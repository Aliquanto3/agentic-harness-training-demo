"""The RAG workshop (story 30, CAP-45): a RAG chain drawn and run apart from the RAG brick.

A chain (`Pipeline`) is an ordered list of stages (`Stage`: a kind, an option, its settings).
`LabRun` runs the chains of one question, lane after lane, with what it is given: the
models lent by the brick or loaded for the run (`Lent`), the brick's index, a stop test and
an emitter. It knows no session. Every figure the page shows is computed here (AD-1): ranks,
scores, sizes, durations, the context built. The workshop is a sandbox: it only reads the
brick's index and never changes the brick's state.
"""

from __future__ import annotations

import gc
import hashlib
import importlib.util
import json
import math
import os
import re
import shutil
import sys
import time
import unicodedata
from array import array
from collections.abc import Callable, Sequence
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import yaml
from pydantic import BaseModel, ConfigDict, Field, model_validator

from wavestack import config
from wavestack.messages import KeyedError, Lazy, Message, join, msg, number, render
from wavestack.models.embedding import Embedder
from wavestack.models.load_registry import LoadRegistry
from wavestack.models.reranker import RerankCancelled, Reranker
from wavestack.rag import index as rag_index
from wavestack.rag.corpus import Chunk, RagContent, chunk_corpus
from wavestack.rag.index import exception_text
from wavestack.rag.retriever import SqliteVecRetriever

# The kinds of stage, in the order a chain draws them.
KINDS = (
    "chunking",
    "embedding",
    "vector_store",
    "vector_search",
    "lexical_search",
    "fusion",
    "rerank",
    "context",
    "generation",
)
# Increment 4: the retrieval segment, between the vector store and the context, in any order
# (the chain's other stages are fixed); a stage of it is added before the context.
RETRIEVAL = ("vector_search", "lexical_search", "fusion", "rerank")
SEARCHES = ("vector_search", "lexical_search")
FIXED_HEAD = ("chunking", "embedding", "vector_store")
FIXED_TAIL = ("context", "generation")
BM25_K1, BM25_B = 1.5, 0.75
RRF_K = 60
_WORD = re.compile(r"\w+")
# Each kind's options, the shipped one first.
OPTIONS: dict[str, tuple[str, ...]] = {
    "chunking": ("paragraphs",),
    "embedding": ("declared", "fastembed"),
    "vector_store": ("sqlite_vec", "memory", "faiss", "lancedb"),
    "vector_search": ("cosine",),
    "lexical_search": ("bm25",),
    "fusion": ("rrf",),
    "rerank": ("declared",),
    "context": ("excerpts",),
    "generation": ("not_run",),
}
# The settings of an option, by name.
PARAMS: dict[tuple[str, str], tuple[str, ...]] = {
    ("chunking", "paragraphs"): ("chunk_max_chars",),
    ("vector_search", "cosine"): ("candidates",),
    ("lexical_search", "bm25"): ("candidates",),
    ("context", "excerpts"): ("top_k",),
}
BOUNDS: dict[str, tuple[int, int]] = {
    "chunk_max_chars": (200, 1500),
    "candidates": (1, 20),
    "top_k": (1, 20),
}
QUESTION_MAX = 500  # the characters of a question the workshop accepts
STATUSES = ("ok", "error", "skipped", "cancelled", "not_run")
LANES_MAX = 2  # a chain, or two compared: A then B
EMBED_BATCH = 8  # passages embedded at a time: « Arrêter » and the progress between batches
PROGRESS_INTERVAL_S = 0.1  # `rag_lab_stage_progress` at most ten times a second

_MIB = 1024**2


# ---------- the page's texts (content/rag_lab.yaml, AD-19) ----------


class _Strict(BaseModel):
    model_config = ConfigDict(extra="forbid")


class StageText(_Strict):
    label_text: str = Field(min_length=1)
    explain_text: str = Field(min_length=1)


class OptionText(_Strict):
    label_text: str = Field(min_length=1)


class ParamText(_Strict):
    label_text: str = Field(min_length=1)
    unit_text: str = ""


class StatusTexts(_Strict):
    waiting_text: str
    running_text: str
    ok_text: str
    error_text: str
    skipped_text: str
    cancelled_text: str
    not_run_text: str


class ColumnTexts(_Strict):
    rank_text: str
    before_text: str
    document_text: str
    score_text: str


class RagLabContent(_Strict):
    """`content/rag_lab.yaml`: every French text of the page, a text per kind of stage, per
    option and per setting."""

    title_text: str = Field(min_length=1)
    intro_text: str = Field(min_length=1)
    busy_text: str = Field(min_length=1)
    chain_title_text: str = Field(min_length=1)
    chain_help_text: str = Field(min_length=1)
    question_label_text: str = Field(min_length=1)
    question_placeholder_text: str = Field(min_length=1)
    default_question_text: str = Field(min_length=1, max_length=QUESTION_MAX)
    run_text: str = Field(min_length=1)
    stop_text: str = Field(min_length=1)
    running_text: str = Field(min_length=1)
    results_title_text: str = Field(min_length=1)
    results_empty_text: str = Field(min_length=1)
    generation_not_run_text: str = Field(min_length=1)
    borrowed_text: str = Field(min_length=1)
    loaded_text: str = Field(min_length=1)
    input_text: str = Field(min_length=1)
    output_text: str = Field(min_length=1)
    facts_text: str = Field(min_length=1)
    duration_text: str = Field(min_length=1)
    memory_text: str = Field(min_length=1)
    last_run_text: str = Field(min_length=1)
    compare_text: str = Field(min_length=1)
    add_text: str = Field(min_length=1)
    add_button_text: str = Field(min_length=1)
    move_before_text: str = Field(min_length=1)
    move_after_text: str = Field(min_length=1)
    remove_text: str = Field(min_length=1)
    reset_chain_text: str = Field(min_length=1)
    chain_a_text: str = Field(min_length=1)
    chain_b_text: str = Field(min_length=1)
    unavailable_text: str = Field(min_length=1)
    comparison_title_text: str = Field(min_length=1)
    common_text: str = Field(min_length=1)
    only_a_text: str = Field(min_length=1)
    only_b_text: str = Field(min_length=1)
    rank_changes_text: str = Field(min_length=1)
    status: StatusTexts
    columns: ColumnTexts
    stages: dict[str, StageText]
    options: dict[str, dict[str, OptionText]]
    params: dict[str, ParamText]

    @model_validator(mode="after")
    def _every_kind_option_and_setting(self) -> RagLabContent:
        """A text for each kind, option and setting the workshop offers, and no other."""
        if set(self.stages) != set(KINDS):
            raise ValueError(f"stages : il faut exactement {', '.join(KINDS)}")
        for kind, options in OPTIONS.items():
            if set(self.options.get(kind, {})) != set(options):
                raise ValueError(f"options.{kind} : il faut exactement {', '.join(options)}")
        if set(self.options) != set(OPTIONS):
            raise ValueError(f"options : il faut exactement {', '.join(OPTIONS)}")
        if set(self.params) != set(BOUNDS):
            raise ValueError(f"params : il faut exactement {', '.join(BOUNDS)}")
        return self


_CONTENT: dict[str, tuple[int, RagLabContent]] = {}  # the latest read, by path


def load_lab_content(lang: str = config.DEFAULT_LANGUAGE) -> RagLabContent:
    """Read `content/rag_lab.yaml` in `lang` (languages 4/5: the session's, never
    `settings.json`'s), again once the file changed: a corrected file shows on the page's
    reload. Raises on a missing or invalid file. Only the latest read of a file is kept."""
    path = config.content_file("rag_lab.yaml", lang)
    mtime = path.stat().st_mtime_ns
    kept = _CONTENT.get(str(path))
    if kept is not None and kept[0] == mtime:
        return kept[1]
    content = RagLabContent.model_validate(yaml.safe_load(path.read_text(encoding="utf-8")))
    _CONTENT[str(path)] = (mtime, content)
    return content


load_lab_content.cache_clear = _CONTENT.clear  # type: ignore[attr-defined]


# ---------- chains ----------


class Stage(_Strict):
    """One stage of a chain: its kind, the option chosen and its settings."""

    id: str = Field(pattern=r"^[a-z0-9_]{1,16}$")
    kind: str = Field(max_length=32)
    option: str = Field(max_length=32)
    params: dict[str, int] = {}


class Pipeline(_Strict):
    """A chain: its name (« A », « B ») and its stages, in order."""

    label_text: str = Field(default="A", min_length=1, max_length=40)
    stages: list[Stage] = Field(min_length=1, max_length=12)

    def find(self, kind: str) -> Stage | None:
        return next((s for s in self.stages if s.kind == kind), None)


def default_pipeline(cfg: config.Config) -> Pipeline:
    """The chain the RAG brick runs: its chunk size, its embedding model, the sqlite-vec
    index, its candidates, its reranker, its `top_k`, then the active model's generation."""
    stages = [
        ("chunking", "paragraphs", {"chunk_max_chars": cfg.rag_chunk_max_chars}),
        ("embedding", "declared", {}),
        ("vector_store", "sqlite_vec", {}),
        ("vector_search", "cosine", {"candidates": cfg.rag_rerank_candidates}),
        ("rerank", "declared", {}),
        ("context", "excerpts", {"top_k": cfg.rag_top_k}),
        ("generation", "not_run", {}),
    ]
    return Pipeline(
        label_text="A",
        stages=[
            Stage(id=f"s{i}", kind=kind, option=option, params=params)
            for i, (kind, option, params) in enumerate(stages, start=1)
        ],
    )


