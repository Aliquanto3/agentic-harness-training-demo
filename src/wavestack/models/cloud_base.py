"""The common base of the cloud adapters (AD-5, AD-26): what every provider API shares.

An adapter (`openai_chat`, `anthropic_messages`, `openai_responses`) sends the body the
harness wrote, byte for byte, to `{base_url}{endpoint}`, with `Content-Type`, the
authentication header and the entry's fixed `extra_headers` only, set per request (never on
the shared client, which comes from `net/factory.create_client`). The key comes from
`config.cloud_key` only; every provider string that enters an event goes through `mask_key`
first (AD-15). A provider's refusal is a `ProviderError` from AD-16's closed list, never
retried; `tool_use_failed` ends the call with `provider_error`, for the malformed-call path
(AD-10). Each adapter reads its own stream (`_read`); the rest is here.

`run_call` is the one place that turns a completion into `model_*` events, for a turn's
call as for the diagnostic's test. It first spaces the sends to one entry by its
`min_interval_s` (`pace`), whatever adapter instance sends them. FinOps (the session's
spend) and the spacing registry live here once, whatever the API.
"""

from __future__ import annotations

import json
import math
import re
import threading
import time
from collections.abc import Callable, Iterator, Sequence
from dataclasses import dataclass, field
from typing import Any, ClassVar

import httpx
from pydantic import SecretStr

from wavestack.cloud import usd_price_fr
from wavestack.config import DEFAULT_EUR_PER_USD, CloudModel, CloudPricing, estimate_tokens
from wavestack.greenops import Impact, cloud_impacts
from wavestack.messages import KeyedError, Lazy, Message, render
from wavestack.models.engine import CancelToken, EngineSnapshot
from wavestack.net.factory import create_client
from wavestack.net.guard import find_blocked
from wavestack.trace.journal import get_journal

DELTA_INTERVAL_S = 0.05  # AD-2: model_delta grouped every 50 ms at most
# Anthropic's 400 says « prompt is too long » (native providers 3/5).
_CONTEXT_WORDS = (
    "context length",
    "context_length",
    "context window",
    "maximum context",
    "prompt is too long",
)
PROVIDER_MESSAGE_MAX = 500  # characters of the provider's own message shown, then « … »

