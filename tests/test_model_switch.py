"""Story 17: hot model switch (CAP-34, AD-3, AD-7, AD-8, AD-17), one test per matrix row.

Two fake engines, a fake cloud adapter, an injected `rss_fn` and an injected probe: no
GGUF, no child process, no network.
"""

from __future__ import annotations

from pathlib import Path

import pytest
from fake_engine import CHATML, FakeEngine
from pydantic import SecretStr
from starlette.testclient import TestClient

from wavestack import config
from wavestack.models import discovery, probe
from wavestack.models.load_registry import LoadRegistry, ModelChoice
from wavestack.session.app_session import _LOAD_FAILED_FR, AppSession, SendRefused
from wavestack.session.diagnostic import DiagnosticSession
from wavestack.trace.journal import get_journal
from wavestack.web.app import create_app

GIB = 1024**3
ORIGIN = {"Origin": "http://127.0.0.1:8420"}
# A second template, so the history rendered by B is recognisably B's (AD-17).
TEMPLATE_B = CHATML.replace("'<|im_start|>' + message.role", "'<|im_start|>[B] ' + message.role")


class Tracker:
    """Engine factory by file stem: records every open and close, and whether two engines
    were ever open at once (AD-8, NFR-2)."""

    def __init__(self, engines: dict[str, FakeEngine], fail: tuple[str, ...] = ()) -> None:
        self.engines, self.fail = engines, set(fail)
        self.open: set[str] = set()
        self.log: list[str] = []
        self.overlap = False

    def factory(self, path: str, n_ctx: int) -> FakeEngine:
        name = Path(path).stem
        self.log.append(f"open {name}")
        self.overlap |= bool(self.open)
        if name in self.fail:
            raise RuntimeError(f"chargement impossible de {name}")
        engine = self.engines[name]
        self.open.add(name)

        def close() -> None:
            self.open.discard(name)
            self.log.append(f"close {name}")

        engine.close = close
        return engine

    def probe(self, path: str, reason: str | None = None):  # noqa: ANN201
        def run(probed: str) -> str | None:
            self.log.append(f"probe {Path(probed).stem}")
            self.overlap |= bool(self.open)
            return reason

        return run


class FakeCloud:
    """The cloud adapter: never asked anything during a switch (AD-21)."""

    def __init__(self, tracker: Tracker) -> None:
        self.tracker = tracker
        tracker.open.add("cloud")
        tracker.log.append("open cloud")

    def close(self) -> None:
        self.tracker.open.discard("cloud")
        self.tracker.log.append("close cloud")


def _files(tmp_path: Path, *names: str) -> dict[str, str]:
    paths = {}
    for name in names:
        path = tmp_path / f"{name}.gguf"
        path.write_bytes(b"placeholder")
        paths[name] = str(path)
    return paths


def _session(tracker: Tracker, *, rss: int = 0, budget_mb: int = 4096, margin_mb: int = 0):
    cfg = config.load_config()
    cfg.values["memory"] = {"budget_mb": budget_mb, "load_margin_mb": margin_mb}
    return AppSession(
        cfg,
        engine_factory=tracker.factory,
        cloud_factory=lambda entry, key: FakeCloud(tracker),
        rss_fn=lambda: rss,
    )


def _booted(tmp_path, engines, **kwargs):
    tracker = Tracker(engines, fail=kwargs.pop("fail", ()))
    paths = _files(tmp_path, *engines)
    session = _session(tracker, **kwargs)
    first = next(iter(engines))
    assert session.boot(paths[first]).result() == "ok"
    return session, tracker, paths


def _events(mark: int, kind: str) -> list[dict]:
    return [e.payload for e in get_journal().events_since(mark) if e.kind == kind]


def _record_probe(path: str, **fields) -> None:
    stat = Path(path).stat()
    probe.record_success(
        probe.ProbeResult(
            ok=True, path=path, size_bytes=stat.st_size, mtime=stat.st_mtime, **fields
        )
    )


