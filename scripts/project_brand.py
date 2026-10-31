"""
Project-specific brand artwork: one motif, palette and composition per project.

The catalogue is authored design data, not a random generator. Every project gets a distinct
palette and a motif that reflects what the project is (network, eye, shield, calendar, orbit, ...),
so a logo or social preview cannot be mistaken for another project's. New projects fall back to a
deterministic identity derived from the name and are still reviewable before they are applied.
"""

import colorsys
import hashlib
import json
import re
from pathlib import Path
from typing import Dict, List, Optional, Sequence, Tuple
from xml.sax.saxutils import escape as xml_escape

from scripts.project_registry import repository_name

CATALOG_PATH = Path(__file__).with_name("brand_catalog.json")
TEXT = "#F8FAFC"
MUTED = "#94A3B8"
FALLBACK_MOTIFS = ("grid", "network", "orbit", "pulse", "terminal", "lens", "stack")
FALLBACK_LAYOUTS = ("left", "split", "editorial", "center", "terminal", "grid", "wave")
_CATALOG: Optional[Dict[str, object]] = None


def _catalog() -> Dict[str, object]:
    global _CATALOG
    if _CATALOG is None:
        try:
            data = json.loads(CATALOG_PATH.read_text(encoding="utf-8"))
            if not isinstance(data, dict) or data.get("schema") != 1:
                raise ValueError("unsupported brand catalog schema")
            _CATALOG = data
        except (OSError, ValueError, TypeError):
            _CATALOG = {"schema": 1, "palettes": [], "projects": {}}
    return _CATALOG


def _hex(hue: float, saturation: float, lightness: float) -> str:
    red, green, blue = colorsys.hls_to_rgb((hue % 360) / 360, lightness, saturation)
    return "#%02x%02x%02x" % (round(red * 255), round(green * 255), round(blue * 255))


def _fallback_palette(name: str) -> Tuple[str, str, str, str]:
    digest = hashlib.sha256(name.encode("utf-8")).hexdigest()
    hues = (188, 262, 330, 42, 152, 215, 298, 12)
    hue = hues[int(digest[:2], 16) % len(hues)]
    return (_hex(hue, 0.45, 0.05), _hex(hue + 28, 0.45, 0.13),
            _hex(hue + 4, 0.88, 0.68), _hex(hue + 72, 0.84, 0.76))


def brand_spec(name: str) -> Dict[str, object]:
    """The authored motif/palette/composition for a project, with a stable fallback."""
    catalog = _catalog()
    projects = catalog.get("projects") if isinstance(catalog.get("projects"), dict) else {}
    palettes = catalog.get("palettes") if isinstance(catalog.get("palettes"), list) else []
    entry = projects.get(name) if isinstance(projects, dict) else None
    if isinstance(entry, dict):
        palette_index = int(entry.get("palette") or 0)
        palette = palettes[palette_index] if 0 <= palette_index < len(palettes) else None
        return {
            "motif": str(entry.get("motif") or "grid"),
            "layout": str(entry.get("layout") or "left"),
            "monogram": str(entry.get("monogram") or ""),
            "display": str(entry.get("display") or ""),
            "category": str(entry.get("category") or ""),
            "tagline": str(entry.get("tagline") or ""),
            "palette": tuple(palette) if isinstance(palette, list) and len(palette) == 4
            else _fallback_palette(name),
            "source": "catalog",
        }
    digest = hashlib.sha256(name.encode("utf-8")).hexdigest()
    return {
        "motif": FALLBACK_MOTIFS[int(digest[2:4], 16) % len(FALLBACK_MOTIFS)],
        "layout": FALLBACK_LAYOUTS[int(digest[4:6], 16) % len(FALLBACK_LAYOUTS)],
        "monogram": "",
        "display": "",
        "category": "",
        "tagline": "",
        "palette": _fallback_palette(name),
        "source": "fallback",
    }


def _display_name(name: str) -> str:
    title = repository_name(name).replace("-", " ")
    title = re.sub(r"(?<=[a-z0-9])(?=[A-Z])", " ", title)
    return re.sub(r"\s+", " ", title).strip()


def _monogram(name: str) -> str:
    words = [word for word in _display_name(name).split() if word]
    if len(words) >= 2:
        return (words[0][0] + words[1][0]).upper()
    word = (words[0] if words else name).upper()
    return word[:2].ljust(2, "X")


