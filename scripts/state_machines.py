#!/usr/bin/env python3
"""
Explicit state-machine registry for AIKit (PRINCIPLE-009, PRINCIPLE-016).

The application encodes many lifecycle states in JSON fields, strings and files.
This module makes those machines readable in one place: states, allowed
transitions, the code that persists them, and the gaps a reader should know.
It is deliberately data-only: importing it changes nothing, and `--list`,
`--json`, `--machine`, `--from/--to` and `--check-status` never write.

Universal CLI contract (PRINCIPLE-011): `--help` exits 0 and writes nothing;
exit 0 success, 1 a refused transition or unknown status, 2 misuse.
"""

from __future__ import annotations

import argparse
import json
import sys
from dataclasses import dataclass
from typing import Dict, Mapping, Optional, Sequence, Tuple


@dataclass(frozen=True)
class Machine:
    """One lifecycle as data: states, intended transitions, and its live source."""

    name: str
    purpose: str
    states: Tuple[str, ...]
    transitions: Mapping[str, Tuple[str, ...]]
    source: str
    gap: str = ""

    def allows(self, source: str, target: str) -> bool:
        return target in self.transitions.get(source, ())


MACHINES: Tuple[Machine, ...] = (
    Machine(
        name="task-lifecycle",
        purpose="The AIKit task a session is working on, and whether it is live or closed.",
        states=("missing", "in_progress", "suspended", "completed", "abandoned", "superseded"),
        transitions={
            "missing": ("in_progress",),
            "in_progress": ("in_progress", "suspended", "completed", "abandoned", "superseded"),
            "suspended": ("in_progress", "abandoned", "superseded"),
            "completed": ("completed", "superseded"),
            "abandoned": (),
            "superseded": ("in_progress", "abandoned"),
        },
        source="scripts/disruption_recovery.py: record_checkpoint, mark_task_completed, "
               "suspend_active_task, reset_active_task, resume_task; .agents/task_ledger.json",
        gap="record_checkpoint could reopen a completed task through the same id, and --audit "
            "did not print a suspended task (fixed in ADR-388).",
    ),
    Machine(
        name="ledger-generation",
        purpose="Which generation of the task ledger is readable, and how a damaged one recovers.",
        states=("missing", "legacy", "valid", "corrupt", "quarantined", "newer"),
        transitions={
            "missing": ("valid", "legacy"),
            "legacy": ("valid",),
            "valid": ("valid", "corrupt", "newer"),
            "corrupt": ("quarantined", "missing"),
            "quarantined": ("missing",),
            "newer": ("newer",),
        },
        source="scripts/disruption_recovery.py: load_ledger, save_ledger, "
               "UnsupportedLedgerVersion, _quarantine_ledger",
        gap="load_ledger is documented as read-only but quarantines on read; --audit creates "
            "the memory directory when the ledger is absent.",
    ),
    Machine(
        name="reforge-run",
        purpose="One independent Reforge audit run over a Git history.",
        states=("none", "active", "stopped", "completed"),
        transitions={
            "none": ("active",),
            "active": ("active", "stopped", "completed"),
            "stopped": ("active", "completed"),
            "completed": ("completed", "active"),
        },
        source="reforge/state.py: create_run, stop_run, resume_run, settle_run; "
               ".aikit/reforge.json run.status",
        gap="completed -> stopped is refused with no clear status output; an unknown status "
            "string is treated as advanceable.",
    ),
    Machine(
        name="reforge-review",
        purpose="Whether the host actually reviewed every hunk of a stage.",
        states=("none", "unreviewed", "partial", "reviewed"),
        transitions={
            "none": ("unreviewed", "reviewed"),
            "unreviewed": ("partial", "reviewed"),
            "partial": ("partial", "reviewed"),
            "reviewed": ("reviewed",),
        },
        source="reforge/pipeline.py: _collect_review, review_stage; reforge/state.py: "
               "review_is_ready; reforge.json entry.review.status",
        gap="review refuses a partial answer while fix accepts and persists one; a review of a "
            "stage older than MAX_HISTORY stops blocking completion.",
    ),
    Machine(
        name="reforge-delivery",
        purpose="The per-window ship record: empty, committed locally, or pushed.",
        states=("absent", "empty", "uncommitted", "commit_failed", "unpushed", "pushed"),
        transitions={
            "absent": ("empty", "uncommitted"),
            "empty": ("empty",),
            "uncommitted": ("empty", "unpushed", "pushed", "commit_failed"),
            "commit_failed": ("uncommitted",),
            "unpushed": ("pushed",),
            "pushed": ("pushed",),
        },
        source="reforge/pipeline.py: _close_window, _publish_backlog; reforge/state.py: "
               "new_delivery, mark_delivered; reforge.json entry.delivery",
        gap="A crash between git commit and mark_delivered leaves a commit on disk with no "
            "recorded SHA; no command reconciles that state.",
    ),
    Machine(
        name="idea-status",
        purpose="What is happening to an Idea Catcher idea; Blocked and Superseded are terminal.",
        states=("Proposed", "Approved", "Integrating", "Integrated", "Deferred",
                "Blocked", "Rejected", "Superseded"),
        transitions={
            "Proposed": ("Approved", "Integrating", "Integrated", "Deferred", "Rejected",
                         "Superseded", "Blocked"),
            "Approved": ("Approved", "Integrating", "Integrated", "Deferred", "Rejected",
                         "Superseded", "Blocked"),
            "Integrating": ("Integrating", "Integrated", "Deferred", "Rejected",
                            "Superseded", "Blocked"),
            "Integrated": ("Integrated", "Deferred", "Rejected", "Superseded", "Blocked"),
            "Deferred": ("Deferred", "Blocked", "Approved", "Integrating", "Integrated",
                         "Rejected", "Superseded"),
            "Blocked": ("Blocked",),
            "Rejected": ("Rejected", "Proposed"),
            "Superseded": ("Superseded",),
        },
        source="idea_catcher/registry.py: STATUS_SPECS, _apply_status, review_idea; "
               ".idea-catcher/ideas.json status",
        gap="validate_ideas has no transition table, so a hand-edited register can reopen a "
            "terminal row; the second deferral is derived from three records with max().",
    ),
    Machine(
        name="idea-repo-review",
        purpose="The lease ledger for repository reviews; a stale active lease is derived.",
        states=("idle", "active", "stale", "finished", "abandoned"),
        transitions={
            "idle": ("active",),
            "active": ("finished", "abandoned", "stale"),
            "stale": ("active", "finished", "abandoned"),
            "finished": (),
            "abandoned": (),
        },
        source="idea_catcher/registry.py: review_start, review_finish, review_abandon, "
               "release_expired, review_rows; .idea-catcher/reviews.json",
        gap="Lease expiry is lazy; MATRIX.md can advertise an expired lease as active, and the "
            "whole ledger machine has no tests.",
    ),
    Machine(
        name="project-lifecycle",
        purpose="How a project enters, leaves, and is discovered by the AIKit registry.",
        states=("unregistered", "local", "attached", "missing", "archived"),
        transitions={
            "unregistered": ("local", "attached"),
            "local": ("local", "missing", "archived"),
            "attached": ("attached", "missing", "archived"),
            "missing": ("local", "attached"),
            "archived": (),
        },
        source="scripts/project_registry.py: create_project, attach_project, _build_project; "
               "scripts/project_archive.py: archive_project; .aikit/project.json",
        gap="No detach or unarchive transition exists; publish and check never refuse an "
            "archived project.",
    ),
    Machine(
        name="license",
        purpose="The project license tier; personal kind lives in the LICENSE header.",
        states=("unrecorded", "personal", "restricted"),
        transitions={
            "unrecorded": ("personal", "restricted"),
            "personal": ("personal", "restricted"),
            "restricted": ("restricted",),
        },
        source="scripts/project_license.py: apply_license_kind, restrict_project; "
               ".aikit/project.json license, LICENSE header",
        gap="A crash between the LICENSE write and the config record reads as unrecorded, and "
            "a half-restricted project can be relicensed and published.",
    ),
    Machine(
        name="ui-identity",
        purpose="Whether a project has a screenshotable UI, and whether that is manual.",
        states=("unknown", "detected", "manual", "required"),
        transitions={
            "unknown": ("detected", "manual"),
            "detected": ("detected", "manual", "required"),
            "manual": ("manual", "detected", "required"),
            "required": ("required", "manual"),
        },
        source="scripts/project_ui.py: detect_ui, auto_ui, set_ui_manual, "
               "refresh_ui_identifier; .aikit/project.json has_ui/ui_source/ui_required",
        gap="fix, media init, new and attach call auto_ui and discard a manual identity; "
            "ui_required is one-way (pinned by tests/test_kit.py:11482).",
    ),
    Machine(
        name="gate-result",
        purpose="The outcome vocabulary of one project gate run.",
        states=("not_run", "pass", "fail", "refused", "rewrite"),
        transitions={
            "not_run": ("pass", "fail", "refused", "rewrite"),
            "pass": ("pass",),
            "fail": ("fail", "pass"),
            "refused": ("refused", "pass"),
            "rewrite": ("rewrite", "pass"),
        },
        source="scripts/project_gates.py: run_gate, resolve_gates; scripts/aikit_cli.py: "
               "cmd_check, cmd_publish",
        gap="Timeout and start failure both report returncode -1; the compat gate disappears "
            "when .aikit/compat.json is deleted.",
    ),
    Machine(
        name="media-asset",
        purpose="Review state of a generated logo, social preview or screenshot.",
        states=("absent", "pending", "approved", "rejected"),
        transitions={
            "absent": ("pending",),
            "pending": ("pending", "approved", "rejected"),
            "approved": ("approved", "rejected"),
            "rejected": ("rejected", "pending"),
        },
        source="scripts/project_media.py: _asset, review_asset, apply_assets; .aikit/media.json",
        gap="Only logo and social preview block publish; an unreviewed screenshot publishes.",
    ),
)

