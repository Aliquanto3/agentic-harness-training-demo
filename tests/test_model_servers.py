"""Story 18: an already-running local server, Ollama (`ollama_raw`) or llama-server
(`llama_server`), one test per row of the I/O matrix (FR-34, AD-5, AD-7, AD-8, AD-9, AD-12).

Both servers are simulated by `httpx.MockTransport`; the Ollama model's tokenizer is a
byte-level double of the GGUF opened `vocab_only`. No network, no GGUF, no server launched.
"""

from __future__ import annotations

import json
import threading
import time
from collections.abc import Iterator
from pathlib import Path

import httpx
import pytest
from fake_engine import FakeEngine
from starlette.testclient import TestClient

from wavestack import config
from wavestack.models import discovery, servers
from wavestack.models.capabilities import capabilities_for
from wavestack.models.engine import CancelToken, EngineMetadata, LlamaCppEngine, VocabTokenizer
from wavestack.models.load_registry import ModelChoice
from wavestack.net.factory import create_loopback_client
from wavestack.net.guard import NetworkBlocked
from wavestack.session.app_session import AppSession, SendRefused
from wavestack.session.diagnostic import DiagnosticSession
from wavestack.trace.journal import get_journal
from wavestack.web.app import create_app

QWEN = (Path(__file__).parent / "fixtures" / "qwen3_5_chat_template.jinja").read_text("utf-8")
ORIGIN = {"Origin": "http://127.0.0.1:8420"}
LLAMA_URL, OLLAMA_URL = "http://127.0.0.1:8080", "http://127.0.0.1:11434"
OLLAMA_NAME = "qwen3.5:2b"
GIB = 1024**3


def call(name: str) -> str:
    """A tool call in the `qwen3_coder` format, as Qwen3.5 writes it."""
    return f"<tool_call>\n<function={name}>\n</function>\n</tool_call>"


# ---------- a byte-level tokenizer, shared by both fake servers ----------

SPECIAL = {"<|im_start|>": 1001, "<|im_end|>": 1002, "<tool_call>": 1003, "</tool_call>": 1004}
PIECE = {v: k.encode() for k, v in SPECIAL.items()}


def tokenize(text: str) -> list[int]:
    ids, i = [], 0
    while i < len(text):
        special = next((s for s in SPECIAL if text.startswith(s, i)), None)
        if special:
            ids.append(SPECIAL[special])
            i += len(special)
        else:
            ids += list(text[i].encode("utf-8"))
            i += 1
    return ids


def piece(token: int) -> bytes:
    return PIECE.get(token, bytes([token]) if token < 256 else b"")


class ByteTokenizer:
    """The double of `VocabTokenizer` (the Ollama model's GGUF, `vocab_only`)."""

    closed = False

    def tokenize(self, text: str) -> list[int]:
        return tokenize(text)

    def token_pieces(self, ids) -> list[bytes]:  # noqa: ANN001
        return [piece(t) for t in ids]

    def metadata(self) -> EngineMetadata:
        return EngineMetadata("qwen35", QWEN, 32768, "", "<|im_end|>", tuple(SPECIAL))

    def close(self) -> None:
        self.closed = True


class Lines(httpx.SyncByteStream):
    """A streamed body, one line per chunk; `closed` once the client let it go."""

    def __init__(self, lines: list[str], on_line=None) -> None:  # noqa: ANN001
        self.lines, self.on_line, self.closed = lines, on_line, False

    def __iter__(self) -> Iterator[bytes]:
        for n, line in enumerate(self.lines):
            if self.on_line:
                self.on_line(n)
            yield (line + "\n").encode("utf-8")

    def close(self) -> None:
        self.closed = True


class FakeServer:
    """Both servers at once, on their default ports: llama-server serves one model and
    Ollama one (or none). `outputs`: the scripted completions, the last one repeated."""

    def __init__(
        self,
        outputs: list[str] | None = None,
        *,
        llama: bool = True,
        ollama: bool = True,
        n_ctx: int = 4096,
        stop_type: str = "eos",
        done_reason: str = "stop",
        extra_prompt_tokens: int = 0,
        thinking: str = "",
        ps_size: int | None = None,
    ) -> None:
        self.outputs = outputs or ["Bonjour !"]
        self.llama, self.ollama = llama, ollama
        self.n_ctx, self.stop_type, self.done_reason = n_ctx, stop_type, done_reason
        self.extra_prompt_tokens, self.thinking, self.ps_size = (
            extra_prompt_tokens,
            thinking,
            ps_size,
        )
        self.bodies: list[tuple[str, dict]] = []  # (path, JSON body) of every POST
        self.completions = 0
        self.down = False  # the server stopped: every request refused
        self.fail_status: int | None = None  # a 5xx on the next completion
        self.streams: list[Lines] = []
        self.on_line = None
        self.stream_override = None  # a stream of its own for the next completion
        self.model_path = "/modeles/Qwen3.5-2B-Q4_K_M.gguf"  # `/props`: the file it loaded
        self.n_ctx_total: int | None = None  # `/props` top-level `n_ctx` (`-np N`: N slots)

    def __call__(self, request: httpx.Request) -> httpx.Response:
        url = str(request.url)
        if self.down or not (
            (url.startswith(LLAMA_URL) and self.llama)
            or (url.startswith(OLLAMA_URL) and self.ollama)
        ):
            raise httpx.ConnectError("connexion refusée", request=request)
        path = request.url.path
        body = json.loads(request.content) if request.content else {}
        if request.method == "POST":
            self.bodies.append((path, body))
        if url.startswith(LLAMA_URL):
            return self._llama(path, body)
        return self._ollama(path, body)

    def _output(self) -> str:
        output = self.outputs[min(self.completions, len(self.outputs) - 1)]
        self.completions += 1
        return output

    def _stream(self, lines: list[str]) -> httpx.Response:
        stream, self.stream_override = self.stream_override or Lines(lines, self.on_line), None
        self.streams.append(stream)
        return httpx.Response(200, stream=stream)

    def _llama(self, path: str, body: dict) -> httpx.Response:
        if path == "/health":
            return httpx.Response(200, json={"status": "ok"})
        if path == "/props":
            return httpx.Response(
                200,
                json={
                    "model_path": self.model_path,
                    "chat_template": QWEN,
                    "bos_token": "",
                    "eos_token": "<|im_end|>",
                    "default_generation_settings": {"n_ctx": self.n_ctx},
                    **({"n_ctx": self.n_ctx_total} if self.n_ctx_total else {}),
                },
            )
        if path == "/v1/models":
            meta = {"n_ctx_train": 32768, "size": 2 * GIB}
            return httpx.Response(200, json={"data": [{"id": "qwen", "meta": meta}]})
        if path == "/tokenize":
            tokens = []
            for t in tokenize(body["content"]):
                raw = piece(t)
                tokens.append({"id": t, "piece": raw.decode() if raw.isascii() else list(raw)})
            return httpx.Response(200, json={"tokens": tokens})
        if path == "/detokenize":
            text = b"".join(piece(t) for t in body["tokens"]).decode("utf-8", "replace")
            return httpx.Response(200, json={"content": text})
        if path == "/completion":
            if self.fail_status:
                return httpx.Response(self.fail_status, text="erreur interne")
            output = self._output()
            lines = [f"data: {json.dumps({'content': c, 'stop': False})}" for c in output]
            end = {"content": "", "stop": True, "stop_type": self.stop_type}
            end["timings"] = {"prompt_n": len(body["prompt"]) + self.extra_prompt_tokens}
            lines.append(f"data: {json.dumps(end | {'tokens_predicted': len(output)})}")
            return self._stream(lines)
        return httpx.Response(404)

    def _ollama(self, path: str, body: dict) -> httpx.Response:
        if path == "/api/tags":
            details = {"family": "qwen35", "parameter_size": "2B"}  # story 25
            model = {"name": OLLAMA_NAME, "size": GIB, "details": details}
            return httpx.Response(200, json={"models": [model]})
        if path == "/api/ps":
            models = [{"name": OLLAMA_NAME, "size": self.ps_size}] if self.ps_size else []
            models += [{"name": "autre:latest", "size": GIB}]  # another client's model
            return httpx.Response(200, json={"models": models})
        if path == "/api/generate":
            if "prompt" not in body:  # `keep_alive: 0`: unload
                return httpx.Response(200, json={"done": True, "done_reason": "unload"})
            output = self._output()
            lines = []
            if self.thinking:
                lines.append(json.dumps({"thinking": self.thinking, "done": False}))
            lines += [json.dumps({"response": c, "done": False}) for c in output]
            end = {
                "response": "",
                "done": True,
                "done_reason": self.done_reason,
                "prompt_eval_count": len(tokenize(body["prompt"])) + self.extra_prompt_tokens,
                "eval_count": len(output),
            }
            return self._stream([*lines, json.dumps(end)])
        return httpx.Response(404)

    def posts(self, path: str) -> list[dict]:
        return [b for p, b in self.bodies if p == path]


