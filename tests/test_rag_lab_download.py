"""Lot 5c-4: « Télécharger » a model missing from the RAG workshop's stage (Composer): the
workshop's own models (`rag_lab_embedding:<id>`, `rag_lab_reranker:<id>`, traced outside the
brick) and the brick's (`rag_embedding`, `rag_reranker`), the room on the disk checked first.

With `httpx.MockTransport` (the scripted Hub of `test_rag_download.py`): nothing leaves the
machine."""

from __future__ import annotations

import hashlib
import shutil
import threading
from pathlib import Path

import httpx
import pytest
from test_bricks import HEADERS
from test_rag import build
from test_rag_download import BYTES, Server, client_of, wait_download
from test_rag_lab_embeddings import E5, lab_entry
from test_rag_lab_rerankers import MINILM_HEADER, QWEN, place_lab
from test_rag_lab_rerankers import lab_entry as reranker_entry
from test_rag_rerank import RERANK_SIZE, rerank_config, session_for

from wavestack import config
from wavestack.messages import render
from wavestack.models import download as download_module
from wavestack.session.app_session import AppSession, SendRefused
from wavestack.trace.journal import get_journal

E5_TARGET = f"rag_lab_embedding:{E5}"
QWEN_TARGET = f"rag_lab_reranker:{QWEN}"
SIZE = 1000  # the declared size of the tests' entries (`lab_entry`)


@pytest.fixture
def index(tmp_path) -> Path:
    path = tmp_path / "rag_index.sqlite"
    build(path)
    return path


def values(index: Path, *, embeddings=(), rerankers=()) -> dict:  # noqa: ANN001
    data = rerank_config(index)
    data["rag_lab"] = {"embeddings": list(embeddings), "rerankers": list(rerankers)}
    return data


def lab_session(data: dict, server: Server | None = None, **kwargs) -> AppSession:  # noqa: ANN003
    """A booted session, the RAG brick off (as in the workshop's own tests), downloading
    from the scripted Hub."""
    kwargs.setdefault("rerank", False)
    kwargs.setdefault("bricks", ())
    transport = httpx.MockTransport(server or Server())
    session, _ = session_for(data, transport=transport, **kwargs)
    return session


def options(session: AppSession, kind: str) -> dict:
    stages = session.rag_lab_state()["catalog"]["stages"]
    return {o["id"]: o for o in next(s for s in stages if s["kind"] == kind)["options"]}


def model_file(kind: str, model_id: str) -> Path:
    return config.models_dir() / f"{kind}/{model_id}.gguf"


# ---------- the catalog: « Télécharger » offered in the stage ----------


def test_an_absent_workshop_model_offers_its_download_in_its_stage(index):
    big = lab_entry(files=[{"url": lab_entry()["files"][0]["url"],
                            "path": f"embedding/{E5}.gguf", "size": 132_439_008}])  # fmt: skip
    session = lab_session(values(index, embeddings=[big], rerankers=[reranker_entry()]))

    e5 = options(session, "embedding")[E5]
    qwen = options(session, "rerank")[QWEN]

    assert (
        e5["available"] is False
        and "Cliquez sur « Télécharger » dans cette étape en mode Composer" in (e5["reason_text"])
    )
    assert "pas encore" not in e5["reason_text"]
    assert e5["download"] == {"target": E5_TARGET, "label_text": "Télécharger (≈ 132 Mo)"}
    assert qwen["available"] is False and "Cliquez sur « Télécharger »" in qwen["reason_text"]
    assert qwen["download"] == {"target": QWEN_TARGET, "label_text": "Télécharger (≈ 1 Mo)"}
    # The others: nothing to download (the workshop's own options, fastembed never).
    assert options(session, "embedding")["fastembed"]["download"] is None
    assert options(session, "vector_store")["memory"]["download"] is None
    session.close()


def test_the_bricks_models_absent_offer_the_cards_targets(index):
    session = lab_session(values(index))

    declared = options(session, "embedding")["declared"]
    rerank = options(session, "rerank")["declared"]

    assert declared["download"]["target"] == "rag_embedding"
    assert declared["download"]["label_text"].startswith("Télécharger le modèle d'embedding")
    assert rerank["download"]["target"] == "rag_reranker"
    assert rerank["download"]["label_text"].startswith("Télécharger le modèle de reranking")
    session.close()


