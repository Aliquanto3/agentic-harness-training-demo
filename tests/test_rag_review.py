"""Story 15, independent review: a fresh install reaches a real search from the UI
(« Télécharger » then « Construire l'index »), the model file's identity, a stale or replaced
index, loads that fail or race, and the hardened helpers."""

from __future__ import annotations

import importlib.util
import json
import math
import pickle
import sqlite3
import sys
import threading
import time
import types
from pathlib import Path

import httpx
import httpx2
import pytest
from fake_embedder import DIMS, MODEL_ID, FakeEmbedder
from fake_engine import FakeEngine
from pydantic import ValidationError
from test_rag import (
    CLOSED_FIRST,
    COVERED,
    MODEL_FILE,
    MODEL_SIZE,
    REPLACED_WHILE_OPEN,
    Embedders,
    build,
    card,
    place_model,
    rag_config,
    rag_session,
    rag_values,
    segments,
    turn_events,
)

from wavestack import config
from wavestack.config import EmbeddingModel, ModelFile
from wavestack.models import discovery
from wavestack.models.download import DownloadError, StopToken, download_files
from wavestack.models.embedding import LlamaCppEmbedder
from wavestack.models.load_registry import EMBEDDING, ModelChoice
from wavestack.net import factory
from wavestack.rag import index as rag_index
from wavestack.rag.corpus import load_rag_content
from wavestack.rag.retriever import score_of
from wavestack.session.app_session import INDEX_HELD_FR, SendRefused
from wavestack.trace.journal import get_journal

URL = "https://huggingface.co/demo/resolve/main/fake.gguf"


@pytest.fixture
def index(tmp_path):
    path = tmp_path / "rag_index.sqlite"
    build(path)
    return path


def wait_idle(session) -> None:  # noqa: ANN001
    deadline = time.monotonic() + 10
    while time.monotonic() < deadline:
        if session.state == "idle" and session._download_cancel is None:
            break
        time.sleep(0.01)
    time.sleep(0.05)
    session.join()


def since(mark: int, kind: str) -> list:
    return [e for e in get_journal().events_since(mark) if e.kind == kind]


# ---------- the fresh install: download, build, search ----------


def test_fresh_install_offers_download_then_build_then_searches(tmp_path):
    index = tmp_path / "rag_index.sqlite"
    session, embedders = rag_session(rag_config(index))  # neither model nor index

    rag = card(session)
    assert "index absent" in rag["reason_text"] and "Téléchargez d'abord" in rag["reason_text"]
    assert "`" not in rag["reason_text"]
    assert rag["download"]["target"] == "rag_embedding" and rag["build_index"] is None
    with pytest.raises(SendRefused, match="Cliquez d'abord sur « Télécharger »"):
        session.build_rag_index()

    place_model()  # what « Télécharger » writes
    with pytest.raises(SendRefused, match="Rien à télécharger"):
        session.download_model("rag_embedding")
    rag = card(session)
    assert rag["download"] is None and rag["build_index"] == {"label_text": "Construire l'index"}

    mark = get_journal().last_seq()
    assert session.build_rag_index().startswith("Construction de l'index RAG")
    assert session.state == "index_build"
    wait_idle(session)

    written = [e for e in since(mark, "effect_applied") if e.payload["effect"] == "rag_index_write"]
    assert len(written) == 1 and str(index) in written[0].payload["lines"][0]
    assert (written[0].brick, written[0].component) == ("rag", "file.rag_index")
    states = [e.payload["state"] for e in since(mark, "session_state")]
    assert states[0] == "index_build" and states[-1] == "idle"
    meta = rag_index.read_meta(index)
    assert (meta.embedding_model_id, meta.model_size) == (MODEL_ID, MODEL_SIZE)
    assert meta.corpus_sha256 and len(meta.model_sha256) == 64
    assert not index.with_name(index.name + ".tmp").exists()
    rag = card(session)
    assert rag["available"] is True and rag["build_index"] is None
    assert embedders.made[0].closed  # the build's own model, closed
    assert session._load_registry.holder(EMBEDDING) == "Faux embedding"  # the brick's
    ended = next(e for e in turn_events(COVERED, session) if e.kind == "rag_search_ended")
    assert ended.payload["status"] == "ok" and ended.payload["excerpts"][0]["doc_id"] == (
        "mots_de_passe"
    )
    session.close()


