"""Story 11: cloud models through `openai_chat` (AD-4, AD-5, AD-15, AD-16, AD-20, AD-21).

Every provider answer comes from an `httpx.MockTransport`: nothing leaves the machine.
"""

from __future__ import annotations

import json
import logging
import threading
import time

import httpx
import pytest
from pydantic import SecretStr
from starlette.testclient import TestClient

from wavestack import config
from wavestack.context.render import distribute
from wavestack.models import discovery
from wavestack.models.openai_chat import OpenAIChatEngine, _quota_scope
from wavestack.session.app_session import AppSession
from wavestack.session.diagnostic import DiagnosticSession
from wavestack.trace.journal import get_journal
from wavestack.web.app import create_app

SENTINEL = "gsk_SENTINEL_0123456789_abcdefWXYZ"
ORIGIN = {"Origin": "http://127.0.0.1:8420"}


def sse(*chunks: dict) -> bytes:
    return ("".join(f"data: {json.dumps(c)}\n\n" for c in chunks) + "data: [DONE]\n\n").encode()


def delta(finish=None, **fields) -> dict:
    return {"choices": [{"index": 0, "delta": fields, "finish_reason": finish}]}


GROQ_TOOL = sse(
    delta(role="assistant", reasoning="Il faut l'heure."),
    delta(
        tool_calls=[
            {
                "index": 0,
                "id": "call_provider",
                "type": "function",
                "function": {"name": "get_datetime", "arguments": "{}"},
            }
        ]
    ),
    {
        **delta("tool_calls"),
        "x_groq": {"usage": {"prompt_tokens": 700, "completion_tokens": 12}},
    },
)
GROQ_TEXT = sse(
    delta(content="Il est 9 h."),
    {**delta("stop"), "x_groq": {"usage": {"prompt_tokens": 760, "completion_tokens": 5}}},
)


class Provider:
    """A scripted provider: one response per request, the last one repeated."""

    def __init__(self, *responses: httpx.Response | bytes) -> None:
        self.responses = responses
        self.requests: list[httpx.Request] = []
        self.sent_at: list[float] = []  # `time.monotonic()` of each request

    def __call__(self, request: httpx.Request) -> httpx.Response:
        self.requests.append(request)
        self.sent_at.append(time.monotonic())
        answer = self.responses[min(len(self.requests) - 1, len(self.responses) - 1)]
        if isinstance(answer, bytes):
            return httpx.Response(
                200, content=answer, headers={"content-type": "text/event-stream"}
            )
        return answer

    def factory(self, entry, key):  # noqa: ANN001
        return OpenAIChatEngine(entry, key, transport=httpx.MockTransport(self))


def _cloud_session(model_id: str, provider: Provider, *, bricks=()) -> AppSession:
    cfg = config.load_config()
    entry = cfg.cloud_model(model_id)
    config.write_api_key(entry.id, entry.host, SecretStr(SENTINEL))
    session = AppSession(cfg, cloud_factory=provider.factory)
    session.boot_cloud(entry).result()
    for brick in bricks:
        session.set_brick(brick, True)
    session.join()
    return session


def _turn(session: AppSession, message: str) -> list:
    mark = get_journal().last_seq()
    session.send(message)
    session.join()
    return get_journal().events_since(mark)


def _of(events, kind):
    return [e for e in events if e.kind == kind]


def _no_sentinel(*texts: str) -> None:
    for text in texts:
        for piece in (SENTINEL, SENTINEL[4:-4]):
            assert piece not in text


def _journal_text() -> str:
    return "\n".join(e.model_dump_json() for e in get_journal().all_events())


