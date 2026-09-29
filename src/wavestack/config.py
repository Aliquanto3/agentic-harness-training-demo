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
from collections.abc import Callable
from dataclasses import dataclass, field
from datetime import date
from functools import cached_property
from pathlib import Path, PurePosixPath, PureWindowsPath
from typing import Annotated, Any, Literal
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


# Story 23: the only request headers `net` traces in clear, lower-cased (AD-15). A closed
# allow-list, not a deny-list: any other header's value is masked before the journal.
PUBLIC_HEADERS = frozenset(
    {
        "host",
        "accept",
        "accept-encoding",
        "accept-language",
        "cache-control",
        "connection",
        "content-length",
        "content-type",
        "mcp-protocol-version",
        "user-agent",
    }
)


class AuthHeader(_Strict):
    name: str = "Authorization"
    scheme: str = "Bearer"

    @field_validator("name")
    @classmethod
    def _not_a_public_header(cls, value: str) -> str:
        """Story 23: a key sent under a header traced in clear would reach the journal."""
        if value.strip().lower() in PUBLIC_HEADERS:
            raise ValueError(
                f"L'en-tête « {value} » est tracé en clair dans le journal : "
                "la clé ne peut pas y être envoyée."
            )
        return value


class CloudReasoning(_Strict):
    """What the reasoning brick adds to the body (AD-6). `resend`: the reasoning received goes
    back to the provider in the form of `format` (AD-4). `tags`: the opening and closing tags
    `think_tags` reads in `content` (Gemini writes `<thought>`)."""

    format: Literal["field", "content_blocks", "think_tags"]
    on: dict[str, Any] = {}
    off: dict[str, Any] = {}
    always: bool = False
    resend: bool = False
    tags: tuple[Annotated[str, Field(min_length=1)], Annotated[str, Field(min_length=1)]] = (
        "<think>",
        "</think>",
    )


class CloudPricing(_Strict):
    """FinOps: a cloud model's list prices, in US dollars per million tokens, and the day they
    were read on the provider's page (`checked`, ISO). The cost of a call is an estimate."""

    input_usd_per_mtok: float = Field(ge=0, allow_inf_nan=False)
    output_usd_per_mtok: float = Field(ge=0, allow_inf_nan=False)
    checked: date


def _is_loopback(host: str) -> bool:
    if host == "localhost":
        return True
    try:
        return ipaddress.ip_address(host).is_loopback
    except ValueError:
        return False


OUTPUT_RESERVE = 512  # AD-9: the output reserve of a model that does not reason
MAX_RESERVE = 1536  # AD-9: the largest output reserve; `tpm // 2` must exceed it
# Story 26 (AD-9): the windows the interface offers, the one list read by the intention and
# the panel; `[context] window` defaults to `DEFAULT_WINDOW` (a value set by hand outside the
# list is still read, never offered).
WINDOW_CHOICES = (4096, 8192, 16384)
DEFAULT_WINDOW = 4096
DEFAULT_TOOL_RESULT_MAX_TOKENS = 1200  # lot B (N3): `[tools] result_max_tokens`
DEFAULT_REASONING_BUDGET = 768  # lot C (N4), lot J: `[reasoning] budget_tokens`
MIN_REASONING_BUDGET = 128  # lot C: the floor, and what is always left to the answer
# Lot D: `[net] contact`, the way to reach the demo's maintainers, sent in the User-Agent.
DEFAULT_NET_CONTACT = "https://github.com/Aliquanto3/agentic-harness-training-demo"
DEFAULT_EUR_PER_USD = 0.86  # FinOps: `[finops] eur_per_usd`


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
    # Story 29: the sampling settings the « LLM nu » screen may send; none by default (the
    # provider's own). Top-k and min-p are never sent to a provider.
    sampling: list[Literal["temperature", "top_p"]] = []
    # What a call the harness makes itself (a forced action) carries besides `id`, `type` and
    # `function`, in chat mode: Gemini 3.x refuses a replayed call without its thought
    # signature, and a made-up call has none. Empty by default: nothing added.
    tool_call_extra: dict[str, Any] = {}
    # FinOps: the declared prices; without them, no cost is computed nor shown for this model.
    pricing: CloudPricing | None = None

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
        """AD-6: `on` while the model reasons (brick on, or `always`), else `off`. A field set
        to `null` is left out: `settings.json` merges into `wavestack.toml` field by field, and
        `null` is how it removes a field the preset declares."""
        if self.reasoning is None:
            return {}
        on = reasoning or self.reasoning.always
        params = self.reasoning.on if on else self.reasoning.off
        return {key: value for key, value in params.items() if value is not None}