@dataclass
class OptionState:
    """What the page shows of an option: its name, whether it can be chosen (with why not),
    and a note on what a run would meet (a model missing, the brick's index stale)."""

    label_text: str
    available: bool = True
    reason_text: str | None = None
    note_text: str | None = None


@dataclass
class Catalog:
    """The kinds, options and settings the workshop offers now, and the shipped chain.
    `lang`: the session's language (languages 5/5), that of `content`, in which the
    refusals and the options' reasons (a `Message` rendered) are written."""

    content: RagLabContent
    default: Pipeline
    options: dict[tuple[str, str], OptionState]
    lang: str = config.DEFAULT_LANGUAGE

    def bounds(self, name: str) -> tuple[int, int]:
        """A setting's bounds; the shipped value always fits (a `[rag]` outside them)."""
        low, high = BOUNDS[name]
        for stage in self.default.stages:
            if name in stage.params:
                low, high = min(low, stage.params[name]), max(high, stage.params[name])
        return low, high

    def payload(self) -> dict[str, Any]:
        stages = []
        for kind in KINDS:
            text = self.content.stages[kind]
            options = []
            for option in OPTIONS[kind]:
                state = self.options.get((kind, option))
                if state is None:
                    continue
                params = []
                for name in PARAMS.get((kind, option), ()):
                    low, high = self.bounds(name)
                    params.append(
                        {
                            "name": name,
                            "label_text": self.content.params[name].label_text,
                            "unit_text": self.content.params[name].unit_text,
                            "min": low,
                            "max": high,
                            "default": param(Stage(id="x", kind=kind, option=option), name, self),
                        }
                    )
                options.append(
                    {
                        "id": option,
                        "label_text": state.label_text,
                        "available": state.available,
                        "reason_text": _rendered(state.reason_text, self.lang),
                        "note_text": _rendered(state.note_text, self.lang),
                        "params": params,
                    }
                )
            stages.append(
                {
                    "kind": kind,
                    "label_text": text.label_text,
                    "explain_text": text.explain_text,
                    "movable": kind in RETRIEVAL,
                    "options": options,
                }
            )
        return {"stages": stages, "insert_before": FIXED_TAIL[0]}

    def option_label(self, kind: str, option: str) -> str:
        state = self.options.get((kind, option))
        return state.label_text if state else option


def _bounds_fr(
    name: str, low: int, high: int, catalog: Catalog, lang: str = config.DEFAULT_LANGUAGE
) -> str:
    text = catalog.content.params[name]
    return _t(
        "check.bounds",
        lang,
        setting=text.label_text.lower(),
        low=lang_int(low, lang),
        high=lang_int(high, lang),
        unit=text.unit_text,
    ).strip()


def check_pipeline(
    pipeline: Pipeline, catalog: Catalog, *, lang: str | None = None
) -> tuple[str, str | None] | None:
    """Why the workshop refuses this chain, in `lang` (the catalog's by default), and the id
    of the stage at fault (`None` when no stage is), or `None` when it runs. The chunking,
    the embedding and the vector store open it, the context and the generation close it, in
    that order; between them, the searches, the fusion and the reranking in any order, each
    once, at least one search; two searches need a fusion after them, a fusion two searches
    before it, a reranking a search before it. Then each stage's option and settings."""
    lang = lang or catalog.lang
    names = {k: catalog.content.stages[k].label_text for k in catalog.content.stages}

    def text(key: str, /, **kw: Any) -> str:
        return _t(f"check.{key}", lang, **kw)

    stages = pipeline.stages
    ids = [s.id for s in stages]
    if len(set(ids)) != len(ids):
        return text("duplicate_id"), None
    for stage in stages:
        if stage.kind not in OPTIONS:
            return text("unknown_kind", kind=stage.kind), stage.id
    seen: set[str] = set()
    for stage in stages:
        if stage.kind in seen:
            return text("once", stage=names[stage.kind]), stage.id
        seen.add(stage.kind)
    kinds = [s.kind for s in stages]
    head, tail = list(FIXED_HEAD), list(FIXED_TAIL)
    order = " → ".join(names[k].lower() for k in (*FIXED_HEAD, *FIXED_TAIL) if k in names)
    for kind in (*head, *tail):
        if kind not in kinds:
            return text("fixed_missing", stage=names[kind], order=order), None
    if kinds[: len(head)] != head or kinds[-len(tail) :] != tail:
        wrong = next(
            s
            for i, s in enumerate(stages)
            if (s.kind in head and i != head.index(s.kind))
            or (s.kind in tail and i != len(stages) - len(tail) + tail.index(s.kind))
        )
        return text("fixed_place", stage=names[wrong.kind], order=order), wrong.id
    segment = stages[len(head) : -len(tail)]
    searches = [s for s in segment if s.kind in SEARCHES]
    if not searches:
        return text("no_search", stage=names["context"]), stages[-len(tail)].id
    position = {s.id: i for i, s in enumerate(segment)}
    fusion = next((s for s in segment if s.kind == "fusion"), None)
    if len(searches) == 2:
        second = searches[1]
        if fusion is None:
            return text("fusion_needed", stage=names[second.kind]), second.id
        if position[fusion.id] < position[second.id]:
            return text("fusion_before", stage=names["fusion"]), fusion.id
    elif fusion is not None:
        return text("fusion_alone", stage=names["fusion"]), fusion.id
    rerank = next((s for s in segment if s.kind == "rerank"), None)
    if rerank is not None and position[rerank.id] < position[searches[0].id]:
        return text("rerank_before", stage=names["rerank"]), rerank.id
    for stage in stages:
        label = names[stage.kind]
        state = catalog.options.get((stage.kind, stage.option))
        if state is None:
            return text("unknown_option", stage=label, option=stage.option), stage.id
        if not state.available:
            reason = _rendered(state.reason_text, lang)
            return (
                text("unavailable", stage=label, option=state.label_text, reason=reason),
                stage.id,
            )
        allowed = PARAMS.get((stage.kind, stage.option), ())
        unknown = set(stage.params) - set(allowed)
        if unknown:
            return text("unknown_setting", stage=label, names=", ".join(sorted(unknown))), stage.id
        for name in allowed:
            if name not in stage.params:
                continue
            low, high = catalog.bounds(name)
            if not low <= stage.params[name] <= high:
                bounds = _bounds_fr(name, low, high, catalog, lang)
                return text("out_of_bounds", stage=label, bounds=bounds), stage.id
    context = pipeline.find("context")
    top_k = param(context, "top_k", catalog) if context else 0
    for stage in searches:
        candidates = param(stage, "candidates", catalog)
        if candidates < top_k:
            return (
                text(
                    "too_few_candidates",
                    stage=names[stage.kind],
                    kept=count_text(candidates, "kept_candidate", lang),
                    extracts=count_text(top_k, "extract", lang),
                    candidates=count_text(top_k, "candidate", lang),
                ),
                stage.id,
            )
    return None


def validate_pipeline(
    pipeline: Pipeline, catalog: Catalog, *, lang: str | None = None
) -> str | None:
    """Why the workshop refuses this chain (in `lang`, the catalog's by default, naming the
    stage at fault), or `None`."""
    refusal = check_pipeline(pipeline, catalog, lang=lang)
    return refusal[0] if refusal else None


def param(stage: Stage, name: str, catalog: Catalog) -> int:
    """A setting of a stage: its value, else the shipped chain's."""
    if name in stage.params:
        return int(stage.params[name])
    shipped = catalog.default.find(stage.kind) or catalog.default.find(
        "vector_search" if name == "candidates" else stage.kind
    )
    if shipped is not None and name in shipped.params:
        return int(shipped.params[name])
    return BOUNDS[name][0]


# ---------- figures in French ----------


def fr_int(n: int) -> str:
    """« 1 536 »: French thousands separator (narrow no-break space)."""
    return f"{n:,}".replace(",", " ")


def count_fr(n: int, one: str, many: str | None = None) -> str:
    """« 1 extrait », « 29 extraits »: a count and its noun, agreed."""
    return f"{fr_int(n)} {one if n == 1 else (many or one + 's')}"


def fr_score(value: float | None) -> str:
    return "—" if value is None else f"{value:.3f}".replace(".", ",")


def fr_rank(n: int) -> str:
    return "1er" if n == 1 else f"{n}ᵉ"


def fr_ms(ms: int) -> str:
    return f"{fr_int(ms)} ms"


def _mo(n: int) -> str:
    return config.mo_fr(n)


def size_fr(n: int) -> str:
    """« 19 Ko », « 1,5 Mo »: a size small or large."""
    if n < _MIB:
        return f"{fr_int(max(1, round(n / 1024)))} Ko"
    return f"{n / _MIB:.1f} Mo".replace(".", ",")


# ---------- figures and texts in the session's language (languages 5/5) ----------
# French keeps the functions above, byte for byte; `messages.number` writes the others.


def _t(key: str, lang: str, /, **kw: Any) -> str:
    """`rag_lab.{key}` of `content/messages.yaml`, in `lang`."""
    return msg(f"rag_lab.{key}", lang, **kw)


