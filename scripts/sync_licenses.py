#!/usr/bin/env python3
"""
Synchronize AIKit's pinned license copies with the canonical aegean-licensing repository.

AIKit ships `licenses/AL-1.1.md` and its siblings so a project can be created offline, and
`licenses/PIN.json` records their digests. The audit found the catalog had drifted between the two
repositories because the copy was manual. This command makes the check explicit:

    python scripts/sync_licenses.py --check   # read-only; exit 1 on drift
    python scripts/sync_licenses.py --write   # copy the canonical texts and refresh PIN.json

The source defaults to the sibling checkout `projects/aegean-licensing/licenses`. Without that
checkout, `--check` still verifies AIKit's target files against `PIN.json`, so a standalone
installation can detect local tampering (ADR-225).
"""

from __future__ import annotations

import sys
from pathlib import Path

ROOT_DIR = Path(__file__).resolve().parent.parent
DEFAULT_SOURCE = ROOT_DIR / "projects" / "aegean-licensing" / "licenses"
TARGET_DIR = ROOT_DIR / "licenses"
PIN_FILE = TARGET_DIR / "PIN.json"
SYNC_FILES = (
    "AL-1.0.md",
    "AL-1.1.md",
    "ACL-1.0.md",
    "AGL-1.0.md",
    "AGL-1.1.md",
    "ASL-1.0.md",
    "ASL-1.1.md",
    "RESTRICTED-NOTICE.md",
    "CATALOG.md",
)
PIN_NOTE = ("Copies of the canonical Aegean license texts. Update with "
            "`python scripts/sync_licenses.py --write` after changing aegean-licensing (ADR-225).")

# Generated from `build_parser().format_help()`; `test_generated_help_matches_the_parser` in
# tests/test_kit.py keeps it in sync. Printing it avoids importing argparse (~130 ms) on --help.
TOP_LEVEL_HELP = """\
usage: sync_licenses.py [-h] [--check] [--write] [--source SOURCE]
                        [--target TARGET]

Check or synchronize AIKit's pinned license copies.

options:
  -h, --help       show this help message and exit
  --check          verify the pinned copies (default action)
  --write          copy the canonical texts and refresh PIN.json
  --source SOURCE  canonical license folder (default: projects/aegean-
                   licensing/licenses)
  --target TARGET  pinned license folder (default: licenses)
"""


def _normalize(text: str) -> str:
    return text.replace("\r\n", "\n").replace("\r", "\n")


def _read_text(path: Path) -> str:
    with open(path, encoding="utf-8", newline="") as handle:
        return handle.read()


def _digest(path: Path) -> str:
    import hashlib

    return hashlib.sha256(_normalize(_read_text(path)).encode()).hexdigest()


def _write_text(path: Path, text: str) -> None:
    """Atomic write with a same-directory temp file, fsync and replace (PRINCIPLE-013)."""
    import os

    path.parent.mkdir(parents=True, exist_ok=True)
    temp = path.with_name(path.name + ".tmp_sync")
    with open(temp, "w", encoding="utf-8", newline="") as handle:
        handle.write(text)
        handle.flush()
        os.fsync(handle.fileno())
    temp.replace(path)


def expected_pin(source: Path) -> dict[str, object]:
    """The PIN.json content the source tree should produce."""
    sha256 = {name: _digest(source / name) for name in SYNC_FILES if name != "CATALOG.md"}
    return {
        "source": "https://github.com/AegeanWorks/aegean-licensing",
        "path": "licenses/",
        "note": PIN_NOTE,
        "sha256": sha256,
        "catalog_sha256": _digest(source / "CATALOG.md"),
    }


