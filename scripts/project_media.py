"""
Project brand and screenshot media pipeline (ADR-235).

Brand assets are generated for every new project, reviewed before they are applied, and only
approved assets reach a README or the AegeanWorks dossier. Screenshots carry the commit they show,
so a capture can never silently outlive the code. The dossier manifest schema follows
`projects/AegeanWorks/docs/media/README.md`; no image is ever written into the dossier without an
approval record and a resolvable commit.
"""

import json
import os
import re
import shutil
import subprocess
import tempfile
import threading
import time
from contextlib import contextmanager
from functools import partial
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Dict, List, Optional, Sequence, Tuple
from urllib.parse import quote
from xml.etree import ElementTree
from xml.sax.saxutils import escape as xml_escape

from scripts.disruption_recovery import (
    ROOT_DIR,
    atomic_write_bytes,
    atomic_write_json,
    atomic_write_text,
    file_lock,
)
from scripts.marked_blocks import block_span, fenced, replace_block
from scripts.project_license import license_state
from scripts.project_publish import extract_readme_description, get_project_repo_url, run_command
from scripts.project_registry import (
    AIKIT_BADGE,
    AIKIT_INTEGRATED_BADGE,
    AIKIT_URL,
    LICENSE_CHOICES,
    ProjectError,
    config_path,
    load_config,
    repository_name,
)
from scripts.project_ui import detect_ui
from scripts.project_brand import brand_spec, logo_svg as brand_logo_svg, social_svg as brand_social_svg

MEDIA_SCHEMA = 1
MEDIA_REL = Path(".aikit") / "media.json"
LOGO_REL = Path("assets") / "logo.svg"
LOGO_PNG_REL = Path("assets") / "logo.png"
SOCIAL_REL = Path("assets") / "social-preview.svg"
SOCIAL_PNG_REL = Path("assets") / "social-preview.png"
SCREENSHOT_DIR = Path("assets") / "screenshots"
MEDIA_BLOCK = "media"
ASSET_DISCLOSURE = ("The banner and logo are **AI-generated brand assets**. They are illustrative "
                    "and may not literally depict every feature or the full project scope.")
BRAND_BLOCK = "brand-assets"
SHOT_BLOCK = "screenshots"
MAX_SCREENSHOTS = 12
PROCESS_TIMEOUT = 90
REVIEWER_PATTERN = re.compile(r"^(agent|subagent|human):[A-Za-z0-9_.:-]+$")
DATE_PATTERN = re.compile(r"^\d{4}-\d{2}-\d{2}$")
COMMIT_PATTERN = re.compile(r"^[0-9a-f]{7,40}$")
PNG_SIGNATURE = b"\x89PNG\r\n\x1a\n"


def media_path(root: Path) -> Path:
    return Path(root) / MEDIA_REL


def _head(root: Path) -> str:
    code, output = run_command(["git", "rev-parse", "HEAD"], root)
    return output.strip() if code == 0 else ""


def _description(root: Path, name: str) -> str:
    try:
        text = extract_readme_description(root)
    except (OSError, ValueError):
        text = ""
    if not text or "<FILL" in text or len(text.strip()) < 10:
        text = f"{repository_name(name)} — an AegeanWorks project."
    return text


def _palette(name: str) -> Tuple[str, str, str, str]:
    return brand_spec(name)["palette"]


def _logo_svg(name: str) -> str:
    return brand_logo_svg(name)


def _social_svg(name: str, kind: str, description: str, repo_url: str,
                tags: Sequence[str] = ()) -> str:
    return brand_social_svg(name, kind, description, repo_url, tags)


def _browser() -> Optional[Path]:
    for name in ("msedge", "chrome", "google-chrome", "chromium", "chromium-browser"):
        found = shutil.which(name)
        if found:
            return Path(found)
    candidates = [
        Path(os.getenv("PROGRAMFILES", "C:/Program Files")) / "Microsoft/Edge/Application/msedge.exe",
        Path(os.getenv("PROGRAMFILES(X86)", "C:/Program Files (x86)")) / "Microsoft/Edge/Application/msedge.exe",
        Path(os.getenv("PROGRAMFILES", "C:/Program Files")) / "Google/Chrome/Application/chrome.exe",
        Path(os.getenv("LOCALAPPDATA", "")) / "Google/Chrome/Application/chrome.exe",
    ]
    return next((path for path in candidates if path.is_file()), None)


class _QuietHandler(SimpleHTTPRequestHandler):
    """Serve one capture directory without writing request logs."""

    def log_message(self, fmt, *args):
        return