def _wrap(text: str, width: int, limit: int) -> List[str]:
    words, lines, current = text.split(), [], ""
    for word in words:
        if len(current) + len(word) + 1 > width and current:
            lines.append(current)
            current = word
        else:
            current = (current + " " + word).strip()
        if len(lines) == limit:
            break
    if current and len(lines) < limit:
        lines.append(current)
    return lines


def _motif_body(motif: str, accent: str, accent2: str) -> str:
    stroke = f'fill="none" stroke="{accent}" stroke-width="6" stroke-linecap="round" stroke-linejoin="round"'
    thin = f'fill="none" stroke="{accent}" stroke-width="3" stroke-linecap="round" stroke-linejoin="round"'
    alt = f'fill="none" stroke="{accent2}" stroke-width="5" stroke-linecap="round" stroke-linejoin="round"'
    soft = f'fill="{accent}" fill-opacity="0.18" stroke="{accent}" stroke-width="2"'
    if motif == "grid":
        return "".join(f'<rect x="{x}" y="{y}" width="26" height="26" rx="6" {soft}/>'
                       for x in (-48, -8, 32) for y in (-48, -8, 32))
    if motif == "network":
        nodes = [(-52, 24), (-18, -42), (20, 34), (54, -14), (48, 44), (-44, -34)]
        return (f'<path d="M-52 24L-18 -42L20 34L54 -14M20 34L48 44M-18 -42L-44 -34" {thin}/>'
                + "".join(f'<circle cx="{x}" cy="{y}" r="8" fill="{accent}"/>' for x, y in nodes))
    if motif == "brain":
        return (f'<path d="M-54 -18C-54 -50 -22 -62 0 -46C22 -62 54 -50 54 -18C62 6 40 30 18 28'
                f'C6 46 -6 46 -18 28C-40 30 -62 6 -54 -18Z" {stroke}/>'
                f'<path d="M0 -46V40M-32 -30C-16 -22 -16 -6 -32 4M30 -30C14 -22 14 -6 30 4" {thin}/>')
    if motif == "atom":
        return (f'<ellipse cx="0" cy="0" rx="58" ry="22" {thin}/>'
                f'<ellipse cx="0" cy="0" rx="58" ry="22" transform="rotate(60)" {thin}/>'
                f'<ellipse cx="0" cy="0" rx="58" ry="22" transform="rotate(120)" {thin}/>'
                f'<circle cx="0" cy="0" r="9" fill="{accent2}"/>')
    if motif == "pulse":
        return (f'<path d="M-62 4H-36L-24 -34L-4 38L16 -24L30 4H62" {stroke}/>'
                f'<circle cx="16" cy="-24" r="5" fill="{accent2}"/>')
    if motif == "stack":
        return (f'<path d="M-52 -26L0 -50L52 -26L0 -2Z" {soft}/>'
                f'<path d="M-52 0L0 24L52 0M-52 24L0 48L52 24" {thin}/>')
    if motif == "eye":
        return (f'<path d="M-64 0Q0 -48 64 0Q0 48 -64 0Z" {stroke}/>'
                f'<circle cx="0" cy="0" r="20" fill="{accent2}" fill-opacity="0.85"/>'
                f'<circle cx="0" cy="0" r="7" fill="{TEXT}"/>')
    if motif == "book":
        return (f'<path d="M-54 -42C-26 -50 -8 -42 0 -32C8 -42 26 -50 54 -42V38'
                f'C26 30 8 38 0 48C-8 38 -26 30 -54 38Z" {stroke}/>'
                f'<path d="M0 -32V48M-42 -24C-26 -28 -14 -24 -8 -18M-42 0C-26 -4 -14 0 -8 6'
                f'M42 -24C26 -28 14 -24 8 -18M42 0C26 -4 14 0 8 6" {thin}/>')
    if motif == "calendar":
        return (f'<rect x="-52" y="-42" width="104" height="90" rx="14" {stroke}/>'
                f'<path d="M-52 -16H52M-30 -54V-34M30 -54V-34" {thin}/>'
                f'<circle cx="-24" cy="8" r="5" fill="{accent2}"/><circle cx="0" cy="8" r="5" fill="{accent}"/>'
                f'<circle cx="24" cy="8" r="5" fill="{accent2}"/><circle cx="-24" cy="30" r="5" fill="{accent}"/>')
    if motif == "shield":
        return (f'<path d="M0 -60L50 -36V8C50 34 24 52 0 62C-24 52 -50 34 -50 8V-36Z" {soft}/>'
                f'<path d="M-22 2L-4 20L28 -16" {alt}/>')
    if motif == "key":
        return (f'<circle cx="-26" cy="0" r="20" {stroke}/><path d="M-6 0H58M38 0V20M54 0V16" {stroke}/>'
                f'<circle cx="-26" cy="0" r="6" fill="{accent2}"/>')
    if motif == "compass":
        return (f'<circle cx="0" cy="0" r="56" {stroke}/><circle cx="0" cy="0" r="42" {thin}/>'
                f'<path d="M0 -48L14 0L0 48L-14 0Z" fill="{accent}" fill-opacity="0.82"/>'
                f'<circle cx="0" cy="0" r="6" fill="{TEXT}"/>')
    if motif == "timer":
        return (f'<circle cx="0" cy="8" r="46" {stroke}/><path d="M-16 -52H16M0 -52V-38" {thin}/>'
                f'<path d="M0 8V-16M0 8L24 22" {alt}/><path d="M-46 8H-38M38 8H46M0 54V46" {thin}/>')
    if motif == "terminal":
        return (f'<rect x="-58" y="-42" width="116" height="84" rx="14" {stroke}/>'
                f'<path d="M-38 -18L-18 0L-38 18M-12 -18H28" {alt}/>'
                f'<circle cx="-44" cy="-32" r="3" fill="{accent2}"/><circle cx="-32" cy="-32" r="3" fill="{accent}"/>')
    if motif == "fold":
        return (f'<path d="M-52 -34L8 -54L52 -22L-8 -2Z" {soft}/>'
                f'<path d="M-52 -34V22L-8 50L52 20V-22M-8 -2V50" {thin}/>')
    if motif == "gauge":
        return (f'<path d="M-54 28A54 54 0 0 1 54 28" {stroke}/>'
                f'<path d="M-54 28H54M-30 20V10M0 16V2M30 20V10" {thin}/>'
                f'<path d="M0 24L30 -18" {alt}/><circle cx="0" cy="24" r="6" fill="{accent2}"/>')
    if motif == "bulb":
        return (f'<path d="M0 -56C-30 -56 -46 -34 -40 -12C-36 4 -22 10 -18 26H18'
                f'C22 10 36 4 40 -12C46 -34 30 -56 0 -56Z" {stroke}/>'
                f'<path d="M-16 38H16M-12 50H12" {thin}/>'
                f'<path d="M-46 -30L-60 -38M46 -30L60 -38M-54 0H-68M54 0H68" {thin}/>')
    if motif == "lens":
        return (f'<circle cx="0" cy="0" r="50" {stroke}/><circle cx="0" cy="0" r="30" {thin}/>'
                f'<path d="M-62 0H62M0 -62V62" {thin}/><circle cx="18" cy="-14" r="8" fill="{accent2}"/>')
    if motif == "waveform":
        heights = (24, 48, 70, 40, 88, 54, 34, 62, 26, 46, 18)
        return "".join(
            f'<rect x="{-54 + i * 11}" y="{-h / 2}" width="6" height="{h}" rx="3" fill="{accent}" fill-opacity="0.86"/>'
            for i, h in enumerate(heights))
    if motif == "leaf":
        return (f'<path d="M0 -58C42 -40 56 0 22 38C0 58 -30 44 -42 18C-56 -14 -34 -48 0 -58Z" {soft}/>'
                f'<path d="M-28 46C-2 18 14 -14 30 -38M-18 12L4 16M2 -8L24 -4M14 -24L32 -20" {thin}/>')
    if motif == "orbit":
        return (f'<ellipse cx="0" cy="0" rx="62" ry="24" {thin}/>'
                f'<ellipse cx="0" cy="0" rx="62" ry="24" transform="rotate(58)" {thin}/>'
                f'<circle cx="0" cy="0" r="12" fill="{accent}"/>'
                f'<circle cx="48" cy="-14" r="6" fill="{accent2}"/>')
    if motif == "camera":
        return (f'<rect x="-58" y="-34" width="116" height="72" rx="14" {stroke}/>'
                f'<path d="M-24 -34L-16 -48H16L24 -34" {stroke}/>'
                f'<circle cx="0" cy="4" r="22" {thin}/><circle cx="0" cy="4" r="9" fill="{accent2}"/>'
                f'<circle cx="40" cy="-20" r="4" fill="{accent}"/>')
    if motif == "prism":
        return (f'<path d="M0 -54L52 40H-52Z" {stroke}/>'
                f'<path d="M-74 12H-24M24 12H74" {alt}/><path d="M-64 -12H-30M30 -12H64" {thin}/>')
    if motif == "flask":
        return (f'<path d="M-20 -54H20M-14 -54V-16L-44 38C-50 50 -42 58 -28 58H28'
                f'C42 58 50 50 44 38L14 -16V-54" {stroke}/>'
                f'<path d="M-34 24H34" {alt}/><circle cx="-10" cy="40" r="4" fill="{accent2}"/>'
                f'<circle cx="12" cy="32" r="3" fill="{accent2}"/>')
    if motif == "wand":
        return (f'<path d="M-48 46L22 -24" stroke="{accent}" stroke-width="9" stroke-linecap="round"/>'
                f'<path d="M28 -46L34 -26L54 -20L34 -14L28 6L22 -14L2 -20L22 -26Z" fill="{accent2}"/>'
                f'<path d="M-38 -34L-32 -18L-16 -12L-32 -6L-38 10L-44 -6L-60 -12L-44 -18Z" {thin}/>'
                f'<circle cx="48" cy="26" r="4" fill="{accent2}"/><circle cx="-20" cy="34" r="3" fill="{accent}"/>')
    if motif == "certificate":
        return (f'<rect x="-46" y="-54" width="92" height="108" rx="10" {stroke}/>'
                f'<path d="M-30 -34H30M-30 -18H30M-30 -2H12" {thin}/>'
                f'<circle cx="22" cy="30" r="18" fill="{accent2}" fill-opacity="0.9"/>'
                f'<path d="M10 44L4 60L20 52M34 44L40 60L24 52" {alt}/>')
    if motif == "dungeon":
        return (f'<path d="M-50 52V-4A50 50 0 0 1 50 -4V52" {stroke}/>'
                f'<path d="M-30 52V0A30 30 0 0 1 30 0V52" {thin}/>'
                f'<path d="M-50 30H-38M38 30H50M-50 10H-38M38 10H50M-18 52H18M-18 40H18" {thin}/>'
                f'<path d="M-12 30L-12 4A12 12 0 0 1 12 4V30" {alt}/>')
    if motif == "vortex":
        return (f'<path d="M4 -54C38 -48 58 -20 50 10C42 40 10 58 -20 48C-46 40 -58 12 -48 -12'
                f'C-40 -32 -20 -42 -2 -34C12 -28 18 -12 10 0C2 10 -12 10 -18 2" {stroke}/>'
                f'<circle cx="52" cy="-34" r="6" fill="{accent2}"/><circle cx="-42" cy="34" r="4" fill="{accent}"/>'
                f'<circle cx="30" cy="46" r="3" fill="{accent2}"/>')
    if motif == "origami":
        return (f'<path d="M-58 40L-8 -54L18 30Z" fill="{accent}" fill-opacity="0.20" stroke="{accent}" stroke-width="3"/>'
                f'<path d="M-18 50L58 -16L8 12Z" fill="{accent2}" fill-opacity="0.18" stroke="{accent2}" stroke-width="3"/>'
                f'<path d="M-8 -54L8 12M18 30L-18 50M-58 40L-18 50M58 -16L18 30" {thin}/>')
    if motif == "dna":
        return (f'<path d="M-24 -56C-52 -30 52 -18 24 8C-4 34 -52 22 -28 56" {stroke}/>'
                f'<path d="M24 -56C52 -30 -52 -18 -24 8C4 34 52 22 28 56" {alt}/>'
                f'<path d="M-38 -30H38M-42 -10H42M-38 12H38M-28 34H28" {thin}/>')
    if motif == "stone":
        return (f'<path d="M-52 18C-50 -26 -18 -52 14 -46C48 -40 60 -8 46 24C34 54 -20 60 -42 38'
                f'C-54 28 -54 28 -54 18Z" fill="{accent}" fill-opacity="0.22" stroke="{accent}" stroke-width="4"/>'
                f'<path d="M-58 34C-30 20 24 20 58 34M-46 48C-20 38 20 38 46 48" {thin}/>')
    if motif == "seed":
        return (f'<path d="M0 58V-8" stroke="{accent}" stroke-width="6" stroke-linecap="round"/>'
                f'<path d="M0 -4C-34 -10 -42 -40 -12 -52C2 -40 4 -20 0 -4Z" fill="{accent2}" fill-opacity="0.28" stroke="{accent2}" stroke-width="3"/>'
                f'<path d="M0 18C30 8 44 -16 20 -30C4 -18 0 2 0 18Z" fill="{accent}" fill-opacity="0.24" stroke="{accent}" stroke-width="3"/>'
                f'<path d="M0 44C-18 48 -30 56 -38 66M0 44C18 48 30 56 38 66" {thin}/>')
    if motif == "branch":
        return (f'<path d="M-42 42V-34M-42 8C-18 8 2 -6 26 -32M-42 8C-18 8 2 22 26 42" {stroke}/>'
                f'<circle cx="-42" cy="46" r="9" fill="{accent}"/>'
                f'<circle cx="26" cy="-34" r="9" fill="{accent2}"/>'
                f'<circle cx="26" cy="46" r="9" fill="{accent2}"/>'
                f'<path d="M-42 -34V-46" {thin}/>')
    if motif == "fingerprint":
        return (f'<path d="M-48 -18C-48 -48 -20 -60 4 -50C30 -40 38 -8 24 16C12 36 -10 44 -28 32" {stroke}/>'
                f'<path d="M-34 -10C-34 -30 -14 -38 2 -30C20 -22 24 -2 14 12" {thin}/>'
                f'<path d="M-20 0C-20 -12 -6 -16 4 -10" {thin}/>'
                f'<path d="M-60 18C-58 42 -34 54 -8 48C18 42 38 20 36 -6" {thin}/>')
    if motif == "ledger":
        return (f'<rect x="-42" y="-52" width="78" height="104" rx="9" {stroke}/>'
                f'<path d="M-24 -32H16M-24 -16H16M-24 0H4M-24 16H16" {thin}/>'
                f'<circle cx="26" cy="40" r="16" fill="{accent2}" fill-opacity="0.9"/>'
                f'<text x="26" y="47" text-anchor="middle" font-family="Segoe UI, Arial, sans-serif" font-size="20" font-weight="700" fill="{TEXT}">$</text>')
    return (f'<rect x="-48" y="-48" width="96" height="96" rx="22" {stroke}/>'
            f'<text x="0" y="14" text-anchor="middle" font-family="Segoe UI, Arial, sans-serif" '
            f'font-size="48" font-weight="700" fill="{accent}">{xml_escape(_monogram("Aa"))}</text>')


