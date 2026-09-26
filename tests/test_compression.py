"""Story 20: context compression (AD-4 `transform_context`, AD-8, AD-22).

The session's tests inject `FakeCompressor`: none needs headroom-ai, an optional dependency.
Only `test_headroom_adapter_*` runs the real library, skipped when it is not installed.
"""

from __future__ import annotations

import importlib.util
import json
import os
import threading

import pytest
from fake_engine import FakeEngine
from pydantic import SecretStr
from test_cloud import SENTINEL, Provider, delta, sse
from test_rag import Embedders, build, place_model, rag_config
from test_tools import QWEN, call
from test_turn import _run

from wavestack import config
from wavestack.compression import env as compression_env
from wavestack.compression import headroom_adapter
from wavestack.compression.port import Compressed
from wavestack.models.load_registry import COMPRESSOR
from wavestack.session.app_session import AppSession
from wavestack.trace.journal import get_journal

LOG = (config.content_dir() / "demo_files" / "journal_serveur.log").read_text(encoding="utf-8")
ERROR_LINE = next(line for line in LOG.splitlines() if " ERROR " in line)


class FakeCompressor:
    """As Headroom without Kompress: a log (INFO lines, more than 5) keeps its WARN and ERROR
    lines and says how many it left out; prose comes back as it was. `fail`: raises."""

    label_fr = "Faux compresseur"

    def __init__(self, *, fail: bool = False) -> None:
        self.fail = fail
        self.seen: list[str] = []
        self.closed = False

    def compress(self, text: str) -> Compressed:
        self.seen.append(text)
        if self.fail:
            raise ValueError("format inattendu")
        lines = text.splitlines()
        if len(lines) <= 5 or not any(" INFO " in line for line in lines):
            return Compressed(text)
        kept = [line for line in lines if " WARN " in line or " ERROR " in line]
        return Compressed("\n".join([*kept, f"[{len(lines) - len(kept)} lignes omises]"]), ("log",))

    def close(self) -> None:
        self.closed = True


class Compressors:
    """The session's `compressor_factory`: records each load; `gate` holds it."""

    def __init__(self, *, fail: bool = False, gate: threading.Event | None = None) -> None:
        self.made: list[FakeCompressor] = []
        self.fail, self.gate = fail, gate

    def __call__(self) -> FakeCompressor:
        if self.gate is not None:
            self.gate.wait(timeout=5)
        compressor = FakeCompressor(fail=self.fail)
        self.made.append(compressor)
        return compressor


def session_with(
    outputs: list[str],
    *,
    bricks: tuple[str, ...] = ("tools", "compression"),
    compressors: Compressors | None = None,
    values: dict | None = None,
    rss: int | None = None,
) -> tuple[AppSession, Compressors, FakeEngine]:
    compressors = compressors or Compressors()
    engine = FakeEngine(outputs=outputs, template=QWEN.decode("utf-8"), architecture="qwen35")
    session = AppSession(
        config.Config(values=values or {"context": {"window": 8192, "near_limit_ratio": 0.8}}),
        engine_factory=lambda path, n_ctx: engine,
        compressor_factory=compressors,
        rss_fn=(lambda: rss) if rss is not None else None,
    )
    session.boot("fake.gguf").result()
    for brick in bricks:
        session.set_brick(brick, True)
    session.join()
    return session, compressors, engine


def card(session: AppSession, brick: str = "compression") -> dict:
    session.join()
    changed = [e for e in get_journal().all_events() if e.kind == "bricks_changed"]
    return next(b for b in changed[-1].payload["bricks"] if b["id"] == brick)


def _kind(ctx: dict, kind: str) -> list[dict]:
    return [s for s in ctx["segments"] if s["kind"] == kind]


def _envelopes(mark: int, kind: str):
    return [e for e in get_journal().events_since(mark) if e.kind == kind]


# ---------- I/O matrix ----------


