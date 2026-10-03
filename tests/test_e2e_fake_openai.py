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
from wavestack.models.openai_chat import ChatBody, ChatEnd, OpenAIChatEngine, ProviderError

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
    # The harness sends back the call as the model made it (story 21: compared with its
    # arguments, the same tool may be called again with others).
    arguments = first.tool_calls[0]["arguments"]
    call = {"id": "c1", "function": {"name": "load_tool_doc", "arguments": arguments}}
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


def test_markdown_trigger_answers_the_sample_with_its_injections():
    """Recette du 02/10: « [markdown] » covers the rendering and the injections to keep as text."""
    reply = fake.plan_reply(_body(_user("Montre le rendu [markdown]"), tools=("get_datetime",)))
    assert reply.status == 200 and not reply.tool_calls
    assert reply.text == fake.MARKDOWN_SAMPLE
    for piece in (
        "*   **1er janvier :**",
        "3. ",
        "<img src=x onerror=alert(1)>",
        "snake_case_name",
        "# Calendrier\n",  # a single `#`: h3
        "__gras souligné__",
        "1) premier\n2) second\n",
        "Un paragraphe\n2026. Une année\n",  # stays in the paragraph
    ):
        assert piece in reply.text, piece
    for link in ("[clic](javascript:alert(1))", "[relatif](/api/state)", "(https://example.org)"):
        assert link in reply.text, link
    assert reply.text.count("```") == 1  # its last block is still open


def test_quota0_trigger_refuses_as_mistral_without_a_plan():
    """Recette du 02/10 (R2): 429, a request quota of 0 and a request id, the D6 message."""
    client = TestClient(fake.create_app())
    headers = {"Authorization": f"Bearer {fake.EXPECTED_KEY}"}
    answer = client.post(
        "/v1/chat/completions", json=_body(_user("Bonjour [quota0]")), headers=headers
    )
    assert answer.status_code == 429
    assert answer.headers["x-ratelimit-limit-req-minute"] == "0"
    assert answer.headers["x-ratelimit-remaining-req-minute"] == "0"
    assert answer.headers["x-request-id"]
    assert answer.json() == {"error": {"message": "Rate limit exceeded"}}

    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(429, headers=dict(answer.headers), content=answer.content)

    engine = OpenAIChatEngine(
        _entry(), SecretStr(fake.EXPECTED_KEY), transport=httpx.MockTransport(handler)
    )
    with pytest.raises(ProviderError) as refused:
        list(engine.complete(ChatBody(b"{}"), CancelToken()))
    assert "Aucun quota actif sur ce compte" in refused.value.message_text


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


def test_reranker_file_fails_while_armed_then_is_served_again():
    """Restes différés, story 6 (E094): a failed download of the reranker, then a good one."""
    client = TestClient(fake.create_app())
    assert client.get("/_e2e/reranker.gguf").content == b"\1" * fake.RERANKER_FILE_SIZE
    assert client.post("/_e2e/reranker_fail", json={"fail": True}).json() == {"fail": True}
    assert client.get("/_e2e/reranker.gguf").status_code == 503
    assert client.post("/_e2e/reranker_fail", json={"fail": False}).json() == {"fail": False}
    assert client.get("/_e2e/reranker.gguf").status_code == 200


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
        hosting_text="Ce poste",
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


def test_delegation_then_the_sub_agent_reads_the_guide():
    ask = _user("Délègue à ton sous-agent la lecture du fichier guide_harnais.md.")
    main = fake.plan_reply(_body(ask, tools=("read_file", "delegate")))
    assert [c["name"] for c in main.tool_calls] == ["delegate"]
    task = json.loads(main.tool_calls[0]["arguments"])["task"]
    system = {"role": "system", "content": "Sous-agent."}
    sub = fake.plan_reply(_body(system, _user(task), tools=("read_file",)))
    assert sub.tool_calls == [{"name": "read_file", "arguments": '{"path": "guide_harnais.md"}'}]


def _prompts(scenario_id: str) -> list[str]:
    """The scenario's prompts, as `content/scenarios.yaml` writes them (folded)."""
    import yaml

    from wavestack import config

    path = config.content_dir() / "scenarios.yaml"
    return yaml.safe_load(path.read_text(encoding="utf-8"))["scenarios"][scenario_id]["prompts"]


