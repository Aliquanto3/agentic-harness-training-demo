"""The « LLM nu » screen (story 29): its texts (`content/llm_lab.yaml`, AD-19) and the pure
functions the session builds its events with (AD-1: the page counts nothing).

Everything here runs without an engine: token rows from ids and pieces, a model's dimensions
from a GGUF header or an engine's answer, and their French figures.
"""

from __future__ import annotations

from collections.abc import Iterable, Sequence
from functools import cache
from pathlib import Path
from typing import Any

import yaml
from pydantic import BaseModel, ConfigDict

from wavestack import config
from wavestack.models.candidates import piece_text
from wavestack.models.gguf_meta import dimensions_from_header, positive_size

# Shared with the models layer: the servers' sizes, the candidates' texts.
__all__ = ["dimensions_from_header", "piece_text"]

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
    title_text: str
    intro_text: str


class LabSections(_Strict):
    tokenization: LabSection
    sampling: LabSection
    loading: LabSection
    reading: LabSection
    generation: LabSection
    reasoning: LabSection


class TokenizationText(_Strict):
    prompt_label_text: str
    placeholder_text: str
    default_text_text: str
    button_text: str
    running_text: str
    counts_text: str
    more_text: str
    special_text: str
    special_help_text: str
    blanks_text: str
    exact_text: str
    estimate_text: str
    empty_text: str


class DiagramSteps(_Strict):
    text_text: str
    tokens_text: str
    ids_text: str
    table_text: str
    table_caption_text: str
    params_text: str
    vector_text: str
    vector_caption_text: str
    layers_text: str
    layers_caption_text: str
    layers_only_caption_text: str


class VectorizationText(_Strict):
    title_text: str
    help_text: str
    unknown_text: str
    steps: DiagramSteps


class SamplingSetting(_Strict):
    label_text: str
    help_text: str


class SamplingSettings(_Strict):
    temperature: SamplingSetting
    top_k: SamplingSetting
    top_p: SamplingSetting
    min_p: SamplingSetting


class SamplingText(_Strict):
    reset_text: str
    unsupported_text: str
    settings: SamplingSettings


class ReadingText(_Strict):
    empty_text: str
    rendered_label_text: str
    body_label_text: str
    tokens_text: str
    waiting_text: str
    first_token_text: str
    read_rate_text: str
    read_rate_unknown_text: str
    sampling_text: str


class GenerationStatus(_Strict):
    completed: str
    cancelled: str
    limit: str
    error: str


class GenerationText(_Strict):
    button_text: str
    stop_text: str
    running_text: str
    empty_text: str
    count_text: str
    fragments_text: str
    rate_text: str
    cloud_text: str
    server_text: str
    more_text: str
    status: GenerationStatus


class LoadingStatus(_Strict):
    ok: str
    restored: str
    cancelled: str
    error: str


class LoadingText(_Strict):
    empty_text: str
    running_text: str
    total_text: str
    local_text: str
    status: LoadingStatus


class ReasoningText(_Strict):
    toggle_text: str
    always_text: str
    thinking_text: str
    answer_text: str
    empty_text: str
    count_text: str
    fragments_count_text: str
    reserve_text: str


class CandidatesText(_Strict):
    toggle_text: str
    help_text: str
    title_text: str
    probability_text: str
    chance_text: str
    dropped_text: str
    chosen_text: str
    legend_text: str


class LabContent(_Strict):
    title_text: str
    intro_text: str
    back_text: str
    change_model_text: str
    active_model_text: str
    no_model_text: str
    busy_text: str
    sections: LabSections
    tokenization: TokenizationText
    vectorization: VectorizationText
    sampling: SamplingText  # story 29, increment 2
    reading: ReadingText
    generation: GenerationText
    loading: LoadingText  # story 29, increment 3
    reasoning: ReasoningText
    candidates: CandidatesText  # story 29, increment 4


@cache
def _read_lab_content(path: str, mtime_ns: int) -> LabContent:
    return LabContent.model_validate(yaml.safe_load(Path(path).read_text(encoding="utf-8")))


def load_lab_content() -> LabContent:
    """Read `content/llm_lab.yaml`, again once the file changed (its modification time): a
    corrected file shows on the page's reload. Raises on an invalid file (the session traces
    it)."""
    path = config.content_file("llm_lab.yaml")
    return _read_lab_content(str(path), path.stat().st_mtime_ns)


load_lab_content.cache_clear = _read_lab_content.cache_clear  # type: ignore[attr-defined]


def fr_int(n: int) -> str:
    """« 151 936 »: French thousands separator (narrow no-break space)."""
    return f"{n:,}".replace(",", " ")


def fr_count(n: int) -> str:
    """A large count in words: « 311 millions », « 1,2 milliard », else `fr_int`."""
    for size, word in ((10**9, "milliard"), (10**6, "million")):
        value = n / size
        # The unit and the plural from the rounded value: never « 1000 millions ».
        rounded = round(value, 1) if value < 10 else float(round(value))
        if rounded >= 1 and (size == 10**9 or rounded < 1000):
            text = f"{rounded:.1f}".rstrip("0").rstrip(".").replace(".", ",")
            return f"{text} {word}{'s' if rounded >= 2 else ''}"
    return fr_int(n)


# ---------- tokens ----------


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


def dimensions_payload(dims: dict[str, Any] | None, source_text: str) -> dict[str, Any]:
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
        source_text = f"{source_text} Inconnus : {_join_fr(missing)}."
    return values | {
        "embedding_params": params,
        "figures_text": figures,
        "source_text": source_text,
    }


def dimensions_fr(values: dict[str, Any]) -> str:
    """One sentence of the diagram: what a token becomes, with the figures known."""
    width, layers = (
        values.get("figures_text", {}).get("embedding_length"),
        values.get("layer_count"),
    )
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
