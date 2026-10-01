"""Story 30: the RAG workshop, a RAG chain drawn and run apart from the RAG brick (AD-1,
AD-2, AD-3, AD-8, AD-20, AD-22, AD-24).

The index is built with the real code of `rag/` and `FakeEmbedder`; the reranker is
`FakeReranker`. Nothing touches the network, and no real model is needed.
"""

from __future__ import annotations

import math
import threading
import time
from pathlib import Path

import pytest
from fake_reranker import FakeReranker
from starlette.testclient import TestClient
from test_bricks import HEADERS
from test_rag import COVERED, Embedders, build, place_model
from test_rag_rerank import Rerankers, place_reranker, rerank_config, session_for

from wavestack import config
from wavestack.models.load_registry import EMBEDDING, RERANKER
from wavestack.rag import lab as rag_lab
from wavestack.rag.corpus import load_rag_content
from wavestack.session.app_session import AppSession, SendRefused
from wavestack.session.diagnostic import DiagnosticSession
from wavestack.trace.journal import get_journal
from wavestack.web.app import create_app

QUESTION = "Combien de jours de télétravail par semaine ?"
KINDS = ["chunking", "embedding", "vector_store", "vector_search", "rerank", "context"]


@pytest.fixture
def index(tmp_path) -> Path:
    path = tmp_path / "rag_index.sqlite"
    build(path)
    return path


def lab_session(values: dict, **kwargs) -> tuple[AppSession, Rerankers]:
    """A booted session, the RAG brick off: the workshop loads its own models."""
    kwargs.setdefault("rerank", False)
    kwargs.setdefault("bricks", ())
    return session_for(values, **kwargs)


def wait_idle(session: AppSession) -> None:
    deadline = time.monotonic() + 10
    while time.monotonic() < deadline and session.state != "idle":
        time.sleep(0.01)
    session.join()


def run(session: AppSession, question: str = QUESTION, pipelines=None) -> list:  # noqa: ANN001
    """One run, the worker joined: the events of the workshop's context."""
    mark = get_journal().last_seq()
    session.run_rag_lab(question, pipelines)
    wait_idle(session)
    return [e for e in get_journal().events_since(mark) if e.context_id == "rag_lab"]


def ended(events: list, kind: str, lane: str = "a") -> dict:
    found = [
        e.payload
        for e in events
        if e.kind == "rag_lab_stage_ended"
        and e.payload["kind"] == kind
        and e.payload["lane"] == lane
    ]
    assert len(found) == 1, (kind, len(found))
    return found[0]


def run_status(events: list) -> str:
    return next(e.payload["status"] for e in events if e.kind == "rag_lab_run_ended")


def ready(index: Path, **kwargs) -> tuple[AppSession, Rerankers]:
    place_model()
    place_reranker()
    return lab_session(rerank_config(index), **kwargs)


# ---------- the shipped chain ----------


def test_the_shipped_chain_runs_each_stage(index):
    session, rerankers = ready(index)
    events = run(session)
    kinds = [e.kind for e in events]
    assert kinds[0] == "rag_lab_run_started" and kinds[-1] == "rag_lab_run_ended"
    started = [e.payload["kind"] for e in events if e.kind == "rag_lab_stage_started"]
    assert started == KINDS  # one pair per stage run, none for the generation
    for kind in KINDS:
        stage = ended(events, kind)
        assert stage["status"] == "ok", (kind, stage["error_text"])
        assert stage["duration_ms"] >= 0 and stage["rss_bytes"] and "Mo" in stage["memory_text"]
    # Scope (AD-2): no turn, the workshop's context, its own components.
    first = next(e for e in events if e.kind == "rag_lab_stage_started")
    assert first.turn_id is None and first.step_id == "lab1.a.s1"
    assert first.brick == "rag" and first.component == "rag_lab.chunking"
    assert (first.actor, first.trigger) == ("harness", "user")

    chunking = ended(events, "chunking")
    assert "29 extraits" in chunking["output_text"]
    search = ended(events, "vector_search")
    assert [i["rank"] for i in search["items"]] == list(range(1, 9))  # rerank_candidates
    assert all(i["before"] is None for i in search["items"])
    scores = [i["score"] for i in search["items"]]
    assert scores == sorted(scores, reverse=True)
    assert search["items"][0]["doc_id"] == "teletravail"

    rerank = ended(events, "rerank")
    assert sorted(i["before"] for i in rerank["items"]) == list(range(1, 9))
    scores = [(i["score"], i["before"]) for i in rerank["items"]]
    assert scores == sorted(scores, key=lambda x: (-x[0], x[1]))  # stable, as the brick's
    assert rerank["items"][0]["sources"][0]["kind"] == "vector_search"

    context = ended(events, "context")
    content = load_rag_content()
    kept = rerank["items"][:3]
    assert [i["chunk_id"] for i in context["items"]] == [i["chunk_id"] for i in kept]
    for position, item in enumerate(context["items"], start=1):
        assert item["text"].startswith(f"Extrait {position} — {item['title_text']} :\n")
    assert context["output_text"].startswith(content.intro_text)

    generation = ended(events, "generation")
    assert generation["status"] == "not_run" and generation["rss_bytes"] is None
    assert "Non exécutée dans l'atelier RAG" in generation["output_text"]
    assert "3 extraits" in generation["input_text"]
    assert run_status(events) == "ok" and session.state == "idle"
    assert rerankers.made and rerankers.made[0].calls[0][0] == QUESTION


