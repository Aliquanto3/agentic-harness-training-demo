"""`anthropic_messages` adapter (native providers 3/5, CAP-2): `POST {base_url}/messages`.

Anthropic's Messages API, streamed (SSE), raw HTTP through the common base (`cloud_base`):
`x-api-key` and the fixed `anthropic-version` and `anthropic-beta` headers come from the
entry (`auth_header`, `extra_headers`). The body is written by `context` alone (the
`anthropic_messages` translator of `context/render.py`, AD-4, AD-26). This module reads the
stream: `text_delta` on the `text` channel, `thinking_delta` on `reasoning`,
`input_json_delta` on `tool_call`; the `thinking` blocks (with their `signature`) and the
`redacted_thinking` ones are kept verbatim, in the order received, for the next call of the
same entry (`ChatEnd.thinking_blocks`); `message_start`'s `input_transformations` (blocks of
an earlier turn the provider threw away, CAP-5) go back to `run_call` (`ChatEnd.dropped`).

`usage` is converted to the pivot (Chat Completions) shape: `prompt_tokens` counts the plain
input plus the tokens read from and written to the provider's cache, which
`prompt_tokens_details` details (CAP-4); `completion_tokens` is the last `output_tokens` of
`message_delta` (cumulative, the thinking included).
"""

from __future__ import annotations

import json
from collections.abc import Iterator
from typing import Any

import httpx

from wavestack.messages import Message
from wavestack.models.cloud_base import _BACK_TO_LOCAL_FR, ChatEnd, CloudEngine, ProviderError
from wavestack.models.engine import CancelToken

# `stop_reason` → the pivot's; `refusal` and any other value raise (AD-16).
_FINISH = {"end_turn": "stop", "tool_use": "stop", "stop_sequence": "stop", "max_tokens": "length"}


def _count(value: Any) -> int:
    return value if isinstance(value, int) and not isinstance(value, bool) and value > 0 else 0


def _merge(usage: dict[str, Any], update: Any) -> None:
    """`message_delta`'s usage over `message_start`'s, its `null` values left out."""
    if isinstance(update, dict):
        usage.update({key: value for key, value in update.items() if value is not None})


def pivot_usage(usage: dict[str, Any]) -> dict[str, Any]:
    """Anthropic's `usage` in the pivot shape (CAP-4): `prompt_tokens = input_tokens +
    cache_read_input_tokens + cache_creation_input_tokens`, `prompt_tokens_details` with the
    tokens read from the cache (`cached_tokens`) and written to it (`cache_write_tokens`),
    `completion_tokens` the output, thinking included."""
    plain = _count(usage.get("input_tokens"))
    read = _count(usage.get("cache_read_input_tokens"))
    written = _count(usage.get("cache_creation_input_tokens"))
    output = _count(usage.get("output_tokens"))
    prompt = plain + read + written
    return {
        "prompt_tokens": prompt,
        "completion_tokens": output,
        "total_tokens": prompt + output,
        "prompt_tokens_details": {"cached_tokens": read, "cache_write_tokens": written},
    }