def test_build_can_be_stopped_and_writes_nothing(tmp_path):
    index = tmp_path / "rag_index.sqlite"
    place_model()
    gate = threading.Event()
    session, _ = rag_session(rag_config(index), embedders=Embedders(gate=gate))
    mark = get_journal().last_seq()
    session.build_rag_index()

    assert session.stop() is True
    gate.set()
    wait_idle(session)

    errors = since(mark, "harness_error")
    assert errors[0].payload["message_text"] == "Construction de l'index RAG arrêtée."
    assert not index.exists() and not index.with_name(index.name + ".tmp").exists()
    assert session._load_registry.holder(EMBEDDING) is None
    session.close()


def test_build_is_refused_when_the_index_is_up_to_date_or_outside_idle(tmp_path):
    index = tmp_path / "rag_index.sqlite"
    build(index)
    place_model()
    session, _ = rag_session(rag_config(index))
    with pytest.raises(SendRefused, match="l'index est à jour"):
        session.build_rag_index()
    session.close()


def test_stale_index_is_unavailable_and_offers_the_build(tmp_path):
    index = tmp_path / "rag_index.sqlite"
    rag_index.build_index(load_rag_content(), FakeEmbedder(), index, chunk_max_chars=600)
    place_model()
    session, embedders = rag_session(rag_config(index))

    rag = card(session)
    assert rag["available"] is False and "index périmé" in rag["reason_text"]
    assert "chunk_max_chars" in rag["reason_text"] and rag["build_index"] is not None
    assert embedders.made == []
    session.close()


# ---------- the model file's identity ----------


def test_another_file_of_the_same_dimensions_is_not_taken_for_the_model(tmp_path):
    index = tmp_path / "rag_index.sqlite"
    build(index)
    path = config.models_dir() / MODEL_FILE
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(b"\1" * (MODEL_SIZE + 7))  # a stand-in: another GGUF, same dims
    session, embedders = rag_session(rag_config(index))

    rag = card(session)
    assert rag["available"] is False and "n'est pas le modèle d'embedding" in rag["reason_text"]
    assert rag["download"] is not None and embedders.made == []
    session.close()


def test_an_index_built_from_another_file_is_refused(tmp_path):
    index = tmp_path / "rag_index.sqlite"
    other = tmp_path / "other.gguf"
    other.write_bytes(b"\2" * 999)
    rag_index.build_index(load_rag_content(), FakeEmbedder(), index, 700, model_file=other)
    place_model()
    session, _ = rag_session(rag_config(index))

    rag = card(session)
    assert rag["available"] is False and "fichier de" in rag["reason_text"]
    assert rag["build_index"] is not None
    session.close()


def test_a_declared_sha256_is_checked_before_loading(tmp_path):
    index = tmp_path / "rag_index.sqlite"
    build(index)
    place_model()
    files = [{"url": URL, "path": MODEL_FILE, "size": MODEL_SIZE, "sha256": "0" * 64}]
    session, embedders = rag_session(rag_config(index, files=files))

    rag = card(session)
    assert rag["available"] is False and "sha256 différent" in rag["reason_text"]
    assert embedders.made == [] and session._load_registry.holder(EMBEDDING) is None
    session.close()


# ---------- loads: scenario and reset, failures, races, the budget's second chance ----------


def test_scenario_loads_the_model_and_reset_releases_it(index):
    place_model()
    session, embedders = rag_session(rag_config(index), bricks=())
    session.launch_scenario("rag")
    session.join()
    assert card(session)["available"] is True and len(embedders.made) == 1

    session.reset()
    session.join()

    assert embedders.made[0].closed and session._load_registry.holder(EMBEDDING) is None
    session.close()


def test_a_failing_factory_leaves_the_brick_unavailable_and_the_registry_free(index):
    place_model()

    def broken(model):  # noqa: ANN001
        raise RuntimeError("GGUF illisible")

    mark = get_journal().last_seq()
    session, _ = rag_session(rag_config(index), embedders=broken)

    rag = card(session)
    assert rag["available"] is False and "n'a pas pu être chargé" in rag["reason_text"]
    assert session._load_registry.holder(EMBEDDING) is None and not session._rag_loading
    errors = [e for e in since(mark, "harness_error") if "embedding" in e.payload["message_text"]]
    assert len(errors) == 1 and errors[0].brick == "rag"
    session.close()


