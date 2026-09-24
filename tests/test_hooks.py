"""Stories 8 and 8b: hooks H1, H2, H3, H5 at the turn's points, decisions and effects (AD-13,
AD-14, AD-23), H5's human validation included."""

from __future__ import annotations

import json
import shutil
import time
from datetime import datetime
from types import SimpleNamespace

import httpx
import httpx2
import pytest
from fake_engine import CHATML, FakeEngine
from test_bricks import HEADERS, _client
from test_mcp import MSLEARN_TOOLS, McpWeb, enable, loop, mcp_session  # noqa: F401 - fixture
from test_mcp_lazy import exact
from test_tools import QWEN, _segments, call, web  # noqa: F401 - fixture
from test_turn import _run

from wavestack import config
from wavestack.bricks.registry import HOOKS
from wavestack.hooks import DEMO_HOOKS, Hook, HookContext, HookResult, ask, date_fr, guard
from wavestack.mcp import connection
from wavestack.mcp.servers import McpServer
from wavestack.net.factory import create_async_client
from wavestack.session.app_session import AppSession
from wavestack.tools.native import NATIVE_TOOLS, demo_dir
from wavestack.tools.parser import ToolCall
from wavestack.trace.journal import get_journal

WINDOW = 16384  # the fake engine counts one token per byte
SECRET = "confidentiel/budget_projet.txt"
BLOCKED = "Bloqué par le hook garde-fou"


def hooks_session(outputs=("Voilà.",), *, hooks=DEMO_HOOKS, memory=False, tools=True, **engine):
    engine.setdefault("template", QWEN.decode("utf-8"))
    engine.setdefault("architecture", "qwen35")
    fake = FakeEngine(outputs=list(outputs), **engine)
    session = AppSession(
        config.Config(values={"context": {"window": WINDOW, "near_limit_ratio": 0.8}}),
        engine_factory=lambda path, n_ctx: fake,
        hooks=hooks,
    )
    session.boot("fake.gguf").result()
    if memory:
        session.set_brick("short_memory", True)
    if tools:
        session.set_brick("tools", True)
    session.set_brick("hooks", True)
    session.join()
    return fake, session


def since(mark: int, kind: str) -> list:
    return [e for e in get_journal().events_since(mark) if e.kind == kind]


def decisions(events: dict) -> list[tuple[str, str, str]]:
    return [(d["hook"], d["point"], d["decision"]) for d in events.get("hook_decided", [])]


def check(events: dict, mark: int) -> None:
    """Every render: the sum equals the total, and no harness error."""
    for ctx in events["context_rendered"]:
        exact(ctx)
    assert since(mark, "harness_error") == []


def audit_lines() -> list[str]:
    return config.audit_path().read_text(encoding="utf-8").splitlines()


def fake_hooks(hook_id: str, point: str, decision: str, arguments=None) -> tuple[Hook, ...]:
    """The demo hooks, with one replaced by a test hook deciding `decision` at `point`."""
    result = HookResult(decision, "Hook de test.", arguments=arguments)
    fake = Hook(hook_id, frozenset({point}), lambda ctx: result)
    return tuple(fake if h.id == hook_id else h for h in DEMO_HOOKS)


# ---------- I/O matrix ----------


def test_activation_enables_three_hooks_of_four_and_draws_them_with_the_audit_log():
    mark = get_journal().last_seq()
    _, session = hooks_session(tools=False)

    card = next(
        b for b in since(mark, "bricks_changed")[-1].payload["bricks"] if b["id"] == "hooks"
    )
    assert card["available"] and card["category"] == "harness"
    # Q1 (8b): H5 starts disabled, « Hooks : 3 activés sur 4 ».
    assert [(o["id"], o["enabled"]) for o in card["options"]] == [(h, h != "h5") for h in HOOKS]
    assert card["options"][3]["label_fr"] == "Validation humaine"
    assert card["options"][0]["label_fr"] == "Garde-fou fichier sensible"
    arch = since(mark, "architecture_changed")[-1].payload
    nodes = {n["id"]: n for n in arch["nodes"]}
    assert [n for n in nodes if n.startswith("hooks.")] == ["hooks.h1", "hooks.h2", "hooks.h3"]
    assert {nodes[f"hooks.{h}"]["kind"] for h in ("h1", "h2", "h3")} == {"hook"}
    assert nodes["hooks.h1"]["detail_fr"].startswith("Avant l'exécution d'un outil")
    audit = nodes["file.audit"]
    assert audit["label_fr"] == "Journal d'audit" and audit["kind"] == "file"
    assert audit["detail_fr"] == str(config.audit_path())
    assert {"from": "hooks.h2", "to": "file.audit", "crosses_boundary": False} in arch["edges"]
    preview = since(mark, "context_preview")[-1].payload  # the gauge counts H3's text too
    (injection,) = _segments(preview, "hook_injection")
    assert injection["text"].startswith("Date et heure du poste : ")
    session.close()


