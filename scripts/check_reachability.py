#!/usr/bin/env python3
"""
Invariant Reachability Shield (PRINCIPLE-014 Rule 7)

A passing test proves a mechanism works. It never proves the mechanism is *used*. The
highest-frequency defect class found in this repository was precisely that gap:

  - `file_lock()` was defined, exported and unit-tested with zero production call sites, so
    parallel agents silently erased each other's ledger checkpoints.
  - `format_resume_report()` read a `last_phase_num` key that no writer ever produced, so every
    resumption silently reported a default phase.

Both were green in CI. This checker closes the class mechanically by auditing two things across
production modules:

  1. Call-site reachability - every function must be called from production code or dispatched
     from an entrypoint. "A test calls it" is not reachability.
  2. Key round-trip integrity - every persisted-state key read must have a writer, and every
     key written should have a reader.

Zero external dependencies (standard library only).

Usage:
  python scripts/check_reachability.py [--verbose]
Exit codes:
  0 clean    1 unreachable capability or phantom key found    2 CLI argument misuse
"""

import ast
import sys
from pathlib import Path
from typing import Dict, List, Set, Tuple

ROOT_DIR = Path(__file__).resolve().parent.parent
PROD_DIR = ROOT_DIR / "scripts"
# Entry points outside scripts/: what they call is reached, so they are audited too (ADR-119).
ROOT_ENTRYPOINTS = ("aikit.py",)

# Deliberately public API: imported by consumers (tests, adopter projects, other tooling) rather
# than called internally. Each entry is a conscious decision, not a silenced warning.
PUBLIC_API_ALLOWLIST: Set[str] = {
    # Re-exported helpers an adopter or test harness legitimately drives directly.
    "get_ledger_path",
    "migrate_ledger_schema",
    "prune_checkpoints",
    "validate_conventional_commit",
    "extract_python_symbols",
    "validate_knowledge_links",
    "parse_principles",
    "validate_triad_consistency",
    "append_domain_rules",
    "load_tier_1b_domain_rules",
    "generate_codebase_map",
    "check_codebase_map_freshness",
    "update_and_validate",
    "sync_all",
    "render_signature",
    "classify_git_status",
    "resolve_active_phase",
    "check_disk_headroom",
    "clean_dangling_temp_files",
    "fsync_dir",
    "find_python_files",
    "run_dogfood",
    "atomic_write_json",
    "load_ledger",
    "save_ledger",
    "record_checkpoint",
    "mark_task_completed",
    "reset_active_task",
    "run_disruption_audit",
    "format_audit_report",
    "format_resume_report",
    "file_lock",
    "locked_ledger",
    "resolve_phase_num",
    "terminate_process_tree",
    "supervised",
    "sandbox_jail",
    "run_cli",
    "repo_fingerprint",
    "validate_argv",
    "print_help",
}

# Keys of third-party formats AIKit reads and never writes, so no AIKit writer can exist: the
# project's own `package.json` (`scripts.test`, project_registry stack detection); OpenCode's
# `opencode.jsonc` (`providers.<p>.models`) and its `--format json` event stream (`type`,
# `part.text`), both read by subagent_delegate (ADR-132).
EXTERNAL_SCHEMA_KEYS: Set[str] = {"scripts", "test", "build", "ui:snapshot", "providers",
                                  "models", "type", "part", "text", "surfaces", "paths",
                                  "protected", "commands", "fast", "fast_timeout", "snapshot",
                                  "snapshot_timeout", "style", "theme_paths", "limits",
                                  "max_files", "max_lines",
                                  # Environment variables `resolve_agent` reads; hosts set them (ADR-209).
                                  "AIKIT_AGENT", "AI_AGENT", "CLAUDE_CODE_SESSION_ID",
                                  # GitHub's topics response names (project_topics, ADR-234).
                                  "names",
                                  # Project-owned `.aikit/project.json` fields: license tags chosen
                                  # by the owner/topics workflow and the optional mechanics contract.
                                  "license_topics", "core"}

# Generator/content functions referenced only through data structures or f-strings.
DYNAMIC_DISPATCH_PREFIXES = ("generate_", "track_", "test_", "_")


_TREE_CACHE: Dict[Tuple[str, str], ast.Module] = {}


def parse_module(path: Path) -> ast.Module:
    """
    Parse a module once per content. Every analysis below walks the same files, and parsing each
    one 3-4 times made the repository scan the slowest unit test. The trees are only read, never
    mutated, so sharing them is safe; the content key means a cached tree is never stale.
    """
    source = path.read_text(encoding="utf-8")
    key = (str(path), source)
    if key not in _TREE_CACHE:
        if len(_TREE_CACHE) > 256:
            _TREE_CACHE.clear()
        _TREE_CACHE[key] = ast.parse(source, filename=str(path))
        _NODES_CACHE.clear()  # keyed by tree identity: a replaced tree must not hit an old entry
    return _TREE_CACHE[key]


