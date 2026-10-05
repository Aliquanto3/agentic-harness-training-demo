"""The `Engine` port and its in-process llama-cpp-python adapter (AD-5).

The port receives token ids already rendered and tokenized by the harness:
no chat format, no token added. Adapters always stream internally and test
the `CancelToken` at every fragment.
"""

from __future__ import annotations

import codecs
import ctypes
import logging
import threading
from collections.abc import Iterator, Sequence
from dataclasses import dataclass
from typing import Any, Literal, Protocol

from wavestack.messages import Message

StopReason = Literal["stop", "length", "cancelled", "error"]


@dataclass(frozen=True)
class Sampling:
    """Story 29: how the next token is drawn, a parameter of every call (AD-5). llama.cpp's
    chain applies top-k, top-p and min-p to the raw logits, then the temperature."""

    temperature: float
    top_k: int
    top_p: float
    min_p: float


# The harness's own values (Qwen non-thinking recommendations): every workshop call, and the
# « LLM nu » screen until it changes them.
DEFAULT_SAMPLING = Sampling(temperature=0.7, top_k=20, top_p=0.8, min_p=0.0)
# E122 (story 4 of the deferred leftovers): `prefill` evaluates by batches of this many ids,
# and tests its `CancelToken` between two (≈ 4 s each on the target CPU).
PREFILL_BATCH = 128
# The screen's bounds, inclusive (its intention validates them).
SAMPLING_BOUNDS: dict[str, tuple[float, float]] = {
    "temperature": (0.0, 2.0),
    "top_k": (0, 100),  # 0: top-k off (llama.cpp keeps the whole vocabulary)
    "top_p": (0.05, 1.0),
    "min_p": (0.0, 0.5),
}


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
    # Story 29: the token this fragment carries, when the engine knows it (in-process: its id
    # and bytes; a server: the chunk it streamed, as bytes), for the « LLM nu » screen.
    token_id: int | None = None
    piece: bytes | None = None
    # Story 29, increment 4: the token's candidates (`models.candidates`), in-process only,
    # when asked: `{token_id, text, p, kept, p_sampled, chosen}` each.
    candidates: tuple[dict[str, Any], ...] | None = None
    # Story 5 of 2026-09-30: with the candidates, the `candidates.TOP` most probable tokens,
    # `{p, texts, tail}` (`candidates.read_logits`), for the session's memory only (never the
    # journal: the live distribution of the « LLM nu » screen).
    top: dict[str, Any] | None = None


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


@dataclass(frozen=True)
class EngineSnapshot:
    """A copy of an engine's state (AD-11): opaque `data` for `restore`, and what the copy
    weighs in memory (`size_bytes`)."""

    data: Any
    size_bytes: int


class Engine(Protocol):
    def complete(
        self, prompt_ids: Sequence[int], stop: Sequence[str], max_tokens: int, cancel: CancelToken
    ) -> Iterator[Fragment]:
        """Story 29: the adapters also take `*, sampling: Sampling | None = None` (`None`:
        `DEFAULT_SAMPLING`), and the in-process one `candidates: int = 0` (read that many
        candidates with each token, into `Fragment.candidates`); the session passes them only
        when the « LLM nu » screen asks (`candidates` only to a file's engine), so an engine
        with the four arguments alone stays valid."""
        ...

    def tokenize(self, text: str) -> list[int]: ...

    def token_pieces(self, ids: Sequence[int]) -> list[bytes]: ...

    def metadata(self) -> EngineMetadata: ...

    def close(self) -> None: ...

    # Cache and state (AD-4, AD-11). The session tolerates an engine without them.

    def cached_ids(self) -> list[int] | None:
        """The ids the engine holds in its cache now; `None` when it cannot say."""
        ...

    def snapshot(self) -> EngineSnapshot | None:
        """A copy of the engine's state; `None` when it cannot save it."""
        ...

    def restore(self, snapshot: EngineSnapshot) -> bool:
        """Put back a `snapshot`; `False` when it could not."""
        ...

    @property
    def last_evaluated(self) -> int | None:
        """The prompt tokens the last `complete` really evaluated; `None` when unknown."""
        ...

    def prefill(self, ids: Sequence[int], cancel: CancelToken) -> int | None:
        """E122: evaluate `ids` into the cache ahead of a call, by batches of `PREFILL_BATCH`,
        reusing the prefix already there and stopping between two batches once `cancel`
        asks (what was evaluated stays useful). Returns how many ids this call evaluated;
        `None` for an engine that cannot (servers, cloud)."""
        ...

    # Story 29 (« LLM nu »): optional too, the session tolerates an engine without it.

    def dimensions(self) -> dict[str, Any] | None:
        """The model's sizes: `vocab_size`, `embedding_length`, `layer_count`, `head_count`,
        `context_length` (`None` when unknown) and `source_text`, where they were read."""
        ...


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


