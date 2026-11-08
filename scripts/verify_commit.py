#!/usr/bin/env python3
"""
Post-Commit Verification (PRINCIPLE-018 Rule 7)

The pre-commit triad (R3) runs against the working tree, so it proves the *tree* is green, not
the *commit*. Those differ whenever staging is a subset of the tree, which is the normal case
under R2's explicit staging. Both failure modes happened on 2026-10-19: ADR-145 was committed
while its implementation sat unstaged, and a regenerated codebase map was committed twice while
stale in the commit itself.

This gate checks out the commit into a throwaway worktree in the system temp directory and runs
the whole gate set there, plus the declared proof gate when `.aikit/proof.json` exists, so a commit
that cannot stand alone is caught while it is still local, where PRINCIPLE-018 R5 undoes it with
`git reset --soft HEAD^` instead of a revert.

Zero external dependencies (standard library only).

Usage:
  python scripts/verify_commit.py [--ref <commit>] [--verbose]
Exit codes:
  0 the commit is green    1 a gate failed or the worktree could not be made    2 CLI argument misuse
"""

import json
import re
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional, Tuple

ROOT_DIR = Path(__file__).resolve().parent.parent
PROOF_FILE = Path(".aikit") / "proof.json"
# The declaration schema: these are the keys the reader below consumes, kept in one literal so
# the reachability shield can see every persisted key has a producer. This file runs directly
# (`python scripts/verify_commit.py`), so `from scripts` imports live behind a direct-run-first
# fallback (the min_killed default is still pinned to proof_gate.DEFAULT_MIN_KILLED by a unit
# test instead of an import).
try:  # hygiene: allow [silent-except] optional shared-policy import fallback path
    from evidence_policy import (  # type: ignore[import-not-found]
        OUTCOME_PASS,
        PolicyError,
        attest,
        evaluate,
    )
except Exception:  # pragma: no cover - import fallback for test imports
    try:
        from scripts.evidence_policy import (  # type: ignore[import-not-found]
            OUTCOME_PASS,
            PolicyError,
            attest,
            evaluate,
        )
    except Exception:
        OUTCOME_PASS = "pass"
        PolicyError = ValueError  # type: ignore[no-redef]
        attest = None  # type: ignore[no-redef]
        evaluate = None  # type: ignore[no-redef]
PROOF_DEFAULTS = {
    "tests": [],
    "pass_to_pass": [],
    "sources": [],
    "waive": [],
    "mutants": 0,
    "min_killed": 3,
    "require_mutation": False,
    "paths": [],
    "max_files": 0,
    "max_lines": 0,
}
# A whole gate set runs inside the worktree; past this the run is hung, not slow.
GATE_TIMEOUT_SECONDS = 600
# The tiers gate bounds each tier itself (TIER_TIMEOUT in check_test_budgets), so it needs room
# for all of them plus the retry allowance; a single outer cap shared with the one-script gates
# killed it before it could report which tier overran (ADR-293).
TIER_GATE_TIMEOUT_SECONDS = 3 * 900 + 120
# Lines of a failing gate's output shown (PRINCIPLE-012 R4, PRINCIPLE-015 R7).
FAILURE_TAIL_LINES = 12

Runner = Callable[[List[str], Path], Tuple[int, str]]
# An overwritten file passes every gate, so a commit leaving a modified file under half its parent
# size is named (IDEA-262, ADR-282). Small files churn freely; added and deleted files are their
# own decision; a task ledger is pruned by its own commands and keeps a .bak.
SHRINK_RATIO = 0.5
SHRINK_MIN_BYTES = 400
SHRINK_EXEMPT = ("task_ledger.json",)
_SHRINK_OK = re.compile(r"(?im)^shrink-ok:[ \t]*\S.{5,}$")


def run_command(argv: List[str], cwd: Path,
                timeout: float = GATE_TIMEOUT_SECONDS) -> Tuple[int, str]:
    """A command's exit code and combined output; -1 when it could not start or timed out."""
    try:
        done = subprocess.run(argv, cwd=str(cwd), stdin=subprocess.DEVNULL, capture_output=True,
                              text=True, encoding="utf-8", errors="replace",
                              timeout=timeout)
    except subprocess.TimeoutExpired:
        return -1, f"the command did not finish within {timeout:g}s"
    except OSError as exc:
        return -1, str(exc)
    return done.returncode, (done.stdout + done.stderr).strip()