def test_groq_turn_with_tool_two_calls_reconciled_body_is_the_one_sent(caplog):
    caplog.set_level(logging.DEBUG)
    provider = Provider(GROQ_TOOL, GROQ_TEXT)
    session = _cloud_session("groq", provider, bricks=("tools",))

    events = _turn(session, "Quelle heure est-il ?")

    assert _of(events, "turn_ended")[0].payload["status"] == "completed"
    rendered = _of(events, "context_rendered")
    outbound = _of(events, "outbound_request")
    reconciled = _of(events, "context_reconciled")
    assert len(rendered) == len(outbound) == len(reconciled) == len(provider.requests) == 2
    for ctx, out, request in zip(rendered, outbound, provider.requests, strict=True):
        # AD-5: the body sent = `context_rendered.body` = the traced body, same call.
        assert request.content == ctx.payload["body"].encode("utf-8")
        assert out.payload["body"] == ctx.payload["body"] and out.call_id == ctx.call_id
        assert out.payload["origin"] == "model" and out.component == "core.model"
        assert "".join(s["text"] for s in ctx.payload["segments"]) == ctx.payload["body"]
        assert all(s["estimated"] for s in ctx.payload["segments"])
        assert set(request.headers) >= {"authorization", "content-type"}
    body = json.loads(rendered[0].payload["body"])
    assert body["model"] == "openai/gpt-oss-120b" and body["stream"] is True
    assert body["reasoning_effort"] == "low" and body["stream_options"] == {"include_usage": True}
    assert body["max_tokens"] == 1536 and body["tools"][0]["function"]["name"] == "get_datetime"
    # The window: min(4096, 131072, 8000 // 2) = 4000, `usable` 2464 (AD-9).
    assert rendered[0].payload["window"] == 4000 and rendered[0].payload["usable"] == 2464
    assert rendered[0].payload["window_source"] == "tpm"

    # AD-4: the session's `tool_call_id` in the 2nd body, the provider's in model_call_ended.
    ended = _of(events, "model_call_ended")[0].payload
    call = ended["tool_calls"][0]
    assert call["provider_id"] == "call_provider" and len(call["id"]) == 9
    second = json.loads(rendered[1].payload["body"])["messages"]
    assistant = next(m for m in second if m["role"] == "assistant")
    assert assistant["tool_calls"][0]["id"] == call["id"] and "content" not in assistant
    assert assistant["tool_calls"][0]["function"]["arguments"] == "{}"
    reply = next(m for m in second if m["role"] == "tool")
    assert reply["tool_call_id"] == call["id"] and "name" not in reply
    assert "call_provider" not in rendered[1].payload["body"]
    assert "Il faut l'heure." not in rendered[1].payload["body"]  # no reasoning sent back

    # After each call, the sums equal `usage.prompt_tokens`, shown without « ≈ ».
    for payload, total in zip((r.payload for r in reconciled), (700, 760), strict=True):
        assert payload["used"] == total == sum(s["tokens"] for s in payload["segments"])
        assert payload["usage_source"] == "api"
    assert ended["usage_source"] == "api" and ended["prompt_tokens"] == 700
    _no_sentinel(_journal_text(), caplog.text)


def test_mistral_content_blocks_split_reasoning_and_text():
    stream = sse(
        delta(content=[{"type": "thinking", "thinking": [{"type": "text", "text": "Réfléchir."}]}]),
        delta(content=[{"type": "text", "text": "Bonjour."}]),
        {**delta("stop"), "usage": {"prompt_tokens": 40, "completion_tokens": 3}},
    )
    provider = Provider(stream)
    session = _cloud_session("mistral", provider)

    events = _turn(session, "Bonjour")

    ended = _of(events, "model_call_ended")[0].payload
    assert ended["reasoning"] == "Réfléchir." and ended["text"] == "Bonjour."
    assert ended["usage_source"] == "api" and ended["prompt_tokens"] == 40
    channels = {d.payload["channel"] for d in _of(events, "model_delta")}
    assert channels == {"reasoning", "text"}
    body = json.loads(_of(events, "context_rendered")[0].payload["body"])
    assert body["reasoning_effort"] == "none" and "stream_options" not in body
    assert body["max_tokens"] == 512 and "tools" not in body


@pytest.mark.parametrize(
    ("status", "headers", "error", "fragment", "scope"),
    [
        (
            429,
            {"retry-after": "7"},
            "Rate limit reached for model `openai/gpt-oss-120b` on tokens per minute (TPM): "
            "Limit 8000, Used 7900. Need more tokens? Upgrade to Dev Tier today at "
            "https://console.groq.com/settings/billing",
            "quota",
            "minute",
        ),
        (413, {}, "Request too large", "dépasse à elle seule", None),
        (401, {}, "Invalid API Key " + SENTINEL, "Clé refusée", None),
        (404, {}, "model not found", "Modèle introuvable", None),
        (503, {}, "overloaded", "indisponible", None),
        (
            400,
            {},
            "This model's maximum context length is 131072 tokens",
            "Contexte dépassé",
            None,
        ),
        (400, {}, "Invalid parameter 'foo' " + SENTINEL, "Requête refusée", None),
        (422, {}, "Unprocessable entity", "Requête refusée", None),
    ],
)
def test_provider_refusals_become_explained_errors(status, headers, error, fragment, scope):
    answer = httpx.Response(status, json={"error": {"message": error}}, headers=headers)
    provider = Provider(answer, GROQ_TEXT)
    session = _cloud_session("groq", provider)

    events = _turn(session, "Bonjour")

    harness = _of(events, "harness_error")[0].payload
    assert fragment in harness["message_fr"] and harness["hints_fr"]
    # Story 11b: the provider's own message ends every refusal, masked.
    masked = error.replace(SENTINEL, "•••")
    assert harness["message_fr"].endswith(f"Message du fournisseur : {masked}")
    assert harness["http_status"] == status and harness["quota_scope"] == scope
    if status == 429:
        assert harness["retry_after_s"] == 7
    assert _of(events, "turn_ended")[0].payload["status"] == "error"
    assert len(provider.requests) == 1  # never retried (AD-16)
    assert session.state == "idle"
    _no_sentinel(_journal_text())
    # The application stays usable.
    assert _of(_turn(session, "Encore"), "turn_ended")[0].payload["status"] == "completed"


