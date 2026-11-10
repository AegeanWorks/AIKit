#!/usr/bin/env python3
"""
AI-compat scaffold and proof for generated projects (Track 2, now).

A generated project is AI-compatible by construction when an agent with zero
project-specific tooling can drive it and verify it: a machine-readable UI
inventory, a scripted run with world-state deltas (headless), screenshots with
before/after pairs (UI), and analysis hooks (layout map, clickmap, evidence).

This module is stdlib-only and has two entry points: `scaffold_compat` writes
the files, `verify_compat` proves them. Roadmap (browser harness, auto
clickmap emission, dossier catalog sync) stays out: it needs per-stack
dependencies and would violate PRINCIPLE-003 R3 and PRINCIPLE-001 frugality.

Usage:
  python scripts/project_compat.py --scaffold <headless|ui> --root <dir>
  python scripts/project_compat.py --verify --root <dir>
Exit codes: 0 clean, 1 findings, 2 usage error.
"""

from __future__ import annotations

import argparse
import json
import shutil
import struct
import subprocess
import sys
import zlib
from pathlib import Path
from typing import Dict, List, Sequence, Tuple

COMPAT_SCHEMA = 1
COMPAT_REL = Path(".aikit") / "compat.json"
INVENTORY_NAME = "inventory.py"
DEMO_NAME = "demo.py"
LAYOUT_REL = Path(".aikit") / "layout-map.json"
CLICKMAP_REL = Path(".aikit") / "clickmap.log"
REPLAY_REL = Path(".aikit") / "replay.log"
BENCH_BASELINE_REL = Path(".aikit") / "bench-baseline.json"
BENCH_DELTA_REL = Path(".aikit") / "bench-delta.json"
EVIDENCE_REL = Path(".aikit") / "evidence.json"
EVIDENCE_SCHEMA = 1
SEED_FLAG = "--seed"
SEED_PROBE = "7"
# The free-space floor before a disk-sensitive replay starts. Must equal
# `project_gates.DEFAULT_MIN_FREE_MB`; a test pins them, because importing it here would
# create the registry -> compat -> gates -> registry cycle the structure gate rejects.
MIN_FREE_MB = 10.0
SCREENSHOT_DIR = Path("assets") / "screenshots"
BEFORE_NAME = "before.png"
AFTER_NAME = "after.png"
PNG_SIGNATURE = b"\x89PNG\r\n\x1a\n"
FAST_TIMEOUT = 30.0

Runner = Tuple[int, str]


def _error(message: str, why: str, fix: str) -> ValueError:
    return ValueError(f"{message}\nWhy: {why}\nFix: {fix}")


def minimal_png_rgb(red: int = 0, green: int = 0, blue: int = 0) -> bytes:
    """A valid 1x1 RGB PNG, stdlib-only, for scaffolded screenshot placeholders."""
    raw = bytes((0, red & 0xFF, green & 0xFF, blue & 0xFF))
    compressed = zlib.compress(raw)

    def chunk(tag: bytes, data: bytes) -> bytes:
        out = struct.pack(">I", len(data)) + tag + data
        out += struct.pack(">I", zlib.crc32(tag + data) & 0xFFFFFFFF)
        return out
    ihdr = struct.pack(">IIBBBBB", 1, 1, 8, 2, 0, 0, 0)
    return (PNG_SIGNATURE + chunk(b"IHDR", ihdr)
            + chunk(b"IDAT", compressed) + chunk(b"IEND", b""))


def minimal_png(variant: int = 0) -> bytes:
    """Legacy single-channel placeholder; prefer ``minimal_png_rgb`` for pairs.

    Only the red channel varies, so before/after pairs built from this alone
    are byte-different but visually indistinguishable. New scaffolds use
    black vs white via ``minimal_png_rgb`` to read as a state change.
    """
    return minimal_png_rgb(variant, 0, 0)


def _inventory_template(kind: str) -> str:
    if kind == "ui":
        lines = [
            "button|Save|save-btn",
            "input|Name|name-field",
            "handler|save|on-save",
        ]
    else:
        lines = [
            "cli|demo|--scripted",
            "cli|inventory|inventory.py",
            "handler|run|demo-run",
        ]
    joined = "\n".join(f"    print({line!r})" for line in lines)
    return (
        "#!/usr/bin/env python3\n"
        "\"\"\"Project-owned UI inventory: one `kind|name|locator` line per control.\"\"\"\n"
        "if __name__ == \"__main__\":\n"
        f"{joined}\n"
    )