@pytest.fixture
def fake(monkeypatch) -> FakeServer:
    server = FakeServer()
    monkeypatch.setattr(servers, "default_transport", httpx.MockTransport(server))
    return server


def _candidate(
    engine: str, gguf_path: str | None = None, resident: bool = False
) -> discovery.ModelCandidate:
    if engine == "ollama":
        return discovery.ModelCandidate(
            source="server",
            status="server",
            server_url=OLLAMA_URL,
            name=OLLAMA_NAME,
            engine="ollama",
            ref=f"ollama/{OLLAMA_NAME}",
            provider="Ollama",
            gguf_path=gguf_path or "/nulle-part/blob",
            resident=resident,
        )
    return discovery.ModelCandidate(
        source="server",
        status="server",
        server_url=LLAMA_URL,
        name="Qwen3.5-2B-Q4_K_M.gguf",
        engine="llama_server",
        ref="llama_server/Qwen3.5-2B-Q4_K_M.gguf",
        provider="llama-server",
        resident=True,
        served_bytes=2 * GIB,
    )


def _factory(tokenizer: ByteTokenizer | None = None, log: list[str] | None = None):
    """The default `server_factory` (`servers.open_engine`), with the tokenizer double."""
    tokenizer = tokenizer or ByteTokenizer()

    def factory(candidate, n_ctx):  # noqa: ANN001, ANN202
        if log is not None:
            log.append(f"open {candidate.engine}")
        if candidate.engine == "ollama":
            return servers.OllamaRawEngine(
                candidate.server_url,
                candidate.name,
                candidate.gguf_path,
                n_ctx,
                tokenizer=tokenizer,
                unload=not candidate.resident,
            )
        return servers.open_engine(candidate, n_ctx, config.load_config())

    return factory


def _session(**kwargs) -> AppSession:
    cfg = config.load_config()
    cfg.values["memory"] = {"budget_mb": kwargs.pop("budget_mb", 4096), "load_margin_mb": 0}
    return AppSession(
        cfg,
        engine_factory=kwargs.pop("engine_factory", lambda path, n_ctx: FakeEngine()),
        server_factory=kwargs.pop("server_factory", _factory()),
        rss_fn=kwargs.pop("rss_fn", lambda: 0),
    )


def _booted(engine: str, **kwargs) -> AppSession:
    session = _session(**kwargs)
    assert session.boot_server(_candidate(engine)).result() == "ok"
    return session


def _run(session: AppSession, message: str) -> dict[str, list[dict]]:
    mark = get_journal().last_seq()
    session.send(message)
    session.join()
    by_kind: dict[str, list[dict]] = {}
    for envelope in get_journal().events_since(mark):
        by_kind.setdefault(envelope.kind, []).append(envelope.payload)
    return by_kind


def _prompt(ctx: dict) -> str:
    return "".join(s["text"] for s in ctx["segments"])


def _errors(events: dict) -> list[str]:
    return [e["message_fr"] for e in events.get("harness_error", [])]


# ---------- I/O matrix ----------


def _web_with_llama_server(monkeypatch, tmp_path, fake: FakeServer):
    """No GGUF anywhere: the diagnostic only finds the model llama-server serves."""
    monkeypatch.setenv("OLLAMA_MODELS", str(tmp_path / "no-ollama"))
    monkeypatch.setenv("HF_HUB_CACHE", str(tmp_path / "no-hf-cache"))
    monkeypatch.setattr(discovery, "_lm_studio_dirs", lambda: [])
    fake.ollama = False
    cfg = config.load_config()
    session = DiagnosticSession(cfg, port=8420)
    monkeypatch.setattr(session, "check_network", lambda: None)
    app_session = AppSession(cfg, server_factory=_factory(), rss_fn=lambda: 0)
    app = create_app(session, port=8420, version="test", app_session=app_session)
    session.hand_to(app_session, session.run(), launch=True)
    return session, app_session, TestClient(app, base_url="http://127.0.0.1:8420")


def test_llama_server_turn_chosen_at_the_diagnostic(monkeypatch, tmp_path, fake):
    """AC 1: the ids sent are the rendered context tokenized; the segments sum to
    `prompt_tokens`; the tool call is parsed."""
    fake.outputs = [call("get_datetime"), "Il est midi."]
    session, app_session, client = _web_with_llama_server(monkeypatch, tmp_path, fake)
    diagnostic = client.get("/api/diagnostic").json()
    assert diagnostic["ready"] is False and diagnostic["blocking_checks"] == ["model"]
    [row] = diagnostic["candidates"]
    assert (row["status"], row["provider"], row["server_url"]) == (
        "server",
        "llama-server",
        LLAMA_URL,
    )
    assert row["served_bytes"] == 2 * GIB  # `meta.size`: the file is not on this disk

    answer = client.post(
        "/api/intentions/select_model",
        json={"kind": "server", "ref": row["ref"]},
        headers=ORIGIN,
    ).json()
    app_session.join()
    assert answer["switching"] is True and answer["ref"] == row["ref"]
    assert config.read_settings()["selected_model"] == {"kind": "server", "ref": row["ref"]}
    app_session.set_brick("tools", True)
    events = _run(app_session, "Quelle heure est-il ?")

    first, second = events["context_rendered"]
    completions = fake.posts("/completion")
    for ctx, body, ended in zip(
        (first, second), completions, events["model_call_ended"], strict=True
    ):
        assert body["prompt"] == tokenize(_prompt(ctx))  # exactly the harness's text
        assert sum(s["tokens"] for s in ctx["segments"]) == ended["prompt_tokens"]
        assert ended["usage_source"] == "engine"
        assert body["stream"] is True and body["cache_prompt"] is True
        assert body["n_predict"] == ctx["reserve"] and body["stop"] == ["<|im_end|>"]
    assert "<|im_start|>system" in _prompt(first)  # the template is the harness's
    assert events["model_call_ended"][0]["tool_calls"][0]["name"] == "get_datetime"
    assert events["tool_ended"][0]["status"] == "ok"
    assert events["turn_ended"][0]["status"] == "completed"
    diagnostic = client.get("/api/diagnostic").json()
    assert diagnostic["loaded"] == {
        "kind": "server",
        "ref": row["ref"],
        "label": "Qwen3.5-2B-Q4_K_M",
    }
    assert diagnostic["selected"] == {"kind": "server", "ref": row["ref"]}


def test_ollama_turn_with_equal_counts(fake):
    session = _booted("ollama")
    events = _run(session, "Bonjour")

    [ctx] = events["context_rendered"]
    [body] = fake.posts("/api/generate")
    assert body["prompt"] == _prompt(ctx) and body["raw"] is True and body["stream"] is True
    assert body["model"] == OLLAMA_NAME
    assert body["options"]["num_ctx"] == ctx["window"] == 4096
    assert body["options"]["num_predict"] == ctx["reserve"]
    assert events["model_call_ended"][0]["prompt_tokens"] == ctx["used"]
    assert events["model_call_ended"][0]["output_tokens"] == len("Bonjour !")
    assert _errors(events) == []
    assert events["turn_ended"][0]["status"] == "completed"


def test_ollama_adds_a_token_reduced_transparency(fake):
    fake.extra_prompt_tokens = 1
    session = _booted("ollama")
    events = _run(session, "Bonjour")

    used = events["context_rendered"][0]["used"]
    [message] = _errors(events)
    assert message.startswith("Transparence réduite")
    assert f"Ollama a lu {used + 1} tokens de prompt, le harnais en a compté {used}" in message
    assert events["turn_ended"][0]["status"] == "completed"


def test_ollama_thinking_field_reported_once_per_call(fake):
    fake.thinking = "je réfléchis"
    session = _booted("ollama")
    events = _run(session, "Bonjour")

    [message] = _errors(events)
    assert "« thinking »" in message and message.startswith("Transparence réduite")
    assert events["turn_ended"][0]["status"] == "completed"


