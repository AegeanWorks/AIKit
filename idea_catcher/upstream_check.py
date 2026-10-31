"""Read-only upstream revalidation for dossier headers.

The register records a URL, a licence and an analysed commit for every source. Those
facts age silently. This module compares them with the live repository, but only when
an explicit ``revalidate`` command asks for it: importing the module and running the
offline gate never touch the network. The fetch callable is injected, so tests never
do either.
"""

from __future__ import annotations

import datetime
import json
import os
import re
import tempfile
from pathlib import Path
from typing import Any, Callable, Mapping

GITHUB_API = "https://api.github.com"
HEADER_LIMIT = 4_000
URL_RE = re.compile(r"https?://github\.com/([A-Za-z0-9_.-]+)/([A-Za-z0-9_.-]+)")
DATE_RE = re.compile(r"\b(\d{4}-\d{2}-\d{2})\b")
SHA_RE = re.compile(r"^[0-9a-fA-F]{7,40}$")
TICK_RE = re.compile(r"`([^`]+)`")

LICENCE_ALIASES = {
    "mit": "MIT",
    "mit license": "MIT",
    "apache-2.0": "Apache-2.0",
    "apache license 2.0": "Apache-2.0",
    "agpl-3.0": "AGPL-3.0",
    "agpl-3.0-only": "AGPL-3.0",
    "agpl-3.0-or-later": "AGPL-3.0",
    "gpl-3.0": "GPL-3.0",
    "gpl-3.0-only": "GPL-3.0",
    "gpl-3.0-or-later": "GPL-3.0",
    "lgpl-3.0": "LGPL-3.0",
    "bsd-2-clause": "BSD-2-Clause",
    "bsd-3-clause": "BSD-3-Clause",
    "cc0-1.0": "CC0-1.0",
    "cc-by-4.0": "CC-BY-4.0",
    "mpl-2.0": "MPL-2.0",
    "unlicense": "Unlicense",
    "noassertion": "NOASSERTION",
}
NO_LICENCE_PHRASES = (
    "none declared",
    "no license file",
    "no licence file",
    "no license grant",
    "no licence grant",
    "noassertion",
)

Fetch = Callable[[str], dict[str, Any]]


class UpstreamError(RuntimeError):
    """The upstream API could not be reached or answered with an error."""


def _header_text(text: str) -> str:
    return text[:HEADER_LIMIT].split("\n## ", 1)[0]


def _field(text: str, label: str) -> str:
    match = re.search(
        r"^- \*\*" + re.escape(label) + r"\*\*:[ \t]*(.+?)[ \t]*$", text, re.M
    )
    return match.group(1).strip() if match else ""


def _first_tick(value: str) -> str:
    match = TICK_RE.search(value)
    return match.group(1).strip() if match else ""


def normalise_licence(value: str) -> str:
    """Turn a messy header licence into one comparable SPDX-ish token."""
    text = str(value or "").strip().strip("`").strip()
    if not text:
        return ""
    lowered = text.lower()
    if any(phrase in lowered for phrase in NO_LICENCE_PHRASES):
        return "NOASSERTION"
    token = re.split(r"[\s(]", lowered, maxsplit=1)[0].strip(".,;")
    return LICENCE_ALIASES.get(token, token)


def _licence_key(value: str) -> str:
    return normalise_licence(value).lower().replace("-only", "").replace("-or-later", "")


def parse_header(text: str) -> dict[str, str]:
    """Read the three upstream facts from a dossier's opening block."""
    header = _header_text(text)
    url = ""
    url_match = URL_RE.search(_field(header, "Source URL"))
    if url_match:
        url = url_match.group(0).rstrip("/").removesuffix(".git")

    licence = normalise_licence(_first_tick(_field(header, "Source License")) or _field(header, "Source License"))

    analysed = _field(header, "Analyzed Commit / Date")
    tokens = [token.strip() for token in TICK_RE.findall(analysed) if token.strip()]
    date = next((token for token in tokens if DATE_RE.fullmatch(token)), "")
    if not date:
        date_match = DATE_RE.search(analysed)
        date = date_match.group(1) if date_match else ""
    commit = next((token for token in tokens if SHA_RE.fullmatch(token)), "")
    ref = next((token for token in tokens if token != date and token != commit), "")
    if not tokens:
        commit_match = re.search(r"\b([0-9a-fA-F]{7,40})\b", analysed)
        commit = commit_match.group(1) if commit_match else ""
    return {"url": url, "licence": licence, "commit": commit, "date": date, "ref": ref}