def test_h1_blocks_the_confidential_file_and_the_turn_goes_on():
    engine, session = hooks_session([call("read_file", path=SECRET), "Je ne peux pas le lire."])
    mark = get_journal().last_seq()

    events = _run(session, "Quel est le budget du projet ?")

    assert ("h1", "before_tool", "block") in decisions(events)
    blocked = next(
        e for e in since(mark, "hook_decided") if e.payload["decision"] == "block"
    )  # the harness decided, on a step of its own
    assert (blocked.actor, blocked.brick, blocked.component) == ("harness", "hooks", "hooks.h1")
    assert blocked.payload["detail_fr"].startswith(BLOCKED)
    assert blocked.payload["point_fr"] == "Avant l'exécution d'un outil"
    assert "tool_started" not in events and "tool_ended" not in events
    (refusal,) = _segments(events["context_rendered"][1], "tool_result")
    assert refusal["text"].startswith(BLOCKED)
    assert (refusal["brick"], refusal["component"]) == ("hooks", "hooks.h1")
    assert "tool_call_malformed" not in events and "limit_reached" not in events  # no retry
    assert events["turn_ended"][0]["status"] == "completed"
    assert events["model_call_ended"][-1]["text"] == "Je ne peux pas le lire."
    check(events, mark)
    session.close()


@pytest.mark.parametrize(
    "path",
    [
        SECRET,
        "confidentiel",
        "./confidentiel/",
        "Confidentiel/../confidentiel/budget_projet.txt",
        "CONFIDENTIEL/budget_projet.txt",  # a case-insensitive filesystem reads it
    ],
)
def test_h1_resolves_the_path_as_read_file_does(path):
    spec = next(s for s in NATIVE_TOOLS if s.name == "read_file")
    ctx = HookContext("before_tool", "t1", call=ToolCall("read_file", {"path": path}), spec=spec)
    assert guard(ctx).decision == "block"


@pytest.mark.parametrize("path", ["../README.md", str(demo_dir() / SECRET)])
def test_h1_leaves_a_path_outside_the_demo_folder_to_the_confinement(path):
    spec = next(s for s in NATIVE_TOOLS if s.name == "read_file")
    ctx = HookContext("before_tool", "t1", call=ToolCall("read_file", {"path": path}), spec=spec)
    assert guard(ctx) is None


def test_h1_is_not_concerned_by_a_tool_without_path():
    spec = next(s for s in NATIVE_TOOLS if s.name == "calculator")
    ctx = HookContext(
        "before_tool", "t1", call=ToolCall("calculator", {"expression": "1"}), spec=spec
    )
    assert guard(ctx) is None


def test_h1_lets_an_ordinary_file_through():
    _, session = hooks_session([call("read_file", path="notes_reunion.txt"), "Voilà."])
    mark = get_journal().last_seq()

    events = _run(session, "Résume les notes de réunion.")

    assert ("h1", "before_tool", "allow") in decisions(events)
    assert events["tool_ended"][0]["status"] == "ok"
    check(events, mark)
    session.close()


def test_h1_off_the_confidential_file_is_read_confinement_stays():
    _, session = hooks_session([call("read_file", path=SECRET), call("read_file", path="../x")])
    session.set_hook("h1", False)

    events = _run(session, "Quel est le budget du projet ?")

    assert all(hook != "h1" for hook, _, _ in decisions(events))
    first, second = events["tool_ended"][:2]
    assert first["status"] == "ok" and first["result"]
    assert second["status"] == "error" and "sort du dossier" in second["error_fr"]  # AD-14
    session.close()


