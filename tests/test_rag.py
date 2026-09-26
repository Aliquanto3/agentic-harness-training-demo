"""Story 15: demonstration corpus and simple RAG (AD-4, AD-8, AD-9, AD-12, AD-22).

The index is built on a temporary file with the real code of `rag/` and `FakeEmbedder`;
nothing touches the network, and no real model is needed (except the `model` test).
"""

from __future__ import annotations

import threading
from pathlib import Path

import pytest
from fake_embedder import DIMS, MODEL_ID, FakeEmbedder
from fake_engine import FakeEngine
from pydantic import SecretStr
from starlette.testclient import TestClient
from test_bricks import HEADERS
from test_cloud import GROQ_TEXT, SENTINEL, Provider
from test_turn import _run

from wavestack import config
from wavestack.models.embedding import LlamaCppEmbedder, model_path
from wavestack.models.load_registry import EMBEDDING, LoadRegistry
from wavestack.rag import index as rag_index
from wavestack.rag.corpus import chunk_corpus, load_rag_content, split_text
from wavestack.rag.retriever import SqliteVecRetriever
from wavestack.session.app_session import AppSession
from wavestack.session.diagnostic import DiagnosticSession
from wavestack.trace.journal import get_journal
from wavestack.web.app import create_app

COVERED = "Combien de caractères doit compter au minimum un mot de passe chez Exemplia ?"
OFF_CORPUS = "Quelle est la capitale du Pérou ?"
MODEL_FILE = "embedding/fake.gguf"
MODEL_SIZE = 1000


def rag_values(index: Path, **embedding: object) -> dict:
    """`[rag]` for the tests: the temporary index, the fake model (64 dimensions)."""
    return {
        "index_path": str(index),
        "top_k": 3,
        "chunk_max_chars": 700,
        "embedding": {
            "id": MODEL_ID,
            "backend": "llama_cpp",
            "label_fr": "Faux embedding",
            "license": "MIT",
            "dims": DIMS,
            "max_tokens": 512,
            "load_path": MODEL_FILE,
            "files": [
                {
                    "url": "https://huggingface.co/demo/resolve/main/fake.gguf",
                    "path": MODEL_FILE,
                    "size": MODEL_SIZE,
                }
            ],
        }
        | embedding,
    }


def rag_config(index: Path, *, window: int = 4096, budget_mb: int = 4096, **embedding) -> dict:
    return {
        "context": {"window": window, "near_limit_ratio": 0.8},
        "memory": {"budget_mb": budget_mb, "load_margin_mb": 1},
        "rag": rag_values(index, **embedding),
    }


def build(path: Path, model_id: str = MODEL_ID) -> rag_index.IndexMeta:
    return rag_index.build_index(
        load_rag_content(), FakeEmbedder(model_id=model_id), path, chunk_max_chars=700
    )


def place_model() -> Path:
    path = config.models_dir() / MODEL_FILE
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(b"\0" * MODEL_SIZE)
    return path


@pytest.fixture
def index(tmp_path) -> Path:
    path = tmp_path / "rag_index.sqlite"
    build(path)
    return path


class Embedders:
    """The session's `embedder_factory`: records each load; `gate` holds it."""

    def __init__(self, *, fail_search: bool = False, gate: threading.Event | None = None):
        self.made: list[FakeEmbedder] = []
        self.fail_search = fail_search
        self.gate = gate

    def __call__(self, model) -> FakeEmbedder:  # noqa: ANN001
        if self.gate is not None:
            self.gate.wait(timeout=5)
        embedder = FakeEmbedder(model_id=model.id, fail=self.fail_search)
        self.made.append(embedder)
        return embedder


