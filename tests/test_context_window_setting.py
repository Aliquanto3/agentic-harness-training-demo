"""Story 26: the context window set in the interface (AD-2, AD-3, AD-8, AD-9), one test per
row of the I/O matrix, plus the pure texts of `context.window` and the route.

Fake engines, synthetic GGUF headers, fake local servers and a fake cloud adapter: no
model, no child process, no network.
"""

from __future__ import annotations

import json
import threading
from pathlib import Path

import httpx
import pytest
from fake_engine import FakeEngine
from gguf_writer import write_gguf
from pydantic import SecretStr
from starlette.testclient import TestClient
from test_model_servers import OLLAMA_NAME, FakeServer, _candidate, _factory

from wavestack import config
from wavestack.context.window import bound_fr, kv_fr, read_time_fr
from wavestack.models import discovery, probe, servers
from wavestack.models.load_registry import LoadRegistry, ModelChoice
from wavestack.session.app_session import AppSession, SendRefused
from wavestack.session.diagnostic import DiagnosticSession
from wavestack.trace.catalog import ContextWindowStatePayload
from wavestack.trace.journal import get_journal
from wavestack.web.app import create_app

GIB = 1024**3
MIB = 1024**2
KV = 112 * 1024  # llama3.2:3b's KV cache, bytes a token (f16)
ORIGIN = {"Origin": "http://127.0.0.1:8420"}
# llama3.2:3b's header: 28 layers × 8 KV heads × (128 + 128) × 2 bytes = 112 Kio a token.
LLAMA32_HEADER = {
    "general.architecture": "llama",
    "llama.block_count": 28,
    "llama.attention.head_count": 24,
    "llama.attention.head_count_kv": 8,
    "llama.attention.key_length": 128,
    "llama.attention.value_length": 128,
}


class Factory:
    """An engine factory that records the `n_ctx` of every engine it opens, and fails (or
    waits on `gate`) for the windows asked."""

    def __init__(self, fail: tuple[int, ...] = (), gate: dict[int, threading.Event] | None = None):
        self.fail, self.gate = set(fail), gate or {}
        self.n_ctx: list[int] = []
        self.entered = threading.Event()

    def __call__(self, path: str, n_ctx: int) -> FakeEngine:
        self.n_ctx.append(n_ctx)
        if n_ctx in self.gate:
            self.entered.set()
            self.gate[n_ctx].wait(5)
        if n_ctx in self.fail:
            raise RuntimeError(f"chargement impossible avec n_ctx={n_ctx}")
        return FakeEngine()


def _session(factory=None, *, rss: int = 150 * MIB, budget_mb: int = 4096, **kwargs) -> AppSession:
    cfg = config.load_config()
    cfg.values["memory"] = {"budget_mb": budget_mb, "load_margin_mb": 0}
    return AppSession(
        cfg,
        engine_factory=factory or Factory(),
        rss_fn=lambda: rss,
        **kwargs,
    )


def _gguf(tmp_path: Path, name: str = "Qwen3.5-2B", *, rss: int = GIB, kv: int | None = KV) -> str:
    """A file measured by the probe (`rss`), its KV cache read (`kv`, `None`: not read)."""
    path = tmp_path / f"{name}.gguf"
    path.write_bytes(b"placeholder")
    stat = path.stat()
    probe.record_success(
        probe.ProbeResult(
            ok=True,
            path=str(path),
            size_bytes=stat.st_size,
            mtime=stat.st_mtime,
            rss_bytes=rss,
            kv_bytes_per_token=kv,
            probe_version=probe.PROBE_VERSION,
            probe_window=4096,
            rss_eval_tokens=0,
        )
    )
    return str(path)


def _booted_file(tmp_path, factory=None, **kwargs) -> tuple[AppSession, str]:
    path = _gguf(tmp_path, rss=kwargs.pop("probe_rss", GIB), kv=kwargs.pop("kv", KV))
    session = _session(factory, **kwargs)
    assert session.boot(path).result() == "ok"
    return session, path