def test_models_loaded_for_the_run_are_closed_and_their_slots_freed(index):
    session, rerankers = ready(index)
    embedders = session._embedder_factory
    events = run(session)
    assert not ended(events, "embedding")["borrowed"]
    assert len(embedders.made) == 1 and embedders.made[0].closed
    assert len(rerankers.made) == 1 and rerankers.made[0].closed
    registry = session._load_registry
    assert registry.holder(EMBEDDING) is None and registry.holder(RERANKER) is None


def test_the_bricks_models_are_borrowed_never_closed_nor_granted_again(index):
    place_model()
    place_reranker()
    session, rerankers = session_for(rerank_config(index))  # the RAG brick and its reranking
    embedders = session._embedder_factory
    assert len(embedders.made) == 1 and len(rerankers.made) == 1
    registry = session._load_registry
    grants = []
    original = registry.grant
    registry.grant = lambda *a, **k: (grants.append(a), original(*a, **k))  # type: ignore[method-assign]
    events = run(session)
    assert ended(events, "embedding")["borrowed"] and ended(events, "rerank")["borrowed"]
    assert len(embedders.made) == 1 and not embedders.made[0].closed
    assert len(rerankers.made) == 1 and not rerankers.made[0].closed
    assert grants == []
    assert registry.holder(EMBEDDING) and registry.holder(RERANKER)
    assert session._embedder is embedders.made[0]  # the brick's state is unchanged


# ---------- the I/O matrix ----------


def test_busy_session_refuses_the_run_and_emits_nothing(index):
    session, _ = ready(index)
    session._set_state("turn", None)
    mark = get_journal().last_seq()
    with pytest.raises(SendRefused) as refused:
        session.run_rag_lab(QUESTION)
    assert "tour" in refused.value.reason_text
    assert not [e for e in get_journal().events_since(mark) if e.kind.startswith("rag_lab")]


def test_a_reason_in_idle_does_not_prevent_the_run_and_comes_back(index):
    session, _ = ready(index)
    session._set_state("idle", "Aucun modèle n'est chargé.")
    events = run(session)
    assert run_status(events) == "ok"
    assert (session.state, session.reason_text) == ("idle", "Aucun modèle n'est chargé.")


def test_the_workshop_state_while_running_refuses_the_workshop(index):
    session, rerankers = ready(index)
    gate = threading.Event()
    rerankers.gate = gate  # holds the reranker's load: the run stays in `rag_lab`
    session.run_rag_lab(QUESTION)
    assert session.state == "rag_lab" and "Atelier RAG : exécution en cours" in session.reason_text
    with pytest.raises(SendRefused) as refused:
        session.send("Bonjour")
    assert "Atelier RAG : exécution en cours" in refused.value.reason_text
    gate.set()
    wait_idle(session)


def test_index_absent_the_store_fails_with_the_bricks_reason(index):
    session, _ = ready(index)
    index.unlink()
    events = run(session)
    store = ended(events, "vector_store")
    assert store["status"] == "error" and "index absent" in store["error_text"]
    for kind in ("vector_search", "rerank", "context", "generation"):
        assert ended(events, kind)["status"] == "skipped"
    assert run_status(events) == "error" and session.state == "idle"


def test_embedding_model_absent(index):
    place_reranker()
    session, _ = lab_session(rerank_config(index))
    events = run(session)
    embedding = ended(events, "embedding")
    assert embedding["status"] == "error"
    assert "Téléchargez-le depuis la carte RAG de l'atelier" in embedding["error_text"]
    assert ended(events, "vector_store")["status"] == "skipped"
    assert run_status(events) == "error"


def test_reranker_absent_the_stage_is_skipped_and_the_search_order_kept(index):
    place_model()
    session, _ = lab_session(rerank_config(index))
    events = run(session)
    rerank = ended(events, "rerank")
    assert rerank["status"] == "skipped" and "carte RAG" in rerank["error_text"]
    search = ended(events, "vector_search")
    context = ended(events, "context")
    assert [i["chunk_id"] for i in context["items"]] == [i["chunk_id"] for i in search["items"][:3]]
    assert run_status(events) == "ok"


def test_reranker_failing_the_stage_errs_and_the_run_goes_on(index):
    place_model()
    place_reranker()
    session, _ = lab_session(rerank_config(index), rerankers=Rerankers(fail=True))
    events = run(session)
    rerank = ended(events, "rerank")
    assert rerank["status"] == "error" and "reranking a échoué" in rerank["error_text"]
    search = ended(events, "vector_search")
    assert [i["chunk_id"] for i in ended(events, "context")["items"]] == [
        i["chunk_id"] for i in search["items"][:3]
    ]
    assert session._load_registry.holder(RERANKER) is None


def test_budget_refusal_nothing_is_loaded(index):
    place_model()
    place_reranker()
    session, _ = lab_session(rerank_config(index, budget_mb=100), rss=200 * 1024**2)
    embedders = session._embedder_factory
    events = run(session)
    embedding = ended(events, "embedding")
    assert embedding["status"] == "error" and "Mémoire insuffisante" in embedding["error_text"]
    assert "Mo" in embedding["error_text"] and embedders.made == []
    assert session._load_registry.holder(EMBEDDING) is None


def test_stop_during_the_reranking(index):
    place_model()
    place_reranker()
    holder: dict = {}

    def factory(model):  # noqa: ANN001, ANN202
        reranker = FakeReranker(model_id=model.id)
        reranker.before_each = lambda: holder["session"].stop()
        return reranker

    session, _ = lab_session(rerank_config(index), rerankers=factory)
    holder["session"] = session
    events = run(session)
    assert ended(events, "rerank")["status"] == "cancelled"
    assert ended(events, "context")["status"] == "skipped"
    assert ended(events, "generation")["status"] == "skipped"
    assert run_status(events) == "cancelled"
    assert session.state == "idle" and session._cancel is None
    assert session._load_registry.holder(RERANKER) is None