def test_h2_logs_calls_tool_and_end_in_order():
    _, session = hooks_session([call("calculator", expression="2+2"), "Cela fait 4."])
    mark = get_journal().last_seq()

    events = _run(session, "Combien font 2 + 2 ?")

    lines = audit_lines()
    assert [line.split(" | ")[2] for line in lines] == [
        "appel au modèle",
        "appel d'outil",
        "appel au modèle",
        "fin du tour",
    ]
    assert all(line.split(" | ")[1] == "t1" for line in lines)
    assert lines[1].endswith('calculator {"expression": "2+2"} | ok')
    assert lines[-1].endswith("| completed")
    applied = since(mark, "effect_applied")
    assert [e.component for e in applied] == ["file.audit", "file.audit"]
    assert [line for e in applied for line in e.payload["lines"]] == lines
    points = [p for h, p, _ in decisions(events) if h == "h2"]
    assert points == ["after_tool", "on_turn_end"]
    check(events, mark)
    session.close()


def test_h2_logs_a_blocked_call():
    _, session = hooks_session([call("read_file", path=SECRET), "Non."])

    _run(session, "Quel est le budget du projet ?")

    blocked = [line for line in audit_lines() if "appel bloqué par H1" in line]
    assert len(blocked) == 1 and blocked[0].endswith("| bloqué")
    session.close()


def test_h2_logs_a_refused_call():
    _, session = hooks_session([call("get_weather", city="Paris"), "Non."])

    _run(session, "Quel temps fait-il ?")

    (refused,) = [line for line in audit_lines() if "appel d'outil refusé" in line]
    assert "get_weather" in refused and refused.endswith("| refusé")
    session.close()


def test_h2_write_failure_is_traced_and_the_turn_goes_on():
    config.audit_path().mkdir(parents=True)  # a folder in its place: the append fails
    _, session = hooks_session(tools=False)
    mark = get_journal().last_seq()

    events = _run(session, "Bonjour")

    (error,) = [e.payload for e in since(mark, "harness_error")]
    assert "journal d'audit" in error["message_fr"]
    assert "effect_applied" not in events
    assert events["turn_ended"][0]["status"] == "completed"
    session.close()


def test_audit_endpoint_reads_the_whole_log():
    _, session = hooks_session(tools=False)
    client = _client(session)

    empty = client.get("/api/audit").json()
    assert empty == {"path": str(config.audit_path()), "text": ""}
    _run(session, "Bonjour")
    text = client.get("/api/audit").json()["text"]
    assert text.splitlines() == audit_lines() and "fin du tour" in text
    session.close()


def test_audit_endpoint_explains_an_unreadable_log():
    config.audit_path().mkdir(parents=True)  # a folder in its place
    _, session = hooks_session(tools=False)

    response = _client(session).get("/api/audit")

    assert response.status_code == 500 and "illisible" in response.json()["detail"]
    session.close()


def test_h3_adds_its_text_before_the_message_and_keeps_it_in_the_history():
    _, session = hooks_session([call("calculator", expression="1+1"), "2.", "Encore."], memory=True)
    mark = get_journal().last_seq()

    first = _run(session, "Combien font 1 + 1 ?")
    second = _run(session, "Et ensuite ?")

    injections = [_segments(ctx, "hook_injection") for ctx in first["context_rendered"]]
    assert [[s["text"] for s in i] for i in injections] == [[injections[0][0]["text"]]] * 2
    (injection,) = injections[0]  # computed once, the same for every call of the turn
    assert injection["text"].startswith("Date et heure du poste : ")
    assert "Règles de la mission" in injection["text"]
    assert (injection["brick"], injection["component"]) == ("hooks", "hooks.h3")
    kinds = [s["kind"] for s in first["context_rendered"][0]["segments"]]
    assert kinds.index("hook_injection") == kinds.index("user_message") - 2  # template between
    ctx = second["context_rendered"][0]
    assert injection["text"] in [s["text"] for s in _segments(ctx, "history")]
    assert len(_segments(ctx, "hook_injection")) == 1
    assert ("h3", "on_user_message", "modify") in decisions(first)
    check(first, mark)
    exact(ctx)
    session.close()


