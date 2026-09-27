"""Story 13: the reasoning brick (CAP-10, FR-9, AD-4, AD-6, AD-9, AD-12).

Local turns run on `FakeEngine` with the Qwen3.5 template (`enable_thinking`); cloud turns
on an `httpx.MockTransport` provider: nothing leaves the machine.
"""

from __future__ import annotations

import json

import pytest
from fake_engine import CHATML, FakeEngine, booted_session
from pydantic import SecretStr
from test_cloud import SENTINEL, Provider, delta, sse
from test_tools import QWEN, call
from test_turn import _run

from wavestack import config
from wavestack.session.app_session import AppSession
from wavestack.trace.journal import get_journal

NO_REASONING = "Indisponible : le modèle actif ne sait pas raisonner."


class RecordingEngine(FakeEngine):
    """Records the `max_tokens` of each call (the output reserve, AD-9)."""

    def __init__(self, **kwargs) -> None:
        super().__init__(**kwargs)
        self.max_tokens: list[int] = []

    def complete(self, prompt_ids, stop, max_tokens, cancel):
        self.max_tokens.append(max_tokens)
        yield from super().complete(prompt_ids, stop, max_tokens, cancel)


def _qwen(outputs: list[str]) -> tuple[RecordingEngine, AppSession]:
    engine = RecordingEngine(outputs=outputs, template=QWEN.decode("utf-8"), architecture="qwen35")
    return engine, booted_session(engine)


def _latest(kind: str, mark: int = 0) -> dict:
    return [e.payload for e in get_journal().events_since(mark) if e.kind == kind][-1]


def _card(mark: int = 0) -> dict:
    cards = _latest("bricks_changed", mark)["bricks"]
    return next(c for c in cards if c["id"] == "reasoning")


def _prompt(ctx: dict) -> str:
    return "".join(s["text"] for s in ctx["segments"])


# ---------- local ----------


def test_local_brick_on_thinks_with_the_reasoning_reserve():
    engine, session = _qwen(["Deux étapes : 14 h 47 + 2 h 38.\n</think>\n\nIl arrive à 17 h 25."])
    session.set_brick("reasoning", True)
    session.join()
    assert _card()["available"] and _card()["always_fr"] is None

    events = _run(session, "À quelle heure ?")

    ctx = events["context_rendered"][0]
    assert _prompt(ctx).endswith("<|im_start|>assistant\n<think>\n")  # enable_thinking=True
    assert ctx["reserve"] == 1536 and ctx["usable"] == 4096 - 1536
    assert engine.max_tokens == [1536]
    channels = [d["channel"] for d in events["model_delta"]]
    assert channels[0] == "reasoning" and channels[-1] == "text"
    ended = events["model_call_ended"][0]
    assert ended["reasoning"].strip() == "Deux étapes : 14 h 47 + 2 h 38."
    assert ended["text"].strip() == "Il arrive à 17 h 25."
    assert events["turn_ended"][0]["status"] == "completed"
    session.close()


def test_local_brick_off_keeps_thinking_off_and_the_plain_reserve():
    engine, session = _qwen(["Il arrive à 17 h 25."])

    events = _run(session, "À quelle heure ?")

    ctx = events["context_rendered"][0]
    assert _prompt(ctx).endswith("<think>\n\n</think>\n\n")  # enable_thinking=False
    assert ctx["reserve"] == 512 and engine.max_tokens == [512]
    session.close()


def test_local_model_without_reasoning_variable_is_unavailable_with_the_reason():
    engine = RecordingEngine(output="Bonjour !", template=CHATML)
    session = booted_session(engine)
    mark = get_journal().last_seq()
    session.set_brick("reasoning", True)
    session.join()

    card = _card(mark)
    assert card["wanted"] and not card["available"]
    assert card["reason_fr"].startswith(NO_REASONING) and "gabarit" in card["reason_fr"]
    events = _run(session, "Bonjour")
    assert events["context_rendered"][0]["reserve"] == 512 and engine.max_tokens == [512]
    session.close()


