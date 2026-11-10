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
import json
import shlex
import shutil
import subprocess
import sys
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Callable, Dict, List, Optional, Tuple, Union

from scripts.disruption_recovery import ROOT_DIR, atomic_write_json, file_lock
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
COMPAT_CLI = ROOT_DIR / "scripts" / "project_compat.py"
COMPAT_GATE = "compat"
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
    """One gate's outcome; `returncode` is -1 when the gate could not start or timed out.

    `kind` names the failure class so a caller can tell an assertion from a timeout, a
    missing tool or a lock collision: pass, assertion, timeout, infra, rewrite, lock.
    `attempts` records a timeout-only retry (dogfood already retries rc=124).
    """

    gate: Gate
    returncode: int
    seconds: float
    output: str
    kind: str = "pass"
    attempts: int = 1
    cached: bool = False

    @property
    def passed(self) -> bool:
        return self.returncode == 0

    def action_hint(self) -> str:
        """One line naming the next action for this failure class."""
        if self.passed:
            return ""
        return {
            "timeout": "raise the gate timeout or reduce its work; the tree was not verified",
            "infra": "fix the environment (disk, permissions, a missing tool), then rerun",
            "lock": "another check or build is running in this project; wait, then rerun",
            "rewrite": "the gate edited the tree; run its write step outside the gate",
        }.get(self.kind, "read the failure tail above and fix its cause")


def _classify_failure(code: int, output: str) -> str:
    """The failure class of a finished gate, from its exit code and output."""
    if code == 0:
        return "pass"
    if code == 124 or "timed out after" in output:
        return "timeout"
    lowered = output.lower()
    if any(marker in lowered for marker in (
            "no space left", "not enough free space", "not enough free", "permission denied",
            "access is denied", "could not start:", "not recognized as an internal or external",
            "no such file or directory", "enoent")):
        return "infra"
    return "assertion"


def disk_free_mb(path: Path) -> Optional[float]:
    """Free megabytes under `path`, or None when the platform cannot report it."""
    try:
        return shutil.disk_usage(path).free / (1024 * 1024)
    except OSError:
        return None


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


def compat_gate(project_root: Path) -> Gate:
    """The built-in AI-compat proof for generated projects (ADR-315)."""
    argv = [sys.executable, str(COMPAT_CLI), "--verify", "--root", str(project_root)]
    command = subprocess.list2cmdline(argv) if sys.platform == "win32" else shlex.join(argv)
    return Gate(COMPAT_GATE, command, "built-in")


