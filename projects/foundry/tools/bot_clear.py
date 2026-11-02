"""Bot-clear proof: a reference policy beats a generated boss in the real game.

Drives the shipped crypt-crawler engine through tools/ai_harness.py
(Playwright headless Edge, deterministic Math.random) so the proof
covers the game as shipped, not a Python copy. The policy is
deliberately simple -- teleport beside the boss, bump-attack, heal at
50%, potion in extremis -- because the gate is winnability, not skill.

A clear is recorded only when ALL of these hold:
  won             the pack boss died and the paladin lived, <= MAX_TURNS
  summon_seen     skeleton count rose above the escort baseline (50% phase)
  enrage_seen     boss attack rose above its pack base (25% phase)
  tells_seen      both phase log tells fired
  clean           no page/console errors during the run

Usage:
    python tools/bot_clear.py packs/crypt-crawler/boss_X.json --report out.json
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any, Dict, List, Optional

FOUNDRY_ROOT = Path(__file__).resolve().parent.parent
if str(FOUNDRY_ROOT) not in sys.path:
    sys.path.insert(0, str(FOUNDRY_ROOT))

from adapters.crypt_crawler import GAME_ROOT  # noqa: E402

if str(GAME_ROOT) not in sys.path:
    sys.path.insert(0, str(GAME_ROOT))

from tools.ai_harness import Harness  # noqa: E402
from validators.boss import validate  # noqa: E402

MAX_TURNS = 60
HEAL_SLOT = 4
HEAL_AT = 0.5

# Reference loadout: the depth-3-expected paladin the fairness predicate
# names. A naked level-1 hero teleported to depth 3 is not the gate; an
# appropriately-leveled, starter-equipped hero is. Applied transparently
# via the engine's own fields and recorded in the report.
# Level-ups: +12 max HP, +6 max mana, +2 attack, +1 defense per level.
SETUP_LEVEL = 5
SETUP_JS = """() => {
  const e = window.gameEngine; const p = e.player;
  const gains = %d;
  p.level = 1 + gains;
  p.max_hp = 65 + 12 * gains; p.hp = p.max_hp;
  p.max_mana = 30 + 6 * gains; p.mana = p.max_mana;
  p.attack = 8 + 2 * gains; p.defense = 4 + 1 * gains;
  p.xp = 0;
  return { level: p.level, attack: p.attack, defense: p.defense,
           max_hp: p.max_hp, max_mana: p.max_mana };
}""" % (SETUP_LEVEL - 1)

GEAR_WANT = ("Forged Iron Sword", "Hardened Leather Armor")


def _sign(value: int) -> int:
    return (value > 0) - (value < 0)


def _boss(monsters: List[Dict[str, Any]], boss_id: str) -> Optional[Dict[str, Any]]:
    for monster in monsters:
        if monster["type"] == boss_id:
            return monster
    return None


def clear_pack(pack_path: Path) -> Dict[str, Any]:
    pack = json.loads(pack_path.read_text(encoding="utf-8"))
    val_errors = validate(pack)
    boss_id = pack["boss_id"]
    seed = pack["spawn"]["seeds"][0]
    base_attack = pack["stats"]["attack"]
    report: Dict[str, Any] = {
        "pack": pack_path.name,
        "boss_id": boss_id,
        "seed": seed,
        "valid": not val_errors,
        "validation_errors": val_errors,
        "turns": 0,
        "won": False,
        "summon_seen": False,
        "enrage_seen": False,
        "tells_seen": {"summon": False, "enrage": False},
        "log_tail": [],
        "errors": [],
    }
    if val_errors:
        report["errors"].append("pack failed validation; bot did not run")
        return report

    full_log: List[str] = []
    with Harness(headless=True) as harness:
        page = harness.open_page(seed=seed, depth=3, hero_class="paladin")
        report["loadout"] = page.evaluate(SETUP_JS)
        # Equip the starter kit through the real inventory path.
        for _ in range(4):
            state = Harness.state(page)
            equipped = {v for v in state["player"]["equipped"].values() if v}
            if all(g in equipped for g in GEAR_WANT):
                break
            idx = next(
                (
                    i
                    for i, item in enumerate(state["player"]["inventory"])
                    if item in GEAR_WANT and item not in equipped
                ),
                None,
            )
            if idx is None:
                break
            state = Harness.apply(page, {"action": "use_item", "index": idx})
        state = Harness.state(page)
        report["loadout"]["equipped"] = state["player"]["equipped"]
        boss = _boss(state["monsters"], boss_id)
        if boss is None:
            report["errors"].append("pack boss not present on depth 3")
            return report
        base_skeletons = sum(1 for m in state["monsters"] if m["type"] == "skeleton")

        placed = False
        for dx, dy in ((0, -1), (0, 1), (-1, 0), (1, 0), (1, 1), (-1, -1)):
            try:
                state = Harness.apply(
                    page, {"action": "teleport", "x": boss["x"] + dx, "y": boss["y"] + dy}
                )
                placed = True
                break
            except Exception:
                continue
        if not placed:
            report["errors"].append("no walkable tile beside the boss")
            return report

        for turn in range(1, MAX_TURNS + 1):
            report["turns"] = turn
            player = state["player"]
            boss = _boss(state["monsters"], boss_id)
            if boss is None:
                report["won"] = state["player"]["hp"] > 0 and not state["gameOver"]
                break
            if state["gameOver"]:
                break
            skeletons = sum(1 for m in state["monsters"] if m["type"] == "skeleton")
            if skeletons > base_skeletons:
                report["summon_seen"] = True
            if boss["attack"] > base_attack:
                report["enrage_seen"] = True
            for line in state.get("log", []):
                if line not in full_log:
                    full_log.append(line)
                if "raises" in line and "skeleton" in line:
                    report["tells_seen"]["summon"] = True
                if "cornered god" in line:
                    report["tells_seen"]["enrage"] = True
            max_hp = player["max_hp"]
            has_potion = any("Elixir" in i or "Potion" in i for i in player["inventory"])
            try:
                if player["hp"] <= max_hp * HEAL_AT and player["mana"] >= 8:
                    state = Harness.apply(page, {"action": "ability", "slot": HEAL_SLOT})
                elif player["hp"] <= max_hp * 0.3 and has_potion:
                    state = Harness.apply(page, {"action": "potion"})
                else:
                    boss = _boss(state["monsters"], boss_id) or boss
                    state = Harness.apply(
                        page,
                        {
                            "action": "move",
                            "dx": _sign(boss["x"] - player["x"]),
                            "dy": _sign(boss["y"] - player["y"]),
                        },
                    )
            except Exception as exc:  # a failed action still costs attention, not the run
                report["errors"].append(f"turn {turn}: {exc}")
                try:
                    state = Harness.apply(page, {"action": "wait"})
                except Exception as exc2:
                    report["errors"].append(f"turn {turn} wait failed: {exc2}")
                    break
        report["log_tail"] = full_log[-12:]
        report["errors"].extend(harness.errors)
        boss = _boss(state["monsters"], boss_id)
        if boss is None and state["player"]["hp"] > 0:
            report["won"] = True

    report["fair"] = bool(
        report["won"]
        and report["summon_seen"]
        and report["enrage_seen"]
        and all(report["tells_seen"].values())
        and not report["errors"]
    )
    return report


def main(argv: List[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description="Bot-clear a generated boss pack.")
    ap.add_argument("pack", help="Pack JSON file")
    ap.add_argument("--report", default=None, help="Write JSON report here")
    args = ap.parse_args(argv)
    report = clear_pack(Path(args.pack))
    print(
        f"pack={report['boss_id']} seed={report['seed']} "
        f"turns={report['turns']} won={report['won']} "
        f"summon={report['summon_seen']} enrage={report['enrage_seen']} "
        f"tells={report['tells_seen']} fair={report.get('fair')}"
    )
    for err in report["errors"]:
        print(f"ERROR {err}")
    if args.report:
        Path(args.report).write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
        print(f"WROTE {args.report}")
    return 0 if report.get("fair") else 1


if __name__ == "__main__":
    raise SystemExit(main())
