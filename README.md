# 🤖 Universal AI Principles & Agent Operating System (Portable Kit)

<!-- aegean:media:start -->
<p align="center"><img src="assets/social-preview.png" alt="AIKit social preview" width="100%"></p>
<p align="center"><a href="LICENSE"><img src="https://img.shields.io/badge/license-AL--1.1-2f9e44" alt="License"></a> <a href="https://www.python.org/"><img src="https://img.shields.io/badge/python-3.13%2B-3776AB" alt="Python 3.13+"></a></p>
*The banner is AI-generated and illustrative, not a literal feature map.*
<!-- aegean:media:end -->


> **AI governance, architecture principles & disruption (incl. power-cut) recovery for any software project**, extracted from production development, with documentation and regression-shielded workflows.
>
> **Name note:** this AIKit (governance/delivery gates, stdlib-only, AL-1.1/ACL-1.0) is not `goaikit/aikit`, `matakartal/aikit-runtime`, `NativeMindNet/aikit` or `ai-kit-python`.

---

## ⚡ 30-Second Cold-Start Quick Reference

> **Orientation Contract**: verified commands and prerequisites below.

- **Runtime Prerequisites**: Python 3.13+ (standard library only; no pip dependencies), `git`, and `gh` for GitHub work.
- **Canonical Regression Shield Gate**:
  ```bash
  python -m unittest discover tests
  ```
  *(100% test pass required before staging or committing).*

> **Standing policy lives in `knowledge/decisions.md`** (append-only ADR register, linked from `knowledge/INDEX.md`): push authorization (ADR-338) and the analyze-first mandate (ADR-339) bind every agent working here, foreign harnesses included. Search it before asking the operator; it outranks chat history.

