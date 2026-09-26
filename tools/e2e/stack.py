"""Starts the fake OpenAI server and WaveStack on a throwaway data dir (end-to-end tests).

The fake model is declared as a cloud model in that data dir's `settings.json`, never in
`wavestack.toml`; its key comes from the variable its `key_env` names. WaveStack opens no
browser (`BROWSER=true`) and finds no local GGUF (`HF_HOME`, `OLLAMA_MODELS` in the dir).
Story 18: a fake llama-server and a fake Ollama (`fake_local_server.py`) run on free ports,
which `settings.json` gives as `[net.loopback_ports]`.

Run alone to explore by hand: `uv run python tools/e2e/stack.py` (Ctrl+C stops both).
"""

from __future__ import annotations

import json
import os
import shutil
import socket
import subprocess
import sys
import tempfile
import time
import urllib.request
from collections.abc import Iterator
from contextlib import contextmanager
from dataclasses import dataclass, field
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
HERE = Path(__file__).resolve().parent
KEY_ENV = "WAVESTACK_FAKE_API_KEY"
MODEL_ENTRY_ID = "fake"
# Story 17: a second fake model, for the hot switch; `launch_app.py` slows its loading.
SECOND_ENTRY_ID = "fake_b"
SECOND_MODEL = "faux-modele-b"


def free_port() -> int:
    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]


def _entry(fake_port: int, entry_id: str, provider: str, model: str) -> dict:
    return {
        "id": entry_id,
        "provider": provider,
        "base_url": f"http://127.0.0.1:{fake_port}/v1",
        "model": model,
        "stream_usage": True,
        "tools": True,
        "context": 32768,
        "hosting_fr": "Ce poste (faux serveur de test, boucle locale)",
        "training": "no",
        "notes_fr": "Faux modèle scripté pour les tests de bout en bout.",
        "key_env": KEY_ENV,
    }


def settings(fake_port: int, llama_port: int = 0, ollama_port: int = 0) -> dict:
    """The `settings.json` override: two cloud models, both on the fake server; the ports of
    the fake local servers (story 18)."""
    values: dict = {
        "cloud": {
            "models": [
                _entry(fake_port, MODEL_ENTRY_ID, "Faux fournisseur (e2e)", "wavestack-fake"),
                _entry(fake_port, SECOND_ENTRY_ID, "Faux fournisseur B (e2e)", SECOND_MODEL),
            ]
        }
    }
    if llama_port and ollama_port:
        values["net"] = {"loopback_ports": {"ollama": ollama_port, "llama_server": llama_port}}
    return values


def wait_http(url: str, timeout_s: float = 60.0) -> None:
    deadline = time.monotonic() + timeout_s
    while time.monotonic() < deadline:
        try:
            with urllib.request.urlopen(url, timeout=2) as response:
                if response.status == 200:
                    return
        except OSError:
            pass
        time.sleep(0.3)
    raise TimeoutError(f"{url} ne répond pas après {timeout_s:g} s")


def _stop(proc: subprocess.Popen) -> None:
    proc.terminate()
    try:
        proc.wait(timeout=10)
    except subprocess.TimeoutExpired:
        proc.kill()


@dataclass
class Stack:
    app_url: str
    fake_url: str
    data_dir: Path
    log_dir: Path
    app_port: int
    env: dict[str, str]
    llama_url: str = ""
    ollama_url: str = ""
    # Fake servers first, WaveStack last (`restart_app` pops it).
    procs: list[subprocess.Popen] = field(default_factory=list)
    launches: int = 0

    def fake_requests(self) -> list[dict]:
        with urllib.request.urlopen(f"{self.fake_url}/_e2e/requests", timeout=5) as r:
            return json.loads(r.read().decode("utf-8"))

    def local_requests(self, url: str) -> list[dict]:
        """What a fake local server received: `{path, body}`, newest last."""
        with urllib.request.urlopen(f"{url}/_e2e/requests", timeout=5) as r:
            return json.loads(r.read().decode("utf-8"))

    def start_app(self) -> None:
        """Launch WaveStack (again) on the same port and data dir; its log is numbered."""
        self.launches += 1
        suffix = "" if self.launches == 1 else f"-{self.launches}"
        log = open(self.log_dir / f"wavestack{suffix}.log", "w", encoding="utf-8")  # noqa: SIM115
        self.procs.append(
            subprocess.Popen(
                [sys.executable, str(HERE / "launch_app.py"), "--port", str(self.app_port)],
                cwd=REPO,
                env=self.env,
                stdout=log,
                stderr=subprocess.STDOUT,
            )
        )
        wait_http(f"{self.app_url}/api/health")

    def restart_app(self) -> None:
        """Stop WaveStack, then launch it again: a « prochain lancement »."""
        _stop(self.procs.pop())
        self.start_app()


