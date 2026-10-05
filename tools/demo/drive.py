"""Drive a running WaveStack for the README demo: screenshots and a manifest per sequence.

Four sequences, one folder each under `<frames>`: `main`, the « LLM nu » scenario then « Outils
natifs » on the same prompt; `llm`, the Atelier LLM's three stages (INPUT, TRANSFORMATION,
OUTPUT) on a sentence to complete; `rag`, the Atelier RAG's guided tour; `mcp`, the Atelier MCP's
handshake with the local server. WaveStack must already run on 127.0.0.1:8420, in French, with a
local model loaded (see README.md next to this file).
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
LAB_PROMPT = "La capitale de la France est"  # a next token worth drawing, unlike « ↵ »
VIEWPORT = {"width": 1600, "height": 900}  # compose.py's highlight boxes are in these pixels
# The elements compose.py frames on the Atelier LLM, measured on each screenshot
LAB_BOXES = {
    "chips": "#token-chips > li",
    "facts": "#transfo-facts",
    "logits": "#part-logits .llm-output-logits-main",
    "token": "#part-token",
}
RAG_BOXES = {"seq": "#rag-seq", "arch": "#rag-arch", "focus": "#rag-focus"}
MCP_BOXES = {"seq": "#mcp-seq-body", "model": "#mcp-model-body"}


class Recorder:
    def __init__(self, page: Page, folder: Path, boxes: dict[str, str] | None = None) -> None:
        self.page, self.folder, self.manifest, self.t0 = page, folder, [], time.time()
        self.boxes = boxes or {}
        folder.mkdir(parents=True, exist_ok=True)
        for old in folder.glob("*.png"):
            old.unlink()
        (folder / "manifest.json").unlink(missing_ok=True)  # never a stale one after a crash

    def shot(self, phase: str) -> None:
        path = self.folder / f"{len(self.manifest):04d}.png"
        self.page.screenshot(path=str(path))
        entry = {"file": path.name, "phase": phase, "t": round(time.time() - self.t0, 2)}
        boxes = {name: element_box(self.page, selector) for name, selector in self.boxes.items()}
        boxes["answer"] = answer_box(self.page)
        entry["boxes"] = {name: box for name, box in boxes.items() if box}
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
          const top = Math.max(b.top, c.top), bottom = Math.min(b.bottom, c.bottom);
          return top < bottom ? [b.left, top, b.right, bottom] : null;  // scrolled out of view
        }"""
    )


def element_box(page: Page, selector: str) -> list[float] | None:
    """The box around every shown match, if whole in the viewport (a cut frame reads badly)."""
    return page.evaluate(
        """(selector) => {
          const rects = [...document.querySelectorAll(selector)]
            .filter((node) => node.offsetParent)
            .map((node) => node.getBoundingClientRect())
            .filter((r) => r.width);
          if (!rects.length) return null;
          const box = [
            Math.min(...rects.map((r) => r.left)), Math.min(...rects.map((r) => r.top)),
            Math.max(...rects.map((r) => r.right)), Math.max(...rects.map((r) => r.bottom)),
          ];
          return box[1] < 0 || box[3] > innerHeight ? null : box;
        }""",
        selector,
    )


def api_state() -> dict:
    with urllib.request.urlopen(BASE + "/api/state", timeout=5) as response:
        return json.load(response)


def session_state() -> str:
    return (api_state().get("session_state") or {}).get("state", "")


def turn(rec: Recorder, phase: str, timeout: float = 300) -> None:
    rec.page.keyboard.press("Enter")
    start = time.time()
    while session_state() == "idle" and time.time() - start < 10:
        rec.shot(phase)
        time.sleep(0.2)
    if session_state() == "idle":
        sys.exit(f"{phase} : le tour n'a pas démarré (message refusé ?)")
    while session_state() != "idle" and time.time() - start < timeout:
        rec.shot(phase)
        time.sleep(0.5)
    if session_state() != "idle":
        sys.exit(f"{phase} : le tour dure encore après {timeout} s")
    rec.hold(phase + "_done", 2.5)


def main_sequence(page: Page, folder: Path) -> None:
    rec = Recorder(page, folder, {"picker": "#scenario-picker"})
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