def _called(body: dict, name: str, arguments: dict, result: str) -> dict:
    """`body` after the call `name(arguments)` and its result."""
    call = {
        "id": f"c{len(body['messages'])}",
        "type": "function",
        "function": {"name": name, "arguments": json.dumps(arguments, ensure_ascii=False)},
    }
    body["messages"] += [
        {"role": "assistant", "tool_calls": [call]},
        {"role": "tool", "tool_call_id": call["id"], "content": result},
    ]
    return body


def _calls(reply) -> list[tuple[str, dict]]:  # noqa: ANN001
    return [(c["name"], json.loads(c["arguments"])) for c in reply.tool_calls]


def test_soc_prompts_read_the_alerts_then_look_for_the_file_and_escalate():
    """Story 21: the scenario's own prompts. The second names no file: the model lists the
    folder, then reads the privileged accounts' inventory, which H1 blocks."""
    first, second = _prompts("soc")
    tools = ("read_file",)
    assert _calls(fake.plan_reply(_body(_user(first), tools=tools))) == [
        ("read_file", {"path": "alertes_siem.log"})
    ]
    body = _body(_user(second), tools=tools)
    assert _calls(fake.plan_reply(body)) == [("read_file", {"path": "."})]
    listing = (
        "alertes_siem.log\nconfidentiel/budget_projet.txt\nconfidentiel/comptes_privilegies.txt"
    )
    body = _called(body, "read_file", {"path": "."}, listing)
    wanted = ("read_file", {"path": "confidentiel/comptes_privilegies.txt"})
    assert _calls(fake.plan_reply(body)) == [wanted]
    body = _called(body, *wanted, "Bloqué par le hook garde-fou : « … » est confidentiel.")
    final = fake.plan_reply(body)
    assert not final.tool_calls and "analyste habilité" in final.text


def test_confidential_path_keeps_its_sub_folders():
    ask = _user("Lis confidentiel/rh/salaires.csv.")
    assert _calls(fake.plan_reply(_body(ask, tools=("read_file",)))) == [
        ("read_file", {"path": "confidentiel/rh/salaires.csv"})
    ]


@pytest.mark.parametrize("scenario_id", ["iam", "sovereignty"])
def test_business_mcp_prompts_search_offered_or_lazy_and_say_when_offline(scenario_id):
    """Story 21: every prompt of IAM and sovereignty calls its server's search when it is
    offered, loads its documentation first in lazy loading, and says so offline."""
    searches = {
        "mslearn": "mslearn__microsoft_docs_search",
        "datagouv": "datagouv__search_datasets",
    }
    for prompt in _prompts(scenario_id):
        server = "datagouv" if "data.gouv" in prompt.lower() else "mslearn"
        search = searches[server]
        assert _calls(fake.plan_reply(_body(_user(prompt), tools=(search,))))[0][0] == search
        lazy = {
            "type": "function",
            "function": {"name": "load_tool_doc", "description": f"… {search} : recherche."},
        }
        body = _body(_user(prompt))
        body["tools"] = [lazy]
        assert _calls(fake.plan_reply(body)) == [("load_tool_doc", {"tool": search})]
        offline = fake.plan_reply(_body(_user(prompt)))
        label = "data.gouv.fr" if server == "datagouv" else "Microsoft Learn"
        assert not offline.tool_calls and label in offline.text


def test_an_absent_server_does_not_hide_the_next_triggers():
    ask = _user("Sur data.gouv.fr, quelle heure est-il ?")
    assert _calls(fake.plan_reply(_body(ask, tools=("get_datetime",)))) == [("get_datetime", {})]


def test_story_27_prompts_keep_their_triggers():
    """Story 27: the prompts that now name their tool or skill still reach the scripted
    call: the glossary in both MCP modes, the skill, the log, and the air quality search on
    data.gouv.fr (its own subject, not the sovereignty one)."""
    mcp = _prompts("mcp_full")[0]
    assert mcp == _prompts("mcp_lazy")[0]
    assert _calls(fake.plan_reply(_body(_user(mcp), tools=("local__define_term",)))) == [
        ("local__define_term", {"term": "MCP"})
    ]
    assert _calls(fake.plan_reply(_body(_user(mcp), tools=("load_tool_doc",)))) == [
        ("load_tool_doc", {"tool": "local__define_term"})
    ]
    skill = _prompts("skills")[0]
    assert _calls(fake.plan_reply(_body(_user(skill), tools=("load_skill", "read_file")))) == [
        ("load_skill", {"skill": "meeting_minutes"})
    ]
    log = _prompts("compression")[0]
    assert _calls(fake.plan_reply(_body(_user(log), tools=("read_file",)))) == [
        ("read_file", {"path": "journal_serveur.log"})
    ]
    search = "datagouv__search_datasets"
    for air in (_prompts("mcp_lazy")[1], _prompts("data_flows")[0]):
        tools = (search, "get_datetime", "read_file")
        assert _calls(fake.plan_reply(_body(_user(air), tools=tools))) == [
            (search, {"query": "air"})
        ]
        offline = fake.plan_reply(_body(_user(air), tools=("get_datetime", "read_file")))
        assert not offline.tool_calls and "data.gouv.fr" in offline.text