@contextmanager
def served_html(source: Path):
    """Yield an HTTP URL for an HTML page, or its file URL for any other asset.

    Headless Chromium batches requestAnimationFrame differently on file:// pages,
    so an app that paints after load can be captured before its first frame. HTML
    is served from a loopback port for the duration of the capture; SVG and other
    static assets keep the direct file URL.
    """
    page = Path(source)
    if page.suffix.lower() not in {".html", ".htm"}:
        yield page.resolve().as_uri()
        return
    handler = partial(_QuietHandler, directory=str(page.parent))
    server = ThreadingHTTPServer(("127.0.0.1", 0), handler)
    thread = threading.Thread(
        target=server.serve_forever, kwargs={"poll_interval": 0.01}, daemon=True
    )
    thread.start()
    try:
        port = server.server_address[1]
        yield f"http://127.0.0.1:{port}/{quote(page.name)}"
    finally:
        server.shutdown()
        server.server_close()
        thread.join(timeout=5)


def capture_html(source: Path, output: Path, width: int, height: int) -> Dict[str, object]:
    """Render a local SVG/HTML file with the installed browser, bounded by a timeout."""
    browser = _browser()
    if browser is None:
        raise ProjectError(
            "No headless browser is installed.",
            "screenshots and PNG social previews need Chromium, Chrome or Edge.",
            "install Microsoft Edge or Chrome, or commit an SVG asset and review it manually.",
        )
    output.parent.mkdir(parents=True, exist_ok=True)
    profile = Path(tempfile.mkdtemp(prefix="aegean_media_"))
    try:
        with served_html(source) as target:
            argv = [
                str(browser), "--headless=new", "--disable-gpu", "--hide-scrollbars",
                "--no-sandbox", "--allow-file-access-from-files", "--force-device-scale-factor=1",
                "--run-all-compositor-stages-before-draw", "--virtual-time-budget=1500",
                f"--user-data-dir={profile}",
                f"--window-size={width},{height}", f"--screenshot={output.resolve()}",
                target,
            ]
            try:
                done = subprocess.run(argv, stdin=subprocess.DEVNULL, capture_output=True, text=True,
                                      encoding="utf-8", errors="replace", timeout=PROCESS_TIMEOUT)
            except (OSError, subprocess.SubprocessError) as exc:
                raise ProjectError(
                    "The headless browser could not render the asset.",
                    str(exc),
                    "check that the browser starts outside AIKit, then retry the capture.",
                ) from exc
    finally:
        shutil.rmtree(profile, ignore_errors=True)
    if not output.is_file():
        raise ProjectError(
            "The browser did not write a screenshot.",
            (done.stdout + done.stderr).strip()[-400:] or "no output file was produced.",
            "retry with a local SVG/HTML file, or capture the screen manually.",
        )
    size = png_size(output)
    if size is None:
        raise ProjectError(
            "The screenshot is not a PNG.",
            "the browser wrote an unrecognized image format.",
            "remove the file and retry the capture.",
        )
    return {"path": str(output), "width": size[0], "height": size[1],
            "browser": str(browser)}


def jpeg_size(path: Path) -> Optional[Tuple[int, int]]:
    try:
        data = path.read_bytes()
    except OSError:
        return None
    if data[:2] != b"\xff\xd8":
        return None
    index = 2
    while index + 9 < len(data):
        if data[index] != 0xFF:
            index += 1
            continue
        marker = data[index + 1]
        if marker in (0xD8, 0xD9):
            index += 2
            continue
        length = int.from_bytes(data[index + 2:index + 4], "big")
        if marker in (0xC0, 0xC1, 0xC2, 0xC3, 0xC5, 0xC6, 0xC7, 0xC9, 0xCA, 0xCB,
                      0xCD, 0xCE, 0xCF):
            height = int.from_bytes(data[index + 5:index + 7], "big")
            width = int.from_bytes(data[index + 7:index + 9], "big")
            return width, height
        index += 2 + length
    return None


def image_size(path: Path) -> Optional[Tuple[int, int]]:
    if path.suffix.lower() == ".png":
        return png_size(path)
    if path.suffix.lower() in {".jpg", ".jpeg"}:
        return jpeg_size(path)
    return None


def png_size(path: Path) -> Optional[Tuple[int, int]]:
    try:
        data = path.read_bytes()[:24]
    except OSError:
        return None
    if len(data) < 24 or data[:8] != PNG_SIGNATURE:
        return None
    return int.from_bytes(data[16:20], "big"), int.from_bytes(data[20:24], "big")


