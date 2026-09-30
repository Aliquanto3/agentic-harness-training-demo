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
from pydantic import BaseModel, Field

from wavestack import config
from wavestack.models import servers

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
    # Story 18, a model an already-running server serves (`source = server`): its adapter,
    # its `ref` (`ollama/{name}`, `llama_server/{file}`), the provider's name, the memory
    # it takes (AD-8), and its GGUF: the blob `ollama_raw` reads its tokenizer from, or the
    # file llama-server loaded (its size only).
    engine: Literal["ollama", "llama_server"] | None = None
    ref: str | None = None
    provider: str | None = None
    served_bytes: int | None = None
    # Already in memory when listed (llama-server; an Ollama model in `/api/ps`): counted,
    # never refused by the budget, and never unloaded by WaveStack (AD-8).
    resident: bool | None = None
    gguf_path: str | None = None
    # Lot E (E1): llama-server's context (`/props`), and the French warning when it is much
    # larger than the window (memory reserved for nothing: « relancez-le avec -c … »).
    n_ctx: int | None = None
    warning_text: str | None = None
    # llama-server: its memory counts its context cache (the KV read in its GGUF); `False`
    # when the file could not be read here (the figure leaves the cache out).
    context_counted: bool | None = None
    # Story 25, the model table (`catalog`): Ollama's family (`details.family` of
    # `/api/tags`), a hint of the publisher; its `parameter_size` (« 0.6B »); the bytes of
    # the file, or those the server reports. llama-server's template, training context and
    # slot context (`/props`, `/v1/models`) give its capabilities as its adapter reads
    # them; never sent in `/api/diagnostic` (the template is long).
    publisher_hint: str | None = None
    params_label: str | None = None
    size_bytes: int | None = None
    server_template: str | None = Field(default=None, exclude=True)
    native_context: int | None = Field(default=None, exclude=True)
    server_context: int | None = Field(default=None, exclude=True)


def _glob_gguf(root: Path) -> list[Path]:
    if not root.is_dir():
        return []
    return sorted(root.rglob("*.gguf"))


# Story 15: `models/embedding/` holds embedding models, never offered as chat models; story
# 16: `models/reranker/` the reranking ones.
EMBEDDING_DIR = "embedding"
RERANKER_DIR = "reranker"


def _key(path: Path) -> str:
    """A path as the file system compares it (case-insensitive on Windows)."""
    return os.path.normcase(os.path.normpath(path))


def _rag_model_files(cfg: config.Config) -> set[str]:
    """The files `[rag.embedding]` and `[rag.reranker]` declare under `models_dir()`, as
    `_key` gives them: never offered as a model, wherever `load_path` puts them."""
    root = config.models_dir()
    files: set[str] = set()
    for model, _ in (cfg.rag_embedding, cfg.rag_reranker):
        if model is not None:
            files |= {_key(root / model.load_path), *(_key(root / f.path) for f in model.files)}
    return files


def _rag_model_dir(path: Path) -> bool:
    """Under `models/embedding/` or `models/reranker/`, whatever the case (Windows)."""
    first = path.relative_to(config.models_dir()).parts[0]
    return first.casefold() in (EMBEDDING_DIR, RERANKER_DIR)


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


def _is_gguf(path: str) -> bool:
    try:
        with open(path, "rb") as f:
            return f.read(4) == b"GGUF"
    except OSError:
        return False


def _server_candidates(
    cfg: config.Config, transport: httpx.BaseTransport | None = None
) -> list[ModelCandidate]:
    """One candidate per model an already-running server serves (AD-7, story 18). An Ollama
    model needs its GGUF blob, read by `_ollama_candidates`, for its tokenizer: without a
    readable one, it is `incompatible`, with the reason."""
    served = servers.list_served(cfg, transport)
    blobs: dict[str, ModelCandidate] = {}
    if any(s.engine == "ollama" for s in served):
        for blob in _ollama_candidates():
            if blob.name and (blob.name not in blobs or blob.status == "found"):
                blobs[blob.name] = blob
    candidates: list[ModelCandidate] = []
    for model in served:
        candidate = ModelCandidate(
            source="server",
            status="server",
            server_url=model.server_url,
            name=model.name,
            engine=model.engine,  # type: ignore[arg-type]
            ref=model.ref,
            provider=model.provider,
            publisher_hint=model.family,
            params_label=model.parameter_size,
            size_bytes=model.size,
        )
        if model.engine == "ollama":
            blob = blobs.get(model.name)
            if blob is None or not blob.path:
                candidate.status = "incompatible"
                candidate.reason = (
                    f"Fichier GGUF du modèle introuvable dans le dossier d'Ollama "
                    f"({_ollama_root()}) : WaveStack ne peut pas lire son tokenizer."
                )
            elif blob.status != "found":
                candidate.status, candidate.reason = "incompatible", blob.reason
            elif not _is_gguf(blob.path):
                candidate.status = "incompatible"
                candidate.reason = "Le fichier du modèle n'est pas un GGUF lisible."
            else:
                candidate.gguf_path = blob.path
        else:  # llama-server: the file it loaded, for its size and KV cache (AD-8)
            candidate.gguf_path = model.model_path
            candidate.n_ctx = model.n_ctx
            candidate.server_template = model.chat_template
            candidate.native_context = model.n_ctx_train
            candidate.server_context = model.slot_ctx
            candidate.warning_text = servers.context_warning_fr(
                model.n_ctx, cfg.context_window, model.slot_ctx
            )
            candidate.context_counted = servers.served_kv(model, model.model_path) is not None
        # Story 24: an Ollama model not loaded yet counts its KV at the window, as `_cost`.
        candidate.served_bytes = servers.served_bytes(
            model, candidate.gguf_path, cfg.context_window
        )
        candidate.resident = model.resident
        candidates.append(candidate)
    return candidates


def discover(explicit_path: str | Path | None = None) -> list[ModelCandidate]:
    """List every model candidate, in AD-7 order. Never raises on a missing location."""
    candidates: list[ModelCandidate] = []
    cfg = config.load_config()
    rag_files = _rag_model_files(cfg)  # stories 15, 16: the RAG's models are no chat model
    candidates += [
        ModelCandidate(source="models_dir", status="found", path=str(p))
        for p in _glob_gguf(config.models_dir())
        if _key(p) not in rag_files and not _rag_model_dir(p)
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
    candidates += _server_candidates(cfg)

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
        if candidate.path and candidate.source != "server" and candidate.size_bytes is None:
            candidate.size_bytes = _file_size(candidate.path)
    return candidates


def _file_size(path: str) -> int | None:
    try:
        return Path(path).stat().st_size
    except OSError:
        return None