def _events(mark: int, kind: str) -> list[dict]:
    return [e.payload for e in get_journal().events_since(mark) if e.kind == kind]


def _state(session: AppSession) -> dict:
    """The last `context_window_state` (validated on emission by its catalog model)."""
    session.join()
    return _events(0, "context_window_state")[-1]


def _choice(state: dict, window: int) -> dict:
    return next(c for c in state["choices"] if c["window"] == window)


def _apply(session: AppSession, window: int) -> tuple[str, str | None]:
    message, future = session.set_context_window(window)
    status = future.result() if future else None
    session.join()
    return message, status


# ---------- pure texts (context/window.py) ----------


def test_bound_texts_by_source():
    assert bound_fr("configured", 4096) is None
    assert bound_fr("native", 8192) == "bornée à 8 192 par le contexte natif du modèle"
    assert bound_fr("server", 8192) == "bornée à 8 192 par llama-server (-c)"
    assert bound_fr("tpm", 4000) == "bornée à 4 000 par le quota du fournisseur"
    assert bound_fr("override", 2048) == "fixée à 2 048 par la déclaration du modèle"


def test_read_time_texts():
    assert read_time_fr(4096, None) == "pas encore mesuré, envoyez un message"
    assert read_time_fr(4096, 200) == "au moins ≈ 20 s"
    assert read_time_fr(4096, 91) == (
        "au moins ≈ 45 s, au-delà des 30 s visées au premier token (NFR-1)"
    )
    assert read_time_fr(16384, 164) == (
        "au moins ≈ 1 min 40 s, au-delà des 30 s visées au premier token (NFR-1)"
    )
    assert read_time_fr(12000, 100) == (
        "au moins ≈ 2 min, au-delà des 30 s visées au premier token (NFR-1)"
    )
    assert read_time_fr(10, 1000) == "au moins ≈ 1 s"


def test_read_time_compares_the_value_shown():
    assert read_time_fr(4096 * 10, 4096 * 10 / 30.3) == "au moins ≈ 30 s"
    assert read_time_fr(31 * 100, 100) == (
        "au moins ≈ 31 s, au-delà des 30 s visées au premier token (NFR-1)"
    )


@pytest.mark.parametrize(
    ("value", "window"),
    [
        (8192, 8192),
        ("8192", 8192),
        (6000, 6000),
        (0, 4096),
        (-4096, 4096),
        (True, 4096),
        ("abc", 4096),
        (512, 4096),
        (513, 513),
        (None, 4096),
        (float("inf"), 4096),
    ],
)
def test_configured_window_read_from_settings(value, window):
    assert config.Config(values={"context": {"window": value}}).context_window == window


def test_kv_text_in_the_registry_unit():
    assert kv_fr(KV * 8192) == "896 Mo"
    assert kv_fr(KV * 16384) == "1,8 Go"
    assert kv_fr(None) == "inconnu"


def test_check_window_refusal_in_figures():
    registry = LoadRegistry(4 * GIB, 0, rss_fn=lambda: 150 * MIB)
    registry.grant("Qwen3.5-4B", 3 * GIB, share=3 * GIB, base=150 * MIB)
    assert registry.check_window("Qwen3.5-4B", 8192, 4096, 3 * GIB + 448 * MIB) is None
    assert registry.check_window("Qwen3.5-4B", 16384, 4096, 0) is None
    assert registry.check_window("Qwen3.5-4B", 16384, 4096, 3 * GIB + 1344 * MIB) == (
        "Fenêtre de 16 384 tokens refusée : Qwen3.5-4B demanderait environ 4,3 Go ; "
        "WaveStack occupe 150 Mo sans le modèle actif, pour un budget de 4,0 Go. Qwen3.5-4B "
        "reste actif avec 4 096 tokens. Choisissez une fenêtre plus petite."
    )