def test_h3_date_format():
    assert date_fr(datetime(2026, 9, 24, 10, 12)) == "jeudi 24 septembre 2026, 10 h 12"
    assert date_fr(datetime(2026, 1, 5, 9, 5)) == "lundi 5 janvier 2026, 9 h 05"


def test_decision_not_allowed_at_a_point_is_traced_and_counts_as_allow():
    hooks = fake_hooks("h2", "after_tool", "block")
    _, session = hooks_session([call("calculator", expression="2+2"), "4."], hooks=hooks)
    mark = get_journal().last_seq()

    events = _run(session, "Combien font 2 + 2 ?")

    (error,) = [e.payload for e in since(mark, "harness_error")]
    assert "« block »" in error["message_fr"] and "after_tool" in error["message_fr"]
    assert ("h2", "after_tool", "allow") in decisions(events)
    assert events["turn_ended"][0]["status"] == "completed"
    session.close()


def test_before_tool_modify_replaces_the_arguments():
    hooks = fake_hooks("h1", "before_tool", "modify", arguments={"expression": "3+3"})
    _, session = hooks_session([call("calculator", expression="2+2"), "6."], hooks=hooks)
    mark = get_journal().last_seq()

    events = _run(session, "Combien font 2 + 2 ?")

    assert ("h1", "before_tool", "modify") in decisions(events)
    assert events["tool_started"][0]["arguments"] == {"expression": "3+3"}
    assert events["tool_ended"][0]["result"] == "6"
    check(events, mark)
    session.close()


def test_a_failing_hook_is_traced_and_the_turn_goes_on():
    def broken(ctx):
        raise RuntimeError("hook en panne")

    hooks = (Hook("h1", frozenset({"before_model_call"}), broken), *DEMO_HOOKS[1:])
    _, session = hooks_session(tools=False, hooks=hooks)
    mark = get_journal().last_seq()

    events = _run(session, "Bonjour")

    (error,) = [e.payload for e in since(mark, "harness_error")]
    assert "a échoué" in error["message_fr"] and "hook en panne" in error["cause"]
    assert events["turn_ended"][0]["status"] == "completed"
    session.close()


@pytest.mark.parametrize(
    "broken",
    [
        lambda path: path.unlink(),
        lambda path: path.write_text("hooks: {}", encoding="utf-8"),  # no text, no points
    ],
)
def test_invalid_hooks_content_makes_the_brick_unavailable(tmp_path, monkeypatch, broken):
    content = tmp_path / "content"
    shutil.copytree(config.content_dir(), content)
    broken(content / "hooks.yaml")
    monkeypatch.setattr(config, "content_dir", lambda: content)
    mark = get_journal().last_seq()

    _, session = hooks_session(tools=False)

    assert since(mark, "harness_error")
    card = next(
        b for b in since(mark, "bricks_changed")[-1].payload["bricks"] if b["id"] == "hooks"
    )
    assert card["wanted"] and not card["available"]
    assert "content/hooks.yaml" in card["reason_fr"]
    session.close()


def test_block_at_turn_end_keeps_a_failed_status():
    _, session = hooks_session(
        tools=False, hooks=fake_hooks("h1", "on_turn_end", "block"), fail=True
    )

    events = _run(session, "Bonjour")

    assert events["turn_ended"][0]["status"] == "error"
    session.close()


def test_block_before_the_model_call_ends_the_turn_without_calling_it():
    engine, session = hooks_session(hooks=fake_hooks("h1", "before_model_call", "block"))

    events = _run(session, "Bonjour")

    assert ("h1", "before_model_call", "block") in decisions(events)
    assert "model_call_started" not in events and engine.calls == []
    assert events["turn_ended"][0]["status"] == "blocked"
    assert session.build_turn_state().history == ()
    session.close()


