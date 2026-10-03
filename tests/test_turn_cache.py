"""Lot A: the engine's cache reused between turns (AD-4, AD-11, AD-17, N1, N2, NFR-1).

One test per row of the spec's I/O matrix, on `FakeEngine` (one token per byte, a simulated
cache that evaluates the whole prompt unless its cache is a prefix of it, as a hybrid model
does) and the Qwen3.5 template fixture: no GGUF needed.
"""

from __future__ import annotations

import threading
import time
from collections.abc import Iterator, Sequence

import pytest
from fake_engine import CHATML, FakeEngine, booted_session
from test_global_memory import DEMO, PREFERENCE, memory_session, memory_texts, remember
from test_mcp import McpWeb, loop, mcp_session, wait_for, web  # noqa: F401
from test_rag import COVERED, OFF_CORPUS, index, place_model, rag_config, rag_session  # noqa: F401
from test_subagent import RESULT, delegation, sub_session
from test_tools import QWEN, call

from wavestack.context.render import reasoning_wrap
from wavestack.models.engine import CancelToken, EngineMetadata, Fragment
from wavestack.session.effects import MemoryWrite
from wavestack.trace.journal import get_journal

QWEN_TEXT = QWEN.decode("utf-8")


def run(session, message: str | None) -> list:
    """Send `message` (`None`: replay the last turn), wait for the turn; its envelopes."""
    mark = get_journal().last_seq()
    if message is None:
        session.replay()
    else:
        session.send(message)
    session.join()
    return get_journal().events_since(mark)


def of(events: list, kind: str, context: str | None = "main") -> list[dict]:
    return [
        e.payload for e in events if e.kind == kind and (context is None or e.context_id == context)
    ]


def prompt(ctx: dict) -> str:
    return "".join(s["text"] for s in ctx["segments"])


def exact(events: list) -> None:
    """The gauge stays exact (the sum of the segments is the total) and the attribution
    found every text (no `harness_error`)."""
    for ctx in of(events, "context_rendered", None):
        assert sum(s["tokens"] for s in ctx["segments"]) == ctx["used"]
    assert of(events, "harness_error", None) == []


def qwen_session(outputs: list[str], *bricks: str, **engine_kwargs):
    engine = FakeEngine(outputs=outputs, template=QWEN_TEXT, architecture="qwen35", **engine_kwargs)
    session = booted_session(engine, window=16384)
    for brick in bricks:
        session.set_brick(brick, True)
    session.join()
    return engine, session


def reused(engine: FakeEngine, call_index: int, output: str) -> None:
    """Call `call_index` starts with the previous call's prompt and output, and the engine
    evaluated only what follows (A5, without GGUF)."""
    before = bytes(engine.calls[call_index - 1]) + output.encode("utf-8")
    assert bytes(engine.calls[call_index]).startswith(before)
    assert engine.evaluated[call_index] == len(engine.calls[call_index]) - len(before)


# ---------- the reasoning block rendered as produced (A1) ----------


def test_the_qwen_template_gives_its_reasoning_block_and_chatml_none():
    assert reasoning_wrap(QWEN_TEXT) == ("<think>\n", "\n</think>\n\n")
    assert reasoning_wrap(CHATML) is None
    llama = (  # Llama 3.2's way: every message kept as it is, no reasoning block
        "{% for m in messages %}<|start_header_id|>{{ m.role }}<|end_header_id|>\n\n"
        "{{ m.content | trim }}<|eot_id|>{% endfor %}"
        "{% if add_generation_prompt %}<|start_header_id|>assistant<|end_header_id|>\n\n"
        "{% endif %}"
    )
    assert reasoning_wrap(llama) is None
    keeps = (  # a template that keeps the past reasoning: nothing to write for it
        "{% for m in messages %}{{ m.role }}:{% if m.reasoning_content %}<think>"
        "{{ m.reasoning_content }}</think>{% endif %}{{ m.content }}\n{% endfor %}"
    )
    assert reasoning_wrap(keeps) is None
    assert reasoning_wrap("{{ raise_exception('non') }}") is None


