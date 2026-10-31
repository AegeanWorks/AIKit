"""Run an external analyzer over one Reforge review packet.

Reforge does not call a model itself. The analyzer is a command the operator chooses: it receives
the packet path and an output path, reads the fenced packet, and writes the same JSON answer a host
reviewer would write. Reforge validates that answer through the normal review gate before it can
change a stage.
"""

from __future__ import annotations

import json
import os
import shlex
import subprocess
import tempfile
from pathlib import Path
from typing import Any, Dict, Tuple

from reforge.errors import ReforgeError
from reforge.review import MAX_ANSWER_BYTES


def _parts(command: str) -> list[str]:
    parts = shlex.split(command)
    if not parts:
        raise ReforgeError(
            "the analyzer command is empty.",
            "the analyzer is the program that reads the packet and writes the findings JSON.",
            "pass --analyzer with an executable and its arguments.",
            exit_code=2,
        )
    return parts


def run_analyzer(root: Path, packet: Path, command: str, timeout: float = 300.0
                 ) -> Tuple[Dict[str, Any], Path]:
    """Run one analyzer command; return its parsed answer and the file holding it.

    Contract: ``<command> <packet> <answer>``. The command writes one JSON object to ``<answer>``.
    The caller owns the returned file and must remove it after the review reads it.
    """
    root = Path(root)
    packet = Path(packet)
    if not packet.is_file():
        raise ReforgeError(
            f"the review packet does not exist: {packet}",
            "the analyzer needs the stage packet it must read.",
            "run `reforge audit` again for that stage, then retry.",
        )
    if timeout <= 0:
        raise ReforgeError(
            f"the analyzer timeout must be positive, not {timeout:g}.",
            "a non-positive timeout would kill the analyzer before it starts.",
            "pass --timeout with a positive number of seconds.",
            exit_code=2,
        )
    parts = _parts(command)
    descriptor, name = tempfile.mkstemp(prefix=".reforge-answer-", suffix=".json",
                                        dir=str(packet.parent))
    os.close(descriptor)
    answer = Path(name)
    try:
        try:
            completed = subprocess.run(
                parts + [str(packet), str(answer)],
                cwd=str(root), capture_output=True, text=True,
                timeout=timeout, check=False,
            )
        except subprocess.TimeoutExpired as exc:
            raise ReforgeError(
                f"the analyzer did not finish within {timeout:g}s.",
                "a slow or interactive analyzer cannot hold the audit open.",
                "run the analyzer directly on the packet, then pass its answer with "
                "`reforge review`.",
            ) from exc
        except OSError as exc:
            raise ReforgeError(
                f"the analyzer could not start: {exc}",
                "the command is missing, is not executable, or cannot be launched.",
                "check the --analyzer command and its working directory.",
            ) from exc
        if completed.returncode != 0:
            raise ReforgeError(
                f"the analyzer exited with code {completed.returncode}.",
                "a failed analyzer produced no reviewed answer, so the stage must stay unreviewed.",
                "run the analyzer directly on the packet to see its output, fix it, and retry.",
            )
        try:
            raw = answer.read_bytes()
        except OSError as exc:
            raise ReforgeError(
                f"the analyzer answer cannot be read: {exc}",
                "the command did not create a readable answer file.",
                "write one JSON object to the path passed as the second argument.",
            ) from exc
        if len(raw) > MAX_ANSWER_BYTES:
            raise ReforgeError(
                f"the analyzer answer is larger than {MAX_ANSWER_BYTES} bytes.",
                "an unbounded answer would be parsed and kept as review state.",
                "write a bounded JSON object with only the findings and hunk attestations.",
            )
        try:
            text = raw.decode("utf-8")
        except UnicodeDecodeError as exc:
            raise ReforgeError(
                f"the analyzer answer is not UTF-8: {exc}",
                "the review gate reads a UTF-8 JSON answer.",
                "write one JSON object to the path passed as the second argument.",
            ) from exc
        if not text.strip():
            raise ReforgeError(
                "the analyzer wrote an empty answer.",
                "an empty file is not a review and cannot advance the stage.",
                "write one JSON object with findings and reviewed_hunks to the answer path.",
            )
        try:
            payload = json.loads(text)
        except ValueError as exc:
            raise ReforgeError(
                f"the analyzer answer is not valid JSON: {exc}",
                "Reforge validates every answer before it records a review.",
                "write one JSON object with a findings list and reviewed_hunks.",
            ) from exc
        if not isinstance(payload, dict):
            raise ReforgeError(
                "the analyzer answer must be one JSON object.",
                "the review gate reads named fields, not a bare array.",
                "return an object with `findings` and `reviewed_hunks`.",
            )
        return payload, answer
    except Exception:
        answer.unlink(missing_ok=True)
        raise
