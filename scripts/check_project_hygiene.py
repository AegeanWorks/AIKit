#!/usr/bin/env python3
"""
Project hygiene scan (PRINCIPLE-003 R4, PRINCIPLE-010, PRINCIPLE-011 R3, PRINCIPLE-000 R5).

A project's gates decide tests, README structure and secrets. This scan decides the mechanical
clauses no gate could see before it existed: a subprocess that parses through the platform shell,
Python started without `sys.executable`, arguments passed as one string, a call that can hang
without `timeout=`, a hard-indexed `os.environ[...]`, a text-mode `open()` without `encoding=`,
a broad `except` whose whole body is `pass`, a machine-specific absolute path, a third-party URL
in a static asset (ADR-137).

Every rule is decidable from the AST or from one line of regex, so a clean run is evidence rather
than opinion, and every finding names the line to change. A deliberate exception is documented as
`hygiene: allow <reason>` on the finding's own line or the line directly above it.

Exit codes:
  0 clean    1 findings    2 CLI argument misuse
"""

import ast
import re
import subprocess
import sys
from dataclasses import dataclass
from pathlib import Path, PurePosixPath
from typing import Callable, Dict, Iterable, List, Optional, Sequence, Set, Tuple

ROOT_DIR = Path(__file__).resolve().parent.parent

# Directories whose contents answer to a tool, not to this repository (PRINCIPLE-003 R2).
SKIP_DIRS = frozenset({".git", ".aikit", "__pycache__", ".venv", "venv", "env", "node_modules",
                       "dist", "build", ".mypy_cache", ".ruff_cache", ".pytest_cache"})

PY_SUFFIX = ".py"
ASSET_SUFFIXES = frozenset({".html", ".css", ".js"})

# Artifacts are decided from git's own lists, never from a guessed file content. A directory or
# suffix here is a cache/build output; if git tracks it, the repository should stop tracking it.
ARTIFACT_DIRS = frozenset({"__pycache__", ".pytest_cache", ".mypy_cache", ".ruff_cache",
                           "htmlcov", "dist", "build", ".eggs", "node_modules", ".venv",
                           "venv"})
ARTIFACT_SUFFIXES = (".pyc", ".pyo", ".log", ".tmp", ".bak", ".orig", ".rej")
ROOT_OUTPUT_SUFFIXES = frozenset({".txt", ".log", ".tmp", ".bak", ".orig", ".rej", ".out"})
GIT_TIMEOUT_SECONDS = 30

ALLOW_MARKER = re.compile(r"hygiene:\s*allow\s+\S{3,}")
SUBPROCESS_FUNCS = frozenset({"run", "call", "check_call", "check_output", "Popen"})
# Popen does not accept `timeout=`; its caller bounds the wait with communicate(timeout=...) or
# wait(timeout=...). Requiring the keyword on the constructor made the rule unsatisfiable.
TIMEOUT_FUNCS = frozenset({"run", "call", "check_call", "check_output"})
BARE_PYTHONS = frozenset({"python", "python.exe", "python3", "python3.exe", "python2",
                          "python2.exe", "py", "py.exe"})
EXTERNAL_URL = re.compile(r"https?://[^\s\"'<>)]+")
URL_HOST = re.compile(r"https?://([^/:\s\"'<>)]+)")
# Hosts whose URLs are not third-party dependencies: a loopback address, an SVG XML namespace.
LOCAL_HOSTS = frozenset({"localhost", "127.0.0.1", "www.w3.org"})
ABSOLUTE_PATH = re.compile(r"^(?:[A-Za-z]:[\\/]|\\\\[^\\\s]+\\|/(?:Users|home|etc|var|opt|usr)/)")
# Calls whose arguments reach the real filesystem: an absolute literal anywhere else is displayed
# content, not a machine path (a game's simulated `/etc/hosts` is not a hardcoded host path).
PATH_CALLS = frozenset({"open", "Path", "read_text", "write_text", "read_bytes", "write_bytes",
                        "exists", "isfile", "isdir", "mkdir", "makedirs", "iterdir", "glob",
                        "rglob", "unlink", "join", "listdir", "walk", "normpath", "abspath",
                        "expanduser"})


