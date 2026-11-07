# foundry

[![AIKit Integrated](https://img.shields.io/badge/AIKit-integrated-6f42c1)](https://github.com/AegeanWorks/AIKit)

Shared content pipeline for the game portfolio (Dustline, crypt-crawler,
Voidfarer, MemoryReconstruction): validated schemas plus a generator that
emits per-game data packs, with the fairness validator as gatekeeper.
Slice 1 targets crypt-crawler bosses. Python stdlib only, like the engines.

## Cold-Start Quick Reference

- **Runtime Prerequisites**: Python 3.10+ (Playwright + Edge only for `tools/bot_clear.py`; everything else is stdlib).
- **Canonical Regression Shield Gate**:
  ```bash
  python -m unittest discover tests
  ```

```powershell
cd projects/foundry
python -m unittest discover tests            # full suite, must stay green
python generators/boss.py --seeds 42,777,1337 --out packs/crypt-crawler
python validators/boss.py "packs/crypt-crawler/*.json"
python ../crypt-crawler/tools/validate_fairness.py --seeds 42,777,1337 --depths 3
python tools/bot_clear.py packs/crypt-crawler/<boss>.json --report report.json
```

Consumer side (crypt-crawler): install packs by copying the JSON files
into `projects/crypt-crawler/packs/` (data install, no code change), then
`python -m unittest discover tests` from `projects/crypt-crawler/`.

## What's Inside

```text
foundry/
├── README.md
├── .aikit/
│   └── decisions.md
├── adapters/
│   ├── __init__.py
│   └── crypt_crawler.py
├── generators/
│   ├── __init__.py
│   └── boss.py
├── schemas/
│   └── boss.schema.json
├── tests/
│   ├── test_generator.py
│   └── test_validator.py
├── tools/
│   └── bot_clear.py
├── validators/
│   ├── __init__.py
│   └── boss.py
└── packs/
    └── crypt-crawler/
        ├── boss_ashen_warden_s42.json
        ├── boss_pale_warden_s1337.json
        └── boss_ruin_vesper_s777.json
```

- `schemas/boss.schema.json` — canonical boss format (slice-1 envelope).
- `validators/boss.py` — gatekeeper: every pack validates, failures name
  `field: reason`.
- `generators/boss.py` — seeded, deterministic, valid-by-construction.
- `adapters/crypt_crawler.py` — consumer facts (catalog ids, target, pack
  major). The reverse mapping lives game-side in
  `crawler/foundry_packs.py`; the pair is the versioned adapter.
- `packs/crypt-crawler/` — baselined generated packs (seed set 42/777/1337).
- `tools/bot_clear.py` — bot-clear proof against the shipped engine.
- `.aikit/decisions.md` — ADRs, append-only.

## Gates (never lowered)

1. Suite green (`python -m unittest discover tests`).
2. Every pack validates before it ships; invalid packs fail with field+reason.
3. Fairness: no unwinnable seed, telegraphed patterns, economy in bounds —
   proven by bot runs (ai_harness Playwright; Keystone once it lands).
