"""
Bounded UI-surface edits against a committed `.aikit/ui.json` contract (opt-in).

A UI task records its baseline commit and allowed surface before the first edit. `verify`
refuses changes outside that surface or protected paths, enforces a diff budget and runs
the project's fast proof command, the snapshot inventory proof and the style drift lint.
`allow` records intended inventory removals; `finish` also requires a recorded human
review; `abort` restores only the surface, leaving unrelated work intact.

PRINCIPLE-006, PRINCIPLE-011, PRINCIPLE-013, PRINCIPLE-014 and PRINCIPLE-018.
"""

import hashlib
import json
import re
import shutil
import subprocess
import tempfile
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Callable, Dict, List, Optional, Sequence, Tuple

from scripts.disruption_recovery import BOOKKEEPING_PATHS, atomic_write_json, file_lock
from scripts.project_registry import ProjectError
from scripts import ui_proof

CONTRACT_REL = ".aikit/ui.json"
TASK_REL = ".aikit/ui_task.json"
HISTORY_REL = ".aikit/ui_history.json"
TASK_SCHEMA = 1
GIT_TIMEOUT_SECONDS = 30
FAST_TIMEOUT_SECONDS = 120
OUTPUT_TAIL_LINES = 8

# Stable machine-readable finding codes for `aikit ui verify --json` (ADR-167). The human
# messages stay descriptive; consumers match on the code, never on prose.
FINDING_CODES = (
    ("the UI contract changed", "ui.contract-changed"),
    ("the baseline moved", "ui.baseline-moved"),
    ("protected path changed:", "ui.protected-path"),
    ("path outside surface", "ui.outside-surface"),
    ("diff budget:", "ui.budget"),
    ("fast UI proof failed", "ui.fast-proof"),
    ("UI snapshot proof failed", "ui.snapshot-proof"),
    ("UI snapshot proof printed no inventory", "ui.snapshot-empty"),
    ("UI snapshot proof lost", "ui.snapshot-lost"),
    ("style literal", "ui.style-literal"),
    ("human review not recorded", "ui.review-missing"),
)


def finding_code(message: str) -> str:
    """The stable code for one verify/finish finding; unknown prose is `ui.other`."""
    text = str(message)
    for prefix, code in FINDING_CODES:
        if text.startswith(prefix):
            return code
    return "ui.other"


def findings_payload(findings: Sequence[str]) -> List[Dict[str, str]]:
    """JSON-safe findings with stable codes and the original human message."""
    return [{"code": finding_code(finding), "message": str(finding)} for finding in findings]

GitIo = Callable[[Path, Sequence[str]], Tuple[int, str, str]]
ShellRunner = Callable[[str, Path, float], Tuple[int, str]]


@dataclass(frozen=True)
class UiContract:
    """One project's committed UI contract: surfaces, protected paths, commands and limits."""

    surfaces: Dict[str, Tuple[str, ...]]
    protected: Tuple[str, ...]
    fast: str
    fast_timeout: int
    snapshot: str
    snapshot_timeout: int
    theme_paths: Tuple[str, ...]
    max_files: int
    max_lines: int
    digest: str


def _error(message: str, why: str, fix: str, exit_code: int = 1) -> ProjectError:
    return ProjectError(message, why, fix, exit_code)


def _tail(output: str) -> str:
    lines = [line for line in output.strip().splitlines() if line.strip()]
    return "\n".join(lines[-OUTPUT_TAIL_LINES:])


def _valid_pattern(pattern: str) -> bool:
    if not isinstance(pattern, str) or not pattern.strip():
        return False
    normalized = pattern.replace("\\", "/")
    if normalized.startswith("/") or (len(normalized) > 1 and normalized[1] == ":"):
        return False
    return ".." not in normalized.split("/")


def _path_list(raw: object, field: str) -> Tuple[str, ...]:
    if not isinstance(raw, list) or not raw or not all(_valid_pattern(item) for item in raw):
        raise _error(f"{field} must be a non-empty list of relative path patterns.",
                     f"the UI contract's {field} decides which paths the contract can reach.",
                     "write relative patterns such as `src/ui/**`; paths may not escape the project.",
                     exit_code=2)
    return tuple(str(item).replace("\\", "/") for item in raw)


