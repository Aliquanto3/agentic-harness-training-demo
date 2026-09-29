"""Story 19: delegation to a sub-agent, the same engine in a context of its own (AD-10,
AD-11, AD-25). One test per row of the I/O matrix, then the contract around it."""

from __future__ import annotations

import shutil
import time

import httpx
import pytest
from fake_engine import CHATML, FakeEngine
from test_bricks import HEADERS, _client
from test_cloud import SENTINEL, Provider, _cloud_session, _journal_text, _no_sentinel, delta, sse
from test_hooks import fake_hooks
from test_tools import QWEN, _segments, call, web  # noqa: F401 - fixture

from wavestack import config
from wavestack.hooks import DEMO_HOOKS
from wavestack.session.app_session import AppSession, ArmRefused
from wavestack.trace.journal import get_journal

TASK = "Lis le fichier notes_reunion.txt et liste les décisions."
RESULT = "Décisions : budget validé, planning validé."


def sub_session(outputs, *, window=16384, bricks=("tools", "subagent"), tools=None, hooks=None):
    """A booted session with a Qwen-like model (tool calls parsed) and `bricks` wanted."""
    engine = FakeEngine(outputs=list(outputs), template=QWEN.decode("utf-8"), architecture="qwen35")
    session = AppSession(
        config.Config(values={"context": {"window": window, "near_limit_ratio": 0.8}}),
        engine_factory=lambda path, n_ctx: engine,
        hooks=hooks or DEMO_HOOKS,
    )
    session.boot("fake.gguf").result()
    for brick in bricks:
        session.set_brick(brick, True)
    for tool in tools or ():
        session.set_tool(tool, True)
    session.join()
    return engine, session


def run(session, message: str) -> list:
    mark = get_journal().last_seq()
    session.send(message)
    session.join()
    return get_journal().events_since(mark)


def of(events, kind: str, context: str | None = None) -> list:
    return [e for e in events if e.kind == kind and (context is None or e.context_id == context)]


def status(events) -> str:
    return of(events, "turn_ended")[0].payload["status"]


def delegation(task: str = TASK) -> str:
    return call("delegate", task=task)


# ---------- I/O matrix ----------


def test_the_model_delegates_and_only_the_result_enters_the_main_context():
    outputs = [delegation(), call("read_file", path="notes_reunion.txt"), RESULT, "Voilà."]
    engine, session = sub_session(outputs)

    events = run(session, "Quelles décisions ont été prises ?")

    (started,) = of(events, "tool_started", "main")
    assert (started.payload["tool"], started.trigger) == ("delegate", "model")
    assert (started.brick, started.component) == ("subagent", "subagent.agent")
    assert started.payload["phase_label"] == "Appel au sous-agent"
    (sub_started,) = of(events, "subagent_started")
    assert sub_started.context_id == "sub1" and sub_started.parent_step == started.step_id
    assert sub_started.payload["task"] == TASK and sub_started.payload["tools"] == ["read_file"]
    (read,) = of(events, "tool_started", "sub1")
    assert read.payload["tool"] == "read_file"
    sub_events = [e for e in events if e.context_id == "sub1"]
    assert all(e.parent_step == started.step_id for e in sub_events)
    assert all(e.trigger == "model" for e in sub_events)
    assert "turn_started" not in {e.kind for e in sub_events}  # not a turn (AD-11)
    assert "turn_ended" not in {e.kind for e in sub_events}
    (ended,) = of(events, "subagent_ended")
    assert ended.payload["status"] == "completed" and ended.payload["result"] == RESULT
    assert ended.payload["calls"] == 2
    assert [e.payload["status"] for e in of(events, "tool_ended", "main")] == ["ok"]
    assert of(events, "tool_ended", "main")[0].payload["result"] == RESULT
    # The main context: the result alone, attributed to the brick, never the file read.
    first, second = of(events, "context_rendered", "main")
    (result,) = _segments(second.payload, "subagent_result")
    assert (result["text"], result["brick"], result["component"]) == (
        RESULT,
        "subagent",
        "subagent.agent",
    )
    notes = (config.content_dir() / "demo_files" / "notes_reunion.txt").read_text("utf-8")
    assert notes.strip()[:60] not in "".join(s["text"] for s in second.payload["segments"])
    assert _segments(second.payload, "tool_result") == []
    assert len(engine.calls) == 4 and status(events) == "completed"
    session.close()


