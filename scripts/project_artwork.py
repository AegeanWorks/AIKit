"""
Image-model brand artwork for projects (ADR-239).

The image model supplies a unique abstract hero image; the exact project name, monogram, tagline
and topics are rendered over it by the local browser. Text therefore stays crisp and unclipped,
while the artwork gives each project a distinct, premium visual identity. Generated assets remain
pending until an agent/subagent/human reviews them.
"""

import hashlib
import html
import os
import re
import time
import urllib.error
import urllib.parse
import urllib.request
from pathlib import Path
from typing import Dict, List, Optional, Sequence, Tuple

from scripts.project_brand import brand_spec
from scripts.project_media import capture_html, load_media, media_path, save_media
from scripts.project_registry import ProjectError, repository_name

ART_REL = Path("assets") / "artwork.jpg"
LOGO_PNG_REL = Path("assets") / "logo.png"
SOCIAL_PNG_REL = Path("assets") / "social-preview.png"
ART_TIMEOUT = 300
RETRY_STATUS = {402, 429, 500, 502, 503, 504}
# Pollinations' free endpoint allows one image every 45 seconds per IP. Serialize explicitly so a
# bulk run does not burn retries; a failed request still leaves the previous approved assets intact.
MIN_INTERVAL_SECONDS = 50.0
_LAST_FETCH = 0.0
MOTIF_PROMPT = {
    "grid": "a precise architectural grid with glowing seams",
    "network": "an interconnected network of luminous nodes",
    "brain": "a stylized neural structure of fine filaments",
    "atom": "an orbital scientific structure with intersecting rings",
    "pulse": "a clean oscilloscope pulse crossing a dark field",
    "stack": "layered translucent planes receding into depth",
    "eye": "a stylized optical lens with concentric rings",
    "book": "layered paper planes and a quiet editorial structure",
    "calendar": "a precise modular grid with highlighted cells",
    "shield": "a faceted protective shield form",
    "aegis": "a minimal geometric gate archway holding a checkpoint diamond, governance and delivery gates",
    "key": "a precise key-and-lock geometry",
    "compass": "a navigational compass rose over a dark field",
    "timer": "concentric time rings with a single marker",
    "terminal": "a minimal terminal pane with luminous code-like glyphs",
    "fold": "folded geometric planes and sharp creases",
    "gauge": "a scientific gauge arc with fine measurement marks",
    "bulb": "a filament-and-light form in a dark field",
    "lens": "a precise lens with refracted light",
    "waveform": "a refined audio waveform with layered harmonics",
    "leaf": "organic leaf veins rendered as precise geometry",
    "orbit": "concentric orbital paths and a small planet",
    "camera": "a camera aperture rendered as precise geometry",
    "prism": "a glass prism splitting a beam of light",
    "flask": "a scientific flask with luminous liquid",
    "branch": "a branching commit graph with luminous nodes",
    "wand": "a slender conductor with geometric sparks",
    "certificate": "a formal document with a wax-seal-like geometry",
    "dungeon": "a layered stone arch and depth",
    "vortex": "a fluid spiral with layered depth",
    "origami": "folded paper planes in sharp geometric creases",
    "dna": "a double helix rendered as precise geometry",
    "stone": "smooth river stones with layered strata",
    "code": "bold angle-bracket code chevrons with a slash, precise vector geometry",
    "cube": "a precise isometric cube, clean engineering geometry",
    "seed": "a seed splitting into a geometric sprout",
    "ledger": "stacked ledger sheets with precise rows, an append-only record",
    "fingerprint": "a fingerprint-like set of fine ridges",
    "notes": "floating paper note cards connected by luminous threads, an abstract idea constellation",
}


def _hex_rgb(value: str) -> Tuple[int, int, int]:
    value = value.lstrip("#")
    return int(value[0:2], 16), int(value[2:4], 16), int(value[4:6], 16)


def _rgba(value: str, alpha: float) -> str:
    red, green, blue = _hex_rgb(value)
    return f"rgba({red},{green},{blue},{alpha})"


def _art_prompt(name: str, description: str, motif: str, palette: Sequence[str]) -> str:
    motif_text = MOTIF_PROMPT.get(motif, "a refined geometric abstract symbol")
    return (
        "Ultra premium abstract hero artwork for a software project, "
        f"{motif_text}, representing {name}. {description} "
        f"Deep cinematic background with {palette[0]} and {palette[1]}, glowing "
        f"{palette[2]} and {palette[3]} accents, volumetric light, subtle micro-detail, "
        "elegant negative space, dark editorial tech aesthetic, flat 3D hybrid, high contrast, "
        "centered composition, no people, no humans, no faces, no text, no letters, no words, "
        "no watermark, no logo text, square"
    )