def scaffold_contract(root: Path, surface: str = "app", fast: str = "",
                      paths: Optional[Sequence[str]] = None,
                      snapshot: str = "") -> Dict[str, object]:
    """
    Write a conservative contract for one surface (ADR-168, `aikit ui init`).

    React/Vite is auto-detected. Any other stack can pass `--fast` and `--paths` for a manual
    zero-dependency contract. The scaffold never runs Node and never guesses a snapshot command.
    The user reviews and commits the contract before `ui begin`.
    """
    path = root / CONTRACT_REL
    if path.exists():
        raise _error("A UI contract already exists.",
                     "ui init never overwrites a committed surface contract.",
                     f"edit or remove {CONTRACT_REL} deliberately, then retry.", exit_code=2)
    surface = surface.strip()
    if not surface:
        raise _error("A UI surface name is required.",
                     "the generated contract needs one named surface.",
                     "pass --surface <name>, for example --surface menu.", exit_code=2)
    if bool(fast) != bool(paths):
        raise _error("ui init needs --fast and --paths together.",
                     "a manual contract needs both a proof command and at least one surface path.",
                     'run `ui init <project> --fast "npm run test" --paths "src/**"`, or omit both '
                     "for the React/Vite scaffold.", exit_code=2)
    if fast:
        surface_paths = _path_list(list(paths or ()), f"surfaces.{surface}.paths")
        theme_paths = [rel for rel in ("tailwind.config.js", "tailwind.config.ts",
                                       "tailwind.config.cjs", "tailwind.config.mjs",
                                       "src/theme.css", "src/theme.ts", "src/styles/theme.css")
                       if (root / rel).is_file()]
        protected = ["tests/**"]
        if any(pattern.startswith("src/") for pattern in surface_paths):
            protected.extend(["src/**/*.test.*", "src/**/*.spec.*", "src/**/__tests__/**"])
        contract: Dict[str, object] = {
            "schema": TASK_SCHEMA,
            "surfaces": {surface: {"paths": list(surface_paths)}},
            "protected": protected,
            "commands": {"fast": fast, "snapshot": snapshot},
            "style": {"theme_paths": theme_paths},
            "limits": {"max_files": 12, "max_lines": 300},
        }
        atomic_write_json(path, contract)
        load_contract(root)
        return contract
    manifest_path = root / "package.json"
    try:
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    except (OSError, ValueError) as exc:
        raise _error("ui init currently supports React/Vite projects with a package.json.",
                     f"the project manifest could not be read: {exc}",
                     "create package.json with React and Vite, or write .aikit/ui.json by hand.",
                     exit_code=2) from exc
    if not isinstance(manifest, dict):
        raise _error("package.json must be a JSON object.",
                     "the UI scaffold reads dependencies and scripts from it.",
                     "repair package.json, then retry.", exit_code=2)
    dependencies: Dict[str, object] = {}
    for field in ("dependencies", "devDependencies", "peerDependencies"):
        value = manifest.get(field)
        if isinstance(value, dict):
            dependencies.update(value)
    if "react" not in dependencies or "vite" not in dependencies:
        raise _error("ui init currently supports React/Vite projects only.",
                     "the scaffold needs a React+Vite dependency set to choose a proof command.",
                     "write .aikit/ui.json by hand for this stack, or add React and Vite.",
                     exit_code=2)
    scripts = manifest.get("scripts")
    scripts = scripts if isinstance(scripts, dict) else {}
    if "vitest" in dependencies and isinstance(scripts.get("test"), str):
        fast = "npm run test -- --run"
    elif isinstance(scripts.get("build"), str):
        fast = "npm run build"
    elif isinstance(scripts.get("test"), str):
        fast = "npm run test"
    else:
        raise _error("The React/Vite project has no usable fast proof script.",
                     "the contract needs a deterministic command that exits after proving the app.",
                     'add a "build" or "test" script to package.json, then retry.', exit_code=2)
    if not (root / "src").is_dir():
        raise _error("The React/Vite project has no src/ folder.",
                     "the scaffold needs a surface root to bound edits.",
                     "create src/, or write .aikit/ui.json by hand for this layout.", exit_code=2)
    theme_paths = [rel for rel in ("tailwind.config.js", "tailwind.config.ts",
                                   "tailwind.config.cjs", "tailwind.config.mjs",
                                   "src/theme.css", "src/theme.ts", "src/styles/theme.css")
                   if (root / rel).is_file()]
    snapshot = "npm run ui:snapshot" if isinstance(scripts.get("ui:snapshot"), str) else ""
    contract: Dict[str, object] = {
        "schema": TASK_SCHEMA,
        "surfaces": {surface: {"paths": ["src/**"]}},
        "protected": ["tests/**", "src/**/*.test.*", "src/**/*.spec.*",
                      "src/**/__tests__/**"],
        "commands": {"fast": fast, "snapshot": snapshot},
        "style": {"theme_paths": theme_paths},
        "limits": {"max_files": 12, "max_lines": 300},
    }
    atomic_write_json(path, contract)
    load_contract(root)  # validate the generated file through the same reader as every verify
    return contract


