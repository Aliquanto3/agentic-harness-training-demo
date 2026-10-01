"""Headroom's offline variables (story 12's conditions, AD-15), stdlib only.

`cli` calls `apply_offline_env()` right after the network guard, before any third-party
import; the adapter calls it again before `import headroom`. No beacon, no update check, no
cost map downloaded by litellm, and tiktoken reads the `cl100k_base` table WaveStack ships
instead of downloading it.

Story 4 (2026-10-01): litellm 1.102.1 ships that table with CRLF line endings, so its sha256
is wrong; tiktoken checks it at first use, deletes the file and wants to download it again.
WaveStack ships the official bytes (LF) in `tiktoken/` and points tiktoken there through
`CUSTOM_TIKTOKEN_CACHE_DIR`, the only variable litellm does not overwrite at its import
(`litellm_core_utils/default_encoding.py` rewrites `TIKTOKEN_CACHE_DIR` otherwise).
"""

from __future__ import annotations

import hashlib
import os
from pathlib import Path

OFFLINE_ENV = {
    "LITELLM_LOCAL_MODEL_COST_MAP": "True",
    "HEADROOM_OFFLINE": "1",
    "HEADROOM_BEACON": "off",
    "HEADROOM_UPDATE_CHECK": "off",
    "DO_NOT_TRACK": "1",
}

# tiktoken's cache names a table after the sha1 of its URL
# (https://openaipublic.blob.core.windows.net/encodings/cl100k_base.tiktoken); the sha256 is
# the `expected_hash` of `tiktoken_ext/openai_public.py`, which tiktoken checks at first use.
CL100K_BASE_FILE = "9b5ad71b2ce5302211f9c61530b329a4922fc6a4"
CL100K_BASE_SHA256 = "223921b76ee99bde995b7ff738513eef100fb51d18c93597a113bcffe865b2a7"
_SHIPPED_DIR = Path(__file__).resolve().parent / "tiktoken"


def tiktoken_cache_dir() -> Path:
    """The folder of the tiktoken table WaveStack ships (`cl100k_base`, the table of the
    adapter's `COUNTING_MODEL`); `.gitattributes` keeps its line endings untouched."""
    return _SHIPPED_DIR


def tiktoken_table_problem() -> str | None:
    """`"missing"` or `"altered"` (sha256 different) when the shipped `cl100k_base` table
    cannot be used, `None` when it can. Checked before Headroom is imported: tiktoken would
    delete a wrong file and go to the network for another one."""
    path = tiktoken_cache_dir() / CL100K_BASE_FILE
    try:
        data = path.read_bytes()
    except OSError:
        return "missing"
    return None if hashlib.sha256(data).hexdigest() == CL100K_BASE_SHA256 else "altered"


def apply_offline_env() -> None:
    """Set the variables (they win over the user's environment: no telemetry, NFR-3)."""
    os.environ.update(OFFLINE_ENV)
    cache = str(tiktoken_cache_dir())
    os.environ["CUSTOM_TIKTOKEN_CACHE_DIR"] = cache  # read by litellm at its import
    os.environ["TIKTOKEN_CACHE_DIR"] = cache  # read by tiktoken, if imported without litellm