def test_redirect_is_refused_and_the_key_never_follows():
    moved = httpx.Response(302, headers={"location": "https://evil.example/v1"})
    provider = Provider(moved)
    session = _cloud_session("groq", provider)

    events = _turn(session, "Bonjour")

    assert "Redirection refusée" in _of(events, "harness_error")[0].payload["message_fr"]
    assert [r.url.host for r in provider.requests] == ["api.groq.com"]
    assert _of(events, "turn_ended")[0].payload["status"] == "error"


def test_invalid_arguments_retry_and_run_no_tool():
    bad = sse(
        delta(
            tool_calls=[
                {"index": 0, "id": "c1", "function": {"name": "calculator", "arguments": "{2*3"}}
            ]
        ),
        delta("tool_calls"),
    )
    provider = Provider(bad, GROQ_TEXT)
    session = _cloud_session("groq", provider, bricks=("tools",))

    events = _turn(session, "Calcule 2*3")

    malformed = _of(events, "tool_call_malformed")
    assert len(malformed) == 1 and malformed[0].payload["reaction"] == "retry"
    assert _of(events, "tool_started") == []
    assert "id" not in _of(events, "model_call_ended")[0].payload["tool_calls"][0]
    second = json.loads(_of(events, "context_rendered")[1].payload["body"])["messages"]
    assert second[-2] == {"role": "assistant", "content": "calculator {2*3"}
    assert second[-1]["role"] == "user" and second[-1]["content"].startswith("Erreur")
    assert _of(events, "turn_ended")[0].payload["status"] == "completed"


def test_tool_use_failed_follows_the_malformed_path():
    said = f"Tool call validation failed: tool is not in request.tools ({SENTINEL})"
    failed = httpx.Response(
        400,
        json={
            "error": {
                "message": said,
                "code": "tool_use_failed",
                "failed_generation": "<function=get_datetime>",
            }
        },
    )
    provider = Provider(failed, GROQ_TEXT)
    session = _cloud_session("groq", provider, bricks=("tools",))

    events = _turn(session, "Heure ?")

    malformed = _of(events, "tool_call_malformed")[0].payload
    assert malformed["raw"] == "<function=get_datetime>"
    # Story 11b: the provider's message, masked, in the detail and in the reinjected text.
    masked = said.replace(SENTINEL, "•••")
    assert malformed["detail_fr"] == f"le fournisseur a refusé l'appel d'outil : {masked}"
    reinjected = json.loads(provider.requests[1].content)["messages"][-1]
    assert reinjected["role"] == "user" and masked in reinjected["content"]
    assert reinjected["content"].endswith("Corrige l'appel ou réponds sans outil.")
    assert _of(events, "harness_error") == []
    assert _of(events, "turn_ended")[0].payload["status"] == "completed"
    _no_sentinel(_journal_text())


def test_tool_use_failed_in_the_stream_carries_the_masked_message():
    said = f"Tool call validation failed ({SENTINEL})"
    failed = sse(
        {
            "error": {
                "message": said,
                "code": "tool_use_failed",
                "failed_generation": "<function=get_datetime>",
            }
        }
    )
    provider = Provider(failed, GROQ_TEXT)
    session = _cloud_session("groq", provider, bricks=("tools",))

    events = _turn(session, "Heure ?")

    malformed = _of(events, "tool_call_malformed")[0].payload
    assert malformed["raw"] == "<function=get_datetime>"
    masked = said.replace(SENTINEL, "•••")
    assert malformed["detail_fr"] == f"le fournisseur a refusé l'appel d'outil : {masked}"
    assert _of(events, "turn_ended")[0].payload["status"] == "completed"
    _no_sentinel(_journal_text())


def test_an_html_page_stays_out_of_the_french_message():
    page = "<html><body>Accès bloqué par le proxy de l'entreprise</body></html>"
    answer = httpx.Response(502, text=page, headers={"content-type": "text/html"})
    session = _cloud_session("groq", Provider(answer))

    harness = _of(_turn(session, "Bonjour"), "harness_error")[0].payload

    assert "Message du fournisseur" not in harness["message_fr"]
    assert "proxy" in harness["cause"]


def test_without_tools_declared_the_tools_brick_is_unavailable(monkeypatch):
    settings = {"cloud": {"models": [{"id": "mistral", "tools": False}]}}
    config.settings_path().parent.mkdir(parents=True, exist_ok=True)
    config.settings_path().write_text(json.dumps(settings), encoding="utf-8")
    session = _cloud_session("mistral", Provider(GROQ_TEXT))

    available, reason = session._availability("tools")

    assert not available and "ne déclare pas l'appel d'outils" in reason


# ---------- configuration (AD-9, AD-20) ----------