def test_toggling_the_brick_recomputes_the_preview():
    _, session = _qwen(["ok"])
    mark = get_journal().last_seq()
    session.set_brick("reasoning", True)
    session.join()
    on = _latest("context_preview", mark)
    mark = get_journal().last_seq()
    session.set_brick("reasoning", False)
    session.join()
    off = _latest("context_preview", mark)

    assert (on["reserve"], on["usable"]) == (1536, 4096 - 1536)
    assert (off["reserve"], off["usable"]) == (512, 4096 - 512)
    assert _prompt(on).endswith("<think>\n") and _prompt(off).endswith("</think>\n\n")
    session.close()


def test_the_turn_reasoning_is_attributed_to_the_model_output():
    engine, session = _qwen(
        [
            "Il faut calculer.\n</think>\n\n" + call("calculator", expression="12*37"),
            "C'est fait.\n</think>\n\nCela fait 444.",
        ]
    )
    session.set_brick("tools", True)
    session.set_brick("reasoning", True)
    session.join()

    events = _run(session, "Combien font 12 × 37 ?")

    second = events["context_rendered"][1]
    turn = [s for s in second["segments"] if s["kind"] == "assistant_turn"]
    assert any(s["text"] == "Il faut calculer." for s in turn)
    template = "".join(s["text"] for s in second["segments"] if s["kind"] == "template")
    assert "Il faut calculer." not in template
    assert sum(s["tokens"] for s in second["segments"]) == second["used"]
    assert [list(_prompt(c).encode()) for c in events["context_rendered"]] == engine.calls
    assert events["tool_ended"][0]["result"] == "444"
    session.close()


def test_a_tool_call_written_in_the_reasoning_is_never_run():
    reasoning = "Je pourrais écrire " + call("calculator", expression="1+1") + " mais non."
    engine, session = _qwen([reasoning + "\n</think>\n\nRéponse sans outil."])
    session.set_brick("tools", True)
    session.set_brick("reasoning", True)
    session.join()

    events = _run(session, "Bonjour")

    assert "tool_started" not in events and "tool_call_malformed" not in events
    assert len(engine.calls) == 1
    assert events["model_call_ended"][0]["tool_calls"] == []
    assert events["turn_ended"][0]["status"] == "completed"
    session.close()


# ---------- cloud ----------


def _cloud(entry: config.CloudModel, provider: Provider, *bricks: str) -> AppSession:
    entry = entry.model_copy(update={"min_interval_s": None})  # no spacing wait in tests
    config.write_api_key(entry.id, entry.host, SecretStr(SENTINEL))
    session = AppSession(config.load_config(), cloud_factory=provider.factory)
    session.boot_cloud(entry).result()
    for brick in bricks:
        session.set_brick(brick, True)
    session.join()
    return session


def _preset(model_id: str) -> config.CloudModel:
    return config.load_config().cloud_model(model_id)


def _bodies(provider: Provider) -> list[dict]:
    return [json.loads(r.content) for r in provider.requests]


def _usage(prompt: int = 40) -> dict:
    return {**delta("stop"), "usage": {"prompt_tokens": prompt, "completion_tokens": 3}}


TEXT = sse(delta(content="Bonjour."), _usage())


def test_cloud_declared_reasoning_sends_on_then_off():
    provider = Provider(TEXT)
    session = _cloud(_preset("mistral"), provider, "reasoning")
    assert _card()["available"] and _card()["always_fr"] is None

    on = _run(session, "Bonjour")
    session.set_brick("reasoning", False)
    session.join()
    off = _run(session, "Encore")

    first, second = _bodies(provider)
    assert first["reasoning_effort"] == "high" and first["max_tokens"] == 1536
    assert second["reasoning_effort"] == "none" and second["max_tokens"] == 512
    assert on["context_rendered"][0]["reserve"] == 1536
    assert on["context_reconciled"][0]["reserve"] == 1536
    assert off["context_rendered"][0]["reserve"] == 512
    session.close()


def test_cloud_model_that_always_reasons_keeps_the_reserve_brick_off():
    provider = Provider(TEXT)
    session = _cloud(_preset("groq"), provider)

    card = _card()
    assert not card["wanted"] and card["available"]
    assert card["always_fr"].startswith("Toujours active pour ce modèle")
    events = _run(session, "Bonjour")

    body = _bodies(provider)[0]
    assert body["reasoning_effort"] == "low" and body["max_tokens"] == 1536
    assert events["context_rendered"][0]["reserve"] == 1536
    session.close()


