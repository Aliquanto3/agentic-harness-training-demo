"""Starts the fake OpenAI server and WaveStack on a throwaway data dir (end-to-end tests).

The fake model is declared as a cloud model in that data dir's `settings.json`, never in
`wavestack.toml`; its key comes from the variable its `key_env` names. WaveStack opens no
browser (`BROWSER=true`) and finds no local GGUF (`HF_HOME`, `OLLAMA_MODELS` in the dir).
Story 18: a fake llama-server and a fake Ollama (`fake_local_server.py`) run on free ports,
which `settings.json` gives as `[net.loopback_ports]`.
Lot D: WaveStack's outbound network is cut by the launcher itself (`_env`, closed proxy), so
the run gives the same result on a connected workstation, behind a proxy or offline.

Run alone to explore by hand: `uv run python tools/e2e/stack.py` (Ctrl+C stops both);
`--network` keeps the workstation's proxies, so the real network stays reachable.
"""

from __future__ import annotations

import argparse
import json
import os
import shutil
import socket
import subprocess
import sys
import tempfile
import time
import tomllib
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
# Story 33: a third fake model that always reasons, for the locked reasoning card.
REASONING_ENTRY_ID = "fake_r"
REASONING_MODEL = "faux-modele-raisonne"
# A fourth fake model shaped as Gemini 3.x (`fake_openai.py`'s Gemini mode, by its name):
# the reasoning and `tool_call_extra` of the real `gemini` preset, read in wavestack.toml.
GEMINI_ENTRY_ID = "fake_g"
GEMINI_MODEL = "gemini-e2e-flash-lite"
GEMINI_PROVIDER = "Faux Gemini (e2e)"


# The launcher's own requests only reach the loopback: never through the workstation's proxy.
_loopback = urllib.request.build_opener(urllib.request.ProxyHandler({}))


def free_port() -> int:
    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]


EMBEDDING_FILE = "embedding/fake-e2e.gguf"
EMBEDDING_SIZE = 4096  # `fake_openai.MODEL_FILE_SIZE`
RERANKER_FILE = "reranker/fake-e2e.gguf"
RERANKER_SIZE = 2048  # `fake_openai.RERANKER_FILE_SIZE`


def _entry(
    fake_port: int, entry_id: str, provider: str, model: str, reasoning: dict | None = None
) -> dict:
    entry = {
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
        # Story 29: as the Groq and Mistral presets, for the « LLM nu » screen.
        "sampling": ["temperature", "top_p"],
    }
    if reasoning is not None:
        entry["reasoning"] = reasoning
    return entry


def gemini_preset() -> dict:
    """The `gemini` entry of wavestack.toml, as declared (never modified)."""
    with (REPO / "wavestack.toml").open("rb") as f:
        models = tomllib.load(f)["cloud"]["models"]
    return next(m for m in models if m["id"] == "gemini")


def _gemini_entry(fake_port: int) -> dict:
    preset = gemini_preset()
    entry = _entry(
        fake_port, GEMINI_ENTRY_ID, GEMINI_PROVIDER, GEMINI_MODEL, reasoning=preset["reasoning"]
    )
    entry["tool_call_extra"] = preset["tool_call_extra"]
    return entry


def rag_settings(fake_port: int, data_dir: Path) -> dict:
    """Story 15: the index in the data dir (absent at first, built from the RAG card, as on a
    fresh install), the fake embedding model (its file served by the fake server, over the
    loopback); story 16: the fake reranker's, likewise."""
    return {
        "index_path": str(data_dir / "rag_index.sqlite"),
        "embedding": {
            "id": "fake-embedding",
            "label_fr": "Faux embedding (e2e)",
            "dims": 64,
            "load_path": EMBEDDING_FILE,
            "files": [
                {
                    "url": f"http://127.0.0.1:{fake_port}/_e2e/model.gguf",
                    "path": EMBEDDING_FILE,
                    "size": EMBEDDING_SIZE,
                }
            ],
        },
        # Story 16: the fake reranker, absent at first, its file served by the fake server.
        "reranker": {
            "id": "fake-reranker",
            "label_fr": "Faux reranker (e2e)",
            "load_path": RERANKER_FILE,
            "files": [
                {
                    "url": f"http://127.0.0.1:{fake_port}/_e2e/reranker.gguf",
                    "path": RERANKER_FILE,
                    "size": RERANKER_SIZE,
                }
            ],
        },
    }


def settings(fake_port: int, data_dir: Path, llama_port: int = 0, ollama_port: int = 0) -> dict:
    """The `settings.json` override: four cloud models, all on the fake server (the third
    always reasons, story 33; the fourth is shaped as Gemini); the RAG's
    index and fake embedding model (story 15); the ports of the fake local servers (story
    18)."""
    values: dict = {
        "rag": rag_settings(fake_port, data_dir),
        "cloud": {
            "models": [
                _entry(fake_port, MODEL_ENTRY_ID, "Faux fournisseur (e2e)", "wavestack-fake"),
                _entry(fake_port, SECOND_ENTRY_ID, "Faux fournisseur B (e2e)", SECOND_MODEL),
                _entry(
                    fake_port,
                    REASONING_ENTRY_ID,
                    "Faux fournisseur R (e2e)",
                    REASONING_MODEL,
                    reasoning={"format": "field", "always": True},
                ),
                _gemini_entry(fake_port),
            ]
        },
    }
    if llama_port and ollama_port:
        values["net"] = {"loopback_ports": {"ollama": ollama_port, "llama_server": llama_port}}
    return values