def load_contract(root: Path) -> UiContract:
    """Load and validate the project's committed UI contract."""
    path = root / CONTRACT_REL
    if not path.is_file():
        raise _error(f"No UI contract at {CONTRACT_REL}.",
                     "the UI guard cannot bound edits without a committed surface contract.",
                     "create .aikit/ui.json and commit it, or do not use `aikit ui`.",
                     exit_code=2)
    try:
        raw = json.loads(path.read_text(encoding="utf-8-sig"))
    except (OSError, ValueError) as exc:
        raise _error(f"Cannot read {CONTRACT_REL}: {exc}",
                     "the UI contract is the only source of surface and protected paths.",
                     "repair .aikit/ui.json to valid JSON, then retry.", exit_code=2) from exc
    if not isinstance(raw, dict) or raw.get("schema") != TASK_SCHEMA:
        raise _error("The UI contract schema is not supported.",
                     "this AIKit reads schema 1 only.",
                     'set "schema": 1 in .aikit/ui.json, or use the AIKit version that wrote it.',
                     exit_code=2)
    raw_surfaces = raw.get("surfaces")
    if not isinstance(raw_surfaces, dict) or not raw_surfaces:
        raise _error("The UI contract declares no surfaces.",
                     "a task is bounded by a named surface.",
                     'add "surfaces": {"menu": {"paths": ["src/ui/**"]}} to .aikit/ui.json.',
                     exit_code=2)
    surfaces: Dict[str, Tuple[str, ...]] = {}
    for name, definition in raw_surfaces.items():
        if not isinstance(name, str) or not name.strip() or not isinstance(definition, dict):
            raise _error("A UI surface is malformed.",
                         "each surface is a name mapped to a paths list.",
                         "write each surface as {\"paths\": [\"src/ui/**\"]}.", exit_code=2)
        surfaces[name] = _path_list(definition.get("paths"), f"surfaces.{name}.paths")
    protected = _path_list(raw.get("protected", []), "protected") if raw.get("protected") else ()
    commands = raw.get("commands")
    if not isinstance(commands, dict) or not isinstance(commands.get("fast"), str):
        raise _error("The UI contract declares no fast proof command.",
                     "every task starts and verifies against a green proof command.",
                     'add "commands": {"fast": "npm run test:ui"} to .aikit/ui.json.', exit_code=2)
    timeout = commands.get("fast_timeout", FAST_TIMEOUT_SECONDS)
    if not isinstance(timeout, int) or not 1 <= timeout <= 600:
        raise _error("The UI fast timeout is invalid.",
                      "a proof command must be bounded between 1 and 600 seconds.",
                      "set commands.fast_timeout to an integer in that range.", exit_code=2)
    snapshot = commands.get("snapshot", "")
    if not isinstance(snapshot, str):
        raise _error("The UI snapshot command is malformed.",
                      "the snapshot command prints the live UI's inventory for the proof.",
                      'write "commands": {"snapshot": "python inventory.py"}.', exit_code=2)  # hygiene: allow example command in the user's project
    snapshot_timeout = commands.get("snapshot_timeout", FAST_TIMEOUT_SECONDS)
    if not isinstance(snapshot_timeout, int) or not 1 <= snapshot_timeout <= 600:
        raise _error("The UI snapshot timeout is invalid.",
                      "a snapshot command must be bounded between 1 and 600 seconds.",
                      "set commands.snapshot_timeout to an integer in that range.", exit_code=2)
    style = raw.get("style", {})
    if not isinstance(style, dict):
        raise _error("The UI style block is malformed.",
                      "the style block declares where theme literals may live.",
                      'write "style": {"theme_paths": ["src/theme.py"]}.', exit_code=2)
    theme_paths = (_path_list(style.get("theme_paths"), "style.theme_paths")
                   if style.get("theme_paths") else ())
    limits = raw.get("limits", {})
    if not isinstance(limits, dict):
        raise _error("The UI limits are malformed.", "limits bound the blast radius.",
                     'write "limits": {"max_files": 6, "max_lines": 150}.', exit_code=2)
    max_files = limits.get("max_files", 8)
    max_lines = limits.get("max_lines", 200)
    if not (isinstance(max_files, int) and max_files >= 1 and
            isinstance(max_lines, int) and max_lines >= 1):
        raise _error("The UI diff limits are invalid.",
                     "file and line limits must be positive integers.",
                     'set "limits": {"max_files": 6, "max_lines": 150}.', exit_code=2)
    digest = hashlib.sha256(json.dumps(raw, sort_keys=True, separators=(",", ":"))
                            .encode("utf-8")).hexdigest()
    return UiContract(surfaces, protected, commands["fast"], timeout, snapshot,
                      snapshot_timeout, theme_paths, max_files, max_lines, digest)