def test_the_event_is_in_the_catalog():
    payload = {
        "configured": 4096,
        "default": 4096,
        "window": 4096,
        "window_source": "configured",
        "read_note_fr": "…",
        "choices": [
            {
                "window": 4096,
                "effective": 4096,
                "source": "configured",
                "kv_fr": "Cache de contexte : 448 Mo",
                "read_fr": "Temps de lecture : pas encore mesuré, envoyez un message",
                "fits": True,
                "current": True,
            }
        ],
    }
    ContextWindowStatePayload.model_validate(payload)
    with pytest.raises(ValueError):
        ContextWindowStatePayload.model_validate(payload | {"window_source": "ailleurs"})
    with pytest.raises(ValueError):
        ContextWindowStatePayload.model_validate(payload | {"hosting": "network"})


# ---------- I/O matrix ----------


def test_launch_without_setting_shows_the_default_window_and_every_choice(tmp_path):
    session, _ = _booted_file(tmp_path)
    state = _state(session)

    assert (state["configured"], state["default"], state["window"]) == (4096, 4096, 4096)
    assert [c["window"] for c in state["choices"]] == [4096, 8192, 16384]
    assert [c["current"] for c in state["choices"]] == [True, False, False]
    assert _choice(state, 8192)["kv_bytes"] == KV * 8192
    assert _choice(state, 8192)["kv_fr"] == "Cache de contexte : 896 Mo"
    assert all(c["fits"] and c["refusal_fr"] is None for c in state["choices"])
    # Débit inconnu: no local call measured yet.
    assert all(
        c["read_s"] is None
        and c["read_fr"] == "Temps de lecture : pas encore mesuré, envoyez un message"
        for c in state["choices"]
    )
    assert "pas encore mesuré" in state["read_note_fr"]
    assert (state["hosting"], state["model_label"]) == ("file", "Qwen3.5-2B")


def test_local_accepted_reloads_with_the_window_and_keeps_the_conversation(tmp_path):
    factory = Factory()
    session, _ = _booted_file(tmp_path, factory)
    session.send("Bonjour")
    session.join()
    mark = get_journal().last_seq()

    message, status = _apply(session, 8192)

    assert message == "Rechargement de Qwen3.5-2B avec une fenêtre de 8 192 tokens…"
    assert status == "ok" and factory.n_ctx == [4096, 8192]
    started = _events(mark, "model_load_started")
    ended = _events(mark, "model_load_ended")
    assert started[0]["phase_label"] == message and started[0]["window"] == 8192
    assert (ended[0]["status"], ended[0]["reason_fr"]) == (
        "ok",
        "Fenêtre de contexte : 8 192 tokens (conversation gardée).",
    )
    assert len(session._history) == 1  # the conversation is kept (AD-17)
    preview = _events(mark, "context_preview")[-1]
    assert (preview["window"], preview["usable"]) == (8192, 7680)
    assert config.read_settings()["context"] == {"window": 8192}
    assert config.load_config().context_window == 8192  # taken back at the next launch
    state = _state(session)
    assert state["configured"] == 8192 and _choice(state, 8192)["current"]
    assert session.state == "idle" and session.reason_fr is None


def test_saving_keeps_the_other_keys_of_context(tmp_path):
    config.save_setting("context", {"near_limit_ratio": 0.7})
    session, _ = _booted_file(tmp_path)
    _apply(session, 8192)
    assert config.read_settings()["context"] == {"near_limit_ratio": 0.7, "window": 8192}


