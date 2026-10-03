"""`openai_responses` adapter (native providers 4/5, CAP-3): `POST {base_url}/responses`.

OpenAI's Responses API, streamed (SSE), stateless (`store: false`, never
`previous_response_id`), raw HTTP through the common base (`cloud_base`), the key in
`Authorization: Bearer` (the default `auth_header`). The body is written by `context` alone
(the `openai_responses` translator of `context/render.py`, AD-4, AD-26). This module reads
the stream: `response.output_text.delta` on the `text` channel,
`response.reasoning_summary_text.delta` on `reasoning`, `response.function_call_arguments.delta`
on `tool_call`; the `reasoning` items (`response.output_item.done`, their
`encrypted_content` and `summary` included) are kept verbatim, in the order received, for
the next call of the same entry (`ChatEnd.thinking_blocks`, the channel of Anthropic's
blocks).

`usage` is converted to the pivot (Chat Completions) shape: `prompt_tokens = input_tokens`,
`prompt_tokens_details.cached_tokens` the tokens read from the provider's cache (CAP-4),
`completion_tokens = output_tokens` (the reasoning tokens included).
"""

from __future__ import annotations

import json
from collections.abc import Iterator
from typing import Any

import httpx

from wavestack.messages import Message
from wavestack.models.cloud_base import (
    _BACK_TO_LOCAL_FR,
    FOLLOWS,
    ChatEnd,
    CloudEngine,
    ProviderError,
    no_credit,
)
from wavestack.models.engine import CancelToken

# `response.failed`'s and `error`'s codes that say the provider is unavailable.
_UNAVAILABLE = ("server_error", "rate_limit_exceeded", "overloaded", "service_unavailable")


def _count(value: Any) -> int:
    return value if isinstance(value, int) and not isinstance(value, bool) and value > 0 else 0


def pivot_usage(usage: dict[str, Any]) -> dict[str, Any]:
    """The Responses `usage` in the pivot shape (CAP-4): `prompt_tokens = input_tokens` (the
    cached tokens included), `prompt_tokens_details.cached_tokens` those read from the cache,
    `completion_tokens = output_tokens` (the reasoning included, detailed in
    `completion_tokens_details.reasoning_tokens`)."""
    details = usage.get("input_tokens_details")
    out_details = usage.get("output_tokens_details")
    prompt = _count(usage.get("input_tokens"))
    output = _count(usage.get("output_tokens"))
    cached = _count(details.get("cached_tokens")) if isinstance(details, dict) else 0
    reasoning = _count(out_details.get("reasoning_tokens")) if isinstance(out_details, dict) else 0
    return {
        "prompt_tokens": prompt,
        "completion_tokens": output,
        "total_tokens": prompt + output,
        "prompt_tokens_details": {"cached_tokens": cached},
        "completion_tokens_details": {"reasoning_tokens": reasoning},
    }


