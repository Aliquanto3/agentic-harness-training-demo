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
# CAP-9 (the page Sécurité's « Matrice des risques »): one row per `mcp-tools.md` category,
# with the tools it names; `write` flags a row whose tools the page's « Quels outils peuvent
# écrire ? » card counts. Order matches `mcp-tools.md`. A tool set from the interface joins
# its row (`ToolPolicy.matrix`): the matrix shows each tool's live rule, never one stand-in.
MATRIX_ROWS: tuple[tuple[str, tuple[str, ...], bool], ...] = (
    ("glossary", ("local__list_terms", "local__define_term"), False),
    ("system", ("local__system_info",), False),
    ("create_path", ("local__create_path",), True),
    ("screenshot", ("local__take_screenshot",), False),
    ("network", (), False),  # datagouv, mslearn: no named tool, the fallback rule
    (
        "github_read",
        (
            "github__list_secret_scanning_alerts",
            "github__list_dependabot_alerts",
            "github__get_file_contents",
            "github__list_issues",
        ),
        False,
    ),
    ("github_write", ("github__merge_pull_request", "github__create_pull_request"), True),
)
_RISK_ORDER = {risk: i for i, risk in enumerate(RISKS)}


def matrix_row_of(name: str) -> str | None:
    """The matrix row a tool belongs to: its named row, else any other GitHub tool is a
    write (`_GITHUB_FALLBACK`), any non-local one a network read; `None` for an unnamed
    local tool (none today)."""
    for row_id, tools, _ in MATRIX_ROWS:
        if name in tools:
            return row_id
    if name.startswith(_GITHUB_PREFIX):
        return "github_write"
    return None if name.startswith("local__") else "network"


_FALLBACK = ("low", "allow")
# GitHub exposes 46 tools (28 read-only): one not named above is presumed to write (the
# orchestrator's prudent default), high risk, refused until this table names it explicitly.
_GITHUB_PREFIX = "github__"
_GITHUB_FALLBACK = ("high", "deny")
# The rows standing for tools they do not name (datagouv, mslearn; « toute écriture »).
_IMPLICIT = {"network": _FALLBACK, "github_write": _GITHUB_FALLBACK}


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

    def matrix(self) -> list[dict[str, object]]:
        """CAP-9: each row with its tools (named, plus any set from the interface that
        belongs to it) and the rule of each; the row's rule (`mixed` when they differ) and
        highest risk also count the tools it does not name (`_IMPLICIT`), on their default."""
        overrides = self.rules()
        rows = []
        for row_id, named, write in MATRIX_ROWS:
            tools = list(named) + [
                n for n in overrides if n not in named and matrix_row_of(n) == row_id
            ]
            rules = {n: overrides.get(n, self.default_rule(n)) for n in tools}
            risks = [self.risk_of(n) for n in tools]
            distinct = set(rules.values())
            if (rest := _IMPLICIT.get(row_id)) is not None:
                risks.append(rest[0])
                distinct.add(rest[1])
            rows.append(
                {
                    "id": row_id,
                    "write": write,
                    "risk": max(risks, key=_RISK_ORDER.__getitem__),
                    "rule": distinct.pop() if len(distinct) == 1 else "mixed",
                    "rules": rules,
                }
            )
        return rows

    def rules(self) -> dict[str, str]:
        """The rules set from the interface this session, by exposed name."""
        with self._lock:
            return dict(self._overrides)
