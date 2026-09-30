"""Story 16: reranking, a sub-option of the RAG brick (CAP-19, AD-2, AD-8, AD-12, AD-21).

The index is built with the real code of `rag/` and `FakeEmbedder`; the reranker is
`FakeReranker`. Nothing touches the network, and no real model is needed (except the `model`
test).
"""

from __future__ import annotations

import threading
import time
from pathlib import Path

import httpx
import pytest
from fake_engine import FakeEngine
from fake_reranker import MODEL_ID, FakeReranker, relevance
from starlette.testclient import TestClient
from test_bricks import HEADERS
from test_rag import (
    CLOSED_FIRST,
    COVERED,
    REPLACED_WHILE_OPEN,
    Embedders,
    build,
    place_model,
    rag_config,
    segments,
)
from test_tools import QWEN

from wavestack import config
from wavestack.config import RerankerModel
from wavestack.models import discovery
from wavestack.models.load_registry import RERANKER, ModelChoice
from wavestack.models.reranker import LlamaCppReranker, pair_tokens, sigmoid
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
        "label_text": "Faux reranker",
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
    """The session's `reranker_factory`: records each load; `gate` holds it, `load_error`
    makes it raise."""

    def __init__(
        self,
        *,
        fail: bool = False,
        gate: threading.Event | None = None,
        load_error: Exception | None = None,
    ) -> None:
        self.made: list[FakeReranker] = []
        self.fail = fail
        self.gate = gate
        self.load_error = load_error

    def __call__(self, model) -> FakeReranker:  # noqa: ANN001
        if self.gate is not None:
            self.gate.wait(timeout=5)
        if self.load_error is not None:
            raise self.load_error
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
    engine: FakeEngine | None = None,
) -> tuple[AppSession, Rerankers]:
    rerankers = rerankers or Rerankers()
    engine = engine or FakeEngine(output="Quatorze caractères.")
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
    tokens, cut = pair_tokens([1, 2], [3, 4, 5, 6], bos=0, eos=9, sep=8, max_tokens=8)
    assert (tokens, cut) == ([0, 1, 2, 9, 8, 3, 4, 9], True)  # [BOS] q [EOS] [SEP] d… [EOS]
    fits = pair_tokens([1], [2], bos=None, eos=9, sep=None, max_tokens=10)
    assert fits == ([1, 9, 2, 9], False)


def test_the_query_keeps_at_least_half_and_takes_the_room_the_passage_leaves():
    # Both too long: the query keeps half of the room (16), the passage the other half.
    tokens, cut = pair_tokens(list(range(100, 200)), [7] * 50, bos=0, eos=9, sep=8, max_tokens=20)
    assert cut and len(tokens) == 20 and tokens[-1] == 9
    assert tokens[1:9] == list(range(100, 108)) and tokens.count(7) == 8
    # A short passage leaves its room to the query.
    tokens, cut = pair_tokens(list(range(100, 200)), [7, 7], bos=0, eos=9, sep=8, max_tokens=20)
    assert (
        cut and len(tokens) == 20 and tokens.count(7) == 2 and tokens[1:15] == list(range(100, 114))
    )
    # A short query leaves its room to the passage.
    tokens, cut = pair_tokens([1], [7] * 50, bos=0, eos=9, sep=8, max_tokens=20)
    assert cut and len(tokens) == 20 and tokens.count(7) == 15


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
    values["rag"]["top_k"] = 50  # never more than 20 either: the candidates stay bounded
    cfg = config.Config(values=values)
    assert (cfg.rag_top_k, cfg.rag_rerank_candidates) == (20, 20)


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
    assert option["label_text"] == "Reranking" and option["download"] is None
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
    assert "Aucun directement" in one(events, "rag_search_ended").payload["placement_text"]
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
    texts = {e["chunk_id"]: e["text"] for e in found}
    for e in reranked:
        assert "text" not in e  # the journal holds each text once: the search's
        assert e["retrieval_score"] == by_rank[e["before"]]["score"]
        assert e["chunk_id"] == by_rank[e["before"]]["chunk_id"]
        text = texts[e["chunk_id"]]
        assert e["score"] == round(relevance(HOTEL, f"{e['title_text']}\n{text}"), 3)
        assert e["truncated"] is False
    progress = [e for e in events if e.kind == "rag_rerank_progress"]
    assert [(e.payload["done"], e.payload["total"]) for e in progress] == [
        (n, 8) for n in range(1, 9)
    ]
    assert {e.step_id for e in progress} == {"t1.main.s2"}

    ctx = one(events, "context_rendered").payload
    rag = segments(ctx, "rag_excerpt")
    assert len(rag) == 4 and {s["brick"] for s in rag} == {"rag"}
    for i, e in enumerate(reranked[:3], start=1):
        head = f"Extrait {i} — {e['title_text']} :\n{texts[e['chunk_id']][:40]}"
        assert rag[i]["text"].startswith(head)
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
    assert "Dans le message" in one(events, "rag_search_ended").payload["placement_text"]
    session.close()