def test_two_turns_without_reasoning_extend_the_cache():
    outputs = [call("calculator", expression="12*37"), "Cela fait 444.", "Oui, 444."]
    engine = FakeEngine(outputs=outputs, template=QWEN_TEXT, architecture="qwen35")
    session = booted_session(engine, window=16384)
    session.launch_scenario("native_tools")
    session.join()

    first = run(session, "Combien font 12 × 37 ?")
    second = run(session, "Tu es sûr ?")

    assert len(engine.calls) == 3
    reused(engine, 1, outputs[0])  # within t1 (as before)
    reused(engine, 2, outputs[1])  # t2's first call extends t1's last call and its output
    for events in (first, second):
        assert of(events, "prefix_not_reused", None) == []
        exact(events)
    (ended,) = of(second, "model_call_ended")
    assert ended["evaluated_tokens"] == engine.evaluated[2] < ended["prompt_tokens"]
    # The past answer and its tool step carry the empty reasoning block they were produced
    # with, in `template` segments: the history's texts are unchanged.
    ctx = of(second, "context_rendered")[0]
    text = prompt(ctx)
    assert "<|im_start|>assistant\n<think>\n\n</think>\n\nCela fait 444.<|im_end|>" in text
    assert "<|im_start|>assistant\n<think>\n\n</think>\n\n<tool_call>" in text
    history = [s["text"] for s in ctx["segments"] if s["kind"] == "history"]
    assert "Cela fait 444." in history and not any("think>" in t for t in history)
    think = [s for s in ctx["segments"] if s["kind"] == "template" and "</think>" in s["text"]]
    assert think and all(s["brick"] is None for s in think)
    session.close()


def test_two_turns_with_reasoning_keep_the_past_reasoning_in_the_history():
    outputs = ["Je salue.\n</think>\n\nBonjour !", "Je réponds.\n</think>\n\nTrès bien."]
    engine, session = qwen_session(outputs, "short_memory", "reasoning")

    first = run(session, "Bonjour")
    second = run(session, "Ça va ?")

    reused(engine, 1, outputs[0])
    assert of(second, "prefix_not_reused", None) == []
    exact(first)
    exact(second)
    ctx = of(second, "context_rendered")[0]
    assert "<|im_start|>assistant\n<think>\nJe salue.\n</think>\n\nBonjour !<|im_end|>" in prompt(
        ctx
    )
    history = {s["text"]: s for s in ctx["segments"] if s["kind"] == "history"}
    assert history["Je salue."]["brick"] == "short_memory"  # counted in `history` (gauge)
    assert "Bonjour !" in history
    session.close()


def test_a_template_without_reasoning_block_renders_the_history_as_before():
    engine = FakeEngine(outputs=["Bonjour !", "Très bien."])  # ChatML: no reasoning block
    session = booted_session(engine)
    session.set_brick("short_memory", True)
    session.join()

    run(session, "Bonjour")
    second = run(session, "Ça va ?")

    ctx = of(second, "context_rendered")[0]
    assert prompt(ctx) == (
        "<|im_start|>user\nBonjour<|im_end|>\n<|im_start|>assistant\nBonjour !<|im_end|>\n"
        "<|im_start|>user\nÇa va ?<|im_end|>\n<|im_start|>assistant\n"
    )
    assert "think" not in prompt(ctx)
    exact(second)
    session.close()


# ---------- the global memory frozen by conversation (A2, N1) ----------


def test_a_memory_write_waits_for_the_next_conversation():
    _, session = memory_session([remember(PREFERENCE), "Noté.", "Voici.", "Voilà."])

    first = run(session, "Retiens que je préfère trois points.")
    second = run(session, "Et ensuite ?")

    system = [
        [
            s["text"]
            for s in of(events, "context_rendered")[0]["segments"]
            if s["kind"] in ("system_prompt", "global_memory")
        ]
        for events in (first, second)
    ]
    assert system[0] == system[1]  # the same system message: the cache is reused
    assert of(second, "prefix_not_reused", None) == []
    drawer = get_journal().events_since(0)
    changed = [e.payload for e in drawer if e.kind == "memory_changed"][-1]
    assert PREFERENCE in [e["text"] for e in changed["entries"]]  # in the drawer already

    session.clear_conversation()
    third = run(session, "Bonjour")
    assert f"- {PREFERENCE}" in memory_texts(of(third, "context_rendered")[0])

    session.launch_scenario("global_memory")  # restores the demonstration: new conversation
    session.join()
    fourth = run(session, "Bonjour")
    assert memory_texts(of(fourth, "context_rendered")[0])[1:] == [f"- {t}" for t in DEMO]
    session.close()