def test_local_refused_by_the_budget_releases_writes_and_reloads_nothing(tmp_path):
    factory = Factory()
    session, _ = _booted_file(tmp_path, factory, probe_rss=3 * GIB)
    state = _state(session)
    refusal = _choice(state, 16384)["refusal_fr"]
    assert not _choice(state, 16384)["fits"] and _choice(state, 8192)["fits"]
    mark = get_journal().last_seq()

    with pytest.raises(SendRefused) as refused:
        session.set_context_window(16384)

    assert refused.value.reason_fr == refusal
    assert refusal.startswith("Fenêtre de 16 384 tokens refusée : Qwen3.5-2B demanderait")
    assert "pour un budget de 4,0 Go (= plafond [memory] budget_mb)" in refusal
    assert "Qwen3.5-2B reste actif avec 4 096 tokens." in refusal
    assert factory.n_ctx == [4096] and session.state == "idle"
    assert _events(mark, "model_load_started") == []
    assert _events(mark, "harness_error")[-1]["message_fr"] == refusal
    assert "context" not in config.read_settings()
    assert session.configured_window == 4096 and session._window == 4096


def test_a_file_whose_probe_missed_the_kv_counts_it_from_its_header(tmp_path):
    """A file probed without `kv_bytes_per_token`: its header's KV for the tokens beyond the
    probe's window, one rule for the check and the grant."""
    factory = Factory()
    session = _session(factory)
    path = tmp_path / "Llama-3.2-3B.gguf"
    write_gguf(path, LLAMA32_HEADER)
    stat = path.stat()
    probe.record_success(
        probe.ProbeResult(
            ok=True,
            path=str(path),
            size_bytes=stat.st_size,
            mtime=stat.st_mtime,
            rss_bytes=GIB,
            probe_version=probe.PROBE_VERSION,
            probe_window=4096,
            rss_eval_tokens=0,
        )
    )
    choice = ModelChoice("file", str(path))
    assert session._cost(choice, 8192) == session._cost(choice, 4096) + KV * 4096
    assert session._reload_cost(choice, 8192) == session._cost(choice, 8192)
    assert session.boot(str(path)).result() == "ok"
    _, status = _apply(session, 8192)
    assert status == "ok"
    granted = session._load_registry._slots["generative"].cost
    assert granted == session._reload_cost(session.active_choice(), 8192)


def test_reload_failure_brings_the_same_model_back_with_its_window(tmp_path):
    factory = Factory(fail=(16384,))
    session, _ = _booted_file(tmp_path, factory)
    mark = get_journal().last_seq()

    _, status = _apply(session, 16384)

    assert status == "restored" and factory.n_ctx == [4096, 16384, 4096]
    reason = _events(mark, "model_load_ended")[-1]["reason_fr"]
    assert reason.startswith("Fenêtre de 16 384 tokens non appliquée (")
    assert reason.endswith(": Qwen3.5-2B est de nouveau actif avec 4 096 tokens.")
    assert "context" not in config.read_settings()
    assert (session.configured_window, session._window) == (4096, 4096)
    assert session.active_model()["label"] == "Qwen3.5-2B"


def test_stop_during_the_reload_brings_the_old_window_back(tmp_path):
    gate = threading.Event()
    factory = Factory(gate={16384: gate})
    session, _ = _booted_file(tmp_path, factory)
    mark = get_journal().last_seq()

    _, future = session.set_context_window(16384)
    assert factory.entered.wait(5) and session.state == "model_load"
    assert session.stop() is True
    gate.set()

    assert future.result() == "cancelled"
    assert factory.n_ctx == [4096, 16384, 4096]
    ended = _events(mark, "model_load_ended")[-1]
    assert (ended["status"], ended["reason_fr"]) == (
        "cancelled",
        "Rechargement arrêté : Qwen3.5-2B est de nouveau actif avec 4 096 tokens.",
    )
    assert "context" not in config.read_settings() and session.configured_window == 4096


def test_same_window_is_not_reloaded(tmp_path):
    factory = Factory()
    session, _ = _booted_file(tmp_path, factory)
    assert session.set_context_window(4096) == ("La fenêtre est déjà de 4 096 tokens.", None)
    assert factory.n_ctx == [4096]


