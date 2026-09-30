"""`openai_chat` adapter (AD-5): `POST {base_url}/chat/completions`, streamed.

It sends the `ChatBody` the harness wrote, byte for byte, with two headers only:
`Content-Type` and the authentication header, set per request (never on the shared
client). The key comes from `config.cloud_key` only; every provider string that enters an
event goes through `mask_key` first (AD-15). A provider's refusal is a `ProviderError`
from AD-16's closed list, never retried; `tool_use_failed` ends the call with
`provider_error`, for the malformed-call path (AD-10).

`run_call` is the one place that turns a completion into `model_*` events, for a turn's
call as for the diagnostic's test. It first spaces the sends to one entry by its
`min_interval_s` (`pace`), whatever adapter instance sends them.
"""

from __future__ import annotations

import json
import re
import threading
import time
from collections.abc import Callable, Iterator
from dataclasses import dataclass, field
from typing import Any

import httpx
from pydantic import SecretStr

from wavestack.config import CloudModel, estimate_tokens
from wavestack.models.capabilities import ChannelSplitter
from wavestack.models.engine import CancelToken, EngineSnapshot
from wavestack.net.factory import create_client
from wavestack.net.guard import find_blocked
from wavestack.trace.journal import get_journal

DELTA_INTERVAL_S = 0.05  # AD-2: model_delta grouped every 50 ms at most
# Mistral ends a cut output with `model_length`.
_FINISH = {"stop": "stop", "tool_calls": "stop", "length": "length", "model_length": "length"}
_CONTEXT_WORDS = ("context length", "context_length", "context window", "maximum context")
PROVIDER_MESSAGE_MAX = 500  # characters of the provider's own message shown, then « … »

# Story 17: the local model comes back without relaunch (CAP-34).
_BACK_TO_LOCAL_FR = "Revenez au modèle local depuis le sélecteur de modèle de la barre haute."


@dataclass(frozen=True)
class ChatBody:
    """The exact request body `context` wrote (AD-4), sent as is."""

    body: bytes


@dataclass
class ChatEnd:
    """A completion's end. `tool_calls`: `{provider_id, name, arguments}` in index order (in
    arrival order without `index`), `arguments` as emitted, plus `extra_content` when the
    provider sent one (Gemini 3.x: the thought signature it wants back with the call).
    `provider_error`: `tool_use_failed`'s generation (AD-10), and `provider_message` its
    `error.message`. All masked, except `extra_content`: it goes back as received, to its own
    provider only (a signature with a piece masked would be refused). It is masked only in
    `model_call_ended.tool_calls` (`run_call`); the next call's body carries it verbatim, and
    so do `context_rendered.body` and `outbound_request.body`, which trace the bytes sent
    (AD-5). A key fragment of 4 characters found inside that base64 signature is a random
    match, not a leak: the provider never sees the key there, it made the signature."""

    stop_reason: str
    tool_calls: list[dict[str, Any]]
    usage: dict[str, Any] | None
    raw_output: str
    provider_error: str | None = None
    provider_message: str | None = None


class ProviderError(Exception):
    """AD-16: one outcome of the closed list, already in French and masked."""

    def __init__(
        self,
        message_fr: str,
        *,
        cause: str,
        hints_fr: list[str],
        http_status: int | None = None,
        retry_after_s: float | None = None,
        quota_scope: str | None = None,
    ) -> None:
        super().__init__(message_fr)
        self.message_fr = message_fr
        self.cause = cause
        self.hints_fr = hints_fr
        self.http_status = http_status
        self.retry_after_s = retry_after_s
        self.quota_scope = quota_scope

    def payload(self, effect_fr: str) -> dict[str, Any]:
        """The `harness_error` payload."""
        return {
            "message_fr": self.message_fr,
            "cause": self.cause,
            "effect_fr": effect_fr,
            "hints_fr": self.hints_fr,
            "http_status": self.http_status,
            "retry_after_s": self.retry_after_s,
            "quota_scope": self.quota_scope,
        }


