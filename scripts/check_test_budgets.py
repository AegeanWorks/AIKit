#!/usr/bin/env python3
"""
Test Tier Budget Gate (PRINCIPLE-010 Rule 6, PRINCIPLE-014 Rule 3)

The two test tiers carry speed budgets because a slow tier stops being run. For months those
budgets were absolute wall-clock numbers that nothing measured:

  - the unit tier was budgeted under 1s and ran 1.21-1.45s for 317 tests;
  - the integration tier was budgeted under 5s and ran 7.63-7.94s for 45 tests.

Both drifted in unnoticed, because every Phase 4 command reported the tiers as green without
reporting how long they took. An absolute per-suite cap also cannot survive a growing suite:
adding a correct, fast test eventually breaks it, which pressures the agent to delete coverage.

This gate replaces the assumption with a measurement. It runs each tier once, reads the count and
duration unittest itself prints, and compares the per-test average against the tier's ceiling. A
green run over the ceiling is repeated once and the faster run is used, because host load is
additive; a red run is never retried (ADR-222). It is the single way Phase 4 runs the tiers, so it adds no second run of its own.

Zero external dependencies (standard library only).

Usage:
  python scripts/check_test_budgets.py [--verbose]
Exit codes:
  0 every tier passed and stayed inside budget   1 a tier failed, exceeded budget or was unreadable   2 CLI argument misuse
"""

import re
import subprocess
import sys
import time
from dataclasses import dataclass, replace
from pathlib import Path
from typing import Callable, Dict, List, Optional, Tuple

ROOT_DIR = Path(__file__).resolve().parent.parent

# The ceiling each tier's average test may reach, in milliseconds. The unit ceiling is 20ms
# (ADR-244) and the integration ceiling is 1000ms (ADR-334, raised on the user's approval
# after the tier repeatedly measured 520-750ms under host load while every test passed).
TIER_BUDGETS_MS: Dict[str, float] = {
    "tests.test_kit": 20.0,
    "tests.test_auto_register": 20.0,
    "tests.test_integration": 1000.0,
}

# A tier that hangs must fail the gate rather than block delivery for ever. This is a hang
# detector, not a second speed limit: the ceilings above are the speed limit, and a loaded host
# can push a green integration tier well past a few minutes. A tier that overruns is reported with
# its own Why/Fix, never raised as a traceback (ADR-293).
TIER_TIMEOUT = 900
TIMEOUT_EXIT = -1
# Host load is additive and arrives in bursts. A tier over its ceiling is measured once more, and
# the faster complete run is used: a real regression is slow in both runs, a load spike is not.
# This does not weaken the ceiling or the test set (ADR-222).
TIER_ATTEMPTS = 2
RETRY_DELAY_SECONDS = 1.0

_SUMMARY = re.compile(r"^Ran (\d+) tests? in ([0-9.]+)s", re.M)
# A failing tier's own traceback is the reason the gate exists; print a bounded tail of it so the
# operator does not have to repeat the identical run to learn which test broke (ADR-299).
FAILURE_TAIL_LINES = 25


def _failure_tail(output: str) -> str:
    """The last bounded slice of a failed tier's output, without its trailing blank lines."""
    lines = [line.rstrip() for line in (output or "").splitlines()]
    while lines and not lines[-1]:
        lines.pop()
    return "\n".join(lines[-FAILURE_TAIL_LINES:])


def _print_failure_tail(tail: str) -> None:
    """Print a bounded failure slice between rules, or nothing when the tail is empty."""
    if not tail:
        return
    print("-" * 58)
    print(tail)
    print("-" * 58)


def _decode_stream(stream: object) -> str:
    if stream is None:
        return ""
    if isinstance(stream, bytes):
        return stream.decode("utf-8", "replace")
    return str(stream)


@dataclass(frozen=True)
class TierResult:
    """One tier's measured outcome; frozen so a report cannot edit what was measured."""

    module: str
    tests: int
    seconds: float
    passed: bool
    attempts: int = 1
    measurements: Tuple[float, ...] = ()
    timed_out: bool = False
    failure_tail: str = ""

    @property
    def per_test_ms(self) -> float:
        return (self.seconds / self.tests * 1000.0) if self.tests else 0.0

    @property
    def budget_ms(self) -> float:
        return TIER_BUDGETS_MS[self.module]

    @property
    def inside_budget(self) -> bool:
        return self.per_test_ms <= self.budget_ms


