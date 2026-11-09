# State-Machine Proposals

Status: analysis and verification of the fixes proposed after
`knowledge/state_machines.md` (ADR-388). Six proposals passed and are
implemented (P1–P4, P9, P11, plus P10 partly); P12's discoverability half is
implemented as `--which` (ADR-394); the rest are deferred with the reason.

## Decision criteria

A proposal passes only when **all** hold:

1. **UX/DX/AX gain is concrete** — it removes a hidden state, a wrong verdict, a
   refused-but-silent transition, or a discoverability gap.
2. **No pinned behavior is weakened** — an existing test that pins the current
   behavior is a product decision, not a bug to edit away.
3. **Blast radius is bounded** — the change is one machine's transition or one
   read-only surface; no multi-surface rewrite without a migration.
4. **Failing-first evidence exists** — the test fails on the old tree and passes
   after the change.
5. **The full suite and the read-only gates pass** — no gate is bypassed.

## Proposals and verdicts

| # | Proposal | UX | DX | AX | Risk | Verdict |
|---|---|---|---|---|---|---|
| P1 | Declare the machines in `scripts/state_machines.py` with a read-only CLI | High | High | High | None | **PASS, implemented** |
| P2 | `--audit` reports a suspended task and an unknown task status | High | Med | High | Low | **PASS, implemented** |
| P3 | Refuse reopening a completed task through `--checkpoint` | High | High | High | Low | **PASS, implemented** |
| P4 | Refuse an unknown checkpoint status before writing | Med | High | High | Low | **PASS, implemented** |
| P5 | Validate Idea Catcher status transitions in `validate_ideas` | Low | High | High | Med | Deferred |
| P6 | Refuse `publish`/`check` on an archived project | High | Med | Med | Med | Deferred |
| P7 | Add a Reforge delivery reconciler for the commit-without-SHA crash | Med | High | High | High | Deferred |
| P8 | Make `restrict_project` transactional across LICENSE/config/README | Med | High | Med | High | Deferred |
| P9 | Preserve a manual UI identity across `fix`/`media init` | Med | Med | Med | Low | **PASS, implemented (ADR-397)** |
| P10 | Make `--audit` truly read-only (no mkdir, no quarantine) | Med | Med | High | High | **PASS, partly, implemented** |
| P11 | Complete `status --json` with every machine's state | Med | Med | High | Low | **PASS, bounded (ADR-401)** |
| P12 | Publish the status vocabulary in every `--help` | High | Low | High | Low | Deferred |

## Implemented proposals

### P1 — explicit registry (read-only)

`scripts/state_machines.py` declares 19 machines as data: states, allowed
transitions, the live source, and the known gap. The CLI is
`--list`, `--json`, `--machine <name>`, `--from/--to`, `--check-status`; it
never writes and `--help` exits 0 in ~134 ms. The 12 core machines were
extended with delegate-run, delegate-transcript, ui-task, compat-proof,
proof-verdict, proof-corpus and dossier-catalogue after the supporting
subsystem map completed.

