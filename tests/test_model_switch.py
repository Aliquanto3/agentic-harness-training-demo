"""Story 17: hot model switch (CAP-34, AD-3, AD-7, AD-8, AD-17), one test per matrix row.

Two fake engines, a fake cloud adapter, an injected `rss_fn` and an injected probe: no
GGUF, no child process, no network.
"""

from __future__ import annotations

import threading
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
    """A successful probe of lot E (version 2), which measured the model (`rss_bytes`) with a
    context of `probe_window` tokens (0 by default here: the whole KV counted apart)."""
    fields.setdefault("rss_bytes", 1)
    fields.setdefault("probe_version", probe.PROBE_VERSION)
    fields.setdefault("probe_window", 0)
    fields.setdefault("rss_eval_tokens", 0)
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
    session, app_session, client, _ = _web(monkeypatch, tmp_path)
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
    assert _events(mark, "prefix_not_reused") == []  # lot A: a new engine, nothing cached

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
    # Lot E (E2): llama.cpp cleared the KV of the probe's whole context: in its RSS already.
    _record_probe(path, rss_bytes=GIB, kv_bytes_per_token=1000, probe_window=4096)
    assert registry.file_cost(path, 4096) == GIB + 256 * 1024**2
    _record_probe(path, rss_bytes=GIB, kv_bytes_per_token=1000, probe_window=1024)
    assert registry.file_cost(path, 4096) == GIB + 3_072_000 + 256 * 1024**2  # the rest only
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


def _web(monkeypatch, tmp_path, **session_kwargs):
    """The web app with A loaded at launch and B on disk; B's probe always succeeds.
    Returns the diagnostic session, the application session, a client and the tracker."""
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
    app_session = _session(tracker, **session_kwargs)
    app = create_app(session, port=8420, version="test", app_session=app_session)
    session.hand_to(app_session, session.run(), launch=True)
    app_session.join()
    return session, app_session, TestClient(app, base_url="http://127.0.0.1:8420"), tracker


def test_web_switch_answers_then_loads_and_diagnostic_reads_the_session(monkeypatch, tmp_path):
    session, app_session, client, _ = _web(monkeypatch, tmp_path)
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
    _, app_session, client, _ = _web(monkeypatch, tmp_path)
    app_session.state, app_session.reason_fr = "turn", "Un tour est en cours."

    answer = client.post(
        "/api/intentions/select_model",
        json={"kind": "file", "ref": str(config.models_dir() / "B.gguf")},
        headers=ORIGIN,
    )

    assert answer.status_code == 409 and "Un tour est en cours." in answer.json()["detail"]
    assert app_session.active_model()["label"] == "A"


# ---------- independent review of story 17 ----------


def _probe_child(monkeypatch, session: DiagnosticSession, result: dict) -> list[str]:
    """The real `_probe_candidate`, its child process answering `result` (`ok`, `reason`...)."""
    from wavestack.session import diagnostic as diagnostic_module

    monkeypatch.setattr(
        session, "_probe_candidate", DiagnosticSession._probe_candidate.__get__(session)
    )
    probed: list[str] = []

    class _Done:
        returncode = 0 if result.get("ok") else 1

        def __init__(self, path: str) -> None:
            self.stdout = probe.ProbeResult(path=path, **result).model_dump_json()

    def run(cmd, **kwargs):  # noqa: ANN001, ANN202
        probed.append(cmd[-1])
        return _Done(cmd[-1])

    monkeypatch.setattr(diagnostic_module.subprocess, "run", run)
    return probed


def test_web_probe_failure_marks_the_candidate_and_restores(monkeypatch, tmp_path):
    session, app_session, client, tracker = _web(monkeypatch, tmp_path)
    probed = _probe_child(monkeypatch, session, {"ok": False, "reason": "Architecture inconnue."})
    b = str(config.models_dir() / "B.gguf")
    mark = get_journal().last_seq()

    answer = client.post("/api/intentions/select_model", json={"ref": b}, headers=ORIGIN)
    app_session.join()

    assert answer.status_code == 200 and answer.json()["ref"] == b and probed == [b]
    assert _events(mark, "model_load_ended")[-1]["status"] == "restored"
    assert app_session.active_model()["label"] == "A" and tracker.open == {"A"}
    listed = next(c for c in client.get("/api/diagnostic").json()["candidates"] if c["path"] == b)
    assert (listed["status"], listed["reason"]) == ("incompatible", "Architecture inconnue.")


