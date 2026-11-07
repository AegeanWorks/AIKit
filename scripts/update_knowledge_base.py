#!/usr/bin/env python3
"""
Codebase Knowledge Base Auto-Updater & Validator (PRINCIPLE-016)

Inspects the repository AST, extracts exported classes, functions, and docstrings,
and generates the authoritative `knowledge/codebase_map.md`. Also validates
the integrity of all knowledge base documents.
"""

import ast
import copy
import os
import re
import subprocess
import sys
import time
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional, Set, Tuple

ROOT_DIR = Path(__file__).resolve().parent.parent
KNOWLEDGE_DIR = ROOT_DIR / "knowledge"
CODEBASE_MAP_PATH = KNOWLEDGE_DIR / "codebase_map.md"

CORE_DOCS = [
    "INDEX.md",
    "architecture.md",
    "services.md",
    "data_models.md",
    "state_and_ui.md",
    "decisions.md",
    "codebase_map.md",
]
# The seven documents PRINCIPLE-016 R1 requires of every project. AIKit's own extra documents
# (model_benchmarks.md, host_clients.md, principles_audit_ledger.md) are optional: requiring them
# failed every adopter who replaced knowledge/ with their own documents, as README instructs (ADR-117).

IGNORE_DIRS = {
    ".git",
    ".github",
    ".agents",
    ".aikit",
    ".kilo",
    "__pycache__",
    ".pytest_cache",
    ".ruff_cache",
    ".mypy_cache",
    ".tox",
    ".nox",
    "node_modules",
    "venv",
    ".venv",
    "env",
    "build",
    "dist",
    "target",
    ".next",
    ".nuxt",
    ".cache",
    ".vite",
    # The projects AIKit builds: each has its own map and gates, never AIKit's (ADR-119).
    "projects",
}


# Oldest Python the repository supports (README "Runtime Prerequisites", PRINCIPLE-003 R4). Parsing
# with this grammar makes the AST gate reject syntax that only newer interpreters accept, which a
# developer on a newer Python would otherwise never see fail locally.
MIN_PYTHON = (3, 13)

FUNCTION_NODES = (ast.FunctionDef, ast.AsyncFunctionDef)


def fsync_dir(dir_path: Path) -> bool:
    """Flush the directory entry so a completed os.replace survives power loss (PRINCIPLE-013 R1).

    No-op on win32, which exposes no directory handle to sync. Kept local to preserve this
    script's standalone clone-and-run execution (PRINCIPLE-011) with zero cross-script imports.
    """
    if sys.platform == "win32":
        return True
    fd = None
    try:
        fd = os.open(str(dir_path), os.O_RDONLY)
        os.fsync(fd)
        return True
    except OSError as e:
        sys.stderr.write(f"[WARN] Could not fsync directory {dir_path}: {e}\n")
        return False
    finally:
        if fd is not None:
            try:
                os.close(fd)
            except OSError:  # hygiene: allow the fd is discarded after the write completed
                pass


def write_generated_file(file_path: Path, content: str, newline: Optional[str] = None) -> None:
    """
    Atomically persist generated text file (flush + fsync + os.replace + fsync_dir) (PRINCIPLE-013 R1).
    `newline=""` writes `content`'s line endings as they are, for an edit to a file someone else wrote.
    """
    file_path.parent.mkdir(parents=True, exist_ok=True)
    tmp_path = file_path.with_suffix(file_path.suffix + f".tmp_{os.getpid()}_{int(time.time() * 1000)}")
    with open(tmp_path, "w", encoding="utf-8", newline=newline) as f:
        f.write(content)
        f.flush()
        os.fsync(f.fileno())
    os.replace(tmp_path, file_path)
    fsync_dir(file_path.parent)


def render_signature(node: Any, drop_self: bool = False) -> List[str]:
    """
    Render a complete call signature from an AST function node (PRINCIPLE-003, PRINCIPLE-016).

    The catalog is what agents consult before verifying call-sites, so a partial signature is
    an anti-hallucination failure: reading only `args.args` silently omitted `*args`, `**kwargs`,
    and every keyword-only parameter, so `f(a, *, b)` was catalogued as `f(a)`. Positional-only
    parameters are marked with a trailing `/` and keyword-only ones follow a bare `*`, matching
    Python's own signature syntax.
    """
    spec = node.args
    parts: List[str] = []

    posonly = [a.arg for a in getattr(spec, "posonlyargs", [])]
    positional = [a.arg for a in spec.args]
    if drop_self:
        if posonly and posonly[0] in ("self", "cls"):
            posonly = posonly[1:]
        elif positional and positional[0] in ("self", "cls"):
            positional = positional[1:]

    parts.extend(posonly)
    if posonly:
        parts.append("/")
    parts.extend(positional)

    if spec.vararg:
        parts.append(f"*{spec.vararg.arg}")
    elif spec.kwonlyargs:
        parts.append("*")
    parts.extend(a.arg for a in spec.kwonlyargs)

    if spec.kwarg:
        parts.append(f"**{spec.kwarg.arg}")

    return parts


# Extracted symbols keyed by (path, content): a hit can never be stale, and callers receive a deep
# copy so mutating a result cannot leak. Bounded to the files of one repository scan.
_SYMBOL_CACHE: Dict[tuple, Dict[str, Any]] = {}
_SYMBOL_CACHE_MAX = 256
# Parsed trees keyed by content, shared by the codebase map and the lazy-code gate so each file is
# parsed once per run; trees are only read, never mutated.
_TREE_CACHE: Dict[str, ast.Module] = {}


def parse_source(content: str, filename: str) -> ast.Module:
    """`ast.parse` at the minimum supported grammar (PRINCIPLE-003 R7), cached by content."""
    if content not in _TREE_CACHE:
        if len(_TREE_CACHE) >= _SYMBOL_CACHE_MAX:
            _TREE_CACHE.clear()
        _TREE_CACHE[content] = ast.parse(content, filename=filename, feature_version=MIN_PYTHON)
    return _TREE_CACHE[content]


def extract_python_symbols(file_path: Path, strict: bool = False) -> Dict[str, Any]:
    """Parse a python file with AST and extract docstrings, classes, and functions (PRINCIPLE-003)."""
    try:
        content = file_path.read_text(encoding="utf-8")
    except Exception as e:
        if strict:
            raise ValueError(f"[PRINCIPLE-003 AST FAILURE] Unreadable file {file_path}: {e}") from e
        return {"error": str(e), "classes": [], "functions": [], "docstring": None}
    key = (str(file_path), content)
    if key in _SYMBOL_CACHE:
        return copy.deepcopy(_SYMBOL_CACHE[key])
    result = _extract_symbols_uncached(file_path, content, strict)
    if "error" not in result:
        if len(_SYMBOL_CACHE) >= _SYMBOL_CACHE_MAX:
            _SYMBOL_CACHE.clear()
        _SYMBOL_CACHE[key] = copy.deepcopy(result)
    return result


