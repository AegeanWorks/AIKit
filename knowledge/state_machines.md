# Implicit State Machines in AIKit

Status: verified inventory (ADR-388). This is the list requested before any fix;
the explicit subset lives in `scripts/state_machines.py` and is readable with
`python scripts/state_machines.py --list`. Nineteen of the 88 state names are
shared by more than one machine, so `--which <state>` names the machines that
declare a bare status read from a file.

An **implicit state machine** is a set of states encoded in JSON fields, status
strings, files or flags, with transitions enforced (or merely assumed) by code.
The method was: map each subsystem from the source, re-read every claimed
transition, then run the suite and the live CLI to separate real behavior from
comments.

## Summary

| Subsystem | Machines | Explicit in registry |
|---|---:|---|
| Task ledger / disruption recovery | 11 | 2 (`task-lifecycle`, `ledger-generation`) |
| Reforge | 9 | 4 (run, review, delivery, lock note) |
| Idea Catcher | 10 | 3 (`idea-status`, `idea-repo-review`, `upstream-check`) |
| Project lifecycle | 10 | 4 (project, license, UI, media; gate result included) |
| Proof / evidence / verification | 7 | 3 (`shared-outcome`, `proof-verdict`, `proof-corpus`) |
| Delegation / UI task / publication | 8 | 7 (delegate run, transcript, UI task, compat, corpus, dossier; gate result shares) |
| Total discovered | ~55 | 21 |

The registry is the **explicit contract**, not a claim that every transition is
enforced. Each machine records its source and a known gap.

## 1. Task ledger / disruption recovery

| Machine | States | Source | Enforcement / gap |
|---|---|---|---|
| **Task lifecycle** | missing, in_progress, suspended, completed, abandoned, superseded | `active_task.status`; `disruption_recovery.py:record_checkpoint, mark_task_completed, suspend_active_task, reset_active_task, resume_task` | Real guards for ownership and wrong-id completion. **Gap (fixed):** `record_checkpoint` reopened a completed task through the same id; `--audit` hid a suspended task; an unknown status was invisible. |
| Ledger generation | missing, legacy, valid, corrupt, quarantined, newer | `.agents/task_ledger.json`, `.bak`, `.corrupt_*`, `.tmp_*` | Atomic write + `.bak` + quarantine. **Gap:** `load_ledger` quarantines on read; `--audit` may create `.agents/`; `.corrupt_*` is never swept. |
| Lifecycle phase | 1..5 + free-text label | `active_phase`, `phase_num`, `last_phase` | `resolve_phase_num`; **no monotonicity**: a later `--phase-num 1` moves the recorded phase backwards. |
| Ownership / take-over | unowned, unidentified, mine, other | `owner`, `started_by`, `continuations` | `_claim` refuses another identified owner; a **suspended** task is unowned because `_claim` short-circuits on `status != in_progress`. |
| Resumability | paused / not paused | derived from the latest checkpoint (`resumable_tasks`) | Only `suspended`/`superseded` are offered; an `in_progress` non-active task is a **ghost** visible nowhere. |
| Advisory lock | absent, held, contended, stale, stolen | `<ledger>.lock` | 3 s acquire timeout vs 30 s staleness; a live holder older than 30 s can be stolen. |
| Checkpoint admission | first plan, prior impact, malformed handoff, leaked secret | `checkpoint_command` | Impact gate keys on the `[1/` prefix; a Phase-2 plan without the marker bypasses it. |
| Audit verdict | clean, disrupted, blocked, incomplete | `audit_body_lines` | Precedence is an `if/elif` chain; `--audit`/`--resume` exit 1 only for a ledger error, so 🔴 conflicts and 🟡 disruption exit 0. |
| Temp-buffer hygiene | fresh (<60 s), stale | `*.tmp_*`, `*.steal_*` | Young buffers are skipped silently; `.bak`/`.corrupt_*`/`.lock` are not swept. |
| Schema version | missing, 1, older, newer, invalid | `version` | Newer/invalid refused; a non-object root bypasses the version check. |
| CLI action precedence | ordered flags | `__main__` `elif` ladder | Conflicting actions are never refused (`--audit --complete x` completes). |

## 2. Reforge

