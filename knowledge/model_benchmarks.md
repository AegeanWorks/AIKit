# Subagent Model Benchmark Database 📊

> **Authority**: Governed by **PRINCIPLE-009 R6** (Pluggable Provider Lifecycle) and **PRINCIPLE-012 R8** (Tiered Model Delegation). This database establishes empirical ground-truth benchmark metrics, published context window capacities, and task suitability criteria for delegating subagent operations across free, local, and cloud providers.

---

## 🎯 Benchmark Evaluation & Ground-Truth Invariant

Model capabilities MUST be sourced exclusively from published, reproducible, and verifiable public evaluation suites. Synthetic, estimated, or unverified benchmark scores are strictly prohibited (**PRINCIPLE-009 R6**).

The 5 primary evaluation dimensions:

1. **SWE-bench Verified (%)**: End-to-end resolution of real-world GitHub issues against official regression test suites. Measures actual software engineering capability and multi-file code editing fidelity.
2. **LiveCodeBench (LCB pass@1 %)**: Evaluates uncontaminated code generation, error correction, and execution fidelity on code problems released after model training cutoffs.
3. **HumanEval (Python pass@1 %)**: Algorithmic synthesis, logical completeness, and basic function implementation.
4. **Context Window (Total & Effective Tokens)**: Maximum token capacity and usable prompt retention window before degradation occurs.
5. **Throughput & Latency (Tokens/sec)**: Generation velocity during bulk file inspections, search condensations, and boilerplate drafting.

---

## 📏 Context Window & Task Payload Sizing Matrix

Model selection MUST match the task's token footprint and required context retention against the model's verified context window (**PRINCIPLE-012 R8**, **PRINCIPLE-010 R1**):

| Context Tier | Payload Range | Typical Subagent Tasks | Target Context Window | Recommended Models |
|---|---|---|---|---|
| **Tier I: Micro** | `< 16,000` chars (~4k tokens) | Focused diff fixes, symbol grep condensation, lint error remediation | $\ge$ 32,000 tokens | `opencode/mimo-v2.6-flash-free`, `ollama/qwen2.5-coder:latest` |
| **Tier II: Standard** | `16k - 64k` chars (~4k - 16k tokens) | Single-module feature implementation, unit test writing, syntax verification | $\ge$ 64,000 tokens | `openrouter/qwen/qwen-2.5-coder-32b-instruct:free`, `opencode/deepseek-v4.1-flash-free` |
| **Tier III: Extended** | `64k - 250k` chars (~16k - 64k tokens) | Multi-file refactoring, subsystem audits, architectural trade-off analysis | $\ge$ 128,000 tokens | `openrouter/deepseek/deepseek-r1:free`, `openrouter/meta-llama/llama-3.3-70b-instruct:free` |
| **Tier IV: Massive** | `> 250,000` chars (> 64k tokens) | Full-repository audits, whole documentation sync, cross-dependency graph analysis | $\ge$ 128,000 - 200,000+ tokens | `openrouter/meta-llama/llama-3.3-70b-instruct:free`, Parent Orchestrator |

---

## 📈 Empirical Model Benchmark Table

These figures were entered without a per-row source. Each row is `unverified` until its Source column holds the URL its scores were read from; an unverified score is never a reason to choose a model (**PRINCIPLE-009 R6**, ADR-114):

The **Specialized Subagent Profile** column says what a model suits, not what runs: each role runs the `model:` of its `.opencode/agents/<role>.md` profile, and another model only through `delegate --model` (ADR-197).

Configured today: `architect` and `reviewer` `gemini/gemini-3.8-flash`, `coder` `opencode/glm-5.3-flash-free`, `explorer` `opencode/mimo-v2.6-flash-free`, `tester` and `worker` `opencode/deepseek-v4.1-flash-free`.

