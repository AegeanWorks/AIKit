"""
Project registry: the projects AIKit builds (cockpit model, ADR-119).

AIKit is the workspace; each project it builds is its own folder and git repository, normally
`projects/<name>/`, or an existing folder attached by path. Everything AIKit records about a
project lives in that project's `.aikit/` directory, so AIKit's own gates, ledger and codebase map
never mix with project code, and a project never carries AIKit's tooling.

Projects under `projects/` are found by scanning for `.aikit/project.json`; only attached folders
outside it are listed in `projects/attached.json`. Both are ignored by AIKit's git. The stack and
test command are detected from the project's files on every call, never stored, so they cannot go
stale; `project.json` holds only an explicit `test_command` override.
"""

import json
import re
import shutil
import subprocess
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Callable, Dict, List, Optional, Tuple

from scripts.disruption_recovery import (
    LEDGER_SCHEMA_VERSION,
    PROJECT_MEMORY_DIRNAME,
    ROOT_DIR,
    atomic_write_json,
    file_lock,
)
from scripts.update_knowledge_base import check_readme, guideline_errors, write_generated_file

PROJECTS_DIRNAME = "projects"
ATTACHED_FILENAME = "attached.json"
CONFIG_FILENAME = "project.json"
# Every project AIKit seeds names where it came from; the badge links to AIKit's page (ADR-199).
AIKIT_URL = "https://github.com/AegeanWorks/AIKit"
# READMEs seeded before the repository moved still link here; a badge refresh migrates them (ADR-213).
LEGACY_AIKIT_URL = "https://github.com/Aegean-E/AIKit"
AIKIT_BADGE = f"[![Built with AIKit](https://img.shields.io/badge/built%20with-AIKit-6f42c1)]({AIKIT_URL})"
# A project AIKit is attached to, or copied into, was not built by it: it is integrated (ADR-202).
AIKIT_INTEGRATED_BADGE = f"[![AIKit Integrated](https://img.shields.io/badge/AIKit-integrated-6f42c1)]({AIKIT_URL})"
DESCRIPTION_MIN, DESCRIPTION_MAX = 10, 350
DESCRIPTION_FILL = (f"<FILL: one sentence on what this project does and for whom, "
                    f"{DESCRIPTION_MIN}-{DESCRIPTION_MAX} characters>")
# A title (a project name or README heading) is title-cased: every significant word starts with
# a capital, small joining words stay lower unless first or last, and known acronyms keep their
# spelling ("muse-ai" is "Muse AI", not "Muse Ai"). Descriptions keep the author's case.
_TITLE_SMALL = {"a", "an", "and", "as", "at", "but", "by", "for", "from", "in", "into", "of",
                "on", "or", "the", "to", "via", "vs", "with"}
_TITLE_ACRONYMS = {"ai": "AI", "aikit": "AIKit", "api": "API", "cli": "CLI", "cpu": "CPU",
                   "css": "CSS", "db": "DB", "drm": "DRM", "gpu": "GPU", "gui": "GUI",
                   "html": "HTML", "http": "HTTP", "json": "JSON", "llm": "LLM", "ml": "ML",
                   "os": "OS", "pdf": "PDF", "sdk": "SDK", "sql": "SQL", "ui": "UI", "ux": "UX",
                   "vr": "VR", "ar": "AR", "xr": "XR", "2d": "2D", "3d": "3D"}
# GitHub's topic rules: lowercase letters, digits and '-', at most 50 characters, 20 per repository.
TOPIC_PATTERN = re.compile(r"^[a-z0-9][a-z0-9-]{0,49}$")
MAX_TOPICS = 20
# The first line of the LICENSE `new` seeds, and the README section that describes it (ADR-214).
PERSONAL_LICENSE_HEADER = "# Aegean License 1.1 (AL-1.1)"
COMMERCIAL_HEADER = "# Aegean Commercial License (ACL-1.0)"
# The canonical license texts, pinned copies of aegean-licensing's licenses/ (ADR-214).
LICENSES_DIR = ROOT_DIR / "licenses"
LICENSE_HEADING = "## 📜 License"
PERSONAL_LICENSE_SECTION = (
    f"{LICENSE_HEADING}\n\n"
    "Free for personal use under the Aegean License 1.1 (AL-1.1); see [LICENSE](LICENSE). "
    "Any commercial use needs the Aegean Commercial License 1.0 (ACL-1.0); see [COMMERCIAL.md](COMMERCIAL.md).\n"
)
# One catalog for the three personal-use licenses AIKit can seed (ADR-218). `key` is the SPDX
# fragment, `header` the first line that identifies the file, `source` the pinned text in
# licenses/, and `tree`/`section` the README lines that name it. Commercial use of all three
# moves to ACL-1.0; the differences are the free-use domain each one grants.
LICENSE_CHOICES = {
    "software": {
        "key": "AL-1.1",
        "name": "Aegean License 1.1 (AL-1.1)",
        "header": PERSONAL_LICENSE_HEADER,
        "version": "1.1",
        "legacy_headers": {"# Aegean License 1.0 (AL-1.0)": "1.0"},
        "source": "AL-1.1.md",
        "summary": "AL-1.1, free personal use",
        "tree": "├── LICENSE                   <- Aegean License 1.1 (AL-1.1): free personal use\n",
        "section": PERSONAL_LICENSE_SECTION,
    },
    "game": {
        "key": "AGL-1.1",
        "name": "Aegean Game License 1.1 (AGL-1.1)",
        "header": "# Aegean Game License 1.1 (AGL-1.1)",
        "version": "1.1",
        "legacy_headers": {"# Aegean Game License 1.0 (AGL-1.0)": "1.0"},
        "source": "AGL-1.1.md",
        "summary": "AGL-1.1, DRM-free personal play",
        "tree": "├── LICENSE                   <- Aegean Game License 1.1 (AGL-1.1): DRM-free personal play\n",
        "section": (
            f"{LICENSE_HEADING}\n\n"
            "Free for personal play under the Aegean Game License 1.1 (AGL-1.1); see [LICENSE](LICENSE). "
            "It is DRM-free: Licensor ships no DRM and a distributor may not add it. Streaming, modding "
            "and free mods are allowed. Commercial use, paid mods and AI training need the Aegean "
            "Commercial License 1.0 (ACL-1.0); see [COMMERCIAL.md](COMMERCIAL.md).\n"
        ),
    },
    "science": {
        "key": "ASL-1.1",
        "name": "Aegean Science License 1.1 (ASL-1.1)",
        "header": "# Aegean Science License 1.1 (ASL-1.1)",
        "version": "1.1",
        "legacy_headers": {"# Aegean Science License 1.0 (ASL-1.0)": "1.0"},
        "source": "ASL-1.1.md",
        "summary": "ASL-1.1, non-commercial research",
        "tree": "├── LICENSE                   <- Aegean Science License 1.1 (ASL-1.1): free non-commercial research\n",
        "section": (
            f"{LICENSE_HEADING}\n\n"
            "Free for non-commercial research and teaching under the Aegean Science License 1.1 "
            "(ASL-1.1); see [LICENSE](LICENSE). It allows publication, reproducibility sharing, "
            "text/data mining and non-commercial ML training. Commercial or industry-sponsored use "
            "needs the Aegean Commercial License 1.0 (ACL-1.0); see [COMMERCIAL.md](COMMERCIAL.md).\n"
        ),
    },
}
DEFAULT_LICENSE_KIND = "software"
# License metadata is part of discovery: GitHub cannot detect the custom Aegean licenses, so every
# project carries explicit license topics. Restricted projects must not advertise a free tier.
LICENSE_TOPIC_SETS = {
    "software": ("source-available", "aegean-license", "commercial-license"),
    "game": ("source-available", "aegean-game-license", "drm-free", "commercial-license"),
    "science": ("source-available", "aegean-science-license", "research", "commercial-license"),
}
RESTRICTED_TOPICS = ("all-rights-reserved", "proprietary")
# Every project is shipped through AIKit, so the integration tag is mandatory metadata like the
# license tags; it is not an AI suggestion.
INTEGRATION_TOPICS = ("aikit", "aikit-integrated")
ALL_LICENSE_TOPICS = tuple(sorted({*sum((list(v) for v in LICENSE_TOPIC_SETS.values()), []),
                                   *RESTRICTED_TOPICS}))