def test_a_model_that_fails_then_is_deleted_is_offered_again_on_reactivation(index):
    """The failure's text says what works without a relaunch: delete the file, switch the
    brick off and on; the card then reads the files again and offers the download."""
    path = place_model()

    def broken(model):  # noqa: ANN001
        raise RuntimeError("GGUF illisible")

    session, _ = rag_session(rag_config(index), embedders=broken)
    reason = card(session)["reason_text"]
    assert "relancez" not in reason and "réactivez la brique RAG" in reason

    path.unlink()
    session.set_brick("rag", False)
    session.join()
    mark = get_journal().last_seq()
    session.set_brick("rag", True)
    session.join()

    rag = card(session, mark)
    assert rag["available"] is False and "modèle absent" in rag["reason_text"]
    assert rag["download"] is not None
    session.close()


def test_switching_the_brick_off_while_it_loads_closes_the_model(index):
    place_model()
    entered, gate = threading.Event(), threading.Event()
    made: list[FakeEmbedder] = []

    def slow(model):  # noqa: ANN001
        entered.set()
        gate.wait(timeout=5)
        made.append(FakeEmbedder(model_id=model.id))
        return made[-1]

    session, _ = rag_session(rag_config(index), embedders=slow, bricks=())
    session.set_brick("rag", True)
    assert entered.wait(5)  # the worker is loading it
    session.set_brick("rag", False)
    gate.set()
    session.join()

    assert made[0].closed and session._embedder is None
    assert session._load_registry.holder(EMBEDDING) is None
    session.close()


def test_a_budget_refusal_is_retried_after_a_model_switch(index, tmp_path):
    place_model()
    rss = {"now": 200 * 1024**2}
    engine = FakeEngine()
    session, embedders = rag_session(rag_config(index, budget_mb=100), engine=engine, bricks=())
    session._load_registry._rss = lambda: rss["now"]
    session.set_brick("rag", True)
    session.join()
    assert "Mémoire insuffisante" in card(session)["reason_text"] and embedders.made == []

    rss["now"] = 10 * 1024**2  # the switch frees memory
    other = tmp_path / "other.gguf"
    other.write_bytes(b"\0" * 10)
    _, future = session.switch_model(ModelChoice("file", str(other)))
    future.result()
    session.join()

    assert card(session)["available"] is True and len(embedders.made) == 1
    session.close()


def test_sqlite_vec_that_does_not_load_makes_the_brick_unavailable(index, monkeypatch):
    import sqlite_vec

    def no_extension(conn):  # noqa: ANN001
        raise AttributeError("'sqlite3.Connection' object has no attribute 'enable_load_extension'")

    monkeypatch.setattr(sqlite_vec, "load", no_extension)
    place_model()
    session, embedders = rag_session(rag_config(index))

    rag = card(session)
    assert rag["available"] is False and "sqlite-vec" in rag["reason_text"]
    assert rag["download"] is None and rag["build_index"] is None and embedders.made == []
    session.close()


def test_a_file_that_is_no_sqlite_index_is_unreadable(tmp_path):
    index = tmp_path / "rag_index.sqlite"
    index.write_bytes(b"pas une base SQLite")
    place_model()
    session, _ = rag_session(rag_config(index))

    rag = card(session)
    assert rag["available"] is False and "illisible" in rag["reason_text"]
    assert rag["build_index"] is not None
    session.close()


@pytest.mark.parametrize("close_first", [CLOSED_FIRST, REPLACED_WHILE_OPEN])
def test_an_index_replaced_during_the_session_is_read_again(index, close_first):
    place_model()
    session, _ = rag_session(rag_config(index))
    time.sleep(0.01)
    if close_first:  # so the file can be replaced on every OS (lot G)
        session._rag_retriever.close()
    # Another build meanwhile: the session notices it by the file's stamp (mtime, size).
    build(index, model_id="autre-modele")

    events = turn_events(COVERED, session)

    ended = next(e for e in events if e.kind == "rag_search_ended").payload
    assert ended["status"] == "error" and "remplacé" in ended["error_text"]
    rag = card(session)
    assert rag["available"] is False and "autre-modele" in rag["reason_text"]
    assert session._load_registry.holder(EMBEDDING) is None
    session.close()