def parse_tier_output(output: str) -> Optional[Tuple[int, float]]:
    """The count and duration unittest prints, or None when it never got that far."""
    match = _SUMMARY.search(output)
    if not match:
        return None
    return int(match.group(1)), float(match.group(2))


def default_runner(module: str, timeout: int) -> Tuple[int, str]:
    """Run one tier the way the runbook documents it, so the gate measures the real command.

    An overrun comes back as TIMEOUT_EXIT with a sentence, not as a raised TimeoutExpired: a gate
    that reports which tier stopped making progress is worth more than one that crashes (ADR-293).
    """
    try:
        proc = subprocess.run(
            [sys.executable, "-m", "unittest", module],
            cwd=str(ROOT_DIR), capture_output=True, text=True,
            encoding="utf-8", errors="replace", timeout=timeout,
        )
    except subprocess.TimeoutExpired as exc:
        partial = _decode_stream(exc.stdout) + _decode_stream(exc.stderr)
        return TIMEOUT_EXIT, f"{partial}did not finish within {timeout}s\n"
    return proc.returncode, (proc.stdout or "") + (proc.stderr or "")


def run_tier(module: str, runner: Optional[Callable[[str, int], Tuple[int, str]]] = None,
             attempts: int = TIER_ATTEMPTS,
             retry_delay: float = RETRY_DELAY_SECONDS) -> Optional[TierResult]:
    """
    Measure one tier, or None when its output carried no summary. A green run over the ceiling is
    measured once more and the faster complete run is kept (ADR-222); a red run is never retried.
    """
    run = runner or default_runner
    best: Optional[TierResult] = None
    measurements: List[float] = []
    for attempt in range(max(1, attempts)):
        code, output = run(module, TIER_TIMEOUT)
        if code == TIMEOUT_EXIT:
            # The runner kept the partial output precisely so the stalled test can be named;
            # dropping it left a timeout report with only the tier, never the test (ADR-293).
            return TierResult(module=module, tests=0, seconds=float(TIER_TIMEOUT),
                              passed=False, attempts=len(measurements) + 1, timed_out=True,
                              failure_tail=_failure_tail(output))
        summary = parse_tier_output(output)
        if summary is None:
            return None
        tests, seconds = summary
        measurements.append((seconds / tests * 1000.0) if tests else 0.0)
        result = TierResult(module=module, tests=tests, seconds=seconds, passed=(code == 0),
                            attempts=len(measurements), measurements=tuple(measurements),
                            failure_tail="" if code == 0 else _failure_tail(output))
        if not result.passed:
            return result
        if best is None or result.per_test_ms < best.per_test_ms:
            best = result
        if result.inside_budget:
            break
        if attempt + 1 < attempts:
            if retry_delay:
                time.sleep(retry_delay)
    return replace(best, attempts=len(measurements), measurements=tuple(measurements)) if best else None


def budget_errors(results: List[TierResult]) -> List[str]:
    """One line per tier that is over its ceiling; empty when every tier fits."""
    errors = []
    for result in results:
        if result.inside_budget:
            continue
        measured = (f"; runs {', '.join(f'{value:.2f}ms' for value in result.measurements)}"
                    if len(result.measurements) > 1 else "")
        errors.append(
            f"{result.module}: {result.per_test_ms:.2f}ms per test exceeds the "
            f"{result.budget_ms:.2f}ms ceiling ({result.tests} tests in "
            f"{result.seconds:.3f}s{measured})"
        )
    return errors