def test_web_refusal_reaches_the_session_lock(monkeypatch, tmp_path):
    """`_diagnostic_class_b` lets `diagnostic` through; the switch itself refuses it."""
    session, app_session, client, _ = _web(monkeypatch, tmp_path)
    assert session.handed_out
    app_session.state, app_session.reason_fr = "diagnostic", "Diagnostic de démarrage en cours."

    answer = client.post(
        "/api/intentions/select_model",
        json={"ref": str(config.models_dir() / "B.gguf")},
        headers=ORIGIN,
    )

    assert answer.status_code == 409
    assert answer.json()["detail"] == "Diagnostic de démarrage en cours."
    assert app_session.active_model()["label"] == "A"


def test_web_budget_refusal_is_a_409_in_figures(monkeypatch, tmp_path):
    session, app_session, client, tracker = _web(monkeypatch, tmp_path, rss=round(3.9 * GIB))
    b = str(config.models_dir() / "B.gguf")
    _record_probe(b, rss_bytes=GIB)

    answer = client.post("/api/intentions/select_model", json={"ref": b}, headers=ORIGIN)

    assert answer.status_code == 409
    assert answer.json()["detail"].startswith("Changement refusé : B demande environ 1,0 Go")
    assert "A reste actif." in answer.json()["detail"] and tracker.open == {"A"}


def test_relaunch_after_a_switch_loads_the_new_model(monkeypatch, tmp_path):
    _, app_session, client, _ = _web(monkeypatch, tmp_path)
    b = str(config.models_dir() / "B.gguf")
    client.post("/api/intentions/select_model", json={"ref": b}, headers=ORIGIN)
    app_session.join()

    relaunched = DiagnosticSession(config.load_config(), port=8420)
    monkeypatch.setattr(relaunched, "_probe_candidate", lambda candidate: None)
    assert relaunched.check_model().model_path == b

    entry = _cloud_entry()
    client.post(
        "/api/intentions/select_model",
        json={"kind": "cloud", "ref": entry.id, "acknowledged": True},
        headers=ORIGIN,
    )
    app_session.join()
    relaunched = DiagnosticSession(config.load_config(), port=8420)
    monkeypatch.setattr(relaunched, "_probe_candidate", lambda candidate: None)
    result = relaunched.check_model()  # AD-21: no warning, no request at a relaunch
    assert result.cloud_model is not None and result.cloud_model.id == entry.id


def test_budget_subtracts_the_active_model():
    registry = LoadRegistry(4 * GIB, 0, rss_fn=lambda: 3 * GIB)
    registry.grant("A", 2 * GIB)

    assert registry.check("B", round(2.5 * GIB)) is None  # 3 − 2 + 2,5 = 3,5 ≤ 4
    refusal = registry.check("B", round(3.1 * GIB))  # 3 − 2 + 3,1 = 4,1 > 4
    assert "WaveStack occupe 1,0 Go sans le modèle actif" in refusal
    assert refusal.endswith("A reste actif. Choisissez un modèle plus petit.")


def test_cloud_ratio_is_kept_per_model(tmp_path):
    session = _session(Tracker({}))
    groq, mistral = _cloud_entry("groq"), _cloud_entry("mistral")
    session.boot_cloud(groq).result()
    session._ratio = 1.3

    _switch(session, ModelChoice("cloud", mistral.id, mistral))
    assert session._ratio == session.cfg.estimate_ratio
    _switch(session, ModelChoice("cloud", groq.id, groq))
    assert session._ratio == 1.3


def test_probe_entry_without_measure_is_probed_again(tmp_path):
    session, tracker, paths = _booted(tmp_path, {"A": FakeEngine(), "B": FakeEngine()})
    stat = Path(paths["B"]).stat()
    probe.record_success(  # written before story 17: no `rss_bytes`
        probe.ProbeResult(ok=True, path=paths["B"], size_bytes=stat.st_size, mtime=stat.st_mtime)
    )
    assert probe.probed_entry(paths["B"]) is not None and not probe.measured(paths["B"])

    _, status = _switch(session, ModelChoice("file", paths["B"]), tracker.probe(paths["B"]))

    assert status == "ok" and "probe B" in tracker.log


