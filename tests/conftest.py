from __future__ import annotations

import pytest

from wavestack.net.guard import install


@pytest.fixture(autouse=True, scope="session")
def _network_guard() -> None:
    """AD-15: pytest installs the same guard, restricted to loopback only."""
    install(allowed_hosts=[])


@pytest.fixture(autouse=True)
def _isolated_data_dir(tmp_path, monkeypatch):
    """Never touch the real user data dir (AD-20) while testing."""
    monkeypatch.setenv("WAVESTACK_DATA_DIR", str(tmp_path / "wavestack-data"))