def _validate_svg(path: Path, title: str) -> List[str]:
    try:
        tree = ElementTree.parse(path)
    except (OSError, ElementTree.ParseError) as exc:
        return [f"{path}: SVG does not parse ({exc})"]
    root = tree.getroot()
    problems = []
    if not root.tag.endswith("svg"):
        problems.append(f"{path}: root element is not svg")
    for node in root.iter():
        if node.tag.endswith("script"):
            problems.append(f"{path}: SVG contains a script element")
        for key, value in node.attrib.items():
            if key.endswith("href") and str(value).startswith(("http://", "https://")):
                problems.append(f"{path}: SVG references an external resource")
    text = path.read_text(encoding="utf-8", errors="replace")
    key = re.sub(r"[^a-z0-9]+", " ", title.lower()).strip()
    haystack = re.sub(r"[^a-z0-9]+", " ", text.lower())
    if key not in haystack:
        problems.append(f"{path}: SVG does not name the project")
    return problems


def _review_record(reviewer: str, method: str, notes: str, score: Optional[int]) -> Dict[str, object]:
    if not REVIEWER_PATTERN.match(reviewer):
        raise ProjectError(
            f"Invalid reviewer '{reviewer}'.",
            "a review must name who made the judgement: agent:<id>, subagent:<id> or human:<id>.",
            "pass --reviewer agent:<session> (or subagent/human) and retry.",
            exit_code=2,
        )
    if method not in {"vision", "structural"}:
        raise ProjectError(
            f"Unknown review method '{method}'.",
            "a review is either a vision judgement or a documented structural fallback.",
            "pass --method vision or --method structural.",
            exit_code=2,
        )
    if not notes.strip():
        raise ProjectError(
            "An approval needs review notes.",
            "a status without evidence cannot be audited later.",
            "pass --notes describing what you checked and why the asset fits the project.",
            exit_code=2,
        )
    return {"status": "approved", "reviewer": reviewer, "method": method,
            "notes": notes.strip(), "score": score, "reviewed_at": time.strftime("%Y-%m-%dT%H:%M:%S")}


def load_media(root: Path) -> Dict[str, object]:
    path = media_path(root)
    if not path.is_file():
        return {"schema": MEDIA_SCHEMA, "name": Path(root).name, "assets": {}, "screenshots": []}
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError) as exc:
        raise ProjectError(
            f"Cannot read {path}.",
            f"the media manifest is not valid JSON: {exc}",
            "restore it from git or remove it and re-run `media init`.",
        ) from exc
    if not isinstance(data, dict) or data.get("schema") != MEDIA_SCHEMA:
        raise ProjectError(
            f"{path} uses an unsupported media schema.",
            f"this AIKit reads schema {MEDIA_SCHEMA} only.",
            "regenerate the manifest with `media init`.",
        )
    data.setdefault("assets", {})
    data.setdefault("screenshots", [])
    return data


def dossier_logo_is_placeholder(manifest: object) -> bool:
    """True when a dossier media manifest still points at the generated fallback card."""
    return isinstance(manifest, dict) and bool((manifest.get("logo") or {}).get("generated"))


def media_blockers(root: Path, dossier: Optional[Path] = None) -> List[str]:
    """Assets that still need a review before a new project may be published."""
    if not media_path(root).is_file():
        return []
    data = load_media(root)
    assets = data.get("assets") or {}
    blockers = []
    for key in ("logo", "social_preview"):
        asset = assets.get(key)
        if not asset:
            blockers.append(f"{key} is missing")
        elif asset.get("status") != "approved":
            blockers.append(f"{key} is {asset.get('status') or 'unreviewed'}")
    dossier_root = Path(dossier) if dossier else ROOT_DIR / "projects" / "AegeanWorks"
    repo = repository_name(str(data.get("name") or root.name))
    manifest_path = dossier_root / "docs" / "media" / f"{repo}.json"
    if manifest_path.is_file():
        try:
            d_manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
        except (OSError, ValueError):  # hygiene: allow unreadable dossier manifest is ignored
            d_manifest = None
        if dossier_logo_is_placeholder(d_manifest):
            blockers.append("dossier logo is a fallback placeholder card")
    return blockers


def save_media(root: Path, data: Dict[str, object]) -> None:
    path = media_path(root)
    with file_lock(path):
        atomic_write_json(path, data)


def _asset(path: Path, commit: str, status: str = "pending_review") -> Dict[str, object]:
    return {"path": path.as_posix(), "status": status, "commit": commit,
            "generated_at": time.strftime("%Y-%m-%dT%H:%M:%S"), "review": None}