def test_the_sub_agent_context_has_its_prompt_the_task_and_its_tools_only():
    outputs = ["Enchanté.", delegation(), RESULT, "Voilà."]
    engine, session = sub_session(outputs, bricks=("short_memory", "system_prompt", "tools"))
    session.set_brick("subagent", True)
    run(session, "Je m'appelle Camille.")

    events = run(session, "Résume les notes.")

    first = of(events, "context_rendered", "sub1")[0].payload
    kinds = {s["kind"] for s in first["segments"]}
    assert "history" not in kinds and "hook_injection" not in kinds
    (prompt,) = _segments(first, "system_prompt")
    assert prompt["brick"] == "subagent" and "sous-agent de WaveStack" in prompt["text"]
    (task,) = _segments(first, "user_message")
    assert (task["text"], task["brick"], task["component"]) == (TASK, "subagent", "subagent.agent")
    catalog = "".join(s["text"] for s in _segments(first, "tool_catalog"))
    assert "read_file" in catalog and "delegate" not in catalog  # no nested delegation
    assert "calculator" not in catalog  # `[subagent] tools` only
    text = "".join(s["text"] for s in first["segments"])
    assert "Camille" not in text and "assistant de démonstration" not in text
    assert sum(s["tokens"] for s in first["segments"]) == first["used"]
    assert list("".join(s["text"] for s in first["segments"]).encode()) == engine.calls[2]
    session.close()


def test_ids_steps_and_figures_of_the_sub_agent():
    outputs = [delegation(), call("read_file", path="notes_reunion.txt"), RESULT, "Voilà."]
    engine, session = sub_session(outputs)

    events = run(session, "Quelles décisions ?")

    calls = of(events, "context_rendered", "sub1")
    assert [e.call_id for e in calls] == ["t1.sub1.c1", "t1.sub1.c2"]
    assert [e.step_id for e in calls] == ["t1.sub1.s1", "t1.sub1.s3"]
    assert of(events, "tool_started", "sub1")[0].step_id == "t1.sub1.s2"
    assert all(e.component == "core.model_sub" for e in calls)
    ended = of(events, "subagent_ended")[0].payload
    assert ended["context_tokens"] == calls[-1].payload["used"]
    assert ended["result_tokens"] == len(RESULT.encode("utf-8"))  # the model's tokenizer
    # The saving: the tool results kept in the sub-agent against the result reinjected.
    kept = sum(s["tokens"] for s in _segments(calls[-1].payload, "tool_result"))
    assert ended["kept_tokens"] == kept > 0
    assert ended["saved_tokens"] == kept - ended["result_tokens"] > 0
    assert ended["context_tokens"] > kept  # the whole context is not the saving
    assert ended["estimated"] is False
    session.close()


def test_forced_delegation_runs_before_the_first_main_call_and_costs_no_call():
    outputs = [call("read_file", path="notes_reunion.txt"), RESULT, "Voilà."]
    engine, session = sub_session(outputs)
    session.arm("delegate", "delegate", {"task": TASK})

    events = run(session, "Bonjour")

    (started,) = of(events, "tool_started", "main")
    assert (started.payload["tool"], started.trigger) == ("delegate", "user")
    first_main = of(events, "model_call_started", "main")[0]
    assert started.seq < first_main.seq
    assert all(e.trigger == "user" for e in events if e.context_id == "sub1")
    assert len(engine.calls) == 3  # two for the sub-agent, one main call
    ctx = of(events, "context_rendered", "main")[0].payload
    (result,) = _segments(ctx, "subagent_result")
    assert result["text"] == RESULT and result["brick"] == "subagent"
    assert status(events) == "completed" and session._armed == []
    session.close()


@pytest.mark.parametrize(
    ("kind", "target", "args", "code", "reason"),
    [
        ("delegate", "delegate", {"task": "  "}, 422, "La tâche du sous-agent est vide."),
        ("delegate", "read_file", {"task": TASK}, 404, "n'est pas la délégation"),
    ],
)
def test_arming_refuses_an_empty_task_or_another_target(kind, target, args, code, reason):
    _, session = sub_session(["Voilà."])
    with pytest.raises(ArmRefused) as refused:
        session.arm(kind, target, args)
    assert reason in refused.value.reason_fr and "Rien n'est armé." in refused.value.reason_fr
    assert refused.value.not_found is (code == 404)
    with _client(session) as client:
        response = client.post(
            "/api/intentions/arm",
            json={"kind": kind, "target": target, "args": args},
            headers=HEADERS,
        )
        assert response.status_code == code
        armed = client.post(
            "/api/intentions/arm",
            json={"kind": "delegate", "target": "delegate", "args": {"task": "x" * 60}},
            headers=HEADERS,
        )
        assert armed.status_code == 200
    (action,) = session._armed
    assert action.label_fr == f"Délégation : « {'x' * 40}… »" and action.brick == "subagent"
    session.close()


