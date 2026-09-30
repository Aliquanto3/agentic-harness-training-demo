"""GreenOps: the estimated energy (Wh) and emissions (g CO₂e) of a model call.

The only module that imports EcoLogits and CodeCarbon, both lazily, and neither ever reaches
the network:
- a cloud call: EcoLogits' method (`llm_impacts`, its core only: no `EcoLogits.init()`, no
  SDK instrumented), from the output tokens and the latency, as a range (min, max);
- a local call: CodeCarbon's offline tracker around the generation (the optional extra
  `greenops`), its energy only, converted at `[greenops] local_gco2e_per_kwh`. Under Windows
  without RAPL, CodeCarbon estimates the power (TDP × load): an estimate, not a measure.

An estimate that fails never stops a call: the call has no footprint and says why
(`note_text`).
"""

from __future__ import annotations

import functools
import importlib
import importlib.util
import logging
import math
import threading
import warnings
from collections.abc import Callable
from dataclasses import dataclass, field
from typing import Any

from wavestack.config import CloudModel

logger = logging.getLogger(__name__)

ECOLOGITS = "ecologits"
CODECARBON = "codecarbon"
INSTALL_FR = "uv sync --extra greenops"
COUNTRY = "FRA"  # the local mix is `[greenops] local_gco2e_per_kwh`; this only names it

# EcoLogits' warnings, in French (its codes, `ecologits.status_messages`).
_WARNINGS_FR = {
    "model-arch-not-released": "architecture non publiée, précision moindre",
    "model-arch-multimodal": "modèle multimodal, précision moindre",
    "electricity-mix-adpe-world": "facteur ADPe du mix mondial par défaut, précision moindre",
    "electricity-mix-pe-world": "facteur d'énergie primaire du mix mondial par défaut",
    "electricity-mix-wue-world": "facteur d'eau du mix mondial par défaut",
}


@dataclass(frozen=True)
class Impact:
    """One call's footprint: energy in Wh and emissions in g CO₂e, each as a range (min =
    max for a single value); `method` is `ecologits` or `codecarbon`. Without figures, the
    call has no footprint and `note_text` says why."""

    method: str
    note_text: str | None = None
    energy_wh_min: float | None = None
    energy_wh_max: float | None = None
    gco2e_min: float | None = None
    gco2e_max: float | None = None

    @property
    def estimated(self) -> bool:
        return self.energy_wh_min is not None

    def fields(self) -> dict[str, Any]:
        """`model_call_ended`'s footprint fields: the figures and the method when estimated,
        and the note (the method's limits, or why there is no footprint)."""
        out: dict[str, Any] = {}
        if self.estimated:
            out |= {
                "energy_wh_min": self.energy_wh_min,
                "energy_wh_max": self.energy_wh_max,
                "gco2e_min": self.gco2e_min,
                "gco2e_max": self.gco2e_max,
                "impact_method": self.method,
            }
        if self.note_text:
            out["impact_note_text"] = self.note_text
        return out


def _number_fr(value: float) -> str:
    """An intensity, French comma (« 41,4 »)."""
    return f"{value:.4g}".replace(".", ",")


# ---------- cloud: EcoLogits ----------


@functools.cache
def _llm_impacts() -> Callable[..., Any]:
    """`ecologits.tracers.utils.llm_impacts`, imported once. EcoLogits sets its own logger
    class for every logger created after its import: the previous one is put back, and its
    warnings (said in French in `note_text`) stay out of the console."""
    previous = logging.getLoggerClass()
    try:
        from ecologits.tracers.utils import llm_impacts
    finally:
        logging.setLoggerClass(previous)
    logging.getLogger("ecologits").setLevel(logging.ERROR)
    return llm_impacts


def _bounds(value: Any) -> tuple[float, float]:
    """An EcoLogits value: a `RangeValue` (min, max) or a single number."""
    low, high = getattr(value, "min", value), getattr(value, "max", value)
    return float(low), float(high)


