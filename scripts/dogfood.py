#!/usr/bin/env python3
"""
Operational Dogfooding Runner (PRINCIPLE-015)

Operates AIKit's own CLI surface the way a user would, inside an ephemeral sandbox jail, and
reports a terse pass/fail dashboard. This is the pre-ship gate that PRINCIPLE-015 Rule 7
requires: unit and integration tests assert contracts in isolation, whereas this exercises a
complete end-to-end lifecycle against real processes and then perturbs it hostilely.

Why a separate runner rather than more tests: PRINCIPLE-015 is explicitly about the agent
*using what it builds*. The dogfood run drives a full create -> modify -> retrieve workflow
through the real `disruption_recovery.py` ledger CLI in a throwaway workspace, which no unit
test does, and it reports in the compact form an agent can read in one glance.

Zero external dependencies (standard library only). Safe to run at any time: every mutation is
confined to an ephemeral SANDBOX_ROOT and the runner asserts the repository is untouched.

Usage:
  python scripts/dogfood.py [--verbose] [--keep-sandbox]
Exit codes:
  0 all tracks passed    1 one or more tracks failed    2 CLI argument misuse
"""

import hashlib
import json
import os
import shutil
import signal
import subprocess
import sys
import tempfile
import time
from contextlib import contextmanager
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple, Union

# Safe terminal encoding on Windows (cp1254/cp1252): the verbose trace replays child output
# that may contain emoji, and the legacy console codec cannot encode it.
if sys.platform == "win32":
    try:
        if hasattr(sys.stdout, "reconfigure"):
            sys.stdout.reconfigure(encoding="utf-8", errors="replace")
        if hasattr(sys.stderr, "reconfigure"):
            sys.stderr.reconfigure(encoding="utf-8", errors="replace")
    except (AttributeError, ValueError, OSError):  # hygiene: allow console encoding is cosmetic
        pass

ROOT_DIR = Path(__file__).resolve().parent.parent
LEDGER_CLI = ROOT_DIR / "scripts" / "disruption_recovery.py"
SYNC_CLI = ROOT_DIR / "scripts" / "sync_principles.py"
KB_CLI = ROOT_DIR / "scripts" / "update_knowledge_base.py"
REACH_CLI = ROOT_DIR / "scripts" / "check_reachability.py"
SECRETS_CLI = ROOT_DIR / "scripts" / "check_secrets.py"
SYNC_LICENSES_CLI = ROOT_DIR / "scripts" / "sync_licenses.py"
AIKIT_CLI = ROOT_DIR / "aikit.py"
LOG_PATH = ROOT_DIR / ".agents" / "dogfood_last_run.log"

PROC_TIMEOUT = 10  # PRINCIPLE-010 R3: no unbounded subprocess
MAX_REPORT_LINES = 15  # PRINCIPLE-015 R7: terse dashboard
FINGERPRINT_CHUNK = 1 << 20  # PRINCIPLE-010: stream dirty files instead of reading them whole


# --------------------------------------------------------------------------------------
# Process supervision (PRINCIPLE-015 Rule 2)
# --------------------------------------------------------------------------------------

def terminate_process_tree(proc: "subprocess.Popen") -> None:
    """
    Kill a process and all of its children (PRINCIPLE-015 Rule 2).

    A plain `proc.kill()` orphans grandchildren, which is how dogfood runs leak zombies and
    collide on ports. Windows has no process groups, so the tree is torn down with
    `taskkill /F /T`; POSIX kills the whole process group with SIGKILL.
    """
    if proc.poll() is not None:
        return
    try:
        if sys.platform == "win32":
            subprocess.run(
                ["taskkill", "/F", "/T", "/PID", str(proc.pid)],
                capture_output=True, timeout=PROC_TIMEOUT,
            )
        else:
            os.killpg(os.getpgid(proc.pid), signal.SIGKILL)
    except (OSError, subprocess.SubprocessError):
        # Last resort: at least kill the direct child rather than leaving it running.
        try:
            proc.kill()
        except OSError:  # hygiene: allow the child is already gone; the tree teardown continues
            pass
    finally:
        try:
            proc.wait(timeout=PROC_TIMEOUT)
        except subprocess.TimeoutExpired:  # hygiene: allow the process was killed; waiting longer cannot help
            pass