def license_topics(kind: Optional[str], restricted: bool = False) -> List[str]:
    """The GitHub topics that name a project's license tier, kept out of automatic AI choice."""
    if restricted:
        return list(RESTRICTED_TOPICS)
    return list(LICENSE_TOPIC_SETS.get(kind or DEFAULT_LICENSE_KIND, LICENSE_TOPIC_SETS["software"]))


# Markers that show a project's domain. A strong marker is enough for high confidence; a weak
# one only suggests. The same analysis selects the license and the domain topic (ADR-218).
LICENSE_MARKERS = {
    "game": {
        "strong": ("project.godot", "*.uproject", "ProjectSettings/ProjectVersion.txt",
                   "*.unity", "*.tscn", "*.gd"),
        "weak": ("Assets", "Content", "game", "engine", "levels", "sprites"),
    },
    "science": {
        "strong": ("*.ipynb", "paper.tex", "CITATION.cff", "*.bib"),
        "weak": ("notebooks", "experiments", "research", "datasets", "data", "figures"),
    },
}
DECISIONS_FILENAME = "decisions.md"
# The project's decision register; entries follow the same format as AIKit's knowledge/decisions.md.
GUIDELINES_FILENAME = "guidelines.md"
# The project tier of PRINCIPLE-001 R4: rules for this project only, below every principle.
GUIDELINES_TEMPLATE = (
    "# Project Guidelines\n\n"
    "Rules for this project only, written by people or AI agents. They add to AIKit's principles and\n"
    "rank below them: a guideline never overrides a principle (PRINCIPLE-000 R6, PRINCIPLE-001 R4).\n"
    "Add one with `python aikit.py guideline <name> \"<rule>\" --source <user|ADR-NNN|person>`, or by\n"
    "hand as one line below in the form `- **G-NNN** (source): rule`; IDs are never reused.\n\n"
    "Persisted state carries a format version. A loader refuses a version it does not support,\n"
    "without modifying or quarantining that file; older versions migrate when a migration exists.\n\n"
    "## Rules\n"
)
DECISIONS_TEMPLATE = (
    "# Decisions\n\n"
    "Why this project is built the way it is, oldest first. One entry per decision that changes a\n"
    "contract, a dependency, a data format or the architecture; IDs are consecutive and never reused.\n\n"
    "<!-- Entry format:\n"
    "### ADR-NNN: <decision in one line>\n"
    "- **Date**: YYYY-MM-DD\n"
    "- **Status**: Accepted\n"
    "- **Context**: <what forced the decision>\n"
    "- **Decision**: <what was decided>\n"
    "- **Consequences**: <what follows, including what it costs>\n"
    "-->\n"
)

def title_case(text: str) -> str:
    """
    A display title from a project name: words capitalised, small joining words left lower unless
    first or last, and known acronyms preserved (`muse-ai-music` -> `Muse AI Music`). Only the
    author-facing title is changed; folder names and descriptions keep their spelling, while
    repository names use `repository_name` (ADR-218, ADR-228).
    """
    words = [word for word in re.split(r"[-_\s]+", text) if word]
    title = []
    for index, word in enumerate(words):
        lower = word.lower()
        if lower in _TITLE_ACRONYMS:
            word = _TITLE_ACRONYMS[lower]
        elif not (0 < index < len(words) - 1 and lower in _TITLE_SMALL):
            word = word[:1].upper() + word[1:]
        title.append(word)
    return " ".join(title) or text


def repository_name(name: str) -> str:
    """
    The GitHub repository name for a project: each hyphen- or underscore-delimited word takes a
    capital first letter, and known acronyms keep their spelling (`tally` -> `Tally`,
    `obezite-mekanizma-projesi` -> `Obezite-Mekanizma-Projesi`, `ui-sandbox` -> `UI-Sandbox`).
    The portable folder and registry key stay lowercase (ADR-228).
    """
    def capitalise(match: "re.Match[str]") -> str:
        word = match.group(0)
        return _TITLE_ACRONYMS.get(word.lower(), word[:1].upper() + word[1:])
    return re.sub(r"[A-Za-z0-9]+", capitalise, name)


def license_choice(kind: str) -> dict:
    """The catalog entry for `kind`, or a ProjectError naming the three choices."""
    choice = LICENSE_CHOICES.get(kind)
    if choice is None:
        raise ProjectError(
            f"Unknown license kind '{kind}'.",
            "a project carries one personal-use license: software, game or science.",
            f"pick one of {', '.join(sorted(LICENSE_CHOICES))}.",
            exit_code=2,
        )
    return choice


