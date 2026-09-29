"""Adapters of an already-running local server: `llama_server` and `ollama_raw` (AD-5, AD-8).

WaveStack never launches, installs nor stops Ollama or llama-server; it only talks to them at
the loopback addresses of `[net.loopback_ports]`, through `net`'s loopback client (no proxy,
any other host refused, AD-15). Both adapters stay in rendered-text mode (AD-4): the harness
builds the whole text, template included; nothing goes through the servers' chat format.

- `llama_server` receives the token ids (`/completion`); its tokenizer is the server's own
  (`/tokenize` with pieces), so the gauge counts exactly the ids it sends.
- `ollama_raw` receives the rendered text (`/api/generate`, `raw: true`), rebuilt from the
  ids' own pieces (control 6 of AD-4 makes it `rendered.prompt`), with `num_ctx` the
  session's effective window; its tokenizer is the model's GGUF opened `vocab_only`
  (`VocabTokenizer`). More prompt tokens read by Ollama than the harness counted, or a
  `thinking` field, is reported as « transparence réduite »; fewer is Ollama's cache.

Sampling: the call's (`engine.Sampling`, story 29; the harness's defaults unless the « LLM
nu » screen gives its own), and the penalties llama-cpp-python's
`generate` leaves neutral, sent explicitly (Ollama's own default `repeat_penalty` is 1.1). No
seed is sent: the in-process engine draws a random one too.
"""

from __future__ import annotations

import json
import re
import socket
import threading
from collections.abc import Iterator, Sequence
from contextlib import contextmanager
from dataclasses import dataclass
from importlib.metadata import PackageNotFoundError, version
from pathlib import Path
from typing import Any, Protocol

import httpx

from wavestack import config
from wavestack.models import gguf_meta, probe
from wavestack.models.engine import (
    DEFAULT_SAMPLING,
    CancelToken,
    EngineMetadata,
    EngineSnapshot,
    Fragment,
    Sampling,
    StopReason,
    VocabTokenizer,
    cut_stop,
)
from wavestack.net.factory import create_loopback_client
from wavestack.trace.journal import get_journal

PROVIDERS = {"ollama": "Ollama", "llama_server": "llama-server"}
DISCOVERY_TIMEOUT_S = 1.0  # probing a server at the diagnostic: never a long wait
# Unloading an Ollama model: WaveStack's shutdown never waits on a stuck server for long.
RELEASE_TIMEOUT = httpx.Timeout(10.0, connect=2.0)
_PROBE_PATHS = {"ollama": "/api/tags", "llama_server": "/health"}
_CANCEL_POLL_S = 0.1
# The template's own markers (`<|im_start|>`, `<tool_call>`, `<think>`…): a server's
# vocabulary may hold them as single tokens, neutralized in untrusted text (AD-4, step 2).
_TEMPLATE_MARKERS = re.compile(r"<\|[^|<>\s]{1,40}\|>|</?[a-z_]{2,30}>")
_RESPONSE_ERRORS = (ValueError, TypeError, AttributeError, KeyError, IndexError)


class ServerError(Exception):
    """A local server unreachable, or refusing the request: the French message names its
    address and the cause (AD-16)."""

    def __init__(self, url: str, cause: str) -> None:
        self.url, self.cause = url, cause
        self.message_fr = f"Serveur local injoignable ({url}) : {cause}"
        super().__init__(self.message_fr)


class Tokenizer(Protocol):
    def tokenize(self, text: str) -> list[int]: ...

    def token_pieces(self, ids: Sequence[int]) -> list[bytes]: ...

    def metadata(self) -> EngineMetadata: ...

    def close(self) -> None: ...


def _cause(exc: httpx.HTTPError) -> str:
    if isinstance(exc, httpx.ConnectError):
        return "connexion refusée (serveur arrêté ?)"
    if isinstance(exc, httpx.TimeoutException):
        return "délai dépassé"
    return f"{type(exc).__name__}: {exc}"


# Tests only: the transport every adapter uses when none is given (pytest sets one that
# refuses every connection, so no real local server is ever reached).
default_transport: httpx.BaseTransport | None = None


def _client(
    connect_timeout_s: float, read_timeout_s: float, transport: httpx.BaseTransport | None
) -> httpx.Client:
    timeout = httpx.Timeout(read_timeout_s, connect=connect_timeout_s)
    return create_loopback_client(timeout=timeout, transport=transport or default_transport)


