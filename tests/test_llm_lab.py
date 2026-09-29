"""Story 29: the « LLM nu » screen (context `llm`, no turn), one test per row of the I/O matrix
where it can run without a real model: `FakeEngine`, the servers' simulated transport, a
synthetic GGUF header, a scripted cloud provider."""

from __future__ import annotations

import json
import shutil
import threading

import httpx
import pytest
from fake_engine import FakeEngine, booted_session
from gguf_writer import write_gguf
from starlette.testclient import TestClient
from test_cloud import Provider, _cloud_session, delta, sse
from test_model_servers import GIB, LLAMA_URL, FakeServer, _booted

from wavestack import config
from wavestack.cloud import chat_fields
from wavestack.models import gguf_meta, servers
from wavestack.models.engine import EngineMetadata, Sampling
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


# ---------- increment 2: sampling, prompt reading, token by token ----------

SCREEN = Sampling(temperature=0.2, top_k=5, top_p=0.9, min_p=0.05)


def _generate(session, prompt: str = "Bonjour", sampling=SCREEN, **kwargs) -> list:
    """Every event emitted while the screen generated, the worker joined (all contexts)."""
    mark = get_journal().last_seq()
    session.llm_generate(prompt, sampling, **kwargs)
    session.join()
    return get_journal().events_since(mark)


def test_screen_generation_events_and_sampling_sent_to_the_engine():
    engine = FakeEngine(output="Salut !", delay=0.005)
    session = booted_session(engine)
    history = list(session._history)
    events = _generate(session)
    assert engine.samplings == [SCREEN]
    kinds = [e.kind for e in events if e.kind != "model_delta"]
    assert kinds[0] == "session_state" and events[0].payload["state"] == "llm_lab"
    assert kinds[1:4] == ["llm_generation_started", "model_call_started", "model_first_token"]
    tokens = [e for e in events if e.kind == "llm_token"]
    assert [t.payload["text"] for t in tokens] == list("Salut !")
    assert [t.payload["index"] for t in tokens] == list(range(7))
    assert kinds[-3:] == ["model_call_ended", "llm_generation_ended", "session_state"]
    assert events[-1].payload["state"] == "idle" and session.state == "idle"
    lab = [e for e in events if e.kind != "session_state"]
    assert all(e.context_id == "llm" and e.turn_id is None for e in lab)
    assert all(e.step_id == e.call_id == "llm1" for e in lab if e.kind != "session_state")
    assert not [e for e in events if e.kind.startswith("context_")]
    started = next(e.payload for e in events if e.kind == "llm_generation_started")
    assert started["rendered"] == "<|im_start|>user\nBonjour<|im_end|>\n<|im_start|>assistant\n"
    assert started["prompt_tokens"] == len(started["rendered"].encode()) and started["exact"]
    assert started["reserve"] == 512 and started["reasoning"] is False
    call = next(e.payload for e in events if e.kind == "model_call_started")
    assert call["sampling"] == {
        "temperature": 0.2,
        "top_k": 5,
        "top_p": 0.9,
        "min_p": 0.05,
        "source": "screen",
        "note_fr": None,
    }
    ended = next(e.payload for e in events if e.kind == "llm_generation_ended")
    assert ended["status"] == "completed" and ended["answer_tokens"] == 7
    assert ended["reasoning_tokens"] == 0 and ended["read_tps"] is not None
    assert session._history == history  # the workshop's conversation got nothing


