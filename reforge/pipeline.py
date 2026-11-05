"""Orchestrates one independent audit run, its safe repairs and their verification."""

import dataclasses
from pathlib import Path
from typing import Callable, Dict, List, Optional, Sequence, Tuple

from reforge.analyzer import run_analyzer
from reforge.audit import audit_window, plan_next_stage, summarize, window_for_stage
from reforge.errors import ReforgeError
from reforge.git_history import commit_count, dirty_paths, head_sha
from reforge.ledger import ledger_artifacts, record_event, stage_files
from reforge.locking import LOCK_REL, run_lock
from reforge.model import Finding, Repair, StagePlan
from reforge.repair import (
    apply_text_patches,
    regression_test_path,
    repair_findings,
    repair_paths,
)
from reforge.review import (
    coverage_for_payload,
    findings_from_payload,
    merge_findings,
    read_findings_file,
    write_packet,
)
from reforge.state import (
    DEFAULT_START,
    DEFAULT_STEP,
    STATE_REL,
    create_run,
    current_run,
    entry_from_stage,
    finalize_review,
    find_run,
    find_unpushed_verified,
    is_reforge_artifact,
    load_state,
    mark_delivered,
    mark_repairs,
    new_delivery,
    pending_fixable,
    pending_reviews,
    record_stage,
    record_review,
    resume_run,
    review_is_ready,
    run_summary,
    runs_summary,
    save_state,
    stop_run,
    unrepaired_findings,
    update_settings,
)
from reforge.verification import (
    default_test_command,
    recheck_repairs,
    review_patch,
    run_test_command,
)

GateRunner = Callable[[], Tuple[bool, Sequence[str]]]


def finding_from_dict(item: Dict[str, object]) -> Finding:
    fields = {field.name for field in dataclasses.fields(Finding)}
    return Finding(**{key: value for key, value in item.items() if key in fields})


def repair_from_dict(item: Dict[str, object]) -> Repair:
    fields = {field.name for field in dataclasses.fields(Repair)}
    return Repair(**{key: value for key, value in item.items() if key in fields})


def _scanner(label: str, text: str):
    try:
        from scripts.check_secrets import scan_diff
    except ImportError:
        return []
    return scan_diff(text, label)


def _stop_value(stop: Optional[int]) -> Optional[int]:
    if stop in (None, 0):
        return None
    try:
        value = int(stop)  # type: ignore[arg-type]
    except (TypeError, ValueError) as exc:
        from reforge.errors import ReforgeError as _ReforgeError
        raise _ReforgeError(
            f"Invalid stop window {stop!r}.",
            "the stop window must be an integer.",
            "pass --stop 0 for unlimited or a positive integer.",
        ) from exc
    return value


def _snapshot(root: Path, findings: Sequence[Finding],
              extra_paths: Sequence[str] = ()) -> Dict[str, Optional[bytes]]:
    from reforge.errors import ReforgeError as _ReforgeError
    paths = {finding.path for finding in findings if finding.fixable}
    try:
        paths.add(str(regression_test_path(root).relative_to(root)).replace("\\", "/"))
    except ValueError as exc:
        raise _ReforgeError(
            "The regression test path escapes the repository.",
            str(exc),
            "run inside the repository so the regression path stays within it.",
        ) from exc
    paths.update(path for path in extra_paths if path)
    snapshots: Dict[str, Optional[bytes]] = {}
    for relative in paths:
        snapshots[relative] = _fingerprint(root / relative)
    return snapshots


def _restore(root: Path, snapshots: Dict[str, Optional[bytes]]) -> List[str]:
    """Restore snapshotted bytes; returns paths that could not be restored."""
    failures: List[str] = []
    for relative, original in snapshots.items():
        path = root / relative
        try:
            if original is None:
                if path.exists():
                    path.unlink()
            else:
                path.parent.mkdir(parents=True, exist_ok=True)
                path.write_bytes(original)
        except OSError:
            failures.append(relative)
            continue
    return failures


def _relative_inside(root: Path, path: Optional[str]) -> str:
    """The repository-relative form of a supplied file, or an empty string when it is outside."""
    if not path:
        return ""
    try:
        return Path(path).resolve().relative_to(Path(root).resolve()).as_posix()
    except (OSError, ValueError, RuntimeError):
        return ""


def _preexisting_dirty(root: Path, ignore: Sequence[str] = ()) -> set:
    """Paths already dirty before Reforge repairs; its own state and artifacts are excluded."""
    ignored = {path.replace("\\", "/") for path in ignore}
    ledger = set(ledger_artifacts(root))
    return {path.replace("\\", "/") for path in dirty_paths(root)
            if path.replace("\\", "/") != STATE_REL.as_posix()
            and path.replace("\\", "/") not in ledger
            and path.replace("\\", "/") not in ignored
            and not is_reforge_artifact(path)}


def _owned_repairs(last: Dict[str, object]) -> set:
    """Paths Reforge repaired itself, excluding targets that were dirty before the repair."""
    dirty = {str(path) for path in (last.get("dirty_targets") or [])}
    return {str(item.get("path") or "") for item in (last.get("repairs") or [])
            if item.get("applied") and item.get("path")} - dirty


