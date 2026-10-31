#!/usr/bin/env python3
"""
Principles Auto-Sync Tool (PRINCIPLE-017)
Generates every always-injected Tier 1 target - including AGENTS.md - from the single Tier 2
source of truth in GUIDELINES.md, enforces principle schema completeness and the Tier 1 context
budget, rejects duplicate principle IDs, checks README parity, injects optional Tier 1B domain
rules, and refuses to overwrite any target it did not generate.
"""

import os
import re
import sys
from pathlib import Path
from typing import Dict, List, Optional, Tuple

ROOT_DIR = Path(__file__).resolve().parent.parent
AGENTS_MD = ROOT_DIR / "AGENTS.md"
GUIDELINES_MD = ROOT_DIR / "GUIDELINES.md"
README_MD = ROOT_DIR / "README.md"
DOMAIN_RULES_PATH = ROOT_DIR / ".agents" / "rules" / "domain.md"


# Tier 1 budget model (PRINCIPLE-001 R4/R6). One unit - estimated tokens - with no dominated
# thresholds: a former 7,200-char "warn" branch sat ahead of the token check in an if/elif
# chain and let ~1,860-token targets through with only a warning.
TARGET_TOKEN_BUDGET = 1750  # per target, INCLUDING any Tier 1B block (ADR-176)
WARN_TOKEN_RATIO = 0.9  # advisory early warning, checked only after every violation
MAX_DOMAIN_CHARS = 1200  # Tier 1B allowance (~300 tokens) that universal rules must leave free
# Floor that catches a truncated or mis-parsed SSOT; raise it whenever a principle is added.
MIN_PRINCIPLES = 20

# Single source of truth for the principle corpus; every Tier 1 target is generated from it.
# AGENTS.md used to be this file, but tools following the AGENTS.md convention auto-load it, which
# put ~15.6k real tokens of Tier 2 into always-on context. It is now a generated Tier 1 target.
SSOT_MD = GUIDELINES_MD

# Markers proving a file was written by this tool (current, then legacy pre-ADR-048 headers).
# Anything else is hand-authored and must never be overwritten by a sync.
GENERATED_MARKERS = ("Generated from `", "(Tier 1 Invariants)")


def is_generated_target(text: str) -> bool:
    """True when `text` carries this tool's generated-file header (current or legacy)."""
    return any(marker in text for marker in GENERATED_MARKERS)


def estimate_tokens(text: str) -> int:
    """
    Estimate tokens as chars // 4.

    Calibrated rather than assumed: against OpenAI's cl100k_base and o200k_base tokenizers this
    corpus measures ~4.2 chars/token, so the estimate over-counts by ~6% and errs conservative.
    Other vendors' tokenizers vary; the margin is the reason a simple ratio is acceptable.
    """
    return len(text) // 4


def fsync_dir(dir_path: Path) -> bool:
    """Flush the directory entry so a completed os.replace survives power loss (PRINCIPLE-013 R1).

    No-op on win32, which exposes no directory handle to sync. Kept local to preserve this
    script's standalone clone-and-run execution (PRINCIPLE-011) with zero cross-script imports.
    """
    if sys.platform == "win32":
        return True
    fd = None
    try:
        fd = os.open(str(dir_path), os.O_RDONLY)
        os.fsync(fd)
        return True
    except OSError as e:
        sys.stderr.write(f"[WARN] Could not fsync directory {dir_path}: {e}\n")
        return False
    finally:
        if fd is not None:
            try:
                os.close(fd)
            except OSError:  # hygiene: allow the fd is discarded after the lock was released
                pass


def load_tier_1b_domain_rules(domain_path: Optional[Path] = None) -> str:
    """Load project-specific domain rules from .agents/rules/domain.md if present (PRINCIPLE-001, PRINCIPLE-017)."""
    path = domain_path or DOMAIN_RULES_PATH
    if not path.exists():
        return ""
    content = path.read_text(encoding="utf-8").strip()
    if not content:
        return ""
    if len(content) > MAX_DOMAIN_CHARS:
        raise ValueError(
            f"[PRINCIPLE-001 BUDGET EXCEEDED] Tier 1B domain rules in {path} "
            f"({len(content)} chars) exceed {MAX_DOMAIN_CHARS} char ceiling (~300 tokens)."
        )
    return content


def append_domain_rules(lines: List[str], domain_rules: str):
    """Helper to append Tier 1B domain rules to prompt targets."""
    if not domain_rules:
        return
    lines.append("---")
    lines.append("")
    lines.append("## Project Domain Invariants (Tier 1B):")
    lines.append(domain_rules)
    lines.append("")


# Parsed principles keyed by (strict, file content). Keying on content, not path or mtime, means a
# cached result can never be stale; callers get fresh dicts so mutating one cannot leak elsewhere.
_PARSE_CACHE: Dict[Tuple[bool, str], List[Dict]] = {}


def parse_principles(agents_file: Path, strict: bool = True) -> List[Dict]:
    """Parse the principle SSOT, enforce strict schema validation, reject duplicate IDs, and verify monotonic lifecycle progression."""
    content = agents_file.read_text(encoding="utf-8")
    cached = _PARSE_CACHE.get((strict, content))
    if cached is not None:
        return [dict(p) for p in cached]
    principles = _parse_principles_uncached(content, strict)
    _PARSE_CACHE.clear()  # one entry is enough; bounded memory (PRINCIPLE-010 R4)
    _PARSE_CACHE[(strict, content)] = [dict(p) for p in principles]
    return principles


