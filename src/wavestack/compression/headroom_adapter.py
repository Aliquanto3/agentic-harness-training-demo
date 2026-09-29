"""Headroom (`headroom-ai`, Apache-2.0), the `Compressor` adapter retained by story 12.

Optional: installed by the `compression` extra (`uv sync --extra compression`). Without it,
or with another version, `missing_fr()` says why and the brick is unavailable. The import is
heavy (litellm, tiktoken): it happens in the constructor, on the session's worker, when the
brick is switched on, never at WaveStack's start.

Story 12's conditions: exact pin, offline variables set before the import, and ML
compression off (`kompress_model="disabled"`: no model, no download, no torch). Without
Kompress, Headroom reduces structured text (JSON arrays, logs) and leaves prose as it is.

`HF_HUB_OFFLINE` (in story 12's measured variant) is set only while Headroom imports and
compresses: `huggingface_hub`, which only Headroom's dependencies import, reads it once, at
its import. WaveStack's own downloads go through `net`, never through `huggingface_hub`, so
`cli` keeps it unset for the rest of the process (AD-15).

Headroom 0.38.0 does not use the user's question to choose what to keep (measured on the demo
log and a JSON array: the same output whatever the question), so none is passed.
"""

from __future__ import annotations

import importlib.metadata
import importlib.util
import os
from collections.abc import Iterator
from contextlib import contextmanager
from typing import Any

from wavestack.compression.env import apply_offline_env
from wavestack.compression.port import Compressed

HEADROOM_VERSION = "0.38.0"
# Headroom counts its own tokens with this model's tiktoken table: only its internal decisions
# use them, WaveStack counts its own (AD-1). `gpt-4` reads `cl100k_base`, which every copy of
# litellm ships (`TIKTOKEN_CACHE_DIR`, see `env`); `gpt-4o` read `o200k_base`, missing from the
# target PC's cache (2026-09-27), so tiktoken tried to download it (AD-15). Lot F.
COUNTING_MODEL = "gpt-4"
_INSTALL_FR = "Installez-la depuis le dossier de WaveStack avec `uv sync --extra compression`"
# A short JSON array: the warm-up call pays the lazy imports once, at load time.
_WARM_UP = '[{"id": 1, "etat": "ok"}, {"id": 2, "etat": "ok"}, {"id": 3, "etat": "erreur"}]'
# Indirections, so a test can pretend Headroom is absent without patching `importlib` itself.
_find_spec = importlib.util.find_spec
_version = importlib.metadata.version


def missing_fr() -> str | None:
    """Why Headroom cannot be used, in French with the command to run; `None` when the pinned
    version is installed."""
    if _find_spec("headroom") is None:
        return (
            f"Indisponible : la bibliothèque Headroom (headroom-ai {HEADROOM_VERSION}), "
            f"dépendance optionnelle, n'est pas installée. {_INSTALL_FR}, puis relancez "
            "WaveStack. Les autres briques fonctionnent sans elle."
        )
    try:
        version = _version("headroom-ai")
    except importlib.metadata.PackageNotFoundError:
        version = "inconnue"
    if version != HEADROOM_VERSION:
        return (
            f"Indisponible : headroom-ai {version} est installé, alors que WaveStack a été "
            f"vérifié hors ligne avec la version {HEADROOM_VERSION} seulement. {_INSTALL_FR}, "
            "puis relancez WaveStack."
        )
    return None


@contextmanager
def hf_offline() -> Iterator[None]:
    """`HF_HUB_OFFLINE=1` while Headroom runs, then the previous value back."""
    previous = os.environ.get("HF_HUB_OFFLINE")
    os.environ["HF_HUB_OFFLINE"] = "1"
    try:
        yield
    finally:
        if previous is None:
            os.environ.pop("HF_HUB_OFFLINE", None)
        else:
            os.environ["HF_HUB_OFFLINE"] = previous


def _messages(text: str) -> list[dict[str, Any]]:
    """`text` as a tool's reply, the only message Headroom may compress (`protect_recent=0`);
    the user message before it is protected by Headroom and left out of the result."""
    call = {"id": "c1", "type": "function", "function": {"name": "outil", "arguments": "{}"}}
    return [
        {"role": "user", "content": "Résultat à compresser."},
        {"role": "assistant", "content": None, "tool_calls": [call]},
        {"role": "tool", "tool_call_id": "c1", "content": text},
    ]


def reply_text(messages: Any, original: str) -> str:
    """The compressed reply, only when Headroom gives back the shape sent: a list whose last
    message is the tool's reply, as a string. Anything else keeps the original."""
    if not isinstance(messages, list) or not messages:
        return original
    last = messages[-1]
    if not isinstance(last, dict) or last.get("role") != "tool":
        return original
    content = last.get("content")
    return content if isinstance(content, str) else original


class HeadroomCompressor:
    """Loaded by the session through the `LoadRegistry` (AD-8): import, then one warm-up."""

    label_fr = f"Headroom {HEADROOM_VERSION}"

    def __init__(self) -> None:
        reason = missing_fr()
        if reason is not None:
            raise RuntimeError(reason)
        apply_offline_env()  # again: a test or a script may import the session without `cli`
        with hf_offline():
            from headroom import compress  # heavy and optional: imported at load time only

        self._compress = compress
        self.compress(_WARM_UP)

    def compress(self, text: str) -> Compressed:
        with hf_offline():
            result = self._compress(
                _messages(text),
                model=COUNTING_MODEL,
                kompress_model="disabled",
                protect_recent=0,
            )
        after = reply_text(getattr(result, "messages", None), text)
        if after is text:
            return Compressed(text)
        transforms = getattr(result, "transforms_applied", None) or ()
        return Compressed(after, tuple(str(t) for t in transforms))

    def close(self) -> None:
        """Nothing to free: the module stays imported, as any library (its RSS stays counted
        until WaveStack stops; the registry's grant is released, and a new load costs 0)."""
