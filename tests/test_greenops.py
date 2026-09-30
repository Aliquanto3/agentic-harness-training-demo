"""GreenOps: the estimated footprint (Wh, g CO₂e) of each model call, the turn and the session.

Cloud calls go through the real EcoLogits (offline, its core only). Local calls play
CodeCarbon with a double (`FakeTracker`); `test_real_codecarbon_*` runs the real tracker,
skipped without the `greenops` extra.
"""

from __future__ import annotations

import json
import os
import subprocess
import sys
import textwrap
import time
from pathlib import Path
from types import SimpleNamespace

import httpx
import pytest
from fake_engine import FakeEngine, booted_session
from test_cloud import (
    GEMINI_TEXT,
    GROQ_TEXT,
    ORIGIN,
    SENTINEL,
    GeminiProvider,
    Provider,
    _app,
    _cloud_session,
    _of,
    _turn,
    delta,
    gemini_call,
    gemini_delta,
    gemini_usage,
    sse,
)
from test_model_servers import FakeServer, _booted

from wavestack import config, greenops
from wavestack.models import servers
from wavestack.models.load_registry import GREENOPS_CODECARBON
from wavestack.trace.catalog import (
    ConsumptionUpdatedPayload,
    ModelCallEndedPayload,
    TurnEndedPayload,
)

REPO = Path(__file__).resolve().parents[1]
KWH = 2e-6  # what the double's tracker measures for a call
_FIND_SPEC = greenops._find_spec  # the real one, before `conftest` plays CodeCarbon absent


class FakeTracker:
    """CodeCarbon's `OfflineEmissionsTracker`, as a double: it records its arguments."""

    made: list[FakeTracker] = []
    fail_stop = False

    def __init__(self, **kwargs) -> None:
        self.kwargs = kwargs
        self.started = self.stopped = False
        FakeTracker.made.append(self)

    def start(self) -> None:
        self.started = True

    energy = KWH

    def stop(self) -> None:
        self.stopped = True
        if FakeTracker.fail_stop:  # as CodeCarbon, which swallows its errors: no data
            return
        self.final_emissions_data = SimpleNamespace(
            energy_consumed=FakeTracker.energy, gpu_energy=0.0
        )


@pytest.fixture
def codecarbon(monkeypatch):
    """CodeCarbon installed, as a double; `loads` counts its imports."""
    FakeTracker.made, FakeTracker.fail_stop, FakeTracker.energy = [], False, KWH
    loads: list[int] = []

    def load():
        loads.append(1)
        return SimpleNamespace(OfflineEmissionsTracker=FakeTracker, count_physical_cpus=lambda: 1)

    monkeypatch.setattr(greenops, "_find_spec", lambda name: object())
    monkeypatch.setattr(greenops, "_load_codecarbon", load)
    return loads


@pytest.fixture
def fake(monkeypatch) -> FakeServer:
    server = FakeServer()
    monkeypatch.setattr(servers, "default_transport", httpx.MockTransport(server))
    return server


def _ready(session) -> None:
    """The background warm-up of CodeCarbon done, its discarded tracker forgotten."""
    if session._greenops_warm_up is not None:
        session._greenops_warm_up.join(10)
        session._greenops_warm_up = None
        FakeTracker.made.clear()


def _local_turn(session) -> dict[str, list]:
    _ready(session)
    events = _turn(session, "Bonjour")
    return {kind: [e.payload for e in _of(events, kind)] for kind in {e.kind for e in events}}


# ---------- cloud: EcoLogits ----------


def test_a_known_cloud_model_gets_a_range_and_its_warnings_in_french():
    entry = config.load_config().cloud_model("gemini")

    impact = greenops.cloud_impacts(entry, 1000, 5.0)

    assert impact.method == "ecologits" and impact.estimated
    assert 0 < impact.energy_wh_min < impact.energy_wh_max
    assert 0 < impact.gco2e_min < impact.gco2e_max
    assert "architecture non publiée" in impact.note_fr and "multimodal" in impact.note_fr
    assert "fourchette" in impact.note_fr


