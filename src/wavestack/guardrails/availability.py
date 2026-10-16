"""Why the `guardrails` brick cannot be used (CAP-5), the same shape as
`compression.headroom_adapter.missing_fr`: an optional dependency, checked once."""

from __future__ import annotations

from importlib.util import find_spec

from wavestack.messages import Message

_INSTALL = "uv sync --extra guardrails"


def missing_fr() -> str | Message | None:
    """`None` once `onnxruntime`, `tokenizers`, `presidio_analyzer`/`presidio_anonymizer` and
    `spacy` are all importable; the brick reports "non installés" with the command otherwise.
    Each guardrail's own model (gravitee, Presidio's `fr_core_news_sm`) is downloaded or
    loaded lazily, at its first use (story 4), never at this check."""
    missing = [
        name
        for name in (
            "onnxruntime",
            "tokenizers",
            "presidio_analyzer",
            "presidio_anonymizer",
            "spacy",
        )
        if find_spec(name) is None
    ]
    if not missing:
        return None
    return Message("guardrails.missing", install=Message("guardrails.install", command=_INSTALL))
