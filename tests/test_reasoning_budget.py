"""Lot C (decision N4): the reasoning budget closed by the harness, local mode only.

One test per row of the spec's I/O matrix, on `FakeEngine` (one token per character, the
Qwen3.5 template): a reasoning that reaches the budget without closing is stopped, closed
with the template's own text and the model relaunched on the rest of the reserve.
"""

from __future__ import annotations

import threading

import pytest
from fake_engine import booted_session
from test_cloud import Provider, delta, sse
from test_reasoning import (
    LONG_REASONING,
    RecordingEngine,
    _bodies,
    _card,
    _cloud,
    _preset,
    _usage,
)
from test_subagent import RESULT, delegation
from test_tools import QWEN, call
from test_turn import _run

from wavestack import config
from wavestack.hooks import DEMO_HOOKS
from wavestack.models.servers import ServerError
from wavestack.session.app_session import AppSession
from wavestack.trace.journal import get_journal

CLOSURE = "\n</think>\n\n"  # `reasoning_wrap(QWEN)[1]`
ANSWER = "Il arrive à 17 h 25."
CUT = LONG_REASONING[:768]  # the reasoning kept: 768 characters, one token each (lot J)
# AD-9: the reserve after the ids of the reasoning and the closure (one id per byte here)
LEFT = 1536 - len((CUT + CLOSURE).encode("utf-8"))


class _Tokenizing(RecordingEngine):
    """Records what the harness tokenizes (the relaunch's new text)."""

    def __init__(self, **kwargs) -> None:
        super().__init__(**kwargs)
        self.tokenized: list[str] = []

    def tokenize(self, text: str) -> list[int]:
        self.tokenized.append(text)
        return super().tokenize(text)


def _session(outputs: list[str], *bricks: str, values: dict | None = None, **kwargs):
    engine = _Tokenizing(
        outputs=outputs, template=QWEN.decode("utf-8"), architecture="qwen35", **kwargs
    )
    session = booted_session(engine, window=16384, values=values)
    for brick in bricks:
        session.set_brick(brick, True)
    session.join()
    return engine, session


def test_a_reasoning_longer_than_the_budget_is_closed_and_the_model_answers():
    engine, session = _session([LONG_REASONING, ANSWER], "reasoning")

    events = _run(session, "À quelle heure arrive le train ?")

    assert engine.max_tokens == [1536, LEFT]  # the whole reserve, shared with the closure
    (cut,) = events["reasoning_cut"]
    assert {k: cut[k] for k in ("budget", "reasoning_tokens", "answer_reserve")} == {
        "budget": 768,
        "reasoning_tokens": 768,
        "answer_reserve": LEFT,
    }
    assert f"garde {LEFT} tokens" in cut["message_text"]
    assert cut["message_text"].startswith("Raisonnement coupé par le harnais à 768 tokens")
    # The relaunch: the ids in the engine's cache, then the template's closure.
    first, relaunch = engine.calls
    assert relaunch == first + list((CUT + CLOSURE).encode("utf-8"))
    assert CLOSURE in engine.tokenized and CUT + CLOSURE not in engine.tokenized
    assert engine.evaluated[1] == len(CLOSURE)  # only the closure is read
    (ended,) = events["model_call_ended"]
    assert ended["raw_output"] == CUT + CLOSURE + ANSWER
    assert ended["reasoning"].strip() == CUT.strip() and ended["text"].strip() == ANSWER
    assert ended["output_tokens"] == 768 + len(ANSWER)
    assert ended["evaluated_tokens"] == engine.evaluated[0] + engine.evaluated[1]
    assert ended["stop_reason"] == "stop" and ended["prompt_tokens"] == len(first)
    assert len(events["model_first_token"]) == 1
    text = "".join(d["text"] for d in events["model_delta"] if d["channel"] == "text")
    assert text.strip() == ANSWER
    assert "output_truncated" not in events
    assert events["turn_ended"][0]["status"] == "completed"
    session.close()


def test_a_reasoning_closed_before_the_budget_is_never_cut():
    output = "Deux étapes.\n</think>\n\n" + ANSWER
    engine, session = _session([output, "jamais lu"], "reasoning")

    events = _run(session, "À quelle heure ?")

    assert "reasoning_cut" not in events
    assert engine.max_tokens == [1536] and len(engine.calls) == 1
    assert events["model_call_ended"][0]["raw_output"] == output
    assert events["turn_ended"][0]["status"] == "completed"
    session.close()