def test_a_missing_reranker_offers_its_download_and_the_rag_goes_on_without_it(index):
    place_model()
    session, rerankers = session_for(rerank_config(index))
    rag = rag_card(session)
    option = rag["rerank"]
    assert rag["available"] is True  # the brick itself stays available
    assert option["enabled"] is True and option["available"] is False
    assert "modèle absent" in option["reason_text"] and "sans reranking" in option["reason_text"]
    assert option["download"]["target"] == "rag_reranker"
    assert "Télécharger le modèle de reranking" in option["download"]["label_text"]
    assert rerankers.made == []

    events = turn(session)

    assert one(events, "rag_search_started").payload["top_k"] == 3
    assert not [e for e in events if e.kind.startswith("rag_rerank")]
    skipped = one(events, "rag_search_ended").payload["rerank_skipped_text"]
    assert "non appliqué" in skipped and "modèle absent" in skipped
    assert rag_card(session)["pending"] is False  # unavailable: nothing waits for next turn
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
    assert "Mémoire insuffisante pour charger le modèle de reranking" in option["reason_text"]
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
    assert "premiers extraits de l'embedding" in ended.payload["error_text"]
    error = one(events, "harness_error")
    assert (
        error.component == "rag.reranker"
        and "Le reranking a échoué" in error.payload["message_text"]
    )
    rag = segments(one(events, "context_rendered").payload, "rag_excerpt")
    assert len(rag) == 4
    for i, e in enumerate(found[:3], start=1):
        assert rag[i]["text"].startswith(f"Extrait {i} — {e['title_text']}")
    assert one(events, "turn_ended").payload["status"] == "completed"
    session.close()


def test_stop_between_two_excerpts_cancels_the_turn(index):
    place_model()
    place_reranker()
    session, rerankers = session_for(rerank_config(index))
    rerankers.made[0].before_each = lambda: session.stop()

    events = turn(session)

    ended = one(events, "rag_rerank_ended")
    assert (
        ended.payload["status"] == "cancelled"
        and ended.payload["error_text"] == "Reranking arrêté."
    )
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
    assert "Le téléchargement du modèle de reranking a échoué" in errors[0].payload["message_text"]
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
    assert node["label_text"] == "Reranking" and node["available"] is True
    assert node["detail_text"] == f"Modèle de reranking {MODEL_ID}, processus local"
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


# ---------- independent review (2026-09-26) ----------


def test_the_reason_is_said_and_the_option_waits_while_the_reranker_loads(index):
    place_model()
    place_reranker()
    gate = threading.Event()
    rerankers = Rerankers(gate=gate)
    session, _ = session_for(rerank_config(index), rerank=False, rerankers=rerankers)
    session.set_rag_rerank(True)  # the worker now waits in the factory
    time.sleep(0.05)
    state = session.build_turn_state()
    assert state.rag_rerank is False
    assert "Chargement du modèle de reranking" in (state.rag_rerank_skipped_text or "")
    gate.set()
    session.join()
    option = rag_card(session)["rerank"]
    assert option["available"] is True and len(rerankers.made) == 1
    session.close()


def test_the_reranker_waits_for_the_embedding_model(index):
    place_model()
    place_reranker()
    rerankers = Rerankers()

    def broken(model):  # noqa: ANN001
        raise RuntimeError("embedding en panne")

    session = AppSession(
        config.Config(values=rerank_config(index)),
        engine_factory=lambda path, n_ctx: FakeEngine(),
        embedder_factory=broken,
        reranker_factory=rerankers,
    )
    session.boot("fake.gguf").result()
    session.set_brick("rag", True)
    session.set_rag_rerank(True)
    session.join()
    session.join()
    option = rag_card(session)["rerank"]
    assert option["available"] is False
    assert "Indisponible tant que la brique RAG l'est" in option["reason_text"]
    assert session._reranker is None and session._load_registry.holder(RERANKER) is None
    assert rerankers.made == []
    session.close()


