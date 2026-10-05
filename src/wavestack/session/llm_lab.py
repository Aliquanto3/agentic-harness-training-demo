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
from wavestack.models import gguf_meta
from wavestack.models.candidates import piece_text
from wavestack.models.gguf_meta import dimensions_from_header, positive_size

# Shared with the models layer: the servers' sizes, the candidates' texts.
__all__ = ["dimensions_from_header", "piece_text"]

TOKEN_LIMIT = 512  # the chips shown at most: the page stays fluid on a projector
TEXT_LIMIT = 2000  # the characters of a prompt the screen accepts
STEP_LIMIT = 64  # lot 6: the tokens the OUTPUT may add to the INPUT, one step at a time

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


# ---------- lot 6 of 2026-10-04: the model's loop in three stages ----------


class StageStep(_Strict):
    """One step of a stage's stepper: its caption's title and text."""

    title_text: str
    text_text: str


class InputRows(_Strict):
    text_text: str
    tokens_text: str
    ids_text: str


class InputSteps(_Strict):
    text: StageStep
    tokens: StageStep
    ids: StageStep


class InputStage(_Strict):
    """1 INPUT: the text, its tokens, their ids, in aligned columns (real)."""

    title_text: str
    subtitle_text: str
    tag_text: str
    link_text: str  # the line down to the TRANSFORMATION
    rows: InputRows
    steps: InputSteps
    ids_count_text: PluralText  # « 5 nombres entre 0 et 248 319 »
    ids_unknown_text: PluralText  # the vocabulary's size unknown
    added_text: PluralText  # « dont 1 ajouté par l'OUTPUT », the session's figures unchanged
    column_label_text: str  # a column's accessible name
    produced_label_text: str  # the same, for a token the engine drew and the trainer added
    bos_text: str  # « Avant ces tokens, le moteur lit aussi {bos} » (the step's BOS)


class TransfoSteps(_Strict):
    embed: StageStep
    attention: StageStep
    mlp: StageStep
    attention_2: StageStep
    mlp_2: StageStep
    skip: StageStep
    final: StageStep


class TransfoLabels(_Strict):
    """The canvas's texts (an illustrative drawing: the figures in it are the model's)."""

    tokens_text: str
    ids_text: str
    vectors_text: str
    drawn_text: str
    of_text: str
    table_text: str
    table_rows_text: str
    attention_text: str
    self_text: str
    mlp_title_text: str
    mlp_real_text: str
    input_text: str
    output_text: str
    mlp_note_text: str
    moe_title_text: str
    moe_drawn_text: str
    moe_drawn_any_text: str
    expert_text: str
    expert_active_text: str
    moe_note_text: str
    layers_text: str
    layers_unknown_text: str
    final_text: str


class TransfoPanel(_Strict):
    """The panel beside the canvas: « En vrai, pour {modèle} » and the stack of layers."""

    facts_title_text: str
    width_text: str
    table_text: str
    table_only_text: str
    layers_text: str
    layers_unknown_text: str
    heads_text: str
    heads_kv_text: str
    mlp_text: str
    moe_text: str
    moe_any_text: str
    stack_title_text: str
    stack_none_text: str
    stack_now_text: str
    stack_hybrid_text: str
    stack_done_text: str
    stack_unknown_text: str
    unknown_text: str  # no dimension read (a cloud model): in place of the facts


class TransfoStage(_Strict):
    """2 TRANSFORMATION: embeddings, layers (attention, MLP), the last vector (illustrative,
    the real dimensions), and the banner of a hybrid or a mixture of experts (D4)."""

    title_text: str
    subtitle_text: str
    tag_text: str
    link_text: str  # the line down to the OUTPUT
    steps: TransfoSteps
    attention_alone_text: str  # one token only: it looks at itself
    skip_unknown_text: str  # the layers' count unknown
    moe_mlp_text: str  # appended to the MLP steps' text for a mixture of experts
    example_text: str
    example_tokens: list[str]  # drawn before any tokenization, said « exemple »
    labels: TransfoLabels
    panel: TransfoPanel
    note_text: PluralText  # « {n} tokens, 8 nombres par vecteur… »
    banner_title_text: str
    banner_hybrid_text: str
    banner_hybrid_any_text: str
    banner_moe_text: str
    banner_moe_any_text: str
    unknown_architecture_text: str


