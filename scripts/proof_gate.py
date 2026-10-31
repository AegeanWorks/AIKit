#!/usr/bin/env python3
"""Prove that a declared test fails on the base tree and passes on the current tree.

This is the primary half of IDEA-956: PRINCIPLE-014 requires a failing-first test, but a green
current run alone cannot prove the test ever failed. The gate copies each declared test file into
a throwaway worktree at ``--base``, runs it there, and requires an assertion failure rather than an
import or collection error; the same file must pass in the current tree.

Mutation scoring is deliberately out of scope here. It is the secondary strength check in the
idea and can be added without changing this contract.

Usage:
  python scripts/proof_gate.py --base HEAD~1 --tests tests/test_x.py [--repo .] [--timeout 20]
      [--json]

Exit codes:
  0 proof holds    1 proof failed    2 setup or usage error
"""

from __future__ import annotations

import argparse
import ast
import json
import re
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path
from typing import Callable, Dict, List, Sequence, Tuple

DEFAULT_TIMEOUT_SECONDS = 20.0
TAIL_LINES = 40
ASSERTION_FAILURE_RE = re.compile(r"FAILED \([^)]*failures=\d+")
COMPARE_MUTATIONS = {"==": "!=", "!=": "==", "<": ">=", "<=": ">", ">": "<=", ">=": "<"}
BINOP_MUTATIONS = {"+": "-", "-": "+"}

Runner = Callable[[Sequence[str], Path, float], Tuple[int, str]]

# The generated and dependency trees no mutation run may copy. Kept beside the copy so the audit
# and knowledge walkers can be pinned to the same core set by a unit test (ADR-300).
COPY_IGNORE_PATTERNS = (
    ".git", ".hg", ".svn", "projects", "references", "scratch", ".idea-catcher",
    "node_modules", "__pycache__", "*.pyc", "*.pyo",
    ".pytest_cache", ".ruff_cache", ".mypy_cache", ".tox", ".nox",
    ".venv", "venv", "env", "build", "dist", "target", ".next", ".nuxt", ".cache", ".vite",
)


class ProofError(ValueError):
    """The proof could not be set up; the exit code is 2."""


def run_command(argv: Sequence[str], cwd: Path, timeout: float) -> Tuple[int, str]:
    """A command's exit code and combined output; 124 on timeout, 127 when it cannot start."""
    try:
        done = subprocess.run(
            list(argv), cwd=str(cwd), stdin=subprocess.DEVNULL, capture_output=True,
            text=True, encoding="utf-8", errors="replace", timeout=timeout,
        )
    except subprocess.TimeoutExpired:
        return 124, f"timed out after {timeout:g}s"
    except OSError as exc:
        return 127, str(exc)
    return done.returncode, (done.stdout + done.stderr).strip()


def module_name(test: Path) -> str:
    """The dotted module name for a repository-relative test path."""
    return ".".join(test.with_suffix("").parts)


def test_argv(test: Path) -> List[str]:
    """The unittest command for one test module, run from the tree root."""
    return [sys.executable, "-m", "unittest", module_name(test)]


def classify_run(code: int, output: str) -> str:
    """Classify one test run as passed, assertion, error or timeout.

    A nonzero run counts as an assertion failure only when unittest reports ``failures=``.
    Import errors, collection errors and timeouts are not proof that the test asserted anything.
    """
    if code == 0:
        return "passed"
    if code == 124:
        return "timeout"
    return "assertion" if ASSERTION_FAILURE_RE.search(output) else "error"


def tail(output: str, lines: int = TAIL_LINES) -> str:
    """The last ``lines`` non-empty output lines, bounded for a JSON record."""
    kept = [line for line in output.splitlines() if line.strip()]
    return "\n".join(kept[-lines:])