def test_a_replay_reads_the_memory_snapshot_of_its_conversation():
    _, session = memory_session([remember(PREFERENCE), "Noté.", "Rejoué."])
    first = run(session, "Retiens ceci.")

    replayed = run(session, None)

    before = memory_texts(of(first, "context_rendered")[0])
    assert memory_texts(of(replayed, "context_rendered")[0]) == before
    assert f"- {PREFERENCE}" not in before
    (reread,) = of(replayed, "prefix_not_reused")
    assert reread["cause"] == "replay" and "Rejeu" in reread["message_text"]
    # The replayed prompt is t1's again: all in cache, but cut before t1's output.
    message = reread["message_text"]
    assert "sont déjà en cache" in message and "recalculer au moins le dernier token" in message
    assert "relit 0" not in message
    session.close()


def test_a_deleted_memory_entry_leaves_the_system_message_at_once():
    _, session = memory_session(["Bonjour.", "Oui."])
    run(session, "Bonjour")
    session.edit_memory("delete", "demo1")
    session.join()

    second = run(session, "Ça va ?")

    lines = memory_texts(of(second, "context_rendered")[0])[1:]
    assert lines == [f"- {t}" for t in DEMO[1:]]  # a deletion applies at once
    assert of(second, "prefix_not_reused")[0]["cause"] == "system"
    session.close()


def test_the_memory_is_taken_at_the_first_turn_with_the_brick_effective():
    _, session = qwen_session(["Bonjour.", "Oui."], "short_memory", "system_prompt")
    run(session, "Bonjour")  # the brick off: nothing taken
    with session._memory_lock:  # a write between the turns, as the model's would be
        session._apply_memory([MemoryWrite(op="add", entry_id="m1", text=PREFERENCE)], "user")
    session.set_brick("global_memory", True)
    session.join()

    second = run(session, "Ça va ?")

    assert f"- {PREFERENCE}" in memory_texts(of(second, "context_rendered")[0])
    session.close()


# ---------- a turn's first call checked against the engine's cache (A3) ----------


def test_a_system_prompt_changed_between_turns_is_named():
    engine, session = qwen_session(["Bonjour.", "Oui."], "short_memory", "system_prompt")
    run(session, "Bonjour")
    session.save_system_prompt("Tu réponds toujours en une phrase.")
    session.join()

    second = run(session, "Ça va ?")

    (reread,) = of(second, "prefix_not_reused")
    assert reread["cause"] == "system"
    assert reread["message_text"].startswith("Le message système a changé")
    cached = len(engine.calls[0]) + len("Bonjour.")
    again = len(engine.calls[1]) - reread["common_tokens"]
    assert f"sur {cached} en cache" in reread["message_text"].replace(" ", "")
    assert f"relit {again} tokens" in reread["message_text"].replace(" ", "")
    assert reread["message_text"].count("modèle hybride") == 1  # the cost on Qwen3.5: everything
    assert engine.evaluated[1] == len(engine.calls[1])
    exact(second)
    session.close()


def test_short_memory_off_resends_no_exchange_it_is_the_history():
    _, session = qwen_session(["Bonjour.", "Oui."])  # the bare LLM, the launch state
    run(session, "Bonjour")

    (reread,) = of(run(session, "Ça va ?"), "prefix_not_reused")

    assert reread["cause"] == "history" and "mémoire courte éteinte" in reread["message_text"]
    session.close()


def test_a_brick_switched_off_that_changes_the_template_text_is_template():
    _, session = qwen_session(["Bonjour.", "Oui."], "short_memory", "tools")
    run(session, "Bonjour")
    session.set_brick("tools", False)  # the template's tools header leaves the prompt
    session.join()

    (reread,) = of(run(session, "Ça va ?"), "prefix_not_reused")

    assert reread["cause"] == "template"
    assert reread["message_text"].startswith("Une brique activée ou désactivée")
    session.close()


