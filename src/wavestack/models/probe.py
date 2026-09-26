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
from importlib import metadata
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
    rss_bytes: int | None = None  # RSS gained by loading the model (n_ctx = 16)
    size_bytes: int | None = None
    mtime: float | None = None
    size_label: str | None = None  # `general.size_label`, e.g. « 2B » (DESIGN.md)
    # AD-8: the KV cache's bytes per token of context (f16 K and V), when the GGUF says it.
    kv_bytes_per_token: int | None = None


def _int_meta(meta: dict[str, Any], key: str) -> int | None:
    try:
        value = int(meta[key])
    except (KeyError, TypeError, ValueError):
        return None
    return value if value > 0 else None


def kv_bytes_per_token(meta: dict[str, Any]) -> int | None:
    """AD-8: the KV cache's bytes per token of context, f16 (2 bytes), K and V:
    `2 × Σ over layers (KV heads × (key size + value size))`, from the GGUF metadata.

    `head_count_kv` may be one integer or one value per layer (hybrid models such as
    Qwen3.5, whose linear-attention layers have 0 KV head); a value that is neither (e.g.
    an array llama-cpp-python only shows as text) gives `None`, never the attention heads
    instead. Sliding-window attention is not taken into account: an overestimate.
    """
    arch = meta.get("general.architecture")
    if not arch:
        return None
    layers = _int_meta(meta, f"{arch}.block_count")
    heads = _int_meta(meta, f"{arch}.attention.head_count")
    key_length = _int_meta(meta, f"{arch}.attention.key_length")
    if key_length is None:
        embedding = _int_meta(meta, f"{arch}.embedding_length")
        key_length = embedding // heads if embedding and heads else None
    value_length = _int_meta(meta, f"{arch}.attention.value_length") or key_length
    kv_key = f"{arch}.attention.head_count_kv"
    raw = meta.get(kv_key)
    if raw is None:
        kv_heads_total = layers * heads if layers and heads else None
    elif isinstance(raw, list | tuple):
        try:
            kv_heads_total = sum(int(n) for n in raw)
        except (TypeError, ValueError):
            kv_heads_total = None
    else:
        per_layer = _int_meta(meta, kv_key)
        kv_heads_total = layers * per_layer if layers and per_layer else None
    if not (kv_heads_total and key_length and value_length):
        return None
    return 2 * kv_heads_total * (key_length + value_length)


def probe_file(path: str) -> ProbeResult:
    """Load `path` fully in this process and report the outcome. Never raises."""
    file_path = Path(path)
    if not file_path.is_file():
        return ProbeResult(ok=False, path=path, reason="Fichier introuvable.")

    try:
        from llama_cpp import Llama
    except ImportError:
        return ProbeResult(ok=False, path=path, reason="llama-cpp-python non installé.")

    process = psutil.Process(os.getpid())
    before = process.memory_info().rss  # the interpreter and llama-cpp-python, without weights
    try:
        llm = Llama(model_path=str(file_path), n_ctx=16, n_batch=16, verbose=False)
    except Exception as exc:  # noqa: BLE001 - any load failure marks the file incompatible
        return ProbeResult(ok=False, path=path, reason=f"Chargement impossible : {exc}")

    try:
        metadata: dict[str, Any] = getattr(llm, "metadata", {}) or {}
        architecture = metadata.get("general.architecture")
        has_chat_template = bool(metadata.get("tokenizer.chat_template"))
        rss_bytes = max(0, process.memory_info().rss - before)  # the model's own share
        stat = file_path.stat()
        return ProbeResult(
            ok=True,
            path=path,
            architecture=architecture,
            has_chat_template=has_chat_template,
            rss_bytes=rss_bytes,
            size_bytes=stat.st_size,
            mtime=stat.st_mtime,
            size_label=metadata.get("general.size_label") or None,
            kv_bytes_per_token=kv_bytes_per_token(metadata),
        )
    finally:
        if hasattr(llm, "close"):
            llm.close()


def record_success(result: ProbeResult) -> None:
    """Persist a successful probe (path, size, mtime, measured cost) in settings.json (AD-7,
    AD-8, AD-20)."""
    if not result.ok:
        return
    probed = config.read_settings().get("probed_models", {})
    probed[result.path] = {
        "size_bytes": result.size_bytes,
        "mtime": result.mtime,
        "architecture": result.architecture,
        "has_chat_template": result.has_chat_template,
        "rss_bytes": result.rss_bytes,
        "size_label": result.size_label,
        "kv_bytes_per_token": result.kv_bytes_per_token,
        "probed_at": time.time(),
    }
    config.save_setting("probed_models", probed)
    failed = config.read_settings().get("failed_probes", {})
    if failed.pop(result.path, None) is not None:
        config.save_setting("failed_probes", failed)


def _llama_cpp_version() -> str | None:
    try:
        return metadata.version("llama-cpp-python")
    except metadata.PackageNotFoundError:
        return None


def _same_file(entry: dict[str, Any], path: str) -> bool:
    file_path = Path(path)
    if not file_path.is_file():
        return False
    stat = file_path.stat()
    return entry.get("size_bytes") == stat.st_size and entry.get("mtime") == stat.st_mtime


def record_failure(path: str, reason: str) -> None:
    """Remember a deterministic probe failure so the file is not reprobed at every launch.

    Skipped when the file is gone or llama-cpp-python is missing: neither says
    anything about the file itself. A llama-cpp-python upgrade invalidates the entry.
    """
    version = _llama_cpp_version()
    file_path = Path(path)
    if version is None or not file_path.is_file():
        return
    stat = file_path.stat()
    failed = config.read_settings().get("failed_probes", {})
    failed[path] = {
        "size_bytes": stat.st_size,
        "mtime": stat.st_mtime,
        "reason": reason,
        "llama_cpp_version": version,
    }
    config.save_setting("failed_probes", failed)


def failed_entry(path: str) -> dict[str, Any] | None:
    """The remembered failure for `path`, if still valid (same size, mtime, llama-cpp-python)."""
    entry = config.read_settings().get("failed_probes", {}).get(path)
    if not entry or entry.get("llama_cpp_version") != _llama_cpp_version():
        return None
    return entry if _same_file(entry, path) else None


def measured(path: str) -> bool:
    """AD-8: `path` has a valid probe entry that measured its cost (`rss_bytes`); an entry
    written before story 17 has none, and the file is probed again before its first switch."""
    entry = probed_entry(path)
    return entry is not None and entry.get("rss_bytes") is not None


def probed_entry(path: str) -> dict[str, Any] | None:
    """The probe cache entry for `path` (architecture...), if still valid (same size/mtime)."""
    entry = config.read_settings().get("probed_models", {}).get(path)
    return entry if entry and _same_file(entry, path) else None


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
