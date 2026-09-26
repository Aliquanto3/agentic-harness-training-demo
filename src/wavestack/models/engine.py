"""The `Engine` port and its in-process llama-cpp-python adapter (AD-5).

The port receives token ids already rendered and tokenized by the harness:
no chat format, no token added. Adapters always stream internally and test
the `CancelToken` at every fragment.
"""

from __future__ import annotations

import codecs
import ctypes
import threading
from collections.abc import Iterator, Sequence
from dataclasses import dataclass
from typing import Literal, Protocol

StopReason = Literal["stop", "length", "cancelled", "error"]

# Default sampling, fixed until a story exposes it (Qwen non-thinking recommendations).
TEMPERATURE = 0.7
TOP_P = 0.8
TOP_K = 20


class CancelToken:
    def __init__(self) -> None:
        self._event = threading.Event()

    def cancel(self) -> None:
        self._event.set()

    @property
    def cancelled(self) -> bool:
        return self._event.is_set()

    def wait(self, timeout: float) -> bool:
        """Wait up to `timeout` seconds; `True` as soon as the cancellation arrives."""
        return self._event.wait(timeout)


@dataclass(frozen=True)
class Fragment:
    """Decoded UTF-8 text; the last fragment of a completion carries its `stop_reason`."""

    text: str
    output_tokens: int
    stop_reason: StopReason | None = None


@dataclass(frozen=True)
class EngineMetadata:
    architecture: str | None
    chat_template: str | None
    native_context: int | None
    bos_token: str
    eos_token: str
    special_tokens: tuple[str, ...]
    # A local server's own context (llama-server `n_ctx`), a bound of the window (AD-9).
    server_context: int | None = None


class Engine(Protocol):
    def complete(
        self, prompt_ids: Sequence[int], stop: Sequence[str], max_tokens: int, cancel: CancelToken
    ) -> Iterator[Fragment]: ...

    def tokenize(self, text: str) -> list[int]: ...

    def token_pieces(self, ids: Sequence[int]) -> list[bytes]: ...

    def metadata(self) -> EngineMetadata: ...

    def close(self) -> None: ...


def partial_suffix_len(text: str, markers: Sequence[str]) -> int:
    """Length of the longest end of `text` that could be the start of one of `markers`."""
    return max(
        (k for m in markers for k in range(len(m) - 1, 0, -1) if text.endswith(m[:k])),
        default=0,
    )


def cut_stop(pending: str, stops: Sequence[str]) -> tuple[str, str, bool]:
    """Split `pending` into (safe to emit, held back, stopped) without leaking a stop prefix."""
    hits = [i for s in stops if (i := pending.find(s)) >= 0]
    if hits:
        return pending[: min(hits)], "", True
    keep = partial_suffix_len(pending, stops)
    return pending[: len(pending) - keep], pending[len(pending) - keep :], False


def _int(value: object) -> int:
    try:
        return int(value)  # type: ignore[call-overload]
    except (TypeError, ValueError):
        return 0


