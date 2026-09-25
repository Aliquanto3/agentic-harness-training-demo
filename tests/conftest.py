from __future__ import annotations

import os
import urllib.request

import pytest

from wavestack.net.guard import install

_PROXY_VARS = ("http_proxy", "https_proxy", "all_proxy", "no_proxy")


@pytest.fixture(autouse=True, scope="session")
def _network_guard() -> None:
    """AD-15: pytest installs the same guard, restricted to loopback only.

    This machine's proxy is ignored: a loopback proxy would be accepted by the
    guard and would carry any destination past it (story 1e).
    """
    for name in list(os.environ):
        if name.lower() in _PROXY_VARS:
            del os.environ[name]
    urllib.request.getproxies_registry = lambda: {}
    install(allowed_hosts=[])


@pytest.fixture(autouse=True)
def _isolated_data_dir(tmp_path, monkeypatch):
    """Never touch the real user data dir (AD-20) while testing."""
    monkeypatch.setenv("WAVESTACK_DATA_DIR", str(tmp_path / "wavestack-data"))
