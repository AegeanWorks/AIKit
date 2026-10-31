"""One-way compatibility re-export for the idea auto-registration engine.

The engine lives in :mod:`idea_catcher.registry`; keeping this module free of registry imports
avoids an import cycle while existing callers and tests can still use `auto_register`.
"""

from idea_catcher.registry import (
    git_commits,
    parse_idea_ids,
    register_from_commits,
    register_from_repo,
)

__all__ = ["git_commits", "parse_idea_ids", "register_from_commits", "register_from_repo"]