def cloud_impacts(entry: CloudModel, output_tokens: int, latency_s: float) -> Impact:
    """EcoLogits' estimate of one cloud call: its output tokens (the reasoning included) and
    its latency (`duration_ms`), under the entry's `impacts` names. Without them, or for a
    model EcoLogits does not know, no figures and the reason."""
    declared = entry.impacts
    if declared is None:
        return Impact(
            ECOLOGITS,
            "Empreinte non estimée : aucune correspondance EcoLogits n'est déclarée pour ce "
            "modèle (champ impacts de son entrée [[cloud.models]]).",
        )
    try:
        result = _llm_impacts()(
            declared.provider, declared.model, output_tokens, latency_s, declared.zone
        )
    except Exception as exc:  # noqa: BLE001 - an estimate never stops a call
        logger.warning("EcoLogits a échoué : %s", exc)
        return Impact(
            ECOLOGITS,
            f"Empreinte non estimée : EcoLogits a échoué ({type(exc).__name__} : {exc}).",
        )
    errors = {e.code for e in result.errors or []}
    if "model-not-registered" in errors:
        why = (
            f"EcoLogits ne connaît pas le modèle « {declared.model} » chez le fournisseur "
            f"« {declared.provider} » (champ impacts de l'entrée)"
        )
    elif "zone-not-registered" in errors:
        why = f"EcoLogits ne connaît pas la zone électrique « {declared.zone} »"
    elif errors or result.energy is None or result.gwp is None:
        why = "EcoLogits n'a pas rendu d'estimation" + (
            f" ({', '.join(sorted(errors))})" if errors else ""
        )
    else:
        why = None
    if why is not None:
        return Impact(ECOLOGITS, f"Empreinte non estimée : {why}.")
    kwh_min, kwh_max = _bounds(result.energy.value)
    kg_min, kg_max = _bounds(result.gwp.value)
    warnings = [_WARNINGS_FR.get(w.code, w.code) for w in result.warnings or []]
    zone = declared.zone or "celle du fournisseur dans EcoLogits"
    note = (
        f"Méthode EcoLogits (hors ligne), modèle « {declared.model} » chez « "
        f"{declared.provider} », zone électrique : {zone} ; estimation à partir des tokens de "
        "sortie (raisonnement compris) et de la durée de l'appel, en cycle de vie : "
        "l'électricité des serveurs et une part de leur fabrication"
    )
    if kwh_min != kwh_max:
        note += " ; fourchette (min–max) selon les hypothèses d'EcoLogits"
    if warnings:
        note += " ; avertissements : " + " ; ".join(warnings)
    if declared.note_text:  # what the estimate stands for (Groq through Hugging Face)
        note += f". {declared.note_text.rstrip('.')}"
    return Impact(
        ECOLOGITS,
        note + ".",
        kwh_min * 1000,
        kwh_max * 1000,
        kg_min * 1000,
        kg_max * 1000,
    )


# ---------- local: CodeCarbon ----------


def _find_spec(name: str) -> Any:
    """`importlib.util.find_spec`, replaced by the tests to play an absent extra."""
    try:
        return importlib.util.find_spec(name)
    except (ImportError, ValueError):
        return None


def _load_codecarbon() -> Any:
    """CodeCarbon's tracker module, imported (replaced by the tests with a double)."""
    return importlib.import_module("codecarbon.emissions_tracker")


def missing_fr() -> str:
    return (
        "Empreinte locale indisponible : CodeCarbon n'est pas installé. Installez l'extra "
        f"GreenOps depuis le dossier de WaveStack (`{INSTALL_FR}`, ajoutez vos autres extras), "
        "puis relancez WaveStack."
    )


@dataclass
class Measure:
    """One local call's tracker, started; `stop()` gives its footprint, once (a second call
    gives the same). Without a tracker, `note_text` says why."""

    tracker: Any
    machine: bool
    gco2e_per_kwh: float
    note_text: str | None = None
    _impact: Impact | None = field(default=None, init=False)

    def stop(self) -> Impact:
        if self._impact is None:
            self._impact = self._stop()
        return self._impact

    def _stop(self) -> Impact:
        if self.tracker is None:
            return Impact(CODECARBON, self.note_text)
        try:
            self.tracker.stop()  # CodeCarbon swallows its own errors: read what it kept
            data = getattr(self.tracker, "final_emissions_data", None)
            kwh = float(data.energy_consumed) - float(getattr(data, "gpu_energy", 0) or 0)
        except Exception as exc:  # noqa: BLE001 - an estimate never stops a call
            logger.warning("CodeCarbon a échoué : %s", exc)
            return Impact(
                CODECARBON,
                "Empreinte non estimée : CodeCarbon n'a pas rendu de mesure "
                f"({type(exc).__name__}).",
            )
        if not math.isfinite(kwh):
            return Impact(
                CODECARBON,
                f"Empreinte non estimée : CodeCarbon a rendu une énergie invalide ({kwh}).",
            )
        kwh = max(0.0, kwh)  # no GPU estimate: its share, if any, is left out
        scope = (
            "poste entier (le modèle tourne dans un autre processus, Ollama ou llama-server)"
            if self.machine
            else "processus de WaveStack seul (le moteur intégré)"
        )
        note = (
            "Mesure CodeCarbon hors ligne : estimation (TDP × charge, sans droits "
            f"administrateur), {scope} ; émissions à {_number_fr(self.gco2e_per_kwh)} g CO₂e "
            "par kWh ([greenops] local_gco2e_per_kwh), sans le GPU. Électricité consommée "
            "seulement : sans la part de fabrication du poste, que l'estimation cloud "
            "(EcoLogits) compte pour les serveurs."
        )
        if kwh == 0:
            note += " CodeCarbon n'a mesuré aucune énergie pour cet appel (trop court)."
        wh, grams = kwh * 1000, kwh * self.gco2e_per_kwh
        return Impact(CODECARBON, note, wh, wh, grams, grams)