@dataclass(frozen=True)
class Finding:
    """One violation, addressed to the line a developer must change."""

    path: str
    line: int
    rule: str
    message: str

    def render(self) -> str:
        """The one-line report form: `path:line [rule] message`."""
        return f"   - {self.path}:{self.line} [{self.rule}] {self.message}"


def _keyword(call: ast.Call, name: str) -> Optional[ast.expr]:
    """The value of `call`'s keyword `name`, or None when the call omits it."""
    for keyword in call.keywords:
        if keyword.arg == name:
            return keyword.value
    return None


def _true_literal(node: Optional[ast.expr]) -> bool:
    """Whether the expression is the literal `True` (a name called `True` cannot exist)."""
    return isinstance(node, ast.Constant) and node.value is True


def _subprocess_aliases(tree: ast.Module) -> Dict[str, str]:
    """Local name -> imported subprocess member, so aliases keep their original call name."""
    aliases: Dict[str, str] = {}
    for node in ast.walk(tree):
        if isinstance(node, ast.ImportFrom) and node.module == "subprocess":
            for alias in node.names:
                aliases[alias.asname or alias.name] = alias.name
    return aliases


def _subprocess_name(call: ast.Call, aliases: Dict[str, str]) -> Optional[str]:
    """The subprocess member a call invokes, whether module-qualified or imported by name."""
    func = call.func
    if isinstance(func, ast.Attribute):
        return func.attr
    if isinstance(func, ast.Name):
        return aliases.get(func.id)
    return None


def _subprocess_call(node: ast.AST, aliases: Dict[str, str]) -> Optional[ast.Call]:
    """The node as a `subprocess` call (module-qualified or imported by name), else None."""
    if not isinstance(node, ast.Call):
        return None
    func = node.func
    if isinstance(func, ast.Attribute) and func.attr in SUBPROCESS_FUNCS:
        if isinstance(func.value, ast.Name) and func.value.id == "subprocess":
            return node
        return None
    if isinstance(func, ast.Name) and func.id in aliases:
        return node
    return None


def check_banned_calls(rel: str, tree: ast.Module) -> Iterable[Finding]:
    """PRINCIPLE-003 R4 and PRINCIPLE-010: calls that lose quoting or execute data as code."""
    aliases = _subprocess_aliases(tree)
    for node in ast.walk(tree):
        call = _subprocess_call(node, aliases)
        if call is not None and _true_literal(_keyword(call, "shell")):
            yield Finding(rel, call.lineno, "shell-true",
                          "a shell command line parses through the platform shell (PRINCIPLE-003 R4)")
        if isinstance(node, ast.Call) and isinstance(node.func, ast.Attribute) \
                and node.func.attr == "system" and isinstance(node.func.value, ast.Name) \
                and node.func.value.id == "os":
            yield Finding(rel, node.lineno, "os-system",
                          "os.system breaks on spaced paths (PRINCIPLE-003 R4)")
        if isinstance(node, ast.Call) and isinstance(node.func, ast.Name) \
                and node.func.id in ("eval", "exec"):
            yield Finding(rel, node.lineno, "eval-exec",
                          f"{node.func.id}() executes data as code (PRINCIPLE-010)")


SCOPE_NODES = (ast.FunctionDef, ast.AsyncFunctionDef)


def _scope_walk(scope: ast.AST) -> Iterable[ast.AST]:
    """Walk one function (or the module) without descending into nested functions."""
    def visit(node: ast.AST) -> Iterable[ast.AST]:
        if node is not scope and isinstance(node, SCOPE_NODES):
            return
        yield node
        for child in ast.iter_child_nodes(node):
            yield from visit(child)

    yield from visit(scope)


def _parents(tree: ast.Module) -> Dict[ast.AST, ast.AST]:
    parents: Dict[ast.AST, ast.AST] = {}
    for node in ast.walk(tree):
        for child in ast.iter_child_nodes(node):
            parents[child] = node
    return parents


def _enclosing_scope(node: ast.AST, parents: Dict[ast.AST, ast.AST]) -> Optional[ast.AST]:
    current = node
    while current in parents:
        current = parents[current]
        if isinstance(current, SCOPE_NODES):
            return current
    return None


