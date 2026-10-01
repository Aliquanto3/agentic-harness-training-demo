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
from fake_engine import FakeEngine
from pydantic import SecretStr
from starlette.testclient import TestClient

from wavestack import config
from wavestack.context.render import distribute
from wavestack.messages import msg
from wavestack.models import discovery
from wavestack.models.openai_chat import OpenAIChatEngine, _quota_scope
from wavestack.session.app_session import AppSession
from wavestack.session.diagnostic import DiagnosticSession
from wavestack.trace.catalog import ContextReconciledPayload
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
        # Story 23: the headers are traced, the key's value masked before the journal.
        traced = {h["name"]: (h["value"], h["masked"]) for h in out.payload["headers"]}
        assert traced["Authorization"] == ("[masqué]", True)
        assert traced["Content-Type"] == ("application/json", False)
        assert [h["name"] for h in out.payload["headers"]] == [
            n.decode("latin-1") for n, _ in request.headers.raw
        ]
        for piece in (SENTINEL[:4], SENTINEL[-4:]):
            assert piece not in out.model_dump_json()
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
    assert fragment in harness["message_text"] and harness["hints_text"]
    # Story 11b: the provider's own message ends every refusal, masked.
    masked = error.replace(SENTINEL, "•••")
    assert harness["message_text"].endswith(f"Message du fournisseur : {masked}")
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

    assert "Redirection refusée" in _of(events, "harness_error")[0].payload["message_text"]
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
    assert malformed["detail_text"] == f"le fournisseur a refusé l'appel d'outil : {masked}"
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
    assert malformed["detail_text"] == f"le fournisseur a refusé l'appel d'outil : {masked}"
    assert _of(events, "turn_ended")[0].payload["status"] == "completed"
    _no_sentinel(_journal_text())


def test_an_html_page_stays_out_of_the_french_message():
    page = "<html><body>Accès bloqué par le proxy de l'entreprise</body></html>"
    answer = httpx.Response(502, text=page, headers={"content-type": "text/html"})
    session = _cloud_session("groq", Provider(answer))

    harness = _of(_turn(session, "Bonjour"), "harness_error")[0].payload

    assert "Message du fournisseur" not in harness["message_text"]
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

    assert [m.id for m in valid] == ["groq", "gemini", "gemma"]
    assert valid[0].tpm == 6000 and valid[0].model == "openai/gpt-oss-120b"
    assert len(errors) == 1 and "Bad-Id" in errors[0]
    assert "api.groq.com" in cfg.allowed_hosts and "api.mistral.ai" not in cfg.allowed_hosts
    assert "generativelanguage.googleapis.com" in cfg.allowed_hosts
    assert config.cloud_window(valid[0], 4096) == (3000, "tpm")


@pytest.mark.parametrize("name", ["User-Agent", "content-type", " Accept "])
def test_a_key_header_traced_in_clear_is_refused_at_load(name):
    """Story 23: a key under a public header would reach the journal in clear."""
    settings = {"cloud": {"models": [{"id": "groq", "auth_header": {"name": name}}]}}
    config.settings_path().parent.mkdir(parents=True, exist_ok=True)
    config.settings_path().write_text(json.dumps(settings), encoding="utf-8")

    valid, errors = config.load_config().cloud_models

    assert "groq" not in [m.id for m in valid]
    (error,) = [e for e in errors if "groq" in e]
    assert "auth_header.name" in error and "tracé en clair dans le journal" in error


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

    assert set(rows) == {"groq", "mistral", "gemini", "gemma"}
    # The first preset on a free tier only: the diagnostic says « offre d'essai ».
    assert rows["gemma"]["disclosure"]["trial"] is True
    assert rows["gemini"]["disclosure"]["trial"] is False
    for model_id in rows:
        assert rows[model_id]["key_set"] is False and "clé API" in rows[model_id]["disabled_text"]
    response = client.post("/api/intentions/test_cloud_model", json={"id": "groq"}, headers=ORIGIN)
    assert response.status_code == 409


def test_key_saved_for_another_host_must_be_typed_again(monkeypatch):
    config.write_api_key("groq", "old.example", SecretStr(SENTINEL))
    _, _, _, client = _app(monkeypatch)

    row = client.get("/api/diagnostic").json()["cloud"]["models"][0]

    assert row["key_set"] is False
    assert row["disabled_text"] == "Clé à ressaisir : l'adresse du fournisseur a changé."


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
    assert state["active_model"]["hosting"] == "network" and state["active_model"]["warning_text"]
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
    # The diagnostic page opened afterwards reads it from its row, not from the replay.
    rows = {r["id"]: r for r in client.get("/api/diagnostic").json()["cloud"]["models"]}
    assert rows["groq"]["last_test"] == check and rows["mistral"]["last_test"] is None
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
    assert _of(sent, "context_overflow") == [] and rendered["uncertain_text"]
    assert rendered["used"] > rendered["usable"] and not rendered["overflow"]

    blocked = _turn(session, "x" * 12000)  # raw ≈ 3000 > 2464
    overflow = _of(blocked, "context_overflow")[0].payload
    assert overflow["used"] > overflow["usable"] and "≈" in overflow["message_text"]
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

    assert app_session.state == "idle" and app_session.reason_text is None
    assert app_session.active_model()["provider"] == "Groq"
    assert provider.requests == []


