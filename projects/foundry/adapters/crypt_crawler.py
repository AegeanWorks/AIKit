"""crypt-crawler adapter: the versioned boundary foundry never crosses.

Foundry emits canonical boss JSON; it never dictates the game's format.
This adapter exposes the consumer facts the validator and generator need
(catalog ids, target identity, supported pack major) by reading the
game's own tables, so a game-side data edit is picked up without a
foundry change. The reverse mapping (canonical pack -> BOSS_TEMPLATES
entry + spawn post) lives game-side in crawler/foundry_packs.py, which
is the adapter's other half pinned by the same pack_version.
"""

from __future__ import annotations

import sys
from pathlib import Path
from typing import Dict, FrozenSet

FOUNDRY_ROOT = Path(__file__).resolve().parent.parent
# foundry lives at <repo>/projects/foundry; the consumer sits beside it.
REPO_ROOT = FOUNDRY_ROOT.parent.parent
GAME_ROOT = REPO_ROOT / "projects" / "crypt-crawler"

TARGET_GAME = "crypt-crawler"
SUPPORTED_MAJOR = 1
ECONOMY_NOTE = "ITEM_CATALOG ids; xp 20-400 / gold 10-300 per schema bands"


def _load_game_tables() -> Dict[str, FrozenSet[str]]:
    if str(GAME_ROOT) not in sys.path:
        sys.path.insert(0, str(GAME_ROOT))
    from crawler.entities import ITEM_CATALOG  # type: ignore[import]

    return {"items": frozenset(ITEM_CATALOG)}


_TABLES = _load_game_tables()
ITEM_IDS: FrozenSet[str] = _TABLES["items"]