def _parse_principles_uncached(content: str, strict: bool) -> List[Dict]:
    """Parsing and validation proper; see parse_principles()."""
    # Level-2 headings (phase sections, checklists, appendices) end a principle's block. Without
    # this bound the last principle swallowed everything after it, so text in a trailing
    # checklist could be misread as part of PRINCIPLE-019.
    section_starts = [m.start() for m in re.finditer(r"^## ", content, re.M)]
    # Exactly two hashes: `^##` alone also matched `###` sub-headings, so a "### ... Phase 5" note
    # re-assigned the following principle's phase (ADR-118).
    phase_pattern = r"^##(?!#)\s*([^\n]*Phase\s*(\d+)[:\s]*([^\n]*))"
    phase_matches = list(re.finditer(phase_pattern, content, re.M))

    pattern = r"### (PRINCIPLE-\d+):\s*([^\n]+)"
    matches = list(re.finditer(pattern, content))
    principles = []
    seen_pids = set()

    for i, match in enumerate(matches):
        pid = match.group(1).strip()
        title = match.group(2).strip()
        start = match.end()
        end = matches[i + 1].start() if i + 1 < len(matches) else len(content)
        later_sections = [s for s in section_starts if start < s < end]
        if later_sections:
            end = later_sections[0]
        block = content[start:end]

        problem_match = re.search(r"- \*\*Problem\*\*:\s*([^\n]+)", block)
        concept_match = re.search(r"- \*\*Concept\*\*:\s*([^\n]+)", block)
        invariant_match = re.search(r"- \*\*Invariant\*\*:\s*([^\n]+)", block)
        rules_match = re.search(r"- \*\*Rules\*\*:\s*\n\s*1\.", block)

        if strict:
            if pid in seen_pids:
                raise ValueError(f"[PRINCIPLE-017 SCHEMA VIOLATION] Duplicate principle ID detected: {pid}")
            seen_pids.add(pid)
            if not title:
                raise ValueError(f"[PRINCIPLE-017 SCHEMA VIOLATION] {pid} has an empty title.")
            if not problem_match or not problem_match.group(1).strip():
                raise ValueError(f"[PRINCIPLE-017 SCHEMA VIOLATION] {pid} is missing required '- **Problem**:' section.")
            if not concept_match or not concept_match.group(1).strip():
                raise ValueError(f"[PRINCIPLE-017 SCHEMA VIOLATION] {pid} is missing required '- **Concept**:' section.")
            if not invariant_match or not invariant_match.group(1).strip():
                raise ValueError(f"[PRINCIPLE-017 SCHEMA VIOLATION] {pid} is missing required '- **Invariant**:' capsule.")
            if not rules_match:
                raise ValueError(f"[PRINCIPLE-017 SCHEMA VIOLATION] {pid} is missing required '- **Rules**:' section with numbered rules.")
            # PRINCIPLE-000 R7 / PRINCIPLE-017 R1: every numbered rule names who it binds.
            untagged = [n for n, rest in re.findall(r"^  (\d+)\. \*\*[^*]+\*\*([^\n]*)", block, re.M)
                        if not re.search(r"\*\[(Agent|Maintainer|Agent \+ Maintainer)\]\*", rest)]
            if untagged:
                raise ValueError(f"[PRINCIPLE-017 SCHEMA VIOLATION] {pid} rule(s) {', '.join('R' + n for n in untagged)} "
                                 "name no audience; add *[Agent]*, *[Maintainer]* or *[Agent + Maintainer]*.")
        else:
            seen_pids.add(pid)

        concept = concept_match.group(1).strip() if concept_match else ""
        invariant = invariant_match.group(1).strip() if invariant_match else concept

        # Determine phase based on preceding phase header
        principle_phase_num = 0
        principle_phase_name = ""
        for pm in phase_matches:
            if pm.start() < match.start():
                principle_phase_num = int(pm.group(2))
                principle_phase_name = pm.group(1).strip()
            else:
                break

        principles.append({
            "id": pid,
            "title": title,
            "concept": concept,
            "invariant": invariant,
            "phase_num": principle_phase_num,
            "phase_name": principle_phase_name,
        })

    # Continuous Sequence Audit: validate monotonic lifecycle progression (PRINCIPLE-002)
    if strict:
        if len(principles) < MIN_PRINCIPLES:
            raise ValueError(f"[PRINCIPLE-002 VIOLATION] Expected at least {MIN_PRINCIPLES} principles, found {len(principles)}.")

        current_phase = 1
        for p in principles:
            phase = p.get("phase_num", 0)
            if phase < current_phase:
                raise ValueError(
                    f"[PRINCIPLE-002 VIOLATION] Phase inversion detected at {p['id']}: "
                    f"assigned to Phase {phase}, but prior principles already reached Phase {current_phase}."
                )
            current_phase = phase

        if current_phase != 5:
            raise ValueError(f"[PRINCIPLE-002 VIOLATION] Principles progression did not reach Phase 5 (ended at Phase {current_phase}).")

    return principles


README_TABLE_BEGIN = "<!-- principles:begin (generated from GUIDELINES.md by scripts/sync_principles.py; do not edit) -->"
README_TABLE_END = "<!-- principles:end -->"


