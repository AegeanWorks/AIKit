#!/usr/bin/env python3
"""Append-only JSONL transcript for sub-agent delegation (S-E).

OpenHands proved an append-only event log plus a replayer (`controller/replay.py`,
`state_tracker.py`, `test_replay.py`); SWE-agent proved a `.traj` bundle with a
`ReplayModel` that swaps the LM for recorded actions (`run/run_replay.py`,
`--validate_only`); OTel gen-ai spans proved content-by-reference
(`gen_ai.input/output.messages` + `*_ref` URIs, prompt version + seed).

This port is stdlib-only: one JSON object per line (`request` then `result`),
credential-scrubbed before the write (PRINCIPLE-019), content stored with
`len` + `sha256` so a replay can prove the identical verdict without a new
model call and without loading tool output into context (PRINCIPLE-012).
"""

import hashlib
import json
import time
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

try:
    from scripts.check_secrets import scrub_text
except ImportError:  # pragma: no cover - standalone `python scripts/delegate_transcript.py`
    from check_secrets import scrub_text

TRANSCRIPT_SCHEMA = 1


def _scrub_data(obj: Any) -> Any:
    """Scrub every string inside `obj` (keys are ours, values may be theirs)."""
    if isinstance(obj, str):
        cleaned, _ = scrub_text(obj)
        return cleaned
    if isinstance(obj, dict):
        return {key: _scrub_data(value) for key, value in obj.items()}
    if isinstance(obj, (list, tuple)):
        return [_scrub_data(value) for value in obj]
    return obj