def gate_commands(secret_range: str) -> List[Tuple[str, List[str], float]]:
    """
    The gates PRINCIPLE-018 R3 names, as they run inside the worktree, each with its own bound.
    The secret scan reads the commit range rather than the tree, so it reports what the push would
    upload (ADR-145); only the tiers gate runs three bounded tiers of its own (ADR-293).
    """
    return [
        ("tiers", [sys.executable, "scripts/check_test_budgets.py"], TIER_GATE_TIMEOUT_SECONDS),
        ("rules", [sys.executable, "scripts/sync_principles.py", "--check"], GATE_TIMEOUT_SECONDS),
        ("knowledge", [sys.executable, "scripts/update_knowledge_base.py", "--check"],
         GATE_TIMEOUT_SECONDS),
        ("reachability", [sys.executable, "scripts/check_reachability.py"], GATE_TIMEOUT_SECONDS),
        ("secrets", [sys.executable, "scripts/check_secrets.py", "--commits", secret_range],
         GATE_TIMEOUT_SECONDS),
        ("dogfood", [sys.executable, "scripts/dogfood.py"], GATE_TIMEOUT_SECONDS),
    ]


def _string_list(value: Any, field: str, *, required: bool = False) -> List[str]:
    """Validate one declaration list; return stripped strings."""
    if value is None:
        if required:
            raise ValueError(f"{PROOF_FILE} needs a non-empty {field!r} list")
        return []
    if not isinstance(value, list) or not all(
        isinstance(item, str) and item.strip() for item in value
    ):
        raise ValueError(f"{PROOF_FILE} {field!r} must be a list of non-empty strings")
    cleaned = [item.strip() for item in value]
    for item in cleaned:
        if item.startswith("-"):
            raise ValueError(f"{PROOF_FILE} {field!r} must not hold flags like {item!r}")
    return cleaned


def _valid_scope_pattern(pattern: str) -> bool:
    """A relative glob that cannot escape the repository (mirrors ui_contract)."""
    if not isinstance(pattern, str) or not pattern.strip():
        return False
    normalized = pattern.replace("\\", "/").strip()
    if normalized.startswith("/") or (len(normalized) > 1 and normalized[1] == ":"):
        return False
    return ".." not in normalized.split("/")


def _scope_list(value: Any, field: str) -> List[str]:
    """Validate one optional scope allowlist; absent means unenforced."""
    if value is None:
        return []
    if not isinstance(value, list) or not all(
        isinstance(item, str) and item.strip() for item in value
    ):
        raise ValueError(f"{PROOF_FILE} {field!r} must be a list of non-empty relative patterns")
    cleaned = [item.replace("\\", "/").strip() for item in value]
    for item in cleaned:
        if item.startswith("-"):
            raise ValueError(f"{PROOF_FILE} {field!r} must not hold flags like {item!r}")
        if not _valid_scope_pattern(item):
            raise ValueError(
                f"{PROOF_FILE} {field!r} holds {item!r}: paths must be relative, "
                "never absolute, and must not contain '..'. "
                "Why: an absolute or escaping pattern silently widens the scope it claims to bound. "
                "Fix: write relative globs such as `scripts/**`.")
    return cleaned


def _scope_int(value: Any, field: str) -> int:
    """Validate one optional scope budget; 0/absent means unenforced."""
    if value is None:
        return 0
    if not isinstance(value, int) or isinstance(value, bool) or value < 0:
        raise ValueError(f"{PROOF_FILE} {field!r} must be a non-negative integer")
    return value


# Files a scope allowlist never constrains: the ledger (bookkeeping the task
# owns, never committed as evidence), the declaration carrier itself, and the
# generated codebase map (rebuilt and separately gated by --check).
SCOPE_EXEMPT_EXACT = (".aikit/proof.json", "knowledge/codebase_map.md")


def _scope_exempt(path: str) -> bool:
    """Whether `path` (repo-relative, forward slashes) sits outside scope."""
    normalized = path.replace("\\", "/")
    if normalized in SCOPE_EXEMPT_EXACT:
        return True
    return normalized == "task_ledger.json" or normalized.endswith("/task_ledger.json")