def _french(lang: str) -> bool:
    return config.as_language(lang) == config.DEFAULT_LANGUAGE


def _rendered(value: Any, lang: str) -> Any:
    """A text given by the session (a `Message`, rendered in `lang`), `None` kept."""
    return None if value is None else render(value, lang)


def lang_int(n: int, lang: str) -> str:
    return fr_int(n) if _french(lang) else number(n, lang)


def agreed(key: str, n: int, lang: str) -> str:
    """A plural of `rag_lab`, agreed as the workshop always did: singular for 1 only."""
    return _t(key, lang, count=1 if n == 1 else 2)


def count_text(n: int, noun: str, lang: str) -> str:
    """`count_fr` in `lang`: « 3 extraits », « 3 excerpts » (`rag_lab.noun.{noun}`)."""
    return f"{lang_int(n, lang)} {agreed(f'noun.{noun}', n, lang)}"


def score_text(value: float | None, lang: str) -> str:
    if value is None or _french(lang):
        return fr_score(value)
    return number(value, lang, 3)


def rank_text(n: int, lang: str) -> str:
    """`fr_rank` in `lang`: « 1er », « 1st », « 1. »."""
    if n == 1:
        key = "first"
    elif n % 100 in (11, 12, 13):
        key = "th"
    else:
        key = {1: "st", 2: "nd", 3: "rd"}.get(n % 10, "th")
    return _t(f"rank.{key}", lang, n=n)


def ms_text(ms: int, lang: str) -> str:
    return f"{lang_int(ms, lang)} ms"


def mo_text(n: int, lang: str) -> str:
    """Bytes in Mo (MB), rounded, without the unit."""
    return _mo(n) if _french(lang) else number(round(n / _MIB), lang)


def size_text(n: int, lang: str) -> str:
    """`size_fr` in `lang`."""
    if n < _MIB:
        return _t("size.kib", lang, n=lang_int(max(1, round(n / 1024)), lang))
    value = f"{n / _MIB:.1f}".replace(".", ",") if _french(lang) else number(n / _MIB, lang, 1)
    return _t("size.mib", lang, n=value)


def quoted(text: str, lang: str) -> str:
    """« text », in `lang`'s quotation marks."""
    return _t("quoted", lang, text=text)


# ---------- the corpus's vectors, cached under `rag_lab_dir()` (AD-20) ----------

CHUNKS_FILE = "chunks.json"  # written last: its presence says the folder is whole
VECTORS_FILE = "vectors.f32"
INDEX_FILE = "index.sqlite"


_DIGESTS: dict[str, tuple[int, int, str]] = {}  # by path: its size, its mtime, its sha256


def file_digest(path: Path) -> str:
    """A file's sha256, computed again only when its size or modification time changed; the
    latest one per path is kept."""
    stat = path.stat()
    kept = _DIGESTS.get(str(path))
    if kept is None or kept[:2] != (stat.st_size, stat.st_mtime_ns):
        kept = (stat.st_size, stat.st_mtime_ns, rag_index.file_sha256(path))
        _DIGESTS[str(path)] = kept
    return kept[2]


def folder_identity(folder: Path) -> tuple[int, str]:
    """A folder's files (a fastembed model): their total size, and one sha256 over each
    file's path and sha256."""
    digest = hashlib.sha256()
    size = 0
    for path in sorted(p for p in folder.rglob("*") if p.is_file()):
        size += path.stat().st_size
        digest.update(f"{path.relative_to(folder).as_posix()}\x1f{file_digest(path)}\x1e".encode())
    return size, digest.hexdigest()


def cache_key(identity: dict[str, Any], chunk_max_chars: int, digest: str) -> str:
    """The folder of a corpus embedded by a model: the model's identity (id, dimensions, file
    size and sha256), the chunk size and the chunks' digest."""
    parts = {"embedder": identity, "chunk_max_chars": chunk_max_chars, "corpus": digest}
    return hashlib.sha256(json.dumps(parts, sort_keys=True).encode()).hexdigest()[:20]


def _replace(path: Path, data: bytes) -> None:
    """A file written whole or not at all: a temporary file, then `os.replace`."""
    tmp = path.with_name(path.name + ".tmp")
    try:
        tmp.write_bytes(data)
        os.replace(tmp, path)
    except BaseException:
        tmp.unlink(missing_ok=True)
        raise


def write_vectors(
    folder: Path, chunks: Sequence[Chunk], vectors: Sequence[Sequence[float]], identity: dict
) -> None:
    """The vectors (float32, `array('f')`), then the chunks and what identifies them."""
    folder.mkdir(parents=True, exist_ok=True)
    flat = array("f", (x for v in vectors for x in v))
    _replace(folder / VECTORS_FILE, flat.tobytes())
    meta = {
        "embedder": identity,
        "dims": len(vectors[0]) if vectors else 0,
        "count": len(vectors),
        "chunks": [list(c) for c in chunks],
    }
    _replace(folder / CHUNKS_FILE, json.dumps(meta, ensure_ascii=False).encode("utf-8"))


def read_vectors(folder: Path, chunks: Sequence[Chunk], dims: int) -> list[list[float]] | None:
    """The cached vectors of exactly these chunks, or `None` (absent, partial, another corpus)."""
    try:
        meta = json.loads((folder / CHUNKS_FILE).read_text(encoding="utf-8"))
        data = (folder / VECTORS_FILE).read_bytes()
    except (OSError, ValueError):
        return None
    if meta.get("dims") != dims or meta.get("count") != len(chunks):
        return None
    if [tuple(c) for c in meta.get("chunks", [])] != [tuple(c) for c in chunks]:
        return None
    if len(data) != 4 * dims * len(chunks):
        return None
    flat = array("f")
    flat.frombytes(data)
    return [list(flat[i * dims : (i + 1) * dims]) for i in range(len(chunks))]


TIE_DIGITS = 6  # two scores equal to this many decimals are a tie, whatever the float noise
TIE_MARGIN = 16  # the extra neighbours an index is asked for, to settle ties the same way


def top(found: Sequence[tuple[float, int]], k: int) -> list[tuple[int, float]]:
    """`(score, chunk_id)` pairs to the `k` best `(chunk_id, score)`: every store ranks alike,
    by score (a tie within the float noise of float32 arithmetic broken by chunk id), the
    score bounded to [0, 1] with 3 decimals."""
    found = [(s if math.isfinite(s) else 0.0, cid) for s, cid in found]  # NaN: no likeness
    ranked = sorted(found, key=lambda x: (-round(x[0], TIE_DIGITS), x[1]))[:k]
    return [(cid, round(min(1.0, max(0.0, s)), 3)) for s, cid in ranked]


def as_float32(vector: Sequence[float]) -> list[float]:
    """A vector as the stores keep it (float32), for every store to compare alike."""
    return list(array("f", vector))


class MemoryStore:
    """Exhaustive search in pure Python: the dot product of the normalized question with each
    normalized vector (its cosine), every vector read, no index."""

    def __init__(self, chunks: Sequence[Chunk], vectors: Sequence[Sequence[float]]) -> None:
        self._chunks = list(chunks)
        self._vectors = [as_float32(v) for v in vectors]

    def search(self, vector: Sequence[float], k: int) -> list[tuple[int, float]]:
        """`(chunk_id, score)` of the `k` nearest, the score bounded to [0, 1] with 3
        decimals; ties by chunk id, as sqlite-vec's query orders them."""
        query = as_float32(vector)
        scored = [
            (sum(a * b for a, b in zip(query, v, strict=True)), i + 1)
            for i, v in enumerate(self._vectors)
        ]
        return top(scored, k)

    def close(self) -> None:
        pass


# Increment 3: the vector stores of the `rag-alt` extra, their module and French name.
LIBRARIES = {"faiss": ("faiss", "FAISS"), "lancedb": ("lancedb", "LanceDB")}
INSTALL_FR = "uv sync --extra compression --extra rag-alt"


def _find_spec(name: str) -> Any:
    """`importlib.util.find_spec`, without importing the module (the end-to-end run replaces
    it to play a workstation without the extra)."""
    return importlib.util.find_spec(name)


def installed(name: str) -> bool:
    """Whether a module could be imported, read without importing it."""
    try:
        return _find_spec(name) is not None
    except (ImportError, ValueError):  # a module in `sys.modules` without its spec
        return name in sys.modules


def not_installed_fr(option: str) -> str:
    """Why FAISS or LanceDB cannot be chosen: the extra, and the command that installs it.
    A `Message` (French as a `str`), rendered in the catalog's language by `payload`."""
    return Message("rag_lab.not_installed", library=LIBRARIES[option][1], command=INSTALL_FR)


@dataclass
class Imported:
    """A library of the extra, imported once for the life of WaveStack: its module, and what
    its import added to WaveStack's memory (said by the stage)."""

    module: Any
    facts: list[tuple[str, str]]


def _as_matrix(numpy: Any, vectors: Sequence[Sequence[float]]) -> Any:
    return numpy.asarray(vectors, dtype=numpy.float32)