def test_stop_between_two_stages(index):
    session, _ = ready(index)
    original = session._rag_lab_embedder

    def embedder(option, loans):  # noqa: ANN001, ANN202
        lent = original(option, loans)
        real = lent.model

        class Stopping:  # « Arrêter » while the question is embedded: seen before the next stage
            model_id, dims = real.model_id, real.dims

            def embed_queries(self, texts):  # noqa: ANN001, ANN202
                session.stop()
                return real.embed_queries(texts)

            def embed_passages(self, texts):  # noqa: ANN001, ANN202
                return real.embed_passages(texts)

        lent.model = Stopping()
        return lent

    session._rag_lab_embedder = embedder  # type: ignore[method-assign]
    events = run(session)
    assert ended(events, "embedding")["status"] == "ok"
    assert ended(events, "vector_store")["status"] == "cancelled"
    assert ended(events, "vector_search")["status"] == "skipped"
    assert run_status(events) == "cancelled"


def chains(session: AppSession) -> tuple[rag_lab.Catalog, rag_lab.Pipeline, rag_lab.Pipeline]:
    """The catalog, the shipped chain A, and a copy B to change."""
    catalog = session._rag_lab_catalog(rag_lab.load_lab_content())
    b = catalog.default.model_copy(deep=True)
    b.label_text = "B"
    return catalog, catalog.default, b


def stage(pipeline: rag_lab.Pipeline, kind: str) -> rag_lab.Stage:
    found = pipeline.find(kind)
    assert found is not None
    return found


@pytest.mark.parametrize(
    ("kind", "change", "said"),
    [
        ("chunking", {"params": {"chunk_max_chars": 150}}, "entre 200 et 1 500 caractères"),
        ("chunking", {"params": {"chunk_max_chars": 1600}}, "entre 200 et 1 500"),
        ("vector_search", {"params": {"candidates": 0}}, "entre 1 et 20"),
        ("context", {"params": {"top_k": 21}}, "entre 1 et 20"),
        ("vector_search", {"params": {"candidates": 2}}, "moins que les 3 extraits"),
        ("vector_store", {"option": "annoy"}, "« annoy » n'existe pas"),
        ("embedding", {"option": "fastembed"}, "fastembed n'est pas installé"),
        ("chunking", {"params": {"top_k": 3}}, "réglage inconnu"),
    ],
)
def test_bounds_and_refusals_name_the_stage(index, kind, change, said):
    session, _ = ready(index)
    catalog, _, b = chains(session)
    target = stage(b, kind)
    for key, value in change.items():
        setattr(target, key, value)
    reason = (rag_lab.validate_pipeline(b, catalog) or "").replace("\u202f", " ")
    label = catalog.content.stages[kind].label_text
    assert f"« {label} »" in reason and said in reason, reason
    mark = get_journal().last_seq()
    with pytest.raises(SendRefused):
        session.run_rag_lab(QUESTION, [catalog.default, b])
    assert not [e for e in get_journal().events_since(mark) if e.kind.startswith("rag_lab")]


def add(pipeline: rag_lab.Pipeline, kind: str, option: str, **params: int) -> rag_lab.Stage:
    """A stage of the retrieval, inserted before the context (as the page does)."""
    new = rag_lab.Stage(id=f"x{len(pipeline.stages)}", kind=kind, option=option, params=params)
    at = next(i for i, s in enumerate(pipeline.stages) if s.kind == "context")
    pipeline.stages.insert(at, new)
    return new


def remove(pipeline: rag_lab.Pipeline, kind: str) -> None:
    pipeline.stages = [s for s in pipeline.stages if s.kind != kind]


def move(pipeline: rag_lab.Pipeline, kind: str, before: str) -> None:
    moved = stage(pipeline, kind)
    pipeline.stages.remove(moved)
    at = next(i for i, s in enumerate(pipeline.stages) if s.kind == before)
    pipeline.stages.insert(at, moved)


def refusal(session: AppSession, pipeline: rag_lab.Pipeline) -> tuple[str, str | None]:
    catalog = session._rag_lab_catalog(rag_lab.load_lab_content())
    found = rag_lab.check_pipeline(pipeline, catalog)
    assert found is not None
    return found


def test_rules_of_the_chain_each_refusal_names_the_stage(index):
    session, _ = ready(index)
    _, _, b = chains(session)

    fixed = b.model_copy(deep=True)
    remove(fixed, "embedding")
    reason, stage_id = refusal(session, fixed)
    assert "« Embedding »" in reason and "fixe" in reason

    fixed = b.model_copy(deep=True)
    move(fixed, "context", "rerank")  # the context among the retrieval
    reason, stage_id = refusal(session, fixed)
    assert "« Construction du contexte »" in reason and stage_id == stage(fixed, "context").id

    none = b.model_copy(deep=True)
    remove(none, "vector_search")
    remove(none, "rerank")
    reason, stage_id = refusal(session, none)
    assert "aucune recherche" in reason and stage_id == stage(none, "context").id

    two = b.model_copy(deep=True)
    remove(two, "rerank")
    bm25 = add(two, "lexical_search", "bm25", candidates=8)
    reason, stage_id = refusal(session, two)
    assert reason.startswith("Deux recherches demandent une fusion après elles")
    assert "« Recherche lexicale BM25 »" in reason and stage_id == bm25.id

    fused = two.model_copy(deep=True)
    fusion = add(fused, "fusion", "rrf")
    assert (
        rag_lab.check_pipeline(fused, session._rag_lab_catalog(rag_lab.load_lab_content())) is None
    )
    move(fused, "fusion", "lexical_search")  # before the second search
    reason, stage_id = refusal(session, fused)
    assert "« Fusion »" in reason and "après les deux recherches" in reason
    assert stage_id == fusion.id

    alone = b.model_copy(deep=True)
    add(alone, "fusion", "rrf")
    reason, stage_id = refusal(session, alone)
    assert "« Fusion »" in reason and "deux recherches avant elle" in reason

    early = b.model_copy(deep=True)
    move(early, "rerank", "vector_search")
    reason, stage_id = refusal(session, early)
    assert "« Reranking »" in reason and stage_id == stage(early, "rerank").id

    twice = b.model_copy(deep=True)
    twice.stages.insert(4, rag_lab.Stage(id="dup", kind="vector_search", option="cosine"))
    reason, stage_id = refusal(session, twice)
    assert "« Recherche »" in reason and "qu'une fois" in reason and stage_id == "dup"

    few = two.model_copy(deep=True)
    add(few, "fusion", "rrf")
    stage(few, "lexical_search").params["candidates"] = 2
    reason, stage_id = refusal(session, few)
    assert "« Recherche lexicale BM25 »" in reason and "moins que les 3 extraits" in reason

    mark = get_journal().last_seq()
    with pytest.raises(SendRefused) as refused:
        session.run_rag_lab(QUESTION, [fused])
    assert "« Fusion »" in refused.value.reason_text
    assert not [e for e in get_journal().events_since(mark) if e.kind.startswith("rag_lab")]


