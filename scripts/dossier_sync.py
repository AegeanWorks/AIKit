"""Keep the AegeanWorks dossier catalogue in step with a published project (PRINCIPLE-016).

One publish is the only event that makes a project part of the public portfolio, so the same
command updates everything the dossier derives from GitHub: the captured metadata, the site
snapshot, the per-repository license ledger, the project card and its JSON-LD entry, the README
atlas row and the catalogue set the dossier's own tests pin. The dossier's media builder then
rebuilds that repository's schema-2 manifest, or the media workflow does it on the next push.

The dossier is written atomically and never committed here: its own repository, gates and review
stay with its owner (PRINCIPLE-018 R1).
"""

import base64
import hashlib
import html
import json
import re
import subprocess
import sys
import time
from pathlib import Path
from typing import Dict, List, Optional, Tuple

from scripts.disruption_recovery import atomic_write_text
from scripts.project_license import TIER_RESTRICTED, license_state
from scripts.project_publish import extract_readme_description, get_project_repo_url
from scripts.project_registry import ProjectError, load_config

ROOT_DIR = Path(__file__).resolve().parent.parent
DOSSIER_REL = Path("projects") / "AegeanWorks"
OWNER = "AegeanWorks"
# The dossier groups the README atlas by category; the card's data-cat uses the same keys.
CATEGORY_LABELS = {
    "ai": "Cognitive AI &amp; Agent Infrastructure",
    "research": "Research &amp; Simulation",
    "health": "Health, Neuro &amp; Personal Tools",
    "tools": "Developer Tools &amp; Utilities",
    "play": "Games &amp; Playable Experiments",
}
SCHEMA_TYPES = {
    "ai": "ArtificialIntelligenceApplication",
    "play": "GameApplication",
}
LICENSE_FAMILIES = {"software": "AL", "game": "AGL", "science": "ASL"}
LICENSE_SHORTS = {"AL": "AL-1.1", "AGL": "AGL-1.1", "ASL": "ASL-1.1"}
TAG_OMIT = {"aikit", "python", "source-available"}
HEALTH_MARKERS = ("health", "medical", "neurology", "clinic", "patient", "diagnos", "sleep")
AI_MARKERS = ("ai", "agent", "llm", "model", "rag", "inference", "cognitive")
MEDIA_TIMEOUT = 240


def dossier_root(explicit: Optional[Path] = None) -> Optional[Path]:
    """The dossier checkout, or None when this workspace does not carry one."""
    candidate = Path(explicit) if explicit else ROOT_DIR / DOSSIER_REL
    return candidate if (candidate / "docs" / "index.html").is_file() else None


def repository_slug(url: Optional[str]) -> Optional[Tuple[str, str]]:
    """(owner, repository) from a GitHub origin URL, else None."""
    if not url:
        return None
    match = re.search(r"github\.com[:/]+([^/\s]+)/([^/\s]+?)(?:\.git)?$", url.strip())
    return (match.group(1), match.group(2)) if match else None


def _today() -> str:
    return time.strftime("%Y-%m-%d")


def _write(path: Path, text: str) -> None:
    atomic_write_text(path, text, backup=False)


def github_facts(name: str) -> Dict[str, object]:
    """The repository's live GitHub facts, read through the `gh` CLI publish already requires."""
    try:
        proc = subprocess.run(
            ["gh", "api", f"repos/{OWNER}/{name}"],
            capture_output=True, text=True, encoding="utf-8", errors="replace", timeout=30,
        )
    except (OSError, subprocess.TimeoutExpired) as exc:
        raise ProjectError(
            f"could not reach GitHub for '{name}'.",
            f"the `gh` CLI failed to run: {exc}",
            "install and authenticate `gh` (`gh auth status`), then retry the publish.",
        )
    if proc.returncode != 0:
        raise ProjectError(
            f"GitHub did not return the repository '{OWNER}/{name}'.",
            (proc.stderr or proc.stdout or "").strip()[-400:] or "gh exited non-zero.",
            f"confirm the repository is public with `gh api repos/{OWNER}/{name}`, then retry.",
        )
    try:
        return json.loads(proc.stdout)
    except ValueError as exc:
        raise ProjectError(
            f"GitHub's answer for '{name}' was not JSON.",
            str(exc),
            "retry after `gh auth status` reports a healthy login.",
        )


