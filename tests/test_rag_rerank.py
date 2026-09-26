"""Story 16: reranking, a sub-option of the RAG brick (CAP-19, AD-2, AD-8, AD-12, AD-21).

The index is built with the real code of `rag/` and `FakeEmbedder`; the reranker is
`FakeReranker`. Nothing touches the network, and no real model is needed (except the `model`
test).
"""

from __future__ import annotations

import time

import httpx
import pytest
from fake_engine import FakeEngine
from fake_reranker import MODEL_ID, FakeReranker, relevance
from starlette.testclient import TestClient
from test_bricks import HEADERS
from test_rag import COVERED, Embedders, build, place_model, rag_config, segments

from wavestack import config
from wavestack.models import discovery
from wavestack.models.load_registry import RERANKER
from wavestack.models.reranker import LlamaCppReranker, model_path, pair_tokens, sigmoid
from wavestack.session.app_session import AppSession, SendRefused
from wavestack.session.diagnostic import DiagnosticSession
from wavestack.trace.journal import get_journal
from wavestack.web.app import create_app

RERANK_FILE = "reranker/fake.gguf"
RERANK_SIZE = 500
URL = "https://huggingface.co/demo/resolve/main/reranker.gguf"
# The fake embedding ranks « Déplacements » 6th for it; the fake reranker puts it first.
HOTEL = "Quel plafond de remboursement s'applique à une nuit d'hôtel à Paris chez Exemplia ?"


@pytest.fixture
def index(tmp_path):
    path = tmp_path / "rag_index.sqlite"
    build(path)
    return path


def rerank_config(index, *, budget_mb: int = 4096, **reranker) -> dict:
    values = rag_config(index, budget_mb=budget_mb)
    values["rag"]["rerank_candidates"] = 8
    values["rag"]["reranker"] = {
        "id": MODEL_ID,
        "backend": "llama_cpp",
        "label_fr": "Faux reranker",
        "license": "MIT",
        "max_tokens": 512,
        "load_path": RERANK_FILE,
        "files": [{"url": URL, "path": RERANK_FILE, "size": RERANK_SIZE}],
    } | reranker
    return values


def place_reranker() -> None:
    path = config.models_dir() / RERANK_FILE
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(b"\0" * RERANK_SIZE)


class Rerankers:
    """The session's `reranker_factory`: records each load."""

    def __init__(self, *, fail: bool = False) -> None:
        self.made: list[FakeReranker] = []
        self.fail = fail

    def __call__(self, model) -> FakeReranker:  # noqa: ANN001
        reranker = FakeReranker(model_id=model.id, fail=self.fail)
        self.made.append(reranker)
        return reranker


def session_for(
    values: dict,
    *,
    rerank: bool = True,
    rerankers: Rerankers | None = None,
    rss: int | None = None,
    transport=None,  # noqa: ANN001
    bricks: tuple[str, ...] = ("rag",),
) -> tuple[AppSession, Rerankers]:
    rerankers = rerankers or Rerankers()
    engine = FakeEngine(output="Quatorze caractères.")
    session = AppSession(
        config.Config(values=values),
        engine_factory=lambda path, n_ctx: engine,
        embedder_factory=Embedders(),
        reranker_factory=rerankers,
        rss_fn=(lambda: rss) if rss is not None else None,
        download_transport=transport,
    )
    session.boot("fake.gguf").result()
    for brick in bricks:
        session.set_brick(brick, True)
    if rerank:
        session.set_rag_rerank(True)
    session.join()
    session.join()
    return session, rerankers


def rag_card(session: AppSession) -> dict:
    session.join()
    changed = [e for e in get_journal().events_since(0) if e.kind == "bricks_changed"]
    return next(b for b in changed[-1].payload["bricks"] if b["id"] == "rag")


def turn(session: AppSession, message: str = COVERED):
    mark = get_journal().last_seq()
    session.send(message)
    session.join()
    return get_journal().events_since(mark)


def one(events, kind: str):
    found = [e for e in events if e.kind == kind]
    assert len(found) == 1, (kind, len(found))
    return found[0]


# ---------- adapter helpers and configuration ----------


def test_pair_layout_and_truncation():
    tokens = pair_tokens([1, 2], [3, 4, 5, 6], bos=0, eos=9, sep=8, max_tokens=8)
    assert tokens == [0, 1, 2, 9, 8, 3, 4, 9]  # [BOS] q [EOS] [SEP] d… [EOS]
    assert pair_tokens([1], [2], bos=None, eos=9, sep=None, max_tokens=10) == [1, 9, 2, 9]
    long = pair_tokens(list(range(100)), [7] * 50, bos=0, eos=9, sep=8, max_tokens=20)
    assert len(long) <= 20 and long[-1] == 9