def test_a_choice_after_a_model_is_loaded_is_a_hot_switch(monkeypatch, tmp_path):
    """Story 17 (CAP-34): local → cloud → local without relaunch, no request sent; the
    diagnostic's « actif » and « chargé » come from the application session."""
    provider = Provider(GROQ_TEXT)
    session, app_session, _, client = _app(monkeypatch, provider)
    app_session._engine_factory = lambda path, n_ctx: FakeEngine()
    monkeypatch.setattr(session, "_probe_candidate", lambda candidate, cancel=None: None)
    gguf = tmp_path / "local.gguf"
    gguf.write_bytes(b"placeholder")
    app_session.boot(str(gguf)).result()  # a GGUF is loaded
    client.post("/api/intentions/set_api_key", json={"id": "groq", "key": SENTINEL}, headers=ORIGIN)

    body = client.post(
        "/api/intentions/select_model",
        json={"kind": "cloud", "ref": "groq", "acknowledged": True},
        headers=ORIGIN,
    ).json()
    app_session.join()

    assert (
        body["switching"] is True and body["message_text"] == "Chargement de openai/gpt-oss-120b…"
    )
    assert app_session._cloud is not None and app_session.active_model()["ref"] == "groq"
    assert config.read_settings()["selected_model"] == {"kind": "cloud", "ref": "groq"}
    assert _row(client)["loaded"] is True and _row(client)["selected"] is True
    assert "next_launch_text" not in client.get("/api/diagnostic").json()

    body = client.post(
        "/api/intentions/select_model", json={"kind": "file", "ref": str(gguf)}, headers=ORIGIN
    ).json()
    app_session.join()

    assert body["switching"] is True and app_session.active_model()["kind"] == "file"
    assert config.read_settings()["selected_model"] == {"kind": "file", "ref": str(gguf)}
    assert _row(client)["loaded"] is False
    assert client.get("/api/diagnostic").json()["loaded_model"] == str(gguf)
    assert provider.requests == []


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
    assert (
        "n'est plus utilisable" in [c for c in checks if c["check"] == "model"][-1]["message_text"]
    )


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

    assert row["key_set"] is True and row["disabled_text"] is None
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
    assert "clé API" in row["disabled_text"]
    response = client.post("/api/intentions/test_cloud_model", json={"id": "groq"}, headers=ORIGIN)
    assert response.status_code == 409


def test_a_key_for_another_host_gives_way_to_the_variable(monkeypatch):
    config.write_api_key("groq", "old.example", SecretStr("old-key-0123456789"))
    monkeypatch.setenv("GROQ_API_KEY", SENTINEL)
    _, _, _, client = _app(monkeypatch)

    row = _row(client)

    assert row["key_set"] is True and row["key_source"] == "env" and row["disabled_text"] is None
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

    assert harness["message_text"].endswith("Message du fournisseur : Invalid API Key")


def test_a_long_provider_message_is_cut_at_500_characters():
    answer = httpx.Response(503, text="x" * 800)
    session = _cloud_session("groq", Provider(answer))

    harness = _of(_turn(session, "Bonjour"), "harness_error")[0].payload

    assert harness["message_text"].endswith("Message du fournisseur : " + "x" * 500 + "…")


def test_an_error_in_the_stream_carries_the_provider_message():
    stream = sse({"error": {"message": "Internal overload"}})
    session = _cloud_session("groq", Provider(stream))

    harness = _of(_turn(session, "Bonjour"), "harness_error")[0].payload

    assert harness["message_text"].endswith("Message du fournisseur : Internal overload")


def test_per_second_quota_names_the_second_and_the_spacing():
    answer = httpx.Response(
        429, json={"message": "Requests rate limit exceeded per second", "type": "rate_limited"}
    )
    session = _cloud_session("mistral", Provider(answer))

    harness = _of(_turn(session, "Bonjour"), "harness_error")[0].payload

    assert harness["quota_scope"] == "second"
    assert "quota dépassé par seconde" in harness["message_text"]
    assert any("min_interval_s" in hint for hint in harness["hints_text"])


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
    assert "quota dépassé (par seconde, par minute ou par jour)" in harness["message_text"]
    assert not any("min_interval_s" in hint for hint in harness["hints_text"])


# D6 (2026-10-01): Mistral's answer to a workspace without any active quota (probe of
# 2026-09-26 on the target PC).
_NO_QUOTA_BODY = {"message": "Rate limit exceeded", "type": "rate_limited", "code": "1300"}
_NO_QUOTA_HEADERS = {
    "x-ratelimit-limit-req-minute": "0",
    "x-ratelimit-remaining-req-minute": "0",
    "retry-after": "60",
}


def test_a_429_without_any_quota_says_so_and_asks_no_wait():
    provider = Provider(httpx.Response(429, json=_NO_QUOTA_BODY, headers=_NO_QUOTA_HEADERS))
    session = _cloud_session("mistral", provider)

    harness = _of(_turn(session, "Bonjour"), "harness_error")[0].payload

    assert harness["message_text"].startswith(
        "Mistral AI refuse l'appel. Aucun quota actif sur ce compte : vérifiez le plan dans la "
        "console du fournisseur."
    )
    assert harness["message_text"].endswith("Message du fournisseur : Rate limit exceeded")
    hints = " ".join(harness["hints_text"])
    assert "Attendez" not in hints and "min_interval_s" not in hints  # neither wait nor spacing
    assert "Revenez au modèle local" in hints
    assert harness["http_status"] == 429
    assert harness["retry_after_s"] is None and harness["quota_scope"] is None
    assert len(provider.requests) == 1  # never retried


def test_a_429_with_a_quota_keeps_the_quota_message():
    headers = {**_NO_QUOTA_HEADERS, "x-ratelimit-limit-req-minute": "60"}
    answer = httpx.Response(429, json=_NO_QUOTA_BODY, headers=headers)
    session = _cloud_session("mistral", Provider(answer))

    harness = _of(_turn(session, "Bonjour"), "harness_error")[0].payload

    assert "aucun quota actif" not in harness["message_text"]
    assert "quota dépassé" in harness["message_text"] and harness["retry_after_s"] == 60


@pytest.mark.parametrize(
    ("lang", "said"),
    [
        ("en", "No active quota on this account: check the plan in the provider's console"),
        ("de", "Kein aktives Kontingent auf diesem Konto: Prüfen Sie den Tarif in der Konsole"),
    ],
)
def test_a_429_without_any_quota_in_english_and_german(lang, said):
    assert said in msg("models.openai_chat.no_quota", lang, provider="Mistral")


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


# ---------- story 32: sections and « déjà lu » in chat mode ----------