def test_probe_measures_the_model_share_of_rss(monkeypatch, tmp_path):
    """Lot E (E2): loaded at the window and the engine's batch, then one full batch of a
    neutral prompt evaluated; the RSS peak (Windows: `peak_wset`) read after it."""
    import sys
    import types

    path = _files(tmp_path, "B")["B"]
    rss = iter([400, 1400])  # before `Llama(...)`, then after the evaluation
    loaded: dict = {}

    class _Memory:
        def __init__(self) -> None:
            self.rss = next(rss)
            self.peak_wset = 1600 if self.rss == 1400 else None  # the peak, in the evaluation

    class _Process:
        def __init__(self, pid: int) -> None:
            pass

        def memory_info(self) -> _Memory:
            return _Memory()

    class _Llama:
        metadata = {"general.architecture": "qwen3", "general.size_label": "2B"}
        n_batch = 512

        def __init__(self, **kwargs) -> None:
            loaded.update(kwargs)

        def tokenize(self, text: bytes, add_bos: bool, special: bool) -> list[int]:
            return list(range(7))

        def eval(self, tokens: list[int]) -> None:
            loaded["evaluated"] = len(tokens)

        def close(self) -> None:
            pass

    monkeypatch.setitem(sys.modules, "llama_cpp", types.SimpleNamespace(Llama=_Llama))
    monkeypatch.setattr(probe.psutil, "Process", _Process)
    monkeypatch.setattr(probe, "_os_peak_rss", lambda: None)

    result = probe.probe_file(path, window=4096)

    assert result.ok and result.rss_bytes == 1200 and result.size_label == "2B"
    assert loaded["n_ctx"] == 4096 and "n_batch" not in loaded  # the engine's own batch
    assert loaded["evaluated"] == 512 and result.rss_eval_tokens == 512
    assert result.probe_version == probe.PROBE_VERSION == 2


def test_kv_cache_per_layer_and_value_length():
    base = {
        "general.architecture": "qwen35",
        "qwen35.block_count": 4,
        "qwen35.attention.head_count": 16,
        "qwen35.attention.key_length": 256,
    }
    # Hybrid: KV heads per layer (0 on the linear-attention layers).
    per_layer = {**base, "qwen35.attention.head_count_kv": [0, 0, 0, 4]}
    assert probe.kv_bytes_per_token(per_layer) == 2 * 4 * (256 + 256)
    with_value = {
        **base,
        "qwen35.attention.head_count_kv": 2,
        "qwen35.attention.value_length": 128,
    }
    assert probe.kv_bytes_per_token(with_value) == 2 * (4 * 2) * (256 + 128)
    # An array shown as text: unknown, never the attention heads instead.
    as_text = {**base, "qwen35.attention.head_count_kv": "arr[i32,4]"}
    assert probe.kv_bytes_per_token(as_text) is None


@pytest.mark.parametrize("step", ["capabilities", "cloud_window"])
def test_a_failure_after_the_factory_closes_the_new_engine(monkeypatch, tmp_path, step):
    from wavestack.session import app_session as module

    session, tracker, paths = _booted(tmp_path, {"A": FakeEngine(), "B": FakeEngine()})

    def boom(*args, **kwargs):  # noqa: ANN002, ANN003, ANN202
        raise RuntimeError("étape en panne")

    if step == "capabilities":
        real = module.capabilities_for
        monkeypatch.setattr(
            module,
            "capabilities_for",
            lambda meta: boom() if tracker.log[-1] == "open B" else real(meta),
        )
        choice = ModelChoice("file", paths["B"])
    else:
        monkeypatch.setattr(config, "cloud_window", boom)
        entry = _cloud_entry()
        choice = ModelChoice("cloud", entry.id, entry)

    _, status = _switch(session, choice)

    assert status == "restored" and not tracker.overlap
    assert tracker.open == {"A"}  # the new engine was closed before A came back