def test_groq_is_estimated_as_gpt_oss_at_hugging_face():
    entry = config.load_config().cloud_model("groq")
    assert (entry.impacts.provider, entry.impacts.model) == (
        "huggingface_hub",
        "openai/gpt-oss-120b",
    )

    impact = greenops.cloud_impacts(entry, 500, 2.0)

    assert impact.method == "ecologits" and impact.energy_wh_min > 0 and impact.gco2e_max > 0


def test_mistral_has_a_single_value_and_a_zone_changes_the_emissions():
    entry = config.load_config().cloud_model("mistral")
    impact = greenops.cloud_impacts(entry, 1000, 5.0)
    assert impact.energy_wh_min == impact.energy_wh_max > 0
    assert "fourchette" not in impact.note_fr

    french = entry.model_copy(update={"impacts": entry.impacts.model_copy(update={"zone": "FRA"})})
    in_france = greenops.cloud_impacts(french, 1000, 5.0)

    assert in_france.energy_wh_min == pytest.approx(impact.energy_wh_min)
    assert in_france.gco2e_min != pytest.approx(impact.gco2e_min)
    assert "zone électrique : FRA" in in_france.note_fr


def test_a_cloud_entry_without_impacts_has_no_footprint_and_says_why():
    entry = config.load_config().cloud_model("gemini").model_copy(update={"impacts": None})

    impact = greenops.cloud_impacts(entry, 1000, 5.0)

    assert not impact.estimated and impact.fields() == {"impact_note_fr": impact.note_fr}
    assert "aucune correspondance EcoLogits" in impact.note_fr


def test_a_model_ecologits_does_not_know_has_no_footprint_and_says_why():
    entry = config.load_config().cloud_model("gemini")
    unknown = entry.model_copy(
        update={"impacts": entry.impacts.model_copy(update={"model": "gemini-inconnu"})}
    )

    impact = greenops.cloud_impacts(unknown, 1000, 5.0)

    assert not impact.estimated
    assert "ne connaît pas le modèle « gemini-inconnu »" in impact.note_fr


def test_an_ecologits_failure_is_caught(monkeypatch):
    def broken(*args):
        raise KeyError("fournisseur")

    monkeypatch.setattr(greenops, "_llm_impacts", lambda: broken)
    entry = config.load_config().cloud_model("gemini")

    impact = greenops.cloud_impacts(entry, 1000, 5.0)

    assert not impact.estimated and "EcoLogits a échoué (KeyError" in impact.note_fr


def test_an_invalid_zone_leaves_the_entry_out_with_the_reason():
    settings = {
        "cloud": {
            "models": [{"id": "gemini", "impacts": {"provider": "x", "model": "y", "zone": "fr"}}]
        }
    }
    config.settings_path().parent.mkdir(parents=True, exist_ok=True)
    config.settings_path().write_text(json.dumps(settings), encoding="utf-8")

    valid, errors = config.load_config().cloud_models

    assert "gemini" not in [m.id for m in valid]
    (error,) = [e for e in errors if "gemini" in e]
    assert "impacts.zone" in error


