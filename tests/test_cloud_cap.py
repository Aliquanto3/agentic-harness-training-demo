"""Native providers 2/5 (CAP-4): the session's spending cap and the cache prices.

Every provider answer comes from an `httpx.MockTransport`: nothing leaves the machine.
"""

from __future__ import annotations

import json
from datetime import date

import pytest
from pydantic import SecretStr
from test_cloud import (
    GEMINI_TEXT,
    GEMINI_TOOL,
    ORIGIN,
    SENTINEL,
    GeminiProvider,
    Provider,
    _app,
    _cloud_session,
    _of,
    _turn,
    delta,
    sse,
)

from wavestack import config
from wavestack.config import CloudPricing
from wavestack.models import cloud_base
from wavestack.models.cloud_base import (
    CallCost,
    ChatBody,
    ProviderError,
    _cached_tokens,
    call_cost,
    record_spend,
    run_call,
)
from wavestack.models.engine import CancelToken, Sampling
from wavestack.trace.journal import get_journal


def _settings(**finops: object) -> None:
    config.settings_path().parent.mkdir(parents=True, exist_ok=True)
    config.settings_path().write_text(json.dumps({"finops": finops}), encoding="utf-8")


def _spent_already(usd: float) -> None:
    """The session's registry as earlier paid calls left it."""
    record_spend(CallCost(usd * 0.6, usd * 0.4, "api"), 0.86)


def _pricing(**cache: float) -> CloudPricing:
    return CloudPricing(
        input_usd_per_mtok=1, output_usd_per_mtok=5, checked=date(2026, 10, 3), **cache
    )


# ---------- `[finops] max_session_usd` ----------


def test_the_cap_is_5_dollars_by_default():
    assert config.load_config().max_session_usd == 5.0


@pytest.mark.parametrize("value", ["abc", "nan", "inf", -1, None, True, False, 10**400])
def test_an_unreadable_or_negative_cap_is_5_dollars(value):
    """A boolean is unreadable (never 1 $ or 0 $); an integer too large for a float, which
    JSON accepts, too."""
    _settings(max_session_usd=value)
    assert config.load_config().max_session_usd == 5.0


@pytest.mark.parametrize("value", [0, 0.01, "2.5", 100])
def test_a_readable_cap_is_kept(value):
    _settings(max_session_usd=value)
    assert config.load_config().max_session_usd == float(value)


# ---------- the cap before the call is sent ----------


def test_under_the_cap_the_call_is_sent():
    _settings(max_session_usd=0.01)
    _spent_already(0.005)
    provider = GeminiProvider(GEMINI_TEXT)
    session = _cloud_session("gemini", provider)

    events = _turn(session, "Bonjour")

    assert len(provider.requests) == 1
    assert _of(events, "harness_error") == []
    assert len(_of(events, "model_call_ended")) == 1


def test_once_the_cap_is_reached_the_call_is_not_sent():
    _settings(max_session_usd=0.01)
    _spent_already(0.01)
    provider = GeminiProvider(GEMINI_TEXT)
    session = _cloud_session("gemini", provider)
    before = session.consumption()

    events = _turn(session, "Bonjour")

    assert provider.requests == []  # nothing reached the transport
    kinds = {e.kind for e in events}
    assert not kinds & {"model_call_started", "model_call_ended", "outbound_request"}
    assert "consumption_updated" not in kinds  # the gauge does not move
    assert session.consumption() == before
    (error,) = (e.payload for e in _of(events, "harness_error"))
    assert error["cause"] == "max_session_usd" and error["http_status"] is None
    message = error["message_text"]
    assert "0,01 $" in message  # the cap and the total, here equal
    assert "max_session_usd" in message and "settings.json" in message
    assert "n'est pas parti" in message
    assert any("Gemma" in hint for hint in error["hints_text"])
    assert _of(events, "turn_ended")


def test_an_entry_without_prices_is_never_refused():
    _settings(max_session_usd=0.01)
    _spent_already(1.0)
    provider = GeminiProvider(GEMINI_TEXT)
    session = _cloud_session("gemma", provider)

    events = _turn(session, "Bonjour")

    assert len(provider.requests) == 1
    assert _of(events, "harness_error") == []


