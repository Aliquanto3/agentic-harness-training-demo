"""Lot B: the results of network and MCP tools bounded to `[tools] result_max_tokens` (N3),
and the cause of an overflow named from the real breakdown.

The fake engine counts one token per UTF-8 byte: the texts below are sized in bytes.
"""

from __future__ import annotations

import json
import re

import httpx
import httpx2
import pytest
from fake_engine import FakeEngine
from pydantic import SecretStr
from test_cloud import SENTINEL, Provider, delta, sse
from test_compression import Compressors
from test_mcp import MSLEARN_TOOLS, McpWeb, enable, loop, mcp_session  # noqa: F401 - fixture
from test_tools import QWEN, _segments, call, tool_session
from test_turn import _run

from wavestack import config
from wavestack.context.segments import SegmentKind
from wavestack.mcp import connection
from wavestack.net.factory import create_async_client, create_client
from wavestack.session.app_session import AppSession
from wavestack.tools import network
from wavestack.trace.catalog import ToolEndedPayload
from wavestack.trace.journal import get_journal

LIMIT = config.DEFAULT_TOOL_RESULT_MAX_TOKENS
FLOOR = 200
MENTION = "[Résultat tronqué par le harnais : "
PARIS = "https://fr.wikipedia.org/wiki/Paris"
PAGE = "\n".join(f"Ligne {i} de la page, avec un peu de texte." for i in range(200))
LOG = (config.content_dir() / "demo_files" / "journal_serveur.log").read_text(encoding="utf-8")
# ≈ 3 000 bytes, 40 lines: as data.gouv's answer to a search.
DATASETS = "\n".join(f"- Jeu de données n° {i} : qualité de l'air, mesures {i}" for i in range(60))


@pytest.fixture
def mcp_web(monkeypatch):
    """Public MCP servers answered in process (as `test_mcp.web`)."""

    def install(server: McpWeb) -> McpWeb:
        monkeypatch.setattr(
            connection,
            "create_async_client",
            lambda **kw: create_async_client(transport=httpx2.MockTransport(server), **kw),
        )
        return server

    return install


@pytest.fixture
def net_web(monkeypatch):
    """Network tools answered by `handler` (as `test_tools.web`)."""

    def install(handler) -> None:  # noqa: ANN001
        monkeypatch.setattr(
            network,
            "create_client",
            lambda **kw: create_client(transport=httpx.MockTransport(handler), **kw),
        )

    return install


def _search(text: str):
    return lambda params: {"content": [{"type": "text", "text": text}]}


def _mslearn_turn(loop, mcp_web, text: str) -> dict:  # noqa: F811
    mcp_web(McpWeb(MSLEARN_TOOLS, _search(text)))
    outputs = [call("mslearn__microsoft_docs_search", query="qualité de l'air"), "Voilà."]
    session = mcp_session(loop, outputs, window=8192)
    session.set_mcp_server("local", False)
    enable(session, "mslearn")
    events = _run(session, "Cherche")
    session.close()
    return events


def _kept(bounded: str) -> str:
    return bounded.split(f"\n\n{MENTION}")[0]


# ---------- I/O matrix ----------


def test_long_mcp_result_is_cut_at_a_line_break_with_the_mention(loop, mcp_web):  # noqa: F811
    assert len(DATASETS.encode("utf-8")) > 2 * LIMIT

    events = _mslearn_turn(loop, mcp_web, DATASETS)

    (ended,) = events["tool_ended"]
    ToolEndedPayload.model_validate(ended)
    result = ended["result"]
    assert len(result.encode("utf-8")) <= LIMIT  # the fake engine: one token per byte
    kept = _kept(result)
    assert DATASETS.startswith(kept) and DATASETS[len(kept)] == "\n"  # whole lines, in order
    total = len(DATASETS.encode("utf-8"))
    tokens = len(kept.encode("utf-8"))
    assert ended["truncated"] == {"tokens": tokens, "total_tokens": total, "estimated": False}
    assert result.endswith(
        f"{MENTION}{tokens} tokens sur {total}. Réponds avec ce qui est gardé, ou relance "
        "l'outil avec une demande plus précise.]"
    )
    assert tokens > LIMIT - 200  # as close to the bound as the lines allow
    # What the model reads next is the bounded text, never the rest.
    reinjected = _segments(events["context_rendered"][1], "tool_result")[0]["text"]
    assert reinjected == result and DATASETS[-30:] not in reinjected
    assert events["turn_ended"][0]["status"] == "completed"