@contextmanager
def supervised(argv: Union[str, List[str]], cwd: Path):
    """
    RAII supervisor: guarantees recursive teardown even if the body raises. `argv` is a list, or
    on Windows a command line string for commands whose quoting `list2cmdline` would mangle.
    """
    kwargs: Dict[str, Any] = {}
    if sys.platform != "win32":
        kwargs["start_new_session"] = True  # own process group, so killpg reaches children
    # Decode as UTF-8 explicitly. AIKit's CLIs reconfigure stdout to UTF-8 on Windows and emit
    # non-ASCII status glyphs, so letting Python fall back to the locale codec (e.g. cp1254 on a
    # Turkish Windows install) kills the reader thread with UnicodeDecodeError and silently
    # hands back empty output (PRINCIPLE-003 R4, PRINCIPLE-011 R4 platform parity).
    proc = subprocess.Popen(  # hygiene: allow caller bounds communicate(timeout=PROC_TIMEOUT) in run_cli
        argv, cwd=str(cwd), stdin=subprocess.DEVNULL,
        stdout=subprocess.PIPE, stderr=subprocess.PIPE,
        text=True, encoding="utf-8", errors="replace", **kwargs,
    )
    try:
        yield proc
    finally:
        terminate_process_tree(proc)


@contextmanager
def sandbox_jail():
    """
    Ephemeral workspace outside the repository and outside host user directories
    (PRINCIPLE-015 Rule 4). Nothing the dogfood run does may escape this directory.
    """
    root = Path(tempfile.mkdtemp(prefix="aikit_dogfood_"))
    try:
        yield root
    finally:
        shutil.rmtree(root, ignore_errors=True)


# --------------------------------------------------------------------------------------
# Probe helpers
# --------------------------------------------------------------------------------------

def run_cli(script: Path, args: List[str], cwd: Path) -> Tuple[int, str, str]:
    """
    Invoke a CLI as a real binary with stdin closed (PRINCIPLE-015 Rule 3 EOF safety).

    Note: `disruption_recovery.py` anchors its ledger to the repository, not to the working
    directory, so callers MUST pass `--workspace` to keep writes inside the jail.
    """
    with supervised([sys.executable, str(script), *args], cwd) as proc:
        try:
            out, err = proc.communicate(timeout=PROC_TIMEOUT)
        except subprocess.TimeoutExpired:
            return 124, "", f"timed out after {PROC_TIMEOUT}s (interactive hang?)"
    return proc.returncode, out or "", err or ""


def repo_fingerprint() -> Optional[str]:
    """
    Content fingerprint of the repository working tree, or None when git is unavailable.

    Comparing `git status --porcelain` text is NOT sufficient: a file that was already dirty
    before the run prints the same " M path" line afterwards no matter how its contents
    changed. The first dogfood run passed its own blast-radius check while overwriting the
    real task ledger for exactly that reason. Hashing only the paths status names closes the
    hole without reading every tracked file on each of the run's two fingerprint calls.
    """
    try:
        status = subprocess.run(
            ["git", "status", "--porcelain=v1", "-z", "--untracked-files=all"],
            cwd=str(ROOT_DIR), capture_output=True, text=True, encoding="utf-8",
            errors="replace", timeout=PROC_TIMEOUT,
        )
    except (OSError, subprocess.SubprocessError):
        return None
    if status.returncode != 0:
        return None

    digest = hashlib.sha256()
    entries = status.stdout.split("\0")
    index = 0
    while index < len(entries):
        entry = entries[index]
        index += 1
        if not entry:
            continue
        digest.update(entry.encode("utf-8"))
        path = entry[3:]  # porcelain's two status columns and one separator precede the path
        if any(column in "RC" for column in entry[:2]):
            if index < len(entries):
                digest.update(entries[index].encode("utf-8"))
                index += 1
        try:
            with (ROOT_DIR / path).open("rb") as handle:  # hygiene: allow binary content hash
                while chunk := handle.read(FINGERPRINT_CHUNK):
                    digest.update(chunk)
        except OSError:
            digest.update(b"<unreadable>")
    return digest.hexdigest()


