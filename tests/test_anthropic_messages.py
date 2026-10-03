"""Native providers (3/5): Claude through Anthropic's Messages API (CAP-2, CAP-5).

A fake SSE server (`httpx.MockTransport`) plays Anthropic's stream: nothing leaves the
machine. Each line of the story's matrix, the body sent equal to the one traced, the
reasoning blocks sent back verbatim to their own entry only, and `reasoning_dropped` in
French, English and German.
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
from wavestack.models.anthropic_messages import AnthropicMessagesEngine
from wavestack.models.cloud_api import create_cloud_engine
from wavestack.models.cloud_base import ChatBody, ProviderError, reset_spend, run_call
from wavestack.models.engine import DEFAULT_SAMPLING, CancelToken
from wavestack.session.app_session import AppSession
from wavestack.trace.journal import get_journal

# A signature holding the key's last 4 characters: verbatim in the body sent, masked in the
# events that do not trace the bytes sent (AD-15).
SIGNATURE_1 = f"c2lnbmF0dXJl{SENTINEL[-4:]}LTE="
SIGNATURE_2 = "c2lnbmF0dXJlLTI="


def sse(*events: dict[str, Any]) -> bytes:
    return "".join(f"event: {e['type']}\ndata: {json.dumps(e)}\n\n" for e in events).encode()


def start(input_tokens: int = 100, **usage: int) -> dict[str, Any]:
    message: dict[str, Any] = {
        "id": "msg_1",
        "type": "message",
        "role": "assistant",
        "model": "claude-haiku-4-5",
        "content": [],
        "usage": {"input_tokens": input_tokens, "output_tokens": 1, **usage},
    }
    return {"type": "message_start", "message": message}


def thinking(index: int, text: str, signature: str) -> list[dict[str, Any]]:
    block = {"type": "thinking", "thinking": "", "signature": ""}
    return [
        {"type": "content_block_start", "index": index, "content_block": block},
        {
            "type": "content_block_delta",
            "index": index,
            "delta": {"type": "thinking_delta", "thinking": text},
        },
        {
            "type": "content_block_delta",
            "index": index,
            "delta": {"type": "signature_delta", "signature": signature},
        },
        {"type": "content_block_stop", "index": index},
    ]


def text(index: int, *pieces: str) -> list[dict[str, Any]]:
    return [
        {
            "type": "content_block_start",
            "index": index,
            "content_block": {"type": "text", "text": ""},
        },
        *(
            {
                "type": "content_block_delta",
                "index": index,
                "delta": {"type": "text_delta", "text": p},
            }
            for p in pieces
        ),
        {"type": "content_block_stop", "index": index},
    ]


def tool_use(index: int, call_id: str, name: str, *partial: str) -> list[dict[str, Any]]:
    block = {"type": "tool_use", "id": call_id, "name": name, "input": {}}
    return [
        {"type": "content_block_start", "index": index, "content_block": block},
        *(
            {
                "type": "content_block_delta",
                "index": index,
                "delta": {"type": "input_json_delta", "partial_json": p},
            }
            for p in partial
        ),
        {"type": "content_block_stop", "index": index},
    ]


def end(stop_reason: str, output_tokens: int, **delta: Any) -> list[dict[str, Any]]:
    return [
        {
            "type": "message_delta",
            "delta": {"stop_reason": stop_reason, "stop_sequence": None, **delta},
            "usage": {"output_tokens": output_tokens},
        },
        {"type": "message_stop"},
    ]


THINK_TOOL = sse(
    start(700),
    {"type": "ping"},
    *thinking(0, "Il faut calculer.", SIGNATURE_1),
    *tool_use(1, "toolu_01", "calculator", '{"expression": ', '"2+3"}'),
    *end("tool_use", 40),
)
THINK_TEXT = sse(
    start(760),
    *thinking(0, "Le résultat suffit.", SIGNATURE_2),
    *text(1, "Cela fait ", "5."),
    *end("end_turn", 30),
)
PLAIN_TEXT = sse(start(800), *text(0, "Bonjour."), *end("end_turn", 5))


class Provider:
    """A scripted Anthropic: one response per request, the last one repeated."""

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


def _entry(model_id: str = "claude_haiku") -> config.CloudModel:
    entry = config.load_config().cloud_model(model_id)
    assert entry is not None
    return entry


def _session(
    provider: Provider,
    *,
    bricks=(),
    model_id: str = "claude_haiku",
    entry: config.CloudModel | None = None,
) -> AppSession:
    cfg = config.load_config()
    entry = entry or _entry(model_id)
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


# ---------- the acceptance: a tools turn, then a reasoning turn, through claude_haiku ----------


def test_a_tools_turn_then_a_reasoning_turn_send_the_signed_thinking_back(caplog):
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
    assert request.url == "https://api.anthropic.com/v1/messages"
    assert request.headers["x-api-key"] == SENTINEL and "authorization" not in request.headers
    assert request.headers["anthropic-version"] == "2023-06-01"
    assert request.headers["anthropic-beta"] == "thinking-binding-controls-2026-08-01"
    traced = {h["name"]: h for h in _of(first, "outbound_request")[0].payload["headers"]}
    assert traced["x-api-key"]["masked"] and traced["x-api-key"]["value"] == "[masqué]"

    body = provider.body(0)
    assert body["model"] == "claude-haiku-4-5" and body["stream"] is True
    assert body["max_tokens"] == 1536 and body["system"]
    assert body["thinking"] == {
        "type": "enabled",
        "budget_tokens": 1024,
        "block_binding": {"prefix_mismatch_behavior": "drop_block"},
    }
    assert "temperature" not in body and "stream_options" not in body
    calculator = next(t for t in body["tools"] if t["name"] == "calculator")
    assert set(calculator) == {"name", "input_schema", "description"}
    assert calculator["input_schema"]["type"] == "object"
    assert body["messages"] == [{"role": "user", "content": "Combien font 2 + 3 ?"}]

    # The reasoning on its channel; the call's id is the session's in the next body.
    channels = {d.payload["channel"] for d in _of(first, "model_delta")}
    assert channels == {"reasoning", "tool_call", "text"}
    ended = _of(first, "model_call_ended")
    assert ended[0].payload["reasoning"] == "Il faut calculer."
    assert ended[1].payload["text"] == "Cela fait 5."
    call = ended[0].payload["tool_calls"][0]
    assert call["provider_id"] == "toolu_01" and call["arguments"] == '{"expression": "2+3"}'
    # AD-15: the signature is masked in the events that are not the bytes sent.
    assert SIGNATURE_1 not in ended[0].payload["raw_output"]
    assert "c2lnbmF0dXJl•••LTE=" in ended[0].payload["raw_output"]

    # The second call: the signed thinking block first, verbatim, then the call.
    assistant, results = provider.body(1)["messages"][1:]
    assert assistant == {
        "role": "assistant",
        "content": [
            {"type": "thinking", "thinking": "Il faut calculer.", "signature": SIGNATURE_1},
            {
                "type": "tool_use",
                "id": call["id"],
                "name": "calculator",
                "input": {"expression": "2+3"},
            },
        ],
    }
    assert results["role"] == "user" and results["content"][0]["type"] == "tool_result"
    assert results["content"][0]["tool_use_id"] == call["id"]
    assert (
        isinstance(results["content"][0]["content"], str)
        and "5" in results["content"][0]["content"]
    )

    # The reasoning turn: both turns' blocks go back, each at the head of its message.
    history = provider.body(2)["messages"]
    assert [m["role"] for m in history] == ["user", "assistant", "user", "assistant", "user"]
    final = history[3]["content"]
    assert final[0] == {
        "type": "thinking",
        "thinking": "Le résultat suffit.",
        "signature": SIGNATURE_2,
    }
    assert final[1] == {"type": "text", "text": "Cela fait 5."}
    assert history[1]["content"][0]["signature"] == SIGNATURE_1

    # AD-4: the thinking text is attributed like the reasoning, its signature to `template`.
    segments = _of(second, "context_rendered")[0].payload["segments"]
    owner = next(s for s in segments if s["text"] == "Le résultat suffit.")
    assert owner["kind"] == "history"
    assert all(SIGNATURE_2 not in s["text"] or s["kind"] == "template" for s in segments)
    _no_sentinel(_journal_text(), caplog.text)


def test_the_thinking_blocks_never_go_to_another_entry():
    provider = Provider(THINK_TEXT, PLAIN_TEXT)
    session = _session(provider, bricks=("short_memory", "reasoning"))
    try:
        _turn(session, "Bonjour")
        session._cloud = _entry("claude_sonnet")  # the same history, for another entry
        _turn(session, "Encore")
    finally:
        session.close()
    second = provider.body(1)
    assert second["messages"][1] == {
        "role": "assistant",
        "content": [{"type": "text", "text": "Cela fait 5."}],
    }
    assert SIGNATURE_2 not in provider.requests[1].content.decode()


def test_with_the_reasoning_brick_off_no_thinking_block_is_sent_back():
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
    # Measured on 2026-10-03: `block_binding` is refused with `{type: "disabled"}` (400).
    assert second["thinking"] == {"type": "disabled"}
    assert second["max_tokens"] == 512
    assert SIGNATURE_2 not in provider.requests[1].content.decode()


# ---------- the matrix ----------


def test_text_usage_and_the_stop():
    provider = Provider(PLAIN_TEXT)
    session = _session(provider)
    try:
        events = _turn(session, "Bonjour")
    finally:
        session.close()
    ended = _of(events, "model_call_ended")[0].payload
    assert ended["text"] == "Bonjour." and ended["stop_reason"] == "stop"
    assert ended["prompt_tokens"] == 800 and ended["output_tokens"] == 5
    assert ended["usage_source"] == "api"
    assert {d.payload["channel"] for d in _of(events, "model_delta")} == {"text"}
    body = json.loads(provider.requests[0].content)
    assert body["thinking"]["type"] == "disabled" and "tools" not in body


def test_parallel_calls_come_in_order_and_their_results_in_one_user_message():
    stream = sse(
        start(700),
        *tool_use(0, "toolu_a", "calculator", '{"expression": "1+1"}'),
        *tool_use(1, "toolu_b", "calculator", '{"expression": "2+2"}'),
        *end("tool_use", 30),
    )
    provider = Provider(stream, PLAIN_TEXT)
    session = _session(provider, bricks=("tools",))
    try:
        events = _turn(session, "Deux calculs")
    finally:
        session.close()
    calls = _of(events, "model_call_ended")[0].payload["tool_calls"]
    assert [c["provider_id"] for c in calls] == ["toolu_a", "toolu_b"]
    messages = provider.body(1)["messages"]
    assert [m["role"] for m in messages] == ["user", "assistant", "user"]
    assert [b["input"] for b in messages[1]["content"]] == [
        {"expression": "1+1"},
        {"expression": "2+2"},
    ]
    results = messages[2]["content"]
    assert [r["tool_use_id"] for r in results] == [c["id"] for c in calls]
    assert all(r["type"] == "tool_result" for r in results)
    _assert_sent_as_traced(events, provider)


def test_a_cached_usage_counts_every_input_token_and_costs_its_prices():
    stream = sse(
        start(100, cache_read_input_tokens=800, cache_creation_input_tokens=100),
        *text(0, "Bonjour."),
        *end("end_turn", 10),
    )
    provider = Provider(stream)
    session = _session(provider)
    try:
        events = _turn(session, "Bonjour")
    finally:
        session.close()
    ended = _of(events, "model_call_ended")[0].payload
    assert ended["prompt_tokens"] == 1000
    # Story 2: 100 × 1 $ + 800 × 0,10 $ + 100 × 1,25 $ per million, then 10 × 5 $.
    assert ended["cost_in_usd"] == pytest.approx(305 / 1_000_000)
    assert ended["cost_out_usd"] == pytest.approx(50 / 1_000_000)


def test_a_refusal_is_explained_with_its_category():
    stream = sse(
        start(100),
        *end(
            "refusal", 0, stop_details={"type": "refusal", "category": "cyber", "explanation": None}
        ),
    )
    provider = Provider(stream, PLAIN_TEXT)
    session = _session(provider)
    try:
        events = _turn(session, "Bonjour")
        after = _turn(session, "Encore")
    finally:
        session.close()
    harness = _of(events, "harness_error")[0].payload
    assert (
        "a refusé de répondre" in harness["message_text"] and "« cyber »" in harness["message_text"]
    )
    assert harness["cause"] == "stop_reason: refusal (cyber)"
    assert _of(events, "turn_ended")[0].payload["status"] == "error"
    # The input read before the refusal is billed: FinOps and the session's cap count it.
    ended = _of(events, "model_call_ended")[0].payload
    assert ended["stop_reason"] == "error" and ended["usage_source"] == "api"
    assert ended["prompt_tokens"] == 100 and ended["cost_in_usd"] == pytest.approx(100 / 1e6)
    assert ended["cost_in_usd"] > 0 and _of(events, "consumption_updated")
    assert _of(after, "turn_ended")[0].payload["status"] == "completed"


@pytest.mark.parametrize("reason", ["pause_turn", "something_new"])
def test_a_stop_the_harness_cannot_go_on_from_is_an_error(reason):
    provider = Provider(sse(start(100), *text(0, "Début"), *end(reason, 3)))
    session = _session(provider)
    try:
        events = _turn(session, "Bonjour")
    finally:
        session.close()
    harness = _of(events, "harness_error")[0].payload
    assert f"a arrêté la réponse ({reason})" in harness["message_text"]
    assert len(provider.requests) == 1  # never retried (AD-16)


def test_the_context_window_exceeded_says_so_as_the_prompt_too_long_400():
    stream = sse(start(100), *text(0, "Début"), *end("model_context_window_exceeded", 3))
    provider = Provider(stream)
    session = _session(provider)
    try:
        events = _turn(session, "Bonjour")
    finally:
        session.close()
    harness = _of(events, "harness_error")[0].payload
    assert "Contexte dépassé" in harness["message_text"]
    assert harness["cause"] == "stop_reason: model_context_window_exceeded"


def test_a_null_in_the_last_usage_keeps_the_first_value():
    stream = sse(
        start(100, cache_read_input_tokens=50),
        *text(0, "Bonjour."),
        {
            "type": "message_delta",
            "delta": {"stop_reason": "end_turn"},
            "usage": {"output_tokens": 7, "input_tokens": None, "cache_read_input_tokens": None},
        },
    )
    provider = Provider(stream)
    session = _session(provider)
    try:
        events = _turn(session, "Bonjour")
    finally:
        session.close()
    ended = _of(events, "model_call_ended")[0].payload
    assert ended["prompt_tokens"] == 150 and ended["output_tokens"] == 7


def test_max_tokens_is_a_cut_output():
    provider = Provider(sse(start(100), *text(0, "Début"), *end("max_tokens", 512)))
    session = _session(provider)
    try:
        events = _turn(session, "Bonjour")
    finally:
        session.close()
    assert _of(events, "output_truncated")[0].payload["channel"] == "text"
    assert _of(events, "model_call_ended")[0].payload["stop_reason"] == "length"


@pytest.mark.parametrize(
    ("kind", "said"),
    [
        ("overloaded_error", "Anthropic est indisponible (overloaded_error)"),
        ("api_error", "Anthropic est indisponible (api_error)"),
        ("invalid_request_error", "Anthropic a interrompu la réponse sur une erreur"),
    ],
)
def test_an_error_event_after_the_200_is_explained(kind, said):
    stream = sse(
        start(100),
        *text(0, "Début"),
        {"type": "error", "error": {"type": kind, "message": "Oups"}},
    )
    provider = Provider(stream)
    session = _session(provider)
    try:
        events = _turn(session, "Bonjour")
    finally:
        session.close()
    harness = _of(events, "harness_error")[0].payload
    assert said in harness["message_text"]
    assert harness["message_text"].endswith("Message du fournisseur : Oups")
    assert len(provider.requests) == 1


@pytest.mark.parametrize(
    ("status", "headers", "error", "fragment"),
    [
        (529, {}, {"type": "overloaded_error", "message": "Overloaded"}, "indisponible (529)"),
        (
            429,
            {"retry-after": "7", "anthropic-ratelimit-requests-remaining": "0"},
            {
                "type": "rate_limit_error",
                "message": "This request would exceed the rate limit for your organization "
                "of 50 requests per minute.",
            },
            "quota dépassé par minute",
        ),
        (
            400,
            {},
            {
                "type": "invalid_request_error",
                "message": "prompt is too long: 210000 tokens > 200000 maximum",
            },
            "Contexte dépassé",
        ),
    ],
)
def test_http_refusals_follow_the_common_rule(status, headers, error, fragment):
    answer = httpx.Response(status, json={"type": "error", "error": error}, headers=headers)
    provider = Provider(answer)
    session = _session(provider)
    try:
        events = _turn(session, "Bonjour")
    finally:
        session.close()
    harness = _of(events, "harness_error")[0].payload
    assert fragment in harness["message_text"] and harness["http_status"] == status
    if status == 429:
        assert harness["retry_after_s"] == 7
        assert any("Attendez 7 s" in hint for hint in harness["hints_text"])
        # The quota headers are the proof of the refusal, traced in clear.
        response = _of(events, "outbound_response")[0].payload
        clear = {h["name"].lower(): h for h in response["headers"]}
        assert clear["anthropic-ratelimit-requests-remaining"]["masked"] is False
    assert len(provider.requests) == 1


def test_a_stream_cut_before_its_stop_reason_is_an_error():
    provider = Provider(sse(start(100), *text(0, "Début")))
    session = _session(provider)
    try:
        events = _turn(session, "Bonjour")
    finally:
        session.close()
    assert "a interrompu la réponse" in _of(events, "harness_error")[0].payload["message_text"]


# ---------- CAP-5: the reasoning the provider threw away ----------

DROPPED = [
    {
        "type": "thinking_dropped",
        "path": "messages.1.content.0",
        "reason": "prefix_binding_mismatch",
    },
    {
        "type": "thinking_dropped",
        "path": "messages.3.content.0",
        "reason": "model_binding_mismatch",
    },
    {"type": "thinking_dropped", "path": "messages.5.content.0", "reason": "a_reason_to_come"},
    {"type": "something_else", "path": "messages.5", "reason": "prefix_binding_mismatch"},
]


def _dropping_stream() -> bytes:
    begin = start(100)
    begin["message"]["input_transformations"] = DROPPED
    return sse(begin, *text(0, "Bonjour."), *end("end_turn", 5))


def test_input_transformations_become_reasoning_dropped_events():
    provider = Provider(_dropping_stream())
    session = _session(provider)
    try:
        events = _turn(session, "Bonjour")
    finally:
        session.close()
    dropped = [e.payload for e in _of(events, "reasoning_dropped")]
    assert [(d["path"], d["reason"]) for d in dropped] == [
        ("messages.1.content.0", "prefix_binding_mismatch"),
        ("messages.3.content.0", "model_binding_mismatch"),
    ]
    assert (
        "Anthropic a jeté le raisonnement d'un tour précédent (messages.1.content.0)"
        in (dropped[0]["message_text"])
    )
    assert "réécrit l'historique" in dropped[0]["message_text"]
    assert "un autre modèle" in dropped[1]["message_text"]
    assert _of(events, "turn_ended")[0].payload["status"] == "completed"


@pytest.mark.parametrize(
    ("lang", "said"),
    [
        ("fr", "le harnais a réécrit l'historique"),
        ("en", "the harness rewrote the history"),
        ("de", "Der Harness hat den Verlauf seitdem umgeschrieben"),
    ],
)
def test_reasoning_dropped_speaks_the_sessions_language(lang, said):
    engine = AnthropicMessagesEngine(
        _entry(), SecretStr(SENTINEL), transport=httpx.MockTransport(Provider(_dropping_stream()))
    )
    mark = get_journal().last_seq()
    try:
        run_call(
            engine,
            ChatBody(b"{}"),
            CancelToken(),
            phase_label="test",
            estimated_prompt=10,
            chars_per_token=4.0,
            call_id=lambda index: f"c{index}",
            lang=lang,
        )
    finally:
        engine.close()
    dropped = [e.payload for e in get_journal().events_since(mark) if e.kind == "reasoning_dropped"]
    assert len(dropped) == 2 and said in dropped[0]["message_text"]


def _call(answer: bytes | httpx.Response, cancel: CancelToken | None = None) -> tuple[Any, list]:
    """One `run_call` through the adapter, outside any session: what it returned (or the
    `ProviderError` it raised), and the events it emitted."""
    engine = AnthropicMessagesEngine(
        _entry(), SecretStr(SENTINEL), transport=httpx.MockTransport(Provider(answer))
    )
    mark = get_journal().last_seq()
    try:
        result: Any = run_call(
            engine,
            ChatBody(b"{}"),
            cancel or CancelToken(),
            phase_label="test",
            estimated_prompt=10,
            chars_per_token=4.0,
            call_id=lambda index: f"c{index}",
        )
    except ProviderError as error:
        result = error
    finally:
        engine.close()
    return result, get_journal().events_since(mark)


def _stopped_between(first: bytes, rest: bytes) -> tuple[Any, list]:
    """A call whose « Arrêter » comes once `first` is read, before `rest`."""
    cancel = CancelToken()

    def chunks():  # noqa: ANN202
        yield first
        cancel.cancel()
        yield rest

    stream = httpx.Response(200, content=chunks(), headers={"content-type": "text/event-stream"})
    return _call(stream, cancel)


def test_a_stop_during_the_stream_ends_the_call_cancelled():
    call, events = _stopped_between(sse(start(100), *text(0, "Bonj")), sse(*end("end_turn", 5)))
    assert not isinstance(call, ProviderError) and call.stop_reason == "cancelled"
    assert call.text == "Bonj" and _of(events, "harness_error") == []
    assert _of(events, "model_call_ended")[0].payload["stop_reason"] == "cancelled"


def test_a_stop_after_the_stop_reason_keeps_the_answer_finished():
    finish, stop = end("tool_use", 20)
    call, events = _stopped_between(
        sse(start(100), *tool_use(0, "toolu_01", "calculator", '{"expression": "2+3"}'), finish),
        sse(stop),
    )
    assert not isinstance(call, ProviderError) and call.stop_reason == "stop"
    assert [c["name"] for c in call.calls] == ["calculator"] and call.calls[0]["id"] == "c0"
    assert _of(events, "model_call_ended")[0].payload["stop_reason"] == "stop"


def test_reasoning_dropped_is_said_even_when_the_call_fails():
    begin = start(100)
    begin["message"]["input_transformations"] = DROPPED
    error, events = _call(sse(begin, *text(0, "Je "), *end("refusal", 3)))
    assert isinstance(error, ProviderError)
    dropped = [e.payload for e in _of(events, "reasoning_dropped")]
    assert [d["reason"] for d in dropped] == ["prefix_binding_mismatch", "model_binding_mismatch"]
    assert _of(events, "model_call_ended")[0].payload["stop_reason"] == "error"


def test_the_dropped_path_goes_through_the_key_mask():
    begin = start(100)
    begin["message"]["input_transformations"] = [
        {
            "type": "thinking_dropped",
            "path": f"messages.{SENTINEL[-4:]}",
            "reason": "prefix_binding_mismatch",
        }
    ]
    _, events = _call(sse(begin, *text(0, "Bonjour."), *end("end_turn", 5)))
    dropped = _of(events, "reasoning_dropped")[0].payload
    assert dropped["path"] == "messages.•••" and SENTINEL[-4:] not in dropped["message_text"]


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
        api="anthropic_messages",
    )
    return rendered.body, rendered.segments


def test_the_translator_joins_the_systems_and_gathers_the_tool_results():
    model = (SegmentKind.ASSISTANT_TURN, None, "core.model")
    call = {
        "id": "abc",
        "type": "function",
        "function": {
            "name": Part(*model[:1], "calculator", *model[1:], "g"),
            "arguments": Part(*model[:1], '{"expression": "1+1", "n": 2}', *model[1:], "g"),
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
        {"role": "assistant", "content": [Part(*model[:1], "", *model[1:])]},  # nothing: left out
    ]
    body, segments = _body(messages)
    sent = json.loads(body)
    assert sent["system"] == "Premier.\n\nSecond."
    assert [m["role"] for m in sent["messages"]] == [
        "user",
        "assistant",
        "user",
        "assistant",
        "user",
    ]
    assert sent["messages"][1]["content"][0] == {
        "type": "tool_use",
        "id": "abc",
        "name": "calculator",
        "input": {"expression": "1+1", "n": 2},
    }
    assert [r["tool_use_id"] for r in sent["messages"][2]["content"]] == ["abc", "def"]
    assert sent["messages"][3] == {
        "role": "assistant",
        "content": [{"type": "text", "text": "calculator {"}],
    }
    assert "".join(s.text for s in segments) == body
    # The call's name and its string values stay attributed to the call (one segment each).
    calls = [s for s in segments if s.kind == SegmentKind.ASSISTANT_TURN and "calculator" in s.text]
    assert len(calls) >= 2 and '"1+1"' in calls[0].text


def test_a_past_answer_of_thinking_alone_is_left_out():
    # The history's form (`omit_empty=False`): a signed thinking, an empty text, no call.
    model = Part(SegmentKind.HISTORY, "", "short_memory", "short_memory.history")
    blocks = [{"type": "thinking", "thinking": "Je réfléchis.", "signature": "sig"}]
    message = AppSession._assistant_message(
        model,
        "Je réfléchis.",
        chat=True,
        resend="thinking_blocks",
        omit_empty=False,
        blocks=blocks,
    )
    assert message["thinking_blocks"]
    user = {"role": "user", "content": [Part(SegmentKind.USER_MESSAGE, "Q")]}
    body, _ = _body([user, message, user])
    assert [m["role"] for m in json.loads(body)["messages"]] == ["user", "user"]


def test_a_thinking_text_with_outer_blanks_keeps_its_bytes():
    model = Part(SegmentKind.HISTORY, "Réponse.", "short_memory", "short_memory.history")
    blocks = [
        {"type": "thinking", "thinking": "\nJe réfléchis.\n", "signature": "sig"},
        {"type": "redacted_thinking", "data": "opaque"},
    ]
    message = AppSession._assistant_message(
        model,
        "\nJe réfléchis.\n",
        chat=True,
        resend="thinking_blocks",
        omit_empty=False,
        blocks=blocks,
    )
    body, segments = _body(
        [{"role": "user", "content": [Part(SegmentKind.USER_MESSAGE, "Q")]}, message]
    )
    sent = json.loads(body)["messages"][1]["content"]
    assert sent[0] == blocks[0] and sent[1] == blocks[1]
    assert sent[2] == {"type": "text", "text": "Réponse."}
    assert any(s.text == "Je réfléchis." and s.kind == SegmentKind.HISTORY for s in segments)
    assert "".join(s.text for s in segments) == body


# ---------- « LLM nu »: no sampling to Anthropic while it thinks ----------


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
    # Haiku 4.5 refuses `temperature` and `top_p` together (400): it declares the first only.
    assert off["temperature"] == DEFAULT_SAMPLING.temperature and "top_p" not in off
    assert "temperature" not in on and "top_p" not in on and on["thinking"]["type"] == "enabled"
    traces = [e.payload["sampling"] for e in events if e.kind == "llm_generation_started"]
    assert traces[0]["source"] == "screen" and traces[1]["source"] == "provider"
    assert "raisonne" in traces[1]["note_text"]


def test_a_provider_error_is_a_provider_error():
    """The adapter's refusals are the common `ProviderError` (AD-16)."""
    engine = AnthropicMessagesEngine(
        _entry(), SecretStr(SENTINEL), transport=httpx.MockTransport(Provider(sse(start(1))))
    )
    try:
        with pytest.raises(ProviderError):
            list(engine.complete(ChatBody(b"{}"), CancelToken()))
    finally:
        engine.close()