def _json(
    client: httpx.Client,
    base: str,
    method: str,
    path: str,
    body: Any = None,
    timeout: httpx.Timeout | None = None,
) -> dict[str, Any]:
    """A JSON object from the server; anything else (unreachable, HTTP error, not JSON, not
    an object) is a `ServerError`."""
    try:
        extra = {"timeout": timeout} if timeout is not None else {}
        response = client.request(method, base + path, json=body, **extra)
    except httpx.HTTPError as exc:
        raise ServerError(base, _cause(exc)) from exc
    if response.status_code >= 400:
        raise ServerError(base, f"HTTP {response.status_code} : {response.text[:200]}")
    try:
        data = response.json()
    except ValueError as exc:
        raise ServerError(base, f"réponse illisible sur {path}") from exc
    if not isinstance(data, dict):
        raise ServerError(base, f"réponse illisible sur {path}")
    return data


def _abort(response: httpx.Response) -> None:
    """Unblocks a read in progress on `response` from another thread: the socket is shut
    down (a plain close would leave the reader waiting until its timeout), then the
    response is closed."""
    stream = response.extensions.get("network_stream")
    sock = stream.get_extra_info("socket") if stream is not None else None
    if isinstance(sock, socket.socket):
        try:
            sock.shutdown(socket.SHUT_RDWR)
        except OSError:
            pass
    try:
        response.close()
    except Exception:  # noqa: BLE001 - closing from another thread: best effort
        pass


@contextmanager
def _stream(
    client: httpx.Client, base: str, path: str, body: Any, cancel: CancelToken
) -> Iterator[httpx.Response]:
    """A streamed POST, closed on exit. Cancelling closes it at once, even while the server
    has sent nothing yet (Ollama loading its model): a watcher thread aborts the read. HTTP
    errors, before or during the stream, become `ServerError`."""
    try:
        with client.stream("POST", base + path, json=body) as response:
            if response.status_code >= 400:
                response.read()
                raise ServerError(base, f"HTTP {response.status_code} : {response.text[:200]}")
            done = threading.Event()

            def watch() -> None:
                while not done.is_set():
                    if cancel.wait(_CANCEL_POLL_S):
                        _abort(response)
                        return

            threading.Thread(target=watch, daemon=True, name="wavestack-cancel").start()
            try:
                yield response
            finally:
                done.set()
    except httpx.HTTPError as exc:
        raise ServerError(base, _cause(exc)) from exc


def _lines(
    response: httpx.Response, base: str, cancel: CancelToken, prefix: str = ""
) -> Iterator[dict]:
    """The stream's JSON objects (`prefix`: `data:` for SSE). `[DONE]` and blank lines are
    skipped; any other line that is not a JSON object is a `ServerError`. A read error once
    cancelled simply ends the stream."""
    try:
        for raw in response.iter_lines():
            line = raw.strip()
            if prefix:
                if not line.startswith(prefix):
                    continue
                line = line[len(prefix) :].strip()
            if not line or line == "[DONE]":
                continue
            try:
                data = json.loads(line)
            except ValueError as exc:
                raise ServerError(base, f"flux illisible : {line[:80]}") from exc
            if not isinstance(data, dict):
                raise ServerError(base, f"flux illisible : {line[:80]}")
            yield data
    except (httpx.HTTPError, httpx.StreamError, RuntimeError, OSError) as exc:
        if cancel.cancelled:
            return
        raise ServerError(
            base, _cause(exc) if isinstance(exc, httpx.HTTPError) else str(exc)
        ) from exc


def _header_dimensions(path: str | None) -> dict[str, int | None]:
    """Story 29: a GGUF header's sizes (`gguf_meta.dimensions_from_header`), when `path` is
    a readable file of this disk; nothing otherwise."""
    local = path if path and Path(path).is_absolute() else None
    meta = gguf_meta.try_read_metadata(local)
    sizes = gguf_meta.dimensions_from_header(meta) if meta else {}
    return {name: value for name, value in sizes.items() if value is not None}


def _positive(value: Any) -> int | None:
    try:
        n = int(value)
    except (TypeError, ValueError):
        return None
    return n if n > 0 else None


