"""Local publish guard: block raw git pushes so only `aikit.py publish` uploads.

The guard is a `.git/hooks/pre-push` wrapper. `aikit publish` installs it and
sets `AIKIT_PUBLISH=1` for the push subprocess; every other push exits before
the remote sees a ref. A pre-existing hook is preserved as `pre-push.local`
and invoked after the guard passes.
"""

from __future__ import annotations

import os
import re
import shlex
import stat
import subprocess
from contextlib import contextmanager
from pathlib import Path
from typing import Iterator, List, Optional

HOOK_MARKER = "# AIKit publish guard"
LOCAL_HOOK_NAME = "pre-push.local"
PUBLISH_ENV = "AIKIT_PUBLISH"
_HOOK_NAME = "pre-push"
_SAFE_NAME = re.compile(r"^[A-Za-z0-9_-]+$")


def _config_value(raw: str) -> str:
    """A git config value as git reads it: quotes removed, and ; or # outside quotes ends it."""
    value, quoted, escaped = [], False, False
    for char in raw.strip():
        if escaped:
            value.append(char)
            escaped = False
        elif char == "\\":
            escaped = True
        elif char == '"':
            quoted = not quoted
        elif char in ";#" and not quoted:
            break
        else:
            value.append(char)
    return "".join(value).strip()


def _config_hooks_path(config: Path, seen: Optional[set[Path]] = None) -> Optional[str]:
    """core.hooksPath from one git config file, following include.path files."""
    if seen is None:
        seen = set()
    try:
        resolved = config.resolve()
    except OSError:
        resolved = config
    if resolved in seen:
        return None
    seen.add(resolved)
    try:
        lines = config.read_text(encoding="utf-8", errors="replace").splitlines()
    except OSError:
        return None
    section = ""
    value: Optional[str] = None
    for raw_line in lines:
        line = raw_line.strip()
        if not line or line.startswith(("#", ";")):
            continue
        if line.startswith("[") and line.endswith("]"):
            section = line[1:-1].strip().lower()
            continue
        if "=" not in line:
            continue
        key, raw = line.split("=", 1)
        key = key.strip().lower()
        if section == "core" and key == "hookspath":
            value = _config_value(raw) or None
        elif section == "include" and key == "path":
            include = _config_value(raw)
            if include:
                path = Path(include).expanduser()
                if not path.is_absolute():
                    path = config.parent / path
                included = _config_hooks_path(path, seen)
                if included:
                    value = included
    return value


def _local_hooks_path(project_root: Path) -> Optional[str]:
    """core.hooksPath from the repository-local .git/config, without spawning git."""
    return _config_hooks_path(Path(project_root) / ".git" / "config")


def _global_hooks_path() -> Optional[str]:
    """core.hooksPath from the global and system config files, without spawning git."""
    paths: List[Path] = []
    if not os.environ.get("GIT_CONFIG_NOSYSTEM"):
        system = os.environ.get("GIT_CONFIG_SYSTEM")
        if system is None:
            paths.append(Path("/etc/gitconfig"))
        elif system:
            paths.append(Path(system).expanduser())
    configured = os.environ.get("GIT_CONFIG_GLOBAL")
    if configured is None:
        home = Path.home()
        paths.append(Path(os.environ.get("XDG_CONFIG_HOME", home / ".config")) / "git" / "config")
        paths.append(home / ".gitconfig")
    elif configured:
        paths.append(Path(configured).expanduser())
    value: Optional[str] = None
    for path in paths:
        if path.is_file():
            found = _config_hooks_path(path)
            if found:
                value = found
    return value


def _git_config_value(project_root: Path, key: str) -> Optional[str]:
    """Read one git config value, or None when it is unset or git cannot run."""
    try:
        result = subprocess.run(
            ["git", "config", "--get", key],
            cwd=project_root,
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            timeout=10,
        )
    except (OSError, subprocess.TimeoutExpired):
        return None
    if result.returncode != 0:
        return None
    value = result.stdout.strip()
    return value or None


