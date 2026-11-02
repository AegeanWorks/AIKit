"""Validator tests: valid packs pass, broken packs fail with field + reason.

Every reject fixture is deliberate: each one breaks exactly one rule so
a regression names the rule it broke.
"""

from __future__ import annotations

import copy
import sys
import unittest
from pathlib import Path

FOUNDRY_ROOT = Path(__file__).resolve().parent.parent
if str(FOUNDRY_ROOT) not in sys.path:
    sys.path.insert(0, str(FOUNDRY_ROOT))

from validators.boss import validate  # noqa: E402


def good_pack() -> dict:
    return {
        "pack_version": "1.0",
        "target_game": "crypt-crawler",
        "boss_id": "boss_gloom_herald",
        "name": "Gloom Herald",
        "stats": {
            "hp": 120,
            "attack": 12,
            "defense": 4,
            "xp_reward": 160,
            "gold_reward": 120,
        },
        "phases": [
            {
                "threshold_pct": 50,
                "effect": "summon_skeletons",
                "tell": "The Herald splits the dark and calls its risen choir.",
            },
            {
                "threshold_pct": 25,
                "effect": "enrage",
                "tell": "The Herald burns with voted wrath. End it fast.",
            },
        ],
        "loot": {"item_id": "amulet_bloodstone"},
        "spawn": {
            "depth": 3,
            "anchor": "stairs",
            "replaces": "boss_lich",
            "seeds": [42],
        },
    }


class TestValidatorAccepts(unittest.TestCase):
    def test_good_pack_is_valid(self):
        self.assertEqual(validate(good_pack()), [])


class TestValidatorRejects(unittest.TestCase):
    def check(self, mutate, field_prefix):
        pack = mutate(copy.deepcopy(good_pack()))
        errors = validate(pack)
        self.assertTrue(errors, f"expected rejection for {field_prefix}")
        self.assertTrue(
            any(e.startswith(field_prefix) for e in errors),
            f"no error names {field_prefix!r}: {errors}",
        )
        return errors

    def test_rejects_unknown_top_field(self):
        self.check(lambda p: p.update(difficulty_curve={}) or p, "pack:")

    def test_rejects_missing_field(self):
        def drop(p):
            del p["loot"]
            return p

        self.check(drop, "loot:")

    def test_rejects_bad_pack_version(self):
        self.check(lambda p: p.update(pack_version="2.0") or p, "pack_version:")

    def test_rejects_wrong_game(self):
        self.check(lambda p: p.update(target_game="dustline") or p, "target_game:")

    def test_rejects_bad_boss_id(self):
        self.check(lambda p: p.update(boss_id="Lich King!") or p, "boss_id:")

    def test_rejects_empty_name(self):
        self.check(lambda p: p.update(name="") or p, "name:")

    def test_rejects_out_of_band_stat(self):
        def mutate(p):
            p["stats"]["attack"] = 99
            return p

        self.check(mutate, "stats.attack:")

    def test_rejects_bool_stat(self):
        def mutate(p):
            p["stats"]["hp"] = True
            return p

        self.check(mutate, "stats.hp:")

    def test_rejects_one_shot_attack(self):
        # The top of the band (attack 25 -> hit 46) fits under the cap, so
        # the band is the cap's enforcement for shippable packs. An
        # over-band attack must trip BOTH the band and the one-shot rule,
        # proving the cap path itself fires with the field and the reason.
        def mutate(p):
            p["stats"]["attack"] = 40
            return p

        errors = self.check(mutate, "stats.attack:")
        self.assertTrue(
            any("one-shot risk" in e for e in errors),
            f"cap did not fire: {errors}",
        )

    def test_cap_math_matches_schema_doc(self):
        from validators.boss import ONE_HIT_CAP, max_theoretical_hit

        self.assertEqual(ONE_HIT_CAP, 53)
        self.assertEqual(max_theoretical_hit(13), 25)  # boss_lich reference
        self.assertEqual(max_theoretical_hit(25), 46)  # band top fits

    def test_rejects_wrong_phase_count(self):
        def mutate(p):
            p["phases"] = p["phases"][:1]
            return p

        self.check(mutate, "phases:")

    def test_rejects_off_envelope_threshold(self):
        def mutate(p):
            p["phases"][0]["threshold_pct"] = 60
            return p

        self.check(mutate, "phases[0].threshold_pct:")

    def test_rejects_custom_effect(self):
        def mutate(p):
            p["phases"][1]["effect"] = "soul_drain"
            return p

        self.check(mutate, "phases[1].effect:")

    def test_rejects_empty_tell(self):
        def mutate(p):
            p["phases"][0]["tell"] = ""
            return p

        self.check(mutate, "phases[0].tell:")

    def test_rejects_unknown_loot(self):
        def mutate(p):
            p["loot"]["item_id"] = "sword_nevermade"
            return p

        self.check(mutate, "loot.item_id:")

    def test_rejects_wrong_depth(self):
        def mutate(p):
            p["spawn"]["depth"] = 2
            return p

        self.check(mutate, "spawn.depth:")

    def test_rejects_vault_anchor(self):
        def mutate(p):
            p["spawn"]["anchor"] = "vault"
            return p

        self.check(mutate, "spawn.anchor:")

    def test_rejects_empty_seeds(self):
        def mutate(p):
            p["spawn"]["seeds"] = []
            return p

        self.check(mutate, "spawn.seeds:")

    def test_rejects_non_object_pack(self):
        self.assertEqual(validate([]), ["pack: must be a JSON object"])

    def test_rejects_deliberately_unfair_generated_pack(self):
        # End to end: take a generator-valid pack and make it unfair in
        # three independent ways. Each must fail loudly with field+reason.
        from generators.boss import generate

        pack = generate(42)
        pack["stats"]["attack"] = 40  # one-shot: max hit 75 > cap 53
        pack["loot"]["item_id"] = "sword_nevermade"  # outside the economy
        pack["phases"][0]["threshold_pct"] = 60  # outside the envelope
        errors = validate(pack)
        joined = "\n".join(errors)
        self.assertIn("stats.attack:", joined)
        self.assertIn("one-shot risk", joined)
        self.assertIn("loot.item_id:", joined)
        self.assertIn("phases[0].threshold_pct:", joined)


if __name__ == "__main__":
    unittest.main()
