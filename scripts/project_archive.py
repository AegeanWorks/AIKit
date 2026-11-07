"""
Archive a project: move it to ``projects/archive/`` and mark its GitHub repository archived.

``python aikit.py archive <name> --reason <why>`` commits an ``Archived`` notice into
the project's README, pushes it, sets the GitHub description to ``[ARCHIVED] ...``
and runs ``gh repo archive``, then moves the folder to ``projects/archive/<name>``
and records ``archived`` in ``.aikit/project.json``. Nothing is uploaded without a
clean secret scan (PRINCIPLE-019), pushes are never forced (PRINCIPLE-018 R4), and
no credential in a remote URL is ever printed (ADR-191).
"""

import re
import shutil
import time
from pathlib import Path
from typing import Callable, Dict, List, Optional, Tuple

from scripts.disruption_recovery import ROOT_DIR, atomic_write_json, file_lock
from scripts.project_publish import (
    PUBLISH_TIMEOUT_SECONDS,
    extract_readme_description,
    get_project_repo_url,
    hide_url_credentials,
    push_range,
    scan_refusal,
)
from scripts.project_registry import (
    DESCRIPTION_MAX,
    DESCRIPTION_MIN,
    ProjectError,
    load_attached,
    projects_dir,
)
from scripts.update_knowledge_base import write_generated_file

Runner = Callable[[List[str], Path], Tuple[int, str]]
ARCHIVE_DIRNAME = "archive"
_ARCHIVE_BANNER_RE = re.compile(r"^>\s*\*\*Archived\*\*")


def _is_archive_banner(line: str) -> bool:
    """Whether a line is the notice this module inserts, not a project description."""
    return bool(_ARCHIVE_BANNER_RE.match(line.strip()))


def _visible_text(raw: str) -> str:
    """Markdown/HTML line reduced to visible text; media-only lines reduce to empty."""
    text = re.sub(r"<!--.*?-->", "", raw)
    text = re.sub(r"<[^>]+>", "", text)
    return text.strip()


def _triad(what: str, why: str, fix: str) -> str:
    return hide_url_credentials(f"Error: {what}\nWhy: {why}\nFix: {fix}")


def archive_dir(workspace: Path = ROOT_DIR) -> Path:
    """The folder archived projects live in: ``projects/archive/`` (git-ignored via ``projects/``)."""
    return projects_dir(Path(workspace)) / ARCHIVE_DIRNAME


def archived_destination(workspace: Path, name: str, to: Optional[Path] = None) -> Path:
    """Where ``name`` moves to: ``to`` when given, else ``projects/archive/<name>``.

    When ``to`` names a folder other than ``name`` it is the containing folder,
    so ``--to /tmp/out`` archives to ``/tmp/out/<name>``; when it already ends
    with ``name`` it is the exact path.
    """
    if to is not None:
        dest = Path(to)
        if dest.name != name:
            return dest / name
        return dest
    return archive_dir(workspace) / name


def validate_archive_move(src: Path, dst: Path) -> Optional[str]:
    """The refusal triad when ``src`` cannot move to ``dst``, else None."""
    import os as _os
    try:
        src_resolved = src.resolve()
        dst_resolved = dst.resolve()
        same = src_resolved == dst_resolved
        if not same and _os.path.normcase(str(src_resolved)) == _os.path.normcase(str(dst_resolved)):
            same = True
    except (OSError, RuntimeError, ValueError):
        return _triad(f"cannot resolve the archive destination {dst}.",
                      "the operating system denied the path lookup.",
                      "check the path permissions, then retry.")
    if same:
        return _triad(f"cannot archive '{src.name}' onto itself.",
                      "the source and the destination are the same folder.",
                      "pass another destination with `--to <dir>`, or omit `--to`.")
    if dst.exists():
        return _triad(f"cannot archive to {dst}: it already exists.",
                      "a move must not overwrite an existing folder.",
                      f"remove or rename {dst}, or pass `--to <dir>`.")
    try:
        if dst.resolve().is_relative_to(src.resolve()):
            return _triad(f"cannot archive '{src.name}' inside itself ({dst}).",
                          "the destination sits inside the folder being moved.",
                          "pass a destination outside the project, e.g. the default `projects/archive/`.")
    except (OSError, RuntimeError, ValueError):
        return _triad(f"cannot resolve the archive destination {dst}.",
                      "the operating system denied the path lookup.",
                      "check the path permissions, then retry.")
    return None


