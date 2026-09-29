"""Story 29: the « LLM nu » screen (context `llm`, no turn), one test per row of the I/O matrix
where it can run without a real model: `FakeEngine`, the servers' simulated transport, a
synthetic GGUF header, a scripted cloud provider."""

from __future__ import annotations

import shutil

import httpx
import pytest
from fake_engine import FakeEngine, booted_session
from gguf_writer import write_gguf
from starlette.testclient import TestClient
from test_cloud import Provider, _cloud_session, delta, sse
from test_model_servers import GIB, LLAMA_URL, FakeServer, _booted

from wavestack import config
from wavestack.models import gguf_meta, servers
from wavestack.models.engine import EngineMetadata
from wavestack.session import llm_lab
from wavestack.session.app_session import SendRefused
from wavestack.session.diagnostic import DiagnosticSession
from wavestack.trace.journal import get_journal
from wavestack.web.app import create_app

ORIGIN = {"Origin": "http://127.0.0.1:8420"}
TEXT = "Bonjour <|im_end|> 🙂"


def _lab(session, run) -> list:
    """The events of the screen's context emitted while `run` ran, the worker joined."""
    mark = get_journal().last_seq()
    run()
    session.join()
    return [e for e in get_journal().events_since(mark) if e.context_id == "llm"]


def _tokenized(session, text: str = TEXT) -> dict:
    events = _lab(session, lambda: session.llm_tokenize(text))
    found = [e for e in events if e.kind == "llm_tokenized"]
    assert len(found) == 1, [(e.kind, e.payload) for e in events]
    envelope = found[0]
    assert envelope.turn_id is None and envelope.step_id == envelope.payload["request_id"]
    return envelope.payload


# ---------- pure functions ----------


def test_token_rows_mark_the_specials_cap_at_512_and_show_partial_bytes():
    ids = list(range(600))
    pieces = [b"<|im_end|>", "é".encode()[:1], b" a"] + [b"x"] * 597
    rows, more = llm_lab.token_rows(ids, pieces, ("<|im_end|>",))
    assert len(rows) == 512 and more == 88
    assert rows[0] == {"id": 0, "text": "<|im_end|>", "special": True}
    assert rows[1]["text"] == "⟨C3⟩" and not rows[1]["special"]  # half a character
    assert rows[2] == {"id": 2, "text": " a", "special": False}
    assert llm_lab.token_rows([1, 2], [b"a", b"b"], ())[1] == 0


def test_dimensions_from_a_synthetic_gguf_header(tmp_path):
    path = write_gguf(
        tmp_path / "qwen.gguf",
        {
            "general.architecture": "qwen35",
            "qwen35.embedding_length": 2048,
            "qwen35.block_count": 24,
            "qwen35.attention.head_count": [16, 16, 8, 16],  # one value per layer
        },
    )
    dims = gguf_meta.dimensions_from_header(gguf_meta.read_metadata(path))
    assert dims == {
        "embedding_length": 2048,
        "layer_count": 24,
        "head_count": 16,
        "context_length": None,  # absent: unknown
    }
    payload = llm_lab.dimensions_payload(dims | {"vocab_size": 151936}, "Lues dans l'en-tête.")
    assert payload["embedding_params"] == 151936 * 2048
    assert payload["figures_fr"]["embedding_length"] == "2 048"
    assert payload["figures_fr"]["context_length"] is None
    assert payload["source_fr"] == "Lues dans l'en-tête. Inconnus : le contexte natif."
    assert payload["figures_fr"]["embedding_params"] == "311 millions"
    assert "2 048 nombres" in llm_lab.dimensions_fr(payload)
    assert llm_lab.dimensions_from_header(None)["embedding_length"] is None


def test_the_content_file_is_valid():
    content = llm_lab.load_lab_content()
    assert content.title_fr == "LLM nu : l'intérieur du modèle"
    sections = content.sections.model_dump()
    assert list(sections) == [
        "tokenization",
        "sampling",
        "loading",
        "reading",
        "generation",
        "reasoning",
    ]


# ---------- tokenization in the session ----------


