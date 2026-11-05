"""Persistent audit runs, written atomically and isolated per project."""

import json
import time
from pathlib import Path
from typing import Dict, List, Optional

from reforge.errors import ReforgeError
from reforge.model import Finding, Repair, StagePlan

SCHEMA_VERSION = 2
STATE_REL = Path(".aikit") / "reforge.json"
MAX_HISTORY = 20
DEFAULT_START = 3
DEFAULT_STEP = 3
_UNSET = object()


def state_path(root: Path) -> Path:
    return Path(root) / STATE_REL


def is_reforge_artifact(relative: str) -> bool:
    """Backups, temp files and locks belong to Reforge, not to the reviewed patch."""
    path = relative.replace("\\", "/")
    return path.startswith(".aikit/reforge.") and path != STATE_REL.as_posix()


def new_state() -> Dict[str, object]:
    """A fresh state with mirrored top-level fields for schema-1 readers and reports."""
    return {
        "schema": SCHEMA_VERSION,
        "next_run_id": 1,
        "active_run": None,
        "last_run": None,
        "runs": [],
        # Mirrors of the last run, kept so status/report and older tooling stay readable.
        "stage": 0,
        "window": 0,
        "audited_commits": [],
        "last_audit": None,
        "history": [],
    }


def _now() -> str:
    return time.strftime("%Y-%m-%dT%H:%M:%S")


def validate_settings(start: int, step: int, stop: Optional[int]) -> None:
    """A run's window plan: start >= 2, step >= 1, and an optional stop at or past start."""
    # bool is an int subclass but never a valid window; fail closed instead of
    # letting True coerce to 1 and slip past the bounds.
    if type(start) is not int or type(step) is not int or (stop is not None and type(stop) is not int):
        raise ReforgeError(
            f"Invalid window settings start={start!r} step={step!r} stop={stop!r}.",
            "start, step and stop must be integers.",
            "pass --start 2 or more, --step 1 or more, --stop 0 (unlimited) or larger.",
            exit_code=2,
        )
    if start < 2:
        raise ReforgeError(
            f"--start must be at least 2, not {start}.",
            "a one-commit audit cannot compare a change with its surroundings.",
            "pass --start 2 or more.",
            exit_code=2,
        )
    if step < 1:
        raise ReforgeError(
            f"--step must be at least 1, not {step}.",
            "the window must include at least one new commit per stage.",
            "pass --step 1 or more.",
            exit_code=2,
        )
    if stop is not None and stop < start:
        raise ReforgeError(
            f"--stop ({stop}) is smaller than --start ({start}).",
            "a run that stops before its first window would audit nothing.",
            "pass --stop 0 (unlimited) or a value at least as large as --start.",
            exit_code=2,
        )


def _stage_key(entry: Dict[str, object]) -> tuple:
    return (entry.get("run"), entry.get("stage"), entry.get("window"), entry.get("timestamp"))


def sync_last_audit(run: Dict[str, object]) -> None:
    """Point the run's history at its last audit entry after a later `fix` wrote it.

    A separate `fix` invocation reloads the state from disk, where `last_audit` and the
    matching history entry are two distinct objects; updating only one left `report`
    showing the pre-repair stage entry.
    """
    last = run.get("last_audit")
    if not isinstance(last, dict):
        return
    key = _stage_key(last)
    history = list(run.get("history") or [])
    for index in range(len(history) - 1, -1, -1):
        entry = history[index]
        if isinstance(entry, dict) and _stage_key(entry) == key:
            history[index] = last
            run["history"] = history
            return


def _mirror(state: Dict[str, object], run: Optional[Dict[str, object]]) -> None:
    sync_last_audit(run or {})
    for key, default in (("stage", 0), ("window", 0), ("audited_commits", []),
                         ("last_audit", None), ("history", [])):
        state[key] = (run or {}).get(key, default)