_matches = ui_proof.matches_pattern


def _is_bookkeeping(path: str) -> bool:
    normalized = path.replace("\\", "/")
    return (normalized in BOOKKEEPING_PATHS or normalized == TASK_REL or
            normalized.startswith(TASK_REL + "."))


def parse_status(text: str) -> List[Tuple[str, str]]:
    """(XY, path) pairs from `git status --porcelain=v1 -z`, renames expanded to both paths."""
    entries = text.split("\0")
    changes: List[Tuple[str, str]] = []
    index = 0
    while index < len(entries):
        entry = entries[index]
        index += 1
        if len(entry) < 4:
            continue
        status, path = entry[:2], entry[3:]
        changes.append((status, path))
        if ("R" in status or "C" in status) and index < len(entries):
            changes.append((status, entries[index]))
            index += 1
    return changes


def _git(root: Path, args: Sequence[str], git_io: Optional[GitIo] = None) -> Tuple[int, str, str]:
    if git_io is not None:
        return git_io(root, args)
    try:
        result = subprocess.run(["git", "-C", str(root), *args], capture_output=True, text=True,
                                encoding="utf-8", errors="replace", timeout=GIT_TIMEOUT_SECONDS)
    except (OSError, subprocess.SubprocessError) as exc:
        raise _error(f"`git {args[0]}` failed in {root.name}: {exc}",
                     "the UI guard reads the project's repository, not AIKit's.",
                     "install git and make the project a repository, then retry.") from exc
    return result.returncode, result.stdout, result.stderr


def _git_ok(root: Path, args: Sequence[str], git_io: Optional[GitIo] = None) -> str:
    code, out, err = _git(root, args, git_io)
    if code != 0:
        raise _error(f"`git {args[0]}` failed in {root.name}: {err.strip()[:160]}",
                     "the UI guard needs a readable git work tree.",
                     "check `git status` in the project, then retry.")
    return out


def _tracked(root: Path, git_io: Optional[GitIo] = None) -> set:
    return {path for path in _git_ok(root, ["ls-files", "-z"], git_io).split("\0") if path}


def _changes(root: Path, git_io: Optional[GitIo] = None) -> List[Tuple[str, str]]:
    text = _git_ok(root, ["status", "--porcelain=v1", "-z", "--untracked-files=all"], git_io)
    return [(status, path) for status, path in parse_status(text) if not _is_bookkeeping(path)]


def surface_digest(root: Path, patterns: Sequence[str],
                   git_io: Optional[GitIo] = None) -> str:
    """A SHA-256 over every current file in a surface, path and content, for evidence binding."""
    names = _tracked(root, git_io) | {path for status, path in _changes(root, git_io)
                                      if status == "??"}
    entries: List[str] = []
    for rel in sorted(name for name in names if _matches(name, patterns)):
        path = root / rel
        if not path.is_file():
            continue
        try:
            mode = path.stat().st_mode & 0o777
            content = path.read_bytes()
        except OSError as exc:
            raise _error(f"Cannot read surface file {rel}: {exc}",
                         "the finished UI task must bind to every file in its surface.",
                         "repair the file's permissions or remove it from the surface, then retry.")
        entries.append(rel.replace("\\", "/") + "\0" + f"{mode:o}" + "\0"
                       + hashlib.sha256(content).hexdigest())
    if not entries:
        return ""
    return hashlib.sha256("\n".join(entries).encode("utf-8")).hexdigest()


