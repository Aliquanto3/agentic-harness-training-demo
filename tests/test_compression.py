"""Story 20: context compression (AD-4 `transform_context`, AD-8, AD-22).

The session's tests inject `FakeCompressor`: none needs headroom-ai, an optional dependency.
Only `test_headroom_adapter_*` runs the real library, skipped when it is not installed.
"""

from __future__ import annotations

import hashlib
import importlib.util
import inspect
import ipaddress
import json
import os
import re
import shutil
import subprocess
import sys
import threading

import httpx
import pytest
from fake_engine import FakeEngine
from pydantic import SecretStr
from test_cloud import SENTINEL, Provider, delta, sse
from test_rag import Embedders, build, place_model, rag_config
from test_tools import QWEN, call, web  # noqa: F401 - `web`: the network tools' fixture
from test_turn import _run

from wavestack import config
from wavestack.compression import env as compression_env
from wavestack.compression import headroom_adapter
from wavestack.compression.port import Compressed, CompressionContent
from wavestack.models.load_registry import COMPRESSOR, ModelChoice
from wavestack.session import app_session as app_session_module
from wavestack.session.app_session import AppSession
from wavestack.tools.registry import ToolSpec
from wavestack.trace.journal import get_journal

LOG = (config.content_dir() / "demo_files" / "journal_serveur.log").read_text(encoding="utf-8")
ERROR_LINE = next(line for line in LOG.splitlines() if " ERROR " in line)
ORIGINAL = LOG.strip()  # what the step keeps as the text before (outer blanks off)


class FakeCompressor:
    """As Headroom without Kompress: a log (INFO lines, more than 5) keeps its WARN and ERROR
    lines and says how many it left out; prose comes back as it was. `fail`: raises."""

    label_text = "Faux compresseur"

    def __init__(self, *, fail: bool = False, prose: bool = False) -> None:
        self.fail, self.prose = fail, prose
        self.seen: list[str] = []
        self.closed = False

    def compress(self, text: str) -> Compressed:
        self.seen.append(text)
        if self.fail:
            raise ValueError("format inattendu")
        if self.prose:  # a compressor that shortens prose too (not Headroom without Kompress)
            return Compressed(text[:120] + " […]", ("prose",))
        lines = text.splitlines()
        if len(lines) <= 5 or not any(" INFO " in line for line in lines):
            return Compressed(text)
        kept = [line for line in lines if " WARN " in line or " ERROR " in line]
        return Compressed("\n".join([*kept, f"[{len(lines) - len(kept)} lignes omises]"]), ("log",))

    def close(self) -> None:
        self.closed = True


class Compressors:
    """The session's `compressor_factory`: records each load; `gate` holds it."""

    def __init__(
        self, *, fail: bool = False, prose: bool = False, gate: threading.Event | None = None
    ) -> None:
        self.made: list[FakeCompressor] = []
        self.fail, self.prose, self.gate = fail, prose, gate

    def __call__(self) -> FakeCompressor:
        if self.gate is not None:
            self.gate.wait(timeout=5)
        compressor = FakeCompressor(fail=self.fail, prose=self.prose)
        self.made.append(compressor)
        return compressor


