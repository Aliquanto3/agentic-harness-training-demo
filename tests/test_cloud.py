"""Story 11: cloud models through `openai_chat` (AD-4, AD-5, AD-15, AD-16, AD-20, AD-21).

Every provider answer comes from an `httpx.MockTransport`: nothing leaves the machine.
"""

from __future__ import annotations

import json
import logging

import httpx
import pytest
from pydantic import SecretStr
from starlette.testclient import TestClient

from wavestack import config
from wavestack.context.render import distribute
from wavestack.models import discovery
from wavestack.models.openai_chat import OpenAIChatEngine
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

    def __call__(self, request: httpx.Request) -> httpx.Response:
        self.requests.append(request)
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
    ],
)
def test_provider_refusals_become_explained_errors(status, headers, error, fragment, scope):
    answer = httpx.Response(status, json={"error": {"message": error}}, headers=headers)
    provider = Provider(answer, GROQ_TEXT)
    session = _cloud_session("groq", provider)

    events = _turn(session, "Bonjour")

    harness = _of(events, "harness_error")[0].payload
    assert fragment in harness["message_fr"] and harness["hints_fr"]
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
    failed = httpx.Response(
        400,
        json={
            "error": {
                "message": "Failed to call a function",
                "code": "tool_use_failed",
                "failed_generation": "<function=get_datetime>",
            }
        },
    )
    provider = Provider(failed, GROQ_TEXT)
    session = _cloud_session("groq", provider, bricks=("tools",))

    events = _turn(session, "Heure ?")

    assert _of(events, "tool_call_malformed")[0].payload["raw"] == "<function=get_datetime>"
    assert _of(events, "harness_error") == []
    assert _of(events, "turn_ended")[0].payload["status"] == "completed"


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

    session.booted_path, session.booted_cloud = None, "groq"  # a cloud model is loaded
    gguf = tmp_path / "other.gguf"
    gguf.write_bytes(b"placeholder")
    body = client.post(
        "/api/intentions/select_model", json={"kind": "file", "ref": str(gguf)}, headers=ORIGIN
    ).json()
    app_session.join()

    assert body["next_launch"] is True and not app_session.model_loaded
    assert config.read_settings()["selected_model"] == {"kind": "file", "ref": str(gguf)}
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
