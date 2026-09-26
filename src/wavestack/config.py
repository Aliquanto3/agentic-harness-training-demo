"""Resolves WaveStack's runtime paths and merges configuration (AD-20).

Only this module resolves paths. Defaults live in ``wavestack.toml`` (repo),
overrides in ``settings.json`` (data dir), written by the session only.
"""

from __future__ import annotations

import ipaddress
import json
import math
import os
import sys
import tomllib
from dataclasses import dataclass, field
from functools import cached_property
from pathlib import Path, PurePosixPath, PureWindowsPath
from typing import Any, Literal
from urllib.parse import urlsplit

# ponytail: pydantic is imported before the network guard (cli imports config first); it
# opens no connection at import, so the guard still precedes any network access.
from pydantic import (
    BaseModel,
    ConfigDict,
    Field,
    SecretStr,
    ValidationError,
    field_validator,
    model_validator,
)


def data_dir() -> Path:
    """Return the single directory holding all runtime data (AD-20).

    Windows: %LOCALAPPDATA%\\WaveStack. Other platforms: ~/.local/share/wavestack.
    """
    override = os.environ.get("WAVESTACK_DATA_DIR")
    if override:
        return Path(override)
    if sys.platform == "win32":
        base = os.environ.get("LOCALAPPDATA") or str(Path.home() / "AppData" / "Local")
        return Path(base) / "WaveStack"
    return Path.home() / ".local" / "share" / "wavestack"


def repo_root() -> Path:
    """Return the repository root (where wavestack.toml lives)."""
    return Path(__file__).resolve().parents[2]


def _deep_merge(base: dict[str, Any], override: dict[str, Any]) -> dict[str, Any]:
    merged = dict(base)
    for key, value in override.items():
        if isinstance(value, dict) and isinstance(merged.get(key), dict):
            merged[key] = _deep_merge(merged[key], value)
        else:
            merged[key] = value
    return merged


class _Strict(BaseModel):
    model_config = ConfigDict(extra="forbid")


class AuthHeader(_Strict):
    name: str = "Authorization"
    scheme: str = "Bearer"


class CloudReasoning(_Strict):
    """What the reasoning brick adds to the body (AD-6). `resend`: the reasoning received goes
    back to the provider in the form of `format` (AD-4)."""

    format: Literal["field", "content_blocks", "think_tags"]
    on: dict[str, Any] = {}
    off: dict[str, Any] = {}
    always: bool = False
    resend: bool = False


def _is_loopback(host: str) -> bool:
    if host == "localhost":
        return True
    try:
        return ipaddress.ip_address(host).is_loopback
    except ValueError:
        return False


OUTPUT_RESERVE = 512  # AD-9: the output reserve of a model that does not reason
MAX_RESERVE = 1536  # AD-9: the largest output reserve; `tpm // 2` must exceed it


def output_reserve(reasoning: bool) -> int:
    """AD-9, the single rule of the output reserve: 1 536 while the model reasons, else 512."""
    return MAX_RESERVE if reasoning else OUTPUT_RESERVE


