"""
Generated text inside a file the user owns, fenced by `<!-- aegean:<name>:start -->` and
`<!-- aegean:<name>:end -->` (IDEA-398, ADR-281).

A generator that edits a README by guessing where its section ends deletes whatever the user put
there: a license switch replaced everything up to the next `## ` heading, so a user's own
subsection under it was lost. A generator that owns only the text between its markers rewrites
that and nothing else, so everything around the block survives every refresh.
"""

from typing import Optional, Tuple


def markers(name: str) -> Tuple[str, str]:
    """The start and end comments of block `name`; HTML comments, so a rendered README hides them."""
    return f"<!-- aegean:{name}:start -->", f"<!-- aegean:{name}:end -->"


def block_span(text: str, name: str) -> Optional[Tuple[int, int]]:
    """Where block `name` starts and ends in `text`, markers included; None unless both are in order."""
    start_marker, end_marker = markers(name)
    start = text.find(start_marker)
    if start < 0:
        return None
    end = text.find(end_marker, start + len(start_marker))
    return None if end < 0 else (start, end + len(end_marker))


def fenced(name: str, body: str) -> str:
    """`body` between the markers of block `name`, one per line, without a trailing newline."""
    start_marker, end_marker = markers(name)
    return f"{start_marker}\n{body.strip(chr(10))}\n{end_marker}"


def replace_block(text: str, name: str, body: str) -> Optional[str]:
    """`text` with block `name` holding `body` and nothing outside it changed; None when it has no block."""
    span = block_span(text, name)
    if span is None:
        return None
    return text[:span[0]] + fenced(name, body) + text[span[1]:]