class ModelFile(_Strict):
    """A file of a local model the harness downloads (stories 15 and 16: embedding,
    reranker): where to download it, where it goes under `models_dir()`, its size in bytes
    and, when declared, its sha256 (empty: not checked)."""

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


class LocalModelSpec(_Strict):
    """What `[rag.embedding]` and `[rag.reranker]` share: the model's name, licence and
    files (downloaded and identified by their size and sha256), the one loaded, and the RSS
    story 12 measured when declared. Only the `llama_cpp` backend has an adapter."""

    id: str = Field(min_length=1)
    backend: Literal["llama_cpp"]
    label_fr: str = Field(min_length=1)
    license: str = Field(min_length=1)
    max_tokens: int = Field(gt=0)
    load_path: str = Field(min_length=1)
    measured_rss_mb: int | None = Field(default=None, gt=0)
    files: list[ModelFile] = Field(min_length=1)

    @field_validator("load_path")
    @classmethod
    def _inside_models_dir(cls, value: str) -> str:
        return _relative_path(value)

    @model_validator(mode="after")
    def _load_path_is_declared(self) -> LocalModelSpec:
        """The file loaded is one of `files`: its size (and sha256) identify the model."""
        if PurePosixPath(self.load_path) not in {PurePosixPath(f.path) for f in self.files}:
            raise ValueError("load_path must be one of files[].path")
        return self

    @property
    def load_file(self) -> ModelFile:
        return next(f for f in self.files if PurePosixPath(f.path) == PurePosixPath(self.load_path))


class EmbeddingModel(LocalModelSpec):
    """`[rag.embedding]` (story 15): the single place that names the embedding model, with
    the values of story 12's verdict."""

    dims: int = Field(gt=0)
    query_prefix: str = ""
    passage_prefix: str = ""


class RerankerModel(LocalModelSpec):
    """`[rag.reranker]` (story 16): the single place that names the reranking model, with
    the values of story 12's verdict. `max_tokens`: one query-excerpt pair."""

    max_tokens: int = Field(gt=8)


class FastembedModel(_Strict):
    """`[rag_lab.fastembed]` (story 30): an optional embedding model of the RAG workshop, run
    by fastembed (ONNX), never downloaded by WaveStack: its files lie under
    `models_dir()/fastembed`, opened with `local_files_only`."""

    model_name: str = Field(min_length=1)
    dims: int = Field(gt=0)
    label_fr: str = Field(min_length=1)
    # The model's own folder under `models/fastembed`, as fastembed's cache names it; by
    # default `models--{model_name, « / » as « -- »}`.
    folder: str | None = Field(default=None, min_length=1)

    @field_validator("folder")
    @classmethod
    def _inside_fastembed_dir(cls, value: str | None) -> str | None:
        return None if value is None else _relative_path(value)

    @property
    def folder_name(self) -> str:
        return self.folder or "models--" + self.model_name.replace("/", "--")


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


_MIB = 1024 * 1024
_GIB = 1024 * _MIB
DEFAULT_BUDGET_MB = 4096  # AD-8, NFR-2: `[memory] budget_mb`, the cap in `dynamic` mode
DEFAULT_BUDGET_RAM_RATIO = 0.6  # story 24: `[memory] budget_ram_ratio`
BUDGET_RAM_RATIO_BOUNDS = (0.1, 0.9)
BUDGET_FLOOR_MB = 512  # story 24: the dynamic budget never goes below it (nor above the cap)


def system_memory() -> tuple[int, int]:
    """Story 24: the machine's RAM, total and available, in bytes (`psutil`). Raises when
    the OS does not say it; tests replace this function."""
    import psutil  # opens no connection; imported here to keep `config` light at import

    memory = psutil.virtual_memory()
    return int(memory.total), int(memory.available)


def mo_fr(n: int) -> str:
    """Bytes in Mo, rounded, French thousands separator: « 4 096 » (the unit apart)."""
    return f"{round(n / _MIB):,}".replace(",", "\u202f")


def go_fr(n: int) -> str:
    """Bytes in Go, one decimal, French decimal comma: « 3,1 Go »."""
    return f"{n / _GIB:.1f}".replace(".", ",") + " Go"


def size_fr(n: int) -> str:
    """Lot E (E3): « 210 Mo » under 1 Go, « 3,1 Go » from there on."""
    return f"{mo_fr(n)} Mo" if n < _GIB else go_fr(n)


def _with_mo(n: int) -> str:
    return f"{mo_fr(n)} Mo"