def archive_notice(reason: str, date_str: str) -> str:
    """The one-paragraph banner ``update_readme_for_archive`` inserts after the description."""
    return f"> **Archived**: {reason.strip()} (archived {date_str}). This project is read-only; its GitHub repository is archived."


def update_readme_for_archive(readme_path: Path, reason: str, date_str: str) -> bool:
    """Insert the archive banner after the README description; idempotent.

    The first paragraph (the GitHub description source) is left untouched so
    ``extract_readme_description`` keeps returning it; the banner goes right
    after it. Returns whether the file changed.
    """
    try:
        with open(readme_path, "r", encoding="utf-8-sig", errors="replace", newline="") as handle:
            text = handle.read()
    except OSError:
        return False
    if "> **Archived**" in text:
        return False
    newline = "\r\n" if "\r\n" in text else "\n"
    lines = text.split(newline)

    def _is_title(line: str) -> bool:
        stripped = line.lstrip()
        # ATX headings '#', '##', ... '######' followed by space or EOL.
        # '#hashtag' without a space is paragraph text, not a heading.
        return bool(re.match(r"#{1,6}(?:\s|$)", stripped))

    title = next((i for i, line in enumerate(lines) if _is_title(line)), None)
    start = (title + 1) if title is not None else 0
    # Find the description block: first non-empty, non-badge block after the title.
    idx = start
    while idx < len(lines):
        stripped = lines[idx].strip()
        if (not stripped or stripped.startswith(("[![", "![", "<!--"))
                or _is_archive_banner(stripped) or not _visible_text(stripped)):
            idx += 1
            continue
        break
    if idx >= len(lines):
        # No description block: append the banner at the end.
        updated = text.rstrip("\r\n") + newline + newline + archive_notice(reason, date_str) + newline
        try:
            write_generated_file(readme_path, updated, newline="")
        except OSError:
            return False
        return True
    # Extend over the whole paragraph (consecutive non-empty lines).
    # A '#' line ends the block only when it is a real ATX heading
    # ('#'-'######' followed by space or EOL); '#hashtag' text is
    # paragraph content, not a heading.
    end = idx
    while end < len(lines) and lines[end].strip() != "":
        stripped = lines[end].strip()
        if re.match(r"#{1,6}(?:\s|$)", stripped):
            break
        end += 1
    banner = archive_notice(reason, date_str)
    # Insert exactly one blank before and after the banner without touching
    # the rest of the file: when the next line is already blank it serves as
    # the trailing separator, otherwise add one. The description block ends
    # at a non-blank line, so the leading blank is always needed.
    if end < len(lines) and lines[end].strip() == "":
        lines[end:end] = ["", banner]
    else:
        lines[end:end] = ["", banner, ""]
    try:
        write_generated_file(readme_path, newline.join(lines).rstrip("\r\n") + newline, newline="")
    except OSError:
        return False
    return True


def archive_github_description(original: str, override: Optional[str] = None) -> str:
    """The GitHub description for an archived repo: ``[ARCHIVED] <original>`` within 350 chars."""
    if override is not None:
        text = override.strip()
        if not text.lower().startswith("[archived]"):
            text = f"[ARCHIVED] {text}"
    else:
        text = original.strip()
        if not text.lower().startswith("[archived]"):
            text = f"[ARCHIVED] {text}" if text else "[ARCHIVED]"
    if len(text) <= DESCRIPTION_MAX:
        return text
    # Keep the marker, cut the rest at a word boundary like publish does.
    head = text[: DESCRIPTION_MAX - 3].rstrip(" ,;:")
    cut = head.rfind(" ", 0, DESCRIPTION_MAX - 3)
    head = head[:cut].rstrip(" ,;:") if cut > 0 else head
    return head + "..."


def _default_runner(argv: List[str], cwd: Path) -> Tuple[int, str]:
    import subprocess

    try:
        done = subprocess.run(argv, cwd=cwd, stdin=subprocess.DEVNULL, capture_output=True,
                              text=True, encoding="utf-8", errors="replace",
                              timeout=PUBLISH_TIMEOUT_SECONDS)
    except (OSError, subprocess.TimeoutExpired) as exc:
        return -1, str(exc)
    return done.returncode, (done.stdout + done.stderr).strip()