def test_chat_second_call_reads_the_first_one_again_and_reconciled_keeps_it():
    provider = Provider(GROQ_TOOL, GROQ_TEXT)
    session = _cloud_session("groq", provider, bricks=("tools",))

    events = _turn(session, "Quelle heure est-il ?")

    first, second = (e.payload for e in _of(events, "context_rendered"))
    assert first["seen_segments"] == 0 and not any(s["seen"] for s in first["sections"])
    assert second["seen_segments"] > 0
    assert any(s["kind"] == "tool_result" and not s["seen"] for s in second["sections"])
    for rendered, reconciled in zip(
        _of(events, "context_rendered"), _of(events, "context_reconciled"), strict=True
    ):
        r, c = rendered.payload, reconciled.payload
        assert c["seen_segments"] == r["seen_segments"]
        cuts = [(s["start"], s["end"], s["kind"], s["seen"]) for s in r["sections"]]
        assert [(s["start"], s["end"], s["kind"], s["seen"]) for s in c["sections"]] == cuts
        assert sum(s["tokens"] for s in c["sections"]) == c["used"]  # recalibrated tokens
        assert c["seen_tokens"] == sum(s["tokens"] for s in c["segments"][: c["seen_segments"]])
        assert "".join(s["text"] for s in r["segments"]) == r["body"]
    for reconciled in _of(events, "context_reconciled"):  # the catalogue's shape (AD-2)
        checked = ContextReconciledPayload.model_validate(reconciled.payload)
        assert checked.sections and checked.seen_segments == reconciled.payload["seen_segments"]
    provider_section = second["sections"][-1]
    assert provider_section["end"] - provider_section["start"] == 1
    assert provider_section["label_text"] == second["segments"][-1]["label_text"]


# ---------- Gemini (Google AI Studio): thought signatures and tagged reasoning ----------

# The shapes the real `gemini-3.5-flash-lite` streamed (probe of 2026-09-29): the tool call
# in one chunk, without `index`, then `{"role": "assistant"}` with `finish_reason: "stop"`; a
# text answer ending on a delta that holds a signature and no content; `usage` on every chunk,
# cumulative, `completion_tokens` without the thinking tokens that `total_tokens` includes.
SIGNATURE = {"google": {"thought_signature": "c2lnbmF0dXJlLWUyZS0x"}}


def gemini_usage(prompt: int, completion: int, thinking: int = 0) -> dict:
    total = prompt + completion + thinking
    return {"prompt_tokens": prompt, "completion_tokens": completion, "total_tokens": total}


def gemini_delta(finish=None, usage=None, **fields) -> dict:
    chunk = delta(finish, role="assistant", **fields)
    return chunk | ({"usage": usage} if usage else {})


GEMINI_TOOL = sse(
    gemini_delta(
        usage=gemini_usage(300, 8),
        tool_calls=[
            {
                "extra_content": SIGNATURE,
                "function": {"arguments": "{}", "name": "get_datetime"},
                "id": "call_91152",
                "type": "function",
            }
        ],
    ),
    gemini_delta("stop", usage=gemini_usage(300, 8)),
)
GEMINI_TEXT = sse(
    gemini_delta(content="Il est 9 h.", usage=gemini_usage(340, 5)),
    gemini_delta(
        "stop",
        usage=gemini_usage(340, 5),
        extra_content={"google": {"thought_signature": "c2lnLWZpbg=="}},
    ),
)
MISSING_SIGNATURE = (
    "Function call is missing a thought_signature in functionCall parts. This is required for "
    "tools to work correctly, and missing thought_signature may lead to degraded model "
    "performance. Additional data, function call `default_api:get_datetime` , position 2. "
    "Please refer to https://ai.google.dev/gemini-api/docs/thought-signatures for more details."
)


class GeminiProvider(Provider):
    """As Gemini 3.x: an assistant message replayed without the `thought_signature` of its
    first call is a 400 (Gemini signs only the first call of a parallel set; its host only:
    another provider's requests pass as they are)."""

    def __call__(self, request: httpx.Request) -> httpx.Response:
        body = json.loads(request.content)
        gemini = request.url.host == "generativelanguage.googleapis.com"
        for message in body["messages"] if gemini else []:
            for call in (message.get("tool_calls") or [])[:1]:
                google = (call.get("extra_content") or {}).get("google") or {}
                if not google.get("thought_signature"):
                    self.requests.append(request)
                    error = {"code": 400, "message": MISSING_SIGNATURE}
                    error["status"] = "INVALID_ARGUMENT"
                    return httpx.Response(400, json=[{"error": error}])  # an array, as Gemini
        return super().__call__(request)


def test_gemini_replays_the_thought_signature_with_reasoning_off(caplog):
    caplog.set_level(logging.DEBUG)
    provider = GeminiProvider(GEMINI_TOOL, GEMINI_TEXT)
    session = _cloud_session("gemini", provider, bricks=("tools",))

    events = _turn(session, "Quelle heure est-il ?")

    assert _of(events, "turn_ended")[0].payload["status"] == "completed"
    assert _of(events, "harness_error") == [] and len(provider.requests) == 2
    first = json.loads(provider.requests[0].content)
    assert first["model"] == "gemini-3.5-flash-lite" and first["max_tokens"] == 512
    assert first["reasoning_effort"] == "minimal" and "extra_body" not in first
    assert first["stream_options"] == {"include_usage": True}
    assert provider.requests[0].url.host == "generativelanguage.googleapis.com"
    assert provider.requests[0].headers["authorization"] == f"Bearer {SENTINEL}"
    second = json.loads(provider.requests[1].content)
    assistant = next(m for m in second["messages"] if m.get("tool_calls"))
    assert assistant["tool_calls"][0]["extra_content"] == SIGNATURE
    # The trace carries it too, for the acceptance run to check.
    ended = _of(events, "model_call_ended")[0].payload
    assert ended["tool_calls"][0]["extra_content"] == SIGNATURE
    assert "thought_signature" in ended["raw_output"]
    # AD-5: the body sent is the one rendered and traced, its segments cover it all.
    for ctx, request in zip(_of(events, "context_rendered"), provider.requests, strict=True):
        assert request.content == ctx.payload["body"].encode("utf-8")
        assert "".join(s["text"] for s in ctx.payload["segments"]) == ctx.payload["body"]
    _no_sentinel(_journal_text(), caplog.text)