def _motif(motif: str, accent: str, accent2: str, cx: float, cy: float, scale: float,
           opacity: float = 1.0) -> str:
    return (f'<g transform="translate({cx} {cy}) scale({scale})" opacity="{opacity}">'
            f'{_motif_body(motif, accent, accent2)}</g>')


def _logo_rings(layout: str, accent: str, accent2: str) -> str:
    if layout in {"center", "wave"}:
        return (f'<circle cx="256" cy="238" r="170" fill="none" stroke="{accent}" '
                f'stroke-opacity="0.22" stroke-width="2"/>'
                f'<circle cx="256" cy="238" r="136" fill="none" stroke="{accent2}" '
                f'stroke-opacity="0.20" stroke-width="2"/>')
    if layout in {"grid", "terminal"}:
        return (f'<path d="M96 160H416M96 238H416M96 316H416M160 96V416M256 96V416M352 96V416" '
                f'stroke="{accent}" stroke-opacity="0.13" stroke-width="2"/>')
    if layout in {"editorial", "split"}:
        return (f'<path d="M64 384L448 128" stroke="{accent2}" stroke-opacity="0.22" stroke-width="3"/>'
                f'<path d="M64 128L448 384" stroke="{accent}" stroke-opacity="0.12" stroke-width="2"/>')
    return (f'<circle cx="256" cy="238" r="164" fill="none" stroke="{accent}" '
            f'stroke-opacity="0.18" stroke-width="2"/>')