def rag_session(
    values: dict,
    engine: FakeEngine | None = None,
    embedders: Embedders | None = None,
    *,
    rss: int | None = None,
    bricks: tuple[str, ...] = ("rag",),
) -> tuple[AppSession, Embedders]:
    embedders = embedders or Embedders()
    engine = engine or FakeEngine(output="Quatorze caractères.")
    session = AppSession(
        config.Config(values=values),
        engine_factory=lambda path, n_ctx: engine,
        embedder_factory=embedders,
        rss_fn=(lambda: rss) if rss is not None else None,
    )
    session.boot("fake.gguf").result()
    for brick in bricks:
        session.set_brick(brick, True)
    session.join()
    return session, embedders


def card(session: AppSession, mark: int = 0) -> dict:
    session.join()
    changed = [e for e in get_journal().events_since(mark) if e.kind == "bricks_changed"]
    return next(b for b in changed[-1].payload["bricks"] if b["id"] == "rag")


def segments(ctx: dict, kind: str | None = None) -> list[dict]:
    return [s for s in ctx["segments"] if kind is None or s["kind"] == kind]


def turn_events(message: str, session: AppSession):
    mark = get_journal().last_seq()
    session.send(message)
    session.join()
    return get_journal().events_since(mark)


# ---------- chunking and corpus ----------


def test_chunking_merges_paragraphs_and_cuts_a_long_one_at_a_sentence_end():
    text = "Un.\n\nDeux.\n\n" + "Phrase longue numéro un. " * 3 + "\n\n" + "x" * 50
    chunks = split_text(text, 40)
    assert chunks[0] == "Un.\n\nDeux."
    assert chunks[1] == "Phrase longue numéro un."  # cut at the sentence's end
    assert all(len(c) <= 40 for c in chunks)
    assert chunks[-2:] == ["x" * 40, "x" * 10]  # no sentence end: cut at the limit


def test_corpus_is_eight_french_documents_of_250_to_450_words():
    content = load_rag_content()
    assert len(content.documents) == 8
    assert "fictifs" in content.notice_fr
    for doc in content.documents:
        words = len((config.content_dir() / doc.file).read_text(encoding="utf-8").split())
        assert 250 <= words <= 450, doc.id
    chunks = chunk_corpus(content, 700)
    assert all(len(c.text) <= 700 for c in chunks)
    assert {c.doc_id for c in chunks} == {d.id for d in content.documents}
    first = [c for c in chunks if c.doc_id == "teletravail"]
    assert [c.position for c in first] == list(range(1, len(first) + 1))


def test_retriever_ranks_by_score_from_one_without_threshold(index):
    excerpts = SqliteVecRetriever(index, FakeEmbedder(), 3).search(COVERED)
    assert [e.position for e in excerpts] == [1, 2, 3]
    assert [e.score for e in excerpts] == sorted((e.score for e in excerpts), reverse=True)
    assert excerpts[0].doc_id == "mots_de_passe"
    assert all(e.score == round(e.score, 3) for e in excerpts)


# ---------- I/O matrix ----------


def test_covered_question_places_three_excerpts_between_the_hook_and_the_message(index):
    place_model()
    session, _ = rag_session(rag_config(index), bricks=("hooks", "rag"))  # H3 injects

    events = turn_events(COVERED, session)

    started = next(e for e in events if e.kind == "rag_search_started")
    ended = next(e for e in events if e.kind == "rag_search_ended")
    assert (started.step_id, started.brick, started.component) == (
        "t1.main.s1",
        "rag",
        "rag.retriever",
    )
    assert (started.actor, started.trigger) == ("harness", "harness")
    assert started.payload == {
        "query": COVERED,
        "top_k": 3,
        "phase_label": "Recherche dans le corpus…",
    }
    assert ended.payload["status"] == "ok"
    excerpts = ended.payload["excerpts"]
    assert len(excerpts) == 3 and excerpts[0]["doc_id"] == "mots_de_passe"
    assert [e["score"] for e in excerpts] == sorted((e["score"] for e in excerpts), reverse=True)
    assert ended.payload["placement_fr"].startswith("Dans le message de l'utilisateur")
    ctx = next(e.payload for e in events if e.kind == "context_rendered")
    kinds = [s["kind"] for s in segments(ctx) if s["kind"] != "template"]
    assert kinds == ["hook_injection", *["rag_excerpt"] * 4, "user_message"]
    rag = segments(ctx, "rag_excerpt")
    assert {(s["brick"], s["component"]) for s in rag} == {("rag", "rag.retriever")}
    assert rag[0]["text"].startswith("Extraits de la documentation interne d'Exemplia")
    assert rag[1]["text"].startswith("Extrait 1 — Politique des mots de passe :\n")
    assert [s["label_fr"] for s in rag] == ["Extraits RAG"] * 4
    session.close()