def catalogue_category(project_path: Path, topics: List[str], description: str) -> str:
    """The dossier category from the project's license kind and its own words."""
    kind = license_state(Path(project_path)).kind
    if kind == "game":
        return "play"
    if kind == "science":
        return "research"
    words = " ".join([*topics, description]).lower()
    if any(marker in words for marker in HEALTH_MARKERS):
        return "health"
    if any(marker in words for marker in AI_MARKERS):
        return "ai"
    return "tools"


def build_entry(name: str, facts: Dict[str, object], description: str) -> Dict[str, object]:
    """The metadata entry the dossier records, in the catalogue's own key order."""
    language = facts.get("language")
    pushed_at = str(facts.get("pushed_at") or "")
    if not isinstance(language, str) or not language.strip():
        raise ProjectError(
            f"GitHub reports no language for '{name}'.",
            "the site card shows the repository's language, and an empty value breaks the catalogue.",
            "push at least one source file to the repository, then retry the publish.",
        )
    if len(pushed_at) < 10:
        raise ProjectError(
            f"GitHub reports no push date for '{name}'.",
            "the site card shows the last update date, and an empty value breaks the catalogue.",
            "push a commit to the repository, then retry the publish.",
        )
    if not description.strip():
        raise ProjectError(
            f"'{name}' has no description for the dossier.",
            "each catalogue card and README row carries the repository's one-line description.",
            "write a README paragraph of 10-350 characters, then retry the publish.",
        )
    license_facts = facts.get("license") if isinstance(facts.get("license"), dict) else {}
    return {
        "id": int(facts.get("id") or 0),
        "name": name,
        "description": description.strip(),
        "topics": [str(topic) for topic in facts.get("topics") or []],
        "language": language,
        "license": str(license_facts.get("spdx_id") or "NOASSERTION"),
        "pushed_at": pushed_at,
        "homepage": str(facts.get("homepage") or ""),
        "archived": bool(facts.get("archived")),
        "default_branch": str(facts.get("default_branch") or "main"),
    }


def _load_json(path: Path) -> Dict[str, object]:
    return json.loads(path.read_text(encoding="utf-8"))


def _dump_json(data: Dict[str, object]) -> str:
    return json.dumps(data, indent=2, ensure_ascii=False) + "\n"


def _upsert_metadata(dossier: Path, entry: Dict[str, object]) -> bool:
    path = dossier / "tests" / "metadata" / "repositories.json"
    data = _load_json(path)
    repositories = list(data.get("repositories") or [])
    for index, repo in enumerate(repositories):
        if str(repo.get("name", "")).lower() == str(entry["name"]).lower():
            repositories[index] = entry
            break
    else:
        repositories.append(entry)
    data["repositories"] = repositories
    data["captured_at"] = _today()
    _write(path, _dump_json(data))
    return True


def _upsert_snapshot(dossier: Path, entry: Dict[str, object]) -> bool:
    metadata = _load_json(dossier / "tests" / "metadata" / "repositories.json")
    path = dossier / "docs" / "atlas-snapshot.json"
    data = _load_json(path)
    data["profile"] = metadata.get("profile") or data.get("profile")
    data["repositories"] = metadata.get("repositories") or [entry]
    data["generated_at"] = _today()
    _write(path, _dump_json(data))
    return True


