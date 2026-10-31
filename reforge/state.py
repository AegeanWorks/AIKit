"""Persistent audit runs, written atomically and isolated per project."""

import json
import os
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
    return data


def _local_atomic_write(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(path.suffix + f".tmp_{os.getpid()}_{int(time.time() * 1000)}")
    try:
        with open(tmp, "w", encoding="utf-8") as handle:
            handle.write(text)
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(tmp, path)
    finally:
        if tmp.exists():
            try:
                tmp.unlink()
            except OSError:  # hygiene: allow temp cleanup cannot fail the completed write
                pass


def save_state(root: Path, data: Dict[str, object]) -> None:
    """Persist through AIKit's atomic writer and lock when available, else a portable fallback."""
    path = state_path(root)
    text = json.dumps(data, indent=2)
    try:
        from scripts.disruption_recovery import atomic_write_json, file_lock
    except ImportError:
        _local_atomic_write(path, text)
        return
    with file_lock(path) as acquired:
        if not acquired:
            raise ReforgeError(
                f"Could not lock {path}.",
                "another Reforge process is writing the same audit state.",
                "retry in a moment; if no process is running, remove the stale .lock file.",
            )
        atomic_write_json(path, data)


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
        "timestamp": _now(),
    }


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
    finished = run_complete(run, int(run.get("window") or 0), total_commits) and review_is_ready(run)
    if finished and run.get("status") != "completed":
        run["status"] = "completed"
        run["updated"] = _now()
        if state.get("active_run") == run["id"]:
            state["active_run"] = None
        return True
    if reopen and not finished and run.get("status") == "completed":
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
    """Change a run's step/stop; start may change only before its first stage."""
    new_start = int(run.get("start") or DEFAULT_START) if start is None else int(start)
    new_step = int(run.get("step") or DEFAULT_STEP) if step is None else int(step)
    new_stop = run.get("stop") if stop is _UNSET else stop
    validate_settings(new_start, new_step, new_stop)  # type: ignore[arg-type]
    if new_start != run.get("start") and int(run.get("stage") or 0) > 0:
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
        "last_audit": ({
            "stage": last.get("stage"),
            "window": last.get("window"),
            "counts": last.get("counts") or {},
            "review": (last.get("review") or last.get("ai") or {}).get("status") or "",
            "new_commits": len(last.get("new_commits") or []),
            "skipped": len(last.get("skipped") or []),
            "timestamp": last.get("timestamp"),
        } if last else None),
        "created": run.get("created"),
        "updated": run.get("updated"),
    }


def runs_summary(state: Dict[str, object]) -> List[Dict[str, object]]:
    return [run_summary(run) for run in state.get("runs") or []]
