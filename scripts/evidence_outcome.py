#!/usr/bin/env python3
"""Shared no-evidence outcome model (IDEA-1118).

Empty evidence must never read as green. Every gate that can observe zero
inputs reports ``inconclusive`` and refuses (fail-closed) instead of
printing OK/pass with threshold 0.

Outcomes:
  pass         evidence exists and the check holds
  fail         evidence exists and the check does not hold
  inconclusive no evidence was observed, so no verdict is proven

Zero external dependencies (standard library only).
"""

from __future__ import annotations

OUTCOME_PASS = "pass"
OUTCOME_FAIL = "fail"
OUTCOME_INCONCLUSIVE = "inconclusive"

VALID_OUTCOMES = frozenset({OUTCOME_PASS, OUTCOME_FAIL, OUTCOME_INCONCLUSIVE})


def outcome_for_counts(observed: int, failures: int = 0) -> str:
    """The shared verdict for a counted observation.

    Zero observations are inconclusive, never a pass. A nonzero observation
    with no failures passes; otherwise it fails.
    """
    if observed <= 0:
        return OUTCOME_INCONCLUSIVE
    return OUTCOME_FAIL if failures > 0 else OUTCOME_PASS


def no_evidence_message(what: str, reason: str) -> list[str]:
    """The Why/Fix lines for an inconclusive refusal (PRINCIPLE-011 R8)."""
    return [
        f"[INCONCLUSIVE] No {what} observed: {reason}.",
        "Why: an empty observation cannot prove a pass; threshold 0 would.",
        f"Fix: provide {what}, or record why none exist before relying on this gate.",
    ]


def is_refusal(outcome: str) -> bool:
    """Whether an outcome must refuse to pass (fail-closed)."""
    return outcome != OUTCOME_PASS
