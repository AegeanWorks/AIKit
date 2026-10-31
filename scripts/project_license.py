"""
Project license tiers (ADR-214).

A project `aikit new` creates is in the personal tier: free for personal use under the Aegean
License 1.1 (AL-1.1), with commercial use sold under the Aegean Commercial License 1.0 (ACL-1.0)
in COMMERCIAL.md. A project whose value outgrows free distribution moves to the restricted tier:
its LICENSE becomes the canonical All Rights Reserved notice (`licenses/RESTRICTED-NOTICE.md`)
naming the cutoff commit, COMMERCIAL.md (a public offer) is removed, and
`.aikit/project.json` records the cutoff. A license already granted cannot be revoked, so the
cutoff only looks forward: every version up to that commit stays under the license it carried.
"""

import re
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Callable, Optional

from scripts.disruption_recovery import atomic_write_json, file_lock
from scripts.marked_blocks import fenced, replace_block
from scripts.project_publish import run_command
from scripts.project_registry import (
    LICENSE_CHOICES,
    LICENSE_HEADING,
    LICENSES_DIR,
    ProjectError,
    _run_git,
    config_path,
    detect_license_kind,
    license_choice,
    license_header_match,
    load_config,
    reconcile_readme_tree,
    seed_assets_manifest,
    seed_commercial,
    seed_reuse,
    write_reuse_metadata,
)
from scripts.update_knowledge_base import write_generated_file

TIER_PERSONAL = "personal"
TIER_RESTRICTED = "restricted"
# An attached project keeps whatever license it came with; AIKit does not interpret it.
TIER_UNRECORDED = "unrecorded"
RESTRICTED_NOTICE_PATH = LICENSES_DIR / "RESTRICTED-NOTICE.md"
RESTRICTED_LICENSE_HEADER = "AEGEAN RESTRICTED SOFTWARE NOTICE"
RESTRICTED_TREE_LINE = "├── LICENSE                   <- All Rights Reserved (restricted tier)"
# A tree entry is `├──` or `└──` depending on its position, so keep whichever prefix the README
# already uses instead of matching one spelling only (a LICENSE listed last uses `└──`). The
# comment is optional: a bare `├── LICENSE` line is relabelled too.
_TREE_ENTRY = r"^([├└]──) {}(?: .*)?$"
_TREE_LICENSE = re.compile(_TREE_ENTRY.format("LICENSE"))
_TREE_COMMERCIAL = re.compile(_TREE_ENTRY.format(r"COMMERCIAL\.md"))
# Any plain License heading (`## License`, `## Licence`, `## 📄 License`), so a README written
# before AIKit is switched in place instead of gaining a second section; `## Commercial
# Licensing` and other titled sections are left alone.
_LICENSE_SECTION = re.compile(r"^## (?:[^\w\s]+\s+)?Licen[cs]e[ \t]*\n.*?(?=^## |\Z)", re.M | re.S)
LICENSE_BLOCK = "license"
RESTRICTED_LICENSE_SECTION = (
    f"{LICENSE_HEADING}\n\n"
    "All Rights Reserved. This project is in the Aegean restricted tier and is not licensed for "
    "use, copying or distribution; see [LICENSE](LICENSE) for the cutoff commit. Versions released "
    "before the cutoff stay under the license they were released with.\n"
)


@dataclass(frozen=True)
class LicenseState:
    tier: str
    since: Optional[str] = None
    since_commit: Optional[str] = None
    kind: Optional[str] = None
    version: Optional[str] = None


def render_restricted_license(name: str, since: str, since_commit: str) -> str:
    """The canonical All Rights Reserved notice, filled for a project restricted from its cutoff on."""
    try:
        template = RESTRICTED_NOTICE_PATH.read_text(encoding="utf-8")
    except OSError as exc:
        raise ProjectError(
            f"Cannot read {RESTRICTED_NOTICE_PATH}: {exc}",
            "the restricted tier writes the canonical Aegean notice, pinned in AIKit's licenses/.",
            "restore it from git (`git checkout -- licenses/RESTRICTED-NOTICE.md`), then retry.",
        ) from exc
    if not template.startswith(RESTRICTED_LICENSE_HEADER):
        raise ProjectError(
            f"{RESTRICTED_NOTICE_PATH} is not the Aegean restricted notice.",
            "the restricted tier writes the canonical Aegean notice, pinned in AIKit's licenses/.",
            "restore it from git (`git checkout -- licenses/RESTRICTED-NOTICE.md`), then retry.",
        )
    return template.format(project=name, since=since, commit=since_commit)


def license_state(project_root: Path) -> LicenseState:
    """The project's tier, personal-license kind and version: the restriction, else what LICENSE says."""
    recorded = load_config(project_root).get("license")
    if isinstance(recorded, dict) and recorded.get("tier") == TIER_RESTRICTED:
        return LicenseState(TIER_RESTRICTED, recorded.get("since"), recorded.get("since_commit"),
                            recorded.get("kind"), recorded.get("version"))
    try:
        first = (project_root / "LICENSE").read_text(encoding="utf-8").lstrip().split("\n", 1)[0]
    except OSError:
        return LicenseState(TIER_UNRECORDED)
    match = license_header_match(first)
    if not match:
        return LicenseState(TIER_UNRECORDED)
    kind, version = match
    return LicenseState(TIER_PERSONAL, kind=kind, version=version)