| Machine | States | Source | Enforcement / gap |
|---|---|---|---|
| **Run** | none, active, stopped, completed | `.aikit/reforge.json` `run.status` | `stop`/`resume`/`settle_run` guard most transitions; an unknown status is accepted as advanceable. `completed -> stopped` is refused with a full Why/Fix triad (verified). |
| Stage / window | stage 0..N, window size, terminal window | `stage`, `window`, `audited_commits`, `total_commits` | `plan_next_stage` refuses completed/stopped/pending review; lowering `--stop` below the current window creates a no-output deadlock. |
| **Review** | none, unreviewed, partial, reviewed | `entry.review.status` | `review` refuses `partial`; `fix` accepts and persists it; a review older than `MAX_HISTORY` stops blocking completion. |
| Finding | fixable/repaired/rejected, source/category | `entry.findings[]` | `mark_repairs` runs after the tree edit; a crash leaves repaired=False on a repaired tree. |
| Repair | applied, left-for-review, not-repaired, dropped | `entry.repairs[]` | In-memory snapshots only; a crash mid-repair has no on-disk undo. |
| **Delivery** | absent, empty, uncommitted, commit_failed, unpushed, pushed | `entry.delivery` | A crash between `git commit` and `mark_delivered` leaves a commit with no SHA; no `reforge delivery` command reconciles it. |
| Lock | absent, held, stale, contended | `.aikit/reforge.run.lock` | 3600 s stale window; `analyze`, `status`, `runs`, `report` read outside the lock. |
| Ledger mirror | in_progress, suspended, completed | `reforge:<run-id>` checkpoints | A third copy of run status written outside the state transaction; never updates `active_task`. |
| State schema | missing, 1 (migrated), 2 | `schema` | Read migration is not written back; `active_run`/`last_run` need not name a real run. |

## 3. Idea Catcher

| Machine | States | Source | Enforcement / gap |
|---|---|---|---|
| **Idea status** | Proposed, Approved, Integrating, Integrated, Deferred, Blocked, Rejected, Superseded | `ideas[].status` | Terminal guards exist in `_apply_status`; **`validate_ideas` has no transition table**, so a hand-edited register can reopen a terminal row. |
| Review verdict | adopt, confirmed, defer, duplicate, implemented, obsolete, reject, blocked | `ideas[].review_log[]` | Verdict vocabulary closed; `set-status --status Deferred` also appends a defer review. |
| Deferral counter | 0, 1, 2+ | derived with `max()` from review log, history and status | Second deferral coerces to Blocked; three records can disagree and `max()` hides it. |
| Tags | verification tags + flags | `ideas[].tags` | One verification tag; adding silently evicts the old one; display uses stored tags while filters use effective tags. |
| **Repo review** | idle, active, stale, finished, abandoned | `.idea-catcher/reviews.json` | Expiry is lazy: only `--release-expired` abandons a past lease, so `MATRIX.md` can call an expired lease active. Reservation, expiry, abandonment and forced takeover are now pinned by `TestIdeaCatcherLeaseLedger`. |
| Number reservation | free, reserved, registered, released | `reviews[].reserved_ids`, `consumed_ids` | Gaps legal only while reserved; `consumed_ids` is written but never validated. |
| Dossier routing | in-sync, retargeted, orphaned, missing, duplicate | dossier headings + `retargeted_from` | Validation catches drift; there is no command to edit a dossier. |
| Freshness | current, aged, unknown, superseded | derived (`classify_freshness`) | Name collision with idea status `Superseded`; never persisted. |
| **Upstream revalidation** | current, missing, licence_changed, moved, archived, analysis_behind, skipped, error | `upstream_check.py` | Precedence is an `if/elif` chain; `--strict` fails on `skipped`/`inconclusive`, contradicting `--help`. Decided states are final per run; `skipped`/`error` can be retried, and a skip does not say whether a limit or a missing repo caused it. |
| Claims audit | implemented, implemented_elsewhere, stub, absent, unknown | `claim_audit.py` | `unknown` only on truncation; `--strict` fails only on `absent`. |

## 4. Project lifecycle