def _sampling(sampling: Sampling | None = None) -> dict[str, float | int]:
    """The call's sampling (story 29; `None`: the harness's defaults, `DEFAULT_SAMPLING`), and
    the penalties llama-cpp-python's `generate` leaves neutral."""
    s = sampling or DEFAULT_SAMPLING
    return {
        "temperature": s.temperature,
        "top_p": s.top_p,
        "top_k": s.top_k,
        "min_p": s.min_p,
        "repeat_penalty": 1.0,
        "presence_penalty": 0.0,
        "frequency_penalty": 0.0,
    }


def _file_name(path: str) -> str:
    """The file name of a path written by the server's OS (`C:\\…\\x.gguf` or `/…/x.gguf`)."""
    return re.split(r"[\\/]", path.rstrip("\\/"))[-1]


def _reduced(message_fr: str, cause: str) -> None:
    get_journal().emit(
        "harness_error",
        {
            "message_fr": message_fr,
            "cause": cause,
            "effect_fr": (
                "Le tour continue. La jauge affiche le compte du harnais, qui n'est plus "
                "exactement ce que le serveur a lu."
            ),
        },
    )


def _interrupted(base: str) -> ServerError:
    return ServerError(base, "flux interrompu avant la fin de la réponse")


class LlamaServerEngine:
    """`llama_server` (AD-5): the ids by `/completion`; tokenizer, pieces and metadata from
    the server itself (`/tokenize`, `/props`, `/v1/models`)."""

    def __init__(
        self,
        url: str,
        *,
        markers: Sequence[str] = (),
        connect_timeout_s: float = 2.0,
        read_timeout_s: float = 300.0,
        transport: httpx.BaseTransport | None = None,
    ) -> None:
        self.url = url.rstrip("/")
        self._client = _client(connect_timeout_s, read_timeout_s, transport)
        self._pieces: dict[int, bytes] = {}  # id -> bytes, filled by `tokenize`
        self._last_evaluated: int | None = None
        # Story 29: what `/v1/models` and `/props` say of the model's sizes and file.
        self._sizes: dict[str, Any] = {}
        self._model_path: str | None = None
        try:
            self._metadata = self._read_metadata(markers)
        except BaseException:
            self._client.close()
            raise

    def _read_metadata(self, markers: Sequence[str]) -> EngineMetadata:
        props = _json(self._client, self.url, "GET", "/props")
        try:
            models = _json(self._client, self.url, "GET", "/v1/models")
        except ServerError:
            models = {}
        data = models.get("data")
        first = data[0] if isinstance(data, list) and data and isinstance(data[0], dict) else {}
        meta = first.get("meta") if isinstance(first.get("meta"), dict) else {}
        # Story 29: the real llama-server gives its vocabulary and embedding size there.
        self._sizes = {
            "vocab_size": _positive(meta.get("n_vocab")),
            "embedding_length": _positive(meta.get("n_embd")),
            "context_length": _positive(meta.get("n_ctx_train")),
        }
        self._model_path = str(props.get("model_path") or "") or None
        template = str(props.get("chat_template") or "") or None
        bos, eos = str(props.get("bos_token") or ""), str(props.get("eos_token") or "")
        special = [t for t in (bos, eos) if t]
        # AD-4, step 2: the configured markers and the template's own, when the server's
        # vocabulary holds them as one token (as the in-process vocabulary says).
        found = _TEMPLATE_MARKERS.findall(template or "")
        for marker in dict.fromkeys([*markers, *found]):
            if marker not in special and len(self.tokenize(marker)) == 1:
                special.append(marker)
        return EngineMetadata(
            architecture=None,  # not exposed: the family is read from the template (AD-6)
            chat_template=template,
            native_context=_positive(meta.get("n_ctx_train")),
            bos_token=bos,
            eos_token=eos,
            special_tokens=tuple(special),
            server_context=_server_n_ctx(props),
        )

    def metadata(self) -> EngineMetadata:
        return self._metadata

    def dimensions(self) -> dict[str, Any] | None:
        """Story 29: vocabulary and embedding size from `/v1/models` (the server's own
        tokenizer and model), layers and heads from the GGUF header of the file it loaded,
        when that file is on this disk."""
        names = {
            "vocab_size": "vocabulaire",
            "embedding_length": "dimension",
            "layer_count": "couches",
            "head_count": "têtes",
            "context_length": "contexte natif",
        }
        served = {k: v for k, v in self._sizes.items() if v is not None}
        header = {k: v for k, v in _header_dimensions(self._model_path).items() if k not in served}
        said = []
        if served:
            listed = ", ".join(names[k] for k in names if k in served)
            said.append(f"{listed.capitalize()} donnés par llama-server (/v1/models)")
        if header:
            listed = ", ".join(names[k] for k in names if k in header)
            said.append(f"{listed} lus dans l'en-tête GGUF de son fichier")
        else:
            said.append(
                "le fichier du modèle, ouvert par llama-server, n'est pas lisible depuis WaveStack"
            )
        source_fr = " ; ".join(said)
        return served | header | {"source_fr": source_fr[0].upper() + source_fr[1:] + "."}

    # AD-4, AD-11: no access to the server's cache nor to its state.

    def cached_ids(self) -> list[int] | None:
        return None

    def snapshot(self) -> EngineSnapshot | None:
        return None

    def restore(self, snapshot: EngineSnapshot) -> bool:
        return False

    @property
    def last_evaluated(self) -> int | None:
        """The prompt tokens the server says it evaluated in the last call, if it said."""
        return self._last_evaluated

    def tokenize(self, text: str) -> list[int]:
        body = {"content": text, "add_special": False, "parse_special": True, "with_pieces": True}
        data = _json(self._client, self.url, "POST", "/tokenize", body)
        ids: list[int] = []
        try:
            for item in data.get("tokens") or []:
                if isinstance(item, dict):
                    token = int(item["id"])
                    piece = item.get("piece")
                    if isinstance(piece, str):  # valid UTF-8 on its own
                        self._pieces[token] = piece.encode("utf-8")
                    elif isinstance(piece, list):  # a partial UTF-8 sequence: its bytes
                        self._pieces[token] = bytes(int(b) for b in piece)
                else:
                    token = int(item)
                ids.append(token)
        except _RESPONSE_ERRORS as exc:
            raise ServerError(self.url, "réponse illisible sur /tokenize") from exc
        return ids

    def token_pieces(self, ids: Sequence[int]) -> list[bytes]:
        for token in dict.fromkeys(t for t in ids if t not in self._pieces):
            # Not seen by `tokenize`: `/detokenize`, once per id. A partial UTF-8 piece
            # comes back as U+FFFD: refused, never cached as wrong bytes.
            data = _json(self._client, self.url, "POST", "/detokenize", {"tokens": [token]})
            content = str(data.get("content") or "")
            if "\ufffd" in content:
                raise ServerError(self.url, f"pièce du token {token} illisible par /detokenize")
            self._pieces[token] = content.encode("utf-8")
        return [self._pieces[t] for t in ids]

    def complete(
        self,
        prompt_ids: Sequence[int],
        stop: Sequence[str],
        max_tokens: int,
        cancel: CancelToken,
        *,
        sampling: Sampling | None = None,
    ) -> Iterator[Fragment]:
        body = {
            "prompt": list(prompt_ids),
            "n_predict": max_tokens,
            "stop": list(stop),
            "stream": True,
            "cache_prompt": True,
            **_sampling(sampling),
        }
        pending = ""
        count = 0
        reason: StopReason | None = None
        self._last_evaluated = None
        with _stream(self._client, self.url, "/completion", body, cancel) as response:
            for data in _lines(response, self.url, cancel, prefix="data:"):
                if cancel.cancelled:
                    break
                if data.get("error"):
                    raise ServerError(self.url, str(data["error"])[:200])
                text = str(data.get("content") or "")
                if text:
                    count += 1
                count = _positive(data.get("tokens_predicted")) or count
                pending += text
                emit, pending, stopped = cut_stop(pending, stop)
                if stopped:
                    yield Fragment(emit, count, "stop", piece=text.encode("utf-8"))
                    return
                if text:
                    yield Fragment(emit, count, piece=text.encode("utf-8"))
                if data.get("stop"):
                    reason = "length" if data.get("stop_type") == "limit" else "stop"
                    timings = data.get("timings")  # its last chunk: `prompt_n` evaluated
                    if isinstance(timings, dict) and isinstance(timings.get("prompt_n"), int):
                        self._last_evaluated = timings["prompt_n"]
                    break
        if cancel.cancelled:
            reason = "cancelled"
        if reason is None:
            raise _interrupted(self.url)
        yield Fragment(pending, count, reason)

    def close(self) -> None:
        self._client.close()