def test_a_present_model_or_a_refused_reranker_offers_no_download(index):
    place_lab(QWEN, MINILM_HEADER)  # there, but a cross-encoder the adapter refuses
    session = lab_session(values(index, rerankers=[reranker_entry()]))

    qwen = options(session, "rerank")[QWEN]

    assert qwen["available"] is False and qwen["download"] is None
    assert qwen["reason_text"].startswith("Indisponible : ")
    assert "Télécharger" not in qwen["reason_text"]
    session.close()


# ---------- the download ----------


@pytest.mark.parametrize(
    ("target", "kind", "model_id", "component", "noun"),
    [
        (E5_TARGET, "embedding", E5, "rag_lab.embedding", "d'embedding"),
        (QWEN_TARGET, "reranker", QWEN, "rag_lab.rerank", "de reranking"),
    ],
)
def test_a_workshop_model_downloads_outside_the_brick(index, target, kind, model_id,
                                                      component, noun):  # fmt: skip
    session = lab_session(values(index, embeddings=[lab_entry()], rerankers=[reranker_entry()]))
    mark = get_journal().last_seq()

    reason = session.download_model(target)
    wait_download(session)

    assert reason.startswith(f"Téléchargement du modèle {noun} : 0 %")
    assert model_file(kind, model_id).read_bytes() == BYTES[:SIZE]
    assert not model_file(kind, model_id).with_suffix(".gguf.part").exists()
    events = get_journal().events_since(mark)
    states = [e.payload["state"] for e in events if e.kind == "session_state"]
    assert states[0] == "download" and states[-1] == "idle"
    assert [e for e in events if e.brick == "rag"] == []  # never on the RAG card
    effects = [e for e in events if e.kind == "effect_applied"]
    assert [e.payload["effect"] for e in effects] == ["model_download"]
    done = effects[0]
    assert (done.brick, done.context_id, done.component, done.turn_id) == (
        None,
        "rag_lab",
        component,
        None,
    )
    sha = hashlib.sha256(BYTES[:SIZE]).hexdigest()
    assert done.payload["lines"] == [f"{model_file(kind, model_id)} · sha256 {sha}"]
    outbound = [e for e in events if e.kind == "outbound_request"]
    assert outbound and {(e.context_id, e.payload["origin"]) for e in outbound} == {
        ("rag_lab", "download")
    }
    assert "harness_error" not in {e.kind for e in events}
    # The catalog read again: the option chosen now, nothing left to download.
    option = options(session, "rerank" if kind == "reranker" else "embedding")[model_id]
    assert option["available"] is True and option["download"] is None
    assert session.state == "idle"
    session.close()


def test_the_declared_sha256_is_checked(index):
    entry = lab_entry()
    entry["files"][0]["sha256"] = "0" * 64
    session = lab_session(values(index, embeddings=[entry]))
    mark = get_journal().last_seq()

    session.download_model(E5_TARGET)
    wait_download(session)

    errors = [e for e in get_journal().events_since(mark) if e.kind == "harness_error"]
    assert len(errors) == 1 and "sha256" in errors[0].payload["cause"]
    assert not model_file("embedding", E5).exists()
    session.close()


@pytest.mark.parametrize(
    ("server", "cause"),
    [
        (Server(body=BYTES[:10]), "taille reçue incorrecte : 10 octets au lieu de 1000"),
        (Server(cdn="https://evil.example.com/lab.gguf"), "connexion refusée par le harnais"),
    ],
)
def test_a_failed_download_is_said_outside_the_brick(index, server, cause):
    session = lab_session(values(index, embeddings=[lab_entry()]), server)
    mark = get_journal().last_seq()

    session.download_model(E5_TARGET)
    wait_download(session)

    events = get_journal().events_since(mark)
    errors = [e for e in events if e.kind == "harness_error"]
    assert len(errors) == 1
    error = errors[0]
    assert (error.brick, error.context_id, error.component) == (
        None,
        "rag_lab",
        "rag_lab.embedding",
    )
    assert error.payload["message_text"] == "Le téléchargement du modèle d'embedding a échoué."
    assert cause in error.payload["cause"]
    assert (
        f"copiez le fichier à la main dans {config.models_dir() / 'embedding'}"
        in (error.payload["effect_text"])
    )
    assert not model_file("embedding", E5).exists()
    assert not model_file("embedding", E5).with_suffix(".gguf.part").exists()
    assert session.state == "idle"
    assert options(session, "embedding")[E5]["download"] is not None  # still offered
    session.close()