def render_readme_table(principles: List[Dict]) -> str:
    """One table per lifecycle phase: ID, title and capsule, exactly as `GUIDELINES.md` states them."""
    lines: List[str] = []
    phase = None
    for p in principles:
        if p["phase_name"] != phase:
            phase = p["phase_name"]
            lines += ([""] if lines else []) + [f"### {phase}", "| Principle | Title | Capsule |", "|---|---|---|"]
        title = re.sub(r"\s*\([^)]*\)$", "", p["title"])  # the subtitle costs README's 30,000-char budget
        cells = [c.replace("|", "\\|") for c in (title, p["invariant"])]
        lines.append(f"| **{p['id']}** | {cells[0]} | {cells[1]} |")
    return "\n".join(lines)


def sync_readme_table(readme_text: str, principles: List[Dict]) -> Optional[str]:
    """`readme_text` with its generated table refreshed, or None when it has no markers."""
    begin, end = readme_text.find(README_TABLE_BEGIN), readme_text.find(README_TABLE_END)
    if begin < 0 or end < begin:
        return None
    return (readme_text[:begin + len(README_TABLE_BEGIN)] + "\n" + render_readme_table(principles)
            + "\n" + readme_text[end:])


def validate_triad_consistency(
    principles: List[Dict],
    readme_file: Path = README_MD,
) -> List[str]:
    """
    Verify the documentation triad's public leg: README.md lists every principle (PRINCIPLE-017).

    This once also compared titles between AGENTS.md and GUIDELINES.md, because the rules lived in
    two hand-maintained copies. That check could only ever catch heading drift, never body drift,
    and ~6 rules had already diverged between the copies. With a single SSOT there is no second
    copy to compare; generated targets are covered by the freshness gate instead.
    """
    errors = []
    if not readme_file.exists():
        errors.append(f"README.md missing at {readme_file}")
        return errors

    r_content = readme_file.read_text(encoding="utf-8")
    if README_TABLE_BEGIN in r_content:
        return []  # a generated table lists every principle by construction; sync checks its freshness
    listed = [p["id"] for p in principles if p["id"] in r_content]
    # A README that documents no principles at all is an adopter's product README, not drift:
    # forcing every adopting project to list AIKit's principle IDs blocked their first sync.
    # A README that documents SOME principles must document all of them.
    if listed:
        errors.extend(f"{p['id']} missing from README.md" for p in principles if p["id"] not in listed)
    return errors


# Every always-injected Tier 1 target: repo-relative path -> heading. One renderer keeps all
# targets in lock-step; five near-identical generators previously had to be edited in parallel,
# and the header text they shared had drifted into contradicting PRINCIPLE-001.
# The operational runbook every Tier 1 header names (ADR-176), and the hosts that load skills
# only from their own folder: generated copy -> source, relative to the repository.
RUNBOOK_PATH = ".agents/skills/aikit/SKILL.md"
# SKILL.md loads whole on every trigger, so detail one kind of task needs lives in topic files it
# names and the agent opens on demand (IDEA-210, ADR-284); each is mirrored like the index.
RUNBOOK_TOPICS = ("projects.md", "delegation.md")
RUNBOOK_MIRRORS: Dict[str, str] = {
    ".claude/skills/aikit/SKILL.md": RUNBOOK_PATH,
    **{f".claude/skills/aikit/{name}": f".agents/skills/aikit/{name}" for name in RUNBOOK_TOPICS},
}

# Claude Code sub-agents, generated from AIKit's role profiles in `.opencode/agents/` so one role
# text serves both hosts (ADR-131). Per role: the tools Claude Code lets it call, and its model;
# read-only roles get no tool that writes, and the cheapest model takes searching and drafting.
OPENCODE_AGENTS_DIR = ".opencode/agents"
CLAUDE_AGENTS_DIR = ".claude/agents"
CLAUDE_AGENT_ROLES: Dict[str, Tuple[str, str]] = {
    "explorer": ("Read, Grep, Glob", "haiku"),
    "architect": ("Read, Grep, Glob", "inherit"),
    "reviewer": ("Read, Grep, Glob, Bash", "sonnet"),
    "worker": ("Read, Grep, Glob, Edit, Write", "haiku"),
    "tester": ("Read, Grep, Glob, Edit, Write, Bash", "sonnet"),
    "coder": ("Read, Grep, Glob, Edit, Write, Bash", "sonnet"),
}


def render_claude_agent(role: str, profile: str) -> str:
    """The Claude Code profile for `role`: the role's own description and instructions, unchanged,
    under Claude Code frontmatter holding the tools and model from `CLAUDE_AGENT_ROLES`."""
    match = re.match(r"^---\n(.*?)\n---\n(.*)$", profile.replace("\r\n", "\n"), re.S)
    if not match:
        raise ValueError(f"{role}: the role profile has no '---' frontmatter block")
    description = re.search(r"^description:\s*(.+)$", match.group(1), re.M)
    if not description:
        raise ValueError(f"{role}: the role profile has no 'description:' line")
    if re.search(r":\s|\s#", description.group(1)):
        # Unquoted YAML: ': ' starts a mapping and ' #' a comment, so the host would not load it.
        raise ValueError(f"{role}: the description holds ': ' or ' #', which breaks its YAML frontmatter")
    tools, model = CLAUDE_AGENT_ROLES[role]
    return (f"---\nname: {role}\ndescription: {description.group(1).strip()}\ntools: {tools}\n"
            f"model: {model}\n---\n<!-- Generated from {OPENCODE_AGENTS_DIR}/{role}.md by "
            f"scripts/sync_principles.py; do not edit. -->\n\n{match.group(2).strip()}\n")