def test_a_gemini_turn_carries_the_footprint_of_its_call_the_turn_and_the_session():
    """1 000 output tokens (thinking included): EcoLogits' range in `model_call_ended`, its
    sums in `turn_ended`, the session's in `consumption_updated` next to the spend."""
    usage = gemini_usage(65, 14, 986)
    stream = sse(gemini_delta(content="Bonjour.", usage=usage), gemini_delta("stop", usage=usage))
    session = _cloud_session("gemini", GeminiProvider(stream))

    events = _turn(session, "Bonjour")

    (ended,) = (e.payload for e in _of(events, "model_call_ended"))
    ModelCallEndedPayload.model_validate(ended)
    assert ended["impact_method"] == "ecologits"
    assert 0 < ended["energy_wh_min"] < ended["energy_wh_max"]
    assert 0 < ended["gco2e_min"] < ended["gco2e_max"]
    assert "architecture non publiée" in ended["impact_note_fr"]
    expected = greenops.cloud_impacts(
        session.cfg.cloud_model("gemini"), 1000, ended["duration_ms"] / 1000
    )
    assert ended["energy_wh_min"] == pytest.approx(expected.energy_wh_min)
    (turn_ended,) = (e.payload for e in _of(events, "turn_ended"))
    TurnEndedPayload.model_validate(turn_ended)
    for key in ("energy_wh_min", "energy_wh_max", "gco2e_min", "gco2e_max"):
        assert turn_ended[key] == pytest.approx(ended[key])
    (spend,) = (e.payload for e in _of(events, "consumption_updated"))
    ConsumptionUpdatedPayload.model_validate(spend)
    assert spend["calls"] == 1 and spend["impact_calls"] == 1
    assert spend["gco2e_max"] == pytest.approx(ended["gco2e_max"])
    assert session.consumption() == spend


def test_a_cloud_call_without_prices_still_counts_its_footprint():
    settings = {"cloud": {"models": [{"id": "groq", "pricing": None}]}}
    config.settings_path().parent.mkdir(parents=True, exist_ok=True)
    config.settings_path().write_text(json.dumps(settings), encoding="utf-8")
    session = _cloud_session("groq", Provider(GROQ_TEXT))

    events = _turn(session, "Bonjour")

    (ended,) = (e.payload for e in _of(events, "model_call_ended"))
    assert "cost_in_usd" not in ended and ended["impact_method"] == "ecologits"
    (spend,) = (e.payload for e in _of(events, "consumption_updated"))
    assert spend["calls"] == 0 and spend["total_usd"] == 0 and spend["impact_calls"] == 1
    assert "cost_in_usd" not in _of(events, "turn_ended")[0].payload
    assert _of(events, "turn_ended")[0].payload["energy_wh_min"] > 0


def test_a_cloud_entry_without_impacts_says_why_and_leaves_the_footprint_alone():
    settings = {"cloud": {"models": [{"id": "gemini", "impacts": None}]}}
    config.settings_path().parent.mkdir(parents=True, exist_ok=True)
    config.settings_path().write_text(json.dumps(settings), encoding="utf-8")
    session = _cloud_session("gemini", GeminiProvider(GEMINI_TEXT))

    events = _turn(session, "Bonjour")

    (ended,) = (e.payload for e in _of(events, "model_call_ended"))
    assert "energy_wh_min" not in ended and "impact_method" not in ended
    assert "aucune correspondance EcoLogits" in ended["impact_note_fr"]
    (spend,) = (e.payload for e in _of(events, "consumption_updated"))
    assert spend["calls"] == 1 and spend["impact_calls"] == 0
    assert "energy_wh_min" not in _of(events, "turn_ended")[0].payload


def test_groqs_note_says_the_estimate_goes_through_hugging_face():
    entry = config.load_config().cloud_model("groq")

    impact = greenops.cloud_impacts(entry, 500, 2.0)

    assert impact.note_fr.endswith(
        "EcoLogits ne connaît pas Groq (puces LPU) : estimation par gpt-oss-120b sur GPU chez "
        "Hugging Face."
    )


def test_a_cloud_call_cut_by_an_error_after_its_output_keeps_its_footprint():
    error = {"error": {"message": "Internal error", "code": 500}}
    session = _cloud_session("gemini", GeminiProvider(sse(delta(content="Il est"), error)))

    events = _turn(session, "Quelle heure est-il ?")

    (ended,) = (e.payload for e in _of(events, "model_call_ended"))
    assert ended["stop_reason"] == "error" and ended["energy_wh_min"] > 0
    turn_ended = _of(events, "turn_ended")[0].payload
    assert turn_ended["status"] == "error"
    for key in ("energy_wh_min", "energy_wh_max", "gco2e_min", "gco2e_max"):
        assert turn_ended[key] == pytest.approx(ended[key])
    (spend,) = (e.payload for e in _of(events, "consumption_updated"))
    assert spend["impact_calls"] == 1


