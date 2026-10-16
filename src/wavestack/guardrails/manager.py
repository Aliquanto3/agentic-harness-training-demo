"""`GuardrailsManager` (CAP-5): one mode per guardrail, applied to a turn's input or output.

The manager owns the only decision a `Classifier` never makes itself: what `block`, `flag`
or `off` means for the turn. `toxicity` and `pii` lazily build their real classifier
(`ToxicityGuardrail`, `PiiGuardrail`); a test passes its own `Classifier` fake instead, so no
test ever downloads a model (story 4).
"""

from __future__ import annotations

from collections.abc import Callable

from wavestack.guardrails.contract import Classifier, Direction, GuardrailId, GuardrailMode, Verdict

DEFAULT_MODES: dict[GuardrailId, GuardrailMode] = {
    "toxicity": "off",
    "pii": "off",
    "injection": "off",
}


def _default_classifiers() -> dict[GuardrailId, Callable[[], Classifier]]:
    from wavestack.guardrails.pii import PiiGuardrail
    from wavestack.guardrails.toxicity import ToxicityGuardrail

    return {"toxicity": ToxicityGuardrail, "pii": PiiGuardrail}


class GuardrailsManager:
    def __init__(
        self, classifier_factories: dict[GuardrailId, Callable[[], Classifier]] | None = None
    ) -> None:
        self.modes: dict[GuardrailId, GuardrailMode] = dict(DEFAULT_MODES)
        # `injection` has no factory yet (story 5): always reported `not_installed`.
        self._factories = (
            classifier_factories if classifier_factories is not None else _default_classifiers()
        )
        self._instances: dict[GuardrailId, Classifier] = {}

    def set_mode(self, guardrail: GuardrailId, mode: GuardrailMode) -> None:
        if guardrail not in DEFAULT_MODES:
            raise ValueError(f"unknown guardrail: {guardrail!r}")
        self.modes[guardrail] = mode

    def _classifier(self, guardrail: GuardrailId) -> Classifier | None:
        if guardrail not in self._factories:
            return None
        instance = self._instances.get(guardrail)
        if instance is None:
            instance = self._factories[guardrail]()
            self._instances[guardrail] = instance
        return instance

    def check(self, direction: Direction, text: str) -> list[Verdict]:
        """One `Verdict` per guardrail whose mode is not `off` (`injection` always reports
        `not_installed`, story 5's placeholder). Never raises: a classifier that fails to
        load reports `error`, the turn is not blocked by an absent model."""
        verdicts: list[Verdict] = []
        for guardrail, mode in self.modes.items():
            if guardrail == "injection":
                if mode != "off":
                    verdicts.append(Verdict("injection", direction, mode, "not_installed"))
                continue
            if mode == "off":
                continue
            verdicts.append(self._check_one(guardrail, mode, direction, text))
        return verdicts

    def _check_one(
        self, guardrail: GuardrailId, mode: GuardrailMode, direction: Direction, text: str
    ) -> Verdict:
        classifier = self._classifier(guardrail)
        if classifier is None:
            return Verdict(guardrail, direction, mode, "not_installed")
        try:
            result = classifier.classify(text)
        except Exception as exc:  # noqa: BLE001 - a missing/broken model never blocks the turn
            return Verdict(guardrail, direction, mode, "error", detail_text=str(exc))
        masked = None
        if mode == "flag" and result.detected and result.entities:
            masked = classifier.mask(text, result.entities)
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
        )

    def unload_idle(self) -> None:
        """Frees every loaded model's RAM (RAM budget, story 4): called when the brick turns
        off, or when the session wants the memory back."""
        for classifier in self._instances.values():
            classifier.unload()
        self._instances.clear()
