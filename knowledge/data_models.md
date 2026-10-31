# Domain Data Models & Schemas

## 📦 Data Structures
The single home of every schema in this repository (**PRINCIPLE-016** R5).

### Task Ledger (`.agents/task_ledger.json`, and `<project>/.aikit/task_ledger.json` per project)
Written only by `scripts/disruption_recovery.py` (locked, atomic; PRINCIPLE-013). `workspace_ledger_path` picks the project's file when the workspace has an `.aikit/` folder (ADR-120); the schema is the same.

| Key | Type | Meaning |
|---|---|---|
| `version` | int | Schema version, `1`; `migrate_ledger_schema` fills missing keys. `ledger_version_supported` decides both the read and the write path: an int from 1 to the current schema is accepted, and an older one is upgraded to the current version (in memory on load, before writing on save). A newer version, or a value that is not a real version (`0`, `-1`, `True`, `"1"`, `1.0`), is refused in place. A missing version is treated as legacy `1` in memory only (ADR-178). |
| `active_task` | object or null | `task_id`, `last_phase` (label), `active_phase` (1-5), `status`, `updated_at` (epoch s), optional `impact_assessment` {`why`, `benefits`, `risks`, `mitigation`}. |
| `checkpoints` | list | At most 20 entries (the active task's plan checkpoint is always kept). Each: `task_id`, `phase`, `phase_num` (1-5), `description`, `files_affected`, `status`, `timestamp`, `timestamp_str`, optional `impact_assessment`, optional `handoff`. |
| `checkpoints[].handoff` | object | Written only when `--handoff` is given, so a checkpoint without one carries no key and the ledger's shape is unchanged. Keys, all optional but `next`: `next` (the one action that resumes the task), `state`, `failed`, `open`, `evidence`. Bounded to 2,000 characters of input. The latest packet of the active task is what `--resume` prints, and its `next` replaces the generic Next Action line (ADR-174). |

`description` and the four `impact_assessment` fields are free text written into a git-tracked file, so a credential shape in any of them makes `--checkpoint` exit 1 before the ledger is read or written; `--redact` records the span as `[REDACTED]` instead (PRINCIPLE-019 R3, ADR-173).

`status` values: `in_progress` (recorded by `--checkpoint`), `completed` (`--complete`), `abandoned` (`--reset`), `superseded` (written for the previous task when `--checkpoint` names a different task while it was still `in_progress`; ADR-077). The plan is the latest `phase_num` 2 checkpoint whose `description` starts with `[1/` (PRINCIPLE-004 R1).

### Project Record (`<project>/.aikit/project.json`)
Written once by `write_memory` in `scripts/project_registry.py` when a project is created or first attached; never overwritten afterwards, so a person may edit it. Committed in the project's own repository (ADR-119).

| Key | Type | Meaning |
|---|---|---|
| `schema` | int | `1`; any other value is refused by `load_config`. |
| `name` | string | The project name: 1-64 of `a-z 0-9 - _`, starting with a letter or digit. |
| `test_command` | string or null | Overrides the detected test command; null means detect from the project's files on every call. |
| `gates` | object | Gate name to shell command (adds or replaces a gate) or null (disables a detected one); `secrets` cannot be named. Absent in records written before ADR-122, read as empty. |
| `ui_required` | bool | When true, `check --strict`/`publish` require a usable `.aikit/ui.json` and surface evidence (ADR-166). |
| `mechanics_required` | bool | When true, `check` requires the `mechanics` contract below (ADR-271). |
| `mechanics` | object or absent | A game/project's headless core: `core` is a list of existing relative paths, `test` is the command that exercises it; `check` adds that command as a gate. |
| `created` | string | Creation date, `YYYY-MM-DD`. |

The project's decision register is `<project>/.aikit/decisions.md`, created from `DECISIONS_TEMPLATE` with the same entry format as `knowledge/decisions.md`; `latest_decision` ignores the template's commented example.

Stacks and test commands are never stored: `detect_stacks` reads the marker files each time, so they cannot go stale.

### Project Guidelines (`<project>/.aikit/guidelines.md`)
The project tier of PRINCIPLE-001 R4: the project's own rules, written by people or agents, ranked below every principle (PRINCIPLE-000 R6). Created from `GUIDELINES_TEMPLATE`; everything after `## Rules` is one rule per line, `- **G-NNN** (source): rule`, where source is `user`, `ADR-NNN` or a person. IDs are never reused. `guideline_errors` (the guidelines gate) rejects a malformed line, a reused ID, a rule worded to override a principle, and a file over `PROJECT_GUIDELINES_MAX_CHARS`; `add_guideline` refuses the same before writing.

### Attached Projects (`projects/attached.json`)
Local to one AIKit checkout (git-ignored). Lists only folders outside `projects/`; folders inside it are found by their `.aikit/project.json`. Written under `file_lock`, atomically. Unreadable content is an error, never an empty list.

| Key | Type | Meaning |
|---|---|---|
| `schema` | int | `1`. |
| `projects` | object | Project name to absolute folder path. |

### Subagent Result Payload
Returned by `delegate_subagent` in `scripts/aikit_cli.py` (`python aikit.py delegate <role> "<task>" --format json`) when executing background tasks delegated to subagents (**PRINCIPLE-008 R1/R6**, **PRINCIPLE-012 R8**).

| Key | Type | Meaning |
|---|---|---|
| `status` | string | `"success"` if process returncode is 0, else `"error"`. |
| `agent` | string | Subagent role invoked (`worker`, `architect`, `coder`, `tester`, `reviewer`, `explorer`). |
| `exit_code` | int | Process exit code (`0` success, `1` operational failure, `2` usage error). |
| `duration_seconds` | float | Execution duration in seconds measured with monotonic clock. |
| `output` | string | Subagent execution findings, suggested diffs, or structured JSON; credential-shaped spans are redacted on every report path (ADR-173, ADR-177). |
| `ledger_shield` | string | `"unmutated"` confirming task ledgers were shielded against unauthorized modification. |

### Project Report Payload
Printed by `cmd_status` and `cmd_resume` in `scripts/aikit_cli.py` (`python aikit.py status <name> --json`, `python aikit.py resume <name> --json`) so CI and wrappers read a contract instead of parsing the human report (**PRINCIPLE-004 R2/R4**, **PRINCIPLE-011 R5**, ADR-172).

| Key | Type | Meaning |
|---|---|---|
| `ok` | bool | `true` when a report was produced; `false` only in the error envelope. |
| `clean` | bool | Delivery readiness, from `project_is_clean`: the same verdict `status --exit-code` returns. `status` only. |
| `project.name` | string | The project as the registry names it. |
| `project.path` | string | Absolute path to the project folder. |
| `project.repo_url` | string or null | Its `origin` remote, or `null` when it is local only. |
| `project.stacks` | list of string | Detected stack names, empty when none was detected. |
| `project.test_command` | string or null | Its test command, or `null` when none is set or detected. |
| `project.latest_decision` | string or null | The newest ADR line in its `.aikit/decisions.md`, or `null`. |
| `project.guidelines` | list of string | Its own rules, verbatim: the rules themselves, never a count, so a JSON cold start cannot lose them. |
| `disruption` | object | The `run_disruption_audit` record for the project, verbatim (see Task Ledger). |
| `ui_task_open` | bool | Whether `.aikit/ui_task.json` exists. `status` only. |
| `gates` | list of string | The Phase 4 gate names `check` would run. `status` only. |
| `error.code` | string | `"project.error"` on an operational or usage failure; `ok` is then `false` and no other key is present. |
| `error.message` | string | The failure's message line; its `Why:`/`Fix:` triad still goes to stderr in text mode. |

### Reforge Audit State (`<project>/.aikit/reforge.json`)
The progressive audits' durable record, written by `reforge/state.py` through AIKit's
`atomic_write_json` and `file_lock` when AIKit is present (portable atomic fallback otherwise);
ADR-230, ADR-232. The per-project run lock is `<project>/.aikit/reforge.run.lock`; other projects
use different locks and states, so they audit concurrently.

| Key | Type | Meaning |
|---|---|---|
| `schema` | int | `2`; schema `1` migrates in memory to `run-1`, and an unsupported value is refused without rewriting the file. |
| `next_run_id` | int | Counter for `run-<n>` IDs; IDs are never reused. |
| `active_run` | string or null | The run a plain `audit`/`run`/`fix` selects. A lock holder or a run with fixable findings blocks a second start. |
| `last_run` | string or null | The run status/report/fix fall back to after completion or stop. |
| `runs` | list | Independent runs, each with `id`, `start`, `step`, `stop`, `stage`, `window`, `audited_commits`, `status` (`active`, `stopped`, `completed`), `created`, `updated`, `last_audit`, `history`. |
| `stage`, `window`, `audited_commits`, `last_audit`, `history` | mirrors | Copies of the last run for schema-1 readers and compact reports. |

Window N is `start + step*(N - 1)`, capped by `stop` when set; `start >= 2`, `step >= 1`,
`stop >= start`, and `stop` may be `null` for unlimited. A run completes when its window reaches
`stop`; its history is then kept while a new run may start from any window. Each stage history is
bounded to 20 entries and carries `stage`, `window`, `commits`, `new_commits`, `prior_commits`,
`findings`, `repairs`, `counts`, `reviewed`, `review`, `skipped`, `tests`, `gates`,
`timestamp`. `skipped` lists only the changed binary paths a stage could not read as text
(ADR-249), so coverage is recorded rather than implied. Each finding carries `code`,
`category`, `severity`, `path`, `line`, `message`, `evidence`, `commit`, `hunk`, `symbol`,
`introduced`, `reproducible`, `fixable`, `interaction`, `source` (`ast`, `text` or `review`) and
`repaired`;
each repair carries `code`, `path`, `line`, `summary`, `test_name` and `applied`.

The same stages are mirrored into the repository's task ledger (`.aikit/task_ledger.json` in a
project, `.agents/task_ledger.json` at AIKit's root) as ordinary checkpoint entries under
`task_id` `reforge:<run-id>`, with `phase_num` 3, `status` `in_progress`, `suspended` or
`completed`, and `files_affected` holding the stage's finding paths plus the paths it could not
analyse (ADR-250). `active_task` is never written, so the operator's task survives an audit.

### Project Presentation Fields (`<project>/.aikit/project.json`)
`has_ui` (bool), `ui_kind` (`web`, `desktop`, `game`, `mobile`, `cli`, `library`, `service`),
`ui_evidence` (relative marker paths), `ui_checked_at` (the last identity write or change) and
`ui_source` (`detected` or `manual`).
`topics` is the AI-chosen list; AIKit validates it, never fills it. `license_topics` records the
mandatory license metadata tags for the project's AL/AGL/ASL/restricted tier. `ui_required` remains the
separate opt-in contract that makes `check --strict` enforce `.aikit/ui.json`; `fix` sets it when it
adopts a detected UI with a test command. `mechanics_required` and `mechanics` declare a game's
headless core and its test command, so the UI and an agent can call the same mechanics (ADR-271).

### Project Media Manifest (`<project>/.aikit/media.json`)
Schema 1; `name`, `repo`, `has_ui`, `ui_kind`, `palette`, `motif`, `layout`, `assets` (`logo`, `social_preview`,
optional `social_preview_png`, `artwork`) and `screenshots`. Logo and social previews may be SVG
fallbacks or model-rendered JPEGs (`model` records the model ID); each asset has `path`, `status`
(`pending_review`, `approved`, `rejected`), `generated_at`, `commit` and `review`; a review records
`reviewer`, `method` (`vision`/`structural`), `notes`, `score` and `reviewed_at`. A screenshot also
records `taken_at`, `viewport`, `width` and `height`, and its `commit` must resolve in the project.
`media apply` copies approved files to `projects/AegeanWorks/docs/media/<Repo>/` and writes the
dossier manifest `docs/media/<Repo>.json` (schema 1: `repo`, `logo`, `screenshots`).

### Brand Catalogue (`scripts/brand_catalog.json`)
Schema 1; `palettes` (one unique four-colour palette per project) and `projects`. Each project entry
has `motif`, `layout`, `palette` index, optional `monogram`, `display` (title-case override such as
"No More Clutter"), `category` (the logo eyebrow) and `tagline` (the curated social-card sentence).

### Reforge Audit State (`.aikit/reforge.json`)
Schema 2; `next_run_id`, `active_run`, `last_run`, `runs` and mirrored top-level fields (`stage`,
`window`, `audited_commits`, `last_audit`, `history`) so schema-1 readers stay readable. Each run
holds `id`, `start`, `step`, `stop`, `status`, its audited SHAs and a bounded history of stage
entries; a stage entry also records `reviewed` (files inspected), `skipped` (binary files only) and
`review` (status `unreviewed`/`reviewed`, the packet path, accepted `findings`, rejected reasons,
redacted span count) (ADR-253, ADR-263). A finding now carries `source` (`ast`/`text`/`review`), and
a reviewed finding may carry `patch_old`/`patch_new`, an exact replacement validated against the
stage's added lines before it is applied. The packet itself lives under
`.aikit/reforge.reviews/stage-<n>-<sha>.md`, matching the `reforge.` artifact prefix so delivery
never commits it. It wraps the repository-derived text in a random-id
`<untrusted_repo_data_...>` fence declared as data, never instructions (ADR-287). Reforge has no
sync config or standalone marker any more (ADR-248).

### Proof Declaration (`.aikit/proof.json`)
Optional commit-level object. `tests` is a required non-empty list of test paths; `sources` is an
optional list of source paths to mutate; `mutants` and `min_killed` are non-negative integers;
`require_mutation` is a boolean that needs `sources` and a positive `mutants`; `waive` is an
optional list of `FILE:LINE:OPERATOR` keys. When the file exists in a commit, `verify_commit.py`
runs `scripts/proof_gate.py` against the commit worktree and its parent and fails the commit when
the proof or the required mutation threshold fails (ADR-291).

### Idea Catcher Register (`targets.json`, `ideas.json`, `reviews.json`, `dossiers/`)
Schema 1, stored as private local data under `.idea-catcher/` at the AIKit root and never in Git.
`targets.json` holds the routing targets; `ideas.json` holds each idea's `id`, dossier,
concept, target, impact, effort, status, reason/evidence, optional `tags`, `superseded_by`, a
`history` list whose entries are either a status change or a `field` (`target`/`tags`) with
`from`/`to`, and a `review_log` list whose entries carry `at`, `by`, `verdict`, `files`,
`commands` and `evidence`. Two `defer` review verdicts move the status to `Blocked`; a blocked
idea refuses every later review or status change. `reviews.json` holds `repos` (claim count, last order) and `reviews` (review id, slug,
URL, kind, lease, reserved ids, state, order). A dossier section from `IDEA-632` onward must carry a
`- **Source**:` line. `MATRIX.md` and `CONCEPTS.md` are generated from these inputs.

## 🛡️ Model Invariants
1. Models are type-annotated; data passed between layers is a frozen dataclass or `NamedTuple` (**PRINCIPLE-009** R5).
2. Every setting has a documented default, so a clone runs with no configuration (**PRINCIPLE-011** R2).
3. A persisted model carries a version key (`version` in the ledger) and a migration function that fills missing keys (**PRINCIPLE-013** R4). A reader refuses an unsupported newer version without modifying or quarantining the file, and upgrades an older supported version through the migration rather than refusing it; a missing version is accepted only through a documented legacy migration.
