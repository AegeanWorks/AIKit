"""The Reforge command grammar, shared by `python -m reforge` and `aikit.py reforge`."""

import argparse
import json
import sys
from pathlib import Path
from typing import Callable, Dict, List, Optional, Sequence, Tuple

from reforge.errors import ReforgeError

GateRunner = Callable[[], Tuple[bool, Sequence[str]]]


def _add_run_selection(command) -> None:
    command.add_argument("--run", dest="run_id", metavar="ID",
                         help="audit run id (default: active run, else the latest)")


def _add_window_settings(command, defaults: bool) -> None:
    command.add_argument("--start", type=int, default=3 if defaults else None,
                         help="first window size, at least 2 (default 3)")
    command.add_argument("--step", type=int, default=3 if defaults else None,
                         help="commits added per stage, at least 1 (default 3)")
    command.add_argument("--stop", type=int, default=None,
                         help="stop after this window size; 0 means unlimited")


def _add_review_options(command, findings: bool = False, rules: bool = True) -> None:
    if rules:
        command.add_argument("--rules", dest="rules", action="store_true", default=True,
                             help="run the cheap deterministic rule pre-pass (default: on)")
        command.add_argument("--no-rules", dest="rules", action="store_false",
                             help="skip the deterministic rule pre-pass")
    if findings:
        command.add_argument("--findings", metavar="FILE",
                             help="apply the reviewer's JSON answer to the stage's changed files")


def add_commands(subparsers) -> None:
    """Declare every Reforge command once, for either top-level CLI."""
    audit = subparsers.add_parser("audit", help="plan the next window and write its review packet")
    audit.add_argument("target", help="registered project name or repository path")
    audit.add_argument("--json", action="store_true", help="print one machine-readable result")
    audit.add_argument("--run", dest="run_id", metavar="ID",
                       help="audit run id (default: active run, else a new run)")
    _add_window_settings(audit, defaults=False)
    _add_review_options(audit)

    for name, text in (("fix", "apply a reviewer's findings to the active run's last audit"),
                       ("run", "audit the next window, then apply its findings")):
        command = subparsers.add_parser(name, help=text)
        command.add_argument("target", help="registered project name or repository path")
        command.add_argument("--json", action="store_true", help="print one machine-readable result")
        _add_run_selection(command)
        command.add_argument("--no-tests", action="store_true",
                             help="do not run the project's tests after a repair")
        command.add_argument("--test-command", metavar="CMD",
                             help="run this command instead of detected unittest discovery")
        command.add_argument("--allow-dirty", action="store_true",
                             help="also commit a finding target that already had uncommitted work")
        command.add_argument("--gates", action="store_true",
                             help="also run the AIKit project gates when invoked from AIKit")
        command.add_argument("--commit", action="store_true",
                             help="commit the repair and audit state (explicit paths only)")
        command.add_argument("--push", action="store_true",
                             help="commit, then push without force (implies --commit)")
        _add_review_options(command, findings=True, rules=False)
        if name == "run":
            _add_window_settings(command, defaults=False)
            _add_review_options(command, rules=True)

    review = subparsers.add_parser("review",
                                   help="record the host review of any retained stage packet")
    review.add_argument("target")
    review.add_argument("--json", action="store_true")
    _add_run_selection(review)
    review.add_argument("--stage", type=int, required=True,
                        help="stage number whose packet was reviewed")
    review.add_argument("--findings", required=True, metavar="FILE",
                        help="the reviewer's JSON answer, including every reviewed hunk id")

    analyze = subparsers.add_parser(
        "analyze", help="run an analyzer command on a stage packet and record its findings")
    analyze.add_argument("target", help="registered project name or repository path")
    analyze.add_argument("--json", action="store_true", help="print one machine-readable result")
    _add_run_selection(analyze)
    analyze.add_argument("--stage", type=int, default=None,
                         help="stage number to analyze (default: the latest audited stage)")
    analyze.add_argument("--analyzer", required=True, metavar="CMD",
                         help="command that reads the packet and writes the findings JSON; "
                              "it receives the packet path and the answer path")
    analyze.add_argument("--timeout", type=float, default=300.0,
                         help="seconds before the analyzer is stopped (default: 300)")

    start = subparsers.add_parser("start", help="start an independent audit run")
    start.add_argument("target")
    start.add_argument("--json", action="store_true")
    _add_window_settings(start, defaults=True)
    stop = subparsers.add_parser("stop", help="stop the active audit run and keep its history")
    stop.add_argument("target")
    stop.add_argument("--json", action="store_true")
    _add_run_selection(stop)
    resume = subparsers.add_parser("resume", help="resume a stopped audit run")
    resume.add_argument("target")
    resume.add_argument("--json", action="store_true")
    _add_run_selection(resume)
    settings = subparsers.add_parser("settings", help="change a run's step or stop window")
    settings.add_argument("target")
    settings.add_argument("--json", action="store_true")
    _add_run_selection(settings)
    _add_window_settings(settings, defaults=False)
    runs = subparsers.add_parser("runs", help="list every audit run and its status")
    runs.add_argument("target")
    runs.add_argument("--json", action="store_true")

    status = subparsers.add_parser("status", help="show the active run, next window and pending findings")
    status.add_argument("target")
    status.add_argument("--json", action="store_true")
    report = subparsers.add_parser("report", help="show every audit run and stage")
    report.add_argument("target")
    report.add_argument("--json", action="store_true")


