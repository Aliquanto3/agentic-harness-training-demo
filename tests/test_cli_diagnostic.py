from __future__ import annotations

import json
import subprocess
from pathlib import Path

from fake_engine import FakeEngine
from starlette.testclient import TestClient

from wavestack import config
from wavestack.models import discovery, probe
from wavestack.session import diagnostic as diagnostic_module
from wavestack.session.app_session import AppSession
from wavestack.session.diagnostic import DiagnosticSession
from wavestack.trace.journal import get_journal
from wavestack.web.app import create_app


def _client(app):
    # TrustedHostMiddleware only allows the app's own host:port; point the
    # test client's Host header there instead of starlette's default "testserver".
    return TestClient(app, base_url="http://127.0.0.1:8420")


def _build(monkeypatch, tmp_path, *, models=(), saved=None, app_session=None):
    """`models`: GGUF file names created in the models dir; `saved`: the stored choice."""
    monkeypatch.setenv("WAVESTACK_DATA_DIR", str(tmp_path / "data"))
    if models:
        config.models_dir().mkdir(parents=True)
    for name in models:
        (config.models_dir() / name).write_bytes(b"placeholder")
    if saved:
        config.save_setting("selected_model", str(config.models_dir() / saved))
    # Isolate discovery from whatever Ollama/LM Studio/HF cache happens to be
    # installed on the machine running the tests: this story's diagnostic
    # tests must be deterministic regardless of the dev's local setup.
    monkeypatch.setenv("OLLAMA_MODELS", str(tmp_path / "no-ollama"))
    monkeypatch.setenv("HF_HUB_CACHE", str(tmp_path / "no-hf-cache"))
    monkeypatch.setattr(discovery, "_lm_studio_dirs", lambda: [tmp_path / "no-lmstudio"])
    monkeypatch.setattr(discovery, "_server_candidates", lambda cfg: [])

    cfg = config.load_config()
    session = DiagnosticSession(cfg, port=8420)
    # Keep these tests offline and process-free: story 1's network probe and
    # the subprocess GGUF probe are covered separately (test_net_guard.py,
    # test_probe.py); this file checks the diagnostic session/API wiring.
    monkeypatch.setattr(session, "check_network", lambda: None)
    monkeypatch.setattr(session, "_probe_candidate", lambda candidate, cancel=None: None)
    app = create_app(session, port=8420, version="test", app_session=app_session)
    return session, app


def test_health_endpoint(monkeypatch, tmp_path):
    _, app = _build(monkeypatch, tmp_path)
    response = _client(app).get("/api/health")
    assert response.status_code == 200
    assert response.json()["status"] == "ok"


def test_no_model_found_blocks_diagnostic(monkeypatch, tmp_path):
    session, app = _build(monkeypatch, tmp_path)

    result = session.check_model()
    assert result.ready is False
    assert result.blocking_checks == ["model"]

    body = _client(app).get("/api/diagnostic").json()
    assert body["ready"] is False
    assert body["blocking_checks"] == ["model"]

    events = get_journal().all_events()
    model_checks = [
        e for e in events if e.kind == "diagnostic_check" and e.payload["check"] == "model"
    ]
    assert model_checks[-1].payload["status"] == "fail"
    assert model_checks[-1].payload["blocking"] is True


def test_diagnostic_gives_the_journal_tip_for_the_page_replay(monkeypatch, tmp_path):
    """The page treats the stream's events up to this `seq` as history (no side effects)."""
    session, app = _build(monkeypatch, tmp_path)
    session.check_model()

    body = _client(app).get("/api/diagnostic").json()

    assert body["seq"] == get_journal().last_seq() > 0


def test_model_in_models_dir_passes_without_blocking(monkeypatch, tmp_path):
    session, _ = _build(monkeypatch, tmp_path)
    models_dir = config.models_dir()
    models_dir.mkdir(parents=True)
    (models_dir / "demo.gguf").write_bytes(b"placeholder")

    result = session.check_model()
    assert result.ready is True
    assert result.blocking_checks == []