### 🛠️ Core Operational Command Matrix
| Operational Role| Canonical Command| Verification Gate|
|---|---|---|
| **Manage Projects**| `python aikit.py <cmd>`| `new`, `attach`, `list`, `status`, `check`, `fix` (ADR-119..124)|
| **Audit & Repair History**| `python aikit.py reforge <cmd>`| `start`, `audit`, `review`, `analyze`, `fix`, `run`, `stop`, `resume`, `settings`, `runs`, `status`, `report`; windows, Python AST (ADR-230, ADR-232, ADR-249, ADR-290)|
| **Route Ideas & Reviews**| `python aikit.py idea-catcher <cmd>`| `validate`, `render`, `status`, `ideas`, `tag`, `history`, `review-idea`, `reviews`, `review-start/finish`, `revalidate`, `audit-claims`, `concepts`; a second deferral blocks an idea permanently (ADR-246, ADR-252, ADR-286)|
| **Project Tags & Media**| `python aikit.py <cmd>`| `ui-id`, `topics --brief/--from-file`, `media init/capture/review/apply/audit`; AI-chosen tags, reviewed logos and commit-stamped screenshots (ADR-233..236)|
| **Run Regression Suite**| `python scripts/check_test_budgets.py`| Both tiers pass; per-test average <=20ms unit, <=1000ms integration|
| **Run One Tier**| `python -m unittest tests.test_kit` / `python -m unittest tests.test_integration`| Isolates a failing tier|
| **Synchronize IDE Rules**| `python scripts/sync_principles.py`| <=1,750 est. tokens/target incl. a reserved 300-token Tier 1B|
| **Verify Rule Freshness**| `python scripts/sync_principles.py --check`| Read-only; exits 1 on rule drift, or when a principle changed since the last commit lacks an ADR naming its `--citing` set (PRINCIPLE-000 R3)|
| **Find Principles to Read**| `python scripts/sync_principles.py --involved <paths/commands/output>`| Same answer for every agent (PRINCIPLE-001 R3)|
| **Cross-Principle Check Set**| `python scripts/sync_principles.py --citing <PRINCIPLE-NNN>`| Principles a rule change must be checked against (PRINCIPLE-000 R3)|
| **Update AST & Knowledge**| `python scripts/update_knowledge_base.py`| Rewrites the codebase map, then runs every audit of `--check` below; exits 1 on a syntax error (Python 3.13 grammar) or any audit failure|
| **Codebase Digest**| `python scripts/update_knowledge_base.py --digest`| Read-only; one line per module in at most 100 lines, shared code first; a cut is stated|
| **Verify AST Map Freshness**| `python scripts/update_knowledge_base.py --check`| Read-only; exits 1 on a stale codebase map, README drift (PRINCIPLE-005), a `python <path>.py` naming a missing file, an ADR ID out of order, unfinished code (PRINCIPLE-007 R3) or a code-structure violation (PRINCIPLE-009 to PRINCIPLE-011)|
| **Classify Lifecycle Track**| `python scripts/disruption_recovery.py --track`| Prints Track A/B/C of current changes (PRINCIPLE-002 R3)|
| **Inspect State Machines**| `python scripts/state_machines.py --list`| Read-only declarations: `--json`, `--machine`, `--from/--to`, `--check-status`; 19 machines, one source (ADR-388, ADR-389)|
| **Audit Disruption Recovery**| `python scripts/disruption_recovery.py --audit`| Clean status check; detects surviving uncommitted files|
| **Resume Interrupted Task**| `python scripts/disruption_recovery.py --resume`| Cold-start command: every `--audit` finding, then the interrupted task, its plan and resumption phase|
| **Record Task Checkpoint**| `python scripts/disruption_recovery.py --checkpoint <task_id> --phase-num <1-5> --desc <text>`| Appends a checkpoint (PRINCIPLE-002 R4); exits 2 when a task's first plan lacks `--why --benefits --risks --mitigation`, and warns when a task reaches Phase 3 with none (PRINCIPLE-007 R1, R6); exits 1 on credential-shaped text, or records `[REDACTED]` with `--redact` (PRINCIPLE-019 R3); `--handoff "next: ...; state: ...; failed: ...; open: ..."` records the packet `--resume` prints (PRINCIPLE-004 R2); `--agent <name>` and `--take-over` per PRINCIPLE-006 R7|
| **Complete Task Ledger**| `python scripts/disruption_recovery.py --complete <task_id>`| Marks the active task completed in `.agents/task_ledger.json`; exits 1, changing nothing, if `<task_id>` is not the active task|
| **Reset Active Task**| `python scripts/disruption_recovery.py --reset [reason]`| Abandons/clears in-progress task in ledger|
| **Purge Temp Buffers**| `python scripts/disruption_recovery.py --clean`| Deletes orphaned `*.tmp_*` buffers older than 60 s; younger ones may be a write in progress|
| **Secret Scan Gate**| `python scripts/check_secrets.py --staged\|--commits <range> [--workspace <project>]`| Exits 1 on a credential pattern in the staged diff or agent memory, or when any surface could not be scanned (PRINCIPLE-019)|
| **Verify the Commit Itself**| `python scripts/verify_commit.py`| Runs every gate against the commit alone in a throwaway worktree; exits 1 when the commit holds less than the tree it was tested in (PRINCIPLE-018 R7); warns on a file cut below half its size unless the message says `shrink-ok: <reason>`|
| **Reachability Shield**| `python scripts/check_reachability.py`| No unwired capability or phantom state key (PRINCIPLE-014 R7)|
| **Operational Dogfood Gate**| `python scripts/dogfood.py`| 5/5 tracks pass; zero host mutation (PRINCIPLE-015)|
| **Discover Any CLI**| `python scripts/<script>.py --help`| Prints usage and exits `0` in <1000ms as a fresh process, writing nothing|
| **Sandbox the Ledger CLI**| `python scripts/disruption_recovery.py --workspace <dir> --audit`| Operates on `<dir>/.agents/`, never the repo ledger|

**Universal CLI contract (PRINCIPLE-011, PRINCIPLE-015).** Every CLI: `--help`/`-h` prints usage, writes nothing, exits `0`; exit `0` success, `1` operational failure, `2` misuse (an unknown flag is refused, never the default); failures print What → Why → Fix on stderr, never a traceback.