class FaissStore:
    """FAISS, exhaustive inner product (`IndexFlatIP`) on the normalized float32 vectors:
    their cosine. Built once in the key's folder (`write_index`, a temporary file, then
    `os.replace`), then read."""

    def __init__(self, faiss: Any, folder: Path, vectors: Sequence[Sequence[float]]) -> None:
        import numpy

        self._numpy = numpy
        path = folder / "faiss" / "index.faiss"
        dims = len(vectors[0])
        index = None
        if path.is_file():
            try:
                index = faiss.read_index(str(path))
            except Exception:  # noqa: BLE001 - rebuilt below
                index = None
            if index is not None and (index.ntotal != len(vectors) or index.d != dims):
                index = None
        self.built = index is None
        if index is None:
            index = faiss.IndexFlatIP(dims)
            index.add(_as_matrix(numpy, vectors))
            path.parent.mkdir(parents=True, exist_ok=True)
            tmp = path.with_name(path.name + ".tmp")
            try:
                faiss.write_index(index, str(tmp))
                os.replace(tmp, path)
            except BaseException:
                tmp.unlink(missing_ok=True)
                raise
        self._index = index
        self.path = path

    def search(self, vector: Sequence[float], k: int) -> list[tuple[int, float]]:
        wanted = min(self._index.ntotal, k + TIE_MARGIN)
        scores, ids = self._index.search(_as_matrix(self._numpy, [vector]), wanted)
        found = [(float(s), int(i) + 1) for s, i in zip(scores[0], ids[0], strict=True) if i >= 0]
        return top(found, k)

    def close(self) -> None:
        self._index = None


class LanceStore:
    """LanceDB, a table `chunks` (`id`, `vector`) searched with the cosine metric. Built once
    in a temporary folder of the key's folder, then moved into place; then read. A table of
    another size or dimension is let go (Windows keeps an open table's files) and deleted."""

    TABLE = "chunks"

    def __init__(self, lancedb: Any, folder: Path, vectors: Sequence[Sequence[float]]) -> None:
        path = folder / "lancedb"
        dims = len(vectors[0])
        table = None
        if path.is_dir():
            try:
                table = lancedb.connect(str(path)).open_table(self.TABLE)
                first = table.head(1).to_pylist()
                if table.count_rows() != len(vectors) or len(first[0]["vector"]) != dims:
                    table = None
            except Exception:  # noqa: BLE001 - rebuilt below
                table = None
            gc.collect()  # a stale table's handles let go before its files are deleted
        self.built = table is None
        if table is None:
            tmp = folder / "lancedb.tmp"
            _delete(tmp)
            try:
                rows = [
                    {"id": i + 1, "vector": [float(x) for x in v]} for i, v in enumerate(vectors)
                ]
                lancedb.connect(str(tmp)).create_table(self.TABLE, data=rows, mode="overwrite")
                gc.collect()
                _delete(path)
                os.replace(tmp, path)
            except BaseException:
                shutil.rmtree(tmp, ignore_errors=True)
                raise
            table = lancedb.connect(str(path)).open_table(self.TABLE)
        self._table = table
        self.path = path

    def search(self, vector: Sequence[float], k: int) -> list[tuple[int, float]]:
        query = self._table.search(list(vector), vector_column_name="vector")
        rows = query.distance_type("cosine").limit(k + TIE_MARGIN).to_list()
        found = [(1.0 - float(r["_distance"]), int(r["id"])) for r in rows]
        return top(found, k)

    def close(self) -> None:
        self._table = None


def _delete(folder: Path) -> None:
    """A folder of the workshop removed, or a `StageFailed` saying why it cannot be."""
    if not folder.exists():
        return
    try:
        shutil.rmtree(folder)
    except OSError as exc:
        raise StageFailed(
            Message("rag_lab.folder_held", folder=folder, error=type(exc).__name__, cause=str(exc))
        ) from exc


class _SqliteStore:
    """A sqlite-vec index (the brick's, read only, or the workshop's), searched through the
    `Retriever` port."""

    def __init__(self, path: Path, embedder: Embedder) -> None:
        self._retriever = SqliteVecRetriever(path, embedder, 1)

    def search(self, vector: Sequence[float], k: int) -> list[tuple[int, float]]:
        found = self._retriever.nearest(list(vector), k + TIE_MARGIN)
        return top([(1.0 - distance, chunk_id) for chunk_id, distance in found], k)

    def close(self) -> None:
        self._retriever.close()


# ---------- a run ----------


def _keyed(text: str) -> Message:
    """A text given to a stage's exception: a `Message` kept, any other text as it is."""
    return text if isinstance(text, Message) else Message("common.verbatim", text=text)


class StageFailed(KeyedError):
    """A stage cannot do its work: its reason, a `Message` (French as `str()` and
    `message_text`, `render(lang)` in the session's) or a text kept as it is. `soft`: the
    chain goes on (the reranking), else the next stages are skipped."""

    def __init__(self, message_text: str, *, soft: bool = False) -> None:
        super().__init__(_keyed(message_text))
        self.message_text: str = self.message
        self.soft = soft


class StageSkipped(KeyedError):
    """A stage that does not run (the reranker is not on the workstation): why, as
    `StageFailed` says it."""

    def __init__(self, reason_text: str) -> None:
        super().__init__(_keyed(reason_text))
        self.reason_text: str = self.message


class LabCancelled(Exception):
    """« Arrêter », seen between two stages, two passages or two candidates."""


@dataclass
class Lent:
    """A model for the run: borrowed from the RAG brick (never closed by the run), or loaded
    for it (closed at its end by whoever lent it)."""

    model: Any
    borrowed: bool
    label_text: str


class Loans:
    """The models a run loads itself (AD-8): the budget checked first (a refusal in figures,
    nothing loaded), then the load and its grant; `close()` closes each and frees its slot. A
    model the brick holds is borrowed: neither checked, granted nor closed. A model the run
    already loaded (lane A's, for lane B) is lent again: one load, one grant, per slot and
    model."""

    def __init__(self, registry: LoadRegistry) -> None:
        self._registry = registry
        self._opened: list[tuple[Any, str]] = []
        self._by_key: dict[tuple[str, str], Any] = {}

    def lend(
        self,
        *,
        borrowed: Any,
        label_text: str,
        noun_text: str,
        unavailable_text: str | None,
        cost: int,
        slot: str,
        open_model: Callable[[], Any],
        soft: bool = False,
    ) -> Lent:
        """`borrowed`: the brick's model, else `None`; `unavailable_text`: why it cannot load
        (a missing file). `soft`: its failure lets the chain go on (the reranker), and a
        missing file only skips the stage."""
        if borrowed is not None:
            return Lent(borrowed, True, label_text)
        if unavailable_text is not None:
            if soft:
                raise StageSkipped(unavailable_text)
            raise StageFailed(unavailable_text)
        if (slot, label_text) in self._by_key:
            return Lent(self._by_key[(slot, label_text)], False, label_text)
        named = Lazy(lambda lang: f"{render(noun_text, lang)} {label_text}")
        refusal = self._registry.check_component(named, cost, slot)
        if refusal is not None:
            raise StageFailed(refusal, soft=soft)
        try:
            model = open_model()
        except Exception as exc:  # noqa: BLE001 - said in the stage, never a crash
            raise StageFailed(
                Message(
                    "rag_lab.load_failed",
                    noun=noun_text,
                    model=label_text,
                    error=type(exc).__name__,
                    cause=str(exc),
                ),
                soft=soft,
            ) from exc
        self._registry.grant(label_text, cost, slot)
        self._opened.append((model, slot))
        self._by_key[(slot, label_text)] = model
        return Lent(model, False, label_text)

    def close(self) -> list[str]:
        """Close what the run loaded, free its slots; the errors met, in French."""
        errors = []
        self._by_key.clear()
        while self._opened:
            model, slot = self._opened.pop()
            try:
                model.close()
            except Exception as exc:  # noqa: BLE001 - it is forgotten all the same
                errors.append(f"{type(exc).__name__} : {exc}")
            self._registry.release(slot)
        return errors


@dataclass
class LabDeps:
    """What a run is given: nothing else of the session reaches it."""

    content: RagContent  # the brick's texts: its corpus and its excerpts' format
    texts: RagLabContent
    catalog: Catalog
    shipped_chunk_max_chars: int
    brick_index: Path
    # Why the brick's index cannot serve (absent, stale, of another model), or `None`.
    brick_index_error: str | None
    lab_dir: Path  # `config.rag_lab_dir()`: the workshop's vectors and indexes
    embedder: Callable[[str], Lent]  # option -> the embedding model, or `StageFailed`
    # option -> what identifies the embedding model (id, dims, size, sha256): its cache's key
    identity: Callable[[str], dict[str, Any]]
    # option (`faiss`, `lancedb`) -> the library, imported once, or `StageFailed`
    importer: Callable[[str], Imported]
    reranker: Callable[[str], Lent]  # option -> the reranker, or `StageSkipped`/`StageFailed`
    cancelled: Callable[[], bool]
    # kind, payload, step id and component of the event
    emit: Callable[[str, dict[str, Any], str, str], None]
    rss: Callable[[], int | None]
    # Languages (4/5): the session's, the corpus's (`content` is `rag.yaml` read in it)
    lang: str = config.DEFAULT_LANGUAGE