def suggest_license(project_root: Path) -> dict:
    """What an AI should choose for this project, with the current file and the evidence."""
    current = license_state(project_root)
    detected = detect_license_kind(project_root)
    # An empty project (or one whose markers are not in this checkout) still has its LICENSE as
    # evidence: never recommend downgrading a deliberate game or science choice to software.
    if detected["kind"] == "software" and current.kind in ("game", "science"):
        detected = {"kind": current.kind, "confidence": "medium",
                    "reasons": [f"current license: {LICENSE_CHOICES[current.kind]['key']}"],
                    "alternatives": ["software"]}
    detected["current"] = current.kind
    detected["current_version"] = current.version
    detected["latest_version"] = LICENSE_CHOICES[detected["kind"]]["version"]
    detected["recommended_key"] = LICENSE_CHOICES[detected["kind"]]["key"]
    if current.kind in LICENSE_CHOICES:
        base = LICENSE_CHOICES[current.kind]["key"].rsplit("-", 1)[0]
        version = current.version or LICENSE_CHOICES[current.kind]["version"]
        detected["current_key"] = f"{base}-{version}"
    else:
        detected["current_key"] = None
    detected["change_needed"] = current.tier == TIER_PERSONAL and current.kind != detected["kind"]
    detected["upgrade_available"] = (current.tier == TIER_PERSONAL
                                     and current.version != detected["latest_version"])
    detected["adoptable"] = (current.tier == TIER_UNRECORDED
                             and detected["kind"] != "software")
    return detected


def _with_license_section(text: str, section: str) -> str:
    """
    `text` (LF) naming `section`'s license. AIKit owns only the paragraph between the
    `aegean:license` markers, so a note the user adds to the section survives a switch (IDEA-398).
    A README without them has its first License section replaced once, now marked, and any later
    one removed.
    """
    heading, _, body = section.partition("\n\n")
    replaced = replace_block(text, LICENSE_BLOCK, body)
    if replaced is not None:
        return replaced
    section = f"{heading}\n\n{fenced(LICENSE_BLOCK, body)}\n"
    found = list(_LICENSE_SECTION.finditer(text))
    if not found:
        return text.rstrip("\n") + "\n\n" + section
    for match in reversed(found[1:]):
        text = text[:match.start()] + text[match.end():]
    first = found[0]
    tail = "\n" if first.end() < len(text) else ""
    return text[:first.start()] + section + tail + text[first.end():]


def _licensed_readme(text: str, newline: str, kind: str,
                     assets_manifest: bool = False) -> str:
    """`text` with its tree's LICENSE line and License section naming the chosen personal license."""
    choice = license_choice(kind)
    # The tree template ends in a newline for `new`; a rewritten line must not keep it.
    tree_line = choice["tree"][3:].rstrip("\n")

    def licensed(line: str) -> str:
        match = _TREE_LICENSE.match(line)
        return f"{match.group(1)}{tree_line}" if match else line

    lines = [licensed(line) for line in text.split(newline)]
    text = "\n".join(lines)
    if assets_manifest and "ASSETS.md" not in text:
        marker = re.search(r"(?m)^[├└]── LICENSE.*$", text)
        if marker:
            text = (text[:marker.end()] +
                    "\n├── ASSETS.md                 <- Asset/data manifest: what the license covers" +
                    text[marker.end():])
    return _with_license_section(text, choice["section"]).replace("\n", newline)


def apply_license_kind(project_root: Path, name: str, kind: str) -> LicenseState:
    """
    Switch a personal-tier project to software (AL-1.1), game (AGL-1.1) or science (ASL-1.1)
    (ADR-218). The canonical text, the README tree line and its License section change together;
    the change is left uncommitted for review. A restricted project is refused: its later
    versions are All Rights Reserved and cannot be relicensed by this command.
    """
    choice = license_choice(kind)
    current = license_state(project_root)
    if current.tier == TIER_RESTRICTED:
        raise ProjectError(
            f"'{name}' is in the restricted tier.",
            "a restricted project's later versions are All Rights Reserved; a personal license "
            "would revoke that decision without a new agreement.",
            "use a separate written agreement for a restricted project, or start a new project.",
            exit_code=2,
        )
    source = LICENSES_DIR / choice["source"]
    try:
        text = source.read_text(encoding="utf-8")
    except OSError as exc:
        raise ProjectError(
            f"Cannot read {source}: {exc}",
            f"the {choice['name']} text is pinned in AIKit's licenses/.",
            f"restore {source.name} from git, then retry.",
        ) from exc
    if not text.lstrip().startswith(choice["header"]):
        raise ProjectError(
            f"{source} is not the {choice['name']} text.",
            f"the {choice['name']} text is pinned in AIKit's licenses/.",
            f"restore {source.name} from git, then retry.",
        )
    # The README's License section links to COMMERCIAL.md; an attached project may not have one.
    # Seed the canonical terms before changing anything, so a failure leaves the project intact.
    if not (project_root / "COMMERCIAL.md").exists():
        seed_commercial(project_root)
    if kind in ("game", "science"):
        seed_assets_manifest(project_root, kind)
    previous = LICENSE_CHOICES.get(current.kind)
    old_key = previous["key"] if previous else None
    write_generated_file(project_root / "LICENSE", text)
    seed_reuse(project_root, kind)
    if old_key and old_key != choice["key"]:
        old_reuse = project_root / "LICENSES" / f"LicenseRef-{old_key}.txt"
        if old_reuse.is_file():
            old_reuse.unlink()
    readme = project_root / "README.md"
    if readme.is_file():
        with open(readme, encoding="utf-8", newline="") as handle:
            original = handle.read()
        newline = "\r\n" if "\r\n" in original else "\n"
        write_generated_file(readme, _licensed_readme(
            original, newline, kind,
            assets_manifest=(project_root / "ASSETS.md").exists()), newline="")
        reconcile_readme_tree(project_root)
    return LicenseState(TIER_PERSONAL, kind=kind, version=choice["version"])


