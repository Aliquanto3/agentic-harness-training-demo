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
from wavestack.messages import join, msg, number, render
from wavestack.models.candidates import piece_text
from wavestack.models.gguf_meta import dimensions_from_header, positive_size

# Shared with the models layer: the servers' sizes, the candidates' texts.
__all__ = ["dimensions_from_header", "piece_text"]

TOKEN_LIMIT = 512  # the chips shown at most: the page stays fluid on a projector
TEXT_LIMIT = 2000  # the characters of a prompt the screen accepts

# The dimensions a model's diagram shows, in its order.
DIMENSION_KEYS = ("vocab_size", "embedding_length", "layer_count", "head_count", "context_length")


class _Strict(BaseModel):
    model_config = ConfigDict(extra="forbid")


class PluralText(_Strict):
    """A count-bearing text (correctif nuit du 2026-10-01, restes différés) : `one` for a
    singular count (`Intl.PluralRules`: 0 and 1 in French, 1 only in English and German),
    `other` otherwise, chosen by `llm.js`'s `text()` the way `i18n.js`'s `t()` already does
    for `content/ui.yaml`."""

    one: str
    other: str


class LabSection(_Strict):
    title_text: str
    intro_text: str
    # Story 5 of 2026-09-30: « Les questions que vous vous posez », the section answering them.
    questions_text: list[str]


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
    # Correctif nuit du 2026-10-01 (restes différés) : `token_noun` and `character_noun` are
    # the plural noun phrases `counts_text` and `estimate_text` compose from (`{n}` tokens
    # or characters); `more_text` is a lone count, so it is plural on its own.
    token_noun: PluralText
    character_noun: PluralText
    counts_text: str
    more_text: PluralText
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
    token_noun: PluralText  # correctif nuit du 2026-10-01 : `tokens_text` composes two of these
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
    count_text: PluralText  # correctif nuit du 2026-10-01 : « 1 tokens produits »
    fragments_text: PluralText
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
    count_text: PluralText  # correctif nuit du 2026-10-01
    fragments_count_text: PluralText
    reserve_text: PluralText


class CandidatesText(_Strict):
    toggle_text: str
    help_text: str
    title_text: str
    probability_text: str
    chance_text: str
    dropped_text: str
    chosen_text: str
    legend_text: str


class DistributionText(_Strict):
    """Story 5 of 2026-09-30: section 2's live distribution."""

    title_text: str
    intro_text: str
    empty_text: str
    token_text: str
    probability_text: str
    chance_text: str
    dropped_text: str
    kept_text: str
    more_text: str
    tail_text: str
    tail_help_text: str


class CompareText(_Strict):
    """Story 5 of 2026-09-30: section 5's A/B comparison."""

    title_text: str
    intro_text: str
    b_settings_text: str
    button_text: str
    running_text: str
    lane_a_text: str
    lane_b_text: str
    waiting_text: str
    empty_text: str


class WindowText(_Strict):
    """Story 5 of 2026-09-30: section 4's diagram of the context window."""

    title_text: str
    prompt_text: str
    free_text: str
    reserve_text: str
    output_text: PluralText  # correctif nuit du 2026-10-01 : « Réponse : 1 tokens »
    output_fragments_text: PluralText  # a server or a cloud model: fragments, not tokens
    caption_text: str


class LabContent(_Strict):
    title_text: str
    intro_text: str
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
    distribution: DistributionText  # story 5 of 2026-09-30
    compare: CompareText
    window: WindowText


@cache
def _read_lab_content(path: str, mtime_ns: int) -> LabContent:
    return LabContent.model_validate(yaml.safe_load(Path(path).read_text(encoding="utf-8")))


def load_lab_content(lang: str = config.DEFAULT_LANGUAGE) -> LabContent:
    """Read `content/llm_lab.yaml` in `lang` (languages 4/5: the session's, never
    `settings.json`'s), again once the file changed (its modification time): a corrected
    file shows on the page's reload. Raises on an invalid file (the session traces it)."""
    path = config.content_file("llm_lab.yaml", lang)
    return _read_lab_content(str(path), path.stat().st_mtime_ns)


load_lab_content.cache_clear = _read_lab_content.cache_clear  # type: ignore[attr-defined]


def fr_int(n: int) -> str:
    """« 151 936 »: French thousands separator (narrow no-break space)."""
    return f"{n:,}".replace(",", " ")


def fr_count(n: int) -> str:
    """A large count in words: « 311 millions », « 1,2 milliard », else `fr_int`."""
    return count_text(n, config.DEFAULT_LANGUAGE)


# ---------- figures in the session's language (languages 5/5) ----------


def _french(lang: str) -> bool:
    return config.as_language(lang) == config.DEFAULT_LANGUAGE


def lang_int(n: int, lang: str) -> str:
    """`fr_int` in `lang`: « 151 936 », « 151,936 », « 151.936 »."""
    return fr_int(n) if _french(lang) else number(n, lang)


def count_text(n: int, lang: str) -> str:
    """`fr_count` in `lang`: « 1,2 milliard », « 1.2 billion », « 1,2 Milliarden »."""
    for size, word in ((10**9, "billion"), (10**6, "million")):
        value = n / size
        # The unit and the plural from the rounded value: never « 1000 millions ».
        rounded = round(value, 1) if value < 10 else float(round(value))
        if rounded >= 1 and (size == 10**9 or rounded < 1000):
            text = f"{rounded:.1f}".rstrip("0").rstrip(".")
            if _french(lang):
                text = text.replace(".", ",")
            else:
                text = number(rounded, lang, 1 if "." in text else 0)
            return msg(f"llm_lab.count.{word}", lang, count=rounded, n=text)
    return lang_int(n, lang)


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


def dimensions_payload(
    dims: dict[str, Any] | None, source_text: str, *, lang: str = config.DEFAULT_LANGUAGE
) -> dict[str, Any]:
    """`llm_tokenized.dimensions`: the values (`None` when unknown), the embedding table's
    size (vocabulary × dimension), their figures in `lang`, and where they come from (a
    `Message` rendered in `lang`), with what is unknown."""
    values = {name: positive_size((dims or {}).get(name)) for name in DIMENSION_KEYS}
    vocab, width = values["vocab_size"], values["embedding_length"]
    params = vocab * width if vocab and width else None
    figures = {name: lang_int(v, lang) if v else None for name, v in values.items()}
    figures["embedding_params"] = count_text(params, lang) if params else None
    source_text = render(source_text, lang)
    missing = [msg(f"llm_lab.dimension.{n}", lang) for n in DIMENSION_KEYS if values[n] is None]
    if missing:
        source_text = msg("llm_lab.unknown", lang, source=source_text, names=join(missing, lang))
    return values | {
        "embedding_params": params,
        "figures_text": figures,
        "source_text": source_text,
    }


def dimensions_fr(values: dict[str, Any], *, lang: str = config.DEFAULT_LANGUAGE) -> str:
    """One sentence of the diagram, in `lang`: what a token becomes, with the figures known
    (`values`: `dimensions_payload`'s, built in the same language)."""
    width, layers = (
        values.get("figures_text", {}).get("embedding_length"),
        values.get("layer_count"),
    )
    if not width:
        return msg("llm_lab.width_unknown", lang)
    if layers:
        return msg("llm_lab.vector_layers", lang, width=width, layers=lang_int(layers, lang))
    return msg("llm_lab.vector", lang, width=width)
