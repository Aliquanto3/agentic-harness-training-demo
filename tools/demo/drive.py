"""Drive a running WaveStack for the README demo: screenshots and a manifest per sequence.

Two sequences, in `<frames>/main` and `<frames>/llm`: the « LLM nu » scenario then « Outils
natifs » on the same prompt, and the bare LLM screen's tokenizer. WaveStack must already run on
127.0.0.1:8420, in French, with a local model loaded (see README.md next to this file).
"""

from __future__ import annotations

import json
import sys
import time
import urllib.request
from pathlib import Path

from playwright.sync_api import Page, sync_playwright

BASE = "http://127.0.0.1:8420"
PROMPT = "Quelle heure est-il ?"
VIEWPORT = {"width": 1600, "height": 900}  # compose.py's highlight boxes are in these pixels


class Recorder:
    def __init__(self, page: Page, folder: Path) -> None:
        self.page, self.folder, self.manifest, self.t0 = page, folder, [], time.time()
        folder.mkdir(parents=True, exist_ok=True)
        for old in folder.glob("*.png"):
            old.unlink()

    def shot(self, phase: str) -> None:
        path = self.folder / f"{len(self.manifest):04d}.png"
        self.page.screenshot(path=str(path))
        entry = {"file": path.name, "phase": phase, "t": round(time.time() - self.t0, 2)}
        answer = answer_box(self.page)
        if answer:
            entry["answer"] = answer
        self.manifest.append(entry)

    def hold(self, phase: str, seconds: float, every: float = 0.4) -> None:
        end = time.time() + seconds
        while time.time() < end:
            self.shot(phase)
            time.sleep(every)

    def type(self, text: str, phase: str) -> None:
        for i, char in enumerate(text):
            self.page.keyboard.type(char)
            if i % 2:
                self.shot(phase)
        self.shot(phase)

    def save(self) -> None:
        (self.folder / "manifest.json").write_text(
            json.dumps(self.manifest, indent=1), encoding="utf-8"
        )


def answer_box(page: Page) -> list[float] | None:
    """The last model bubble, clipped to the visible chat: the answer moves with its length."""
    return page.evaluate(
        """() => {
          const bubbles = document.querySelectorAll("#chat .bubble-model");
          const chat = document.getElementById("chat");
          if (!bubbles.length || !chat) return null;
          const b = bubbles[bubbles.length - 1].getBoundingClientRect();
          const c = chat.getBoundingClientRect();
          return [b.left, Math.max(b.top, c.top), b.right, Math.min(b.bottom, c.bottom)];
        }"""
    )


def session_state() -> str:
    with urllib.request.urlopen(BASE + "/api/state", timeout=5) as response:
        return json.load(response)["session_state"]["state"]


def turn(rec: Recorder, phase: str, timeout: float = 300) -> None:
    rec.page.keyboard.press("Enter")
    start = time.time()
    while session_state() == "idle" and time.time() - start < 10:
        rec.shot(phase)
        time.sleep(0.2)
    while session_state() != "idle" and time.time() - start < timeout:
        rec.shot(phase)
        time.sleep(0.5)
    rec.hold(phase + "_done", 2.5)


def main_sequence(page: Page, folder: Path) -> None:
    rec = Recorder(page, folder)
    page.goto(BASE + "/")
    page.wait_for_timeout(2500)
    for scenario, prefix in (("bare_llm", "bare"), ("native_tools", "tools")):
        page.select_option("#scenario-picker", scenario)
        rec.hold(f"{prefix}_scenario", 2.5)
        page.locator("#composer-input").click()
        rec.type(PROMPT, f"{prefix}_type")
        turn(rec, f"{prefix}_turn")
    rec.hold("tools_final", 2)
    rec.save()


def llm_sequence(page: Page, folder: Path) -> None:
    rec = Recorder(page, folder)
    page.goto(BASE + "/llm")
    page.wait_for_timeout(2000)
    rec.hold("llm_intro", 1.5)
    box = page.locator("textarea").first
    box.fill("")
    box.click()
    rec.type(PROMPT, "llm_type")
    page.get_by_role("button", name="Découper en tokens").click()
    rec.hold("llm_tokens", 1.5)
    for _ in range(4):  # down to the token chips and « Du texte au vecteur »
        page.mouse.wheel(0, 100)
        time.sleep(0.15)
        rec.shot("llm_scroll")
    rec.hold("llm_done", 2)
    rec.save()


if __name__ == "__main__":
    frames = Path(sys.argv[1])
    with sync_playwright() as playwright:
        browser = playwright.chromium.launch(channel="chrome")
        page = browser.new_page(viewport=VIEWPORT)
        main_sequence(page, frames / "main")
        llm_sequence(page, frames / "llm")
        browser.close()
    print(f"Images dans {frames}")