def test_the_gemma_entry_is_the_free_open_model_on_the_gemini_host():
    """Lot 1 of 2026-09-30: Gemma 4 shares Gemini's host, key and signature workaround; free
    tier only (trial, no price); `training = "no"` by the EEA clause (terms of 2026-09-30)."""
    cfg = config.load_config()
    gemma, gemini = cfg.cloud_model("gemma"), cfg.cloud_model("gemini")

    assert gemma.model == "gemma-4-26b-a4b-it" and gemma.host == gemini.host
    assert gemma.key_env == gemini.key_env == "GEMINI_API_KEY"
    assert gemma.tool_call_extra == gemini.tool_call_extra
    assert gemma.trial and gemma.training == "no" and gemma.pricing is None
    assert gemma.impacts is not None and gemma.impacts.model == "gemma-4-26b-a4b-it"
    assert gemma.context == 262144 and gemma.tools and gemma.stream_usage
    assert "offre gratuite" in gemma.notes_text and "EEE" in gemma.notes_text
    assert "usage personnel" in gemma.notes_text and "GEMINI_API_KEY" in gemma.notes_text
    # Gemini keeps « obligatoire »: Google reserves paid services to API clients in the EEA.
    assert "obligatoire" in gemini.notes_text and "EEE" in gemini.notes_text
    assert gemma.reasoning is not None and not gemma.reasoning.always
    assert gemma.reasoning.tags == ("<thought>", "</thought>")
    thinking = {"google": {"thinking_config": {"include_thoughts": True}}}
    assert gemma.reasoning.on == {"extra_body": thinking}
    assert gemma.reasoning.off == {"reasoning_effort": "minimal"}


def test_gemma_reasoning_on_only_asks_to_see_the_thoughts_and_replays_the_signature():
    """Gemma 4 refuses `thinking_level`, `thinking_budget` and every `reasoning_effort` but
    `minimal` (probe of 2026-09-30): brick on, the body carries `include_thoughts` alone. Its
    tool calls are signed as Gemini's, and replayed the same way."""
    provider = GeminiProvider(GEMINI_TOOL, GEMINI_TEXT)
    session = _cloud_session("gemma", provider, bricks=("tools", "reasoning"))

    events = _turn(session, "Quelle heure est-il ?")

    assert _of(events, "turn_ended")[0].payload["status"] == "completed"
    assert _of(events, "harness_error") == [] and len(provider.requests) == 2
    first = json.loads(provider.requests[0].content)
    assert first["model"] == "gemma-4-26b-a4b-it" and first["max_tokens"] == 1536
    assert first["extra_body"] == {"google": {"thinking_config": {"include_thoughts": True}}}
    assert "reasoning_effort" not in first
    assert "thinking_level" not in json.dumps(first) and "thinking_budget" not in json.dumps(first)
    assert provider.requests[0].url.host == "generativelanguage.googleapis.com"
    second = json.loads(provider.requests[1].content)
    assistant = next(m for m in second["messages"] if m.get("tool_calls"))
    assert assistant["tool_calls"][0]["extra_content"] == SIGNATURE


def test_gemma_reasoning_off_sends_minimal_and_no_extra_body():
    """The nominal case: `minimal` is what stops Gemma 4 from thinking by default."""
    provider = GeminiProvider(GEMINI_TOOL, GEMINI_TEXT)
    session = _cloud_session("gemma", provider, bricks=("tools",))

    events = _turn(session, "Quelle heure est-il ?")

    assert _of(events, "turn_ended")[0].payload["status"] == "completed"
    assert len(provider.requests) == 2
    first = json.loads(provider.requests[0].content)
    assert first["model"] == "gemma-4-26b-a4b-it" and first["max_tokens"] == 512
    assert first["reasoning_effort"] == "minimal" and "extra_body" not in first
    second = json.loads(provider.requests[1].content)
    assistant = next(m for m in second["messages"] if m.get("tool_calls"))
    assert assistant["tool_calls"][0]["extra_content"] == SIGNATURE


def test_without_the_signature_the_fake_gemini_refuses():
    """The fake provider itself: the matrix's « sans signature, 400 » holds."""
    groq_shaped = sse(
        delta(
            tool_calls=[
                {
                    "index": 0,
                    "id": "c1",
                    "function": {"name": "get_datetime", "arguments": "{}"},
                }
            ]
        ),
        delta("tool_calls"),
    )
    provider = GeminiProvider(groq_shaped, GEMINI_TEXT)
    session = _cloud_session("gemini", provider, bricks=("tools",))

    events = _turn(session, "Quelle heure est-il ?")

    assert _of(events, "turn_ended")[0].payload["status"] == "error"
    harness = _of(events, "harness_error")[0].payload
    assert harness["http_status"] == 400
    # Gemini's error body is an array: its own message still ends the French one.
    assert harness["message_text"].startswith("Requête refusée par Google AI Studio (400)")
    assert harness["message_text"].endswith(f"Message du fournisseur : {MISSING_SIGNATURE}")


def test_gemini_reasoning_on_reads_the_thought_tags():
    marked = {"google": {"thought": True}}
    stream = sse(
        gemini_delta(content="<thought>Je réfl", extra_content=marked, usage=gemini_usage(40, 0)),
        gemini_delta(content="échis.", extra_content=marked, usage=gemini_usage(40, 0)),
        gemini_delta(content="</thought>Bon", usage=gemini_usage(40, 1, 986)),
        gemini_delta(content="jour.", usage=gemini_usage(40, 2, 986)),
        gemini_delta(
            "stop", usage=gemini_usage(40, 2, 986), extra_content={"google": SIGNATURE["google"]}
        ),
    )
    provider = Provider(stream)
    session = _cloud_session("gemini", provider, bricks=("reasoning",))

    events = _turn(session, "Bonjour")

    body = json.loads(provider.requests[0].content)
    assert body["extra_body"] == {
        "google": {"thinking_config": {"thinking_level": "medium", "include_thoughts": True}}
    }
    assert "reasoning_effort" not in body and body["max_tokens"] == 1536
    ended = _of(events, "model_call_ended")[0].payload
    assert ended["reasoning"] == "Je réfléchis." and ended["text"] == "Bonjour."
    channels = {d.payload["channel"] for d in _of(events, "model_delta")}
    assert channels == {"reasoning", "text"}
    # The thinking tokens count: `total − prompt`, not `completion_tokens` alone.
    assert ended["output_tokens"] == 988 and ended["stop_reason"] == "stop"