@pytest.mark.parametrize("close_first", [CLOSED_FIRST, REPLACED_WHILE_OPEN])
def test_an_index_replaced_with_the_reranker_loaded_closes_it(index, close_first):
    place_model()
    place_reranker()
    session, rerankers = session_for(rerank_config(index))
    time.sleep(0.01)
    if close_first:  # so the file can be replaced on every OS (lot G)
        session._rag_retriever.close()
    build(index, model_id="autre-modele")  # another build meanwhile, noticed by its stamp

    turn(session)

    assert rerankers.made[0].closed and session._load_registry.holder(RERANKER) is None
    session.close()


def test_a_reranker_refused_by_the_budget_loads_after_a_model_switch(index, tmp_path):
    place_model()
    place_reranker()
    rss = {"now": (4096 - 100) * 1024**2}
    values = rerank_config(index, measured_rss_mb=600)
    session, rerankers = session_for(values, rerank=False)
    session._load_registry._rss = lambda: rss["now"]
    session.set_rag_rerank(True)
    session.join()
    session.join()
    assert "Mémoire insuffisante" in rag_card(session)["rerank"]["reason_text"]
    assert rerankers.made == []

    rss["now"] = 100 * 1024**2  # the switch frees memory
    other = tmp_path / "other.gguf"
    other.write_bytes(b"\0" * 10)
    _, future = session.switch_model(ModelChoice("file", str(other)))
    future.result()
    session.join()
    session.join()

    assert rag_card(session)["rerank"]["available"] is True and len(rerankers.made) == 1
    assert session._load_registry.holder(RERANKER) == "Faux reranker"
    session.close()


def _nodes() -> dict:
    changed = [e for e in get_journal().events_since(0) if e.kind == "architecture_changed"]
    return {n["id"]: n for n in changed[-1].payload["nodes"]}


def test_the_schema_node_says_why_the_reranker_is_unavailable(index):
    place_model()
    session, _ = session_for(rerank_config(index))  # its file is missing
    node = _nodes()["rag.reranker"]
    assert node["available"] is False and "modèle absent" in node["reason_text"]
    session.close()


def test_a_factory_that_raises_says_why_on_the_card(index):
    place_model()
    place_reranker()
    rerankers = Rerankers(load_error=ValueError("pas un modèle de reranking"))
    mark = get_journal().last_seq()
    session, _ = session_for(rerank_config(index), rerankers=rerankers)
    option = rag_card(session)["rerank"]
    assert option["available"] is False
    assert "n'a pas pu être chargé" in option["reason_text"]
    assert "pas un modèle de reranking" in option["reason_text"]
    errors = [e for e in get_journal().events_since(mark) if e.kind == "harness_error"]
    assert [e.component for e in errors] == ["rag.reranker"]
    assert session._load_registry.holder(RERANKER) is None
    session.close()


def test_a_declared_sha256_that_differs_refuses_the_file(index):
    place_model()
    place_reranker()
    values = rerank_config(index)
    values["rag"]["reranker"]["files"][0]["sha256"] = "0" * 64
    session, rerankers = session_for(values)
    option = rag_card(session)["rerank"]
    assert option["available"] is False and "sha256" in option["reason_text"]
    assert rerankers.made == []
    session.close()


def test_scores_that_are_not_figures_keep_the_embedding_order(index):
    place_model()
    place_reranker()
    session, rerankers = session_for(rerank_config(index))
    rerankers.made[0].bad_score = "beaucoup"

    events = turn(session, HOTEL)

    found = one(events, "rag_search_ended").payload["excerpts"]
    ended = one(events, "rag_rerank_ended").payload
    assert ended["status"] == "error" and ended["excerpts"] == []
    rag = segments(one(events, "context_rendered").payload, "rag_excerpt")
    assert rag[1]["text"].startswith(f"Extrait 1 — {found[0]['title_text']}")
    assert one(events, "turn_ended").payload["status"] == "completed"
    session.close()


def test_truncated_excerpts_are_said(index):
    place_model()
    place_reranker()
    session, rerankers = session_for(rerank_config(index))
    rerankers.made[0].truncate_over = 400

    events = turn(session, HOTEL)

    reranked = one(events, "rag_rerank_ended").payload["excerpts"]
    found = {e["chunk_id"]: e for e in one(events, "rag_search_ended").payload["excerpts"]}
    for e in reranked:
        long = len(f"{e['title_text']}\n{found[e['chunk_id']]['text']}") > 400
        assert e["truncated"] is long
    assert any(e["truncated"] for e in reranked)
    session.close()