def _head(root: Path, git_io: Optional[GitIo] = None) -> str:
    return _git_ok(root, ["rev-parse", "--verify", "HEAD"], git_io).strip()


def _default_shell_runner() -> "ShellRunner":
    from scripts.project_gates import run_shell
    return run_shell


def _run_fast(contract: UiContract, root: Path,
              runner: Optional[ShellRunner]) -> Tuple[int, str]:
    run = runner or _default_shell_runner()
    return run(contract.fast, root, float(contract.fast_timeout))


def _run_snapshot(contract: UiContract, root: Path,
                  runner: Optional[ShellRunner]) -> Tuple[int, str]:
    run = runner or _default_shell_runner()
    return run(contract.snapshot, root, float(contract.snapshot_timeout))


def _task_path(root: Path) -> Path:
    return root / TASK_REL


def read_task(root: Path) -> Dict[str, object]:
    """The open UI task record, refusing a missing or unreadable one."""
    path = _task_path(root)
    if not path.is_file():
        raise _error("No UI task is open.",
                     "the guard only bounds edits after `aikit ui begin`.",
                     "run `python aikit.py ui begin <project> --surface <name>` first.")
    try:
        task = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError) as exc:
        raise _error(f"The UI task record is unreadable: {exc}",
                     "a corrupt record cannot prove the baseline or the surface.",
                     "run `python aikit.py ui abort <project>` to drop it, then begin again.") from exc
    required = ("surface", "baseline_commit", "contract_hash", "started_at", "strikes")
    if (not isinstance(task, dict) or task.get("schema") != TASK_SCHEMA or
            any(key not in task for key in required)):
        raise _error("The UI task record is malformed.",
                     "the guard needs the surface, baseline commit, contract hash and strikes.",
                     "run `python aikit.py ui abort <project>` to drop it, then begin again.")
    return task


def _task_error(message: str, fix: str) -> ProjectError:
    return _error(message, "the open UI task no longer matches the project.", fix)


def begin(root: Path, surface: str, git_io: Optional[GitIo] = None,
          shell_runner: Optional[ShellRunner] = None) -> Dict[str, object]:
    """Open a bounded task for one named surface, from a clean, green baseline."""
    contract = load_contract(root)
    if surface not in contract.surfaces:
        names = ", ".join(sorted(contract.surfaces)) or "none"
        raise _error(f"Unknown UI surface '{surface}'.",
                     f"the contract declares: {names}.",
                     "choose one of the declared surface names.", exit_code=2)
    tracked = _tracked(root, git_io)
    if CONTRACT_REL not in tracked:
        raise _error(f"{CONTRACT_REL} is not tracked.",
                     "a surface contract that is not committed cannot bound a baseline.",
                     f"commit {CONTRACT_REL} before beginning a UI task.")
    with file_lock(_task_path(root)) as acquired:
        if not acquired:
            raise _task_error("Another UI operation holds the task lock.",
                              "wait for it to finish, then retry.")
        if _task_path(root).exists():
            raise _task_error("A UI task is already open.",
                              "run `python aikit.py ui finish <project>` or "
                              "`python aikit.py ui abort <project>` before beginning another.")
        changes = _changes(root, git_io)
        if changes:
            listed = ", ".join(path for _, path in changes[:6])
            raise _task_error(f"The tree is not clean: {listed}",
                              "begin from a clean baseline so the diff is only the UI task.")
        baseline = _head(root, git_io)
        code, output = _run_fast(contract, root, shell_runner)
        if code != 0:
            raise _task_error(f"The fast UI proof failed before the task started (exit {code}).",
                              f"fix the baseline first; output:\n{_tail(output)}")
        baseline_snapshot: List[str] = []
        if contract.snapshot:
            code, output = _run_snapshot(contract, root, shell_runner)
            if code != 0:
                raise _task_error(
                    f"The UI snapshot proof failed before the task started (exit {code}).",
                    f"fix the baseline UI first; output:\n{_tail(output)}")
            baseline_snapshot = ui_proof.snapshot_lines(output)
            if not baseline_snapshot:
                raise _error("The UI snapshot proof printed no inventory entries.",
                             "a task cannot baseline a UI it cannot enumerate.",
                             "make the snapshot command print one entry per control or "
                             "handler, then begin again.")
        task = {
            "schema": TASK_SCHEMA,
            "surface": surface,
            "baseline_commit": baseline,
            "contract_hash": contract.digest,
            "started_at": time.time(),
            "strikes": 0,
            "baseline_snapshot": baseline_snapshot,
            "allowed_removals": [],
        }
        atomic_write_json(_task_path(root), task)
        return task


