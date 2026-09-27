"""Fake `Engine` for harness tests: one token per UTF-8 byte, scripted output."""

from __future__ import annotations

import threading
import time
from collections.abc import Iterator, Sequence

from wavestack import config
from wavestack.models.engine import CancelToken, EngineMetadata, EngineSnapshot, Fragment
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
        self.cache: list[int] = []
        self.evaluated: list[int] = []
        self.snapshots = 0
        self.restores = 0

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
        self, prompt_ids: Sequence[int], stop: Sequence[str], max_tokens: int, cancel: CancelToken
    ) -> Iterator[Fragment]:
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
        for char in output:
            time.sleep(self.delay)
            if cancel.cancelled:
                yield Fragment("", count, "cancelled")
                return
            count += 1
            self.cache += list(char.encode("utf-8"))
            yield Fragment(char, count)
            if count >= max_tokens:
                yield Fragment("", count, "length")
                return
        yield Fragment("", count, "stop")

    def close(self) -> None:
        pass


def booted_session(engine: FakeEngine, *, window: int = 4096) -> AppSession:
    session = AppSession(
        config.Config(values={"context": {"window": window, "near_limit_ratio": 0.8}}),
        engine_factory=lambda path, n_ctx: engine,
    )
    session.boot("fake.gguf").result()
    return session
