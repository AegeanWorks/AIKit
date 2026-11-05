#!/usr/bin/env python3
"""Witness-keyed proof corpus with replay and pruning (IDEA-1156).

``prove()`` runs in an ephemeral temp worktree that is deleted on the way
out, so no proof artifact survives for audit. This module stores IDEA-1202
receipts (plus IDEA-1168 envelopes) as content-keyed entries under
``.aikit/proof_corpus/``, replays an entry by re-proving the same witness,
and prunes the corpus to a bounded size.

The witness key is the SHA-256 of the canonical receipt evidence (base,
declared tests, tree manifest, gate digest): the same proof always files
under the same key, and a changed tree files elsewhere instead of
overwriting history. Replay compares verdicts, never file bytes, so a
green proof stays comparable across machines.

Zero external dependencies (standard library only).
"""

from __future__ import annotations

import argparse
import hashlib
import inspect
import json
import os
import sys
import time
from pathlib import Path
from typing import Any, Callable, Dict, List, Mapping, Tuple

try:  # hygiene: allow [silent-except] optional shared-model import fallback path
    from evidence_outcome import (  # type: ignore[import-not-found]
        OUTCOME_FAIL,
        OUTCOME_INCONCLUSIVE,
        OUTCOME_PASS,
        is_refusal,
    )
except Exception:  # pragma: no cover - import fallback for test imports
    try:
        from scripts.evidence_outcome import (  # type: ignore[import-not-found]
            OUTCOME_FAIL,
            OUTCOME_INCONCLUSIVE,
            OUTCOME_PASS,
            is_refusal,
        )
    except Exception:
        OUTCOME_PASS = "pass"
        OUTCOME_FAIL = "fail"
        OUTCOME_INCONCLUSIVE = "inconclusive"

        def is_refusal(outcome: str) -> bool:  # type: ignore[no-redef]
            return outcome != OUTCOME_PASS


CORPUS_SCHEMA = 1
DEFAULT_KEEP = 20
CORPUS_DIRNAME = Path(".aikit") / "proof_corpus"


def canonical_bytes(payload: Mapping[str, Any]) -> bytes:
    """One canonical byte form for any JSON payload (matches the envelope)."""
    return json.dumps(payload, sort_keys=True, separators=(",", ":"),
                      ensure_ascii=True).encode("utf-8")


def witness_key(receipt: Mapping[str, Any]) -> str:
    """Content hash binding a receipt to its evidence (IDEA-1156 witness).

    Same base, tests, pass-to-pass, manifest and gate digest always file under
    the same key; any drift files a new entry instead of rewriting the past.
    An empty pass-to-pass frame is omitted so receipts written before the
    pass-to-pass frame (S-F) keep their original key instead of orphaning.
    """
    manifest = receipt.get("tree_manifest") or []
    gates = receipt.get("gate_digest") or {}
    tests = sorted(str(value) for value in list(receipt.get("tests") or []))
    p2p = sorted(str(value) for value in list(receipt.get("pass_to_pass") or []))
    witness: Dict[str, Any] = {"base": str(receipt.get("base", "")), "tests": tests,
                               "tree_manifest": manifest, "gate_digest": gates}
    if p2p:
        witness["pass_to_pass"] = p2p
    return hashlib.sha256(canonical_bytes(witness)).hexdigest()


def entry_path(corpus: Path, key: str) -> Path:
    """Filesystem path of one corpus entry (hex key, no traversal)."""
    safe = "".join(char for char in key if char in "0123456789abcdef")[:64]
    if not safe:
        raise ValueError(f"refusing unkeyed corpus entry {key!r}")
    return Path(corpus) / f"witness_{safe}.json"


def _atomic_write_json(path: Path, value: Any) -> None:
    import tempfile as _tempfile
    parent = path.parent
    parent.mkdir(parents=True, exist_ok=True)
    handle_no, temporary = _tempfile.mkstemp(
        prefix=path.name + ".tmp_", dir=str(parent))
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