def test_cloud_models_merge_by_id_and_invalid_entries_are_left_out():
    settings = {
        "cloud": {
            "models": [
                {"id": "groq", "tpm": 6000},
                {"id": "mistral", "enabled": False},
                {"id": "Bad-Id", "provider": "x"},
            ]
        }
    }
    config.settings_path().parent.mkdir(parents=True, exist_ok=True)
    config.settings_path().write_text(json.dumps(settings), encoding="utf-8")

    cfg = config.load_config()
    valid, errors = cfg.cloud_models

    assert [m.id for m in valid] == ["groq"]
    assert valid[0].tpm == 6000 and valid[0].model == "openai/gpt-oss-120b"
    assert len(errors) == 1 and "Bad-Id" in errors[0]
    assert "api.groq.com" in cfg.allowed_hosts and "api.mistral.ai" not in cfg.allowed_hosts
    assert config.cloud_window(valid[0], 4096) == (3000, "tpm")


def test_cloud_window_sources_and_unavailable_quota():
    groq = config.load_config().cloud_model("groq")
    assert config.cloud_window(groq, 4096) == (4000, "tpm")
    assert config.cloud_window(groq.model_copy(update={"window": 2000}), 4096) == (2000, "override")
    small = groq.model_copy(update={"tpm": 3000})
    assert config.cloud_unavailable_fr(small) is not None
    assert config.cloud_unavailable_fr(groq) is None


def test_distribute_largest_remainders():
    assert distribute([300, 100], 360) == ([270, 90], 0)
    assert distribute([300, 100], 450) == ([300, 100], 50)
    shares, gap = distribute([5, 5, 5], 10)
    assert sum(shares) == 10 and gap == 0


# ---------- diagnostic and web intentions (AD-3, AD-18, AD-21) ----------


def _app(monkeypatch, provider: Provider | None = None):
    monkeypatch.setenv("OLLAMA_MODELS", "no-ollama")
    monkeypatch.setenv("HF_HUB_CACHE", "no-hf-cache")
    monkeypatch.setattr(discovery, "_lm_studio_dirs", lambda: [])
    monkeypatch.setattr(discovery, "_server_candidates", lambda cfg: [])
    cfg = config.load_config()
    factory = provider.factory if provider else None
    session = DiagnosticSession(cfg, port=8420, cloud_factory=factory)
    monkeypatch.setattr(session, "check_network", lambda: None)
    app_session = AppSession(cfg, cloud_factory=factory)
    app = create_app(session, port=8420, version="test", app_session=app_session)
    return session, app_session, app, TestClient(app, base_url="http://127.0.0.1:8420")


def test_without_key_test_and_choose_are_disabled_with_the_reason(monkeypatch):
    _, _, _, client = _app(monkeypatch)

    rows = {r["id"]: r for r in client.get("/api/diagnostic").json()["cloud"]["models"]}

    assert set(rows) == {"groq", "mistral"}
    assert rows["groq"]["key_set"] is False and "clé API" in rows["groq"]["disabled_fr"]
    response = client.post("/api/intentions/test_cloud_model", json={"id": "groq"}, headers=ORIGIN)
    assert response.status_code == 409


def test_key_saved_for_another_host_must_be_typed_again(monkeypatch):
    config.write_api_key("groq", "old.example", SecretStr(SENTINEL))
    _, _, _, client = _app(monkeypatch)

    row = client.get("/api/diagnostic").json()["cloud"]["models"][0]

    assert row["key_set"] is False
    assert row["disabled_fr"] == "Clé à ressaisir : l'adresse du fournisseur a changé."


def test_choose_without_confirmation_is_refused_and_nothing_is_written(monkeypatch):
    _, _, _, client = _app(monkeypatch)
    client.post("/api/intentions/set_api_key", json={"id": "groq", "key": SENTINEL}, headers=ORIGIN)

    response = client.post(
        "/api/intentions/select_model", json={"kind": "cloud", "ref": "groq"}, headers=ORIGIN
    )

    assert response.status_code == 409
    assert "avertissement non confirmé" in response.json()["detail"]
    assert "selected_model" not in config.read_settings()


def test_confirmed_choice_boots_then_a_relaunch_takes_it_back_without_request(monkeypatch):
    provider = Provider(GROQ_TEXT)
    session, app_session, _, client = _app(monkeypatch, provider)
    session.check_model()
    client.post("/api/intentions/set_api_key", json={"id": "groq", "key": SENTINEL}, headers=ORIGIN)

    body = client.post(
        "/api/intentions/select_model",
        json={"kind": "cloud", "ref": "groq", "acknowledged": True},
        headers=ORIGIN,
    ).json()
    app_session.join()

    assert body["saved"] is True and body["ready"] is True
    assert config.read_settings()["selected_model"] == {"kind": "cloud", "ref": "groq"}
    state = client.get("/api/state").json()
    assert state["active_model"]["provider"] == "Groq"
    assert state["active_model"]["hosting"] == "network" and state["active_model"]["warning_fr"]
    model = next(n for n in state["architecture_changed"]["nodes"] if n["id"] == "core.model")
    assert model["hosting"] == "network" and model["provider"] == "Groq"

    # Relaunch: the choice is taken back with no warning and no request.
    mark = get_journal().last_seq()
    relaunched = DiagnosticSession(config.load_config(), port=8420)
    result = relaunched.check_model()
    assert result.ready and result.cloud_model is not None and result.cloud_model.id == "groq"
    assert provider.requests == []
    checks = [e.payload for e in get_journal().events_since(mark) if e.kind == "diagnostic_check"]
    assert all(c["status"] == "ok" for c in checks)
    _no_sentinel(json.dumps(state), json.dumps(body), config.settings_path().read_text("utf-8"))