def test_an_overflowing_turn_checks_nothing_and_is_not_abandoned():
    _, session = qwen_session(["Bonjour.", "Oui."], "short_memory")
    run(session, "Bonjour")

    overflow = run(session, "x" * 20000)
    third = run(session, "Ça va ?")

    assert of(overflow, "turn_ended")[0]["status"] == "overflow"
    assert of(overflow, "prefix_not_reused", None) == []  # no call, nothing to check
    assert of(third, "prefix_not_reused", None) == []  # the cache still holds t1
    session.close()


def test_a_turn_cancelled_during_its_call_is_abandoned():
    engine, session = qwen_session(["Bonjour, je réfléchis longuement.", "Oui."], "short_memory")
    engine.gate = threading.Event()
    session.send("Bonjour")
    deadline = time.monotonic() + 5
    while not engine.calls and time.monotonic() < deadline:
        time.sleep(0.01)
    session.stop()
    engine.gate.set()
    session.join()
    engine.gate = None

    (reread,) = of(run(session, "Ça va ?"), "prefix_not_reused")

    assert reread["cause"] == "abandoned"
    session.close()


def test_a_cleared_conversation_is_a_reset():
    _, session = qwen_session(["Bonjour.", "Oui."], "short_memory")
    run(session, "Bonjour")
    session.clear_conversation()

    (reread,) = of(run(session, "Ça va ?"), "prefix_not_reused")

    assert reread["cause"] == "reset" and "vidée" in reread["message_text"]
    session.close()


def test_a_scenario_change_is_a_reset():
    # Without a prefill (E122): with one, the engine's cache holds the new scenario's prefix
    # once it ends, and the first turn extends it (`test_a_prefill_after_a_conversation…`).
    engine = EngineWithoutPrefill(
        outputs=["Bonjour.", "Oui."], template=QWEN_TEXT, architecture="qwen35"
    )
    session = booted_session(engine, window=16384)
    session.launch_scenario("short_memory")
    session.join()
    run(session, "Bonjour")
    session.launch_scenario("system_prompt")
    session.join()

    (reread,) = of(run(session, "Ça va ?"), "prefix_not_reused")

    assert reread["cause"] == "reset"
    session.close()


def test_a_failed_previous_turn_is_abandoned():
    engine, session = qwen_session(["Bonjour.", "Oui."], "short_memory")
    engine.fail = True
    assert of(run(session, "Bonjour"), "turn_ended")[0]["status"] == "error"
    engine.fail = False

    (reread,) = of(run(session, "Ça va ?"), "prefix_not_reused")

    assert reread["cause"] == "abandoned" and "n'a pas abouti" in reread["message_text"]
    session.close()


def test_a_history_rewritten_without_the_rag_excerpts_is_named(index):  # noqa: F811
    place_model()
    engine = FakeEngine(outputs=["Douze.", "Lima."], template=QWEN_TEXT, architecture="qwen35")
    session, _ = rag_session(rag_config(index), engine, bricks=("short_memory", "rag"))
    run(session, COVERED)

    second = run(session, OFF_CORPUS)

    (reread,) = of(second, "prefix_not_reused")
    assert reread["cause"] == "history"
    assert reread["message_text"].startswith("L'historique n'est plus rendu")
    exact(second)
    session.close()


def test_the_first_turn_and_a_new_model_check_nothing():
    engine, session = qwen_session(["Bonjour."], "short_memory")

    events = run(session, "Bonjour")

    assert of(events, "prefix_not_reused", None) == []
    assert of(events, "model_call_ended")[0]["evaluated_tokens"] == len(engine.calls[0])
    session.close()


# ---------- the main context's state kept around a delegation (A4, N2) ----------


def delegated(engine_kwargs: dict | None = None, bricks=("tools", "subagent")):
    outputs = [
        delegation(),
        call("read_file", path="notes_reunion.txt"),
        RESULT,
        "Voilà.",
        "Rien d'autre.",
    ]
    engine, session = sub_session(outputs, bricks=bricks)
    for key, value in (engine_kwargs or {}).items():
        setattr(engine, key, value)
    events = run(session, "Quelles décisions ont été prises ?")
    return outputs, engine, session, events