def test_the_workshop_turn_after_the_screen_is_rendered_as_without_it():
    alone = booted_session(FakeEngine())
    alone.send("Bonjour")
    alone.join()
    mark = get_journal().last_seq()
    alone.send("Et ensuite ?")
    alone.join()
    alone_events = get_journal().events_since(mark)
    expected = [e.payload for e in alone_events if e.kind == "context_rendered"]
    alone_causes = [e.payload["cause"] for e in alone_events if e.kind == "prefix_not_reused"]

    engine = FakeEngine()
    session = booted_session(engine)
    session.send("Bonjour")
    session.join()
    _generate(session, "Une question de l'écran")
    mark = get_journal().last_seq()
    session.send("Et ensuite ?")
    session.join()
    events = get_journal().events_since(mark)
    rendered = [e.payload for e in events if e.kind == "context_rendered"]
    strip = lambda p: [(s["kind"], s["text"]) for s in p["segments"]]  # noqa: E731
    assert [strip(p) for p in rendered] == [strip(p) for p in expected]
    assert engine.restores == 1  # the main context's state came back
    causes = [e.payload["cause"] for e in events if e.kind == "prefix_not_reused"]
    assert causes == alone_causes and "llm" not in causes  # the same reading as without it
    call = next(e.payload for e in events if e.kind == "model_call_started")
    assert call["sampling"]["source"] == "harness"  # the workshop's own defaults, traced
    assert (call["sampling"]["temperature"], call["sampling"]["top_k"]) == (0.7, 20)
    assert engine.samplings == [SCREEN]  # the workshop's call passed no sampling


def test_a_stateless_engine_says_the_screen_took_its_cache():
    session = booted_session(FakeEngine(stateful=False))
    session.send("Bonjour")
    session.join()
    _generate(session)
    mark = get_journal().last_seq()
    session.send("Et ensuite ?")
    session.join()
    causes = [e.payload for e in get_journal().events_since(mark) if e.kind == "prefix_not_reused"]
    assert [c["cause"] for c in causes] == ["llm"]
    assert causes[0]["message_fr"].startswith("L'écran « LLM nu » a occupé le cache du moteur")


def test_stop_ends_the_screen_generation_cancelled():
    gate = threading.Event()
    engine = FakeEngine(output="x" * 200, delay=0.01, gate=gate)
    session = booted_session(engine)
    mark = get_journal().last_seq()
    session.llm_generate("Bonjour", SCREEN)
    assert session.state == "llm_lab"
    with pytest.raises(SendRefused):
        session.send("Pendant l'écran")
    assert session.stop() is True
    gate.set()
    session.join()
    ended = [
        e.payload for e in get_journal().events_since(mark) if e.kind == "llm_generation_ended"
    ]
    assert ended[0]["status"] == "cancelled" and session.state == "idle"


def test_screen_refused_outside_idle_and_bounds_validated():
    session = booted_session(FakeEngine())
    client = _web(session)
    post = lambda body: client.post(  # noqa: E731
        "/api/intentions/llm_generate", json=body, headers=ORIGIN
    )
    good = {"temperature": 0.2, "top_k": 5, "top_p": 0.9, "min_p": 0.05}
    answer = post({"prompt": "Bonjour", "sampling": good})
    assert answer.status_code == 200 and answer.json()["request_id"].startswith("llm")
    session.join()
    for field, value in (("temperature", 2.5), ("top_k", 0), ("top_p", 0.01), ("min_p", 0.6)):
        bad = post({"prompt": "Bonjour", "sampling": good | {field: value}})
        assert bad.status_code == 422, field
    assert post({"prompt": "", "sampling": good}).status_code == 422
    session.state, session.reason_fr = "turn", "Un tour est en cours."
    busy = post({"prompt": "Bonjour", "sampling": good})
    assert busy.status_code == 409 and "Un tour est déjà en cours" in busy.json()["detail"]
    lab = client.get("/api/llm_lab").json()["sampling"]
    assert lab["defaults"] == {"temperature": 0.7, "top_k": 20, "top_p": 0.8, "min_p": 0.0}
    assert lab["bounds"]["top_k"] == [1, 100]
    assert set(lab["supported"].values()) == {None}  # a local model takes all four