class ReforgeArgumentParser(argparse.ArgumentParser):
    """argparse whose usage errors carry the AIKit What/Why/Fix triad (PRINCIPLE-011)."""

    def error(self, message: str):
        self.print_usage(sys.stderr)
        print(f"Error: {message}", file=sys.stderr)
        print("Why: the command line does not match any Reforge command.", file=sys.stderr)
        print(f"Fix: run `{self.prog} --help` to list the valid forms.", file=sys.stderr)
        raise SystemExit(2)


def build_parser() -> argparse.ArgumentParser:
    parser = ReforgeArgumentParser(
        prog="python reforge.py",
        description="Progressive Git history auditing and autonomous safe repair. Each project "
                    "has independent runs; window N is start + step*(N-1), capped by --stop.",
    )
    commands = parser.add_subparsers(dest="command", required=True,
                                     parser_class=ReforgeArgumentParser)
    add_commands(commands)
    return parser


def _report_error(error: ReforgeError, as_json: bool) -> int:
    if as_json:
        print(json.dumps({"ok": False, "error": {
            "code": "reforge.error", "message": error.message,
            "why": error.why, "fix": error.fix,
        }}, indent=2))
    else:
        print(error.triad(), file=sys.stderr)
    return error.exit_code


def _run_line(run: Dict[str, object]) -> str:
    line = (f"{run.get('id')} [{run.get('status')}] start={run.get('start')} "
            f"step={run.get('step')} stop={run.get('stop') or 'none'} "
            f"stage={run.get('stage')} pending={run.get('pending_fixable')}")
    unreviewed = run.get("unreviewed_stages") or []
    if unreviewed:
        line += " unreviewed=" + ",".join(str(stage) for stage in unreviewed)
    return line


def _print_runs(runs: Sequence[Dict[str, object]]) -> None:
    if not runs:
        print("  no audit runs yet")
    for run in runs:
        print(f"  {_run_line(run)}")


