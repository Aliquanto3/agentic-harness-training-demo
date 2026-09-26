"""The reranking port and its adapter (story 16, AD-8, AD-22).

`[rag.reranker]` names the model; only its `backend`'s adapter exists (story 12's verdict:
`llama_cpp`, bge-reranker-v2-m3 in `RANK` pooling). A reranker reads the query and one
excerpt together and gives one relevance figure: `Llama.embed()` does not fit (it reads
`n_embd` floats per sequence, a `RANK` model writes one), so the adapter decodes each pair
and reads the pooled output itself, as story 12's bench does. The figure (a logit) is brought
back to [0, 1] by a sigmoid. `llama_cpp` is imported lazily: only `models` imports it.
"""

from __future__ import annotations

import math
from collections.abc import Callable, Sequence
from pathlib import Path
from typing import NamedTuple, Protocol

from wavestack import config
from wavestack.config import RerankerModel


class RerankScore(NamedTuple):
    """One excerpt's relevance in [0, 1], and whether it was cut to fit the pair."""

    score: float
    truncated: bool = False


class Reranker(Protocol):
    """What the RAG needs from a reranking model: one relevance score in [0, 1] per excerpt,
    for a query. `cancelled` is checked between two excerpts; `progress(done, total)` is
    called after each one."""

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


def sigmoid(logit: float) -> float:
    """A reranker's logit as a score in [0, 1] (FlagEmbedding's `normalize=True`)."""
    if math.isnan(logit):
        return 0.0
    if logit >= 0:
        return 1.0 / (1.0 + math.exp(-logit))
    z = math.exp(logit)
    return z / (1.0 + z)


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
    room = max(2, max_tokens - len(head) - len(middle) - len(close))
    cut = len(query) + len(passage) > room
    if cut:
        keep_query = min(len(query), max(room // 2, room - len(passage)))
        query, passage = query[: max(1, keep_query)], passage[: room - max(1, keep_query)]
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


class LlamaCppReranker:
    """In-process adapter: `Llama(embedding=True, pooling_type=RANK)`, one pair decoded at a
    time, its score read from the pooled output. A probe pair at load refuses, in French, a
    file that gives no finite score."""

    def __init__(self, model: RerankerModel, path: Path | None = None) -> None:
        import llama_cpp

        self.model_id = model.id
        self._max = model.max_tokens
        n = model.max_tokens
        self._llm = llama_cpp.Llama(
            model_path=str(path or model_path(model)),
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
            raise ValueError(
                f"le fichier déclare le pooling {declared} dans ses métadonnées GGUF, pas RANK "
                "(4) : c'est un modèle d'embedding, pas un modèle de reranking"
            )
        try:
            self._bos, self._eos, self._sep = special_tokens(llama_cpp, self._llm)
            probe = self._logit("Exemplia", "Politique des mots de passe")[0]
        except Exception as exc:  # noqa: BLE001 - said in French, below
            self.close()
            raise ValueError(
                f"le modèle ne note pas une paire question-extrait ({type(exc).__name__}) : "
                "ce n'est pas un modèle de reranking en pooling RANK"
            ) from exc
        if not math.isfinite(probe):
            self.close()
            raise ValueError(
                "le modèle rend un score non fini pour une paire question-extrait : ce n'est "
                "pas un modèle de reranking utilisable"
            )

    def _tokens(self, text: str) -> list[int]:
        return self._llm.tokenize(text.encode("utf-8"), add_bos=False, special=False)

    def _logit(self, query: str, passage: str) -> tuple[float, bool]:
        import llama_cpp

        llm = self._llm
        tokens, cut = pair_tokens(
            self._tokens(query),
            self._tokens(passage),
            bos=self._bos,
            eos=self._eos,
            sep=self._sep,
            max_tokens=self._max,
        )
        llm._ctx.kv_cache_clear()
        llm._batch.reset()
        llm._batch.add_sequence(tokens, 0, True)
        try:
            llm._ctx.decode(llm._batch)
            ptr = llama_cpp.llama_get_embeddings_seq(llm._ctx.ctx, 0)
            return float(ptr[0]), cut
        finally:
            llm._batch.reset()

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
            logit, cut = self._logit(query, passage)
            scores.append(RerankScore(sigmoid(logit), cut))
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