TIER1_TARGETS: Dict[str, str] = {
    # Auto-loaded by tools following the AGENTS.md convention (e.g. OpenAI Codex, GitHub Copilot's
    # coding agent), so it must be a budgeted Tier 1 file, never the full specification.
    "AGENTS.md": "# Agent Instructions (Tier 1)",
    "GEMINI.md": "# Gemini Instructions (Tier 1)",
    ".agents/rules/principles.md": "# Workspace Agent Rules (Tier 1)",
    "CLAUDE.md": "# Claude Instructions (Tier 1)",
    ".cursorrules": "# Cursor Rules (Tier 1)",
    ".github/copilot-instructions.md": "# Copilot Instructions (Tier 1)",
    ".windsurfrules": "# Windsurf Rules (Tier 1)",
    ".clinerules": "# Cline Rules (Tier 1)",
}


def tier1_title(title: str) -> str:
    """Drop a trailing parenthetical subtitle in Tier 1; the full title stays in Tier 2."""
    return re.sub(r"\s*\([^)]*\)\s*$", "", title).strip()


def render_tier1_target(heading: str, principles: List[Dict], domain_rules: str = "") -> str:
    """
    Render one always-injected Tier 1 target (PRINCIPLE-001 R1/R3, PRINCIPLE-017 R2).

    The header deliberately says *when* to read Tier 2, not merely *that* it exists. The former
    "Strictly follow all principles defined in AGENTS.md and GUIDELINES.md" invited agents to
    load ~27k tokens of Tier 2 up front - the exact bloat PRINCIPLE-001 exists to prevent. It also
    marks the file as generated, so a hand edit is not silently overwritten by the next sync.
    """
    lines = [
        heading,
        "",
        # Wording mirrors PRINCIPLE-001 R1 (precedence) and R3 (trigger names) exactly; a test
        # keeps the two in lock-step so every agent receives the same instruction.
        # The generator is deliberately not named here: the PRINCIPLE-017 capsule below names
        # `scripts/sync_principles.py`, and the next line names `sync_principles.py --involved`,
        # so the 32 characters bought nothing and the Tier 1 budget had 3 left (ADR-175). The
        # `Generated from ` prefix is a GENERATED_MARKERS entry and must stay.
        f"> Generated from `{SSOT_MD.name}`; do not edit.",
        # Only 2 of the 8 hosts auto-discover the runbook, so the other 6 need this pointer to
        # the commands the Tier 1 capsules name but do not spell out (ADR-176).
        f"> Runbook: `{RUNBOOK_PATH}` for test, sync, gate and recovery commands.",
        "> Capsules bind; `GUIDELINES.md` wins on conflict. On a contract change, failure or "
        "ambiguity, read the `### PRINCIPLE-NNN:` section of each principle "
        "`sync_principles.py --involved` lists; never the whole file unless asked.",
        "",
        "## Core Principles",
    ]
    for p in principles:
        label = f"{p['id']} {tier1_title(p['title'])}"
        summary = p.get("invariant") or p.get("concept")
        # Plain labels: bold markers are decoration (PRINCIPLE-001 R7), ~4 chars x every line.
        lines.append(f"- {label}: {summary}")
    lines.append("")
    append_domain_rules(lines, domain_rules)
    return "\n".join(lines)


def audit_tier1_budget(principles: List[Dict], domain_rules: str = "") -> int:
    """
    Enforce the Tier 1 context budget on every target (PRINCIPLE-001 R4/R6/R9).

    Two blocking checks, evaluated BEFORE the advisory warning so a warning can never shadow a
    violation:
      1. Total: the rendered target, including any Tier 1B block, must fit TARGET_TOKEN_BUDGET.
      2. Tier 1B headroom: with no domain rules loaded, the universal rules must still leave room
         for a FULL MAX_DOMAIN_CHARS block. Without this, the kit can grow until an adopter who
         follows PRINCIPLE-017 R6 and copies the shipped template is blocked by AIKit's own
         footprint - which is exactly what happened once the token target became enforced.

    Returns the number of violations; each carries a What/Why/Fix diagnostic.
    """
    violations = 0
    warn_at = int(TARGET_TOKEN_BUDGET * WARN_TOKEN_RATIO)
    full_tier1b = "x" * MAX_DOMAIN_CHARS
    print("\n--- Context Budget Audit (PRINCIPLE-001) ---")
    for rel, heading in TIER1_TARGETS.items():
        name = Path(rel).name
        tokens = estimate_tokens(render_tier1_target(heading, principles, domain_rules))
        reserved = estimate_tokens(render_tier1_target(heading, principles, full_tier1b))
        # Tokens a Tier 1B block could still use once the universal rules are in place.
        tier1b_room = TARGET_TOKEN_BUDGET - reserved + MAX_DOMAIN_CHARS // 4
        if tokens > TARGET_TOKEN_BUDGET:
            violations += 1
            print(f"[TOKEN EXCEEDED] {name}: ~{tokens} tokens > {TARGET_TOKEN_BUDGET}-token Tier 1 budget")
        elif not domain_rules and reserved > TARGET_TOKEN_BUDGET:
            violations += 1
            print(f"[TIER 1B HEADROOM] {name}: ~{tokens} tokens leaves room for only "
                  f"~{max(tier1b_room, 0)} of the promised ~{MAX_DOMAIN_CHARS // 4} Tier 1B tokens")
        elif tokens >= warn_at:
            print(f"[BUDGET WARN] {name}: ~{tokens} tokens >= {warn_at} ({int(WARN_TOKEN_RATIO * 100)}% of budget)")
        else:
            print(f"[BUDGET PASS] {name}: ~{tokens} tokens (Tier 1B room: ~{tier1b_room} tokens)")

    if violations:
        sys.stderr.write(
            f"\n[ERROR] {violations} target(s) breach the Tier 1 context budget (PRINCIPLE-001).\n"
            f"Why: always-injected rules cost context on every turn in every IDE, and universal "
            f"rules must leave the full ~{MAX_DOMAIN_CHARS // 4}-token Tier 1B allowance free.\n"
            f"Fix: condense capsule narrative (never mechanisms, numbers or tool names) until each "
            f"target is <= {TARGET_TOKEN_BUDGET} est. tokens including a full Tier 1B block.\n"
        )
    return violations