def test_the_diagnostic_test_runs_through_the_messages_api():
    """« Tester » (CAP-2): the fixed tool call, then its reply, in Anthropic's own shapes."""
    from wavestack.session.diagnostic import DiagnosticSession

    cfg = config.load_config()
    entry = _entry()
    config.write_api_key(entry.id, entry.host, SecretStr(SENTINEL))
    stream = sse(start(300), *tool_use(0, "toolu_t", "get_datetime", "{}"), *end("tool_use", 9))
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
    assert second["thinking"] == {"type": "disabled"} and second["tools"][0]["input_schema"]
    assert [m["role"] for m in second["messages"]] == ["user", "assistant", "user"]
    assert second["messages"][1]["content"][0]["type"] == "tool_use"
    assert second["messages"][1]["content"][0]["input"] == {}
    assert second["messages"][2]["content"][0]["type"] == "tool_result"


# ---------- review of 2026-10-03 ----------


def test_a_redacted_block_between_thinking_and_a_call_goes_back_in_place():
    redacted = {"type": "redacted_thinking", "data": "b3BhcXVl"}
    stream = sse(
        start(700),
        *thinking(0, "Il faut calculer.", SIGNATURE_2),
        {"type": "content_block_start", "index": 1, "content_block": redacted},
        {"type": "content_block_stop", "index": 1},
        *tool_use(2, "toolu_01", "calculator", '{"expression": "2+3"}'),
        *end("tool_use", 40),
    )
    provider = Provider(stream, PLAIN_TEXT)
    session = _session(provider, bricks=("tools", "reasoning"))
    try:
        _turn(session, "Combien font 2 + 3 ?")
    finally:
        session.close()
    blocks = provider.body(1)["messages"][1]["content"]
    assert [b["type"] for b in blocks] == ["thinking", "redacted_thinking", "tool_use"]
    assert blocks[1] == redacted