def _print_findings(payload: Dict[str, object]) -> None:
    findings = payload.get("findings") or []
    plan = payload.get("plan") or {}
    print(f"Reforge {payload['mode']} {payload.get('run')} stage {payload['stage']} "
          f"(window {plan.get('window')}, {len(plan.get('new_commits') or [])} new commit(s))")
    for item in findings:
        interaction = f" [{item['interaction']}]" if item.get("interaction") else ""
        origin = " (review)" if item.get("source") == "review" else ""
        print(f"  [{item['category']}/{item['severity']}] {item['path']}:{item['line']} "
              f"{item['code']}: {item['message']}{origin}{interaction}")
        if item.get("evidence"):
            print(f"      evidence: {item['evidence']}")
    for repair in payload.get("repairs") or []:
        mark = "OK" if repair.get("applied") else "SKIP"
        print(f"  [{mark}] {repair['path']}:{repair['line']} {repair['summary']}")
    tests = payload.get("tests") or {}
    if tests:
        print(f"  [{'PASS' if tests.get('passed') else 'FAIL'}] tests: {tests.get('command')}")
    reviewed = int(payload.get("reviewed") or 0)
    if reviewed:
        print(f"  reviewed {reviewed} changed file(s)")
    review = payload.get("review") or {}
    _print_review(review)
    if not findings:
        if review.get("status") == "reviewed":
            print("  no introduced findings")
        else:
            print("  no deterministic findings; host review is still pending")
    skipped = payload.get("skipped") or []
    if skipped:
        shown = ", ".join(str(path) for path in skipped[:5])
        more = f" (+{len(skipped) - 5} more)" if len(skipped) > 5 else ""
        print(f"  [SKIP] {len(skipped)} binary file(s) not analysed: {shown}{more}")
    if payload["mode"] == "audit" and findings:
        print(f"Next: review {payload.get('root')}, write the findings JSON, then run "
              f"`python reforge.py fix {payload['root']} --run {payload.get('run')} "
              f"--findings <file>`.")
    elif payload["mode"] == "review":
        print(f"Stage {payload['stage']} is recorded as reviewed.")
    elif payload["mode"] in {"run", "fix"} and payload.get("repaired"):
        print(f"Next: review the patch in {payload['root']}, then commit with --commit/--push.")
    elif payload["mode"] in {"run", "fix"}:
        print("No safe automatic repair: review the evidence above and fix by hand.")
    if payload.get("run_status") == "completed":
        print(f"Run {payload.get('run')} reached its stop and is complete.")
    _print_ledger(payload)


def _start_payload(payload: Dict[str, object]) -> None:
    print(f"[OK] Started {payload['run']['id']} (start={payload['run']['start']}, "
          f"step={payload['run']['step']}, stop={payload['run']['stop'] or 'none'}).")
    _print_runs(payload.get("runs") or [])
    _print_ledger(payload)


def _print_review(report: Dict[str, object]) -> None:
    """Say whether a reviewer answered the stage, and where its packet is."""
    status = str(report.get("status") or "")
    if not status:
        return
    packet = report.get("packet") or ""
    accepted = len(report.get("findings") or [])
    rejected = len(report.get("rejected") or [])
    redacted = int(report.get("redacted") or 0)
    detail = f", {accepted} accepted" + (f", {rejected} dropped" if rejected else "")
    if report.get("method"):
        detail += f", via {report['method']}"
    if redacted:
        detail += f", {redacted} secret span(s) redacted"
    if status == "reviewed":
        print(f"  [REVIEW] reviewed {len(report.get('files') or [])} file(s){detail}")
    elif status == "unreviewed":
        print(f"  [REVIEW] awaiting the host review{detail}")
    elif status == "partial":
        print(f"  [REVIEW] incomplete review{detail}: {report.get('reason') or 'unknown'}")
    else:
        print(f"  [REVIEW] {status}: {report.get('reason') or 'unknown'}")
    coverage = report.get("coverage") or {}
    if isinstance(coverage, dict) and coverage:
        missing = len(coverage.get("missing") or [])
        print(f"      hunk coverage: {coverage.get('reported', 0)}/{coverage.get('total', 0)}"
              + (f", {missing} missing" if missing else ""))
    if packet:
        print(f"      packet: {packet}")


def _print_ledger(payload: Dict[str, object]) -> None:
    """Say where the run was recorded: the ledger is how a cold start finds an open audit."""
    ledger = payload.get("ledger") or {}
    if not isinstance(ledger, dict):
        return
    if ledger.get("recorded"):
        print(f"  [OK] task ledger {ledger.get('task_id')} updated in {ledger.get('path')}")
    elif ledger.get("path"):
        print(f"  [WARN] task ledger not updated: {ledger.get('reason')}")
    elif ledger.get("reason"):
        print(f"  [SKIP] task ledger not updated: {ledger.get('reason')}")


