"""The `Retriever` port (AD-22) and its sqlite-vec strategy (story 15): the `top_k` nearest
chunks to the query, no threshold, scored `1 − cosine distance` bounded to [0, 1]."""

from __future__ import annotations

import math
import threading
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Protocol

from wavestack.models.embedding import Embedder
from wavestack.rag.index import VEC_TABLE, connect, serialize_vector


@dataclass(frozen=True)
class Excerpt:
    """A chunk found for a query: its rank (from 1), and its score (3 decimals, 0 to 1)."""

    position: int
    chunk_id: int
    doc_id: str
    title_fr: str
    text: str
    score: float

    def payload(self) -> dict[str, object]:
        return asdict(self)


class Retriever(Protocol):
    """V2's strategies (reranking, hybrid search) will implement this same port."""

    def search(self, query: str) -> list[Excerpt]: ...


def score_of(distance: float) -> float:
    """`1 − cosine distance`, bounded to [0, 1] (opposite vectors score 0); NaN scores 0."""
    score = 1.0 - float(distance)
    if math.isnan(score):
        return 0.0
    return round(min(1.0, max(0.0, score)), 3)


class SqliteVecRetriever:
    """The nearest chunks of the index, by the embedder's query vector. One connection,
    opened once (the extension loaded once), closed by `close()`."""

    def __init__(self, index_path: Path, embedder: Embedder, top_k: int) -> None:
        self._embedder = embedder
        self._top_k = top_k
        self._lock = threading.Lock()
        self._conn = connect(index_path)

    def search(self, query: str) -> list[Excerpt]:
        vector = self._embedder.embed_queries([query])[0]
        if not any(vector):
            raise ValueError("la question ne donne aucun vecteur exploitable (vecteur nul)")
        with self._lock:
            if self._conn is None:
                raise RuntimeError("l'index est fermé")
            rows = self._conn.execute(
                f"SELECT c.id, v.distance, c.doc_id, c.title_fr, c.text FROM {VEC_TABLE} AS v "
                "JOIN chunks AS c ON c.id = v.rowid WHERE v.embedding MATCH ? AND v.k = ? "
                "ORDER BY v.distance, c.id",
                (serialize_vector(vector), self._top_k),
            ).fetchall()
        return [
            Excerpt(
                position=i,
                chunk_id=int(rowid),
                doc_id=doc_id,
                title_fr=title_fr,
                text=text,
                score=score_of(distance),
            )
            for i, (rowid, distance, doc_id, title_fr, text) in enumerate(rows, start=1)
        ]

    def close(self) -> None:
        with self._lock:
            conn, self._conn = self._conn, None
        if conn is not None:
            conn.close()