@pytest.mark.parametrize("engine", ["llama_server", "ollama"])
def test_output_cut_is_length(fake, engine):
    fake.stop_type, fake.done_reason = "limit", "length"
    session = _booted(engine)
    events = _run(session, "Bonjour")

    assert events["model_call_ended"][0]["stop_reason"] == "length"
    assert events["output_truncated"][0]["channel"] == "text"
    assert events["turn_ended"][0]["status"] == "limit"


@pytest.mark.parametrize("engine", ["llama_server", "ollama"])
def test_stop_mid_stream_closes_it(fake, engine):
    fake.outputs = ["Une réponse assez longue pour être arrêtée."]
    session = _booted(engine)
    cancel = CancelToken()
    fake.on_line = lambda n: cancel.cancel() if n == 3 else None
    ids = session._engine.tokenize("<|im_start|>user\nBonjour<|im_end|>\n")

    fragments = list(session._engine.complete(ids, ["<|im_end|>"], 100, cancel))

    assert fragments[-1].stop_reason == "cancelled"
    assert fake.streams[-1].closed is True
    assert fragments[-1].output_tokens < len(fake.outputs[0])


def test_stop_intention_during_a_served_turn(fake):
    gate = threading.Event()
    fake.outputs = ["Une réponse longue."]
    fake.on_line = lambda n: gate.wait(5) if n == 2 else None
    session = _booted("llama_server")
    mark = get_journal().last_seq()
    session.send("Bonjour")
    assert session.stop() is True
    gate.set()
    session.join()

    ended = [e.payload for e in get_journal().events_since(mark) if e.kind == "turn_ended"]
    assert ended[0]["status"] == "cancelled" and fake.streams[-1].closed


@pytest.mark.parametrize("failure", ["down", "500"])
def test_server_stopped_mid_turn(fake, failure):
    session = _booted("llama_server")
    session._emit_preview()  # tokenized before the server stops
    if failure == "down":
        fake.down = True
    else:
        fake.fail_status = 500
    events = _run(session, "Bonjour")

    assert events["turn_ended"][0]["status"] == "error"
    [message] = _errors(events)
    assert message.startswith(f"Serveur local injoignable ({LLAMA_URL})")
    assert session.state == "idle"
    fake.down, fake.fail_status = False, None
    assert _run(session, "Encore")["turn_ended"][0]["status"] == "completed"  # still usable


def test_unreadable_blob_is_incompatible(monkeypatch, tmp_path, fake):
    root = tmp_path / "ollama"
    monkeypatch.setenv("OLLAMA_MODELS", str(root))
    manifest = root / "manifests" / "registry.ollama.ai" / "library" / "qwen3.5" / "2b"
    manifest.parent.mkdir(parents=True)
    layer = {"mediaType": "application/vnd.ollama.image.tensor", "digest": "sha256:abc"}
    manifest.write_text(json.dumps({"layers": [layer]}), encoding="utf-8")

    candidates = discovery._server_candidates(config.load_config())

    ollama = next(c for c in candidates if c.engine == "ollama")
    assert ollama.status == "incompatible" and "tenseur" in (ollama.reason or "")
    assert ollama.gguf_path is None

    manifest.unlink()  # no blob at all
    ollama = next(
        c for c in discovery._server_candidates(config.load_config()) if c.engine == "ollama"
    )
    assert ollama.status == "incompatible" and "introuvable" in (ollama.reason or "")


def test_vocab_only_failure_keeps_the_previous_model(monkeypatch, fake):
    """`VocabTokenizer` refused by llama-cpp-python: the previous model stays active."""

    def refuse(path):  # noqa: ANN001, ANN202
        raise ValueError(f"Failed to load model from file: {path}")

    monkeypatch.setattr(servers, "VocabTokenizer", refuse)
    session = AppSession(
        config.load_config(),
        engine_factory=lambda path, n_ctx: FakeEngine(),
        server_factory=lambda c, n_ctx: servers.open_engine(c, n_ctx, config.load_config()),
        rss_fn=lambda: 0,
    )
    assert session.boot("A.gguf").result() == "ok"
    mark = get_journal().last_seq()

    _, future = session.switch_model(ModelChoice.served(_candidate("ollama")))

    assert future.result() == "restored"
    assert session.active_model()["label"] == "A" and session.state == "idle"
    events = [e.payload for e in get_journal().events_since(mark)]
    error = next(e for e in events if "message_fr" in e and "Ollama" in e["message_fr"])
    assert "Failed to load model from file" in error["cause"]  # lot E (E6): the detail
    ended = next(e for e in events if e.get("status") == "restored")
    assert "Failed to load model" not in ended["reason_fr"]  # the reason, in French only
    assert "ne sait pas lire le tokenizer de ce modèle" in ended["reason_fr"]
    assert "servez-le plutôt avec llama-server" in ended["reason_fr"]  # the way out


def test_budget_exceeded_keeps_the_previous_model(fake, tmp_path):
    """An Ollama model not loaded yet costs its file, its KV cache and the margin."""
    blob = tmp_path / "blob"
    with open(blob, "wb") as f:
        f.truncate(5 * GIB - 256 * 1024**2)  # sparse: 4,75 Go on disk, nothing written
    cfg = config.load_config()
    cfg.values["memory"] = {"budget_mb": 4096, "load_margin_mb": 256}
    session = AppSession(
        cfg,
        engine_factory=lambda path, n_ctx: FakeEngine(),
        server_factory=_factory(),
        rss_fn=lambda: GIB,
    )
    assert session.boot("A.gguf").result() == "ok"

    with pytest.raises(SendRefused) as refused:
        session.switch_model(ModelChoice.served(_candidate("ollama", str(blob))))

    assert refused.value.reason_fr.startswith(
        f"Changement refusé : {OLLAMA_NAME} demande environ 5,0 Go"
    )
    assert "A reste actif" in refused.value.reason_fr
    assert session.active_model()["label"] == "A"
    assert fake.posts("/api/generate") == []  # nothing sent to Ollama


@pytest.mark.parametrize("engine", ["ollama", "llama_server"])
def test_budget_counts_a_resident_served_model_without_refusing_it(fake, tmp_path, engine):
    """Already in memory (an Ollama model in `/api/ps`, llama-server's model): choosing it
    adds nothing, so it is never refused; its memory is granted."""
    session = _session(rss_fn=lambda: 10 * GIB)  # far past the 4 Go budget
    assert session.boot("A.gguf").result() == "ok"
    candidate = _candidate(engine, str(tmp_path / "blob"), resident=True)
    candidate.served_bytes = 3 * GIB

    _, future = session.switch_model(ModelChoice.served(candidate))

    assert future.result() == "ok" and session.active_model()["kind"] == "server"
    assert session._load_registry._slots["generative"].cost == 3 * GIB


def test_leaving_ollama_unloads_it_and_never_two_models(fake):
    log: list[str] = []
    session = _session(
        server_factory=_factory(log=log),
        engine_factory=lambda path, n_ctx: log.append("open file") or FakeEngine(),
    )
    assert session.boot("A.gguf").result() == "ok"
    session._engine.close = lambda: log.append("close file")

    _, future = session.switch_model(ModelChoice.served(_candidate("ollama")))
    assert future.result() == "ok"
    assert log == ["open file", "close file", "open ollama"]  # A closed before Ollama
    assert fake.posts("/api/generate") == []
    _run(session, "Bonjour")  # Ollama loads the model on this first call

    _, future = session.switch_model(ModelChoice("file", "B.gguf"))  # changing model
    assert future.result() == "ok"
    assert fake.posts("/api/generate")[-1] == {"model": OLLAMA_NAME, "keep_alive": 0}

    _, future = session.switch_model(ModelChoice.served(_candidate("ollama")))
    future.result()
    _run(session, "Bonjour")
    session.close()  # closing WaveStack
    assert fake.posts("/api/generate")[-1] == {"model": OLLAMA_NAME, "keep_alive": 0}


def test_ollama_never_unloads_what_it_did_not_load(fake):
    """No generation asked, or a model Ollama already held when chosen (another client's):
    WaveStack leaves it loaded."""
    session = _booted("ollama")
    _, future = session.switch_model(ModelChoice("file", "B.gguf"))
    assert future.result() == "ok" and fake.posts("/api/generate") == []  # never used

    _, future = session.switch_model(ModelChoice.served(_candidate("ollama", resident=True)))
    assert future.result() == "ok"
    _run(session, "Bonjour")
    session.close()
    assert all("keep_alive" not in body for body in fake.posts("/api/generate"))


