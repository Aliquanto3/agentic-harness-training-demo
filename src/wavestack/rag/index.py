"""The sqlite-vec index (story 15, AD-22): built offline or from the RAG card, read by the
RAG brick.

Tables: `meta` (key, value), `chunks` (`id`, `doc_id`, `title_fr`, `position`, `text`) and
the virtual table `chunks_vec` (`vec0`, `float[dims] distance_metric=cosine`), whose rowid
is the chunk's `id`. `meta` says which model built it (id, dimensions, file size and
sha256) and from which corpus (a hash of its chunks): another model, or a changed corpus,
is detected. The index is written into a temporary file, then replaces the old one.
"""

from __future__ import annotations

import hashlib
import os
import sqlite3
from collections.abc import Callable, Sequence
from datetime import UTC, datetime
from pathlib import Path
from typing import NamedTuple

from wavestack.config import DEFAULT_LANGUAGE
from wavestack.messages import KeyedError, Message
from wavestack.models.embedding import Embedder
from wavestack.rag.corpus import Chunk, RagContent, chunk_corpus

VEC_TABLE = "chunks_vec"


class IndexMeta(NamedTuple):
    embedding_model_id: str
    dims: int
    chunk_max_chars: int
    chunks: int
    built_at: str
    corpus_sha256: str = ""  # `corpus_digest` of the chunks indexed
    model_size: int = 0  # the model file's size and sha256, when known at build time
    model_sha256: str = ""


class VecUnavailable(Exception):
    """sqlite-vec cannot be loaded into this Python's sqlite3."""


class BuildCancelled(KeyedError):
    """The build was stopped (« Arrêter »): nothing is written. `str()` is French, the
    session calls `render(lang)` (languages 5/5)."""

    def __init__(self, *_: object) -> None:
        super().__init__("rag.index.build_cancelled")


# Languages (5/5): a `Message`, French as a `str`, `render(lang)` in another language.
INDEX_IN_USE_FR = Message("rag.index.in_use")
_WINERRORS_IN_USE = (5, 32)  # ERROR_ACCESS_DENIED, ERROR_SHARING_VIOLATION


class IndexInUse(OSError):
    """The system refused to replace the index because another program holds it open
    (lot G): Windows refuses to replace a file an open handle holds. Its message, in
    French, says so; the caller adds what to do (`render(lang)`: in another language)."""

    def __init__(self, *args: object) -> None:
        super().__init__(*(args or (INDEX_IN_USE_FR,)))

    def render(self, lang: str) -> str:
        """The message in `lang` (a `Message` rendered, any other text as it is)."""
        first = self.args[0] if len(self.args) == 1 else None
        return first.render(lang) if isinstance(first, Message) else str(self)


def exception_text(exc: BaseException, lang: str) -> str:
    """An exception's text in `lang` (languages 5/5): a keyed one (`render`), or one whose
    only argument is a `Message`, rendered; any other (a third party's) as `str()`."""
    render = getattr(exc, "render", None)
    if callable(render):
        return str(render(lang))
    if len(exc.args) == 1 and isinstance(exc.args[0], Message):
        return exc.args[0].render(lang)
    return str(exc)


def _held_open(exc: PermissionError, path: Path) -> bool:
    """A refusal to replace `path` that only an open handle explains: Windows' access
    denied or sharing violation (`winerror`, absent elsewhere) on a writable target. A
    read-only target, or any POSIX refusal (an open file never blocks it there), is not."""
    return getattr(exc, "winerror", None) in _WINERRORS_IN_USE and os.access(path, os.W_OK)


def serialize_vector(vector: Sequence[float]) -> bytes:
    import sqlite_vec

    return sqlite_vec.serialize_float32(list(vector))


def corpus_digest(chunks: Sequence[Chunk]) -> str:
    """What identifies the chunks of a corpus: documents, ranks and texts."""
    digest = hashlib.sha256()
    for chunk in chunks:
        digest.update(f"{chunk.doc_id}\x1f{chunk.position}\x1f{chunk.text}\x1e".encode())
    return digest.hexdigest()


def passage_text(chunk: Chunk) -> str:
    """What is embedded for a chunk: its document's title, then its text."""
    return f"{chunk.title_text}\n{chunk.text}"


