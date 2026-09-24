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


def load_config() -> Config:
    """Load wavestack.toml, then overlay settings.json from the data dir."""
    defaults: dict[str, Any] = {}
    toml_path = repo_root() / "wavestack.toml"
    if toml_path.exists():
        try:
            defaults = tomllib.loads(toml_path.read_text(encoding="utf-8"))
        except tomllib.TOMLDecodeError:
            defaults = {}

    settings_path = data_dir() / "settings.json"
    overrides: dict[str, Any] = {}
    if settings_path.exists():
        try:
            overrides = json.loads(settings_path.read_text(encoding="utf-8"))
        except json.JSONDecodeError:
            overrides = {}

    return Config(values=_deep_merge(defaults, overrides))


def content_dir() -> Path:
    """French pedagogical content shipped with the repo (AD-19)."""
    return repo_root() / "content"


def models_dir() -> Path:
    return data_dir() / "models"


def settings_path() -> Path:
    return data_dir() / "settings.json"