def create_run(state: Dict[str, object], start: int = DEFAULT_START,
               step: int = DEFAULT_STEP, stop: Optional[int] = None) -> Dict[str, object]:
    """Add one independent audit run and make it active; its history starts empty."""
    validate_settings(start, step, stop)
    run_id = f"run-{int(state.get('next_run_id') or 1)}"
    state["next_run_id"] = int(state.get("next_run_id") or 1) + 1
    run = {
        "id": run_id,
        "start": start,
        "step": step,
        "stop": stop,
        "stage": 0,
        "window": 0,
        "audited_commits": [],
        "status": "active",
        "created": _now(),
        "updated": _now(),
        "last_audit": None,
        "history": [],
    }
    state.setdefault("runs", []).append(run)
    state["active_run"] = run_id
    state["last_run"] = run_id
    _mirror(state, run)
    return run


def _find_by_id(state: Dict[str, object], run_id: str) -> Optional[Dict[str, object]]:
    return next((run for run in state.get("runs") or [] if run.get("id") == run_id), None)


def find_run(state: Dict[str, object], run_id: Optional[str] = None) -> Optional[Dict[str, object]]:
    """The named run, else the active one, else the most recent; None when there is none."""
    if run_id:
        run = _find_by_id(state, run_id)
        if run is None:
            raise ReforgeError(
                f"No audit run named '{run_id}'.",
                "run IDs are recorded in `.aikit/reforge.json` and shown by `reforge runs`.",
                "run `reforge runs <project>` to list them.",
                exit_code=2,
            )
        return run
    for key in ("active_run", "last_run"):
        selected = state.get(key)
        if selected:
            run = _find_by_id(state, str(selected))
            if run is not None:
                return run
    runs = state.get("runs") or []
    return runs[-1] if runs else None


def current_run(state: Dict[str, object], run_id: Optional[str] = None) -> Dict[str, object]:
    run = find_run(state, run_id)
    if run is None:
        raise ReforgeError(
            "No audit run exists yet.",
            "start one so its window settings and history have a home.",
            "run `reforge start <project> --start 3 --step 3 --stop 15`.",
        )
    return run


def _migrate_v1(data: Dict[str, object]) -> Dict[str, object]:
    """A schema-1 state becomes run-1 without losing its stage, commits or history."""
    run = {
        "id": "run-1",
        "start": DEFAULT_START,
        "step": DEFAULT_STEP,
        "stop": None,
        "stage": int(data.get("stage") or 0),
        "window": int(data.get("window") or 0),
        "audited_commits": list(data.get("audited_commits") or []),
        "status": "active",
        "created": _now(),
        "updated": _now(),
        "last_audit": data.get("last_audit"),
        "history": list(data.get("history") or []),
    }
    state = new_state()
    state["next_run_id"] = 2
    state["runs"] = [run]
    state["active_run"] = "run-1"
    state["last_run"] = "run-1"
    _mirror(state, run)
    return state