def test_cloud_test_makes_two_calls_without_key_in_the_trace(monkeypatch, caplog):
    caplog.set_level(logging.DEBUG)
    provider = Provider(GROQ_TOOL, GROQ_TEXT)
    _, app_session, _, client = _app(monkeypatch, provider)
    answers = [
        client.post(
            "/api/intentions/set_api_key", json={"id": "groq", "key": SENTINEL}, headers=ORIGIN
        ),
        client.post(  # an invalid one: its validation error never echoes the key
            "/api/intentions/set_api_key", json={"id": 5, "key": SENTINEL}, headers=ORIGIN
        ),
        client.post(
            "/api/intentions/set_api_key", json={"id": "nope", "key": SENTINEL}, headers=ORIGIN
        ),
    ]
    assert [a.status_code for a in answers] == [200, 422, 409]
    mark = get_journal().last_seq()

    response = client.post("/api/intentions/test_cloud_model", json={"id": "groq"}, headers=ORIGIN)

    assert response.status_code == 200 and response.json()["ok"] is True
    events = get_journal().events_since(mark)
    outbound = _of(events, "outbound_request")
    assert len(outbound) == 2 and all(e.payload["origin"] == "model" for e in outbound)
    assert all(e.turn_id is None and e.context_id == "diag" for e in outbound)
    check = _of(events, "diagnostic_check")[-1].payload
    assert check["check"] == "cloud_test" and check["status"] == "ok"
    assert check["tool_call"] == {"name": "get_datetime", "arguments": "{}"}
    assert check["answer"] == "Il est 9 h."
    states = [e.payload["state"] for e in _of(events, "session_state")]
    assert states[0] == "model_load" and states[-1] == "diagnostic"
    assert app_session._ratio == config.load_config().estimate_ratio  # never trained
    _no_sentinel(
        _journal_text(),
        caplog.text,
        *(a.text for a in answers),
        response.text,
        client.get("/api/diagnostic").text,
        client.get("/api/state").text,
    )
    assert json.loads(config.api_keys_path().read_text("utf-8"))["groq"]["key"] == SENTINEL


# ---------- review follow-ups ----------


def test_provider_text_is_masked_and_mistral_model_length_truncates():
    stream = sse(delta(content=f"Votre clé est {SENTINEL}."), delta("model_length"))
    session = _cloud_session("mistral", Provider(stream))

    events = _turn(session, "Bonjour")

    assert _of(events, "output_truncated")[0].payload["channel"] == "text"
    assert _of(events, "turn_ended")[0].payload["status"] == "limit"
    _no_sentinel(_journal_text())


@pytest.mark.parametrize(("factor", "expected"), [(1.2, None), (0.1, 0.8), (10, 1.5)])
def test_ratio_learns_from_real_calls_within_bounds(factor, expected):
    probe = _cloud_session("groq", Provider(GROQ_TEXT))
    raw = probe._render(probe.build_turn_state(), "Bonjour", "t1.main.c1")[0].raw_total
    prompt = max(1, round(raw * factor))  # 0 would mean « no usage »
    usage = {"prompt_tokens": prompt, "completion_tokens": 2}
    session = _cloud_session(
        "groq", Provider(sse(delta(content="Oui."), {**delta("stop"), "usage": usage}))
    )

    _turn(session, "Bonjour")

    assert session._ratio == pytest.approx(expected or prompt / raw)


def test_chat_overflow_is_decided_by_the_raw_estimate_only():
    session = _cloud_session("groq", Provider(GROQ_TEXT))  # usable 2464
    session._ratio = 1.5

    sent = _turn(session, "x" * 8000)  # raw ≈ 2000 ≤ 2464 < 2000 × 1.5
    rendered = _of(sent, "context_rendered")[0].payload
    assert _of(sent, "context_overflow") == [] and rendered["uncertain_fr"]
    assert rendered["used"] > rendered["usable"] and not rendered["overflow"]

    blocked = _turn(session, "x" * 12000)  # raw ≈ 3000 > 2464
    overflow = _of(blocked, "context_overflow")[0].payload
    assert overflow["used"] > overflow["usable"] and "≈" in overflow["message_fr"]
    assert _of(blocked, "turn_ended")[0].payload["status"] == "overflow"