# ---------- Gemini mode (`model` starting with `gemini`) ----------


def _gemini(*messages: dict, tools: tuple[str, ...] = (), thoughts: bool = False) -> dict:
    body = _body(*messages, tools=tools) | {"model": "gemini-e2e-flash-lite"}
    if thoughts:
        config = {"thinking_level": "medium", "include_thoughts": True}
        body["extra_body"] = {"google": {"thinking_config": config}}
    else:
        body["reasoning_effort"] = "minimal"
    return body


def _signed(name: str, signature: str | None) -> dict:
    call = {"id": "c1", "type": "function", "function": {"name": name, "arguments": "{}"}}
    if signature is not None:
        call["extra_content"] = {"google": {"thought_signature": signature}}
    return call


def test_gemini_mode_signs_each_call_and_thinks_only_when_asked():
    ask = _user("Quelle heure est-il ? [raisonne]")
    reply = fake.plan_reply(_gemini(ask, tools=("get_datetime",)))
    assert reply.gemini and reply.thought == "" and reply.reasoning == ""
    chunks = fake.sse_chunks(reply, {}, "chatcmpl-e2e000007")
    deltas = [c["choices"][0]["delta"] for c in chunks if c.get("choices")]
    first = next(d["tool_calls"][0] for d in deltas if d.get("tool_calls"))
    assert first["extra_content"]["google"]["thought_signature"] == "signature-fausse-000007-0"
    assert not any("reasoning" in d for d in deltas)

    thinking = fake.plan_reply(_gemini(ask, tools=("get_datetime",), thoughts=True))
    assert thinking.thought == fake.GEMINI_THOUGHT
    text = "".join(
        c["choices"][0]["delta"].get("content") or ""
        for c in fake.sse_chunks(fake.plan_reply(_gemini(_user("Bonjour"), thoughts=True)), {}, "c")
    )
    assert text.startswith(f"<thought>{fake.GEMINI_THOUGHT}</thought>")


def test_gemini_mode_refuses_a_call_of_the_turn_sent_back_unsigned():
    ask = _user("Quelle heure est-il ?")
    reply = {"role": "tool", "tool_call_id": "c1", "content": "samedi 10 h"}
    unsigned = {"role": "assistant", "tool_calls": [_signed("get_datetime", None)]}
    refused = fake.plan_reply(_gemini(ask, unsigned, reply, tools=("get_datetime",)))
    assert refused.status == 400 and "thought_signature" in refused.error["message"]
    signed = {"role": "assistant", "tool_calls": [_signed("get_datetime", "sig")]}
    answered = fake.plan_reply(_gemini(ask, signed, reply, tools=("get_datetime",)))
    assert answered.status == 200 and "samedi 10 h" in answered.text
    # A call of an earlier turn (another provider's, say) is not checked, as at Gemini.
    earlier = (_user("Avant"), unsigned, reply, {"role": "assistant", "content": "Oui"})
    assert fake.plan_reply(_gemini(*earlier, ask, tools=("get_datetime",))).status == 200
    # Outside Gemini mode, nothing changes.
    assert fake.plan_reply(_body(ask, unsigned, reply, tools=("get_datetime",))).status == 200