def model_key() -> str:
    return (os.getenv("POLLINATIONS_API_KEY") or os.getenv("POLL_KEY") or "").strip()


def _model_headers() -> Dict[str, str]:
    key = model_key()
    if not key:
        raise ProjectError(
            "No Pollinations API key is available for image generation.",
            "the online image model needs a secret key; AIKit never stores it in the repository.",
            "export POLLINATIONS_API_KEY (or POLL_KEY) in the environment, then retry.",
        )
    return {"Authorization": f"Bearer {key}", "User-Agent": "AegeanWorks-AIKit/1.0"}


def _download_url(url: str, output: Path, attempts: int = 4) -> None:
    output.parent.mkdir(parents=True, exist_ok=True)
    last = None
    for attempt in range(attempts):
        try:
            request = urllib.request.Request(url, headers=_model_headers())
            data = urllib.request.urlopen(request, timeout=ART_TIMEOUT).read()
            if not (data[:3] == b"\xff\xd8\xff" or data[:8] == b"\x89PNG\r\n\x1a\n"):
                raise ProjectError(
                    "The image model did not return an image.",
                    f"it returned {data[:40]!r}",
                    "retry the generation; no asset was recorded.",
                )
            output.write_bytes(data)
            return
        except urllib.error.HTTPError as exc:
            last = f"HTTP {exc.code}: {exc.read()[:200]!r}"
            if exc.code not in RETRY_STATUS or attempt == attempts - 1:
                break
            time.sleep(8)
        except OSError as exc:
            last = str(exc)
            if attempt == attempts - 1:
                break
            time.sleep(5)
    raise ProjectError(
        "The online image model is unavailable.",
        f"the artwork request failed after {attempts} attempts: {last}",
        "check POLLINATIONS_API_KEY and the network, then retry; no asset was replaced.",
    )


def _palette_words(palette: Sequence[str]) -> str:
    return f"base {palette[0]}, depth {palette[1]}, accent {palette[2]}, highlight {palette[3]}"


def _logo_model_prompt(name: str) -> str:
    # Art-only: the image model never renders text (it misspells and clips).
    # The exact title, monogram and category are overlaid locally by compose_brand
    # with crisp vector type, so the model prompt must forbid every letter.
    spec = brand_spec(name)
    motif = MOTIF_PROMPT.get(str(spec.get("motif")), "a refined geometric software symbol")
    return (
        "Premium abstract square background for a software brand mark. One simple geometric "
        f"focal motif, {motif}, centered in the upper two thirds with generous negative space "
        f"around it. Palette: {_palette_words(spec['palette'])}. Deep cinematic dark field, "
        "volumetric light, subtle micro-detail, flat 3D hybrid, soft vignette, full-bleed "
        "edge-to-edge, no text, no letters, no words, no numbers, no monogram, no logo text, "
        "no watermark, no border, no frame, no mockup."
    )


def _social_model_prompt(name: str) -> str:
    # Art-only: the image model paints the abstract field; compose_brand overlays the
    # exact project title, kicker, tagline and chips locally for legibility.
    spec = brand_spec(name)
    motif = MOTIF_PROMPT.get(str(spec.get("motif")), "a refined geometric software symbol")
    return (
        "Wide 2:1 abstract hero background for a software project banner. Premium abstract "
        f"artwork of {motif} occupying the right half, fading into a deep navy editorial "
        f"field on the left for overlaid text. Palette {_palette_words(spec['palette'])}. "
        "Strong left-to-right gradient from solid dark (left) to detailed artwork (right), "
        "single full-bleed edge-to-edge dark background, no white bands, no frames, "
        "no borders, no letterboxing, generous negative space on the left, no text, "
        "no letters, no words, no watermark, no clipping."
    )


def _local_description(root: Path, name: str, fallback: str = "") -> str:
    for candidate in ("README.md", "readme.md"):
        path = root / candidate
        if path.is_file():
            try:
                text = path.read_text(encoding="utf-8", errors="replace")
                lines = [line.strip("# ").strip() for line in text.splitlines()]
                lines = [line for line in lines if len(line) >= 10 and not line.startswith(("<", "!", "["))]
                if lines:
                    # First substantial prose line, kept short for the social card.
                    pick = next((line for line in lines[1:3] if line), lines[0])
                    return pick[:280]
            except OSError:
                pass
    return fallback or f"{repository_name(name)} — an AegeanWorks project."