# --------------------------------------------------------------------------------------
# Tracks
# --------------------------------------------------------------------------------------

def track_golden_lifecycle(jail: Path, log: List[str]) -> Tuple[bool, str]:
    """
    Track 1 (PRINCIPLE-015 Rule 5): a complete create -> modify -> retrieve lifecycle driven
    through the real ledger CLI, asserting observable state on disk at each step.
    """
    workspace = jail / "golden"
    workspace.mkdir(parents=True, exist_ok=True)
    ledger = workspace / ".agents" / "task_ledger.json"

    # CREATE: record a checkpoint with a full pre-flight impact assessment.
    code, out, err = run_cli(LEDGER_CLI, [
        "--workspace", str(workspace),
        "--checkpoint", "dogfood-task", "--phase", "implementation", "--phase-num", "3",
        "--desc", "dogfood golden path", "--why", "verify end-to-end ledger lifecycle",
        "--benefits", "proves the CLI works as shipped", "--risks", "none",
        "--mitigation", "ephemeral sandbox",
    ], workspace)
    log.append(f"[create] rc={code} out={out.strip()[:120]} err={err.strip()[:120]}")
    if code != 0:
        return False, f"checkpoint create failed (rc={code}): {err.strip()[:80]}"
    if not ledger.exists():
        return False, "checkpoint reported success but no ledger was written"

    data = json.loads(ledger.read_text(encoding="utf-8"))
    active = data.get("active_task") or {}
    if active.get("active_phase") != 3:
        return False, f"phase not persisted: expected 3, got {active.get('active_phase')!r}"
    if (active.get("impact_assessment") or {}).get("why") != "verify end-to-end ledger lifecycle":
        return False, "pre-flight impact assessment was not persisted (PRINCIPLE-007 R6)"

    # MODIFY: advance the task to a later phase; the ledger must reflect the newer phase.
    code, out, err = run_cli(LEDGER_CLI, [
        "--workspace", str(workspace),
        "--checkpoint", "dogfood-task", "--phase", "verification", "--phase-num", "4",
        "--desc", "dogfood advanced",
    ], workspace)
    log.append(f"[modify] rc={code} out={out.strip()[:120]}")
    if code != 0:
        return False, f"checkpoint modify failed (rc={code})"
    active = (json.loads(ledger.read_text(encoding="utf-8")).get("active_task") or {})
    if active.get("active_phase") != 4:
        return False, f"phase did not advance: got {active.get('active_phase')!r}"

    # RETRIEVE: the audit and resume reports must surface the recorded phase, not a default.
    code, out, err = run_cli(LEDGER_CLI, ["--workspace", str(workspace), "--resume"], workspace)
    log.append(f"[retrieve] rc={code} out={out.strip()[:300]}")
    if code != 0:
        return False, f"resume failed (rc={code})"
    if "Phase 4" not in out:
        return False, "resume report lost the recorded phase (PRINCIPLE-002 R4)"

    # COMPLETE: terminal transition must be observable.
    code, out, err = run_cli(LEDGER_CLI, ["--workspace", str(workspace), "--complete", "dogfood-task"], workspace)
    log.append(f"[complete] rc={code} out={out.strip()[:120]}")
    if code != 0:
        return False, f"complete failed (rc={code})"
    active = (json.loads(ledger.read_text(encoding="utf-8")).get("active_task") or {})
    if active.get("status") != "completed":
        return False, f"task not marked completed: {active.get('status')!r}"

    return True, "create -> modify -> retrieve -> complete verified on disk"


