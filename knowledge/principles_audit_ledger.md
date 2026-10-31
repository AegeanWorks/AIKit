# AIKit Principles Comprehensive 7-Pass Audit Ledger 📑

> **Status: snapshot, not an evaluation (ADR-117).** This ledger was written at ADR-107 and is not kept current; `GUIDELINES.md` is the only source of the rules, several of which changed afterwards (ADR-108 to ADR-117). No model was run against the principles: every "Predicted cross-LLM behavior" line and the interpretability table at the end are the author's predictions, not measurements. Absolute claims such as "completely", "guarantees" or "airtight" are the author's wording, not verified properties.

> **Goal Authority**: Comprehensive 7-pass deep-dive analytical evaluation across all 20 principles (**PRINCIPLE-000** to **PRINCIPLE-019**).
> **Evaluation Dimensions**:
> 1. **Pass 1: Semantic Clarity & Cross-LLM Interpretability** (Do different models like Claude, GPT-4o, Gemini, DeepSeek, Qwen interpret it identically?)
> 2. **Pass 2: Strengths & Mechanical Invariants** (What parts are test-backed, bounded, and high-impact?)
> 3. **Pass 3: Weaknesses, Loopholes & Edge Cases** (Where can an agent satisfice, misinterpret, or find ambiguity?)
> 4. **Pass 4: Cross-Principle Alignment & Redundancies** (Inter-principle couplings, circular citations, and frictions)
> 5. **Pass 5: Operational Usability & Cognitive Ergonomics** (Session overhead, developer friction, and practical flow)
> 6. **Pass 6: Multi-Host / Multi-Client Portability** (Antigravity, Claude, OpenCode, Cursor, Copilot parity)
> 7. **Pass 7: Proposed Evolutions, Working Impact, Drawbacks & Gains** (Concrete evolution recommendations, working impact, drawbacks, and gains)

---

## 🏛️ Phase 1: Meta-Governance & Attentional Grounding

---

### 🔍 PRINCIPLE-000: Meta-Principle Integrity & Mutual Alignment (Code Quality Primacy)

#### Pass 1: Semantic Clarity & Cross-LLM Interpretability
- **Clarity Assessment**: Exceptional. The principle establishes an unambiguous definition of conflict ("at the same step, obeying one requires an action the other forbids, or forbids an action the other requires") and strict RFC 2119 keyword interpretations.
- **Predicted cross-LLM behavior (not measured)**: Frontier models (Claude 3.7 Sonnet, GPT-4o, Gemini 2.0) parse the 4-tier resolution hierarchy in R6 deterministically. Local and smaller open weights (Qwen2.5-Coder-7B) correctly follow the explicit rule citation precedence.
- **Semantic Risks**: Rule R4 references "When the agent judges that obeying a rule literally would make the code or its tests worse...". The term "worse" invites model-specific subjective aesthetic judgments unless explicitly anchored to measurable code quality metrics.

#### Pass 2: Strengths & Mechanical Invariants
- **Automated Verification Shield**: Rule R3 (`Cross-Principle Impact Verification Gate`) is mechanically enforced by `python scripts/sync_principles.py --check` and `sync_principles.py --citing`. Any guideline edit is blocked at pre-commit unless a corresponding ADR is recorded citing all affected principles.
- **Anti-Malicious Compliance (R5)**: Hardens AI execution against "satisficing"—prohibits vacuous assertions, stub constants written only to pass tests, and silent `except: pass` blocks.
- **Deterministic Conflict Hierarchy (R6)**: Tier 1 (`P019`, `P013`) $\rightarrow$ Tier 2 (`P003`, `P014`) $\rightarrow$ Tier 3 (`P000`, `P009`) $\rightarrow$ Tier 4 (`P001`, `P012`). Provides a mathematical topological sort for resolving rule collisions.

#### Pass 3: Weaknesses, Loopholes & Edge Cases
- **Same-Tier Collisions**: If two rules within the same hierarchy tier conflict and neither cites the other, R6 mandates stopping and asking the user. In fully autonomous, non-interactive execution modes (e.g. overnight `/goal` runs), this produces an unresolvable halt without an automated conservative fallback.
- **Subtle Semantic Drift**: A maintainer could edit rule text without changing principle IDs, subtly altering intent without triggering the grep anchor check if not meticulously reviewed.

#### Pass 4: Cross-Principle Alignment & Redundancies
- Seamlessly anchors all 19 other principles. Cites and is cited by `PRINCIPLE-001` (Progressive Disclosure), `PRINCIPLE-003` (Intent Ambiguity), `PRINCIPLE-004` (ADR Register), `PRINCIPLE-014` (Test Weakening), and `PRINCIPLE-019` (Secret Hygiene). Zero circular deadlocks detected.

#### Pass 5: Operational Usability & Cognitive Ergonomics
- High discipline barrier. Editing even a minor typographical error in `GUIDELINES.md` requires an ADR and cross-principle citing audit. While this maintains high governance rigor, it creates ceremony overhead for trivial prose touch-ups.

#### Pass 6: Multi-Host / Multi-Client Portability
- 100% portable. Evaluated identically in Google Antigravity, Claude Code, OpenCode CLI, and Cursor. Purely rules-based with zero host tool dependencies.

#### Pass 7: Proposed Evolutions, Working Impact, Drawbacks & Gains
- **Proposed Change**: Clarify R4's "make code worse" with objective, falsifiable criteria: cyclomatic complexity increase $> 5$, test execution time increase $> 200$ms, or duplicate block length $> 15$ lines.
- **Working Impact on AIKit**: Prevents divergent model judgments on code craftsmanship; provides uniform stopping criteria across Claude, Gemini, and Qwen.
- **Drawbacks**: Adds approximately 180 characters to `PRINCIPLE-000 R4`.
- **Gains**: Completely closes the subjective interpretation loophole for craftsmanship doubts.

---

### 🔍 PRINCIPLE-001: Progressive Rule Disclosure & Governance Frugality (Zero Instruction Bloat)

#### Pass 1: Semantic Clarity & Cross-LLM Interpretability
- **Clarity Assessment**: High precision. The Two-Tier architecture is cleanly partitioned: Tier 1 (always injected, strict $\le$ 1,600 estimated tokens) vs. Tier 2 (on-demand deep rationale in `GUIDELINES.md` and `knowledge/`).
- **Predicted cross-LLM behavior (not measured)**: The three retrieval triggers in R3 (Contract-Change, Failure, Ambiguity) are universally recognizable by all modern LLMs. Models reliably recognize when a public function signature, CLI flag, or schema field changes.
- **Semantic Risks**: In R3, "reading every principle section one after another counts as loading it in full". Models with massive context windows (1M+ tokens) naturally tend to read large swaths of files; this restriction must remain explicitly stated to prevent prompt pollution.

#### Pass 2: Strengths & Mechanical Invariants
- **Token Budget Gate (R6)**: Hard gate enforcing `estimate_tokens = len(text) // 4 <= 1600` for every generated Tier 1 file. Automatically checked by `sync_principles.py --check` and validated in unit tests.
- **Deletion Test (R2)**: Self-sufficient invariant capsules must pass a deletion test: any phrase whose removal loses no command, path, number, or named gate must be removed.
- **Hand-Edit Protection (R1)**: `GENERATED_MARKERS` ensure that `sync_principles.py` never overwrites hand-authored developer instructions.

#### Pass 3: Weaknesses, Loopholes & Edge Cases
- **Manual Grep Reliance**: R5 requires agents to use text-search tools for `### PRINCIPLE-NNN:` rather than line numbers. While effective, an agent with poor search tools might retrieve incomplete slices if the terminating delimiter is miscalculated.
- **Tier 1B Headroom Contention**: As universal principles in Tier 1A expand, they compress the 300-token headroom reserved for project-specific domain rules in Tier 1B.

#### Pass 4: Cross-Principle Alignment & Redundancies
- Directly interlocks with `PRINCIPLE-017` (which executes the cross-IDE generation) and `PRINCIPLE-012` (Token Frugality). R8 governs Pre-Flight and Post-Flight checklist execution, bridging planning and delivery.

#### Pass 5: Operational Usability & Cognitive Ergonomics
- Outstanding token efficiency. Preserves ~90% of prompt context for user code compared to monolithic rule systems (which typically consume 15,000–30,000 prompt tokens on turn 1).

#### Pass 6: Multi-Host / Multi-Client Portability
- The foundation of AIKit's multi-host portability. Generates native instruction files for Antigravity (`AGENTS.md`, `GEMINI.md`, `principles.md`), Claude (`CLAUDE.md`), Cursor (`.cursorrules`), and GitHub Copilot (`.github/copilot-instructions.md`).

#### Pass 7: Proposed Evolutions, Working Impact, Drawbacks & Gains
- **Proposed Change**: Add a programmatic retrieval CLI command: `python scripts/sync_principles.py --read PRINCIPLE-NNN`, which prints exactly that principle's section to stdout.
- **Working Impact on AIKit**: Allows agents in any terminal environment (Antigravity, Claude Code, OpenCode) to read exact principle slices with a single command without computing line slices.
- **Drawbacks**: Adds ~15 lines to `scripts/sync_principles.py`.
- **Gains**: Guarantees zero line-drift or slicing errors across diverse agent toolsets.

---

### 🔍 PRINCIPLE-002: Lifecycle-Aligned Instruction Ordering & Attentional Priming (Cognitive Flow Invariant)