def test_brick_off_after_arming_drops_the_action_and_the_turn_goes_on():
    engine, session = sub_session(["Voilà."])
    session.arm("delegate", "delegate", {"task": TASK})
    session.set_brick("subagent", False)

    events = run(session, "Bonjour")

    (dropped,) = of(events, "action_dropped")
    assert "Sous-agent" in dropped.payload["reason_fr"] and dropped.trigger == "user"
    assert of(events, "subagent_started") == [] and len(engine.calls) == 1
    assert status(events) == "completed"
    session.close()


def test_sub_agent_overflow_fails_the_delegation_not_the_turn():
    # The fake engine counts a token per byte: the guide (≈ 7 000 bytes) cannot fit in 4 096.
    task = "Lis le fichier guide_harnais.md et résume-le."
    outputs = [delegation(task), call("read_file", path="guide_harnais.md"), "Désolé."]
    engine, session = sub_session(outputs, window=4096)

    events = run(session, "Résume le guide.")

    (overflow,) = of(events, "context_overflow")
    assert (
        overflow.context_id == "sub1" and "contexte du sous-agent" in overflow.payload["message_fr"]
    )
    (ended,) = of(events, "tool_ended", "main")
    assert ended.payload["status"] == "overflow"
    assert "La délégation au sous-agent a échoué" in ended.payload["error_fr"]
    ended_sub = of(events, "subagent_ended")[0].payload
    assert ended_sub["status"] == "overflow" and ended_sub["saved_tokens"] == 0
    second = of(events, "context_rendered", "main")[-1].payload
    (result,) = _segments(second, "subagent_result")  # the error, as the result (H-6)
    assert "dépassé" in result["text"]
    assert len(engine.calls) == 3 and status(events) == "completed"
    session.close()


def test_sub_agent_bound_stops_it_after_four_calls():
    reads = [call("read_file", path="notes_reunion.txt")] * 4
    engine, session = sub_session([delegation(), *reads, "Voilà."])

    events = run(session, "Quelles décisions ?")

    (limit,) = of(events, "limit_reached")
    assert limit.context_id == "sub1" and limit.payload["limit"] == "sub_calls"
    assert of(events, "tool_ended", "main")[0].payload["status"] == "limit"
    assert len(of(events, "model_call_started", "sub1")) == 4
    assert of(events, "subagent_ended")[0].payload["calls"] == 4
    assert len(engine.calls) == 6 and status(events) == "completed"  # c1 + 4 + c2
    session.close()


def test_sub_agent_retries_count_in_its_calls():
    bad = "<tool_call>\n<function=read_file\nx\n</tool_call>"
    engine, session = sub_session([delegation(), bad, bad, bad, "Voilà."])

    events = run(session, "Quelles décisions ?")

    assert [e.payload["reaction"] for e in of(events, "tool_call_malformed", "sub1")] == [
        "retry",
        "retry",
        "stop",
    ]
    (limit,) = of(events, "limit_reached", "sub1")
    assert limit.payload["limit"] == "sub_retries"
    assert "le tour principal continue" in limit.payload["message_fr"]
    assert of(events, "tool_ended", "main")[0].payload["status"] == "limit"
    assert status(events) == "completed"
    session.close()


def test_sub_agent_output_cut_at_the_reserve_fails_the_delegation():
    engine, session = sub_session([delegation(), "x" * 600, "Voilà."])

    events = run(session, "Quelles décisions ?")

    (cut,) = of(events, "output_truncated")
    assert cut.context_id == "sub1" and cut.payload["max_tokens"] == 512
    assert of(events, "tool_ended", "main")[0].payload["status"] == "limit"
    assert of(events, "subagent_ended")[0].payload["status"] == "limit"
    assert status(events) == "completed"
    session.close()


def test_sub_agent_provider_refusal_is_traced_in_its_context_and_the_turn_goes_on():
    delegate = sse(
        delta(
            tool_calls=[
                {
                    "index": 0,
                    "id": "c1",
                    "function": {"name": "delegate", "arguments": '{"task": "Résume."}'},
                }
            ]
        ),
        delta("tool_calls"),
    )
    refused = httpx.Response(
        429, json={"error": {"message": f"Rate limit {SENTINEL}"}}, headers={"retry-after": "7"}
    )
    final = sse(delta(content="Voilà."), delta("stop"))
    provider = Provider(delegate, refused, final)
    session = _cloud_session("groq", provider, bricks=("tools", "subagent"))

    mark = get_journal().last_seq()
    session.send("Résume les notes.")
    session.join()
    events = get_journal().events_since(mark)

    (error,) = of(events, "harness_error")
    assert error.context_id == "sub1" and "délégation échoue" in error.payload["effect_fr"]
    (ended,) = of(events, "tool_ended", "main")
    assert ended.payload["status"] == "error"
    assert of(events, "subagent_ended")[0].payload["estimated"] is True
    assert len(provider.requests) == 3 and status(events) == "completed"
    _no_sentinel(_journal_text())
    session.close()