@dataclass
class Item:
    """An excerpt in a ranked list: its rank (from 1), where it was before, its score."""

    chunk_id: int
    doc_id: str
    title_text: str
    text: str
    score: float | None
    rank: int = 0
    before: int | None = None
    sources: list[dict[str, Any]] = field(default_factory=list)

    def payload(self) -> dict[str, Any]:
        return {
            "rank": self.rank,
            "before": self.before,
            "chunk_id": self.chunk_id,
            "doc_id": self.doc_id,
            "title_text": self.title_text,
            "text": self.text,
            "score": self.score,
            "sources": self.sources,
        }


@dataclass
class _Result:
    input_text: str = ""
    output_text: str = ""
    facts: list[tuple[str, str]] = field(default_factory=list)
    items: list[Item] = field(default_factory=list)
    borrowed: bool = False


@dataclass
class _Lane:
    """What the stages of one lane hand each other."""

    lane: str
    pipeline: Pipeline
    chunk_max_chars: int = 0
    chunks: list[Chunk] = field(default_factory=list)
    embedder: Embedder | None = None
    embedder_label: str = ""
    query_vector: list[float] | None = None
    vectors: list[list[float]] | None = None  # the passages', when the store needs them
    key: str = ""  # the cache's folder of this corpus and model
    store: Any = None  # `MemoryStore`, `_SqliteStore`…
    lists: list[list[Item]] = field(default_factory=list)  # each search's, until fused
    list_kinds: list[str] = field(default_factory=list)  # the stage that made each list
    context: list[Item] = field(default_factory=list)
    context_text: str = ""
    status: str = "ok"

    @property
    def ranked(self) -> list[Item] | None:
        """The list the next stage works on: the last one made."""
        return self.lists[-1] if self.lists else None