def _extract_symbols_uncached(file_path: Path, content: str, strict: bool) -> Dict[str, Any]:
    """AST extraction proper; see extract_python_symbols()."""
    try:
        tree = parse_source(content, str(file_path))
    except Exception as e:
        if strict:
            raise ValueError(f"[PRINCIPLE-003 AST FAILURE] Syntax error in {file_path}: {e}") from e
        return {"error": str(e), "classes": [], "functions": [], "docstring": None}

    module_docstring = ast.get_docstring(tree)
    classes = []
    functions = []

    for node in tree.body:
        if isinstance(node, ast.ClassDef):
            class_doc = ast.get_docstring(node)
            methods = []
            for item in node.body:
                if isinstance(item, FUNCTION_NODES):
                    decorators = {ast.unparse(d).split(".")[-1] for d in item.decorator_list}
                    kind = "property" if decorators & {"property", "cached_property"} else "method"
                    methods.append({
                        "name": item.name,
                        "args": render_signature(item, drop_self=True),
                        "is_async": isinstance(item, ast.AsyncFunctionDef),
                        "kind": kind,
                        "docstring": ast.get_docstring(item)
                    })
            classes.append({
                "name": node.name,
                "docstring": class_doc,
                "methods": methods
            })
        elif isinstance(node, FUNCTION_NODES):
            functions.append({
                "name": node.name,
                "args": render_signature(node),
                "is_async": isinstance(node, ast.AsyncFunctionDef),
                "docstring": ast.get_docstring(node)
            })

    line_count = len(content.splitlines())
    return {
        "docstring": module_docstring,
        "classes": classes,
        "functions": functions,
        "line_count": line_count,
        "size_bytes": len(content.encode("utf-8"))
    }


# A root `.gitignore` line naming one directory (`name/`, `/name/`) or all of its contents
# (`name/*`, `/name/*`): no other glob, no negation.
GITIGNORED_DIR_RE = re.compile(r"^/?([^\s/*?\[\]!#]+)/(?:\*)?$")


def gitignored_top_dirs(root: Path) -> Set[str]:
    """
    The top-level directories `root/.gitignore` excludes by name. Git never tracks them, so their
    code is no part of the repository and must not enter its map or structure checks (ADR-201).
    Only the plain directory form and the all-contents form (`/reports/*`) are recognised; other
    glob and nested patterns are left to git.
    """
    try:
        lines = (root / ".gitignore").read_text(encoding="utf-8", errors="replace").splitlines()
    except OSError:
        return set()
    return {m.group(1) for m in map(GITIGNORED_DIR_RE.match, (line.strip() for line in lines)) if m}


def find_python_files(root: Path) -> List[Path]:
    """
    Every Python file under `root`, skipping `IGNORE_DIRS`. Ignored directories are pruned while
    walking, relative to `root`: `rglob` descended into `.git` and friends (16ms vs 0.8ms here) and
    matched ignored names anywhere in the absolute path, so a clone under `C:\\build\\` or
    `/home/u/env/` would have catalogued nothing.
    """
    py_files: List[Path] = []
    skipped_at_top = IGNORE_DIRS | gitignored_top_dirs(root)
    for dirpath, dirnames, filenames in os.walk(root):
        skipped = skipped_at_top if Path(dirpath) == root else IGNORE_DIRS
        dirnames[:] = [d for d in dirnames if d not in skipped]
        py_files += [
            Path(dirpath) / name
            for name in filenames
            if name.endswith(".py") and not name.startswith(".tmp_")
        ]
    return sorted(py_files)


# The map is 2,275 lines here and 6,872 in neurocore, past what PRINCIPLE-004 lets one read take
# and PRINCIPLE-012's payload cap, so `--digest` gives one line per module inside both (IDEA-005).
DIGEST_MAX_LINES = 100
DIGEST_MAX_CHARS = 16_000
DIGEST_PURPOSE_CHARS = 80
# Folders whose code is meant for reuse come first, so a cut drops app code before shared code (IDEA-044).
DIGEST_SHARED_HINTS = ("util", "helper", "lib", "common", "shared", "core", "service", "schema")
DigestRow = Tuple[str, int, int, int, Optional[str]]


def build_digest(rows: List[DigestRow], max_lines: int = DIGEST_MAX_LINES,
                 max_chars: int = DIGEST_MAX_CHARS, map_name: str = "codebase_map.md") -> str:
    """
    `path  <lines>L <classes>C <functions>F  purpose` per module, within both budgets, shared-code
    folders first. Pure and deterministic; anything cut is counted on a closing `truncated:` line.
    """
    def shared(path: str) -> bool:
        return any(hint in part for part in path.split("/")[:-1] for hint in DIGEST_SHARED_HINTS)

    def row_line(row: DigestRow) -> str:
        path, lines, classes, functions, docstring = row
        purpose = (docstring or "").strip().split("\n")[0] or "-"
        if len(purpose) > DIGEST_PURPOSE_CHARS:
            purpose = purpose[:DIGEST_PURPOSE_CHARS - 3] + "..."
        return f"{path}  {lines}L {classes}C {functions}F  {purpose}"

    def cut(count: int) -> str:
        return f"truncated: {count} module(s) omitted; {map_name} lists every symbol"

    ordered = sorted(rows, key=lambda row: (not shared(row[0]), row[0]))
    out = [f"# {len(rows)} modules, {sum(row[1] for row in rows):,} lines (full symbols: {map_name})"]
    for index, row in enumerate(ordered):
        rest = len(ordered) - index - 1
        candidate = out + [row_line(row)] + ([cut(rest)] if rest else [])
        if len(candidate) > max_lines or len("\n".join(candidate)) > max_chars:
            out.append(cut(len(ordered) - index))
            break
        out.append(row_line(row))
    return "\n".join(out)


def digest_rows(root: Path) -> List[DigestRow]:
    """One digest row per Python module under `root`, from the AST extractor the map uses."""
    rows: List[DigestRow] = []
    for file_path in find_python_files(root):
        info = extract_python_symbols(file_path, strict=False)
        rel = file_path.relative_to(root).as_posix()
        docstring = "(syntax error: not catalogued)" if "error" in info else info.get("docstring")
        rows.append((rel, info.get("line_count", 0), len(info.get("classes", [])),
                     len(info.get("functions", [])), docstring))
    return rows