def test_h5_asks_inside_the_sub_agent_and_its_refusal_goes_back_to_it(web):  # noqa: F811
    sent = web(lambda r: httpx.Response(200, text="<p>Paris</p>"))
    page = call("fetch_page", url="https://fr.wikipedia.org/wiki/Paris")
    engine, session = sub_session(
        [delegation("Lis la page Paris."), page, "Refusé, désolé.", "Voilà."],
        bricks=("tools", "subagent", "hooks"),
        tools=("fetch_page",),
    )
    session.set_hook("h5", True)
    session.join()
    mark = get_journal().last_seq()
    session.send("Parle-moi de Paris.")
    deadline = time.monotonic() + 30
    while not of(get_journal().events_since(mark), "approval_requested"):
        assert time.monotonic() < deadline
        time.sleep(0.01)
    while session.state != "awaiting_human":
        time.sleep(0.01)
    (asked,) = of(get_journal().events_since(mark), "approval_requested")
    session.answer_approval(asked.payload["approval_id"], False, False)
    session.join()
    events = get_journal().events_since(mark)

    assert asked.context_id == "sub1" and asked.step_id.startswith("t1.sub1.h")
    decided = [e for e in of(events, "hook_decided", "sub1") if e.payload["hook"] == "h5"]
    assert decided[0].step_id == asked.step_id
    assert sent == []  # refused: nothing left the workstation
    second = of(events, "context_rendered", "sub1")[-1].payload
    refusal = [s for s in second["segments"] if s["brick"] == "hooks"]
    assert refusal and "Refusé par l'utilisateur" in refusal[0]["text"]
    assert of(events, "subagent_ended")[0].payload["result"] == "Refusé, désolé."
    assert status(events) == "completed"
    session.close()


def test_before_model_call_hooks_apply_inside_the_sub_agent():
    hooks = fake_hooks("h1", "before_model_call", "block")
    engine, session = sub_session(
        ["Jamais lu."], bricks=("tools", "subagent", "hooks"), hooks=hooks
    )
    session.arm("delegate", "delegate", {"task": TASK})  # forced: the sub-agent calls first

    events = run(session, "Bonjour")

    blocked = [e for e in of(events, "hook_decided") if e.payload["decision"] == "block"]
    assert [e.context_id for e in blocked] == ["sub1", "main"]
    assert blocked[0].step_id.startswith("t1.sub1.h")
    (ended,) = of(events, "tool_ended", "main")
    assert ended.payload["status"] == "error" and "a bloqué" in ended.payload["error_fr"]
    assert engine.calls == [] and status(events) == "blocked"
    session.close()


def test_stop_during_the_sub_agent_cancels_the_turn_without_another_call():
    engine, session = sub_session([delegation(), "x" * 400, "Jamais lu."])
    engine.delay = 0.005
    mark = get_journal().last_seq()
    session.send("Quelles décisions ?")
    deadline = time.monotonic() + 30
    while not of(get_journal().events_since(mark), "model_call_started", "sub1"):
        assert time.monotonic() < deadline
        time.sleep(0.01)
    session.stop()
    session.join()
    events = get_journal().events_since(mark)

    assert of(events, "subagent_ended")[0].payload["status"] == "cancelled"
    (ended,) = of(events, "tool_ended", "main")
    assert ended.payload["status"] == "cancelled"
    assert "Délégation arrêtée" in ended.payload["error_fr"]
    assert status(events) == "cancelled" and len(engine.calls) == 2
    session.close()


def test_without_the_tools_brick_the_sub_agent_answers_without_tools():
    engine, session = sub_session([delegation(), RESULT, "Voilà."], bricks=("subagent",))

    events = run(session, "Quelles décisions ?")

    first = of(events, "context_rendered", "sub1")[0].payload
    assert _segments(first, "tool_catalog") == []
    assert of(events, "subagent_started")[0].payload["tools"] == []
    assert of(events, "subagent_ended")[0].payload["result"] == RESULT
    assert status(events) == "completed"
    session.close()


# ---------- the contract around it ----------


