"""Adapters of an already-running local server: `llama_server` and `ollama_raw` (AD-5, AD-8).

WaveStack never launches, installs nor stops Ollama or llama-server; it only talks to them at
the loopback addresses of `[net.loopback_ports]`, through `net`'s loopback client (no proxy,
any other host refused, AD-15). Both adapters stay in rendered-text mode (AD-4): the harness
builds the whole text, template included; nothing goes through the servers' chat format.

- `llama_server` receives the token ids (`/completion`); its tokenizer is the server's own
  (`/tokenize` with pieces), so the gauge counts exactly the ids it sends.
- `ollama_raw` receives the rendered text (`/api/generate`, `raw: true`), rebuilt from the
  ids' own pieces (control 6 of AD-4 makes it `rendered.prompt`), with `num_ctx` always sent;
  its tokenizer is the model's GGUF opened `vocab_only` (`VocabTokenizer`). A different
  `prompt_eval_count`, or a `thinking` field, is reported as « transparence réduite ».
"""

from __future__ import annotations

import json
import re
from collections.abc import Iterator, Sequence
from contextlib import contextmanager
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Protocol

import httpx

from wavestack import config
from wavestack.models.engine import (
    TEMPERATURE,
    TOP_K,
    TOP_P,
    CancelToken,
    EngineMetadata,
    Fragment,
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
) -> Any:
    try:
        extra = {"timeout": timeout} if timeout is not None else {}
        response = client.request(method, base + path, json=body, **extra)
    except httpx.HTTPError as exc:
        raise ServerError(base, _cause(exc)) from exc
    if response.status_code >= 400:
        raise ServerError(base, f"HTTP {response.status_code} : {response.text[:200]}")
    try:
        return response.json()
    except ValueError as exc:
        raise ServerError(base, f"réponse illisible sur {path}") from exc


@contextmanager
def _stream(client: httpx.Client, base: str, path: str, body: Any) -> Iterator[httpx.Response]:
    """A streamed POST; closed on exit (cancellation included). HTTP errors, before or during
    the stream, become `ServerError`."""
    try:
        with client.stream("POST", base + path, json=body) as response:
            if response.status_code >= 400:
                response.read()
                raise ServerError(base, f"HTTP {response.status_code} : {response.text[:200]}")
            yield response
    except httpx.HTTPError as exc:
        raise ServerError(base, _cause(exc)) from exc


def _positive(value: Any) -> int | None:
    try:
        n = int(value)
    except (TypeError, ValueError):
        return None
    return n if n > 0 else None