class OllamaRawEngine:
    """`ollama_raw` (AD-5): the rendered text by `/api/generate` in `raw` mode, `num_ctx` the
    session's effective window (`use_window`); tokenizer, pieces and metadata from the GGUF
    opened `vocab_only`. `unload`: Ollama had not loaded this model when it was chosen, so
    leaving it unloads it (`keep_alive: 0`) — never a model another client had loaded."""

    def __init__(
        self,
        url: str,
        name: str,
        gguf_path: str | None,
        n_ctx: int,
        *,
        tokenizer: Tokenizer | None = None,
        unload: bool = True,
        connect_timeout_s: float = 2.0,
        read_timeout_s: float = 300.0,
        transport: httpx.BaseTransport | None = None,
    ) -> None:
        self.url, self.name = url.rstrip("/"), name
        self._gguf_path = gguf_path  # story 29: its header gives the model's sizes
        self._tokenizer = tokenizer if tokenizer is not None else _open_tokenizer(gguf_path)
        self.num_ctx = n_ctx  # until the session gives its effective window
        self._unload = unload
        self._used = False  # a generation was asked: Ollama may have loaded the model
        self._client = _client(connect_timeout_s, read_timeout_s, transport)
        self._closed = False
        self._last_evaluated: int | None = None

    def use_window(self, window: int) -> None:
        """AD-9: the session's effective window, the single source of `num_ctx`."""
        self.num_ctx = window

    def metadata(self) -> EngineMetadata:
        return self._tokenizer.metadata()

    def dimensions(self) -> dict[str, Any] | None:
        """Story 29: the vocabulary from the GGUF's tokenizer (`vocab_only`), the other
        sizes from its header, read in pure Python."""
        vocab_size = getattr(self._tokenizer, "vocab_size", None)
        dims: dict[str, Any] = dict(_header_dimensions(self._gguf_path))
        dims["vocab_size"] = vocab_size() if callable(vocab_size) else None
        return dims | {
            "source_fr": (
                "Vocabulaire lu par le tokenizer du fichier GGUF d'Ollama ; dimensions lues "
                "dans son en-tête."
            )
        }

    # AD-4, AD-11: no access to the server's cache nor to its state.

    def cached_ids(self) -> list[int] | None:
        return None

    def snapshot(self) -> EngineSnapshot | None:
        return None

    def restore(self, snapshot: EngineSnapshot) -> bool:
        return False

    @property
    def last_evaluated(self) -> int | None:
        """The prompt tokens the server says it evaluated in the last call, if it said."""
        return self._last_evaluated

    def tokenize(self, text: str) -> list[int]:
        return self._tokenizer.tokenize(text)

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
    ) -> Iterator[Fragment]:
        prompt = b"".join(self.token_pieces(prompt_ids)).decode("utf-8")
        body = {
            "model": self.name,
            "prompt": prompt,
            "raw": True,
            "stream": True,
            "options": {
                "num_ctx": self.num_ctx,
                "num_predict": max_tokens,
                "stop": list(stop),
                **_sampling(sampling),
            },
        }
        pending = ""
        count = 0
        reason: StopReason | None = None
        stopped = thinking = False
        self._used = True
        self._last_evaluated = None
        with _stream(self._client, self.url, "/api/generate", body, cancel) as response:
            for data in _lines(response, self.url, cancel):
                if cancel.cancelled:
                    break
                if data.get("error"):
                    raise ServerError(self.url, str(data["error"])[:200])
                if data.get("thinking") and not thinking:  # once per call
                    thinking = True
                    _reduced(
                        "Transparence réduite : Ollama a renvoyé un champ « thinking » en mode "
                        "raw ; ce raisonnement, séparé par Ollama, n'est pas dans la sortie "
                        "brute que lit le harnais.",
                        "champ thinking reçu",
                    )
                text = str(data.get("response") or "")
                if text:
                    count += 1
                if text and not stopped:
                    pending += text
                    emit, pending, stopped = cut_stop(pending, stop)
                    yield Fragment(emit, count, piece=text.encode("utf-8"))
                if data.get("done"):
                    count = _positive(data.get("eval_count")) or count
                    reason = (
                        "length" if not stopped and data.get("done_reason") == "length" else "stop"
                    )
                    evaluated = data.get("prompt_eval_count")
                    if isinstance(evaluated, int):
                        self._last_evaluated = evaluated
                    self._check_count(evaluated, len(prompt_ids))
                    break
        if cancel.cancelled:
            reason = "cancelled"
        if reason is None:
            raise _interrupted(self.url)
        yield Fragment(pending, count, reason)

    def _check_count(self, evaluated: Any, counted: int) -> None:
        """More tokens read than the harness counted: Ollama tokenized the text its own way
        (« transparence réduite »). Fewer: the start of the prompt came from its cache, an
        information only."""
        if not isinstance(evaluated, int) or evaluated == counted:
            return
        if evaluated > counted:
            _reduced(
                f"Transparence réduite : Ollama a lu {evaluated} tokens de prompt, le harnais "
                f"en a compté {counted}. Ollama a tokenisé le texte à sa façon (par exemple "
                "en ajoutant un token de début).",
                f"prompt_eval_count = {evaluated}, harnais = {counted}",
            )
            return
        get_journal().emit(
            "server_cache_used",
            {
                "prompt_tokens": counted,
                "evaluated_tokens": evaluated,
                "message_fr": (
                    f"Ollama n'a relu que {evaluated} tokens sur {counted} : le début du "
                    "prompt venait de son cache (préfixe identique à l'appel précédent)."
                ),
            },
        )

    def close(self) -> None:
        """AD-8: leaving an Ollama model WaveStack made it load unloads it (`keep_alive: 0`);
        a failure is traced, never blocking."""
        if self._closed:
            return
        self._closed = True
        try:
            if self._unload and self._used:
                error = release_ollama(self.url, self.name, client=self._client)
                if error is not None:
                    get_journal().emit(
                        "harness_error",
                        {
                            "message_fr": f"Ollama n'a pas déchargé le modèle {self.name}.",
                            "cause": error,
                            "effect_fr": (
                                "WaveStack continue ; Ollama le déchargera de lui-même après "
                                "son délai d'inactivité."
                            ),
                        },
                    )
        finally:
            self._client.close()
            self._tokenizer.close()