def test_cloud_model_without_reasoning_declared_is_unavailable():
    provider = Provider(TEXT)
    session = _cloud(_preset("mistral").model_copy(update={"reasoning": None}), provider)
    mark = get_journal().last_seq()
    session.set_brick("reasoning", True)
    session.join()

    card = _card(mark)
    assert not card["available"] and card["reason_fr"].startswith(NO_REASONING)
    assert "« mistral » ne déclare pas de raisonnement" in card["reason_fr"]
    _run(session, "Bonjour")
    body = _bodies(provider)[0]
    assert "reasoning_effort" not in body and body["max_tokens"] == 512
    session.close()


def _thinking(text: str) -> dict:
    return delta(content=[{"type": "thinking", "thinking": [{"type": "text", "text": text}]}])


TOOL_WITH_BLOCKS = sse(
    _thinking("Il faut l'heure."),
    delta(
        tool_calls=[
            {
                "index": 0,
                "id": "call_1",
                "type": "function",
                "function": {"name": "get_datetime", "arguments": "{}"},
            }
        ]
    ),
    {**delta("tool_calls"), "usage": {"prompt_tokens": 50, "completion_tokens": 5}},
)
TOOL_WITH_FIELD = sse(
    delta(reasoning="Il faut l'heure."),
    delta(
        tool_calls=[
            {
                "index": 0,
                "id": "call_1",
                "type": "function",
                "function": {"name": "get_datetime", "arguments": "{}"},
            }
        ]
    ),
    {**delta("tool_calls"), "usage": {"prompt_tokens": 50, "completion_tokens": 5}},
)
TEXT_WITH_BLOCKS = sse(
    _thinking("Lire l'outil."),
    delta(content=[{"type": "text", "text": "Il est 9 h."}]),
    _usage(60),
)
TEXT_WITH_FIELD = sse(delta(reasoning="Lire l'outil."), delta(content="Il est 9 h."), _usage(60))
TOOL_WITH_TAGS = sse(
    delta(content="<think>Il faut l'heure.</think>"),
    delta(
        tool_calls=[
            {
                "index": 0,
                "id": "call_1",
                "type": "function",
                "function": {"name": "get_datetime", "arguments": "{}"},
            }
        ]
    ),
    {**delta("tool_calls"), "usage": {"prompt_tokens": 50, "completion_tokens": 5}},
)
TEXT_WITH_TAGS = sse(delta(content="<think>Lire l'outil.</think>Il est 9 h."), _usage(60))
STREAMS = {
    "content_blocks": (TOOL_WITH_BLOCKS, TEXT_WITH_BLOCKS, TEXT),
    "field": (TOOL_WITH_FIELD, TEXT_WITH_FIELD, TEXT),
    "think_tags": (TOOL_WITH_TAGS, TEXT_WITH_TAGS, TEXT),
}


def _assistant(body: dict) -> list[dict]:
    return [m for m in body["messages"] if m["role"] == "assistant"]


@pytest.mark.parametrize(
    ("preset", "form"),
    [("mistral", "content_blocks"), ("groq", "field"), ("mistral", "think_tags")],
)
def test_resend_sends_the_reasoning_back_in_the_declared_form(preset, form):
    entry = _preset(preset)
    reasoning = entry.reasoning.model_copy(update={"resend": True, "format": form})
    entry = entry.model_copy(update={"reasoning": reasoning})
    provider = Provider(*STREAMS[form])
    session = _cloud(entry, provider, "tools", "short_memory", "reasoning")

    first = _run(session, "Quelle heure est-il ?")
    later = _run(session, "Merci")

    in_turn = _assistant(_bodies(provider)[1])[0]
    if form == "content_blocks":
        assert in_turn["content"] == [
            {"type": "thinking", "thinking": [{"type": "text", "text": "Il faut l'heure."}]}
        ]
    elif form == "field":
        assert in_turn["reasoning"] == "Il faut l'heure." and "content" not in in_turn
    else:
        assert in_turn["content"] == "<think>Il faut l'heure.</think>"
    turn = [s for s in first["context_rendered"][1]["segments"] if s["kind"] == "assistant_turn"]
    assert any("Il faut l'heure." in s["text"] for s in turn)
    # The next turn: the past answer's reasoning goes back too, counted as history.
    history = " ".join(
        s["text"] for s in later["context_rendered"][0]["segments"] if s["kind"] == "history"
    )
    assert "Il faut l'heure." in history and "Lire l'outil." in history
    body = later["context_rendered"][0]["body"]
    assert body == provider.requests[2].content.decode("utf-8")
    # The past answer, in the form received: the thinking before the text (review item 3, 15).
    past = _assistant(_bodies(provider)[2])[-1]
    if form == "content_blocks":
        assert past["content"] == [
            {"type": "thinking", "thinking": [{"type": "text", "text": "Lire l'outil."}]},
            {"type": "text", "text": "Il est 9 h."},
        ]
    elif form == "field":
        assert past["reasoning"] == "Lire l'outil." and past["content"] == "Il est 9 h."
    else:
        assert past["content"] == "<think>Lire l'outil.</think>Il est 9 h."
    session.close()