def _upsert_license(dossier: Path, name: str, family: str) -> bool:
    path = dossier / "docs" / "atlas-core.js"
    text = path.read_text(encoding="utf-8")
    pattern = re.compile(r"(export const REPO_LICENSES = Object\.freeze\(\{\n)(.*?)(\n\}\);)", re.S)
    match = pattern.search(text)
    if match is None:
        return False
    key = name.lower()
    entry = f'  "{key}": "{family}",\n'
    body = match.group(2)
    existing = re.compile(r'^\s*"?%s"?\s*:\s*"[A-Z]+",\s*$' % re.escape(key), re.M)
    if existing.search(body):
        body = existing.sub(entry.rstrip("\n"), body)
    else:
        body = body.rstrip("\n") + "\n" + entry.rstrip("\n")
    _write(path, text[:match.start(2)] + body + text[match.end(2):])
    return True


def _escape(value: str) -> str:
    return html.escape(str(value), quote=False)


def _attribute(value: str) -> str:
    return html.escape(str(value), quote=True)


def _card(entry: Dict[str, object], family: str, category: str, mark: str) -> str:
    name = str(entry["name"])
    topics = ",".join(str(topic) for topic in entry["topics"])
    tags = "".join(
        f'<span class="tag">{_escape(topic)}</span>'
        for topic in [t for t in entry["topics"] if t not in TAG_OMIT][:6]
    )
    short = LICENSE_SHORTS.get(family, family)
    return (
        f'<a class="project reveal" data-repo-id="{int(entry["id"])}" '
        f'data-archived="{"true" if entry["archived"] else "false"}" data-cat="{category}" '
        f'data-topics="{_attribute(topics)}" '
        f'data-repo-url="https://github.com/{OWNER}/{name}" href="project.html?repo={name}" '
        f'data-language="{_attribute(str(entry["language"]))}" data-license="{short}" '
        f'data-pushed-at="{_escape(str(entry["pushed_at"]))}"> '
        '<!-- hygiene: allow outbound link, not a loaded dependency -->\n'
        f'          <span class="project-mark mark-{category}" aria-hidden="true">{mark}</span>\n'
        f'          <h3>{_escape(name)}</h3>\n'
        f'          <p>{_escape(str(entry["description"]))}</p>\n\n'
        f'          <span class="project-facts">{_escape(str(entry["language"]))} — {short} — '
        f'Updated {_escape(str(entry["pushed_at"]))[:10]}</span>\n\n'
        f'          <span class="project-tags">{tags}</span>\n'
        '        </a>'
    )


def _upsert_card(dossier: Path, entry: Dict[str, object], family: str,
                 category: str) -> bool:
    path = dossier / "docs" / "index.html"
    text = path.read_text(encoding="utf-8")
    url = f"https://github.com/{OWNER}/{entry['name']}"
    block = re.compile(r'<a class="project reveal".*?</a>', re.S)
    old = next((m for m in block.finditer(text) if f'data-repo-url="{url}"' in m.group(0)),
               None)
    if old is not None:
        old_category = re.search(r'data-cat="([^"]+)"', old.group(0))
        category = old_category.group(1) if old_category else category
        old_mark = re.search(r'project-mark mark-\w+" aria-hidden="true">([^<]+)<', old.group(0))
        mark = old_mark.group(1) if old_mark else _mark(str(entry["name"]))
        text = text[:old.start()] + _card(entry, family, category, mark) + text[old.end():]
    else:
        grid = text.find('<div class="project-grid" id="project-grid">')
        close = text.find("\n      </div>", grid)
        if grid < 0 or close < 0:
            return False
        text = text[:close] + "\n\n        " + _card(entry, family, category, _mark(str(entry["name"]))) + text[close:]
    _write(path, text)
    return True


def _mark(name: str) -> str:
    return (name[:1].upper() + name[1:2].lower()) or "AW"


def _inline_digest(body: str) -> str:
    return base64.b64encode(hashlib.sha256(body.encode("utf-8")).digest()).decode("ascii")