def test_block_at_turn_end_keeps_the_answer_out_of_the_history():
    engine, session = hooks_session(hooks=fake_hooks("h1", "on_turn_end", "block"), memory=True)

    events = _run(session, "Bonjour")

    assert len(engine.calls) == 1 and events["turn_ended"][0]["status"] == "blocked"
    assert session.build_turn_state().history == ()
    session.close()


def test_brick_checked_then_unchecked_is_the_bare_llm_byte_for_byte():
    engine, session = hooks_session(tools=False, template=CHATML, architecture="fake")
    session.set_brick("hooks", False)
    mark = get_journal().last_seq()

    events = _run(session, "Bonjour")

    assert engine.calls[0] == list(b"<|im_start|>user\nBonjour<|im_end|>\n<|im_start|>assistant\n")
    assert "hook_decided" not in events
    assert since(mark, "harness_error") == []
    session.close()


def test_hook_sub_option_is_pending_kept_across_the_brick_and_http():
    _, session = hooks_session(tools=False)
    client = _client(session)
    mark = get_journal().last_seq()

    response = client.post(
        "/api/intentions/hook", json={"hook": "h2", "enabled": False}, headers=HEADERS
    )
    assert response.json() == {"accepted": True}
    unknown = client.post(
        "/api/intentions/hook", json={"hook": "h9", "enabled": True}, headers=HEADERS
    )
    assert unknown.status_code == 404
    card = next(
        b for b in since(mark, "bricks_changed")[-1].payload["bricks"] if b["id"] == "hooks"
    )
    assert card["pending"] and [o["enabled"] for o in card["options"]] == [True, False, True, False]
    nodes = {n["id"] for n in since(mark, "architecture_changed")[-1].payload["nodes"]}
    assert "hooks.h2" not in nodes and "file.audit" not in nodes
    session.set_brick("hooks", False)
    session.set_brick("hooks", True)  # Q1: the choices stay
    assert session.build_turn_state().hooks == ("h1", "h3")
    session.close()


# ---------- story 8b: H5, human validation before any network call ----------

ASKED = "awaiting_human"
HOLIDAYS = {"2026-01-01": "1er janvier"}
HOLIDAYS_HOST = "calendrier.api.gouv.fr"


def h5_session(outputs, tool="public_holidays", *, h5=True):
    _, session = hooks_session(outputs)
    session.set_tool(tool, True)
    if h5:
        session.set_hook("h5", True)
    session.join()
    return session


def wait_asked(mark: int, n: int = 1):
    """The `n`-th `approval_requested` since `mark`, once the session waits for it."""
    deadline = time.monotonic() + 30
    while time.monotonic() < deadline:
        waiting = [e for e in since(mark, "session_state") if e.payload["state"] == ASKED]
        if len(waiting) >= n:
            return since(mark, "approval_requested")[n - 1]
        time.sleep(0.01)
    raise AssertionError("no validation asked")


def run_asked(session, message: str, *answers) -> dict[str, list[dict]]:
    """Send `message`; each `answer(asked)` runs on this thread once the n-th validation
    waits, as the user's click would; then waits for the turn. Payloads by kind."""
    mark = get_journal().last_seq()
    session.send(message)
    for n, answer in enumerate(answers, 1):
        answer(wait_asked(mark, n))
    session.join()
    events: dict[str, list[dict]] = {}
    for envelope in get_journal().events_since(mark):
        events.setdefault(envelope.kind, []).append(envelope.payload)
    return events


def answer(session, approved: bool, disable_hook: bool = False):
    return lambda asked: session.answer_approval(
        asked.payload["approval_id"], approved, disable_hook
    )


