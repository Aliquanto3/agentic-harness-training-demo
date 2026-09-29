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
from wavestack.models.candidates import candidates_from_logits
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
    assert dims.get("layer_count") is None and "en-tête" in dims["source_fr"]


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
    # The workshop's projections read it: out of the screen's context.
    assert events[-1].context_id is None and events[-1].step_id is None
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
    for field, value in (("temperature", 2.5), ("top_k", -1), ("top_p", 0.01), ("min_p", 0.6)):
        bad = post({"prompt": "Bonjour", "sampling": good | {field: value}})
        assert bad.status_code == 422, field
    assert post({"prompt": "", "sampling": good}).status_code == 422
    session.state, session.reason_fr = "turn", "Un tour est en cours."
    busy = post({"prompt": "Bonjour", "sampling": good})
    assert busy.status_code == 409 and "Un tour est déjà en cours" in busy.json()["detail"]
    lab = client.get("/api/llm_lab").json()["sampling"]
    assert lab["defaults"] == {"temperature": 0.7, "top_k": 20, "top_p": 0.8, "min_p": 0.0}
    assert lab["bounds"]["top_k"] == [0, 100]  # 0: top-k off
    assert post({"prompt": "Bonjour", "sampling": good | {"top_k": 0}}).status_code == 409
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


# ---------- increment 3: the model's load and the reasoning ----------


def _load_events(mark: int) -> list:
    return [e for e in get_journal().events_since(mark) if e.kind.startswith("model_load")]


def test_a_file_load_emits_its_steps_and_its_memory(tmp_path):
    from test_model_switch import Tracker, _files, _session

    tracker = Tracker({"A": FakeEngine()})
    paths = _files(tmp_path, "A")
    rss = iter([100 * 2**20] + [300 * 2**20] * 50)
    session = _session(tracker, rss=lambda: next(rss))
    mark = get_journal().last_seq()
    assert session.boot(paths["A"]).result() == "ok"
    events = _load_events(mark)
    steps = [e.payload for e in events if e.kind == "model_load_step"]
    assert [s["step"] for s in steps] == ["release", "check", "engine", "ready"]
    assert "copie des poids en mémoire vive" in steps[2]["label_fr"]
    assert all(e.turn_id is None and e.step_id is None for e in events)
    assert [s["elapsed_ms"] for s in steps] == sorted(s["elapsed_ms"] for s in steps)
    ended = events[-1].payload
    assert ended["status"] == "ok"
    memory = ended["memory"]
    assert memory["rss_before"] == 100 * 2**20 and memory["rss_after"] == 300 * 2**20
    assert memory["where_fr"].startswith("Mémoire vive (RAM) du processeur, pas de carte graphique")
    lab = session.lab_state()
    assert [e["kind"] for e in lab["last_load"]][0] == "model_load_started"
    assert lab["last_load"][-1]["kind"] == "model_load_ended"


def test_a_served_model_and_a_cloud_model_load_steps(monkeypatch):
    server = FakeServer()
    monkeypatch.setattr(servers, "default_transport", httpx.MockTransport(server))
    mark = get_journal().last_seq()
    _booted("llama_server")
    steps = [e.payload for e in _load_events(mark) if e.kind == "model_load_step"]
    assert [s["step"] for s in steps] == ["release", "check", "engine", "ready"]
    assert steps[2]["label_fr"] == "Connexion à llama-server"
    ended = _load_events(mark)[-1].payload
    assert "dans son propre processus, en RAM de ce poste" in ended["memory"]["where_fr"]

    mark = get_journal().last_seq()
    provider = Provider(sse(delta(content="ok"), delta("stop")))
    _cloud_session("groq", provider)
    events = _load_events(mark)
    steps = [e.payload for e in events if e.kind == "model_load_step"]
    assert steps[2]["label_fr"] == "Préparation, sans chargement (modèle cloud)"
    memory = events[-1].payload["memory"]
    assert memory["cost_bytes"] == 0
    assert memory["where_fr"].startswith("Aucune mémoire sur ce poste : le modèle tourne chez Groq")


