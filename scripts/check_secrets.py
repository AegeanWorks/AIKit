#!/usr/bin/env python3
"""
Secret & Sensitive Data Hygiene Scanner (PRINCIPLE-019)

Secret leakage is the one defect class with no clean rollback: once a credential is pushed,
logged, or sent to a third party, it must be rotated, not reverted. This scanner is therefore a
*pre*-commit gate, the fourth leg of the PRINCIPLE-018 Rule 3 delivery triad.

It scans two surfaces that AI agents leak through in practice:

  1. Staged content (`git diff --cached`), or named files, or the whole tracked tree.
  2. Agent working memory - `.agents/task_ledger.json` free-text fields and the dogfood log.
     This repository's own PRINCIPLE-007 workflow persists `--why` / `--benefits` / `--risks` /
     `--mitigation` straight into a git-tracked ledger, so an agent that quotes a key while
     explaining its reasoning commits that key to history permanently.

Detection is pattern-first (known credential shapes have near-zero false-positive rates) with a
conservative high-entropy fallback for assignment-shaped lines only. Deliberate exceptions use an
inline `# aikit:allow-secret` pragma or the ALLOWLIST_SUBSTRINGS set - never a silenced scanner.

Zero external dependencies (standard library only).

Usage:
  python scripts/check_secrets.py [--staged | --all | --file <path> | --commits <range>] [--verbose]
Exit codes:
  0 clean    1 potential secret found    2 CLI argument misuse
"""

import math
import re
import subprocess
import sys
from pathlib import Path
from typing import Dict, Iterable, List, Optional, Tuple

ROOT_DIR = Path(__file__).resolve().parent.parent
# Agent working memory, relative to the scanned repository: AIKit's ledger and dogfood log, or a
# project's `.aikit/` ledger (ADR-121). Whichever exist are scanned.
AGENT_MEMORY_PATHS = (
    Path(".agents") / "task_ledger.json",
    Path(".agents") / "dogfood_last_run.log",
    Path(".aikit") / "task_ledger.json",
)

PRAGMA = "aikit:allow-secret"
PROC_TIMEOUT = 15

# Known credential shapes. Pattern-first detection keeps false positives near zero, which is what
# keeps the gate trusted; an untrusted gate gets bypassed and protects nothing.
SECRET_PATTERNS: Tuple[Tuple[str, str], ...] = (
    ("AWS access key id", r"\b(?:AKIA|ASIA)[0-9A-Z]{16}\b"),
    ("GitHub token", r"\bgh[pousr]_[A-Za-z0-9]{36,}\b"),
    ("GitHub fine-grained token", r"\bgithub_pat_[A-Za-z0-9_]{22,}\b"),
    ("Slack token", r"\bxox[abprs]-[A-Za-z0-9-]{10,}\b"),
    ("Google API key", r"\bAIza[0-9A-Za-z_\-]{35}\b"),
    # The newer Google AI Studio key format (`AQ.` + 50 chars): a bare one has no key name for the
    # entropy rule to catch (ADR-132).
    ("Google AI Studio key", r"\bAQ\.[0-9A-Za-z_\-]{30,}"),
    ("Stripe secret key", r"\b(?:sk|rk)_(?:live|test)_[0-9A-Za-z]{20,}\b"),
    ("OpenAI-style API key", r"\bsk-(?:proj-)?[A-Za-z0-9_\-]{32,}\b"),
    ("Anthropic-style API key", r"\bsk-ant-[A-Za-z0-9_\-]{32,}\b"),
    # Widened in ADR-173. Every shape below is anchored on a literal vendor prefix, so it keeps
    # the near-zero false-positive property the gate's trust depends on; a bare-length or PII
    # pattern would not, and is deliberately absent.
    ("GitLab personal access token", r"\bglpat-[A-Za-z0-9_\-]{20,}"),
    ("npm access token", r"\bnpm_[A-Za-z0-9]{36}\b"),
    ("PyPI upload token", r"\bpypi-AgEIcHlwaS5vcmc[A-Za-z0-9_\-]{50,}"),
    ("SendGrid API key", r"\bSG\.[A-Za-z0-9_\-]{22}\.[A-Za-z0-9_\-]{43}\b"),
    ("Hugging Face token", r"\bhf_[A-Za-z0-9]{34,}\b"),
    ("Google OAuth client secret", r"\bGOCSPX-[A-Za-z0-9_\-]{28}\b"),
    ("Mailgun API key", r"\bkey-[0-9a-f]{32}\b"),
    ("Telegram bot token", r"\b\d{8,10}:AA[A-Za-z0-9_\-]{30,}"),
    ("Docker Hub access token", r"\bdckr_pat_[A-Za-z0-9_\-]{20,}"),
    ("Notion integration token", r"\bsecret_[A-Za-z0-9]{43}\b"),
    ("Linear API key", r"\blin_api_[A-Za-z0-9]{40}\b"),
    ("Slack incoming webhook",
     r"https://hooks\.slack\.com/services/T[A-Za-z0-9]+/B[A-Za-z0-9]+/[A-Za-z0-9]{20,}"),
    ("Azure storage account key", r"\bAccountKey=[A-Za-z0-9+/=]{60,}"),
    ("JSON Web Token", r"\beyJ[A-Za-z0-9_\-]{10,}\.[A-Za-z0-9_\-]{10,}\.[A-Za-z0-9_\-]{10,}\b"),
    ("Private key block",
     r"-----BEGIN (?:RSA |EC |OPENSSH |PGP |DSA |ENCRYPTED |SSH2 ENCRYPTED )?PRIVATE KEY-----"),
    ("Password in URL", r"\b[a-zA-Z][a-zA-Z0-9+.\-]*://[^/\s:@]+:[^/\s:@]+@"),
    ("Authorization header value", r"\bAuthorization\s*[:=]\s*[\"']?(?:Bearer|Basic)\s+[A-Za-z0-9._\-=/+]{16,}"),
    ("Hardcoded password assignment", r"\b(?:password|passwd|secret|api_key|apikey|access_token|auth_token|private_key)\s*[:=]\s*[\"'][^\"'\s]{8,}[\"']"),
)