def test_off_corpus_question_still_sends_three_low_scored_excerpts(index):
    place_model()
    session, _ = rag_session(rag_config(index))
    covered = next(e for e in turn_events(COVERED, session) if e.kind == "rag_search_ended")

    events = turn_events(OFF_CORPUS, session)

    ended = next(e for e in events if e.kind == "rag_search_ended").payload
    assert len(ended["excerpts"]) == 3  # no threshold
    assert max(e["score"] for e in ended["excerpts"]) < covered.payload["excerpts"][0]["score"]
    ctx = next(e.payload for e in events if e.kind == "context_rendered")
    assert len(segments(ctx, "rag_excerpt")) == 4
    session.close()


def test_index_absent_makes_the_brick_unavailable_without_step_nor_segment(tmp_path):
    place_model()
    session, embedders = rag_session(rag_config(tmp_path / "absent.sqlite"))

    rag = card(session)
    assert rag["available"] is False and "index absent" in rag["reason_fr"]
    assert "scripts/build_rag_index.py" in rag["reason_fr"]
    assert rag["download"] is None and embedders.made == []
    events = turn_events(COVERED, session)
    assert not [e for e in events if e.kind.startswith("rag_search")]
    ctx = next(e.payload for e in events if e.kind == "context_rendered")
    assert segments(ctx, "rag_excerpt") == []
    session.close()


def test_index_of_another_model_names_both_models(tmp_path):
    place_model()
    path = tmp_path / "other.sqlite"
    build(path, model_id="autre-modele")
    session, embedders = rag_session(rag_config(path))

    rag = card(session)
    assert rag["available"] is False
    assert "autre-modele" in rag["reason_fr"] and MODEL_ID in rag["reason_fr"]
    assert "Reconstruisez l'index" in rag["reason_fr"] and rag["download"] is None
    assert embedders.made == []
    session.close()


def test_model_absent_offers_the_download(index):
    session, embedders = rag_session(rag_config(index))  # no model file

    rag = card(session)
    assert rag["available"] is False and "modèle absent" in rag["reason_fr"]
    assert str(config.models_dir() / "embedding") in rag["reason_fr"]
    assert rag["download"] == {
        "target": "rag_embedding",
        "label_fr": "Télécharger le modèle d'embedding (≈ 1 Mo)",
    }
    assert embedders.made == []
    session.close()


def test_budget_exceeded_refuses_in_figures_and_loads_nothing(index):
    place_model()
    session, embedders = rag_session(rag_config(index, budget_mb=100), rss=200 * 1024**2)

    rag = card(session)
    assert rag["available"] is False
    assert rag["reason_fr"] == (
        "Indisponible : Mémoire insuffisante pour charger le modèle d'embedding Faux "
        "embedding : WaveStack occupe 200 Mo, il en faut environ 1 de plus, au-delà du budget "
        "de 100 Mo. Désactivez une brique ou relevez `memory.budget_mb` dans settings.json."
    )
    assert embedders.made == [] and session._load_registry.holder(EMBEDDING) is None
    events = turn_events(COVERED, session)
    assert not [e for e in events if e.kind.startswith("rag_search")]
    session.close()