def test_forced_action_ids_and_json_arguments_in_the_chat_body():
    provider = Provider(GROQ_TEXT)
    session = _cloud_session("groq", provider, bricks=("tools",))
    session.arm("tool", "get_datetime", {})

    _turn(session, "Quelle heure est-il ?")

    messages = json.loads(provider.requests[0].content)["messages"]
    at = next(i for i, m in enumerate(messages) if m.get("tool_calls"))
    call, reply = messages[at]["tool_calls"][0], messages[at + 1]
    assert reply["role"] == "tool" and reply["tool_call_id"] == call["id"]
    assert len(call["id"]) == 9 and call["function"]["arguments"] == "{}"


def test_cli_relaunch_prepares_the_saved_cloud_model_without_request(monkeypatch):
    from wavestack import cli

    config.save_setting("selected_model", {"kind": "cloud", "ref": "groq"})
    config.write_api_key("groq", "api.groq.com", SecretStr(SENTINEL))
    provider = Provider(GROQ_TEXT)
    session, app_session, _, _ = _app(monkeypatch, provider)

    cli._run_diagnostic_then_boot(session, app_session)
    app_session.join()

    assert app_session.state == "idle" and app_session.reason_fr is None
    assert app_session.active_model()["provider"] == "Groq"
    assert provider.requests == []


def test_a_choice_after_a_model_is_loaded_waits_for_the_next_launch(monkeypatch, tmp_path):
    provider = Provider(GROQ_TEXT)
    session, app_session, _, client = _app(monkeypatch, provider)
    client.post("/api/intentions/set_api_key", json={"id": "groq", "key": SENTINEL}, headers=ORIGIN)
    session.booted_path = str(tmp_path / "loaded.gguf")  # a GGUF is loaded

    body = client.post(
        "/api/intentions/select_model",
        json={"kind": "cloud", "ref": "groq", "acknowledged": True},
        headers=ORIGIN,
    ).json()
    app_session.join()

    assert body["next_launch"] is True and app_session._cloud is None
    assert config.read_settings()["selected_model"] == {"kind": "cloud", "ref": "groq"}
    # Story 11b: the same text, kept by `/api/diagnostic` for every reload of the page.
    assert body["message_fr"] == "Choix enregistré : relancez WaveStack pour l'utiliser."
    assert client.get("/api/diagnostic").json()["next_launch_fr"] == body["message_fr"]

    session.booted_path, session.booted_cloud = None, "groq"  # a cloud model is loaded
    gguf = tmp_path / "other.gguf"
    gguf.write_bytes(b"placeholder")
    body = client.post(
        "/api/intentions/select_model", json={"kind": "file", "ref": str(gguf)}, headers=ORIGIN
    ).json()
    app_session.join()

    assert body["next_launch"] is True and not app_session.model_loaded
    assert config.read_settings()["selected_model"] == {"kind": "file", "ref": str(gguf)}
    assert body["message_fr"] == "Choix enregistré : relancez WaveStack pour l'utiliser."
    assert client.get("/api/diagnostic").json()["next_launch_fr"] == body["message_fr"]
    assert provider.requests == []

    session.selected_cloud, session.selected_model_path = "groq", None  # the loaded one
    assert client.get("/api/diagnostic").json()["next_launch_fr"] is None


def test_diagnostic_intentions_are_refused_while_the_session_is_busy(monkeypatch):
    provider = Provider(GROQ_TEXT)
    _, app_session, _, client = _app(monkeypatch, provider)
    app_session.state = "turn"

    answers = [
        client.post(path, json=payload, headers=ORIGIN)
        for path, payload in (
            ("/api/intentions/set_api_key", {"id": "groq", "key": SENTINEL}),
            (
                "/api/intentions/select_model",
                {"kind": "cloud", "ref": "groq", "acknowledged": True},
            ),
            ("/api/intentions/test_cloud_model", {"id": "groq"}),
        )
    ]

    assert [a.status_code for a in answers] == [409, 409, 409]
    assert not config.api_keys_path().exists() and "selected_model" not in config.read_settings()
    assert provider.requests == []


def test_select_model_without_ref_nor_path_is_invalid(monkeypatch):
    _, _, _, client = _app(monkeypatch)

    response = client.post("/api/intentions/select_model", json={"kind": "file"}, headers=ORIGIN)

    assert response.status_code == 422 and "ref" in response.json()["detail"]


def test_check_model_warns_on_invalid_entry_and_unusable_saved_cloud(monkeypatch):
    settings = {
        "cloud": {"models": [{"id": "Bad-Id"}]},
        "selected_model": {"kind": "cloud", "ref": "groq"},
    }
    config.settings_path().parent.mkdir(parents=True, exist_ok=True)
    config.settings_path().write_text(json.dumps(settings), encoding="utf-8")
    session, _, _, _ = _app(monkeypatch)
    mark = get_journal().last_seq()

    result = session.check_model()

    checks = [e.payload for e in get_journal().events_since(mark) if e.kind == "diagnostic_check"]
    cloud = [c for c in checks if c["check"] == "cloud"]
    assert len(cloud) == 1 and cloud[0]["status"] == "warn" and not cloud[0]["blocking"]
    assert result.cloud_model is None
    assert "n'est plus utilisable" in [c for c in checks if c["check"] == "model"][-1]["message_fr"]