class VocabTokenizer:
    """A GGUF's tokenizer, token pieces and metadata (AD-4, AD-5): the single local tokenizer
    code, shared by `LlamaCppEngine` (its loaded model) and `ollama_raw` (the GGUF opened
    `vocab_only`, no weights). `Llama.detokenize` is banned here: its 32-byte buffer
    truncates without error."""

    def __init__(self, model_path: str | None = None, *, model: object | None = None) -> None:
        import llama_cpp

        self._lib = llama_cpp
        self._owned = model is None
        if model is None:
            from llama_cpp import _internals

            if not model_path:
                raise ValueError("aucun fichier GGUF pour le tokenizer")
            params = llama_cpp.llama_model_default_params()
            params.vocab_only = True
            model = _internals.LlamaModel(path_model=model_path, params=params, verbose=False)
        self._model = model
        self._vocab = model.vocab  # type: ignore[attr-defined]
        self._metadata = self._read_metadata()

    def _token_text(self, token: int) -> str:
        if token < 0:
            return ""
        return self._lib.llama_vocab_get_text(self._vocab, token).decode("utf-8", "replace")

    def _read_metadata(self) -> EngineMetadata:
        lib = self._lib
        try:
            meta = self._model.metadata() or {}  # type: ignore[attr-defined]
        except Exception:  # noqa: BLE001 - as `Llama`: metadata unreadable, empty
            meta = {}
        mask = lib.LLAMA_TOKEN_ATTR_CONTROL | lib.LLAMA_TOKEN_ATTR_USER_DEFINED
        special = []
        for token in range(lib.llama_vocab_n_tokens(self._vocab)):
            if lib.llama_vocab_get_attr(self._vocab, token) & mask:
                text = self._token_text(token)
                if len(text) >= 2 and text.strip():
                    special.append(text)
        arch = meta.get("general.architecture")
        # `vocab_only` loads no hyperparameters: `n_ctx_train()` is 0, the GGUF key says it.
        native = self._model.n_ctx_train() or _int(meta.get(f"{arch}.context_length"))  # type: ignore[attr-defined]
        return EngineMetadata(
            architecture=arch,
            chat_template=meta.get("tokenizer.chat_template"),
            native_context=native or None,
            bos_token=self._token_text(lib.llama_vocab_bos(self._vocab)),
            eos_token=self._token_text(lib.llama_vocab_eos(self._vocab)),
            special_tokens=tuple(special),
        )

    def metadata(self) -> EngineMetadata:
        return self._metadata

    def is_eog(self, token: int) -> bool:
        return bool(self._lib.llama_vocab_is_eog(self._vocab, token))

    def tokenize(self, text: str) -> list[int]:
        return self._model.tokenize(text.encode("utf-8"), add_bos=False, special=True)  # type: ignore[attr-defined]

    def token_pieces(self, ids: Sequence[int]) -> list[bytes]:
        pieces = []
        for token in ids:
            buf = ctypes.create_string_buffer(32)
            n = self._lib.llama_token_to_piece(self._vocab, token, buf, len(buf), 0, True)
            if n < 0:  # buffer too small: -n is the size needed
                buf = ctypes.create_string_buffer(-n)
                n = self._lib.llama_token_to_piece(self._vocab, token, buf, len(buf), 0, True)
            pieces.append(buf.raw[:n])
        return pieces

    def close(self) -> None:
        """Frees the model only when this tokenizer opened it (`vocab_only`)."""
        if self._owned:
            self._model.close()  # type: ignore[attr-defined]


class LlamaCppEngine:
    """In-process adapter; its tokenizer is `VocabTokenizer` on the loaded model."""

    def __init__(self, model_path: str, n_ctx: int) -> None:
        import llama_cpp

        self._llm = llama_cpp.Llama(model_path=model_path, n_ctx=n_ctx, verbose=False)
        self._tokenizer = VocabTokenizer(model=self._llm._model)

    def metadata(self) -> EngineMetadata:
        return self._tokenizer.metadata()

    def tokenize(self, text: str) -> list[int]:
        return self._tokenizer.tokenize(text)

    def token_pieces(self, ids: Sequence[int]) -> list[bytes]:
        return self._tokenizer.token_pieces(ids)

    def complete(
        self, prompt_ids: Sequence[int], stop: Sequence[str], max_tokens: int, cancel: CancelToken
    ) -> Iterator[Fragment]:
        decoder = codecs.getincrementaldecoder("utf-8")("replace")
        pending = ""
        count = 0
        reason: StopReason = "stop"
        tokens = self._llm.generate(
            prompt_ids, temp=TEMPERATURE, top_p=TOP_P, top_k=TOP_K, min_p=0.0
        )
        try:
            for token in tokens:
                if cancel.cancelled:
                    reason = "cancelled"
                    break
                if self._tokenizer.is_eog(token):
                    break
                count += 1
                pending += decoder.decode(self.token_pieces([token])[0])
                emit, pending, stopped = cut_stop(pending, stop)
                if stopped:
                    yield Fragment(emit, count, "stop")
                    return
                yield Fragment(emit, count)
                if count >= max_tokens:
                    reason = "length"
                    break
        finally:
            tokens.close()
        yield Fragment(pending + decoder.decode(b"", final=True), count, reason)

    def close(self) -> None:
        self._llm.close()
