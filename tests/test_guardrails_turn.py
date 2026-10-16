"""Story 5 (CAP-5, CAP-6): the guardrails brick actually filters the turn's input and
output. Fake classifiers only (as `test_guardrails.py`): no test loads a real model."""

from __future__ import annotations

import json

from fake_engine import FakeEngine, booted_session

from wavestack.guardrails.contract import Classification, Entity
from wavestack.guardrails.manager import GuardrailsManager
from wavestack.trace.journal import get_journal


class FakeClassifier:
    def __init__(self, trigger: str) -> None:
        self.trigger = trigger

    def classify(self, text: str) -> Classification:
        if self.trigger not in text:
            return Classification(detected=False, score=0.1, threshold=0.5)
        start = text.index(self.trigger)
        entity = Entity("TEST", start, start + len(self.trigger), 0.9)
        return Classification(detected=True, score=0.9, threshold=0.5, entities=(entity,))

    def mask(self, text: str, entities: tuple[Entity, ...]) -> str:
        for e in entities:
            text = text[: e.start] + f"[{e.label}]" + text[e.end :]
        return text

    def unload(self) -> None:
        pass


def _guarded_session(engine: FakeEngine, **fakes: FakeClassifier):
    session = booted_session(engine)
    session._guardrails_missing = None  # the brick is available, whatever is installed
    session._guardrails = GuardrailsManager({g: (lambda f=f: f) for g, f in fakes.items()})
    session.set_brick("guardrails", True)
    return session


def _run(session, message: str) -> dict[str, list[dict]]:
    mark = get_journal().last_seq()
    session.send(message)
    session.join()
    by_kind: dict[str, list[dict]] = {}
    for envelope in get_journal().events_since(mark):
        by_kind.setdefault(envelope.kind, []).append(envelope.payload)
    return by_kind


def test_input_blocked_never_reaches_the_model() -> None:
    engine = FakeEngine(output="ignoré")
    session = _guarded_session(engine, toxicity=FakeClassifier("INSULT"))
    session.set_guardrail_mode("toxicity", "block")

    events = _run(session, "t'es INSULT")

    assert engine.calls == []  # the model never saw it
    assert events["turn_ended"][0]["status"] == "blocked"
    [verdict] = events["guardrail_verdict"]
    assert verdict["direction"] == "input" and verdict["detected"] is True
    assert verdict["banner_text"]


def _texts(events: dict[str, list[dict]], *kinds: str) -> str:
    """Everything the trace (journal, export) holds for these kinds, as one string."""
    return json.dumps([events.get(k, []) for k in kinds], ensure_ascii=False)


def test_output_masked_before_it_reaches_the_user() -> None:
    """Review of story 5 (HIGH): in « Masquer », the raw answer is never streamed nor
    traced; only the masked text reaches the screen (`turn_ended.text`) and the history."""
    engine = FakeEngine(output="contact PII ici")
    session = _guarded_session(engine, pii=FakeClassifier("PII"))
    session.set_guardrail_mode("pii", "flag")

    events = _run(session, "bonjour")

    assert events["turn_ended"][0]["status"] == "completed"
    assert events["model_call_started"][0]["withheld"] is True
    assert "PII" not in _texts(events, "model_delta", "model_call_ended", "turn_ended")
    assert events["turn_ended"][0]["text"] == "contact [TEST] ici"
    [verdict] = [v for v in events["guardrail_verdict"] if v["direction"] == "output"]
    assert verdict["masked_text"] == "contact [TEST] ici"
    assert session._history[-1].text == "contact [TEST] ici"


def test_output_blocked_leaves_nothing_in_clear() -> None:
    engine = FakeEngine(output="tu es INSULT")
    session = _guarded_session(engine, toxicity=FakeClassifier("INSULT"))
    session.set_guardrail_mode("toxicity", "block")

    events = _run(session, "bonjour")

    assert events["turn_ended"][0]["status"] == "blocked"
    assert events["turn_ended"][0]["text"] == ""
    assert "INSULT" not in _texts(events, "model_delta", "model_call_ended", "turn_ended")
    [verdict] = [v for v in events["guardrail_verdict"] if v["direction"] == "output"]
    assert "pas reçu la réponse" in verdict["banner_text"]
    assert session._history == []