def test_gemini_thought_marked_apart_goes_to_the_reasoning_channel():
    """Without `think_tags` (a fallback of settings.json), the mark alone decides."""
    settings = {"cloud": {"models": [{"id": "gemini", "reasoning": {"format": "field"}}]}}
    config.settings_path().parent.mkdir(parents=True, exist_ok=True)
    config.settings_path().write_text(json.dumps(settings), encoding="utf-8")
    thought = {"google": {"thought": True}}
    stream = sse(
        gemini_delta(content="Pensée.", extra_content=thought),
        gemini_delta(content="Réponse."),
        gemini_delta("stop"),
    )
    session = _cloud_session("gemini", Provider(stream))

    ended = _of(_turn(session, "Bonjour"), "model_call_ended")[0].payload

    assert ended["reasoning"] == "Pensée." and ended["text"] == "Réponse."


@pytest.mark.parametrize(
    ("usage", "expected"),
    [
        ({"prompt_tokens": 65, "completion_tokens": 14, "total_tokens": 1065}, 1000),  # Gemini
        ({"prompt_tokens": 700, "completion_tokens": 12, "total_tokens": 712}, 12),  # Groq
        ({"prompt_tokens": 40, "completion_tokens": 3}, 3),  # no total
        ({}, 0),  # unknown: the caller estimates
    ],
)
def test_output_tokens_count_the_hidden_thinking(usage, expected):
    from wavestack.models.openai_chat import output_tokens

    assert output_tokens(usage) == expected


def test_the_signature_never_reaches_another_provider():
    provider = GeminiProvider(GEMINI_TOOL, GEMINI_TEXT, GROQ_TEXT)
    session = _cloud_session("gemini", provider, bricks=("tools", "short_memory"))
    _turn(session, "Quelle heure est-il ?")
    groq = session.cfg.cloud_model("groq")
    config.write_api_key(groq.id, groq.host, SecretStr(SENTINEL))
    session.boot_cloud(groq).result()
    session.join()

    events = _turn(session, "Et demain ?")

    assert _of(events, "turn_ended")[0].payload["status"] == "completed"
    sent = provider.requests[-1]
    assert sent.url.host == "api.groq.com" and b'"tool_calls"' in sent.content
    assert b"extra_content" not in sent.content and b"thought_signature" not in sent.content


def test_a_forced_action_on_gemini_carries_tool_call_extra_and_no_other_entry_does():
    for model_id, expected in (
        ("gemini", {"google": {"thought_signature": "skip_thought_signature_validator"}}),
        ("groq", None),
        ("mistral", None),
    ):
        provider = GeminiProvider(GEMINI_TEXT) if model_id == "gemini" else Provider(GROQ_TEXT)
        session = _cloud_session(model_id, provider, bricks=("tools",))
        session.arm("tool", "get_datetime", {})

        events = _turn(session, "Quelle heure est-il ?")

        assert _of(events, "turn_ended")[0].payload["status"] == "completed", model_id
        messages = json.loads(provider.requests[0].content)["messages"]
        call = next(m for m in messages if m.get("tool_calls"))["tool_calls"][0]
        assert call.get("extra_content") == expected, model_id
        extra = {"extra_content"} if expected else set()
        assert set(call) == {"id", "type", "function"} | extra, model_id


def test_gemini_test_replays_the_signature_of_the_first_call(monkeypatch, caplog):
    caplog.set_level(logging.DEBUG)
    provider = GeminiProvider(GEMINI_TOOL, GEMINI_TEXT)
    _, _, _, client = _app(monkeypatch, provider)
    client.post(
        "/api/intentions/set_api_key", json={"id": "gemini", "key": SENTINEL}, headers=ORIGIN
    )

    response = client.post(
        "/api/intentions/test_cloud_model", json={"id": "gemini"}, headers=ORIGIN
    )

    assert response.status_code == 200 and response.json()["ok"] is True
    assert len(provider.requests) == 2
    second = json.loads(provider.requests[1].content)
    assistant = next(m for m in second["messages"] if m.get("tool_calls"))
    assert assistant["tool_calls"][0]["extra_content"] == SIGNATURE
    _no_sentinel(_journal_text(), caplog.text, response.text, client.get("/api/diagnostic").text)


def test_gemini_key_from_its_variable_makes_it_choosable(monkeypatch):
    monkeypatch.setenv("GEMINI_API_KEY", SENTINEL)
    _, _, _, client = _app(monkeypatch)

    row = _row(client, "gemini")

    assert row["key_set"] is True and row["disabled_text"] is None
    assert row["key_source"] == "env" and row["key_env"] == "GEMINI_API_KEY"
    assert "generativelanguage.googleapis.com" in config.load_config().allowed_hosts
    _no_sentinel(client.get("/api/diagnostic").text)


def test_gemini_fallbacks_come_from_settings_without_code():
    """A null removes a field the preset declares: the fallback `reasoning_effort` alone."""
    settings = {
        "cloud": {
            "models": [
                {
                    "id": "gemini",
                    "model": "gemini-3.6-flash",
                    "reasoning": {
                        "tags": ["<thinking>", "</thinking>"],
                        "on": {"extra_body": None, "reasoning_effort": "low"},
                    },
                }
            ]
        }
    }
    config.settings_path().parent.mkdir(parents=True, exist_ok=True)
    config.settings_path().write_text(json.dumps(settings), encoding="utf-8")

    entry = config.load_config().cloud_model("gemini")

    assert entry.model == "gemini-3.6-flash"
    assert entry.reasoning_params(True) == {"reasoning_effort": "low"}
    assert entry.reasoning_params(False) == {"reasoning_effort": "minimal"}
    assert entry.reasoning.tags == ("<thinking>", "</thinking>")
    with pytest.raises(ValueError):
        config.CloudReasoning.model_validate({"format": "think_tags", "tags": ["", "</x>"]})