def test_short_mcp_result_is_unchanged(loop, mcp_web):  # noqa: F811
    events = _mslearn_turn(loop, mcp_web, "Trois jeux de données.")

    (ended,) = events["tool_ended"]
    assert ended["result"] == "Trois jeux de données." and "truncated" not in ended


def test_a_single_long_line_is_cut_on_a_character_boundary(loop, mcp_web):  # noqa: F811
    line = "é" * 2000  # 2 bytes each: a cut by bytes would split one

    events = _mslearn_turn(loop, mcp_web, line)

    result = events["tool_ended"][0]["result"]
    kept = _kept(result)
    assert set(kept) == {"é"} and len(result.encode("utf-8")) <= LIMIT
    mention = len(result.encode("utf-8")) - len(kept.encode("utf-8"))
    assert len(kept.encode("utf-8")) >= LIMIT - mention - 2  # as close as a character allows


def test_read_file_is_never_bounded():
    engine = FakeEngine(
        outputs=[call("read_file", path="journal_serveur.log"), "Voilà."],
        template=QWEN.decode("utf-8"),
        architecture="qwen35",
    )
    session = AppSession(
        config.Config(values={"context": {"window": 16384}}),
        engine_factory=lambda path, n_ctx: engine,
    )
    session.boot("fake.gguf").result()
    session.set_brick("tools", True)
    assert len(LOG.encode("utf-8")) > LIMIT

    (ended,) = _run(session, "Lis le journal")["tool_ended"]

    assert ended["result"] == LOG and "truncated" not in ended
    session.close()


def test_a_long_tool_error_is_never_bounded(loop, mcp_web):  # noqa: F811
    server = mcp_web(McpWeb(MSLEARN_TOOLS))
    long = "Paramètre invalide. " * 200
    server.error = {"code": -32602, "message": long}
    session = mcp_session(loop, [call("mslearn__microsoft_docs_search", query="x"), "Voilà."])
    session.set_mcp_server("local", False)
    enable(session, "mslearn")

    (ended,) = _run(session, "Cherche")["tool_ended"]

    assert ended["status"] == "error" and long.strip() in ended["error_fr"]
    assert ended["result"] is None and "truncated" not in ended
    session.close()


def _chat_turn(net_web, prompt_tokens: int) -> tuple[AppSession, dict]:  # noqa: F811
    """A Groq turn calling `fetch_page` (bound 300); `prompt_tokens`: each call's `usage`,
    from which the session learns its ratio (AD-4) before the tool runs."""
    net_web(lambda r: httpx.Response(200, text=PAGE, headers={"content-type": "text/plain"}))
    tool = sse(
        delta(
            tool_calls=[
                {
                    "index": 0,
                    "id": "call_provider",
                    "type": "function",
                    "function": {
                        "name": "fetch_page",
                        "arguments": json.dumps({"url": PARIS}),
                    },
                }
            ]
        ),
        {
            **delta("tool_calls"),
            "x_groq": {"usage": {"prompt_tokens": prompt_tokens, "completion_tokens": 9}},
        },
    )
    usage = {"prompt_tokens": prompt_tokens, "completion_tokens": 2}
    text = sse(delta(content="Voilà."), {**delta("stop"), "x_groq": {"usage": usage}})
    values = config._deep_merge(config.load_config().values, {"tools": {"result_max_tokens": 300}})
    cfg = config.Config(values=values)
    entry = cfg.cloud_model("groq")
    config.write_api_key(entry.id, entry.host, SecretStr(SENTINEL))
    session = AppSession(cfg, cloud_factory=Provider(tool, text).factory)
    session.boot_cloud(entry).result()
    session.set_brick("tools", True)
    session.set_tool("fetch_page", True)
    session.join()
    (ended,) = _run(session, "Lis la page Paris")["tool_ended"]
    return session, ended


