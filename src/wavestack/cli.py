"""``wavestack`` entry point: launch sequence and diagnostic (AD-21, AD-24).

Sequencing matters: the network guard installs before any third-party
import (AD-15), which is why `config` and `net.guard` (stdlib-only modules)
are imported and used at module load time, ahead of everything else.
"""

from __future__ import annotations

import argparse
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


def _print_journal_event(envelope) -> None:  # noqa: ANN001
    """AD-21 rule 3: diagnostic_check/harness_error events print to the terminal too."""
    if envelope.kind not in ("diagnostic_check", "harness_error"):
        return
    payload = envelope.payload
    parts = [payload.get("message_text", "")]
    for key in ("action_text", "cause"):
        if payload.get(key):
            parts.append(payload[key])
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


def _existing_instance_healthy(port: int) -> bool:
    try:
        with urllib.request.urlopen(f"http://127.0.0.1:{port}/api/health", timeout=2) as resp:
            return resp.status == 200
    except (urllib.error.URLError, OSError):
        return False


def _existing_instance_ready(port: int) -> bool:
    """The running instance's `GET /api/diagnostic` says `ready`, with nothing blocking:
    `launch_page`'s rule."""
    try:
        with urllib.request.urlopen(f"http://127.0.0.1:{port}/api/diagnostic", timeout=2) as resp:
            body = json.loads(resp.read().decode("utf-8"))
        result = DiagnosticResult(
            ready=bool(body.get("ready")), blocking_checks=list(body.get("blocking_checks") or [])
        )
    except (urllib.error.URLError, OSError, ValueError, AttributeError, TypeError):
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
    parser = argparse.ArgumentParser(prog="wavestack", description="Lance WaveStack.")
    parser.add_argument(
        "--port", type=int, default=_cfg.port, help="Port d'écoute (défaut : configuration)."
    )
    args = parser.parse_args(argv)

    reserved = _try_reserve_port(args.port)
    if reserved is None:
        if _existing_instance_healthy(args.port):
            page = "/" if _existing_instance_ready(args.port) else "/diagnostic"
            webbrowser.open(f"http://127.0.0.1:{args.port}{page}")
            return 0
        print(
            f"Le port {args.port} est déjà utilisé par un autre programme. "
            f"Relancez avec --port <autre_port>."
        )
        return 1
    # ponytail: release-then-rebind is a small race window, acceptable for a
    # local training demo. Upgrade to a passed-fd server if it ever bites.
    reserved.close()

    # Story 24 (AD-8): the memory budget, computed now, once, from the RAM available at
    # launch: before the diagnostic and any model load, shared by both sessions.
    _cfg.memory_budget  # noqa: B018 - evaluated for its cached value
    session = DiagnosticSession(_cfg, args.port)
    app_session = AppSession(_cfg)
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

    uvicorn.run(app, host="127.0.0.1", port=args.port, log_level="warning")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