#### Pass 1: Semantic Clarity & Cross-LLM Interpretability
- **Clarity Assessment**: Crystal clear. Decomposes tasks into 5 lock-step phases: Grounding $\rightarrow$ Planning $\rightarrow$ Implementation $\rightarrow$ Verification $\rightarrow$ Delivery.
- **Predicted cross-LLM behavior (not measured)**: Models adhere strictly to the sequence when prompted with phase names. The 3-track definition in R3 (Track A: query, Track B: docs, Track C: code/config/schemas) eliminates guessing.
- **Semantic Risks**: In R1, the distinction between "phase entered" and "phase finished" is subtle: a recorded checkpoint denotes entering a phase, meaning an interrupted agent resumes *inside* that phase.

#### Pass 2: Strengths & Mechanical Invariants
- **Objective Track Computation**: Track classification is not left to agent judgment; `python scripts/disruption_recovery.py --track` inspects `git status --porcelain -z` and AST syntax trees to compute Track A, B, or C objectively.
- **Verification Lock (R1)**: Commits and pushes are strictly locked until all Phase 4 commands pass on the exact working tree being delivered. Any edit after Phase 4 invalidates verification.
- **Immunity to User Priming (R5)**: Forbids skipping verification gates even when the user urges "push immediately" or "skip tests", directly mitigating conversational sycophancy.

#### Pass 3: Weaknesses, Loopholes & Edge Cases
- **Silent Escalation Drift**: If an agent starts a task predicting Track B (doc edit) but inadvertently touches code, it escalates to Track C. R3 mandates re-checking `--track` before committing and completing skipped phases, but an agent bypassing `--track` could prematurely commit.
- **Unverified Override Audit**: R5 permits delivering unverified code only upon explicit user override with a commit message ending in `Unverified: <gates>`. If the agent fails to format this line correctly, git history loses visibility of skipped gates.

#### Pass 4: Cross-Principle Alignment & Redundancies
- Serves as the cognitive backbone linking `PRINCIPLE-004` (Compaction Resumption), `PRINCIPLE-006` (Atomic Checkpointing), `PRINCIPLE-007` (Pre-Flight Impact Assessment), `PRINCIPLE-014` (Automated Tests), and `PRINCIPLE-018` (Git Delivery).

#### Pass 5: Operational Usability & Cognitive Ergonomics
- Adaptive pathing spares developers and agents unnecessary ceremony on trivial questions (Track A) or documentation fixes (Track B), saving time and tokens.

#### Pass 6: Multi-Host / Multi-Client Portability
- Fully portable. All life-cycle commands (`--track`, `--checkpoint`, `--resume`, `--complete`) are pure standard-library Python commands executable across all OS and host environments.

#### Pass 7: Proposed Evolutions, Working Impact, Drawbacks & Gains
- **Proposed Change**: In `scripts/disruption_recovery.py --validate-commit`, automatically inspect whether `--track` indicates Track C changes while Phase 2 impact checkpoints are missing from the ledger.
- **Working Impact on AIKit**: Mechanically guarantees that Track C tasks cannot commit without an impact assessment checkpoint, even if the agent forgot to evaluate `--track`.
- **Drawbacks**: Adds minor validation logic to commit validation script (~20 lines).
- **Gains**: Closes the silent escalation loophole entirely.

---

### 🔍 PRINCIPLE-003: Empirical Grounding & Anti-Hallucination Invariant (Verify-Before-Execution)

#### Pass 1: Semantic Clarity & Cross-LLM Interpretability
- **Clarity Assessment**: Exceptional. Mandates "Read-Before-Write" slice freshness, manifest-backed dependency reality, and bi-directional contract parity.
- **Predicted cross-LLM behavior (not measured)**: The distinction in R6 between *Runtime Ambiguity* (handled by running code with defaults/errors) and *Intent Ambiguity* (handled by the agent asking the user) is one of the most effective guardrails across all LLM architectures.
- **Semantic Risks**: R4 requires using the launcher and shell reported by the active environment. On Windows environments with multiple Python installations (`py` vs `python`), models can occasionally trigger process execution errors if they copy Linux `python3` invocations.

#### Pass 2: Strengths & Mechanical Invariants
- **Strict AST Syntax Gate (R7)**: `python scripts/update_knowledge_base.py` parses all Python files with the grammar of `MIN_PYTHON` (Python 3.10), blocking syntax introduced in newer runtimes.
- **Whole-Word Grep Anchor (R2)**: Mandates `git grep -n -w -e <name>` (requiring `-e` to avoid option confusion) across all tracked files before renaming or deleting symbols.
- **Invariant Reachability Shield**: Checked by `python scripts/check_reachability.py` to prevent orphaned dead code or hallucinated function signatures.

#### Pass 3: Weaknesses, Loopholes & Edge Cases
- **Stale Memory Drift**: If an agent reads a file, plans for several turns, and another process or subagent modifies that file, the agent's slice is stale. R1 strictly forbids writing without re-reading, but enforcing this relies on agent compliance unless verified by file mtime checks.
- **Multi-Language Manifest Gaps**: In polyglot repositories without standard manifests, dependency reality falls back to `README.md` `Runtime Prerequisites`, which requires continuous manual curation.

#### Pass 4: Cross-Principle Alignment & Redundancies
- Closely coupled with `PRINCIPLE-004` (AST map navigation), `PRINCIPLE-011` (error diagnostic triad), `PRINCIPLE-014` (reachability shield), and `PRINCIPLE-016` (codebase map freshness).

#### Pass 5: Operational Usability & Cognitive Ergonomics
- Eliminates the single largest category of autonomous AI defects: hallucinated imports and stale symbol calls. Slightly increases tool call count prior to edits, but saves immense debugging time.

#### Pass 6: Multi-Host / Multi-Client Portability
- Enforces strict cross-platform parity: `pathlib.Path`, `sys.executable`, list subprocess arguments without `shell=True`, and `sys.platform` branching.

#### Pass 7: Proposed Evolutions, Working Impact, Drawbacks & Gains
- **Proposed Change**: Explicitly codify in R4 that on Windows PowerShell/CMD, if launcher permission errors occur (e.g. sandboxed access denial to `py`), the agent must resolve `sys.executable` or execute via direct binary path.
- **Working Impact on AIKit**: Streamlines execution across diverse sandboxed Windows environments.
- **Drawbacks**: None; purely clarifying.
- **Gains**: Prevents intermittent subagent execution hangs on Windows.

---

### 🔍 PRINCIPLE-004: Attentional Drift Prevention & Compaction Resilience (Context Anchor Protocol)

#### Pass 1: Semantic Clarity & Cross-LLM Interpretability
- **Clarity Assessment**: High. Establishes that chat is transient progress and disk files are persistent state ("Chat holds progress, not state").
- **Predicted cross-LLM behavior (not measured)**: Models reliably identify the active living plan by searching for the latest `--phase-num 2` checkpoint starting with `[1/`.
- **Semantic Risks**: The rule that intermediate messages must be $\le 15$ lines can cause models to artificially truncate necessary diagnostic logs or error traces unless clarified.

#### Pass 2: Strengths & Mechanical Invariants
- **Rolling Ledger Bounding (R1)**: `scripts/disruption_recovery.py` bounds the ledger to at most 20 checkpoints while preserving the active plan, preventing unbounded state file growth.
- **Slice-Capped Tool Output (R3 & R5)**: Caps single tool output to 100 lines and searches to 50 matches. Directly prevents token context exhaustion.
- **Compaction Resumption & Anti-Repetition (R2)**: On cold start or compaction, running `--resume` immediately restores recommended phase and prevents asking previously answered questions.

#### Pass 3: Weaknesses, Loopholes & Edge Cases
- **Mega-File Overwrite Friction**: To overwrite a 400-line file, an agent must read it in 100-line slices (4 tool calls) to satisfy R3 and P003 R1 before writing. While safe, this creates turn latency for routine file rewrites.
- **Subagent Ledger Contamination**: If a subagent attempts to record checkpoints, it corrupts the parent task's state. (Mitigated by PRINCIPLE-008 R6 and permission denials).

#### Pass 4: Cross-Principle Alignment & Redundancies
- Bridges `PRINCIPLE-002` (lifecycle phase resumption), `PRINCIPLE-006` (checkpoint structure), `PRINCIPLE-008` (milestone decomposition), and `PRINCIPLE-016` (ADR monotonicity).

#### Pass 5: Operational Usability & Cognitive Ergonomics
- Exceptional resilience against context compaction. Long sessions that would completely derail standard coding assistants continue seamlessly in AIKit because all critical state lives on disk.

#### Pass 6: Multi-Host / Multi-Client Portability
- 100% portable. Relies exclusively on JSON WAL files (`.agents/task_ledger.json`) and Markdown documents (`knowledge/decisions.md`).

#### Pass 7: Proposed Evolutions, Working Impact, Drawbacks & Gains
- **Proposed Change**: Explicitly exempt structured machine-generated diagnostics (for instance, test failure traces or JSON lint reports) from the 15-line conversational message cap, subject only to the 100-line tool output ceiling.
- **Working Impact on AIKit**: Allows agents to display full error tracebacks without awkward manual splitting.
- **Drawbacks**: Slightly longer intermediate conversational turns.
- **Gains**: Significantly improved diagnostic transparency during Phase 4 verification.

---

## 🧭 Phase 2: Pre-Flight Orientation & Planning

---