def test_select_model_intention_rechecks_the_given_path(monkeypatch, tmp_path):
    session, app = _build(monkeypatch, tmp_path)
    model_file = tmp_path / "picked.gguf"
    model_file.write_bytes(b"placeholder")

    response = _client(app).post(
        "/api/intentions/select_model",
        json={"path": str(model_file)},
        headers={"Origin": "http://127.0.0.1:8420"},
    )
    assert response.status_code == 200
    assert response.json()["ready"] is True
    assert session.selected_model_path == str(model_file)


def test_select_model_wrong_origin_is_refused(monkeypatch, tmp_path):
    _, app = _build(monkeypatch, tmp_path)
    response = _client(app).post(
        "/api/intentions/select_model",
        json={"path": "irrelevant.gguf"},
        headers={"Origin": "http://evil.test"},
    )
    assert response.status_code == 403


def test_select_model_missing_origin_is_refused(monkeypatch, tmp_path):
    _, app = _build(monkeypatch, tmp_path)
    response = _client(app).post(
        "/api/intentions/select_model",
        json={"path": "irrelevant.gguf"},
    )
    assert response.status_code == 403


def test_select_model_wrong_content_type_is_rejected(monkeypatch, tmp_path):
    _, app = _build(monkeypatch, tmp_path)
    response = _client(app).post(
        "/api/intentions/select_model",
        content="not json",
        headers={
            "Origin": "http://127.0.0.1:8420",
            "Content-Type": "text/plain",
        },
    )
    assert response.status_code == 415


def test_probe_failure_marks_candidate_incompatible_and_stays_blocking(monkeypatch, tmp_path):
    session, _ = _build(monkeypatch, tmp_path)
    # _build() stubs _probe_candidate to a no-op; restore the real, bound method.
    monkeypatch.setattr(
        session, "_probe_candidate", DiagnosticSession._probe_candidate.__get__(session)
    )
    models_dir = config.models_dir()
    models_dir.mkdir(parents=True)
    (models_dir / "bad.gguf").write_bytes(b"not a real gguf")

    class _FakeCompletedProcess:
        stdout = '{"ok": false, "path": "bad.gguf", "reason": "Fichier corrompu."}'

    monkeypatch.setattr(diagnostic_module, "_run_probe", lambda *a, **k: _FakeCompletedProcess())

    before = get_journal().last_seq()
    result = session.check_model()

    assert result.ready is False
    assert result.blocking_checks == ["model"]
    errors = [e for e in get_journal().events_since(before) if e.kind == "harness_error"]
    assert errors and "Fichier corrompu." in errors[0].payload["cause"]


def test_probe_subprocess_crash_marks_candidate_incompatible(monkeypatch, tmp_path):
    session, _ = _build(monkeypatch, tmp_path)
    monkeypatch.setattr(
        session, "_probe_candidate", DiagnosticSession._probe_candidate.__get__(session)
    )
    models_dir = config.models_dir()
    models_dir.mkdir(parents=True)
    (models_dir / "bad.gguf").write_bytes(b"not a real gguf")

    def _raise(*args, **kwargs):
        raise subprocess.TimeoutExpired(cmd="probe", timeout=1)

    monkeypatch.setattr(diagnostic_module, "_run_probe", _raise)

    result = session.check_model()

    assert result.ready is False
    assert result.blocking_checks == ["model"]


def test_probe_failure_is_remembered_and_not_reprobed(monkeypatch, tmp_path):
    session, _ = _build(monkeypatch, tmp_path, models=("bad.gguf",))
    monkeypatch.setattr(
        session, "_probe_candidate", DiagnosticSession._probe_candidate.__get__(session)
    )
    runs = []

    class _FakeCompletedProcess:
        stdout = '{"ok": false, "path": "bad.gguf", "reason": "Fichier corrompu."}'

    def _run(*args, **kwargs):
        runs.append(args)
        return _FakeCompletedProcess()

    monkeypatch.setattr(diagnostic_module, "_run_probe", _run)

    session.check_model()
    result = session.check_model()  # next launch: same file, same size and date

    assert len(runs) == 1
    assert result.candidates[0].status == "incompatible"
    assert result.candidates[0].reason == "Fichier corrompu."