def track_chaos_perturbation(jail: Path, log: List[str]) -> Tuple[bool, str]:
    """
    Track 2 (PRINCIPLE-015 Rule 5): hostile perturbations. Each must fail cleanly with no
    unhandled traceback, and the kit must self-heal where it claims to.
    """
    workspace = jail / "chaos"
    workspace.mkdir(parents=True, exist_ok=True)
    ledger = workspace / ".agents" / "task_ledger.json"
    failures = []

    # 1. Malformed flag: must exit 2, never perform the default action.
    code, out, err = run_cli(LEDGER_CLI, ["--workspace", str(workspace), "--not-a-real-flag"], workspace)
    log.append(f"[chaos:badflag] rc={code} err={err.strip()[:160]}")
    if code != 2:
        failures.append(f"bad flag returned {code}, expected 2")
    if "Traceback" in err:
        failures.append("bad flag produced an unhandled traceback")

    # 2. Missing required value: must be refused, not crash.
    code, out, err = run_cli(LEDGER_CLI, ["--workspace", str(workspace), "--validate-commit"], workspace)
    log.append(f"[chaos:novalue] rc={code} err={err.strip()[:160]}")
    if code == 0:
        failures.append("--validate-commit with no argument was accepted")
    if "Traceback" in err:
        failures.append("missing value produced an unhandled traceback")

    # 3. Corrupted ledger (simulated power cut): must self-heal, not crash (PRINCIPLE-013 R4).
    run_cli(LEDGER_CLI, ["--workspace", str(workspace), "--checkpoint", "victim", "--phase", "planning"], workspace)
    if not ledger.exists():
        failures.append("could not seed ledger for corruption test")
    else:
        ledger.write_text("{ truncated mid-write", encoding="utf-8")
        code, out, err = run_cli(LEDGER_CLI, ["--workspace", str(workspace), "--audit"], workspace)
        log.append(f"[chaos:corrupt] rc={code} err={err.strip()[:200]}")
        if code != 0:
            failures.append(f"audit crashed on corrupted ledger (rc={code})")
        if "Traceback" in err:
            failures.append("corrupted ledger produced an unhandled traceback")
        quarantined = list(ledger.parent.glob("*.corrupt_*"))
        if not quarantined:
            failures.append("corrupted ledger was not quarantined (PRINCIPLE-013 R4)")

    # 4. Zero-byte ledger (classic truncation): must degrade cleanly.
    ledger.write_text("", encoding="utf-8")
    code, out, err = run_cli(LEDGER_CLI, ["--workspace", str(workspace), "--audit"], workspace)
    log.append(f"[chaos:zerobyte] rc={code}")
    if code != 0 or "Traceback" in err:
        failures.append("audit did not survive a 0-byte ledger")

    if failures:
        return False, "; ".join(failures[:3])
    return True, "bad flag, missing value, corrupt + 0-byte ledger all handled cleanly"


def track_readonly_gates(jail: Path, log: List[str]) -> Tuple[bool, str]:
    """
    Track 3: the two freshness gates the delivery triad depends on must run read-only from an
    unrelated working directory and still report truthfully (PRINCIPLE-017 R3, PRINCIPLE-016 R4).
    """
    failures = []
    # check_reachability.py has no write mode at all, so it takes no --check flag; passing one
    # would be (correctly) rejected as misuse. Each gate gets the args it actually declares.
    gates = (
        ("sync", SYNC_CLI, ["--check"]),
        ("kb", KB_CLI, ["--check"]),
        ("reach", REACH_CLI, []),
        ("secrets", SECRETS_CLI, ["--all"]),
        ("licenses", SYNC_LICENSES_CLI, ["--check"]),
    )
    # The gates are independent read-only processes, so they run concurrently: run one after
    # another they took ~1s and pushed the integration tier past its 5s budget (ADR-080).
    from concurrent.futures import ThreadPoolExecutor  # lazy: --help stays fast (PRINCIPLE-010)
    with ThreadPoolExecutor(max_workers=min(len(gates), os.cpu_count() or 1)) as pool:  # PRINCIPLE-010 R3
        results = list(pool.map(lambda gate: run_cli(gate[1], gate[2], jail), gates))
    for (name, script, args), (code, out, err) in zip(gates, results):
        label = f"{name} {' '.join(args)}".strip()
        log.append(f"[gate:{name}] rc={code} out={out.strip()[-160:]}")
        if code != 0:
            failures.append(f"{label} failed (rc={code})")
        if "Traceback" in err:
            failures.append(f"{label} produced a traceback")
    if failures:
        return False, "; ".join(failures)
    return True, "sync, AST map, reachability and secret gates all clean"