def test_api_state_gives_the_reconciled_context_after_a_cloud_turn(monkeypatch):
    provider = Provider(GROQ_TEXT)
    _, app_session, _, client = _app(monkeypatch, provider)
    entry = app_session.cfg.cloud_model("groq")
    config.write_api_key(entry.id, entry.host, SecretStr(SENTINEL))
    app_session.boot_cloud(entry).result()

    _turn(app_session, "Bonjour")

    state = client.get("/api/state").json()
    assert state["context_reconciled"]["payload"]["usage_source"] == "api"


# ---------- story 11b: key from the environment ----------


def _row(client, model_id="groq") -> dict:
    rows = client.get("/api/diagnostic").json()["cloud"]["models"]
    return next(r for r in rows if r["id"] == model_id)


def test_key_from_the_environment_variable_tests_and_never_shows(monkeypatch, caplog):
    caplog.set_level(logging.DEBUG)
    monkeypatch.setenv("GROQ_API_KEY", f"  {SENTINEL}  ")
    provider = Provider(GROQ_TOOL, GROQ_TEXT)
    _, _, _, client = _app(monkeypatch, provider)

    row = _row(client)
    response = client.post("/api/intentions/test_cloud_model", json={"id": "groq"}, headers=ORIGIN)

    assert row["key_set"] is True and row["disabled_fr"] is None
    assert row["key_source"] == "env" and row["key_env"] == "GROQ_API_KEY"
    assert response.status_code == 200 and response.json()["ok"] is True
    assert provider.requests[0].headers["authorization"] == f"Bearer {SENTINEL}"  # stripped
    assert not config.api_keys_path().exists()
    _no_sentinel(_journal_text(), caplog.text, response.text, client.get("/api/diagnostic").text)


def test_the_saved_key_comes_before_the_variable(monkeypatch):
    monkeypatch.setenv("GROQ_API_KEY", "env-key-0123456789")
    config.write_api_key("groq", "api.groq.com", SecretStr(SENTINEL))
    provider = Provider(GROQ_TEXT)
    session = _cloud_session("groq", provider)
    _, _, _, client = _app(monkeypatch)

    _turn(session, "Bonjour")

    assert provider.requests[0].headers["authorization"] == f"Bearer {SENTINEL}"
    assert _row(client)["key_source"] == "file"


def test_a_blank_variable_counts_as_no_key(monkeypatch):
    monkeypatch.setenv("GROQ_API_KEY", "   ")
    _, _, _, client = _app(monkeypatch)

    row = _row(client)

    assert row["key_set"] is False and row["key_source"] is None
    assert "clé API" in row["disabled_fr"]
    response = client.post("/api/intentions/test_cloud_model", json={"id": "groq"}, headers=ORIGIN)
    assert response.status_code == 409


def test_a_key_for_another_host_gives_way_to_the_variable(monkeypatch):
    config.write_api_key("groq", "old.example", SecretStr("old-key-0123456789"))
    monkeypatch.setenv("GROQ_API_KEY", SENTINEL)
    _, _, _, client = _app(monkeypatch)

    row = _row(client)

    assert row["key_set"] is True and row["key_source"] == "env" and row["disabled_fr"] is None
    key = config.cloud_key(config.load_config().cloud_model("groq"))
    assert key is not None and key.get_secret_value() == SENTINEL


def test_presets_name_their_variable_and_key_env_is_a_name_only():
    cfg = config.load_config()
    assert cfg.cloud_model("groq").key_env == "GROQ_API_KEY"
    assert cfg.cloud_model("mistral").key_env == "MISTRAL_API_KEY"
    assert cfg.cloud_model("mistral").min_interval_s == 1
    groq = cfg.cloud_model("groq").model_dump()
    for bad in ({"key_env": "gsk_value-with-dash"}, {"min_interval_s": 0}, {"min_interval_s": 61}):
        with pytest.raises(ValueError):
            config.CloudModel.model_validate(groq | bad)


# ---------- story 11b: provider messages and quotas (AD-16) ----------


def test_invalid_key_ends_with_the_provider_message():
    answer = httpx.Response(401, json={"error": {"message": "Invalid API Key"}})
    session = _cloud_session("groq", Provider(answer))

    harness = _of(_turn(session, "Bonjour"), "harness_error")[0].payload

    assert harness["message_fr"].endswith("Message du fournisseur : Invalid API Key")