def load_state(root: Path) -> Dict[str, object]:
    """Read the state; a missing file is fresh, schema 1 migrates in memory, corrupt is refused."""
    path = state_path(root)
    if not path.is_file():
        return new_state()
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeDecodeError, ValueError) as exc:
        raise ReforgeError(
            f"Cannot read {path}.",
            f"the file holds Reforge's audit runs and is not valid JSON: {exc}",
            f"restore {path.name}.bak or remove the file to start a fresh audit; no code was changed.",
        ) from exc
    if not isinstance(data, dict):
        raise ReforgeError(f"{path} is not a JSON object.", "it must hold the audit state.",
                           "restore it from its .bak shadow or a committed copy.")
    schema = data.get("schema")
    if schema == 1:
        return _migrate_v1(data)
    if schema != SCHEMA_VERSION:
        raise ReforgeError(
            f"{path} has an unsupported Reforge schema.",
            f"this Reforge reads schema {SCHEMA_VERSION} (and migrates schema 1) only.",
            "update Reforge, or restore the file from the project's git history.",
        )
    for key, default in (("next_run_id", 1), ("active_run", None), ("last_run", None),
                         ("runs", []), ("stage", 0), ("window", 0),
                         ("audited_commits", []), ("last_audit", None), ("history", [])):
        data.setdefault(key, default)
    if not isinstance(data["runs"], list) or not isinstance(data["audited_commits"], list) \
            or not isinstance(data["history"], list):
        raise ReforgeError(
            f"{path} is structurally invalid.",
            "'runs', 'audited_commits' and 'history' must be lists.",
            "restore the file from its .bak shadow or a committed copy.",
        )
    if not all(isinstance(run, dict) and isinstance(run.get("id"), str) for run in data["runs"]):
        raise ReforgeError(
            f"{path} is structurally invalid.",
            "every entry in 'runs' must be an object with a string 'id'.",
            "restore the file from its .bak shadow or a committed copy.",
        )
    for run in data["runs"]:
        stage = run.get("stage", 0)
        window = run.get("window", 0)
        if type(stage) is not int or type(window) is not int:
            raise ReforgeError(
                f"{path} is structurally invalid.",
                f"run {run.get('id')} has a non-integer stage/window.",
                "restore the file from its .bak shadow or a committed copy.",
            )
        for field in ("start", "step"):
            value = run.get(field)
            if value is not None and type(value) is not int:
                raise ReforgeError(
                    f"{path} is structurally invalid.",
                    f"run {run.get('id')} has a non-integer {field}.",
                    "restore the file from its .bak shadow or a committed copy.",
                )
        stop_value = run.get("stop")
        if stop_value is not None and type(stop_value) is not int:
            raise ReforgeError(
                f"{path} is structurally invalid.",
                f"run {run.get('id')} has a non-integer stop.",
                "restore the file from its .bak shadow or a committed copy.",
            )
        if not isinstance(run.get("history", []), list) or not isinstance(run.get("audited_commits", []), list):
            raise ReforgeError(
                f"{path} is structurally invalid.",
                f"run {run.get('id')} has a non-list history/audited_commits.",
                "restore the file from its .bak shadow or a committed copy.",
            )
        last = run.get("last_audit")
        if last is not None and not isinstance(last, dict):
            raise ReforgeError(
                f"{path} is structurally invalid.",
                f"run {run.get('id')} has a non-object last_audit.",
                "restore the file from its .bak shadow or a committed copy.",
            )
    return data


def save_state(root: Path, data: Dict[str, object]) -> None:
    """Persist through AIKit's atomic writer under its advisory lock.

    Reforge is an AIKit subsystem, so the locked writer is always available; a second,
    weaker fallback would serialize concurrent writers in only one environment and skip
    the `.bak` shadow that `load_state`'s recovery hint names (PRINCIPLE-013).
    """
    from scripts.disruption_recovery import atomic_write_json, file_lock

    path = state_path(root)
    with file_lock(path) as acquired:
        if not acquired:
            raise ReforgeError(
                f"Could not lock {path}.",
                "another Reforge process is writing the same audit state.",
                "retry in a moment; if no process is running, remove the stale .lock file.",
            )
        atomic_write_json(path, data)


def new_delivery(empty: bool = False) -> Dict[str, object]:
    """Per-window ship record; `pushed` is True only after `push()` returns 0.

    `commit` holds the full SHA for remote matching, `short` the display form from
    delivery. A post-push update dirties `.aikit/reforge.json` until the next window's
    commit carries it; resume reads the disk state so it still knows the window landed.
    """
    return {
        "commit": "",
        "short": "",
        "pushed": False,
        "push_error": None,
        "empty": bool(empty),
        "timestamp": _now(),
    }


def entry_from_stage(plan: StagePlan, findings: List[Finding], repairs: List[Repair],
                     tests: Optional[Dict[str, object]] = None,
                     gates: Optional[Dict[str, object]] = None,
                     skipped: Optional[List[str]] = None,
                     reviewed: int = 0,
                     review: Optional[Dict[str, object]] = None) -> Dict[str, object]:
    """One stage's durable record; `skipped` names binary files and `reviewed` counts the rest."""
    counts: Dict[str, int] = {}
    for finding in findings:
        counts[finding.category] = counts.get(finding.category, 0) + 1
    applied = sum(1 for repair in repairs if repair.applied)
    return {
        "run": plan.run_id,
        "stage": plan.stage,
        "window": plan.window,
        "commits": [commit.sha for commit in plan.commits],
        "new_commits": list(plan.new_shas),
        "prior_commits": list(plan.prior_shas),
        "findings": [finding.as_dict() for finding in findings],
        "repairs": [repair.as_dict() for repair in repairs],
        "counts": counts,
        "reviewed": int(reviewed),
        "review": review or {},
        "skipped": list(skipped or []),
        "tests": tests or {},
        "gates": gates or {},
        "delivery": new_delivery(empty=(applied == 0)),
        "timestamp": _now(),
    }


