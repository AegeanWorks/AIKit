"""
Project gates: the checks a project's own configuration declares, run as its Phase 4 (ADR-122).

A gate is a named shell command run in the project folder. The test gate comes from stack
detection or `test_command`; further gates are detected only from configuration the project
already has (a `[tool.ruff]` table, a `lint` script, a Go module), never guessed. The project's
`.aikit/project.json` may add or replace a gate in its `gates` map, or disable a detected one
with `null`. The hygiene scan, the guidelines check and the secret scan are built in, run on every check, and
cannot be replaced (ADR-137).
"""

import hashlib
import shlex
import subprocess
import sys
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Callable, Dict, List, Optional, Tuple, Union

from scripts.disruption_recovery import ROOT_DIR
from scripts.dogfood import supervised
from scripts.project_registry import (
    Project,
    ProjectError,
    load_config,
    node_runner,
    node_scripts,
)

SECRETS_CLI = ROOT_DIR / "scripts" / "check_secrets.py"
SECRETS_GATE = "secrets"
HYGIENE_CLI = ROOT_DIR / "scripts" / "check_project_hygiene.py"
HYGIENE_GATE = "hygiene"
UPDATE_KB_CLI = ROOT_DIR / "scripts" / "update_knowledge_base.py"
GUIDELINES_GATE = "guidelines"
# One gate may build and test a whole project; past this it is treated as hung.
GATE_TIMEOUT_SECONDS = 1800
# Lines of a failing gate's output shown (PRINCIPLE-012 R7: terse, the end holds the error).
FAILURE_TAIL_LINES = 20
# A tracked-file snapshot is one bounded git call plus hashing only the dirty files.
SNAPSHOT_TIMEOUT_SECONDS = 30
SNAPSHOT_CHUNK_BYTES = 1 << 20
REWRITE_LIST_LIMIT = 5


def _tracked_snapshot(root: Path) -> Optional[Dict[str, str]]:
    """Content hashes of the dirty tracked files, or None when git cannot answer.

    The porcelain status lists only dirty files, so clean files cost nothing; hashing
    catches editing an already-dirty file again, which the status text alone would miss.
    Untracked files are never snapshotted: build output is not a rewrite. None is a
    documented default (non-git project, git missing): no observation, no verdict.
    """
    try:
        status = subprocess.run(
            ["git", "status", "--porcelain=v1", "-z", "--untracked-files=no"],
            cwd=str(root), capture_output=True, text=True, encoding="utf-8",
            errors="replace", timeout=SNAPSHOT_TIMEOUT_SECONDS,
        )
    except (OSError, subprocess.SubprocessError):
        return None
    if status.returncode != 0:
        return None
    paths: List[str] = []
    fields = status.stdout.split("\0")
    index = 0
    while index < len(fields):
        entry = fields[index]
        index += 1
        if not entry:
            continue
        paths.append(entry[3:])
        if entry[0] in "RC" or entry[1] in "RC":
            # Rename/copy in -z order: the next field is the source path, which shares
            # no status prefix and must not be hashed as entry[3:].
            index += 1
    snapshot: Dict[str, str] = {}
    for relative in paths:
        try:
            digest = hashlib.sha256()
            with (root / relative).open("rb") as handle:
                while chunk := handle.read(SNAPSHOT_CHUNK_BYTES):
                    digest.update(chunk)
            snapshot[relative] = digest.hexdigest()
        except OSError:
            snapshot[relative] = "<unreadable>"
    return snapshot


def _rewritten_paths(before: Optional[Dict[str, str]],
                     after: Optional[Dict[str, str]]) -> List[str]:
    """Tracked paths whose content identity changed between two snapshots."""
    if before is None or after is None:
        return []
    return sorted(path for path in set(before) | set(after)
                  if before.get(path) != after.get(path))


@dataclass(frozen=True)
class Gate:
    """A named check and the shell command that runs it; `source` says where it came from."""

    name: str
    command: str
    source: str


@dataclass(frozen=True)
class GateResult:
    """One gate's outcome; `returncode` is -1 when the gate could not start or timed out."""

    gate: Gate
    returncode: int
    seconds: float
    output: str

    @property
    def passed(self) -> bool:
        return self.returncode == 0