### 🔍 PRINCIPLE-005: AI Cold-Start Readiness & Living Documentation (README Sync)

#### Pass 1: Semantic Clarity & Cross-LLM Interpretability
- **Clarity Assessment**: Exceptional clarity. The SSOT triad cleanly separates duties: `README.md` for human users, `GUIDELINES.md` for AI agent instructions, and `knowledge/` for deep architectural logic and schemas.
- **Predicted cross-LLM behavior (not measured)**: Modern frontier LLMs (Claude 3.7 Sonnet, GPT-4o, Gemini 2.0) easily interpret the mandatory sections (`Cold-Start Quick Reference`, `What's Inside`, `Canonical Regression Shield Gate`). Smaller models correctly parse the strict 20,000 character limit.
- **Semantic Risks**: Rule R2 lists triggers that force a README update. While specific, an LLM might question whether adding an internal private helper function to an existing script counts as changing "what a command documented in README checks, writes or prints". The principle clarifies this covers user-observable output, but explicitly defining "user-observable" prevents edge-case churn.

#### Pass 2: Strengths & Mechanical Invariants
- **Character Budget Hard Gate (R1)**: Hard ceiling of <= 20,000 characters for `README.md`, mechanically enforced by `python scripts/update_knowledge_base.py --check`. This mathematically guarantees that initial turn context consumption remains < 5,000 tokens across all model tokenizers.
- **Whole-Tree Drift Shield (R5)**: The ASCII directory tree under `What's Inside` is strictly compared against `git ls-files`. Any new, renamed, or deleted tracked file in a non-collapsed directory fails the check automatically.
- **Executable Command Parity (R3)**: Every script flag and unittest module cited in `README.md` is verified against actual codebase existence.

#### Pass 3: Weaknesses, Loopholes & Edge Cases
- **Polyglot Parsing Limit (R6)**: `update_knowledge_base.py --check` natively verifies `python scripts/...` and `python -m unittest` commands, but relies on agent run-before-documenting honor code for non-Python toolchains (such as `npm test` or `cargo build`).
- **Collapsed Directory Ambiguity**: Rule R5 allows collapsing directories with zero children shown, but does not define criteria for when a directory must be collapsed versus expanded, leading to stylistic variance across different models.

#### Pass 4: Cross-Principle Alignment & Redundancies
- Seamlessly aligns with `PRINCIPLE-001` (Progressive Disclosure), `PRINCIPLE-016` (Knowledge Base SSOT), and `PRINCIPLE-017` (Automated Rule Generation). The automated table generation between `<!-- principles:begin -->` and `<!-- principles:end -->` ensures zero duplicate maintenance.

#### Pass 5: Operational Usability & Cognitive Ergonomics
- Drastically reduces developer and agent ramp-up time. A fresh agent turn 1 requires only scanning the Quick Reference block (approximately 350 tokens) to immediately execute the test suite and verify environment health.

#### Pass 6: Multi-Host / Multi-Client Portability
- 100% host agnostic. Read identically by Antigravity, Claude Code, Cursor, Copilot, and human terminal users via `cat README.md` or web renderers.

#### Pass 7: Proposed Evolutions, Working Impact, Drawbacks & Gains
- **Proposed Change**: Extend `update_knowledge_base.py --check` to include a rudimentary regex validator for foreign shell commands in the Quick Reference block (verifying binary availability via `shutil.which`).
- **Working Impact on AIKit**: Increases confidence in multi-stack polyglot repositories without breaking zero-dependency rules.
- **Drawbacks**: Adds approximately 25 lines to `scripts/update_knowledge_base.py`.
- **Gains**: Completely prevents rotting quickstart commands in polyglot projects.

---

### 🔍 PRINCIPLE-006: Incremental Progress Checkpointing & Disruption Recovery (Zero-Progress-Loss Workflow)

#### Pass 1: Semantic Clarity & Cross-LLM Interpretability
- **Clarity Assessment**: High precision. The principle eliminates ambiguity around when to commit by binding conventional micro-commits directly to plan milestone completions.
- **Predicted cross-LLM behavior (not measured)**: All evaluated models (Claude, GPT, Gemini, DeepSeek, Qwen) understand the micro-commit format: `type(scope): [milestone N/M] <description>`.
- **Semantic Risks**: Rule R1 states "MUST NOT start milestone N+1 while milestone N is finished but uncommitted". LLMs executing parallel tool calls or generating multi-file changes might unintentionally edit files slated for milestone N+1 before committing milestone N unless explicitly gated by their internal execution loop.

#### Pass 2: Strengths & Mechanical Invariants
- **Commit Validation Gate (R1)**: Enforced via `python scripts/disruption_recovery.py --validate-commit`, which rejects tags outside 1 <= N <= M, 2 <= M <= 6 and blocks milestone commits with missing tags.
- **Atomic File Writing (R3)**: Enforces WAL staging with advisory locking and `os.replace` (backed by `PRINCIPLE-013 R1`) for all ledger mutations, ensuring crash survivability even during sudden power loss.
- **Dangling Buffer Hygiene (R6)**: Enforces cleaning stale `*.tmp_*` buffers older than 60 seconds via `scripts/disruption_recovery.py --clean`.

#### Pass 3: Weaknesses, Loopholes & Edge Cases
- **Uncommitted Failure Accumulation**: R4 states that failing work stays uncommitted in the working tree and is described in `--checkpoint --desc`. If an agent crashes while in a broken intermediate state, the next agent might mistake broken uncommitted changes for user-intentional work unless `--resume` clearly highlights the failure context.
- **60-Second Buffer Grace Period**: In exceptionally slow virtual environments or network mounts, an active write buffer older than 60 seconds could theoretically be flagged as stale if file timestamps drift.

#### Pass 4: Cross-Principle Alignment & Redundancies
- Directly couples with `PRINCIPLE-002` (Lifecycle Phases), `PRINCIPLE-004` (Task Ledger Invariants), `PRINCIPLE-008` (Milestone Horizon), `PRINCIPLE-013` (Atomic I/O), and `PRINCIPLE-018` (Git Delivery). Zero conflicting directives.

#### Pass 5: Operational Usability & Cognitive Ergonomics
- Prevents the catastrophic scenario where an agent executes a 6-milestone refactor, hits a turn limit or crash on milestone 5, and loses all work. Each completed milestone is securely committed and replayable.

#### Pass 6: Multi-Host / Multi-Client Portability
- Native Git and standard Python implementation. Operates flawlessly whether triggered via Antigravity bash tools, Claude Code bash execution, or standard command-line shells.

#### Pass 7: Proposed Evolutions, Working Impact, Drawbacks & Gains
- **Proposed Change**: In `scripts/disruption_recovery.py --checkpoint`, add an explicit `--status (in-progress|failing|blocked)` flag to checkpoints so recovery agents immediately know if the uncommitted tree was left in a failing test state.
- **Working Impact on AIKit**: Gives resuming agents immediate clarity on whether the working tree compiles and passes tests before attempting Phase 3 resumption.
- **Drawbacks**: Adds one optional CLI argument to `scripts/disruption_recovery.py`.
- **Gains**: Enhances cold-start disruption recovery fidelity across heterogeneous AI agents.

---

### 🔍 PRINCIPLE-007: Pre-flight Impact & Quality Checklist (Cold-Start Gate)

#### Pass 1: Semantic Clarity & Cross-LLM Interpretability
- **Clarity Assessment**: Crystal clear. Establishes a mandatory 4-dimension blast-radius taxonomy: `contract:`, `dependency:`, `concurrency:`, and `state:`.
- **Predicted cross-LLM behavior (not measured)**: Models reliably output the structured format required by `--risks "contract: ...; dependency: ...; concurrency: ...; state: ..."`.
- **Semantic Risks**: The prohibition against speculative over-engineering (Scope Ceiling in R4) can be interpreted with varying degrees of strictness by different models. Grounding scope strictly to the recorded plan milestones eliminates subjectivity.

#### Pass 2: Strengths & Mechanical Invariants
- **Machine-Gated Assessment (R6)**: `python scripts/disruption_recovery.py --checkpoint` strictly requires `--why`, `--benefits`, `--risks`, and `--mitigation` on the initial Phase 2 checkpoint, exiting with status code 2 if any field or risk dimension is omitted.
- **Anti-Satisficing Code Gate (R3)**: Mechanically verified by `python scripts/update_knowledge_base.py`, which rejects `TODO`, `FIXME`, `XXX`, `HACK`, hollow stubs (`pass`, `...`), and uncodified `# type: ignore` / `# noqa` annotations.
- **Rollback Preparedness (R5)**: Requires reporting pre-existing dirty working tree state before the first file edit, ensuring non-destructive recoil back to the base commit.

#### Pass 3: Weaknesses, Loopholes & Edge Cases
- **Vacuous Risk Verdicts**: An agent can technically satisfy the gate by passing `--risks "contract: none; dependency: none; concurrency: none; state: none" --mitigation "none"` without conducting genuine analysis. While prohibited by PRINCIPLE-000 R5 (Anti-Malicious Compliance), detection currently relies on model integrity.
- **Scope Creep via Refactoring**: An agent fixing a minor bug might be tempted to clean up adjacent functions under the guise of good craftsmanship, violating R4 unless tied to a recorded milestone.

#### Pass 4: Cross-Principle Alignment & Redundancies
- Directly interlocks with `PRINCIPLE-000` (Anti-Malicious Compliance), `PRINCIPLE-002` (Track C Trigger), `PRINCIPLE-008` (Milestones), and `PRINCIPLE-018` (Recoil Safety).