def store(receipt: Mapping[str, Any], corpus: Path, *,
          envelope: Mapping[str, Any] | None = None,
          now: float | None = None) -> Tuple[str, Path]:
    """File a receipt under its witness key (IDEA-1156); returns key, path."""
    key = witness_key(receipt)
    entry: Dict[str, Any] = {
        "schema": CORPUS_SCHEMA,
        "key": key,
        "stored_at": int(now if now is not None else time.time()),
        "receipt": json.loads(json.dumps(dict(receipt), sort_keys=True)),
    }
    if envelope is not None:
        entry["envelope"] = json.loads(json.dumps(dict(envelope), sort_keys=True))
    dest = entry_path(corpus, key)
    _atomic_write_json(dest, entry)
    return key, dest


def load(corpus: Path, key: str) -> Dict[str, Any] | None:
    """Read one entry by witness key; None when absent or unreadable."""
    try:
        return json.loads(entry_path(corpus, key).read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return None


def list_entries(corpus: Path) -> List[Dict[str, Any]]:
    """Every readable entry, oldest first (IDEA-1156 pruning order)."""
    found: List[Dict[str, Any]] = []
    root = Path(corpus)
    if not root.is_dir():
        return found
    for path in sorted(root.glob("witness_*.json")):
        try:
            entry = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            continue
        if isinstance(entry, dict) and entry.get("schema") == CORPUS_SCHEMA:
            found.append({"key": entry.get("key"), "stored_at": entry.get("stored_at", 0),
                          "path": str(path), "entry": entry})
    found.sort(key=lambda row: (row["stored_at"], row["key"]))
    return found


def prune(corpus: Path, keep: int = DEFAULT_KEEP) -> List[str]:
    """Delete oldest entries past the cap (IDEA-1156); returns deleted keys."""
    if keep < 0:
        raise ValueError(f"refusing negative prune cap {keep}")
    entries = list_entries(corpus)
    doomed = entries[:max(0, len(entries) - keep)]
    deleted: List[str] = []
    for row in doomed:
        try:
            Path(str(row["path"])).unlink()
            deleted.append(str(row["key"]))
        except OSError:
            continue
    return deleted


def _accepts_pass_to_pass(prove_fn: Callable[..., Any]) -> bool:
    """Whether the prover accepts a `pass_to_pass` keyword (S-F contract).

    Old test doubles only accept (repo, base, tests); probing the signature
    keeps the fallback deterministic instead of matching `TypeError` text,
    which varies by interpreter. A `**kwargs` prover is assumed to accept it;
    an introspection failure fails open so the subsequent call decides.
    """
    try:
        params = inspect.signature(prove_fn).parameters.values()
    except (TypeError, ValueError):
        return True
    return any(param.kind == inspect.Parameter.VAR_KEYWORD for param in params) \
        or "pass_to_pass" in [param.name for param in params]


def replay(entry: Mapping[str, Any], *,
           prove_fn: Callable[..., Mapping[str, Any]] | None = None,
           repo: str | Path = ".") -> Dict[str, Any]:
    """Re-prove a stored entry and compare verdicts (IDEA-1156); never raises.

    ``prove_fn`` defaults to the real proof gate (integration); unit tests
    inject a double (PRINCIPLE-009 R4). Missing evidence is inconclusive,
    a changed verdict is fail, an identical verdict is pass.
    """
    receipt = entry.get("receipt")
    if not isinstance(receipt, Mapping):
        return {"outcome": OUTCOME_INCONCLUSIVE, "reason": "entry has no receipt"}
    if prove_fn is None:
        try:  # hygiene: prefer the in-repo prover so a same-named installed package cannot shadow it
            from scripts.proof_gate import prove as prove_fn  # type: ignore[import-not-found]
        except ImportError:
            try:
                from proof_gate import prove as prove_fn  # type: ignore[import-not-found]
            except ImportError:
                return {"outcome": OUTCOME_INCONCLUSIVE,
                        "reason": "no prover available in this context"}
    try:
        tests = [str(value) for value in list(receipt.get("tests") or [])]
        p2p = [str(value) for value in list(receipt.get("pass_to_pass") or [])]
        prove_kwargs: dict = {"repo": Path(repo), "base": str(receipt.get("base", "")),
                              "tests": [Path(value) for value in tests]}
        if p2p and _accepts_pass_to_pass(prove_fn):
            prove_kwargs["pass_to_pass"] = [Path(value) for value in p2p]
        try:
            fresh = prove_fn(**prove_kwargs)
        except TypeError as exc:
            # Introspection said yes but the call refused (e.g. a wrapped
            # double): retry without pass-to-pass so the fail-to-pass verdict
            # still replays; pass-to-pass is then unchecked but recorded.
            # Both guards matter: the kwarg must have been sent and the error
            # must name it, otherwise an unrelated TypeError would be masked
            # by a silent retry.
            if "pass_to_pass" not in prove_kwargs or not p2p or "pass_to_pass" not in str(exc):
                raise
            prove_kwargs.pop("pass_to_pass", None)
            fresh = prove_fn(**prove_kwargs)
    except Exception as exc:
        detail = f"replay could not run: {exc}"
        return {"outcome": OUTCOME_INCONCLUSIVE, "reason": detail}
    was_proof = bool(receipt.get("proof", False))
    is_proof = bool(fresh.get("proof", False))
    if is_proof == was_proof:
        return {"outcome": OUTCOME_PASS,
                "reason": f"replay matches stored verdict proof={was_proof}"}
    return {"outcome": OUTCOME_FAIL,
            "reason": f"replay proof={is_proof} differs from stored proof={was_proof}"}


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="python scripts/proof_corpus.py",
        description="File, replay and prune witness-keyed proof receipts.")
    sub = parser.add_subparsers(dest="command", required=True)
    store_cmd = sub.add_parser("store", help="file a receipt JSON under its witness key")
    store_cmd.add_argument("receipt", help="IDEA-1202 receipt JSON file")
    store_cmd.add_argument("--envelope", default="", help="optional IDEA-1168 envelope JSON")
    store_cmd.add_argument("--corpus", default=str(CORPUS_DIRNAME), help="corpus directory")
    replay_cmd = sub.add_parser("replay", help="re-prove a stored witness key")
    replay_cmd.add_argument("key", help="witness key hex")
    replay_cmd.add_argument("--corpus", default=str(CORPUS_DIRNAME), help="corpus directory")
    replay_cmd.add_argument("--repo", default=".", help="repository to re-prove in")
    prune_cmd = sub.add_parser("prune", help="delete oldest entries past the cap")
    prune_cmd.add_argument("--corpus", default=str(CORPUS_DIRNAME), help="corpus directory")
    prune_cmd.add_argument("--keep", type=int, default=DEFAULT_KEEP, help="entries to keep")
    return parser