def test_the_rag_rerank_route_is_404_without_a_rag_brick():
    session = AppSession(
        config.Config(values={}),
        engine_factory=lambda path, n_ctx: FakeEngine(),
        bricks=[],
    )
    app = create_app(
        DiagnosticSession(config.load_config(), port=8421),
        port=8421,
        version="test",
        app_session=session,
    )
    client = TestClient(app, base_url="http://127.0.0.1:8421")
    answer = client.post("/api/intentions/rag_rerank", json={"enabled": True}, headers=HEADERS)
    assert answer.status_code == 404
    session.close()


def test_the_sub_agent_context_is_never_reranked(index):
    place_model()
    place_reranker()
    qwen = FakeEngine(
        outputs=["Résultat du sous-agent.", "Voilà."],
        template=QWEN.decode("utf-8"),
        architecture="qwen35",
    )
    session, rerankers = session_for(rerank_config(index), bricks=("rag", "subagent"), engine=qwen)
    session.arm("delegate", "delegate", {"task": "Résume le guide du harnais."})

    events = turn(session, HOTEL)

    starts = [e for e in events if e.kind in ("rag_search_started", "rag_rerank_started")]
    assert [e.context_id for e in starts] == ["main", "main"]
    assert any(e.context_id.startswith("sub") for e in events if e.context_id)
    assert len(rerankers.made[0].calls) == 1
    session.close()


def test_the_reranker_file_outside_its_folder_is_never_offered_as_a_chat_model(monkeypatch):
    model, _ = config.load_config().rag_reranker
    values = {
        "rag": {
            "reranker": model.model_dump()
            | {
                "load_path": "Autre/r.gguf",
                "files": [
                    {"url": "https://huggingface.co/d/r.gguf", "path": "Autre/r.gguf", "size": 4}
                ],
            }
        }
    }
    monkeypatch.setattr(config, "load_config", lambda: config.Config(values=values))
    for name in ("Autre/r.gguf", "RERANKER/x.gguf", "Embedding/y.gguf", "qwen.gguf"):
        path = config.models_dir() / name
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(b"GGUF")
    monkeypatch.setattr(discovery, "_ollama_candidates", lambda: [])
    monkeypatch.setattr(discovery, "_server_candidates", lambda cfg: [])
    paths = {c.path for c in discovery.discover() if c.source == "models_dir"}
    assert paths == {str(config.models_dir() / "qwen.gguf")}


FIXTURES = Path(__file__).parent / "fixtures"
TINY = RerankerModel(
    id="tiny",
    backend="llama_cpp",
    label_text="Petit reranker synthétique",
    license="MIT",
    max_tokens=64,
    load_path="reranker/tiny.gguf",
    files=[{"url": "https://huggingface.co/d/t.gguf", "path": "reranker/tiny.gguf", "size": 1}],
)


def test_the_adapter_scores_pairs_on_a_synthetic_reranker():
    reranker = LlamaCppReranker(TINY, FIXTURES / "tiny-bert-rank.gguf")
    try:
        seen = []
        scores = reranker.score(
            "mot de passe",
            ["le mot de passe fait 14 caractères", "a b " * 100],
            progress=lambda done, total: seen.append((done, total)),
        )
        assert (reranker._bos, reranker._eos, reranker._sep) == (2, 3, 3)
    finally:
        reranker.close()
    assert [s.truncated for s in scores] == [False, True]  # 200 words, 64 tokens
    assert all(0 <= s.score <= 1 for s in scores) and seen == [(1, 2), (2, 2)]


def test_the_adapter_refuses_an_embedding_gguf():
    with pytest.raises(ValueError, match="pas un modèle de reranking"):
        LlamaCppReranker(TINY, FIXTURES / "tiny-bert-cls.gguf")


@pytest.mark.model
def test_real_reranker_puts_the_password_document_first(real_models_dir):
    model, error = config.load_config().rag_reranker
    if model is None:
        pytest.skip(error or "[rag.reranker] non déclarée")
    path = real_models_dir / model.load_path
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
    assert all(0 <= s.score <= 1 for s in scores)  # `RerankScore(score, truncated)`
    assert max(range(3), key=lambda i: scores[i].score) == 1