class OutputSteps(_Strict):
    logits: StageStep
    draw: StageStep
    token: StageStep


class OutputStage(_Strict):
    """3 OUTPUT: logits, the draw and its settings, the token the engine drew (real)."""

    title_text: str
    subtitle_text: str
    tag_text: str
    steps: OutputSteps
    logits_title_text: str
    logits_text: str
    logits_start_text: str
    arrow_logits_text: str
    draw_title_text: str
    draw_text: str
    dropped_text: str  # « écarté ({reglage}) »
    kept_text: PluralText
    arrow_draw_text: str
    token_title_text: str
    draw_button_text: str
    append_text: str
    undo_text: str
    none_text: str
    history_text: str
    running_text: str
    end_text: str
    raw_text: str  # the step reads the text without the chat template, unlike « Générer »
    limit_text: str
    step_token_text: str
    help_text: str  # the « ? » of a setting's name, for screen readers
    tokenize_first_text: str  # « Tirer » waits for the tokens of the text typed


class StagesText(_Strict):
    show_all_text: str  # the stepper's right button for INPUT and TRANSFORMATION
    input: InputStage
    transfo: TransfoStage
    output: OutputStage


class LabContent(_Strict):
    title_text: str
    intro_text: str
    change_model_text: str
    active_model_text: str
    no_model_text: str
    busy_text: str
    sections: LabSections
    stages: StagesText  # lot 6 of 2026-10-04
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
    dims: dict[str, Any] | None,
    source_text: str,
    *,
    lang: str = config.DEFAULT_LANGUAGE,
    architecture: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """`llm_tokenized.dimensions`: the values (`None` when unknown), the embedding table's
    size (vocabulary × dimension), their figures in `lang`, and where they come from (a
    `Message` rendered in `lang`), with what is unknown. Lot 6 of 2026-10-04: the largest
    id (`figures_text.max_id`, the INPUT's « entre 0 et … ») and `architecture` (D4,
    `architecture_from_header`'s), `None` when not given."""
    values = {name: positive_size((dims or {}).get(name)) for name in DIMENSION_KEYS}
    vocab, width = values["vocab_size"], values["embedding_length"]
    params = vocab * width if vocab and width else None
    figures = {name: lang_int(v, lang) if v else None for name, v in values.items()}
    figures["embedding_params"] = count_text(params, lang) if params else None
    figures["max_id"] = lang_int(vocab - 1, lang) if vocab else None
    source_text = render(source_text, lang)
    missing = [msg(f"llm_lab.dimension.{n}", lang) for n in DIMENSION_KEYS if values[n] is None]
    if missing:
        source_text = msg("llm_lab.unknown", lang, source=source_text, names=join(missing, lang))
    return values | {
        "embedding_params": params,
        "figures_text": figures,
        "source_text": source_text,
        "architecture": architecture,
    }


# ---------- lot 6 of 2026-10-04 (D4): the model's family, from its GGUF header ----------

# Architectures llama.cpp runs with recurrent (or convolution) layers among the attention ones.
HYBRID_ARCHITECTURES = frozenset(
    {
        "mamba",
        "mamba2",
        "rwkv6",
        "rwkv7",
        "jamba",
        "falcon-h1",
        "granitehybrid",
        "lfm2",
        "nemotron_h",
        "plamo2",
    }
)
# `{arch}.{prefix}…` keys only a recurrent (or short convolution) layer has.
HYBRID_KEY_PREFIXES = ("ssm.", "shortconv.", "wkv.")
ARCHITECTURE_FIGURES = (
    "attention_interval",
    "kv_head_count",
    "feed_forward_length",
    "expert_count",
    "expert_used_count",
)


