"""Generator tests: determinism, validity, uniqueness, catalog honesty."""

from __future__ import annotations

import sys
import unittest
from pathlib import Path

FOUNDRY_ROOT = Path(__file__).resolve().parent.parent
if str(FOUNDRY_ROOT) not in sys.path:
    sys.path.insert(0, str(FOUNDRY_ROOT))

from adapters.crypt_crawler import ITEM_IDS  # noqa: E402
from generators.boss import BASELINE_SEEDS, generate, pack_bytes  # noqa: E402
from validators.boss import max_theoretical_hit, validate  # noqa: E402


class TestGenerator(unittest.TestCase):
    def test_deterministic_per_seed(self):
        self.assertEqual(generate(42), generate(42))
        self.assertEqual(pack_bytes(generate(777)), pack_bytes(generate(777)))

    def test_distinct_seeds_distinct_packs(self):
        self.assertNotEqual(generate(42), generate(777))

    def test_baseline_seeds_valid(self):
        for seed in BASELINE_SEEDS:
            with self.subTest(seed=seed):
                self.assertEqual(validate(generate(seed)), [])

    def test_wide_seed_range_valid(self):
        for seed in range(1, 51):
            with self.subTest(seed=seed):
                self.assertEqual(validate(generate(seed)), [])

    def test_boss_ids_unique_over_range(self):
        ids = [generate(s)["boss_id"] for s in range(1, 201)]
        self.assertEqual(len(ids), len(set(ids)), "boss_id collision in 1..200")

    def test_loot_resolves_in_catalog(self):
        for seed in list(BASELINE_SEEDS) + list(range(1, 21)):
            with self.subTest(seed=seed):
                item = generate(seed)["loot"]["item_id"]
                self.assertIn(item, ITEM_IDS)

    def test_no_one_shot_over_range(self):
        from validators.boss import ONE_HIT_CAP

        for seed in range(1, 201):
            with self.subTest(seed=seed):
                atk = generate(seed)["stats"]["attack"]
                self.assertLessEqual(max_theoretical_hit(atk), ONE_HIT_CAP)

    def test_empty_loot_pool_fails_loud(self):
        import generators.boss as boss_mod

        old = boss_mod.ITEM_IDS
        boss_mod.ITEM_IDS = frozenset()
        try:
            with self.assertRaises(ValueError):
                generate(42)
        finally:
            boss_mod.ITEM_IDS = old

    def test_spawn_claims_own_seed(self):
        for seed in BASELINE_SEEDS:
            with self.subTest(seed=seed):
                pack = generate(seed)
                self.assertEqual(pack["spawn"]["seeds"], [seed])
                self.assertEqual(pack["spawn"]["replaces"], "boss_lich")


if __name__ == "__main__":
    unittest.main()