def _check_commit_targets(root: Path, targets: Sequence[str], allow_dirty: bool,
                          deliver: bool, ignore: Sequence[str] = (),
                          owned: Sequence[str] = ()) -> None:
    """Refuse a commit whose target file already held work Reforge did not make."""
    if allow_dirty or not deliver:
        return
    overlap = sorted(set(targets) & _preexisting_dirty(root, ignore) - set(owned))
    if overlap:
        shown = ", ".join(overlap[:8])
        raise ReforgeError(
            "Cannot commit a repair over uncommitted work in the same file.",
            f"these finding targets already held changes Reforge did not make: {shown}",
            "run the repair without --commit/--push to apply and verify it, or commit/stash "
            "those files first; nothing was changed.",
        )


def _fingerprint(path: Path) -> Optional[bytes]:
    try:
        return path.read_bytes() if path.is_file() else None
    except OSError:
        return None


def _execute_repairs(root: Path, findings: Sequence[Finding], add_tests: bool,
                     run_tests: bool, test_command: Optional[str],
                     gate_runner: Optional[GateRunner],
                     extra_allowed: Sequence[str] = (),
                     preexisting: Sequence[str] = ()) -> Tuple[List[Repair], Dict[str, object],
                                                                  Dict[str, object]]:
    targets = [finding for finding in findings if finding.fixable and not finding.repaired]
    if not targets:
        return [], {}, {}
    target_paths = {finding.path for finding in targets}
    unrelated = [path for path in preexisting if path not in target_paths]
    snapshots: Dict[str, Optional[bytes]] = {}
    try:
        snapshots = _snapshot(root, targets, unrelated)
        # Deterministic rules keep their proven edit; reviewed findings carry an exact text patch
        # that was validated against the file when the answer was parsed, and is re-checked here.
        rule_findings = [item for item in targets if not item.patch_old]
        patch_findings = [item for item in targets if item.patch_old]
        repairs = repair_findings(root, rule_findings, add_tests=add_tests)
        repairs.extend(apply_text_patches(root, patch_findings))
        applied = [repair for repair in repairs if repair.applied]
        tests: Dict[str, object] = {}
        gates: Dict[str, object] = {}
        if applied:
            issues = recheck_repairs(root, applied)
            allowed = repair_paths(repairs, root) + [STATE_REL.as_posix(), LOCK_REL.as_posix()]
            allowed += [path for path in dirty_paths(root) if is_reforge_artifact(path)]
            allowed += [path for path in extra_allowed if path]
            allowed += [path for path in preexisting if path]
            # The stage checkpoint Reforge appended, and its .bak/.lock siblings, are its own
            # bookkeeping; without this the review would reject every tree on a project with a ledger.
            allowed.extend(ledger_artifacts(root))
            issues += review_patch(root, allowed, _scanner)
            if issues:
                raise ReforgeError(
                    "The repair patch failed review.",
                    "; ".join(issues[:6]),
                    "review the listed paths and re-run; the working tree was restored.",
                )
            command = test_command or default_test_command(root)
            if run_tests and command:
                tests = run_test_command(command, root)
                if not tests.get("passed"):
                    raise ReforgeError(
                        "The repaired tree failed its tests.",
                        f"`{command}` exited {tests.get('code')}: " +
                        " | ".join(str(line) for line in (tests.get("tail") or [])[-3:]),
                        "review the test output; the repair was rolled back.",
                    )
            if gate_runner is not None:
                passed, lines = gate_runner()
                gates = {"passed": passed, "lines": list(lines)}
                if not passed:
                    raise ReforgeError(
                        "The repaired tree failed the project's quality gates.",
                        " | ".join(str(line) for line in list(lines)[-4:]),
                        "review the gates; the repair was rolled back.",
                    )
            changed = [path for path in unrelated
                       if _fingerprint(root / path) != snapshots.get(path)]
            if changed:
                raise ReforgeError(
                    "The repair changed unrelated uncommitted work.",
                    f"these paths differed before and after the repair: {', '.join(changed[:8])}",
                    "review the listed paths; every change made by the repair was rolled back.",
                )
        return repairs, tests, gates
    except ReforgeError as exc:
        failures = _restore(root, snapshots)
        if failures:
            exc = ReforgeError(
                str(exc),
                f"{exc.args[1] if len(exc.args) > 1 else ''} Restore incomplete: "
                f"{', '.join(failures[:8])} could not be restored.",
                str(exc.args[2]) if len(exc.args) > 2 else "",
            )
            raise exc from None
        raise
    except Exception as exc:
        failures = _restore(root, snapshots)
        suffix = f" Restore incomplete: {', '.join(failures[:8])}." if failures else \
            " the working tree was restored."
        raise ReforgeError(
            "The repair could not be applied.",
            f"the repair engine stopped before a reviewable patch existed: {exc}",
            "review the finding evidence, fix the source or the generated test file by hand, "
            f"then run the audit again;{suffix}",
        ) from exc


def _payload(root: Path, mode: str, plan: StagePlan, run: Dict[str, object],
             findings: Sequence[Finding], repairs: Sequence[Repair], tests: Dict[str, object],
             gates: Dict[str, object], skipped: Sequence[str] = (),
             ledger: Optional[Dict[str, object]] = None,
             reviewed: int = 0, review: Optional[Dict[str, object]] = None,
             delivery: Optional[Dict[str, object]] = None,
             delivery_lines: Optional[Sequence[str]] = None) -> Dict[str, object]:
    applied = sum(1 for repair in repairs if repair.applied)
    return {
        "mode": mode,
        "root": str(root),
        "run": plan.run_id,
        "run_status": run.get("status"),
        "stage": plan.stage,
        "plan": plan.as_dict(),
        "counts": summarize(findings),
        "findings": [finding.as_dict() for finding in findings],
        "repairs": [repair.as_dict() for repair in repairs],
        "commit_paths": sorted(set(repair_paths(repairs, root)) | {STATE_REL.as_posix()}),
        "repaired": applied,
        "pending_fixable": len(pending_fixable(run)),
        "reviewed": reviewed,
        "review": review or {},
        "skipped": list(skipped),
        "ledger": ledger or {},
        "delivery": delivery or {},
        "delivery_lines": list(delivery_lines or []),
        "tests": tests,
        "gates": gates,
        "summary": (f"{plan.run_id} stage {plan.stage}: {reviewed} file(s) reviewed, "
                    f"{len(findings)} finding(s), {applied} repaired, window {plan.window}"
                    + (f", {len(skipped)} binary file(s) not analysed" if skipped else "")),
    }