def _bounded_wait(scope: ast.AST) -> Tuple[Set[str], Set[int]]:
    """Variable names and direct call nodes in one scope whose Popen wait carries a timeout."""
    names: Set[str] = set()
    calls: Set[int] = set()
    for node in _scope_walk(scope):
        if not isinstance(node, ast.Call):
            continue
        func = node.func
        if not (isinstance(func, ast.Attribute) and func.attr in ("communicate", "wait")
                and _keyword(node, "timeout") is not None):
            continue
        calls.add(id(func.value))
        if isinstance(func.value, ast.Name):
            names.add(func.value.id)
    return names, calls


def _popen_targets(scope: ast.AST, call: ast.Call) -> Set[str]:
    """Names a Popen call is assigned to in one scope, including `with ... as name`."""
    names: Set[str] = set()
    for node in _scope_walk(scope):
        if isinstance(node, ast.Assign) and node.value is call:
            names.update(target.id for target in node.targets if isinstance(target, ast.Name))
        elif isinstance(node, ast.AnnAssign) and node.value is call \
                and isinstance(node.target, ast.Name):
            names.add(node.target.id)
        elif isinstance(node, ast.NamedExpr) and node.value is call \
                and isinstance(node.target, ast.Name):
            names.add(node.target.id)
        elif isinstance(node, ast.With):
            for item in node.items:
                if item.context_expr is call and isinstance(item.optional_vars, ast.Name):
                    names.add(item.optional_vars.id)
    return names


def check_subprocess_calls(rel: str, tree: ast.Module) -> Iterable[Finding]:
    """PRINCIPLE-003 R4 and PRINCIPLE-010: portable, bounded, list-passed subprocess calls."""
    aliases = _subprocess_aliases(tree)
    parents = _parents(tree)
    bounded_cache: Dict[int, Tuple[Set[str], Set[int]]] = {}
    for node in ast.walk(tree):
        call = _subprocess_call(node, aliases)
        if call is None:
            continue
        if call.args and isinstance(call.args[0], ast.Constant) \
                and isinstance(call.args[0].value, str):
            yield Finding(rel, call.lineno, "subprocess-argv",
                          "arguments must be a list, not a string (PRINCIPLE-003 R4)")
        first = call.args[0] if call.args else None
        if isinstance(first, (ast.List, ast.Tuple)) and first.elts:
            head = first.elts[0]
            if isinstance(head, ast.Constant) and isinstance(head.value, str) \
                    and head.value.lower() in BARE_PYTHONS:
                yield Finding(rel, call.lineno, "sys-executable",
                              "start Python with sys.executable, not a bare name (PRINCIPLE-003 R4)")
        name = _subprocess_name(call, aliases)
        if name == "Popen":
            scope = _enclosing_scope(call, parents) or tree
            if id(scope) not in bounded_cache:
                bounded_cache[id(scope)] = _bounded_wait(scope)
            bounded_names, bounded_calls = bounded_cache[id(scope)]
            targets = _popen_targets(scope, call)
            if id(call) not in bounded_calls and not (targets & bounded_names):
                yield Finding(rel, call.lineno, "popen-wait-timeout",
                              "Popen needs communicate(timeout=...) or wait(timeout=...) "
                              "(PRINCIPLE-010)")
        elif name in TIMEOUT_FUNCS and _keyword(call, "timeout") is None:
            yield Finding(rel, call.lineno, "subprocess-timeout",
                          "subprocess call without timeout= can hang a gate (PRINCIPLE-010)")


def check_environ_index(rel: str, tree: ast.Module) -> Iterable[Finding]:
    """PRINCIPLE-011 R3: a hard-indexed environment variable crashes where it is unset."""
    for node in ast.walk(tree):
        if not isinstance(node, ast.Subscript):
            continue
        value = node.value
        if isinstance(value, ast.Attribute) and value.attr == "environ" \
                and isinstance(value.value, ast.Name) and value.value.id == "os":
            yield Finding(rel, node.lineno, "environ-index",
                          "os.environ[...] raises KeyError when unset; use os.getenv "
                          "with a default (PRINCIPLE-011 R3)")