def seed_media_assets(project_root: Path, name: str, force: bool = False,
                      capture_png: bool = False) -> Dict[str, object]:
    """Generate candidate logo/social assets and a pending manifest; never touches the README."""
    root = Path(project_root)
    manifest_path = media_path(root)
    if manifest_path.is_file() and not force:
        return {"path": str(root), "created": False, "manifest": str(manifest_path)}
    existing = load_media(root) if manifest_path.is_file() else {}
    kept_screenshots = list(existing.get("screenshots") or [])
    ui = detect_ui(root)
    kind = str(ui.get("kind") or "library")
    description = _description(root, name)
    # Brand candidates are generated before the first commit (and before review), so they record
    # no commit stamp. Screenshots are the assets that must name the code they show.
    commit = ""
    logo = LOGO_REL
    social = SOCIAL_REL
    if force or not (root / logo).is_file():
        atomic_write_text(root / logo, _logo_svg(name), backup=False)
    if force or not (root / social).is_file():
        try:
            topics = load_config(root).get("topics") or []
        except (OSError, ValueError, KeyError, ProjectError):
            topics = []
        atomic_write_text(root / social, _social_svg(
            name, kind, description, f"github.com/AegeanWorks/{repository_name(name)}", topics),
            backup=False)
    assets: Dict[str, object] = {
        "logo": _asset(logo, commit),
        "social_preview": _asset(social, commit),
    }
    social_png = root / SOCIAL_PNG_REL
    if capture_png and _browser() is not None:
        try:
            capture_html(root / social, social_png, 1280, 640)
            assets["social_preview_png"] = _asset(SOCIAL_PNG_REL, commit)
        except ProjectError:  # hygiene: allow PNG rendering is optional; the SVG candidate remains
            pass
        logo_png = root / LOGO_PNG_REL
        try:
            capture_html(root / logo, logo_png, 512, 512)
            assets["logo_png"] = _asset(LOGO_PNG_REL, commit)
        except ProjectError:  # hygiene: allow PNG rendering is optional; the SVG candidate remains
            pass
    data = {
        "schema": MEDIA_SCHEMA,
        "name": name,
        "repo": repository_name(name),
        "has_ui": bool(ui.get("has_ui")),
        "ui_kind": kind,
        "palette": list(_palette(name)),
        "motif": brand_spec(name)["motif"],
        "layout": brand_spec(name)["layout"],
        "assets": assets,
        "screenshots": kept_screenshots,
    }
    save_media(root, data)
    return {"path": str(root), "created": True, "manifest": str(manifest_path),
            "assets": sorted(assets), "has_ui": data["has_ui"], "kind": kind}


def capture_screenshot(project_root: Path, name: str, url: Optional[str] = None,
                       viewport: str = "1440x900", force: bool = False) -> Dict[str, object]:
    """Capture a UI project at HEAD and register the image as pending review."""
    root = Path(project_root)
    ui = detect_ui(root)
    if not ui.get("has_ui"):
        raise ProjectError(
            f"'{name}' is not marked as a UI project.",
            "screenshots are attached only to projects whose identifier says a UI exists.",
            f"run `python aikit.py ui-id {name} --set yes` after confirming the interface, "
            "or `--set auto` after adding the UI markers.",
        )
    commit = _head(root)
    if not commit:
        raise ProjectError(
            f"'{name}' has no commit to stamp a screenshot with.",
            "a capture without a commit cannot be linked from the dossier.",
            "commit the project, then capture again.",
        )
    width, height = _parse_viewport(viewport)
    source = _surface(root, url, name)
    date = time.strftime("%Y-%m-%d")
    raw_slug = Path(url).stem if url else "home"
    slug = re.sub(r"[^a-z0-9]+", "-", raw_slug.lower()).strip("-")[:40] or "home"
    output = root / SCREENSHOT_DIR / f"{date}-{slug}.png"
    if output.exists() and not force:
        raise ProjectError(
            f"{output} already exists.",
            "a date-stamped capture is immutable; replacing it would hide what changed.",
            "pass --force to replace it deliberately, or capture on another day/URL.",
        )
    captured = capture_html(source, output, width, height)
    if (captured["width"], captured["height"]) != (width, height):
        raise ProjectError(
            "The capture dimensions do not match the requested viewport.",
            f"requested {width}x{height}, got {captured['width']}x{captured['height']}.",
            "retry with a supported viewport or check the browser's device scale.",
        )
    data = load_media(root)
    entry = {
        "path": output.relative_to(root).as_posix(),
        "alt": f"{repository_name(name)} interface at {date}",
        "caption": f"{repository_name(name)} interface captured from {url or source.name}",
        "commit": commit,
        "taken_at": date,
        "viewport": viewport,
        "width": width,
        "height": height,
        "status": "pending_review",
        "review": None,
    }
    data["screenshots"] = (list(data.get("screenshots") or []) + [entry])[-MAX_SCREENSHOTS:]
    save_media(root, data)
    return {"path": str(output), **entry}