def _entry_applied(entry: Dict[str, object]) -> int:
    repairs = entry.get("repairs") or []
    return sum(1 for item in repairs
               if isinstance(item, dict) and item.get("applied"))


def _entry_verified(entry: Dict[str, object]) -> bool:
    """A stage that reached `record_stage` with passing gates; rollback already excluded failures."""
    if not isinstance(entry, dict):
        return False
    if _entry_applied(entry) == 0:
        return False
    tests = entry.get("tests") or {}
    if isinstance(tests, dict) and tests and not tests.get("passed"):
        return False
    gates = entry.get("gates") or {}
    if isinstance(gates, dict) and gates and not gates.get("passed"):
        return False
    return True


def _delivery_of(entry: Dict[str, object]) -> Dict[str, object]:
    delivery = entry.get("delivery")
    return delivery if isinstance(delivery, dict) else {}


def _stage_candidates(run: Dict[str, object]) -> List[Dict[str, object]]:
    """History plus last_audit deduplicated by stage; last_audit wins on collision."""
    by_stage: Dict[object, Dict[str, object]] = {}
    for entry in (run.get("history") or []):
        if isinstance(entry, dict) and entry.get("stage") is not None:
            by_stage[entry.get("stage")] = entry
    last = run.get("last_audit")
    if isinstance(last, dict) and last.get("stage") is not None:
        by_stage[last.get("stage")] = last
    return [by_stage[key] for key in sorted(by_stage, key=lambda s: int(s or 0))]


def find_unpushed_verified(run: Dict[str, object]) -> List[Dict[str, object]]:
    """Verified stages with applied repairs that were committed but never pushed.

    Empty windows never commit and verified-but-uncommitted windows have no SHA
    to push, so both are skipped: only a stage with a local commit SHA is pending.
    """
    pending: List[Dict[str, object]] = []
    for entry in _stage_candidates(run):
        if not _entry_verified(entry):
            continue
        delivery = _delivery_of(entry)
        if delivery.get("empty"):
            continue
        if delivery.get("pushed"):
            continue
        if not delivery.get("commit"):
            continue
        pending.append(entry)
    return pending


def find_uncommitted_verified(run: Dict[str, object]) -> List[Dict[str, object]]:
    """Verified stages with applied repairs that were never committed.

    Empty windows never commit by design, so they are skipped. A stage with a
    commit SHA (even unpushed) is committed, so only stages with no SHA and no
    empty mark are pending. Callers use this to refuse a new `--commit`/`--push`
    audit while an older window would otherwise orphan in the tree.
    """
    pending: List[Dict[str, object]] = []
    for entry in _stage_candidates(run):
        if not _entry_verified(entry):
            continue
        delivery = _delivery_of(entry)
        if delivery.get("empty"):
            continue
        if delivery.get("commit"):
            continue
        pending.append(entry)
    return pending


def mark_delivered(root: Path, state: Dict[str, object], run: Dict[str, object],
                   stage: int, delivery: Dict[str, object]) -> Dict[str, object]:
    """Record one stage's push hash in history and last_audit, then persist.

    Both copies are updated because a reloaded state holds two distinct objects;
    `sync_last_audit` covers the in-memory alias but not a prior `load_state`.
    """
    updated = dict(delivery)
    updated.setdefault("timestamp", _now())
    matches = [entry for entry in (run.get("history") or [])
               if isinstance(entry, dict) and entry.get("stage") == stage]
    last = run.get("last_audit")
    if isinstance(last, dict) and last.get("stage") == stage \
            and all(candidate is not last for candidate in matches):
        matches.append(last)
    for entry in matches:
        entry["delivery"] = dict(updated)
    run["updated"] = _now()
    _mirror(state, run)
    save_state(root, state)
    return run


def run_complete(run: Dict[str, object], window: int,
                 total_commits: Optional[int] = None) -> bool:
    stop = run.get("stop")
    if isinstance(stop, int):
        return window >= stop
    if total_commits is None:
        return False
    audited = run.get("audited_commits")
    audited_count = len(audited) if isinstance(audited, list) else 0
    return window >= total_commits or audited_count >= total_commits