def test_unload_failure_is_traced_never_blocking(fake):
    session = _booted("ollama")
    _run(session, "Bonjour")
    fake.down = True
    mark = get_journal().last_seq()

    _, future = session.switch_model(ModelChoice("file", "B.gguf"))

    assert future.result() == "ok" and session.active_model()["label"] == "B"
    errors = [e.payload for e in get_journal().events_since(mark) if e.kind == "harness_error"]
    assert errors[0]["message_fr"] == f"Ollama n'a pas déchargé le modèle {OLLAMA_NAME}."


def _diagnostic(monkeypatch, tmp_path, models: tuple[str, ...] = ()) -> DiagnosticSession:
    monkeypatch.setenv("OLLAMA_MODELS", str(tmp_path / "no-ollama"))
    monkeypatch.setenv("HF_HUB_CACHE", str(tmp_path / "no-hf-cache"))
    monkeypatch.setattr(discovery, "_lm_studio_dirs", lambda: [])
    config.models_dir().mkdir(parents=True)
    for name in models:
        (config.models_dir() / name).write_bytes(b"placeholder")
    session = DiagnosticSession(config.load_config(), port=8420)
    monkeypatch.setattr(session, "_probe_candidate", lambda candidate, cancel=None: None)
    return session


def test_saved_server_choice_taken_back_while_served(monkeypatch, tmp_path, fake):
    fake.ollama = False
    ref = "llama_server/Qwen3.5-2B-Q4_K_M.gguf"
    config.save_setting("selected_model", {"kind": "server", "ref": ref})
    session = _diagnostic(monkeypatch, tmp_path, models=("A.gguf",))

    result = session.check_model()

    assert result.ready is True and result.server is not None and result.server.ref == ref
    assert result.model_path is None  # the single file is not loaded instead
    app_session = _session()
    session.hand_to(app_session, result, launch=True)
    app_session.join()
    assert app_session.active_model()["kind"] == "server"


def test_saved_server_choice_with_the_server_off(monkeypatch, tmp_path, fake):
    fake.down = True
    config.save_setting("selected_model", {"kind": "server", "ref": "ollama/qwen3.5:2b"})
    session = _diagnostic(monkeypatch, tmp_path, models=("A.gguf",))
    mark = get_journal().last_seq()

    result = session.check_model()

    assert result.ready is True and result.model_path == str(config.models_dir() / "A.gguf")
    check = [
        e.payload
        for e in get_journal().events_since(mark)
        if e.kind == "diagnostic_check" and e.payload["check"] == "model"
    ][-1]
    assert check["status"] == "warn"
    assert (
        "Le modèle servi enregistré n'est plus disponible : ollama/qwen3.5:2b"
        in check["message_fr"]
    )


def test_servers_only_block_with_a_choice(monkeypatch, tmp_path, fake):
    fake.ollama = False
    session = _diagnostic(monkeypatch, tmp_path)
    mark = get_journal().last_seq()

    result = session.check_model()

    assert result.ready is False and result.blocking_checks == ["model"] and result.server is None
    check = [e.payload for e in get_journal().events_since(mark) if e.kind == "diagnostic_check"][
        -1
    ]
    assert check["blocking"] is True and "choisissez un modèle servi" in check["message_fr"]


# ---------- schema, indicator, window, capabilities, discovery, client ----------


def test_active_model_and_schema_after_a_reload(monkeypatch, tmp_path, fake):
    """AC 2: the indicator and the robot outside the harness come back from `/api/state`."""
    _, app_session, client = _web_with_llama_server(monkeypatch, tmp_path, fake)
    ref = "llama_server/Qwen3.5-2B-Q4_K_M.gguf"
    client.post("/api/intentions/select_model", json={"kind": "server", "ref": ref}, headers=ORIGIN)
    app_session.join()

    state = client.get("/api/state").json()
    assert state["active_model"] == {
        "id": ref,
        "label": "Qwen3.5-2B-Q4_K_M",
        "hosting": "local",
        "provider": "llama-server",
        "server_url": LLAMA_URL,
        "disclosure": None,
        "kind": "server",
        "ref": ref,
    }
    nodes = {n["id"]: n for n in state["architecture_changed"]["nodes"]}
    model = nodes["core.model"]
    assert model["hosting"] == "local" and model["process"] == "external"
    assert (model["provider"], model["server_url"]) == ("llama-server", LLAMA_URL)
    assert state["architecture_changed"]["edges"] == [
        {"from": "core.harness", "to": "core.model", "crosses_boundary": False}
    ]


def test_window_is_the_servers_context_when_smaller(fake):
    fake.n_ctx = 2048
    session = _booted("llama_server")
    session._emit_preview()

    preview = [e.payload for e in get_journal().all_events() if e.kind == "context_preview"][-1]
    assert (preview["window"], preview["window_source"]) == (2048, "server")


def test_llama_server_metadata_and_pieces(fake):
    engine = servers.LlamaServerEngine(LLAMA_URL, markers=["<|im_start|>", "[INST]"])
    meta = engine.metadata()
    assert meta.architecture is None and meta.chat_template == QWEN
    assert (meta.native_context, meta.server_context) == (32768, 4096)
    # `[INST]`: several tokens; the template's `<tool_call>` markers: one token each.
    assert meta.special_tokens == ("<|im_end|>", "<|im_start|>", "<tool_call>", "</tool_call>")
    ids = engine.tokenize("été <|im_start|>")
    assert b"".join(engine.token_pieces(ids)) == "été <|im_start|>".encode()  # list pieces
    engine._pieces.clear()  # not seen by `tokenize`: `/detokenize`
    assert engine.token_pieces([ord("a")]) == [b"a"]
    caps = capabilities_for(meta)  # AD-6: the family from the template
    assert (caps.family, caps.tool_call_parser) == ("qwen3", "qwen3_coder")
    engine.close()


def test_server_candidates_one_per_served_model(monkeypatch, tmp_path, fake):
    """Closes the first entry of deferred-work.md: `_server_candidates` with a simulated
    transport."""
    root = tmp_path / "ollama"
    monkeypatch.setenv("OLLAMA_MODELS", str(root))
    manifest = root / "manifests" / "registry.ollama.ai" / "library" / "qwen3.5" / "2b"
    manifest.parent.mkdir(parents=True)
    blob = root / "blobs" / "sha256-abc"
    blob.parent.mkdir(parents=True)
    blob.write_bytes(b"GGUF" + b"\0" * 60)
    layer = {"mediaType": "application/vnd.ollama.image.model", "digest": "sha256:abc"}
    manifest.write_text(json.dumps({"layers": [layer]}), encoding="utf-8")
    fake.ps_size = 3 * GIB
    cfg = config.load_config()

    candidates = discovery._server_candidates(cfg, transport=httpx.MockTransport(fake))

    by_engine = {c.engine: c for c in candidates}
    ollama, llama = by_engine["ollama"], by_engine["llama_server"]
    assert (ollama.status, ollama.ref, ollama.gguf_path) == (
        "server",
        f"ollama/{OLLAMA_NAME}",
        str(blob),
    )
    assert ollama.served_bytes == 3 * GIB and ollama.resident  # `/api/ps`: loaded
    assert llama.resident is True
    assert (llama.status, llama.ref, llama.name) == (
        "server",
        "llama_server/Qwen3.5-2B-Q4_K_M.gguf",
        "Qwen3.5-2B-Q4_K_M.gguf",
    )
    fake.down = True
    assert discovery._server_candidates(cfg) == []  # a silent server: nothing listed