---

## 📦 What's Inside

```text
portable_agent_kit/
├── README.md                     <- This Integration & Setup Guide
├── LICENSE                       <- Aegean License 1.1 (AL-1.1)
├── COMMERCIAL.md                 <- Paid commercial terms (ACL-1.0)
├── licenses/                     <- Pinned Aegean license texts + PIN.json
├── aikit.py                      <- Project CLI
├── assets/                       <- Root brand assets
│   ├── logo.svg
│   ├── logo.png
│   ├── social-preview.svg
│   └── social-preview.png
├── reforge.py                    <- Aegean Reforge CLI entry point (and `aikit.py reforge`)
├── reforge/                      <- host-reviewed Git history auditor & safe repair engine
├── idea_catcher.py               <- Idea Catcher CLI entry point (and `aikit.py idea-catcher`)
├── idea_catcher/                 <- idea register and matrix renderer
│   ├── __init__.py
│   ├── __main__.py
│   ├── registry.py
│   ├── auto_register.py          <- Automatic idea registration from commit references
│   ├── claim_audit.py
│   ├── concept_map.py
│   ├── upstream_check.py
│   └── version.py
├── .gitignore                    <- Credential & local-state baseline (PRINCIPLE-019 R3)
├── AGENTS.md                     <- Generated Tier 1 capsules (AGENTS.md-convention hosts)
├── GUIDELINES.md                 <- Source of truth: every principle and rule (Tier 2)
├── GEMINI.md                     <- Google Gemini & Antigravity IDE rules
├── CLAUDE.md                     <- Claude Code configuration
├── .cursorrules                  <- Cursor IDE instructions
├── .windsurfrules                <- Codeium Windsurf IDE instructions
├── .clinerules                   <- Cline / Roo Code IDE instructions
├── .github/
│   ├── copilot-instructions.md   <- GitHub Copilot instructions
│   └── workflows/
│       └── ci.yml                <- CI gate (both tiers + freshness)
├── .claude/
│   ├── agents/                   <- Claude sub-agents (generated)
│   ├── settings.json             <- no agent may edit a task ledger
│   └── skills/
│       └── aikit/
│           ├── SKILL.md          <- Claude Code runbook (native skill)
│           ├── projects.md       <- Project command matrix (read on demand)
│           └── delegation.md     <- Sub-agent delegation (read on demand)
├── .agents/
│   ├── rules/
│   │   ├── principles.md         <- Antigravity / Agent IDE workspace rules
│   │   ├── domain.md.template    <- Template for project domain rules (Tier 1B)
│   │   ├── persistence.md.template <- Versioned state contract
│   │   └── readme_quickref.md.template <- adopter README quick-ref (R6)
│   ├── skills/
│   │   └── aikit/
│   │       ├── SKILL.md          <- Operational runbook index (source of the copies)
│   │       ├── projects.md       <- Project command matrix and Reforge protocol
│   │       └── delegation.md     <- Sub-agents, aikit delegate, headless OpenCode
│   ├── agents/
│   │   └── opencode_worker.md    <- OpenCode subagent spec for free models
│   └── task_ledger.json          <- Disruption ledger for power-loss resilience (WAL)
├── .opencode/
│   └── agents/                   <- OpenCode subagent profiles (architect, coder, ...)
├── opencode.jsonc                <- OpenCode provider, model & permission config
├── scripts/
│   ├── sync_principles.py        <- Generates 8 Tier 1 files from GUIDELINES.md
│   ├── sync_licenses.py          <- Pinned license/catalog sync and drift check
│   ├── disruption_recovery.py    <- audit, checkpointing and ledger CLI
│   ├── disruption_help.py        <- generated help for the recovery fast path
│   ├── state_machines.py         <- Explicit lifecycle machines (read-only registry, ADR-388)
│   ├── update_knowledge_base.py  <- Codebase AST symbol extractor & validator
│   ├── dogfood.py                <- Dogfood runner (sandbox jail + chaos tracks)
│   ├── check_reachability.py     <- reachability shield (anti-dead-capability)
│   ├── check_test_budgets.py     <- Test tier budget gate (per-test ceilings)
│   ├── project_registry.py       <- Project discovery, stack detection, memory
│   ├── project_license.py        <- License tiers and restrict
│   ├── marked_blocks.py          <- aegean:<name> blocks a generator owns in user files
│   ├── project_gates.py          <- A project's gates: detection, overrides
│   ├── check_project_hygiene.py  <- Source, asset & artifact hygiene
│   ├── ui_contract.py            <- Bounded UI-surface guard (opt-in .aikit/ui.json)
│   ├── ui_proof.py               <- UI proofs: inventory diff + style drift lint (pure)
│   ├── aikit_cli.py              <- `aikit.py` commands
│   ├── aikit_parser.py           <- `aikit.py` grammar, alone for --help
│   ├── aikit_help.py             <- Generated top-level help for the --help fast path
│   ├── subagent_delegate.py      <- Bounded OpenCode sub-agent runs
│   ├── project_publish.py        <- Uploads a project to its own GitHub repo
│   ├── git_guard.py              <- pre-push guard: raw push is refused (ADR-341)
│   ├── project_archive.py        <- Retires a project to projects/archive/ and archives GitHub
│   ├── dossier_sync.py           <- Publish-time AegeanWorks catalogue sync (ADR-308)
│   ├── project_ui.py             <- Durable has_ui/ui_kind identifier (ADR-233)
│   ├── project_topics.py         <- AI topic brief and validator, max 20 (ADR-236)
│   ├── project_media.py          <- logo/social/screenshot pipeline (ADR-235)
│   ├── project_machine_states.py <- Live project-level state machines (ADR-401)
│   ├── project_brand.py          <- motif, palette and social composition (ADR-238)
│   ├── project_artwork.py        <- image-model hero art + text overlay (ADR-239)
│   ├── brand_catalog.json        <- Authored unique project identities
│   ├── check_secrets.py          <- Secret/sensitive data scanner
│   ├── delegate_transcript.py    <- Append-only delegate transcript + replay (S-E)
│   ├── evidence_outcome.py       <- Shared no-evidence inconclusive outcome (IDEA-1118)
│   ├── proof_envelope.py         <- Sealed HMAC commit-proof envelope (IDEA-1168)
│   ├── evidence_policy.py        <- Named policy over step attestations (IDEA-1169)
│   ├── proof_corpus.py           <- Witness-keyed proof corpus (IDEA-1156)
│   ├── proof_gate.py             <- Fail-to-pass proof gate (IDEA-956)
│   ├── project_compat.py         <- AI-compat scaffold + proof (inventory/deltas/screenshots)
│   └── verify_commit.py          <- Verifies a commit alone in a throwaway worktree
├── reports/                    <- Local-only research inbox (PRINCIPLE-016 R7; only README.md tracked)
│   └── README.md               <- Inbox lifecycle: triage into the register, then delete
├── tests/
│   ├── test_kit.py               <- Unit tier (<=20ms per test)
│   ├── test_auto_register.py     <- Unit tier: idea registration from commits
│   └── test_integration.py       <- Integration tier: concurrency, CLI contracts
└── knowledge/
    ├── INDEX.md                  <- Knowledge base table of contents
    ├── architecture.md           <- System architecture and component boundaries
    ├── services.md               <- Core services and API contracts
    ├── data_models.md            <- Data structures, schemas, and persistence models
    ├── state_and_ui.md           <- Presentation layer, UI state, and event loops
    ├── state_machines.md         <- Verified inventory of implicit lifecycle machines (ADR-388)
    ├── state_machine_proposals.md  <- State-machine fix proposals and verdicts (ADR-388)
    ├── decisions.md              <- Architectural Decision Records (ADRs)
    ├── codebase_map.md           <- Auto-generated AST catalog of classes and functions
    ├── model_benchmarks.md       <- Subagent model benchmarks & selection tree
    ├── host_clients.md           <- Host client portability & parity
    ├── repo_backlog.md           <- Repos left for later
    └── principles_audit_ledger.md  <- Snapshot audit at ADR-107 (not kept current)
```

