"""Headroom's offline variables (story 12's conditions, AD-15), stdlib only.

`cli` calls `apply_offline_env()` right after the network guard, before any third-party
import; the adapter calls it again before `import headroom`. No beacon, no update check, no
cost map downloaded by litellm, and tiktoken reads the tables litellm ships instead of
downloading them.
"""

from __future__ import annotations

import importlib.util
import os
from pathlib import Path

OFFLINE_ENV = {
    "LITELLM_LOCAL_MODEL_COST_MAP": "True",
    "HEADROOM_OFFLINE": "1",
    "HEADROOM_BEACON": "off",
    "HEADROOM_UPDATE_CHECK": "off",
    "DO_NOT_TRACK": "1",
}


def tiktoken_cache_dir() -> Path | None:
    """The tiktoken tables litellm ships (`cl100k_base`, `o200k_base`), found without
    importing litellm; `None` when litellm is not installed."""
    try:
        spec = importlib.util.find_spec("litellm")
    except (ImportError, ValueError):
        return None
    if spec is None or not spec.submodule_search_locations:
        return None
    path = Path(next(iter(spec.submodule_search_locations))) / "litellm_core_utils" / "tokenizers"
    return path if path.is_dir() else None


def apply_offline_env() -> None:
    """Set the variables (they win over the user's environment: no telemetry, NFR-3)."""
    os.environ.update(OFFLINE_ENV)
    cache = tiktoken_cache_dir()
    if cache is not None:
        os.environ["TIKTOKEN_CACHE_DIR"] = str(cache)
