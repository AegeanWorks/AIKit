"""
Sub-agent delegation: run one OpenCode sub-agent on a bounded brief (ADR-126, ADR-128).

The sub-agent runs as a supervised process with stdin closed and a timeout (PRINCIPLE-011 R5,
PRINCIPLE-015 R2). Its permissions in `.opencode/agents/<role>.md` already deny writing any task
ledger; the ledger check here detects a ledger that changed during the run and reports it, and
never writes the ledger back: another session may have checkpointed during the run, and
overwriting the file would erase that work (PRINCIPLE-006 R6, PRINCIPLE-013).
"""

import json
import re
import shutil
import subprocess
import time
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional, Tuple

from scripts.check_secrets import scrub_text
from scripts.disruption_recovery import ROOT_DIR, workspace_ledger_path
from scripts.project_registry import ProjectError, find_project

AGENTS_DIR = ROOT_DIR / ".opencode" / "agents"
OPENCODE_CONFIG = ROOT_DIR / "opencode.jsonc"
# Providers that run on this machine, so every model they serve costs nothing (ADR-132).
LOCAL_PROVIDERS = ("ollama", "lmstudio")
# Providers whose models in `opencode.jsonc` are only the free-tier ones verified by a live call.
DECLARED_FREE_PROVIDERS = ("gemini",)
# A Windows `.cmd`/`.bat` runs through cmd.exe, which re-parses the command line: a `"` ends the
# quoting so `&` runs a command, and `%VAR%` expands even inside quotes (ADR-194).
SHELL_SCRIPT_SUFFIXES = (".cmd", ".bat")
CMD_META_CHARS = frozenset('"%!^&|<>\r\n')
# The executable an npm shim forwards to: `"%dp0%\node_modules\...\opencode.exe"   %*`.
SHIM_TARGET_RE = re.compile(r'"%~?dp0%?\\?([^"%]+?\.exe)"', re.IGNORECASE)


def load_opencode_config(path: Path = OPENCODE_CONFIG) -> Dict[str, Any]:
    """The OpenCode configuration; its `providers` declare which Gemini models are free-tier."""
    return json.loads(path.read_text(encoding="utf-8"))


def is_free_model(model: str, config: Dict[str, Any]) -> bool:
    """
    Whether `model` (`provider/name`) costs nothing to call: an OpenCode `-free` or OpenRouter
    `:free` model, any local model, or a model `opencode.jsonc` lists under a declared free-tier
    provider. Anything else is treated as paid (PRINCIPLE-012 R8: free models only).
    """
    provider, _, name = model.partition("/")
    # `provider/model#variant`: the variant is not part of the name, so `#-free` frees nothing.
    name = name.partition("#")[0]
    if not provider or not name:
        return False
    if provider in LOCAL_PROVIDERS or name.endswith(("-free", ":free")):
        return True
    if provider in DECLARED_FREE_PROVIDERS:
        return name in config.get("providers", {}).get(provider, {}).get("models", {})
    return False


def subagent_roles(agents_dir: Path = AGENTS_DIR) -> Tuple[str, ...]:
    """The roles OpenCode can run: one per profile in `.opencode/agents/` (the single source)."""
    return tuple(sorted(p.stem for p in agents_dir.glob("*.md")))


def _triad(what: str, why: str, fix: str) -> str:
    return f"Error: {what}\nWhy: {why}\nFix: {fix}"


def opencode_command(runner_bin: str, role: str, prompt: str, file: Optional[str],
                     model: Optional[str]) -> List[str]:
    """The `opencode run` argv for one headless sub-agent call."""
    cmd = [runner_bin, "run", "--standalone", "--format", "json", "--agent", role]
    if file:
        cmd += ["--file", str(file)]
    if model:
        cmd += ["--model", str(model)]
    # `--` ends the options: a brief starting with `--auto` was read as a flag (ADR-194).
    return cmd + ["--", prompt]


def direct_executable(found: str) -> str:
    """
    The program to start for `found`: the executable an npm `.cmd` shim forwards to when it exists,
    so no cmd.exe parses the brief; otherwise `found` itself.
    """
    path = Path(found)
    if path.suffix.lower() not in SHELL_SCRIPT_SUFFIXES:
        return found
    try:
        match = SHIM_TARGET_RE.search(path.read_text(encoding="utf-8", errors="replace"))
    except OSError:
        return found
    target = path.parent / match.group(1) if match else None
    return str(target) if target is not None and target.is_file() else found


def _run_supervised(cmd: List[str], cwd: Path, timeout: int) -> subprocess.CompletedProcess:
    from scripts.dogfood import supervised  # lazy: `aikit --help` stays inside its budget
    with supervised(cmd, cwd) as proc:
        stdout, stderr = proc.communicate(timeout=timeout)
    return subprocess.CompletedProcess(cmd, proc.returncode, stdout or "", stderr or "")