def test_an_answer_longer_than_the_reserve_left_is_cut_on_the_text():
    engine, session = _session([LONG_REASONING, "x" * (LEFT + 100)], "reasoning")

    events = _run(session, "À quelle heure ?")

    assert engine.max_tokens == [1536, LEFT]
    assert events["output_truncated"] == [
        {"channel": "text", "output_tokens": LEFT, "max_tokens": LEFT}  # the answer's own
    ]
    ended = events["model_call_ended"][0]
    assert ended["text"].strip() == "x" * LEFT  # the text received is kept
    assert ended["stop_reason"] == "length"
    assert events["turn_ended"][0]["status"] == "limit"
    session.close()


class _StoppedRelaunch(RecordingEngine):
    """Holds the relaunch until the user stops the turn."""

    def __init__(self, **kwargs) -> None:
        super().__init__(**kwargs)
        self.relaunched = threading.Event()

    def complete(self, prompt_ids, stop, max_tokens, cancel):
        if self.calls:  # the relaunch
            self.relaunched.set()
            cancel.wait(5)
        yield from super().complete(prompt_ids, stop, max_tokens, cancel)


def test_a_stop_during_the_relaunch_cancels_the_turn():
    engine = _StoppedRelaunch(
        outputs=[LONG_REASONING, ANSWER], template=QWEN.decode("utf-8"), architecture="qwen35"
    )
    session = booted_session(engine, window=16384)
    session.set_brick("reasoning", True)
    session.join()
    mark = get_journal().last_seq()

    session.send("À quelle heure ?")
    assert engine.relaunched.wait(5)
    assert session.stop() is True
    session.join()

    events: dict[str, list[dict]] = {}
    for envelope in get_journal().events_since(mark):
        events.setdefault(envelope.kind, []).append(envelope.payload)
    assert len(events["reasoning_cut"]) == 1
    (ended,) = events["model_call_ended"]
    assert ended["stop_reason"] == "cancelled" and ended["raw_output"] == CUT + CLOSURE
    assert events["turn_ended"][0]["status"] == "cancelled"
    session.close()


def test_the_brick_off_keeps_the_plain_reserve_and_no_budget():
    engine, session = _session([LONG_REASONING])

    events = _run(session, "À quelle heure ?")

    assert engine.max_tokens == [512] and "reasoning_cut" not in events
    assert events["output_truncated"][0]["channel"] == "text"
    session.close()


def test_chat_mode_is_unchanged():
    provider = Provider(
        sse(delta(role="assistant", reasoning=LONG_REASONING), delta(content="Bonjour."), _usage())
    )
    session = _cloud(_preset("groq"), provider)

    assert _card()["limits_text"] is None  # the provider manages its reasoning effort
    events = _run(session, "Bonjour")

    assert "reasoning_cut" not in events and len(provider.requests) == 1
    assert _bodies(provider)[0]["max_tokens"] == 1536
    assert events["turn_ended"][0]["status"] == "completed"
    session.close()


def test_the_next_turn_extends_the_cache_after_a_cut():
    outputs = [LONG_REASONING, ANSWER, "Je vérifie.\n</think>\n\nOui."]
    engine, session = _session(outputs, "short_memory", "reasoning")

    _run(session, "À quelle heure ?")
    second = _run(session, "Tu es sûr ?")

    assert "prefix_not_reused" not in second and "reasoning_cut" not in second
    before = bytes(engine.calls[1]) + ANSWER.encode("utf-8")
    assert bytes(engine.calls[2]).startswith(before)
    assert engine.evaluated[2] == len(engine.calls[2]) - len(before)
    assert second["turn_ended"][0]["status"] == "completed"
    session.close()


def test_a_cut_waits_for_the_first_token_after_a_blank():
    """The history's render trims the reasoning (AD-4): a reasoning cut after a blank would
    not be rendered as produced at the next turn."""
    values = {"reasoning": {"budget_tokens": 1027}}  # the 1 027th character is a space
    outputs = [LONG_REASONING, ANSWER, "Je vérifie.\n</think>\n\nOui."]
    engine, session = _session(outputs, "short_memory", "reasoning", values=values)
    assert LONG_REASONING[1026] == " "

    first = _run(session, "À quelle heure ?")
    second = _run(session, "Tu es sûr ?")

    assert first["reasoning_cut"][0]["reasoning_tokens"] == 1028
    assert first["model_call_ended"][0]["raw_output"].startswith(LONG_REASONING[:1028] + CLOSURE)
    assert "prefix_not_reused" not in second
    session.close()


@pytest.mark.parametrize(
    ("value", "expected"),
    [
        (None, 768),
        ("beaucoup", 768),
        (512.5, 768),
        (True, 768),
        (600, 600),
        ("700", 700),
        (800.0, 800),
        (10, 128),
        (1536, 1408),
        (99999, 1408),
    ],
)
def test_the_budget_setting_is_bounded(value, expected):
    values = {} if value is None else {"reasoning": {"budget_tokens": value}}
    assert config.Config(values=values).reasoning_budget_tokens == expected