def test_the_turn_sums_the_footprint_of_the_sub_agent():
    provider = GeminiProvider(
        gemini_call("delegate", '{"task": "Lis notes_reunion.txt."}', "p1", "sig-principal"),
        gemini_call("read_file", '{"path": "notes_reunion.txt"}', "p2", "sig-sous-agent"),
        GEMINI_TEXT,
        GEMINI_TEXT,
    )
    session = _cloud_session("gemini", provider, bricks=("tools", "subagent"))

    events = _turn(session, "Quelles décisions ?")

    calls = _of(events, "model_call_ended")
    assert len(calls) == 4 and any((c.context_id or "").startswith("sub") for c in calls)
    turn_ended = _of(events, "turn_ended")[0].payload
    for key in ("energy_wh_min", "energy_wh_max", "gco2e_min", "gco2e_max"):
        assert turn_ended[key] == pytest.approx(sum(c.payload[key] for c in calls))
    counts = [e.payload["impact_calls"] for e in _of(events, "consumption_updated")]
    assert counts == [1, 2, 3, 4]


def test_tester_and_the_llm_screen_add_to_the_session_footprint(monkeypatch):
    from wavestack.models.engine import Sampling
    from wavestack.trace.journal import get_journal

    provider = GeminiProvider(GEMINI_TEXT)
    _, app_session, _, client = _app(monkeypatch, provider)
    client.post(
        "/api/intentions/set_api_key", json={"id": "gemini", "key": SENTINEL}, headers=ORIGIN
    )
    mark = get_journal().last_seq()

    client.post("/api/intentions/test_cloud_model", json={"id": "gemini"}, headers=ORIGIN)

    tested = [e for e in get_journal().events_since(mark) if e.kind == "consumption_updated"]
    assert tested and tested[-1].payload["impact_calls"] == len(tested)
    assert all(e.context_id == "diag" for e in tested)
    session = _cloud_session("gemini", GeminiProvider(GEMINI_TEXT))
    mark = get_journal().last_seq()

    session.llm_generate("Bonjour", Sampling(temperature=0.2, top_k=5, top_p=0.9, min_p=0.05))
    session.join()

    (spend,) = [e for e in get_journal().events_since(mark) if e.kind == "consumption_updated"]
    assert spend.context_id == "llm"
    assert spend.payload["impact_calls"] == len(tested) + 1
    assert spend.payload["gco2e_max"] > tested[-1].payload["gco2e_max"]


def test_a_refused_cloud_call_has_no_footprint():
    provider = Provider(httpx.Response(401, json={"error": {"message": "Invalid API Key"}}))
    session = _cloud_session("gemini", provider)

    events = _turn(session, "Bonjour")

    (ended,) = (e.payload for e in _of(events, "model_call_ended"))
    assert ended["stop_reason"] == "error" and "impact_method" not in ended
    assert "impact_note_fr" not in ended and session.consumption() is None


# ---------- local: CodeCarbon ----------


def test_a_local_call_on_the_embedded_engine_is_measured_in_process(codecarbon):
    session = booted_session(FakeEngine())

    events = _local_turn(session)

    (tracker,) = FakeTracker.made
    assert tracker.kwargs == {
        "country_iso_code": "FRA",
        "save_to_file": False,
        "log_level": "error",
        "measure_power_secs": 1,
        "tracking_mode": "process",
    }
    assert tracker.started and tracker.stopped
    (ended,) = events["model_call_ended"]
    ModelCallEndedPayload.model_validate(ended)
    assert ended["impact_method"] == "codecarbon"
    assert ended["energy_wh_min"] == ended["energy_wh_max"] == pytest.approx(KWH * 1000)
    assert ended["gco2e_min"] == pytest.approx(KWH * 41.4)
    assert "estimation (TDP × charge, sans droits administrateur)" in ended["impact_note_fr"]
    assert "processus de WaveStack seul" in ended["impact_note_fr"]
    (spend,) = events["consumption_updated"]
    assert spend["calls"] == 0 and spend["total_usd"] == 0 and spend["impact_calls"] == 1
    assert spend["gco2e_max"] == pytest.approx(KWH * 41.4)
    (turn_ended,) = events["turn_ended"]
    assert turn_ended["status"] == "completed"
    assert turn_ended["energy_wh_max"] == pytest.approx(KWH * 1000)
    assert "cost_in_usd" not in turn_ended
    assert session.consumption() == spend