def mask_key(text: str, key: SecretStr | None) -> str:
    """AD-15: the key, its first 4 and its last 4 characters never enter an event."""
    if key is None:
        return text
    secret = key.get_secret_value()
    for piece in (secret, secret[:4], secret[-4:]):
        if piece:
            text = text.replace(piece, "•••")
    return text


def _mask_value(value: Any, mask: Callable[[str], str]) -> Any:
    """`mask` on every string of a JSON value (`extra_content`), at any depth."""
    if isinstance(value, str):
        return mask(value)
    if isinstance(value, dict):
        return {k: _mask_value(v, mask) for k, v in value.items()}
    if isinstance(value, list):
        return [_mask_value(v, mask) for v in value]
    return value


def _is_thought(delta: dict[str, Any]) -> bool:
    """Gemini may mark a `content` delta as thought (`extra_content.google.thought`)."""
    extra = delta.get("extra_content")
    google = extra.get("google") if isinstance(extra, dict) else None
    return isinstance(google, dict) and google.get("thought") is True


def _clip(text: str, limit: int = PROVIDER_MESSAGE_MAX) -> str:
    text = text.strip()
    return text if len(text) <= limit else text[:limit].rstrip() + "…"


def _provider_message(response: httpx.Response) -> tuple[str, dict[str, Any], bool]:
    """The provider's own message and error object, from its JSON or its text; the flag
    says whether the message may be shown: not an HTML page (a proxy's, say)."""
    try:
        data = response.json()
    except ValueError:
        html = "text/html" in response.headers.get("content-type", "").lower()
        return response.text, {}, not html
    if isinstance(data, list) and data and isinstance(data[0], dict):
        data = data[0]  # Gemini: `[{"error": {…}}]`
    error = data.get("error") if isinstance(data, dict) else None
    if isinstance(error, dict):
        return str(error.get("message") or error), error, True
    if isinstance(data, dict):
        detail = data.get("message") or data.get("detail") or error or data
        return str(detail), data, True
    return str(data), {}, True


# `/s` as a unit only: Groq's messages link to `console.groq.com/settings`.
_SECOND = re.compile(r"per sec(ond)?\b|/s(ec(ond)?)?\b|\brps\b")


def _quota_scope(message: str) -> str:
    """Minute markers first: Groq's per-minute message also says « … Dev Tier today »."""
    lowered = message.lower()
    if any(w in lowered for w in ("per minute", "(tpm)", "(rpm)", " tpm", " rpm")):
        return "minute"
    if _SECOND.search(lowered):
        return "second"
    if any(w in lowered for w in ("per day", "(tpd)", "(rpd)", " tpd", " rpd", "daily")):
        return "day"
    return "unknown"


_QUOTA_FR = {
    "second": "quota dépassé par seconde",
    "minute": "quota dépassé par minute",
    "day": "quota dépassé par jour",
}


# ---------- spacing of the sends to one entry (AD-16) ----------

_pace_lock = threading.Lock()
_last_start: dict[str, float] = {}  # entry.id → the monotonic time of its last send


def pace(entry: CloudModel, cancel: CancelToken) -> bool:
    """Wait until `min_interval_s` has passed since the last send to `entry.id`, from any
    adapter instance (« Tester » builds its own). `False` when cancelled while waiting: the
    call is then not sent. Never read from `x-ratelimit-*` headers."""
    interval = entry.min_interval_s
    if not interval:
        return True
    with _pace_lock:
        now = time.monotonic()
        previous = _last_start.get(entry.id)
        start = now if previous is None else max(now, previous + interval)
        _last_start[entry.id] = start  # reserved now: a concurrent send waits after it
    while (delay := start - time.monotonic()) > 0:  # a timer may wake a little early
        if cancel.wait(delay):
            with _pace_lock:  # the slot is freed, unless another send took a later one
                if _last_start.get(entry.id) == start:
                    if previous is None:
                        del _last_start[entry.id]
                    else:
                        _last_start[entry.id] = previous
            return False
    with _pace_lock:  # the real departure, unless a later send already reserved its own
        if _last_start.get(entry.id) == start:
            _last_start[entry.id] = time.monotonic()
    return True