def _sampling() -> dict[str, float | int]:
    """The in-process engine's sampling (`engine.py`), sent to the servers too."""
    return {"temperature": TEMPERATURE, "top_p": TOP_P, "top_k": TOP_K, "min_p": 0.0}


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
        try:
            self._metadata = self._read_metadata(markers)
        except BaseException:
            self._client.close()
            raise

    def _read_metadata(self, markers: Sequence[str]) -> EngineMetadata:
        props = _json(self._client, self.url, "GET", "/props") or {}
        try:
            models = _json(self._client, self.url, "GET", "/v1/models") or {}
        except ServerError:
            models = {}
        data = models.get("data") or [{}]
        meta = (data[0] or {}).get("meta") or {}
        settings = props.get("default_generation_settings") or {}
        bos, eos = str(props.get("bos_token") or ""), str(props.get("eos_token") or "")
        special = [t for t in (bos, eos) if t]
        # AD-4, step 2: the template markers the server's vocabulary holds as one token.
        for marker in markers:
            if marker not in special and len(self.tokenize(marker)) == 1:
                special.append(marker)
        return EngineMetadata(
            architecture=None,  # not exposed: the family is read from the template (AD-6)
            chat_template=props.get("chat_template") or None,
            native_context=_positive(meta.get("n_ctx_train")),
            bos_token=bos,
            eos_token=eos,
            special_tokens=tuple(special),
            server_context=_positive(settings.get("n_ctx")) or _positive(props.get("n_ctx")),
        )

    def metadata(self) -> EngineMetadata:
        return self._metadata

    def tokenize(self, text: str) -> list[int]:
        body = {"content": text, "add_special": False, "parse_special": True, "with_pieces": True}
        data = _json(self._client, self.url, "POST", "/tokenize", body) or {}
        ids: list[int] = []
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
        return ids

    def token_pieces(self, ids: Sequence[int]) -> list[bytes]:
        pieces = []
        for token in ids:
            if token not in self._pieces:  # not seen by `tokenize`: one `/detokenize`
                data = _json(self._client, self.url, "POST", "/detokenize", {"tokens": [token]})
                self._pieces[token] = str((data or {}).get("content") or "").encode("utf-8")
            pieces.append(self._pieces[token])
        return pieces

    def complete(
        self, prompt_ids: Sequence[int], stop: Sequence[str], max_tokens: int, cancel: CancelToken
    ) -> Iterator[Fragment]:
        body = {
            "prompt": list(prompt_ids),
            "n_predict": max_tokens,
            "stop": list(stop),
            "stream": True,
            "cache_prompt": True,
            **_sampling(),
        }
        pending = ""
        count = 0
        reason: StopReason = "stop"
        with _stream(self._client, self.url, "/completion", body) as response:
            for line in response.iter_lines():
                if cancel.cancelled:
                    reason = "cancelled"
                    break
                if not line.startswith("data:"):
                    continue
                data = json.loads(line[5:])
                if data.get("error"):
                    raise ServerError(self.url, str(data["error"])[:200])
                text = str(data.get("content") or "")
                if text:
                    count += 1
                count = _positive(data.get("tokens_predicted")) or count
                pending += text
                emit, pending, stopped = cut_stop(pending, stop)
                if stopped:
                    yield Fragment(emit, count, "stop")
                    return
                if text:
                    yield Fragment(emit, count)
                if data.get("stop"):
                    reason = "length" if data.get("stop_type") == "limit" else "stop"
                    break
        yield Fragment(pending, count, reason)

    def close(self) -> None:
        self._client.close()


class OllamaRawEngine:
    """`ollama_raw` (AD-5): the rendered text by `/api/generate` in `raw` mode, `num_ctx` the
    effective window; tokenizer, pieces and metadata from the GGUF opened `vocab_only`."""

    def __init__(
        self,
        url: str,
        name: str,
        gguf_path: str | None,
        n_ctx: int,
        *,
        tokenizer: Tokenizer | None = None,
        connect_timeout_s: float = 2.0,
        read_timeout_s: float = 300.0,
        transport: httpx.BaseTransport | None = None,
    ) -> None:
        self.url, self.name = url.rstrip("/"), name
        self._tokenizer = tokenizer if tokenizer is not None else VocabTokenizer(gguf_path)
        native = self._tokenizer.metadata().native_context
        # AD-9: min(configured, native); Ollama has no context of its own until we send one.
        self.num_ctx = min(n_ctx, native) if native else n_ctx
        self._client = _client(connect_timeout_s, read_timeout_s, transport)
        self._closed = False

    def metadata(self) -> EngineMetadata:
        return self._tokenizer.metadata()

    def tokenize(self, text: str) -> list[int]:
        return self._tokenizer.tokenize(text)

    def token_pieces(self, ids: Sequence[int]) -> list[bytes]:
        return self._tokenizer.token_pieces(ids)

    def complete(
        self, prompt_ids: Sequence[int], stop: Sequence[str], max_tokens: int, cancel: CancelToken
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
                **_sampling(),
            },
        }
        pending = ""
        count = 0
        reason: StopReason = "stop"
        stopped = thinking = False
        with _stream(self._client, self.url, "/api/generate", body) as response:
            for line in response.iter_lines():
                if cancel.cancelled:
                    reason = "cancelled"
                    break
                if not line.strip():
                    continue
                data = json.loads(line)
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
                    yield Fragment(emit, count)
                if data.get("done"):
                    count = _positive(data.get("eval_count")) or count
                    if not stopped and data.get("done_reason") == "length":
                        reason = "length"
                    evaluated = data.get("prompt_eval_count")
                    if isinstance(evaluated, int) and evaluated != len(prompt_ids):
                        _reduced(
                            f"Transparence réduite : Ollama a lu {evaluated} tokens de prompt, "
                            f"le harnais en a compté {len(prompt_ids)}. Ollama tokenise le "
                            "texte à sa façon, ou ne compte que la partie hors de son cache.",
                            f"prompt_eval_count = {evaluated}, harnais = {len(prompt_ids)}",
                        )
                    break
        yield Fragment(pending, count, reason)

    def close(self) -> None:
        """AD-8: leaving an Ollama model unloads it (`keep_alive: 0`); a failure is traced,
        never blocking."""
        if self._closed:
            return
        self._closed = True
        try:
            error = release_ollama(self.url, self.name, client=self._client)
            if error is not None:
                get_journal().emit(
                    "harness_error",
                    {
                        "message_fr": f"Ollama n'a pas déchargé le modèle {self.name}.",
                        "cause": error,
                        "effect_fr": (
                            "WaveStack continue ; Ollama le déchargera de lui-même après son "
                            "délai d'inactivité."
                        ),
                    },
                )
        finally:
            self._client.close()
            self._tokenizer.close()


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
    size: int | None = None  # bytes the server reports for the model

    @property
    def provider(self) -> str:
        return PROVIDERS[self.engine]