def test_served_models_keep_ollama_details_and_llama_server_template(monkeypatch, fake):
    """Story 25: what the model table needs, read from the answers discovery already
    fetched (`/api/tags`, `/props`, `/v1/models`), never by another request."""
    paths: list[str] = []

    def recording(request: httpx.Request) -> httpx.Response:
        paths.append(request.url.path)
        return fake(request)

    monkeypatch.setattr(servers, "default_transport", httpx.MockTransport(recording))
    by_engine = {m.engine: m for m in servers.list_served(config.load_config())}
    assert sorted(paths) == ["/api/ps", "/api/tags", "/health", "/props", "/v1/models"]
    ollama, llama = by_engine["ollama"], by_engine["llama_server"]
    assert (ollama.family, ollama.parameter_size) == ("qwen35", "2B")
    assert (llama.chat_template, llama.n_ctx_train, llama.size) == (QWEN, 32768, 2 * GIB)
    # …handed to the candidates, the template never sent in `/api/diagnostic`.
    by_engine = {c.engine: c for c in discovery._server_candidates(config.load_config())}
    assert (by_engine["ollama"].publisher_hint, by_engine["ollama"].params_label) == (
        "qwen35",
        "2B",
    )
    candidate = by_engine["llama_server"]
    assert (candidate.server_template, candidate.native_context) == (QWEN, 32768)
    assert "server_template" not in candidate.model_dump()


def test_loopback_client_refuses_any_other_host():
    seen = []
    transport = httpx.MockTransport(lambda r: seen.append(r) or httpx.Response(200))
    client = create_loopback_client(transport=transport)
    assert client._trust_env is False  # an office proxy never receives 127.0.0.1
    with pytest.raises(NetworkBlocked):
        client.get("http://example.org/api/tags")
    assert client.get("http://127.0.0.1:11434/api/tags").status_code == 200
    assert len(seen) == 1
    client.close()


def test_ollama_engine_close_unloads_and_closes_its_tokenizer(fake):
    tokenizer = ByteTokenizer()
    engine = servers.OllamaRawEngine(OLLAMA_URL, OLLAMA_NAME, None, 65536, tokenizer=tokenizer)
    list(engine.complete(tokenize("Bonjour"), [], 10, CancelToken()))
    engine.close()
    engine.close()  # once only
    assert fake.posts("/api/generate")[-1] == {"model": OLLAMA_NAME, "keep_alive": 0}
    assert len(fake.posts("/api/generate")) == 2
    assert tokenizer.closed


def test_e2e_fake_llama_server_speaks_what_the_adapter_reads():
    """`tools/e2e/fake_local_server.py`, read by the real `llama_server` adapter."""
    import importlib.util
    import sys

    path = Path(__file__).resolve().parents[1] / "tools" / "e2e" / "fake_local_server.py"
    spec = importlib.util.spec_from_file_location("fake_local_server", path)
    module = importlib.util.module_from_spec(spec)
    sys.modules["fake_local_server"] = module
    spec.loader.exec_module(module)
    client = TestClient(module.create_app("llama_server"))

    def bridge(request: httpx.Request) -> httpx.Response:
        answer = client.request(request.method, request.url.path, content=request.content)
        return httpx.Response(answer.status_code, content=answer.content)

    engine = servers.LlamaServerEngine(LLAMA_URL, transport=httpx.MockTransport(bridge))
    prompt = "<|im_start|>user\nQuelle heure est-il ?<|im_end|>\n<|im_start|>assistant\n"
    ids = engine.tokenize(prompt)
    assert b"".join(engine.token_pieces(ids)) == prompt.encode()
    text = "".join(f.text for f in engine.complete(ids, ["<|im_end|>"], 100, CancelToken()))
    assert text == "Réponse du faux llama-server au message : « Quelle heure est-il ? »"
    assert capabilities_for(engine.metadata()).family == "qwen3"
    engine.close()


# ---------- independent review of story 18 ----------

TINY = Path(__file__).parent / "fixtures" / "tiny-llama.gguf"


def test_ollama_cache_is_an_information_not_reduced_transparency(fake):
    fake.extra_prompt_tokens = -10  # the start of the prompt came from Ollama's cache
    session = _booted("ollama")
    events = _run(session, "Bonjour")

    used = events["context_rendered"][0]["used"]
    assert _errors(events) == []
    [cached] = events["server_cache_used"]
    assert (cached["prompt_tokens"], cached["evaluated_tokens"]) == (used, used - 10)
    assert "cache" in cached["message_fr"]
    # Lot A: the call's `evaluated_tokens` is Ollama's `prompt_eval_count`.
    assert events["model_call_ended"][0]["evaluated_tokens"] == used - 10


def test_llama_server_evaluated_tokens_are_its_timings(fake):
    """Lot A: llama-server's closing chunk says the prompt tokens it evaluated
    (`timings.prompt_n`, fewer when its cache served the start)."""
    fake.extra_prompt_tokens = -7
    session = _booted("llama_server")
    events = _run(session, "Bonjour")

    used = events["context_rendered"][0]["used"]
    assert events["model_call_ended"][0]["evaluated_tokens"] == used - 7
    assert _errors(events) == []


class Blocking(httpx.SyncByteStream):
    """A server that sends nothing (Ollama loading its model) until the client closes."""

    def __init__(self) -> None:
        self.released = threading.Event()
        self.closed = False

    def __iter__(self) -> Iterator[bytes]:
        self.released.wait(10)
        return
        yield b""  # a generator

    def close(self) -> None:
        self.closed = True
        self.released.set()


@pytest.mark.parametrize("engine", ["llama_server", "ollama"])
def test_stop_before_the_first_token_closes_the_stream_at_once(fake, engine):
    session = _booted(engine)
    fake.stream_override = Blocking()
    stream = fake.stream_override
    cancel = CancelToken()
    threading.Timer(0.2, cancel.cancel).start()
    started = time.monotonic()

    fragments = list(session._engine.complete(tokenize("Bonjour"), [], 10, cancel))

    assert time.monotonic() - started < 2  # never the read timeout (300 s)
    assert fragments[-1].stop_reason == "cancelled" and stream.closed


def test_close_during_a_silent_stream_does_not_wait(fake):
    """`AppSession.close` stops the turn: the silent stream is closed, the worker ends."""
    session = _booted("ollama")
    fake.stream_override = Blocking()
    session.send("Bonjour")
    time.sleep(0.2)
    started = time.monotonic()
    session.close()
    assert time.monotonic() - started < 3


@pytest.mark.parametrize(
    ("lines", "cause"),
    [
        (["pas du JSON"], "flux illisible"),
        (["[1, 2]"], "flux illisible"),
        ([json.dumps({"response": "Bon", "done": False})], "flux interrompu"),
    ],
)
def test_malformed_ollama_stream_is_a_server_error(fake, lines, cause):
    session = _booted("ollama")
    fake.stream_override = Lines(lines)
    with pytest.raises(servers.ServerError) as error:
        list(session._engine.complete(tokenize("Bonjour"), [], 10, CancelToken()))
    assert cause in error.value.message_fr


def test_llama_stream_done_marker_is_skipped_and_an_early_end_refused(fake):
    session = _booted("llama_server")
    fake.stream_override = Lines(
        ["data: " + json.dumps({"content": "Oui", "stop": False}), "data: [DONE]"]
    )
    with pytest.raises(servers.ServerError) as error:
        list(session._engine.complete(tokenize("Bonjour"), [], 10, CancelToken()))
    assert "flux interrompu avant la fin" in error.value.message_fr


def test_malformed_server_answers_are_skipped_or_refused(monkeypatch):
    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.path == "/api/tags":
            return httpx.Response(200, json=[{"name": "x"}])  # not an object
        if request.url.path == "/health":
            return httpx.Response(200, json={"status": "ok"})
        return httpx.Response(200, text="<html>pas du JSON</html>")

    monkeypatch.setattr(servers, "default_transport", httpx.MockTransport(handler))
    assert servers.list_served(config.load_config()) == []  # both servers skipped
    with pytest.raises(servers.ServerError) as error:
        servers.LlamaServerEngine(LLAMA_URL)
    expected = f"Serveur local injoignable ({LLAMA_URL}) : réponse illisible sur /props"
    assert error.value.message_fr == expected


def test_ollama_cloud_models_are_never_listed_as_local(monkeypatch):
    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.path == "/api/tags":
            models = [
                {"name": "gpt-oss:120b-cloud"},
                {"name": "kimi:latest", "remote_host": "https://ollama.com:443"},
                {"name": "qwen3:0.6b"},
            ]
            return httpx.Response(200, json={"models": models})
        if request.url.path == "/api/ps":
            return httpx.Response(200, json={"models": []})
        raise httpx.ConnectError("non", request=request)

    monkeypatch.setattr(servers, "default_transport", httpx.MockTransport(handler))
    assert [m.name for m in servers.list_served(config.load_config())] == ["qwen3:0.6b"]