def test_an_empty_answer_becomes_a_sentence():
    engine, session = sub_session([delegation(), "  ", "Voilà."])

    events = run(session, "Quelles décisions ?")

    assert of(events, "subagent_ended")[0].payload["result"] == (
        "(Le sous-agent n'a rendu aucun texte.)"
    )
    session.close()


def test_the_result_stays_in_the_history_without_a_stub():
    engine, session = sub_session(
        [delegation(), RESULT, "Voilà.", "Encore."], bricks=("short_memory", "tools", "subagent")
    )
    run(session, "Quelles décisions ?")

    events = run(session, "Et ensuite ?")

    ctx = of(events, "context_rendered", "main")[0].payload
    assert _segments(ctx, "subagent_result") == []
    assert RESULT in [s["text"] for s in _segments(ctx, "history")]
    session.close()


def test_sub_agents_are_numbered_over_the_session():
    outputs = [delegation(), RESULT, "Voilà."] * 2
    engine, session = sub_session(outputs)
    run(session, "Un.")
    session.clear_conversation()
    session.join()

    events = run(session, "Deux.")

    assert of(events, "subagent_started")[0].context_id == "sub2"  # H-10: never reset
    session.close()


def test_the_schema_draws_a_second_model_and_the_card_its_force():
    _, session = sub_session(["Voilà."])
    mark = get_journal().last_seq()
    session.set_brick("subagent", False)
    session.set_brick("subagent", True)
    arch = of(get_journal().events_since(mark), "architecture_changed")[-1].payload
    nodes = {n["id"]: n for n in arch["nodes"]}
    sub = nodes["core.model_sub"]
    assert (sub["kind"], sub["hosting"], sub["label_fr"]) == (
        "model",
        "local",
        "Modèle (sous-agent)",
    )
    assert nodes["subagent.agent"]["kind"] == "brick"
    # As `core.model`: drawn inside the harness locally, with no edge.
    assert all(e["to"] != "core.model_sub" for e in arch["edges"])
    cards = of(get_journal().events_since(mark), "bricks_changed")[-1].payload["bricks"]
    card = next(b for b in cards if b["id"] == "subagent")
    assert card["force"]["label_fr"] == "Déléguer au sous-agent"
    assert card["force"]["kind"] == "delegate" and card["force"]["target"] == "delegate"
    assert list(card["force"]["parameters"]) == ["task"] and card["force"]["presets"]
    assert card["limits_fr"].startswith("Sous-agent : 4 appels au modèle au plus")
    assert "Lecture de fichier" in card["limits_fr"]
    session.set_brick("subagent", False)
    arch = of(get_journal().events_since(mark), "architecture_changed")[-1].payload
    assert "core.model_sub" not in {n["id"] for n in arch["nodes"]}
    session.close()


def test_cloud_sub_model_is_drawn_in_the_network_zone_and_keeps_its_own_ratio():
    delegate = sse(
        delta(
            tool_calls=[
                {
                    "index": 0,
                    "id": "c1",
                    "function": {"name": "delegate", "arguments": '{"task": "R"}'},
                }
            ]
        ),
        {**delta("tool_calls"), "usage": {"prompt_tokens": 1, "completion_tokens": 1}},
    )
    sub_answer = sse(
        delta(content="Résultat."),
        {**delta("stop"), "usage": {"prompt_tokens": 100000, "completion_tokens": 1}},
    )
    final = sse(
        delta(content="Voilà."),
        {**delta("stop"), "usage": {"prompt_tokens": 1, "completion_tokens": 1}},
    )
    session = _cloud_session("groq", Provider(delegate, sub_answer, final), bricks=("subagent",))
    arch = [e for e in get_journal().all_events() if e.kind == "architecture_changed"][-1].payload
    sub = next(n for n in arch["nodes"] if n["id"] == "core.model_sub")
    assert sub["hosting"] == "network" and sub["provider"] == "Groq"
    assert {"from": "core.harness", "to": "core.model_sub", "crosses_boundary": True} in arch[
        "edges"
    ]

    events = run(session, "Résume.")

    assert session._ratios == {"groq": 0.8, "groq#sub": 1.5}  # AD-4: one ratio each
    reconciled = of(events, "context_reconciled", "sub1")[0].payload
    ended = of(events, "subagent_ended")[0].payload
    assert ended["context_tokens"] == reconciled["used"] == 100000
    assert status(events) == "completed"
    session.close()


def test_all_bricks_off_after_the_subagent_is_the_bare_llm_byte_for_byte():
    engine = FakeEngine(template=CHATML)
    session = AppSession(
        config.Config(values={"context": {"window": 4096, "near_limit_ratio": 0.8}}),
        engine_factory=lambda path, n_ctx: engine,
    )
    session.boot("fake.gguf").result()
    session.set_brick("subagent", True)
    session.set_brick("subagent", False)

    run(session, "Bonjour")

    assert engine.calls[0] == list(b"<|im_start|>user\nBonjour<|im_end|>\n<|im_start|>assistant\n")
    session.close()