def detect_license_kind(project_root: Path) -> dict:
    """
    The domain an AI should pick a license for, from the project's own markers. Strong markers
    (Godot/Unity/Unreal, notebooks, a paper, CITATION.cff) decide; weak directory names only add
    evidence. Returns `{kind, confidence, reasons, alternatives}`; software is the fallback.
    """
    scores = {kind: 0 for kind in ("game", "science")}
    reasons: Dict[str, List[str]] = {kind: [] for kind in scores}
    for kind, groups in LICENSE_MARKERS.items():
        for pattern in groups["strong"]:
            hit = next(iter(project_root.glob(pattern)), None)
            if hit is not None:
                scores[kind] += 3
                reasons[kind].append(f"strong marker: {hit.name}")
        for name in groups["weak"]:
            if (project_root / name).exists():
                scores[kind] += 1
                reasons[kind].append(f"weak marker: {name}/")
    ranking = sorted(scores.items(), key=lambda item: item[1], reverse=True)
    kind, top = ranking[0]
    if top == 0 or top == ranking[1][1]:
        return {"kind": DEFAULT_LICENSE_KIND, "confidence": "low", "reasons": [],
                "alternatives": [k for k, score in ranking if score]}
    strong = any(reason.startswith("strong") for reason in reasons[kind])
    if not strong and top < 2:
        # One weak directory name ("data/", "game/") is not evidence: it is common in software
        # projects too. A recommendation needs one strong marker, or at least two agreeing weak
        # ones (ADR-218).
        return {"kind": DEFAULT_LICENSE_KIND, "confidence": "low", "reasons": [],
                "alternatives": [k for k, score in ranking if score]}
    confidence = "high" if strong or top >= 3 else "medium"
    alternatives = [other for other, score in ranking
                    if score and other != kind and score >= top - 1]
    return {"kind": kind, "confidence": confidence, "reasons": reasons[kind],
            "alternatives": alternatives}


def render_project_readme(name: str, test_command: Optional[str] = None,
                          description: Optional[str] = None, licensed: bool = False,
                          integrated: bool = False,
                          license_kind: str = DEFAULT_LICENSE_KIND,
                          license_version: Optional[str] = None,
                          assets_manifest: bool = False, reuse: bool = False) -> str:
    """
    A README whose structure passes PRINCIPLE-005's audit, with a `<FILL:` prerequisite marker: the
    gate stays red until the agent states the project's own runtime facts (ADR-138). The tree lists
    every tracked top-level entry; `.aikit/` is listed without children, so a new memory file never
    makes the tree incomplete. A badge under the title links to AIKit, and the paragraph after it
    is the description `publish` uploads; `licensed` lists the LICENSE and COMMERCIAL.md `new`
    copies (ADR-199, ADR-214), the heading is title-cased, and `license_kind` selects the personal
    license (ADR-218); `integrated` marks a project AIKit was attached to rather than one it built
    (ADR-202).
    """
    choice = license_choice(license_kind)
    version = license_version or choice["version"]
    def versioned(text: str) -> str:
        return text.replace(choice["version"], version)

    license_line = (f"{versioned(choice['tree'])}"
                    "├── COMMERCIAL.md             <- Commercial licensing terms\n") if licensed else ""
    assets_line = ("├── ASSETS.md                 <- Asset/data manifest: what the license covers\n"
                   if licensed and assets_manifest else "")
    reuse_line = ("├── LICENSES/                 <- REUSE license texts\n"
                  "├── REUSE.toml                <- Machine-readable SPDX metadata\n"
                  if licensed and reuse else "")
    license_section = f"\n{versioned(choice['section'])}" if licensed else ""
    return (
        f"# {title_case(name)}\n\n"
        f"{AIKIT_INTEGRATED_BADGE if integrated else AIKIT_BADGE}\n\n"
        f"{description or DESCRIPTION_FILL}\n\n"
        "## ⚡ 30-Second Cold-Start Quick Reference\n\n"
        "- **Runtime Prerequisites**: <FILL: each runtime this project needs and its minimum version>\n"
        "- **Canonical Regression Shield Gate**:\n"
        "  ```bash\n"
        f"  {test_command or '<FILL: the command that runs the whole test suite from this project root>'}\n"
        "  ```\n\n"
        "### 🛠️ AIKit Commands (run from the AIKit folder)\n"
        "| Role | Command |\n"
        "|---|---|\n"
        f"| Status, task and gates | `python aikit.py status {name}` |\n"
        f"| Phase 4: every gate | `python aikit.py check {name}` |\n"
        f"| Repair memory and map, then check | `python aikit.py fix {name}` |\n"
        f"| Resume an interrupted task | `python aikit.py resume {name}` |\n\n"
        "## 📦 What's Inside\n\n"
        "```text\n"
        f"{name}/\n"
        "├── .gitignore                <- transient AIKit state excluded\n"
        f"{license_line}"
        f"{assets_line}"
        f"{reuse_line}"
        "├── README.md\n"
        "└── .aikit/                   <- this project's memory: record, ledger, decisions\n"
        "```\n"
        f"{license_section}"
    )


def license_header_match(first_line: str) -> Optional[Tuple[str, str]]:
    """The `(kind, version)` a LICENSE first line names, including an archived legacy header."""
    stripped = first_line.lstrip("\ufeff").strip()
    for kind, choice in LICENSE_CHOICES.items():
        if stripped == choice["header"]:
            return kind, choice["version"]
        for legacy_header, legacy_version in choice.get("legacy_headers", {}).items():
            if stripped == legacy_header:
                return kind, legacy_version
    return None


def seed_readme(project_root: Path, name: str, test_command: Optional[str] = None,
                description: Optional[str] = None, licensed: bool = False,
                integrated: bool = False, license_kind: Optional[str] = None) -> bool:
    """
    Write the template README when the project has none; returns whether it did. `new` and `fix`
    call it, `attach` never does: attaching leaves an existing folder's files alone. Only `new`
    passes `licensed`, since only it writes the LICENSE; `fix` passes `integrated` for an attached
    one. Without an explicit `license_kind`, the project's LICENSE header decides, else the
    markers do (ADR-218).
    """
    readme = project_root / "README.md"
    if readme.exists():
        return False
    license_version = None
    if license_kind is None:
        try:
            first = (project_root / "LICENSE").read_text(encoding="utf-8").lstrip().split("\n", 1)[0]
        except OSError:
            first = ""
        match = license_header_match(first)
        if match:
            license_kind, license_version = match
        else:
            license_kind = detect_license_kind(project_root)["kind"]
    write_generated_file(readme, render_project_readme(
        name, test_command, description, licensed, integrated, license_kind, license_version,
        assets_manifest=(project_root / ASSETS_MANIFEST_NAME).exists(),
        reuse=(project_root / REUSE_FILE).exists()))
    return True


def migrate_aikit_links(project_root: Path) -> bool:
    """
    Rewrite the pre-move AIKit URL in the README to the current one; returns whether it did. Run
    for every project AIKit refreshes, built or attached, so a repository that moved with the
    organization does not keep a dead link (ADR-213). The file's own line endings are kept.
    """
    readme = project_root / "README.md"
    try:
        with open(readme, encoding="utf-8", newline="") as handle:
            text = handle.read()
    except FileNotFoundError:
        return False
    if LEGACY_AIKIT_URL not in text:
        return False
    write_generated_file(readme, text.replace(LEGACY_AIKIT_URL, AIKIT_URL), newline="")
    return True