def generate_codebase_map(root: Optional[Path] = None, strict: bool = True) -> str:
    """Generate the markdown content for knowledge/codebase_map.md with AST validation (PRINCIPLE-003)."""
    target_root = root or ROOT_DIR
    lines = [
        "# Codebase Map & Symbol Catalog 🗺️",
        "",
        "> **AUTO-GENERATED & VERIFIED BY `scripts/update_knowledge_base.py`**",
        "> This document provides an automated, up-to-date registry of all modules, classes, and exported functions across this repository.",
        "",
        "---",
        ""
    ]

    files_to_scan = find_python_files(target_root)

    total_classes = 0
    total_functions = 0
    total_methods = 0
    total_lines = 0

    modules_data = []
    syntax_errors = []

    for file_path in files_to_scan:
        rel_path = file_path.relative_to(target_root)
        info = extract_python_symbols(file_path, strict=False)
        if "error" in info:
            syntax_errors.append((rel_path, info["error"]))
            continue

        c_count = len(info.get("classes", []))
        f_count = len(info.get("functions", []))
        l_count = info.get("line_count", 0)

        total_classes += c_count
        total_functions += f_count
        total_methods += sum(len(c.get("methods", [])) for c in info.get("classes", []))
        total_lines += l_count

        modules_data.append((rel_path, info))

    if syntax_errors and strict:
        err_msg = "\n".join([f"  - {p}: {err}" for p, err in syntax_errors])
        raise ValueError(
            f"[PRINCIPLE-003 AST GATE FAILURE] Found {len(syntax_errors)} invalid Python file(s) with syntax errors:\n{err_msg}"
        )

    lines.append(f"## 📊 Codebase Metrics")
    lines.append(f"- **Total Python Modules**: `{len(modules_data)}`")
    lines.append(f"- **Total Classes**: `{total_classes}`")
    lines.append(f"- **Total Top-Level Functions**: `{total_functions}`")
    lines.append(f"- **Total Class Methods**: `{total_methods}`")
    lines.append(f"- **Total Source Lines**: `{total_lines}`")
    lines.append("")
    lines.append("---")
    lines.append("")
    lines.append("## 📦 Modules & Exported Symbols")
    lines.append("")

    for rel_path, info in modules_data:
        str_path = str(rel_path).replace("\\", "/")
        lines.append(f"### [`{str_path}`]({str_path})")
        if info.get("docstring"):
            clean_doc = info["docstring"].strip().split("\n")[0]
            lines.append(f"> *{clean_doc}*")
            lines.append("")

        lines.append(f"**Size**: `{info.get('line_count', 0)}` lines (`{info.get('size_bytes', 0)}` bytes)")
        lines.append("")

        classes = info.get("classes", [])
        if classes:
            lines.append("**Classes:**")
            for c in classes:
                c_name = c["name"]
                c_doc = f" - *{c['docstring'].strip().split(chr(10))[0]}*" if c.get("docstring") else ""
                lines.append(f"- `class {c_name}`{c_doc}")
                for m in c.get("methods", []):
                    m_doc = f" - *{m['docstring'].strip().split(chr(10))[0]}*" if m.get("docstring") else ""
                    if m.get("kind") == "property":
                        lines.append(f"  - Property `.{m['name']}`{m_doc}")
                        continue
                    args_str = ", ".join(m["args"])
                    m_kind = "async def " if m.get("is_async") else ""
                    lines.append(f"  - Method `{m_kind}.{m['name']}({args_str})`{m_doc}")
            lines.append("")

        functions = info.get("functions", [])
        if functions:
            lines.append("**Functions:**")
            for f in functions:
                args_str = ", ".join(f["args"])
                f_doc = f" - *{f['docstring'].strip().split(chr(10))[0]}*" if f.get("docstring") else ""
                f_kind = "async def" if f.get("is_async") else "def"
                lines.append(f"- `{f_kind} {f['name']}({args_str})`{f_doc}")
            lines.append("")

        lines.append("---")
        lines.append("")

    return "\n".join(lines)


def validate_knowledge_links(knowledge_dir: Path) -> List[str]:
    """Verify that all relative file links in knowledge/INDEX.md physically exist on disk (PRINCIPLE-016)."""
    index_path = knowledge_dir / "INDEX.md"
    if not index_path.exists():
        return [f"INDEX.md missing in {knowledge_dir}"]
    content = index_path.read_text(encoding="utf-8")
    link_pattern = re.compile(r'\[([^\]]+)\]\(([^)#]+)(?:#[^)]*)?\)')
    broken = []
    for match in link_pattern.finditer(content):
        target = match.group(2).strip()
        if target.startswith("http://") or target.startswith("https://") or target.startswith("mailto:"):
            continue
        target_path = (knowledge_dir / target).resolve()
        if not target_path.exists():
            broken.append(f"{target} (referenced in INDEX.md)")
    return broken


def audit_adr_register(decisions: str) -> List[str]:
    """
    ADR IDs must be unique and consecutive (PRINCIPLE-016 R3, PRINCIPLE-000 R3). Two sessions that
    picked "the next number" from memory wrote ADR-064 and ADR-065 twice; nothing noticed.
    """
    errors: List[str] = []
    previous = None
    # Template examples live inside HTML comments; they are documentation, not register entries.
    visible = re.sub(r"<!--.*?-->", "", decisions, flags=re.S)
    for number in (int(n) for n in re.findall(r"^### ADR-(\d+):", visible, re.M)):
        if previous is not None and number != previous + 1:
            kind = "duplicates or precedes" if number <= previous else "skips after"
            errors.append(f"ADR-{number:03d} {kind} ADR-{previous:03d}; the next ID must be ADR-{previous + 1:03d}")
        previous = number if previous is None else max(previous, number)
    return errors


def check_codebase_map_freshness(knowledge_dir: Optional[Path] = None, root: Optional[Path] = None, strict: bool = True) -> bool:
    """
    Check if codebase_map.md accurately reflects current codebase AST (PRINCIPLE-016).
    Returns True if fresh. If stale and strict=True, raises ValueError. If stale and strict=False, returns False.
    """
    target_root = root or ROOT_DIR
    k_dir = knowledge_dir or (target_root / "knowledge")
    map_path = k_dir / "codebase_map.md"
    if not map_path.exists():
        if strict:
            raise ValueError(f"[PRINCIPLE-016 CODEBASE MAP MISSING] {map_path} does not exist.")
        return False

    current_content = map_path.read_text(encoding="utf-8").replace("\r\n", "\n").strip()
    generated_content = generate_codebase_map(root=target_root, strict=strict).replace("\r\n", "\n").strip()
    is_fresh = (current_content == generated_content)
    if not is_fresh and strict:
        raise ValueError(
            f"[PRINCIPLE-016 CODEBASE MAP STALE] {map_path.name} is out of sync with AST. "
            "Run 'python scripts/update_knowledge_base.py' to synchronize."
        )
    return is_fresh


def update_and_validate(knowledge_dir: Optional[Path] = None, root: Optional[Path] = None, strict: bool = True):
    target_root = root or ROOT_DIR
    k_dir = knowledge_dir or (target_root / "knowledge")
    k_dir.mkdir(parents=True, exist_ok=True)
    map_path = k_dir / "codebase_map.md"

    # 1. Update codebase_map.md atomically (fsync + replace) with strict AST verification (PRINCIPLE-003)
    map_content = generate_codebase_map(root=target_root, strict=strict)
    write_generated_file(map_path, map_content)
    try:
        rel_str = str(map_path.relative_to(target_root))
    except ValueError:
        rel_str = str(map_path)
    print(f"[UPDATED] {rel_str}")

    # 2. Validate all core knowledge base docs exist
    missing = []
    for doc in CORE_DOCS:
        p = k_dir / doc
        if not p.exists():
            missing.append(doc)

    if missing:
        msg = f"Missing knowledge base documents: {', '.join(missing)}"
        if strict:
            raise ValueError(f"[PRINCIPLE-016 KNOWLEDGE BASE GAP] {msg}")
        print(f"[WARN] {msg}")
    else:
        print(f"[OK] Verified {len(CORE_DOCS)} knowledge base documents in {k_dir.name}/")

    # 3. Validate link integrity in knowledge/INDEX.md (PRINCIPLE-016)
    broken_links = validate_knowledge_links(k_dir)
    if broken_links:
        msg = f"Broken relative links in {k_dir.name}/INDEX.md: {', '.join(broken_links)}"
        if strict:
            raise ValueError(f"[PRINCIPLE-016 LINK INTEGRITY FAILURE] {msg}")
        print(f"[WARN] {msg}")
    else:
        print(f"[OK] Verified link integrity in {k_dir.name}/INDEX.md")

    # 4. ADR IDs unique and consecutive (PRINCIPLE-016 R3)
    decisions = k_dir / "decisions.md"
    adr_errors = audit_adr_register(decisions.read_text(encoding="utf-8")) if decisions.exists() else []
    if adr_errors:
        msg = f"ADR register out of order in {k_dir.name}/decisions.md: {'; '.join(adr_errors)}"
        if strict:
            raise ValueError(f"[PRINCIPLE-016 ADR REGISTER] {msg}")
        print(f"[WARN] {msg}")
    else:
        print(f"[OK] Verified ADR IDs are unique and consecutive in {k_dir.name}/decisions.md")