def completion_total(run: Dict[str, object], live: Optional[int] = None) -> Optional[int]:
    """The repository commit count that closes an unlimited run: live first, then the stored one.

    A bounded run ignores both because `run_complete` answers from its stop.
    """
    if isinstance(live, int):
        return live
    stored = run.get("total_commits")
    return int(stored) if isinstance(stored, int) else None


def settle_run(run: Dict[str, object], state: Dict[str, object],
               total_commits: Optional[int] = None, *, reopen: bool = False) -> bool:
    """The one completed/active transition, shared by every entry point.

    A run settles as completed only when its window is done and every retained stage is reviewed.
    A review or settings change may also reopen a completed run that no longer meets that bar
    (`reopen=True`); recording a stage never does. Returns whether the status changed.
    """
    total = completion_total(run, total_commits)
    finished = run_complete(run, int(run.get("window") or 0), total) and review_is_ready(run)
    if finished and run.get("status") != "completed":
        run["status"] = "completed"
        run["updated"] = _now()
        if state.get("active_run") == run["id"]:
            state["active_run"] = None
        return True
    if reopen and not finished and run.get("status") == "completed":
        active = state.get("active_run")
        if active and active != run["id"]:
            other = _find_by_id(state, str(active))
            if other is not None and other.get("status") == "active":
                raise ReforgeError(
                    f"Cannot reopen audit run {run.get('id')} while {active} is active.",
                    "reopening would orphan the active run with status active.",
                    "stop or complete the active run first, or resume it explicitly.",
                )
        run["status"] = "active"
        run["updated"] = _now()
        state["active_run"] = run["id"]
        return True
    return False


def pending_reviews(run: Dict[str, object]) -> List[Dict[str, object]]:
    """Every retained stage whose review object explicitly says it is not reviewed.

    History is capped, so stages older than the retained window are not re-judged. A missing
    review object is a legacy stage and stays readable; an explicit ``unreviewed`` or ``partial``
    status blocks progress and completion.
    """
    entries: List[Dict[str, object]] = []
    seen = set()
    candidates = list(run.get("history") or [])
    last = run.get("last_audit")
    if isinstance(last, dict):
        candidates.append(last)
    for entry in candidates:
        if not isinstance(entry, dict):
            continue
        stage = entry.get("stage")
        if stage in seen:
            continue
        seen.add(stage)
        review = entry.get("review")
        if isinstance(review, dict) and review.get("status") not in (None, "", "reviewed"):
            entries.append(entry)
    return sorted(entries, key=lambda item: int(item.get("stage") or 0))


def review_is_ready(run: Dict[str, object]) -> bool:
    """True when every retained stage has no explicit pending review."""
    return not pending_reviews(run)


def finalize_review(root: Path, state: Dict[str, object],
                    run: Dict[str, object],
                    total_commits: Optional[int] = None) -> Dict[str, object]:
    """Settle the run after a review and persist its mirror in one write."""
    sync_last_audit(run)
    settle_run(run, state, total_commits)
    state["last_run"] = run["id"]
    _mirror(state, run)
    save_state(root, state)
    return run


def record_review(root: Path, state: Dict[str, object], run: Dict[str, object],
                  stage: int, review: Dict[str, object],
                  total_commits: Optional[int] = None) -> Dict[str, object]:
    """Attach a host review to one retained stage, then settle the run's status.

    A stage may be reviewed long after a later stage ran, which is how a completed run recovers
    from an unreviewed historical packet.
    """
    matches = [entry for entry in (run.get("history") or [])
               if isinstance(entry, dict) and entry.get("stage") == stage]
    last = run.get("last_audit")
    if isinstance(last, dict) and last.get("stage") == stage:
        matches.append(last)
    if not matches:
        raise ReforgeError(
            f"Audit run {run.get('id')} has no stage {stage} to review.",
            "only a stage still in the run's retained history can be reviewed.",
            "run `reforge report <project>` to list the stages that are available.",
            exit_code=2,
        )
    for entry in matches:
        entry["review"] = review
    run["updated"] = _now()
    settle_run(run, state, total_commits, reopen=True)
    state["last_run"] = run["id"]
    _mirror(state, run)
    save_state(root, state)
    return run