def test_flag_mode_still_streams_live() -> None:
    """« Signaler » changes nothing: the answer streams as without the brick."""
    engine = FakeEngine(output="tu es INSULT")
    session = _guarded_session(engine, toxicity=FakeClassifier("INSULT"))
    session.set_guardrail_mode("toxicity", "flag")

    events = _run(session, "bonjour")

    assert not events["model_call_started"][0].get("withheld")
    assert events["model_call_ended"][0]["text"] == "tu es INSULT"
    assert "text" not in events["turn_ended"][0]


def test_input_masked_never_goes_back_to_the_model() -> None:
    """Review of story 5 (HIGH): the masked message enters the history; the next turn's
    context never carries the raw one."""
    engine = FakeEngine(output="ok")
    session = _guarded_session(engine, pii=FakeClassifier("PII"))
    session.set_guardrail_mode("pii", "flag")
    session.set_brick("short_memory", True)

    _run(session, "mon PII est là")
    assert session._history[-1].user == "mon [TEST] est là"
    session.set_guardrail_mode("pii", "off")
    events = _run(session, "suite")

    assert "mon PII" not in _texts(events, "context_rendered")
    assert "mon [TEST] est là" in _texts(events, "context_rendered")


def test_security_journal_records_the_verdict() -> None:
    engine = FakeEngine(output="bonjour")
    session = _guarded_session(engine, toxicity=FakeClassifier("INSULT"))
    session.set_guardrail_mode("toxicity", "block")

    _run(session, "t'es INSULT")

    [entry] = [e for e in session.security_journal_entries() if e["source"] == "guardrail"]
    assert entry["decision"] == "blocked"
    assert "Toxicité" in entry["reason_text"]


def test_partial_analysis_is_said_never_silent() -> None:
    """Review of story 5 (MEDIUM): a text scored only in part (toxicity's window budget)
    says so in its verdict and in the security journal."""

    class Partial(FakeClassifier):
        def classify(self, text: str) -> Classification:
            return Classification(detected=False, score=0.1, threshold=0.5, partial=True)

    engine = FakeEngine(output="ok")
    session = _guarded_session(engine, toxicity=Partial("x"))
    session.set_guardrail_mode("toxicity", "flag")

    events = _run(session, "très long")

    [verdict] = [v for v in events["guardrail_verdict"] if v["direction"] == "input"]
    assert verdict["partial"] is True and "en partie" in verdict["verdict_text"]
    assert verdict["banner_text"]
    entries = [e for e in session.security_journal_entries() if e["source"] == "guardrail"]
    assert entries[0]["decision"] == "partial"


def test_cloud_call_withholds_the_answer_too() -> None:
    """Review of story 5 (HIGH): the chat path (`run_call`) streams and traces no final
    answer under `withhold`; the caller keeps it (`ChatCall.text`) for the check."""
    from wavestack.models.cloud_base import ChatBody, ChatEnd, run_call
    from wavestack.models.engine import CancelToken

    class Engine:
        def complete(self, body, cancel):
            yield ("text", "contact PII ")
            yield ("text", "ici")
            yield ChatEnd("stop", [], None, "contact PII ici")

    mark = get_journal().last_seq()
    call = run_call(
        Engine(),
        ChatBody(b"{}"),
        CancelToken(),
        phase_label="test",
        estimated_prompt=1,
        chars_per_token=4,
        call_id=lambda i: f"id{i}",
        withhold=True,
    )

    events = get_journal().events_since(mark)
    assert call.text == "contact PII ici"
    assert [e.payload.get("withheld") for e in events if e.kind == "model_call_started"] == [True]
    assert "PII" not in json.dumps([e.payload for e in events], ensure_ascii=False)