def test_native_crash_is_remembered_python_error_is_not(monkeypatch, tmp_path):
    session, _ = _build(monkeypatch, tmp_path, models=("crash.gguf",))
    monkeypatch.setattr(
        session, "_probe_candidate", DiagnosticSession._probe_candidate.__get__(session)
    )
    path = str(config.models_dir() / "crash.gguf")

    class _Died:
        stdout = ""
        returncode = 1  # Python error in the child: environment, not the file

    monkeypatch.setattr(diagnostic_module, "_run_probe", lambda *a, **k: _Died())
    session.check_model()
    assert "failed_probes" not in config.read_settings()

    _Died.returncode = 3221225477  # Windows access violation while loading
    session.check_model()
    assert path in config.read_settings()["failed_probes"]


def test_explicit_choice_of_a_remembered_failure_is_not_reprobed(monkeypatch, tmp_path):
    session, _ = _build(monkeypatch, tmp_path, models=("bad.gguf",))
    path = str(config.models_dir() / "bad.gguf")
    probe.record_failure(path, "Fichier corrompu.")

    result = session.select_model(path)

    assert result.saved is False
    assert "Fichier corrompu." in result.message_text


def test_probe_timeout_is_not_remembered(monkeypatch, tmp_path):
    session, _ = _build(monkeypatch, tmp_path, models=("slow.gguf",))
    monkeypatch.setattr(
        session, "_probe_candidate", DiagnosticSession._probe_candidate.__get__(session)
    )

    def _raise(*args, **kwargs):
        raise subprocess.TimeoutExpired(cmd="probe", timeout=1)

    monkeypatch.setattr(diagnostic_module, "_run_probe", _raise)
    session.check_model()

    assert "failed_probes" not in config.read_settings()


def test_network_unreachable_warns_without_blocking(monkeypatch, tmp_path):
    # The session-wide guard fixture (conftest.py) allows only loopback hosts,
    # so this real check_network() call is refused by the guard exactly like
    # an unreachable host would be (AD-16: never an unhandled exception).
    session, _ = _build(monkeypatch, tmp_path)

    before = get_journal().last_seq()
    DiagnosticSession.check_network(session)  # _build() stubs the instance's check_network

    events = [
        e
        for e in get_journal().events_since(before)
        if e.kind == "diagnostic_check" and e.payload["check"] == "network"
    ]
    assert events[-1].payload["status"] == "warn"
    assert events[-1].payload["blocking"] is False


def test_full_run_emits_all_checks(monkeypatch, tmp_path):
    session, _ = _build(monkeypatch, tmp_path)
    models_dir = config.models_dir()
    models_dir.mkdir(parents=True)
    (models_dir / "demo.gguf").write_bytes(b"placeholder")

    before = get_journal().last_seq()
    result = session.run()
    assert result.ready is True

    kinds_checked = {
        e.payload["check"]
        for e in get_journal().events_since(before)
        if e.kind == "diagnostic_check"
    }
    assert kinds_checked == {"memory", "model", "port"}


# ---------- story 1b: model choice at the diagnostic ----------


def _recording_app_session(received):
    def factory(path, n_ctx):
        received.append(path)
        return FakeEngine()

    return AppSession(config.load_config(), engine_factory=factory)


def _select(app, path):
    return (
        _client(app)
        .post(
            "/api/intentions/select_model",
            json={"path": str(path)},
            headers={"Origin": "http://127.0.0.1:8420"},
        )
        .json()
    )


def _last_model_check(before):
    checks = [
        e.payload
        for e in get_journal().events_since(before)
        if e.kind == "diagnostic_check" and e.payload["check"] == "model"
    ]
    return checks[-1]