@pytest.mark.parametrize("state", ["turn", "model_load", "awaiting_human"])
def test_refused_outside_idle(tmp_path, state):
    session, _ = _booted_file(tmp_path)
    session.state, session.reason_fr = state, None
    with pytest.raises(SendRefused) as refused:
        session.set_context_window(8192)
    assert refused.value.reason_fr == session._refusal_reason()
    assert "context" not in config.read_settings()


def test_no_model_saves_the_window_for_the_next_load(tmp_path):
    factory = Factory()
    session = _session(factory)
    assert session.boot(None).result() == "error"  # idle, no model

    message, future = session.set_context_window(8192)
    session.join()

    assert future is None and "s'appliquera au prochain chargement" in message
    assert config.read_settings()["context"] == {"window": 8192}
    state = _state(session)
    assert (state["configured"], state["hosting"], state["model_label"]) == (8192, None, None)
    assert _choice(state, 8192)["current"]
    assert session.boot(_gguf(tmp_path)).result() == "ok"
    assert factory.n_ctx == [8192] and session._window == 8192


def test_overflow_names_the_new_window(tmp_path):
    session, _ = _booted_file(tmp_path)
    _apply(session, 8192)
    mark = get_journal().last_seq()
    session.send("x" * 9000)
    session.join()
    [overflow] = _events(mark, "context_overflow")
    assert overflow["usable"] == 7680
    assert "(fenêtre de 8 192 moins 512 réservés à la réponse)" in overflow["message_fr"]


def test_the_read_rate_is_measured_on_a_local_call(tmp_path):
    engine = FakeEngine(delay=0.02)
    session = _session(lambda path, n_ctx: engine)
    assert session.boot(_gguf(tmp_path)).result() == "ok"
    for _ in range(2):  # the first call after the load warms it up: never measured
        session.send("Bonjour, lis ce message assez long pour dépasser soixante-quatre tokens.")
        session.join()
        if not session._read_tps:
            assert _state(session)["read_tps"] is None

    state = _state(session)
    tps = state["read_tps"]
    assert tps and tps > 0
    for choice in state["choices"]:
        assert choice["read_s"] == pytest.approx(choice["effective"] / tps, abs=0.06)
        assert choice["read_fr"].startswith("Temps de lecture : au moins ≈ ")
    assert "tokens/s" in state["read_note_fr"]


def test_a_short_call_is_no_measure(tmp_path):
    session, _ = _booted_file(tmp_path)
    session._note_read_rate(640, 1000)  # the first call after the load: warm-up
    session._note_read_rate(63, 100)
    session._note_read_rate(640, 0)
    session._note_read_rate(None, 1000)  # evaluated unknown: the cache may have served it
    assert session._read_tps == {}
    session._note_read_rate(640, 1000)
    assert session._read_tps == {"Qwen3.5-2B": 640.0}
    _apply(session, 8192)  # a reload: its first call is warm-up again
    session._read_tps.clear()
    session._note_read_rate(640, 1000)
    assert session._read_tps == {}


def test_shrinking_is_never_refused(tmp_path):
    """RSS grew past the budget: a larger window is refused, a smaller one only frees."""
    config.save_setting("context", {"window": 8192})
    factory = Factory()
    session, _ = _booted_file(tmp_path, factory, probe_rss=3 * GIB, rss=5 * GIB)
    state = _state(session)
    assert _choice(state, 4096)["fits"] and not _choice(state, 16384)["fits"]
    assert "reste actif avec 8\u202f192 tokens" in _choice(state, 16384)["refusal_fr"]
    _, status = _apply(session, 4096)
    assert status == "ok" and factory.n_ctx == [8192, 4096]


def test_reset_keeps_the_window(tmp_path):
    session, _ = _booted_file(tmp_path)
    _apply(session, 8192)
    session.reset()
    session.join()
    assert session.configured_window == 8192 and session._window == 8192
    assert config.read_settings()["context"] == {"window": 8192}