@pytest.mark.parametrize(
    ("lang", "said", "cap", "total"),
    [
        ("en", "Session spending cap reached", "$0.01", "$0.02"),
        ("de", "Ausgabenobergrenze der Sitzung erreicht", "0,01 $", "0,02 $"),
    ],
)
def test_the_cap_message_is_in_the_session_language(lang, said, cap, total):
    _settings(max_session_usd=0.01)
    _spent_already(0.02)
    provider = GeminiProvider(GEMINI_TEXT)
    session = _cloud_session("gemini", provider)
    session.set_language(lang)
    session.join()

    events = _turn(session, "Hello")

    assert provider.requests == []
    (error,) = (e.payload for e in _of(events, "harness_error"))
    message = error["message_text"]
    assert said in message and cap in message and total in message
    assert "max_session_usd" in message


def test_the_llm_screen_is_refused_too():
    _settings(max_session_usd=0.01)
    _spent_already(0.01)
    provider = GeminiProvider(GEMINI_TEXT)
    session = _cloud_session("gemini", provider)
    mark = get_journal().last_seq()

    session.llm_generate("Bonjour", Sampling(temperature=0.2, top_k=5, top_p=0.9, min_p=0.05))
    session.join()

    events = get_journal().events_since(mark)
    assert provider.requests == []
    (error,) = (e.payload for e in _of(events, "harness_error"))
    assert error["cause"] == "max_session_usd"
    assert _of(events, "model_call_started") == []


def test_tester_is_refused_too(monkeypatch):
    _settings(max_session_usd=0.01)
    _spent_already(0.01)
    provider = GeminiProvider(GEMINI_TOOL, GEMINI_TEXT)
    _, _, _, client = _app(monkeypatch, provider)
    client.post(
        "/api/intentions/set_api_key", json={"id": "gemini", "key": SENTINEL}, headers=ORIGIN
    )
    mark = get_journal().last_seq()

    client.post("/api/intentions/test_cloud_model", json={"id": "gemini"}, headers=ORIGIN)

    events = get_journal().events_since(mark)
    assert provider.requests == []
    assert _of(events, "model_call_started") == []
    (check,) = (e.payload for e in _of(events, "diagnostic_check"))
    assert check["status"] == "fail" and "max_session_usd" in check["message_text"]


def _run(provider: Provider, max_session_usd: float | None):
    entry = config.load_config().cloud_model("gemini")
    engine = provider.factory(entry, SecretStr(SENTINEL))
    try:
        return run_call(
            engine,
            ChatBody(b'{"messages": []}'),
            CancelToken(),
            phase_label="test",
            estimated_prompt=10,
            chars_per_token=4.0,
            call_id=str,
            max_session_usd=max_session_usd,
        )
    finally:
        engine.close()


def test_run_call_without_a_cap_checks_nothing():
    _spent_already(100.0)
    provider = GeminiProvider(GEMINI_TEXT)

    call = _run(provider, None)

    assert len(provider.requests) == 1 and call.stop_reason == "stop"


def test_the_cap_is_checked_again_after_the_spacing_wait(monkeypatch):
    """A concurrent call that ends during the wait brings the total to the cap: the waiting
    call is not sent."""
    _spent_already(0.005)
    real_pace = cloud_base.pace

    def pace(entry, cancel):  # noqa: ANN001
        _spent_already(0.005)  # the concurrent call's cost, recorded while this one waits
        return real_pace(entry, cancel)

    monkeypatch.setattr(cloud_base, "pace", pace)
    provider = GeminiProvider(GEMINI_TEXT)
    mark = get_journal().last_seq()

    with pytest.raises(ProviderError) as refused:
        _run(provider, 0.01)

    assert refused.value.cause == "max_session_usd"
    assert provider.requests == []
    assert _of(get_journal().events_since(mark), "model_call_started") == []


def test_the_refusal_names_the_cap_and_the_total():
    _spent_already(100.0)
    entry = config.load_config().cloud_model("gemini")
    assert cloud_base.session_cap_error(entry, None) is None
    error = cloud_base.session_cap_error(entry, 5.0)
    assert isinstance(error, ProviderError) and error.cause == "max_session_usd"
    assert "100,00 $" in str(error) and "5,00 $" in str(error)


# ---------- the cache prices ----------