# A value that is wholly an interpolation or a template placeholder is an indirection, not a
# literal credential. This must be honoured by the pattern detectors too, not only the entropy
# fallback: `password = "${DB_PASS}"` is correct code, and a scanner that blocks correct code  # aikit:allow-secret
# gets bypassed, which protects nothing.
INTERPOLATION_ONLY_RE = re.compile(
    r"""[:=]\s*["']?\s*(?:\$\{[^}]*\}|\$[A-Za-z_][A-Za-z0-9_]*|\{\{[^}]*\}\}|"""
    r"""\{[A-Za-z_][A-Za-z0-9_]*\}|%\([^)]*\)s|<[^>]*>)\s*["']?\s*$"""
)

# Assignment-shaped lines whose value may be a raw secret; entropy is only applied here.
ASSIGNMENT_RE = re.compile(
    r"(?i)\b([A-Z0-9_]*(?:KEY|TOKEN|SECRET|PASSWORD|PASSWD|CREDENTIAL|AUTH)[A-Z0-9_]*)\s*[:=]\s*[\"']?([^\s\"',;]{16,})[\"']?"
)
# A unified-diff hunk header; group 1 is the first line number on the new side.
HUNK_RE = re.compile(r"^@@ -\d+(?:,\d+)? \+(\d+)(?:,\d+)? @@")
# A quoted token long enough to be a generated key; `looks_random` decides whether it is one.
BARE_LITERAL_RE = re.compile(r"[\"']([A-Za-z0-9_\-]{40,})[\"']")

# Allowlisting is risk-tiered, because a weak word must never veto a high-confidence match.
# A red-check caught this: "AKIAIOSFODNN7EXAMPLE" was missed purely because the line contained  # aikit:allow-secret
# the word "example", which would equally have hidden a live key on an "# example usage" line.
#
# STRONG markers are unambiguous placeholders and the explicit pragma: they suppress everything.
# WEAK markers suppress only the low-confidence entropy fallback, never a pattern match.
STRONG_ALLOWLIST = frozenset({
    PRAGMA, "your-key-here", "your_key_here", "<your", "placeholder", "changeme",
    "redacted", "<redacted>", "xxxxxxxx", "0000000000",
})
WEAK_ALLOWLIST = frozenset({"example", "sample", "dummy", "fake", "test-token"})

# Retained for callers and tests that want the full token set.
ALLOWLIST_SUBSTRINGS = STRONG_ALLOWLIST | WEAK_ALLOWLIST