| Model Identifier | Provider / Engine | Cost Tier | Context Window | SWE-bench Verified (%) | LiveCodeBench (%) | HumanEval (%) | Throughput | Specialized Subagent Profile | Source |
|---|---|---|---|---|---|---|---|---|---|
| **`openrouter/deepseek/deepseek-r1:free`** | OpenRouter Free | **Free ($0.00)** | **128k** | **49.2%** | **65.9%** | **92.8%** | Deliberate (~25 t/s) | **`architect`**: Deep reasoning on system design, ADR preparation, and subtle test failure diagnostics | `unverified` |
| **`openrouter/qwen/qwen-2.5-coder-32b-instruct:free`** | OpenRouter Free | **Free ($0.00)** | **128k** | **39.8%** | **49.3%** | **92.7%** | Moderate (~55 t/s) | **`coder`** / **`tester`**: High-fidelity code generation, refactoring, and regression test suites | `unverified` |
| **`opencode/deepseek-v4.1-flash-free`** | OpenCode Native | **Free ($0.00)** | **128k** | **36.4%** | **46.8%** | **91.2%** | Very Fast (~110 t/s) | **`worker`**: General-purpose background worker for code drafting and file audits | `unverified` |
| **`openrouter/meta-llama/llama-3.3-70b-instruct:free`** | OpenRouter Free | **Free ($0.00)** | **128k** | **37.8%** | **45.2%** | **88.6%** | Fast (~70 t/s) | **`reviewer`**: Large-context documentation review, schema audits, and knowledge base sync | `unverified` |
| **`opencode/glm-5.3-flash-free`** | OpenCode Native | **Free ($0.00)** | **128k** | **33.1%** | **44.2%** | **88.5%** | Fast (~85 t/s) | **`reviewer`**: Markdown link verification, AST integrity checks, and test log triage | `unverified` |
| **`opencode/mimo-v2.6-flash-free`** | OpenCode Native | **Free ($0.00)** | **32k** | **29.8%** | **41.5%** | **86.4%** | Ultra-Fast (~140 t/s) | **`explorer`**: High-speed symbol lookup, directory tree mapping, and grep filtering | `unverified` |
| **`gemini/gemini-3.8-flash`** | Google Gemini API (free tier) | **Free tier (rate-limited)** | **1,048,576** | n/a | n/a | n/a | Fast | **`architect`**, **`reviewer`**: design analysis and whole-document review in one context (window from models.list, free tier verified by a call, ADR-132) | https://ai.google.dev/gemini-api/docs/models |
| **`gemini/gemini-3.5-flash-lite`** | Google Gemini API (free tier) | **Free tier (rate-limited)** | **1,048,576** | n/a | n/a | n/a | Very Fast | Cheap large-context reading when `explorer`'s 32k is too small | https://ai.google.dev/gemini-api/docs/models |
| **`ollama/qwen2.5-coder:latest`** | Local Ollama | **Free / Offline** | **32k** (up to 128k) | **28.6%** | **38.4%** | **88.4%** | Hardware-dependent | **Offline `coder` / `tester`**: Zero network access, air-gapped security, zero credential risk | `unverified` |
| **`ollama/deepseek-r1:latest`** | Local Ollama | **Free / Offline** | **64k** | **44.0%** | **58.2%** | **89.4%** | Hardware-dependent | **Offline `architect`**: Local architectural analysis and complex reasoning | `unverified` |
| *`claude-3-7-sonnet` (Frontier Ref)* | Anthropic (Paid) | Paid / Quota | 200k | 70.3% | 71.4% | 94.2% | Fast (~75 t/s) | **Parent Orchestrator**: Sole authority for planning, commits, and ledger updates | `unverified` |
| *`gpt-4o` (Frontier Ref)* | OpenAI (Paid) | Paid / Quota | 128k | 45.1% | 62.5% | 92.6% | Fast (~80 t/s) | **Parent Orchestrator Fallback** | `unverified` |

---

## 🔬 Benchmark Verification Sources & Methodology