# ---------- served models ----------


@pytest.fixture
def fake(monkeypatch) -> FakeServer:
    server = FakeServer()
    monkeypatch.setattr(servers, "default_transport", httpx.MockTransport(server))
    return server


def _llama(fake, **kwargs) -> tuple[AppSession, object]:
    fake.ollama, fake.n_ctx = False, 8192
    [candidate] = discovery._server_candidates(
        config.load_config(), transport=httpx.MockTransport(fake)
    )
    session = _session(server_factory=_factory(), **kwargs)
    assert session.boot_server(candidate).result() == "ok"
    return session, candidate


def test_llama_server_same_effective_window_saves_without_reloading(fake):
    """-c 8192 and a window of 8 192: 16 384 would still be 8 192, nothing reloads."""
    config.save_setting("context", {"window": 8192})
    session, _ = _llama(fake)
    mark = get_journal().last_seq()

    message, status = _apply(session, 16384)

    assert status is None and "sans rechargement" in message
    assert "reste de 8\u202f192 tokens (bornée à 8\u202f192 par llama-server (-c))" in message
    assert _events(mark, "model_load_started") == []
    assert (session.configured_window, session._window) == (16384, 8192)
    assert session._window_source == "server"
    assert config.read_settings()["context"] == {"window": 16384}
    assert _state(session)["configured"] == 16384


def test_llama_server_is_never_checked_against_the_budget(fake):
    """Its memory (2 Gio here) is fixed by its -c: a small budget refuses no window."""
    session, candidate = _llama(fake, budget_mb=512)
    candidate.served_bytes = 2 * GIB
    state = _state(session)
    assert all(c["fits"] and c["refusal_fr"] is None for c in state["choices"])
    _, status = _apply(session, 16384)
    assert status == "ok" and session._window == 8192


def test_llama_server_bounds_the_choice_by_its_context(fake):
    fake.ollama, fake.n_ctx = False, 8192
    [candidate] = discovery._server_candidates(
        config.load_config(), transport=httpx.MockTransport(fake)
    )
    session = _session(server_factory=_factory())
    assert session.boot_server(candidate).result() == "ok"
    state = _state(session)

    choice = _choice(state, 16384)
    assert (choice["effective"], choice["source"]) == (8192, "server")
    assert choice["bound_fr"] == "bornée à 8 192 par llama-server (-c)"
    assert choice["kv_fr"] == "Cache de contexte : réservé par llama-server (-c 8 192), inchangé"
    assert choice["fits"] and choice["kv_bytes"] is None

    _, status = _apply(session, 16384)  # never checked against the budget: its -c fixed it
    assert status == "ok"
    assert (session._window, session._window_source) == (8192, "server")
    assert config.read_settings()["context"] == {"window": 16384}
    preview = _events(0, "context_preview")[-1]
    assert (preview["window"], preview["window_source"]) == (8192, "server")


def _ollama_blob(monkeypatch, tmp_path, header: dict | None, size: int) -> Path:
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


@pytest.mark.parametrize(("header", "kv"), [(LLAMA32_HEADER, KV), (None, 0)])
@pytest.mark.parametrize("resident", [False, True])
def test_ollama_reloads_at_the_new_num_ctx_and_costs_its_kv(
    monkeypatch, tmp_path, fake, header, kv, resident
):
    """Ollama loads the model again at its new `num_ctx`: the file, its KV (f16) at the new
    window and the margin, even when it holds it already; KV unreadable: file and margin."""
    size = 2_000_000_000
    blob = _ollama_blob(monkeypatch, tmp_path, header, size)
    cfg = config.load_config()
    cfg.values["memory"] = {"budget_mb": 4096, "load_margin_mb": 256}
    session = AppSession(cfg, server_factory=_factory(), rss_fn=lambda: 150 * MIB)
    candidate = _candidate("ollama", str(blob), resident=resident)
    candidate.served_bytes = 1 * GIB  # what `/api/ps` or the diagnostic said, at 4 096
    choice = ModelChoice.served(candidate)
    assert session.boot_server(candidate).result() == "ok"

    assert session._reload_cost(choice, 8192) == size + kv * 8192 + 256 * MIB
    state = _state(session)
    assert _choice(state, 8192)["kv_fr"] == (
        "Cache de contexte : 896 Mo" if kv else "Cache de contexte : inconnu"
    )
    _, status = _apply(session, 8192)
    assert status == "ok" and session._engine.num_ctx == 8192
    assert session.active_model()["label"] == OLLAMA_NAME