def repo_from_url(url: str) -> str:
    """Return ``owner/name`` for a GitHub URL, or an empty string."""
    match = URL_RE.search(str(url or ""))
    if not match:
        return ""
    return f"{match.group(1)}/{match.group(2).removesuffix('.git')}"


def _is_missing(payload: Mapping[str, Any]) -> bool:
    return payload.get("status") == 404 or str(payload.get("message", "")).lower() == "not found"


def _nested(payload: Mapping[str, Any], *keys: str) -> Any:
    value: Any = payload
    for key in keys:
        if not isinstance(value, Mapping):
            return None
        value = value.get(key)
    return value


def resolve_upstream(repo: str, fetch: Fetch, *, commit: str = "") -> dict[str, Any]:
    """Fetch the current facts for one repository with an injected fetch callable."""
    meta = fetch(f"{GITHUB_API}/repos/{repo}")
    if _is_missing(meta):
        return {"missing": True}
    full_name = str(meta.get("full_name") or repo)
    moved_to = str(meta.get("moved_to") or "")
    if not moved_to and full_name.lower() != repo.lower():
        moved_to = full_name
    branch = str(meta.get("default_branch") or "main")
    latest = fetch(f"{GITHUB_API}/repos/{repo}/commits/{branch}")
    if _is_missing(latest):
        latest = {}
    latest_sha = str(latest.get("sha") or "")
    latest_date = str(_nested(latest, "commit", "committer", "date") or "")
    commits_behind: int | None = None
    if commit and SHA_RE.fullmatch(commit):
        compare = fetch(f"{GITHUB_API}/repos/{repo}/compare/{commit}...{branch}")
        if not _is_missing(compare):
            ahead = compare.get("ahead_by")
            if isinstance(ahead, int) and not isinstance(ahead, bool):
                commits_behind = ahead
    return {
        "missing": False,
        "archived": bool(meta.get("archived")),
        "licence": str(_nested(meta, "license", "spdx_id") or ""),
        "moved_to": moved_to,
        "default_branch": branch,
        "latest_commit": latest_sha,
        "latest_date": latest_date,
        "commits_behind": commits_behind,
    }


def diff_upstream(recorded: Mapping[str, str], current: Mapping[str, Any]) -> dict[str, Any]:
    """Classify the difference between the dossier and the live repository."""
    recorded_licence = normalise_licence(str(recorded.get("licence", "")))
    current_licence = normalise_licence(str(current.get("licence", "")))
    result: dict[str, Any] = {
        "state": "current",
        "recorded_licence": recorded_licence,
        "current_licence": current_licence,
        "moved_to": "",
        "commits_behind": None,
    }
    if current.get("missing"):
        result["state"] = "missing"
        return result
    moved_to = str(current.get("moved_to", "") or "")
    behind = current.get("commits_behind")
    result["moved_to"] = moved_to
    result["commits_behind"] = behind if isinstance(behind, int) else None
    if _licence_key(recorded_licence) and _licence_key(current_licence):
        if _licence_key(recorded_licence) != _licence_key(current_licence):
            result["state"] = "licence_changed"
            return result
    if moved_to:
        result["state"] = "moved"
    elif current.get("archived"):
        result["state"] = "archived"
    elif isinstance(behind, int) and behind > 0:
        result["state"] = "analysis_behind"
    return result


def is_failure(result: Mapping[str, Any]) -> bool:
    """Only a licence change or a vanished repository fails ``--strict``."""
    return result.get("state") in {"licence_changed", "missing"}


def render_report(results: list[Mapping[str, Any]]) -> str:
    """Render one compact table for the terminal."""
    counts: dict[str, int] = {}
    for row in results:
        state = str(row.get("state", "unknown"))
        counts[state] = counts.get(state, 0) + 1
    summary = " · ".join(f"{count} {state}" for state, count in sorted(counts.items()))
    lines = [
        f"{len(results)} dossier(s) checked · {summary or 'nothing to check'}",
        "",
        "| Dossier | Repository | State | Recorded licence | Current licence | Moved to | Commits behind |",
        "|---|---|---|---|---|---|---|",
    ]
    for row in results:
        lines.append(
            "| {dossier} | `{repo}` | {state} | {recorded} | {current} | {moved} | {behind} |".format(
                dossier=row.get("dossier", "—"),
                repo=row.get("repo", "—"),
                state=row.get("state", "unknown"),
                recorded=row.get("recorded_licence") or "—",
                current=row.get("current_licence") or "—",
                moved=row.get("moved_to") or "—",
                behind=row.get("commits_behind") if row.get("commits_behind") is not None else "—",
            )
        )
    return "\n".join(lines)


