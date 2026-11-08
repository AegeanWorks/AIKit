"""
`aikit` command line: create, attach, list, report on, check, fix and delegate for the projects
AIKit builds (ADR-119 to ADR-128).

Run through the root shim: `python aikit.py <command>`. Exit codes: 0 success, 1 the request
could not be carried out, 2 the command line was wrong (PRINCIPLE-011).
"""

import argparse
import json
import re
import sys
import time
from pathlib import Path
from typing import Dict, List, Optional

from scripts.aikit_parser import TriadArgumentParser, build_parser, report_error  # re-exported
from scripts.disruption_recovery import (
    UnsupportedLedgerVersion,
    LedgerOwnershipError,
    atomic_write_json,
    checkpoint_command,
    clean_dangling_temp_files,
    file_lock,
    format_resume_report,
    mark_task_completed,
    report_ownership,
    resolve_agent,
    run_disruption_audit,
    workspace_ledger_path,
)
from scripts.project_license import (
    TIER_RESTRICTED,
    apply_license_kind,
    license_state,
    public_remote_refusal,
    restrict_project,
    suggest_license,
)
from scripts.project_publish import (
    auto_push_project,
    extract_readme_description,
    get_project_repo_url,
    publish_project,
)
from scripts.git_guard import install_pre_push_hook, is_guard_installed
from scripts.project_archive import archive_project, is_archived

from scripts.project_registry import (
    DEFAULT_LICENSE_KIND,
    DESCRIPTION_MAX,
    DESCRIPTION_MIN,
    INTEGRATION_TOPICS,
    LICENSE_CHOICES,
    MAX_TOPICS,
    Project,
    ProjectError,
    add_aikit_badge,
    add_guideline,
    attach_project,
    config_path,
    create_project,
    find_project,
    latest_decision,
    license_topics,
    list_projects,
    load_config,
    mechanics_errors,
    migrate_aikit_links,
    normalize_topics,
    is_game_project,
    project_guidelines,
    reconcile_readme_tree,
    seed_readme,
    seed_reuse,
    write_memory,
)
from scripts.subagent_delegate import delegate_subagent
from scripts import ui_contract
from scripts import dossier_sync, project_artwork, project_media, project_topics, project_ui
from scripts.update_knowledge_base import (
    find_python_files,
    generate_codebase_map,
    write_generated_file,
)


def failure_tail(output):
    from scripts.project_gates import failure_tail as _failure_tail
    return _failure_tail(output)


def _register_delivered_ideas(project_path: Path, project_name: str) -> List[dict]:
    """Register ideas named by the project's delivered commits; raises on a bad register."""
    from idea_catcher.registry import register_from_repo
    return register_from_repo(project_path, project_name)


def _report_registered_ideas(project_path: Path, project_name: str) -> None:
    """Best-effort registration after a push; delivery already succeeded, so never fail it."""
    try:
        registered = _register_delivered_ideas(project_path, project_name)
    except Exception as exc:  # the push is the delivery boundary; registration is bookkeeping
        print(f"[WARN] idea-catcher auto-registration skipped: {exc}", file=sys.stderr)
        return
    if registered:
        print("[OK] idea-catcher: registered "
              + ", ".join(str(row.get("id", "")) for row in registered)
              + " from the delivered commits; MATRIX.md refreshed.")


def _sync_dossier(project_path: Path, project_name: str) -> None:
    """Best-effort dossier catalogue sync after a publish; the publish itself already succeeded."""
    try:
        result = dossier_sync.sync_published(project_path, project_name)
    except (ProjectError, OSError, ValueError, KeyError) as exc:
        print(f"[DOSSIER] catalogue sync skipped: {exc}", file=sys.stderr)
        return
    if result.get("skipped"):
        print(f"[DOSSIER] {result['skipped']}; the catalogue is unchanged.")
        return
    print(f"[DOSSIER] updated {result['repo']} in the AegeanWorks catalogue "
          f"(category={result['category']}, {result['family']}): "
          + ", ".join(str(path) for path in result["files"]))
    print(f"[DOSSIER] {result['media']}")
    print("[DOSSIER] Review and commit the AegeanWorks repository; nothing was committed here.")


def resolve_gates(project):
    from scripts.project_gates import resolve_gates as _resolve_gates
    return _resolve_gates(project)


def run_gates(path, gates):
    from scripts.project_gates import run_gates as _run_gates
    return _run_gates(path, gates)


def present_project(name: str, workspace: Path) -> Project:
    """The registered project `name`, refusing one whose folder or record is gone."""
    project = find_project(name, workspace)
    if not project.present:
        raise ProjectError(
            f"Project '{project.name}' is missing at {project.path}.",
            "its folder or .aikit/project.json is gone, so there is no memory to use.",
            "restore the folder, or attach its new location with `python aikit.py attach <path>`.",
        )
    return project


def project_is_clean(audit: Dict[str, object], open_ui_task: bool) -> bool:
    """
    Whether the project's tree and ledger are delivery-ready, decided once for every surface.

    `status --exit-code` and `status --json` both read this. Computing the same verdict twice is
    the defect class ADR-155 and ADR-161 each had to repair, where two readiness surfaces
    disagreed about one tree and auto-push followed the laxer one (ADR-172). A ledger error is a
    failed audit, not a clean tree, so it is part of the verdict (ADR-177).
    """
    dirty = (audit.get("modified_files") or audit.get("untracked_files")
             or audit.get("conflicted_files"))
    return not (audit.get("git_missing") or audit.get("ledger_error") or dirty or open_ui_task)


# GitHub topic per detected stack (ADR-215); java-maven and java-gradle are both `java`.
# A brand-new project has no marker files, so its test runner is only a hint for the AI brief,
# never an automatically published topic (ADR-216, ADR-236).
TEST_RUNNER_TOPICS = (
    (("python", "pytest", "unittest"), "python"),
    (("npm ", "npm test", "yarn", "pnpm", "jest", "vitest", "node "), "javascript"),
    (("cargo",), "rust"),
    (("go test",), "golang"),
    (("mvn", "gradle"), "java"),
    (("dotnet",), "dotnet"),
)


def test_command_topic(test_command: Optional[str]) -> Optional[str]:
    """The language topic a known test runner implies, or None for a custom command."""
    command = (test_command or "").lower()
    for runners, topic in TEST_RUNNER_TOPICS:
        if any(runner in command for runner in runners):
            return topic
    return None


def publish_topics(recorded: List[str]) -> List[str]:
    """The AI-chosen topics `publish` sets, validated; AIKit adds no tag on its own (ADR-236)."""
    return normalize_topics(list(recorded))


def license_summary(project: Project) -> str:
    """One line on the project's license tier for `status` (ADR-214)."""
    state = license_state(project.path)
    if state.tier == TIER_RESTRICTED:
        # A hand-edited project.json can record the tier without its cutoff; say so rather than
        # print "since None, cutoff  (All Rights Reserved)".
        since = state.since or "an unrecorded date"
        cutoff = state.since_commit[:12] if state.since_commit else "an unrecorded commit"
        return f"restricted since {since}, cutoff {cutoff} (All Rights Reserved)"
    if state.tier == "personal":
        choice = LICENSE_CHOICES.get(state.kind)
        if not choice:
            return "personal (AL-1.1, free personal use)"
        version = state.version or choice["version"]
        key = f"{choice['key'].rsplit('-', 1)[0]}-{version}"
        summary = choice["summary"].split(", ", 1)[1]
        return f"personal ({key}, {summary})"
    return "unrecorded (the project's own LICENSE applies)"


def project_payload(project: Project) -> Dict[str, object]:
    """The project half of a `--json` report: what `status` prints as its header lines."""
    state = license_state(project.path)
    return {
        "license": {"tier": state.tier, "since": state.since, "since_commit": state.since_commit},
        "name": project.name,
        "path": str(project.path),
        "repo_url": get_project_repo_url(project.path),
        "stacks": [stack.name for stack in project.stacks],
        "test_command": project.test_command or None,
        "latest_decision": latest_decision(project.path) or None,
        # The rules themselves, not a count: PRINCIPLE-004 R2 requires them in every cold-start
        # report, and a JSON reader that got only a number would silently lose them (ADR-172).
        "guidelines": project_guidelines(project.path),
    }


def error_envelope(error: ProjectError) -> str:
    """The stable `--json` failure shape shared by every project command (ADR-167, ADR-172)."""
    return json.dumps({"ok": False,
                       "error": {"code": "project.error", "message": str(error)}}, indent=2)


def print_guidelines(project: Project) -> None:
    """The project's own rules, with their rank, in every cold-start report (PRINCIPLE-004 R2)."""
    rules = project_guidelines(project.path)
    print(f"Guidelines: {len(rules)} rule(s) in .aikit/guidelines.md; they add to and rank below "
          f"AIKit's principles (PRINCIPLE-000 R6).")
    for rule in rules:
        print(f"  {rule}")


