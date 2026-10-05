"""Lot 5c-3: the Generation stage of the RAG workshop, run by the workshop's active model.

Sent: the system prompt brick's text (nothing when the brick is off), then the context the
chain built and the question, within a turn's bounds (output reserve, reasoning budget).
Local through `_call_model`, cloud through `run_call`; scope `rag_lab`, never a turn. The
models are fakes (`FakeEngine`, a scripted provider); nothing touches the network.
"""

from __future__ import annotations

import time
from pathlib import Path

import httpx
import pytest
from fake_engine import FakeEngine
from pydantic import SecretStr
from test_cloud import GROQ_TEXT, SENTINEL, Provider
from test_rag import Embedders, build, place_model
from test_rag_lab import QUESTION, ended, run, run_status, stage, wait_idle
from test_rag_rerank import Rerankers, place_reranker, rerank_config, session_for

from wavestack import config
from wavestack.greenops import Impact
from wavestack.rag import lab as rag_lab
from wavestack.rag.corpus import load_rag_content
from wavestack.session.app_session import AppSession
from wavestack.trace.journal import get_journal

GENERATION = "lab1.s7"  # the shipped chain's seventh stage, in the first run
ANSWER = "Quatorze caractères."


@pytest.fixture
def index(tmp_path) -> Path:
    path = tmp_path / "rag_index.sqlite"
    build(path)
    return path


def ready(index: Path, *, engine: FakeEngine | None = None, window: int = 4096, **values):
    """A booted session (the RAG brick off), its models' files in place."""
    place_model()
    place_reranker()
    config_values = rerank_config(index) | values
    config_values["context"] = {"window": window, "near_limit_ratio": 0.8}
    session, _ = session_for(config_values, rerank=False, bricks=(), engine=engine)
    return session


def generation_options(session: AppSession) -> dict:
    stages = session.rag_lab_state()["catalog"]["stages"]
    return {o["id"]: o for o in next(s for s in stages if s["kind"] == "generation")["options"]}


def own_chain(session: AppSession) -> rag_lab.Pipeline:
    """The shipped chain on its own index (chunks of 300 characters, the memory store): it runs
    in any language, the brick's index being the French one."""
    chain = session._rag_lab_catalog(rag_lab.load_lab_content()).default.model_copy(deep=True)
    stage(chain, "chunking").params["chunk_max_chars"] = 300
    stage(chain, "vector_store").option = "memory"
    return chain


def model_calls(events: list) -> list:
    return [e for e in events if e.kind.startswith("model_call")]


class Meter:
    """A CodeCarbon stand-in: each local call costs 0.5 Wh and 0.03 g CO₂e."""

    def start(self, machine: bool):  # noqa: ANN201, ARG002
        return self

    def stop(self) -> Impact:
        return Impact("codecarbon", None, 0.5, 0.5, 0.03, 0.03)


# ---------- the shipped chain, a local model ----------


def test_the_active_model_answers_the_augmented_prompt(index):
    session = ready(index)
    session._local_meter = Meter()
    mark = get_journal().last_seq()
    events = run(session)

    generation = ended(events, "generation")
    assert generation["status"] == "ok", generation["error_text"]
    assert generation["output_text"] == ANSWER
    assert generation["option"] == "active" and generation["warning_text"] is None
    # The prompt shown is the one rendered exactly: the context, then the question.
    prompt = generation["prompt_text"]
    content = load_rag_content()
    assert prompt.index(content.intro_text) < prompt.index(QUESTION)
    assert prompt.endswith("<|im_start|>assistant\n")
    assert session._engine.calls[-1] == list(prompt.encode("utf-8"))
    facts = {f["label_text"]: f["value_text"] for f in generation["facts"]}
    tokens = len(prompt.encode("utf-8"))
    assert facts["Modèle"] == session.active_model()["label"]
    assert facts["Tokens du prompt"] == rag_lab.fr_int(tokens)
    assert facts["Tokens produits"] == "20 sur 512 (réserve de sortie d'un tour)"
    assert "Envoyé au modèle actif de l'atelier" in generation["input_text"]
    assert run_status(events) == "ok" and session.state == "idle"

    # The live text: `model_delta` of the workshop's context, on the stage's step; the
    # progress in tokens, against the reserve.
    deltas = [e for e in events if e.kind == "model_delta"]
    assert "".join(e.payload["text"] for e in deltas) == ANSWER
    assert {(e.step_id, e.context_id, e.brick) for e in deltas} == {(GENERATION, "rag_lab", None)}
    progress = [
        e.payload
        for e in events
        if e.kind == "rag_lab_stage_progress" and e.payload["kind"] == "generation"
    ]
    assert progress[0]["done"] == 0 and {p["total"] for p in progress} == {512}
    assert all(p["done"] <= len(ANSWER) for p in progress)  # at most ten a second
    (call,) = [e for e in model_calls(events) if e.kind == "model_call_ended"]
    assert (call.step_id, call.call_id, call.actor) == (GENERATION, GENERATION, "model")
    # No turn, ever; the session's spend (GreenOps) counts the call.
    every = get_journal().events_since(mark)
    assert all(e.turn_id is None for e in every)
    (spend,) = [e.payload for e in every if e.kind == "consumption_updated"]
    assert spend["impact_calls"] == 1
    assert session.consumption() == spend