def _glob_match(path: str, pattern: str) -> bool:
    """Recursive glob: `**` spans zero or more segments, `*?[]` stay in-segment.

    `pathlib.PurePath.match` does not let `**` cross directories
    (`scripts/**` misses `scripts/a/b.py`), so only a pattern with a whole
    `**` segment uses the segment walker. Other patterns keep pathlib's suffix
    matching, which lets `*.py` and `scripts/*.py` match at any depth. A pattern
    without glob characters also matches everything beneath that directory
    (`scripts` covers `scripts/a.py`).
    """
    import fnmatch as _fn
    from pathlib import PurePosixPath as _Pure
    candidate = path.replace("\\", "/").strip()
    pat = pattern.replace("\\", "/").strip()
    if not any(char in pat for char in "*?["):
        return candidate == pat or candidate.startswith(pat.rstrip("/") + "/")
    if "**" not in pat.split("/"):
        return _Pure(candidate).match(pat)
    p_segs = pat.split("/")
    s_segs = candidate.split("/")

    def rec(pi: int, si: int) -> bool:
        if pi == len(p_segs):
            return si == len(s_segs)
        if p_segs[pi] == "**":
            return any(rec(pi + 1, k) for k in range(si, len(s_segs) + 1))
        if si >= len(s_segs):
            return False
        return _fn.fnmatchcase(s_segs[si], p_segs[pi]) and rec(pi + 1, si + 1)

    return rec(0, 0)


def _scope_match(path: str, patterns: List[str]) -> bool:
    """Whether one repo-relative path matches any allowlist glob."""
    return any(_glob_match(path, pattern) for pattern in patterns)


def scope_errors(declaration: Dict[str, Any], files: List[str],
                 added_lines: int) -> List[str]:
    """Scope failures for one declaration against changed files and diff size."""
    errors: List[str] = []
    patterns = [str(p) for p in declaration.get("paths", [])]
    max_files = int(declaration.get("max_files", 0) or 0)
    max_lines = int(declaration.get("max_lines", 0) or 0)
    if not patterns and not max_files and not max_lines:
        return errors
    scoped = [f for f in files if not _scope_exempt(f)]
    if patterns:
        outside = sorted(f for f in scoped if not _scope_match(f, patterns))
        if outside:
            errors.append(
                f"scope: {len(outside)} file(s) outside `paths`: {', '.join(outside[:5])}"
                f"{' ...' if len(outside) > 5 else ''}. "
                "Why: the declaration bounds the change; an unlisted file is out of scope. "
                "Fix: list the path pattern in `paths`, or drop the file from the commit.")
    if max_files and len(scoped) > max_files:
        errors.append(
            f"scope: {len(scoped)} file(s) exceed `max_files` {max_files}. "
            "Why: an unbounded diff cannot be reviewed as one unit. "
            "Fix: split the change, or raise `max_files` deliberately.")
    if max_lines and added_lines > max_lines:
        errors.append(
            f"scope: {added_lines} changed line(s) exceed `max_lines` {max_lines}. "
            "Why: an unbounded diff cannot be reviewed as one unit. "
            "Fix: split the change, or raise `max_lines` deliberately.")
    return errors


def _numstat_total(output: str) -> int:
    """Added plus deleted lines across a `git diff --numstat` output.

    Binary files report `- -` instead of counts; each counts as one changed
    line so a binary cannot slip under a `max_lines` budget uncounted.
    """
    total = 0
    for line in output.splitlines():
        fields = line.split()
        if len(fields) >= 3 and fields[0].isdigit() and fields[1].isdigit():
            total += int(fields[0]) + int(fields[1])
        elif len(fields) >= 3 and fields[0] == "-" and fields[1] == "-":
            total += 1
    return total


def commit_files_and_lines(ref: str, repo: Path, run: Runner) -> Tuple[List[str], int]:
    """Changed files and changed lines for one commit.

    A root commit has no parent to diff against: the whole tree counts as
    changed files with 0 lines, so `max_files` still binds while `max_lines`
    cannot (there is no base for a line delta).
    """
    code, parent = run(["git", "rev-parse", f"{ref}^"], repo)
    if code == 0 and parent.strip():
        base = parent.strip().splitlines()[0].strip()
        code, names = run(["git", "diff-tree", "--no-commit-id", "--name-only",
                           "-r", "-m", ref], repo)
        files = (sorted({line for line in names.splitlines() if line.strip()})
                 if code == 0 else [])
        code, stat = run(["git", "diff", "--numstat", f"{base}", ref], repo)
        return files, _numstat_total(stat) if code == 0 else 0
    code, names = run(["git", "ls-tree", "-r", "--name-only", ref], repo)
    return (sorted({line for line in names.splitlines() if line.strip()})
            if code == 0 else [], 0)