def cmd_new(args: argparse.Namespace) -> int:
    # Checked before anything is created: alone, --public was silently ignored (ADR-192).
    if getattr(args, "public", False) and not getattr(args, "publish", False):
        return report_error(ProjectError(
            "--public needs --publish.",
            "--public sets the visibility of the GitHub repository that --publish creates; "
            "without --publish no repository is created.",
            f"add --publish, or create the project now and run `python aikit.py publish {args.name} "
            "--public` later.",
            exit_code=2,
        ))
    # `new --publish` uploads only AIKit's starter files, so it skips publish's gates, which the
    # seed's <FILL: markers would always fail; a repository still never starts undescribed (ADR-205).
    if getattr(args, "publish", False) and not getattr(args, "description", None):
        return report_error(ProjectError(
            "--publish needs --description.",
            "the GitHub repository --publish creates takes its description from the new README, "
            "which has none until --description gives it one.",
            f'add --description "<one line, 10-350 characters>", or create the project now and run '
            f"`python aikit.py publish {args.name}` once its README is filled.",
            exit_code=2,
        ))
    license_kind = getattr(args, "license_kind", "auto")
    if license_kind == "auto":
        license_kind = DEFAULT_LICENSE_KIND
    root = create_project(
        args.name, args.test, workspace=args.workspace, description=args.description,
        topics=args.topic, license_kind=license_kind,
    )
    print(f"[OK] Created project '{args.name}' at {root} "
          f"with the {LICENSE_CHOICES[license_kind]['name']}")
    if config_path(root).is_file():
        identity = project_ui.auto_ui(root)
        print(f"     UI identifier: has_ui={identity['has_ui']} kind={identity['kind']} "
              "(uncommitted; update with `ui-id` as the interface appears).")
    if not getattr(args, "no_media", False):
        media = None
        if project_artwork.model_key():
            try:
                media = project_artwork.generate_model_brand(
                    root, args.name, force=True)
                print("     AI-generated logo and social banner created "
                      "(uncommitted; vision review required before applying).")
            except (ProjectError, OSError, ValueError) as exc:
                print(f"     [WARN] Image-model brand generation failed: {exc}", file=sys.stderr)
        if media is None:
            media = project_media.seed_media_assets(root, args.name)
            print("     Local brand candidates generated "
                  "(uncommitted; set POLLINATIONS_API_KEY for model-rendered assets).")
        print(f"     Next: review `python aikit.py media review {args.name} ...`, then "
              f"`python aikit.py media apply {args.name}` before publishing.")
    if getattr(args, "publish", False):
        blockers = project_media.media_blockers(root)
        if blockers:
            print(f"Error: '{args.name}' has unreviewed brand assets.", file=sys.stderr)
            print(f"Why: {', '.join(blockers)} must be approved before publication.", file=sys.stderr)
            print(f"Fix: review with `python aikit.py media review {args.name} ...`, apply, "
                  "then publish; the project stays local.", file=sys.stderr)
            return 2
        print(f"Publishing '{args.name}' to GitHub:")
        # Tags are chosen by an AI, never inferred here; `--topic` is the explicit first choice.
        first_topics = normalize_topics(
            [*INTEGRATION_TOPICS, *license_topics(license_kind),
             *(args.topic or [])][:MAX_TOPICS])
        code, report = publish_project(root, args.name, public=getattr(args, "public", False),
                                       topics=publish_topics(first_topics))
        print(report, file=sys.stdout if code == 0 else sys.stderr)
        if code != 0:
            print(f"[WARN] Project created locally at {root}, but GitHub publication failed.", file=sys.stderr)
            return code
        _report_registered_ideas(root, args.name)
        _sync_dossier(root, args.name)
    else:
        print(f"     Next: describe what to build; work happens inside {root}.")
    return 0


def cmd_attach(args: argparse.Namespace) -> int:
    name, folder, created = attach_project(args.path, args.name, args.test, workspace=args.workspace)
    state = "created .aikit/ memory" if created else "kept its existing .aikit/ memory"
    print(f"[OK] Attached '{name}' at {folder} ({state})")
    # The gates are the project's own commands; a process boundary is no security boundary (ADR-207).
    print("     Note: check, fix and publish run this project's own commands under your account, "
          "unsandboxed; attach only repositories you trust.")
    # An integrated project says so and links to AIKit; the edit is the user's to commit (ADR-202).
    if migrate_aikit_links(folder):
        print("     Updated the README's pre-move AIKit link (uncommitted; review and commit it).")
    elif add_aikit_badge(folder):
        print("     Added the AIKit Integrated badge under the README title (uncommitted; review and "
              "commit it).")
    elif not (folder / "README.md").is_file():
        print(f"     No README.md: `python aikit.py fix {name}` writes one with the AIKit Integrated badge.")
    if config_path(folder).is_file():
        identity = project_ui.auto_ui(folder)
        print(f"     UI identifier: has_ui={identity['has_ui']} kind={identity['kind']} "
              f"(uncommitted; review and commit it).")
    if not (folder / ".aikit" / "media.json").is_file():
        try:
            project_media.seed_media_assets(folder, name)
            print("     Local brand candidates generated "
                  "(uncommitted; review before applying).")
        except (ProjectError, OSError, ValueError) as exc:
            # A read-only or full assets folder must not undo a successful attach.
            print(f"     [WARN] Brand media candidates could not be generated: {exc}")
    return 0


def cmd_list(args: argparse.Namespace) -> int:
    projects = list_projects(args.workspace)
    if not projects:
        print("No projects yet. Create one with `python aikit.py new <name>`.")
        return 0
    for project in projects:
        if not project.present:
            print(f"{project.name}  MISSING  {project.path}  (folder or .aikit/project.json gone)")
            continue
        stacks = ",".join(s.name for s in project.stacks) or "no stack detected"
        test = project.test_command or "no test command"
        kind = "attached" if project.attached else "local"
        repo_url = get_project_repo_url(project.path)
        repo_note = f"  repo: {repo_url}" if repo_url else ""
        archived = "  [ARCHIVED]" if is_archived(project.path) else ""
        print(f"{project.name}  [{stacks}]  test: {test}  ({kind}: {project.path}){repo_note}{archived}")
    return 0


def cmd_status(args: argparse.Namespace) -> int:
    if getattr(args, "json", False):
        try:
            project = present_project(args.name, args.workspace)
        except ProjectError as exc:
            print(error_envelope(exc))
            return exc.exit_code
        audit = run_disruption_audit(workspace_dir=project.path)
        open_ui_task = (project.path / ui_contract.TASK_REL).is_file()
        clean = project_is_clean(audit, open_ui_task)
        print(json.dumps({
            "ok": True,
            "clean": clean,
            "project": project_payload(project),
            "disruption": audit,
            "ui_task_open": open_ui_task,
            "gates": [gate.name for gate in resolve_gates(project)],
        }, indent=2, default=str))
        if audit.get("ledger_error"):
            return 1
        if getattr(args, "exit_code", False) and not clean:
            return 1
        return 0
    project = present_project(args.name, args.workspace)
    stacks = ",".join(s.name for s in project.stacks) or "none detected"
    repo_url = get_project_repo_url(project.path)
    print(f"Project:   {project.name}  ({project.path})")
    print(f"Repo:      {repo_url or f'none (local only; publish with python aikit.py publish {project.name})'}")
    print(f"Stacks:    {stacks}")
    print(f"License:   {license_summary(project)}")
    print(f"Tests:     {project.test_command or 'none; set one with .aikit/project.json test_command'}")
    print(f"Decision:  {latest_decision(project.path) or 'none recorded yet'}")
    print_guidelines(project)
    audit = run_disruption_audit(workspace_dir=project.path)
    print(format_resume_report(audit))
    if audit.get("ledger_error"):
        return 1
    open_ui_task = (project.path / ui_contract.TASK_REL).is_file()
    if open_ui_task:
        print(f"UI task:   open at {ui_contract.TASK_REL}; "
              f"run `python aikit.py ui status {project.name}`")
    # PRINCIPLE-011 R8: for project work, the project is the workspace of every lifecycle command.
    print(f'Ledger:    python aikit.py checkpoint {project.name} --task <id> --phase-num <1-5> --desc "..."')
    gates = ", ".join(gate.name for gate in resolve_gates(project))
    print(f"Phase 4 gates ({gates}): python aikit.py check {project.name}")
    if getattr(args, "exit_code", False) and not project_is_clean(audit, open_ui_task):
        return 1
    return 0