def test_invalid_subagent_content_makes_the_brick_unavailable(tmp_path, monkeypatch):
    content = tmp_path / "content"
    shutil.copytree(config.content_dir(), content)
    (content / "subagent.yaml").write_text("delegate: {}\n", encoding="utf-8")
    monkeypatch.setattr(config, "content_dir", lambda: content)

    session = AppSession(config.Config(values={}))
    session._caps = session._caps or type("Caps", (), {"tool_call_parser": "qwen3_coder"})()
    available, reason = session._availability("subagent")
    assert not available and "content/subagent.yaml" in reason
    assert session._registry.get("delegate") is None
    session.close()


def test_h2_logs_the_delegation_under_its_own_name():
    engine, session = sub_session(
        [delegation(), call("read_file", path="notes_reunion.txt"), RESULT, "Voilà."],
        bricks=("tools", "subagent", "hooks"),
    )
    path = config.audit_path()
    before = path.read_text("utf-8").splitlines() if path.exists() else []

    run(session, "Quelles décisions ?")

    lines = path.read_text("utf-8").splitlines()[len(before) :]
    tools = [line.split(" | ")[3] for line in lines if " | appel d'outil | " in line]
    assert tools[0].startswith("read_file") and tools[1].startswith("delegate")
    session.close()


# ---------- independent review (2026-09-26) ----------


def test_h5_state_during_the_sub_agent_is_the_sessions(web):  # noqa: F811
    """The blocker: `session_state` `awaiting_human` emitted in `sub1` reaches `/api/state`
    and the front as the session's state (the front routes by kind, see app.js SUB_KINDS)."""
    web(lambda r: httpx.Response(200, text="<p>Paris</p>"))
    page = call("fetch_page", url="https://fr.wikipedia.org/wiki/Paris")
    engine, session = sub_session(
        [delegation("Lis la page Paris."), page, "Paris.", "Voilà."],
        bricks=("tools", "subagent", "hooks"),
        tools=("fetch_page",),
    )
    session.set_hook("h5", True)
    session.join()
    client = _client(session)
    mark = get_journal().last_seq()
    session.send("Parle-moi de Paris.")
    deadline = time.monotonic() + 30
    while session.state != "awaiting_human":
        assert time.monotonic() < deadline
        time.sleep(0.01)
    state = client.get("/api/state").json()
    assert state["session_state"]["state"] == "awaiting_human"
    assert state["pending_approval"]["tool"] == "fetch_page"
    answered = client.post(
        "/api/intentions/approval",
        json={"approval_id": state["pending_approval"]["approval_id"], "approved": True},
        headers=HEADERS,
    )
    assert answered.status_code == 200
    session.join()
    events = get_journal().events_since(mark)
    waiting = [e for e in of(events, "session_state") if e.payload["state"] == "awaiting_human"]
    assert waiting and waiting[0].context_id == "sub1"
    assert of(events, "subagent_ended")[0].payload["status"] == "completed"
    assert status(events) == "completed"
    session.close()


def test_delegation_through_fetch_page(web):  # noqa: F811
    sent = web(lambda r: httpx.Response(200, text="<p>Paris est la capitale.</p>"))
    page = call("fetch_page", url="https://fr.wikipedia.org/wiki/Paris")
    engine, session = sub_session(
        [delegation("Lis la page Paris."), page, "Paris est la capitale.", "Voilà."],
        tools=("fetch_page",),
    )

    events = run(session, "Parle-moi de Paris.")

    assert of(events, "subagent_started")[0].payload["tools"] == ["read_file", "fetch_page"]
    (fetched,) = of(events, "tool_started", "sub1")
    assert fetched.payload["tool"] == "fetch_page" and len(sent) == 1
    (outbound,) = of(events, "outbound_request")
    assert outbound.context_id == "sub1" and outbound.parent_step is not None
    assert of(events, "subagent_ended")[0].payload["result"] == "Paris est la capitale."
    session.close()


def test_state_after_a_stopped_delegation_shows_the_main_context():
    engine, session = sub_session([delegation(), "x" * 400, "Jamais lu."])
    engine.delay = 0.005
    mark = get_journal().last_seq()
    session.send("Quelles décisions ?")
    deadline = time.monotonic() + 30
    while not of(get_journal().events_since(mark), "model_call_started", "sub1"):
        assert time.monotonic() < deadline
        time.sleep(0.01)
    session.stop()
    session.join()
    last = [e for e in get_journal().events_since(mark) if e.kind == "context_rendered"][-1]
    assert last.context_id == "sub1"  # the journal's last one is the sub-agent's

    with _client(session) as client:
        state = client.get("/api/state", headers=HEADERS).json()
    assert state["context_rendered"]["context_id"] == "main"
    session.close()