def test_a_question_without_any_vector_fails_the_search_not_the_turn(index):
    place_model()
    session, _ = rag_session(rag_config(index))

    events = turn_events("de la ?", session)  # only short words: a null vector

    ended = next(e for e in events if e.kind == "rag_search_ended").payload
    assert ended["status"] == "error" and "vecteur nul" in ended["error_text"]
    assert next(e for e in events if e.kind == "turn_ended").payload["status"] == "completed"
    ctx = next(e.payload for e in events if e.kind == "context_rendered")
    assert segments(ctx, "rag_excerpt") == []
    session.close()


# ---------- helpers ----------


def test_score_is_bounded_to_zero_and_one():
    assert score_of(0.0) == 1.0 and score_of(0.25) == 0.75
    assert score_of(1.5) == 0.0 and score_of(-0.2) == 1.0 and score_of(math.nan) == 0.0


@pytest.mark.parametrize("path", ["/x.gguf", "\\x.gguf", "C:x.gguf", "C:\\x.gguf", "a/../b"])
def test_paths_outside_the_models_folder_are_refused(path):
    with pytest.raises(ValidationError):
        ModelFile(url=URL, path=path, size=1)


def test_load_path_must_be_a_declared_file(tmp_path):
    values = rag_values(tmp_path / "i.sqlite", load_path="embedding/autre.gguf")["embedding"]
    with pytest.raises(ValidationError, match="load_path must be one of files"):
        EmbeddingModel.model_validate(values)


def _fake_llama(monkeypatch, vector) -> None:  # noqa: ANN001
    class Llama:
        def __init__(self, **kwargs) -> None:  # noqa: ANN003
            pass

        def n_embd(self) -> int:
            return DIMS

        def embed(self, text, **kwargs):  # noqa: ANN001, ANN003
            return vector

        def close(self) -> None:
            pass

    monkeypatch.setitem(sys.modules, "llama_cpp", types.SimpleNamespace(Llama=Llama))


def test_a_gguf_without_pooling_is_refused_in_french(monkeypatch, tmp_path):
    model = EmbeddingModel.model_validate(rag_values(tmp_path / "i.sqlite")["embedding"])
    _fake_llama(monkeypatch, [[0.1] * DIMS, [0.2] * DIMS])  # one vector per token
    with pytest.raises(ValueError, match="pooling absent"):
        LlamaCppEmbedder(model, tmp_path / "x.gguf")
    _fake_llama(monkeypatch, [0.5] * DIMS)
    embedder = LlamaCppEmbedder(model, tmp_path / "x.gguf")
    assert embedder.embed_queries(["x"])[0][0] == pytest.approx(1 / math.sqrt(DIMS))


def test_the_whole_embedding_folder_is_never_offered_as_a_chat_model(monkeypatch):
    for name in ("embedding/autre-embedding.gguf", "qwen.gguf"):
        path = config.models_dir() / name
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(b"GGUF")
    monkeypatch.setattr(discovery, "_ollama_candidates", lambda: [])
    monkeypatch.setattr(discovery, "_server_candidates", lambda cfg: [])
    paths = {c.path for c in discovery.discover() if c.source == "models_dir"}
    assert paths == {str(config.models_dir() / "qwen.gguf")}


def test_a_failed_write_leaves_no_temporary_file(tmp_path, monkeypatch):
    def broken(*args):  # noqa: ANN002
        raise sqlite3.OperationalError("disque plein")

    monkeypatch.setattr(rag_index, "_fill", broken)
    path = tmp_path / "rag_index.sqlite"
    with pytest.raises(sqlite3.OperationalError):
        build(path)
    assert not path.exists() and not path.with_name(path.name + ".tmp").exists()


def refuse_replacing(monkeypatch, target, winerror: int | None = 32) -> None:  # noqa: ANN001
    """Lot G: the system refuses to replace `target`. `winerror` 32 (or 5, on a writable
    target): what Windows does when a handle holds it open; `None`: a POSIX refusal."""
    replace = rag_index.os.replace

    def refused(src, dst, **kwargs):  # noqa: ANN001, ANN003
        if Path(dst) == target:
            exc = PermissionError(13, "Accès refusé", str(dst))
            if winerror is not None:
                exc.winerror = winerror
            raise exc
        replace(src, dst, **kwargs)

    monkeypatch.setattr(rag_index.os, "replace", refused)


