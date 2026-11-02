"""Foundry boss-pack validator: every generated pack validates before it ships.

Stdlib only. Each violation is reported as ``field: reason`` so invalid
packs fail loudly. Structural rules mirror schemas/boss.schema.json;
semantic rules (catalog membership, one-hit cap) need the consumer
adapter and live here because JSON Schema cannot express them.
"""

from __future__ import annotations

import argparse
import json
import math
import re
import sys
from pathlib import Path
from typing import Any, Container, Dict, List

FOUNDRY_ROOT = Path(__file__).resolve().parent.parent
if str(FOUNDRY_ROOT) not in sys.path:
    sys.path.insert(0, str(FOUNDRY_ROOT))

from adapters.crypt_crawler import (  # noqa: E402
    ECONOMY_NOTE,
    ITEM_IDS,
    SUPPORTED_MAJOR,
    TARGET_GAME,
)

BOSS_ID_RE = re.compile(r"^boss_[a-z0-9_]{2,27}$")

# Slice-1 generic is_boss envelope (crypt-crawler engine.js turn loop):
#   50%: summon up to 2 skeletons + log tell; 25%: attack x1.3 + log tell.
# Phase scaling as implemented: p2 atk = ceil(atk*1.2), p3 atk = ceil(p2*1.3).
ENVELOPE = (
    {"threshold_pct": 50, "effect": "summon_skeletons"},
    {"threshold_pct": 25, "effect": "enrage"},
)

# No-one-shot bound. Engine max roll: floor(base * 1.2 * omenMult) with
# base = max(1, atk - def); worst case def = 0, omen = 1.0.
# Reference: paladin 65 base HP + 12/level, depth-3 expected level >= 3
# gives >= 89 HP; 60% of that is ~53.
ONE_HIT_CAP = 53

STAT_BANDS = {
    "hp": (20, 200),
    "attack": (3, 25),
    "defense": (0, 12),
    "xp_reward": (20, 400),
    "gold_reward": (10, 300),
}

TOP_FIELDS = {
    "pack_version",
    "target_game",
    "boss_id",
    "name",
    "stats",
    "phases",
    "loot",
    "spawn",
}


def _is_int(value: Any) -> bool:
    return type(value) is int


def max_theoretical_hit(attack: int) -> int:
    """Worst-case single-turn damage for a slice-1 boss: phase-3 attack."""
    phased = math.ceil(math.ceil(attack * 1.2) * 1.3)
    return math.floor(phased * 1.2)