def test_bm25_ranks_a_hand_written_corpus():
    docs = ["Le chat mange.", "Le chien aboie fort.", "Chat, chat noir !", "Un chat noir dort."]
    scores = rag_lab.bm25("le chat noir", docs)
    assert rag_lab.bm25_terms("Le chat NOIR, un œil") == ["chat", "noir", "œil"]  # 3 letters+
    assert scores[1] == 0  # no word shared (« le » is too short)
    ranked = sorted(range(4), key=lambda i: -scores[i])
    assert ranked[:3] == [2, 3, 0]  # « chat » twice and « noir », then the shorter one
    n, mean = 4, (2 + 3 + 3 + 3) / 4  # words of 3 letters or more: « un » is not one
    idf_chat = math.log(1 + (n - 3 + 0.5) / (3 + 0.5))
    tf_norm = 1 + 1.5 * (1 - 0.75 + 0.75 * 2 / mean)
    assert scores[0] == pytest.approx(idf_chat * 2.5 / tf_norm)


def test_rrf_fuses_reciprocal_ranks():
    fused = rag_lab.rrf([[1, 2, 3], [3, 1, 4]])
    assert [i for i, _ in fused] == [1, 3, 2, 4]
    assert fused[0][1] == pytest.approx(1 / 61 + 1 / 62)
    assert fused[1][1] == pytest.approx(1 / 63 + 1 / 61)
    assert fused[3][1] == pytest.approx(1 / 63)


def test_a_hybrid_chain_runs_bm25_the_fusion_then_the_reranking(index):
    session, _ = ready(index)
    _, a, b = chains(session)
    hybrid = a.model_copy(deep=True)
    remove(hybrid, "rerank")
    add(hybrid, "lexical_search", "bm25", candidates=8)
    add(hybrid, "fusion", "rrf")
    add(hybrid, "rerank", "declared")  # the reranking after the fusion
    events = run(session, QUESTION, [hybrid])
    assert run_status(events) == "ok"
    vector = ended(events, "vector_search")["items"]
    lexical = ended(events, "lexical_search")
    assert lexical["status"] == "ok" and 0 < len(lexical["items"]) <= 8
    assert all(i["score"] > 0 for i in lexical["items"])
    fusion = ended(events, "fusion")
    ids = {i["chunk_id"] for i in vector} | {i["chunk_id"] for i in lexical["items"]}
    assert {i["chunk_id"] for i in fusion["items"]} == ids
    ranks = {
        kind: {i["chunk_id"]: i["rank"] for i in items}
        for kind, items in (("vector_search", vector), ("lexical_search", lexical["items"]))
    }
    for item in fusion["items"]:
        sources = {src["kind"]: src["rank"] for src in item["sources"]}
        assert sources == {kind: ranks[kind].get(item["chunk_id"]) for kind in ranks}
        expected = sum(1 / (60 + r) for r in sources.values() if r is not None)
        assert item["score"] == pytest.approx(expected, abs=1e-4)
    rerank = ended(events, "rerank")
    assert sorted(i["before"] for i in rerank["items"]) == list(range(1, len(fusion["items"]) + 1))
    assert rerank["items"][0]["sources"][0]["kind"] == "vector_search"  # the fusion's sources
    context = ended(events, "context")
    assert [i["chunk_id"] for i in context["items"]] == [i["chunk_id"] for i in rerank["items"][:3]]


def test_bm25_alone_is_a_chain(index):
    session, _ = ready(index)
    _, a, _ = chains(session)
    lexical = a.model_copy(deep=True)
    remove(lexical, "vector_search")
    remove(lexical, "rerank")
    add(lexical, "lexical_search", "bm25", candidates=5)
    events = run(session, "Combien de jours de télétravail ?", [lexical])
    assert run_status(events) == "ok"
    items = ended(events, "context")["items"]
    assert len(items) == 3 and items[0]["doc_id"] == "teletravail"


def test_the_memory_search_ranks_as_sqlite_vec(index):
    session, _ = ready(index)
    catalog, a, b = chains(session)
    stage(b, "vector_store").option = "memory"
    for question in (QUESTION, COVERED, "Quel plafond pour une nuit d'hôtel à Paris ?"):
        events = run(session, question, [a, b])
        searched = [ended(events, "vector_search", lane)["items"] for lane in "ab"]
        assert [(i["chunk_id"], i["score"]) for i in searched[0]] == [
            (i["chunk_id"], i["score"]) for i in searched[1]
        ], question
        comparison = next(e for e in events if e.kind == "rag_lab_run_ended").payload["comparison"]
        assert comparison["basis"] == "excerpt"
        assert len(comparison["common"]) == 3 and not comparison["rank_changes"]
        assert not comparison["only_a"] and not comparison["only_b"]