def test_the_catalog_names_the_active_model_and_ships_it(index):
    session = ready(index)
    options = generation_options(session)
    assert list(options) == ["active", "not_run"]
    label = session.active_model()["label"]
    assert options["active"]["label_text"] == f"Modèle actif de l'atelier : {label}"
    assert options["active"]["available"] and options["active"]["note_text"] is None
    assert options["not_run"]["label_text"] == "Ne pas générer"
    shipped = session.rag_lab_state()["default_pipeline"]["stages"][-1]
    assert (shipped["kind"], shipped["option"]) == ("generation", "active")


def test_the_system_prompt_brick_decides_the_system_message(index):
    session = ready(index)
    session.set_brick("system_prompt", True)
    session.join()
    with_prompt = ended(run(session), "generation")
    default = session.build_turn_state().system_prompt
    assert with_prompt["prompt_text"].startswith(f"<|im_start|>system\n{default}")
    assert "le prompt système de l'atelier" in with_prompt["input_text"]

    session.set_brick("system_prompt", False)
    session.join()
    without = ended(run(session), "generation")
    assert "<|im_start|>system" not in without["prompt_text"]
    assert without["prompt_text"].startswith("<|im_start|>user\n")
    assert "aucun prompt système" in without["input_text"]


def test_no_tool_memory_nor_skill_reaches_the_prompt(index):
    session = ready(index)
    for brick in ("system_prompt", "tools", "global_memory", "skills"):
        session.set_brick(brick, True)
    session.join()
    prompt = ended(run(session), "generation")["prompt_text"]
    state = session.build_turn_state()
    assert prompt.startswith(f"<|im_start|>system\n{state.system_prompt}<|im_end|>\n")
    assert "<|im_start|>user\n" in prompt and prompt.count("<|im_start|>") == 3


# ---------- the two options ----------


def test_do_not_generate_shows_what_would_be_sent(index):
    session = ready(index)
    chain = session._rag_lab_catalog(rag_lab.load_lab_content()).default.model_copy(deep=True)
    stage(chain, "generation").option = "not_run"
    events = run(session, QUESTION, chain)
    generation = ended(events, "generation")
    assert generation["status"] == "not_run" and generation["rss_bytes"] is None
    assert "vous avez choisi de ne pas générer" in generation["output_text"]
    assert "3 extraits" in generation["input_text"] and generation["prompt_text"] is None
    assert not model_calls(events) and session._engine.calls == []
    started = [e.payload["kind"] for e in events if e.kind == "rag_lab_stage_started"]
    assert "generation" not in started
    assert run_status(events) == "ok"


def test_without_a_model_the_stage_is_skipped_and_the_run_ends(index):
    place_model()
    place_reranker()
    session = AppSession(
        config.Config(values=rerank_config(index)),
        embedder_factory=Embedders(),
        reranker_factory=Rerankers(),
    )
    session.boot(None).result()
    session.join()
    options = generation_options(session)
    assert options["active"]["label_text"] == "Modèle actif de l'atelier"
    assert "l'étape Generation sera sautée" in options["active"]["note_text"]

    events = run(session)
    generation = ended(events, "generation")
    assert generation["status"] == "skipped"
    assert "Aucun modèle chargé dans l'atelier" in generation["error_text"]
    assert "recevrait" in generation["input_text"]
    assert ended(events, "context")["status"] == "ok"
    assert run_status(events) == "ok" and session.state == "idle"
    assert not model_calls(events)


def test_a_stage_failed_upstream_skips_the_generation(index):
    session = ready(index)
    index.unlink()
    events = run(session)
    assert ended(events, "generation")["status"] == "skipped"
    assert not model_calls(events) and session._engine.calls == []