def hook_path(project_root: Path) -> Optional[Path]:
    """The repository's pre-push hook path, or None when the folder is not a git repo."""
    project_root = Path(project_root)
    dot_git = project_root / ".git"
    if dot_git.is_dir():
        # core.hooksPath redirects Git away from .git/hooks; install where Git looks.
        configured = _local_hooks_path(project_root)
        if configured is None:
            # The local file does not set it, but global/system config or an
            # include may; read those files directly so the unit tier spawns nothing.
            configured = _global_hooks_path()
        if configured:
            path = Path(configured).expanduser()
            if not path.is_absolute():
                path = project_root / path
            return path / _HOOK_NAME
        return dot_git / "hooks" / _HOOK_NAME
    if not dot_git.exists():
        return None
    # A worktree or submodule stores `.git` as a file; ask git for the real hooks path.
    configured = _git_config_value(project_root, "core.hooksPath")
    if configured:
        path = Path(configured).expanduser()
        if not path.is_absolute():
            path = project_root / path
        return path / _HOOK_NAME
    try:
        result = subprocess.run(
            ["git", "rev-parse", "--git-path", "hooks"],
            cwd=project_root,
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            timeout=10,
        )
    except (OSError, subprocess.TimeoutExpired):
        return None
    if result.returncode != 0 or not result.stdout.strip():
        return None
    path = Path(result.stdout.strip())
    if not path.is_absolute():
        path = project_root / path
    return path / _HOOK_NAME


def install_pre_push_hook(project_root: Path, project_name: str) -> Optional[Path]:
    """Install the guard and return its path, or None when there is no git repository."""
    target = hook_path(project_root)
    if target is None:
        return None
    if not _SAFE_NAME.fullmatch(project_name):
        raise ValueError(f"project name is not safe for a hook: {project_name!r}")
    target.parent.mkdir(parents=True, exist_ok=True)
    if target.is_file():
        existing = _read_text(target)
        if HOOK_MARKER not in existing:
            local = target.with_name(LOCAL_HOOK_NAME)
            if not local.exists():
                target.replace(local)
    target.write_text(_hook_script(project_name), encoding="utf-8", newline="\n")
    try:
        target.chmod(target.stat().st_mode | stat.S_IXUSR | stat.S_IXGRP | stat.S_IXOTH)
    except OSError:
        pass
    return target


def is_guard_installed(project_root: Path) -> bool:
    """Whether the project's pre-push hook is the AIKit guard."""
    target = hook_path(project_root)
    return bool(target and target.is_file() and HOOK_MARKER in _read_text(target))


@contextmanager
def publish_environment() -> Iterator[None]:
    """Mark the current process as an authorised AIKit publish."""
    previous = os.environ.get(PUBLISH_ENV)
    os.environ[PUBLISH_ENV] = "1"
    try:
        yield
    finally:
        if previous is None:
            os.environ.pop(PUBLISH_ENV, None)
        else:
            os.environ[PUBLISH_ENV] = previous


def _hook_script(project_name: str) -> str:
    quoted = shlex.quote(project_name)
    return f"""#!/bin/sh
{HOOK_MARKER}
# Direct pushes bypass AIKit's media, license, topics and gate sequence.
if [ "$AIKIT_PUBLISH" != "1" ]; then
  echo "AIKit: direct git push is blocked for {quoted}." >&2
  echo "Use: python aikit.py publish {quoted}" >&2
  exit 1
fi
local_hook="$(dirname "$0")/{LOCAL_HOOK_NAME}"
if [ -x "$local_hook" ]; then
  exec "$local_hook" "$@"
fi
exit 0
"""


def _read_text(path: Path) -> str:
    try:
        return path.read_text(encoding="utf-8", errors="replace")
    except OSError:
        return ""