def _python_gates(root: Path) -> List[Tuple[str, str]]:
    pyproject = root / "pyproject.toml"
    text = pyproject.read_text(encoding="utf-8", errors="replace") if pyproject.exists() else ""
    gates = []
    if (root / "ruff.toml").exists() or (root / ".ruff.toml").exists() or "[tool.ruff" in text:
        gates.append(("lint", "python -m ruff check ."))
    if (root / "mypy.ini").exists() or "[tool.mypy" in text:
        gates.append(("typecheck", "python -m mypy ."))
    return gates


def _node_gates(root: Path) -> List[Tuple[str, str]]:
    scripts = node_scripts(root)
    runner = node_runner(root)
    return [(name, f"{runner} run {name}") for name in ("lint", "typecheck", "build") if name in scripts]


def _go_gates(root: Path) -> List[Tuple[str, str]]:
    return [("vet", "go vet ./...")]


# Gates beyond the test command, by stack: each detected only from the project's own config.
# A stack without an entry contributes its test gate only (PRINCIPLE-009 R3: lookup, not if-chain).
EXTRA_GATES: Dict[str, Callable[[Path], List[Tuple[str, str]]]] = {
    "python": _python_gates,
    "node": _node_gates,
    "go": _go_gates,
}


def guidelines_gate(project_root: Path) -> Gate:
    """The built-in guidelines and quality scan of the project's repository."""
    argv = [sys.executable, str(UPDATE_KB_CLI), "--workspace", str(project_root), "--check"]
    command = subprocess.list2cmdline(argv) if sys.platform == "win32" else shlex.join(argv)
    return Gate(GUIDELINES_GATE, command, "built-in")


def hygiene_gate(project_root: Path) -> Gate:
    """The built-in hygiene scan of the project's source and static assets (ADR-137)."""
    argv = [sys.executable, str(HYGIENE_CLI), "--workspace", str(project_root)]
    command = subprocess.list2cmdline(argv) if sys.platform == "win32" else shlex.join(argv)
    return Gate(HYGIENE_GATE, command, "built-in")


def secrets_gate(project_root: Path) -> Gate:
    """The built-in secret scan of the project's repository."""
    argv = [sys.executable, str(SECRETS_CLI), "--workspace", str(project_root)]
    command = subprocess.list2cmdline(argv) if sys.platform == "win32" else shlex.join(argv)
    return Gate(SECRETS_GATE, command, "built-in")


def resolve_gates(project: Project) -> List[Gate]:
    """
    The project's gates in run order: test, detected extras, `gates` overrides, hygiene,
    guidelines, secret scan.
    Two stacks detecting the same gate name keep the first; an override names the gate it means.
    """
    gates: Dict[str, Gate] = {}
    if project.test_command:
        gates["test"] = Gate("test", project.test_command, "detected")
    for stack in project.stacks:
        for name, command in EXTRA_GATES.get(stack.name, lambda root: [])(project.path):
            gates.setdefault(name, Gate(name, command, f"detected ({stack.name})"))
    config = load_config(project.path)
    overrides = config.get("gates", {})
    mechanics = config.get("mechanics")
    if isinstance(mechanics, dict):
        command = mechanics.get("test")
        if isinstance(command, str) and command.strip():
            gates.setdefault("mechanics", Gate("mechanics", command.strip(), "project.json"))
    if not isinstance(overrides, dict):
        raise ProjectError(
            f"{project.path / '.aikit' / 'project.json'}: 'gates' is not a mapping.",
            "`gates` maps a gate name to its command, or to null to disable a detected gate.",
            'write it as e.g. "gates": {"lint": "npm run lint", "build": null}.',
        )
    for name, command in overrides.items():
        if name in (SECRETS_GATE, GUIDELINES_GATE, HYGIENE_GATE):
            raise ProjectError(
                f"project.json may not override the '{name}' gate.",
                f"the {name} gate guards every commit and cannot be replaced.",
                f"remove '{name}' from `gates`.",
            )
        if command is None:
            gates.pop(name, None)
        elif isinstance(command, str) and command.strip():
            gates[name] = Gate(name, command, "project.json")
        else:
            raise ProjectError(
                f"project.json gate '{name}' is neither a command nor null.",
                "each gate is one shell command run in the project folder.",
                f'set "{name}" to a command string, or to null to disable it.',
            )
    return [*gates.values(), hygiene_gate(project.path), guidelines_gate(project.path),
            secrets_gate(project.path)]


