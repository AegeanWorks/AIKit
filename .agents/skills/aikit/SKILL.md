---
name: aikit
description: >-
  Operational runbook and command matrix for AIKit (Universal AI Principles & Disruption Recovery).
  Use this skill whenever running test suites, verifying rule freshness, synchronizing principles,
  updating the AST codebase map and knowledge base, classifying change tracks, auditing or resuming disruption recovery,
  checkpointing tasks, scanning for secrets, verifying reachability, or executing dogfooding and pre-commit gates.
---

# AIKit Operational Runbook (Universal Host Integration)

This operational runbook provides the unified command matrix for driving AIKit across all supported agent host clients (Antigravity, Claude, OpenCode, Cursor, Copilot, Windsurf, Cline) under **PRINCIPLE-009 R7** (Pluggable Host Architecture) and **PRINCIPLE-017 R2** (Cross-IDE Synchronization).

---

## 🌐 Host Client Operation Matrix

- **Antigravity**: Native chat harness. Discovers this skill via `.agents/skills/aikit/SKILL.md` and rule files in `.agents/rules/`.
- **Claude (Code CLI / Desktop)**: Reads `CLAUDE.md` automatically on startup. Discovers this skill natively via `.claude/skills/aikit/SKILL.md`. Executes kit commands directly via terminal tool calls.
- **OpenCode**: Runs headless subagent profiles (`architect`, `coder`, `tester`, etc.) via `opencode run --standalone` and slash commands via `opencode.jsonc`.
- **Cursor / VS Code / Windsurf / Cline**: Loads `.cursorrules`, `.github/copilot-instructions.md`, `.windsurfrules`, `.clinerules`. Runs terminal commands.
- **State SSOT**: All clients interact with workspace state strictly through `python scripts/disruption_recovery.py` and `.agents/task_ledger.json` (a project's: `.aikit/task_ledger.json`).

---

## 🧱 Projects: Building Software Other Than AIKit (PRINCIPLE-011 R8)
The user's software lives in its own project, never in AIKit's tree. The full command matrix (`new`, `attach`, `check`, `license`, `publish`, `media`, `reforge`, `idea-catcher` and more) and the Reforge protocol are in `projects.md`; read it before project work.
- Request names no single project: ask which one, or the name of a new one, before writing code.
- Before writing code in a project, read its guidelines (`status` or `resume` prints them): its own rules, which add to the principles and never override one (PRINCIPLE-000 R6). When the user states a lasting rule for the project, record it with `aikit guideline`.
- In the steps below, project work replaces the repository with the project: use the cockpit subcommands above, or add `--workspace <project path>` to every `disruption_recovery.py` command, write ADRs in `<project>/.aikit/decisions.md`, stage and commit inside the project, and run `python aikit.py check <name>` as Phase 4. `aikit fix <name>` self-heals project memory and cleans temporary buffers. AIKit's other gates are for changes to AIKit only.
- The project check runs the built-in hygiene scan of its source and static assets: mark a deliberate finding `hygiene: allow <reason>` on its own line or the line directly above it. After the check passes, record the checklist outcome (`checklists: passed`, or the failed or skipped item IDs) in the task's latest checkpoint description before the commit (PRINCIPLE-001 R8, PRINCIPLE-011 R8).

---

## 🤝 Delegating to Sub-Agents (PRINCIPLE-008 R6, PRINCIPLE-012 R8)
Before delegating, read `delegation.md`: the Claude Code roles, `aikit delegate` on free models, headless OpenCode runs, and the rule that no sub-agent writes a task ledger.

## 🧭 Phase 1: Orientation & Cold-Start Recovery

### 1. Resume Interrupted Tasks
Run on session startup, cold starts, or after a context compaction:
```bash
python scripts/disruption_recovery.py --resume
```
- If an interrupted task is found, resume from its recommended phase.
- If uncommitted files or orphaned buffers exist, inspect them before proceeding.
- For a module overview in one read, run `python scripts/update_knowledge_base.py --digest [--workspace projects/<name>]` instead of opening the full codebase map.

### 2. Disruption Recovery Audit
Inspect the entire repository status, active task, and dangling temporary files:
```bash
python scripts/disruption_recovery.py --audit
```

### 3. Change Track Classification
Determine whether proposed edits require formal checklists:
```bash
python scripts/disruption_recovery.py --track
```
- **Track A**: Zero edits / read-only investigation.
- **Track B**: Documentation, comments, and non-rule markdown. Requires Post-Flight checklist and secret scan.
- **Track C**: Code, rules, workflows, or schemas. Full lifecycle verification required.

---

## 📋 Phase 2: Checkpointing & Planning (Track C Gate)

### 1. Pre-Flight Checklist
Review before making any code modifications on Track C tasks:
- Freshness: Read target files in slices before writing (PRINCIPLE-003 R1).
- Call Sites: Grep all symbol references across the repository before refactoring (PRINCIPLE-003 R2).
- Zero Undeclared Deps: Only use standard-library modules or explicitly declared dependencies (PRINCIPLE-003 R3).
- Platform Parity: Use `pathlib.Path` and avoid shell-specific builtins (PRINCIPLE-003 R4).

### 2. Record Micro-Milestones
Checkpoint plan with explicit impact assessment (`--why`, `--benefits`, `--risks`, `--mitigation`):
```bash
python scripts/disruption_recovery.py --checkpoint <task_id> --phase-num 2 --desc "[1/M] Planning and architectural design" --why "<motivation>" --benefits "<gains>" --risks "contract: ...; dependency: ...; concurrency: ...; state: ..." --mitigation "<strategy>"
```
- Bound milestone count to $M \le 6$ (PRINCIPLE-008 R3).
- Name yourself on every `--checkpoint`, `--complete` and `--reset`: `--agent <host>:<session>` (e.g. `kilo:2`) unless `AIKIT_AGENT` is set or you are Claude Code. A task another agent owns is refused (exit 1); continue it only with `--take-over` once that agent has stopped, and tell the user (PRINCIPLE-006 R7).

---

## 🛠️ Phase 3: Implementation & Synchronization

### 1. Synchronize Principles & IDE Instructions
After modifying `GUIDELINES.md` or `.agents/rules/domain.md`, update all 8 host client instruction files and README:
```bash
python scripts/sync_principles.py
```
- Verify zero budget violations (<1,750 tokens per target):
```bash
python scripts/sync_principles.py --check
```

### 2. Synchronize AST Codebase Map & Knowledge Base
After creating or refactoring symbols:
```bash
python scripts/update_knowledge_base.py
```
- Verify link integrity and codebase map freshness:
```bash
python scripts/update_knowledge_base.py --check
```

The headless OpenCode commands are in `delegation.md` (sub-agents never write the ledger).

---

## 🔒 Phase 4: Verification Gate Shield (Pre-Commit Delivery Triad)

Before committing any Track B or Track C changes, ALL gates must pass:

### 1. Test Suite Verification (100% Pass Required)
```bash
# Both tiers plus their per-test budgets (unit <=20ms, integration <=500ms)
python scripts/check_test_budgets.py

# Either tier on its own, when a failure needs isolating
python -m unittest tests.test_kit
python -m unittest tests.test_integration
```

### 2. Read-Only Quality Gates
```bash
# Rule and budget freshness check
python scripts/sync_principles.py --check

# AST and knowledge base check
python scripts/update_knowledge_base.py --check

# Pinned license/catalog drift check
python scripts/sync_licenses.py --check

# Secret and credential scan
python scripts/check_secrets.py --all

# Invariant reachability shield
python scripts/check_reachability.py

# Universal operational dogfooding runner
python scripts/dogfood.py
```

---

## 🚀 Phase 5: Delivery & Git Operations

> **Authorization gate**: run Phase 5 only when PRINCIPLE-018 R1 authorizes the commit or push; when it does not, stop after Phase 4 and report the uncommitted files.

### 1. Mark Task Completed
```bash
python scripts/disruption_recovery.py --complete <task_id>
```

### 2. Purge Dangling Temp Files
```bash
python scripts/disruption_recovery.py --clean
```

### 3. Conventional Commit Validation
```bash
python scripts/disruption_recovery.py --validate-commit "<type>(<scope>): <subject>"
```

### 4. Explicit Staging & Non-Destructive Recoil
```bash
# Stage modified files explicitly by name (NEVER git add .)
git add <file1> <file2> ...

# Commit
git commit -m "<type>(<scope>): <subject>"
```