def _fake_probe_ok(monkeypatch, session, architecture="qwen35"):
    """Restore the real `_probe_candidate`, with a child process that always succeeds."""
    monkeypatch.setattr(
        session, "_probe_candidate", DiagnosticSession._probe_candidate.__get__(session)
    )
    calls = []

    def _run(cmd, **kwargs):
        path = cmd[-1]
        calls.append(path)
        stat = Path(path).stat()

        class _Done:
            stdout = probe.ProbeResult(
                ok=True,
                path=path,
                architecture=architecture,
                size_bytes=stat.st_size,
                mtime=stat.st_mtime,
            ).model_dump_json()

        return _Done()

    monkeypatch.setattr(diagnostic_module, "_run_probe", _run)
    return calls


def test_saved_choice_is_loaded_at_startup(monkeypatch, tmp_path):
    session, _ = _build(monkeypatch, tmp_path, models=("a.gguf", "b.gguf"), saved="b.gguf")

    result = session.check_model()

    assert result.ready is True
    assert result.model_path == str(config.models_dir() / "b.gguf")


def test_saved_choice_gone_warns_then_applies_startup_rule(monkeypatch, tmp_path):
    session, _ = _build(monkeypatch, tmp_path, models=("a.gguf", "b.gguf"), saved="gone.gguf")
    before = get_journal().last_seq()

    result = session.check_model()

    assert result.model_path is None and result.blocking_checks == ["model"]
    check = _last_model_check(before)
    assert "gone.gguf" in check["message_text"]
    assert "Plusieurs modèles trouvés" in check["message_text"]


def test_saved_choice_gone_with_single_file_loads_it_with_warning(monkeypatch, tmp_path):
    session, _ = _build(monkeypatch, tmp_path, models=("a.gguf",), saved="gone.gguf")
    before = get_journal().last_seq()

    result = session.check_model()

    assert result.model_path == str(config.models_dir() / "a.gguf")
    check = _last_model_check(before)
    assert check["status"] == "warn" and "gone.gguf" in check["message_text"]


def test_single_candidate_is_loaded_at_startup(monkeypatch, tmp_path):
    session, _ = _build(monkeypatch, tmp_path, models=("a.gguf",))

    result = session.check_model()

    assert result.ready is True
    assert result.model_path == str(config.models_dir() / "a.gguf")


def test_several_candidates_block_until_a_choice(monkeypatch, tmp_path):
    session, _ = _build(monkeypatch, tmp_path, models=("a.gguf", "b.gguf"))
    before = get_journal().last_seq()

    result = session.check_model()

    assert result.ready is False and result.model_path is None
    assert result.blocking_checks == ["model"]
    check = _last_model_check(before)
    assert check["status"] == "warn" and check["blocking"] is True
    assert check["message_text"] == "Plusieurs modèles trouvés : choisissez-en un."


def test_choose_before_load_saves_and_loads_exactly_that_file(monkeypatch, tmp_path):
    received = []
    session, app = _build(
        monkeypatch,
        tmp_path,
        models=("a.gguf", "b.gguf"),
        app_session=_recording_app_session(received),
    )
    session.check_model()  # blocked: several candidates
    chosen = config.models_dir() / "b.gguf"

    body = _select(app, chosen)
    app.state.app_session.join()

    assert body["ready"] is True and body["saved"] is True and body["switching"] is True
    assert received == [str(chosen)]
    assert config.read_settings()["selected_model"] == {"kind": "file", "ref": str(chosen)}
    assert _client(app).get("/api/diagnostic").json()["ready"] is True  # "Ouvrir WaveStack"

    # Relaunch: the saved choice is loaded with no further action.
    relaunched = DiagnosticSession(config.load_config(), port=8420)
    monkeypatch.setattr(relaunched, "_probe_candidate", lambda candidate, cancel=None: None)
    assert relaunched.check_model().model_path == str(chosen)