def _regular_interval(kv_heads: list[Any]) -> int | None:
    """The period of the full-attention layers when a per-layer `head_count_kv` (0: a
    recurrent layer) puts them exactly every n layers, the last of each n; else `None`."""
    attends = [isinstance(v, int | float) and not isinstance(v, bool) and v > 0 for v in kv_heads]
    if not any(attends) or all(attends):
        return None
    period = attends.index(True) + 1
    regular = all(a == ((i + 1) % period == 0) for i, a in enumerate(attends))
    return period if regular else None


def classify_header(meta: dict[str, Any] | None) -> dict[str, Any]:
    """The family of a GGUF header (`gguf_meta.read_metadata`), its values only. Hybrid
    when `{arch}.ssm.*`, `{arch}.full_attention_interval`, `{arch}.shortconv.*`, `{arch}.wkv.*`,
    a per-layer `{arch}.attention.head_count_kv` holding a 0, or an architecture of
    `HYBRID_ARCHITECTURES`; a mixture of experts when `{arch}.expert_count > 1` (noted besides
    on a hybrid); `unknown` without `general.architecture`."""
    meta = meta or {}
    arch = meta.get("general.architecture")
    empty: dict[str, Any] = dict.fromkeys(("name", *ARCHITECTURE_FIGURES))
    if not isinstance(arch, str) or not arch:
        return empty | {"family": "unknown"}
    prefix = f"{arch}."

    def key(name: str) -> Any:
        return meta.get(prefix + name)

    kv = key("attention.head_count_kv")
    hybrid = (
        arch in HYBRID_ARCHITECTURES
        or prefix + "full_attention_interval" in meta
        or any(k.startswith(prefix + p) for k in meta for p in HYBRID_KEY_PREFIXES)
        or (isinstance(kv, list) and 0 in kv)
    )
    experts = positive_size(key("expert_count"))
    moe = experts is not None and experts > 1
    interval = positive_size(key("full_attention_interval")) if hybrid else None
    if hybrid and interval is None and isinstance(kv, list):
        interval = _regular_interval(kv)
    width = positive_size(key("expert_feed_forward_length")) if moe else None
    return empty | {
        "name": arch,
        "family": "hybrid" if hybrid else "moe" if moe else "dense",
        "attention_interval": interval,
        "kv_head_count": positive_size(kv),
        "feed_forward_length": width or positive_size(key("feed_forward_length")),
        "expert_count": experts if moe else None,
        "expert_used_count": positive_size(key("expert_used_count")) if moe else None,
    }


def _with_figures(values: dict[str, Any], lang: str) -> dict[str, Any]:
    figures = {
        name: lang_int(values[name], lang) if values[name] else None
        for name in ARCHITECTURE_FIGURES
    }
    return dict(values) | {"figures_text": figures}


def architecture_from_header(
    meta: dict[str, Any] | None, *, lang: str = config.DEFAULT_LANGUAGE
) -> dict[str, Any]:
    """`llm_tokenized.dimensions.architecture` (`LlmArchitecture`): `classify_header`'s
    values and their figures in `lang`. Never raises: a header absent says `unknown`."""
    return _with_figures(classify_header(meta), lang)


@cache
def _header_family(path: str, mtime_ns: int) -> dict[str, Any]:
    return classify_header(gguf_meta.try_read_metadata(path))


def read_architecture(
    path: str | Path | None, *, lang: str = config.DEFAULT_LANGUAGE
) -> dict[str, Any]:
    """`architecture_from_header` of the GGUF file at `path`, its header read once per
    modification time (a 2 GB file's header, at each tokenization otherwise); `unknown`
    when the file is absent or not a readable GGUF."""
    try:
        mtime = Path(path).stat().st_mtime_ns if path else None
    except (OSError, ValueError):
        mtime = None
    if mtime is None:
        return architecture_from_header(None, lang=lang)
    return _with_figures(_header_family(str(path), mtime), lang)


read_architecture.cache_clear = _header_family.cache_clear  # type: ignore[attr-defined]


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