def test_registry_refusal_uses_the_injected_measure():
    registry = LoadRegistry(4096 * 1024**2, 128 * 1024**2, rss_fn=lambda: 4000 * 1024**2)
    cost = registry.embedding_cost(None, [121_020_096])
    assert cost == 121_020_096 + 128 * 1024**2
    refusal = registry.check_component("le modèle d'embedding X", cost, EMBEDDING)
    assert refusal is not None and "WaveStack occupe 4 000 Mo" in refusal
    assert "environ 243 de plus" in refusal and "budget de 4 096 Mo" in refusal
    assert registry.embedding_cost(300, [1]) == 300 * 1024**2  # the measure, when declared


def test_search_failure_is_traced_and_the_turn_goes_on_without_excerpts(index):
    place_model()
    session, _ = rag_session(rag_config(index), embedders=Embedders(fail_search=True))

    events = turn_events(COVERED, session)

    kinds = [e.kind for e in events]
    error = kinds.index("harness_error")
    assert kinds.index("rag_search_started") < error < kinds.index("rag_search_ended")
    assert events[error].payload["effect_fr"] == "Le tour continue sans extraits RAG."
    ended = next(e for e in events if e.kind == "rag_search_ended").payload
    assert ended["status"] == "error" and ended["excerpts"] == []
    assert "Le tour continue sans extraits RAG" in ended["error_fr"]
    assert next(e for e in events if e.kind == "turn_ended").payload["status"] == "completed"
    ctx = next(e.payload for e in events if e.kind == "context_rendered")
    assert segments(ctx, "rag_excerpt") == []
    session.close()


def test_activation_loads_once_and_deactivation_closes_and_releases(index):
    place_model()
    session, embedders = rag_session(rag_config(index))
    assert len(embedders.made) == 1 and session._load_registry.holder(EMBEDDING)
    session.set_brick("rag", True)  # already wanted: nothing loads again
    session.join()
    assert len(embedders.made) == 1

    session.set_brick("rag", False)
    session.join()

    assert embedders.made[0].closed and session._load_registry.holder(EMBEDDING) is None
    events = turn_events(COVERED, session)
    assert not [e for e in events if e.kind.startswith("rag_search")]
    session.close()


def test_close_releases_the_embedding_model(index):
    place_model()
    session, embedders = rag_session(rag_config(index))
    session.close()
    assert embedders.made[0].closed and session._load_registry.holder(EMBEDDING) is None


def test_a_turn_sent_while_the_model_loads_runs_without_rag(index):
    place_model()
    gate = threading.Event()
    session, embedders = rag_session(rag_config(index), embedders=Embedders(gate=gate), bricks=())
    mark = get_journal().last_seq()
    session.set_brick("rag", True)
    changed = [e for e in get_journal().events_since(mark) if e.kind == "bricks_changed"]
    rag = next(b for b in changed[-1].payload["bricks"] if b["id"] == "rag")
    assert rag["available"] is False and rag["reason_fr"].startswith("Chargement du modèle")

    session.send(COVERED)
    gate.set()
    session.join()

    events = get_journal().events_since(mark)
    assert not [e for e in events if e.kind.startswith("rag_search")]
    assert len(embedders.made) == 1 and card(session)["available"] is True
    session.close()


def test_replay_searches_again_and_the_history_keeps_no_excerpt(index):
    place_model()
    session, _ = rag_session(rag_config(index), bricks=("short_memory", "rag"))
    _run(session, COVERED)

    second = turn_events(OFF_CORPUS, session)
    ctx = next(e.payload for e in second if e.kind == "context_rendered")
    history = " ".join(s["text"] for s in segments(ctx, "history"))
    assert COVERED in history and "Extrait 1 —" not in history
    assert len(segments(ctx, "rag_excerpt")) == 4  # the second turn searched again

    mark = get_journal().last_seq()
    session.replay()
    session.join()
    replayed = get_journal().events_since(mark)
    started = [e.payload for e in replayed if e.kind == "rag_search_started"]
    assert [p["query"] for p in started] == [OFF_CORPUS]  # the replayed turn's own message
    session.close()