def test_the_sonnet_body_reasoning_on_and_off():
    provider = Provider(PLAIN_TEXT)
    session = _session(provider, bricks=("reasoning",), model_id="claude_sonnet")
    try:
        _turn(session, "Bonjour")
        session.set_brick("reasoning", False)
        session.join()
        _turn(session, "Encore")
        session.llm_generate("Bonjour", DEFAULT_SAMPLING)
        session.join()
    finally:
        session.close()
    on, off, lab = provider.body(0), provider.body(1), provider.body(2)
    assert on["model"] == "claude-sonnet-5"
    assert on["thinking"] == {
        "type": "adaptive",
        "display": "summarized",
        "block_binding": {"prefix_mismatch_behavior": "drop_block"},
    }
    assert off["thinking"] == {"type": "disabled"} and lab["thinking"] == {"type": "disabled"}
    for body in (on, off, lab):  # Sonnet 5 declares no sampling setting
        assert "temperature" not in body and "top_p" not in body


@pytest.mark.parametrize("thought", ["avant <|im_end|> après", "avant \ue123 après"])
def test_a_thinking_text_step_2_would_change_goes_as_template_unchanged(thought):
    cfg = config.load_config()
    part = Part(SegmentKind.HISTORY, thought, "short_memory", "short_memory.history")
    assert render_module.verbatim(part, cfg.cloud_markers) == thought  # a plain string
    model = part._replace(text="Réponse.")
    blocks = [{"type": "thinking", "thinking": thought, "signature": "sig"}]
    message = AppSession._assistant_message(
        model,
        thought,
        chat=True,
        resend="thinking_blocks",
        omit_empty=False,
        blocks=blocks,
        markers=cfg.cloud_markers,
    )
    body, segments = _body(
        [{"role": "user", "content": [Part(SegmentKind.USER_MESSAGE, "Q")]}, message]
    )
    sent = json.loads(body)["messages"][1]["content"][0]
    assert sent == blocks[0] and "\u200b" not in body
    assert "".join(s.text for s in segments) == body