def _review_error(run: Dict[str, object], pending: Sequence[Dict[str, object]]) -> ReforgeError:
    return ReforgeError(
        f"Audit run {run.get('id')} has {len(pending)} fixable finding(s) awaiting repair.",
        "an audit is a review in progress; starting the next stage would move its history past "
        "findings that were never repaired.",
        f"run `reforge fix <project> --run {run.get('id')}`, or `reforge stop <project> --run "
        f"{run.get('id')}` to abandon this review and start a new audit later.",
    )


def _plan_from_last(run: Dict[str, object], last: Dict[str, object]) -> StagePlan:
    """Rebuild the stage a `fix` must apply, from the run and its last audit entry."""
    return StagePlan(
        stage=int(last.get("stage") or 0), window=int(last.get("window") or 0),
        commits=(), new_shas=tuple(last.get("new_commits") or []),
        prior_shas=tuple(last.get("prior_commits") or []),
        run_id=str(run.get("id") or ""),
        start=int(run.get("start") or DEFAULT_START),
        step=int(run.get("step") or DEFAULT_STEP),
        stop=run.get("stop") if isinstance(run.get("stop"), int) else None,
    )


def _collect_review(root: Path, plan: StagePlan, reviewed: Optional[Sequence[str]],
                    findings_file: Optional[str], packet: bool,
                    method: str = "host") -> Dict[str, object]:
    """Write the review packet and load the reviewer's answer, if one was supplied.

    Reforge does not call a model. `packet` writes the stage's full diff for a reviewer to read;
    `findings_file` supplies that reviewer's answer, and `method` records whether the host or an
    analyzer produced it. Both are optional, so the planner can record a stage before any review.
    """
    report: Dict[str, object] = {
        "status": "unreviewed", "findings": [], "rejected": [], "files": list(reviewed or []),
        "packet": "", "redacted": 0, "reason": "", "method": "",
    }
    if packet:
        path, redactions = write_packet(root, plan, list(reviewed or []))
        report.update(packet=str(path), redacted=redactions)
    if findings_file:
        try:
            payload = read_findings_file(Path(findings_file))
        except (OSError, UnicodeDecodeError, ValueError) as exc:
            raise ReforgeError(
                f"The findings file cannot be read: {findings_file}",
                f"it must hold one JSON object or array: {exc}",
                "write the findings as the packet's prompt describes, then pass the file again; "
                "nothing was changed.",
            ) from exc
        found, rejected = findings_from_payload(
            root, payload, plan, list(reviewed) if reviewed is not None else None)
        coverage = coverage_for_payload(root, plan, payload)
        if coverage:
            report["coverage"] = coverage
        status = "reviewed"
        reason = "the answer held no findings" if not found and not rejected else ""
        reported = payload.get("reviewed_hunks") if isinstance(payload, dict) else None
        if not isinstance(reported, list):
            status = "partial"
            reason = ("the answer did not list reviewed_hunks; every packet hunk must carry a "
                      "quote and a note before the review counts")
        elif (coverage.get("missing") or coverage.get("unknown")
              or coverage.get("invalid")):
            status = "partial"
            first = (coverage.get("invalid") or [{}])[0]
            detail = (f"; {first.get('id')}: {first.get('reason')}" if first.get("reason") else "")
            reason = (f"the answer attested {coverage.get('reported', 0)}/"
                      f"{coverage.get('total', 0)} hunks; "
                      f"{len(coverage.get('missing') or [])} missing, "
                      f"{len(coverage.get('unknown') or [])} unknown, "
                      f"{len(coverage.get('invalid') or [])} unattested{detail}")
        report.update(status=status, findings=found, rejected=rejected, method=method)
        if reason:
            report["reason"] = reason
    elif not packet:
        report["reason"] = "no review supplied"
    else:
        report["reason"] = "awaiting the reviewer's findings"
    return report


def _serialize_review(report: Dict[str, object]) -> Dict[str, object]:
    """The small JSON-safe form of a review kept in state and printed by the CLI."""
    meta = {key: value for key, value in report.items() if key != "findings"}
    meta["findings"] = [item.as_dict() for item in report.get("findings") or []]
    return meta