def check_licenses(source: Path | None = None, target: Path = TARGET_DIR) -> list[str]:
    """
    Return every drift or tamper finding; empty means the pinned copies are consistent. When
    `source` exists, each canonical text is compared to the target; the target is always checked
    against `PIN.json`.
    """
    import json

    errors: list[str] = []
    pin_path = target / "PIN.json"
    try:
        pin = json.loads(pin_path.read_text(encoding="utf-8"))
    except (OSError, ValueError) as exc:
        return [f"{pin_path}: {exc}"]
    recorded = pin.get("sha256")
    if not isinstance(recorded, dict):
        errors.append(f"{pin_path}: missing sha256 map")
        recorded = {}
    for name in SYNC_FILES:
        if name == "CATALOG.md":
            continue
        path = target / name
        if not path.is_file():
            errors.append(f"{path}: missing")
        elif recorded.get(name) != _digest(path):
            errors.append(f"{path}: digest differs from PIN.json")
    catalog = target / "CATALOG.md"
    if not catalog.is_file():
        errors.append(f"{catalog}: missing")
    elif pin.get("catalog_sha256") != _digest(catalog):
        errors.append(f"{catalog}: digest differs from PIN.json")
    if source is not None and source.is_dir():
        for name in SYNC_FILES:
            source_path = source / name
            target_path = target / name
            if not source_path.is_file():
                errors.append(f"{source_path}: missing canonical file")
            elif not target_path.is_file():
                errors.append(f"{target_path}: missing pinned copy")
            elif _normalize(source_path.read_text(encoding="utf-8")) != _normalize(
                    target_path.read_text(encoding="utf-8")):
                errors.append(f"{target_path}: differs from {source_path}")
    return errors


def sync_licenses(source: Path = DEFAULT_SOURCE, target: Path = TARGET_DIR) -> None:
    """Copy every canonical text into the target and rewrite PIN.json."""
    import json

    if not source.is_dir():
        raise FileNotFoundError(f"canonical license folder not found: {source}")
    for name in SYNC_FILES:
        source_path = source / name
        if not source_path.is_file():
            raise FileNotFoundError(f"canonical file not found: {source_path}")
    target.mkdir(parents=True, exist_ok=True)
    for name in SYNC_FILES:
        text = _read_text(source / name)
        _write_text(target / name, text)
    pin = expected_pin(source)
    _write_text(target / "PIN.json",
                json.dumps(pin, indent=2, ensure_ascii=False) + "\n")


def build_parser():
    """The full parser; imported lazily so the top-level help stays under the startup budget."""
    import argparse

    parser = argparse.ArgumentParser(
        prog="sync_licenses.py",
        description="Check or synchronize AIKit's pinned license copies.")
    parser.add_argument("--check", action="store_true",
                        help="verify the pinned copies (default action)")
    parser.add_argument("--write", action="store_true",
                        help="copy the canonical texts and refresh PIN.json")
    parser.add_argument("--source", type=Path, default=DEFAULT_SOURCE,
                        help="canonical license folder (default: projects/aegean-licensing/licenses)")
    parser.add_argument("--target", type=Path, default=TARGET_DIR,
                        help="pinned license folder (default: licenses)")
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    if args.write and args.check:
        print("Why: --check and --write do opposite things.", file=sys.stderr)
        print("Fix: run one of them.", file=sys.stderr)
        return 2
    if args.write:
        try:
            sync_licenses(args.source, args.target)
        except (OSError, ValueError) as exc:
            print(f"[FAIL] {exc}", file=sys.stderr)
            return 1
        print(f"[OK] Synchronized {len(SYNC_FILES)} files from {args.source} to {args.target}.")
        return 0
    errors = check_licenses(args.source, args.target)
    if errors:
        for error in errors:
            print(f"[FAIL] {error}", file=sys.stderr)
        print("Why: AIKit uses pinned copies, so a drifted copy can seed the wrong text.",
              file=sys.stderr)
        print("Fix: run `python scripts/sync_licenses.py --write`, review the diff, and commit.",
              file=sys.stderr)
        return 1
    print(f"[OK] Pinned license texts and catalog match ({len(SYNC_FILES)} files).")
    return 0


if __name__ == "__main__":
    if any(argument in ("-h", "--help") for argument in sys.argv[1:]):
        print(TOP_LEVEL_HELP, end="")
        sys.exit(0)
    sys.exit(main())