def test_the_local_intensity_comes_from_the_configuration(codecarbon):
    session = booted_session(FakeEngine(), values={"greenops": {"local_gco2e_per_kwh": 100}})

    (ended,) = _local_turn(session)["model_call_ended"]

    assert ended["gco2e_min"] == pytest.approx(KWH * 100)
    assert "100 g CO₂e par kWh" in ended["impact_note_fr"]


def test_the_local_intensity_is_bounded():
    assert config.Config(values={}).local_gco2e_per_kwh == 41.4
    assert config.Config(values={"greenops": {"local_gco2e_per_kwh": 29}}).local_gco2e_per_kwh == 29
    assert config.Config(values={"greenops": {"local_gco2e_per_kwh": -5}}).local_gco2e_per_kwh == 0
    for unreadable in ("abc", "nan", "inf", None):
        values = {"greenops": {"local_gco2e_per_kwh": unreadable}}
        assert config.Config(values=values).local_gco2e_per_kwh == 41.4
    assert config.Config(values={}).greenops_codecarbon_cost_bytes == 80 * 1024 * 1024
    for unreadable in (float("inf"), float("nan"), "abc"):
        values = {"greenops": {"codecarbon_cost_mb": unreadable}}
        assert config.Config(values=values).greenops_codecarbon_cost_bytes == 80 * 1024 * 1024


def test_the_default_intensity_is_ecologits_france_factor():
    from ecologits.electricity_mix_repository import electricity_mixes

    france = electricity_mixes.find_electricity_mix(zone="FRA")

    assert config.DEFAULT_LOCAL_GCO2E_PER_KWH == pytest.approx(france.gwp * 1000, abs=0.05)


def test_without_the_extra_a_local_turn_ends_and_gives_the_command():
    """The default of the tests (`conftest`): CodeCarbon absent."""
    session = booted_session(FakeEngine())

    events = _local_turn(session)

    assert events["turn_ended"][0]["status"] == "completed"
    (ended,) = events["model_call_ended"]
    assert "energy_wh_min" not in ended and "impact_method" not in ended
    assert "uv sync --extra greenops" in ended["impact_note_fr"]
    assert "consumption_updated" not in events and session.consumption() is None


@pytest.mark.parametrize("engine", ["llama_server", "ollama"])
def test_a_served_model_is_measured_on_the_whole_machine(codecarbon, fake, engine):
    session = _booted(engine)

    events = _local_turn(session)

    (tracker,) = FakeTracker.made
    assert tracker.kwargs["tracking_mode"] == "machine"
    (ended,) = events["model_call_ended"]
    assert ended["impact_method"] == "codecarbon" and "poste entier" in ended["impact_note_fr"]


def test_codecarbon_is_counted_once_by_the_memory_budget(codecarbon):
    session = booted_session(FakeEngine())  # its warm-up imports CodeCarbon

    _local_turn(session)
    _local_turn(session)

    assert codecarbon == [1] and len(FakeTracker.made) == 2
    assert session._load_registry.holder(GREENOPS_CODECARBON) == "CodeCarbon"