def cmd_resume(args: argparse.Namespace) -> int:
    if getattr(args, "json", False):
        try:
            project = present_project(args.name, args.workspace)
        except ProjectError as exc:
            print(error_envelope(exc))
            return exc.exit_code
        audit = run_disruption_audit(workspace_dir=project.path)
        print(json.dumps({"ok": True, "project": project_payload(project),
                          "disruption": audit}, indent=2, default=str))
        return 1 if audit.get("ledger_error") else 0
    project = present_project(args.name, args.workspace)
    print_guidelines(project)
    audit = run_disruption_audit(workspace_dir=project.path)
    print(format_resume_report(audit))
    return 1 if audit.get("ledger_error") else 0


def cmd_guideline(args: argparse.Namespace) -> int:
    project = present_project(args.name, args.workspace)
    gid = add_guideline(project.path, args.rule, args.source)
    print(f"[OK] {gid} added to the guidelines of '{project.name}'; it ranks below AIKit's principles.")
    return 0


def cmd_checkpoint(args: argparse.Namespace) -> int:
    project = present_project(args.name, args.workspace)
    impact = {"why": args.why, "benefits": args.benefits, "risks": args.risks,
              "mitigation": args.mitigation}
    return checkpoint_command(args.task, f"phase {args.phase_num}", args.phase_num, args.desc, impact,
                              workspace_ledger_path(project.path), redact=args.redact,
                              handoff=args.handoff, agent=args.agent, take_over=args.take_over)


def cmd_complete(args: argparse.Namespace) -> int:
    project = present_project(args.name, args.workspace)
    try:
        writer = resolve_agent(args.agent)
    except ValueError as error:
        return report_error(ProjectError(str(error), "the ledger names the agent behind every write (ADR-209).",
                                         "pass --agent <host>:<session>, or set AIKIT_AGENT.", exit_code=2))
    try:
        completed = mark_task_completed(args.task, ledger_file=workspace_ledger_path(project.path),
                                        agent=writer, take_over=args.take_over)
    except LedgerOwnershipError as error:
        return report_ownership(error)
    if completed:
        print(f"[OK] Task '{args.task}' marked as completed in '{project.name}'.")
        return 0
    print(f"Error: task '{args.task}' is not the active task of '{project.name}'.", file=sys.stderr)
    print("Why: only the active task can be completed; nothing was changed.", file=sys.stderr)
    print(f"Fix: run `python aikit.py resume {project.name}` to see the active task's ID.", file=sys.stderr)
    return 1


def cmd_clean(args: argparse.Namespace) -> int:
    project = present_project(args.name, args.workspace)
    # Only stale buffers: a younger one may be another agent's atomic write in flight (PRINCIPLE-013).
    cleaned = clean_dangling_temp_files(project.path)
    for rel in cleaned:
        print(f"[CLEAN] {rel}")
    print(f"[OK] {len(cleaned)} stale temporary file(s) removed from '{project.name}'.")
    return 0


def project_baseline_errors(project: Project, audit: dict) -> List[str]:
    """The delivery baseline `--strict` requires; ordinary check reports these as warnings."""
    errors: List[str] = []
    if audit.get("ledger_error"):
        errors.append("the project ledger declares a schema this AIKit cannot read")
    if audit.get("git_missing"):
        errors.append("the project is not a git repository, so a clean tree cannot be verified")
    if audit.get("modified_files") or audit.get("untracked_files"):
        errors.append("the project has uncommitted non-bookkeeping changes")
    if audit.get("conflicted_files"):
        errors.append("the project has unresolved merge conflicts")
    if (project.path / ui_contract.TASK_REL).is_file():
        errors.append("a UI task is open; finish or abort it before delivery")
    config = load_config(project.path)
    required = config.get("ui_required") is True
    contract_path = project.path / ui_contract.CONTRACT_REL
    if required or contract_path.is_file():
        try:
            ui_contract.load_contract(project.path)
        except ProjectError as exc:
            prefix = ("ui_required is true but the UI contract is unusable" if required
                      else "the UI contract is unusable")
            errors.append(f"{prefix}: {exc}")
        else:
            if required and not audit.get("git_missing"):
                try:
                    errors.extend(ui_contract.surface_evidence_errors(project.path))
                except ProjectError as exc:
                    errors.append(f"the UI evidence is unusable: {exc}")
    errors.extend(mechanics_errors(project.path, config))
    if find_python_files(project.path) and not (project.path / ".aikit" / "codebase_map.md").is_file():
        errors.append("Python sources exist but .aikit/codebase_map.md is missing")
    return errors


def default_topic_warning(project: Project) -> Optional[str]:
    """The default-only topic warning, or None when the project has a domain topic."""
    try:
        config = load_config(project.path)
    # hygiene: allow the default-topic warning is best effort; a missing record omits it
    except (OSError, ValueError, KeyError, ProjectError):
        return None
    topics = list(config.get("topics") or [])
    try:
        state = license_state(project.path)
        kind = state.kind
        restricted = state.tier == TIER_RESTRICTED
    # hygiene: allow the license tier is best effort; an unreadable record keeps the default warning
    except (OSError, ValueError, ProjectError):
        kind, restricted = None, False
    defaults = set(INTEGRATION_TOPICS) | set(license_topics(kind, restricted=restricted))
    if any(topic not in defaults for topic in topics):
        return None
    return (f"[WARN] '{project.name}' only has default license topics; run "
            f"`python aikit.py topics {project.name} --brief`, then record the choice with "
            f"`--from-file` or `--set`.")


def ui_review_waiver(project_root: Path) -> Optional[str]:
    """The project rule that waives the person in a UI review, or None (ADR-310)."""
    for line in project_guidelines(project_root):
        text = line.lower()
        asks_nobody = any(phrase in text for phrase in (
            "do not ask", "don't ask", "never ask", "no human", "not ask"))
        names_review = "ui review" in text or "ui/ux review" in text
        if asks_nobody and names_review:
            return line
    return None


def _named_guideline(line: str) -> str:
    match = re.search(r"G-\d{3}", line)
    return match.group(0) if match else "the project guideline"


