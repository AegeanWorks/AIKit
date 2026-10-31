"""Generate and validate the Idea Catcher register.

``MATRIX.md`` is a rendered artefact. Its two inputs are ``targets.json`` (which
projects ideas can be routed to) and ``ideas.json`` (every extracted idea, its
routing and its decision state). Editing either input and re-running ``render``
is the whole workflow; ``render --check`` fails when the rendered matrix no
longer matches them, so a stale register cannot be merged.

Adding a routing target is one command, not a code change:

    python aikit.py idea-catcher add-target --id research-engine --name "Research Engine" \
        --path ../research-engine --stack "..." --gate "..." --fit "..."

Every non-``Proposed`` status must record why it was decided. A rejected idea
needs the reason and who decided; an integrated one needs the evidence (ADR or
commit); a superseded one needs the idea that replaced it.

``ideas`` hides ``Rejected`` rows and rows tagged ``duplicate`` unless
``--include-rejected`` / ``--include-duplicates`` (or an explicit ``--status Rejected`` /
``--tag duplicate``) asks for them, so a closed or duplicated idea leaves the default
working list without leaving the audit trail. The reviewer records the reason and author.

Exit codes follow AIKit PRINCIPLE-011: 0 success, 1 validation/check failure,
2 bad usage.
"""

from __future__ import annotations

import argparse
import contextlib
import dataclasses
import datetime
import json
import os
import re
import subprocess
import sys
import tempfile
import time
from pathlib import Path
from typing import Any, List, Mapping, Sequence, Tuple

try:  # ``python idea_catcher/registry.py`` runs the module as a script.
    from . import claim_audit, concept_map, upstream_check
except ImportError:  # pragma: no cover - exercised by the CLI entry point
    import claim_audit  # type: ignore[no-redef]
    import concept_map  # type: ignore[no-redef]
    import upstream_check  # type: ignore[no-redef]

TARGETS_FILE = "targets.json"
IDEAS_FILE = "ideas.json"
REVIEWS_FILE = "reviews.json"
MATRIX_FILE = "MATRIX.md"
LOCK_FILE = ".registry.lock"


def default_root() -> Path:
    """The private register this AIKit checkout serves.

    The shipped package lives at the AIKit root, while its data lives beside it in the
    ignored ``.idea-catcher`` folder and never enters Git. A standalone checkout that keeps
    its data beside the package still works. ``IDEA_CATCHER_ROOT`` overrides both.
    """
    override = os.environ.get("IDEA_CATCHER_ROOT")
    if override:
        return Path(override).expanduser().resolve()
    checkout = Path(__file__).resolve().parents[1]
    if (checkout / TARGETS_FILE).is_file():
        return checkout
    private = checkout / ".idea-catcher"
    if (private / TARGETS_FILE).is_file():
        return private
    return private


ROOT = default_root()

SCHEMA = 1
REVIEW_LEASE_MINUTES = 180
SLUG_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._-]*/[A-Za-z0-9][A-Za-z0-9._-]*$")
MIN_REASON_CHARS = 24
DEFERRAL_LIMIT = 2
BLOCKED_STATUS = "Blocked"
REVIEW_VERDICTS = (
    "adopt", "confirmed", "defer", "duplicate", "implemented", "obsolete", "reject", "blocked",
)
IDEA_ID_RE = re.compile(r"^IDEA-(\d{3,})$")
TARGET_ID_RE = re.compile(r"^[a-z0-9]+(?:-[a-z0-9]+)*$")
DOSSIER_HEADING_RE = re.compile(r"^### `(IDEA-\d{3,})`:[ \t]*(.+?)[ \t]*$", re.M)
DOSSIER_TARGET_RE = re.compile(r"^- \*\*Target Project\*\*: `([^`]+)`", re.M)
DOSSIER_SOURCE_RE = re.compile(r"^- \*\*Source\*\*:[ \t]*(.+?)[ \t]*$", re.M)
MATRIX_ROW_RE = re.compile(r"^\| `(IDEA-\d{3,})` \|", re.M)


@dataclasses.dataclass(frozen=True)
class StatusSpec:
    """One decision state: how it renders and what a recorded decision must carry."""

    label: str
    color: str
    meaning: str
    requires: tuple[str, ...] = ()


# The decision vocabulary is a contract, not configuration: renderer, validator
# and tests all read this table. Statuses are appended, never renamed.
STATUS_SPECS: dict[str, StatusSpec] = {
    "Proposed": StatusSpec(
        "Proposed", "9e9e9e", "Captured in the register; no routing decision yet."
    ),
    "Approved": StatusSpec(
        "Approved", "0969da", "Accepted for implementation in the routed target.", ("reason",)
    ),
    "Integrating": StatusSpec(
        "Integrating", "d4a72c", "Implementation is in progress in the target.", ("reason",)
    ),
    "Integrated": StatusSpec(
        "Integrated", "1a7f37", "Shipped in the target; the evidence names the ADR or commit.",
        ("reason", "evidence"),
    ),
    "Deferred": StatusSpec(
        "Deferred", "8250df", "Deliberately parked until a named condition holds.", ("reason",)
    ),
    "Blocked": StatusSpec(
        "Blocked", "24292f",
        "Deferred twice; closed permanently and never reviewed again.",
        ("reason", "decided_by"),
    ),
    "Rejected": StatusSpec(
        "Rejected", "cf222e", "Declined on second analysis; the reason records why.",
        ("reason", "decided_by"),
    ),
    "Superseded": StatusSpec(
        "Superseded", "57606a", "Replaced by another idea in this register.", ("superseded_by",)
    ),
}

@dataclasses.dataclass(frozen=True)
class TagSpec:
    """One analysis tag: what it asserts and whether it competes with other verification tags."""

    meaning: str
    verification: bool = False


# Tags describe the analysis, not the decision: status says what we do with an idea, tags say
# how far to trust it. At most one verification tag applies; `unverified` is the implicit default.
TAG_SPECS: dict[str, TagSpec] = {
    "verified": TagSpec("The mechanism and its claims were checked against the source or a running probe.", True),
    "unverified": TagSpec("Taken from the analysis as written; nothing independently checked (default).", True),
    "disputed": TagSpec("A second look contradicts a claim; read the reason before routing.", True),
    "duplicate": TagSpec("Overlaps another idea or an existing capability in the target."),
    "stale": TagSpec("The source repository changed since the analysis; re-review before trusting."),
    "deep-checked": TagSpec(
        "A deep second pass checked the routed project's files, symbols and implementation "
        "contract, not only the source dossier.", True,
    ),
    "target-checked": TagSpec(
        "Files, symbols and contracts the blueprint names were checked in the routed project; "
        "claims about the source repository were not re-checked."
    ),
    "revised": TagSpec("A second review corrected this idea; the dossier's Second Review section says how."),
}
UNVERIFIED_TAG = "unverified"

# The register's own vocabulary for the two scoring columns, so a typo cannot quietly
# become a third value that sorts differently in the matrix.
IMPACT_VALUES = ("High", "Med-High", "Med", "Med-Low", "Low")
EFFORT_VALUES = ("High", "Med", "Low")
MAX_CONCEPT_CHARS = 300

# Review kinds describe the source project, not the analysis topic. Existing records
# predate the field and are treated as `unspecified`.
REPO_KINDS = ("framework", "tool", "awesome-list", "survey", "unspecified")
DEFAULT_REPO_KIND = "unspecified"

# A Source line is required for ideas registered from this number onward. Existing
# sections keep their historical shape; new sections must say where the idea came from.
SOURCE_REQUIRED_FROM = 632

# The cheap alternative to a full revision log: every mutable decision field records
# a before/after entry in the existing history list.
HISTORY_FIELDS = ("target", "tags")


class RegistryError(ValueError):
    """A registry write was refused because the result would be invalid."""


@dataclasses.dataclass(frozen=True)
class DossierSection:
    """One idea section's routing metadata, including its optional source locator."""

    title: str
    target: str | None
    source: str


@dataclasses.dataclass(frozen=True)
class DossierEntry:
    """A dossier section joined with the dossier path that declares it."""

    path: str
    title: str
    target: str | None
    source: str


# ---------------------------------------------------------------------------
# Loading and writing
# ---------------------------------------------------------------------------

def load_json(path: Path) -> dict[str, Any]:
    """Read one registry file, refusing a missing or non-object document by name."""
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except FileNotFoundError as error:
        raise RegistryError(f"{path.name} is missing; the register needs it in the project root") from error
    except json.JSONDecodeError as error:
        raise RegistryError(f"{path.name} is not valid JSON (line {error.lineno}, column {error.colno})") from error
    if not isinstance(payload, dict):
        raise RegistryError(f"{path.name} must hold a JSON object, not a {type(payload).__name__}")
    return payload


def write_text_atomic(path: Path, text: str) -> None:
    """Write atomically: temp file in the same directory, fsync, then replace."""
    fd, tmp = tempfile.mkstemp(prefix=path.name + ".", suffix=".tmp", dir=str(path.parent))
    try:
        with os.fdopen(fd, "w", encoding="utf-8", newline="\n") as handle:
            handle.write(text)
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(tmp, path)
    finally:
        if os.path.exists(tmp):
            os.unlink(tmp)


def write_json(path: Path, payload: dict[str, Any]) -> None:
    """Write one registry JSON document atomically."""
    write_text_atomic(path, json.dumps(payload, indent=2, ensure_ascii=False) + "\n")


def load_targets(root: Path = ROOT) -> list[dict[str, Any]]:
    payload = load_json(root / TARGETS_FILE)
    return list(payload.get("targets", []))


class LockBusy(RuntimeError):
    """Another process holds the registry lock and the wait timed out."""


