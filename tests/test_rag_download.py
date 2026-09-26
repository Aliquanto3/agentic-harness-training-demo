"""Story 15: « Télécharger » the embedding model (AD-15, AD-21), with `httpx.MockTransport`:
nothing leaves the machine."""

from __future__ import annotations

import hashlib
import re
import threading
import time

import httpx
import pytest
from fake_engine import FakeEngine
from starlette.testclient import TestClient
from test_bricks import HEADERS
from test_rag import MODEL_FILE, MODEL_SIZE, Embedders, build, card, place_model, rag_config

from wavestack import config
from wavestack.config import EmbeddingFile
from wavestack.models.download import DownloadError, download_files
from wavestack.models.engine import CancelToken
from wavestack.session.app_session import AppSession, SendRefused
from wavestack.session.diagnostic import DiagnosticSession
from wavestack.trace.journal import get_journal
from wavestack.web.app import create_app

URL = "https://huggingface.co/demo/resolve/main/fake.gguf"
CDN = "https://cdn-lfs.hf.co/demo/fake.gguf"
BYTES = bytes(range(256)) * 4  # 1 024 bytes


@pytest.fixture
def index(tmp_path):
    path = tmp_path / "rag_index.sqlite"
    build(path)
    return path


class Server:
    """A scripted Hub: `huggingface.co` redirects to `cdn` (a 302), which sends `body`.
    `gate`: the CDN waits for it before answering."""

    def __init__(self, cdn: str = CDN, body: bytes = BYTES[:MODEL_SIZE], gate=None) -> None:
        self.cdn, self.body, self.gate = cdn, body, gate
        self.urls: list[str] = []

    def __call__(self, request: httpx.Request) -> httpx.Response:
        self.urls.append(str(request.url))
        if request.url.host == "huggingface.co":
            return httpx.Response(302, headers={"location": self.cdn})
        if self.gate is not None:
            self.gate.wait(timeout=5)
        return httpx.Response(200, content=self.body)


def download_session(values: dict, server: Server, embedders: Embedders | None = None):
    embedders = embedders or Embedders()
    engine = FakeEngine(output="Bonjour.")
    session = AppSession(
        config.Config(values=values),
        engine_factory=lambda path, n_ctx: engine,
        embedder_factory=embedders,
        download_transport=httpx.MockTransport(server),
    )
    session.boot("fake.gguf").result()
    session.set_brick("rag", True)
    session.join()
    return session, embedders


def wait_download(session: AppSession) -> None:
    deadline = time.monotonic() + 10
    while time.monotonic() < deadline:
        if session.state == "idle" and session._download_cancel is None:
            break
        time.sleep(0.01)
    time.sleep(0.05)  # the thread's last emissions
    session.join()


def test_download_follows_the_redirect_traces_each_hop_and_loads_the_model(index):
    server = Server()
    session, embedders = download_session(rag_config(index), server)
    assert card(session)["download"] is not None
    mark = get_journal().last_seq()

    reason = session.download_model("rag_embedding")
    wait_download(session)

    assert re.fullmatch(r"Téléchargement du modèle d'embedding : 0 % \(0 / \d+ Mo\)", reason)
    events = get_journal().events_since(mark)
    states = [e.payload for e in events if e.kind == "session_state"]
    assert states[0]["state"] == "download" and states[-1]["state"] == "idle"
    outbound = [e for e in events if e.kind == "outbound_request"]
    assert [e.payload["url"] for e in outbound] == [URL, CDN]
    assert {e.payload["origin"] for e in outbound} == {"download"}
    assert {e.turn_id for e in outbound} == {None}
    target = config.models_dir() / MODEL_FILE
    assert target.read_bytes() == BYTES[:MODEL_SIZE]
    assert not target.with_name(target.name + ".part").exists()
    assert len(embedders.made) == 1  # the brick was wanted: loaded
    rag = card(session)
    assert rag["available"] is True and rag["download"] is None
    kinds = [e.kind for e in events]
    assert {"bricks_changed", "architecture_changed", "context_preview"} <= set(kinds)
    assert "harness_error" not in kinds
    session.close()