def test_the_vectors_cache_is_read_again_and_rebuilt_when_the_size_changes(index):
    session, _ = ready(index)
    catalog, a, b = chains(session)
    stage(b, "chunking").params["chunk_max_chars"] = 300
    stage(b, "vector_store").option = "memory"
    stage(b, "context").params["top_k"] = 2
    first = run(session, QUESTION, [a, b])
    embedding = ended(first, "embedding", "b")
    assert "calculés (77 passages)" in embedding["output_text"]
    progress = [
        e for e in first if e.kind == "rag_lab_stage_progress" and e.payload["kind"] == "embedding"
    ]
    assert progress and progress[-1].payload["done"] == progress[-1].payload["total"] == 77
    assert len(ended(first, "context", "b")["items"]) == 2
    folders = list(config.rag_lab_dir().iterdir())
    assert len(folders) == 1
    assert {p.name for p in folders[0].iterdir()} == {"chunks.json", "vectors.f32"}
    second = run(session, QUESTION, [a, b])
    assert "relus du cache" in ended(second, "embedding", "b")["output_text"]
    assert (
        ended(second, "vector_search", "b")["items"] == ended(first, "vector_search", "b")["items"]
    )
    stage(b, "chunking").params["chunk_max_chars"] = 1200
    third = run(session, QUESTION, [a, b])
    assert "calculés (16 passages)" in ended(third, "embedding", "b")["output_text"]
    assert len(list(config.rag_lab_dir().iterdir())) == 2
    comparison = next(e for e in third if e.kind == "rag_lab_run_ended").payload["comparison"]
    assert comparison["basis"] == "document" and "par document" in comparison["summary_text"]


def test_sqlite_vec_of_another_size_is_built_in_the_workshops_folder(index):
    session, _ = ready(index)
    before = index.stat().st_mtime_ns
    catalog, a, _ = chains(session)
    stage(a, "chunking").params["chunk_max_chars"] = 300
    first = run(session, QUESTION, [a])
    store = ended(first, "vector_store")
    assert store["status"] == "ok" and "construit (77 vecteurs)" in store["output_text"]
    second = run(session, QUESTION, [a])
    assert "relu" in ended(second, "vector_store")["output_text"]
    assert index.stat().st_mtime_ns == before  # the brick's index is never written
    built = list(config.rag_lab_dir().glob("*/index.sqlite"))
    assert len(built) == 1
    assert not list(config.rag_lab_dir().rglob("*.tmp"))


def test_stop_while_the_passages_are_embedded_leaves_no_file(index):
    session, _ = ready(index)
    catalog, a, _ = chains(session)
    stage(a, "chunking").params["chunk_max_chars"] = 300
    stage(a, "vector_store").option = "memory"
    original = session._rag_lab_embedder

    def embedder(option, loans):  # noqa: ANN001, ANN202
        lent = original(option, loans)
        real = lent.model
        seen = []

        class Stopping:
            model_id, dims = real.model_id, real.dims

            def embed_queries(self, texts):  # noqa: ANN001, ANN202
                return real.embed_queries(texts)

            def embed_passages(self, texts):  # noqa: ANN001, ANN202
                seen.append(texts)
                if len(seen) == 3:  # batches of 8 passages: 3 of 10
                    session.stop()
                return real.embed_passages(texts)

        lent.model = Stopping()
        return lent

    session._rag_lab_embedder = embedder  # type: ignore[method-assign]
    events = run(session, QUESTION, [a])
    assert ended(events, "embedding")["status"] == "cancelled"
    assert run_status(events) == "cancelled"
    assert not config.rag_lab_dir().exists() or not list(config.rag_lab_dir().rglob("*"))


class FakeTextEmbedding:
    """fastembed's `TextEmbedding`, faked: the fake bag of words, what it was opened with."""

    opened: list[dict] = []

    def __init__(self, **kwargs) -> None:  # noqa: ANN003
        FakeTextEmbedding.opened.append(kwargs)

    def query_embed(self, texts):  # noqa: ANN001, ANN201
        from fake_embedder import vector

        return iter([vector(t) for t in texts])

    passage_embed = query_embed


def test_fastembed_unavailable_without_the_package_then_available(index, monkeypatch):
    import importlib.machinery
    import sys
    import types

    session, _ = ready(index)
    options = {
        (s["kind"], o["id"]): o
        for s in session.rag_lab_state()["catalog"]["stages"]
        for o in s["options"]
    }
    fastembed = options[("embedding", "fastembed")]
    assert not fastembed["available"] and "pas installé" in fastembed["reason_text"]

    module = types.ModuleType("fastembed")
    module.__spec__ = importlib.machinery.ModuleSpec("fastembed", None)
    module.TextEmbedding = FakeTextEmbedding  # type: ignore[attr-defined]
    monkeypatch.setitem(sys.modules, "fastembed", module)
    reason = session._rag_lab_fastembed()[1]
    assert "[rag_lab.fastembed]" in reason  # installed, not declared
    values = rerank_config(index)
    values["rag_lab"] = {
        "fastembed": {"model_name": "fake/minilm", "dims": 64, "label_text": "Fast"}
    }
    session.cfg = config.Config(values=values)
    assert "ne sont pas dans" in session._rag_lab_fastembed()[1]  # no file
    folder = config.models_dir() / "fastembed" / "models--fake--minilm"
    folder.mkdir(parents=True)
    (folder / "model.onnx").write_bytes(b"\0" * 100)
    assert session._rag_lab_fastembed() == (session.cfg.rag_lab_fastembed[0], None)

    catalog, a, b = chains(session)
    assert catalog.options[("embedding", "fastembed")].label_text == "Fast"
    stage(b, "embedding").option = "fastembed"
    events = run(session, QUESTION, [a, b])
    embedding = ended(events, "embedding", "b")
    assert embedding["status"] == "ok" and "calculés (29 passages)" in embedding["output_text"]
    assert FakeTextEmbedding.opened[-1]["local_files_only"] is True
    assert ended(events, "vector_store", "b")["status"] == "ok"  # its own sqlite-vec index
    assert session._load_registry.holder("rag_lab.embedding") is None
    # The library (fastembed, onnxruntime) is counted for life, apart from the model.
    assert session._load_registry.holder("rag_lab.fastembed") == "fastembed"