def track_help_startup_budget(jail: Path, log: List[str]) -> Tuple[bool, str]:
    """
    Track 4: every entrypoint must answer --help safely and inside the PRINCIPLE-010 R5
    startup budget, measured as a real process rather than asserted.
    """
    # PRINCIPLE-010 R5, one fresh process per entrypoint. Raised from 200 by user decision (ADR-179):
    # aikit.py --help has a ~160ms floor on the development machine because it imports nearly every
    # module to print help, so a single 200ms sample failed on ordinary process-start jitter. The
    # 47-71ms medians ADR-083 recorded predate aikit.py joining this loop (ADR-119).
    budget_ms = 250
    attempts = 2
    failures = []
    slowest = 0.0
    for script in (LEDGER_CLI, SYNC_CLI, KB_CLI, REACH_CLI, SECRETS_CLI, SYNC_LICENSES_CLI,
                   AIKIT_CLI):
        measurements = []
        problem = ""
        for attempt in range(attempts):
            start = time.perf_counter()
            code, out, err = run_cli(script, ["--help"], jail)
            elapsed = (time.perf_counter() - start) * 1000
            measurements.append(elapsed)
            if code != 0:
                problem = f"{script.name} --help rc={code}"
            elif err.strip():
                problem = f"{script.name} --help wrote to stderr"
            elif "usage:" not in out.lower():
                problem = f"{script.name} --help printed no usage block"
            if problem or elapsed <= budget_ms:
                break
            if attempt + 1 < attempts:
                time.sleep(0.25)
        best = min(measurements)
        slowest = max(slowest, best)
        suffix = f" (best of {len(measurements)})" if len(measurements) > 1 else ""
        log.append(f"[help:{script.name}] rc={code} {best:.0f}ms{suffix}")
        if problem:
            failures.append(problem)
        elif best > budget_ms:
            failures.append(f"{script.name} --help took {best:.0f}ms > {budget_ms}ms")
    if failures:
        return False, "; ".join(failures[:3])
    return True, f"all entrypoints safe, slowest --help {slowest:.0f}ms"


TRACKS = (
    ("golden lifecycle", track_golden_lifecycle),
    ("chaos perturbation", track_chaos_perturbation),
    ("read-only gates", track_readonly_gates),
    ("help + startup budget", track_help_startup_budget),
)
# Tracks whose verdict is a measured duration: they never share the machine with another track.
TIMED_TRACKS = frozenset({"help + startup budget"})


def _run_track(name: str, fn, jail: Path) -> Tuple[str, bool, str, List[str]]:
    """Run one track with its own log; a crashing track is a failing track, never a crashing run."""
    track_log: List[str] = []
    try:
        ok, detail = fn(jail, track_log)
    except Exception as e:
        ok, detail = False, f"track raised {type(e).__name__}: {e}"
        track_log.append(f"[exception] {type(e).__name__}: {e}")
    return name, ok, detail, track_log


# --------------------------------------------------------------------------------------
# Runner
# --------------------------------------------------------------------------------------

