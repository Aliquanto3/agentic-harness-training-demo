"""Native providers (1/5): the `api` field, the common cloud base and the body translators
(AD-4, AD-5, AD-26).

The `openai_chat` bodies are pinned by fingerprints taken BEFORE the refactoring
(`fixtures/openai_chat_bodies.json`): the same reference history, rendered for the `groq`,
`mistral`, `gemini` and `gemma` entries of `wavestack.toml`, reasoning on and off, must give
the same bytes. Every provider answer comes from an `httpx.MockTransport`.
"""

from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Any, get_args

import httpx
import pytest
from pydantic import SecretStr, ValidationError
from test_cloud import GROQ_TEXT, GROQ_TOOL, SENTINEL, Provider, _no_sentinel, _of, _turn

from wavestack import config
from wavestack.cloud import chat_fields
from wavestack.context import render as render_module
from wavestack.context.render import render_chat_body
from wavestack.context.segments import Joined, Part, SegmentKind
from wavestack.models import cloud_api
from wavestack.models.cloud_api import create_cloud_engine
from wavestack.models.engine import DEFAULT_SAMPLING
from wavestack.models.openai_chat import OpenAIChatEngine
from wavestack.session.app_session import AppSession
from wavestack.session.diagnostic import DiagnosticSession
from wavestack.trace.journal import get_journal

FIXTURE = Path(__file__).parent / "fixtures" / "openai_chat_bodies.json"
ENTRIES = ("groq", "mistral", "gemini", "gemma")

_MODEL = (SegmentKind.ASSISTANT_TURN, None, "core.model")
_TOOL = (SegmentKind.TOOL_CATALOG, "tools", "tools.get_datetime", "tool.get_datetime")


def _assistant(entry: config.CloudModel, text: str, reasoning: str) -> dict[str, Any]:
    """An assistant message with its reasoning sent back in the form of the entry's
    `format` (as the session writes it, `_assistant_message`), whether or not the entry
    resends it: every shape the chat body knows is covered."""
    content = Part(SegmentKind.ASSISTANT_TURN, text, *_MODEL[1:])
    thought = content._replace(text=reasoning)
    form = entry.reasoning.format if entry.reasoning is not None else None
    answer: dict[str, Any] = {"role": "assistant"}
    if form == "content_blocks":
        answer["content"] = [
            {"type": "thinking", "thinking": [{"type": "text", "text": thought}]},
            *([{"type": "text", "text": content}] if text else []),
        ]
    elif form == "think_tags":
        tags = entry.reasoning.tags
        tagged = thought._replace(text=f"{tags[0]}{reasoning}{tags[1]}")
        answer["content"] = [Joined((tagged, *([content] if text else [])), sep="")]
    elif text:
        answer["content"] = [content]
    if form == "field":
        answer["reasoning"] = thought
    return answer


def reference_history(
    entry: config.CloudModel,
) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    """System, user, an assistant tool call (reasoning sent back), the tool's reply, a final
    answer (reasoning sent back), a new user message; and one declared tool."""
    call = _assistant(entry, "", "Il faut l'heure exacte : j'appelle l'outil.")
    sent: dict[str, Any] = {
        "id": "t1.s1.call0",
        "type": "function",
        "function": {
            "name": Part(*_MODEL[:1], "get_datetime", *_MODEL[1:], "t1.s1.0"),
            "arguments": Part(*_MODEL[:1], '{"zone": "Europe/Paris"}', *_MODEL[1:], "t1.s1.0"),
        },
    }
    sent |= {k: v for k, v in entry.tool_call_extra.items() if k not in sent}
    call["tool_calls"] = [sent]
    final = _assistant(entry, "Il est 9 h 30 à Paris.", "La réponse de l'outil suffit.")
    messages = [
        {
            "role": "system",
            "content": [
                Part(SegmentKind.SYSTEM_PROMPT, "Tu es un assistant « WaveStack ».", None, "core")
            ],
        },
        {"role": "user", "content": [Part(SegmentKind.USER_MESSAGE, "Quelle heure est-il ?")]},
        call,
        {
            "role": "tool",
            "tool_call_id": "t1.s1.call0",
            "content": [
                Part(
                    SegmentKind.TOOL_RESULT,
                    '{"datetime": "2026-10-03T09:30:00+02:00"}',
                    "tools",
                    "tools.get_datetime",
                )
            ],
        },
        final,
        {"role": "user", "content": [Part(SegmentKind.USER_MESSAGE, "Et à Tokyo, déjà ?")]},
    ]
    tools = [
        {
            "type": "function",
            "function": {
                "name": Part(_TOOL[0], "get_datetime", *_TOOL[1:]),
                "description": Part(_TOOL[0], "Donne la date et l'heure d'un fuseau.", *_TOOL[1:]),
                "parameters": {
                    "type": "object",
                    "properties": {
                        "zone": {
                            "type": "string",
                            "description": Part(_TOOL[0], "Fuseau IANA.", *_TOOL[1:]),
                        }
                    },
                },
            },
        }
    ]
    return messages, tools