def add_aikit_badge(project_root: Path) -> bool:
    """
    Put the AIKit Integrated badge under the README's title, or at its top without one; returns
    whether it changed the README. A README that already links to AIKit, or no README, is left
    alone. A README that still links to the pre-move repository has that URL rewritten first (even
    when the current URL also appears), so a refresh never adds a second badge beside a stale one
    and never leaves a mixed pair behind. The file's own line endings are kept, so the only change
    in its diff is the badge (ADR-202, ADR-213).
    """
    if migrate_aikit_links(project_root):
        return True
    readme = project_root / "README.md"
    try:
        with open(readme, encoding="utf-8", newline="") as handle:
            text = handle.read()
    except FileNotFoundError:
        return False
    if AIKIT_URL in text:
        return False
    newline = "\r\n" if "\r\n" in text else "\n"
    lines = text.split(newline)
    title = next((i for i, line in enumerate(lines) if line.startswith("# ")), None)
    if title is None:
        lines[0:0] = [AIKIT_INTEGRATED_BADGE, ""]
    elif title + 1 < len(lines) and lines[title + 1] == "":
        lines[title + 2:title + 2] = [AIKIT_INTEGRATED_BADGE, ""]
    else:
        lines[title + 1:title + 1] = ["", AIKIT_INTEGRATED_BADGE, ""]
    write_generated_file(readme, newline.join(lines), newline="")
    return True


def validate_description(description: Optional[str]) -> Optional[str]:
    """The description stripped, or None; one line of 10-350 characters (GitHub's limit is 350)."""
    if description is None:
        return None
    text = description.strip()
    if "\n" in text or "\r" in text or not DESCRIPTION_MIN <= len(text) <= DESCRIPTION_MAX:
        raise ProjectError(
            f"Invalid description ({len(text)} characters).",
            f"it becomes the README's first paragraph and the GitHub description, which holds one "
            f"line of at most {DESCRIPTION_MAX} characters; under {DESCRIPTION_MIN} says nothing.",
            f"write one line of {DESCRIPTION_MIN}-{DESCRIPTION_MAX} characters on what the project "
            "does and for whom.",
            exit_code=2,
        )
    return text


def normalize_topics(topics: Optional[List[str]]) -> List[str]:
    """`aikit` then each topic lowercased, without repeats; refuses what GitHub would refuse."""
    result = ["aikit"]
    for raw in topics or []:
        topic = raw.strip().lower()
        if not TOPIC_PATTERN.match(topic):
            raise ProjectError(
                f"Invalid topic '{raw}'.",
                "GitHub topics are lowercase letters, digits and '-', start with a letter or digit, "
                "and hold at most 50 characters.",
                "pass each topic as one word, e.g. `--topic web --topic flask`.",
                exit_code=2,
            )
        if topic not in result:
            result.append(topic)
    if len(result) > MAX_TOPICS:
        raise ProjectError(
            f"{len(result)} topics, counting 'aikit'.",
            f"a GitHub repository holds at most {MAX_TOPICS} topics.",
            f"keep at most {MAX_TOPICS - 1} --topic values.",
            exit_code=2,
        )
    return result


ASSETS_MANIFEST_NAME = "ASSETS.md"
REUSE_FILE = "REUSE.toml"
REUSE_LICENSES_DIR = "LICENSES"
GAME_ASSETS_MANIFEST = """# Asset Manifest

Assets listed here are offered under the Aegean Game License 1.1 (AGL-1.1) as part of the game.
Assets not listed remain proprietary: they may be used only to play the game and may not be
extracted, redistributed or included in a mod without a grant.

| Path or pattern | Type | Rights holder | License | Notes |
|---|---|---|---|---|
| `assets/` | art, audio, level data | AegeanWorks | AGL-1.1 | Replace with the real inventory |
"""
SCIENCE_ASSETS_MANIFEST = """# Data and Asset Manifest

Project Data listed here is offered under the Aegean Science License 1.1 (ASL-1.1) for
non-commercial research. Third-party data and model weights keep their own licenses. Personal data
must have a lawful basis and a dataset-specific notice.

| Path or pattern | Type | Rights holder | License | Personal data | Notes |
|---|---|---|---|---|---|
| `data/` | dataset | AegeanWorks | ASL-1.1 | no | Replace with the real inventory |
"""


def seed_assets_manifest(project_root: Path, kind: str) -> bool:
    """
    Write the asset/data manifest `new --kind game|science` needs, so the license boundary has a
    concrete inventory from the first commit (ADR-223). A software project gets no manifest, and
    an existing file is never overwritten.
    """
    if kind not in ("game", "science"):
        return False
    path = project_root / ASSETS_MANIFEST_NAME
    if path.exists():
        return False
    text = GAME_ASSETS_MANIFEST if kind == "game" else SCIENCE_ASSETS_MANIFEST
    write_generated_file(path, text)
    return True


def _reuse_licenses_dir(project_root: Path) -> Path:
    """
    The directory that holds the REUSE license texts.

    Prefer an exact `LICENSES/`; then reuse an existing `licenses/` directory in the case the
    checkout already has one. On Windows the two names resolve to the same directory, so
    constructing `LICENSES/` would silently write into the lowercase tree and leave a path that
    a POSIX checkout cannot resolve.
    """
    try:
        children = [path for path in project_root.iterdir() if path.is_dir()]
    except OSError:
        return project_root / REUSE_LICENSES_DIR
    for path in children:
        if path.name == REUSE_LICENSES_DIR:
            return path
    for path in children:
        if path.name == "licenses":
            return path
    for path in children:
        if path.name.lower() == REUSE_LICENSES_DIR.lower():
            return path
    return project_root / REUSE_LICENSES_DIR


def _reuse_keeps_project_annotations(path: Path, identifier: str) -> bool:
    """Whether `REUSE.toml`'s blanket annotation already names `identifier`."""
    try:
        text = path.read_text(encoding="utf-8")
    except OSError:
        return False
    blocks = text.split("[[annotations]]")[1:]
    if len(blocks) < 2:
        return False
    needle = f'SPDX-License-Identifier = "{identifier}"'
    return any(needle in block and ('"**"' in block or "'**'" in block) for block in blocks)


def write_reuse_metadata(project_root: Path, identifier: str,
                         copyright_notice: str = "2026 AegeanWorks") -> bool:
    """
    Write `LICENSES/<identifier>.txt` (or the project's existing `licenses/` directory) and a
    `REUSE.toml` annotation for `identifier`. The caller passes a complete SPDX expression such as
    `LicenseRef-AL-1.1` (ADR-226).

    A refresh with the identifier already present keeps a project's extra annotations, such as an
    asset-specific `LicenseRef`; a different identifier rewrites the blanket metadata.
    """
    try:
        license_text = (project_root / "LICENSE").read_text(encoding="utf-8")
    except OSError:
        return False
    licenses_dir = _reuse_licenses_dir(project_root)
    write_generated_file(licenses_dir / f"{identifier}.txt", license_text)
    metadata = (
        "version = 1\n\n"
        "[[annotations]]\n"
        'path = ["**"]\n'
        'precedence = "aggregate"\n'
        f'SPDX-FileCopyrightText = "{copyright_notice}"\n'
        f'SPDX-License-Identifier = "{identifier}"\n'
    )
    if not _reuse_keeps_project_annotations(project_root / REUSE_FILE, identifier):
        write_generated_file(project_root / REUSE_FILE, metadata)
    return True