def _workspace(args, root: Path, gate_runner: Optional[GateRunner]) -> int:
    import reforge.pipeline as pipeline
    from reforge.delivery import deliver

    action = getattr(args, "reforge_action", None) or args.command
    as_json = bool(getattr(args, "json", False))
    if action == "audit" and (getattr(args, "commit", False) or getattr(args, "push", False)):
        raise ReforgeError(
            "--commit is not valid with audit.",
            "an audit records findings but changes no code, so there is no repair patch to commit.",
            "run `fix` or `run`, then commit the repair patch; nothing was recorded.",
            exit_code=2,
        )
    if action == "status":
        payload = pipeline.status_payload(root)
        if as_json:
            print(json.dumps({"ok": True, "result": payload}, indent=2))
        else:
            print(f"Repository: {payload['root']}")
            print(f"HEAD:       {payload['head'][:12] or 'none'}")
            run = payload.get("run")
            print(f"Active run: {payload.get('active_run') or 'none'}"
                  + (f" ({run['status']})" if run else ""))
            if run:
                print(f"Settings:   start={run['start']} step={run['step']} "
                      f"stop={run['stop'] or 'none'}")
            print(f"Stage:      {payload['stage']} completed; next {payload['next_stage']} "
                  f"(window {payload['next_window'] or 'none'})")
            print(f"Audited:    {payload['audited_commits']} commit(s)")
            print(f"Pending:    {payload['pending_findings']} fixable finding(s)")
            unreviewed = payload.get("unreviewed_stages") or []
            if unreviewed:
                print("Unreviewed: stage(s) " + ", ".join(str(stage) for stage in unreviewed))
            review = payload.get("review") or {}
            if review:
                packet = review.get("packet") or ""
                print(f"Review:     {review.get('status') or 'unreviewed'}"
                      + (f" ({packet})" if packet else ""))
            print("Runs:")
            _print_runs(payload.get("runs") or [])
        return 0
    if action == "runs":
        payload = pipeline.runs_payload(root)
        if as_json:
            print(json.dumps({"ok": True, "result": payload}, indent=2))
        else:
            print(f"Audit runs for {payload['root']}:")
            _print_runs(payload.get("runs") or [])
        return 0
    if action == "report":
        payload = pipeline.report_payload(root)
        if as_json:
            print(json.dumps({"ok": True, "result": payload}, indent=2))
        else:
            print(f"Reforge report for {payload['root']}: {len(payload['runs'])} run(s)")
            for run in payload["runs"]:
                pending = len(pipeline.pending_fixable(run))
                print(f"  {_run_line({**run, 'pending_fixable': pending})}")
                for entry in run.get("history") or []:
                    counts = ", ".join(f"{k}={v}" for k, v in
                                       sorted((entry.get("counts") or {}).items()))
                    skipped = len(entry.get("skipped") or [])
                    review = (entry.get("review") or {}).get("status") or "unreviewed"
                    print(f"    stage {entry['stage']} window {entry['window']}: "
                          f"{len(entry.get('new_commits') or [])} new, "
                          f"{int(entry.get('reviewed') or 0)} file(s), review {review}, "
                          f"{len(entry.get('repairs') or [])} repair(s)"
                          f"{', ' + str(skipped) + ' binary not analysed' if skipped else ''}"
                          f"{' (' + counts + ')' if counts else ''}")
        return 0
    if action == "review":
        payload = pipeline.review_stage(root, run_id=getattr(args, "run_id", None),
                                        stage=getattr(args, "stage", None),
                                        findings_file=getattr(args, "findings", None))
        if as_json:
            print(json.dumps({"ok": True, "result": payload}, indent=2))
        else:
            _print_findings(payload)
        return 0
    if action == "analyze":
        payload = pipeline.analyze_stage(
            root, run_id=getattr(args, "run_id", None), stage=getattr(args, "stage", None),
            command=getattr(args, "analyzer", ""), timeout=getattr(args, "timeout", 300.0))
        if as_json:
            print(json.dumps({"ok": True, "result": payload}, indent=2))
        else:
            _print_findings(payload)
        return 0
    if action == "start":
        payload = pipeline.start_audit(root, start=args.start, step=args.step, stop=args.stop)
        if as_json:
            print(json.dumps({"ok": True, "result": payload}, indent=2))
        else:
            _start_payload(payload)
        return 0
    if action == "stop":
        payload = pipeline.stop_audit(root, run_id=getattr(args, "run_id", None))
        if as_json:
            print(json.dumps({"ok": True, "result": payload}, indent=2))
        else:
            print(f"[OK] Stopped {payload['run']['id']}; its history is kept.")
            _print_runs(payload.get("runs") or [])
            _print_ledger(payload)
        return 0
    if action == "resume":
        payload = pipeline.resume_audit(root, run_id=getattr(args, "run_id", None))
        if as_json:
            print(json.dumps({"ok": True, "result": payload}, indent=2))
        else:
            print(f"[OK] Resumed {payload['run']['id']} at stage {payload['run']['stage']}.")
            _print_ledger(payload)
        return 0
    if action == "settings":
        payload = pipeline.configure_audit(root, run_id=getattr(args, "run_id", None),
                                           start=args.start, step=args.step, stop=args.stop)
        if as_json:
            print(json.dumps({"ok": True, "result": payload}, indent=2))
        else:
            print(f"[OK] {_run_line(payload['run'])}")
        return 0

    do_commit = bool(getattr(args, "commit", False) or getattr(args, "push", False))
    payload = pipeline.run_pipeline(
        root, mode=action, add_tests=True, run_tests=not getattr(args, "no_tests", False),
        test_command=getattr(args, "test_command", None), gate_runner=gate_runner,
        allow_dirty=getattr(args, "allow_dirty", False), run_id=getattr(args, "run_id", None),
        start=getattr(args, "start", None), step=getattr(args, "step", None),
        stop=getattr(args, "stop", None),
        rules=bool(getattr(args, "rules", False)),
        findings_file=getattr(args, "findings", None),
        deliver=do_commit,
    )
    if do_commit:
        run_name = payload.get("run") or "active"
        if payload.get("repaired"):
            message = f"fix(reforge): repair {run_name} stage {payload['stage']} findings"
        else:
            message = f"chore(reforge): record {run_name} stage {payload['stage']} audit"
        delivery = deliver(root, message, bool(getattr(args, "push", False)),
                           paths=payload.get("commit_paths"))
        payload["delivery"] = delivery[0]
        payload["delivery_lines"] = delivery[1]
    if as_json:
        print(json.dumps({"ok": True, "result": payload}, indent=2))
    else:
        _print_findings(payload)
        for line in payload.get("delivery_lines") or []:
            print(line)
    return 0