README_MAX_CHARS = 32_500
README_LABELS = (
    "Cold-Start Quick Reference",
    "**Runtime Prerequisites**:",
    "**Canonical Regression Shield Gate**:",
    "What's Inside",
)
_TREE_LINE = re.compile(r"^((?:│   |    )*)(?:├── |└── )(.+)$")
_SCRIPT_COMMAND = re.compile(r"python (scripts/[\w.]+\.py)([^`\n|]*)")
_UNITTEST_COMMAND = re.compile(r"python -m unittest (tests\.\w+)")
_AIKIT_COMMAND = re.compile(r"python aikit\.py (?:--workspace \S+ )?([a-z][\w-]*)")
# The project CLI declares each subcommand once; parsed from source, never imported, because
# `aikit_cli` imports this module (ADR-147).
_AIKIT_SUBCOMMAND = re.compile(r'(?:add_parser|project_command)\(\s*"([a-z][\w-]*)"')
_FLAG = re.compile(r"(?<![\w-])(--[a-z][a-z-]*)")


_LAZY_MARKER = re.compile(r"#\s*(TODO|FIXME|XXX|HACK)\b|#.*?\b(TODO|FIXME|XXX|HACK)(?:\([^)]*\))?:")
_UNNAMED_SUPPRESSION = re.compile(r"#\s*(type:\s*ignore(?!\[)|noqa(?!\s*:))")
_LAZY_WORDS = re.compile(r"TODO|FIXME|XXX|HACK|type:\s*ignore|noqa")
_EXEMPT_DECORATORS = {"abstractmethod", "overload"}
_EXEMPT_BASES = {"Protocol", "ABC"}


def _names(nodes) -> set:
    """Bare names of decorators or base classes (`abc.abstractmethod` -> `abstractmethod`)."""
    return {n.attr if isinstance(n, ast.Attribute) else getattr(n, "id", "")
            for n in (d.func if isinstance(d, ast.Call) else d for d in nodes)}


def audit_lazy_code(source: str, rel: str) -> List[str]:
    """
    PRINCIPLE-007 R3 as a gate: a `TODO`/`FIXME`/`XXX`/`HACK` comment marker, a `# type: ignore`
    or `# noqa` that names no error code, and a stub - a function whose body is only `pass`, `...`
    or `raise NotImplementedError` - unless it is abstract, an overload, or declared in a
    Protocol or ABC. The rule listed these acts for years with nothing checking them.
    """
    errors: List[str] = []
    # Tokenizing is the slow part; a file without any marker word cannot hold a marker comment.
    if _LAZY_WORDS.search(source):
        import io
        import tokenize
        try:
            for token in tokenize.generate_tokens(io.StringIO(source).readline):
                if token.type != tokenize.COMMENT:
                    continue
                if _LAZY_MARKER.match(token.string):
                    errors.append(f"{rel}:{token.start[0]}: '{token.string.strip()[:40]}' marks unfinished code")
                if _UNNAMED_SUPPRESSION.search(token.string):
                    errors.append(f"{rel}:{token.start[0]}: suppression names no error code")
        except (tokenize.TokenError, IndentationError, SyntaxError):  # hygiene: allow the AST gate reports an unparsable file with its own line
            pass  # the AST gate (PRINCIPLE-003 R7) reports unparsable files with file and line
    try:
        tree = parse_source(source, rel)
    except SyntaxError:
        return errors
    # One walk; `in_contract` marks the direct members of a Protocol or ABC class.
    stack = [(tree, False)]
    while stack:
        node, in_contract = stack.pop()
        for child in ast.iter_child_nodes(node):
            if isinstance(child, ast.ClassDef):
                stack.append((child, bool(_names(child.bases) & _EXEMPT_BASES)))
                continue
            if isinstance(child, (ast.FunctionDef, ast.AsyncFunctionDef)):
                if not in_contract and not _names(child.decorator_list) & _EXEMPT_DECORATORS and _is_stub(child):
                    errors.append(f"{rel}:{child.lineno}: function '{child.name}' is a stub")
            stack.append((child, False))
    return sorted(errors, key=lambda e: int(e.split(":")[1]))


def _is_stub(fn: ast.AST) -> bool:
    """A body (after any docstring) that is only `pass`, `...` or `raise NotImplementedError`."""
    body = fn.body[1:] if ast.get_docstring(fn) is not None else fn.body
    if len(body) != 1:
        return False
    stmt = body[0]
    if isinstance(stmt, ast.Pass):
        return True
    if isinstance(stmt, ast.Expr) and isinstance(stmt.value, ast.Constant):
        return stmt.value.value is Ellipsis
    if isinstance(stmt, ast.Raise) and stmt.exc is not None:
        exc = stmt.exc.func if isinstance(stmt.exc, ast.Call) else stmt.exc
        return getattr(exc, "id", None) == "NotImplementedError"
    return False


JUNK_DRAWER_NAMES = {"utils", "util", "helpers", "helper", "common", "misc"}
ROLE_METHOD_LIMIT = 5
SUBPROCESS_BLOCKING = {"run", "call", "check_call", "check_output"}