def project_path_violations(paths: List[str]) -> List[str]:
    """Changed paths AIKit must never track: a project owns its own repository."""
    violations: List[str] = []
    for path in paths:
        normalized = str(path).replace("\\", "/").strip("/").lower()
        if normalized == "projects" or normalized.startswith("projects/"):
            violations.append(path)
    return violations


def proof_command_from_declaration(
    declaration: object, *, worktree: Path, parent: str, script: Path
) -> List[str]:
    """Build the proof-gate command from a parsed `.aikit/proof.json` object."""
    if not isinstance(declaration, dict):
        raise ValueError(f"{PROOF_FILE} must hold a JSON object")
    # Closed schema (IDEA-1114, IDEA-1203): the readable keys are exactly PROOF_DEFAULTS.
    # An unknown key fails loudly with the known list, so a typo cannot silently disable
    # the proof it meant to configure. No live declaration carries unknown keys, so there
    # is no legacy set to grandfather; adding one later means editing this literal.
    unknown = sorted(key for key in declaration if key not in PROOF_DEFAULTS)
    if unknown:
        raise ValueError(
            f"{PROOF_FILE} has unknown key(s): {', '.join(unknown)}. "
            f"Known keys: {', '.join(sorted(PROOF_DEFAULTS))}. "
            "Why: a misspelled key silently disables the proof it meant to configure. "
            "Fix: rename the key, or remove it.")
    tests = _string_list(declaration.get("tests"), "tests", required=True)
    pass_to_pass = _string_list(declaration.get("pass_to_pass", PROOF_DEFAULTS["pass_to_pass"]),
                                "pass_to_pass")
    sources = _string_list(declaration.get("sources", PROOF_DEFAULTS["sources"]), "sources")
    waive = _string_list(declaration.get("waive", PROOF_DEFAULTS["waive"]), "waive")
    mutants = declaration.get("mutants", PROOF_DEFAULTS["mutants"])
    min_killed = declaration.get("min_killed", PROOF_DEFAULTS["min_killed"])
    require = declaration.get("require_mutation", PROOF_DEFAULTS["require_mutation"])
    if not isinstance(mutants, int) or isinstance(mutants, bool) or mutants < 0:
        raise ValueError(f"{PROOF_FILE} 'mutants' must be a non-negative integer")
    if not isinstance(min_killed, int) or isinstance(min_killed, bool) or min_killed < 0:
        raise ValueError(f"{PROOF_FILE} 'min_killed' must be a non-negative integer")
    if not isinstance(require, bool):
        raise ValueError(f"{PROOF_FILE} 'require_mutation' must be a boolean")
    if require and (not sources or mutants <= 0):
        raise ValueError(
            f"{PROOF_FILE} 'require_mutation' needs 'sources' and 'mutants' greater than zero"
        )
    _scope_list(declaration.get("paths", PROOF_DEFAULTS["paths"]), "paths")
    _scope_int(declaration.get("max_files", PROOF_DEFAULTS["max_files"]), "max_files")
    _scope_int(declaration.get("max_lines", PROOF_DEFAULTS["max_lines"]), "max_lines")
    command = [
        sys.executable, str(script), "--repo", str(worktree), "--base", parent,
        "--tests", *tests,
    ]
    if pass_to_pass:
        command += ["--pass-to-pass", *pass_to_pass]
    if sources:
        command += ["--sources", *sources]
    if mutants:
        command += ["--mutants", str(mutants)]
    if min_killed != PROOF_DEFAULTS["min_killed"]:
        command += ["--min-killed", str(min_killed)]
    if require:
        command.append("--require-mutation")
    for key in waive:
        command += ["--waive", key]
    return command


def scope_step(worktree: Path, ref: str, repo: Path, run: Runner
               ) -> Optional[Tuple[bool, str, List[str]]]:
    """Scope verdict for a commit carrying `.aikit/proof.json`; None when absent."""
    path = worktree / PROOF_FILE
    if not path.is_file():
        return None
    try:
        declaration = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError) as exc:
        return False, str(exc), [f"[FAIL] scope declaration: {exc}"]
    if not isinstance(declaration, dict):
        return False, "not a JSON object", ["[FAIL] scope declaration: not a JSON object"]
    try:
        _scope_list(declaration.get("paths", []), "paths")
        _scope_int(declaration.get("max_files", 0), "max_files")
        _scope_int(declaration.get("max_lines", 0), "max_lines")
    except ValueError as exc:
        return False, str(exc), [f"[FAIL] scope declaration: {exc}"]
    files, lines = commit_files_and_lines(ref, repo, run)
    problems = scope_errors(declaration, files, lines)
    if problems:
        return False, "; ".join(problems), ["[FAIL] scope"] + [
            f"       {line}" for problem in problems for line in problem.splitlines()]
    return True, f"{len(files)} file(s), {lines} line(s) inside scope", ["[PASS] scope"]