Why it passes: it is additive, it gives AX a machine-readable contract and DX a
single place to change a vocabulary, and it makes UX failures explainable ("this
transition is not in the machine") without changing runtime behavior.

Verification: unit tests assert every transition target is a declared state and
the task machine equals the ledger vocabulary; the integration test pins the CLI
contract (help 0, JSON parses, allowed 0, refused 1, unknown flag 2).

### P2 — audit visibility

`run_disruption_audit` already detected `suspended_task`, but `audit_body_lines`
never printed it and `clean_shutdown` stayed true. `--audit` printed
`🟢 Clean state` while `--resume` offered the paused task. The audit now sets
`clean_shutdown=False` for a suspended or unknown-status active task and prints
`⏸️ Paused Task` / `🔴 Unknown Task Status`.

Why it passes: it is a read-only report change on data the code already
collected; the unit tests use a temporary workspace.

Verification: `test_audit_reports_a_suspended_task` and
`test_audit_reports_an_unknown_task_status` fail before the change and pass
after; the full suite is green.

### P3 — completed task is terminal

`record_checkpoint` treated a checkpoint with the completed task's id as a new
task: it replaced `active_task`, reset `started_by`, and erased the closure with
no superseded entry. The write path now raises `CompletedTaskError` inside the
ledger lock, so the file is unchanged; `checkpoint_command` (both CLIs) prints a
Why/Fix triad and exits 1.

Why it passes: completed is a terminal state in the machine; the change is a
single transition guard with a clear escape (`--resume-task` for suspended,
a new id for new work). New work under a different id remains allowed.

Verification: `test_completed_task_cannot_be_reopened_by_a_checkpoint` asserts
the status, checkpoint count and file are unchanged;
`test_a_new_task_can_follow_a_completed_one` asserts the escape.

### P4 — unknown checkpoint status

`record_checkpoint(status=...)` accepted any string; an unknown value made the
task invisible to every reader (`_claim`, audit, resumability). The function now
validates against the registry's checkpoint vocabulary before taking the lock.

Why it passes: the CLI never passes an invalid status, so no command changes; a
library caller gets a named error instead of a silent ghost.

Verification: `test_unknown_checkpoint_status_is_refused_before_writing` asserts
the error and that no ledger file is created.

## Deferred proposals and why

- **P5 (idea transitions).** The register is being edited by a concurrent goal
  during this change; a validation pass needs a quiescent `ideas.json` and a
  decision on `Integrated -> Proposed`. The transition table is identified but
  not wired. AX gain is real; blast radius is the whole register.
- **P6 (archived project guard).** `publish` on an archived project is clearly
  wrong, but `check` on one may be a legitimate read-only audit. The refusal
  boundary is a product decision, so it is not changed unilaterally.
- **P7 (delivery reconciler).** A new command and a recovery rule for a crash
  window; needs a design for "commit exists, no SHA" before code.
- **P8 (license transaction).** Reordering five writes or adding a journal
  changes failure semantics across LICENSE, REUSE, README and GitHub; needs a
  migration and a rollback test.
- **P9 (manual UI identity).** **Implemented (ADR-397), without weakening the
  pin.** The original claim was that the overwrite at `tests/test_kit.py` was a
  product decision that had to be overridden. Re-reading it: the pin asserts
  `auto_ui(root)` overwrites, which is exactly what `ui-id --set auto` means. The
  defect was that `fix` and `media init` used that same unconditional path. So
  `auto_ui` and `adopt_ui` gained a keyword-only `respect_manual=False`, and the
  two maintenance callers pass `True`. The pin is untouched and still passes.
- **P10 (read-only audit).** The quarantine rename on read is pinned by a test;
  making `--audit` non-mutating needs a separate recovery command. High value,
  but it changes a durability guarantee. **Partly implemented (ADR-393):** the
  `mkdir` half is fixed — `--audit` no longer creates `.agents` when the ledger
  is absent — while the quarantine of a corrupt ledger stays, because that is
  lossless recovery rather than a side effect.
- **P11 (complete status JSON).** **Implemented as far as it is honest (ADR-401).**
  The seven project-level machines are now reported (`project-lifecycle`,
  `license`, `ui-identity`, `media-asset`, `ui-task`, `task-lifecycle`,
  `ledger-generation`), and the payload names the fourteen it did not sample
  with `read_count` + `registry_count`, so 7 of 21 cannot be read as a complete
  snapshot. Reading the rest would open Reforge runs, the idea register,
  delegation transcripts and proof artifacts — work a cold-start status call
  must not do.
- **P12 (help vocabulary).** The generated help copies are test-pinned; adding
  the vocabulary means updating both copies and the README together. Follow-up.

## Verification

- `python -m unittest tests.test_kit` before edits: 1009 tests, OK (baseline).
- `python -m unittest discover tests` after edits: **1118 tests, OK** (one
  skipped).
- `python scripts/update_knowledge_base.py`: map regenerated, every audit passes.
- Registry CLI contract: `--list` 21 machines, `--json` parses, allowed exit 0,
  refused exit 1, unknown flag exit 2.
- **P9 and the discoverability half of P12 (ADR-394, ADR-397):** 1039 unit +
  89 integration tests pass; `state_machines.py --which <state>` resolves a bare
  status to its machines (19 of 88 names are shared), and `fix` / `media init`
  preserve a manual UI identity while `ui-id --set auto` still overwrites.
- **JSON-shape hardening (ADR-395, ADR-396, ADR-398):** 1041 unit + 89
  integration tests pass after `proof_envelope.verify`, the two proof write
  paths, `sync_licenses.check_licenses` and `dossier_sync._upsert_jsonld` were
  made to fail closed on a non-object document instead of raising.
