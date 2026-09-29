"""WaveStack for the end-to-end run: `wavestack.cli`, the second fake model slowed down.

Loading a cloud model takes no time (no request, AD-21): the run could never see the
« Chargement du modèle… » stopwatch. Here, preparing the model `fake_b` waits
`WAVESTACK_E2E_LOAD_DELAY_S` seconds (2 by default); every other load is untouched.
"""

from __future__ import annotations

import os
import time

from wavestack.session import app_session

SLOW_REF = "fake_b"
DELAY_S = float(os.environ.get("WAVESTACK_E2E_LOAD_DELAY_S", "2"))
_install = app_session.AppSession._install


def _slow_install(self: app_session.AppSession, choice) -> None:  # noqa: ANN001
    if choice.ref == SLOW_REF:
        time.sleep(DELAY_S)
    _install(self, choice)


app_session.AppSession._install = _slow_install

if __name__ == "__main__":
    from wavestack import cli

    raise SystemExit(cli.main())
