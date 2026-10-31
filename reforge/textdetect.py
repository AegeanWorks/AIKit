"""Structural review of changed text files that need no language front end.

Reforge reviews the changes a working session actually makes, and those are not only Python:
documentation, JSON configuration, TOML metadata and workflows change in the same commits. This
module keeps that review honest without guessing: it validates the formats the standard library
can parse, reports the defects a text diff can prove, and says nothing about a file whose grammar
it cannot check. Every finding still carries a line of evidence.

Binary files are reported by the caller as not analysed, because they cannot be read as text.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import List, Optional, Sequence

from reforge.detectors import RULES, allow_marker
from reforge.model import Finding

try:  # Python 3.11+ ships TOML in the standard library; older runtimes check nothing.
    import tomllib
except ImportError:  # pragma: no cover - exercised only on Python 3.10
    tomllib = None  # type: ignore[assignment]

JSON_SUFFIXES = (".json",)
TOML_SUFFIXES = (".toml",)
MARKDOWN_SUFFIXES = (".md", ".markdown")
CONFLICT_MARKERS = ("<<<<<<<", ">>>>>>>")
FENCE_MARKERS = ("```", "~~~")


def is_text(source: str) -> bool:
    """Whether a file revision can be reviewed as text instead of skipped as binary."""
    return "\x00" not in source


def _snippet(lines: Sequence[str], line: int) -> str:
    if 1 <= line <= len(lines):
        return lines[line - 1].strip()[:160]
    return ""


def _finding(code: str, path: str, line: int, lines: Sequence[str], commit: str) -> Finding:
    rule = RULES[code]
    return Finding(
        code=code,
        category=rule.category,
        severity=rule.severity,
        path=path,
        line=int(line),
        message=rule.message,
        evidence=f"{path}:{int(line)}: {_snippet(lines, int(line))}",
        commit=commit,
        reproducible=code.startswith("invalid-"),
        source="text",
    )


def _conflict_markers(path: str, lines: Sequence[str], commit: str) -> List[Finding]:
    return [_finding("merge-conflict-marker", path, number, lines, commit)
            for number, text in enumerate(lines, 1)
            if text.startswith(CONFLICT_MARKERS)]


def _invalid_json(path: str, source: str, lines: Sequence[str], commit: str) -> List[Finding]:
    try:
        json.loads(source)
    except ValueError as exc:
        line = int(getattr(exc, "lineno", 1) or 1)
        return [_finding("invalid-json", path, line, lines, commit)]
    return []


def _invalid_toml(path: str, source: str, lines: Sequence[str], commit: str) -> List[Finding]:
    if tomllib is None:  # pragma: no cover - Python 3.10 has no parser, so nothing is claimed
        return []
    try:
        tomllib.loads(source)
    except ValueError as exc:
        line = int(getattr(exc, "lineno", 1) or 1)
        return [_finding("invalid-toml", path, line, lines, commit)]
    return []


def _unclosed_fence(path: str, lines: Sequence[str], commit: str) -> List[Finding]:
    opened: Optional[int] = None
    opener: Optional[str] = None
    for number, text in enumerate(lines, 1):
        stripped = text.strip()
        marker = next((item for item in FENCE_MARKERS if stripped.startswith(item)), None)
        if marker is None:
            continue
        if opener is None:
            opener, opened = marker, number
        elif stripped.startswith(opener) and set(stripped) == {opener[0]}:
            opener, opened = None, None
    return [_finding("unclosed-code-fence", path, opened, lines, commit)] if opened else []


def detect_text(path: str, source: str, commit: str) -> List[Finding]:
    """Every proven defect in one text file revision, ordered by line."""
    lines = source.splitlines()
    suffix = Path(path).suffix.lower()
    findings = _conflict_markers(path, lines, commit)
    if suffix in JSON_SUFFIXES:
        findings += _invalid_json(path, source, lines, commit)
    elif suffix in TOML_SUFFIXES:
        findings += _invalid_toml(path, source, lines, commit)
    if suffix in MARKDOWN_SUFFIXES:
        findings += _unclosed_fence(path, lines, commit)
    kept = [item for item in findings if not allow_marker(lines, item.line)]
    return sorted(kept, key=lambda item: (item.line, item.code))