def _demo_template(kind: str) -> str:
    return (
        "#!/usr/bin/env python3\n"
        "\"\"\"Headless scripted drive: prints WORLD-DELTA lines, no input, exits 0.\"\"\"\n"
        "import sys\n"
        "def _parse_seed(argv):\n"
        "    seed = 0\n"
        "    if \"--seed\" in argv:\n"
        "        index = argv.index(\"--seed\")\n"
        "        try:\n"
        "            seed = int(argv[index + 1])\n"
        "        except (IndexError, ValueError):\n"
        "            print(\"Usage: python demo.py --scripted [--seed N]\")\n"  # hygiene: allow usage text for demo.py in the scaffolded project
        "            sys.exit(2)\n"
        "    return seed\n"
        "if __name__ == \"__main__\":\n"
        "    if \"--scripted\" not in sys.argv:\n"
        "        print(\"Usage: python demo.py --scripted [--seed N]\")\n"  # hygiene: allow usage text for demo.py in the scaffolded project
        "        sys.exit(2)\n"
        "    _seed = _parse_seed(sys.argv)\n"
        "    print(f\"SEED: {_seed}\")\n"
        "    print(f\"WORLD-DELTA: counter={_seed}->{_seed + 1}\")\n"
        "    print(f\"WORLD-DELTA: items={_seed + 2}->{_seed + 3}\")\n"
        "    print(\"OK: scripted drive complete\")\n"
    )


def scaffold_compat(root: Path, kind: str) -> Dict[str, object]:
    """Write compat files for `headless` or `ui`; returns the compat record."""
    if kind not in ("headless", "ui"):
        raise _error(f"Unknown compat kind '{kind}'.",
                     "the scaffold knows headless and ui only.",
                     "pass --scaffold headless or --scaffold ui.")
    root = Path(root)
    (root / ".aikit").mkdir(parents=True, exist_ok=True)
    (root / SCREENSHOT_DIR).mkdir(parents=True, exist_ok=True)
    has_ui = kind == "ui"
    compat: Dict[str, object] = {
        "schema": COMPAT_SCHEMA,
        "kind": kind,
        "has_ui": has_ui,
        "commands": {
            "inventory": f"python {INVENTORY_NAME}",
            "scripted": f"python {DEMO_NAME} --scripted",
        },
        "seed": {
            "flag": SEED_FLAG,
            "replay_log": REPLAY_REL.as_posix(),
        },
        "bench": {
            "baseline": BENCH_BASELINE_REL.as_posix(),
            "delta": BENCH_DELTA_REL.as_posix(),
        },
        "evidence": {
            "schema": EVIDENCE_SCHEMA,
            "file": EVIDENCE_REL.as_posix(),
        },
        "screenshots": {
            "dir": SCREENSHOT_DIR.as_posix(),
            "before": (SCREENSHOT_DIR / BEFORE_NAME).as_posix() if has_ui else "",
            "after": (SCREENSHOT_DIR / AFTER_NAME).as_posix() if has_ui else "",
        },
        "hooks": {
            "layout_map": LAYOUT_REL.as_posix(),
            "clickmap": CLICKMAP_REL.as_posix(),
        },
    }
    (root / COMPAT_REL).write_text(json.dumps(compat, indent=2) + "\n", encoding="utf-8")
    (root / INVENTORY_NAME).write_text(_inventory_template(kind), encoding="utf-8")
    (root / DEMO_NAME).write_text(_demo_template(kind), encoding="utf-8")
    (root / REPLAY_REL).write_text("", encoding="utf-8")
    (root / BENCH_BASELINE_REL).write_text(
        json.dumps({"baseline_seed": 0, "note": "benchmark-before-land baseline"}, indent=2) + "\n",
        encoding="utf-8")
    (root / BENCH_DELTA_REL).write_text(
        json.dumps({"seed": 0, "deltas": 2}, indent=2) + "\n", encoding="utf-8")
    (root / EVIDENCE_REL).write_text(
        json.dumps({"schema": EVIDENCE_SCHEMA, "links": []}, indent=2) + "\n", encoding="utf-8")
    layout = {"controls": [
        {"name": "save-btn", "box": [10, 10, 80, 24]},
        {"name": "name-field", "box": [10, 40, 160, 24]},
    ]} if has_ui else {"controls": []}
    (root / LAYOUT_REL).write_text(json.dumps(layout, indent=2) + "\n", encoding="utf-8")
    (root / CLICKMAP_REL).write_text(
        "click save-btn -> on-save\n" if has_ui else "", encoding="utf-8")
    if has_ui:
        # Black vs white reads as a state change; the old red-channel-only
        # pair (0 vs 1) was byte-different but visually identical.
        (root / SCREENSHOT_DIR / BEFORE_NAME).write_bytes(minimal_png_rgb(0, 0, 0))
        (root / SCREENSHOT_DIR / AFTER_NAME).write_bytes(minimal_png_rgb(255, 255, 255))
    return compat