def test_chat_mode_bounds_a_network_result_with_an_estimate(net_web):  # noqa: F811
    session, ended = _chat_turn(net_web, 700)

    cut = ended["truncated"]
    assert cut["estimated"] is True and cut["tokens"] <= 300 < cut["total_tokens"]
    assert session._count_tokens(ended["result"])[0] <= 300
    assert PAGE.startswith(_kept(ended["result"]))
    session.close()


def test_chat_mode_bounds_with_a_provider_ratio_above_one(net_web):  # noqa: F811
    session, ended = _chat_turn(net_web, 100_000)  # the provider counts more: ratio 1,5

    assert session._ratios["groq"] == 1.5
    estimate = config.estimate_tokens(ended["result"], session.cfg.chars_per_token)
    assert round(estimate * 1.5) <= 300  # what the provider counts, not the capped gauge
    assert estimate > 150  # still near the bound: 200 at this ratio, less a line
    assert ended["truncated"]["tokens"] <= 300
    session.close()


@pytest.mark.parametrize(
    ("value", "expected"),
    [
        (None, LIMIT),
        ("beaucoup", LIMIT),
        (1.5, LIMIT),
        (True, LIMIT),
        (50, FLOOR),
        (3000, 3000),
        ("1500", 1500),
        (1500.0, 1500),
    ],
)
def test_bound_default_and_floor(value, expected):
    values = {} if value is None else {"tools": {"result_max_tokens": value}}
    assert config.Config(values=values).tool_result_max_tokens == expected


def test_the_shipped_bound_is_n3():
    assert LIMIT == 1200 and config.load_config().tool_result_max_tokens == LIMIT


def test_a_final_count_above_the_search_shortens_the_prefix_again():
    """A tokenizer that counts the real mention more than the widest one used by the search
    (`N tokens sur N`): the second loop shortens the prefix until the text fits."""
    session = _session()
    text = "\n".join(f"ligne {i:04d} " + "x" * 40 for i in range(100))

    def count(piece: str, *, uncapped: bool = False) -> tuple[int, bool]:
        widest = re.search(r": (\d+) tokens sur \1\.", piece)
        return len(piece.encode()) + (100 if MENTION in piece and not widest else 0), False

    session._count_tokens = count
    bounded, cut = session._bound_result(text)

    assert count(bounded)[0] <= LIMIT and cut["tokens"] < LIMIT - 200
    assert text.startswith(_kept(bounded)) and cut["total_tokens"] == len(text)
    session.close()


# ---------- every path through `_run_tool` ----------


def _values_session(loop, outputs, values: dict) -> AppSession:  # noqa: F811
    """As `test_mcp.mcp_session`, with `values` merged in."""
    engine = FakeEngine(outputs=list(outputs), template=QWEN.decode("utf-8"), architecture="qwen35")
    base = {"context": {"window": 16384}, "mcp": {"connect_timeout_s": 10, "call_timeout_s": 10}}
    session = AppSession(
        config.Config(values=config._deep_merge(base, values)),
        engine_factory=lambda path, n_ctx: engine,
    )
    session.boot("fake.gguf").result()
    if loop is not None:
        session.attach_loop(loop)
    return session


def test_a_local_mcp_server_result_is_cut(loop):  # noqa: F811
    session = _values_session(
        loop,
        [call("local__define_term", term="MCP"), "Voilà."],
        {"tools": {"result_max_tokens": FLOOR}},
    )
    enable(session)

    (ended,) = _run(session, "Que veut dire MCP ?")["tool_ended"]

    assert ended["result"].startswith("MCP : ") and MENTION in ended["result"]
    assert len(ended["result"].encode("utf-8")) <= FLOOR < ended["truncated"]["total_tokens"]
    session.close()


def test_a_forced_action_result_is_cut(net_web):  # noqa: F811
    net_web(lambda r: httpx.Response(200, text=PAGE, headers={"content-type": "text/plain"}))
    _, session = tool_session(["Voilà."], values={"tools": {"result_max_tokens": FLOOR}})
    session.set_tool("fetch_page", True)
    session.join()
    session.arm("tool", "fetch_page", {"url": PARIS})
    mark = get_journal().last_seq()

    _run(session, "Lis la page Paris")

    (ended,) = [e for e in get_journal().events_since(mark) if e.kind == "tool_ended"]
    assert ended.trigger == "user" and ended.payload["truncated"]["total_tokens"] > FLOOR
    assert len(ended.payload["result"].encode("utf-8")) <= FLOOR
    session.close()