def test_big_tool_result_is_compressed_once_before_the_next_call():
    session, compressors, engine = session_with(
        [call("read_file", path="journal_serveur.log"), "Le disque est plein."]
    )
    mark = get_journal().last_seq()

    events = _run(session, "Lis le fichier journal_serveur.log")

    assert events["turn_ended"][0]["status"] == "completed"
    first, second = events["context_rendered"]
    assert "compressed_from" not in json.dumps(first)  # nothing to compress before call 1
    started, ended = events["compression_started"][0], events["compression_ended"][0]
    assert started["items"] == 1 and started["compressor_fr"] == "Faux compresseur"
    assert ended["status"] == "ok" and ended["error_fr"] is None
    item = ended["items"][0]
    assert item["source_fr"] == "Résultat de l'outil « read_file »"
    assert (item["kind"], item["brick"], item["component"]) == (
        "tool_result",
        "tools",
        "tools.read_file",
    )
    assert item["changed"] and item["text_before"] == LOG and ERROR_LINE in item["text_after"]
    # The session counts the tokens itself (fake engine: one per byte).
    assert item["tokens_before"] == len(LOG.encode())
    assert item["tokens_after"] == len(item["text_after"].encode()) < item["tokens_before"]
    assert ended["saved_tokens"] == ended["tokens_before"] - ended["tokens_after"] > 0

    # The step: the harness's own, between the tool and the second call.
    order = [
        e
        for e in get_journal().events_since(mark)
        if e.kind in ("tool_ended", "compression_started", "compression_ended", "context_rendered")
    ]
    assert [e.kind for e in order] == [
        "context_rendered",
        "tool_ended",
        "compression_started",
        "compression_ended",
        "context_rendered",
    ]
    step = order[2]
    assert (step.brick, step.component, step.actor, step.trigger) == (
        "compression",
        "compression.compressor",
        "harness",
        "harness",
    )
    assert step.step_id == order[3].step_id and step.step_id.endswith(".main.s3")

    # The call reads the compressed reply, which keeps its kind, brick and component.
    [result] = _kind(second, "tool_result")
    assert result["text"] == item["text_after"] and result["component"] == "tools.read_file"
    assert result["compressed_from"] == {"tokens_before": len(LOG.encode()), "text_before": LOG}
    assert second["uncompressed_used"] == second["used"] + len(LOG.encode()) - result["tokens"]
    assert LOG not in bytes(engine.calls[1]).decode()
    assert len(compressors.made[0].seen) == 1  # compressed once, when it entered


def test_history_keeps_the_compressed_text_and_never_compresses_it_again():
    session, compressors, _ = session_with(
        [call("read_file", path="journal_serveur.log"), "Disque plein.", "Au revoir."],
        bricks=("tools", "compression", "short_memory"),
    )
    _run(session, "Lis le fichier journal_serveur.log")
    seen = len(compressors.made[0].seen)

    events = _run(session, "Merci")

    assert "compression_started" not in events and len(compressors.made[0].seen) == seen
    [ctx] = events["context_rendered"]
    history = " ".join(s["text"] for s in _kind(ctx, "history"))
    assert ERROR_LINE in history and "lignes omises" in history and LOG not in history
    assert "compressed_from" not in json.dumps(ctx) and "uncompressed_used" not in ctx


def test_forced_action_is_compressed_before_the_first_call():
    session, _, _ = session_with(["Le disque est plein."])
    session.arm("tool", "read_file", {"path": "journal_serveur.log"})

    events = _run(session, "Que dit ce journal ?")

    [ctx] = events["context_rendered"]
    [result] = _kind(ctx, "tool_result")
    assert result["compressed_from"]["text_before"] == LOG and ERROR_LINE in result["text"]
    assert events["compression_ended"][0]["items"][0]["source_fr"].endswith("« read_file »")


def test_rag_excerpts_are_candidates_but_prose_passes_unchanged(tmp_path):
    index = tmp_path / "rag_index.sqlite"
    build(index)
    place_model()
    compressors = Compressors()
    engine = FakeEngine(output="Quatorze caractères.")
    values = rag_config(index) | {"compression": {"min_chars": 300}}
    session = AppSession(
        config.Config(values=values),
        engine_factory=lambda path, n_ctx: engine,
        embedder_factory=Embedders(),
        compressor_factory=compressors,
    )
    session.boot("fake.gguf").result()
    for brick in ("rag", "compression"):
        session.set_brick(brick, True)
    session.join()

    events = _run(session, "Combien de caractères pour un mot de passe chez Exemplia ?")

    [ctx] = events["context_rendered"]
    excerpts = _kind(ctx, "rag_excerpt")
    ended = events["compression_ended"][0]
    intro = excerpts[0]["text"]
    assert 1 <= len(ended["items"]) <= 3  # the excerpts long enough, never the intro
    assert all(len(i["text_before"]) >= 300 and i["text_before"] != intro for i in ended["items"])
    assert {i["kind"] for i in ended["items"]} == {"rag_excerpt"}
    assert ended["items"][0]["source_fr"].startswith("Extrait RAG n° ")
    assert all(not i["changed"] and i["text_after"] == i["text_before"] for i in ended["items"])
    assert ended["saved_tokens"] == 0 and ended["status"] == "ok"
    assert all("compressed_from" not in s for s in excerpts) and "uncompressed_used" not in ctx


def test_small_result_makes_no_step():
    session, compressors, _ = session_with([call("get_datetime"), "Il est midi."])

    events = _run(session, "Quelle heure est-il ?")

    assert events["turn_ended"][0]["status"] == "completed"
    assert "compression_started" not in events and "compression_ended" not in events
    assert len(compressors.made[0].seen) == 0