---

## 🚀 Start a Project

Open this folder in any AI host and describe what to build. Each project gets its own folder under `projects/` (ignored by AIKit's git) and its own repository; AIKit's gates, map and ledger never read it. `new` also detects the UI kind, adds license topics and creates logo/social candidates that must be reviewed before `publish` (ADR-243, ADR-245).

```bash
python aikit.py new my-app --description "<10-350 chars>" --topic web  # new repo, .aikit/, AL-1.1 LICENSE, AIKit badge
python aikit.py attach ../existing  # register an existing folder; adds .aikit/, ignore rules, badge
python aikit.py list                # every project, its stack and test command
python aikit.py status my-app       # task, changes, decision; --exit-code fails when dirty, --json for CI
python aikit.py check my-app        # tests, checks, hygiene, guidelines, secrets; --push pushes (exit 1 if blocked)
python aikit.py push my-app          # every gate, then push to origin (alias for check --push; never forced)
python aikit.py check my-app --strict  # delivery gate: clean tree, map, no conflicts, no open UI task
python aikit.py ui init my-app        # React/Vite pilot: write a conservative .aikit/ui.json
python aikit.py ui init my-app --fast "npm run test" --paths "src/**"  # other stacks
python aikit.py ui begin my-app --surface menu  # bound edits to one declared UI surface
python aikit.py ui verify my-app       # scope, budget, fast + snapshot proofs, style drift
python aikit.py ui allow my-app "Btn*" --reason "<why>"  # intended inventory removal
python aikit.py ui finish my-app --reviewed  # close after review; a guideline can waive the human
python aikit.py fix my-app          # restore memory/README, adopt UI, refresh map, then check
python aikit.py guideline my-app "money is integer cents" --source user  # project rule
python aikit.py publish my-app [--owner ORG] [--license auto]  # pre-push guard, repo, description, recorded AI topics
python aikit.py archive my-app --reason "superseded by X" [--offline]  # move to projects/archive/, archive GitHub repo
python aikit.py license my-app [--suggest|--set game|--restrict]  # AL-1.1, AGL-1.1 (DRM-free games) or ASL-1.1 (science)
```
A project's memory is `.aikit/`; ledger commands take `--workspace projects/<name>`. `publish` installs a pre-push guard at `.git/hooks` or the repository's `core.hooksPath`: a raw `git push` is refused until the project is uploaded through AIKit (ADR-341, ADR-342); `push`, `check --push` and the online `archive` path use the same authorized push (ADR-343). Publishing also needs a 10-350 char README description; `license` picks AL-1.1, AGL-1.1 or ASL-1.1. `check` wants `checklists: passed`; deliberate hygiene findings need `hygiene: allow <reason>`. `ui` is opt-in (`.aikit/ui.json`); `finish` needs `--reviewed` (ADR-160..166). `check`/`fix`/`publish` run project commands unsandboxed: attach trusted repositories only.

## 🔁 Aegean Reforge: Host Review & Safe Repair

Reforge audits history in widening windows and repairs only what it can prove. It lives in
`reforge/` and `reforge.py`: `aikit.py reforge` uses the project registry; the standalone repository
is archived (ADR-248).

```bash
python aikit.py reforge start my-app --start 3 --step 3  # full history by default
python aikit.py reforge audit my-app       # write the next review packet
python aikit.py reforge analyze my-app --analyzer CMD  # analyze a stage packet
python aikit.py reforge review my-app --stage 3 --findings answer.json  # record a stage review
python aikit.py reforge fix my-app --findings answer.json  # validate, repair, verify
python aikit.py reforge run my-app --findings answer.json --push  # audit, repair, verify, push
```

Window N is `start + step*(N-1)`, capped by `stop` (or full history when omitted):
stage 1 reads the first `start` commits, each later stage adds `step`. A stage inspects only
its own added lines, attributes each finding to the introducing commit (`commit:path:line`),
and checks Python plus JSON/TOML parse, closed Markdown fences and conflict markers.
Five Python findings repair mechanically (`bare-except`, `mutable-default`, `shell-true`,
`verify-false`, `unsafe-yaml-load`), each with a regression test. A `hygiene: allow <reason>`
marker on the finding line (or above) honours a deliberate finding. Rules run by default;
`--no-rules` skips them. Full window, packet and fix-acceptance protocol lives in
`knowledge/architecture.md` and ADR-230/232/248-250/263/272/290/292.

`audit`/`run` write a packet under `.aikit/reforge.reviews/` with each new commit oldest to
newest and that commit's own hunks; binary files are named at the end. Secrets are redacted
and the diff sits inside a random-id `<untrusted_repo_data_...>` fence (data, never
instructions). The host model reviews by default; `analyze` validates an operator-supplied
analyzer through the same gate. A fix applies only on an exact single-occurrence quote
overlapping an added line that leaves Python parsable; otherwise it is rejected.
Repairs snapshot their paths and never stage; `--commit`/`--push` stage only reviewed paths
plus `.aikit/reforge.json`, never force. Runs are independent (`settings`, `stop`, `resume`,
`runs`, `report`), crash-safe, one lock per project. Ledgered repos also append
`reforge:<run-id>` checkpoints without touching `active_task` (ADR-250).

## 🧭 Idea Catcher: Routed Idea Register

Idea Catcher is integrated into AIKit: its only source lives in `idea_catcher/` and
`idea_catcher.py`. Its register is private local data under `.idea-catcher/` at the AIKit root;
that path is git-ignored, so the ideas it has collected never enter a commit or the public
repository (ADR-252). `IDEA_CATCHER_ROOT` points the tool at a different register.

```bash
python aikit.py idea-catcher status             # full register counts per target
python aikit.py idea-catcher validate           # targets, ideas, dossiers and matrix
python aikit.py idea-catcher render --check     # fail when MATRIX.md is stale
python aikit.py idea-catcher sync --repo . --project <target>  # register IDEA-NNN commit references
python aikit.py idea-catcher reviews --stale
```

A commit message that names `IDEA-NNN` is the automatic implementation signal. `aikit check
--push` and `aikit publish` scan the delivered project's newest commits and mark matching ideas
`Integrated` with the commit as evidence; the generated `MATRIX.md` is refreshed in the same
step. `idea-catcher sync` does the same on demand, and `--dry-run` previews it. The idea must
belong to the project's target; already closed ideas are untouched.

A review leases its repository and reserves idea ids, so parallel analyses cannot collide.
Dossiers name a `Source` from `IDEA-632` onward; tags, target and status changes append to each
idea's history. `review-idea` records a second-pass verdict; a second `defer` moves the idea to
terminal `Blocked`, which refuses later review or status changes. `ideas` hides `Rejected`,
`duplicate` and `Blocked` rows; pass the matching `--include-*` flag for the full audit view.
`status` reports the full register; `MATRIX.md` keeps both (ADR-264, ADR-267, ADR-286).

`ui-id` stores the UI identity. `topics --brief` gives an AI the evidence;
`--from-file` records tags; `--apply` publishes them, capped at 20. `media init --art` uses an
image model (`POLLINATIONS_API_KEY`); approved logos survive unless `--force`. `attach`/`fix` seed
media candidates; `fix` adds an approved banner to a README lacking one; `publish` syncs the
dossier catalogue.

## 📥 Alternative: Copy AIKit Into an Existing Project

To govern a repository in place, copy `GUIDELINES.md`, `scripts/`,
`knowledge/` and `.agents/`, run the sync scripts, and keep project rules in `domain.md`. Do not
copy `tests/`, `.github/` or the ledger.

---

## 🏛️ The 20 Core Principles (Lifecycle-Ordered)

The principles are strictly organized across **5 chronological execution phases**:

<!-- principles:begin (generated from GUIDELINES.md by scripts/sync_principles.py; do not edit) -->
### 🏛️ Phase 1: Meta-Governance & Attentional Grounding
| Principle | Title | Capsule |
|---|---|---|
| **PRINCIPLE-000** | Meta-Principle Integrity & Mutual Alignment | Every rule binds; conflicts follow R6 order; rule edits re-check every citing principle; gaming a gate is a violation; quality doubts go to the user. |
| **PRINCIPLE-001** | Progressive Rule Disclosure & Governance Frugality | Pre-Flight checklist before the first Track C edit; Post-Flight checklist before any Track B or C commit; report only failed items (R8). |
| **PRINCIPLE-002** | Lifecycle-Aligned Instruction Ordering & Attentional Priming | Track via `disruption_recovery.py --track` (A none, B docs/comments but not rule files, C rest); urgency alone never skips P018 gates (R5). |
| **PRINCIPLE-003** | Empirical Grounding & Anti-Hallucination Invariant | Read-before-write slice freshness; `git grep -w -e` call-site check; deps only if declared; platform parity; ask on intent ambiguity; strict AST syntax gate. |
| **PRINCIPLE-004** | Attentional Drift Prevention & Compaction Resilience | Plan = latest `[1/` Phase 2 `--desc` in `task_ledger.json`; cold start `--resume`; never re-ask recorded answers; ADR before commit; reads/output <=100 lines. |

### 🧭 Phase 2: Pre-Flight Orientation & Planning
| Principle | Title | Capsule |
|---|---|---|
| **PRINCIPLE-005** | AI Cold-Start Readiness & Living Documentation | README <=32500 chars: prerequisites, test command, tree; user-visible changes update it same commit; `update_knowledge_base.py --check` gates it. |
| **PRINCIPLE-006** | Incremental Progress Checkpointing & Disruption Recovery | Commit `[milestone N/M]` once Phase 4 passes under PRINCIPLE-018 R1; failing work uncommitted via `--checkpoint`; `--complete`/`--reset` before switching tasks; `--clean` stale `.tmp_*`; ledger writes name `--agent`; another agent's task needs `--take-over`. |
| **PRINCIPLE-007** | Pre-flight Impact & Quality Checklist | Track C first plan checkpoint carries --why --benefits --risks (contract, dependency, concurrency, state) --mitigation; no TODO or stub; no change outside the plan. |
| **PRINCIPLE-008** | Hierarchical Problem & Task Decomposition | Plan of M<=6 milestones (more: split into tasks), built bottom-up, each passing Phase 4 alone; re-plan = new `[1/M']` checkpoint; sub-agents never write the ledger. |

### 🏗️ Phase 3: Architecture & Lean Implementation
| Principle | Title | Capsule |
|---|---|---|
| **PRINCIPLE-009** | Modularity & Pluggable Architecture | Every module: no junk-drawer name, roles of 1-5 methods, no import cycle (gated). At a pluggable boundary: 4 layers, registry lookup, constructor DI with default, frozen DTOs. |
| **PRINCIPLE-010** | Performance & Resource Optimization | Stream uncontrolled input; threads only for steps >=200ms; timeout= on subprocess, with on open(); one fsync per file; `--help` <1000ms; unit <=20ms, integ <=1000ms/test. |
| **PRINCIPLE-011** | Zero-Friction Onboarding & Instant Usability | Only declared deps; creates its dirs; prompts only with `--interactive`; no `os.environ[...]` reads; exit 0/1/2/3 (`3` = gates passed, tree not delivery-ready, ADR-410); errors give `Why:`/`Fix:`; demo <10s; other software: its `aikit.py` project is the workspace (R8). |
| **PRINCIPLE-012** | Token Frugality & Lean Code Architecture | LLM code: <=16k-char payloads, static prefix first, schema-checked replies, 429 backoff, step caps; agent: diff -U3, search <=50 hits, relative paths. |

### 🛡️ Phase 4: Operational Verification & Resilience
| Principle | Title | Capsule |
|---|---|---|
| **PRINCIPLE-013** | Crash Resilience, State Atomicity & Power-Loss Recovery | State files: >=10MB free, temp + fsync + os.replace (5 tries) + dir fsync, .bak, advisory locking 3s/30s stale, corrupt -> quarantine/.bak/migrate. Generated: temp + fsync + replace. |
| **PRINCIPLE-014** | Automated Test Verification & Continuous Test Coverage | 100% test pass gate; behaviour change = failing-first test; weakening a test needs user approval + ADR naming it; unit <=20ms/test, no spawns/sleeps; integ <=1000ms/test; tempdir + addCleanup; `scripts/check_reachability.py`. |
| **PRINCIPLE-015** | Universal Operational Dogfooding & Chaos Verification | Domain-specific interactive dogfooding via `scripts/dogfood.py` as a commit gate; golden path + chaos perturbation; non-interactive stdin parity; portable RAII process tree teardown; ephemeral safety jail; terse reporting (<=15 lines). |

### 🚀 Phase 5: Living Synchronization & Delivery
| Principle | Title | Capsule |
|---|---|---|
| **PRINCIPLE-016** | AI Knowledge Base & Continuous Synchronization | Canonical `knowledge/` sync; atomic code-and-doc pairing; monotonic append-only ADR register; strict AST syntax validation; link integrity shield; `scripts/update_knowledge_base.py`. |
| **PRINCIPLE-017** | Living Principles System & Automated Synchronization | Rule sync (`scripts/sync_principles.py`); context budget check; schema compliance; freshness test gate; Tier 1B domain rules (<=1,200 chars). |
| **PRINCIPLE-018** | Automatic Git Workflow | Conventional commits (`--validate-commit`) + adaptive push, never forced, only if authorized (R1); explicit staging (no `git add .`); pre-commit triad (tests/gates/diff); commit verified alone pre-push (R7); non-destructive recoil. |
| **PRINCIPLE-019** | Secret & Sensitive Data Hygiene | Zero credentials in tracked files, logs or ledgers; secrets via env/secret store; `.gitignore` credential baseline; `scripts/check_secrets.py` scans staged diffs + ledger; redacted diagnostics; rotate, never revert. |
<!-- principles:end -->
---

## ⚡ Disruption Recovery & Power-Loss Protection

If electricity cuts out, battery dies, or the computer crashes mid-task:
1. **Pre-flight Audit**: On a cold start, run this one command first (PRINCIPLE-004 R2):
   ```bash
   python scripts/disruption_recovery.py --resume
   ```
   It prints `--audit` findings, the active task, plan and resumption phase; with none it confirms a clean working tree.
2. **Everything else** (`--audit`, `--checkpoint`, `--complete`, `--reset`, `--clean`) is in the command matrix above.
3. **Atomic File Safety**: state files use temp write, fsync and atomic rename (PRINCIPLE-013); corrupt ledgers auto-recover from `.bak`.

---

## 🛠️ Adding New Principles to Your Project

1. Add `### PRINCIPLE-0XX: [Title]` (the next free ID) to `GUIDELINES.md` only, with `Problem`, `Concept`, `Invariant` and numbered `Rules`, under the right lifecycle heading.
2. Raise `MIN_PRINCIPLES` in `scripts/sync_principles.py` and `EXPECTED_PRINCIPLE_COUNT` in `tests/test_kit.py`; add the ID to this README and both checklists.
3. Run `python scripts/sync_principles.py`. On `[TOKEN EXCEEDED]` or `[TIER 1B HEADROOM]`, pay for the new capsule by condensing existing capsule narrative (PRINCIPLE-001 R9).
4. All 8 generated Tier 1 files then carry the new capsule.