def proof_gate_command(worktree: Path, ref: str, run: Runner) -> Optional[List[str]]:
    """The declared proof command for a commit, or None when no declaration exists."""
    path = Path(worktree) / PROOF_FILE
    if not path.is_file():
        return None
    try:
        declaration = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise ValueError(f"{PROOF_FILE} is not readable JSON: {exc}") from exc
    code, parent = run(["git", "rev-parse", f"{ref}^"], Path(worktree))
    if code != 0:
        return None
    parent = parent.strip().splitlines()[0].strip() if parent.strip() else ""
    if not parent:
        return None
    script = Path(worktree) / "scripts" / "proof_gate.py"
    if not script.is_file():
        raise ValueError("scripts/proof_gate.py is missing from the commit")
    return proof_command_from_declaration(
        declaration, worktree=Path(worktree), parent=parent, script=script
    )


def scanned_range(repo: Path, ref: str, run: Runner) -> str:
    """
    The commits this verification covers, as resolved SHAs: everything past the upstream when one
    resolves and is behind, otherwise this commit alone. Resolved, because the worktree is
    detached, where `@{u}` and `HEAD` mean something else or nothing.

    A bare SHA is returned only for a root commit, because `git log -p <sha>` walks every commit
    reachable from it: handing one back whenever no upstream resolved scanned the whole history,
    which stays red forever over a key already revoked (ADR-133, ADR-149).
    """
    head = run(["git", "rev-parse", ref], repo)[1].strip()
    code, upstream = run(["git", "rev-parse", f"{ref}@{{u}}"], repo)
    upstream = upstream.strip() if code == 0 else ""
    if upstream and upstream != head:
        return f"{upstream}..{head}"
    code, parent = run(["git", "rev-parse", f"{ref}^"], repo)
    parent = parent.strip() if code == 0 else ""
    return f"{parent}..{head}" if parent else head


def shrunk_files(sizes: Dict[str, Tuple[int, int]], ratio: float = SHRINK_RATIO,
                 min_bytes: int = SHRINK_MIN_BYTES) -> List[str]:
    """Each path, from (old, new) sizes, that fell below `ratio` of an old size of at least `min_bytes`."""
    return [f"{path}: {old:,} -> {new:,} bytes" for path, (old, new) in sorted(sizes.items())
            if old >= min_bytes and new < old * ratio and Path(path).name not in SHRINK_EXEMPT]


def tree_sizes(ref: str, repo: Path, run: Runner) -> Dict[str, int]:
    """Blob sizes in `ref`'s tree by path; empty when git cannot list it."""
    code, output = run(["git", "ls-tree", "-r", "-l", "-z", ref], repo)
    sizes: Dict[str, int] = {}
    if code != 0:
        return sizes
    for record in output.split("\0"):
        meta, _, path = record.partition("\t")
        fields = meta.split()
        if path and len(fields) == 4 and fields[1] == "blob" and fields[3].isdigit():
            sizes[path] = int(fields[3])
    return sizes


def shrink_warnings(ref: str, repo: Path, run: Runner) -> List[str]:
    """
    `[WARN]` lines for files `ref` cut below half their parent size, with Why/Fix; none for a root
    commit or one whose message carries `shrink-ok: <reason>`. A warning, never a failure.
    """
    if run(["git", "rev-parse", f"{ref}^"], repo)[0] != 0:
        return []
    code, message = run(["git", "log", "-1", "--format=%B", ref], repo)
    if code == 0 and _SHRINK_OK.search(message):
        return []
    before, after = tree_sizes(f"{ref}^", repo, run), tree_sizes(ref, repo, run)
    flagged = shrunk_files({path: (before[path], size) for path, size in after.items() if path in before})
    if not flagged:
        return []
    return [f"[WARN] {line}" for line in flagged] + [
        "Why: a modified file at under half its previous size is often content that was overwritten, "
        "and no other gate notices (IDEA-262).",
        "Fix: if the cut is intended, add a `shrink-ok: <reason>` line to the commit message; "
        "otherwise restore what was lost before pushing.",
    ]