class LabRun:
    """One run of the workshop: the chains of `pipelines`, one lane each (« a », « b »), in
    order, on the same question. `run()` emits `rag_lab_run_started`, a
    `rag_lab_stage_started` / `rag_lab_stage_ended` pair per stage run (only the latter for a
    stage skipped or not run), and `rag_lab_run_ended`; it never raises."""

    def __init__(
        self, run_id: str, question: str, pipelines: Sequence[Pipeline], deps: LabDeps
    ) -> None:
        self.run_id = run_id
        self.question = question
        self.pipelines = list(pipelines)
        self.deps = deps
        self.lanes: list[_Lane] = []
        self.ended = False  # `rag_lab_run_ended` emitted

    # -- events --

    def _emit(self, kind: str, payload: dict[str, Any], step_id: str, component: str) -> None:
        self.deps.emit(kind, {"run_id": self.run_id, **payload}, step_id, component)

    def _step(self, lane: str, index: int) -> str:
        return f"{self.run_id}.{lane}.s{index}"

    def _label(self, stage: Stage) -> str:
        return self.deps.texts.stages[stage.kind].label_text

    # -- texts, in the session's language (languages 5/5) --

    @property
    def _lang(self) -> str:
        return self.deps.lang

    def _text(self, key: str, /, **kw: Any) -> str:
        return _t(key, self._lang, **kw)

    def _int(self, n: int) -> str:
        return lang_int(n, self._lang)

    def _count(self, n: int, noun: str) -> str:
        return count_text(n, noun, self._lang)

    def _quoted(self, text: str) -> str:
        return quoted(text, self._lang)

    # -- the run --

    def run(self) -> str:
        started = time.monotonic()
        texts = self.deps.texts
        lanes = []
        for pipeline, lane in zip(self.pipelines, "ab", strict=False):
            lanes.append(
                {
                    "lane": lane,
                    "label_text": pipeline.label_text,
                    "stages": [
                        {
                            "stage_id": s.id,
                            "kind": s.kind,
                            "option": s.option,
                            "label_text": self._label(s),
                            "option_label_text": self.deps.catalog.option_label(s.kind, s.option),
                            "params": s.params,
                        }
                        for s in pipeline.stages
                    ],
                }
            )
        self._emit(
            "rag_lab_run_started",
            {
                "question": self.question,
                "lanes": lanes,
                "phase_label": self._text(
                    "run.phase", running=texts.running_text, question=self.question[:80]
                ),
            },
            self.run_id,
            "rag_lab",
        )
        status, comparison = "error", None
        try:
            cancelled = False
            for pipeline, lane in zip(self.pipelines, "ab", strict=False):
                state = _Lane(lane, pipeline)
                self.lanes.append(state)
                try:
                    self._run_lane(state, skip_all=cancelled)
                finally:
                    if state.store is not None:
                        try:
                            state.store.close()
                        except Exception:  # noqa: BLE001 - a store closed badly is forgotten
                            pass
                cancelled = cancelled or state.status == "cancelled"
            statuses = {lane.status for lane in self.lanes}
            status = "ok"
            if "cancelled" in statuses or "error" in statuses:
                status = "cancelled" if "cancelled" in statuses else "error"
            if len(self.lanes) == LANES_MAX and status != "cancelled":
                comparison = compare(self.lanes[0], self.lanes[1], self._lang)
        except Exception:  # noqa: BLE001 - the run ends in error, `run_ended` all the same
            status, comparison = "error", None
        finally:
            self.end(status, _ms(time.monotonic() - started), comparison)
        return status

    def end(self, status: str, duration_ms: int, comparison: dict[str, Any] | None = None) -> None:
        """`rag_lab_run_ended`, once: the page never stays « en cours »."""
        if self.ended:
            return
        self.ended = True
        self._emit(
            "rag_lab_run_ended",
            {"status": status, "duration_ms": duration_ms, "comparison": comparison},
            self.run_id,
            "rag_lab",
        )

    def _run_lane(self, lane: _Lane, skip_all: bool) -> None:
        stopped = skip_all  # an earlier stage failed or was stopped: the rest is skipped
        if skip_all:
            lane.status = "cancelled"
        for index, stage in enumerate(lane.pipeline.stages, start=1):
            step_id = self._step(lane.lane, index)
            component = f"rag_lab.{stage.kind}"
            base = {"lane": lane.lane, "stage_id": stage.id, "kind": stage.kind}
            base["option"] = stage.option
            if stopped:
                self._ended(step_id, component, base, "skipped", _Result(), None, 0, None)
                continue
            if stage.kind == "generation":
                result = self._generation(lane)
                self._ended(step_id, component, base, "not_run", result, None, 0, None)
                continue
            if self.deps.cancelled():
                self._ended(step_id, component, base, "cancelled", _Result(), None, 0, None)
                lane.status, stopped = "cancelled", True
                continue
            self._emit(
                "rag_lab_stage_started",
                base | {"phase_label": self._text("stage.running", stage=self._label(stage))},
                step_id,
                component,
            )
            rss_before = self.deps.rss()
            started = time.monotonic()
            status, error_text, result = "ok", None, _Result()
            try:
                result = self._run_stage(lane, stage, step_id, component, base)
            except LabCancelled:
                status, error_text = "cancelled", self._text("stage.stopped")
                lane.status, stopped = "cancelled", True
            except StageSkipped as skipped:
                status, error_text = "skipped", skipped.render(self._lang)
                result = self._passed_on(lane, error_text)
            except StageFailed as failed:
                status, error_text = "error", failed.render(self._lang)
                if failed.soft:
                    result = self._passed_on(lane, error_text)
                else:
                    lane.status, stopped = "error", True
            except Exception as exc:  # noqa: BLE001 - AD-16: a stage's failure, never a crash
                status = "error"
                error_text = self._text(
                    "stage.failed",
                    error=type(exc).__name__,
                    cause=exception_text(exc, self._lang),
                )
                lane.status, stopped = "error", True
            duration = _ms(time.monotonic() - started)
            self._ended(step_id, component, base, status, result, error_text, duration, rss_before)

    def _ended(
        self,
        step_id: str,
        component: str,
        base: dict[str, Any],
        status: str,
        result: _Result,
        error_text: str | None,
        duration_ms: int,
        rss_before: int | None,
    ) -> None:
        rss = self.deps.rss() if status in ("ok", "error", "cancelled") or rss_before else None
        memory_text = None
        if rss is not None:
            memory_text = self._text("stage.memory", mo=mo_text(rss, self._lang))
            if rss_before is not None:
                delta = rss - rss_before
                sign = "+" if delta >= 0 else "−"
                memory_text = self._text(
                    "stage.memory_during",
                    memory=memory_text,
                    sign=sign,
                    mo=mo_text(abs(delta), self._lang),
                )
        self._emit(
            "rag_lab_stage_ended",
            base
            | {
                "status": status,
                "input_text": result.input_text,
                "output_text": result.output_text,
                "facts": [
                    {"label_text": render(k, self._lang), "value_text": render(v, self._lang)}
                    for k, v in result.facts
                ],
                "items": [i.payload() for i in result.items],
                "borrowed": result.borrowed,
                "error_text": error_text,
                "duration_ms": duration_ms,
                "rss_bytes": rss,
                "memory_text": memory_text,
            },
            step_id,
            component,
        )

    def _progress(self, step_id: str, component: str, base: dict[str, Any]):  # noqa: ANN202
        """A progress callback: at most ten events a second, the last one always."""
        last = 0.0

        def progress(done: int, total: int) -> None:
            nonlocal last
            now = time.monotonic()
            if done < total and now - last < PROGRESS_INTERVAL_S:
                return
            last = now
            self._emit(
                "rag_lab_stage_progress", base | {"done": done, "total": total}, step_id, component
            )

        return progress

    def _check(self) -> None:
        if self.deps.cancelled():
            raise LabCancelled()

    def _run_stage(
        self, lane: _Lane, stage: Stage, step_id: str, component: str, base: dict[str, Any]
    ) -> _Result:
        progress = self._progress(step_id, component, base)
        if stage.kind == "chunking":
            return self._chunking(lane, stage)
        if stage.kind == "embedding":
            return self._embedding(lane, stage, progress)
        if stage.kind == "vector_store":
            return self._vector_store(lane, stage)
        if stage.kind == "vector_search":
            return self._vector_search(lane, stage)
        if stage.kind == "lexical_search":
            return self._lexical_search(lane, stage)
        if stage.kind == "fusion":
            return self._fusion(lane, stage)
        if stage.kind == "rerank":
            return self._rerank(lane, stage, progress)
        if stage.kind == "context":
            return self._context(lane, stage)
        raise StageFailed(Message("rag_lab.stage.unknown", kind=stage.kind))

    def _passed_on(self, lane: _Lane, reason_text: str) -> _Result:
        """A reranking skipped or failed: the search's order goes on unchanged."""
        n = len(lane.ranked or [])
        return _Result(
            input_text=self._text("passed_on.input", candidates=self._count(n, "candidate")),
            output_text=self._text("passed_on.output", reason=reason_text),
        )

    # -- the stages --

    def _uses_brick_index(self, lane: _Lane) -> bool:
        """The brick's own configuration (its embedding model, its chunk size, sqlite-vec):
        its index serves, read only."""
        store = lane.pipeline.find("vector_store")
        embedding = lane.pipeline.find("embedding")
        return (
            store is not None
            and store.option == "sqlite_vec"
            and embedding is not None
            and embedding.option == "declared"
            and lane.chunk_max_chars == self.deps.shipped_chunk_max_chars
        )

    def _chunking(self, lane: _Lane, stage: Stage) -> _Result:
        size = param(stage, "chunk_max_chars", self.deps.catalog)
        lane.chunk_max_chars = size
        source = self._text("chunking.source_corpus")
        chunks: list[Chunk] = []
        if self._uses_brick_index(lane) and self.deps.brick_index_error is None:
            # Its ids are the index's: never the corpus's chunks under the brick's vectors.
            try:
                chunks = rag_index.read_chunks(self.deps.brick_index)
            except Exception as exc:  # noqa: BLE001 - said in the stage
                raise StageFailed(
                    Message(
                        "rag_lab.chunking.index_unreadable",
                        error=type(exc).__name__,
                        cause=exception_text(exc, self._lang),
                    )
                ) from exc
            source = self._text("chunking.source_index")
        if not chunks:
            chunks = chunk_corpus(self.deps.content, size, self.deps.lang)
        if not chunks:
            raise StageFailed(Message("rag_lab.chunking.no_chunks"))
        lane.chunks = chunks
        docs = len({c.doc_id for c in chunks})
        longest = max(len(c.text) for c in chunks)
        mean = round(sum(len(c.text) for c in chunks) / len(chunks))
        text, count = self._text, self._int

        def chars(n: int) -> str:
            return text("chunking.characters", n=count(n))

        return _Result(
            input_text=text(
                "chunking.input",
                documents=self._count(docs, "document"),
                declared=count(len(self.deps.content.documents)),
            ),
            output_text=text(
                "chunking.output",
                extracts=self._count(len(chunks), "extract"),
                size=count(size),
                source=source,
            ),
            facts=[
                (text("chunking.max_size"), chars(size)),
                (text("chunking.extracts"), count(len(chunks))),
                (text("chunking.mean"), chars(mean)),
                (text("chunking.longest"), chars(longest)),
            ],
        )

    def _embedding(
        self, lane: _Lane, stage: Stage, progress: Callable[[int, int], None]
    ) -> _Result:
        lent = self.deps.embedder(stage.option)
        embedder: Embedder = lent.model
        lane.embedder_label = lent.label_text
        self._check()
        text = self._text
        n = self._int(len(lane.chunks))
        passages_n = self._count(len(lane.chunks), "passage")
        vectors_n = self._count(len(lane.chunks), "vector")
        facts = [
            (text("fact.model"), lent.label_text),
            (text("fact.dimensions"), self._int(embedder.dims)),
        ]
        if self._uses_brick_index(lane):
            if self.deps.brick_index_error is None:
                passages = text("embedding.brick_passages", passages=passages_n)
            else:
                passages = text("embedding.brick_unusable")
        else:
            identity = self.deps.identity(stage.option)
            digest = rag_index.corpus_digest(lane.chunks)
            lane.key = cache_key(identity, lane.chunk_max_chars, digest)
            folder = self.deps.lab_dir / lane.key
            vectors = read_vectors(folder, lane.chunks, embedder.dims)
            if vectors is not None:
                passages = text("embedding.cached", vectors=vectors_n, key=lane.key)
                facts.append((text("fact.passages"), text("embedding.cached_fact", n=n)))
            else:
                vectors = []
                total = len(lane.chunks)
                started = time.monotonic()
                for at in range(0, total, EMBED_BATCH):
                    self._check()
                    batch = lane.chunks[at : at + EMBED_BATCH]
                    vectors += embedder.embed_passages([rag_index.passage_text(c) for c in batch])
                    progress(min(at + EMBED_BATCH, total), total)
                if len(vectors) != total or any(len(v) != embedder.dims for v in vectors):
                    raise StageFailed(Message("rag_lab.embedding.wrong_dims", dims=embedder.dims))
                write_vectors(folder, lane.chunks, vectors, identity)
                seconds = time.monotonic() - started
                passages = text(
                    "embedding.computed",
                    passages=passages_n,
                    duration=ms_text(_ms(seconds), self._lang),
                    key=lane.key,
                )
                facts.append(
                    (text("fact.passages"), text("embedding.computed_fact", passages=passages_n))
                )
            lane.vectors = vectors
        vector = embedder.embed_queries([self.question])[0]
        if not any(vector):
            raise StageFailed(Message("rag_lab.embedding.null_vector"))
        lane.embedder = embedder
        lane.query_vector = vector
        separator = text("list_separator")
        shown = separator.join(score_text(v, self._lang) for v in vector[:4])
        facts.append((text("fact.provenance"), self._provenance(lent)))
        return _Result(
            input_text=text(
                "embedding.input",
                question=self.question,
                extracts=self._count(len(lane.chunks), "extract"),
            ),
            output_text=text(
                "embedding.output", n=self._int(len(vector)), shown=shown, passages=passages
            ),
            facts=facts,
            borrowed=lent.borrowed,
        )

    def _provenance(self, lent: Lent) -> str:
        return self.deps.texts.borrowed_text if lent.borrowed else self.deps.texts.loaded_text

    def _vector_store(self, lane: _Lane, stage: Stage) -> _Result:
        if lane.embedder is None:
            raise StageFailed(Message("rag_lab.vector_store.no_embedder"))
        n = len(lane.chunks)
        dims = lane.embedder.dims
        text, count = self._text, self._int
        vectors_fact, metric_fact = text("fact.vectors"), text("fact.metric")
        if self._uses_brick_index(lane):
            if self.deps.brick_index_error is not None:
                raise StageFailed(self.deps.brick_index_error)
            path = self.deps.brick_index
            meta = rag_index.read_meta(path)
            lane.store = _SqliteStore(path, lane.embedder)
            return _Result(
                input_text=text(
                    "vector_store.brick_input",
                    vectors=self._count(meta.chunks, "vector"),
                    dims=count(meta.dims),
                    model=meta.embedding_model_id,
                    date=meta.built_at[:10],
                ),
                output_text=text("vector_store.brick_output", file=path.name),
                facts=[
                    (text("fact.file"), str(path)),
                    (vectors_fact, count(meta.chunks)),
                    (metric_fact, text("vector_store.cosine")),
                ],
            )
        if lane.vectors is None:
            raise StageFailed(Message("rag_lab.vector_store.no_vectors"))
        vectors_text = text(
            "vector_store.vectors", vectors=self._count(n, "vector"), dims=count(dims)
        )
        input_text = text("vector_store.input", vectors=vectors_text)
        if stage.option == "memory":
            lane.store = MemoryStore(lane.chunks, lane.vectors)
            size = n * dims * 4
            return _Result(
                input_text=input_text,
                output_text=text("vector_store.memory_output", size=size_text(size, self._lang)),
                facts=[(vectors_fact, count(n)), (metric_fact, text("vector_store.cosine_dot"))],
            )
        if stage.option == "sqlite_vec":
            path = self.deps.lab_dir / lane.key / INDEX_FILE
            built = text("vector_store.reread")
            try:
                meta = rag_index.read_meta(path) if path.is_file() else None
            except Exception:  # noqa: BLE001 - rebuilt below
                meta = None
            fits = (
                meta is not None
                and meta.chunks == n
                and meta.dims == dims
                and meta.chunk_max_chars == lane.chunk_max_chars
                and meta.corpus_sha256 == rag_index.corpus_digest(lane.chunks)
            )
            if not fits:
                self._check()
                rag_index.write_index(
                    path,
                    lane.chunks,
                    lane.vectors,
                    model_id=lane.embedder.model_id,
                    dims=dims,
                    chunk_max_chars=lane.chunk_max_chars,
                )
                built = text("vector_store.built", vectors=self._count(n, "vector"))
            lane.store = _SqliteStore(path, lane.embedder)
            return _Result(
                input_text=input_text,
                output_text=text("vector_store.sqlite_output", state=built, key=lane.key),
                facts=[
                    (text("fact.file"), str(path)),
                    (vectors_fact, count(n)),
                    (metric_fact, text("vector_store.cosine")),
                ],
            )
        if stage.option in LIBRARIES:
            label = LIBRARIES[stage.option][1]
            imported = self.deps.importer(stage.option)
            self._check()
            folder = self.deps.lab_dir / lane.key
            if stage.option == "faiss":
                store: Any = FaissStore(imported.module, folder, lane.vectors)
                kind = text("vector_store.faiss_kind")
            else:
                store = LanceStore(imported.module, folder, lane.vectors)
                kind = text("vector_store.lancedb_kind")
            lane.store = store
            vectors_n = self._count(n, "vector")
            state = text(
                "vector_store.built" if store.built else "vector_store.reread_count",
                vectors=vectors_n,
            )
            return _Result(
                input_text=input_text,
                output_text=text(
                    "vector_store.library_output",
                    library=label,
                    state=state,
                    kind=kind,
                    key=lane.key,
                ),
                facts=[
                    (text("fact.folder"), str(store.path)),
                    (vectors_fact, count(n)),
                    *imported.facts,
                ],
            )
        raise StageFailed(Message("rag_lab.vector_store.unknown", option=stage.option))

    def _vector_search(self, lane: _Lane, stage: Stage) -> _Result:
        if lane.store is None or lane.query_vector is None:
            raise StageFailed(Message("rag_lab.vector_search.no_store"))
        k = param(stage, "candidates", self.deps.catalog)
        hits = lane.store.search(lane.query_vector, k)
        items = []
        for rank, (chunk_id, score) in enumerate(hits, start=1):
            chunk = lane.chunks[chunk_id - 1]
            items.append(
                Item(chunk_id, chunk.doc_id, chunk.title_text, chunk.text, score, rank=rank)
            )
        lane.lists.append(items)
        lane.list_kinds.append("vector_search")
        best = items[0].score if items else None
        worst = items[-1].score if items else None
        text = self._text
        return _Result(
            input_text=text("vector_search.input", vectors=self._count(len(lane.chunks), "vector")),
            output_text=text(
                "vector_search.output",
                extracts=self._count(len(items), "extract"),
                best=score_text(best, self._lang),
                worst=score_text(worst, self._lang),
            ),
            facts=[
                (text("fact.requested"), self._int(k)),
                (text("fact.found"), self._int(len(items))),
            ],
            items=items,
        )

    def _rerank(self, lane: _Lane, stage: Stage, progress: Callable[[int, int], None]) -> _Result:
        candidates = lane.ranked
        if not candidates:
            raise StageSkipped(Message("rag_lab.rerank.no_candidates"))
        lent = self.deps.reranker(stage.option)
        reranker: Reranker = lent.model
        passages = [f"{c.title_text}\n{c.text}" for c in candidates]
        try:
            raw = reranker.score(self.question, passages, self.deps.cancelled, progress)
        except RerankCancelled:
            raise LabCancelled() from None
        except Exception as exc:  # noqa: BLE001 - the chain goes on with the search's order
            raise StageFailed(
                Message(
                    "rag_lab.rerank.failed",
                    error=type(exc).__name__,
                    cause=exception_text(exc, self._lang),
                ),
                soft=True,
            ) from exc
        if len(raw) != len(candidates):
            scores_n, candidates_n = len(raw), len(candidates)
            raise StageFailed(
                Message(
                    "rag_lab.rerank.mismatch",
                    scores=Lazy(lambda lang: count_text(scores_n, "score", lang)),
                    candidates=Lazy(lambda lang: count_text(candidates_n, "candidate", lang)),
                ),
                soft=True,
            )
        scores = []
        for item in raw:
            try:
                value = float(item.score)
            except (TypeError, ValueError):
                raise StageFailed(Message("rag_lab.rerank.not_a_number"), soft=True) from None
            scores.append(round(min(1.0, max(0.0, value)), 3))
        # Stable, as the brick's: the reranker's score, then the search's rank.
        order = sorted(range(len(candidates)), key=lambda i: (-scores[i], candidates[i].rank))
        items = []
        for rank, i in enumerate(order, start=1):
            c = candidates[i]
            items.append(
                Item(
                    c.chunk_id,
                    c.doc_id,
                    c.title_text,
                    c.text,
                    scores[i],
                    rank=rank,
                    before=c.rank,
                    sources=c.sources
                    or [
                        {
                            "kind": self._made_by(lane),
                            "label_text": self.deps.texts.stages[self._made_by(lane)].label_text,
                            "rank": c.rank,
                            "score": c.score,
                        }
                    ],
                )
            )
        lane.lists[-1] = items
        moved = max(items, key=lambda x: (x.before or 0) - x.rank)
        text = self._text
        climb = (
            text(
                "rerank.climb",
                title=moved.title_text,
                before=rank_text(moved.before or 0, self._lang),
                after=rank_text(moved.rank, self._lang),
            )
            if (moved.before or 0) > moved.rank
            else text("rerank.unchanged")
        )
        return _Result(
            input_text=text("rerank.input", candidates=self._count(len(candidates), "candidate")),
            output_text=text(
                "rerank.output",
                candidates=self._count(len(items), "reordered_candidate"),
                climb=climb,
            ),
            facts=[
                (text("fact.model"), lent.label_text),
                (text("fact.pairs"), self._int(len(candidates))),
                (text("fact.provenance"), self._provenance(lent)),
            ],
            items=items,
            borrowed=lent.borrowed,
        )

    def _made_by(self, lane: _Lane) -> str:
        """The kind of the stage that made the lane's current list (a search or the fusion)."""
        return lane.list_kinds[-1] if lane.list_kinds else "vector_search"

    def _lexical_search(self, lane: _Lane, stage: Stage) -> _Result:
        if not lane.chunks:
            raise StageFailed(Message("rag_lab.lexical_search.no_chunks"))
        k = param(stage, "candidates", self.deps.catalog)
        passages = [rag_index.passage_text(c) for c in lane.chunks]
        scored = bm25(self.question, passages, self.deps.lang)
        found = sorted(
            ((score, i + 1) for i, score in enumerate(scored) if score > 0),
            key=lambda x: (-round(x[0], TIE_DIGITS), x[1]),
        )[:k]
        items = []
        for rank, (score, chunk_id) in enumerate(found, start=1):
            chunk = lane.chunks[chunk_id - 1]
            items.append(
                Item(
                    chunk_id, chunk.doc_id, chunk.title_text, chunk.text, round(score, 3), rank=rank
                )
            )
        lane.lists.append(items)
        lane.list_kinds.append("lexical_search")
        text = self._text
        terms = bm25_terms(self.question, self.deps.lang)
        words = ", ".join(self._quoted(w) for w in dict.fromkeys(terms))
        return _Result(
            input_text=text(
                "lexical_search.input",
                words=words or text("lexical_search.no_words"),
                extracts=self._count(len(lane.chunks), "extract"),
            ),
            output_text=text("lexical_search.output", extracts=self._count(len(items), "extract")),
            facts=[
                (text("fact.requested"), self._int(k)),
                (text("fact.found"), self._int(len(items))),
            ],
            items=items,
        )

    def _fusion(self, lane: _Lane, stage: Stage) -> _Result:
        if len(lane.lists) < 2:
            raise StageFailed(Message("rag_lab.fusion.needs_two"))
        kinds = lane.list_kinds[-len(lane.lists) :]
        found: dict[int, Item] = {}
        ranks: dict[str, dict[int, tuple[int, float | None]]] = {}
        for kind, ranked in zip(kinds, lane.lists, strict=True):
            ranks[kind] = {i.chunk_id: (i.rank, i.score) for i in ranked}
            for item in ranked:
                found.setdefault(item.chunk_id, item)
        fused = rrf([[i.chunk_id for i in ranked] for ranked in lane.lists])
        items = []
        for rank, (chunk_id, score) in enumerate(fused, start=1):
            item = found[chunk_id]
            sources = [
                {
                    "kind": kind,
                    "label_text": self.deps.texts.stages[kind].label_text,
                    "rank": ranks[kind].get(chunk_id, (None, None))[0],
                    "score": ranks[kind].get(chunk_id, (None, None))[1],
                }
                for kind in kinds
            ]
            items.append(
                Item(
                    chunk_id,
                    item.doc_id,
                    item.title_text,
                    item.text,
                    round(score, 4),
                    rank=rank,
                    sources=sources,
                )
            )
        both = sum(1 for chunk_id, _ in fused if all(chunk_id in ranks[k] for k in kinds))
        text = self._text
        sizes = join([f"{len(r)}" for r in lane.lists], self._lang)
        lane.lists = [items]
        lane.list_kinds = ["fusion"]
        return _Result(
            input_text=text("fusion.input", sizes=sizes),
            output_text=text(
                "fusion.output",
                extracts=self._count(len(items), "extract"),
                both=self._int(both),
                found=agreed("fusion.found", both, self._lang),
                k=RRF_K,
            ),
            facts=[
                (text("fact.constant"), str(RRF_K)),
                (text("fact.fused"), self._int(len(items))),
            ],
            items=items,
        )

    def _context(self, lane: _Lane, stage: Stage) -> _Result:
        ranked = lane.ranked
        if ranked is None:
            raise StageFailed(Message("rag_lab.context.nothing"))
        top_k = param(stage, "top_k", self.deps.catalog)
        kept = ranked[:top_k]
        content = self.deps.content
        items = [
            Item(
                c.chunk_id,
                c.doc_id,
                c.title_text,
                content.excerpt(rank, c.title_text, c.text),
                c.score,
                rank=rank,
                before=c.rank,
                sources=c.sources,
            )
            for rank, c in enumerate(kept, start=1)
        ]
        lane.context = items
        text = "\n\n".join([content.intro_text, *(i.text for i in items)]) if items else ""
        lane.context_text = text
        say = self._text
        return _Result(
            input_text=say("context.input", extracts=self._count(len(ranked), "extract")),
            output_text=text or say("context.empty"),
            facts=[
                (
                    say("fact.kept"),
                    say("context.kept", kept=self._int(len(items)), total=self._int(len(ranked))),
                ),
                (say("fact.characters"), self._int(len(text))),
                (say("fact.placement"), content.placement_text),
            ],
            items=items,
        )

    def _generation(self, lane: _Lane) -> _Result:
        if lane.status != "ok" or not lane.context_text:
            context = self._text("generation.question_only")
        else:
            kept = self._count(len(lane.context), "extract")
            context = self._text("generation.with_context", extracts=kept)
        return _Result(
            input_text=self._text("generation.input", context=context, question=self.question),
            output_text=self.deps.texts.generation_not_run_text,
        )