# Only the scanner's own pattern table is exempt. Documentation and instruction files can carry a
# pasted credential, so skipping them made `--all`'s "every tracked file" claim false (ADR-163).
SKIP_PATH_PARTS = ("scripts/check_secrets.py",)

TEXT_SUFFIXES = frozenset({
    ".py", ".md", ".txt", ".json", ".yml", ".yaml", ".toml", ".cfg", ".ini", ".env",
    ".sh", ".ps1", ".js", ".ts", ".rs", ".go", ".java", ".rb", ".log", "",
})


def shannon_entropy(value: str) -> float:
    """Bits of entropy per character; random credentials score high, English prose low."""
    if not value:
        return 0.0
    counts: Dict[str, int] = {}
    for ch in value:
        counts[ch] = counts.get(ch, 0) + 1
    length = len(value)
    return -sum((c / length) * math.log2(c / length) for c in counts.values())


def is_strongly_allowlisted(line: str) -> bool:
    """An explicit pragma or an unambiguous placeholder suppresses every detector."""
    lowered = line.lower()
    return any(token in lowered for token in STRONG_ALLOWLIST)


def is_weakly_allowlisted(line: str) -> bool:
    """A hint like "example" suppresses only the low-confidence entropy fallback."""
    lowered = line.lower()
    return any(token in lowered for token in WEAK_ALLOWLIST)


def scan_text(label: str, text: str) -> List[Tuple[str, int, str, str]]:
    """Return (label, line_no, detector, excerpt) for every finding in a blob of text."""
    findings: List[Tuple[str, int, str, str]] = []
    for lineno, line in enumerate(text.splitlines(), 1):
        if is_strongly_allowlisted(line):
            continue
        stripped = line.strip()
        if not stripped:
            continue

        if INTERPOLATION_ONLY_RE.search(line):
            continue  # the value is an indirection, not a credential

        matched = False
        for detector, pattern in SECRET_PATTERNS:
            hit = re.search(pattern, line)
            if hit:
                findings.append((label, lineno, detector, redact(line, hit.start(), hit.end())))
                matched = True
                break
        if matched:
            continue

        # Conservative entropy fallback: only on assignment-shaped lines, so prose and hashes
        # committed as data do not trip the gate.
        if is_weakly_allowlisted(line):
            continue  # pattern detectors already ran; skip only the entropy fallback
        match = ASSIGNMENT_RE.search(line)
        if match:
            name, value = match.group(1), match.group(2)
            if value.startswith(("$", "{", "%", "<")) or "os.getenv" in line or "os.environ" in line:
                continue  # an indirection, not a literal
            if len(value) >= 20 and shannon_entropy(value) >= 3.8:
                findings.append((label, lineno, f"high-entropy value for {name}",
                                 redact(line, match.start(2), match.end(2))))
                continue
        # A long random-looking string literal with no key name beside it: a real Gemini key, split
        # in two inside a test, passed every check above and was committed (ADR-133).
        bare = BARE_LITERAL_RE.search(line)
        if bare and looks_random(bare.group(1)):
            findings.append((label, lineno, "high-entropy string literal",
                             redact(line, bare.start(1), bare.end(1))))
    return findings


def looks_random(value: str) -> bool:
    """A token shaped like a generated key: mixed case and digits, and high entropy. Hex digests
    and long identifiers lack the mix, so they do not trip it."""
    return (shannon_entropy(value) >= 4.5 and any(c.islower() for c in value)
            and any(c.isupper() for c in value) and any(c.isdigit() for c in value))


def redact(line: str, start: int, end: int) -> str:
    """
    The line with the secret span cut to its first 4 characters plus `***` (PRINCIPLE-019 R4).
    Findings used to print the raw line, so the scanner itself echoed every credential it caught
    into the terminal, the transcript and the dogfood log.
    """
    return (line[:start] + line[start:end][:4] + "***" + line[end:]).strip()[:88]


SCRUB_PLACEHOLDER = "[REDACTED]"


def scrub_text(text: str) -> Tuple[str, List[str]]:
    """
    `text` with every credential-shaped span replaced by `[REDACTED]`, and the detectors hit.

    Used at the boundaries that write free text into tracked state, because PRINCIPLE-019 R5
    makes a leaked credential unrecoverable: refusing or scrubbing the write is worth more than
    reporting it afterwards. Only `SECRET_PATTERNS` run here, never the entropy fallback -
    prose legitimately carries commit hashes and digests, and a scrubber that ate them would be
    worked around rather than fixed (ADR-173). The placeholder is in `STRONG_ALLOWLIST`, so
    scrubbed text is clean when the scanner reads it back.
    """
    detectors: List[str] = []
    scrubbed = text
    for detector, pattern in SECRET_PATTERNS:
        scrubbed, hits = re.subn(pattern, SCRUB_PLACEHOLDER, scrubbed)
        if hits:
            detectors.append(detector)
    return scrubbed, detectors