def _reasoning_items(ordered: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """The output's `reasoning` items, verbatim (never masked here, AD-15: masked in
    `raw_output` only), in the order received; only the finished ones (`encrypted_content`,
    from `response.output_item.done`). Each carries `FOLLOWS`, the item that came right after
    it, for the translator to send it back in the same place: OpenAI refuses a reasoning item
    not followed by the item it preceded."""
    kept: list[dict[str, Any]] = []
    pending: list[dict[str, Any]] = []
    calls = 0
    for item in ordered:
        kind = item.get("type")
        if kind == "reasoning":
            if item.get("encrypted_content"):
                pending.append(dict(item))
                kept.append(pending[-1])
            continue
        if kind == "function_call":
            follower = f"call:{calls}"
            calls += 1
        elif kind == "message":
            follower = "message"
        else:
            continue
        for waiting in pending:
            waiting[FOLLOWS] = follower
        pending = []
    return kept


class OpenAIResponsesEngine(CloudEngine):
    """The Responses adapter: `POST {base_url}/responses`, its SSE events read by `_read`."""

    api = "openai_responses"
    endpoint = "/responses"

    def _read(
        self, response: httpx.Response, cancel: CancelToken
    ) -> Iterator[tuple[str, str] | ChatEnd]:
        """The stream; a `ProviderError` raised once the provider gave its usage
        (`response.failed`, `response.incomplete`) carries it: the input is billed. An `error`
        event is raised when the stream ends or fails, so that the usage that follows counts."""
        usage: dict[str, Any] = {}
        try:
            yield from self._stream(response, cancel, usage)
        except ProviderError as error:
            error.usage = pivot_usage(usage) if usage else None
            raise

    def _stream(
        self, response: httpx.Response, cancel: CancelToken, usage: dict[str, Any]
    ) -> Iterator[tuple[str, str] | ChatEnd]:
        """`_read`'s work; `usage` is filled in place once read."""
        entry = self.entry
        items: dict[Any, dict[str, Any]] = {}  # output_index (or item id) → the item
        keys: dict[str, Any] = {}  # item id → its key in `items`
        raw: list[str] = []
        summary: tuple[Any, Any] | None = None  # the summary part being received
        said = False  # a reasoning fragment already went out (parts are separated)
        failure: Any = None  # an `error` event's error, raised once the stream says no more
        stop = None
        for line in response.iter_lines():
            if cancel.cancelled:
                # A terminal event ends the loop: an answer read to its end is never here.
                stop = "cancelled"
                break  # leaving the `with` closes the stream (AD-5)
            if not line or line.startswith((":", "event:", "id:", "retry:")):
                continue
            data = line[5:].strip() if line.startswith("data:") else None
            if data == "[DONE]":
                break
            try:
                event = json.loads(data) if data is not None else None
            except ValueError:
                event = None
            if not isinstance(event, dict):
                raise self._error(
                    self._text("unreadable_stream", provider=entry.provider),
                    line[:300],
                    [Message("models.openai_chat.hint.retry_turn"), _BACK_TO_LOCAL_FR],
                )
            kind = event.get("type")
            if kind == "error":
                # Measured on 2026-10-03: `response.failed` follows, with the usage if any.
                failure = event.get("error") if "error" in event else event
                continue
            if kind in ("response.completed", "response.incomplete", "response.failed"):
                answer = event.get("response") or {}
                if isinstance(answer.get("usage"), dict):
                    usage.clear()
                    usage.update(answer["usage"])
                if kind == "response.failed" or failure is not None:
                    raise self._failure(failure or answer.get("error"))
                if kind == "response.incomplete":
                    stop = self._incomplete(answer.get("incomplete_details"))
                else:
                    stop = "stop"
                break  # a terminal event: nothing after it is read
            if kind in ("response.output_item.added", "response.output_item.done"):
                item = event.get("item") or {}
                key = event.get("output_index", item.get("id"))
                if kind == "response.output_item.done":
                    raw.append(data or "")
                    if item.get("type") == "function_call" and key in items:
                        # The arguments as streamed, else those of the finished item.
                        partial = items[key].get("partial") or str(item.get("arguments") or "")
                        items[key] = dict(item) | {"partial": partial}
                    else:
                        items[key] = dict(item)
                else:
                    items[key] = dict(item) | (
                        {"partial": ""} if item.get("type") == "function_call" else {}
                    )
                if item.get("id"):
                    keys[str(item["id"])] = key
                continue
            key = event.get("output_index")
            if key is None:
                key = keys.get(str(event.get("item_id")), event.get("item_id"))
            delta = event.get("delta")
            if kind == "response.output_text.delta" and isinstance(delta, str) and delta:
                yield "text", self.mask(delta)
            elif kind == "response.refusal.delta" and isinstance(delta, str) and delta:
                yield "text", self.mask(delta)  # the model's refusal, said as its answer
            elif (
                kind == "response.reasoning_summary_text.delta" and isinstance(delta, str) and delta
            ):
                part = (event.get("item_id", key), event.get("summary_index"))
                if said and part != summary:
                    yield "reasoning", "\n\n"  # one summary part, or one item, from the next
                summary, said = part, True
                yield "reasoning", self.mask(delta)
            elif (
                kind == "response.function_call_arguments.delta"
                and isinstance(delta, str)
                and delta
            ):
                call = items.setdefault(key, {"type": "function_call", "partial": ""})
                call["partial"] = call.get("partial", "") + delta
                yield "tool_call", self.mask(delta)
        if failure is not None and stop != "cancelled":
            raise self._failure(failure)  # an `error` event the stream did not follow
        if stop is None:
            # The stream ended without `response.completed`: cut short.
            raise self._error(
                self._text("interrupted", provider=entry.provider),
                "response.completed absent",
                [Message("models.openai_chat.hint.retry_turn"), _BACK_TO_LOCAL_FR],
            )
        # By `output_index`; an item without one (keyed by its id) after, in arrival order.
        ordered = [items[k] for k in sorted(k for k in items if isinstance(k, int))] + [
            items[k] for k in items if not isinstance(k, int)
        ]
        calls = [
            {
                "provider_id": self.mask(str(i.get("call_id") or "")) or None,
                "name": self.mask(str(i.get("name") or "")),
                # A call without arguments sends `{}`.
                "arguments": self.mask(i.get("partial") or str(i.get("arguments") or "{}")),
            }
            for i in ordered
            if i.get("type") == "function_call"
        ]
        yield ChatEnd(
            stop,
            calls,
            pivot_usage(usage) if usage else None,
            self.mask("\n".join(raw)),
            thinking_blocks=_reasoning_items(ordered),
        )

    def _incomplete(self, details: Any) -> str:
        """`response.incomplete`: `length` when the output limit cut it, else an explained
        error, the reason quoted (AD-16)."""
        reason = details.get("reason") if isinstance(details, dict) else None
        if reason == "max_output_tokens":
            return "length"
        reason = str(reason or "incomplete")
        raise self._error(
            self._text("stopped", provider=self.entry.provider, finish=reason),
            f"incomplete: {reason}",
            [Message("models.openai_chat.hint.rephrase"), _BACK_TO_LOCAL_FR],
        )

    def _failure(self, error: Any) -> Exception:
        """`response.failed` or an `error` event after the 200 (AD-16): the context window
        exceeded, the provider unavailable, or the response interrupted; never retried."""
        error = error if isinstance(error, dict) else {}
        code = str(error.get("code") or error.get("type") or "error")
        said = str(error.get("message") or code)
        provider = self.entry.provider
        if no_credit(error):
            # Measured on 2026-10-03: an account without credit gets a 200, then `error`
            # (`insufficient_quota`, `credit_balance_exhausted`) and `response.failed`.
            return self._error(
                self._text("no_credit", provider=provider),
                f"{code}: {said}",
                [_BACK_TO_LOCAL_FR],
                provider_message=said,
            )
        if code == "context_length_exceeded":
            return self._error(
                self._text("context_exceeded", provider=provider),
                f"{code}: {said}",
                [Message("models.openai_chat.hint.clear_conversation"), _BACK_TO_LOCAL_FR],
                provider_message=said,
            )
        if code in _UNAVAILABLE:
            return self._error(
                self._text("unavailable", provider=provider, status=code),
                f"{code}: {said}",
                [Message("models.openai_chat.hint.retry_later"), _BACK_TO_LOCAL_FR],
                provider_message=said,
            )
        return self._error(
            self._text("interrupted", provider=provider),
            f"{code}: {said}",
            [Message("models.openai_chat.hint.retry_turn"), _BACK_TO_LOCAL_FR],
            provider_message=said,
        )
