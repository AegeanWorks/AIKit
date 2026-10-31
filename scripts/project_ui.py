"""
Project UI identifier (ADR-233): does this project have a user interface a screenshot can show?

A deterministic, stdlib-only scan of marker files, framework dependencies and markup. The result
is written to `.aikit/project.json` as `has_ui`, `ui_kind`, `ui_evidence`, `ui_checked_at` and
`ui_source`, so the screenshot and dossier pipeline never guesses from a project name. A manual
`--set yes|no` is preserved until the next explicit `--set auto`.
"""

import json
import time
from pathlib import Path
from typing import Dict, List, Optional, Tuple

from scripts.disruption_recovery import atomic_write_json, file_lock
from scripts.project_registry import config_path, load_config

UI_WEB = "web"
UI_DESKTOP = "desktop"
UI_GAME = "game"
UI_MOBILE = "mobile"
UI_CLI = "cli"
UI_LIBRARY = "library"
UI_SERVICE = "service"
UI_KINDS = (UI_WEB, UI_DESKTOP, UI_GAME, UI_MOBILE, UI_CLI, UI_LIBRARY, UI_SERVICE)
UI_KINDS_WITH_SCREENSHOTS = frozenset({UI_WEB, UI_DESKTOP, UI_GAME, UI_MOBILE})
MAX_SCAN_FILES = 500
MARKUP_LIMIT_BYTES = 250_000
SKIP_DIRS = frozenset({".git", ".aikit", "node_modules", "dist", "build", "target", "vendor",
                       ".venv", "venv", "__pycache__", ".next", ".nuxt", "coverage"})
WEB_MARKERS = ("index.html", "app.html", "public/index.html", "docs/index.html",
               "web/index.html", "frontend/index.html", "src/index.html")
FRAMEWORKS = {
    "react": UI_WEB, "vue": UI_WEB, "svelte": UI_WEB, "next": UI_WEB, "nuxt": UI_WEB,
    "angular": UI_WEB, "@angular/core": UI_WEB, "vite": UI_WEB, "astro": UI_WEB,
    "electron": UI_DESKTOP, "@tauri-apps/api": UI_DESKTOP, "tauri": UI_DESKTOP,
    "react-native": UI_MOBILE, "expo": UI_MOBILE, "capacitor": UI_MOBILE,
}
PYTHON_GUI = ("tkinter", "ttkbootstrap", "customtkinter", "pyqt", "pyside", "kivy",
              "wxpython", "dearpygui", "pyglet", "streamlit", "gradio", "textual", "pygame",
              "arcade")
GAME_MARKERS = ("project.godot", "game.project", "*.unity", "*.uproject")
MOBILE_MARKERS = ("android", "ios", "*.xcodeproj")
CLI_TOKENS = ("argparse", "click", "typer", "docopt", "fire", "console_scripts", "entry_points")


def _scan_files(root: Path) -> List[Path]:
    files = []
    for path in root.rglob("*"):
        if len(files) >= MAX_SCAN_FILES:
            break
        if any(part in SKIP_DIRS for part in path.parts):
            continue
        if path.is_file():
            files.append(path)
    return files


def _read_small(path: Path, limit: int = MARKUP_LIMIT_BYTES) -> str:
    try:
        if path.stat().st_size > limit:
            return ""
        return path.read_text(encoding="utf-8", errors="replace")
    except OSError:
        return ""


def _package_dependencies(root: Path) -> Dict[str, str]:
    package = root / "package.json"
    try:
        data = json.loads(package.read_text(encoding="utf-8")) if package.is_file() else {}
    except (OSError, ValueError):
        return {}
    found: Dict[str, str] = {}
    if not isinstance(data, dict):
        return found
    for key in ("dependencies", "devDependencies", "peerDependencies"):
        value = data.get(key)
        if isinstance(value, dict):
            found.update({str(name).lower(): str(version) for name, version in value.items()})
    return found


def _python_dependency_text(root: Path) -> str:
    parts = []
    for name in ("requirements.txt", "requirements-dev.txt", "pyproject.toml", "setup.py",
                 "setup.cfg", "Pipfile"):
        text = _read_small(root / name)
        if text:
            parts.append(text.lower())
    return "\n".join(parts)