def _cloud_entry(model_id: str = "groq"):
    entry = config.load_config().cloud_model(model_id)
    config.write_api_key(entry.id, entry.host, SecretStr("k-test"))
    return entry


def _switch(session: AppSession, choice: ModelChoice, probe_fn=None) -> tuple[str, str | None]:
    message, future = session.switch_model(choice, probe=probe_fn)
    return message, future.result() if future else None


# ---------- matrix rows ----------


def test_local_to_local_probed(tmp_path):
    session, tracker, paths = _booted(tmp_path, {"A": FakeEngine(), "B": FakeEngine()})
    _record_probe(paths["B"])
    mark = get_journal().last_seq()

    message, status = _switch(session, ModelChoice("file", paths["B"]), tracker.probe(paths["B"]))

    assert message == "Chargement de B…" and status == "ok"
    assert tracker.log[-2:] == ["close A", "open B"] and "probe B" not in tracker.log
    states = [p["state"] for p in _events(mark, "session_state")]
    assert states[0] == "model_load" and states[-1] == "idle"
    ended = _events(mark, "model_load_ended")
    assert [(e["model"]["ref"], e["status"]) for e in ended] == [(paths["B"], "ok")]
    for kind in ("bricks_changed", "architecture_changed", "context_preview"):
        assert _events(mark, kind), kind
    model = _events(mark, "architecture_changed")[-1]["nodes"][1]
    assert model["id"] == "core.model" and model["model"] == "B"
    assert config.read_settings()["selected_model"] == {"kind": "file", "ref": paths["B"]}
    assert session.active_model()["kind"] == "file" and session.active_model()["ref"] == paths["B"]


def test_never_probed_gguf_is_probed_after_the_release(tmp_path):
    session, tracker, paths = _booted(tmp_path, {"A": FakeEngine(), "B": FakeEngine()})

    _, status = _switch(session, ModelChoice("file", paths["B"]), tracker.probe(paths["B"]))

    assert status == "ok"
    assert tracker.log[-3:] == ["close A", "probe B", "open B"]
    assert not tracker.overlap  # never two generative models in memory, probe included


def test_probe_records_rss_size_label_and_kv_cache(tmp_path):
    path = _files(tmp_path, "B")["B"]
    meta = {
        "general.architecture": "qwen3",
        "qwen3.block_count": 28,
        "qwen3.attention.head_count": 16,
        "qwen3.attention.head_count_kv": 8,
        "qwen3.embedding_length": 2048,
    }
    kv = probe.kv_bytes_per_token(meta)
    assert kv == 4 * 28 * 8 * 128  # head size from embedding_length / head_count
    assert probe.kv_bytes_per_token({**meta, "qwen3.attention.key_length": 256}) == 4 * 28 * 8 * 256
    assert probe.kv_bytes_per_token({"general.architecture": "x"}) is None

    _record_probe(path, rss_bytes=2 * GIB, size_label="2B", kv_bytes_per_token=kv)

    entry = probe.probed_entry(path)
    assert (entry["rss_bytes"], entry["size_label"], entry["kv_bytes_per_token"]) == (
        2 * GIB,
        "2B",
        kv,
    )


@pytest.mark.parametrize("failure", ["probe", "load"])
def test_probe_or_load_failure_restores_the_previous_model(tmp_path, failure):
    session, tracker, paths = _booted(
        tmp_path,
        {"A": FakeEngine(), "B": FakeEngine()},
        fail=("B",) if failure == "load" else (),
    )
    reason = "Architecture inconnue." if failure == "probe" else None
    mark = get_journal().last_seq()

    _, status = _switch(session, ModelChoice("file", paths["B"]), tracker.probe(paths["B"], reason))

    assert status == "restored"
    assert tracker.log[-1] == "open A" and tracker.open == {"A"}
    assert session.state == "idle" and session.reason_fr is None
    assert session.active_model()["ref"] == paths["A"]
    ended = _events(mark, "model_load_ended")[-1]
    assert ended["status"] == "restored" and "A est de nouveau actif" in ended["reason_fr"]
    error = _events(mark, "harness_error")[-1]
    assert "Retour au modèle précédent : A." in error["effect_fr"]
    assert ("Architecture inconnue." if failure == "probe" else "chargement impossible") in (
        error["cause"]
    )
    assert "selected_model" not in config.read_settings()  # saved after a success only