# The message keys keep their `models.openai_chat.*` names on purpose (native providers 1/5:
# no retranslation), whatever the API.
# Story 17: the local model comes back without relaunch (CAP-34).
_BACK_TO_LOCAL_FR = Message("models.openai_chat.back_to_local")


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
    match, not a leak: the provider never sees the key there, it made the signature.

    Native providers 3/5 (Anthropic): `thinking_blocks`, the `thinking` (text and
    `signature`) and `redacted_thinking` (`data`) blocks in the order received, verbatim like
    `extra_content` (masked only in `raw_output`); native providers 4/5 (OpenAI's Responses
    API), the `reasoning` items, `encrypted_content` included, the same way; `dropped`, the
    provider's `input_transformations` entries (blocks of an earlier turn it threw away,
    CAP-5)."""

    stop_reason: str
    tool_calls: list[dict[str, Any]]
    usage: dict[str, Any] | None
    raw_output: str
    provider_error: str | None = None
    provider_message: str | None = None
    thinking_blocks: list[dict[str, Any]] = field(default_factory=list)
    dropped: list[dict[str, Any]] = field(default_factory=list)


class ProviderError(KeyedError):
    """AD-16: one outcome of the closed list, masked. Languages (5/5): its text and its
    hints are `Message`s (a plain text is kept verbatim): `str()`, `message_text` and
    `hints_text` give the French, `payload(effect_text, lang=)` the event in `lang`."""

    def __init__(
        self,
        message_text: str | Message,
        *,
        cause: str,
        hints_text: list[str],
        http_status: int | None = None,
        retry_after_s: float | None = None,
        quota_scope: str | None = None,
    ) -> None:
        if not isinstance(message_text, Message):
            message_text = Message("common.verbatim", text=message_text)
        super().__init__(message_text)
        self.message_text = message_text
        self.cause = cause
        self.hints_text = hints_text
        self.http_status = http_status
        self.retry_after_s = retry_after_s
        self.quota_scope = quota_scope
        # FinOps: what the call cost when an output had come before the error (`run_call`).
        self.cost: CallCost | None = None
        # GreenOps: its estimated footprint, likewise.
        self.impact: Impact | None = None
        # Native providers 3/5 and 4/5: the pivot usage the stream gave before the error (the
        # input is billed even without output), and Anthropic's `input_transformations`
        # entries read by then (CAP-5); set by the adapter, read by `run_call`.
        self.usage: dict[str, Any] | None = None
        self.dropped: list[dict[str, Any]] = []

    def payload(self, effect_text: str, lang: str = "fr") -> dict[str, Any]:
        """The `harness_error` payload, its texts in `lang` (the session's); `effect_text`
        may be a `Message`. `cause` is the provider's own text, never translated, or the
        harness's own code when no provider was asked (`max_session_usd`, CAP-4)."""
        return {
            "message_text": self.render(lang),
            "cause": self.cause,
            "effect_text": render(effect_text, lang),
            "hints_text": [render(hint, lang) for hint in self.hints_text],
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


def _no_quota(response: httpx.Response) -> bool:
    """D6 (2026-10-01): a 429 whose `x-ratelimit-limit-req-minute` is `0`, the account has no
    active quota at all. Read for the explanation only, never to wait or retry."""
    return response.headers.get("x-ratelimit-limit-req-minute", "").strip() == "0"


# Native providers 4/5: OpenAI's codes (`code` or `type`) for an account without credit, on a
# 429 or in the stream (measured on 2026-10-03); waiting or retrying would not help.
NO_CREDIT = ("insufficient_quota", "credit_balance_exhausted")


def no_credit(error: Any) -> bool:
    """The provider's error object says the account has no credit left (`NO_CREDIT`)."""
    return isinstance(error, dict) and bool({error.get("code"), error.get("type")} & set(NO_CREDIT))


_QUOTA_FR = {
    scope: Message(f"models.openai_chat.quota.{scope}") for scope in ("second", "minute", "day")
}


# ---------- spacing of the sends to one entry (AD-16) ----------

_pace_lock = threading.Lock()
_last_start: dict[str, float] = {}  # entry.id → the monotonic time of its last send


def pace(entry: CloudModel, cancel: CancelToken) -> bool:
    """Wait until `min_interval_s` has passed since the last send to `entry.id`, from any
    adapter instance (« Tester » builds its own). `False` when cancelled while waiting: the
    call is then not sent. Never read from `x-ratelimit-*` headers (`_no_quota` reads one, for
    a message only)."""
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


# ---------- FinOps: the cost of a call and the session's spend ----------


@dataclass(frozen=True)
class CallCost:
    """What one cloud call cost, in dollars (an estimate from the declared prices);
    `source` is `estimate` when its tokens were estimated, not read from `usage`."""

    input_usd: float
    output_usd: float
    source: str  # api | estimate


def call_cost(
    pricing: CloudPricing,
    prompt_tokens: int,
    output_tokens: int,
    source: str,
    *,
    cached_read: int = 0,
    cached_write: int = 0,
) -> CallCost:
    """Input: `prompt_tokens` (the whole input, cached tokens included) × the input price
    / 10⁶, except the `cached_read` tokens read from the provider's cache and the
    `cached_write` ones written to it, at their own prices when the entry declares them (the
    input price otherwise, CAP-4); output: `output_tokens` (the reasoning tokens included,
    even those Gemini leaves out of `completion_tokens`) × the output price / 10⁶."""
    price_in = pricing.input_usd_per_mtok
    read_price = pricing.cache_read_usd_per_mtok
    write_price = pricing.cache_write_usd_per_mtok
    cached_read = max(0, min(cached_read, prompt_tokens))
    cached_write = max(0, min(cached_write, prompt_tokens - cached_read))
    plain = prompt_tokens - cached_read - cached_write
    input_usd = (
        plain * price_in
        + cached_read * (price_in if read_price is None else read_price)
        + cached_write * (price_in if write_price is None else write_price)
    )
    return CallCost(
        input_usd / 1_000_000,
        output_tokens * pricing.output_usd_per_mtok / 1_000_000,
        source,
    )


def _cached_tokens(usage: dict[str, Any]) -> tuple[int, int]:
    """The pivot usage's cached input tokens (CAP-4): `prompt_tokens_details.cached_tokens`
    read from the cache (OpenAI's shape), `cache_write_tokens` written to it (the Anthropic
    adapter's); 0 when absent or unreadable."""
    details = usage.get("prompt_tokens_details")
    if not isinstance(details, dict):
        return 0, 0

    def count(name: str) -> int:
        value = details.get(name)
        if isinstance(value, bool) or not isinstance(value, int | float):
            return 0
        if not math.isfinite(value):  # `json.loads` reads `NaN` and `Infinity`
            return 0
        return max(0, int(value))

    return count("cached_tokens"), count("cache_write_tokens")


# The session's spend, every paid call counted (turns, sub-agent, « Tester », « LLM nu »),
# and its footprint (GreenOps), every call with an estimated footprint counted, local ones
# included: neither « Vider la conversation » nor « Réinitialiser » resets them, only a
# relaunch. Never written to disk.
_spend_lock = threading.Lock()
_EMPTY: dict[str, Any] = {
    "in": 0.0,
    "out": 0.0,
    "calls": 0,
    "approx": False,
    "wh_min": 0.0,
    "wh_max": 0.0,
    "g_min": 0.0,
    "g_max": 0.0,
    "impact_calls": 0,
}
_spend: dict[str, Any] = dict(_EMPTY)


def _spend_payload(eur_per_usd: float) -> dict[str, Any]:
    total = _spend["in"] + _spend["out"]
    return {
        "total_in_usd": _spend["in"],
        "total_out_usd": _spend["out"],
        "total_usd": total,
        "calls": _spend["calls"],
        "approx": _spend["approx"],
        "eur_per_usd": eur_per_usd,
        "total_eur": total * eur_per_usd,
        # GreenOps: the sums of the calls' ranges, `impact_calls` of them.
        "energy_wh_min": _spend["wh_min"],
        "energy_wh_max": _spend["wh_max"],
        "gco2e_min": _spend["g_min"],
        "gco2e_max": _spend["g_max"],
        "impact_calls": _spend["impact_calls"],
    }


def record_spend(
    cost: CallCost | None,
    eur_per_usd: float,
    emit: Callable[[dict[str, Any]], Any] | None = None,
    impact: Impact | None = None,
) -> dict[str, Any]:
    """Adds one call's cost (a cloud call with prices) and its footprint (GreenOps, when
    estimated; a local call has one and no cost) to the session's registry; returns the
    `consumption_updated` payload, read under the same lock. `emit` runs under that lock
    too: two concurrent calls emit their totals in the order they were added."""
    with _spend_lock:
        if cost is not None:
            _spend["in"] += cost.input_usd
            _spend["out"] += cost.output_usd
            _spend["calls"] += 1
            _spend["approx"] = _spend["approx"] or cost.source == "estimate"
        if impact is not None and impact.estimated:
            _spend["wh_min"] += impact.energy_wh_min
            _spend["wh_max"] += impact.energy_wh_max
            _spend["g_min"] += impact.gco2e_min
            _spend["g_max"] += impact.gco2e_max
            _spend["impact_calls"] += 1
        payload = _spend_payload(eur_per_usd)
        if emit is not None:
            emit(payload)
        return payload


def session_spend(eur_per_usd: float) -> dict[str, Any] | None:
    """The session's spend and footprint as `consumption_updated` carries them; `None`
    before a paid call or a call with a footprint."""
    with _spend_lock:
        counted = _spend["calls"] or _spend["impact_calls"]
        return _spend_payload(eur_per_usd) if counted else None


def session_cap_error(entry: CloudModel, max_session_usd: float | None) -> ProviderError | None:
    """CAP-4: the refusal of a priced call (an entry with `pricing`) once the session's
    total (`_spend`, the registry of `consumption_updated`) has reached `max_session_usd`;
    `None` when the call may go (no cap, no prices, or the total below the cap). Checked
    before the call is sent; a call under way is never stopped, so the total may exceed
    the cap by the cost of each call already under way when it was reached."""
    if max_session_usd is None or entry.pricing is None:
        return None
    with _spend_lock:
        total = _spend["in"] + _spend["out"]
    if total < max_session_usd:
        return None
    return ProviderError(
        Message(
            "models.openai_chat.session_cap",
            cap=Lazy(lambda lang: usd_price_fr(max_session_usd, lang)),
            total=Lazy(lambda lang: usd_price_fr(total, lang)),
        ),
        cause="max_session_usd",
        hints_text=[
            Message("models.openai_chat.hint.free_models"),
            _BACK_TO_LOCAL_FR,
        ],
    )


def reset_spend() -> None:
    """Tests only: a relaunch is the one reset of the session's spend."""
    with _spend_lock:
        _spend.update(_EMPTY)


class CloudEngine:
    """The `Engine` of a cloud model, whatever its API: input is a `ChatBody` (`input =
    "chat"`); it has no tokenizer, so `tokenize` and `token_pieces` are unavailable. A
    subclass names its `api` and its `endpoint` (the path after `base_url`), and reads its
    own stream (`_read`)."""

    input = "chat"
    api: ClassVar[str]
    endpoint: ClassVar[str]

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
        raise NotImplementedError(f"{self.api} has no local tokenizer (AD-5)")

    def token_pieces(self, ids: Any) -> list[bytes]:
        raise NotImplementedError(f"{self.api} has no local tokenizer (AD-5)")

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

    def prefill(self, ids: Sequence[int], cancel: CancelToken) -> int | None:
        return None  # E122: nothing to evaluate ahead at a provider

    @property
    def last_evaluated(self) -> int | None:
        return None

    def _text(self, key: str, **kw: Any) -> Message:
        """`models.openai_chat.{key}`, every plain text variable masked (AD-15)."""
        return Message(
            f"models.openai_chat.{key}",
            **{
                name: self.mask(value)
                if isinstance(value, str) and not isinstance(value, Message)
                else value
                for name, value in kw.items()
            },
        )

    def _error(
        self,
        message_text: Message,
        cause: str,
        hints_text: list[str],
        *,
        provider_message: str | None = None,
        **figures: Any,
    ) -> Any:
        """A masked `ProviderError`; `message_text` ends with the provider's own message, when
        its answer carries one (AD-16)."""
        if provider_message and provider_message.strip():
            message_text = self._text(
                "with_provider_message",
                message=message_text,
                said=_clip(self.mask(provider_message)),
            )
        return ProviderError(
            message_text, cause=_clip(self.mask(cause)), hints_text=hints_text, **figures
        )

    def _headers(self) -> dict[str, str]:
        """AD-5: `Content-Type`, the authentication header, then the entry's fixed
        `extra_headers` (never secret; masked in `outbound_request` all the same, since none
        is in `PUBLIC_HEADERS`)."""
        entry = self.entry
        scheme = entry.auth_header.scheme
        secret = self._key.get_secret_value()
        return {
            "Content-Type": "application/json",
            entry.auth_header.name: f"{scheme} {secret}" if scheme else secret,
            **entry.extra_headers,
        }

    def complete(self, body: ChatBody, cancel: CancelToken) -> Iterator[tuple[str, str] | ChatEnd]:
        """`(channel, text)` fragments, then one `ChatEnd`. Raises `ProviderError`."""
        entry = self.entry
        url = f"{entry.base_url}{self.endpoint}"
        try:
            with self._client.stream(
                "POST", url, content=body.body, headers=self._headers()
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
                self._text("timeout", provider=entry.provider),
                f"{type(exc).__name__}: {exc}",
                [
                    Message("models.openai_chat.hint.slow_provider"),
                    Message("models.openai_chat.hint.test_network"),
                ],
            ) from None
        except Exception as exc:
            if find_blocked(exc) is None and not isinstance(exc, httpx.TransportError):
                raise
            raise self._error(
                self._text("no_network", provider=entry.provider, host=entry.host),
                f"{type(exc).__name__}: {exc}",
                [
                    Message("models.openai_chat.hint.check_connection"),
                    Message("models.openai_chat.hint.allow_host", host=entry.host),
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
            location = response.headers.get("location")
            raise self._error(
                self._text(
                    "redirect",
                    provider=provider,
                    status=status,
                    location=Message("models.openai_chat.another_address")
                    if location is None
                    else location,
                ),
                cause,
                [Message("models.openai_chat.hint.check_base_url"), *local],
                http_status=status,
                **said,
            )
        if status == 429 and no_credit(error):  # native providers 4/5: add credit, not wait
            raise self._error(
                self._text("no_credit", provider=provider),
                cause,
                local,
                http_status=status,
                **said,
            )
        if status == 429 and _no_quota(response):
            # D6 of 2026-10-01: an account without any active quota (Mistral's workspace
            # without a plan) refuses every call; waiting or spacing would not help. The one
            # reading of an `x-ratelimit-*` header, for this message only (never a wait).
            raise self._error(
                self._text("no_quota", provider=provider),
                cause,
                local,
                http_status=status,
                **said,
            )
        if status == 429:
            retry = response.headers.get("retry-after")
            try:
                retry_after = float(retry) if retry else None
            except ValueError:
                retry_after = None
            wait = (
                [Message("models.openai_chat.hint.wait_seconds", seconds=f"{retry_after:g}")]
                if retry_after
                else []
            )
            scope = _quota_scope(message)
            interval = self.entry.min_interval_s
            spacing = (
                [
                    Message(
                        "models.openai_chat.hint.min_interval",
                        interval=f"{interval:g}",
                        model=self.entry.id,
                    )
                ]
                if interval
                else []
            )
            quota = _QUOTA_FR.get(scope, Message("models.openai_chat.quota.unknown"))
            raise self._error(
                self._text("quota_refused", quota=quota),
                cause,
                [
                    *(wait or [Message("models.openai_chat.hint.wait_a_bit")]),
                    *spacing,
                    Message("models.openai_chat.hint.reduce_context"),
                    *local,
                ],
                http_status=status,
                retry_after_s=retry_after,
                quota_scope=scope,
                **said,
            )
        if status == 413:
            raise self._error(
                self._text("too_large"),
                cause,
                [Message("models.openai_chat.hint.reduce_window"), *local],
                http_status=status,
                **said,
            )
        # OpenAI's code says it whatever its message (native providers 4/5).
        exceeded = error.get("code") == "context_length_exceeded"
        if status == 400 and (exceeded or any(w in message.lower() for w in _CONTEXT_WORDS)):
            raise self._error(
                self._text("context_exceeded", provider=provider),
                cause,
                [Message("models.openai_chat.hint.clear_conversation"), *local],
                http_status=status,
                **said,
            )
        if status in (400, 422):
            raise self._error(
                self._text("bad_request", provider=provider, status=status),
                cause,
                [Message("models.openai_chat.hint.check_declaration"), *local],
                http_status=status,
                **said,
            )
        if status in (401, 403):
            raise self._error(
                self._text("key_refused", provider=provider, status=status),
                cause,
                [Message("models.openai_chat.hint.reenter_key"), *local],
                http_status=status,
                **said,
            )
        if status == 404:
            raise self._error(
                self._text("not_found", provider=provider, model=self.entry.model),
                cause,
                [Message("models.openai_chat.hint.check_model_name"), *local],
                http_status=status,
                **said,
            )
        if status >= 500:
            raise self._error(
                self._text("unavailable", provider=provider, status=status),
                cause,
                [Message("models.openai_chat.hint.retry_later"), *local],
                http_status=status,
                **said,
            )
        raise self._error(
            self._text("unexpected", provider=provider, status=status),
            cause,
            local,
            http_status=status,
            **said,
        )

    def _read(
        self, response: httpx.Response, cancel: CancelToken
    ) -> Iterator[tuple[str, str] | ChatEnd]:
        """The API's own stream: `(channel, text)` fragments, masked, then one `ChatEnd`."""
        raise NotImplementedError


# ---------- one call, as `model_*` events (AD-2) ----------


@dataclass
class ChatCall:
    """What `run_call` read. `calls`: `{id, provider_id, name, arguments, parsed}`, `id` set
    only when every call is valid; `malformed`: `(reinjected, detail_text)` (AD-10)."""

    text: str = ""
    reasoning: str = ""
    stop_reason: str = "stop"
    channel: str = "text"  # the channel of the last fragment, for `output_truncated`
    calls: list[dict[str, Any]] = field(default_factory=list)
    malformed: tuple[str, str] | None = None
    usage: dict[str, Any] | None = None
    output_tokens: int = 0
    output_tps: int | None = None
    cost: CallCost | None = None  # FinOps: set when the entry declares its prices
    impact: Impact | None = None  # GreenOps: its footprint, or why it has none
    # Native providers 3/5 and 4/5: the provider's reasoning blocks (Anthropic) or `reasoning`
    # items (OpenAI's Responses API), verbatim, for its own entry only.
    thinking_blocks: list[dict[str, Any]] = field(default_factory=list)


# Native providers 4/5: the key a kept `reasoning` item carries for the `openai_responses`
# translator only (never sent): the item that followed it in the output, `message` or
# `call:<n>` (the n-th call). Here, so that `context/render.py` imports it from `models`.
FOLLOWS = "_follows"


# CAP-5: why a provider threw away the reasoning of an earlier turn (`input_transformations`);
# an unknown type or reason is ignored (Anthropic adds values over time).
DROP_REASONS = (
    "prefix_binding_mismatch",
    "model_binding_mismatch",
    "organization_binding_mismatch",
)


def reasoning_dropped(
    dropped: list[dict[str, Any]],
    provider: str,
    lang: str = "fr",
    mask: Callable[[str], str] = lambda text: text,
) -> list[dict[str, Any]]:
    """The `reasoning_dropped` payloads of a call's `input_transformations` (CAP-5): one per
    `thinking_dropped` entry of a known reason, `message_text` in `lang`, its `path` (the
    provider's string) through `mask` (AD-15)."""
    payloads = []
    for item in dropped:
        if not isinstance(item, dict) or item.get("type") != "thinking_dropped":
            continue
        reason = item.get("reason")
        if reason not in DROP_REASONS:
            continue
        path = mask(str(item.get("path") or ""))
        text = Message(
            f"models.openai_chat.reasoning_dropped.{reason}", provider=provider, path=path
        )
        payloads.append({"path": path, "reason": reason, "message_text": text.render(lang)})
    return payloads


def _reinjected(text: str, calls: list[dict[str, Any]]) -> str:
    """AD-10: `content`, then each call's `name` and `arguments` as emitted."""
    return "\n".join([text, *(f"{c['name']} {c['arguments']}" for c in calls)]).strip()


def _check_calls(calls: list[dict[str, Any]]) -> str | None:
    """Why the output's calls cannot run (AD-10), a `Message` (French as a text, rendered
    by the executor in the session's language); `None` when all are valid."""
    for call in calls:
        if not call["name"]:
            return Message("models.openai_chat.call.no_name")
        try:
            parsed = json.loads(call["arguments"] or "{}")
        except ValueError as exc:
            return Message("models.openai_chat.call.invalid_json", name=call["name"], cause=exc)
        if not isinstance(parsed, dict):
            return Message("models.openai_chat.call.not_object", name=call["name"])
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
    eur_per_usd: float = DEFAULT_EUR_PER_USD,
    lang: str = "fr",
    max_session_usd: float | None = None,
) -> ChatCall:
    """One streamed call under the caller's scope: `model_call_started`, `model_first_token`,
    `model_delta` (grouped), `model_call_ended`. Raises `ProviderError` after ending the call
    with `stop_reason: error`. `call_id(index)` gives a valid call's session id (AD-4).
    `sampling_trace` (story 29): `model_call_started.sampling`. FinOps: an entry with
    `pricing` gets the call's cost in `model_call_ended`, added to the session's spend, then
    `consumption_updated` (the total converted at `eur_per_usd`). GreenOps: likewise, the
    call's footprint as EcoLogits estimates it (`impacts`), or why it has none, its note in
    `lang` (the session's). `max_session_usd` (CAP-4): a priced call is refused before
    anything is sent or traced once the session's total has reached it (`ProviderError`,
    cause `max_session_usd`), checked before the spacing wait (a refused call takes no
    slot) and again after it (a concurrent call may have ended during the wait); calls
    already under way are never stopped, so the total may exceed the cap by the cost of
    each of them. `None` checks nothing."""
    entry = getattr(engine, "entry", None)
    if isinstance(entry, CloudModel):
        if (refused := session_cap_error(entry, max_session_usd)) is not None:
            raise refused
        # AD-16: the spacing wait, before the call starts, so neither `prompt_ms` nor
        # `duration_ms` counts it; cancelled while waiting, nothing is sent.
        if not pace(entry, cancel):
            return ChatCall(stop_reason="cancelled")
        if (refused := session_cap_error(entry, max_session_usd)) is not None:
            raise refused
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
        prompt_tokens = int(usage.get("prompt_tokens") or estimated_prompt)
        source = "api" if out.usage else "estimate"
        payload: dict[str, Any] = {
            "raw_output": raw_output,
            "reasoning": out.reasoning,
            "text": out.text,
            "tool_calls": [traced(c) for c in out.calls],
            "prompt_tokens": prompt_tokens,
            "output_tokens": out.output_tokens,
            "prompt_ms": round((first - started) * 1000),
            "gen_ms": gen_ms,
            "stop_reason": stop_reason,
            "duration_ms": round((now - started) * 1000),
            "output_tps": out.output_tps,
            "usage_source": source,
        }
        pricing = entry.pricing if isinstance(entry, CloudModel) else None
        # FinOps: a call refused before any output (an HTTP error, the network) is not billed,
        # unless the provider's usage came before the error (native providers 3/5).
        produced = stop_reason != "error" or first_at is not None or out.usage is not None
        if pricing is not None and produced:
            cached_read, cached_write = _cached_tokens(usage)
            out.cost = call_cost(
                pricing,
                prompt_tokens,
                out.output_tokens,
                source,
                cached_read=cached_read,
                cached_write=cached_write,
            )
            payload |= {
                "cost_in_usd": out.cost.input_usd,
                "cost_out_usd": out.cost.output_usd,
                "cost_source": source,
            }
        # GreenOps: nor has it a footprint; EcoLogits' latency is `duration_ms`.
        if isinstance(entry, CloudModel) and produced:
            out.impact = cloud_impacts(entry, out.output_tokens, payload["duration_ms"] / 1000)
            payload |= out.impact.fields(lang)
        journal.emit("model_call_ended", payload, actor="model")
        impact = out.impact if out.impact is not None and out.impact.estimated else None
        if out.cost is not None or impact is not None:
            record_spend(
                out.cost,
                eur_per_usd,
                lambda spend: journal.emit("consumption_updated", spend),
                impact=impact,
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
    except Exception as exc:  # a provider's refusal or anything else: the call still ends
        flush()
        out.text, out.reasoning = "".join(channels["text"]), "".join(channels["reasoning"])
        if isinstance(exc, ProviderError):  # native providers 3/5: what came before the error
            out.usage = exc.usage
            provider = entry.provider if isinstance(entry, CloudModel) else ""
            for dropped in reasoning_dropped(exc.dropped, provider, lang, mask):
                journal.emit("reasoning_dropped", dropped)
        ended("error", "")
        if isinstance(exc, ProviderError):
            exc.cost, exc.impact = out.cost, out.impact
        raise
    assert end is not None
    out.text, out.reasoning = "".join(channels["text"]), "".join(channels["reasoning"])
    out.stop_reason, out.usage, out.calls = end.stop_reason, end.usage, end.tool_calls
    out.thinking_blocks = end.thinking_blocks
    # CAP-5: the reasoning of an earlier turn the provider threw away, said with its cause.
    provider = entry.provider if isinstance(entry, CloudModel) else ""
    for dropped in reasoning_dropped(end.dropped, provider, lang, mask):
        journal.emit("reasoning_dropped", dropped)
    if end.provider_error is not None:
        detail = (
            Message("models.openai_chat.call.refused_with", said=end.provider_message)
            if end.provider_message
            else Message("models.openai_chat.call.refused")
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