def _parse_viewport(value: str) -> Tuple[int, int]:
    match = re.fullmatch(r"(\d{2,5})x(\d{2,5})", value.strip())
    if not match:
        raise ProjectError(
            f"Invalid viewport '{value}'.",
            "a viewport is WIDTHxHEIGHT, for example 1440x900.",
            "pass --viewport 1440x900.",
            exit_code=2,
        )
    width, height = int(match.group(1)), int(match.group(2))
    if width > 8000 or height > 8000:
        raise ProjectError("The viewport is too large.", "the dossier caps images at 8000px.",
                           "pass a viewport of at most 8000x8000.", exit_code=2)
    return width, height


def _surface(root: Path, url: Optional[str], name: str) -> Path:
    if url:
        path = Path(url)
        if path.is_file():
            return path
        raise ProjectError(
            f"{url} is not a local file.",
            "the capture is offline and commit-stamped; it does not fetch a remote app.",
            f"start the {name} UI locally and pass its index.html path with --url.",
            exit_code=2,
        )
    for candidate in ("docs/index.html", "index.html", "public/index.html", "web/index.html",
                      "src/index.html", "app.html"):
        path = root / candidate
        if path.is_file():
            return path
    raise ProjectError(
        f"No UI entry point was found for '{name}'.",
        "the identifier says this project has a UI, but no index.html is discoverable.",
        "pass the local entry point with `--url <file>`; a server-only UI needs a static export.",
    )


def _find_asset(data: Dict[str, object], kind: str, index: Optional[int]) -> Tuple[Dict[str, object], str]:
    if kind == "screenshot":
        shots = data.get("screenshots") or []
        if not shots:
            raise ProjectError("There are no screenshots to review.", "capture one first.",
                               "run `python aikit.py media capture <name>`.")
        position = (index or len(shots)) - 1
        if not 0 <= position < len(shots):
            raise ProjectError(f"Screenshot {index} does not exist.", "indexes are 1-based.",
                               "run `media status` to list the captures.", exit_code=2)
        return shots[position], f"screenshots[{position}]"
    assets = data.get("assets") or {}
    if kind not in assets:
        raise ProjectError(
            f"No {kind} asset exists.",
            "the manifest has no candidate for that asset.",
            f"run `python aikit.py media init <name> --force` to generate it.",
        )
    return assets[kind], f"assets.{kind}"


def review_media(project_root: Path, kind: str, decision: str, reviewer: str, method: str,
                 notes: str, score: Optional[int] = None, index: Optional[int] = None) -> Dict[str, object]:
    """Validate the asset, then record an approve/reject decision with its evidence."""
    root = Path(project_root)
    data = load_media(root)
    asset, label = _find_asset(data, kind, index)
    path = root / str(asset.get("path") or "")
    if not path.is_file():
        raise ProjectError(
            f"{path} is missing.",
            "an asset cannot be reviewed without its file.",
            "regenerate the asset, then review it again.",
        )
    problems: List[str] = []
    if kind in {"logo", "social_preview"} and path.suffix.lower() in {".png", ".jpg", ".jpeg"}:
        size = image_size(path)
        expected = (1024, 1024) if kind == "logo" else (1280, 640)
        if size is None:
            problems = [f"{path}: not a readable image"]
        elif kind == "logo" and not (size[0] == size[1] and size[0] >= 512):
            problems = [f"{path}: expected a square logo, got {size[0]}x{size[1]}"]
        elif kind == "social_preview" and size != expected:
            problems = [f"{path}: expected 1280x640, got {size[0]}x{size[1]}"]
    elif kind in {"logo", "social_preview"}:
        problems = _validate_svg(path, str(data.get("name") or root.name))
    elif kind == "social_preview_png":
        size = png_size(path)
        if size is None:
            problems = [f"{path}: not a PNG"]
        elif size != (1280, 640):
            problems = [f"{path}: expected 1280x640, got {size[0]}x{size[1]}"]
    elif kind == "logo_png":
        size = png_size(path)
        if size is None:
            problems = [f"{path}: not a PNG"]
        elif size != (512, 512):
            problems = [f"{path}: expected 512x512, got {size[0]}x{size[1]}"]
    else:
        size = png_size(path)
        if size is None:
            problems = [f"{path}: not a PNG"]
        commit = str(asset.get("commit") or "")
        if not COMMIT_PATTERN.match(commit):
            problems.append(f"{path}: the screenshot has no commit stamp")
        else:
            code, _ = run_command(["git", "cat-file", "-e", f"{commit}^{{commit}}"], root)
            if code != 0:
                problems.append(f"{path}: commit {commit[:12]} does not resolve")
        if not DATE_PATTERN.match(str(asset.get("taken_at") or "")):
            problems.append(f"{path}: the capture date is missing or invalid")
    if problems:
        raise ProjectError(
            "The asset did not pass structural review.",
            "; ".join(problems[:5]),
            "fix the asset or regenerate it; nothing was approved.",
        )
    if decision == "approve":
        record = _review_record(reviewer, method, notes, score)
    elif decision == "reject":
        if not notes.strip():
            raise ProjectError("A rejection needs a reason.", "the next review needs to know what failed.",
                               "pass --notes with the reason.", exit_code=2)
        record = {"status": "rejected", "reviewer": reviewer, "method": method,
                  "notes": notes.strip(), "score": score,
                  "reviewed_at": time.strftime("%Y-%m-%dT%H:%M:%S")}
    else:
        raise ProjectError(f"Unknown decision '{decision}'.", "use approve or reject.",
                           "pass --decision approve or --decision reject.", exit_code=2)
    asset["status"] = record["status"]
    asset["review"] = record
    save_media(root, data)
    return {"project": name_of(root), "kind": kind, "label": label, "status": record["status"],
            "asset": str(path), "review": record}


