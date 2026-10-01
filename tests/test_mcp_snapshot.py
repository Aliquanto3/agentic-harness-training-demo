"""Story 2 of the deferred leftovers (E089, AD-9): a public MCP server whose live `tools/list`
drifts from its versioned snapshot beyond `[mcp] snapshot_drift_threshold` is said on the
MCP card and in `mcp_connect_ended`; without a snapshot, nothing."""

from __future__ import annotations

import json

import pytest
from test_mcp import MSLEARN_TOOLS, McpWeb, enable, loop, mcp_session, since, web  # noqa: F401

from wavestack import config
from wavestack.mcp import snapshot as mcp_snapshot
from wavestack.trace.journal import get_journal

EXTRA_TOOL = {
    "name": "microsoft_learn_quiz",
    "description": "Build a quiz from a Microsoft Learn module.",
    "inputSchema": {"type": "object", "properties": {"module": {"type": "string"}}},
}


@pytest.fixture
def snapshots(tmp_path, monkeypatch):
    """`content/mcp_snapshots/` replaced by a folder of the test's own."""
    monkeypatch.setattr(
        mcp_snapshot, "snapshot_path", lambda server_id: tmp_path / f"{server_id}.json"
    )

    def write(server_id: str, tools: list[dict]) -> None:
        body = {"server": server_id, "captured_at": "2026-09-27T06:36:17+00:00", "tools": tools}
        (tmp_path / f"{server_id}.json").write_text(json.dumps(body), encoding="utf-8")

    return write


def _mcp_card() -> dict:
    bricks = since(0, "bricks_changed")[-1].payload["bricks"]
    return next(b for b in bricks if b["id"] == "mcp")


def _connect_mslearn(loop, web, tools: list[dict], **mcp) -> tuple:  # noqa: F811
    web(McpWeb(tools))
    session = mcp_session(loop, **mcp)
    session.set_mcp_server("local", False)
    ended = enable(session, "mslearn")
    assert ended["status"] == "ok"
    return session, ended


# ---------- the measure, pure ----------


def test_drift_counts_tools_added_removed_and_the_documentation_weight():
    renamed = {**MSLEARN_TOOLS[2], "name": "microsoft_docs_get"}
    live = [MSLEARN_TOOLS[0], MSLEARN_TOOLS[1], renamed]

    drift = mcp_snapshot.drift(MSLEARN_TOOLS, live)

    assert drift.added == ("microsoft_docs_get",)
    assert drift.removed == ("microsoft_docs_fetch",)
    assert drift.weight_before == sum(mcp_snapshot.tool_weight(t) for t in MSLEARN_TOOLS)
    assert drift.ratio == pytest.approx(2 / 3)  # two names changed on three tools
    same = mcp_snapshot.drift(MSLEARN_TOOLS, MSLEARN_TOOLS)
    assert (same.added, same.removed, same.ratio) == ((), (), 0.0)
    longer = [{**t, "description": t["description"] * 3} for t in MSLEARN_TOOLS]
    assert mcp_snapshot.drift(MSLEARN_TOOLS, longer).ratio > 0.2  # same names, heavier docs


def test_the_versioned_snapshots_are_read():
    """The session reads `content/mcp_snapshots/` as `scripts/snapshot_mcp.py` writes it."""
    for server_id in ("datagouv", "mslearn"):
        tools = mcp_snapshot.load_snapshot(server_id)
        assert tools and all(isinstance(t.get("name"), str) and t["name"] for t in tools)
        assert mcp_snapshot.documentation_weight(tools) > 0
    assert mcp_snapshot.load_snapshot("local") is None  # the local server has none


def test_a_gap_just_over_the_threshold_never_reads_as_equal_to_it(loop):  # noqa: F811
    session = mcp_session(loop)
    drift = mcp_snapshot.Drift((), (), 1000, 1204, 0.204)

    assert "de 21 % (seuil : 20 %)" in session._drift_text("mslearn", drift)
    session.close()


