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
from wavestack.models.embedding import Embedder
from wavestack.models.load_registry import LoadRegistry
from wavestack.models.reranker import RerankCancelled, Reranker
from wavestack.rag import index as rag_index
from wavestack.rag.corpus import Chunk, RagContent, chunk_corpus
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
    label_fr: str = Field(min_length=1)
    explain_fr: str = Field(min_length=1)


class OptionText(_Strict):
    label_fr: str = Field(min_length=1)


class ParamText(_Strict):
    label_fr: str = Field(min_length=1)
    unit_fr: str = ""


class StatusTexts(_Strict):
    waiting_fr: str
    running_fr: str
    ok_fr: str
    error_fr: str
    skipped_fr: str
    cancelled_fr: str
    not_run_fr: str


class ColumnTexts(_Strict):
    rank_fr: str
    before_fr: str
    document_fr: str
    score_fr: str


class RagLabContent(_Strict):
    """`content/rag_lab.yaml`: every French text of the page, a text per kind of stage, per
    option and per setting."""

    title_fr: str = Field(min_length=1)
    intro_fr: str = Field(min_length=1)
    back_fr: str = Field(min_length=1)
    busy_fr: str = Field(min_length=1)
    chain_title_fr: str = Field(min_length=1)
    chain_help_fr: str = Field(min_length=1)
    question_label_fr: str = Field(min_length=1)
    question_placeholder_fr: str = Field(min_length=1)
    default_question_fr: str = Field(min_length=1, max_length=QUESTION_MAX)
    run_fr: str = Field(min_length=1)
    stop_fr: str = Field(min_length=1)
    running_fr: str = Field(min_length=1)
    results_title_fr: str = Field(min_length=1)
    results_empty_fr: str = Field(min_length=1)
    generation_not_run_fr: str = Field(min_length=1)
    borrowed_fr: str = Field(min_length=1)
    loaded_fr: str = Field(min_length=1)
    input_fr: str = Field(min_length=1)
    output_fr: str = Field(min_length=1)
    facts_fr: str = Field(min_length=1)
    duration_fr: str = Field(min_length=1)
    memory_fr: str = Field(min_length=1)
    last_run_fr: str = Field(min_length=1)
    compare_fr: str = Field(min_length=1)
    add_fr: str = Field(min_length=1)
    add_button_fr: str = Field(min_length=1)
    move_before_fr: str = Field(min_length=1)
    move_after_fr: str = Field(min_length=1)
    remove_fr: str = Field(min_length=1)
    reset_chain_fr: str = Field(min_length=1)
    chain_a_fr: str = Field(min_length=1)
    chain_b_fr: str = Field(min_length=1)
    unavailable_fr: str = Field(min_length=1)
    comparison_title_fr: str = Field(min_length=1)
    common_fr: str = Field(min_length=1)
    only_a_fr: str = Field(min_length=1)
    only_b_fr: str = Field(min_length=1)
    rank_changes_fr: str = Field(min_length=1)
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


def load_lab_content() -> RagLabContent:
    """Read `content/rag_lab.yaml`, again once the file changed: a corrected file shows on
    the page's reload. Raises on a missing or invalid file. Only the latest read is kept."""
    path = config.content_file("rag_lab.yaml")
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

    label_fr: str = Field(default="A", min_length=1, max_length=40)
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
        label_fr="A",
        stages=[
            Stage(id=f"s{i}", kind=kind, option=option, params=params)
            for i, (kind, option, params) in enumerate(stages, start=1)
        ],
    )


@dataclass
class OptionState:
    """What the page shows of an option: its name, whether it can be chosen (with why not),
    and a note on what a run would meet (a model missing, the brick's index stale)."""

    label_fr: str
    available: bool = True
    reason_fr: str | None = None
    note_fr: str | None = None


@dataclass
class Catalog:
    """The kinds, options and settings the workshop offers now, and the shipped chain."""

    content: RagLabContent
    default: Pipeline
    options: dict[tuple[str, str], OptionState]

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
                            "label_fr": self.content.params[name].label_fr,
                            "unit_fr": self.content.params[name].unit_fr,
                            "min": low,
                            "max": high,
                            "default": param(Stage(id="x", kind=kind, option=option), name, self),
                        }
                    )
                options.append(
                    {
                        "id": option,
                        "label_fr": state.label_fr,
                        "available": state.available,
                        "reason_fr": state.reason_fr,
                        "note_fr": state.note_fr,
                        "params": params,
                    }
                )
            stages.append(
                {
                    "kind": kind,
                    "label_fr": text.label_fr,
                    "explain_fr": text.explain_fr,
                    "movable": kind in RETRIEVAL,
                    "options": options,
                }
            )
        return {"stages": stages, "insert_before": FIXED_TAIL[0]}

    def option_label(self, kind: str, option: str) -> str:
        state = self.options.get((kind, option))
        return state.label_fr if state else option