def generate_model_brand(project_root: Path, name: str,
                         force: bool = False, parts: Sequence[str] = ("logo", "social"),
                         seed_offset: int = 0, description: str = "",
                         tags: Sequence[str] = (), kind: str = "") -> Dict[str, object]:
    """Render the requested parts with the online image model (ADR-239/240/241).

    The model paints an abstract, text-free background only; the exact title,
    monogram, kicker and chips are composited locally by compose_brand so type
    stays crisp, spelled correctly and unclipped. This keeps future `media init
    --art` output professional even when the model drifts.
    """
    root = Path(project_root)
    spec = brand_spec(name)
    model = os.getenv("POLLINATIONS_IMAGE_MODEL", "community/scriptsnsenses-sys/flux-2-dev-free")
    seed = int(hashlib.sha256(name.encode("utf-8")).hexdigest()[:6], 16) + seed_offset
    data = load_media(root)
    assets = dict(data.get("assets") or {})
    if (not force and "logo" in parts
            and (assets.get("logo") or {}).get("status") == "approved"):
        # Same contract as `generate_brand`: an approved identity survives a plain re-run (ADR-298).
        # A social-only regeneration does not touch the logo, so it must not be refused for it.
        return {"skipped": True, "reason": "approved assets already exist"}
    stamp = time.strftime("%Y-%m-%dT%H:%M:%S")
    resolved_kind = (kind or str(data.get("ui_kind") or "library")).strip() or "library"
    resolved_tags = tuple(tags) or tuple(data.get("topics") or ()) or (resolved_kind, "aegeanworks", "software")
    resolved_desc = (description or _local_description(root, name)
                     or str(spec.get("tagline") or ""))
    # One abstract, text-free hero background shared by both lockups.
    art = root / ART_REL
    query = urllib.parse.urlencode({"model": model, "width": 1024, "height": 1024,
                                    "seed": seed, "nologo": "true"})
    _download_url("https://gen.pollinations.ai/image/"
                  + urllib.parse.quote(_art_prompt(name, resolved_desc,
                                                   str(spec.get("motif")), spec["palette"]))
                  + "?" + query, art)
    tagline = str(spec.get("tagline") or "") or resolved_desc
    composed = compose_brand(root, name, tagline, resolved_tags, resolved_kind)
    logo = Path(composed["logo"])
    social = Path(composed["social"])
    if "logo" in parts:
        assets["logo"] = {"path": LOGO_PNG_REL.as_posix(), "status": "pending_review", "commit": "",
                          "generated_at": stamp, "review": None}
    if "social" in parts:
        assets["social_preview"] = {"path": SOCIAL_PNG_REL.as_posix(),
                                    "status": "pending_review", "commit": "",
                                    "generated_at": stamp, "review": None}
    assets["artwork"] = {"path": ART_REL.as_posix(), "status": "pending_review", "commit": "",
                         "generated_at": stamp, "review": None}
    data["assets"] = assets
    data["motif"] = spec.get("motif")
    data["layout"] = spec.get("layout")
    data["palette"] = list(spec.get("palette") or [])
    data["model"] = model
    save_media(root, data)
    return {"path": str(root), "created": True, "manifest": str(media_path(root)),
            "assets": sorted(assets), "has_ui": bool(data.get("has_ui")),
            "kind": resolved_kind, "model": model,
            "logo": str(logo), "social": str(social),
            "logo_size": (512, 512), "social_size": (1280, 640), "parts": list(parts)}


def _download(url: str, output: Path, attempts: int = 4) -> None:
    output.parent.mkdir(parents=True, exist_ok=True)
    last: Optional[str] = None
    for attempt in range(attempts):
        try:
            request = urllib.request.Request(url, headers={"User-Agent": "AegeanWorks-AIKit/1.0"})
            data = urllib.request.urlopen(request, timeout=ART_TIMEOUT).read()
            if data[:3] != b"\xff\xd8\xff" and data[:8] != b"\x89PNG\r\n\x1a\n":
                raise ProjectError(
                    "The image model did not return an image.",
                    f"it returned {data[:40]!r}",
                    "retry the generation; no asset was recorded.",
                )
            output.write_bytes(data)
            return
        except urllib.error.HTTPError as exc:
            last = f"HTTP {exc.code}"
            if exc.code not in RETRY_STATUS or attempt == attempts - 1:
                break
            time.sleep(60)
        except (OSError, ProjectError) as exc:
            last = str(exc)
            if attempt == attempts - 1:
                break
            time.sleep(20)
    raise ProjectError(
        "The image model is unavailable.",
        f"the artwork request failed after {attempts} attempts: {last}",
        "check the network and retry `media init <name> --art`; the previous assets were kept.",
    )