def cmd_check(args: argparse.Namespace) -> int:
    project = present_project(args.name, args.workspace)
    # A restricted project may be pushed only to a private repository (ADR-214); checked before the
    # gates so a refused push costs nothing.
    if getattr(args, "push", False):
        refusal = public_remote_refusal(project.path, project.name)
        if refusal:
            return report_error(refusal)
    results = run_gates(project.path, resolve_gates(project))
    for result in results:
        mark = "PASS" if result.passed else "FAIL"
        print(f"[{mark}] {result.gate.name} ({result.seconds:.1f}s, {result.gate.source}): {result.gate.command}")
        if not result.passed:
            for line in failure_tail(result.output):
                print(f"       {line}")
    passed = sum(result.passed for result in results)
    print(f"{passed}/{len(results)} gates passed for '{project.name}'")
    print("Manual: record 'checklists: passed' or the failed or skipped item IDs in the task's"
          " latest checkpoint before the next commit (PRINCIPLE-001 R8, PRINCIPLE-011 R8).")
    # These warnings describe the project, not the gate run, so a failing tier must not hide them;
    # `fix` ends in this same check and used to print the topic warning a second time on success.
    if not (project.path / ".aikit" / "media.json").is_file():
        print(f"[WARN] Brand media not initialized; run `python aikit.py media init {project.name}`.")
    warning = default_topic_warning(project)
    if warning:
        print(warning)
    failed = [result.gate.name for result in results if not result.passed]
    sys.stdout.flush()  # the report above, then the triad, in that order when both are piped
    if failed:
        print(f"Error: gate(s) failed: {', '.join(failed)}", file=sys.stderr)
        print("Why: a project commits only when every gate passes (PRINCIPLE-011 R8, PRINCIPLE-014 R1).",
              file=sys.stderr)
        print(f"Fix: run `python aikit.py fix {project.name}` for memory and map drift; fix any other "
              "cause shown above by hand, then rerun the check.", file=sys.stderr)
        return 1
    if not any(result.gate.name == "test" for result in results):
        print("Error: the project has no test gate.", file=sys.stderr)
        print("Why: without tests the gates prove nothing about behaviour (PRINCIPLE-011 R8, PRINCIPLE-014 R1).", file=sys.stderr)
        print("Fix: write tests, and set `test_command` in .aikit/project.json when it is not detected.",
              file=sys.stderr)
        return 1

    audit = run_disruption_audit(workspace_dir=project.path)
    baseline_errors = project_baseline_errors(project, audit)
    strict = bool(getattr(args, "strict", False))
    for error in baseline_errors:
        print(f"[{'FAIL' if strict else 'WARN'}] {error}")
    identity = project_ui.ui_payload(project.path)
    if (identity.get("has_ui")
            and not (project.path / ui_contract.CONTRACT_REL).is_file()):
        print("[WARN] UI detected but .aikit/ui.json is missing; run `python aikit.py fix "
              f"{project.name}` or `python aikit.py ui init {project.name}`.")
    game_config = load_config(project.path)
    if is_game_project(game_config) and not isinstance(game_config.get("mechanics"), dict):
        print("[WARN] Game detected but .aikit/project.json has no mechanics contract; declare "
              "`mechanics.core` and `mechanics.test` for a headless AI-testable core.")
    if audit.get("ledger_error") or (strict and baseline_errors):
        print("Error: the project is not delivery-ready.", file=sys.stderr)
        print("Why: a passing gate run must describe the committed tree, not an unverified working copy.",
              file=sys.stderr)
        print("Fix: commit the non-bookkeeping changes, resolve any merge conflicts, finish or "
              "abort any open UI task, run `python aikit.py fix <name>` for a missing map, or "
              "open the ledger with the AIKit version that wrote it; then rerun with --strict.",
              file=sys.stderr)
        return 1

    open_ui_task = (project.path / ui_contract.TASK_REL).is_file()
    ui_unready = any(error.startswith(("ui_required is true", "the UI contract is unusable",
                                       "UI surface", "the UI evidence is unusable"))
                     for error in baseline_errors)
    dirty = bool(audit.get("modified_files") or audit.get("untracked_files")
                 or audit.get("conflicted_files")) or open_ui_task or ui_unready
    if dirty:
        detail = (f"{len(audit.get('modified_files', []))} modified, "
                  f"{len(audit.get('untracked_files', []))} untracked, "
                  f"{len(audit.get('conflicted_files', []))} conflicted")
        if open_ui_task:
            detail += ", 1 open UI task"
        if ui_unready:
            detail += ", UI contract not delivery-ready"
        print(f"[DELIVERY] NOT READY: {detail}; run `check --strict` before pushing.")
    # Pushing is opt-in. check is the documented Phase 4, and it used to publish unpushed commits
    # whenever its gates passed, so an agent whose host allows a push only on request pushed
    # without one (PRINCIPLE-018 R4, ADR-185).
    # A push that was asked for and did not happen is an operational failure, exit 1: while the push
    # was implicit a warning was enough, but a caller that passed --push reads exit 0 as "pushed"
    # (PRINCIPLE-011 R5, ADR-187).
    if getattr(args, "push", False):
        if dirty:
            print("Error: uncommitted changes or unresolved conflicts exist; skipping the push.",
                  file=sys.stderr)
            print("Why: a push must upload the tree the gates verified, not a working copy that "
                  "differs from it.", file=sys.stderr)
            print("Fix: commit or resolve the changes and run `check --strict` before pushing.",
                  file=sys.stderr)
            return 1
        push_code, push_report = auto_push_project(project.path, project.name)
        if push_code != 0:
            print(push_report, file=sys.stderr)
            return 1
        if push_report:
            print(push_report)
        _report_registered_ideas(project.path, project.name)
    return 0



def cmd_push(args: argparse.Namespace) -> int:
    """Gated push: a discoverable alias for `check --push`."""
    return cmd_check(argparse.Namespace(
        name=args.name,
        workspace=args.workspace,
        push=True,
        strict=False,
        no_push=False,
    ))


def cmd_fix(args: argparse.Namespace) -> int:
    """
    Repair what AIKit can repair mechanically, then run the gates: everything left is the
    agent's to fix by hand, guided by each gate's output.
    """
    project = present_project(args.name, args.workspace)
    fixes: List[str] = []
    memory = project.path / ".aikit"
    expected = ["project.json", "guidelines.md", "decisions.md", "task_ledger.json"]
    missing = [name for name in expected if not (memory / name).is_file()]
    write_memory(project.path, project.name, project.test_command)
    fixes += [f"restored .aikit/{name}" for name in missing if (memory / name).is_file()]
    state = license_state(project.path)
    if state.tier == "personal" and state.kind:
        seed_reuse(project.path, state.kind, state.version)
        fixes.append("refreshed REUSE.toml and LICENSES/ metadata")
    if seed_readme(project.path, project.name, project.test_command, integrated=project.attached):
        fixes.append("seeded README.md from the project template (complete it by hand)")
    if migrate_aikit_links(project.path):
        fixes.append("updated the README's pre-move AIKit link")
    fixes += reconcile_readme_tree(project.path)
    fixes += [f"removed stale buffer {rel}" for rel in clean_dangling_temp_files(project.path)]
    if find_python_files(project.path):
        write_generated_file(memory / "codebase_map.md", generate_codebase_map(root=project.path, strict=False))
        fixes.append("regenerated .aikit/codebase_map.md")
    identity = project_ui.auto_ui(project.path)
    fixes.append(f"refreshed UI identifier (has_ui={identity['has_ui']}, kind={identity['kind']})")
    test_command = project.test_command or str(load_config(project.path).get("test_command") or "")
    adoption = project_ui.adopt_ui(project.path, test_command)
    if adoption["adopted"]:
        fixes.append("wrote .aikit/ui.json and marked the UI contract required")
    elif identity["has_ui"]:
        print(f"[WARN] UI contract not adopted: {adoption['reason']}")
    media_file = memory / "media.json"
    if not media_file.is_file():
        try:
            project_media.seed_media_assets(project.path, project.name)
            fixes.append("seeded brand media candidates (.aikit/media.json and assets/)")
        except (ProjectError, OSError, ValueError) as exc:
            print(f"[WARN] Brand media candidates could not be generated: {exc}")
    else:
        try:
            m_data = project_media.load_media(project.path)
            assets = m_data.get("assets") or {}
            approved_shots = [s for s in m_data.get("screenshots") or []
                              if project_media._approved(s)]
            readme_path = project.path / "README.md"
            if readme_path.is_file() and (project_media._approved(assets.get("social_preview"))
                                          or approved_shots):
                readme_text = readme_path.read_text(encoding="utf-8", errors="ignore")
                if "<!-- aegean:media:start -->" not in readme_text:
                    repo = project_media.repository_name(project.name)
                    project_media._update_readme(readme_path, repo, m_data, approved_shots)
                    fixes.append("updated README.md with approved brand media")
        except (ProjectError, OSError, ValueError) as exc:
            # A corrupt or unsupported manifest is the operator's to fix; swallowing it made
            # `fix` report success while the media and README stayed unrepaired (ADR-306).
            print(f"[WARN] Brand media could not be read or written: {exc}")
    for fix in fixes:
        print(f"[FIXED] {fix}")
    print(f"Checking '{project.name}' after {len(fixes)} repair(s):")
    return cmd_check(args)