def seed_reuse(project_root: Path, kind: str, version: Optional[str] = None) -> bool:
    """
    Write the machine-readable REUSE metadata for a project: a `LICENSES/LicenseRef-<key>.txt`
    copy and a `REUSE.toml` annotation naming the current license expression (ADR-226). A project
    that prefers per-file SPDX headers can keep them; this manifest is the baseline. `version`
    keeps a legacy 1.0 project labelled 1.0 instead of the current 1.1.
    """
    choice = license_choice(kind)
    base = choice["key"].rsplit("-", 1)[0]
    return write_reuse_metadata(project_root, f"LicenseRef-{base}-{version or choice['version']}")


def seed_license(project_root: Path, kind: str = DEFAULT_LICENSE_KIND) -> None:
    """Copy the chosen personal Aegean license into a new project (ADR-199, ADR-214, ADR-218)."""
    choice = license_choice(kind)
    source = LICENSES_DIR / choice["source"]
    try:
        text = source.read_text(encoding="utf-8")
    except OSError as exc:
        raise ProjectError(
            f"Cannot read {source}: {exc}",
            f"a new project starts with the {choice['name']} text AIKit ships.",
            f"restore {source.name} in the AIKit licenses/ folder from git, then retry.",
        ) from exc
    if not text.lstrip().startswith(choice["header"]):
        raise ProjectError(
            f"{source} is not the {choice['name']} text.",
            f"a new project starts with the {choice['name']} text AIKit ships.",
            f"restore {source.name} in the AIKit licenses/ folder from git, then retry.",
        )
    write_generated_file(project_root / "LICENSE", text)


def seed_commercial(project_root: Path) -> None:
    """Copy AIKit's canonical COMMERCIAL.md into a new project (ADR-212, ADR-214)."""
    source = ROOT_DIR / "COMMERCIAL.md"
    try:
        text = source.read_text(encoding="utf-8")
    except OSError as exc:
        raise ProjectError(
            f"Cannot read {source}: {exc}",
            "a new project starts with the Aegean commercial terms AIKit ships.",
            "restore COMMERCIAL.md in the AIKit folder from git (`git checkout -- COMMERCIAL.md`), then retry.",
        ) from exc
    if not text.lstrip().startswith(COMMERCIAL_HEADER):
        raise ProjectError(
            f"{source} is not the Aegean commercial licensing text.",
            "a new project starts with the Aegean commercial terms AIKit ships.",
            "restore COMMERCIAL.md in the AIKit folder from git (`git checkout -- COMMERCIAL.md`), then retry.",
        )
    write_generated_file(project_root / "COMMERCIAL.md", text)


def _tree_entry_name(line: str) -> Optional[str]:
    """The exact top-level name a README tree line lists, or None for a nested or prose line."""
    match = re.match(r"^[├└]──\s+(.+?)(?:\s{2,}<-.*)?$", line)
    if match is None:
        return None
    return match.group(1).rstrip().rstrip("/")


def reconcile_readme_tree(project_root: Path, runner: Optional[Callable] = None) -> List[str]:
    """
    Auto-reconcile top-level tracked files omitted from the README tree block (PRINCIPLE-005 R5).
    Returns a list of descriptions for files added to the tree.
    """
    readme_path = project_root / "README.md"
    if not readme_path.is_file():
        return []
    if runner is None and not (project_root / ".git").exists() and not (project_root / ".git").is_file():
        return []
    findings = check_readme(project_root)
    omitted: List[str] = []
    for f in findings:
        m = re.search(r"README\.md tree omits tracked '([^']+)' \(R5\)", f)
        if m:
            omitted.append(m.group(1))
    if not omitted:
        return []

    top_omitted = [p for p in omitted if "/" not in p and (project_root / p).exists()]
    if not top_omitted:
        return []

    text = readme_path.read_text(encoding="utf-8")
    heading = re.search(r"^#+ .*What's Inside", text, re.M)
    if not heading:
        return []
    fence = text.find("```text\n", heading.end())
    if fence < 0:
        return []
    end_fence = text.find("```", fence + len("```text\n"))
    if end_fence < 0:
        return []

    block = text[fence + len("```text\n"):end_fence]
    lines = block.splitlines()
    if len(lines) < 2:
        return []

    insert_idx = 1
    for idx, line in enumerate(lines):
        if line.startswith("├── .gitignore") or line.startswith("├── README.md"):
            insert_idx = idx + 1

    reconciled = []
    new_lines = list(lines[:insert_idx])
    for item in top_omitted:
        if any(_tree_entry_name(line) == item for line in lines):
            continue
        suffix = "/" if (project_root / item).is_dir() else ""
        new_lines.append(f"├── {item}{suffix}")
        reconciled.append(item)

    if not reconciled:
        return []

    new_lines.extend(lines[insert_idx:])
    new_block = "\n".join(new_lines) + "\n"
    new_text = text[:fence + len("```text\n")] + new_block + text[end_fence:]
    write_generated_file(readme_path, new_text)
    return [f"added '{item}' to README.md tree" for item in reconciled]


SCHEMA_VERSION = 1
NAME_PATTERN = re.compile(r"^[a-z0-9][a-z0-9_-]{0,63}$")
# Names Windows reserves for devices: a folder cannot carry one, so it is no portable segment (ADR-196).
WINDOWS_DEVICE_NAMES = frozenset({"con", "prn", "aux", "nul",
                                  *(f"{port}{n}" for port in ("com", "lpt") for n in range(10))})
GIT_TIMEOUT_SECONDS = 30

# Transient files AIKit's atomic writes and locks leave next to project state (PRINCIPLE-013).
PROJECT_GITIGNORE_LINES = (
    ".aikit/*.lock",
    ".aikit/*.bak",
    ".aikit/*.tmp_*",
    ".aikit/*.corrupt_*",
    "__pycache__/",
    "*.py[cod]",
    "node_modules/",
)


class ProjectError(Exception):
    """A request AIKit cannot carry out, with its reason and remedy (PRINCIPLE-011 R6)."""

    def __init__(self, message: str, why: str, fix: str, exit_code: int = 1):
        super().__init__(message)
        self.why = why
        self.fix = fix
        self.exit_code = exit_code


@dataclass(frozen=True)
class Stack:
    """A toolchain detected in a project folder and the command that runs its tests."""

    name: str
    test_command: Optional[str]