# ---------- the bounds ----------


def test_an_answer_at_the_reserve_is_cut_with_a_warning(index):
    session = ready(index, engine=FakeEngine(output="x" * 600))
    events = run(session)
    generation = ended(events, "generation")
    assert generation["status"] == "ok" and generation["output_text"] == "x" * 512
    assert generation["warning_text"] == "Réponse coupée à 512 tokens : la réserve de sortie " + (
        "d'un tour de l'atelier est atteinte."
    )
    facts = {f["label_text"]: f["value_text"] for f in generation["facts"]}
    assert facts["Tokens produits"] == "512 sur 512 (réserve de sortie d'un tour)"
    assert run_status(events) == "ok"


def test_a_prompt_longer_than_the_room_is_not_sent(index):
    session = ready(index, window=1500)  # a token per byte: three excerpts do not fit
    events = run(session)
    generation = ended(events, "generation")
    assert generation["status"] == "error"
    tokens = len(generation["prompt_text"].encode("utf-8"))
    assert tokens > 1500 - 512
    expected = (
        f"Prompt trop long : {tokens:,} tokens pour 988 utilisables (fenêtre de "
        "1,500 moins 512 réservés à la réponse) : rien n'est envoyé au modèle."
    )
    assert generation["error_text"].replace(" ", " ").startswith(expected.replace(",", " "))
    assert not model_calls(events) and session._engine.calls == []
    assert "recevrait" in generation["input_text"]  # nothing sent: never « Envoyé »
    assert run_status(events) == "error" and session.state == "idle"


def test_a_reasoning_model_gets_a_turns_reasoning_reserve(index):
    session = ready(index)
    # The fake model cannot reason: the session's rule (`_reasoning_on`) said true here.
    session._reasoning_on = lambda state: True
    progress = [
        e.payload["total"]
        for e in run(session)
        if e.kind == "rag_lab_stage_progress" and e.payload["kind"] == "generation"
    ]
    assert set(progress) == {1536}


# ---------- « Arrêter », a failing model ----------


def test_stop_during_the_generation_keeps_the_partial_answer(index):
    session = ready(index, engine=FakeEngine(output="x" * 400, delay=0.005))
    mark = get_journal().last_seq()
    session.run_rag_lab(QUESTION)
    deadline = time.monotonic() + 10
    while time.monotonic() < deadline and not [
        e
        for e in get_journal().events_since(mark)
        if e.kind == "model_delta" and e.context_id == "rag_lab"
    ]:
        time.sleep(0.01)
    assert session.stop()
    wait_idle(session)
    events = [e for e in get_journal().events_since(mark) if e.context_id == "rag_lab"]
    generation = ended(events, "generation")
    assert generation["status"] == "cancelled" and generation["prompt_text"]
    assert generation["output_text"] and set(generation["output_text"]) == {"x"}
    assert len(generation["output_text"]) < 400
    assert run_status(events) == "cancelled"
    assert session.state == "idle" and session._cancel is None


def test_an_empty_answer_is_said(index):
    session = ready(index, engine=FakeEngine(output=""))
    generation = ended(run(session), "generation")
    assert generation["status"] == "ok"
    assert generation["output_text"] == "Le modèle n'a rien répondu."


def test_a_failing_model_errs_the_stage_and_the_session_comes_back(index):
    session = ready(index)
    session._engine.fail = True
    events = run(session)
    generation = ended(events, "generation")
    assert generation["status"] == "error"
    assert generation["error_text"] == "L'étape a échoué (RuntimeError : moteur en panne)."
    assert QUESTION in generation["prompt_text"]  # the prompt rendered stays shown
    errors = [e for e in events if e.kind == "harness_error"]
    assert errors and errors[-1].brick is None  # traced, never on the RAG brick's card
    assert run_status(events) == "error" and session.state == "idle"


# ---------- the main context's cache ----------


def test_the_turn_after_a_run_keeps_its_prefix(index):
    session = ready(index)
    session.send("Bonjour")
    session.join()
    run(session)
    mark = get_journal().last_seq()
    session.send("Et ensuite ?")
    session.join()
    assert session._engine.restores == 1
    events = get_journal().events_since(mark)
    causes = [e.payload["cause"] for e in events if e.kind == "prefix_not_reused"]
    assert "rag_lab" not in causes