def test_threshold_is_read_bounded_and_defaults_to_a_fifth():
    def threshold(value):  # noqa: ANN001, ANN202
        return config.Config(values={"mcp": {"snapshot_drift_threshold": value}})

    assert config.Config(values={}).mcp_snapshot_drift_threshold == 0.2
    assert threshold(0.5).mcp_snapshot_drift_threshold == 0.5
    assert threshold(-1).mcp_snapshot_drift_threshold == 0.0
    assert threshold(99).mcp_snapshot_drift_threshold == 10.0
    for unreadable in ("beaucoup", float("nan"), True, None):
        assert threshold(unreadable).mcp_snapshot_drift_threshold == 0.2
    assert config.load_config().mcp_snapshot_drift_threshold == 0.2  # wavestack.toml


# ---------- at connection ----------


def test_a_server_beyond_the_threshold_is_said_on_the_mcp_card(loop, web, snapshots):  # noqa: F811
    snapshots("mslearn", MSLEARN_TOOLS)

    session, ended = _connect_mslearn(loop, web, [*MSLEARN_TOOLS, EXTRA_TOOL])

    text = ended["drift_text"]
    assert text.startswith("Microsoft Learn s'écarte de son instantané de")
    assert "1 outil ajouté (microsoft_learn_quiz)" in text and "seuil : 20 %" in text
    assert "scripts/snapshot_mcp.py" in text
    options = {o["id"]: o for o in _mcp_card()["options"]}
    assert options["mslearn"]["drift_text"] == text
    assert options["local"]["drift_text"] is None and options["datagouv"]["drift_text"] is None

    mark = get_journal().last_seq()
    session.set_mcp_server("mslearn", False)  # disconnected: the warning goes with it
    session.join()
    assert since(mark, "bricks_changed")
    assert {o["id"]: o["drift_text"] for o in _mcp_card()["options"]}["mslearn"] is None
    session.close()


def test_a_server_within_the_threshold_says_nothing(loop, web, snapshots):  # noqa: F811
    snapshots("mslearn", MSLEARN_TOOLS)

    session, ended = _connect_mslearn(
        loop, web, [*MSLEARN_TOOLS, EXTRA_TOOL], snapshot_drift_threshold=0.5
    )

    assert "drift_text" not in ended
    assert all(o["drift_text"] is None for o in _mcp_card()["options"])
    session.close()


def test_the_same_tools_as_the_snapshot_say_nothing(loop, web, snapshots):  # noqa: F811
    snapshots("mslearn", MSLEARN_TOOLS)

    session, ended = _connect_mslearn(loop, web, MSLEARN_TOOLS)

    assert "drift_text" not in ended
    session.close()


def test_a_server_that_fails_loses_its_warning(loop, web, snapshots):  # noqa: F811
    snapshots("mslearn", MSLEARN_TOOLS)
    session, ended = _connect_mslearn(loop, web, [*MSLEARN_TOOLS, EXTRA_TOOL])
    assert ended["drift_text"]

    session._mcp_failed("mslearn", "délai dépassé")  # a call could not reach it

    assert {o["id"]: o["drift_text"] for o in session._mcp_options()}["mslearn"] is None
    session.close()


def test_the_local_server_is_never_compared(loop, snapshots):  # noqa: F811
    from wavestack.mcp.servers import McpServer

    snapshots("local", [EXTRA_TOOL])
    session = mcp_session(loop)

    assert session._mcp_snapshot_drift(McpServer("local", None), []) is None
    session.close()


def test_without_a_snapshot_nothing_is_compared(loop, web, snapshots):  # noqa: F811
    session, ended = _connect_mslearn(loop, web, [EXTRA_TOOL])

    assert "drift_text" not in ended
    assert all(o["drift_text"] is None for o in _mcp_card()["options"])
    session.close()
