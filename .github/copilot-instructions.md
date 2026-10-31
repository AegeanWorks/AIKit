# Copilot Instructions (Tier 1)

> Generated from `GUIDELINES.md`; do not edit.
> Runbook: `.agents/skills/aikit/SKILL.md` for test, sync, gate and recovery commands.
> Capsules bind; `GUIDELINES.md` wins on conflict. On a contract change, failure or ambiguity, read the `### PRINCIPLE-NNN:` section of each principle `sync_principles.py --involved` lists; never the whole file unless asked.

## Core Principles
- PRINCIPLE-000 Meta-Principle Integrity & Mutual Alignment: Every rule binds; conflicts follow R6 order; rule edits re-check every citing principle; gaming a gate is a violation; quality doubts go to the user.
- PRINCIPLE-001 Progressive Rule Disclosure & Governance Frugality: Pre-Flight checklist before the first Track C edit; Post-Flight checklist before any Track B or C commit; report only failed items (R8).
- PRINCIPLE-002 Lifecycle-Aligned Instruction Ordering & Attentional Priming: Track via `disruption_recovery.py --track` (A none, B docs/comments but not rule files, C rest); urgency alone never skips P018 gates (R5).
- PRINCIPLE-003 Empirical Grounding & Anti-Hallucination Invariant: Read-before-write slice freshness; `git grep -w -e` call-site check; deps only if declared; platform parity; ask on intent ambiguity; strict AST syntax gate.
- PRINCIPLE-004 Attentional Drift Prevention & Compaction Resilience: Plan = latest `[1/` Phase 2 `--desc` in `task_ledger.json`; cold start `--resume`; never re-ask recorded answers; ADR before commit; reads/output <=100 lines.
- PRINCIPLE-005 AI Cold-Start Readiness & Living Documentation: README <=30k chars: prerequisites, test command, tree; user-visible changes update it same commit; `update_knowledge_base.py --check` gates it.
- PRINCIPLE-006 Incremental Progress Checkpointing & Disruption Recovery: Commit `[milestone N/M]` once Phase 4 passes under PRINCIPLE-018 R1; failing work uncommitted via `--checkpoint`; `--complete`/`--reset` before switching tasks; `--clean` stale `.tmp_*`; ledger writes name `--agent`; another agent's task needs `--take-over`.
- PRINCIPLE-007 Pre-flight Impact & Quality Checklist: Track C first plan checkpoint carries --why --benefits --risks (contract, dependency, concurrency, state) --mitigation; no TODO or stub; no change outside the plan.
- PRINCIPLE-008 Hierarchical Problem & Task Decomposition: Plan of M<=6 milestones (more: split into tasks), built bottom-up, each passing Phase 4 alone; re-plan = new `[1/M']` checkpoint; sub-agents never write the ledger.
- PRINCIPLE-009 Modularity & Pluggable Architecture: Every module: no junk-drawer name, roles of 1-5 methods, no import cycle (gated). At a pluggable boundary: 4 layers, registry lookup, constructor DI with default, frozen DTOs.
- PRINCIPLE-010 Performance & Resource Optimization: Stream uncontrolled input; threads only for steps >=200ms; timeout= on subprocess, with on open(); one fsync per file; `--help` <250ms; unit <=20ms, integ <=500ms/test.
- PRINCIPLE-011 Zero-Friction Onboarding & Instant Usability: Only declared deps; creates its dirs; prompts only with `--interactive`; no `os.environ[...]` reads; exit 0/1/2; errors give `Why:`/`Fix:`; demo <10s; other software: its `aikit.py` project is the workspace (R8).
- PRINCIPLE-012 Token Frugality & Lean Code Architecture: LLM code: <=16k-char payloads, static prefix first, schema-checked replies, 429 backoff, step caps; agent: diff -U3, search <=50 hits, relative paths.
- PRINCIPLE-013 Crash Resilience, State Atomicity & Power-Loss Recovery: State files: >=10MB free, temp + fsync + os.replace (5 tries) + dir fsync, .bak, advisory locking 3s/30s stale, corrupt -> quarantine/.bak/migrate. Generated: temp + fsync + replace.
- PRINCIPLE-014 Automated Test Verification & Continuous Test Coverage: 100% test pass gate; behaviour change = failing-first test; weakening a test needs user approval + ADR naming it; unit <=20ms/test, no spawns/sleeps; integ <=500ms/test; tempdir + addCleanup; `scripts/check_reachability.py`.
- PRINCIPLE-015 Universal Operational Dogfooding & Chaos Verification: Domain-specific interactive dogfooding via `scripts/dogfood.py` as a commit gate; golden path + chaos perturbation; non-interactive stdin parity; portable RAII process tree teardown; ephemeral safety jail; terse reporting (<=15 lines).
- PRINCIPLE-016 AI Knowledge Base & Continuous Synchronization: Canonical `knowledge/` sync; atomic code-and-doc pairing; monotonic append-only ADR register; strict AST syntax validation; link integrity shield; `scripts/update_knowledge_base.py`.
- PRINCIPLE-017 Living Principles System & Automated Synchronization: Rule sync (`scripts/sync_principles.py`); context budget check; schema compliance; freshness test gate; Tier 1B domain rules (<=1,200 chars).
- PRINCIPLE-018 Automatic Git Workflow: Conventional commits (`--validate-commit`) + adaptive push, never forced, only if authorized (R1); explicit staging (no `git add .`); pre-commit triad (tests/gates/diff); commit verified alone pre-push (R7); non-destructive recoil.
- PRINCIPLE-019 Secret & Sensitive Data Hygiene: Zero credentials in tracked files, logs or ledgers; secrets via env/secret store; `.gitignore` credential baseline; `scripts/check_secrets.py` scans staged diffs + ledger; redacted diagnostics; rotate, never revert.
