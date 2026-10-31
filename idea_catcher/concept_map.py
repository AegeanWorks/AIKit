"""Deterministic concept co-occurrence map for the idea register.

The map is a review artefact, not a search engine and not a gate. It runs offline over
the committed dossiers and ``ideas.json``, reports exact duplicates, strongly shared
terms and per-target vocabulary, and writes nothing unless the caller asks for it.
"""

from __future__ import annotations

import os
import re
import tempfile
from pathlib import Path
from typing import Any, Mapping, Sequence

MIN_TOKEN = 3
MAX_TARGET_TERMS = 8
MAX_REPORT_EDGES = 200
MAX_CLUSTERS = 20
MAX_CLUSTER_TERMS = 12

# A generic English list plus terms that are boilerplate in this register. Keeping the
# list committed and reviewable is what stops "gate", "file" and "aikit" becoming
# spurious clusters.
STOP_WORDS = frozenset(
    """
    a an and are as at be been being but by can could did do does for from had has have
    he her here him his how i if in into is it its itself just may me more most my no nor
    not now of on once only or other our out over own same she should so some such than
    that the their them then there these they this those through to too under until up
    very was we were what when where which while who whom why will with would you your
    aikit neurocore aegean licensing reforge idea ideas dossier dossiers register registry
    gate gates test tests tested file files code source project projects
    implementation implement implemented implementation blueprint blueprints agent agents
    section sections table tables row rows column columns value values use used using
    make makes made add adds added new existing current currently per via etc example
    examples case cases also must need needs required require requires within without
    action actions analyzed analysed architecture cold combat commit commits complexity
    concept concepts contract contracts mechanism mechanisms potential improvement
    improvements weakness weaknesses priority impact effort score scores recommended
    adopt adapt skip executive summary core how these those step steps verification
    rollback read only offline deterministic generated com www http https github html
    repo repos repository repositories primary stack url license licence
    """.split()
)


def tokenize(text: str, stop: Sequence[str] | set[str] | frozenset[str] = STOP_WORDS) -> list[str]:
    """Lowercase, split on punctuation, and drop short or boilerplate terms."""
    blocked = set(stop)
    tokens = []
    for token in re.split(r"[^a-z0-9]+", str(text).lower()):
        if len(token) < MIN_TOKEN or len(token) > 40 or token.isdigit() or token in blocked:
            continue
        tokens.append(token)
    return tokens


def _doc_tokens(value: Sequence[str] | str) -> set[str]:
    if isinstance(value, str):
        return set(tokenize(value))
    return {token for token in value if len(token) >= MIN_TOKEN and token not in STOP_WORDS}


def build_cooccurrence(
    docs: Mapping[str, Sequence[str] | str], min_df: int = 3
) -> dict[tuple[str, str], int]:
    """Count document-level co-occurrence for terms that appear in at least ``min_df`` docs."""
    if min_df < 1:
        raise ValueError("min_df must be at least 1")
    per_doc = {doc_id: _doc_tokens(tokens) for doc_id, tokens in docs.items()}
    document_frequency: dict[str, int] = {}
    for tokens in per_doc.values():
        for token in tokens:
            document_frequency[token] = document_frequency.get(token, 0) + 1
    eligible = {token for token, count in document_frequency.items() if count >= min_df}
    graph: dict[tuple[str, str], int] = {}
    for tokens in per_doc.values():
        terms = sorted(tokens & eligible)
        for index, first in enumerate(terms):
            for second in terms[index + 1:]:
                graph[(first, second)] = graph.get((first, second), 0) + 1
    return dict(sorted(graph.items(), key=lambda item: (-item[1], item[0])))


def clusters(graph: Mapping[tuple[str, str], int], threshold: int = 3) -> list[list[str]]:
    """Connected components of the edges at or above ``threshold``."""
    parent: dict[str, str] = {}

    def find(term: str) -> str:
        parent.setdefault(term, term)
        while parent[term] != term:
            parent[term] = parent[parent[term]]
            term = parent[term]
        return term

    def union(first: str, second: str) -> None:
        left, right = find(first), find(second)
        if left != right:
            parent[right] = left

    for (first, second), weight in graph.items():
        if weight >= threshold:
            union(first, second)
    grouped: dict[str, list[str]] = {}
    for term in parent:
        grouped.setdefault(find(term), []).append(term)
    components = [sorted(terms) for terms in grouped.values()]
    components.sort(key=lambda terms: (-len(terms), terms))
    return components


def _normalise_concept(concept: str) -> str:
    return re.sub(r"[^a-z0-9]+", " ", str(concept).lower()).strip()


def exact_duplicates(ideas: Mapping[str, Any]) -> list[list[str]]:
    """Idea ids whose normalised concept strings are identical."""
    grouped: dict[str, list[str]] = {}
    for idea in ideas.get("ideas", []) or []:
        normalised = _normalise_concept(str(idea.get("concept", "")))
        if normalised:
            grouped.setdefault(normalised, []).append(str(idea.get("id", "")))
    duplicates = [sorted(ids) for ids in grouped.values() if len(ids) > 1]
    duplicates.sort()
    return duplicates


def documents_from_root(root: Path) -> dict[str, list[str]]:
    """One token document per dossier, keyed by its relative path."""
    documents: dict[str, list[str]] = {}
    for path in sorted((root / "dossiers").glob("*.md")):
        if path.name == "TEMPLATE.md":
            continue
        relative = str(path.relative_to(root)).replace("\\", "/")
        documents[relative] = tokenize(path.read_text(encoding="utf-8"))
    return documents