def test_a_delegation_with_a_stateful_engine_keeps_the_main_cache():
    outputs, engine, session, events = delegated()

    (ended,) = of(events, "subagent_ended", None)
    assert ended["state_saved_bytes"] > 0 and ended["state_restore_ms"] is not None
    assert (engine.snapshots, engine.restores) == (1, 1)
    assert of(events, "prefix_not_reused", None) == []
    # The main call after the delegation evaluates its new tokens only.
    before = bytes(engine.calls[0]) + outputs[0].encode()
    assert bytes(engine.calls[3]).startswith(before)
    main = of(events, "model_call_ended")
    assert main[1]["evaluated_tokens"] == len(engine.calls[3]) - len(before)
    assert of(events, "turn_ended")[0]["status"] == "completed"
    exact(events)
    session.close()


def test_a_delegation_with_a_stateless_engine_traces_the_reading():
    _, engine, session, events = delegated({"stateful": False})

    (ended,) = of(events, "subagent_ended", None)
    assert ended["state_saved_bytes"] is None and ended["state_restore_ms"] is None
    (reread,) = of(events, "prefix_not_reused")
    assert reread["cause"] == "subagent"
    assert "ne sait pas sauvegarder" in reread["message_text"]
    assert engine.evaluated[3] == len(engine.calls[3])  # the main context read again
    assert of(events, "turn_ended")[0]["status"] == "completed"
    session.close()


def test_the_turn_after_a_stateless_delegation_is_not_blamed_on_it():
    bricks = ("short_memory", "tools", "subagent")
    _, _, session, _ = delegated({"stateful": False}, bricks=bricks)

    second = run(session, "Autre chose ?")

    assert [r for r in of(second, "prefix_not_reused") if r["cause"] == "subagent"] == []
    session.close()


def test_a_failed_restore_goes_on_and_traces_the_reading():
    _, engine, session, events = delegated({"fail_restore": True})

    (ended,) = of(events, "subagent_ended", None)
    assert ended["state_saved_bytes"] > 0 and ended["state_restore_ms"] is None
    (reread,) = of(events, "prefix_not_reused")
    assert reread["cause"] == "subagent" and "a échoué" in reread["message_text"]
    assert of(events, "turn_ended")[0]["status"] == "completed"
    assert of(events, "harness_error", None) == []  # never a fatal error
    session.close()


def test_a_failed_save_goes_on_and_traces_the_reading():
    def broken():
        raise MemoryError("plus de mémoire")

    _, engine, session, events = delegated({"snapshot": broken})

    (reread,) = of(events, "prefix_not_reused")
    assert reread["cause"] == "subagent" and "a échoué" in reread["message_text"]
    assert of(events, "subagent_ended", None)[0]["state_saved_bytes"] is None
    assert of(events, "turn_ended")[0]["status"] == "completed"
    session.close()


# ---------- an engine without cache nor state (a server) ----------


class BareEngine:
    """The `Engine` port without `cached_ids`, `snapshot`, `restore` nor `last_evaluated`."""

    def __init__(self, fake: FakeEngine) -> None:
        self.fake = fake

    def tokenize(self, text: str) -> list[int]:
        return self.fake.tokenize(text)

    def token_pieces(self, ids: Sequence[int]) -> list[bytes]:
        return self.fake.token_pieces(ids)

    def metadata(self) -> EngineMetadata:
        return self.fake.metadata()

    def complete(
        self, prompt_ids: Sequence[int], stop: Sequence[str], max_tokens: int, cancel: CancelToken
    ) -> Iterator[Fragment]:
        return self.fake.complete(prompt_ids, stop, max_tokens, cancel)

    def close(self) -> None:
        pass


def test_an_engine_without_cache_nor_state_still_works():
    fake = FakeEngine(
        outputs=["Bonjour.", delegation(), RESULT, "Voilà."],
        template=QWEN_TEXT,
        architecture="qwen35",
    )
    session = booted_session(BareEngine(fake), window=16384)  # type: ignore[arg-type]
    for brick in ("short_memory", "tools", "subagent"):
        session.set_brick(brick, True)
    session.join()

    first = run(session, "Bonjour")
    second = run(session, "Quelles décisions ?")

    assert of(first, "model_call_ended")[0]["evaluated_tokens"] is None
    # The ids sent and the output stand for the cache: t2 extends t1, then the delegation.
    reread = of(second, "prefix_not_reused")
    assert [r["cause"] for r in reread] == ["subagent"]
    assert of(second, "turn_ended")[0]["status"] == "completed"
    exact(second)
    session.close()


