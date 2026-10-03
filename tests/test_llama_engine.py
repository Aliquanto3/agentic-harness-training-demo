"""Restes différés, story 1 (E008): `LlamaCppEngine.complete` itself, never `FakeEngine`.

Each behaviour runs on two engines. `gguf` (marked `model`): a real GGUF named by
`WAVESTACK_TEST_GGUF`, greedy sampling, skipped otherwise. `stub`: the real `complete` on
a scripted `llama_cpp` (token ids, pieces, end of generation), so that a mutation of
`complete` fails pytest without any model. The tests read what the engine yields (token
count, ids, pieces), never a text the model would have to write.
"""

from __future__ import annotations

import os
from collections.abc import Callable, Iterator
from dataclasses import dataclass
from pathlib import Path
from types import SimpleNamespace

import pytest

from wavestack.context.render import render_template
from wavestack.models.capabilities import capabilities_for
from wavestack.models.engine import CancelToken, Fragment, LlamaCppEngine, Sampling

GREEDY = Sampling(temperature=0.0, top_k=1, top_p=1.0, min_p=0.0)
EOG = b"<|im_end|>"

# The stub's outputs, by prompt. After the end of generation llama.cpp would go on: so does
# the script, beyond the test's `max_tokens`, so that an engine which does not stop there
# ends on `length`, not `stop`.
SCRIPTS = {
    "long": [piece for n in range(7, 60) for piece in (f" {n}".encode(), b",")],
    "short": [b"Oui", b".", EOG, *[b" encore"] * 300],
    # « Café 🦜. »: « é » (2 bytes) and the parrot (4 bytes) cut between two tokens.
    "multibyte": [b"Caf", b"\xc3", b"\xa9", b" ", b"\xf0\x9f", b"\xa6\x9c", b".", EOG],
}


class _StubVocab:
    """The tokenizer's side `complete` reads: ids are positions in `pieces`."""

    def __init__(self) -> None:
        self.pieces: list[bytes] = []

    def id(self, piece: bytes) -> int:
        if piece not in self.pieces:
            self.pieces.append(piece)
        return self.pieces.index(piece)

    def is_eog(self, token: int) -> bool:
        return self.pieces[token] == EOG

    def token_pieces(self, ids: list[int]) -> list[bytes]:
        return [self.pieces[i] for i in ids]


@dataclass
class Subject:
    engine: LlamaCppEngine
    prompts: dict[str, list[int]]
    is_eog: Callable[[int], bool]
    scripted: bool = False  # the stub: its outputs are known


def _stub() -> Subject:
    vocab = _StubVocab()

    def generate(prompt_ids, **sampling) -> Iterator[int]:  # noqa: ANN001, ANN003
        for piece in SCRIPTS[vocab.pieces[prompt_ids[0]].decode()]:
            yield vocab.id(piece)

    engine = LlamaCppEngine.__new__(LlamaCppEngine)  # no model loaded
    engine._lib = SimpleNamespace(
        llama_perf_context_reset=lambda ctx: None,
        llama_perf_context=lambda ctx: SimpleNamespace(n_p_eval=0),
    )
    engine._llm = SimpleNamespace(ctx=None, generate=generate)
    engine._tokenizer = vocab
    engine._last_evaluated = None
    prompts = {name: [vocab.id(name.encode())] for name in SCRIPTS}
    return Subject(engine, prompts, vocab.is_eog, scripted=True)


def _chat(engine: LlamaCppEngine, message: str) -> list[int]:
    """`message` in the model's own chat template, reasoning off when it has the switch."""
    meta = engine.metadata()
    caps = capabilities_for(meta)
    switch = {caps.reasoning_variable: False} if caps.reasoning_variable else {}
    text = render_template(
        caps.chat_template or "",
        [{"role": "user", "content": message}],
        add_generation_prompt=True,
        bos_token=meta.bos_token,
        eos_token=meta.eos_token,
        **switch,
    )
    return engine.tokenize(text)