def test_any_save_failure_keeps_the_loaded_model(monkeypatch, tmp_path):
    session, _, paths = _booted(tmp_path, {"A": FakeEngine(), "B": FakeEngine()})

    def refuse(key, value):
        raise ValueError("réglage refusé")

    monkeypatch.setattr(config, "save_setting", refuse)

    _, status = _switch(session, ModelChoice("file", paths["B"]))

    assert status == "ok" and session.active_model()["label"] == "B"


def test_unsaved_switch_is_not_shown_as_the_saved_choice(monkeypatch, tmp_path):
    session, app_session, client, _ = _web(monkeypatch, tmp_path)
    a, b = (str(config.models_dir() / f"{n}.gguf") for n in "AB")

    def refuse(key, value):
        raise PermissionError("settings.json en lecture seule")

    monkeypatch.setattr(config, "save_setting", refuse)
    mark = get_journal().last_seq()
    client.post("/api/intentions/select_model", json={"ref": b}, headers=ORIGIN)
    app_session.join()

    diagnostic = client.get("/api/diagnostic").json()
    assert diagnostic["loaded_model"] == b and diagnostic["selected_model"] == a
    check = [c for c in _events(mark, "diagnostic_check") if c["check"] == "model"][-1]
    assert check["status"] == "warn" and "non mémorisé" in check["message_fr"]


def test_ollama_blob_is_named_by_its_tag(tmp_path):
    choice = ModelChoice("file", str(tmp_path / "sha256-abcd"), name="qwen3.5:2b")
    assert choice.label == "qwen3.5:2b" and choice.file_name == "qwen3.5:2b"
    assert ModelChoice("file", "/m/Qwen-B.gguf", name="Qwen-B.gguf").label == "Qwen-B"

    tracker = Tracker({"sha256-abcd": FakeEngine()})
    path = tmp_path / "sha256-abcd"
    path.write_bytes(b"placeholder")
    session = _session(tracker)
    session.boot(str(path), "qwen3.5:2b").result()
    assert session.active_model()["label"] == "qwen3.5:2b"


def test_a_failing_close_still_releases_and_restores(tmp_path):
    session, tracker, paths = _booted(tmp_path, {"A": FakeEngine(), "B": FakeEngine()})
    engine_a = tracker.engines["A"]

    def broken_close() -> None:
        raise RuntimeError("fermeture impossible")

    engine_a.close = broken_close

    _, status = _switch(session, ModelChoice("file", paths["B"]))

    assert status == "restored" and session.active_model()["label"] == "A"
    assert session._load_registry.holder() == "A"


def test_budget_checked_again_with_the_probe_measure(tmp_path):
    session, tracker, paths = _booted(tmp_path, {"A": FakeEngine(), "B": FakeEngine()})

    def probe_measuring(path: str) -> None:
        tracker.log.append("probe B")
        _record_probe(path, rss_bytes=5 * GIB)  # what the child process measured
        return None

    mark = get_journal().last_seq()
    _, status = _switch(session, ModelChoice("file", paths["B"]), probe_measuring)

    assert status == "restored" and "open B" not in tracker.log
    ended = _events(mark, "model_load_ended")[-1]
    assert "Changement refusé : B demande environ 5,0 Go" in ended["reason_fr"]
    assert session.active_model()["label"] == "A"


def test_diagnostic_blocks_again_when_no_model_is_left(monkeypatch, tmp_path):
    _, app_session, client, tracker = _web(monkeypatch, tmp_path)
    tracker.fail = {"A", "B"}

    client.post(
        "/api/intentions/select_model",
        json={"ref": str(config.models_dir() / "B.gguf")},
        headers=ORIGIN,
    )
    app_session.join()

    diagnostic = client.get("/api/diagnostic").json()
    assert diagnostic["ready"] is False and diagnostic["blocking_checks"] == ["model"]
    assert not app_session.model_loaded


# ---------- lot E: estimate, refusal, stop during a load ----------

MIB = 1024**2


def test_refusal_gives_wavestack_memory_in_mo_under_one_go():
    """E3: WaveStack's real memory without the active model, in Mo under 1 Go."""
    registry = LoadRegistry(4 * GIB, 0, rss_fn=lambda: 210 * MIB + 2 * GIB)
    registry.grant("A", 2 * GIB)

    refusal = registry.check("B", round(3.9 * GIB))

    assert "WaveStack occupe 210 Mo sans le modèle actif, pour un budget de 4,0 Go." in refusal
    assert refusal.startswith("Changement refusé : B demande environ 3,9 Go ;")


