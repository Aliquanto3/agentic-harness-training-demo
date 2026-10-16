"""CAP-2: risk level and allow/ask/deny rule per MCP tool.

Defaults validated against `mcp-tools.md` (2026-10-16): the local glossary and the public
servers' tools are low risk, allowed; a future story (2: sandboxed files and the
screenshot, 3: GitHub) adds its own entries here as it introduces those tools. A tool not
listed defaults to low risk, allowed, so a new tool never starts out silently refused.

The rule alone is settable from the interface (CAP-2's "réglable dans l'interface"); the
risk level is a fact about the tool, not a setting.
"""

from __future__ import annotations

import threading

RISKS = ("low", "mid", "high")
RULES = ("allow", "ask", "deny")

# Exposed tool name (`{server}__{tool}`, `ToolRegistry.exposed_name`) -> (risk, default rule).
_DEFAULTS: dict[str, tuple[str, str]] = {
    "local__list_terms": ("low", "allow"),
    "local__define_term": ("low", "allow"),
    # Story 2 (CAP-1), defaults validated in `mcp-tools.md`.
    "local__system_info": ("low", "allow"),
    "local__create_path": ("mid", "ask"),
    "local__take_screenshot": ("high", "ask"),
    # Story 3 (CAP-4), defaults validated in `mcp-tools.md`: GitHub acts with the connected
    # person's own rights, so a read tool stays a deliberate choice (`ask` would need the
    # workshop's own authorization bandeau for every alert lookup); writes are refused.
    "github__list_secret_scanning_alerts": ("mid", "allow"),
    "github__list_dependabot_alerts": ("mid", "allow"),
    "github__get_file_contents": ("mid", "allow"),
    "github__list_issues": ("mid", "allow"),
    "github__merge_pull_request": ("high", "deny"),
    "github__create_pull_request": ("high", "deny"),
}
_FALLBACK = ("low", "allow")
# GitHub exposes 46 tools (28 read-only): one not named above is presumed to write (the
# orchestrator's prudent default), high risk, refused until this table names it explicitly.
_GITHUB_PREFIX = "github__"
_GITHUB_FALLBACK = ("high", "deny")


def _lookup(name: str) -> tuple[str, str]:
    if name in _DEFAULTS:
        return _DEFAULTS[name]
    return _GITHUB_FALLBACK if name.startswith(_GITHUB_PREFIX) else _FALLBACK


class ToolPolicy:
    """The rule overrides a session holds on top of `mcp-tools.md`'s defaults; thread-safe
    (a tool call and a rule change may come from different threads)."""

    def __init__(self) -> None:
        self._lock = threading.Lock()
        self._overrides: dict[str, str] = {}

    @staticmethod
    def risk_of(name: str) -> str:
        return _lookup(name)[0]

    @staticmethod
    def default_rule(name: str) -> str:
        return _lookup(name)[1]

    def rule_of(self, name: str) -> str:
        with self._lock:
            return self._overrides.get(name, self.default_rule(name))

    def set_rule(self, name: str, rule: str) -> None:
        if rule not in RULES:
            raise ValueError(rule)
        with self._lock:
            # Kept even when back to the default: `rules()` must tell a reloaded page that a
            # tool's rule changed since its connection listed it.
            self._overrides[name] = rule

    def rules(self) -> dict[str, str]:
        """The rules set from the interface this session, by exposed name."""
        with self._lock:
            return dict(self._overrides)