def name_of(root: Path) -> str:
    if not config_path(root).is_file():
        # A standalone repository (for example Aegean Reforge itself) has media but no AIKit memory.
        return Path(root).name
    try:
        return str(load_config(root).get("name") or Path(root).name)
    except (OSError, ValueError, KeyError):
        return Path(root).name


def _approved(asset: object) -> bool:
    """True only for a reviewed, approved asset entry; a missing entry is simply not approved."""
    return (isinstance(asset, dict) and asset.get("status") == "approved"
            and isinstance(asset.get("review"), dict))


def _copy_media(source: Path, target: Path) -> None:
    target.parent.mkdir(parents=True, exist_ok=True)
    atomic_write_bytes(target, source.read_bytes(), backup=False)


def apply_media(project_root: Path, name: str, dossier: Optional[Path] = None) -> Dict[str, object]:
    """Copy approved assets into the dossier and reference them from the project README."""
    root = Path(project_root)
    data = load_media(root)
    repo = repository_name(name)
    dossier_root = Path(dossier) if dossier else ROOT_DIR / "projects" / "AegeanWorks"
    media_dir = dossier_root / "docs" / "media" / repo
    manifest_path = dossier_root / "docs" / "media" / f"{repo}.json"
    if not dossier_root.is_dir():
        raise ProjectError(
            f"The dossier root {dossier_root} does not exist.",
            "approved media is published through the AegeanWorks dossier.",
            "pass --dossier <AegeanWorks path>, or create the dossier first.",
        )
    applied: List[str] = []
    existing_manifest: Dict[str, object] = {}
    if manifest_path.is_file():
        try:
            existing = json.loads(manifest_path.read_text(encoding="utf-8"))
        except (OSError, ValueError):  # hygiene: allow broken-dossier manifests to rebuild from approved assets
            existing = None
        if isinstance(existing, dict):
            schema = existing.get("schema")
            if schema != MEDIA_SCHEMA:
                # The dossier's own builder owns any other schema; rewriting it as schema 1
                # would drop the preview, screenshot captures and their digests.
                raise ProjectError(
                    f"{manifest_path} uses dossier schema {schema!r}, which AIKit does not write.",
                    "that manifest is generated by the dossier's own media builder, so a schema 1 "
                    "rewrite would delete its preview, screenshots, commit stamps and digests, and "
                    "the published page would silently lose the project's media.",
                    "record this asset with the dossier's builder (for AegeanWorks, "
                    "`python tools/build_dossier_media.py ingest`), or delete the manifest "  # hygiene: allow path inside the AegeanWorks project, not AIKit
                    "deliberately before applying.",
                )
            existing_manifest = existing
    dossier: Dict[str, object] = {"schema": MEDIA_SCHEMA, "repo": repo, "screenshots": []}
    dossier.update(existing_manifest)
    assets = data.get("assets") or {}
    logo = assets.get("logo")
    logo_png = assets.get("logo_png")
    if _approved(logo):
        source = root / str(logo["path"])
        target = media_dir / f"logo{source.suffix.lower()}"
        _copy_media(source, target)
        dossier["logo"] = {"src": f"media/{repo}/{target.name}", "alt": f"{repo} logo"}
        applied.append(str(target))
        if _approved(logo_png):
            png_source = root / str(logo_png["path"])
            if png_source.is_file():
                png_target = media_dir / "logo.png"
                _copy_media(png_source, png_target)
                applied.append(str(png_target))
    approved_shots = []
    for shot in data.get("screenshots") or []:
        if not _approved(shot):
            continue
        source = root / str(shot["path"])
        if not source.is_file():
            continue
        target = media_dir / source.name
        _copy_media(source, target)
        approved_shots.append({
            "src": f"media/{repo}/{source.name}",
            "alt": str(shot.get("alt") or f"{repo} screenshot"),
            "caption": str(shot.get("caption") or shot.get("alt") or ""),
            "commit": str(shot.get("commit") or "")[:7],
            "taken_at": str(shot.get("taken_at") or ""),
            "viewport": str(shot.get("viewport") or ""),
            "width": int(shot.get("width") or 0),
            "height": int(shot.get("height") or 0),
        })
        applied.append(str(target))
    dossier["screenshots"] = approved_shots[:MAX_SCREENSHOTS]
    atomic_write_text(manifest_path, json.dumps(dossier, indent=2) + "\n", backup=False)
    applied.append(str(manifest_path))
    readme = root / "README.md"
    if readme.is_file():
        _update_readme(readme, repo, data, approved_shots)
        applied.append(str(readme))
    return {"project": name, "repo": repo, "applied": applied,
            "logo": bool(_approved(logo)), "screenshots": len(approved_shots),
            "manifest": str(manifest_path)}