def test_cloud_model_gets_the_excerpts_in_the_json_body_and_embeds_locally(index):
    place_model()
    values = config._deep_merge(
        config.load_config().values, {"rag": rag_values(index), "memory": {"load_margin_mb": 1}}
    )
    cfg = config.Config(values=values)
    entry = cfg.cloud_model("groq")
    config.write_api_key(entry.id, entry.host, SecretStr(SENTINEL))
    provider = Provider(GROQ_TEXT)
    embedders = Embedders()
    session = AppSession(cfg, cloud_factory=provider.factory, embedder_factory=embedders)
    session.boot_cloud(entry).result()
    session.set_brick("rag", True)
    session.join()

    events = turn_events(COVERED, session)

    body = provider.requests[-1].content.decode()
    assert "Extrait 1 — Politique des mots de passe" in body and "14 caractères" in body
    ctx = next(e.payload for e in events if e.kind == "context_rendered")
    assert len(segments(ctx, "rag_excerpt")) == 4
    assert session._load_registry.holder(EMBEDDING) == "Faux embedding"
    nodes = {n["id"]: n for n in session_nodes()}
    assert nodes["rag.retriever"]["hosting"] == "local"
    assert nodes["core.model"]["hosting"] == "network"
    session.close()


def session_nodes() -> list[dict]:
    last = [e for e in get_journal().all_events() if e.kind == "architecture_changed"][-1]
    return last.payload["nodes"]


def test_preview_places_the_longest_excerpts_of_the_index(index):
    place_model()
    session, _ = rag_session(rag_config(index))
    preview = [e for e in get_journal().all_events() if e.kind == "context_preview"][-1].payload

    rag = segments(preview, "rag_excerpt")
    longest = rag_index.longest_chunks(index, 3)
    assert len(rag) == 4 and rag[0]["text"].startswith("Extraits de la documentation")
    for i, (segment, chunk) in enumerate(zip(rag[1:], longest, strict=True), start=1):
        assert segment["text"] == f"Extrait {i} — {chunk.title_fr} :\n{chunk.text}"
    every = sorted((len(c.text) for c in rag_index.read_chunks(index)), reverse=True)
    assert [len(c.text) for c in longest] == every[:3]
    session.close()


def test_schema_draws_the_index_file_and_the_retriever(index):
    place_model()
    session, _ = rag_session(rag_config(index))

    nodes = {n["id"]: n for n in session_nodes()}
    edges = {(e["from"], e["to"]) for e in last_edges()}
    meta = rag_index.read_meta(index)
    assert nodes["file.rag_index"]["kind"] == "file"
    assert nodes["file.rag_index"]["label_fr"] == "Index RAG (rag_index.sqlite)"
    detail = nodes["file.rag_index"]["detail_fr"]
    assert str(index) in detail and f"{meta.chunks} extraits" in detail and MODEL_ID in detail
    assert nodes["rag.retriever"]["kind"] == "brick"
    assert nodes["rag.retriever"]["detail_fr"] == (
        f"Modèle d'embedding {MODEL_ID}, processus local"
    )
    assert ("rag.retriever", "file.rag_index") in edges
    assert ("rag.retriever", "core.harness") in edges
    session.close()


def last_edges() -> list[dict]:
    last = [e for e in get_journal().all_events() if e.kind == "architecture_changed"][-1]
    return last.payload["edges"]


def test_overflow_mostly_from_excerpts_names_the_rag_cause(index):
    place_model()
    session, _ = rag_session(rag_config(index, window=1400))

    events = turn_events("Mot de passe ?", session)

    overflow = next(e.payload for e in events if e.kind == "context_overflow")
    assert "Cause : les extraits RAG" in overflow["message_fr"]
    assert "baissez `rag.top_k`" in overflow["message_fr"]
    session.close()


