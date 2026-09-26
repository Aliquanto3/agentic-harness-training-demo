"""Headroom (`headroom-ai`, Apache-2.0), the `Compressor` adapter retained by story 12.

Optional: installed by the `compression` extra (`uv sync --extra compression`). Without it,
or with another version, `missing_fr()` says why and the brick is unavailable. The import is
heavy (litellm, tiktoken): it happens in the constructor, on the session's worker, when the
brick is switched on, never at WaveStack's start.

Story 12's conditions: exact pin, offline variables set before the import, and ML
compression off (`kompress_model="disabled"`: no model, no download, no torch). Without
Kompress, Headroom reduces structured text (JSON arrays, logs) and leaves prose as it is.
"""

from __future__ import annotations

import importlib.metadata
import importlib.util
from typing import Any

from wavestack.compression.env import apply_offline_env
from wavestack.compression.port import Compressed

HEADROOM_VERSION = "0.38.0"
# Headroom counts its own tokens with this model's tiktoken table (`o200k_base`, shipped by
# litellm): only its internal decisions use them, WaveStack counts its own (AD-1).
COUNTING_MODEL = "gpt-4o"
_INSTALL_FR = "Installez-la depuis le dossier de WaveStack avec `uv sync --extra compression`"
# A short JSON array: the warm-up call pays the lazy imports once, at load time.
_WARM_UP = '[{"id": 1, "etat": "ok"}, {"id": 2, "etat": "ok"}, {"id": 3, "etat": "erreur"}]'


def missing_fr() -> str | None:
    """Why Headroom cannot be used, in French with the command to run; `None` when the pinned
    version is installed."""
    if importlib.util.find_spec("headroom") is None:
        return (
            f"Indisponible : la bibliothèque Headroom (headroom-ai {HEADROOM_VERSION}), "
            f"dépendance optionnelle, n'est pas installée. {_INSTALL_FR}, puis relancez "
            "WaveStack. Les autres briques fonctionnent sans elle."
        )
    try:
        version = importlib.metadata.version("headroom-ai")
    except importlib.metadata.PackageNotFoundError:
        version = "inconnue"
    if version != HEADROOM_VERSION:
        return (
            f"Indisponible : headroom-ai {version} est installé, alors que WaveStack a été "
            f"vérifié hors ligne avec la version {HEADROOM_VERSION} seulement. {_INSTALL_FR}, "
            "puis relancez WaveStack."
        )
    return None


def _messages(text: str) -> list[dict[str, Any]]:
    """`text` as a tool's reply, the only message Headroom may compress (`protect_recent=0`);
    the user message before it is protected by Headroom and left out of the result."""
    call = {"id": "c1", "type": "function", "function": {"name": "outil", "arguments": "{}"}}
    return [
        {"role": "user", "content": "Résultat à compresser."},
        {"role": "assistant", "content": None, "tool_calls": [call]},
        {"role": "tool", "tool_call_id": "c1", "content": text},
    ]


class HeadroomCompressor:
    """Loaded by the session through the `LoadRegistry` (AD-8): import, then one warm-up."""

    label_fr = f"Headroom {HEADROOM_VERSION}"

    def __init__(self) -> None:
        reason = missing_fr()
        if reason is not None:
            raise RuntimeError(reason)
        apply_offline_env()  # again: a test or a script may import the session without `cli`
        from headroom import compress  # heavy and optional: imported at load time only

        self._compress = compress
        self.compress(_WARM_UP)

    def compress(self, text: str) -> Compressed:
        result = self._compress(
            _messages(text),
            model=COUNTING_MODEL,
            kompress_model="disabled",
            protect_recent=0,
        )
        after = result.messages[-1].get("content")
        if not isinstance(after, str):  # another shape than the one sent: keep the original
            return Compressed(text)
        return Compressed(after, tuple(str(t) for t in result.transforms_applied))

    def close(self) -> None:
        """Nothing to free: the module stays imported, as any library (its RSS stays counted
        until WaveStack stops; the registry's grant is released)."""