def test_previous_model_failing_too_leaves_idle_with_the_reason(tmp_path):
    session, tracker, paths = _booted(tmp_path, {"A": FakeEngine(), "B": FakeEngine()})
    tracker.fail = {"A", "B"}
    mark = get_journal().last_seq()

    _, status = _switch(session, ModelChoice("file", paths["B"]))

    assert status == "error" and not session.model_loaded and tracker.open == set()
    assert session.state == "idle" and session.reason_fr == _LOAD_FAILED_FR
    assert _events(mark, "model_load_ended")[-1]["status"] == "error"
    assert session.active_model() is None


def test_budget_exceeded_refuses_before_any_release(tmp_path):
    engines = {"Qwen3.5-2B": FakeEngine(), "Qwen3.5-4B": FakeEngine()}
    tracker = Tracker(engines)
    paths = _files(tmp_path, *engines)
    a_cost = Path(paths["Qwen3.5-2B"]).stat().st_size
    session = _session(tracker, rss=round(1.9 * GIB) + a_cost)
    session.boot(paths["Qwen3.5-2B"]).result()
    _record_probe(paths["Qwen3.5-4B"], rss_bytes=round(3.1 * GIB))
    mark = get_journal().last_seq()

    with pytest.raises(SendRefused) as refused:
        session.switch_model(ModelChoice("file", paths["Qwen3.5-4B"]))

    assert refused.value.reason_fr == (
        "Changement refusé : Qwen3.5-4B demande environ 3,1 Go ; WaveStack occupe 1,9 Go sans "
        "le modèle actif, pour un budget de 4,0 Go. Qwen3.5-2B reste actif. Choisissez un "
        "modèle plus petit."
    )
    assert tracker.open == {"Qwen3.5-2B"} and session.state == "idle"
    assert _events(mark, "harness_error")[-1]["message_fr"] == refused.value.reason_fr
    assert _events(mark, "model_load_started") == []
    assert "selected_model" not in config.read_settings()


def test_local_to_cloud(tmp_path):
    session, tracker, _ = _booted(tmp_path, {"A": FakeEngine()})
    entry = _cloud_entry()

    message, status = _switch(session, ModelChoice("cloud", entry.id, entry))

    assert status == "ok" and message == f"Chargement de {entry.model}…"
    assert tracker.log[-2:] == ["close A", "open cloud"]
    active = session.active_model()
    assert (active["hosting"], active["kind"], active["ref"]) == ("network", "cloud", "groq")
    assert session._window == config.cloud_window(entry, session.cfg.context_window)[0]
    assert config.read_settings()["selected_model"] == {"kind": "cloud", "ref": "groq"}


def test_cloud_without_confirmation_or_key_changes_nothing(monkeypatch, tmp_path):
    session, app_session, client = _web(monkeypatch, tmp_path)
    mark = get_journal().last_seq()

    unconfirmed = client.post(
        "/api/intentions/select_model", json={"kind": "cloud", "ref": "groq"}, headers=ORIGIN
    )
    without_key = client.post(
        "/api/intentions/select_model",
        json={"kind": "cloud", "ref": "groq", "acknowledged": True},
        headers=ORIGIN,
    )

    assert unconfirmed.status_code == 409 and "non confirmé" in unconfirmed.json()["detail"]
    assert without_key.status_code == 409 and "clé" in without_key.json()["detail"].lower()
    assert _events(mark, "model_load_started") == []
    assert app_session.active_model()["kind"] == "file"


