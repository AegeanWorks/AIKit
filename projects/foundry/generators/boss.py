"""Foundry boss generator: seeded, deterministic, valid-by-construction.

Stdlib only. generate(seed) is pure: the same seed always yields the
same pack dict, and write_pack() serializes canonically (sorted keys,
indent 2, trailing newline) so regeneration is byte-identical. Every
emitted pack passes validators.boss.validate before it is returned;
a generator bug that produces an invalid pack raises instead of
shipping it.
"""

from __future__ import annotations

import argparse
import json
import random
import sys
from pathlib import Path
from typing import Dict, List

FOUNDRY_ROOT = Path(__file__).resolve().parent.parent
if str(FOUNDRY_ROOT) not in sys.path:
    sys.path.insert(0, str(FOUNDRY_ROOT))

from adapters.crypt_crawler import ITEM_IDS  # noqa: E402
from validators.boss import validate  # noqa: E402

PACK_VERSION = "1.0"

# Slice-1 seed set: the baselined packs. 42/777 overlap the consumer's
# own sweep seeds on purpose, proving replacement packs keep the
# 1-boss-on-stairs invariant the consumer suite enforces.
BASELINE_SEEDS = (42, 777, 1337)

ARCHETYPES = (
    # name, hp band, attack band, defense band
    ("bruiser", (120, 170), (12, 17), (4, 7)),
    ("summoner", (80, 110), (9, 12), (2, 4)),
    ("tyrant", (150, 200), (15, 20), (5, 8)),
)

# Curated loot: real ITEM_CATALOG ids with end-of-depth-3 desirability.
LOOT_POOL = (
    "tome_pyromancy",
    "hammer_thunder",
    "cloak_ethereal",
    "amulet_bloodstone",
    "ring_shadow",
    "boots_shadowstep",
)

NAME_ADJS = (
    "gloom", "marrow", "hollow", "ashen", "ruin", "wither",
    "obsidian", "sable", "grim", "pale",
)
NAME_NOUNS = (
    "herald", "cantor", "warden", "matron", "legate", "vesper",
    "requiem", "psalm", "warden", "elegy",
)

TELLS = {
    "summon_skeletons": (
        "{name} splits the dark and calls its risen servants.",
        "{name} tears the floor open; the dead climb out.",
    ),
    "enrage": (
        "{name} burns with ending wrath. Finish it fast.",
        "{name} fights like a cornered god now.",
    ),
}


def _clamp(value: int, lo: int, hi: int) -> int:
    return max(lo, min(hi, value))


def generate(seed: int) -> Dict:
    """Build the canonical boss pack for a seed (pure, deterministic)."""
    rng = random.Random(seed)
    kind, hp_band, atk_band, def_band = rng.choice(ARCHETYPES)
    hp = rng.randint(*hp_band)
    attack = rng.randint(*atk_band)
    defense = rng.randint(*def_band)
    xp_reward = _clamp(hp // 2 + attack * 5, 20, 400)
    gold_reward = _clamp(hp // 3 + attack * 4, 10, 300)
    loot_id = rng.choice([i for i in LOOT_POOL if i in ITEM_IDS]) or "amulet_bloodstone"
    adj = rng.choice(NAME_ADJS)
    noun = rng.choice(NAME_NOUNS)
    # Seed suffix: guarantees registry uniqueness and traces a pack to
    # the seed that produced it. Still matches ^boss_[a-z0-9_]{2,27}$.
    boss_id = f"boss_{adj}_{noun}_s{seed}"
    name = f"{adj.title()} {noun.title()}"
    _ = kind  # archetype shapes the bands above; behavior stays in the envelope
    pack = {
        "pack_version": PACK_VERSION,
        "target_game": "crypt-crawler",
        "boss_id": boss_id,
        "name": name,
        "stats": {
            "hp": hp,
            "attack": attack,
            "defense": defense,
            "xp_reward": xp_reward,
            "gold_reward": gold_reward,
        },
        "phases": [
            {
                "threshold_pct": 50,
                "effect": "summon_skeletons",
                "tell": rng.choice(TELLS["summon_skeletons"]).format(name=name),
            },
            {
                "threshold_pct": 25,
                "effect": "enrage",
                "tell": rng.choice(TELLS["enrage"]).format(name=name),
            },
        ],
        "loot": {"item_id": loot_id},
        "spawn": {
            "depth": 3,
            "anchor": "stairs",
            "replaces": "boss_lich",
            "seeds": [seed],
        },
    }
    errors = validate(pack)
    if errors:
        raise ValueError(f"generator produced invalid pack for seed {seed}: {errors}")
    return pack


def pack_bytes(pack: Dict) -> bytes:
    return (json.dumps(pack, sort_keys=True, indent=2) + "\n").encode("utf-8")


def write_pack(seed: int, out_dir: Path) -> Path:
    pack = generate(seed)
    out_dir.mkdir(parents=True, exist_ok=True)
    path = out_dir / f"{pack['boss_id']}.json"
    path.write_bytes(pack_bytes(pack))
    return path


def main(argv: List[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description="Generate foundry boss packs.")
    ap.add_argument("--seeds", default=",".join(map(str, BASELINE_SEEDS)))
    ap.add_argument("--out", default=str(FOUNDRY_ROOT / "packs" / "crypt-crawler"))
    args = ap.parse_args(argv)
    seeds = [int(s) for s in args.seeds.split(",") if s.strip()]
    out_dir = Path(args.out)
    for seed in seeds:
        print(f"WROTE {write_pack(seed, out_dir)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
