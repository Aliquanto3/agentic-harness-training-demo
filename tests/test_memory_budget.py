"""Story 24: the memory counted right (base measured before the engine), the dynamic budget
computed once at launch, and the hot switch's probe that « Arrêter » kills at once.

No real model: fake engines, an injected RSS, the machine's RAM injected
(`config.system_memory`), and for the probe a real child process that only sleeps.
"""

from __future__ import annotations

import subprocess
import sys
import threading
import time
from pathlib import Path

import psutil
import pytest
from fake_engine import FakeEngine

from wavestack import config
from wavestack.models import discovery, probe
from wavestack.models.engine import CancelToken
from wavestack.models.load_registry import LoadRegistry, ModelChoice
from wavestack.session import diagnostic as diagnostic_module
from wavestack.session.app_session import AppSession, SendRefused
from wavestack.session.diagnostic import DiagnosticSession
from wavestack.trace.journal import get_journal

MIB = 1024**2
GIB = 1024**3
NB = " "  # the French thousands separator of the figures
PCT = " %"


def _ram(monkeypatch, total_mb: int, available_mb: int) -> None:
    monkeypatch.setattr(config, "system_memory", lambda: (total_mb * MIB, available_mb * MIB))


def _cfg(**memory) -> config.Config:
    cfg = config.load_config()
    cfg.values["memory"] = {"load_margin_mb": 0, **memory}
    return cfg


def _memory_check(cfg: config.Config) -> dict:
    mark = get_journal().last_seq()
    DiagnosticSession(cfg, port=8420).check_memory()
    return [
        e.payload
        for e in get_journal().events_since(mark)
        if e.kind == "diagnostic_check" and e.payload["check"] == "memory"
    ][-1]


# ---------- the budget (matrix rows) ----------


def test_dynamic_budget_at_its_cap(monkeypatch):
    _ram(monkeypatch, 16071, 9600)
    budget = _cfg().memory_budget

    assert (budget.bytes, budget.mode, budget.ram_limited) == (4096 * MIB, "dynamic", False)
    assert budget.calc_fr() == (
        f"plafond [memory] budget_mb de 4{NB}096 Mo, plus petit que 60{PCT} des 9{NB}600 Mo de "
        f"RAM disponibles au lancement (5{NB}760 Mo), sur 16{NB}071 Mo"
    )


def test_dynamic_budget_limited_by_the_ram(monkeypatch):
    _ram(monkeypatch, 16071, 5000)
    cfg = _cfg()

    assert cfg.memory_budget.bytes == 3000 * MIB and cfg.memory_budget.ram_limited
    check = _memory_check(cfg)
    assert (check["status"], check["blocking"]) == ("warn", False)
    assert "fermez des applications puis relancez WaveStack" in check["action_fr"]
    assert f"Budget mémoire de WaveStack : 3{NB}000 Mo" in check["message_fr"]
    assert f"RAM du poste : 16{NB}071 Mo, dont 5{NB}000 Mo disponibles" in check["message_fr"]

    registry = LoadRegistry(cfg.memory_budget, 0, rss_fn=lambda: 150 * MIB)
    refusal = registry.check("B", 3 * GIB)
    # One unit per sentence, the calculation in short (the diagnostic has it in full).
    assert (
        f"pour un budget de 2,9 Go (= 60{PCT} des 4,9 Go de RAM disponibles au lancement). "
        "Choisissez un modèle plus petit, ou fermez des applications puis relancez WaveStack."
    ) in refusal
    component = registry.check_component("le modèle d'embedding X", 3 * GIB, "embedding")
    assert (
        f"au-delà du budget de 3{NB}000 Mo (= 60{PCT} des 5{NB}000 Mo de RAM disponibles au "
        "lancement). Désactivez une brique, ou fermez des applications puis relancez WaveStack."
    ) in component
    assert "relevez [memory] budget_mb" not in component