def test_codecarbon_refused_by_the_budget_leaves_the_local_footprint_unavailable(codecarbon):
    values = {"greenops": {"codecarbon_cost_mb": 10**8}}  # far past any budget
    session = booted_session(FakeEngine(), values=values)

    events = _local_turn(session)

    assert events["turn_ended"][0]["status"] == "completed"
    (ended,) = events["model_call_ended"]
    assert "energy_wh_min" not in ended
    assert ended["impact_note_fr"].startswith(
        "Empreinte locale indisponible : Mémoire insuffisante"
    )
    assert codecarbon == [] and FakeTracker.made == []
    assert session._load_registry.holder(GREENOPS_CODECARBON) is None


def test_the_warm_up_imports_codecarbon_in_the_background_without_counting(codecarbon):
    session = booted_session(FakeEngine())
    session._greenops_warm_up.join(10)

    assert codecarbon == [1]
    assert session._load_registry.holder(GREENOPS_CODECARBON) == "CodeCarbon"
    (tracker,) = FakeTracker.made  # the CPU detected once, then discarded
    assert tracker.started and tracker.stopped
    assert session.consumption() is None


def test_a_local_call_that_fails_before_any_token_has_no_footprint(codecarbon):
    session = booted_session(FakeEngine(fail=True))

    events = _local_turn(session)

    (ended,) = events["model_call_ended"]
    assert ended["stop_reason"] == "error"
    assert "energy_wh_min" not in ended and "impact_note_fr" not in ended
    (tracker,) = FakeTracker.made
    assert tracker.stopped  # stopped whatever happened
    assert "consumption_updated" not in events and session.consumption() is None


def test_an_unexpected_error_still_stops_the_tracker(codecarbon, monkeypatch):
    session = booted_session(FakeEngine())
    _ready(session)

    def broken(*args, **kwargs):
        raise RuntimeError("panne imprévue")

    monkeypatch.setattr(session, "_call_model_local", broken)
    with pytest.raises(RuntimeError):
        session._call_model(object(), None, (), 64)

    (tracker,) = FakeTracker.made
    assert tracker.started and tracker.stopped


def test_an_infinite_energy_is_no_footprint(codecarbon):
    FakeTracker.energy = float("inf")
    session = booted_session(FakeEngine())

    (ended,) = _local_turn(session)["model_call_ended"]

    assert "energy_wh_min" not in ended
    assert "CodeCarbon a rendu une énergie invalide" in ended["impact_note_fr"]


def test_a_zero_energy_says_why(codecarbon):
    FakeTracker.energy = 0.0
    session = booted_session(FakeEngine())

    (ended,) = _local_turn(session)["model_call_ended"]

    assert ended["energy_wh_min"] == 0 and "aucune énergie" in ended["impact_note_fr"]


def test_start_never_raises_and_grants_nothing_on_a_broken_module(monkeypatch):
    granted: list[int] = []
    monkeypatch.setattr(greenops, "_find_spec", lambda name: object())
    monkeypatch.setattr(greenops, "_load_codecarbon", lambda: SimpleNamespace())
    meter = greenops.LocalMeter(41.4, grant=lambda: granted.append(1))

    impact = meter.start(False).stop()

    assert not impact.estimated
    assert "CodeCarbon n'a pas démarré (AttributeError)" in impact.note_fr
    assert granted == []

    def refusing() -> str:
        raise RuntimeError("registre")

    other = greenops.LocalMeter(41.4, check=refusing)
    assert "RuntimeError" in other.start(True).stop().note_fr


def test_a_failed_measure_never_stops_the_turn(codecarbon):
    FakeTracker.fail_stop = True
    session = booted_session(FakeEngine())

    events = _local_turn(session)

    assert events["turn_ended"][0]["status"] == "completed"
    (ended,) = events["model_call_ended"]
    assert "energy_wh_min" not in ended
    assert "CodeCarbon n'a pas rendu de mesure" in ended["impact_note_fr"]
    assert "consumption_updated" not in events