def test_a_chatml_template_with_tool_calls_only_is_not_qwen3():
    qwen25 = (
        "{% for m in messages %}<|im_start|>{{ m.role }}\n{{ m.content }}<|im_end|>\n"
        "{% endfor %}{# <tool_call> #}"
    )
    caps = capabilities_for(EngineMetadata(None, qwen25, None, "", "<|im_end|>", ()))
    assert caps.family == "unknown" and caps.tool_call_parser is None
    assert capabilities_for(EngineMetadata(None, QWEN, None, "", "", ())).family == "qwen3"


@pytest.mark.parametrize("engine", ["llama_server", "ollama"])
def test_sampling_matches_the_in_process_engine(fake, engine):
    session = _booted(engine)
    _run(session, "Bonjour")
    if engine == "ollama":
        sent = fake.posts("/api/generate")[-1]["options"]
    else:
        sent = fake.posts("/completion")[-1]
    assert {k: sent[k] for k in ("temperature", "top_p", "top_k", "min_p")} == {
        "temperature": 0.7,
        "top_p": 0.8,
        "top_k": 20,
        "min_p": 0.0,
    }
    penalties = (sent["repeat_penalty"], sent["presence_penalty"], sent["frequency_penalty"])
    assert penalties == (1.0, 0.0, 0.0) and "seed" not in sent


def test_loopback_ports_parsing():
    ports = {"ollama": "11435", "llama_server": 70000, "x": "a"}
    cfg = config.Config(values={"net": {"loopback_ports": ports}})
    assert cfg.loopback_ports == {"ollama": 11435}  # out of range, not a number: ignored
    assert config.Config(values={}).loopback_ports == {"ollama": 11434, "llama_server": 8080}


def test_ollama_stop_marker_is_cut(fake):
    fake.outputs = ["Oui.<|im_end|>suite"]
    session = _booted("ollama")
    stop = ["<|im_end|>"]
    fragments = list(session._engine.complete(tokenize("Bonjour"), stop, 50, CancelToken()))
    assert "".join(f.text for f in fragments) == "Oui."
    assert fragments[-1].stop_reason == "stop"


def test_num_ctx_is_the_sessions_window(fake):
    cfg = config.load_config()
    cfg.values["context"] = {"window": 8192, "near_limit_ratio": 0.8}
    session = AppSession(cfg, server_factory=_factory(), rss_fn=lambda: 0)
    assert session.boot_server(_candidate("ollama")).result() == "ok"
    events = _run(session, "Bonjour")
    assert fake.posts("/api/generate")[-1]["options"]["num_ctx"] == session._window == 8192
    assert events["context_rendered"][0]["window"] == 8192


def test_detokenize_replacement_character_is_refused(fake):
    engine = servers.LlamaServerEngine(LLAMA_URL)
    with pytest.raises(servers.ServerError) as error:
        engine.token_pieces([0xC3])  # half of « é »: `/detokenize` gives U+FFFD
    assert "illisible par /detokenize" in error.value.message_fr
    assert 0xC3 not in engine._pieces
    engine.close()


def test_unload_request_has_its_own_short_timeout(fake):
    seen = []

    def spy(request: httpx.Request) -> httpx.Response:
        seen.append(request)
        return fake(request)

    engine = servers.OllamaRawEngine(
        OLLAMA_URL,
        OLLAMA_NAME,
        None,
        4096,
        tokenizer=ByteTokenizer(),
        transport=httpx.MockTransport(spy),
    )
    list(engine.complete(tokenize("Bonjour"), [], 10, CancelToken()))
    engine.close()
    unload = seen[-1]
    assert json.loads(unload.content) == {"model": OLLAMA_NAME, "keep_alive": 0}
    assert unload.extensions["timeout"]["read"] == 10.0


def test_blob_without_gguf_magic_is_incompatible(monkeypatch, tmp_path, fake):
    root = tmp_path / "ollama"
    monkeypatch.setenv("OLLAMA_MODELS", str(root))
    manifest = root / "manifests" / "registry.ollama.ai" / "library" / "qwen3.5" / "2b"
    manifest.parent.mkdir(parents=True)
    (root / "blobs").mkdir()
    (root / "blobs" / "sha256-abc").write_bytes(b"PAS UN GGUF")
    layer = {"mediaType": "application/vnd.ollama.image.model", "digest": "sha256:abc"}
    manifest.write_text(json.dumps({"layers": [layer]}), encoding="utf-8")

    listed = discovery._server_candidates(config.load_config())
    ollama = next(c for c in listed if c.engine == "ollama")

    assert ollama.status == "incompatible" and ollama.gguf_path is None
    assert ollama.reason == "Le fichier du modèle n'est pas un GGUF lisible."


def test_choosing_a_file_keeps_the_served_models_choosable(monkeypatch, tmp_path, fake):
    """An incompatible served model (no path) never marks the others incompatible."""
    session = _diagnostic(monkeypatch, tmp_path, models=("A.gguf", "B.gguf"))
    session.check_model()  # Ollama's model: no GGUF on disk, incompatible
    session.select_model(str(config.models_dir() / "A.gguf"))

    listed = {c.ref: c.status for c in session.last_result.candidates if c.source == "server"}
    assert listed == {
        f"ollama/{OLLAMA_NAME}": "incompatible",
        "llama_server/Qwen3.5-2B-Q4_K_M.gguf": "server",
    }


def test_saved_served_model_now_incompatible_shows_its_reason(monkeypatch, tmp_path, fake):
    config.save_setting("selected_model", {"kind": "server", "ref": f"ollama/{OLLAMA_NAME}"})
    session = _diagnostic(monkeypatch, tmp_path, models=("A.gguf",))
    mark = get_journal().last_seq()

    session.check_model()

    check = [
        e.payload
        for e in get_journal().events_since(mark)
        if e.kind == "diagnostic_check" and e.payload["check"] == "model"
    ][-1]
    assert "Fichier GGUF du modèle introuvable dans le dossier d'Ollama" in check["message_fr"]


def _web_file_loaded(monkeypatch, tmp_path):
    session = _diagnostic(monkeypatch, tmp_path, models=("A.gguf",))
    monkeypatch.setattr(session, "check_network", lambda: None)
    closing = type("FakeCloud", (), {"close": lambda self: None})
    app_session = AppSession(
        config.load_config(),
        engine_factory=lambda path, n_ctx: FakeEngine(),
        server_factory=_factory(),
        cloud_factory=lambda entry, key: closing(),
        rss_fn=lambda: 0,
    )
    app = create_app(session, port=8420, version="test", app_session=app_session)
    session.hand_to(app_session, session.run(), launch=True)
    app_session.join()
    return session, app_session, TestClient(app, base_url="http://127.0.0.1:8420")


def test_hot_switch_to_a_served_model_after_a_file(monkeypatch, tmp_path, fake):
    _, app_session, client = _web_file_loaded(monkeypatch, tmp_path)
    a = str(config.models_dir() / "A.gguf")
    diagnostic = client.get("/api/diagnostic").json()
    assert diagnostic["loaded"] == {"kind": "file", "ref": a, "label": "A"}
    ref = "llama_server/Qwen3.5-2B-Q4_K_M.gguf"

    answer = client.post(
        "/api/intentions/select_model", json={"kind": "server", "ref": ref}, headers=ORIGIN
    ).json()
    app_session.join()

    assert answer["switching"] is True and answer["ref"] == ref
    assert app_session.active_model()["kind"] == "server"
    assert config.read_settings()["selected_model"] == {"kind": "server", "ref": ref}
    diagnostic = client.get("/api/diagnostic").json()
    assert diagnostic["selected"] == {"kind": "server", "ref": ref}
    assert diagnostic["loaded"] == {"kind": "server", "ref": ref, "label": "Qwen3.5-2B-Q4_K_M"}


def test_diagnostic_selected_and_loaded_for_a_file_then_a_cloud_model(monkeypatch, tmp_path, fake):
    from pydantic import SecretStr

    session, app_session, client = _web_file_loaded(monkeypatch, tmp_path)
    a = str(config.models_dir() / "A.gguf")
    assert client.get("/api/diagnostic").json()["selected"] is None  # single file, unsaved
    session.select_model(a)
    assert client.get("/api/diagnostic").json()["selected"] == {"kind": "file", "ref": a}
    entry = config.load_config().cloud_model("groq")
    config.write_api_key(entry.id, entry.host, SecretStr("k-test"))

    client.post(
        "/api/intentions/select_model",
        json={"kind": "cloud", "ref": "groq", "acknowledged": True},
        headers=ORIGIN,
    )
    app_session.join()

    diagnostic = client.get("/api/diagnostic").json()
    assert diagnostic["loaded"] == {"kind": "cloud", "ref": "groq", "label": entry.model}
    assert diagnostic["selected"] == {"kind": "cloud", "ref": "groq"}


