"""
Record Reforge progress in the audited repository's AIKit task ledger.

Reforge keeps its own durable audit state (`.aikit/reforge.json`), but that file is invisible to
the agent workflow: a session that is interrupted mid-audit, or a fresh agent doing a cold start,
reads `.agents/task_ledger.json` or `<project>/.aikit/task_ledger.json` and nothing else. This
module appends one checkpoint per run lifecycle event under a dedicated `reforge:<run-id>` task, so
`disruption_recovery.py --resume` shows the audit in progress, a stopped run appears as resumable,
and a completed run disappears from the paused list.

It never becomes the active task: `record_checkpoint` would supersede whatever the operator is
working on, so the entry is appended under the ledger's own lock with `active_task` untouched. A
repository without a ledger (any plain checkout, and the `reforge.py` entry point on arbitrary
repos) is simply left alone and the caller reports that nothing was recorded.
"""

import time
from pathlib import Path
from typing import Dict, List, Optional, Sequence

LEDGER_TASK_PREFIX = "reforge:"
# Phase 3 (implementation) is where a repair actually mutates the tree (PRINCIPLE-002 lifecycle).
LEDGER_PHASE_NUM = 3
DESCRIPTION_LIMIT = 240


def ledger_path(root: Path) -> Optional[Path]:
    """The ledger `root` already has, or None; Reforge never creates one for a foreign repository.

    AIKit keeps its ledger in `.agents/task_ledger.json`, a project keeps its in
    `.aikit/task_ledger.json`. Reforge's own state lives in `.aikit/reforge.json`, so the
    presence of `.aikit/` says nothing about which ledger a repository uses: ask for each
    candidate by name and take the one that exists.
    """
    root = Path(root)
    try:
        from scripts.disruption_recovery import workspace_ledger_path
    except ImportError:
        return None
    candidates = [workspace_ledger_path(root),
                  root / ".aikit" / "task_ledger.json",
                  root / ".agents" / "task_ledger.json"]
    for path in candidates:
        if path.is_file():
            return path
    return None


def ledger_relative(root: Path) -> Optional[str]:
    """The ledger's repo-relative path when it exists, for the queue of paths Reforge may dirty."""
    path = ledger_path(root)
    if path is None:
        return None
    try:
        return str(path.relative_to(Path(root))).replace("\\", "/")
    except ValueError:  # hygiene: allow a ledger can only sit under the audited root
        return None


def ledger_artifacts(root: Path) -> List[str]:
    """The ledger plus the `.bak` and `.lock` siblings AIKit's atomic writer leaves beside it."""
    relative = ledger_relative(root)
    if not relative:
        return []
    return [relative, f"{relative}.bak", f"{relative}.lock"]


def _describe(stage: int, description: str) -> str:
    text = " ".join(str(description).split())
    if len(text) > DESCRIPTION_LIMIT:
        text = text[:DESCRIPTION_LIMIT - 1].rstrip() + "…"
    return f"Reforge stage {stage}: {text}" if stage else text


def record_event(root: Path, run_id: str, stage: int, description: str,
                 files: Sequence[str] = (), status: str = "in_progress",
                 agent: Optional[str] = None) -> Dict[str, object]:
    """Append one checkpoint for `run_id`; returns what happened instead of raising.

    A ledger that is locked, corrupt or written by a newer schema must never abort an audit that
    already changed the working tree, so the failure is returned and the caller prints it.
    """
    task_id = f"{LEDGER_TASK_PREFIX}{run_id}"
    result: Dict[str, object] = {"task_id": task_id, "path": None, "recorded": False}
    path = ledger_path(root)
    if path is None:
        result["reason"] = "no AIKit task ledger in this repository"
        return result
    result["path"] = str(path)
    try:
        from scripts.disruption_recovery import locked_ledger, resolve_agent
    except ImportError as exc:
        result["reason"] = f"AIKit's ledger module is unavailable: {exc}"
        return result
    entry = {
        "task_id": task_id,
        "phase": f"reforge stage {stage}" if stage else "reforge run",
        "phase_num": LEDGER_PHASE_NUM,
        "description": _describe(stage, description),
        "files_affected": [str(item).replace("\\", "/") for item in files][:20],
        "status": status,
        "timestamp": time.time(),
        "timestamp_str": time.strftime("%Y-%m-%d %H:%M:%S", time.localtime()),
        "agent": agent or resolve_agent(),
    }
    try:
        with locked_ledger(path) as ledger:
            # Appended, never assigned to `active_task`: the operator's task must survive an audit.
            ledger.setdefault("checkpoints", []).append(entry)
    except (TimeoutError, OSError, ValueError, KeyError, TypeError) as exc:
        result["reason"] = f"{type(exc).__name__}: {exc}"
        return result
    result["recorded"] = True
    result["status"] = status
    return result


def stage_files(findings: Sequence[object], skipped: Sequence[str]) -> List[str]:
    """Paths a stage touched or could not read: the ledger's `files_affected` for that entry."""
    paths: List[str] = []
    for finding in findings:
        path = str(getattr(finding, "path", "") or "")
        if path and path not in paths:
            paths.append(path)
    for path in skipped:
        if path not in paths:
            paths.append(path)
    return paths