| Machine | States | Source | Enforcement / gap |
|---|---|---|---|
| **Project** | unregistered, local, attached, missing, archived | `projects/<n>/.aikit/project.json`, `attached.json`, folder | Create/attach guards are real; no detach or unarchive command; `publish`/`check` never refuse an archived project. |
| **License** | unrecorded, personal, restricted | `project.json.license`, LICENSE first line | `restricted` is one-way; a crash between LICENSE and config reads as `unrecorded`, and a half-restricted project can be published. |
| Gate set | detected, configured, disabled, built-in, absent | `project.json.gates`, markers | Built-ins cannot be overridden; the compat gate disappears if `.aikit/compat.json` is deleted; `-1` means start-failure or timeout. |
| Delivery readiness | clean, dirty, git_missing, ledger_error, ui_task_open, required errors | derived | Three different cleanliness definitions (`project_is_clean`, `project_baseline_errors`, archive's porcelain test). |
| Publish / remote / guard | local-only, has-origin, unpushed, pushed, guard installed | `.git/config`, hook, GitHub | Guard installed before push; description/topics update only with `gh` auth; topics failure is a note, not a failure. |
| Archive | active, archived, archived-offline, moved-unrecorded | `project.json.archived*`, folder, README, GitHub | Forward transition only; partial move/record leaves a discoverable but unflagged project. |
| Topics | unrecorded, default-only, recorded, applied, drift | `project.json.topics*`, GitHub | `publish` rejects default-only; `check` only warns; no applied fingerprint. |
| **UI identity** | unknown, detected, manual, required | `project.json.has_ui/ui_source/ui_required` | `fix`/`media init`/`new`/`attach` call `auto_ui` and discard a manual identity; `ui_required` is one-way (pinned by `tests/test_kit.py:11482`). |
| Compat scaffold | no scaffold, headless, ui, verified | `.aikit/compat.json`, evidence files | Built-in gate but deletable; `emit_evidence` is unlocked. |
| **Media asset** | absent, pending, approved, rejected | `.aikit/media.json` | Only logo and social preview block publish; an unreviewed screenshot publishes. |
| **Gate result** | not_run, pass, fail, refused, rewrite | `project_gates.py` | Timeout and start failure both report `-1`; `new --publish` skips all gates. |

## 5. Proof, evidence and verification

| Machine | States | Source | Enforcement / gap |
|---|---|---|---|
| **Shared outcome** | not_run, pass, fail, inconclusive | `evidence_outcome.py` | Zero observations -> inconclusive; an unknown string is a refusal but is never validated. |
| **Proof verdict** | not-run, holds, failed, setup-error | `proof_gate.py: main` | Exit 0 holds / 1 failed / 2 setup, measured. The returned record carries only a boolean `proof`, so a setup failure is visible in the exit code, not the record. Each test run is classed separately as passed/assertion/error/timeout. |
| Mutation scoring | killed, survived, timeout, error | `proof_gate.py` | Only `assertion` kills; the threshold shrinks to the number generated; an empty mutation set fails even when optional. `waived` is a summary count of unrun mutants, not a per-record state; a record with no mutant generated is simply absent from `records`. |
| Receipt / corpus | absent, stored, replay-pass, replay-fail, replay-inconclusive, pruned, corrupt | `proof_gate.write_receipt`, `proof_corpus.py` | Replay is read-only: it returns the shared three outcomes without changing the stored entry, so replay-* is an observation, not a persisted state. A failing re-run of the same witness key overwrites a stored pass; corrupt entries are skipped and never pruned. |
| Sealed envelope | unsealed, sealed, expired, tampered, unknown-key | `proof_envelope.py` | Check order masks tamper behind unknown-key/expiry; `--keyid` is effectively single-entry. |
| Evidence policy | pass, fail, inconclusive | `evidence_policy.py` | A `fail` is never outvoted; a quorum shortfall is inconclusive; the sealed branch is unreachable from `verify_commit`. |
| Commit verification | pass, fail, inconclusive, skipped | `verify_commit.py` | Missing `.aikit/proof.json` silently skips the proof step; `inconclusive` and `fail` share exit 1; `quorum:N` counts `project-files`. |

## 6. Delegation, UI task and publication

| Machine | States | Source | Enforcement / gap |
|---|---|---|---|
| **Delegate run** | ready, refused, blocked, ran-ok, ran-failed, timed-out, spawn-failed, ledger-violation | `subagent_delegate.py` | Refusals are pre-spawn; the sub-agent's exit 2 collides with AIKit's refusal; a refused run writes no transcript. |
| **Delegate transcript** | absent, in-flight, complete, invalid, replay-pass/fail/inconclusive | `delegate_transcript.py` | `verify_transcript` never recomputes the output digest, so replay does not prove identical text; no CLI path selects a transcript. |
| **UI task** | none, open, verified, stale, finished, aborted | `ui_contract.py` | A corrupt task advises `ui abort`, which needs the same unreadable file; abort drops allowed removals and records no history. |
| UI finding codes | 11 codes + `ui.other` escape | `ui_contract.py`, `ui_proof.py` | Prefix matching, no enum at the raise site; `ui.error` is outside the vocabulary. |
| UI inventory / style proof | baselined, allowed, lost, empty, lint-off | `ui_proof.py` | A renamed locator reports a loss; a missing snapshot command disables the layer; only added lines are linted. |
| UI surface evidence | evidenced, unevidenced, legacy, unreadable | `ui_contract.py` | Any edit invalidates evidence; an untracked file can block it permanently. |
| Dossier catalogue | no-dossier, skipped, synced, partial, media-stale | `dossier_sync.py` | Every skip is a named reason in the returned dict, so a partial sync is distinguishable from a complete one; an empty metadata list truncates the atlas; category can freeze while JSON-LD moves. |
| Compat proof | absent, headless, ui, pass, findings | `project_compat.py` | Optional seed/bench/evidence sections disable checks; `ui -> headless` retires screenshots; 124/127 sentinels collide. |

## 7. Supporting cross-cutting findings

1. **Derived-but-unread state.** `ui_task.verified_at`, its `strikes` counter,
   transcript `status`/`*_len`, `ledger_shield: "unmutated"` and the scaffold
   benchmark baseline are written but never consumed.
2. **Silent partial success.** Dossier upserts and the compat runner return the
   same observable state for "unchanged" and "not checked".
3. **Exit-code overloading.** Delegate exit 2 is both a refusal and a worker
   failure; compat 124/127 are both sentinels and real codes; `verify_commit`
   maps fail and inconclusive to the same exit 1.
4. **Fabricated integrity claims.** The transcript docstring claims replay proves
   the identical verdict while the digest is never recomputed; the corpus
   docstring claims a changed tree files elsewhere while the witness omits the
   verdict and the pass can be overwritten.
5. **Dead-end recovery.** A corrupt `ui_task.json` tells the operator to abort,
   but abort reads the same file; a renamed surface makes abort raise `KeyError`.

## Cross-cutting findings (verified)

1. **Duplicate state without reconciliation.** Run status exists in
   `run.status`, `entry.review.status` and the task-ledger checkpoint; project
   license exists in five surfaces; project identity in six. Only some pairs are
   cross-checked.
2. **Missing reverse transitions.** No unarchive, unrestrict, detach, unpublish,
   or delivery reconciliation. Error text sometimes names them as if they exist.
3. **Read-only commands mutate.** `--audit` creates the memory directory and can
   quarantine the ledger on read; `load_ledger` renames a corrupt file.
4. **Status vocabularies are open strings.** The task ledger, reforge run and
   project UI accept an unknown value and treat it as "not the special case".
5. **Exit codes contradict verdicts.** `--audit`/`--resume` exit 0 for conflicts
   and disruption; `--complete`/`--resume-task` use 1 for a refused transition.
6. **Concurrency is single-ledger.** Two goal agents cannot both own the active
   task; the second either supersedes the first or is refused. This was visible
   live during the audit (`verify-83ideas` owned the ledger while this work ran).

## Verification log

- Baseline before edits: `python -m unittest tests.test_kit` -> **1009 tests,
  OK** (one skipped).
- Re-read and confirmed: completed-task reopen (`record_checkpoint`), suspended
  audit gap (`run_disruption_audit` + `audit_body_lines`), unknown status
  invisibility, reforge delivery crash window, idea terminal guards vs missing
  transition table, archived publish gap, manual UI overwrite + pinned test.
- After edits: `python -m unittest discover tests` -> **1118 tests, OK** (one
  skipped); `python scripts/update_knowledge_base.py --check` passes.
- Registry CLI: `--list` 21 machines; `--json` parses; `completed -> in_progress`
  refused with exit 1; `--help` 134 ms.
- Re-audit 2026-11-09: `upstream-check` added as the 20th explicit machine (8 states,
  source `idea_catcher/upstream_check.py`). The Mutation scoring row was corrected from
  six states to four: `waived` is a summary count of unrun mutants and `not-generated`
  never appears in the code. `test_mutation_record_states_match_the_code` now compares
  that row against `proof_gate` so the doc cannot drift back.
- Second re-audit 2026-11-09 (ADR-390): the machine called `proof-verdict` was really the
  shared outcome, so it is renamed `shared-outcome` and a real `proof-verdict` was added
  with the measured `not-run/holds/failed/setup-error`. The Receipt/corpus row now says
  `absent` (the code's word) and lists the three replay observations separately, because
  replay is read-only. `test_registry_machine_names_match_the_doc_rows` pairs every
  registry machine with its doc row and fails when the vocabularies differ.
- Machine states are not all literals. `gate-result`, `delegate-run`,
  `delegate-transcript` and `proof-corpus` describe states computed at call time, so
  the registry is a contract, not a claim that every transition is enforced.

## Evidence anchors

- Task ledger: `scripts/disruption_recovery.py:909-950` (record), `:963-985`
  (complete), `:998-1020` (reset), `:1123-1130` (suspend), `:1251-1291` (audit),
  `:1309-1366` (report).
- Reforge: `reforge/state.py:115-140`, `:638-677`, `:482-511`, `:515-539`;
  `reforge/pipeline.py:505-597`, `:659-668`.
- Idea Catcher: `idea_catcher/registry.py:107-139`, `:485-540`, `:1144-1247`,
  `:1295-1393`, `:1497-1816`.
- Project: `scripts/project_registry.py:1081-1176`; `scripts/project_publish.py:265-387`;
  `scripts/project_archive.py:270-563`; `scripts/project_ui.py:283-312`;
  `scripts/project_gates.py:183-232`; `scripts/project_media.py:322-345`.
