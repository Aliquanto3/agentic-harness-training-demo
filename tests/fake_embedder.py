"""Fake embedding model for the RAG tests (story 15): a hashed bag of words, 64 dimensions,
normalized and deterministic. No file, no network."""

from __future__ import annotations

import hashlib
import re
from collections.abc import Sequence

from wavestack.models.embedding import normalize

DIMS = 64
MODEL_ID = "fake-embedding"
_WORD = re.compile(r"\w+")
# Words every document shares: noise for a bag of words, like the short ones.
_STOP = frozenset(
    "exemplia chez dans pour avec sont cette elle elles leur leurs plus tout tous toute quel "
    "quelle quels combien doit être avoir fait ces ses une des les aux par sur qui que est "
    "pas son sa".split()
)


def vector(text: str) -> list[float]:
    counts = [0.0] * DIMS
    for word in _WORD.findall(text.lower()):
        if len(word) < 3 or word in _STOP:
            continue
        counts[int(hashlib.md5(word.encode()).hexdigest(), 16) % DIMS] += 1.0
    return normalize(counts)


class FakeEmbedder:
    def __init__(self, *, model_id: str = MODEL_ID, fail: bool = False) -> None:
        self.model_id = model_id
        self.dims = DIMS
        self.fail = fail  # `embed_queries` raises: a search that fails
        self.closed = False
        self.queries: list[str] = []

    def embed_queries(self, texts: Sequence[str]) -> list[list[float]]:
        if self.fail:
            raise RuntimeError("embedder en panne")
        self.queries += texts
        return [vector(t) for t in texts]

    def embed_passages(self, texts: Sequence[str]) -> list[list[float]]:
        return [vector(t) for t in texts]

    def close(self) -> None:
        self.closed = True