def session_with(
    outputs: list[str],
    *,
    bricks: tuple[str, ...] = ("tools", "compression"),
    compressors: Compressors | None = None,
    values: dict | None = None,
    rss: int | None = None,
    rss_fn=None,  # noqa: ANN001
) -> tuple[AppSession, Compressors, FakeEngine]:
    compressors = compressors or Compressors()
    engine = FakeEngine(outputs=outputs, template=QWEN.decode("utf-8"), architecture="qwen35")
    window = {"context": {"window": 8192, "near_limit_ratio": 0.8}}
    session = AppSession(
        config.Config(values=window | (values or {})),
        engine_factory=lambda path, n_ctx: engine,
        compressor_factory=compressors,
        rss_fn=rss_fn or ((lambda: rss) if rss is not None else None),
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


def _text_before(events: dict, compressed_from: dict) -> str:
    """The text before, kept once by the compression step the segment names."""
    ended = [
        e
        for e in get_journal().all_events()
        if e.kind == "compression_ended" and e.step_id == compressed_from["step_id"]
    ]
    return ended[-1].payload["items"][compressed_from["item"]]["text_before"]


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
    assert started["items"] == 1 and started["compressor_text"] == "Faux compresseur"
    assert ended["status"] == "ok" and ended["error_text"] is None
    item = ended["items"][0]
    assert item["source_text"] == "Résultat de l'outil « read_file »"
    assert (item["kind"], item["brick"], item["component"]) == (
        "tool_result",
        "tools",
        "tools.read_file",
    )
    assert item["changed"] and item["text_before"] == ORIGINAL
    assert ERROR_LINE in item["text_after"]
    # The session counts the tokens itself (fake engine: one per byte).
    assert item["tokens_before"] == len(ORIGINAL.encode())
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
    # The original is traced once, in the step: the segment points at it.
    assert result["compressed_from"] == {
        "tokens_before": len(ORIGINAL.encode()),
        "estimated": False,
        "step_id": step.step_id,
        "item": 0,
    }
    assert _text_before(events, result["compressed_from"]) == ORIGINAL
    assert ORIGINAL not in json.dumps(second, ensure_ascii=False)
    assert second["uncompressed_used"] == second["used"] + len(ORIGINAL.encode()) - result["tokens"]
    assert ORIGINAL not in bytes(engine.calls[1]).decode()
    assert len(compressors.made[0].seen) == 1  # compressed once, when it entered
    # Append only (AD-4): the second call extends the first, token for token.
    assert engine.calls[1][: len(engine.calls[0])] == engine.calls[0]
    assert "prefix_not_reused" not in events


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
    assert _text_before(events, result["compressed_from"]) == ORIGINAL
    assert ERROR_LINE in result["text"]
    assert events["compression_ended"][0]["items"][0]["source_text"].endswith("« read_file »")


def rag_compression_session(tmp_path, compressors: Compressors, outputs=None):  # noqa: ANN001
    index = tmp_path / "rag_index.sqlite"
    build(index)
    place_model()
    engine = FakeEngine(
        outputs=outputs or ["Quatorze caractères."],
        template=QWEN.decode("utf-8"),
        architecture="qwen35",
    )
    values = rag_config(index, window=16384) | {"compression": {"min_chars": 300}}
    session = AppSession(
        config.Config(values=values),
        engine_factory=lambda path, n_ctx: engine,
        embedder_factory=Embedders(),
        compressor_factory=compressors,
    )
    session.boot("fake.gguf").result()
    for brick in ("tools", "rag", "compression"):
        session.set_brick(brick, True)
    session.join()
    return session, engine


def test_rag_excerpts_are_candidates_but_prose_passes_unchanged(tmp_path):
    session, _ = rag_compression_session(tmp_path, Compressors())

    events = _run(session, "Combien de caractères pour un mot de passe chez Exemplia ?")

    [ctx] = events["context_rendered"]
    excerpts = _kind(ctx, "rag_excerpt")
    ended = events["compression_ended"][0]
    intro = excerpts[0]["text"]
    assert 1 <= len(ended["items"]) <= 3  # the excerpts long enough, never the intro
    assert all(len(i["text_before"]) >= 300 and i["text_before"] != intro for i in ended["items"])
    assert {i["kind"] for i in ended["items"]} == {"rag_excerpt"}
    assert ended["items"][0]["source_text"].startswith("Extrait RAG n° ")
    assert all(not i["changed"] and i["text_after"] is None for i in ended["items"])
    assert ended["saved_tokens"] == 0 and ended["status"] == "ok"
    assert all("compressed_from" not in s for s in excerpts) and "uncompressed_used" not in ctx


def test_small_result_makes_no_step():
    session, compressors, _ = session_with([call("get_datetime"), "Il est midi."])

    events = _run(session, "Quelle heure est-il ?")

    assert events["turn_ended"][0]["status"] == "completed"
    assert "compression_started" not in events and "compression_ended" not in events
    assert len(compressors.made[0].seen) == 0


def test_eligibility_is_decided_when_the_reply_is_made():
    session, _, _ = session_with(["OK"], values={"compression": {"min_chars": 0}})
    text = "x" * 50
    reply = session._reply_step
    native = session._registry.get("read_file")
    network = session._registry.get("fetch_page")
    mcp = ToolSpec(
        name="local__define_term",
        run=lambda **kw: text,
        params={"term": "string"},
        component="mcp.local",
        source="mcp_local",
    )
    kept = [
        reply("a", "read_file", text, "tools.read_file", "tools", None, native),
        reply("b", "fetch_page", text, "tools.fetch_page", "tools", None, network),
        reply("c", "local__define_term", text, "mcp.local", "mcp", None, mcp),
    ]
    assert [session._compressible(step) for step in kept] == [True, True, True]
    harness = session._registry.get("load_skill") or session._registry.get("remember")
    refused = [
        reply("d", "read_file", text, "tools.read_file", "tools", "h1", native),  # a hook
        reply("e", "read_file", text, "core.harness", "tools", None, None),  # the harness
        reply("f", "load_skill", text, "skills.caveman", "skills", None, harness),  # meta-tool
        reply("g", "delegate", text, "subagent.agent", "subagent", None, None),  # sub-agent
        {"role": "tool", "name": None, "content": text, "component": "core.harness"},
    ]
    assert [session._compressible(step) for step in refused] == [False] * len(refused)


def test_network_and_mcp_outputs_are_compressed(web):  # noqa: F811
    page = "\n".join(f"2026-09-21 02:{i:02d}:00 INFO page {i}" for i in range(40))
    page += "\n2026-09-21 03:00:00 ERROR page introuvable"
    web(lambda r: httpx.Response(200, text=page, headers={"content-type": "text/plain"}))
    session, compressors, _ = session_with(
        [call("fetch_page", url="https://fr.wikipedia.org/wiki/Paris"), "Voilà."],
        # Lot B: the fake engine counts a token per byte; the whole page reaches the compressor.
        values={"tools": {"result_max_tokens": 4000}},
    )
    session.set_tool("fetch_page", True)
    session.join()

    events = _run(session, "Lis la page Paris")

    [item] = events["compression_ended"][0]["items"]
    assert item["source_text"] == "Résultat de l'outil « fetch_page »" and item["changed"]
    assert (item["brick"], item["component"]) == ("tools", "tools.fetch_page")
    assert "page introuvable" in item["text_after"]


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
    monkeypatch.setattr(headroom_adapter, "_find_spec", lambda name: None)
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
    assert compression["reason_text"] == reason
    assert _run(session, "Bonjour")["turn_ended"][0]["status"] == "completed"

    monkeypatch.setattr(headroom_adapter, "_find_spec", lambda name: object())
    monkeypatch.setattr(headroom_adapter, "_version", lambda name: "0.39.0")
    other = headroom_adapter.missing_fr()
    assert "0.39.0" in other and "0.38.0" in other and "uv sync --extra compression" in other


def test_budget_refusal_loads_nothing():
    compressors = Compressors()
    session, _, _ = session_with(
        ["OK"], compressors=compressors, rss=4096 * 1024 * 1024, bricks=("compression",)
    )

    compression = card(session)
    assert not compression["available"] and "Mémoire insuffisante" in compression["reason_text"]
    assert "environ 110 de plus" in compression["reason_text"] and compressors.made == []
    assert session._load_registry.holder(COMPRESSOR) is None


def test_budget_refusal_names_the_compressor_in_the_case_of_its_sentence():
    """The factory without a label (Headroom always has one): the generic noun, in German
    the object of « laden » (accusative), the schema's detail keeping the subject."""
    session, _, _ = session_with(
        ["OK"],
        rss=4096 * 1024 * 1024,
        bricks=("compression",),
        values={"language": "de"},
    )
    reason = card(session)["reason_text"]
    assert "um den Kompressor zu laden" in reason and "der Kompressor zu laden" not in reason
    assert session._compressor_label() == "der Kompressor"
    assert session._compressor_label(to_load=True) == "den Kompressor"


def test_compressor_failure_keeps_the_original_and_the_turn_ends():
    session, _, _ = session_with(
        [call("read_file", path="journal_serveur.log"), "Je lis le journal."],
        compressors=Compressors(fail=True),
    )

    events = _run(session, "Lis le fichier journal_serveur.log")

    assert events["turn_ended"][0]["status"] == "completed"
    ended = events["compression_ended"][0]
    assert ended["status"] == "error" and "ValueError" in ended["error_text"]
    assert not ended["items"][0]["changed"] and ended["saved_tokens"] == 0
    assert any("compression" in e["message_text"] for e in events["harness_error"])
    [result] = _kind(events["context_rendered"][1], "tool_result")
    assert result["text"] == ORIGINAL and "compressed_from" not in result
    assert ended["items"][0]["text_after"] is None


def test_compression_alone_is_the_bare_llm_byte_for_byte():
    bare, _, bare_engine = session_with(["Bonjour !"], bricks=())
    alone, compressors, engine = session_with(["Bonjour !"], bricks=("compression",))

    events = _run(alone, "Bonjour")
    _run(bare, "Bonjour")

    assert card(alone)["available"] and compressors.made  # loaded, yet nothing to compress
    assert "compression_started" not in events and engine.calls == bare_engine.calls


def test_three_calls_a_reply_already_read_is_never_compressed_again():
    session, compressors, engine = session_with(
        [
            call("read_file", path="journal_serveur.log"),
            call("get_datetime"),
            "Le disque était plein à 2 h 45.",
        ]
    )

    events = _run(session, "Lis journal_serveur.log puis donne l'heure")

    assert events["turn_ended"][0]["status"] == "completed"
    assert len(events["compression_started"]) == 1 and len(compressors.made[0].seen) == 1
    _, second, third = events["context_rendered"]
    journal = [s for s in _kind(second, "tool_result") if s["component"] == "tools.read_file"]
    again = [s for s in _kind(third, "tool_result") if s["component"] == "tools.read_file"]
    assert [s["text"] for s in journal] == [s["text"] for s in again]
    assert journal[0]["compressed_from"] == again[0]["compressed_from"]
    for before, after in zip(engine.calls, engine.calls[1:], strict=False):  # append only
        assert after[: len(before)] == before
    assert "prefix_not_reused" not in events


def test_rag_excerpts_are_offered_once_then_only_the_new_tool_output(tmp_path):
    session, _ = rag_compression_session(
        tmp_path,
        Compressors(),
        [call("read_file", path="journal_serveur.log"), "Le disque était plein."],
    )

    events = _run(session, "Lis le fichier journal_serveur.log")

    first, second = events["compression_ended"]
    assert {i["kind"] for i in first["items"]} == {"rag_excerpt"}
    assert [i["kind"] for i in second["items"]] == ["tool_result"]


def test_a_shortened_rag_excerpt_is_rendered_compressed(tmp_path):
    session, _ = rag_compression_session(tmp_path, Compressors(prose=True))

    events = _run(session, "Combien de caractères pour un mot de passe chez Exemplia ?")

    [ctx] = events["context_rendered"]
    items = events["compression_ended"][0]["items"]
    compressed = [s for s in _kind(ctx, "rag_excerpt") if "compressed_from" in s]
    assert compressed and len(compressed) == len([i for i in items if i["changed"]])
    for segment in compressed:
        assert segment["text"].endswith("[…]") and segment["brick"] == "rag"
        before = _text_before(events, segment["compressed_from"])
        assert len(before) > len(segment["text"])
        assert segment["compressed_from"]["tokens_before"] == len(before.encode())
    assert ctx["uncompressed_used"] > ctx["used"]


class Blanks(FakeCompressor):
    """Gives the text back with other outer blanks, and no transforms."""

    def compress(self, text: str) -> Compressed:
        self.seen.append(text)
        return Compressed("\n  " + text.strip() + "  \n", None)  # type: ignore[arg-type]


def test_outer_blanks_alone_are_no_compression():
    session, _, _ = session_with(
        [call("read_file", path="journal_serveur.log"), "OK"],
        compressors=lambda: Blanks(),  # type: ignore[arg-type]
    )

    events = _run(session, "Lis le fichier journal_serveur.log")

    [item] = events["compression_ended"][0]["items"]
    assert not item["changed"] and item["transforms"] == [] and item["text_after"] is None


def test_a_stop_between_two_texts_still_ends_the_step(tmp_path):
    holder: dict[str, AppSession] = {}

    class Stopper(FakeCompressor):
        def compress(self, text: str) -> Compressed:
            self.seen.append(text)
            holder["session"].stop()  # « Arrêter » while Headroom works
            return Compressed(text[:100])

    made: list[Stopper] = []

    def factory() -> Stopper:
        made.append(Stopper())
        return made[-1]

    session, _ = rag_compression_session(tmp_path, factory)  # type: ignore[arg-type]
    holder["session"] = session

    events = _run(session, "Combien de caractères pour un mot de passe chez Exemplia ?")

    assert events["turn_ended"][0]["status"] == "cancelled"
    assert len(made[0].seen) == 1 and len(events["compression_ended"][0]["items"]) == 1
    assert "context_rendered" not in events  # no call after the stop


def test_invalid_content_makes_the_brick_unavailable_with_the_file(monkeypatch):
    def broken():
        raise ValueError("gabarit invalide")

    monkeypatch.setattr(app_session_module, "load_compression_content", broken)
    session, compressors, _ = session_with(["OK"], bricks=("compression",))

    compression = card(session)
    assert not compression["available"] and "content/compression.yaml" in compression["reason_text"]
    assert compressors.made == []


def test_templates_with_an_unknown_placeholder_are_refused():
    good = {
        "phase_label_text": "Compression…",
        "step_title_text": "Compression",
        "tool_source_text": "Outil {tool}",
        "rag_source_text": "Extrait {n}",
        "unchanged_text": "Inchangé.",
        "limits_text": "Au moins {min_chars} caractères.",
    }
    CompressionContent.model_validate(good)
    with pytest.raises(ValueError, match="tool_source_text"):
        CompressionContent.model_validate(good | {"tool_source_text": "Outil {outil}"})
    with pytest.raises(ValueError, match="limits_text"):
        CompressionContent.model_validate(good | {"limits_text": "Seuil {"})


def test_switching_on_again_counts_the_library_once():
    rss = {"now": 100 * 1024**2}
    session, compressors, _ = session_with(
        ["OK"], bricks=("compression",), rss_fn=lambda: rss["now"]
    )
    assert card(session)["available"]
    session.set_brick("compression", False)
    session.join()

    rss["now"] = 4096 * 1024**2 - 10 * 1024**2  # Headroom's memory stays in the RSS measured
    session.set_brick("compression", True)

    assert card(session)["available"] and len(compressors.made) == 2
    assert session._load_registry.holder(COMPRESSOR) == "Faux compresseur"


def test_switching_the_brick_off_while_it_loads_closes_the_compressor():
    entered, gate = threading.Event(), threading.Event()
    compressors = Compressors(gate=gate)

    def slow() -> FakeCompressor:
        entered.set()
        return compressors()

    session, _, _ = session_with(["OK"], compressors=slow, bricks=())  # type: ignore[arg-type]
    session.set_brick("compression", True)
    assert entered.wait(5)  # the worker is loading it
    session.set_brick("compression", False)
    gate.set()
    session.join()

    assert compressors.made[0].closed and session._compressor is None
    assert session._load_registry.holder(COMPRESSOR) is None


def test_a_budget_refusal_is_retried_after_a_model_switch(tmp_path):
    rss = {"now": 4096 * 1024**2}
    session, compressors, _ = session_with(
        ["OK"], bricks=("compression",), rss_fn=lambda: rss["now"]
    )
    assert "Mémoire insuffisante" in card(session)["reason_text"] and compressors.made == []

    rss["now"] = 100 * 1024**2  # the switch frees memory
    other = tmp_path / "other.gguf"
    other.write_bytes(b"\0" * 10)
    _, future = session.switch_model(ModelChoice("file", str(other)))
    future.result()
    session.join()

    assert card(session)["available"] and len(compressors.made) == 1


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
    assert not loading["available"] and loading["reason_text"] == "Chargement du compresseur…"
    gate.set()
    compression = card(session)
    assert compression["available"] and compression["reason_text"] is None
    assert "300 caractères" in compression["limits_text"]
    assert session._load_registry.holder(COMPRESSOR) == "Faux compresseur"

    session.set_brick("compression", False)
    session.join()
    assert compressors.made[0].closed and session._load_registry.holder(COMPRESSOR) is None


def test_schema_draws_the_compressor_in_the_harness_process():
    session, _, _ = session_with(["OK"], bricks=("compression",))
    session._emit_architecture()
    nodes = [e for e in get_journal().all_events() if e.kind == "architecture_changed"]
    node = next(n for n in nodes[-1].payload["nodes"] if n["id"] == "compression.compressor")
    # The loaded compressor's own label, not the Headroom class's.
    assert node["hosting"] == "local" and "Faux compresseur" in node["detail_text"]


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


_TIKTOKEN_ENV = ("TIKTOKEN_CACHE_DIR", "CUSTOM_TIKTOKEN_CACHE_DIR")


def _forget_offline_env(monkeypatch) -> None:  # noqa: ANN001
    """Unset every variable the adapter sets; monkeypatch puts them back afterwards."""
    for name in (*compression_env.OFFLINE_ENV, *_TIKTOKEN_ENV, "HF_HUB_OFFLINE"):
        monkeypatch.delenv(name, raising=False)


def test_offline_variables_are_set_and_win_over_the_environment(monkeypatch):
    _forget_offline_env(monkeypatch)
    monkeypatch.setenv("HEADROOM_BEACON", "on")
    compression_env.apply_offline_env()
    for name, value in compression_env.OFFLINE_ENV.items():
        assert os.environ[name] == value
    # Story 4: litellm rewrites TIKTOKEN_CACHE_DIR at its import, never CUSTOM_TIKTOKEN_CACHE_DIR.
    shipped = config.repo_root() / "src" / "wavestack" / "compression" / "tiktoken"
    assert compression_env.tiktoken_cache_dir() == shipped.resolve()
    for name in _TIKTOKEN_ENV:
        assert os.environ[name] == str(compression_env.tiktoken_cache_dir())


def test_shipped_cl100k_base_table_is_the_official_one():
    """Story 4: the bytes tiktoken checks (LF line endings, `expected_hash` of
    `tiktoken_ext/openai_public.py`), under the name of tiktoken's cache."""
    assert compression_env.CL100K_BASE_FILE == _tiktoken_file("cl100k_base")
    data = (compression_env.tiktoken_cache_dir() / compression_env.CL100K_BASE_FILE).read_bytes()
    assert b"\r" not in data
    # The hash tiktoken itself checks (it deletes a table that differs), read from its source.
    openai_public = pytest.importorskip("tiktoken_ext.openai_public")
    expected = re.findall(r"[0-9a-f]{64}", inspect.getsource(openai_public.cl100k_base))
    assert hashlib.sha256(data).hexdigest() == compression_env.CL100K_BASE_SHA256 == expected[0]
    assert compression_env.tiktoken_table_problem() is None
    license_file = compression_env.tiktoken_cache_dir() / "LICENSE-tiktoken"
    assert "MIT License" in license_file.read_text(encoding="utf-8")
    attributes = (config.repo_root() / ".gitattributes").read_text(encoding="utf-8")
    assert f"src/wavestack/compression/tiktoken/{compression_env.CL100K_BASE_FILE} -text" in (
        attributes
    )


@pytest.mark.parametrize("state", ["missing", "altered"])
def test_missing_or_altered_table_makes_the_brick_unavailable(state, tmp_path, monkeypatch):
    """Story 4: the brick says why, and Headroom (whose import would have tiktoken download
    the table) is never loaded."""
    if state == "altered":  # litellm 1.102.1's copy: the same table with CRLF line endings
        shipped = compression_env.tiktoken_cache_dir() / compression_env.CL100K_BASE_FILE
        data = shipped.read_bytes().replace(b"\n", b"\r\n")
        (tmp_path / compression_env.CL100K_BASE_FILE).write_bytes(data)
    monkeypatch.setattr(compression_env, "tiktoken_cache_dir", lambda: tmp_path)
    monkeypatch.setattr(headroom_adapter, "_find_spec", lambda name: object())
    monkeypatch.setattr(headroom_adapter, "_version", lambda name: "0.38.0")
    assert compression_env.tiktoken_table_problem() == state

    reason = headroom_adapter.missing_fr()
    assert reason is not None and "cl100k_base" in reason
    assert str(tmp_path / compression_env.CL100K_BASE_FILE) in reason
    assert ("absente" if state == "missing" else "altérée") in reason
    loaded = []
    monkeypatch.setattr(headroom_adapter, "HeadroomCompressor", lambda: loaded.append(1))

    engine = FakeEngine(output="Bonjour")
    session = AppSession(
        config.Config(values={}), engine_factory=lambda path, n_ctx: engine
    )  # the default adapter: Headroom
    session.boot("fake.gguf").result()
    session.set_brick("compression", True)
    compression = card(session)
    assert compression["wanted"] and not compression["available"]
    assert compression["reason_text"] == reason
    assert _run(session, "Bonjour")["turn_ended"][0]["status"] == "completed"
    assert loaded == []


def test_cli_sets_the_offline_variables_before_third_party_imports():
    source = (config.repo_root() / "src" / "wavestack" / "cli.py").read_text(encoding="utf-8")
    assert source.index("_headroom_offline()") < source.index("import truststore")


def test_scenario_compression_closes_the_programme():
    scenarios = (config.content_dir() / "scenarios.yaml").read_text(encoding="utf-8")
    # Story 21: FR-38's last brick, after the sub-agent, in the programme's last module.
    assert scenarios.index("scenarios: [rag, rag_rerank]") < scenarios.index(
        "scenarios: [subagent, compression]\n\ntransverse:"
    )
    lines = LOG.splitlines()
    assert ERROR_LINE in LOG and len(lines) >= 60  # Headroom sees a log from about 50 lines
    # A coherent night: every lot up to the error copied once, none after it.
    copied = [line for line in lines if " copié" in line and "lots copiés" not in line]
    assert [int(line.split("lot ")[1].split()[0]) for line in copied] == list(range(1, 58))
    after = lines[lines.index(ERROR_LINE) + 1 :]
    assert after and not any(re.search(r"lot \d+ copié", line) for line in after)


@pytest.mark.skipif(
    importlib.util.find_spec("headroom") is None, reason="headroom-ai (extra) absent"
)
def test_headroom_adapter_compresses_the_demo_log_offline(monkeypatch):
    _forget_offline_env(monkeypatch)
    compressor = headroom_adapter.HeadroomCompressor()  # the network guard is installed

    # The adapter set the variables itself; HF_HUB_OFFLINE only while Headroom ran.
    for name, value in compression_env.OFFLINE_ENV.items():
        assert os.environ[name] == value
    assert "HF_HUB_OFFLINE" not in os.environ
    hub = sys.modules.get("huggingface_hub.constants")
    assert hub is None or hub.HF_HUB_OFFLINE is True

    result = compressor.compress(LOG)
    prose = "La politique de mots de passe impose quatorze caractères au minimum. " * 5
    assert len(result.text) <= len(LOG) * 0.4 and ERROR_LINE in result.text  # measured: −73 %
    assert "lot 12 copié" not in result.text  # what is cut is lost for the model
    assert compressor.compress(prose).text.strip() == prose.strip()


# Child of the offline test: records every resolution or connection attempt (the recording hook
# first, as the bench's `_record_and_guard`: the guard raising must not hide it), installs the
# guard, sets the offline variables as `cli` does, then imports the adapter and compresses.
# argv: the log, the tiktoken cache to use in place of litellm's, optionally another counting
# model (the negative control).
_OFFLINE_CHILD = r"""
import json, os, sys
from pathlib import Path

attempts, phase = [], ["start"]


def record(event, args):
    if event == "socket.getaddrinfo":
        host = args[0]
        if host is None:  # passive lookup (a local bind), not a destination
            return
        if isinstance(host, bytes):
            host = host.decode("ascii", "replace")
        attempts.append([phase[0], event, str(host)])
    elif event == "socket.connect":
        address = args[1]
        if isinstance(address, tuple) and address:
            attempts.append([phase[0], event, str(address[0])])


sys.addaudithook(record)
import urllib.request

for lookup in ("getproxies_registry", "getproxies_macosx_sysconf"):  # the system's proxy
    if hasattr(urllib.request, lookup):
        setattr(urllib.request, lookup, lambda: {})
from wavestack.net.guard import install

install(allowed_hosts=[])
from wavestack.compression import env

env.tiktoken_cache_dir = lambda: Path(sys.argv[2])
env.apply_offline_env()
phase[0] = "import"
from wavestack.compression import headroom_adapter

if len(sys.argv) > 3:
    headroom_adapter.COUNTING_MODEL = sys.argv[3]
compressor = headroom_adapter.HeadroomCompressor()
phase[0] = "compression"
with open(sys.argv[1], encoding="utf-8") as f:
    log = f.read()
result = compressor.compress(log)
print(json.dumps({
    "attempts": attempts,
    "model": headroom_adapter.COUNTING_MODEL,
    "before": len(log),
    "text": result.text,
    "tiktoken_cache_dir": os.environ.get("TIKTOKEN_CACHE_DIR"),
}))
"""


def _outside_loopback(host: str) -> bool:
    """A destination off this machine: not loopback (IPv4-mapped included), not unspecified."""
    if host.lower() in ("", "localhost"):
        return False
    try:
        ip = ipaddress.ip_address(host.split("%")[0])
    except ValueError:
        return True
    mapped = getattr(ip, "ipv4_mapped", None)
    return not (ip.is_loopback or ip.is_unspecified or (mapped and mapped.is_loopback))


def test_outside_loopback_keeps_local_addresses_local():
    for host in ("", "localhost", "127.0.0.1", "::1", "0.0.0.0", "::", "::ffff:127.0.0.1"):
        assert not _outside_loopback(host), host
    for host in ("openaipublic.blob.core.windows.net", "57.150.192.193", "::ffff:8.8.8.8"):
        assert _outside_loopback(host), host


def _tiktoken_file(encoding: str) -> str:
    """tiktoken's cache file name for an OpenAI table: the sha1 of its URL."""
    url = f"https://openaipublic.blob.core.windows.net/encodings/{encoding}.tiktoken"
    return hashlib.sha1(url.encode()).hexdigest()


def _run_offline_child(tmp_path, model: str | None = None) -> dict:  # noqa: ANN001
    """The child above, with a tiktoken cache reduced to what WaveStack ships (`cl100k_base`,
    story 4), copied: the negative control must not write in the shipped folder."""
    shipped = compression_env.tiktoken_cache_dir()
    table = _tiktoken_file("cl100k_base")
    assert (shipped / table).is_file(), "WaveStack ne livre pas cl100k_base"
    cache = tmp_path / "tiktoken"
    cache.mkdir(exist_ok=True)
    shutil.copy(shipped / table, cache / table)
    env = {
        var: value
        for var, value in os.environ.items()
        if not var.lower().endswith("_proxy")
        and var not in (*compression_env.OFFLINE_ENV, *_TIKTOKEN_ENV, "HF_HUB_OFFLINE")
    }
    env["PYTHONIOENCODING"] = "utf-8"
    path = config.content_dir() / "demo_files" / "journal_serveur.log"
    argv = [sys.executable, "-c", _OFFLINE_CHILD, str(path), str(cache)]
    proc = subprocess.run(
        [*argv, model] if model else argv,
        env=env,
        cwd=config.repo_root(),
        capture_output=True,
        text=True,
        encoding="utf-8",
        timeout=300,
    )
    assert proc.returncode == 0, proc.stderr[-2000:]
    last = next((line for line in reversed(proc.stdout.splitlines()) if line.startswith("{")), None)
    assert last is not None, proc.stdout[-2000:]
    return json.loads(last)


_NO_HEADROOM = pytest.mark.skipif(
    importlib.util.find_spec("headroom") is None, reason="headroom-ai (extra) absent"
)


@_NO_HEADROOM
def test_headroom_makes_no_network_attempt_at_import_nor_compression(tmp_path):
    """Lot F (AD-15): the in-process test above passes even when Headroom tries the network
    (it falls back silently); here every attempt is recorded, in a fresh process."""
    out = _run_offline_child(tmp_path)

    public = [a for a in out["attempts"] if _outside_loopback(a[2])]
    assert public == [], f"tentatives réseau de Headroom : {public}"
    assert out["model"] == "gpt-4"
    assert ERROR_LINE in out["text"] and len(out["text"]) < out["before"]  # compressed
    # Story 4 review: litellm left the folder WaveStack points at (CUSTOM_TIKTOKEN_CACHE_DIR),
    # and tiktoken kept the table there (a bad sha256 would have deleted it).
    assert out["tiktoken_cache_dir"] == str(tmp_path / "tiktoken")
    assert (tmp_path / "tiktoken" / _tiktoken_file("cl100k_base")).is_file()


@_NO_HEADROOM
def test_headroom_offline_check_sees_the_old_counting_model_reach_out(tmp_path):
    """Negative control: with `gpt-4o`, the same child records tiktoken's attempt to fetch
    `o200k_base`, as on the target PC."""
    out = _run_offline_child(tmp_path, model="gpt-4o")

    hosts = {a[2] for a in out["attempts"] if _outside_loopback(a[2])}
    assert "openaipublic.blob.core.windows.net" in hosts


@pytest.mark.skipif(importlib.util.find_spec("tiktoken") is None, reason="tiktoken (extra) absent")
def test_headroom_counts_with_the_table_wavestack_ships():
    # `gpt-4o` (`o200k_base`) sent tiktoken to the network on the target PC (lot F).
    from tiktoken.model import encoding_name_for_model

    encoding = encoding_name_for_model(headroom_adapter.COUNTING_MODEL)
    assert encoding == "cl100k_base"
    assert (compression_env.tiktoken_cache_dir() / _tiktoken_file(encoding)).is_file()


def test_compression_cost_is_110_mb_by_default():
    mib = 1024 * 1024
    assert config.load_config().compression_cost_bytes == 110 * mib  # wavestack.toml
    assert config.Config(values={}).compression_cost_bytes == 110 * mib  # key absent


def test_headroom_reply_of_another_shape_keeps_the_original():
    text = "original"
    assert headroom_adapter.reply_text(None, text) is text
    assert headroom_adapter.reply_text([{"role": "user", "content": "x"}], text) is text
    assert headroom_adapter.reply_text([{"role": "tool", "content": [{"t": 1}]}], text) is text
    assert headroom_adapter.reply_text([{"role": "tool", "content": "court"}], text) == "court"