def cmd_publish(args: argparse.Namespace) -> int:
    project = present_project(args.name, args.workspace)
    # Install the local guard before any refusal: even a failed publish must block a raw retry.
    guard = install_pre_push_hook(project.path, project.name)
    if guard is not None and not is_guard_installed(project.path):
        return report_error(ProjectError(
            f"the publish guard could not be installed in '{project.name}'.",
            "a direct git push would bypass AIKit's publish gates.",
            "check .git/hooks permissions, then publish again.",
            exit_code=1,
        ))
    # A restricted project is not distributed: a public repository would hand it out (ADR-214).
    if args.public and license_state(project.path).tier == TIER_RESTRICTED:
        return report_error(ProjectError(
            f"'{project.name}' is in the restricted tier; publish --public is refused.",
            "a restricted project is All Rights Reserved and must not be made available to the public.",
            "publish it without --public to a private repository, or keep it local.",
            exit_code=2,
        ))
    # An existing origin is pushed as it is, so its visibility must be private too.
    if get_project_repo_url(project.path):
        refusal = public_remote_refusal(project.path, project.name)
        if refusal:
            return report_error(refusal)
    if not project_media.media_path(project.path).is_file():
        # A project without any brand manifest (attached or legacy) cannot be reviewed,
        # so publish seeds local candidates first and then follows the normal review path.
        try:
            project_media.seed_media_assets(project.path, project.name)
            print(f"     Local brand candidates generated for '{project.name}' "
                  "(uncommitted; review before applying).")
        except (ProjectError, OSError, ValueError) as exc:
            return report_error(ProjectError(
                f"'{project.name}' has no brand assets and none could be generated.",
                str(exc),
                f"run `python aikit.py media init {project.name}`, then publish again; "
                "nothing was published.",
            ))
    blockers = project_media.media_blockers(project.path)
    if blockers:
        return report_error(ProjectError(
            f"'{project.name}' has unreviewed brand assets.",
            f"{', '.join(blockers)} must be approved before publication.",
            f"review with `python aikit.py media review {project.name} ...`, then "
            f"`python aikit.py media apply {project.name}`; nothing was published.",
        ))
    # The README's first paragraph is the one description source (ADR-202), so a publish without
    # a usable one would create an undescribed repository (ADR-216). Long text is cut at GitHub's
    # 350-character limit by extraction; too little is refused before any gate runs.
    readme_path = project.path / "README.md"
    try:
        readme_text = readme_path.read_text(encoding="utf-8", errors="replace")
    except OSError:
        readme_text = ""
    if "<FILL:" in readme_text:
        return report_error(ProjectError(
            f"'{project.name}' README still holds the template description placeholder.",
            "the GitHub description comes from the README's first paragraph, and a placeholder "
            "is not a description.",
            "replace the <FILL: ...> paragraph with one sentence of "
            f"{DESCRIPTION_MIN}-{DESCRIPTION_MAX} characters, then publish again.",
            exit_code=2,
        ))
    description = extract_readme_description(project.path)
    if len(description) < DESCRIPTION_MIN:
        return report_error(ProjectError(
            f"'{project.name}' has no usable README description ({len(description)} characters).",
            "the GitHub repository takes its description from the README's first paragraph, and "
            f"a repository description is one line of {DESCRIPTION_MIN}-{DESCRIPTION_MAX} characters.",
            f"write one sentence of {DESCRIPTION_MIN}-{DESCRIPTION_MAX} characters under the README "
            'title, e.g. "A tool that turns X into Y for Z", then publish again.',
            exit_code=2,
        ))
    # The AI chooses the personal license from the project's own markers (ADR-218). `--license
    # auto` applies a high-confidence change and stops: publish uploads commits, so the new
    # LICENSE must be reviewed and committed before the next publish.
    requested_license = getattr(args, "license", "keep")
    suggestion = suggest_license(project.path)
    current = license_state(project.path)
    if requested_license in LICENSE_CHOICES and (
            current.kind != requested_license
            or (current.version and current.version != LICENSE_CHOICES[requested_license]["version"])):
        apply_license_kind(project.path, project.name, requested_license)
        print(f"[LICENSE] '{project.name}' now carries "
              f"{LICENSE_CHOICES[requested_license]['name']}.")
        print("Commit LICENSE and README.md, then publish again; nothing was uploaded.")
        return 1
    if (requested_license == "auto" and suggestion["change_needed"]
            and suggestion["confidence"] == "high"):
        apply_license_kind(project.path, project.name, suggestion["kind"])
        print(f"[LICENSE] The markers select {LICENSE_CHOICES[suggestion['kind']]['name']} "
              f"({'; '.join(suggestion['reasons'])}).")
        print("Commit LICENSE and README.md, then publish again; nothing was uploaded.")
        return 1
    if suggestion["change_needed"]:
        print(f"[LICENSE] Suggested {LICENSE_CHOICES[suggestion['kind']]['key']} "
              f"({suggestion['confidence']} confidence); run `python aikit.py license "
              f"{project.name} --set {suggestion['kind']}` to switch.")
    elif suggestion["upgrade_available"]:
        print(f"[LICENSE] {suggestion['current_version']} -> {suggestion['latest_version']} "
              f"available; run `python aikit.py license {project.name} --set "
              f"{suggestion['kind']}` to upgrade.")
    audit = run_disruption_audit(workspace_dir=project.path)
    errors = project_baseline_errors(project, audit)
    if errors:
        print("[FAIL] the project is not delivery-ready:", file=sys.stderr)
        for error in errors:
            print(f"       {error}", file=sys.stderr)
        print("Why: publish uploads the committed tree; a tree that fails the delivery baseline "
              "must not be published.", file=sys.stderr)
        print("Fix: commit the work, finish or abort any open UI task, add the missing map or "
              "UI contract, then retry the publish.", file=sys.stderr)
        return 1
    results = run_gates(project.path, resolve_gates(project))
    print(f"{sum(1 for result in results if result.passed)}/{len(results)} gates passed before publish.")
    if any(not result.passed for result in results):
        for result in results:
            if not result.passed:
                print(f"[FAIL] {result.gate.name}: {result.gate.command}", file=sys.stderr)
                for line in failure_tail(result.output):
                    print(f"       {line}", file=sys.stderr)
        print("Error: the project's gates failed; publish refuses an unverified tree.",
              file=sys.stderr)
        print("Why: a published commit must carry the same verified tree that check requires.",
              file=sys.stderr)
        print(f"Fix: run `python aikit.py check {project.name}` and repair the failed gates, "
              "then retry the publish.", file=sys.stderr)
        return 1
    if not any(result.gate.name == "test" for result in results):
        print("Error: the project has no test gate.", file=sys.stderr)
        print("Why: publish must not upload a tree without a behavioural test gate.",
              file=sys.stderr)
        print("Fix: write tests, and set `test_command` in .aikit/project.json when it is not "
              "detected.", file=sys.stderr)
        return 1
    # `new` records the topics; a project.json from before ADR-199 has none (ADR-200).
    # Topics are AI-chosen and recorded; uploading with the bare ["aikit"] default would
    # leave the repository effectively untagged (AIKit validates tags, never invents them).
    config = load_config(project.path)
    recorded_topics = list(config.get("topics") or [])
    if {str(topic).strip().lower() for topic in recorded_topics} <= {"aikit"}:
        try:
            brief = project_topics.ai_brief(project.path, project.name, [], [])
            hints = ", ".join(brief.get("hint_tags") or [])
        except (ProjectError, OSError, ValueError):
            hints = ""
        return report_error(ProjectError(
            f"'{project.name}' has no recorded GitHub topics.",
            "the repository would publish with only the fallback 'aikit' tag.",
            f"pick tags{(' (candidates: ' + hints + ')') if hints else ''}, record the choice with "
            f"`python aikit.py topics {project.name} --brief` then `--from-file`, and publish "
            "again; nothing was published.",
        ))
    code, report = publish_project(project.path, project.name, public=args.public,
                                   topics=publish_topics(config.get("topics") or ["aikit"]),
                                   owner=getattr(args, "owner", None), description=description)
    print(report, file=sys.stdout if code == 0 else sys.stderr)
    if code == 0:
        _report_registered_ideas(project.path, project.name)
        _sync_dossier(project.path, project.name)
    return code


def cmd_archive(args: argparse.Namespace) -> int:
    """Move a project to `projects/archive/` and archive its GitHub repository."""
    try:
        project = present_project(args.name, args.workspace)
    except ProjectError as exc:
        if getattr(args, "json", False):
            print(error_envelope(exc))
            return exc.exit_code
        raise
    if is_archived(project.path):
        message = f"project '{project.name}' is already archived at {project.path}."
        if getattr(args, "json", False):
            print(json.dumps({"ok": True, "archived": True, "project": project.name,
                              "path": str(project.path), "note": message}, indent=2))
            return 0
        print(message)
        return 0
    code, report = archive_project(
        project.path, project.name, reason=getattr(args, "reason", ""),
        workspace=args.workspace, to=getattr(args, "to", None),
        description=getattr(args, "description", None),
        offline=bool(getattr(args, "offline", False)),
        allow_dirty=bool(getattr(args, "allow_dirty", False)),
    )
    if getattr(args, "json", False):
        payload = {"ok": code == 0, "project": project.name,
                   "reason": getattr(args, "reason", ""),
                   "offline": bool(getattr(args, "offline", False))}
        if code == 0:
            try:
                moved = present_project(args.name, args.workspace)
                payload.update({"archived": True, "path": str(moved.path)})
            except ProjectError:
                payload.update({"archived": True})
            payload["report"] = report
            print(json.dumps(payload, indent=2, default=str))
        else:
            print(json.dumps({"ok": False, "error": {"code": "project.error",
                                                     "message": report}}, indent=2))
        return code
    print(report, file=sys.stdout if code == 0 else sys.stderr)
    return code