def wait_http(url: str, timeout_s: float = 60.0) -> None:
    deadline = time.monotonic() + timeout_s
    while time.monotonic() < deadline:
        try:
            with _loopback.open(url, timeout=2) as response:
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
        with _loopback.open(f"{self.fake_url}/_e2e/requests", timeout=5) as r:
            return json.loads(r.read().decode("utf-8"))

    def local_requests(self, url: str) -> list[dict]:
        """What a fake local server received: `{path, body}`, newest last."""
        with _loopback.open(f"{url}/_e2e/requests", timeout=5) as r:
            return json.loads(r.read().decode("utf-8"))

    def start_app(self) -> None:
        """Launch WaveStack (again) on the same port and data dir; its log is numbered."""
        self.launches += 1
        suffix = "" if self.launches == 1 else f"-{self.launches}"
        log = open(self.log_dir / f"wavestack{suffix}.log", "w", encoding="utf-8")  # noqa: SIM115
        self.procs.append(
            subprocess.Popen(
                [sys.executable, str(HERE / "wavestack_e2e.py"), "--port", str(self.app_port)],
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


# Lot D: the run cuts WaveStack's outbound network itself, so that it gives the same result
# on a connected workstation, behind an office proxy or offline. Its proxy variables name a
# loopback port on which nothing listens (`closed_port`): a request to a public host still
# passes the network guard and is traced (`outbound_request`, which `network_tools` and H5
# check), then fails (proxy unreachable), explained. `allowed_hosts` cannot do it: the guard
# refuses a host outside the list before tracing it. The loopback (fake servers) bypasses it.
LOOPBACK_NO_PROXY = "127.0.0.1,localhost,::1"
PROXY_VARS = ("HTTP_PROXY", "HTTPS_PROXY", "ALL_PROXY")


@contextmanager
def closed_port() -> Iterator[int]:
    """A loopback port bound but never listening while the stack runs: a connection to it is
    refused, and no other process can take it meanwhile."""
    with socket.socket() as s:
        if sys.platform == "win32":  # else a socket with SO_REUSEADDR could still bind it
            s.setsockopt(socket.SOL_SOCKET, socket.SO_EXCLUSIVEADDRUSE, 1)
        s.bind(("127.0.0.1", 0))
        yield s.getsockname()[1]


def _env(data_dir: Path, proxy_port: int | None) -> dict[str, str]:
    """`proxy_port=None` (manual exploration with `--network`) keeps the workstation's
    proxies: the real network stays reachable."""
    env = dict(os.environ)
    if proxy_port is not None:
        # Every inherited proxy variable goes (any case, any scheme): only ours remain.
        env = {k: v for k, v in env.items() if not k.lower().endswith("_proxy")}
        proxy = f"http://127.0.0.1:{proxy_port}"
        for name, value in [(n, proxy) for n in PROXY_VARS] + [("NO_PROXY", LOOPBACK_NO_PROXY)]:
            env[name] = value
            if sys.platform != "win32":  # case-insensitive there: one name only
                env[name.lower()] = value
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
    data_dir: Path | None = None,
    log_dir: Path | None = None,
    keep: bool = False,
    network: bool = False,
) -> Iterator[Stack]:
    """Both servers, stopped on exit; the data dir is removed unless `keep`. WaveStack's
    outbound network is cut unless `network` (manual exploration only)."""
    owned = data_dir is None
    data_dir = data_dir or Path(tempfile.mkdtemp(prefix="wavestack-e2e-"))
    log_dir = log_dir or data_dir
    log_dir.mkdir(parents=True, exist_ok=True)
    data_dir.mkdir(parents=True, exist_ok=True)
    with closed_port() as proxy_port:
        fake_port, app_port = free_port(), free_port()
        llama_port, ollama_port = free_port(), free_port()
        (data_dir / "settings.json").write_text(
            json.dumps(
                settings(fake_port, data_dir, llama_port, ollama_port), ensure_ascii=False, indent=2
            ),
            encoding="utf-8",
        )
        stack = Stack(
            app_url=f"http://127.0.0.1:{app_port}",
            fake_url=f"http://127.0.0.1:{fake_port}",
            data_dir=data_dir,
            log_dir=log_dir,
            app_port=app_port,
            env=_env(data_dir, None if network else proxy_port),
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
    parser = argparse.ArgumentParser(description="Faux modèle et WaveStack, pour explorer.")
    parser.add_argument(
        "--network",
        action="store_true",
        help="garder le réseau sortant (proxys du poste) ; coupé par défaut, comme le parcours",
    )
    args = parser.parse_args()
    with running_stack(keep=True, network=args.network) as stack:
        print(f"WaveStack : {stack.app_url}/diagnostic")
        print(f"Faux modèle : {stack.fake_url}/v1 (clé via {KEY_ENV})")
        print(f"Faux llama-server : {stack.llama_url} · faux Ollama : {stack.ollama_url}")
        print(f"Dossier de données : {stack.data_dir}")
        print(
            "Réseau sortant : " + ("gardé" if args.network else "coupé (--network pour le garder)")
        )
        try:
            while True:
                time.sleep(1)
        except KeyboardInterrupt:
            pass


if __name__ == "__main__":
    main()