class CloudModel(_Strict):
    """One `[[cloud.models]]` entry (AD-20): an OpenAI-compatible model. No key field:
    `key_env` names an environment variable, never holds a value. `min_interval_s`: the
    least time between two sends to this entry (AD-16)."""

    id: str = Field(pattern=r"^[a-z0-9_]+$")
    provider: str = Field(min_length=1)
    base_url: str
    model: str = Field(min_length=1)
    auth_header: AuthHeader = AuthHeader()
    max_tokens_field: Literal["max_tokens", "max_completion_tokens"] = "max_tokens"
    stream_usage: bool = False
    tools: bool = False
    reasoning: CloudReasoning | None = None
    context: int = Field(gt=0)
    tpm: int | None = Field(default=None, gt=0)
    window: int | None = Field(default=None, gt=0)
    hosting_fr: str = Field(min_length=1)
    training: Literal["yes", "no", "opt_out"]
    trial: bool = False
    notes_fr: str = ""
    enabled: bool = True
    key_env: str | None = Field(default=None, pattern=r"^[A-Z_][A-Z0-9_]*$")
    min_interval_s: float | None = Field(default=None, gt=0, le=60)

    @field_validator("base_url")
    @classmethod
    def _https_without_query(cls, value: str) -> str:
        parts = urlsplit(value)
        host = parts.hostname or ""
        if parts.scheme != "https" and not (parts.scheme == "http" and _is_loopback(host)):
            raise ValueError("base_url must be https (http for the loopback only)")
        if not host or parts.query or parts.fragment:
            raise ValueError("base_url needs a host and no query nor fragment")
        return value.rstrip("/")

    @property
    def host(self) -> str:
        return urlsplit(self.base_url).hostname or ""

    @property
    def always_reasons(self) -> bool:
        return self.reasoning is not None and self.reasoning.always

    def reserve_for(self, reasoning: bool) -> int:
        """AD-9: the reasoning reserve while it reasons (brick on, or `always`), else 512."""
        return output_reserve(reasoning or self.always_reasons)

    @property
    def reserve(self) -> int:
        """The reserve with the reasoning brick off (« Tester », the window check)."""
        return self.reserve_for(False)

    def reasoning_params(self, reasoning: bool) -> dict[str, Any]:
        """AD-6: `on` while the model reasons (brick on, or `always`), else `off`."""
        if self.reasoning is None:
            return {}
        on = reasoning or self.reasoning.always
        return dict(self.reasoning.on if on else self.reasoning.off)


class EmbeddingFile(_Strict):
    """A file of the embedding model (story 15): where to download it, where it goes under
    `models_dir()`, its size in bytes and, when declared, its sha256 (empty: not checked)."""

    url: str
    path: str = Field(min_length=1)
    size: int = Field(gt=0)
    sha256: str = Field(default="", pattern=r"^([0-9a-fA-F]{64})?$")

    @field_validator("url")
    @classmethod
    def _https(cls, value: str) -> str:
        parts = urlsplit(value)
        host = parts.hostname or ""
        if parts.scheme != "https" and not (parts.scheme == "http" and _is_loopback(host)):
            raise ValueError("url must be https (http for the loopback only)")
        if not host:
            raise ValueError("url needs a host")
        return value

    @field_validator("path")
    @classmethod
    def _inside_models_dir(cls, value: str) -> str:
        return _relative_path(value)


def _relative_path(value: str) -> str:
    """A path relative to `models_dir()` that stays inside it, read as a Windows and as a
    POSIX path alike (« \\x », « C:x », « /x » and « .. » refused everywhere)."""
    for path in (PureWindowsPath(value), PurePosixPath(value)):
        if path.is_absolute() or path.drive or path.root or ".." in path.parts:
            raise ValueError("path must be relative to the models folder, without '..'")
    return value


class EmbeddingModel(_Strict):
    """`[rag.embedding]` (story 15): the single place that names the embedding model, with
    the values of story 12's verdict. Only the `llama_cpp` backend has an adapter."""

    id: str = Field(min_length=1)
    backend: Literal["llama_cpp"]
    label_fr: str = Field(min_length=1)
    license: str = Field(min_length=1)
    dims: int = Field(gt=0)
    max_tokens: int = Field(gt=0)
    query_prefix: str = ""
    passage_prefix: str = ""
    load_path: str = Field(min_length=1)
    measured_rss_mb: int | None = Field(default=None, gt=0)
    files: list[EmbeddingFile] = Field(min_length=1)

    @field_validator("load_path")
    @classmethod
    def _inside_models_dir(cls, value: str) -> str:
        return _relative_path(value)

    @model_validator(mode="after")
    def _load_path_is_declared(self) -> EmbeddingModel:
        """The file loaded is one of `files`: its size (and sha256) identify the model."""
        if PurePosixPath(self.load_path) not in {PurePosixPath(f.path) for f in self.files}:
            raise ValueError("load_path must be one of files[].path")
        return self

    @property
    def load_file(self) -> EmbeddingFile:
        return next(f for f in self.files if PurePosixPath(f.path) == PurePosixPath(self.load_path))