def test_a_broken_codecarbon_install_is_said_once(monkeypatch):
    loads: list[int] = []

    def load():
        loads.append(1)
        raise OSError("DLL bloquée")

    monkeypatch.setattr(greenops, "_find_spec", lambda name: object())
    monkeypatch.setattr(greenops, "_load_codecarbon", load)
    meter = greenops.LocalMeter(41.4)

    first, second = meter.start(False).stop(), meter.start(False).stop()

    assert loads == [1] and not first.estimated and first == second
    assert "CodeCarbon n'a pas pu être chargé (OSError : DLL bloquée)" in first.note_fr


def test_a_gemini_turn_then_a_local_one_add_up_in_the_session(codecarbon, monkeypatch):
    usage = gemini_usage(65, 14, 986)
    stream = sse(gemini_delta(content="Bonjour.", usage=usage), gemini_delta("stop", usage=usage))
    cloud = _cloud_session("gemini", GeminiProvider(stream))
    (cloud_call,) = (e.payload for e in _of(_turn(cloud, "Bonjour"), "model_call_ended"))
    local = booted_session(FakeEngine())

    events = _local_turn(local)

    (spend,) = events["consumption_updated"]
    assert spend["calls"] == 1 and spend["impact_calls"] == 2
    assert spend["energy_wh_min"] == pytest.approx(cloud_call["energy_wh_min"] + KWH * 1000)
    assert spend["gco2e_max"] == pytest.approx(cloud_call["gco2e_max"] + KWH * 41.4)


# ---------- no network, no file ----------

_OFFLINE = textwrap.dedent(
    """
    import json, sys, time

    from wavestack.net import guard

    guard.install([])  # WaveStack's network guard, nothing allowed
    seen = []
    sys.addaudithook(
        lambda event, args: seen.append([event, repr(args)[:120]])
        if event in ("socket.getaddrinfo", "socket.connect", "socket.gethostbyname")
        else None
    )
    from wavestack import config, greenops

    cfg = config.load_config()
    impacts = [greenops.cloud_impacts(cfg.cloud_model(i), 800, 3.0).estimated
               for i in ("groq", "mistral", "gemini")]
    local = None
    if greenops._find_spec("codecarbon") is not None:
        measure = greenops.LocalMeter(41.4).start(machine=False)
        end = time.monotonic() + 1.5
        while time.monotonic() < end:
            pass
        local = measure.stop().estimated
    print(json.dumps({"impacts": impacts, "local": local, "seen": seen}))
    """
)


def test_ecologits_and_the_offline_tracker_never_reach_the_network(tmp_path):
    """Under WaveStack's network guard (nothing allowed), with an audit hook recording every
    resolution and connection: none, and no `emissions.csv` written."""
    env = {**os.environ, "PYTHONUTF8": "1", "WAVESTACK_DATA_DIR": str(tmp_path / "data")}
    result = subprocess.run(
        [sys.executable, "-c", _OFFLINE],
        cwd=tmp_path,
        env=env,
        capture_output=True,
        text=True,
        timeout=180,
    )

    assert result.returncode == 0, result.stderr[-2000:]
    report = json.loads(result.stdout.strip().splitlines()[-1])
    assert report["impacts"] == [True, True, True]
    # With the extra, the real tracker ran and measured.
    assert report["local"] is (True if _FIND_SPEC("codecarbon") is not None else None)
    assert report["seen"] == []
    assert not list(tmp_path.glob("*.csv")) and not (REPO / "emissions.csv").exists()


def test_real_codecarbon_measures_a_local_call(monkeypatch):
    pytest.importorskip("codecarbon")
    monkeypatch.setattr(greenops, "_find_spec", _FIND_SPEC)
    meter = greenops.LocalMeter(41.4)
    measure = meter.start(machine=False)
    end = time.monotonic() + 1.5
    while time.monotonic() < end:  # a busy process, as during a generation
        pass

    impact = measure.stop()

    assert impact.estimated and impact.method == "codecarbon", impact.note_fr
    assert impact.energy_wh_min > 0
    assert impact.gco2e_min == pytest.approx(impact.energy_wh_min / 1000 * 41.4)