def test_fastembed_invalid_section_says_why(index):
    session, _ = ready(index)
    values = rerank_config(index)
    values["rag_lab"] = {"fastembed": {"model_name": "fake/minilm", "dims": 0, "label_text": "F"}}
    session.cfg = config.Config(values=values)
    model, reason = session.cfg.rag_lab_fastembed
    assert model is None and "[rag_lab.fastembed] est invalide (dims)" in reason


def test_fastembed_checks_the_declared_models_own_folder(index, monkeypatch):
    import importlib.machinery
    import sys
    import types

    module = types.ModuleType("fastembed")
    module.__spec__ = importlib.machinery.ModuleSpec("fastembed", None)
    monkeypatch.setitem(sys.modules, "fastembed", module)
    session, _ = ready(index)
    values = rerank_config(index)
    values["rag_lab"] = {"fastembed": {"model_name": "fake/minilm", "dims": 64, "label_text": "F"}}
    session.cfg = config.Config(values=values)
    other = config.models_dir() / "fastembed" / "models--other--model"
    other.mkdir(parents=True)
    (other / "model.onnx").write_bytes(b"\0")  # another model's file does not count
    assert "models--fake--minilm" in session._rag_lab_fastembed()[1]


# ---------- review: settings, run's end, loans, brick switched off, BM25 ----------


def test_settings_omitted_are_the_bricks_own_rag_values(index):
    place_model()
    place_reranker()
    values = rerank_config(index)
    values["rag"]["top_k"], values["rag"]["rerank_candidates"] = 4, 10
    session, _ = lab_session(values)
    catalog = session._rag_lab_catalog(rag_lab.load_lab_content())
    bare = catalog.default.model_copy(deep=True)
    for s in bare.stages:
        s.params = {}  # every setting left to the catalog's values ([rag])
    assert rag_lab.validate_pipeline(bare, catalog) is None
    events = run(session, QUESTION, [bare])
    assert "700 caractères" in ended(events, "chunking")["output_text"]
    assert len(ended(events, "vector_search")["items"]) == 10
    assert len(ended(events, "context")["items"]) == 4


def test_the_run_always_ends_even_when_the_comparison_fails(index, monkeypatch):
    session, _ = ready(index)
    _, a, b = chains(session)

    def broken(*args):  # noqa: ANN002, ANN202
        raise RuntimeError("comparaison cassée")

    monkeypatch.setattr(rag_lab, "compare", broken)
    events = run(session, QUESTION, [a, b])
    assert run_status(events) == "error" and session.state == "idle"


def test_the_run_always_ends_even_when_an_event_cannot_be_emitted(index):
    session, _ = ready(index)
    real = session._rag_lab_emit
    failed = []

    def emit(kind, payload, step_id, component):  # noqa: ANN001, ANN202
        if kind == "rag_lab_stage_ended" and not failed:
            failed.append(kind)
            raise ValueError("émission impossible")
        return real(kind, payload, step_id, component)

    session._rag_lab_emit = emit  # type: ignore[method-assign]
    events = run(session)
    ends = [e for e in events if e.kind == "rag_lab_run_ended"]
    assert len(ends) == 1 and ends[0].payload["status"] == "error"
    assert session.state == "idle" and session._cancel is None


def test_two_lanes_load_each_model_once(index):
    session, rerankers = ready(index)
    embedders = session._embedder_factory
    grants = []
    registry = session._load_registry
    original = registry.grant
    registry.grant = lambda *a, **k: (grants.append(a[2] if len(a) > 2 else a), original(*a, **k))  # type: ignore[method-assign]
    _, a, b = chains(session)
    stage(b, "vector_store").option = "memory"
    events = run(session, QUESTION, [a, b])
    assert run_status(events) == "ok"
    assert len(embedders.made) == 1 and len(rerankers.made) == 1
    assert sorted(grants) == ["embedding", "reranker"]
    assert embedders.made[0].closed and rerankers.made[0].closed
    assert registry.holder("embedding") is None and registry.holder("reranker") is None


def test_a_brick_switched_off_during_a_run_waits_for_its_end(index):
    place_model()
    place_reranker()
    session, rerankers = session_for(rerank_config(index))  # the brick holds both models
    embedder = session._embedder_factory.made[0]
    gate = threading.Event()
    rerankers.made[0].before_each = lambda: gate.wait(timeout=5)
    mark = get_journal().last_seq()
    session.run_rag_lab(QUESTION)
    deadline = time.monotonic() + 5
    while time.monotonic() < deadline and not [
        e
        for e in get_journal().events_since(mark)
        if e.kind == "rag_lab_stage_started" and e.payload["kind"] == "rerank"
    ]:
        time.sleep(0.01)
    session.set_brick("rag", False)  # class (a): its release waits on the worker
    time.sleep(0.1)
    assert not embedder.closed and session.state == "rag_lab"
    gate.set()
    wait_idle(session)
    session.join()
    events = [e for e in get_journal().events_since(mark) if e.context_id == "rag_lab"]
    for kind in KINDS:
        assert ended(events, kind)["status"] == "ok", kind
    assert ended(events, "embedding")["borrowed"] and run_status(events) == "ok"
    assert embedder.closed  # released by the brick, after the run


