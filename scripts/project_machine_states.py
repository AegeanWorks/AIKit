"""Read the project-level machine states that `status` can derive (P11, ADR-401).

Seven of the registry's 21 machines are readable from a project's own state without
running a gate or scanning a Git history: project-lifecycle, license, ui-identity,
media-asset, ui-task, task-lifecycle and ledger-generation. The other fourteen live in
Reforge runs, the Idea Catcher register, delegation transcripts, upstream checks,
compat proofs or proof artifacts; a cold-start status call must not go looking for
them.

So this module reports the seven it read, and names the fourteen it did not, rather
than implying a complete snapshot. A machine whose read fails is reported with its
reason instead of being silently dropped or given a state outside its declared
vocabulary.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Dict, Mapping

from scripts import state_machines
from scripts.project_archive import is_archived
from scripts.project_license import license_state
from scripts.project_media import load_media, media_path
from scripts.project_registry import Project, config_path, load_config
from scripts.ui_contract import TASK_REL

READ_MACHINES = (
    "project-lifecycle",
    "license",
    "ui-identity",
    "media-asset",
    "ui-task",
    "task-lifecycle",
    "ledger-generation",
)


def _project_lifecycle(project: Project) -> str:
    path = Path(project.path)
    if not path.is_dir():
        return "missing"
    if is_archived(path):
        return "archived"
    return "attached" if project.attached else "local"


def _license(project: Project) -> str:
    tier = license_state(Path(project.path)).tier
    return tier if tier in state_machines.BY_NAME["license"].states else "unrecorded"


def _ui_identity(project: Project) -> str:
    """A config read, not a filesystem scan: `status` must stay a cold-start report."""
    path = config_path(Path(project.path))
    if not path.is_file():
        return "unknown"
    config = load_config(Path(project.path))
    if str(config.get("ui_source") or "") == "manual":
        return "manual"
    if config.get("ui_required") is True:
        return "required"
    if "has_ui" in config:
        return "detected"
    return "unknown"


def _media_asset(project: Project) -> str:
    """One state for the manifest: the least-reviewed asset decides it."""
    if not media_path(Path(project.path)).is_file():
        return "absent"
    data = load_media(Path(project.path))
    statuses = [str(entry.get("status") or "") for entry in (data.get("assets") or {}).values()
                if isinstance(entry, dict)]
    statuses += [str(shot.get("status") or "") for shot in (data.get("screenshots") or [])
                 if isinstance(shot, dict)]
    if not statuses:
        return "absent"
    if "rejected" in statuses:
        return "rejected"
    if "pending_review" in statuses:
        return "pending"
    if all(status == "approved" for status in statuses):
        return "approved"
    return "pending"


def _ui_task(project: Project) -> str:
    path = Path(project.path) / TASK_REL
    if not path.is_file():
        return "none"
    try:
        record = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        raise _Unreadable("the task record is not valid JSON")
    if not isinstance(record, dict):
        raise _Unreadable("the task record is not a JSON object")
    return "verified" if record.get("verified_at") else "open"


class _Unreadable(Exception):
    """A state file exists but cannot be read into a declared state."""


def _task_lifecycle(audit: Mapping[str, object]) -> str:
    """`missing` means no active task, which is the state a fresh project is in."""
    for key, state in (("interrupted_task", "in_progress"), ("suspended_task", "suspended")):
        if audit.get(key):
            return state
    return "missing"


def _ledger_generation(audit: Mapping[str, object], ledger_exists: bool) -> str:
    if audit.get("ledger_error"):
        return "newer"
    if audit.get("quarantined_files"):
        return "quarantined"
    return "valid" if ledger_exists else "missing"


def project_states(project: Project, audit: Mapping[str, object],
                   ledger_exists: bool) -> Dict[str, object]:
    """Each readable machine's live state, plus the ones this report did not sample.

    `ledger_exists` is passed rather than inferred from `audit`, because the audit
    reports recovery facts, not the ledger's presence; guessing a key it never sets
    is how an inventory starts lying.
    """
    readers = {
        "project-lifecycle": lambda: _project_lifecycle(project),
        "license": lambda: _license(project),
        "ui-identity": lambda: _ui_identity(project),
        "media-asset": lambda: _media_asset(project),
        "ui-task": lambda: _ui_task(project),
        "task-lifecycle": lambda: _task_lifecycle(audit),
        "ledger-generation": lambda: _ledger_generation(audit, ledger_exists),
    }
    states: Dict[str, str] = {}
    errors: Dict[str, str] = {}
    for name in READ_MACHINES:
        try:
            states[name] = readers[name]()
        except _Unreadable as exc:
            errors[name] = str(exc)
        except Exception as exc:  # a status report must never end in a traceback
            errors[name] = f"{type(exc).__name__}: {exc}"
    missing = sorted(machine.name for machine in state_machines.MACHINES
                     if machine.name not in states)
    return {
        "states": states,
        "errors": errors,
        "not_sampled": missing,
        "read_count": len(states),
        "registry_count": len(state_machines.MACHINES),
    }
