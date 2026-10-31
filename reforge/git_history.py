"""Bounded Git reads used by the auditor, the repair review and delivery."""

import os
import re
import subprocess
from functools import lru_cache
from pathlib import Path
from typing import Dict, List, Optional, Sequence, Set, Tuple

from reforge.model import CommitInfo

GIT_TIMEOUT_SECONDS = 60
FIELD = "\x1f"


def _repo_key(repo: Path) -> str:
    """A stable cache key for one checkout path."""
    return os.path.abspath(os.fspath(repo))


def run_git(repo: Path, *args: str, timeout: int = GIT_TIMEOUT_SECONDS) -> Tuple[int, str]:
    """Run git with stdin closed and a timeout; returns (exit code, combined output)."""
    try:
        done = subprocess.run(
            ["git", "-c", "core.quotePath=false", *args],
            cwd=str(repo),
            stdin=subprocess.DEVNULL,
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            timeout=timeout,
        )
    except (OSError, subprocess.SubprocessError) as exc:
        return -1, str(exc)
    # Output is preserved exactly: `git status --porcelain` and `git show` start with significant
    # whitespace, and stripping it silently renamed the first status path ("app.py" -> "pp.py").
    return done.returncode, (done.stdout + done.stderr)


def is_git_repo(repo: Path) -> bool:
    code, _ = run_git(repo, "rev-parse", "--is-inside-work-tree")
    return code == 0


def head_sha(repo: Path) -> str:
    code, out = run_git(repo, "rev-parse", "HEAD")
    return out.strip() if code == 0 else ""


def commit_window(repo: Path, limit: int) -> List[CommitInfo]:
    """The newest `limit` commits, newest first."""
    if limit < 1:
        return []
    code, out = run_git(repo, "log", f"-n{limit}", f"--format=%H{FIELD}%s{FIELD}%an{FIELD}%aI")
    if code != 0:
        return []
    commits = []
    for line in out.splitlines():
        parts = line.split(FIELD)
        if len(parts) == 4:
            commits.append(CommitInfo(parts[0], parts[1], parts[2], parts[3]))
    return commits


def commit_info(repo: Path, sha: str) -> Optional[CommitInfo]:
    code, out = run_git(repo, "show", "-s", f"--format=%H{FIELD}%s{FIELD}%an{FIELD}%aI", sha)
    if code != 0:
        return None
    parts = out.strip().split(FIELD)
    return CommitInfo(*parts) if len(parts) == 4 else None


def commit_count(repo: Path) -> int:
    code, out = run_git(repo, "rev-list", "--count", "HEAD")
    out = out.strip()
    return int(out) if code == 0 and out.isdigit() else 0


@lru_cache(maxsize=2048)
def _changed_files(repo_key: str, sha: str) -> Tuple[Tuple[str, str], ...]:
    code, out = run_git(Path(repo_key), "diff-tree", "--root", "--no-commit-id", "--name-status",
                        "-r", "--no-renames", "-z", sha)
    if code != 0:
        return ()
    parts = out.split("\0")
    pairs: List[Tuple[str, str]] = []
    index = 0
    while index + 1 < len(parts):
        status, path = parts[index], parts[index + 1]
        if status and path:
            pairs.append((status[:1], path))
        index += 2
    return tuple(pairs)


def changed_files(repo: Path, sha: str) -> List[Tuple[str, str]]:
    """(status, relative path) pairs a commit changed; root commits included."""
    return list(_changed_files(_repo_key(repo), sha))


@lru_cache(maxsize=4096)
def _added_lines(repo_key: str, sha: str, path: str) -> Tuple[int, ...]:
    parent = _parent_sha(repo_key, sha)
    if not parent:
        source = _file_at(repo_key, sha, path)
        return tuple(range(1, len(source.splitlines()) + 1)) if source else ()
    code, out = run_git(Path(repo_key), "diff", "--unified=0", parent, sha, "--", path)
    if code != 0:
        return ()
    return tuple(sorted(_added_from_diff(out)))


def added_lines(repo: Path, sha: str, path: str) -> Set[int]:
    """Line numbers a commit adds to `path`, from a zero-context diff."""
    return set(_added_lines(_repo_key(repo), sha, path))


@lru_cache(maxsize=1024)
def _changed_files_range(repo_key: str, base: str, head: str) -> Tuple[Tuple[str, str], ...]:
    if not base:
        code, out = run_git(Path(repo_key), "ls-tree", "-r", "--name-only", "-z", head)
        return tuple(("A", path) for path in out.split("\0") if path) if code == 0 else ()
    code, out = run_git(Path(repo_key), "diff", "--name-status", "-z", "--no-renames", base, head)
    if code != 0:
        return ()
    parts = out.split("\0")
    pairs: List[Tuple[str, str]] = []
    index = 0
    while index + 1 < len(parts):
        status, path = parts[index], parts[index + 1]
        if status and path:
            pairs.append((status[:1], path))
        index += 2
    return tuple(pairs)


def changed_files_range(repo: Path, base: str, head: str) -> List[Tuple[str, str]]:
    """(status, path) for the net change between two commits; `base` empty means `head` is a root."""
    return list(_changed_files_range(_repo_key(repo), base, head))


