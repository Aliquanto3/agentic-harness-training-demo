"""Model candidate discovery: the single function that lists GGUF candidates (AD-7).

Never launches Ollama or LM Studio; only reads their on-disk state, or probes
an already-running server at a loopback address.
"""

from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Literal

import httpx
from pydantic import BaseModel

from wavestack import config
from wavestack.net.factory import create_client
from wavestack.trace.scope import scoped

CandidateSource = Literal["explicit", "models_dir", "hf_cache", "lm_studio", "ollama", "server"]
CandidateStatus = Literal["found", "incompatible", "server"]


class ModelCandidate(BaseModel):
    source: CandidateSource
    status: CandidateStatus
    path: str | None = None
    server_url: str | None = None
    reason: str | None = None
    name: str | None = None  # readable: `model:tag` for Ollama, the file name otherwise
    architecture: str | None = None  # from the probe cache, once probed
    size_label: str | None = None  # `general.size_label` (« 2B »), from the probe cache


def _glob_gguf(root: Path) -> list[Path]:
    if not root.is_dir():
        return []
    return sorted(root.rglob("*.gguf"))


def _hf_cache_dir() -> Path:
    hub_cache = os.environ.get("HF_HUB_CACHE")
    if hub_cache:
        return Path(hub_cache)
    hf_home = os.environ.get("HF_HOME")
    if hf_home:
        return Path(hf_home) / "hub"
    return Path.home() / ".cache" / "huggingface" / "hub"


def _lm_studio_dirs() -> list[Path]:
    return [Path.home() / ".lmstudio" / "models", Path.home() / ".cache" / "lm-studio" / "models"]


def _ollama_root() -> Path:
    override = os.environ.get("OLLAMA_MODELS")
    return Path(override) if override else Path.home() / ".ollama" / "models"


def _ollama_name(manifest_path: Path, manifests_dir: Path) -> str:
    """`registry.ollama.ai/library/qwen3.5/9b` -> `qwen3.5:9b`, as `ollama list` shows it."""
    parts = list(manifest_path.relative_to(manifests_dir).parts)
    if parts[:1] == ["registry.ollama.ai"]:
        parts = parts[1:]
        if parts[:1] == ["library"]:
            parts = parts[1:]
    return "/".join(parts[:-1]) + ":" + parts[-1] if len(parts) > 1 else parts[-1]


def _ollama_candidates() -> list[ModelCandidate]:
    root = _ollama_root()
    manifests_dir = root / "manifests"
    blobs_dir = root / "blobs"
    candidates: list[ModelCandidate] = []
    if not manifests_dir.is_dir():
        return candidates
    for manifest_path in manifests_dir.rglob("*"):
        if not manifest_path.is_file():
            continue
        try:
            manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            continue
        name = _ollama_name(manifest_path, manifests_dir)
        for layer in manifest.get("layers", []):
            media_type = layer.get("mediaType", "")
            digest = layer.get("digest", "")
            blob_path = blobs_dir / digest.replace(":", "-")
            if media_type == "application/vnd.ollama.image.model":
                if blob_path.exists():
                    candidates.append(
                        ModelCandidate(
                            source="ollama", status="found", path=str(blob_path), name=name
                        )
                    )
            elif media_type == "application/vnd.ollama.image.tensor":
                candidates.append(
                    ModelCandidate(
                        source="ollama",
                        status="incompatible",
                        path=str(blob_path),
                        name=name,
                        reason="Format de tenseur Ollama, non chargeable en processus.",
                    )
                )
    return candidates


def _server_candidates(cfg: config.Config) -> list[ModelCandidate]:
    ports: dict[str, int] = cfg.get(
        "net", "loopback_ports", default={"ollama": 11434, "llama_server": 8080}
    )
    probe_paths = {"ollama": "/api/tags", "llama_server": "/health"}
    candidates: list[ModelCandidate] = []
    with scoped(origin="diagnostic"):
        client = create_client(timeout=1.0)
        try:
            for name, port in ports.items():
                url = f"http://127.0.0.1:{port}"
                try:
                    response = client.get(url + probe_paths.get(name, "/"))
                except httpx.HTTPError:
                    continue
                if response.status_code < 500:
                    candidates.append(
                        ModelCandidate(source="server", status="server", server_url=url)
                    )
        finally:
            client.close()
    return candidates


def discover(explicit_path: str | Path | None = None) -> list[ModelCandidate]:
    """List every model candidate, in AD-7 order. Never raises on a missing location."""
    candidates: list[ModelCandidate] = []
    candidates += [
        ModelCandidate(source="models_dir", status="found", path=str(p))
        for p in _glob_gguf(config.models_dir())
    ]
    candidates += [
        ModelCandidate(source="hf_cache", status="found", path=str(p))
        for p in _glob_gguf(_hf_cache_dir())
    ]

    for lmstudio_dir in _lm_studio_dirs():
        found = _glob_gguf(lmstudio_dir)
        if found:
            candidates += [
                ModelCandidate(source="lm_studio", status="found", path=str(p)) for p in found
            ]
            break

    candidates += _ollama_candidates()
    candidates += _server_candidates(config.load_config())

    # The explicit path comes first (AD-7), unless it is already listed (e.g. an Ollama blob).
    if explicit_path and str(Path(explicit_path)) not in {c.path for c in candidates}:
        path = Path(explicit_path)
        if path.is_file():
            explicit = ModelCandidate(source="explicit", status="found", path=str(path))
        else:
            explicit = ModelCandidate(
                source="explicit",
                status="incompatible",
                path=str(path),
                reason="Fichier introuvable.",
            )
        candidates.insert(0, explicit)

    for candidate in candidates:
        if candidate.path and candidate.name is None:
            candidate.name = Path(candidate.path).name
    return candidates
