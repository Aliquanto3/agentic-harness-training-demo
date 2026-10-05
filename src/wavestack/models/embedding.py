"""The embedding port and its adapter (story 15, AD-8, AD-22).

`[rag.embedding]` names the model; only its `backend`'s adapter exists (story 12's verdict:
`llama_cpp`). Vectors are normalized, so the index's cosine distance is `1 − dot product`.
`llama_cpp` is imported lazily, as in `engine.py`: only `models` imports it.
"""

from __future__ import annotations

import math
from collections.abc import Sequence
from pathlib import Path
from typing import Any, Protocol

from wavestack import config
from wavestack.config import EmbeddingModel
from wavestack.messages import KeyedError


class EmbedderRefused(KeyedError, ValueError):
    """An embedding model that cannot serve (a `ValueError`, as before): keyed (languages
    5/5), `str()` the French, `render(lang)` the session's language."""


class Embedder(Protocol):
    """What the RAG needs from an embedding model: one vector per text, normalized. Queries
    and passages each get their own prefix (the model's convention)."""

    model_id: str
    dims: int

    def embed_queries(self, texts: Sequence[str]) -> list[list[float]]: ...

    def embed_passages(self, texts: Sequence[str]) -> list[list[float]]: ...

    def close(self) -> None: ...


def normalize(vector: Sequence[float]) -> list[float]:
    """The unit vector (a null vector stays null)."""
    norm = math.sqrt(sum(x * x for x in vector))
    return [x / norm for x in vector] if norm else [0.0 for _ in vector]


def model_path(model: EmbeddingModel) -> Path:
    """Where the model loads from: `load_path`, under `models_dir()`."""
    return config.models_dir() / model.load_path


class LlamaCppEmbedder:
    """In-process adapter: `Llama(embedding=True)`, the pooling read from the GGUF, one text
    per call, truncated to `max_tokens` tokens (lot 5c-1: counted in `last_truncated`)."""

    def __init__(self, model: EmbeddingModel, path: Path | None = None) -> None:
        import llama_cpp

        self.model_id = model.id
        self.dims = model.dims
        self._model = model
        n = self.max_tokens = model.max_tokens
        self.last_truncated: int | None = None  # lot 5c-1: of the last call's texts
        self._llm = llama_cpp.Llama(
            model_path=str(path or model_path(model)),
            embedding=True,
            n_ctx=n,
            n_batch=n,
            n_ubatch=n,
            verbose=False,
        )
        found = self._llm.n_embd()
        if found != model.dims:
            self.close()
            raise EmbedderRefused("models.embedding.wrong_dims", found=found, declared=model.dims)
        # One flat vector per text: a GGUF without pooling (`none`) gives one per token.
        probe = self._llm.embed("Exemplia", normalize=False, truncate=True)
        flat = isinstance(probe, list) and all(isinstance(x, int | float) for x in probe)
        if not flat or len(probe) != model.dims:
            self.close()
            raise EmbedderRefused("models.embedding.not_pooled")

    def _embed(self, texts: Sequence[str], prefix: str) -> list[list[float]]:
        """Lot 5c-1: `last_truncated`, how many of `texts` llama.cpp cut at `max_tokens` (it
        tokenizes each as `embed` does, then keeps its first `n_batch` tokens); `None` when the
        tokenizer cannot be read."""
        tokenize = getattr(self._llm, "tokenize", None)
        cut: int | None = 0 if tokenize is not None else None
        vectors = []
        for text in texts:
            full = prefix + text
            if cut is not None:
                try:
                    cut += len(tokenize(full.encode("utf-8"))) > self.max_tokens  # type: ignore[misc]
                except Exception:  # noqa: BLE001 - the count is a note, never a failure
                    cut = None
            vectors.append(normalize(self._llm.embed(full, normalize=False, truncate=True)))
        self.last_truncated = cut
        return vectors

    def embed_queries(self, texts: Sequence[str]) -> list[list[float]]:
        return self._embed(texts, self._model.query_prefix)

    def embed_passages(self, texts: Sequence[str]) -> list[list[float]]:
        return self._embed(texts, self._model.passage_prefix)

    def close(self) -> None:
        llm, self._llm = getattr(self, "_llm", None), None
        if llm is not None:
            llm.close()


def open_embedder(model: EmbeddingModel) -> Embedder:
    """The adapter of the declared `backend` (only `llama_cpp` is accepted by the config)."""
    return LlamaCppEmbedder(model)


def fastembed_dir() -> Path:
    """Story 30: where the RAG workshop's fastembed model lies, copied by hand (never
    downloaded by WaveStack)."""
    return config.models_dir() / "fastembed"


class FastembedEmbedder:
    """Story 30, the RAG workshop's optional embedding model: fastembed (ONNX, no torch),
    imported lazily, opened from `fastembed_dir()` with `local_files_only` (AD-15: it never
    reaches the network). Vectors are normalized, as the llama.cpp adapter's."""

    def __init__(self, model_name: str, dims: int) -> None:
        from fastembed import TextEmbedding

        self.model_id = model_name
        self.dims = dims
        self._model = TextEmbedding(
            model_name=model_name, cache_dir=str(fastembed_dir()), local_files_only=True
        )

    def _vectors(self, rows: Any) -> list[list[float]]:
        vectors = [normalize([float(x) for x in row]) for row in rows]
        if any(len(v) != self.dims for v in vectors):
            raise EmbedderRefused("models.embedding.fastembed_dims", dims=self.dims)
        return vectors

    def embed_queries(self, texts: Sequence[str]) -> list[list[float]]:
        return self._vectors(self._model.query_embed(list(texts)))

    def embed_passages(self, texts: Sequence[str]) -> list[list[float]]:
        return self._vectors(self._model.passage_embed(list(texts)))

    def close(self) -> None:
        self._model = None