def _open_mode(call: ast.Call) -> Optional[str]:
    """The literal mode of an open() call, or None when binary-ness is not decidable."""
    mode = _keyword(call, "mode")
    if mode is None and len(call.args) >= 2:
        mode = call.args[1]
    if mode is None:
        return "r"
    if isinstance(mode, ast.Constant) and isinstance(mode.value, str):
        return mode.value
    return None


def _is_open_call(node: ast.AST) -> bool:
    """
    Whether the node is a builtin `open(...)` or an object's `.open(...)` method call.

    `os.open()` returns a file descriptor and cannot be used as a `with` item; it is closed in a
    `finally` block, so PRINCIPLE-010 R4's builtin/Path.open rule does not cover it.
    """
    if not isinstance(node, ast.Call):
        return False
    func = node.func
    if isinstance(func, ast.Name) and func.id == "open":
        return True
    if isinstance(func, ast.Attribute) and func.attr == "open":
        return not (isinstance(func.value, ast.Name) and func.value.id == "os")
    return False


def check_open_calls(rel: str, tree: ast.Module) -> Iterable[Finding]:
    """PRINCIPLE-003 R4 and PRINCIPLE-010: text mode needs an explicit encoding and a with block."""
    held = {id(item.context_expr) for node in ast.walk(tree) if isinstance(node, ast.With)
            for item in node.items}
    for node in ast.walk(tree):
        if not _is_open_call(node):
            continue
        if _keyword(node, "encoding") is None:
            mode = _open_mode(node)
            if mode is not None and "b" not in mode:
                yield Finding(rel, node.lineno, "open-encoding",
                              "text-mode open() without encoding= reads the locale's "
                              "encoding (PRINCIPLE-003 R4)")
        if id(node) not in held:
            yield Finding(rel, node.lineno, "open-context",
                          "open() outside a with block can leak the handle (PRINCIPLE-010)")


def check_silent_except(rel: str, tree: ast.Module) -> Iterable[Finding]:
    """
    PRINCIPLE-000 R5: a handler that discards the error and does nothing hides the failure.
    Flagged: any `except ...: pass`, whatever it catches, and a broad handler (bare, `Exception`
    or `BaseException`) whose whole body is a lone `return`, `continue` or `break`. A typed
    handler that skips an item is a decision, not a silence, so it is left alone. A deliberate
    discard carries `hygiene: allow <reason>` on the handler's line or the one above (ADR-147).
    """
    for node in ast.walk(tree):
        if not isinstance(node, ast.ExceptHandler) or len(node.body) != 1:
            continue
        body = node.body[0]
        broad = node.type is None or (isinstance(node.type, ast.Name)
                                      and node.type.id in ("Exception", "BaseException"))
        bare_exit = (isinstance(body, (ast.Continue, ast.Break))
                     or (isinstance(body, ast.Return) and body.value is None))
        if isinstance(body, ast.Pass):
            caught = "a bare except" if node.type is None else f"`except {ast.unparse(node.type)}`"
            yield Finding(rel, node.lineno, "silent-except",
                          f"{caught} with only pass discards the error (PRINCIPLE-000 R5)")
        elif broad and bare_exit:
            yield Finding(rel, node.lineno, "silent-except",
                          f"a broad except with only {type(body).__name__.lower()} discards every "
                          f"error (PRINCIPLE-000 R5)")


def _docstring_ids(tree: ast.Module) -> Set[int]:
    """Ids of docstring constants: prose may name any path without baking it into behaviour."""
    found: Set[int] = set()
    for node in ast.walk(tree):
        if not isinstance(node, (ast.Module, ast.FunctionDef, ast.AsyncFunctionDef,
                                 ast.ClassDef)):
            continue
        body = node.body
        if body and isinstance(body[0], ast.Expr) and isinstance(body[0].value, ast.Constant) \
                and isinstance(body[0].value.value, str):
            found.add(id(body[0].value))
    return found