QWEN_TEMPLATE = (
    "{% for message in messages %}<|im_start|>{{ message.role }}\n{{ message.content }}"
    "<|im_end|>\n{% endfor %}{% if add_generation_prompt %}<|im_start|>assistant\n"
    "{% if enable_thinking is defined and enable_thinking is false %}<think>\n\n</think>\n\n"
    "{% else %}<think>\n{% endif %}{% endif %}"
)


def _reasoning_session(output: str, **values) -> tuple[FakeEngine, object]:
    engine = FakeEngine(output=output, template=QWEN_TEMPLATE, architecture="qwen35")
    return engine, booted_session(engine, window=8192, values=values or None)


def test_reasoning_sets_the_template_variable_and_counts_both_channels():
    engine, session = _reasoning_session("Je réfléchis.\n</think>\n\nRéponse.")
    lab = session.lab_state()["reasoning"]
    assert lab["mode"] == "toggle" and lab["reserve"] == 1536
    events = _generate(session, "Combien ?", reasoning=True)
    started = next(e.payload for e in events if e.kind == "llm_generation_started")
    assert started["rendered"].endswith("<|im_start|>assistant\n<think>\n")
    assert started["reserve"] == 1536 and started["reasoning"] is True
    tokens = [e.payload for e in events if e.kind == "llm_token"]
    thinking = "".join(t["text"] for t in tokens if t["channel"] == "reasoning")
    assert thinking.startswith("Je réfléchis.")
    ended = next(e.payload for e in events if e.kind == "llm_generation_ended")
    assert ended["reasoning_tokens"] > 0 and ended["answer_tokens"] > 0
    assert ended["reasoning_tokens"] + ended["answer_tokens"] == len(tokens)

    off = _generate(session, "Combien ?")
    started = next(e.payload for e in off if e.kind == "llm_generation_started")
    assert started["rendered"].endswith("<think>\n\n</think>\n\n") and started["reserve"] == 512


def test_a_long_reasoning_is_cut_in_the_screen_context():
    engine, session = _reasoning_session("x" * 900, reasoning={"budget_tokens": 200})
    events = _generate(session, "Combien ?", reasoning=True)
    cuts = [e for e in events if e.kind == "reasoning_cut"]
    assert len(cuts) == 1 and cuts[0].context_id == "llm"


def test_reasoning_refused_without_it_and_forced_when_always():
    session = booted_session(FakeEngine())  # CHATML: no reasoning variable
    assert session.lab_state()["reasoning"]["mode"] == "never"
    with pytest.raises(SendRefused) as refused:
        session.llm_generate("Bonjour", SCREEN, reasoning=True)
    assert "raisonn" in refused.value.reason_fr
    assert session.state == "idle"

    provider = Provider(sse(delta(reasoning="Hmm."), delta(content="Oui."), delta("stop")))
    cloud = _cloud_session("groq", provider)  # gpt-oss always reasons
    assert cloud.lab_state()["reasoning"]["mode"] == "always"
    events = _generate(cloud, "Bonjour")
    started = next(e.payload for e in events if e.kind == "llm_generation_started")
    assert started["reasoning"] is True and started["reserve"] == 1536
    body = json.loads(provider.requests[-1].content)
    assert body["reasoning_effort"] == "low"


# ---------- increment 4: the candidates' probabilities ----------


def _softmax(values: list[float]) -> list[float]:
    import math

    top = max(values)
    weights = [math.exp(v - top) for v in values]
    return [w / sum(weights) for w in weights]


LOGITS = [4.0, 3.0, 2.0, 1.0, 0.5, 0.0, -1.0, -2.0]


def _by_id(rows: list[dict]) -> dict[int, dict]:
    return {r["token_id"]: r for r in rows}