def _throttle() -> None:
    global _LAST_FETCH
    wait = MIN_INTERVAL_SECONDS - (time.monotonic() - _LAST_FETCH)
    if wait > 0:
        time.sleep(wait)
    _LAST_FETCH = time.monotonic()


def fetch_artwork(project_root: Path, name: str, description: str = "") -> Path:
    """Generate and store this project's hero image; retries transient model failures."""
    root = Path(project_root)
    _throttle()
    spec = brand_spec(name)
    prompt = _art_prompt(name, description or f"{repository_name(name)} project",
                         str(spec["motif"]), spec["palette"])
    # Pollinations rejects seeds above signed 32-bit; keep the hash stable but in range.
    seed = int(hashlib.sha256(name.encode("utf-8")).hexdigest()[:8], 16) % 2_147_483_647
    url = ("https://image.pollinations.ai/prompt/" + urllib.parse.quote(prompt)
           + f"?width=1024&height=1024&seed={seed}&nologo=true&private=true&model=flux"
             "&referrer=aikit")
    target = root / ART_REL
    _download(url, target)
    return target


def _monogram(name: str) -> str:
    spec = brand_spec(name)
    override = spec.get("monogram") if isinstance(spec, dict) else None
    if isinstance(override, str) and override:
        return override.upper()
    title = repository_name(name)
    if any(char.isdigit() for char in title):
        return "".join(char for char in title if char.isalnum())[:2].upper()
    words = re.findall(r"[A-Z]+(?=[A-Z][a-z]|\d|$)|[A-Z]?[a-z]+", title)
    if len(words) >= 2:
        return (words[0][0] + words[1][0]).upper()
    return title[:2].upper()


def _display_name(name: str) -> str:
    spec = brand_spec(name)
    override = spec.get("display") if isinstance(spec, dict) else ""
    if isinstance(override, str) and override:
        return override
    title = repository_name(name).replace("-", " ")
    title = re.sub(r"(?<=[a-z0-9])(?=[A-Z])", " ", title)
    return re.sub(r"\s+", " ", title).strip()


def _wrap_words(text: str, max_chars: int, max_lines: int) -> List[str]:
    lines: List[str] = []
    current = ""
    for word in text.split():
        candidate = (current + " " + word).strip()
        if len(candidate) > max_chars and current:
            lines.append(current)
            current = word
        else:
            current = candidate
        if len(lines) == max_lines:
            break
    if current and len(lines) < max_lines:
        lines.append(current)
    return lines or [text]


def _lockup(title: str, max_lines: int = 3) -> Tuple[List[str], int]:
    size = 56 if len(title) <= 12 else 48 if len(title) <= 20 else 40 if len(title) <= 30 else 33
    max_chars = max(10, int(392 / (size * 0.54)))
    return _wrap_words(title, max_chars, max_lines), size