def test_typed_path_outside_locations_is_probed_saved_and_loaded(monkeypatch, tmp_path):
    received = []
    session, app = _build(
        monkeypatch,
        tmp_path,
        models=("a.gguf", "b.gguf"),
        app_session=_recording_app_session(received),
    )
    probed = _fake_probe_ok(monkeypatch, session)
    elsewhere = tmp_path / "elsewhere" / "picked.gguf"
    elsewhere.parent.mkdir()
    elsewhere.write_bytes(b"placeholder")

    body = _select(app, elsewhere)
    app.state.app_session.join()

    assert probed == [str(elsewhere)]  # only the chosen file, never the other candidates
    assert body["saved"] is True and received == [str(elsewhere)]
    assert config.read_settings()["selected_model"] == {"kind": "file", "ref": str(elsewhere)}
    listed = _client(app).get("/api/diagnostic").json()
    picked = next(c for c in listed["candidates"] if c["path"] == str(elsewhere))
    assert picked["name"] == "picked.gguf" and picked["architecture"] == "qwen35"
    assert listed["selected_model"] == str(elsewhere)


def test_invalid_path_is_neither_saved_nor_loaded(monkeypatch, tmp_path):
    received = []
    session, app = _build(
        monkeypatch,
        tmp_path,
        models=("a.gguf", "b.gguf"),
        app_session=_recording_app_session(received),
    )
    session.check_model()

    missing = _select(app, tmp_path / "missing.gguf")

    monkeypatch.setattr(
        session, "_probe_candidate", DiagnosticSession._probe_candidate.__get__(session)
    )

    class _Refused:
        stdout = '{"ok": false, "path": "bad.gguf", "reason": "Architecture inconnue."}'

    monkeypatch.setattr(diagnostic_module, "_run_probe", lambda *a, **k: _Refused())
    bad = tmp_path / "bad.gguf"
    bad.write_bytes(b"not a gguf")
    incompatible = _select(app, bad)
    app.state.app_session.join()

    assert "Fichier introuvable" in missing["message_text"]
    assert "Architecture inconnue." in incompatible["message_text"]
    for body in (missing, incompatible):
        assert body["saved"] is False and body["ready"] is False
    assert received == []  # no other candidate loaded instead
    assert "selected_model" not in config.read_settings()


def test_choice_after_load_is_a_hot_switch(monkeypatch, tmp_path):
    """Story 17 (CAP-34): no relaunch; the new file is probed by the application session
    once the loaded model is released, then loaded and saved."""
    received = []
    session, app = _build(
        monkeypatch, tmp_path, models=("a.gguf",), app_session=_recording_app_session(received)
    )
    first = session.check_model()
    assert first.model_path  # handed out at startup (cli.py boots it)
    session.hand_to(app.state.app_session, first, launch=True)
    app.state.app_session.join()
    probed = _fake_probe_ok(monkeypatch, session)
    other = tmp_path / "other.gguf"
    other.write_bytes(b"placeholder")

    body = _select(app, other)
    app.state.app_session.join()

    assert body["switching"] is True and body["message_text"] == "Chargement de other…"
    assert "Choix enregistré" not in body["message_text"] and "next_launch" not in body
    assert received == [first.model_path, str(other)] and probed == [str(other)]
    assert config.read_settings()["selected_model"] == {"kind": "file", "ref": str(other)}
    diagnostic = _client(app).get("/api/diagnostic").json()
    assert "next_launch_text" not in diagnostic
    assert diagnostic["loaded_model"] == diagnostic["selected_model"] == str(other)
    listed = next(c for c in diagnostic["candidates"] if c["path"] == str(other))
    assert listed["architecture"] == "qwen35"


def test_settings_write_failure_is_traced_and_model_still_loads(monkeypatch, tmp_path):
    received = []
    session, app = _build(
        monkeypatch,
        tmp_path,
        models=("a.gguf", "b.gguf"),
        app_session=_recording_app_session(received),
    )
    session.check_model()

    def _refuse(key, value):
        raise PermissionError("settings.json en lecture seule")

    monkeypatch.setattr(config, "save_setting", _refuse)
    before = get_journal().last_seq()
    chosen = config.models_dir() / "a.gguf"

    body = _select(app, chosen)
    app.state.app_session.join()

    assert body["ready"] is True and received == [str(chosen)]
    assert body["saved"] is False and "pas pu être mémorisé" in body["message_text"]
    errors = [e for e in get_journal().events_since(before) if e.kind == "harness_error"]
    assert any("lecture seule" in e.payload["cause"] for e in errors)