def recovery_fix(ref: str, resolved: str, repo: Path, run: Runner) -> str:
    """
    The Fix line for a commit that fails on its own, chosen by where that commit is.

    The undo PRINCIPLE-018 R5 names, `git reset --soft HEAD^`, fits only an unpushed HEAD. It used
    to be printed for every failing commit, so verifying an older one with --ref, or one already on
    the remote, told the user to undo a different commit or rewrite published history (ADR-186).
    """
    target = run(["git", "rev-parse", ref], repo)[1].strip()
    # Published if the upstream has it, or - when there is no upstream, as after `git push origin
    # HEAD` without -u - if any remote-tracking branch does. Treating "no upstream" as "unpushed"
    # printed the reset advice for a commit already on the remote (ADR-188).
    upstream_has_it = run(["git", "merge-base", "--is-ancestor", target, "HEAD@{u}"], repo)[0] == 0
    remote_has_it = bool(run(["git", "branch", "-r", "--contains", target], repo)[1].strip())
    if upstream_has_it or remote_has_it:
        return (f"Fix: {resolved} is already on the remote, so do not rewrite it: add what is "
                "missing in a new commit (PRINCIPLE-018 R5).")
    if target != run(["git", "rev-parse", "HEAD"], repo)[1].strip():
        return (f"Fix: {resolved} is not HEAD, so undoing HEAD would remove a different commit: "
                "add what is missing in a new commit (PRINCIPLE-018 R5).")
    return ("Fix: while the commit is unpushed, `git reset --soft HEAD^` (PRINCIPLE-018 R5), add "
            "what is missing, and commit again.")


def stage_commit(repo: Path, run: Runner) -> str:
    """
    A commit object for exactly what is staged, without touching any ref.

    `git write-tree` reads the index and `git commit-tree` wraps it, so the
    detached worktree below proves the index, not the tree or HEAD
    (IDEA-1116). Object-db writes only; no branch, stash or worktree moves.
    Raises ValueError when there is nothing staged or git cannot answer.
    """
    code, _ = run(["git", "diff", "--cached", "--quiet"], repo)
    if code == 0:
        raise ValueError("nothing staged")
    code, tree = run(["git", "write-tree"], repo)
    tree = tree.strip()
    if code != 0 or not tree:
        raise ValueError(f"`git write-tree` failed: {tree[-200:]}")
    parent = run(["git", "rev-parse", "HEAD"], repo)
    argv = ["git", "commit-tree", tree, "-m",
            "aikit: staged-tree verification (detached, never pushed)"]
    if parent[0] == 0 and parent[1].strip():
        argv[3:3] = ["-p", parent[1].strip()]
    code, made = run(argv, repo)
    made = made.strip()
    if code != 0 or not made:
        raise ValueError(f"`git commit-tree` failed: {made[-200:]}")
    return made


def verify_staged(repo: Path = ROOT_DIR, runner: Optional[Runner] = None,
                  policy: str = "require-all") -> Tuple[int, List[str]]:
    """
    Verify the staged index on its own (IDEA-1116); returns (exit code, report).

    An empty index is inconclusive (IDEA-1118): there is nothing to prove, so
    nothing may read as green.
    """
    run = runner or run_command
    try:
        staged = stage_commit(repo, run)
    except ValueError as exc:
        if "nothing staged" in str(exc):
            return 1, ["[INCONCLUSIVE] No staged changes: nothing to verify.",
                       "Why: an empty index cannot prove a pass.",
                       "Fix: stage what the commit should record, then rerun "
                       "`python scripts/verify_commit.py --staged`."]
        return 1, [f"Error: the staged tree could not be read: {exc}",
                   "Why: `git write-tree` / `git commit-tree` must answer.",
                   "Fix: fix the git error above, then run this gate again."]
    code, report = verify_commit(staged, repo, runner, policy)
    if code != 0:
        report = report + ["Note: this verified the staged index as a detached commit; "
                           "unstage files that should not ship and stage files that "
                           "should, then rerun."]
    return code, report