def _logo_html(name: str, art: Path) -> str:
    spec = brand_spec(name)
    palette = spec["palette"]
    title = _display_name(name)
    monogram = _monogram(name)
    category = str(spec.get("category") or "").strip()
    uri = art.resolve().as_uri()
    lines, size = _lockup(title)
    name_html = "<br>".join(html.escape(line) for line in lines)
    name_height = len(lines) * size * 1.05
    category_top = 512 - 88 - name_height - 30
    rule_top = category_top - 16
    return f'''<!doctype html><html><head><meta charset="utf-8"><style>
*{{box-sizing:border-box}} html,body{{margin:0;width:512px;height:512px;overflow:hidden}}
body{{background:{palette[0]};font-family:'Segoe UI',Arial,sans-serif}}
.art{{position:absolute;inset:0;background:url('{uri}') center 38%/128% no-repeat;filter:saturate(1.06) contrast(1.03)}}
.veil{{position:absolute;inset:0;background:linear-gradient(180deg,{_rgba(palette[0],.10)} 0%,{_rgba(palette[0],.22)} 38%,{_rgba(palette[0],.78)} 64%,{_rgba(palette[0],.98)} 100%)}}
.safe{{position:absolute;inset:10px;border:1px solid {_rgba(palette[2],.22)};border-radius:26px}}
.badge{{position:absolute;left:54px;top:54px;width:104px;height:104px;border-radius:26px;background:{_rgba(palette[0],.66)};border:1px solid {_rgba(palette[2],.55)};box-shadow:0 18px 50px rgba(0,0,0,.45);backdrop-filter:blur(4px)}}
.mark{{position:absolute;left:54px;top:54px;width:104px;height:104px;display:flex;align-items:center;justify-content:center;font-size:{38 if len(monogram) <= 2 else 30}px;font-weight:800;letter-spacing:{1 if len(monogram) <= 2 else 0}px;color:{palette[2]};text-shadow:0 2px 12px rgba(0,0,0,.45)}}
.category{{position:absolute;left:56px;top:{category_top}px;font-size:11px;font-weight:650;letter-spacing:3px;color:{palette[2]};text-transform:uppercase}}
.rule{{position:absolute;left:56px;top:{rule_top}px;width:54px;height:2px;background:linear-gradient(90deg,{palette[2]},{palette[3]})}}
.name{{position:absolute;left:54px;bottom:88px;width:410px;font-size:{size}px;line-height:1.05;font-weight:700;letter-spacing:-0.6px;color:#f8fafc;text-shadow:0 6px 26px rgba(0,0,0,.45)}}
</style></head><body><div class="art"></div><div class="veil"></div><div class="safe"></div>
<div class="badge"></div><div class="mark">{html.escape(monogram)}</div>
<div class="category">{html.escape(category)}</div><div class="rule"></div>
<div class="name">{name_html}</div></body></html>'''


def _chips_html(tags: Sequence[str]) -> str:
    generic = {"aikit", "aegeanworks", "software", "source-available"}
    selected = [str(tag).replace("-", " ").strip()[:20]
                for tag in tags if str(tag) not in generic and str(tag).strip()]
    if not selected:
        selected = [str(tag).replace("-", " ").strip()[:20]
                    for tag in list(tags)[:3] if str(tag).strip()]
    chips = []
    for label in selected[:3]:
        if not label:
            continue
        chips.append(f'<span class="chip">{html.escape(label)}</span>')
    return "".join(chips)


