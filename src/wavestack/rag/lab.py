"""The RAG workshop (story 30, CAP-45): a RAG chain drawn and run apart from the RAG brick.

A chain (`Pipeline`) is an ordered list of stages (`Stage`: a kind, an option, its settings).
`LabRun` runs the chains of one question, lane after lane, with what it is given: the
models lent by the brick or loaded for the run (`Lent`), the brick's index, a stop test and
an emitter. It knows no session. Every figure the page shows is computed here (AD-1): ranks,
scores, sizes, durations, the context built. The workshop is a sandbox: it only reads the
brick's index and never changes the brick's state.
"""

from __future__ import annotations

import time
from collections.abc import Callable, Sequence
from dataclasses import dataclass, field
from functools import cache
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
    "rerank",
    "context",
    "generation",
)
# Each kind's options, the shipped one first.
OPTIONS: dict[str, tuple[str, ...]] = {
    "chunking": ("paragraphs",),
    "embedding": ("declared",),
    "vector_store": ("sqlite_vec",),
    "vector_search": ("cosine",),
    "rerank": ("declared",),
    "context": ("excerpts",),
    "generation": ("not_run",),
}
# The settings of an option, by name.
PARAMS: dict[tuple[str, str], tuple[str, ...]] = {
    ("chunking", "paragraphs"): ("chunk_max_chars",),
    ("vector_search", "cosine"): ("candidates",),
    ("context", "excerpts"): ("top_k",),
}
BOUNDS: dict[str, tuple[int, int]] = {
    "chunk_max_chars": (200, 1500),
    "candidates": (1, 20),
    "top_k": (1, 20),
}
QUESTION_MAX = 500  # the characters of a question the workshop accepts
STATUSES = ("ok", "error", "skipped", "cancelled", "not_run")
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


@cache
def _read_content(path: str, mtime_ns: int) -> RagLabContent:
    return RagLabContent.model_validate(yaml.safe_load(Path(path).read_text(encoding="utf-8")))


def load_lab_content() -> RagLabContent:
    """Read `content/rag_lab.yaml`, again once the file changed: a corrected file shows on
    the page's reload. Raises on a missing or invalid file."""
    path = config.content_dir() / "rag_lab.yaml"
    return _read_content(str(path), path.stat().st_mtime_ns)


load_lab_content.cache_clear = _read_content.cache_clear  # type: ignore[attr-defined]


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
                    shipped = self.default.find(kind)
                    params.append(
                        {
                            "name": name,
                            "label_fr": self.content.params[name].label_fr,
                            "unit_fr": self.content.params[name].unit_fr,
                            "min": low,
                            "max": high,
                            "default": shipped.params.get(name) if shipped else low,
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
                    "options": options,
                }
            )
        return {"stages": stages}

    def option_label(self, kind: str, option: str) -> str:
        state = self.options.get((kind, option))
        return state.label_fr if state else option


def validate_pipeline(pipeline: Pipeline, catalog: Catalog) -> str | None:
    """Why the workshop refuses this chain (French, naming the stage at fault), or `None`.
    Increment 1: only the shipped chain runs."""
    shipped = catalog.default
    kinds = [s.kind for s in pipeline.stages]
    if kinds != [s.kind for s in shipped.stages]:
        return (
            "Seule la chaîne livrée s'exécute ici : découpage, embedding, base vectorielle, "
            "recherche, reranking, construction du contexte et génération, dans cet ordre."
        )
    for stage, ref in zip(pipeline.stages, shipped.stages, strict=True):
        label = catalog.content.stages[stage.kind].label_fr
        if stage.option != ref.option or stage.params != ref.params:
            return f"Étape « {label} » : seule l'option livrée, avec ses réglages, s'exécute ici."
    return None


# ---------- figures in French ----------


def fr_int(n: int) -> str:
    """« 1 536 »: French thousands separator (narrow no-break space)."""
    return f"{n:,}".replace(",", " ")


def fr_score(value: float | None) -> str:
    return "—" if value is None else f"{value:.3f}".replace(".", ",")


def fr_rank(n: int) -> str:
    return "1er" if n == 1 else f"{n}ᵉ"


def fr_ms(ms: int) -> str:
    return f"{fr_int(ms)} ms"