def cmd_license(args: argparse.Namespace) -> int:
    project = present_project(args.name, args.workspace)
    state = license_state(project.path)
    if getattr(args, "json", False) and not getattr(args, "suggest", False):
        return report_error(ProjectError(
            "--json is only meaningful with --suggest.",
            "the tier and --set outputs are human text; an agent needs the suggestion payload.",
            f"run `python aikit.py license {project.name} --suggest --json`.",
            exit_code=2,
        ))
    if getattr(args, "set_kind", None):
        state = apply_license_kind(project.path, project.name, args.set_kind)
        print(f"[OK] '{project.name}' now carries the {LICENSE_CHOICES[state.kind]['name']}.")
        print(f"     Review and commit LICENSE and README.md in {project.path}, then publish.")
        return 0
    suggestion = suggest_license(project.path)
    restricted = state.tier == TIER_RESTRICTED
    if getattr(args, "suggest", False):
        if restricted:
            if getattr(args, "json", False):
                print(json.dumps({"ok": True, "result": {
                    "project": project.name,
                    "tier": state.tier,
                    "set_allowed": False,
                    "current": "restricted",
                    "suggested": None,
                    "current_key": None,
                    "recommended_key": None,
                    "confidence": "n/a",
                    "reasons": [],
                    "alternatives": [],
                    "change_needed": False,
                    "adoptable": False,
                }}, indent=2))
                return 0
            print(f"Project: {project.name}")
            print("Tier:    restricted (All Rights Reserved)")
            print("A restricted project cannot switch to a personal license; use a separate "
                  "written agreement or start a new project.")
            return 0
        if getattr(args, "json", False):
            print(json.dumps({"ok": True, "result": {
                "project": project.name,
                "tier": state.tier,
                "set_allowed": True,
                "current": state.kind or "unrecorded",
                "suggested": suggestion["kind"],
                "current_key": suggestion["current_key"],
                "recommended_key": suggestion["recommended_key"],
                "confidence": suggestion["confidence"],
                "reasons": suggestion["reasons"],
                "alternatives": suggestion["alternatives"],
                "change_needed": suggestion["change_needed"],
                "upgrade_available": suggestion["upgrade_available"],
                "adoptable": suggestion["adoptable"],
                "current_version": suggestion["current_version"],
                "latest_version": suggestion["latest_version"],
            }}, indent=2, default=str))
            return 0
        print(f"Project: {project.name}")
        print(f"Current: {state.kind or 'unrecorded'} {state.version or ''}".rstrip())
        print(f"Suggest: {LICENSE_CHOICES[suggestion['kind']]['key']} "
              f"({suggestion['confidence']} confidence)")
        for reason in suggestion["reasons"]:
            print(f"  - {reason}")
        if suggestion["change_needed"]:
            print(f"Switch with `python aikit.py license {project.name} --set {suggestion['kind']}`.")
        elif suggestion["upgrade_available"]:
            print(f"Upgrade with `python aikit.py license {project.name} --set {suggestion['kind']}` "
                  f"({suggestion['current_version']} -> {suggestion['latest_version']}).")
        elif state.tier == "unrecorded" and suggestion["kind"] != DEFAULT_LICENSE_KIND:
            print(f"This project's own LICENSE is not an Aegean one; adopt "
                  f"{LICENSE_CHOICES[suggestion['kind']]['key']} with "
                  f"`python aikit.py license {project.name} --set {suggestion['kind']}`.")
        else:
            print("No license change is needed.")
        return 0
    already = state.tier == TIER_RESTRICTED
    state = restrict_project(project.path, project.name) if args.restrict else state
    print(f"License tier of '{project.name}': {state.tier}")
    if state.tier != TIER_RESTRICTED:
        print(f"     Kind:    {state.kind or 'unrecorded'} {state.version or ''}".rstrip())
        print(f"     Suggest: {LICENSE_CHOICES[suggestion['kind']]['key']} "
              f"({suggestion['confidence']} confidence)")
        if suggestion["change_needed"]:
            print(f"     Apply with `python aikit.py license {project.name} --set {suggestion['kind']}`.")
        elif suggestion["upgrade_available"]:
            print(f"     Upgrade with `python aikit.py license {project.name} --set "
                  f"{suggestion['kind']}` ({suggestion['current_version']} -> "
                  f"{suggestion['latest_version']}).")
        elif state.tier == "unrecorded" and suggestion["kind"] != DEFAULT_LICENSE_KIND:
            print(f"     This project's own LICENSE is not an Aegean one; adopt "
                  f"{LICENSE_CHOICES[suggestion['kind']]['key']} with "
                  f"`python aikit.py license {project.name} --set {suggestion['kind']}`.")
        if not args.restrict:
            print(f"     Restrict it with `python aikit.py license {project.name} --restrict`.")
        return 0
    cutoff = state.since_commit[:12] if state.since_commit else "an unrecorded commit"
    print(f"     Cutoff: commit {cutoff} on {state.since or 'an unrecorded date'}.")
    print("     Versions up to that commit stay under the license they were released with.")
    if args.restrict and not already:
        print("Next, outside AIKit:")
        print(f"  1. Review and commit LICENSE, README.md and the removed COMMERCIAL.md in {project.path}.")
        print("  2. Make the GitHub repository private: `gh repo edit --visibility private "
              "--accept-visibility-change-consequences`.")
        print("  3. Remove public releases, packages and download links of later versions.")
        print("  4. Tell Aegean Commercial License (ACL-1.0) holders whether later versions are covered.")
    return 0


def _write_project_topics(project: Project, topics: List[str], source: str = "ai") -> List[str]:
    path = config_path(project.path)
    with file_lock(path):
        config = load_config(project.path)
        config["topics"] = topics
        config["topics_source"] = source
        config["topics_reviewed_at"] = time.strftime("%Y-%m-%d")
        atomic_write_json(path, config)
    return topics


def _topic_error(exc: ValueError) -> int:
    return report_error(ProjectError(
        str(exc),
        "AIKit validates the AI's topic choice but never invents the final list.",
        "fix the chosen topics and retry `python aikit.py topics <name> --from-file <file>`.",
        exit_code=2,
    ))


def cmd_topics(args: argparse.Namespace) -> int:
    """Let an AI choose GitHub topics; validate, record and optionally apply them (ADR-236)."""
    project = present_project(args.name, args.workspace)
    config = load_config(project.path)
    if args.set_topics is not None and (args.add or args.remove):
        return report_error(ProjectError(
            "--set replaces the list; --add and --remove edit it.",
            "one mode per call keeps the resulting list predictable.",
            f"use `python aikit.py topics {project.name} --set ...` or `--add`/`--remove`, not both.",
            exit_code=2,
        ))
    if getattr(args, "from_file", None) and (args.set_topics is not None or args.add or args.remove):
        return report_error(ProjectError(
            "--from-file is one complete AI choice and cannot be mixed with --set/--add/--remove.",
            "the choice file is the reviewable artifact; editing it twice hides the real list.",
            f"use `--from-file` alone, or `--set`/`--add`/`--remove` without it.",
            exit_code=2,
        ))
    recorded = list(config.get("topics") or ["aikit"])
    slug = project_topics.repo_slug(project.path, project.name)
    current: List[str] = []
    live_error = ""
    needs_live = bool(getattr(args, "apply", False) or getattr(args, "review", False))
    if needs_live and not getattr(args, "offline", False):
        current, live_error = project_topics.github_topics(slug)

    change_flags = (args.set_topics is not None or args.add or args.remove
                    or getattr(args, "from_file", None) or getattr(args, "apply", False))
    if (args.suggest or getattr(args, "brief", False) or getattr(args, "review", False)) and change_flags:
        return report_error(ProjectError(
            "read-only topic views cannot be combined with a change.",
            "an AI reads the brief or audit, then records a separate deliberate choice.",
            f"run `python aikit.py topics {project.name} --brief` first.",
            exit_code=2,
        ))

    if args.suggest:
        suggestion = suggest_license(project.path)
        state = license_state(project.path)
        restricted = state.tier == TIER_RESTRICTED
        brief = project_topics.ai_brief(project.path, project.name, recorded, current)
        payload = {"project": project.name, "tier": state.tier,
                   "set_allowed": not restricted,
                   "topics": recorded,
                   "domain": None if restricted else suggestion["kind"],
                   "confidence": "n/a" if restricted else suggestion["confidence"],
                   "reasons": [] if restricted else suggestion["reasons"],
                   "recommended_key": None if restricted else suggestion["recommended_key"],
                   "hint_tags": brief["hint_tags"], "brief": brief}
        if getattr(args, "json", False):
            print(json.dumps({"ok": True, "result": payload}, indent=2, default=str))
            return 0
        print(f"Project: {project.name}")
        print(f"Topics:  {', '.join(recorded)}")
        print(f"Possible tags for the AI to consider: {', '.join(brief['hint_tags'])}")
        print("No tag is chosen automatically; use --from-file or --set to record the AI choice.")
        return 0

    if getattr(args, "brief", False):
        brief = project_topics.ai_brief(project.path, project.name, recorded, current)
        payload = {"project": project.name, "slug": slug, "brief": brief,
                   "recorded_topics": recorded, "current_topics": current,
                   "live_error": live_error}
        if getattr(args, "json", False):
            print(json.dumps({"ok": True, "result": payload}, indent=2))
            return 0
        print(f"AI topic brief for '{project.name}' ({slug})")
        print(f"Description: {brief['description'] or '(none)'}")
        print(f"Stacks: {', '.join(brief['stacks']) or 'none detected'}; "
              f"UI: {brief['ui']['has_ui']} ({brief['ui']['kind']})")
        print(f"Recorded: {', '.join(recorded)}")
        print(f"Current:  {', '.join(current) if current else '(unavailable)'}")
        print(f"Possible tags to consider: {', '.join(brief['hint_tags'])}")
        print("Choose the final list and write it as a JSON object with a topics array, then run:")
        print(f"  python aikit.py topics {project.name} --from-file <file> [--apply]")
        return 0

    if getattr(args, "review", False):
        audit = project_topics.topic_audit(current or recorded, recorded)
        result = {"project": project.name, "slug": slug, "audit": audit,
                  "current": current, "recorded": recorded, "live_error": live_error}
        if getattr(args, "json", False):
            print(json.dumps({"ok": True, "result": result}, indent=2))
            return 0
        print(f"Topics for '{project.name}': {len(current or recorded)} used, "
              f"{project_topics.MAX_TOPICS} allowed")
        print(f"  current:  {', '.join(current) if current else '(offline)'}")
        print(f"  recorded: {', '.join(recorded)}")
        for problem in audit["problems"]:
            print(f"  - {problem}")
        if audit["ok"]:
            print("  no policy problem found")
        return 0

    chosen: Optional[List[str]] = None
    explicit_remove: List[str] = []
    replace = False
    if getattr(args, "from_file", None):
        try:
            choice = project_topics.read_choice_file(Path(args.from_file))
        except ValueError as exc:
            return _topic_error(exc)
        chosen = list(choice["topics"])
        explicit_remove = list(choice["remove"])
    elif args.set_topics is not None:
        chosen = list(args.set_topics)
        replace = True
    elif args.add or args.remove:
        chosen = list(args.add or [])
        explicit_remove = [str(item).strip().lower() for item in (args.remove or [])]
    elif getattr(args, "apply", False):
        chosen = []

    if chosen is None:
        if getattr(args, "json", False):
            print(json.dumps({"ok": True, "result": {"project": project.name, "topics": recorded,
                                                     "current": current, "slug": slug}}, indent=2))
        else:
            print(f"Topics for '{project.name}': {', '.join(recorded)}")
            print("Read-only. Use --brief for an AI brief, --from-file for the AI's choice, "
                  "or --review to audit.")
        return 0

    try:
        plan = project_topics.validate_choice(
            project.path, recorded, current, chosen, replace=replace, remove=explicit_remove)
    except ValueError as exc:
        return _topic_error(exc)
    source = "ai" if (getattr(args, "from_file", None) or getattr(args, "brief", False)) else "manual"
    topics = _write_project_topics(project, plan["desired"], source)
    if getattr(args, "apply", False):
        plan["apply"] = project_topics.apply_topics(slug, plan["added"], plan["removed"])
    plan.update({"project": project.name, "slug": slug, "topics": topics,
                 "live_error": live_error})
    if getattr(args, "json", False):
        print(json.dumps({"ok": True, "result": plan}, indent=2))
        return 0
    print(f"[OK] Topics for '{project.name}' ({slug}): {', '.join(topics)}")
    if plan["added"]:
        print(f"     Added:   {', '.join(plan['added'])}")  # noqa: F541
    if plan["removed"]:
        print(f"     Removed: {', '.join(plan['removed'])}")
    if "apply" in plan:
        print(f"     GitHub:  {'applied' if plan['apply']['ok'] else 'partly failed'}")
    else:
        print("     Local only; pass --apply to update GitHub.")
    print("Review and commit .aikit/project.json; the AI chose this list.")
    return 0



