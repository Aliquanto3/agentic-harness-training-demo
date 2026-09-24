"""Fake `Engine` for harness tests: one token per UTF-8 byte, scripted output."""

from __future__ import annotations

import threading
import time
from collections.abc import Iterator, Sequence

from wavestack import config
from wavestack.models.engine import CancelToken, EngineMetadata, Fragment
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
        template: str | None = CHATML,
        fail: bool = False,
        gate: threading.Event | None = None,
        delay: float = 0.0,
    ) -> None:
        self.output = output
        self.template = template
        self.fail = fail
        self.gate = gate
        self.delay = delay
        self.calls: list[list[int]] = []

    def tokenize(self, text: str) -> list[int]:
        return list(text.encode("utf-8"))

    def token_pieces(self, ids: Sequence[int]) -> list[bytes]:
        return [bytes([i]) for i in ids]

    def metadata(self) -> EngineMetadata:
        return EngineMetadata(
            architecture="fake",
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
        if self.gate is not None:
            self.gate.wait(timeout=5)
        if self.fail:
            raise RuntimeError("moteur en panne")
        count = 0
        for char in self.output:
            time.sleep(self.delay)
            if cancel.cancelled:
                yield Fragment("", count, "cancelled")
                return
            count += 1
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