def test_the_signature_goes_back_as_received_and_is_masked_in_the_trace():
    """A signature is opaque: masked, it would be refused. It goes back byte for byte to the
    provider that emitted it; `model_call_ended` masks it like any provider string."""
    raw = f"sig{SENTINEL[:4]}tail"
    stream = GEMINI_TOOL.replace(b"c2lnbmF0dXJlLWUyZS0x", raw.encode())
    provider = GeminiProvider(stream, GEMINI_TEXT)
    session = _cloud_session("gemini", provider, bricks=("tools",))

    events = _turn(session, "Quelle heure est-il ?")

    traced = _of(events, "model_call_ended")[0].payload["tool_calls"][0]["extra_content"]
    assert traced == {"google": {"thought_signature": "sig•••tail"}}
    second = json.loads(provider.requests[1].content)
    assistant = next(m for m in second["messages"] if m.get("tool_calls"))
    assert assistant["tool_calls"][0]["extra_content"]["google"]["thought_signature"] == raw


def gemini_call(name: str, arguments: str, call_id: str, signature: str) -> bytes:
    """A Gemini tool call as the real API streams it: one chunk, no `index`, then « stop »."""
    call = {
        "extra_content": {"google": {"thought_signature": signature}},
        "function": {"arguments": arguments, "name": name},
        "id": call_id,
        "type": "function",
    }
    return sse(gemini_delta(tool_calls=[call]), gemini_delta("stop"))


def test_calls_without_index_keep_their_arrival_order():
    """Gemini sends no `index`: calls keyed by `id` stay in arrival order, never sorted."""
    from wavestack.models.engine import CancelToken
    from wavestack.models.openai_chat import ChatBody, ChatEnd

    calls = [
        {"id": call_id, "type": "function", "function": {"name": name, "arguments": "{}"}}
        for call_id, name in (("call_99999", "get_datetime"), ("call_100002", "calculator"))
    ]
    stream = sse(gemini_delta(tool_calls=calls), gemini_delta("stop"))
    entry = config.load_config().cloud_model("gemini")
    engine = Provider(stream).factory(entry, SecretStr(SENTINEL))

    end = list(engine.complete(ChatBody(b"{}"), CancelToken()))[-1]

    assert isinstance(end, ChatEnd)
    assert [c["provider_id"] for c in end.tool_calls] == ["call_99999", "call_100002"]
    engine.close()


def _tool_calls_of(*fragments: dict) -> list[dict]:
    """The calls `openai_chat` reads from one streamed answer, a fragment per chunk."""
    from wavestack.models.engine import CancelToken
    from wavestack.models.openai_chat import ChatBody, ChatEnd

    stream = sse(*(delta(tool_calls=[f]) for f in fragments), delta("tool_calls"))
    entry = config.load_config().cloud_model("groq")
    engine = Provider(stream).factory(entry, SecretStr(SENTINEL))
    end = list(engine.complete(ChatBody(b"{}"), CancelToken()))[-1]
    engine.close()
    assert isinstance(end, ChatEnd)
    return end.tool_calls


def test_two_parallel_calls_under_one_index_stay_two_calls():
    """E048: a provider that sends two calls under the same `index` (or none), each with its
    own `id`: two calls, never one with the names glued together."""
    first = {"index": 0, "id": "call_a", "function": {"name": "get_datetime", "arguments": "{}"}}
    second = {"index": 0, "id": "call_b", "function": {"name": "calculator", "arguments": ""}}
    rest = {"index": 0, "function": {"arguments": '{"expression": "2+2"}'}}

    calls = _tool_calls_of(first, second, rest)

    assert [(c["provider_id"], c["name"]) for c in calls] == [
        ("call_a", "get_datetime"),
        ("call_b", "calculator"),
    ]
    assert [c["arguments"] for c in calls] == ["{}", '{"expression": "2+2"}']
    no_index = [{k: v for k, v in f.items() if k != "index"} for f in (first, second)]
    assert [c["name"] for c in _tool_calls_of(*no_index)] == ["get_datetime", "calculator"]


def test_fragments_of_one_call_stay_one_call():
    """E048: the fragments that follow a call's first one (same `index`, no `id`, the same
    `id` again, or a fresh `id` without a name) extend it: one call, its arguments put
    together."""
    head = {"index": 0, "id": "call_a", "function": {"name": "calculator", "arguments": '{"ex'}}
    tail = {"index": 0, "function": {"arguments": 'pression": '}}
    again = {"index": 0, "id": "call_a", "function": {"arguments": '"1'}}
    fresh = {"index": 0, "id": "delta_3", "function": {"arguments": '+1"}'}}
    other = {"index": 1, "id": "call_b", "function": {"name": "get_datetime", "arguments": "{}"}}

    calls = _tool_calls_of(head, tail, again, fresh, other)

    assert [(c["name"], c["arguments"]) for c in calls] == [
        ("calculator", '{"expression": "1+1"}'),
        ("get_datetime", "{}"),
    ]
    assert calls[1]["provider_id"] == "call_b"


def test_a_sub_agent_on_gemini_replays_its_own_signature():
    """The sub-agent's context (`_sub_messages`) sends its call back signed, as the main one."""
    provider = GeminiProvider(
        gemini_call("delegate", '{"task": "Lis notes_reunion.txt."}', "p1", "sig-principal"),
        gemini_call("read_file", '{"path": "notes_reunion.txt"}', "p2", "sig-sous-agent"),
        GEMINI_TEXT,
        GEMINI_TEXT,
    )
    session = _cloud_session("gemini", provider, bricks=("tools", "subagent"))

    events = _turn(session, "Quelles décisions ?")

    assert _of(events, "turn_ended")[0].payload["status"] == "completed"
    assert _of(events, "harness_error") == [] and len(provider.requests) == 4
    sub_second = json.loads(provider.requests[2].content)
    assert sub_second["messages"][0]["content"].startswith("Tu es un sous-agent")
    (assistant,) = [m for m in sub_second["messages"] if m.get("tool_calls")]
    signed = assistant["tool_calls"][0]["extra_content"]["google"]["thought_signature"]
    assert signed == "sig-sous-agent"
    main_second = json.loads(provider.requests[3].content)
    (assistant,) = [m for m in main_second["messages"] if m.get("tool_calls")]
    signed = assistant["tool_calls"][0]["extra_content"]["google"]["thought_signature"]
    assert signed == "sig-principal"