def _note_stage(root: Path, run: Dict[str, object], plan: StagePlan, entry: Dict[str, object],
                findings: Sequence[Finding], skipped: Sequence[str]) -> Dict[str, object]:
    """Mirror one stage into the repository's task ledger so cold start can see the audit."""
    applied = sum(1 for repair in entry.get("repairs") or [] if repair.get("applied"))
    counts = ", ".join(f"{name}={value}" for name, value in sorted((entry.get("counts") or {}).items()))
    review = entry.get("review") or {}
    delivery = entry.get("delivery") if isinstance(entry.get("delivery"), dict) else {}
    if delivery.get("empty"):
        ship = "empty — nothing to commit"
    elif delivery.get("pushed") and delivery.get("short"):
        ship = f"commit {delivery.get('short')} pushed"
    elif (delivery.get("commit") or delivery.get("short")) and not delivery.get("pushed"):
        ship = f"commit {delivery.get('short') or delivery.get('commit')} verified-but-unpushed"
    elif applied:
        ship = "verified-but-uncommitted"
    else:
        ship = "no repairs"
    description = (
        f"window {plan.window}, {len(entry.get('new_commits') or [])} commit(s), "
        f"{int(entry.get('reviewed') or 0)} file(s) reviewed ({review.get('status') or 'unreviewed'}), "
        f"{len(findings)} finding(s), {applied} repaired, {ship}"
        + (f", {len(skipped)} binary not analysed" if skipped else "")
        + (f" ({counts})" if counts else "")
    )
    return record_event(root, plan.run_id, plan.stage, description,
                        stage_files(findings, skipped),
                        status="completed" if run.get("status") == "completed" else "in_progress")


def _delivery_message(run_id: str, stage: int, repaired: int) -> str:
    """Conventional message shared by the stage-close hook (no caller variants)."""
    if repaired:
        return f"fix(reforge): repair {run_id} stage {stage} findings"
    return f"chore(reforge): record {run_id} stage {stage} audit"


def _publish_backlog(root: Path, state: Dict[str, object],
                     run: Dict[str, object]) -> Tuple[Dict[str, object], List[str]]:
    """Push previously verified-but-unpushed windows before auditing the next one.

    A single `git push` publishes every local window commit, so all pending stages
    flip to pushed together keeping their own SHAs. Only runs when the operator
    passed `--push`; otherwise the backlog accumulates and the next stage proceeds.
    """
    from reforge.delivery import push_committed

    pending = find_unpushed_verified(run)
    if not pending:
        return {"pushed": False, "stages": []}, []
    push_committed(root)
    head = head_sha(root)
    pushed_stages: List[int] = []
    for entry in pending:
        stage = int(entry.get("stage") or 0)
        delivery = dict(entry.get("delivery") or {})
        # find_unpushed_verified only returns stages that already hold a local
        # commit SHA, so the commit is kept verbatim; the push flips pushed only.
        delivery["pushed"] = True
        delivery["push_error"] = None
        mark_delivered(root, state, run, stage, delivery)
        pushed_stages.append(stage)
    line = f"[OK] Pushed {len(pushed_stages)} pending window(s) without force: " + ",".join(
        f"stage {stage}" for stage in pushed_stages)
    record_event(root, str(run.get("id")), int(pushed_stages[-1]),
                 f"backlog push of stage(s) {','.join(str(s) for s in pushed_stages)}; HEAD {head[:12] if head else 'unknown'}",
                 status="completed" if run.get("status") == "completed" else "in_progress")
    return {"pushed": True, "stages": pushed_stages, "commit": head}, [line]


def _close_window(root: Path, state: Dict[str, object], run: Dict[str, object],
                  entry: Dict[str, object], commit_paths: Sequence[str],
                  do_commit: bool, do_push: bool) -> Tuple[Dict[str, object], List[str]]:
    """Commit and push one verified window; empty windows never commit.

    Must run inside `run_lock()` after `record_stage()`. Repair rollback never runs
    here: verified repairs stay in the tree and only the delivery mark changes on
    commit/push failure (verified-but-uncommitted / verified-but-unpushed).
    The post-push hash update is a second `save_state()` that rides dirty until the
    next window's commit; resume reads disk state so it still lands correctly.
    """
    from reforge.delivery import deliver

    applied = sum(1 for item in (entry.get("repairs") or [])
                  if isinstance(item, dict) and item.get("applied"))
    stage = int(entry.get("stage") or 0)
    run_id = str(entry.get("run") or run.get("id") or "")
    if applied == 0:
        delivery = new_delivery(empty=True)
        entry["delivery"] = delivery
        mark_delivered(root, state, run, stage, delivery)
        return {"commit": "", "short": "", "pushed": False, "empty": True}, [
            "[OK] Nothing to commit: the window held no applied repairs."]
    if not do_commit and not do_push:
        delivery = new_delivery(empty=False)
        entry["delivery"] = delivery
        mark_delivered(root, state, run, stage, delivery)
        return {"commit": "", "short": "", "pushed": False, "empty": False}, [
            "Not committed: pass --commit to publish this window, --push to publish and push."]
    message = _delivery_message(run_id, stage, applied)
    try:
        report, lines = deliver(root, message, do_push, paths=list(commit_paths))
    except ReforgeError as exc:
        text = f"{exc.message or ''} {exc.why or ''}".lower()
        is_push_failure = ("push failed" in text or "commit is local" in text)
        if is_push_failure:
            full = head_sha(root)
            delivery = {"commit": full, "short": (full[:7] if full else ""),
                        "pushed": False, "push_error": exc.message,
                        "empty": False}
        else:
            delivery = {"commit": "", "short": "", "pushed": False,
                        "push_error": exc.message, "empty": False}
        entry["delivery"] = delivery
        mark_delivered(root, state, run, stage, delivery)
        raise
    if report.get("nothing_to_commit"):
        delivery = new_delivery(empty=True)
        entry["delivery"] = delivery
        mark_delivered(root, state, run, stage, delivery)
        return {"commit": "", "short": "", "pushed": False, "empty": True}, list(lines)
    full = head_sha(root)
    short = str(report.get("commit") or "")
    delivery = {"commit": full or short, "short": short,
                "pushed": bool(do_push and report.get("pushed")),
                "push_error": None, "empty": False}
    entry["delivery"] = delivery
    mark_delivered(root, state, run, stage, delivery)
    return {"commit": delivery["commit"], "short": short,
            "pushed": delivery["pushed"], "empty": False}, list(lines)