def _operator_span(left: ast.AST, right: ast.AST, lines: Sequence[str],
                   token: str) -> Tuple[int, int, int] | None:
    """The (line, start, end) span of an operator between two same-line operands."""
    left_end = getattr(left, "end_lineno", None)
    if left_end is None or left_end != getattr(right, "lineno", None):
        return None
    start = getattr(left, "end_col_offset", None)
    end = getattr(right, "col_offset", None)
    if start is None or end is None or end < start:
        return None
    line = lines[left_end - 1]
    segment = line[start:end]
    offset = segment.find(token)
    if offset < 0:
        return None
    return left_end, start + offset, start + offset + len(token)


def mutations_for_source(text: str, file_label: str, limit: int = 6) -> List[Dict[str, object]]:
    """Deterministic, bounded mutants for single-line operators in one source file.

    Only operators with a clear, local replacement are generated. Chained comparisons,
    multi-line expressions and unsupported operators are skipped rather than guessed at.
    """
    if limit <= 0:
        return []
    try:
        tree = ast.parse(text)
    except SyntaxError as exc:
        raise ProofError(f"{file_label} does not parse: {exc}") from exc
    lines = text.splitlines(keepends=True)
    found: List[Dict[str, object]] = []

    def add(line: int, start: int, end: int, operator: str, replacement: str) -> None:
        found.append({
            "file": file_label,
            "line": line,
            "column": start,
            "end": end,
            "operator": operator,
            "replacement": replacement,
        })

    compare_tokens = {
        ast.Eq: "==", ast.NotEq: "!=", ast.Lt: "<", ast.LtE: "<=",
        ast.Gt: ">", ast.GtE: ">=",
    }
    for node in ast.walk(tree):
        if isinstance(node, ast.Compare) and len(node.ops) == 1:
            token = compare_tokens.get(type(node.ops[0]))  # aikit:allow-secret: operator lookup, not a credential
            if token in COMPARE_MUTATIONS:
                span = _operator_span(node.left, node.comparators[0], lines, token)
                if span:
                    add(span[0], span[1], span[2], token, COMPARE_MUTATIONS[token])
        elif isinstance(node, ast.BoolOp) and len(node.values) >= 2:
            token = "and" if isinstance(node.op, ast.And) else (
                "or" if isinstance(node.op, ast.Or) else ""
            )
            if token:
                span = _operator_span(node.values[0], node.values[1], lines, token)
                if span:
                    add(span[0], span[1], span[2], token,
                        "or" if token == "and" else "and")
        elif isinstance(node, ast.BinOp):
            token = "+" if isinstance(node.op, ast.Add) else (
                "-" if isinstance(node.op, ast.Sub) else ""
            )
            if token in BINOP_MUTATIONS:
                span = _operator_span(node.left, node.right, lines, token)
                if span:
                    add(span[0], span[1], span[2], token, BINOP_MUTATIONS[token])
        elif isinstance(node, ast.UnaryOp) and isinstance(node.op, ast.Not):
            line = lines[node.lineno - 1]
            if line[node.col_offset:node.col_offset + 3] == "not":
                add(node.lineno, node.col_offset, node.col_offset + 3, "not", "")
        elif isinstance(node, ast.Constant) and isinstance(node.value, bool):
            token = "True" if node.value else "False"
            line = lines[node.lineno - 1]
            if line[node.col_offset:node.end_col_offset] == token:
                add(node.lineno, node.col_offset, node.end_col_offset, token,
                    "False" if token == "True" else "True")

    unique: List[Dict[str, object]] = []
    seen = set()
    for mutant in sorted(found, key=lambda item: (
        int(item["line"]), int(item["column"]), int(item["end"]), str(item["replacement"])
    )):
        key = (mutant["file"], mutant["line"], mutant["column"], mutant["end"],
               mutant["replacement"])
        if key in seen:
            continue
        seen.add(key)
        unique.append(mutant)
        if len(unique) >= limit:
            break
    return unique


def mutant_key(mutant: Dict[str, object]) -> str:
    """The stable waiver key for one mutant."""
    return f"{mutant['file']}:{mutant['line']}:{mutant['operator']}"