def _ollama_blob(tmp_path, *tags):
    """One Ollama blob, listed under `library/qwen3.5/<tag>` for each tag."""
    ollama = tmp_path / "no-ollama"  # the OLLAMA_MODELS root set by _build
    manifest_dir = ollama / "manifests" / "registry.ollama.ai" / "library" / "qwen3.5"
    manifest_dir.mkdir(parents=True)
    (ollama / "blobs").mkdir()
    blob = ollama / "blobs" / "sha256-aaaa"
    blob.write_bytes(b"fake gguf bytes")
    layer = {"mediaType": "application/vnd.ollama.image.model", "digest": "sha256:aaaa"}
    for tag in tags:
        (manifest_dir / tag).write_text(json.dumps({"layers": [layer]}), encoding="utf-8")
    return blob


def test_ollama_candidate_named_from_manifest_with_cached_architecture(monkeypatch, tmp_path):
    session, app = _build(monkeypatch, tmp_path)
    blob = _ollama_blob(tmp_path, "9b")
    stat = blob.stat()
    probe.record_success(
        probe.ProbeResult(
            ok=True,
            path=str(blob),
            architecture="qwen35",
            size_bytes=stat.st_size,
            mtime=stat.st_mtime,
            rss_bytes=1,  # lot E: a complete entry of the current probe, never probed again
            probe_version=probe.PROBE_VERSION,
            probe_window=4096,
            rss_eval_tokens=512,
        )
    )

    session.check_model()
    listed = _client(app).get("/api/diagnostic").json()["candidates"]

    assert [(c["name"], c["architecture"], c["status"]) for c in listed] == [
        ("qwen3.5:9b", "qwen35", "found")
    ]


def test_selected_ollama_blob_is_listed_once_under_its_name(monkeypatch, tmp_path):
    received = []
    session, app = _build(monkeypatch, tmp_path, app_session=_recording_app_session(received))
    blob = _ollama_blob(tmp_path, "9b")
    before = get_journal().last_seq()

    _select(app, blob)
    app.state.app_session.join()

    listed = _client(app).get("/api/diagnostic").json()
    assert [c["name"] for c in listed["candidates"] if c["path"] == str(blob)] == ["qwen3.5:9b"]
    assert listed["loaded_model"] == str(blob) and received == [str(blob)]
    assert "Modèle retenu : qwen3.5:9b" in _last_model_check(before)["message_text"]

    # Relaunch with the saved blob: still listed once.
    relaunched = DiagnosticSession(config.load_config(), port=8420)
    monkeypatch.setattr(relaunched, "_probe_candidate", lambda candidate, cancel=None: None)
    result = relaunched.check_model()
    assert result.model_path == str(blob)
    assert [c.path for c in result.candidates].count(str(blob)) == 1


def test_ollama_tags_sharing_one_blob_count_as_one_file(monkeypatch, tmp_path):
    session, _ = _build(monkeypatch, tmp_path)
    blob = _ollama_blob(tmp_path, "9b", "latest")

    result = session.check_model()

    assert result.ready is True and result.model_path == str(blob)


def test_served_models_only_block_until_one_is_chosen(monkeypatch, tmp_path):
    """Story 18: a served model is never chosen by default (Ollama would load it)."""
    session, _ = _build(monkeypatch, tmp_path)
    server = discovery.ModelCandidate(
        source="server",
        status="server",
        server_url="http://127.0.0.1:11434",
        name="qwen3:0.6b",
        engine="ollama",
        ref="ollama/qwen3:0.6b",
        provider="Ollama",
    )
    monkeypatch.setattr(discovery, "_server_candidates", lambda cfg: [server])
    before = get_journal().last_seq()

    result = session.check_model()

    assert result.ready is False and result.blocking_checks == ["model"]
    assert result.model_path is None and result.server is None
    check = _last_model_check(before)
    assert check["blocking"] is True and "choisissez un modèle servi" in check["message_text"]