def _refresh_inline_hash(page: str, old_body: str, new_body: str) -> str:
    """Replace the old inline-script CSP hash, so the rewritten JSON-LD stays allowed."""
    old_hash = f"'sha256-{_inline_digest(old_body)}'"
    new_hash = f"'sha256-{_inline_digest(new_body)}'"
    if old_hash == new_hash:
        return page
    policy = re.search(r'(http-equiv="Content-Security-Policy" content=")([^"]*)(")', page)
    if policy is None or old_hash not in policy.group(2):
        return page
    updated = policy.group(2).replace(old_hash, new_hash, 1)
    return page[:policy.start(2)] + updated + page[policy.end(2):]


def _upsert_jsonld(dossier: Path, entry: Dict[str, object], family: str,
                   category: str) -> bool:
    path = dossier / "docs" / "index.html"
    text = path.read_text(encoding="utf-8")
    script = re.compile(r'(<script type="application/ld\+json">)(.*?)(</script>)', re.S)
    match = script.search(text)
    if match is None:
        return False
    data = json.loads(match.group(2))
    item_lists = [node for node in data.get("@graph", []) if node.get("@type") == "ItemList"]
    if not item_lists:
        return False
    item_list = item_lists[0]
    name = str(entry["name"])
    url = f"https://github.com/{OWNER}/{name}"
    items = item_list.get("itemListElement") or []
    item = {
        "@type": "ListItem",
        "position": len(items) + 1,
        "item": {
            "@type": "SoftwareApplication",
            "name": name,
            "description": str(entry["description"]),
            "applicationCategory": SCHEMA_TYPES.get(category, "DeveloperApplication"),
            "url": f"https://aegeanworks.github.io/AegeanWorks/project.html?repo={name}",
            "codeRepository": url,
        },
    }
    for index, existing in enumerate(items):
        if str(existing.get("item", {}).get("codeRepository", "")).lower() == url.lower():
            item["position"] = existing.get("position", index + 1)
            items[index] = item
            break
    else:
        items.append(item)
    item_list["itemListElement"] = items
    item_list["numberOfItems"] = len(items)
    old_body = match.group(2)
    new_body = json.dumps(data, ensure_ascii=False, separators=(",", ":"))
    text = text[:match.start(2)] + new_body + text[match.end(2):]
    text = _refresh_inline_hash(text, old_body, new_body)
    count = len(items)
    text = re.sub(r"<dd data-project-count>\d+</dd>", f"<dd data-project-count>{count}</dd>", text)
    text = re.sub(r"<span data-project-count>\d+</span>",
                  f"<span data-project-count>{count}</span>", text)
    _write(path, text)
    return True


def _upsert_readme(dossier: Path, entry: Dict[str, object], category: str) -> bool:
    path = dossier / "README.md"
    text = path.read_text(encoding="utf-8")
    name = str(entry["name"])
    description = str(entry["description"]).replace("|", "\\|")
    row = f"| [{name}](https://github.com/{OWNER}/{name}) | {description} |"
    existing = re.compile(r"^\| \[%s\]\(https://github\.com/%s/[^)]+\) \|.*$"
                          % (re.escape(name), OWNER), re.M)
    if existing.search(text):
        text = existing.sub(lambda _match: row, text, count=1)
    else:
        label = f"<summary><b>{CATEGORY_LABELS.get(category, CATEGORY_LABELS['tools'])}</b></summary>"
        start = text.find(label)
        end = text.find("</details>", start) if start >= 0 else -1
        if end < 0:
            return False
        insert_at = text.rfind("\n\n", start, end)
        insert_at = end if insert_at < 0 else insert_at
        text = text[:insert_at] + "\n" + row + text[insert_at:]
    _write(path, text)
    return True