def test_a_past_answer_of_reasoning_only_sends_no_empty_text_block():
    entry = _preset("mistral")
    reasoning = entry.reasoning.model_copy(update={"resend": True})
    entry = entry.model_copy(update={"reasoning": reasoning})
    provider = Provider(sse(_thinking("Rien à dire."), _usage()), TEXT)
    session = _cloud(entry, provider, "short_memory", "reasoning")

    _run(session, "Bonjour")
    _run(session, "Encore")

    past = _assistant(_bodies(provider)[1])[-1]
    assert past["content"] == [
        {"type": "thinking", "thinking": [{"type": "text", "text": "Rien à dire."}]}
    ]
    session.close()


def test_without_resend_the_reasoning_never_goes_back():
    provider = Provider(TOOL_WITH_BLOCKS, TEXT_WITH_BLOCKS, TEXT)
    session = _cloud(_preset("mistral"), provider, "tools", "short_memory", "reasoning")

    _run(session, "Quelle heure est-il ?")
    _run(session, "Merci")

    for request in provider.requests[1:]:
        text = request.content.decode("utf-8")
        assert "Il faut l'heure." not in text and "Lire l'outil." not in text
        assert "thinking" not in text
    session.close()


# ---------- independent review (2026-09-26) ----------


LONG_REASONING = "je réfléchis " * 200  # 2 600 characters: one token each in `FakeEngine`


def test_local_reasoning_that_never_closes_still_answers_within_the_reasoning_reserve():
    """Lot C (N4): no more empty bubble; the harness closes the reasoning at its budget and
    the answer takes the rest of the 1 536-token reserve (`tests/test_reasoning_budget.py`)."""
    engine, session = _qwen([LONG_REASONING, "Bonjour."])
    session.set_brick("reasoning", True)
    session.join()

    events = _run(session, "Bonjour")

    assert events["context_rendered"][0]["reserve"] == 1536
    # The reserve, shared: what the relaunch adds to the prompt comes out of it (AD-9).
    left = len(engine.calls[0]) + 1536 - len(engine.calls[1])
    assert (
        engine.max_tokens == [1536, left] and events["reasoning_cut"][0]["answer_reserve"] == left
    )
    assert events["reasoning_cut"][0]["reasoning_tokens"] == 1024
    assert "output_truncated" not in events
    assert events["model_call_ended"][0]["text"].strip() == "Bonjour."
    assert events["turn_ended"][0]["status"] == "completed"
    session.close()


def test_local_tool_call_cut_names_the_reasoning_reserve():
    cut = "Il faut calculer.\n</think>\n\n<tool_call>\n<function=calculator>\n" + "1+" * 1000
    engine, session = _qwen([cut, "Abandon."])
    session.set_brick("tools", True)
    session.set_brick("reasoning", True)
    session.join()

    events = _run(session, "Combien ?")

    assert events["output_truncated"][0]["max_tokens"] == 1536
    assert "1\u202f536 tokens" in events["tool_call_malformed"][0]["detail_fr"]
    session.close()


def test_chat_tool_call_cut_names_the_reasoning_reserve():
    cut = sse(
        delta(
            tool_calls=[
                {
                    "index": 0,
                    "id": "call_1",
                    "type": "function",
                    "function": {"name": "get_datetime", "arguments": '{"tz'},
                }
            ]
        ),
        {**delta("length"), "usage": {"prompt_tokens": 50, "completion_tokens": 1536}},
    )
    provider = Provider(cut, TEXT)
    session = _cloud(_preset("mistral"), provider, "tools", "reasoning")

    events = _run(session, "Quelle heure est-il ?")

    truncated = events["output_truncated"][0]
    assert truncated["channel"] == "tool_call" and truncated["max_tokens"] == 1536
    assert "1\u202f536 tokens" in events["tool_call_malformed"][0]["detail_fr"]
    assert _bodies(provider)[0]["max_tokens"] == 1536
    session.close()


