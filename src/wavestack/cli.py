"""``wavestack`` entry point: launch sequence and diagnostic (AD-21, AD-24).

Sequencing matters: the network guard installs before any third-party
import (AD-15), which is why `config` and `net.guard` (stdlib-only modules)
are imported and used at module load time, ahead of everything else.
"""

from __future__ import annotations

import argparse
import atexit
import http.client
import json
import logging
import os
import socket
import sys
import threading
import time
import urllib.error
import urllib.request
import webbrowser

from wavestack import config as _config
from wavestack.net.guard import install as _install_guard

_cfg = _config.load_config()
_install_guard(_cfg.allowed_hosts)

from wavestack.compression.env import apply_offline_env as _headroom_offline  # noqa: E402

_headroom_offline()  # story 20: Headroom's offline variables, before any third-party import

os.environ["HF_HUB_DISABLE_XET"] = "1"
os.environ["HF_HUB_DISABLE_TELEMETRY"] = "1"
# HF_HUB_OFFLINE is never set: it is read at import time and would block a
# later, explicit model download (AD-15).

import truststore  # noqa: E402 - must follow the guard install above

# AD-15: a request line at INFO/DEBUG could carry a cloud model's header; never below WARNING.
for _name in ("httpx", "httpcore"):
    logging.getLogger(_name).setLevel(logging.WARNING)

truststore.inject_into_ssl()

import uvicorn  # noqa: E402

from wavestack.messages import msg, render  # noqa: E402
from wavestack.session.app_session import AppSession  # noqa: E402
from wavestack.session.diagnostic import (  # noqa: E402
    DiagnosticResult,
    DiagnosticSession,
    launch_page,
)
from wavestack.trace.journal import get_journal  # noqa: E402
from wavestack.web.app import create_app  # noqa: E402

VERSION = "0.1.0"
BROWSER_DELAY_S = 1.0  # the page opens 1 s after the start at the earliest
LAUNCH_WAIT_S = 30.0  # past this, the diagnostic page opens while the checks go on
# Story 7 of the deferred leftovers (E077): an open page keeps its SSE stream, which uvicorn
# would wait for forever at Ctrl+C; past this delay the streams are cancelled and the
# lifespan still closes the engines. A second Ctrl+C skips the lifespan: `main` closes the
# session after `uvicorn.run` returns, and `atexit` as a last resort (finition V1, #21; `close`
# does nothing the second time). The local MCP servers are then left to `asyncio.run`, whose
# loop is closed. Closing the console window may end the process before either (not measured).
SHUTDOWN_GRACE_S = 2.0
# Languages (5/5): the terminal speaks English, whatever the session's language; never
# read from settings.json.
TERMINAL_LANGUAGE = "en"


def _english(text: object) -> str:
    """A text of an event in the terminal's language: one that keeps its `Message` (the
    diagnostic's `Said`, a keyed error) or a `Message` is rendered again; any other text
    (a third party's, or not keyed yet) is printed as it is."""
    return render(getattr(text, "message", text), TERMINAL_LANGUAGE)


def _print_journal_event(envelope) -> None:  # noqa: ANN001
    """AD-21 rule 3: diagnostic_check/harness_error events print to the terminal too."""
    if envelope.kind not in ("diagnostic_check", "harness_error"):
        return
    payload = envelope.payload
    parts = [_english(payload.get("message_text", ""))]
    for key in ("action_text", "cause"):
        if payload.get(key):
            parts.append(_english(payload[key]))
    print(" — ".join(parts))


def _try_reserve_port(port: int) -> socket.socket | None:
    sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    if sys.platform == "win32":
        # SO_REUSEADDR on Windows lets a second process silently bind an
        # already-listening port instead of failing — the opposite of what a
        # reservation check needs. SO_EXCLUSIVEADDRUSE is the Windows
        # equivalent of POSIX's plain (no-reuse) bind-fails-if-taken behavior.
        sock.setsockopt(socket.SOL_SOCKET, socket.SO_EXCLUSIVEADDRUSE, 1)
    else:
        sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
    try:
        sock.bind(("127.0.0.1", port))
        sock.listen(1)
        return sock
    except (OSError, OverflowError):
        sock.close()
        return None


def _existing_instance_health(port: int) -> dict | None:
    """Story R0 (CAP-1): the body of the running instance's `GET /api/health`; `{}` when it
    answers 200 with no readable JSON object (an older or foreign instance), `None` when
    nothing healthy answers."""
    try:
        with urllib.request.urlopen(f"http://127.0.0.1:{port}/api/health", timeout=2) as resp:
            if resp.status != 200:
                return None
            raw = resp.read(65536)  # a foreign responder never makes the CLI buffer forever
    except (urllib.error.URLError, OSError, http.client.HTTPException):
        return None
    try:
        body = json.loads(raw.decode("utf-8"))
    except (ValueError, UnicodeDecodeError):
        return {}
    return body if isinstance(body, dict) else {}


def _same_folder(a: str, b: str) -> bool:
    """Two folders compared once resolved, case-insensitive on Windows (`normcase`)."""
    try:
        return os.path.normcase(os.path.realpath(a)) == os.path.normcase(os.path.realpath(b))
    except (OSError, ValueError):
        return False


