"""Resolves WaveStack's runtime paths and merges configuration (AD-20).

Only this module resolves paths. Defaults live in ``wavestack.toml`` (repo),
overrides in ``settings.json`` (data dir), written by the session only.
"""

from __future__ import annotations

import json
import os
import sys
import tomllib
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any


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
        return list(self.get("net", "allowed_hosts", default=[]))

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
    def selected_model(self) -> str | None:
        """The GGUF chosen on the diagnostic page, loaded at every launch (story 1b)."""
        value = self.get("selected_model")
        return str(value) if value else None


def load_config() -> Config:
    """Load wavestack.toml, then overlay settings.json from the data dir."""
    defaults: dict[str, Any] = {}
    toml_path = repo_root() / "wavestack.toml"
    if toml_path.exists():
        try:
            defaults = tomllib.loads(toml_path.read_text(encoding="utf-8"))
        except tomllib.TOMLDecodeError:
            defaults = {}

    return Config(values=_deep_merge(defaults, read_settings()))


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


def audit_path() -> Path:
    """The audit log H2 feeds, written by the session only (AD-20, AD-23)."""
    return data_dir() / "audit.log"