def _note_review(root: Path, run: Dict[str, object], stage: int,
                 review: Dict[str, object]) -> Dict[str, object]:
    """Mirror a host review into the task ledger, including the completion it may unlock."""
    description = (
        f"stage {stage} {review.get('method') or 'host'} review "
        f"{review.get('status') or 'incomplete'}; "
        f"run {run.get('status') or 'active'}"
        + (f"; coverage {review.get('coverage', {}).get('reported', 0)}/"
           f"{review.get('coverage', {}).get('total', 0)}"
           if isinstance(review.get("coverage"), dict) else "")
    )
    return record_event(root, str(run.get("id")), stage, description,
                        status="completed" if run.get("status") == "completed" else "in_progress")


def run_pipeline(root: Path, mode: str = "run", add_tests: bool = True,
                 run_tests: bool = True, test_command: Optional[str] = None,
                 gate_runner: Optional[GateRunner] = None,
                 allow_dirty: bool = False, run_id: Optional[str] = None,
                 start: Optional[int] = None, step: Optional[int] = None,
                 stop: Optional[int] = None, rules: bool = True,
                 findings_file: Optional[str] = None,
                 packet: bool = True, deliver: bool = False,
                 do_push: bool = False) -> Dict[str, object]:
    """Audit the next stage (`audit`), repair the last one (`fix`), or do both (`run`).

    `deliver` commits one verified window, `do_push` pushes it (implies commit).
    Both run inside `run_lock()` via `_close_window()`; empty windows never commit.
    A `--push` invocation first publishes any verified-but-unpushed backlog, then
    closes the current window, so resume knows exactly which windows landed.
    """
    root = Path(root)
    findings_rel = _relative_inside(root, findings_file)
    do_commit = bool(deliver or do_push)
    with run_lock(root):
        state = load_state(root)
        if mode == "fix":
            run = current_run(state, run_id)
            total_commits = (None if isinstance(run.get("stop"), int)
                             else (commit_count(root) or None))
            last = run.get("last_audit")
            if not isinstance(last, dict):
                raise ReforgeError(
                    f"Audit run {run.get('id')} has no audit to fix.",
                    "`fix` repairs the findings of a run's latest completed stage.",
                    "run `audit` or `run` first; nothing was changed.",
                )
            plan = _plan_from_last(run, last)
            all_findings = [finding_from_dict(item) for item in unrepaired_findings(run)]
            review_meta = dict(last.get("review") or last.get("ai") or {})
            reviewed = int(last.get("reviewed") or 0)
            skipped = list(last.get("skipped") or [])
            if not findings_file and not review_is_ready(run):
                raise ReforgeError(
                    f"Audit run {run.get('id')} stage {last.get('stage')} is awaiting host review.",
                    "no repair may be accepted from an unreviewed stage packet.",
                    "review the packet and rerun `fix` with `--findings <file>`; nothing was changed.",
                )
            if findings_file:
                report = _collect_review(root, plan, review_meta.get("files") or None,
                                         findings_file, packet=False)
                report["packet"] = review_meta.get("packet") or report.get("packet") or ""
                report["redacted"] = review_meta.get("redacted") or 0
                all_findings = merge_findings(all_findings, report.get("findings") or [])
                review_meta = _serialize_review(report)
                last["findings"] = [item.as_dict() for item in all_findings]
                last["counts"] = summarize(all_findings)
                last["review"] = review_meta
            fixable = [item for item in all_findings if item.fixable]
            guard = {item.path for item in fixable if not item.repaired}
            guard |= {str(item.get("path")) for item in (last.get("repairs") or [])
                      if item.get("applied") and item.get("path")}
            _check_commit_targets(
                root, sorted(guard), allow_dirty, do_commit, (findings_rel,), _owned_repairs(last))
            backlog_lines: List[str] = []
            if do_push:
                _, backlog_lines = _publish_backlog(root, state, run)
            if not fixable:
                if findings_file:
                    finalize_review(root, state, run, total_commits=total_commits)
                    ledger = _note_review(root, run, int(last.get("stage") or 0), review_meta)
                    return _payload(root, mode, plan, run, all_findings,
                                    [repair_from_dict(item) for item in (last.get("repairs") or [])],
                                    last.get("tests") or {}, last.get("gates") or {},
                                    skipped, ledger, reviewed=reviewed, review=review_meta,
                                    delivery=dict(last.get("delivery") or {}),
                                    delivery_lines=list(backlog_lines))
                # `audit` then `fix` in two invocations leaves a reviewed patch uncommitted;
                # a second `fix --commit` publishes it instead of refusing (the CLI's own advice).
                applied = [repair_from_dict(item) for item in (last.get("repairs") or [])
                           if item.get("applied")]
                pending = [path for path in repair_paths(applied, root)
                           if path in dirty_paths(root)]
                if not pending:
                    raise ReforgeError(
                        f"Audit run {run.get('id')} has no safe automatic repair left.",
                        "every remaining finding needs a human decision, or every repair is complete.",
                        f"review the evidence, then start the next audit or `reforge stop <project> "
                        f"--run {run.get('id')}`.",
                    )
                if do_commit or do_push:
                    commit_paths = sorted(set(repair_paths(applied, root))
                                          | {STATE_REL.as_posix()})
                    delivery_report, delivery_lines = _close_window(
                        root, state, run, last, commit_paths, do_commit, do_push)
                    ledger = _note_stage(root, run, plan, last, all_findings, skipped)
                    return _payload(root, mode, plan, run, all_findings, applied,
                                    last.get("tests") or {}, last.get("gates") or {},
                                    skipped, ledger, reviewed=reviewed, review=review_meta,
                                    delivery=delivery_report,
                                    delivery_lines=list(backlog_lines) + list(delivery_lines))
                return _payload(root, mode, plan, run, all_findings, applied,
                                last.get("tests") or {}, last.get("gates") or {},
                                skipped, reviewed=reviewed, review=review_meta,
                                delivery=dict(last.get("delivery") or {}),
                                delivery_lines=list(backlog_lines))
            preexisting = _preexisting_dirty(root, (findings_rel,))
            targets = [item.path for item in fixable if not item.repaired]
            if targets:
                fresh = sorted(set(targets) & preexisting)
                prior = {str(path) for path in (last.get("dirty_targets") or [])}
                last["dirty_targets"] = sorted(prior | set(fresh))
            repairs, tests, gates = _execute_repairs(root, all_findings, add_tests, run_tests,
                                                     test_command, gate_runner,
                                                     extra_allowed=(findings_rel,),
                                                     preexisting=preexisting)
            last["repairs"] = [repair.as_dict() for repair in repairs]
            last["tests"] = tests
            last["gates"] = gates
            last["review"] = review_meta
            mark_repairs(root, state, run, repairs)
            finalize_review(root, state, run, total_commits=total_commits)
            if do_commit or do_push:
                # Re-read the persisted entry so the commit stages the saved state file.
                refreshed = run.get("last_audit") if isinstance(run.get("last_audit"), dict) else last
                commit_paths = sorted(set(repair_paths(repairs, root)) | {STATE_REL.as_posix()})
                delivery_report, delivery_lines = _close_window(
                    root, state, run, refreshed, commit_paths, do_commit, do_push)
                if findings_file:
                    _note_review(root, run, int(last.get("stage") or 0), review_meta)
                ledger = _note_stage(root, run, plan, refreshed, all_findings, skipped)
                return _payload(root, mode, plan, run, all_findings, repairs, tests, gates,
                                skipped, ledger, reviewed=reviewed, review=review_meta,
                                delivery=delivery_report,
                                delivery_lines=list(backlog_lines) + list(delivery_lines))
            ledger = _note_review(root, run, int(last.get("stage") or 0), review_meta) \
                if findings_file else None
            # Record the verified-but-uncommitted mark without a ledger checkpoint.
            _close_window(root, state, run, last,
                          sorted(set(repair_paths(repairs, root)) | {STATE_REL.as_posix()}),
                          False, False)
            return _payload(root, mode, plan, run, all_findings, repairs, tests, gates,
                            skipped, ledger, reviewed=reviewed, review=review_meta,
                            delivery=dict(last.get("delivery") or {}),
                            delivery_lines=list(backlog_lines))

        if mode not in {"audit", "run"}:
            raise ReforgeError(
                f"Unknown mode '{mode}'.",
                "Reforge supports audit, fix and run.",
                "run `--help` to list the valid commands.",
                exit_code=2,
            )
        run = find_run(state, run_id)
        if run is None:
            run = create_run(state, start if start is not None else DEFAULT_START,
                             step if step is not None else DEFAULT_STEP,
                             _stop_value(stop))
            save_state(root, state)
        elif any(value is not None for value in (start, step, stop)):
            raise ReforgeError(
                f"Audit run {run.get('id')} already has its window settings.",
                "a run keeps the start/step/stop it was created with so its stages stay explainable.",
                f"change them with `reforge settings <project> --run {run.get('id')}`, "
                "or start a new run.",
                exit_code=2,
            )
        pending = pending_fixable(run)
        if pending:
            raise _review_error(run, pending)
        if do_commit or do_push:
            from reforge.state import find_uncommitted_verified
            uncommitted = find_uncommitted_verified(run)
            if uncommitted:
                stages = ", ".join(str(int(e.get("stage") or 0)) for e in uncommitted)
                raise ReforgeError(
                    f"Stage(s) {stages} are verified-but-uncommitted.",
                    "a new --commit/--push audit would orphan those repairs in the tree.",
                    "publish the previous window first (e.g. `reforge fix <project> "
                    f"--findings <file> --commit` for stage {stages}), or run without "
                    "--commit/--push; nothing was changed.",
                )
        backlog_lines: List[str] = []
        if do_push:
            _, backlog_lines = _publish_backlog(root, state, run)
        plan = plan_next_stage(root, run)
        skipped: List[str] = []
        reviewed: List[str] = []
        findings = audit_window(root, plan, run.get("history") or [], skipped, reviewed, rules)
        review = _collect_review(root, plan, reviewed, findings_file, packet)
        findings = merge_findings(findings, review.get("findings") or [])
        review_meta = _serialize_review(review)
        if mode == "audit":
            entry = entry_from_stage(plan, findings, [], skipped=skipped,
                                     reviewed=len(reviewed), review=review_meta)
            record_stage(root, state, run, entry,
                         total_commits=(None if isinstance(run.get("stop"), int)
                                        else (commit_count(root) or None)))
            return _payload(root, mode, plan, run, findings, [], {}, {}, skipped,
                            _note_stage(root, run, plan, entry, findings, skipped),
                            reviewed=len(reviewed), review=review_meta,
                            delivery=dict(entry.get("delivery") or {}),
                            delivery_lines=list(backlog_lines))
        _check_commit_targets(root, [item.path for item in findings if item.fixable],
                              allow_dirty, do_commit, (findings_rel,))
        preexisting = _preexisting_dirty(root, (findings_rel,))
        repairs, tests, gates = _execute_repairs(root, findings, add_tests, run_tests,
                                                 test_command, gate_runner,
                                                 extra_allowed=(findings_rel,),
                                                 preexisting=preexisting)
        entry = entry_from_stage(plan, findings, repairs, tests, gates, skipped=skipped,
                                 reviewed=len(reviewed), review=review_meta)
        entry["dirty_targets"] = sorted(
            {item.path for item in findings if item.fixable} & preexisting)
        record_stage(root, state, run, entry,
                     total_commits=(None if isinstance(run.get("stop"), int)
                                    else (commit_count(root) or None)))
        mark_repairs(root, state, run, repairs)
        commit_paths = sorted(set(repair_paths(repairs, root)) | {STATE_REL.as_posix()})
        delivery_report, delivery_lines = _close_window(
            root, state, run, entry, commit_paths, do_commit, do_push)
        return _payload(root, mode, plan, run, findings, repairs, tests, gates, skipped,
                        _note_stage(root, run, plan, entry, findings, skipped),
                        reviewed=len(reviewed), review=review_meta,
                        delivery=delivery_report,
                        delivery_lines=list(backlog_lines) + list(delivery_lines))


