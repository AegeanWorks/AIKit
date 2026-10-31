"""Generated top-level help for the disruption-recovery `--help` fast path (ADR-180).

The string is compared with `scripts.disruption_recovery.HELP_TEXT` by
`tests.test_kit.TestAikitHelpFastPath`. Regenerate it when the help text changes.
"""

HELP_TEXT = """\
AIKit Disruption Recovery & Task Ledger (PRINCIPLE-006, PRINCIPLE-013)

Usage:
  python scripts/disruption_recovery.py [ACTION] [OPTIONS]

Actions (default: --audit):
  --audit                    Report working-tree drift, dangling buffers, and ledger state
  --resume                   Print the resumption report for an interrupted task
  --clean                    Purge orphaned temporary buffers (*.tmp_*) older than 60 s; younger
                             ones may belong to a write in progress and are kept
  --checkpoint <task_id>     Record a task checkpoint in .agents/task_ledger.json; a task's
                             first plan (--phase-num 2, --desc starting '[1/') needs --why,
                             --benefits, --mitigation and --risks with 'contract:', 'dependency:',
                             'concurrency:' and 'state:' verdicts, else exit 2 (PRINCIPLE-007 R6);
                             a task reaching Phase 3+ with no assessment gets a warning
  --complete <task_id>       Mark a task as completed
  --reset [reason]           Abandon and clear the active task
  --suspend <reason>         Pause the active task without abandoning it; --resume-task <id>
                             reactivates it at its recorded phase (ADR-219)
  --resume-task <task_id>    Reactivate a suspended or superseded task
  --validate-commit <msg>    Validate a Conventional Commit message (PRINCIPLE-018)
  --track                    Print the lifecycle track (A/B/C) of the current changes (PRINCIPLE-002 R3)

Workspace:
  --workspace <dir>          Operate on <dir>'s ledger instead of this repository's:
                             <dir>/.aikit/task_ledger.json for a project (ADR-120), else
                             <dir>/.agents/task_ledger.json. Required for sandboxed
                             dogfooding, which must never mutate the host repo (PRINCIPLE-015 R4).

Checkpoint options:
  --phase <name>             Lifecycle phase label (e.g. planning, implementation)
  --phase-num <1-5>          Numeric lifecycle phase for compaction resumption
  --desc <text>              Checkpoint description
  --why <text>               Pre-flight impact: root cause / user goal (PRINCIPLE-007)
  --benefits <text>          Pre-flight impact: expected benefits
  --risks <text>             Pre-flight impact: blast-radius risks
  --mitigation <text>        Pre-flight impact: risk mitigations
  --handoff <text>           Cold-start packet as `key: value` segments separated by ';':
                             next (required), state, failed, open, evidence (PRINCIPLE-004 R2)
  --redact                   With --checkpoint: record credential-shaped free text as
                             [REDACTED] instead of refusing the write (PRINCIPLE-019 R3)

Agent options (--checkpoint, --complete, --reset; ADR-209):
  --agent <name>             Who is writing, e.g. kilo:2 (default: AIKIT_AGENT, else Claude
                             Code's own session id, else 'unidentified'); every write records it
  --take-over                Continue a task another identified agent owns; without it the write
                             exits 1 and changes nothing, with it the ledger records who
                             continued from whom
  -h, --help                 Show this help message and exit

Exit codes:
  0  success    1  operational failure (an unwritable, full or locked ledger prints
                    What/Why/Fix, never a traceback)    2  CLI argument misuse
"""