_NODES_CACHE: Dict[int, List[ast.AST]] = {}


def module_nodes(path: Path) -> List[ast.AST]:
    """
    Every node of the module, walked once per parsed tree: references, state keys and literals
    each walked every tree again, and those walks were most of the shield's time (ADR-128).
    """
    tree = parse_module(path)
    if id(tree) not in _NODES_CACHE:
        _NODES_CACHE[id(tree)] = list(ast.walk(tree))
    return _NODES_CACHE[id(tree)]


def production_modules() -> List[Path]:
    """Production source files whose reachability is audited (excludes this checker itself)."""
    modules = [p for p in PROD_DIR.glob("*.py") if p.name != Path(__file__).name]
    modules += [ROOT_DIR / name for name in ROOT_ENTRYPOINTS if (ROOT_DIR / name).is_file()]
    return sorted(modules)


def collect_definitions(files: List[Path]) -> Dict[str, str]:
    """Map every top-level function name to the module that defines it."""
    defined: Dict[str, str] = {}
    for path in files:
        tree = parse_module(path)
        for node in tree.body:
            if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
                defined.setdefault(node.name, path.name)
    return defined


def collect_references(files: List[Path]) -> Set[str]:
    """
    Every name referenced in production code, however it is reached.

    Deliberately broad: a bare `ast.Name` load counts, because a function can be used as a
    value (stored in a tuple of tracks, passed as a callback, wrapped by a decorator) without
    ever appearing as `Call(func=Name(...))`. Under-counting here would produce false alarms.
    """
    referenced: Set[str] = set()
    for path in files:
        for node in module_nodes(path):
            if isinstance(node, ast.Name):
                referenced.add(node.id)
            elif isinstance(node, ast.Attribute):
                referenced.add(node.attr)
            elif isinstance(node, ast.ImportFrom):
                for alias in node.names:
                    referenced.add(alias.name)
    return referenced


def find_unreachable(files: List[Path]) -> List[Tuple[str, str]]:
    """Functions defined in production code with no production reference outside themselves and no allowlist entry."""
    refs_by_file: Dict[Path, Set[str]] = {}
    for p in files:
        s: Set[str] = set()
        for n in module_nodes(p):
            if isinstance(n, ast.Name):
                s.add(n.id)
            elif isinstance(n, ast.Attribute):
                s.add(n.attr)
            elif isinstance(n, ast.ImportFrom):
                for a in n.names:
                    s.add(a.name)
        refs_by_file[p] = s

    unreachable: List[Tuple[str, str]] = []
    seen: Set[Tuple[str, str]] = set()
    for p in files:
        tree = parse_module(p)
        for node in tree.body:
            if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
                name = node.name
                if (name, p.name) in seen:
                    continue
                seen.add((name, p.name))
                if name in PUBLIC_API_ALLOWLIST or name.startswith(DYNAMIC_DISPATCH_PREFIXES):
                    continue
                if any(name in refs_by_file[op] for op in files if op != p):
                    continue
                in_this_file_outside = False
                for top in tree.body:
                    if top is node:
                        continue
                    for n in ast.walk(top):
                        if (isinstance(n, ast.Name) and n.id == name) or (
                            isinstance(n, ast.Attribute) and n.attr == name
                        ) or (
                            isinstance(n, ast.ImportFrom) and any(a.name == name for a in n.names)
                        ):
                            in_this_file_outside = True
                            break
                    if in_this_file_outside:
                        break
                if not in_this_file_outside:
                    unreachable.append((name, p.name))
    return sorted(unreachable)


def collect_state_keys(files: List[Path]) -> Tuple[Dict[str, str], Set[str]]:
    """
    Literal string keys read via `.get("k")` or `["k"]`, and keys written as dict literals,
    subscript assignments or `.setdefault("k", v)`, which creates the key when it is missing and
    is therefore a read and a producer at once. Used to catch readers keyed to fields nothing
    produces.
    """
    reads: Dict[str, str] = {}
    writes: Set[str] = set()
    for path in files:
        for node in module_nodes(path):
            # dict literal writes: {"k": v}
            if isinstance(node, ast.Dict):
                for key in node.keys:
                    if isinstance(key, ast.Constant) and isinstance(key.value, str):
                        writes.add(key.value)
            # subscript assignment writes: d["k"] = v
            elif isinstance(node, ast.Assign):
                for target in node.targets:
                    if (isinstance(target, ast.Subscript)
                            and isinstance(target.slice, ast.Constant)
                            and isinstance(target.slice.value, str)):
                        writes.add(target.slice.value)
            # .get("k") reads
            elif (isinstance(node, ast.Call) and isinstance(node.func, ast.Attribute)
                  and node.func.attr in ("get", "setdefault") and node.args
                  and isinstance(node.args[0], ast.Constant)
                  and isinstance(node.args[0].value, str)):
                reads.setdefault(node.args[0].value, path.name)
                if node.func.attr == "setdefault":
                    writes.add(node.args[0].value)
    return reads, writes