def test_the_bricks_index_unreadable_fails_the_chunking(index, monkeypatch):
    session, _ = ready(index)

    def broken(path):  # noqa: ANN001, ANN202
        raise OSError("disque illisible")

    monkeypatch.setattr(rag_lab.rag_index, "read_chunks", broken)
    events = run(session)
    chunking = ended(events, "chunking")
    assert chunking["status"] == "error" and "ne se lit pas" in chunking["error_text"]
    assert ended(events, "embedding")["status"] == "skipped"


def test_bm25_keeps_codes_and_numbers_folds_accents_drops_stop_words():
    terms = rag_lab.bm25_terms("L'IA et les RH : 35 jours de Télétravail")
    assert terms == ["ia", "rh", "35", "jours", "teletravail"]
    scores = rag_lab.bm25("télétravail RH", ["Le teletravail", "Les RH et la paie", "Autre"])
    assert scores[0] > 0 and scores[1] > 0 and scores[2] == 0


def test_bm25_drops_the_stop_words_of_the_sessions_language():
    """Restes du 2026-10-01: each language its short words; acronyms and numbers kept
    (« IT » and « US » are not English stop words: they name something)."""
    assert rag_lab.bm25_terms("What is the HR policy for IT and US staff in 2024?", "en") == [
        "hr",
        "policy",
        "it",
        "us",
        "staff",
        "2024",
    ]
    assert rag_lab.bm25_terms("Wie viele Tage Homeoffice gibt es für die HR und IT?", "de") == [
        "viele",
        "tage",
        "homeoffice",
        "gibt",
        "hr",
        "it",
    ]
    # French by default, and for a language WaveStack does not know.
    assert rag_lab.bm25_terms("le the der") == ["the", "der"]
    assert rag_lab.bm25_terms("le the der", "xx") == ["the", "der"]
    # The query's stop words never score: « the » alone finds nothing in English.
    docs = ["The remote work policy", "The expense policy", "Other"]
    assert rag_lab.bm25("the", docs, "en") == [0.0, 0.0, 0.0]
    assert rag_lab.bm25("the", docs, "fr")[0] > 0


def test_a_lexical_search_in_english_says_the_words_it_looked_for(index):
    place_model()
    place_reranker()
    session, _ = lab_session(rerank_config(index) | {"language": "en"})
    _, a, _ = chains(session)
    lexical = a.model_copy(deep=True)
    remove(lexical, "vector_search")
    remove(lexical, "rerank")
    stage(lexical, "vector_store").option = "memory"  # the brick's index is the French one
    add(lexical, "lexical_search", "bm25", candidates=5)
    events = run(session, "How many days of remote work are there for the HR team?", [lexical])
    searched = ended(events, "lexical_search")
    assert searched["status"] == "ok", searched["error_text"]
    # « how », « of », « are », « there », « for », « the »: English stop words, left out.
    words = "(“many”, “days”, “remote”, “work”, “hr”, “team”)"
    assert words in searched["input_text"], searched["input_text"]
    explain = rag_lab.load_lab_content("en").stages["lexical_search"].explain_text
    assert "English function words" in explain and "French" not in explain
    assert (
        "deutsche Füllwörter"
        in rag_lab.load_lab_content("de").stages["lexical_search"].explain_text
    )


def test_a_nan_score_counts_as_zero_and_counts_agree():
    assert rag_lab.top([(float("nan"), 1), (0.5, 2)], 2) == [(2, 0.5), (1, 0.0)]
    assert rag_lab.count_fr(1, "extrait") == "1 extrait"
    assert rag_lab.count_fr(1536, "extrait") == "1\u202f536 extraits"


# ---------- state, content, sandbox ----------


def test_state_catalog_default_chain_and_last_run(index):
    session, _ = ready(index)
    state = session.rag_lab_state()
    assert state["content"]["title_text"] and state["content_error_text"] is None
    stages = state["catalog"]["stages"]
    assert [s["kind"] for s in stages] == list(rag_lab.KINDS)
    assert state["catalog"]["insert_before"] == "context"
    movable = {s["kind"] for s in stages if s["movable"]}
    assert movable == {"vector_search", "lexical_search", "fusion", "rerank"}
    options = {s["kind"]: s["options"][0] for s in stages}
    assert options["embedding"]["label_text"] == "Faux embedding"
    assert options["rerank"]["label_text"] == "Faux reranker"
    assert options["vector_store"]["label_text"] == "sqlite-vec"
    assert options["chunking"]["params"][0] | {"label_text": ""} == {
        "name": "chunk_max_chars",
        "label_text": "",
        "unit_text": "caractères",
        "min": 200,
        "max": 1500,
        "default": 700,
    }
    assert [s["id"] for s in state["default_pipeline"]["stages"]] == [f"s{i}" for i in range(1, 8)]
    assert state["session_state"]["state"] == "idle"
    events = run(session)
    run_id = events[0].payload["run_id"]
    state = session.rag_lab_state()
    kinds = [e["kind"] for e in state["last_run"]]
    assert kinds[0] == "rag_lab_run_started" and kinds[-1] == "rag_lab_run_ended"
    assert all(e["payload"]["run_id"] == run_id for e in state["last_run"])
    assert len(state["last_run"]) == len(events)