BY_NAME: Dict[str, Machine] = {machine.name: machine for machine in MACHINES}


def as_dict() -> Dict[str, object]:
    """A deterministic JSON-ready view; useful to agents and documentation tests."""
    return {
        "schema": 1,
        "machines": [
            {
                "name": machine.name,
                "purpose": machine.purpose,
                "states": list(machine.states),
                "transitions": {state: list(targets) for state, targets in machine.transitions.items()},
                "source": machine.source,
                "gap": machine.gap,
            }
            for machine in MACHINES
        ],
    }


def run_transition(machine: Machine, source: str, target: str) -> int:
    if source not in machine.states:
        print(f"Why: '{source}' is not a state of {machine.name}.", file=sys.stderr)
        print(f"Fix: choose one of {', '.join(machine.states)}.", file=sys.stderr)
        return 2
    if target not in machine.states:
        print(f"Why: '{target}' is not a state of {machine.name}.", file=sys.stderr)
        print(f"Fix: choose one of {', '.join(machine.states)}.", file=sys.stderr)
        return 2
    if machine.allows(source, target):
        print(f"allowed: {machine.name}: {source} -> {target}")
        return 0
    print(f"refused: {machine.name}: {source} -> {target}")
    print(f"Why: the {machine.name} machine has no such transition.", file=sys.stderr)
    print(f"Fix: from '{source}' use one of {', '.join(machine.transitions.get(source, ())) or 'none'}.",
          file=sys.stderr)
    return 1