def _bounds_fr(name: str, low: int, high: int, catalog: Catalog) -> str:
    text = catalog.content.params[name]
    return f"{text.label_fr.lower()} entre {fr_int(low)} et {fr_int(high)} {text.unit_fr}".strip()


def check_pipeline(pipeline: Pipeline, catalog: Catalog) -> tuple[str, str | None] | None:
    """Why the workshop refuses this chain, in French, and the id of the stage at fault
    (`None` when no stage is), or `None` when it runs. The chunking, the embedding and the
    vector store open it, the context and the generation close it, in that order; between
    them, the searches, the fusion and the reranking in any order, each once, at least one
    search; two searches need a fusion after them, a fusion two searches before it, a
    reranking a search before it. Then each stage's option and settings."""
    names = {k: catalog.content.stages[k].label_fr for k in catalog.content.stages}
    stages = pipeline.stages
    ids = [s.id for s in stages]
    if len(set(ids)) != len(ids):
        return "Deux étapes de la chaîne portent le même identifiant.", None
    for stage in stages:
        if stage.kind not in OPTIONS:
            return f"Étape inconnue : « {stage.kind} ».", stage.id
    seen: set[str] = set()
    for stage in stages:
        if stage.kind in seen:
            return f"Étape « {names[stage.kind]} » : elle n'apparaît qu'une fois.", stage.id
        seen.add(stage.kind)
    kinds = [s.kind for s in stages]
    head, tail = list(FIXED_HEAD), list(FIXED_TAIL)
    order = " → ".join(names[k].lower() for k in (*FIXED_HEAD, "…", *FIXED_TAIL) if k in names)
    order = order.replace(" → … → ", " → (recherches, fusion, reranking) → ")
    for kind in (*head, *tail):
        if kind not in kinds:
            return (
                f"Étape « {names[kind]} » : elle est fixe et ne se retire pas ({order}).",
                None,
            )
    if kinds[: len(head)] != head or kinds[-len(tail) :] != tail:
        wrong = next(
            s
            for i, s in enumerate(stages)
            if (s.kind in head and i != head.index(s.kind))
            or (s.kind in tail and i != len(stages) - len(tail) + tail.index(s.kind))
        )
        return (
            f"Étape « {names[wrong.kind]} » : elle est fixe, à sa place dans la chaîne ({order}).",
            wrong.id,
        )
    segment = stages[len(head) : -len(tail)]
    searches = [s for s in segment if s.kind in SEARCHES]
    if not searches:
        context = stages[-len(tail)]
        return (
            f"Étape « {names['context']} » : aucune recherche ne lui apporte d'extraits. "
            "Ajoutez une recherche vectorielle ou lexicale.",
            context.id,
        )
    position = {s.id: i for i, s in enumerate(segment)}
    fusion = next((s for s in segment if s.kind == "fusion"), None)
    if len(searches) == 2:
        second = searches[1]
        if fusion is None:
            return (
                f"Deux recherches demandent une fusion après elles (étape « "
                f"{names[second.kind]} ») : ajoutez la fusion, ou retirez une recherche.",
                second.id,
            )
        if position[fusion.id] < position[second.id]:
            return (
                f"Étape « {names['fusion']} » : elle doit venir après les deux recherches, "
                "qu'elle fusionne. Déplacez-la après elles.",
                fusion.id,
            )
    elif fusion is not None:
        return (
            f"Étape « {names['fusion']} » : la fusion demande deux recherches avant elle. "
            "Ajoutez une seconde recherche, ou retirez la fusion.",
            fusion.id,
        )
    rerank = next((s for s in segment if s.kind == "rerank"), None)
    if rerank is not None and position[rerank.id] < position[searches[0].id]:
        return (
            f"Étape « {names['rerank']} » : le reranking réordonne les candidats d'une "
            "recherche, il doit venir après une recherche.",
            rerank.id,
        )
    for stage in stages:
        label = names[stage.kind]
        state = catalog.options.get((stage.kind, stage.option))
        if state is None:
            return f"Étape « {label} » : l'option « {stage.option} » n'existe pas.", stage.id
        if not state.available:
            return (
                f"Étape « {label} » : {state.label_fr} n'est pas utilisable. {state.reason_fr}",
                stage.id,
            )
        allowed = PARAMS.get((stage.kind, stage.option), ())
        unknown = set(stage.params) - set(allowed)
        if unknown:
            return f"Étape « {label} » : réglage inconnu ({', '.join(sorted(unknown))}).", stage.id
        for name in allowed:
            if name not in stage.params:
                continue
            low, high = catalog.bounds(name)
            if not low <= stage.params[name] <= high:
                return f"Étape « {label} » : {_bounds_fr(name, low, high, catalog)}.", stage.id
    context = pipeline.find("context")
    top_k = param(context, "top_k", catalog) if context else 0
    for stage in searches:
        candidates = param(stage, "candidates", catalog)
        if candidates < top_k:
            kept = "candidat retenu" if candidates == 1 else "candidats retenus"
            return (
                f"Étape « {names[stage.kind]} » : {fr_int(candidates)} {kept}, moins que les "
                f"{count_fr(top_k, 'extrait')} que le contexte doit garder. Retenez au moins "
                f"{count_fr(top_k, 'candidat')}, ou gardez moins d'extraits.",
                stage.id,
            )
    return None