def sync_all(
    check_only: bool = False,
    exit_on_mismatch: bool = True,
    domain_path: Optional[Path] = None,
    readme_file: Optional[Path] = None,
) -> int:
    """
    Generate every always-injected Tier 1 target from the principle SSOT.

    Returns the number of problems found - 0 means success in both write and check modes. With
    `exit_on_mismatch=True` (the CLI) any problem exits 1 instead of returning. Only AIKit has
    Tier 1 files: projects are worked on from AIKit's folder, whose files every host loads (ADR-127).
    """
    root = ROOT_DIR.resolve()
    ssot_file = SSOT_MD
    agents_file = AGENTS_MD
    readme_file = readme_file or (root / "README.md")
    domain_path = domain_path or (root / ".agents" / "rules" / "domain.md")

    if not ssot_file.exists():
        print(f"Error: Master file {ssot_file} not found.")
        if exit_on_mismatch:
            sys.exit(1)
        return 1

    try:
        principles = parse_principles(ssot_file, strict=True)
    except ValueError as schema_error:
        # Distinguish an unmigrated pre-ADR-048 layout (rules still in AGENTS.md) from a genuine
        # schema defect, and never surface either as a raw traceback (PRINCIPLE-011 R6).
        legacy = False
        if agents_file.exists() and not is_generated_target(agents_file.read_text(encoding="utf-8")):
            try:
                legacy = bool(parse_principles(agents_file, strict=True))
            except ValueError:
                legacy = False
        if legacy:
            sys.stderr.write(
                f"[MIGRATION REQUIRED] The principles still live in AGENTS.md (pre-ADR-048 layout).\n"
                f"Why: {ssot_file.name} is now the single source of truth and AGENTS.md is generated, "
                f"because AGENTS.md-convention agents auto-load it as always-on context.\n"
                f"Fix: move each '### PRINCIPLE-NNN:' section (Concept/Invariant/Rules) from AGENTS.md "
                f"into {ssot_file.name}, delete AGENTS.md, then re-run this script to regenerate it.\n"
            )
        else:
            sys.stderr.write(
                f"[SCHEMA ERROR] {schema_error}\n"
                f"Why: every principle in {ssot_file.name} needs '### PRINCIPLE-NNN:', Problem, Concept, "
                f"Invariant and numbered Rules, each rule tagged with its audience (PRINCIPLE-017 R1).\n"
                f"Fix: complete the section named above, then re-run.\n"
            )
        if exit_on_mismatch:
            sys.exit(1)
        return 1
    print(f"Parsed {len(principles)} active principles from {ssot_file.name}:")
    for p in principles:
        print(f" - {p['id']}: {p['title']}")

    # Documentation triad, public leg: README.md must list every principle in the SSOT.
    triad_errors = validate_triad_consistency(principles, readme_file=readme_file)
    if triad_errors:
        # ASCII bullets: this CLI does not reconfigure stdout, and '•' printed as garbage on cp1254.
        err_msg = "\n".join([f"  - {e}" for e in triad_errors])
        print(f"\n[TRIAD DRIFT DETECTED]:\n{err_msg}")
        if exit_on_mismatch:
            sys.exit(1)
        return len(triad_errors)
    else:
        readme_text = readme_file.read_text(encoding="utf-8") if readme_file.exists() else ""
        if any(p["id"] in readme_text for p in principles):
            print(f"[OK] Verified README.md lists every principle in {ssot_file.name}")
        else:
            # Mode transparency (PRINCIPLE-011 R3): say why the check did not apply.
            print("[INFO] README.md documents no principles (adopter README); parity check not applicable")

    try:
        domain_rules = load_tier_1b_domain_rules(domain_path)
    except ValueError as budget_error:
        # An oversized domain.md is an adopter's likeliest first error; it used to end in a raw
        # traceback (PRINCIPLE-011 R6, PRINCIPLE-017 R6).
        sys.stderr.write(
            f"[DOMAIN RULES TOO LONG] {budget_error}\n"
            f"Why: Tier 1B is injected into every Tier 1 file and must fit the reserved "
            f"{MAX_DOMAIN_CHARS} characters (PRINCIPLE-017 R6).\n"
            f"Fix: shorten .agents/rules/domain.md to at most {MAX_DOMAIN_CHARS} characters, "
            f"moving detail to knowledge/, then re-run.\n"
        )
        if exit_on_mismatch:
            sys.exit(1)
        return 1
    if domain_rules:
        print(f"[LOADED] Injected Tier 1B domain rules ({len(domain_rules)} chars)")

    targets = {
        root / rel: render_tier1_target(heading, principles, domain_rules)
        for rel, heading in TIER1_TARGETS.items()
    }

    budget_violations = audit_tier1_budget(principles, domain_rules)
    if budget_violations > 0:
        if exit_on_mismatch:
            sys.exit(1)
        return budget_violations

    # Never overwrite a file this tool did not generate, and decide that for EVERY target before
    # writing ANY, so a protected file cannot leave a half-synced tree (PRINCIPLE-013 R6). This
    # protects an adopter's own CLAUDE.md, and a pre-ADR-048 AGENTS.md that still holds the rules.
    foreign = []
    for target_path, expected_content in targets.items():
        if target_path.exists():
            current = target_path.read_text(encoding="utf-8")
            if current.strip() != expected_content.strip() and not is_generated_target(current):
                foreign.append(str(target_path.relative_to(root)))
    if foreign:
        sys.stderr.write(
            f"\n[PROTECTED] Refusing to overwrite hand-authored file(s): {', '.join(foreign)}\n"
            f"Why: sync only overwrites files it generated, so your own instructions are never lost. "
            f"Older AIKit layouts kept the full rules in AGENTS.md; AGENTS.md is now generated from "
            f"{ssot_file.name}.\n"
            f"Fix: move project-specific instructions into .agents/rules/domain.md (Tier 1B, "
            f"<={MAX_DOMAIN_CHARS} chars) and principle changes into {ssot_file.name}, then delete or "
            f"rename the file(s) above and re-run.\n"
        )
        if exit_on_mismatch:
            sys.exit(1)
        return len(foreign)

    # README's principle table is generated between markers (PRINCIPLE-005 R4, PRINCIPLE-017 R4):
    # the hand-written rows had drifted from the capsules for 19 of 20 principles. Only the block
    # between the markers is rewritten; a README without them (an adopter's) is left alone.
    written = dict(targets)
    # Only the README of the repository being synced: a README outside ROOT_DIR (a test sandbox
    # reading the real one) is never written (PRINCIPLE-015 R4).
    if readme_file.exists() and readme_file.resolve().is_relative_to(root):
        readme_expected = sync_readme_table(readme_file.read_text(encoding="utf-8"), principles)
        if readme_expected is not None:
            written[readme_file] = readme_expected
    # Hosts that load skills only from their own folder get an exact copy of the one runbook, so
    # an edit to it cannot leave theirs stale (ADR-128); `--check` reports a drifted copy.
    for mirror, source in RUNBOOK_MIRRORS.items():
        if (root / source).is_file():
            written[root / mirror] = (root / source).read_text(encoding="utf-8")
    for role in CLAUDE_AGENT_ROLES:
        profile = root / OPENCODE_AGENTS_DIR / f"{role}.md"
        if profile.is_file():
            written[root / CLAUDE_AGENTS_DIR / f"{role}.md"] = render_claude_agent(
                role, profile.read_text(encoding="utf-8"))

    mismatches = 0
    for target_path, expected_content in written.items():
        if not check_only:
            target_path.parent.mkdir(parents=True, exist_ok=True)
        if target_path.exists():
            current_content = target_path.read_text(encoding="utf-8")
            if current_content.strip() == expected_content.strip():
                print(f"[OK] Synced: {target_path.relative_to(root)}")
                continue

        mismatches += 1
        if check_only:
            print(f"[OUT OF SYNC]: {target_path.relative_to(root)}")
        else:
            # Atomic fsync write (PRINCIPLE-006, PRINCIPLE-013)
            tmp_target = target_path.with_suffix(target_path.suffix + f".tmp_{os.getpid()}")
            with open(tmp_target, "w", encoding="utf-8") as f:
                f.write(expected_content)
                f.flush()
                os.fsync(f.fileno())
            os.replace(tmp_target, target_path)
            fsync_dir(target_path.parent)
            print(f"[UPDATED]: {target_path.relative_to(root)}")

    if check_only and mismatches > 0:
        print(f"\n{mismatches} file(s) out of sync with {ssot_file.name}.")
        if exit_on_mismatch:
            sys.exit(1)
        return mismatches

    readme_note = " and the README principle table" if len(written) > len(targets) else ""
    print(f"\nAll {len(targets)} AI guideline targets{readme_note} are synchronized successfully "
          f"({mismatches} file(s) updated).")
    # The return value always counts PROBLEMS, so 0 means success in every mode. It previously
    # returned the number of files updated in write mode, making a successful sync look like a
    # failure to any programmatic caller.
    return 0