def test_the_card_gives_the_budget_and_the_answer_reserve():
    _, session = _session(["ok"], values={"reasoning": {"budget_tokens": 1000}})

    assert _card()["limits_text"] == (
        "Budget de réflexion : 1 000 tokens ; au-delà, le harnais ferme la réflexion et "
        "garde 536 tokens pour la réponse."
    )
    session.close()


def test_a_smaller_budget_leaves_more_to_the_answer():
    values = {"reasoning": {"budget_tokens": 128}}
    engine, session = _session([LONG_REASONING, ANSWER], "reasoning", values=values)

    events = _run(session, "À quelle heure ?")

    assert engine.max_tokens == [1536, 1536 - len((LONG_REASONING[:128] + CLOSURE).encode())]
    assert events["reasoning_cut"][0]["reasoning_tokens"] == 128
    assert events["turn_ended"][0]["status"] == "completed"
    session.close()


def test_the_sub_agent_takes_the_same_path_when_it_reasons():
    """Locally the sub-agent never reasons (the brick contributes to the main context only);
    made to reason here, its call takes the same budget."""
    thinking = "<think>\n" + LONG_REASONING
    engine = RecordingEngine(
        outputs=[delegation(), thinking, RESULT, "Voilà."],
        template=QWEN.decode("utf-8"),
        architecture="qwen35",
    )
    session = AppSession(
        config.Config(values={"context": {"window": 16384}}),
        engine_factory=lambda path, n_ctx: engine,
        hooks=DEMO_HOOKS,
    )
    session.boot("fake.gguf").result()
    for brick in ("tools", "subagent"):
        session.set_brick(brick, True)
    session.join()
    session._reasoning_on = lambda state: session._ratio_key() == "sub"
    mark = get_journal().last_seq()

    session.send("Quelles décisions ont été prises ?")
    session.join()

    envelopes = get_journal().events_since(mark)
    (cut,) = [e for e in envelopes if e.kind == "reasoning_cut"]
    assert cut.context_id != "main" and cut.payload["reasoning_tokens"] == 768
    assert engine.max_tokens[:3] == [512, 1536, cut.payload["answer_reserve"]]
    assert bytes(engine.calls[2]).endswith(CLOSURE.encode("utf-8"))
    (sub_ended,) = [e.payload for e in envelopes if e.kind == "subagent_ended"]
    assert sub_ended["status"] == "completed"
    (turn_ended,) = [e.payload for e in envelopes if e.kind == "turn_ended"]
    assert turn_ended["status"] == "completed"
    session.close()


def test_a_stateless_engine_relaunches_on_the_prompt_and_the_output():
    engine, session = _session([LONG_REASONING, ANSWER], "reasoning", stateful=False)

    events = _run(session, "À quelle heure ?")

    first, relaunch = engine.calls
    assert relaunch == first + list((CUT + CLOSURE).encode("utf-8"))
    assert CUT + CLOSURE in engine.tokenized  # nothing cached to start from
    assert events["reasoning_cut"][0]["answer_reserve"] == LEFT
    assert events["turn_ended"][0]["status"] == "completed"
    session.close()


def test_a_cache_without_the_last_token_relaunches_on_it_and_its_rest():
    engine, session = _session([LONG_REASONING, ANSWER], "reasoning", cache_lags=True)

    events = _run(session, "À quelle heure ?")

    first, relaunch = engine.calls
    assert relaunch == first + list((CUT + CLOSURE).encode("utf-8"))
    assert CUT[-1] + CLOSURE in engine.tokenized  # the token sampled, not evaluated yet
    assert engine.evaluated[1] == len((CUT[-1] + CLOSURE).encode("utf-8"))
    assert events["reasoning_cut"][0]["answer_reserve"] == LEFT
    session.close()


def test_the_models_own_closing_tag_across_the_budget_is_never_cut():
    output = LONG_REASONING[:764] + "</think>\n\n" + ANSWER  # the tag across the 768 budget
    engine, session = _session([output, "jamais lu"], "reasoning")

    events = _run(session, "À quelle heure ?")

    assert "reasoning_cut" not in events and len(engine.calls) == 1
    assert events["model_call_ended"][0]["raw_output"] == output
    session.close()