def audit_architecture(modules: Dict[str, str]) -> List[str]:
    """
    The parts of PRINCIPLE-009 and PRINCIPLE-010 every module can be checked against: no
    junk-drawer module name (P009 R1), a Protocol or ABC declares 1 to 5 methods (P009 R2), no
    import cycle between the repository's own modules and no assignment to another object's
    `_private` attribute (P009 R5), every blocking subprocess call has a timeout (P010 R3),
    and `open()` runs only in a `with` statement (P010 R4).
    `modules` maps a module's dotted name to its source.
    """
    errors: List[str] = []
    graph: Dict[str, set] = {}
    by_leaf = {m.rsplit(".", 1)[-1]: m for m in modules}
    for name, source in modules.items():
        leaf = name.rsplit(".", 1)[-1]
        if leaf in JUNK_DRAWER_NAMES:
            errors.append(f"{name}: '{leaf}' is a junk-drawer module name; name it after what it holds")
        try:
            tree = parse_source(source, name)
        except SyntaxError:
            continue
        imported = set()
        managed = {id(item.context_expr) for node in ast.walk(tree)
                   if isinstance(node, (ast.With, ast.AsyncWith)) for item in node.items}
        for node in ast.walk(tree):
            # P009 R5: `other._x = v` reaches past a module's interface; `self`/`cls` is its own.
            if isinstance(node, (ast.Assign, ast.AugAssign, ast.AnnAssign)):
                targets = node.targets if isinstance(node, ast.Assign) else [node.target]
                for target in targets:
                    if (isinstance(target, ast.Attribute) and target.attr.startswith("_")
                            and not target.attr.startswith("__")
                            and getattr(target.value, "id", None) not in ("self", "cls", None)):
                        owner = ast.unparse(target.value)
                        errors.append(f"{name}:{target.lineno}: assigns to {owner}.{target.attr}, "
                                      f"another object's private attribute (PRINCIPLE-009 R5)")
            if isinstance(node, ast.Call):
                func = node.func
                owner = getattr(getattr(func, "value", None), "id", "")
                if (owner == "subprocess" and getattr(func, "attr", "") in SUBPROCESS_BLOCKING
                        and not any(k.arg == "timeout" for k in node.keywords)):
                    errors.append(f"{name}:{node.lineno}: subprocess.{func.attr} without timeout= (PRINCIPLE-010 R3)")
                # Builtin open() and method-style Path.open(); os.open returns a raw descriptor that
                # R4 covers with try/finally instead.
                is_open = ((isinstance(func, ast.Name) and func.id == "open")
                           or (isinstance(func, ast.Attribute) and func.attr == "open" and owner != "os"))
                if is_open and id(node) not in managed:
                    errors.append(f"{name}:{node.lineno}: open() outside a with statement (PRINCIPLE-010 R4)")
            if (isinstance(node, ast.Subscript) and isinstance(node.ctx, ast.Load)
                    and isinstance(node.value, ast.Attribute) and node.value.attr == "environ"
                    and getattr(node.value.value, "id", "") == "os"):
                errors.append(f"{name}:{node.lineno}: os.environ[...] read; use os.getenv() with a default (PRINCIPLE-011 R3)")
            if isinstance(node, ast.Import):
                imported |= {a.name for a in node.names}
            elif isinstance(node, ast.ImportFrom) and node.module and not node.level:
                imported.add(node.module)
            elif isinstance(node, ast.ClassDef) and _names(node.bases) & _EXEMPT_BASES:
                methods = [b for b in node.body if isinstance(b, (ast.FunctionDef, ast.AsyncFunctionDef))]
                if not 1 <= len(methods) <= ROLE_METHOD_LIMIT:
                    errors.append(f"{name}: role '{node.name}' declares {len(methods)} methods; "
                                  f"a role declares 1 to {ROLE_METHOD_LIMIT}")
        # A dependency is any repository module named by an import, by full or last dotted name.
        graph[name] = {m for i in imported for m in (i if i in modules else by_leaf.get(i.rsplit(".", 1)[-1]),)
                       if m and m != name}
    seen: Dict[str, int] = {}
    def visit(node: str, path: List[str]) -> None:
        seen[node] = 1
        for nxt in sorted(graph.get(node, ())):
            if seen.get(nxt) == 1:
                cycle = path[path.index(nxt):] + [nxt]
                errors.append(f"import cycle: {' -> '.join(cycle)}")
            elif nxt not in seen:
                visit(nxt, path + [nxt])
        seen[node] = 2
    for start in sorted(graph):
        if start not in seen:
            visit(start, [start])
    return errors


def check_architecture(root: Path = ROOT_DIR) -> List[str]:
    """`audit_architecture` over every Python file the codebase map covers."""
    modules = {path.relative_to(root).with_suffix("").as_posix().replace("/", "."): path.read_text(encoding="utf-8")
               for path in find_python_files(root)}
    return audit_architecture(modules)


def report_architecture(errors: List[str]) -> bool:
    """Print architecture findings with the remediation triad (PRINCIPLE-011 R6); True when clean."""
    if not errors:
        print("[OK] No junk-drawer module, oversized role, import cycle, untimed subprocess, unmanaged open() or raw os.environ read (PRINCIPLE-009, PRINCIPLE-010, PRINCIPLE-011)")
        return True
    print(f"[FAIL] Code structure ({len(errors)}):")
    for error in errors[:20]:
        print(f"   - {error}")
    print("   Why: each one couples modules (PRINCIPLE-009), can hang or leak (PRINCIPLE-010) or crash on a missing variable (PRINCIPLE-011).")
    print("   Fix: rename the module, split the role, break the cycle, add timeout=, use with, or use os.getenv().")
    return False


def check_lazy_code(root: Path = ROOT_DIR) -> List[str]:
    """`audit_lazy_code` over every Python file the codebase map covers."""
    errors: List[str] = []
    for path in find_python_files(root):
        errors += audit_lazy_code(path.read_text(encoding="utf-8"), path.relative_to(root).as_posix())
    return errors


def report_lazy_code(errors: List[str]) -> bool:
    """Print lazy-code findings with the remediation triad (PRINCIPLE-011 R6); True when clean."""
    if not errors:
        print("[OK] No unfinished-code markers, stubs or unnamed suppressions (PRINCIPLE-007 R3)")
        return True
    print(f"[FAIL] Unfinished code ({len(errors)}):")
    for error in errors[:20]:
        print(f"   - {error}")
    if len(errors) > 20:
        print(f"   ... and {len(errors) - 20} more")
    print("   Why: a marker or stub reports as done code that is not (PRINCIPLE-007 R3, PRINCIPLE-000 R5).")
    print("   Fix: finish the code, or name the error code a suppression silences (e.g. '# noqa: E402').")
    return False


README_TEMPLATE = ".agents/rules/readme_quickref.md.template"
README_PLACEHOLDER = "<FILL:"


def quick_reference_errors(readme: str) -> List[str]:
    """
    The structure PRINCIPLE-005 R1 states, not just its words: a heading, then inside its section
    a `- **Runtime Prerequisites**:` line naming a version and a fenced command right after the
    test-gate label. A substring check passed a README that merely mentioned the labels in prose.
    """
    heading = re.search(r"^(#{1,6}) [^\n]*Cold-Start Quick Reference", readme, re.M)
    if not heading:
        return ["README.md has no heading containing 'Cold-Start Quick Reference' (R1)"]
    rest = readme[heading.end():]
    following = re.search(rf"^#{{1,{len(heading.group(1))}}} ", rest, re.M)
    section = rest[:following.start()] if following else rest
    errors: List[str] = []
    prerequisites = re.search(r"^- \*\*Runtime Prerequisites\*\*:([^\n]*)", section, re.M)
    if not prerequisites:
        errors.append("the Quick Reference has no line starting '- **Runtime Prerequisites**:' (R1)")
    elif not re.search(r"\d", prerequisites.group(1)):
        errors.append("'- **Runtime Prerequisites**:' names no minimum version (R1)")
    if not re.search(r"\*\*Canonical Regression Shield Gate\*\*:[ \t]*\n[ \t]*```[^\n]*\n[ \t]*\S", section):
        errors.append("the Quick Reference has no fenced command right after "
                      "'**Canonical Regression Shield Gate**:' (R1)")
    return errors