def public_remote_refusal(project_root: Path, name: str,
                          runner: Optional[Callable] = None) -> Optional[ProjectError]:
    """
    The error that stops a push of a restricted project, or None. Only a remote GitHub reports as
    PRIVATE may receive one: a public, internal or unknown visibility is refused, because a
    restricted project must not be handed to the public (ADR-214).
    """
    if license_state(project_root).tier != TIER_RESTRICTED:
        return None
    code, output = (runner or run_command)(
        ["gh", "repo", "view", "--json", "visibility", "--jq", ".visibility"], project_root)
    visibility = output.strip().upper() if code == 0 else "UNKNOWN"
    if visibility == "PRIVATE":
        return None
    return ProjectError(
        f"'{name}' is in the restricted tier and its GitHub repository is {visibility.lower()}; "
        "the push is refused.",
        "a restricted project is All Rights Reserved and may be pushed only to a private repository.",
        "make the repository private (`gh repo edit --visibility private "
        "--accept-visibility-change-consequences`), or log in with `gh auth login` so AIKit can "
        "confirm it is private, then push again. A remote outside GitHub cannot be confirmed: "
        "check that it is private, then push with git yourself.",
        exit_code=2,
    )


def _restricted_readme(text: str, newline: str) -> str:
    """`text` with its tree's licensing lines and its License section switched to the restricted tier."""
    def licensed(line: str) -> str:
        match = _TREE_LICENSE.match(line)
        return (f"{match.group(1)}{RESTRICTED_TREE_LINE[3:]}" if match else line)

    lines = [licensed(line) for line in text.split(newline) if not _TREE_COMMERCIAL.match(line)]
    return _with_license_section("\n".join(lines), RESTRICTED_LICENSE_SECTION).replace("\n", newline)


def restrict_project(project_root: Path, name: str, today: Optional[str] = None,
                     runner: Optional[Callable] = None) -> LicenseState:
    """
    Move a project to the restricted tier at its current commit; returns the recorded state. A
    project already restricted keeps its first cutoff. Nothing is committed: the change is left in
    the working tree for review. A project without a commit has nothing to cut off, so it is refused
    before any file changes.
    """
    current = license_state(project_root)
    if current.tier == TIER_RESTRICTED:
        return current
    head = (runner or _run_git)(project_root, "rev-parse", "--verify", "HEAD")
    commit = (head.stdout or "").strip()
    if head.returncode != 0 or not commit:
        raise ProjectError(
            f"'{name}' has no commit to record as the cutoff.",
            "the restricted tier names the last commit released under the earlier license, so it "
            "is clear which versions keep that license.",
            "commit the project's current state, then run the command again.",
        )
    state = LicenseState(TIER_RESTRICTED, today or time.strftime("%Y-%m-%d"), commit,
                         current.kind, current.version)
    write_generated_file(project_root / "LICENSE",
                         render_restricted_license(name, state.since, state.since_commit))
    write_reuse_metadata(project_root, "LicenseRef-Aegean-Restricted")
    if current.kind in LICENSE_CHOICES:
        old_reuse = (project_root / "LICENSES" /
                     f"LicenseRef-{LICENSE_CHOICES[current.kind]['key']}.txt")
        if old_reuse.is_file():
            old_reuse.unlink()
    (project_root / "COMMERCIAL.md").unlink(missing_ok=True)
    readme = project_root / "README.md"
    if readme.is_file():
        with open(readme, encoding="utf-8", newline="") as handle:
            text = handle.read()
        newline = "\r\n" if "\r\n" in text else "\n"
        write_generated_file(readme, _restricted_readme(text, newline), newline="")
        reconcile_readme_tree(project_root)
    path = config_path(project_root)
    with file_lock(path):
        config = load_config(project_root)
        config["license"] = {"tier": state.tier, "since": state.since,
                             "since_commit": state.since_commit, "kind": state.kind,
                             "version": state.version}
        atomic_write_json(path, config)
    return state
