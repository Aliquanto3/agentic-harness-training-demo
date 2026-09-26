from __future__ import annotations

import threading
import time

import pytest

from wavestack import cli, config
from wavestack.session.diagnostic import DiagnosticResult, DiagnosticSession, launch_page


def test_reserve_port_then_conflict_returns_none_for_second_caller():
    first = cli._try_reserve_port(0)  # port 0: OS picks a free ephemeral port
    assert first is not None
    port = first.getsockname()[1]
    try:
        second = cli._try_reserve_port(port)
        assert second is None
    finally:
        first.close()


@pytest.mark.parametrize(("ready", "page"), [(True, "/"), (False, "/diagnostic")])
def test_main_opens_browser_and_exits_zero_when_existing_instance_healthy(monkeypatch, ready, page):
    opened = []
    monkeypatch.setattr(cli, "_try_reserve_port", lambda port: None)
    monkeypatch.setattr(cli, "_existing_instance_healthy", lambda port: True)
    monkeypatch.setattr(cli, "_existing_instance_ready", lambda port: ready)
    monkeypatch.setattr(cli.webbrowser, "open", lambda url: opened.append(url))

    exit_code = cli.main(["--port", "8888"])

    assert exit_code == 0
    assert opened == [f"http://127.0.0.1:8888{page}"]


def test_main_reports_conflict_and_exits_nonzero_when_port_used_by_other_process(
    monkeypatch, capsys
):
    monkeypatch.setattr(cli, "_try_reserve_port", lambda port: None)
    monkeypatch.setattr(cli, "_existing_instance_healthy", lambda port: False)

    exit_code = cli.main(["--port", "8888"])

    assert exit_code == 1
    assert "8888" in capsys.readouterr().out


# ---------- story 11b: the page opened at launch (AD-21, step 2) ----------


def _opened(monkeypatch) -> list[str]:
    opened: list[str] = []
    monkeypatch.setattr(cli.webbrowser, "open", lambda url: opened.append(url))
    return opened


def test_a_ready_launch_opens_the_main_page_once_the_result_is_known(monkeypatch):
    opened = _opened(monkeypatch)
    monkeypatch.setattr(cli, "BROWSER_DELAY_S", 0.2)
    launched = cli._Launched()
    threading.Timer(0.4, lambda: launched.set(DiagnosticResult(ready=True))).start()
    started = time.monotonic()

    cli._open_browser(8888, False, launched)

    assert opened == ["http://127.0.0.1:8888/"]
    assert time.monotonic() - started >= 0.38  # after the result, not after the delay


def test_a_quick_result_still_waits_for_the_delay(monkeypatch):
    opened = _opened(monkeypatch)
    monkeypatch.setattr(cli, "BROWSER_DELAY_S", 0.3)
    launched = cli._Launched()
    launched.set(DiagnosticResult(ready=True))
    started = time.monotonic()

    cli._open_browser(8888, False, launched)

    assert opened == ["http://127.0.0.1:8888/"] and time.monotonic() - started >= 0.29


def test_a_blocked_launch_opens_the_diagnostic(monkeypatch):
    opened = _opened(monkeypatch)
    monkeypatch.setattr(cli, "BROWSER_DELAY_S", 0)
    launched = cli._Launched()
    launched.set(DiagnosticResult(ready=False, blocking_checks=["model"]))

    cli._open_browser(8888, False, launched)

    assert opened == ["http://127.0.0.1:8888/diagnostic"]
    assert launch_page(DiagnosticResult(ready=True, blocking_checks=["model"])) == "/diagnostic"


def test_a_diagnostic_still_running_opens_the_diagnostic(monkeypatch):
    opened = _opened(monkeypatch)
    monkeypatch.setattr(cli, "BROWSER_DELAY_S", 0)
    monkeypatch.setattr(cli, "LAUNCH_WAIT_S", 0.1)

    cli._open_browser(8888, False, cli._Launched())

    assert opened == ["http://127.0.0.1:8888/diagnostic"]


def test_the_first_launch_opens_the_diagnostic_without_waiting(monkeypatch):
    opened = _opened(monkeypatch)
    monkeypatch.setattr(cli, "BROWSER_DELAY_S", 0)
    monkeypatch.setattr(cli, "LAUNCH_WAIT_S", 5)
    session = DiagnosticSession(config.load_config(), port=8888)
    launched = cli._Launched()
    launched.set(DiagnosticResult(ready=True))  # ready: `/` on any later launch
    started = time.monotonic()

    first = session.first_launch()
    cli._open_browser(8888, first, launched)

    assert time.monotonic() - started < 1
    assert first is True and opened == ["http://127.0.0.1:8888/diagnostic"]
    assert config.read_settings()["diagnostic_shown"] is True
    assert session.first_launch() is False


def test_a_failed_write_of_the_first_launch_mark_is_ignored(monkeypatch):
    def refuse(key, value):
        raise PermissionError("settings.json en lecture seule")

    monkeypatch.setattr(config, "save_setting", refuse)
    session = DiagnosticSession(config.load_config(), port=8888)

    assert session.first_launch() is True
    assert "diagnostic_shown" not in config.read_settings()


@pytest.mark.parametrize("content", ["{pas du json", "[1, 2]"])
def test_an_unreadable_settings_file_is_never_rewritten_at_launch(content):
    path = config.settings_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content, encoding="utf-8")
    session = DiagnosticSession(config.load_config(), port=8888)

    assert session.first_launch() is True
    assert path.read_text(encoding="utf-8") == content


def test_the_launch_result_is_known_before_the_model_is_handed_out(monkeypatch):
    launched = cli._Launched()
    result = DiagnosticResult(ready=True)
    seen = []

    class Session:
        def run(self):
            return result

        def hand_to(self, app_session, given, *, launch=False):
            seen.append((launched.done.is_set(), given, launch))

    cli._run_diagnostic_then_boot(Session(), object(), launched)

    assert seen == [(True, result, True)]
    assert launched.result is result and launch_page(launched.result) == "/"


class _Answer:
    def __init__(self, body: bytes) -> None:
        self.body = body

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        return False

    def read(self) -> bytes:
        return self.body


@pytest.mark.parametrize(
    ("body", "ready"),
    [
        (b'{"ready": true, "blocking_checks": []}', True),
        (b'{"ready": false, "blocking_checks": []}', False),
        (b'{"ready": true, "blocking_checks": ["model"]}', False),
        (b"<html>pas du json</html>", False),
    ],
)
def test_existing_instance_ready_follows_launch_page(monkeypatch, body, ready):
    urls = []

    def urlopen(url, timeout):
        urls.append(url)
        return _Answer(body)

    monkeypatch.setattr(cli.urllib.request, "urlopen", urlopen)

    assert cli._existing_instance_ready(8888) is ready
    assert urls == ["http://127.0.0.1:8888/api/diagnostic"]