@pytest.mark.parametrize(
    ("server", "cause"),
    [
        (Server(cdn="https://evil.example.com/fake.gguf"), "connexion refusée par le harnais"),
        (Server(body=BYTES[:10]), "taille reçue incorrecte : 10 octets au lieu de 1000"),
        (Server(cdn="http://cdn-lfs.hf.co/fake.gguf"), "adresse non https refusée"),
    ],
)
def test_a_failed_download_removes_the_part_and_says_what_to_copy(index, server, cause):
    session, embedders = download_session(rag_config(index), server)
    mark = get_journal().last_seq()

    session.download_model("rag_embedding")
    wait_download(session)

    errors = [e.payload for e in get_journal().events_since(mark) if e.kind == "harness_error"]
    assert len(errors) == 1 and cause in errors[0]["cause"]
    folder = config.models_dir() / "embedding"
    assert f"copiez le fichier à la main dans {folder}" in errors[0]["effect_fr"]
    assert not folder.exists() or not any(folder.iterdir())  # no `.part`, no file
    assert session.state == "idle" and embedders.made == []
    assert card(session)["download"] is not None  # still offered
    session.close()


def test_stop_cancels_the_download(index):
    gate = threading.Event()
    session, _ = download_session(rag_config(index), Server(gate=gate))
    mark = get_journal().last_seq()
    session.download_model("rag_embedding")
    assert session.state == "download"

    assert session.stop() is True
    gate.set()
    wait_download(session)

    errors = [e.payload for e in get_journal().events_since(mark) if e.kind == "harness_error"]
    assert errors[0]["message_fr"] == "Téléchargement du modèle d'embedding arrêté."
    assert not (config.models_dir() / MODEL_FILE).exists()
    assert not (config.models_dir() / (MODEL_FILE + ".part")).exists()
    session.close()


def test_sha256_mismatch_fails_and_a_declared_one_passes(tmp_path):
    body = BYTES[:MODEL_SIZE]
    good = hashlib.sha256(body).hexdigest()
    transport = httpx.MockTransport(lambda request: httpx.Response(200, content=body))
    wrong = EmbeddingFile(url=URL, path="m/x.gguf", size=MODEL_SIZE, sha256="0" * 64)
    with pytest.raises(DownloadError, match="sha256"):
        download_files([wrong], tmp_path, CancelToken(), lambda *p: None, transport=transport)
    assert not (tmp_path / "m/x.gguf.part").exists() and not (tmp_path / "m/x.gguf").exists()

    right = EmbeddingFile(url=URL, path="m/x.gguf", size=MODEL_SIZE, sha256=good)
    progress: list[tuple[int, int]] = []
    download_files([right], tmp_path, CancelToken(), lambda *p: progress.append(p),
                   transport=transport)  # fmt: skip
    assert (tmp_path / "m/x.gguf").read_bytes() == body
    assert progress[-1] == (MODEL_SIZE, MODEL_SIZE)


def test_download_is_refused_outside_idle_with_the_reason(index):
    gate = threading.Event()
    engine = FakeEngine(output="Bonjour.", gate=gate)
    session = AppSession(
        config.Config(values=rag_config(index)),
        engine_factory=lambda path, n_ctx: engine,
        embedder_factory=Embedders(),
    )
    session.boot("fake.gguf").result()
    client = client_of(session)
    session.send("Bonjour")  # the turn waits on the gate

    answer = client.post("/api/intentions/download_model", json={"target": "rag_embedding"},
                         headers=HEADERS)  # fmt: skip

    assert answer.status_code == 409
    assert answer.json()["detail"].startswith("Un tour est déjà en cours")
    gate.set()
    session.join()
    session.close()


def client_of(session: AppSession) -> TestClient:
    app = create_app(
        DiagnosticSession(config.load_config(), port=8421),
        port=8421,
        version="test",
        app_session=session,
    )
    return TestClient(app, base_url="http://127.0.0.1:8421")


def test_routes_unknown_target_404_and_nothing_to_download_409(index):
    place_model()
    session, embedders = download_session(rag_config(index), Server())
    client = client_of(session)

    unknown = client.post("/api/intentions/download_model", json={"target": "llm"},
                          headers=HEADERS)  # fmt: skip
    present = client.post("/api/intentions/download_model", json={"target": "rag_embedding"},
                          headers=HEADERS)  # fmt: skip

    assert unknown.status_code == 404
    assert present.status_code == 409 and present.json()["detail"].startswith("Rien à télécharger")
    with pytest.raises(SendRefused):
        session.download_model("rag_embedding")
    session.close()


def test_a_file_copied_by_hand_is_found_by_the_download_button(index):
    session, embedders = download_session(rag_config(index), Server())
    assert "modèle absent" in card(session)["reason_fr"]
    place_model()  # copied by hand while WaveStack runs

    with pytest.raises(SendRefused, match="Rien à télécharger"):
        session.download_model("rag_embedding")
    session.join()

    assert card(session)["available"] is True and len(embedders.made) == 1
    session.close()