def should_skip(path_str: str) -> bool:
    normalized = path_str.replace("\\", "/")
    return normalized in SKIP_PATH_PARTS


def git_output(args: List[str], repo: Path = ROOT_DIR) -> Optional[str]:
    # core.quotePath=false: git otherwise prints a non-ASCII path quoted and octal-escaped
    # ("\305\237ifre.txt"), so a diff header no longer read as `+++ b/<path>` and the finding lost
    # its file name (ADR-182).
    try:
        res = subprocess.run(
            ["git", "-c", "core.quotePath=false", *args], cwd=str(repo), capture_output=True,
            text=True, encoding="utf-8", errors="replace", timeout=PROC_TIMEOUT,
        )
    except (OSError, subprocess.SubprocessError):
        return None
    return res.stdout if res.returncode == 0 else None


def scan_staged(gaps: Optional[List[str]] = None,
                repo: Path = ROOT_DIR) -> List[Tuple[str, int, str, str]]:
    """Scan staged content only - the surface about to become permanent history."""
    diff = git_output(["diff", "--cached", "--unified=0"], repo)
    if diff is None:
        if gaps is not None:
            gaps.append("git diff --cached failed, so the staged changes were not scanned")
        return []
    return scan_diff(diff, "<staged>")


def scan_diff(diff: str, default_label: str = "<diff>") -> List[Tuple[str, int, str, str]]:
    """Every added line of a unified diff, labelled by its file. Pure: removed lines are history
    already, and context lines are scanned where they were added."""
    findings = []
    current, lineno = default_label, 0
    for line in diff.splitlines():
        if line.startswith("+++ "):
            current = line[6:].strip() if line.startswith("+++ b/") else default_label
            continue
        hunk = HUNK_RE.match(line)
        if hunk:
            lineno = int(hunk.group(1))
            continue
        if line.startswith("+"):
            if not should_skip(current):
                findings.extend((label, lineno, detector, excerpt)
                                for label, _, detector, excerpt in scan_text(current, line[1:]))
            lineno += 1
    return findings


def scan_commits(rev_range: str, gaps: Optional[List[str]] = None,
                 repo: Path = ROOT_DIR) -> List[Tuple[str, int, str, str]]:
    """
    Every line the commits in `rev_range` add: what a push uploads. The working tree is not, so a
    key committed and then deleted in an uncommitted edit passed a working-tree scan (ADR-145).
    """
    log = git_output(["log", "-p", "-m", "--format=", "--unified=0", "--no-color",
                      "--no-ext-diff", rev_range, "--"], repo)
    if log is None:
        if gaps is not None:
            gaps.append(f"git log {rev_range} failed, so those commits were not scanned")
        return []
    # -m shows a merge-resolution hunk once per parent; keep one finding per coordinate.
    return list(dict.fromkeys(scan_diff(log, f"<{rev_range}>")))


def iter_tracked_files(gaps: Optional[List[str]] = None, repo: Path = ROOT_DIR,
                        include_self: bool = False) -> Iterable[Path]:
    # NUL-separated: a newline-separated listing quotes any path git considers unusual, and the
    # quoted name ended in `.txt"`, failed the suffix test and was skipped without a gap - every
    # tracked file with a non-ASCII name, silently, under `--all` (ADR-182).
    listing = git_output(["ls-files", "-z"], repo)
    if listing is None:
        if gaps is not None:
            gaps.append("git ls-files failed, so no tracked file was scanned")
        return []
    for rel in listing.split("\0"):
        if not rel or (not include_self and should_skip(rel)):
            continue
        path = repo / rel
        if path.suffix.lower() in TEXT_SUFFIXES and path.is_file():
            yield path