def test_fixed_budget(monkeypatch):
    _ram(monkeypatch, 16071, 9600)  # the RAM does not set the budget
    cfg = _cfg(budget_mode="fixed", budget_mb=6144)

    assert (cfg.memory_budget.bytes, cfg.memory_budget.mode) == (6144 * MIB, "fixed")
    assert cfg.memory_budget.calc_fr().startswith(f"valeur fixe [memory] budget_mb de 6{NB}144 Mo")
    check = _memory_check(cfg)
    assert check["status"] == "ok" and check["action_fr"] is None
    assert f"Budget mémoire de WaveStack : 6{NB}144 Mo (valeur fixe" in check["message_fr"]
    refusal = LoadRegistry(cfg.memory_budget, 0, rss_fn=lambda: 0).check("B", 7 * GIB)
    assert "pour un budget de 6,0 Go (= valeur fixe [memory] budget_mb)." in refusal


def test_ram_at_the_cap_is_ok(monkeypatch):
    _ram(monkeypatch, 16071, 9600)
    check = _memory_check(_cfg())

    assert (check["status"], check["action_fr"]) == ("ok", None)
    assert f"Budget mémoire de WaveStack : 4{NB}096 Mo (plafond" in check["message_fr"]


@pytest.mark.parametrize(
    ("available_mb", "budget_mb", "said"),
    [
        (800, 512, "La RAM disponible est faible"),
        (5000, 6144, "Le budget fixe dépasse la RAM disponible au lancement"),
        (5000, 20000, "Le budget fixe dépasse la RAM totale du poste"),
    ],
)
def test_fixed_budget_warns_when_the_ram_is_short(monkeypatch, available_mb, budget_mb, said):
    _ram(monkeypatch, 16071, available_mb)
    check = _memory_check(_cfg(budget_mode="fixed", budget_mb=budget_mb))

    assert (check["status"], check["blocking"]) == ("warn", False)
    assert check["action_fr"].startswith(said)


def test_fixed_budget_with_unreadable_ram_warns(monkeypatch):
    def unreadable():  # noqa: ANN202
        raise OSError("RAM illisible")

    monkeypatch.setattr(config, "system_memory", unreadable)
    check = _memory_check(_cfg(budget_mode="fixed", budget_mb=6144))

    assert (check["status"], check["blocking"]) == ("warn", False)
    assert check["message_fr"].startswith("RAM du poste non mesurée.")


@pytest.mark.parametrize("available_mb", [0, -1])
def test_ram_said_to_be_zero_counts_as_unmeasured(monkeypatch, available_mb):
    _ram(monkeypatch, 16071, available_mb)
    budget = _cfg().memory_budget

    assert (budget.bytes, budget.measured) == (4096 * MIB, False)
    assert "RAM du poste non mesurée" in budget.calc_fr()


def test_dynamic_budget_never_below_its_floor(monkeypatch):
    _ram(monkeypatch, 16071, 100)  # 60 % of 100 Mo: 60 Mo, every load would be refused
    budget = _cfg().memory_budget

    assert budget.bytes == 512 * MIB and budget.floored and budget.ram_limited
    assert budget.calc_fr().endswith("relevé au plancher de 512 Mo")
    assert _cfg(budget_mb=300).memory_budget.bytes == 300 * MIB  # never above the cap


@pytest.mark.parametrize("value", [float("inf"), float("nan"), True, "abc", 0, -5, None])
def test_invalid_budget_mb_is_the_default(monkeypatch, value):
    _ram(monkeypatch, 16071, 12000)
    cfg = _cfg(budget_mb=value)

    assert cfg.memory_budget.cap_bytes == 4096 * MIB
    AppSession(cfg, engine_factory=lambda path, n_ctx: FakeEngine())  # never raises