def _social_html(name: str, art: Path, description: str, kind: str,
                 tags: Sequence[str]) -> str:
    spec = brand_spec(name)
    palette = spec["palette"]
    layout = str(spec["layout"])
    text_80 = _rgba("#f8fafc", .86)
    text_45 = _rgba("#f8fafc", .55)
    chip_border = _rgba("#94a3b8", .38)
    chip_text = _rgba("#f8fafc", .86)
    title = _display_name(name)
    category = str(spec.get("category") or "").strip()
    kicker = category or kind.strip().upper() or "PROJECT"
    title_size = 78 if len(title) <= 14 else 64 if len(title) <= 22 else 52
    title_lines = _wrap_words(title, 16 if title_size >= 74 else 20 if title_size >= 60 else 24, 2)
    title_html = "<br>".join(html.escape(line) for line in title_lines)
    tagline = html.escape((description or f"{title} — an AegeanWorks project.")[:220])
    uri = art.resolve().as_uri()
    repo_suffix = str(spec.get("repo") or "").strip() or repository_name(name)
    repo_url = f"github.com/AegeanWorks/{repo_suffix}"
    chips = _chips_html(tags or (kind, "aegeanworks", "software"))
    accent, accent2 = palette[2], palette[3]
    if layout == "center":
        center = f'''<div class="center-art" style="background-image:url('{uri}')"></div>
        <div class="center-veil"></div>
        <div class="center-kicker">AEGEANWORKS · {html.escape(kicker)}</div>
        <div class="center-title">{title_html}</div>
        <div class="center-tag">{tagline}</div>
        <div class="center-chips">{chips}</div>
        <div class="foot">AEGEANWORKS</div><div class="url">{repo_url}</div>'''
        body = center
        css = f'''.center-art{{position:absolute;inset:0;background-position:center 34%;background-size:cover;filter:saturate(1.08)}}
        .center-veil{{position:absolute;inset:0;background:radial-gradient(circle at 50% 35%,{_rgba(palette[0],.10)} 0%,{_rgba(palette[0],.55)} 52%,{_rgba(palette[0],.96)} 100%)}}
        .center-kicker{{position:absolute;left:0;right:0;top:104px;text-align:center;font-size:16px;letter-spacing:8px;color:{accent};font-weight:600;text-shadow:0 2px 14px rgba(0,0,0,.5)}}
        .center-title{{position:absolute;left:70px;right:70px;top:192px;text-align:center;font-size:{title_size}px;line-height:1.02;font-weight:800;color:#f8fafc;letter-spacing:-1px;text-shadow:0 4px 24px rgba(0,0,0,.55)}}
        .center-tag{{position:absolute;left:190px;right:190px;top:360px;max-height:96px;overflow:hidden;display:-webkit-box;-webkit-line-clamp:3;-webkit-box-orient:vertical;text-align:center;font-size:25px;line-height:1.4;color:{text_80};text-shadow:0 2px 12px rgba(0,0,0,.5)}}
        .center-chips{{position:absolute;left:0;right:0;top:492px;display:flex;justify-content:center;gap:10px}}
        .foot{{position:absolute;left:76px;bottom:32px;font-size:12px;letter-spacing:5px;color:{text_45};z-index:4}}
        .url{{position:absolute;right:56px;bottom:32px;font-size:16px;letter-spacing:1px;color:{text_45};z-index:5;font-family:'Segoe UI',Arial,sans-serif}}'''
    else:
        serif = layout == "editorial"
        family = "Georgia, 'Times New Roman', serif" if serif else "'Segoe UI', Arial, sans-serif"
        panel = f'''<div class="art" style="background-image:url('{uri}')"></div>
        <div class="panel"></div>
        <div class="band"></div>
        <div class="kicker">AEGEANWORKS · {html.escape(kicker)}</div>
        <div class="title">{title_html}</div>
        <div class="rule"></div>
        <div class="tag">{tagline}</div>
        <div class="chips">{chips}</div>
        <div class="foot">AEGEANWORKS</div><div class="footerband"></div><div class="url">{repo_url}</div>'''
        body = panel
        css = f'''.panel{{position:absolute;left:0;top:0;width:790px;height:640px;background:linear-gradient(100deg,{palette[0]} 0%,{palette[1]} 68%,{_rgba(palette[1],.92)} 100%);z-index:3}}
        .art{{position:absolute;right:0;top:0;width:600px;height:640px;background-position:center 38%;background-size:auto 124%;filter:saturate(1.05);z-index:1}}
        .art:after{{content:'';position:absolute;inset:0;background:linear-gradient(90deg,{palette[1]} 0%,{_rgba(palette[1],.10)} 45%,{_rgba(palette[0],.10)} 100%),linear-gradient(0deg,{_rgba(palette[0],.92)} 0%,transparent 18%)}}
        .band{{position:absolute;left:0;top:0;width:1280px;height:4px;background:{accent};z-index:5}}
        .kicker{{position:absolute;left:76px;top:138px;font-size:16px;letter-spacing:7px;color:{accent};font-weight:600;z-index:4;font-family:{family};text-shadow:0 2px 12px rgba(0,0,0,.5)}}
        .title{{position:absolute;left:72px;top:196px;width:700px;font-size:{title_size}px;line-height:.98;font-weight:800;color:#f8fafc;letter-spacing:-1px;z-index:4;font-family:{family};text-shadow:0 4px 22px rgba(0,0,0,.5)}}
        .rule{{position:absolute;left:74px;top:360px;width:560px;height:2px;background:linear-gradient(90deg,{accent},{accent2});z-index:4}}
        .tag{{position:absolute;left:76px;top:392px;width:540px;max-height:112px;overflow:hidden;display:-webkit-box;-webkit-line-clamp:3;-webkit-box-orient:vertical;font-size:26px;line-height:1.38;color:{text_80};z-index:4;font-family:{family};text-shadow:0 2px 12px rgba(0,0,0,.45)}}
        .chips{{position:absolute;left:76px;top:534px;display:flex;gap:10px;z-index:4}}
        .foot{{position:absolute;left:76px;bottom:32px;font-size:12px;letter-spacing:5px;color:{text_45};z-index:4}}
        .footerband{{position:absolute;right:0;bottom:0;width:600px;height:84px;background:linear-gradient(0deg,{palette[0]} 0%,{_rgba(palette[0],.92)} 55%,transparent 100%);z-index:4}}
        .url{{position:absolute;right:56px;bottom:32px;font-size:16px;letter-spacing:1px;color:{text_45};z-index:5;font-family:'Segoe UI',Arial,sans-serif}}'''
    return f'''<!doctype html><html><head><meta charset="utf-8"><style>
*{{box-sizing:border-box}} html,body{{margin:0;width:1280px;height:640px;overflow:hidden}}
body{{background:{palette[0]};font-family:'Segoe UI',Arial,sans-serif}}
.chip{{padding:9px 16px;border:1px solid {chip_border};border-radius:20px;font-size:15px;color:{chip_text};background:{_rgba(palette[0],.55)};font-family:'Segoe UI',Arial,sans-serif}}
{css}
</style></head><body>{body}</body></html>'''