def test_sigmoid_bounds_the_logit():
    assert sigmoid(0) == 0.5
    assert 0 <= sigmoid(-800) < 0.001 and 0.999 < sigmoid(800) <= 1
    assert sigmoid(float("nan")) == 0.0


def test_reranker_section_absent_invalid_and_candidates_bounds(index):
    values = rag_config(index)
    model, error = config.Config(values=values).rag_reranker
    assert model is None and "[rag.reranker]" in error and "absente" in error
    values = rerank_config(index, max_tokens=0)
    model, error = config.Config(values=values).rag_reranker
    assert model is None and "invalide (max_tokens)" in error
    values = rerank_config(index)
    values["rag"]["rerank_candidates"] = 1
    assert config.Config(values=values).rag_rerank_candidates == 3  # never below top_k
    values["rag"]["rerank_candidates"] = 50
    assert config.Config(values=values).rag_rerank_candidates == 20


def test_the_shipped_configuration_declares_the_verdict():
    model, error = config.load_config().rag_reranker
    assert error is None and model.id == "bge-reranker-v2-m3-q4_k_m"
    assert model.load_file.size == 438376864 and model.license == "Apache-2.0"
    assert config.load_config().rag_rerank_candidates == 8


def test_the_reranker_is_never_offered_as_a_chat_model(monkeypatch):
    for name in ("reranker/autre.gguf", "qwen.gguf"):
        path = config.models_dir() / name
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(b"GGUF")
    monkeypatch.setattr(discovery, "_ollama_candidates", lambda: [])
    monkeypatch.setattr(discovery, "_server_candidates", lambda cfg: [])
    paths = {c.path for c in discovery.discover() if c.source == "models_dir"}
    assert paths == {str(config.models_dir() / "qwen.gguf")}


# ---------- I/O matrix ----------


def test_the_sub_option_is_off_at_launch_and_available_with_its_files(index):
    place_model()
    place_reranker()
    session, rerankers = session_for(rerank_config(index), rerank=False)
    option = rag_card(session)["rerank"]
    assert option["enabled"] is False and option["available"] is True
    assert option["label_fr"] == "Reranking" and option["download"] is None
    assert rerankers.made == []  # loaded only once enabled
    session.close()


def test_reranking_turn_orders_the_candidates_and_keeps_the_first_three(index):
    place_model()
    place_reranker()
    session, rerankers = session_for(rerank_config(index), bricks=("hooks", "rag"))
    assert len(rerankers.made) == 1
    assert session._load_registry.holder(RERANKER) == "Faux reranker"

    events = turn(session, HOTEL)

    search = one(events, "rag_search_started")
    found = one(events, "rag_search_ended").payload["excerpts"]
    assert search.payload["top_k"] == 8 and len(found) == 8
    assert "Aucun directement" in one(events, "rag_search_ended").payload["placement_fr"]
    started = one(events, "rag_rerank_started")
    ended = one(events, "rag_rerank_ended")
    assert (started.step_id, started.brick, started.component) == (
        "t1.main.s2",
        "rag",
        "rag.reranker",
    )
    assert (started.actor, started.trigger) == ("harness", "harness")
    assert started.payload["candidates"] == 8 and started.payload["keep"] == 3
    reranked = ended.payload["excerpts"]
    assert ended.payload["status"] == "ok" and ended.payload["keep"] == 3
    assert [e["position"] for e in reranked] == list(range(1, 9))
    assert sorted(e["before"] for e in reranked) == list(range(1, 9))
    assert [e["score"] for e in reranked] == sorted((e["score"] for e in reranked), reverse=True)
    assert (reranked[0]["doc_id"], reranked[0]["before"]) == ("deplacements", 6)  # moved up
    by_rank = {e["position"]: e for e in found}
    for e in reranked:
        assert e["retrieval_score"] == by_rank[e["before"]]["score"]
        assert e["score"] == round(relevance(HOTEL, f"{e['title_fr']}\n{e['text']}"), 3)

    ctx = one(events, "context_rendered").payload
    rag = segments(ctx, "rag_excerpt")
    assert len(rag) == 4 and {s["brick"] for s in rag} == {"rag"}
    for i, e in enumerate(reranked[:3], start=1):
        assert rag[i]["text"].startswith(f"Extrait {i} — {e['title_fr']} :\n{e['text'][:40]}")
    kinds = [s["kind"] for s in ctx["segments"]]
    assert kinds.index("hook_injection") < kinds.index("rag_excerpt") < kinds.index("user_message")
    assert one(events, "model_call_started").step_id == "t1.main.s3"
    session.close()