def test_a_served_model_is_never_subtracted_from_the_rss():
    """E3: a served model's memory is in another process: WaveStack's RSS stays whole."""
    registry = LoadRegistry(4 * GIB, 0, rss_fn=lambda: 210 * MIB)
    registry.grant("qwen3.5:2b", 3 * GIB, in_process=False)

    refusal = registry.check("olmo-3:7b", round(4.4 * GIB))

    assert "WaveStack occupe 210 Mo sans le modèle actif" in refusal  # never « 0,0 Go »
    assert registry.check("petit", 3 * GIB) is None  # 210 Mo + 3 Go ≤ 4 Go


def test_4b_estimate_after_the_new_probe_exceeds_the_budget(tmp_path):
    """Acceptance (N5): the 4B, probed at the window after an evaluation (weights, the whole
    window's KV, compute buffers: ≈ 4,05 Go injected here, to measure on the PC), plus the
    margin, is past the 4 096 Mo budget (≈ 4,3 Go); the refusal gives WaveStack's real
    memory."""
    engines = {"Qwen3.5-2B": FakeEngine(), "Qwen3.5-4B": FakeEngine()}
    tracker = Tracker(engines)
    paths = _files(tmp_path, *engines)
    held = Path(paths["Qwen3.5-2B"]).stat().st_size  # the 2B's share of the RSS (its file)
    session = _session(tracker, rss=210 * MIB + held, margin_mb=256)
    session.boot(paths["Qwen3.5-2B"]).result()
    kv = 131_072  # bytes per token: 0,5 Go at 4 096 tokens, as the story 17 probe read it
    _record_probe(
        paths["Qwen3.5-4B"],
        rss_bytes=round(4.05 * GIB),
        kv_bytes_per_token=kv,
        probe_window=4096,
        rss_eval_tokens=512,
    )

    cost = session._cost(ModelChoice("file", paths["Qwen3.5-4B"]))
    with pytest.raises(SendRefused) as refused:
        session.switch_model(ModelChoice("file", paths["Qwen3.5-4B"]))

    assert cost == round(4.05 * GIB) + 256 * MIB > 4096 * MIB  # no KV counted twice
    assert "Qwen3.5-4B demande environ 4,3 Go" in refused.value.reason_fr
    assert "WaveStack occupe 210 Mo sans le modèle actif" in refused.value.reason_fr
    assert tracker.open == {"Qwen3.5-2B"}


def _gated(session: AppSession, tracker: Tracker, name: str):  # noqa: ANN202
    """`name`'s load waits for `gate`; `entered` once it is under way."""
    entered, gate = threading.Event(), threading.Event()
    factory = tracker.factory

    def slow(path: str, n_ctx: int) -> FakeEngine:
        if Path(path).stem == name:
            entered.set()
            gate.wait(5)
        return factory(path, n_ctx)

    session._engine_factory = slow
    return entered, gate


def test_stop_during_a_slow_load_brings_the_previous_model_back(tmp_path):
    """E4: « Arrêter » in `model_load`: accepted, then at the next checkpoint (after the
    load: llama.cpp cannot interrupt it) B is released and A reloaded, never both."""
    session, tracker, paths = _booted(tmp_path, {"A": FakeEngine(), "B": FakeEngine()})
    _record_probe(paths["B"])
    entered, gate = _gated(session, tracker, "B")
    mark = get_journal().last_seq()

    _, future = session.switch_model(ModelChoice("file", paths["B"]))
    assert entered.wait(5) and session.state == "model_load"
    assert session.stop() is True
    gate.set()

    assert future.result() == "cancelled"
    assert tracker.log[-3:] == ["open B", "close B", "open A"] and tracker.open == {"A"}
    assert not tracker.overlap
    ended = _events(mark, "model_load_ended")[-1]
    assert (ended["status"], ended["reason_fr"]) == (
        "cancelled",
        "Chargement arrêté : A est de nouveau actif.",
    )
    assert session.state == "idle" and session.reason_fr is None
    assert session.active_model()["label"] == "A" and session._load_registry.holder() == "A"
    assert "selected_model" not in config.read_settings()  # never saved
    assert session.stop() is False  # nothing left to stop