def test_stop_ends_the_download_with_a_neutral_line(index):
    gate = threading.Event()
    session = lab_session(values(index, embeddings=[lab_entry()]), Server(gate=gate))
    mark = get_journal().last_seq()
    session.download_model(E5_TARGET)
    assert session.state == "download"

    assert session.stop() is True
    gate.set()
    wait_download(session)

    events = get_journal().events_since(mark)
    assert [e for e in events if e.kind == "harness_error"] == []
    stopped = [e for e in events if e.kind == "effect_applied"]
    assert [e.payload["effect"] for e in stopped] == ["model_download_stopped"]
    assert (stopped[0].brick, stopped[0].component) == (None, "rag_lab.embedding")
    assert stopped[0].payload["lines"][0].startswith("Téléchargement du modèle d'embedding arrêté")
    assert not model_file("embedding", E5).exists()
    assert not model_file("embedding", E5).with_suffix(".gguf.part").exists()
    e5 = options(session, "embedding")[E5]
    assert e5["available"] is False and e5["download"] is not None
    assert session.state == "idle"
    session.close()


# ---------- the room on the disk ----------


def test_not_enough_room_refuses_before_anything_starts(index, monkeypatch):
    big = lab_entry(files=[{"url": lab_entry()["files"][0]["url"],
                            "path": f"embedding/{E5}.gguf", "size": 640_000_000}])  # fmt: skip
    server = Server()
    session = lab_session(values(index, embeddings=[big]), server)
    monkeypatch.setattr(download_module, "free_bytes", lambda dest: 200_000_000)
    mark = get_journal().last_seq()

    with pytest.raises(SendRefused) as refused:
        session.download_model(E5_TARGET)

    said = render(refused.value.reason_text, "fr")
    assert said.startswith(
        "Place insuffisante pour le modèle d'embedding : 640 Mo à télécharger, 200 Mo libres "
        f"dans {config.models_dir()}"
    )
    assert session.state == "idle" and server.urls == []
    assert [e for e in get_journal().events_since(mark) if e.kind == "session_state"] == []
    client = client_of(session)
    answer = client.post("/api/intentions/download_model", json={"target": E5_TARGET},
                         headers=HEADERS)  # fmt: skip
    assert answer.status_code == 409 and answer.json()["detail"].startswith("Place insuffisante")
    session.close()


def test_the_room_is_checked_for_the_bricks_model_too(index, monkeypatch):
    session = lab_session(values(index), bricks=("rag",))
    monkeypatch.setattr(download_module, "free_bytes", lambda dest: 10)

    with pytest.raises(SendRefused, match="Place insuffisante pour le modèle d'embedding"):
        session.download_model("rag_embedding")
    with pytest.raises(SendRefused, match="Place insuffisante pour le modèle de reranking"):
        session.download_model("rag_reranker")
    assert session.state == "idle"
    session.close()


def test_an_unreadable_disk_does_not_refuse(index, monkeypatch):
    session = lab_session(values(index, embeddings=[lab_entry()]))
    monkeypatch.setattr(download_module, "free_bytes", lambda dest: None)

    session.download_model(E5_TARGET)
    wait_download(session)

    assert model_file("embedding", E5).is_file()
    session.close()


def test_free_bytes_reads_the_first_existing_parent(tmp_path, monkeypatch):
    free = download_module.free_bytes(tmp_path / "not" / "yet" / "there")
    assert isinstance(free, int) and free > 0

    seen: list[Path] = []

    def disk_usage(path):  # noqa: ANN001, ANN202
        seen.append(Path(path))
        raise OSError("disque illisible")

    monkeypatch.setattr(shutil, "disk_usage", disk_usage)
    assert download_module.free_bytes(tmp_path / "absent") is None
    assert seen == [tmp_path]


# ---------- refusals ----------


def test_an_unknown_target_is_404(index):
    session = lab_session(values(index, embeddings=[lab_entry()]))
    client = client_of(session)

    for target in ("rag_lab_embedding:nope", "rag_lab_reranker:nope", "rag_lab_embedding:"):
        with pytest.raises(KeyError):
            session.download_model(target)
        answer = client.post("/api/intentions/download_model", json={"target": target},
                             headers=HEADERS)  # fmt: skip
        assert answer.status_code == 404
        assert answer.json()["detail"] == "Cible de téléchargement inconnue."
    # An embedding model's id is no reranker's target.
    with pytest.raises(KeyError):
        session.download_model(f"rag_lab_reranker:{E5}")
    session.close()