def test_candidates_at_temperature_one_keep_all():
    rows = candidates_from_logits(LOGITS, Sampling(1.0, 100, 1.0, 0.0), chosen_id=1)
    p = _softmax(LOGITS)
    assert [r["token_id"] for r in rows] == [0, 1, 2, 3, 4]
    assert [round(r["p"], 6) for r in rows] == [round(x, 6) for x in p[:5]]
    assert all(r["kept"] for r in rows)
    assert [round(r["p_sampled"], 6) for r in rows] == [round(x, 6) for x in p[:5]]
    assert [r["chosen"] for r in rows] == [False, True, False, False, False]
    assert sum(r["p"] for r in rows) <= 1


def test_candidates_temperature_changes_the_chance_not_the_probability():
    rows = candidates_from_logits(LOGITS, Sampling(0.5, 100, 1.0, 0.0), chosen_id=0)
    sharp = _softmax([v / 0.5 for v in LOGITS])
    assert round(rows[0]["p"], 6) == round(_softmax(LOGITS)[0], 6)
    assert round(rows[0]["p_sampled"], 6) == round(sharp[0], 6)


def test_candidates_greedy_top_k_top_p_min_p():
    greedy = _by_id(candidates_from_logits(LOGITS, Sampling(0.0, 100, 1.0, 0.0), chosen_id=0))
    assert greedy[0]["p_sampled"] == 1.0 and greedy[1]["p_sampled"] == 0.0

    top_k = _by_id(candidates_from_logits(LOGITS, Sampling(1.0, 2, 1.0, 0.0), chosen_id=0))
    assert [top_k[t]["kept"] for t in range(5)] == [True, True, False, False, False]
    assert round(top_k[0]["p_sampled"] + top_k[1]["p_sampled"], 6) == 1.0

    # top-p 0.8: the renormalized cumulated sum reaches it at the second token (0.62 + 0.23).
    top_p = _by_id(candidates_from_logits(LOGITS, Sampling(1.0, 100, 0.8, 0.0), chosen_id=0))
    assert [top_p[t]["kept"] for t in range(4)] == [True, True, False, False]

    # min-p 0.3: kept when p >= 0.3 × p_max, i.e. logit >= 4 + ln 0.3 ≈ 2.8.
    min_p = _by_id(candidates_from_logits(LOGITS, Sampling(1.0, 100, 1.0, 0.3), chosen_id=0))
    assert [min_p[t]["kept"] for t in range(3)] == [True, True, False]


def test_the_token_drawn_outside_the_five_is_added_and_marked():
    rows = candidates_from_logits(LOGITS, Sampling(1.0, 100, 1.0, 0.0), chosen_id=6)
    assert len(rows) == 6 and rows[-1]["token_id"] == 6 and rows[-1]["chosen"]
    assert rows[-1]["kept"] and rows[-1]["p_sampled"] > 0


def test_candidates_reach_llm_token_with_their_text():
    script = [
        [{"token_id": 83, "p": 0.6, "kept": True, "p_sampled": 0.8, "chosen": True}],
        [{"token_id": 97, "p": 0.3, "kept": True, "p_sampled": 0.2, "chosen": True}],
    ]
    engine = FakeEngine(output="Sa", candidates_script=script)
    session = booted_session(engine)
    assert session.lab_state()["candidates"] == {"available": True, "reason_fr": None, "n": 5}
    events = _generate(session, candidates=True)
    tokens = [e.payload for e in events if e.kind == "llm_token"]
    assert tokens[0]["candidates"] == [
        {"token_id": 83, "text": "S", "p": 0.6, "kept": True, "p_sampled": 0.8, "chosen": True}
    ]
    assert engine.candidates == [5]
    plain = _generate(session)  # unchecked: nothing asked, nothing carried
    assert all(e.payload.get("candidates") is None for e in plain if e.kind == "llm_token")
    assert engine.candidates == [5]


def test_candidates_unavailable_on_servers_and_the_cloud(monkeypatch):
    server = FakeServer()
    monkeypatch.setattr(servers, "default_transport", httpx.MockTransport(server))
    session = _booted("llama_server")
    lab = session.lab_state()["candidates"]
    assert lab["available"] is False and "llama-server" in lab["reason_fr"]
    with pytest.raises(SendRefused):
        session.llm_generate("Bonjour", SCREEN, candidates=True)
    assert session.state == "idle"
    ollama = _booted("ollama").lab_state()["candidates"]
    assert ollama["available"] is False and "Ollama" in ollama["reason_fr"]
    provider = Provider(sse(delta(content="ok"), delta("stop")))
    cloud = _cloud_session("groq", provider).lab_state()["candidates"]
    assert cloud["available"] is False and "Groq" in cloud["reason_fr"]