def test_h5_approved_the_request_leaves_only_after_the_click(web):  # noqa: F811
    sent = web(lambda r: httpx.Response(200, json=HOLIDAYS))
    session = h5_session([call("public_holidays", year="2026"), "Le 1er janvier."])
    mark = get_journal().last_seq()
    before_click = []

    def look_then_approve(asked):
        before_click.extend(sent)
        assert session.state == ASKED
        answer(session, True)(asked)

    events = run_asked(session, "Jours fériés 2026 ?", look_then_approve)

    assert before_click == []  # AD-13: nothing leaves before the answer
    assert ("h5", "before_tool", "ask_human") in decisions(events)
    (asked,) = since(mark, "approval_requested")
    preview = session._registry.get("public_holidays").preview(year=2026)
    assert asked.payload == {
        "approval_id": "t1.a1",
        "tool": "public_holidays",
        "destination": HOLIDAYS_HOST,
        "preview": preview,
    }
    assert (asked.brick, asked.component) == ("hooks", "hooks.h5")
    decided = next(e for e in since(mark, "hook_decided") if e.payload["hook"] == "h5")
    (resolved,) = since(mark, "approval_resolved")
    assert asked.step_id == decided.step_id == resolved.step_id  # the hook's own step
    assert resolved.actor == "user"
    assert resolved.payload == {
        "approval_id": "t1.a1",
        "decision": "approved",
        "hook_disabled": False,
    }
    assert [p["state"] for p in events["session_state"]] == ["turn", ASKED, "turn", "idle"]
    assert len(sent) == 1 and events["tool_ended"][0]["status"] == "ok"
    (outbound,) = events["outbound_request"]
    assert {k: outbound[k] for k in ("method", "url", "body")} == preview
    assert ("h2", "after_tool", "allow") in decisions(events)
    assert events["turn_ended"][0]["status"] == "completed"
    (line,) = [line for line in audit_lines() if "validation humaine" in line]
    assert line.endswith(f"| validation humaine | public_holidays vers {HOLIDAYS_HOST} | autorisé")
    check(events, mark)
    session.close()


def test_h5_refused_nothing_leaves_and_the_refusal_is_reinjected(web):  # noqa: F811
    sent = web(lambda r: httpx.Response(200, json=HOLIDAYS))
    session = h5_session([call("public_holidays", year="2026"), "Je n'ai pas pu vérifier."])
    mark = get_journal().last_seq()

    events = run_asked(session, "Jours fériés 2026 ?", answer(session, False))

    assert sent == [] and "outbound_request" not in events
    assert "tool_started" not in events and "tool_ended" not in events
    assert events["approval_resolved"][0]["decision"] == "refused"
    (refusal,) = _segments(events["context_rendered"][1], "tool_result")
    assert refusal["text"] == (
        "Refusé par l'utilisateur (validation humaine) : l'appel à « public_holidays » vers "
        f"{HOLIDAYS_HOST} n'a pas été envoyé."
    )
    assert (refusal["brick"], refusal["component"]) == ("hooks", "hooks.h5")
    assert "tool_call_malformed" not in events and "limit_reached" not in events  # no retry
    assert events["turn_ended"][0]["status"] == "completed"
    assert events["model_call_ended"][-1]["text"] == "Je n'ai pas pu vérifier."
    (line,) = [line for line in audit_lines() if "validation humaine" in line]
    assert line.endswith(f"| validation humaine | public_holidays vers {HOLIDAYS_HOST} | refusé")
    check(events, mark)
    session.close()


def test_h5_approve_and_stop_asking_disables_it_for_the_rest_of_the_turn(web):  # noqa: F811
    sent = web(lambda r: httpx.Response(200, json=HOLIDAYS))
    outputs = [call("public_holidays", year="2026"), call("public_holidays", year="2027"), "Ok."]
    session = h5_session(outputs)
    mark = get_journal().last_seq()

    events = run_asked(session, "Jours fériés 2026 et 2027 ?", answer(session, True, True))

    assert len(events["approval_requested"]) == 1 and len(sent) == 2
    assert events["approval_resolved"][0]["hook_disabled"] is True
    assert [p["hook"] for p in events["hook_decided"]].count("h5") == 1
    card = next(b for b in events["bricks_changed"][-1]["bricks"] if b["id"] == "hooks")
    assert [o["enabled"] for o in card["options"]] == [True, True, True, False]
    assert not card["pending"]  # no « Prend effet au prochain tour »
    nodes = {n["id"] for n in events["architecture_changed"][-1]["nodes"]}
    assert "hooks.h5" not in nodes
    assert session.build_turn_state().hooks == ("h1", "h2", "h3")
    check(events, mark)
    session.set_hook("h5", True)  # the next turn asks again: nothing left switched off
    session._engine.outputs += [call("public_holidays", year="2028"), "Ok."]
    again = run_asked(session, "Et 2028 ?", answer(session, True))
    assert len(again["approval_requested"]) == 1 and len(sent) == 3
    session.close()