def _ms(seconds: float) -> int:
    return round(seconds * 1000)


# Short words that say nothing of a subject, by language, accents folded (BM25 skips them;
# the corpus, read from the session's language's index, and the question are in it). Words that
# may be acronyms or times are kept: « it », « us », « who » (IT, US, WHO), « am » (9 am).
STOP_WORDS_BY_LANG: dict[str, frozenset[str]] = {
    "fr": frozenset(
        "au aux avec ce ces cette dans de des du elle elles en est et il ils la le les leur "
        "leurs lui mais me ne nous on ou par pas pour qu que qui sa se ses si son sont sur ta "
        "te tes ton tu un une vos votre vous".split()
    ),
    "en": frozenset(
        "a about after all also an and any are as at be been before being but by can "
        "could did do does for from had has have he her here him his how if in into is its "
        "me more most my no not of on or other our out over she should so some such than "
        "that the their them then there these they this those to too under up was we were "
        "what when where which while whom why will with would you your".split()
    ),
    "de": frozenset(
        "aber alle als am an auch auf aus bei bin bis bist da damit dann das dass dem den "
        "der des die dir doch du durch ein eine einem einen einer eines er es fur hat haben "
        "hatte ich ihr ihre im in ist ja kann man mit nach nicht noch nur ob oder sich sie "
        "sind so uber um und uns unter vom von vor war waren was wenn wer werden wie wir "
        "wird wo zu zum zur".split()
    ),
}