def _upsert_catalogue_set(dossier: Path, name: str) -> bool:
    path = dossier / "tests" / "test_profile.py"
    text = path.read_text(encoding="utf-8")
    pattern = re.compile(r"(PUBLIC_REPOS = \{\n)(.*?)(\n\})", re.S)
    match = pattern.search(text)
    if match is None:
        return False
    body = match.group(2)
    if re.search(r'^\s*"%s",?\s*$' % re.escape(name), body, re.M):
        return False
    body = body.rstrip("\n") + f'\n    "{name}",'
    _write(path, text[:match.start(2)] + body + text[match.end(2):])
    return True


def sync_entry(dossier: Path, entry: Dict[str, object], family: str,
               category: str) -> List[str]:
    """Upsert one catalogue entry everywhere the dossier records it; return changed files."""
    changed: List[str] = []
    if _upsert_metadata(dossier, entry):
        changed.append("tests/metadata/repositories.json")
    if _upsert_snapshot(dossier, entry):
        changed.append("docs/atlas-snapshot.json")
    if _upsert_license(dossier, str(entry["name"]), family):
        changed.append("docs/atlas-core.js")
    if _upsert_card(dossier, entry, family, category):
        changed.append("docs/index.html")
    # The JSON-LD block and the project counts share index.html with the card.
    if _upsert_jsonld(dossier, entry, family, category) and "docs/index.html" not in changed:
        changed.append("docs/index.html")
    if _upsert_readme(dossier, entry, category):
        changed.append("README.md")
    if _upsert_catalogue_set(dossier, str(entry["name"])):
        changed.append("tests/test_profile.py")
    return changed


def _refresh_media(dossier: Path, name: str) -> str:
    """Rebuild the dossier's schema-2 media for one repository; the workflow retries on push."""
    builder = dossier / "tools" / "build_dossier_media.py"
    if not builder.is_file():
        return "the dossier has no media builder; nothing rebuilt."
    try:
        proc = subprocess.run(
            [sys.executable, str(builder), "fetch", "--repo", name, "--force", "--screenshots"],
            cwd=str(dossier), capture_output=True, text=True, encoding="utf-8",
            errors="replace", timeout=MEDIA_TIMEOUT,
        )
    except (OSError, subprocess.TimeoutExpired) as exc:
        return f"media left to the dossier workflow ({exc})."
    if proc.returncode != 0:
        detail = (proc.stderr or proc.stdout or "").strip().splitlines()
        tail = detail[-1] if detail else "builder exited non-zero"
        return f"media left to the dossier workflow ({tail})."
    return "media rebuilt with the dossier builder."


def sync_published(project_path: Path, project_name: str,
                   dossier: Optional[Path] = None) -> Dict[str, object]:
    """Bring the dossier catalogue in line with a published project; never raises for a skip."""
    root = dossier_root(dossier)
    if root is None:
        return {"skipped": "no AegeanWorks dossier in this workspace"}
    slug = repository_slug(get_project_repo_url(Path(project_path)))
    if slug is None:
        return {"skipped": "the project has no GitHub origin"}
    owner, name = slug
    if owner.lower() != OWNER.lower():
        return {"skipped": f"origin belongs to '{owner}', not {OWNER}"}
    state = license_state(Path(project_path))
    if state.tier == TIER_RESTRICTED:
        return {"skipped": "restricted projects are not published in the dossier"}
    facts = github_facts(name)
    # The catalogue is the public portfolio: `publish` is private by default (ADR-134), so a
    # private repository must never be listed even though the sync can read its facts.
    if facts.get("private"):
        return {"skipped": f"{owner}/{name} is private, so it stays out of the public catalogue"}
    description = str(facts.get("description") or "").strip()
    if not description:
        description = extract_readme_description(Path(project_path))
    entry = build_entry(name, facts, description)
    category = catalogue_category(Path(project_path), list(entry["topics"]), description)
    family = LICENSE_FAMILIES.get(state.kind or "software", "AL")
    files = sync_entry(root, entry, family, category)
    return {
        "project": project_name,
        "repo": name,
        "category": category,
        "family": family,
        "files": files,
        "media": _refresh_media(root, name),
    }