#### Pass 5: Operational Usability & Cognitive Ergonomics
- Enforces deliberate planning before writing code. Requires a single command at Phase 2, introducing negligible token and time overhead while preventing high-cost architectural regressions.

#### Pass 6: Multi-Host / Multi-Client Portability
- Uniformly enforced across all hosts through the Python CLI runner. Does not rely on host-specific IDE extension APIs.

#### Pass 7: Proposed Evolutions, Working Impact, Drawbacks & Gains
- **Proposed Change**: Add an automated heuristic check in `disruption_recovery.py` that warns when all four blast-radius dimensions are marked `none` on tasks modifying more than 3 files.
- **Working Impact on AIKit**: Prompts agents to double-check their impact assumptions on non-trivial architectural changes.
- **Drawbacks**: May produce false-positive warnings on multi-file text or documentation refactors.
- **Gains**: Closes the vacuous assessment shortcut on complex code modifications.

---

### 🔍 PRINCIPLE-008: Hierarchical Problem & Task Decomposition

#### Pass 1: Semantic Clarity & Cross-LLM Interpretability
- **Clarity Assessment**: Exceptional. Mandates Top-Down Decomposition, Bottom-Up Execution, bounded milestone horizons (1 <= M <= 6), and single-domain leaf atomicity.
- **Predicted cross-LLM behavior (not measured)**: The rule that "no milestone may use a class, function, flag or file that a later milestone creates" is universally understood by LLMs, guiding foundation-first dependency ordering.
- **Semantic Risks**: Rule R4 requires that a milestone change one architectural layer (from PRINCIPLE-009). If an AI does not inspect PRINCIPLE-009's 4 layers (Interface, Logic, Port, Adapter), it may decompose by arbitrary file groupings instead of architectural boundaries.

#### Pass 2: Strengths & Mechanical Invariants
- **Bounded Milestone Horizon (R3)**: Hard invariant of at most 6 milestones per task (M <= 6). Plans requiring more than 6 milestones must be split into separate tasks, preventing runaway multi-day unverified state accumulation.
- **Subagent Concurrency Shield (R6)**: Subagents are strictly forbidden from writing to `.agents/task_ledger.json`. They must execute non-interactively with closed stdin and return diffs or findings to the parent agent, guaranteeing single-writer consistency.
- **Recursion Depth Cap (R1)**: Caps subagent hierarchy depth to at most 3 levels and input briefs to <= 50 files or records, mathematically preventing token explosions and runaway agent loops.

#### Pass 3: Weaknesses, Loopholes & Edge Cases
- **Dynamic Re-Plan Churn**: When an in-flight milestone reveals unexpected complexity, R5 mandates recording a new `[1/M']` checkpoint. If an agent encounters repeated surprises, frequent re-planning can consume turns without making implementation progress.
- **Subagent Verification Responsibility**: If a parent agent blindly accepts a subagent's diff without running Phase 4 gates (violating R6), regressions could slip into staged commits.

#### Pass 4: Cross-Principle Alignment & Redundancies
- Directly anchors `PRINCIPLE-004` (Living Plan SSOT), `PRINCIPLE-006` (Milestone Commits), `PRINCIPLE-007` (Scope Ceiling), `PRINCIPLE-009` (Layered Decomposition), and `PRINCIPLE-012` (Token Limits).

#### Pass 5: Operational Usability & Cognitive Ergonomics
- Decomposing tasks into 2 to 6 verifiable milestones provides clear psychological checkpoints for human supervisors and provides an infallible audit trail for disrupted AI sessions.

#### Pass 6: Multi-Host / Multi-Client Portability
- Works uniformly across single-agent and multi-agent harnesses (such as Antigravity subagents, Claude Code subagents, OpenCode background tasks).

#### Pass 7: Proposed Evolutions, Working Impact, Drawbacks & Gains
- **Proposed Change**: Formally standardize the subagent return payload schema in `knowledge/data_models.md` as a structured JSON object (`status`, `deliverables`, `findings`, `failed_checks`) to eliminate variability in subagent report parsing.
- **Working Impact on AIKit**: Streamlines multi-agent orchestration and makes subagent verification deterministic.
- **Drawbacks**: Requires subagents to format responses according to the JSON schema.
- **Gains**: Guarantees zero parsing ambiguities across heterogeneous subagent models (for instance, parent Claude calling subagent Qwen).

---

## 🏗️ Phase 3: Architecture & Lean Implementation

---

### 🔍 PRINCIPLE-009: Modularity & Pluggable Architecture

#### Pass 1: Semantic Clarity & Cross-LLM Interpretability
- **Clarity Assessment**: Exceptional. Provides an unambiguous definition of a pluggable boundary ("a role with two or more production implementations in the repository or in the recorded plan"). It establishes the canonical 4-layer taxonomy: Presentation, Service, Domain, Adapter.
- **Predicted cross-LLM behavior (not measured)**: Frontier models (Claude, GPT-4o, Gemini) strictly respect the prohibited junk-drawer names (`utils`, `util`, `helpers`, `helper`, `common`, `misc`) and the 1-to-5 method role protocol invariant. Smaller models correctly follow constructor injection with default fallbacks (`self._adapter = adapter or DefaultAdapter()`).
- **Semantic Risks**: Rule R1 allows the four layers to share one module if under 300 lines. Some models might prematurely split a simple 150-line utility into 4 separate files, introducing unnecessary boilerplate unless guided by the 300-line threshold.

#### Pass 2: Strengths & Mechanical Invariants
- **Static Gate Enforcement (R1 & R5)**: `python scripts/update_knowledge_base.py` AST parser mechanically scans all modules for forbidden junk-drawer names, role interfaces exceeding 5 methods, and circular module import graphs.
- **Pluggable Provider Lifecycle (R6)**: Enforces a 5-step lifecycle for integrating external AI providers (declarative configuration in `opencode.jsonc`, environment-variable credentials per P019, non-interactive execution with timeouts per P010/P011, `.agents/**` write-isolation per P008, and ground-truth benchmark metrics in `knowledge/model_benchmarks.md`).
- **Pluggable Host Architecture (R7)**: Decouples core kit logic from proprietary host IDEs. Enforces instruction projection (P017), skill parity, and unified disruption state through `.agents/task_ledger.json`.

#### Pass 3: Weaknesses, Loopholes & Edge Cases
- **Layering Boundary Bleed**: In scripts hovering around 280-320 lines, agents frequently waffle between keeping all four layers in a single file versus splitting into four modules, resulting in file structure churn.
- **Subagent Benchmark Freshness**: While R6 mandates recording ground-truth benchmark scores from public leaderboards, model capabilities evolve rapidly; benchmarks must be dated and version-tagged to prevent obsolescence.

#### Pass 4: Cross-Principle Alignment & Redundancies
- Cohesively ties together `PRINCIPLE-003` (zero undeclared dependencies), `PRINCIPLE-008` (single-domain leaf atomicity), `PRINCIPLE-010` (pure stdlib speed), `PRINCIPLE-011` (zero-config constructor DI), `PRINCIPLE-017` (instruction projection), and `PRINCIPLE-019` (credential hygiene).

#### Pass 5: Operational Usability & Cognitive Ergonomics
- Prevents spaghetti architecture without forcing enterprise micro-framework overhead. The pure standard-library constructor injection pattern enables unit testing with lightweight test doubles without requiring third-party mocking libraries or DI containers.

#### Pass 6: Multi-Host / Multi-Client Portability
- Specifically engineered for universal host neutrality. Whether hosted in Google Antigravity, Claude Code, OpenCode CLI, Cursor, or GitHub Copilot, the identical Python modules and recovery contracts execute without modification.

#### Pass 7: Proposed Evolutions, Working Impact, Drawbacks & Gains
- **Proposed Change**: Add an automated check in `scripts/update_knowledge_base.py` that verifies that any provider declared in `opencode.jsonc` has an entry with context window and benchmark ratings in `knowledge/model_benchmarks.md`.
- **Working Impact on AIKit**: Mathematically binds external provider declarations to ground-truth benchmark documentation.
- **Drawbacks**: Adds approximately 30 lines of JSON/Markdown cross-validation logic.
- **Gains**: Guarantees zero unverified model additions across provider configurations.

---

### 🔍 PRINCIPLE-010: Performance & Resource Optimization (Speed & Lean Architecture)

#### Pass 1: Semantic Clarity & Cross-LLM Interpretability
- **Clarity Assessment**: Outstanding mathematical precision. Replaces vague directives like "make it fast" with explicit, falsifiable numeric ceilings: loop lookup in $O(1)$ set/dict, threads only for operations taking >= 200ms, subprocess calls gated by timeouts, `--help` in < 200ms, unit test suite < 1s, integration suite < 5s.
- **Predicted cross-LLM behavior (not measured)**: All evaluated LLMs parse the explicit millisecond and second thresholds accurately. Models consistently add `timeout=` to subprocess invocations when instructed by this principle.
- **Semantic Risks**: Rule R1 distinguishes between "uncontrolled input" (must be streamed or read incrementally) and "bounded files" (rule files, ledger) that may be read whole. An LLM might occasionally over-engineer streaming readers for small, bounded config files.