def record_stage(root: Path, state: Dict[str, object], run: Dict[str, object],
                 entry: Dict[str, object],
                 total_commits: Optional[int] = None) -> Dict[str, object]:
    """Advance one run, remember its audited SHAs, and settle it when the window is done."""
    run["stage"] = entry["stage"]
    run["window"] = entry["window"]
    audited = list(run.get("audited_commits") or [])
    known = set(audited)
    audited.extend(sha for sha in entry["new_commits"] if sha not in known)
    run["audited_commits"] = audited
    if total_commits is not None:
        run["total_commits"] = int(total_commits)
    run["last_audit"] = entry
    history = list(run.get("history") or [])
    history.append(entry)
    run["history"] = history[-MAX_HISTORY:]
    run["updated"] = _now()
    settle_run(run, state, total_commits)
    state["last_run"] = run["id"]
    _mirror(state, run)
    save_state(root, state)
    return state


def mark_repairs(root: Path, state: Dict[str, object], run: Dict[str, object],
                 repairs: List[Repair]) -> Dict[str, object]:
    """Mark repaired findings in the run's last audit so `fix` is idempotent."""
    keys = {(repair.code, repair.path, repair.line) for repair in repairs if repair.applied}
    last = run.get("last_audit")
    if isinstance(last, dict):
        for item in last.get("findings") or []:
            if (item.get("code"), item.get("path"), item.get("line")) in keys:
                item["repaired"] = True
    _mirror(state, run)
    save_state(root, state)
    return state


def unrepaired_findings(run: Dict[str, object]) -> List[Dict[str, object]]:
    last = run.get("last_audit")
    if not isinstance(last, dict):
        return []
    return [item for item in last.get("findings") or [] if not item.get("repaired")]


def pending_fixable(run: Dict[str, object]) -> List[Dict[str, object]]:
    """Findings an agent still has to repair before another stage may start."""
    return [item for item in unrepaired_findings(run) if item.get("fixable")]


def stop_run(root: Path, state: Dict[str, object], run: Dict[str, object]) -> Dict[str, object]:
    if run.get("status") == "completed":
        raise ReforgeError(
            f"Audit run {run['id']} already completed at its stop.",
            "a completed run has no active review left to stop.",
            "start a new audit run with `reforge start`.",
        )
    run["status"] = "stopped"
    run["updated"] = _now()
    if state.get("active_run") == run["id"]:
        state["active_run"] = None
    state["last_run"] = run["id"]
    _mirror(state, run)
    save_state(root, state)
    return run


def resume_run(root: Path, state: Dict[str, object], run: Dict[str, object]) -> Dict[str, object]:
    if run.get("status") != "stopped":
        raise ReforgeError(
            f"Audit run {run['id']} is {run.get('status')}, not stopped.",
            "only a stopped run can be resumed without changing its history.",
            "use `reforge runs` to pick a stopped run, or `reforge start` for a new one.",
        )
    active = state.get("active_run")
    if active and active != run["id"]:
        other = _find_by_id(state, str(active))
        if other is not None and other.get("status") == "active":
            raise ReforgeError(
                f"Cannot resume audit run {run.get('id')} while {active} is active.",
                "resuming would orphan the active run with status active.",
                "stop the active run first, then resume.",
            )
    run["status"] = "active"
    run["updated"] = _now()
    state["active_run"] = run["id"]
    state["last_run"] = run["id"]
    _mirror(state, run)
    save_state(root, state)
    return run