def test_failed_load_lets_a_new_choice_load(monkeypatch, tmp_path):
    received = []

    def factory(path, n_ctx):
        received.append(path)
        if path.endswith("a.gguf"):
            raise RuntimeError("chargement impossible")
        return FakeEngine()

    app_session = AppSession(config.load_config(), engine_factory=factory)
    session, app = _build(
        monkeypatch, tmp_path, models=("a.gguf", "b.gguf"), app_session=app_session
    )
    session.check_model()
    first, second = config.models_dir() / "a.gguf", config.models_dir() / "b.gguf"

    _select(app, first)
    app_session.join()
    assert not app_session.model_loaded and app_session.state == "idle"

    body = _select(app, second)
    app_session.join()

    assert body["switching"] is True  # story 17: loaded without relaunch
    assert received == [str(first), str(second)] and app_session.model_loaded


def test_quoted_pasted_path_is_accepted(monkeypatch, tmp_path):
    received = []
    session, app = _build(
        monkeypatch,
        tmp_path,
        models=("a.gguf", "b.gguf"),
        app_session=_recording_app_session(received),
    )
    chosen = config.models_dir() / "b.gguf"

    body = _select(app, f'  "{chosen}" ')
    app.state.app_session.join()

    assert body["saved"] is True and received == [str(chosen)]
    assert config.read_settings()["selected_model"] == {"kind": "file", "ref": str(chosen)}


def test_two_models_and_no_choice_launch_on_the_diagnostic_page(monkeypatch, tmp_path):
    """Story 11b: a blocked launch opens `/diagnostic`, a ready one `/`."""
    from wavestack.session.diagnostic import launch_page

    session, _ = _build(monkeypatch, tmp_path, models=("a.gguf", "b.gguf"))

    assert launch_page(session.check_model()) == "/diagnostic"

    session, _ = _build(monkeypatch, tmp_path / "one", models=("a.gguf",))
    assert launch_page(session.check_model()) == "/"


def test_launch_fallback_loads_the_file(monkeypatch, tmp_path):
    """Story 11b: a saved cloud model without key falls back on the file at launch."""
    monkeypatch.setenv("WAVESTACK_DATA_DIR", str(tmp_path / "data"))
    config.save_setting("selected_model", {"kind": "cloud", "ref": "groq"})
    received = []
    session, app = _build(
        monkeypatch, tmp_path, models=("a.gguf",), app_session=_recording_app_session(received)
    )

    result = session.check_model()
    session.hand_to(app.state.app_session, result, launch=True)
    app.state.app_session.join()

    assert result.model_path and session.selected_cloud == "groq"
    diagnostic = _client(app).get("/api/diagnostic").json()
    assert diagnostic["loaded_model"] == result.model_path and "next_launch_text" not in diagnostic


