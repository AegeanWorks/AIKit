# AIKit Delegation: Sub-Agents and OpenCode

Read this before handing work to a sub-agent (PRINCIPLE-008 R6, PRINCIPLE-012 R8).

- **Claude Code**: hand bounded work to the project sub-agents in `.claude/agents/` through the Agent tool: `explorer` (searches, haiku), `worker` (docs and boilerplate, haiku), `architect` (read-only design), `reviewer` (audits, runs read-only gates), `tester` and `coder` (sonnet). Brief each with the milestone, the files it may change and the commands that verify it; run Phase 4 on what comes back.
- **Other hosts**: `python aikit.py delegate <role> "<brief>" [--project <name>]` runs the same role through OpenCode, on free models only: `architect` and `reviewer` on Gemini 3.8 Flash (needs `GEMINI_API_KEY` in the environment), the rest on OpenCode `-free` models (no key). A paid `--model` is refused (ADR-132).
- Roles have one text, `.opencode/agents/<role>.md`; `python scripts/sync_principles.py` regenerates the Claude copies. No agent can Edit or Write a task ledger (`.claude/settings.json`).

## Headless OpenCode Runs

Delegate bulk token-heavy work to free or local subagents using headless non-interactive mode:
```bash
# High-speed grep and symbol exploration
opencode run --standalone --format json --agent explorer "<query>"

# Architecture & deep reasoning (SWE-bench 49.2%)
opencode run --standalone --format json --agent architect "<prompt>"

# High-fidelity code refactoring (SWE-bench 39.8%)
opencode run --standalone --format json --agent coder --file <target> "<prompt>"

# Automated test creation and regression verification
opencode run --standalone --format json --agent tester --file <test_file> "<prompt>"

# Documentation, link and claim-fidelity audit
opencode run --standalone --format json --agent reviewer "<audit_prompt>"

# Offline / Air-gapped code generation via local Ollama
opencode run --standalone --format json --agent coder --model ollama/qwen2.5-coder:latest --auto "<prompt>"
```
*(Subagents MUST NOT write to the ledger; only the root orchestrator writes checkpoints).*
