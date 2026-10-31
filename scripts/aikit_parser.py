"""
The `aikit` command-line grammar: its parser and the Why/Fix triad for usage errors.

Kept apart from scripts/aikit_cli.py so `python aikit.py --help` loads argparse and this module
instead of every module the commands use (PRINCIPLE-010 R5, ADR-180). It imports no AIKit module
at top level: ProjectError is imported inside TriadArgumentParser.error, and aikit_cli, which
imports this module and re-exports its names, is never imported here.
"""

import argparse
import sys
from pathlib import Path
from typing import TYPE_CHECKING, NoReturn

if TYPE_CHECKING:
    from scripts.project_registry import ProjectError

# The values scripts/disruption_recovery.py defines, mirrored rather than imported: importing it
# would load the module graph this file exists to avoid. tests/test_kit.py pins both to it.
ROOT_DIR = Path(__file__).resolve().parent.parent
TEMP_STALE_SECONDS = 60


def report_error(error: "ProjectError") -> int:
    """Print the error triad to stderr and return its exit code."""
    print(f"Error: {error}", file=sys.stderr)
    print(f"Why: {error.why}", file=sys.stderr)
    print(f"Fix: {error.fix}", file=sys.stderr)
    return error.exit_code


class TriadArgumentParser(argparse.ArgumentParser):
    """argparse whose usage errors carry Why/Fix like every other AIKit error."""

    def error(self, message: str) -> NoReturn:
        # Imported on the one path that needs it, so `--help` stays light (ADR-180).
        from scripts.project_registry import ProjectError
        self.print_usage(sys.stderr)
        sys.exit(report_error(ProjectError(
            message,
            "the command line does not match any `aikit` command.",
            f"run `{self.prog} --help` to list the valid forms.",
            exit_code=2,
        )))