def resolve_gates(project: Project) -> List[Gate]:
    """
    The project's gates in run order: test, detected extras, mechanics test/bench,
    `gates` overrides, hygiene, guidelines, secret scan, compat.
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
        bench = mechanics.get("bench")
        if isinstance(bench, str) and bench.strip():
            gates.setdefault("bench", Gate("bench", bench.strip(), "project.json"))
    if not isinstance(overrides, dict):
        raise ProjectError(
            f"{project.path / '.aikit' / 'project.json'}: 'gates' is not a mapping.",
            "`gates` maps a gate name to its command, or to null to disable a detected gate.",
            'write it as e.g. "gates": {"lint": "npm run lint", "build": null}.',
        )
    for name, command in overrides.items():
        if name in (SECRETS_GATE, GUIDELINES_GATE, HYGIENE_GATE, COMPAT_GATE):
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
    # A project's canonical machine result may replace the gates it already wraps (ADR-406
    # follow-up): `gates.verify` runs once and the named detected gates are suppressed. The
    # built-in scans below can never be replaced or suppressed.
    if "verify" in gates:
        replaced = config.get("replace_detected", [])
        if not isinstance(replaced, list) or not all(isinstance(name, str) for name in replaced):
            raise ProjectError(
                f"{project.path / '.aikit' / 'project.json'}: 'replace_detected' is not a list of gate names.",
                "`gates.verify` replaces the detected gates it already runs.",
                'write it as e.g. "replace_detected": ["test", "lint", "typecheck", "build"].',
            )
        for name in replaced:
            gates.pop(name, None)
    built = [hygiene_gate(project.path), guidelines_gate(project.path),
             secrets_gate(project.path)]
    if (project.path / ".aikit" / "compat.json").is_file():
        built.append(compat_gate(project.path))
    return [*gates.values(), *built]


def verify_gate_warnings(project: Project) -> List[str]:
    """Warnings when a project's canonical verify command is not the one governing the check."""
    try:
        config = load_config(project.path)
    except (OSError, ValueError, KeyError, ProjectError):
        return []
    overrides = config.get("gates")
    if not isinstance(overrides, dict):
        return []
    verify = overrides.get("verify")
    warnings: List[str] = []
    if isinstance(verify, str) and verify.strip():
        replaced = config.get("replace_detected") or []
        try:
            detected = {gate.name for gate in resolve_gates(project)
                        if gate.source.startswith("detected") and gate.name != "verify"}
        except ProjectError:
            return []
        duplicates = sorted(detected - {str(name) for name in replaced})
        if duplicates and not replaced:
            warnings.append(
                "gates.verify is configured but replace_detected is empty; the check also runs "
                f"{', '.join(duplicates)}. Add them to replace_detected or remove the duplicates.")
    elif "verify" in node_scripts(project.path):
        warnings.append(
            "package.json declares a 'verify' script but it is not a gate; add "
            '"gates": {"verify": "npm run verify"} or keep the detected gates.')
    return warnings


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


# The free-space floor a disk-sensitive gate needs before it starts. One constant so the
# gate preflight and the compat replay cannot disagree about "enough room".
DEFAULT_MIN_FREE_MB = 10.0

DEPENDENCY_MANIFESTS = (
    "package.json", "package-lock.json", "npm-shrinkwrap.json", "yarn.lock", "pnpm-lock.yaml",
    "pyproject.toml", "poetry.lock", "requirements.txt", "requirements-dev.txt",
    "Pipfile.lock", "uv.lock", "Cargo.lock", "go.sum", "composer.lock", "Gemfile.lock",
)


def dependency_digest(project_root: Path) -> str:
    """A digest of the dependency manifests, so an install invalidates a cached pass.

    `git status` cannot see a dependency install inside an ignored directory (`.venv/`,
    `node_modules/`), so a pass earned before `pip install`/`npm ci` would otherwise stay
    valid for a tree whose dependencies changed. Hashing the manifests closes that.
    """
    parts: List[str] = []
    for name in DEPENDENCY_MANIFESTS:
        path = Path(project_root) / name
        try:
            stat = path.stat()
        except OSError:
            continue
        parts.append(f"{name}\0{stat.st_size}\0{stat.st_mtime_ns}")
    return hashlib.sha256("\n".join(parts).encode("utf-8")).hexdigest()


def _cache_file(cache_dir: Path, tree_key: str, gate: Gate, project_root: Path) -> Path:
    """One gate result's content-addressed path for a clean tree and its dependencies."""
    material = "\0".join(("gates-v2", tree_key, dependency_digest(project_root),
                          str(project_root.resolve()),
                          gate.name, gate.command, sys.version, sys.platform))
    return cache_dir / (hashlib.sha256(material.encode("utf-8")).hexdigest() + ".json")