def test_h5_stop_while_waiting_cancels_and_sends_nothing(web):  # noqa: F811
    sent = web(lambda r: httpx.Response(200, json=HOLIDAYS))
    session = h5_session([call("public_holidays", year="2026"), "Jamais lu."])

    events = run_asked(session, "Jours fériés 2026 ?", lambda asked: session.stop())

    assert sent == [] and "tool_started" not in events
    assert events["approval_resolved"][0]["decision"] == "cancelled"
    assert events["turn_ended"][0]["status"] == "cancelled"
    assert session.state == "idle"
    assert any(line.endswith("| annulé") for line in audit_lines())
    session.close()


def test_h5_stop_just_before_the_wait_cancels_without_waiting(web):  # noqa: F811
    sent = web(lambda r: httpx.Response(200, json=HOLIDAYS))
    session = h5_session([call("public_holidays", year="2026"), "Jamais lu."])

    def stop_when_asking(envelope) -> None:
        if envelope.kind == "hook_decided" and envelope.payload["decision"] == "ask_human":
            session.stop()  # still in `turn`: the wait must not begin

    get_journal().subscribe(stop_when_asking)
    try:
        events = _run(session, "Jours fériés 2026 ?")
    finally:
        get_journal().unsubscribe(stop_when_asking)

    assert events["approval_resolved"][0]["decision"] == "cancelled"
    assert events["turn_ended"][0]["status"] == "cancelled"
    assert ASKED not in [p["state"] for p in events["session_state"]]
    assert sent == [] and "tool_started" not in events
    session.close()


def test_h5_asks_with_the_host_the_sender_parses(web):  # noqa: F811
    sent = web(lambda r: httpx.Response(200, text="page"))
    url = "https://x]@fr.wikipedia.org/"  # `urlsplit` rejects it, httpx sends it
    session = h5_session([call("fetch_page", url=url), "Non."], "fetch_page")
    before_answer = []

    def look_then_refuse(asked):
        before_answer.extend(sent)
        answer(session, False)(asked)

    events = run_asked(session, "Lis cette page", look_then_refuse)

    (asked,) = events["approval_requested"]
    assert asked["destination"] == "fr.wikipedia.org"
    assert before_answer == [] and sent == []
    assert "harness_error" not in events  # H5 did not fail open
    session.close()


def test_h5_close_while_waiting_never_hangs(web):  # noqa: F811
    web(lambda r: httpx.Response(200, json=HOLIDAYS))
    session = h5_session([call("public_holidays", year="2026"), "Jamais lu."])
    mark = get_journal().last_seq()
    session.send("Jours fériés 2026 ?")
    wait_asked(mark)

    session.close()  # through `stop()`

    assert since(mark, "turn_ended")[0].payload["status"] == "cancelled"


def test_h5_http_first_answer_wins_and_state_shows_the_pending_validation(web):  # noqa: F811
    web(lambda r: httpx.Response(200, json=HOLIDAYS))
    session = h5_session([call("public_holidays", year="2026"), "Voilà."])
    client = _client(session)
    mark = get_journal().last_seq()
    assert client.get("/api/state").json()["pending_approval"] is None
    session.send("Jours fériés 2026 ?")
    asked = wait_asked(mark)

    def post(**body):
        return client.post("/api/intentions/approval", json=body, headers=HEADERS)

    assert client.get("/api/state").json()["pending_approval"] == asked.payload
    unknown = post(approval_id="t9.a1", approved=True)
    assert unknown.status_code == 409 and "t9.a1" in unknown.json()["detail"]
    approval_id = asked.payload["approval_id"]
    first = post(approval_id=approval_id, approved=False, disable_hook=True)
    second = post(approval_id=approval_id, approved=True)
    session.join()

    assert first.status_code == 200 and first.json() == {"accepted": True}
    assert second.status_code == 409 and second.json()["detail"]
    (resolved,) = since(mark, "approval_resolved")
    # The first answer wins; `disable_hook` only counts with `approved`.
    assert resolved.payload["decision"] == "refused" and not resolved.payload["hook_disabled"]
    assert "h5" in session.build_turn_state().hooks
    assert client.get("/api/state").json()["pending_approval"] is None
    assert post(approval_id=approval_id, approved=True).status_code == 409  # out of any wait
    session.close()