class OpenAIChatEngine:
    """The `Engine` of a cloud model: input is a `ChatBody` (`input = "chat"`); it has no
    tokenizer, so `tokenize` and `token_pieces` are unavailable."""

    input = "chat"

    def __init__(
        self,
        entry: CloudModel,
        key: SecretStr,
        *,
        transport: httpx.BaseTransport | None = None,
        connect_timeout_s: float = 10.0,
        read_timeout_s: float = 60.0,
    ) -> None:
        self.entry = entry
        self._key = key
        timeout = httpx.Timeout(read_timeout_s, connect=connect_timeout_s)
        self._client = create_client(timeout=timeout, transport=transport)

    def mask(self, text: str) -> str:
        return mask_key(text, self._key)

    def tokenize(self, text: str) -> list[int]:
        raise NotImplementedError("openai_chat has no local tokenizer (AD-5)")

    def token_pieces(self, ids: Any) -> list[bytes]:
        raise NotImplementedError("openai_chat has no local tokenizer (AD-5)")

    def close(self) -> None:
        self._client.close()

    # AD-4, AD-11: the provider's cache and state are out of reach; the whole context is
    # sent again at every call.

    def cached_ids(self) -> list[int] | None:
        return None

    def snapshot(self) -> EngineSnapshot | None:
        return None

    def restore(self, snapshot: EngineSnapshot) -> bool:
        return False

    @property
    def last_evaluated(self) -> int | None:
        return None

    def _error(
        self,
        message_fr: str,
        cause: str,
        hints_fr: list[str],
        *,
        provider_message: str | None = None,
        **figures: Any,
    ) -> Any:
        """A masked `ProviderError`; `message_fr` ends with the provider's own message, when
        its answer carries one (AD-16)."""
        if provider_message and provider_message.strip():
            message_fr = (
                f"{message_fr} Message du fournisseur : {_clip(self.mask(provider_message))}"
            )
        return ProviderError(
            self.mask(message_fr), cause=_clip(self.mask(cause)), hints_fr=hints_fr, **figures
        )

    def complete(self, body: ChatBody, cancel: CancelToken) -> Iterator[tuple[str, str] | ChatEnd]:
        """`(channel, text)` fragments, then one `ChatEnd`. Raises `ProviderError`."""
        entry = self.entry
        scheme = entry.auth_header.scheme
        secret = self._key.get_secret_value()
        headers = {
            "Content-Type": "application/json",
            entry.auth_header.name: f"{scheme} {secret}" if scheme else secret,
        }
        try:
            with self._client.stream(
                "POST", f"{entry.base_url}/chat/completions", content=body.body, headers=headers
            ) as response:
                if response.status_code != 200:
                    response.read()
                    yield self._refused(response)
                    return
                yield from self._read(response, cancel)
        except ProviderError:
            raise
        except httpx.TimeoutException as exc:
            raise self._error(
                f"Délai dépassé : {entry.provider} n'a pas répondu à temps.",
                f"{type(exc).__name__}: {exc}",
                [
                    "Relancez le tour : un fournisseur chargé répond parfois lentement.",
                    "Vérifiez le réseau du poste avec « Tester » au diagnostic.",
                ],
            ) from None
        except Exception as exc:
            if find_blocked(exc) is None and not isinstance(exc, httpx.TransportError):
                raise
            raise self._error(
                f"Réseau absent : {entry.provider} ({entry.host}) est injoignable depuis ce poste.",
                f"{type(exc).__name__}: {exc}",
                [
                    "Vérifiez la connexion du poste, ou le proxy.",
                    f"L'hôte {entry.host} doit être autorisé par le réseau de l'entreprise.",
                    _BACK_TO_LOCAL_FR,
                ],
            ) from None

    def _refused(self, response: httpx.Response) -> ChatEnd:
        """A non-200 answer: `tool_use_failed` ends the call, anything else raises."""
        status = response.status_code
        provider = self.entry.provider
        message, error, shown = _provider_message(response)
        cause = f"HTTP {status} : {message}"
        if error.get("code") == "tool_use_failed":
            generation = str(error.get("failed_generation") or message)
            return ChatEnd(
                "stop",
                [],
                None,
                "",
                provider_error=self.mask(generation),
                provider_message=_clip(self.mask(message)) or None,
            )
        local = [_BACK_TO_LOCAL_FR]
        said = {"provider_message": message if shown else None}  # HTML: in `cause` only
        if 300 <= status < 400:
            raise self._error(
                f"Redirection refusée : {provider} a répondu {status} vers "
                f"{response.headers.get('location', 'une autre adresse')}. La clé n'est "
                "jamais renvoyée ailleurs.",
                cause,
                ["Vérifiez base_url dans la déclaration du modèle.", *local],
                http_status=status,
                **said,
            )
        if status == 429:
            retry = response.headers.get("retry-after")
            try:
                retry_after = float(retry) if retry else None
            except ValueError:
                retry_after = None
            wait = [f"Attendez {retry_after:g} s avant de relancer."] if retry_after else []
            scope = _quota_scope(message)
            interval = self.entry.min_interval_s
            spacing = (
                [
                    f"Augmentez min_interval_s ({interval:g} s aujourd'hui) dans la déclaration "
                    f"du modèle « {self.entry.id} »."
                ]
                if interval
                else []
            )
            quota = _QUOTA_FR.get(scope, "quota dépassé (par seconde, par minute ou par jour)")
            raise self._error(
                f"Le fournisseur refuse l'appel : {quota}.",
                cause,
                [
                    *(wait or ["Attendez un peu avant de relancer."]),
                    *spacing,
                    "Réduisez le contexte : lazy loading, moins d'outils, conversation vidée.",
                    *local,
                ],
                http_status=status,
                retry_after_s=retry_after,
                quota_scope=scope,
                **said,
            )
        if status == 413:
            raise self._error(
                "La requête dépasse à elle seule le quota par minute du fournisseur.",
                cause,
                ["Réduisez la fenêtre de contexte : attendre ne sert à rien.", *local],
                http_status=status,
                **said,
            )
        if status == 400 and any(w in message.lower() for w in _CONTEXT_WORDS):
            raise self._error(
                f"Contexte dépassé : {provider} refuse un contexte plus long que sa fenêtre.",
                cause,
                ["Videz la conversation, ou passez la brique MCP en lazy loading.", *local],
                http_status=status,
                **said,
            )
        if status in (400, 422):
            raise self._error(
                f"Requête refusée par {provider} ({status}) : défaut du harnais ou du préréglage.",
                cause,
                ["Vérifiez la déclaration du modèle (wavestack.toml ou settings.json).", *local],
                http_status=status,
                **said,
            )
        if status in (401, 403):
            raise self._error(
                f"Clé refusée par {provider} ({status}). Vérifiez-la dans le diagnostic.",
                cause,
                ["Ressaisissez la clé au diagnostic, puis « Tester ».", *local],
                http_status=status,
                **said,
            )
        if status == 404:
            raise self._error(
                f"Modèle introuvable chez {provider} (404) : « {self.entry.model} » a "
                "peut-être été retiré.",
                cause,
                ["Vérifiez le nom du modèle dans la console du fournisseur.", *local],
                http_status=status,
                **said,
            )
        if status >= 500:
            raise self._error(
                f"{provider} est indisponible ({status}).",
                cause,
                ["Réessayez dans quelques minutes.", *local],
                http_status=status,
                **said,
            )
        raise self._error(
            f"Réponse inattendue de {provider} ({status}).",
            cause,
            local,
            http_status=status,
            **said,
        )

    def _read(
        self, response: httpx.Response, cancel: CancelToken
    ) -> Iterator[tuple[str, str] | ChatEnd]:
        entry = self.entry
        reasoning = entry.reasoning
        think = reasoning is not None and reasoning.format == "think_tags"
        splitter = ChannelSplitter(tuple(reasoning.tags)) if think else None
        calls: dict[Any, dict[str, Any]] = {}
        raw: list[str] = []
        usage = groq_usage = None
        stop = "stop"
        for line in response.iter_lines():
            if cancel.cancelled:
                stop = "cancelled"
                break  # leaving the `with` closes the stream (AD-5)
            if not line or line.startswith((":", "event:", "id:", "retry:")):
                continue
            data = line[5:].strip() if line.startswith("data:") else None
            if data == "[DONE]":
                break
            try:
                chunk = json.loads(data) if data is not None else None
            except ValueError:
                chunk = None
            if not isinstance(chunk, dict):
                raise self._error(
                    f"Réponse illisible : une ligne du flux de {entry.provider} n'est pas au "
                    "format attendu (SSE).",
                    line[:300],
                    [
                        "Relancez le tour.",
                        _BACK_TO_LOCAL_FR,
                    ],
                )
            if chunk.get("error"):
                error = chunk["error"] if isinstance(chunk["error"], dict) else {}
                said = str(error.get("message") or chunk["error"])
                if error.get("code") == "tool_use_failed":
                    generation = str(error.get("failed_generation") or said)
                    raw_output = self.mask("\n".join(raw))
                    message = _clip(self.mask(said)) or None
                    yield ChatEnd(
                        "stop",
                        [],
                        usage,
                        raw_output,
                        provider_error=self.mask(generation),
                        provider_message=message,
                    )
                    return
                raise self._error(
                    f"{entry.provider} a interrompu la réponse sur une erreur.",
                    said,
                    [
                        "Relancez le tour.",
                        _BACK_TO_LOCAL_FR,
                    ],
                    provider_message=said,
                )
            usage = chunk.get("usage") or usage
            groq_usage = (chunk.get("x_groq") or {}).get("usage") or groq_usage
            choices = chunk.get("choices") or []
            if not choices:  # a usage-only chunk (Azure)
                continue
            choice = choices[0]
            delta = choice.get("delta") or {}
            raw.append(json.dumps(delta, ensure_ascii=False))
            for channel, text in self._channels(delta, splitter, calls):
                yield channel, self.mask(text)  # AD-15: every provider string is masked
            finish = choice.get("finish_reason")
            if finish:
                if finish not in _FINISH:
                    raise self._error(
                        f"{entry.provider} a arrêté la réponse ({finish}).",
                        f"finish_reason: {finish}",
                        [
                            "Reformulez le message.",
                            _BACK_TO_LOCAL_FR,
                        ],
                    )
                stop = _FINISH[finish]
        if splitter is not None:
            for channel, text in splitter.flush():
                yield channel, self.mask(text)
        # By `index` when every call has one; else (Gemini sends none, calls keyed by `id`) in
        # arrival order: ids do not sort (`call_99999` would follow `call_100002`).
        indexed = all(isinstance(key, int) for key in calls)
        ordered = [
            {
                k: self.mask(v) if isinstance(v, str) and k != "extra_content" else v
                for k, v in calls[key].items()
            }
            for key in (sorted(calls) if indexed else calls)
        ]
        yield ChatEnd(stop, ordered, usage or groq_usage, self.mask("\n".join(raw)))

    @staticmethod
    def _channels(
        delta: dict[str, Any], splitter: ChannelSplitter | None, calls: dict[Any, dict[str, Any]]
    ) -> Iterator[tuple[str, str]]:
        for name in ("reasoning", "reasoning_content"):
            if isinstance(delta.get(name), str) and delta[name]:
                yield "reasoning", delta[name]
        content = delta.get("content")
        # Gemini marks its thought chunks (`extra_content.google.thought`), tags included: with
        # `think_tags`, the tags decide (the closing one comes in an unmarked chunk); the mark
        # alone decides only without them.
        if isinstance(content, str) and content and splitter is None and _is_thought(delta):
            yield "reasoning", content
        elif isinstance(content, str) and content:
            yield from splitter.feed(content) if splitter else [("text", content)]
        elif isinstance(content, list):  # Mistral: `thinking` and `text` blocks
            for block in content:
                if not isinstance(block, dict):
                    continue
                if block.get("type") == "text" and block.get("text"):
                    yield "text", str(block["text"])
                elif block.get("type") == "thinking":
                    thinking = block.get("thinking")
                    parts = thinking if isinstance(thinking, list) else [thinking]
                    for part in parts:
                        text = part.get("text") if isinstance(part, dict) else part
                        if isinstance(text, str) and text:
                            yield "reasoning", text
        for call in delta.get("tool_calls") or []:
            key = call.get("index", call.get("id"))
            acc = calls.setdefault(key, {"provider_id": None, "name": "", "arguments": ""})
            if call.get("id"):
                acc["provider_id"] = call["id"]
            if isinstance(call.get("extra_content"), dict):  # Gemini 3.x: thought signature
                acc["extra_content"] = acc.get("extra_content", {}) | call["extra_content"]
            function = call.get("function") or {}
            text = (function.get("name") or "") + (function.get("arguments") or "")
            acc["name"] += function.get("name") or ""
            acc["arguments"] += function.get("arguments") or ""
            if text:
                yield "tool_call", text