def _attached_path(workspace: Path) -> Path:
    return projects_dir(Path(workspace)) / "attached.json"


def _forget_or_move_attached(workspace: Path, name: str, src: Path, dst: Path) -> None:
    """Keep ``attached.json`` true after the move: forget inside-``projects/`` targets, else repoint."""
    from scripts.project_registry import ProjectError as _ProjectError
    path = _attached_path(workspace)
    with file_lock(path):
        try:
            attached = load_attached(workspace)
        except (OSError, ValueError, KeyError, _ProjectError):
            return
        if name not in attached:
            return
        try:
            inside = dst.resolve().is_relative_to(projects_dir(Path(workspace)).resolve())
        except (OSError, RuntimeError, ValueError):
            inside = False
        if inside:
            attached.pop(name, None)
        else:
            attached[name] = str(dst)
        try:
            atomic_write_json(path, {"schema": 1, "projects": attached})
        except OSError:
            return


def _record_archived_config(project_path: Path, reason: str, date_str: str,
                            repo: str, description: str) -> None:
    """Record the archive in ``.aikit/project.json`` without touching other keys."""
    from scripts.project_registry import ProjectError as _ProjectError
    from scripts.project_registry import config_path, load_config

    path = config_path(project_path)
    with file_lock(path):
        try:
            config = load_config(project_path)
        except (OSError, ValueError, KeyError, _ProjectError) as exc:
            raise _ProjectError(f"cannot record archive in {path}: {exc}",
                                "the project record could not be read.",
                                "restore .aikit/project.json from git, then archive again.") from exc
        config["archived"] = True
        config["archived_at"] = date_str
        config["archive_reason"] = reason
        config["archive_repo"] = repo
        config["archive_description"] = description
        atomic_write_json(path, config)