def _cached_pass(cache_path: Path) -> Optional[GateResult]:
    """The cached pass for this gate, or None when absent, unreadable or not a pass."""
    try:
        payload = json.loads(cache_path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return None
    if payload.get("schema") != 1 or not payload.get("passed"):
        return None
    gate = Gate(str(payload.get("gate", "")), str(payload.get("command", "")), "cache")
    return GateResult(gate, 0, 0.0, str(payload.get("output", "")),
                      kind="pass", cached=True)


def _store_pass(cache_path: Path, gate: Gate, output: str) -> None:
    """Record a pass; only a pass is ever cached, so a failure can never hide a fix."""
    atomic_write_json(cache_path, {"schema": 1, "gate": gate.name, "command": gate.command,
                                   "passed": True, "output": output[-4000:]})


def run_gates(project_root: Path, gates: List[Gate],
              runner: Optional[Callable[[str, Path, float], Tuple[int, str]]] = None,
              timeout: float = GATE_TIMEOUT_SECONDS,
              snapshotter: Optional[Callable[[Path], Optional[Dict[str, str]]]] = None,
              lock_path: Optional[Path] = None,
              lock_timeout: float = 30.0,
              retry_timeouts: bool = False,
              min_free_mb: float = 0.0,
              free_space: Optional[Callable[[Path], Optional[float]]] = None,
              cache_dir: Optional[Path] = None,
              tree_key: Optional[str] = None
              ) -> List[GateResult]:
    """Run every gate, even after a failure, so one report lists all of them.

    A gate that rewrites tracked files fails even when its command exits 0: a check
    that edits the tree is not a check (IDEA-1117). The snapshot is content hashes,
    so touching an already-dirty file is caught; untracked build output is ignored.

    `lock_path` serializes two runs on the same project (a build and a check sharing
    `build/` otherwise report a raw compiler error as a test failure). A timeout-only
    failure may be retried once (`retry_timeouts`); an assertion is never retried.
    `min_free_mb` fails an expensive gate with `kind="infra"` before it starts.
    """
    runner = runner or run_shell
    snapshot = snapshotter or _tracked_snapshot
    free = free_space or disk_free_mb

    def run_all() -> List[GateResult]:
        results: List[GateResult] = []
        if cache_dir is not None and tree_key:
            cache_dir.mkdir(parents=True, exist_ok=True)
        for gate in gates:
            cache_path = None
            if cache_dir is not None and tree_key:
                cache_path = _cache_file(cache_dir, tree_key, gate, project_root)
                cached = _cached_pass(cache_path)
                if cached is not None:
                    results.append(GateResult(gate, 0, 0.0, cached.output,
                                              kind="pass", cached=True))
                    continue
            if min_free_mb > 0:
                available = free(project_root)
                if available is not None and available < min_free_mb:
                    results.append(GateResult(
                        gate, -1, 0.0,
                        f"not started: {available:.1f} MB free; the gate needs at least "
                        f"{min_free_mb:.0f} MB. Free space, then rerun.",
                        kind="infra"))
                    continue
            before = snapshot(project_root)
            start = time.perf_counter()
            code, output = runner(gate.command, project_root, timeout)
            elapsed = time.perf_counter() - start
            kind = _classify_failure(code, output)
            attempts = 1
            if retry_timeouts and kind == "timeout":
                attempts = 2
                start = time.perf_counter()
                code, output = runner(gate.command, project_root, timeout)
                elapsed += time.perf_counter() - start
                kind = _classify_failure(code, output)
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
                kind = "rewrite"
            results.append(GateResult(gate, code, elapsed, output, kind=kind, attempts=attempts))
            if cache_path is not None and code == 0 and not rewritten:
                try:
                    _store_pass(cache_path, gate, output)
                except OSError:  # hygiene: allow a cache write failure; the gate result still stands
                    pass
        return results

    if lock_path is None:
        return run_all()
    with file_lock(lock_path, timeout_seconds=lock_timeout) as acquired:
        if not acquired:
            return [GateResult(
                Gate("lock", "", "built-in"), -1, 0.0,
                f"another check or build is running in this project; could not acquire "
                f"{lock_path.name} within {lock_timeout:.0f}s. Wait for it to finish, then rerun.",
                kind="lock")]
        return run_all()


def failure_tail(output: str, lines: int = FAILURE_TAIL_LINES) -> List[str]:
    """The last `lines` non-empty lines of a gate's output, where its error normally is."""
    return [line for line in output.splitlines() if line.strip()][-lines:]