def _percent_fr(ratio: float) -> str:
    """« 60 % », « 62,5 % »."""
    return f"{ratio * 100:.1f}".rstrip("0").rstrip(".").replace(".", ",") + "\u00a0%"


@dataclass(frozen=True)
class MemoryBudget:
    """Story 24 (AD-8, NFR-2): WaveStack's memory budget, computed once at launch.

    `dynamic` (default): `min(cap, max(floor, ratio × RAM available at launch))`; `fixed`:
    the cap itself (`[memory] budget_mb`). `ram_limited`: the RAM, not the cap, set it;
    `floored`: the RAM share was below `BUDGET_FLOOR_MB`. `measured`: the RAM could be read
    (else the budget is the cap)."""

    bytes: int
    mode: Literal["dynamic", "fixed"]
    cap_bytes: int
    ratio: float
    total_bytes: int | None = None
    available_bytes: int | None = None
    ram_limited: bool = False
    measured: bool = False
    floored: bool = False

    def calc_fr(self) -> str:
        """How the budget was reached, in French and in Mo (the diagnostic)."""
        cap = f"[memory] budget_mb de {_with_mo(self.cap_bytes)}"
        if self.mode == "fixed":
            return f"valeur fixe {cap} (budget_mode = « fixed »)"
        if not self.measured or self.available_bytes is None:
            return f"plafond {cap}, RAM du poste non mesurée"
        share = f"{_percent_fr(self.ratio)} des {_with_mo(self.available_bytes)} de RAM"
        total = f", sur {_with_mo(self.total_bytes)}" if self.total_bytes else ""
        part = f"({_with_mo(int(self.ratio * self.available_bytes))})"
        if self.floored:
            return (
                f"{share} disponibles au lancement {part}{total}, relevé au plancher de "
                f"{BUDGET_FLOOR_MB} Mo"
            )
        if self.ram_limited:
            return f"{share} disponibles au lancement {part}{total}, sous le plafond {cap}"
        return f"plafond {cap}, plus petit que {share} disponibles au lancement {part}{total}"

    def short_fr(self, fmt: Callable[[int], str] = size_fr) -> str:
        """The calculation in short, for a refusal (one unit: `fmt`): « = plafond
        [memory] budget_mb », « = 60 % des 7,2 Go de RAM disponibles au lancement »."""
        if self.mode == "fixed":
            return "= valeur fixe [memory] budget_mb"
        if not self.measured or self.available_bytes is None:
            return "= plafond [memory] budget_mb, RAM du poste non mesurée"
        if self.floored:
            return "= plancher, RAM disponible au lancement faible"
        if self.ram_limited:
            return (
                f"= {_percent_fr(self.ratio)} des {fmt(self.available_bytes)} de RAM "
                "disponibles au lancement"
            )
        return "= plafond [memory] budget_mb"