def logo_svg(name: str) -> str:
    """A 512px square identity: project motif, unique palette, monogram and AegeanWorks mark."""
    spec = brand_spec(name)
    bg1, bg2, accent, accent2 = spec["palette"]
    motif = str(spec["motif"])
    layout = str(spec["layout"])
    title = _display_name(name)
    return f'''<svg xmlns="http://www.w3.org/2000/svg" width="512" height="512" viewBox="0 0 512 512" role="img" aria-labelledby="title desc" data-motif="{xml_escape(motif)}" data-layout="{xml_escape(layout)}">
  <title id="title">{xml_escape(title)} logo</title>
  <desc id="desc">Project-specific {xml_escape(motif)} mark for {xml_escape(title)}; AegeanWorks identity.</desc>
  <defs>
    <linearGradient id="bg" x1="0" y1="0" x2="1" y2="1"><stop offset="0" stop-color="{bg1}"/><stop offset="1" stop-color="{bg2}"/></linearGradient>
    <linearGradient id="mark" x1="0" y1="0" x2="1" y2="1"><stop offset="0" stop-color="{accent}"/><stop offset="1" stop-color="{accent2}"/></linearGradient>
  </defs>
  <rect width="512" height="512" rx="112" fill="url(#bg)"/>
  {_logo_rings(layout, accent, accent2)}
  {_motif(motif, accent, accent2, 256, 232, 1.62)}
  <text x="256" y="404" text-anchor="middle" font-family="Segoe UI, Arial, sans-serif" font-size="62" font-weight="700" fill="url(#mark)" letter-spacing="3">{xml_escape(_monogram(name))}</text>
  <text x="256" y="458" text-anchor="middle" font-family="Segoe UI, Arial, sans-serif" font-size="17" letter-spacing="6" fill="{TEXT}" fill-opacity="0.55">AEGEANWORKS</text>
</svg>
'''


