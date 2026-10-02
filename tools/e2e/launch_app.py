"""WaveStack for the end-to-end run: `wavestack.cli`, the second fake model slowed down.

Loading a cloud model takes no time (no request, AD-21): the run could never see the
« Chargement du modèle… » stopwatch. Here, preparing the model `fake_b` waits
`WAVESTACK_E2E_LOAD_DELAY_S` seconds (2 by default); every other load is untouched.

Story 24: the probe of a file named `sonde-lente-e2e.gguf` is a child that only sleeps
(120 s), its path kept last to find it again: a slow probe without a real model, for
« Arrêter » to kill.

Restes différés, story 6: `read_file` of `confidentiel/outil-lent-e2e` waits
`WAVESTACK_E2E_TOOL_DELAY_S` seconds (1.5 by default), a slow tool to see the schema at work.
"""

from __future__ import annotations

import os
import sys
import time
from pathlib import Path

from wavestack.session import app_session, diagnostic

SLOW_REF = "fake_b"
DELAY_S = float(os.environ.get("WAVESTACK_E2E_LOAD_DELAY_S", "2"))
_install = app_session.AppSession._install


def _slow_install(self: app_session.AppSession, choice, window=None) -> None:  # noqa: ANN001
    if choice.ref == SLOW_REF:
        time.sleep(DELAY_S)
    _install(self, choice, window)  # story 26: the window of a reload, if any


app_session.AppSession._install = _slow_install

SLOW_PROBE = "sonde-lente-e2e.gguf"
_probe_argv = diagnostic._probe_argv


def _slow_probe_argv(path: str, window: int) -> list[str]:
    if Path(path).name == SLOW_PROBE:
        return [sys.executable, "-c", "import time; time.sleep(120)", path]
    return _probe_argv(path, window)


diagnostic._probe_argv = _slow_probe_argv

# Restes différés, story 6 (E020, E032): `read_file` of this path waits before it reads (the
# file does not exist: the tool then fails, explained), long enough for the page to show the
# robot « utilise un outil », the tool's halo and the path to its node.
SLOW_TOOL_PATH = "confidentiel/outil-lent-e2e"
SLOW_TOOL_DELAY_S = float(os.environ.get("WAVESTACK_E2E_TOOL_DELAY_S", "1.5"))
_read_file = app_session.AppSession._read_file


def _slow_read_file(self: app_session.AppSession, path: str) -> str:
    if path == SLOW_TOOL_PATH:
        time.sleep(SLOW_TOOL_DELAY_S)
    return _read_file(self, path)


app_session.AppSession._read_file = _slow_read_file

if __name__ == "__main__":
    from wavestack import cli

    raise SystemExit(cli.main())