@contextlib.contextmanager
def file_lock(path: Path, *, timeout: float | None = 30.0):
    """Hold an exclusive cross-process lock on ``path`` for the ``with`` block.

    POSIX uses ``flock`` and Windows uses ``msvcrt.locking`` on a one-byte range,
    so two processes (or two threads with separate handles) serialise without a
    shared server. ``timeout=None`` blocks until the holder releases; a short
    timeout raises ``LockBusy`` instead of hanging a busy CLI. The handle lives
    inside this context manager, so it is always closed.
    """
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, "a+b") as handle:
        handle.seek(0, os.SEEK_END)
        if handle.tell() == 0:
            handle.write(b"\0")
            handle.flush()
        deadline = None if timeout is None else time.monotonic() + timeout
        while True:
            try:
                handle.seek(0)
                if os.name == "nt":
                    import msvcrt

                    msvcrt.locking(handle.fileno(), msvcrt.LK_NBLCK, 1)
                else:
                    import fcntl

                    fcntl.flock(handle.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
                break
            except OSError as error:
                if deadline is not None and time.monotonic() >= deadline:
                    raise LockBusy(
                        f"another Idea Catcher process holds {path.name}; retry when it finishes"
                    ) from error
                time.sleep(0.02)
        try:
            yield
        finally:
            handle.seek(0)
            if os.name == "nt":
                import msvcrt

                msvcrt.locking(handle.fileno(), msvcrt.LK_UNLCK, 1)
            else:
                import fcntl

                fcntl.flock(handle.fileno(), fcntl.LOCK_UN)


@contextlib.contextmanager
def registry_lock(root: Path = ROOT, *, timeout: float | None = 30.0):
    """Serialise one read-modify-write cycle over the registry.

    Every writer re-reads its inputs *after* taking this lock, so a concurrent
    analysis cannot overwrite another one's idea, target or decision.
    """
    with file_lock(root / LOCK_FILE, timeout=timeout):
        yield


def now_iso() -> str:
    """UTC timestamp with second precision; injectable in tests via ``now`` args."""
    return datetime.datetime.now(datetime.timezone.utc).replace(microsecond=0).isoformat()


def load_reviews(root: Path = ROOT) -> dict[str, Any]:
    path = root / REVIEWS_FILE
    if not path.exists():
        return {"schema": SCHEMA, "reviews": [], "repos": {}}
    return load_json(path)


def empty_reviews() -> dict[str, Any]:
    return {"schema": SCHEMA, "reviews": [], "repos": {}}


def target_ids(targets: list[dict[str, Any]]) -> list[str]:
    return [str(target.get("id", "")) for target in targets]


def load_ideas(root: Path = ROOT) -> dict[str, Any]:
    return load_json(root / IDEAS_FILE)


# ---------------------------------------------------------------------------
# Dossiers
# ---------------------------------------------------------------------------

def parse_dossier_sections(text: str) -> dict[str, DossierSection]:
    """Map every ``### `IDEA-NNN`: Title`` heading (three or more digits) to its metadata."""
    sections: dict[str, DossierSection] = {}
    matches = list(DOSSIER_HEADING_RE.finditer(text))
    for index, match in enumerate(matches):
        end = matches[index + 1].start() if index + 1 < len(matches) else len(text)
        section = text[match.start():end]
        target = DOSSIER_TARGET_RE.search(section)
        source = DOSSIER_SOURCE_RE.search(section)
        sections[match.group(1)] = DossierSection(
            title=match.group(2).strip(),
            target=target.group(1) if target else None,
            source=source.group(1).strip() if source else "",
        )
    return sections


def parse_dossier_ideas(text: str) -> dict[str, tuple[str, str | None]]:
    """Map every heading to (title, declared target); kept for narrow callers."""
    return {
        idea_id: (section.title, section.target)
        for idea_id, section in parse_dossier_sections(text).items()
    }


def dossier_sources(root: Path = ROOT) -> dict[str, tuple[str, str | None]]:
    """Map idea id -> (dossier relative path, target declared in that dossier)."""
    found: dict[str, tuple[str, str | None]] = {}
    for path in sorted((root / "dossiers").glob("*.md")):
        if path.name == "TEMPLATE.md":
            continue
        for idea_id, section in parse_dossier_sections(path.read_text(encoding="utf-8")).items():
            found[idea_id] = (f"dossiers/{path.name}", section.target)
    return found


def dossier_duplicates(root: Path = ROOT) -> dict[str, list[str]]:
    """Map every idea id declared in more than one dossier to those dossiers."""
    claims: dict[str, list[str]] = {}
    for path in sorted((root / "dossiers").glob("*.md")):
        if path.name == "TEMPLATE.md":
            continue
        for idea_id in parse_dossier_sections(path.read_text(encoding="utf-8")):
            claims.setdefault(idea_id, []).append(f"dossiers/{path.name}")
    return {idea_id: paths for idea_id, paths in claims.items() if len(paths) > 1}


def dossier_catalog(root: Path = ROOT) -> dict[str, DossierEntry]:
    """Map idea id -> dossier path, title, declared target and source locator."""
    found: dict[str, DossierEntry] = {}
    for path in sorted((root / "dossiers").glob("*.md")):
        if path.name == "TEMPLATE.md":
            continue
        for idea_id, section in parse_dossier_sections(path.read_text(encoding="utf-8")).items():
            found[idea_id] = DossierEntry(
                path=f"dossiers/{path.name}",
                title=section.title,
                target=section.target,
                source=section.source,
            )
    return found


# ---------------------------------------------------------------------------
# Validation
# ---------------------------------------------------------------------------

def validate_targets(targets: list[dict[str, Any]]) -> list[str]:
    errors: list[str] = []
    if not targets:
        return ["targets.json declares no targets"]
    seen: set[str] = set()
    for index, target in enumerate(targets):
        where = f"targets[{index}]"
        if not isinstance(target, dict):
            errors.append(f"{where} is not an object")
            continue
        tid = str(target.get("id", ""))
        if not TARGET_ID_RE.match(tid):
            errors.append(f"{where} id {tid!r} is not lowercase kebab-case")
        if tid in seen:
            errors.append(f"target id {tid!r} is declared twice")
        seen.add(tid)
        for field in ("name", "path", "stack", "gate", "fit", "added"):
            if not str(target.get(field, "")).strip():
                errors.append(f"target {tid or where} has an empty {field}")
        added = str(target.get("added", ""))
        if added and not re.match(r"^\d{4}-\d{2}-\d{2}$", added):
            errors.append(f"target {tid} added {added!r} is not YYYY-MM-DD")
    if "aikit" not in seen:
        errors.append("targets.json must declare the 'aikit' framework target")
    return errors


def validate_idea(idea: dict[str, Any], targets: list[str], sources: dict[str, tuple[str, str | None]]) -> list[str]:
    errors: list[str] = []
    idea_id = str(idea.get("id", ""))
    match = IDEA_ID_RE.match(idea_id)
    if not match:
        return [f"idea id {idea_id!r} is not IDEA-NNN"]
    if idea_id not in sources:
        errors.append(f"{idea_id}: no dossier section declares this idea")
    if not str(idea.get("concept", "")).strip():
        errors.append(f"{idea_id}: concept is empty")
    concept = str(idea.get("concept", ""))
    if "\n" in concept or "\r" in concept:
        errors.append(f"{idea_id}: concept must be one line so it can render in a table row")
    if len(concept) > MAX_CONCEPT_CHARS:
        errors.append(f"{idea_id}: concept is {len(concept)} characters; the cap is {MAX_CONCEPT_CHARS}")
    target = str(idea.get("target", ""))
    if target not in targets:
        errors.append(f"{idea_id}: target {target!r} is not declared in targets.json")
    for field, allowed in (("impact", IMPACT_VALUES), ("effort", EFFORT_VALUES)):
        value = str(idea.get(field, "")).strip()
        if not value:
            errors.append(f"{idea_id}: {field} is empty")
        elif value not in allowed:
            errors.append(f"{idea_id}: {field} {value!r} is not one of {', '.join(allowed)}")
    dossier = str(idea.get("dossier", ""))
    if idea_id in sources and dossier != sources[idea_id][0]:
        errors.append(f"{idea_id}: dossier {dossier!r} is not {sources[idea_id][0]!r}")
    declared = sources.get(idea_id, (None, None))[1]
    retargeted = str(idea.get("retargeted_from", "") or "")
    if declared and declared != target:
        if not retargeted:
            errors.append(
                f"{idea_id}: routed to {target!r} but its dossier says {declared!r}; "
                "record retargeted_from with a reason"
            )
        elif retargeted != declared:
            errors.append(
                f"{idea_id}: retargeted_from {retargeted!r} does not match the dossier target {declared!r}"
            )
        if not str(idea.get("reason", "")).strip():
            errors.append(f"{idea_id}: a retarget needs a reason")
    errors.extend(validate_tags(idea_id, idea.get("tags")))
    status = str(idea.get("status", ""))
    spec = STATUS_SPECS.get(status)
    if spec is None:
        errors.append(f"{idea_id}: unknown status {status!r}")
        return errors
    for required in spec.requires:
        value = str(idea.get(required, "") or "")
        if not value.strip():
            errors.append(f"{idea_id}: status {status} requires {required}")
        elif required == "reason" and len(value.strip()) < MIN_REASON_CHARS:
            errors.append(f"{idea_id}: reason is shorter than {MIN_REASON_CHARS} characters")
    if status != "Proposed" and not str(idea.get("decided_at", "") or "").strip():
        errors.append(f"{idea_id}: status {status} requires decided_at")
    if status == BLOCKED_STATUS and deferral_count(idea) < DEFERRAL_LIMIT:
        errors.append(
            f"{idea_id}: status Blocked requires at least {DEFERRAL_LIMIT} deferral review(s)"
        )
    review_log = idea.get("review_log")
    if review_log is not None:
        if not isinstance(review_log, list):
            errors.append(f"{idea_id}: review_log must be a list")
        else:
            for entry in review_log:
                if not isinstance(entry, dict):
                    errors.append(f"{idea_id}: review_log entries must be objects")
                    continue
                if str(entry.get("verdict", "")) not in REVIEW_VERDICTS:
                    errors.append(
                        f"{idea_id}: review_log verdict {entry.get('verdict')!r} is not one of "
                        f"{', '.join(REVIEW_VERDICTS)}"
                    )
                if not re.match(r"^\d{4}-\d{2}-\d{2}$", str(entry.get("at", ""))):
                    errors.append(f"{idea_id}: review_log entry needs an ISO date in 'at'")
                for field in ("by", "evidence"):
                    if not str(entry.get(field, "") or "").strip():
                        errors.append(f"{idea_id}: review_log entry needs {field}")
                for field in ("files", "commands"):
                    value = entry.get(field)
                    if value is not None and not (
                        isinstance(value, list) and all(isinstance(item, str) for item in value)
                    ):
                        errors.append(f"{idea_id}: review_log {field} must be a list of strings")
    if status == "Superseded":
        replacement = str(idea.get("superseded_by", "") or "")
        if replacement and replacement not in sources:
            errors.append(f"{idea_id}: superseded_by {replacement!r} does not exist")
    for entry in idea.get("history", []) or []:
        if not isinstance(entry, dict):
            errors.append(f"{idea_id}: history entries must be objects")
            continue
        field = entry.get("field")
        if field is not None:
            if field not in HISTORY_FIELDS:
                errors.append(
                    f"{idea_id}: history field {field!r} is not one of {', '.join(HISTORY_FIELDS)}"
                )
        elif str(entry.get("status", "")) not in STATUS_SPECS:
            errors.append(f"{idea_id}: history entry has unknown status {entry.get('status')!r}")
        if not re.match(r"^\d{4}-\d{2}-\d{2}$", str(entry.get("at", ""))):
            errors.append(f"{idea_id}: history entry needs an ISO date in 'at'")
    return errors


def validate_tags(idea_id: str, tags: Any) -> list[str]:
    """Refuse unknown or repeated tags and more than one verification tag."""
    if tags is None:
        return []
    if not isinstance(tags, list):
        return [f"{idea_id}: tags must be a list"]
    errors: list[str] = []
    seen: set[str] = set()
    for tag in tags:
        if tag not in TAG_SPECS:
            errors.append(f"{idea_id}: unknown tag {tag!r}; allowed: {', '.join(TAG_SPECS)}")
        elif tag in seen:
            errors.append(f"{idea_id}: tag {tag!r} repeats")
        seen.add(str(tag))
    if sum(1 for tag in seen if tag in TAG_SPECS and TAG_SPECS[tag].verification) > 1:
        errors.append(f"{idea_id}: at most one verification tag may apply")
    return errors


def effective_tags(idea: Mapping[str, Any]) -> list[str]:
    """Stored tags, the implicit `unverified` default, and the decision status once one is made."""
    tags = [str(tag) for tag in idea.get("tags", []) or []]
    if not any(tag in TAG_SPECS and TAG_SPECS[tag].verification for tag in tags):
        tags.insert(0, UNVERIFIED_TAG)
    status = str(idea.get("status", "Proposed"))
    if status != "Proposed":
        tags.append(status.lower())
    return tags


def deferral_count(idea: Mapping[str, Any]) -> int:
    """How many times a review has deferred this idea.

    A deferral is a ``review_log`` verdict of ``defer``. Legacy rows without a review log fall
    back to their status history so the two-deferral rule applies to data written before the
    review log existed. A current Deferred status with no recorded history counts as one.
    """
    logged = sum(
        1 for entry in idea.get("review_log", []) or []
        if isinstance(entry, dict) and entry.get("verdict") == "defer"
    )
    history = sum(
        1 for entry in idea.get("history", []) or []
        if isinstance(entry, dict) and entry.get("status") == "Deferred"
    )
    current = 1 if idea.get("status") == "Deferred" else 0
    return max(logged, history, current)


def idea_number(idea_id: str) -> int | None:
    match = IDEA_ID_RE.match(idea_id)
    return int(match.group(1)) if match else None


def reserved_ids(reviews: Mapping[str, Any] | None) -> dict[int, int]:
    """Map every reserved idea number to the review that holds it.

    Only an *active* review holds a reservation; finishing or abandoning a review
    releases whatever it did not consume.
    """
    held: dict[int, int] = {}
    for review in (reviews or {}).get("reviews", []) or []:
        if review.get("status") != "active":
            continue
        for number in review.get("reserved_ids", []) or []:
            held[int(number)] = int(review["review_id"])
    return held


def free_idea_numbers(count: int, *, payload: Mapping[str, Any], reviews: Mapping[str, Any] | None) -> list[int]:
    """The lowest ``count`` numbers that are neither registered nor reserved."""
    taken = {idea_number(str(idea.get("id", ""))) for idea in payload.get("ideas", [])}
    taken |= set(reserved_ids(reviews))
    taken.discard(None)
    numbers: list[int] = []
    candidate = 1
    while len(numbers) < count:
        if candidate not in taken:
            numbers.append(candidate)
        candidate += 1
    return numbers


def validate_ideas(
    payload: dict[str, Any],
    targets: list[dict[str, Any]],
    root: Path = ROOT,
    reviews: Mapping[str, Any] | None = None,
) -> list[str]:
    errors: list[str] = []
    if payload.get("schema") != SCHEMA:
        errors.append(f"ideas.json schema is {payload.get('schema')!r}; expected {SCHEMA}")
    ids = target_ids(targets)
    sources = dossier_sources(root)
    catalog = dossier_catalog(root)
    for idea_id, paths in sorted(dossier_duplicates(root).items()):
        errors.append(f"{idea_id} is declared in more than one dossier: {', '.join(paths)}")
    ideas = payload.get("ideas", [])
    if not isinstance(ideas, list) or not ideas:
        return errors + ["ideas.json declares no ideas"]
    seen: dict[str, int] = {}
    for idea in ideas:
        if not isinstance(idea, dict):
            errors.append("ideas contains a non-object entry")
            continue
        idea_id = str(idea.get("id", ""))
        seen[idea_id] = seen.get(idea_id, 0) + 1
        errors.extend(validate_idea(idea, ids, sources))
        entry = catalog.get(idea_id)
        number = idea_number(idea_id)
        if (
            entry is not None
            and number is not None
            and number >= SOURCE_REQUIRED_FROM
            and not entry.source.strip()
        ):
            errors.append(
                f"{idea_id}: needs a '- **Source**:' line in {entry.path}; "
                f"ideas from IDEA-{SOURCE_REQUIRED_FROM:03d} onward must name their source"
            )
    for idea_id, count in seen.items():
        if count > 1:
            errors.append(f"{idea_id} appears {count} times")
    numbers = sorted(int(IDEA_ID_RE.match(i).group(1)) for i in seen if IDEA_ID_RE.match(i))
    held = reserved_ids(reviews)
    if numbers:
        if numbers[0] != 1:
            errors.append(f"idea numbering starts at {numbers[0]}, not 1")
        missing = sorted(set(range(1, numbers[-1] + 1)) - set(numbers))
        # A gap is legal only while a live review has reserved the number: that is how two
        # sessions can write dossiers in parallel without planning the same ids.
        unexplained = [number for number in missing if number not in held]
        if unexplained:
            errors.append(f"idea numbering has gaps at {unexplained} with no reservation")
    for number in sorted(held):
        if f"IDEA-{number:03d}" in seen:
            errors.append(
                f"IDEA-{number:03d} is both registered and reserved by review {held[number]}"
            )
    for idea_id in sources:
        if idea_id in seen:
            continue
        number = idea_number(idea_id)
        if number is not None and number in held:
            # A dossier may be written ahead of registration; the reservation makes that legal.
            continue
        errors.append(f"{idea_id} is declared in {sources[idea_id][0]} but missing from ideas.json")
    return errors


# ---------------------------------------------------------------------------
# Rendering
# ---------------------------------------------------------------------------

def badge(status: str) -> str:
    """Shields.io badge for one status; the alt text carries the decision state."""
    spec = STATUS_SPECS[status]
    url = f"https://img.shields.io/badge/idea-{spec.label}-{spec.color}"
    return f"![{spec.label}]({url})"


def _cell(value: object) -> str:
    text = str(value if value is not None else "").strip()
    return text.replace("|", "\\|") if text else "—"


def _status_counts(ideas: list[dict[str, Any]]) -> str:
    counts = {status: 0 for status in STATUS_SPECS}
    for idea in ideas:
        counts[str(idea.get("status", "Proposed"))] = counts.get(str(idea.get("status", "Proposed")), 0) + 1
    parts = [f"{counts[status]} {status}" for status in STATUS_SPECS if counts.get(status)]
    return " · ".join(parts)


def render_matrix(
    targets: list[dict[str, Any]],
    payload: dict[str, Any],
    reviews: Mapping[str, Any] | None = None,
) -> str:
    ideas = payload.get("ideas", [])
    review_payload = dict(reviews) if reviews else empty_reviews()
    rows = review_rows(review_payload)
    lines: list[str] = [
        "# Cross-Project Integration Backlog & Synthesis Matrix",
        "",
        "**Generated file.** This register is rendered from [`ideas.json`](ideas.json), "
        "[`targets.json`](targets.json) and [`reviews.json`](reviews.json). Edit those inputs, then run "
        "`python aikit.py idea-catcher render`; `render --check` fails when the committed copy drifts.",
        "",
        f"{len(ideas)} ideas · {len(targets)} routing targets · {_status_counts(ideas)}",
        "",
        "## 🎯 Target Ecosystem Reference",
        "",
        "| Target | Workspace Path | Stack & Constraints | Gate Command | Route here when |",
        "|---|---|---|---|---|",
    ]
    for target in targets:
        lines.append(
            "| **{name}** (`{id}`) | `{path}` | {stack} | `{gate}` | {fit} |".format(
                name=_cell(target.get("name")),
                id=_cell(target.get("id")),
                path=_cell(target.get("path")),
                stack=_cell(target.get("stack")),
                gate=_cell(target.get("gate")),
                fit=_cell(target.get("fit")),
            )
        )
    lines += [
        "",
        "## 🏷️ Status Vocabulary",
        "",
        "A decision is never implicit: every status other than `Proposed` must record why in "
        "`ideas.json`, and the table below is the complete vocabulary.",
        "",
        "| Status | Badge | Meaning | Recorded decision requires |",
        "|---|---|---|---|",
    ]
    for status, spec in STATUS_SPECS.items():
        requires = ", ".join(f"`{field}`" for field in spec.requires) or "—"
        lines.append(f"| `{status}` | {badge(status)} | {_cell(spec.meaning)} | {requires} |")
    lines += [
        "",
        "## 🔖 Tag Vocabulary",
        "",
        "Tags record how far an analysis can be trusted and sit next to the status, never instead of "
        "it. A decided status also shows as a lowercase tag, and an idea with no verification tag is "
        "`unverified`. Set them with `python aikit.py idea-catcher tag IDEA-NNN --add verified`.",
        "",
        "| Tag | Kind | Meaning |",
        "|---|---|---|",
    ]
    for tag, tag_spec in TAG_SPECS.items():
        kind = "verification (one at most)" if tag_spec.verification else "flag"
        lines.append(f"| `{tag}` | {kind} | {_cell(tag_spec.meaning)} |")
    lines += [
        "",
        "## 🗂️ Repository Review Ledger",
        "",
        "How many times each repository has been analyzed, in review order, and whether an analysis "
        "is running right now. Claim with `review-start`, close with `review-finish`; a claim holds a "
        "lease, so a crashed analysis goes stale instead of blocking forever.",
        "",
    ]
    if rows:
        active_now = sum(1 for row in rows if row["state"] == "active")
        finished = sum(int(row["review_count"] or 0) for row in rows)
        lines += [
            f"{len(rows)} repositories · {finished} finished reviews · {active_now} active now",
            "",
            "| Review Order | Repository | Kind | Reviews | Last Reviewed | State | Dossier |",
            "|---|---|---|---|---|---|---|",
        ]
        for row in rows:
            order = f"#{row['order']}" if row["order"] else "—"
            held = row.get("reserved") or []
            if row["state"] == "active":
                state = f"**active** (review {row['active_review_id']} until `{row['lease_until']}`)"
                if held:
                    state += f", holds IDEA-{held[0]:03d}..IDEA-{held[-1]:03d}"
            elif row["state"] == "stale":
                state = f"stale (review {row['active_review_id']} lease expired `{row['lease_until']}`)"
            else:
                state = "idle"
            dossier = str(row.get("dossier") or "")
            lines.append(
                "| {order} | `{slug}` | {kind} | {count} | {last} | {state} | {dossier} |".format(
                    order=order,
                    slug=_cell(row["slug"]),
                    kind=_cell(row.get("kind", DEFAULT_REPO_KIND)),
                    count=_cell(row.get("review_count", 0)),
                    last=_cell(row.get("last_reviewed_at") or "—"),
                    state=state,
                    dossier=f"[`{dossier}`]({dossier})" if dossier else "—",
                )
            )
    else:
        lines.append("_No repository reviews recorded yet._")
    lines += [
        "",
        "## 📋 Master Idea Register",
        "",
        "| Idea ID | Source Dossier | Concept | Target Project | Impact / Effort | Status | Tags | Rationale | Evidence |",
        "|---|---|---|---|---|---|---|---|---|",
    ]
    for idea in ideas:
        status = str(idea.get("status", "Proposed"))
        dossier = str(idea.get("dossier", ""))
        dossier_cell = f"[`{dossier}`]({dossier})" if dossier else "—"
        target = str(idea.get("target", ""))
        target_cell = f"`{target}`"
        retargeted = str(idea.get("retargeted_from", "") or "")
        if retargeted:
            target_cell += f" (from `{retargeted}`)"
        lines.append(
            "| `{id}` | {dossier} | {concept} | {target} | {impact} / {effort} | {status} | {tags} | "
            "{reason} | {evidence} |".format(
                id=_cell(idea.get("id")),
                tags=" ".join(f"`{tag}`" for tag in effective_tags(idea)),
                dossier=dossier_cell,
                concept=_cell(idea.get("concept")),
                target=target_cell,
                impact=_cell(idea.get("impact")),
                effort=_cell(idea.get("effort")),
                status=badge(status) if status in STATUS_SPECS else _cell(status),
                reason=_cell(idea.get("reason")),
                evidence=_cell(idea.get("evidence")),
            )
        )
    lines.append("")
    return "\n".join(lines)


def matrix_matches(
    root: Path,
    targets: list[dict[str, Any]],
    payload: dict[str, Any],
    reviews: Mapping[str, Any] | None = None,
) -> tuple[bool, str]:
    expected = render_matrix(targets, payload, reviews)
    path = root / MATRIX_FILE
    if not path.is_file():
        return False, f"{MATRIX_FILE} does not exist"
    actual = path.read_text(encoding="utf-8").replace("\r\n", "\n")
    if actual == expected:
        return True, ""
    actual_rows = MATRIX_ROW_RE.findall(actual)
    expected_rows = MATRIX_ROW_RE.findall(expected)
    if len(actual_rows) != len(expected_rows):
        return False, f"{MATRIX_FILE} lists {len(actual_rows)} ideas; the register has {len(expected_rows)}"
    return False, f"{MATRIX_FILE} is stale; run `python aikit.py idea-catcher render`"


def write_matrix(
    root: Path,
    targets: list[dict[str, Any]],
    payload: dict[str, Any],
    reviews: Mapping[str, Any] | None = None,
) -> Path:
    """Render the matrix from already-loaded inputs and replace it atomically."""
    text = render_matrix(targets, payload, reviews)
    path = root / MATRIX_FILE
    with registry_lock(root):
        write_text_atomic(path, text)
    return path


def render_to_disk(root: Path = ROOT) -> Path:
    """Refresh ``MATRIX.md`` from the register's three source documents."""
    return write_matrix(root, load_targets(root), load_ideas(root), load_reviews(root))


# ---------------------------------------------------------------------------
# Writes
# ---------------------------------------------------------------------------

def add_target(root: Path, *, target: dict[str, Any], require_path: bool = True) -> list[dict[str, Any]]:
    if require_path:
        resolved = (root / str(target["path"])).resolve()
        if not resolved.is_dir():
            raise RegistryError(
                f"target path {target['path']!r} does not resolve to a directory from {root}; "
                "pass --allow-missing-path to register a planned target"
            )
    with registry_lock(root):
        payload = load_json(root / TARGETS_FILE)
        targets = list(payload.get("targets", []))
        if any(item.get("id") == target["id"] for item in targets):
            raise RegistryError(f"target {target['id']!r} already exists")
        targets.append(target)
        errors = validate_targets(targets)
        if errors:
            raise RegistryError("; ".join(errors))
        payload["targets"] = targets
        write_json(root / TARGETS_FILE, payload)
    return targets


def add_idea(
    root: Path,
    *,
    dossier: str,
    target: str,
    impact: str,
    effort: str,
    idea_id: str = "",
    concept: str = "",
    review_id: int | None = None,
) -> dict[str, Any]:
    """Register a dossier section as an idea, taking the title from the heading.

    The whole read-modify-write runs under the registry lock, so two analyses
    registering ideas at the same time cannot pick the same id or drop each
    other's row. When ``review_id`` is given the id must be one that review
    reserved, which is what keeps two parallel dossiers from claiming the same
    number.
    """
    with registry_lock(root):
        catalog = dossier_catalog(root)
        payload = load_ideas(root)
        reviews = load_reviews(root)
        ideas = list(payload.get("ideas", []))
        existing = {str(idea.get("id", "")) for idea in ideas}
        held = reserved_ids(reviews)
        review = None
        if review_id is not None:
            review = next(
                (item for item in reviews.get("reviews", []) if item.get("review_id") == review_id), None
            )
            if review is None:
                raise RegistryError(f"review {review_id} does not exist")
            if review.get("status") != "active":
                raise RegistryError(f"review {review_id} is {review.get('status')}; reservations belong to active reviews")
            mine = sorted(int(number) for number in review.get("reserved_ids", []) or [])
        else:
            mine = []
        if review_id is not None and not mine:
            raise RegistryError(
                f"review {review_id} holds no reserved ids; start a review with --reserve N"
            )
        if not idea_id:
            if review_id is not None:
                idea_id = f"IDEA-{mine[0]:03d}"
            else:
                idea_id = f"IDEA-{free_idea_numbers(1, payload=payload, reviews=reviews)[0]:03d}"
        number = idea_number(idea_id)
        if idea_id in existing:
            # A crash between writing ideas.json and releasing the reservation leaves the id both
            # registered and reserved. Re-running the same registration heals it instead of
            # failing, but only for the review that reserved it.
            same = next(item for item in ideas if item.get("id") == idea_id)
            consumed = [int(n) for n in review.get("consumed_ids", []) or []] if review else []
            if (
                review is not None
                and number is not None
                and number in consumed
                and same.get("dossier") == dossier
            ):
                if number in mine:
                    review["reserved_ids"] = [n for n in mine if n != number]
                reviews["reviews"] = [
                    review if item.get("review_id") == review_id else item
                    for item in reviews.get("reviews", [])
                ]
                write_json(root / REVIEWS_FILE, reviews)
                return dict(same)
            raise RegistryError(f"{idea_id} already exists")
        holder = held.get(number) if number is not None else None
        if holder is not None and holder != review_id:
            raise RegistryError(
                f"{idea_id} is reserved by review {holder}; use an id from your own reservation "
                f"(start a review with --reserve N) or wait for that review to finish"
            )
        if review_id is not None and number is not None and number not in mine:
            raise RegistryError(
                f"{idea_id} is not in review {review_id}'s reservation "
                f"({', '.join(f'IDEA-{n:03d}' for n in mine) or 'empty'}); "
                "reserve the numbers before writing the dossier"
            )
        if idea_id not in catalog:
            raise RegistryError(f"{dossier} has no '### `{idea_id}`: <title>' section")
        entry = catalog[idea_id]
        if entry.path != dossier:
            raise RegistryError(f"{idea_id} lives in {entry.path}, not {dossier}")
        if entry.target and entry.target != target:
            raise RegistryError(
                f"{idea_id} declares target {entry.target!r} in {dossier}; route it there or retarget the dossier first"
            )
        if number is not None and number >= SOURCE_REQUIRED_FROM and not entry.source.strip():
            raise RegistryError(
                f"{idea_id} needs a '- **Source**: <path or repo-level> — <why>' line in {dossier}; "
                f"ideas from IDEA-{SOURCE_REQUIRED_FROM:03d} onward must name their source"
            )
        idea: dict[str, Any] = {
            "id": idea_id,
            "dossier": dossier,
            "concept": concept.strip() or entry.title,
            "target": target,
            "impact": impact,
            "effort": effort,
            "status": "Proposed",
            "reason": "",
            "decided_at": "",
            "decided_by": "",
            "evidence": "",
        }
        errors = validate_idea(
            idea,
            target_ids(load_targets(root)),
            {key: (value.path, value.target) for key, value in catalog.items()},
        )
        if errors:
            raise RegistryError("; ".join(errors))
        ideas.append(idea)
        payload["ideas"] = ideas
        write_json(root / IDEAS_FILE, payload)
        if review is not None and number is not None and number in mine:
            review["reserved_ids"] = [n for n in mine if n != number]
            review["consumed_ids"] = sorted(set(list(review.get("consumed_ids", []) or []) + [number]))
            reviews["reviews"] = [
                review if item.get("review_id") == review_id else item
                for item in reviews.get("reviews", [])
            ]
            write_json(root / REVIEWS_FILE, reviews)
        return idea


def _history_entry(
    *, field: str, before: Any, after: Any, by: str, at: str, reason: str = ""
) -> dict[str, Any]:
    entry: dict[str, Any] = {"field": field, "from": before, "to": after, "at": at, "by": by}
    if reason:
        entry["reason"] = reason
    return entry


def set_tags(
    root: Path,
    idea_id: str,
    *,
    add: Sequence[str] = (),
    remove: Sequence[str] = (),
    by: str = "",
    reason: str = "",
) -> dict[str, Any]:
    """Add and remove analysis tags; a new verification tag replaces the previous one."""
    with registry_lock(root):
        payload = load_ideas(root)
        targets = load_targets(root)
        ideas = list(payload.get("ideas", []))
        position = next((i for i, idea in enumerate(ideas) if idea.get("id") == idea_id), None)
        if position is None:
            raise RegistryError(f"{idea_id} is not in the register")
        idea = dict(ideas[position])
        before = [str(tag) for tag in idea.get("tags", []) or []]
        tags = [tag for tag in before if tag not in remove]
        for tag in add:
            spec = TAG_SPECS.get(tag)
            if spec is not None and spec.verification:
                tags = [kept for kept in tags if not TAG_SPECS.get(kept, TagSpec("")).verification]
            if tag not in tags:
                tags.append(tag)
        if tags:
            idea["tags"] = tags
        else:
            idea.pop("tags", None)
        if tags != before:
            history = list(idea.get("history", []) or [])
            history.append(
                _history_entry(
                    field="tags",
                    before=before,
                    after=tags,
                    by=by,
                    at=datetime.date.today().isoformat(),
                    reason=reason,
                )
            )
            idea["history"] = history
        errors = validate_idea(idea, target_ids(targets), dossier_sources(root))
        if errors:
            raise RegistryError("; ".join(errors))
        ideas[position] = idea
        payload["ideas"] = ideas
        write_json(root / IDEAS_FILE, payload)
        return idea


def _append_history(
    idea: dict[str, Any], status: str, *, at: str, by: str, reason: str
) -> None:
    history = list(idea.get("history", []) or [])
    history.append({"status": status, "at": at, "by": by, "reason": reason})
    idea["history"] = history


def _append_review(
    idea: dict[str, Any],
    *,
    verdict: str,
    evidence: str,
    by: str,
    at: str,
    files: Sequence[str] = (),
    commands: Sequence[str] = (),
    notes: str = "",
) -> None:
    if verdict not in REVIEW_VERDICTS:
        raise RegistryError(f"unknown review verdict {verdict!r}")
    entry: dict[str, Any] = {
        "at": at,
        "by": by or "unidentified",
        "verdict": verdict,
        "files": list(files),
        "commands": list(commands),
        "evidence": evidence.strip(),
    }
    if notes:
        entry["notes"] = notes
    idea["review_log"] = list(idea.get("review_log", []) or []) + [entry]


def _apply_status(
    idea: dict[str, Any],
    *,
    status: str,
    reason: str,
    decided_at: str,
    decided_by: str,
    evidence: str,
    target: str,
    superseded_by: str,
    declared: str | None,
    record_deferral: bool,
    deferrals_before: int,
    new_deferral: bool = False,
) -> str:
    """Apply one decision to a loaded idea; return the effective status.

    A second ``Deferred`` decision is coerced to ``Blocked``. The coercion records the second
    deferral in both the review log and the status history, so an auditor can see why the idea
    will never be reviewed again.
    """
    previous = str(idea.get("status", "Proposed"))
    if previous == BLOCKED_STATUS and status != BLOCKED_STATUS:
        raise RegistryError(
            f"{idea.get('id')} is Blocked after two deferrals and will not be reviewed again"
        )
    at = decided_at or datetime.date.today().isoformat()
    effective_deferrals = deferrals_before + (1 if new_deferral else 0)
    auto_blocked = False
    if status == "Deferred":
        if record_deferral:
            _append_review(
                idea,
                verdict="defer",
                evidence=reason or "Deferred by decision",
                by=decided_by,
                at=at,
            )
        if deferrals_before >= DEFERRAL_LIMIT - 1:
            auto_blocked = True
            status = BLOCKED_STATUS
            _append_history(
                idea, "Deferred", at=at, by=decided_by,
                reason=reason or "Second deferral",
            )
            reason = (
                f"{reason} " if reason else ""
            ) + f"Second deferral; blocked permanently after {effective_deferrals} deferrals."
    if status == BLOCKED_STATUS and effective_deferrals < DEFERRAL_LIMIT:
        raise RegistryError(
            f"{idea.get('id')} cannot be Blocked without {DEFERRAL_LIMIT} deferral reviews"
        )
    if status == BLOCKED_STATUS and new_deferral and deferral_count(idea) < DEFERRAL_LIMIT:
        # Legacy rows record their first deferral only in the status history. The review log
        # entry just written is the second event; mirror it in history so both sources agree.
        _append_history(
            idea, "Deferred", at=at, by=decided_by,
            reason=reason or "Second deferral",
        )
    if status != previous:
        _append_history(idea, status, at=at, by=decided_by, reason=reason)
    idea["status"] = status
    for field, value in (
        ("reason", reason),
        ("decided_at", at),
        ("decided_by", decided_by),
        ("evidence", evidence),
        ("superseded_by", superseded_by),
    ):
        if value:
            idea[field] = value
    if status != "Superseded":
        # A stale replacement pointer on an idea that is no longer superseded would tell a
        # reader to follow a decision that has been reversed.
        idea.pop("superseded_by", None)
    if target and target != idea.get("target"):
        # Bind the re-route to the *dossier's* target, not the current one, so routing back
        # to the original analysis is representable: it simply clears the marker.
        current_target = str(idea.get("target", ""))
        history = list(idea.get("history", []) or [])
        history.append(
            _history_entry(
                field="target",
                before=current_target,
                after=target,
                by=decided_by,
                at=at,
                reason=reason,
            )
        )
        idea["history"] = history
        if declared and target == declared:
            idea.pop("retargeted_from", None)
        else:
            idea["retargeted_from"] = declared or current_target
        idea["target"] = target
    return status


def set_status(
    root: Path,
    idea_id: str,
    *,
    status: str,
    reason: str = "",
    decided_at: str = "",
    decided_by: str = "",
    evidence: str = "",
    target: str = "",
    superseded_by: str = "",
) -> dict[str, Any]:
    with registry_lock(root):
        payload = load_ideas(root)
        targets = load_targets(root)
        ideas = list(payload.get("ideas", []))
        position = next((i for i, idea in enumerate(ideas) if idea.get("id") == idea_id), None)
        if position is None:
            raise RegistryError(f"{idea_id} is not in the register")
        idea = dict(ideas[position])
        sources = dossier_sources(root)
        declared = (sources.get(idea_id) or (None, None))[1]
        deferrals_before = deferral_count(idea)
        _apply_status(
            idea,
            status=status,
            reason=reason,
            decided_at=decided_at,
            decided_by=decided_by,
            evidence=evidence,
            target=target,
            superseded_by=superseded_by,
            declared=declared,
            record_deferral=True,
            deferrals_before=deferrals_before,
            new_deferral=(status == "Deferred"),
        )
        errors = validate_idea(idea, target_ids(targets), sources)
        if errors:
            raise RegistryError("; ".join(errors))
        ideas[position] = idea
        payload["ideas"] = ideas
        write_json(root / IDEAS_FILE, payload)
        return idea


def review_idea(
    root: Path,
    idea_id: str,
    *,
    verdict: str,
    evidence: str,
    by: str = "",
    notes: str = "",
    files: Sequence[str] = (),
    commands: Sequence[str] = (),
    status: str = "",
    reason: str = "",
    decided_at: str = "",
    superseded_by: str = "",
) -> dict[str, Any]:
    """Record one second-pass review and apply its decision.

    A second ``defer`` verdict blocks the idea permanently. A ``Blocked`` idea is refused, which
    is the executable form of "won't be reviewed again".
    """
    if verdict not in REVIEW_VERDICTS:
        raise RegistryError(f"unknown review verdict {verdict!r}")
    if len(evidence.strip()) < MIN_REASON_CHARS:
        raise RegistryError(
            f"a review needs evidence of at least {MIN_REASON_CHARS} characters"
        )
    with registry_lock(root):
        payload = load_ideas(root)
        targets = load_targets(root)
        ideas = list(payload.get("ideas", []))
        position = next((i for i, idea in enumerate(ideas) if idea.get("id") == idea_id), None)
        if position is None:
            raise RegistryError(f"{idea_id} is not in the register")
        idea = dict(ideas[position])
        if idea.get("status") == BLOCKED_STATUS:
            raise RegistryError(
                f"{idea_id} is Blocked after two deferrals and will not be reviewed again"
            )
        sources = dossier_sources(root)
        declared = (sources.get(idea_id) or (None, None))[1]
        before = deferral_count(idea)
        at = decided_at or datetime.date.today().isoformat()
        _append_review(
            idea, verdict=verdict, evidence=evidence, by=by, at=at,
            files=files, commands=commands, notes=notes,
        )
        target_status = status
        if not target_status:
            target_status = {
                "adopt": "Approved",
                "defer": "Deferred",
                "duplicate": "Superseded" if superseded_by else "Rejected",
                "implemented": "Integrated",
                "obsolete": "Rejected",
                "reject": "Rejected",
                "blocked": BLOCKED_STATUS,
                "confirmed": str(idea.get("status", "Proposed")),
            }.get(verdict, str(idea.get("status", "Proposed")))
        if verdict == "defer" and before >= DEFERRAL_LIMIT - 1:
            target_status = BLOCKED_STATUS
        confirmed = verdict == "confirmed"
        _apply_status(
            idea,
            status=target_status,
            reason="" if confirmed else (reason or evidence),
            decided_at=str(idea.get("decided_at", "") or "") if confirmed else at,
            decided_by="" if confirmed else by,
            evidence="" if confirmed else (reason or evidence),
            target="",
            superseded_by=superseded_by,
            declared=declared,
            record_deferral=False,
            deferrals_before=before,
            new_deferral=(verdict == "defer"),
        )
        errors = validate_idea(idea, target_ids(targets), sources)
        if errors:
            raise RegistryError("; ".join(errors))
        ideas[position] = idea
        payload["ideas"] = ideas
        write_json(root / IDEAS_FILE, payload)
        return idea


# ---------------------------------------------------------------------------
# Automatic registration from commit references
# ---------------------------------------------------------------------------

COMMIT_IDEA_RE = re.compile(r"\bIDEA-\d{3,}\b")
COMMIT_RECORD_SEPARATOR = "\x1e"
COMMIT_FIELD_SEPARATOR = "\x1f"
GIT_LOG_TIMEOUT_SECONDS = 30


def parse_idea_ids(message: str) -> List[str]:
    """Every distinct IDEA-NNN token (three or more digits) in one commit message, sorted."""
    return sorted(set(COMMIT_IDEA_RE.findall(message)))


def git_commits(repo_path: Path, limit: int = 200) -> List[Tuple[str, str, str]]:
    """(sha, subject, body) for the newest commits, newest first."""
    try:
        done = subprocess.run(
            ["git", "-C", str(repo_path), "log", f"-n{max(limit, 1)}",
             f"--format=%H{COMMIT_FIELD_SEPARATOR}%s{COMMIT_FIELD_SEPARATOR}"
             f"%b{COMMIT_RECORD_SEPARATOR}"],
            stdin=subprocess.DEVNULL, capture_output=True, text=True, encoding="utf-8",
            errors="replace", timeout=GIT_LOG_TIMEOUT_SECONDS,
        )
    except (OSError, subprocess.SubprocessError) as exc:
        raise ValueError(f"git log failed in {repo_path}: {exc}") from exc
    if done.returncode != 0:
        raise ValueError(f"git log failed in {repo_path}: {done.stderr.strip()}")
    commits: List[Tuple[str, str, str]] = []
    for record in done.stdout.split(COMMIT_RECORD_SEPARATOR):
        record = record.strip("\n")
        if not record:
            continue
        parts = record.split(COMMIT_FIELD_SEPARATOR, 2)
        if len(parts) != 3:
            continue
        commits.append((parts[0].strip(), parts[1].strip(), parts[2]))
    return commits


def register_from_commits(
    root: Path,
    project: str,
    commits: Sequence[Tuple[str, str, str]],
    dry_run: bool = False,
) -> List[dict]:
    """Mark matching ideas Integrated; return one record per change.

    A missing register is an empty one only at :func:`register_from_repo`; an existing but
    unreadable register raises, so ``idea-catcher sync`` reports it instead of claiming there is
    nothing to register. The ``check --push`` caller catches the error and keeps the push green.
    """
    payload = load_ideas(root)
    ideas = {str(idea.get("id", "")): idea for idea in payload.get("ideas", [])
             if isinstance(idea, dict)}
    updated: List[dict] = []
    for sha, subject, body in commits:
        for idea_id in parse_idea_ids(f"{subject}\n{body}"):
            idea = ideas.get(idea_id)
            if idea is None or str(idea.get("target", "")) != project:
                continue
            if idea.get("status") in {"Integrated", "Superseded", "Rejected", BLOCKED_STATUS}:
                continue
            record = {"id": idea_id, "commit": sha, "subject": subject}
            if dry_run:
                updated.append(record)
                continue
            reason = f"Implemented by commit {sha[:12]}: {subject}".strip()
            set_status(
                root, idea_id, status="Integrated", reason=reason,
                decided_by="aikit:auto-register", evidence=f"{sha}; {project}",
            )
            idea["status"] = "Integrated"
            updated.append(record)
    return updated


def register_from_repo(
    repo_path: Path,
    project: str,
    root: Path | None = None,
    limit: int = 200,
    dry_run: bool = False,
) -> List[dict]:
    """Scan one repository's commits and register matching IDEA-NNN references.

    A non-dry-run update also refreshes ``MATRIX.md``, so the generated register never lags the
    status it just recorded. A missing register is still an empty one: a project without Idea
    Catcher data pushes exactly as before. A project with no idea routed to it returns before
    spawning Git, so an ordinary push pays nothing for the feature.
    """
    root = default_root() if root is None else Path(root)
    if not (root / IDEAS_FILE).is_file():
        return []
    payload = load_ideas(root)
    if not any(str(idea.get("target", "")) == project
               for idea in payload.get("ideas", []) if isinstance(idea, dict)):
        return []
    updated = register_from_commits(
        root, project, git_commits(Path(repo_path), limit), dry_run,
    )
    if updated and not dry_run:
        render_to_disk(root)
    return updated


# ---------------------------------------------------------------------------
# Repository review ledger
# ---------------------------------------------------------------------------

REVIEW_STATUSES = ("active", "finished", "abandoned")


def _parse_ts(value: str) -> datetime.datetime:
    try:
        return datetime.datetime.fromisoformat(value)
    except (TypeError, ValueError) as error:
        raise RegistryError(f"timestamp {value!r} is not ISO 8601") from error


def _lease_expired(review: Mapping[str, Any], now: str) -> bool:
    return str(review.get("lease_until", "")) <= now


def validate_reviews(
    payload: Mapping[str, Any],
    root: Path = ROOT,
    *,
    ideas_payload: Mapping[str, Any] | None = None,
) -> list[str]:
    errors: list[str] = []
    if payload.get("schema") != SCHEMA:
        errors.append(f"reviews.json schema is {payload.get('schema')!r}; expected {SCHEMA}")
    reviews = payload.get("reviews", [])
    repos = payload.get("repos", {})
    if not isinstance(reviews, list):
        return errors + ["reviews.json 'reviews' must be a list"]
    if not isinstance(repos, dict):
        return errors + ["reviews.json 'repos' must be an object"]
    ids: list[int] = []
    orders: list[int] = []
    active: dict[str, int] = {}
    counts: dict[str, int] = {}
    last_order: dict[str, int] = {}
    reserved_by: dict[int, int] = {}
    for review in reviews:
        if not isinstance(review, dict):
            errors.append("reviews contains a non-object entry")
            continue
        rid = review.get("review_id")
        if not isinstance(rid, int) or isinstance(rid, bool) or rid < 1:
            errors.append(f"review entry has invalid review_id {rid!r}")
            continue
        ids.append(rid)
        slug = str(review.get("slug", ""))
        if not SLUG_RE.match(slug):
            errors.append(f"review {rid}: slug {slug!r} is not owner/name")
        status = str(review.get("status", ""))
        if status not in REVIEW_STATUSES:
            errors.append(f"review {rid}: unknown status {status!r}")
        kind = review.get("kind")
        if kind is not None and kind not in REPO_KINDS:
            errors.append(f"review {rid}: kind {kind!r} is not one of {', '.join(REPO_KINDS)}")
        for field in ("started_at", "lease_until"):
            if not str(review.get(field, "")).strip():
                errors.append(f"review {rid}: {field} is required")
            else:
                try:
                    _parse_ts(str(review[field]))
                except RegistryError:
                    errors.append(f"review {rid}: {field} is not ISO 8601")
        if status == "active":
            if str(review.get("finished_at", "")).strip():
                errors.append(f"review {rid}: an active review has no finished_at")
            if slug in active:
                errors.append(
                    f"reviews {active[slug]} and {rid} are both active for {slug}; one repo, one analysis"
                )
            active[slug] = rid
        else:
            if not str(review.get("finished_at", "")).strip():
                errors.append(f"review {rid}: status {status} requires finished_at")
            if status == "abandoned" and not str(review.get("closed_reason", "")).strip():
                errors.append(f"review {rid}: an abandoned review requires closed_reason")
        if status == "finished":
            order = review.get("order")
            if not isinstance(order, int) or isinstance(order, bool) or order < 1:
                errors.append(f"review {rid}: a finished review requires a positive integer order")
            else:
                orders.append(order)
                counts[slug] = counts.get(slug, 0) + 1
                last_order[slug] = max(last_order.get(slug, 0), order)
        reserved = review.get("reserved_ids", [])
        if not isinstance(reserved, list):
            errors.append(f"review {rid}: reserved_ids must be a list")
            reserved = []
        elif not all(
            isinstance(number, int) and not isinstance(number, bool) and number >= 1
            for number in reserved
        ):
            errors.append(f"review {rid}: every reserved id must be a positive integer")
            reserved = []
        elif reserved != sorted(set(reserved)):
            errors.append(f"review {rid}: reserved_ids must be sorted and unique")
        for number in reserved:
            holder = reserved_by.get(number)
            if holder is not None and holder != rid:
                errors.append(f"IDEA-{number:03d} is reserved by reviews {holder} and {rid}")
            reserved_by[number] = rid
        if status != "active" and reserved:
            errors.append(f"review {rid}: a {status} review must release its reserved ids")
        dossier = str(review.get("dossier", "") or "")
        if dossier and not (root / dossier).is_file():
            errors.append(f"review {rid}: dossier {dossier!r} does not exist")
        idea_count = review.get("ideas")
        if idea_count is not None and (
            not isinstance(idea_count, int) or isinstance(idea_count, bool) or idea_count < 0
        ):
            errors.append(f"review {rid}: ideas must be a non-negative integer or null")
    if ids:
        if sorted(ids) != list(range(1, max(ids) + 1)):
            errors.append("review ids must be contiguous from 1")
        if len(set(ids)) != len(ids):
            errors.append("review ids must be unique")
    if len(set(orders)) != len(orders):
        errors.append("finished review orders must be unique")
    for slug, entry in repos.items():
        if not isinstance(entry, dict):
            errors.append(f"repos[{slug!r}] must be an object")
            continue
        if not SLUG_RE.match(str(slug)):
            errors.append(f"repos key {slug!r} is not owner/name")
        if entry.get("review_count") != counts.get(slug, 0):
            errors.append(
                f"repos[{slug!r}].review_count is {entry.get('review_count')!r} but "
                f"{counts.get(slug, 0)} finished reviews are recorded"
            )
        expected_order = last_order.get(slug)
        if entry.get("order") != expected_order:
            errors.append(
                f"repos[{slug!r}].order is {entry.get('order')!r} but the last finished order is {expected_order!r}"
            )
    for slug in counts:
        if slug not in repos:
            errors.append(f"{slug} has finished reviews but no repos entry")
    if ideas_payload is not None:
        registered = {str(item.get("id", "")) for item in ideas_payload.get("ideas", []) or []}
        for number, holder in sorted(reserved_by.items()):
            if f"IDEA-{number:03d}" in registered:
                errors.append(
                    f"IDEA-{number:03d} is both registered and reserved by review {holder}"
                )
    return errors


def _release(review: dict[str, Any], now: str, reason: str) -> None:
    """Close a review and drop the idea numbers it had not consumed."""
    review["status"] = "abandoned"
    review["finished_at"] = now
    review["closed_reason"] = reason
    review["reserved_ids"] = []


def release_expired(root: Path, *, now: str = "") -> list[int]:
    """Abandon every active review whose lease has passed and release its ids."""
    now = now or now_iso()
    with registry_lock(root):
        payload = load_reviews(root)
        reviews = list(payload.get("reviews", []))
        released: list[int] = []
        for review in reviews:
            if review.get("status") == "active" and _lease_expired(review, now):
                released.append(int(review["review_id"]))
                _release(review, now, "lease expired")
        if released:
            payload["reviews"] = reviews
            errors = validate_reviews(payload, root)
            if errors:
                raise RegistryError("; ".join(errors))
            write_json(root / REVIEWS_FILE, payload)
        return released


def review_start(
    root: Path,
    *,
    slug: str,
    url: str = "",
    agent: str = "",
    lease_minutes: int = REVIEW_LEASE_MINUTES,
    now: str = "",
    force: bool = False,
    reserve: int = 0,
    kind: str = "",
) -> dict[str, Any]:
    """Claim one repository for analysis and reserve the idea numbers it will use.

    Reserving ids is what makes parallel dossier writing safe: two sessions analyse
    different repositories at the same time, and each already knows the numbers its
    sections will carry, so neither can plan a number the other is about to take.
    """
    if not SLUG_RE.match(slug):
        raise RegistryError(f"--repo {slug!r} must be owner/name (letters, digits, . _ -)")
    if lease_minutes < 1:
        raise RegistryError("--lease-minutes must be at least 1")
    if reserve < 0:
        raise RegistryError("--reserve cannot be negative")
    if kind and kind not in REPO_KINDS:
        raise RegistryError(f"--kind {kind!r} must be one of {', '.join(REPO_KINDS)}")
    kind = kind or DEFAULT_REPO_KIND
    now = now or now_iso()
    with registry_lock(root):
        payload = load_reviews(root)
        reviews = list(payload.get("reviews", []))
        repos = dict(payload.get("repos", {}))
        for review in reviews:
            if review.get("status") != "active":
                continue
            if _lease_expired(review, now):
                _release(review, now, "lease expired")
                continue
            if review.get("slug") != slug:
                continue
            if not force:
                raise RegistryError(
                    f"{slug} is already being reviewed as review {review['review_id']} "
                    f"by {review.get('agent') or 'an unnamed agent'} until {review['lease_until']}; "
                    "wait for it, finish it, or pass --force to take over"
                )
            _release(review, now, "superseded by --force")
        next_id = max((int(item["review_id"]) for item in reviews), default=0) + 1
        reserved = free_idea_numbers(reserve, payload=load_ideas(root), reviews=payload) if reserve else []
        review = {
            "review_id": next_id,
            "slug": slug,
            "url": url,
            "agent": agent,
            "kind": kind,
            "started_at": now,
            "lease_until": _plus_minutes(now, lease_minutes),
            "finished_at": "",
            "status": "active",
            "dossier": "",
            "ideas": None,
            "order": None,
            "closed_reason": "",
            "reserved_ids": reserved,
            "consumed_ids": [],
        }
        reviews.append(review)
        entry = dict(repos.get(slug, {"slug": slug, "url": url, "first_reviewed_at": now,
                                      "last_reviewed_at": "", "review_count": 0, "order": None,
                                      "dossier": "", "kind": kind}))
        entry["kind"] = kind
        if url:
            entry["url"] = url
        repos[slug] = entry
        payload["reviews"] = reviews
        payload["repos"] = repos
        errors = validate_reviews(payload, root)
        if errors:
            raise RegistryError("; ".join(errors))
        write_json(root / REVIEWS_FILE, payload)
        return review


def review_finish(
    root: Path,
    review_id: int,
    *,
    dossier: str = "",
    ideas: int | None = None,
    now: str = "",
) -> dict[str, Any]:
    """Close an active review, giving it the next place in the review order."""
    now = now or now_iso()
    with registry_lock(root):
        payload = load_reviews(root)
        reviews = list(payload.get("reviews", []))
        review = next((item for item in reviews if item.get("review_id") == review_id), None)
        if review is None:
            raise RegistryError(f"review {review_id} does not exist")
        if review.get("status") != "active":
            raise RegistryError(f"review {review_id} is {review.get('status')}; only an active review can finish")
        if dossier and not (root / dossier).is_file():
            raise RegistryError(f"dossier {dossier!r} does not exist")
        order = max((int(item["order"]) for item in reviews if item.get("order")), default=0) + 1
        review.update({"status": "finished", "finished_at": now, "dossier": dossier,
                       "ideas": ideas, "order": order, "reserved_ids": []})
        repos = dict(payload.get("repos", {}))
        entry = dict(repos.get(review["slug"], {"slug": review["slug"], "url": review.get("url", ""),
                                                "first_reviewed_at": review["started_at"],
                                                "review_count": 0, "order": None, "dossier": ""}))
        entry["review_count"] = int(entry.get("review_count", 0)) + 1
        entry["last_reviewed_at"] = now
        entry["order"] = order
        if dossier:
            entry["dossier"] = dossier
        repos[review["slug"]] = entry
        payload["reviews"] = reviews
        payload["repos"] = repos
        errors = validate_reviews(payload, root)
        if errors:
            raise RegistryError("; ".join(errors))
        write_json(root / REVIEWS_FILE, payload)
        return review


def review_abandon(root: Path, review_id: int, *, reason: str, now: str = "") -> dict[str, Any]:
    """Close an active review without counting it, recording why."""
    if len(reason.strip()) < MIN_REASON_CHARS:
        raise RegistryError(f"an abandoned review needs a reason of at least {MIN_REASON_CHARS} characters")
    now = now or now_iso()
    with registry_lock(root):
        payload = load_reviews(root)
        reviews = list(payload.get("reviews", []))
        review = next((item for item in reviews if item.get("review_id") == review_id), None)
        if review is None:
            raise RegistryError(f"review {review_id} does not exist")
        if review.get("status") != "active":
            raise RegistryError(f"review {review_id} is {review.get('status')}; only an active review can be abandoned")
        review.update({"status": "abandoned", "finished_at": now,
                       "closed_reason": reason.strip(), "reserved_ids": []})
        payload["reviews"] = reviews
        errors = validate_reviews(payload, root)
        if errors:
            raise RegistryError("; ".join(errors))
        write_json(root / REVIEWS_FILE, payload)
        return review


def review_rows(payload: Mapping[str, Any], *, now: str | None = None) -> list[dict[str, Any]]:
    """One row per repository: review order, count, last review and current state.

    ``now=None`` renders the recorded state without evaluating lease expiry, which
    keeps the generated MATRIX.md stable over time; the ``reviews`` command passes
    the current time so it can report a lease as stale.
    """
    reviews = payload.get("reviews", []) or []
    rows: list[dict[str, Any]] = []
    for slug, entry in (payload.get("repos", {}) or {}).items():
        active = [
            item for item in reviews
            if item.get("slug") == slug and item.get("status") == "active"
        ]
        current = active[0] if active else None
        if current is None:
            state = "idle"
        elif now is not None and _lease_expired(current, now):
            state = "stale"
        else:
            state = "active"
        rows.append({
            "slug": slug,
            "url": entry.get("url", ""),
            "kind": entry.get("kind", DEFAULT_REPO_KIND),
            "review_count": entry.get("review_count", 0),
            "last_reviewed_at": entry.get("last_reviewed_at", ""),
            "order": entry.get("order"),
            "dossier": entry.get("dossier", ""),
            "state": state,
            "active_review_id": current.get("review_id") if current else None,
            "active_agent": current.get("agent", "") if current else "",
            "lease_until": current.get("lease_until", "") if current else "",
            "reserved": tuple(current.get("reserved_ids", []) or []) if current else (),
        })
    rows.sort(key=lambda row: (row["order"] is None, row["order"] or 0, row["slug"]))
    return rows


def classify_freshness(
    review: Mapping[str, Any],
    dossier_text: str,
    *,
    today: str,
    max_age_days: int = 180,
) -> str:
    """Classify one review as current, aged, superseded or unknown.

    Freshness is computed from the dossier header and the review ledger; it is never
    persisted, so it cannot itself go stale.
    """
    if int(review.get("review_count", 0) or 0) > 1:
        return "superseded"
    header = upstream_check.parse_header(dossier_text)
    analysed = str(header.get("date", ""))
    if not analysed:
        return "unknown"
    try:
        analysed_date = datetime.date.fromisoformat(analysed)
        today_date = datetime.date.fromisoformat(today)
    except ValueError:
        return "unknown"
    return "aged" if (today_date - analysed_date).days > max_age_days else "current"


def stale_reviews(
    rows: list[dict[str, Any]],
    root: Path = ROOT,
    *,
    today: str = "",
    max_age_days: int = 180,
) -> list[dict[str, Any]]:
    """Return the non-current rows, oldest analysis first, with a ``freshness`` field."""
    today = today or datetime.date.today().isoformat()
    stale: list[dict[str, Any]] = []
    for row in rows:
        dossier = str(row.get("dossier") or "")
        path = root / dossier if dossier else None
        try:
            text = path.read_text(encoding="utf-8") if path is not None and path.is_file() else ""
        except OSError:
            text = ""
        freshness = classify_freshness(row, text, today=today, max_age_days=max_age_days)
        if freshness == "current":
            continue
        item = dict(row)
        item["freshness"] = freshness
        item["_analysed"] = upstream_check.parse_header(text).get("date", "")
        stale.append(item)
    stale.sort(key=lambda row: (not row["_analysed"], str(row["_analysed"]), str(row.get("slug", ""))))
    for row in stale:
        row.pop("_analysed", None)
    return stale


def list_ideas(
    payload: Mapping[str, Any],
    *,
    target: str = "",
    status: str = "",
    dossier: str = "",
    tag: str = "",
    include_rejected: bool = False,
    include_duplicates: bool = False,
    include_blocked: bool = False,
) -> list[dict[str, Any]]:
    """Return the register rows matching the filters, in id order.

    ``Rejected`` rows, rows tagged ``duplicate`` and ``Blocked`` rows are hidden unless the
    matching ``include_*`` flag is set, ``status`` asks for one explicitly, or ``tag='duplicate'``
    asks for duplicates explicitly. The include flags are alternatives: either one shows a row
    that belongs to several categories. They stay in the register and in ``MATRIX.md``; they only
    leave the default working list.
    """
    rows: list[dict[str, Any]] = []
    for idea in payload.get("ideas", []) or []:
        if target and idea.get("target") != target:
            continue
        if status and idea.get("status") != status:
            continue
        tags = effective_tags(idea)
        rejected = idea.get("status") == "Rejected"
        duplicate = "duplicate" in tags
        blocked = idea.get("status") == BLOCKED_STATUS
        show_rejected = rejected and (include_rejected or status == "Rejected")
        show_duplicate = duplicate and (include_duplicates or tag == "duplicate")
        show_blocked = blocked and (include_blocked or status == BLOCKED_STATUS)
        if (rejected or duplicate or blocked) and not (
            show_rejected or show_duplicate or show_blocked
        ):
            continue
        if dossier and idea.get("dossier") != dossier:
            continue
        if tag and tag not in tags:
            continue
        rows.append(dict(idea))
    rows.sort(key=lambda row: str(row.get("id", "")))
    return rows


def idea_history(payload: Mapping[str, Any], idea_id: str) -> list[dict[str, Any]]:
    """Return one idea's recorded changes, or refuse an unknown id."""
    for idea in payload.get("ideas", []) or []:
        if idea.get("id") == idea_id:
            return [dict(entry) for entry in idea.get("history", []) or []]
    raise RegistryError(f"{idea_id} is not in the register")


def proposed_by_target(payload: Mapping[str, Any]) -> dict[str, dict[str, int]]:
    """Per target, how many ideas sit in each decision state."""
    counts: dict[str, dict[str, int]] = {}
    for idea in payload.get("ideas", []) or []:
        target = str(idea.get("target", ""))
        state = str(idea.get("status", "Proposed"))
        counts.setdefault(target, {})
        counts[target][state] = counts[target].get(state, 0) + 1
    return counts


def _plus_minutes(now: str, minutes: int) -> str:
    return (_parse_ts(now) + datetime.timedelta(minutes=minutes)).replace(microsecond=0).isoformat()


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------

def _report(errors: list[str]) -> int:
    if not errors:
        print("[OK] registry is valid")
        return 0
    print(f"[FAIL] {len(errors)} registry problem(s):")
    for error in errors:
        print(f"  - {error}")
    return 1


def add_commands(sub: argparse._SubParsersAction) -> None:
    """Declare every Idea Catcher command once, for either top-level CLI."""
    sub.add_parser("validate", help="validate targets.json, ideas.json, dossiers and MATRIX.md")
    render = sub.add_parser("render", help="write MATRIX.md from the registry")
    render.add_argument("--check", action="store_true", help="fail instead of writing when stale")
    sub.add_parser("status", help="print the full register's idea and proposed counts")
    sync = sub.add_parser("sync", help="register ideas named by IDEA-NNN commit messages")
    sync.add_argument("--repo", default=".", help="git repository to scan (default: current folder)")
    sync.add_argument("--project", default="", help="idea target id; defaults to the repository folder name")
    sync.add_argument("--limit", type=int, default=200, help="newest commits to scan (default 200)")
    sync.add_argument("--dry-run", action="store_true", help="show changes without writing")
    sync.add_argument("--json", action="store_true")
    add = sub.add_parser("add-target", help="register a new routing target")
    add.add_argument("--id", required=True)
    add.add_argument("--name", required=True)
    add.add_argument("--path", required=True)
    add.add_argument("--stack", required=True)
    add.add_argument("--gate", required=True)
    add.add_argument("--fit", required=True)
    add.add_argument("--added", default=datetime.date.today().isoformat(),
                     help="ISO date the target joined; defaults to today")
    add.add_argument("--allow-missing-path", action="store_true")
    idea = sub.add_parser("add-idea", help="register a dossier section as an idea")
    idea.add_argument("--dossier", required=True)
    idea.add_argument("--target", required=True)
    idea.add_argument("--impact", required=True)
    idea.add_argument("--effort", required=True)
    idea.add_argument("--id", default="", help="IDEA-NNN; defaults to the next free number")
    idea.add_argument("--concept", default="", help="overrides the dossier heading as the concept")
    idea.add_argument("--review", type=int, default=None, help="the review that reserved this id")
    decide = sub.add_parser("set-status", help="record a decision for one idea")
    decide.add_argument("idea_id")
    decide.add_argument("--status", required=True, choices=sorted(STATUS_SPECS))
    decide.add_argument("--reason", default="")
    decide.add_argument("--decided-at", default="")
    decide.add_argument("--decided-by", default="")
    decide.add_argument("--evidence", default="")
    decide.add_argument("--target", default="")
    decide.add_argument("--superseded-by", default="")
    review = sub.add_parser(
        "review-idea", help="record a second-pass idea review; two defer verdicts block it"
    )
    review.add_argument("idea_id")
    review.add_argument("--verdict", required=True, choices=sorted(REVIEW_VERDICTS))
    review.add_argument("--evidence", required=True,
                        help="what was checked and what it proved; at least 24 characters")
    review.add_argument("--by", default="", help="who performed the review")
    review.add_argument("--notes", default="")
    review.add_argument("--file", dest="files", action="append", default=[],
                        help="file checked; repeat for several")
    review.add_argument("--command", dest="commands", action="append", default=[],
                        help="command run; repeat for several")
    review.add_argument("--status", default="", choices=("", *sorted(STATUS_SPECS)),
                        help="override the status implied by the verdict")
    review.add_argument("--reason", default="", help="decision reason for a status change")
    review.add_argument("--decided-at", default="")
    review.add_argument("--superseded-by", default="")
    start = sub.add_parser("review-start", help="claim a repository for analysis")
    start.add_argument("--repo", required=True, help="owner/name")
    start.add_argument("--url", default="")
    start.add_argument("--agent", default="")
    start.add_argument("--kind", default=DEFAULT_REPO_KIND, choices=REPO_KINDS,
                       help="what the repository is: framework, tool, awesome-list, survey")
    start.add_argument("--lease-minutes", type=int, default=REVIEW_LEASE_MINUTES)
    start.add_argument("--reserve", type=int, default=0, help="reserve N idea numbers for this review")
    start.add_argument("--force", action="store_true", help="take over an unexpired claim")
    finish = sub.add_parser("review-finish", help="close a review and give it the next order")
    finish.add_argument("review_id", type=int)
    finish.add_argument("--dossier", default="")
    finish.add_argument("--ideas", type=int, default=None)
    abandon = sub.add_parser("review-abandon", help="close a review without counting it")
    abandon.add_argument("review_id", type=int)
    abandon.add_argument("--reason", required=True)
    list_reviews = sub.add_parser("reviews", help="show the repository review ledger")
    list_reviews.add_argument("--json", action="store_true", help="print rows as JSON")
    list_reviews.add_argument(
        "--release-expired", action="store_true", help="abandon expired leases and free their ids"
    )
    list_reviews.add_argument(
        "--stale", action="store_true", help="only reviews whose dossier is aged, superseded or unknown"
    )
    list_reviews.add_argument("--max-age-days", type=int, default=180,
                              help="age at which an analysis becomes aged (default 180)")
    revalidate = sub.add_parser(
        "revalidate", help="re-check dossier headers against upstream (network)"
    )
    revalidate.add_argument("--strict", action="store_true",
                            help="fail on a licence change or a missing repository")
    revalidate.add_argument("--limit", type=int, default=0,
                            help="maximum repositories fetched this run (0 = all)")
    revalidate.add_argument("--cache-dir", default="",
                            help="cache directory; defaults to .aikit/upstream-cache")
    revalidate.add_argument("--today", default="", help="override the cache day (tests)")
    revalidate.add_argument("--json", action="store_true", help="print results as JSON")
    audit = sub.add_parser(
        "audit-claims", help="check advertised modules against a real repository checkout"
    )
    audit.add_argument("--repo-path", required=True, help="path to the analysed checkout")
    audit.add_argument("--dossier", default="", help="dossier whose backticked paths are the claims")
    audit.add_argument("--claim", action="append", default=[], metavar="NAME=PATH[:SYMBOLS]",
                       help="explicit claim; repeat for several modules")
    audit.add_argument("--commit", default="", help="commit the evidence is pinned to")
    audit.add_argument("--max-files", type=int, default=claim_audit.MAX_FILES_DEFAULT)
    audit.add_argument("--strict", action="store_true", help="fail if any module is absent")
    audit.add_argument("--json", action="store_true", help="print evidence as JSON")
    concepts = sub.add_parser("concepts", help="render the concept co-occurrence report")
    concepts.add_argument("--write", action="store_true", help="write CONCEPTS.md")
    concepts.add_argument("--min-df", type=int, default=3, help="minimum document frequency (default 3)")
    concepts.add_argument("--threshold", type=int, default=3,
                          help="minimum pair weight for a strong edge (default 3)")
    concepts.add_argument("--json", action="store_true", help="print the graph as JSON")
    list_ideas = sub.add_parser("ideas", help="list ideas, optionally for one target")
    list_ideas.add_argument("--target", default="", help="limit to one target id")
    list_ideas.add_argument("--status", default="", choices=("", *sorted(STATUS_SPECS)))
    list_ideas.add_argument("--dossier", default="")
    list_ideas.add_argument("--tag", default="", help="verified, rejected, ... (stored or status-derived)")
    list_ideas.add_argument(
        "--include-rejected",
        action="store_true",
        help="include Rejected ideas, which are hidden from the default working list",
    )
    list_ideas.add_argument(
        "--include-duplicates",
        action="store_true",
        help="include ideas tagged duplicate, which are hidden from the default working list",
    )
    list_ideas.add_argument(
        "--include-blocked",
        action="store_true",
        help="include Blocked ideas, which are hidden from the default working list",
    )
    list_ideas.add_argument("--json", action="store_true")
    tagger = sub.add_parser("tag", help="add or remove analysis tags on one idea")
    tagger.add_argument("idea_id")
    tagger.add_argument("--add", action="append", default=[], choices=sorted(TAG_SPECS), metavar="TAG")
    tagger.add_argument("--remove", action="append", default=[], choices=sorted(TAG_SPECS), metavar="TAG")
    tagger.add_argument("--by", default="", help="who changed the tags")
    tagger.add_argument("--reason", default="", help="why the tags changed")
    history = sub.add_parser("history", help="show the recorded changes for one idea")
    history.add_argument("idea_id")
    history.add_argument("--json", action="store_true", help="print entries as JSON")


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="idea_catcher", description=__doc__.splitlines()[0])
    add_commands(parser.add_subparsers(dest="command", required=True))
    return parser