def update_settings(root: Path, state: Dict[str, object], run: Dict[str, object],
                    start: Optional[int] = None, step: Optional[int] = None,
                    stop: object = _UNSET) -> Dict[str, object]:
    """Change a run's step/stop; start may change only before its first stage.

    Step stays mutable: plan_next_stage derives the next window from the current
    stage plus start/step and de-duplicates via audited_commits, so raising step
    is the documented recovery for a "no new commits" window (audit.py). Guarding
    step would strand that path and contradict the CLI contract.
    """
    for label, value in (("start", start), ("step", step)):
        if value is not None and isinstance(value, (bool, float)):
            raise ReforgeError(
                "The run's window settings are not integers.",
                f"could not parse {label}: {value!r}.",
                "restore .aikit/reforge.json from its .bak shadow or start a new run.",
                exit_code=2,
            )
    if stop is not _UNSET and stop is not None and isinstance(stop, bool):
        raise ReforgeError(
            "The run's window settings are not integers.",
            f"could not parse stop: {stop!r}.",
            "pass --stop 0 for unlimited or a positive integer.",
            exit_code=2,
        )
    try:
        new_start = int(run.get("start") or DEFAULT_START) if start is None else int(start)
        new_step = int(run.get("step") or DEFAULT_STEP) if step is None else int(step)
    except (TypeError, ValueError) as exc:
        raise ReforgeError(
            "The run's window settings are not integers.",
            f"could not parse start/step: {exc}.",
            "restore .aikit/reforge.json from its .bak shadow or start a new run.",
            exit_code=2,
        ) from exc
    if stop is _UNSET:
        new_stop = run.get("stop")
    elif stop is None or (type(stop) is int and stop == 0) or (type(stop) is str and stop == "0"):
        new_stop = None
    elif isinstance(stop, (bool, float)):
        raise ReforgeError(
            "The run's window settings are not integers.",
            f"could not parse stop: {stop!r}.",
            "pass --stop 0 for unlimited or a positive integer.",
            exit_code=2,
        )
    else:
        try:
            new_stop = int(stop)  # type: ignore[arg-type]
        except (TypeError, ValueError) as exc:
            raise ReforgeError(
                "The run's window settings are not integers.",
                f"could not parse stop: {exc}.",
                "pass --stop 0 for unlimited or a positive integer.",
                exit_code=2,
            ) from exc
    validate_settings(new_start, new_step, new_stop)  # type: ignore[arg-type]
    # Fail closed on a corrupt stage: an unknown stage type blocks a start
    # change rather than silently allowing the window to shift mid-run.
    try:
        _stage_num = int(run.get("stage") or 0)
    except (TypeError, ValueError):
        _stage_num = 1
    if start is not None and new_start != run.get("start") and _stage_num > 0:
        raise ReforgeError(
            "The start window cannot change after a run has audited a stage.",
            "earlier stages keep the window they actually used, so the progression would be ambiguous.",
            "leave --start unchanged, or start a new audit run with the new start.",
            exit_code=2,
        )
    run["start"] = new_start
    run["step"] = new_step
    run["stop"] = new_stop
    run["updated"] = _now()
    if run.get("status") in ("active", "completed"):
        settle_run(run, state, reopen=True)
    _mirror(state, run)
    save_state(root, state)
    return run


def run_summary(run: Dict[str, object]) -> Dict[str, object]:
    last = run.get("last_audit") if isinstance(run.get("last_audit"), dict) else None
    last_delivery = _delivery_of(last) if isinstance(last, dict) else {}
    return {
        "id": run.get("id"),
        "status": run.get("status"),
        "start": run.get("start"),
        "step": run.get("step"),
        "stop": run.get("stop"),
        "stage": run.get("stage"),
        "window": run.get("window"),
        "audited_commits": len(run.get("audited_commits") or []),
        "pending_fixable": len(pending_fixable(run)),
        "unreviewed_stages": [int(entry.get("stage") or 0) for entry in pending_reviews(run)],
        "unpushed_stages": [int(entry.get("stage") or 0)
                            for entry in find_unpushed_verified(run)],
        "uncommitted_stages": [int(entry.get("stage") or 0)
                               for entry in find_uncommitted_verified(run)],
        "last_audit": ({
            "stage": last.get("stage"),
            "window": last.get("window"),
            "counts": last.get("counts") or {},
            "review": (last.get("review") or last.get("ai") or {}).get("status") or "",
            "new_commits": len(last.get("new_commits") or []),
            "skipped": len(last.get("skipped") or []),
            "delivery": {
                "commit": last_delivery.get("commit") or "",
                "short": last_delivery.get("short") or "",
                "pushed": bool(last_delivery.get("pushed")),
                "empty": bool(last_delivery.get("empty")),
            },
            "timestamp": last.get("timestamp"),
        } if last else None),
        "created": run.get("created"),
        "updated": run.get("updated"),
    }


def runs_summary(state: Dict[str, object]) -> List[Dict[str, object]]:
    return [run_summary(run) for run in state.get("runs") or []]