#### Pass 2: Strengths & Mechanical Invariants
- **Subprocess Timeout Gate (R3)**: `scripts/update_knowledge_base.py` uses AST inspection to verify that every `subprocess.run`, `call`, `check_call`, and `check_output` specifies a non-zero `timeout=`. Missing timeouts cause immediate gate failure.
- **Context Manager File I/O (R4)**: Mechanically verified by AST inspection; raw `open()` or `Path.open()` outside of a `with` statement fails validation.
- **Speed Gates (R5 & R6)**: Measured automatically during verification: `--help` startup budget (< 200ms) verified by `scripts/dogfood.py`, and unit test suite (< 1s) verified during Phase 4 test execution.

#### Pass 3: Weaknesses, Loopholes & Edge Cases
- **Hardware Variance Flapping**: The sub-second (< 1s) unit test and < 5s integration test thresholds can flap when executed on heavily loaded or constrained continuous integration (CI) runners. AIKit handles this by requiring unit tests to spawn zero processes and execute zero `time.sleep` calls.
- **Popen Timeout Handling**: While `subprocess.run` has native `timeout=`, `subprocess.Popen` requires manual handling via `.wait(timeout=...)` or `.communicate(timeout=...)`. An agent could forget the timeout on a custom streaming Popen loop if not careful.

#### Pass 4: Cross-Principle Alignment & Redundancies
- Directly reinforces `PRINCIPLE-003` (deterministic execution), `PRINCIPLE-011` (headless non-blocking execution), `PRINCIPLE-013` (batch I/O coalescing with single `os.fsync`), and `PRINCIPLE-014` (test timing tiers).

#### Pass 5: Operational Usability & Cognitive Ergonomics
- Ensures that developer and agent workflows remain blisteringly fast. A full unit test pass taking < 1 second encourages continuous local test verification after every code edit without context switching delay.

#### Pass 6: Multi-Host / Multi-Client Portability
- Cross-platform portability is preserved by using standard Python concurrency primitives (`asyncio`, `concurrent.futures`, `os.cpu_count()`) rather than platform-specific multiprocessing forks or Unix-only signals.

#### Pass 7: Proposed Evolutions, Working Impact, Drawbacks & Gains
- **Proposed Change**: Add a CPU-frequency normalization factor or a 1.5x margin of tolerance for `tests.test_integration` when running inside resource-constrained containerized sandboxes.
- **Working Impact on AIKit**: Prevents flaky gate failures in noisy cloud runner environments while preserving strict execution discipline on local machines.
- **Drawbacks**: Adds minor timing adjustment logic in integration runners.
- **Gains**: Eliminates false-positive performance gate breaks in slow virtualized environments.

---

### 🔍 PRINCIPLE-011: Zero-Friction Onboarding & Instant Usability (One-Click Start)

#### Pass 1: Semantic Clarity & Cross-LLM Interpretability
- **Clarity Assessment**: Exceptional. The invariant establishes a pure-standard-library clone-and-run baseline, automatic directory provisioning (`mkdir(parents=True, exist_ok=True)`), safe environment reads (`os.getenv()` with default), deterministic exit codes (0/1/2), and the Actionable Remediation Triad.
- **Predicted cross-LLM behavior (not measured)**: Models reliably implement the Actionable Remediation Triad:
  1. What failed
  2. `Why:` <root cause>
  3. `Fix:` <exact resolving command>
- **Semantic Risks**: Rule R5 specifies deterministic exit codes: 0 for success, 1 for operational failure, and 2 for usage errors. A model coming from C or POSIX traditions might occasionally attempt to return custom non-standard error codes unless bound by this rule.

#### Pass 2: Strengths & Mechanical Invariants
- **Unsafe Environment Variable Ban (R3)**: `scripts/update_knowledge_base.py` scans Python ASTs for `os.environ[...]` indexing, enforcing `os.getenv(..., default)` across the entire codebase. This completely eliminates runtime `KeyError` crashes from missing environment variables.
- **Headless Non-Interactive Parity (R5)**: Mechanically prohibits blocking keyboard prompts (`input()`) unless `--interactive` or `-i` is explicitly passed, guaranteeing that scripts never hang automated test runners or headless subagents.
- **Actionable Remediation Triad (R6)**: Enforced across all CLI tools and unit tests; usage errors print to stderr and exit with status code 2, while runtime tracebacks are caught and translated into user-actionable remediation instructions.

#### Pass 3: Weaknesses, Loopholes & Edge Cases
- **Traceback Suppression vs Debugging**: While suppressing raw tracebacks provides clean user-facing error messages, it can occasionally obscure internal logic bugs during development unless a `--debug` or `--verbose` flag is available.
- **Simulated Success Detection**: Rule R3 prohibits reporting simulated success on missing credentials. Detecting whether an adapter is silently returning mock data instead of raising an error relies on rigorous test coverage.

#### Pass 4: Cross-Principle Alignment & Redundancies
- Seamlessly aligns with `PRINCIPLE-003` (zero undeclared dependencies), `PRINCIPLE-008` (closed stdin subagents), `PRINCIPLE-010` (rapid `--help` startup), and `PRINCIPLE-015` (dogfooding verification).

#### Pass 5: Operational Usability & Cognitive Ergonomics
- Delivers an exemplary first-run developer experience. Any developer or agent can clone the repository and run `--audit` or `dogfood.py` within seconds without installing third-party packages, configuring virtualenvs, or setting environment variables.

#### Pass 6: Multi-Host / Multi-Client Portability
- Rule R4 explicitly bans platform-specific shell builtins (`export`, `set`, `./script.sh`), ensuring that documented commands run identically across Windows PowerShell, CMD, macOS zsh, and Linux bash.

#### Pass 7: Proposed Evolutions, Working Impact, Drawbacks & Gains
- **Proposed Change**: Standardize a global `--debug` flag across all `scripts/*.py` utilities that displays the underlying Python exception traceback after the Actionable Remediation Triad when troubleshooting.
- **Working Impact on AIKit**: Preserves clean error messages for end users while giving maintainers deep diagnostic traces on demand.
- **Drawbacks**: Adds ~10 lines of argument parsing logic per script.
- **Gains**: Accelerates internal debugging without violating the Triad presentation invariant.

---

### 🔍 PRINCIPLE-012: Token Frugality & Lean Code Architecture (Context Budgeting)

#### Pass 1: Semantic Clarity & Cross-LLM Interpretability
- **Clarity Assessment**: High precision. Distinguishes cleanly between rules binding code that calls LLM APIs (R1, R2, R4, R6) and rules binding the agent's own behavior and code generation (R3, R5, R7, R8).
- **Predicted cross-LLM behavior (not measured)**: Models understand the static prefix vs variable tail prompt caching split (R2) and apply repository-relative paths (`scripts/disruption_recovery.py`) rather than verbose absolute paths.
- **Semantic Risks**: Rule R7 forbids "a function whose body only calls another function with the same arguments". Some models might interpret standard design pattern delegations (e.g. wrapper facades) as premature abstraction unless the rule's specific boundaries are kept clear.

#### Pass 2: Strengths & Mechanical Invariants
- **Prompt Cache Optimization (R2)**: Mandates that system instructions, schemas, and static rules form a byte-identical prefix, placing dynamic data (timestamps, session IDs, task state) exclusively in the variable tail. This maximizes KV cache hit rates on modern providers (OpenAI, Anthropic, Google, DeepSeek), slashing inference costs and latency.
- **Bounded Tool Outputs (R3)**: Enforces `git diff -U3` and capping search results to at most 50 matches (`| head -n 50`), preventing massive log dumps from poisoning context windows.
- **Circuit Breakers (R6)**: Enforces mandatory exponential backoff with full jitter on HTTP 429/529 and hard ceilings on autonomous loop steps and token consumption.
- **Tiered Model Delegation (R8)**: Explicitly permits offloading bulk searches, file indexing, and syntax linting to free-tier or local models guided by `knowledge/model_benchmarks.md`.

#### Pass 3: Weaknesses, Loopholes & Edge Cases
- **Prompt Size Estimation Variance**: R1 caps the prompt variable tail at 16,000 characters. Since tokenizers differ (e.g. TikToken vs SentencePiece vs Gemma), character counts are used as a safe universal proxy, but character-to-token ratios can diverge on non-English text or dense code.
- **Subagent Routing Ambiguity**: When choosing between free models and frontier models, an agent might underestimate task complexity and delegate a nuanced refactor to a weaker model unless specialized subagent profiles (`architect`, `coder`, `tester`, `reviewer`) are strictly observed.

#### Pass 4: Cross-Principle Alignment & Redundancies
- Directly interlocks with `PRINCIPLE-001` (context budget ceilings), `PRINCIPLE-004` (100-line tool limits), `PRINCIPLE-008` (subagent briefs and single ledger writer), and `PRINCIPLE-009` (pluggable model provider lifecycle).

#### Pass 5: Operational Usability & Cognitive Ergonomics
- Delivers extreme cost and token efficiency. Sessions can run for hundreds of turns without hitting context exhaustion or running up unnecessary API expenses.

#### Pass 6: Multi-Host / Multi-Client Portability
- Native compatibility across cloud and local model providers. Operates identically whether connecting to Anthropic Claude, OpenAI, Google Gemini, OpenCode gateways, or local Ollama/vLLM instances.