class TokenizerRefused(ValueError):
    """Lot E (E6): llama-cpp-python refused a served model's GGUF. `reason_fr` in French,
    `detail` the loader's own message (a technical detail, never the reason)."""

    def __init__(self, reason_fr: str, detail: str) -> None:
        super().__init__(reason_fr)
        self.reason_fr, self.detail = reason_fr, detail


def _open_tokenizer(gguf_path: str | None) -> VocabTokenizer:
    """The GGUF's tokenizer, `vocab_only`; a refusal of llama-cpp-python becomes a French
    reason that names the way out (llama-server tokenizes by itself), its own message kept
    as the detail."""
    try:
        return VocabTokenizer(gguf_path)
    except Exception as exc:  # noqa: BLE001 - any refusal of the native loader
        try:
            lib = f"llama-cpp-python {version('llama-cpp-python')}"
        except PackageNotFoundError:
            lib = "llama-cpp-python"
        raise TokenizerRefused(
            f"{lib} ne sait pas lire le tokenizer de ce modèle (certains modèles "
            "récents d'Ollama) : servez-le plutôt avec llama-server, qui tokenise lui-même.",
            str(exc),
        ) from exc


def release_ollama(
    url: str,
    name: str,
    *,
    client: httpx.Client | None = None,
    transport: httpx.BaseTransport | None = None,
) -> str | None:
    """`POST /api/generate {model, keep_alive: 0}`: Ollama unloads `name` now. Returns the
    cause of a failure, else `None`."""
    own = client is None
    client = client or _client(2.0, 10.0, transport)
    body = {"model": name, "keep_alive": 0}
    try:
        _json(client, url.rstrip("/"), "POST", "/api/generate", body, timeout=RELEASE_TIMEOUT)
    except ServerError as exc:
        return exc.cause
    finally:
        if own:
            client.close()
    return None