def cmd_ui_id(args: argparse.Namespace) -> int:
    """Detect or manually set a project's UI identifier (ADR-233)."""
    project = present_project(args.name, args.workspace)
    if args.set_ui == "auto":
        result = project_ui.auto_ui(project.path)
    elif args.set_ui == "yes":
        result = project_ui.set_ui_manual(project.path, True, args.kind)
    elif args.set_ui == "no":
        result = project_ui.set_ui_manual(project.path, False)
    else:
        result = project_ui.ui_payload(project.path)
    payload = {"project": project.name, **result}
    if getattr(args, "json", False):
        print(json.dumps({"ok": True, "result": payload}, indent=2))
        return 0
    print(f"UI identifier for '{project.name}': has_ui={payload['has_ui']} kind={payload['kind']} "
          f"source={payload.get('source') or 'recorded'}")
    for path in payload.get("evidence") or []:
        print(f"  evidence: {path}")
    print("Used by the media/screenshot pipeline; `--set yes|no` records a manual decision.")
    return 0


def cmd_media(args: argparse.Namespace) -> int:
    """Generate, review and apply brand/screenshot media (ADR-235)."""
    project = present_project(args.name, args.workspace)
    action = args.media_action
    if action == "init":
        project_ui.auto_ui(project.path)
    elif action == "capture":
        project_ui.refresh_ui_identifier(project.path)
    if action == "init":
        if getattr(args, "art", False) and project_artwork.model_key():
            try:
                result = project_artwork.generate_model_brand(
                    project.path, project.name, force=args.force)
            except (ProjectError, OSError, ValueError) as exc:
                print(f"     [WARN] Image-model brand failed: {exc}; "
                      "seeding local candidates instead.", file=sys.stderr)
                result = project_media.seed_media_assets(
                    project.path, project.name, force=args.force, capture_png=args.png)
        elif getattr(args, "art", False):
            try:
                description = extract_readme_description(project.path) or ""
                config = load_config(project.path)
                ui = project_ui.ui_payload(project.path)
                result = project_artwork.generate_brand(
                    project.path, project.name, description=description,
                    tags=config.get("topics") or [], kind=str(ui.get("kind") or "library"),
                    force=args.force, refresh_art=args.force)
            except (ProjectError, OSError, ValueError) as exc:
                print(f"     [WARN] Art-backed brand failed: {exc}; "
                      "seeding local candidates instead.", file=sys.stderr)
                result = project_media.seed_media_assets(
                    project.path, project.name, force=args.force, capture_png=args.png)
        else:
            result = project_media.seed_media_assets(
                project.path, project.name, force=args.force, capture_png=args.png)
    elif action == "status":
        result = project_media.media_status(project.path)
    elif action == "capture":
        result = project_media.capture_screenshot(
            project.path, project.name, url=args.url, viewport=args.viewport, force=args.force)
    elif action == "review":
        result = project_media.review_media(
            project.path, args.kind, args.decision, args.reviewer, args.method,
            args.notes, score=args.score, index=args.index)
    elif action == "apply":
        result = project_media.apply_media(
            project.path, project.name, dossier=args.dossier,
            readme_only=getattr(args, "readme_only", False))
    else:
        result = project_media.audit_media(project.path, dossier=args.dossier)
    if getattr(args, "json", False):
        print(json.dumps({"ok": True, "result": result}, indent=2))
        return 0
    if action == "init":
        if result.get("skipped"):
            print(f"[OK] '{project.name}' already has approved brand assets; nothing regenerated "
                  "(use --force to replace).")
        else:
            assets = result.get("assets") or (["artwork", "logo", "social_preview"]
                                              if result.get("artwork") else [])
            print(f"[OK] Media candidates for '{project.name}': {', '.join(assets)} "
                  f"(has_ui={result.get('has_ui')}, kind={result.get('kind')}); "
                  "review before applying.")
    elif action == "status":
        print(f"Media for '{project.name}' (has_ui={result['has_ui']}):")
        for key, asset in result["assets"].items():
            print(f"  {key}: {asset['status']} {asset['path']}")
        for shot in result["screenshots"]:
            print(f"  screenshot: {shot['status']} {shot['path']} commit={shot['commit']}")
    elif action == "capture":
        print(f"[OK] Captured {result['path']} at commit {result['commit'][:12]}; "
              "status=pending_review.")
    elif action == "review":
        print(f"[OK] {result['kind']} {result['status']}: {result['asset']}")
    elif action == "apply":
        print(f"[OK] Applied approved media for '{project.name}' to {result['repo']} "
              f"({result['screenshots']} screenshot(s)).")
        for path in result["applied"]:
            print(f"  {path}")
        print("Review and commit these files; nothing was pushed.")
    else:
        print(f"Media audit for '{project.name}': {'clean' if result['ok'] else 'problems'}")
        for problem in result["problems"]:
            print(f"  - {problem}")
        print(f"  pending reviews: {result['pending']}; dossier screenshots: "
              f"{result['dossier_screenshots']}")
    return 0