@dataclass(frozen=True)
class Project:
    """A registered project as `aikit list` reports it."""

    name: str
    path: Path
    attached: bool
    stacks: Tuple[Stack, ...]
    test_command: Optional[str]
    present: bool


def _python_test(root: Path) -> str:
    pyproject = root / "pyproject.toml"
    uses_pytest = ((root / "pytest.ini").exists() or (root / "conftest.py").exists()
                   or (pyproject.exists()
                       and "pytest" in pyproject.read_text(encoding="utf-8", errors="replace")))
    return "python -m pytest" if uses_pytest else "python -m unittest discover"


def node_scripts(root: Path) -> Dict[str, str]:
    """The `scripts` map of the project's `package.json`; empty when absent or unreadable."""
    try:
        manifest = json.loads((root / "package.json").read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return {}
    scripts = manifest.get("scripts") if isinstance(manifest, dict) else None
    if not isinstance(scripts, dict):
        return {}
    return {str(k): v for k, v in scripts.items() if isinstance(v, str)}


def node_runner(root: Path) -> str:
    """The package manager the project's lockfile names: pnpm, yarn, or npm by default."""
    if (root / "pnpm-lock.yaml").exists():
        return "pnpm"
    return "yarn" if (root / "yarn.lock").exists() else "npm"


def _node_test(root: Path) -> Optional[str]:
    test = node_scripts(root).get("test")
    # `npm init` writes a placeholder test script that only fails; it is not a test command.
    if test is None or "no test specified" in test:
        return None
    return f"{node_runner(root)} test"


def _gradle_test(root: Path) -> str:
    return "./gradlew test" if (root / "gradlew").exists() else "gradle test"


def _fixed(command: str) -> Callable[[Path], str]:
    return lambda root: command


# (stack, marker globs, test-command resolver), in report order. Data, not branches: a new stack
# is one row (PRINCIPLE-009).
DETECTORS: Tuple[Tuple[str, Tuple[str, ...], Callable[[Path], Optional[str]]], ...] = (
    ("python", ("pyproject.toml", "setup.py", "setup.cfg", "requirements.txt"), _python_test),
    ("node", ("package.json",), _node_test),
    ("rust", ("Cargo.toml",), _fixed("cargo test")),
    ("go", ("go.mod",), _fixed("go test ./...")),
    ("java-maven", ("pom.xml",), _fixed("mvn -q test")),
    ("java-gradle", ("build.gradle", "build.gradle.kts"), _gradle_test),
    ("dotnet", ("*.sln", "*.csproj", "*.fsproj"), _fixed("dotnet test")),
)


def detect_stacks(root: Path) -> Tuple[Stack, ...]:
    """Every stack whose marker file sits in the project's top folder (polyglot repos list several)."""
    found = []
    for name, markers, resolve in DETECTORS:
        if any(next(root.glob(marker), None) is not None for marker in markers):
            found.append(Stack(name, resolve(root)))
    return tuple(found)


def validate_name(name: str) -> None:
    """Reject names that are not one portable folder name."""
    if not NAME_PATTERN.match(name):
        raise ProjectError(
            f"Invalid project name '{name}'.",
            "a project name becomes a folder and a registry key, so it must be one portable path "
            "segment.",
            "use 1-64 lowercase letters, digits, '-' or '_', starting with a letter or digit, "
            "e.g. 'my-app'.",
            exit_code=2,
        )
    if name in WINDOWS_DEVICE_NAMES:
        raise ProjectError(
            f"Invalid project name '{name}'.",
            "it is a Windows device name: no folder can be called that on Windows, so the project "
            "could not be created there, nor its repository cloned.",
            f"pick another name, e.g. '{name}-app'.",
            exit_code=2,
        )


def projects_dir(workspace: Path = ROOT_DIR) -> Path:
    return workspace / PROJECTS_DIRNAME


def config_path(project_root: Path) -> Path:
    return project_root / PROJECT_MEMORY_DIRNAME / CONFIG_FILENAME


def load_config(project_root: Path) -> Dict[str, object]:
    """A project's `.aikit/project.json`; a missing, unreadable or newer file is an error."""
    path = config_path(project_root)
    try:
        config = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError) as exc:
        raise ProjectError(
            f"Cannot read {path}: {exc}",
            "the file is AIKit's record of this project; without it the project is not registered.",
            f"restore it from the project's git history or `{path.name}.bak`, or attach the folder "
            "again with `python aikit.py attach <path>`.",
        ) from exc
    if not isinstance(config, dict) or config.get("schema") != SCHEMA_VERSION:
        raise ProjectError(
            f"{path} has an unsupported schema.",
            f"this AIKit reads project schema {SCHEMA_VERSION} only.",
            "update AIKit, or restore the file from the project's git history.",
        )
    return config


def is_game_project(config: Dict[str, object]) -> bool:
    """Whether the project's own metadata classifies it as a game."""
    topics = {str(topic).lower() for topic in config.get("topics", []) or []}
    license_topics = {str(topic).lower() for topic in config.get("license_topics", []) or []}
    return (str(config.get("ui_kind") or "") == "game" or "game" in topics
            or "aegean-game-license" in license_topics)


def mechanics_errors(project_root: Path, config: Dict[str, object]) -> List[str]:
    """Validate an optional mechanics contract: a headless core and the command that tests it.

    A project opts in with `"mechanics_required": true`; a declared contract is validated even
    when the flag is false, so a half-written contract cannot look testable to an agent.
    """
    mechanics = config.get("mechanics")
    required = config.get("mechanics_required") is True
    if mechanics is None:
        return ["mechanics_required is true but .aikit/project.json has no mechanics contract"] \
            if required else []
    if not isinstance(mechanics, dict):
        return ["the mechanics contract is not a mapping"]
    errors: List[str] = []
    core = mechanics.get("core")
    if not isinstance(core, list) or not core:
        errors.append("the mechanics contract has no core path list")
    else:
        missing = [str(path) for path in core if not (Path(project_root) / str(path)).exists()]
        if missing:
            errors.append(f"mechanics core path(s) do not exist: {', '.join(missing)}")
    test = mechanics.get("test")
    if not isinstance(test, str) or not test.strip():
        errors.append("the mechanics contract has no test command")
    return errors



def _ensure_gitignore(project_root: Path) -> None:
    """Append the transient-state patterns the project's `.gitignore` does not yet list."""
    path = project_root / ".gitignore"
    text = path.read_text(encoding="utf-8") if path.exists() else ""
    missing = [line for line in PROJECT_GITIGNORE_LINES if line not in text.splitlines()]
    if not missing:
        return
    prefix = "" if not text or text.endswith("\n") else "\n"
    block = prefix + "# AIKit transient state\n" + "\n".join(missing) + "\n"
    with open(path, "a", encoding="utf-8") as handle:
        handle.write(block)