class LocalMeter:
    """CodeCarbon around each local call (one meter per session). Its first use asks the
    memory budget (`check`, a French refusal or `None`), imports CodeCarbon, then counts it
    for life (`grant`), as FAISS in the RAG workshop. `start()` and `warm_up()` never
    raise."""

    def __init__(
        self,
        gco2e_per_kwh: float,
        check: Callable[[], str | None] = lambda: None,
        grant: Callable[[], None] = lambda: None,
    ) -> None:
        self.gco2e_per_kwh = gco2e_per_kwh
        self._check = check
        self._grant = grant
        self._lock = threading.Lock()
        self._tracker_class: Any = None
        self._broken: str | None = None
        # Held by `warm_up` while it imports CodeCarbon and detects the CPU: a call that
        # starts meanwhile waits for it.
        self._warming = threading.Lock()

    def _tracker(self) -> tuple[Any, str | None]:
        with self._lock:
            if self._tracker_class is not None:
                return self._tracker_class, None
            if self._broken is not None:
                return None, self._broken
            if _find_spec(CODECARBON) is None:
                return None, missing_fr()
            refusal = self._check()
            if refusal is not None:  # asked again at the next call: the budget may change
                return None, f"Empreinte locale indisponible : {refusal}"
            try:
                module = _load_codecarbon()
            except Exception as exc:  # noqa: BLE001 - a DLL blocked, a broken install
                self._broken = (
                    "Empreinte locale indisponible : CodeCarbon n'a pas pu être chargé "
                    f"({type(exc).__name__} : {exc}). Relancez `{INSTALL_FR}` depuis le "
                    "dossier de WaveStack."
                )
                return None, self._broken
            logging.getLogger("codecarbon").setLevel(logging.ERROR)
            # CodeCarbon asks PowerShell for the CPU sockets at every tracker (2 s under
            # Windows): once is enough.
            counter = getattr(module, "count_physical_cpus", None)
            if counter is not None and not hasattr(counter, "cache_info"):
                module.count_physical_cpus = functools.cache(counter)
            tracker_class = module.OfflineEmissionsTracker  # before the grant: may fail
            self._grant()
            self._tracker_class = tracker_class
            return self._tracker_class, None

    def warm_up(self, machine: bool) -> None:
        """In the background, once a local model is ready: CodeCarbon imported (within the
        budget) and the CPU detected by a first tracker, discarded, so that the first call
        does not wait for them. Nothing without the extra; never raises."""
        if _find_spec(CODECARBON) is None:
            return
        with self._warming:
            try:
                self._start(machine).stop()
            except Exception as exc:  # noqa: BLE001 - the first call will say it
                logger.warning("Préparation de CodeCarbon en échec : %s", exc)

    def start(self, machine: bool) -> Measure:
        """A tracker started before the generation: `machine` for a model served by another
        process (Ollama, llama-server), else the process only (the embedded engine). Waits
        for a warm-up under way; never raises."""
        with self._warming:
            pass
        try:
            return self._start(machine)
        except Exception as exc:  # noqa: BLE001 - an estimate never stops a call
            logger.warning("CodeCarbon n'a pas démarré : %s", exc)
            return Measure(
                None,
                machine,
                self.gco2e_per_kwh,
                f"Empreinte non estimée : CodeCarbon n'a pas démarré ({type(exc).__name__}).",
            )

    def _start(self, machine: bool) -> Measure:
        tracker_class, reason = self._tracker()
        if tracker_class is None:
            return Measure(None, machine, self.gco2e_per_kwh, reason)
        try:
            with warnings.catch_warnings():  # `save_to_file`, deprecated by CodeCarbon 3
                warnings.simplefilter("ignore", DeprecationWarning)
                tracker = tracker_class(
                    country_iso_code=COUNTRY,
                    save_to_file=False,
                    log_level="error",
                    measure_power_secs=1,
                    tracking_mode="machine" if machine else "process",
                )
            tracker.start()
        except Exception as exc:  # noqa: BLE001 - an estimate never stops a call
            logger.warning("CodeCarbon n'a pas démarré : %s", exc)
            return Measure(
                None,
                machine,
                self.gco2e_per_kwh,
                f"Empreinte non estimée : CodeCarbon n'a pas démarré ({type(exc).__name__}).",
            )
        return Measure(tracker, machine, self.gco2e_per_kwh)