def test_cloud_to_local_keeps_the_cloud_ratio(tmp_path):
    tracker = Tracker({"B": FakeEngine()})
    paths = _files(tmp_path, "B")
    session = _session(tracker)
    entry = _cloud_entry()
    session.boot_cloud(entry).result()
    session._ratio = 1.3

    _, status = _switch(session, ModelChoice("file", paths["B"]))

    assert status == "ok" and tracker.log[-2:] == ["close cloud", "open B"]
    assert session.active_model()["hosting"] == "local"
    _switch(session, ModelChoice("cloud", entry.id, entry))
    assert session._ratio == 1.3  # AD-4: kept by cloud model id


@pytest.mark.parametrize("state", ["turn", "awaiting_human", "model_load"])
def test_switch_refused_outside_idle(tmp_path, state):
    session, tracker, paths = _booted(tmp_path, {"A": FakeEngine(), "B": FakeEngine()})
    session.state, session.reason_fr = state, "Occupé pour le test."

    with pytest.raises(SendRefused):
        session.switch_model(ModelChoice("file", paths["B"]))

    assert tracker.open == {"A"} and session.state == state


def test_same_model_is_not_reloaded(tmp_path):
    session, tracker, paths = _booted(tmp_path, {"A": FakeEngine()})
    opened = list(tracker.log)

    message, future = session.switch_model(ModelChoice("file", paths["A"]))

    assert (message, future) == ("A est déjà actif.", None) and tracker.log == opened


def test_lost_capability_leaves_wanted_and_comes_back(tmp_path):
    engines = {"A": FakeEngine(architecture="qwen3"), "B": FakeEngine()}
    session, _, paths = _booted(tmp_path, engines)
    session.set_brick("tools", True)
    assert session._availability("tools") == (True, None)

    _switch(session, ModelChoice("file", paths["B"]))
    available, reason = session._availability("tools")
    assert not available and "appel d'outils" in reason
    card = next(b for b in _events(0, "bricks_changed")[-1]["bricks"] if b["id"] == "tools")
    assert card["wanted"] is True and card["available"] is False

    _switch(session, ModelChoice("file", paths["A"]))
    assert session._availability("tools") == (True, None)


def test_conversation_is_kept_and_replay_plays_the_new_model(tmp_path):
    engines = {"A": FakeEngine(output="Réponse A"), "B": FakeEngine(template=TEMPLATE_B)}
    session, _, paths = _booted(tmp_path, engines)
    session.set_brick("short_memory", True)
    for message in ("Premier", "Second"):
        session.send(message)
        session.join()

    _switch(session, ModelChoice("file", paths["B"]))
    mark = get_journal().last_seq()
    session.send("Troisième")
    session.join()

    prompt = bytes(engines["B"].calls[0]).decode("utf-8")
    assert "[B] user\nPremier" in prompt and "[B] assistant\nRéponse A" in prompt
    assert "[B] user\nSecond" in prompt
    assert _events(mark, "turn_started")[0]["active_model"]["label"] == "B"

    mark = get_journal().last_seq()
    session.replay()
    session.join()
    started = _events(mark, "turn_started")[0]
    assert started["replay_of"] == "t3" and started["active_model"]["ref"] == paths["B"]
    assert len(engines["B"].calls) == 2 and len(engines["A"].calls) == 2


def test_unwritable_settings_keeps_the_switch(monkeypatch, tmp_path):
    session, _, paths = _booted(tmp_path, {"A": FakeEngine(), "B": FakeEngine()})

    def refuse(key, value):
        raise PermissionError("settings.json en lecture seule")

    monkeypatch.setattr(config, "save_setting", refuse)
    mark = get_journal().last_seq()

    _, status = _switch(session, ModelChoice("file", paths["B"]))

    assert status == "ok" and session.active_model()["ref"] == paths["B"]
    ended = _events(mark, "model_load_ended")[-1]
    assert "choix non mémorisé pour les prochains lancements" in ended["reason_fr"]
    assert any("lecture seule" in e["cause"] for e in _events(mark, "harness_error"))


# ---------- load registry, trace, web ----------