def scroll_to(rec: Recorder, section: str, phase: str) -> None:
    """Glide the page to a stage's top, filmed, as a trainer would scroll."""
    rec.page.evaluate(
        """(id) => window.scrollTo({
          top: document.getElementById(id).getBoundingClientRect().top + scrollY - 12,
          behavior: "smooth",
        })""",
        section,
    )
    for _ in range(6):
        rec.shot(phase)
        time.sleep(0.12)


def next_step(page: Page, stepper: str) -> None:
    """The ▶ of a stage's stepper, which reveals one more step of its drawing."""
    page.locator(f"#{stepper} .diagram-step-next").click()
    page.wait_for_timeout(700)


def llm_sequence(page: Page, folder: Path) -> None:
    rec = Recorder(page, folder, LAB_BOXES)
    page.goto(BASE + "/llm")
    page.wait_for_timeout(2000)
    rec.hold("llm_intro", 1.2)
    box = page.locator("#llm-prompt")
    box.fill("")
    box.click()
    rec.type(LAB_PROMPT, "llm_type")
    page.locator("#tokenize-button").click()
    page.wait_for_timeout(1200)
    rec.hold("input_text", 1)
    next_step(page, "input-stepper")  # the tokens
    rec.hold("input_tokens", 1.2)
    next_step(page, "input-stepper")  # their ids, all the model reads
    rec.hold("input_ids", 1.5)
    scroll_to(rec, "stage-transfo", "transfo_scroll")
    rec.hold("transfo_embedding", 1.5)
    next_step(page, "transfo-stepper")  # first layer: the tokens look at each other
    rec.hold("transfo_attention", 1.5)
    scroll_to(rec, "stage-output", "output_scroll")
    rec.hold("output_logits", 1.5)
    page.locator("#llm-step-button").click()
    page.wait_for_function("!document.getElementById('llm-step-append').disabled", timeout=60000)
    page.wait_for_timeout(600)
    rec.hold("output_draw", 2)
    rec.save()


def rag_sequence(page: Page, folder: Path) -> None:
    """The guided tour (« Dérouler »): no run, which would need the RAG models downloaded."""
    rec = Recorder(page, folder, RAG_BOXES)
    page.goto(BASE + "/rag")
    page.wait_for_timeout(2000)
    page.locator("button[data-mode=play]").click()
    rec.hold("rag_intro", 1)
    for _ in range(5):  # Documents to Question: BUILD, then the start of RUN
        next_step(page, "rag-stepper")
        rec.hold("rag_steps", 0.6)
    rec.hold("rag_done", 1.2)
    rec.save()


def mcp_sequence(page: Page, folder: Path) -> None:
    """The local glossary server, joined by stdio: no network needed."""
    rec = Recorder(page, folder, MCP_BOXES)
    page.goto(BASE + "/mcp")
    page.wait_for_timeout(2000)
    rec.hold("mcp_intro", 1)
    page.locator("#mcp-connect").click()
    rec.hold("mcp_handshake", 5)
    rec.hold("mcp_done", 1.2)
    rec.save()


if __name__ == "__main__":
    sequences = {
        "main": main_sequence,
        "llm": llm_sequence,
        "rag": rag_sequence,
        "mcp": mcp_sequence,
    }
    if len(sys.argv) not in (2, 3) or sys.argv[2:] and sys.argv[2] not in sequences:
        names = "|".join(sequences)
        sys.exit(f"usage : drive.py <dossier des captures> [{names}] (toutes par défaut)")
    state = api_state()
    if (state.get("session_state") or {}).get("language") != "fr":
        sys.exit("WaveStack doit tourner en français (les libellés cherchés sont en français).")
    if session_state() != "idle":
        sys.exit("WaveStack doit avoir un modèle chargé et attendre (état « idle »).")
    frames = Path(sys.argv[1])
    with sync_playwright() as playwright:
        browser = playwright.chromium.launch(channel="chrome")
        page = browser.new_page(viewport=VIEWPORT)
        for name in sys.argv[2:] or sequences:  # one alone, to replay a take that came out badly
            sequences[name](page, frames / name)
        browser.close()
    print(f"Images dans {frames}")