def validate(pack: Any) -> List[str]:
    """Return a list of ``field: reason`` violations (empty == valid)."""
    errors: List[str] = []
    if not isinstance(pack, dict):
        return ["pack: must be a JSON object"]
    unknown = sorted(set(pack) - TOP_FIELDS)
    if unknown:
        errors.append(f"pack: unknown fields {unknown}")
    for field in sorted(TOP_FIELDS):
        if field not in pack:
            errors.append(f"{field}: missing required field")

    ver = pack.get("pack_version")
    if "pack_version" in pack:
        if not isinstance(ver, str) or not re.match(r"^1\.[0-9]+$", ver):
            errors.append(
                "pack_version: must match ^1.[0-9]+$ "
                f"(supported major {SUPPORTED_MAJOR}), got {ver!r}"
            )

    if "target_game" in pack and pack.get("target_game") != TARGET_GAME:
        errors.append(f"target_game: must be {TARGET_GAME!r}, got {pack.get('target_game')!r}")

    boss_id = pack.get("boss_id")
    if "boss_id" in pack:
        if not isinstance(boss_id, str) or not BOSS_ID_RE.match(boss_id):
            errors.append(f"boss_id: must match ^boss_[a-z0-9_]{{2,27}}$, got {boss_id!r}")

    name = pack.get("name")
    if "name" in pack:
        if not isinstance(name, str) or not (1 <= len(name) <= 60):
            errors.append("name: must be a 1-60 character string")

    stats = pack.get("stats")
    if "stats" in pack:
        if not isinstance(stats, dict):
            errors.append("stats: must be an object")
        else:
            extra = sorted(set(stats) - set(STAT_BANDS))
            if extra:
                errors.append(f"stats: unknown fields {extra}")
            for key in sorted(STAT_BANDS):
                if key not in stats:
                    errors.append(f"stats.{key}: missing required field")
                elif not _is_int(stats[key]):
                    errors.append(f"stats.{key}: must be an integer, got {stats[key]!r}")
                else:
                    lo, hi = STAT_BANDS[key]
                    if not (lo <= stats[key] <= hi):
                        errors.append(
                            f"stats.{key}: must be within [{lo}, {hi}], got {stats[key]}"
                        )
            if all(_is_int(stats.get(k)) for k in STAT_BANDS):
                hit = max_theoretical_hit(stats["attack"])
                if hit > ONE_HIT_CAP:
                    errors.append(
                        f"stats.attack: one-shot risk, max theoretical hit {hit} "
                        f"exceeds cap {ONE_HIT_CAP} (60% of depth-3 paladin HP)"
                    )

    phases = pack.get("phases")
    if "phases" in pack:
        if not isinstance(phases, list) or len(phases) != 2:
            errors.append("phases: must be exactly the 2-entry slice-1 envelope [50, 25]")
        else:
            for i, (phase, want) in enumerate(zip(phases, ENVELOPE)):
                field = f"phases[{i}]"
                if not isinstance(phase, dict):
                    errors.append(f"{field}: must be an object")
                    continue
                extra = sorted(set(phase) - {"threshold_pct", "effect", "tell"})
                if extra:
                    errors.append(f"{field}: unknown fields {extra}")
                if phase.get("threshold_pct") != want["threshold_pct"]:
                    errors.append(
                        f"{field}.threshold_pct: slice-1 envelope requires "
                        f"{want['threshold_pct']}, got {phase.get('threshold_pct')!r}"
                    )
                if phase.get("effect") != want["effect"]:
                    errors.append(
                        f"{field}.effect: slice-1 envelope requires "
                        f"{want['effect']!r}, got {phase.get('effect')!r}"
                    )
                tell = phase.get("tell")
                if not isinstance(tell, str) or not (1 <= len(tell) <= 200):
                    errors.append(f"{field}.tell: must be a 1-200 character string")

    loot = pack.get("loot")
    if "loot" in pack:
        if not isinstance(loot, dict):
            errors.append("loot: must be an object")
        else:
            extra = sorted(set(loot) - {"item_id"})
            if extra:
                errors.append(f"loot: unknown fields {extra}")
            item_id = loot.get("item_id")
            if "item_id" not in loot:
                errors.append("loot.item_id: missing required field")
            elif item_id not in ITEM_IDS:
                errors.append(
                    f"loot.item_id: unknown {item_id!r}, must resolve in "
                    f"consumer ITEM_CATALOG ({ECONOMY_NOTE})"
                )

    spawn = pack.get("spawn")
    if "spawn" in pack:
        if not isinstance(spawn, dict):
            errors.append("spawn: must be an object")
        else:
            extra = sorted(set(spawn) - {"depth", "anchor", "replaces", "seeds"})
            if extra:
                errors.append(f"spawn: unknown fields {extra}")
            if spawn.get("depth") != 3:
                errors.append(
                    f"spawn.depth: slice 1 supports depth 3 only, got {spawn.get('depth')!r}"
                )
            if spawn.get("anchor") != "stairs":
                errors.append(
                    f"spawn.anchor: slice 1 supports 'stairs' only, got {spawn.get('anchor')!r}"
                )
            if spawn.get("replaces") != "boss_lich":
                errors.append(
                    "spawn.replaces: slice 1 supports 'boss_lich' only, "
                    f"got {spawn.get('replaces')!r}"
                )
            seeds = spawn.get("seeds")
            if not isinstance(seeds, list) or not seeds:
                errors.append("spawn.seeds: must be a non-empty list of seed integers")
            elif not all(_is_int(s) and 1 <= s <= 999999 for s in seeds):
                errors.append(
                    "spawn.seeds: every seed must be an integer within [1, 999999]"
                )
    return errors


def validate_file(path: Path) -> List[str]:
    try:
        pack = json.loads(path.read_text(encoding="utf-8"))
    except FileNotFoundError:
        return [f"{path.name}: file not found"]
    except json.JSONDecodeError as exc:
        return [f"{path.name}: invalid JSON: {exc}"]
    return [f"{path.name}: {e}" for e in validate(pack)]


def main(argv: List[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description="Validate foundry boss packs.")
    ap.add_argument("packs", nargs="+", help="Pack JSON files to validate")
    args = ap.parse_args(argv)
    import glob as _glob

    files: List[str] = []
    for pattern in args.packs:
        hits = sorted(_glob.glob(pattern))
        files.extend(hits if hits else [pattern])
    failures = 0
    for name in files:
        errs = validate_file(Path(name))
        if errs:
            failures += 1
            for err in errs:
                print(f"REJECT {err}")
        else:
            print(f"OK {name}")
    print(f"{len(files) - failures}/{len(files)} valid")
    return 0 if failures == 0 else 2


if __name__ == "__main__":
    raise SystemExit(main())
