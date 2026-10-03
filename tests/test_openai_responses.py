"""Native providers (4/5): GPT-6 Luna through OpenAI's Responses API (CAP-3).

A fake SSE server (`httpx.MockTransport`) plays the Responses stream, in the shapes read on
the real API on 2026-10-03 (`response.created`, `error` then `response.failed`): nothing
leaves the machine. Each line of the story's matrix, the body sent equal to the one traced,
the `reasoning` items sent back verbatim to their own entry only, and the bodies of
`openai_luna` with the reasoning on and off.
"""

from __future__ import annotations

import json
import logging
from typing import Any

import httpx
import pytest
from pydantic import SecretStr
from test_cloud import SENTINEL, _journal_text, _no_sentinel, _of, _turn

from wavestack import config
from wavestack.cloud import chat_fields
from wavestack.context import render as render_module
from wavestack.context.render import render_chat_body
from wavestack.context.segments import Part, SegmentKind
from wavestack.models.cloud_api import create_cloud_engine
from wavestack.models.cloud_base import ChatBody, ProviderError, reset_spend
from wavestack.models.engine import DEFAULT_SAMPLING, CancelToken
from wavestack.models.openai_responses import OpenAIResponsesEngine
from wavestack.session.app_session import AppSession
from wavestack.trace.journal import get_journal

# An encrypted reasoning holding the key's last 4 characters: verbatim in the body sent,
# masked in the events that do not trace the bytes sent (AD-15).
ENCRYPTED_1 = f"gAAAAABlbmNyeXB0ZWQ{SENTINEL[-4:]}LTE="
ENCRYPTED_2 = "gAAAAABlbmNyeXB0ZWQtMg=="


def sse(*events: dict[str, Any]) -> bytes:
    return "".join(f"event: {e['type']}\ndata: {json.dumps(e)}\n\n" for e in events).encode()


def created() -> dict[str, Any]:
    response = {"id": "resp_1", "object": "response", "status": "in_progress", "usage": None}
    return {"type": "response.created", "response": response}