# ---------- one call, as `model_*` events (AD-2) ----------


@dataclass
class ChatCall:
    """What `run_call` read. `calls`: `{id, provider_id, name, arguments, parsed}`, `id` set
    only when every call is valid; `malformed`: `(reinjected, detail_fr)` (AD-10)."""

    text: str = ""
    reasoning: str = ""
    stop_reason: str = "stop"
    channel: str = "text"  # the channel of the last fragment, for `output_truncated`
    calls: list[dict[str, Any]] = field(default_factory=list)
    malformed: tuple[str, str] | None = None
    usage: dict[str, Any] | None = None
    output_tokens: int = 0
    output_tps: int | None = None


def _reinjected(text: str, calls: list[dict[str, Any]]) -> str:
    """AD-10: `content`, then each call's `name` and `arguments` as emitted."""
    return "\n".join([text, *(f"{c['name']} {c['arguments']}" for c in calls)]).strip()


def _check_calls(calls: list[dict[str, Any]]) -> str | None:
    """Why the output's calls cannot run (AD-10), in French; `None` when all are valid."""
    for call in calls:
        if not call["name"]:
            return "un appel d'outil n'a pas de nom"
        try:
            parsed = json.loads(call["arguments"] or "{}")
        except ValueError as exc:
            return f"les arguments de « {call['name']} » ne sont pas du JSON valide ({exc})"
        if not isinstance(parsed, dict):
            return f"les arguments de « {call['name']} » ne sont pas un objet JSON"
        call["parsed"] = parsed
    return None