def review_stage(root: Path, run_id: Optional[str] = None, stage: Optional[int] = None,
                 findings_file: Optional[str] = None,
                 method: str = "host") -> Dict[str, object]:
    """Record a host or analyzer review of any retained stage, including an older one."""
    root = Path(root)
    if stage is None or not findings_file:
        raise ReforgeError(
            "A review needs both a stage and an answer file.",
            "Reforge records which packet hunks the host actually read.",
            "run `reforge review <project> --stage <n> --findings <file>`; nothing was changed.",
            exit_code=2,
        )
    with run_lock(root):
        state = load_state(root)
        run = current_run(state, run_id)
        total_commits = (None if isinstance(run.get("stop"), int)
                         else (commit_count(root) or None))
        entry = next((item for item in (run.get("history") or [])
                      if isinstance(item, dict) and item.get("stage") == stage), None)
        last = run.get("last_audit")
        if isinstance(last, dict) and last.get("stage") == stage:
            entry = last
        if entry is None:
            raise ReforgeError(
                f"Audit run {run.get('id')} has no stage {stage} to review.",
                "only a stage still in the run's retained history can be reviewed.",
                "run `reforge report <project>` to list the stages that are available.",
                exit_code=2,
            )
        plan = _plan_from_last(run, entry)
        review_meta = dict(entry.get("review") or {})
        files = review_meta.get("files")
        report = _collect_review(root, plan, files if isinstance(files, list) else None,
                                 findings_file, packet=False, method=method)
        report["packet"] = review_meta.get("packet") or report.get("packet") or ""
        report["redacted"] = review_meta.get("redacted") or 0
        if report.get("status") != "reviewed":
            raise ReforgeError(
                f"Stage {stage} was not reviewed: the answer is incomplete.",
                str(report.get("reason") or "every packet hunk must be attested in reviewed_hunks."),
                "read the packet, give each hunk a verbatim quote and a distinct note in "
                "`reviewed_hunks`, then pass the answer again; nothing was changed.",
            )
        findings = [finding_from_dict(item) for item in entry.get("findings") or []]
        findings = merge_findings(findings, report.get("findings") or [])
        entry["findings"] = [item.as_dict() for item in findings]
        entry["counts"] = summarize(findings)
        review_meta = _serialize_review(report)
        entry["review"] = review_meta
        record_review(root, state, run, int(stage), review_meta,
                      total_commits=total_commits)
        return _payload(root, "review", plan, run, findings, [], entry.get("tests") or {},
                        entry.get("gates") or {}, entry.get("skipped") or [],
                        _note_review(root, run, int(stage), review_meta),
                        reviewed=int(entry.get("reviewed") or 0), review=review_meta)