def load_compat(root: Path) -> Dict[str, object]:
    """Load and validate the project's compat record."""
    path = Path(root) / COMPAT_REL
    if not path.is_file():
        raise _error(f"No compat record at {COMPAT_REL}.",
                     "verify needs the scaffolded compat contract.",
                     "run `python scripts/project_compat.py --scaffold <kind> --root <dir>` first.")
    try:
        raw = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError) as exc:
        raise _error(f"Cannot read {COMPAT_REL}: {exc}",
                     "the compat record must be valid JSON.",
                     "repair or re-scaffold it.") from exc
    if not isinstance(raw, dict) or raw.get("schema") != COMPAT_SCHEMA:
        raise _error("The compat schema is not supported.",
                     "this reader handles schema 1 only.",
                     f"set \"schema\": {COMPAT_SCHEMA} in {COMPAT_REL}.")
    return raw


def inventory_lines(output: str) -> List[str]:
    """Sorted, deduplicated non-empty inventory lines."""
    return sorted({line.strip() for line in output.splitlines() if line.strip()})


def _run(cmd: str, root: Path, timeout: float = FAST_TIMEOUT) -> Runner:
    try:
        done = subprocess.run(cmd.split(), cwd=str(root), stdin=subprocess.DEVNULL,
                              capture_output=True, text=True, encoding="utf-8",
                              errors="replace", timeout=timeout)
    except subprocess.TimeoutExpired:
        return 124, f"timed out after {timeout:g}s"
    except OSError as exc:
        return 127, str(exc)
    return done.returncode, (done.stdout + done.stderr).strip()


def _delta_lines(output: str) -> List[str]:
    """Sorted WORLD-DELTA lines; the seeded-replay identity check compares these."""
    return sorted(line.strip() for line in output.splitlines() if "WORLD-DELTA:" in line)


def emit_evidence(root: Path, cause: str, gate: str, artifact: str) -> Dict[str, object]:
    """Append one cause -> gate -> artifact link to the scaffolded evidence file."""
    root = Path(root)
    path = root / EVIDENCE_REL
    try:
        record = json.loads(path.read_text(encoding="utf-8")) if path.is_file() else {}
    except (OSError, ValueError):
        record = {}
    if not isinstance(record, dict) or record.get("schema") != EVIDENCE_SCHEMA:
        record = {"schema": EVIDENCE_SCHEMA, "links": []}
    links = record.get("links")
    if not isinstance(links, list):
        links = []
        record["links"] = links
    entry = {"cause": str(cause), "gate": str(gate), "artifact": str(artifact)}
    links.append(entry)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(record, indent=2) + "\n", encoding="utf-8")
    return entry


def compass_report(findings: List[str]) -> Dict[str, object]:
    """Quality-as-compass: scores are info, only missing evidence fails.

    Never gates on a numeric threshold; a threshold would turn the compass into
    a target and invite gaming (PRINCIPLE-000 R5). Callers fail on the findings
    list, never on the score value.
    """
    return {"score_info": "compass only", "missing_evidence": list(findings)}