# ---------- discovery (AD-7) and cost (AD-8) ----------


@dataclass
class ServedModel:
    """One model an already-running server serves."""

    engine: str  # ollama | llama_server
    server_url: str
    name: str  # Ollama `model:tag`; llama-server: its file name
    ref: str  # `ollama/{name}` or `llama_server/{file}`
    model_path: str | None = None  # llama-server: the file it loaded (`/props`)
    size: int | None = None  # bytes the server reports for the model file
    # Already in memory when listed: llama-server always; Ollama once in `/api/ps`, with
    # the memory it reports there (`resident_size`).
    resident: bool = False
    resident_size: int | None = None
    # Lot E (E1): llama-server's whole context (`/props`), whose KV cache it reserved at
    # launch, and one slot's (`-np N` shares the whole between N slots).
    n_ctx: int | None = None
    slot_ctx: int | None = None
    # Story 25, read from the answers already fetched, never by another request: Ollama's
    # `details` in `/api/tags` (`family`, `parameter_size`); llama-server's template
    # (`/props`) and training context (`/v1/models`), the model table's capabilities.
    family: str | None = None
    parameter_size: str | None = None
    chat_template: str | None = None
    n_ctx_train: int | None = None

    @property
    def provider(self) -> str:
        return PROVIDERS[self.engine]