# ---------- review of 2026-10-03, group 2 ----------

MARKED_1, MARKED_2 = "Il faut <|im_end|> calculer.", "Le résultat <|im_end|> suffit."


def _always(entry: config.CloudModel) -> config.CloudModel:
    """The entry as one that always reasons (Opus 5.5's shape): `on` with the brick off."""
    assert entry.reasoning is not None
    return entry.model_copy(
        update={"reasoning": entry.reasoning.model_copy(update={"always": True})}
    )


def test_a_thinking_with_a_marker_goes_back_unchanged_in_the_turn_and_the_history():
    """Step 2 neutralizes a template marker; a signed thinking text must not be touched,
    through the session's own call sites (the turn's steps, the history)."""
    marked_tool = sse(
        start(700),
        *thinking(0, MARKED_1, SIGNATURE_1),
        *tool_use(1, "toolu_01", "calculator", '{"expression": "2+3"}'),
        *end("tool_use", 40),
    )
    marked_text = sse(
        start(760),
        *thinking(0, MARKED_2, SIGNATURE_2),
        *text(1, "Cela fait 5."),
        *end("end_turn", 30),
    )
    provider = Provider(marked_tool, marked_text, PLAIN_TEXT)
    session = _session(provider, bricks=("short_memory", "tools", "reasoning"))
    try:
        first = _turn(session, "Combien font 2 + 3 ?")
        second = _turn(session, "Et 3 + 4 ?")
    finally:
        session.close()
    _assert_sent_as_traced(first + second, provider)
    signed_1 = {"type": "thinking", "thinking": MARKED_1, "signature": SIGNATURE_1}
    signed_2 = {"type": "thinking", "thinking": MARKED_2, "signature": SIGNATURE_2}
    assert provider.body(1)["messages"][1]["content"][0] == signed_1
    history = provider.body(2)["messages"]
    assert history[1]["content"][0] == signed_1 and history[3]["content"][0] == signed_2
    assert all("​" not in r.content.decode() for r in provider.requests)