def _mo(n: int) -> str:
    return config.mo_fr(n)


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
    model the brick holds is borrowed: neither checked, granted nor closed."""

    def __init__(self, registry: LoadRegistry) -> None:
        self._registry = registry
        self._opened: list[tuple[Any, str]] = []

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
        return Lent(model, False, label_fr)

    def close(self) -> list[str]:
        """Close what the run loaded, free its slots; the errors met, in French."""
        errors = []
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
    embedder: Callable[[str], Lent]  # option -> the embedding model, or `StageFailed`
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


class _KnownQuery:
    """The embedder, the question's vector already computed: a store's search does not
    embed it a second time."""

    def __init__(self, embedder: Embedder, question: str, vector: list[float]) -> None:
        self.model_id, self.dims = embedder.model_id, embedder.dims
        self._embedder, self._question, self._vector = embedder, question, vector

    def embed_queries(self, texts: Sequence[str]) -> list[list[float]]:
        return [
            self._vector if t == self._question else self._embedder.embed_queries([t])[0]
            for t in texts
        ]

    def embed_passages(self, texts: Sequence[str]) -> list[list[float]]:
        return self._embedder.embed_passages(texts)

    def close(self) -> None:  # the lender closes the real one
        pass


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
    retriever: SqliteVecRetriever | None = None
    ranked: list[Item] | None = None  # the current ranked list
    context: list[Item] = field(default_factory=list)
    context_text: str = ""
    status: str = "ok"


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
        cancelled = False
        for pipeline, lane in zip(self.pipelines, "ab", strict=False):
            state = _Lane(lane, pipeline)
            self.lanes.append(state)
            try:
                self._run_lane(state, skip_all=cancelled)
            finally:
                if state.retriever is not None:
                    state.retriever.close()
            cancelled = cancelled or state.status == "cancelled"
        statuses = {lane.status for lane in self.lanes}
        status = (
            "cancelled" if "cancelled" in statuses else "error" if "error" in statuses else "ok"
        )
        self._emit(
            "rag_lab_run_ended",
            {
                "status": status,
                "duration_ms": _ms(time.monotonic() - started),
                "comparison": None,
            },
            self.run_id,
            "rag_lab",
        )
        return status

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
            return self._embedding(lane, stage)
        if stage.kind == "vector_store":
            return self._vector_store(lane, stage)
        if stage.kind == "vector_search":
            return self._vector_search(lane, stage)
        if stage.kind == "rerank":
            return self._rerank(lane, stage, progress)
        if stage.kind == "context":
            return self._context(lane, stage)
        raise StageFailed(f"Étape inconnue : {stage.kind}.")

    def _passed_on(self, lane: _Lane, reason_fr: str) -> _Result:
        """A reranking skipped or failed: the search's order goes on unchanged."""
        n = len(lane.ranked or [])
        return _Result(
            input_fr=f"{n} candidats de la recherche.",
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
        size = int(stage.params.get("chunk_max_chars", self.deps.shipped_chunk_max_chars))
        lane.chunk_max_chars = size
        source = "le corpus (content/corpus), découpé pour cette exécution"
        chunks: list[Chunk] = []
        if self._uses_brick_index(lane) and self.deps.brick_index_error is None:
            try:
                chunks = rag_index.read_chunks(self.deps.brick_index)
                source = "l'index de la brique RAG (découpé à sa construction)"
            except Exception:  # noqa: BLE001 - read from the corpus instead
                chunks = []
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
                f"{docs} documents du corpus de démonstration ({len(self.deps.content.documents)} "
                f"déclarés dans content/rag.yaml)."
            ),
            output_fr=(
                f"{fr_int(len(chunks))} extraits de {fr_int(size)} caractères au plus, lus dans "
                f"{source}."
            ),
            facts=[
                ("Taille maximale", f"{fr_int(size)} caractères"),
                ("Extraits", fr_int(len(chunks))),
                ("Longueur moyenne", f"{fr_int(mean)} caractères"),
                ("Plus long", f"{fr_int(longest)} caractères"),
            ],
        )

    def _embedding(self, lane: _Lane, stage: Stage) -> _Result:
        lent = self.deps.embedder(stage.option)
        embedder: Embedder = lent.model
        lane.embedder_label = lent.label_fr
        self._check()
        vector = embedder.embed_queries([self.question])[0]
        if not any(vector):
            raise StageFailed(
                "La question ne donne aucun vecteur exploitable (vecteur nul) : reformulez-la "
                "avec des mots du corpus."
            )
        lane.embedder = _KnownQuery(embedder, self.question, vector)  # type: ignore[assignment]
        lane.query_vector = vector
        shown = " ; ".join(fr_score(v) for v in vector[:4])
        if self._uses_brick_index(lane) and self.deps.brick_index_error is None:
            passages = (
                f"Les {fr_int(len(lane.chunks))} passages (titre du document, puis extrait) sont "
                "déjà vectorisés dans l'index de la brique RAG, calculés à sa construction."
            )
        else:
            passages = (
                "Les passages ne sont pas vectorisés ici : l'index de la brique RAG ne peut pas "
                "servir (voir Base vectorielle)."
            )
        return _Result(
            input_fr=f"La question « {self.question} », et les {fr_int(len(lane.chunks))} "
            "extraits du découpage.",
            output_fr=(
                f"Question → vecteur de {fr_int(len(vector))} nombres ({shown} ; …). {passages}"
            ),
            facts=[
                ("Modèle", lent.label_fr),
                ("Dimensions", fr_int(embedder.dims)),
                (
                    "Provenance",
                    self.deps.texts.borrowed_fr if lent.borrowed else self.deps.texts.loaded_fr,
                ),
            ],
            borrowed=lent.borrowed,
        )

    def _vector_store(self, lane: _Lane, stage: Stage) -> _Result:
        if lane.embedder is None:
            raise StageFailed("Aucun modèle d'embedding : l'étape Embedding n'a pas abouti.")
        if not self._uses_brick_index(lane):
            raise StageFailed("Cette base vectorielle n'est pas proposée ici.")
        if self.deps.brick_index_error is not None:
            raise StageFailed(self.deps.brick_index_error)
        path = self.deps.brick_index
        meta = rag_index.read_meta(path)
        lane.retriever = SqliteVecRetriever(path, lane.embedder, 1)
        return _Result(
            input_fr=(
                f"{fr_int(meta.chunks)} vecteurs de {fr_int(meta.dims)} dimensions, calculés par "
                f"« {meta.embedding_model_id} » le {meta.built_at[:10]}."
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

    def _vector_search(self, lane: _Lane, stage: Stage) -> _Result:
        if lane.retriever is None:
            raise StageFailed("Aucune base vectorielle : l'étape précédente n'a pas abouti.")
        k = int(stage.params.get("candidates", 8))
        excerpts = lane.retriever.search(self.question, k)
        items = [
            Item(e.chunk_id, e.doc_id, e.title_fr, e.text, e.score, rank=e.position)
            for e in excerpts
        ]
        lane.ranked = items
        best = items[0].score if items else None
        worst = items[-1].score if items else None
        return _Result(
            input_fr=f"Le vecteur de la question, comparé aux {fr_int(len(lane.chunks))} vecteurs "
            "de la base.",
            output_fr=(
                f"Les {len(items)} extraits les plus proches, sans seuil : score = 1 − distance "
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
                f"{len(raw)} scores pour {len(candidates)} candidats : l'ordre de la recherche "
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
                    sources=[
                        {
                            "kind": "vector_search",
                            "label_fr": "Recherche",
                            "rank": c.rank,
                            "score": c.score,
                        }
                    ],
                )
            )
        lane.ranked = items
        moved = max(items, key=lambda x: (x.before or 0) - x.rank)
        climb = (
            f"« {moved.title_fr} » monte du {fr_rank(moved.before or 0)} au "
            f"{fr_rank(moved.rank)} rang."
            if (moved.before or 0) > moved.rank
            else "L'ordre de la recherche ne change pas."
        )
        return _Result(
            input_fr=f"La question et les {len(candidates)} candidats de la recherche, lus par "
            "paires.",
            output_fr=f"{len(items)} candidats réordonnés par le reranker. {climb}",
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

    def _context(self, lane: _Lane, stage: Stage) -> _Result:
        ranked = lane.ranked
        if ranked is None:
            raise StageFailed("Aucune recherche n'a abouti : il n'y a rien à placer.")
        top_k = int(stage.params.get("top_k", 3))
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
            input_fr=f"Les {len(ranked)} extraits classés par l'étape précédente.",
            output_fr=text or "Aucun extrait : le modèle ne recevrait que la question.",
            facts=[
                ("Extraits gardés", f"{len(items)} sur {len(ranked)}"),
                ("Caractères", fr_int(len(text))),
                ("Placement", content.placement_fr),
            ],
            items=items,
        )

    def _generation(self, lane: _Lane) -> _Result:
        if lane.status != "ok" or not lane.context_text:
            context = "la question seule (aucun contexte construit)"
        else:
            context = (
                f"le contexte construit ({fr_int(len(lane.context))} extraits), puis la question"
            )
        return _Result(
            input_fr=(
                f"Le modèle actif de l'atelier recevrait : son prompt système, {context} : "
                f"« {self.question} »."
            ),
            output_fr=self.deps.texts.generation_not_run_fr,
        )


def _ms(seconds: float) -> int:
    return round(seconds * 1000)


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