def _sha(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def append_event(path: Path, kind: str, data: Dict[str, Any]) -> Dict[str, Any]:
    """Append one scrubbed event; returns the stored event (with `seq`/`ts`)."""
    target = Path(path)
    target.parent.mkdir(parents=True, exist_ok=True)
    from scripts.disruption_recovery import LOCK_TIMEOUT_SECONDS, file_lock

    with file_lock(target, timeout_seconds=LOCK_TIMEOUT_SECONDS) as acquired:
        if not acquired:
            raise TimeoutError(
                f"Could not acquire the delegate transcript lock for {target.name} "
                f"within {LOCK_TIMEOUT_SECONDS:g}s; no event was appended."
            )
        seq = 1
        try:
            with open(target, "r", encoding="utf-8") as handle:
                for line in handle:
                    if line.strip():
                        seq += 1
        except FileNotFoundError:
            seq = 1
        event = {
            "schema": TRANSCRIPT_SCHEMA,
            "seq": seq,
            "ts": time.time(),
            "kind": kind,
            "data": _scrub_data(data),
        }
        with open(target, "a", encoding="utf-8") as handle:  # hygiene: allow single append stream per event
            handle.write(json.dumps(event) + "\n")
            handle.flush()
            try:
                import os as _os
                _os.fsync(handle.fileno())
            except OSError:  # hygiene: allow degraded durability; the line is already written
                pass
    return event


def append_request(path: Path, role: str, prompt: str, file: Optional[str],
                   model: Optional[str], timeout: int,
                   output_format: str = "text") -> Dict[str, Any]:
    """Log a delegate invocation (prompt scrubbed, plus len+sha for replay audit)."""
    cleaned, _ = scrub_text(prompt or "")
    return append_event(path, "request", {
        "role": role,
        "prompt": cleaned,
        "prompt_len": len(cleaned),
        "prompt_sha": _sha(cleaned),
        "file": file,
        "model": model,
        "timeout": timeout,
        "output_format": output_format,
    })


def append_result(path: Path, exit_code: int, output: str,
                  duration_s: float) -> Dict[str, Any]:
    """Log a delegate outcome (output scrubbed, plus len+sha for identical-verdict proof)."""
    cleaned, _ = scrub_text(output or "")
    return append_event(path, "result", {
        "exit_code": exit_code,
        "output": cleaned,
        "output_len": len(cleaned),
        "output_sha": _sha(cleaned),
        "duration_s": round(duration_s, 3),
        "status": "success" if exit_code == 0 else "error",
    })


def _load_events(path: Path) -> List[Dict[str, Any]]:
    """Parse every line; raises ValueError with Why/Fix on the first corrupt line."""
    target = Path(path)
    try:
        with open(target, "r", encoding="utf-8") as handle:
            lines = handle.readlines()
    except OSError as exc:
        raise ValueError(f"transcript {target} cannot be read: {exc}\n"
                         f"Why: the replay source is missing or unreadable.\n"
                         f"Fix: pass the transcript file a delegate run wrote.") from exc
    events: List[Dict[str, Any]] = []
    for index, line in enumerate(lines, start=1):
        if not line.strip():
            continue
        try:
            event = json.loads(line)
        except ValueError as exc:
            raise ValueError(f"transcript {target} line {index} is not JSON: {exc}\n"
                             f"Why: the transcript was truncated or hand-edited.\n"
                             f"Fix: re-run the delegate with transcript_path to rewrite it.") from exc
        if not isinstance(event, dict):
            raise ValueError(f"transcript {target} line {index} is not an object\n"
                             f"Why: every transcript line must be one JSON object.\n"
                             f"Fix: re-run the delegate with transcript_path to rewrite it.")
        events.append(event)
    return events


def verify_transcript(path: Path) -> Tuple[bool, str]:
    """Check schema/seq/order/kinds/secrets; (True, detail) or (False, Why/Fix detail)."""
    target = Path(path)
    try:
        events = _load_events(target)
    except ValueError as exc:
        return False, str(exc)
    if not events:
        return False, ("transcript is empty\n"
                       "Why: no delegate request was recorded.\n"
                       "Fix: run the delegate with transcript_path first.")
    for index, event in enumerate(events, start=1):
        if event.get("schema") != TRANSCRIPT_SCHEMA:
            return False, (f"transcript line {index} declares schema {event.get('schema')!r}\n"
                           "Why: this build reads only schema 1.\n"
                           "Fix: rewrite the transcript with this build's delegate.")
        if event.get("seq") != index:
            return False, (f"transcript line {index} declares seq {event.get('seq')!r}\n"
                           "Why: an append-only log numbers every event once, in order.\n"
                           "Fix: re-run the delegate with transcript_path to rewrite it.")
        if not isinstance(event.get("ts"), (int, float)):
            return False, (f"transcript line {index} has no numeric ts\n"
                           "Why: replay order needs timestamps.\n"
                           "Fix: re-run the delegate with transcript_path to rewrite it.")
    stamps = [event["ts"] for event in events]
    if any(later < earlier for earlier, later in zip(stamps, stamps[1:])):
        return False, ("transcript timestamps go backwards\n"
                       "Why: an append-only log never rewrites the past.\n"
                       "Fix: re-run the delegate with transcript_path to rewrite it.")
    kinds = [event.get("kind") for event in events]
    if kinds[0] != "request":
        return False, ("transcript does not start with a request\n"
                       "Why: every delegate run starts by logging its brief.\n"
                       "Fix: re-run the delegate with transcript_path to rewrite it.")
    if "result" not in kinds:
        return False, ("transcript has no result\n"
                       "Why: the delegate run never finished or was never logged.\n"
                       "Fix: re-run the delegate with transcript_path to rewrite it.")
    try:
        with open(target, "r", encoding="utf-8") as handle:
            raw = handle.read()
    except OSError as exc:
        return False, (f"transcript cannot be re-read: {exc}\n"
                       "Why: the replay source is unreadable.\n"
                       "Fix: re-run the delegate with transcript_path to rewrite it.")
    _, hits = scrub_text(raw)
    if hits:
        return False, ("transcript holds credential-shaped text\n"
                       "Why: a stored secret is as unrecoverable as a committed one.\n"
                       "Fix: delete the transcript and re-run; prompts are scrubbed on write.")
    last = next(event for event in reversed(events) if event.get("kind") == "result")
    data = last.get("data", {})
    return True, (f"transcript ok: {len(events)} events, "
                  f"exit {data.get('exit_code')}, "
                  f"output_sha {str(data.get('output_sha', ''))[:12]}")


def replay_transcript(path: Path) -> Tuple[int, str]:
    """Return the recorded (exit_code, output) without invoking any runner."""
    ok, detail = verify_transcript(path)
    if not ok:
        raise ValueError(detail)
    events = _load_events(Path(path))
    last = next(event for event in reversed(events) if event.get("kind") == "result")
    data = last.get("data", {})
    return int(data.get("exit_code", 1)), str(data.get("output", ""))