def test_meta_tools_hook_refusals_errors_and_subagent_results_are_never_candidates():
    session, _, _ = session_with(["OK"], values={"compression": {"min_chars": 0}})
    long = "x" * 50
    base = {"role": "tool", "id": "abc", "content": long, "brick": "tools"}
    assert session._compressible(base | {"name": "read_file", "component": "tools.read_file"})
    refused = [
        base | {"name": "load_skill", "component": "skills.caveman", "kind": "skill_body"},
        base | {"name": "load_tool_doc", "component": "mcp.local", "brick": "mcp"},
        base | {"name": "remember", "component": "file.memory", "brick": "global_memory"},
        base
        | {
            "name": "delegate",
            "component": "subagent.agent",
            "brick": "subagent",
            "kind": "subagent_result",
        },
        base | {"name": "read_file", "component": "hooks.h1", "brick": "hooks"},
        base | {"name": "read_file", "component": "core.harness"},  # refused by the harness
        base | {"name": None, "id": None, "component": "core.harness"},  # malformed call
    ]
    assert [session._compressible(step) for step in refused] == [False] * len(refused)


def test_hook_refusal_is_not_compressed():
    session, _, _ = session_with(
        [call("read_file", path="confidentiel/budget_projet.txt"), "Je ne peux pas."],
        bricks=("tools", "hooks", "compression"),
        values={"compression": {"min_chars": 0}},
    )
    session.set_hook("h1", True)
    session.join()

    events = _run(session, "Lis le budget confidentiel")

    assert "Bloqué par le hook" in _kind(events["context_rendered"][1], "tool_result")[0]["text"]
    assert "compression_started" not in events


def test_headroom_missing_or_another_version_makes_the_brick_unavailable(monkeypatch):
    monkeypatch.setattr(headroom_adapter.importlib.util, "find_spec", lambda name: None)
    reason = headroom_adapter.missing_fr()
    assert "uv sync --extra compression" in reason and "0.38.0" in reason

    engine = FakeEngine(output="Bonjour")
    session = AppSession(
        config.Config(values={}), engine_factory=lambda path, n_ctx: engine
    )  # the default adapter: Headroom
    session.boot("fake.gguf").result()
    session.set_brick("compression", True)
    compression = card(session)
    assert compression["wanted"] and not compression["available"]
    assert compression["reason_fr"] == reason
    assert _run(session, "Bonjour")["turn_ended"][0]["status"] == "completed"

    monkeypatch.undo()
    monkeypatch.setattr(headroom_adapter.importlib.util, "find_spec", lambda name: object())
    monkeypatch.setattr(headroom_adapter.importlib.metadata, "version", lambda name: "0.39.0")
    other = headroom_adapter.missing_fr()
    assert "0.39.0" in other and "0.38.0" in other and "uv sync --extra compression" in other


def test_budget_refusal_loads_nothing():
    compressors = Compressors()
    session, _, _ = session_with(
        ["OK"], compressors=compressors, rss=4096 * 1024 * 1024, bricks=("compression",)
    )

    compression = card(session)
    assert not compression["available"] and "Mémoire insuffisante" in compression["reason_fr"]
    assert "environ 130 de plus" in compression["reason_fr"] and compressors.made == []
    assert session._load_registry.holder(COMPRESSOR) is None


def test_compressor_failure_keeps_the_original_and_the_turn_ends():
    session, _, _ = session_with(
        [call("read_file", path="journal_serveur.log"), "Je lis le journal."],
        compressors=Compressors(fail=True),
    )

    events = _run(session, "Lis le fichier journal_serveur.log")

    assert events["turn_ended"][0]["status"] == "completed"
    ended = events["compression_ended"][0]
    assert ended["status"] == "error" and "ValueError" in ended["error_fr"]
    assert not ended["items"][0]["changed"] and ended["saved_tokens"] == 0
    assert any("compression" in e["message_fr"] for e in events["harness_error"])
    [result] = _kind(events["context_rendered"][1], "tool_result")
    assert result["text"] == LOG.strip() and "compressed_from" not in result


def test_compression_alone_is_the_bare_llm_byte_for_byte():
    bare, _, bare_engine = session_with(["Bonjour !"], bricks=())
    alone, compressors, engine = session_with(["Bonjour !"], bricks=("compression",))

    events = _run(alone, "Bonjour")
    _run(bare, "Bonjour")

    assert card(alone)["available"] and compressors.made  # loaded, yet nothing to compress
    assert "compression_started" not in events and engine.calls == bare_engine.calls