#### Pass 7: Proposed Evolutions, Working Impact, Drawbacks & Gains
- **Proposed Change**: Add an automated token estimator utility in `scripts/` that calculates tokenizer-specific token counts for prompt prefixes and payloads across Claude, OpenAI, and Gemini tokenizers.
- **Working Impact on AIKit**: Provides exact token telemetry alongside character counts.
- **Drawbacks**: Requires maintaining static BPE/SentencePiece vocabulary tables or relying on heuristic character ratios to preserve zero external dependencies.
- **Gains**: Delivers precision KV cache alignment and budget verification.

---

## 🛡️ Phase 4: Operational Verification & Resilience

---

### 🔍 PRINCIPLE-013: Crash Resilience, State Atomicity & Power-Loss Recovery (Fail-Safe Operations)

#### Pass 1: Semantic Clarity & Cross-LLM Interpretability
- **Clarity Assessment**: Exceptional. The principle establishes a crisp, formal distinction between *state files* (files the program writes and reads back that cannot be rebuilt from tracked sources) and *generated files* (files rebuilt deterministically by running a generator command).
- **Predicted cross-LLM behavior (not measured)**: All evaluated models (Claude, GPT, Gemini, DeepSeek, Qwen) accurately implement the 5-step atomic write sequence: write to temp file in same directory $\rightarrow$ flush and `os.fsync` $\rightarrow$ atomic rename with `os.replace` retried up to 5 times on `PermissionError` $\rightarrow$ fsync parent directory.
- **Semantic Risks**: Rule R1 specifies a 5-try retry loop with exponential backoff on `PermissionError` specifically to mitigate Windows file lock contention (`WinError 32`). A model running exclusively in Linux container environments might treat this retry loop as superfluous unless reminded of cross-platform parity.

#### Pass 2: Strengths & Mechanical Invariants
- **Storage Headroom Pre-Flight Check (R2)**: Checks with `shutil.disk_usage` that at least 10MB of free space exists before writing any state file. Completely eliminates truncated files resulting from `ENOSPC` (disk full).
- **Advisory Lock Invariant (R3)**: Every read-modify-write holds a `<file>.lock` file with a 3-second acquisition timeout. Deadlocks are broken by an atomic rename of any lock older than 30 seconds.
- **Dual-Slot Shadow Snapshots & Auto-Quarantine (R4)**: Before replacing a state file, code copies the current version to `<file>.bak`. Corrupted files are automatically quarantined to `<file>.corrupt_<epoch>` and migrated rather than crashing the system.
- **Continuous Chaos & Fault-Injection Tests (R7)**: Mechanically verified in `tests/test_kit.py` and `tests/test_integration.py` through dedicated fault-injection tests (0-byte file, malformed JSON, disk exhaustion, concurrent writers).

#### Pass 3: Weaknesses, Loopholes & Edge Cases
- **Directory Fsync on Windows**: In Python on Windows, calling `os.fsync` on an open directory handle raises `OSError` (`[Errno 22] Invalid argument`). The kit skips directory syncing on Windows (`if sys.platform == "win32"` in `fsync_dir`), but a naive AI implementing P013 outside the kit could hit Windows handle errors.
- **Stale Lock Inode Recycling**: In fast multi-process loops, breaking a 30-second stale lock via atomic rename could theoretically race if clock skew exists across container mounts.

#### Pass 4: Cross-Principle Alignment & Redundancies
- Directly underpins `PRINCIPLE-004` (Ledger Persistence), `PRINCIPLE-006` (Atomic Checkpointing), `PRINCIPLE-010` (Batch I/O Coalescing), and `PRINCIPLE-016` (Knowledge Base Storage). Zero conflicting directives.

#### Pass 5: Operational Usability & Cognitive Ergonomics
- Delivers complete peace of mind during long-running autonomous runs. Machine crashes, hard resets, or abrupt terminal closures never leave corrupt or half-written ledger files.

#### Pass 6: Multi-Host / Multi-Client Portability
- The 5-try retry loop specifically overcomes Windows NTFS opportunistic lock contention (`WinError 32`), while maintaining strict POSIX atomicity on Linux and macOS.

#### Pass 7: Proposed Evolutions, Working Impact, Drawbacks & Gains
- **Proposed Change**: Formalize a generic context manager in `scripts/disruption_recovery.py` (`atomic_state_transaction(path)`) that encapsulates lock acquisition, disk check, `.bak` snapshotting, temp write, fsync, and quarantine.
- **Working Impact on AIKit**: Centralizes all P013 requirements into a reusable standard-library utility.
- **Drawbacks**: Adds approximately 40 lines of code to `scripts/disruption_recovery.py`.
- **Gains**: Completely prevents ad-hoc atomic write omissions across new scripts.

---

### 🔍 PRINCIPLE-014: Automated Test Verification & Continuous Test Coverage (Regression Shield)

#### Pass 1: Semantic Clarity & Cross-LLM Interpretability
- **Clarity Assessment**: Outstanding clarity. Enforces the golden invariant: 100% test pass gate, behavior changes require a failing-first test, and weakening a test is strictly defined and forbidden without user approval and a recorded ADR.
- **Predicted cross-LLM behavior (not measured)**: The definition of test weakening ("any change after which it accepts a behavior it rejected before") is universally understood by all models, effectively closing the loophole where models delete assertions to make a failing suite pass.
- **Semantic Risks**: Rule R1 distinguishes between a "behavior change" (requires a new test) and a "refactor" (existing tests pass unchanged). An agent could misclassify an internal contract shift as a refactor unless verified by reachability and interface checks.

#### Pass 2: Strengths & Mechanical Invariants
- **100% Test Pass Gate (R1 & R2)**: Zero failed, errored, or skipped tests permitted.
- **Anti-Mock Echo Invariant (R5)**: Mechanically prohibits tautological tests that only assert on mock calls (`assert_called_once`). Every test must assert at least one observable side effect or contract result.
- **Sub-Second Unit Test Tier (R3)**: Enforces `tests/test_kit.py` running in < 1s with zero subprocess spawns, zero sleeps, zero network calls, and deterministic random seeds.
- **Invariant Reachability Shield (R7)**: Mechanically verified by `python scripts/check_reachability.py`, ensuring that production functions have live production call sites and persisted keys have production writers.

#### Pass 3: Weaknesses, Loopholes & Edge Cases
- **Allowlist Creep in Reachability**: `scripts/check_reachability.py` maintains an allowlist for legitimate public entry points (such as CLI handlers or dynamic dispatchers). An agent could attempt to add unused dead code to the allowlist instead of fixing callers.
- **Negative Path Incompleteness**: While R6 mandates testing invalid input for new functions, verifying that *all* edge cases are exercised still relies on developer test design quality.

#### Pass 4: Cross-Principle Alignment & Redundancies
- Directly reinforces `PRINCIPLE-000` (Code Quality Primacy), `PRINCIPLE-002` (Phase 4 Verification Gate), `PRINCIPLE-003` (Empirical Reality), `PRINCIPLE-007` (Anti-Satisficing), `PRINCIPLE-010` (Test Timing Budgets), and `PRINCIPLE-018` (Git Triad Gate).

#### Pass 5: Operational Usability & Cognitive Ergonomics
- The sub-second execution of the unit test suite enables instant feedback. Developers and agents run the test suite repeatedly without breaking creative flow.

#### Pass 6: Multi-Host / Multi-Client Portability
- Relies solely on Python's built-in `unittest` framework. Requires zero external test runners (`pytest`, `tox`) and executes reliably across all hosts and CI runners.

#### Pass 7: Proposed Evolutions, Working Impact, Drawbacks & Gains
- **Proposed Change**: Enhance `scripts/check_reachability.py` with an AST mutation score checker that flags tests with zero assertions on function return values.
- **Working Impact on AIKit**: Mechanically guarantees that all unit tests verify tangible state or outputs.
- **Drawbacks**: Increases reachability check execution time by approximately 150ms.
- **Gains**: Mathematically eliminates vacuous assertions and mock echoes.

---

### 🔍 PRINCIPLE-015: Universal Operational Dogfooding & Chaos Verification (The AI Must Use What It Builds)

#### Pass 1: Semantic Clarity & Cross-LLM Interpretability
- **Clarity Assessment**: High precision. The principle mandates that the AI agent must run what it builds the way a user would: in a real sandbox, on the golden path, and under hostile chaos perturbation.
- **Predicted cross-LLM behavior (not measured)**: Models grasp the domain-specific nature of the runner: CLI commands run as real processes with closed stdin, web apps check root containers and console errors, APIs verify HTTP schemas and 500ms latency, GUIs test offscreen window lifecycle.
- **Semantic Risks**: Rule R5 specifies that "running `--help` alone is not a dogfood run". Models might assume that invoking `--audit` satisfies the requirement without executing the interactive golden path and chaos perturbation tracks.

#### Pass 2: Strengths & Mechanical Invariants
- **Dual-Track Dogfooding (R5)**: Every dogfood run executes both a golden path (creates, modifies, and verifies state end-to-end) and a hostile chaos perturbation (interrupted input, malformed JSON, invalid flags, lock contention).
- **Portable RAII Process Tree Teardown (R2)**: Uses `taskkill /F /T /PID` on Windows and `os.killpg(pid, signal.SIGKILL)` on POSIX within context managers, guaranteeing zero orphaned daemon or zombie processes.
- **Terse Context Reporting (R7)**: Output is strictly capped at <= 15 lines in the conversational context, writing verbose execution traces to `.agents/dogfood_last_run.log`.