class RerankerModel(_Strict):
    """`[rag.reranker]` (story 16): the single place that names the reranking model, with
    the values of story 12's verdict. Only the `llama_cpp` backend has an adapter; its files
    are declared, downloaded and identified as the embedding model's are."""

    id: str = Field(min_length=1)
    backend: Literal["llama_cpp"]
    label_fr: str = Field(min_length=1)
    license: str = Field(min_length=1)
    max_tokens: int = Field(gt=8)  # one query-excerpt pair, in tokens
    load_path: str = Field(min_length=1)
    measured_rss_mb: int | None = Field(default=None, gt=0)
    files: list[EmbeddingFile] = Field(min_length=1)

    @field_validator("load_path")
    @classmethod
    def _inside_models_dir(cls, value: str) -> str:
        return _relative_path(value)

    @model_validator(mode="after")
    def _load_path_is_declared(self) -> RerankerModel:
        if PurePosixPath(self.load_path) not in {PurePosixPath(f.path) for f in self.files}:
            raise ValueError("load_path must be one of files[].path")
        return self

    @property
    def load_file(self) -> EmbeddingFile:
        return next(f for f in self.files if PurePosixPath(f.path) == PurePosixPath(self.load_path))


def _merge_cloud_models(base: Any, override: Any) -> list[Any]:
    """AD-20: `[[cloud.models]]` entries merge by `id`, field by field, on the raw dicts."""
    merged: dict[Any, Any] = {}
    entries = [
        *(base if isinstance(base, list) else []),
        *(override if isinstance(override, list) else []),
    ]
    for n, entry in enumerate(entries):
        key = entry.get("id", f"#{n}") if isinstance(entry, dict) else f"#{n}"
        previous = merged.get(key)
        both = isinstance(previous, dict) and isinstance(entry, dict)
        merged[key] = _deep_merge(previous, entry) if both else entry
    return list(merged.values())