def test_cloud_sub_agent_tool_call_and_reply_are_paired_in_its_second_body():
    def calls(name, arguments, call_id):
        return sse(
            delta(
                tool_calls=[
                    {"index": 0, "id": call_id, "function": {"name": name, "arguments": arguments}}
                ]
            ),
            delta("tool_calls"),
        )

    provider = Provider(
        calls("delegate", '{"task": "Lis notes_reunion.txt."}', "p1"),
        calls("read_file", '{"path": "notes_reunion.txt"}', "p2"),
        sse(delta(content=RESULT), delta("stop")),
        sse(delta(content="Voilà."), delta("stop")),
    )
    session = _cloud_session("groq", provider, bricks=("tools", "subagent"))

    events = run(session, "Quelles décisions ?")

    import json

    second = json.loads(provider.requests[2].content)  # the sub-agent's second call
    assert second["messages"][0]["content"].startswith("Tu es un sous-agent")
    (assistant,) = [m for m in second["messages"] if m.get("tool_calls")]
    (tool_call,) = assistant["tool_calls"]
    assert tool_call["function"] == {
        "name": "read_file",
        "arguments": '{"path": "notes_reunion.txt"}',
    }
    (reply,) = [m for m in second["messages"] if m["role"] == "tool"]
    assert reply["tool_call_id"] == tool_call["id"] != "p2"  # the session's id (AD-4)
    assert "delegate" not in [t["function"]["name"] for t in second.get("tools", [])]
    assert status(events) == "completed"
    session.close()


def test_an_exception_in_the_sub_agent_fails_the_delegation_only(monkeypatch):
    engine, session = sub_session([delegation(), "Voilà."])

    def broken(*args, **kwargs):
        raise RuntimeError("panne du sous-agent")

    monkeypatch.setattr(session, "_run_subagent", broken)

    events = run(session, "Quelles décisions ?")

    (error,) = of(events, "harness_error")
    assert error.context_id == "sub1" and "RuntimeError" in error.payload["cause"]
    assert of(events, "subagent_ended")[0].payload["status"] == "error"
    (ended,) = of(events, "tool_ended", "main")
    assert ended.payload["status"] == "error"
    assert ended.payload["error_fr"].startswith("La délégation au sous-agent a échoué")
    assert status(events) == "completed"
    session.close()


def test_h3_injection_stays_in_the_main_context():
    engine, session = sub_session(
        [delegation(), RESULT, "Voilà."], bricks=("tools", "subagent", "hooks")
    )

    events = run(session, "Quelles décisions ?")

    main = of(events, "context_rendered", "main")[0].payload
    assert _segments(main, "hook_injection")
    for rendered in of(events, "context_rendered", "sub1"):
        assert _segments(rendered.payload, "hook_injection") == []
    session.close()


def test_h1_blocks_a_confidential_read_asked_by_the_sub_agent():
    secret = call("read_file", path="confidentiel/budget_projet.txt")
    engine, session = sub_session(
        [delegation(), secret, "Bloqué.", "Voilà."], bricks=("tools", "subagent", "hooks")
    )

    events = run(session, "Résume le budget.")

    (blocked,) = [e for e in of(events, "hook_decided", "sub1") if e.payload["decision"] == "block"]
    assert blocked.payload["hook"] == "h1" and blocked.step_id.startswith("t1.sub1.h")
    assert of(events, "tool_started", "sub1") == []  # the tool never ran
    second = of(events, "context_rendered", "sub1")[-1].payload
    refusal = [s for s in second["segments"] if s["brick"] == "hooks"]
    assert refusal and "garde-fou" in refusal[0]["text"]
    lines = config.audit_path().read_text("utf-8").splitlines()
    assert any(" | t1.sub1 | appel bloqué par H1 | " in line for line in lines)
    session.close()


def test_the_sub_agent_does_not_reason_and_keeps_the_small_reserve():
    thought = "Je délègue.\n</think>\n\n"  # the main model reasons, then calls
    engine, session = sub_session([thought + delegation(), RESULT, thought + "Voilà."])
    session.set_brick("reasoning", True)
    session.join()

    events = run(session, "Quelles décisions ?")

    main = of(events, "context_rendered", "main")[0].payload
    sub = of(events, "context_rendered", "sub1")[0].payload
    assert main["reserve"] == 1536 and sub["reserve"] == 512
    prompt = "".join(s["text"] for s in sub["segments"])
    assert not prompt.endswith("<think>\n")  # enable_thinking off in the sub-agent
    session.close()