def _badge_row(project_root: Path, repo: str = "") -> str:
    """License and AIKit badges under the banner; AegeanWorks keeps its own badge set."""
    if repo.strip().lower() == "aegeanworks":
        return ""
    try:
        state = license_state(project_root)
    except (ProjectError, OSError, ValueError):
        # Standalone Aegean Reforge has a LICENSE but no AIKit project memory.
        class _Default:
            tier = "personal"
            kind = "software"
        state = _Default()
    if state.tier == "restricted":
        label, color = "All_Rights_Reserved", "b60205"
    else:
        license_id = LICENSE_CHOICES.get(state.kind or "software",
                                        LICENSE_CHOICES["software"])["key"]
        label = license_id.replace("-", "--")
        color = "2f9e44" if state.kind == "software" else (
            "7048e8" if state.kind == "game" else "1c7ed6")
    license_badge = (
        f'<a href="LICENSE"><img src="https://img.shields.io/badge/license-{label}-{color}" '
        f'alt="License"></a>')
    aikit_badge = (
        f'<a href="{AIKIT_URL}"><img '
        'src="https://img.shields.io/badge/AIKit-integrated-6f42c1" '
        'alt="AIKit Integrated"></a>')
    return f'<p align="center">{license_badge} {aikit_badge}</p>'


def _update_readme(readme: Path, repo: str, data: Dict[str, object],
                   shots: Sequence[Dict[str, object]]) -> None:
    text = readme.read_text(encoding="utf-8")
    assets = data.get("assets") or {}
    pieces = []
    if _approved(assets.get("social_preview")):
        social_src = str(assets["social_preview"].get("path") or "assets/social-preview.png").replace("\\", "/")
        pieces.append(f'<p align="center"><img src="{social_src}" '
                      f'alt="{repo} social preview" width="100%"></p>')
        badges = _badge_row(readme.parent, repo)
        if badges:
            pieces.append(badges)
    if pieces:
        body = "\n".join(pieces)
        replaced = replace_block(text, MEDIA_BLOCK, body)
        if replaced is None:
            lines = text.splitlines(keepends=True)
            at = next((index + 1 for index, line in enumerate(lines) if line.startswith("# ")), 0)
            replaced = "".join(lines[:at]) + "\n" + fenced(MEDIA_BLOCK, body) + "\n" + "".join(lines[at:])
        text = replaced
    if shots:
        cells = []
        for shot in shots:
            cells.append(
                f'<a href="https://github.com/AegeanWorks/{repo}/commit/{shot["commit"]}">'
                f'<img src="assets/screenshots/{Path(shot["src"]).name}" '
                f'alt="{xml_escape(shot["alt"])}"></a>\n\n'
                f'*commit `{shot["commit"]}` · {shot["taken_at"]}*'
            )
        body = "## Screenshots\n\n" + "\n\n".join(cells)
        replaced = replace_block(text, SHOT_BLOCK, body)
        text = replaced if replaced is not None else (
            text.rstrip("\n") + "\n\n" + fenced(SHOT_BLOCK, body) + "\n")
    else:
        span = block_span(text, SHOT_BLOCK)
        if span is not None:
            text = text[:span[0]].rstrip("\n") + "\n" + text[span[1]:].lstrip("\n")
    # An older banner line would duplicate the single social preview. Remove legacy banner embeds
    # outside our marker, leaving ordinary prose that merely mentions a banner untouched.
    lines = []
    for line in text.splitlines(keepends=True):
        stripped = line.strip()
        if (("banner." in stripped and (stripped.startswith("<img") or stripped.startswith("![")))
                or ("banner." in stripped and stripped.startswith("<p"))):
            continue
        if stripped in {f"*{ASSET_DISCLOSURE}*", ASSET_DISCLOSURE,
                        "*Brand assets are generated and may not fully represent the project scope.*",
                        "*The banner and logo are AI-generated brand assets. They are illustrative "
                        "and may not literally depict every feature or the full project scope.*",
                        AIKIT_BADGE, AIKIT_INTEGRATED_BADGE}:
            continue
        lines.append(line)
    text = "".join(lines)
    body = f"## 🎨 Brand Assets\n\n> **AI-Generated Brand Artwork.** {ASSET_DISCLOSURE}"
    section = fenced(BRAND_BLOCK, body) + "\n"
    replaced = replace_block(text, BRAND_BLOCK, body)
    if replaced is not None:
        text = replaced
    else:
        license_heading = re.search(r"(?im)^##[^\n]*licen[cs]e[^\n]*\n", text)
        if license_heading:
            index = license_heading.start()
            text = text[:index] + section + "\n" + text[index:]
        else:
            text = text.rstrip("\n") + "\n\n" + section
    atomic_write_text(readme, text, backup=False)