@pytest.fixture(scope="module", params=["stub", pytest.param("gguf", marks=pytest.mark.model)])
def subject(request) -> Iterator[Subject]:  # noqa: ANN001
    if request.param == "stub":
        yield _stub()
        return
    path = os.environ.get("WAVESTACK_TEST_GGUF")
    if not path or not Path(path).is_file():
        pytest.skip("WAVESTACK_TEST_GGUF does not point to a GGUF file.")
    engine = LlamaCppEngine(path, n_ctx=2048)
    try:
        prompts = {
            "long": engine.tokenize("1, 2, 3, 4, 5, 6,"),  # a plain text the model continues
            "short": _chat(engine, "Réponds seulement par le mot « oui »."),
            "multibyte": _chat(engine, "Recopie exactement, sans rien ajouter : 𝔚𝔞𝔳𝔢 🦜 𝔖𝔱𝔞𝔠𝔨"),
        }
        yield Subject(engine, prompts, engine._tokenizer.is_eog)
    finally:
        engine.close()


def _run(subject: Subject, prompt: str, *, stop=(), max_tokens: int = 64) -> list[Fragment]:  # noqa: ANN001
    engine, ids = subject.engine, subject.prompts[prompt]
    return list(engine.complete(ids, list(stop), max_tokens, CancelToken(), sampling=GREEDY))


def _tokens(fragments: list[Fragment]) -> list[Fragment]:
    return [f for f in fragments if f.token_id is not None]


def _whole(piece: bytes) -> bool:
    try:
        piece.decode("utf-8")
    except UnicodeDecodeError:
        return False
    return True


def test_the_end_of_generation_ends_the_completion_and_is_never_emitted(subject):
    fragments = _run(subject, "short", max_tokens=256)

    tokens = _tokens(fragments)
    assert tokens and not any(subject.is_eog(f.token_id) for f in tokens)
    assert fragments[-1].stop_reason == "stop"
    assert fragments[-1].output_tokens == len(tokens)


def test_the_output_is_cut_at_exactly_max_tokens(subject):
    fragments = _run(subject, "long", max_tokens=5)

    assert len(_tokens(fragments)) == 5
    assert fragments[-1].stop_reason == "length" and fragments[-1].output_tokens == 5


def test_a_stop_sequence_and_its_prefix_are_never_emitted(subject):
    reference = _tokens(_run(subject, "long", max_tokens=24))
    texts = [f.text for f in reference]
    full = "".join(texts)
    # Two tokens in a row, first seen where the first one starts: once the first is read,
    # what is pending is a prefix of the stop sequence, to be held back.
    for k in range(1, len(texts) - 2):
        stop, start = texts[k] + texts[k + 1], len("".join(texts[:k]))
        if texts[k] and texts[k + 1] and stop.strip() and full.find(stop) == start:
            break
    else:
        pytest.fail(f"aucune séquence d'arrêt de deux tokens dans {full!r}")

    # A second stop sequence never met: the first token, a prefix of it, is held back, then
    # released whole once the next token shows it is no stop.
    false_start = texts[0] + "\x00"
    fragments = _run(subject, "long", stop=[stop, false_start], max_tokens=24)

    assert fragments[-1].stop_reason == "stop"
    assert "".join(f.text for f in fragments) == full[:start]


def test_a_cancellation_stops_after_the_token_being_read(subject):
    cancel, fragments = CancelToken(), []
    engine, ids = subject.engine, subject.prompts["long"]
    for fragment in engine.complete(ids, [], 24, cancel, sampling=GREEDY):
        fragments.append(fragment)
        if fragment.token_id is not None:
            cancel.cancel()  # « Arrêter », pressed while the first token is shown

    assert len(_tokens(fragments)) == 1
    assert fragments[-1].stop_reason == "cancelled" and fragments[-1].output_tokens == 1


def test_a_character_cut_between_two_tokens_is_decoded_whole(subject):
    fragments = _run(subject, "multibyte", max_tokens=256)

    pieces = [f.piece for f in _tokens(fragments)]
    if all(_whole(p) for p in pieces):  # the model's vocabulary, not the engine
        if not subject.scripted:
            pytest.skip("aucun caractère coupé entre deux tokens avec ce GGUF")
        pytest.fail("aucun caractère coupé entre deux tokens : le cas n'est pas exercé")
    text = "".join(f.text for f in fragments)
    assert fragments[-1].stop_reason == "stop"
    assert "�" not in text and text == b"".join(pieces).decode("utf-8")
