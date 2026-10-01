"""Fake `Engine` for harness tests: one token per UTF-8 byte, scripted output."""

from __future__ import annotations

import threading
import time
from collections.abc import Iterator, Sequence

from wavestack import config
from wavestack.models.candidates import read_logits
from wavestack.models.engine import (
    DEFAULT_SAMPLING,
    PREFILL_BATCH,
    CancelToken,
    EngineMetadata,
    EngineSnapshot,
    Fragment,
    common_prefix_len,
)
from wavestack.session.app_session import AppSession

CHATML = (
    r"{% for message in messages %}"
    r"{{ '<|im_start|>' + message.role + '\n' + message.content + '<|im_end|>\n' }}"
    r"{% endfor %}"
    r"{% if add_generation_prompt %}{{ '<|im_start|>assistant\n' }}{% endif %}"
)


class FakeEngine:
    def __init__(
        self,
        *,
        output: str = "Bonjour !",
        outputs: list[str] | None = None,
        template: str | None = CHATML,
        architecture: str = "fake",
        fail: bool = False,
        gate: threading.Event | None = None,
        delay: float = 0.0,
        stateful: bool = True,
        fail_restore: bool = False,
        cache_lags: bool = False,
        candidates_script: list[list[dict]] | None = None,
        logits_script: list[list[float]] | None = None,
        prefill_batch: int = PREFILL_BATCH,
        prefill_gate: threading.Event | None = None,
    ) -> None:
        self.output = output
        self.outputs = outputs  # one per call, the last one repeated
        self.template = template
        self.architecture = architecture
        self.fail = fail
        self.gate = gate
        self.delay = delay
        self.calls: list[list[int]] = []
        # Lot A: a simulated cache, the ids of the last call then the bytes it emitted (the
        # prompt tokens it evaluated: all of them unless the cache is their prefix, as on a
        # hybrid model). `stateful=False`: no `snapshot` (a server); `fail_restore`: a
        # `restore` that fails.
        self.stateful = stateful
        self.fail_restore = fail_restore
        # Lot C: as llama.cpp, the last token sampled is not in the cache (not evaluated yet).
        self.cache_lags = cache_lags
        self.cache: list[int] = []
        self.evaluated: list[int] = []
        # Story 29: the sampling of each call that gave one (the « LLM nu » screen only).
        self.samplings: list = []
        # Story 29, increment 4: the candidates of each token (their text from the id's
        # byte), given when the screen asks; `candidates` records how many were asked.
        self.candidates_script = candidates_script
        self.candidates: list[int] = []
        # Story 5 of 2026-09-30: scripted logits, one list per token (a small vocabulary: the
        # ids are their positions), read as the in-process engine reads its own
        # (`candidates.read_logits`): the candidates and the most probable tokens (`top`); the
        # token drawn is the most probable. Takes over `candidates_script` for those tokens.
        self.logits_script = logits_script
        self.snapshots = 0
        self.restores = 0
        # E122: `prefill` by batches of `prefill_batch`; `prefill_gate` waits after the first
        # batch (a test sends a message meanwhile). `prefills`: the ids each call asked for;
        # `prefilled`: how many it evaluated. Nothing enters `evaluated` nor `calls`.
        self.prefill_batch = prefill_batch
        self.prefill_gate = prefill_gate
        self.prefills: list[list[int]] = []
        self.prefilled: list[int] = []

    @property
    def last_evaluated(self) -> int | None:
        return self.evaluated[-1] if self.evaluated else None

    def cached_ids(self) -> list[int] | None:
        return list(self.cache) if self.stateful else None  # a server says nothing

    def snapshot(self) -> EngineSnapshot | None:
        if not self.stateful:
            return None
        self.snapshots += 1
        return EngineSnapshot(list(self.cache), len(self.cache) * 4)

    def restore(self, snapshot: EngineSnapshot) -> bool:
        self.restores += 1
        if self.fail_restore:
            return False
        self.cache = list(snapshot.data)
        return True

    def prefill(self, ids: Sequence[int], cancel: CancelToken) -> int | None:
        """As `LlamaCppEngine.prefill`: the cache cut to its common prefix with `ids`, then
        the rest by batches, each checked against `cancel` first."""
        if not self.stateful:
            return None  # a server cannot
        wanted = list(ids)
        self.prefills.append(wanted)
        common = common_prefix_len(self.cache, wanted)
        if common == len(wanted):
            self.prefilled.append(0)
            return 0  # every id asked is in cache already: left as it is
        self.cache = wanted[:common]
        evaluated = 0
        for start in range(common, len(wanted), self.prefill_batch):
            if cancel.cancelled:
                break
            batch = wanted[start : start + self.prefill_batch]
            self.cache += batch
            evaluated += len(batch)
            if start == common and self.prefill_gate is not None:
                self.prefill_gate.wait(timeout=5)
        self.prefilled.append(evaluated)
        return evaluated

    def tokenize(self, text: str) -> list[int]:
        return list(text.encode("utf-8"))

    def token_pieces(self, ids: Sequence[int]) -> list[bytes]:
        return [bytes([i]) for i in ids]

    def metadata(self) -> EngineMetadata:
        return EngineMetadata(
            architecture=self.architecture,
            chat_template=self.template,
            native_context=None,
            bos_token="",
            eos_token="<|im_end|>",
            special_tokens=("<|im_start|>", "<|im_end|>"),
        )

    def complete(
        self,
        prompt_ids: Sequence[int],
        stop: Sequence[str],
        max_tokens: int,
        cancel: CancelToken,
        *,
        sampling=None,  # noqa: ANN001 - story 29: given by the « LLM nu » screen only
        candidates: int = 0,
    ) -> Iterator[Fragment]:
        if sampling is not None:
            self.samplings.append(sampling)
        if candidates:
            self.candidates.append(candidates)
        self.calls.append(list(prompt_ids))
        prefix = self.cache and list(prompt_ids[: len(self.cache)]) == self.cache
        self.evaluated.append(len(prompt_ids) - (len(self.cache) if prefix else 0))
        self.cache = list(prompt_ids)
        if self.gate is not None:
            self.gate.wait(timeout=5)
        if self.fail:
            raise RuntimeError("moteur en panne")
        n = len(self.calls) - 1
        output = self.outputs[min(n, len(self.outputs) - 1)] if self.outputs else self.output
        count = 0
        held: list[int] = []  # `cache_lags`: the last token sampled, not evaluated yet
        for char in output:
            time.sleep(self.delay)
            if cancel.cancelled:
                yield Fragment("", count, "cancelled")
                return
            count += 1
            if self.cache_lags:
                self.cache += held
                held = list(char.encode("utf-8"))
            else:
                self.cache += list(char.encode("utf-8"))
            # Story 29: one character = one token, its bytes the piece.
            read, top = None, None
            if candidates and self.logits_script and count <= len(self.logits_script):
                logits = self.logits_script[count - 1]
                chosen = max(range(len(logits)), key=logits.__getitem__)
                read, top = read_logits(
                    logits, sampling or DEFAULT_SAMPLING, chosen, candidates, self.token_pieces
                )
            elif candidates and self.candidates_script and count <= len(self.candidates_script):
                read = tuple(
                    {"text": bytes([c["token_id"]]).decode("utf-8", "replace")} | c
                    for c in self.candidates_script[count - 1]
                )
            yield Fragment(char, count, piece=char.encode("utf-8"), candidates=read, top=top)
            if count >= max_tokens:
                yield Fragment("", count, "length")
                return
        yield Fragment("", count, "stop")

    def close(self) -> None:
        pass


def booted_session(
    engine: FakeEngine, *, window: int = 4096, values: dict | None = None
) -> AppSession:
    context = {"context": {"window": window, "near_limit_ratio": 0.8}}
    session = AppSession(
        config.Config(values=config._deep_merge(context, values or {})),
        engine_factory=lambda path, n_ctx: engine,
    )
    session.boot("fake.gguf").result()
    return session
