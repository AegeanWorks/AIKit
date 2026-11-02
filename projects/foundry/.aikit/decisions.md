# foundry decisions (append-only)

## ADR-001: crypt-crawler is the first consumer, bosses the first content type
- Date: 2026-11-03. Status: accepted.
- Decision: Slice 1 targets crypt-crawler (stdlib-only, data-table precedent
  ITEM_CATALOG/GUARDIAN_TEMPLATES/BOSS_TEMPLATES, single boss spawn call
  site, existing ai_harness + validate_fairness) with boss packs (phases,
  tells, loot). dustline (JS, no bot surface), voidfarer (large surface),
  MemoryReconstruction (npm toolchain) deferred to later slices.
- Consequences: All foundry contracts are proven against one real loader
  before the loop repeats per content type and per game.

## ADR-002: "no code change" means loader-once, data-after
- Date: 2026-11-03. Status: accepted.
- Decision: Stage 2 refuted literal zero-code-change loading (no JSON
  loading in the game, hardcoded spawn sites in server.py, per-type engine
  specials). The one-time integration is crawler/foundry_packs.py (loader,
  slice-1 structural checks, skip-with-recorded-error) + a spawn hook in
  server.py. After it lands, each pack ships as a JSON file only; Stage 4
  proves this with a clean git status apart from packs/.
- Consequences: Per-pack content work is a data task. Loader/hook changes
  are versioned integration work, not content.

## ADR-003: slice-1 bosses live inside the generic is_boss envelope
- Date: 2026-11-03. Status: accepted.
- Decision: The engine applies fixed phase behavior to ANY is_boss monster
  (50%: summon <=2 skeletons + log tell; 25%: attack x1.3 + log tell).
  Slice-1 packs are constrained to exactly this envelope (thresholds 50/25,
  effects summon_skeletons/enrage); custom specials (drain/hymn-class) need
  a data-driven interpreter deferred to slice 2. Pack `tell` strings are
  required and the bot asserts a tell fires, but slice-1 engine log text
  stays canonical (known cosmetic gap: fixed log lines name Malakor).
- Consequences: New bosses get telegraphed phases with no engine edits.
  Slice 2 adds the interpreter; the schema's envelope check is the seam.

## ADR-004: replacement spawning preserves consumer invariants
- Date: 2026-11-03. Status: accepted.
- Decision: Pack spawn claims (depth 3, anchor stairs, replaces boss_lich,
  seeds [...]). The server spawns the pack boss INSTEAD of the lich for
  claimed seeds, keeping the enforced invariants (exactly 1 boss, on the
  stairs) that test_depth_three_boss_guards_the_stairs and
  validate_fairness.py assert. Duplicate (depth, seed) claims resolve by
  sorted filename, first wins, recorded as an error.
- Consequences: Baselines can overlap the consumer's own sweep seeds
  (42/777) and both suites stay green.

## ADR-005: loudness is split across the boundary
- Date: 2026-11-03. Status: accepted.
- Decision: foundry's validators/boss.py is the shipping gate (exit 2 +
  `field: reason` lines; full semantic checks incl. catalog membership and
  the one-hit cap). The game loader repeats only structural checks and
  skips bad packs with a stderr warning + recorded error (never raises),
  so one bad pack cannot brick the game; tests assert the recording.
- Consequences: Fail-fast at generation time, fail-safe at load time.

## ADR-006: the proof bot plays the shipped engine with a stated loadout
- Date: 2026-11-03. Status: accepted.
- Decision: Keystone playtest.py uses an ActionState contract crypt-crawler
  does not implement (not landed for this consumer), so the proof bot runs
  through tools/ai_harness.py (Playwright Edge, deterministic RNG) against
  the real JS engine. Python crawler/combat.py is not the live loop and is
  never the proof surface. The bot uses a documented level-5 paladin with
  equipped starters (depth-3-expected), because a naked level-1 hero is not
  the winnability question; the loadout is recorded in every report.
- Consequences: Bot clears prove the shipped game. Pre-existing harness
  selftest failures (2 omen checks, unrelated to bosses) are baselined, not
  fixed here.