def _cache_path(cache_dir: Path, repo: str) -> Path:
    return cache_dir / (repo.replace("/", "__") + ".json")


def _load_cache(path: Path, today: str) -> dict[str, Any] | None:
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return None
    if payload.get("date") != today:
        return None
    current = payload.get("current")
    return dict(current) if isinstance(current, dict) else None


def _store_cache(path: Path, today: str, current: Mapping[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    payload = json.dumps({"date": today, "current": dict(current)}, ensure_ascii=False, sort_keys=True) + "\n"
    handle, temporary = tempfile.mkstemp(prefix=path.name + ".tmp_", dir=path.parent)
    try:
        with os.fdopen(handle, "w", encoding="utf-8", newline="\n") as stream:
            stream.write(payload)
            stream.flush()
            os.fsync(stream.fileno())
        os.replace(temporary, path)
    finally:
        if os.path.exists(temporary):
            os.unlink(temporary)


def run_revalidation(
    root: Path,
    *,
    fetch: Fetch | None = None,
    today: str = "",
    cache_dir: Path | None = None,
    limit: int = 0,
) -> list[dict[str, Any]]:
    """Check every dossier header, reusing a same-day cache and never editing a dossier."""
    today = today or datetime.date.today().isoformat()
    cache = cache_dir or (root / ".aikit" / "upstream-cache")
    fetch = fetch or github_fetch
    results: list[dict[str, Any]] = []
    requests = 0
    for path in sorted((root / "dossiers").glob("*.md")):
        if path.name == "TEMPLATE.md":
            continue
        text = path.read_text(encoding="utf-8")
        header = parse_header(text)
        repo = repo_from_url(header["url"])
        dossier = str(path.relative_to(root)).replace("\\", "/")
        if not repo:
            results.append({"dossier": dossier, "repo": "", "state": "skipped",
                            "recorded_licence": header["licence"], "current_licence": "",
                            "moved_to": "", "commits_behind": None})
            continue
        cached = _load_cache(_cache_path(cache, repo), today)
        if cached is not None:
            current = cached
        elif limit and requests >= limit:
            results.append({"dossier": dossier, "repo": repo, "state": "skipped",
                            "recorded_licence": header["licence"], "current_licence": "",
                            "moved_to": "", "commits_behind": None})
            continue
        else:
            try:
                current = resolve_upstream(repo, fetch, commit=header["commit"])
            except UpstreamError as error:
                results.append({"dossier": dossier, "repo": repo, "state": "error",
                                "recorded_licence": header["licence"], "current_licence": "",
                                "moved_to": "", "commits_behind": None, "error": str(error)})
                requests += 1
                continue
            requests += 1
            _store_cache(_cache_path(cache, repo), today, current)
        diff = diff_upstream(header, current)
        results.append({"dossier": dossier, "repo": repo, **diff})
    return results


def github_fetch(url: str) -> dict[str, Any]:
    """Default network fetch: stdlib only, optional token, polite timeout."""
    # Imported here so `aikit.py --help` does not pay for http.client/ssl on every start.
    import urllib.error
    import urllib.request

    headers = {
        "Accept": "application/vnd.github+json",
        "User-Agent": "idea-catcher-revalidate",
    }
    token = os.environ.get("GITHUB_TOKEN") or os.environ.get("GH_TOKEN")
    if token:
        headers["Authorization"] = f"Bearer {token}"
    request = urllib.request.Request(url, headers=headers)
    try:
        with urllib.request.urlopen(request, timeout=10) as response:
            return json.loads(response.read().decode("utf-8"))
    except urllib.error.HTTPError as error:
        if error.code == 404:
            return {"status": 404, "message": "Not Found"}
        if error.code in (403, 429):
            raise UpstreamError(
                "GitHub rate limit reached; set GITHUB_TOKEN for a higher limit or retry later"
            ) from error
        raise UpstreamError(f"GitHub returned HTTP {error.code} for {url}") from error
    except (urllib.error.URLError, TimeoutError, ValueError) as error:
        raise UpstreamError(f"cannot reach GitHub: {error}") from error