@pytest.mark.parametrize(
    ("memory", "ratio", "mode"),
    [
        ({"budget_ram_ratio": 3}, 0.9, "dynamic"),
        ({"budget_ram_ratio": 0.01}, 0.1, "dynamic"),
        ({"budget_ram_ratio": "abc"}, 0.6, "dynamic"),
        ({"budget_ram_ratio": True}, 0.6, "dynamic"),
        ({"budget_mode": "turbo"}, 0.6, "dynamic"),
        ({"budget_mode": " FIXED "}, 0.6, "fixed"),
    ],
)
def test_invalid_settings_are_bounded_or_defaulted(monkeypatch, memory, ratio, mode):
    _ram(monkeypatch, 16384, 4000)
    budget = _cfg(**memory).memory_budget

    assert (budget.ratio, budget.mode) == (ratio, mode)
    if mode == "dynamic":
        assert budget.bytes == min(4096 * MIB, max(512 * MIB, int(ratio * 4000 * MIB)))


def test_unreadable_ram_gives_the_cap_and_a_warning(monkeypatch):
    def unreadable():  # noqa: ANN202
        raise OSError("RAM illisible")

    monkeypatch.setattr(config, "system_memory", unreadable)
    cfg = _cfg()

    assert cfg.memory_budget.bytes == 4096 * MIB and not cfg.memory_budget.measured
    assert "RAM du poste non mesurée" in cfg.memory_budget.calc_fr()
    check = _memory_check(cfg)
    assert (check["status"], check["blocking"]) == ("warn", False)
    assert "RAM du poste non mesurée" in check["message_fr"]


def test_budget_computed_once_and_shared_by_diagnostic_and_session(monkeypatch):
    """Never recomputed during the session: the diagnostic's figure is the refusals'."""
    _ram(monkeypatch, 16384, 5000)
    cfg = _cfg()
    session = AppSession(cfg, engine_factory=lambda path, n_ctx: FakeEngine())
    _ram(monkeypatch, 16384, 12000)  # the RAM frees up afterwards: nothing changes

    assert cfg.memory_budget.bytes == 3000 * MIB
    assert session._load_registry.budget is cfg.memory_budget
    assert f"Budget mémoire de WaveStack : 3{NB}000 Mo" in _memory_check(cfg)["message_fr"]


# ---------- the base, measured before the engine ----------


def test_refusal_never_says_zero_when_the_weights_are_little_resident():
    """C4: RSS 900 Mo with the model, the probe's share 2,5 Go: « 150 Mo », the base."""
    registry = LoadRegistry(4 * GIB, 0, rss_fn=lambda: 900 * MIB)
    registry.grant("A", 3 * GIB, share=round(2.5 * GIB), base=150 * MIB)

    refusal = registry.check("B", 4 * GIB)

    assert "WaveStack occupe 150 Mo sans le modèle actif" in refusal
    registry.grant("A", 3 * GIB, share=round(2.5 * GIB))  # without the base (lot E): 0 Mo,
    assert registry.check("B", 4 * GIB) is None  # and a 4 Go model let through


def test_what_loaded_after_the_model_still_counts():
    """`max(base, rss − share)`: weights resident, an embedding loaded afterwards."""
    registry = LoadRegistry(4 * GIB, 0, rss_fn=lambda: 150 * MIB + 2 * GIB + 300 * MIB)
    registry.grant("A", 2 * GIB, share=2 * GIB, base=150 * MIB)

    assert "WaveStack occupe 450 Mo sans le modèle actif" in registry.check("B", 4 * GIB)


def test_session_measures_the_base_just_before_the_engine(tmp_path):
    """The RSS injected changes once the engine is created: the base is the one before."""
    a, b = tmp_path / "A.gguf", tmp_path / "B.gguf"
    for path in (a, b):
        path.write_bytes(b"placeholder")
    for path, rss in ((a, round(2.5 * GIB)), (b, round(3.9 * GIB))):
        stat = path.stat()
        probe.record_success(
            probe.ProbeResult(
                ok=True,
                path=str(path),
                rss_bytes=rss,
                size_bytes=stat.st_size,
                mtime=stat.st_mtime,
                probe_version=probe.PROBE_VERSION,
                probe_window=4096,
                rss_eval_tokens=512,
                kv_bytes_per_token=None,
            )
        )
    loaded: list[str] = []

    def factory(path: str, n_ctx: int) -> FakeEngine:
        loaded.append(path)
        return FakeEngine()

    session = AppSession(
        _cfg(),
        engine_factory=factory,
        rss_fn=lambda: 900 * MIB if loaded else 150 * MIB,
    )
    assert session.boot(str(a)).result() == "ok"

    with pytest.raises(SendRefused) as refused:
        session.switch_model(ModelChoice("file", str(b)))

    assert "WaveStack occupe 150 Mo sans le modèle actif" in refused.value.reason_fr
    assert "pour un budget de 4,0 Go (= plafond [memory] budget_mb)." in refused.value.reason_fr