def test_ollama_reload_cost_unknown_is_refused(fake):
    """A blob WaveStack cannot read: the reload's cost is unknown, never the margin alone."""
    session = AppSession(config.load_config(), server_factory=_factory(), rss_fn=lambda: 150 * MIB)
    candidate = _candidate("ollama", "blobs/sha256-abc", resident=True)
    assert session.boot_server(candidate).result() == "ok"
    assert session._reload_cost(ModelChoice.served(candidate), 8192) is None
    refusal = _choice(_state(session), 8192)["refusal_fr"]
    assert "coût" in refusal and "inconnu" in refusal
    with pytest.raises(SendRefused) as refused:
        session.set_context_window(8192)
    assert refused.value.reason_fr == refusal and session.configured_window == 4096


def test_ollama_cost_after_a_window_set_without_model(monkeypatch, tmp_path, fake):
    """No model active, 8 192 saved: an Ollama model not loaded yet costs its file and its
    KV at 8 192 plus the margin, not the launch's figure (at 4 096)."""
    size = 2_000_000_000
    blob = _ollama_blob(monkeypatch, tmp_path, LLAMA32_HEADER, size)
    cfg = config.load_config()
    cfg.values["memory"] = {"budget_mb": 4096, "load_margin_mb": 256}
    session = AppSession(cfg, server_factory=_factory(), rss_fn=lambda: 150 * MIB)
    assert session.boot(None).result() == "error"
    candidate = _candidate("ollama", str(blob))
    candidate.served_bytes = size + KV * 4096  # the diagnostic's line, at the launch window
    choice = ModelChoice.served(candidate)
    assert session._cost(choice) == size + KV * 4096 + 256 * MIB
    session.set_context_window(8192)
    assert session._cost(choice) == size + KV * 8192 + 256 * MIB


# ---------- cloud ----------


class FakeCloud:
    def close(self) -> None:
        pass


def _cloud(**fields) -> AppSession:
    entry = config.CloudModel.model_validate(
        {
            "id": "essai",
            "provider": "Fournisseur",
            "base_url": "https://api.example.test/v1",
            "model": "modele-essai",
            "context": 32768,
            "hosting_fr": "Ailleurs",
            "training": "no",
            **fields,
        }
    )
    config.write_api_key(entry.id, entry.host, SecretStr("k-test"))
    factory = Factory()
    session = _session(factory, cloud_factory=lambda entry, key: FakeCloud())
    assert session.boot_cloud(entry).result() == "ok"
    session.factory = factory  # type: ignore[attr-defined]
    return session


def test_cloud_takes_the_window_at_the_next_turn_without_reloading():
    session = _cloud()
    state = _state(session)
    assert all(
        c["kv_fr"] == "Cache de contexte : chez le fournisseur, aucune mémoire sur ce poste"
        and c["read_s"] is None
        for c in state["choices"]
    )
    mark = get_journal().last_seq()

    message, status = _apply(session, 8192)

    assert status is None and "sans rechargement" in message
    assert _events(mark, "model_load_started") == [] and session.factory.n_ctx == []
    preview = _events(mark, "context_preview")[-1]
    assert (preview["window"], preview["usable"]) == (8192, 7680)
    assert config.read_settings()["context"] == {"window": 8192}
    assert _state(session)["window"] == 8192