def _diff_lines(root: Path, baseline: str, git_io: Optional[GitIo]) -> int:
    output = _git_ok(root, ["diff", "--numstat", baseline, "--"], git_io)
    total = 0
    for line in output.splitlines():
        parts = line.split("\t")
        if len(parts) < 3 or _is_bookkeeping(parts[2]):
            continue
        added, deleted = parts[0], parts[1]
        total += (1 if added == "-" else int(added)) + (1 if deleted == "-" else int(deleted))
    return total


def _line_count(path: Path) -> int:
    try:
        with path.open("rb") as handle:  # hygiene: allow binary line count; encoding does not apply
            return sum(1 for _ in handle) or 1
    except OSError:
        return 1


def _budget_findings(root: Path, changes: Sequence[Tuple[str, str]], contract: UiContract,
                     task: Dict[str, object], git_io: Optional[GitIo]) -> List[str]:
    files = {path for _, path in changes}
    findings: List[str] = []
    if len(files) > contract.max_files:
        findings.append(f"diff budget: {len(files)} files changed; the limit is "
                        f"{contract.max_files}.")
    lines = _diff_lines(root, str(task["baseline_commit"]), git_io)
    for status, path in changes:
        if status == "??":
            lines += _line_count(root / path)
    if lines > contract.max_lines:
        findings.append(f"diff budget: {lines} changed lines; the limit is {contract.max_lines}.")
    return findings


def _added_lines(root: Path, changes: Sequence[Tuple[str, str]], baseline: str,
                 surface: Sequence[str], git_io: Optional[GitIo]) -> List[Tuple[str, int, str]]:
    """(path, line number, text) for every line added inside the task's surface."""
    tracked = [path for status, path in changes if status != "??" and _matches(path, surface)]
    untracked = [path for status, path in changes if status == "??" and _matches(path, surface)]
    added: List[Tuple[str, int, str]] = []
    if tracked:
        text = _git_ok(root, ["diff", baseline, "--", *tracked], git_io)
        path, number = "", 0
        for line in text.splitlines():
            header = re.match(r"^@@ -\d+(?:,\d+)? \+(\d+)(?:,\d+)? @@", line)
            if header is not None:
                number = int(header.group(1)) - 1
            elif line.startswith("+++ b/"):
                path, number = line[6:], 0
            elif line.startswith("+"):
                number += 1
                added.append((path, number, line[1:]))
            elif line.startswith(" "):
                number += 1
    for path in untracked:
        try:
            content = (root / path).read_text(encoding="utf-8", errors="replace")
        except OSError:
            continue
        for number, line in enumerate(content.splitlines(), start=1):
            added.append((path, number, line))
    return added


def verify(root: Path, git_io: Optional[GitIo] = None,
           shell_runner: Optional[ShellRunner] = None) -> List[str]:
    """Check the open task's scope, contract, baseline, budget and proof commands."""
    contract = load_contract(root)
    with file_lock(_task_path(root)) as acquired:
        if not acquired:
            raise _task_error("Another UI operation holds the task lock.",
                              "wait for it to finish, then retry.")
        task = read_task(root)
        if task["contract_hash"] != contract.digest:
            findings = ["the UI contract changed after the task began."]
        elif _head(root, git_io) != task["baseline_commit"]:
            findings = ["the baseline moved (HEAD changed) after the task began."]
        else:
            surface = contract.surfaces[str(task["surface"])]
            changes = _changes(root, git_io)
            findings = []
            for _, path in changes:
                if _matches(path, contract.protected):
                    findings.append(f"protected path changed: {path}")
                elif not _matches(path, surface):
                    findings.append(f"path outside surface '{task['surface']}': {path}")
            findings.extend(_budget_findings(root, changes, contract, task, git_io))
            if not findings:
                code, output = _run_fast(contract, root, shell_runner)
                if code != 0:
                    findings.append(f"fast UI proof failed (exit {code}):\n{_tail(output)}")
                if contract.snapshot and "baseline_snapshot" in task:
                    code, output = _run_snapshot(contract, root, shell_runner)
                    if code != 0:
                        findings.append(f"UI snapshot proof failed (exit {code}):\n{_tail(output)}")
                    else:
                        current = ui_proof.snapshot_lines(output)
                        task["last_snapshot"] = current
                        if not current:
                            findings.append("UI snapshot proof printed no inventory entries.")
                        else:
                            findings.extend(ui_proof.inventory_findings(
                                list(task["baseline_snapshot"]), current,
                                [entry["pattern"]
                                 for entry in allowed_removal_entries(task)]))
                if contract.theme_paths:
                    added = _added_lines(root, changes, str(task["baseline_commit"]),
                                         surface, git_io)
                    findings.extend(ui_proof.style_findings(added, contract.theme_paths))
        task["strikes"] = int(task["strikes"]) + (1 if findings else 0)
        if not findings:
            task["verified_at"] = time.time()
        atomic_write_json(_task_path(root), task)
        return findings