def test_a_stateless_engine_says_the_rag_workshop_took_its_cache(index):
    session = ready(index, engine=FakeEngine(output=ANSWER, stateful=False))
    session.send("Bonjour")
    session.join()
    run(session)
    mark = get_journal().last_seq()
    session.send("Et ensuite ?")
    session.join()
    causes = [e.payload for e in get_journal().events_since(mark) if e.kind == "prefix_not_reused"]
    assert [c["cause"] for c in causes] == ["rag_lab"]
    assert causes[0]["message_text"].startswith(
        "L'Atelier RAG a occupé le cache du moteur pour sa génération"
    )


# ---------- a cloud model ----------


def cloud_session(index: Path, provider: Provider) -> AppSession:
    place_model()
    place_reranker()
    shipped = config.load_config()
    cfg = config.Config(values=config._deep_merge(shipped.values, rerank_config(index)))
    entry = cfg.cloud_model("groq")
    config.write_api_key(entry.id, entry.host, SecretStr(SENTINEL))
    session = AppSession(
        cfg,
        cloud_factory=provider.factory,
        embedder_factory=Embedders(),
        reranker_factory=Rerankers(),
    )
    session.boot_cloud(entry).result()
    session.join()
    return session


def test_a_cloud_model_answers_and_the_session_pays(index):
    provider = Provider(GROQ_TEXT)
    session = cloud_session(index, provider)
    mark = get_journal().last_seq()
    events = run(session)

    generation = ended(events, "generation")
    assert generation["status"] == "ok" and generation["output_text"] == "Il est 9 h."
    assert QUESTION in generation["prompt_text"] and '"messages"' in generation["prompt_text"]
    facts = {f["label_text"]: f["value_text"] for f in generation["facts"]}
    assert facts["Tokens du prompt"].startswith("≈ ")
    assert len(provider.requests) == 1
    every = get_journal().events_since(mark)
    assert all(e.turn_id is None for e in every)
    assert [e for e in every if e.kind == "consumption_updated"]
    assert not [e for e in every if e.kind == "context_reconciled"]


# ---------- languages ----------


@pytest.mark.parametrize(
    ("lang", "option", "sent", "produced", "cut"),
    [
        (
            "en",
            "The workshop's active model: ",
            "Sent to the workshop's active model",
            "Tokens produced",
            "Answer cut at 512 tokens",
        ),
        (
            "de",
            "Aktives Modell der Werkstatt: ",
            "An das aktive Modell der Werkstatt gesendet",
            "Erzeugte Tokens",
            "Antwort bei 512 Tokens abgeschnitten",
        ),
    ],
)
def test_options_facts_and_warnings_are_translated(index, lang, option, sent, produced, cut):
    session = ready(index, engine=FakeEngine(output="x" * 600))
    session.set_language(lang)
    options = generation_options(session)
    assert options["active"]["label_text"].startswith(option)
    assert options["not_run"]["label_text"] in ("Do not generate", "Nicht generieren")
    generation = ended(run(session, QUESTION, own_chain(session)), "generation")
    assert generation["input_text"].startswith(sent)
    assert produced in {f["label_text"] for f in generation["facts"]}
    assert generation["warning_text"].startswith(cut)


@pytest.mark.parametrize("lang", ["en", "de"])
def test_the_reasons_are_translated(index, lang):
    place_model()
    place_reranker()
    session = AppSession(
        config.Config(values=rerank_config(index)),
        embedder_factory=Embedders(),
        reranker_factory=Rerankers(),
    )
    session.boot(None).result()
    session.join()
    session.set_language(lang)
    note = generation_options(session)["active"]["note_text"]
    assert note.startswith({"en": "No model loaded", "de": "Kein Modell"}[lang])
    generation = ended(run(session, QUESTION, own_chain(session)), "generation")
    assert generation["error_text"].startswith({"en": "No model", "de": "Kein Modell"}[lang])


def test_a_provider_error_errs_the_stage_with_its_message(index):
    refused = httpx.Response(500, json={"error": {"message": "Internal error"}})
    session = cloud_session(index, Provider(refused))
    events = run(session)
    generation = ended(events, "generation")
    assert generation["status"] == "error" and "Internal error" in generation["error_text"]
    assert QUESTION in generation["prompt_text"]
    (error,) = [e.payload for e in events if e.kind == "harness_error"]
    assert error["effect_text"].startswith("La génération de l'Atelier RAG s'arrête")
    assert run_status(events) == "error" and session.state == "idle"