def output_tokens(usage: dict[str, Any]) -> int:
    """The tokens the model produced, from `usage` (0: unknown). Gemini's `completion_tokens`
    leaves out its thinking tokens, billed as output and counted against `max_tokens`:
    `total_tokens − prompt_tokens` then says more, and is taken. Groq and Mistral give
    `total = prompt + completion`: their `completion_tokens` stays."""
    try:
        completion = int(usage.get("completion_tokens") or 0)
    except (TypeError, ValueError):
        completion = 0
    total, prompt = usage.get("total_tokens"), usage.get("prompt_tokens")
    if isinstance(total, int) and isinstance(prompt, int) and total - prompt > completion:
        return total - prompt
    return completion


def output_tps(output_tokens: int, gen_ms: int) -> int | None:
    """AD-2: computed by the session; `None` when `gen_ms` is 0."""
    return round(output_tokens / (gen_ms / 1000)) if gen_ms > 0 else None


def run_call(
    engine: Any,
    body: ChatBody,
    cancel: CancelToken,
    *,
    phase_label: str,
    estimated_prompt: int,
    chars_per_token: float,
    call_id: Callable[[int], str],
    sampling_trace: dict[str, Any] | None = None,
) -> ChatCall:
    """One streamed call under the caller's scope: `model_call_started`, `model_first_token`,
    `model_delta` (grouped), `model_call_ended`. Raises `ProviderError` after ending the call
    with `stop_reason: error`. `call_id(index)` gives a valid call's session id (AD-4).
    `sampling_trace` (story 29): `model_call_started.sampling`."""
    entry = getattr(engine, "entry", None)
    # AD-16: the spacing wait, before the call starts, so neither `prompt_ms` nor
    # `duration_ms` counts it; cancelled while waiting, nothing is sent.
    if isinstance(entry, CloudModel) and not pace(entry, cancel):
        return ChatCall(stop_reason="cancelled")
    journal = get_journal()
    started = time.monotonic()
    started_payload: dict[str, Any] = {"phase_label": phase_label}
    if sampling_trace is not None:  # story 29: what sampling the call carries, and whose
        started_payload["sampling"] = sampling_trace
    journal.emit("model_call_started", started_payload)
    out = ChatCall()
    channels: dict[str, list[str]] = {"reasoning": [], "text": [], "tool_call": []}
    pending: list[tuple[str, str]] = []
    first_at = last_at = None
    last_flush = started
    end: ChatEnd | None = None

    def flush() -> None:
        nonlocal last_flush
        while pending:
            channel, text = pending[0][0], ""
            while pending and pending[0][0] == channel:
                text += pending.pop(0)[1]
            journal.emit("model_delta", {"channel": channel, "text": text}, actor="model")
        last_flush = time.monotonic()

    mask = getattr(engine, "mask", None) or (lambda text: text)

    def traced(call: dict[str, Any]) -> dict[str, Any]:
        keys = ("id", "provider_id", "name", "arguments", "extra_content")
        found = {k: call.get(k) for k in keys if call.get(k)}
        # AD-15: masked in this event only; the replayed body, and so `context_rendered.body`
        # and `outbound_request.body` (the bytes sent, AD-5), carry the signature verbatim.
        if "extra_content" in found:
            found["extra_content"] = _mask_value(found["extra_content"], mask)
        return found

    def ended(stop_reason: str, raw_output: str) -> None:
        now = time.monotonic()
        first, last = first_at or now, last_at or first_at or now
        text_all = "".join("".join(v) for v in channels.values())
        usage = out.usage or {}
        out.output_tokens = output_tokens(usage) or estimate_tokens(text_all, chars_per_token)
        gen_ms = round((last - first) * 1000)
        out.output_tps = output_tps(out.output_tokens, gen_ms)
        journal.emit(
            "model_call_ended",
            {
                "raw_output": raw_output,
                "reasoning": out.reasoning,
                "text": out.text,
                "tool_calls": [traced(c) for c in out.calls],
                "prompt_tokens": int(usage.get("prompt_tokens") or estimated_prompt),
                "output_tokens": out.output_tokens,
                "prompt_ms": round((first - started) * 1000),
                "gen_ms": gen_ms,
                "stop_reason": stop_reason,
                "duration_ms": round((now - started) * 1000),
                "output_tps": out.output_tps,
                "usage_source": "api" if out.usage else "estimate",
            },
            actor="model",
        )

    try:
        for item in engine.complete(body, cancel):
            if isinstance(item, ChatEnd):
                end = item
                continue
            channel, text = item
            now = time.monotonic()
            if first_at is None:
                first_at = now
                journal.emit("model_first_token", {}, actor="model")
            last_at = now
            out.channel = channel
            channels[channel].append(text)
            pending.append(item)
            if now - last_flush >= DELTA_INTERVAL_S:
                flush()
        flush()
    except Exception:  # a provider's refusal or anything else: the call still ends
        flush()
        out.text, out.reasoning = "".join(channels["text"]), "".join(channels["reasoning"])
        ended("error", "")
        raise
    assert end is not None
    out.text, out.reasoning = "".join(channels["text"]), "".join(channels["reasoning"])
    out.stop_reason, out.usage, out.calls = end.stop_reason, end.usage, end.tool_calls
    if end.provider_error is not None:
        detail = (
            f"le fournisseur a refusé l'appel d'outil : {end.provider_message}"
            if end.provider_message
            else "le fournisseur a refusé l'appel d'outil mal formé"
        )
        out.malformed = (end.provider_error, detail)
    elif out.calls and out.stop_reason == "stop":
        detail = _check_calls(out.calls)
        if detail is not None:
            out.malformed = (_reinjected(out.text, out.calls), detail)
        else:
            for index, call in enumerate(out.calls):
                call["id"] = call_id(index)
    ended(end.stop_reason, end.raw_output)
    return out