def _call_head(node: ast.Call) -> str:
    """The called function's final name: `Path` for Path(...), `join` for os.path.join(...)."""
    func = node.func
    if isinstance(func, ast.Name):
        return func.id
    if isinstance(func, ast.Attribute):
        return func.attr
    return ""


def _direct_arguments(call: ast.Call) -> List[ast.expr]:
    """Positional and keyword argument expressions of a call."""
    return [*call.args, *(keyword.value for keyword in call.keywords)]


def check_absolute_paths(rel: str, tree: ast.Module) -> Iterable[Finding]:
    """PRINCIPLE-003 R4: a machine-specific path reaching file access breaks every other machine."""
    docstrings = _docstring_ids(tree)
    candidates: Set[int] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Call) and _call_head(node) in PATH_CALLS:
            for argument in _direct_arguments(node):
                if isinstance(argument, ast.Constant) and isinstance(argument.value, str):
                    candidates.add(id(argument))
    for node in ast.walk(tree):
        if not isinstance(node, ast.Constant) or not isinstance(node.value, str):
            continue
        if id(node) in candidates and id(node) not in docstrings and ABSOLUTE_PATH.match(node.value):
            yield Finding(rel, node.lineno, "absolute-path",
                          f"absolute path '{node.value[:48]}' is machine-specific (PRINCIPLE-003 R4)")


def check_asset_source(rel: str, source: str) -> List[Finding]:
    """PRINCIPLE-003 R3: a static asset that loads from a third party is a hidden dependency."""
    findings: List[Finding] = []
    lines = source.splitlines()
    for number, line in enumerate(lines, start=1):
        if _marked(lines, number):
            continue
        for match in EXTERNAL_URL.finditer(line):
            host = URL_HOST.match(match.group(0))
            if host and host.group(1).lower() in LOCAL_HOSTS:
                continue
            findings.append(Finding(rel, number, "external-url",
                                    f"'{match.group(0)[:52]}' loads from a third party "
                                    "(PRINCIPLE-003 R3)"))
    return findings


def _marked(lines: Sequence[str], line: int) -> bool:
    """
    Whether a deliberated `hygiene: allow <reason>` marker covers the finding's line.

    The marker is read on the finding's own line or the line directly above it: a long call or a
    line already at the width limit has no room for a trailing comment, and forcing one there was
    the reason deliberate exceptions went unmarked (ADR-171). One line above only, never further,
    so a marker cannot drift away from what it excuses.
    """
    if not 1 <= line <= len(lines):
        return False
    if ALLOW_MARKER.search(lines[line - 1]):
        return True
    return line >= 2 and bool(ALLOW_MARKER.search(lines[line - 2]))


PYTHON_CHECKS: Tuple[Callable[[str, ast.Module], Iterable[Finding]], ...] = (
    check_banned_calls,
    check_subprocess_calls,
    check_environ_index,
    check_open_calls,
    check_silent_except,
    check_absolute_paths,
)


def check_python_source(rel: str, source: str) -> List[Finding]:
    """Every Python finding in one source text; findings on `hygiene: allow` lines are dropped."""
    try:
        tree = ast.parse(source)
    except SyntaxError as error:
        return [Finding(rel, error.lineno or 1, "unparseable",
                        "a syntax error blocks the hygiene scan of this file")]
    lines = source.splitlines()
    raw: List[Finding] = []
    for check in PYTHON_CHECKS:
        raw.extend(check(rel, tree))
    return [finding for finding in raw if not _marked(lines, finding.line)]


def _read_source(rel: str, path: Path) -> Tuple[Optional[str], List[Finding]]:
    """The file's UTF-8 text, or the finding that replaces it (PRINCIPLE-000 R5: no silent skip)."""
    try:
        return path.read_text(encoding="utf-8-sig"), []
    except (OSError, UnicodeDecodeError):
        return None, [Finding(rel, 1, "unreadable",
                              "the file could not be read as UTF-8 text; its hygiene is unproven")]


def _is_root_test_module(path: str) -> bool:
    """
    Whether `path` is a test module at the project root, where default runners import it.

    `unittest discover` collects `test*.py`, and on Windows its fnmatch match is case-insensitive,
    so the name is compared lowercased; pytest additionally collects `*_test.py`.
    """
    if "/" in path:
        return False
    name = PurePosixPath(path).name.lower()
    return name.endswith(PY_SUFFIX) and (name.startswith("test") or name.endswith("_test.py"))