def allowed_removal_entries(task: Dict[str, object]) -> List[Dict[str, str]]:
    """
    One task's allowed removals as `{"pattern": ..., "reason": ...}` records.

    A task written before removals carried a reason holds bare pattern strings; those stay
    readable and are reported as `legacy entry` rather than rewritten (ADR-171).
    """
    entries: List[Dict[str, str]] = []
    for item in task.get("allowed_removals", []) or []:
        if isinstance(item, dict):
            entries.append({"pattern": str(item.get("pattern", "")),
                            "reason": str(item.get("reason", ""))})
        else:
            entries.append({"pattern": str(item), "reason": "legacy entry"})
    return entries


def allow(root: Path, pattern: str, reason: str = "") -> Dict[str, object]:
    """Record one intended inventory removal pattern and its reason on the open task."""
    if not isinstance(pattern, str) or not pattern.strip():
        raise _error("The allowed removal pattern is empty.",
                     "verify treats removed inventory entries as findings unless allowed.",
                     "pass a glob such as `Button*` for the entries this task removes.",
                     exit_code=2)
    if not isinstance(reason, str) or not reason.strip():
        raise _error("An allowed removal needs a reason.",
                     "an unexplained allow line turns a real control loss into a clean pass.",
                     'rerun `ui allow <project> "<pattern>" --reason "<why the removal is intended>"`.',
                     exit_code=2)
    contract = load_contract(root)
    with file_lock(_task_path(root)) as acquired:
        if not acquired:
            raise _task_error("Another UI operation holds the task lock.",
                              "wait for it to finish, then retry.")
        task = read_task(root)
        if task["contract_hash"] != contract.digest:
            raise _task_error("The UI contract changed after the task began.",
                              "abort the task and begin again under the new contract.")
        allowed = allowed_removal_entries(task)
        if not any(entry["pattern"] == pattern for entry in allowed):
            allowed.append({"pattern": pattern, "reason": reason.strip()})
        task["allowed_removals"] = allowed
        atomic_write_json(_task_path(root), task)
        return task


def _read_history(root: Path) -> List[Dict[str, object]]:
    """Read the append-only UI history; a missing file is empty, a malformed one is an error."""
    path = root / HISTORY_REL
    if not path.is_file():
        return []
    try:
        loaded = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError) as exc:
        raise _error(f"The UI history {HISTORY_REL} is unreadable: {exc}",
                     "a finished task's history is evidence; the guard refuses to guess.",
                     f"repair or move {HISTORY_REL} aside, then retry.") from exc
    if not isinstance(loaded, list) or not all(isinstance(record, dict) for record in loaded):
        raise _error(f"The UI history {HISTORY_REL} is malformed.",
                     "a finished task's history is evidence; the guard refuses to guess.",
                     f"repair or move {HISTORY_REL} aside, then retry.")
    return loaded


def surface_evidence_errors(root: Path, git_io: Optional[GitIo] = None) -> List[str]:
    """Surfaces whose current files do not match any finished task's recorded digest."""
    contract = load_contract(root)
    history = _read_history(root)
    errors: List[str] = []
    for name, patterns in contract.surfaces.items():
        digest = surface_digest(root, patterns, git_io)
        if not any(record.get("surface") == name and record.get("surface_digest") == digest
                   for record in history):
            errors.append(f"UI surface '{name}' has no finished UI task matching its current files; "
                          "finish a new UI task (records before ADR-169 have no digest)")
    return errors