def build_parser() -> argparse.ArgumentParser:
    parser = TriadArgumentParser(
        prog="python aikit.py",
        description="Create and manage the projects AIKit builds. Each project is its own folder "
                    "and git repository with its memory in .aikit/.",
    )
    # Explicit, never guessed from the working directory: a stray `projects/` folder elsewhere
    # must not become the registry (ADR-128).
    parser.add_argument("--workspace", type=Path, default=ROOT_DIR, metavar="DIR",
                        help="AIKit checkout whose projects/ to use (default: this one; for sandboxes)")
    commands = parser.add_subparsers(dest="command", required=True, parser_class=TriadArgumentParser)

    def project_command(name: str, help_text: str) -> argparse.ArgumentParser:
        sub = commands.add_parser(name, help=help_text)
        sub.add_argument("name", help="project name, as `list` shows it")
        return sub

    new = commands.add_parser("new", help="create projects/<name>/ as a new git repository")
    new.add_argument("name", help="folder name: lowercase letters, digits, '-' or '_'; not a Windows device name such as con or nul")
    new.add_argument("--test", metavar="CMD", help="test command, when it cannot be detected")
    new.add_argument("--description", metavar="TEXT",
                     help="one line of 10-350 characters: the README's first paragraph and the "
                          "GitHub description")
    new.add_argument("--topic", action="append", metavar="TOPIC",
                     help="a GitHub topic, repeatable; 'aikit' is always added")
    new.add_argument("--kind", dest="license_kind", choices=("auto", "software", "game", "science"),
                     default="auto",
                     help="personal license: software (AL-1.1), game (AGL-1.1), science (ASL-1.1); "
                          "auto starts with software and publish can switch later")
    new.add_argument("--publish", action="store_true",
                     help="upload the starter files to GitHub at creation (needs --description); later "
                          "uploads go through `publish` and its gates")
    new.add_argument("--public", action="store_true", help="with --publish: make the GitHub repository public (default: private)")
    new.add_argument("--no-media", action="store_true",
                     help="skip the generated logo/social-preview candidates and media manifest")

    attach = commands.add_parser("attach", help="register an existing project folder and add the AIKit Integrated badge to its README")
    attach.add_argument("path", type=Path, help="the project's top folder")
    attach.add_argument("--name", help="project name (default: the folder name)")
    attach.add_argument("--test", metavar="CMD", help="test command, when it cannot be detected")

    commands.add_parser("list", help="show every project, its stacks and test command")
    status = project_command("status",
                             "a project's task, uncommitted work, latest decision and gates")
    status.add_argument("--exit-code", action="store_true",
                        help="exit 1 when the project is dirty, conflicted, has an open UI task, or cannot be audited")
    status.add_argument("--json", action="store_true",
                        help="print the report as JSON instead of text; `clean` is the --exit-code verdict")
    resume = project_command("resume", "the cold-start report for a project (PRINCIPLE-004 R2)")
    resume.add_argument("--json", action="store_true",
                        help="print the cold-start report as JSON instead of text")

    checkpoint = project_command("checkpoint", "record a checkpoint in the project's ledger")
    checkpoint.add_argument("--task", required=True, help="task ID")
    checkpoint.add_argument("--phase-num", type=int, required=True, choices=[1, 2, 3, 4, 5],
                            help="lifecycle phase 1-5")
    checkpoint.add_argument("--desc", required=True, help="what was done; a plan starts '[1/M]'")
    for field in ("why", "benefits", "risks", "mitigation"):
        checkpoint.add_argument(f"--{field}", default=None,
                                help="impact assessment, required on a task's first plan (PRINCIPLE-007 R6)")
    checkpoint.add_argument("--handoff", default="",
                            help="cold-start packet: 'next: ...' plus optional state, failed, "
                                 "open, evidence, separated by ';' (PRINCIPLE-004 R2)")
    checkpoint.add_argument("--redact", action="store_true",
                            help="record credential-shaped text as [REDACTED] instead of refusing it")

    complete = project_command("complete", "mark the project's active task completed")
    complete.add_argument("--task", required=True, help="the active task's ID")
    # Every ledger write names its agent; another agent's task needs --take-over (ADR-209).
    for sub in (checkpoint, complete):
        sub.add_argument("--agent", metavar="NAME",
                         help="who is writing, e.g. kilo:2 (default: AIKIT_AGENT, else Claude Code's "
                              "session, else 'unidentified')")
        sub.add_argument("--take-over", action="store_true",
                         help="continue a task another agent owns; the ledger records who continued")

    project_command("clean", f"delete the project's temp buffers older than {TEMP_STALE_SECONDS}s")
    guideline = project_command("guideline", "add a rule to the project's guidelines (below the principles)")
    guideline.add_argument("rule", help="the rule, one line")
    guideline.add_argument("--source", required=True, help="where it comes from: user, ADR-NNN or a person")

    check = project_command("check", "run every gate of a project (its Phase 4)")
    # A verification never publishes on its own: push only on request, when push delivery is
    # authorized (PRINCIPLE-018 R4, ADR-185). --no-push is now the default, kept for old scripts.
    delivery = check.add_mutually_exclusive_group()
    delivery.add_argument("--push", action="store_true",
                          help="after every gate passes on a clean tree, push unpushed commits to "
                               "origin (never forced); exit 1 if the push does not happen")
    delivery.add_argument("--no-push", action="store_true",
                          help="the default; kept so existing scripts still run")
    check.add_argument("--strict", action="store_true",
                       help="require a clean non-bookkeeping tree and a codebase map before passing")
    project_command("fix", "restore missing project memory and README, refresh its map, then check")
    publish = project_command("publish", "upload the project to its own GitHub repository, named in "
                                         "catalog title case (private by default)")
    publish.add_argument("--public", action="store_true", help="create the repository as public")
    publish.add_argument("--owner", metavar="ORG", help="create the repository under this organization "
                         "or user instead of your own account (ADR-215)")
    publish.add_argument("--license", choices=("keep", "auto", "software", "game", "science"),
                         default="auto",
                         help="with auto (default), apply the high-confidence license the project's "
                              "markers select and stop so it can be committed; keep leaves LICENSE unchanged")

    license_cmd = project_command("license", "show or choose the project's license (ADR-214, ADR-218)")
    license_mode = license_cmd.add_mutually_exclusive_group()
    license_mode.add_argument("--restrict", action="store_true",
                              help="make later versions All Rights Reserved from the current commit; "
                                   "earlier releases keep their license")
    license_mode.add_argument("--suggest", action="store_true",
                              help="show the license the project's markers recommend")
    license_mode.add_argument("--set", dest="set_kind", choices=("software", "game", "science"),
                              help="switch the personal license: software (AL-1.1), game (AGL-1.1), "
                                   "science (ASL-1.1)")
    license_cmd.add_argument("--json", action="store_true",
                             help="with --suggest, print one machine-readable suggestion object")

    topics_cmd = project_command("topics", "show or set the GitHub topics a project records")
    topics_cmd.add_argument("--suggest", action="store_true",
                            help="show an AI brief and the current/recorded tags (read-only)")
    topics_cmd.add_argument("--brief", action="store_true",
                            help="print the bounded brief an AI agent uses to choose tags (read-only)")
    topics_cmd.add_argument("--review", action="store_true",
                            help="audit current/recorded topics without choosing anything (read-only)")
    topics_cmd.add_argument("--from-file", dest="from_file", metavar="JSON",
                            help="record the AI's chosen topics from a JSON file")
    topics_cmd.add_argument("--set", dest="set_topics", nargs="*", metavar="TOPIC",
                            help="record an explicit AI/user topic choice; 'aikit' is always added")
    topics_cmd.add_argument("--add", action="append", metavar="TOPIC",
                            help="add one topic to the recorded choice")
    topics_cmd.add_argument("--remove", action="append", metavar="TOPIC",
                            help="remove one topic from the recorded choice")
    topics_cmd.add_argument("--apply", action="store_true",
                            help="apply the recorded/chosen topics on GitHub")
    topics_cmd.add_argument("--offline", action="store_true",
                            help="do not read the live GitHub topics")
    topics_cmd.add_argument("--json", action="store_true",
                            help="print one machine-readable object instead of text")

    ui_id = project_command("ui-id", "detect or set whether a project has a screenshotable UI (ADR-233)")
    ui_id.add_argument("--set", dest="set_ui", choices=("auto", "yes", "no"), default=None,
                       help="write a manual yes/no, or auto to re-detect; default: show")
    ui_id.add_argument("--kind", choices=("web", "desktop", "game", "mobile", "cli", "library", "service"),
                       help="with --set yes, override the detected interface kind")
    ui_id.add_argument("--json", action="store_true", help="print one machine-readable object")

    media = commands.add_parser("media", help="generate, review and apply project logos, social previews and screenshots")
    media_commands = media.add_subparsers(dest="media_action", required=True,
                                          parser_class=TriadArgumentParser)
    media_init = media_commands.add_parser("init", help="generate candidate logo/social assets and .aikit/media.json")
    media_init.add_argument("name", help="project name, as `list` shows it")
    media_init.add_argument("--force", action="store_true", help="regenerate candidates in place")
    media_init.add_argument("--png", action="store_true", help="also render the 1280x640 social preview PNG")
    media_init.add_argument("--art", action="store_true",
                            help="use the image model for unique hero artwork, then compose exact text (ADR-239)")
    media_init.add_argument("--json", action="store_true")
    media_status_cmd = media_commands.add_parser("status", help="show asset and screenshot review states")
    media_status_cmd.add_argument("name")
    media_status_cmd.add_argument("--json", action="store_true")
    media_capture = media_commands.add_parser("capture", help="capture a UI project at HEAD for review")
    media_capture.add_argument("name")
    media_capture.add_argument("--url", help="local index.html/HTML entry point (default: detected)")
    media_capture.add_argument("--viewport", default="1440x900", metavar="WxH")
    media_capture.add_argument("--force", action="store_true", help="replace today's capture deliberately")
    media_capture.add_argument("--json", action="store_true")
    media_review = media_commands.add_parser("review", help="record a vision or structural review decision")
    media_review.add_argument("name")
    media_review.add_argument("--kind", required=True,
                              choices=("logo", "social_preview", "social_preview_png", "screenshot"))
    media_review.add_argument("--decision", required=True, choices=("approve", "reject"))
    media_review.add_argument("--reviewer", required=True,
                              help="agent:<id>, subagent:<id> or human:<id>")
    media_review.add_argument("--method", choices=("vision", "structural"), default="structural")
    media_review.add_argument("--notes", required=True, help="what was checked and why it fits")
    media_review.add_argument("--score", type=int, help="optional 0-100 quality score")
    media_review.add_argument("--index", type=int, help="1-based screenshot index (default: latest)")
    media_review.add_argument("--json", action="store_true")
    media_apply = media_commands.add_parser("apply", help="copy approved assets to README and the AegeanWorks dossier")
    media_apply.add_argument("name")
    media_apply.add_argument("--dossier", type=Path, help="AegeanWorks project root")
    media_apply.add_argument("--json", action="store_true")
    media_audit = media_commands.add_parser("audit", help="verify files, commit stamps, README and dossier links")
    media_audit.add_argument("name")
    media_audit.add_argument("--dossier", type=Path)
    media_audit.add_argument("--json", action="store_true")

    ui = commands.add_parser("ui", help="bound edits to one UI surface declared in .aikit/ui.json")
    ui_commands = ui.add_subparsers(dest="ui_action", required=True, parser_class=TriadArgumentParser)
    for action, text in (("init", "write a UI contract (React/Vite auto, or --fast/--paths)"),
                         ("begin", "open a bounded task from a clean green baseline"),
                         ("verify", "check scope, budget, the fast and snapshot proofs, style"),
                         ("finish", "verify, then close the task (needs --reviewed)"),
                         ("allow", "record an intended inventory removal pattern"),
                         ("abort", "restore only the surface to its baseline"),
                         ("status", "show the open task and its changed paths")):
        sub = ui_commands.add_parser(action, help=text)
        sub.add_argument("name", help="project name, as `list` shows it")
        if action == "begin":
            sub.add_argument("--surface", required=True,
                             help="surface name declared in .aikit/ui.json")
        if action == "init":
            sub.add_argument("--surface", default="app",
                             help="surface name for the generated contract")
            sub.add_argument("--fast", default="",
                             help="manual proof command for a non-React/Vite stack")
            sub.add_argument("--paths", action="append", default=None,
                             help="surface path pattern for a manual contract; repeatable")
            sub.add_argument("--snapshot", default="",
                             help="optional inventory command for a manual contract")
        if action == "allow":
            sub.add_argument("pattern",
                             help="glob matching the inventory entries this task removes")
            sub.add_argument("--reason", required=True,
                             help="why the removal is intended; recorded with the allow entry")
        if action == "finish":
            sub.add_argument("--reviewed", action="store_true",
                             help="confirm a human looked at the running UI")
            sub.add_argument("--reviewer", metavar="NAME",
                             help="who reviewed the running UI, recorded in the task history")
        if action == "verify":
            sub.add_argument("--json", action="store_true",
                             help="emit stable finding codes as JSON for CI")


    reforge = commands.add_parser("reforge", help="audit Git history in 3/6/9 stages and repair "
                                                  "evidence-backed findings (Aegean Reforge)")
    idea = commands.add_parser("idea-catcher", help="validate, render and review the Idea Catcher "
                                                    "register shipped in idea_catcher/")
    reforge_commands = reforge.add_subparsers(dest="reforge_action", required=True,
                                              parser_class=TriadArgumentParser)
    from reforge.cli import add_commands as add_reforge_commands
    add_reforge_commands(reforge_commands)
    idea_commands = idea.add_subparsers(dest="idea_catcher_action", required=True,
                                        parser_class=TriadArgumentParser)
    from idea_catcher.registry import add_commands as add_idea_catcher_commands
    add_idea_catcher_commands(idea_commands)

    delegate = commands.add_parser("delegate", help="run an OpenCode sub-agent on a bounded brief")
    delegate.add_argument("role", help="a profile name in .opencode/agents/")
    delegate.add_argument("prompt", help="the brief for the sub-agent, always sent as the message; "
                                         "exit 1 if only a .cmd shim is found and the brief holds "
                                         "characters cmd.exe would interpret")
    delegate.add_argument("--file", "-f", default=None, help="file to attach to the brief")
    delegate.add_argument("--project", "-p", default=None, help="run inside this registered project")
    delegate.add_argument("--model", "-m", default=None, help="model ID, e.g. ollama/qwen2.5-coder")
    delegate.add_argument("--timeout", type=int, default=120, help="seconds before the run is killed")
    delegate.add_argument("--format", choices=["text", "json"], default="text", help="report format")
    return parser
