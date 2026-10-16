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

    def ensure_loaded(self, on_progress=None, cancel=None) -> None:
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


# --- Review of story 13 ---------------------------------------------------------------


def test_install_failure_is_kept_for_the_card_but_a_stop_is_not() -> None:
    fake = FakeInjection()
    fake.has_token = True
    fake.fails_with = RuntimeError("401 unauthorized")
    m = GuardrailsManager({"injection": lambda: fake})
    with pytest.raises(RuntimeError):
        m.install_injection(lambda done, total: None)
    assert m.load_error("injection") == "401 unauthorized"

    stopped = RuntimeError("stopped")
    stopped.cancelled = True  # like `DownloadError(cancelled=True)`
    fake.fails_with = stopped
    with pytest.raises(RuntimeError):
        m.install_injection(lambda done, total: None)
    assert m.load_error("injection") is None  # « Arrêter » is no failure


def test_injection_ready_from_files_on_disk_after_unload() -> None:
    fake = FakeInjection()
    fake.has_token = True

    def factory() -> FakeInjection:
        return fake

    factory.is_installed = lambda: True  # files and token already there
    m = GuardrailsManager({"injection": factory})
    assert m.injection_ready() is True  # a restart: no token asked again
    m.unload_idle()
    assert m.injection_ready() is True


def test_malicious_score_is_stable_and_never_fails_open_on_nan() -> None:
    from wavestack.guardrails.injection import malicious_score

    assert malicious_score([0.0, 0.0]) == pytest.approx(0.5)
    assert malicious_score([1000.0, 1001.0]) == pytest.approx(0.7310586)  # no overflow
    assert malicious_score([-1000.0, 1000.0]) == pytest.approx(1.0)
    with pytest.raises(ValueError):
        malicious_score([float("nan"), 0.0])


def _hub(status: int | None, seen: list):
    import httpx

    def handler(request: httpx.Request) -> httpx.Response:
        seen.append(request)
        if status is None:
            raise httpx.ConnectError("refused", request=request)
        return httpx.Response(status)

    return httpx.MockTransport(handler)


def test_licence_check_accepted_asks_the_official_repo_without_weights() -> None:
    from wavestack.guardrails.injection import check_licence
    from wavestack.trace.journal import get_journal

    seen: list = []
    mark = get_journal().last_seq()
    check_licence("hf_secret_token", transport=_hub(200, seen))
    [request] = seen
    assert request.method == "HEAD"
    url = str(request.url)
    assert url.startswith("https://huggingface.co/meta-llama/Llama-Prompt-Guard-2-22M/")
    assert url.endswith("/config.json")
    assert request.headers["authorization"] == "Bearer hf_secret_token"
    traced = [e.payload for e in get_journal().events_since(mark)]
    assert traced and "hf_secret_token" not in repr(traced)  # AD-15: masked


@pytest.mark.parametrize("status", [401, 403])
def test_licence_check_refused_says_to_accept_the_licence(status: int) -> None:
    from wavestack.guardrails.injection import LICENCE_PAGE, check_licence
    from wavestack.models.download import DownloadError

    with pytest.raises(DownloadError) as caught:
        check_licence("hf_x", transport=_hub(status, []))
    assert LICENCE_PAGE in str(caught.value)
    assert "licence" in str(caught.value)


def test_licence_check_network_failure_is_a_download_error() -> None:
    from wavestack.guardrails.injection import check_licence
    from wavestack.models.download import DownloadError

    with pytest.raises(DownloadError) as caught:
        check_licence("hf_x", transport=_hub(None, []))
    assert "huggingface.co" in str(caught.value)


def test_ensure_loaded_downloads_nothing_when_the_licence_is_refused(monkeypatch, tmp_path):
    import sys
    import types

    from pydantic import SecretStr

    from wavestack.guardrails import injection
    from wavestack.models.download import DownloadError

    # No real onnxruntime/tokenizers needed: the refusal comes before they are used.
    monkeypatch.setitem(sys.modules, "onnxruntime", types.ModuleType("onnxruntime"))
    tok = types.ModuleType("tokenizers")
    tok.Tokenizer = object
    monkeypatch.setitem(sys.modules, "tokenizers", tok)
    monkeypatch.setattr(injection.config, "hf_token", lambda: SecretStr("hf_x"))
    monkeypatch.setattr(injection, "_dest", lambda: tmp_path)

    def refuse(token, **kw):
        raise DownloadError("refused")

    downloads: list = []
    monkeypatch.setattr(injection, "check_licence", refuse)
    monkeypatch.setattr(injection, "download_files", lambda *a, **k: downloads.append(a))
    with pytest.raises(DownloadError):
        injection.PromptGuardGuardrail().ensure_loaded()
    assert downloads == []