def _append_history(root: Path, task: Dict[str, object], reviewer: str,
                    git_io: Optional[GitIo] = None) -> None:
    """Append the finished task's evidence to the project's UI history (ADR-161, ADR-169)."""
    path = root / HISTORY_REL
    history = _read_history(root)
    contract = load_contract(root)
    digest = surface_digest(root, contract.surfaces[str(task["surface"])], git_io)
    final = [str(line) for line in task.get("last_snapshot", [])]
    snapshot_digest = hashlib.sha256("\n".join(final).encode("utf-8")).hexdigest() if final else ""
    history.append({
        "schema": TASK_SCHEMA,
        "surface": task["surface"],
        "baseline_commit": task["baseline_commit"],
        "contract_hash": task["contract_hash"],
        "started_at": task["started_at"],
        "finished_at": time.time(),
        "strikes": int(task["strikes"]),
        "reviewer": reviewer,
        "allowed_removals": allowed_removal_entries(task),
        "final_snapshot_digest": snapshot_digest,
        "final_snapshot_entries": len(final),
        "surface_digest": digest,
    })
    atomic_write_json(path, history)


def finish(root: Path, git_io: Optional[GitIo] = None,
           shell_runner: Optional[ShellRunner] = None,
           reviewed: bool = False, reviewer: str = "") -> List[str]:
    """Close a task only after a successful verify, a recorded review and its evidence."""
    findings = verify(root, git_io, shell_runner)
    if findings:
        return findings
    if not reviewed:
        return ["human review not recorded: no one confirmed the running UI looks right."]
    with file_lock(_task_path(root)) as acquired:
        if not acquired:
            raise _task_error("Another UI operation holds the task lock.",
                              "wait for it to finish, then retry.")
        task = read_task(root)
        _append_history(root, task, reviewer, git_io)
        _task_path(root).unlink(missing_ok=True)
        _task_path(root).with_suffix(".json.bak").unlink(missing_ok=True)
    return []


def abort(root: Path, git_io: Optional[GitIo] = None) -> Dict[str, object]:
    """Restore only the surface to its baseline, preserving and reporting everything else."""
    contract = load_contract(root)
    with file_lock(_task_path(root)) as acquired:
        if not acquired:
            raise _task_error("Another UI operation holds the task lock.",
                              "wait for it to finish, then retry.")
        task = read_task(root)
        baseline = str(task["baseline_commit"])
        if _head(root, git_io) != baseline:
            raise _task_error("The baseline moved; refusing to restore over newer commits.",
                              "resolve the history by hand, then delete .aikit/ui_task.json.")
        surface = contract.surfaces[str(task["surface"])]
        tracked = _tracked(root, git_io)
        restore: List[str] = []
        untracked: List[str] = []
        skipped: List[str] = []
        for status, path in _changes(root, git_io):
            if _matches(path, contract.protected) or not _matches(path, surface):
                skipped.append(path)
            elif status == "??":
                untracked.append(path)
            elif path in tracked:
                restore.append(path)
        backup: Optional[Path] = None
        if restore or untracked:
            backup = Path(tempfile.mkdtemp(prefix="aikit_ui_abort_"))
        if restore:
            patch = _git_ok(root, ["diff", "--binary", baseline, "--", *restore], git_io)
            (backup / "changes.patch").write_text(patch, encoding="utf-8")
        for path in untracked:
            destination = backup / path
            destination.parent.mkdir(parents=True, exist_ok=True)
            try:
                shutil.copy2(root / path, destination)
            except OSError as exc:
                raise _task_error(f"Cannot back up {path} before abort: {exc}",
                                  "nothing was restored; resolve the file handle, then retry.") from exc
        if restore:
            _git_ok(root, ["restore", "--source", baseline, "--staged", "--worktree",
                           "--", *restore], git_io)
        for path in untracked:
            (root / path).unlink(missing_ok=True)
        _task_path(root).unlink(missing_ok=True)
        _task_path(root).with_suffix(".json.bak").unlink(missing_ok=True)
        return {"backup": str(backup) if backup is not None else "",
                "restored": sorted(restore + untracked),
                "skipped": sorted(set(skipped))}


def status(root: Path, git_io: Optional[GitIo] = None) -> Dict[str, object]:
    """The open task, its baseline and the paths changed under it right now."""
    task = read_task(root)
    return {"surface": task["surface"], "baseline_commit": task["baseline_commit"],
            "strikes": task["strikes"],
            "changed": sorted({path for _, path in _changes(root, git_io)})}