def delegate_subagent(
    role: str,
    prompt: str,
    file: Optional[str] = None,
    project_name: Optional[str] = None,
    model: Optional[str] = None,
    timeout: int = 120,
    output_format: str = "text",
    runner: Optional[Callable[..., subprocess.CompletedProcess]] = None,
    workspace: Path = ROOT_DIR,
) -> Tuple[int, str]:
    """
    Run `role` on `prompt` in AIKit or in project `project_name`; returns (exit code, report).
    `runner(cmd, cwd=, timeout=)` defaults to a supervised OpenCode process (PRINCIPLE-009 R4).
    """
    roles = subagent_roles()
    if role not in roles:
        return 2, _triad(f"unknown subagent role '{role}'.",
                         f"roles are the profiles in .opencode/agents/: {', '.join(roles)}.",
                         'name one of them, e.g. `python aikit.py delegate worker "..."`.')
    if model and not is_free_model(model, load_opencode_config()):
        return 2, _triad(f"'{model}' is not a free model.",
                         "sub-agents run only on free models: OpenCode '-free', OpenRouter ':free', local "
                         "models, or the free-tier Gemini models opencode.jsonc lists (PRINCIPLE-012 R8).",
                         "omit --model to use the role's own free model, or name a free one, e.g. "
                         "gemini/gemini-3.8-flash or opencode/deepseek-v4.1-flash-free.")
    if not prompt.strip():
        return 2, _triad("empty prompt provided.",
                         "a sub-agent needs a bounded brief (PRINCIPLE-008 R6).",
                         "pass the task as a non-empty quoted prompt.")
    target = workspace
    if project_name:
        try:
            target = find_project(project_name, workspace).path
        except ProjectError as exc:
            return exc.exit_code, _triad(str(exc), exc.why, exc.fix)
    if file and not (Path(file) if Path(file).is_absolute() else target / file).exists():
        return 2, _triad(f"target file '{file}' does not exist.",
                         "the sub-agent cannot inspect a file that is not there.",
                         "check the path (relative to the project), or omit --file.")

    runner_bin = "opencode"
    if runner is None:
        found = shutil.which("opencode")
        if not found:
            return 1, _triad("the `opencode` CLI was not found on PATH.",
                             "delegation runs OpenCode sub-agents (PRINCIPLE-009 R6).",
                             "install OpenCode and make `opencode` callable, then retry.")
        runner_bin, runner = direct_executable(found), _run_supervised
        unsafe = sorted(CMD_META_CHARS.intersection(prompt + (file or "") + (model or "")))
        if Path(runner_bin).suffix.lower() in SHELL_SCRIPT_SUFFIXES and unsafe:
            return 1, _triad(f"the brief holds {' '.join(map(repr, unsafe))}, which cmd.exe would "
                             f"interpret: {runner_bin} is a script, not an executable.",
                             "cmd.exe runs a command after a quote and `&`, and expands %VAR% inside "
                             "quotes, so the brief could run commands or leak the environment.",
                             "install OpenCode so its executable is found beside the shim, or "
                             "rephrase the brief without those characters.")

    ledgers = {workspace_ledger_path(workspace), workspace_ledger_path(target)}
    before = {path: path.read_bytes() if path.is_file() else None for path in ledgers}
    started = time.perf_counter()
    try:
        proc = runner(opencode_command(runner_bin, role, prompt, file, model), cwd=target, timeout=timeout)
    except subprocess.TimeoutExpired:
        return 1, _triad(f"subagent timed out after {timeout}s; its process tree was killed.",
                         "an unbounded run holds the session (PRINCIPLE-010 R3).",
                         "narrow the brief (PRINCIPLE-008 R1) or raise --timeout.")
    except OSError as exc:
        return 1, _triad(f"the subagent process could not start: {exc}",
                         "the OpenCode binary failed to launch.",
                         "run `opencode --version` to check the installation.")
    seconds = time.perf_counter() - started

    changed = [path for path, data in before.items()
               if (path.read_bytes() if path.is_file() else None) != data]
    if changed:
        return 1, _triad(f"a task ledger changed during the subagent run: {', '.join(map(str, changed))}",
                         "sub-agents must never write a ledger (PRINCIPLE-008 R6); a parallel session "
                         "may also have checkpointed, so AIKit does not overwrite it.",
                         "compare the file with `git diff`, keep the session's own entries, and remove "
                         "any the sub-agent wrote.")

    # Every report path is scrubbed here, not only inside `answer_text`: the JSON payload and the
    # failure text embed stdout/stderr directly, so a sub-agent could otherwise leak a credential
    # into the caller's context (PRINCIPLE-019 R4/R5, ADR-173, ADR-177).
    safe_stdout, _ = scrub_text(proc.stdout or "")
    safe_stderr, _ = scrub_text(proc.stderr or "")
    if output_format == "json":
        return proc.returncode, json.dumps({
            "status": "success" if proc.returncode == 0 else "error",
            "agent": role,
            "exit_code": proc.returncode,
            "duration_seconds": round(seconds, 3),
            "output": safe_stdout.strip(),
            "ledger_shield": "unmutated",
        }, indent=2)
    if proc.returncode != 0:
        detail = safe_stderr.strip() or safe_stdout.strip() or f"exit code {proc.returncode}"
        return proc.returncode, f"[SUBAGENT ERROR ({role}, {seconds:.1f}s)]\n{detail}"
    return 0, f"[SUBAGENT OK ({role}, {seconds:.1f}s)]\n{answer_text(proc.stdout)}"


def answer_text(stdout: str) -> str:
    """
    The sub-agent's own words from OpenCode's `--format json` event stream: the `text` parts in
    order. The raw stream also holds every tool call and its full output, which cost the lead agent
    tokens for nothing (PRINCIPLE-012). Output that is not that stream is returned unchanged.

    Credential-shaped spans are scrubbed, with no opt-in: the answer reaches the lead agent's
    context and whatever logs it, and a leaked key there is as unrecoverable as one in a commit
    (PRINCIPLE-019 R4, R5; ADR-173).
    """
    texts = []
    for line in stdout.splitlines():
        try:
            event = json.loads(line)
        except ValueError:
            return scrub_text(stdout.strip())[0]
        part = event.get("part") if isinstance(event, dict) else None
        if isinstance(event, dict) and event.get("type") == "text" and isinstance(part, dict):
            texts.append(str(part.get("text", "")))
    return scrub_text("\n".join(texts).strip() or stdout.strip())[0]