def test_an_engine_without_cache_names_a_past_answer_rewritten():
    fake = FakeEngine(outputs=["Bonjour.", "Oui."], template=QWEN_TEXT, architecture="qwen35")
    session = booted_session(BareEngine(fake), window=16384)  # type: ignore[arg-type]
    session.set_brick("short_memory", True)
    session.join()
    run(session, "Bonjour")
    with session._lock:  # the answer rendered otherwise than it was produced
        session._history[0] = session._history[0]._replace(text="Salut.")

    (reread,) = of(run(session, "Ça va ?"), "prefix_not_reused")

    assert reread["cause"] == "history"
    session.close()


# ---------- story 4 of the deferred leftovers (E122): the first turn prefilled ----------


class EngineWithoutPrefill(FakeEngine):
    """A server-like engine, with a cache but without `prefill`: the session emits nothing."""

    prefill = None  # type: ignore[assignment]


class EnginePrefillFails(FakeEngine):
    """`prefill` fails after its first batch, whose ids stay in the cache."""

    def prefill(self, ids: Sequence[int], cancel: CancelToken) -> int | None:
        wanted = list(ids)
        self.prefills.append(wanted)
        self.cache = wanted[: self.prefill_batch]
        raise RuntimeError("moteur en panne")


def prefill_of(mark: int) -> tuple[list[dict], list[dict]]:
    events = get_journal().events_since(mark)
    return of(events, "context_prefill_started", None), of(events, "context_prefill_ended", None)


def launch(session, scenario_id: str) -> tuple[dict, dict]:
    """Launch `scenario_id`, wait for its prefill to end; its started and ended payloads."""
    mark = get_journal().last_seq()
    session.launch_scenario(scenario_id)
    wait_for(session, "context_prefill_ended", mark)
    (started,), (ended,) = prefill_of(mark)
    return started, ended


def until(predicate, what: str) -> None:  # noqa: ANN001
    """Poll `predicate` without `join` (the worker may be waiting on a gate)."""
    deadline = time.monotonic() + 10
    while not predicate():
        assert time.monotonic() < deadline, what
        time.sleep(0.01)


def prefilling_session(gate: threading.Event, scenario_id: str = "native_tools"):
    """A scenario launched, its prefill holding on `gate` after its first batch of 64 ids."""
    engine = FakeEngine(
        outputs=["Bonjour !"],
        template=QWEN_TEXT,
        architecture="qwen35",
        prefill_batch=64,
        prefill_gate=gate,
    )
    session = booted_session(engine, window=16384)
    mark = get_journal().last_seq()
    session.launch_scenario(scenario_id)
    until(lambda: len(engine.cache) >= 64, "first batch evaluated")
    return engine, session, mark


def test_a_scenario_launch_prefills_and_the_first_call_extends_the_prefix():
    engine = FakeEngine(outputs=["Bonjour !"], template=QWEN_TEXT, architecture="qwen35")
    session = booted_session(engine, window=16384)
    plain = EngineWithoutPrefill(outputs=["Bonjour !"], template=QWEN_TEXT, architecture="qwen35")
    witness = booted_session(plain, window=16384)

    started, ended = launch(session, "native_tools")

    (prefix,) = engine.prefills
    assert started["tokens"] == ended["tokens"] == len(prefix) > 0
    assert ended["status"] == "completed" and ended["evaluated_tokens"] == len(prefix)
    assert engine.prefilled == [len(prefix)] and engine.calls == [] and engine.evaluated == []
    assert "pendant la lecture de la consigne" in started["message_text"]
    assert ended["message_text"].startswith("Préremplissage terminé")
    # The boundary: before the message, one token short of the template's own newline.
    assert bytes(prefix).decode("utf-8").endswith("<|im_start|>user")

    events = run(session, "Quelle heure est-il ?")
    witness.launch_scenario("native_tools")
    witness.join()
    control = run(witness, "Quelle heure est-il ?")

    assert engine.calls[0][: len(prefix)] == prefix  # the first call extends the prefix
    (call,) = of(events, "model_call_ended")
    assert call["evaluated_tokens"] == engine.evaluated[0] == len(engine.calls[0]) - len(prefix)
    assert of(events, "prefix_not_reused", None) == []
    # The same context, id for id, as without any prefill (E122: nothing sent changes).
    assert engine.calls[0] == plain.calls[0] and plain.evaluated[0] == len(plain.calls[0])
    mine, theirs = of(events, "context_rendered")[0], of(control, "context_rendered")[0]
    assert prompt(mine) == prompt(theirs) and mine["used"] == theirs["used"]
    assert of(control, "context_prefill_started", None) == [] and plain.prefills == []
    exact(events)
    session.close()
    witness.close()