def scan_all(gaps: Optional[List[str]] = None,
             repo: Path = ROOT_DIR) -> List[Tuple[str, int, str, str]]:
    findings = []
    # The scanner's own file carries line pragmas on its detector examples, so --all can scan it.
    for path in iter_tracked_files(gaps, repo, include_self=True):
        try:
            findings.extend(scan_text(str(path.relative_to(repo)),
                                      path.read_text(encoding="utf-8", errors="replace")))
        except OSError as e:
            if gaps is not None:
                gaps.append(f"{path.relative_to(repo)} could not be read: {e}")
    return findings


def scan_agent_memory(gaps: Optional[List[str]] = None,
                      repo: Path = ROOT_DIR) -> List[Tuple[str, int, str, str]]:
    """
    PRINCIPLE-019 Rule 3: agent working memory is tracked output. The ledger's free-text impact
    fields are committed, so a credential quoted while explaining reasoning becomes permanent.
    """
    findings = []
    for path in (repo / rel for rel in AGENT_MEMORY_PATHS):
        if not path.exists():
            continue
        try:
            findings.extend(scan_text(f"agent-memory:{path.name}",
                                      path.read_text(encoding="utf-8", errors="replace")))
        except OSError as e:
            if gaps is not None:
                gaps.append(f"agent memory {path.name} could not be read: {e}")
    return findings


def run_scan(mode: str = "staged", target: Optional[Path] = None,
             verbose: bool = False, repo: Path = ROOT_DIR, commits: Optional[str] = None) -> int:
    """Scan the requested surface plus agent memory, reporting tersely (PRINCIPLE-012 R4)."""
    print("=" * 58)
    print("SECRET & SENSITIVE DATA SCAN (PRINCIPLE-019)")
    print("=" * 58)

    gaps: List[str] = []
    if mode == "file" and target is not None:
        if not target.exists():
            print(f"[FAIL] No such file: {target}", file=sys.stderr)
            return 1
        try:
            label = str(target.resolve().relative_to(repo.resolve()))
        except ValueError:
            label = target.name
        try:
            findings = scan_text(label, target.read_text(encoding="utf-8", errors="replace"))
        except OSError as e:
            findings, gaps = [], [f"{label} could not be read: {e}"]
        scope = label
    elif mode == "all":
        findings = scan_all(gaps, repo)
        scope = "all tracked text files"
    elif mode == "commits" and commits:
        findings = scan_commits(commits, gaps, repo)
        scope = f"lines added by commits {commits}"
    else:
        findings = scan_staged(gaps, repo)
        scope = "staged changes"

    findings.extend(scan_agent_memory(gaps, repo))
    where = "" if repo == ROOT_DIR else f" in {repo}"
    print(f"Scope: {scope} + agent working memory{where}")

    # PRINCIPLE-000 R5: a scan that skipped a surface must not report clean. It used to warn,
    # print [OK] and exit 0 when git failed, so the pre-commit gate passed having scanned nothing.
    if gaps:
        print(f"[FAIL] Scan incomplete: {len(gaps)} surface(s) not scanned:")
        for gap in gaps[:12]:
            print(f"   - {gap}")
        print("   Why: an unscanned surface can hold a credential; 'clean' would be unproven.")
        print("   Fix: run inside the git worktree with `git` on PATH, or fix the file's permissions.")
        print("=" * 58)
        return 1

    if not findings:
        print("[OK] No credential patterns or high-entropy literals detected.")
        if verbose:
            print(f"      {len(SECRET_PATTERNS)} detectors active; "
                  f"{len(ALLOWLIST_SUBSTRINGS)} allowlist tokens.")
        print("=" * 58)
        return 0

    print(f"\n[FAIL] {len(findings)} potential secret(s) detected:")
    for label, lineno, detector, excerpt in findings[:12]:
        print(f"   - {label}:{lineno} [{detector}]")
        print(f"       {excerpt}")
    if len(findings) > 12:
        print(f"   ... and {len(findings) - 12} more")
    print("\n   Why: a committed credential cannot be reverted, only rotated"
          " (PRINCIPLE-019 R6).")
    print("   Fix: remove the value, supply it via an environment variable or secret store,")
    print(f"        rotate it if it was ever pushed, or mark a false positive with a"
          f" '# {PRAGMA}' pragma.")
    print("=" * 58)
    return 1


KNOWN_FLAGS = {"--staged", "--all", "--file", "--commits", "--workspace", "--verbose", "-v", "--help", "-h"}
VALUE_FLAGS = {"--file", "--commits", "--workspace"}