def run_dogfood(verbose: bool = False, keep_sandbox: bool = False) -> int:
    """Execute every dogfood track and emit a terse dashboard (PRINCIPLE-015 Rule 7)."""
    log: List[str] = [f"AIKit dogfood run {time.strftime('%Y-%m-%d %H:%M:%S')}"]
    tree_before = repo_fingerprint()
    results: List[Tuple[str, bool, str]] = []
    started = time.perf_counter()

    jail_cm = sandbox_jail()
    jail = jail_cm.__enter__()
    try:
        log.append(f"sandbox: {jail}")
        # Each track works in its own sandbox folder with its own log, so the untimed tracks run
        # concurrently (~0.4s each, PRINCIPLE-010 R2); a track that times processes runs alone
        # afterwards, so parallel load cannot inflate what it measures.
        from concurrent.futures import ThreadPoolExecutor  # lazy: --help stays fast (PRINCIPLE-010)
        untimed = [(name, fn) for name, fn in TRACKS if name not in TIMED_TRACKS]
        timed = [(name, fn) for name, fn in TRACKS if name in TIMED_TRACKS]
        with ThreadPoolExecutor(max_workers=max(1, min(len(untimed), os.cpu_count() or 1))) as pool:
            outcomes = list(pool.map(lambda track: _run_track(*track, jail), untimed))
        outcomes += [_run_track(name, fn, jail) for name, fn in timed]
        for name, ok, detail, track_log in outcomes:
            log += [f"--- track: {name} ---", *track_log]
            results.append((name, ok, detail))

        # PRINCIPLE-015 Rule 4: nothing may have escaped the jail.
        escaped = [p.name for p in ROOT_DIR.glob("aikit_dogfood_*")]
        tree_after = repo_fingerprint()
        if escaped:
            results.append(("blast radius", False, f"sandbox artifacts in repo: {escaped}"))
        elif tree_before is not None and tree_after is not None and tree_before != tree_after:
            results.append(("blast radius", False, "dogfood run altered tracked repository content"))
        else:
            results.append(("blast radius", True, "zero host mutation; tracked content hash identical"))
    finally:
        if keep_sandbox:
            print(f"[INFO] sandbox retained at {jail}")
        else:
            jail_cm.__exit__(None, None, None)

    elapsed = time.perf_counter() - started
    passed = sum(1 for _, ok, _ in results if ok)
    total = len(results)

    # Verbose detail goes to the log file, not the console (PRINCIPLE-015 Rule 7).
    log.append(f"result: {passed}/{total} tracks passed in {elapsed:.2f}s")
    try:
        LOG_PATH.parent.mkdir(parents=True, exist_ok=True)
        LOG_PATH.write_text("\n".join(log) + "\n", encoding="utf-8")
        log_note = str(LOG_PATH.relative_to(ROOT_DIR))
    except OSError:
        log_note = "(log unavailable: read-only filesystem)"

    lines = ["=" * 58, "AIKit OPERATIONAL DOGFOOD (PRINCIPLE-015)", "=" * 58]
    for name, ok, detail in results:
        mark = "PASS" if ok else "FAIL"
        lines.append(f"[{mark}] {name}: {detail[:70]}")
    lines.append(f"{passed}/{total} tracks passed in {elapsed:.2f}s | log: {log_note}")
    lines.append("=" * 58)
    report = lines[: MAX_REPORT_LINES + 3]
    print("\n".join(report))

    if verbose:
        print("\n--- verbose trace ---")
        for entry in log:
            print(f"  {entry}")

    return 0 if passed == total else 1


KNOWN_FLAGS = {"--verbose", "-v", "--keep-sandbox", "--help", "-h"}

HELP_TEXT = """AIKit Operational Dogfooding Runner (PRINCIPLE-015)

Usage:
  python scripts/dogfood.py [OPTIONS]

Drives AIKit's own CLI surface end-to-end inside an ephemeral sandbox jail, then perturbs it
hostilely, and reports a terse pass/fail dashboard. Never mutates the repository.

Options:
  --verbose, -v    Print the full trace to stdout in addition to the log file
  --keep-sandbox   Leave the sandbox directory on disk for inspection
  -h, --help       Show this help message and exit

Exit codes:
  0  all tracks passed    1  one or more tracks failed    2  CLI argument misuse
"""


if __name__ == "__main__":
    argv = sys.argv[1:]
    if "-h" in argv or "--help" in argv:
        print(HELP_TEXT, end="")
        sys.exit(0)

    unknown = [a for a in argv if a.startswith("-") and a not in KNOWN_FLAGS]
    if unknown:
        print(f"[INVALID USAGE] Unrecognized option(s): {', '.join(unknown)}", file=sys.stderr)
        print(f"Why: this runner accepts only {', '.join(sorted(KNOWN_FLAGS))}.", file=sys.stderr)
        print("Fix: run 'python scripts/dogfood.py --help' to list valid options.", file=sys.stderr)
        sys.exit(2)

    sys.exit(run_dogfood(
        verbose=("--verbose" in argv or "-v" in argv),
        keep_sandbox=("--keep-sandbox" in argv),
    ))
