"""Patch review, repair re-checks and bounded test execution."""

import shlex
import subprocess
import sys
from pathlib import Path
from typing import Callable, Dict, List, Optional, Sequence, Tuple

from reforge.detectors import detect_source
from reforge.git_history import diff_paths, untracked_paths, worktree_diff
from reforge.model import Repair

TEST_TIMEOUT_SECONDS = 900
TAIL_LINES = 20
Scanner = Callable[[str, str], Sequence[Tuple[str, int, str, str]]]


def _shell(command: str) -> object:
    return f'cmd /d /s /c "{command}"' if sys.platform == "win32" else ["/bin/sh", "-c", command]


def run_test_command(command: str, cwd: Path,
                     timeout: int = TEST_TIMEOUT_SECONDS) -> Dict[str, object]:
    """Run a project command with stdin closed and the whole process tree bounded."""
    try:
        done = subprocess.run(
            _shell(command), cwd=str(cwd), stdin=subprocess.DEVNULL, capture_output=True,
            text=True, encoding="utf-8", errors="replace", timeout=timeout,
        )
    except (OSError, subprocess.SubprocessError) as exc:
        return {"command": command, "code": -1, "passed": False, "output": str(exc), "tail": [str(exc)]}
    output = (done.stdout + done.stderr).strip()
    tail = [line for line in output.splitlines() if line.strip()][-TAIL_LINES:]
    return {"command": command, "code": done.returncode, "passed": done.returncode == 0,
            "output": output, "tail": tail}


def python_command(*args: str) -> str:
    argv = [sys.executable, *args]
    return subprocess.list2cmdline(argv) if sys.platform == "win32" else shlex.join(argv)


def default_test_command(root: Path) -> str:
    """The repository's own unittest discovery when it has tests; never a guessed runner."""
    tests = root / "tests"
    if tests.is_dir() and any(tests.glob("test*.py")):
        return python_command("-m", "unittest", "discover", "tests")
    if any(root.glob("test*.py")):
        return python_command("-m", "unittest", "discover", "-s", ".", "-p", "test*.py")
    return ""


def recheck_repairs(root: Path, repairs: Sequence[Repair]) -> List[str]:
    """Every repaired rule must be absent from the file it was repaired in."""
    issues: List[str] = []
    checks = {(item.path, item.code) for item in repairs if item.applied}
    for relative, code in sorted(checks):
        path = root / relative
        try:
            source = path.read_text(encoding="utf-8")
        except OSError as exc:
            issues.append(f"{relative}: the repaired file could not be read back: {exc}")
            continue
        remaining = [item for item in detect_source(relative, source, "worktree")
                     if item.code == code]
        if remaining:
            issues.append(f"{relative}:{remaining[0].line}: {code} is still present after the repair")
    return issues


def review_patch(root: Path, allowed_paths: Sequence[str],
                 scanner: Optional[Scanner] = None) -> List[str]:
    """Review the actual diff: only intended paths, no credential-shaped added line."""
    allowed = {path.replace("\\", "/") for path in allowed_paths}
    diff = worktree_diff(root, [])
    changed = set(diff_paths(diff))
    changed.update(path.replace("\\", "/") for path in untracked_paths(root))
    issues = [f"{path}: changed outside the repair's allowed paths" for path in sorted(changed - allowed)]
    if not changed:
        issues.append("the repair produced no patch to review")
    if scanner is not None:
        for label, line, detector, excerpt in scanner("reforge-patch", diff):
            issues.append(f"{label}:{line}: credential-shaped added line ({detector}): {excerpt}")
    return issues