def test_invalid_embedding_section_makes_the_brick_unavailable_without_crash(index):
    session, embedders = rag_session(rag_config(index, dims=0))

    rag = card(session)
    assert rag["available"] is False and "[rag.embedding] est invalide" in rag["reason_fr"]
    assert "dims" in rag["reason_fr"] and embedders.made == []
    session.close()


def test_state_and_scenario_rag(index):
    session, _ = rag_session(rag_config(index), bricks=())
    app = create_app(
        DiagnosticSession(config.load_config(), port=8421),
        port=8421,
        version="test",
        app_session=session,
    )
    client = TestClient(app, base_url="http://127.0.0.1:8421")
    session.set_brick("rag", True)  # wanted but unavailable: model absent
    session.join()
    state = client.get("/api/state").json()
    rag = next(b for b in state["bricks_changed"]["bricks"] if b["id"] == "rag")
    assert rag["wanted"] and rag["available"] is False and "modèle absent" in rag["reason_fr"]
    assert rag["download"]["target"] == "rag_embedding"

    launched = client.post("/api/intentions/scenario", json={"scenario_id": "rag"}, headers=HEADERS)
    assert launched.status_code == 200
    session.join()
    state = client.get("/api/state").json()
    wanted = {b["id"] for b in state["bricks_changed"]["bricks"] if b["wanted"]}
    assert wanted == {"short_memory", "system_prompt", "tools", "mcp", "skills", "hooks", "rag"}
    mcp = next(b for b in state["bricks_changed"]["bricks"] if b["id"] == "mcp")
    hooks = next(b for b in state["bricks_changed"]["bricks"] if b["id"] == "hooks")
    assert mcp["mode"] == "lazy"
    assert {o["id"] for o in hooks["options"] if o["enabled"]} == {"h1", "h2"}
    assert state["scenario_changed"]["active"] == "rag"
    session.close()


# ---------- the index shipped and the real model ----------


def test_shipped_index_matches_the_corpus():
    cfg = config.load_config()
    path = cfg.rag_index_path()
    if not path.is_file():
        pytest.skip("index non livré : il se construit sur le poste de référence")
    meta = rag_index.read_meta(path)
    model, _ = cfg.rag_embedding
    assert model is not None and meta.embedding_model_id == model.id and meta.dims == model.dims
    shipped = [c.text for c in rag_index.read_chunks(path)]
    assert shipped == [c.text for c in chunk_corpus(load_rag_content(), meta.chunk_max_chars)]


@pytest.mark.model
def test_real_embedding_model_finds_the_password_document(tmp_path):
    model, _ = config.load_config().rag_embedding
    path = model_path(model)
    if not path.is_file():
        pytest.skip(f"modèle d'embedding absent : {path}")
    embedder = LlamaCppEmbedder(model, path)
    try:
        index = tmp_path / "real.sqlite"
        rag_index.build_index(load_rag_content(), embedder, index, 700)
        excerpts = SqliteVecRetriever(index, embedder, 3).search(COVERED)
    finally:
        embedder.close()
    assert excerpts[0].doc_id == "mots_de_passe"


def test_the_embedding_model_is_never_offered_as_a_chat_model(monkeypatch):
    from wavestack.models import discovery

    model, _ = config.load_config().rag_embedding
    embedding = config.models_dir() / model.load_path
    chat = config.models_dir() / "qwen.gguf"
    for path in (embedding, chat):
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(b"GGUF")
    monkeypatch.setattr(discovery, "_ollama_candidates", lambda: [])
    monkeypatch.setattr(discovery, "_server_candidates", lambda cfg: [])

    paths = {c.path for c in discovery.discover() if c.source == "models_dir"}

    assert paths == {str(chat)}