# ---------- loading, card, schema ----------


def test_loading_then_release_through_the_registry():
    gate = threading.Event()
    compressors = Compressors(gate=gate)
    session, _, _ = session_with(["OK"], compressors=compressors, bricks=())
    mark = get_journal().last_seq()
    session.set_brick("compression", True)
    loading = [
        b
        for e in _envelopes(mark, "bricks_changed")
        for b in e.payload["bricks"]
        if b["id"] == "compression"
    ][-1]
    assert not loading["available"] and loading["reason_fr"].startswith("Chargement de Headroom")
    gate.set()
    compression = card(session)
    assert compression["available"] and compression["reason_fr"] is None
    assert "300 caractères" in compression["limits_fr"]
    assert session._load_registry.holder(COMPRESSOR) == "Headroom 0.38.0"

    session.set_brick("compression", False)
    session.join()
    assert compressors.made[0].closed and session._load_registry.holder(COMPRESSOR) is None


def test_schema_draws_the_compressor_in_the_harness_process():
    session, _, _ = session_with(["OK"], bricks=("compression",))
    session._emit_architecture()
    nodes = [e for e in get_journal().all_events() if e.kind == "architecture_changed"]
    node = next(n for n in nodes[-1].payload["nodes"] if n["id"] == "compression.compressor")
    assert node["hosting"] == "local" and "Headroom 0.38.0" in node["detail_fr"]


# ---------- chat mode ----------


def test_chat_mode_sends_the_compressed_reply_with_estimated_tokens():
    read = sse(
        delta(
            tool_calls=[
                {
                    "index": 0,
                    "id": "call_p",
                    "type": "function",
                    "function": {
                        "name": "read_file",
                        "arguments": '{"path": "journal_serveur.log"}',
                    },
                }
            ]
        ),
        {
            **delta("tool_calls"),
            "x_groq": {"usage": {"prompt_tokens": 900, "completion_tokens": 9}},
        },
    )
    text = sse(
        delta(content="Disque plein."),
        {**delta("stop"), "x_groq": {"usage": {"prompt_tokens": 800, "completion_tokens": 4}}},
    )
    provider = Provider(read, text)
    cfg = config.load_config()
    entry = cfg.cloud_model("groq")
    config.write_api_key(entry.id, entry.host, SecretStr(SENTINEL))
    session = AppSession(cfg, cloud_factory=provider.factory, compressor_factory=Compressors())
    session.boot_cloud(entry).result()
    for brick in ("tools", "compression"):
        session.set_brick(brick, True)
    session.join()

    events = _run(session, "Lis le fichier journal_serveur.log")

    ended = events["compression_ended"][0]
    assert ended["estimated"] and ended["items"][0]["changed"]
    second = json.loads(provider.requests[1].content)["messages"]
    reply = next(m for m in second if m["role"] == "tool")
    assert reply["content"] == ended["items"][0]["text_after"] and LOG not in reply["content"]
    assert (
        events["context_rendered"][1]["uncompressed_used"] > events["context_rendered"][1]["used"]
    )


# ---------- offline variables, content, the real adapter ----------


def test_offline_variables_are_set_and_win_over_the_environment(monkeypatch):
    monkeypatch.setenv("HEADROOM_BEACON", "on")
    compression_env.apply_offline_env()
    for name, value in compression_env.OFFLINE_ENV.items():
        assert os.environ[name] == value
    cache = compression_env.tiktoken_cache_dir()
    if cache is not None:
        assert os.environ["TIKTOKEN_CACHE_DIR"] == str(cache)


def test_cli_sets_the_offline_variables_before_third_party_imports():
    source = (config.repo_root() / "src" / "wavestack" / "cli.py").read_text(encoding="utf-8")
    assert source.index("_headroom_offline()") < source.index("import truststore")


def test_scenario_compression_closes_the_programme():
    scenarios = (config.content_dir() / "scenarios.yaml").read_text(encoding="utf-8")
    assert scenarios.index("scenarios: [rag]") < scenarios.index("scenarios: [compression]")
    assert ERROR_LINE in LOG and len(LOG.splitlines()) >= 50


@pytest.mark.skipif(
    importlib.util.find_spec("headroom") is None, reason="headroom-ai (extra) absent"
)
def test_headroom_adapter_compresses_the_demo_log_offline():
    compressor = headroom_adapter.HeadroomCompressor()  # the network guard is installed

    result = compressor.compress(LOG)
    prose = "La politique de mots de passe impose quatorze caractères au minimum. " * 5

    assert len(result.text) < len(LOG) / 2 and ERROR_LINE in result.text
    assert compressor.compress(prose).text.strip() == prose.strip()
    assert os.environ["HEADROOM_OFFLINE"] == "1"