def reference_body(entry: config.CloudModel, reasoning: bool, **kw: Any) -> str:
    cfg = config.load_config()
    messages, tools = reference_history(entry)
    return render_chat_body(
        messages,
        tools,
        call_id="t1.c1",
        fields=chat_fields(entry, entry.reserve_for(reasoning), reasoning=reasoning),
        markers=cfg.cloud_markers,
        estimate=lambda text: config.estimate_tokens(text, cfg.chars_per_token),
        provider_label_text="chez le fournisseur",
        **kw,
    ).body


def fingerprints() -> dict[str, dict[str, dict[str, Any]]]:
    cfg = config.load_config()
    found: dict[str, dict[str, dict[str, Any]]] = {}
    for model_id in ENTRIES:
        entry = cfg.cloud_model(model_id)
        assert entry is not None, model_id
        found[model_id] = {}
        for state, on in (("on", True), ("off", False)):
            data = reference_body(entry, on).encode("utf-8")
            found[model_id][state] = {
                "sha256": hashlib.sha256(data).hexdigest(),
                "length": len(data),
            }
    return found


def test_openai_chat_bodies_are_byte_for_byte_those_before_the_refactoring():
    expected = json.loads(FIXTURE.read_text("utf-8"))
    assert fingerprints() == expected


# ---------- the `api` field and `extra_headers` (CAP-1, AD-5) ----------


def test_every_entry_of_wavestack_toml_speaks_openai_chat_without_extra_headers():
    """Except Anthropic's (native providers 3/5), with its two fixed headers."""
    raw = config.load_config().get("cloud", "models", default=[])
    entries = [config.CloudModel.model_validate(item) for item in raw]
    assert {e.id for e in entries} >= set(ENTRIES)
    native = [e for e in entries if e.provider == "Anthropic"]
    assert {e.id for e in native} == {"claude_haiku", "claude_sonnet"}
    assert all(e.api == "anthropic_messages" for e in native)
    assert all(set(e.extra_headers) == {"anthropic-version", "anthropic-beta"} for e in native)
    others = [e for e in entries if e not in native]
    assert all(e.api == "openai_chat" and e.extra_headers == {} for e in others)


def _declaration(**fields: Any) -> dict[str, Any]:
    return {
        "id": "native",
        "provider": "Native",
        "base_url": "https://api.example.com/v1",
        "model": "native-1",
        "context": 8192,
        "hosting_text": "Ailleurs.",
        "training": "no",
        **fields,
    }


def test_api_accepts_only_an_api_with_an_adapter():
    assert config.CloudModel.model_validate(_declaration()).api == "openai_chat"
    native = config.CloudModel.model_validate(_declaration(api="anthropic_messages"))
    assert native.api == "anthropic_messages"  # native providers 3/5
    for api in ("openai_responses", "fake_api"):
        with pytest.raises(ValidationError):
            config.CloudModel.model_validate(_declaration(api=api))