def test_a_busy_session_refuses_with_its_reason(index):
    gate = threading.Event()
    session = lab_session(
        values(index, embeddings=[lab_entry()], rerankers=[reranker_entry()]), Server(gate=gate)
    )
    client = client_of(session)
    session.download_model(E5_TARGET)

    with pytest.raises(SendRefused):
        session.download_model(QWEN_TARGET)
    answer = client.post("/api/intentions/download_model", json={"target": QWEN_TARGET},
                         headers=HEADERS)  # fmt: skip
    assert answer.status_code == 409 and answer.json()["detail"]

    gate.set()
    wait_download(session)
    session.close()


def test_a_file_copied_by_hand_meanwhile_has_nothing_to_download(index):
    session = lab_session(values(index, embeddings=[lab_entry()]))
    assert options(session, "embedding")[E5]["download"] is not None
    path = model_file("embedding", E5)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(b"\0" * SIZE)  # copied by hand while WaveStack runs
    client = client_of(session)

    answer = client.post("/api/intentions/download_model", json={"target": E5_TARGET},
                         headers=HEADERS)  # fmt: skip

    assert answer.status_code == 409 and answer.json()["detail"].startswith("Rien à télécharger")
    e5 = options(session, "embedding")[E5]
    assert e5["available"] is True and e5["download"] is None
    session.close()


def test_the_bricks_model_keeps_the_bricks_scope(index):
    session = lab_session(values(index), Server(body=BYTES[:RERANK_SIZE]), bricks=("rag",))
    mark = get_journal().last_seq()

    session.download_model("rag_reranker")
    wait_download(session)

    effects = [e for e in get_journal().events_since(mark) if e.kind == "effect_applied"]
    assert [(e.payload["effect"], e.brick, e.component) for e in effects] == [
        ("model_download", "rag", "rag.reranker")
    ]
    assert options(session, "rerank")["declared"]["download"] is None
    session.close()


def test_the_files_are_read_again_before_idle(index):
    """The page reads the catalog again when the session leaves `download`: by then the
    brick's « Télécharger » is gone, without waiting for `_rag_caught_up`."""
    session = lab_session(values(index), Server(), bricks=("rag",))
    seen: list[tuple[str, object]] = []
    caught_up = session._rag_caught_up

    def record() -> None:
        seen.append((session.state, options(session, "embedding")["declared"]["download"]))
        caught_up()

    session._rag_caught_up = record  # type: ignore[method-assign]

    session.download_model("rag_embedding")
    wait_download(session)

    assert seen == [("idle", None)]
    session.close()


def test_the_need_is_rounded_up_never_below_the_free_room(index, monkeypatch):
    big = lab_entry(files=[{"url": lab_entry()["files"][0]["url"],
                            "path": f"embedding/{E5}.gguf", "size": 640_400_000}])  # fmt: skip
    session = lab_session(values(index, embeddings=[big]))
    monkeypatch.setattr(download_module, "free_bytes", lambda dest: 640_300_000)

    with pytest.raises(SendRefused) as refused:
        session.download_model(E5_TARGET)

    assert "641 Mo à télécharger, 640 Mo libres" in render(refused.value.reason_text, "fr")
    session.close()


# ---------- languages ----------


@pytest.mark.parametrize(
    ("lang", "label", "reason", "full", "progress"),
    [
        (
            "en",
            "Download (≈ 1 MB)",
            "Click “Download” in this stage in “Compose” mode",
            "Not enough room for the embedding model: 1 MB to download, 0 MB free in",
            "Downloading the embedding model: 0%",
        ),
        (
            "de",
            "Herunterladen (≈ 1 MB)",
            "Klicken Sie in diesem Schritt im Modus „Zusammenstellen“ auf „Herunterladen“",
            "Nicht genug Platz für das Embedding-Modell: 1 MB zum Herunterladen benötigt, "
            "0 MB frei in",
            "Download des Embedding-Modells: 0 %",
        ),
    ],
)
def test_the_texts_are_translated(index, monkeypatch, lang, label, reason, full, progress):
    session = lab_session(values(index, embeddings=[lab_entry()]))
    session.set_language(lang)
    session.join()

    e5 = options(session, "embedding")[E5]
    assert e5["download"]["label_text"] == label and reason in e5["reason_text"]
    content = session.rag_lab_state()["content"]
    assert content["download_stop_text"] and content["download_done_text"]
    monkeypatch.setattr(download_module, "free_bytes", lambda dest: 10)
    with pytest.raises(SendRefused) as refused:
        session.download_model(E5_TARGET)
    assert render(refused.value.reason_text, lang).startswith(full)
    monkeypatch.setattr(download_module, "free_bytes", lambda dest: None)
    assert render(session.download_model(E5_TARGET), lang).startswith(progress)
    wait_download(session)
    session.close()
