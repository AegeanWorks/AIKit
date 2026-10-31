"""
GitHub topic policy (ADR-234, revised by ADR-236): an AI agent chooses the tags; AIKit validates,
records and applies them.

GitHub allows 20 topics per repository. AIKit never invents the final list: it produces a bounded
brief from the project's own README, stack, interface identifier and licence, and then accepts the
agent's explicit choice (`--from-file` or `--set`). The validator only enforces GitHub's syntax,
the 20-topic cap, uniqueness and the permanent `aikit` topic. A current tag survives only when the
agent keeps it; no evidence hint is written automatically.
"""

import json
import re
from pathlib import Path
from typing import Callable, Dict, Iterable, List, Optional, Sequence, Tuple

from scripts.project_license import license_state
from scripts.project_publish import get_project_repo_url, run_command
from scripts.project_registry import (
    MAX_TOPICS,
    TOPIC_PATTERN,
    detect_stacks,
    license_topics,
    normalize_topics,
    repository_name,
)
from scripts.project_ui import detect_ui

Runner = Callable[[List[str]], Tuple[int, str]]
README_BRIEF_CHARS = 4000
MIN_CHOICES = 2

# Hints for the AI brief, never applied automatically. Each pair is a keyword and the discovery
# tags an agent may consider when the keyword genuinely describes the project.
TOPIC_HINTS: Tuple[Tuple[Tuple[str, ...], Tuple[str, ...]], ...] = (
    (("ai", "artificial intelligence", "llm", "prompt", "transformer", "model"),
     ("ai", "llm", "machine-learning")),
    (("agent", "agentic", "autonomous"), ("ai-agents", "agentic-ai")),
    (("local-first", "offline", "no network"), ("local-first", "offline-first")),
    (("privacy", "private", "local data"), ("privacy", "privacy-preserving")),
    (("cli", "command line", "command-line"), ("cli", "command-line-tool")),
    (("web app", "web-app", "browser", "http server"), ("web", "web-app")),
    (("api", "sdk", "client library"), ("api", "sdk")),
    (("desktop", "window", "gui", "dashboard"), ("desktop-app", "gui", "dashboard")),
    (("game", "pygame", "godot", "roguelike", "dungeon"), ("game", "gamedev")),
    (("science", "research", "experiment", "n-of-1", "falsification"), ("science", "research")),
    (("health", "medical", "clinic", "neuro", "sleep", "binaural"),
     ("health", "healthcare", "neuroscience")),
    (("test", "testing", "quality", "audit", "verify", "gate"), ("testing", "quality-assurance")),
    (("security", "secret", "credential", "signature", "vulnerability"),
     ("security", "secrets-management")),
    (("database", "sqlite", "storage engine", "ledger"), ("database", "sqlite")),
    (("memory", "rag", "knowledge graph", "knowledge-graph"), ("memory", "rag", "knowledge-graph")),
    (("visualization", "chart", "plot", "image"), ("visualization", "data-visualization")),
    (("automation", "workflow engine", "pipeline"), ("automation", "workflow")),
    (("framework", "developer tool", "developer-tools", "library"),
     ("developer-tools", "framework")),
    (("education", "learn", "tutorial", "lesson"), ("education", "learning")),
    (("music", "audio", "sound"), ("audio", "music", "sound")),
    (("game asset", "sprite", "pixel art", "pixel-art"), ("pixel-art", "game-assets")),
)
BASE_TAGS = ("aikit", "aikit-integrated", "aegeanworks", "software")
STACK_TAGS = {"python": "python", "node": "javascript", "rust": "rust", "go": "golang",
              "java-maven": "java", "java-gradle": "java", "dotnet": "dotnet"}
CHOICE_SCHEMA = {
    "topics": ["aikit", "aegeanworks", "software", "python"],
    "reason": "one short sentence on why this list fits the repository",
}


def _read_readme(root: Path) -> str:
    path = root / "README.md"
    try:
        if path.is_file():
            return path.read_text(encoding="utf-8", errors="replace")[:README_BRIEF_CHARS]
    except OSError:  # hygiene: allow unreadable-README to yield the empty brief excerpt
        pass
    return ""


def _license_tags(root: Path) -> List[str]:
    try:
        state = license_state(root)
    except (OSError, ValueError, KeyError):
        return []
    if state is None:
        return []
    return license_topics(getattr(state, "kind", None), state.tier == "restricted")


def _has_token(text: str, token: str) -> bool:
    pattern = r"(?<![a-z0-9])" + re.escape(token) + r"(?![a-z0-9])"
    return re.search(pattern, text) is not None