def test_a_message_during_the_prefill_abandons_it_and_reuses_the_part_evaluated():
    gate = threading.Event()
    engine, session, mark = prefilling_session(gate)

    session.send("Bonjour")  # accepted at once: the prefill never blocks the user
    gate.set()
    session.join()

    events = get_journal().events_since(mark)
    (ended,) = of(events, "context_prefill_ended", None)
    assert ended["status"] == "abandoned" and ended["evaluated_tokens"] == 64 < ended["tokens"]
    assert ended["message_text"].startswith("Préremplissage abandonné après 64 tokens")
    assert engine.prefilled == [64]
    kinds = [e.kind for e in events]
    assert kinds.index("context_prefill_ended") < kinds.index("model_call_started")
    assert engine.calls[0][:64] == engine.prefills[0][:64]  # the part evaluated is reused
    assert engine.evaluated[0] == len(engine.calls[0]) - 64
    assert of(events, "prefix_not_reused", None) == []
    assert of(events, "turn_ended")[0]["status"] == "completed"
    session.close()


def test_a_setting_changed_during_the_prefill_abandons_it():
    gate = threading.Event()
    engine, session, mark = prefilling_session(gate)

    session.set_brick("hooks", True)  # class (a): the preview is rendered again, not prefilled
    gate.set()
    session.join()

    started, ended = prefill_of(mark)
    assert len(started) == 1 and [e["status"] for e in ended] == ["abandoned"]
    assert engine.prefilled == [64]
    assert of(get_journal().events_since(mark), "context_preview", None)[-1]  # the preview
    session.close()


def test_a_model_load_during_the_prefill_abandons_it():
    gate = threading.Event()
    engine, session, mark = prefilling_session(gate)

    session.set_context_window(8192)  # class (b): leaves `idle` for a reload
    gate.set()
    session.join()

    started, ended = prefill_of(mark)
    assert len(started) == 1 and [e["status"] for e in ended] == ["abandoned"]
    assert engine.prefilled == [64]
    session.close()


def test_a_prefill_that_fails_is_traced_as_an_error_and_the_turn_follows():
    engine = EnginePrefillFails(
        outputs=["Bonjour !"], template=QWEN_TEXT, architecture="qwen35", prefill_batch=64
    )
    session = booted_session(engine, window=16384)

    started, ended = launch(session, "native_tools")

    assert started["phase_label"].startswith("Préremplissage du cache (")  # AD-2: a phase
    assert started["phase_label"].endswith(" tokens)")
    assert ended["status"] == "error" and "moteur en panne" in ended["message_text"]
    assert ended["evaluated_tokens"] == 64 < ended["tokens"]  # what sits in the cache
    events = run(session, "Bonjour")
    assert of(events, "turn_ended")[0]["status"] == "completed"
    assert of(events, "prefix_not_reused", None) == []
    assert engine.evaluated[0] == len(engine.calls[0]) - 64
    session.close()


def test_a_prefill_after_a_conversation_leaves_no_false_reset():
    """`_main_cache` held the previous conversation: once the prefill ends it follows the
    engine's cache, which the first turn extends (no `prefix_not_reused{reset}`)."""
    engine = FakeEngine(outputs=["Bonjour.", "Oui."], template=QWEN_TEXT, architecture="qwen35")
    session = booted_session(engine, window=16384)
    session.launch_scenario("short_memory")
    session.join()
    run(session, "Bonjour")

    _, ended = launch(session, "system_prompt")
    events = run(session, "Ça va ?")

    assert ended["status"] == "completed"
    prefix = engine.prefills[-1]
    assert engine.calls[-1][: len(prefix)] == prefix
    assert of(events, "prefix_not_reused", None) == []
    (call,) = of(events, "model_call_ended")
    assert call["evaluated_tokens"] == engine.evaluated[-1] == len(engine.calls[-1]) - len(prefix)
    session.close()