def verify_commit(ref: str = "HEAD", repo: Path = ROOT_DIR,
                   runner: Optional[Runner] = None,
                   policy: str = "require-all") -> Tuple[int, List[str]]:
    """
    Run every gate against `ref` checked out on its own; returns (exit code, report lines).
    `runner` defaults to real subprocesses (PRINCIPLE-009 R4: the tests inject a double).
    `policy` names the evidence policy over the step attestations (IDEA-1169);
    the default keeps the historical all-must-pass verdict byte-identical.
    """
    run = runner or run_command
    report: List[str] = []
    code, resolved = run(["git", "rev-parse", "--short", ref], repo)
    if code != 0:
        return 1, ["Error: no commit to verify.",
                   f"Why: '{ref}' does not name a commit in {repo}.",
                   "Fix: commit first, or pass --ref <commit>."]
    resolved = resolved.strip()
    secret_range = scanned_range(repo, ref, run)

    tree = Path(tempfile.mkdtemp(prefix="aikit_verify_"))
    worktree = tree / "commit"
    worktree_added = False
    try:
        code, output = run(["git", "worktree", "add", "--detach", str(worktree), ref], repo)
        if code != 0:
            return 1, [f"Error: the commit {resolved} could not be checked out on its own.",
                       f"Why: `git worktree add` failed: {output[-300:]}",
                       "Fix: fix the git error above, then run this gate again."]
        worktree_added = True
        failures = []
        steps: List[Tuple[str, bool, str]] = []
        changed, _ = commit_files_and_lines(ref, repo, run)
        project_paths = project_path_violations(changed)
        if project_paths:
            report.append("[FAIL] project-files")
            report += [f"       {path}" for path in project_paths[:FAILURE_TAIL_LINES]]
            report.append("       AIKit tracks no project files; each project is its own repository.")
            failures.append("project-files")
            steps.append(("project-files", False, ", ".join(project_paths[:5])))
        else:
            report.append("[PASS] project-files")
            steps.append(("project-files", True, ""))
        for name, argv, timeout in gate_commands(secret_range):
            # An injected runner declares two arguments, so only the real one receives the bound.
            code, output = (run_command(argv, worktree, timeout) if runner is None
                            else run(argv, worktree))
            report.append(f"[{'PASS' if code == 0 else 'FAIL'}] {name}")
            tail = "\n".join([line for line in output.splitlines() if line.strip()]
                             [-FAILURE_TAIL_LINES:])
            steps.append((name, code == 0, tail))
            if code != 0:
                failures.append(name)
                report += [f"       {line}" for line in tail.splitlines()]
        try:
            proof_command = proof_gate_command(worktree, ref, run)
        except (OSError, ValueError) as exc:
            report.append(f"[FAIL] proof declaration: {exc}")
            failures.append("proof")
            steps.append(("proof", False, str(exc)))
        else:
            if proof_command:
                code, output = run(proof_command, worktree)
                report.append(f"[{'PASS' if code == 0 else 'FAIL'}] proof")
                tail = "\n".join([line for line in output.splitlines() if line.strip()]
                                 [-FAILURE_TAIL_LINES:])
                steps.append(("proof", code == 0, tail))
                if code != 0:
                    failures.append("proof")
                    report += [f"       {line}" for line in tail.splitlines()]
            scope = scope_step(worktree, ref, repo, run)
            if scope is not None:
                passed, evidence, scope_lines = scope
                report += scope_lines
                steps.append(("scope", passed, evidence))
                if not passed:
                    failures.append("scope")
    finally:
        # The worktree is removed whether or not a gate failed, and its registration with it.
        if worktree_added:
            run(["git", "worktree", "remove", "--force", str(worktree)], repo)
        shutil.rmtree(tree, ignore_errors=True)

    report += shrink_warnings(ref, repo, run)
    # IDEA-1169: the verdict is the named policy over the step attestations.
    # The default require-all keeps the historical verdict byte-identical.
    if evaluate is None or attest is None:  # pragma: no cover - import fallback
        bad, outcome = failures, ("pass" if not failures else "fail")
    else:
        try:
            verdict = evaluate(
                policy, [attest(name, "pass" if passed else "fail", evidence)
                         for name, passed, evidence in steps])
        except PolicyError as exc:
            return 2, [f"Error: unknown policy {policy!r}: {exc}",
                       "Why: the policy vocabulary is closed so a typo cannot silently "
                       "weaken the gate.",
                       "Fix: pass --policy require-all or --policy quorum:N."]
        outcome = str(verdict.get("outcome", "fail"))
        bad = list(verdict.get("failed", [])) or [name for name, ok, _ in steps if not ok]
    if outcome != OUTCOME_PASS:
        return 1, report + [
            f"Error: commit {resolved} does not pass on its own: {', '.join(bad)}.",
            "Why: the pre-commit gates ran on the working tree, so the commit can hold less than "
            "what was tested (PRINCIPLE-018 R3, R7).",
            recovery_fix(ref, resolved, repo, run),
        ]
    return 0, report + [f"[OK] Commit {resolved} passes every gate on its own."]