def fold(text: str) -> str:
    """Lower case, accents dropped (« Télétravail » → « teletravail », « für » → « fur »)."""
    decomposed = unicodedata.normalize("NFKD", text.lower())
    return "".join(c for c in decomposed if not unicodedata.combining(c))


def bm25_terms(text: str, lang: str = config.DEFAULT_LANGUAGE) -> list[str]:
    """BM25's words: `\\w+` in lower case, accents folded, two characters or more (« IA »,
    « RH », « 35 » kept), the short stop words of `lang` (the session's) left out."""
    stop = STOP_WORDS_BY_LANG.get(
        config.as_language(lang), STOP_WORDS_BY_LANG[config.DEFAULT_LANGUAGE]
    )
    return [w for w in _WORD.findall(fold(text)) if len(w) >= 2 and w not in stop]


def bm25(query: str, documents: Sequence[str], lang: str = config.DEFAULT_LANGUAGE) -> list[float]:
    """Okapi BM25 of each document for the query, in pure Python: k1 = 1.5, b = 0.75, the
    idf `ln(1 + (N − df + 0.5) / (df + 0.5))` (never negative); `lang`: whose stop words."""
    docs = [bm25_terms(d, lang) for d in documents]
    n = len(docs)
    if not n:
        return []
    mean = sum(len(d) for d in docs) / n or 1.0
    df: dict[str, int] = {}
    for words in docs:
        for word in set(words):
            df[word] = df.get(word, 0) + 1
    terms = list(dict.fromkeys(bm25_terms(query, lang)))
    scores = []
    for words in docs:
        counts: dict[str, int] = {}
        for word in words:
            counts[word] = counts.get(word, 0) + 1
        score = 0.0
        for term in terms:
            tf = counts.get(term, 0)
            if not tf:
                continue
            idf = math.log(1 + (n - df[term] + 0.5) / (df[term] + 0.5))
            norm = tf + BM25_K1 * (1 - BM25_B + BM25_B * len(words) / mean)
            score += idf * tf * (BM25_K1 + 1) / norm
        scores.append(score)
    return scores


def rrf(lists: Sequence[Sequence[int]], k: int = RRF_K) -> list[tuple[int, float]]:
    """Reciprocal rank fusion of ranked lists of ids: `(id, Σ 1 / (k + rank))`, best first
    (ties by best rank, then id)."""
    scores: dict[int, float] = {}
    best: dict[int, int] = {}
    for ranked in lists:
        for rank, item in enumerate(ranked, start=1):
            scores[item] = scores.get(item, 0.0) + 1.0 / (k + rank)
            best[item] = min(best.get(item, rank), rank)
    return sorted(scores.items(), key=lambda x: (-round(x[1], TIE_DIGITS), best[x[0]], x[0]))


def _compared(key: str, item: Item) -> dict[str, Any]:
    return {"key": key, "doc_id": item.doc_id, "title_text": item.title_text}


def compare(a: _Lane, b: _Lane, lang: str = config.DEFAULT_LANGUAGE) -> dict[str, Any]:
    """The two contexts, compared in Python (AD-1): excerpt by excerpt when both chains cut
    the corpus alike, else document by document (a document's best rank). `summary_text`
    in `lang` (languages 5/5)."""
    same_cut = a.chunk_max_chars == b.chunk_max_chars and a.chunks == b.chunks
    basis = "excerpt" if same_cut else "document"

    def ranks(lane: _Lane) -> dict[str, tuple[int, Item]]:
        found: dict[str, tuple[int, Item]] = {}
        for item in lane.context:
            chunk = lane.chunks[item.chunk_id - 1] if lane.chunks else None
            key = f"{item.doc_id}#{chunk.position}" if same_cut and chunk else item.doc_id
            if key not in found:
                found[key] = (item.rank, item)
        return found

    in_a, in_b = ranks(a), ranks(b)
    common, only_a, only_b, changes = [], [], [], []
    for key, (rank, item) in in_a.items():
        if key in in_b:
            entry = _compared(key, item) | {"rank_a": rank, "rank_b": in_b[key][0]}
            common.append(entry)
            if rank != in_b[key][0]:
                changes.append(entry)
        else:
            only_a.append(_compared(key, item) | {"rank_a": rank, "rank_b": None})
    for key, (rank, item) in in_b.items():
        if key not in in_a:
            only_b.append(_compared(key, item) | {"rank_a": None, "rank_b": rank})
    unit = _t(f"compare.unit_{basis}", lang, count=len(common))
    parts = []
    if not a.context or not b.context:
        parts.append(_t("compare.one_empty", lang))
    names = ", ".join(quoted(e["title_text"], lang) for e in common)
    parts.append(
        _t(
            "compare.common",
            lang,
            count=len(common),
            unit=unit,
            names=f" ({names})" if names else "",
            only_a=len(only_a),
            only_b=len(only_b),
        )
    )
    if changes:
        moves = ", ".join(
            _t(
                "compare.move",
                lang,
                title=e["title_text"],
                rank_a=rank_text(e["rank_a"], lang),
                rank_b=rank_text(e["rank_b"], lang),
            )
            for e in changes
        )
        parts.append(_t("compare.gaps", lang, moves=moves))
    elif common:
        parts.append(_t("compare.no_gap", lang))
    if not same_cut:
        parts.append(_t("compare.other_cut", lang))
    return {
        "basis": basis,
        "common": common,
        "only_a": only_a,
        "only_b": only_b,
        "rank_changes": changes,
        "summary_text": " ".join(parts),
    }


def last_run(envelopes: Sequence[Any]) -> list[dict[str, Any]]:
    """The envelopes of the last run in `envelopes` (a journal's), from its
    `rag_lab_run_started` on: the page rebuilds it after a reload (AD-1)."""
    start = next(
        (
            i
            for i in range(len(envelopes) - 1, -1, -1)
            if envelopes[i].kind == "rag_lab_run_started"
        ),
        None,
    )
    if start is None:
        return []
    run_id = envelopes[start].payload.get("run_id")
    return [
        e.model_dump(mode="json")
        for e in envelopes[start:]
        if e.kind.startswith("rag_lab_") and e.payload.get("run_id") == run_id
    ]