def test_tokens_read_from_the_cache_cost_the_cache_price():
    cost = call_cost(_pricing(cache_read_usd_per_mtok=0.10), 1000, 10, "api", cached_read=800)
    assert cost.input_usd == pytest.approx((200 * 1 + 800 * 0.10) / 1e6)
    assert cost.output_usd == pytest.approx(10 * 5 / 1e6)


def test_without_cache_prices_the_cost_does_not_change():
    cost = call_cost(_pricing(), 1000, 10, "api", cached_read=800, cached_write=100)
    assert cost.input_usd == pytest.approx(1000 * 1 / 1e6)


def test_tokens_written_to_the_cache_cost_the_write_price():
    pricing = _pricing(cache_read_usd_per_mtok=0.10, cache_write_usd_per_mtok=1.25)
    cost = call_cost(pricing, 1000, 0, "api", cached_read=800, cached_write=100)
    assert cost.input_usd == pytest.approx((100 * 1 + 800 * 0.10 + 100 * 1.25) / 1e6)


@pytest.mark.parametrize(
    ("read", "write", "expected"),
    [
        (800, 500, 800 * 0.10 + 200 * 1.25),  # the written part clamped to what is left
        (1500, 100, 1000 * 0.10),  # the read part clamped to the whole input
        (-5, -5, 1000 * 1),  # never negative
    ],
)
def test_cached_tokens_never_exceed_the_input(read, write, expected):
    pricing = _pricing(cache_read_usd_per_mtok=0.10, cache_write_usd_per_mtok=1.25)
    cost = call_cost(pricing, 1000, 0, "api", cached_read=read, cached_write=write)
    assert cost.input_usd == pytest.approx(expected / 1e6)
    assert cost.input_usd >= 0


@pytest.mark.parametrize(
    "details",
    [
        None,
        [800],
        {"cached_tokens": True, "cache_write_tokens": False},
        {"cached_tokens": "800", "cache_write_tokens": "100"},
        {"cached_tokens": -5, "cache_write_tokens": -5},
        {"cached_tokens": float("nan"), "cache_write_tokens": float("inf")},
    ],
)
def test_unreadable_cached_tokens_count_zero(details):
    assert _cached_tokens({"prompt_tokens": 1000, "prompt_tokens_details": details}) == (0, 0)


def test_cached_tokens_are_read_from_the_usage_details():
    usage = {"prompt_tokens_details": {"cached_tokens": 800, "cache_write_tokens": 100}}
    assert _cached_tokens(usage) == (800, 100)


@pytest.mark.parametrize("field", ["cache_read_usd_per_mtok", "cache_write_usd_per_mtok"])
@pytest.mark.parametrize("value", [-1, float("nan"), float("inf")])
def test_a_cache_price_must_be_finite_and_not_negative(field, value):
    with pytest.raises(ValueError):
        _pricing(**{field: value})


def test_a_call_reads_the_cached_tokens_of_its_usage():
    """The pivot usage: `prompt_tokens` counts the whole input, `prompt_tokens_details`
    the cached part."""
    usage = {
        "prompt_tokens": 1000,
        "completion_tokens": 10,
        "total_tokens": 1010,
        "prompt_tokens_details": {"cached_tokens": 800, "cache_write_tokens": 100},
    }
    stream = sse(delta(content="Oui."), {**delta("stop"), "usage": usage})
    pricing = {
        "input_usd_per_mtok": 1,
        "output_usd_per_mtok": 5,
        "cache_read_usd_per_mtok": 0.10,
        "cache_write_usd_per_mtok": 1.25,
        "checked": "2026-10-03",
    }
    settings = {"cloud": {"models": [{"id": "gemini", "pricing": pricing}]}}
    config.settings_path().parent.mkdir(parents=True, exist_ok=True)
    config.settings_path().write_text(json.dumps(settings), encoding="utf-8")
    session = _cloud_session("gemini", GeminiProvider(stream))

    events = _turn(session, "Bonjour")

    (ended,) = (e.payload for e in _of(events, "model_call_ended"))
    expected = (100 * 1 + 800 * 0.10 + 100 * 1.25) / 1e6
    assert ended["cost_in_usd"] == pytest.approx(expected)
    assert ended["cost_out_usd"] == pytest.approx(10 * 5 / 1e6)