def _say_already_running(health: dict, port: int, lang: str) -> None:
    """Story R0 (CAP-1): where the reused instance was launched from, and a warning when it
    is not this folder (or it does not say: an instance from before)."""
    root = health.get("root")
    commit = health.get("commit")
    here = str(_config.repo_root())
    if not isinstance(root, str) or not root:
        print(msg("cli.already_running_unknown", lang, port=port))
        print(msg("cli.other_tree", lang, here=here))
        return
    if isinstance(commit, str) and commit:
        print(msg("cli.already_running", lang, port=port, root=root, commit=commit))
    else:
        print(msg("cli.already_running_no_commit", lang, port=port, root=root))
    if not _same_folder(root, here):
        print(msg("cli.other_tree", lang, here=here))


def _existing_instance_ready(port: int) -> bool:
    """The running instance's `GET /api/diagnostic` says `ready`, with nothing blocking:
    `launch_page`'s rule."""
    try:
        with urllib.request.urlopen(f"http://127.0.0.1:{port}/api/diagnostic", timeout=2) as resp:
            body = json.loads(resp.read().decode("utf-8"))
        result = DiagnosticResult(
            ready=bool(body.get("ready")), blocking_checks=list(body.get("blocking_checks") or [])
        )
    except (
        urllib.error.URLError,
        OSError,
        http.client.HTTPException,
        ValueError,
        AttributeError,
        TypeError,
    ):
        return False
    return launch_page(result) == "/"


class _Launched:
    """The launch diagnostic's result, once `session.run()` returned it."""

    def __init__(self) -> None:
        self.done = threading.Event()
        self.result: DiagnosticResult | None = None

    def set(self, result: DiagnosticResult) -> None:
        self.result = result
        self.done.set()


def _run_diagnostic_then_boot(
    session: DiagnosticSession, app_session: AppSession, launched: _Launched | None = None
) -> None:
    """The launch's diagnostic, then its model: a cloud model chosen at an earlier launch is
    prepared without any request (AD-21). `launched` learns the result first."""
    result = session.run()
    if launched is not None:
        launched.set(result)
    session.hand_to(app_session, result, launch=True)


def _open_browser(port: int, first: bool, launched: _Launched) -> None:
    """AD-21, step 2: at the first launch, the diagnostic after 1 s, to watch the checks.
    Later, once the result is known (1 s at the earliest, 30 s at most): the main page when
    ready with nothing blocking, else the diagnostic."""
    started = time.monotonic()
    page = "/diagnostic"
    if not first and launched.done.wait(LAUNCH_WAIT_S) and launched.result is not None:
        page = launch_page(launched.result)
    time.sleep(max(0.0, BROWSER_DELAY_S - (time.monotonic() - started)))
    webbrowser.open(f"http://127.0.0.1:{port}{page}")


def main(argv: list[str] | None = None) -> int:
    lang = TERMINAL_LANGUAGE
    parser = argparse.ArgumentParser(prog="wavestack", description=msg("cli.description", lang))
    parser.add_argument("--port", type=int, default=_cfg.port, help=msg("cli.port_help", lang))
    args = parser.parse_args(argv)

    reserved = _try_reserve_port(args.port)
    if reserved is None:
        health = _existing_instance_health(args.port)
        if health is not None:
            _say_already_running(health, args.port, lang)
            page = "/" if _existing_instance_ready(args.port) else "/diagnostic"
            webbrowser.open(f"http://127.0.0.1:{args.port}{page}")
            return 0
        print(msg("cli.port_taken", lang, port=args.port))
        return 1
    # ponytail: release-then-rebind is a small race window, acceptable for a
    # local training demo. Upgrade to a passed-fd server if it ever bites.
    reserved.close()

    # Story 24 (AD-8): the memory budget, computed now, once, from the RAM available at
    # launch: before the diagnostic and any model load, shared by both sessions.
    _cfg.memory_budget  # noqa: B018 - evaluated for its cached value
    session = DiagnosticSession(_cfg, args.port)
    app_session = AppSession(_cfg)
    atexit.register(app_session.close)  # #21: the lifespan skipped by a second Ctrl+C
    app = create_app(session, port=args.port, version=VERSION, app_session=app_session)

    get_journal().subscribe(_print_journal_event)

    first = session.first_launch()
    launched = _Launched()
    threading.Thread(
        target=_run_diagnostic_then_boot,
        args=(session, app_session, launched),
        name="wavestack-diagnostic",
        daemon=True,
    ).start()
    threading.Thread(
        target=_open_browser,
        args=(args.port, first, launched),
        name="wavestack-browser",
        daemon=True,
    ).start()

    try:
        uvicorn.run(
            app,
            host="127.0.0.1",
            port=args.port,
            log_level="warning",
            timeout_graceful_shutdown=SHUTDOWN_GRACE_S,
        )
    finally:
        # #21: on the main thread, before the interpreter joins the worker threads (a turn
        # waiting for an H5 answer would hold the exit): `stop()` cancels it first.
        app_session.close()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