def _read_json(path: str) -> Any:
    with open(path, "r", encoding="utf-8") as handle:
        return json.load(handle)


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    if args.command == "store":
        try:
            receipt = _read_json(args.receipt)
            envelope = _read_json(args.envelope) if args.envelope else None
            key, dest = store(receipt, Path(args.corpus), envelope=envelope)
        except (OSError, ValueError) as error:
            print(f"Error: cannot store {args.receipt}: {error}", file=sys.stderr)
            print("Why: the corpus files receipts, not raw trees.", file=sys.stderr)
            print("Fix: point at an IDEA-1202 receipt file and rerun.", file=sys.stderr)
            return 2
        print(f"[OK] stored witness {key} -> {dest}")
        return 0
    if args.command == "replay":
        entry = load(Path(args.corpus), args.key)
        if entry is None:
            print(f"[INCONCLUSIVE] no entry for witness {args.key}.", file=sys.stderr)
            print("Why: an absent witness proves nothing.", file=sys.stderr)
            print("Fix: store the receipt first, then replay its key.", file=sys.stderr)
            return 1
        result = replay(entry, repo=args.repo)
        print(f"[{result['outcome'].upper()}] {result['reason']}")
        return 0 if result["outcome"] == OUTCOME_PASS else 1
    try:
        deleted = prune(Path(args.corpus), keep=args.keep)
    except ValueError as error:
        print(f"Error: {error}", file=sys.stderr)
        print("Why: a negative cap would delete the whole corpus.", file=sys.stderr)
        print("Fix: pass --keep 0 or more.", file=sys.stderr)
        return 2
    print(f"[OK] pruned {len(deleted)} entr{'y' if len(deleted) == 1 else 'ies'}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