class SpecialEngine(FakeEngine):
    """One token per byte, `<|im_end|>` one special token (id 1002), and its sizes."""

    def tokenize(self, text: str) -> list[int]:
        ids: list[int] = []
        for i, part in enumerate(text.split("<|im_end|>")):
            if i:
                ids.append(1002)
            ids += list(part.encode("utf-8"))
        return ids

    def token_pieces(self, ids) -> list[bytes]:  # noqa: ANN001
        return [b"<|im_end|>" if i == 1002 else bytes([i]) for i in ids]

    def dimensions(self) -> dict:
        return {
            "vocab_size": 1004,
            "embedding_length": 2048,
            "layer_count": 24,
            "head_count": 16,
            "context_length": 32768,
            "source_fr": "Lues dans le faux moteur.",
        }


def test_local_tokenization_is_exact_with_the_special_token_and_the_sizes():
    session = booted_session(SpecialEngine())
    payload = _tokenized(session)
    utf8 = TEXT.replace("<|im_end|>", "").encode("utf-8")
    assert payload["exact"] and payload["hosting"] == "local"
    assert payload["token_count"] == len(utf8) + 1 == len(payload["tokens"])
    assert payload["char_count"] == len(TEXT)
    special = [t for t in payload["tokens"] if t["special"]]
    assert special == [{"id": 1002, "text": "<|im_end|>", "special": True}]
    assert payload["tokens"][0] == {"id": ord("B"), "text": "B", "special": False}
    assert payload["tokens"][-1]["text"] == "⟨82⟩"  # the emoji's last byte, alone
    assert payload["figures_fr"]["token_count"] == str(payload["token_count"])
    dims = payload["dimensions"]
    assert dims["figures_fr"]["embedding_length"] == "2 048"
    assert dims["figures_fr"]["vocab_size"] == "1 004"
    assert dims["embedding_params"] == 1004 * 2048
    assert payload["unavailable_fr"] is None and payload["estimate"] is None
    assert session.state == "idle"


def test_an_engine_without_dimensions_says_they_are_unknown():
    session = booted_session(FakeEngine())
    payload = _tokenized(session, "abc")
    assert payload["exact"] and [t["text"] for t in payload["tokens"]] == ["a", "b", "c"]
    dims = payload["dimensions"]
    assert dims["embedding_length"] is None and dims["vocab_size"] is None
    assert dims["source_fr"].startswith("Ce moteur ne dit pas les dimensions")
    assert payload["dimensions_fr"].startswith("Dimension d'embedding inconnue")


def test_long_text_shows_512_chips_and_the_rest():
    session = booted_session(FakeEngine())
    payload = _tokenized(session, "a" * 2000)
    assert payload["token_count"] == 2000 and len(payload["tokens"]) == 512
    assert payload["more"] == 1488 and payload["figures_fr"]["more"] == "1 488"


def test_cloud_tokenizer_is_at_the_provider_with_the_estimate():
    provider = Provider(sse(delta(content="ok"), delta("stop")))
    session = _cloud_session("groq", provider)
    payload = _tokenized(session, "Bonjour tout le monde")
    assert payload["exact"] is False and payload["tokens"] == []
    assert payload["hosting"] == "network"
    assert payload["estimate"] == config.estimate_tokens(
        "Bonjour tout le monde", session.cfg.chars_per_token
    )
    assert "chez Groq" in payload["unavailable_fr"]
    assert payload["dimensions"] is None and "Groq" in payload["dimensions_fr"]
    assert not provider.requests  # nothing left the workstation to cut the text


def test_tokenization_is_refused_outside_idle():
    session = booted_session(FakeEngine())
    session.state, session.reason_fr = "turn", "Un tour est en cours."
    with pytest.raises(SendRefused):
        session.llm_tokenize("abc")


# ---------- the servers' sizes ----------


class SizedServer(FakeServer):
    """The real llama-server gives `n_vocab` and `n_embd` in `/v1/models`."""

    def _llama(self, path: str, body: dict) -> httpx.Response:
        if path == "/v1/models":
            meta = {"n_ctx_train": 32768, "size": 2 * GIB, "n_vocab": 1004, "n_embd": 2048}
            return httpx.Response(200, json={"data": [{"id": "qwen", "meta": meta}]})
        return super()._llama(path, body)


def test_llama_server_sizes_and_special_token(monkeypatch):
    server = SizedServer()
    monkeypatch.setattr(servers, "default_transport", httpx.MockTransport(server))
    session = _booted("llama_server")
    payload = _tokenized(session)
    assert [t["id"] for t in payload["tokens"] if t["special"]] == [1002]
    dims = payload["dimensions"]
    assert (dims["vocab_size"], dims["embedding_length"]) == (1004, 2048)
    assert dims["layer_count"] is None  # the server's file is not on this disk
    assert "llama-server (/v1/models)" in dims["source_fr"]
    assert "llama-server (/tokenize)" in payload["tokenizer_fr"]
    assert not server.posts("/completion")


