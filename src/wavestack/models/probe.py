"""GGUF probe: full load in a child process before first use (AD-7).

Run as ``python -m wavestack.models.probe <path>``. A GGUF never loaded
successfully before is probed this way so a corrupt or incompatible file
cannot crash the main process mid-session (AD-16).

Installs the same network guard as the main process (AD-15), since loading
a model must never reach the network.
"""

from __future__ import annotations

import json
import os
import sys
import time
from pathlib import Path
from typing import Any

import psutil
from pydantic import BaseModel

from wavestack import config


class ProbeResult(BaseModel):
    ok: bool
    path: str
    reason: str | None = None
    architecture: str | None = None
    has_chat_template: bool = False
    rss_bytes: int | None = None
    size_bytes: int | None = None
    mtime: float | None = None


def probe_file(path: str) -> ProbeResult:
    """Load `path` fully in this process and report the outcome. Never raises."""
    file_path = Path(path)
    if not file_path.is_file():
        return ProbeResult(ok=False, path=path, reason="Fichier introuvable.")

    try:
        from llama_cpp import Llama
    except ImportError:
        return ProbeResult(ok=False, path=path, reason="llama-cpp-python non installé.")

    try:
        llm = Llama(model_path=str(file_path), n_ctx=16, n_batch=16, verbose=False)
    except Exception as exc:  # noqa: BLE001 - any load failure marks the file incompatible
        return ProbeResult(ok=False, path=path, reason=f"Chargement impossible : {exc}")

    try:
        metadata: dict[str, Any] = getattr(llm, "metadata", {}) or {}
        architecture = metadata.get("general.architecture")
        has_chat_template = bool(metadata.get("tokenizer.chat_template"))
        rss_bytes = psutil.Process(os.getpid()).memory_info().rss
        stat = file_path.stat()
        return ProbeResult(
            ok=True,
            path=path,
            architecture=architecture,
            has_chat_template=has_chat_template,
            rss_bytes=rss_bytes,
            size_bytes=stat.st_size,
            mtime=stat.st_mtime,
        )
    finally:
        if hasattr(llm, "close"):
            llm.close()


def record_success(result: ProbeResult) -> None:
    """Persist a successful probe (path, size, mtime) in settings.json (AD-7, AD-20)."""
    if not result.ok:
        return
    path = config.settings_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    settings: dict[str, Any] = {}
    if path.exists():
        try:
            settings = json.loads(path.read_text(encoding="utf-8"))
        except json.JSONDecodeError:
            settings = {}
    probed = settings.setdefault("probed_models", {})
    probed[result.path] = {
        "size_bytes": result.size_bytes,
        "mtime": result.mtime,
        "architecture": result.architecture,
        "has_chat_template": result.has_chat_template,
        "probed_at": time.time(),
    }
    path.write_text(json.dumps(settings, ensure_ascii=False, indent=2), encoding="utf-8")


def already_probed(path: str) -> bool:
    """True if `path` was probed successfully before, with a matching size/mtime."""
    settings_file = config.settings_path()
    if not settings_file.exists():
        return False
    try:
        settings = json.loads(settings_file.read_text(encoding="utf-8"))
    except json.JSONDecodeError:
        return False
    entry = settings.get("probed_models", {}).get(path)
    if not entry:
        return False
    file_path = Path(path)
    if not file_path.is_file():
        return False
    stat = file_path.stat()
    return entry.get("size_bytes") == stat.st_size and entry.get("mtime") == stat.st_mtime


def main() -> int:
    from wavestack.net.guard import install as install_guard

    cfg = config.load_config()
    install_guard(cfg.allowed_hosts)

    if len(sys.argv) != 2:
        print(json.dumps({"ok": False, "reason": "Usage: probe.py <path>"}))
        return 2

    result = probe_file(sys.argv[1])
    print(result.model_dump_json())
    return 0 if result.ok else 1


if __name__ == "__main__":
    raise SystemExit(main())
