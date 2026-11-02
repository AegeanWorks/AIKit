# foundry

Shared content pipeline for the game portfolio (Dustline, crypt-crawler,
Voidfarer, MemoryReconstruction): validated schemas plus a generator that
emits per-game data packs, with the fairness validator as gatekeeper.
Slice 1 targets crypt-crawler bosses. Python stdlib only, like the engines.

## Cold start

Prerequisites: Python 3.10+ (Playwright + Edge only for `tools/bot_clear.py`;
everything else is stdlib).

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

## Layout

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