HELP_TEXT = """AIKit Secret & Sensitive Data Scanner (PRINCIPLE-019)

Usage:
  python scripts/check_secrets.py [OPTIONS]

Scans for credential patterns and high-entropy literals, plus agent working memory
(.agents/ or a project's .aikit/ task ledger, and the dogfood log), which is committed like any other
file and is a real leak path for agent-authored rationale.

Options:
  --staged         Scan staged changes only (default) - the surface about to become history
  --all            Scan every tracked text file
  --file <path>    Scan a single file
  --commits <range>  Scan the lines added by the commits in <range> (e.g. HEAD, @{u}..HEAD):
                   exactly what a push uploads (ADR-145)
  --workspace <dir>  Scan the git repository at <dir> instead of AIKit's, e.g. a project
                   under projects/ (ADR-121)
  --verbose, -v    Print detector and allowlist counts
  -h, --help       Show this help message and exit

False positives:
  Add a '# aikit:allow-secret' pragma on the line, or extend ALLOWLIST_SUBSTRINGS.

Exit codes:
  0  clean    1  potential secret found, or a surface could not be scanned    2  CLI argument misuse
"""


if __name__ == "__main__":
    # Findings name the user's own files, so a non-ASCII path must survive a Windows pipe, whose
    # default encoding is the console code page (cp1254, cp1252). Done here, not at import, so a
    # module that imports this scanner keeps its own streams (ADR-182).
    if sys.platform == "win32":
        for stream in (sys.stdout, sys.stderr):
            try:
                stream.reconfigure(encoding="utf-8", errors="replace")
            except (AttributeError, ValueError, OSError):  # hygiene: allow encoding is cosmetic; a stream that cannot change keeps its own
                pass
    argv = sys.argv[1:]
    if "-h" in argv or "--help" in argv:
        print(HELP_TEXT, end="")
        sys.exit(0)

    unknown: List[str] = []
    i = 0
    while i < len(argv):
        token = argv[i]
        if token.startswith("-"):
            if token not in KNOWN_FLAGS:
                unknown.append(token)
            elif token in VALUE_FLAGS:
                i += 1
        i += 1
    if unknown:
        print(f"[INVALID USAGE] Unrecognized option(s): {', '.join(unknown)}", file=sys.stderr)
        print(f"Why: this scanner accepts only {', '.join(sorted(KNOWN_FLAGS))}.", file=sys.stderr)
        print("Fix: run 'python scripts/check_secrets.py --help' to list valid options.",
              file=sys.stderr)
        sys.exit(2)

    scan_mode = "all" if "--all" in argv else "staged"
    scan_target: Optional[Path] = None
    if "--file" in argv:
        idx = argv.index("--file")
        if idx + 1 >= len(argv) or argv[idx + 1].startswith("-"):
            print("[INVALID USAGE] --file requires a path argument.", file=sys.stderr)
            print("Why: there is no sensible default file to scan.", file=sys.stderr)
            print("Fix: pass '--file <path>'.", file=sys.stderr)
            sys.exit(2)
        scan_mode, scan_target = "file", Path(argv[idx + 1])

    scan_commits_range: Optional[str] = None
    if "--commits" in argv:
        idx = argv.index("--commits")
        if idx + 1 >= len(argv) or argv[idx + 1].startswith("-"):
            print("[INVALID USAGE] --commits requires a revision range.", file=sys.stderr)
            print("Why: the commits to scan cannot be inferred without it.", file=sys.stderr)
            print("Fix: pass '--commits <range>', e.g. --commits HEAD or --commits @{u}..HEAD", file=sys.stderr)
            sys.exit(2)
        scan_mode, scan_commits_range = "commits", argv[idx + 1]

    scan_repo = ROOT_DIR
    if "--workspace" in argv:
        idx = argv.index("--workspace")
        if idx + 1 >= len(argv) or argv[idx + 1].startswith("-") or not Path(argv[idx + 1]).is_dir():
            print("[INVALID USAGE] --workspace requires an existing directory.", file=sys.stderr)
            print("Why: the repository to scan cannot be inferred without it.", file=sys.stderr)
            print("Fix: pass '--workspace <dir>', e.g. --workspace projects/my-app", file=sys.stderr)
            sys.exit(2)
        scan_repo = Path(argv[idx + 1]).resolve()

    sys.exit(run_scan(mode=scan_mode, target=scan_target,
                      verbose=("--verbose" in argv or "-v" in argv), repo=scan_repo,
                      commits=scan_commits_range))
