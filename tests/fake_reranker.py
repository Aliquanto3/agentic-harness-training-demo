"""Fake reranking model for the tests and the end-to-end run (story 16): the share of the
query's words found in the excerpt, weighted by their length, plus a little of their
density. Deterministic, no file, no network; it orders differently from `FakeEmbedder`."""

from __future__ import annotations

from collections.abc import Callable, Sequence

from fake_embedder import _STOP, _WORD

from wavestack.models.reranker import RerankCancelled, RerankScore

MODEL_ID = "fake-reranker"


def _words(text: str) -> list[str]:
    return [w for w in _WORD.findall(text.lower()) if len(w) >= 3 and w not in _STOP]


def relevance(query: str, passage: str) -> float:
    """In [0, 1]: 0.8 × the query's (length-weighted) words found, 0.2 × their density."""
    wanted = set(_words(query))
    if not wanted:
        return 0.0
    words = _words(passage)
    present = set(words)
    found = [w for w in wanted if w in present]
    share = sum(len(w) for w in found) / sum(len(w) for w in wanted)
    density = min(1.0, 10 * sum(words.count(w) for w in found) / max(1, len(words)))
    return round(0.8 * share + 0.2 * density, 6)


class FakeReranker:
    def __init__(self, *, model_id: str = MODEL_ID, fail: bool = False) -> None:
        self.model_id = model_id
        self.fail = fail  # `score` raises: a reranking that fails
        # Excerpts longer than this many characters are said cut (the pair's limit).
        self.truncate_over: int | None = None
        self.bad_score: object = None  # given as the first score instead of a figure
        self.closed = False
        self.calls: list[tuple[str, list[str]]] = []
        self.before_each: Callable[[], None] | None = None  # e.g. « Arrêter » mid-way

    def score(
        self,
        query: str,
        passages: Sequence[str],
        cancelled: Callable[[], bool] | None = None,
        progress: Callable[[int, int], None] | None = None,
    ) -> list[RerankScore]:
        if self.fail:
            raise RuntimeError("reranker en panne")
        self.calls.append((query, list(passages)))
        scores = []
        for passage in passages:
            if self.before_each is not None:
                self.before_each()
            if cancelled is not None and cancelled():
                raise RerankCancelled("reranking arrêté")
            cut = self.truncate_over is not None and len(passage) > self.truncate_over
            scores.append(RerankScore(relevance(query, passage), cut))
            if progress is not None:
                progress(len(scores), len(passages))
        if self.bad_score is not None:
            scores[0] = RerankScore(self.bad_score, False)  # type: ignore[arg-type]
        return scores

    def close(self) -> None:
        self.closed = True