@pytest.mark.parametrize(
    ("auth", "name"),
    [
        ({}, "Content-Type"),
        ({}, "content-type"),
        ({}, "accept"),
        ({}, "User-Agent"),
        ({}, "Authorization"),
        ({}, "AUTHORIZATION"),
        ({"auth_header": {"name": "x-api-key", "scheme": ""}}, "X-Api-Key"),
    ],
)
def test_extra_headers_refuses_a_public_or_reserved_header(auth, name):
    with pytest.raises(ValidationError) as caught:
        config.CloudModel.model_validate(_declaration(**auth, extra_headers={name: "x"}))
    assert f"« {name} »" in str(caught.value) and "extra_headers" in str(caught.value)


def test_extra_headers_accepts_a_fixed_header():
    entry = config.CloudModel.model_validate(
        _declaration(
            auth_header={"name": "x-api-key", "scheme": ""},
            extra_headers={"anthropic-version": "2023-06-01"},
        )
    )
    assert entry.extra_headers == {"anthropic-version": "2023-06-01"}


# ---------- the engine and the translator, chosen by `api` (AD-26) ----------


def test_the_api_field_the_engines_and_the_translators_name_the_same_apis():
    """AD-26: an API enters `CloudModel.api`, `ENGINES` and `TRANSLATORS` together."""
    declared = set(get_args(config.CloudModel.model_fields["api"].annotation))
    assert declared == set(cloud_api.ENGINES) == set(render_module.TRANSLATORS)


def test_the_factory_gives_the_openai_chat_engine():
    entry = config.load_config().cloud_model("groq")
    engine = create_cloud_engine(
        entry, SecretStr(SENTINEL), connect_timeout_s=1.0, read_timeout_s=1.0
    )
    try:
        assert type(engine) is OpenAIChatEngine and engine.api == entry.api == "openai_chat"
    finally:
        engine.close()


class FakeNativeEngine(OpenAIChatEngine):
    """An API of the test only: its own path, and the Chat Completions stream to read."""

    api = "fake_api"
    endpoint = "/fake/native"


def _fake_translator(
    model: dict[str, Any], messages: list[dict[str, Any]], tools: Any, tail: dict[str, Any]
) -> dict[str, Any]:
    """A native shape: the system apart, the rest under `input`, tools under `functions`."""
    system = [m["content"] for m in messages if m["role"] == "system"]
    rest = [m for m in messages if m["role"] != "system"]
    return {
        **model,
        "system": system,
        "input": rest,
        **({"functions": tools} if tools else {}),
        **tail,
    }


@pytest.fixture
def fake_api(monkeypatch):
    """`fake_api` registered for the test's duration: its engine and its translator."""
    monkeypatch.setitem(cloud_api.ENGINES, "fake_api", FakeNativeEngine)
    monkeypatch.setitem(render_module.TRANSLATORS, "fake_api", _fake_translator)


def _native_entry(**update: Any) -> config.CloudModel:
    entry = config.load_config().cloud_model("groq")
    # `api` accepts `openai_chat` only: the test's API enters without validation.
    return entry.model_copy(update={"api": "fake_api", **update})


def _session(entry: config.CloudModel, provider: Provider) -> AppSession:
    """Engines from `create_cloud_engine`, on the provider's transport; the tools brick on."""
    cfg = config.load_config()
    config.write_api_key(entry.id, entry.host, SecretStr(SENTINEL))

    def factory(entry, key):  # noqa: ANN001, ANN202
        return create_cloud_engine(
            entry,
            key,
            connect_timeout_s=cfg.cloud_connect_timeout_s,
            read_timeout_s=cfg.cloud_read_timeout_s,
            transport=httpx.MockTransport(provider),
        )

    session = AppSession(cfg, cloud_factory=factory)
    session.boot_cloud(entry).result()
    session.set_brick("tools", True)
    session.join()
    return session


def test_default_factories_choose_the_engine_by_api(fake_api):
    cfg = config.load_config()
    key = SecretStr(SENTINEL)
    session = AppSession(cfg)
    try:
        for factory in (session._cloud_factory, DiagnosticSession(cfg, 8420)._cloud_factory):
            for entry, kind in (
                (cfg.cloud_model("groq"), OpenAIChatEngine),
                (_native_entry(), FakeNativeEngine),
            ):
                engine = factory(entry, key)
                try:
                    assert type(engine) is kind
                finally:
                    engine.close()
    finally:
        session.close()