def validate_pipeline(pipeline: Pipeline, catalog: Catalog) -> str | None:
    """Why the workshop refuses this chain (French, naming the stage at fault), or `None`."""
    refusal = check_pipeline(pipeline, catalog)
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
    """Why FAISS or LanceDB cannot be chosen: the extra, and the command that installs it."""
    label = LIBRARIES[option][1]
    return (
        f"Indisponible : {label} n'est pas installé. Depuis le dossier de WaveStack : "
        f"`{INSTALL_FR}`, puis relancez WaveStack. Sans `--extra compression`, Headroom serait "
        "retiré."
    )


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
            f"Le dossier {folder} ne peut pas être supprimé ({type(exc).__name__} : {exc}) : "
            "un autre programme le tient peut-être ouvert. Fermez-le, ou supprimez le dossier "
            "rag_lab WaveStack arrêté."
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


class StageFailed(Exception):
    """A stage cannot do its work: its French reason. `soft`: the chain goes on (the
    reranking), else the next stages are skipped."""

    def __init__(self, message_fr: str, *, soft: bool = False) -> None:
        super().__init__(message_fr)
        self.message_fr = message_fr
        self.soft = soft


class StageSkipped(Exception):
    """A stage that does not run (the reranker is not on the workstation): why, in French."""

    def __init__(self, reason_fr: str) -> None:
        super().__init__(reason_fr)
        self.reason_fr = reason_fr


class LabCancelled(Exception):
    """« Arrêter », seen between two stages, two passages or two candidates."""


@dataclass
class Lent:
    """A model for the run: borrowed from the RAG brick (never closed by the run), or loaded
    for it (closed at its end by whoever lent it)."""

    model: Any
    borrowed: bool
    label_fr: str


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
        label_fr: str,
        noun_fr: str,
        unavailable_fr: str | None,
        cost: int,
        slot: str,
        open_model: Callable[[], Any],
        soft: bool = False,
    ) -> Lent:
        """`borrowed`: the brick's model, else `None`; `unavailable_fr`: why it cannot load
        (a missing file). `soft`: its failure lets the chain go on (the reranker), and a
        missing file only skips the stage."""
        if borrowed is not None:
            return Lent(borrowed, True, label_fr)
        if unavailable_fr is not None:
            if soft:
                raise StageSkipped(unavailable_fr)
            raise StageFailed(unavailable_fr)
        if (slot, label_fr) in self._by_key:
            return Lent(self._by_key[(slot, label_fr)], False, label_fr)
        refusal = self._registry.check_component(f"{noun_fr} {label_fr}", cost, slot)
        if refusal is not None:
            raise StageFailed(refusal, soft=soft)
        try:
            model = open_model()
        except Exception as exc:  # noqa: BLE001 - said in the stage, never a crash
            raise StageFailed(
                f"Le {noun_fr} {label_fr} n'a pas pu être chargé ({type(exc).__name__} : {exc}).",
                soft=soft,
            ) from exc
        self._registry.grant(label_fr, cost, slot)
        self._opened.append((model, slot))
        self._by_key[(slot, label_fr)] = model
        return Lent(model, False, label_fr)

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


@dataclass
class Item:
    """An excerpt in a ranked list: its rank (from 1), where it was before, its score."""

    chunk_id: int
    doc_id: str
    title_fr: str
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
            "title_fr": self.title_fr,
            "text": self.text,
            "score": self.score,
            "sources": self.sources,
        }