INVOLVEMENT_FALLBACK = "PRINCIPLE-003"


def involved_principles(principles: List[Dict], text: str) -> List[str]:
    """
    Compute which principles a situation involves (PRINCIPLE-001 R3), identically for every agent.

    A principle is involved when a backtick-quoted name in its capsule (a file, path, script or
    command) occurs verbatim in `text`, or when `text` contains its ID. `text` is the paths the
    agent will change, the commands it will run, and any failing output. With no match the answer
    is PRINCIPLE-003. Matching on names rather than on loose "terms" is the point: words like
    "test" or "gate" occur in nearly every capsule, so letting each model judge what counts as a
    term gave different models different reading lists.
    """
    involved = set(re.findall(r"PRINCIPLE-\d{3}", text))
    known = {p["id"] for p in principles}
    involved &= known
    for p in principles:
        names = [n.strip() for n in re.findall(r"`([^`]+)`", p.get("invariant", ""))]
        if any(name and name in text for name in names):
            involved.add(p["id"])
    return sorted(involved) or [INVOLVEMENT_FALLBACK]


def principle_sections(ssot_text: str) -> Dict[str, str]:
    """Each `### PRINCIPLE-NNN:` section's text, ending at the next heading of level 2 or 3."""
    sections: Dict[str, str] = {}
    for match in re.finditer(r"^### (PRINCIPLE-\d{3}):", ssot_text, re.M):
        rest = ssot_text[match.end():]
        end = re.search(r"^#{2,3} ", rest, re.M)
        sections[match.group(1)] = rest[:end.start()] if end else rest
    return sections


