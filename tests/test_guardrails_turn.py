"""Story 5 (CAP-5, CAP-6): the guardrails brick actually filters the turn's input and
output. Fake classifiers only (as `test_guardrails.py`): no test loads a real model."""

from __future__ import annotations

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


def test_output_masked_before_it_reaches_the_user() -> None:
    engine = FakeEngine(output="contact PII ici")
    session = _guarded_session(engine, pii=FakeClassifier("PII"))
    session.set_guardrail_mode("pii", "flag")

    events = _run(session, "bonjour")

    assert events["turn_ended"][0]["status"] == "completed"
    ended = events["model_call_ended"][0]
    assert ended["text"] == "contact PII ici"  # the model's own raw answer, unmasked
    [verdict] = [v for v in events["guardrail_verdict"] if v["direction"] == "output"]
    assert verdict["masked_text"] == "contact [TEST] ici"


def test_security_journal_records_the_verdict() -> None:
    engine = FakeEngine(output="bonjour")
    session = _guarded_session(engine, toxicity=FakeClassifier("INSULT"))
    session.set_guardrail_mode("toxicity", "block")

    _run(session, "t'es INSULT")

    [entry] = [e for e in session.security_journal_entries() if e["source"] == "guardrail"]
    assert entry["decision"] == "blocked"
    assert "Toxicité" in entry["reason_text"]