def main(argv: list[str] | None = None, root: Path = ROOT) -> int:
    return run(build_parser().parse_args(argv), root)


def run(args: argparse.Namespace, root: Path = ROOT) -> int:
    """Execute an already parsed command; shared with `python aikit.py idea-catcher`."""
    try:
        if args.command == "add-target":
            targets = add_target(
                root,
                target={
                    "id": args.id,
                    "name": args.name,
                    "path": args.path,
                    "stack": args.stack,
                    "gate": args.gate,
                    "fit": args.fit,
                    "added": args.added,
                },
                require_path=not args.allow_missing_path,
            )
            print(f"[OK] registered target {args.id!r}; {len(targets)} targets now route ideas")
            print("     next: python aikit.py idea-catcher render")
            return 0
        if args.command == "add-idea":
            idea = add_idea(
                root,
                dossier=args.dossier,
                target=args.target,
                impact=args.impact,
                effort=args.effort,
                idea_id=args.id,
                concept=args.concept,
                review_id=args.review,
            )
            print(f"[OK] registered {idea['id']} in {idea['dossier']} -> {idea['target']}")
            print("     next: python aikit.py idea-catcher render")
            return 0
        if args.command == "sync":
            repo = Path(args.repo).expanduser().resolve()
            project = args.project or repo.name
            try:
                updated = register_from_repo(
                    repo, project, root=root, limit=args.limit, dry_run=args.dry_run,
                )
            except (OSError, ValueError) as exc:
                print(f"Error: {exc}", file=sys.stderr)
                print("Why: the Git history could not be read, or the register refused an update.",
                      file=sys.stderr)
                print("Fix: pass an existing Git checkout with `--repo <path>`; run "
                      "`idea-catcher validate` if the register is invalid.", file=sys.stderr)
                return 1
            if args.json:
                print(json.dumps({"ok": True, "result": {"project": project, "updated": updated}},
                                 indent=2))
            elif not updated:
                print(f"No new IDEA-NNN commit references for target '{project}'.")
                if not args.project:
                    print("     If that is not this repository's target id, pass `--project <id>`.")
            else:
                for row in updated:
                    print(f"[OK] {row['id']} <- {row['commit'][:12]} {row['subject']}")
                if args.dry_run:
                    print("     dry run: no files written")
                else:
                    print(f"     matrix refreshed: {MATRIX_FILE}")
            return 0
        if args.command == "set-status":
            idea = set_status(
                root,
                args.idea_id,
                status=args.status,
                reason=args.reason,
                decided_at=args.decided_at,
                decided_by=args.decided_by,
                evidence=args.evidence,
                target=args.target,
                superseded_by=args.superseded_by,
            )
            print(f"[OK] {idea['id']} is now {idea['status']}")
            print("     next: python aikit.py idea-catcher render")
            return 0
        if args.command == "review-idea":
            idea = review_idea(
                root,
                args.idea_id,
                verdict=args.verdict,
                evidence=args.evidence,
                by=args.by,
                notes=args.notes,
                files=args.files,
                commands=args.commands,
                status=args.status,
                reason=args.reason,
                decided_at=args.decided_at,
                superseded_by=args.superseded_by,
            )
            print(f"[OK] {idea['id']} reviewed as {args.verdict}; status {idea['status']}")
            if idea["status"] == BLOCKED_STATUS:
                print("     blocked after two deferrals; it will not be reviewed again")
            print("     next: python aikit.py idea-catcher render")
            return 0
        if args.command == "tag":
            idea = set_tags(
                root, args.idea_id, add=args.add, remove=args.remove,
                by=args.by, reason=args.reason,
            )
            print(f"[OK] {idea['id']} tags: {', '.join(effective_tags(idea))}")
            print("     next: python aikit.py idea-catcher render")
            return 0
        if args.command == "review-start":
            review = review_start(
                root,
                slug=args.repo,
                url=args.url,
                agent=args.agent,
                lease_minutes=args.lease_minutes,
                force=args.force,
                reserve=args.reserve,
                kind=args.kind,
            )
            print(
                f"[OK] review {review['review_id']} claimed {review['slug']} "
                f"until {review['lease_until']}; analyze, then `review-finish {review['review_id']}`"
            )
            held = review["reserved_ids"]
            if held:
                print(
                    f"     reserved {len(held)} idea number(s): "
                    f"IDEA-{held[0]:03d}..IDEA-{held[-1]:03d} "
                    f"({', '.join(f'IDEA-{n:03d}' for n in held)})"
                )
                print(
                    "     write those headings in the dossier, then register each with "
                    f"`add-idea --review {review['review_id']}`"
                )
            return 0
        if args.command == "review-finish":
            review = review_finish(
                root, args.review_id, dossier=args.dossier, ideas=args.ideas
            )
            print(
                f"[OK] review {review['review_id']} finished {review['slug']} "
                f"at order #{review['order']}"
            )
            print("     next: python aikit.py idea-catcher render")
            return 0
        if args.command == "review-abandon":
            review = review_abandon(root, args.review_id, reason=args.reason)
            print(f"[OK] review {review['review_id']} abandoned: {review['closed_reason']}")
            return 0
        if args.command == "revalidate":
            if args.limit < 0:
                raise RegistryError("--limit cannot be negative")
            results = upstream_check.run_revalidation(
                root,
                today=args.today,
                cache_dir=Path(args.cache_dir) if args.cache_dir else None,
                limit=args.limit,
            )
            if args.json:
                print(json.dumps(results, indent=2, ensure_ascii=False))
            else:
                print(upstream_check.render_report(results))
            errors = [row for row in results if row.get("state") == "error"]
            failures = [row for row in results if upstream_check.is_failure(row)]
            if errors:
                print(f"[FAIL] {len(errors)} upstream check(s) could not complete")
                return 1
            if args.strict and failures:
                print(f"[FAIL] {len(failures)} upstream change(s) need attention")
                return 1
            return 0
        if args.command == "audit-claims":
            dossier_path = root / args.dossier if args.dossier else None
            if dossier_path is not None and not dossier_path.is_file():
                raise RegistryError(f"dossier {args.dossier!r} does not exist")
            if dossier_path is None and not args.claim:
                raise RegistryError("give --dossier or at least one --claim")
            text = dossier_path.read_text(encoding="utf-8") if dossier_path is not None else ""
            claims = [claim_audit.parse_claim(value) for value in args.claim]
            if dossier_path is not None and not claims:
                claims = claim_audit.claims_from_dossier(text)
            if not claims:
                raise RegistryError(f"dossier {args.dossier!r} advertises no repository paths")
            commit = args.commit or upstream_check.parse_header(text).get("commit", "")
            evidence = claim_audit.audit_claims(
                Path(args.repo_path), claims, commit=commit, max_files=args.max_files
            )
            verdict = claim_audit.assess_ratio(
                Path(args.repo_path), evidence, max_files=args.max_files
            )
            if args.json:
                payload = {
                    "evidence": [
                        {
                            "module": row.claim.name,
                            "advertised_path": row.claim.advertised_path,
                            "state": row.state,
                            "evidence_paths": list(row.evidence_paths),
                            "symbols": list(row.symbols),
                            "verified_at_commit": row.verified_at_commit,
                        }
                        for row in evidence
                    ],
                    "verdict": verdict,
                }
                print(json.dumps(payload, indent=2, ensure_ascii=False))
            else:
                print(claim_audit.render_table(evidence))
                print()
                print(claim_audit.render_summary(verdict))
            if args.strict and any(row.state == "absent" for row in evidence):
                print("[FAIL] an advertised module is absent from the checkout")
                return 1
            return 0
        targets = load_targets(root)
        payload = load_ideas(root)
        reviews = load_reviews(root)
        if args.command == "concepts":
            if args.min_df < 1:
                raise RegistryError("--min-df must be at least 1")
            if args.threshold < 1:
                raise RegistryError("--threshold must be at least 1")
            docs = concept_map.documents_from_ideas(payload)
            graph = concept_map.build_cooccurrence(docs, min_df=args.min_df)
            components = concept_map.clusters(graph, threshold=args.threshold)
            duplicates = concept_map.exact_duplicates(payload)
            overlap = concept_map.target_overlap(payload, docs)
            if args.json:
                print(json.dumps({
                    "documents": len(docs),
                    "edges": [
                        {"a": first, "b": second, "weight": weight}
                        for (first, second), weight in list(graph.items())[:concept_map.MAX_REPORT_EDGES]
                    ],
                    "clusters": components,
                    "duplicates": duplicates,
                    "target_overlap": {
                        target: [{"term": term, "documents": count} for term, count in terms]
                        for target, terms in overlap.items()
                    },
                }, indent=2, ensure_ascii=False))
                return 0
            text = concept_map.render_report(
                graph,
                components,
                duplicates=duplicates,
                target_overlap_=overlap,
                min_df=args.min_df,
                threshold=args.threshold,
                documents=len(docs),
            )
            if args.write:
                concept_map.write_report(root / "CONCEPTS.md", text)
                print(
                    f"[OK] wrote CONCEPTS.md ({len(graph)} edge(s), "
                    f"{len(duplicates)} duplicate group(s))"
                )
            else:
                print(text)
            return 0
        if args.command == "reviews":
            if args.release_expired:
                released = release_expired(root)
                if released:
                    print(f"[OK] released expired review(s): {', '.join(map(str, released))}")
                else:
                    print("[OK] no expired review to release")
                reviews = load_reviews(root)
            rows = review_rows(reviews, now=now_iso())
            if args.stale:
                if args.max_age_days < 0:
                    raise RegistryError("--max-age-days cannot be negative")
                rows = stale_reviews(
                    rows, root, today=now_iso()[:10], max_age_days=args.max_age_days
                )
                if not rows:
                    print("no stale reviews: every dossier is current")
                    return 0
            if args.json:
                print(json.dumps(rows, indent=2, ensure_ascii=False))
                return 0
            if not rows:
                print("no repository reviews recorded yet")
                return 0
            for row in rows:
                order = f"#{row['order']}" if row["order"] else "—"
                lease = f" until {row['lease_until']}" if row["lease_until"] else ""
                freshness = f" · {row['freshness']}" if row.get("freshness") else ""
                print(
                    f"{order:>5}  {row['slug']:<40} {row['review_count']:>2} review(s)  "
                    f"{row['state']}{lease}{freshness}"
                )
            return 0
        if args.command == "history":
            entries = idea_history(payload, args.idea_id)
            if args.json:
                print(json.dumps(entries, indent=2, ensure_ascii=False))
                return 0
            if not entries:
                print(f"{args.idea_id} has no recorded history")
                return 0
            for entry in entries:
                who = entry.get("by") or "—"
                if entry.get("field"):
                    print(
                        f"  {entry.get('at', '')}  {entry['field']}: "
                        f"{json.dumps(entry.get('from'), ensure_ascii=False)} -> "
                        f"{json.dumps(entry.get('to'), ensure_ascii=False)}  by {who}"
                    )
                else:
                    print(f"  {entry.get('at', '')}  status -> {entry.get('status')}  by {who}")
            return 0
        if args.command == "ideas":
            if args.target and args.target not in target_ids(targets):
                print(f"[FAIL] target {args.target!r} is not declared in targets.json")
                return 1
            rows = list_ideas(
                payload,
                target=args.target,
                status=args.status,
                dossier=args.dossier,
                tag=args.tag,
                include_rejected=args.include_rejected,
                include_duplicates=args.include_duplicates,
                include_blocked=args.include_blocked,
            )
            hidden = 0
            if ((args.status != "Rejected" and not args.include_rejected)
                    or (args.tag != "duplicate" and not args.include_duplicates)
                    or (args.status != BLOCKED_STATUS and not args.include_blocked)):
                hidden = len(list_ideas(
                    payload,
                    target=args.target,
                    status=args.status,
                    dossier=args.dossier,
                    tag=args.tag,
                    include_rejected=True,
                    include_duplicates=True,
                    include_blocked=True,
                )) - len(rows)
            if args.json:
                print(json.dumps(rows, indent=2, ensure_ascii=False))
                return 0
            scope = f"target {args.target}" if args.target else "all targets"
            if not rows:
                print(f"no ideas for {scope}")
                if hidden:
                    print(
                        f"  ({hidden} hidden idea(s); use --include-rejected, "
                        "--include-duplicates or --include-blocked to show them)"
                    )
                return 0
            by_state = _status_counts(rows)
            print(f"{len(rows)} idea(s) for {scope} · {by_state}")
            if hidden:
                print(
                    f"  ({hidden} hidden idea(s); use --include-rejected, "
                    "--include-duplicates or --include-blocked to show them)"
                )
            for row in rows:
                print(
                    f"  {row['id']}  {row.get('status', 'Proposed'):<12} "
                    f"{row.get('impact', ''):<9}/{row.get('effort', ''):<4} "
                    f"{row.get('concept', '')}"
                    + (f"  [{', '.join(row['tags'])}]" if row.get("tags") else "")
                )
            return 0
        if args.command == "status":
            print(f"{len(payload.get('ideas', []))} ideas · {_status_counts(payload.get('ideas', []))}")
            print(f"{len(reviews.get('repos', {}))} repositories reviewed · {len(reviews.get('reviews', []))} review records")
            docs = concept_map.documents_from_ideas(payload)
            graph = concept_map.build_cooccurrence(docs, min_df=3)
            print(
                f"concepts: {concept_map.shared_pair_count(graph)} strong pair(s) at weight >= 3; "
                "run `concepts --write` for the map"
            )
            held = reserved_ids(reviews)
            if held:
                print(f"reserved idea numbers: {', '.join(f'IDEA-{n:03d}' for n in sorted(held))}")
            for target in targets:
                target_id = str(target["id"])
                rows = list_ideas(payload, target=target_id, include_rejected=True,
                                  include_duplicates=True, include_blocked=True)
                proposed = sum(1 for row in rows if row.get("status") == "Proposed")
                print(f"  {target_id:<22} {len(rows):>3} idea(s), {proposed:>3} proposed")
            return 0
        if args.command == "render":
            matches, message = matrix_matches(root, targets, payload, reviews)
            if args.check:
                if matches:
                    print("[OK] MATRIX.md matches the registry")
                    return 0
                print(f"[FAIL] {message}")
                return 1
            write_matrix(root, targets, payload, reviews)
            print(f"[OK] wrote {MATRIX_FILE}")
            return 0
        errors = validate_targets(targets) + validate_ideas(payload, targets, root, reviews)
        errors += validate_reviews(reviews, root, ideas_payload=payload)
        matches, message = matrix_matches(root, targets, payload, reviews)
        if not matches:
            errors.append(message)
        return _report(errors)
    except RegistryError as error:
        print(f"[FAIL] {error}")
        return 1
    except upstream_check.UpstreamError as error:
        print(f"[FAIL] {error}")
        print("       Why: the upstream API did not answer; the offline register is unchanged.")
        print("       Fix: retry later, set GITHUB_TOKEN, or run without --strict.")
        return 1
    except OSError as error:
        print(f"[FAIL] cannot read or write the registry: {error}")
        return 1


if __name__ == "__main__":
    sys.exit(main())