def find_phantom_keys(files: List[Path]) -> List[Tuple[str, str]]:
    """State keys read by production code that no production code ever writes."""
    # Strict by design: a read key needs a producer the AST can see - a dict-literal key, a
    # subscript assignment or `.setdefault("k", ...)` - or an entry in EXTERNAL_SCHEMA_KEYS for
    # data another program writes.
    # A key written only through a comprehension or a loop over a tuple of names is flagged even
    # if its name appears as a literal elsewhere; write such keys literally instead.
    #
    # A fallback here once meant to excuse any key appearing more than once as a literal. It
    # collected those literals into a set, so its count never exceeded 1 and it never excused
    # anything. It was removed rather than repaired: repaired, it would have passed the hidden
    # producer this shield caught in the ADR-174 handoff work. Pinned by
    # test_a_producer_hidden_in_a_comprehension_is_flagged.
    reads, writes = collect_state_keys(files)
    return [(key, module) for key, module in sorted(reads.items())
            if key not in writes and key not in EXTERNAL_SCHEMA_KEYS]


def run_check(verbose: bool = False) -> int:
    """Audit reachability and key round-trips, reporting tersely (PRINCIPLE-012 Rule 4)."""
    files = production_modules()
    unreachable = find_unreachable(files)
    phantom = find_phantom_keys(files)

    print("=" * 58)
    print("INVARIANT REACHABILITY SHIELD (PRINCIPLE-014 R7)")
    print("=" * 58)
    print(f"Audited {len(files)} production module(s) in scripts/")

    if unreachable:
        print(f"\n[FAIL] {len(unreachable)} capability defined but never reached in production:")
        for name, module in unreachable:
            print(f"   - {name}() in {module}")
        print("   Why: a tested-but-unwired mechanism is a defect that reports as green.")
        print("   Fix: wire it into the path it protects, delete it, or add it to")
        print("        PUBLIC_API_ALLOWLIST with a reason if it is deliberately public API.")
    else:
        print("[OK] Every production function is reachable from production code.")

    if phantom:
        print(f"\n[FAIL] {len(phantom)} state key read with no producer:")
        for key, module in phantom:
            print(f"   - '{key}' read in {module}")
        print("   Why: a reader keyed to a field nothing writes silently returns its default.")
        print("   Fix: write the key, or read the key that is actually persisted.")
    else:
        print("[OK] Every state key read by production code has a producer.")

    if verbose:
        defined = collect_definitions(files)
        print(f"\n--- {len(defined)} production functions audited ---")
        for name, module in sorted(defined.items()):
            tag = "allowlisted" if name in PUBLIC_API_ALLOWLIST else "internal"
            print(f"   {module}: {name} ({tag})")

    print("=" * 58)
    return 1 if (unreachable or phantom) else 0


KNOWN_FLAGS = {"--verbose", "-v", "--help", "-h"}

HELP_TEXT = """AIKit Invariant Reachability Shield (PRINCIPLE-014 Rule 7)

Usage:
  python scripts/check_reachability.py [OPTIONS]

Audits production modules for capabilities that are defined, exported and tested but never
actually called in production, and for persisted-state keys read with no producer. Both are
defects that report as green in a passing test suite.

Options:
  --verbose, -v   List every audited function and its allowlist status
  -h, --help      Show this help message and exit

Exit codes:
  0  clean    1  unreachable capability or phantom key found    2  CLI argument misuse
"""


if __name__ == "__main__":
    argv = sys.argv[1:]
    if "-h" in argv or "--help" in argv:
        print(HELP_TEXT, end="")
        sys.exit(0)

    unknown = [a for a in argv if a.startswith("-") and a not in KNOWN_FLAGS]
    if unknown:
        print(f"[INVALID USAGE] Unrecognized option(s): {', '.join(unknown)}", file=sys.stderr)
        print(f"Why: this checker accepts only {', '.join(sorted(KNOWN_FLAGS))}.", file=sys.stderr)
        print("Fix: run 'python scripts/check_reachability.py --help' to list valid options.",
              file=sys.stderr)
        sys.exit(2)

    sys.exit(run_check(verbose=("--verbose" in argv or "-v" in argv)))