def test_h5_host_outside_the_list_is_left_to_the_executor(web):  # noqa: F811
    sent = web(lambda r: httpx.Response(200, text="page"))
    session = h5_session([call("fetch_page", url="https://exemple.com"), "Non."], "fetch_page")
    mark = get_journal().last_seq()

    events = _run(session, "Lis https://exemple.com")

    assert "approval_requested" not in events and sent == []
    assert all(hook != "h5" for hook, _, _ in decisions(events))
    assert events["tool_ended"][0]["status"] == "error"
    assert "Adresse refusée" in events["tool_ended"][0]["error_fr"]
    check(events, mark)
    session.close()


def test_h5_does_not_ask_for_a_local_tool():
    session = h5_session([call("get_datetime"), "Il est midi."], "get_datetime")
    mark = get_journal().last_seq()

    events = _run(session, "Quelle heure est-il ?")

    assert "approval_requested" not in events
    assert all(hook != "h5" for hook, _, _ in decisions(events))
    assert events["tool_ended"][0]["status"] == "ok"
    check(events, mark)
    session.close()


def test_h5_off_the_network_call_leaves_without_asking(web):  # noqa: F811
    sent = web(lambda r: httpx.Response(200, json=HOLIDAYS))
    session = h5_session([call("public_holidays", year="2026"), "Voilà."], h5=False)

    events = _run(session, "Jours fériés 2026 ?")

    assert "approval_requested" not in events and len(sent) == 1
    session.close()


def test_h5_public_mcp_preview_is_the_tools_call_body(loop, monkeypatch):  # noqa: F811
    server = McpWeb(MSLEARN_TOOLS)
    monkeypatch.setattr(
        connection,
        "create_async_client",
        lambda **kw: create_async_client(transport=httpx2.MockTransport(server), **kw),
    )
    outputs = [call("mslearn__microsoft_docs_search", query="accès conditionnel"), "Voilà."]
    session = mcp_session(loop, outputs)
    session.set_mcp_server("local", False)
    enable(session, "mslearn")
    session.set_brick("hooks", True)
    session.set_hook("h5", True)
    session.join()
    posted = []

    def look_then_approve(asked):
        posted.extend(r for r in server.sent if b"tools/call" in r.content)
        answer(session, True)(asked)

    events = run_asked(session, "Accès conditionnel ?", look_then_approve)

    assert posted == []
    (asked,) = events["approval_requested"]
    url = session._mcp_servers["mslearn"].url
    assert asked["destination"] == httpx.URL(url).host
    assert (asked["preview"]["method"], asked["preview"]["url"]) == ("POST", url)
    body = json.loads(asked["preview"]["body"])
    assert body == {
        "jsonrpc": "2.0",
        "method": "tools/call",
        "params": {
            "name": "microsoft_docs_search",  # the server's own name
            "arguments": {"query": "accès conditionnel"},
            "_meta": {},
        },
    }
    (outbound,) = [p for p in events["outbound_request"] if "tools/call" in p["body"]]
    sent_body = json.loads(outbound["body"])
    assert {k: v for k, v in sent_body.items() if k != "id"} == body  # but the JSON-RPC id
    assert events["tool_ended"][0]["status"] == "ok"
    session.close()


def test_h5_is_not_concerned_by_the_local_mcp_server():
    _, session = hooks_session(tools=False)
    tool = SimpleNamespace(name="define_term", input_schema={}, description="Définit un terme.")
    spec = session._mcp_spec(McpServer("local", None), None, tool)
    ctx = HookContext("before_tool", "t1", call=ToolCall("local__define_term", {}), spec=spec)
    assert spec.preview is None and ask(ctx) is None
    session.close()