def _env(data_dir: Path) -> dict[str, str]:
    env = dict(os.environ)
    env.update(
        {
            "WAVESTACK_DATA_DIR": str(data_dir),
            KEY_ENV: "e2e-fake-key",
            "BROWSER": "true",  # webbrowser.open runs `true`: nothing opens
            "HF_HOME": str(data_dir / "hf"),
            "OLLAMA_MODELS": str(data_dir / "ollama"),
            "PYTHONUNBUFFERED": "1",
        }
    )
    return env


@contextmanager
def running_stack(
    data_dir: Path | None = None, log_dir: Path | None = None, keep: bool = False
) -> Iterator[Stack]:
    """Both servers, stopped on exit; the data dir is removed unless `keep`."""
    owned = data_dir is None
    data_dir = data_dir or Path(tempfile.mkdtemp(prefix="wavestack-e2e-"))
    log_dir = log_dir or data_dir
    log_dir.mkdir(parents=True, exist_ok=True)
    data_dir.mkdir(parents=True, exist_ok=True)
    fake_port, app_port = free_port(), free_port()
    llama_port, ollama_port = free_port(), free_port()
    (data_dir / "settings.json").write_text(
        json.dumps(settings(fake_port, llama_port, ollama_port), ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    stack = Stack(
        app_url=f"http://127.0.0.1:{app_port}",
        fake_url=f"http://127.0.0.1:{fake_port}",
        data_dir=data_dir,
        log_dir=log_dir,
        app_port=app_port,
        env=_env(data_dir),
        llama_url=f"http://127.0.0.1:{llama_port}",
        ollama_url=f"http://127.0.0.1:{ollama_port}",
    )
    try:
        fake_log = open(log_dir / "fake_openai.log", "w", encoding="utf-8")  # noqa: SIM115
        stack.procs.append(
            subprocess.Popen(
                [sys.executable, str(HERE / "fake_openai.py"), "--port", str(fake_port)],
                cwd=REPO,
                env=stack.env,
                stdout=fake_log,
                stderr=subprocess.STDOUT,
            )
        )
        wait_http(f"{stack.fake_url}/v1/models")
        for flavor, port in (("llama_server", llama_port), ("ollama", ollama_port)):
            log = open(log_dir / f"fake_{flavor}.log", "w", encoding="utf-8")  # noqa: SIM115
            stack.procs.append(
                subprocess.Popen(
                    [
                        sys.executable,
                        str(HERE / "fake_local_server.py"),
                        "--flavor",
                        flavor,
                        "--port",
                        str(port),
                    ],
                    cwd=REPO,
                    env=stack.env,
                    stdout=log,
                    stderr=subprocess.STDOUT,
                )
            )
        wait_http(f"{stack.llama_url}/health")
        wait_http(f"{stack.ollama_url}/api/tags")
        stack.start_app()
        yield stack
    finally:
        for proc in reversed(stack.procs):
            _stop(proc)
        if owned and not keep:
            shutil.rmtree(data_dir, ignore_errors=True)


def main() -> None:
    with running_stack(keep=True) as stack:
        print(f"WaveStack : {stack.app_url}/diagnostic")
        print(f"Faux modèle : {stack.fake_url}/v1 (clé via {KEY_ENV})")
        print(f"Faux llama-server : {stack.llama_url} · faux Ollama : {stack.ollama_url}")
        print(f"Dossier de données : {stack.data_dir}")
        try:
            while True:
                time.sleep(1)
        except KeyboardInterrupt:
            pass


if __name__ == "__main__":
    main()