def file_sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as file:
        for block in iter(lambda: file.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def connect(path: Path, *, readonly: bool = True) -> sqlite3.Connection:
    """A connection with sqlite-vec loaded, usable from any thread (the caller serializes).
    Raises `VecUnavailable`, or `sqlite3.Error` for an unreadable file."""
    if readonly:
        uri = f"{path.resolve().as_uri()}?mode=ro"
        conn = sqlite3.connect(uri, uri=True, check_same_thread=False)
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
    model_size: int = 0,
    model_sha256: str = "",
) -> IndexMeta:
    """Write the index into `path` (a temporary file first, removed on failure). The
    system refusing to replace `path` because it is open elsewhere: `IndexInUse`."""
    if not chunks:
        raise ValueError(Message("rag.index.empty_corpus"))
    if len(vectors) != len(chunks) or any(len(v) != dims for v in vectors):
        raise ValueError(Message("rag.index.wrong_vectors", dims=dims))
    meta = IndexMeta(
        model_id,
        dims,
        chunk_max_chars,
        len(chunks),
        datetime.now(UTC).isoformat(timespec="seconds"),
        corpus_digest(chunks),
        model_size,
        model_sha256,
    )
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_name(path.name + ".tmp")
    tmp.unlink(missing_ok=True)
    try:
        conn = connect(tmp, readonly=False)
        try:
            with conn:
                _fill(conn, meta, chunks, vectors)
        finally:
            conn.close()
        try:
            os.replace(tmp, path)
        except PermissionError as exc:
            if not _held_open(exc, path):
                raise
            raise IndexInUse() from exc
    except BaseException:
        tmp.unlink(missing_ok=True)
        raise
    return meta


def _fill(
    conn: sqlite3.Connection,
    meta: IndexMeta,
    chunks: Sequence[Chunk],
    vectors: Sequence[Sequence[float]],
) -> None:
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
        f"vec0(embedding float[{meta.dims}] distance_metric=cosine)"
    )
    for i, (chunk, vector) in enumerate(zip(chunks, vectors, strict=True), start=1):
        conn.execute(
            "INSERT INTO chunks (id, doc_id, title_fr, position, text) VALUES (?, ?, ?, ?, ?)",
            (i, chunk.doc_id, chunk.title_text, chunk.position, chunk.text),
        )
        conn.execute(
            f"INSERT INTO {VEC_TABLE} (rowid, embedding) VALUES (?, ?)",
            (i, serialize_vector(vector)),
        )


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
        corpus_sha256=values.get("corpus_sha256", ""),
        model_size=int(values.get("model_size") or 0),
        model_sha256=values.get("model_sha256", ""),
    )


def read_chunks(path: Path) -> list[Chunk]:
    """Every chunk of the index, in its order."""
    conn = connect(path)
    try:
        rows = conn.execute(
            "SELECT doc_id, title_fr AS title_text, position, text FROM chunks ORDER BY id"
        ).fetchall()
    finally:
        conn.close()
    return [Chunk(*row) for row in rows]


def longest_chunks(path: Path, n: int) -> list[Chunk]:
    """The `n` longest chunks (in characters): the preview's excerpts (AD-9)."""
    conn = connect(path)
    try:
        rows = conn.execute(
            "SELECT doc_id, title_fr AS title_text, position, text FROM chunks "
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
    *,
    model_file: Path | None = None,
    cancelled: Callable[[], bool] | None = None,
    lang: str = DEFAULT_LANGUAGE,
) -> IndexMeta:
    """Chunk the corpus, embed each passage (title and text) with `embedder`, write the
    index. `model_file`: the model's file, whose size and sha256 go into `meta`.
    `cancelled()` true: `BuildCancelled`, nothing written. `lang`: the corpus's language
    (languages 4/5), `content` being `rag.yaml` read in it (its titles)."""
    chunks = chunk_corpus(content, chunk_max_chars, lang)
    if not chunks:
        raise ValueError(Message("rag.index.empty_corpus"))
    vectors = []
    for i, chunk in enumerate(chunks, start=1):
        if cancelled is not None and cancelled():
            raise BuildCancelled()
        vectors += embedder.embed_passages([passage_text(chunk)])
        if on_progress is not None:
            on_progress(i, len(chunks))
    size, sha = 0, ""
    if model_file is not None:
        size, sha = model_file.stat().st_size, file_sha256(model_file)
    return write_index(
        path,
        chunks,
        vectors,
        model_id=embedder.model_id,
        dims=embedder.dims,
        chunk_max_chars=chunk_max_chars,
        model_size=size,
        model_sha256=sha,
    )