All metrics are verifiable against public evaluation registries:
1. **SWE-bench Verified**: Evaluated on Princeton NLP's 500-task curated human-validated subset (`https://www.swebench.com/`).
2. **LiveCodeBench**: Evaluated on LiveCodeBench v5 test set under standard pass@1 greedy decoding (`https://livecodebench.github.io/`).
3. **HumanEval**: OpenAI HumanEval 0-shot pass@1 using standard Python execution harnesses.
4. **DeepSeek-R1 Metrics**: Sourced from *DeepSeek-R1 Technical Report* (arXiv:2501.12948, Jan 2025).
5. **Qwen2.5-Coder Metrics**: Sourced from *Qwen2.5-Coder Technical Report* (arXiv:2409.12186, Sep 2024).
6. **Meta Llama 3.3 Metrics**: Sourced from Meta AI Llama 3.3 70B Model Card and public LMSYS benchmark releases.

---

## 🧭 Multi-Subagent Selection & Routing Decision Tree

When delegating background tasks to subagents under **PRINCIPLE-012 R8**, match task requirements across Context Window, Reasoning Depth, and Agent Role. A branch naming a model other than the role's configured one is a `--model` override:

```
Task Delegation Request
│
├── 1. Need 100% Offline / Zero Network / Air-Gapped Security?
│   ├── Reasoning / Complex Logic ──► Use 'ollama/deepseek-r1:latest' (Agent: architect)
│   └── Code Generation / Tests  ──► Use 'ollama/qwen2.5-coder:latest' (Agent: coder/tester)
│
├── 2. Massive Context (>64k tokens) Documentation Review or Repository-Wide Audit?
│   └── YES ──► Use 'openrouter/meta-llama/llama-3.3-70b-instruct:free' (Agent: reviewer, 128k context)
│
├── 3. Deep Architectural Reasoning, ADR Trade-offs, or Tricky Bug Diagnosis?
│   └── YES ──► Use 'openrouter/deepseek/deepseek-r1:free' (Agent: architect, 128k context)
│
├── 4. Bounded Code Generation, Feature Implementation, or Complex Refactoring?
│   └── YES ──► Use 'openrouter/qwen/qwen-2.5-coder-32b-instruct:free' (Agent: coder, 128k context)
│
├── 5. Unit / Integration Test Generation and Regression Shield Expansion?
│   └── YES ──► Use 'openrouter/qwen/qwen-2.5-coder-32b-instruct:free' (Agent: tester, 128k context)
│
├── 6. High-Speed Symbol Discovery, Regex Search, or File Tree Exploration?
│   └── YES ──► Use 'opencode/mimo-v2.6-flash-free' (Agent: explorer)
│
├── 7. General-Purpose Background Search, File Summaries, and Boilerplate Drafting?
│   └── YES ──► Use 'opencode/deepseek-v4.1-flash-free' (Agent: worker, 128k context)
│
└── 8. Task Ledger Updates, Git Commits, and Phase 4 Gate Approvals?
    └── MUST REMAIN WITH PARENT ORCHESTRATOR (PRINCIPLE-008 R6, PRINCIPLE-018 R2)
```

---

## 🔒 Security & Fencing Bounds

Every subagent model invocation MUST adhere to the **Pluggable Provider Lifecycle (PRINCIPLE-009 R6)**:
- **Ledger Invariant (PRINCIPLE-008 R6)**: Subagent permissions must strictly deny edits to `.agents/**`. Only the lead orchestrator records checkpoints.
- **Closed Stdin (PRINCIPLE-011 R5)**: Invocations must pass closed stdin (`< NUL`, `$null`, or `stdin=subprocess.DEVNULL`) to guarantee non-interactive execution.
- **Verification Gate (PRINCIPLE-014)**: Subagent output is untrusted raw material until validated against Phase 4 tests by the parent orchestrator prior to staging.
- **Secret Hygiene (PRINCIPLE-019)**: Subagents must never receive API keys or credentials in CLI arguments or prompt text.
