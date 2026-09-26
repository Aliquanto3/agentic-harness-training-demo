"""The `Retriever` port (AD-22) and its sqlite-vec strategy (story 15): the `top_k` nearest
chunks to the query, no threshold, scored `1 − cosine distance`."""

from __future__ import annotations

from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Protocol

from wavestack.models.embedding import Embedder
from wavestack.rag.index import VEC_TABLE, connect, serialize_vector


@dataclass(frozen=True)
class Excerpt:
    """A chunk found for a query: its rank (from 1), and its score (3 decimals)."""

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


class SqliteVecRetriever:
    """The nearest chunks of the index, by the embedder's query vector."""

    def __init__(self, index_path: Path, embedder: Embedder, top_k: int) -> None:
        self._path = index_path
        self._embedder = embedder
        self._top_k = top_k

    def search(self, query: str) -> list[Excerpt]:
        vector = self._embedder.embed_queries([query])[0]
        conn = connect(self._path)  # one connection per search: nothing held between turns
        try:
            nearest = conn.execute(
                f"SELECT rowid, distance FROM {VEC_TABLE} WHERE embedding MATCH ? AND k = ? "
                "ORDER BY distance",
                (serialize_vector(vector), self._top_k),
            ).fetchall()
            rows = []
            for rowid, distance in sorted(nearest, key=lambda row: (row[1], row[0])):
                doc_id, title_fr, text = conn.execute(
                    "SELECT doc_id, title_fr, text FROM chunks WHERE id = ?", (rowid,)
                ).fetchone()
                rows.append((rowid, distance, doc_id, title_fr, text))
        finally:
            conn.close()
        return [
            Excerpt(
                position=i,
                chunk_id=int(rowid),
                doc_id=doc_id,
                title_fr=title_fr,
                text=text,
                score=round(1.0 - float(distance), 3),
            )
            for i, (rowid, distance, doc_id, title_fr, text) in enumerate(rows, start=1)
        ]
