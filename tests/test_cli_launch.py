from __future__ import annotations

import http.client
import sys
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
    monkeypatch.setattr(
        cli, "_existing_instance_health", lambda port: {"root": str(config.repo_root())}
    )
    monkeypatch.setattr(cli, "_existing_instance_ready", lambda port: ready)
    monkeypatch.setattr(cli.webbrowser, "open", lambda url: opened.append(url))

    exit_code = cli.main(["--port", "8888"])

    assert exit_code == 0
    assert opened == [f"http://127.0.0.1:8888{page}"]


def test_main_reports_conflict_and_exits_nonzero_when_port_used_by_other_process(
    monkeypatch, capsys
):
    monkeypatch.setattr(cli, "_try_reserve_port", lambda port: None)
    monkeypatch.setattr(cli, "_existing_instance_health", lambda port: None)

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
    def __init__(self, body: bytes, status: int = 200) -> None:
        self.body = body
        self.status = status

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        return False

    def read(self, size: int = -1) -> bytes:
        return self.body if size < 0 else self.body[:size]


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


# ---------- story R0 (CAP-1): which folder and which commit the reused instance runs ----------


def _reuse(monkeypatch, health) -> list[str]:
    """A port held by a healthy instance answering `health`; the pages the browser opened."""
    monkeypatch.setattr(cli, "_try_reserve_port", lambda port: None)
    monkeypatch.setattr(cli, "_existing_instance_health", lambda port: health)
    monkeypatch.setattr(cli, "_existing_instance_ready", lambda port: True)
    return _opened(monkeypatch)


def _other_tree_line() -> str:
    return cli.msg("cli.other_tree", "en", here=str(config.repo_root()))


def test_the_same_folder_says_where_and_which_commit(monkeypatch, capsys):
    here = str(config.repo_root())
    opened = _reuse(monkeypatch, {"status": "ok", "root": here, "commit": "abc1234"})

    assert cli.main(["--port", "8888"]) == 0

    out = capsys.readouterr().out
    assert out.splitlines() == [
        cli.msg("cli.already_running", "en", port=8888, root=here, commit="abc1234")
    ]
    assert "already running" in out and f"{here} (abc1234)" in out
    assert opened == ["http://127.0.0.1:8888/"]


def test_the_same_folder_spelled_otherwise_is_still_this_folder(monkeypatch, capsys):
    here = str(config.repo_root())
    other_spelling = here.upper() if sys.platform == "win32" else here + "/."
    _reuse(monkeypatch, {"root": other_spelling, "commit": "abc1234"})

    assert cli.main(["--port", "8888"]) == 0

    assert _other_tree_line() not in capsys.readouterr().out


def test_another_folder_adds_the_warning(monkeypatch, capsys, tmp_path):
    elsewhere = str(tmp_path / "other-tree")
    opened = _reuse(monkeypatch, {"root": elsewhere, "commit": "def5678"})

    assert cli.main(["--port", "8888"]) == 0

    assert capsys.readouterr().out.splitlines() == [
        cli.msg("cli.already_running", "en", port=8888, root=elsewhere, commit="def5678"),
        _other_tree_line(),
    ]
    assert "--port" in _other_tree_line()
    assert opened == ["http://127.0.0.1:8888/"]


def test_no_commit_gives_the_variant_without_it(monkeypatch, capsys):
    here = str(config.repo_root())
    _reuse(monkeypatch, {"root": here, "commit": None})

    assert cli.main(["--port", "8888"]) == 0

    assert capsys.readouterr().out.splitlines() == [
        cli.msg("cli.already_running_no_commit", "en", port=8888, root=here)
    ]


@pytest.mark.parametrize("health", [{"status": "ok", "version": "0.1.0"}, {}])
def test_an_older_or_unreadable_instance_is_from_an_unknown_folder(monkeypatch, capsys, health):
    opened = _reuse(monkeypatch, health)

    assert cli.main(["--port", "8888"]) == 0

    assert capsys.readouterr().out.splitlines() == [
        cli.msg("cli.already_running_unknown", "en", port=8888),
        _other_tree_line(),
    ]
    assert opened == ["http://127.0.0.1:8888/"]


