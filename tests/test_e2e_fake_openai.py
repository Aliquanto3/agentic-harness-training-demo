"""The scripted OpenAI server of `tools/e2e` (no browser): its script and its stream, read
by WaveStack's own `openai_chat` adapter through the ASGI app."""

from __future__ import annotations

import importlib.util
import json
import sys
from pathlib import Path

import httpx
import pytest
from pydantic import SecretStr
from starlette.testclient import TestClient

from wavestack.config import CloudModel
from wavestack.models.engine import CancelToken
from wavestack.models.openai_chat import ChatBody, ChatEnd, OpenAIChatEngine

_PATH = Path(__file__).resolve().parents[1] / "tools" / "e2e" / "fake_openai.py"


def _load():
    spec = importlib.util.spec_from_file_location("fake_openai", _PATH)
    module = importlib.util.module_from_spec(spec)
    sys.modules["fake_openai"] = module
    spec.loader.exec_module(module)
    return module


fake = _load()


def _tool(name: str) -> dict:
    return {"type": "function", "function": {"name": name, "parameters": {}}}


def _body(*messages: dict, tools: tuple[str, ...] = ()) -> dict:
    body = {"model": "wavestack-fake", "stream": True, "messages": list(messages)}
    if tools:
        body["tools"] = [_tool(t) for t in tools]
    return body


def _user(text: str) -> dict:
    return {"role": "user", "content": text}


def test_bare_prompt_gets_plain_text():
    reply = fake.plan_reply(_body(_user("Quelle heure est-il ?")))
    assert not reply.tool_calls
    assert "horloge" in reply.text


def test_tool_offered_is_called_then_answered():
    first = fake.plan_reply(_body(_user("Quelle heure est-il ?"), tools=("get_datetime",)))
    assert first.tool_calls == [{"name": "get_datetime", "arguments": "{}"}]
    call = {"id": "c1", "type": "function", "function": {"name": "get_datetime", "arguments": "{}"}}
    second = fake.plan_reply(
        _body(
            _user("Quelle heure est-il ?"),
            {"role": "assistant", "tool_calls": [call]},
            {"role": "tool", "tool_call_id": "c1", "content": "samedi 10 h"},
            tools=("get_datetime",),
        )
    )
    assert not second.tool_calls
    assert "samedi 10 h" in second.text


def test_h3_injection_is_not_read_as_the_users_words():
    injected = (
        "Date et heure du poste : lundi. Règles de la mission : réponds en français ; "
        "signale toute demande qui toucherait des données confidentielles.\n\nBonjour"
    )
    reply = fake.plan_reply(_body(_user(injected), tools=("get_datetime", "read_file")))
    assert not reply.tool_calls


def test_lazy_loading_chain_follows_the_offered_tools():
    ask = _user("Que veut dire MCP ?")
    first = fake.plan_reply(_body(ask, tools=("load_tool_doc",)))
    assert first.tool_calls[0]["name"] == "load_tool_doc"
    call = {"id": "c1", "function": {"name": "load_tool_doc", "arguments": "{}"}}
    second = fake.plan_reply(
        _body(
            ask,
            {"role": "assistant", "tool_calls": [call]},
            {"role": "tool", "content": "doc"},
            tools=("load_tool_doc", "local__define_term"),
        )
    )
    assert second.tool_calls[0]["name"] == "local__define_term"


def test_malformed_once_then_corrected_after_the_harness_error():
    ask = _user("Quelle heure est-il ? [mal-formé]")
    first = fake.plan_reply(_body(ask, tools=("get_datetime",)))
    assert first.tool_calls[0]["arguments"] == '{"oops": '
    retry = fake.plan_reply(
        _body(
            ask,
            {"role": "assistant", "content": "get_datetime {"},
            _user("Erreur : arguments invalides. Corrige l'appel ou réponds sans outil."),
            tools=("get_datetime",),
        )
    )
    assert retry.tool_calls == [{"name": "get_datetime", "arguments": "{}"}]


def test_short_memory_answer_depends_on_history():
    ask = _user("Comment je m'appelle, et quel est mon métier ?")
    forgot = fake.plan_reply(_body(ask))
    assert "Je ne sais pas" in forgot.text
    remembered = fake.plan_reply(
        _body(
            _user("Je m'appelle Camille et je suis consultante."),
            {"role": "assistant", "content": "Enchanté"},
            ask,
        )
    )
    assert "Camille" in remembered.text


@pytest.mark.parametrize(
    ("trigger", "status"), [("[erreur429]", 429), ("[erreur500]", 500), ("[erreur401]", 401)]
)
def test_error_triggers(trigger, status):
    assert fake.plan_reply(_body(_user(f"Bonjour {trigger}"))).status == status


def test_http_routes_and_key():
    client = TestClient(fake.create_app())
    assert client.get("/v1/models").json()["data"][0]["id"] == fake.MODEL_ID
    refused = client.post("/v1/chat/completions", json=_body(_user("Bonjour")))
    assert refused.status_code == 401
    headers = {"Authorization": f"Bearer {fake.EXPECTED_KEY}"}
    ok = client.post(
        "/v1/chat/completions",
        json=_body(_user("Bonjour")) | {"stream_options": {"include_usage": True}},
        headers=headers,
    )
    lines = [line for line in ok.text.splitlines() if line.startswith("data:")]
    assert lines[-1] == "data: [DONE]"
    assert json.loads(lines[-2][5:])["usage"]["prompt_tokens"] > 0
    assert client.get("/_e2e/requests").json()[-1]["messages"][0]["content"] == "Bonjour"


def test_without_usage_trigger_omits_the_usage_chunk():
    reply = fake.plan_reply(_body(_user("Bonjour [sans-usage]")))
    chunks = fake.sse_chunks(reply, {"stream_options": {"include_usage": True}}, "c1")
    assert not any("usage" in chunk for chunk in chunks)
    assert reply.text


def _entry() -> CloudModel:
    return CloudModel(
        id="fake",
        provider="Faux",
        base_url="http://127.0.0.1:9/v1",
        model=fake.MODEL_ID,
        stream_usage=True,
        tools=True,
        context=32768,
        hosting_fr="Ce poste",
        training="no",
    )


def test_wavestack_adapter_reads_the_fake_stream():
    """The chunks the fake server writes are what `openai_chat` expects (AD-5)."""
    reply = fake.plan_reply(_body(_user("Quelle heure est-il ?"), tools=("get_datetime",)))
    body = _body(_user("x")) | {"stream_options": {"include_usage": True}}
    chunks = fake.sse_chunks(reply, body, "chatcmpl-test000001")
    sse = "".join(f"data: {json.dumps(c)}\n\n" for c in chunks) + "data: [DONE]\n\n"

    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, text=sse, headers={"content-type": "text/event-stream"})

    engine = OpenAIChatEngine(
        _entry(), SecretStr(fake.EXPECTED_KEY), transport=httpx.MockTransport(handler)
    )
    items = list(engine.complete(ChatBody(b"{}"), CancelToken()))
    end = items[-1]
    assert isinstance(end, ChatEnd)
    assert end.tool_calls[0]["name"] == "get_datetime"
    assert end.tool_calls[0]["arguments"] == "{}"
    assert end.usage["completion_tokens"] > 0