def run_check(runner: Optional[Callable[[str, int], Tuple[int, str]]] = None,
              verbose: bool = False, retry_delay: float = RETRY_DELAY_SECONDS,
              sequential: bool = False) -> int:
    print("=" * 58)
    print("TEST TIER BUDGET GATE (PRINCIPLE-010 R6)")
    print("=" * 58)

    modules = list(TIER_BUDGETS_MS)
    if sequential or len(modules) <= 1:
        measured: List[Optional[TierResult]] = [
            run_tier(module, runner=runner, retry_delay=retry_delay) for module in modules
        ]
    else:
        # Tiers are independent subprocess runs of several seconds each, so threads only
        # parallelize the wait (PRINCIPLE-010 R3); reporting below stays in registry order.
        # The tiers share the working tree, so a tier test that mutates it races a tier test
        # that audits it: tree fixtures must be underscore-prefixed and tree auditors must
        # skip them (the convention the annotation audit already uses).
        from concurrent.futures import ThreadPoolExecutor  # lazy: --help stays fast (PRINCIPLE-010)
        with ThreadPoolExecutor(max_workers=len(modules)) as pool:
            futures = [pool.submit(run_tier, module, runner, TIER_ATTEMPTS, retry_delay)
                       for module in modules]
            measured = [future.result() for future in futures]

    results: List[TierResult] = []
    failures: List[str] = []
    for module, result in zip(modules, measured):
        if result is None:
            failures.append(f"{module}: produced no test summary, so it could not be measured")
            print(f"[FAIL] {module}: no 'Ran N tests in Xs' summary; the tier did not run")
            continue
        results.append(result)
        if result.timed_out:
            failures.append(f"{module}: did not finish within {TIER_TIMEOUT}s")
            print(f"[FAIL] {module}: did not finish within {TIER_TIMEOUT}s")
            # The partial output names the test that stopped making progress; without it the
            # operator had to rerun the tier to find it (ADR-293, ADR-299).
            _print_failure_tail(result.failure_tail)
            continue
        if not result.passed:
            failures.append(f"{module}: the tier failed")
        verdict = "FAIL" if not result.passed else ("OVER" if not result.inside_budget else "PASS")
        retried = (f" (best of {result.attempts}; retried for host load)"
                   if result.attempts > 1 else "")
        print(f"[{verdict}] {module}: {result.tests} tests in {result.seconds:.3f}s "
              f"= {result.per_test_ms:.2f}ms per test (ceiling {result.budget_ms:.2f}ms){retried}")
        _print_failure_tail(result.failure_tail)

    over = budget_errors(results)
    for line in over:
        print(f"Why: {line}")
    if over:
        print("Fix: profile the tier and return the slowest tests to budget, or raise the ceiling "
              "in PRINCIPLE-010 R6 with an ADR and the user's approval (PRINCIPLE-014 R3).")
    if failures:
        for line in failures:
            print(f"Why: {line}")
        print("Fix: run the tier directly to see which test failed, then repair it before delivery.")
    if any(result.timed_out for result in results):
        print(f"Fix: a tier that is still running after {TIER_TIMEOUT}s has hung or is load-bound; "
              "re-run with a quiet host, or find the test that stopped making progress "
              "(PRINCIPLE-010 R3).")

    if verbose:
        for r in results:
            print(f"   {r.module}: budget {r.budget_ms:.2f}ms, headroom "
                  f"{r.budget_ms - r.per_test_ms:.2f}ms per test")

    if not failures and not over:
        print(f"[OK] {len(results)} tier(s) passed and stayed inside budget.")
    print("=" * 58)
    return 1 if (failures or over) else 0


KNOWN_FLAGS = {"--verbose", "-v", "--sequential", "--help", "-h"}

HELP_TEXT = """AIKit Test Tier Budget Gate (PRINCIPLE-010 Rule 6)

Usage:
  python scripts/check_test_budgets.py [OPTIONS]

Runs every test tier once and fails when a tier fails, when its output carries no summary, or
when its average test exceeds the tier's ceiling. This is Phase 4's way of running the tiers, so
it replaces running them by hand rather than adding a second run.

Options:
  --verbose, -v   Print each tier's ceiling and remaining headroom
  --sequential    Run tiers one after another (default runs them concurrently)
  -h, --help      Show this help message and exit

Exit codes:
  0  inside budget    1  tier failed, over budget or unreadable    2  CLI argument misuse
"""


if __name__ == "__main__":
    argv = sys.argv[1:]
    if "-h" in argv or "--help" in argv:
        print(HELP_TEXT, end="")
        sys.exit(0)

    unknown = [a for a in argv if a.startswith("-") and a not in KNOWN_FLAGS]
    if unknown:
        print(f"[INVALID USAGE] Unrecognized option(s): {', '.join(unknown)}", file=sys.stderr)
        print(f"Why: this gate accepts only {', '.join(sorted(KNOWN_FLAGS))}.", file=sys.stderr)
        print("Fix: run 'python scripts/check_test_budgets.py --help' to list valid options.",
              file=sys.stderr)
        sys.exit(2)

    sys.exit(run_check(verbose=("--verbose" in argv or "-v" in argv),
                      sequential=("--sequential" in argv)))