def test_a_refused_delegate_call_is_not_a_sub_agent_result():
    engine, session = sub_session([call("delegate"), "Voilà."])  # no `task`

    events = run(session, "Quelles décisions ?")

    assert of(events, "subagent_started") == []
    second = of(events, "context_rendered", "main")[1].payload
    assert _segments(second, "subagent_result") == []
    assert "argument « task » manquant" in _segments(second, "tool_result")[0]["text"]
    session.close()


@pytest.mark.parametrize(
    ("args", "reason"),
    [({"task": 12}, "doit être un texte"), ({"task": "Lis.", "path": "x"}, "Argument inconnu")],
)
def test_arming_refuses_a_non_text_task_or_another_argument(args, reason):
    _, session = sub_session(["Voilà."])
    with _client(session) as client:
        response = client.post(
            "/api/intentions/arm",
            json={"kind": "delegate", "target": "delegate", "args": args},
            headers=HEADERS,
        )
    assert response.status_code == 422 and reason in response.json()["detail"]
    assert session._armed == []
    session.close()


def test_an_unknown_tool_in_the_subagent_section_is_traced_at_load():
    mark = get_journal().last_seq()
    session = AppSession(config.Config(values={"subagent": {"tools": ["read_file", "lire_tout"]}}))
    (error,) = of(get_journal().events_since(mark), "harness_error")
    assert "lire_tout" in error.payload["message_fr"]
    session.close()


def test_token_count_falls_back_to_an_estimate():
    engine, session = sub_session(["Voilà."])

    def broken(text):
        raise RuntimeError("tokenizer")

    engine.tokenize = broken
    assert session._count_tokens("x" * 40) == (10, True)
    session.close()


# ---------- follow-up review (2026-09-26) ----------


@pytest.mark.parametrize(("ratio", "tokens"), [(1.3, 10), (0.9, 9)])
def test_chat_result_tokens_follow_the_segments_scaling(ratio, tokens):
    """As `distribute`: a main ratio above 1 never grows a segment, below 1 shrinks it."""
    session = _cloud_session("groq", Provider(sse(delta(content="Oui."), delta("stop"))))
    session._ratios["groq"] = ratio
    assert session._count_tokens("x" * 40) == (tokens, True)  # 40 characters: 10 estimated
    session.close()


def _delegating_provider(*sub_answers):
    delegate = sse(
        delta(
            tool_calls=[
                {
                    "index": 0,
                    "id": "c1",
                    "function": {"name": "delegate", "arguments": '{"task": "R"}'},
                }
            ]
        ),
        delta("tool_calls"),
    )
    return Provider(delegate, *sub_answers, sse(delta(content="Voilà."), delta("stop")))


def test_chat_cut_output_keeps_the_reconciled_context_figure():
    cut = sse(
        delta(content="Début…"),
        {**delta("length"), "usage": {"prompt_tokens": 4321, "completion_tokens": 512}},
    )
    session = _cloud_session("groq", _delegating_provider(cut), bricks=("subagent",))

    events = run(session, "Résume.")

    ended = of(events, "subagent_ended")[0].payload
    assert ended["status"] == "limit" and ended["context_tokens"] == 4321
    assert ended["context_estimated"] is False
    session.close()


def test_chat_context_without_usage_is_marked_estimated():
    answer = sse(delta(content="Résultat."), delta("stop"))  # no `usage`
    session = _cloud_session("groq", _delegating_provider(answer), bricks=("subagent",))

    events = run(session, "Résume.")

    ended = of(events, "subagent_ended")[0].payload
    assert ended["status"] == "completed" and ended["context_estimated"] is True
    session.close()


def test_a_failed_delegation_counts_the_error_actually_reinjected():
    reads = [call("read_file", path="notes_reunion.txt")] * 4
    engine, session = sub_session([delegation(), *reads, "Voilà."])

    events = run(session, "Quelles décisions ?")

    ended = of(events, "subagent_ended")[0].payload
    main = of(events, "context_rendered", "main")[-1].payload
    (reinjected,) = _segments(main, "subagent_result")
    assert ended["result"] == reinjected["text"]
    assert ended["result"].startswith("Erreur : La délégation au sous-agent a échoué")
    assert ended["result_tokens"] == len(ended["result"].encode("utf-8"))
    assert ended["saved_tokens"] == 0
    session.close()