def test_a_sub_agent_network_result_is_cut_but_never_the_delegation(net_web):  # noqa: F811
    net_web(lambda r: httpx.Response(200, text=PAGE, headers={"content-type": "text/plain"}))
    answer = "Paris est la capitale. " * 17  # ≈ 390 bytes: above the bound, below the reserve
    outputs = [
        call("delegate", task="Lis la page Paris."),
        call("fetch_page", url=PARIS),
        answer,
        "Voilà.",
    ]
    session = _values_session(None, outputs, {"tools": {"result_max_tokens": FLOOR}})
    for brick in ("tools", "subagent"):
        session.set_brick(brick, True)
    session.set_tool("fetch_page", True)
    session.join()
    mark = get_journal().last_seq()

    _run(session, "Parle-moi de Paris.")

    ended = {
        e.context_id: e.payload for e in get_journal().events_since(mark) if e.kind == "tool_ended"
    }
    assert len(ended["sub1"]["result"].encode("utf-8")) <= FLOOR and ended["sub1"]["truncated"]
    delegated = ended["main"]
    assert delegated["result"] == answer.strip() and "truncated" not in delegated
    assert len(answer.encode("utf-8")) > FLOOR
    session.close()


# ---------- the cause of an overflow (B2) ----------


def _overflow(session: AppSession, **tokens: int) -> str:
    segments = [{"kind": SegmentKind(kind), "tokens": n} for kind, n in tokens.items()]
    mark = get_journal().last_seq()
    session._emit_overflow(
        {"used": 4000, "usable": 3584, "window": 4096, "reserve": 512, "segments": segments}
    )
    (event,) = [e for e in get_journal().events_since(mark) if e.kind == "context_overflow"]
    return event.payload["message_fr"]


def _session(**kwargs) -> AppSession:
    engine = FakeEngine(template=QWEN.decode("utf-8"), architecture="qwen35")
    session = AppSession(
        config.Config(values={"context": {"window": 4096}}),
        engine_factory=lambda path, n_ctx: engine,
        **kwargs,
    )
    session.boot("fake.gguf").result()
    return session


def test_a_tool_result_overflow_names_it_and_never_the_descriptions():
    session = _session(compressor_factory=Compressors())

    message = _overflow(session, tool_result=2500, tool_catalog=900, template=3000, history=100)

    assert "Cause : les résultats d'outils" in message and "question plus précise" in message
    assert "videz la conversation" in message
    assert "descriptions d'outils" not in message
    assert "allumez la compression" in message  # available and off
    session.close()


def test_the_compression_hint_only_when_the_brick_is_available_and_off():
    session = _session(compressor_factory=Compressors())
    session.set_brick("compression", True)
    session.join()
    assert "compression" not in _overflow(session, tool_result=2500)
    session.close()

    session = _session(compressor_factory=Compressors())
    session._compression_missing = "Headroom n'est pas installé."
    assert "compression" not in _overflow(session, tool_result=2500)
    session.close()


def test_memory_and_skills_overflows_name_their_cause():
    session = _session()

    memory = _overflow(session, global_memory=2000, history=300)
    skills = _overflow(session, skill_catalog=900, skill_body=900, history=1500)
    sub = _overflow(session, subagent_result=2000, history=300)

    assert "mémoire globale" in memory and "Modifier la mémoire" in memory
    assert "skills" in skills and "videz la conversation" in skills  # 1 800 together
    assert "résultat du sous-agent" in sub
    session.close()


def test_grouped_kinds_decide_the_winner():
    session = _session()

    history = _overflow(session, history=1000, assistant_turn=800, tool_result=1500)
    hook = _overflow(session, hook_injection=2000, user_message=100, history=300)

    assert "l'historique de la conversation" in history
    assert "hook H3" in hook and "désactivez H3" in hook and "message à lui seul" not in hook
    session.close()


def test_the_message_keeps_the_ties_and_the_descriptions_cause():
    session = _session()

    tie = _overflow(session, user_message=1000, tool_result=1000)
    catalog = _overflow(session, tool_catalog=2000, tool_result=500)

    assert "le message à lui seul" in tie
    assert "descriptions d'outils" in catalog
    session.close()