def print_machine(machine: Machine) -> None:
    print(f"{machine.name} - {machine.purpose}")
    print(f"Source: {machine.source}")
    print("States:")
    for state in machine.states:
        targets = machine.transitions.get(state, ())
        print(f"  {state} -> {', '.join(targets) if targets else '(terminal)'}")
    if machine.gap:
        print(f"Known gap: {machine.gap}")


def main(argv: Optional[Sequence[str]] = None) -> int:
    parser = argparse.ArgumentParser(
        description="Inspect AIKit's implicit state machines as explicit data (read-only).")
    parser.add_argument("--list", action="store_true", help="list machines (default)")
    parser.add_argument("--json", action="store_true", help="print the full registry as JSON")
    parser.add_argument("--machine", help="show one machine by name")
    parser.add_argument("--from", dest="source", help="transition source state")
    parser.add_argument("--to", dest="target", help="transition target state")
    parser.add_argument("--check-status", dest="status", help="check whether a state is known")
    args = parser.parse_args(argv)

    if args.source is not None or args.target is not None:
        if not (args.machine and args.source is not None and args.target is not None):
            parser.error("--from and --to require --machine")
        machine = BY_NAME.get(args.machine)
        if machine is None:
            parser.error(f"unknown machine '{args.machine}'")
        return run_transition(machine, args.source, args.target)

    if args.status is not None:
        if not args.machine:
            parser.error("--check-status requires --machine")
        machine = BY_NAME.get(args.machine)
        if machine is None:
            parser.error(f"unknown machine '{args.machine}'")
        if args.status in machine.states:
            print(f"known: {machine.name}: {args.status}")
            return 0
        print(f"unknown: {machine.name}: {args.status}", file=sys.stderr)
        print(f"Fix: choose one of {', '.join(machine.states)}.", file=sys.stderr)
        return 1

    if args.machine:
        machine = BY_NAME.get(args.machine)
        if machine is None:
            print(f"Why: unknown machine '{args.machine}'.", file=sys.stderr)
            print(f"Fix: choose one of {', '.join(BY_NAME)}.", file=sys.stderr)
            return 2
        print_machine(machine)
        return 0

    if args.json:
        print(json.dumps(as_dict(), indent=2))
        return 0

    print(f"{len(MACHINES)} explicit state machines (read-only):")
    for machine in MACHINES:
        print(f"  {machine.name:<20} {len(machine.states):>2} states  {machine.purpose}")
    print("Use --machine <name>, --json, or --machine <name> --from <state> --to <state>.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