def _ollama_cloud(model: dict[str, Any]) -> bool:
    """An Ollama « cloud » model runs on ollama.com's servers, never on this workstation."""
    name = str(model.get("name") or model.get("model") or "")
    return bool(model.get("remote_host") or model.get("remote_model")) or name.endswith("-cloud")


def _served_by(client: httpx.Client, engine: str, url: str) -> list[ServedModel]:
    if engine == "ollama":
        tags = _json(client, url, "GET", "/api/tags")
        try:
            running = _json(client, url, "GET", "/api/ps").get("models") or []
        except ServerError:
            running = []
        loaded = {
            str(m.get("name") or m.get("model")): _positive(m.get("size"))
            for m in running
            if isinstance(m, dict)
        }
        served = []
        for model in tags.get("models") or []:
            name = str(model.get("name") or model.get("model") or "")
            if not name or _ollama_cloud(model):
                continue
            details = model.get("details")
            details = details if isinstance(details, dict) else {}
            served.append(
                ServedModel(
                    engine,
                    url,
                    name,
                    f"ollama/{name}",
                    size=_positive(model.get("size")),
                    resident=name in loaded,
                    resident_size=loaded.get(name),
                    family=_text(details.get("family")),
                    parameter_size=_text(details.get("parameter_size")),
                )
            )
        return served
    health = client.get(url + _PROBE_PATHS[engine])
    if health.status_code >= 400:  # 503: still loading its model, nothing to choose yet
        return []
    props = _json(client, url, "GET", "/props")
    try:
        models = _json(client, url, "GET", "/v1/models")
    except ServerError:
        models = {}
    first = (models.get("data") or [{}])[0] or {}
    model_path = str(props.get("model_path") or "") or None
    name = _file_name(model_path) if model_path else str(first.get("id") or "modèle")
    meta = first.get("meta") if isinstance(first.get("meta"), dict) else {}
    size = _positive(meta.get("size"))
    return [
        ServedModel(
            engine,
            url,
            name,
            f"llama_server/{name}",
            model_path,
            size,
            True,
            n_ctx=_server_n_ctx(props, whole=True),
            slot_ctx=_server_n_ctx(props),
            chat_template=str(props.get("chat_template") or "") or None,
            n_ctx_train=_positive(meta.get("n_ctx_train")),
        )
    ]


def _text(value: Any) -> str | None:
    """A non-empty string from a server's answer, else `None`."""
    return (value.strip() or None) if isinstance(value, str) else None


def _server_n_ctx(props: dict[str, Any], *, whole: bool = False) -> int | None:
    """llama-server's context, as `/props` says it: one slot's (the window's bound, AD-9),
    else the whole; `whole`: the larger of both (the memory it reserved, lot E)."""
    settings = props.get("default_generation_settings")
    settings = settings if isinstance(settings, dict) else {}
    slot, total = _positive(settings.get("n_ctx")), _positive(props.get("n_ctx"))
    if whole:
        return max(slot or 0, total or 0) or None
    return slot or total


def list_served(
    cfg: config.Config, transport: httpx.BaseTransport | None = None
) -> list[ServedModel]:
    """Every model the servers of `[net.loopback_ports]` serve now, `/api/ps` read once per
    Ollama; a silent server, or one whose answers do not have the expected shape, is
    skipped. Never launches anything."""
    served: list[ServedModel] = []
    client = _client(DISCOVERY_TIMEOUT_S, DISCOVERY_TIMEOUT_S * 3, transport)
    try:
        for engine, port in cfg.loopback_ports.items():
            if engine not in PROVIDERS:
                continue
            url = f"http://127.0.0.1:{port}"
            try:
                served += _served_by(client, engine, url)
            except (httpx.HTTPError, ServerError, *_RESPONSE_ERRORS):
                continue
    finally:
        client.close()
    return served


