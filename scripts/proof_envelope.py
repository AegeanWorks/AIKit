#!/usr/bin/env python3
"""Signed commit-proof envelope (IDEA-1168).

A proof verdict is only as trustworthy as its binding to the evidence. This
module seals a reproducible receipt (IDEA-1202) inside a canonical,
tamper-evident envelope: canonical JSON, HMAC-SHA256, key id and expiry.

Key custody decision (recorded in the ADR): symmetric HMAC-SHA256 with the
key supplied out of band via the ``AIKIT_PROOF_KEY`` environment variable
(``os.getenv`` with a default; never logged, never stored in the repo).
No private key files, no new dependencies. Verification recomputes the
same HMAC, so any byte flip in the payload fails closed.

Outcomes reuse the shared model (IDEA-1118): a bad signature is ``fail``
(tamper evidence); an expired envelope or an unknown key id is
``inconclusive`` (stale or unverifiable, never a pass).

Zero external dependencies (standard library only).
"""

from __future__ import annotations

import argparse
import hashlib
import hmac
import json
import os
import sys
import time
from pathlib import Path
from typing import Any, Dict, Mapping

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


ENVELOPE_SCHEMA = 1
ENVELOPE_ALG = "HS256"
DEFAULT_KEY_ID = "local"
DEFAULT_TTL_SECONDS = 90 * 24 * 3600
PROOF_KEY_ENV = "AIKIT_PROOF_KEY"


class EnvelopeError(Exception):
    """The envelope could not be sealed or read."""


def canonical_bytes(payload: Mapping[str, Any]) -> bytes:
    """One canonical byte form for any JSON payload (IDEA-1168).

    Sorted keys, no whitespace, UTF-8: the same payload always signs the
    same bytes on every platform.
    """
    return json.dumps(payload, sort_keys=True, separators=(",", ":"),
                      ensure_ascii=True).encode("utf-8")


def default_keys() -> Dict[str, str]:
    """Key ring from the environment (IDEA-1168 custody: env only)."""
    key = (os.getenv(PROOF_KEY_ENV, "") or "").strip()
    return {DEFAULT_KEY_ID: key} if key else {}


def seal(payload: Mapping[str, Any], *, key: str, keyid: str = DEFAULT_KEY_ID,
         ttl_seconds: int = DEFAULT_TTL_SECONDS,
         now: float | None = None) -> Dict[str, Any]:
    """Seal a receipt payload into a signed envelope (IDEA-1168).

    Raises EnvelopeError when no key is supplied: an unsigned envelope
    must never be mistaken for a sealed one.
    """
    if not key:
        raise EnvelopeError(
            f"no sealing key for keyid {keyid!r}; set {PROOF_KEY_ENV}")
    issued = int(now if now is not None else time.time())
    body = json.loads(json.dumps(dict(payload), sort_keys=True))
    payload_hash = hashlib.sha256(canonical_bytes(body)).hexdigest()
    envelope: Dict[str, Any] = {
        "schema": ENVELOPE_SCHEMA,
        "alg": ENVELOPE_ALG,
        "keyid": keyid,
        "iat": issued,
        "exp": issued + max(0, int(ttl_seconds)),
        "payload_sha256": payload_hash,
        "payload": body,
    }
    envelope["sig"] = hmac.new(key.encode("utf-8"), canonical_bytes(envelope),
                               hashlib.sha256).hexdigest()
    return envelope