def _is_root_readme(path: str) -> bool:
    """
    Whether `path` is the project's own README at the repository root.

    Only the root file counts: a `docs/README.md` is ordinary documentation, while the root README
    is what PRINCIPLE-005 gates read and what `publish` uploads as the project's front page.
    """
    return "/" not in path and PurePosixPath(path).stem.casefold() == "readme"


def _artifact_rule(path: str) -> Optional[Tuple[str, str]]:
    """The tracked-artifact rule and message for `path`, or None when it is ordinary source."""
    parts = PurePosixPath(path).parts
    name = parts[-1]
    if any(part in ARTIFACT_DIRS or part.endswith(".egg-info") for part in parts[:-1]):
        return ("tracked-artifact",
                "tracked cache or build output; remove it from the index and ignore it")
    if name == ".coverage" or name.startswith(".coverage."):
        return ("tracked-artifact",
                "tracked coverage output; remove it from the index and ignore it")
    if name.endswith(ARTIFACT_SUFFIXES):
        return ("tracked-artifact",
                "tracked cache, log or temporary output; remove it from the index and ignore it")
    if parts and parts[0] == ".aikit" and (name.startswith("corrupt_")
                                           or ".tmp_" in name
                                           or name.endswith((".bak", ".lock"))):
        return ("tracked-artifact",
                "tracked AIKit temporary buffer; run `aikit clean` or remove it from the index")
    return None


def classify_artifacts(tracked: Sequence[str], untracked: Sequence[str]) -> List[Finding]:
    """
    Artifact findings from git's tracked and untracked-non-ignored path lists.

    The rule is decidable from the path alone: a root test module changes default test discovery,
    an untracked root output/source is drift, and a tracked cache is a repository artifact. Pure
    so the unit tier can cover every shape without spawning git (PRINCIPLE-014 R3).
    """
    findings: List[Finding] = []
    for path in tracked:
        rel = path.replace("\\", "/")
        if _is_root_test_module(rel):
            findings.append(Finding(rel, 1, "root-test-module",
                                    "a root test module is imported or collected by the default "
                                    "test runner; move it under tests/ (PRINCIPLE-014 R4)"))
            continue
        artifact = _artifact_rule(rel)
        if artifact is not None:
            findings.append(Finding(rel, 1, artifact[0],
                                    f"{artifact[1]} (PRINCIPLE-014 R4)"))
    for path in untracked:
        rel = path.replace("\\", "/")
        if _is_root_test_module(rel):
            findings.append(Finding(rel, 1, "root-test-module",
                                    "an untracked root test module is imported or collected by "
                                    "the default test runner; move it under tests/ "
                                    "(PRINCIPLE-014 R4)"))
        elif _is_root_readme(rel):
            # Before the output-suffix rule below: an untracked `README.txt` was told to delete
            # itself, which is the opposite of what a project README needs (ADR-171).
            findings.append(Finding(rel, 1, "untracked-readme",
                                    "the project README is not tracked; the gates read it and "
                                    "publish will not ship it, so track it "
                                    "(PRINCIPLE-005 R1)"))
        elif "/" not in rel and (PurePosixPath(rel).suffix == PY_SUFFIX
                                  or PurePosixPath(rel).suffix in ASSET_SUFFIXES):
            findings.append(Finding(rel, 1, "untracked-root-source",
                                    "untracked source at the project root; move it into the "
                                    "package or scripts layout, or track it deliberately "
                                    "(PRINCIPLE-014 R4)"))
        elif "/" not in rel and PurePosixPath(rel).suffix in ROOT_OUTPUT_SUFFIXES:
            findings.append(Finding(rel, 1, "untracked-output",
                                    "untracked root output; delete it or add the exact path to "
                                    ".gitignore (PRINCIPLE-014 R4)"))
    return sorted(findings, key=lambda finding: (finding.path, finding.line, finding.rule))


