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
}
_FALLBACK = ("low", "allow")


class ToolPolicy:
    """The rule overrides a session holds on top of `mcp-tools.md`'s defaults; thread-safe
    (a tool call and a rule change may come from different threads)."""

    def __init__(self) -> None:
        self._lock = threading.Lock()
        self._overrides: dict[str, str] = {}

    @staticmethod
    def risk_of(name: str) -> str:
        return _DEFAULTS.get(name, _FALLBACK)[0]

    @staticmethod
    def default_rule(name: str) -> str:
        return _DEFAULTS.get(name, _FALLBACK)[1]

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