def hint_tags(project_root: Path, description: str = "") -> List[str]:
    """Possible tags for the AI to consider; the agent decides and may ignore all of them."""
    root = Path(project_root)
    text = " ".join((repository_name(root.name), description, _read_readme(root))).lower()
    tags = list(BASE_TAGS)
    for stack in detect_stacks(root):
        tag = STACK_TAGS.get(stack.name)
        if tag:
            tags.append(tag)
    if (root / "tsconfig.json").is_file() or "typescript" in text:
        tags.append("typescript")
    ui = detect_ui(root)
    if ui.get("has_ui"):
        tags.append("user-interface")
        kind = str(ui.get("kind") or "")
        if kind == "web":
            tags.append("web-app")
        elif kind == "desktop":
            tags.append("desktop-app")
        elif kind == "game":
            tags.extend(("game", "gamedev"))
        elif kind == "mobile":
            tags.append("mobile-app")
    elif ui.get("kind") == "cli":
        tags.append("cli")
    for tokens, mapped in TOPIC_HINTS:
        if any(_has_token(text, token) for token in tokens):
            tags.extend(mapped)
    tags.extend(_license_tags(root))
    return _dedupe(tag for tag in tags if TOPIC_PATTERN.match(tag))


def ai_brief(project_root: Path, name: str, recorded: Sequence[str],
             current: Sequence[str] = ()) -> Dict[str, object]:
    """The bounded evidence an AI agent needs to choose the final tags."""
    root = Path(project_root)
    description = ""
    try:
        from scripts.project_publish import extract_readme_description
        description = extract_readme_description(root) or ""
    except (OSError, ValueError):
        description = ""
    ui = detect_ui(root)
    stacks = [stack.name for stack in detect_stacks(root)]
    return {
        "project": name,
        "repo": repository_name(name),
        "description": description,
        "readme_excerpt": _read_readme(root),
        "stacks": stacks,
        "ui": {"has_ui": bool(ui.get("has_ui")), "kind": ui.get("kind"),
               "evidence": list(ui.get("evidence") or [])},
        "license_hints": _license_tags(root),
        "recorded_topics": list(recorded),
        "current_topics": list(current),
        "hint_tags": hint_tags(root, description),
        "max_topics": MAX_TOPICS,
        "rules": [
            "You choose the final list; AIKit only validates it.",
            "Keep a current tag only if it genuinely describes the project.",
            "Use lowercase letters, digits and '-' only; 50 characters maximum.",
            "Aim for the most useful set up to 20; do not pad with unrelated or duplicate tags.",
            "Never claim open-source for a source-available licence.",
            "`aikit` is always included.",
        ],
        "reply_schema": CHOICE_SCHEMA,
    }


def _dedupe(tags: Iterable[str]) -> List[str]:
    result = []
    for raw in tags:
        tag = str(raw).strip().lower()
        if TOPIC_PATTERN.match(tag) and tag not in result:
            result.append(tag)
    return result


def _dedupe_raw(tags: Iterable[object]) -> List[str]:
    seen = []
    for raw in tags:
        tag = str(raw).strip().lower()
        if tag and tag not in seen:
            seen.append(tag)
    return seen


def validate_choice(project_root: Path, recorded: Sequence[str], current: Sequence[str],
                    chosen: Sequence[str], replace: bool = False,
                    remove: Sequence[str] = ()) -> Dict[str, object]:
    """Validate an AI addition to the existing tags; valid older tags are never dropped.

    `replace=True` is the explicit `--set` path. The normal AI workflow (`--from-file`) keeps every
    valid current tag, then adds the AI's new choice until GitHub's 20-topic ceiling.
    """
    invalid = [tag for tag in _dedupe_raw(chosen) if not TOPIC_PATTERN.match(tag)]
    if invalid:
        raise ValueError(f"invalid topics chosen: {', '.join(invalid)}")
    current_raw = _dedupe_raw(current)
    valid_current = [tag for tag in current_raw if TOPIC_PATTERN.match(tag)]
    # Offline/no-remote projects have no live list; their recorded list is the current truth.
    valid_recorded = [tag for tag in _dedupe_raw(recorded) if TOPIC_PATTERN.match(tag)]
    if replace:
        topics = normalize_topics(_dedupe_raw(chosen))
    else:
        merged = _dedupe_raw([*valid_current, *valid_recorded, *chosen])
        if "aikit" not in merged:
            merged.insert(0, "aikit")
        topics = normalize_topics(merged[:MAX_TOPICS])
    requested_removals = {tag.strip().lower() for tag in remove}
    if requested_removals:
        topics = [tag for tag in topics if tag not in requested_removals]
        if "aikit" not in topics:
            topics.insert(0, "aikit")
    if len(topics) < MIN_CHOICES:
        raise ValueError("the AI choice needs at least one tag beside 'aikit'")
    if len(topics) > MAX_TOPICS:
        raise ValueError(f"{len(topics)} topics exceeds GitHub's {MAX_TOPICS}")
    kept = [tag for tag in valid_current if tag in topics]
    added = [tag for tag in topics if tag not in current_raw]
    removed = [tag for tag in current_raw if tag not in topics]
    return {
        "current": list(current),
        "recorded": list(recorded),
        "desired": topics,
        "kept": kept,
        "added": added,
        "removed": removed,
        "invalid_chosen": invalid,
        "invalid_current": [tag for tag in current_raw if not TOPIC_PATTERN.match(tag)],
        "at_limit": len(topics) >= MAX_TOPICS,
        "count": len(topics),
    }