def test_catalog_notes_say_what_a_run_would_meet(index):
    session, _ = lab_session(rerank_config(index))  # no model file, no reranker file
    index.unlink()
    options = {s["kind"]: s["options"][0] for s in session.rag_lab_state()["catalog"]["stages"]}
    assert "modèle absent" in options["embedding"]["note_text"]
    assert "index absent" in options["vector_store"]["note_text"]
    assert "modèle absent" in options["rerank"]["note_text"]
    assert all(o["available"] for o in options.values())


def test_invalid_content_is_said_and_refuses_the_run(index, monkeypatch):
    session, _ = ready(index)

    def broken():  # noqa: ANN202
        raise ValueError("fichier cassé")

    broken.cache_clear = lambda: None  # type: ignore[attr-defined]
    monkeypatch.setattr(rag_lab, "load_lab_content", broken)
    state = session.rag_lab_state()
    assert state["content"] is None and "content/rag_lab.yaml" in state["content_error_text"]
    assert state["catalog"] is None
    with pytest.raises(SendRefused):
        session.run_rag_lab(QUESTION)


def test_content_file_is_valid_and_names_every_kind():
    content = rag_lab.load_lab_content()
    assert set(content.stages) == set(rag_lab.KINDS)
    assert content.default_question_text == QUESTION


_SKIP = {".git", ".venv", "__pycache__", ".pytest_cache", ".ruff_cache", "screenshots"}


def _repo_files() -> dict[str, int]:
    root = config.repo_root()
    found = {}
    for path in root.rglob("*"):
        if _SKIP & set(path.relative_to(root).parts) or not path.is_file():
            continue
        found[str(path)] = path.stat().st_mtime_ns
    return found


def test_nothing_is_written_under_the_repository(index):
    session, _ = ready(index)
    before = _repo_files()
    run(session)
    assert _repo_files() == before


# ---------- the web layer ----------


def _client(session: AppSession) -> TestClient:
    app = create_app(
        DiagnosticSession(session.cfg, port=8421), port=8421, version="t", app_session=session
    )
    return TestClient(app, base_url="http://127.0.0.1:8421")


def test_web_page_state_and_intention(index):
    session, _ = ready(index)
    client = _client(session)
    assert client.get("/rag").status_code == 200
    body = client.get("/api/rag_lab").json()
    assert body["catalog"] and body["seq"] >= 0
    for question in ("", "   ", "x" * 501):
        refused = client.post(
            "/api/intentions/rag_lab_run", json={"question": question}, headers=HEADERS
        )
        assert refused.status_code == 422, question
        assert refused.json()["detail"].startswith("Intention invalide")
        assert "input" not in str(refused.json()["errors"])
    three = [body["default_pipeline"]] * 3
    too_many = client.post(
        "/api/intentions/rag_lab_run",
        json={"question": QUESTION, "pipelines": three},
        headers=HEADERS,
    )
    assert too_many.status_code == 422
    changed = body["default_pipeline"] | {}
    changed["stages"] = [dict(s) for s in changed["stages"]]
    changed["stages"][2]["option"] = "annoy"
    refused = client.post(
        "/api/intentions/rag_lab_run",
        json={"question": QUESTION, "pipelines": [changed]},
        headers=HEADERS,
    )
    assert refused.status_code == 409 and "Base vectorielle" in refused.json()["detail"]
    ok = client.post("/api/intentions/rag_lab_run", json={"question": QUESTION}, headers=HEADERS)
    assert ok.status_code == 200 and ok.json()["run_id"].startswith("lab")
    wait_idle(session)
    session._set_state("download", "Téléchargement du modèle d'embedding : 10 %")
    busy = client.post("/api/intentions/rag_lab_run", json={"question": QUESTION}, headers=HEADERS)
    assert busy.status_code == 409 and "Téléchargement" in busy.json()["detail"]
    session._set_state("idle")


def test_an_embedder_for_the_workshop_is_the_brick_factorys(index):
    """The fake embedder records its queries: the question is embedded once per run (the
    store's search reuses the vector)."""
    session, _ = ready(index)
    embedders: Embedders = session._embedder_factory
    run(session)
    assert embedders.made[0].queries == [QUESTION]
    assert COVERED  # the brick's own question stays untouched


def test_web_validate_is_read_only_and_names_the_stage(index):
    session, _ = ready(index)
    client = _client(session)
    body = client.get("/api/rag_lab").json()
    shipped = body["default_pipeline"]
    ok = client.post("/api/rag_lab/validate", json={"pipelines": [shipped]}, headers=HEADERS)
    assert ok.status_code == 200 and ok.json() == {"valid": True, "refusals": []}
    chain = {"label_text": "B", "stages": [dict(s) for s in shipped["stages"]]}
    chain["stages"][4] = {"id": "s9", "kind": "fusion", "option": "rrf", "params": {}}
    mark = get_journal().last_seq()
    answer = client.post(
        "/api/rag_lab/validate", json={"pipelines": [shipped, chain]}, headers=HEADERS
    ).json()
    assert not answer["valid"]
    assert answer["refusals"] == [
        {"lane": "b", "stage_id": "s9", "reason_text": answer["refusals"][0]["reason_text"]}
    ]
    assert "« Fusion »" in answer["refusals"][0]["reason_text"]
    assert get_journal().last_seq() == mark  # nothing emitted
    refused = client.post(
        "/api/intentions/rag_lab_run",
        json={"question": QUESTION, "pipelines": [shipped, chain]},
        headers=HEADERS,
    )
    assert refused.status_code == 409 and refused.json()["detail"].startswith("Chaîne B : ")