def test_stop_during_the_probe_never_loads_the_new_model(tmp_path):
    session, tracker, paths = _booted(tmp_path, {"A": FakeEngine(), "B": FakeEngine()})

    def probe_and_stop(path: str) -> None:
        tracker.log.append("probe B")
        assert session.stop() is True  # the click lands while the child process runs
        return None

    _, status = _switch(session, ModelChoice("file", paths["B"]), probe_and_stop)

    assert status == "cancelled" and "open B" not in tracker.log
    assert tracker.log[-3:] == ["close A", "probe B", "open A"]
    assert session.active_model()["label"] == "A"


def test_stop_without_a_previous_model_leaves_none_with_the_reason(tmp_path):
    """E4: the launch's load stopped: no model is active, and `idle` says why."""
    from wavestack.session.app_session import _LOAD_STOPPED_FR

    tracker = Tracker({"A": FakeEngine()})
    paths = _files(tmp_path, "A")
    session = _session(tracker)
    entered, gate = _gated(session, tracker, "A")
    mark = get_journal().last_seq()

    future = session.boot(paths["A"])
    assert entered.wait(5) and session.stop() is True
    gate.set()

    assert future.result() == "cancelled"
    assert not session.model_loaded and tracker.open == set()
    assert session.state == "idle" and session.reason_fr == _LOAD_STOPPED_FR
    ended = _events(mark, "model_load_ended")[-1]
    assert (ended["status"], ended["reason_fr"]) == (
        "cancelled",
        "Chargement arrêté : aucun modèle n'est actif.",
    )


def test_web_stop_answers_stopping_during_a_load(monkeypatch, tmp_path):
    session, app_session, client, tracker = _web(monkeypatch, tmp_path)
    entered, gate = _gated(app_session, tracker, "B")
    b = str(config.models_dir() / "B.gguf")
    _record_probe(b)

    client.post("/api/intentions/select_model", json={"ref": b}, headers=ORIGIN)
    assert entered.wait(5)
    stop = client.post("/api/intentions/stop", json={}, headers=ORIGIN)
    gate.set()
    app_session.join()

    assert stop.json() == {"stopping": True}
    assert app_session.active_model()["label"] == "A"
    diagnostic = client.get("/api/diagnostic").json()
    assert diagnostic["ready"] is True and diagnostic["loaded_model"].endswith("A.gguf")


@pytest.mark.parametrize(
    "error", [ValueError("Failed to load model from file: B.gguf"), RuntimeError("abort")]
)
def test_llama_cpp_refusal_at_the_load_is_said_in_french(tmp_path, error):
    """E6: any failure of the in-process engine's factory: the French reason, llama.cpp's own
    message as the cause (a technical detail)."""
    session, tracker, paths = _booted(tmp_path, {"A": FakeEngine(), "B": FakeEngine()})
    factory = tracker.factory

    def refuse(path: str, n_ctx: int) -> FakeEngine:
        if Path(path).stem == "B":
            raise error
        return factory(path, n_ctx)

    session._engine_factory = refuse
    mark = get_journal().last_seq()

    _, status = _switch(session, ModelChoice("file", paths["B"]))

    assert status == "restored"
    ended = _events(mark, "model_load_ended")[-1]
    assert "ne sait pas charger ce fichier" in ended["reason_fr"]
    assert str(error) not in ended["reason_fr"]
    assert _events(mark, "harness_error")[-1]["cause"] == str(error)


def test_refusal_with_a_local_model_active_gives_the_real_remainder(tmp_path):
    """E3: the active file's measured share of the RSS comes off, never its estimate (margin
    and KV), which could leave « 0 Mo »."""
    engines = {"A": FakeEngine(), "B": FakeEngine()}
    tracker = Tracker(engines)
    paths = _files(tmp_path, *engines)
    share = round(1.5 * GIB)
    _record_probe(paths["A"], rss_bytes=share, kv_bytes_per_token=131_072)  # estimate: 2,25 Go
    _record_probe(paths["B"], rss_bytes=round(3.9 * GIB))
    session = _session(tracker, rss=210 * MIB + share, margin_mb=256)
    session.boot(paths["A"]).result()

    with pytest.raises(SendRefused) as refused:
        session.switch_model(ModelChoice("file", paths["B"]))

    assert "WaveStack occupe 210 Mo sans le modèle actif" in refused.value.reason_fr