def choice_from_payload(payload: object) -> Dict[str, object]:
    """Accept `{"topics": [...], "remove": [...]}` or a bare list; anything else is refused."""
    removals: List[str] = []
    if isinstance(payload, dict):
        raw_remove = payload.get("remove", [])
        if raw_remove and (not isinstance(raw_remove, list)
                           or not all(isinstance(item, str) for item in raw_remove)):
            raise ValueError('"remove" must be a list of strings')
        removals = [str(item).strip().lower() for item in raw_remove]
        payload = payload.get("topics")
    if not isinstance(payload, list) or not all(isinstance(item, str) for item in payload):
        raise ValueError('the choice file must be {"topics": ["..."]} or a JSON array of strings')
    return {"topics": [item for item in payload], "remove": removals}


def read_choice_file(path: Path) -> Dict[str, object]:
    try:
        payload = json.loads(Path(path).read_text(encoding="utf-8"))
    except (OSError, ValueError) as exc:
        raise ValueError(f"cannot read the AI choice file: {exc}") from exc
    return choice_from_payload(payload)


def repo_slug(project_root: Path, name: str) -> str:
    """`owner/repo` from the project's origin, else the conventional AegeanWorks name."""
    url = get_project_repo_url(Path(project_root))
    if url:
        match = re.search(r"github\.com[/:]([^/]+)/([^/.]+?)(?:\.git)?/?$", url)
        if match:
            return f"{match.group(1)}/{match.group(2)}"
    return f"AegeanWorks/{repository_name(name)}"


def github_topics(slug: str, runner: Optional[Runner] = None) -> Tuple[List[str], str]:
    """Read the repository's live topics; ([], error) when GitHub cannot be reached."""
    run = runner or (lambda argv: run_command(argv, Path.cwd()))
    code, output = run(["gh", "api", "-H", "Accept: application/vnd.github+json",
                        f"repos/{slug}/topics"])
    if code != 0:
        return [], output.strip()[-300:]
    try:
        data = json.loads(output)
    except ValueError:
        return [], "the topics response was not JSON"
    names = data.get("names") if isinstance(data, dict) else None
    return ([str(item) for item in names] if isinstance(names, list) else []), ""


def apply_topics(slug: str, add: Sequence[str], remove: Sequence[str],
                 runner: Optional[Runner] = None) -> Dict[str, object]:
    """Add and remove topics in two explicit calls; a failure is reported, never hidden."""
    run = runner or (lambda argv: run_command(argv, Path.cwd()))
    notes = []
    if remove:
        code, output = run(["gh", "repo", "edit", slug, "--remove-topic", ",".join(remove)])
        notes.append({"action": "remove", "ok": code == 0, "detail": output.strip()[-200:]})
    if add:
        code, output = run(["gh", "repo", "edit", slug, "--add-topic", ",".join(add)])
        notes.append({"action": "add", "ok": code == 0, "detail": output.strip()[-200:]})
    return {"slug": slug, "ok": all(note["ok"] for note in notes), "calls": notes}


def topic_audit(current: Sequence[str], recorded: Sequence[str]) -> Dict[str, object]:
    """Audit the live/recorded lists without choosing anything for the agent."""
    current_raw = _dedupe_raw(current)
    problems = []
    invalid = [tag for tag in current_raw if not TOPIC_PATTERN.match(tag)]
    if invalid:
        problems.append(f"invalid topics: {', '.join(invalid)}")
    if len(current_raw) > MAX_TOPICS:
        problems.append(f"{len(current_raw)} topics exceeds GitHub's {MAX_TOPICS}")
    if set(current_raw) != set(_dedupe_raw(recorded)):
        problems.append("the live topics and the recorded topics differ; run --review")
    return {"ok": not problems, "problems": problems, "invalid": invalid,
            "current": current_raw, "recorded": _dedupe_raw(recorded),
            "at_limit": len(current_raw) >= MAX_TOPICS}
