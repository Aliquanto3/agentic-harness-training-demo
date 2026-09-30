"""The `Compressor` port (AD-22) and the texts of the `compression` brick (AD-19)."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Protocol

import yaml
from pydantic import BaseModel, Field, model_validator

from wavestack import config


@dataclass(frozen=True)
class Compressed:
    """What a compressor returns for one text: the new text, and the names of what it did."""

    text: str
    transforms: tuple[str, ...] = ()


class Compressor(Protocol):
    """A loaded compressor: `compress` may raise (the session traces it, AD-16)."""

    label_fr: str  # « Headroom 0.38.0 », shown in the step and the schema

    def compress(self, text: str) -> Compressed: ...

    def close(self) -> None: ...


class CompressionContent(BaseModel):
    """`content/compression.yaml`: what the step and the card say, in French."""

    phase_label_fr: str = Field(min_length=1)  # « Compression du contexte… »
    step_title_fr: str = Field(min_length=1)  # « Compression (Headroom) »
    tool_source_fr: str = Field(min_length=1)  # « Résultat de l'outil « {tool} » »
    rag_source_fr: str = Field(min_length=1)  # « Extrait RAG n° {n} »
    unchanged_fr: str = Field(min_length=1)  # a candidate left as it was
    limits_fr: str = Field(min_length=1)  # the card's line: scope and threshold ({min_chars})

    @model_validator(mode="after")
    def _templates_format(self) -> CompressionContent:
        """Each template takes its own placeholder only: a typo fails at load time (the brick
        is then unavailable with the file named), never in the middle of a turn."""
        for field, values in (
            ("tool_source_fr", {"tool": "read_file"}),
            ("rag_source_fr", {"n": 1}),
            ("limits_fr", {"min_chars": 300}),
        ):
            try:
                getattr(self, field).format(**values)
            except (KeyError, IndexError, ValueError) as exc:
                raise ValueError(f"{field}: gabarit invalide ({exc!r})") from exc
        return self


def load_compression_content(lang: str | None = None) -> CompressionContent:
    """Raises on a missing or invalid file (the session traces it)."""
    path = config.content_file("compression.yaml", lang)
    return CompressionContent.model_validate(yaml.safe_load(path.read_text(encoding="utf-8")))