def cmd_reforge(args: argparse.Namespace) -> int:
    """Reach Aegean Reforge through AIKit's registry, gates and persistence."""
    from reforge.cli import dispatch

    target = getattr(args, "target", None)
    project = None
    if args.reforge_action in ("audit", "fix", "run", "review", "analyze", "status",
                               "report", "start", "stop",
                               "resume", "settings", "runs") and target:
        try:
            project = find_project(target, args.workspace)
        except ProjectError:
            project = None
        if project is not None and not project.present:
            raise ProjectError(
                f"Project '{project.name}' is missing at {project.path}.",
                "its folder or .aikit/project.json is gone, so there is no repository to audit.",
                "restore it, or pass a repository path instead of the project name.",
            )
    gate_runner = None
    if getattr(args, "gates", False):
        if project is None:
            raise ProjectError(
                "--gates needs a registered project.",
                "AIKit's gates read a project's .aikit/ memory; a bare path has none.",
                "register the folder with `python aikit.py attach <path>`, then use its name.",
                exit_code=2,
            )

        def gate_runner():
            gates = resolve_gates(project)
            results = run_gates(project.path, gates)
            lines = [f"[{'PASS' if result.passed else 'FAIL'}] {result.gate.name}"
                     + ("" if result.passed else ": " + " | ".join(failure_tail(result.output)[-3:]))
                     for result in results]
            return all(result.passed for result in results), lines

    return dispatch(args, aikit_root=args.workspace,
                    project_root=project.path if project else None,
                    gate_runner=gate_runner)


def cmd_idea_catcher(args: argparse.Namespace) -> int:
    """Reach the private Idea Catcher register that ships with AIKit."""
    from idea_catcher.registry import default_root, run

    args.command = args.idea_catcher_action
    return run(args, default_root())


def cmd_delegate(args: argparse.Namespace) -> int:
    code, report = delegate_subagent(args.role, args.prompt, file=args.file, project_name=args.project,
                                     model=args.model, timeout=args.timeout, output_format=args.format,
                                     workspace=args.workspace)
    print(report, file=sys.stdout if code == 0 else sys.stderr)
    return code


def cmd_ui(args: argparse.Namespace) -> int:
    """Bound a UI task to one declared surface and keep it inside that contract."""
    project = present_project(args.name, args.workspace)
    if args.ui_action == "init":
        contract = ui_contract.scaffold_contract(project.path, args.surface,
                                                 fast=args.fast, paths=args.paths,
                                                 snapshot=args.snapshot)
        command = contract["commands"]["fast"]
        identity = project_ui.refresh_ui_identifier(project.path)
        print(f"[OK] Wrote {ui_contract.CONTRACT_REL} for surface '{args.surface}' "
              f"with fast proof '{command}'. UI identifier: has_ui={identity['has_ui']} "
              f"kind={identity['kind']}. Review and commit it, then run `ui begin`.")
        return 0
    if args.ui_action == "begin":
        task = ui_contract.begin(project.path, args.surface)
        identity = project_ui.refresh_ui_identifier(project.path)
        print(f"[OK] UI task opened on '{args.surface}' from "
              f"{str(task['baseline_commit'])[:12]}; UI identifier: "
              f"has_ui={identity['has_ui']} kind={identity['kind']}.")
        return 0
    if args.ui_action == "allow":
        ui_contract.allow(project.path, args.pattern, args.reason)
        print(f"[OK] Inventory removals matching '{args.pattern}' are intended: {args.reason}")
        return 0
    if args.ui_action in ("verify", "finish"):
        before = None
        if args.ui_action == "finish":
            try:
                before = ui_contract.read_task(project.path)
            except ProjectError:
                before = None
            reviewer = getattr(args, "reviewer", "") or ""
            reviewed = bool(args.reviewed)
            waiver = ui_review_waiver(project.path) if not reviewed else None
            if waiver:
                reviewed = True
                reviewer = reviewer or f"agent:{resolve_agent()}"
                print(f"[NOTE] {_named_guideline(waiver)} waives human UI review; recording "
                      f"the verification as a review by {reviewer}.")
            findings = ui_contract.finish(project.path, reviewed=reviewed, reviewer=reviewer)
        else:
            try:
                findings = ui_contract.verify(project.path)
            except ProjectError as exc:
                if getattr(args, "json", False):
                    print(json.dumps({"ok": False, "surface": None,
                                      "error": {"code": "ui.error", "message": str(exc)}},
                                     indent=2))
                    return getattr(exc, "exit_code", 1)
                raise
        if args.ui_action == "verify":
            contract = ui_contract.load_contract(project.path)
            style_lint = "on" if contract.theme_paths else "off"
        else:
            style_lint = ""
        if args.ui_action == "verify" and getattr(args, "json", False):
            payload = {"ok": not findings, "findings": ui_contract.findings_payload(findings),
                       "style_lint": style_lint}
            try:
                payload["surface"] = ui_contract.read_task(project.path).get("surface")
            except ProjectError:
                payload["surface"] = None
            print(json.dumps(payload, indent=2))
            return 0 if not findings else 1
        if args.ui_action == "verify" and style_lint == "off":
            print("[INFO] style lint: off (no style.theme_paths declared).")
        for finding in findings:
            print(f"[FAIL] {finding}")
        # finish() reports a missing review only after verify() found nothing, so when that is the
        # sole finding the change is inside its contract. The contract advice below would say the
        # opposite and lead with `ui abort`, which reverts valid work. Keyed on the stable finding
        # code, not the message text, so the JSON contract and this branch cannot drift apart.
        if findings and all(ui_contract.finding_code(f) == "ui.review-missing" for f in findings):
            print("Error: the UI change passed verification; only the recorded review is missing.",
                  file=sys.stderr)
            print("Why: a UI task closes only after a person or agent reviewed the running surface.",
                  file=sys.stderr)
            print(f"Fix: look at the running UI, then run `python aikit.py ui finish "
                  f"{project.name} --reviewed` (add --reviewer <name> to record who).",
                  file=sys.stderr)
            return 1
        if findings:
            print("Error: the UI change is outside its contract.", file=sys.stderr)
            print("Why: a UI task proves one reviewed surface, not an unbounded rewrite.",
                  file=sys.stderr)
            print(f"Fix: revert the listed paths, record intended removals with "
                  f"`python aikit.py ui allow {project.name} <pattern> --reason <why>`, or run "
                  f"`python aikit.py ui abort {project.name}` to restore the surface; "
                  "then rerun.", file=sys.stderr)
            if args.ui_action == "finish":
                print("Fix: `ui finish` also needs --reviewed after a review of "
                      "the running UI.", file=sys.stderr)
            return 1
        identity = project_ui.refresh_ui_identifier(project.path)
        print(f"[OK] UI surface verified for '{project.name}'." if args.ui_action == "verify"
              else f"[OK] UI task closed for '{project.name}'.")
        print(f"[OK] UI identifier: has_ui={identity['has_ui']} kind={identity['kind']}.")
        # The closing report names what the task was allowed to remove: an allow decision that is
        # never read back is an unreviewed control loss (ADR-171).
        for entry in ui_contract.allowed_removal_entries(before or {}):
            print(f"[NOTE] allowed removal '{entry['pattern']}': {entry['reason']}")
        return 0
    if args.ui_action == "abort":
        result = ui_contract.abort(project.path)
        if result["backup"]:
            print(f"[OK] Restored {len(result['restored'])} path(s); backup: {result['backup']}")
        else:
            print("[OK] Restored 0 path(s); there was nothing to back up.")
        if result["skipped"]:
            print("[WARN] Left outside the surface: " + ", ".join(result["skipped"]),
                  file=sys.stderr)
        return 0
    info = ui_contract.status(project.path)
    print(f"Surface:  {info['surface']}")
    print(f"Baseline: {str(info['baseline_commit'])[:12]}")
    print(f"Strikes:  {info['strikes']}")
    print("Changed:  " + (", ".join(info["changed"]) if info["changed"] else "none"))
    return 0


HANDLERS = {
    "new": cmd_new,
    "attach": cmd_attach,
    "list": cmd_list,
    "status": cmd_status,
    "resume": cmd_resume,
    "checkpoint": cmd_checkpoint,
    "complete": cmd_complete,
    "clean": cmd_clean,
    "guideline": cmd_guideline,
    "check": cmd_check,
    "push": cmd_push,
    "fix": cmd_fix,
    "publish": cmd_publish,
    "archive": cmd_archive,
    "license": cmd_license,
    "topics": cmd_topics,
    "ui-id": cmd_ui_id,
    "media": cmd_media,
    "reforge": cmd_reforge,
    "idea-catcher": cmd_idea_catcher,
    "delegate": cmd_delegate,
    "ui": cmd_ui,
}


def main(argv: Optional[List[str]] = None) -> int:
    args = build_parser().parse_args(argv)
    try:
        return HANDLERS[args.command](args)
    except ProjectError as error:
        return report_error(error)
    except UnsupportedLedgerVersion as error:
        print(f"[LEDGER VERSION REFUSED] {error}", file=sys.stderr)
        return 1
    except OSError as error:
        return report_error(ProjectError(
            "a filesystem operation failed",
            f"the operating system denied or interrupted it: {error}",
            "check the path permissions and free space, then retry; never delete a state file "
            "that cannot be read.",
        ))