KEEPS_REASONING = (  # ChatML that keeps the past reasoning: no `reasoning_wrap`
    "{% for m in messages %}<|im_start|>{{ m.role }}\n{% if m.reasoning_content %}<think>"
    "{{ m.reasoning_content }}</think>{% endif %}{{ m.content }}<|im_end|>\n{% endfor %}"
    "{% if add_generation_prompt %}<|im_start|>assistant\n{% if enable_thinking %}<think>\n"
    "{% else %}<think>\n\n</think>\n\n{% endif %}{% endif %}"
)


def test_a_template_without_reasoning_block_closes_with_the_tag():
    engine = RecordingEngine(outputs=[LONG_REASONING, ANSWER], template=KEEPS_REASONING)
    session = booted_session(engine, window=16384)
    session.set_brick("reasoning", True)
    session.join()

    events = _run(session, "À quelle heure ?")

    first, relaunch = engine.calls
    assert relaunch == first + list((CUT + "</think>\n\n").encode("utf-8"))
    assert events["model_call_ended"][0]["text"].strip() == ANSWER
    session.close()


class _FailingRelaunch(RecordingEngine):
    def __init__(self, error: Exception, **kwargs) -> None:
        super().__init__(**kwargs)
        self.error = error

    def complete(self, prompt_ids, stop, max_tokens, cancel):
        if self.calls:  # the relaunch
            raise self.error
        yield from super().complete(prompt_ids, stop, max_tokens, cancel)


@pytest.mark.parametrize(
    "error",
    [RuntimeError("moteur en panne"), ServerError("http://127.0.0.1:8080", "arrêté")],
    ids=["engine", "server"],
)
def test_a_failed_relaunch_ends_the_call_once_in_error(error):
    engine = _FailingRelaunch(
        error, outputs=[LONG_REASONING], template=QWEN.decode("utf-8"), architecture="qwen35"
    )
    session = booted_session(engine, window=16384)
    session.set_brick("reasoning", True)
    session.join()

    events = _run(session, "À quelle heure ?")

    assert len(events["reasoning_cut"]) == 1
    (ended,) = events["model_call_ended"]
    assert ended["stop_reason"] == "error" and ended["raw_output"] == CUT + CLOSURE
    assert events["turn_ended"][0]["status"] == "error"
    session.close()


def test_a_tool_call_in_the_answer_after_a_cut_is_run():
    outputs = [
        LONG_REASONING,
        call("calculator", expression="12*37"),
        "C'est fait.\n</think>\n\nCela fait 444.",
    ]
    engine, session = _session(outputs, "tools", "reasoning")

    events = _run(session, "Combien font 12 × 37 ?")

    assert len(events["reasoning_cut"]) == 1
    assert [e["tool"] for e in events["tool_started"]] == ["calculator"]
    assert events["tool_ended"][0]["result"] == "444"
    assert events["turn_ended"][0]["status"] == "completed"
    session.close()


def test_no_budget_with_the_brick_off_even_if_the_model_thinks():
    values = {"reasoning": {"budget_tokens": 128}}  # under the 512 reserve
    engine, session = _session(["<think>\n" + LONG_REASONING], values=values)

    events = _run(session, "À quelle heure ?")

    assert engine.max_tokens == [512] and "reasoning_cut" not in events
    assert events["output_truncated"][0]["channel"] == "reasoning"
    session.close()


def test_the_largest_budget_still_leaves_the_answer_its_floor():
    values = {"reasoning": {"budget_tokens": 1408}}  # exactly the floor left: applied
    engine, session = _session([LONG_REASONING, ANSWER], "reasoning", values=values)
    assert "reasoning_cut" in _run(session, "À quelle heure ?")
    session.close()
    assert config.Config(values={"reasoning": {"budget_tokens": 1409}}).reasoning_budget_tokens == (
        1408
    )


def test_a_relaunch_after_a_cut_stays_one_call_and_the_next_call_reads_it_again():
    """Story 32: the relaunch is the same call (one `context_rendered`, one
    `model_call_ended`); the next call's « déjà lu » is its prefix of the first call."""
    engine, session = _session([LONG_REASONING, call("get_datetime"), ANSWER], "reasoning", "tools")

    events = _run(session, "Quelle heure est-il ?")

    assert len(events["reasoning_cut"]) == 1 and len(engine.calls) == 3  # call, relaunch, call
    first, second = events["context_rendered"]  # no context of its own for the relaunch
    assert len(events["model_call_ended"]) == 2
    assert first["seen_segments"] == 0
    seen = second["seen_segments"]
    assert 0 < seen < len(second["segments"])
    assert [s["text"] for s in second["segments"][:seen]] == [
        s["text"] for s in first["segments"][:seen]
    ]
    assert any(s["kind"] == "tool_result" and not s["seen"] for s in second["sections"])
    assert events["turn_ended"][0]["status"] == "completed"
    session.close()