def test_an_api_of_the_registry_writes_its_body_and_sends_it_as_traced(fake_api, caplog):
    provider = Provider(GROQ_TOOL, GROQ_TEXT)
    session = _session(_native_entry(), provider)
    try:
        events = _turn(session, "Quelle heure est-il ?")
    finally:
        session.close()

    assert _of(events, "turn_ended")[0].payload["status"] == "completed"
    rendered = _of(events, "context_rendered")
    outbound = _of(events, "outbound_request")
    assert len(rendered) == len(outbound) == len(provider.requests) == 2
    for ctx, out, request in zip(rendered, outbound, provider.requests, strict=True):
        # CAP-1: the body sent = `context_rendered.body` = `outbound_request.body`.
        assert request.content == ctx.payload["body"].encode("utf-8")
        assert out.payload["body"] == ctx.payload["body"] and out.call_id == ctx.call_id
        assert request.url.path.endswith("/fake/native")
        body = json.loads(ctx.payload["body"])
        assert "messages" not in body and body["functions"][0]["function"]["name"]
        assert "system" in body and body["input"][-1]["role"] in ("user", "tool")
        # AD-4: the segments are still the bytes sent.
        assert "".join(s["text"] for s in ctx.payload["segments"]) == ctx.payload["body"]
    second = json.loads(rendered[1].payload["body"])["input"]
    assert [m["role"] for m in second][-2:] == ["assistant", "tool"]
    journal = "\n".join(e.model_dump_json() for e in get_journal().all_events())
    _no_sentinel(journal, caplog.text)


def test_the_llm_lab_and_the_test_call_use_the_translator_of_the_api(fake_api, monkeypatch):
    provider = Provider(GROQ_TOOL, GROQ_TEXT)
    entry = _native_entry()
    session = _session(entry, provider)
    try:
        session.llm_generate("Bonjour", DEFAULT_SAMPLING)
        session.join()
    finally:
        session.close()
    assert json.loads(provider.requests[-1].content)["input"][0]["role"] == "user"

    cfg = config.load_config()
    monkeypatch.setattr(type(cfg), "cloud_model", lambda self, model_id: entry)
    tested = Provider(GROQ_TOOL, GROQ_TEXT)
    diagnostic = DiagnosticSession(
        cfg,
        8420,
        cloud_factory=lambda e, k: create_cloud_engine(
            e, k, connect_timeout_s=1.0, read_timeout_s=1.0, transport=httpx.MockTransport(tested)
        ),
    )
    diagnostic.test_cloud_model(entry.id)
    assert len(tested.requests) == 2
    assert all(r.url.path.endswith("/fake/native") for r in tested.requests)
    assert all("input" in json.loads(r.content) for r in tested.requests)


def test_extra_headers_are_sent_on_each_request_and_masked_in_the_trace():
    provider = Provider(GROQ_TOOL, GROQ_TEXT)
    entry = config.load_config().cloud_model("groq")
    entry = entry.model_copy(update={"extra_headers": {"anthropic-version": "2023-06-01"}})
    session = _session(entry, provider)
    try:
        events = _turn(session, "Quelle heure est-il ?")
    finally:
        session.close()

    outbound = _of(events, "outbound_request")
    assert len(provider.requests) == len(outbound) == 2
    for request, out in zip(provider.requests, outbound, strict=True):
        assert request.headers["anthropic-version"] == "2023-06-01"
        names = [n.decode("latin-1").lower() for n, _ in request.headers.raw]
        # After the authentication header, set per request (AD-5).
        assert names.index("anthropic-version") > names.index("authorization")
        traced = {h["name"]: (h["value"], h["masked"]) for h in out.payload["headers"]}
        assert traced["anthropic-version"] == ("[masqué]", True)


def test_an_entry_without_extra_headers_sends_content_type_and_the_key_only():
    entry = config.load_config().cloud_model("groq")
    engine = create_cloud_engine(
        entry, SecretStr(SENTINEL), connect_timeout_s=1.0, read_timeout_s=1.0
    )
    try:
        assert engine._headers() == {
            "Content-Type": "application/json",
            "Authorization": f"Bearer {SENTINEL}",
        }
    finally:
        engine.close()
