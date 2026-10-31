"""Advertised-module evidence for a real repository checkout.

A dossier written from a README repeats a product's feature list as if it were
architecture. This module checks each advertised module against a local checkout and
labels it ``implemented``, ``implemented_elsewhere``, ``stub``, ``absent`` or
``unknown``. It is read-only and never edits a dossier.

The merged IDEA-500 summary adds a repository-level claim-to-artefact verdict, so a
docs-only product page is labelled a design brief instead of a framework.
"""

from __future__ import annotations

import ast
import os
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Iterable, Sequence

STUB_BYTES = 16
MAX_FILES_DEFAULT = 5_000
PATH_RE = re.compile(r"^[A-Za-z0-9_.@+-]+(?:/[A-Za-z0-9_.@+-]+)+/?$")
IDENTIFIER_RE = re.compile(r"^[A-Za-z_][A-Za-z0-9_.]*$")
SOURCE_SUFFIXES = {
    ".py", ".js", ".jsx", ".ts", ".tsx", ".go", ".rs", ".java", ".kt", ".kts",
    ".cs", ".rb", ".php", ".swift", ".c", ".h", ".cc", ".cpp", ".hpp", ".m", ".mm",
}
SCHEMA_SUFFIXES = {".json", ".yaml", ".yml", ".toml", ".sql", ".graphql", ".proto"}
DOC_SUFFIXES = {".md", ".rst", ".txt"}
SKIP_DIRS = {".git", "__pycache__", "node_modules", ".venv", "venv", "dist", "build", ".mypy_cache"}
PLACEHOLDER_LINES = {"", "pass", "...", "todo", "fixme", "placeholder"}


class AuditError(ValueError):
    """The audit cannot run against the given repository or claim."""


@dataclass(frozen=True)
class ModuleClaim:
    name: str
    advertised_path: str | None
    entrypoints: tuple[str, ...] = ()


@dataclass(frozen=True)
class ClaimEvidence:
    claim: ModuleClaim
    state: str
    evidence_paths: tuple[str, ...]
    symbols: tuple[str, ...]
    verified_at_commit: str


def parse_claim(value: str) -> ModuleClaim:
    """Parse ``name=path`` or ``name=path:Symbol,other_symbol``."""
    text = str(value or "").strip()
    if not text:
        raise AuditError("an empty --claim is not a module claim")
    name, separator, rest = text.partition("=")
    if not separator:
        name, rest = Path(text).stem or text, text
    path, _, symbols = rest.partition(":")
    entrypoints = tuple(part.strip() for part in symbols.split(",") if part.strip())
    path = path.strip()
    if not name.strip():
        raise AuditError(f"claim {value!r} has no name")
    return ModuleClaim(name=name.strip(), advertised_path=path or None, entrypoints=entrypoints)


def claims_from_dossier(text: str) -> list[ModuleClaim]:
    """Extract backticked repository paths from a dossier, with nearby symbols."""
    claims: list[ModuleClaim] = []
    seen: set[str] = set()
    for line in text.splitlines():
        tokens = re.findall(r"`([^`]+)`", line)
        for token in tokens:
            if token in seen or not _looks_like_path(token):
                continue
            seen.add(token)
            path = token.rstrip("/")
            entrypoints = tuple(
                candidate for candidate in tokens
                if candidate != token and IDENTIFIER_RE.fullmatch(candidate)
            )[:5]
            claims.append(
                ModuleClaim(
                    name=Path(path).stem or path,
                    advertised_path=path,
                    entrypoints=entrypoints,
                )
            )
    return claims


def _looks_like_path(token: str) -> bool:
    if "://" in token or any(marker in token for marker in ("{", "}", "*", "?", "<", ">", " ")):
        return False
    if ".." in token.split("/"):
        return False
    if not PATH_RE.fullmatch(token):
        return False
    suffix = Path(token.rstrip("/")).suffix.lower()
    return suffix in SOURCE_SUFFIXES | SCHEMA_SUFFIXES | DOC_SUFFIXES or "/" in token


def _relative(repo: Path, path: Path) -> str:
    return str(path.relative_to(repo)).replace("\\", "/")


def _safe_path(repo: Path, advertised: str) -> Path:
    candidate = (repo / advertised).resolve()
    if candidate != repo and not candidate.is_relative_to(repo):
        raise AuditError(f"advertised path {advertised!r} escapes the repository")
    return candidate