#### Pass 3: Weaknesses, Loopholes & Edge Cases
- **Ephemeral Sandbox Leakage**: If a subprocess spawned during dogfooding bypasses the temp directory context manager (for instance, writing to the current working directory), it could dirty git status. R4 detects this by checking git tree fingerprints before and after the run.
- **Long-Running Process Hanging**: In edge cases where a process ignores termination signals, the teardown context manager must forcefully kill the tree after a finite grace period (e.g. 2 seconds) to avoid hanging the entire runner.

#### Pass 4: Cross-Principle Alignment & Redundancies
- Directly interlocks with `PRINCIPLE-002` (Phase 4 Verification), `PRINCIPLE-010` (Subprocess Timeouts), `PRINCIPLE-011` (Non-Interactive Headless Parity), `PRINCIPLE-013` (Fault Injection), and `PRINCIPLE-018` (Pre-Commit Gate).

#### Pass 5: Operational Usability & Cognitive Ergonomics
- Closes the gap between passing unit tests and real-world execution. Prevents the common AI syndrome where all unit tests pass using mocks, but the actual CLI tool crashes when executed in a real shell.

#### Pass 6: Multi-Host / Multi-Client Portability
- AIKit's `scripts/dogfood.py` executes natively across Windows, Linux, and macOS without requiring virtualization, Docker, or external orchestration tools.

#### Pass 7: Proposed Evolutions, Working Impact, Drawbacks & Gains
- **Proposed Change**: Add an automated mock-network interceptor in `scripts/dogfood.py` that verifies that the dogfood runner itself makes zero outbound network requests when testing local workflows.
- **Working Impact on AIKit**: Confirms hermetic offline isolation during Phase 4 verification.
- **Drawbacks**: Adds minor network socket hook logic.
- **Gains**: Guarantees zero external network dependencies during automated dogfood verification.

---

## 🚀 Phase 5: Living Synchronization & Delivery

---

### 🔍 PRINCIPLE-016: AI Knowledge Base & Continuous Synchronization

#### Pass 1: Semantic Clarity & Cross-LLM Interpretability
- **Clarity Assessment**: Exceptional. Mandates the canonical structure of `knowledge/`: `INDEX.md`, `architecture.md`, `services.md`, `data_models.md`, `state_and_ui.md`, `decisions.md`, and `codebase_map.md`.
- **Predicted cross-LLM behavior (not measured)**: Models reliably identify where specific changes belong: schemas in `data_models.md`, architectural decisions in `decisions.md`, service gates in `services.md`.
- **Semantic Risks**: Rule R2 prohibits restating rule text from `GUIDELINES.md` inside `knowledge/` documents. Some models tend to summarize rule text when citing principles; this restriction must be strictly maintained to prevent divergence.

#### Pass 2: Strengths & Mechanical Invariants
- **Monotonic Append-Only ADR Register (R3)**: Past architectural decision records (ADRs) are strictly immutable once committed. Modifying past decisions is forbidden; superseding decisions require appending a new ADR that explicitly references the predecessor.
- **Strict AST Syntax Validation & Freshness Gate (R4)**: `python scripts/update_knowledge_base.py` parses all Python files with the grammar of `MIN_PYTHON` (3.10) and regenerates `codebase_map.md`. Commits are blocked if the committed map differs from a fresh AST generation.
- **Link Integrity Shield (R6)**: `update_knowledge_base.py` mechanically checks that all relative links in `INDEX.md` resolve to existing files.

#### Pass 3: Weaknesses, Loopholes & Edge Cases
- **ADR Renumbering Race**: If two concurrent branches add ADRs with the same sequence number, a merge conflict occurs. R3 handles this by renumbering duplicate IDs and recording the resolution in a new ADR.
- **Symbol Citation Drift**: Rule R2 requires that `UPPER_CASE` constants and function names cited in `knowledge/` documents exist in the code. Maintaining this citation integrity requires regular execution of `scripts/update_knowledge_base.py`.

#### Pass 4: Cross-Principle Alignment & Redundancies
- Directly anchors `PRINCIPLE-003` (Empirical Reality), `PRINCIPLE-004` (Context Compaction Resumption), `PRINCIPLE-005` (Documentation Partitioning Triad), and `PRINCIPLE-017` (Living Principles Sync).

#### Pass 5: Operational Usability & Cognitive Ergonomics
- Provides the ultimate living map of the codebase. A fresh AI session or new human contributor can navigate the entire architecture, data schemas, and historical decisions without scanning thousands of lines of raw source code.

#### Pass 6: Multi-Host / Multi-Client Portability
- Markdown and Python standard library implementation. Universally readable by all AI context loaders and markdown renderers.

#### Pass 7: Proposed Evolutions, Working Impact, Drawbacks & Gains
- **Proposed Change**: Add an automated citation linter in `scripts/update_knowledge_base.py` that verifies that every ADR title in `knowledge/decisions.md` matches the format `### ADR-NNN: <Title>` with consecutive numbering.
- **Working Impact on AIKit**: Prevents accidental numbering skips or formatting inconsistencies in the ADR register.
- **Drawbacks**: Adds approximately 15 lines of regex checking.
- **Gains**: Mathematically guarantees contiguous, unbroken ADR history.

---

### 🔍 PRINCIPLE-017: Living Principles System & Automated Synchronization (Auto-Sync Governance)

#### Pass 1: Semantic Clarity & Cross-LLM Interpretability
- **Clarity Assessment**: Exceptional. The principle cements `GUIDELINES.md` as the single hand-edited source of truth and enforces that all Tier 1 prompt targets across all host IDEs are generated deterministically.
- **Predicted cross-LLM behavior (not measured)**: Frontier models (Claude, GPT-4o, Gemini) and local models (Qwen, DeepSeek) interpret the 5-section schema (`Title`, `Problem`, `Concept`, `Invariant`, `Rules`) identically. Models correctly recognize that editing derived files (such as `AGENTS.md` or `CLAUDE.md`) directly is forbidden.
- **Semantic Risks**: Rule R5 specifies that principles belong to the nearest `## ... Phase N:` heading above them and must appear in non-decreasing phase order. An agent inserting a new principle must place it in the correct phase section to prevent generator exit code 1.

#### Pass 2: Strengths & Mechanical Invariants
- **Deterministic Auto-Sync Freshness Gate (R3)**: Enforced via `python scripts/sync_principles.py --check` and unit test assertions (`sync_all(check_only=True) == 0`). Any drift between `GUIDELINES.md` and derived targets blocks commits immediately.
- **Strict Context Budget Cap**: Enforces the 1,600 estimated token ceiling for generated Tier 1 instruction files, ensuring minimal prompt footprint across all client harnesses.
- **Triad Title Parity (R4)**: Principle titles exist exactly once in `GUIDELINES.md` and are projected automatically into `README.md`'s principle table, eliminating documentation divergence by construction.

#### Pass 3: Weaknesses, Loopholes & Edge Cases
- **Tier 1B Domain Rules Overflow**: Rule R6 caps `.agents/rules/domain.md` at 1,200 characters. In repositories with intricate domain rules, developers may struggle to compress requirements into this tight character envelope.
- **Sync Command Sequencing**: If an agent edits `GUIDELINES.md` but forgets to run `python scripts/sync_principles.py` before checking `git diff`, tests and pre-commit gates will fail until the sync command is executed.

#### Pass 4: Cross-Principle Alignment & Redundancies
- Directly interlocks with `PRINCIPLE-000` (Integrity & Mutual Alignment), `PRINCIPLE-001` (Progressive Rule Disclosure), `PRINCIPLE-005` (README Table Generation), `PRINCIPLE-009` (Host Portability), and `PRINCIPLE-018` (Pre-Commit Delivery Triad).

#### Pass 5: Operational Usability & Cognitive Ergonomics
- Eliminates manual synchronization drudgery. Updating a rule in one place (`GUIDELINES.md`) instantly propagates across Google Antigravity, Claude Code, Cursor, and GitHub Copilot with mathematical consistency.

#### Pass 6: Multi-Host / Multi-Client Portability
- The architectural bedrock of multi-client support in AIKit. Generates native rule surfaces tailored to each host's configuration format while preserving a unified set of invariant capsules.

#### Pass 7: Proposed Evolutions, Working Impact, Drawbacks & Gains
- **Proposed Change**: Add a `--diff` flag to `scripts/sync_principles.py` that displays an in-memory unified diff of derived files when `--check` fails, showing exactly which files and capsules drifted.
- **Working Impact on AIKit**: Provides immediate visual clarity when CI runners detect rule drift.
- **Drawbacks**: Adds approximately 20 lines to `scripts/sync_principles.py`.
- **Gains**: Accelerates troubleshooting of synchronization mismatches.

---

### 🔍 PRINCIPLE-018: Automatic Git Workflow (Commit & Push)

#### Pass 1: Semantic Clarity & Cross-LLM Interpretability
- **Clarity Assessment**: Outstanding clarity. Strictly defines conventional commit formatting, explicit named staging, the pre-commit delivery triad, adaptive pushing without force, and non-destructive soft recoil.
- **Predicted cross-LLM behavior (not measured)**: All evaluated models strictly respect the prohibition against blind staging (`git add .`, `git add -A`, `git add -u`). Models consistently format commits according to the conventional spec: `type(scope): [milestone N/M] description`.
- **Semantic Risks**: Rule R4 mandates running `git pull --rebase` if a push is rejected. If an LLM encounters a complex rebase conflict, it must execute `git rebase --abort` and ask the user rather than attempting heuristic conflict resolution that could corrupt history.