def analyze_stage(root: Path, run_id: Optional[str] = None, stage: Optional[int] = None,
                  command: str = "", timeout: float = 300.0) -> Dict[str, object]:
    """Run the configured analyzer over one stage packet, then record its answer as the review."""
    root = Path(root)
    if not command.strip():
        raise ReforgeError(
            "the analyze command needs an analyzer.",
            "Reforge runs the analyzer the operator names; it does not pick a model.",
            "pass --analyzer with a command that writes the findings JSON.",
            exit_code=2,
        )
    state = load_state(root)
    run = current_run(state, run_id)
    entry = None
    if stage is None:
        entry = run.get("last_audit")
    else:
        entry = next((item for item in (run.get("history") or [])
                      if isinstance(item, dict) and item.get("stage") == stage), None)
    if not isinstance(entry, dict):
        raise ReforgeError(
            f"Audit run {run.get('id')} has no audited stage to analyze.",
            "the analyzer needs a stage packet that already exists.",
            "run `reforge audit` for that stage first, then retry.",
        )
    packet = (entry.get("review") or {}).get("packet") or ""
    if not packet:
        raise ReforgeError(
            f"Audit run {run.get('id')} stage {entry.get('stage')} has no packet.",
            "a stage without a packet has nothing for the analyzer to read.",
            "run `reforge audit` again for that stage, then retry.",
        )
    candidate = Path(packet)
    if not candidate.is_absolute():
        for base in (root, Path.cwd()):
            resolved = base / candidate
            if resolved.is_file():
                candidate = resolved
                break
    _, answer = run_analyzer(root, candidate, command, timeout)
    try:
        return review_stage(root, run_id=str(run.get("id") or ""),
                            stage=int(entry.get("stage") or 0),
                            findings_file=str(answer), method="analyzer")
    finally:
        answer.unlink(missing_ok=True)