def test_switching_the_sub_option_off_closes_the_reranker_and_searches_as_before(index):
    place_model()
    place_reranker()
    session, rerankers = session_for(rerank_config(index))
    session.set_rag_rerank(False)
    session.join()
    assert rerankers.made[0].closed and session._load_registry.holder(RERANKER) is None
    assert rag_card(session)["rerank"]["enabled"] is False

    events = turn(session)

    assert one(events, "rag_search_started").payload["top_k"] == 3
    assert not [e for e in events if e.kind.startswith("rag_rerank")]
    assert "Dans le message" in one(events, "rag_search_ended").payload["placement_fr"]
    session.close()


def test_a_missing_reranker_offers_its_download_and_the_rag_goes_on_without_it(index):
    place_model()
    session, rerankers = session_for(rerank_config(index))
    rag = rag_card(session)
    option = rag["rerank"]
    assert rag["available"] is True  # the brick itself stays available
    assert option["enabled"] is True and option["available"] is False
    assert "modèle absent" in option["reason_fr"] and "sans reranking" in option["reason_fr"]
    assert option["download"]["target"] == "rag_reranker"
    assert "Télécharger le modèle de reranking" in option["download"]["label_fr"]
    assert rerankers.made == []

    events = turn(session)

    assert one(events, "rag_search_started").payload["top_k"] == 3
    assert not [e for e in events if e.kind.startswith("rag_rerank")]
    session.close()


def test_a_budget_refusal_makes_only_the_sub_option_unavailable(index):
    place_model()
    place_reranker()
    values = rerank_config(index, measured_rss_mb=600)
    rss = (4096 - 100) * 1024 * 1024  # the embedding fits, the reranker does not
    mark = get_journal().last_seq()
    session, rerankers = session_for(values, rss=rss)
    rag = rag_card(session)
    assert rag["available"] is True
    option = rag["rerank"]
    assert option["available"] is False
    assert "Mémoire insuffisante pour charger le modèle de reranking" in option["reason_fr"]
    assert rerankers.made == [] and session._load_registry.holder(RERANKER) is None
    errors = [e for e in get_journal().events_since(mark) if e.kind == "harness_error"]
    assert [e.component for e in errors] == ["rag.reranker"]

    events = turn(session)
    assert not [e for e in events if e.kind.startswith("rag_rerank")]
    session.close()


def test_a_failing_reranker_keeps_the_embedding_order(index):
    place_model()
    place_reranker()
    session, _ = session_for(rerank_config(index), rerankers=Rerankers(fail=True))

    events = turn(session)

    found = one(events, "rag_search_ended").payload["excerpts"]
    ended = one(events, "rag_rerank_ended")
    assert ended.payload["status"] == "error" and ended.payload["excerpts"] == []
    assert "premiers extraits de l'embedding" in ended.payload["error_fr"]
    error = one(events, "harness_error")
    assert (
        error.component == "rag.reranker" and "Le reranking a échoué" in error.payload["message_fr"]
    )
    rag = segments(one(events, "context_rendered").payload, "rag_excerpt")
    assert len(rag) == 4
    for i, e in enumerate(found[:3], start=1):
        assert rag[i]["text"].startswith(f"Extrait {i} — {e['title_fr']}")
    assert one(events, "turn_ended").payload["status"] == "completed"
    session.close()


def test_stop_between_two_excerpts_cancels_the_turn(index):
    place_model()
    place_reranker()
    session, rerankers = session_for(rerank_config(index))
    rerankers.made[0].before_each = lambda: session.stop()

    events = turn(session)

    ended = one(events, "rag_rerank_ended")
    assert ended.payload["status"] == "error" and ended.payload["error_fr"] == "Reranking arrêté."
    assert not [e for e in events if e.kind == "harness_error"]
    assert not [e for e in events if e.kind == "model_call_started"]
    assert one(events, "turn_ended").payload["status"] == "cancelled"
    session.close()


class Hub:
    """`huggingface.co` answers with the file's bytes (`status` other than 200: a failure)."""

    def __init__(self, status: int = 200) -> None:
        self.status = status

    def __call__(self, request: httpx.Request) -> httpx.Response:
        if self.status != 200:
            return httpx.Response(self.status)
        return httpx.Response(200, content=b"\1" * RERANK_SIZE)


def wait_idle(session: AppSession) -> None:
    deadline = time.monotonic() + 10
    while time.monotonic() < deadline:
        if session.state == "idle" and session._download_cancel is None:
            break
        time.sleep(0.01)
    time.sleep(0.05)
    session.join()
    session.join()


def test_download_of_the_reranker_then_it_loads(index):
    place_model()
    transport = httpx.MockTransport(Hub())
    session, rerankers = session_for(rerank_config(index), transport=transport)
    mark = get_journal().last_seq()

    reason = session.download_model("rag_reranker")
    wait_idle(session)

    assert reason.startswith("Téléchargement du modèle de reranking : 0 %")
    events = get_journal().events_since(mark)
    outbound = [e for e in events if e.kind == "outbound_request"]
    assert [e.payload["url"] for e in outbound] == [URL]
    assert {(e.payload["origin"], e.component) for e in outbound} == {("download", "rag.reranker")}
    assert (config.models_dir() / RERANK_FILE).read_bytes() == b"\1" * RERANK_SIZE
    assert len(rerankers.made) == 1  # enabled and the brick wanted: loaded
    option = rag_card(session)["rerank"]
    assert option["available"] is True and option["download"] is None
    with pytest.raises(SendRefused, match="Rien à télécharger : les fichiers du modèle de rerank"):
        session.download_model("rag_reranker")
    session.close()