#### Pass 2: Strengths & Mechanical Invariants
- **Commit Message Validation Gate (R1)**: Mechanically checked by `python scripts/disruption_recovery.py --validate-commit "<message>"`, which enforces valid conventional commit types (`feat`, `fix`, `refactor`, `docs`, `chore`, `test`, `perf`, `build`, `ci`), 72-character subject ceilings, and valid milestone range tags ($1 \le N \le M, 2 \le M \le 6$).
- **Explicit Staging Invariant (R2)**: Hard ban on blind staging commands (`git add .`, `git add -A`, `git add --all`, `git add -u`, `git commit -a`), preventing accidental staging of untracked scratch files or secrets.
- **Pre-Commit Delivery Triad (R3)**: Commits are strictly gated on:
  1. 100% test pass on both tiers
  2. All read-only gates passing (`sync_principles.py --check`, `update_knowledge_base.py --check`, `check_reachability.py`, `check_secrets.py`, `dogfood.py`)
  3. Staged diff containing precisely the intended modifications
- **Non-Destructive Recoil (R5)**: Prohibits `git reset --hard` and `git clean` on unowned changes, mandating `git reset --soft HEAD^` for local unpushed commits and `git revert` for pushed commits.

#### Pass 3: Weaknesses, Loopholes & Edge Cases
- **Unverified Commit Override**: Under PRINCIPLE-002 R5, an explicit user override permits committing unverified code if the message ends with `Unverified: <gates>`. If misused, unverified code can enter git history; this is mitigated by tracking unverified flags in audit logs.
- **Dirty Tree Staging Confusion**: If an agent modifies multiple files across different milestones simultaneously, staging only the files for milestone N while leaving milestone N+1 dirty requires meticulous file-by-file staging discipline.

#### Pass 4: Cross-Principle Alignment & Redundancies
- Directly anchors `PRINCIPLE-002` (Phase 5 Delivery), `PRINCIPLE-006` (Milestone Micro-Commits), `PRINCIPLE-007` (Rollback Point), `PRINCIPLE-014` (Test Gate), and `PRINCIPLE-019` (Secret Scanning Gate).

#### Pass 5: Operational Usability & Cognitive Ergonomics
- Delivers clean, bisectable git histories. Every commit corresponds to a passing milestone, making git bisect and automated release note generation completely reliable.

#### Pass 6: Multi-Host / Multi-Client Portability
- Native Git command implementation. Compatible with all Git CLI clients, SSH/HTTPS remotes, and hosting providers (GitHub, GitLab, Bitbucket).

#### Pass 7: Proposed Evolutions, Working Impact, Drawbacks & Gains
- **Proposed Change**: Add an automated pre-stage validator in `scripts/disruption_recovery.py` (`--validate-staging`) that checks that no untracked `.tmp_*` or `.bak` files exist in the working tree prior to staging.
- **Working Impact on AIKit**: Adds a mechanical safety catch before `git add` operations.
- **Drawbacks**: Adds minor validation overhead.
- **Gains**: Prevents transient buffer files from ever reaching the staging area.

---

### 🔍 PRINCIPLE-019: Secret & Sensitive Data Hygiene (Irreversible Disclosure Shield)

#### Pass 1: Semantic Clarity & Cross-LLM Interpretability
- **Clarity Assessment**: Exceptional. Establishes the foundational truth that secret exposure is the only defect class with no clean rollback: once a secret is committed or pushed, it must be rotated immediately; `git reset` or deleting the file cannot cure the disclosure.
- **Predicted cross-LLM behavior (not measured)**: All models parse the requirement to read secrets exclusively from environment variables via `os.getenv`. Redaction formats (`first 4 characters + ***`) are applied consistently across models.
- **Semantic Risks**: Rule R7 forbids "inventing, guessing or filling in a credential value to make a flow proceed". When testing API integrations, models sometimes fabricate dummy API keys (such as `sk-12345...`) that can trip entropy scanners unless properly mocked.

#### Pass 2: Strengths & Mechanical Invariants
- **Mechanical Pre-Commit Secret Scan (R5)**: `python scripts/check_secrets.py` scans the staged diff, agent memory (`task_ledger.json`), and dogfood logs. It detects high-entropy strings, known vendor patterns (AWS, GCP, GitHub, Slack, OpenAI, OpenCode), private keys, and certificates.
- **Ignore-List Baseline (R2)**: `.gitignore` must contain mandatory credential patterns (`.env`, `*.pem`, `*.key`, `id_rsa*`, `credentials.*`, `secrets.*`). Mechanically verified in unit tests.
- **Diagnostic Redaction (R4)**: Forbids printing `os.environ` or raw authorization headers, requiring truncation and masking (`first 4 chars + ***`).
- **Rotate, Never Revert Protocol (R6)**: Enforces that exposed secrets are treated as compromised and must be revoked at the provider immediately rather than attempting a cosmetic git reset.

#### Pass 3: Weaknesses, Loopholes & Edge Cases
- **Allowlist Abuse**: Developers can suppress scanner warnings using `# aikit:allow-secret` or adding patterns to `STRONG_ALLOWLIST` / `WEAK_ALLOWLIST`. Rule R5 requires a commit message explaining why, but human review is needed to verify legitimate false positives.
- **Free-Text Rationale Leakage**: While structured configs are easily scanned, an agent writing free-form task descriptions in `task_ledger.json` might accidentally paste authorization bearer tokens. AIKit scans the ledger explicitly to block this.

#### Pass 4: Cross-Principle Alignment & Redundancies
- Directly interlocks with `PRINCIPLE-000` (Integrity Tier 1 Priority), `PRINCIPLE-003` (Empirical Reality), `PRINCIPLE-009` (Provider Credential Isolation), `PRINCIPLE-011` (Safe Env Reads), and `PRINCIPLE-018` (Pre-Commit Gate).

#### Pass 5: Operational Usability & Cognitive Ergonomics
- Protects users and organizations from disastrous security breaches. Runs silently in sub-second time during Phase 4 verification, providing total credential assurance without developer friction.

#### Pass 6: Multi-Host / Multi-Client Portability
- Scans files and diffs using pure standard-library regular expressions and entropy calculations. Operates identically across Windows, Linux, and macOS without requiring external secret scanning daemons.

#### Pass 7: Proposed Evolutions, Working Impact, Drawbacks & Gains
- **Proposed Change**: Add automated detection patterns for emerging cloud providers (such as OpenCode service account keys and inference gateway tokens) to `scripts/check_secrets.py`.
- **Working Impact on AIKit**: Keeps secret scanning definitions aligned with newly added provider ecosystems.
- **Drawbacks**: Adds approximately 12 lines of regex patterns.
- **Gains**: Guarantees zero credential leaks when integrating newly supported AI providers.

---

## 📊 Cross-Cutting Synthesis & Architectural Roadmap

### Systemic Strengths
1. **Falsifiable Invariants**: Every principle is anchored to measurable, decidable criteria (milliseconds, character budgets, exit codes, AST queries) rather than aspirational prose.
2. **Crash & Compaction Resilience**: With the dual-tier memory partition (JSON WAL on disk, transient conversation in chat), AIKit survives infinite session compactions and abrupt power cuts without state corruption.
3. **Multi-Host Decoupling**: Pure standard-library implementation guarantees that AIKit works identically inside Google Antigravity, Anthropic Claude Code, Cursor, OpenCode, and standard terminal environments.
4. **Zero-Satisficing Verification Shield**: Unit tests, integration tests, reachability analysis, secret scanning, and operational dogfooding form an airtight pre-commit delivery triad.

### Systemic Trade-Offs & Architectural Costs
1. **Governance Ceremony**: Strict adherence to the 5-phase lifecycle, impact assessments, and milestone micro-commits requires disciplined agent execution. While this prevents high-cost bugs, it introduces deliberate pacing on Track C changes.
2. **Context Budget Boundaries**: The 20,000 character limit on `README.md` and 1,600 token ceiling on Tier 1 instruction files force relentless prose compression, necessitating continuous use of the living knowledge base in `knowledge/`.

### Predicted Cross-Model Interpretability (not measured)

| Principle Group | Frontier Models (Claude, GPT-4o, Gemini) | Local / Open Weights (DeepSeek, Qwen) | Key Deterministic Anchor |
| :--- | :--- | :--- | :--- |
| **P000 - P004** (Meta & Grounding) | Flawless compliance with RFC 2119 keywords and 4-tier conflict hierarchy | Follows explicit rule citation precedence; requires bounded reads (<= 100 lines) | AST map search, whole-word grep, 100-line tool cap |
| **P005 - P008** (Orientation & Planning) | Excellent structured impact assessments and milestone decomposition | Strict adherence to $M \le 6$ and single ledger writer | CLI gate enforcement (`--checkpoint` exit code 2 on missing fields) |
| **P009 - P012** (Architecture & Speed) | Natural adherence to 4 layers and constructor injection | Respects banned names (`utils`) and explicit performance limits | AST syntax gates, static prompt prefix caching |
| **P013 - P016** (Resilience & Verification) | Accurate implementation of atomic write loops and reachability checks | Follows exact retry loops and sub-second test execution | `os.replace` 5-try retry, 100% test pass gate, reachability shield |
| **P017 - P019** (Delivery & Security) | Perfect adherence to conventional commits, explicit staging, and secret redaction | Relies on machine gates (`--validate-commit`, `check_secrets.py`) | Automated gate exit codes, zero `git add .` invariant |

---