def test_cloud_bounded_by_its_quota():
    session = _cloud(tpm=8000)
    state = _state(session)
    assert all(
        c["effective"] == 4000
        and c["source"] == "tpm"
        and c["bound_fr"] == "bornée à 4 000 par le quota du fournisseur"
        for c in state["choices"]
    )


def test_cloud_with_a_declared_window_cannot_be_set():
    session = _cloud(window=2048)
    state = _state(session)
    assert state["locked_fr"] and "fenêtre fixée par la déclaration du modèle" in state["locked_fr"]
    assert all(
        c["bound_fr"] == "fixée à 2 048 par la déclaration du modèle" for c in state["choices"]
    )
    with pytest.raises(SendRefused) as refused:
        session.set_context_window(8192)
    assert refused.value.reason_fr == state["locked_fr"]
    assert "context" not in config.read_settings()
    # The route: a 409 with the same reason.
    diagnostic = DiagnosticSession(config.load_config(), port=8420)
    client = TestClient(
        create_app(diagnostic, port=8420, version="test", app_session=session),
        base_url="http://127.0.0.1:8420",
    )
    answer = client.post("/api/intentions/context_window", json={"window": 8192}, headers=ORIGIN)
    assert answer.status_code == 409 and answer.json()["detail"] == state["locked_fr"]


# ---------- the route ----------


def _web(monkeypatch, tmp_path):
    monkeypatch.setenv("OLLAMA_MODELS", str(tmp_path / "no-ollama"))
    monkeypatch.setenv("HF_HUB_CACHE", str(tmp_path / "no-hf-cache"))
    monkeypatch.setattr(discovery, "_lm_studio_dirs", lambda: [])
    monkeypatch.setattr(discovery, "_server_candidates", lambda cfg: [])
    config.models_dir().mkdir(parents=True)
    path = config.models_dir() / "A.gguf"
    path.write_bytes(b"placeholder")
    config.save_setting("selected_model", {"kind": "file", "ref": str(path)})
    cfg = config.load_config()
    session = DiagnosticSession(cfg, port=8420)
    monkeypatch.setattr(session, "check_network", lambda: None)
    monkeypatch.setattr(session, "_probe_candidate", lambda candidate, cancel=None: None)
    app_session = _session()
    app = create_app(session, port=8420, version="test", app_session=app_session)
    session.hand_to(app_session, session.run(), launch=True)
    app_session.join()
    return app_session, TestClient(app, base_url="http://127.0.0.1:8420")


def test_route_applies_refuses_and_validates(monkeypatch, tmp_path):
    app_session, client = _web(monkeypatch, tmp_path)
    post = lambda body: client.post(  # noqa: E731
        "/api/intentions/context_window", json=body, headers=ORIGIN
    )

    answer = post({"window": 8192})
    app_session.join()
    assert answer.status_code == 200
    assert answer.json() == {
        "switching": True,
        "message_fr": "Rechargement de A avec une fenêtre de 8 192 tokens…",
    }
    assert app_session.configured_window == 8192
    state = client.get("/api/state").json()["context_window_state"]
    assert state["configured"] == 8192
    # Story 25's table: the window configured now, not the launch's.
    rows = [
        m for g in client.get("/api/diagnostic").json()["models"]["groups"] for m in g["models"]
    ]
    assert next(m for m in rows if m["value"] == "cloud:mistral")["window"] == 8192

    invalid = post({"window": 5000})
    assert invalid.status_code == 422 and invalid.json()["detail"].startswith("Intention invalide")

    app_session.state, app_session.reason_fr = "turn", "Un tour est en cours."
    busy = post({"window": 16384})
    assert busy.status_code == 409 and "Un tour est en cours." in busy.json()["detail"]
    assert app_session.configured_window == 8192