def test_old_or_incomplete_probe_entries_are_probed_again(monkeypatch, tmp_path):
    """Lot E (E2): at launch, only the saved file about to boot is measured again when its
    entry is an older probe's (no `probe_version = 2`) or incomplete, at the window; the
    others keep their entry until chosen (`AppSession._load` probes them after the
    release). A remembered failure of the current probe wins over an older success."""
    names = ("old.gguf", "incomplete.gguf", "complete.gguf")
    session, _ = _build(monkeypatch, tmp_path, models=names)
    complete = {"rss_bytes": 1, "probe_version": probe.PROBE_VERSION, "probe_window": 4096}
    for name, fields in zip(
        names,
        (
            {"rss_bytes": 1, "kv_bytes_per_token": 128},  # story 17: no version
            {"probe_version": probe.PROBE_VERSION},  # no measure
            {**complete, "rss_eval_tokens": 512},
        ),
        strict=True,
    ):
        path = config.models_dir() / name
        stat = path.stat()
        probe.record_success(
            probe.ProbeResult(
                ok=True,
                path=str(path),
                architecture="qwen35",
                size_bytes=stat.st_size,
                mtime=stat.st_mtime,
                **fields,
            )
        )
    assert [probe.measured(str(config.models_dir() / n)) for n in names] == [False, False, True]
    windows = []
    calls = _fake_probe_ok(monkeypatch, session)
    real_run = diagnostic_module._run_probe

    def run(cmd, **kwargs):  # noqa: ANN001, ANN202
        windows.append(cmd[cmd.index("--window") + 1])
        return real_run(cmd, **kwargs)

    monkeypatch.setattr(diagnostic_module, "_run_probe", run)

    kept = session._discover(None)
    assert calls == [] and all(c.architecture == "qwen35" for c in kept)  # entries read

    session.selected_model_path = str(config.models_dir() / "old.gguf")
    assert session.check_model().model_path == session.selected_model_path
    assert [Path(c).name for c in calls] == ["old.gguf"]  # the saved one, about to boot
    assert windows == [str(session.cfg.context_window)]

    incomplete = str(config.models_dir() / "incomplete.gguf")
    monkeypatch.setattr(probe, "_llama_cpp_version", lambda: "0.3.35")
    probe.record_failure(incomplete, probe.incompatible_fr())  # its reprobe failed
    listed = session._discover(None, reprobe={incomplete})
    assert len(calls) == 1  # no endless reprobe
    failed = next(c for c in listed if c.path == incomplete)
    assert (failed.status, failed.reason) == ("incompatible", probe.incompatible_fr())


def test_transient_probe_failure_is_never_remembered(monkeypatch, tmp_path):
    """Lot E: a probe short of memory (or time) says nothing about the file."""
    import subprocess as sp

    session, _ = _build(monkeypatch, tmp_path, models=("m.gguf",))
    monkeypatch.setattr(
        session, "_probe_candidate", DiagnosticSession._probe_candidate.__get__(session)
    )
    monkeypatch.setattr(probe, "_llama_cpp_version", lambda: "0.3.35")
    path = str(config.models_dir() / "m.gguf")

    class _Done:
        returncode = 1
        stdout = probe.ProbeResult(
            ok=False, path=path, reason=probe.transient_fr(), detail="oom", transient=True
        ).model_dump_json()

    def timeout(cmd, **kwargs):  # noqa: ANN001, ANN202
        raise sp.TimeoutExpired(cmd, kwargs["timeout"])

    for run in (lambda cmd, **kw: _Done(), timeout):
        monkeypatch.setattr(diagnostic_module, "_run_probe", run)
        [candidate] = session._discover(None)
        assert (candidate.status, candidate.reason) == ("incompatible", probe.transient_fr())
        assert probe.failed_entry(path) is None
    assert diagnostic_module.PROBE_TIMEOUT_S == 300


def test_incompatible_probe_keeps_the_loader_message_as_the_cause(monkeypatch, tmp_path):
    """Lot E (E6): the reason in French, llama.cpp's own message as the technical detail."""
    session, _ = _build(monkeypatch, tmp_path, models=("bad.gguf",))
    monkeypatch.setattr(
        session, "_probe_candidate", DiagnosticSession._probe_candidate.__get__(session)
    )
    path = str(config.models_dir() / "bad.gguf")
    reason = probe.incompatible_fr()

    class _Done:
        returncode = 1
        stdout = probe.ProbeResult(
            ok=False, path=path, reason=reason, detail=f"Failed to load model from file: {path}"
        ).model_dump_json()

    monkeypatch.setattr(diagnostic_module, "_run_probe", lambda cmd, **kw: _Done())
    before = get_journal().last_seq()

    session.check_model()

    listed = next(c for c in session.last_result.candidates if c.path == path)
    assert (listed.status, listed.reason) == ("incompatible", reason)
    assert reason.startswith("llama-cpp-python") and "ne sait pas charger ce fichier" in reason
    error = [e.payload for e in get_journal().events_since(before) if e.kind == "harness_error"][0]
    assert error["message_text"] == f"Modèle incompatible : {reason}"
    assert error["cause"] == f"Failed to load model from file: {path}"