def dispatch(args, aikit_root: Optional[Path] = None, project_root: Optional[Path] = None,
             gate_runner: Optional[GateRunner] = None) -> int:
    """Run one parsed request; every failure is reported as a triad or a JSON envelope."""
    as_json = bool(getattr(args, "json", False))
    try:
        root = Path(project_root) if project_root else Path(getattr(args, "target", ""))
        root = root.expanduser().resolve()
        if not root.is_dir():
            raise ReforgeError(
                f"{root} is not a directory.",
                "Reforge audits a repository root or an AIKit project name.",
                "pass the repository path, or register the project with `aikit attach`.",
                exit_code=2,
            )
        return _workspace(args, root, gate_runner)
    except ReforgeError as error:
        return _report_error(error, as_json)
    except OSError as error:
        return _report_error(ReforgeError(
            "a filesystem operation failed",
            f"the operating system denied or interrupted it: {error}",
            "check the path permissions and free space, then retry.",
        ), as_json)
    except Exception as error:  # report an unexpected stop instead of a traceback (PRINCIPLE-011)
        return _report_error(ReforgeError(
            "Reforge stopped unexpectedly.",
            f"{type(error).__name__}: {error}",
            "nothing was committed; re-run with --json and report the message and command.",
        ), as_json)


def main(argv: Optional[List[str]] = None) -> int:
    args = build_parser().parse_args(argv)
    return dispatch(args, aikit_root=Path(__file__).resolve().parent.parent)