KNOWN_FLAGS = {"--ref", "--policy", "--staged", "--verbose", "-v", "--help", "-h"}

HELP_TEXT = """AIKit Post-Commit Verification (PRINCIPLE-018 R7)

Usage:
  python scripts/verify_commit.py [OPTIONS]

Checks out a commit into a throwaway worktree and runs the whole gate set there, so a commit
that holds less than the tree it was tested in is caught while it is still local. It also warns,
without failing, when the commit leaves a modified file under half its parent size; a
`shrink-ok: <reason>` line in the commit message records that the cut was intended.

Options:
  --ref <commit>   The commit to verify (default: HEAD)
  --policy <word>  Evidence policy over the step attestations: require-all
                   (default) or quorum:N (IDEA-1169)
  --staged         Verify the staged index instead of a commit: the index is
                   wrapped with write-tree/commit-tree (no ref moves) and the
                   gates run on that (IDEA-1116)
  --verbose, -v    Print the resolved commit range scanned for secrets
  -h, --help       Show this help message and exit

Exit codes:
  0  the commit is green    1  a gate failed, or the commit could not be checked out    2  CLI argument misuse
"""


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
    argv = sys.argv[1:]
    if "-h" in argv or "--help" in argv:
        print(HELP_TEXT, end="")
        sys.exit(0)
    unknown = [a for i, a in enumerate(argv) if a.startswith("-") and a not in KNOWN_FLAGS
               and (i == 0 or argv[i - 1] not in ("--ref", "--policy"))]
    if unknown:
        print(f"[INVALID USAGE] Unrecognized option(s): {', '.join(unknown)}", file=sys.stderr)
        print(f"Why: this gate accepts only {', '.join(sorted(KNOWN_FLAGS))}.", file=sys.stderr)
        print("Fix: run 'python scripts/verify_commit.py --help' to list valid options.", file=sys.stderr)
        sys.exit(2)
    target = "HEAD"
    if "--ref" in argv:
        index = argv.index("--ref")
        if index + 1 >= len(argv) or argv[index + 1].startswith("-"):
            print("[INVALID USAGE] --ref requires a commit.", file=sys.stderr)
            print("Why: there is no sensible default other than HEAD, which is already the default.",
                  file=sys.stderr)
            print("Fix: pass '--ref <commit>', or omit it to verify HEAD.", file=sys.stderr)
            sys.exit(2)
        target = argv[index + 1]
    if "--ref" in argv and "--staged" in argv:
        print("[INVALID USAGE] --ref and --staged verify different trees; pass one.",
              file=sys.stderr)
        print("Why: --ref checks out a commit while --staged wraps the index.",
              file=sys.stderr)
        print("Fix: drop one of the two flags and rerun.", file=sys.stderr)
        sys.exit(2)
    policy = "require-all"
    if "--policy" in argv:
        index = argv.index("--policy")
        if index + 1 >= len(argv) or argv[index + 1].startswith("-"):
            print("[INVALID USAGE] --policy requires a policy word.", file=sys.stderr)
            print("Why: the policy vocabulary is closed so a typo cannot silently weaken the gate.",
                  file=sys.stderr)
            print("Fix: pass '--policy require-all' or '--policy quorum:N'.", file=sys.stderr)
            sys.exit(2)
        policy = argv[index + 1]

    print("=" * 58)
    print("POST-COMMIT VERIFICATION (PRINCIPLE-018 R7)")
    print("=" * 58)
    if "--verbose" in argv or "-v" in argv:
        if "--staged" in argv:
            print("Staged index scan: the staged range is verified, not a commit range.")
        else:
            print(f"Secret scan range: {scanned_range(ROOT_DIR, target, run_command)}")
    if "--staged" in argv:
        exit_code, lines = verify_staged(ROOT_DIR, None, policy)
    else:
        exit_code, lines = verify_commit(target, policy=policy)
    stream = sys.stdout if exit_code == 0 else sys.stderr
    for line in lines:
        print(line, file=stream)
    print("=" * 58, file=stream)
    sys.exit(exit_code)