def archive_project(project_path: Path, name: str, reason: str, workspace: Path = ROOT_DIR,
                    to: Optional[Path] = None, description: Optional[str] = None,
                    offline: bool = False, allow_dirty: bool = False,
                    runner: Optional[Runner] = None,
                    date_str: Optional[str] = None) -> Tuple[int, str]:
    """Move ``project_path`` to the archive and archive its GitHub repository.

    Returns ``(exit code, report)`` like ``publish_project``: ``runner`` defaults
    to real git/gh calls (tests inject a fake). ``date_str`` defaults to today.
    """
    from scripts.project_topics import repo_slug

    run = runner or _default_runner
    workspace = Path(workspace)
    src = Path(project_path)
    if not src.is_dir():
        return 1, _triad(f"project '{name}' is missing at {src}.",
                          "its folder is gone, so there is nothing to archive.",
                          "restore the folder, or drop the name from the registry.")
    dst = archived_destination(workspace, name, to)
    refusal = validate_archive_move(src, dst)
    if refusal:
        return 1, refusal
    if is_archived(src):
        return 1, _triad(f"'{name}' is already archived.",
                         "the project record already marks it archived.",
                         "unarchive it first, or archive another project; nothing was moved.")
    reason = (reason or "").strip()
    if not reason:
        return 1, _triad(f"archiving '{name}' needs a reason.",
                          "the README banner and the project record name why it was retired.",
                          f"pass `--reason \"<why this project is retired>\"`, e.g. "
                          f"`python aikit.py archive {name} --reason \"superseded by X\"`.")
    if "\n" in reason or "\r" in reason:
        return 1, _triad(f"invalid --reason (must be one line).",
                          "the archive banner and record hold one line of why it was retired.",
                          "write one line without line breaks.")
    if len(reason) > 500:
        return 1, _triad(f"invalid --reason ({len(reason)} characters).",
                          "the archive banner holds at most 500 characters.",
                          "write one line of at most 500 characters.")
    day = date_str or time.strftime("%Y-%m-%d")
    readme_path = src / "README.md"
    try:
        readme_text = readme_path.read_text(encoding="utf-8-sig", errors="replace")
    except OSError:
        readme_text = ""
    original = extract_readme_description(src)
    if description is not None:
        override = description.strip()
        if "\n" in override or "\r" in override:
            return 1, _triad(f"invalid --description (must be one line).",
                             f"an override holds one line of {DESCRIPTION_MIN}-{DESCRIPTION_MAX} characters.",
                             f"write one line of {DESCRIPTION_MIN}-{DESCRIPTION_MAX} characters.")
        if len(override) < DESCRIPTION_MIN or len(override) > DESCRIPTION_MAX:
            return 1, _triad(f"invalid --description ({len(override)} characters).",
                             f"an override holds one line of {DESCRIPTION_MIN}-{DESCRIPTION_MAX} characters.",
                             f"write one line of {DESCRIPTION_MIN}-{DESCRIPTION_MAX} characters.")
    elif "<FILL:" in readme_text:
        return 1, _triad(f"'{name}' README still holds the template description placeholder.",
                          "the GitHub description comes from the README's first paragraph.",
                          "replace the <FILL: ...> paragraph with one sentence, or pass a valid "
                          f"`--description` of {DESCRIPTION_MIN}-{DESCRIPTION_MAX} characters, "
                          "then archive again.")
    elif not original or len(original) < DESCRIPTION_MIN:
        return 1, _triad(f"'{name}' has no usable README description ({len(original)} characters).",
                          "the archived GitHub repository keeps a description, and it comes from "
                          "the README's first paragraph.",
                          f"write one sentence of {DESCRIPTION_MIN}-{DESCRIPTION_MAX} characters "
                          "under the README title, then archive again.")
    else:
        override = None
    new_desc = archive_github_description(original, override or description)
    # Dirty trees are refused: the archive commit must describe the archived tree.
    # Untracked files never ship in the banner commit, so they do not block;
    # only tracked modifications do.
    code, porcelain = run(["git", "status", "--porcelain", "--untracked-files=no"], src)
    if code != 0:
        return 1, _triad(f"could not inspect '{name}' for uncommitted changes.",
                         "git status failed, so the archive cannot prove the tree it retires.",
                         "fix the git error shown, then archive again; nothing was moved.")
    dirty = bool(porcelain.strip())
    if not dirty:
        _code_untracked, _porcelain_untracked = run(["git", "status", "--porcelain"], src)
        if _code_untracked == 0 and bool(_porcelain_untracked.strip()):
            notes_untracked = True
        else:
            notes_untracked = False
    else:
        notes_untracked = False
    if dirty and not allow_dirty:
        return 1, _triad(f"'{name}' has uncommitted changes; nothing was archived.",
                          "the archive commit must describe the tree being retired, not a working "
                          "copy that differs from it.",
                          "commit or discard the changes, or retry with `--allow-dirty` to move "
                          "them along (they stay uncommitted).")
    notes: List[str] = []
    if dirty and allow_dirty:
        notes.append("Note: uncommitted changes move along uncommitted.")
    if not dirty and notes_untracked:
        notes.append("Note: untracked files move along uncommitted.")
    repo_url = get_project_repo_url(src, runner=run)
    slug = repo_slug(src, name)
    if repo_url and "/" in repo_url:
        # Derive the slug from the push URL so forks/renames use one name for
        # both `git push` and `gh repo edit/archive`; fall back to the local
        # origin slug when the URL has no owner/repo shape.
        try:
            cleaned = repo_url.strip().rstrip("/").removesuffix(".git")
            if ":" in cleaned and "/" not in cleaned.rsplit(":", 1)[-1]:
                cleaned = cleaned.rsplit(":", 1)[-1]
            tail = cleaned.rsplit("/", 2)
            if len(tail) >= 2 and tail[-1] and tail[-2]:
                slug = f"{tail[-2]}/{tail[-1]}"
        except (AttributeError, ValueError):
            pass
    needs_github = bool(repo_url) and not offline
    if dirty and allow_dirty and needs_github:
        return 1, _triad(f"'{name}' has uncommitted changes; nothing was archived online.",
                         "git push only publishes commits, so an online archive would turn "
                         "the GitHub repository read-only while uncommitted work can never "
                         "be pushed afterwards.",
                         "commit or discard the changes, then archive again, or retry with "
                         "`--offline` to move them along locally; nothing was moved.")
    if offline:
        notes.append("Offline: the GitHub repository is left untouched; only the local folder moves.")
    elif not repo_url:
        notes.append("No 'origin' remote: only the local folder moves; no GitHub repository to archive.")

    # README banner first: the push below uploads it before the repo goes read-only.
    # A secret in the reason/description would ship in the banner, commit and
    # project record, so refuse before writing anything.
    # The pragma is neutralized first: it suppresses the scanner by design, so
    # honoring it here would let `--reason "ghp_xxx # aikit:allow-secret"`
    # smuggle a credential into the public banner and commit message.
    try:
        from scripts.check_secrets import scan_text as _scan_text
        _banner_text = f"{reason}\n{new_desc}".replace("aikit:allow-secret", "x")
        _banner_findings = _scan_text(f"{name}/archive-reason", _banner_text)
    except (ImportError, AttributeError, ValueError, TypeError, RuntimeError, OSError) as exc:
        return 1, _triad(f"could not scan the archive banner for '{name}': {exc}",
                          "the banner, commit message and project record would publish "
                          "the reason/description without a secret check.",
                          "fix the scanner error shown, then archive again; nothing was moved.")
    if _banner_findings:
        return 1, _triad(f"refusing to archive '{name}': the reason/description looks like a credential.",
                          "the archive banner, commit message and project record would publish it.",
                          "remove the credential-shaped text from --reason/--description, then archive again.")
    readme_changed = update_readme_for_archive(readme_path, reason, day)
    if not readme_changed and "> **Archived**" not in (readme_text or ""):
        try:
            current = readme_path.read_text(encoding="utf-8-sig", errors="replace")
        except OSError:
            current = ""
        if "> **Archived**" not in current:
            if needs_github:
                return 1, _triad(f"the archive banner for '{name}' could not be written.",
                                 "the remote must hold the archived README before the repository goes "
                                 "read-only, so an unwritten banner cannot be archived online.",
                                 "fix the README permissions, or retry with `--offline` to move locally "
                                 "only; nothing was moved.")
            notes.append("Note: the archive banner could not be written to README.md; "
                         "it moves along without the banner.")
    add_ok = False
    if readme_changed:
        add_code, add_out = run(["git", "add", "--", "README.md"], src)
        if add_code != 0:
            if offline or not needs_github:
                notes.append(f"Note: the archive banner could not be staged ({add_out.strip()[-200:]}); "
                             "it moves along uncommitted.")
            else:
                return 1, _triad(f"the archive banner for '{name}' could not be staged.\n{add_out.strip()[-800:]}",
                                 "the remote must hold the archived README before the repository goes "
                                 "read-only, so an unstaged banner cannot be archived online.",
                                 "fix the git error shown, or retry with `--offline` to move locally "
                                 "only; nothing was moved.")
            add_ok = False
        else:
            add_ok = True
        if add_ok:
            msg = f"docs({name}): mark as archived"
            code, out = run(["git", "commit", "-m", msg, "-m", reason], src)
            if code == 0:
                notes.append(f"Committed the archive banner ({msg}).")
            elif offline or not needs_github:
                notes.append(f"Note: the archive banner could not be committed ({out.strip()[-200:]}); "
                             "it moves along uncommitted.")
            else:
                return 1, _triad(f"the archive banner for '{name}' could not be committed.\n{out.strip()[-800:]}",
                                 "the remote must hold the archived README before the repository goes "
                                 "read-only, so an uncommitted banner cannot be archived online.",
                                 "fix the git error shown (identity, hooks, permissions), or retry with "
                                 "`--offline` to move locally only; nothing was moved.")

    if needs_github:
        if run(["gh", "auth", "status"], src)[0] != 0:
            return 1, _triad("the GitHub CLI is not installed or not logged in.",
                              "AIKit archives the repository with `gh`.",
                              "install GitHub CLI, run `gh auth login`, then archive again; "
                              "or pass `--offline` for a local-only move (nothing was moved).")
        rev_range = push_range(src, run)
        refusal = scan_refusal(src, rev_range, run)
        if refusal:
            return 1, refusal
        # Push the committed history (including the banner commit when present).
        # A dirty tree here implies --allow-dirty, and `git push` only publishes
        # commits, so uncommitted changes still move along uncommitted.
        code, out = run(["git", "push", "-u", "origin", "HEAD"], src)
        if code != 0:
            return 1, _triad(f"pushing the archive commit for '{name}' failed.\n{out[-800:]}",
                              "the remote refused the push; the repository must hold the "
                              "archived README before it goes read-only.",
                              "pull or fix the cause shown, then archive again; nothing was moved.")
        notes.append(f"Pushed the archived tree to {hide_url_credentials(repo_url or slug)}.")
        code, out = run(["gh", "repo", "edit", slug, "--description", new_desc], src)
        if code != 0:
            notes.append(f"Note: the GitHub description was not set ({out.strip()[-200:]}); run "
                         f"`gh repo edit {slug} --description \"{new_desc[:60]}...\"` by hand.")
        else:
            notes.append(f"Set the GitHub description to '{new_desc[:80]}'.")
        code, out = run(["gh", "repo", "archive", slug, "--yes"], src)
        if code != 0:
            lowered = out.lower()
            # "already archived" is the CLI sentence; JSON `{"archived": true}`
            # also means already archived. A bare `archived ... true` without a
            # colon/equals (e.g. "archived flag must be true") is a different
            # error and must not be swallowed. The word boundary keeps
            # `unarchived` from matching `archived`.
            already = "already archived" in lowered or bool(
                re.search(r'["\']?\barchived\b["\']?\s*[:=]\s*true', lowered)
            )
            if already:
                notes.append("The GitHub repository was already archived.")
            else:
                return 1, _triad(f"archiving the GitHub repository '{slug}' failed.\n{out[-800:]}",
                                  "GitHub refused the archive; the local folder was not moved, so "
                                  "the retry still sees the same tree.",
                                  "fix the cause shown (rights, network, name), then archive again.")
        else:
            notes.append(f"Archived the GitHub repository {slug} (read-only).")

    # Record after the move so a failed move leaves the source unmarked and
    # retryable; recording before the move would strand `archived=true` at the
    # old path and make the retry report "already archived" without moving.
    try:
        dst.parent.mkdir(parents=True, exist_ok=True)
        shutil.move(str(src), str(dst))
    except (OSError, shutil.Error) as exc:
        # Only clean a partial dst when src still exists (safe retry). When src
        # is gone the copy likely completed and deleting dst would destroy the
        # only copy, so leave both for operator inspection.
        try:
            if src.exists() and dst.exists():
                # dst did not exist before the move (validated above), so an
                # existing dst here is partial from this failed move.
                if dst.is_dir() and not dst.is_symlink():
                    shutil.rmtree(dst, ignore_errors=True)
                else:
                    dst.unlink(missing_ok=True)
        except (OSError, shutil.Error):
            pass
        return 1, _triad(f"moving '{name}' to {dst} failed: {exc}",
                         "the filesystem denied the move.",
                         "check the path permissions and free space, then archive again.")
    try:
        _record_archived_config(dst, reason, day, slug if needs_github else (repo_url or slug), new_desc)
    except (OSError, ValueError, KeyError, AttributeError, TypeError, shutil.Error,
            ProjectError) as exc:
        return 1, _triad(f"archived '{name}' to {dst} but could not record it in .aikit/project.json: {exc}",
                         "the project record is AIKit's memory of the archive.",
                         "restore the file from git inside the archived folder, then re-record the "
                         "archive fields (archived, archived_at, archive_reason).")
    _forget_or_move_attached(workspace, name, src, dst)
    # Dossier catalogue is a networked publish side-effect (gh api): an offline
    # Dossier sync is best-effort only and must never fail the archive:
    # the move and the .aikit record already succeeded above.
    if not offline:
        try:
            from scripts import dossier_sync as _dossier_sync
            try:
                _dossier_result = _dossier_sync.sync_published(dst, name)
            except Exception as _dossier_exc:
                notes.append(f"Note: dossier catalogue sync skipped ({_dossier_exc}).")
            else:
                if isinstance(_dossier_result, dict) and not _dossier_result.get("skipped"):
                    notes.append(f"Dossier catalogue updated for archived '{name}'.")
        except Exception as _import_exc:
            notes.append(f"Note: dossier catalogue sync unavailable ({_import_exc}).")
    lines = [f"[OK] Archived '{name}' to {dst} with reason '{reason}'."]
    lines.extend(notes)
    lines.append("Review and push the project's own repository if it still has local commits; "
                 "the archived folder keeps its git history.")
    return 0, "\n".join(lines)


def is_archived(project_path: Path) -> bool:
    """Whether ``.aikit/project.json`` records this project as archived."""
    try:
        from scripts.project_registry import ProjectError as _ProjectError
        from scripts.project_registry import load_config

        return bool(load_config(Path(project_path)).get("archived") is True)
    except (OSError, ValueError, KeyError, _ProjectError):
        return False