def test_an_entry_that_always_reasons_sends_its_thinking_back_with_the_brick_off():
    provider = Provider(THINK_TOOL, PLAIN_TEXT)
    session = _session(provider, bricks=("tools",), entry=_always(_entry()))
    try:
        events = _turn(session, "Combien font 2 + 3 ?")
    finally:
        session.close()
    assert _of(events, "turn_ended")[0].payload["status"] == "completed"
    assert provider.body(0)["thinking"]["type"] == "enabled"  # `on`, the brick off
    blocks = provider.body(1)["messages"][1]["content"]
    assert blocks[0] == {
        "type": "thinking",
        "thinking": "Il faut calculer.",
        "signature": SIGNATURE_1,
    }
    assert blocks[1]["type"] == "tool_use"


def test_the_diagnostic_test_sends_the_thinking_back_for_an_entry_that_always_reasons(
    monkeypatch,
):
    from wavestack.session.diagnostic import DiagnosticSession

    cfg = config.load_config()
    entry = _always(_entry())
    monkeypatch.setattr(config.Config, "cloud_model", lambda self, model_id: entry)  # frozen
    config.write_api_key(entry.id, entry.host, SecretStr(SENTINEL))
    stream = sse(
        start(300),
        *thinking(0, "Je lis l'heure.", SIGNATURE_2),
        *tool_use(1, "toolu_t", "get_datetime", "{}"),
        *end("tool_use", 9),
    )
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
    assert second["thinking"]["type"] == "enabled"
    blocks = second["messages"][1]["content"]
    assert blocks[0] == {
        "type": "thinking",
        "thinking": "Je lis l'heure.",
        "signature": SIGNATURE_2,
    }
    assert blocks[1]["type"] == "tool_use"


def test_a_call_with_two_string_arguments_counts_its_arguments_once():
    cfg = config.load_config()
    model = (SegmentKind.ASSISTANT_TURN, None, "core.model")
    arguments = '{"expression": "' + "1+" * 40 + '1", "unit": "' + "kilomètres " * 10 + '"}'
    call = {
        "id": "abc",
        "type": "function",
        "function": {
            "name": Part(*model[:1], "calculator", *model[1:], "g"),
            "arguments": Part(*model[:1], arguments, *model[1:], "g"),
        },
    }
    messages = [
        {"role": "user", "content": [Part(SegmentKind.USER_MESSAGE, "Calcule.")]},
        {"role": "assistant", "content": [], "tool_calls": [call]},
    ]
    body, segments = _body(messages)
    [segment] = [s for s in segments if s.kind == SegmentKind.ASSISTANT_TURN]
    # Both string values sit in the one call segment, with the template between them.
    assert '"1+1+' in segment.text and "kilomètres" in segment.text
    expected = config.estimate_tokens("calculator" + arguments, cfg.chars_per_token)
    assert segment.tokens == expected  # `arguments` counted once, not once per value
    assert "".join(s.text for s in segments) == body