def start_audit(root: Path, start: Optional[int] = None, step: Optional[int] = None,
                stop: Optional[int] = None) -> Dict[str, object]:
    """Create a new independent run, refusing while another run is still active."""
    root = Path(root)
    with run_lock(root):
        state = load_state(root)
        active = find_run(state)
        if active is not None and active.get("status") == "active":
            raise ReforgeError(
                f"Audit run {active.get('id')} is still active.",
                "two runs in one project would interleave their stage windows and patches.",
                f"finish or stop it first: `reforge stop <project> --run {active.get('id')}`, "
                "or use a different project; each project has its own lock and state.",
            )
        run = create_run(state, start if start is not None else DEFAULT_START,
                         step if step is not None else DEFAULT_STEP, _stop_value(stop))
        save_state(root, state)
        ledger = record_event(root, str(run["id"]), 0,
                              f"run started (start={run['start']}, step={run['step']}, "
                              f"stop={run['stop']})")
        return {"mode": "start", "root": str(root), "run": run_summary(run),
                "runs": runs_summary(state), "ledger": ledger}


def stop_audit(root: Path, run_id: Optional[str] = None) -> Dict[str, object]:
    root = Path(root)
    with run_lock(root):
        state = load_state(root)
        run = current_run(state, run_id)
        stopped = stop_run(root, state, run)
        ledger = record_event(root, str(stopped["id"]), int(stopped.get("stage") or 0),
                              f"run stopped at stage {stopped.get('stage') or 0}; "
                              "resume it with `reforge resume`", status="suspended")
        return {"mode": "stop", "root": str(root), "run": run_summary(stopped),
                "runs": runs_summary(state), "ledger": ledger}


def resume_audit(root: Path, run_id: Optional[str] = None) -> Dict[str, object]:
    root = Path(root)
    with run_lock(root):
        state = load_state(root)
        run = current_run(state, run_id)
        resumed = resume_run(root, state, run)
        ledger = record_event(root, str(resumed["id"]), int(resumed.get("stage") or 0),
                              "run resumed")
        return {"mode": "resume", "root": str(root), "run": run_summary(resumed),
                "runs": runs_summary(state), "ledger": ledger}


def configure_audit(root: Path, run_id: Optional[str] = None, start: Optional[int] = None,
                    step: Optional[int] = None, stop: Optional[int] = None) -> Dict[str, object]:
    root = Path(root)
    with run_lock(root):
        state = load_state(root)
        run = current_run(state, run_id)
        changes: Dict[str, object] = {}
        if start is not None:
            changes["start"] = start
        if step is not None:
            changes["step"] = step
        if stop is not None:
            changes["stop"] = _stop_value(stop)
        updated = update_settings(root, state, run, **changes)
        return {"mode": "settings", "root": str(root), "run": run_summary(updated),
                "runs": runs_summary(state)}


def runs_payload(root: Path) -> Dict[str, object]:
    root = Path(root)
    state = load_state(root)
    return {"root": str(root), "active_run": state.get("active_run"),
            "last_run": state.get("last_run"), "runs": runs_summary(state)}


def status_payload(root: Path) -> Dict[str, object]:
    root = Path(root)
    state = load_state(root)
    run = find_run(state)
    stage = int((run or {}).get("stage") or 0)
    pending = len(pending_fixable(run)) if run else 0
    next_window = None
    if run and run.get("status") == "active":
        next_window = window_for_stage(stage + 1, int(run.get("start") or DEFAULT_START),
                                       int(run.get("step") or DEFAULT_STEP),
                                       run.get("stop") if isinstance(run.get("stop"), int) else None)
    last = (run or {}).get("last_audit")
    review = (last.get("review") or last.get("ai") or {}) if isinstance(last, dict) else {}
    return {
        "root": str(root),
        "head": head_sha(root),
        "stage": stage,
        "next_stage": stage + 1,
        "next_window": next_window,
        "audited_commits": len((run or {}).get("audited_commits") or []),
        "pending_findings": pending,
        "review": review,
        "unreviewed_stages": [int(entry.get("stage") or 0)
                              for entry in pending_reviews(run)] if run else [],
        "active_run": state.get("active_run"),
        "last_run": state.get("last_run"),
        "run": run_summary(run) if run else None,
        "runs": runs_summary(state),
        "last_audit": last,
        "history": len((run or {}).get("history") or []),
    }


def report_payload(root: Path) -> Dict[str, object]:
    root = Path(root)
    state = load_state(root)
    return {
        "root": str(root),
        "active_run": state.get("active_run"),
        "last_run": state.get("last_run"),
        "runs": list(state.get("runs") or []),
    }