def audit_media(project_root: Path, dossier: Optional[Path] = None) -> Dict[str, object]:
    """Check the manifest, files, commit stamps, dossier links and README references."""
    root = Path(project_root)
    data = load_media(root)
    name = str(data.get("name") or root.name)
    repo = repository_name(name)
    dossier_root = Path(dossier) if dossier else ROOT_DIR / "projects" / "AegeanWorks"
    problems = []
    pending = 0
    assets = data.get("assets") or {}
    for key in ("logo", "social_preview", "social_preview_png"):
        asset = assets.get(key)
        if not asset:
            continue
        if not (root / str(asset.get("path") or "")).is_file():
            problems.append(f"assets.{key}: file is missing")
        if asset.get("status") != "approved":
            pending += 1
    for shot in data.get("screenshots") or []:
        if shot.get("status") != "approved":
            pending += 1
        if not (root / str(shot.get("path") or "")).is_file():
            problems.append(f"screenshot {shot.get('path')}: file is missing")
        if not COMMIT_PATTERN.match(str(shot.get("commit") or "")):
            problems.append(f"screenshot {shot.get('path')}: commit stamp is invalid")
    manifest_path = dossier_root / "docs" / "media" / f"{repo}.json"
    dossier_manifest = None
    if manifest_path.is_file():
        try:
            dossier_manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            problems.append(f"{manifest_path}: dossier manifest is not valid JSON")
        if dossier_logo_is_placeholder(dossier_manifest):
            problems.append(f"{manifest_path}: dossier logo is a fallback placeholder card (authentic artwork required)")
    readme = root / "README.md"
    readme_text = readme.read_text(encoding="utf-8") if readme.is_file() else ""
    social_path = str((assets.get("social_preview") or {}).get("path") or "")
    if _approved(assets.get("social_preview")) and social_path not in readme_text:
        problems.append("README does not reference the approved social preview")
    if _approved(assets.get("logo")) and "assets/logo" in readme_text:
        problems.append("README shows the logo hero; only the social preview belongs there")
    if block_span(readme_text, BRAND_BLOCK) is None or "## 🎨 Brand Assets" not in readme_text:
        problems.append("README lacks the Brand Assets section")
    if "ai-generated brand assets" not in readme_text.lower():
        problems.append("README lacks the generated-asset disclosure")
    # `apply` writes the badge row with the banner, so a project with no approved
    # social preview must not be failed for badges that were never inserted.
    if repo.strip().lower() != "aegeanworks" and _approved(assets.get("social_preview")):
        if "img.shields.io/badge/license-" not in readme_text:
            problems.append("README lacks the license badge under the banner")
        if "AIKit-integrated" not in readme_text:
            problems.append("README lacks the AIKit Integrated badge under the banner")
    return {"project": name, "repo": repo, "ok": not problems, "problems": problems,
            "pending": pending, "dossier": str(manifest_path) if dossier_manifest else "",
            "dossier_screenshots": len((dossier_manifest or {}).get("screenshots") or [])}


def media_status(project_root: Path) -> Dict[str, object]:
    root = Path(project_root)
    data = load_media(root)
    assets = data.get("assets") or {}
    return {
        "project": str(data.get("name") or root.name),
        "repo": repository_name(str(data.get("name") or root.name)),
        "has_ui": bool(data.get("has_ui")),
        "ui_kind": data.get("ui_kind"),
        "assets": {key: {"path": value.get("path"), "status": value.get("status")}
                   for key, value in assets.items()},
        "screenshots": [{"path": shot.get("path"), "status": shot.get("status"),
                         "commit": shot.get("commit"), "taken_at": shot.get("taken_at")}
                        for shot in data.get("screenshots") or []],
        "manifest": str(media_path(root)),
    }