class AnthropicMessagesEngine(CloudEngine):
    """The Messages adapter: `POST {base_url}/messages`, its SSE events read by `_read`."""

    api = "anthropic_messages"
    endpoint = "/messages"

    def _read(
        self, response: httpx.Response, cancel: CancelToken
    ) -> Iterator[tuple[str, str] | ChatEnd]:
        """The stream; a `ProviderError` raised after `message_start` carries the usage and
        the `input_transformations` read by then: the input is billed, the drops traced."""
        usage: dict[str, Any] = {}
        dropped: list[dict[str, Any]] = []
        try:
            yield from self._stream(response, cancel, usage, dropped)
        except ProviderError as error:
            error.usage = pivot_usage(usage) if usage else None
            error.dropped = list(dropped)
            raise

    def _stream(
        self,
        response: httpx.Response,
        cancel: CancelToken,
        usage: dict[str, Any],
        dropped: list[dict[str, Any]],
    ) -> Iterator[tuple[str, str] | ChatEnd]:
        """`_read`'s work; `usage` and `dropped` are filled in place as they are read."""
        entry = self.entry
        blocks: dict[int, dict[str, Any]] = {}  # index → the content block being received
        raw: list[str] = []
        stop = None
        for line in response.iter_lines():
            if cancel.cancelled:
                stop = "cancelled"
                break  # leaving the `with` closes the stream (AD-5)
            if not line or line.startswith((":", "event:", "id:", "retry:")):
                continue
            data = line[5:].strip() if line.startswith("data:") else None
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
                raise self._stream_error(event)
            if kind == "message_start":
                message = event.get("message") or {}
                _merge(usage, message.get("usage"))
                transformations = message.get("input_transformations")
                if isinstance(transformations, list):
                    dropped[:] = [t for t in transformations if isinstance(t, dict)]
                continue
            if kind == "message_delta":
                _merge(usage, event.get("usage"))
                delta = event.get("delta") or {}
                if delta.get("stop_reason"):
                    stop = self._finish(delta.get("stop_reason"), delta.get("stop_details"))
                continue
            if kind not in ("content_block_start", "content_block_delta"):
                continue  # `ping`, `content_block_stop`, `message_stop`, any new event
            raw.append(data or "")
            index = event.get("index")
            if kind == "content_block_start":
                block = event.get("content_block") or {}
                blocks[index] = dict(block)
                if block.get("type") == "tool_use":
                    blocks[index] |= {"partial": ""}
                elif block.get("type") == "text" and block.get("text"):
                    yield "text", self.mask(str(block["text"]))
                elif block.get("type") == "thinking" and block.get("thinking"):
                    yield "reasoning", self.mask(str(block["thinking"]))
                continue
            block = blocks.setdefault(index, {})
            delta = event.get("delta") or {}
            if delta.get("type") == "text_delta" and delta.get("text"):
                block["text"] = block.get("text", "") + delta["text"]
                yield "text", self.mask(str(delta["text"]))
            elif delta.get("type") == "thinking_delta" and delta.get("thinking"):
                block["thinking"] = block.get("thinking", "") + delta["thinking"]
                yield "reasoning", self.mask(str(delta["thinking"]))
            elif delta.get("type") == "signature_delta":
                # Verbatim for the next call (never masked here); masked in `raw_output`.
                block["signature"] = block.get("signature", "") + str(delta.get("signature", ""))
            elif delta.get("type") == "input_json_delta" and delta.get("partial_json"):
                block["partial"] = block.get("partial", "") + delta["partial_json"]
                yield "tool_call", self.mask(str(delta["partial_json"]))
        if stop is None:
            # The stream ended without `message_delta`'s `stop_reason`: cut short.
            raise self._error(
                self._text("interrupted", provider=entry.provider),
                "stop_reason absent",
                [Message("models.openai_chat.hint.retry_turn"), _BACK_TO_LOCAL_FR],
            )
        ordered = [blocks[i] for i in sorted(blocks, key=lambda i: (not isinstance(i, int), i))]
        calls = [
            {
                "provider_id": self.mask(str(b.get("id") or "")) or None,
                "name": self.mask(str(b.get("name") or "")),
                # A call without input deltas sends `{}`.
                "arguments": self.mask(b.get("partial") or json.dumps(b.get("input") or {})),
            }
            for b in ordered
            if b.get("type") == "tool_use"
        ]
        thinking = [
            {"type": "thinking", "thinking": b.get("thinking", ""), "signature": b["signature"]}
            if b.get("type") == "thinking"
            else {"type": "redacted_thinking", "data": b.get("data", "")}
            for b in ordered
            if b.get("type") == "redacted_thinking"
            or (b.get("type") == "thinking" and b.get("signature"))
        ]
        yield ChatEnd(
            stop,
            calls,
            pivot_usage(usage) if usage else None,
            self.mask("\n".join(raw)),
            thinking_blocks=thinking,
            dropped=list(dropped),
        )

    def _finish(self, reason: Any, details: Any) -> str:
        """`stop_reason` in the pivot's terms; a refusal, the context window exceeded, or a stop
        the harness cannot go on from (`pause_turn`, any new value), raises (AD-16)."""
        provider = self.entry.provider
        if reason in _FINISH:
            return _FINISH[reason]
        if reason == "model_context_window_exceeded":  # as the 400 « prompt is too long »
            raise self._error(
                self._text("context_exceeded", provider=provider),
                f"stop_reason: {reason}",
                [Message("models.openai_chat.hint.clear_conversation"), _BACK_TO_LOCAL_FR],
            )
        if reason == "refusal":
            category = details.get("category") if isinstance(details, dict) else None
            message = (
                self._text("refusal_category", provider=provider, category=str(category))
                if category
                else self._text("refusal", provider=provider)
            )
            raise self._error(
                message,
                f"stop_reason: refusal ({category})" if category else "stop_reason: refusal",
                [Message("models.openai_chat.hint.rephrase"), _BACK_TO_LOCAL_FR],
            )
        raise self._error(
            self._text("stopped", provider=provider, finish=str(reason)),
            f"stop_reason: {reason}",
            [Message("models.openai_chat.hint.rephrase"), _BACK_TO_LOCAL_FR],
        )

    def _stream_error(self, event: dict[str, Any]) -> Exception:
        """An `error` event after the 200 (AD-16): `overloaded_error` says the provider is
        unavailable, any other the response was interrupted; never retried."""
        error = event.get("error") if isinstance(event.get("error"), dict) else {}
        kind = str(error.get("type") or "error")
        said = str(error.get("message") or kind)
        provider = self.entry.provider
        if kind in ("overloaded_error", "api_error"):
            return self._error(
                self._text("unavailable", provider=provider, status=kind),
                f"{kind}: {said}",
                [Message("models.openai_chat.hint.retry_later"), _BACK_TO_LOCAL_FR],
                provider_message=said,
            )
        return self._error(
            self._text("interrupted", provider=provider),
            f"{kind}: {said}",
            [Message("models.openai_chat.hint.retry_turn"), _BACK_TO_LOCAL_FR],
            provider_message=said,
        )