def run_shell(command: str, cwd: Path, timeout: float) -> Tuple[int, str]:
    """
    Run `command` through the platform shell with stdin closed; on timeout the whole process
    tree is killed (PRINCIPLE-015 R2). Returns (exit code, combined output); -1 when it could
    not start or timed out.
    """
    # `cmd /c` runs only the first line of a command and reports that line's exit code, so
    # "exit 0\nexit 7" passed on Windows while /bin/sh returned 7: a gate that skipped its own
    # steps. Refused on every platform, before anything starts, so a project behaves the same on
    # all of them; a trailing newline is not a second step and still runs (ADR-183).
    if "\n" in command.strip() or "\r" in command.strip():
        return -1, ("refused: the command contains a line break, and Windows cmd runs only its "
                    "first line while reporting success for the rest. Join the steps with && (or "
                    "put them in a script) so every platform runs all of them.")
    # A JSON "\u0000" escape decodes to NUL; no process can receive one, and Popen raised an
    # uncaught ValueError, so `aikit check` ended in a traceback (ADR-189).
    if "\0" in command:
        return -1, ("refused: the command contains a NUL character, which no shell can run; "
                    "remove the \\u0000 escape from its configuration.")
    # Windows gets one command line: `list2cmdline` would backslash-escape the command's own
    # quotes, which cmd does not understand; `/s` makes cmd strip only the outer pair.
    shell: Union[str, List[str]] = (f'cmd /d /s /c "{command}"' if sys.platform == "win32"
                                    else ["/bin/sh", "-c", command])
    try:
        with supervised(shell, cwd) as proc:
            try:
                out, err = proc.communicate(timeout=timeout)
            except subprocess.TimeoutExpired:
                return -1, f"timed out after {timeout:.0f}s; the process tree was killed"
    except OSError as exc:
        return -1, f"could not start: {exc}"
    return proc.returncode, (out or "") + (err or "")


def run_gates(project_root: Path, gates: List[Gate],
              runner: Optional[Callable[[str, Path, float], Tuple[int, str]]] = None,
              timeout: float = GATE_TIMEOUT_SECONDS,
              snapshotter: Optional[Callable[[Path], Optional[Dict[str, str]]]] = None
              ) -> List[GateResult]:
    """Run every gate, even after a failure, so one report lists all of them.

    A gate that rewrites tracked files fails even when its command exits 0: a check
    that edits the tree is not a check (IDEA-1117). The snapshot is content hashes,
    so touching an already-dirty file is caught; untracked build output is ignored.
    """
    runner = runner or run_shell
    snapshot = snapshotter or _tracked_snapshot
    results = []
    for gate in gates:
        before = snapshot(project_root)
        start = time.perf_counter()
        code, output = runner(gate.command, project_root, timeout)
        elapsed = time.perf_counter() - start
        rewritten = _rewritten_paths(before, snapshot(project_root))
        if rewritten:
            shown = ", ".join(rewritten[:REWRITE_LIST_LIMIT])
            if len(rewritten) > REWRITE_LIST_LIMIT:
                shown += ", ..."
            output += (f"\n[REWRITE] gate '{gate.name}' rewrote tracked files: {shown}. "
                       "Why: a check that edits the tree is not a check. "
                       "Fix: run the command's write step outside the gate, or point the gate "
                       "at a copy.")
            if code == 0:
                code = 1
        results.append(GateResult(gate, code, elapsed, output))
    return results


def failure_tail(output: str, lines: int = FAILURE_TAIL_LINES) -> List[str]:
    """The last `lines` non-empty lines of a gate's output, where its error normally is."""
    return [line for line in output.splitlines() if line.strip()][-lines:]
