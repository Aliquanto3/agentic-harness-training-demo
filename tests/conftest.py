from __future__ import annotations

import os
import urllib.request
from pathlib import Path

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


@pytest.fixture
def real_models_dir() -> Path:
    """Lot G (G2): the real models' folder, for the `model` tests of the RAG, named by
    `WAVESTACK_TEST_MODELS_DIR` (the data dir stays isolated); skipped without it."""
    value = os.environ.get("WAVESTACK_TEST_MODELS_DIR")
    if not value:
        pytest.skip(
            "WAVESTACK_TEST_MODELS_DIR n'est pas posée : elle doit nommer le dossier des "
            "modèles de WaveStack, par exemple : "
            '$env:WAVESTACK_TEST_MODELS_DIR = "$env:LOCALAPPDATA\\WaveStack\\models"'
        )
    path = Path(value)
    if not path.is_dir():
        pytest.skip(f"WAVESTACK_TEST_MODELS_DIR ne nomme pas un dossier : {path}")
    return path


_PROC = Path("/proc/self")


def _held_open() -> set[str]:
    """The files this process holds: open descriptors and memory-mapped files (Linux)."""
    held = set()
    for fd in (_PROC / "fd").iterdir():
        try:
            held.add(os.readlink(fd))
        except OSError:
            pass
    for line in (_PROC / "maps").read_text().splitlines():
        parts = line.split(maxsplit=5)
        if len(parts) == 6 and parts[5].startswith("/"):
            held.add(parts[5])
    return held


@pytest.fixture
def windows_file_rules(monkeypatch):
    """Lot G: Windows' file rules, simulated on Linux. Windows refuses to replace, rename or
    delete a file an open handle holds (WinError 32); this fixture makes `os.replace`,
    `os.rename`, `os.unlink` and `os.remove` (hence `Path.replace`, `Path.unlink`…) raise
    the same `PermissionError` (`winerror` 32) when their source or target is a file this
    process holds open (descriptor or memory mapping, read in `/proc/self`). Without
    `/proc` (Windows applies its rules itself, macOS), nothing is patched.

    Opt-in for the whole suite: `WAVESTACK_TEST_WINDOWS_FILES=1 uv run pytest`."""
    if not (_PROC / "fd").is_dir():
        return

    def guarded(name: str):  # noqa: ANN202
        original = getattr(os, name)

        def call(*paths, **kwargs):  # noqa: ANN002, ANN003
            held = _held_open()
            for path in paths:
                if kwargs.get("dir_fd") or kwargs.get("src_dir_fd"):
                    break  # relative to a directory descriptor: not simulated
                real = os.path.realpath(os.fsdecode(path))
                if real in held and os.path.isfile(real):
                    exc = PermissionError(
                        13, f"[WinError 32 simulée] {name} : fichier ouvert par le processus", real
                    )
                    exc.winerror = 32
                    raise exc
            return original(*paths, **kwargs)

        return call

    for name in ("replace", "rename", "unlink", "remove"):
        monkeypatch.setattr(os, name, guarded(name))


@pytest.fixture(autouse=True)
def _windows_file_rules_opt_in(request):
    """Lot G: `WAVESTACK_TEST_WINDOWS_FILES=1` puts every test under `windows_file_rules`."""
    if os.environ.get("WAVESTACK_TEST_WINDOWS_FILES") == "1":
        request.getfixturevalue("windows_file_rules")


@pytest.fixture(autouse=True)
def _no_cloud_key_variables(monkeypatch):
    """Story 11b: a key the machine's environment provides never reaches a test."""
    for name in ("GROQ_API_KEY", "MISTRAL_API_KEY", "GEMINI_API_KEY"):
        monkeypatch.delenv(name, raising=False)


@pytest.fixture(autouse=True)
def _fresh_pacing():
    """Story 11b: the spacing of cloud sends starts afresh in each test."""
    from wavestack.models import openai_chat

    openai_chat._last_start.clear()
    openai_chat.reset_spend()  # FinOps: the session's spend starts at zero in each test
    yield
    openai_chat._last_start.clear()
    openai_chat.reset_spend()


@pytest.fixture(autouse=True)
def _no_local_model_server(monkeypatch):
    """Story 18: no real Ollama nor llama-server is ever reached from a test; a test that
    needs one passes its own `httpx.MockTransport`."""
    import httpx

    from wavestack.models import servers

    def refuse(request: httpx.Request) -> httpx.Response:
        raise httpx.ConnectError("aucun serveur local en test", request=request)

    monkeypatch.setattr(servers, "default_transport", httpx.MockTransport(refuse))


GIB = 1024**3


@pytest.fixture(autouse=True)
def _fixed_system_memory(monkeypatch):
    """Story 24: the machine's RAM, pinned (16 Gio, 12 Gio available): the dynamic budget
    stays at its 4 096 Mo cap whatever the machine running the tests."""
    from wavestack import config

    monkeypatch.setattr(config, "system_memory", lambda: (16 * GIB, 12 * GIB))