def test_an_index_in_use_is_refused_in_french_and_left_as_it_was(index, monkeypatch):
    refuse_replacing(monkeypatch, index)

    with pytest.raises(rag_index.IndexInUse) as refused:
        build(index, model_id="autre-modele")

    assert isinstance(refused.value, OSError)
    assert str(refused.value) == (
        "L'index est ouvert par un autre programme (WaveStack, un antivirus ou un outil de "
        "synchronisation) : il ne peut pas être remplacé."
    )
    assert isinstance(refused.value.__cause__, PermissionError)
    assert not index.with_name(index.name + ".tmp").exists()
    assert rag_index.read_meta(index).embedding_model_id == MODEL_ID  # the old one, intact
    copy = pickle.loads(pickle.dumps(refused.value))
    assert type(copy) is rag_index.IndexInUse and str(copy) == str(refused.value)


@pytest.mark.parametrize("read_only", [True, False], ids=["read-only-target", "posix"])
def test_another_refusal_is_not_taken_for_an_index_in_use(index, monkeypatch, read_only):
    if read_only:  # Windows' access denied on a read-only file
        refuse_replacing(monkeypatch, index, winerror=5)
        index.chmod(0o444)
        access = rag_index.os.access  # root may write anyway: say what the mode says
        monkeypatch.setattr(
            rag_index.os,
            "access",
            lambda p, mode, **kw: False if Path(p) == index else access(p, mode, **kw),  # noqa: ANN001, ANN003
        )
    else:  # EACCES: the folder is not writable (an open file never blocks it on POSIX)
        refuse_replacing(monkeypatch, index, winerror=None)
    try:
        with pytest.raises(PermissionError) as refused:
            build(index, model_id="autre-modele")
    finally:
        index.chmod(0o644)

    assert not isinstance(refused.value, rag_index.IndexInUse)
    assert "Accès refusé" in str(refused.value)
    assert not index.with_name(index.name + ".tmp").exists()


def test_the_simulated_windows_rules_refuse_replacing_an_open_index(index, windows_file_rules):
    if not Path("/proc/self/fd").is_dir():
        pytest.skip("simulation sans /proc : sous Windows, le système applique ses règles")
    conn = rag_index.connect(index)  # what the session's retriever holds
    try:
        with pytest.raises(rag_index.IndexInUse):
            build(index, model_id="autre-modele")
        with pytest.raises(PermissionError):
            index.unlink()
    finally:
        conn.close()
    assert rag_index.read_meta(index).embedding_model_id == MODEL_ID

    build(index, model_id="autre-modele")  # closed: replaced

    assert rag_index.read_meta(index).embedding_model_id == "autre-modele"


def test_the_card_says_another_program_holds_the_index(tmp_path, monkeypatch):
    index = tmp_path / "rag_index.sqlite"
    rag_index.build_index(load_rag_content(), FakeEmbedder(), index, chunk_max_chars=600)
    place_model()
    session, _ = rag_session(rag_config(index))  # a stale index: « Construire l'index »
    refuse_replacing(monkeypatch, index)
    mark = get_journal().last_seq()

    session.build_rag_index()
    wait_idle(session)

    error = next(e for e in since(mark, "harness_error") if e.component == "file.rag_index")
    assert error.payload["message_text"] == "L'index RAG n'a pas pu être construit."
    assert error.payload["cause"] == INDEX_HELD_FR
    assert "relancez ce script" not in str(error.payload)
    assert rag_index.read_meta(index).chunk_max_chars == 600  # left as it was
    assert not index.with_name(index.name + ".tmp").exists()
    session.close()