def test_llama_server_and_ollama_receive_the_screen_sampling(monkeypatch):
    server = FakeServer(outputs=["Salut"])
    monkeypatch.setattr(servers, "default_transport", httpx.MockTransport(server))
    session = _booted("llama_server")
    events = _generate(session)
    body = server.posts("/completion")[-1]
    assert (body["temperature"], body["top_k"], body["top_p"], body["min_p"]) == (
        0.2,
        5,
        0.9,
        0.05,
    )
    tokens = [e.payload["text"] for e in events if e.kind == "llm_token"]
    assert "".join(tokens) == "Salut"
    # The workshop's request is unchanged: the engine's defaults.
    session.send("Bonjour")
    session.join()
    body = server.posts("/completion")[-1]
    assert (body["temperature"], body["top_k"], body["top_p"], body["min_p"]) == (
        0.7,
        20,
        0.8,
        0.0,
    )

    session = _booted("ollama")
    _generate(session)
    options = server.posts("/api/generate")[-1]["options"]
    assert (options["temperature"], options["top_k"], options["top_p"], options["min_p"]) == (
        0.2,
        5,
        0.9,
        0.05,
    )


def test_chat_fields_send_the_declared_sampling_only():
    cfg = config.load_config()
    groq = cfg.cloud_model("groq")
    assert groq.sampling == ["temperature", "top_p"]
    fields = chat_fields(groq, 512, sampling=SCREEN)
    assert list(fields)[:4] == ["model", "stream", "max_tokens", "temperature"]
    assert fields["temperature"] == 0.2 and fields["top_p"] == 0.9
    assert "top_k" not in fields and "min_p" not in fields
    assert "temperature" not in chat_fields(groq, 512)  # the workshop's body: unchanged
    bare = groq.model_copy(update={"sampling": []})
    assert "temperature" not in chat_fields(bare, 512, sampling=SCREEN)


def test_cloud_screen_generation_traces_what_the_provider_takes():
    provider = Provider(sse(delta(content="Sa"), delta(content="lut"), delta("stop")))
    session = _cloud_session("groq", provider)
    events = _generate(session)
    body = json.loads(provider.requests[-1].content)
    assert body["temperature"] == 0.2 and body["top_p"] == 0.9 and "top_k" not in body
    assert body["messages"] == [{"role": "user", "content": "Bonjour"}]
    call = next(e.payload for e in events if e.kind == "model_call_started")
    assert call["sampling"]["source"] == "screen"
    assert call["sampling"]["top_k"] is None and call["sampling"]["min_p"] is None
    assert "non réglables chez Groq" in call["sampling"]["note_fr"]
    fragments = [e.payload for e in events if e.kind == "llm_token"]
    assert [f["text"] for f in fragments] == ["Sa", "lut"]
    assert all(f["token_id"] is None for f in fragments)
    assert not [e for e in events if e.kind == "context_reconciled"]
    lab = session.lab_state()["sampling"]
    assert lab["supported"]["temperature"] is None
    assert "non réglable chez Groq" in lab["supported"]["top_k"]

    # The workshop's cloud call: no sampling sent, traced as the provider's.
    mark = get_journal().last_seq()
    session.send("Bonjour")
    session.join()
    body = json.loads(provider.requests[-1].content)
    assert "temperature" not in body
    call = next(
        e.payload for e in get_journal().events_since(mark) if e.kind == "model_call_started"
    )
    assert call["sampling"]["source"] == "provider" and call["sampling"]["temperature"] is None


def test_cloud_without_declaration_sends_no_sampling(monkeypatch):
    provider = Provider(sse(delta(content="ok"), delta("stop")))
    session = _cloud_session("groq", provider)
    monkeypatch.setattr(session, "_cloud", session._cloud.model_copy(update={"sampling": []}))
    events = _generate(session)
    body = json.loads(provider.requests[-1].content)
    assert not {"temperature", "top_p", "top_k", "min_p"} & set(body)
    call = next(e.payload for e in events if e.kind == "model_call_started")
    assert call["sampling"]["source"] == "provider"