# ---------- the probe « Arrêter » kills ----------

SLEEPER = "import sys, time; time.sleep(60)"


def _sleeper_argv(path: str, window: int) -> list[str]:
    return [sys.executable, "-c", SLEEPER, path]  # the path last, to find the child again


def _children_with(marker: str) -> list[psutil.Process]:
    found = []
    for child in psutil.Process().children(recursive=True):
        try:
            if any(marker in part for part in child.cmdline()):
                found.append(child)
        except psutil.Error:
            continue
    return found


def _wait_for_child(marker: str, timeout: float = 10.0) -> psutil.Process:
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        if children := _children_with(marker):
            return children[0]
        time.sleep(0.05)
    raise AssertionError(f"no child process for {marker}")


def test_run_probe_kills_the_child_when_stopped(tmp_path):
    marker = str(tmp_path / "sonde-lente.gguf")
    cancel = CancelToken()
    outcome: dict = {}

    def run() -> None:
        outcome["result"] = diagnostic_module._run_probe(
            _sleeper_argv(marker, 4096), cancel=cancel, timeout=300
        )
        outcome["at"] = time.monotonic()

    worker = threading.Thread(target=run)
    worker.start()
    child = _wait_for_child(marker)
    stopped = time.monotonic()
    cancel.cancel()
    worker.join(5)

    assert not worker.is_alive() and outcome["result"] is None
    assert outcome["at"] - stopped < 2
    assert not psutil.pid_exists(child.pid)  # killed and reaped


def test_run_probe_past_its_timeout_kills_the_child(tmp_path):
    marker = str(tmp_path / "sonde-bloquee.gguf")

    with pytest.raises(subprocess.TimeoutExpired):
        diagnostic_module._run_probe(_sleeper_argv(marker, 4096), cancel=None, timeout=0.5)

    assert _children_with(marker) == []


def test_run_probe_reads_utf8_and_replaces_invalid_bytes():
    """C6: the child's output is UTF-8 on every OS (never cp1252), invalid bytes replaced."""
    code = (
        "import sys; sys.stdout.buffer.write('abîmé\\n'.encode('utf-8') + b'\\xff\\n'); "
        "sys.stdout.flush()"
    )
    done = diagnostic_module._run_probe([sys.executable, "-c", code], cancel=None, timeout=30)

    assert done is not None and done.returncode == 0
    assert done.stdout.splitlines() == ["abîmé", "�"]


def _diagnostic_and_session(monkeypatch, tmp_path):  # noqa: ANN202
    monkeypatch.setenv("OLLAMA_MODELS", str(tmp_path / "no-ollama"))
    monkeypatch.setenv("HF_HUB_CACHE", str(tmp_path / "no-hf-cache"))
    monkeypatch.setattr(discovery, "_lm_studio_dirs", lambda: [])
    monkeypatch.setattr(discovery, "_server_candidates", lambda cfg: [])
    monkeypatch.setattr(probe, "_llama_cpp_version", lambda: "0.3.35")
    a = tmp_path / "A.gguf"
    a.write_bytes(b"placeholder")
    cfg = _cfg()
    diagnostic = DiagnosticSession(cfg, port=8420)
    loaded: list[str] = []

    def factory(path: str, n_ctx: int) -> FakeEngine:
        loaded.append(Path(path).stem)
        return FakeEngine()

    session = AppSession(cfg, engine_factory=factory, rss_fn=lambda: 150 * MIB)
    assert session.boot(str(a)).result() == "ok"
    return diagnostic, session, loaded