def test_a_redirected_post_is_traced_with_its_body_and_an_async_hop_with_a_marker():
    def server(request: httpx.Request) -> httpx.Response:
        if request.url.path == "/w/api.php":
            return httpx.Response(307, headers={"location": "https://fr.wikipedia.org/w/api2"})
        return httpx.Response(200, text="ok")

    mark = get_journal().last_seq()
    with factory.create_client(transport=httpx.MockTransport(server)) as client:
        client.post(
            "https://fr.wikipedia.org/w/api.php", content=b'{"q": 1}', follow_redirects=True
        )
    traced = [e.payload for e in since(mark, "outbound_request")]
    assert [p["body"] for p in traced] == ['{"q": 1}', '{"q": 1}']

    class Unread(httpx2.AsyncByteStream):
        async def __aiter__(self):  # noqa: ANN204
            yield b"x"

    hop = httpx2.Request("POST", "https://example.org/", stream=Unread())
    assert factory._body(hop).decode() == factory.REDIRECT_BODY_NOT_READ


class _Hanging(httpx.SyncByteStream):
    """A body that sends one chunk, then waits (a stalled server) until closed."""

    def __init__(self) -> None:
        self.closed = threading.Event()

    def __iter__(self):  # noqa: ANN204
        yield b"\0" * 10
        if not self.closed.wait(10):
            yield b"\0" * 10
        raise httpx.ReadError("fermé")

    def close(self) -> None:
        self.closed.set()


def test_stop_acts_at_once_while_waiting_for_data(tmp_path):
    body = _Hanging()
    transport = httpx.MockTransport(lambda request: httpx.Response(200, stream=body))
    file = ModelFile(url=URL, path="m/x.gguf", size=1000)
    token = StopToken()
    outcome: dict = {}

    def run() -> None:
        try:
            download_files([file], tmp_path, token, lambda *p: None, transport=transport)
        except DownloadError as exc:
            outcome["error"] = exc

    thread = threading.Thread(target=run)
    started = time.monotonic()
    thread.start()
    time.sleep(0.2)
    token.cancel()
    thread.join(5)

    assert outcome["error"].cancelled and time.monotonic() - started < 3
    assert not (tmp_path / "m/x.gguf.part").exists()


# ---------- scripts/build_rag_index.py ----------


def _script():
    path = config.repo_root() / "scripts" / "build_rag_index.py"
    spec = importlib.util.spec_from_file_location("build_rag_index_script", path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _settings(tmp_path) -> None:
    values = {"rag": rag_values(tmp_path / "script.sqlite")}
    config.settings_path().parent.mkdir(parents=True, exist_ok=True)
    config.settings_path().write_text(json.dumps(values), encoding="utf-8")


def fake_factory(model, path):  # noqa: ANN001
    return FakeEmbedder(model_id=model.id)


def test_script_builds_the_index_and_records_the_file(tmp_path, capsys):
    _settings(tmp_path)
    place_model()

    assert _script().main([], embedder_factory=fake_factory) == 0

    meta = rag_index.read_meta(tmp_path / "script.sqlite")
    assert meta.model_size == MODEL_SIZE and "Index écrit" in capsys.readouterr().out


def test_script_refuses_another_file_and_invalid_content(tmp_path, capsys, monkeypatch):
    _settings(tmp_path)
    other = tmp_path / "autre.gguf"
    other.write_bytes(b"\0" * 12)
    script = _script()

    assert script.main(["--model", str(other)], embedder_factory=fake_factory) == 2
    assert "n'est pas le modèle déclaré" in capsys.readouterr().err
    assert not (tmp_path / "script.sqlite").exists()

    def invalid():
        raise ValueError("documents manquants")

    monkeypatch.setattr(script, "load_rag_content", invalid)
    assert script.main([], embedder_factory=fake_factory) == 2
    assert "content/rag.yaml est absent ou invalide" in capsys.readouterr().err


def test_script_says_in_french_that_wavestack_uses_the_index(tmp_path, capsys, monkeypatch):
    _settings(tmp_path)
    place_model()
    target = tmp_path / "script.sqlite"
    build(target)
    before = rag_index.read_meta(target)
    refuse_replacing(monkeypatch, target)

    assert _script().main([], embedder_factory=fake_factory) == 1

    err = capsys.readouterr().err
    assert err.strip() == (
        f"{rag_index.INDEX_IN_USE_FR} Construisez-le depuis la carte RAG, ou arrêtez "
        "WaveStack, puis relancez ce script."
    )
    assert not target.with_name(target.name + ".tmp").exists()
    assert rag_index.read_meta(target) == before  # the old index, intact