def _python_symbols(tree: ast.AST) -> tuple[list[str], bool]:
    symbols: list[str] = []
    behaviour = False
    for node in getattr(tree, "body", []):
        if isinstance(node, (ast.ClassDef, ast.FunctionDef, ast.AsyncFunctionDef)):
            symbols.append(node.name)
            behaviour = True
        elif isinstance(node, (ast.Assign, ast.AnnAssign, ast.Import, ast.ImportFrom,
                               ast.If, ast.For, ast.While, ast.Try, ast.With)):
            behaviour = True
        elif isinstance(node, ast.Expr) and not (
            isinstance(node.value, ast.Constant) and node.value.value is Ellipsis
        ):
            behaviour = True
    return symbols, behaviour


def _symbols(path: Path) -> tuple[str, ...]:
    try:
        text = path.read_text(encoding="utf-8", errors="replace")
    except OSError:
        return ()
    suffix = path.suffix.lower()
    if suffix == ".py":
        try:
            symbols, _ = _python_symbols(ast.parse(text))
            return tuple(symbols)
        except SyntaxError:
            return tuple(re.findall(r"^(?:class|def|async def)\s+([A-Za-z_]\w*)", text, re.M))
    patterns = {
        ".js": r"(?:class|function|const|let|var)\s+([A-Za-z_$][\w$]*)",
        ".jsx": r"(?:class|function|const|let|var)\s+([A-Za-z_$][\w$]*)",
        ".ts": r"(?:class|function|const|let|var|interface|type)\s+([A-Za-z_$][\w$]*)",
        ".tsx": r"(?:class|function|const|let|var|interface|type)\s+([A-Za-z_$][\w$]*)",
        ".go": r"(?:func|type)\s+(?:\([^)]*\)\s*)?([A-Za-z_]\w*)",
        ".rs": r"(?:fn|struct|enum|trait)\s+([A-Za-z_]\w*)",
        ".java": r"(?:class|interface|enum|record)\s+([A-Za-z_]\w*)",
        ".kt": r"(?:class|interface|object|fun)\s+([A-Za-z_]\w*)",
        ".cs": r"(?:class|interface|enum|record)\s+([A-Za-z_]\w*)",
    }
    pattern = patterns.get(suffix)
    return tuple(dict.fromkeys(re.findall(pattern, text))) if pattern else ()


def _is_stub(path: Path) -> bool:
    try:
        if path.stat().st_size <= STUB_BYTES:
            return True
        text = path.read_text(encoding="utf-8", errors="replace")
    except OSError:
        return True
    if path.suffix.lower() == ".py":
        try:
            tree = ast.parse(text)
        except SyntaxError:
            tree = None
        if tree is not None:
            _, behaviour = _python_symbols(tree)
            if not behaviour:
                return True
    meaningful = []
    for line in text.splitlines():
        stripped = line.strip()
        if not stripped or stripped.startswith(("#", "//", "/*", "*")):
            continue
        if stripped.lower().rstrip(".;") in PLACEHOLDER_LINES:
            continue
        meaningful.append(stripped)
    return not meaningful


def _has_behaviour(path: Path) -> bool:
    try:
        text = path.read_text(encoding="utf-8", errors="replace")
    except OSError:
        return False
    if path.suffix.lower() == ".py":
        try:
            _, behaviour = _python_symbols(ast.parse(text))
            return behaviour
        except SyntaxError:
            return False
    return any(
        line.strip() and not line.strip().startswith(("#", "//", "/*", "*"))
        for line in text.splitlines()
    )


def _walk_files(repo: Path, max_files: int) -> tuple[list[Path], bool]:
    found: list[Path] = []
    for current, dirs, files in os.walk(repo):
        dirs[:] = sorted(directory for directory in dirs if directory not in SKIP_DIRS)
        for name in sorted(files):
            found.append(Path(current) / name)
            if len(found) > max_files:
                return found, True
    return found, False


def _find_symbol(repo: Path, entrypoints: Sequence[str], max_files: int) -> str:
    if not entrypoints:
        return ""
    files, _ = _walk_files(repo, max_files)
    for path in files:
        if path.suffix.lower() not in SOURCE_SUFFIXES:
            continue
        try:
            text = path.read_text(encoding="utf-8", errors="replace")
        except OSError:
            continue
        if any(re.search(r"\b" + re.escape(name) + r"\b", text) for name in entrypoints):
            return _relative(repo, path)
    return ""