# ---------- the tiny synthetic GGUF: llama-cpp-python in the default suite ----------


def test_vocab_tokenizer_on_a_real_gguf():
    tokenizer = VocabTokenizer(str(TINY))
    meta = tokenizer.metadata()
    # `vocab_only` reads no hyperparameters: the native context comes from the GGUF key.
    assert (meta.architecture, meta.native_context) == ("llama", 256)
    assert meta.eos_token == "<|im_end|>"
    assert meta.special_tokens == ("<|im_start|>", "<|im_end|>")
    text = "<|im_start|>user\nÉté 🙂<|im_end|>"
    ids = tokenizer.tokenize(text)
    assert (ids[0], ids[-1]) == (257, 258)  # one token per template marker
    pieces = tokenizer.token_pieces(ids)
    assert b"".join(pieces) == text.encode() and b"\xc3" in pieces  # « É » split in bytes
    tokenizer.close()


_LOG_SPY = """
import builtins, sys
calls = []
real = builtins.print
def spy(*args, **kwargs):
    if "file" in kwargs:  # llama-cpp-python's log callback prints to a file (sys.stderr)
        calls.append(args)
    return real(*args, **kwargs)
builtins.print = spy
if sys.argv[2] == "raw":  # the control: the model opened as before lot J
    import llama_cpp
    from llama_cpp import _internals
    params = llama_cpp.llama_model_default_params()
    params.vocab_only = True
    _internals.LlamaModel(path_model=sys.argv[1], params=params, verbose=False)
else:
    from wavestack.models.engine import VocabTokenizer
    tokenizer = VocabTokenizer(sys.argv[1])
    tokenizer.tokenize("Bonjour")
    tokenizer.close()
real(len(calls))
"""


def test_vocab_tokenizer_opened_alone_keeps_llama_cpp_quiet():
    """Lot J: in a fresh process (nothing has set llama.cpp's log level yet), opening a GGUF
    `vocab_only` does not let llama.cpp's log callback print. Unquieted, it printed the whole
    vocabulary load (45 lines for this file) into the null file llama-cpp-python swaps for
    stderr, opened in cp1252 on Windows: Qwen3.5's pieces (« Ċ », « Ġ ») raised an ignored
    `UnicodeEncodeError` (target PC, 2026-09-27)."""
    import subprocess
    import sys

    def printed(mode: str) -> int:
        proc = subprocess.run(
            [sys.executable, "-c", _LOG_SPY, str(TINY), mode],
            capture_output=True,
            text=True,
            timeout=60,
        )
        assert proc.returncode == 0, proc.stderr
        return int(proc.stdout.strip().splitlines()[-1])

    assert printed("raw") > 0  # the spy sees the callback's output when nothing quiets it
    assert printed("tokenizer") == 0


def test_llama_cpp_engine_on_a_real_gguf():
    engine = LlamaCppEngine(str(TINY), n_ctx=128)
    meta = engine.metadata()
    assert (meta.architecture, meta.native_context) == ("llama", 256)
    assert meta.chat_template is not None
    ids = engine.tokenize("<|im_start|>user\nBonjour<|im_end|>\n<|im_start|>assistant\n")
    fragments = list(engine.complete(ids, ["<|im_end|>"], 5, CancelToken()))
    assert fragments[-1].stop_reason in ("length", "stop")
    assert fragments[-1].output_tokens <= 5
    engine.close()


def test_ollama_rebuilds_the_rendered_text_from_real_pieces(fake):
    """`ollama_raw` with the real `vocab_only` tokenizer: « É » and « 🙂 » are split across
    byte pieces, the markers are single tokens, and the text sent is the text rendered."""
    engine = servers.OllamaRawEngine(OLLAMA_URL, OLLAMA_NAME, str(TINY), 4096)
    text = "<|im_start|>user\nÉté 🙂 font<|im_end|>\n<|im_start|>assistant\n"
    ids = engine.tokenize(text)
    assert len(ids) < len(text.encode())  # the markers and « on » merged

    list(engine.complete(ids, ["<|im_end|>"], 10, CancelToken()))

    assert fake.posts("/api/generate")[-1]["prompt"] == text
    engine.close()


def test_stop_unblocks_a_real_socket_read():
    """A real loopback socket that stays silent after its headers (Ollama loading a model):
    the cancel watcher shuts the socket down, the blocked read returns at once."""
    import socket as socket_module

    server = socket_module.socket()
    server.bind(("127.0.0.1", 0))
    server.listen(1)
    port = server.getsockname()[1]
    release = threading.Event()

    def serve() -> None:
        conn, _ = server.accept()
        conn.recv(65536)
        conn.sendall(
            b"HTTP/1.1 200 OK\r\nContent-Type: application/x-ndjson\r\n"
            b"Transfer-Encoding: chunked\r\n\r\n"
        )
        release.wait(10)
        conn.close()

    threading.Thread(target=serve, daemon=True).start()
    engine = servers.OllamaRawEngine(
        f"http://127.0.0.1:{port}",
        OLLAMA_NAME,
        None,
        4096,
        tokenizer=ByteTokenizer(),
        unload=False,
        transport=httpx.HTTPTransport(),
    )
    cancel = CancelToken()
    threading.Timer(0.3, cancel.cancel).start()
    started = time.monotonic()
    try:
        fragments = list(engine.complete(tokenize("Bonjour"), [], 10, cancel))
    finally:
        release.set()
        server.close()
    assert time.monotonic() - started < 3
    assert fragments[-1].stop_reason == "cancelled"
    engine.close()


# ---------- lot E: llama-server's context (E1), the refusal with a served model (E3) ----------

TINY = str(Path(__file__).parent / "fixtures" / "tiny-llama.gguf")


def _llama_candidate(fake: FakeServer) -> discovery.ModelCandidate:
    fake.ollama = False
    [candidate] = discovery._server_candidates(
        config.load_config(), transport=httpx.MockTransport(fake)
    )
    return candidate


@pytest.mark.parametrize(
    ("n_ctx", "warned"), [(262_144, True), (4096, False), (6144, False), (6145, True)]
)
def test_llama_server_memory_counts_its_whole_context(fake, n_ctx, warned):
    """E1: its file plus its KV cache for its whole `n_ctx` (the KV read in the GGUF it
    loaded, without the weights), and a warning past 1,5 times the window."""
    fake.n_ctx, fake.model_path = n_ctx, TINY
    size = Path(TINY).stat().st_size

    candidate = _llama_candidate(fake)

    assert candidate.n_ctx == n_ctx and candidate.gguf_path == TINY
    assert candidate.served_bytes == size + 128 * n_ctx and candidate.context_counted
    if warned:
        assert f"lancé avec un contexte de {n_ctx:,} tokens".replace(",", "\u202f") in (
            candidate.warning_fr
        )
        assert candidate.warning_fr.endswith("relancez-le avec `-c 4096`.")
    else:
        assert candidate.warning_fr is None


def test_llama_server_kv_unreadable_counts_the_file_and_keeps_the_warning(fake):
    fake.n_ctx = 262_144  # `model_path` is not on this disk: no KV readable

    candidate = _llama_candidate(fake)

    assert candidate.served_bytes == 2 * GIB  # the size `/v1/models` gives
    assert candidate.context_counted is False  # the page says the cache is left out
    assert "262\u202f144 tokens" in candidate.warning_fr


def test_llama_server_relative_model_path_is_not_read_here(fake, monkeypatch):
    """A relative `model_path` is the server's working directory's, not WaveStack's."""
    monkeypatch.chdir(Path(TINY).parent)
    fake.n_ctx, fake.model_path = 4096, "tiny-llama.gguf"  # readable from here, by chance

    candidate = _llama_candidate(fake)

    assert candidate.served_bytes == 2 * GIB and candidate.context_counted is False