def common_prefix_len(a: Sequence[int], b: Sequence[int]) -> int:
    """How many ids `a` and `b` share from their start."""
    n = 0
    for x, y in zip(a, b, strict=False):
        if int(x) != int(y):
            break
        n += 1
    return n


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
            # Lot J: opened alone, no `Llama(verbose=False)` has quieted llama.cpp's log, which
            # would print the whole vocabulary load (UnicodeEncodeError on a cp1252 stderr).
            # Errors only: the process-wide level `Llama(verbose=False)` sets for the engine.
            logging.getLogger("llama-cpp-python").setLevel(logging.ERROR)
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

    def vocab_size(self) -> int | None:
        """Story 29: the tokens of the vocabulary, as the tokenizer holds them."""
        return int(self._lib.llama_vocab_n_tokens(self._vocab)) or None

    def is_eog(self, token: int) -> bool:
        return bool(self._lib.llama_vocab_is_eog(self._vocab, token))

    def adds_bos(self) -> int | None:
        """Lot 6 of 2026-10-04: the id of the begin-of-text token this vocabulary asks before
        a text (Gemma, Llama), `None` when it asks none (Qwen) or llama.cpp cannot say."""
        lib = self._lib
        adds = getattr(lib, "llama_vocab_get_add_bos", None)
        if adds is None or not adds(self._vocab):
            return None
        token = int(lib.llama_vocab_bos(self._vocab))
        return None if token in (getattr(lib, "LLAMA_TOKEN_NULL", -1), -1) else token

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

        self._lib = llama_cpp
        self._llm = llama_cpp.Llama(model_path=model_path, n_ctx=n_ctx, verbose=False)
        self._tokenizer = VocabTokenizer(model=self._llm._model)
        self._last_evaluated: int | None = None

    @property
    def last_evaluated(self) -> int | None:
        return self._last_evaluated

    def cached_ids(self) -> list[int] | None:
        """`generate` evaluates only the ids that extend these (the last token sampled is
        not among them)."""
        return [int(t) for t in self._llm.input_ids[: self._llm.n_tokens]]

    def snapshot(self) -> EngineSnapshot | None:
        """`Llama.save_state` without its copy of the logits (`scores`, up to n_batch ×
        vocabulary floats, ≈ 500 Mo for Qwen3.5): only the llama.cpp state and the ids in
        cache, which `generate` needs to reuse it."""
        lib, ctx = self._lib, self._llm.ctx
        size = int(lib.llama_state_get_size(ctx))
        buffer = (ctypes.c_uint8 * size)()
        written = int(lib.llama_state_get_data(ctx, buffer, size))
        if written <= 0 or written > size:
            raise RuntimeError(f"copie de l'état llama.cpp en échec ({written} octets)")
        n_tokens = self._llm.n_tokens
        ids = self._llm.input_ids[:n_tokens].copy()
        return EngineSnapshot((buffer, written, ids, n_tokens), written + int(ids.nbytes))

    def restore(self, snapshot: EngineSnapshot) -> bool:
        """`Llama.load_state`'s steps, without the logits: the next `generate` evaluates at
        least one token again (`_requires_eval`)."""
        buffer, written, ids, n_tokens = snapshot.data
        try:
            restored = int(self._lib.llama_state_set_data(self._llm.ctx, buffer, written))
        except Exception:  # noqa: BLE001 - the state is unknown: treated as a failure
            restored = -1
        if restored != written:
            self._llm.n_tokens = 0  # a state half set is never reused: all evaluated again
            return False
        self._llm.input_ids[:n_tokens] = ids
        self._llm.n_tokens = n_tokens
        self._llm._requires_eval = True
        return True

    def prefill(self, ids: Sequence[int], cancel: CancelToken) -> int | None:
        """E122: `Llama.eval` by batches of `PREFILL_BATCH`, after the cache is brought back
        to its common prefix with `ids` (cut when the memory allows it, as `generate` does;
        else `reset`, since a hybrid model cannot truncate its state). `eval` leaves
        `_requires_eval` false, and the next `generate` evaluates only the ids that extend
        what is in cache."""
        llm = self._llm
        wanted = [int(t) for t in ids]
        common = common_prefix_len(llm.input_ids[: llm.n_tokens], wanted)
        if common == len(wanted):
            return 0  # every id asked is in cache already: nothing to cut nor to evaluate
        if common < llm.n_tokens:  # the cache goes further: cut it, or start over
            if common > 0 and llm._ctx.kv_cache_seq_rm(-1, common, -1):
                llm.n_tokens = common
            else:
                llm.reset()
                common = 0
        evaluated = 0
        try:
            for start in range(common, len(wanted), PREFILL_BATCH):
                if cancel.cancelled:
                    break
                batch = wanted[start : start + PREFILL_BATCH]
                llm.eval(batch)
                evaluated += len(batch)
        finally:
            # llama.cpp books the tokens decoded into its counters at its next
            # synchronization (a logits read): done here, so that they are not counted as
            # prompt tokens of the next `complete` (`last_evaluated`, AD-4).
            self._lib.llama_synchronize(llm.ctx)
        return evaluated

    def metadata(self) -> EngineMetadata:
        return self._tokenizer.metadata()

    def dimensions(self) -> dict[str, Any] | None:
        """Story 29: the loaded model's sizes, from llama.cpp itself."""
        lib, model = self._lib, self._llm._model

        def size(value: object) -> int | None:
            return _int(value) or None

        return {
            "vocab_size": self._tokenizer.vocab_size(),
            "embedding_length": size(lib.llama_model_n_embd(model.model)),
            "layer_count": size(lib.llama_model_n_layer(model.model)),
            "head_count": size(lib.llama_model_n_head(model.model)),
            "context_length": size(model.n_ctx_train()),
            # A `Message` (French as a text), rendered by the session in its language.
            "source_text": Message("models.engine.dimensions_source"),
        }

    def tokenize(self, text: str) -> list[int]:
        return self._tokenizer.tokenize(text)

    def adds_bos(self) -> int | None:
        return self._tokenizer.adds_bos()

    def token_pieces(self, ids: Sequence[int]) -> list[bytes]:
        return self._tokenizer.token_pieces(ids)

    def complete(
        self,
        prompt_ids: Sequence[int],
        stop: Sequence[str],
        max_tokens: int,
        cancel: CancelToken,
        *,
        sampling: Sampling | None = None,
        candidates: int = 0,
    ) -> Iterator[Fragment]:
        """`candidates` (story 29): the number of most probable tokens to read with each
        token, from the logits of the position it was drawn from (the last one: never
        `logits_all`, which would hold n_ctx × vocabulary floats)."""
        s = sampling or DEFAULT_SAMPLING
        decoder = codecs.getincrementaldecoder("utf-8")("replace")
        pending = ""
        count = 0
        reason: StopReason = "stop"
        self._last_evaluated = None
        self._lib.llama_perf_context_reset(self._llm.ctx)
        tokens = self._llm.generate(
            prompt_ids, temp=s.temperature, top_p=s.top_p, top_k=s.top_k, min_p=s.min_p
        )
        try:
            for token in tokens:
                if cancel.cancelled:
                    reason = "cancelled"
                    break
                if self._tokenizer.is_eog(token):
                    break
                count += 1
                piece = self.token_pieces([token])[0]
                read, top = (
                    self._candidates(int(token), s, candidates) if candidates else (None, None)
                )
                pending += decoder.decode(piece)
                emit, pending, stopped = cut_stop(pending, stop)
                if stopped:
                    yield Fragment(emit, count, "stop", int(token), piece, read, top)
                    return
                yield Fragment(
                    emit, count, token_id=int(token), piece=piece, candidates=read, top=top
                )
                if count >= max_tokens:
                    reason = "length"
                    break
        finally:
            tokens.close()
            # The prompt tokens evaluated, the ones reused from the cache excluded (AD-4).
            self._last_evaluated = int(self._lib.llama_perf_context(self._llm.ctx).n_p_eval)
        yield Fragment(pending + decoder.decode(b"", final=True), count, reason)

    def _candidates(
        self, token: int, sampling: Sampling, n: int
    ) -> tuple[tuple[dict[str, Any], ...], dict[str, Any]]:
        """Story 29: when `generate` yields a token, the context still holds the logits it
        was drawn from: `n_vocab()` floats of the last position, read in place. Story 5 of
        2026-09-30: with its `n` candidates, the `candidates.TOP` most probable tokens."""
        import numpy as np  # installed with llama-cpp-python

        from wavestack.models.candidates import read_logits

        pointer = self._lib.llama_get_logits_ith(self._llm.ctx, -1)
        logits = np.ctypeslib.as_array(pointer, shape=(self._llm.n_vocab(),))
        return read_logits(logits, sampling, token, n, self.token_pieces)

    def close(self) -> None:
        self._llm.close()