def _evidence(paths: List[Path], root: Path, limit: int = 12) -> List[str]:
    seen = []
    for path in paths:
        try:
            relative = path.relative_to(root).as_posix()
        except ValueError:
            continue
        if relative not in seen:
            seen.append(relative)
    return sorted(seen)[:limit]


def _html_files(files: List[Path], root: Path) -> List[Path]:
    found = []
    for path in files:
        if path.suffix.lower() not in {".html", ".htm"}:
            continue
        text = _read_small(path).lower()
        if "<html" in text or "<body" in text or "<div" in text:
            found.append(path)
    return found


def detect_ui(project_root: Path, respect_manual: bool = True) -> Dict[str, object]:
    """Classify a project's interface, with the marker files that justify the answer."""
    root = Path(project_root)
    config = load_config(root) if config_path(root).is_file() else {}
    if respect_manual and config.get("ui_source") == "manual" and isinstance(config.get("has_ui"), bool):
        return {
            "has_ui": bool(config["has_ui"]),
            "kind": str(config.get("ui_kind") or UI_LIBRARY),
            "evidence": list(config.get("ui_evidence") or []),
            "source": "manual",
        }
    files = _scan_files(root)
    deps = _package_dependencies(root)
    python_deps = _python_dependency_text(root)
    evidence: List[Path] = []
    kind = UI_LIBRARY
    for marker in WEB_MARKERS:
        path = root / marker
        if path.is_file():
            evidence.append(path)
            kind = UI_WEB
    html = _html_files(files, root)
    if html:
        evidence.extend(html)
        kind = UI_WEB
    for name, framework_kind in FRAMEWORKS.items():
        if name in deps:
            evidence.append(root / "package.json")
            if framework_kind in {UI_DESKTOP, UI_MOBILE}:
                kind = framework_kind
            elif kind not in {UI_DESKTOP, UI_MOBILE}:
                kind = UI_WEB
    for token in PYTHON_GUI:
        if token in python_deps:
            evidence.append(root / "pyproject.toml" if (root / "pyproject.toml").exists()
                            else root / "requirements.txt")
            kind = UI_GAME if token in {"pygame", "arcade"} else UI_DESKTOP
            break
    for pattern in GAME_MARKERS:
        matches = list(root.glob(pattern))
        if matches:
            evidence.extend(matches)
            kind = UI_GAME
            break
    for marker in MOBILE_MARKERS:
        path = root / marker
        if path.exists():
            evidence.append(path)
            kind = UI_MOBILE
            break
    if kind == UI_LIBRARY:
        cli_text = python_deps + "\n" + "\n".join(_read_small(path)[:20_000] for path in files
                                                 if path.suffix == ".py" and path.stat().st_size < 100_000)
        if any(token in cli_text for token in CLI_TOKENS):
            kind = UI_CLI
            evidence.extend(path for path in files
                            if path.suffix == ".py" and any(token in _read_small(path, 20_000)
                                                            for token in CLI_TOKENS))
        elif any((root / name).exists() for name in ("main.py", "app.py", "server.py")):
            kind = UI_SERVICE
            evidence.extend(root / name for name in ("main.py", "app.py", "server.py")
                            if (root / name).exists())
    if config.get("ui_required") is True:
        kind = UI_WEB if kind == UI_LIBRARY else kind
        if not evidence:
            evidence.append(config_path(root))
    return {
        "has_ui": kind in UI_KINDS_WITH_SCREENSHOTS,
        "kind": kind,
        "evidence": _evidence(evidence, root),
        "source": "detected",
    }


def write_ui_identity(project_root: Path, result: Dict[str, object]) -> Dict[str, object]:
    """Persist the identifier atomically, preserving the rest of the project's memory."""
    result = dict(result)
    result.setdefault("checked_at", time.strftime("%Y-%m-%d"))
    path = config_path(project_root)
    if not path.is_file():
        raise FileNotFoundError(path)
    with file_lock(path):
        config = load_config(project_root)
        updated = {
            "has_ui": bool(result.get("has_ui")),
            "ui_kind": str(result.get("kind") or UI_LIBRARY),
            "ui_evidence": list(result.get("evidence") or []),
            "ui_checked_at": result.get("checked_at") or "",
            "ui_source": str(result.get("source") or "detected"),
        }
        if all(config.get(key) == value for key, value in updated.items()):
            return config
        config.update(updated)
        atomic_write_json(path, config)
    return config