@lru_cache(maxsize=2048)
def _added_lines_range(repo_key: str, base: str, head: str, path: str) -> Tuple[int, ...]:
    if not base:
        source = _file_at(repo_key, head, path)
        return tuple(range(1, len(source.splitlines()) + 1)) if source else ()
    code, out = run_git(Path(repo_key), "diff", "--unified=0", base, head, "--", path)
    if code != 0:
        return ()
    return tuple(sorted(_added_from_diff(out)))


def added_lines_range(repo: Path, base: str, head: str, path: str) -> Set[int]:
    """Line numbers the whole stage (`base`..`head`) adds to `path`, as it stands at `head`."""
    return set(_added_lines_range(_repo_key(repo), base, head, path))


def range_diff(repo: Path, base: str, head: str, path: str) -> str:
    """The net diff of one path across a whole stage, with three lines of context."""
    if not base:
        code, out = run_git(repo, "show", "--format=", "--unified=3", head, "--", path)
        return out if code == 0 else ""
    code, out = run_git(repo, "diff", "--unified=3", base, head, "--", path)
    return out if code == 0 else ""


def _added_from_diff(diff_text: str) -> Set[int]:
    """Line numbers a zero-context diff adds, read from its hunk headers."""
    lines: Set[int] = set()
    current = 0
    hunk = re.compile(r"^@@ -\d+(?:,\d+)? \+(\d+)(?:,(\d+))? @@")
    for line in diff_text.splitlines():
        match = hunk.match(line)
        if match:
            current = int(match.group(1))
            continue
        if line.startswith("+") and not line.startswith("+++"):
            lines.add(current)
            current += 1
        elif line.startswith(" "):
            current += 1
    return lines


@lru_cache(maxsize=4096)
def _parent_sha(repo_key: str, sha: str) -> str:
    code, out = run_git(Path(repo_key), "rev-parse", f"{sha}^")
    return out.strip() if code == 0 else ""


def parent_sha(repo: Path, sha: str) -> str:
    """The first parent of `sha`, or an empty string for a root commit."""
    return _parent_sha(_repo_key(repo), sha)


@lru_cache(maxsize=512)
def _file_at(repo_key: str, sha: str, path: str) -> Optional[str]:
    code, out = run_git(Path(repo_key), "show", f"{sha}:{path}")
    return out if code == 0 else None


def file_at(repo: Path, sha: str, path: str) -> Optional[str]:
    """One file's complete text at a commit, or None when it did not exist there."""
    return _file_at(_repo_key(repo), sha, path)


def worktree_diff(repo: Path, paths: Sequence[str]) -> str:
    args = ["diff", "--unified=3", "--"] + list(paths)
    code, out = run_git(repo, *args)
    return out if code == 0 else ""


def status_paths(repo: Path) -> List[str]:
    """Changed tracked paths, including both sides of a rename, from NUL-delimited porcelain."""
    code, out = run_git(repo, "status", "--porcelain", "-z", "--untracked-files=no")
    if code != 0:
        return []
    entries = out.split("\0")
    paths: List[str] = []
    index = 0
    while index < len(entries):
        entry = entries[index]
        index += 1
        if len(entry) < 4:
            continue
        status, path = entry[:2], entry[3:]
        paths.append(path)
        if "R" in status or "C" in status:
            original = entries[index] if index < len(entries) else ""
            if original:
                paths.append(original)
            index += 1
    return paths


def untracked_paths(repo: Path) -> List[str]:
    code, out = run_git(repo, "ls-files", "--others", "--exclude-standard", "-z")
    return [path for path in out.split("\0") if path] if code == 0 else []


def diff_paths(diff_text: str) -> List[str]:
    """Paths in a unified diff, in first-seen order."""
    paths: List[str] = []
    for line in diff_text.splitlines():
        if line.startswith("+++ b/"):
            path = line[6:].strip()
            if path not in paths:
                paths.append(path)
    return paths


def commit_paths(repo: Path, sha: str) -> List[str]:
    code, out = run_git(repo, "show", "--pretty=format:", "--name-only", sha)
    return [line.strip() for line in out.splitlines() if line.strip()] if code == 0 else []


def stage_and_commit(repo: Path, paths: Sequence[str], message: str) -> Tuple[int, str]:
    """Explicit `git add -- <paths>` then commit; never stages the whole tree."""
    code, out = run_git(repo, "add", "--", *paths)
    if code != 0:
        return code, out
    return run_git(repo, "commit", "-m", message)


def push(repo: Path) -> Tuple[int, str]:
    """Adaptive, never forced push: set the upstream once when origin exists."""
    code, out = run_git(repo, "push", timeout=120)
    if code == 0:
        return 0, out
    if "has no upstream branch" in out or "no upstream" in out.lower():
        code, upstream = run_git(repo, "remote", "get-url", "origin")
        if code == 0:
            return run_git(repo, "push", "-u", "origin", "HEAD", timeout=120)
    return code, out


def dirty_paths(repo: Path) -> Dict[str, str]:
    """Tracked and untracked paths that differ from HEAD, for delivery refusal."""
    tracked = {path: "modified" for path in status_paths(repo)}
    tracked.update({path: "untracked" for path in untracked_paths(repo)})
    return tracked
