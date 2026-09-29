"""The « LLM nu » screen (story 29): its texts (`content/llm_lab.yaml`, AD-19) and the pure
functions the session builds its events with (AD-1: the page counts nothing).

Everything here runs without an engine: token rows from ids and pieces, a model's dimensions
from a GGUF header or an engine's answer, and their French figures.
"""

from __future__ import annotations

from collections.abc import Iterable, Sequence
from functools import cache
from typing import Any

import yaml
from pydantic import BaseModel, ConfigDict

from wavestack import config
from wavestack.models.gguf_meta import dimensions_from_header, positive_size

__all__ = ["dimensions_from_header"]  # story 29: shared with the server adapters

TOKEN_LIMIT = 512  # the chips shown at most: the page stays fluid on a projector
TEXT_LIMIT = 2000  # the characters of a prompt the screen accepts

# The dimensions a model's diagram shows, in its order.
DIMENSION_KEYS = ("vocab_size", "embedding_length", "layer_count", "head_count", "context_length")
_DIMENSION_NAMES_FR = {
    "vocab_size": "le vocabulaire",
    "embedding_length": "la dimension d'embedding",
    "layer_count": "le nombre de couches",
    "head_count": "le nombre de têtes d'attention",
    "context_length": "le contexte natif",
}


class _Strict(BaseModel):
    model_config = ConfigDict(extra="forbid")


class LabSection(_Strict):
    title_fr: str
    intro_fr: str


class LabSections(_Strict):
    tokenization: LabSection
    sampling: LabSection
    loading: LabSection
    reading: LabSection
    generation: LabSection
    reasoning: LabSection


class TokenizationText(_Strict):
    prompt_label_fr: str
    placeholder_fr: str
    default_text_fr: str
    button_fr: str
    running_fr: str
    counts_fr: str
    more_fr: str
    special_fr: str
    special_help_fr: str
    blanks_fr: str
    exact_fr: str
    estimate_fr: str
    empty_fr: str


class DiagramSteps(_Strict):
    text_fr: str
    tokens_fr: str
    ids_fr: str
    table_fr: str
    table_caption_fr: str
    params_fr: str
    vector_fr: str
    vector_caption_fr: str
    layers_fr: str
    layers_caption_fr: str
    layers_only_caption_fr: str


class VectorizationText(_Strict):
    title_fr: str
    help_fr: str
    unknown_fr: str
    steps: DiagramSteps


class LabContent(_Strict):
    title_fr: str
    intro_fr: str
    back_fr: str
    change_model_fr: str
    active_model_fr: str
    no_model_fr: str
    busy_fr: str
    sections: LabSections
    tokenization: TokenizationText
    vectorization: VectorizationText


@cache
def load_lab_content() -> LabContent:
    """Read `content/llm_lab.yaml`. Raises on an invalid file (the session traces it)."""
    path = config.content_dir() / "llm_lab.yaml"
    return LabContent.model_validate(yaml.safe_load(path.read_text(encoding="utf-8")))


def fr_int(n: int) -> str:
    """« 151 936 »: French thousands separator (narrow no-break space)."""
    return f"{n:,}".replace(",", " ")


def fr_count(n: int) -> str:
    """A large count in words: « 311 millions », « 1,2 milliard », else `fr_int`."""
    for size, word in ((10**9, "milliard"), (10**6, "million")):
        if n >= size:
            value = n / size
            text = f"{value:.1f}".rstrip("0").rstrip(".") if value < 10 else f"{round(value)}"
            return f"{text.replace('.', ',')} {word}{'s' if value >= 2 else ''}"
    return fr_int(n)


# ---------- tokens ----------


def piece_text(piece: bytes) -> str:
    """A token's text: its UTF-8 bytes decoded, or, when they are only part of a character
    (a byte-level token, one of an emoji's four bytes), the bytes themselves: « ⟨F0 9F⟩ »."""
    try:
        return piece.decode("utf-8")
    except UnicodeDecodeError:
        return "⟨" + " ".join(f"{b:02X}" for b in piece) + "⟩"


def token_rows(
    ids: Sequence[int],
    pieces: Sequence[bytes],
    specials: Iterable[str],
    limit: int = TOKEN_LIMIT,
) -> tuple[list[dict[str, Any]], int]:
    """The chips of the first `limit` tokens, `{id, text, special}`, and how many more there
    are. `pieces`: the bytes of those tokens (at least the first `limit`); `specials`: the
    vocabulary's special tokens (template markers), each read as one token."""
    special = set(specials)
    rows = []
    for token, piece in zip(ids[:limit], pieces[:limit], strict=False):
        text = piece_text(piece)
        rows.append({"id": int(token), "text": text, "special": text in special})
    return rows, max(len(ids) - limit, 0)


# ---------- dimensions ----------


def merge_dimensions(*sources: dict[str, Any] | None) -> dict[str, int | None]:
    """The first known value of each dimension, in the order of `sources`."""
    merged: dict[str, int | None] = dict.fromkeys(DIMENSION_KEYS)
    for source in sources:
        for name in DIMENSION_KEYS:
            if merged[name] is None and source:
                merged[name] = positive_size(source.get(name))
    return merged


def dimensions_payload(dims: dict[str, Any] | None, source_fr: str) -> dict[str, Any]:
    """`llm_tokenized.dimensions`: the values (`None` when unknown), the embedding table's
    size (vocabulary × dimension), their French figures, and where they come from, with
    what is unknown."""
    values = {name: positive_size((dims or {}).get(name)) for name in DIMENSION_KEYS}
    vocab, width = values["vocab_size"], values["embedding_length"]
    params = vocab * width if vocab and width else None
    figures = {name: fr_int(v) if v else None for name, v in values.items()}
    figures["embedding_params"] = fr_count(params) if params else None
    missing = [_DIMENSION_NAMES_FR[n] for n in DIMENSION_KEYS if values[n] is None]
    if missing:
        source_fr = f"{source_fr} Inconnus : {_join_fr(missing)}."
    return values | {"embedding_params": params, "figures_fr": figures, "source_fr": source_fr}


def dimensions_fr(values: dict[str, Any]) -> str:
    """One sentence of the diagram: what a token becomes, with the figures known."""
    width, layers = values.get("figures_fr", {}).get("embedding_length"), values.get("layer_count")
    if not width:
        return (
            "Dimension d'embedding inconnue : le vecteur de chaque token existe, mais ce moteur "
            "ne dit pas sa taille."
        )
    if layers:
        return (
            f"Chaque token devient un vecteur de {width} nombres, que {fr_int(layers)} couches "
            "transforment l'une après l'autre."
        )
    return f"Chaque token devient un vecteur de {width} nombres, que les couches transforment."


def _join_fr(items: list[str]) -> str:
    if len(items) < 2:
        return "".join(items)
    return ", ".join(items[:-1]) + f" et {items[-1]}"