def verify_compat(root: Path, runner=None) -> List[str]:
    """Prove the scaffolded project is drivable; returns findings (empty is clean)."""
    compat = load_compat(root)
    root = Path(root)
    run = runner or _run
    findings: List[str] = []
    commands = compat.get("commands") if isinstance(compat.get("commands"), dict) else {}
    inv_cmd = commands.get("inventory") if isinstance(commands, dict) else ""
    scr_cmd = commands.get("scripted") if isinstance(commands, dict) else ""
    if not isinstance(inv_cmd, str) or not inv_cmd.strip():
        return ["compat record declares no inventory command."]
    if not isinstance(scr_cmd, str) or not scr_cmd.strip():
        return ["compat record declares no scripted command."]
    code, out = run(str(inv_cmd), root)
    if code != 0:
        findings.append(f"inventory command failed (exit {code}):\n{out[-400:]}")
        return findings
    entries = inventory_lines(out)
    if not entries:
        findings.append("inventory command printed no entries.")
    else:
        bad = [e for e in entries if len(e.split("|")) != 3 or not all(p.strip() for p in e.split("|"))]
        if bad:
            findings.append(f"inventory lines must be kind|name|locator: {bad[0][:120]}")
    code, out = run(str(scr_cmd), root)
    if code != 0:
        findings.append(f"scripted command failed (exit {code}):\n{out[-400:]}")
    elif "WORLD-DELTA:" not in out:
        findings.append("scripted command printed no WORLD-DELTA lines.")
    seed_cfg = compat.get("seed") if isinstance(compat.get("seed"), dict) else None
    if seed_cfg is not None:
        flag = seed_cfg.get("flag") if isinstance(seed_cfg, dict) else ""
        if not isinstance(flag, str) or flag.strip() != SEED_FLAG:
            findings.append(f"compat seed flag must be {SEED_FLAG!r}.")
        else:
            free_mb = None
            try:
                free_mb = shutil.disk_usage(root).free / (1024 * 1024)
            except OSError:  # hygiene: allow an unreadable disk figure; the replay still runs
                pass
            # Same floor the gate preflight uses. Declared here rather than imported from
            # `project_gates` (that would close registry -> compat -> gates -> registry);
            # a test pins the two constants equal so they cannot drift.
            if free_mb is not None and free_mb < MIN_FREE_MB:
                findings.append(
                    f"seeded replay not started (infra): {free_mb:.1f} MB free; at least "
                    f"{MIN_FREE_MB:.0f} MB is required.")
            else:
                first_code, first_out = run(f"{scr_cmd} {SEED_FLAG} {SEED_PROBE}", root)
                second_code, second_out = run(f"{scr_cmd} {SEED_FLAG} {SEED_PROBE}", root)
                if first_code != 0 or second_code != 0:
                    # Preserve the cause: a disk/permission failure is not a determinism verdict.
                    combined = "\n".join(part for part in (first_out, second_out) if part)
                    lowered = combined.lower()
                    if any(marker in lowered for marker in ("no space left", "not enough free space",
                                                            "not enough free", "permission denied")):
                        kind = "infra"
                    elif "timed out" in lowered:
                        kind = "timeout"
                    else:
                        kind = "product"
                    findings.append(
                        f"seeded replay could not run ({kind}: exit {first_code}/{second_code}) — "
                        f"not a determinism verdict; command: {scr_cmd} {SEED_FLAG} {SEED_PROBE}\n"
                        f"{combined[-400:]}")
                elif _delta_lines(first_out) != _delta_lines(second_out) or not _delta_lines(first_out):
                    findings.append("seeded replay diverged: same seed gave different WORLD-DELTA lines.")
    bench_cfg = compat.get("bench") if isinstance(compat.get("bench"), dict) else None
    if bench_cfg is not None:
        for key in ("baseline", "delta"):
            rel = bench_cfg.get(key) if isinstance(bench_cfg, dict) else ""
            if not isinstance(rel, str) or not rel:
                findings.append(f"compat bench needs {key}.")
                continue
            path = root / rel
            if not path.is_file():
                findings.append(f"bench {key} missing: {rel}")
                continue
            try:
                json.loads(path.read_text(encoding="utf-8"))
            except (OSError, ValueError) as exc:
                findings.append(f"bench {key} is not readable JSON: {exc}")
    evidence_cfg = compat.get("evidence") if isinstance(compat.get("evidence"), dict) else None
    if evidence_cfg is not None:
        rel = evidence_cfg.get("file") if isinstance(evidence_cfg, dict) else ""
        if not isinstance(rel, str) or not rel:
            findings.append("compat evidence needs file.")
        else:
            path = root / rel
            if not path.is_file():
                findings.append(f"evidence file missing: {rel}")
            else:
                try:
                    record = json.loads(path.read_text(encoding="utf-8"))
                except (OSError, ValueError) as exc:
                    findings.append(f"evidence file is not readable JSON: {exc}")
                else:
                    if not isinstance(record, dict) or record.get("schema") != EVIDENCE_SCHEMA:
                        findings.append("evidence schema is not supported.")
    has_ui = bool(compat.get("has_ui"))
    if has_ui:
        shots = compat.get("screenshots") if isinstance(compat.get("screenshots"), dict) else {}
        shot_bytes: Dict[str, bytes] = {}
        for key in ("before", "after"):
            rel = shots.get(key) if isinstance(shots, dict) else ""
            if not isinstance(rel, str) or not rel:
                findings.append(f"UI compat needs screenshots.{key}.")
                continue
            path = root / rel
            if not path.is_file():
                findings.append(f"screenshot missing: {rel}")
                continue
            try:
                data = path.read_bytes()
            except OSError as exc:
                findings.append(f"cannot read screenshot {rel}: {exc}")
                continue
            if data[:8] != PNG_SIGNATURE:
                findings.append(f"screenshot is not a PNG: {rel}")
                continue
            shot_bytes[key] = data
        if "before" in shot_bytes and "after" in shot_bytes:
            if shot_bytes["before"] == shot_bytes["after"]:
                findings.append(
                    "screenshots are byte-identical: before/after show no state change"
                )
        hooks = compat.get("hooks") if isinstance(compat.get("hooks"), dict) else {}
        layout_rel = hooks.get("layout_map") if isinstance(hooks, dict) else ""
        if not isinstance(layout_rel, str) or not layout_rel:
            layout_rel = LAYOUT_REL.as_posix()
        try:
            layout_raw = json.loads((root / layout_rel).read_text(encoding="utf-8"))
        except (OSError, ValueError):
            layout_raw = {}
        controls = layout_raw.get("controls") if isinstance(layout_raw, dict) else []
        if isinstance(controls, list) and controls:
            names = [c.get("name") for c in controls if isinstance(c, dict)]
            names = [n for n in names if isinstance(n, str) and n.strip()]
            tokens = {part.strip() for e in entries for part in e.split("|") if part.strip()}
            lowered = {t.lower() for t in tokens}
            missing = [n for n in names if n not in tokens and n.lower() not in lowered]
            if missing:
                findings.append(
                    f"layout controls missing from inventory: {', '.join(sorted(missing))}"
                )
        for rel_key in ("layout_map", "clickmap"):
            hooks = compat.get("hooks") if isinstance(compat.get("hooks"), dict) else {}
            rel = hooks.get(rel_key) if isinstance(hooks, dict) else ""
            if not isinstance(rel, str) or not rel or not (root / rel).is_file():
                findings.append(f"analysis hook missing: {rel_key} ({rel or 'unset'})")
    return findings


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="python scripts/project_compat.py",
                                     description="Scaffold and prove AI-compat projects.")
    parser.add_argument("--scaffold", metavar="KIND",
                        help="write compat files for headless or ui")
    parser.add_argument("--verify", action="store_true",
                        help="prove the scaffolded project is drivable")
    parser.add_argument("--root", default=".", help="project folder (default: current)")
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    root = Path(str(args.root))
    try:
        if args.scaffold:
            scaffold_compat(root, str(args.scaffold).strip())
            print(f"[OK] scaffolded {args.scaffold} compat in {root}")
            return 0
        if args.verify:
            findings = verify_compat(root)
            if findings:
                print("[FAIL] compat proof failed:", file=sys.stderr)
                for line in findings:
                    print(f"       {line}", file=sys.stderr)
                print("Why: the generated project cannot be driven with zero project-specific tooling.",
                      file=sys.stderr)
                print("Fix: re-run the scaffold, then keep inventory, deltas and screenshots green.",
                      file=sys.stderr)
                return 1
            print(f"[OK] compat proof holds in {root}")
            return 0
    except ValueError as exc:
        print(f"Error: {exc}", file=sys.stderr)
        return 2
    print("Usage: --scaffold <headless|ui> --root <dir> or --verify --root <dir>",
          file=sys.stderr)
    print("Why: exactly one action is required.", file=sys.stderr)
    print("Fix: pass --scaffold or --verify with --root.", file=sys.stderr)
    return 2


if __name__ == "__main__":
    raise SystemExit(main())