def audit_claims(
    repo_path: Path,
    claims: Sequence[ModuleClaim],
    *,
    commit: str = "",
    max_files: int = MAX_FILES_DEFAULT,
) -> list[ClaimEvidence]:
    """Check every advertised module against a real checkout."""
    repo = Path(repo_path).resolve()
    if not repo.is_dir():
        raise AuditError(f"repository path {str(repo_path)!r} is not a directory")
    if max_files < 1:
        raise AuditError("max_files must be at least 1")
    _, truncated = _walk_files(repo, max_files)
    evidence: list[ClaimEvidence] = []
    for claim in claims:
        paths: tuple[str, ...] = ()
        symbols: tuple[str, ...] = ()
        state = "absent"
        if claim.advertised_path:
            candidate = _safe_path(repo, claim.advertised_path)
            if candidate.is_file():
                paths = (_relative(repo, candidate),)
                if _is_stub(candidate):
                    state = "stub"
                else:
                    symbols = _symbols(candidate)
                    state = "implemented" if symbols or _has_behaviour(candidate) else "stub"
            elif candidate.exists():
                state = "stub"
            else:
                found = _find_symbol(repo, claim.entrypoints, max_files)
                if found:
                    state, paths = "implemented_elsewhere", (found,)
                elif truncated:
                    state = "unknown"
        else:
            found = _find_symbol(repo, claim.entrypoints, max_files)
            if found:
                state, paths = "implemented_elsewhere", (found,)
            elif truncated:
                state = "unknown"
        evidence.append(
            ClaimEvidence(
                claim=claim,
                state=state,
                evidence_paths=paths,
                symbols=symbols,
                verified_at_commit=commit or "unknown",
            )
        )
    return evidence


def _count_artefacts(repo: Path, max_files: int) -> dict[str, int]:
    counts = {"source": 0, "schema": 0, "tests": 0, "docs": 0}
    files, _ = _walk_files(repo, max_files)
    for path in files:
        relative = _relative(repo, path).lower()
        suffix = path.suffix.lower()
        if suffix in SOURCE_SUFFIXES:
            counts["source"] += 1
            if relative.startswith(("tests/", "test/")) or path.name.startswith("test_"):
                counts["tests"] += 1
        elif suffix in SCHEMA_SUFFIXES:
            counts["schema"] += 1
        elif suffix in DOC_SUFFIXES:
            counts["docs"] += 1
    return counts


def assess_ratio(
    repo_path: Path, evidence: Sequence[ClaimEvidence], *, max_files: int = MAX_FILES_DEFAULT
) -> dict[str, object]:
    """Repository-level verdict merged from IDEA-500: implemented, brief, or docs-only."""
    repo = Path(repo_path).resolve()
    artefacts = _count_artefacts(repo, max_files)
    claims = len(evidence)
    implemented = sum(1 for row in evidence if row.state in {"implemented", "implemented_elsewhere"})
    absent = sum(1 for row in evidence if row.state == "absent")
    unknown = sum(1 for row in evidence if row.state == "unknown")
    stub = sum(1 for row in evidence if row.state == "stub")
    if claims == 0:
        verdict = "unknown"
    elif implemented == 0:
        verdict = "docs-only" if artefacts["source"] == 0 and artefacts["docs"] else "design-brief"
    elif implemented * 2 < claims:
        verdict = "design-brief"
    else:
        verdict = "implemented"
    if verdict == "unknown":
        confidence = "low"
    elif implemented == claims and absent == 0 and unknown == 0:
        confidence = "high"
    elif implemented:
        confidence = "medium"
    else:
        confidence = "low"
    return {
        "claims": claims,
        "implemented": implemented,
        "stub": stub,
        "absent": absent,
        "unknown": unknown,
        "artefacts": artefacts,
        "verdict": verdict,
        "confidence": confidence,
    }


def render_summary(verdict: dict[str, object]) -> str:
    artefacts = verdict.get("artefacts", {})
    if not isinstance(artefacts, dict):
        artefacts = {}
    return (
        f"claims {verdict.get('claims', 0)} · implemented {verdict.get('implemented', 0)} · "
        f"stub {verdict.get('stub', 0)} · absent {verdict.get('absent', 0)} · "
        f"unknown {verdict.get('unknown', 0)} · "
        f"artefacts source {artefacts.get('source', 0)}/schema {artefacts.get('schema', 0)}/"
        f"tests {artefacts.get('tests', 0)}/docs {artefacts.get('docs', 0)} · "
        f"verdict {verdict.get('verdict', 'unknown')} ({verdict.get('confidence', 'low')} confidence)"
    )


def render_table(evidence: Iterable[ClaimEvidence]) -> str:
    lines = [
        "| Module | State | Evidence | Symbols | Verified at |",
        "|---|---|---|---|---|",
    ]
    for row in evidence:
        symbols = row.symbols[:8]
        symbol_text = ", ".join(f"`{symbol}`" for symbol in symbols) or "—"
        if len(row.symbols) > len(symbols):
            symbol_text += f", … (+{len(row.symbols) - len(symbols)})"
        lines.append(
            "| {name} | {state} | {paths} | {symbols} | {commit} |".format(
                name=row.claim.name,
                state=row.state,
                paths=", ".join(f"`{path}`" for path in row.evidence_paths) or "—",
                symbols=symbol_text,
                commit=row.verified_at_commit,
            )
        )
    return "\n".join(lines)