def test_load_registry_cost_from_the_probe_cache(tmp_path):
    path = _files(tmp_path, "B")["B"]
    registry = LoadRegistry(4 * GIB, 256 * 1024**2, rss_fn=lambda: 0)
    size = Path(path).stat().st_size

    assert registry.file_cost(path, 4096) == size + 256 * 1024**2  # never probed: its size

    _record_probe(path, rss_bytes=GIB, kv_bytes_per_token=1000)
    assert registry.file_cost(path, 4096) == GIB + 4_096_000 + 256 * 1024**2
    assert registry.check("B", 0) is None  # a cloud model only frees memory
    assert registry.check("B", 5 * GIB).startswith("Changement refusé : B demande environ 5,0 Go")


def test_launch_load_emits_model_load_events_out_of_any_turn(tmp_path):
    mark = get_journal().last_seq()
    _booted(tmp_path, {"A": FakeEngine()})

    events = [e for e in get_journal().events_since(mark) if e.kind.startswith("model_load")]
    assert [e.kind for e in events] == ["model_load_started", "model_load_ended"]
    assert all(e.turn_id is None and e.step_id is None for e in events)
    assert events[0].payload["phase_label"] == "Chargement du modèle A.gguf…"
    assert events[1].payload["status"] == "ok" and events[1].payload["duration_ms"] >= 0


def _web(monkeypatch, tmp_path):
    """The web app with A loaded at launch and B on disk; B's probe always succeeds."""
    monkeypatch.setenv("OLLAMA_MODELS", str(tmp_path / "no-ollama"))
    monkeypatch.setenv("HF_HUB_CACHE", str(tmp_path / "no-hf-cache"))
    monkeypatch.setattr(discovery, "_lm_studio_dirs", lambda: [])
    monkeypatch.setattr(discovery, "_server_candidates", lambda cfg: [])
    config.models_dir().mkdir(parents=True)
    tracker = Tracker({"A": FakeEngine(), "B": FakeEngine()})
    for name in ("A", "B"):
        (config.models_dir() / f"{name}.gguf").write_bytes(b"placeholder")
    config.save_setting(
        "selected_model", {"kind": "file", "ref": str(config.models_dir() / "A.gguf")}
    )
    cfg = config.load_config()
    session = DiagnosticSession(cfg, port=8420)
    monkeypatch.setattr(session, "check_network", lambda: None)
    monkeypatch.setattr(session, "_probe_candidate", lambda candidate: None)
    app_session = _session(tracker)
    app = create_app(session, port=8420, version="test", app_session=app_session)
    session.hand_to(app_session, session.run(), launch=True)
    app_session.join()
    return session, app_session, TestClient(app, base_url="http://127.0.0.1:8420")


def test_web_switch_answers_then_loads_and_diagnostic_reads_the_session(monkeypatch, tmp_path):
    session, app_session, client = _web(monkeypatch, tmp_path)
    b = str(config.models_dir() / "B.gguf")

    answer = client.post(
        "/api/intentions/select_model", json={"kind": "file", "ref": b}, headers=ORIGIN
    )
    app_session.join()

    body = answer.json()
    assert answer.status_code == 200 and body["switching"] is True
    assert body["message_fr"] == "Chargement de B…" and "next_launch" not in body
    diagnostic = client.get("/api/diagnostic").json()
    assert diagnostic["loaded_model"] == b and diagnostic["selected_model"] == b
    assert "next_launch_fr" not in diagnostic
    state = client.get("/api/state").json()
    assert (state["active_model"]["kind"], state["active_model"]["ref"]) == ("file", b)


def test_web_switch_refused_during_a_turn(monkeypatch, tmp_path):
    _, app_session, client = _web(monkeypatch, tmp_path)
    app_session.state, app_session.reason_fr = "turn", "Un tour est en cours."

    answer = client.post(
        "/api/intentions/select_model",
        json={"kind": "file", "ref": str(config.models_dir() / "B.gguf")},
        headers=ORIGIN,
    )

    assert answer.status_code == 409 and "Un tour est en cours." in answer.json()["detail"]
    assert app_session.active_model()["label"] == "A"