def _served_by(client: httpx.Client, engine: str, url: str) -> list[ServedModel]:
    if engine == "ollama":
        tags = _json(client, url, "GET", "/api/tags") or {}
        served = []
        for model in tags.get("models") or []:
            name = str(model.get("name") or model.get("model") or "")
            if name:
                served.append(
                    ServedModel(
                        engine, url, name, f"ollama/{name}", size=_positive(model.get("size"))
                    )
                )
        return served
    health = client.get(url + _PROBE_PATHS[engine])
    if health.status_code >= 400:  # 503: still loading its model, nothing to choose yet
        return []
    props = _json(client, url, "GET", "/props") or {}
    try:
        models = _json(client, url, "GET", "/v1/models") or {}
    except ServerError:
        models = {}
    first = (models.get("data") or [{}])[0] or {}
    model_path = str(props.get("model_path") or "") or None
    name = _file_name(model_path) if model_path else str(first.get("id") or "modèle")
    size = _positive((first.get("meta") or {}).get("size"))
    return [ServedModel(engine, url, name, f"llama_server/{name}", model_path, size)]


def list_served(
    cfg: config.Config, transport: httpx.BaseTransport | None = None
) -> list[ServedModel]:
    """Every model the servers of `[net.loopback_ports]` serve now; a silent or unknown
    server is skipped. Never launches anything."""
    served: list[ServedModel] = []
    client = _client(DISCOVERY_TIMEOUT_S, DISCOVERY_TIMEOUT_S * 3, transport)
    try:
        for engine, port in cfg.loopback_ports.items():
            if engine not in PROVIDERS:
                continue
            url = f"http://127.0.0.1:{port}"
            try:
                served += _served_by(client, engine, url)
            except (httpx.HTTPError, ServerError, ValueError, TypeError):
                continue
    finally:
        client.close()
    return served


def served_bytes(
    engine: str,
    url: str,
    name: str,
    *,
    path: str | None = None,
    fallback: int | None = None,
    transport: httpx.BaseTransport | None = None,
) -> int:
    """AD-8: the served model's memory. Ollama: `/api/ps` `size` once loaded, else its blob's
    size (`path`); llama-server: its file's size (`path`), else `meta.size` (`fallback`). 0
    when nothing says it."""
    if engine == "ollama":
        client = _client(DISCOVERY_TIMEOUT_S, DISCOVERY_TIMEOUT_S * 3, transport)
        try:
            running = _json(client, url.rstrip("/"), "GET", "/api/ps") or {}
            for model in running.get("models") or []:
                if model.get("name") == name or model.get("model") == name:
                    size = _positive(model.get("size"))
                    if size:
                        return size
        except (ServerError, ValueError, TypeError):
            pass
        finally:
            client.close()
    if path:
        try:
            return Path(path).stat().st_size
        except OSError:
            pass
    return fallback or 0


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
            candidate.server_url, candidate.name, candidate.gguf_path, n_ctx, **timeouts
        )
    raise ValueError(f"serveur local inconnu : {candidate.engine}")