def test_a_failed_reranker_download_removes_the_part(index):
    place_model()
    session, rerankers = session_for(rerank_config(index), transport=httpx.MockTransport(Hub(503)))
    mark = get_journal().last_seq()

    session.download_model("rag_reranker")
    wait_idle(session)

    errors = [e for e in get_journal().events_since(mark) if e.kind == "harness_error"]
    assert len(errors) == 1 and errors[0].component == "rag.reranker"
    assert "Le téléchargement du modèle de reranking a échoué" in errors[0].payload["message_fr"]
    assert not list((config.models_dir() / "reranker").glob("*.part"))
    assert rerankers.made == [] and rag_card(session)["rerank"]["download"] is not None
    session.close()


def test_scenario_rag_rerank_then_reset(index):
    place_model()
    place_reranker()
    session, rerankers = session_for(rerank_config(index), rerank=False, bricks=())

    session.launch_scenario("rag_rerank")
    session.join()
    session.join()
    rag = rag_card(session)
    assert rag["wanted"] and rag["rerank"]["enabled"] is True
    assert len(rerankers.made) == 1 and not rerankers.made[0].closed

    session.reset()
    session.join()
    session.join()
    assert rag_card(session)["rerank"]["enabled"] is False
    assert rerankers.made[0].closed and session._load_registry.holder(RERANKER) is None
    session.close()


# ---------- card, schema, route ----------


def test_the_sub_option_changed_since_the_last_turn_is_pending(index):
    place_model()
    place_reranker()
    session, _ = session_for(rerank_config(index), rerank=False)
    turn(session)
    assert rag_card(session)["pending"] is False
    session.set_rag_rerank(True)
    assert rag_card(session)["pending"] is True
    turn(session)
    assert rag_card(session)["pending"] is False
    session.close()


def test_the_schema_draws_the_reranker_while_the_sub_option_is_enabled(index):
    place_model()
    place_reranker()
    session, _ = session_for(rerank_config(index))

    def nodes() -> dict:
        changed = [e for e in get_journal().events_since(0) if e.kind == "architecture_changed"]
        return {n["id"]: n for n in changed[-1].payload["nodes"]}

    node = nodes()["rag.reranker"]
    assert node["label_fr"] == "Reranking" and node["available"] is True
    assert node["detail_fr"] == f"Modèle de reranking {MODEL_ID}, processus local"
    session.set_rag_rerank(False)
    session.join()
    assert "rag.reranker" not in nodes() and "rag.retriever" in nodes()
    session.close()


def test_routes_rag_rerank_and_download_target(index):
    place_model()
    place_reranker()
    session, rerankers = session_for(rerank_config(index), rerank=False)
    app = create_app(
        DiagnosticSession(config.load_config(), port=8421),
        port=8421,
        version="test",
        app_session=session,
    )
    client = TestClient(app, base_url="http://127.0.0.1:8421")

    answer = client.post("/api/intentions/rag_rerank", json={"enabled": True}, headers=HEADERS)
    assert answer.status_code == 200 and answer.json() == {"accepted": True}
    session.join()
    session.join()
    state = client.get("/api/state").json()
    rag = next(b for b in state["bricks_changed"]["bricks"] if b["id"] == "rag")
    assert rag["rerank"]["enabled"] is True and len(rerankers.made) == 1

    nothing = client.post(
        "/api/intentions/download_model", json={"target": "rag_reranker"}, headers=HEADERS
    )
    assert nothing.status_code == 409 and "Rien à télécharger" in nothing.json()["detail"]
    session.close()


@pytest.mark.model
def test_real_reranker_puts_the_password_document_first():
    model, _ = config.load_config().rag_reranker
    path = model_path(model)
    if not path.is_file():
        pytest.skip(f"modèle de reranking absent : {path}")
    reranker = LlamaCppReranker(model, path)
    try:
        passages = [
            "Accord de télétravail\nLe télétravail est possible deux jours par semaine.",
            "Politique des mots de passe\nUn mot de passe compte au moins 14 caractères.",
            "Sauvegardes\nLes sauvegardes sont quotidiennes et gardées 30 jours.",
        ]
        scores = reranker.score(COVERED, passages)
    finally:
        reranker.close()
    assert all(0 <= s <= 1 for s in scores)
    assert max(range(3), key=scores.__getitem__) == 1