def _git_paths(root: Path, args: Sequence[str]) -> Tuple[Optional[List[str]], Optional[Finding]]:
    """The NUL-separated path list from one bounded git call, or the finding that replaced it."""
    try:
        proc = subprocess.run(["git", "-C", str(root), *args], capture_output=True, text=True,
                              encoding="utf-8", errors="replace", timeout=GIT_TIMEOUT_SECONDS)
    except (OSError, subprocess.SubprocessError) as error:
        return None, Finding(".", 1, "git-unavailable",
                             f"the artifact scan needs git on PATH: {error}")
    if proc.returncode != 0:
        detail = proc.stderr.strip() or f"git exit code {proc.returncode}"
        return None, Finding(".", 1, "git-unavailable",
                             f"the artifact scan needs a git work tree: {detail[:120]}")
    return [path for path in proc.stdout.split("\0") if path], None


def scan_artifacts(root: Path) -> List[Finding]:
    """Artifact findings for one git work tree, read-only and sorted (PRINCIPLE-014 R4)."""
    tracked, error = _git_paths(root, ["ls-files", "-z"])
    if error is not None:
        return [error]
    untracked, error = _git_paths(root, ["ls-files", "--others", "--exclude-standard", "-z"])
    if error is not None:
        return [error]
    findings = classify_artifacts(tracked or [], untracked or [])
    seen = {finding.path for finding in findings}
    # git's lists omit ignored paths, but discovery still imports an ignored root test module.
    for path in sorted(root.glob("*.py")):
        if path.is_file() and path.name not in seen and _is_root_test_module(path.name):
            findings.append(Finding(path.name, 1, "root-test-module",
                                    "a root test module is imported or collected by the default "
                                    "test runner; move it under tests/ (PRINCIPLE-014 R4)"))
    return sorted(findings, key=lambda finding: (finding.path, finding.line, finding.rule))


def scan_tree(root: Path, artifacts: bool = False) -> List[Finding]:
    """
    Every hygiene finding under `root` in stable order. Generated and vendored directories are
    skipped whole; each surviving file is read once, as UTF-8. `artifacts=True` also asks git
    about untracked outputs, root test modules and tracked caches.
    """
    findings: List[Finding] = []
    for path in sorted(root.rglob("*")):
        parts = path.relative_to(root).parts
        if not path.is_file() or any(part in SKIP_DIRS for part in parts[:-1]):
            continue
        rel = path.relative_to(root).as_posix()
        if path.suffix == PY_SUFFIX or path.suffix in ASSET_SUFFIXES:
            source, gaps = _read_source(rel, path)
            findings.extend(gaps)
            if source is None:
                continue
            if path.suffix == PY_SUFFIX:
                findings.extend(check_python_source(rel, source))
            else:
                findings.extend(check_asset_source(rel, source))
    if artifacts:
        findings.extend(scan_artifacts(root))
    return sorted(findings, key=lambda finding: (finding.path, finding.line, finding.rule))


REPORT_LIMIT = 20


def run_scan(root: Path, artifacts: bool = False) -> int:
    """Scan `root` and print the report; the process exit code (PRINCIPLE-012 R4: terse)."""
    if not root.is_dir():
        print(f"[INVALID USAGE] Not a directory: {root}", file=sys.stderr)
        print("Why: the hygiene scan walks a project workspace.", file=sys.stderr)
        print("Fix: pass --workspace <dir> pointing at the project root.", file=sys.stderr)
        return 2
    findings = scan_tree(root, artifacts=artifacts)
    print("=" * 58)
    print("PROJECT HYGIENE SCAN (PRINCIPLE-003 R4, PRINCIPLE-010, PRINCIPLE-011)")
    print("=" * 58)
    print(f"Scope: {root.resolve()}")
    if artifacts:
        print("Artifacts: git worktree checked (untracked, root tests, tracked caches)")
    if not findings:
        print("[OK] No hygiene findings.")
        print("=" * 58)
        return 0
    print(f"[FAIL] {len(findings)} hygiene finding(s):")
    for finding in findings[:REPORT_LIMIT]:
        print(finding.render())
    if len(findings) > REPORT_LIMIT:
        print(f"   ... and {len(findings) - REPORT_LIMIT} more")
    print("   Why: each finding breaks portability, resource discipline or offline integrity")
    print("     on a machine other than the author's (PRINCIPLE-003 R4, PRINCIPLE-010).")
    print("   Fix: change the line, or document a deliberate exception with")
    print("     `hygiene: allow <reason>` on the finding's line or the line above it.")
    print("=" * 58)
    return 1