def compose_brand(project_root: Path, name: str, description: str = "",
                  tags: Sequence[str] = (), kind: str = "library") -> Dict[str, object]:
    """Render the final 512px logo and 1280x640 social card over the generated artwork."""
    root = Path(project_root)
    art = root / ART_REL
    if not art.is_file():
        raise ProjectError(
            f"{art} is missing.",
            "the AI brand composition needs its generated hero artwork.",
            "run `media init <name> --art` first.",
        )
    logo = root / LOGO_PNG_REL
    social = root / SOCIAL_PNG_REL
    logo_html = root / ".aikit" / "brand-logo.html"
    social_html = root / ".aikit" / "brand-social.html"
    logo_html.parent.mkdir(parents=True, exist_ok=True)
    logo_html.write_text(_logo_html(name, art), encoding="utf-8")
    social_html.write_text(_social_html(name, art, description, kind, tags), encoding="utf-8")
    logo_result = capture_html(logo_html, logo, 512, 512)
    social_result = capture_html(social_html, social, 1280, 640)
    for temporary in (logo_html, social_html):
        try:
            temporary.unlink()
        except OSError:  # hygiene: allow temporary HTML cleanup cannot fail the rendered PNG
            pass
    logo_size = (logo_result["width"], logo_result["height"])
    social_size = (social_result["width"], social_result["height"])
    if logo_size != (512, 512) or social_size != (1280, 640):
        raise ProjectError(
            f"Brand composition rendered {logo_size[0]}x{logo_size[1]} and "
            f"{social_size[0]}x{social_size[1]}.",
            "the logo must be 512x512 and the social card 1280x640.",
            "retry the composition; no asset was recorded.",
        )
    return {"logo": str(logo), "social": str(social), "logo_size": logo_size,
            "social_size": social_size}


def generate_brand(project_root: Path, name: str, description: str = "",
                   tags: Sequence[str] = (), kind: str = "library",
                   force: bool = True, refresh_art: bool = False) -> Dict[str, object]:
    """Fetch image-model artwork, compose PNG brand assets, and mark them for review."""
    root = Path(project_root)
    data = load_media(root)
    existing = data.get("assets") or {}
    if not force and (existing.get("logo") or {}).get("status") == "approved":
        return {"skipped": True, "reason": "approved assets already exist"}
    spec = brand_spec(name)
    if refresh_art or not (root / ART_REL).is_file():
        fetch_artwork(root, name, description)
    tagline = str(spec.get("tagline") or "") or description
    composed = compose_brand(root, name, tagline, tags, kind)
    data["assets"] = {
        "logo": {"path": LOGO_PNG_REL.as_posix(), "status": "pending_review", "commit": "",
                 "generated_at": time.strftime("%Y-%m-%dT%H:%M:%S"), "review": None},
        "social_preview": {"path": SOCIAL_PNG_REL.as_posix(), "status": "pending_review",
                           "commit": "", "generated_at": time.strftime("%Y-%m-%dT%H:%M:%S"),
                           "review": None},
        "artwork": {"path": ART_REL.as_posix(), "status": "pending_review", "commit": "",
                    "generated_at": time.strftime("%Y-%m-%dT%H:%M:%S"), "review": None},
    }
    data["motif"] = brand_spec(name)["motif"]
    data["layout"] = brand_spec(name)["layout"]
    data["palette"] = list(brand_spec(name)["palette"])
    save_media(root, data)
    return {"artwork": str(root / ART_REL), **composed, "has_ui": bool(data.get("has_ui")),
            "kind": kind}