def test_a_second_gemini_turn_sends_the_earlier_call_back_signed():
    """Short memory: the earlier turn's call goes back to Gemini with its `extra_content`."""
    provider = GeminiProvider(GEMINI_TOOL, GEMINI_TEXT, GEMINI_TEXT)
    session = _cloud_session("gemini", provider, bricks=("tools", "short_memory"))
    _turn(session, "Quelle heure est-il ?")

    events = _turn(session, "Et demain ?")

    assert _of(events, "turn_ended")[0].payload["status"] == "completed"
    assert _of(events, "harness_error") == [] and len(provider.requests) == 3
    later = json.loads(provider.requests[2].content)
    (assistant,) = [m for m in later["messages"] if m.get("tool_calls")]
    assert assistant["tool_calls"][0]["extra_content"] == SIGNATURE


# ---------- FinOps: the estimated cost of each cloud call, the turn and the session ----------

GEMINI_IN, GEMINI_OUT = 0.30, 2.50  # the preset's `pricing`, dollars per million tokens


def _cost(payload: dict) -> tuple:
    return payload.get("cost_in_usd"), payload.get("cost_out_usd"), payload.get("cost_source")


def _spent() -> dict | None:
    from wavestack.models import openai_chat

    return openai_chat.session_spend(0.86)


def test_a_gemini_call_costs_its_prompt_and_every_output_token():
    """65 prompt tokens, `total_tokens` 1 065, `completion_tokens` 14: the output billed is
    1 000 tokens, the thinking tokens included (total − prompt)."""
    from wavestack.trace.catalog import ConsumptionUpdatedPayload, ModelCallEndedPayload

    usage = gemini_usage(65, 14, 986)
    stream = sse(gemini_delta(content="Bonjour.", usage=usage), gemini_delta("stop", usage=usage))
    session = _cloud_session("gemini", GeminiProvider(stream))

    events = _turn(session, "Bonjour")

    (ended,) = (e.payload for e in _of(events, "model_call_ended"))
    assert ended["prompt_tokens"] == 65 and ended["output_tokens"] == 1000
    cost_in, cost_out = 65 * GEMINI_IN / 1e6, 1000 * GEMINI_OUT / 1e6
    assert _cost(ended) == (pytest.approx(cost_in), pytest.approx(cost_out), "api")
    ModelCallEndedPayload.model_validate(ended)
    (spend,) = (e.payload for e in _of(events, "consumption_updated"))
    ConsumptionUpdatedPayload.model_validate(spend)
    assert spend["total_in_usd"] == pytest.approx(cost_in)
    assert spend["total_out_usd"] == pytest.approx(cost_out)
    assert spend["calls"] == 1 and spend["approx"] is False
    assert spend["eur_per_usd"] == 0.86
    assert spend["total_eur"] == pytest.approx((cost_in + cost_out) * 0.86)
    (turn_ended,) = (e.payload for e in _of(events, "turn_ended"))
    assert _cost(turn_ended) == (pytest.approx(cost_in), pytest.approx(cost_out), "api")


def test_a_call_without_usage_has_an_estimated_cost():
    """Mistral (`stream_usage = false`): the cost follows the estimated tokens, « ≈ »."""
    session = _cloud_session("mistral", Provider(sse(delta(content="Oui."), delta("stop"))))

    events = _turn(session, "Bonjour")

    (ended,) = (e.payload for e in _of(events, "model_call_ended"))
    assert ended["usage_source"] == "estimate" and ended["cost_source"] == "estimate"
    assert ended["cost_in_usd"] == pytest.approx(ended["prompt_tokens"] * 0.15 / 1e6)
    assert ended["cost_out_usd"] == pytest.approx(ended["output_tokens"] * 0.60 / 1e6)
    (spend,) = (e.payload for e in _of(events, "consumption_updated"))
    assert spend["approx"] is True
    assert _of(events, "turn_ended")[0].payload["cost_source"] == "estimate"


def test_an_entry_without_pricing_has_no_cost_and_leaves_the_total_alone():
    # GreenOps: without `impacts` either, nothing reaches the session's registry.
    settings = {"cloud": {"models": [{"id": "groq", "pricing": None, "impacts": None}]}}
    config.settings_path().parent.mkdir(parents=True, exist_ok=True)
    config.settings_path().write_text(json.dumps(settings), encoding="utf-8")
    session = _cloud_session("groq", Provider(GROQ_TEXT))

    events = _turn(session, "Bonjour")

    (ended,) = (e.payload for e in _of(events, "model_call_ended"))
    assert "cost_in_usd" not in ended and "cost_source" not in ended
    assert _of(events, "consumption_updated") == [] and _spent() is None
    assert "cost_in_usd" not in _of(events, "turn_ended")[0].payload
    assert session.consumption() is None


def test_the_turn_sums_every_call_the_sub_agent_included():
    provider = GeminiProvider(
        gemini_call("delegate", '{"task": "Lis notes_reunion.txt."}', "p1", "sig-principal"),
        gemini_call("read_file", '{"path": "notes_reunion.txt"}', "p2", "sig-sous-agent"),
        GEMINI_TEXT,
        GEMINI_TEXT,
    )
    session = _cloud_session("gemini", provider, bricks=("tools", "subagent"))

    events = _turn(session, "Quelles décisions ?")

    calls = _of(events, "model_call_ended")
    assert len(calls) == 4 and any((c.context_id or "").startswith("sub") for c in calls)
    assert all(c.payload["cost_in_usd"] is not None for c in calls)
    turn_ended = _of(events, "turn_ended")[0].payload
    total_in = sum(c.payload["cost_in_usd"] for c in calls)
    total_out = sum(c.payload["cost_out_usd"] for c in calls)
    assert turn_ended["cost_in_usd"] == pytest.approx(total_in)
    assert turn_ended["cost_out_usd"] == pytest.approx(total_out)
    # The session's total follows each call, in order.
    spends = [e.payload for e in _of(events, "consumption_updated")]
    assert [s["calls"] for s in spends] == [1, 2, 3, 4]
    assert spends[-1]["total_in_usd"] == pytest.approx(total_in)