KNOWN_FLAGS = {"--workspace", "--artifacts", "--help", "-h"}

HELP_TEXT = """AIKit Project Hygiene Scan (PRINCIPLE-003 R4, PRINCIPLE-010, PRINCIPLE-011 R3)

Usage:
  python scripts/check_project_hygiene.py --workspace <project-dir> [--artifacts]

Rules (Python):
  shell-true          a shell command line parses through the platform shell
  os-system           os.system breaks on spaced paths
  eval-exec           eval() and exec() execute data as code
  subprocess-argv     subprocess arguments must be a list, not a string
  subprocess-timeout  subprocess call without timeout= can hang a gate
  sys-executable      start Python with sys.executable, not a bare interpreter name
  environ-index       os.environ[...] raises KeyError when the variable is unset
  open-encoding       text-mode open() without encoding= reads the locale's encoding
  open-context        open() outside a with block can leak the handle
  silent-except       a broad except whose whole body is pass hides the error
  absolute-path       a machine-specific path literal reaching file access
  unparseable         a syntax error blocks the scan of the file

Rules (static assets .html, .css, .js):
  external-url        the asset loads code, fonts or data from a third party

Rules (--artifacts, decided from git's tracked and untracked file lists):
  root-test-module    a test module at the project root is imported or collected by the runner
  untracked-root-source  source at the project root is not tracked or placed in the layout
  untracked-readme    the root README is not tracked, so the gates and publish cannot see it
  untracked-output    an untracked root .txt/.log/.tmp/.bak/.orig/.rej/.out file is drift
  tracked-artifact    a cache, coverage file or build output is tracked by git

Exceptions:
  Mark a deliberate line with `hygiene: allow <reason>`, on that line or the one directly
  above it; the reason is part of the record.

Exit codes:
  0 clean, 1 findings, 2 argument misuse.
"""


def main(argv: Sequence[str]) -> int:
    """Parse `--workspace` and run; argument misuse returns 2 with the Why/Fix triad."""
    if any(token in ("--help", "-h") for token in argv):
        print(HELP_TEXT)
        return 0
    unknown = [token for token in argv if token.startswith("-") and token not in KNOWN_FLAGS]
    if unknown:
        print(f"[INVALID USAGE] Unrecognized option(s): {', '.join(unknown)}", file=sys.stderr)
        print(f"Why: this scan accepts only {', '.join(sorted(KNOWN_FLAGS))}.", file=sys.stderr)
        print("Fix: run 'python scripts/check_project_hygiene.py --help' for valid options.",
              file=sys.stderr)
        return 2
    root = ROOT_DIR
    if "--workspace" in argv:
        index = argv.index("--workspace")
        if index + 1 >= len(argv) or argv[index + 1].startswith("-"):
            print("[INVALID USAGE] --workspace requires a directory.", file=sys.stderr)
            print("Why: the workspace to scan cannot be inferred from a missing value.",
                  file=sys.stderr)
            print("Fix: pass '--workspace <dir>'.", file=sys.stderr)
            return 2
        root = Path(argv[index + 1])
    return run_scan(root, artifacts="--artifacts" in argv)


if __name__ == "__main__":
    # This CLI prints a project's own file paths, so a non-ASCII name must survive a Windows pipe,
    # whose default encoding is the console code page; `aikit check` reads gate output as UTF-8.
    # Here rather than at import, so a module that imports this one keeps its streams (ADR-189).
    if sys.platform == "win32":
        for stream in (sys.stdout, sys.stderr):
            try:
                stream.reconfigure(encoding="utf-8", errors="replace")
            except (AttributeError, ValueError, OSError):  # hygiene: allow encoding is cosmetic; a stream that cannot change keeps its own
                pass
    sys.exit(main(sys.argv[1:]))