def test_ollama_sizes_from_the_blob_header(monkeypatch, tmp_path):
    blob = write_gguf(
        tmp_path / "blob",
        {"general.architecture": "qwen35", "qwen35.embedding_length": 1024},
    )

    class Tokenizer:
        def tokenize(self, text):  # noqa: ANN001, ANN202
            return list(text.encode())

        def token_pieces(self, ids):  # noqa: ANN001, ANN202
            return [bytes([i]) for i in ids]

        def metadata(self):  # noqa: ANN202
            return EngineMetadata("qwen35", "x", None, "", "", ())

        def vocab_size(self):  # noqa: ANN202
            return 151936

        def close(self):  # noqa: ANN202
            pass

    engine = servers.OllamaRawEngine(
        "http://127.0.0.1:11434", "m", str(blob), 4096, tokenizer=Tokenizer()
    )
    dims = engine.dimensions()
    assert dims["vocab_size"] == 151936 and dims["embedding_length"] == 1024
    assert dims["layer_count"] is None and "en-tête" in dims["source_fr"]


def test_llama_server_dimensions_read_its_file_header_when_local(tmp_path, monkeypatch):
    server = SizedServer()
    header = write_gguf(
        tmp_path / "model.gguf",
        {"general.architecture": "qwen35", "qwen35.block_count": 24},
    )
    server.model_path = str(header)
    monkeypatch.setattr(servers, "default_transport", httpx.MockTransport(server))
    engine = servers.LlamaServerEngine(LLAMA_URL)
    dims = engine.dimensions()
    assert dims["layer_count"] == 24 and dims["vocab_size"] == 1004
    assert "en-tête GGUF" in dims["source_fr"]


# ---------- the web routes ----------


def _web(session) -> TestClient:
    diagnostic = DiagnosticSession(session.cfg, port=8420)
    app = create_app(diagnostic, port=8420, version="test", app_session=session)
    return TestClient(app, base_url="http://127.0.0.1:8420")


def test_routes_answer_refuse_and_validate():
    session = booted_session(SpecialEngine())
    client = _web(session)
    for path in ("/llm", "/static/llm.js", "/static/llm.css"):
        assert client.get(path).status_code == 200, path
    lab = client.get("/api/llm_lab").json()
    assert lab["content"]["title_fr"] == "LLM nu : l'intérieur du modèle"
    assert lab["content_error_fr"] is None and lab["tokenizer"]["exact"] is True
    assert lab["session_state"]["state"] == "idle" and lab["active_model"]["hosting"] == "local"
    assert lab["seq"] <= get_journal().last_seq()

    post = lambda body: client.post(  # noqa: E731
        "/api/intentions/llm_tokenize", json=body, headers=ORIGIN
    )
    answer = post({"text": "abc"})
    assert answer.status_code == 200 and answer.json()["request_id"].startswith("llm")
    session.join()
    assert post({"text": ""}).status_code == 422
    assert post({"text": "a" * 2001}).status_code == 422
    session.state, session.reason_fr = "turn", "Un tour est en cours."
    busy = post({"text": "abc"})
    assert busy.status_code == 409 and busy.json()["detail"].startswith("Refusé pour l'instant")


def test_invalid_content_is_traced_and_the_page_stays_served(monkeypatch, tmp_path):
    content = tmp_path / "content"
    shutil.copytree(config.content_dir(), content)
    (content / "llm_lab.yaml").write_text("title_fr: 3\n", encoding="utf-8")
    monkeypatch.setattr(config, "content_dir", lambda: content)
    llm_lab.load_lab_content.cache_clear()
    try:
        session = booted_session(FakeEngine())
        mark = get_journal().last_seq()
        response = _web(session).get("/api/llm_lab")
        assert response.status_code == 200
        body = response.json()
        assert body["content"] is None and "llm_lab.yaml" in body["content_error_fr"]
        errors = [e for e in get_journal().events_since(mark) if e.kind == "harness_error"]
        assert len(errors) == 1 and errors[0].context_id == "llm"
        assert _web(session).get("/llm").status_code == 200
    finally:
        llm_lab.load_lab_content.cache_clear()