def citing_principles(ssot_text: str, pid: str) -> List[str]:
    """
    The principles a change to `pid` must be checked against (PRINCIPLE-000 R3): those whose
    section cites `pid`, and those `pid`'s own section cites. Computed, so every agent lists the
    same set; a raw `git grep` returns files and lines, and each model mapped them differently.
    """
    sections = principle_sections(ssot_text)
    cited_by = {other for other, body in sections.items() if other != pid and re.search(rf"\b{pid}\b", body)}
    cites = set(re.findall(r"PRINCIPLE-\d{3}", sections.get(pid, ""))) & set(sections) - {pid}
    return sorted(cited_by | cites)


def _adr_blocks(decisions: str) -> Dict[str, str]:
    """ADR ID -> its text, for every `### ADR-NNN:` heading."""
    return {m.group(1): m.group(2) for m in
            re.finditer(r"^### (ADR-\d+):(.*?)(?=^### ADR-|\Z)", decisions, re.M | re.S)}


def checklist_sections(ssot_text: str) -> str:
    """Extract Pre-Flight and Post-Flight checklist text if present."""
    matches = re.findall(r"^###\s*[🛫🛬]?\s*(?:Pre-Flight|Post-Flight) Checklist.*?(?=^###|\Z)",
                         ssot_text, re.M | re.S)
    return "\n".join(matches)


def changed_principles(old_text: str, new_text: str) -> List[str]:
    """Principles whose `### PRINCIPLE-NNN:` section or governed checklists differ (PRINCIPLE-000 R3)."""
    def norm(section: Optional[str]) -> Optional[str]:
        return None if section is None else "\n".join(l.rstrip() for l in section.strip().splitlines())
    old, new = principle_sections(old_text), principle_sections(new_text)
    changed = sorted(pid for pid in set(old) | set(new) if norm(old.get(pid)) != norm(new.get(pid)))
    if norm(checklist_sections(old_text)) != norm(checklist_sections(new_text)):
        if "PRINCIPLE-001" not in changed and "PRINCIPLE-001" in (set(old) | set(new)):
            changed.append("PRINCIPLE-001")
            changed.sort()
    return changed


def cross_check_errors(old_text: str, new_text: str, old_decisions: str, new_decisions: str) -> List[str]:
    """
    PRINCIPLE-000 R3 made decidable: every principle whose section changed since the last commit
    needs an ADR added since then whose `Cross-principle check:` line names every principle
    `--citing` prints for it. Completeness used to rest on each model's own list.
    """
    changed = changed_principles(old_text, new_text)
    if not changed:
        return []
    # Parsed once: re-parsing the old register for every ADR took ~0.9s at 128 ADRs (ADR-128).
    old_ids = set(_adr_blocks(old_decisions))
    added = [body for adr, body in _adr_blocks(new_decisions).items() if adr not in old_ids]
    if not added:
        return [f"{', '.join(changed)} changed but no ADR was added to knowledge/decisions.md (PRINCIPLE-004 R4)"]
    lines = [m.group(1) for body in added for m in re.finditer(r"Cross-principle check:([^\n]*)", body)]
    if not lines:
        return [f"{', '.join(changed)} changed but no added ADR has a 'Cross-principle check:' line"]
    named = set(re.findall(r"PRINCIPLE-\d{3}", " ".join(lines)))
    errors = []
    for pid in changed:
        source = new_text if pid in principle_sections(new_text) else old_text
        missing = [p for p in citing_principles(source, pid) if p not in named]
        if missing:
            errors.append(f"{pid} changed; its Cross-principle check line omits {', '.join(missing)} "
                          f"(python scripts/sync_principles.py --citing {pid})")
    return errors