def apply_mutation(text: str, mutant: Dict[str, object]) -> str:
    """Apply one mutant to its source text."""
    lines = text.splitlines(keepends=True)
    index = int(mutant["line"]) - 1
    if index < 0 or index >= len(lines):
        raise ProofError(f"mutant line {mutant['line']} is outside {mutant['file']}")
    line = lines[index]
    start = int(mutant["column"])
    end = int(mutant["end"])
    lines[index] = line[:start] + str(mutant["replacement"]) + line[end:]
    return "".join(lines)


def _copy_repo(repo: Path, destination: Path) -> None:
    """Copy the working tree without Git metadata, project checkouts, or generated bulk."""
    ignore = shutil.ignore_patterns(*COPY_IGNORE_PATTERNS)
    try:
        shutil.copytree(repo, destination, ignore=ignore)
    except OSError as exc:
        raise ProofError(f"could not copy {repo} for mutation scoring: {exc}") from exc


def _run_declared_tests(tree: Path, tests: Sequence[Path], timeout: float,
                        runner: Runner) -> Tuple[int, str]:
    for test in tests:
        code, output = runner(test_argv(test), tree, timeout)
        if code != 0:
            return code, output
    return 0, "all declared tests passed"


def mutation_suite(
    repo: Path,
    tree: Path,
    *,
    tests: Sequence[Path],
    sources: Sequence[Path],
    limit: int,
    min_killed: int,
    waive: Sequence[str] = (),
    timeout: float,
    runner: Runner,
) -> Dict[str, object]:
    """Generate bounded mutants in a copy of the tree and score them with the declared tests."""
    current = tree / "current"
    _copy_repo(repo, current)
    repo_root = repo.resolve()
    mutants: List[Tuple[Path, Dict[str, object]]] = []
    for source in sources:
        candidate = source if source.is_absolute() else repo / source
        try:
            relative = candidate.resolve().relative_to(repo_root)
        except ValueError as exc:
            raise ProofError(
                f"declared source {str(source)!r} is outside the repository {repo}"
            ) from exc
        path = current / relative
        if not path.is_file():
            raise ProofError(f"declared source {str(source)!r} does not exist")
        try:
            text = path.read_text(encoding="utf-8")
        except (OSError, UnicodeDecodeError) as exc:
            raise ProofError(f"declared source {str(source)!r} is not readable UTF-8: {exc}") from exc
        remaining = limit - len(mutants)
        if remaining <= 0:
            break
        for mutant in mutations_for_source(text, relative.as_posix(), remaining):
            mutants.append((path, mutant))

    waived_keys = set(waive)
    active = [(path, mutant) for path, mutant in mutants
              if mutant_key(mutant) not in waived_keys]
    waived = len(mutants) - len(active)
    records: List[Dict[str, object]] = []
    for path, mutant in active:
        original = path.read_bytes()
        mutated = apply_mutation(original.decode("utf-8"), mutant)
        try:
            path.write_bytes(mutated.encode("utf-8"))
            code, output = _run_declared_tests(current, tests, timeout, runner)
        finally:
            path.write_bytes(original)
        status = "killed" if code != 0 else "survived"
        if code == 124:
            status = "timeout"
        records.append({
            "file": mutant["file"],
            "line": mutant["line"],
            "operator": mutant["operator"],
            "replacement": mutant["replacement"],
            "status": status,
            "exit": code,
            "output": tail(output),
        })

    killed = sum(1 for row in records if row["status"] in {"killed", "timeout"})
    survived = len(records) - killed
    threshold = min(min_killed, len(records)) if records else 0
    return {
        "generated": len(mutants),
        "waived": waived,
        "scored": len(records),
        "killed": killed,
        "survived": survived,
        "threshold": threshold,
        "passed": killed >= threshold,
        "mutants": records,
    }


def _git(repo: Path, *args: str, timeout: float) -> Tuple[int, str]:
    return run_command(["git", *args], repo, timeout)