def served_bytes(model: ServedModel, path: str | None, window: int | None = None) -> int | None:
    """AD-8: the served model's memory. Resident: what Ollama reports in `/api/ps`; else
    (llama-server) its file's size plus its KV cache for its whole context `n_ctx` (lot E,
    E1: llama-server reserves it at launch), the KV read in the file's metadata, without the
    weights (the file's size alone when unreadable); not loaded yet (Ollama): its blob's
    size, plus (story 24) its KV cache at `window` when given and readable
    (`ollama_load_bytes`). `None` when nothing says it."""
    if model.resident and model.resident_size:
        return model.resident_size
    size = model.size
    local = _local(path)
    if local:
        try:
            size = Path(local).stat().st_size
        except OSError:
            pass
    if model.engine == "ollama" and not model.resident and window and local:
        return ollama_load_bytes(local, window) or size
    kv = served_kv(model, path)
    return size + kv * (model.n_ctx or 0) if size is not None and kv else size


def ollama_load_bytes(path: str | None, window: int) -> int | None:
    """Story 24 (AD-8): what Ollama will take to load a model it does not hold yet: its
    blob's size plus its KV cache (f16) at `window`, read in the blob's header in pure
    Python; the size alone when the KV is unreadable; `None` without a readable file.
    Never the probe's RSS of the blob: that measured llama-cpp-python in WaveStack's own
    child (compute buffers, KV at `probe_window`), not Ollama's engine."""
    local = _local(path)
    if not local:
        return None
    try:
        size = Path(local).stat().st_size
    except OSError:
        return None
    kv = probe.gguf_kv_bytes_per_token(local) or 0
    return size + kv * max(window, 0)


def served_kv(model: ServedModel, path: str | None) -> int | None:
    """Lot E (E1): the KV cache's bytes per token of llama-server's model, read in its GGUF
    header when `path` is a file of this disk (an absolute path: a relative one was the
    server's, not WaveStack's); `None` otherwise, the memory then leaving the cache out."""
    if model.engine != "llama_server" or not model.n_ctx:
        return None
    return probe.gguf_kv_bytes_per_token(_local(path))


def _local(path: str | None) -> str | None:
    return path if path and Path(path).is_absolute() else None


# Lot E (E1): llama-server's context counts as « much larger » than the window past this.
CONTEXT_WARN_FACTOR = 1.5


def context_warning_fr(n_ctx: int | None, window: int, slot_ctx: int | None = None) -> str | None:
    """Lot E (E1): the French warning when a slot of llama-server has a context much larger
    than WaveStack's window (`-c` omitted: the model's whole native context), whose memory
    it reserved for nothing; `None` otherwise. With several slots (`-np N`), `-c {window}`
    alone would shrink each slot below the window: the advice is `-np 1 -c {window}`."""
    slot = slot_ctx or n_ctx
    if not slot or slot <= window * CONTEXT_WARN_FACTOR:
        return None
    whole = max(n_ctx or 0, slot)
    slots = whole // slot if whole > slot else 1
    shared = f" ({_fr_int(slot)} par emplacement, {slots} emplacements)" if slots > 1 else ""
    advice = f"-np 1 -c {window}" if slots > 1 else f"-c {window}"
    return (
        f"llama-server a été lancé avec un contexte de {_fr_int(whole)} tokens{shared}, alors "
        f"que WaveStack n'en utilise que {_fr_int(window)} : il réserve la mémoire de tout ce "
        f"contexte. Arrêtez-le et relancez-le avec `{advice}`."
    )


def _fr_int(n: int) -> str:
    """« 262 144 »: French thousands separator (narrow no-break space)."""
    return f"{n:,}".replace(",", "\u202f")


def open_engine(
    candidate: Any, n_ctx: int, cfg: config.Config, transport: httpx.BaseTransport | None = None
) -> LlamaServerEngine | OllamaRawEngine:
    """The adapter of a served-model candidate (`discovery.ModelCandidate`, `source =
    server`): the default `server_factory` of the application session."""
    timeouts = {
        "connect_timeout_s": cfg.model_server_connect_timeout_s,
        "read_timeout_s": cfg.model_server_read_timeout_s,
        "transport": transport,
    }
    if candidate.engine == "llama_server":
        return LlamaServerEngine(candidate.server_url, markers=cfg.cloud_markers, **timeouts)
    if candidate.engine == "ollama":
        return OllamaRawEngine(
            candidate.server_url,
            candidate.name,
            candidate.gguf_path,
            n_ctx,
            unload=not candidate.resident,
            **timeouts,
        )
    raise ValueError(f"serveur local inconnu : {candidate.engine}")