def documents_from_ideas(ideas: Mapping[str, Any]) -> dict[str, list[str]]:
    """One token document per dossier, built from the idea concepts it registers.

    Whole-dossier text is deliberately not used: headers, blueprint headings and the
    routing table appear in every dossier and would drown the signal in boilerplate.
    """
    documents: dict[str, list[str]] = {}
    for idea in ideas.get("ideas", []) or []:
        dossier = str(idea.get("dossier", ""))
        if not dossier:
            continue
        documents.setdefault(dossier, []).extend(tokenize(str(idea.get("concept", ""))))
    return documents


def target_overlap(
    ideas: Mapping[str, Any], docs: Mapping[str, Sequence[str] | str]
) -> dict[str, list[tuple[str, int]]]:
    """Per target, the terms shared by at least two of its dossiers."""
    dossiers_by_target: dict[str, set[str]] = {}
    for idea in ideas.get("ideas", []) or []:
        target = str(idea.get("target", ""))
        dossier = str(idea.get("dossier", ""))
        if target and dossier:
            dossiers_by_target.setdefault(target, set()).add(dossier)
    overlap: dict[str, list[tuple[str, int]]] = {}
    for target, dossiers in sorted(dossiers_by_target.items()):
        frequency: dict[str, int] = {}
        for dossier in dossiers:
            for token in _doc_tokens(docs.get(dossier, ())):
                frequency[token] = frequency.get(token, 0) + 1
        shared = [(term, count) for term, count in frequency.items() if count >= 2]
        shared.sort(key=lambda item: (-item[1], item[0]))
        overlap[target] = shared[:MAX_TARGET_TERMS]
    return overlap


def shared_pair_count(graph: Mapping[tuple[str, str], int], threshold: int = 3) -> int:
    return sum(1 for weight in graph.values() if weight >= threshold)


def render_report(
    graph: Mapping[tuple[str, str], int],
    clusters_: Sequence[Sequence[str]] = (),
    *,
    duplicates: Sequence[Sequence[str]] = (),
    target_overlap_: Mapping[str, Sequence[tuple[str, int]]] | None = None,
    min_df: int = 3,
    threshold: int = 3,
    documents: int = 0,
    limit: int = MAX_REPORT_EDGES,
) -> str:
    """Render the deterministic Markdown report."""
    terms = {term for pair in graph for term in pair}
    lines = [
        "# Concept Co-occurrence Map",
        "",
        "**Generated file.** This report is derived from [`ideas.json`](ideas.json) and the "
        "dossiers. It is a review artefact, not a gate: regenerate it with "
        "`python aikit.py idea-catcher concepts --write`.",
        "",
        f"{documents} dossier(s) · {len(terms)} term(s) · {len(graph)} edge(s) · "
        f"{shared_pair_count(graph, threshold)} strong pair(s) at weight >= {threshold}",
        "",
        "## Exact duplicates",
        "",
    ]
    if duplicates:
        for group in duplicates:
            lines.append(f"- {', '.join(f'`{idea_id}`' for idea_id in group)}")
    else:
        lines.append("_No exact duplicate concepts._")
    lines += [
        "",
        f"## Strong shared terms (df >= {min_df}, pair weight >= {threshold})",
        "",
    ]
    strong = sorted(
        ((pair, weight) for pair, weight in graph.items() if weight >= threshold),
        key=lambda item: (-item[1], item[0]),
    )
    shown = strong[:max(1, limit)]
    if shown:
        lines += ["| Term A | Term B | Documents |", "|---|---|---|"]
        for (first, second), weight in shown:
            lines.append(f"| `{first}` | `{second}` | {weight} |")
        if len(strong) > len(shown):
            lines.append("")
            lines.append(f"_Showing the top {len(shown)} of {len(strong)} strong pairs._")
    else:
        lines.append("_No strong shared-term pair yet._")
    lines += [
        "",
        "## Concept clusters",
        "",
    ]
    if clusters_:
        for component in list(clusters_)[:MAX_CLUSTERS]:
            terms_for_cluster = list(component)[:MAX_CLUSTER_TERMS]
            rendered = ", ".join(f"`{term}`" for term in terms_for_cluster)
            if len(component) > len(terms_for_cluster):
                rendered += f", … (+{len(component) - len(terms_for_cluster)})"
            lines.append("- " + rendered)
        if len(clusters_) > MAX_CLUSTERS:
            lines.append(f"- _… (+{len(clusters_) - MAX_CLUSTERS} more clusters)_")
    else:
        lines.append("_No cluster at this threshold._")
    lines += [
        "",
        "## Target vocabulary overlap",
        "",
    ]
    overlap = target_overlap_ or {}
    if overlap:
        lines += ["| Target | Shared terms |", "|---|---|"]
        for target, terms_for_target in sorted(overlap.items()):
            rendered = ", ".join(f"`{term}` ({count})" for term, count in terms_for_target) or "—"
            lines.append(f"| `{target}` | {rendered} |")
    else:
        lines.append("_No target shares a term across two dossiers._")
    return "\n".join(lines) + "\n"


def write_report(path: Path, text: str) -> None:
    """Write the generated report atomically."""
    path.parent.mkdir(parents=True, exist_ok=True)
    handle, temporary = tempfile.mkstemp(prefix=path.name + ".tmp_", dir=path.parent)
    try:
        with os.fdopen(handle, "w", encoding="utf-8", newline="\n") as stream:
            stream.write(text)
            stream.flush()
            os.fsync(stream.fileno())
        os.replace(temporary, path)
    finally:
        if os.path.exists(temporary):
            os.unlink(temporary)