def test_stop_whose_previous_model_fails_to_come_back_is_an_error(tmp_path):
    session, tracker, paths = _booted(tmp_path, {"A": FakeEngine(), "B": FakeEngine()})
    _record_probe(paths["B"])
    entered, gate = _gated(session, tracker, "B")
    mark = get_journal().last_seq()

    _, future = session.switch_model(ModelChoice("file", paths["B"]))
    assert entered.wait(5) and session.stop() is True
    tracker.fail = {"A"}
    gate.set()

    assert future.result() == "error"
    assert not session.model_loaded and tracker.open == set()
    assert session.reason_fr == _LOAD_FAILED_FR
    ended = _events(mark, "model_load_ended")[-1]
    assert (ended["status"], ended["reason_fr"]) == (
        "error",
        "Chargement arrêté ; le modèle précédent (A) n'a pas pu être rechargé.",
    )


def test_stop_after_the_last_checkpoint_answers_false(tmp_path):
    """E4: past the last checkpoint, « Arrêter » is refused, never accepted then ignored."""
    session, _, paths = _booted(tmp_path, {"A": FakeEngine(), "B": FakeEngine()})
    answers = []
    save = session._save_choice

    def save_and_stop(choice: ModelChoice) -> str | None:
        answers.append(session.stop())  # the click lands after the load
        return save(choice)

    session._save_choice = save_and_stop

    _, status = _switch(session, ModelChoice("file", paths["B"]))

    assert answers == [False] and status == "ok"
    assert session.active_model()["label"] == "B"


def test_web_hot_switch_stopped_with_no_model_blocks_the_diagnostic(monkeypatch, tmp_path):
    session, app_session, client, tracker = _web(monkeypatch, tmp_path)
    b = str(config.models_dir() / "B.gguf")
    _record_probe(b)
    tracker.fail = {"A", "B"}  # B and A fail: no model left
    client.post("/api/intentions/select_model", json={"ref": b}, headers=ORIGIN)
    app_session.join()
    assert not app_session.model_loaded
    tracker.fail = set()
    entered, gate = _gated(app_session, tracker, "B")
    mark = get_journal().last_seq()

    client.post("/api/intentions/select_model", json={"ref": b}, headers=ORIGIN)
    assert entered.wait(5)
    assert client.post("/api/intentions/stop", json={}, headers=ORIGIN).json()["stopping"]
    gate.set()
    app_session.join()

    diagnostic = client.get("/api/diagnostic").json()
    assert diagnostic["ready"] is False and diagnostic["blocking_checks"] == ["model"]
    check = [c for c in _events(mark, "diagnostic_check") if c["check"] == "model"][-1]
    assert check["blocking"] and "le chargement a été arrêté" in check["message_fr"]


def test_launch_boot_stopped_blocks_the_diagnostic(monkeypatch, tmp_path):
    """E4: « Arrêter » during the launch's load: no model, the diagnostic blocks again."""
    monkeypatch.setenv("OLLAMA_MODELS", str(tmp_path / "no-ollama"))
    monkeypatch.setenv("HF_HUB_CACHE", str(tmp_path / "no-hf-cache"))
    monkeypatch.setattr(discovery, "_lm_studio_dirs", lambda: [])
    monkeypatch.setattr(discovery, "_server_candidates", lambda cfg: [])
    config.models_dir().mkdir(parents=True)
    (config.models_dir() / "A.gguf").write_bytes(b"placeholder")
    session = DiagnosticSession(config.load_config(), port=8420)
    monkeypatch.setattr(session, "check_network", lambda: None)
    monkeypatch.setattr(session, "_probe_candidate", lambda candidate: None)
    tracker = Tracker({"A": FakeEngine()})
    app_session = _session(tracker)
    entered, gate = _gated(app_session, tracker, "A")
    result = session.run()
    assert result.ready is True

    session.hand_to(app_session, result, launch=True)
    assert entered.wait(5) and app_session.stop() is True
    gate.set()
    app_session.join()

    assert not app_session.model_loaded
    assert session.last_result.ready is False and session.last_result.blocking_checks == ["model"]