def test_a_long_provider_message_is_cut_at_500_characters():
    answer = httpx.Response(503, text="x" * 800)
    session = _cloud_session("groq", Provider(answer))

    harness = _of(_turn(session, "Bonjour"), "harness_error")[0].payload

    assert harness["message_fr"].endswith("Message du fournisseur : " + "x" * 500 + "…")


def test_an_error_in_the_stream_carries_the_provider_message():
    stream = sse({"error": {"message": "Internal overload"}})
    session = _cloud_session("groq", Provider(stream))

    harness = _of(_turn(session, "Bonjour"), "harness_error")[0].payload

    assert harness["message_fr"].endswith("Message du fournisseur : Internal overload")


def test_per_second_quota_names_the_second_and_the_spacing():
    answer = httpx.Response(
        429, json={"message": "Requests rate limit exceeded per second", "type": "rate_limited"}
    )
    session = _cloud_session("mistral", Provider(answer))

    harness = _of(_turn(session, "Bonjour"), "harness_error")[0].payload

    assert harness["quota_scope"] == "second"
    assert "quota dépassé par seconde" in harness["message_fr"]
    assert any("min_interval_s" in hint for hint in harness["hints_fr"])


@pytest.mark.parametrize(
    ("message", "scope"),
    [
        ("Requests rate limit exceeded per second", "second"),
        ("Limit 1 rps reached", "second"),
        ("Limit: 5 req/s", "second"),
        ("Rate limit: 1 request per sec", "second"),
        ("Limit 2 req/sec", "second"),
        ("Limit 2 requests/second", "second"),
        ("tokens per minute (TPM). Upgrade today at https://console.groq.com/settings", "minute"),
        ("see https://console.groq.com/settings/billing", "unknown"),
        ("tokens per day (TPD)", "day"),
    ],
)
def test_quota_scope(message, scope):
    assert _quota_scope(message) == scope


def test_unknown_quota_names_the_three_scopes():
    answer = httpx.Response(429, json={"error": {"message": "Too many requests"}})
    session = _cloud_session("groq", Provider(answer))

    harness = _of(_turn(session, "Bonjour"), "harness_error")[0].payload

    assert harness["quota_scope"] == "unknown"
    assert "quota dépassé (par seconde, par minute ou par jour)" in harness["message_fr"]
    assert not any("min_interval_s" in hint for hint in harness["hints_fr"])


# ---------- story 11b: spacing of the sends (min_interval_s) ----------


def _spaced(interval: float) -> None:
    settings = {"cloud": {"models": [{"id": "mistral", "min_interval_s": interval}]}}
    config.settings_path().parent.mkdir(parents=True, exist_ok=True)
    config.settings_path().write_text(json.dumps(settings), encoding="utf-8")


MISTRAL_TEXT = sse(
    delta(content="Oui."), {**delta("stop"), "usage": {"prompt_tokens": 40, "completion_tokens": 2}}
)


def test_two_close_sends_are_spaced_across_adapters_and_the_wait_is_not_timed(monkeypatch):
    _spaced(0.4)
    provider = Provider(MISTRAL_TEXT)
    session = _cloud_session("mistral", provider)
    _, _, _, client = _app(monkeypatch, provider)

    first = _turn(session, "Bonjour")
    mark = get_journal().last_seq()
    response = client.post(  # « Tester » builds its own adapter
        "/api/intentions/test_cloud_model", json={"id": "mistral"}, headers=ORIGIN
    )
    tested = get_journal().events_since(mark)
    second = _turn(session, "Encore")

    assert response.status_code == 200
    gaps = [b - a for a, b in zip(provider.sent_at, provider.sent_at[1:], strict=False)]
    # Counted between departures: the arrival here may come a few ms closer.
    assert len(provider.sent_at) == 3 and all(gap >= 0.38 for gap in gaps)
    for events in (first, tested, second):
        ended = _of(events, "model_call_ended")[0].payload
        assert ended["prompt_ms"] < 350 and ended["duration_ms"] < 350


def test_a_cancel_during_the_wait_sends_nothing():
    from wavestack.models import openai_chat
    from wavestack.models.engine import CancelToken

    _spaced(30)
    provider = Provider(MISTRAL_TEXT)
    entry = config.load_config().cloud_model("mistral")
    engine = provider.factory(entry, SecretStr(SENTINEL))
    seeded = openai_chat._last_start[entry.id] = time.monotonic()  # a send just left
    cancel = CancelToken()
    threading.Timer(0.1, cancel.cancel).start()
    mark = get_journal().last_seq()
    started = time.monotonic()

    call = openai_chat.run_call(
        engine,
        openai_chat.ChatBody(b"{}"),
        cancel,
        phase_label="test",
        estimated_prompt=1,
        chars_per_token=4,
        call_id=lambda i: f"id{i}",
    )

    assert call.stop_reason == "cancelled" and time.monotonic() - started < 5
    assert provider.requests == [] and get_journal().events_since(mark) == []
    assert openai_chat._last_start[entry.id] == seeded  # the slot is given back
    engine.close()