@pytest.mark.model
def test_real_engine_candidates(tmp_path):
    import os

    path = os.environ.get("WAVESTACK_TEST_GGUF")
    if not path:
        pytest.skip("WAVESTACK_TEST_GGUF not set to a real GGUF file")
    from wavestack.models.engine import CancelToken, LlamaCppEngine

    engine = LlamaCppEngine(path, n_ctx=512)
    try:
        ids = engine.tokenize("La capitale de la France est")
        fragments = list(engine.complete(ids, (), 4, CancelToken(), sampling=SCREEN, candidates=5))
        rows = [f.candidates for f in fragments if f.candidates]
        assert rows
        for candidates in rows:
            assert sum(c["p"] for c in candidates[:5]) <= 1.0 + 1e-6
            chosen = [c for c in candidates if c["chosen"]]
            assert len(chosen) == 1 and chosen[0]["kept"]
    finally:
        engine.close()


# ---------- review fixes ----------


def test_large_counts_take_their_unit_from_the_rounded_value():
    assert llm_lab.fr_count(999_600_000) == "1 milliard"
    assert llm_lab.fr_count(1_999_000_000) == "2 milliards"
    assert llm_lab.fr_count(311_000_000) == "311 millions"


def test_the_screen_is_refused_like_a_turn_when_idle_carries_a_reason():
    session = booted_session(FakeEngine())
    session.reason_fr = "Envoi indisponible : le modèle n'a pas pu être chargé."
    for ask in (lambda: session.llm_tokenize("abc"), lambda: session.llm_generate("a", SCREEN)):
        with pytest.raises(SendRefused):
            ask()
    assert session.reason_fr.startswith("Envoi indisponible")  # never wiped


def test_the_final_fragment_of_held_text_is_no_chip_and_lanes_have_decoded_text():
    engine = FakeEngine(output="Oui 🙂")
    session = booted_session(engine)
    events = _generate(session)
    tokens = [e.payload for e in events if e.kind == "llm_token"]
    assert len(tokens) == len("Oui 🙂")
    assert "".join(p["text"] for t in tokens for p in t["parts"]) == "Oui 🙂"


def test_the_content_is_read_again_once_the_file_changed(monkeypatch, tmp_path):
    content = tmp_path / "content"
    shutil.copytree(config.content_dir(), content)
    monkeypatch.setattr(config, "content_dir", lambda: content)
    llm_lab.load_lab_content.cache_clear()
    try:
        assert llm_lab.load_lab_content().title_fr == "LLM nu : l'intérieur du modèle"
        path = content / "llm_lab.yaml"
        path.write_text(path.read_text("utf-8").replace("l'intérieur", "le dedans"), "utf-8")
        import os

        stat = path.stat()
        os.utime(path, ns=(stat.st_atime_ns, stat.st_mtime_ns + 10**9))
        assert llm_lab.load_lab_content().title_fr == "LLM nu : le dedans du modèle"
        path.write_text("", "utf-8")
        os.utime(path, ns=(stat.st_atime_ns, stat.st_mtime_ns + 2 * 10**9))
        session = booted_session(FakeEngine())
        body = _web(session).get("/api/llm_lab")
        assert body.status_code == 200 and body.json()["content_error_fr"]  # no IndexError
    finally:
        llm_lab.load_lab_content.cache_clear()


def test_sampling_intention_bounds_are_the_engine_bounds():
    from wavestack.models.engine import SAMPLING_BOUNDS
    from wavestack.web.app import SamplingIntention

    schema = SamplingIntention.model_json_schema()["properties"]
    for name, (low, high) in SAMPLING_BOUNDS.items():
        assert (schema[name]["minimum"], schema[name]["maximum"]) == (low, high)