def test_a_tool_call_in_an_unclosed_reasoning_is_never_run():
    engine, session = _qwen(["Je pourrais " + call("calculator", expression="1+1") + " voyons"])
    session.set_brick("tools", True)
    session.set_brick("reasoning", True)
    session.join()

    events = _run(session, "Bonjour")

    assert "tool_started" not in events and "tool_call_malformed" not in events
    assert len(engine.calls) == 1
    session.close()


@pytest.mark.parametrize(
    "after",
    ["\n<think>je continue sans refermer", " fin </think> puis du texte"],
    ids=["second-unclosed-think", "literal-closing-tag"],
)
def test_a_valid_call_counts_whatever_follows_it(after):
    first = "Il faut calculer.\n</think>\n\n" + call("calculator", expression="12*37") + after
    engine, session = _qwen([first, "C'est fait.\n</think>\n\nCela fait 444."])
    session.set_brick("tools", True)
    session.set_brick("reasoning", True)
    session.join()

    events = _run(session, "Combien font 12 × 37 ?")

    assert [e["tool"] for e in events["tool_started"]] == ["calculator"]
    assert events["tool_ended"][0]["result"] == "444"
    session.close()


def test_a_malformed_step_rerenders_its_text_without_the_reasoning():
    broken = "Il faut calculer.\n</think>\n\n<tool_call>\n<function=calculator>\n"
    engine, session = _qwen([broken, "C'est fait.\n</think>\n\nJe ne sais pas."])
    session.set_brick("tools", True)
    session.set_brick("reasoning", True)
    session.join()

    events = _run(session, "Combien ?")

    assert events["tool_call_malformed"][0]["reaction"] == "retry"
    second = events["context_rendered"][1]
    turn = [s for s in second["segments"] if s["kind"] == "assistant_turn"]
    assert any(s["text"] == "Il faut calculer." for s in turn)  # the reasoning, apart
    assert not any("</think>" in s["text"] for s in turn)  # the content holds no reasoning
    assert _prompt(second).count("Il faut calculer.") == 1
    session.close()


def test_without_a_model_the_reason_says_so():
    session = AppSession(config.Config(values={}))
    mark = get_journal().last_seq()
    session.boot(None).result()

    assert _card(mark)["reason_fr"] == "Indisponible : aucun modèle chargé."
    session.close()


def test_a_window_too_small_for_the_reasoning_reserve_makes_it_unavailable():
    engine = RecordingEngine(output="ok", template=QWEN.decode("utf-8"), architecture="qwen35")
    session = booted_session(engine, window=1536)
    mark = get_journal().last_seq()
    session.set_brick("reasoning", True)
    session.join()

    card = _card(mark)
    assert not card["available"] and "1\u202f536" in card["reason_fr"]
    assert _run(session, "Bonjour")["context_rendered"][0]["reserve"] == 512
    session.close()


def test_a_model_that_always_reasons_draws_the_brick_and_names_the_model():
    entry = _preset("groq")
    session = _cloud(entry, Provider(TEXT))

    card = _card()
    assert not card["wanted"]
    assert f"{entry.model} raisonne à chaque réponse ; ce modèle ne permet pas" in card["always_fr"]
    assert entry.provider not in card["always_fr"]
    nodes = {n["id"] for n in _latest("architecture_changed")["nodes"]}
    assert "reasoning.mode" in nodes
    session.close()


def test_reasoning_scenario_adds_the_brick_to_the_bare_llm():
    """Story 21: second scenario of module 1 (FR-38), the reasoning alone."""
    _, session = _qwen(["ok"])

    session.launch_scenario("reasoning")
    session.join()

    assert session._wanted == {"reasoning"}
    assert session._mcp_lazy is False
    preview = _latest("context_preview")
    # The fit itself needs the real tokenizer (AD-9's `model` test): one token per byte here.
    assert preview["reserve"] == 1536 and preview["usable"] == 4096 - 1536
    session.close()