def write_memory(project_root: Path, name: str, test_command: Optional[str] = None,
                 topics: Optional[List[str]] = None) -> bool:
    """
    Create the project's `.aikit/project.json`, `.aikit/decisions.md` and `.aikit/task_ledger.json`
    unless they exist. Returns whether `project.json` was created: existing memory is never
    overwritten.
    """
    path = config_path(project_root)
    _ensure_gitignore(project_root)
    guidelines = project_root / PROJECT_MEMORY_DIRNAME / GUIDELINES_FILENAME
    if not guidelines.exists():
        write_generated_file(guidelines, GUIDELINES_TEMPLATE)
    decisions = project_root / PROJECT_MEMORY_DIRNAME / DECISIONS_FILENAME
    if not decisions.exists():
        decisions.parent.mkdir(parents=True, exist_ok=True)
        decisions.write_text(DECISIONS_TEMPLATE, encoding="utf-8")
    ledger_path = project_root / PROJECT_MEMORY_DIRNAME / "task_ledger.json"
    if not ledger_path.exists():
        ledger_path.parent.mkdir(parents=True, exist_ok=True)
        atomic_write_json(ledger_path, {"version": LEDGER_SCHEMA_VERSION, "active_task": None,
                                        "checkpoints": []})
    if path.exists():
        return False
    atomic_write_json(path, {
        "schema": SCHEMA_VERSION,
        "name": name,
        "test_command": test_command,
        # The topics `publish` sets on GitHub (ADR-200). The description is the README's first
        # paragraph only: a second copy here went stale once the README was edited (ADR-202).
        "topics": topics if topics is not None else ["aikit"],
        # Gate name -> command, or null to disable a detected gate (project_gates, ADR-122).
        "gates": {},
        # Opt-in: strict delivery and publish require .aikit/ui.json (ADR-166).
        "ui_required": False,
        # Opt-in: a game/project declares a headless mechanics core and its test command.
        "mechanics_required": False,
        "created": time.strftime("%Y-%m-%d"),
    })
    return True


def _attached_path(workspace: Path) -> Path:
    return projects_dir(workspace) / ATTACHED_FILENAME


def load_attached(workspace: Path = ROOT_DIR) -> Dict[str, str]:
    """Attached project folders by name; an unreadable file is an error, not an empty list."""
    path = _attached_path(workspace)
    if not path.exists():
        return {}
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError) as exc:
        raise ProjectError(
            f"Cannot read {path}: {exc}",
            "it lists the attached project folders; reading it as empty would forget them.",
            f"restore `{path.name}.bak` over it, or delete it and attach the folders again.",
        ) from exc
    projects = data.get("projects") if isinstance(data, dict) else None
    if not isinstance(projects, dict):
        raise ProjectError(
            f"{path} has no 'projects' mapping.",
            "it lists the attached project folders; reading it as empty would forget them.",
            f"restore `{path.name}.bak` over it, or delete it and attach the folders again.",
        )
    return {str(k): str(v) for k, v in projects.items()}


def _registered_names(workspace: Path, attached: Optional[Dict[str, str]] = None) -> Dict[str, Path]:
    """Name to folder for every project; `attached` spares a second read of `attached.json`."""
    attached = load_attached(workspace) if attached is None else attached
    names = {name: Path(path) for name, path in attached.items()}
    root = projects_dir(workspace)
    if root.is_dir():
        for child in sorted(root.iterdir()):
            if config_path(child).is_file():
                names.setdefault(child.name, child)
    return names


def _run_git(project_root: Path, *args: str) -> "subprocess.CompletedProcess[str]":
    try:
        return subprocess.run(["git", *args], cwd=project_root, capture_output=True, text=True,
                              encoding="utf-8", errors="replace", timeout=GIT_TIMEOUT_SECONDS)
    except (OSError, subprocess.TimeoutExpired) as exc:
        raise ProjectError(
            f"`git {args[0]}` failed in {project_root}: {exc}",
            "every project is its own git repository, separate from AIKit's.",
            "install git and put it on PATH, then run the command again.",
        ) from exc


def _git_start(project_root: Path) -> None:
    """
    `git init`, then commit the project's memory and instructions so a new project starts clean.
    Raises when the commit cannot be made (typically no git identity): a clean baseline is required
    for delivery and the UI guard, and AIKit never invents an author.
    """
    result = _run_git(project_root, "init", "--quiet")
    if result.returncode != 0:
        raise ProjectError(
            f"`git init` failed in {project_root}: {result.stderr.strip()}",
            "every project is its own git repository, separate from AIKit's.",
            "fix the git error above, then run the command again.",
        )
    # LICENSE only when present: `git add` of a missing path fails the whole call.
    stage_items = [item for item in (".gitignore", "LICENSE", "COMMERCIAL.md", "ASSETS.md",
                                     "REUSE.toml", "LICENSES", "README.md", PROJECT_MEMORY_DIRNAME)
                   if (project_root / item).exists()]
    _run_git(project_root, "add", "--", *stage_items)
    result = _run_git(project_root, "commit", "--quiet", "-m", "chore: start project with AIKit memory")
    if result.returncode != 0:
        # git's last stderr line is the cause; the lines before it are generic advice.
        cause = (result.stderr.strip().splitlines() or ["git commit failed"])[-1]
        raise ProjectError(
            f"initial commit failed: {cause}",
            "a project needs a committed baseline for delivery, UI baselines and publish.",
            "set `git config user.name` and `git config user.email` (or repo-local equivalents), "
            "then run `aikit new` again.",
        )
    return None


def create_project(name: str, test_command: Optional[str] = None, workspace: Path = ROOT_DIR,
                   git_start: Optional[Callable[[Path], None]] = None,
                   description: Optional[str] = None, topics: Optional[List[str]] = None,
                   license_kind: str = DEFAULT_LICENSE_KIND) -> Path:
    """
    Create `projects/<name>/` as a new git repository whose first commit holds the project's
    `.aikit/` memory and return the folder. `git_start` defaults to the real git calls
    (PRINCIPLE-009 R4: a test injects a double) and raises when it cannot commit a baseline.
    `license_kind` selects software (AL-1.1), game (AGL-1.1) or science (ASL-1.1) (ADR-218).
    """
    git_start = git_start or _git_start
    validate_name(name)
    # Checked before the folder exists, so a refused value leaves nothing behind (ADR-199).
    description = validate_description(description)
    topics = normalize_topics(topics)
    license_choice(license_kind)
    # License tags are mandatory metadata, not AI suggestions; keep room for them under the
    # 20-topic ceiling before user topics.
    license_tags = license_topics(license_kind)
    combined = [*INTEGRATION_TOPICS, *license_tags,
                *[topic for topic in topics if topic not in INTEGRATION_TOPICS]]
    topics = normalize_topics(combined[:MAX_TOPICS])
    if name in _registered_names(workspace):
        raise ProjectError(
            f"A project named '{name}' already exists.",
            "a name selects exactly one project folder.",
            "pick another name, or work on the existing project.",
        )
    project_root = projects_dir(workspace) / name
    if project_root.exists():
        raise ProjectError(
            f"{project_root} already exists.",
            "`new` creates a folder; it never adopts or overwrites one.",
            f"run `python aikit.py attach {project_root}` to register the existing folder.",
        )
    project_root.mkdir(parents=True)
    try:
        write_memory(project_root, name, test_command, topics)
        seed_license(project_root, license_kind)
        seed_reuse(project_root, license_kind)
        seed_assets_manifest(project_root, license_kind)
        seed_commercial(project_root)
        seed_readme(project_root, name, test_command, description, licensed=True,
                    license_kind=license_kind)
        git_start(project_root)
    except BaseException:
        # Only this call created the folder, so removing it leaves no half-made project behind.
        shutil.rmtree(project_root, ignore_errors=True)
        raise
    return project_root