def test_tester_counts_in_the_session_total_and_the_state_gives_it(monkeypatch):
    provider = GeminiProvider(GEMINI_TOOL, GEMINI_TEXT)
    _, _, _, client = _app(monkeypatch, provider)
    client.post(
        "/api/intentions/set_api_key", json={"id": "gemini", "key": SENTINEL}, headers=ORIGIN
    )
    assert client.get("/api/state").json()["consumption_updated"] is None
    mark = get_journal().last_seq()

    client.post("/api/intentions/test_cloud_model", json={"id": "gemini"}, headers=ORIGIN)

    spends = [e for e in get_journal().events_since(mark) if e.kind == "consumption_updated"]
    assert [s.payload["calls"] for s in spends] == [1, 2]
    assert all(s.context_id == "diag" for s in spends)
    assert client.get("/api/state").json()["consumption_updated"] == spends[-1].payload
    row = _row(client, "gemini")
    assert row["price_text"].startswith("Prix : 0,30 $ / 2,50 $ par million de tokens")
    assert row["price_text"].endswith(
        "relevé le 29/09/2026 ; le coût de chaque appel en est une estimation"
    )


def test_the_llm_screen_counts_in_the_session_total():
    from wavestack.models.engine import Sampling

    session = _cloud_session("gemini", GeminiProvider(GEMINI_TEXT))
    mark = get_journal().last_seq()

    session.llm_generate("Bonjour", Sampling(temperature=0.2, top_k=5, top_p=0.9, min_p=0.05))
    session.join()

    (spend,) = [e for e in get_journal().events_since(mark) if e.kind == "consumption_updated"]
    assert spend.context_id == "llm" and spend.payload["calls"] == 1
    assert session.consumption() == spend.payload


def test_neither_clearing_nor_resetting_gives_the_money_back():
    session = _cloud_session("gemini", GeminiProvider(GEMINI_TEXT))
    _turn(session, "Bonjour")
    before = session.consumption()
    assert before is not None and before["calls"] == 1

    session.clear_conversation()
    session.join()
    session.reset()
    session.join()

    assert session.consumption() == before
    events = _turn(session, "Encore")
    assert _of(events, "consumption_updated")[0].payload["calls"] == 2


def test_a_refused_call_costs_nothing():
    """A provider's refusal before any output (here a 401) is not billed."""
    provider = Provider(httpx.Response(401, json={"error": {"message": "Invalid API Key"}}))
    session = _cloud_session("gemini", provider)

    events = _turn(session, "Bonjour")

    (ended,) = (e.payload for e in _of(events, "model_call_ended"))
    assert ended["stop_reason"] == "error" and "cost_in_usd" not in ended
    assert _of(events, "consumption_updated") == [] and session.consumption() is None


def test_a_negative_price_leaves_the_entry_out_with_the_reason():
    pricing = {"input_usd_per_mtok": -1, "output_usd_per_mtok": 2.5, "checked": "2026-09-29"}
    settings = {"cloud": {"models": [{"id": "gemini", "pricing": pricing}]}}
    config.settings_path().parent.mkdir(parents=True, exist_ok=True)
    config.settings_path().write_text(json.dumps(settings), encoding="utf-8")

    valid, errors = config.load_config().cloud_models

    assert "gemini" not in [m.id for m in valid]
    (error,) = [e for e in errors if "gemini" in e]
    assert "écarté" in error and "pricing.input_usd_per_mtok" in error


def test_the_euro_rate_is_bounded():
    """Bounded to [0,5 ; 2]; a value that is not a finite number is the default."""
    assert config.Config(values={}).eur_per_usd == 0.86
    assert config.Config(values={"finops": {"eur_per_usd": 0.92}}).eur_per_usd == 0.92
    assert config.Config(values={"finops": {"eur_per_usd": 5}}).eur_per_usd == 2.0
    assert config.Config(values={"finops": {"eur_per_usd": 0.1}}).eur_per_usd == 0.5
    for unreadable in ("abc", "nan", "inf", None):
        assert config.Config(values={"finops": {"eur_per_usd": unreadable}}).eur_per_usd == 0.86


def test_a_configured_euro_rate_reaches_the_event_and_the_state(monkeypatch):
    settings = {"finops": {"eur_per_usd": 0.92}}
    config.settings_path().parent.mkdir(parents=True, exist_ok=True)
    config.settings_path().write_text(json.dumps(settings), encoding="utf-8")
    provider = GeminiProvider(GEMINI_TEXT)
    _, app_session, _, client = _app(monkeypatch, provider)
    config.write_api_key("gemini", "generativelanguage.googleapis.com", SecretStr(SENTINEL))
    app_session.boot_cloud(config.load_config().cloud_model("gemini")).result()
    app_session.join()

    events = _turn(app_session, "Bonjour")

    (spend,) = (e.payload for e in _of(events, "consumption_updated"))
    assert spend["eur_per_usd"] == 0.92
    assert spend["total_eur"] == pytest.approx(spend["total_usd"] * 0.92)
    assert spend["total_usd"] == pytest.approx(spend["total_in_usd"] + spend["total_out_usd"])
    assert client.get("/api/state").json()["consumption_updated"] == spend


def test_a_priced_call_cut_by_an_error_after_its_output_is_billed_to_the_turn():
    """Content, then an error in the stream: the call ends in error, yet an output came, so
    it is billed; the turn's total is that call's cost."""
    error = {"error": {"message": "Internal error", "code": 500}}
    session = _cloud_session("gemini", GeminiProvider(sse(delta(content="Il est"), error)))

    events = _turn(session, "Quelle heure est-il ?")

    (ended,) = (e.payload for e in _of(events, "model_call_ended"))
    assert ended["stop_reason"] == "error"
    assert ended["cost_in_usd"] > 0 and ended["cost_out_usd"] > 0
    assert ended["cost_source"] == "estimate"  # no `usage` came before the error
    (spend,) = (e.payload for e in _of(events, "consumption_updated"))
    assert spend["calls"] == 1 and spend["total_in_usd"] == ended["cost_in_usd"]
    turn_ended = _of(events, "turn_ended")[0].payload
    assert turn_ended["status"] == "error" and turn_ended["cost_source"] == "estimate"
    assert turn_ended["cost_in_usd"] == ended["cost_in_usd"]
    assert turn_ended["cost_out_usd"] == ended["cost_out_usd"]