@dataclass
class _Result:
    input_fr: str = ""
    output_fr: str = ""
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
        return self.deps.texts.stages[stage.kind].label_fr

    # -- the run --

    def run(self) -> str:
        started = time.monotonic()
        texts = self.deps.texts
        lanes = []
        for pipeline, lane in zip(self.pipelines, "ab", strict=False):
            lanes.append(
                {
                    "lane": lane,
                    "label_fr": pipeline.label_fr,
                    "stages": [
                        {
                            "stage_id": s.id,
                            "kind": s.kind,
                            "option": s.option,
                            "label_fr": self._label(s),
                            "option_label_fr": self.deps.catalog.option_label(s.kind, s.option),
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
                "phase_label": f"{texts.running_fr} « {self.question[:80]} »",
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
                comparison = compare(self.lanes[0], self.lanes[1])
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
                base | {"phase_label": f"{self._label(stage)} en cours…"},
                step_id,
                component,
            )
            rss_before = self.deps.rss()
            started = time.monotonic()
            status, error_fr, result = "ok", None, _Result()
            try:
                result = self._run_stage(lane, stage, step_id, component, base)
            except LabCancelled:
                status, error_fr = "cancelled", "Arrêtée par « Arrêter »."
                lane.status, stopped = "cancelled", True
            except StageSkipped as skipped:
                status, error_fr = "skipped", skipped.reason_fr
                result = self._passed_on(lane, skipped.reason_fr)
            except StageFailed as failed:
                status, error_fr = "error", failed.message_fr
                if failed.soft:
                    result = self._passed_on(lane, failed.message_fr)
                else:
                    lane.status, stopped = "error", True
            except Exception as exc:  # noqa: BLE001 - AD-16: a stage's failure, never a crash
                status = "error"
                error_fr = f"L'étape a échoué ({type(exc).__name__} : {exc})."
                lane.status, stopped = "error", True
            duration = _ms(time.monotonic() - started)
            self._ended(step_id, component, base, status, result, error_fr, duration, rss_before)

    def _ended(
        self,
        step_id: str,
        component: str,
        base: dict[str, Any],
        status: str,
        result: _Result,
        error_fr: str | None,
        duration_ms: int,
        rss_before: int | None,
    ) -> None:
        rss = self.deps.rss() if status in ("ok", "error", "cancelled") or rss_before else None
        memory_fr = None
        if rss is not None:
            memory_fr = f"{_mo(rss)} Mo"
            if rss_before is not None:
                delta = rss - rss_before
                sign = "+" if delta >= 0 else "−"
                memory_fr += f" ({sign}{_mo(abs(delta))} Mo pendant l'étape)"
        self._emit(
            "rag_lab_stage_ended",
            base
            | {
                "status": status,
                "input_fr": result.input_fr,
                "output_fr": result.output_fr,
                "facts": [{"label_fr": k, "value_fr": v} for k, v in result.facts],
                "items": [i.payload() for i in result.items],
                "borrowed": result.borrowed,
                "error_fr": error_fr,
                "duration_ms": duration_ms,
                "rss_bytes": rss,
                "memory_fr": memory_fr,
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
        raise StageFailed(f"Étape inconnue : {stage.kind}.")

    def _passed_on(self, lane: _Lane, reason_fr: str) -> _Result:
        """A reranking skipped or failed: the search's order goes on unchanged."""
        n = len(lane.ranked or [])
        return _Result(
            input_fr=f"{count_fr(n, 'candidat')} de la recherche.",
            output_fr=f"Ordre de la recherche gardé tel quel. {reason_fr}",
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
        source = "le corpus (content/corpus), découpé pour cette exécution"
        chunks: list[Chunk] = []
        if self._uses_brick_index(lane) and self.deps.brick_index_error is None:
            # Its ids are the index's: never the corpus's chunks under the brick's vectors.
            try:
                chunks = rag_index.read_chunks(self.deps.brick_index)
            except Exception as exc:  # noqa: BLE001 - said in the stage
                raise StageFailed(
                    f"L'index de la brique RAG ne se lit pas ({type(exc).__name__} : {exc}). "
                    "Reconstruisez-le depuis la carte RAG de l'atelier."
                ) from exc
            source = "l'index de la brique RAG (découpé à sa construction)"
        if not chunks:
            chunks = chunk_corpus(self.deps.content, size)
        if not chunks:
            raise StageFailed("Le corpus ne donne aucun extrait.")
        lane.chunks = chunks
        docs = len({c.doc_id for c in chunks})
        longest = max(len(c.text) for c in chunks)
        mean = round(sum(len(c.text) for c in chunks) / len(chunks))
        return _Result(
            input_fr=(
                f"{count_fr(docs, 'document')} du corpus de démonstration "
                f"({fr_int(len(self.deps.content.documents))} déclarés dans content/rag.yaml)."
            ),
            output_fr=(
                f"{count_fr(len(chunks), 'extrait')} de {fr_int(size)} caractères au plus, lus "
                "dans "
                f"{source}."
            ),
            facts=[
                ("Taille maximale", f"{fr_int(size)} caractères"),
                ("Extraits", fr_int(len(chunks))),
                ("Longueur moyenne", f"{fr_int(mean)} caractères"),
                ("Plus long", f"{fr_int(longest)} caractères"),
            ],
        )

    def _embedding(
        self, lane: _Lane, stage: Stage, progress: Callable[[int, int], None]
    ) -> _Result:
        lent = self.deps.embedder(stage.option)
        embedder: Embedder = lent.model
        lane.embedder_label = lent.label_fr
        self._check()
        n = fr_int(len(lane.chunks))
        passages_n = count_fr(len(lane.chunks), "passage")
        vectors_n = count_fr(len(lane.chunks), "vecteur")
        facts = [("Modèle", lent.label_fr), ("Dimensions", fr_int(embedder.dims))]
        if self._uses_brick_index(lane):
            if self.deps.brick_index_error is None:
                passages = (
                    f"Passages (titre du document, puis extrait) : {passages_n}, déjà vectorisés "
                    "dans l'index de la brique RAG, calculés à sa construction."
                )
            else:
                passages = (
                    "Les passages ne sont pas vectorisés ici : l'index de la brique RAG ne peut "
                    "pas servir (voir Base vectorielle)."
                )
        else:
            identity = self.deps.identity(stage.option)
            digest = rag_index.corpus_digest(lane.chunks)
            lane.key = cache_key(identity, lane.chunk_max_chars, digest)
            folder = self.deps.lab_dir / lane.key
            vectors = read_vectors(folder, lane.chunks, embedder.dims)
            if vectors is not None:
                passages = f"Passages relus du cache ({vectors_n}, dossier {lane.key})."
                facts.append(("Passages", f"relus du cache ({n})"))
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
                    raise StageFailed(
                        f"Le modèle ne rend pas un vecteur de {embedder.dims} dimensions par "
                        "passage."
                    )
                write_vectors(folder, lane.chunks, vectors, identity)
                seconds = time.monotonic() - started
                passages = (
                    f"Passages calculés ({passages_n}) en {fr_ms(_ms(seconds))}, puis mis en "
                    f"cache (dossier {lane.key})."
                )
                facts.append(("Passages", f"calculés ({passages_n})"))
            lane.vectors = vectors
        vector = embedder.embed_queries([self.question])[0]
        if not any(vector):
            raise StageFailed(
                "La question ne donne aucun vecteur exploitable (vecteur nul) : reformulez-la "
                "avec des mots du corpus."
            )
        lane.embedder = embedder
        lane.query_vector = vector
        shown = " ; ".join(fr_score(v) for v in vector[:4])
        facts.append(("Provenance", self._provenance(lent)))
        return _Result(
            input_fr=(
                f"La question « {self.question} », et le découpage : "
                f"{count_fr(len(lane.chunks), 'extrait')}."
            ),
            output_fr=(
                f"Question → vecteur de {fr_int(len(vector))} nombres ({shown} ; …). {passages}"
            ),
            facts=facts,
            borrowed=lent.borrowed,
        )

    def _provenance(self, lent: Lent) -> str:
        return self.deps.texts.borrowed_fr if lent.borrowed else self.deps.texts.loaded_fr

    def _vector_store(self, lane: _Lane, stage: Stage) -> _Result:
        if lane.embedder is None:
            raise StageFailed("Aucun modèle d'embedding : l'étape Embedding n'a pas abouti.")
        n = len(lane.chunks)
        dims = lane.embedder.dims
        if self._uses_brick_index(lane):
            if self.deps.brick_index_error is not None:
                raise StageFailed(self.deps.brick_index_error)
            path = self.deps.brick_index
            meta = rag_index.read_meta(path)
            lane.store = _SqliteStore(path, lane.embedder)
            return _Result(
                input_fr=(
                    f"{count_fr(meta.chunks, 'vecteur')} de {fr_int(meta.dims)} dimensions, "
                    "calculés "
                    f"par « {meta.embedding_model_id} » le {meta.built_at[:10]}."
                ),
                output_fr=(
                    f"Index sqlite-vec de la brique RAG, lu seulement ({path.name}) : l'atelier "
                    "n'y écrit jamais."
                ),
                facts=[
                    ("Fichier", str(path)),
                    ("Vecteurs", fr_int(meta.chunks)),
                    ("Métrique", "cosinus"),
                ],
            )
        if lane.vectors is None:
            raise StageFailed("Aucun vecteur des passages : l'étape Embedding n'a pas abouti.")
        vectors_fr = f"{count_fr(n, 'vecteur')} de {fr_int(dims)} dimensions"
        if stage.option == "memory":
            lane.store = MemoryStore(lane.chunks, lane.vectors)
            size = n * dims * 4
            return _Result(
                input_fr=f"De l'étape Embedding : {vectors_fr}.",
                output_fr=(
                    f"Rangés en mémoire, sans index ({size_fr(size)} en float32) : chaque "
                    "recherche compare la question à tous les vecteurs."
                ),
                facts=[("Vecteurs", fr_int(n)), ("Métrique", "cosinus (produit scalaire)")],
            )
        if stage.option == "sqlite_vec":
            path = self.deps.lab_dir / lane.key / INDEX_FILE
            built = "relu"
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
                built = f"construit ({count_fr(n, 'vecteur')})"
            lane.store = _SqliteStore(path, lane.embedder)
            return _Result(
                input_fr=f"De l'étape Embedding : {vectors_fr}.",
                output_fr=(
                    f"Index sqlite-vec de l'atelier {built} (dossier {lane.key}) : l'index de la "
                    "brique n'est pas touché."
                ),
                facts=[("Fichier", str(path)), ("Vecteurs", fr_int(n)), ("Métrique", "cosinus")],
            )
        if stage.option in LIBRARIES:
            label = LIBRARIES[stage.option][1]
            imported = self.deps.importer(stage.option)
            self._check()
            folder = self.deps.lab_dir / lane.key
            if stage.option == "faiss":
                store: Any = FaissStore(imported.module, folder, lane.vectors)
                kind = "index plat à produit scalaire (IndexFlatIP)"
            else:
                store = LanceStore(imported.module, folder, lane.vectors)
                kind = "table « chunks », métrique cosinus"
            lane.store = store
            state = (
                f"construit ({count_fr(n, 'vecteur')})"
                if store.built
                else f"relu ({count_fr(n, 'vecteur')})"
            )
            return _Result(
                input_fr=f"De l'étape Embedding : {vectors_fr}.",
                output_fr=(
                    f"Index {label} {state}, {kind}, dans le dossier {lane.key} de l'atelier."
                ),
                facts=[("Dossier", str(store.path)), ("Vecteurs", fr_int(n)), *imported.facts],
            )
        raise StageFailed(f"Base vectorielle inconnue : {stage.option}.")

    def _vector_search(self, lane: _Lane, stage: Stage) -> _Result:
        if lane.store is None or lane.query_vector is None:
            raise StageFailed("Aucune base vectorielle : l'étape précédente n'a pas abouti.")
        k = param(stage, "candidates", self.deps.catalog)
        hits = lane.store.search(lane.query_vector, k)
        items = []
        for rank, (chunk_id, score) in enumerate(hits, start=1):
            chunk = lane.chunks[chunk_id - 1]
            items.append(Item(chunk_id, chunk.doc_id, chunk.title_fr, chunk.text, score, rank=rank))
        lane.lists.append(items)
        lane.list_kinds.append("vector_search")
        best = items[0].score if items else None
        worst = items[-1].score if items else None
        return _Result(
            input_fr=(
                "Le vecteur de la question, comparé à ceux de la base : "
                f"{count_fr(len(lane.chunks), 'vecteur')}."
            ),
            output_fr=(
                f"Les plus proches, sans seuil : {count_fr(len(items), 'extrait')} ; "
                "score = 1 − distance "
                f"cosinus, de {fr_score(best)} à {fr_score(worst)}."
            ),
            facts=[("Candidats demandés (k)", fr_int(k)), ("Trouvés", fr_int(len(items)))],
            items=items,
        )

    def _rerank(self, lane: _Lane, stage: Stage, progress: Callable[[int, int], None]) -> _Result:
        candidates = lane.ranked
        if not candidates:
            raise StageSkipped("Aucun candidat à réordonner.")
        lent = self.deps.reranker(stage.option)
        reranker: Reranker = lent.model
        passages = [f"{c.title_fr}\n{c.text}" for c in candidates]
        try:
            raw = reranker.score(self.question, passages, self.deps.cancelled, progress)
        except RerankCancelled:
            raise LabCancelled() from None
        except Exception as exc:  # noqa: BLE001 - the chain goes on with the search's order
            raise StageFailed(
                f"Le reranking a échoué ({type(exc).__name__} : {exc}). La construction du "
                "contexte garde l'ordre de la recherche.",
                soft=True,
            ) from exc
        if len(raw) != len(candidates):
            raise StageFailed(
                f"{count_fr(len(raw), 'score')} pour {count_fr(len(candidates), 'candidat')} : "
                "l'ordre de la recherche "
                "est gardé.",
                soft=True,
            )
        scores = []
        for item in raw:
            try:
                value = float(item.score)
            except (TypeError, ValueError):
                raise StageFailed(
                    "Le reranker a rendu un score qui n'est pas un nombre : l'ordre de la "
                    "recherche est gardé.",
                    soft=True,
                ) from None
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
                    c.title_fr,
                    c.text,
                    scores[i],
                    rank=rank,
                    before=c.rank,
                    sources=c.sources
                    or [
                        {
                            "kind": self._made_by(lane),
                            "label_fr": self.deps.texts.stages[self._made_by(lane)].label_fr,
                            "rank": c.rank,
                            "score": c.score,
                        }
                    ],
                )
            )
        lane.lists[-1] = items
        moved = max(items, key=lambda x: (x.before or 0) - x.rank)
        climb = (
            f"« {moved.title_fr} » monte du {fr_rank(moved.before or 0)} au "
            f"{fr_rank(moved.rank)} rang."
            if (moved.before or 0) > moved.rank
            else "L'ordre de la recherche ne change pas."
        )
        return _Result(
            input_fr=(
                f"La question et {count_fr(len(candidates), 'candidat')} de la recherche, lus "
                "par paires."
            ),
            output_fr=(
                f"{count_fr(len(items), 'candidat réordonné', 'candidats réordonnés')} par le "
                f"reranker. {climb}"
            ),
            facts=[
                ("Modèle", lent.label_fr),
                ("Paires lues", fr_int(len(candidates))),
                (
                    "Provenance",
                    self.deps.texts.borrowed_fr if lent.borrowed else self.deps.texts.loaded_fr,
                ),
            ],
            items=items,
            borrowed=lent.borrowed,
        )

    def _made_by(self, lane: _Lane) -> str:
        """The kind of the stage that made the lane's current list (a search or the fusion)."""
        return lane.list_kinds[-1] if lane.list_kinds else "vector_search"

    def _lexical_search(self, lane: _Lane, stage: Stage) -> _Result:
        if not lane.chunks:
            raise StageFailed("Aucun extrait : le découpage n'a pas abouti.")
        k = param(stage, "candidates", self.deps.catalog)
        scored = bm25(self.question, [rag_index.passage_text(c) for c in lane.chunks])
        found = sorted(
            ((score, i + 1) for i, score in enumerate(scored) if score > 0),
            key=lambda x: (-round(x[0], TIE_DIGITS), x[1]),
        )[:k]
        items = []
        for rank, (score, chunk_id) in enumerate(found, start=1):
            chunk = lane.chunks[chunk_id - 1]
            items.append(
                Item(chunk_id, chunk.doc_id, chunk.title_fr, chunk.text, round(score, 3), rank=rank)
            )
        lane.lists.append(items)
        lane.list_kinds.append("lexical_search")
        words = ", ".join(f"« {w} »" for w in dict.fromkeys(bm25_terms(self.question)))
        return _Result(
            input_fr=(
                f"Les mots de la question ({words or 'aucun'}), cherchés dans les "
                f"{count_fr(len(lane.chunks), 'extrait')}, sans embedding."
            ),
            output_fr=(
                f"Ceux qui partagent le plus de mots avec la question : "
                f"{count_fr(len(items), 'extrait')}, "
                f"pondérés par leur rareté (BM25, k1 = 1,5, b = 0,75) ; un extrait sans aucun "
                "mot commun n'est pas retenu."
            ),
            facts=[("Candidats demandés (k)", fr_int(k)), ("Trouvés", fr_int(len(items)))],
            items=items,
        )

    def _fusion(self, lane: _Lane, stage: Stage) -> _Result:
        if len(lane.lists) < 2:
            raise StageFailed("La fusion demande deux listes de recherche.")
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
                    "label_fr": self.deps.texts.stages[kind].label_fr,
                    "rank": ranks[kind].get(chunk_id, (None, None))[0],
                    "score": ranks[kind].get(chunk_id, (None, None))[1],
                }
                for kind in kinds
            ]
            items.append(
                Item(
                    chunk_id,
                    item.doc_id,
                    item.title_fr,
                    item.text,
                    round(score, 4),
                    rank=rank,
                    sources=sources,
                )
            )
        both = sum(1 for chunk_id, _ in fused if all(chunk_id in ranks[k] for k in kinds))
        sizes = " et ".join(f"{len(r)}" for r in lane.lists)
        lane.lists = [items]
        lane.list_kinds = ["fusion"]
        return _Result(
            input_fr=f"Les deux listes des recherches ({sizes} extraits), avec leurs rangs.",
            output_fr=(
                f"{count_fr(len(items), 'extrait')}, dont {fr_int(both)} "
                f"{'trouvé' if both == 1 else 'trouvés'} par les deux recherches, classés par "
                f"fusion des rangs réciproques : score = Σ 1 / ({RRF_K} + rang). Un extrait bien "
                "classé par les deux passe devant."
            ),
            facts=[("Constante k", str(RRF_K)), ("Extraits fusionnés", fr_int(len(items)))],
            items=items,
        )

    def _context(self, lane: _Lane, stage: Stage) -> _Result:
        ranked = lane.ranked
        if ranked is None:
            raise StageFailed("Aucune recherche n'a abouti : il n'y a rien à placer.")
        top_k = param(stage, "top_k", self.deps.catalog)
        kept = ranked[:top_k]
        content = self.deps.content
        items = [
            Item(
                c.chunk_id,
                c.doc_id,
                c.title_fr,
                content.excerpt(rank, c.title_fr, c.text),
                c.score,
                rank=rank,
                before=c.rank,
                sources=c.sources,
            )
            for rank, c in enumerate(kept, start=1)
        ]
        lane.context = items
        text = "\n\n".join([content.intro_fr, *(i.text for i in items)]) if items else ""
        lane.context_text = text
        return _Result(
            input_fr=(f"Le classement de l'étape précédente : {count_fr(len(ranked), 'extrait')}."),
            output_fr=text or "Aucun extrait : le modèle ne recevrait que la question.",
            facts=[
                ("Extraits gardés", f"{fr_int(len(items))} sur {fr_int(len(ranked))}"),
                ("Caractères", fr_int(len(text))),
                ("Placement", content.placement_fr),
            ],
            items=items,
        )

    def _generation(self, lane: _Lane) -> _Result:
        if lane.status != "ok" or not lane.context_text:
            context = "la question seule (aucun contexte construit)"
        else:
            kept = count_fr(len(lane.context), "extrait")
            context = f"le contexte construit ({kept}), puis la question"
        return _Result(
            input_fr=(
                f"Le modèle actif de l'atelier recevrait : son prompt système, {context} : "
                f"« {self.question} »."
            ),
            output_fr=self.deps.texts.generation_not_run_fr,
        )


def _ms(seconds: float) -> int:
    return round(seconds * 1000)


# Short French words that say nothing of a subject, accents folded (BM25 skips them).
STOP_WORDS = frozenset(
    "au aux avec ce ces cette dans de des du elle elles en est et il ils la le les leur leurs "
    "lui mais me ne nous on ou par pas pour qu que qui sa se ses si son sont sur ta te tes "
    "ton tu un une vos votre vous".split()
)


def fold(text: str) -> str:
    """Lower case, accents dropped (« Télétravail » → « teletravail »)."""
    decomposed = unicodedata.normalize("NFKD", text.lower())
    return "".join(c for c in decomposed if not unicodedata.combining(c))


def bm25_terms(text: str) -> list[str]:
    """BM25's words: `\\w+` in lower case, accents folded, two characters or more (« IA »,
    « RH », « 35 » kept), a short list of French stop words left out."""
    return [w for w in _WORD.findall(fold(text)) if len(w) >= 2 and w not in STOP_WORDS]


def bm25(query: str, documents: Sequence[str]) -> list[float]:
    """Okapi BM25 of each document for the query, in pure Python: k1 = 1.5, b = 0.75, the
    idf `ln(1 + (N − df + 0.5) / (df + 0.5))` (never negative)."""
    docs = [bm25_terms(d) for d in documents]
    n = len(docs)
    if not n:
        return []
    mean = sum(len(d) for d in docs) / n or 1.0
    df: dict[str, int] = {}
    for words in docs:
        for word in set(words):
            df[word] = df.get(word, 0) + 1
    terms = list(dict.fromkeys(bm25_terms(query)))
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
    return {"key": key, "doc_id": item.doc_id, "title_fr": item.title_fr}


def compare(a: _Lane, b: _Lane) -> dict[str, Any]:
    """The two contexts, compared in Python (AD-1): excerpt by excerpt when both chains cut
    the corpus alike, else document by document (a document's best rank)."""
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
    unit = "extrait" if same_cut else "document"
    parts = []
    if not a.context or not b.context:
        parts.append("Une des deux chaînes n'a construit aucun contexte.")
    names = ", ".join(f"« {e['title_fr']} »" for e in common)
    parts.append(
        f"En commun : {len(common)} {unit}{'s' if len(common) > 1 else ''}"
        + (f" ({names})" if names else "")
        + f" ; seulement dans A : {len(only_a)} ; seulement dans B : {len(only_b)}."
    )
    if changes:
        moves = ", ".join(
            f"« {e['title_fr']} » {fr_rank(e['rank_a'])} en A, {fr_rank(e['rank_b'])} en B"
            for e in changes
        )
        parts.append(f"Écarts de rang : {moves}.")
    elif common:
        parts.append("Aucun écart de rang entre les extraits communs.")
    if not same_cut:
        parts.append("Les deux chaînes découpent le corpus autrement : comparaison par document.")
    return {
        "basis": basis,
        "common": common,
        "only_a": only_a,
        "only_b": only_b,
        "rank_changes": changes,
        "summary_fr": " ".join(parts),
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
