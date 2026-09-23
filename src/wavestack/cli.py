"""``wavestack`` entry point: launch sequence and diagnostic (AD-21, AD-24).

Sequencing matters: the network guard installs before any third-party
import (AD-15), which is why `config` and `net.guard` (stdlib-only modules)
are imported and used at module load time, ahead of everything else.
"""

from __future__ import annotations

import argparse
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

os.environ["HF_HUB_DISABLE_XET"] = "1"
os.environ["HF_HUB_DISABLE_TELEMETRY"] = "1"
# HF_HUB_OFFLINE is never set: it is read at import time and would block a
# later, explicit model download (AD-15).

import truststore  # noqa: E402 - must follow the guard install above

truststore.inject_into_ssl()

import uvicorn  # noqa: E402

from wavestack.session.diagnostic import DiagnosticSession  # noqa: E402
from wavestack.trace.journal import get_journal  # noqa: E402
from wavestack.web.app import create_app  # noqa: E402

VERSION = "0.1.0"


def _print_journal_event(envelope) -> None:  # noqa: ANN001
    """AD-21 rule 3: diagnostic_check/harness_error events print to the terminal too."""
    if envelope.kind not in ("diagnostic_check", "harness_error"):
        return
    payload = envelope.payload
    parts = [payload.get("message_fr", "")]
    for key in ("action_fr", "cause"):
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


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="wavestack", description="Lance WaveStack.")
    parser.add_argument(
        "--port", type=int, default=_cfg.port, help="Port d'écoute (défaut : configuration)."
    )
    args = parser.parse_args(argv)

    reserved = _try_reserve_port(args.port)
    if reserved is None:
        if _existing_instance_healthy(args.port):
            webbrowser.open(f"http://127.0.0.1:{args.port}/diagnostic")
            return 0
        print(
            f"Le port {args.port} est déjà utilisé par un autre programme. "
            f"Relancez avec --port <autre_port>."
        )
        return 1
    # ponytail: release-then-rebind is a small race window, acceptable for a
    # local training demo. Upgrade to a passed-fd server if it ever bites.
    reserved.close()

    session = DiagnosticSession(_cfg, args.port)
    app = create_app(session, port=args.port, version=VERSION)

    get_journal().subscribe(_print_journal_event)

    threading.Thread(target=session.run, name="wavestack-diagnostic", daemon=True).start()

    def _open_browser() -> None:
        time.sleep(1.0)
        webbrowser.open(f"http://127.0.0.1:{args.port}/diagnostic")

    threading.Thread(target=_open_browser, name="wavestack-browser", daemon=True).start()

    uvicorn.run(app, host="127.0.0.1", port=args.port, log_level="warning")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
