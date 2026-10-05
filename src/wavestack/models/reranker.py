"""The reranking port and its adapter (story 16, AD-8, AD-22).

`[rag.reranker]` names the model; only its `backend`'s adapter exists (story 12's verdict:
`llama_cpp`, bge-reranker-v2-m3 in `RANK` pooling). A reranker reads the query and one
excerpt together and gives one relevance figure: `Llama.embed()` does not fit (it reads
`n_embd` floats per sequence, a `RANK` model writes one), so the adapter decodes each pair
and reads the pooled output itself, as story 12's bench does. `llama_cpp` is imported lazily:
only `models` imports it.

Lot 5c-2: how a pair is laid out and its figure read depends on the model, said by its GGUF
header (`rerank_format`): a cross-encoder (BGE, XLM-R converted as `bert`, not causal) takes
`[BOS] q [EOS] [SEP] d [EOS]` and gives a logit, brought back to [0, 1] by a sigmoid; a
reranker of LLM architecture (Qwen3-Reranker, causal) takes its GGUF's own rerank template
and gives a probability already, read as it is. A cross-encoder that needs segment ids
(`token_type_count` >= 2, ms-marco MiniLM: llama.cpp does not pass them) and an LLM without a
rerank template are refused: their scores would mean nothing.
"""

from __future__ import annotations

import math
import re
from collections.abc import Callable, Mapping, Sequence
from pathlib import Path
from typing import Any, Literal, NamedTuple, Protocol

from wavestack import config
from wavestack.config import RerankerModel
from wavestack.messages import KeyedError
from wavestack.models import gguf_meta


class RerankScore(NamedTuple):
    """One excerpt's relevance in [0, 1], and whether it was cut to fit the pair."""

    score: float
    truncated: bool = False


# Lot 5c-2: how a reranker's figure becomes its score, said in the Reranking stage's focus.
ScoreReading = Literal["sigmoid", "probability"]


class Reranker(Protocol):
    """What the RAG needs from a reranking model: one relevance score in [0, 1] per excerpt,
    for a query. `cancelled` is checked between two excerpts; `progress(done, total)` is
    called after each one. Lot 5c-2: an adapter may also say `score_reading` (the sigmoid of
    a logit, or the model's own probability) and `max_tokens` (a pair's length)."""

    model_id: str

    def score(
        self,
        query: str,
        passages: Sequence[str],
        cancelled: Callable[[], bool] | None = None,
        progress: Callable[[int, int], None] | None = None,
    ) -> list[RerankScore]: ...

    def close(self) -> None: ...


class RerankCancelled(Exception):
    """« Arrêter » between two excerpts."""


class RerankerRefused(KeyedError, ValueError):
    """A reranking model that cannot serve (a `ValueError`, as before): keyed (languages
    5/5), `str()` the French, `render(lang)` the session's language."""


def sigmoid(logit: float) -> float:
    """A reranker's logit as a score in [0, 1] (FlagEmbedding's `normalize=True`)."""
    if math.isnan(logit):
        return 0.0
    if logit >= 0:
        return 1.0 / (1.0 + math.exp(-logit))
    z = math.exp(logit)
    return z / (1.0 + z)