def test_wavestack_adapter_reads_the_fake_gemini_stream_with_the_preset():
    """The preset's `<thought>` tags and the signature, read by `openai_chat` (AD-5)."""
    from wavestack import config

    entry = config.load_config().cloud_model("gemini")
    entry = entry.model_copy(update={"base_url": "http://127.0.0.1:9/v1"})
    body = _gemini(_user("Quelle heure est-il ?"), tools=("get_datetime",), thoughts=True)
    chunks = fake.sse_chunks(fake.plan_reply(body), body, "chatcmpl-test000002")
    sse = "".join(f"data: {json.dumps(c)}\n\n" for c in chunks) + "data: [DONE]\n\n"

    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, text=sse, headers={"content-type": "text/event-stream"})

    engine = OpenAIChatEngine(
        entry, SecretStr(fake.EXPECTED_KEY), transport=httpx.MockTransport(handler)
    )
    items = list(engine.complete(ChatBody(b"{}"), CancelToken()))
    end = items[-1]
    reasoning = "".join(t for c, t in items[:-1] if c == "reasoning")
    assert reasoning == fake.GEMINI_THOUGHT
    assert not any(c == "text" and "<thought>" in t for c, t in items[:-1])
    signature = end.tool_calls[0]["extra_content"]["google"]["thought_signature"]
    assert signature == "signature-fausse-000002-0"


def test_gemini_mode_streams_the_shapes_of_the_real_api():
    """The probe of 2026-09-29: one tool-call chunk without `index`, `finish_reason: "stop"`,
    `usage` on every chunk, thoughts marked and tagged, a closing signature, a 400 array."""
    usage = {"stream_options": {"include_usage": True}}
    body = _gemini(_user("Quelle heure est-il ?"), tools=("get_datetime",)) | usage
    chunks = fake.sse_chunks(fake.plan_reply(body), body, "chatcmpl-e2e000008")
    assert all("usage" in c for c in chunks)
    deltas = [c["choices"][0]["delta"] for c in chunks]
    [with_calls] = [d for d in deltas if d.get("tool_calls")]
    assert "index" not in with_calls["tool_calls"][0]
    assert with_calls["tool_calls"][0]["function"] == {"arguments": "{}", "name": "get_datetime"}
    assert deltas[-1] == {"role": "assistant"}
    assert chunks[-1]["choices"][0]["finish_reason"] == "stop"

    body = _gemini(_user("Bonjour"), thoughts=True) | usage
    chunks = fake.sse_chunks(fake.plan_reply(body), body, "chatcmpl-e2e000009")
    deltas = [c["choices"][0]["delta"] for c in chunks]
    marked = [d for d in deltas if d.get("extra_content") == {"google": {"thought": True}}]
    assert marked[0]["content"].startswith("<thought>")
    assert all("</thought>" not in d["content"] for d in marked)
    closing = deltas[len(marked)]
    assert closing["content"].startswith("</thought>") and "extra_content" not in closing
    assert "content" not in deltas[-1]
    assert deltas[-1]["extra_content"]["google"]["thought_signature"]
    last = chunks[-1]["usage"]
    assert last["total_tokens"] - last["prompt_tokens"] > last["completion_tokens"]

    client = TestClient(fake.create_app())
    headers = {"Authorization": f"Bearer {fake.EXPECTED_KEY}"}
    unsigned = {"role": "assistant", "tool_calls": [_signed("get_datetime", None)]}
    reply = {"role": "tool", "tool_call_id": "c1", "content": "10 h"}
    body = _gemini(_user("Quelle heure est-il ?"), unsigned, reply, tools=("get_datetime",))
    refused = client.post("/v1/chat/completions", json=body, headers=headers)
    assert refused.status_code == 400
    [error] = refused.json()
    assert "`default_api:get_datetime` , position 1" in error["error"]["message"]
    assert error["error"]["status"] == "INVALID_ARGUMENT"


def test_gemini_mode_signs_only_the_first_call_of_a_parallel_set():
    """As the real API (2026-09-29): 3 parallel calls, a signature on the first only; the
    replay is checked on each assistant message's first call."""
    reply = fake.Reply(
        tool_calls=[{"name": n, "arguments": "{}"} for n in ("a", "b", "c")], gemini=True
    )
    [calls] = [
        c["choices"][0]["delta"]["tool_calls"]
        for c in fake.sse_chunks(reply, {}, "chatcmpl-e2e000010")
        if c["choices"][0]["delta"].get("tool_calls")
    ]
    assert [("extra_content" in c) for c in calls] == [True, False, False]

    ask = _user("Quelle heure est-il ?")
    result = {"role": "tool", "tool_call_id": "c1", "content": "10 h"}
    first_signed = [_signed("get_datetime", "sig"), _signed("calculator", None)]
    unsigned = [_signed("get_datetime", None), _signed("calculator", None)]
    for calls, status in ((first_signed, 200), (unsigned, 400)):
        sent = {"role": "assistant", "tool_calls": calls}
        body = _gemini(ask, sent, result, tools=("get_datetime", "calculator"))
        assert fake.plan_reply(body).status == status