def test_llama_server_with_several_slots_counts_the_whole_context(fake):
    """`-np 4` without `-c`: each slot has a quarter of the native context; the memory is the
    whole context's, and `-c 4096` alone would shrink each slot: `-np 1 -c 4096`."""
    fake.model_path, fake.n_ctx, fake.n_ctx_total = TINY, 65_536, 262_144

    candidate = _llama_candidate(fake)

    assert candidate.n_ctx == 262_144
    assert candidate.served_bytes == Path(TINY).stat().st_size + 128 * 262_144
    assert "65\u202f536 par emplacement, 4 emplacements" in candidate.warning_fr
    assert candidate.warning_fr.endswith("relancez-le avec `-np 1 -c 4096`.")
    fake.n_ctx = 4096  # `-np 4 -c 16384`: each slot fits the window, nothing to advise
    fake.n_ctx_total = 16_384
    assert _llama_candidate(fake).warning_fr is None


def test_hot_switch_to_llama_server_carries_its_warning(monkeypatch, tmp_path, fake):
    fake.n_ctx, fake.model_path = 262_144, TINY
    _, app_session, client = _web_file_loaded(monkeypatch, tmp_path)
    mark = get_journal().last_seq()

    client.post(
        "/api/intentions/select_model",
        json={"kind": "server", "ref": "llama_server/tiny-llama.gguf"},
        headers=ORIGIN,
    )
    app_session.join()

    check = [
        e.payload
        for e in get_journal().events_since(mark)
        if e.kind == "diagnostic_check" and e.payload["check"] == "model"
    ][-1]
    assert check["status"] == "warn" and check["message_fr"].startswith("Modèle actif :")
    assert "relancez-le avec `-c 4096`" in check["message_fr"]


def test_diagnostic_advises_c_4096_for_the_served_model(monkeypatch, tmp_path, fake):
    """E1: the line of the model retained, and the candidate's, say it."""
    fake.ollama, fake.n_ctx, fake.model_path = False, 262_144, TINY
    ref = "llama_server/tiny-llama.gguf"
    config.save_setting("selected_model", {"kind": "server", "ref": ref})
    session = _diagnostic(monkeypatch, tmp_path)
    mark = get_journal().last_seq()

    result = session.check_model()

    assert result.server is not None and result.server.ref == ref
    check = [
        e.payload
        for e in get_journal().events_since(mark)
        if e.kind == "diagnostic_check" and e.payload["check"] == "model"
    ][-1]
    assert check["status"] == "warn" and "servi par llama-server" in check["message_fr"]
    assert "relancez-le avec `-c 4096`" in check["message_fr"]
    assert result.server.warning_fr and result.server.served_bytes > 128 * 262_144


def test_refusal_with_a_served_model_active_counts_wavestack_whole(fake, tmp_path):
    """E3: llama-server's model is in another process: WaveStack's RSS is not reduced by it
    (the refusal said « 0,0 Go »)."""
    blob = tmp_path / "blob"
    with open(blob, "wb") as f:
        f.truncate(5 * GIB)  # sparse: nothing written
    session = _session(rss_fn=lambda: 210 * 1024**2)
    assert session.boot_server(_candidate("llama_server")).result() == "ok"

    with pytest.raises(SendRefused) as refused:
        session.switch_model(ModelChoice.served(_candidate("ollama", str(blob))))

    assert "WaveStack occupe 210 Mo sans le modèle actif" in refused.value.reason_fr
    assert "Qwen3.5-2B-Q4_K_M reste actif" in refused.value.reason_fr


# ---------- story 24: an Ollama model not resident costs its file, its KV and the margin ----------

MIB = 1024**2
# llama3.2:3b's KV cache: 28 layers × 8 KV heads × (128 + 128) × 2 bytes = 112 Kio a token.
LLAMA32_HEADER = {
    "general.architecture": "llama",
    "llama.block_count": 28,
    "llama.attention.head_count": 24,
    "llama.attention.head_count_kv": 8,
    "llama.attention.key_length": 128,
    "llama.attention.value_length": 128,
}
LLAMA32_KV = 112 * 1024


def _ollama_blob(monkeypatch, tmp_path, header: dict | None, size: int) -> Path:
    """The Ollama folder with `OLLAMA_NAME`'s manifest and its blob: a GGUF header (none:
    no KV to read), sparse up to `size` bytes."""
    from gguf_writer import write_gguf

    root = tmp_path / "ollama"
    monkeypatch.setenv("OLLAMA_MODELS", str(root))
    manifest = root / "manifests" / "registry.ollama.ai" / "library" / "qwen3.5" / "2b"
    manifest.parent.mkdir(parents=True)
    blob = root / "blobs" / "sha256-abc"
    blob.parent.mkdir(parents=True)
    if header is None:
        blob.write_bytes(b"GGUF" + b"\0" * 60)
    else:
        write_gguf(blob, header)
    with open(blob, "r+b") as f:
        f.truncate(size)
    layer = {"mediaType": "application/vnd.ollama.image.model", "digest": "sha256:abc"}
    manifest.write_text(json.dumps({"layers": [layer]}), encoding="utf-8")
    return blob


@pytest.mark.parametrize(("header", "kv"), [(LLAMA32_HEADER, LLAMA32_KV), (None, 0)])
def test_ollama_not_resident_costs_file_kv_at_the_window_and_margin(
    monkeypatch, tmp_path, fake, header, kv
):
    """C5: never the probe's RSS of the blob (llama-cpp-python in WaveStack's child, 3,6 Go
    here), but the file, its KV (f16) at the window and the margin: llama3.2:3b (2,0 Go)
    passes under 4 096 Mo with ≈ 150 Mo of base. KV unreadable: the file and the margin."""
    from wavestack.models import probe

    size = 2_000_000_000
    blob = _ollama_blob(monkeypatch, tmp_path, header, size)
    stat = blob.stat()
    probe.record_success(  # the entry a probe of the blob left (lot E)
        probe.ProbeResult(
            ok=True,
            path=str(blob),
            rss_bytes=round(3.6 * GIB),
            size_bytes=stat.st_size,
            mtime=stat.st_mtime,
            kv_bytes_per_token=kv or None,
            probe_version=probe.PROBE_VERSION,
            probe_window=4096,
            rss_eval_tokens=512,
        )
    )
    cfg = config.load_config()
    cfg.values["memory"] = {"budget_mb": 4096, "load_margin_mb": 256}

    [candidate] = [
        c
        for c in discovery._server_candidates(cfg, transport=httpx.MockTransport(fake))
        if c.engine == "ollama"
    ]
    session = AppSession(
        cfg,
        engine_factory=lambda path, n_ctx: FakeEngine(),
        server_factory=_factory(),
        rss_fn=lambda: 150 * MIB,
    )
    assert session.boot("A.gguf").result() == "ok"
    choice = ModelChoice.served(candidate)

    assert not candidate.resident and candidate.gguf_path == str(blob)
    assert candidate.served_bytes == size + kv * 4096  # the diagnostic's line
    assert session._cost(choice) == size + kv * 4096 + 256 * MIB  # the margin at the check
    if kv:
        assert f"{candidate.served_bytes / GIB:.1f}" == "2.3"  # « ≈ 2,3 Go »
        assert f"{session._cost(choice) / GIB:.1f}" == "2.6"
    _, future = session.switch_model(choice)  # never refused: 150 Mo + 2,6 Go ≤ 4 096 Mo
    assert future.result() == "ok"
    assert session.active_model()["label"] == OLLAMA_NAME


def test_ollama_not_resident_blob_unreadable_costs_the_diagnostic_figure(fake):
    """The blob is not readable from here (relative path): the cost is the diagnostic's
    figure (the size Ollama reports) plus the margin, never the margin alone."""
    cfg = config.load_config()
    cfg.values["memory"] = {"budget_mb": 4096, "load_margin_mb": 256}
    session = AppSession(
        cfg,
        engine_factory=lambda path, n_ctx: FakeEngine(),
        server_factory=_factory(),
        rss_fn=lambda: 150 * MIB,
    )
    candidate = _candidate("ollama", "blobs/sha256-abc")
    served = servers.ServedModel(
        engine="ollama",
        server_url=OLLAMA_URL,
        name=OLLAMA_NAME,
        ref=f"ollama/{OLLAMA_NAME}",
        size=2 * GIB,
    )
    candidate.served_bytes = servers.served_bytes(served, candidate.gguf_path, 4096)

    assert candidate.served_bytes == 2 * GIB  # the diagnostic's fallback: Ollama's size
    assert session._cost(ModelChoice.served(candidate)) == 2 * GIB + 256 * MIB