def fit(query: list[int], passage: list[int], room: int) -> tuple[list[int], list[int], bool]:
    """Lot 5c-2: the query and the passage cut to `room` tokens together, and whether
    something was cut: the query (a user's message) keeps at least half of the room, more when
    the passage leaves some; the passage takes the rest (the rule of `pair_tokens` and of
    a rerank template's pair)."""
    room = max(2, room)
    if len(query) + len(passage) <= room:
        return query, passage, False
    keep = max(1, min(len(query), max(room // 2, room - len(passage))))
    return query[:keep], passage[: room - keep], True


def pair_tokens(
    query: list[int],
    passage: list[int],
    *,
    bos: int | None,
    eos: int | None,
    sep: int | None,
    max_tokens: int,
) -> tuple[list[int], bool]:
    """`[BOS] q [EOS] [SEP] d [EOS]` (llama-server's `format_rerank`), a special token left
    out when `None` (the vocabulary does not add it), and whether something was cut. When the
    pair does not fit in `max_tokens`, the query (a user's message) keeps at least half of the
    room, more when the passage leaves some; the passage takes the rest."""
    head = [bos] if bos is not None else []
    close = [eos] if eos is not None else []
    middle = close + ([sep] if sep is not None else [])
    query, passage, cut = fit(query, passage, max_tokens - len(head) - len(middle) - len(close))
    return head + query + middle + passage + close, cut


def special_tokens(llama_cpp, llm) -> tuple[int | None, int | None, int | None]:  # noqa: ANN001
    """BOS, EOS and SEP as the vocabulary adds them to a pair: `None` when it does not add
    one, when the token is `LLAMA_TOKEN_NULL` (-1), or when this llama-cpp-python has no
    binding to say so (never assumed)."""
    vocab = llama_cpp.llama_model_get_vocab(llm._model.model)
    null = getattr(llama_cpp, "LLAMA_TOKEN_NULL", -1)

    def token(name: str) -> int | None:
        adds = getattr(llama_cpp, f"llama_vocab_get_add_{name}", None)
        if adds is None or not adds(vocab):
            return None
        value = int(getattr(llama_cpp, f"llama_vocab_{name}")(vocab))
        return None if value in (null, -1) else value

    return token("bos"), token("eos"), token("sep")


def model_path(model: RerankerModel) -> Path:
    """Where the model loads from: `load_path`, under `models_dir()`."""
    return config.models_dir() / model.load_path


# ---------- lot 5c-2: the pair's format, read in the GGUF header ----------

RANK_POOLING = 4  # llama.cpp's `LLAMA_POOLING_TYPE_RANK`
RERANK_TEMPLATE = "tokenizer.chat_template.rerank"
# The fields of a rerank template llama-server fills (`format_prompt_rerank`), each once.
_FIELDS = ("document", "query")
_FIELD = re.compile(r"\{(query|document)\}")


class RerankFormat(NamedTuple):
    """How a reranker reads a pair: `pair` (`[BOS] q [EOS] [SEP] d [EOS]`, a logit) or
    `template` (its GGUF's rerank template, a probability), and that template."""

    kind: Literal["pair", "template"]
    template: str | None = None

    @property
    def score_reading(self) -> ScoreReading:
        return "probability" if self.kind == "template" else "sigmoid"


PAIR = RerankFormat("pair")


def _number(value: object) -> int | None:
    """A GGUF integer, typed (the header read in Python) or as a text (llama.cpp's metadata)."""
    if value is None or isinstance(value, bool):
        return None
    try:
        return int(str(value).strip())
    except ValueError:
        return None


# llama.cpp's encoder architectures (bidirectional, never an LLM), when their GGUF was
# converted without `{arch}.attention.causal`.
ENCODERS = frozenset(
    {
        "bert",
        "modern-bert",
        "neo-bert",
        "nomic-bert",
        "nomic-bert-moe",
        "jina-bert-v2",
        "jina-bert-v3",
        "t5encoder",
    }
)


def _causal(value: object, arch: str) -> bool:
    """`{arch}.attention.causal`: true, a causal model (an LLM); false (`bert`, BGE), a
    bidirectional encoder; absent, causal unless `arch` is a known encoder. A text is
    llama.cpp's metadata (`"false"`)."""
    if value is None:
        return arch not in ENCODERS
    if isinstance(value, str):
        return value.strip().casefold() not in ("false", "0")
    return bool(value)


def _usable_template(template: object) -> bool:
    """A rerank template with `{query}` and `{document}`, once each."""
    return isinstance(template, str) and sorted(_FIELD.findall(template)) == list(_FIELDS)


def rerank_format(meta: Mapping[str, Any] | None) -> RerankFormat:
    """Lot 5c-2: how the model of this GGUF header reads a pair, or `RerankerRefused` with
    the reason it cannot be a reranker WaveStack scores: an embedding pooling, segment ids
    (`token_type_count` >= 2), an LLM architecture without a usable rerank template. A header
    without its architecture (unread) gives the pair, as before: the load's probe judges."""
    meta = meta or {}
    arch = meta.get("general.architecture")
    if not isinstance(arch, str) or not arch:
        return PAIR
    pooling = _number(meta.get(f"{arch}.pooling_type"))
    if pooling is not None and pooling != RANK_POOLING:
        raise RerankerRefused("models.reranker.embedding_pooling", pooling=pooling)
    segments = _number(meta.get("tokenizer.ggml.token_type_count"))
    if segments is not None and segments >= 2:
        raise RerankerRefused("models.reranker.segments", count=segments)
    if not _causal(meta.get(f"{arch}.attention.causal"), arch):
        return PAIR
    template = meta.get(RERANK_TEMPLATE)
    if not _usable_template(template):
        raise RerankerRefused("models.reranker.no_rerank_template", arch=arch)
    return RerankFormat("template", str(template))


def template_parts(template: str) -> list[str]:
    """The rerank template cut at its fields: text, field name, text, field name, text."""
    return _FIELD.split(template)


class LlamaCppReranker:
    """In-process adapter: `Llama(embedding=True, pooling_type=RANK)`, one pair decoded at a
    time, its score read from the pooled output. Lot 5c-2: the GGUF header says how a pair is
    laid out and its figure read (`rerank_format`), and refuses before any load what cannot
    be scored. A probe pair at load refuses, in French, a file that gives no finite score."""

    def __init__(self, model: RerankerModel, path: Path | None = None) -> None:
        import llama_cpp

        self.model_id = model.id
        self.max_tokens = self._max = model.max_tokens
        file = path or model_path(model)
        header = gguf_meta.try_read_metadata(file)
        form = rerank_format(header)  # refused here: nothing loaded
        n = model.max_tokens
        self._llm = llama_cpp.Llama(
            model_path=str(file),
            embedding=True,
            pooling_type=llama_cpp.LLAMA_POOLING_TYPE_RANK,
            n_ctx=n,
            n_batch=n,
            n_ubatch=n,
            verbose=False,
        )
        # An embedding GGUF loads in `RANK` too, and scores anything: its declared pooling
        # (`CLS`, `MEAN`…) refuses it. Undeclared, the forced `RANK` stands (story 12).
        meta = getattr(self._llm, "metadata", None) or {}
        declared = meta.get(f"{meta.get('general.architecture', '')}.pooling_type")
        if declared is not None and str(declared) != str(int(llama_cpp.LLAMA_POOLING_TYPE_RANK)):
            self.close()
            raise RerankerRefused("models.reranker.embedding_pooling", pooling=declared)
        if header is None:  # the header not read in Python: llama.cpp's metadata says
            try:
                form = rerank_format(meta)
            except RerankerRefused:
                self.close()
                raise
        self.format = form
        self.score_reading: ScoreReading = form.score_reading
        self._parts = template_parts(form.template) if form.template else []
        try:
            self._bos, self._eos, self._sep = special_tokens(llama_cpp, self._llm)
            probe = self._figure("Exemplia", "Politique des mots de passe")[0]
        except Exception as exc:  # noqa: BLE001 - said in French, below
            self.close()
            raise RerankerRefused("models.reranker.no_score", kind=type(exc).__name__) from exc
        if not math.isfinite(probe):
            self.close()
            raise RerankerRefused("models.reranker.not_finite")

    def _tokens(self, text: str, special: bool = False) -> list[int]:
        return self._llm.tokenize(text.encode("utf-8"), add_bos=False, special=special)

    def _pair(self, query: str, passage: str) -> tuple[list[int], bool]:
        """The pair's tokens and whether something was cut. A template: filled and tokenized
        as one sequence, its special tokens parsed (llama-server's `format_prompt_rerank`);
        too long, its fixed parts are kept whole and the query and the passage cut (`fit`)."""
        if not self._parts:
            return pair_tokens(
                self._tokens(query),
                self._tokens(passage),
                bos=self._bos,
                eos=self._eos,
                sep=self._sep,
                max_tokens=self._max,
            )
        values = {"query": query, "document": passage}
        filled = "".join(values[p] if i % 2 else p for i, p in enumerate(self._parts))
        tokens = self._tokens(filled, special=True)
        if len(tokens) <= self._max:
            return tokens, False
        fixed = [self._tokens(p, special=True) for p in self._parts[::2]]
        q, d, cut = fit(
            self._tokens(query), self._tokens(passage), self._max - sum(len(f) for f in fixed)
        )
        kept = {"query": q, "document": d}
        tokens = []
        for i, part in enumerate(self._parts):
            tokens += kept[part] if i % 2 else fixed[i // 2]
        return tokens, cut

    def _figure(self, query: str, passage: str) -> tuple[float, bool]:
        """The pooled output of one pair (a logit; a probability for a template)."""
        import llama_cpp

        llm = self._llm
        tokens, cut = self._pair(query, passage)
        llm._ctx.kv_cache_clear()
        llm._batch.reset()
        llm._batch.add_sequence(tokens, 0, True)
        try:
            llm._ctx.decode(llm._batch)
            ptr = llama_cpp.llama_get_embeddings_seq(llm._ctx.ctx, 0)
            return float(ptr[0]), cut
        finally:
            llm._batch.reset()

    def _score(self, figure: float) -> float:
        """The figure as a score in [0, 1]: the sigmoid of a logit; a template's probability
        as it is (a sigmoid would squeeze it between 0.5 and 0.73), only bounded."""
        if self.score_reading == "sigmoid":
            return sigmoid(figure)
        return 0.0 if math.isnan(figure) else min(1.0, max(0.0, figure))

    def score(
        self,
        query: str,
        passages: Sequence[str],
        cancelled: Callable[[], bool] | None = None,
        progress: Callable[[int, int], None] | None = None,
    ) -> list[RerankScore]:
        scores = []
        for passage in passages:
            if cancelled is not None and cancelled():
                raise RerankCancelled("reranking arrêté")
            figure, cut = self._figure(query, passage)
            scores.append(RerankScore(self._score(figure), cut))
            if progress is not None:
                progress(len(scores), len(passages))
        return scores

    def close(self) -> None:
        llm, self._llm = getattr(self, "_llm", None), None
        if llm is not None:
            llm.close()


def open_reranker(model: RerankerModel) -> Reranker:
    """The adapter of the declared `backend` (only `llama_cpp` is accepted by the config)."""
    return LlamaCppReranker(model)