@dataclass(frozen=True)
class Config:
    """Merged configuration: wavestack.toml defaults overridden by settings.json."""

    values: dict[str, Any] = field(default_factory=dict)

    def get(self, *path: str, default: Any = None) -> Any:
        node: Any = self.values
        for key in path:
            if not isinstance(node, dict) or key not in node:
                return default
            node = node[key]
        return node

    @property
    def port(self) -> int:
        try:
            return int(self.get("server", "port", default=8420))
        except (TypeError, ValueError):
            return 8420

    @property
    def allowed_hosts(self) -> list[str]:
        """AD-15: the configured hosts, plus the host of every enabled cloud model."""
        hosts = list(self.get("net", "allowed_hosts", default=[]))
        return hosts + [m.host for m in self.cloud_models[0] if m.host not in hosts]

    @cached_property
    def cloud_models(self) -> tuple[list[CloudModel], list[str]]:
        """The enabled, valid cloud models, and why each invalid entry was left out (French)."""
        valid: list[CloudModel] = []
        errors: list[str] = []
        raw = self.get("cloud", "models", default=[])
        for entry in raw if isinstance(raw, list) else []:
            try:
                model = CloudModel.model_validate(entry)
            except ValidationError as exc:
                name = entry.get("id", "?") if isinstance(entry, dict) else "?"
                fields = ", ".join(
                    ".".join(str(p) for p in e["loc"]) or "entrée" for e in exc.errors()
                )
                errors.append(
                    f"Modèle cloud « {name} » écarté : déclaration invalide ({fields}). "
                    "Corrigez wavestack.toml ou settings.json, puis relancez WaveStack."
                )
                continue
            if model.enabled and all(m.id != model.id for m in valid):
                valid.append(model)
        return valid, errors

    def cloud_model(self, model_id: str) -> CloudModel | None:
        return next((m for m in self.cloud_models[0] if m.id == model_id), None)

    def _float(self, *path: str, default: float, low: float, high: float) -> float:
        try:
            return min(high, max(low, float(self.get(*path, default=default))))
        except (TypeError, ValueError):
            return default

    @property
    def chars_per_token(self) -> float:
        return self._float("cloud", "chars_per_token", default=4.0, low=0.5, high=100.0)

    @property
    def estimate_ratio(self) -> float:
        return self._float("cloud", "estimate_ratio", default=1.0, low=0.8, high=1.5)

    @property
    def cloud_connect_timeout_s(self) -> float:
        return self._seconds("cloud", "connect_timeout_s", default=10.0)

    @property
    def cloud_read_timeout_s(self) -> float:
        return self._seconds("cloud", "read_timeout_s", default=60.0)

    @property
    def cloud_markers(self) -> list[str]:
        """AD-4, chat mode: template markers neutralized in every harness text."""
        return [str(m) for m in self.get("cloud", "neutralize_markers", default=[])]

    @property
    def connectivity_probe_host(self) -> str:
        return str(self.get("net", "connectivity_probe_host", default="huggingface.co"))

    @property
    def context_window(self) -> int:
        try:
            return int(self.get("context", "window", default=4096))
        except (TypeError, ValueError):
            return 4096

    @property
    def memory_budget_bytes(self) -> int:
        """AD-8: WaveStack's memory budget, `[memory] budget_mb`."""
        return max(1, self._int("memory", "budget_mb", default=4096)) * 1024 * 1024

    @property
    def load_margin_bytes(self) -> int:
        """AD-8: the margin added to a local model's estimated cost, `[memory] load_margin_mb`."""
        return max(0, self._int("memory", "load_margin_mb", default=256)) * 1024 * 1024

    @cached_property
    def rag_embedding(self) -> tuple[EmbeddingModel | None, str | None]:
        """Story 15: the `[rag.embedding]` model, or why its declaration is invalid (French)."""
        raw = self.get("rag", "embedding")
        if raw is None:
            return None, (
                "La section [rag.embedding] de wavestack.toml est absente : elle nomme le "
                "modèle d'embedding. Rétablissez-la, puis relancez WaveStack."
            )
        try:
            return EmbeddingModel.model_validate(raw), None
        except ValidationError as exc:
            fields = ", ".join(
                ".".join(str(p) for p in e["loc"]) or "section" for e in exc.errors()
            )
            return None, (
                f"La section [rag.embedding] est invalide ({fields}). Corrigez wavestack.toml "
                "ou settings.json, puis relancez WaveStack."
            )

    @property
    def rag_top_k(self) -> int:
        """Story 15: the excerpts placed in the context at each turn."""
        return max(1, self._int("rag", "top_k", default=3))

    @cached_property
    def rag_reranker(self) -> tuple[RerankerModel | None, str | None]:
        """Story 16: the `[rag.reranker]` model, or why its declaration is absent or invalid
        (French)."""
        raw = self.get("rag", "reranker")
        if raw is None:
            return None, (
                "Indisponible : la section [rag.reranker] de wavestack.toml est absente (elle "
                "nomme le modèle de reranking). Rétablissez-la, puis relancez WaveStack."
            )
        try:
            return RerankerModel.model_validate(raw), None
        except ValidationError as exc:
            fields = ", ".join(
                ".".join(str(p) for p in e["loc"]) or "section" for e in exc.errors()
            )
            return None, (
                f"Indisponible : la section [rag.reranker] est invalide ({fields}). Corrigez "
                "wavestack.toml ou settings.json, puis relancez WaveStack."
            )

    @property
    def rag_rerank_candidates(self) -> int:
        """Story 16: the candidates the embedding retains for the reranker, from `top_k` to
        20."""
        return max(self.rag_top_k, min(20, self._int("rag", "rerank_candidates", default=8)))

    @property
    def rag_chunk_max_chars(self) -> int:
        """Story 15: the largest excerpt the chunking makes, in characters."""
        return max(50, self._int("rag", "chunk_max_chars", default=700))

    @property
    def compression_min_chars(self) -> int:
        """Story 20: a shorter tool result or RAG excerpt is not given to the compressor."""
        return max(0, self._int("compression", "min_chars", default=300))

    @property
    def compression_cost_bytes(self) -> int:
        """Story 20 (AD-8): what loading Headroom is expected to add (story 12: 130 MB)."""
        return max(0, self._int("compression", "cost_mb", default=130)) * 1024 * 1024

    def rag_index_path(self) -> Path:
        """Story 15: the sqlite-vec index; a relative path is from the repository root."""
        path = Path(str(self.get("rag", "index_path", default="data/rag_index.sqlite")))
        return path if path.is_absolute() else repo_root() / path

    @property
    def near_limit_ratio(self) -> float:
        try:
            return float(self.get("context", "near_limit_ratio", default=0.8))
        except (TypeError, ValueError):
            return 0.8

    def _int(self, *path: str, default: int) -> int:
        try:
            return int(self.get(*path, default=default))
        except (TypeError, ValueError):
            return default

    @property
    def tool_max_calls(self) -> int:
        """AD-10: model calls per turn in the main context."""
        return max(1, self._int("tools", "max_calls", default=6))

    @property
    def tool_max_retries(self) -> int:
        """AD-10: new attempts per turn after a refused call, counted in `tool_max_calls`."""
        return max(0, self._int("tools", "max_retries", default=2))

    @property
    def subagent_tools(self) -> list[str]:
        """Story 19 (AD-11): the tools the sub-agent may use, when enabled in the tools brick."""
        tools = self.get("subagent", "tools", default=["read_file", "fetch_page"])
        return [str(t) for t in tools] if isinstance(tools, list) else []

    @property
    def subagent_max_calls(self) -> int:
        """AD-10: the sub-agent's model calls per delegation, on a counter of its own."""
        return max(1, self._int("subagent", "max_calls", default=4))

    @property
    def fetch_page_hosts(self) -> list[str]:
        """The only hosts `fetch_page` may request, over https."""
        default = ["fr.wikipedia.org", "calendrier.api.gouv.fr"]
        return list(self.get("tools", "fetch_page_hosts", default=default))

    @property
    def fetch_page_max_chars(self) -> int:
        return max(1, self._int("tools", "fetch_page_max_chars", default=4000))

    @property
    def mcp_urls(self) -> dict[str, str]:
        """Public MCP servers (story 6): server id -> Streamable HTTP endpoint."""
        default = {
            "datagouv": "https://mcp.data.gouv.fr/mcp",
            "mslearn": "https://learn.microsoft.com/api/mcp",
        }
        return {**default, **dict(self.get("mcp", "urls", default={}))}

    def _seconds(self, *path: str, default: float) -> float:
        try:
            return max(0.1, float(self.get(*path, default=default)))
        except (TypeError, ValueError):
            return default

    @property
    def mcp_connect_timeout_s(self) -> float:
        return self._seconds("mcp", "connect_timeout_s", default=15.0)

    @property
    def mcp_call_timeout_s(self) -> float:
        return self._seconds("mcp", "call_timeout_s", default=30.0)

    @property
    def model_server_connect_timeout_s(self) -> float:
        """Story 18: connecting to an already-running local server, `[model_servers]`."""
        return self._seconds("model_servers", "connect_timeout_s", default=2.0)

    @property
    def model_server_read_timeout_s(self) -> float:
        """Story 18: reading a local server's answer or stream, `[model_servers]`."""
        return self._seconds("model_servers", "read_timeout_s", default=300.0)

    @property
    def loopback_ports(self) -> dict[str, int]:
        """AD-7: the already-running local servers to probe, `[net.loopback_ports]`."""
        value = self.get("net", "loopback_ports", default=None)
        if not isinstance(value, dict):
            return {"ollama": 11434, "llama_server": 8080}
        ports = {}
        for name, port in value.items():
            try:
                number = int(port)
            except (TypeError, ValueError):
                continue
            if 1 <= number <= 65535:  # any other value would break the diagnostic's URLs
                ports[str(name)] = number
        return ports

    @property
    def selected_model(self) -> dict[str, str] | None:
        """AD-20: `{kind: file|server|cloud, ref}`; a plain string (story 1b) is a file."""
        value = self.get("selected_model")
        if isinstance(value, dict) and value.get("kind") in ("file", "server", "cloud"):
            return {"kind": str(value["kind"]), "ref": str(value.get("ref") or "")}
        return {"kind": "file", "ref": str(value)} if isinstance(value, str) and value else None