def _chips(tags: Sequence[str], x: int, y: int) -> str:
    parts = []
    for index, tag in enumerate(list(tags)[:3]):
        label = xml_escape(str(tag).replace("-", " ")[:18])
        width = 26 + len(str(tag)) * 10
        offset = x + index * (width + 12)
        parts.append(f'<rect x="{offset}" y="{y}" width="{width}" height="38" rx="19" '
                     f'fill="#0B1220" fill-opacity="0.55" stroke="{MUTED}" stroke-opacity="0.35"/>'
                     f'<text x="{offset + width / 2}" y="{y + 25}" text-anchor="middle" '
                     f'font-family="Segoe UI, Arial, sans-serif" font-size="15" fill="{TEXT}" '
                     f'fill-opacity="0.82">{label}</text>')
    return "".join(parts)


def social_svg(name: str, kind: str, description: str, repo_url: str,
               tags: Sequence[str] = ()) -> str:
    """A 1280x640 social card with a layout chosen for this project, not a shared template."""
    spec = brand_spec(name)
    bg1, bg2, accent, accent2 = spec["palette"]
    motif = str(spec["motif"])
    layout = str(spec["layout"])
    title = _display_name(name)
    lines = _wrap(description or f"{title} — an AegeanWorks project.", 50, 3)
    font_size = 76 if len(title) <= 15 else 62 if len(title) <= 22 else 50
    tagline = ""
    chips = ""
    if layout == "center":
        title_y, text_x, align = 356, 640, "middle"
        tagline = tagline.replace(f'x="{text_x}"', f'x="{text_x}"')
        chips = _chips(tags or (kind, "aegeanworks", "software"), 430, 530)
        mark = _motif(motif, accent, accent2, 640, 214, 1.55)
        title_block = (f'<text x="640" y="{title_y}" text-anchor="middle" font-family="Segoe UI, Arial, sans-serif" '
                       f'font-size="{font_size}" font-weight="700" fill="{TEXT}">{xml_escape(title)}</text>'
                       f'<text x="640" y="{title_y + 56}" text-anchor="middle" font-family="Segoe UI, Arial, sans-serif" '
                       f'font-size="22" letter-spacing="5" fill="{accent}">AEGEANWORKS · {xml_escape(kind.upper())}</text>')
        tagline = "".join(
            f'<text x="640" y="{428 + index * 38}" text-anchor="middle" '
            f'font-family="Segoe UI, Arial, sans-serif" font-size="25" fill="{TEXT}" '
            f'fill-opacity="0.72">{xml_escape(line)}</text>' for index, line in enumerate(lines))
    elif layout == "split":
        mark = _motif(motif, accent, accent2, 245, 320, 1.9)
        title_block = (f'<text x="548" y="246" font-family="Segoe UI, Arial, sans-serif" '
                       f'font-size="{font_size}" font-weight="700" fill="{TEXT}">{xml_escape(title)}</text>'
                       f'<text x="550" y="292" font-family="Segoe UI, Arial, sans-serif" '
                       f'font-size="21" letter-spacing="5" fill="{accent}">AEGEANWORKS · {xml_escape(kind.upper())}</text>')
        tagline = "".join(
            f'<text x="550" y="{344 + index * 42}" font-family="Segoe UI, Arial, sans-serif" '
            f'font-size="28" fill="{TEXT}" fill-opacity="0.74">{xml_escape(line)}</text>'
            for index, line in enumerate(lines))
        chips = _chips(tags or (kind, "aegeanworks", "software"), 550, 500)
    elif layout == "terminal":
        mark = _motif(motif, accent, accent2, 1040, 320, 1.8, 0.42)
        title_block = (f'<text x="78" y="206" font-family="Consolas, monospace" font-size="20" '
                       f'fill="{accent}">$ open {xml_escape(repository_name(name))}</text>'
                       f'<text x="78" y="292" font-family="Segoe UI, Arial, sans-serif" '
                       f'font-size="{font_size}" font-weight="700" fill="{TEXT}">{xml_escape(title)}</text>')
        tagline = "".join(
            f'<text x="80" y="{348 + index * 40}" font-family="Consolas, monospace" '
            f'font-size="25" fill="{TEXT}" fill-opacity="0.72">{xml_escape(line)}</text>'
            for index, line in enumerate(lines))
        chips = _chips(tags or (kind, "aegeanworks", "software"), 80, 502)
    elif layout == "editorial":
        mark = _motif(motif, accent, accent2, 1030, 304, 2.35, 0.85)
        title_block = (f'<text x="76" y="238" font-family="Georgia, Times New Roman, serif" '
                       f'font-size="{font_size}" font-weight="700" fill="{TEXT}">{xml_escape(title)}</text>'
                       f'<path d="M78 270H690" stroke="{accent}" stroke-width="3"/>'
                       f'<text x="78" y="316" font-family="Segoe UI, Arial, sans-serif" '
                       f'font-size="20" letter-spacing="6" fill="{accent}">AEGEANWORKS · {xml_escape(kind.upper())}</text>')
        tagline = "".join(
            f'<text x="80" y="{378 + index * 42}" font-family="Georgia, Times New Roman, serif" '
            f'font-size="29" fill="{TEXT}" fill-opacity="0.74">{xml_escape(line)}</text>'
            for index, line in enumerate(lines))
        chips = _chips(tags or (kind, "aegeanworks", "software"), 80, 506)
    elif layout == "grid":
        pattern = "".join(_motif(motif, accent, accent2, x, y, 0.55, 0.10)
                          for x in (160, 440, 720, 1000) for y in (130, 400))
        mark = _motif(motif, accent, accent2, 188, 318, 2.0)
        title_block = (f'<text x="384" y="250" font-family="Segoe UI, Arial, sans-serif" '
                       f'font-size="{font_size}" font-weight="700" fill="{TEXT}">{xml_escape(title)}</text>'
                       f'<text x="386" y="296" font-family="Segoe UI, Arial, sans-serif" '
                       f'font-size="21" letter-spacing="5" fill="{accent}">AEGEANWORKS · {xml_escape(kind.upper())}</text>')
        tagline = "".join(
            f'<text x="386" y="{348 + index * 42}" font-family="Segoe UI, Arial, sans-serif" '
            f'font-size="28" fill="{TEXT}" fill-opacity="0.74">{xml_escape(line)}</text>'
            for index, line in enumerate(lines))
        chips = _chips(tags or (kind, "aegeanworks", "software"), 386, 502)
        mark += pattern
    elif layout == "wave":
        mark = _motif(motif, accent, accent2, 190, 300, 2.0)
        title_block = (f'<text x="390" y="246" font-family="Segoe UI, Arial, sans-serif" '
                       f'font-size="{font_size}" font-weight="700" fill="{TEXT}">{xml_escape(title)}</text>'
                       f'<text x="392" y="292" font-family="Segoe UI, Arial, sans-serif" '
                       f'font-size="21" letter-spacing="5" fill="{accent}">AEGEANWORKS · {xml_escape(kind.upper())}</text>')
        tagline = "".join(
            f'<text x="392" y="{344 + index * 42}" font-family="Segoe UI, Arial, sans-serif" '
            f'font-size="28" fill="{TEXT}" fill-opacity="0.74">{xml_escape(line)}</text>'
            for index, line in enumerate(lines))
        chips = _chips(tags or (kind, "aegeanworks", "software"), 392, 500)
    else:
        mark = _motif(motif, accent, accent2, 190, 310, 2.0)
        title_block = (f'<text x="390" y="246" font-family="Segoe UI, Arial, sans-serif" '
                       f'font-size="{font_size}" font-weight="700" fill="{TEXT}">{xml_escape(title)}</text>'
                       f'<text x="392" y="292" font-family="Segoe UI, Arial, sans-serif" '
                       f'font-size="21" letter-spacing="5" fill="{accent}">AEGEANWORKS · {xml_escape(kind.upper())}</text>')
        tagline = "".join(
            f'<text x="392" y="{344 + index * 42}" font-family="Segoe UI, Arial, sans-serif" '
            f'font-size="28" fill="{TEXT}" fill-opacity="0.74">{xml_escape(line)}</text>'
            for index, line in enumerate(lines))
        chips = _chips(tags or (kind, "aegeanworks", "software"), 392, 500)
    panel = ""
    if layout == "split":
        panel = (f'<path d="M0 0H470L300 640H0Z" fill="{accent}" fill-opacity="0.09"/>'
                 f'<path d="M470 0L300 640" stroke="{accent}" stroke-opacity="0.30" stroke-width="2"/>')
    return f'''<svg xmlns="http://www.w3.org/2000/svg" width="1280" height="640" viewBox="0 0 1280 640" role="img" aria-labelledby="title desc" data-motif="{xml_escape(motif)}" data-layout="{xml_escape(layout)}">
  <title id="title">{xml_escape(title)} social preview</title>
  <desc id="desc">{xml_escape(description)}</desc>
  <defs>
    <linearGradient id="bg" x1="0" y1="0" x2="1" y2="1"><stop offset="0" stop-color="{bg1}"/><stop offset="1" stop-color="{bg2}"/></linearGradient>
    <radialGradient id="glow" cx="0.2" cy="0.12" r="0.95"><stop offset="0" stop-color="{accent}" stop-opacity="0.28"/><stop offset="1" stop-color="{accent}" stop-opacity="0"/></radialGradient>
    <linearGradient id="band" x1="0" y1="0" x2="1" y2="0"><stop offset="0" stop-color="{accent}"/><stop offset="1" stop-color="{accent2}"/></linearGradient>
  </defs>
  <rect width="1280" height="640" fill="url(#bg)"/>
  <rect width="1280" height="640" fill="url(#glow)"/>
  {panel}
  <g opacity="0.15" stroke="{TEXT}">
    <path d="M0 128H1280M0 256H1280M0 384H1280M0 512H1280M256 0V640M512 0V640M768 0V640M1024 0V640"/>
  </g>
  {mark}
  {title_block}
  {tagline}
  {chips}
  <text x="76" y="592" font-family="Segoe UI, Arial, sans-serif" font-size="19" letter-spacing="6" fill="{TEXT}" fill-opacity="0.50">AEGEANWORKS</text>
  <text x="1204" y="592" text-anchor="end" font-family="Segoe UI, Arial, sans-serif" font-size="20" fill="{accent}">{xml_escape(repo_url)}</text>
</svg>
'''