def test_another_scenario_during_the_prefill_abandons_it_and_prefills_its_own():
    gate = threading.Event()
    engine, session, mark = prefilling_session(gate)

    session.launch_scenario("short_memory")
    gate.set()
    wait_for(session, "context_prefill_ended", mark, n=2)

    started, ended = prefill_of(mark)
    assert [e["status"] for e in ended] == ["abandoned", "completed"]
    assert len(started) == 2 and engine.prefilled[0] == 64
    assert engine.cache == engine.prefills[1]  # the second scenario's prefix is in cache
    session.close()


@pytest.mark.parametrize("engine_kind", ["without_prefill", "stateless"])
def test_an_engine_that_cannot_prefill_gets_no_event(engine_kind):
    if engine_kind == "without_prefill":
        engine = EngineWithoutPrefill(
            outputs=["Bonjour !"], template=QWEN_TEXT, architecture="qwen35"
        )
    else:  # a server: `cached_ids` is None, `prefill` too
        engine = FakeEngine(
            outputs=["Bonjour !"], template=QWEN_TEXT, architecture="qwen35", stateful=False
        )
    session = booted_session(engine, window=16384)
    mark = get_journal().last_seq()

    session.launch_scenario("native_tools")
    session.join()

    assert prefill_of(mark) == ([], []) and engine.prefills == []
    assert of(run(session, "Bonjour"), "turn_ended")[0]["status"] == "completed"
    session.close()


def test_the_prefix_holds_with_h3s_injection_before_the_message():
    """The `subagent` scenario keeps H3 on: its injection precedes the message, within the
    prefix (the preview's injection is the turn's)."""
    engine = FakeEngine(outputs=["Bonjour !"], template=QWEN_TEXT, architecture="qwen35")
    session = booted_session(engine, window=16384)
    _, ended = launch(session, "subagent")
    assert ended["status"] == "completed"
    (prefix,) = engine.prefills

    events = run(session, "Bonjour")

    ctx = of(events, "context_rendered")[0]
    (injection,) = [s["text"] for s in ctx["segments"] if s["kind"] == "hook_injection"]
    assert injection.encode("utf-8") in bytes(prefix)
    assert engine.calls[0][: len(prefix)] == prefix
    assert engine.evaluated[0] == len(engine.calls[0]) - len(prefix)
    assert of(events, "prefix_not_reused", None) == []
    exact(events)
    session.close()


DATAGOUV = [
    {
        "name": "search_datasets",
        "description": "Recherche des jeux de données publics.",
        "inputSchema": {"type": "object", "properties": {"q": {"type": "string"}}},
    }
]


def test_the_mcp_lazy_scenario_prefills_after_its_connections_with_the_catalog(loop, web):  # noqa: F811
    web(McpWeb(DATAGOUV))
    session = mcp_session(loop, ["Voilà."], window=16384)
    engine = session._engine
    mark = get_journal().last_seq()

    session.launch_scenario("mcp_lazy")
    wait_for(session, "context_prefill_ended", mark)

    events = get_journal().events_since(mark)
    kinds = [e.kind for e in events]
    connected = [i for i, k in enumerate(kinds) if k == "mcp_connect_ended"]
    assert len(connected) == 2 and kinds.index("context_prefill_started") > max(connected)
    (ended,) = of(events, "context_prefill_ended", None)
    assert ended["status"] == "completed"
    (prefix,) = engine.prefills
    text = bytes(prefix).decode("utf-8")
    assert "- local__define_term" in text and "- datagouv__search_datasets" in text
    assert '"name": "load_tool_doc"' in text

    turn = run(session, "Que veut dire MCP ?")

    assert engine.calls[0][: len(prefix)] == prefix
    assert of(turn, "prefix_not_reused", None) == []
    exact(turn)
    session.close()