def set_ui_manual(project_root: Path, has_ui: bool, kind: Optional[str] = None) -> Dict[str, object]:
    """Record an explicit human/agent decision; `auto` clears it on the next detection."""
    detected = detect_ui(project_root, respect_manual=False)
    result = {
        "has_ui": has_ui,
        "kind": kind or (detected["kind"] if has_ui else UI_LIBRARY),
        "evidence": detected["evidence"],
        "source": "manual",
    }
    write_ui_identity(project_root, result)
    return result


def auto_ui(project_root: Path) -> Dict[str, object]:
    result = detect_ui(project_root, respect_manual=False)
    write_ui_identity(project_root, result)
    return result


def refresh_ui_identifier(project_root: Path) -> Dict[str, object]:
    """Re-detect after UI work; a UI command or capture proves a screenshotable surface exists."""
    detected = detect_ui(project_root, respect_manual=False)
    if not detected["has_ui"]:
        kind = str(detected["kind"])
        detected = {
            "has_ui": True,
            "kind": "web" if kind == UI_LIBRARY else kind,
            "evidence": detected["evidence"],
            "source": "manual",
        }
    config = load_config(project_root)
    unchanged = (
        bool(config.get("has_ui")) == bool(detected["has_ui"])
        and str(config.get("ui_kind") or "") == str(detected["kind"] or UI_LIBRARY)
        and list(config.get("ui_evidence") or []) == list(detected["evidence"] or [])
        and str(config.get("ui_source") or "") == str(detected["source"] or "detected")
    )
    if unchanged:
        detected["checked_at"] = config.get("ui_checked_at") or time.strftime("%Y-%m-%d")
    else:
        detected.setdefault("checked_at", time.strftime("%Y-%m-%d"))
    write_ui_identity(project_root, detected)
    return detected


def ui_payload(project_root: Path) -> Dict[str, object]:
    detected = detect_ui(project_root)
    config = load_config(project_root) if config_path(project_root).is_file() else {}
    return {
        "has_ui": detected["has_ui"],
        "kind": detected["kind"],
        "evidence": detected["evidence"],
        "source": detected["source"],
        "checked_at": config.get("ui_checked_at") or "",
        "ui_required": bool(config.get("ui_required")),
    }


def _surface_paths(project_root: Path, evidence: List[str]) -> List[str]:
    """The smallest practical surface: detected entry files plus a source tree if one exists."""
    paths: List[str] = []
    for relative in evidence:
        if (project_root / relative).is_file() and relative not in paths:
            paths.append(relative)
    for relative, pattern in (("src", "src/**"), ("game.js", "game.js"), ("public", "public/**")):
        if (project_root / relative).exists() and pattern not in paths:
            paths.append(pattern)
    return paths


def adopt_ui(project_root: Path, test_command: str = "") -> Dict[str, object]:
    """Adopt a detected UI project into the bounded UI contract, without guessing a proof.

    A contract is written only when the project already has a test command to act as its fast
    proof; otherwise the caller gets the reason and can run `aikit ui init` with a real command.
    Existing contracts are kept and only marked required.
    """
    project_root = Path(project_root)
    identity = auto_ui(project_root)
    if not identity.get("has_ui"):
        return {"adopted": False, "reason": "no UI detected"}
    from scripts import ui_contract

    contract = project_root / ui_contract.CONTRACT_REL
    adopted = False
    if not contract.is_file():
        paths = _surface_paths(project_root, list(identity.get("evidence") or []))
        if not test_command.strip():
            return {"adopted": False,
                    "reason": "UI detected but the project has no test command; run aikit ui init"}
        if not paths:
            return {"adopted": False,
                    "reason": "UI detected but no surface path could be bounded; run aikit ui init"}
        ui_contract.scaffold_contract(project_root, "app", fast=test_command.strip(),
                                      paths=paths, snapshot="")
        adopted = True
    config = load_config(project_root)
    if config.get("ui_required") is not True:
        config["ui_required"] = True
        atomic_write_json(config_path(project_root), config)
    return {"adopted": adopted, "reason": ""}
