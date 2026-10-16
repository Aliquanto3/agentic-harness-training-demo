"""Story 13 (CAP-5): Prompt Guard 2 wired as a real guardrail — `not_installed` without a
Hugging Face token, never cached, then the same `check()`/`install_injection` path as the
other two once it has a model. A fake classifier only: no test downloads the ONNX model."""

from __future__ import annotations

import pytest

from wavestack.guardrails.contract import Classification, Entity, NotInstalled
from wavestack.guardrails.manager import GuardrailsManager


class FakeInjection:
    """A `PromptGuardGuardrail` fake: `has_token` stands in for `config.hf_token()`, `loaded`
    for the ONNX session once `ensure_loaded` (lazily, or `install_injection`) built it."""

    def __init__(self) -> None:
        self.has_token = False
        self.loaded = False
        self.load_calls = 0
        self.classify_calls = 0
        self.fails_with: Exception | None = None

    def ensure_loaded(self, on_progress=None) -> None:
        if self.loaded:
            return  # like the real classifier: nothing re-downloaded once loaded
        if not self.has_token:
            raise NotInstalled("no token")
        self.load_calls += 1
        if on_progress is not None:
            on_progress(1, 1)
        if self.fails_with is not None:
            raise self.fails_with
        self.loaded = True

    def classify(self, text: str) -> Classification:
        self.classify_calls += 1
        self.ensure_loaded()
        detected = "INJECT" in text
        entity = (Entity("MALICIOUS", 0, len(text), 0.9),) if detected else ()
        return Classification(
            detected=detected, score=0.9 if detected else 0.1, threshold=0.5, entities=entity
        )

    def mask(self, text: str, entities: tuple[Entity, ...]) -> str:
        return text

    def unload(self) -> None:
        self.loaded = False


def test_injection_without_token_reports_not_installed_never_cached() -> None:
    fake = FakeInjection()
    m = GuardrailsManager({"injection": lambda: fake})
    m.set_mode("injection", "block")
    [v1] = m.check("input", "INJECT this")
    [v2] = m.check("input", "INJECT this")
    assert v1.status == "not_installed" and v2.status == "not_installed"
    assert fake.classify_calls == 2  # cheap to re-check: never cached in `_load_errors`
    assert m.load_error("injection") is None


def test_injection_blocks_once_installed() -> None:
    fake = FakeInjection()
    fake.has_token = True
    m = GuardrailsManager({"injection": lambda: fake})
    m.set_mode("injection", "block")
    [verdict] = m.check("input", "INJECT this")
    assert verdict.status == "active"
    assert verdict.blocks is True


def test_withholds_output_includes_injection_block() -> None:
    fake = FakeInjection()
    fake.has_token = True
    m = GuardrailsManager({"injection": lambda: fake})
    assert m.withholds_output() is False
    m.set_mode("injection", "block")
    assert m.withholds_output() is True


def test_install_injection_registers_the_loaded_instance_for_later_checks() -> None:
    fake = FakeInjection()
    fake.has_token = True  # the token the "Installer" button just saved
    m = GuardrailsManager({"injection": lambda: fake})
    assert m.injection_ready() is False
    m.install_injection(lambda done, total: None)
    assert m.injection_ready() is True
    assert fake.load_calls == 1
    m.set_mode("injection", "block")
    [verdict] = m.check("input", "INJECT this")
    assert verdict.status == "active"
    assert fake.load_calls == 1  # `check` reuses the instance `install_injection` loaded


def test_install_injection_raises_the_classifier_s_own_failure() -> None:
    fake = FakeInjection()
    fake.has_token = True
    fake.fails_with = RuntimeError("download failed")
    m = GuardrailsManager({"injection": lambda: fake})
    with pytest.raises(RuntimeError, match="download failed"):
        m.install_injection(lambda done, total: None)
    assert m.injection_ready() is False


def test_install_injection_without_a_token_raises_not_installed() -> None:
    fake = FakeInjection()
    m = GuardrailsManager({"injection": lambda: fake})
    with pytest.raises(NotInstalled):
        m.install_injection(lambda done, total: None)


def test_install_injection_without_a_factory_raises_not_installed() -> None:
    m = GuardrailsManager({})
    with pytest.raises(NotInstalled):
        m.install_injection(lambda done, total: None)