def attach_project(folder: Path, name: Optional[str] = None, test_command: Optional[str] = None,
                   workspace: Path = ROOT_DIR) -> Tuple[str, Path, bool]:
    """
    Register an existing folder as a project; returns (name, folder, memory_created). The folder's
    own files and git history are left alone apart from `.aikit/` and `.gitignore` entries.
    """
    folder = folder.resolve()
    if not folder.is_dir():
        raise ProjectError(
            f"{folder} is not a directory.",
            "`attach` registers an existing project folder.",
            "pass the path of the project's top folder, or create one with `python aikit.py new <name>`.",
            exit_code=2,
        )
    kit = workspace.resolve()
    inside_projects = projects_dir(kit) in folder.parents
    if not inside_projects and (folder == kit or kit in folder.parents or folder in kit.parents):
        raise ProjectError(
            f"{folder} overlaps the AIKit folder {kit}.",
            "a project inside AIKit's own tree (or containing it) would mix AIKit's files with the "
            "project's.",
            f"move the project into {projects_dir(kit)} or outside AIKit, then attach it.",
            exit_code=2,
        )
    name = name or re.sub(r"[^a-z0-9_-]+", "-", folder.name.lower()).strip("-_")
    validate_name(name)
    registered = _registered_names(kit)
    if name in registered and registered[name].resolve() != folder:
        raise ProjectError(
            f"A different project named '{name}' already exists.",
            "a name selects exactly one project folder.",
            "pass another name with `--name`.",
        )
    # One folder, one name: a second name made two projects share one .aikit/ ledger (ADR-202).
    other = next((known for known, path in registered.items()
                  if known != name and path.resolve() == folder), None)
    if other is not None:
        raise ProjectError(
            f"{folder} is already attached as '{other}'.",
            "a folder holds one .aikit/ memory, so it can be one project only.",
            f"use `{other}`, or detach it first by removing its entry from projects/attached.json.",
            exit_code=2,
        )
    created = write_memory(folder, name, test_command)
    if not inside_projects:
        path = _attached_path(kit)
        with file_lock(path):
            attached = load_attached(kit)
            attached[name] = str(folder)
            atomic_write_json(path, {"schema": SCHEMA_VERSION, "projects": attached})
    return name, folder, created


def _build_project(name: str, path: Path, attached: bool) -> Project:
    present = config_path(path).is_file()
    override = load_config(path).get("test_command") if present else None
    stacks = detect_stacks(path) if present else ()
    detected = next((s.test_command for s in stacks if s.test_command), None)
    return Project(name, path, attached, stacks,
                   override if isinstance(override, str) else detected, present)


def list_projects(workspace: Path = ROOT_DIR) -> List[Project]:
    """Every registered project, sorted by name; a vanished attached folder is reported, not dropped."""
    attached = load_attached(workspace)
    return [_build_project(name, path, name in attached)
            for name, path in sorted(_registered_names(workspace, attached).items())]


def find_project(name: str, workspace: Path = ROOT_DIR) -> Project:
    """The registered project called `name`; only that project's folder is inspected."""
    attached = load_attached(workspace)
    path = _registered_names(workspace, attached).get(name)
    if path is not None:
        return _build_project(name, path, name in attached)
    raise ProjectError(
        f"No project named '{name}'.",
        "commands act on a registered project only.",
        "run `python aikit.py list` to see the names, or `python aikit.py new <name>`.",
        exit_code=2,
    )



def project_guidelines(project_root: Path) -> List[str]:
    """The project's rule lines (`- **G-NNN** (source): rule`), oldest first; [] when it has none."""
    path = project_root / PROJECT_MEMORY_DIRNAME / GUIDELINES_FILENAME
    if not path.is_file():
        return []
    return [line.strip() for line in path.read_text(encoding="utf-8").splitlines()
            if re.match(r"^- \*\*G-\d{3}\*\* \(", line.strip())]


def add_guideline(project_root: Path, rule: str, source: str) -> str:
    """
    Append one rule to the project's guidelines and return its new ID. Whatever the guidelines
    gate would reject, an override of a principle above all, is refused before anything is written.
    """
    rule, source = rule.strip(), source.strip()
    if not rule or "\n" in rule or not source or any(c in source for c in "()\n"):
        raise ProjectError(
            "A guideline needs a one-line rule and a source.",
            "each rule is one identifiable line that says where it came from (PRINCIPLE-001 R4).",
            'pass the rule as one quoted line and --source user, ADR-NNN or a person\'s name.',
            exit_code=2,
        )
    path = project_root / PROJECT_MEMORY_DIRNAME / GUIDELINES_FILENAME
    with file_lock(path):
        text = path.read_text(encoding="utf-8") if path.is_file() else GUIDELINES_TEMPLATE
        used = [int(n) for n in re.findall(r"^- \*\*G-(\d{3})\*\*", text, re.M)]
        gid = f"G-{max(used, default=0) + 1:03d}"
        updated = text.rstrip("\n") + f"\n- **{gid}** ({source}): {rule}\n"
        errors = guideline_errors(updated)
        if errors:
            raise ProjectError(
                f"The guideline was not added: {'; '.join(errors)}.",
                "project guidelines add rules below AIKit's principles and can never override one "
                "(PRINCIPLE-000 R6).",
                "state the rule as a constraint the principles allow, or ask the user whether a "
                "principle itself should change.",
            )
        write_generated_file(path, updated)
    return gid


def latest_decision(project_root: Path) -> Optional[str]:
    """The last `### ADR-NNN: ...` heading in the project's decision register, if any."""
    path = project_root / PROJECT_MEMORY_DIRNAME / DECISIONS_FILENAME
    if not path.is_file():
        return None
    # The template's entry-format example sits in an HTML comment; it is not a decision.
    text = re.sub(r"<!--.*?-->", "", path.read_text(encoding="utf-8"), flags=re.S)
    headings = re.findall(r"^### (ADR-\d+: .+)$", text, flags=re.M)
    return headings[-1] if headings else None