@pytest.mark.parametrize(
    ("body", "health"),
    [
        (b'{"root": "C:/x", "commit": null}', {"root": "C:/x", "commit": None}),
        (b'{"status": "ok", "version": "0.1.0"}', {"status": "ok", "version": "0.1.0"}),
        (b"<html>pas du json</html>", {}),
        (b"[1, 2]", {}),
        (b"\xff\xfe", {}),
    ],
)
def test_existing_instance_health_gives_the_body(monkeypatch, body, health):
    urls = []

    def urlopen(url, timeout):
        urls.append(url)
        return _Answer(body)

    monkeypatch.setattr(cli.urllib.request, "urlopen", urlopen)

    assert cli._existing_instance_health(8888) == health
    assert urls == ["http://127.0.0.1:8888/api/health"]


def test_nothing_answering_is_no_instance(monkeypatch):
    def urlopen(url, timeout):
        raise cli.urllib.error.URLError("refused")

    monkeypatch.setattr(cli.urllib.request, "urlopen", urlopen)

    assert cli._existing_instance_health(8888) is None


def test_a_foreign_program_answering_no_http_is_no_instance(monkeypatch):
    def urlopen(url, timeout):
        raise http.client.BadStatusLine("x")

    monkeypatch.setattr(cli.urllib.request, "urlopen", urlopen)

    assert cli._existing_instance_health(8888) is None


def test_a_status_other_than_200_is_no_instance(monkeypatch):
    monkeypatch.setattr(
        cli.urllib.request,
        "urlopen",
        lambda url, timeout: _Answer(b'{"root": "C:/x"}', status=204),
    )

    assert cli._existing_instance_health(8888) is None


# ---------- story 7 of the deferred leftovers (E077): Ctrl+C with a page still open ----------


def test_main_gives_uvicorn_the_shutdown_grace(monkeypatch):
    """`main` hands uvicorn `SHUTDOWN_GRACE_S`: without it, an open page's stream holds the
    shutdown forever."""
    runs: list[dict] = []

    class _Session:
        def __init__(self, cfg, port) -> None:
            pass

        def first_launch(self) -> bool:
            return False

    class _Reserved:
        def close(self) -> None:
            pass

    monkeypatch.setattr(cli, "_try_reserve_port", lambda port: _Reserved())
    monkeypatch.setattr(cli, "DiagnosticSession", _Session)
    monkeypatch.setattr(cli, "AppSession", lambda cfg: type("S", (), {"close": lambda s: None})())
    monkeypatch.setattr(cli.atexit, "register", lambda fn: None)  # #21, never for real here
    monkeypatch.setattr(cli, "create_app", lambda *args, **kwargs: "app")
    monkeypatch.setattr(
        cli, "get_journal", lambda: type("J", (), {"subscribe": lambda s, f: None})()
    )
    monkeypatch.setattr(cli, "_run_diagnostic_then_boot", lambda *args: None)
    monkeypatch.setattr(cli, "_open_browser", lambda *args: None)
    monkeypatch.setattr(cli.uvicorn, "run", lambda app, **kwargs: runs.append(kwargs))

    assert cli.main(["--port", "8888"]) == 0

    assert runs[0]["timeout_graceful_shutdown"] == cli.SHUTDOWN_GRACE_S
    assert runs[0]["host"] == "127.0.0.1" and runs[0]["port"] == 8888


