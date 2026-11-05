#!/usr/bin/env python3
"""Evidence policy over step attestations (IDEA-1169).

``verify_commit`` used to hardcode all-must-pass over a fixed gate list:
no named policy, no way to verify sealed evidence. This module names the
policy and evaluates step attestations under it, so the gate set can grow
a quorum or a sealed-evidence hook without changing the fail-closed core.

Policies (closed vocabulary):
  require-all  every attestation must pass (today's behavior, the default)
  quorum:N     at least N attestations must pass

Fail-closed in both: any ``fail`` fails the run outright (tamper evidence
is never outvoted); otherwise ``inconclusive`` unless the pass bar holds.
Sealed attestations (IDEA-1168): when an attestation carries an envelope
and keys are supplied, the envelope verdict decides that step.

Zero external dependencies (standard library only).
"""

from __future__ import annotations

import hashlib
from typing import Any, Callable, Dict, List, Mapping, Sequence, Tuple

try:  # hygiene: allow [silent-except] optional shared-model import fallback path
    from scripts.evidence_outcome import (  # type: ignore[import-not-found]
        OUTCOME_FAIL,
        OUTCOME_INCONCLUSIVE,
        OUTCOME_PASS,
    )
except Exception:  # pragma: no cover - import fallback for direct runs
    try:
        from evidence_outcome import (  # type: ignore[import-not-found]
            OUTCOME_FAIL,
            OUTCOME_INCONCLUSIVE,
            OUTCOME_PASS,
        )
    except Exception:
        OUTCOME_PASS = "pass"
        OUTCOME_FAIL = "fail"
        OUTCOME_INCONCLUSIVE = "inconclusive"


POLICY_REQUIRE_ALL = "require-all"
POLICY_QUORUM_PREFIX = "quorum:"


class PolicyError(Exception):
    """The policy text names no known policy."""


def parse_policy(text: str) -> Tuple[str, int]:
    """Parse a policy word into (kind, n); closed vocabulary (IDEA-1169)."""
    if not isinstance(text, str):
        raise PolicyError(f"unknown policy {text!r}; want 'require-all' or 'quorum:N'")
    cleaned = (text or "").strip()
    if cleaned == POLICY_REQUIRE_ALL:
        return POLICY_REQUIRE_ALL, 0
    if cleaned.startswith(POLICY_QUORUM_PREFIX):
        try:
            quorum = int(cleaned[len(POLICY_QUORUM_PREFIX):])
        except ValueError:
            raise PolicyError(
                f"unknown policy {text!r}; want 'require-all' or 'quorum:N'")
        if quorum < 1:
            raise PolicyError(
                f"unknown policy {text!r}; want 'require-all' or 'quorum:N'")
        return "quorum", quorum
    raise PolicyError(f"unknown policy {text!r}; want 'require-all' or 'quorum:N'")


def evidence_hash(text: str) -> str:
    """Short stable digest of a step's evidence tail (IDEA-1169)."""
    return hashlib.sha256(str(text or "").encode("utf-8", errors="replace")).hexdigest()[:16]


def attest(step: str, outcome: str, evidence: str = "",
           envelope: Mapping[str, Any] | None = None) -> Dict[str, Any]:
    """One step attestation: what ran, its shared-model outcome, its evidence."""
    record: Dict[str, Any] = {
        "step": step,
        "outcome": outcome,
        "evidence": evidence_hash(str(evidence or "")),
    }
    if envelope is not None:
        if not isinstance(envelope, Mapping):
            record["envelope"] = {"unverifiable": str(envelope)[:200]}
        else:
            record["envelope"] = dict(envelope)
    return record


def evaluate(policy_text: str, attestations: Sequence[Mapping[str, Any]], *,
             envelope_keys: Mapping[str, str] | None = None,
             verify_sealed: Callable[[Mapping[str, Any]], Mapping[str, Any]] | None = None,
             ) -> Dict[str, Any]:
    """Evaluate attestations under the named policy (IDEA-1169).

    Raises PolicyError on an unknown policy word; otherwise never raises.
    A sealed attestation (one carrying an envelope) is decided by envelope
    verification when keys are supplied; tamper evidence (fail) always fails
    the run, and the pass bar decides between pass and inconclusive.

    ``verify_sealed`` receives the envelope with the key ring as ``keys=``
    (the ``proof_envelope.verify`` shape); it defaults to the bundled
    verifier so callers only pass keys.
    """
    if verify_sealed is None and envelope_keys:
        try:  # hygiene: prefer the in-repo verifier so a same-named installed package cannot shadow it
            from scripts.proof_envelope import (  # type: ignore[import-not-found]
                verify as verify_sealed)
        except Exception:
            try:
                from proof_envelope import verify as verify_sealed  # type: ignore[import-not-found]
            except Exception:
                verify_sealed = None
    kind, quorum = parse_policy(policy_text)
    decided: List[Dict[str, Any]] = []
    for record in attestations:
        outcome = str(record.get("outcome", OUTCOME_INCONCLUSIVE))
        sealed = record.get("envelope")
        keys = envelope_keys or {}
        if sealed is not None:
            if not keys or verify_sealed is None:
                # Fail-closed: a sealed step without keys/verifier is never
                # trusted on its claim; it stays inconclusive.
                outcome = OUTCOME_INCONCLUSIVE
            elif not isinstance(sealed, Mapping):
                outcome = OUTCOME_INCONCLUSIVE
            else:
                try:
                    verdict = verify_sealed(sealed, keys=keys)
                except Exception:
                    # Tamper evidence wins: a verifier crash fails the step
                    # rather than breaking the never-raises contract.
                    outcome = OUTCOME_FAIL
                else:
                    if isinstance(verdict, Mapping):
                        outcome = str(verdict.get("outcome", OUTCOME_INCONCLUSIVE))
                    else:
                        outcome = OUTCOME_INCONCLUSIVE
        decided.append({"step": str(record.get("step", "?")), "outcome": outcome})
    failed = [row["step"] for row in decided if row["outcome"] == OUTCOME_FAIL]
    passed = [row["step"] for row in decided if row["outcome"] == OUTCOME_PASS]
    if failed:
        return {"outcome": OUTCOME_FAIL, "passed": passed, "failed": failed,
                "reason": f"policy {kind} refused: {', '.join(failed)} failed"}
    if kind == "quorum":
        if len(passed) >= quorum:
            return {"outcome": OUTCOME_PASS, "passed": passed, "failed": [],
                    "reason": f"policy quorum:{quorum} met by {len(passed)} step(s)"}
        return {"outcome": OUTCOME_INCONCLUSIVE, "passed": passed, "failed": [],
                "reason": f"policy quorum:{quorum} short: {len(passed)} passed"}
    if len(decided) == 0:
        return {"outcome": OUTCOME_INCONCLUSIVE, "passed": [], "failed": [],
                "reason": "policy require-all refused: no attestations observed"}
    if len(passed) == len(decided):
        return {"outcome": OUTCOME_PASS, "passed": passed, "failed": [],
                "reason": "policy require-all met: every step passed"}
    return {"outcome": OUTCOME_INCONCLUSIVE, "passed": passed, "failed": [],
            "reason": "policy require-all refused: a step has no pass"}