def reasoning(index: int, item_id: str, encrypted: str, *texts: str) -> list[dict[str, Any]]:
    where = {"item_id": item_id, "output_index": index}
    events: list[dict[str, Any]] = [
        {
            "type": "response.output_item.added",
            "output_index": index,
            "item": {"id": item_id, "type": "reasoning", "summary": []},
        }
    ]
    for n, text in enumerate(texts):
        part = {"type": "summary_text", "text": ""}
        events += [
            {"type": "response.reasoning_summary_part.added", **where, "summary_index": n}
            | {"part": part},
            *(
                {
                    "type": "response.reasoning_summary_text.delta",
                    **where,
                    "summary_index": n,
                    "delta": piece,
                }
                for piece in (text[: len(text) // 2], text[len(text) // 2 :])
            ),
            {
                "type": "response.reasoning_summary_text.done",
                **where,
                "summary_index": n,
                "text": text,
            },
        ]
    item = {
        "id": item_id,
        "type": "reasoning",
        "encrypted_content": encrypted,
        "summary": [{"type": "summary_text", "text": t} for t in texts],
    }
    events.append({"type": "response.output_item.done", "output_index": index, "item": item})
    return events


def message(index: int, *pieces: str) -> list[dict[str, Any]]:
    item_id = f"msg_{index}"
    where = {"item_id": item_id, "output_index": index, "content_index": 0}
    added = {"id": item_id, "type": "message", "role": "assistant", "content": []}
    done = added | {
        "status": "completed",
        "content": [{"type": "output_text", "text": "".join(pieces), "annotations": []}],
    }
    return [
        {"type": "response.output_item.added", "output_index": index, "item": added},
        *({"type": "response.output_text.delta", **where, "delta": p} for p in pieces),
        {"type": "response.output_text.done", **where, "text": "".join(pieces)},
        {"type": "response.output_item.done", "output_index": index, "item": done},
    ]


def function_call(index: int, call_id: str, name: str, *pieces: str) -> list[dict[str, Any]]:
    item_id = f"fc_{index}"
    added = {
        "id": item_id,
        "type": "function_call",
        "status": "in_progress",
        "arguments": "",
        "call_id": call_id,
        "name": name,
    }
    where = {"item_id": item_id, "output_index": index}
    return [
        {"type": "response.output_item.added", "output_index": index, "item": added},
        *({"type": "response.function_call_arguments.delta", **where, "delta": p} for p in pieces),
        {"type": "response.function_call_arguments.done", **where, "arguments": "".join(pieces)},
        {
            "type": "response.output_item.done",
            "output_index": index,
            "item": added | {"status": "completed", "arguments": "".join(pieces)},
        },
    ]


def usage(input_tokens: int, output_tokens: int, cached: int = 0, thought: int = 0) -> dict:
    return {
        "input_tokens": input_tokens,
        "input_tokens_details": {"cached_tokens": cached},
        "output_tokens": output_tokens,
        "output_tokens_details": {"reasoning_tokens": thought},
        "total_tokens": input_tokens + output_tokens,
    }


def completed(input_tokens: int, output_tokens: int, **more: int) -> dict[str, Any]:
    response = {
        "id": "resp_1",
        "status": "completed",
        "usage": usage(input_tokens, output_tokens, **more),
    }
    return {"type": "response.completed", "response": response}


def incomplete(reason: str, input_tokens: int = 100, output_tokens: int = 512) -> dict:
    response = {
        "id": "resp_1",
        "status": "incomplete",
        "incomplete_details": {"reason": reason},
        "usage": usage(input_tokens, output_tokens),
    }
    return {"type": "response.incomplete", "response": response}


THINK_TOOL = sse(
    created(),
    *reasoning(0, "rs_1", ENCRYPTED_1, "Il faut calculer."),
    *function_call(1, "call_01", "calculator", '{"expression": ', '"2+3"}'),
    completed(700, 40, thought=20),
)
THINK_TEXT = sse(
    created(),
    *reasoning(0, "rs_2", ENCRYPTED_2, "Le résultat suffit."),
    *message(1, "Cela fait ", "5."),
    completed(760, 30, thought=10),
)
PLAIN_TEXT = sse(created(), *message(0, "Bonjour."), completed(800, 5))


class Provider:
    """A scripted OpenAI: one response per request, the last one repeated."""

    def __init__(self, *responses: httpx.Response | bytes) -> None:
        self.responses = responses
        self.requests: list[httpx.Request] = []

    def __call__(self, request: httpx.Request) -> httpx.Response:
        self.requests.append(request)
        answer = self.responses[min(len(self.requests) - 1, len(self.responses) - 1)]
        if isinstance(answer, bytes):
            return httpx.Response(
                200, content=answer, headers={"content-type": "text/event-stream"}
            )
        return answer

    def body(self, n: int) -> dict[str, Any]:
        return json.loads(self.requests[n].content)


def _entry(model_id: str = "openai_luna") -> config.CloudModel:
    entry = config.load_config().cloud_model(model_id)
    assert entry is not None
    return entry


def _session(provider: Provider, *, bricks=(), model_id: str = "openai_luna") -> AppSession:
    cfg = config.load_config()
    entry = _entry(model_id)
    config.write_api_key(entry.id, entry.host, SecretStr(SENTINEL))

    def factory(entry, key):  # noqa: ANN001, ANN202
        return create_cloud_engine(
            entry,
            key,
            connect_timeout_s=1.0,
            read_timeout_s=5.0,
            transport=httpx.MockTransport(provider),
        )

    session = AppSession(cfg, cloud_factory=factory)
    session.boot_cloud(entry).result()
    for brick in bricks:
        session.set_brick(brick, True)
    session.join()
    return session


def _one_turn(stream: bytes | httpx.Response, *more: bytes) -> tuple[list, Provider]:
    provider = Provider(stream, *more)
    session = _session(provider)
    try:
        events = _turn(session, "Bonjour")
    finally:
        session.close()
    return events, provider


@pytest.fixture(autouse=True)
def _spend():
    reset_spend()
    yield
    reset_spend()


def _assert_sent_as_traced(events: list, provider: Provider) -> None:
    rendered = _of(events, "context_rendered")
    outbound = _of(events, "outbound_request")
    assert len(rendered) == len(outbound) == len(provider.requests)
    for ctx, out, request in zip(rendered, outbound, provider.requests, strict=True):
        # CAP-1: the body sent = `context_rendered.body` = `outbound_request.body`.
        assert request.content == ctx.payload["body"].encode("utf-8")
        assert out.payload["body"] == ctx.payload["body"] and out.call_id == ctx.call_id
        # AD-4: the segments are the bytes sent.
        assert "".join(s["text"] for s in ctx.payload["segments"]) == ctx.payload["body"]


# ---------- the acceptance: a tools turn with the reasoning on, then a reasoning turn ----------


def test_a_tools_turn_then_a_reasoning_turn_send_the_reasoning_items_back(caplog):
    caplog.set_level(logging.DEBUG)
    provider = Provider(THINK_TOOL, THINK_TEXT, THINK_TEXT)
    session = _session(provider, bricks=("system_prompt", "short_memory", "tools", "reasoning"))
    try:
        first = _turn(session, "Combien font 2 + 3 ?")
        second = _turn(session, "Et 3 + 4 ?")
    finally:
        session.close()

    assert [_of(t, "turn_ended")[0].payload["status"] for t in (first, second)] == ["completed"] * 2
    assert _of(first, "harness_error") == [] and len(provider.requests) == 3
    _assert_sent_as_traced(first + second, provider)

    request = provider.requests[0]
    assert request.url == "https://api.openai.com/v1/responses"
    assert request.headers["authorization"] == f"Bearer {SENTINEL}"
    traced = {h["name"]: h for h in _of(first, "outbound_request")[0].payload["headers"]}
    assert traced["Authorization"]["masked"] and traced["Authorization"]["value"] == "[masqué]"

    body = provider.body(0)
    assert body["model"] == "gpt-6-luna" and body["stream"] is True
    assert body["max_output_tokens"] == 1536 and body["instructions"]
    assert body["reasoning"] == {"effort": "low", "summary": "auto"}
    assert body["store"] is False and body["include"] == ["reasoning.encrypted_content"]
    assert "temperature" not in body and "max_tokens" not in body and "messages" not in body
    assert "previous_response_id" not in body and "stream_options" not in body
    calculator = next(t for t in body["tools"] if t["name"] == "calculator")
    assert calculator["type"] == "function" and calculator["parameters"]["type"] == "object"
    assert "function" not in calculator and calculator["description"]
    assert calculator["strict"] is False
    assert body["input"] == [{"type": "message", "role": "user", "content": "Combien font 2 + 3 ?"}]

    # The summary on the Reasoning channel; the call's id is the session's in the next body.
    channels = {d.payload["channel"] for d in _of(first, "model_delta")}
    assert channels == {"reasoning", "tool_call", "text"}
    ended = _of(first, "model_call_ended")
    assert ended[0].payload["reasoning"] == "Il faut calculer."
    assert ended[1].payload["text"] == "Cela fait 5."
    assert ended[0].payload["prompt_tokens"] == 700 and ended[0].payload["output_tokens"] == 40
    call = ended[0].payload["tool_calls"][0]
    assert call["provider_id"] == "call_01" and call["arguments"] == '{"expression": "2+3"}'
    # AD-15: the encrypted reasoning is masked in the events that are not the bytes sent.
    assert ENCRYPTED_1 not in ended[0].payload["raw_output"]
    assert "gAAAAABlbmNyeXB0ZWQ•••LTE=" in ended[0].payload["raw_output"]

    # The second call: the reasoning item first, verbatim (`id` included), then the call.
    items = provider.body(1)["input"]
    assert items[1] == {
        "id": "rs_1",
        "type": "reasoning",
        "encrypted_content": ENCRYPTED_1,
        "summary": [{"type": "summary_text", "text": "Il faut calculer."}],
    }
    assert items[2] == {
        "type": "function_call",
        "call_id": call["id"],
        "name": "calculator",
        "arguments": '{"expression": "2+3"}',
    }
    assert items[3]["type"] == "function_call_output" and items[3]["call_id"] == call["id"]
    assert isinstance(items[3]["output"], str) and "5" in items[3]["output"]

    # The reasoning turn: both turns' items go back, each right before its turn's items.
    history = provider.body(2)["input"]
    assert [i["type"] for i in history] == [
        "message",
        "reasoning",
        "function_call",
        "function_call_output",
        "reasoning",
        "message",
        "message",
    ]
    assert history[4]["id"] == "rs_2" and history[4]["encrypted_content"] == ENCRYPTED_2
    assert history[5] == {"type": "message", "role": "assistant", "content": "Cela fait 5."}
    assert history[1]["encrypted_content"] == ENCRYPTED_1

    # AD-4: the summary text is attributed like the reasoning, the encrypted part to `template`.
    segments = _of(second, "context_rendered")[0].payload["segments"]
    owner = next(s for s in segments if s["text"] == "Le résultat suffit.")
    assert owner["kind"] == "history"
    assert all(ENCRYPTED_2 not in s["text"] or s["kind"] == "template" for s in segments)
    _no_sentinel(_journal_text(), caplog.text)


def test_the_reasoning_items_never_go_to_another_entry():
    provider = Provider(THINK_TEXT, PLAIN_TEXT)
    session = _session(provider, bricks=("short_memory", "reasoning"))
    try:
        _turn(session, "Bonjour")
        session._cloud = _entry("claude_haiku")  # the same history, for Claude
        _turn(session, "Encore")
    finally:
        session.close()
    sent = provider.requests[1].content.decode()
    assert ENCRYPTED_2 not in sent and "rs_2" not in sent
    second = provider.body(1)
    assert second["messages"][1] == {
        "role": "assistant",
        "content": [{"type": "text", "text": "Cela fait 5."}],
    }


def test_with_the_reasoning_brick_off_no_reasoning_item_is_sent_back():
    provider = Provider(THINK_TEXT, PLAIN_TEXT)
    session = _session(provider, bricks=("short_memory", "reasoning"))
    try:
        _turn(session, "Bonjour")
        session.set_brick("reasoning", False)
        session.join()
        _turn(session, "Encore")
    finally:
        session.close()
    second = provider.body(1)
    assert second["reasoning"] == {"effort": "none"}  # Luna has no `minimal`
    assert second["max_output_tokens"] == 512
    assert second["store"] is False and second["include"] == ["reasoning.encrypted_content"]
    assert ENCRYPTED_2 not in provider.requests[1].content.decode()
    assert [i["type"] for i in second["input"]] == ["message", "message", "message"]


# ---------- the matrix ----------


def test_text_usage_and_the_stop():
    events, provider = _one_turn(PLAIN_TEXT)
    ended = _of(events, "model_call_ended")[0].payload
    assert ended["text"] == "Bonjour." and ended["stop_reason"] == "stop"
    assert ended["prompt_tokens"] == 800 and ended["output_tokens"] == 5
    assert ended["usage_source"] == "api"
    assert {d.payload["channel"] for d in _of(events, "model_delta")} == {"text"}
    body = provider.body(0)
    assert body["reasoning"] == {"effort": "none"} and "tools" not in body
    _assert_sent_as_traced(events, provider)


def test_parallel_calls_come_in_order_with_one_output_each():
    stream = sse(
        created(),
        *function_call(0, "call_a", "calculator", '{"expression": "1+1"}'),
        *function_call(1, "call_b", "calculator", '{"expression": "2+2"}'),
        completed(700, 30),
    )
    provider = Provider(stream, PLAIN_TEXT)
    session = _session(provider, bricks=("tools",))
    try:
        events = _turn(session, "Deux calculs")
    finally:
        session.close()
    calls = _of(events, "model_call_ended")[0].payload["tool_calls"]
    assert [c["provider_id"] for c in calls] == ["call_a", "call_b"]
    items = provider.body(1)["input"]
    assert [i["type"] for i in items] == [
        "message",
        "function_call",
        "function_call",
        "function_call_output",
        "function_call_output",
    ]
    assert [i["arguments"] for i in items[1:3]] == [
        '{"expression": "1+1"}',
        '{"expression": "2+2"}',
    ]
    assert [i["call_id"] for i in items[3:]] == [c["id"] for c in calls]
    _assert_sent_as_traced(events, provider)


def test_max_output_tokens_is_a_cut_output():
    events, _ = _one_turn(sse(created(), *message(0, "Début"), incomplete("max_output_tokens")))
    assert _of(events, "output_truncated")[0].payload["channel"] == "text"
    ended = _of(events, "model_call_ended")[0].payload
    assert ended["stop_reason"] == "length" and ended["output_tokens"] == 512


def test_another_incomplete_reason_is_an_explained_error():
    events, provider = _one_turn(sse(created(), *message(0, "Début"), incomplete("content_filter")))
    harness = _of(events, "harness_error")[0].payload
    assert "OpenAI a arrêté la réponse (content_filter)" in harness["message_text"]
    assert harness["cause"] == "incomplete: content_filter"
    # The usage came with the event: the input is billed.
    ended = _of(events, "model_call_ended")[0].payload
    assert ended["stop_reason"] == "error" and ended["usage_source"] == "api"
    assert len(provider.requests) == 1


def test_a_failed_response_after_the_200_counts_the_usage_read():
    failed = {
        "type": "response.failed",
        "response": {
            "id": "resp_1",
            "status": "failed",
            "error": {"code": "server_error", "message": "Oups"},
            "usage": usage(100, 3),
        },
    }
    events, provider = _one_turn(sse(created(), *message(0, "Début"), failed), PLAIN_TEXT)
    harness = _of(events, "harness_error")[0].payload
    assert "OpenAI est indisponible (server_error)" in harness["message_text"]
    assert harness["message_text"].endswith("Message du fournisseur : Oups")
    assert _of(events, "turn_ended")[0].payload["status"] == "error"
    ended = _of(events, "model_call_ended")[0].payload
    assert ended["stop_reason"] == "error" and ended["usage_source"] == "api"
    assert ended["prompt_tokens"] == 100
    assert ended["cost_in_usd"] == pytest.approx(100 * 0.10 / 1e6)
    assert _of(events, "consumption_updated")
    assert len(provider.requests) == 1  # never retried (AD-16)


@pytest.mark.parametrize(
    ("error", "said"),
    [
        # As read on the real API on 2026-10-03, `error` then `response.failed`.
        (
            {
                "type": "insufficient_quota",
                "code": "credit_balance_exhausted",
                "message": "You have no credits remaining.",
                "param": None,
            },
            "le crédit du compte est épuisé",
        ),
        ({"type": "server_error", "code": "server_error", "message": "Oups"}, "indisponible"),
        (
            {"type": "invalid_request_error", "code": "context_length_exceeded", "message": "Oups"},
            "Contexte dépassé",
        ),
        ({"code": "something_new", "message": "Oups"}, "a interrompu la réponse sur une erreur"),
    ],
)
def test_an_error_event_after_the_200_is_explained(error, said):
    failed = {
        "type": "response.failed",
        "response": {"id": "resp_1", "status": "failed", "error": error, "usage": None},
    }
    stream = sse(created(), {"type": "error", "error": error, "sequence_number": 2}, failed)
    events, provider = _one_turn(stream)
    harness = _of(events, "harness_error")[0].payload
    assert said in harness["message_text"]
    assert harness["message_text"].endswith(f"Message du fournisseur : {error['message']}")
    ended = _of(events, "model_call_ended")[0].payload
    assert ended["usage_source"] == "estimate" and "cost_in_usd" not in ended  # not billed
    assert len(provider.requests) == 1


def test_an_error_event_then_a_failure_with_usage_bills_the_input():
    error = {"type": "server_error", "code": "server_error", "message": "Oups"}
    failed = {
        "type": "response.failed",
        "response": {"id": "resp_1", "status": "failed", "error": error, "usage": usage(100, 3)},
    }
    events, _ = _one_turn(
        sse(created(), *message(0, "Début"), {"type": "error", "error": error}, failed)
    )
    assert "indisponible (server_error)" in _of(events, "harness_error")[0].payload["message_text"]
    ended = _of(events, "model_call_ended")[0].payload
    assert ended["usage_source"] == "api" and ended["prompt_tokens"] == 100


def test_a_flat_error_event_is_read_too():
    stream = sse(created(), {"type": "error", "code": "server_error", "message": "Oups"})
    events, _ = _one_turn(stream)
    assert "indisponible (server_error)" in _of(events, "harness_error")[0].payload["message_text"]


@pytest.mark.parametrize(
    ("status", "headers", "error", "fragment"),
    [
        (
            429,
            {"retry-after": "7", "x-ratelimit-remaining-requests": "0"},
            {
                "type": "requests",
                "code": "rate_limit_exceeded",
                "message": "Rate limit reached for gpt-6-luna on requests per min (RPM).",
            },
            "quota dépassé par minute",
        ),
        (
            429,
            {},
            {"type": "insufficient_quota", "code": "insufficient_quota", "message": "No credit."},
            "le crédit du compte est épuisé",
        ),
        (
            400,
            {},
            {
                "type": "invalid_request_error",
                "code": "context_length_exceeded",
                "message": "Your input exceeds the limit of this model.",
            },
            "Contexte dépassé",
        ),
        (
            400,
            {},
            {
                "type": "invalid_request_error",
                "code": None,
                "param": "temperature",
                "message": "Unsupported parameter: 'temperature' is not supported with this model.",
            },
            "Requête refusée par OpenAI (400)",
        ),
    ],
)
def test_http_refusals_follow_the_common_rule(status, headers, error, fragment):
    answer = httpx.Response(status, json={"error": error}, headers=headers)
    events, provider = _one_turn(answer)
    harness = _of(events, "harness_error")[0].payload
    assert fragment in harness["message_text"] and harness["http_status"] == status
    if headers.get("retry-after"):
        assert harness["retry_after_s"] == 7
        assert any("Attendez 7 s" in hint for hint in harness["hints_text"])
    assert len(provider.requests) == 1


def test_a_cached_usage_costs_the_cache_price():
    events, _ = _one_turn(sse(created(), *message(0, "Bonjour."), completed(1000, 10, cached=800)))
    ended = _of(events, "model_call_ended")[0].payload
    assert ended["prompt_tokens"] == 1000
    # Story 2: 200 × 0,10 $ + 800 × 0,01 $ per million, then 10 × 0,50 $.
    assert ended["cost_in_usd"] == pytest.approx(28 / 1_000_000)
    assert ended["cost_out_usd"] == pytest.approx(5 / 1_000_000)


def test_a_stream_cut_before_its_completion_is_an_error():
    events, _ = _one_turn(sse(created(), *message(0, "Début")))
    assert "a interrompu la réponse" in _of(events, "harness_error")[0].payload["message_text"]


def test_two_summary_parts_are_separated_on_the_reasoning_channel():
    stream = sse(
        created(),
        *reasoning(0, "rs_1", ENCRYPTED_2, "Premier point.", "Second point."),
        *message(1, "Fait."),
        completed(100, 20),
    )
    provider = Provider(stream, PLAIN_TEXT)
    session = _session(provider, bricks=("short_memory", "reasoning"))
    try:
        events = _turn(session, "Bonjour")
        _turn(session, "Encore")
    finally:
        session.close()
    ended = _of(events, "model_call_ended")[0].payload
    assert ended["reasoning"] == "Premier point.\n\nSecond point."
    sent = provider.body(1)["input"][1]
    assert [s["text"] for s in sent["summary"]] == ["Premier point.", "Second point."]


def test_a_refusal_is_the_answer_text():
    item = {"id": "msg_0", "type": "message", "role": "assistant", "content": []}
    where = {"item_id": "msg_0", "output_index": 0, "content_index": 0}
    refusal = [{"type": "refusal", "refusal": "Je ne peux pas aider."}]
    stream = sse(
        created(),
        {"type": "response.output_item.added", "output_index": 0, "item": item},
        {"type": "response.refusal.delta", **where, "delta": "Je ne peux "},
        {"type": "response.refusal.delta", **where, "delta": "pas aider."},
        {
            "type": "response.output_item.done",
            "output_index": 0,
            "item": item | {"content": refusal},
        },
        completed(100, 6),
    )
    events, _ = _one_turn(stream)
    ended = _of(events, "model_call_ended")[0].payload
    assert ended["text"] == "Je ne peux pas aider." and ended["stop_reason"] == "stop"
    assert _of(events, "turn_ended")[0].payload["status"] == "completed"


def test_a_call_without_argument_deltas_takes_the_finished_items_or_an_empty_object():
    def call(index: int, call_id: str, arguments: str) -> list[dict[str, Any]]:
        added = {"id": f"fc_{index}", "type": "function_call", "arguments": ""}
        added |= {"call_id": call_id, "name": "calculator"}
        done = added | {"status": "completed", "arguments": arguments}
        return [
            {"type": "response.output_item.added", "output_index": index, "item": added},
            {"type": "response.output_item.done", "output_index": index, "item": done},
        ]

    stream = sse(
        created(),
        *call(0, "call_a", '{"expression": "1+1"}'),
        *call(1, "call_b", ""),
        completed(9, 9),
    )
    provider = Provider(stream, PLAIN_TEXT)
    session = _session(provider, bricks=("tools",))
    try:
        events = _turn(session, "Calcule")
    finally:
        session.close()
    calls = _of(events, "model_call_ended")[0].payload["tool_calls"]
    assert [c["arguments"] for c in calls] == ['{"expression": "1+1"}', "{}"]
    sent = [i for i in provider.body(1)["input"] if i["type"] == "function_call"]
    assert [i["arguments"] for i in sent] == ['{"expression": "1+1"}', "{}"]


def test_interleaved_reasoning_items_go_back_in_the_order_received():
    stream = sse(
        created(),
        *reasoning(0, "rs_a", ENCRYPTED_1, "Premier calcul."),
        *function_call(1, "call_a", "calculator", '{"expression": "1+1"}'),
        *reasoning(2, "rs_b", ENCRYPTED_2, "Second calcul."),
        *function_call(3, "call_b", "calculator", '{"expression": "2+2"}'),
        # A reasoning item never finished (no `encrypted_content`): never sent back.
        {
            "type": "response.output_item.added",
            "output_index": 4,
            "item": {"id": "rs_x", "type": "reasoning", "summary": []},
        },
        completed(700, 60),
    )
    provider = Provider(stream, PLAIN_TEXT)
    session = _session(provider, bricks=("tools", "reasoning"))
    try:
        _turn(session, "Deux calculs")
    finally:
        session.close()
    items = provider.body(1)["input"]
    assert [(i["type"], i.get("id") or i.get("call_id")) for i in items[:5]] == [
        ("message", None),
        ("reasoning", "rs_a"),
        ("function_call", items[2]["call_id"]),
        ("reasoning", "rs_b"),
        ("function_call", items[4]["call_id"]),
    ]
    assert [i["type"] for i in items[5:]] == ["function_call_output"] * 2
    sent = provider.requests[1].content.decode()
    assert "rs_x" not in sent and "_follows" not in sent


def test_the_reasoning_items_never_go_to_another_responses_entry():
    provider = Provider(THINK_TEXT, PLAIN_TEXT)
    session = _session(provider, bricks=("short_memory", "reasoning"))
    try:
        _turn(session, "Bonjour")
        # The same history, for another Responses entry (Sol, say).
        session._cloud = _entry().model_copy(update={"id": "openai_sol", "model": "gpt-6.1-sol"})
        _turn(session, "Encore")
    finally:
        session.close()
    sent = provider.requests[1].content.decode()
    assert ENCRYPTED_2 not in sent and "rs_2" not in sent
    assert provider.body(1)["input"][1] == {
        "type": "message",
        "role": "assistant",
        "content": "Cela fait 5.",
    }


def test_nothing_after_a_terminal_event_is_read():
    stream = sse(created(), *message(0, "Bonjour."), completed(800, 5)) + b"data: illisible\n\n"
    events, _ = _one_turn(stream)
    assert _of(events, "harness_error") == []
    assert _of(events, "model_call_ended")[0].payload["stop_reason"] == "stop"


def test_a_provider_error_is_a_provider_error():
    """The adapter's refusals are the common `ProviderError` (AD-16)."""
    engine = OpenAIResponsesEngine(
        _entry(), SecretStr(SENTINEL), transport=httpx.MockTransport(Provider(sse(created())))
    )
    try:
        with pytest.raises(ProviderError):
            list(engine.complete(ChatBody(b"{}"), CancelToken()))
    finally:
        engine.close()


# ---------- the translator (AD-4, AD-26) ----------


def _body(messages: list[dict[str, Any]], tools: Any = None) -> tuple[str, list]:
    cfg = config.load_config()
    rendered = render_chat_body(
        messages,
        tools,
        call_id="t1.c1",
        fields=chat_fields(_entry(), 512),
        markers=cfg.cloud_markers,
        estimate=lambda t: config.estimate_tokens(t, cfg.chars_per_token),
        provider_label_text="chez le fournisseur",
        api="openai_responses",
    )
    return rendered.body, rendered.segments


def test_the_translator_writes_instructions_and_items():
    model = (SegmentKind.ASSISTANT_TURN, None, "core.model")
    call = {
        "id": "abc",
        "type": "function",
        "function": {
            "name": Part(*model[:1], "calculator", *model[1:], "g"),
            "arguments": Part(*model[:1], '{"expression": "1+1"}', *model[1:], "g"),
        },
    }
    item = {"id": "rs_0", "type": "reasoning", "encrypted_content": "x", "summary": []}
    tool = {
        "type": "function",
        "function": {
            "name": "calculator",
            "description": Part(SegmentKind.TOOL_CATALOG, "Calcule.", "tools", "tools.x"),
            "parameters": {"type": "object", "properties": {}},
        },
    }
    messages = [
        {"role": "system", "content": [Part(SegmentKind.SYSTEM_PROMPT, "Premier.")]},
        {"role": "system", "content": [Part(SegmentKind.SYSTEM_PROMPT, "Second.")]},
        {"role": "user", "content": [Part(SegmentKind.USER_MESSAGE, "Calcule.")]},
        {"role": "assistant", "content": [], "tool_calls": [call, call | {"id": "def"}]},
        {"role": "tool", "tool_call_id": "abc", "content": [Part(SegmentKind.TOOL_RESULT, "2")]},
        {"role": "tool", "tool_call_id": "def", "content": [Part(SegmentKind.TOOL_RESULT, "2")]},
        # A malformed call's error (AD-10): a user message, after the raw output.
        {"role": "assistant", "content": [Part(*model[:1], "calculator {", *model[1:])]},
        {"role": "user", "content": [Part(SegmentKind.TOOL_RESULT, "JSON invalide")]},
        # Reasoning items alone, with nothing to precede: left out with the message.
        {"role": "assistant", "content": [Part(*model[:1], "", *model[1:])]}
        | {"reasoning_items": [item]},
    ]
    body, segments = _body(messages, [tool])
    sent = json.loads(body)
    assert sent["instructions"] == "Premier.\n\nSecond."
    assert list(sent) == [
        "model",
        "instructions",
        "input",
        "tools",
        "stream",
        "max_output_tokens",
        "reasoning",
        "store",
        "include",
    ]
    assert sent["input"] == [
        {"type": "message", "role": "user", "content": "Calcule."},
        {
            "type": "function_call",
            "call_id": "abc",
            "name": "calculator",
            "arguments": '{"expression": "1+1"}',
        },
        {
            "type": "function_call",
            "call_id": "def",
            "name": "calculator",
            "arguments": '{"expression": "1+1"}',
        },
        {"type": "function_call_output", "call_id": "abc", "output": "2"},
        {"type": "function_call_output", "call_id": "def", "output": "2"},
        {"type": "message", "role": "assistant", "content": "calculator {"},
        {"type": "message", "role": "user", "content": "JSON invalide"},
    ]
    assert sent["tools"] == [
        {
            "type": "function",
            "name": "calculator",
            "description": "Calcule.",
            "parameters": {"type": "object", "properties": {}},
            "strict": False,  # strict by default: optional fields would be refused or forced
        }
    ]
    assert "".join(s.text for s in segments) == body
    # Each call's name and arguments stay attributed to the call.
    calls = [s.text for s in segments if s.kind == SegmentKind.ASSISTANT_TURN]
    assert sum(text.count("1+1") for text in calls) == 2


def test_a_reasoning_item_whose_follower_is_gone_goes_before_the_turns_first_item():
    model = (SegmentKind.ASSISTANT_TURN, None, "core.model")
    call = {
        "id": "abc",
        "type": "function",
        "function": {
            "name": Part(*model[:1], "calculator", *model[1:], "g"),
            "arguments": Part(*model[:1], "{}", *model[1:], "g"),
        },
    }
    kept = {"id": "rs_1", "type": "reasoning", "encrypted_content": "x", "summary": []}
    gone = kept | {"id": "rs_0"}
    messages = [
        {"role": "user", "content": [Part(SegmentKind.USER_MESSAGE, "Calcule.")]},
        {
            "role": "assistant",
            "content": [],
            "tool_calls": [call],
            "reasoning_items": [gone | {"_follows": "message"}, kept | {"_follows": "call:0"}],
        },
    ]
    body, segments = _body(messages)
    items = json.loads(body)["input"]
    assert [i.get("id") or i["type"] for i in items] == ["message", "rs_0", "rs_1", "function_call"]
    assert items[1] == gone and items[2] == kept  # `_follows` never sent
    assert "".join(s.text for s in segments) == body


@pytest.mark.parametrize("thought", ["avant <|im_end|> après", "avant \ue123 après"])
def test_a_summary_step_2_would_change_goes_as_template_unchanged(thought):
    cfg = config.load_config()
    part = Part(SegmentKind.HISTORY, thought, "short_memory", "short_memory.history")
    assert render_module.verbatim(part, cfg.cloud_markers) == thought  # a plain string
    item = {
        "id": "rs_1",
        "type": "reasoning",
        "encrypted_content": "x",
        "summary": [{"type": "summary_text", "text": thought}],
    }
    message = AppSession._assistant_message(
        part._replace(text="Réponse."),
        thought,
        chat=True,
        resend="reasoning_items",
        omit_empty=False,
        blocks=[item],
        markers=cfg.cloud_markers,
    )
    body, segments = _body(
        [{"role": "user", "content": [Part(SegmentKind.USER_MESSAGE, "Q")]}, message]
    )
    sent = json.loads(body)["input"]
    assert sent[1] == item and "​" not in body
    assert sent[2] == {"type": "message", "role": "assistant", "content": "Réponse."}
    assert "".join(s.text for s in segments) == body


# ---------- « LLM nu »: sampling only with the reasoning off ----------


def test_the_llm_lab_sends_sampling_only_with_the_reasoning_off():
    provider = Provider(PLAIN_TEXT)
    session = _session(provider)
    try:
        mark = get_journal().last_seq()
        session.llm_generate("Bonjour", DEFAULT_SAMPLING)
        session.join()
        session.llm_generate("Bonjour", DEFAULT_SAMPLING, reasoning=True)
        session.join()
        events = get_journal().events_since(mark)
    finally:
        session.close()
    off, on = provider.body(0), provider.body(1)
    assert off["reasoning"] == {"effort": "none"}
    assert (
        off["temperature"] == DEFAULT_SAMPLING.temperature
        and off["top_p"] == DEFAULT_SAMPLING.top_p
    )
    assert "temperature" not in on and "top_p" not in on
    assert on["reasoning"] == {"effort": "low", "summary": "auto"}
    assert on["store"] is False and off["store"] is False
    traces = [e.payload["sampling"] for e in events if e.kind == "llm_generation_started"]
    assert traces[0]["source"] == "screen" and traces[1]["source"] == "provider"
    assert "OpenAI" in traces[1]["note_text"] and "raisonne" in traces[1]["note_text"]


def test_the_diagnostic_test_runs_through_the_responses_api():
    """« Tester » (CAP-3): the fixed tool call, then its output, in the Responses shapes."""
    from wavestack.session.diagnostic import DiagnosticSession

    cfg = config.load_config()
    entry = _entry()
    config.write_api_key(entry.id, entry.host, SecretStr(SENTINEL))
    stream = sse(created(), *function_call(0, "call_t", "get_datetime", "{}"), completed(300, 9))
    provider = Provider(stream, PLAIN_TEXT)
    diagnostic = DiagnosticSession(
        cfg,
        8420,
        cloud_factory=lambda e, k: create_cloud_engine(
            e, k, connect_timeout_s=1.0, read_timeout_s=5.0, transport=httpx.MockTransport(provider)
        ),
    )
    result = diagnostic.test_cloud_model(entry.id)
    assert result["ok"] is True and len(provider.requests) == 2
    second = provider.body(1)
    assert second["reasoning"] == {"effort": "none"} and second["tools"][0]["type"] == "function"
    assert [i["type"] for i in second["input"]] == [
        "message",
        "function_call",
        "function_call_output",
    ]
    assert second["input"][1]["arguments"] == "{}"
