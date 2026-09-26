"""The `Compressor` port (AD-22) and the texts of the `compression` brick (AD-19)."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Protocol

import yaml
from pydantic import BaseModel, Field

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


def load_compression_content() -> CompressionContent:
    """Raises on a missing or invalid file (the session traces it)."""
    path = config.content_dir() / "compression.yaml"
    return CompressionContent.model_validate(yaml.safe_load(path.read_text(encoding="utf-8")))