def cloud_window(entry: CloudModel, configured: int) -> tuple[int, str]:
    """AD-9: min(`window` or the configured window, `context`, `tpm // 2`), and its source."""
    options = [
        (entry.window, "override") if entry.window else (configured, "configured"),
        (entry.context, "native"),
    ]
    if entry.tpm:
        options.append((entry.tpm // 2, "tpm"))
    return min(options, key=lambda option: option[0])


def cloud_unavailable_fr(entry: CloudModel) -> str | None:
    """AD-9: why an entry cannot serve a turn whatever its key, `None` when it can."""
    if entry.tpm and entry.tpm // 2 <= MAX_RESERVE:
        return (
            f"Indisponible : le quota de {entry.tpm} tokens par minute ne laisse pas de place "
            f"au contexte une fois la réponse réservée ({MAX_RESERVE} tokens)."
        )
    return None


def estimate_tokens(text: str, chars_per_token: float) -> int:
    """AD-4, chat mode: tokens estimated from the characters of the original text."""
    return math.ceil(len(text) / chars_per_token) if text else 0


def load_config() -> Config:
    """Load wavestack.toml, then overlay settings.json from the data dir."""
    defaults: dict[str, Any] = {}
    toml_path = repo_root() / "wavestack.toml"
    if toml_path.exists():
        try:
            defaults = tomllib.loads(toml_path.read_text(encoding="utf-8"))
        except tomllib.TOMLDecodeError:
            defaults = {}

    settings = read_settings()
    values = _deep_merge(defaults, settings)
    models = _merge_cloud_models(_cloud_list(defaults), _cloud_list(settings))
    if models:  # AD-20: merged by `id`, where `_deep_merge` replaces lists
        values["cloud"] = {**(values.get("cloud") or {}), "models": models}
    return Config(values=values)


def _cloud_list(values: dict[str, Any]) -> Any:
    cloud = values.get("cloud")
    return cloud.get("models") if isinstance(cloud, dict) else None


def read_settings() -> dict[str, Any]:
    """The raw settings.json overrides; empty when absent or unreadable."""
    path = settings_path()
    if not path.exists():
        return {}
    try:
        settings = json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError:
        return {}
    return settings if isinstance(settings, dict) else {}


def save_setting(key: str, value: Any) -> None:
    """Read-modify-write one top-level key of settings.json. Raises OSError on write failure."""
    settings = read_settings()
    settings[key] = value
    path = settings_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(settings, ensure_ascii=False, indent=2), encoding="utf-8")


def content_dir() -> Path:
    """French pedagogical content shipped with the repo (AD-19)."""
    return repo_root() / "content"


def models_dir() -> Path:
    return data_dir() / "models"


def settings_path() -> Path:
    return data_dir() / "settings.json"


def api_keys_path() -> Path:
    """AD-20: `{id: {host, key}}`; read by `cloud_key` only, written by `write_api_key` only."""
    return data_dir() / "api_keys.json"


def _api_keys() -> dict[str, Any]:
    try:
        keys = json.loads(api_keys_path().read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return {}
    return keys if isinstance(keys, dict) else {}


def _file_key(entry: CloudModel) -> str | None:
    saved = _api_keys().get(entry.id)
    if not isinstance(saved, dict) or saved.get("host") != entry.host or not saved.get("key"):
        return None
    return str(saved["key"])


def _env_key(entry: CloudModel) -> str | None:
    if not entry.key_env:
        return None
    return os.environ.get(entry.key_env, "").strip() or None


def cloud_key(entry: CloudModel) -> SecretStr | None:
    """The only reader of a key (AD-20): `api_keys.json` for this host first, else the
    variable `key_env` names (blank counts as absent); `None` when neither gives one."""
    key = _file_key(entry) or _env_key(entry)
    return SecretStr(key) if key else None


def cloud_key_source(entry: CloudModel) -> Literal["file", "env"] | None:
    """Where `cloud_key` finds the key, for display only: never the key itself."""
    if _file_key(entry):
        return "file"
    return "env" if _env_key(entry) else None


def api_key_host_changed(entry: CloudModel) -> bool:
    """A key was saved for this entry, but for another host: it must be typed again."""
    saved = _api_keys().get(entry.id)
    return isinstance(saved, dict) and bool(saved.get("key")) and saved.get("host") != entry.host


def write_api_key(model_id: str, host: str, key: SecretStr) -> None:
    """The only writer of `api_keys.json`: an atomic replace. Raises OSError on failure."""
    keys = _api_keys()
    keys[model_id] = {"host": host, "key": key.get_secret_value()}
    path = api_keys_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(".tmp")
    tmp.write_text(json.dumps(keys, ensure_ascii=False, indent=2), encoding="utf-8")
    os.replace(tmp, path)


def memory_path() -> Path:
    """The global memory (AD-20), read and written by the session only (AD-23)."""
    return data_dir() / "memory.json"


def audit_path() -> Path:
    """The audit log H2 feeds, written by the session only (AD-20, AD-23)."""
    return data_dir() / "audit.log"
