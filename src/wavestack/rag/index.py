"""The sqlite-vec index (story 15, AD-22): written offline, read by the RAG brick.

Tables: `meta` (key, value), `chunks` (`id`, `doc_id`, `title_fr`, `position`, `text`) and
the virtual table `chunks_vec` (`vec0`, `float[dims] distance_metric=cosine`), whose rowid
is the chunk's `id`. The index is written into a temporary file, then replaces the old one.
"""

from __future__ import annotations

import os
import sqlite3
from collections.abc import Callable, Sequence
from datetime import UTC, datetime
from pathlib import Path
from typing import NamedTuple

from wavestack.models.embedding import Embedder
from wavestack.rag.corpus import Chunk, RagContent, chunk_corpus

VEC_TABLE = "chunks_vec"


class IndexMeta(NamedTuple):
    embedding_model_id: str
    dims: int
    chunk_max_chars: int
    chunks: int
    built_at: str


class VecUnavailable(Exception):
    """sqlite-vec cannot be loaded into this Python's sqlite3."""


def serialize_vector(vector: Sequence[float]) -> bytes:
    import sqlite_vec

    return sqlite_vec.serialize_float32(list(vector))


def connect(path: Path, *, readonly: bool = True) -> sqlite3.Connection:
    """A connection with sqlite-vec loaded. Raises `VecUnavailable`, or `sqlite3.Error` for
    an unreadable file."""
    if readonly:
        conn = sqlite3.connect(f"{path.resolve().as_uri()}?mode=ro", uri=True)
    else:
        conn = sqlite3.connect(path)
    try:
        load_vec(conn)
    except VecUnavailable:
        conn.close()
        raise
    return conn


def load_vec(conn: sqlite3.Connection) -> None:
    try:
        import sqlite_vec

        conn.enable_load_extension(True)
        sqlite_vec.load(conn)
        conn.enable_load_extension(False)
    except (ImportError, AttributeError, sqlite3.Error) as exc:
        raise VecUnavailable(f"{type(exc).__name__}: {exc}") from exc


def vec_unavailable() -> str | None:
    """Why sqlite-vec cannot be loaded here (its cause), `None` when it can."""
    conn = sqlite3.connect(":memory:")
    try:
        load_vec(conn)
    except VecUnavailable as exc:
        return str(exc)
    finally:
        conn.close()
    return None


def write_index(
    path: Path,
    chunks: Sequence[Chunk],
    vectors: Sequence[Sequence[float]],
    *,
    model_id: str,
    dims: int,
    chunk_max_chars: int,
) -> IndexMeta:
    """Write the index into `path` (a temporary file first, then replaced)."""
    if not chunks:
        raise ValueError("corpus vide : aucun extrait à indexer")
    if len(vectors) != len(chunks) or any(len(v) != dims for v in vectors):
        raise ValueError(f"il faut un vecteur de {dims} dimensions par extrait")
    meta = IndexMeta(
        model_id,
        dims,
        chunk_max_chars,
        len(chunks),
        datetime.now(UTC).isoformat(timespec="seconds"),
    )
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_name(path.name + ".tmp")
    tmp.unlink(missing_ok=True)
    conn = connect(tmp, readonly=False)
    try:
        with conn:
            conn.execute("CREATE TABLE meta (key TEXT PRIMARY KEY, value TEXT NOT NULL)")
            conn.executemany(
                "INSERT INTO meta (key, value) VALUES (?, ?)",
                [(key, str(value)) for key, value in meta._asdict().items()],
            )
            conn.execute(
                "CREATE TABLE chunks (id INTEGER PRIMARY KEY, doc_id TEXT NOT NULL, "
                "title_fr TEXT NOT NULL, position INTEGER NOT NULL, text TEXT NOT NULL)"
            )
            conn.execute(
                f"CREATE VIRTUAL TABLE {VEC_TABLE} USING "
                f"vec0(embedding float[{dims}] distance_metric=cosine)"
            )
            for i, (chunk, vector) in enumerate(zip(chunks, vectors, strict=True), start=1):
                conn.execute(
                    "INSERT INTO chunks (id, doc_id, title_fr, position, text) "
                    "VALUES (?, ?, ?, ?, ?)",
                    (i, chunk.doc_id, chunk.title_fr, chunk.position, chunk.text),
                )
                conn.execute(
                    f"INSERT INTO {VEC_TABLE} (rowid, embedding) VALUES (?, ?)",
                    (i, serialize_vector(vector)),
                )
    finally:
        conn.close()
    os.replace(tmp, path)
    return meta


def read_meta(path: Path) -> IndexMeta:
    """The index's `meta`. Raises `VecUnavailable`, `sqlite3.Error`, `KeyError`, `ValueError`."""
    conn = connect(path)
    try:
        values = dict(conn.execute("SELECT key, value FROM meta").fetchall())
    finally:
        conn.close()
    return IndexMeta(
        embedding_model_id=values["embedding_model_id"],
        dims=int(values["dims"]),
        chunk_max_chars=int(values["chunk_max_chars"]),
        chunks=int(values["chunks"]),
        built_at=values["built_at"],
    )


def read_chunks(path: Path) -> list[Chunk]:
    """Every chunk of the index, in its order."""
    conn = connect(path)
    try:
        rows = conn.execute(
            "SELECT doc_id, title_fr, position, text FROM chunks ORDER BY id"
        ).fetchall()
    finally:
        conn.close()
    return [Chunk(*row) for row in rows]


def longest_chunks(path: Path, n: int) -> list[Chunk]:
    """The `n` longest chunks (in characters): the preview's excerpts (AD-9)."""
    conn = connect(path)
    try:
        rows = conn.execute(
            "SELECT doc_id, title_fr, position, text FROM chunks "
            "ORDER BY length(text) DESC, id LIMIT ?",
            (n,),
        ).fetchall()
    finally:
        conn.close()
    return [Chunk(*row) for row in rows]


def build_index(
    content: RagContent,
    embedder: Embedder,
    path: Path,
    chunk_max_chars: int,
    on_progress: Callable[[int, int], None] | None = None,
) -> IndexMeta:
    """Chunk the corpus, embed every passage with `embedder`, write the index."""
    chunks = chunk_corpus(content, chunk_max_chars)
    if not chunks:
        raise ValueError("corpus vide : aucun extrait à indexer")
    vectors = []
    for i, chunk in enumerate(chunks, start=1):
        vectors += embedder.embed_passages([chunk.text])
        if on_progress is not None:
            on_progress(i, len(chunks))
    return write_index(
        path,
        chunks,
        vectors,
        model_id=embedder.model_id,
        dims=embedder.dims,
        chunk_max_chars=chunk_max_chars,
    )