def compute_memory_budget(mode: str, cap_mb: int, ratio: float) -> MemoryBudget:
    """Story 24: the budget from the `[memory]` settings (already bounded) and the RAM read
    now. The RAM unreadable (or said to be 0): the cap, said in the calculation."""
    cap = max(1, cap_mb) * _MIB
    fixed = mode == "fixed"
    try:
        total, available = system_memory()
    except Exception:  # noqa: BLE001 - any failure of the OS reading: the cap, never a crash
        total = available = 0
    if available <= 0:
        return MemoryBudget(
            bytes=cap, mode="fixed" if fixed else "dynamic", cap_bytes=cap, ratio=ratio
        )
    total = total if total > 0 else None
    if fixed:  # the RAM is read for the diagnostic only
        return MemoryBudget(
            bytes=cap,
            mode="fixed",
            cap_bytes=cap,
            ratio=ratio,
            total_bytes=total,
            available_bytes=available,
            measured=True,
        )
    part = int(ratio * available)
    floor = BUDGET_FLOOR_MB * _MIB
    return MemoryBudget(
        bytes=min(cap, max(floor, part)),
        mode="dynamic",
        cap_bytes=cap,
        ratio=ratio,
        total_bytes=total,
        available_bytes=available,
        ram_limited=part < cap,
        measured=True,
        floored=part < floor < cap,
    )


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

    @property
    def net_contact(self) -> str:
        """Lot D: `[net] contact` for the User-Agent; the default when missing or invalid
        (not a string, empty, longer than 200, or outside printable ASCII without parentheses,
        which would break the header's comment)."""
        value = self.get("net", "contact", default=None)
        if not isinstance(value, str):
            return DEFAULT_NET_CONTACT
        value = value.strip()
        valid = 0 < len(value) <= 200 and all(" " <= c <= "~" and c not in "()" for c in value)
        return value if valid else DEFAULT_NET_CONTACT

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
                # Story 23: the key header's reason, in French (the other reasons are not).
                reasons = "".join(
                    f" {e['msg'].removeprefix('Value error, ')}"
                    for e in exc.errors()
                    if e["loc"][:1] == ("auth_header",) and e["type"] == "value_error"
                )
                errors.append(
                    f"Modèle cloud « {name} » écarté : déclaration invalide ({fields}).{reasons} "
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
    def eur_per_usd(self) -> float:
        """FinOps: `[finops] eur_per_usd`, the rate the session's spend is converted at, in
        euros per dollar (0,86 by default, bounded to [0,5 ; 2]). A value that is not a finite
        number (unreadable, `nan`, `inf`) is the default, never clamped."""
        try:
            rate = float(self.get("finops", "eur_per_usd", default=DEFAULT_EUR_PER_USD))
        except (TypeError, ValueError):
            return DEFAULT_EUR_PER_USD
        return min(2.0, max(0.5, rate)) if math.isfinite(rate) else DEFAULT_EUR_PER_USD

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
        """`[context] window` (AD-9), `DEFAULT_WINDOW` by default. Story 26: a window chosen
        in the interface comes from `settings.json` (`context.window`), merged over
        `wavestack.toml` by `load_config`; during the session, `AppSession.configured_window`
        is the one that holds. A boolean, a non-number, or a value not above `OUTPUT_RESERVE`
        gives `DEFAULT_WINDOW`."""
        value = self.get("context", "window", default=DEFAULT_WINDOW)
        if isinstance(value, bool):  # `true` is no window
            return DEFAULT_WINDOW
        try:
            window = int(value)
        except (TypeError, ValueError, OverflowError):
            return DEFAULT_WINDOW
        # A window no larger than the output reserve leaves no context (`usable` ≤ 0): the
        # default. Above it, a window up to `MAX_RESERVE` stays valid: the reasoning brick is
        # then unavailable (`reasoning_window_fr`), so `usable` stays positive.
        return window if window > OUTPUT_RESERVE else DEFAULT_WINDOW

    @cached_property
    def memory_budget(self) -> MemoryBudget:
        """AD-8, story 24: the memory budget, computed once per `Config` (the launch computes
        it right after loading the configuration, `cli.main`), shared by the diagnostic and
        the session: `[memory] budget_mode`
        (`dynamic` by default, an unknown mode too, or `fixed`), `budget_mb` (the cap, or
        the fixed value) and `budget_ram_ratio` (0,6, bounded to [0,1 ; 0,9])."""
        raw_mode = self.get("memory", "budget_mode", default="dynamic")
        mode = "fixed" if str(raw_mode).strip().lower() == "fixed" else "dynamic"
        low, high = BUDGET_RAM_RATIO_BOUNDS
        raw_ratio = self.get("memory", "budget_ram_ratio", default=DEFAULT_BUDGET_RAM_RATIO)
        ratio = (
            DEFAULT_BUDGET_RAM_RATIO
            if isinstance(raw_ratio, bool)
            else self._float(
                "memory", "budget_ram_ratio", default=DEFAULT_BUDGET_RAM_RATIO, low=low, high=high
            )
        )
        if not math.isfinite(ratio):
            ratio = DEFAULT_BUDGET_RAM_RATIO
        raw_cap = self.get("memory", "budget_mb", default=DEFAULT_BUDGET_MB)
        try:  # `inf`, `true`, a text, 0 or less: the default, never a crash nor a 1 Mo budget
            cap_mb = DEFAULT_BUDGET_MB if isinstance(raw_cap, bool) else int(raw_cap)
        except (TypeError, ValueError, OverflowError):
            cap_mb = DEFAULT_BUDGET_MB
        if cap_mb < 1:
            cap_mb = DEFAULT_BUDGET_MB
        return compute_memory_budget(mode, cap_mb, ratio)

    @property
    def memory_budget_bytes(self) -> int:
        """AD-8: WaveStack's memory budget in bytes (`memory_budget`)."""
        return self.memory_budget.bytes

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
                "modèle d'embedding. Rétablissez-la, puis relancez WaveStack (la configuration "
                "n'est lue qu'au lancement)."
            )
        try:
            return EmbeddingModel.model_validate(raw), None
        except ValidationError as exc:
            fields = ", ".join(
                ".".join(str(p) for p in e["loc"]) or "section" for e in exc.errors()
            )
            return None, (
                f"La section [rag.embedding] est invalide ({fields}). Corrigez wavestack.toml "
                "ou settings.json, puis relancez WaveStack (la configuration n'est lue qu'au "
                "lancement)."
            )

    @property
    def rag_top_k(self) -> int:
        """Story 15: the excerpts placed in the context at each turn, 1 to 20 (story 16: the
        reranker's candidates never exceed 20 either)."""
        return min(20, max(1, self._int("rag", "top_k", default=3)))

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
        """Story 20 (AD-8): what loading Headroom is expected to add (lot J: 84 MB at peak on
        the target PC with `gpt-4`, plus 30 %; 107 MB at peak on Linux)."""
        return max(0, self._int("compression", "cost_mb", default=110)) * 1024 * 1024

    @cached_property
    def rag_lab_fastembed(self) -> tuple[FastembedModel | None, str | None]:
        """Story 30: the workshop's fastembed model, or why there is none (French)."""
        raw = self.get("rag_lab", "fastembed")
        if raw is None:
            return None, (
                "Indisponible : aucun modèle fastembed n'est déclaré. Ajoutez une section "
                "[rag_lab.fastembed] (model_name, dims, label_fr) à settings.json, WaveStack "
                "arrêté."
            )
        try:
            return FastembedModel.model_validate(raw), None
        except ValidationError as exc:
            fields = ", ".join(
                ".".join(str(p) for p in e["loc"]) or "section" for e in exc.errors()
            )
            return None, (
                f"Indisponible : la section [rag_lab.fastembed] est invalide ({fields}). "
                "Corrigez-la, puis relancez WaveStack."
            )

    @property
    def rag_lab_faiss_cost_bytes(self) -> int:
        """Story 30 (AD-8): what importing FAISS is expected to add, `[rag_lab] faiss_cost_mb`
        (16 MB measured on Linux, 37 MB with numpy's first import)."""
        return max(0, self._int("rag_lab", "faiss_cost_mb", default=60)) * 1024 * 1024

    @property
    def rag_lab_fastembed_cost_bytes(self) -> int:
        """Story 30 (AD-8): what importing fastembed (and onnxruntime) is expected to add, for
        the life of WaveStack, `[rag_lab] fastembed_cost_mb`; the model itself is counted
        apart, by its files' size, and released after each run."""
        return max(0, self._int("rag_lab", "fastembed_cost_mb", default=150)) * 1024 * 1024

    @property
    def rag_lab_lancedb_cost_bytes(self) -> int:
        """Story 30 (AD-8): what importing LanceDB (and pyarrow) is expected to add,
        `[rag_lab] lancedb_cost_mb` (104 to 121 MB measured on Linux)."""
        return max(0, self._int("rag_lab", "lancedb_cost_mb", default=180)) * 1024 * 1024

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
    def tool_result_max_tokens(self) -> int:
        """Lot B (N3): the most tokens a network or MCP tool's result may take, cut before the
        compression; a missing or non-integer value is the default, and 200 the floor."""
        default = DEFAULT_TOOL_RESULT_MAX_TOKENS
        raw = self.get("tools", "result_max_tokens", default=default)
        if isinstance(raw, bool) or (isinstance(raw, float) and not raw.is_integer()):
            return default
        return max(200, self._int("tools", "result_max_tokens", default=default))

    @property
    def reasoning_budget_tokens(self) -> int:
        """Lot C (N4), local mode: the reasoning tokens after which the harness closes the
        reasoning itself, the rest of the reserve going to the answer. A missing or
        non-integer value is the default; bounded so that the reasoning and the answer each
        keep at least 128 of the 1 536 tokens of the reserve."""
        default = DEFAULT_REASONING_BUDGET
        raw = self.get("reasoning", "budget_tokens", default=default)
        if isinstance(raw, bool) or (isinstance(raw, float) and not raw.is_integer()):
            return default
        value = self._int("reasoning", "budget_tokens", default=default)
        return min(MAX_RESERVE - MIN_REASONING_BUDGET, max(MIN_REASONING_BUDGET, value))

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


def rag_lab_dir() -> Path:
    """Story 30 (AD-20): the RAG workshop's vectors and indexes, built on demand, never in
    the repository; the folder can be deleted, WaveStack stopped."""
    return data_dir() / "rag_lab"


def memory_path() -> Path:
    """The global memory (AD-20), read and written by the session only (AD-23)."""
    return data_dir() / "memory.json"


def audit_path() -> Path:
    """The audit log H2 feeds, written by the session only (AD-20, AD-23)."""
    return data_dir() / "audit.log"
