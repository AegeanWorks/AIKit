# AIKit Projects: Command Matrix

Read this when the work is in a project under `projects/` (the binding rules are in `SKILL.md`).

The user's software lives in its own project, never in AIKit's tree:
```bash
python aikit.py list                 # which projects exist
python aikit.py new <name> --description "<10-350 chars>" [--topic <t>]... [--kind software|game|science]  # own repo + .aikit memory; auto-detects UI, generates model logo/social candidates (POLLINATIONS_API_KEY) or local fallback, writes media pending; --publish refuses until logo/social are reviewed and applied (ADR-243)
python aikit.py attach <path>        # an existing folder: adds .aikit/ memory and an AIKit Integrated badge under its README title (uncommitted)
python aikit.py status <name>        # its task, changes, latest decision and its gates
python aikit.py check <name>         # its Phase 4: tests, stack gates, hygiene, guidelines, secret scan; exit 0 to commit; never pushes, add --push only when push delivery is authorized (PRINCIPLE-018 R4)
python aikit.py guideline <name> "<rule>" --source user   # a project rule, below the principles
python aikit.py publish <name> [--public] [--owner <org>] [--license auto]  # its own GitHub repo with the README description, the recorded AI-chosen topics and an AI-chosen license; needs a 10-350 char README paragraph; only when the user asks
python aikit.py license <name> [--suggest [--json]|--set software|game|science|--restrict]  # AL-1.1, AGL-1.1 (DRM-free games) or ASL-1.1 (science); --restrict, only when the user asks, makes later versions All Rights Reserved from HEAD (earlier releases keep their license), drops COMMERCIAL.md, blocks publish --public, and allows check --push or publish only to a repository gh reports private (ADR-214)
python aikit.py topics <name> --brief --json   # bounded evidence for an AI to choose tags; no tag chosen automatically
python aikit.py topics <name> --from-file <json> [--apply]  # record the AI's choice; apply only with --apply (ADR-236)
python aikit.py topics <name> --review [--json]  # audit current/recorded tags without choosing
python aikit.py ui-id <name> [--set auto|yes|no] [--kind <k>]  # durable has_ui/ui_kind evidence (ADR-233)
python aikit.py media init --art <name>  # IMAGE MODEL: POLLINATIONS_API_KEY env only; gen.pollinations.ai free flux model renders title+category, then the square is reframed to 1280x640; never commit the key (ADR-239, ADR-241)
python aikit.py fix <name>           # self-heals memory, adopts UI, cleans temp buffers, syncs codebase map
python aikit.py checkpoint <name>    # disruption checkpoint on the project ledger; --agent <host>:<session> names you
python aikit.py resume <name>        # disruption resume on the project
python aikit.py complete <name>      # mark project task complete; another agent's task needs --take-over
python scripts/disruption_recovery.py --suspend "<reason>" --workspace projects/<name>  # pause a task, keep it resumable
python scripts/disruption_recovery.py --resume-task <task_id> --workspace projects/<name>  # reactivate a paused or superseded task (ADR-219)
python aikit.py clean <name>         # clean dangling project buffers
python aikit.py reforge start <name> --start 3 --step 3  # full history by default; per-project lock
python aikit.py reforge audit <name>   # write the next window's review packet (commit:path:line)
python aikit.py reforge fix <name> --findings answer.json  # validate, repair, verify
python aikit.py reforge run <name> --findings answer.json --push  # audit, repair, verify, push
python aikit.py reforge review <name> --stage 3 --findings answer.json  # record any stage's review
python aikit.py reforge audit <name> --no-rules  # skip the deterministic pre-pass
python aikit.py reforge settings|stop|resume|runs|status|report <name>  # manage runs (ADR-232, ADR-249)
python reforge.py <path> --help        # same engine against any repo, no project registry (ADR-248)
python aikit.py idea-catcher status     # shipped tool over the private .idea-catcher/ register (ADR-246, ADR-252)
python aikit.py idea-catcher validate   # targets, ideas, dossiers and generated matrix; render --check
python aikit.py idea-catcher render --check  # fail when MATRIX.md is stale
python aikit.py idea-catcher review-idea IDEA-NNN --verdict defer --evidence "..."  # second defer blocks
python aikit.py idea-catcher sync --repo <path> --project <target>  # register delivered IDEA-NNN references and refresh MATRIX.md
```
- A second `defer` verdict in `review-idea` moves an idea to `Blocked`; blocked ideas are hidden
  from the default list and refuse every later review or status change (ADR-286).
- Reforge in one paragraph: window N is `start + step*(N-1)`, capped by `stop`; with no `--stop`, the run continues until the final window reaches the repository's complete commit history and then completes automatically. A stage inspects only the lines its own commits add and attributes each finding to the commit that introduced it. Five Python rules repair mechanically (`bare-except`, `mutable-default`, `shell-true`, `verify-false`, `unsafe-yaml-load`), each with a generated regression test; a line marked `hygiene: allow <reason>` is honoured, not reported; every other Python rule, every text check and every host finding is reported for a human, or applied only through a validated replacement. A red test or gate restores the exact bytes, and `--commit`/`--push` stage only reviewed paths plus `.aikit/reforge.json`, never forcing (in a project that file is committed memory; at AIKit's own root `.aikit/` is git-ignored tool state, so only reviewed paths are committed). Reforge may repair beside unrelated uncommitted work: those paths are snapshotted, never staged, and a commit is refused only when a finding's own target file was already dirty (`--allow-dirty` overrides). Python files use the AST detectors by default (`--no-rules` skips them) and every other changed text file uses `reforge/textdetect.py`, so only binary files print as `[SKIP] ... not analysed` instead of passing silently. `audit`/`run` write each new commit's own hunks, oldest to newest, to `.aikit/reforge.reviews/` with credential spans redacted; a later hunk may correct an earlier one, so findings must quote the current file. The main host model reviews each packet by default; subagents and external analyzers remain opt-in for explicitly delegated or specialized work. The host agent returns `path`, `line`, `severity`, `kind`, `message`, `evidence`, optional `commit`/`hunk`, an optional exact `fix`, and one `reviewed_hunks` object per packet hunk with its id, a verbatim quote of a line that hunk adds (or removes, for a deletion-only hunk) and a distinct note; an id-only list, a wrong quote or a repeated note is partial and never counts as a review, and answers are capped at 4 MiB with `method` recording host or analyzer (ADR-292), and any retained unreviewed stage blocks the next stage and run completion (`review --stage N --findings` records a historical review). `fix --findings answer.json` validates the answer against the stage (path, line, commit, hunk, current evidence, exact-once replacement, stage overlap, Python parse) and applies it. Each project has its own resolved lock and state, so projects audit in parallel while one project refuses a second run. Every run also appends `reforge:<run-id>` checkpoints to the repo's AIKit ledger without touching `active_task`, so `--resume` shows it; a plain checkout without a ledger is audited anyway. `reforge/` + `reforge.py` are the only source; the standalone repository is archived (ADR-263, ADR-266).
- A UI project is adopted by `fix` when it has a test command: it writes `.aikit/ui.json`, sets `ui_required`, and runs the project test command as its fast proof; without a test command it reports the gap instead of inventing one. A game/project may declare `mechanics.core` (existing paths) and `mechanics.test` in `.aikit/project.json`; `check` validates it and adds the mechanics command as a gate, so an agent and the UI exercise the same headless core.