def _resolve_base(repo: Path, base: str, timeout: float) -> str:
    code, output = _git(repo, "rev-parse", "--verify", f"{base}^{{commit}}", timeout=timeout)
    if code != 0:
        raise ProofError(
            f"base {base!r} does not name a commit in {repo}: {tail(output, 3)}"
        )
    return output.splitlines()[0].strip()


def _copy_tests(repo: Path, worktree: Path, tests: Sequence[Path]) -> List[Path]:
    """Copy each declared test into the base worktree and return its repo-relative path."""
    copied: List[Path] = []
    for value in tests:
        source = value if value.is_absolute() else repo / value
        try:
            relative = source.resolve().relative_to(repo.resolve())
        except ValueError as exc:
            raise ProofError(f"test {str(value)!r} is outside the repository {repo}") from exc
        if not source.is_file():
            raise ProofError(f"declared test {str(value)!r} does not exist")
        destination = worktree / relative
        destination.parent.mkdir(parents=True, exist_ok=True)
        destination.write_bytes(source.read_bytes())
        copied.append(relative)
    return copied


def prove(
    repo: Path,
    *,
    base: str = "HEAD~1",
    tests: Sequence[Path],
    sources: Sequence[Path] = (),
    mutants: int = 0,
    min_killed: int = 3,
    require_mutation: bool = False,
    waive: Sequence[str] = (),
    timeout: float = DEFAULT_TIMEOUT_SECONDS,
    runner: Runner = run_command,
) -> Dict[str, object]:
    """Run the declared tests on the base and current trees and return the proof record."""
    repo = Path(repo).resolve()
    if timeout <= 0:
        raise ProofError("timeout must be greater than zero")
    if not tests:
        raise ProofError("at least one --tests path is required")
    if mutants < 0 or min_killed < 0:
        raise ProofError("mutant counts cannot be negative")
    if require_mutation and (not sources or mutants <= 0):
        raise ProofError("--require-mutation needs --sources and --mutants greater than zero")
    code, output = _git(repo, "rev-parse", "--show-toplevel", timeout=timeout)
    if code != 0:
        raise ProofError(f"{repo} is not a Git checkout: {tail(output, 3)}")
    resolved = _resolve_base(repo, base, timeout)

    tree = Path(tempfile.mkdtemp(prefix="aikit_proof_"))
    worktree = tree / "base"
    added = False
    results: List[Dict[str, object]] = []
    mutation: Dict[str, object] | None = None
    fail_to_pass_failures: List[str] = []
    failures: List[str] = []
    try:
        code, output = _git(repo, "worktree", "add", "--detach", str(worktree), resolved,
                            timeout=timeout)
        if code != 0:
            raise ProofError(f"git worktree add failed: {tail(output, 3)}")
        added = True
        copied = _copy_tests(repo, worktree, tests)
        for relative in copied:
            base_code, base_output = runner(test_argv(relative), worktree, timeout)
            current_code, current_output = runner(test_argv(relative), repo, timeout)
            results.append({
                "test": relative.as_posix(),
                "base": {
                    "exit": base_code,
                    "verdict": classify_run(base_code, base_output),
                    "output": tail(base_output),
                },
                "current": {
                    "exit": current_code,
                    "verdict": classify_run(current_code, current_output),
                    "output": tail(current_output),
                },
            })
        for result in results:
            test = str(result["test"])
            base_result = result["base"]
            current_result = result["current"]
            if base_result["verdict"] != "assertion":
                fail_to_pass_failures.append(
                    f"{test}: base verdict is {base_result['verdict']}, not an assertion failure"
                )
            if current_result["verdict"] != "passed":
                fail_to_pass_failures.append(
                    f"{test}: current verdict is {current_result['verdict']}, not a pass"
                )
        failures.extend(fail_to_pass_failures)
        if not fail_to_pass_failures and sources and mutants > 0:
            mutation = mutation_suite(
                repo, tree, tests=copied, sources=sources, limit=mutants,
                min_killed=min_killed, waive=waive, timeout=timeout, runner=runner,
            )
            if require_mutation and not mutation["passed"]:
                failures.append(
                    f"mutation: {mutation['killed']}/{mutation['scored']} killed, "
                    f"threshold {mutation['threshold']}"
                )
    finally:
        if added:
            _git(repo, "worktree", "remove", "--force", str(worktree), timeout=timeout)
        shutil.rmtree(tree, ignore_errors=True)

    reason = "; ".join(failures) if failures else (
        "every test failed on base and passes now"
        + (f"; mutation {mutation['killed']}/{mutation['scored']} killed"
           + (f", {mutation['waived']} waived" if mutation["waived"] else "")
           if mutation else "")
    )
    return {
        "repo": str(repo),
        "base": resolved,
        "tests": [str(result["test"]) for result in results],
        "proof": not failures,
        "fail_to_pass": not fail_to_pass_failures,
        "mutation": mutation,
        "reason": reason,
        "results": results,
    }