def git_head_text(rel_path: str) -> Optional[str]:
    """`rel_path` as committed at HEAD, or None when git, a commit or the file is missing."""
    import subprocess  # lazy: only --check needs git (PRINCIPLE-010 --help budget)
    try:
        res = subprocess.run(["git", "show", f"HEAD:{rel_path}"], cwd=str(ROOT_DIR), capture_output=True,
                             text=True, encoding="utf-8", errors="replace", timeout=10)
    except (OSError, subprocess.SubprocessError):
        return None
    return res.stdout if res.returncode == 0 else None


def print_help():
    """Print command line usage for sync_principles.py."""
    print("""AIKit Principles Auto-Sync Tool (PRINCIPLE-017)

Usage:
  python scripts/sync_principles.py [OPTIONS]

Options:
  --check          Verify, without writing, that all guideline targets are fresh and that every principle
                   changed since the last commit has an ADR naming its --citing set (PRINCIPLE-000 R3);
                   exits 1 on either
  --domain <path>  Specify custom path to Tier 1B domain rules file (default: .agents/rules/domain.md)
  --involved TEXT  List the principles TEXT involves (PRINCIPLE-001 R3); must be the first argument,
                   and every later argument is TEXT: paths to change, commands to run, failing output
  --citing ID      List the principles a change to principle ID must be checked against: those
                   citing it and those it cites (PRINCIPLE-000 R3); must be the first argument
  -h, --help      Show this help message and exit
""")


if __name__ == "__main__":
    # --involved takes free text that may itself contain flags (failing output often mentions
    # --help), so it must come first and nothing after it is parsed as an option.
    if len(sys.argv) > 1 and sys.argv[1] == "--involved":
        if len(sys.argv) < 3:
            print("[INVALID USAGE] --involved requires text to match.", file=sys.stderr)
            print("Why: involvement is computed from the paths, commands or failing output given.", file=sys.stderr)
            print("Fix: python scripts/sync_principles.py --involved scripts/dogfood.py \"pytest failed\"", file=sys.stderr)
            sys.exit(2)
        for pid in involved_principles(parse_principles(SSOT_MD, strict=True), " ".join(sys.argv[2:])):
            print(pid)
        sys.exit(0)

    if len(sys.argv) > 1 and sys.argv[1] == "--citing":
        _text = SSOT_MD.read_text(encoding="utf-8")
        _pid = sys.argv[2] if len(sys.argv) == 3 else ""
        if _pid not in principle_sections(_text):
            print(f"[INVALID USAGE] --citing needs one existing principle ID, got '{_pid}'.", file=sys.stderr)
            print("Why: the cross-principle set of PRINCIPLE-000 R3 is computed for one principle.", file=sys.stderr)
            print("Fix: python scripts/sync_principles.py --citing PRINCIPLE-004", file=sys.stderr)
            sys.exit(2)
        for _cited in citing_principles(_text, _pid):
            print(_cited)
        sys.exit(0)

    if "-h" in sys.argv or "--help" in sys.argv:
        print_help()
        sys.exit(0)

    _known = {"--check", "--domain", "--help", "-h"}
    _argv = sys.argv[1:]
    _unknown = []
    _i = 0
    while _i < len(_argv):
        _tok = _argv[_i]
        if _tok.startswith("-"):
            if _tok not in _known:
                _unknown.append(_tok)
            elif _tok == "--domain":
                _i += 1  # consume the path value
        _i += 1
    if _unknown:
        print(f"[INVALID USAGE] Unrecognized option(s): {', '.join(_unknown)}", file=sys.stderr)
        print("Why: unrecognized flags would otherwise trigger an unintended full rule rewrite.", file=sys.stderr)
        print("Fix: run 'python scripts/sync_principles.py --help' to list valid options.", file=sys.stderr)
        sys.exit(2)

    check_mode = "--check" in sys.argv
    custom_domain = None
    if "--domain" in sys.argv:
        try:
            idx = sys.argv.index("--domain")
            custom_domain = Path(sys.argv[idx + 1])
        except (IndexError, ValueError):
            sys.stderr.write("Error: --domain requires a file path argument.\n")
            sys.exit(1)


    sync_all(check_only=check_mode, exit_on_mismatch=True, domain_path=custom_domain)

    if check_mode:
        _decisions_path = ROOT_DIR / "knowledge" / "decisions.md"
        _old_rules, _old_decisions = git_head_text("GUIDELINES.md"), git_head_text("knowledge/decisions.md")
        if _old_rules is None:
            # Documented default (PRINCIPLE-003 R6): no committed copy to compare, e.g. the commit
            # that first adds GUIDELINES.md to an adopter repository.
            print("[WARN] No committed GUIDELINES.md at HEAD; cross-principle check skipped (PRINCIPLE-000 R3).")
        else:
            _errors = cross_check_errors(
                _old_rules, SSOT_MD.read_text(encoding="utf-8"), _old_decisions or "",
                _decisions_path.read_text(encoding="utf-8") if _decisions_path.exists() else "")
            if _errors:
                print(f"[FAIL] Cross-principle check incomplete ({len(_errors)}):")
                for _error in _errors:
                    print(f"   - {_error}")
                print("   Why: a rule change not checked against the rules citing it can contradict them.")
                print("   Fix: add an ADR containing a 'Cross-principle check:' line naming each listed principle.")
                sys.exit(1)
            print("[OK] Every changed principle has an ADR naming its --citing set (PRINCIPLE-000 R3)")