def verify(envelope: Mapping[str, Any], *, keys: Mapping[str, str],
           now: float | None = None) -> Dict[str, Any]:
    """Verify a sealed envelope (IDEA-1168); fail-closed, never raises.

    ``fail`` means tamper evidence (bad signature or payload mismatch);
    ``inconclusive`` means unverifiable (expired, unknown key, bad shape).
    """
    moment = int(now if now is not None else time.time())
    shaped = envelope if isinstance(envelope, Mapping) else {}

    def refused(outcome: str, reason: str) -> Dict[str, Any]:
        return {"outcome": outcome, "reason": reason, "keyid": shaped.get("keyid")}

    if not isinstance(envelope, Mapping):
        return refused(OUTCOME_INCONCLUSIVE, "envelope is not a JSON object")
    if envelope.get("schema") != ENVELOPE_SCHEMA:
        return refused(OUTCOME_INCONCLUSIVE,
                       f"unsupported schema {envelope.get('schema')!r}")
    if envelope.get("alg") != ENVELOPE_ALG:
        return refused(OUTCOME_INCONCLUSIVE, f"unsupported alg {envelope.get('alg')!r}")
    keyid = envelope.get("keyid")
    key = keys.get(keyid, "") if isinstance(keyid, str) else ""
    if not key:
        return refused(OUTCOME_INCONCLUSIVE, f"unknown keyid {keyid!r}")
    try:
        expiry = int(envelope.get("exp", -1))  # type: ignore[arg-type]
    except (TypeError, ValueError):
        return refused(OUTCOME_INCONCLUSIVE, "envelope has no numeric exp")
    if moment >= expiry:
        return refused(OUTCOME_INCONCLUSIVE, "envelope expired")
    payload = envelope.get("payload")
    if not isinstance(payload, Mapping):
        return refused(OUTCOME_INCONCLUSIVE, "envelope has no payload object")
    body = json.loads(json.dumps(dict(payload), sort_keys=True))
    if hashlib.sha256(canonical_bytes(body)).hexdigest() != envelope.get("payload_sha256"):
        return refused(OUTCOME_FAIL, "payload hash mismatch (tampered)")
    unsigned = {key_: value for key_, value in envelope.items() if key_ != "sig"}
    expected = hmac.new(key.encode("utf-8"), canonical_bytes(unsigned),
                        hashlib.sha256).hexdigest()
    if not hmac.compare_digest(expected, str(envelope.get("sig", ""))):
        return refused(OUTCOME_FAIL, "signature mismatch (tampered)")
    return {"outcome": OUTCOME_PASS, "reason": "sealed and verified", "keyid": keyid}


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="python scripts/proof_envelope.py",
        description="Seal a proof receipt (IDEA-1202 JSON) or verify a sealed envelope.")
    sub = parser.add_subparsers(dest="command", required=True)
    seal_cmd = sub.add_parser("seal", help="seal a receipt file into an envelope")
    seal_cmd.add_argument("receipt", help="input receipt JSON (IDEA-1202 write_receipt)")
    seal_cmd.add_argument("--out", required=True, help="output envelope JSON path")
    seal_cmd.add_argument("--keyid", default=DEFAULT_KEY_ID, help="key id for the envelope")
    seal_cmd.add_argument("--ttl", type=int, default=DEFAULT_TTL_SECONDS,
                          help="seconds until expiry")
    seal_cmd.add_argument("--key", default="",
                          help="sealing key (prefer env AIKIT_PROOF_KEY; never logged)")
    verify_cmd = sub.add_parser("verify", help="verify a sealed envelope file")
    verify_cmd.add_argument("envelope", help="input envelope JSON path")
    return parser


def _read_json(path: str) -> Any:
    with open(path, "r", encoding="utf-8") as handle:
        return json.load(handle)


def _write_json(path: str, value: Any) -> None:
    import tempfile as _tempfile
    parent = str(Path(path).parent)
    if parent and parent != ".":
        Path(parent).mkdir(parents=True, exist_ok=True)
    handle_no, temporary = _tempfile.mkstemp(
        prefix=Path(path).name + ".tmp_", dir=parent if parent else ".")
    try:
        with os.fdopen(handle_no, "w", encoding="utf-8", newline="\n") as stream:
            stream.write(json.dumps(value, indent=2, ensure_ascii=False,
                                    sort_keys=True) + "\n")
            stream.flush()
            os.fsync(stream.fileno())
        os.replace(temporary, path)
    finally:
        if os.path.exists(temporary):
            os.unlink(temporary)


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    if args.command == "seal":
        key = args.key or (os.getenv(PROOF_KEY_ENV, "") or "").strip()
        if not key:
            print(f"Error: no sealing key; set {PROOF_KEY_ENV} or pass --key.",
                  file=sys.stderr)
            print("Why: an envelope without a key proves nothing.", file=sys.stderr)
            print(f"Fix: export {PROOF_KEY_ENV}=<secret> and rerun.", file=sys.stderr)
            return 2
        try:
            payload = _read_json(args.receipt)
            envelope = seal(payload, key=key, keyid=args.keyid, ttl_seconds=args.ttl)
            _write_json(args.out, envelope)
        except (OSError, ValueError, EnvelopeError) as error:
            print(f"Error: cannot seal {args.receipt}: {error}", file=sys.stderr)
            print("Why: the receipt must be readable JSON and the key non-empty.",
                  file=sys.stderr)
            print("Fix: point at the IDEA-1202 receipt file and rerun.", file=sys.stderr)
            return 2
        print(f"[OK] sealed {args.receipt} -> {args.out} "
              f"(keyid {envelope['keyid']}, exp {envelope['exp']})")
        return 0
    try:
        envelope = _read_json(args.envelope)
    except (OSError, ValueError) as error:
        print(f"Error: cannot read {args.envelope}: {error}", file=sys.stderr)
        print("Why: verification needs the sealed envelope file.", file=sys.stderr)
        print("Fix: point at the .sealed.json from the seal step.", file=sys.stderr)
        return 2
    result = verify(envelope, keys=default_keys())
    print(f"[{result['outcome'].upper()}] {result['reason']}")
    if result["outcome"] == OUTCOME_INCONCLUSIVE and result["reason"].startswith("unknown keyid"):
        print(f"Why: no key for this keyid is configured; set {PROOF_KEY_ENV}.",
              file=sys.stderr)
        print("Fix: export the sealing key on this machine and rerun.", file=sys.stderr)
    return 0 if result["outcome"] == OUTCOME_PASS else 1


if __name__ == "__main__":
    raise SystemExit(main())