def parse_readme_tree(readme: str) -> List[str]:
    """
    Paths in the first ```text block after "What's Inside" (PRINCIPLE-005 R5), relative to the
    repository root; a directory ends with '/'. The block's first line (the root) is skipped.
    """
    heading = re.search(r"^#+ .*What's Inside", readme, re.M)  # a heading, never a mention in prose
    fence = readme.find("```text\n", heading.end()) if heading else -1
    if fence < 0:
        return []
    block = readme[fence + len("```text\n"):readme.find("```", fence + len("```text\n"))]
    paths: List[str] = []
    stack: List[str] = []
    for line in block.splitlines():
        match = _TREE_LINE.match(line)
        if not match:
            continue
        name = match.group(2).split("<-")[0].strip()
        stack = stack[:len(match.group(1)) // 4] + [name.rstrip("/")]
        paths.append("/".join(stack) + ("/" if name.endswith("/") else ""))
    return paths


def audit_readme(
    readme: str,
    tracked: Optional[List[str]],
    exists: Callable[[str], bool],
    script_source: Callable[[str], Optional[str]],
) -> List[str]:
    """
    Every PRINCIPLE-005 rule a program can decide, as one error per violation. Pure: the caller
    supplies the tracked files (None when git is unavailable), a path test and a script reader.
    It replaces a test holding a fixed list of AIKit paths, which never noticed a new file
    missing from the tree, a dead path in it, or a documented flag that no script declares.
    """
    errors: List[str] = []
    if len(readme) > README_MAX_CHARS:
        errors.append(f"README.md has {len(readme):,} chars; the limit is {README_MAX_CHARS:,} (R1)")
    errors += quick_reference_errors(readme)
    if README_PLACEHOLDER in readme:
        errors.append(f"README.md still holds an unfilled '{README_PLACEHOLDER}' placeholder (R1); "
                      "only the project's own facts can replace it")

    tree = parse_readme_tree(readme)
    if not tree:
        errors.append("README.md has no ```text directory tree after \"What's Inside\" (R5)")
    listed = {p.rstrip("/") for p in tree}
    errors += [f"README.md tree lists '{p}', which does not exist (R5)" for p in tree if not exists(p.rstrip("/"))]
    if tree and tracked is not None:
        # A tracked file deleted in the working copy is on its way out; the tree describes what
        # exists, the same rule the dead-path check above applies (ADR-214).
        tracked = [t for t in tracked if exists(t)]
        required = {t.split("/")[0] for t in tracked}
        for directory in (p.rstrip("/") for p in tree if p.endswith("/") and any(q != p and q.startswith(p) for q in tree)):
            prefix = directory + "/"
            required |= {prefix + t[len(prefix):].split("/")[0] for t in tracked if t.startswith(prefix)}
        errors += [f"README.md tree omits tracked '{p}' (R5)" for p in sorted(required - listed)]

    for match in _SCRIPT_COMMAND.finditer(readme):
        script = match.group(1)
        source = script_source(script)
        if source is None:
            errors.append(f"README.md runs '{script}', which does not exist (R3)")
            continue
        errors += [f"README.md passes {flag} to {script}, which does not declare it (R3)"
                   for flag in _FLAG.findall(match.group(2)) if f'"{flag}"' not in source]
    # The `aikit.py` grammar lives in aikit_parser.py, apart from the commands, so `--help` can
    # load it alone (ADR-180); the subcommands are read where they are declared.
    documented = sorted(set(_AIKIT_COMMAND.findall(readme)))
    cli_source = script_source("scripts/aikit_parser.py")
    if cli_source:
        known = set(_AIKIT_SUBCOMMAND.findall(cli_source))
        errors += [f"README.md runs 'python aikit.py {cmd}', which the CLI does not declare (R3)"
                   for cmd in documented if cmd not in known]
    elif documented and exists("aikit.py"):
        # Where aikit.py lives, its grammar file must too: skipping here switched this check off
        # without a word whenever the file was renamed. An adopter project has no aikit.py of its
        # own and runs the commands from the AIKit folder, so it still skips (ADR-184).
        errors.append("README.md runs `python aikit.py` commands, but scripts/aikit_parser.py, "
                      "which declares them, does not exist (R3)")
    for module in _UNITTEST_COMMAND.findall(readme):
        if not exists(module.replace(".", "/") + ".py"):
            errors.append(f"README.md runs test module '{module}', which does not exist (R3)")
    return sorted(set(errors))


# Any `python <path>.py`, not only `scripts/*.py`: the README rule above never saw the ten
# idea-catcher hints naming `tools/idea_catcher.py` after ADR-252 removed it (IDEA-406).
_PYTHON_SCRIPT_REF = re.compile(r"python3?\s+(?:-I\s+)?((?:[\w.-]+/)*[\w-]+\.py)\b")
# The marker check_project_hygiene.py honours: an example, or a path relative to a named project.
_REFERENCE_ALLOW = re.compile(r"hygiene:\s*allow\s+\S{3,}")
_REFERENCE_SUFFIXES = (".py", ".md", ".mdc", ".jsonc")
_REFERENCE_HOST_FILES = {".clinerules", ".cursorrules", ".windsurfrules"}
# The ADR register is append-only history that may name what has since moved; tests build dead
# references on purpose; the rest are other repositories or vendored text.
_REFERENCE_SKIP = ("knowledge/decisions.md", "tests/", "projects/", "references/", "scratch/", "licenses/")


def script_reference_sources(tracked: List[str]) -> List[str]:
    """The tracked files whose `python <path>.py` references must resolve: code and instructions."""
    return sorted(rel for rel in tracked
                  if not rel.startswith(_REFERENCE_SKIP)
                  and (rel.endswith(_REFERENCE_SUFFIXES) or rel in _REFERENCE_HOST_FILES))


def audit_script_references(sources: Dict[str, str], exists: Callable[[str], bool]) -> List[str]:
    """
    One error per `python <path>.py` naming a file that does not exist, as `file:line`. Pure. A
    `hygiene: allow <reason>` marker on the line or the line above exempts it.
    """
    errors: List[str] = []
    for rel, text in sorted(sources.items()):
        lines = text.splitlines()
        for number, line in enumerate(lines, 1):
            for match in _PYTHON_SCRIPT_REF.finditer(line):
                script = match.group(1)
                allowed = _REFERENCE_ALLOW.search(line) or (number > 1 and _REFERENCE_ALLOW.search(lines[number - 2]))
                if not exists(script) and not allowed:
                    errors.append(f"{rel}:{number} runs '{script}', which does not exist")
    return errors


def tracked_files(root: Path) -> Optional[List[str]]:
    """`git ls-files` for `root` (bounded, PRINCIPLE-010 R3), or None when git is unavailable."""
    try:
        listing = subprocess.run(["git", "ls-files", "-z"], cwd=root, capture_output=True,
                                 text=True, encoding="utf-8", errors="replace", timeout=10)
        if listing.returncode == 0:
            return [p for p in listing.stdout.split("\0") if p]
    except (OSError, subprocess.SubprocessError):  # hygiene: allow git is optional here; the caller prints the WARN that follows
        pass
    return None


def check_script_references(root: Path = ROOT_DIR) -> Optional[List[str]]:
    """Run `audit_script_references` over `root`'s tracked sources; None when git is unavailable."""
    tracked = tracked_files(root)
    if tracked is None:
        return None
    sources: Dict[str, str] = {}
    for rel in script_reference_sources(tracked):
        path = root / rel
        if path.is_file():
            with open(path, encoding="utf-8", errors="replace") as handle:
                sources[rel] = handle.read()
    return audit_script_references(sources, lambda rel: (root / rel).is_file())


def report_script_references(errors: Optional[List[str]]) -> bool:
    """Print dead `python <path>.py` references with Why/Fix (PRINCIPLE-011 R6); True when clean."""
    if errors is None:
        print("[WARN] git is unavailable, so python script references were not checked (IDEA-406).")
        return True
    if not errors:
        print("[OK] Every `python <path>.py` in AIKit's code and instructions names an existing file.")
        return True
    print(f"[FAIL] {len(errors)} reference(s) name a python script that does not exist:")
    for error in errors[:20]:
        print(f"   - {error}")
    if len(errors) > 20:
        print(f"   ... and {len(errors) - 20} more")
    print("   Why: an agent or user who runs a printed or documented command that names a missing file "
          "gets an error instead of the fix it promised.")
    print("   Fix: point each line at the current entry point, or mark an example or a path relative to "
          "another project with `hygiene: allow <reason>` on that line or the line above.")
    return False


def check_readme(root: Path = ROOT_DIR) -> List[str]:
    """Run `audit_readme` on `root`, listing tracked files with git (bounded, PRINCIPLE-010 R3)."""
    readme_path = root / "README.md"
    if not readme_path.is_file():
        return ["README.md does not exist (R1)"]
    tracked = tracked_files(root)
    if tracked is None:
        print("[WARN] git is unavailable, so README tree completeness was not checked (PRINCIPLE-005 R5).")

    def script_source(rel: str) -> Optional[str]:
        path = root / rel
        return path.read_text(encoding="utf-8") if path.is_file() else None

    return audit_readme(readme_path.read_text(encoding="utf-8"), tracked,
                        lambda rel: (root / rel).exists(), script_source)


def report_readme(errors: List[str]) -> bool:
    """Print README findings with the remediation triad (PRINCIPLE-011 R6); True when clean."""
    if not errors:
        print("[OK] README.md: size, labels, directory tree and documented commands verified (PRINCIPLE-005)")
        return True
    print(f"[FAIL] README.md drift ({len(errors)}):")
    for error in errors[:20]:
        print(f"   - {error}")
    if len(errors) > 20:
        print(f"   ... and {len(errors) - 20} more")
    print("   Why: a cold-starting agent trusts README.md; a dead path or command wastes its first turn.")
    print("   Fix: edit README.md as each line says (rule numbers are PRINCIPLE-005's), then re-run.")
    return False


# A project's own rules (PRINCIPLE-001 R4 project tier): read at every project cold start, so they
# stay small (PRINCIPLE-012), and each is one identifiable line.
PROJECT_GUIDELINES_MAX_CHARS = 4_000
_GUIDELINE_RULE = re.compile(r"^- \*\*(G-\d{3})\*\* \(([^()\n]+)\): (\S.*)$")
# Wording that would make a project rule weaken a principle; rules may only add to them.
_GUIDELINE_OVERRIDE = re.compile(
    r"\b(ignore|ignores|override|overrides|skip|skips|disable|disables|bypass|bypasses|waive|waives|"
    r"exempt|exempts|suspend|suspends|relax|relaxes)\b[^\n]*\bPRINCIPLE-\d{3}"
    r"|\bPRINCIPLE-\d{3}[^\n]*\b(does not apply|do not apply|no longer applies|is waived|is optional|"
    r"is suspended|is relaxed)\b", re.I)


def guideline_errors(text: str) -> List[str]:
    """
    Problems in a project's `.aikit/guidelines.md`: over the size limit, a line under `## Rules`
    that is not `- **G-NNN** (source): rule`, a reused ID, or a rule worded to override a principle,
    which it never can (PRINCIPLE-000 R6). Pure, so `add_guideline` refuses what this rejects.
    """
    errors: List[str] = []
    if len(text) > PROJECT_GUIDELINES_MAX_CHARS:
        errors.append(f"it has {len(text):,} chars; the limit is {PROJECT_GUIDELINES_MAX_CHARS:,} (PRINCIPLE-001 R4)")
    heading = re.search(r"^## Rules[ \t]*$", text, re.M)
    if not heading:
        return errors + ["it has no '## Rules' heading (PRINCIPLE-001 R4)"]
    seen: Dict[str, int] = {}
    for line in (l.strip() for l in text[heading.end():].splitlines()):
        if not line:
            continue
        rule = _GUIDELINE_RULE.match(line)
        if not rule:
            errors.append(f"'{line[:60]}' is not '- **G-NNN** (source): rule' (PRINCIPLE-001 R4)")
            continue
        gid = rule.group(1)
        seen[gid] = seen.get(gid, 0) + 1
        if seen[gid] == 2:
            errors.append(f"{gid} is used twice; each rule keeps its own ID (PRINCIPLE-001 R4)")
        if _GUIDELINE_OVERRIDE.search(rule.group(3)):
            errors.append(f"{gid} overrides a principle; project guidelines only add to them (PRINCIPLE-000 R6)")
    return errors


def memory_dir(root: Path) -> Path:
    """Where `root` keeps its map and decisions: a project's `.aikit/`, else `knowledge/`.

    The `.aikit/project.json` marker decides, so a tool state folder inside AIKit (Reforge writes
    `.aikit/reforge.json`) cannot hide AIKit's own `knowledge/` (ADR-253).
    """
    memory = root / ".aikit"
    if memory.is_dir() and ((memory / "project.json").is_file() or not (root / ".agents").is_dir()):
        return memory
    return root / "knowledge"


def check_workspace(root: Path = ROOT_DIR) -> bool:
    """
    Every read-only audit of `--check`, for AIKit or for a project it builds: the codebase map
    (a project's only once `aikit fix` has written one), the full PRINCIPLE-005 README audit,
    unfinished code, code structure and the ADR register. One code path, so a project is held to
    exactly AIKit's checks; a size-only README check let a README listing nine deleted files pass
    (ADR-128). Reports every failure before returning, never stopping at the first.
    """
    memory = memory_dir(root)
    ok = True
    map_path = memory / "codebase_map.md"
    if map_path.is_file() or root == ROOT_DIR:
        rel = map_path.relative_to(root)
        if check_codebase_map_freshness(memory, root=root, strict=False):
            print(f"[OK] {rel} is fresh and synchronized with the AST.")
        else:
            # The exact command for this folder: a project's stale map used to point at AIKit's.
            remedy = ("python scripts/update_knowledge_base.py" if root == ROOT_DIR
                      else f'python scripts/update_knowledge_base.py --workspace "{root}"')
            print(f"[FAIL] {rel} is stale. Fix: run `{remedy}`.")
            ok = False
    ok = report_readme(check_readme(root)) and ok
    if root == ROOT_DIR:
        # Only AIKit: a project's docs name AIKit's own `aikit.py` and `scripts/`, which live in
        # the AIKit folder, so every project would fail on them (44 of 44 measured).
        ok = report_script_references(check_script_references(root)) and ok
    ok = report_lazy_code(check_lazy_code(root)) and ok
    ok = report_architecture(check_architecture(root)) and ok
    guidelines = memory / "guidelines.md"
    if guidelines.is_file():
        rel = guidelines.relative_to(root)
        errors = guideline_errors(guidelines.read_text(encoding="utf-8"))
        for error in errors:
            print(f"[FAIL] {rel}: {error}")
        if errors:
            print("   Why: a project's guidelines add rules below AIKit's principles; a broken or overriding "
                  "rule would be read differently by each agent.")
            print("   Fix: correct each line above, or rewrite the rule as a constraint the principles allow.")
        else:
            print(f"[OK] {rel}: every rule is well-formed and adds to the principles.")
        ok = ok and not errors
    decisions = memory / "decisions.md"
    if decisions.is_file():
        rel = decisions.relative_to(root)
        errors = audit_adr_register(decisions.read_text(encoding="utf-8"))
        for error in errors:
            print(f"[FAIL] {rel}: {error} (PRINCIPLE-016 R3)")
        if not errors:
            print(f"[OK] {rel}: ADR IDs are unique and consecutive.")
        ok = ok and not errors
    return ok


KNOWN_FLAGS = {"--check", "--digest", "--lenient", "--workspace", "--help", "-h"}

HELP_TEXT = """AIKit Knowledge Base Auto-Updater (PRINCIPLE-016)

Usage:
  python scripts/update_knowledge_base.py [OPTIONS]

Options:
  --check            Verify, without writing, that codebase_map.md matches the AST and that README.md
                     passes the PRINCIPLE-005 checks (size, labels, directory tree, documented
                     commands), that ADR IDs in decisions.md are unique and
                     consecutive, and that no Python file holds a TODO/FIXME marker, a stub or
                     an unnamed suppression (PRINCIPLE-007 R3), and no module has a junk-drawer
                     name, a role of 0 or more than 5 methods, or an import cycle
                     (PRINCIPLE-009), and no subprocess call lacks timeout= and no open()
                     runs outside a with statement (PRINCIPLE-010), and no code reads os.environ[...] (PRINCIPLE-011 R3);
                     exits 1 on any of them
  --digest           Print one line per module (path, lines, classes, functions, purpose) within
                     100 lines and 16k chars, shared-code folders first; a cut is stated. Writes nothing
  --workspace <dir>  Run checks against the project workspace at <dir> (e.g. projects/<name>)
  --lenient          Downgrade AST syntax and link integrity failures from errors to warnings
  -h, --help         Show this help message and exit

Exit codes:
  0  success    1  stale map / validation failure    2  CLI argument misuse
"""


def _validate_argv(argv: List[str], known: set, help_text: str) -> None:
    """Short-circuit on --help and reject unknown flags with exit 2 (PRINCIPLE-011, PRINCIPLE-015)."""
    if "-h" in argv or "--help" in argv:
        print(help_text, end="")
        sys.exit(0)
    unknown: List[str] = []
    i = 0
    while i < len(argv):
        a = argv[i]
        if a.startswith("-"):
            if a not in known:
                unknown.append(a)
            elif a == "--workspace":
                i += 1  # skip directory value
        i += 1
    if unknown:
        print(f"[INVALID USAGE] Unrecognized option(s): {', '.join(unknown)}", file=sys.stderr)
        print(f"Why: this tool accepts only {', '.join(sorted(known))}.", file=sys.stderr)
        print("Fix: run 'python scripts/update_knowledge_base.py --help' to list valid options.", file=sys.stderr)
        sys.exit(2)


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
    _validate_argv(sys.argv[1:], KNOWN_FLAGS, HELP_TEXT)

    target_root = ROOT_DIR
    if "--workspace" in sys.argv:
        widx = sys.argv.index("--workspace")
        if widx + 1 >= len(sys.argv) or sys.argv[widx + 1].startswith("-"):
            print("[INVALID USAGE] --workspace requires a directory argument.", file=sys.stderr)
            print("Why: the target workspace directory must be explicitly specified.", file=sys.stderr)
            print("Fix: pass '--workspace <dir>'.", file=sys.stderr)
            sys.exit(2)
        target_root = Path(sys.argv[widx + 1]).resolve()
        if not target_root.is_dir():
            print(f"[INVALID USAGE] --workspace '{target_root}' does not exist or is not a directory.", file=sys.stderr)
            print("Why: the audits read that folder's files and git repository.", file=sys.stderr)
            print("Fix: pass an existing project folder, e.g. --workspace projects/<name>.", file=sys.stderr)
            sys.exit(2)

    if "--digest" in sys.argv:
        # Read-only, and before every write path: a digest must never refresh the map.
        map_rel = (memory_dir(target_root) / "codebase_map.md").relative_to(target_root).as_posix()
        print(build_digest(digest_rows(target_root), map_name=map_rel))
        sys.exit(0)

    if "--check" in sys.argv:
        try:
            sys.exit(0 if check_workspace(target_root) else 1)
        except Exception as e:
            print(f"[FAIL] The read-only checks could not finish: {e}")
            print("Why: a check that did not run proves nothing, so it is reported as a failure.")
            print("Fix: correct the cause named above (often an unreadable file), then re-run --check.")
            sys.exit(1)

    is_lenient = "--lenient" in sys.argv
    k_dir = target_root / "knowledge"
    if k_dir.is_dir() or target_root == ROOT_DIR:
        try:
            update_and_validate(k_dir, root=target_root, strict=not is_lenient)
        except ValueError as gate_error:
            # PRINCIPLE-003 R7 halts here; PRINCIPLE-011 R6 forbids doing it with a raw traceback.
            # Each failure gets its own Why/Fix: an ADR-ID or link error used to be reported as a
            # syntax error, sending the reader to a file that parses fine.
            if "[PRINCIPLE-003" in str(gate_error):
                print(f"[AST GATE FAILED] {gate_error}", file=sys.stderr)
                print("Why: a file that does not parse cannot be catalogued or trusted (PRINCIPLE-003 R7).",
                      file=sys.stderr)
                print("Fix: correct the syntax error in the file named above, then re-run this script.",
                      file=sys.stderr)
            else:
                print(f"[KNOWLEDGE GATE FAILED] {gate_error}", file=sys.stderr)
                print("Why: the knowledge base is incomplete or out of order (PRINCIPLE-016).", file=sys.stderr)
                print("Fix: add the missing document, repair the link or renumber the ADR named above, "
                      "then re-run this script.", file=sys.stderr)
            sys.exit(1)
    elif (target_root / ".aikit").is_dir():
        map_content = generate_codebase_map(root=target_root, strict=not is_lenient)
        map_path = target_root / ".aikit" / "codebase_map.md"
        write_generated_file(map_path, map_content)
        print(f"[UPDATED] {map_path.relative_to(target_root)}")

    readme_ok = report_readme(check_readme(target_root))
    lazy_ok = report_lazy_code(check_lazy_code(target_root))
    arch_ok = report_architecture(check_architecture(target_root))
    if not (readme_ok and lazy_ok and arch_ok) and not is_lenient:
        sys.exit(1)