def test_shutdown_with_an_open_stream_ends_and_runs_the_lifespan():
    """A real uvicorn with `SHUTDOWN_GRACE_S` and a stream that never ends (the page's SSE):
    asked to stop, it stops within the grace and still runs the lifespan's close."""
    import asyncio
    from contextlib import asynccontextmanager

    import httpx
    import uvicorn
    from fastapi import FastAPI
    from fastapi.responses import StreamingResponse

    closed = threading.Event()

    @asynccontextmanager
    async def lifespan(_):
        yield
        closed.set()

    app = FastAPI(lifespan=lifespan)

    @app.get("/stream")
    async def stream() -> StreamingResponse:
        async def forever():
            while True:
                yield b": keep-alive\n\n"
                await asyncio.sleep(0.2)

        return StreamingResponse(forever(), media_type="text/event-stream")

    server = uvicorn.Server(
        uvicorn.Config(
            app,
            host="127.0.0.1",
            port=0,
            log_level="warning",
            timeout_graceful_shutdown=cli.SHUTDOWN_GRACE_S,
        )
    )
    serving = threading.Thread(target=server.run, daemon=True)
    serving.start()
    deadline = time.monotonic() + 10
    while not server.started and time.monotonic() < deadline:
        time.sleep(0.05)
    assert server.started, "uvicorn did not start"
    port = server.servers[0].sockets[0].getsockname()[1]
    opened = threading.Event()

    def read() -> None:
        try:
            with httpx.Client(trust_env=False, timeout=httpx.Timeout(5, read=None)) as client:
                with client.stream("GET", f"http://127.0.0.1:{port}/stream") as response:
                    for _ in response.iter_raw():
                        opened.set()
        except httpx.HTTPError:
            pass

    threading.Thread(target=read, daemon=True).start()
    assert opened.wait(5)
    started = time.monotonic()
    server.should_exit = True  # what uvicorn's own handler sets at Ctrl+C
    serving.join(cli.SHUTDOWN_GRACE_S + 5)

    assert not serving.is_alive()
    assert time.monotonic() - started < cli.SHUTDOWN_GRACE_S + 3
    assert closed.is_set()


def test_the_session_is_closed_at_exit_even_without_the_lifespan(monkeypatch):
    """Finition V1 (#21): a second Ctrl+C during the grace delay skips uvicorn's lifespan,
    which closes the session (an Ollama model stays loaded): `main` closes it, then `atexit`."""
    registered: list = []

    class _Session:
        def __init__(self, cfg, port) -> None:
            pass

        def first_launch(self) -> bool:
            return False

    class _AppSession:
        closed = 0

        def __init__(self, cfg) -> None:
            pass

        def close(self) -> None:
            _AppSession.closed += 1

    monkeypatch.setattr(
        cli, "_try_reserve_port", lambda port: type("R", (), {"close": lambda s: None})()
    )
    monkeypatch.setattr(cli, "DiagnosticSession", _Session)
    monkeypatch.setattr(cli, "AppSession", _AppSession)
    monkeypatch.setattr(cli, "create_app", lambda *args, **kwargs: "app")
    monkeypatch.setattr(
        cli, "get_journal", lambda: type("J", (), {"subscribe": lambda s, f: None})()
    )
    monkeypatch.setattr(cli, "_run_diagnostic_then_boot", lambda *args: None)
    monkeypatch.setattr(cli, "_open_browser", lambda *args: None)
    monkeypatch.setattr(cli.uvicorn, "run", lambda app, **kwargs: None)  # no lifespan ran
    monkeypatch.setattr(cli.atexit, "register", registered.append)

    assert cli.main([]) == 0
    # On the main thread as `uvicorn.run` returns, before the worker threads are joined...
    assert _AppSession.closed == 1
    # ... and at the interpreter's exit, as a last resort (`close` does nothing twice).
    [close] = registered
    assert close.__func__ is _AppSession.close


def test_closing_the_session_twice_closes_its_engine_once():
    """Finition V1 (#21): the lifespan, then `atexit`; the second `close` does nothing."""
    from fake_engine import FakeEngine, booted_session

    engine, closed = FakeEngine(), []
    engine.close = lambda: closed.append(1)
    session = booted_session(engine)
    session.close()
    session.close()
    assert closed == [1] and not session.model_loaded