def test_stop_during_a_slow_probe_kills_it_and_records_nothing(monkeypatch, tmp_path):
    """C4: « Arrêter » during the probe of a hot-switched file: the child is gone at once,
    the previous model is back, nothing marks the file incompatible."""
    diagnostic, session, loaded = _diagnostic_and_session(monkeypatch, tmp_path)
    monkeypatch.setattr(diagnostic_module, "_probe_argv", _sleeper_argv)
    slow = tmp_path / "sonde-lente.gguf"
    slow.write_bytes(b"any bytes")
    mark = get_journal().last_seq()

    _, future = session.switch_model(ModelChoice("file", str(slow)), probe=diagnostic.probe_path)
    child = _wait_for_child(str(slow))
    stopped = time.monotonic()
    threading.Thread(target=session.stop).start()

    assert future.result(timeout=5) == "cancelled"
    assert time.monotonic() - stopped < 2
    assert not psutil.pid_exists(child.pid)  # killed and reaped
    assert _children_with(str(slow)) == []
    assert "sonde-lente" not in loaded and session.active_model()["label"] == "A"
    assert "failed_probes" not in config.read_settings()
    assert probe.failed_entry(str(slow)) is None and probe.probed_entry(str(slow)) is None
    events = get_journal().events_since(mark)
    assert not [e for e in events if e.kind == "harness_error"]
    ended = [e.payload for e in events if e.kind == "model_load_ended"][-1]
    assert (ended["status"], ended["reason_fr"]) == (
        "cancelled",
        "Chargement arrêté : A est de nouveau actif.",
    )


def test_launch_probe_is_never_interruptible(monkeypatch, tmp_path):
    """The launch's diagnostic probes without a token: nothing can stop it (no « Arrêter »)."""
    seen: list = []
    monkeypatch.setattr(
        diagnostic_module,
        "_run_probe",
        lambda argv, cancel, timeout: seen.append(cancel) or None,
    )
    diagnostic, _, _ = _diagnostic_and_session(monkeypatch, tmp_path)
    candidate = discovery.ModelCandidate(
        source="explicit", status="found", path=str(tmp_path / "A.gguf"), name="A.gguf"
    )

    diagnostic._probe_candidate(candidate)

    assert seen == [None]


def test_probe_ending_in_the_slice_of_the_stop_records_nothing(monkeypatch, tmp_path):
    """The child ends (a failure) in the very slice « Arrêter » is pressed: the load reports
    `cancelled`, so nothing is recorded against the file."""
    diagnostic, _, _ = _diagnostic_and_session(monkeypatch, tmp_path)
    path = tmp_path / "course.gguf"
    path.write_bytes(b"bad")
    cancel = CancelToken()

    def ended_as_stopped(argv, cancel, timeout):  # noqa: ANN001, ANN202
        cancel.cancel()  # pressed while the child was ending
        failure = probe.ProbeResult(ok=False, path=argv[-1], reason="Architecture inconnue.")
        return subprocess.CompletedProcess(argv, 1, failure.model_dump_json(), "")

    monkeypatch.setattr(diagnostic_module, "_run_probe", ended_as_stopped)
    mark = get_journal().last_seq()

    assert diagnostic.probe_path(str(path), cancel) is None
    assert probe.failed_entry(str(path)) is None and "failed_probes" not in config.read_settings()
    assert not [e for e in get_journal().events_since(mark) if e.kind == "harness_error"]


def test_run_probe_checks_the_stop_before_returning_a_result():
    cancel = CancelToken()
    cancel.cancel()  # set while the child was already done

    done = diagnostic_module._run_probe(
        [sys.executable, "-c", "print('fini')"], cancel=cancel, timeout=30
    )

    assert done is None