def render_text(result: Dict[str, object]) -> str:
    """A terse human report for the CLI."""
    lines = [
        f"{'[OK]' if result['proof'] else '[FAIL]'} {result['reason']}",
        f"       base {result['base']} · {len(result['tests'])} test file(s)",
    ]
    for row in result["results"]:
        base = row["base"]
        current = row["current"]
        lines.append(
            f"       {row['test']}: base {base['verdict']} (exit {base['exit']}) · "
            f"current {current['verdict']} (exit {current['exit']})"
        )
    mutation = result.get("mutation")
    if mutation:
        waived = f", {mutation['waived']} waived" if mutation["waived"] else ""
        lines.append(
            f"       mutation: {mutation['killed']}/{mutation['scored']} killed "
            f"(threshold {mutation['threshold']}{waived})"
        )
    return "\n".join(lines)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="python scripts/proof_gate.py",
        description="Prove declared tests fail on the base tree and pass on the current tree.",
    )
    parser.add_argument("--repo", default=".", help="Git checkout (default: current folder)")
    parser.add_argument("--base", default="HEAD~1", help="base commit or revision (default: HEAD~1)")
    parser.add_argument("--tests", nargs="+", required=True, metavar="PATH",
                        help="declared test file(s), relative to the repository")
    parser.add_argument("--sources", nargs="+", default=[], metavar="PATH",
                        help="changed source file(s) to mutate; enables mutation scoring")
    parser.add_argument("--mutants", type=int, default=0,
                        help="maximum mutants to generate (default: 0, mutation off)")
    parser.add_argument("--min-killed", type=int, default=3,
                        help="mutants that must be killed; capped by generated count (default: 3)")
    parser.add_argument("--require-mutation", action="store_true",
                        help="make the mutation threshold part of the pass/fail proof")
    parser.add_argument("--waive", action="append", default=[], metavar="FILE:LINE:OPERATOR",
                        help="equivalent mutant to exclude; repeat for several")
    parser.add_argument("--timeout", type=float, default=DEFAULT_TIMEOUT_SECONDS,
                        help=f"seconds per test run (default: {DEFAULT_TIMEOUT_SECONDS:g})")
    parser.add_argument("--json", action="store_true", help="print one machine-readable result")
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    try:
        result = prove(
            Path(args.repo), base=args.base,
            tests=[Path(value) for value in args.tests],
            sources=[Path(value) for value in args.sources],
            mutants=args.mutants, min_killed=args.min_killed,
            require_mutation=args.require_mutation, waive=args.waive, timeout=args.timeout,
        )
    except ProofError as error:
        print(f"Error: {error}", file=sys.stderr)
        print("Why: the proof gate could not establish a base and current tree.", file=sys.stderr)
        print("Fix: pass an existing Git checkout, a real base commit and existing test paths.",
              file=sys.stderr)
        return 2
    if args.json:
        print(json.dumps(result, indent=2, ensure_ascii=False))
    else:
        print(render_text(result))
    return 0 if result["proof"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
