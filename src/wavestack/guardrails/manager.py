"""`GuardrailsManager` (CAP-5): one mode per guardrail, applied to a turn's input or output.

The manager owns the only decision a `Classifier` never makes itself: what `block`, `flag`
or `off` means for the turn. `toxicity` and `pii` lazily build their real classifier
(`ToxicityGuardrail`, `PiiGuardrail`); a test passes its own `Classifier` fake instead, so no
test ever downloads a model (story 4).
"""

from __future__ import annotations

from collections.abc import Callable

from wavestack.guardrails.contract import (
    Classifier,
    Direction,
    GuardrailId,
    GuardrailMode,
    NotInstalled,
    Verdict,
)

DEFAULT_MODES: dict[GuardrailId, GuardrailMode] = {
    "toxicity": "off",
    "pii": "off",
    "injection": "off",
}


def _default_classifiers() -> dict[GuardrailId, Callable[[], Classifier]]:
    from wavestack.guardrails.injection import PromptGuardGuardrail
    from wavestack.guardrails.pii import PiiGuardrail
    from wavestack.guardrails.toxicity import ToxicityGuardrail

    return {"toxicity": ToxicityGuardrail, "pii": PiiGuardrail, "injection": PromptGuardGuardrail}


class GuardrailsManager:
    def __init__(
        self, classifier_factories: dict[GuardrailId, Callable[[], Classifier]] | None = None
    ) -> None:
        self.modes: dict[GuardrailId, GuardrailMode] = dict(DEFAULT_MODES)
        self._factories = (
            classifier_factories if classifier_factories is not None else _default_classifiers()
        )
        self._instances: dict[GuardrailId, Classifier] = {}
        # Story 5 (review of story 4): a failed first load (e.g. the 135 MB download) is
        # cached here, never retried on every turn; cleared by `unload_idle` (a fresh brick
        # restart is the only way back, as for a classify-time failure, AD-16).
        self._load_errors: dict[GuardrailId, str] = {}

    def set_mode(self, guardrail: GuardrailId, mode: GuardrailMode) -> None:
        if guardrail not in DEFAULT_MODES:
            raise ValueError(f"unknown guardrail: {guardrail!r}")
        self.modes[guardrail] = mode

    def withholds_output(self) -> bool:
        """Story 5 (story 13: `injection` included now that it is a real guardrail, not a
        placeholder): whether an answer must be checked before it is shown (`block`, or `pii`
        in `flag`, which masks): then it is never streamed live."""
        return any(m == "block" or (g == "pii" and m == "flag") for g, m in self.modes.items())

    def _classifier(self, guardrail: GuardrailId) -> Classifier | None:
        if guardrail not in self._factories or guardrail in self._load_errors:
            return None
        instance = self._instances.get(guardrail)
        if instance is None:
            try:
                instance = self._factories[guardrail]()
            except Exception as exc:  # noqa: BLE001 - cached, never retried every turn
                self._load_errors[guardrail] = str(exc)
                return None
            self._instances[guardrail] = instance
        return instance

    def check(self, direction: Direction, text: str) -> list[Verdict]:
        """One `Verdict` per guardrail whose mode is not `off`. Never raises: a classifier
        that fails to load reports `error`, one that is not set up yet (story 13: injection
        without a Hugging Face token) reports `not_installed`; neither blocks the turn."""
        verdicts: list[Verdict] = []
        for guardrail, mode in self.modes.items():
            if mode == "off":
                continue
            verdicts.append(self._check_one(guardrail, mode, direction, text))
        return verdicts

    def _check_one(
        self, guardrail: GuardrailId, mode: GuardrailMode, direction: Direction, text: str
    ) -> Verdict:
        classifier = self._classifier(guardrail)
        if classifier is None:
            if guardrail in self._load_errors:
                return Verdict(
                    guardrail, direction, mode, "error", detail_text=self._load_errors[guardrail]
                )
            return Verdict(guardrail, direction, mode, "not_installed")
        masked = None
        try:
            result = classifier.classify(text)
            if mode == "flag" and result.detected and result.entities:
                masked = classifier.mask(text, result.entities)
        except NotInstalled as exc:
            # Story 13: cheap to check again next turn (a token file, not a model download),
            # so never cached in `_load_errors` like a real load failure below.
            return Verdict(guardrail, direction, mode, "not_installed", detail_text=str(exc))
        except Exception as exc:  # noqa: BLE001 - a missing/broken model never blocks the turn
            # The real classifiers load (and download) inside `classify`: the failure is
            # cached here, never retried on every turn, until `unload_idle`.
            self._load_errors[guardrail] = str(exc)
            self._instances.pop(guardrail, None)
            return Verdict(guardrail, direction, mode, "error", detail_text=str(exc))
        return Verdict(
            guardrail,
            direction,
            mode,
            "active",
            detected=result.detected,
            score=result.score,
            threshold=result.threshold,
            entities=tuple(e.label for e in result.entities),
            masked_text=masked,
            partial=result.partial,
        )

    def load_error(self, guardrail: GuardrailId) -> str | None:
        """Story 13: the card's own read of `_load_errors`, without reaching into the
        manager's private cache."""
        return self._load_errors.get(guardrail)

    def injection_ready(self) -> bool:
        """Story 13: whether the injection classifier is already loaded (its model files on
        disk, its ONNX session built) — the card's switch replaces « non installé » once
        this is true, instead of waiting for the first turn's lazy load. Checking `.loaded`,
        not just presence in `_instances`: `_classifier` caches the lazy, still-unloaded
        instance there on the very first `check()`, token or not (AD-16: a verdict is still
        produced, so the instance is kept)."""
        instance = self._instances.get("injection")
        return bool(instance is not None and getattr(instance, "loaded", False))

    def install_injection(self, on_progress: Callable[[int, int], None]) -> None:
        """Story 13, the brick's « Installer »: an eager, explicit load (unlike the other
        guardrails' lazy first-`classify` download), so a bad token or a network failure
        surfaces here, with progress, rather than silently as the next turn's `error`
        verdict. Found through the normal factory so `check()` reuses this same instance
        afterwards. Raises `NotInstalled` (no token) or the classifier's own error."""
        self._load_errors.pop("injection", None)
        instance = self._instances.get("injection")
        if instance is None:
            if "injection" not in self._factories:
                raise NotInstalled("")
            instance = self._factories["injection"]()
        instance.ensure_loaded(on_progress)  # type: ignore[call-arg]
        self._instances["injection"] = instance

    def unload_idle(self) -> None:
        """Frees every loaded model's RAM (RAM budget, story 4): called when the brick turns
        off, or when the session wants the memory back."""
        for classifier in self._instances.values():
            classifier.unload()
        self._instances.clear()
        self._load_errors.clear()  # story 5: a fresh try next time (off, then on again)
