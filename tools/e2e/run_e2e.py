"""End-to-end run of WaveStack's tier 1 in a headless Chromium, on the fake OpenAI model.

    uv run --with playwright==1.56.0 python tools/e2e/run_e2e.py [--only NAME ...] [--keep]

Starts `stack.running_stack`, picks the fake model at the diagnostic like a user, then
plays each scenario of `content/scenarios.yaml` and the transverse features (forced
actions, replay and compare, reset, H5). Every check is printed PASS/FAIL; a failing
scenario does not stop the next one. Screenshots go to `tools/e2e/screenshots/` (JPEG),
logs to the data dir (printed with `--keep`). Exit code 1 when a check failed.
"""

from __future__ import annotations

import argparse
import contextlib
import importlib.util
import json
import os
import re
import sys
import threading
import time
import traceback
from collections.abc import Callable
from pathlib import Path
from typing import Any

import httpx
from playwright.sync_api import Page, expect, sync_playwright
from playwright.sync_api import TimeoutError as PlaywrightTimeout

sys.path.insert(0, str(Path(__file__).resolve().parent))
from stack import (  # noqa: E402
    ANTHROPIC_MODEL,
    ANTHROPIC_PROVIDER,
    GEMINI_ENTRY_ID,
    GEMINI_MODEL,
    GEMINI_PROVIDER,
    MODEL_ENTRY_ID,
    PRICED_ENTRY_ID,
    PRICED_MODEL,
    PRICED_PROVIDER,
    REASONING_ENTRY_ID,
    REASONING_MODEL,
    SECOND_ENTRY_ID,
    SECOND_MODEL,
    Stack,
    running_stack,
)

from wavestack.models.candidates import distribution as live_distribution  # noqa: E402
from wavestack.models.candidates import dropped_by as live_dropped_by  # noqa: E402
from wavestack.models.engine import Sampling  # noqa: E402
from wavestack.rag import index as rag_index  # noqa: E402
from wavestack.session import llm_lab  # noqa: E402
from wavestack.trace.envelope import Envelope  # noqa: E402

SHOTS = Path(__file__).resolve().parent / "screenshots"
REPO = Path(__file__).resolve().parents[2]
CHROMIUM = "/opt/pw-browsers/chromium"  # fallback when the bundled revision is missing
TURN_TIMEOUT_S = 60.0


# ---------- the journal, read from /api/stream ----------


class Events:
    """Every envelope of `/api/stream`, collected by a background thread."""

    def __init__(self, url: str) -> None:
        self.items: list[dict[str, Any]] = []
        self._lock = threading.Lock()
        self._url = url
        threading.Thread(target=self._run, daemon=True).start()

    def _run(self) -> None:
        try:
            with httpx.Client(trust_env=False, timeout=httpx.Timeout(5, read=None)) as client:
                with client.stream("GET", f"{self._url}/api/stream") as response:
                    for line in response.iter_lines():
                        if line.startswith("data:"):
                            envelope = json.loads(line[5:])
                            if "seq" not in envelope:
                                continue  # `server_instance`, outside the journal
                            with self._lock:
                                self.items.append(envelope)
        except httpx.HTTPError:
            pass  # WaveStack stopped at the end of the run

    def mark(self) -> int:
        with self._lock:
            return self.items[-1]["seq"] if self.items else 0

    def since(self, seq: int, kind: str | None = None) -> list[dict[str, Any]]:
        with self._lock:
            return [e for e in self.items if e["seq"] > seq and (kind is None or e["kind"] == kind)]

    def wait(
        self,
        kind: str,
        after: int,
        pred: Callable[[dict[str, Any]], bool] = lambda e: True,
        timeout: float = TURN_TIMEOUT_S,
    ) -> dict[str, Any]:
        deadline = time.monotonic() + timeout
        while time.monotonic() < deadline:
            for e in self.since(after, kind):
                if pred(e["payload"]):
                    return e
            time.sleep(0.1)
        raise TimeoutError(f"aucun événement {kind} après seq {after} en {timeout:g} s")


# ---------- the run ----------


class Run:
    def __init__(self, page: Page, stack: Stack, events: Events) -> None:
        self.page, self.stack, self.ev = page, stack, events
        self.results: list[tuple[str, str, bool, str]] = []  # scenario, check, ok, detail
        self.known: list[tuple[str, str, str, str]] = []  # scenario, check, anomaly, detail
        self.earlier_events: list[dict[str, Any]] = []  # journals of stopped processes
        self.current = ""

    # -- bookkeeping --

    def check(self, ok: bool, what: str, detail: str = "", known: str | None = None) -> bool:
        """`known`: the anomaly this check shows, already reported (the report's id); its
        failure prints KNOWN and does not fail the run."""
        if not ok and known:
            self.known.append((self.current, what, known, detail))
            print(f"  KNOWN [{known}] {what}" + (f" — {detail}" if detail else ""))
            return False
        self.results.append((self.current, what, bool(ok), detail))
        print(f"  {'PASS' if ok else 'FAIL'} {what}" + (f" — {detail}" if detail else ""))
        return bool(ok)

    def rest_pointer(self) -> None:
        """Story 34: the pointer off every linkable element, so a capture is not dimmed by the
        linked view of whatever the last click left under it."""
        self.page.mouse.move(0, 0)
        time.sleep(0.2)  # the 150 ms fade

    def shot(self, name: str, full_page: bool = False, keep_pointer: bool = False) -> None:
        SHOTS.mkdir(parents=True, exist_ok=True)
        if not keep_pointer:
            self.rest_pointer()
        self.page.screenshot(
            path=str(SHOTS / f"{name}.jpg"), type="jpeg", quality=70, full_page=full_page
        )

    def shot_element(self, name: str, selector: str, keep_pointer: bool = False) -> None:
        """Story 33: one piece of the page only (the top bar, a pane), for a close-up."""
        SHOTS.mkdir(parents=True, exist_ok=True)
        if not keep_pointer:
            self.rest_pointer()
        self.page.locator(selector).first.screenshot(
            path=str(SHOTS / f"{name}.jpg"), type="jpeg", quality=80
        )

    def token_color(self, name: str) -> str:
        """A colour token of tokens.css, as `getComputedStyle` writes a colour (`rgb(…)`)."""
        return self.page.evaluate(_CSS_COLOR_JS, name)

    def css(self, locator, prop: str) -> str:
        return locator.evaluate(f"e => getComputedStyle(e).getPropertyValue('{prop}')")

    # -- the API, for what the UI does not show plainly --

    def api(self, method: str, path: str, body: Any = None) -> httpx.Response:
        headers = {"Origin": self.stack.app_url, "Content-Type": "application/json"}
        with httpx.Client(trust_env=False, timeout=10) as client:
            return client.request(method, f"{self.stack.app_url}{path}", headers=headers, json=body)

    def state(self) -> dict[str, Any]:
        return self.api("GET", "/api/state").json()

    def bricks_state(self) -> dict[str, Any]:
        """The last `bricks_changed` payload: cards and system prompt."""
        return self.state()["bricks_changed"]

    def bricks(self) -> dict[str, dict[str, Any]]:
        return {b["id"]: b for b in self.state()["bricks_changed"]["bricks"]}

    # -- UI gestures --

    def wait_replayed(self, timeout: float = 30) -> None:
        """Barrier after a navigation: the page replayed the journal up to its `/api/state`
        snapshot (app.js marks `data-journal-replayed`); acting before races the replay."""
        expect(self.page.locator("body[data-journal-replayed]")).to_be_attached(
            timeout=timeout * 1000
        )

    def goto_app(self) -> None:
        self.page.goto(f"{self.stack.app_url}/")
        self.wait_replayed()

    def reload_app(self) -> None:
        self.page.reload()
        self.wait_replayed()

    def wait_idle(self, timeout: float = 30) -> None:
        self.wait_replayed(timeout)
        # The page's HTML enables the button before app.js renders: wait for the programme.
        expect(self.page.locator("#scenario-picker option").nth(1)).to_be_attached(
            timeout=timeout * 1000
        )
        expect(self.page.locator("#composer-send")).to_be_enabled(timeout=timeout * 1000)

    def launch(self, scenario_id: str) -> None:
        self.wait_idle()
        seq = self.ev.mark()
        self.page.select_option("#scenario-picker", scenario_id)
        self.ev.wait("scenario_changed", seq, lambda p: p["active"] == scenario_id, 30)
        # MCP connections run after the launch; wait until they are all answered.
        time.sleep(0.5)
        for started in self.ev.since(seq, "mcp_connect_started"):
            server = started["payload"].get("server")
            self.ev.wait("mcp_connect_ended", seq, lambda p, s=server: p["server"] == s, 45)
        self.wait_idle()

    def send(self, text: str, expect_approval: bool = False) -> dict[str, Any]:
        """Types and sends `text`; returns `turn_ended` (or `approval_requested`)."""
        self.wait_idle()
        seq = self.ev.mark()
        self.page.fill("#composer-input", text)
        self.page.press("#composer-input", "Enter")
        self.wait_turn_started(seq, "l'envoi")
        if expect_approval:
            return self.ev.wait("approval_requested", seq)
        return self.ev.wait("turn_ended", seq)

    def replay(self) -> dict[str, Any]:
        self.wait_idle()
        seq = self.ev.mark()
        self.page.click("#replay-last")
        self.wait_turn_started(seq, "« Rejouer »")
        return self.ev.wait("turn_ended", seq)

    def wait_turn_started(self, seq: int, gesture: str, timeout: float = 5) -> None:
        """A gesture that starts no turn says why: the composer's state and its reason."""
        try:
            self.ev.wait("turn_started", seq, timeout=timeout)
        except TimeoutError:
            composer = self.page.evaluate(
                "() => { const q = (s) => document.querySelector(s);"
                " return { input: q('#composer-input').disabled,"
                " send: q('#composer-send').disabled,"
                " value: q('#composer-input').value,"
                " reason: q('#composer-reason').hidden ? ''"
                " : q('#composer-reason').textContent }; }"
            )
            raise TimeoutError(
                f"{gesture} n'a lancé aucun tour en {timeout:g} s : champ "
                f"{'désactivé' if composer['input'] else 'actif'}, bouton « Envoyer » "
                f"{'désactivé' if composer['send'] else 'actif'}, saisie « {composer['value']} », "
                f"#composer-reason « {composer['reason']} »"
            ) from None

    def last_answer(self) -> str:
        time.sleep(0.3)  # the last render after `turn_ended`
        return self.page.locator("#chat .bubble-model").last.inner_text()

    def card(self, name: str):
        return self.page.locator("article.brick-card").filter(
            has=self.page.locator(".brick-name", has_text=name)
        )

    def parent_off(self, brick: str) -> dict[str, Any]:
        """Story 22: the sub-options of a card, as its brick off shows them."""
        self.open_options(brick)
        details = self.card(brick).locator("details.brick-options")
        return details.evaluate(
            "d => ({ summary: d.querySelector('summary').textContent,"
            " switches: [...d.querySelectorAll('input.brick-toggle')].map(t => ({"
            " key: t.dataset.focusKey, disabled: t.disabled,"
            " title: t.closest('.brick-option').title,"
            " described: t.getAttribute('aria-description') || '' })) })"
        )

    def set_brick(self, name: str, on: bool) -> None:
        toggle = self.card(name).locator(".brick-head input.brick-toggle")
        if toggle.is_checked() != on:
            seq = self.ev.mark()
            toggle.click()
            self.ev.wait("bricks_changed", seq, timeout=10)
            time.sleep(0.3)

    def open_options(self, brick: str) -> None:
        """Unfolds the card's option list. D3 (2026-10-01): « Afficher les actions forcées »
        unfolds it too, at the next render; a click landing just after that render folds it
        back, so the list is checked open, and clicked again if not."""
        details = self.card(brick).locator("details.brick-options")
        for _ in range(3):
            if details.get_attribute("open") is None:
                details.locator("summary").click()
            opened, _ = self.poll(lambda: details.get_attribute("open") is not None, 1)
            if opened:
                return
        raise AssertionError(f"la liste d'options de la carte {brick} reste repliée")

    def set_option(self, brick: str, option: str, on: bool) -> None:
        self.open_options(brick)
        toggle = (
            self.card(brick)
            .locator("label.brick-option", has_text=option)
            .locator("input.brick-toggle")
        )
        if toggle.is_disabled():  # story 22: a brick off greys its sub-options
            raise AssertionError(
                f"« {option} » est désactivé : allumez la brique {brick} avant de régler "
                "ses options"
            )
        if toggle.is_checked() != on:
            seq = self.ev.mark()
            toggle.click()
            self.ev.wait("bricks_changed", seq, timeout=10)
            time.sleep(0.3)

    def show_forced(self, on: bool = True) -> None:
        toggle = self.page.locator("label.force-toggle input")
        if toggle.is_checked() != on:
            toggle.click()

    def arm(self, button_label: str, preset: str | None = None) -> dict[str, Any]:
        seq = self.ev.mark()
        button = self.page.get_by_role("button", name=button_label)
        needs_form = button.get_attribute("aria-expanded") is not None
        button.click()
        if needs_form:
            form = self.page.locator(".force-form")
            expect(form).to_be_visible(timeout=5000)
            if preset is not None:
                form.locator("select").first.select_option(label=preset)
            form.get_by_role("button", name="Armer").click()
        return self.ev.wait("armed_actions_changed", seq, lambda p: bool(p["actions"]), timeout=10)

    def poll(self, condition: Callable[[], bool], timeout: float = 15) -> tuple[bool, float]:
        """Whether `condition` becomes true within `timeout`, and after how long."""
        started = time.monotonic()
        while True:
            if condition():
                return True, time.monotonic() - started
            if time.monotonic() - started > timeout:
                return False, timeout
            time.sleep(0.1)

    def fake_calls(self) -> list[dict[str, Any]]:
        return self.stack.fake_requests()


# ---------- lot 3 of 2026-10-04: the cards of « Diagnostic et modèles » ----------


def _goto_diagnostic(r: Run) -> None:
    """`/diagnostic`, once its cloud cards are drawn (the local ones may still be searched)."""
    r.page.goto(f"{r.stack.app_url}/diagnostic")
    expect(r.page.locator("#cloud-models .model-card").first).to_be_visible(timeout=20_000)


def _card(r: Run, value: str):
    """The card holding the source `value` (`cloud:{id}`, `server:{ref}`)."""
    return r.page.locator(f'.model-card[data-values~="{value}"]')


def _cloud_card(r: Run, model: str):
    """A cloud card by its model's name."""
    return r.page.locator("#cloud-models .model-card").filter(
        has=r.page.locator(".model-card-name", has_text=re.compile(rf"^{re.escape(model)}$"))
    )


def _unfold(card):
    """Unfolds `card` (a click on its head) unless it is; returns it."""
    head = card.locator(".model-card-head")
    expect(head).to_be_visible(timeout=20_000)
    if head.get_attribute("aria-expanded") != "true":
        head.click()
    expect(card.locator(".model-card-detail")).to_be_visible(timeout=5000)
    return card


def _open_checks(r: Run) -> None:
    """The checks panel open by the user's choice (a closed then open summary): it stays so."""
    panel = r.page.locator("#checks-panel")
    summary = panel.locator("summary")
    if panel.get_attribute("open") is not None:
        summary.click()
    summary.click()
    expect(panel).to_have_attribute("open", "", timeout=5000)


_CARD_JS = """(card) => {
  const head = card.querySelector('.model-card-head');
  const pill = head.querySelector('.state-pill');
  const facts = {};
  for (const dt of card.querySelectorAll('.card-facts dt')) {
    const dd = dt.nextElementSibling;
    const fact = [...dd.querySelectorAll('.card-fact')].map((x) => x.textContent).join(' | ');
    const why = [...dd.querySelectorAll('.card-why')].map((x) => x.textContent).join(' | ');
    facts[dt.textContent] = [fact || dd.textContent, why];
  }
  const group = card.closest('.publisher-group');
  return {
    name: card.querySelector('.model-card-name').textContent,
    origin: card.querySelector('.model-card-origin').textContent,
    size: head.querySelector('.model-card-size').textContent,
    state: pill.dataset.state,
    state_text: pill.textContent,
    publisher: group?.querySelector('.publisher-group-name')?.textContent ?? '',
    expanded: head.getAttribute('aria-expanded'),
    label: head.getAttribute('aria-label'),
    facts,
    text: card.innerText,
  };
}"""


def _card_info(r: Run, value: str) -> dict[str, Any]:
    """A card unfolded, by one of its sources: its head, its publisher, its state, and each
    fact of its detail (« Fenêtre », « Prix »…) as [value, reason], spaces made plain."""
    card = _unfold(_card(r, value))
    info = card.evaluate(_CARD_JS)
    plain = lambda t: t.replace("\u202f", " ").replace("\xa0", " ")  # noqa: E731
    info["facts"] = {k: [plain(v[0]), plain(v[1])] for k, v in info["facts"].items()}
    for key in ("name", "origin", "size", "text", "state_text"):
        info[key] = plain(info[key])
    return info


def _api_cards(r: Run) -> list[dict[str, Any]]:
    """Each card of `/api/diagnostic`, with its group and its sources (`members`)."""
    cards = []
    for group in r.api("GET", "/api/diagnostic").json()["models"]["groups"]:
        by_value = {m["value"]: m for m in group["models"]}
        for card in group["cards"]:
            members = [by_value[v] for v in card["source_values"]]
            cards.append({**card, "group": group, "members": members})
    return cards


# ---------- scenarios ----------


def s_diagnostic(r: Run) -> None:
    page = r.page
    _goto_diagnostic(r)
    # Lot 3 of 2026-10-04: a card, unfolded by a click on its head.
    row = _unfold(_cloud_card(r, "wavestack-fake"))
    r.check(
        "Clé fournie par la variable WAVESTACK_FAKE_API_KEY" in row.inner_text(),
        "la carte du faux modèle, dépliée, indique la clé lue dans key_env",
    )
    r.check("e2e-fake-key" not in page.content(), "la valeur de la clé n'apparaît pas dans la page")
    row.get_by_role("button", name="Tester").click()
    expect(row.locator(".card-message.is-ok")).to_contain_text("Test réussi", timeout=20_000)
    expect(row.locator(".model-card-head .state-pill")).to_have_text("Test réussi")
    r.check(True, "« Tester » réussit (appel d'outil get_datetime reçu), pastille « Test réussi »")
    row.get_by_role("button", name="Choisir ce modèle…").click()
    dialog = page.locator("#cloud-warning")
    expect(dialog).to_be_visible()
    r.check(
        "Faux fournisseur (e2e)" in dialog.inner_text(),
        "l'avertissement cloud nomme le fournisseur",
    )
    r.shot("01-diagnostic-avertissement-cloud")
    page.locator("#cloud-warning-confirm").click()
    expect(row.locator(".model-card-head .state-pill")).to_have_text("Actif", timeout=20_000)
    r.check(
        "is-active" in (row.get_attribute("class") or "")
        and row.locator(".model-card-head").get_attribute("aria-expanded") == "true",
        "« Utiliser ce modèle » : la carte passe à « Actif », bordure épaisse, toujours dépliée",
    )
    _diagnostic_cards(r)
    # Story 2 (2026-09-30): « Ouvrir WaveStack » gave way to « Atelier » of the shared bar.
    ok, took = r.poll(lambda: bool(r.api("GET", "/api/diagnostic").json().get("ready")), 20)
    r.check(ok, "diagnostic prêt", f"{took:.1f} s")
    page.locator('.site-nav > a[href="/"]:not(.site-nav-brand)').click()
    page.wait_for_url(f"{r.stack.app_url}/", timeout=10_000)
    expect(page.locator("#model-indicator")).to_contain_text("wavestack-fake", timeout=20_000)
    r.check(True, "l'indicateur de modèle de la barre de l'atelier montre le faux modèle")
    # Lot 1 of 2026-10-04 (D2): « Harnais » current, the full title in <title> and in a
    # visually hidden h1 (no height taken).
    h1 = page.locator("h1")
    r.check(
        page.title() == "WaveStack — Atelier Harnais"
        and h1.count() == 1
        and h1.text_content() == "Atelier Harnais"
        and (h1.bounding_box() or {"height": 0})["height"] <= 1
        and page.locator('.site-nav a[aria-current="page"]').inner_text() == "Harnais",
        "atelier : titre « WaveStack — Atelier Harnais », h1 masqué, onglet « Harnais » courant",
        page.title(),
    )
    r.wait_idle()
    _key_applied_at_once(r)


def _key_applied_at_once(r: Run) -> None:
    """Correction A (2026-10-05): a key saved at the diagnostic applies without a restart,
    and the harness page reads its model list again on `effect_applied {api_key_set}`."""
    r.page.wait_for_timeout(1_000)  # the page's own first reads of the list are done
    with r.page.expect_request(
        lambda q: q.method == "GET" and q.url.endswith("/api/diagnostic"), timeout=10_000
    ):
        answer = r.api(
            "POST", "/api/intentions/set_api_key", {"id": MODEL_ENTRY_ID, "key": "e2e-fake-key"}
        )
    r.check(
        answer.status_code == 200
        and "sans relancer" in str(answer.json().get("message_text"))
        and "e2e-fake-key" not in answer.text,
        "clé enregistrée au diagnostic : « sans relancer », l'atelier relit sa liste de modèles",
        answer.text[:200],
    )


def _diagnostic_cards(r: Run) -> None:
    """Lot 3 of 2026-10-04: the checks folded once green, opened at a warning; the columns at
    1280 and 1440 px (and 2 when zoomed, 1 under 640 px); one card unfolded at a time, Échap
    folding it back with the focus on its head; logos served by the page."""
    page = r.page
    _goto_diagnostic(r)
    r.poll(lambda: "en cours" not in page.inner_text("#checks-summary"), 15)
    summary = page.inner_text("#checks-summary")
    states = page.eval_on_selector_all("#checks > li", "ls => ls.map(l => l.className)")
    ok, _ = r.poll(lambda: page.locator("#checks-panel").get_attribute("open") is not None, 5)
    r.check(
        summary.startswith("· ")
        and ("avertissement" in summary or "échec" in summary or "contrôles OK" in summary)
        and (ok == any(s != "ok" for s in states)),
        "contrôles : résumé dans le panneau, ouvert d'office à un avertissement",
        f"{summary} · {states}",
    )
    columns = []
    for width, zoom in ((1280, 1), (1440, 1), (1280, 1.6), (600, 1)):
        page.set_viewport_size({"width": round(width / zoom), "height": 900})
        time.sleep(0.3)
        columns.append(
            page.eval_on_selector(
                "#cloud-models .model-grid",
                "g => getComputedStyle(g).gridTemplateColumns.split(' ').length",
            )
        )
    page.set_viewport_size({"width": 1600, "height": 1000})
    r.check(
        columns[0] == 3 and columns[1] in (4, 5) and columns[2] == 2 and columns[3] == 1,
        "grille : 3 colonnes à 1280 px, 4 ou 5 à 1440 px, 2 en projection agrandie, 1 sous 640 px",
        str(columns),
    )
    heads = page.locator("#cloud-models .model-card-head")
    first, second = heads.nth(0), heads.nth(1)
    first.click()
    second.click()
    expanded = page.locator('.model-card-head[aria-expanded="true"]')
    r.check(
        expanded.count() == 1 and second.get_attribute("aria-expanded") == "true",
        "une seule carte dépliée à la fois",
    )
    region = page.locator(".model-card-detail")
    r.check(
        region.get_attribute("role") == "region"
        and second.get_attribute("aria-controls") == region.get_attribute("id"),
        "carte dépliée : une région nommée, désignée par l'en-tête (aria-controls)",
    )
    page.keyboard.press("Escape")
    focused = page.evaluate("() => document.activeElement?.className")
    r.check(
        expanded.count() == 0 and focused == "model-card-head",
        "Échap replie la carte, le focus revient sur son en-tête",
        str(focused),
    )
    logos = page.eval_on_selector_all(
        ".model-logo img", "is => is.map(i => [i.getAttribute('src'), i.naturalWidth])"
    )
    r.check(
        bool(logos) and all(src.startswith("/static/logos/") and w > 0 for src, w in logos),
        "logos servis par la page (static/logos), chargés",
        str(logos[:4]),
    )
    r.shot("01b-diagnostic-cartes", full_page=True)


def s_bare_llm(r: Run) -> None:
    r.launch("bare_llm")
    guide = r.page.locator("#scenario-info-popover")
    r.check(
        r.page.locator("#scenario-info").is_visible()
        and not guide.is_visible()
        and "LLM nu" in guide.text_content(),
        "consigne derrière le « i » de la Vue humain, fermée au lancement",
    )
    _parent_off_at_launch(r)
    before = len(r.fake_calls())
    r.page.locator("#suggested-prompts button").first.click()
    r.check(
        r.page.input_value("#composer-input") == "Quelle heure est-il ?",
        "la puce de prompt suggéré remplit le champ",
    )
    time.sleep(0.5)
    r.check(len(r.fake_calls()) == before, "la puce n'envoie rien au modèle")
    seq = r.ev.mark()
    r.page.press("#composer-input", "Enter")
    ended = r.ev.wait("turn_ended", seq)
    r.check(ended["payload"]["status"] == "completed", "tour terminé", ended["payload"]["status"])
    body = r.fake_calls()[-1]
    r.check(not body.get("tools"), "aucun outil envoyé au LLM nu")
    r.check(
        [m["role"] for m in body["messages"]] == ["user"],
        "LLM nu : un seul message (utilisateur), pas de prompt système",
        str([m["role"] for m in body["messages"]]),
    )
    r.check("horloge" in r.last_answer(), "la réponse du faux modèle s'affiche")
    rendered = r.state().get("context_rendered") or {}
    r.check(bool(rendered), "Contexte LLM : context_rendered disponible")
    total = r.page.locator("#ctx .ctx-total").inner_text()
    r.check(
        "(total renvoyé par le fournisseur)" in total and "somme des segments" not in total,
        "en-tête de Contexte LLM : le total du fournisseur, sans « somme des segments » (A3)",
        total,
    )
    r.check(
        re.match(r"Tour \d+ · ", total) is not None,
        "en-tête de Contexte LLM : « Tour N », comme Orchestration (A3)",
        total,
    )
    r.shot("02-llm-nu")
    r.send("Bonjour [sans-usage]")
    total = r.page.locator("#ctx .ctx-total").inner_text()
    r.check(
        "(somme des segments)" in total and "fournisseur" not in total,
        "sans `usage` du fournisseur : « (somme des segments) » seule (A3)",
        total,
    )
    r.send("Bonjour [raisonne]")
    details = r.page.locator("#chat .bubble-model").last.locator("details.reasoning-block")
    r.check(
        details.count() == 1 and details.get_attribute("open") is None,
        "un champ `reasoning` du fournisseur s'affiche replié",
    )
    # Story 32: the call's reflection, then its answer, each on its own background.
    time.sleep(0.3)
    blocks = r.page.locator("#ctx .ctx-call").last.locator(".ctx-produced")
    found = blocks.evaluate_all(
        "bs => bs.map(b => [b.classList.contains('is-reasoning') ? 'reasoning'"
        " : b.classList.contains('is-answer') ? 'answer' : 'other',"
        " getComputedStyle(b).backgroundColor])"
    )
    kinds = [k for k, _ in found]
    colours = dict(found)
    r.check(
        kinds[:2] == ["reasoning", "answer"]
        and colours["reasoning"] == r.token_color("--color-reasoning-soft")
        and colours["answer"] != colours["reasoning"],
        "Contexte LLM : la réflexion (--color-reasoning-soft) précède la réponse, sur un "
        "autre fond",
        str(found),
    )
    total = r.page.locator("#ctx .ctx-total").inner_text()
    r.check(re.match(r"Tour \d+ · ", total) is not None, "« Tour N · » toujours en tête", total)
    _show_reasoning_option(r)
    _braces_stay_text(r, "mode chat")


def _show_reasoning_option(r: Run) -> None:
    """E053 (story 5 of the deferred leftovers): « Afficher le raisonnement » unticked hides
    the reasoning block of the Vue humain, never Contexte LLM's; the choice survives a reload;
    ticked again, the block comes back."""
    toggle = r.page.locator("#show-reasoning")
    chat_blocks = r.page.locator("#chat .bubble-model").last.locator("details.reasoning-block")
    ctx_reasoning = r.page.locator("#ctx .ctx-call").last.locator(".ctx-produced.is-reasoning")
    toggle.uncheck()
    try:
        hidden, _ = r.poll(lambda: chat_blocks.count() == 0, 5)
        r.check(
            hidden and ctx_reasoning.count() >= 1,
            "E053 : « Afficher le raisonnement » décoché, plus de bloc dans la Vue humain ; "
            "Contexte LLM garde la réflexion",
            f"blocs Vue humain {chat_blocks.count()}, "
            f"réflexions Contexte LLM {ctx_reasoning.count()}",
        )
        stored = r.page.evaluate("() => localStorage.getItem('wavestack.showReasoning')")
        r.reload_app()
        still, _ = r.poll(
            lambda: r.page.locator("#chat .bubble-model").count() > 0 and chat_blocks.count() == 0,
            10,
        )
        r.check(
            stored == "0" and still and not toggle.is_checked(),
            "E053 : le choix est gardé au rechargement (option décochée, aucun bloc)",
            f"localStorage {stored!r}, case {'cochée' if toggle.is_checked() else 'décochée'}",
        )
    finally:
        toggle.check()  # the next scenarios show the reasoning, as by default
    shown, _ = r.poll(lambda: chat_blocks.count() == 1, 5)
    r.check(shown, "E053 : recoché, le bloc de raisonnement revient dans la Vue humain")


def _parent_off_at_launch(r: Run) -> None:
    """Story 22: « Raisonnement » heads the panel; the bricks off at launch grey their
    sub-options (MCP's lazy loading too), with the reason on hover and « brique éteinte »."""
    first = r.page.locator("article.brick-card").first.locator(".brick-name").inner_text()
    r.check(first == "Raisonnement", "panneau des briques : « Raisonnement » en tête", first)
    # X1: MCP off in lazy loading. The session still accepts the mode, brick off (API);
    # restored whatever happens, so that no later scenario inherits it.
    seq = r.ev.mark()
    lazy_on = r.api("POST", "/api/intentions/mcp_mode", {"lazy": True})
    try:
        r.ev.wait("bricks_changed", seq, timeout=10)
        time.sleep(0.3)
        _parent_off_cards(r, lazy_on)
    finally:
        seq = r.ev.mark()
        r.api("POST", "/api/intentions/mcp_mode", {"lazy": False})
        r.ev.wait("bricks_changed", seq, timeout=10)


def _parent_off_cards(r: Run, lazy_on: httpx.Response) -> None:
    cards = r.bricks()
    r.check(
        lazy_on.status_code == 200 and cards["mcp"]["mode"] == "lazy",
        "brique MCP éteinte : la session accepte le lazy loading (API inchangée)",
        str(lazy_on.status_code),
    )
    for brick_id in ("mcp", "tools", "skills", "hooks"):
        card = cards[brick_id]
        label = card["label_text"]
        expected = (
            card["reason_text"] or f"La brique {label} est indisponible."
            if not card["available"]
            else f"Activez la brique {label} pour régler cette option."
        )
        seen = r.parent_off(label)
        switches = seen["switches"]
        r.check(
            not card["wanted"]
            and bool(switches)
            and all(
                sw["disabled"] and sw["title"] == expected and sw["described"] == expected
                for sw in switches
            )
            and "brique éteinte" in seen["summary"],
            f"brique {label} éteinte : sous-options désactivées, raison au survol, "
            "« brique éteinte » dans le résumé",
            f"{seen['summary']} · {len(switches)} interrupteurs · {expected}",
        )
        if brick_id == "mcp":
            lazy = r.card(label).locator('input[data-focus-key="option:mcp:lazy"]')
            r.check(
                lazy.is_disabled() and card["lazy_label_text"] not in seen["summary"],
                "MCP éteint : « Lazy loading » désactivé, le résumé ne le montre plus actif",
                f"mode {card['mode']} · {seen['summary']}",
            )
        else:  # folded again: only MCP's list stays open for the capture
            r.card(label).locator("details.brick-options").evaluate("d => { d.open = false; }")


def s_short_memory(r: Run) -> None:
    r.launch("short_memory")
    prompts = [
        "Je m'appelle Pascal et je suis consultant en cybersécurité.",
        "Comment je m'appelle, et quel est mon métier ?",
    ]
    r.send(prompts[0])
    r.send(prompts[1])
    r.check("Pascal" in r.last_answer(), "mémoire active : le prénom revient", r.last_answer())
    r.check(len(r.fake_calls()[-1]["messages"]) >= 3, "l'historique est réinjecté")
    r.set_brick("Mémoire courte", False)
    r.send(prompts[1])
    r.check("Je ne sais pas" in r.last_answer(), "mémoire éteinte : l'oubli", r.last_answer())


def s_system_prompt(r: Run) -> None:
    r.launch("system_prompt")
    r.send("Présente-toi en quelques phrases.")
    first = r.fake_calls()[-1]
    r.check(first["messages"][0]["role"] == "system", "le prompt système part en tête du contexte")
    r.page.click("#edit-system-prompt")
    save = r.page.locator("#drawer-save")
    status = r.page.locator("#drawer-status")
    r.check(
        save.is_disabled(), "tiroir du prompt système : « Enregistrer » désactivé, texte inchangé"
    )
    r.page.fill("#drawer-text", "Réponds toujours en une phrase, comme un pirate.")
    r.check(save.is_enabled(), "texte modifié : « Enregistrer » actif")
    r.page.click("#drawer-save")
    try:
        expect(status).to_contain_text("Prompt système enregistré", timeout=5000)
        confirmed = True
    except AssertionError:
        confirmed = False
    r.check(
        confirmed and status.get_attribute("role") == "status" and save.is_disabled(),
        "« Enregistrer » : « Prompt système enregistré. » (role=status), bouton de nouveau "
        "désactivé",
        status.inner_text() or "(aucun message)",
    )
    r.page.type("#drawer-text", " ")
    r.check(
        status.inner_text() == "" and save.is_enabled(),
        "saisie suivante : la confirmation s'efface, « Enregistrer » redevient actif",
    )
    r.page.fill("#drawer-text", "Réponds toujours en une phrase, comme un pirate.")
    r.check(save.is_disabled(), "texte revenu à celui enregistré : « Enregistrer » désactivé")
    if r.page.locator("#edit-drawer").is_visible():
        r.page.click("#drawer-close")
    ended = r.replay()
    r.check(ended["payload"]["status"] == "completed", "rejeu du dernier prompt terminé")
    r.check("Arrr" in r.last_answer(), "le prompt modifié change la réponse", r.last_answer())
    sent = r.fake_calls()[-1]["messages"]
    users = [m for m in sent if m["role"] == "user"]
    r.check(
        len(users) == 1 and not any(m["role"] == "assistant" for m in sent),
        "rejeu : le tour d'origine ne revient pas dans l'historique (AD-17)",
        str([m["role"] for m in sent]),
    )
    badge = r.page.locator("#chat .replay-badge")
    r.check(badge.count() >= 1, "badge « Rejeu » sur le tour rejoué")
    r.page.click("#compare-turns")
    heading = r.page.locator("#ctx .ctx-heading", has_text="Comparaison de tours")
    r.check(heading.is_visible(), "« Comparer » ouvre la comparaison de tours")
    r.shot("04-prompt-systeme-rejeu-comparer")
    r.page.locator("#ctx").get_by_role("button", name="Fermer").click()
    _default_compare_pair(r)

    # Story 22: « Rétablir le prompt par défaut » confirms too.
    r.page.click("#edit-system-prompt")
    r.page.click("#drawer-reset")
    try:
        expect(status).to_contain_text("Prompt par défaut rétabli", timeout=5000)
        restored = True
    except AssertionError:
        restored = False
    r.check(
        restored and save.is_disabled() and r.bricks_state()["system_prompt"]["is_default"],
        "« Rétablir » : « Prompt par défaut rétabli. », « Enregistrer » désactivé",
        status.inner_text() or "(aucun message)",
    )
    r.page.click("#drawer-close")


def _default_compare_pair(r: Run) -> None:
    """E042 (restes différés, story 6): one more turn after the replay; « Comparer » still
    opens on the replayed turn and its origin (the origin on the left), not on the two last
    turns."""
    page = r.page
    r.send("Merci.")
    replays = [e for e in r.ev.since(0, "turn_started") if e["payload"].get("replay_of")]
    origin, replay = (
        (replays[-1]["payload"]["replay_of"], replays[-1]["turn_id"]) if replays else ("", "")
    )
    _turn_rendered_ended(r)
    page.click("#compare-turns")
    selects = page.locator("#ctx .turn-compare-head select")
    expect(selects).to_have_count(2, timeout=5000)
    pair = (selects.nth(0).input_value(), selects.nth(1).input_value())
    last = r.ev.since(0, "turn_started")[-1]["turn_id"]
    r.check(
        bool(replays) and pair == (origin, replay),
        "« Comparer » après un tour de plus : le tour rejoué face à son origine (l'origine à "
        "gauche), pas les deux derniers tours",
        f"paire {pair} · attendu {(origin, replay)} · dernier tour {last}",
    )
    page.locator("#ctx").get_by_role("button", name="Fermer").click()


# ---------- story 32: Contexte LLM, each call what it read then what it produced ----------

_CTX_CALLS_JS = """() => [...document.querySelectorAll('#ctx .ctx-call')].map((c) => {
  const seen = c.querySelector('details.ctx-seen');
  return {
    id: c.dataset.callId,
    title: c.querySelector('.ctx-call-title')?.textContent ?? '',
    head: c.querySelector('.ctx-call-head')?.textContent ?? '',
    seen: seen ? { open: seen.open, summary: seen.querySelector('summary').textContent } : null,
    exact: [...c.querySelectorAll('pre.ctx-exact')].map((p) => p.textContent),
  };
})"""
_CALL_FIGURES = re.compile(
    r"Lu : ≈? ?[\d\u202f\u00a0]+ tokens · évalués : (non communiqué|[\d\u202f\u00a0]+) · "
    r"produits : ≈? ?[\d\u202f\u00a0]+"
)
_SEEN_SUMMARY = re.compile(
    r"Déjà lu à l'appel précédent · \d+ sections? · [\d\u202f\u00a0]+ tokens"
)


def _ctx_calls(r: Run) -> list[dict[str, Any]]:
    time.sleep(0.3)  # the last render after `turn_ended`
    return r.page.evaluate(_CTX_CALLS_JS)


def _ctx_mode(r: Run, label: str) -> None:
    """Story 32: « Lecture groupée », « Texte exact » or « Corps JSON » (remembered by the
    browser: every scenario that switches goes back to « Lecture groupée »)."""
    group = r.page.get_by_role("group", name="Affichage du contexte")
    group.get_by_role("button", name=label, exact=True).click()
    expect(group.get_by_role("button", name=label, exact=True)).to_have_attribute(
        "aria-pressed", "true", timeout=5000
    )


def _ctx_focus_shot(r: Run, name: str) -> None:
    """Contexte LLM in focus mode, for a capture of its calls, then back to the grid."""
    focus = r.page.locator('.pane[data-pane="ctx"] .pane-focus')
    focus.click()
    time.sleep(0.3)
    r.shot(name)
    focus.click()
    time.sleep(0.2)


def _braces_stay_text(r: Run, where: str) -> None:
    """Story 32: a message holding a cut JSON and braces (`{"a": ` and `{x}`): the pane still
    renders, the text is shown as sent, no JSON tree for it."""
    seq = r.ev.mark()
    ended = r.send('Lis ceci : {"a": et {x}')
    r.check(ended["payload"]["status"] == "completed", f"{where} : tour avec des accolades")
    rendered = r.ev.since(seq, "context_rendered")
    calls = _ctx_calls(r)
    section = (
        r.page.locator("#ctx .ctx-call")
        .last.locator(".ctx-section")
        .filter(has=r.page.locator(".ctx-section-label", has_text="Message de l'utilisateur"))
        .last
    )
    text = section.locator(".ctx-section-text").inner_text() if section.count() else ""
    r.check(
        bool(calls)
        and calls[-1]["id"] == rendered[-1]["call_id"]
        and '{"a": et {x}' in text
        and section.locator(".json-tree").count() == 0,
        f'{where} : `{{"a": ` et `{{x}}` restent du texte, sans arbre, le volet s\'affiche',
        text[:120],
    )


def _cache_not_reused(r: Run) -> None:
    """Lot 1 of 2026-10-04, in local text mode (the ids of the fake llama-server, AD-4): the
    system message changed between two turns (« Prompt système » switched), the next turn's
    first call does not extend the engine's cache. `prefix_not_reused` carries `again_tokens`;
    Orchestration's « Cache non réutilisé » says « <cause> · N tokens relus », folded at the
    turn's end, its message on a click."""
    page = r.page
    was = bool(r.bricks()["system_prompt"]["wanted"])
    r.set_brick("Prompt système", not was)
    try:
        seq = r.ev.mark()
        ended = r.send("Et maintenant ?")
        events = [e["payload"] for e in r.ev.since(seq, "prefix_not_reused")]
        payload = events[0] if events else {}
        again = payload.get("again_tokens")
        r.check(
            ended["payload"]["status"] == "completed"
            and len(events) == 1
            and payload.get("cause") == "system"
            and isinstance(again, int)
            and again > 0,
            "cache : « Prompt système » basculé entre deux tours, un `prefix_not_reused` "
            "(cause « system ») avec `again_tokens`",
            str(events)[:300],
        )
        if not payload:
            return
        catalogue = _ui_catalogue("fr")
        number = page.evaluate("n => new Intl.NumberFormat('fr-FR').format(n)", again)
        figure = " · ".join(
            [
                catalogue["main.orch.prefix_causes.system"],
                catalogue[f"main.orch.rows.again_tokens.{'one' if again == 1 else 'other'}"].format(
                    count=number
                ),
            ]
        )
        row = (
            _turn_group(r, ended["turn_id"])
            .locator(".turn-step")
            .filter(has=page.locator(".turn-step-name", has_text="Cache non réutilisé"))
        )
        expect(row).to_have_count(1, timeout=5000)
        shown = row.locator(".turn-step-figure").inner_text()
        folded = row.locator(".turn-step-line").get_attribute("aria-expanded") == "false"
        r.check(
            shown == figure and folded and row.locator(".turn-step-body").count() == 0,
            "Orchestration : « Cache non réutilisé », figure « <cause> · N tokens relus », "
            "repliée à la fin du tour",
            f"{shown!r} · attendu {figure!r} · repliée {folded}",
        )
        row.locator(".turn-step-line").click()
        body = row.locator(".turn-step-body")
        expect(body).to_be_visible(timeout=5000)
        said = " ".join(body.inner_text().split())
        r.check(
            " ".join(payload["message_text"].split()) in said,
            "un clic déplie la ligne et montre son message",
            said[:200],
        )
        follow = page.locator("#follow-live")
        if follow.is_visible():
            follow.click()  # the frozen view back to live, for what follows
    finally:
        r.set_brick("Prompt système", was)


def _read_and_produced(r: Run, seq: int) -> None:
    """Story 32, « Quelle heure est-il ? » with the fake cloud: two numbered calls, the second
    folding what the first read and showing the tool result as new; what each produced, on
    its own background; « Texte exact » equal to the body sent; « Corps JSON » as a tree."""
    page = r.page
    calls = _ctx_calls(r)
    titles = [c["title"] for c in calls]
    r.check(
        titles == ["Appel 1 sur 2", "Appel 2 sur 2"],
        "Contexte LLM : deux appels, « Appel 1 sur 2 » et « Appel 2 sur 2 »",
        str(titles),
    )
    r.check(
        bool(calls) and all(_CALL_FIGURES.search(c["head"]) for c in calls),
        "chaque appel : « Lu : n tokens · évalués : … · produits : n »",
        " | ".join(c["head"] for c in calls),
    )
    seen = calls[-1]["seen"] if calls else None
    r.check(
        len(calls) == 2
        and calls[0]["seen"] is None
        and seen is not None
        and not seen["open"]
        and _SEEN_SUMMARY.search(seen["summary"]) is not None,
        "appel 2 : le déjà-lu replié (« Déjà lu à l'appel précédent · k sections · n tokens ») ;"
        " appel 1 : rien de replié",
        str(seen),
    )
    first, second = page.locator("#ctx .ctx-call").nth(0), page.locator("#ctx .ctx-call").nth(1)
    new = second.locator(
        ".ctx-section.is-new", has=page.locator(".ctx-new-badge", has_text="Nouveau")
    ).filter(has_text="Résultats d'outils")
    r.check(
        new.count() >= 1 and first.locator(".ctx-new-badge").count() == 0,
        "appel 2 : le résultat d'outil réinjecté marqué « Nouveau » ; aucun badge à l'appel 1",
    )
    tool = first.locator(".ctx-produced.is-tool-call")
    r.check(
        tool.count() == 1
        and tool.locator(".json-key", has_text='"name"').count() >= 1
        and tool.locator(".json-string", has_text="get_datetime").count() >= 1,
        "appel 1 : l'appel d'outil produit, en arbre JSON (« name », « get_datetime »)",
    )
    answer = second.locator(".ctx-produced.is-answer")
    r.check(
        answer.count() == 1 and "D'après le résultat" in answer.inner_text(),
        "appel 2 : la réponse produite, « D'après le résultat… »",
    )
    produced = r.css(page.locator("#ctx .ctx-produced").first, "background-color")
    sections = set(
        page.locator("#ctx .ctx-section").evaluate_all(
            "ss => ss.map(s => getComputedStyle(s).backgroundColor)"
        )
    )
    r.check(
        produced == r.token_color("--color-produced-soft") and produced not in sections,
        "le produit sur --color-produced-soft, distinct du fond de toute section lue",
        f"{produced} · sections {sorted(sections)}",
    )
    r.check(
        page.locator("#ctx .ctx-produced-tag", has_text="Produit par le modèle").first.is_visible(),
        "« Produit par le modèle » visible",
    )
    _ctx_focus_shot(r, "40-contexte-appels-numerotes")

    # « Texte exact »: the body of each call's `context_rendered`, byte for byte, that is the
    # body the fake provider received.
    rendered = {e["call_id"]: e["payload"] for e in r.ev.since(seq, "context_rendered")}
    received = r.fake_calls()[-2:]
    _ctx_mode(r, "Texte exact")
    calls = _ctx_calls(r)
    exact = [c["exact"][0] if len(c["exact"]) == 1 else None for c in calls]
    r.check(
        len(exact) == 2
        and all(
            x == rendered.get(c["id"], {}).get("body") for x, c in zip(exact, calls, strict=True)
        ),
        "« Texte exact » : chaque pre.ctx-exact est le body du context_rendered de son appel",
    )
    try:
        loaded = [json.loads(x or "") for x in exact]
    except ValueError:
        loaded = None
    r.check(loaded == received, "« Texte exact » : json.loads = corps reçu par le faux fournisseur")
    styled = page.locator("#ctx pre.ctx-exact .ctx-seg, #ctx pre.ctx-exact .json-tree").count()
    r.check(styled == 0, "« Texte exact » : sans habillage (ni marge ni arbre)", str(styled))
    _ctx_focus_shot(r, "41-contexte-texte-exact")

    # « Corps JSON »: a tree, folded and unfolded by its summary.
    _ctx_mode(r, "Corps JSON")
    tree = page.locator("#ctx .json-tree").first
    key = tree.locator(".json-key", has_text='"messages"').first
    r.check(key.is_visible(), "« Corps JSON » : l'arbre montre la clé « messages »")
    summary = tree.locator("details.json-node > summary").first
    children = tree.locator("details.json-node > .json-children").first
    summary.click()
    folded = not children.is_visible()
    summary.click()
    unfolded = children.is_visible()
    r.check(folded and unfolded, "un clic sur le summary replie l'arbre, un second le déplie")
    # Lot 1 of 2026-10-04: the root open (its keys shown), every node under it folded; a
    # click unfolds one, and it stays so after the next rendering (another view, then back).
    inner = tree.locator("details.json-node details.json-node").first
    sub_folded = (
        inner.evaluate("n => !n.open")
        and tree.locator("details.json-node details.json-node[open]").count() == 0
    )
    r.check(sub_folded, "« Corps JSON » : racine ouverte, sous-nœuds repliés à l'ouverture")
    inner.locator(":scope > summary").click()
    opened = inner.evaluate("n => n.open")
    _ctx_mode(r, "Lecture groupée")
    _ctx_mode(r, "Corps JSON")
    tree = page.locator("#ctx .json-tree").first
    kept = tree.locator("details.json-node details.json-node").first.evaluate("n => n.open")
    r.check(opened and kept, "un sous-nœud déplié par un clic le reste au rendu suivant")
    _ctx_focus_shot(r, "42-contexte-corps-json")
    _ctx_mode(r, "Lecture groupée")


def s_native_tools(r: Run) -> None:
    r.launch("native_tools")
    b = r.bricks()
    r.check(
        all(b[x]["wanted"] for x in ("short_memory", "system_prompt", "tools")),
        "briques du scénario actives",
    )
    for prompt, tool, needle in [
        ("Quelle heure est-il ?", "get_datetime", "D'après le résultat"),
        ("Combien font 1234 multiplié par 5678 ?", "calculator", "7006652"),
        (
            "Lis le fichier recette_crepes.txt et donne-moi la liste des ingrédients.",
            "read_file",
            "farine",
        ),
    ]:
        seq = r.ev.mark()
        ended = r.send(prompt)
        tools = [e["payload"]["tool"] for e in r.ev.since(seq, "tool_started")]
        results = [e["payload"] for e in r.ev.since(seq, "tool_ended")]
        r.check(tool in tools, f"{tool} appelé", str(tools))
        r.check(
            bool(results) and results[-1]["status"] == "ok",
            f"{tool} réussi",
            str(results[-1] if results else None)[:200],
        )
        answer = r.last_answer().replace(" ", "").replace(" ", "")
        r.check(
            ended["payload"]["status"] == "completed" and needle.replace(" ", "") in answer,
            f"réponse finale après {tool}",
            r.last_answer()[:160],
        )
        if tool == "get_datetime":
            _read_and_produced(r, seq)
    orch = r.page.locator("#orch-scroll").inner_text()
    r.check("Demande un outil" in orch, "Orchestration montre la demande d'outil")
    r.shot("05-outils-natifs-orchestration")
    _slow_tool_turn(r)
    _diagram_module(r)


# ---------- lot 2 (2026-10-04): the shared diagram's module, on a test host ----------

# A host fixed over the page: two blocks (one explained, one not), a wire layer, a stepper; a
# second layer on a host of no width (a hidden pane). `window.__e2eDiagram` keeps them.
_DIAGRAM_SETUP_JS = """async () => {
  const d = await import('/static/diagram.js');
  document.getElementById('e2e-diagram')?.remove();
  const host = document.createElement('div');
  host.id = 'e2e-diagram';
  host.style.cssText = 'position: fixed; left: 40px; top: 120px; width: 420px; height: 160px;'
    + ' z-index: 50; background: var(--color-surface-raised);';
  const said = d.block('e2e-said', 'A');
  const mute = d.block('e2e-mute', 'B');
  host.append(said, mute);
  document.body.appendChild(host);
  const draws = { shown: 0, hidden: 0 };
  const layer = d.wireLayer(host, ({ box }) => {
    draws.shown += 1;
    const a = box(said), b = box(mute);
    return [
      d.wire(`M${a.r},${a.cy} H${b.l}`, 'diagram-wire'),
      d.marker(b.cx, b.b + 14, '✋', 'is-stop'),
    ];
  });
  const hidden = document.createElement('div');
  hidden.style.cssText = 'position: relative; width: 0; height: 40px; overflow: hidden;';
  host.appendChild(hidden);
  const hiddenLayer = d.wireLayer(hidden, () => {
    draws.hidden += 1;
    return [d.wire('M0,0 H10', 'diagram-wire')];
  });
  const shown = [];
  const lives = [];
  const steps = document.createElement('div');
  steps.style.cssText = 'position: absolute; left: 8px; bottom: 8px;';
  host.appendChild(steps);
  // Lot 4 (AD-28): `describe` names a step, `onLive` hears the live mode change.
  const stepper = d.createStepper(steps, {
    onShow: (frame) => shown.push(frame),
    describe: (frame, index) => `nom ${frame} (${index})`,
    onLive: (live) => lives.push(live),
  });
  const popover = d.explain(said, 'Le bloc A expliqué.');
  const none = d.explain(mute, '');
  d.light(host, said);
  layer.schedule();
  hiddenLayer.schedule();
  // Lot 4 (AD-28): a block hidden by `reveal()` (progressive discovery), a path's core.
  const late = d.block('e2e-late', 'C');
  host.appendChild(late);
  d.reveal(late, false);
  const core = d.svgEl('svg');
  core.appendChild(d.wire('M0,0 H10', 'diagram-path-core'));
  host.appendChild(core);
  window.__e2eDiagram = { d, host, said, mute, layer, hidden, draws, stepper, shown, lives,
    popover, none, late, core };
}"""

# The stepper's state: index, live mode, the position's text, its bounds (lot 4: in
# `aria-disabled`, never `disabled`), the frames shown, the status node, the live dot.
_DIAGRAM_STEPPER_JS = """() => {
  const { stepper, shown, lives } = window.__e2eDiagram;
  const bar = stepper.element;
  const pos = bar.querySelector('.diagram-step-position');
  const prev = bar.querySelector('.diagram-step-prev');
  const next = bar.querySelector('.diagram-step-next');
  const live = bar.querySelector('.diagram-step-live');
  const status = bar.querySelector('.diagram-step-status');
  const dot = live.querySelector('.diagram-step-live-dot');
  return {
    index: stepper.index, live: stepper.live, shown: [...shown], lives: [...lives],
    position: pos.hidden ? null : pos.textContent,
    positionLive: pos.getAttribute('aria-live'),
    prev: prev.getAttribute('aria-disabled') === 'true',
    next: next.getAttribute('aria-disabled') === 'true',
    nativeDisabled: prev.disabled || next.disabled,
    pressed: live.getAttribute('aria-pressed'),
    dot: dot && !dot.hidden ? dot.textContent : null,
    dotHidden: dot?.getAttribute('aria-hidden'),
    liveBackground: getComputedStyle(live).backgroundColor,
    status: status?.textContent ?? null,
    statusRole: status?.getAttribute('role'),
    statusPolite: status?.getAttribute('aria-live'),
    statusWidth: status ? status.getBoundingClientRect().width : null,
  };
}"""


def _diagram_module(r: Run) -> None:
    """Lot 2 (2026-10-04): `static/diagram.js` in the page, on a test host: the halo, the wires
    (none on a host of no width, drawn once it is resized), the stepper's matrix (empty, live,
    back, forward, bounds, resume, clear) and a block's explanation (anchored under it, closed
    by Escape or a click elsewhere; none without a text). The test host is removed after,
    whatever happened: it lies fixed over the shared page."""
    r.page.evaluate(_DIAGRAM_SETUP_JS)
    try:
        _diagram_module_checks(r)
    finally:
        r.page.evaluate(
            "() => { document.getElementById('e2e-diagram')?.remove();"
            " delete window.__e2eDiagram; }"
        )


def _diagram_module_checks(r: Run) -> None:
    page = r.page
    ui = _ui_catalogue("fr")
    state = page.evaluate(_DIAGRAM_STEPPER_JS)
    r.check(
        state["prev"]
        and state["next"]
        and not state["nativeDisabled"]
        and state["position"] is None
        and state["live"],
        "lot 2 : pas à pas vide : ◀ ▶ indisponibles (lot 4 : aria-disabled, jamais disabled), "
        "position masquée, en direct",
        str(state),
    )
    page.wait_for_function("() => window.__e2eDiagram.draws.shown > 0", timeout=5000)
    drawn = page.evaluate(
        """() => { const { host, hidden, draws, said, mute } = window.__e2eDiagram;
        return { paths: host.querySelectorAll(':scope > .diagram-wires .diagram-wire').length,
          stop: host.querySelector(':scope > .diagram-wires .diagram-marker.is-stop')?.textContent,
          hidden: hidden.querySelector('.diagram-wires').childElementCount,
          hiddenDraws: draws.hidden,
          lit: said.classList.contains('is-active') && !mute.classList.contains('is-active'),
          halo: getComputedStyle(said).boxShadow, mute: getComputedStyle(mute).boxShadow }; }"""
    )
    r.check(
        drawn["paths"] == 1
        and drawn["stop"] == "✋"
        and drawn["hidden"] == 0
        and drawn["hiddenDraws"] == 0
        and drawn["lit"]
        and drawn["halo"] != "none"
        and drawn["mute"] == "none",
        "lot 2 : fils et marqueur tracés, halo sur le bloc allumé seul ; conteneur de largeur "
        "nulle : aucun fil, sans erreur",
        str(drawn),
    )
    # The hidden host shown (no `schedule()`): its ResizeObserver redraws it.
    page.evaluate("() => { window.__e2eDiagram.hidden.style.width = '40px'; }")
    try:
        page.wait_for_function(
            "() => { const { hidden, draws } = window.__e2eDiagram; return draws.hidden > 0"
            " && hidden.querySelector('.diagram-wires').childElementCount > 0; }",
            timeout=5000,
        )
        redrawn = True
    except PlaywrightTimeout:
        redrawn = False
    r.check(
        redrawn,
        "lot 2 : le conteneur redimensionné est redessiné sans appel à schedule()",
        str(page.evaluate("() => window.__e2eDiagram.draws")),
    )

    # Live: each push shows the last step.
    page.evaluate(
        "() => ['un', 'deux', 'trois'].forEach((f) => window.__e2eDiagram.stepper.push(f))"
    )
    state = page.evaluate(_DIAGRAM_STEPPER_JS)

    def position(n: int, total: int) -> str:
        return ui["common.diagram.position"].replace("{n}", str(n)).replace("{total}", str(total))

    r.check(
        state["index"] == 2
        and state["live"]
        and state["position"] == position(3, 3)
        and state["shown"][-1] == "trois"
        and not state["prev"]
        and state["next"]
        and state["pressed"] == "true",
        "lot 2 : en direct, chaque push affiche la dernière étape (« 3 / 3 »), ▶ désactivé",
        str(state),
    )
    r.check(
        state["status"] == ""
        and state["statusRole"] == "status"
        and state["statusPolite"] == "polite"
        and (state["statusWidth"] or 0) <= 1
        and state["positionLive"] is None
        and state["dot"] == "● "
        and state["dotHidden"] == "true"
        and state["liveBackground"] != "rgba(0, 0, 0, 0)",
        "lot 4 : en direct, le nœud status du pas à pas (poli, masqué) se tait, la position "
        "n'est plus une région vivante ; « Suivre le direct » pressé : fond plein et « ● » "
        "en aria-hidden",
        str(state),
    )
    # A bound's button keeps the focus and does nothing (forced: Playwright waits for an
    # `aria-disabled` button to be enabled).
    bound = page.locator("#e2e-diagram .diagram-step-next")
    bound.click(force=True)
    after = page.evaluate(_DIAGRAM_STEPPER_JS)
    focused = page.evaluate(
        "() => document.activeElement?.classList.contains('diagram-step-next') ?? false"
    )
    r.check(
        after["index"] == 2 and after["live"] and after["shown"] == state["shown"] and focused,
        "lot 4 : un clic sur ▶ à la borne est sans effet et le bouton garde le focus",
        f"{after} · focus {focused}",
    )
    bar = page.locator("#e2e-diagram .diagram-stepper")
    bar.locator(".diagram-step-prev").click()
    page.evaluate("() => window.__e2eDiagram.stepper.push('quatre')")
    state = page.evaluate(_DIAGRAM_STEPPER_JS)
    r.check(
        state["index"] == 1
        and not state["live"]
        and state["shown"][-1] == "deux"
        and state["position"] == position(2, 4)
        and state["pressed"] == "false"
        and not state["next"],
        "lot 2 : ◀ quitte le direct (étape n-1), un push suivant ne déplace pas la vue",
        str(state),
    )
    # Said when ◀ was pressed (3 steps then), not again at each push out of live mode.
    announce = (
        ui["common.diagram.announce"]
        .replace("{n}", "2")
        .replace("{total}", "3")
        .replace("{name}", "nom deux (1)")
    )
    r.check(
        state["status"] == announce
        and state["lives"] == [False]
        and state["dot"] is None
        and state["pressed"] == "false",
        "lot 4 : hors du direct, le nœud status dit « Étape 2 sur 3 : {nom} » (describe) au "
        "clic, onLive reçoit false, « ● » retiré",
        f"{state['status']!r} · attendu {announce!r} · {state['lives']}",
    )
    bar.locator(".diagram-step-prev").click()
    state = page.evaluate(_DIAGRAM_STEPPER_JS)
    r.check(
        state["index"] == 0 and state["prev"] and state["shown"][-1] == "un",
        "lot 2 : à l'étape 1, ◀ désactivé",
        str(state),
    )
    bar.locator(".diagram-step-next").click()
    state = page.evaluate(_DIAGRAM_STEPPER_JS)
    r.check(
        state["index"] == 1
        and not state["live"]
        and state["shown"][-1] == "deux"
        and state["position"] == position(2, 4),
        "lot 2 : ▶ hors du direct avance d'une étape et reste hors du direct",
        str(state),
    )
    bar.locator(".diagram-step-live").click()
    page.evaluate("() => window.__e2eDiagram.stepper.push('cinq')")
    state = page.evaluate(_DIAGRAM_STEPPER_JS)
    r.check(
        state["index"] == 4
        and state["live"]
        and state["shown"][-2:] == ["quatre", "cinq"]
        and state["next"]
        and state["pressed"] == "true",
        "lot 2 : « Suivre le direct » revient à la dernière étape et la suit",
        str(state),
    )
    r.check(
        state["lives"] == [False, True] and state["status"] == "",
        "lot 4 : « Suivre le direct » : onLive reçoit true, le nœud status se tait",
        str(state),
    )

    # Lot 4: load() puts a whole series back, live, a single onShow on its last frame;
    # refresh() draws the current step again without touching the live mode.
    page.evaluate(
        "() => { const { stepper, shown } = window.__e2eDiagram; stepper.show(0);"
        " shown.length = 0; stepper.load(['a', 'b', 'c']); }"
    )
    loaded = page.evaluate(_DIAGRAM_STEPPER_JS)
    page.evaluate(
        "() => { const { stepper, shown } = window.__e2eDiagram; stepper.show(1);"
        " shown.length = 0; stepper.refresh(); }"
    )
    refreshed = page.evaluate(_DIAGRAM_STEPPER_JS)
    r.check(
        loaded["shown"] == ["c"]
        and loaded["index"] == 2
        and loaded["live"]
        and loaded["position"] == position(3, 3)
        and refreshed["shown"] == ["b"]
        and not refreshed["live"]
        and refreshed["index"] == 1,
        "lot 4 : load() restitue en un bloc, en direct, un seul onShow sur la dernière trame ; "
        "refresh() redessine l'étape courante sans toucher au direct",
        f"{loaded} · {refreshed}",
    )
    page.evaluate("() => window.__e2eDiagram.stepper.clear()")
    state = page.evaluate(_DIAGRAM_STEPPER_JS)
    r.check(
        state["index"] == -1
        and state["live"]
        and state["position"] is None
        and state["prev"]
        and state["next"]
        and state["shown"][-1] is None,
        "lot 2 : clear() : aucune étape, en direct, onShow reçoit null",
        str(state),
    )

    # A block's explanation: anchored under it, closed by Escape, then by a click elsewhere.
    def opened() -> bool:
        return page.evaluate("() => window.__e2eDiagram.popover.matches(':popover-open')")

    said = page.locator("#e2e-diagram .e2e-said")
    said.click()
    ok, _ = r.poll(opened, 3)
    where = page.evaluate(
        """() => { const { said, popover } = window.__e2eDiagram;
        const b = said.getBoundingClientRect(), p = popover.getBoundingClientRect();
        return { below: p.top >= b.bottom - 1, near: p.top - b.bottom < 40,
          text: popover.textContent }; }"""
    )
    r.check(
        ok and where["below"] and where["near"] and where["text"] == "Le bloc A expliqué.",
        "lot 2 : clic sur un bloc : son explication dans un popover ancré sous lui",
        str(where),
    )
    page.keyboard.press("Escape")
    closed_by_escape, _ = r.poll(lambda: not opened(), 3)
    said.click()
    reopened, _ = r.poll(opened, 3)
    box = page.locator("#e2e-diagram").bounding_box() or {}
    page.mouse.click(box.get("x", 0) + box.get("width", 0) - 10, box.get("y", 0) + 10)
    closed_by_click, _ = r.poll(lambda: not opened(), 3)
    page.locator("#e2e-diagram .e2e-mute").click()
    time.sleep(0.2)
    mute = page.evaluate(
        "() => ({ none: window.__e2eDiagram.none,"
        " open: document.querySelectorAll(':popover-open').length,"
        " popovers: document.querySelectorAll('#e2e-diagram .diagram-explain').length })"
    )
    r.check(
        closed_by_escape
        and reopened
        and closed_by_click
        and mute["none"] is None
        and mute["open"] == 0
        and mute["popovers"] == 1,
        "lot 2 : Échap ou un clic ailleurs ferme l'explication ; un bloc sans texte n'en a pas",
        f"Échap {closed_by_escape} · rouvert {reopened} · clic ailleurs {closed_by_click} · {mute}",
    )
    _diagram_module_lot4(r)


def _diagram_module_lot4(r: Run) -> None:
    """Lot 4 (AD-28): the explanation kept open by a click in it, closed when the focus leaves
    for anything else; the ink ring under the halo; the path's core at 3 px; `reveal()`: a
    hidden element keeps its place out of the accessibility tree, then fades in."""
    page = r.page

    def opened() -> bool:
        return page.evaluate("() => window.__e2eDiagram.popover.matches(':popover-open')")

    said = page.locator("#e2e-diagram .e2e-said")
    said.click()
    shown, _ = r.poll(opened, 3)
    page.locator("#e2e-diagram .diagram-explain").click()
    time.sleep(0.2)
    kept = opened()
    focusable = page.evaluate("() => window.__e2eDiagram.popover.tabIndex === -1")
    page.locator("#e2e-diagram .e2e-mute").focus()
    closed, _ = r.poll(lambda: not opened(), 3)
    r.check(
        shown and kept and focusable and closed,
        "lot 4 : la bulle d'explication est focalisable, un clic dedans la garde ouverte, le "
        "focus parti ailleurs la ferme",
        f"ouverte {shown} · gardée {kept} · tabindex -1 {focusable} · fermée {closed}",
    )
    looks = page.evaluate(
        """() => { const { said, core } = window.__e2eDiagram;
        return { halo: getComputedStyle(said).boxShadow,
          core: getComputedStyle(core.querySelector('.diagram-path-core')).strokeWidth }; }"""
    )
    r.check(
        looks["halo"].count("rgb") >= 2 and looks["core"] == "3px",
        "lot 4 : le bloc allumé porte l'anneau d'encre sous le halo ; le cœur du fil parcouru "
        "fait 3 px (--spacing-stroke-path)",
        str(looks),
    )
    hidden = page.evaluate(
        """() => { const { late } = window.__e2eDiagram; const box = late.getBoundingClientRect();
        return { cls: late.classList.contains('diagram-unrevealed'),
          visibility: getComputedStyle(late).visibility, width: box.width }; }"""
    )
    page.evaluate("() => window.__e2eDiagram.d.reveal(window.__e2eDiagram.late, true)")
    revealed = page.evaluate(
        """() => { const { late } = window.__e2eDiagram;
        return { cls: late.classList.contains('diagram-unrevealed'),
          visibility: getComputedStyle(late).visibility,
          fading: late.classList.contains('diagram-revealing')
            || getComputedStyle(late).animationName !== 'none' }; }"""
    )
    page.evaluate("() => window.__e2eDiagram.d.reveal([window.__e2eDiagram.late], false)")
    again = page.evaluate("() => getComputedStyle(window.__e2eDiagram.late).visibility")
    r.check(
        hidden["cls"]
        and hidden["visibility"] == "hidden"
        and hidden["width"] > 0
        and not revealed["cls"]
        and revealed["visibility"] == "visible"
        and revealed["fading"]
        and again == "hidden",
        "lot 4 : reveal() : un élément pas encore apparu garde sa place, invisible (hors de "
        "l'arbre d'accessibilité), puis apparaît en fondu ; masqué de nouveau en revenant",
        f"{hidden} · {revealed} · {again}",
    )


# ---------- restes différés, story 6: the schema at work, the rail and the event log ----------

SLOW_TOOL_PATH = "confidentiel/outil-lent-e2e"  # as `launch_app.SLOW_TOOL_PATH`

# Every state of the schema while a turn runs: the robot's accessible name (its pose), the
# components lit (`is-active`) and the paths drawn while `read_file` is lit; a mutation
# observer, so no frame is missed and no delay is needed.
_SCHEMA_RECORDER_JS = """() => {
  const rec = { poses: [], active: [], paths: 0 };
  const note = () => {
    const robot = document.querySelector('#schema .robot[data-component="core.model"]');
    const label = robot?.getAttribute('aria-label') ?? '';
    if (rec.poses.at(-1) !== label) rec.poses.push(label);
    for (const node of document.querySelectorAll('#schema .is-active:not(.robot)')) {
      const id = node.dataset.component;
      if (id && !rec.active.includes(id)) rec.active.push(id);
      if (id === 'tools.read_file') {
        const paths = document.querySelectorAll('#schema .diagram-wires .diagram-path').length;
        rec.paths = Math.max(rec.paths, paths);
      }
    }
  };
  note();
  const observer = new MutationObserver(note);
  observer.observe(document.getElementById('schema'), {
    subtree: true, childList: true, attributes: true, attributeFilter: ['class', 'aria-label'],
  });
  window.__e2eSchema = { rec, observer };
}"""

_GROUP_ROWS_JS = """g => [...g.querySelectorAll('.turn-step')].map((s) => ({
  name: s.querySelector('.turn-step-name')?.textContent ?? '',
  expanded: s.querySelector('.turn-step-line')?.getAttribute('aria-expanded') ?? '',
  body: Boolean(s.querySelector(':scope > .turn-step-body')),
  sticky: s.classList.contains('tone-error'),
  links: s.dataset.links ?? '',
}))"""


def _rows(group) -> list[dict[str, Any]]:  # noqa: ANN001
    return group.evaluate(_GROUP_ROWS_JS) if group.count() == 1 else []


def _row_names(rows: list[dict[str, Any]]) -> str:
    return " | ".join(f"{x['name']}{'▾' if x['expanded'] == 'true' else '▸'}" for x in rows)


def _slow_tool_turn(r: Run) -> None:
    """E020, E031, E032 (restes différés, story 6), on a fourth turn whose `read_file` lasts
    1.5 s (`launch_app.py`) and whose calls stream slowly (« [lent] »): the robot's poses, the
    tool's halo and path; the previous turn, opened by hand, folded by the new one in live
    mode; the current line unfolded in live; a click freezes the view, the line clicked stays
    unfolded and the lines that come after it do not; « Suivre le direct »; then the event
    log."""
    page = r.page
    ui = _ui_catalogue("fr")
    poses = {k: ui[f"main.schema.poses.{k}"] for k in ("idle", "thinking", "tool")}
    catalog_name, runs_tool = ui["main.orch.rows.catalog"], ui["main.orch.rows.runs_tool"]
    if page.locator("#follow-live").is_visible():
        page.click("#follow-live")
    r.wait_idle()
    previous = _turn_group(r, r.ev.since(0, "turn_ended")[-1]["turn_id"])
    head = previous.locator(":scope > .turn-group-head")
    head.click()  # folded, then opened again by hand: kept open by `turnOpen`
    head.click()
    opened = head.get_attribute("aria-expanded") == "true"
    page.evaluate(_SCHEMA_RECORDER_JS)
    seq = r.ev.mark()
    page.fill("#composer-input", f"Lis le fichier {SLOW_TOOL_PATH} [lent]")
    page.press("#composer-input", "Enter")
    r.wait_turn_started(seq, "l'envoi")
    turn_id = r.ev.since(seq, "turn_started")[0]["turn_id"]
    group = _turn_group(r, turn_id)
    expect(group).to_have_count(1, timeout=10_000)
    r.check(
        opened and head.get_attribute("aria-expanded") == "false",
        "E031 : en direct, le nouveau tour replie le précédent, même ouvert à la main",
        f"ouvert avant : {opened} · après : {head.get_attribute('aria-expanded')}",
    )

    # Live: the first call streams; its line, the current one, is the only one unfolded.
    r.poll(lambda: len(_rows(group)) >= 2, 10)
    rows = _rows(group)
    r.check(
        len(rows) >= 2
        and rows[-1]["expanded"] == "true"
        and all(x["expanded"] == "false" for x in rows[:-1] if not x["sticky"]),
        "E031 : en direct, seule la ligne courante (la dernière) est dépliée",
        _row_names(rows),
    )

    # The tool runs (1.5 s): the robot « utilise un outil » before any click on the rail (a
    # click selects, which rebuilds the schema whatever its key says).
    tool_row = group.locator(".turn-step").filter(
        has=page.locator(".turn-step-name", has_text=runs_tool)
    )
    expect(tool_row).to_have_count(1, timeout=15_000)

    def recorded() -> dict[str, Any]:
        return page.evaluate("() => window.__e2eSchema.rec")

    r.poll(lambda: any(poses["tool"] in p for p in recorded()["poses"]), 1)
    before_click = len(recorded()["poses"])

    # A click on the catalog line freezes the view: it stays unfolded, so does the line
    # current at the click; the lines that come after are not unfolded.
    catalog = group.locator(".turn-step").filter(
        has=page.locator(".turn-step-name", has_text=catalog_name)
    )
    catalog.locator(".turn-step-line").click()
    clicked = _rows(group)
    frozen = page.locator("#follow-live").is_visible()
    ended = r.ev.wait("turn_ended", seq)
    _turn_rendered_ended(r, turn_id)
    rows = _rows(group)
    # The lines that came after the click; the one current at the click stays unfolded.
    later = [x for x in rows[len(clicked) :] if not x["sticky"]]
    current = rows[len(clicked) - 1] if clicked and len(rows) >= len(clicked) else {}
    r.check(
        frozen
        and page.locator("#follow-live").is_visible()
        and rows[0]["name"] == catalog_name
        and rows[0]["expanded"] == "true"
        and rows[0]["body"]
        and current.get("expanded") == "true"
        and bool(later)
        and all(x["expanded"] == "false" for x in later),
        "E031 : un clic fige la vue ; la ligne cliquée reste dépliée jusqu'à la fin du tour, "
        "les lignes venues après restent repliées",
        f"au clic : {_row_names(clicked)} · à la fin : {_row_names(rows)}",
    )
    scroll = page.locator("#orch-scroll")
    page.click("#follow-live")
    rows = _rows(group)
    at_bottom = scroll.evaluate("s => s.scrollHeight - s.scrollTop - s.clientHeight < 2")
    r.check(
        page.locator("#follow-live").is_hidden()
        and rows[-1]["expanded"] == "true"
        and all(x["expanded"] == "false" for x in rows[:-1] if not x["sticky"])
        and at_bottom,
        "E031 : « Suivre le direct » : vue en direct, seule la dernière ligne dépliée, "
        "Orchestration défilée en bas",
        f"{_row_names(rows)} · en bas : {at_bottom}",
    )

    # The schema while it ran (E020, E032).
    rec = page.evaluate(
        "() => { window.__e2eSchema.observer.disconnect(); return window.__e2eSchema.rec; }"
    )
    shown = rec["poses"][:before_click]
    thinking = next((i for i, p in enumerate(shown) if poses["thinking"] in p), -1)
    tool = next((i for i, p in enumerate(shown) if poses["tool"] in p), -1)
    r.check(
        0 <= thinking < tool and poses["idle"] in rec["poses"][-1],
        "E020 : le robot « réfléchit » pendant l'appel, « utilise un outil » pendant l'outil "
        "(sans reconstruction du schéma), puis revient « au repos »",
        " → ".join(rec["poses"]),
    )
    r.check(
        "tools.read_file" in rec["active"] and rec["paths"] >= 1,
        "E032 : pendant l'outil, halo sur le nœud « Lecture de fichier » et chemin tracé vers lui",
        f"allumés {rec['active']} · chemins {rec['paths']}",
    )
    links = tool_row.get_attribute("data-links") or ""
    r.check(
        "tools.read_file" in links.split(),
        "E032 : l'étape de l'outil garde le composant de son enveloppe (tools.read_file)",
        links,
    )
    r.check(ended["payload"]["status"] == "completed", "tour à l'outil lent terminé")
    _event_log(r, seq)


_DELTAS = re.compile(r"^Morceaux de réponse × ([\d   ]+)$")
_NOTHING_TO_SUMMARIZE = {"model_first_token"}  # an empty payload: its label says it all
_LOG_ROWS_JS = """() => [...document.querySelectorAll('#event-log-list .event-log-item')].map(
  (li) => ({
    name: li.querySelector('.event-log-name').textContent,
    kind: li.querySelector('.event-log-kind').textContent,
    summary: li.querySelector('.event-log-summary').textContent,
  }))"""


def _digits(text: str) -> int:
    found = re.sub(r"\D", "", text)
    return int(found) if found else -1


def _event_log(r: Run, seq: int) -> None:
    """E031 (restes différés, story 6): the event log under Orchestration. Its title counts
    the events the page received; consecutive `model_delta` of one call share a row
    (« Morceaux de réponse × N », N their number); each row says its kind by the label of
    `main.log.kinds` and summarizes it; every kind of the catalog has a label in the three
    languages and a summary (a case of `eventSummary`, or the payload's `message_text`)."""
    page = r.page
    ui = _ui_catalogue("fr")
    page.click("#event-log-head")
    expect(page.locator("#event-log-list")).to_be_visible(timeout=5000)
    try:
        resets = r.ev.since(0, "harness_reset")
        start = resets[-1]["seq"] if resets else 0  # the log restarts after a reset
        title = page.locator("#event-log-title")
        # Recounted at each poll: events may still land after `turn_ended`.
        ok, _ = r.poll(lambda: _digits(title.inner_text()) == len(r.ev.since(start)), 10)
        r.check(
            ok,
            "E031 : le titre du journal compte les événements reçus",
            f"{title.inner_text()} · attendu {len(r.ev.since(start))}",
        )
        rows = page.evaluate(_LOG_ROWS_JS)
        merged = [(x, _DELTAS.match(x["name"])) for x in rows]
        total = sum(_digits(m.group(1)) if m else 1 for _, m in merged)
        # A model load's refreshing `scenario_changed` is counted, but has no row (lot E).
        total += sum(
            1 for e in r.ev.since(start, "scenario_changed") if e["payload"].get("refresh")
        )
        calls = [e for e in r.ev.since(seq, "model_call_ended")]
        last_call = calls[-1]["call_id"] if calls else None
        deltas = [e for e in r.ev.since(seq, "model_delta") if e["call_id"] == last_call]
        last_merged = next((m for _, m in reversed(merged) if m), None)
        r.check(
            total == _digits(title.inner_text())
            and last_merged is not None
            and _digits(last_merged.group(1)) == len(deltas) > 1,
            "E031 : les model_delta d'un appel forment une ligne « Morceaux de réponse × N » ; "
            "les lignes et leurs morceaux font le compte du titre",
            f"Σ lignes {total} · titre {title.inner_text()} · dernière fusion "
            f"{last_merged.group(0) if last_merged else None} · deltas du dernier appel "
            f"{len(deltas)}",
        )
        labels = {k.split(".")[-1]: v for k, v in ui.items() if k.startswith("main.log.kinds.")}
        wrong = [
            f"{x['kind']} : {x['name']}"
            for x, m in merged
            if not m and x["kind"] in labels and x["name"] != labels[x["kind"]]
        ]
        r.check(
            not wrong and any(x["kind"] in labels for x in rows),
            "E031 : chaque ligne du journal dit son type par son libellé (main.log.kinds)",
            "; ".join(wrong[:8]),
        )
        empty = sorted(
            {
                x["kind"]
                for x in rows
                if not x["summary"].strip()
                and x["kind"] != "model_delta"  # a chunk of text, maybe only blanks
                and x["kind"] not in _NOTHING_TO_SUMMARIZE
            }
        )
        r.check(not empty, "E031 : chaque ligne du journal résume son événement", str(empty))
        _log_catalog(r)
    finally:
        page.click("#event-log-head")


def _log_catalog(r: Run) -> None:
    """E031: every kind of the catalog (`trace/catalog.py`) has its label in `fr`, `en` and
    `de`, and a summary in the `eventSummary` the page loaded (the gaps noted by story 6 were
    closed on 2026-10-02)."""
    from wavestack.trace.catalog import PAYLOAD_MODELS

    unlabelled: set[str] = set()
    for lang in ("fr", "en", "de"):
        labels = {k.split(".")[-1] for k in _ui_catalogue(lang) if k.startswith("main.log.kinds.")}
        unlabelled |= {f"{k} ({lang})" for k in PAYLOAD_MODELS if k not in labels}
    source = httpx.get(f"{r.stack.app_url}/static/app.js", trust_env=False, timeout=10).text
    source = source.replace("\r\n", "\n")  # a Windows checkout serves it with CRLF
    body = source[source.index("function eventSummary(group) {") :]
    cases = set(re.findall(r'case "([a-z_]+)":', body[: body.index("\n}\n")]))
    unsummarized = {
        k
        for k, model in PAYLOAD_MODELS.items()
        if k not in cases and "message_text" not in model.model_fields
    } - _NOTHING_TO_SUMMARIZE
    r.check(
        not unlabelled,
        "E031 : chaque type du catalogue a son libellé dans main.log.kinds (fr, en, de)",
        str(sorted(unlabelled)),
    )
    r.check(
        not unsummarized,
        "E031 : chaque type du catalogue a un résumé (eventSummary ou message_text)",
        str(sorted(unsummarized)),
    )


def s_malformed(r: Run) -> None:
    r.launch("native_tools")
    seq = r.ev.mark()
    ended = r.send("Quelle heure est-il ? [mal-formé]")
    bad = r.ev.since(seq, "tool_call_malformed")
    r.check(
        len(bad) == 1 and bad[0]["payload"]["reaction"] == "retry",
        "appel mal formé détecté, nouvel essai",
        str([e["payload"] for e in bad])[:300],
    )
    r.check(
        ended["payload"]["status"] == "completed",
        "le tour aboutit après correction",
        ended["payload"]["status"],
    )
    r.shot("06-appel-mal-forme-corrige")
    seq = r.ev.mark()
    ended = r.send("Quelle heure est-il ? [mal-formé-toujours]")
    limit = r.ev.since(seq, "limit_reached")
    r.check(
        bool(limit) and limit[0]["payload"]["limit"] == "retries",
        "borne des nouveaux essais atteinte",
        str([e["payload"] for e in limit])[:300],
    )
    r.check(
        ended["payload"]["status"] == "limit",
        "tour terminé en « limit »",
        ended["payload"]["status"],
    )
    r.check(
        "appels refusés" in r.last_answer(),
        "la borne est expliquée dans la Vue humain",
        r.last_answer()[:200],
    )
    seq = r.ev.mark()
    r.send("Bonjour [outil-inconnu]")
    bad = r.ev.since(seq, "tool_call_malformed")
    r.check(
        bool(bad),
        "outil inconnu refusé par le harnais",
        bad[0]["payload"]["detail_text"] if bad else "",
    )
    seq = r.ev.mark()
    ended = r.send("Bonjour [tool_use_failed]")
    bad = r.ev.since(seq, "tool_call_malformed")
    r.check(
        bool(bad),
        "tool_use_failed (400 du fournisseur) suit le chemin mal formé",
        bad[0]["payload"]["detail_text"][:200] if bad else ended["payload"]["status"],
    )


def _on_vivid_both_themes(r: Run, locator, prop: str = "color") -> list[str]:
    """Story 31: `prop` of `locator` against --color-on-vivid, in light then in dark (the
    attribute set by hand, then removed): the text on red, explicit in both themes."""
    seen = []
    for theme in (None, "dark"):
        if theme:
            r.page.evaluate("() => document.documentElement.setAttribute('data-theme', 'dark')")
        seen.append((theme or "clair", r.css(locator, prop), r.token_color("--color-on-vivid")))
        r.page.evaluate("() => document.documentElement.removeAttribute('data-theme')")
    return [f"{theme} : {got} ≠ {want}" for theme, got, want in seen if got != want]


def _error_tile_on_vivid(r: Run) -> None:
    """Story 31: a model call that ended in error: its tile red, its letter in on-vivid."""
    step = r.page.locator(
        "#orch-scroll .turn-step.tone-error",
        has=r.page.locator(".turn-step-title", has_text="Appelle le modèle"),
    ).last
    expect(step).to_be_attached(timeout=5000)
    wrong = _on_vivid_both_themes(r, step.locator(".turn-step-tile"))
    r.check(
        not wrong, "appel au modèle en erreur : lettre de la tuile en --color-on-vivid", str(wrong)
    )


def s_provider_errors(r: Run) -> None:
    r.launch("bare_llm")
    for trigger, needle in [
        ("[erreur429]", "quota dépassé par minute"),
        ("[erreur500]", "indisponible (500)"),
        ("[flux-erreur]", "interrompu la réponse"),
        ("[erreur401]", "Clé refusée"),
    ]:
        seq = r.ev.mark()
        ended = r.send(f"Bonjour {trigger}")
        errors = [e["payload"]["message_text"] for e in r.ev.since(seq, "harness_error")]
        r.check(
            ended["payload"]["status"] == "error",
            f"{trigger} : tour en erreur",
            ended["payload"]["status"],
        )
        r.check(
            any(needle in m for m in errors),
            f"{trigger} : message français attendu",
            " | ".join(errors)[:300],
        )
        r.check(
            needle in r.last_answer(),
            f"{trigger} : l'erreur s'affiche dans la Vue humain",
            r.last_answer()[:200],
        )
        if trigger == "[erreur429]":
            r.shot("07-erreur-fournisseur-429")
        if trigger == "[erreur500]":
            _error_tile_on_vivid(r)
    _quota0_refusal(r)
    ended = r.send("Bonjour")
    r.check(ended["payload"]["status"] == "completed", "WaveStack reste utilisable ensuite")
    seq = r.ev.mark()
    ended = r.send("Explique [coupé]")
    r.check(
        ended["payload"]["status"] == "limit",
        "sortie coupée (finish_reason length)",
        ended["payload"]["status"],
    )


_QUOTA0_LOG_ROW_JS = """() => [...document.querySelectorAll('#event-log-list .event-log-item')]
  .filter((li) => li.querySelector('.event-log-kind').textContent === 'outbound_response')
  .map((li) => ({
    name: li.querySelector('.event-log-name').textContent,
    summary: li.querySelector('.event-log-summary').textContent,
  }))"""


def _quota0_refusal(r: Run) -> None:
    """Recette du 02/10 (R2): a 429 with a request quota of 0 (Mistral without a plan) leaves
    `outbound_response` between `outbound_request` and `model_call_ended`: its status, the
    quota headers in clear, the request id masked. The log labels and summarizes it,
    Orchestration does not show it, and D6's message is unchanged. The `[quota0]` model call
    is traced despite the loopback by the graft of `wavestack_e2e.py`; the conversation is
    cleared after, so no later request carries the mark."""
    try:
        seq = r.ev.mark()
        ended = r.send("Bonjour [quota0]")
        events = r.ev.since(seq)
        kinds = [e["kind"] for e in events]
        responses = [e["payload"] for e in events if e["kind"] == "outbound_response"]
        errors = [e["payload"]["message_text"] for e in r.ev.since(seq, "harness_error")]
        r.check(ended["payload"]["status"] == "error", "[quota0] : tour en erreur")
        ordered = (
            "outbound_request" in kinds
            and "outbound_response" in kinds
            and "model_call_ended" in kinds
            and kinds.index("outbound_request")
            < kinds.index("outbound_response")
            < kinds.index("model_call_ended")
        )
        r.check(
            ordered and len(responses) == 1,
            "[quota0] : outbound_response, une fois, entre outbound_request et model_call_ended",
            str([k for k in kinds if k.startswith(("outbound", "model_call"))]),
        )
        headers = {
            h["name"]: (h["value"], h["masked"]) for h in (responses or [{}])[0].get("headers", [])
        }
        r.check(
            bool(responses)
            and responses[0]["status"] == 429
            and headers.get("x-ratelimit-limit-req-minute") == ("0", False)
            and headers.get("x-ratelimit-remaining-req-minute") == ("0", False)
            and headers.get("x-request-id") == ("[masqué]", True),
            "[quota0] : statut 429, en-têtes de quota en clair, x-request-id masqué",
            str(responses)[:400],
        )
        r.check(
            "e2e-quota0-request" not in json.dumps(r.ev.since(seq), ensure_ascii=False),
            "[quota0] : la valeur de x-request-id n'entre pas dans le journal",
        )
        d6 = "Aucun quota actif sur ce compte : vérifiez le plan dans la console du fournisseur."
        r.check(
            any(d6 in m for m in errors) and d6 in r.last_answer(),
            "[quota0] : message D6 inchangé, dans le journal et la Vue humain",
            " | ".join(errors)[:300],
        )
        rail = r.page.locator("#orch-scroll").inner_text()
        r.check(
            "x-ratelimit" not in rail and "e2e-quota0" not in rail,
            "[quota0] : outbound_response n'est pas affiché dans Orchestration",
        )
        r.page.click("#event-log-head")
        try:
            expect(r.page.locator("#event-log-list")).to_be_visible(timeout=5000)
            rows = r.page.evaluate(_QUOTA0_LOG_ROW_JS)
            row = rows[-1] if rows else {}
            summary = row.get("summary", "")
            r.check(
                row.get("name") == "Réponse d'erreur reçue"
                and summary.startswith("429 · POST http://127.0.0.1:")
                and "/chat/completions" in summary
                and "x-ratelimit-limit-req-minute: 0" in summary
                and "x-ratelimit-remaining-req-minute: 0" in summary
                and "x-request-id" not in summary,
                "[quota0] : journal, « Réponse d'erreur reçue » · 429 · POST url · quota en clair",
                str(row),
            )
        finally:
            r.page.click("#event-log-head")
    finally:
        _clear_conversation(r)


# ---------- recette du 02/10: the Vue humain renders the answer's Markdown ----------

# Watches the chat while the answer streams: once a rendered `.bubble-text` is in the last
# answer, a mutation batch that leaves none is a loss (a flicker).
_MD_WATCH_JS = """() => {
  const chat = document.getElementById('chat');
  const watch = { seen: false, lost: 0, batches: 0 };
  const last = () => [...chat.querySelectorAll('.bubble-model')].at(-1);
  new MutationObserver(() => {
    watch.batches += 1;
    const has = Boolean(last()?.querySelector('.bubble-text.is-markdown'));
    if (has) watch.seen = true;
    else if (watch.seen) watch.lost += 1;
  }).observe(chat, { childList: true, subtree: true, characterData: true });
  window.__mdWatch = watch;
}"""

# Finition V1 (#18): `markdown.js` itself, on texts whose first opener has no closer. Each
# case gives the text and its `em` and `strong`; then the time of a 10 000-character
# paragraph of unclosed `*` (≈ 550 ms with the cubic scan before #18, ≈ 4 ms after).
_MD_INLINE_JS = """async (cases) => {
  const { renderMarkdown } = await import('/static/markdown.js');
  const render = (text) => {
    const box = document.createElement('div');
    box.appendChild(renderMarkdown(text));
    return box;
  };
  const texts = (box, s) => [...box.querySelectorAll(s)].map((e) => e.textContent);
  const got = cases.map((text) => {
    const box = render(text);
    return { text: box.textContent, em: texts(box, 'em'), strong: texts(box, 'strong') };
  });
  const big = 'a *b '.repeat(2000);
  const start = performance.now();
  render(big);
  return { got, ms: performance.now() - start };
}"""

# Finition V1 (#18): an unclosed opener of one kind never hides the emphases after it.
_MD_UNCLOSED = [
    ("**a puis *b* et _c_", {"text": "**a puis b et c", "em": ["b", "c"], "strong": []}),
    ("*a puis **b** et __c__", {"text": "*a puis b et c", "em": [], "strong": ["b", "c"]}),
    ("__a puis _b_ et **c**", {"text": "__a puis b et c", "em": ["b"], "strong": ["c"]}),
]

_MD_DOM_JS = """() => {
  const bubble = [...document.querySelectorAll('#chat .bubble-model')].at(-1)
    ?.querySelector('.bubble-text.is-markdown');
  if (!bubble) return null;
  const q = (s) => [...bubble.querySelectorAll(s)];
  const links = q('a');
  return {
    whiteSpace: getComputedStyle(bubble).whiteSpace,
    title: q('h3').map((h) => h.textContent),
    heading: q('h4').map((h) => h.textContent),
    strong: q('ul > li > strong').map((s) => s.textContent),
    underscored: q('p > strong').map((s) => s.textContent),
    year: q('p').filter((p) => p.textContent.includes('2026. Une année'))
      .map((p) => p.innerText),
    nested: q('ul ul > li > em').map((e) => e.textContent),
    inlineCode: q('li code').map((c) => c.textContent),
    ordered: q('ol').map((o) => [o.getAttribute('start'), o.children.length]),
    breaks: q('p br').length,
    links: links.map((a) => [a.getAttribute('href'), a.target, a.rel, a.textContent]),
    blocks: q('pre > code').map((c) => [c.className, c.textContent]),
    forbidden: q('img, b, script, hr, table, blockquote, del, s, iframe').length,
    text: bubble.innerText,
    elsewhere: document.querySelectorAll('.is-markdown').length
      - document.querySelectorAll('#chat .is-markdown').length,
  };
}"""


def _markdown_problems(dom: dict[str, Any] | None) -> list[str]:
    """What the rendering of `fake_openai.MARKDOWN_SAMPLE` misses, or [] when right."""
    if not dom:
        return ["aucune .bubble-text.is-markdown"]
    expected = {
        "title": ["Calendrier"],
        "heading": ["Jours fériés"],
        "strong": ["1er janvier :", "1er mai :"],
        "underscored": ["gras souligné"],  # `__x__`
        "year": ["Un paragraphe\n2026. Une année"],  # never an `ol start="2026"`
        "nested": ["sous-point"],
        "inlineCode": ["code_en_ligne"],
        "ordered": [["3", 2], [None, 2]],  # `3.` then `1)`, and no other list
        "blocks": [["language-text", "bloc fermé **brut**"], ["language-py", "x = 1"]],
    }
    problems = [f"{k} : {dom[k]}" for k, v in expected.items() if dom[k] != v]
    links = dom["links"]
    if not (
        len(links) == 1
        and links[0][0].startswith("https://example.org")
        and links[0][1] == "_blank"
        and "noopener" in links[0][2].split()
        and links[0][3] == "site"
    ):
        problems.append(f"liens : {links}")
    text = dom["text"]
    for raw in (
        "snake_case_name",
        "*pas d'italique*",
        "<img src=x onerror=alert(1)><b>gras HTML</b>",
        "[clic](javascript:alert(1))",
        "[relatif](/api/state)",
        "![image](https://example.org/a.png)",
        "---",
        "| a | b |",
        "> citation ~~barré~~",
    ):
        if raw not in text:
            problems.append(f"texte brut manquant : {raw}")
    if dom["forbidden"]:
        problems.append(f"{dom['forbidden']} élément(s) interdit(s) (img, b, hr, table…)")
    if dom["breaks"] < 1:
        problems.append("aucun <br> pour le saut de ligne simple")
    if dom["whiteSpace"] != "normal":
        problems.append(f"white-space {dom['whiteSpace']}")
    if dom["elsewhere"]:
        problems.append(f"{dom['elsewhere']} rendu(s) Markdown hors de la Vue humain")
    return problems


def s_markdown(r: Run) -> None:
    """Recette du 02/10: « [markdown] » answers `fake_openai.MARKDOWN_SAMPLE`. The Vue humain
    renders it (lists, bold, italic, headings, code, the safe link), keeps the injections as
    text (HTML, `javascript:`, a relative link, an image), never loses its `.bubble-text`
    while streaming, and shows the same after a reload; Contexte LLM, the event log and the
    screen reader's announcement keep the `**`."""
    page = r.page
    page.set_viewport_size({"width": 1600, "height": 1000})
    errors: list[str] = []
    listener = lambda e: errors.append(str(e))  # noqa: E731
    page.on("pageerror", listener)
    dialogs: list[str] = []
    on_dialog = lambda d: (dialogs.append(d.message), d.dismiss())  # noqa: E731
    page.on("dialog", on_dialog)
    try:
        r.launch("bare_llm")
        page.evaluate(_MD_WATCH_JS)
        ended = r.send("Montre le rendu [markdown]")
        r.check(ended["payload"]["status"] == "completed", "[markdown] : tour terminé")
        time.sleep(0.3)  # the last render after `turn_ended`
        watch = page.evaluate("() => window.__mdWatch")
        r.check(
            watch["seen"] and watch["lost"] == 0 and watch["batches"] > 3,
            "pendant le flux, la .bubble-text rendue ne disparaît jamais",
            str(watch),
        )
        dom = page.evaluate(_MD_DOM_JS)
        problems = _markdown_problems(dom)
        r.check(
            not problems,
            "Vue humain : listes, gras, italique, titre h4, code, bloc ouvert, lien sûr ; "
            "HTML, javascript:, lien relatif et image restent du texte",
            "; ".join(problems)[:500],
        )
        r.check(
            page.locator("#chat img").count() == 0 and not dialogs,
            "aucune image ni alerte injectée",
            str(dialogs),
        )
        inline = page.evaluate(_MD_INLINE_JS, [text for text, _ in _MD_UNCLOSED])
        wrong = [
            f"{text!r} : {got}"
            for (text, expected), got in zip(_MD_UNCLOSED, inline["got"], strict=True)
            if got != expected
        ]
        r.check(
            not wrong and inline["ms"] < 100,
            "Finition V1 (#18) : une ouverture non fermée ne masque pas les emphases suivantes, "
            "et 10 000 caractères de `*` non fermés se rendent en moins de 100 ms",
            f"{'; '.join(wrong)[:300]} · {inline['ms']:.1f} ms",
        )
        r.shot("40-markdown-vue-humain")
        ctx = page.locator("#ctx").inner_text()
        live = page.locator("#chat-live").text_content() or ""
        r.check(
            "**1er janvier :**" in ctx and "**1er janvier :**" in live,
            "Contexte LLM et l'annonce (#chat-live) gardent le Markdown brut",
            f"ctx {'**1er janvier :**' in ctx} · annonce {live[:80]!r}",
        )
        page.click("#event-log-head")
        try:
            expect(page.locator("#event-log-list")).to_be_visible(timeout=5000)
            summaries = page.evaluate(
                "() => [...document.querySelectorAll('#event-log-list .event-log-item')]"
                ".filter((li) => li.querySelector('.event-log-kind').textContent"
                " === 'model_delta').map((li) =>"
                " li.querySelector('.event-log-summary').textContent)"
            )
            r.check(
                any("**1er janvier :**" in s for s in summaries),
                "le journal garde le Markdown brut",
                str([s[:60] for s in summaries[-2:]]),
            )
        finally:
            page.click("#event-log-head")
        rail = page.locator("#orch-scroll")
        r.check(
            rail.locator("strong, .is-markdown").filter(has_text="1er janvier").count() == 0,
            "Orchestration ne rend pas le Markdown",
        )
        r.reload_app()
        time.sleep(0.3)
        again = page.evaluate(_MD_DOM_JS)
        r.check(
            again is not None
            and dom is not None
            and {k: again[k] for k in again if k != "text"}
            == {k: dom[k] for k in dom if k != "text"},
            "après rechargement, la Vue humain montre le même rendu",
            "; ".join(_markdown_problems(again))[:300],
        )
        r.check(not errors, "aucune erreur de page", "; ".join(errors)[:300])
    finally:
        page.remove_listener("pageerror", listener)
        page.remove_listener("dialog", on_dialog)
        _clear_conversation(r)


# ---------- recette du 02/10 (R1): the diagnostic says it waits ----------

_LISTS_JS = """() => ['checks', 'candidates', 'cloud-models'].map((id) => {
  const list = document.getElementById(id);
  return { id, loading: list.querySelectorAll(':scope > .loading-note').length,
    text: list.innerText.trim(), rows: list.children.length };
})"""


def s_diagnostic_wait(r: Run) -> None:
    """R1: `/api/diagnostic` held 1.5 s by the browser; meanwhile, « Diagnostic en cours… » in
    the three lists (Contrôles included: its stream opens after the answer); then each list
    replaces it with its rows."""
    page = r.page
    held: list[Any] = []
    hold = lambda route: held.append(route)  # noqa: E731 - answered below, 1.5 s later
    page.route("**/api/diagnostic", hold)
    try:
        page.goto(f"{r.stack.app_url}/diagnostic", wait_until="domcontentloaded")
        for _ in range(100):  # Playwright hands the route over while it waits, not in a sleep
            if held:
                break
            page.wait_for_timeout(100)
        r.check(bool(held), "la page demande /api/diagnostic (retenue par le test)")
        asked_at = time.monotonic()
        page.wait_for_timeout(300)  # the page's texts in its language (`await ready`)
        during = page.evaluate(_LISTS_JS)
        r.check(
            all(x["loading"] == 1 and x["text"] == "Diagnostic en cours…" for x in during),
            "pendant l'attente : « Diagnostic en cours… » dans Contrôles, Modèles détectés et "
            "Modèles cloud",
            str(during),
        )
        r.shot("41-diagnostic-en-cours")
        page.wait_for_timeout(max(0, int((1.5 - (time.monotonic() - asked_at)) * 1000)))
    finally:
        try:
            for route in held:
                with contextlib.suppress(Exception):  # already handled: nothing to release
                    route.continue_()
        finally:
            page.unroute("**/api/diagnostic", hold)

    def replaced() -> bool:
        lists = page.evaluate(_LISTS_JS)
        return all(x["loading"] == 0 for x in lists) and all(
            x["rows"] > 0 for x in lists if x["id"] != "candidates"
        )

    ok, took = r.poll(replaced, 15)
    r.check(
        ok,
        "après la réponse : le texte d'attente laisse place aux lignes des trois listes",
        f"{page.evaluate(_LISTS_JS)} · {took:.1f} s",
    )
    r.goto_app()


def s_network_tools(r: Run) -> None:
    r.launch("network_tools")
    _outbound_card(r)
    for prompt, tool in [
        ("Quels sont les jours fériés en France cette année ?", "public_holidays"),
        ("Résume l'article Wikipédia sur le Mont-Saint-Michel.", "wikipedia_summary"),
    ]:
        seq = r.ev.mark()
        ended = r.send(prompt)
        results = [e["payload"] for e in r.ev.since(seq, "tool_ended")]
        outbound = [e["payload"]["url"] for e in r.ev.since(seq, "outbound_request")]
        r.check(bool(outbound), f"{tool} : la requête sortante est tracée", str(outbound)[:200])
        res = results[-1] if results else {}
        r.check(
            res.get("status") == "error" and "Service injoignable" in (res.get("error_text") or ""),
            f"{tool} : échec réseau expliqué (réseau sortant coupé par le lanceur)",
            (res.get("error_text") or str(res))[:300],
        )
        r.check(
            ended["payload"]["status"] == "completed",
            f"{tool} : le tour se termine",
            ended["payload"]["status"],
        )
        if tool == "public_holidays":
            _holidays_outbound(r, seq)
    r.shot("08-outils-reseau-echec-explique")
    _reveal_from_schema(r)
    schema_fits(r, "Wikipédia")


# ---------- story 23: the outbound data, headers included, and the way to it ----------

_OUTBOUND_STEP_JS = """([title, within]) => {
  const steps = [...document.querySelectorAll(`#orch-scroll ${within} .turn-step`)]
    .filter((s) => s.querySelector('.turn-step-name')?.textContent === title
      || s.querySelector('.turn-step-title')?.textContent === title);
  const step = steps.at(-1);
  if (!step) return null;
  const payload = step.querySelector('.turn-step-body .outbound-payload');
  const pane = document.querySelector('[data-pane="orch"]');
  const scroll = document.getElementById('orch-scroll').getBoundingClientRect();
  const head = payload?.querySelector('summary').getBoundingClientRect();
  return {
    unfolded: Boolean(step.querySelector('.turn-step-body')),
    pane: Boolean(pane && pane.offsetParent !== null && !pane.hidden),
    open: payload ? payload.open : null,
    text: payload ? payload.innerText : '',
    visible: Boolean(head && head.height > 0 && head.top >= scroll.top - 1
      && head.bottom <= scroll.bottom + 1),
    masked: payload ? payload.querySelectorAll('.outbound-masked').length : 0,
  };
}"""


def _outbound_step(r: Run, title: str, within: str = "") -> dict[str, Any]:
    """The last step `title` (under `within`, e.g. `.harness-prep`) and its outbound block."""
    return r.page.evaluate(_OUTBOUND_STEP_JS, [title, within]) or {}


def _revealed(r: Run, found: dict[str, Any], expected: list[str], what: str) -> None:
    """Orchestration shown, the step unfolded, its block open, on screen and saying `expected`."""
    missing = [e for e in expected if e not in found.get("text", "")]
    ok = all(found.get(flag) for flag in ("pane", "unfolded", "open", "visible")) and not missing
    detail = {k: v for k, v in found.items() if k != "text"}
    r.check(ok, what, "" if ok else f"{detail} manque {missing}")


def _unfold_step(r: Run, title: str) -> None:
    """Unfolds the last step `title` of Orchestration (a failed one already is: sticky)."""
    step = r.page.locator("#orch-scroll .turn-step").filter(
        has=r.page.locator(".turn-step-title", has_text=title)
    )
    if not step.last.locator(".turn-step-body").count():
        step.last.locator(".turn-step-line").click()
    time.sleep(0.3)


def _outbound_card(r: Run) -> None:
    """The Outils card says what leaves the workstation, its options folded."""
    card = r.card("Outils")
    folded = card.locator("details.brick-options").get_attribute("open") is None
    text = card.locator(".brick-outbound").inner_text() if folded else ""
    names = ["Jours fériés", "Résumé Wikipédia", "Lecture de page web"]
    names += ["data.gouv.fr", "Microsoft Learn", "Données sortantes"]
    names.insert(0, "Peuvent sortir du poste")  # declared, enabled or not
    missing = [n for n in names if n not in text]
    r.check(
        folded and card.locator(".brick-outbound").is_visible() and not missing,
        "carte Outils, options repliées : ce qui sort du poste et où le lire",
        f"manque {missing} dans « {text[:200]} »" if missing else "",
    )


def _holidays_outbound(r: Run, seq: int) -> None:
    title = "Exécute l'outil hors du poste · Jours fériés"
    _unfold_step(r, title)
    block = _outbound_step(r, title)
    text = block.get("text", "")
    expected = [
        "Données sortantes",
        "GET https://calendrier.api.gouv.fr/jours-feries/",
        "En-têtes",
        "User-Agent: WaveStack/0.1 (demonstrateur pedagogique; ",
        "Aucun corps : seule l'adresse sort du poste.",
    ]
    missing = [e for e in expected if e not in text]
    ok = block.get("unfolded") and block.get("open") and not missing
    r.check(
        ok,
        f"« {title} » : données sortantes, adresse, User-Agent avec contact, aucun corps",
        "" if ok else f"{ {k: v for k, v in block.items() if k != 'text'} } manque {missing}",
    )
    traced = [e["payload"] for e in r.ev.since(seq, "outbound_request")]
    headers = traced[0].get("headers", []) if traced else []
    agent = next((h["value"] for h in headers if h["name"] == "User-Agent"), "")
    r.check(
        "demonstrateur pedagogique" in agent and not any(h["masked"] for h in headers),
        "outbound_request : en-têtes tracés, User-Agent en clair, aucun masqué",
        str(headers)[:300],
    )
    if r.page.locator("#follow-live").is_visible():
        r.page.click("#follow-live")  # back to the live view for the next turn
        time.sleep(0.3)


def _schema_node(r: Run, name: str):
    return r.page.locator(".arch-zone-network .arch-node").filter(has_text=name).first


def _reveal_from_schema(r: Run) -> None:
    """A click on the Wikipédia node leads to its outbound block, even folded, out of sight
    and with Orchestration hidden; a node never contacted leads nowhere."""
    title = "Exécute l'outil hors du poste · Résumé Wikipédia"
    page = r.page
    page.keyboard.press("Escape")  # no selection: the click selects the node
    block = page.locator("#orch-scroll .turn-step").filter(
        has=page.locator(".turn-step-title", has_text=title)
    )
    summary = block.last.locator(".outbound-payload > summary")
    if summary.count():
        summary.click()  # folded by the user: the click on the node opens it again
    page.evaluate("() => { document.getElementById('orch-scroll').scrollTop = 0; }")
    page.locator('[data-pane="orch"] .pane-hide').click()
    time.sleep(0.3)

    contact = {n["id"]: n.get("contact") for n in r.state()["architecture_changed"]["nodes"]}
    r.check(
        contact.get("tools.fetch_page") == "not_contacted",
        "« Lecture de page web » jamais contactée dans la session",
        str(contact.get("tools.fetch_page")),
    )
    node = _schema_node(r, "Lecture de page web")
    tip = node.get_attribute("title") or ""
    node.click()
    time.sleep(0.3)
    hidden = page.locator('[data-pane="orch"]').evaluate("p => p.offsetParent === null")
    r.check(
        "Non contacté" in tip and "Clic : ses données sortantes" not in tip and hidden,
        "nœud non contacté : sélection seule, infobulle « Non contacté »",
        tip.replace("\n", " · ")[:200],
    )

    node = _schema_node(r, "Wikipédia")
    tip = node.get_attribute("title") or ""
    r.check(
        "Clic : ses données sortantes dans Orchestration" in tip,
        "nœud Wikipédia contacté : l'infobulle dit où mène le clic",
        tip.replace("\n", " · ")[:200],
    )
    node.click()
    time.sleep(0.5)
    _revealed(
        r,
        _outbound_step(r, title),
        [
            "Données sortantes",
            "GET https://fr.wikipedia.org/api/rest_v1/page/summary/",
            "En-têtes",
            "User-Agent: WaveStack/0.1 (demonstrateur pedagogique; ",
            "Accept: */*",
        ],
        "clic sur le nœud Wikipédia : Orchestration montrée, étape dépliée, bloc ouvert et à "
        "l'écran, en-têtes compris",
    )
    r.check(
        not page.locator("#follow-live").is_hidden(),
        "la vue est figée (« Suivre le direct » proposé)",
    )
    r.shot("08b-donnees-sortantes-en-tetes")
    # A second click on the node, already selected: it stays selected and leads there again.
    page.evaluate("() => { document.getElementById('orch-scroll').scrollTop = 0; }")
    _schema_node(r, "Wikipédia").click()
    time.sleep(0.3)
    found = _outbound_step(r, title)
    selected = _schema_node(r, "Wikipédia").get_attribute("aria-pressed") == "true"
    r.check(
        selected and found.get("visible"),
        "second clic sur le nœud Wikipédia : toujours sélectionné, bloc de nouveau à l'écran",
        f"sélectionné : {selected}, à l'écran : {found.get('visible')}",
    )

    # The first turn folds back with the live view: its node unfolds it again.
    page.click("#follow-live")
    time.sleep(0.3)
    folded = page.locator("#orch-scroll .turn-group:not(.harness-prep) > .turn-group-head").first
    r.check(
        folded.get_attribute("aria-expanded") == "false",
        "en direct, le tour des jours fériés est replié",
    )
    _schema_node(r, "Jours fériés").click()
    time.sleep(0.5)
    _revealed(
        r,
        _outbound_step(r, "Exécute l'outil hors du poste · Jours fériés"),
        ["Données sortantes", "GET https://calendrier.api.gouv.fr/", "User-Agent: WaveStack/0.1"],
        "clic sur le nœud Jours fériés : tour replié déplié, étape dépliée, bloc ouvert et à "
        "l'écran",
    )
    page.click("#follow-live")
    page.keyboard.press("Escape")
    time.sleep(0.3)


# ---------- story 33: contrasts and one colour per discipline ----------

_DISCIPLINE_NAMES = ["Prompt engineering", "Context engineering", "Harness engineering"]
_FIGURES = re.compile(r"\d[\d\s\u202f]* / \d[\d\s\u202f]* tokens · [\d,]+ %")


def _fully_visible(r: Run, selector: str) -> str:
    """'' when `selector` is inside the viewport and its bar (the main screen's or, story 2 of
    2026-09-30, the shared one at the head), not cut by its own width."""
    return r.page.evaluate(
        "(q) => { const e = document.querySelector(q); if (!e) return 'absent';"
        " const b = e.getBoundingClientRect(); const bar = e.closest('.top-bar, .site-nav')"
        "?.getBoundingClientRect() ?? {left: 0, right: innerWidth, top: 0, bottom: innerHeight};"
        " if (b.width === 0) return 'vide';"
        " if (b.left < bar.left - 1 || b.right > bar.right + 1 || b.right > innerWidth)"
        " return `hors de la barre (${Math.round(b.left)}-${Math.round(b.right)})`;"
        " if (b.top < bar.top - 1 || b.bottom > bar.bottom + 1)"
        " return `déborde en hauteur (${Math.round(b.top)}-${Math.round(b.bottom)})`;"
        " if (e.scrollWidth > e.clientWidth + 1 || e.scrollHeight > e.clientHeight + 1)"
        " return `coupé (${e.scrollWidth}×${e.scrollHeight} > ${e.clientWidth}×${e.clientHeight})`;"
        " return ''; }",
        selector,
    )


def _last_gauge(r: Run) -> dict[str, Any]:
    """The payload the gauge shows: the latest of `context_preview`, `context_rendered` and
    `context_reconciled` in `/api/state` (as app.js keeps the most recent)."""
    state = r.state()
    envelopes = [
        state[k]
        for k in ("context_preview", "context_rendered", "context_reconciled")
        if state.get(k)
    ]
    return max(envelopes, key=lambda e: e["seq"])["payload"] if envelopes else {}


def s_disciplines(r: Run) -> None:
    """Story 33: the dark top bar and its legend, the bricks in two groups, tinted by
    discipline, their status lines, and the same colour in the four other panes."""
    page = r.page
    page.set_viewport_size({"width": 1600, "height": 1000})
    r.launch("network_tools")
    r.send("Résume l'article Wikipédia sur le Mont-Saint-Michel.")
    time.sleep(0.5)

    # The top bar: ink (story 31: its role token, ink-fill), the legend, the figures.
    ink = r.token_color("--color-ink-fill")
    r.check(
        r.css(page.locator(".top-bar"), "background-color") == ink,
        "barre de l'atelier : fond --color-ink-fill",
    )
    r.check(
        r.css(page.locator(".top-bar"), "color") == r.token_color("--color-on-ink"),
        "barre de l'atelier : texte en --color-on-ink (story 2 du 2026-09-30 : sans titre)",
    )
    legend = page.inner_text("#gauge-legend")
    r.check(
        all(name in legend for name in _DISCIPLINE_NAMES),
        "#gauge-legend : prompt, context et harness engineering",
        legend.replace("\n", " · "),
    )
    segs = page.eval_on_selector_all(
        ".gauge-seg",
        "ss => ss.map(s => [s.dataset.discipline || '', getComputedStyle(s).backgroundColor])",
    )
    wrong = [(d, bg) for d, bg in segs if not d or bg != r.token_color(f"--color-discipline-{d}")]
    r.check(
        bool(segs) and not wrong,
        "jauge : chaque segment porte sa discipline et le fond de son jeton",
        f"{len(segs)} segments ; écarts : {wrong}",
    )
    figures = page.inner_text("#gauge-figures")
    r.check(bool(_FIGURES.search(figures)), "jauge : total en tokens et en pourcentage", figures)
    for selector in ("#gauge-legend", "#gauge-figures"):
        cut = _fully_visible(r, selector)
        r.check(not cut, f"1600 × 1000 : {selector} entièrement visible", cut)
    r.shot_element("28-disciplines-barre-haute", ".top-bar")
    # Narrower windows (EXPERIENCE.md: 1280 px of reference): the bar never overflows, the
    # scenario's and the model's names give way; at 1280 px, with three hidden panes' chips
    # and a long message (set in the page: nothing in the parcours shows one on demand).
    for width, height in [(1366, 768), (1280, 720)]:
        page.set_viewport_size({"width": width, "height": height})
        time.sleep(0.5)
        if width == 1280:
            for pane in ("ctx", "orch", "schema"):
                page.locator(f'.pane[data-pane="{pane}"] .pane-hide').click()
            expect(page.locator("#pane-chips .pane-chip")).to_have_count(3, timeout=5000)
            page.evaluate(
                "() => { document.getElementById('top-status').textContent ="
                " 'Chargement du modèle faux-modele-raisonne-avec-un-nom-tres-long… 12,5 s'; }"
            )
        over = page.evaluate(
            "() => { const bar = document.querySelector('.top-bar').getBoundingClientRect();"
            " return [...document.querySelectorAll('.top-bar > *')]"
            ".filter(e => e.offsetParent && getComputedStyle(e).position !== 'absolute')"
            ".map(e => [e.id || e.className, e.getBoundingClientRect()])"
            ".filter(([, b]) => b.right > bar.right + 1 || b.bottom > bar.bottom + 1)"
            ".map(([n, b]) => `${n} (${Math.round(b.right)} > ${Math.round(bar.right)})`); }"
        )
        r.check(
            not over, f"{width} × {height} : la barre de l'atelier tient dans sa largeur", str(over)
        )
        cut = _fully_visible(r, "#gauge-legend")
        r.check(not cut, f"{width} × {height} : #gauge-legend entièrement visible", cut)
        cut = _fully_visible(r, "#gauge-figures")
        if width == 1280:  # lot K (A1): with three chips the figures give way, whole in their
            # tooltip (they cede before the chips; a chip « · lié » never cedes)
            whole = page.evaluate(
                "() => { const f = document.getElementById('gauge-figures');"
                " return f.title === f.textContent && f.getBoundingClientRect().width > 0; }"
            )
            r.check(
                not cut or whole,
                "1280 × 720, trois puces : chiffres de la jauge entiers, ou coupés avec leur "
                "texte entier en infobulle",
                cut,
            )
        else:
            r.check(not cut, f"{width} × {height} : #gauge-figures entièrement visible", cut)
        if width == 1280:
            status = page.evaluate(
                "() => { const s = document.getElementById('top-status').getBoundingClientRect();"
                " return s.left >= 0 && s.right <= innerWidth + 1; }"
            )
            r.check(
                status, "1280 × 720 : le message de la barre de l'atelier tient dans la fenêtre"
            )
            reset = page.locator("#reset-button").bounding_box() or {}
            r.check(
                reset.get("x", 1e9) + reset.get("width", 0) <= width + 1,
                "1280 × 720 : « Réinitialiser » reste dans la fenêtre, chips et message compris",
                str(reset),
            )
            while page.locator("#pane-chips .pane-chip").count():
                page.locator("#pane-chips .pane-chip").first.click()
            page.evaluate("() => { document.getElementById('top-status').textContent = ''; }")
    page.set_viewport_size({"width": 1600, "height": 1000})
    time.sleep(0.3)

    # The bricks panel: legend, two groups, cards tinted by discipline.
    bricks = page.locator("#bricks")
    panel_legend = bricks.locator(".brick-legend").inner_text()
    r.check(
        all(n in panel_legend for n in [*_DISCIPLINE_NAMES, "Sort du poste de travail"]),
        "panneau des briques : légende des quatre disciplines",
        panel_legend.replace("\n", " · "),
    )
    titles = bricks.locator(".brick-group-title").all_inner_texts()
    r.check(
        [t.lower() for t in titles] == ["ce que le modèle lit", "ce que le harnais fait"],
        "« Ce que le modèle lit » puis « Ce que le harnais fait »",
        str(titles),
    )
    first_group = page.evaluate(
        "() => { const names = []; let n = document.querySelector('#bricks .brick-group-title');"
        " for (n = n?.nextElementSibling; n && !n.matches('.brick-group-title');"
        " n = n.nextElementSibling) if (n.matches('article.brick-card'))"
        " names.push(n.querySelector('.brick-name').textContent); return names; }"
    )
    r.check(
        first_group
        == ["Raisonnement", "Prompt système", "Mémoire courte", "Mémoire globale", "RAG"],
        "premier groupe : Raisonnement, Prompt système, Mémoire courte, Mémoire globale, RAG",
        str(first_group),
    )
    r.check(
        r.css(r.card("Prompt système"), "border-left-color")
        == r.token_color("--color-discipline-prompt"),
        "carte Prompt système : trait gauche --color-discipline-prompt",
    )
    r.check(
        r.css(r.card("RAG"), "background-color")
        == r.token_color("--color-discipline-neutral-soft"),
        "carte RAG éteinte : fond --color-discipline-neutral-soft",
    )
    prompt_switch = r.card("Prompt système").locator(".brick-head input.brick-toggle")
    r.check(
        r.css(prompt_switch, "background-color") == r.token_color("--color-discipline-prompt"),
        "carte Prompt système : interrupteur coché de sa discipline",
    )

    # The status lines, from the values received.
    status = {
        name: r.card(name).locator("p.brick-status").inner_text()
        for name in ("Prompt système", "Mémoire globale", "Outils")
    }
    row = next(
        (b for b in _last_gauge(r).get("by_brick", []) if b["brick"] == "system_prompt"), None
    )
    expected = (
        f"{'≈ ' if row['estimated'] else ''}{row['tokens']} "
        f"token{'s' if row['tokens'] > 1 else ''} dans le contexte"
        if row
        else "(absent de by_brick)"
    )
    r.check(
        bool(row) and row["tokens"] > 0 and status["Prompt système"] == expected,
        "ligne d'état de Prompt système : les tokens de by_brick, « ≈ » en mode chat",
        f"{status['Prompt système']} / attendu {expected}",
    )
    r.check(
        re.search(r"\d+ entrées? · \d+ tokens?", status["Mémoire globale"]) is not None,
        "ligne d'état de Mémoire globale : « n entrées · n tokens »",
        status["Mémoire globale"],
    )
    # « contacté » counts the network tools nodes whose `contact` is set: the scenario alone
    # contacts Wikipédia only; after `network_tools`, the holidays' service is counted too.
    nodes = r.state()["architecture_changed"]["nodes"]
    contacted = [
        n["id"]
        for n in nodes
        if n["id"].startswith("tools.")
        and n["hosting"] == "network"
        and n.get("contact") not in (None, "not_contacted")
    ]
    tools_line = re.search(r"(\d+) déclarés? · (\d+) contactés?", status["Outils"])
    r.check(
        tools_line is not None
        and int(tools_line.group(2)) == len(contacted)
        and "tools.wikipedia_summary" in contacted,
        "ligne d'état d'Outils : « n déclarés · c contacté(s) », Wikipédia compris",
        f"{status['Outils']} ; nœuds contactés : {contacted}",
    )
    r.check(
        r.card("Outils").locator(".brick-network").inner_text().strip() == "RÉSEAU",
        "carte Outils : puce « 🌐 RÉSEAU »",
    )
    r.shot_element("29-disciplines-briques", '.pane[data-pane="bricks"]')

    # Prompt système off (by the API, so the click does not light-dismiss the explanation):
    # « Éteinte », the open explanation kept.
    help_button = r.card("Prompt système").locator(".brick-help")
    help_button.click()
    expect(page.locator("#explain-system_prompt")).to_be_visible(timeout=5000)
    seq = r.ev.mark()
    r.api("POST", "/api/intentions/brick", {"brick": "system_prompt", "wanted": False})
    r.ev.wait("bricks_changed", seq, timeout=10)
    time.sleep(0.5)
    r.check(
        r.card("Prompt système").locator("p.brick-status").inner_text() == "Éteinte",
        "Prompt système éteint : sa ligne d'état dit « Éteinte »",
    )
    r.check(
        page.locator("#explain-system_prompt").evaluate("e => e.matches(':popover-open')"),
        "l'explication ouverte reste ouverte",
    )
    page.keyboard.press("Escape")
    r.set_brick("Prompt système", True)

    # Vue humain: the user's bubble on ink; every pane's band on surface.
    bubble = page.locator("#chat .bubble-user").last
    r.check(
        r.css(bubble, "background-color") == ink
        and r.css(bubble, "color") == r.token_color("--color-on-ink"),
        "dernière bulle de l'utilisateur : fond --color-ink-fill, texte --color-on-ink",
    )
    bands = page.eval_on_selector_all(
        ".pane-header", "hs => hs.map(h => getComputedStyle(h).backgroundColor)"
    )
    r.check(
        len(bands) == 5 and set(bands) == {r.token_color("--color-surface")},
        "chaque en-tête des cinq volets : fond --color-surface",
        str(bands),
    )
    r.shot_element("30-disciplines-vue-humain", '.pane[data-pane="human"]')

    # Contexte LLM: every section its discipline; the system prompt's rule and swatch.
    ctx = page.locator("#ctx .ctx-section")
    disciplines = ctx.evaluate_all("ss => ss.map(s => s.dataset.discipline || '')")
    r.check(
        bool(disciplines) and all(disciplines),
        "Contexte LLM : chaque section porte sa discipline",
        str(disciplines),
    )
    prompt = (
        page.locator("#ctx .ctx-section")
        .filter(
            has=page.locator(".ctx-section-label", has_text=re.compile(r"^Prompt système · ≈? ?\d"))
        )
        .first
    )
    r.check(
        r.css(prompt, "border-left-color") == r.token_color("--color-discipline-prompt")
        and r.css(prompt.locator(".swatch").first, "background-color")
        == r.token_color("--color-segment-system-prompt"),
        "section du prompt système : filet de sa discipline, pastille de son type",
    )
    r.shot_element("31-disciplines-contexte", '.pane[data-pane="ctx"]')

    # Orchestration: the model's tiles on ink, the network step, the harness step.
    def tile(name: str):
        step = page.locator(
            "#orch-scroll .turn-step", has=page.locator(".turn-step-title", has_text=name)
        ).last
        return step.locator(".turn-step-tile")

    r.check(
        r.css(tile("Appelle le modèle"), "background-color") == ink,
        "Orchestration : la tuile de l'appel au modèle a le fond --color-ink-fill",
    )
    r.check(
        tile("Résumé Wikipédia").get_attribute("data-discipline") == "network",
        "Orchestration : l'exécution de wikipedia_summary est en discipline réseau",
    )
    r.check(
        tile("Décrit les outils").get_attribute("data-discipline") == "harness",
        "Orchestration : « Décrit les outils » est en harness engineering",
    )
    r.shot_element("32-disciplines-orchestration", '.pane[data-pane="orch"]')

    # The schema: the model's ink plate, the nodes by discipline.
    plate = page.locator(
        "#schema .arch-cloud-model, #schema .arch-server-model, #schema .arch-robots"
    )
    r.check(
        r.css(plate.first, "background-color") == ink,
        "schéma : la plaque du modèle a le fond --color-ink-fill",
    )

    def node(name: str):
        return page.locator("#schema .arch-node", has_text=name).first

    r.check(
        node("Résumé Wikipédia").get_attribute("data-discipline") == "network",
        "schéma : le nœud Wikipédia est en discipline réseau",
    )
    r.check(
        node("Calculatrice").get_attribute("data-discipline") == "harness",
        "schéma : le nœud Calculatrice est en harness engineering",
    )
    r.shot_element("33-disciplines-schema", '.pane[data-pane="schema"]')


# ---------- story 31: the dark theme ----------

THEME_KEY = "wavestack.theme"
_PANES = ("bricks", "human", "ctx", "orch", "schema")

# For every visible element that carries text: its first opaque background up the tree, the
# WCAG ratio, the threshold (4.5; 3 from 24 px, or from 18.66 px in bold). Skipped, as WCAG
# exempts them or as the ratio cannot be told: an ancestor at `opacity < 1` or disabled, a
# background image. A native `select` counts, for the option it shows.
_CONTRAST_SWEEP_JS = """(scopes) => {
  const parse = (c) => {
    const m = c.match(/rgba?\\(([^)]+)\\)/);
    if (!m) return null;
    const [r, g, b, a = 1] = m[1].split(/[ ,\\/]+/).filter(Boolean).map(Number);
    return [r, g, b, a];
  };
  const over = (top, under) => top.slice(0, 3).map((v, i) => v * top[3] + under[i] * (1 - top[3]));
  const lum = (rgb) => {
    const l = rgb.map((v) => {
      v /= 255;
      return v <= 0.04045 ? v / 12.92 : ((v + 0.055) / 1.055) ** 2.4;
    });
    return 0.2126 * l[0] + 0.7152 * l[1] + 0.0722 * l[2];
  };
  const ratio = (a, b) => {
    const [x, y] = [lum(a), lum(b)].sort((p, q) => q - p);
    return (x + 0.05) / (y + 0.05);
  };
  const exempt = (el) => {
    for (let n = el; n && n.nodeType === 1; n = n.parentElement) {
      if (parseFloat(getComputedStyle(n).opacity) < 1) return true;
      if (n.matches(':disabled, [aria-disabled="true"]')) return true;
    }
    return false;
  };
  const background = (el) => {
    const layers = [];
    for (let n = el; n && n.nodeType === 1; n = n.parentElement) {
      const s = getComputedStyle(n);
      if (s.backgroundImage !== 'none') return null;
      const c = parse(s.backgroundColor);
      if (c && c[3] > 0) { layers.push(c); if (c[3] >= 1) break; }
    }
    let rgb = [255, 255, 255];
    if (!layers.length || layers[layers.length - 1][3] < 1) {
      const scheme = getComputedStyle(document.documentElement).colorScheme;
      if (scheme.includes('dark')) rgb = [18, 18, 18];
    }
    for (const layer of layers.reverse()) rgb = over(layer, rgb);
    return rgb;
  };
  const failures = [];
  const seen = new Set();
  for (const scope of scopes) {
    for (const root of document.querySelectorAll(scope)) {
      for (const el of [root, ...root.querySelectorAll('*')]) {
        if (seen.has(el)) continue;
        seen.add(el);
        const text = el.matches('select')
          ? (el.selectedOptions[0]?.textContent || '')
          : [...el.childNodes].filter((n) => n.nodeType === 3).map((n) => n.textContent).join('');
        if (!text.trim()) continue;
        if (!el.checkVisibility({ visibilityProperty: true })) continue;
        const box = el.getBoundingClientRect();
        if (box.width <= 1 || box.height <= 1) continue;
        if (exempt(el)) continue;
        let bg = background(el);
        if (!bg) continue;
        const s = getComputedStyle(el);
        // SVG text is painted by `fill`, over the shape drawn beside it (a marker's disc).
        const svgText = el instanceof SVGTextContentElement;
        if (svgText) {
          const shape = [...el.parentNode.children].find((n) => n !== el
            && n.matches('circle, rect, ellipse, path, polygon')
            && (parse(getComputedStyle(n).fill) || [0, 0, 0, 0])[3] > 0);
          if (shape) bg = over(parse(getComputedStyle(shape).fill), bg);
        }
        const fg = parse(svgText ? s.fill : s.color);
        if (!fg || fg[3] === 0) continue;
        const size = parseFloat(s.fontSize);
        const bold = parseInt(s.fontWeight, 10) >= 700;
        const threshold = size >= 24 || (size >= 18.66 && bold) ? 3 : 4.5;
        const r = ratio(over(fg, bg), bg);
        if (r < threshold) {
          const name = `${el.tagName.toLowerCase()}.${[...el.classList].join('.')}`;
          const said = text.trim().slice(0, 30);
          failures.push(`${name} « ${said} » ${r.toFixed(2)} < ${threshold}`);
        }
      }
    }
  }
  return failures;
}"""


def _contrast_sweep(r: Run, scopes: list[str]) -> list[str]:
    """Story 31: every text of `scopes` that misses WCAG AA against its background. The pointer
    rests first: the linked view would dim, hence exempt, most of the page."""
    r.rest_pointer()
    return r.page.evaluate(_CONTRAST_SWEEP_JS, scopes)


def _design_rgb(key: str) -> str:
    """A colour of DESIGN.md's frontmatter (`surface-dark`…), as `getComputedStyle` writes it."""
    import yaml

    design = next((REPO / "_bmad-output" / "planning-artifacts" / "ux-designs").glob("*/DESIGN.md"))
    text = design.read_text(encoding="utf-8")
    colors = yaml.safe_load(text.split("---\n", 2)[1])["colors"]
    value = colors[key].lstrip("#")
    return "rgb({}, {}, {})".format(*(int(value[i : i + 2], 16) for i in (0, 2, 4)))


# Story 2 (2026-09-30): each control of the shared bar, the brand, the five links and
# « Affichage ▾ », whole, inside the bar, on one line.
_SITE_NAV_PROBLEMS_JS = """() => {
  const nav = document.querySelector('nav.site-nav');
  if (!nav) return ['barre commune absente'];
  const box = nav.getBoundingClientRect();
  const problems = [];
  if (nav.scrollWidth > nav.clientWidth + 1) {
    problems.push(`barre commune : ${nav.scrollWidth} px > ${nav.clientWidth}`);
  }
  if (box.left < 0 || box.right > innerWidth + 1) {
    const span = `${Math.round(box.left)}-${Math.round(box.right)}`;
    problems.push(`barre commune hors de la fenêtre (${span})`);
  }
  const items = [...nav.children].filter(e => e.checkVisibility());
  const links = items.filter(e => e.tagName === 'A').map(e => e.getAttribute('href'));
  const order = links.join(' ');
  if (order !== '/ / /llm /rag /mcp /diagnostic') problems.push(`liens ${order}`);
  if (!items.some(e => e.id === 'display-menu')) problems.push('« Affichage ▾ » absent');
  for (const e of [...items, document.getElementById('display-menu-toggle')]) {
    if (!e) continue;
    const b = e.getBoundingClientRect();
    const name = e.id || e.textContent.trim();
    const out = b.left < box.left - 1 || b.right > box.right + 1
      || b.top < box.top - 1 || b.bottom > box.bottom + 1;
    if (b.width === 0) problems.push(`${name} vide`);
    else if (out) problems.push(`${name} hors de la barre commune`);
    else if (e.scrollWidth > e.clientWidth + 1) {
      problems.push(`${name} coupé (${e.scrollWidth} > ${e.clientWidth})`);
    }
  }
  return problems;
}"""


# The two bars and the five panes, for the contrast sweeps.
_BARS_AND_PANES = [".site-nav", ".top-bar", *(f'.pane[data-pane="{p}"]' for p in _PANES)]


def _site_nav_problems(r: Run) -> list[str]:
    return r.page.evaluate(_SITE_NAV_PROBLEMS_JS)


def _bar_fits(r: Run) -> tuple[bool, str]:
    """Every control of the main screen's bar whole, inside the bar, on one line;
    « Réinitialiser » too. Story 2 (2026-09-30): the shared bar at the head likewise (its brand,
    its five links and « Affichage ▾ »), and the main screen's bar under the panes."""
    controls = r.page.evaluate(
        "() => [...document.querySelectorAll('.top-bar > *')]"
        ".filter(e => e.id && e.offsetParent && e.getBoundingClientRect().width > 0"
        " && getComputedStyle(e).position !== 'absolute')"
        ".map(e => '#' + e.id)"
    )
    cut = {c: why for c in controls if (why := _fully_visible(r, c))}
    nav = _site_nav_problems(r)
    under = _bar_under_panes(r)
    ok = "#reset-button" in controls and not cut and not nav and not under
    return ok, f"{controls} ; {cut} ; barre commune {nav} ; {under}"


def _bar_under_panes(r: Run) -> str:
    """'' when the main screen's bar lies under its panes, inside the window; else why."""
    return r.page.evaluate(
        "() => { const bar = document.querySelector('.top-bar'); if (!bar) return '';"
        " const b = bar.getBoundingClientRect();"
        " const panes = [...document.querySelectorAll('.pane')].filter(p => p.checkVisibility());"
        " if (!panes.length) return 'aucun volet visible';"
        " const low = Math.max(...panes.map(p => p.getBoundingClientRect().bottom));"
        " if (b.top < low - 1) return `barre basse (haut ${Math.round(b.top)}) sur les volets"
        " (bas ${Math.round(low)})`;"
        " if (b.bottom > innerHeight + 1) return `barre basse hors de la fenêtre"
        " (${Math.round(b.bottom)} > ${innerHeight})`; return ''; }"
    )


def _window_panel_outside(page: Page) -> str | None:
    """Open the « Fenêtre » panel, say how it leaves the window (if it does), close it."""
    page.locator("#window-toggle").click()
    expect(page.locator("#window-panel")).to_be_visible(timeout=5000)
    panel = page.evaluate(
        "() => { const p = document.getElementById('window-panel')"
        ".getBoundingClientRect(); return [p.left, p.right, p.bottom,"
        " innerWidth, innerHeight, p.top].map(Math.round); }"
    )
    page.keyboard.press("Escape")
    expect(page.locator("#window-panel")).to_be_hidden(timeout=5000)
    left, right, bottom, inner_w, inner_h, top = panel
    if left < 0 or right > inner_w or bottom > inner_h or top < 0:
        return f"panneau « Fenêtre » hors de la fenêtre ({panel})"
    return None


def _bar_panels_problems(r: Run) -> list[str]:
    """Story 2 (2026-09-30): the main screen's bar is under the panes; « Fenêtre » and
    « Volets ▾ » open upwards, each whole in the window, above the bar and under the shared
    bar at the head. Both closed after."""
    page = r.page
    problems = []
    for toggle, panel in (
        ("#window-toggle", "#window-panel"),
        ("#pane-menu-toggle", "#pane-menu-list"),
    ):
        if page.locator(toggle).is_disabled():
            problems.append(f"{toggle} désactivé")
            continue
        page.locator(toggle).click()
        expect(page.locator(panel)).to_be_visible(timeout=5000)
        where = page.evaluate(
            "(q) => { const p = document.querySelector(q).getBoundingClientRect();"
            " const bar = document.querySelector('.top-bar').getBoundingClientRect();"
            " const out = p.left < 0 || p.top < 0 || p.right > innerWidth + 1"
            " || p.bottom > innerHeight + 1;"
            " if (out) return `hors de la fenêtre (${[p.left, p.top, p.right, p.bottom]"
            ".map(Math.round)})`;"
            " if (p.bottom > bar.top + 1) return `sur la barre (bas ${Math.round(p.bottom)}"
            " > ${Math.round(bar.top)})`;"
            " const nav = document.querySelector('.site-nav').getBoundingClientRect();"
            " if (p.top < nav.bottom - 1) return `sous la barre commune (haut"
            " ${Math.round(p.top)} < ${Math.round(nav.bottom)})`; return ''; }",
            panel,
        )
        if where:
            problems.append(f"{panel} {where}")
        page.keyboard.press("Escape")
        expect(page.locator(panel)).to_be_hidden(timeout=5000)
    return problems


def _top_bar_problems(r: Run, chip) -> list[str]:
    """Lot K (A1): what is wrong in the top bar: a control out of the bar or cut (the chips
    aside), « Réinitialiser » missing, the gauge's legend under the « Fenêtre » button; with
    `chip`, the chip cut, or cut once 10 px wider (the fonts of Windows are wider)."""
    page = r.page
    problems = []
    controls = page.evaluate(
        "() => [...document.querySelectorAll('.top-bar > *')]"
        ".filter(e => e.id && e.offsetParent && e.getBoundingClientRect().width > 0"
        " && getComputedStyle(e).position !== 'absolute')"
        ".map(e => '#' + e.id)"
    )
    for control in controls:
        if control == "#pane-chips" and chip is None:
            continue
        if why := _fully_visible(r, control):
            problems.append(f"{control} {why}")
    if "#reset-button" not in controls:
        problems.append("« Réinitialiser » absent")
    covered = page.evaluate(
        "() => { const l = document.getElementById('gauge-legend').getBoundingClientRect();"
        " const w = document.getElementById('window-toggle').getBoundingClientRect();"
        " return Math.round(l.right - w.left); }"
    )
    if covered > 0:
        problems.append(f"légende recouverte de {covered} px par « Fenêtre ▾ »")
    if chip is not None:
        if "· lié" not in chip.inner_text():
            problems.append(f"puce « {chip.inner_text()} » sans « · lié »")
        for extra in (0, 10):
            missing = chip.evaluate(
                "(c, extra) => {"
                " c.style.paddingRight = extra ? `calc(var(--spacing-3) + ${extra}px)` : '';"
                " const m = c.scrollWidth - c.clientWidth;"
                " const bar = document.querySelector('.top-bar').getBoundingClientRect();"
                " const reset = document.getElementById('reset-button').getBoundingClientRect();"
                " const out = reset.right > bar.right + 1;"
                " c.style.paddingRight = ''; return out ? 999 : m; }",
                extra,
            )
            if missing > 1:
                problems.append(
                    f"puce « {chip.inner_text()} » "
                    + (f"coupée de {missing} px" if missing < 999 else ": la barre déborde")
                    + (f" une fois {extra} px plus large" if extra else "")
                )
    return problems


def _display_menu_picker(r: Run, words: str = "◐ Système") -> str:
    """Languages (2/5): '' when « Affichage ▾ » shows the theme's symbol, opens on its three
    controls, each whole in the window, the theme picker with its words, and the keyboard
    changes the theme through it (the face following); else what is wrong. Back to
    « Système » after, the menu closed."""
    page = r.page
    problems = []
    if (face := page.text_content(".display-menu-symbol")) != "◐":
        problems.append(f"face « {face} »")
    _open_display(page)
    cut = page.evaluate(
        "() => ['#theme-picker', '#language-picker', '#projection-toggle'].filter(q => {"
        " const e = document.querySelector(q), b = e.getBoundingClientRect();"
        " return !e.checkVisibility() || b.left < 0 || b.right > innerWidth"
        " || b.bottom > innerHeight || e.scrollWidth > e.clientWidth + 1; })"
    )
    if cut:
        problems.append(f"coupés ou hors de la fenêtre : {cut}")
    picker = page.locator("#theme-picker")
    shown = picker.evaluate("(s) => s.options[s.selectedIndex].textContent.trim()")
    if shown != words:
        problems.append(f"sélecteur « {shown} »")
    picker.focus()
    page.keyboard.press("ArrowDown")
    time.sleep(0.2)
    moved = (picker.input_value(), _theme_attr(r), page.text_content(".display-menu-symbol"))
    if moved != ("light", "light", "☀"):
        problems.append(f"au clavier : {moved}")
    picker.select_option("system")
    _close_display(page)
    return " ; ".join(problems)


# ---------- languages (2/5): « Affichage ▾ », the theme, the language and the projection ----------


def _open_display(page: Page) -> None:
    """The theme, the language and the projection mode are in « Affichage ▾ » (decision of
    2026-09-30), in the shared bar at the head of every page since story 2 of 2026-09-30: the
    menu is opened first. A page without it as is."""
    if not page.locator("#display-menu-toggle").count():
        return
    if page.locator("#display-menu-panel").is_hidden():
        page.locator("#display-menu-toggle").click()
        expect(page.locator("#display-menu-panel")).to_be_visible(timeout=5000)


def _close_display(page: Page) -> None:
    panel = page.locator("#display-menu-panel")
    if panel.count() and panel.is_visible():
        page.locator("#display-menu-toggle").click()
        expect(page.locator("#display-menu-panel")).to_be_hidden(timeout=5000)


def _pick_theme(page: Page, theme: str) -> None:
    _open_display(page)
    page.locator("#theme-picker").select_option(theme)
    _close_display(page)


def _toggle_projection(page: Page) -> None:
    _open_display(page)
    page.locator("#projection-toggle").click()
    _close_display(page)


def _theme_attr(r: Run) -> str | None:
    return r.page.evaluate("() => document.documentElement.getAttribute('data-theme')")


def _stored_theme(r: Run) -> str | None:
    return r.page.evaluate(f"() => localStorage.getItem('{THEME_KEY}')")


def _body_bg(r: Run) -> str:
    return r.css(r.page.locator("body"), "background-color")


def s_themes(r: Run) -> None:
    """Story 31: « Système » by default and following the workstation, « Sombre » chosen and
    kept (before app.js, on every page), the tokens of the dark palette, the contrasts of both
    themes, a corrupt value, no storage. Ends on « Système » and a light workstation."""
    page = r.page
    page.set_viewport_size({"width": 1600, "height": 1000})
    errors: list[str] = []
    on_error = lambda e: errors.append(str(e))  # noqa: E731
    page.on("pageerror", on_error)
    try:
        _themes(r, errors)
    finally:
        page.remove_listener("pageerror", on_error)
        page.unroute("**/static/app.js")
        page.emulate_media(color_scheme="light")
        if not page.url.startswith(r.stack.app_url) or "/static" in page.url:
            r.goto_app()
        if page.locator("#theme-picker").count():
            _pick_theme(page, "system")


def _themes(r: Run, errors: list[str]) -> None:
    page = r.page
    page.emulate_media(color_scheme="light")
    r.launch("network_tools")
    r.send("Résume l'article Wikipédia sur le Mont-Saint-Michel.")
    page.evaluate(f"() => localStorage.removeItem('{THEME_KEY}')")
    r.reload_app()
    while page.locator("#pane-chips .pane-chip").count():
        page.locator("#pane-chips .pane-chip").first.click()
    time.sleep(0.5)

    # « Système », no attribute; the bar still on one line with the picker.
    picker = page.locator("#theme-picker")
    options = picker.locator("option").evaluate_all(
        "os => os.map(o => [o.value, o.textContent.trim()])"
    )
    r.check(
        picker.input_value() == "system"
        and options == [["system", "◐ Système"], ["light", "☀ Clair"], ["dark", "☾ Sombre"]],
        "#theme-picker : « Système », puis Clair et Sombre",
        f"{picker.input_value()} {options}",
    )
    r.check(_theme_attr(r) is None, "aucun choix mémorisé : pas d'attribut data-theme")
    fits, detail = _bar_fits(r)
    r.check(
        fits,
        "1600 × 1000 : chaque commande de la barre commune et de la barre de l'atelier entière, "
        "sur une ligne",
        detail,
    )
    closed = page.locator("#display-menu-panel").is_hidden()
    menu = _display_menu_picker(r)
    r.check(
        closed and not menu,
        "1600 × 1000 : « Affichage ▾ » fermé, puis ouvert sur le thème avec ses mots",
        menu,
    )
    page.set_viewport_size({"width": 1440, "height": 900})
    time.sleep(0.3)
    fits, detail = _bar_fits(r)
    r.check(fits, "1440 × 900 : barre de l'atelier sur une ligne, « Réinitialiser » entier", detail)
    # At 1280 px, « Affichage ▾ » in the shared bar, its menu whole and working with the
    # keyboard; the main screen's bar under the panes, its panels whole above it.
    # In projection mode too.
    page.set_viewport_size({"width": 1280, "height": 720})
    time.sleep(0.3)
    for projection in (False, True):
        mode = "mode projection" if projection else "mode normal"
        if projection:
            _toggle_projection(page)
            time.sleep(0.3)
        fits, detail = _bar_fits(r)
        menu = _display_menu_picker(r)
        panels = _bar_panels_problems(r)
        r.check(
            fits and not menu and not panels,
            f"1280 × 720, {mode} : « Affichage ▾ » entier, son menu au clavier, deux barres sur "
            "une ligne, « Fenêtre » et « Volets ▾ » entiers au-dessus de la barre de l'atelier",
            f"{detail} ; {menu} ; {panels}",
        )
        if projection:
            _toggle_projection(page)
            time.sleep(0.3)
    page.set_viewport_size({"width": 1600, "height": 1000})
    time.sleep(0.3)
    light_sweep = _contrast_sweep(r, _BARS_AND_PANES)
    r.check(
        not light_sweep,
        "thème clair : balayage des contrastes (deux barres et cinq volets)",
        "; ".join(light_sweep[:6]),
        known="clair-préexistant",
    )

    # « Système » follows the workstation, without a reload (CSS only).
    page.emulate_media(color_scheme="dark")
    time.sleep(0.3)
    r.check(
        _theme_attr(r) is None and _body_bg(r) == _design_rgb("surface-dark"),
        "poste sombre, « Système » : fond de body en surface-dark, sans rechargement",
        _body_bg(r),
    )
    page.emulate_media(color_scheme="light")
    time.sleep(0.3)
    r.check(
        _body_bg(r) == _design_rgb("surface"),
        "poste clair : le fond de body revient à surface",
        _body_bg(r),
    )

    # « Sombre » chosen on a light workstation.
    _pick_theme(page, "dark")
    time.sleep(0.3)
    r.check(
        _theme_attr(r) == "dark" and _stored_theme(r) == "dark",
        '« Sombre » : <html data-theme="dark">, wavestack.theme mémorisé',
        f"{_theme_attr(r)} / {_stored_theme(r)}",
    )
    fill = _design_rgb("ink-fill-dark")
    bubble = page.locator("#chat .bubble-user").last
    call_tile = page.locator(
        "#orch-scroll .turn-step",
        has=page.locator(".turn-step-title", has_text="Appelle le modèle"),
    ).last.locator(".turn-step-tile")
    plate = page.locator(
        "#schema .arch-cloud-model, #schema .arch-server-model, #schema .arch-robots"
    ).first
    fills = {
        "barre de l'atelier": r.css(page.locator(".top-bar"), "background-color"),
        "dernière bulle": r.css(bubble, "background-color"),
        "tuile de l'appel au modèle": r.css(call_tile, "background-color"),
        "plaque du modèle": r.css(plate, "background-color"),
    }
    wrong = {k: v for k, v in fills.items() if v != fill}
    r.check(
        not wrong,
        "sombre : barre de l'atelier, bulle, tuile et plaque du modèle en ink-fill-dark",
        str(wrong),
    )
    prompt = (
        page.locator("#ctx .ctx-section")
        .filter(
            has=page.locator(".ctx-section-label", has_text=re.compile(r"^Prompt système · ≈? ?\d"))
        )
        .first
    )
    r.check(
        r.css(prompt, "border-left-color") == _design_rgb("discipline-prompt-dark"),
        "sombre : filet du prompt système en discipline-prompt-dark",
        r.css(prompt, "border-left-color"),
    )
    segs = page.eval_on_selector_all(
        ".gauge-seg",
        "ss => ss.map(s => [s.dataset.discipline || '', getComputedStyle(s).backgroundColor])",
    )
    off = [(d, bg) for d, bg in segs if not d or bg != _design_rgb(f"discipline-{d}-dark")]
    r.check(
        bool(segs) and not off,
        "sombre : chaque segment de la jauge sur le jeton sombre de sa discipline",
        f"{len(segs)} segments ; écarts : {off}",
    )
    dark_sweep = _contrast_sweep(r, _BARS_AND_PANES)
    r.check(
        not dark_sweep,
        "sombre : aucun contraste sous AA dans les deux barres et les cinq volets",
        "; ".join(dark_sweep[:8]),
    )
    # What opens over the panes: the « Volets ▾ » list, the « Fenêtre » panel, the drawer.
    page.locator("#pane-menu-toggle").click()
    expect(page.locator("#pane-menu-list")).to_be_visible(timeout=5000)
    overlays = {"liste « Volets ▾ »": _contrast_sweep(r, ["#pane-menu-list"])}
    page.locator("#pane-menu-toggle").click()
    page.locator("#window-toggle").click()
    expect(page.locator("#window-panel")).to_be_visible(timeout=5000)
    overlays["panneau « Fenêtre »"] = _contrast_sweep(r, ["#window-panel"])
    page.keyboard.press("Escape")
    r.card("Prompt système").locator(".brick-edit").click()
    expect(page.locator("#edit-drawer")).to_be_visible(timeout=5000)
    overlays["tiroir d'édition"] = _contrast_sweep(r, ["#edit-drawer"])
    page.locator("#drawer-close").click()
    expect(page.locator("#edit-drawer")).to_be_hidden(timeout=5000)
    r.check(
        not any(overlays.values()),
        "sombre : aucun contraste sous AA dans « Volets ▾ », « Fenêtre » et le tiroir d'édition",
        str({k: v[:4] for k, v in overlays.items() if v}),
    )
    r.shot("46-theme-sombre-atelier", full_page=True)
    r.shot_element("47-theme-sombre-vue-humain", '.pane[data-pane="human"]')
    r.shot_element("48-theme-sombre-schema", '.pane[data-pane="schema"]')

    # Kept at the reload, before app.js (aborted), then the picker once app.js is back.
    page.route("**/static/app.js", lambda route: route.abort())
    page.reload(wait_until="load")
    r.check(
        _theme_attr(r) == "dark" and _body_bg(r) == _design_rgb("surface-dark"),
        'rechargement sans app.js : data-theme="dark" et fond surface-dark déjà posés',
        f"{_theme_attr(r)} {_body_bg(r)}",
    )
    page.unroute("**/static/app.js")
    r.reload_app()
    r.check(
        page.locator("#theme-picker").input_value() == "dark" and not errors,
        "après rechargement : le sélecteur montre « Sombre », aucune pageerror",
        "; ".join(errors[:3]),
    )

    # The same theme on the other pages (same origin), each with its picker.
    # Lot 3 of 2026-10-04: /models redirects to « Diagnostic et modèles »; a card unfolded.
    for path, shot in (("/diagnostic", "49-theme-sombre-diagnostic"),):
        _goto_diagnostic(r)
        _unfold(page.locator("#cloud-models .model-card").first)
        time.sleep(0.5)
        tiles = page.eval_on_selector_all(
            ".model-logo:not(.is-initial)", "ts => ts.map(t => getComputedStyle(t).backgroundColor)"
        )
        r.check(
            bool(tiles) and set(tiles) == {"rgb(255, 255, 255)"},
            "sombre : les logos restent sur leur tuile blanche (logo-tile)",
            str(sorted(set(tiles))),
        )
        sweep = _contrast_sweep(r, ["body"])
        r.check(
            _theme_attr(r) == "dark"
            and _body_bg(r) == _design_rgb("surface-dark")
            and page.locator("#theme-picker").input_value() == "dark"
            and not sweep,
            f"{path} : sombre, son sélecteur sur « Sombre », aucun contraste sous AA",
            f"{_theme_attr(r)} {_body_bg(r)} ; " + "; ".join(sweep[:6]),
        )
        r.shot(shot, full_page=True)
    # « Clair » on the diagnostic wins over a dark workstation, back in the workshop.
    page.goto(f"{r.stack.app_url}/diagnostic")
    _pick_theme(page, "light")
    page.emulate_media(color_scheme="dark")
    r.goto_app()
    r.check(
        _theme_attr(r) == "light" and _body_bg(r) == _design_rgb("surface"),
        "« Clair » choisi au diagnostic, poste sombre : l'atelier reste clair",
        f"{_theme_attr(r)} {_body_bg(r)}",
    )
    page.emulate_media(color_scheme="light")

    # Lot K (A4): « Sombre » in the workshop, « Clair » at the diagnostic, then « Back »: the
    # workshop's picker says « Clair » (the browser's form restoration no longer wins).
    _pick_theme(page, "dark")
    time.sleep(0.2)
    page.goto(f"{r.stack.app_url}/diagnostic")
    expect(page.locator("#theme-picker")).to_have_value("dark", timeout=10_000)
    _pick_theme(page, "light")
    time.sleep(0.2)
    page.go_back()
    r.wait_replayed()
    time.sleep(0.3)
    picked = page.locator("#theme-picker").input_value()
    face = page.text_content(".display-menu-symbol")
    r.check(
        picked == "light" and _theme_attr(r) == "light" and face == "☀",
        "« Sombre », /diagnostic, « Clair », « Précédent » : atelier clair, sélecteur sur "
        "« Clair »",
        f"sélecteur {picked}, data-theme {_theme_attr(r)}, face « {face} »",
    )

    # A corrupt value: « Système », silently.
    page.evaluate(f"() => localStorage.setItem('{THEME_KEY}', 'violet')")
    r.reload_app()
    r.check(
        _theme_attr(r) is None and page.locator("#theme-picker").input_value() == "system",
        "wavestack.theme = « violet » : pas d'attribut, sélecteur sur « Système »",
    )

    # No storage: « Système », a choice for the page only, no error.
    # A context of its own (the run's page has one it owns): its storage starts empty.
    context = page.context.browser.new_context(
        viewport={"width": 1600, "height": 1000}, locale="fr-FR"
    )
    blocked = context.new_page()
    blocked_errors: list[str] = []
    blocked.on("pageerror", lambda e: blocked_errors.append(f"pageerror: {e}"))
    blocked.on("console", lambda m: blocked_errors.append(m.text) if m.type == "error" else None)
    blocked.add_init_script(
        "Storage.prototype.getItem = function () { throw new Error('stockage bloqué'); };"
        "Storage.prototype.setItem = function () { throw new Error('stockage bloqué'); };"
    )
    try:
        blocked.goto(f"{r.stack.app_url}/")
        expect(blocked.locator("body[data-journal-replayed]")).to_be_attached(timeout=30_000)
        start = blocked.evaluate("() => document.documentElement.getAttribute('data-theme')")
        _pick_theme(blocked, "dark")
        time.sleep(0.3)
        chosen = blocked.evaluate("() => document.documentElement.getAttribute('data-theme')")
        kept = blocked.locator("#theme-picker").input_value()
        # A page of the same context, storage unblocked: nothing was written.
        reader = context.new_page()
        reader.goto(f"{r.stack.app_url}/static/theme.js")
        stored = reader.evaluate(f"() => localStorage.getItem('{THEME_KEY}')")
        r.check(
            start is None
            and chosen == "dark"
            and kept == "dark"
            and stored is None
            and not blocked_errors,
            "sans stockage : « Système », puis « Sombre » pour la page seule, sans erreur",
            f"{start} → {chosen} ({kept}) ; mémorisé : {stored} ; {blocked_errors[:3]}",
        )
    finally:
        context.close()

    # The light theme, for comparison.
    _pick_theme(page, "system")
    time.sleep(0.3)
    r.shot("51-theme-clair-atelier", full_page=True)


# ---------- story 34: the linked view, the guided reading of the panes ----------

# What the linked view lights: every `.is-linked` element, named by its class and first text.
_LINKED_JS = """() => [...document.querySelectorAll('.is-linked')]
  .map((e) => `${e.className.replace(/ ?is-(linked|selection-linked)/g, '')}|${
    (e.textContent || '').trim().slice(0, 40)}`)
  .sort()"""

_STEPS_JS = """() => {
  const groups = [...document.querySelectorAll('#orch-scroll .turn-group:not(.harness-prep)')];
  const group = groups.at(-1);
  return [...(group?.querySelectorAll('.turn-step') ?? [])].map((s) => ({
    name: s.querySelector('.turn-step-name').textContent,
    title: s.querySelector('.turn-step-title').textContent,
    letter: s.querySelector('.turn-step-tile').textContent,
    net: s.querySelector('.net-mark').hidden ? ''
      : `${s.querySelector('.net-mark').textContent} ${s.querySelector('.net-host').textContent}`,
    figure: s.querySelector('.turn-step-figure').textContent,
  }));
}"""


def _linking(r: Run) -> bool:
    return r.page.evaluate("() => document.body.classList.contains('linking')")


def _is_linked(locator) -> bool:
    return locator.evaluate("e => e.classList.contains('is-linked')")


def _step(r: Run, name: str):
    """The last step of Orchestration whose title (name and note) says `name`."""
    return (
        r.page.locator("#orch-scroll .turn-step")
        .filter(has=r.page.locator(".turn-step-title", has_text=name))
        .last
    )


_TURN_GROUPS = "#orch-scroll .turn-group:not(.harness-prep)"


def _turn_group(r: Run, turn_id: str):
    """Orchestration's group of turn `turn_id` (its « Tour N » names the id in its tooltip)."""
    title = _ui_catalogue("fr")["main.turn.id_title"].format(id=turn_id)
    return r.page.locator(_TURN_GROUPS).filter(
        has=r.page.locator(f'.turn-group-title[title="{title}"]')
    )


def _turn_rendered_ended(r: Run, turn_id: str | None = None, timeout: float = 10) -> None:
    """Restes différés, story 6: the page rendered the turn (by default the last one the
    stream thread saw end) as ended, its group no longer `is-live`: the stream thread may
    read `turn_ended` before the page renders it."""
    if turn_id is None:
        turn_id = r.ev.since(0, "turn_ended")[-1]["turn_id"]
    group = _turn_group(r, turn_id)
    expect(group).to_have_count(1, timeout=timeout * 1000)
    expect(group).not_to_have_class(re.compile(r"\bis-live\b"), timeout=timeout * 1000)


# ---------- restes différés, story 6 (E033): resizing the panes, their layout remembered ----------

_PANES_KEY = "wavestack.panes"
_PANE_IDS = ["bricks", "human", "ctx", "orch", "schema"]
_PANE_SIZES_JS = """() => {
  const box = (node) => {
    const rect = node.getBoundingClientRect();
    return { w: rect.width, h: rect.height };
  };
  const sizes = { top: box(document.querySelector('.top-row')) };
  for (const pane of document.querySelectorAll('.pane[data-pane]')) {
    sizes[pane.dataset.pane] = box(pane);
  }
  return sizes;
}"""


def _pane_sizes(r: Run) -> dict[str, dict[str, float]]:
    return r.page.evaluate(_PANE_SIZES_JS)


def _stored_panes(r: Run) -> Any:
    raw = r.page.evaluate(f"() => localStorage.getItem('{_PANES_KEY}')")
    try:
        return json.loads(raw) if raw else {}
    except ValueError:
        return raw


def _reload_with_panes(r: Run, value: str | None) -> None:
    """`localStorage["wavestack.panes"]` set to `value` (removed when `None`), then a reload."""
    r.page.evaluate(
        "([key, value]) => value === null ? localStorage.removeItem(key)"
        " : localStorage.setItem(key, value)",
        [_PANES_KEY, value],
    )
    r.reload_app()
    r.wait_idle()


def _hidden_panes(r: Run) -> list[str]:
    return r.page.evaluate(
        "() => [...document.querySelectorAll('.pane.is-hidden')].map((p) => p.dataset.pane)"
    )


def _near(a: float, b: float) -> bool:
    return abs(a - b) < 1.5


def _press(r: Run, key: str, times: int = 1) -> None:
    for _ in range(times):
        r.page.keyboard.press(key)


def s_panes(r: Run) -> None:
    """E033 (restes différés, story 6): the gutter handles by keyboard (16 px a press): only
    the two neighbours move, each stops at its minimum, the schema's handle moves its height
    the right way; a double click goes back to the default proportions; hiding a pane is
    stored at once; a stored layout comes back, a corrupt one or five hidden panes leave the
    defaults. `app.js` is a module: `moveBoundary` and `loadPaneLayout` are read from what
    they lay out."""
    page = r.page
    page.set_viewport_size({"width": 1600, "height": 1000})
    errors: list[str] = []
    listener = lambda e: errors.append(str(e))  # noqa: E731
    page.on("pageerror", listener)
    top = ["bricks", "human", "ctx", "orch"]
    try:
        _reload_with_panes(r, None)
        base = _pane_sizes(r)
        handle = page.locator('.pane-resize-handle[data-handle="human"]')
        handle.focus()
        _press(r, "ArrowRight")
        r.poll(lambda: _near(_pane_sizes(r)["human"]["w"], base["human"]["w"] + 16), 3)
        moved = {p: round(_pane_sizes(r)[p]["w"] - base[p]["w"], 1) for p in top}
        stored = _stored_panes(r)
        r.check(
            _near(moved["human"], 16)
            and _near(moved["ctx"], -16)
            and _near(moved["orch"], 0)
            and _near(moved["bricks"], 0)
            and {"human", "ctx"} <= set(stored.get("sizes", {})),
            "E033 : → sur la poignée Vue humain | Contexte LLM : +16 px d'un côté, −16 px de "
            "l'autre, les autres volets immobiles, mémorisé",
            f"{moved} · {stored}",
        )
        _press(r, "ArrowLeft", 40)
        low = _pane_sizes(r)
        _press(r, "ArrowRight")  # the boundary was stopped at the minimum, not pushed past it
        back = _pane_sizes(r)
        r.check(
            _near(low["human"]["w"], 240)
            and _near(back["human"]["w"], 256)
            and _near(low["orch"]["w"], base["orch"]["w"]),
            "E033 : ← répété : la Vue humain s'arrête à sa largeur minimale (240 px) ; un → "
            "la rend aussitôt à 256 px",
            f"Vue humain {low['human']['w']:.1f} puis {back['human']['w']:.1f} · "
            f"Orchestration {low['orch']['w']:.1f}",
        )
        _press(r, "ArrowRight", 80)
        high = _pane_sizes(r)
        r.check(
            _near(high["ctx"]["w"], 240) and _near(high["orch"]["w"], base["orch"]["w"]),
            "E033 : → répété : le Contexte LLM s'arrête à sa largeur minimale (240 px)",
            f"Contexte LLM {high['ctx']['w']:.1f} · Orchestration {high['orch']['w']:.1f}",
        )
        handle.dblclick()
        reset = _pane_sizes(r)
        stored = _stored_panes(r)
        r.check(
            all(_near(reset[p]["w"], base[p]["w"]) for p in top)
            and not {"human", "ctx", "orch"} & set(stored.get("sizes", {})),
            "E033 : double clic sur la poignée : proportions par défaut, oubliées du stockage",
            f"{ {p: round(reset[p]['w']) for p in top} } · {stored}",
        )

        schema = page.locator('.pane-resize-handle[data-handle="schema"]')
        schema.focus()
        _press(r, "ArrowDown")
        r.poll(lambda: _near(_pane_sizes(r)["schema"]["h"], base["schema"]["h"] - 16), 3)
        lower = _pane_sizes(r)
        r.check(
            _near(lower["schema"]["h"], base["schema"]["h"] - 16)
            and _near(lower["top"]["h"], base["top"]["h"] + 16),
            "E033 : ↓ sur la poignée du schéma : la frontière descend, le schéma perd 16 px, la "
            "rangée du haut les gagne",
            f"schéma {base['schema']['h']:.0f} → {lower['schema']['h']:.0f} · rangée du haut "
            f"{base['top']['h']:.0f} → {lower['top']['h']:.0f}",
        )
        schema.dblclick()

        page.locator('.pane[data-pane="ctx"] [data-action="hide"]').click()
        stored = _stored_panes(r)
        r.check(
            "ctx" in stored.get("hidden", []),
            "E033 : masquer un volet l'inscrit aussitôt dans le stockage",
            str(stored),
        )
        _reload_with_panes(r, json.dumps({"hidden": ["ctx"], "sizes": {"bricks": 300}}))
        kept = _pane_sizes(r)
        r.check(
            _hidden_panes(r) == ["ctx"] and _near(kept["bricks"]["w"], 300),
            "E033 : au rechargement, le volet masqué et la largeur mémorisés reviennent",
            f"{_hidden_panes(r)} · briques {kept['bricks']['w']:.1f}",
        )
        _reload_with_panes(r, "{pas du json")
        corrupt = _pane_sizes(r)
        r.check(
            _hidden_panes(r) == [] and all(_near(corrupt[p]["w"], base[p]["w"]) for p in top),
            "E033 : stockage illisible : disposition par défaut",
            f"{_hidden_panes(r)} · { {p: round(corrupt[p]['w']) for p in top} }",
        )
        invalid = {"hidden": _PANE_IDS, "sizes": {"bricks": -5, "human": "x", "schema": 1e9}}
        _reload_with_panes(r, json.dumps(invalid))
        refused = _pane_sizes(r)
        r.check(
            _hidden_panes(r) == []
            and all(_near(refused[p]["w"], base[p]["w"]) for p in top)
            and _near(refused["schema"]["h"], base["schema"]["h"]),
            "E033 : cinq volets masqués et tailles invalides refusés : tout visible, tailles "
            "par défaut",
            f"{_hidden_panes(r)} · { {p: round(refused[p]['w']) for p in top} }",
        )
        r.check(not errors, "E033 : aucune erreur de page", "; ".join(errors)[:300])
        _reload_with_panes(r, None)
        _focus_mode_keeps_the_page_still(r)
    finally:
        page.remove_listener("pageerror", listener)
        page.set_viewport_size({"width": 1600, "height": 1000})
        _reload_with_panes(r, None)


_SCROLL_TO_OUTBOUND_JS = """() => {
  const target = [...document.querySelectorAll('#orch-scroll .outbound-payload')].at(-1)
    || [...document.querySelectorAll('#orch-scroll .turn-step')].at(-1);
  if (target) target.scrollIntoView({ block: 'center' });
  return Boolean(target);
}"""


def _focus_mode_keeps_the_page_still(r: Run) -> None:
    """Recette du 02/10: each pane in focus mode (⛶), at 1280×672 and 1440×900: a scroll of
    Orchestration to its outbound data, the wheel, then End never scroll the page
    (`document.scrollingElement.scrollTop` stays 0) and the bottom bar stays under the panes.
    Orchestration first gets a turn with an outbound block (its failed tool step unfolds)."""
    page = r.page
    if page.locator("#orch-scroll .outbound-payload").count() == 0:
        r.launch("network_tools")
        r.send("Quels sont les jours fériés en France cette année ?")
        time.sleep(0.5)
    problems: list[str] = []
    for width, height in ((1280, 672), (1440, 900)):
        page.set_viewport_size({"width": width, "height": height})
        for pane in _PANE_IDS:
            focus = page.locator(f'.pane[data-pane="{pane}"] .pane-focus')
            focus.click()
            time.sleep(0.2)
            reached = page.evaluate(_SCROLL_TO_OUTBOUND_JS) if pane == "orch" else True
            box = page.locator(f'.pane[data-pane="{pane}"]').bounding_box()
            if box:
                page.mouse.move(box["x"] + box["width"] / 2, box["y"] + box["height"] / 2)
                page.mouse.wheel(0, 3000)
            page.keyboard.press("End")
            time.sleep(0.3)
            top = page.evaluate("() => document.scrollingElement.scrollTop")
            bar = _bar_under_panes(r)
            if top != 0 or bar or not reached:
                problems.append(
                    f"{pane} {width}×{height} : scrollTop {top}"
                    + (f", {bar}" if bar else "")
                    + ("" if reached else ", rien vers quoi défiler")
                )
            page.evaluate("() => window.scrollTo(0, 0)")
            focus.click()
            time.sleep(0.2)
    r.check(
        not problems,
        "mode focus de chaque volet (1280×672, 1440×900) : défilement d'Orchestration vers ses "
        "données sortantes, molette, Fin : la page ne défile pas, la barre reste sous les volets",
        "; ".join(problems)[:500],
    )


def s_linked_view(r: Run) -> None:
    """Story 34: hover, focus and click light what is linked in every pane, Escape clears;
    the numbered panes, the frieze of the rail, the outbound summary, the projection mode."""
    page = r.page
    page.set_viewport_size({"width": 1600, "height": 1000})
    r.launch("network_tools")
    seq = r.ev.mark()
    ended = r.send("Résume l'article Wikipédia sur le Mont-Saint-Michel.")
    turn_id = ended["turn_id"]
    time.sleep(0.5)
    r.rest_pointer()

    # Hover: the Outils card lights its nodes, segments and steps; the rest is dimmed.
    r.card("Outils").locator("p.brick-status").hover()
    time.sleep(0.3)
    wiki = page.locator("#schema .arch-node", has_text="Résumé Wikipédia").first
    calc = page.locator("#schema .arch-node", has_text="Calculatrice").first
    lit_segments = page.locator("#ctx .ctx-section.is-linked").count()
    tool_step = _step(r, "Exécute l'outil hors du poste")
    memory_opacity = float(r.css(r.card("Mémoire globale"), "opacity") or 1)
    r.check(
        _linking(r)
        and _is_linked(wiki)
        and _is_linked(calc)
        and lit_segments >= 1
        and _is_linked(tool_step)
        and memory_opacity < 0.5,
        "survol de la carte Outils : nœuds, segments et étape d'outil éclairés, "
        "carte Mémoire globale estompée",
        f"linking {_linking(r)}, Wikipédia {_is_linked(wiki)}, Calculatrice {_is_linked(calc)}, "
        f"{lit_segments} segments, étape {_is_linked(tool_step)}, opacité {memory_opacity}",
    )
    r.shot("35-vue-liee-survol", keep_pointer=True)
    # Languages (2/5): the title leaves the bar under 1 700 px; « Réinitialiser » links nothing.
    page.locator("#reset-button").hover()
    time.sleep(0.2)
    r.check(not _linking(r), "pointeur sur « Réinitialiser » : plus d'éclairage")

    # Hover: a gauge segment, the model's plate, the model's calls.
    page.locator('.gauge-seg[data-discipline="harness"]').first.hover()
    time.sleep(0.2)
    r.check(
        _is_linked(r.card("Outils")),
        "survol du segment harness de la jauge : la carte Outils s'éclaire",
    )
    plate = page.locator(
        "#schema .arch-cloud-model, #schema .arch-server-model, #schema .arch-robots"
    )
    plate.first.hover()
    time.sleep(0.2)
    flags = page.locator("#ctx .ctx-section").evaluate_all(
        "ss => ss.map(s => s.classList.contains('is-linked'))"
    )
    r.check(
        bool(flags) and all(flags),
        "survol de la plaque du modèle : chaque section de Contexte LLM s'éclaire",
        f"{sum(flags)} / {len(flags)}",
    )
    # Story 32: Contexte LLM shows every call of the turn; a call step lights the sections of
    # its own call (« Répond », the last one; « Appelle le modèle », an older one), no other.
    for name in ("Répond", "Appelle le modèle"):
        step = _step(r, name)
        call_id = next(
            (
                k[5:]
                for k in (step.get_attribute("data-links") or "").split()
                if k.startswith("call:")
            ),
            "",
        )
        step.locator(".turn-step-line").hover()
        time.sleep(0.2)
        flags = page.locator("#ctx .ctx-section").evaluate_all(
            "(ss, id) => ss.map(s => [s.closest('.ctx-call')?.dataset.callId === id,"
            " s.classList.contains('is-linked')])",
            call_id,
        )
        own = [lit for mine, lit in flags if mine]
        others = [lit for mine, lit in flags if not mine]
        r.check(
            _is_linked(plate.first) and bool(own) and all(own) and not any(others),
            f"survol de « {name} » : plaque du modèle et sections de son appel éclairées, "
            "celles de l'autre appel non",
            f"appel {call_id}, plaque {_is_linked(plate.first)}, sections {sum(own)} / {len(own)}"
            f", autres {sum(others)} / {len(others)}",
        )

    # Keyboard: a focused section, then a step line reached by Tab, light as the hover does.
    segment = page.locator("#ctx .ctx-section").first
    segment.hover()
    time.sleep(0.2)
    hovered = page.evaluate(_LINKED_JS)
    r.rest_pointer()
    segment.locator(".ctx-section-select").focus()  # story 32: the margin is its control
    time.sleep(0.2)
    focused = page.evaluate(_LINKED_JS)
    r.check(
        bool(hovered) and focused == hovered,
        "segment de Contexte LLM au clavier : même éclairage qu'au survol",
        f"{len(focused)} / {len(hovered)} éléments",
    )
    target = _step(r, "Exécute l'outil hors du poste").locator(".turn-step-line")
    target.hover()
    time.sleep(0.2)
    hovered = page.evaluate(_LINKED_JS)
    r.rest_pointer()
    _step(r, "Demande un outil").locator(".turn-step-line").focus()
    page.keyboard.press("Tab")
    time.sleep(0.2)
    on_line = page.evaluate(
        "() => document.activeElement?.closest('.turn-step')?.querySelector('.turn-step-title')"
        "?.textContent ?? ''"
    )
    focused = page.evaluate(_LINKED_JS)
    r.check(
        on_line.startswith("Exécute l'outil hors du poste")
        and bool(hovered)
        and focused == hovered,
        "étape d'Orchestration atteinte par Tab : même éclairage qu'au survol",
        f"focus sur « {on_line} », {len(focused)} / {len(hovered)} éléments",
    )
    page.evaluate("() => document.activeElement?.blur()")
    time.sleep(0.2)
    r.check(not _linking(r), "focus perdu : plus d'éclairage")

    # Click: a persistent selection, an ink outline in every pane, « lié » on a hidden pane's
    # chip; Escape clears it.
    calc.click()
    time.sleep(0.3)
    shown = page.evaluate(
        "() => ['#ctx .ctx-section', '#orch-scroll .turn-step'].map((q) =>"
        " [...document.querySelectorAll(`${q}.is-selection-linked`)]"
        ".some((e) => e.getClientRects().length > 0))"
    )
    r.check(
        all(shown) and not _linking(r),
        "clic sur le nœud Calculatrice : un segment et une étape visibles cerclés d'encre, "
        "rien d'estompé sous le pointeur resté sur la source",
        f"segment, étape : {shown} ; estompage {_linking(r)}",
    )
    page.locator('.pane[data-pane="ctx"] .pane-hide').click()
    time.sleep(0.3)
    card = r.card("Outils")
    chip = page.locator("#pane-chips .pane-chip", has_text="Contexte LLM")
    selected = card.evaluate("e => e.classList.contains('is-selection-linked')")
    r.check(
        selected
        and r.css(card, "outline-color") == r.token_color("--color-ink")
        and "lié" in chip.inner_text()
        and "lié" in (chip.get_attribute("aria-label") or ""),
        "clic sur le nœud Calculatrice : carte Outils cerclée d'encre, "
        "puce « + Contexte LLM · lié »",
        f"sélection {selected}, contour {r.css(card, 'outline-color')}, "
        f"puce « {chip.inner_text()} »",
    )
    r.shot("36-selection-liee")
    page.keyboard.press("Escape")
    time.sleep(0.3)
    left = page.locator(".is-selection-linked").count()
    r.check(
        left == 0 and "lié" not in chip.inner_text(),
        "Échap : sélection effacée partout, la puce ne dit plus « lié »",
        f"{left} éléments encore sélectionnés, puce « {chip.inner_text()} »",
    )
    chip.click()
    time.sleep(0.3)

    # Reduced motion: no fade.
    page.emulate_media(reduced_motion="reduce")
    duration = r.css(r.card("Outils"), "transition-duration")
    page.emulate_media(reduced_motion="no-preference")
    r.check(duration == "0s", "mouvement réduit : aucune transition sur une carte", duration)

    # The panes, numbered and subtitled, in reading order; the bricks panel without a number.
    heads = page.evaluate(
        "() => ['human', 'ctx', 'orch', 'schema', 'bricks'].map((id) => {"
        ' const h = document.querySelector(`.pane[data-pane="${id}"] .pane-header`);'
        " return [h.querySelector('.pane-step')?.textContent ?? null,"
        " h.querySelector('.pane-title').textContent,"
        " h.querySelector('.pane-subtitle').textContent]; })"
    )
    expected = [
        ["1", "Vue humain", "Ce que voit l'utilisateur"],
        ["2", "Contexte LLM", "Ce que le modèle lit, dans l'ordre"],
        ["3", "Orchestration", "Ce que fait le harnais, pas à pas"],
        ["4", "Schéma d'architecture", "Où tourne chaque pièce"],
    ]
    r.check(
        heads[:4] == expected and heads[4][0] is None,
        "volets numérotés 1 à 4 avec leur sous-titre ; panneau des briques sans numéro",
        str(heads),
    )
    hint = page.locator("#bricks .brick-link-hint").inner_text()
    r.check(
        hint.startswith("Survolez une brique"),
        "panneau des briques : l'aide sur la vue liée sous la légende",
        hint,
    )

    # The frieze: verbs, who acts, the network row, the final answer's figure.
    steps = page.evaluate(_STEPS_JS)
    names = [s["name"] for s in steps]
    letters = [s["letter"] for s in steps]
    r.check(
        names
        == [
            "Décrit les outils",
            "Appelle le modèle",
            "Demande un outil",
            "Exécute l'outil hors du poste",
            "Réinjecte le résultat",
            "Répond",
        ]
        and letters == ["H", "M", "M", "R", "H", "M"],
        "Orchestration : titres en verbes, pastilles H, M, M, R, H, M",
        f"{names} {letters}",
    )
    network = next((s for s in steps if s["name"] == "Exécute l'outil hors du poste"), {})
    answer = next((s for s in steps if s["name"] == "Répond"), {})
    r.check(
        "Résumé Wikipédia" in network.get("title", "")
        and network.get("net") == "🌐 RÉSEAU → fr.wikipedia.org",
        "la ligne réseau nomme l'outil et « 🌐 RÉSEAU → fr.wikipedia.org »",
        str(network),
    )
    r.check(
        re.search(r"écrits · [\d,]+ s", answer.get("figure", "")) is not None,
        "« Répond » : sa figure (écrits, durée)",
        answer.get("figure", ""),
    )
    _step(r, "Décrit les outils").locator(".turn-step-line").click()
    time.sleep(0.3)
    r.check(
        _step(r, "Décrit les outils").locator(".turn-step-body").count() == 1,
        "un clic sur une ligne déplie toujours son détail",
    )
    r.shot_element("37-frise-orchestration", '.pane[data-pane="orch"]')
    page.keyboard.press("Escape")  # the step's selection
    if page.locator("#follow-live").is_visible():
        page.click("#follow-live")

    # The outbound summary under the schema.
    # K: the model's calls and the requests of the tool steps that did not fail; a failed
    # step (the network cut by the launcher) is one failed attempt, listed apart.
    in_turn = [e for e in r.ev.since(seq) if e.get("turn_id") == turn_id]
    calls = sum(1 for e in in_turn if e["kind"] == "model_call_started")
    failed_steps = {
        e["step_id"]
        for e in in_turn
        if e["kind"] == "tool_ended" and e["payload"].get("status") != "ok"
    }
    requests = sum(
        1
        for e in in_turn
        if e["kind"] == "outbound_request"
        and e["payload"].get("origin") == "brick"
        and e["step_id"] not in failed_steps
    )
    summary = page.inner_text("#schema-outbound")
    wanted = [
        f"quitté le poste {calls + requests} fois",
        "vers le modèle chez",
        "contexte complet",
        "1 tentative en échec vers Résumé Wikipédia (le titre de l'article)",
    ]
    missing = [w for w in wanted if w not in summary]
    r.check(
        summary.startswith("Au tour") and not missing and "requête" not in summary,
        f"bilan des sorties : {calls} appels et {requests} requête(s) sorties, "
        "la tentative en échec à part",
        f"manque {missing} dans « {summary} »" if missing else summary,
    )

    def node(name: str):
        return page.locator("#schema .arch-node", has_text=name).first

    tips = {
        name: node(name).get_attribute("title") or ""
        for name in ("Résumé Wikipédia", "Jours fériés", "Lecture de page web")
    }
    pill = node("Résumé Wikipédia").locator(".arch-node-pill").inner_text()
    page_pill = node("Lecture de page web").locator(".arch-node-pill").inner_text()
    r.check(
        "Au tour 1 : tentative en échec" in tips["Résumé Wikipédia"]
        and pill in ("en échec", "indisponible")
        and "Au tour 1 : non contacté." in tips["Jours fériés"]
        and page_pill == "non contacté",
        "schéma : Wikipédia en échec au tour 1 (rien ne l'a atteint), Jours fériés et Lecture "
        "de page web non contactés",
        f"{tips} ; pastilles « {pill} », « {page_pill} »",
    )
    r.shot_element("38-bilan-des-sorties", '.pane[data-pane="schema"]')

    # Projection mode: every text larger, remembered, kept by the reset.
    toggle = page.locator("#projection-toggle")
    _toggle_projection(page)
    time.sleep(0.3)

    def projection() -> tuple[bool, str, str]:
        return (
            page.evaluate("() => document.documentElement.classList.contains('projection')"),
            r.css(page.locator("body"), "font-size"),
            toggle.get_attribute("aria-pressed") or "",
        )

    on, size, pressed = projection()
    cut = _fully_visible(r, "#reset-button")
    over = page.evaluate(
        "() => { const bar = document.querySelector('.top-bar').getBoundingClientRect();"
        " return [...document.querySelectorAll('.top-bar > *')]"
        ".filter(e => e.offsetParent && getComputedStyle(e).position !== 'absolute')"
        ".filter(e => { const b = e.getBoundingClientRect();"
        " return b.right > bar.right + 1 || b.bottom > bar.bottom + 1 || b.top < bar.top - 1; })"
        ".map(e => e.id || e.className); }"
    )
    r.check(
        on and size == "18px" and pressed == "true" and not cut and not over,
        "Mode projection : textes à 18 px, bouton pressé, barre de l'atelier sur une ligne "
        "à 1600 × 1000",
        f"{on} {size} {pressed} ; Réinitialiser : {cut or 'visible'} ; débordent : {over}",
    )
    r.shot("39-mode-projection")
    # Lot K (A1): a selection shown on a hidden pane's chip, whole with 10 px to spare (the
    # fonts of Windows are wider than the container's), the bar on one line, « Réinitialiser »
    # whole and the gauge's legend never under « Fenêtre ▾ », at four widths, projection mode
    # then normal mode; at 1024 px (1280 px zoomed to 125 %), the bar and the legend only.
    node("Calculatrice").click()
    page.locator('.pane[data-pane="ctx"] .pane-hide').click()
    time.sleep(0.5)
    chip = page.locator("#pane-chips .pane-chip", has_text="Contexte LLM")
    for projection_on in (True, False):
        if not projection_on:
            _toggle_projection(page)
        mode = "mode projection" if projection_on else "mode normal"
        for width, height in ((1280, 720), (1366, 768), (1440, 900), (1600, 1000)):
            page.set_viewport_size({"width": width, "height": height})
            time.sleep(0.3)
            if "· lié" not in chip.inner_text():  # a click in the bar may clear the selection
                node("Calculatrice").click()
                time.sleep(0.3)
            problems = _top_bar_problems(r, chip)
            r.check(
                not problems,
                f"{width} × {height} en {mode} : barre sur une ligne, « Réinitialiser » entier, "
                "légende de la jauge dégagée, « · lié » entier sur la puce (10 px de marge)",
                "; ".join(problems) or f"puce « {chip.inner_text()} »",
            )
        # Lot K, suite (K1): 1280 and 1366 px zoomed to 150 % (853 and 911 CSS px; a real
        # Edge window's frame leaves a little less, 840), the chip linked but free to give
        # way: the bar on one line, « Réinitialiser » in the window, no horizontal scroll, the
        # « Fenêtre » panel open whole in the window.
        for width, height in ((840, 433), (853, 433), (911, 512)):
            page.set_viewport_size({"width": width, "height": height})
            time.sleep(0.3)
            if "· lié" not in chip.inner_text():
                node("Calculatrice").click()
                time.sleep(0.3)
            problems = _top_bar_problems(r, None)
            if "· lié" not in chip.inner_text():
                problems.append(f"puce « {chip.inner_text()} » sans « · lié »")
            if cut := _fully_visible(r, "#reset-button"):
                problems.append(f"« Réinitialiser » {cut}")
            scroll = page.evaluate(
                "() => { const s = document.scrollingElement;"
                " return s.scrollWidth - s.clientWidth; }"
            )
            if scroll > 1:
                problems.append(f"la page défile de {scroll} px en largeur")
            if outside := _window_panel_outside(page):
                problems.append(outside)
            chip_cut, figures = page.evaluate(
                "(c) => [c.scrollWidth - c.clientWidth, Math.round(document"
                ".getElementById('gauge-figures').getBoundingClientRect().width)]",
                chip.element_handle(),
            )
            r.check(
                not problems,
                f"{width} × {height} (zoom 150 %) en {mode} : barre sur une ligne, "
                "« Réinitialiser » entier dans la fenêtre, aucun défilement horizontal, "
                "panneau « Fenêtre » entier",
                "; ".join(problems)
                or f"puce « {chip.inner_text()} » coupée de {chip_cut} px ; chiffres de la "
                f"jauge sur {figures} px",
            )
    # 1280 px zoomed to 125 % (1024 CSS px; a real Edge window's frame leaves about 1005):
    # the legend stays shown, whole and clear of « Fenêtre ▾ ».
    for width in (1024, 1005):
        page.set_viewport_size({"width": width, "height": 700})
        time.sleep(0.3)
        problems = _top_bar_problems(r, None)
        if cut := _fully_visible(r, "#gauge-legend"):
            problems.append(f"légende de la jauge {cut}")
        r.check(
            not problems,
            f"{width} × 700 : barre sur une ligne, « Réinitialiser » entier, légende de la jauge "
            "visible et dégagée",
            "; ".join(problems),
        )
    _toggle_projection(page)
    time.sleep(0.3)
    page.keyboard.press("Escape")
    chip.click()
    # Lot K, suite (K8): the same widths with no pane hidden, so no chip pushes « Fenêtre ▾ »
    # to the left: its panel, anchored under it, stays whole in the window.
    for projection_on in (True, False):
        if not projection_on:
            _toggle_projection(page)
        mode = "mode projection" if projection_on else "mode normal"
        for width, height in ((840, 433), (853, 433), (911, 512)):
            page.set_viewport_size({"width": width, "height": height})
            time.sleep(0.3)
            chips = page.locator("#pane-chips .pane-chip").count()
            outside = _window_panel_outside(page)
            r.check(
                not chips and not outside,
                f"{width} × {height} (zoom 150 %) en {mode}, aucun volet masqué : panneau "
                "« Fenêtre » entier dans la fenêtre",
                outside or f"{chips} puce(s) de volet masqué",
            )
    _toggle_projection(page)
    time.sleep(0.3)
    page.set_viewport_size({"width": 1600, "height": 1000})
    time.sleep(0.3)
    r.reload_app()
    r.wait_idle()
    page.click("#reset-button")
    time.sleep(0.5)
    on, size, pressed = projection()
    r.check(
        on and size == "18px" and pressed == "true",
        "Mode projection gardé après rechargement puis Réinitialiser",
        f"{on} {size} {pressed}",
    )
    r.check(
        page.inner_text("#schema-outbound")
        == "Aucun tour affiché : rien n'a quitté le poste pendant un tour.",
        "après Réinitialiser : le bilan dit qu'aucun tour n'est affiché",
        page.inner_text("#schema-outbound"),
    )
    _toggle_projection(page)
    time.sleep(0.3)
    on, size, pressed = projection()
    r.check(
        not on and size == "14px" and pressed == "false",
        "second clic : retour à 14 px",
        f"{on} {size} {pressed}",
    )


# ---------- restes différés, story 6 (E032): the schema's bins, H5's wait, H1's block ----------

_SCHEMA_NODES_JS = """() => [...document.querySelectorAll('#schema .arch-node')].map((n) => {
  const bin = n.closest('.arch-group');
  return {
    id: n.dataset.component,
    zone: n.closest('.arch-zone-network') ? 'network'
      : n.closest('.arch-zone-local') ? 'local' : '',
    bin: [...(bin?.classList ?? [])].find((c) => c.startsWith('arch-group-'))?.slice(11) ?? '',
    network: n.classList.contains('is-network'),
    count: bin?.querySelector('.arch-group-title')?.textContent.split(' · ').at(-1) ?? '',
    members: bin?.querySelectorAll('.arch-node').length ?? 0,
  };
})"""
_BINS = {"tools": "tool", "mcp": "mcp", "file": "file", "skills": "skill"}


def _schema_bins(r: Run, what: str, wanted: set[tuple[str, str]]) -> None:
    """E032: each node of the schema in the bin of its kind and the zone of its hosting (a
    network node in the network zone only), each bin's count its nodes'; `wanted`: the
    (zone, bin) pairs this scenario must draw."""
    nodes = r.page.evaluate(_SCHEMA_NODES_JS)
    wrong = [
        n
        for n in nodes
        if n["zone"] != ("network" if n["network"] else "local")
        or n["bin"] != _BINS.get(n["id"].split(".")[0])
        or n["count"] != str(n["members"])
    ]
    drawn = {(n["zone"], n["bin"]) for n in nodes}
    r.check(
        bool(nodes) and not wrong and wanted <= drawn,
        f"E032 ({what}) : chaque nœud dans le bac de son type et la zone de son hébergement",
        f"mal rangés {wrong[:4]} · bacs {sorted(drawn)}",
    )


# Lot 2 (2026-10-04): whether the schema drew the moving path past the boundary
# (`.diagram-path-core.is-flow`) at any moment, recorded by a mutation observer.
_FLOW_RECORDER_JS = """() => {
  const state = { flow: false };
  const note = () => {
    if (document.querySelector('#schema .diagram-wires .diagram-path-core.is-flow')) {
      state.flow = true;
    }
  };
  state.observer = new MutationObserver(note);
  state.observer.observe(document.getElementById('schema'), { subtree: true, childList: true });
  window.__e2eFlow = state;
}"""


def _schema_h5_pending(r: Run) -> None:
    """E032: H5 waits for the user: H5 lit, the path stopped before the boundary on ✋."""
    page = r.page
    hook = page.locator('#schema .arch-hook[data-component="hooks.h5"]')
    stop = page.locator("#schema .diagram-wires .diagram-marker.is-stop")
    ok, _ = r.poll(
        lambda: stop.count() == 1 and "is-active" in (hook.get_attribute("class") or ""), 5
    )
    paths = page.locator("#schema .diagram-wires .diagram-path").count()
    marker = stop.text_content() if stop.count() == 1 else ""
    r.check(
        ok and marker == "✋" and paths >= 1,
        "E032 : H5 attend : halo sur H5, chemin arrêté avant la frontière sur ✋",
        f"marqueur {marker!r} · chemins {paths} · H5 {hook.get_attribute('class')}",
    )
    # Lot 2 (2026-10-04): the shared halo and wires as the page computes them.
    looks = page.evaluate(
        """() => { const shadow = (n) => n ? getComputedStyle(n).boxShadow : null;
        const dashed = document.querySelector('#schema .diagram-wires .diagram-wire.is-dashed');
        const h5 = document.querySelector('#schema .arch-hook[data-component="hooks.h5"]');
        return { lit: shadow(h5),
          unlit: shadow(document.querySelector('#schema .arch-hook:not(.is-active)')),
          dash: dashed ? getComputedStyle(dashed).strokeDasharray : null }; }"""
    )
    r.check(
        looks["lit"] not in (None, "none")
        and looks["unlit"] == "none"
        and looks["dash"] not in (None, "none"),
        "lot 2 : halo calculé sur H5 allumé, aucun sur un hook éteint ; fil réseau en tirets",
        str(looks),
    )


def _schema_blocked_while_running(r: Run) -> None:
    """E032: H1 blocked the tool: while the turn goes on, H1 lit and the path stopped at the
    strip on ✖."""
    page = r.page
    hook = page.locator('#schema .arch-hook[data-component="hooks.h1"]')
    block = page.locator("#schema .diagram-wires .diagram-marker.is-block")
    ok, _ = r.poll(
        lambda: block.count() == 1 and "is-active" in (hook.get_attribute("class") or ""), 20
    )
    marker = block.text_content() if block.count() == 1 else ""
    r.check(
        ok and marker == "✖",
        "E032 : H1 a bloqué, le tour continue : halo sur H1, chemin arrêté à la bande sur ✖",
        f"marqueur {marker!r} · H1 {hook.get_attribute('class')}",
    )


def _hook_strip_state(r: Run, hook_id: str, cls: str, said: str) -> None:
    """E032: a hook of the strip « Points d'accroche » marked off or blocked, and saying so."""
    node = r.page.locator(f'#schema .arch-hook[data-component="hooks.{hook_id}"]')
    ok, _ = r.poll(
        lambda: node.count() == 1 and cls in (node.get_attribute("class") or "").split(), 5
    )
    text = node.inner_text() if node.count() == 1 else ""
    r.check(
        ok and said in text,
        f"E032 : bande des hooks, {hook_id.upper()} « {said.strip('· ')} » ({cls})",
        f"{node.get_attribute('class') if node.count() else None} · {text!r}",
    )


def _h5_rendering(r: Run, card: Any) -> None:
    """Finition V1 (#16): the part of story 8c's rendering left unchecked by `h5`. While the
    validation waits: the tool by its label (« Jours fériés », never `public_holidays`); the
    card kept from one rendering to the next (the bubble's seconds tick meanwhile); its trace
    in Orchestration, read only (no button), the tool by its label and its name; the chip
    « + Vue humain » linked (●) when that pane is hidden."""
    page = r.page
    text = card.inner_text()
    r.check(
        "Outil : Jours fériés · Destination : " in text and "public_holidays" not in text,
        "#16 : la carte nomme l'outil par son libellé (« Jours fériés »)",
        text[:160],
    )
    card.evaluate("n => { n.dataset.e2eKept = '1'; }")
    ticking = page.locator("#chat .working-indicator").last
    before = ticking.inner_text() if ticking.count() else ""
    ticked, _ = r.poll(lambda: ticking.count() == 1 and ticking.inner_text() != before, 5)
    kept = page.locator('#chat .approval-card[data-e2e-kept="1"]').count() == 1
    r.check(
        ticked and kept,
        "#16 : la carte de validation est gardée d'un rendu à l'autre",
        f"rendu {ticked} ({before!r} → {ticking.inner_text() if ticking.count() else None!r})"
        f" · gardée {kept}",
    )
    line = page.locator("#orch-scroll .turn-step-line", has_text="Validation humaine").last
    line.click()
    body = line.locator("xpath=following-sibling::div[contains(@class,'turn-step-body')]")
    try:
        expect(body).to_contain_text("En attente de votre réponse dans la Vue humain", timeout=5000)
        trace = body.inner_text()
        r.check(
            body.get_by_role("button").count() == 0 and "Jours fériés (public_holidays)" in trace,
            "#16 : Orchestration montre la validation sans bouton, l'outil par son libellé et "
            "son nom",
            trace[:200],
        )
    finally:
        line.click()
        follow = page.locator("#follow-live")
        if follow.is_visible():
            follow.click()  # back to the live view
    page.locator('[data-pane="human"] .pane-hide').click()
    try:
        chip = page.locator("#pane-chips .pane-chip", has_text="Vue humain")
        expect(chip).to_be_visible(timeout=5000)
        r.check(
            "is-linked" in (chip.get_attribute("class") or "").split()
            and chip.locator(".pane-chip-dot").count() == 1
            and (chip.get_attribute("title") or "").startswith(
                "Une validation humaine attend votre réponse"
            ),
            "#16 : volet masqué pendant l'attente, la puce « + Vue humain » est liée (●)",
            f"{chip.get_attribute('class')} · {chip.get_attribute('title')}",
        )
        chip.click()
    finally:
        if page.locator('[data-pane="human"]').evaluate("p => p.offsetParent === null"):
            page.locator("#pane-chips .pane-chip", has_text="Vue humain").click()
    expect(card).to_be_visible(timeout=5000)


def _focus_back_on_the_card(r: Run) -> None:
    """Finition V1 (#16): once its buttons are gone, the focus goes back to the card."""
    focused, _ = r.poll(
        lambda: (
            re.fullmatch(
                r"approval:[^:]+",
                r.page.evaluate("() => document.activeElement?.dataset?.focusKey || ''"),
            )
            is not None
        ),
        5,
    )
    r.check(
        focused,
        "#16 : le focus revient à la carte une fois ses boutons retirés",
        r.page.evaluate("() => document.activeElement?.outerHTML?.slice(0, 120) || ''"),
    )


def _h1_block_cleared(r: Run) -> None:
    """Finition V1 (#16): after « Vider la conversation », the strip no longer says H1
    blocked (the red line of a hidden turn), which it said just before."""
    node = r.page.locator('#schema .arch-hook[data-component="hooks.h1"]')
    r.check(
        node.count() == 1 and "is-blocked" in (node.get_attribute("class") or ""),
        "#16 : H1 dit « ✖ a bloqué » avant « Vider la conversation »",
        (node.get_attribute("class") or "") if node.count() else "absent",
    )
    seq = r.ev.mark()
    r.page.click("#clear-conversation")
    r.ev.wait("conversation_cleared", seq, timeout=10)
    gone, _ = r.poll(
        lambda: node.count() == 1 and "is-blocked" not in (node.get_attribute("class") or ""), 5
    )
    r.check(
        gone and "✖" not in node.inner_text(),
        "#16 : après « Vider la conversation », H1 ne dit plus « ✖ a bloqué »",
        f"{node.get_attribute('class')} · {node.inner_text()!r}",
    )


def s_h5(r: Run) -> None:
    r.launch("network_tools")
    r.set_brick("Hooks", True)
    r.set_option("Hooks", "Validation humaine", True)
    _schema_bins(r, "h5", {("local", "tool"), ("network", "tool")})
    asked = r.send("Quels sont les jours fériés en France cette année ?", expect_approval=True)
    r.check(
        asked["payload"]["tool"] == "public_holidays", "H5 suspend le tour avant l'outil réseau"
    )
    _schema_h5_pending(r)
    card = r.page.locator("#chat .approval-card").last
    expect(card).to_be_visible(timeout=10_000)
    r.check(
        "calendrier.api.gouv.fr" in card.inner_text(),
        "la carte montre la destination exacte",
        card.inner_text()[:200],
    )
    # Story 23: the preview keeps method, address and body; its headers are set when sending.
    preview = card.locator(".outbound-payload")
    preview.locator("summary").click()
    text = preview.inner_text()
    expected = ["Données sortantes", "Requête", "GET https://calendrier.api.gouv.fr/", "Corps"]
    expected.append("Posés par le client HTTP à l'envoi (User-Agent, Accept…)")
    missing = [e for e in expected if e not in text]
    r.check(
        not missing and not preview.locator(".outbound-headers").count(),
        "aperçu H5 : méthode, adresse et corps, note sur les en-têtes posés à l'envoi",
        f"manque {missing}" if missing else "",
    )
    preview.locator("summary").click()  # folded again, as the card opens
    _awaiting_indicator(r)
    _h5_rendering(r, card)
    r.shot("09-h5-validation-humaine")
    seq = r.ev.mark()
    posts = _approval_posts(r)
    try:
        # E030: two clicks on the same node, at once: the second must send nothing (the
        # button is not disabled yet; only the card's `answering` guard stops it).
        card.get_by_role("button", name="Refuser", exact=True).evaluate(
            "b => { b.click(); b.click(); }"
        )
        resolved = r.ev.wait("approval_resolved", seq, timeout=10)
        ended = r.ev.wait("turn_ended", seq)
        r.page.evaluate("() => 0")  # a round trip: the page's queued `request` events arrive
    finally:
        r.page.remove_listener("request", posts.listener)
    r.check(
        len(posts) == 1,
        "E030 : deux clics sur « Refuser » n'envoient qu'une réponse",
        f"{len(posts)} requête(s) POST /api/intentions/approval",
    )
    r.check(resolved["payload"]["decision"] == "refused", "« Refuser » : décision refused")
    _card_decision(r, "Décision : Refusé")
    r.check(not r.ev.since(seq, "outbound_request"), "refusé : rien ne sort du poste")
    r.check(
        ended["payload"]["status"] == "completed",
        "le tour se termine après le refus",
        ended["payload"]["status"],
    )
    asked = r.send("Quels sont les jours fériés en France cette année ?", expect_approval=True)
    seq = r.ev.mark()
    r.page.evaluate(_FLOW_RECORDER_JS)
    r.page.locator("#chat .approval-card").last.get_by_role(
        "button", name="Autoriser", exact=True
    ).click()
    r.ev.wait("approval_resolved", seq, timeout=10)
    r.ev.wait("turn_ended", seq)
    flow = r.page.evaluate(
        "() => { window.__e2eFlow.observer.disconnect(); return window.__e2eFlow.flow; }"
    )
    _focus_back_on_the_card(r)
    r.check(bool(r.ev.since(seq, "outbound_request")), "« Autoriser » : la requête part")
    r.check(
        flow,
        "lot 2 : l'outil réseau autorisé : chemin animé (is-flow) au-delà de la frontière",
    )
    results = [e["payload"] for e in r.ev.since(seq, "tool_ended")]
    r.check(
        bool(results) and results[-1]["status"] == "error",
        "autorisé : l'échec réseau est expliqué",
        (results[-1].get("error_text") or "")[:200] if results else "",
    )
    # A reload while the turn waits: the card comes back (AD-1); « Arrêter » cancels it.
    asked = r.send("Quels sont les jours fériés en France cette année ?", expect_approval=True)
    _buttons_off_outside_awaiting(r)
    r.page.reload()
    card = r.page.locator("#chat .approval-card").last
    ok, took = r.poll(
        lambda: (
            card.count() == 1
            and card.get_by_role("button", name="Autoriser", exact=True).is_enabled()
        )
    )
    r.check(
        ok,
        "après rechargement : la validation en attente réapparaît, active",
        f"au bout de {took:.1f} s",
    )
    seq = r.ev.mark()
    r.page.click("#composer-stop")
    resolved = r.ev.wait("approval_resolved", seq, timeout=10)
    ended = r.ev.wait("turn_ended", seq)
    r.check(
        resolved["payload"]["decision"] == "cancelled"
        and ended["payload"]["status"] == "cancelled",
        "« Arrêter » pendant la validation : décision cancelled, tour annulé",
        f"{resolved['payload']['decision']} / {ended['payload']['status']}",
    )
    r.check(not r.ev.since(seq, "outbound_request"), "annulé : rien ne sort du poste")
    _card_decision(r, "Décision : Annulé : tour arrêté")
    _approval_refused_409(r)
    # « Autoriser et ne plus demander » turns H5 off.
    asked = r.send("Quels sont les jours fériés en France cette année ?", expect_approval=True)
    seq = r.ev.mark()
    r.page.locator("#chat .approval-card").last.get_by_role(
        "button", name="Autoriser et ne plus demander"
    ).click()
    resolved = r.ev.wait("approval_resolved", seq, timeout=10)
    r.ev.wait("turn_ended", seq)
    r.check(resolved["payload"]["hook_disabled"], "« ne plus demander » désactive H5")
    h5 = [o for o in r.bricks()["hooks"]["options"] if o["id"] == "h5"]
    r.check(bool(h5) and not h5[0]["enabled"], "H5 apparaît désactivé dans la carte Hooks")
    _hook_strip_state(r, "h5", "is-off", f"· {_ui_catalogue('fr')['main.schema.hook_off']}")
    _h5_cleared(r)


class _Requests(list):
    """The requests a page sent to one intention, while `listener` is attached."""

    listener: Callable[[Any], None]


def _approval_posts(r: Run) -> _Requests:
    posts = _Requests()

    def listener(request) -> None:  # noqa: ANN001
        if request.method == "POST" and request.url.endswith("/api/intentions/approval"):
            posts.append(request)

    posts.listener = listener
    r.page.on("request", listener)
    return posts


def _card_decision(r: Run, decision: str) -> None:
    """E028: once answered, the last H5 card of the Vue humain says its decision."""
    card = r.page.locator("#chat .approval-card").last
    ok, _ = r.poll(lambda: card.count() == 1 and decision in card.inner_text(), 5)
    r.check(
        ok,
        f"E028 : la carte répondue affiche « {decision} », sans bouton",
        card.inner_text()[:200] if card.count() else "aucune carte",
    )
    r.check(card.locator("button").count() == 0, f"E028 : « {decision} » : boutons retirés")


def _awaiting_indicator(r: Run) -> None:
    """E028 (story 5 of the deferred leftovers): while H5 waits, the turn's indicator says
    « En attente de validation », in the Vue humain and in Orchestration's header."""
    chat = r.page.locator("#chat .bubble-model").last.locator(".working-indicator")
    orch = r.page.locator("#orch-working-label")
    ok, _ = r.poll(
        lambda: (
            chat.count() == 1
            and "En attente de validation" in chat.inner_text()
            and "En attente de validation" in orch.inner_text()
        ),
        5,
    )
    r.check(
        ok,
        "E028 : indicateur « En attente de validation » (Vue humain et Orchestration)",
        f"{chat.inner_text() if chat.count() else 'aucun indicateur'} · {orch.inner_text()}",
    )


_SESSION_NOT_AWAITING = "turn"


def _buttons_off_outside_awaiting(r: Run) -> None:
    """E028: the card's three buttons only act in `awaiting_human`. The real session never
    shows a pending validation in another state for long: `/api/state` is rewritten for one
    reload (`state: turn`, the journal's older `session_state` are not replayed), then the
    page is reloaded as it is."""

    rewritten: list[str] = []

    def rewrite(route) -> None:  # noqa: ANN001
        response = route.fetch()
        body = response.json()
        if isinstance(body.get("session_state"), dict):
            rewritten.append(body["session_state"].get("state"))
            body["session_state"]["state"] = _SESSION_NOT_AWAITING
        route.fulfill(response=response, json=body)

    r.page.route("**/api/state", rewrite)
    try:
        r.reload_app()
        card = r.page.locator("#chat .approval-card").last
        names = ["Autoriser", "Refuser", "Autoriser et ne plus demander"]
        buttons = [card.get_by_role("button", name=name, exact=True) for name in names]
        ok, _ = r.poll(
            lambda: card.count() == 1 and all(b.count() == 1 and b.is_disabled() for b in buttons),
            10,
        )
        pending = card.count() == 1 and "Décision" not in card.inner_text()
        r.check(
            ok and pending and "awaiting_human" in rewritten,
            "E028 : hors `awaiting_human`, la carte en attente garde ses trois boutons inactifs",
            f"état réécrit {rewritten}, carte {'en attente' if pending else 'répondue ?'}, "
            + str(
                [(n, b.count() and b.is_disabled()) for n, b in zip(names, buttons, strict=True)]
            ),
        )
    finally:
        r.page.unroute("**/api/state", rewrite)


_REASONS_JS = """() => {
  window.__composerReasons = [];
  const node = document.getElementById('composer-reason');
  const note = () => {
    if (!node.hidden && node.textContent) window.__composerReasons.push(node.textContent);
  };
  new MutationObserver(note).observe(node, {
    childList: true, characterData: true, subtree: true, attributes: true,
  });
}"""


def _approval_refused_409(r: Run) -> None:
    """E030: an answer the session refuses (409) is said under the composer. The validation is
    answered by the API first, then the page's own request goes through: a real 409."""
    asked = r.send("Quels sont les jours fériés en France cette année ?", expect_approval=True)
    approval_id = asked["payload"]["approval_id"]
    answers: list[int] = []

    def answer_first(route) -> None:  # noqa: ANN001
        try:
            answers.append(
                r.api(
                    "POST",
                    "/api/intentions/approval",
                    {"approval_id": approval_id, "approved": False, "disable_hook": False},
                ).status_code
            )
        finally:
            route.continue_()

    r.page.evaluate(_REASONS_JS)
    seq = r.ev.mark()
    r.page.route("**/api/intentions/approval", answer_first)
    try:
        with r.page.expect_response("**/api/intentions/approval") as info:
            r.page.locator("#chat .approval-card").last.get_by_role(
                "button", name="Refuser", exact=True
            ).click()
        status = info.value.status
        r.ev.wait("turn_ended", seq)
    finally:
        r.page.unroute("**/api/intentions/approval", answer_first)
    # `session.approval.answered`: the first answer counts (not « unknown »).
    answered = "Cette validation a déjà reçu une réponse : la première compte."
    reasons = "() => window.__composerReasons || []"
    ok, _ = r.poll(lambda: answered in r.page.evaluate(reasons), 5)
    r.check(
        answers == [200] and status == 409 and ok,
        "E030 : réponse refusée par la session (409) affichée sous le champ de saisie",
        f"API {answers}, page {status}, textes {sorted(set(r.page.evaluate(reasons)))}",
    )


def _h5_cleared(r: Run) -> None:
    """E030: after « Vider la conversation », no H5 card in the Vue humain, no trace in
    Orchestration or Contexte LLM, and the schema keeps no state of the hidden turns."""
    node = _schema_node(r, "Jours fériés")
    before = node.get_attribute("title") or ""
    seq = r.ev.mark()
    r.page.click("#clear-conversation")
    r.ev.wait("conversation_cleared", seq, timeout=10)
    ok, _ = r.poll(
        lambda: (
            r.page.locator("#chat .approval-card").count() == 0
            and r.page.locator("#orch-scroll .turn-step").count() == 0
            and r.page.locator("#ctx .ctx-call").count() == 0
        ),
        5,
    )
    r.check(
        ok,
        "E030 : après « Vider la conversation », aucune carte H5 (Vue humain), aucune étape "
        "(Orchestration), aucun appel (Contexte LLM)",
        f"cartes {r.page.locator('#chat .approval-card').count()}, "
        f"étapes {r.page.locator('#orch-scroll .turn-step').count()}, "
        f"appels {r.page.locator('#ctx .ctx-call').count()}",
    )
    gone, _ = r.poll(lambda: "Au tour" not in (node.get_attribute("title") or ""), 5)
    r.check(
        "Au tour" in before and gone,
        "E030 : le schéma ne dit plus l'état du tour masqué (Jours fériés sans « Au tour »)",
        f"avant : {before!r} · après : {node.get_attribute('title')!r}",
    )


def s_mcp_full(r: Run) -> None:
    seq = r.ev.mark()
    r.launch("mcp_full")
    ends = {e["payload"]["server"]: e["payload"] for e in r.ev.since(seq, "mcp_connect_ended")}
    r.check(
        ends.get("local", {}).get("status") == "ok",
        "serveur MCP local connecté",
        str(ends.get("local"))[:200],
    )
    dg = ends.get("datagouv", {})
    r.check(
        dg.get("status") == "error" and bool(dg.get("error_text")),
        "data.gouv.fr injoignable : échec expliqué",
        (dg.get("error_text") or str(dg))[:300],
    )
    gauge = r.page.locator("#gauge-figures").inner_text()
    seq = r.ev.mark()
    ended = r.send(_prompts("mcp_full")[0])
    tools = [e["payload"]["tool"] for e in r.ev.since(seq, "tool_started")]
    r.check("local__define_term" in tools, "outil MCP local appelé", str(tools))
    r.check(
        "MCP" in r.last_answer() and ended["payload"]["status"] == "completed",
        "réponse issue du glossaire MCP",
        r.last_answer()[:200],
    )
    # Chat mode: each tool definition of the body (native and MCP) shown as a tree, not as
    # the fragments of JSON the sentinels cut. Lot 1 of 2026-10-04: the root open, its sub-nodes
    # folded, so `function.name` is read from the DOM (`text_contents`), not from what shows.
    tools_row = (
        r.page.locator("#ctx .ctx-call")
        .first.locator(".ctx-section")
        .filter(has=r.page.locator(".ctx-section-label", has_text="Descriptions d'outils"))
    )
    names = (
        tools_row.first.locator(".json-tree .json-string").all_text_contents()
        if tools_row.count()
        else []
    )
    r.check(
        tools_row.count() >= 1
        and tools_row.first.locator(".json-tree .json-key", has_text='"parameters"').count() >= 1
        and '"local__define_term"' in names,
        "mode cloud : les descriptions d'outils, MCP compris, en arbres JSON",
        str(names[:6]),
    )
    # 2026-10-05: each tool folded says its name (native or MCP at a glance).
    folded = (
        tools_row.first.locator(".json-folded-name").all_inner_texts() if tools_row.count() else []
    )
    r.check(
        '"local__define_term"' in folded and '"get_datetime"' in folded,
        "mode cloud : chaque outil replié montre son nom (natif ou MCP sans déplier)",
        str(folded[:8]),
    )
    _ctx_focus_shot(r, "10b-contexte-outils-mcp-en-arbre")
    r.shot("10-mcp-documentation-complete")
    r.results.append((r.current, f"jauge avant envoi : {gauge}", True, ""))
    # Lot K: in full documentation too, each tool of the local server has its forced call.
    r.show_forced(True)
    r.open_options("MCP")
    button = r.page.get_by_role("button", name="Forcer l'appel : local__define_term")
    r.check(
        button.count() == 1 and "Forcer l'appel · local__define_term" in button.inner_text(),
        "documentation complète : bouton « Forcer l'appel · local__define_term »",
        button.inner_text() if button.count() else "absent",
    )
    r.show_forced(False)
    _mcp_server_switch(r)


def _intention_toggle(r: Run, path: str, brick: str, option: str, on: bool) -> Any:
    """Clicks an option's switch in its card; returns the body the page posted to `path`, or
    why none came (the check that reads it then fails with that reason)."""
    try:
        with r.page.expect_request(
            lambda q: q.method == "POST" and q.url.endswith(path), timeout=10_000
        ) as info:
            r.set_option(brick, option, on)
    except (TimeoutError, PlaywrightTimeout) as error:
        return f"pas de requête {path} suivie de bricks_changed : {error}".splitlines()[0]
    return info.value.post_data_json


def _mcp_server_switch(r: Run) -> None:
    """E016 (story 5 of the deferred leftovers): the server's switch in the MCP card posts to
    `/api/intentions/mcp_server`; switched back on, the server is contacted again and its new
    connection line, after the turn, is paired with its own end (« connecté », with the « MCP »
    badge); the server's node lists its tools in its tooltip. E030: « Vider la conversation »
    hides that line too."""
    label = "Glossaire WaveStack"
    off = _intention_toggle(r, "/api/intentions/mcp_server", "MCP", label, False)
    seq = r.ev.mark()
    on = _intention_toggle(r, "/api/intentions/mcp_server", "MCP", label, True)
    r.check(
        off == {"server": "local", "enabled": False} and on == {"server": "local", "enabled": True},
        "E016 : l'interrupteur du serveur poste `/api/intentions/mcp_server` (décoché, recoché)",
        f"{off} puis {on}",
    )
    r.ev.wait("mcp_connect_ended", seq, lambda p: p["server"] == "local", 45)
    lines = r.page.locator("#orch-scroll .turn-off .turn-step").filter(
        has=r.page.locator(".turn-step-title", has_text=label)
    )
    connecting = r.page.locator("#orch-scroll .turn-step-figure", has_text="connexion…")
    ok, _ = r.poll(
        lambda: (
            lines.count() == 1
            and "connecté" in lines.last.locator(".turn-step-figure").inner_text()
            and connecting.count() == 0
        ),
        5,
    )
    r.check(
        ok,
        "E016 : la nouvelle connexion, après le tour, reçoit sa propre fin (« connecté », "
        "aucune ligne « connexion… »)",
        f"{lines.count()} ligne(s) ; « connexion… » : {connecting.count()}",
    )
    if lines.count():
        lines.last.locator(".turn-step-line").click()
        badge = lines.last.locator(".turn-step-body .step-badge.is-mcp")
        shown, _ = r.poll(lambda: badge.count() == 1, 5)
        r.check(
            shown and badge.inner_text() == "MCP",
            "E016 : la ligne de connexion dépliée porte le badge « MCP »",
            f"{badge.count()} badge(s) « MCP »",
        )
    follow = r.page.locator("#follow-live")
    if follow.is_visible():
        follow.click()  # back to the live view the click on the line froze
    node = r.page.locator(".arch-node-mcp").filter(has_text=label).first
    title = node.get_attribute("title") or ""
    r.check(
        "Outils : " in title and "define_term" in title and "list_terms" in title,
        "E016 : l'infobulle du nœud du serveur liste ses outils",
        title,
    )
    seq = r.ev.mark()
    r.page.click("#clear-conversation")
    r.ev.wait("conversation_cleared", seq, timeout=10)
    gone, _ = r.poll(lambda: r.page.locator("#orch-scroll .turn-step").count() == 0, 5)
    r.check(
        gone,
        "E030 : après « Vider la conversation », la connexion MCP d'après le tour est masquée",
        r.page.locator("#orch-scroll").inner_text()[:200],
    )


def s_mcp_lazy(r: Run) -> None:
    first, second = _prompts("mcp_lazy")
    r.launch("mcp_lazy")
    guide = r.page.locator("#scenario-info-popover").text_content()
    r.check(
        not r.bricks()["rag"]["wanted"] and "le RAG, laissé éteint" in guide,
        "lazy loading : RAG non voulu (story 27), la consigne le dit",
        guide[:200],
    )
    # E017 (story 5 of the deferred leftovers): the « Lazy loading » switch of the MCP card.
    off = _intention_toggle(r, "/api/intentions/mcp_mode", "MCP", "Lazy loading", False)
    mode_off = r.bricks()["mcp"].get("mode")
    on = _intention_toggle(r, "/api/intentions/mcp_mode", "MCP", "Lazy loading", True)
    mode_on = r.bricks()["mcp"].get("mode")
    r.check(
        off == {"lazy": False}
        and on == {"lazy": True}
        and mode_off != "lazy"
        and mode_on == "lazy",
        "E017 : l'interrupteur « Lazy loading » poste `/api/intentions/mcp_mode` (décoché, "
        "recoché)",
        f"{off} → {mode_off} ; {on} → {mode_on}",
    )
    body_tools = None
    seq = r.ev.mark()
    ended = r.send(first)
    calls = r.fake_calls()
    body_tools = (
        [t["function"]["name"] for t in calls[-3].get("tools") or []] if len(calls) >= 3 else []
    )
    tools = [e["payload"]["tool"] for e in r.ev.since(seq, "tool_started")]
    r.check(
        tools[:2] == ["load_tool_doc", "local__define_term"],
        "lazy : documentation chargée puis outil appelé",
        str(tools),
    )
    r.check(
        "local__define_term" not in body_tools,
        "lazy : l'outil n'est pas décrit avant le chargement",
        str(body_tools),
    )
    r.check(ended["payload"]["status"] == "completed", "tour lazy terminé")
    # E017: the harness's step that loads the documentation, unfolded, carries the MCP badge.
    title = "Chargement de la documentation"
    if not _step(r, title).locator(".turn-step-body").count():
        _step(r, title).locator(".turn-step-line").click()
    badge = _step(r, title).locator(".turn-step-body .step-badge.is-mcp")
    shown, _ = r.poll(lambda: badge.count() == 1, 5)
    r.check(
        shown and badge.inner_text() == "MCP",
        "E017 : l'étape « Chargement de la documentation » porte le badge « MCP »",
        f"{badge.count()} badge(s) « MCP »" if _step(r, title).count() else "étape absente",
    )
    follow = r.page.locator("#follow-live")
    if follow.is_visible():
        follow.click()
    seq = r.ev.mark()
    ended = r.send(second)
    r.check(
        ended["payload"]["status"] == "completed",
        "qualité de l'air sans data.gouv.fr : réponse sans outil",
        r.last_answer()[:160],
    )
    # D16 (story 4 of the deferred leftovers, 2026-10-02): the documentation loaded at the
    # first prompt stays in the history, so the second turn rewrites no system message.
    # The E2E stack runs the fake OpenAI provider (chat mode, no prefix control): this check
    # holds trivially here; the local-mode proof is `tests/test_mcp_lazy.py`, and no prefill
    # check is possible without an in-process engine.
    rereads = [
        e["payload"]
        for e in r.ev.since(seq, "prefix_not_reused")
        if e["payload"].get("cause") == "system"
    ]
    r.check(
        not rereads,
        "D16 : aucune relecture `system` au tour qui suit load_tool_doc",
        str(rereads)[:200],
    )
    # Story 9: force an MCP documentation. D3 (2026-10-01): the switch unfolds the MCP list.
    r.show_forced(False)
    mcp_options = r.card("MCP").locator("details.brick-options")
    if mcp_options.get_attribute("open") is not None:
        mcp_options.locator("summary").click()
    r.show_forced(True)
    unfolded, _ = r.poll(lambda: mcp_options.get_attribute("open") is not None, 5)
    r.check(unfolded, "D3 : « Afficher les actions forcées » déplie la liste des serveurs MCP")
    r.open_options("MCP")
    armed = r.arm("Charger la documentation : Glossaire WaveStack")
    r.check(armed["payload"]["actions"][0]["kind"] == "tool_doc", "documentation MCP armée")
    seq = r.ev.mark()
    r.send("Bonjour")
    tools = [e["payload"] for e in r.ev.since(seq, "tool_started")]
    r.check(
        any(t["tool"] == "load_tool_doc" for t in tools),
        "l'action forcée charge la documentation au tour suivant",
        str(tools)[:200],
    )
    r.shot("11-mcp-lazy-force")
    # Lot K (2026-09-29): force the MCP tool's call itself, with its preset.
    armed = r.arm("Forcer l'appel : local__define_term", preset="MCP")
    action = armed["payload"]["actions"][0]
    r.check(
        (action["kind"], action["target"], action["args"])
        == ("tool", "local__define_term", {"term": "MCP"}),
        "« Forcer l'appel » d'un outil MCP armé avec son préréglage",
        str(action),
    )
    seq = r.ev.mark()
    r.send("Bonjour")
    started = [e for e in r.ev.since(seq, "tool_started")]
    forced = [e for e in started if e["payload"]["tool"] == "local__define_term"]
    r.check(
        bool(forced) and forced[0]["trigger"] == "user" and forced[0]["brick"] == "mcp",
        "l'appel MCP forcé part au tour suivant, déclenché par l'utilisateur",
        str([(e["payload"]["tool"], e.get("trigger")) for e in started])[:200],
    )
    # A tool without parameter: armed in one click, its own name as the target.
    armed = r.arm("Forcer l'appel : local__list_terms")
    action = armed["payload"]["actions"][0]
    r.check(
        (action["kind"], action["target"], action["args"]) == ("tool", "local__list_terms", {}),
        "« Forcer l'appel » d'un outil MCP sans paramètre armé en un clic",
        str(action),
    )
    r.page.locator("#armed-chips button").first.click()  # disarm
    r.show_forced(False)


def s_skills(r: Run) -> None:
    r.launch("skills")
    guide = r.page.locator("#scenario-info-popover").text_content()
    r.check(
        "« Déclencher le skill » sur « Compte rendu de réunion »" in guide
        and not r.bricks()["rag"]["wanted"],
        "consigne des skills : l'action forcée de secours ; RAG non voulu",
        guide[:200],
    )
    # E023 (story 5 of the deferred leftovers): the skill's switch, then its node « chargé ».
    label = "Compte rendu de réunion"
    off = _intention_toggle(r, "/api/intentions/skill", "Skills", label, False)
    on = _intention_toggle(r, "/api/intentions/skill", "Skills", label, True)
    r.check(
        off == {"skill": "meeting_minutes", "enabled": False}
        and on == {"skill": "meeting_minutes", "enabled": True},
        "E023 : l'interrupteur du skill poste `/api/intentions/skill` (décoché, recoché)",
        f"{off} puis {on}",
    )
    node = r.page.locator(".arch-node-skill").filter(has_text=label).first

    def loaded() -> bool:
        return "is-loaded" in (node.get_attribute("class") or "").split() and (
            "Chargé dans la conversation." in (node.get_attribute("title") or "")
        )

    r.check(
        node.count() == 1 and not loaded() and "Non chargé." in (node.get_attribute("title") or ""),
        "E023 : avant le tour, le skill est « Non chargé » dans le schéma",
        node.get_attribute("title") if node.count() else "nœud absent",
    )
    seq = r.ev.mark()
    ended = r.send(_prompts("skills")[0])
    tools = [e["payload"]["tool"] for e in r.ev.since(seq, "tool_started")]
    r.check("load_skill" in tools, "le modèle charge le skill", str(tools))
    r.check(ended["payload"]["status"] == "completed", "tour terminé")
    sent = json.dumps(r.fake_calls()[-1]["messages"], ensure_ascii=False)
    r.check("compte rendu de réunion structuré" in sent, "le contenu du skill rejoint le contexte")
    ok, _ = r.poll(loaded, 5)
    r.check(
        ok,
        "E023 : après le tour, le nœud du skill est marqué chargé (classe et infobulle)",
        f"{node.get_attribute('class')} · {node.get_attribute('title')}",
    )


def s_caveman(r: Run) -> None:
    r.launch("caveman")
    r.send("Explique en quelques phrases ce qu'est un harnais d'agent.")
    long_answer = r.last_answer()
    r.show_forced(True)
    r.open_options("Skills")
    armed = r.arm("Déclencher le skill : Caveman")
    r.check(armed["payload"]["actions"][0]["target"] == "caveman", "Caveman armé")
    expect(r.page.locator("#armed-chips")).to_be_visible(timeout=5000)
    r.check(True, "puce d'action armée au-dessus du champ")
    ended = r.replay()
    short_answer = r.last_answer()
    r.check(ended["payload"]["status"] == "completed", "rejeu avec Caveman terminé")
    r.check(
        len(short_answer) < len(long_answer) / 2,
        "réponse Caveman bien plus courte",
        f"{len(long_answer)} → {len(short_answer)} caractères",
    )
    r.page.locator("#chat .replay-badge").last.click()
    compare = r.page.locator("#ctx")
    r.check("Comparaison de tours" in compare.inner_text(), "le badge Rejeu ouvre la comparaison")
    r.check(
        "Sortie" in compare.inner_text() and "(-" in compare.inner_text().replace("−", "-"),
        "la comparaison montre moins de tokens en sortie",
        compare.locator(".turn-compare-figures").last.inner_text()[:200]
        if compare.locator(".turn-compare-figures").count()
        else "",
    )
    r.shot("13-caveman-comparer")
    compare.get_by_role("button", name="Fermer").click()
    r.show_forced(False)


def s_hooks(r: Run) -> None:
    r.launch("hooks")
    # « [lent] » (restes différés, story 6, E032): the answer after the block streams slowly,
    # while the schema shows the path stopped at the strip.
    r.wait_idle()
    seq = r.ev.mark()
    r.page.fill(
        "#composer-input", "Lis le fichier confidentiel/budget_projet.txt et résume-le. [lent]"
    )
    r.page.press("#composer-input", "Enter")
    r.wait_turn_started(seq, "l'envoi")
    _schema_blocked_while_running(r)
    ended = r.ev.wait("turn_ended", seq)
    decided = [e["payload"] for e in r.ev.since(seq, "hook_decided")]
    blocks = [d for d in decided if d["hook"] == "h1" and d["decision"] == "block"]
    r.check(
        bool(blocks),
        "H1 bloque la lecture du dossier confidentiel",
        str([(d["hook"], d["decision"]) for d in decided]),
    )
    r.check(any(d["hook"] == "h2" for d in decided), "H2 journalise")
    r.check(ended["payload"]["status"] == "completed", "le tour se termine")
    _turn_rendered_ended(r, ended["turn_id"])
    blocked = f"· ✖ {_ui_catalogue('fr')['main.schema.hook_blocked']}"
    _hook_strip_state(r, "h1", "is-blocked", blocked)
    row = _step(r, "Hook H1")
    links = (row.get_attribute("data-links") or "") if row.count() else ""
    r.check(
        "hooks.h1" in links.split(),
        "E032 : l'étape « Hook H1 » du blocage garde le composant de son enveloppe (hooks.h1)",
        links,
    )
    r.check(
        "budget" not in r.last_answer().lower() or "bloqu" in r.last_answer().lower(),
        "le contenu confidentiel n'atteint pas la réponse",
        r.last_answer()[:200],
    )
    r.shot("14-hooks-h1-bloque")
    # Forced read_file, « Fichier sensible » preset, then replay (story 9).
    r.show_forced(True)
    r.open_options("Outils")
    armed = r.arm("Forcer l'appel : Lecture de fichier", preset="Fichier sensible")
    args = armed["payload"]["actions"][0]["args"]
    r.check(
        args.get("path") == "confidentiel/budget_projet.txt",
        "préréglage « Fichier sensible »",
        str(args),
    )
    seq = r.ev.mark()
    r.replay()
    # H1 blocks before `tool_started`: the hook's decision carries the trigger.
    decisions = r.ev.since(seq, "hook_decided")
    r.check(
        any(e.get("trigger") == "user" for e in decisions),
        "l'appel forcé est attribué à l'utilisateur",
        str([e.get("trigger") for e in decisions]),
    )
    decided = [e["payload"] for e in r.ev.since(seq, "hook_decided")]
    r.check(
        any(d["hook"] == "h1" and d["decision"] == "block" for d in decided),
        "H1 bloque aussi l'appel forcé",
    )
    r.check(
        "Forcé par l'utilisateur" in r.page.locator("#orch-scroll").inner_text(),
        "Orchestration affiche « Forcé par l'utilisateur »",
    )
    audit = r.api("GET", "/api/audit")
    text = audit.json().get("text", "") if audit.status_code == 200 else ""
    r.check(
        "bloqué par H1" in text,
        "journal d'audit H2 écrit (blocage H1 compris)",
        text.strip().splitlines()[-1][:200] if text.strip() else str(audit.status_code),
    )
    r.show_forced(False)
    _h1_block_cleared(r)


def s_subagent(r: Run) -> None:
    """Story 19: delegation by the model, then forced; the switch of Contexte LLM, the
    delegation line and its child lines in Orchestration, the second robot of the schema."""
    page = r.page
    r.launch("subagent")
    r.check(
        not r.bricks()["rag"]["wanted"]
        and "sans le raisonnement ni le RAG"
        in page.locator("#scenario-info-popover").text_content(),
        "sous-agent : RAG non voulu, la consigne le dit (story 27, D5)",
    )
    # The scenario's own prompt; « [lent] » slows the fake model down to see the robot work.
    prompt = _prompts("subagent")[0] + " [lent]"
    before = len(r.fake_calls())
    r.wait_idle()
    seq = r.ev.mark()
    page.fill("#composer-input", prompt)
    page.press("#composer-input", "Enter")
    # The sub-agent's robot works while its calls run (the fake model streams slowly).
    sub_robot = page.locator('#schema .robot[data-component="core.model_sub"]')
    r.check(sub_robot.count() == 1, "schéma : un second robot « Sous-agent »")
    active, _ = r.poll(lambda: "is-active" in (sub_robot.get_attribute("class") or ""), 30)
    r.check(active, "le robot du sous-agent s'anime pendant ses appels")
    gauge_during = page.locator("#gauge-figures").inner_text() if active else ""
    r.check(
        sub_robot.locator("xpath=ancestor::*[contains(@class,'arch-zone-network')]").count() == 1,
        "modèle cloud : le robot du sous-agent est dans la zone Réseau",
    )
    ended = r.ev.wait("turn_ended", seq)
    r.check(ended["payload"]["status"] == "completed", "tour terminé", ended["payload"]["status"])
    started = [e for e in r.ev.since(seq, "tool_started") if e["context_id"] == "main"]
    r.check(
        [e["payload"]["tool"] for e in started] == ["delegate"]
        and started[0]["trigger"] == "model",
        "le modèle délègue (delegate, déclenché par le modèle)",
        str([(e["payload"]["tool"], e["trigger"]) for e in started]),
    )
    # D5 (2026-10-01): the delegation is a consulted tool, named under the answer.
    tools_line = page.locator("#chat .bubble-model").last.locator(".answer-tools")
    named, _ = r.poll(
        lambda: tools_line.count() == 1 and "Délégation au sous-agent" in tools_line.inner_text(),
        5,
    )
    r.check(named, "D5 : la délégation est nommée sous la réponse")
    done = r.ev.since(seq, "subagent_ended")
    figures = done[0]["payload"] if done else {}
    r.check(
        figures.get("status") == "completed" and figures.get("saved_tokens", 0) > 0,
        "sous-agent terminé, économie de tokens positive",
        str({k: figures.get(k) for k in ("context_tokens", "result_tokens", "saved_tokens")}),
    )
    bodies = r.fake_calls()[before:]
    sub_bodies = [b for b in bodies if "sous-agent de WaveStack" in json.dumps(b["messages"][0])]
    r.check(len(sub_bodies) == 2, "deux appels du sous-agent au modèle", str(len(sub_bodies)))
    guide = "## 8. Le sous-agent"
    r.check(
        any(guide in json.dumps(b["messages"], ensure_ascii=False) for b in sub_bodies),
        "le guide est lu dans le contexte du sous-agent",
    )
    main_last = json.dumps(bodies[-1]["messages"], ensure_ascii=False)
    r.check(guide not in main_last, "le guide n'entre pas dans le contexte principal")
    sub_used = {
        e["payload"]["used"]
        for e in r.ev.since(seq)
        if e["kind"] in ("context_rendered", "context_reconciled")
        and e["context_id"].startswith("sub")
    }
    shown = [page.evaluate("n => new Intl.NumberFormat('fr-FR').format(n)", n) for n in sub_used]
    r.check(
        bool(gauge_during) and not any(n in gauge_during for n in shown),
        "la jauge reste sur le contexte principal pendant le sous-agent",
        f"jauge « {gauge_during} » · sous-agent {sorted(sub_used)}",
    )

    # Orchestration: the delegation line, its trigger, its figures and its child lines.
    rail = page.locator("#orch-scroll")
    line = rail.locator(".turn-step-line", has_text="Délégation au sous-agent").last
    r.check(line.count() == 1, "Orchestration : ligne « Délégation au sous-agent »")
    r.check("économisés" in line.inner_text(), "la ligne montre l'économie", line.inner_text())
    r.check("Déclenché par le modèle" in line.inner_text(), "badge « Déclenché par le modèle »")
    children = rail.locator(".turn-step.is-sub")
    r.check(children.count() >= 3, "lignes filles du sous-agent", str(children.count()))
    line.click()
    body = line.locator("xpath=following-sibling::div[contains(@class,'turn-step-body')]")
    expect(body).to_contain_text("Économie pour le contexte principal", timeout=5000)
    r.check(True, "l'étape dépliée donne tâche, tokens restés, réinjectés et économisés")

    # Contexte LLM (story 22): tabs « Agent principal » / « Sous-agent subN », the main one
    # selected after the turn; each shows its context with its total.
    ctx = page.locator("#ctx")
    switch = ctx.get_by_role("tablist", name="Contexte affiché")
    expect(switch).to_be_visible(timeout=5000)
    main_tab = switch.get_by_role("tab", name="Agent principal", exact=True)
    sub_tab = switch.get_by_role("tab", name=re.compile(r"^Sous-agent sub\d+$"))
    r.check(
        main_tab.get_attribute("aria-selected") == "true"
        and sub_tab.count() == 1
        and sub_tab.get_attribute("aria-selected") == "false",
        "Contexte LLM : onglets « Agent principal » (sélectionné) et « Sous-agent subN »",
        " | ".join(switch.get_by_role("tab").all_inner_texts()),
    )
    sub_tab.click()
    text = ctx.inner_text()
    r.check(
        sub_tab.get_attribute("aria-selected") == "true"
        and "sous-agent de WaveStack" in text
        and "Résultats d'outils" in text
        and "Sous-agent sub" in text,
        "onglet du sous-agent : son prompt, la tâche, le résultat d'outil, son total",
    )
    # Story 32: the sub-agent's calls numbered the same way; its second one folds what its
    # first one read.
    calls = _ctx_calls(r)
    n = len(calls)
    r.check(
        n >= 1
        and [c["title"] for c in calls] == [f"Appel {i} sur {n}" for i in range(1, n + 1)]
        and all(c["id"].split(".")[1].startswith("sub") for c in calls)
        and calls[0]["seen"] is None
        and all(c["seen"] is not None and not c["seen"]["open"] for c in calls[1:]),
        "onglet du sous-agent : ses appels numérotés, le déjà-lu replié à partir du 2e",
        " | ".join(f"{c['title']} ({'déjà lu' if c['seen'] else '—'})" for c in calls),
    )
    main_tab.click()
    text = ctx.inner_text()
    r.check(
        main_tab.get_attribute("aria-selected") == "true"
        and "Résultat du sous-agent" in text
        and guide not in text,
        "onglet « Agent principal » : le seul résultat, en « Résultat du sous-agent »",
    )
    between = ctx.locator(".ctx-between").get_by_role(
        "button", name=re.compile(r"^Voir le contexte du sous-agent sub\d+$")
    )
    r.check(
        between.count() == 1
        and "délégation au sous-agent" in ctx.locator(".ctx-between").first.inner_text(),
        "« Agent principal » : entre les appels, la délégation et l'onglet du sous-agent",
        " | ".join(ctx.locator(".ctx-between").all_inner_texts()),
    )
    if between.count() == 1:
        between.click()
        r.check(
            sub_tab.get_attribute("aria-selected") == "true",
            "la ligne entre les appels ouvre l'onglet du sous-agent",
        )
        main_tab.click()
    body.get_by_role("button", name="Voir le contexte du sous-agent").click()
    r.check(
        sub_tab.get_attribute("aria-selected") == "true"
        and "sous-agent de WaveStack" in ctx.inner_text(),
        "« Voir le contexte du sous-agent » sélectionne son onglet",
    )
    r.shot("19-sous-agent-delegation")

    # Story 22: « Annuler » and a second click on the button close the form.
    r.show_forced(True)
    delegate = page.get_by_role("button", name="Déléguer au sous-agent")
    form = page.locator(".force-form")
    page.set_viewport_size({"width": 1280, "height": 650})
    # Lot K (A8), E125 (restes différés, story 6): the button says the form is open at once,
    # read on the node clicked in the same task as the click, before the next frame rebuilds
    # the panel (whose new button says it anyway); then on the rebuilt button.
    expect(delegate).to_be_enabled(timeout=5000)
    at_click = delegate.evaluate("b => { b.click(); return b.getAttribute('aria-expanded'); }")
    expect(form).to_be_visible(timeout=5000)
    r.check(
        at_click == "true" and delegate.get_attribute("aria-expanded") == "true",
        "1280 × 650 : formulaire « Déléguer au sous-agent » ouvert, aria-expanded=true lu "
        "juste après le clic (avant la reconstruction du panneau), puis après",
        f"au clic : {at_click} · après : {delegate.get_attribute('aria-expanded')}",
    )
    page.set_viewport_size({"width": 1600, "height": 1000})
    form.get_by_role("button", name="Annuler").click()
    closed, took = r.poll(lambda: form.count() == 0, 2)
    focused = page.evaluate("() => document.activeElement?.dataset.focusKey || ''")
    r.check(
        closed
        and delegate.get_attribute("aria-expanded") == "false"
        and focused.startswith("force:subagent:"),
        "« Annuler » ferme le formulaire « Déléguer au sous-agent », focus sur le bouton",
        f"{took:.2f} s · focus {focused}",
    )
    delegate.click()
    expect(form).to_be_visible(timeout=5000)
    delegate.click()
    closed, took = r.poll(lambda: form.count() == 0, 2)
    r.check(
        closed and delegate.get_attribute("aria-expanded") == "false",
        "re-clic sur « Déléguer au sous-agent » : le formulaire se ferme",
        f"{took:.2f} s",
    )

    # Forced delegation: the card's button, its preset, the chip (disarmed by keyboard too).
    armed = r.arm("Déléguer au sous-agent", preset="Résumer le guide du harnais")
    action = armed["payload"]["actions"][0]
    r.check(
        action["kind"] == "delegate" and "guide_harnais.md" in action["args"]["task"],
        "« Déléguer au sous-agent » arme la délégation avec le préréglage",
        str(action),
    )
    chip = page.locator("#armed-chips .armed-chip", has_text="Armé : Délégation")
    expect(chip).to_be_visible(timeout=5000)
    seq = r.ev.mark()
    chip.focus()
    page.keyboard.press("Enter")
    r.ev.wait("armed_actions_changed", seq, lambda p: not p["actions"], timeout=10)
    r.check(True, "la puce se désarme au clavier")
    r.arm("Déléguer au sous-agent", preset="Résumer le guide du harnais")
    seq = r.ev.mark()
    ended = r.send("Bonjour")
    forced = [e for e in r.ev.since(seq, "tool_started") if e["context_id"] == "main"]
    r.check(
        bool(forced)
        and forced[0]["payload"]["tool"] == "delegate"
        and forced[0]["trigger"] == "user",
        "délégation forcée consommée par le tour (déclenchée par l'utilisateur)",
    )
    r.check(ended["payload"]["status"] == "completed", "tour forcé terminé")
    ok, _ = r.poll(
        lambda: main_tab.count() == 1 and main_tab.get_attribute("aria-selected") == "true", 5
    )
    r.check(ok, "au tour suivant, l'onglet « Agent principal » est de nouveau sélectionné")
    delegation = rail.locator(".turn-step-line", has_text="Délégation au sous-agent").last
    r.check(
        "Forcé par l'utilisateur" in delegation.inner_text(), "badge « Forcé par l'utilisateur »"
    )
    r.show_forced(False)

    # H5 inside the sub-agent (independent review): the session waits, the Vue humain card
    # is answerable, a refusal goes back to the sub-agent and the turn ends.
    r.set_option("Outils", "Lecture de page web", True)
    r.set_option("Hooks", "Validation humaine", True)
    enabled = {
        b: [o["id"] for o in r.bricks()[b]["options"] if o["enabled"]] for b in ("tools", "hooks")
    }
    r.check(
        "fetch_page" in enabled["tools"] and "h5" in enabled["hooks"],
        "« Lecture de page web » et H5 activés",
        str(enabled),
    )
    asked = r.send(
        "Délègue à ton sous-agent la lecture de la page web de Paris.", expect_approval=True
    )
    r.check(
        asked["context_id"].startswith("sub") and asked["payload"]["tool"] == "fetch_page",
        "H5 demande la validation dans le contexte du sous-agent",
        f"{asked['context_id']} · {asked['payload']['tool']}",
    )
    card = page.locator("#chat .approval-card").last
    refuse = card.get_by_role("button", name="Refuser", exact=True)
    ok, took = r.poll(lambda: card.count() == 1 and refuse.is_enabled(), 10)
    r.check(ok, "Vue humain : la carte de validation du sous-agent est active", f"{took:.1f} s")
    r.check(
        "awaiting_human" == (r.state()["session_state"] or {}).get("state"),
        "la session attend la validation",
    )
    seq = r.ev.mark()
    refuse.click()
    resolved = r.ev.wait("approval_resolved", seq, timeout=10)
    ended = r.ev.wait("turn_ended", seq)
    r.check(resolved["payload"]["decision"] == "refused", "« Refuser » dans le sous-agent")
    r.check(not r.ev.since(seq, "outbound_request"), "refusé : rien ne sort du poste")
    r.check(
        ended["payload"]["status"] == "completed",
        "le tour se termine après le refus",
        ended["payload"]["status"],
    )
    r.set_option("Hooks", "Validation humaine", False)


def s_data_flows(r: Run) -> None:
    """Story 27 (X1): everything is active at launch, nothing to turn on by hand: the MCP
    brick in lazy loading, the local server and data.gouv.fr."""
    seq = r.ev.mark()
    r.launch("data_flows")
    enabled, mode = _enabled_servers(r)
    r.check(
        r.bricks()["mcp"]["wanted"] and enabled == ["datagouv", "local"] and mode == "lazy",
        "lancement : brique MCP voulue, serveur local et data.gouv.fr, lazy loading",
        f"{enabled} · {mode}",
    )
    r.check(
        "Décochez puis recochez data.gouv.fr"
        in r.page.locator("#scenario-info-popover").text_content(),
        "consigne : tout est actif, décocher puis recocher data.gouv.fr",
    )
    _public_server_offline(r, "datagouv", "data.gouv.fr", seq)
    crossing = _crossing_besides_the_model(r)
    r.check(
        any("datagouv" in e["from"] + e["to"] for e in crossing),
        "le flux vers data.gouv.fr franchit la frontière du poste",
        str(crossing)[:300],
    )
    arch = r.state()["architecture_changed"]
    local = [e for e in arch["edges"] if "mcp.local" in e["from"] + e["to"]]
    r.check(
        bool(local) and all(not e.get("crosses_boundary") for e in local),
        "le serveur MCP local reste sur le poste",
        str(local)[:200],
    )
    _schema_bins(r, "data_flows", {("local", "mcp"), ("network", "mcp")})
    _datagouv_node_reveals_its_connection(r)
    _datagouv_connection_outbound(r, seq)
    r.shot("15-ou-vont-mes-donnees-schema")
    schema_fits(r, "data.gouv.fr")
    # The instructions' gesture: data.gouv.fr unchecked, then checked again.
    r.set_option("MCP", "data.gouv.fr", False)
    crossing = _crossing_besides_the_model(r)
    r.check(
        not crossing,
        "data.gouv.fr décoché : plus aucun flux ne franchit la frontière (hors modèle cloud)",
        str(crossing)[:300],
    )
    seq = r.ev.mark()
    r.set_option("MCP", "data.gouv.fr", True)
    r.ev.wait("mcp_connect_ended", seq, lambda p: p["server"] == "datagouv", 45)
    time.sleep(0.5)
    crossing = _crossing_besides_the_model(r)
    r.check(
        any("datagouv" in e["from"] + e["to"] for e in crossing),
        "data.gouv.fr recoché : son flux franchit de nouveau la frontière",
        str(crossing)[:300],
    )


def _crossing_besides_the_model(r: Run) -> list[dict[str, Any]]:
    """The schema's edges that cross the workstation's boundary, but the run's cloud model's."""
    arch = r.state()["architecture_changed"]
    return [
        e
        for e in arch["edges"]
        if e.get("crosses_boundary") and "core.model" not in e["from"] + e["to"]
    ]


def _datagouv_node_reveals_its_connection(r: Run) -> None:
    """Story 23: a click on the data.gouv.fr node, preparation folded and Orchestration
    hidden, unfolds its connection there and brings its block on screen."""
    page = r.page
    page.keyboard.press("Escape")
    if page.locator("#follow-live").is_visible():
        page.click("#follow-live")  # a view an earlier scenario froze: back to live first
    head = page.locator("#orch-scroll .harness-prep .turn-group-head")
    if head.get_attribute("aria-expanded") == "true":
        head.click()
    page.locator('[data-pane="orch"] .pane-hide').click()
    time.sleep(0.3)
    node = _schema_node(r, "data.gouv.fr")
    r.check(
        "Clic : ses données sortantes dans Orchestration" in (node.get_attribute("title") or ""),
        "nœud data.gouv.fr : l'infobulle dit où mène le clic",
    )
    node.click()
    time.sleep(0.5)
    _revealed(
        r,
        _outbound_step(r, "data.gouv.fr", ".harness-prep"),
        ["Données sortantes", "mcp.data.gouv.fr", "User-Agent: WaveStack/0.1"],
        "clic sur le nœud data.gouv.fr : Orchestration montrée, préparation et connexion "
        "dépliées, bloc ouvert et à l'écran",
    )
    r.check(
        page.locator("#follow-live").is_hidden(),
        "une connexion ne fige pas la vue (pas de « Suivre le direct »)",
    )
    page.keyboard.press("Escape")


def _datagouv_connection_outbound(r: Run, seq: int) -> None:
    """Story 23: the connection to data.gouv.fr, unfolded in the preparation, shows what it
    sent, headers included (story 5b's block, untested before: deferred-work item 43)."""
    page = r.page
    prep = page.locator("#orch-scroll .harness-prep")
    if prep.locator(".turn-group-head").get_attribute("aria-expanded") == "false":
        prep.locator(".turn-group-head").click()
    line = prep.locator(".turn-step").filter(
        has=page.locator(".turn-step-name", has_text="data.gouv.fr")
    )
    if not line.last.locator(".turn-step-body").count():
        line.last.locator(".turn-step-line").click()
    time.sleep(0.3)
    payload = line.last.locator(".outbound-payload")
    text = payload.inner_text() if payload.count() else ""
    expected = ["Données sortantes", "mcp.data.gouv.fr", "En-têtes", "User-Agent: WaveStack/0.1"]
    missing = [e for e in expected if e not in text]
    r.check(
        not missing,
        "connexion data.gouv.fr dépliée : données sortantes, en-têtes et User-Agent",
        f"manque {missing} dans « {text[:200]} »" if missing else "",
    )
    traced = [e["payload"] for e in r.ev.since(seq, "outbound_request")]
    names = [h["name"] for p in traced for h in p.get("headers", [])]
    r.check(
        bool(traced) and "User-Agent" in names,
        "connexion data.gouv.fr : en-têtes tracés dans outbound_request",
        str(names)[:200],
    )


def schema_fits(r: Run, node: str) -> None:
    """A2: the network zone of the schema, whole, at the two target widths."""
    for width, height in [(1600, 1000), (1366, 768)]:
        r.page.set_viewport_size({"width": width, "height": height})
        time.sleep(0.5)
        over = r.page.evaluate(
            "() => { const b = document.querySelector('.pane-body-schema');"
            " return b.scrollWidth - b.clientWidth; }"
        )
        r.check(
            over <= 2,
            f"{width}×{height} : la zone Réseau du schéma tient sans défilement (A2)",
            f"{over} px masqués à droite",
        )
        cut = r.page.evaluate(
            "(name) => { const b = document.querySelector('.pane-body-schema')"
            ".getBoundingClientRect();"
            " const n = [...document.querySelectorAll('.arch-zone-network .arch-node')]"
            ".find(e => e.textContent.includes(name));"
            " if (!n) return 'absent'; const r = n.getBoundingClientRect();"
            " return r.right <= b.right + 1 ? '' : `${Math.round(r.right - b.right)} px coupés`; }",
            node,
        )
        r.check(not cut, f"{width}×{height} : le nœud {node} est entier", cut)
    r.page.set_viewport_size({"width": 1600, "height": 1000})


# ---------- story 21: the programme in FR-38's order, the business scenarios ----------


def _scenarios_yaml() -> dict[str, Any]:
    """`content/scenarios.yaml`, the source of the expected programme and prompts: a
    scenario added by its rules needs no change here."""
    import yaml

    return yaml.safe_load((REPO / "content" / "scenarios.yaml").read_text(encoding="utf-8"))


def _prompts(scenario_id: str) -> list[str]:
    return [" ".join(p.split()) for p in _scenarios_yaml()["scenarios"][scenario_id]["prompts"]]


def s_programme(r: Run) -> None:
    """The scenario picker lists FR-38's modules, then the hosting and business scenarios;
    a module launched directly has the previous modules' bricks (CAP-40)."""
    content = _scenarios_yaml()
    expected = [
        [f"Module {i} · {m['title_text']} · {m['duration_min']} min", m["scenarios"]]
        for i, m in enumerate(content["program"], start=1)
    ] + [["Transverses et métier", content["transverse"]]]
    read = (
        "() => [...document.querySelectorAll('#scenario-picker optgroup')].map(g =>"
        " [g.label, [...g.querySelectorAll('option')].map(o => o.value)])"
    )
    r.wait_idle()
    ok, took = r.poll(lambda: r.page.evaluate(read) == expected, 10)
    r.check(
        ok,
        "sélecteur : modules dans l'ordre de FR-38, puis « Transverses et métier »",
        str(r.page.evaluate(read))[:400],
    )
    first = content["program"][4]["scenarios"][0]
    earlier = {
        b
        for m in content["program"][:4]
        for i in m["scenarios"]
        for b in content["scenarios"][i]["bricks"]
    } - {"reasoning", "rag"}
    r.launch(first)  # module 5, launched directly
    wanted = {k for k, b in r.bricks().items() if b["wanted"]}
    r.check(
        earlier <= wanted and not {"reasoning", "rag"} & wanted,
        "module 5 lancé directement : les briques des modules 1 à 4, sans le raisonnement ni "
        "le RAG",
        str(sorted(wanted)),
    )
    guide = r.page.locator("#scenario-info-popover")
    r.check(
        "sans le raisonnement ni le RAG" in guide.text_content(),
        "la consigne dit que le raisonnement et le RAG restent éteints",
    )
    r.launch("mcp_full")
    r.check(
        not r.bricks()["rag"]["wanted"]
        and "sauf le raisonnement et le RAG" in guide.text_content(),
        "« MCP en documentation complète » : RAG éteint, la consigne le dit",
    )


def s_soc(r: Run) -> None:
    """FR-40, SOC: H2 logs the reads; the model looks for the privileged accounts' inventory
    itself and H1 blocks it; the audit log opens from the schema."""
    first, second = _prompts("soc")
    r.launch("soc")
    guide = r.page.locator("#scenario-info-popover").text_content()
    r.check(
        "Métier SOC" in guide and "analyste habilité" in guide,
        "consigne du scénario SOC affichée, qui cite l'analyste habilité",
    )
    seq = r.ev.mark()
    ended = r.send(first)
    _scenario_info(r)
    reads = [e["payload"] for e in r.ev.since(seq, "tool_ended")]
    r.check(
        bool(reads) and reads[0]["status"] == "ok",
        "read_file lit alertes_siem.log",
        str(reads)[:200],
    )
    decided = [e["payload"] for e in r.ev.since(seq, "hook_decided")]
    r.check(any(d["hook"] == "h2" for d in decided), "H2 journalise la lecture")
    r.check(
        ended["payload"]["status"] == "completed" and "SIEM" in r.last_answer(),
        "la réponse s'appuie sur le journal d'alertes",
        r.last_answer()[:160],
    )
    seq = r.ev.mark()
    ended = r.send(second)
    started = [e["payload"]["arguments"] for e in r.ev.since(seq, "tool_started")]
    r.check(
        started[:1] == [{"path": "."}],
        "le prompt ne nomme aucun fichier : le modèle liste le dossier",
        str(started)[:200],
    )
    decided = [e["payload"] for e in r.ev.since(seq, "hook_decided")]
    r.check(
        any(d["hook"] == "h1" and d["decision"] == "block" for d in decided),
        "H1 bloque l'inventaire des comptes à privilèges que le modèle a trouvé",
        str([(d["hook"], d["decision"]) for d in decided]),
    )
    r.check(
        ended["payload"]["status"] == "completed" and "analyste habilité" in r.last_answer(),
        "le tour se termine par une escalade vers un humain",
        r.last_answer()[:160],
    )
    calls = r.fake_calls()
    sent = json.dumps(calls[-1]["messages"], ensure_ascii=False) if calls else ""
    r.check(
        bool(calls) and "adm.nguyen" not in sent, "le contenu confidentiel n'atteint pas le modèle"
    )
    audit = r.api("GET", "/api/audit").json().get("text", "")
    r.check(
        "alertes_siem.log" in audit and "bloqué par H1" in audit,
        "journal d'audit : les lectures permises et la lecture bloquée",
        audit.strip().splitlines()[-1][:200] if audit.strip() else "vide",
    )
    r.page.locator('#schema .arch-node[data-component="file.audit"]').click()
    text = r.page.locator("#audit-text")
    expect(r.page.locator("#audit-dialog")).to_be_visible(timeout=5000)
    try:
        expect(text).to_contain_text("bloqué par H1", timeout=10_000)
        opened = True
    except AssertionError:
        opened = False
    r.check(opened, "clic sur « Journal d'audit » dans le schéma : le fichier s'ouvre")
    # The scenario's lines are the last ones of a log the whole run feeds.
    text.evaluate("e => { for (let n = e; n; n = n.parentElement) n.scrollTop = n.scrollHeight; }")
    r.shot("26-metier-soc-journal-audit")
    r.page.click("#audit-close")

    # Left open, the instructions follow the scenario launched next.
    info = r.page.locator("#scenario-info")
    info.click()
    popover = r.page.locator("#scenario-info-popover")
    expect(popover).to_be_visible(timeout=5000)
    r.launch("reasoning")
    title = _content("fr", "scenarios.yaml")["scenarios"]["reasoning"]["title_text"]
    r.check(
        title in (popover.text_content() or "") and "Métier SOC" not in popover.text_content(),
        "nouveau scénario : la consigne ouverte montre le nouveau",
        (popover.text_content() or "")[:120],
    )
    r.page.keyboard.press("Escape")


def _scenario_info(r: Run) -> None:
    """The scenario's instructions sit behind the « i » of the Vue humain title: a toggletip
    (click, Escape) previewed on hover; open, the field and the last bubble stay in view."""
    info = r.page.locator("#scenario-info")
    popover = r.page.locator("#scenario-info-popover")
    open_ = "e => e.matches(':popover-open')"
    r.check(
        info.is_visible() and "Métier SOC" in (info.get_attribute("aria-label") or ""),
        "« i » visible, nommé d'après le scénario",
        info.get_attribute("aria-label") or "",
    )
    info.click()
    r.check(popover.evaluate(open_), "clic sur le « i » : la consigne s'ouvre")
    box, view = popover.bounding_box(), r.page.viewport_size
    r.check(
        bool(box and view)
        and box["x"] >= 0
        and box["y"] >= 0
        and box["x"] + box["width"] <= view["width"]
        and box["y"] + box["height"] <= view["height"],
        "consigne longue : entière dans la fenêtre (elle défile au besoin)",
        str(box),
    )

    def in_view() -> str:
        """Empty when the field is whole in the pane and 20 px of the last bubble show."""
        body = r.page.locator("section[data-pane='human'] .pane-body-human").bounding_box()
        chat = r.page.locator("#chat").bounding_box()
        field = r.page.locator("#composer-input").bounding_box()
        bubble = r.page.locator("#chat .bubble").last.bounding_box()
        if not (body and chat and field and bubble):
            return f"champ {field} · bulle {bubble} · fil {chat}"
        fits = field["y"] + field["height"] <= body["y"] + body["height"]
        shown = min(bubble["y"] + bubble["height"], chat["y"] + chat["height"]) - max(
            bubble["y"], chat["y"]
        )
        return "" if fits and shown >= 20 else f"champ {field} · bulle {bubble} · fil {chat}"

    missing = in_view()
    r.check(not missing, "la consigne ne prend pas de place au fil ni au champ", missing)
    r.page.keyboard.press("Escape")
    r.check(not popover.evaluate(open_), "Échap ferme la consigne")
    r.page.mouse.move(0, 0)  # the pointer must enter the « i » again
    info.hover()
    ok, took = r.poll(lambda: popover.evaluate(open_), 3)
    r.check(ok, "survol du « i » : la consigne s'ouvre en infobulle", f"au bout de {took:.1f} s")
    info.click()
    r.page.mouse.move(0, 0)
    time.sleep(0.6)
    r.check(popover.evaluate(open_), "un clic pendant le survol la garde ouverte")
    r.page.keyboard.press("Escape")
    info.hover()
    r.poll(lambda: popover.evaluate(open_), 3)
    r.page.mouse.move(0, 0)
    ok, took = r.poll(lambda: not popover.evaluate(open_), 3)
    r.check(ok, "ouverte au survol, elle se ferme quand la souris s'en va", f"{took:.1f} s")


def _public_server_offline(r: Run, server: str, label: str, seq: int | None = None) -> None:
    """`seq`: the server is contacted by this launch, its answer is awaited after `seq`.
    Without it, a server already enabled by the previous scenario is not contacted again
    (AD-15): its last answer, the current connection state, still stands."""
    if seq is not None:
        ended = r.ev.wait("mcp_connect_ended", seq, lambda p: p["server"] == server, 45)["payload"]
    else:
        ends = {e["payload"]["server"]: e["payload"] for e in r.ev.since(0, "mcp_connect_ended")}
        ended = ends.get(server, {})
    r.check(
        ended.get("status") == "error" and bool(ended.get("error_text")),
        f"{label} injoignable sans réseau : échec expliqué",
        (ended.get("error_text") or str(ended))[:200],
    )
    arch = r.state()["architecture_changed"]
    drawn = next((n for n in arch["nodes"] if n["id"] == f"mcp.{server}"), {})
    r.check(
        drawn.get("hosting") == "network" and drawn.get("available") is False,
        f"schéma : {label} dessiné dans la zone Réseau, indisponible",
        str({k: drawn.get(k) for k in ("hosting", "available", "reason_text")})[:200],
    )
    zone = r.page.locator("#schema .arch-zone-network")
    r.check(label in zone.inner_text(), f"le nœud {label} est dans la zone Réseau du schéma")


def _enabled_servers(r: Run) -> tuple[list[str], str]:
    mcp = r.bricks()["mcp"]
    return sorted(o["id"] for o in mcp["options"] if o["enabled"]), mcp.get("mode", "")


def s_iam(r: Run) -> None:
    """FR-40, IAM: Microsoft Learn alone, full documentation; offline here, since the launcher
    cuts the outbound network (to test with the network on the target PC)."""
    seq = r.ev.mark()
    r.launch("iam")
    started = [e["payload"]["server"] for e in r.ev.since(seq, "mcp_connect_started")]
    r.check("mslearn" in started, "le scénario contacte Microsoft Learn", str(started))
    enabled, mode = _enabled_servers(r)
    r.check(
        enabled == ["mslearn"] and mode == "full",
        "carte MCP : Microsoft Learn seul, documentation complète",
        f"{enabled} · {mode}",
    )
    _public_server_offline(r, "mslearn", "Microsoft Learn", seq)
    for prompt in _prompts("iam"):
        seq = r.ev.mark()
        ended = r.send(prompt)
        r.check(
            ended["payload"]["status"] == "completed"
            and not r.ev.since(seq, "tool_started")
            and "Microsoft Learn" in r.last_answer(),
            "le tour aboutit sans outil, serveur indisponible",
            r.last_answer()[:160],
        )


def s_sovereignty(r: Run) -> None:
    """FR-40, sovereignty: data.gouv.fr and Microsoft Learn in lazy loading, two flows out
    of the workstation to two operators."""
    r.launch("sovereignty")
    enabled, mode = _enabled_servers(r)
    r.check(
        enabled == ["datagouv", "mslearn"] and mode == "lazy",
        "carte MCP : data.gouv.fr et Microsoft Learn, lazy loading",
        f"{enabled} · {mode}",
    )
    _public_server_offline(r, "datagouv", "data.gouv.fr")
    _public_server_offline(r, "mslearn", "Microsoft Learn")
    arch = r.state()["architecture_changed"]
    crossing = [e for e in arch["edges"] if e.get("crosses_boundary")]
    # The run's model is a cloud one: its flow crosses too, as the instructions say.
    others = {e["from"] + e["to"] for e in crossing if "core.model" not in e["from"] + e["to"]}
    r.check(
        any("datagouv" in e for e in others)
        and any("mslearn" in e for e in others)
        and all("datagouv" in e or "mslearn" in e for e in others),
        "hors modèle cloud, seuls les flux vers data.gouv.fr et Microsoft Learn sortent du poste",
        str(crossing)[:300],
    )
    r.check(
        any("core.model" in e["from"] + e["to"] for e in crossing),
        "le modèle cloud du parcours franchit lui aussi la frontière",
    )
    for prompt, label in zip(
        _prompts("sovereignty"), ("data.gouv.fr", "Microsoft Learn"), strict=True
    ):
        ended = r.send(prompt)
        r.check(
            ended["payload"]["status"] == "completed" and label in r.last_answer(),
            f"le tour aboutit, sans {label}",
            r.last_answer()[:160],
        )


def _forced_section(r: Run) -> None:
    """D3 (2026-10-01): the switch in its titled section with the ✋; turned on, it unfolds the
    option list of the bricks whose Forcer buttons are in it (here « Outils »)."""
    r.show_forced(False)
    details = r.card("Outils").locator("details.brick-options")
    if details.get_attribute("open") is not None:
        details.locator("summary").click()  # folded first: the switch must be what unfolds it
    r.check(details.get_attribute("open") is None, "D3 : liste des outils repliée au départ")
    section = r.page.locator("#bricks .force-section")
    title = section.locator(".force-section-title").inner_text()
    hand = section.locator(".force-toggle-icon").inner_text()
    r.check(
        title.strip().lower() == "actions forcées" and hand.strip() == "✋",
        "D3 : l'interrupteur des actions forcées a son titre de section et l'icône ✋",
        f"{title!r} · {hand!r}",
    )
    r.check(
        section.locator(".brick-toggle").count() == 1
        and r.page.locator("#bricks .force-section article.brick-card").count() == 0,
        "D3 : la section ne porte que l'interrupteur des actions forcées",
    )
    # Lot 1 of 2026-10-04: the « ? » by the title, the bricks' help popover, anchored to the
    # button, still open after a rebuild of the panel (a brick switched by the API, so that no
    # click light-dismisses it).
    help_button = section.locator("#force-help")
    help_button.click()
    bubble = r.page.locator("#explain-force-section")
    expect(bubble).to_be_visible(timeout=5000)
    button_box, bubble_box = help_button.bounding_box(), bubble.bounding_box()
    anchored = bool(button_box and bubble_box) and (
        abs(bubble_box["y"] - (button_box["y"] + button_box["height"])) < 24
        and bubble_box["x"] - 24 < button_box["x"] < bubble_box["x"] + bubble_box["width"]
    )
    r.check(
        help_button.get_attribute("aria-label") == "Ce que font les actions forcées"
        and bubble.inner_text().strip()
        == "Le harnais déclenche lui-même l'outil, sans laisser le modèle décider."
        and anchored,
        "lot 1 : le « ? » d'« Actions forcées » ouvre son aide, ancrée sous le bouton",
        f"{button_box} · {bubble_box}",
    )
    was = bool(r.bricks()["system_prompt"]["wanted"])
    seq = r.ev.mark()
    r.api("POST", "/api/intentions/brick", {"brick": "system_prompt", "wanted": not was})
    r.ev.wait("bricks_changed", seq, timeout=10)
    time.sleep(0.5)
    r.check(
        r.page.locator("#explain-force-section").evaluate("e => e.matches(':popover-open')"),
        "lot 1 : l'aide d'« Actions forcées » reste ouverte après un nouveau rendu",
    )
    r.page.keyboard.press("Escape")
    r.set_brick("Prompt système", was)
    r.show_forced(True)
    opened, _ = r.poll(lambda: details.get_attribute("open") is not None, 5)
    r.check(opened, "D3 : « Afficher les actions forcées » déplie la liste des outils")
    r.check(
        details.get_by_role("button", name="Forcer l'appel : Heure et date").is_visible(),
        "D3 : le bouton « Forcer l'appel » est visible sans autre clic",
    )


def _consulted_tools(r: Run) -> None:
    """D5 (2026-10-01): under the answer of a turn that called a tool, « Outils consultés
    pendant ce tour : … », each name leading to its Orchestration step; none without tool."""
    line = r.page.locator("#chat .bubble-model").last.locator(".answer-tools")
    r.check(
        line.count() == 1 and "Outils consultés pendant ce tour" in line.inner_text(),
        "D5 : la réponse dit les outils consultés pendant le tour",
        line.inner_text() if line.count() else "aucune ligne",
    )
    link = line.get_by_role("button", name="Calculatrice")
    r.check(link.count() == 1, "D5 : « Calculatrice » nommée sous la réponse")
    link.click()
    step = _step(r, "Calculatrice")
    opened, _ = r.poll(
        lambda: (
            step.locator(".turn-step-line").get_attribute("aria-expanded") == "true"
            and "is-selected" in (step.get_attribute("class") or "").split()
        ),
        5,
    )
    r.check(
        opened,
        "D5 : un clic sur le nom déplie et sélectionne l'étape de l'outil dans Orchestration",
        step.get_attribute("class") or "",
    )
    r.send("Bonjour")
    after = r.page.locator("#chat .bubble-model").last.locator(".answer-tools")
    r.check(after.count() == 0, "D5 : un tour sans outil n'affiche aucune ligne d'outils")


def _forced_kept_after_reload(r: Run) -> None:
    """E035 (story 5 of the deferred leftovers): « Afficher les actions forcées », turned on,
    is remembered by the browser: after a reload, the switch is on and the Forcer buttons are
    there without a click."""
    r.show_forced(True)
    stored = r.page.evaluate("() => localStorage.getItem('wavestack.forcedActions')")
    r.reload_app()
    toggle = r.page.locator("label.force-toggle input")
    # In the option list, folded after a reload: by its focus key, not by role (hidden).
    button = r.page.locator('#bricks .force-button[data-focus-key="force:tools:get_datetime"]')
    ok, _ = r.poll(lambda: toggle.count() == 1 and toggle.is_checked() and button.count() == 1, 10)
    r.check(
        stored == "1" and ok,
        "E035 : « Afficher les actions forcées » gardé après rechargement (bouton « Forcer » là)",
        f"localStorage {stored!r}, case {'cochée' if toggle.is_checked() else 'décochée'}, "
        f"{button.count()} bouton(s) « Forcer l'appel » de l'heure",
    )


def _forced_dropped(r: Run) -> None:
    """E035: an armed action whose tool is unticked before the turn is dropped, said by its
    line « Action forcée abandonnée · … » in Orchestration."""
    r.open_options("Outils")
    r.arm("Forcer l'appel : Heure et date")
    try:
        r.set_option("Outils", "Heure et date", False)
        seq = r.ev.mark()
        r.send("Bonjour")
        dropped = r.ev.since(seq, "action_dropped")
        line = _step(r, "Action forcée abandonnée")
        ok, _ = r.poll(lambda: line.count() == 1 and "Heure et date" in line.inner_text(), 5)
        r.check(
            bool(dropped) and ok,
            "E035 : ligne « Action forcée abandonnée · Heure et date » dans Orchestration",
            f"{len(dropped)} action_dropped ; "
            + (line.inner_text()[:160] if line.count() else "ligne absente"),
        )
    finally:
        r.set_option("Outils", "Heure et date", True)


def s_forced_native(r: Run) -> None:
    r.launch("native_tools")
    _forced_section(r)
    _forced_kept_after_reload(r)
    r.open_options("Outils")
    r.arm("Forcer l'appel : Heure et date")
    expect(r.page.locator("#armed-chips")).to_be_visible(timeout=5000)
    r.check(True, "outil sans paramètre armé en un clic")
    r.page.locator("#armed-chips button").first.click()  # disarm
    time.sleep(0.5)
    r.check(not r.state()["armed_actions_changed"]["actions"], "la puce désarme l'action")
    r.arm("Forcer l'appel : Calculatrice", preset="Multiplication")
    seq = r.ev.mark()
    ended = r.send("Bonjour")
    starts = [e for e in r.ev.since(seq, "tool_started")]
    r.check(
        any(e["payload"]["tool"] == "calculator" and e.get("trigger") == "user" for e in starts),
        "calculatrice forcée exécutée avant l'appel au modèle",
    )
    r.check(
        "444" in r.last_answer() and ended["payload"]["status"] == "completed",
        "le modèle reçoit le résultat forcé (12*37 = 444)",
        r.last_answer()[:160],
    )
    # Story 34: the forced step's tile says the user acts.
    tile = _step(r, "Calculatrice").locator(".turn-step-tile").inner_text()
    r.check(tile == "U", "l'étape forcée porte la pastille « U »", tile)
    _consulted_tools(r)
    _forced_dropped(r)
    r.show_forced(False)


def _memory_file(r: Run) -> list[dict[str, Any]]:
    path = r.stack.data_dir / "memory.json"
    return json.loads(path.read_text(encoding="utf-8")) if path.exists() else []


def _memory_step(r: Run):
    """The last « Écriture en mémoire » step of Orchestration."""
    name = r.page.locator(".turn-step-name", has_text="Écriture en mémoire")
    return r.page.locator("#orch-scroll .turn-step", has=name).last


# A color token of tokens.css, as `getComputedStyle` writes a color (`rgb(…)`).
_CSS_COLOR_JS = (
    "name => { const probe = document.createElement('span');"
    " probe.style.color = `var(${name})`; document.body.appendChild(probe);"
    " const color = getComputedStyle(probe).color; probe.remove(); return color; }"
)


def _memory_drawer_frame(r: Run) -> None:
    """Story 22 (C1): the cross, « Tout effacer » and « Fermer » in view without scrolling,
    inside the drawer; « Tout effacer » a danger button, unlike an entry's « Enregistrer »."""
    drawer = r.page.locator("#memory-drawer")
    frame = drawer.bounding_box() or {}
    viewport = r.page.viewport_size or {}
    buttons = {
        "×": drawer.get_by_role("button", name="Fermer la mémoire globale"),
        "Tout effacer": drawer.get_by_role("button", name="Tout effacer", exact=True),
        "Fermer": drawer.get_by_role("button", name="Fermer", exact=True),
    }
    outside = []
    for name, button in buttons.items():
        box = button.bounding_box()
        if not (
            box
            and box["y"] >= frame["y"]
            and box["y"] + box["height"] <= frame["y"] + frame["height"]
            and box["x"] >= frame["x"]
            and box["x"] + box["width"] <= frame["x"] + frame["width"]
            and box["y"] + box["height"] <= viewport.get("height", 0)
        ):
            outside.append(f"{name} {box}")
    scrolled, overflows = drawer.locator("#memory-scroll").evaluate(
        "e => [e.scrollTop, e.scrollHeight > e.clientHeight]"
    )
    r.check(overflows, "la liste des 6 entrées déborde : seule la zone centrale défile")
    r.check(
        not outside and scrolled == 0,
        "tiroir de la mémoire (6 entrées) : croix, « Tout effacer » et « Fermer » visibles "
        "sans défiler",
        "; ".join(outside) or f"cadre {frame}",
    )
    read = (
        "b => { const s = getComputedStyle(b);"
        " return [b.className, s.borderTopColor, s.boxShadow]; }"
    )
    clear = buttons["Tout effacer"].evaluate(read)
    save = drawer.get_by_role("button", name="Enregistrer l'entrée 1").evaluate(read)
    danger = r.page.evaluate(_CSS_COLOR_JS, "--color-danger")
    r.check(
        "danger" in clear[0].split() and clear[1] == danger and save[1] != clear[1],
        "« Tout effacer » : classe danger, bordure danger, distincte d'« Enregistrer » d'une "
        "entrée",
        f"Tout effacer {clear} · Enregistrer {save} · danger {danger}",
    )
    r.check(
        save[2] == "none", "« Enregistrer » d'une entrée : action compacte sans relief", save[2]
    )


def s_global_memory(r: Run) -> None:
    """Story 14: written by the model, then forced, read back after clearing, edited in the
    drawer (from the schema's node and from the card), restored by the reset."""
    r.launch("global_memory")
    card = r.card("Mémoire globale")
    expect(card).to_contain_text("3 entrées en mémoire globale", timeout=5000)
    r.check(True, "la carte compte les 3 entrées de démonstration")

    # The model writes (the fake model calls `remember` on « Retiens que … »).
    seq = r.ev.mark()
    r.send("Retiens que je préfère des réponses en trois points au plus.")
    writes = [
        e for e in r.ev.since(seq, "effect_applied") if e["payload"].get("effect") == "memory_write"
    ]
    r.check(
        len(writes) == 1
        and writes[0].get("trigger") == "model"
        and writes[0].get("component") == "file.memory",
        "remember : effet memory_write sur file.memory, déclenché par le modèle",
        str([(e.get("trigger"), e.get("component")) for e in writes]),
    )
    saved = _memory_file(r)
    r.check(
        [e["source"] for e in saved] == ["demo", "demo", "demo", "model"],
        "memory.json : la démonstration puis l'entrée du modèle",
        str([e["source"] for e in saved]),
    )
    step = _memory_step(r)
    r.check(
        "Déclenché par le modèle" in step.locator(".turn-step-trigger").inner_text(),
        "étape « Écriture en mémoire » avec le badge « Déclenché par le modèle »",
    )
    step.locator(".turn-step-line").click()
    expect(step).to_contain_text("Entrée écrite dans memory.json", timeout=5000)
    r.check(
        "trois points au plus" in step.inner_text(),
        "l'étape dépliée montre l'entrée écrite par le harnais",
    )
    r.shot("19-memoire-ecriture-par-le-modele")

    # Cleared conversation: the name and the preference come back by the system message.
    seq = r.ev.mark()
    r.page.click("#clear-conversation")
    r.ev.wait("conversation_cleared", seq, timeout=10)
    r.send("Rappelle-moi mon prénom, puis donne-moi des conseils pour préparer une formation.")
    r.check(
        "Pascal" in r.last_answer(),
        "après « Vider la conversation », le prénom revient de la mémoire globale",
        r.last_answer()[:120],
    )
    body = r.fake_calls()[-1]
    first = body["messages"][0]
    r.check(
        first.get("role") == "system" and "trois points" in json.dumps(first, ensure_ascii=False),
        "la préférence est dans le message système envoyé",
        [m.get("role") for m in body["messages"]].__repr__(),
    )
    r.check(
        [m.get("role") for m in body["messages"]][1:] == ["user"],
        "aucun historique : seule la mémoire globale a porté l'information",
    )

    # « Écrire en mémoire » forced from the card.
    r.show_forced(True)
    card.get_by_role("button", name="Écrire en mémoire : Mémoire globale").click()
    form = card.locator(".force-form")
    expect(form).to_be_visible(timeout=5000)
    form.locator("input").fill("Pascal anime la formation à Nantes.")
    seq = r.ev.mark()
    form.get_by_role("button", name="Armer").click()
    r.ev.wait("armed_actions_changed", seq, lambda p: bool(p["actions"]), timeout=10)
    expect(card.locator(".armed-chip")).to_contain_text("Armé : Écrire en mémoire", timeout=5000)
    r.check(True, "puce « Armé : Écrire en mémoire (…) » sur la carte")
    seq = r.ev.mark()
    r.send("Bonjour")
    forced = [e for e in r.ev.since(seq, "tool_started") if e["payload"]["tool"] == "remember"]
    r.check(
        len(forced) == 1
        and forced[0].get("trigger") == "user"
        and forced[0]["seq"] < r.ev.since(seq, "model_call_started")[0]["seq"],
        "écriture forcée : remember exécuté par l'utilisateur, avant l'appel au modèle",
    )
    r.check(
        "Forcé par l'utilisateur" in _memory_step(r).locator(".turn-step-trigger").inner_text(),
        "étape « Écriture en mémoire » avec le badge « Forcé par l'utilisateur »",
    )
    r.check(_memory_file(r)[-1]["source"] == "user", "memory.json : entrée forcée, source user")
    # D5 (2026-10-01): `remember`, a harness tool, is no source of the answer.
    r.check(
        r.page.locator("#chat .bubble-model").last.locator(".answer-tools").count() == 0,
        "D5 : une écriture en mémoire forcée n'est pas listée parmi les outils consultés",
    )
    r.show_forced(False)
    # Story 22: a sixth entry, so that the drawer's list is long.
    r.send("Retiens que j'anime aussi un atelier sur les hooks le mardi.")
    r.check(len(_memory_file(r)) == 6, "memory.json : 6 entrées", str(len(_memory_file(r))))

    # The drawer, opened by a click on the schema's node.
    drawer = r.page.locator("#memory-drawer")
    r.page.locator('#schema .arch-node[data-component="file.memory"]').click()
    expect(drawer).to_be_visible(timeout=5000)
    entries = drawer.locator("#memory-list li")
    r.check(entries.count() == 6, "clic sur le nœud memory.json : le tiroir liste 6 entrées")
    r.check(
        str(r.stack.data_dir / "memory.json") in drawer.inner_text(),
        "le tiroir donne le chemin du fichier",
    )
    _memory_drawer_frame(r)
    # D7 (2026-10-01): each entry says when it was written, `created_at` of memory.json.
    dates = entries.evaluate_all(
        "items => items.map(li => { const t = li.querySelector('time.memory-entry-date');"
        " return t ? [t.dateTime, t.textContent] : null; })"
    )
    written = [e["created_at"] for e in _memory_file(r)]
    r.check(
        [d[0] if d else None for d in dates] == written and all(d and d[1].strip() for d in dates),
        "D7 : chaque entrée du tiroir affiche sa date d'écriture (created_at)",
        f"{dates} · {written}",
    )
    r.shot("20-memoire-tiroir")

    seq = r.ev.mark()
    entries.first.locator("textarea").fill("L'utilisateur s'appelle Pascal Martin.")
    entries.first.get_by_role("button", name="Enregistrer l'entrée 1").click()
    r.ev.wait("memory_changed", seq, timeout=10)
    saved = _memory_file(r)
    r.check(
        saved[0]["text"] == "L'utilisateur s'appelle Pascal Martin."
        and saved[0]["source"] == "user",
        "modifier : memory.json réécrit, source user",
    )
    replaced = [e for e in r.ev.since(seq, "effect_applied")]
    r.check(
        [e.get("trigger") for e in replaced] == ["user"],
        "l'écriture du tiroir est attribuée à l'utilisateur",
    )

    seq = r.ev.mark()
    drawer.get_by_role("button", name="Supprimer l'entrée 2").click()
    r.ev.wait("memory_changed", seq, timeout=10)
    expect(entries).to_have_count(5, timeout=5000)
    r.check(len(_memory_file(r)) == 5, "supprimer : 5 entrées restent")

    entries.first.locator("textarea").fill("Texte modifié sans l'enregistrer.")
    r.page.keyboard.press("Escape")
    alert = drawer.locator("#memory-alert")
    expect(alert).to_contain_text("Modification non enregistrée. Enregistrer ou abandonner ?")
    r.check(drawer.is_visible(), "Échap avec une modification : le tiroir demande quoi faire")
    drawer.get_by_role("button", name="Abandonner").click()
    expect(drawer).to_be_hidden(timeout=5000)
    r.check(len(_memory_file(r)) == 5, "abandonner : rien n'est écrit")

    # Story 22: the cross closes the drawer like « Fermer ».
    card.get_by_role("button", name="Modifier la mémoire").click()
    expect(drawer).to_be_visible(timeout=5000)
    drawer.get_by_role("button", name="Fermer la mémoire globale").click()
    closed, _ = r.poll(lambda: drawer.is_hidden(), 5)
    r.check(closed, "la croix « × » ferme le tiroir de la mémoire")

    card.get_by_role("button", name="Modifier la mémoire").click()
    expect(drawer).to_be_visible(timeout=5000)
    drawer.get_by_role("button", name="Tout effacer", exact=True).click()
    expect(alert).to_contain_text("Effacer les 5 entrées")
    confirm = drawer.get_by_role("button", name="Oui, tout effacer")
    look = confirm.evaluate(
        "b => { const s = getComputedStyle(b); return [b.className, s.backgroundColor]; }"
    )
    danger = r.page.evaluate(_CSS_COLOR_JS, "--color-danger")
    r.check(
        "danger" in look[0] and look[1] == danger,
        "« Oui, tout effacer » : bouton danger, fond de la couleur danger",
        f"{look} · danger {danger}",
    )
    wrong = _on_vivid_both_themes(r, confirm)
    r.check(not wrong, "« Oui, tout effacer » : texte en --color-on-vivid sur le rouge", str(wrong))
    r.check(len(_memory_file(r)) == 5, "« Tout effacer » demande d'abord confirmation")
    seq = r.ev.mark()
    drawer.get_by_role("button", name="Oui, tout effacer").click()
    r.ev.wait("memory_changed", seq, lambda p: p["entries"] == [], timeout=10)
    empty = drawer.locator("#memory-empty")
    expect(empty).to_be_visible(timeout=5000)
    r.check(
        "Aucune information en mémoire globale." in empty.inner_text() and _memory_file(r) == [],
        "tout effacer : fichier vide et message de mémoire vide",
        empty.inner_text(),
    )
    r.shot("21-memoire-tiroir-vide")
    drawer.get_by_role("button", name="Fermer", exact=True).click()
    expect(drawer).to_be_hidden(timeout=5000)

    # The reset restores the demonstration.
    seq = r.ev.mark()
    r.page.click("#reset-button")
    r.ev.wait("harness_reset", seq, timeout=10)
    r.ev.wait("memory_changed", seq, lambda p: len(p["entries"]) == 3, timeout=10)
    r.check(
        [e["source"] for e in _memory_file(r)] == ["demo"] * 3,
        "réinitialiser : la mémoire de démonstration est restaurée",
    )


RAG_QUESTION = "Combien de caractères doit compter au minimum un mot de passe chez Exemplia ?"


def _rag_step(r: Run):
    """The last « Recherche RAG » step of Orchestration."""
    name = r.page.locator(".turn-step-name", has_text="Recherche RAG")
    return r.page.locator("#orch-scroll .turn-step", has=name).last


def s_rag(r: Run) -> None:
    """Story 15, a fresh install: neither model nor index; a download that fails (explained)
    then succeeds, « Construire l'index » from the card, then a turn without and with the
    RAG, the search step, the excerpts in Contexte LLM, the index in the schema, « Comparer »,
    and the step still there after a reload."""
    r.launch("rag")
    card = r.card("RAG")
    download = card.get_by_role("button", name=re.compile("Télécharger le modèle d'embedding"))
    expect(download).to_be_visible(timeout=10_000)
    r.check(
        "index absent" in card.inner_text()
        and "Téléchargez d'abord" in card.inner_text()
        and download.is_enabled(),
        "installation neuve : « index absent », et « Télécharger » proposé d'abord",
        card.inner_text()[:260],
    )
    rag = r.bricks()["rag"]
    r.check(
        rag["wanted"]
        and not rag["available"]
        and rag["download"]["target"] == "rag_embedding"
        and rag["build_index"] is None,
        "/api/state : RAG voulue, indisponible, téléchargement proposé, pas encore de construction",
    )
    # Story 22: wanted but unavailable, the brick greys « Reranking » with its own reason.
    rerank = card.locator('input[data-focus-key="option:rag:rerank"]')
    row = card.locator("label.brick-option:has(input[data-focus-key='option:rag:rerank'])")
    r.check(
        rerank.is_disabled()
        and row.get_attribute("title") == rag["reason_text"]
        and rerank.get_attribute("aria-description") == rag["reason_text"],
        "RAG voulue mais indisponible : « Reranking » désactivé, raison de la brique au survol",
        f"« {row.get_attribute('title')} » · raison « {rag['reason_text']} »",
    )

    # The file is not served yet: the download fails, explained on the card.
    seq = r.ev.mark()
    download.click()
    r.ev.wait("session_state", seq, lambda p: p["state"] == "download", 10)
    error = r.ev.wait("harness_error", seq, timeout=20)
    r.ev.wait("session_state", seq, lambda p: p["state"] == "idle", 20)
    effect = error["payload"].get("effect_text") or ""
    r.check(
        "copiez le fichier à la main dans" in effect and error.get("brick") == "rag",
        "échec du téléchargement : harness_error, avec le dossier où copier le fichier",
        effect[:200],
    )
    notice = card.locator(".force-error")
    expect(notice).to_contain_text("copiez le fichier à la main", timeout=5000)
    r.check(True, "la carte RAG explique l'échec du téléchargement")
    part = list((r.stack.data_dir / "models").rglob("*.part"))
    r.check(not part, "aucun fichier .part laissé", str(part))

    # Finition V1 (#20): the file served a byte a second, « Arrêter » during the download: a
    # neutral line on the card, no failure, no copy by hand.
    ready = f"{r.stack.fake_url}/_e2e/model_ready"
    httpx.post(ready, json={"slow": True}, timeout=5, trust_env=False)
    seq = r.ev.mark()
    card.get_by_role("button", name=re.compile("Télécharger le modèle d'embedding")).click()
    r.ev.wait("session_state", seq, lambda p: p["state"] == "download", 10)
    # The `.part` open first (the answer's headers received): its removal is what is checked.
    started, _ = r.poll(lambda: bool(list((r.stack.data_dir / "models").rglob("*.part"))), 10)
    r.check(started, "#20 : le fichier .part existe avant « Arrêter »")
    r.api("POST", "/api/intentions/stop")
    stopped = r.ev.wait(
        "effect_applied", seq, lambda p: p["effect"] == "model_download_stopped", 20
    )
    r.ev.wait("session_state", seq, lambda p: p["state"] == "idle", 20)
    note = card.locator(".brick-note", has_text="arrêté")
    expect(note).to_contain_text("le fichier en cours est supprimé", timeout=5000)
    r.check(
        not r.ev.since(seq, "harness_error")
        and stopped.get("brick") == "rag"
        and card.locator(".force-error").count() == 0
        and "copiez le fichier à la main" not in card.inner_text(),
        "#20 : téléchargement arrêté, ligne neutre sur la carte, ni erreur ni copie à la main",
        note.inner_text(),
    )
    part = list((r.stack.data_dir / "models").rglob("*.part"))
    r.check(not part, "#20 : aucun fichier .part laissé après « Arrêter »", str(part))

    # The file is served now: the download succeeds; the card offers the index's build.
    httpx.post(ready, timeout=5, trust_env=False)
    seq = r.ev.mark()
    card.get_by_role("button", name=re.compile("Télécharger le modèle d'embedding")).click()
    r.ev.wait("session_state", seq, lambda p: p["state"] == "download", 10)
    r.ev.wait(
        "bricks_changed",
        seq,
        lambda p: next(b for b in p["bricks"] if b["id"] == "rag").get("build_index") is not None,
        30,
    )
    r.check(
        (r.stack.data_dir / "models" / "embedding" / "fake-e2e.gguf").is_file(),
        "téléchargement réussi : le fichier du modèle est dans le dossier des modèles",
    )
    sha = [
        e for e in r.ev.since(seq, "effect_applied") if e["payload"]["effect"] == "model_download"
    ]
    r.check(
        len(sha) == 1 and "sha256" in sha[0]["payload"]["lines"][0],
        "le téléchargement trace le sha256 du fichier",
    )
    build = card.get_by_role("button", name="Construire l'index")
    expect(build).to_be_visible(timeout=5000)
    r.check(
        not r.bricks()["rag"]["available"] and "index absent" in card.inner_text(),
        "modèle présent, index absent : « Construire l'index » proposé",
    )

    # « Construire l'index »: built on the workstation, then the brick loads (it is wanted).
    seq = r.ev.mark()
    build.click()
    r.ev.wait("session_state", seq, lambda p: p["state"] == "index_build", 10)
    r.ev.wait(
        "bricks_changed",
        seq,
        lambda p: next(b for b in p["bricks"] if b["id"] == "rag")["available"],
        60,
    )
    written = [
        e for e in r.ev.since(seq, "effect_applied") if e["payload"]["effect"] == "rag_index_write"
    ]
    r.check(len(written) == 1, "construction réussie : effet rag_index_write tracé")
    r.check(True, "index construit : la brique RAG devient disponible")
    path = r.stack.data_dir / "rag_index.sqlite"
    chunks = rag_index.read_meta(path).chunks if path.is_file() else -1
    nodes = {n["id"]: n for n in r.state()["architecture_changed"]["nodes"]}
    index = nodes.get("file.rag_index") or {}
    r.check(
        index.get("kind") == "file" and f"{chunks} extraits" in (index.get("detail_text") or ""),
        "schéma : le fichier d'index, local, avec son nombre d'extraits",
        str(index.get("detail_text"))[:200],
    )
    chip = r.page.locator('#schema .arch-chip[data-component="rag.retriever"]')
    r.check(
        "📚" in chip.inner_text() and "processus local" in (chip.get_attribute("title") or ""),
        "schéma : la puce 📚 du RAG, son infobulle nomme le modèle d'embedding",
        chip.get_attribute("title") or "",
    )
    expect(r.page.locator('#schema .arch-node[data-component="file.rag_index"]')).to_be_visible()

    # Brick off: the model does not know Exemplia.
    r.set_brick("RAG", False)
    seq = r.ev.mark()
    ended = r.send(RAG_QUESTION)
    r.check(ended["payload"]["status"] == "completed", "tour sans RAG terminé")
    answer = r.last_answer()
    r.check("Je ne connais pas" in answer, "sans RAG : le modèle ne sait pas", answer)
    r.check(not r.ev.since(seq, "rag_search_started"), "sans RAG : aucune recherche")

    # Brick on again, the prompt replayed: the harness searches, the answer cites the document.
    seq = r.ev.mark()
    r.set_brick("RAG", True)
    r.ev.wait(
        "bricks_changed",
        seq,
        lambda p: next(b for b in p["bricks"] if b["id"] == "rag")["available"],
        20,
    )
    seq = r.ev.mark()
    ended = r.replay()
    searched = r.ev.since(seq, "rag_search_ended")
    r.check(
        len(searched) == 1 and searched[0]["payload"]["status"] == "ok",
        "rejeu avec RAG : une recherche, réussie",
    )
    excerpts = searched[0]["payload"]["excerpts"] if searched else []
    r.check(
        len(excerpts) == 3 and excerpts[0]["doc_id"] == "mots_de_passe",
        "3 extraits, le premier tiré de la politique des mots de passe",
        str([(e["doc_id"], e["score"]) for e in excerpts]),
    )
    r.check(
        "Politique des mots de passe" in r.last_answer() and "14 caractères" in r.last_answer(),
        "avec RAG : la réponse s'appuie sur le bon document",
        r.last_answer(),
    )
    body = json.dumps(r.fake_calls()[-1]["messages"], ensure_ascii=False)
    r.check(
        "Extrait 1 — Politique des mots de passe" in body,
        "les extraits partent dans le message de l'utilisateur (corps JSON)",
    )

    # Orchestration: the step, its figure, its unfolded body.
    step = _rag_step(r)
    figure = step.locator(".turn-step-figure").inner_text()
    r.check(
        re.match(r"3 extraits · ", figure) is not None
        and "⚙ harnais" in step.locator(".turn-step-actor").inner_text(),
        "Orchestration : « 📚 Recherche RAG », acteur harnais, « 3 extraits · durée »",
        figure,
    )
    r.check(
        step.locator(".turn-step-tile").get_attribute("data-discipline") == "context",
        "Orchestration : la tuile de « Recherche RAG » est en context engineering (story 33)",
    )
    step.locator(".turn-step-line").click()
    expect(step.locator(".rag-excerpts li")).to_have_count(3, timeout=5000)
    text = step.inner_text()
    r.check(
        RAG_QUESTION in text and "Dans le message de l'utilisateur" in text,
        "l'étape dépliée montre la requête et le placement",
    )
    score = step.locator(".rag-score").first.inner_text()
    r.check(re.fullmatch(r"[01],\d\d", score) is not None, "score affiché à la française", score)
    step.locator(".rag-excerpt-head").first.click()
    expect(r.page.locator('#schema .arch-chip[data-component="rag.retriever"]')).to_have_class(
        re.compile("is-selected"), timeout=5000
    )
    r.check(True, "un clic sur un extrait sélectionne le composant RAG dans le schéma")

    # Contexte LLM: the intro and three excerpts, one section of four segments (story 32),
    # before the message.
    rag = (
        r.page.locator("#ctx .ctx-call")
        .last.locator(".ctx-section")
        .filter(
            has=r.page.locator(".ctx-section-label", has_text=re.compile(r"^Extraits RAG · ≈? ?\d"))
        )
    )
    pieces = (
        rag.first.locator(".ctx-seg:not(.is-template), .ctx-json[data-segment-id]").count()
        if rag.count()
        else 0
    )
    r.check(
        rag.count() == 1 and pieces == 4,
        "Contexte LLM : une section « Extraits RAG », 4 segments (intro et 3 extraits)",
        f"{rag.count()} section(s), {pieces} segments",
    )
    r.shot("22-rag-recherche-et-extraits")

    # « Comparer » the replay with the turn without RAG.
    r.page.locator("#chat .replay-badge").last.click()
    compare = r.page.locator("#ctx")
    headings = compare.locator("h4.turn-compare-brick").all_inner_texts()
    r.check(
        "Comparaison de tours" in compare.inner_text() and "RAG" in headings,
        "« Comparer » : la brique RAG apparaît dans la comparaison, avec ses extraits",
        str(headings),
    )
    compare.get_by_role("button", name="Fermer").click()

    # AD-1: after a reload, the step is rebuilt from the journal.
    r.page.reload()
    r.wait_idle()
    step = _rag_step(r)
    expect(step).to_be_visible(timeout=10_000)
    r.check(
        re.match(r"3 extraits · ", step.locator(".turn-step-figure").inner_text()) is not None,
        "après rechargement, l'étape « Recherche RAG » est toujours là",
    )


RERANK_QUESTION = (
    "Quel plafond de remboursement s'applique à une nuit d'hôtel à Paris chez Exemplia ?"
)


def _rerank_step(r: Run):
    """The last « Reranking » step of Orchestration."""
    name = r.page.locator(".turn-step-name", has_text="Reranking")
    return r.page.locator("#orch-scroll .turn-step", has=name).last


def _rerank_wait_failure(r: Run, seq: int) -> str:
    """Story 4: why the reranker is still not available after its download, on one line (the
    run reports an exception's first line): the `rag.rerank` card's reason, the
    `harness_error`s since `seq`, and the session states the worker went through."""
    try:
        rerank = r.bricks()["rag"].get("rerank") or {}
        reason = f"rerank.available={rerank.get('available')}, raison : {rerank.get('reason_text')}"
    except Exception as exc:  # noqa: BLE001 - the report must not hide the timeout
        reason = f"état des briques illisible ({type(exc).__name__}: {exc})"
    errors = [
        f"{e['payload'].get('message_text', '')} ({e['payload'].get('cause', '')})"
        for e in r.ev.since(seq, "harness_error")
    ]
    states = [e["payload"].get("state") for e in r.ev.since(seq, "session_state")]
    text = (
        f"{reason} · harness_error : {errors or 'aucun'} · états de session : {states or 'aucun'}"
    )
    return " ".join(text.split())


RERANK_FAILURE_MARK = "[reranker-en-panne]"  # as `wavestack_e2e.RERANK_FAILURE_MARK`


def _fake_post(r: Run, path: str, body: dict[str, Any]) -> None:
    """A debug route of the fake OpenAI server (`fake_openai.py`)."""
    with httpx.Client(trust_env=False, timeout=5) as client:
        client.post(f"{r.stack.fake_url}{path}", json=body).raise_for_status()


def _rerank_download_fails(r: Run, card, download) -> None:  # noqa: ANN001
    """E094 (restes différés, story 6): the reranker's file refused by the fake server (503):
    the failure said under the « Reranking » switch, « Télécharger » offered again."""
    _fake_post(r, "/_e2e/reranker_fail", {"fail": True})
    try:
        seq = r.ev.mark()
        download.click()

        def failed() -> list[dict[str, Any]]:
            errors = r.ev.since(seq, "harness_error")
            return [e["payload"] for e in errors if e.get("component") == "rag.reranker"]

        r.poll(lambda: bool(failed()), 30)
        errors = failed()
        notice = card.locator(".brick-suboption .force-error")
        r.poll(lambda: notice.count() == 1 and notice.is_visible(), 10)
        text = notice.inner_text() if notice.count() == 1 else ""
        r.check(
            bool(errors) and errors[0]["message_text"] in text,
            "E094 : téléchargement du reranker refusé (503) : l'échec dit sous l'interrupteur "
            "« Reranking »",
            f"{text[:200]} · harness_error {[e['message_text'] for e in errors]}",
        )
        expect(download).to_be_visible(timeout=10_000)
        rerank = r.bricks()["rag"].get("rerank") or {}
        r.check(
            not rerank.get("available") and download.is_enabled(),
            "après l'échec : « Télécharger le modèle de reranking » de nouveau proposé",
            str(rerank)[:200],
        )
    finally:
        _fake_post(r, "/_e2e/reranker_fail", {"fail": False})


def _rerank_download_stopped(r: Run, card, download) -> None:  # noqa: ANN001
    """Finition V1 (#20, review of PR #21, 2026-10-04): the reranker's file served a byte a
    second, « Arrêter » once its `.part` is open: a neutral line under the « Reranking »
    switch, in place of the earlier failure's red one; no `harness_error`, no `.part` left,
    « Télécharger » offered again."""
    folder = r.stack.data_dir / "models" / "reranker"
    _fake_post(r, "/_e2e/reranker_slow", {"slow": True})
    try:
        seq = r.ev.mark()
        download.click()
        r.ev.wait("session_state", seq, lambda p: p["state"] == "download", 10)
        opened, _ = r.poll(lambda: bool(list(folder.rglob("*.part"))), 10)
        r.check(opened, "#20 (Reranking) : le fichier .part existe avant « Arrêter »")
        r.api("POST", "/api/intentions/stop")
        stopped = r.ev.wait(
            "effect_applied", seq, lambda p: p["effect"] == "model_download_stopped", 20
        )
        r.ev.wait("session_state", seq, lambda p: p["state"] == "idle", 20)
        note = card.locator(".brick-suboption .brick-note", has_text="arrêté")
        expect(note).to_contain_text("le fichier en cours est supprimé", timeout=5000)
        errors = [e for e in r.ev.since(seq, "harness_error") if e.get("component")]
        r.check(
            not errors
            and stopped.get("component") == "rag.reranker"
            and card.locator(".brick-suboption .force-error").count() == 0
            and "modèle de reranking" in note.inner_text(),
            "#20 (Reranking) : téléchargement arrêté, ligne neutre sous l'interrupteur, à la "
            "place de la ligne rouge de l'échec, sans erreur",
            f"{note.inner_text()} · {stopped.get('component')} · erreurs {len(errors)}",
        )
        left = list(folder.rglob("*.part")) if folder.exists() else []
        expect(download).to_be_visible(timeout=10_000)
        r.check(
            not left and download.is_enabled(),
            "#20 (Reranking) : aucun .part laissé, « Télécharger » de nouveau proposé",
            str(left),
        )
    finally:
        _fake_post(r, "/_e2e/reranker_slow", {"slow": False})


def _rerank_step_failed(r: Run) -> None:
    """E094: the fake reranker breaks down while it scores (`RERANK_FAILURE_MARK` in the
    question): the « Reranking » step in error, unfolded and kept so, its error said; the
    turn goes on with the embedding's first excerpts."""
    seq = r.ev.mark()
    ended = r.send(f"{RERANK_QUESTION} {RERANK_FAILURE_MARK}")
    reranked = [e["payload"] for e in r.ev.since(seq, "rag_rerank_ended")]
    searched = r.ev.since(seq, "rag_search_ended")
    first = [e["title_text"] for e in searched[0]["payload"]["excerpts"][:3]] if searched else []
    body = json.dumps(r.fake_calls()[-1]["messages"], ensure_ascii=False)
    error_text = (reranked[0].get("error_text") or "") if reranked else ""
    r.check(
        ended["payload"]["status"] == "completed"
        and len(reranked) == 1
        and reranked[0]["status"] == "error"
        and "reranker en panne (e2e)" in error_text
        and body.count("Extrait ") == 3
        and all(f"Extrait {i} — {t}" in body for i, t in enumerate(first, 1)),
        "reranker en panne : le tour continue avec les 3 premiers extraits de l'embedding, "
        "dans leur ordre ; rag_rerank_ended en erreur",
        f"{ended['payload']['status']} · {error_text[:160]}",
    )
    _turn_rendered_ended(r, ended["turn_id"])
    step = _rerank_step(r)
    line = step.locator(".turn-step-line")
    body = step.locator(".turn-step-body")
    figure = step.locator(".turn-step-figure").inner_text()
    said = body.inner_text() if body.count() else ""
    r.check(
        "tone-error" in (step.get_attribute("class") or "")
        and line.get_attribute("aria-expanded") == "true"
        and figure == _ui_catalogue("fr")["main.orch.error"]
        and "reranker en panne (e2e)" in said,
        "E094 : étape « Reranking » en erreur dans le rail (ton d'erreur, dépliée, l'erreur dite)",
        f"{step.get_attribute('class')} · {line.get_attribute('aria-expanded')} · {figure} · "
        f"{said[:160]}",
    )


def s_rag_rerank(r: Run) -> None:
    """Story 16, after `rag` (index built, embedding model there): the « Reranking »
    sub-option of the RAG card, its model absent (the RAG goes on without it), then
    downloaded; a turn whose step shows the order before and after, the kept excerpts in the
    message sent, the reranker in the schema; switched off: pending, no step; a reload."""
    r.launch("rag_rerank")
    program = r.state()["scenario_changed"]["program"]
    scenario = next(
        s for m in program["modules"] for s in m["scenarios"] if s["id"] == "rag_rerank"
    )
    r.check(
        scenario["prompts"][0] == RERANK_QUESTION and "{" not in scenario["description_text"],
        "le premier prompt du scénario est celui que le parcours joue ; consigne chiffrée",
        scenario["description_text"][:160],
    )
    card = r.card("RAG")
    toggle = card.locator('input[data-focus-key="option:rag:rerank"]')
    download = card.get_by_role("button", name=re.compile("Télécharger le modèle de reranking"))
    expect(download).to_be_visible(timeout=10_000)
    rag = r.bricks()["rag"]
    rerank = rag.get("rerank") or {}
    r.check(
        rag["available"]
        and rerank.get("enabled")
        and not rerank.get("available")
        and (rerank.get("download") or {}).get("target") == "rag_reranker",
        "scénario : sous-option cochée, modèle de reranking absent, « Télécharger » proposé, "
        "brique RAG disponible",
        str(rerank)[:300],
    )
    reason = card.locator(".brick-suboption .brick-reason").inner_text()
    r.check(
        toggle.is_checked() and "modèle absent" in reason and "sans reranking" in reason,
        "la carte RAG : case « Reranking » cochée, raison « modèle absent »",
        reason[:200],
    )

    # Without its model, the RAG searches as before: no reranking step.
    seq = r.ev.mark()
    ended = r.send(RERANK_QUESTION)
    r.check(ended["payload"]["status"] == "completed", "tour sans modèle de reranking terminé")
    searched = r.ev.since(seq, "rag_search_started")
    r.check(
        len(searched) == 1
        and searched[0]["payload"]["top_k"] == 3
        and not r.ev.since(seq, "rag_rerank_started"),
        "sans modèle de reranking : recherche de 3 extraits, aucune étape « Reranking »",
    )

    _rerank_download_fails(r, card, download)
    _rerank_download_stopped(r, card, download)

    # « Télécharger le modèle de reranking »: the file, then the reranker loads.
    seq = r.ev.mark()
    download.click()
    r.ev.wait("session_state", seq, lambda p: p["state"] == "download", 10)
    try:
        r.ev.wait(
            "bricks_changed",
            seq,
            lambda p: (
                (next(b for b in p["bricks"] if b["id"] == "rag").get("rerank") or {}).get(
                    "available"
                )
                is True
            ),
            30,
        )
    except TimeoutError as exc:
        # Story 4 (deferred work): the card's reason and the harness errors tell a budget
        # refusal from a worker that never loaded. The cause observed was neither: the worker
        # loaded at once, but its « available » card was lost by the stream (the journal
        # notified two threads out of `seq` order) and the download thread's « Chargement »,
        # built before, was emitted last; both fixed in the application. Delay unchanged.
        raise TimeoutError(f"{exc} · {_rerank_wait_failure(r, seq)}") from None
    r.check(
        (r.stack.data_dir / "models" / "reranker" / "fake-e2e.gguf").is_file(),
        "téléchargement réussi : le fichier du reranker est dans le dossier des modèles",
    )
    sha = [
        e for e in r.ev.since(seq, "effect_applied") if e["payload"]["effect"] == "model_download"
    ]
    r.check(
        len(sha) == 1 and "reranker" in sha[0]["payload"]["lines"][0],
        "le téléchargement trace le fichier du reranker et son sha256",
        str(sha[0]["payload"]["lines"] if sha else None),
    )
    expect(download).to_be_hidden(timeout=5000)
    r.check(True, "la carte ne propose plus « Télécharger le modèle de reranking »")

    # The prompt replayed: 8 candidates, reranked; the first three go to the message.
    seq = r.ev.mark()
    ended = r.replay()
    r.check(ended["payload"]["status"] == "completed", "rejeu avec reranking terminé")
    search = r.ev.since(seq, "rag_search_ended")
    reranked = r.ev.since(seq, "rag_rerank_ended")
    found = search[0]["payload"]["excerpts"] if search else []
    after = reranked[0]["payload"]["excerpts"] if reranked else []
    r.check(
        len(found) == 8 and len(after) == 8 and reranked[0]["payload"]["status"] == "ok",
        "recherche de 8 candidats, puis reranking des 8",
        f"{len(found)} / {len(after)}",
    )
    first = after[0] if after else {}
    r.check(
        first.get("doc_id") == "deplacements" and first.get("before", 1) > 3,
        "le reranker remonte « Déplacements » en tête (hors des 3 premiers de l'embedding)",
        str([(e["doc_id"], e["before"], e["score"]) for e in after]),
    )
    body = json.dumps(r.fake_calls()[-1]["messages"], ensure_ascii=False)
    r.check(
        "Extrait 1 — Déplacements et notes de frais" in body and body.count("Extrait ") == 3,
        "seuls les 3 premiers après reranking partent dans le message (corps JSON)",
    )

    # Orchestration: the step, its figure, the order before and after.
    step = _rerank_step(r)
    figure = step.locator(".turn-step-figure").inner_text()
    r.check(
        re.match(r"3 gardés sur 8 · ", figure) is not None
        and "⚙ harnais" in step.locator(".turn-step-actor").inner_text(),
        "Orchestration : « ↕️ Reranking », acteur harnais, « 3 gardés sur 8 · durée »",
        figure,
    )
    search_figure = _rag_step(r).locator(".turn-step-figure").inner_text()
    r.check(
        re.match(r"8 extraits · ", search_figure) is not None,
        "l'étape « Recherche RAG » qui précède montre les 8 candidats",
        search_figure,
    )
    step.locator(".turn-step-line").click()
    expect(step.locator(".rerank-after li")).to_have_count(8, timeout=5000)
    r.check(
        step.locator(".rerank-before li").count() == 8
        and step.locator(".rerank-after li.is-kept").count() == 3,
        "l'étape dépliée montre l'ordre avant (8) et après (8), dont 3 gardés",
    )
    move = step.locator(".rerank-after .rerank-move").first.inner_text()
    text = step.inner_text()
    r.check(
        move.startswith("↑") and "Avant (embedding)" in text and "Après (reranker)" in text,
        "le premier extrait après reranking est marqué comme remonté",
        move,
    )
    step.locator(".rerank-after .rag-excerpt-head").first.click()
    chip = r.page.locator('#schema .arch-chip[data-component="rag.reranker"]')
    expect(chip).to_have_class(re.compile("is-selected"), timeout=5000)
    r.check(
        "↕" in chip.inner_text() and "Modèle de reranking" in (chip.get_attribute("title") or ""),
        "un clic sur un extrait sélectionne la puce du reranker, qui nomme son modèle",
        chip.get_attribute("title") or "",
    )
    r.shot("25-reranking-avant-apres")

    # AD-1: after a reload, the reranking step is rebuilt from the journal.
    r.page.reload()
    r.wait_idle()
    expect(_rerank_step(r)).to_be_visible(timeout=10_000)
    r.check(
        re.match(r"3 gardés sur 8 · ", _rerank_step(r).locator(".turn-step-figure").inner_text())
        is not None,
        "après rechargement, l'étape « Reranking » est toujours là",
    )
    _rerank_step_failed(r)

    # Switched off: « Prend effet au prochain tour », no reranker in the schema, no step.
    seq = r.ev.mark()
    toggle.click()
    r.ev.wait("bricks_changed", seq, timeout=10)
    expect(card.locator(".brick-pending")).to_be_visible(timeout=5000)
    expect(chip).to_have_count(0, timeout=5000)
    r.check(True, "case décochée : « Prend effet au prochain tour », le reranker quitte le schéma")
    seq = r.ev.mark()
    r.replay()
    r.check(
        not r.ev.since(seq, "rag_rerank_started")
        and r.ev.since(seq, "rag_search_started")[0]["payload"]["top_k"] == 3,
        "rejeu sans reranking : 3 extraits, aucune étape « Reranking »",
    )

    # Story 22 (M3): « Reranking » checked, then the RAG brick off: greyed, disabled, the
    # reason on hover; the brick back on, the switch is active again, still checked.
    seq = r.ev.mark()
    toggle.click()
    r.ev.wait("bricks_changed", seq, timeout=10)
    r.set_brick("RAG", False)
    row = card.locator("label.brick-option:has(input[data-focus-key='option:rag:rerank'])")
    look = toggle.evaluate("t => getComputedStyle(t).backgroundColor")
    primary = r.page.evaluate(_CSS_COLOR_JS, "--color-primary")
    muted = r.page.evaluate(_CSS_COLOR_JS, "--color-muted")
    title = row.get_attribute("title") or ""
    r.check(
        toggle.is_checked()
        and toggle.is_disabled()
        and look != primary
        and look == muted
        and "Activez la brique RAG" in title
        and toggle.get_attribute("aria-description") == title,
        "brique RAG éteinte : « Reranking » coché mais grisé, désactivé, raison au survol",
        f"fond {look} (violet {primary}) · « {title} »",
    )
    r.shot("27-reranking-brique-rag-eteinte")
    r.set_brick("RAG", True)
    r.check(
        toggle.is_checked() and toggle.is_enabled() and not row.get_attribute("title"),
        "brique RAG rallumée : « Reranking » de nouveau réglable, toujours coché",
    )


def _compression_step(r: Run):
    """The last « Compression (…) » step of Orchestration."""
    name = r.page.locator(".turn-step-name", has_text="Compression (")
    return r.page.locator("#orch-scroll .turn-step", has=name).last


def s_mcp_lab(r: Run) -> None:
    """Story 6 of 2026-09-30, then lot 4 of 2026-10-04 (« Atelier MCP en séquence », AD-27,
    AD-28): the four panes, the glossary's handshake drawn arrow by arrow (five captured
    methods, the tabs 🔧 2 · 📄 1 · 💬 1), the stepper ◀ ▶ and the progressive discovery
    (the columns keep their place), a call by hand and `isError`, a resource then sent to the
    model, a prompt then sent to the model, « Par le modèle » on the fake cloud model (the
    host between the model and the server, the main gauge untouched), the reload rebuilding
    the same arrows, the panes hidden and focused. Captures 61 to 63. Back to `/`."""
    page = r.page
    page.set_viewport_size({"width": 1600, "height": 1000})
    errors: list[str] = []
    listener = lambda e: errors.append(str(e))  # noqa: E731
    page.on("pageerror", listener)
    try:
        _mcp_lab(r, errors)
    finally:
        page.remove_listener("pageerror", listener)
        if page.locator("#theme-picker").count():
            _pick_theme(page, "system")
        r.goto_app()


def _goto_mcp(r: Run) -> None:
    r.page.goto(f"{r.stack.app_url}/mcp")
    expect(r.page.locator("body[data-mcp-ready]")).to_be_attached(timeout=15_000)


def _mcp_rows(r: Run, kind: str | None = None) -> list[dict[str, str | None]]:
    """The arrows of the Séquence, in order: their kind, method, ends, and whether shown."""
    selector = "#mcp-seq li.mcp-row" + (f'[data-kind="{kind}"]' if kind else "")
    return r.page.locator(selector).evaluate_all(
        """items => items.map(i => ({key: i.dataset.key, kind: i.dataset.kind,
            method: i.dataset.method ?? null, from: i.dataset.from, to: i.dataset.to,
            error: i.classList.contains('is-error'),
            shown: !i.classList.contains('mcp-ahead')
              && !i.classList.contains('diagram-unrevealed')}))"""
    )


def _mcp_click(r: Run, selector: str) -> None:
    """A command, once the page made it available (`aria-disabled`, never `disabled`)."""
    button = r.page.locator(selector)
    expect(button).to_have_attribute("aria-disabled", "false", timeout=20_000)
    button.click()


def _mcp_connect(r: Run, server: str, timeout: float = 60) -> dict[str, Any]:
    page = r.page
    page.locator(f'#mcp-servers input[value="{server}"]').check()
    seq = r.ev.mark()
    _mcp_click(r, "#mcp-connect")
    ended = r.ev.wait("mcp_lab_connect_ended", seq, timeout=timeout)["payload"]
    expect(page.locator("#mcp-busy")).to_be_hidden(timeout=15_000)
    return ended


def _mcp_heads_x(r: Run) -> list[float]:
    return r.page.locator("#mcp-heads .mcp-head").evaluate_all(
        "heads => heads.map(h => Math.round(h.getBoundingClientRect().left))"
    )


def _mcp_revealed_heads(r: Run) -> list[str]:
    return r.page.locator("#mcp-heads .mcp-head:not(.diagram-unrevealed)").evaluate_all(
        "heads => heads.map(h => h.dataset.col)"
    )


def _mcp_lab(r: Run, errors: list[str]) -> None:
    page = r.page
    r.goto_app()
    r.wait_idle()
    if (r.state().get("active_model") or {}).get("ref") != MODEL_ENTRY_ID:
        _pick_model(r, A_LABEL)
    brick_before = r.bricks()["mcp"]
    # (1) The links, the page and its four panes.
    link = page.locator('.site-nav a[href="/mcp"]')
    r.check(
        link.is_visible() and link.inner_text() == "MCP",
        "barre commune : lien « MCP » visible, entier, vers /mcp",
        link.inner_text() if link.count() else "absent",
    )
    ok, detail = _bar_fits(r)
    r.check(ok, "barre commune entière avec cinq onglets, sur une ligne, à 1600 × 1000", detail)
    r.check(
        page.locator('a.brick-workshop-link[href="/mcp"]').count() == 1,
        "la carte de la brique MCP renvoie à l'atelier MCP",
    )
    link.click()
    page.wait_for_url("**/mcp")
    expect(page.locator("body[data-mcp-ready]")).to_be_attached(timeout=10_000)
    panes = page.locator("#layout .pane").evaluate_all("ps => ps.map(p => p.dataset.pane)")
    r.check(
        page.locator("nav.site-nav a[aria-current=page]").inner_text() == "MCP"
        and page.title() == "WaveStack — Atelier MCP"
        and page.locator("h1").inner_text() == "Atelier MCP"
        and panes == ["servers", "seq", "model", "arch"]
        and not _site_nav_problems(r),
        "/mcp : barre commune, « MCP » courant, titre « Atelier MCP », quatre volets",
        f"{panes} {_site_nav_problems(r)}",
    )
    servers = page.locator("#mcp-servers .mcp-server").evaluate_all(
        "items => items.map(i => i.dataset.server)"
    )
    r.check(servers == ["local", "datagouv", "mslearn"], "/mcp : les trois serveurs", str(servers))
    r.check(
        page.locator("#mcp-seq-empty").is_visible()
        and not _mcp_revealed_heads(r)
        and page.locator("#mcp-arch-empty").is_visible(),
        "avant connexion : la Séquence invite à se connecter, aucune colonne, Architecture vide",
    )

    # (2) The glossary's handshake: five methods captured, the lists, the tabs.
    ended = _mcp_connect(r, "local")
    r.check(ended["status"] == "ok", "poignée de main avec le glossaire local", str(ended)[:200])
    expect(page.locator('#mcp-seq li.mcp-row[data-key$=":lists"]')).to_be_attached(timeout=10_000)
    rpc = _mcp_rows(r, "rpc")
    methods = [row["method"] for row in rpc]
    r.check(
        methods
        == [
            "initialize",
            "initialize",
            "notifications/initialized",
            "tools/list",
            "tools/list",
            "resources/list",
            "resources/list",
            "prompts/list",
            "prompts/list",
        ]
        and [(row["from"], row["to"]) for row in rpc[:2]]
        == [("client", "server"), ("server", "client")],
        "poignée de main : initialize, notifications/initialized, tools/list, resources/list, "
        "prompts/list, capturés, client ↔ serveur",
        str(methods),
    )
    kinds = [row["kind"] for row in _mcp_rows(r)]
    r.check(
        kinds[0] == "host" and kinds[-1] == "host",
        "flèches déduites : Hôte → Client « lance le serveur », Client → Hôte "
        "« 🔧 2 · 📄 1 · 💬 1 »",
        str(kinds),
    )
    tabs = [page.locator(f"#mcp-tab-{k}").inner_text() for k in ("tools", "resources", "prompts")]
    r.check(
        tabs[0].endswith("Outils 2")
        and tabs[1].endswith("Ressources 1")
        and tabs[2].endswith("Prompts 1"),
        "onglets des primitives : 🔧 Outils 2 · 📄 Ressources 1 · 💬 Prompts 1",
        str(tabs),
    )
    full = page.locator("#mcp-model-body .mcp-total-number").inner_text()
    page.locator('#mcp-doc-mode [data-value="lazy"]').click()
    lazy = page.locator("#mcp-model-body .mcp-total-number").inner_text()
    page.locator('#mcp-doc-mode [data-value="full"]').click()
    r.check(
        full != lazy and full != "—",
        "ce que le modèle voit : le bloc « outils », son total en documentation complète puis "
        "en lazy loading",
        f"{full} / {lazy}",
    )

    # (3) The stepper: back to the first step, the columns appear one by one, in place.
    steps = page.locator("#mcp-stepper .diagram-step-position").inner_text()
    last_x = _mcp_heads_x(r)
    prev = page.locator("#mcp-stepper .diagram-step-prev")
    for _ in range(40):
        if prev.get_attribute("aria-disabled") == "true":
            break
        prev.click()
    first_heads = _mcp_revealed_heads(r)
    first_rows = [row["key"] for row in _mcp_rows(r) if row["shown"]]
    first_x = _mcp_heads_x(r)
    page.locator("#mcp-stepper .diagram-step-next").click()
    page.locator("#mcp-stepper .diagram-step-next").click()
    third_heads = _mcp_revealed_heads(r)
    status = page.locator("#mcp-stepper .diagram-step-status").inner_text()
    r.check(
        first_heads == ["host", "client"]
        and len(first_rows) == 1
        and "server" in third_heads
        and first_x == last_x
        and status.startswith("Étape 3 sur"),
        "stepper : à l'étape 1, l'hôte et le client seuls ; le serveur apparaît ensuite ; les "
        "colonnes ne bougent pas ; l'étape annoncée",
        f"{steps} · {first_heads} → {third_heads} · {status}",
    )
    page.locator("#mcp-stepper .diagram-step-live").click()
    r.shot("61-atelier-mcp-poignee-de-main")

    # (4) A call by hand, then an unknown term: `isError`, a result, a red arrow.
    page.locator("#mcp-tab-tools").click()
    page.locator("#mcp-call-tool").select_option("define_term")
    page.locator('#mcp-call-fields input[name="term"]').fill("harnais")
    seq = r.ev.mark()
    _mcp_click(r, "#mcp-call-run")
    call = r.ev.wait("mcp_lab_call_ended", seq, timeout=30)["payload"]
    expect(page.locator("#mcp-model-body .mcp-context-block.is-result")).to_be_visible(
        timeout=10_000
    )
    ghosts = len([row for row in _mcp_rows(r, "ghost")])
    r.check(
        call["status"] == "ok" and not call["is_error"] and ghosts == 5,
        "appel à la main : tools/call capturé, résultat réinjecté, cinq fantômes (pas de modèle)",
        f"{call['status']} · {ghosts}",
    )
    page.locator('#mcp-call-fields input[name="term"]').fill("xyz")
    seq = r.ev.mark()
    _mcp_click(r, "#mcp-call-run")
    unknown = r.ev.wait("mcp_lab_call_ended", seq, timeout=30)["payload"]
    expect(page.locator("#mcp-seq li.mcp-row.is-error")).not_to_have_count(0, timeout=10_000)
    r.check(
        unknown["status"] == "ok"
        and unknown["is_error"] is True
        and unknown["connection"] == "open",
        "terme inconnu : isError, un résultat (statut ok), flèche rouge, connexion ouverte",
        str(unknown)[:200],
    )
    r.shot("62-atelier-mcp-appel")

    # (5) A resource read, then sent to the model with a question.
    page.locator("#mcp-tab-resources").click()
    seq = r.ev.mark()
    _mcp_click(r, "#mcp-read")
    read = r.ev.wait("mcp_lab_read_ended", seq, timeout=30)["payload"]
    seq = r.ev.mark()
    _mcp_click(r, "#mcp-read-send")
    asked = r.ev.wait("mcp_lab_ask_ended", seq, timeout=60)["payload"]
    sent = [e["payload"] for e in r.ev.since(seq, "mcp_lab_model_started")]
    r.check(
        read["status"] == "ok"
        and asked["status"] == "ok"
        and sent
        and [s["part"] for s in sent[0]["sends"]][:2] == ["resource", "question"],
        "ressource lue puis envoyée au modèle avec la question",
        f"{read['status']} · {asked.get('outcome')} · {sent[0]['sends'] if sent else None}"[:300],
    )

    # (6) A prompt got, then sent to the model as the user's message.
    page.locator("#mcp-tab-prompts").click()
    seq = r.ev.mark()
    _mcp_click(r, "#mcp-prompt-get")
    got = r.ev.wait("mcp_lab_prompt_ended", seq, timeout=30)["payload"]
    seq = r.ev.mark()
    _mcp_click(r, "#mcp-prompt-send")
    asked = r.ev.wait("mcp_lab_ask_ended", seq, timeout=60)["payload"]
    sent = [e["payload"] for e in r.ev.since(seq, "mcp_lab_model_started")]
    r.check(
        got["status"] == "ok"
        and "hook" in got["messages"][0]["text"]
        and asked["status"] == "ok"
        and sent
        and sent[0]["sends"][0]["part"] == "prompt",
        "prompt explain_term(term = « hook ») obtenu, puis envoyé au modèle",
        f"{got['status']} · {asked.get('outcome')}",
    )

    # (7) « Par le modèle » on the fake cloud model: the host between the model and the server.
    gauge_before = {
        k: r.state().get(k) for k in ("context_rendered", "context_reconciled", "context_preview")
    }
    page.locator("#mcp-tab-tools").click()
    page.locator('#mcp-call-mode [data-value="model"]').click()
    page.locator("#mcp-ask-question").fill("Que veut dire MCP ?")
    seq = r.ev.mark()
    _mcp_click(r, "#mcp-ask-send")
    asked = r.ev.wait("mcp_lab_ask_ended", seq, timeout=90)["payload"]
    expect(page.locator("#mcp-busy")).to_be_hidden(timeout=15_000)
    events = r.ev.since(seq)
    tool = [e for e in events if e["kind"] == "mcp_lab_call_ended" and e["step_id"].endswith(".t1")]
    model_rows = [row for row in _mcp_rows(r) if "model" in (row["from"], row["to"])]
    gauge_after = {
        k: r.state().get(k) for k in ("context_rendered", "context_reconciled", "context_preview")
    }
    r.check(
        asked["status"] == "ok"
        and asked["outcome"] == "answer"
        and asked["calls"] == 2
        and tool
        and tool[0]["payload"]["by"] == "model",
        "par le modèle : appel au modèle, tools/call par l'hôte (mcp{n}.t1), réponse finale",
        str(asked)[:200],
    )
    r.check(
        model_rows and all({row["from"], row["to"]} <= {"model", "host"} for row in model_rows),
        "le modèle ne parle qu'à l'hôte : aucune flèche entre le modèle et le client ou le serveur",
        str([(row["from"], row["to"]) for row in model_rows]),
    )
    r.check(
        gauge_after == gauge_before,
        "la jauge de l'atelier principal ne bouge pas (contexte mcp_lab écarté)",
    )
    light = _contrast_sweep(r, ["main", "nav.site-nav"])
    _pick_theme(page, "dark")
    dark = _contrast_sweep(r, ["main", "nav.site-nav"])
    _pick_theme(page, "system")
    r.check(not light and not dark, "/mcp : contrastes AA en clair et en sombre", str(light + dark))
    r.shot("63-atelier-mcp-par-le-modele")

    # (8) The reload: the same arrows, the phases folded but the last, live.
    before = [(row["key"], row["kind"], row["error"]) for row in _mcp_rows(r)]
    phases = page.locator("#mcp-seq .mcp-phase").count()
    _goto_mcp(r)
    expect(page.locator("#mcp-seq .mcp-phase")).to_have_count(phases, timeout=10_000)
    after = [(row["key"], row["kind"], row["error"]) for row in _mcp_rows(r)]
    folded = page.locator('#mcp-seq .mcp-phase-toggle[aria-expanded="false"]').count()
    r.check(
        after == before
        and folded == phases - 1
        and page.locator("#mcp-stepper .diagram-step-live").get_attribute("aria-pressed") == "true",
        "page rechargée : last_session rejoué, mêmes flèches, phases repliées sauf la dernière, "
        "en direct",
        f"{len(before)} / {len(after)} flèches · {folded} repliées sur {phases}",
    )

    # (9) The panes: « Ce que le modèle voit » hidden, its chip, shown again; Séquence focused.
    page.locator('.pane[data-pane="model"] [data-action="hide"]').click()
    chip = page.locator("#mcp-pane-chips .pane-chip")
    hidden_ok = page.locator('.pane[data-pane="model"]').is_hidden() and chip.count() == 1
    chip.first.click()
    page.locator('.pane[data-pane="seq"] [data-action="focus"]').click()
    focused = page.locator('.pane[data-pane="seq"].is-focused').count() == 1
    page.locator('.pane[data-pane="seq"] [data-action="focus"]').click()
    r.check(
        hidden_ok
        and page.locator('.pane[data-pane="model"]').is_visible()
        and focused
        and page.locator('.pane[data-pane="seq"] [data-action="hide"]').count() == 0,
        "volets : « — » masque, la puce « + Ce que le modèle voit » réaffiche, ⛶ met la "
        "Séquence en focus, la Séquence ne se masque pas",
    )
    page.locator('#mcp-arch-switch [data-view="before"]').click()
    before_view = (
        page.locator("#mcp-arch-before").is_visible() and page.locator("#mcp-arch").is_hidden()
    )
    page.locator('#mcp-arch-switch [data-view="after"]').click()
    r.check(before_view, "Architecture : la vue « Avant MCP », puis « Avec MCP »")
    r.check(not errors, "/mcp : aucune erreur JavaScript", str(errors)[:300])

    # (10) The brick, untouched by the workshop.
    r.goto_app()
    after_brick = r.bricks()["mcp"]
    r.check(
        (after_brick.get("wanted"), after_brick.get("options"))
        == (brick_before.get("wanted"), brick_before.get("options")),
        "la brique MCP de l'atelier est inchangée",
    )


def s_mcp_lab_page(r: Run) -> None:
    """Restes du 2026-10-01 (story 6), then lot 4 of 2026-10-04: what `/mcp` does on its own
    side. The state unreachable (`page.route`), then back; « Occupé » during a real turn of
    the workshop; « Arrêter » pressed during the glossary's handshake; data.gouv.fr cut by the
    stack (its outbound request in the detail, the failure kept on its card); then a
    `last_session` served by `page.route` (a public server: ⊘ on its resources and prompts, a
    tool with an object, an integer and a boolean parameter, a bounded call): the fields, an
    invalid JSON said without a request, the arguments sent. Back to `/`."""
    page = r.page
    page.set_viewport_size({"width": 1600, "height": 1000})
    errors: list[str] = []
    listener = lambda e: errors.append(str(e))  # noqa: E731
    page.on("pageerror", listener)
    try:
        _mcp_lab_page(r, errors)
    finally:
        page.remove_listener("pageerror", listener)
        for pattern in ("**/api/mcp_lab", "**/api/intentions/mcp_lab_call"):
            page.unroute(pattern)
        r.goto_app()


def _mcp_busy_checks(r: Run) -> None:
    """A turn of the workshop running: « Occupé », « Se connecter » unavailable (focus kept),
    a direct connection refused, « Arrêter » of the MCP workshop unavailable."""
    page = r.page
    busy = page.locator("#mcp-busy")
    expect(busy).to_be_visible(timeout=10_000)
    refused = r.api("POST", "/api/intentions/mcp_lab_connect", {"server": "local"})
    connect = page.locator("#mcp-connect")
    r.check(
        "Un tour est en cours" in busy.inner_text()
        and connect.get_attribute("aria-disabled") == "true"
        and "Un tour est en cours" in (connect.get_attribute("title") or "")
        and page.locator("#mcp-stop").get_attribute("aria-disabled") == "true"
        and refused.status_code == 409,
        "tour de l'atelier en cours : bandeau « Occupé » avec la raison, « Se connecter » "
        "indisponible (aria-disabled), connexion directe 409, « Arrêter » indisponible",
        f"{busy.inner_text()} · {refused.status_code}",
    )


def _mcp_stop_during_handshake(r: Run) -> bool:
    """« Se connecter » then « Arrêter » as soon as it is available, at most three times (the
    handshake can win the race); whether the stop was seen, checked either way."""
    page = r.page
    stopped, attempts = None, 0
    page.locator('#mcp-servers input[value="local"]').check()
    while stopped is None and attempts < 3:
        attempts += 1
        seq = r.ev.mark()
        _mcp_click(r, "#mcp-connect")
        stop = page.locator("#mcp-stop")
        try:
            expect(stop).to_have_attribute("aria-disabled", "false", timeout=5000)
            stop.click()
        except Exception:  # noqa: BLE001 - the handshake ended first
            pass
        ended = r.ev.wait("mcp_lab_connect_ended", seq, timeout=60)["payload"]
        if ended["status"] != "ok":
            stopped = ended
        expect(page.locator("#mcp-busy")).to_be_hidden(timeout=15_000)
    if stopped is None:
        r.check(False, "« Arrêter » pressé pendant la poignée de main", f"{attempts} essai(s)")
        return False
    state = r.api("GET", "/api/mcp_lab").json()
    meta = page.locator("#mcp-seq .mcp-phase").last.locator(".mcp-phase-meta")
    expect(meta).to_contain_text("arrêtée", timeout=10_000)
    r.check(
        stopped["status"] == "cancelled"
        and stopped["error_kind"] == "stopped"
        and state["open_server"] is None
        and state["session_state"]["state"] == "idle"
        and page.locator(".mcp-badge-state.is-open").count() == 0,
        "« Arrêter » pendant la poignée de main : phase « arrêtée par l'utilisateur », aucune "
        "connexion ouverte, session en idle",
        f"{attempts} essai(s) · {meta.inner_text()[:120]}",
    )
    return True


def _mcp_lab_page(r: Run, errors: list[str]) -> None:
    page = r.page
    r.goto_app()
    r.wait_idle()
    if (r.state().get("active_model") or {}).get("ref") != MODEL_ENTRY_ID:
        _pick_model(r, A_LABEL)

    # (1) The workshop's state unreachable: said, then the page comes back by itself.
    page.route("**/api/mcp_lab", lambda route: route.abort())
    page.goto(f"{r.stack.app_url}/mcp")
    alert = page.locator("#mcp-content-error")
    expect(alert).to_be_visible(timeout=10_000)
    said = alert.inner_text()
    ready_meanwhile = page.locator("body[data-mcp-ready]").count()
    page.unroute("**/api/mcp_lab")
    expect(page.locator("body[data-mcp-ready]")).to_be_attached(timeout=15_000)
    r.check(
        said.startswith("Atelier MCP indisponible (") and not ready_meanwhile and alert.is_hidden(),
        "/mcp injoignable : l'alerte le dit, la page se rétablit seule (nouvel essai)",
        said,
    )

    # (2) A real turn of the workshop: « Occupé », the commands unavailable.
    seq = r.ev.mark()
    r.api("POST", "/api/intentions/send", {"message": "Explique le harnais [lent] [long]"})
    r.ev.wait("model_first_token", seq, timeout=20)
    try:
        _mcp_busy_checks(r)
    finally:  # the turn never outlives this step, even when a check raised
        r.api("POST", "/api/intentions/stop")
        r.ev.wait("turn_ended", seq, timeout=30)
    expect(page.locator("#mcp-busy")).to_be_hidden(timeout=10_000)
    expect(page.locator("#mcp-connect")).to_have_attribute("aria-disabled", "false", timeout=10_000)

    # (3) « Arrêter » pressed during the handshake.
    if not _mcp_stop_during_handshake(r):
        return

    # (4) data.gouv.fr, the network cut by the stack: the request leaves through the guard,
    # shown in its detail, and fails; the failure stays on its card.
    ended = _mcp_connect(r, "datagouv", timeout=90)
    initialize = page.locator('#mcp-seq li.mcp-row[data-method="initialize"]').last
    expect(initialize).to_have_class(re.compile(r"\bis-error\b"), timeout=10_000)
    initialize.locator("button.mcp-arrow").click()
    detail = initialize.locator(".mcp-message-detail")
    outbound = detail.locator(".mcp-outbound")
    card = page.locator('#mcp-servers .mcp-server[data-server="datagouv"]')
    r.check(
        ended["status"] == "error"
        and ended["connection"] == "closed"
        and outbound.count() == 1
        and "POST https://mcp.data.gouv.fr/mcp" in outbound.inner_text()
        and card.locator(".mcp-badge-state.is-failed").count() == 1
        and "reste disponible" in page.locator("#mcp-server-note").inner_text()
        and page.locator("#mcp-tab-tools").count() == 0,
        "data.gouv.fr hors réseau : requête sortante POST dans l'encart, initialize en rouge, "
        "carte « injoignable », le glossaire reste disponible, aucun onglet",
        f"{ended.get('error_kind')} · {page.locator('#mcp-server-note').inner_text()[:120]}",
    )
    r.shot("66-atelier-mcp-serveur-public-hors-reseau")

    # (5) A public server's tools, served by `page.route` (no network here).
    calls: list[dict[str, Any]] = []

    def state(route) -> None:  # noqa: ANN001
        response = route.fetch()
        body = response.json()
        body["last_session"] = _mcp_fake_session(body["seq"])
        body["open_server"] = "datagouv"
        route.fulfill(response=response, json=body)

    def intercepted(route) -> None:  # noqa: ANN001
        calls.append(route.request.post_data_json)
        route.fulfill(status=409, json={"detail": "Appel intercepté (e2e)."})

    page.route("**/api/mcp_lab", state)
    page.route("**/api/intentions/mcp_lab_call", intercepted)
    _goto_mcp(r)
    expect(page.locator("#mcp-tab-tools")).to_be_visible(timeout=10_000)
    kinds = page.locator("#mcp-call-fields [data-kind]").evaluate_all(
        "fields => fields.map(f => [f.name, f.dataset.kind, f.type ?? f.tagName])"
    )
    unavailable = [
        page.locator(f"#mcp-tab-{k}").get_attribute("aria-disabled")
        for k in ("resources", "prompts")
    ]
    r.check(
        unavailable == ["true", "true"]
        and "⊘" in page.locator("#mcp-tab-resources").inner_text()
        and kinds
        == [
            ["query", "text", "text"],
            ["page_size", "number", "number"],
            ["filters", "json", "textarea"],
            ["strict", "boolean", "checkbox"],
        ],
        "serveur public : ressources et prompts « ⊘ » ; un champ par paramètre : texte, nombre, "
        "JSON, case",
        f"{unavailable} {kinds}",
    )
    result = page.locator("#mcp-model-body .mcp-context-block.is-result")
    r.check(
        result.count() == 1
        and "Borné : 512 tokens gardés sur 2 048." in _plain(result.inner_text()),
        "appel borné rejoué : la note « Borné » sous le résultat réinjecté",
        _plain(result.inner_text())[-160:] if result.count() else "absent",
    )
    page.locator("#mcp-call-preset").select_option("0")
    query = page.locator('#mcp-call-fields input[name="query"]').input_value()
    page.locator('#mcp-call-fields input[name="page_size"]').fill("20")
    page.locator('#mcp-call-fields textarea[name="filters"]').fill("{oops")
    page.locator('#mcp-call-fields input[name="strict"]').check()
    page.locator("#mcp-call-run").click()
    status = page.locator("#mcp-command-status")
    expect(status).to_have_text("Valeur JSON invalide pour filters.", timeout=5000)
    r.check(
        query == "cybersécurité" and not calls,
        "JSON invalide : dit sous le formulaire, aucune requête envoyée",
        f"{query!r} · {status.inner_text()}",
    )
    page.locator('#mcp-call-fields textarea[name="filters"]').fill('{"organization": "anssi"}')
    page.locator("#mcp-call-run").click()
    expect(status).to_have_text("Appel intercepté (e2e).", timeout=5000)
    r.check(
        calls
        == [
            {
                "server": "datagouv",
                "tool": "search_datasets",
                "arguments": {
                    "query": "cybersécurité",
                    "page_size": 20,
                    "filters": {"organization": "anssi"},
                    "strict": True,
                },
            }
        ],
        "arguments envoyés : texte, entier, objet JSON, booléen, convertis par la page",
        str(calls),
    )
    page.unroute("**/api/mcp_lab")
    page.unroute("**/api/intentions/mcp_lab_call")

    # (6) « Liste en échec » and « Fenêtre dépassée », served: the glossary's prompts/list left
    # unanswered (its timeout in `list_errors`), then an ask whose context exceeds the window.
    def failures(route) -> None:  # noqa: ANN001
        response = route.fetch()
        body = response.json()
        body["last_session"] = _mcp_fake_failures(body["seq"])
        body["open_server"] = "local"
        route.fulfill(response=response, json=body)

    page.route("**/api/mcp_lab", failures)
    _goto_mcp(r)
    listed = page.locator('#mcp-seq li.mcp-row[data-method="prompts/list"]')
    expect(listed).to_have_count(1, timeout=10_000)
    page.locator("#mcp-tab-prompts").click()
    panel = page.locator("#mcp-panel-prompts")
    model = page.locator('#mcp-seq li.mcp-row[data-kind="model"]')
    r.check(
        "is-error" in (listed.get_attribute("class") or "")
        and "is-unanswered" in (listed.get_attribute("class") or "")
        and "La liste des prompts a échoué" in (panel.text_content() or "")
        and model.count() == 1
        and "is-error" in (model.get_attribute("class") or "")
        and "non envoyé" in (model.text_content() or ""),
        "liste en échec : requête prompts/list en rouge, sans réponse, l'onglet le dit ; fenêtre "
        "dépassée : la flèche Hôte → modèle « non envoyé » en rouge",
        f"{listed.get_attribute('class')} · {(panel.text_content() or '')[:80]} · "
        f"{(model.text_content() or '')[:80] if model.count() else 'absent'}",
    )
    page.unroute("**/api/mcp_lab")

    # (7) The reset (`harness_reset`): the series drawn live goes, as a reload would show it.
    _goto_mcp(r)
    rows = page.locator("#mcp-seq li.mcp-row")
    had = rows.count()
    r.poll(lambda: r.api("GET", "/api/mcp_lab").json()["session_state"]["state"] == "idle", 15)
    reset = r.api("POST", "/api/intentions/reset")
    expect(rows).to_have_count(0, timeout=10_000)
    r.check(
        had > 0 and reset.status_code == 200 and rows.count() == 0,
        "réinitialisation : la série affichée en direct disparaît (harness_reset)",
        f"{had} flèche(s) avant · {reset.status_code}",
    )
    r.check(not errors, "/mcp : aucune erreur JavaScript", str(errors)[:300])


_DATAGOUV_SCHEMA = {
    "type": "object",
    "properties": {
        "query": {"type": "string", "description": "Mots cherchés (e2e)"},
        "page_size": {"type": "integer"},
        "filters": {"type": "object"},
        "strict": {"type": "boolean"},
    },
    "required": ["query"],
}


def _mcp_fake_session(seq: int) -> list[dict[str, Any]]:
    """A `last_session` with a public server's connection and a bounded call (AD-27),
    validated by the journal's `Envelope` (its payload models)."""
    definition = json.dumps(
        {
            "type": "function",
            "function": {
                "name": "datagouv__search_datasets",
                "description": "Search datasets on data.gouv.fr (served, e2e).",
                "parameters": _DATAGOUV_SCHEMA,
            },
        }
    )
    lazy = json.dumps({"type": "function", "function": {"name": "load_tool_doc"}})
    rpc = lambda method, n: json.dumps({"jsonrpc": "2.0", "id": n, "method": method})  # noqa: E731
    answer = lambda n: json.dumps({"jsonrpc": "2.0", "id": n, "result": {}})  # noqa: E731
    served = {
        "name": "search_datasets",
        "description": "Search datasets on data.gouv.fr (served, e2e).",
        "inputSchema": _DATAGOUV_SCHEMA,
    }
    listed = json.dumps({"jsonrpc": "2.0", "id": 1, "result": {"tools": [served]}})
    first = seq - 11
    message = lambda direction, method, text, kind, ms, reply=None: {  # noqa: E731
        "direction": direction,
        "method": method,
        "jsonrpc": text,
        "elapsed_ms": ms,
        "elapsed_kind": "round_trip" if kind == "response" else "since_start",
        "message_type": kind,
        "reply_to_seq": reply,
    }
    events = [
        (
            "mcp90",
            "mcp_lab_exchange_started",
            {
                "exchange": "connect",
                "server": "datagouv",
                "transport": "streamable_http",
                "launch_text": "ouvre une session HTTP avec mcp.data.gouv.fr",
            },
        ),
        (
            "mcp90",
            "mcp_lab_message",
            message("to_server", "initialize", rpc("initialize", 0), "request", 0),
        ),
        (
            "mcp90",
            "mcp_lab_message",
            message("from_server", "initialize", answer(0), "response", 40, first + 2),
        ),
        (
            "mcp90",
            "mcp_lab_message",
            message("to_server", "tools/list", rpc("tools/list", 1), "request", 45),
        ),
        (
            "mcp90",
            "mcp_lab_message",
            message("from_server", "tools/list", listed, "response", 30, first + 4),
        ),
        (
            "mcp90",
            "mcp_lab_connect_ended",
            {
                "server": "datagouv",
                "status": "ok",
                "connection": "open",
                "primitives": {"tools": True, "resources": False, "prompts": False},
                "tools": [
                    {
                        "name": "datagouv__search_datasets",
                        "tool": "search_datasets",
                        "description": "Search datasets on data.gouv.fr (served, e2e).",
                        "schema": _DATAGOUV_SCHEMA,
                        "definition_text": definition,
                        "doc_tokens": 120,
                        "line_text": "- datagouv__search_datasets: Search datasets",
                        "line_tokens": 12,
                    }
                ],
                "full_tokens": 120,
                "lazy_tokens": 60,
                "load_tool_doc_tokens": 48,
                "lazy_definition_text": lazy,
                "duration_ms": 80,
            },
        ),
        (
            "mcp91",
            "mcp_lab_exchange_started",
            {
                "exchange": "call",
                "server": "datagouv",
                "transport": "streamable_http",
                "by": "hand",
                "tool": "search_datasets",
                "arguments": {"query": "cybersécurité"},
            },
        ),
        (
            "mcp91",
            "mcp_lab_message",
            message("to_server", "tools/call", rpc("tools/call", 2), "request", 0),
        ),
        (
            "mcp91",
            "outbound_request",
            {
                "origin": "brick",
                "method": "POST",
                "url": "https://mcp.data.gouv.fr/mcp",
                "body": rpc("tools/call", 2),
                "message_seq": first + 8,
            },
        ),
        (
            "mcp91",
            "mcp_lab_message",
            message("from_server", "tools/call", answer(2), "response", 110, first + 8),
        ),
        (
            "mcp91",
            "mcp_lab_call_ended",
            {
                "server": "datagouv",
                "tool": "search_datasets",
                "arguments": {"query": "cybersécurité"},
                "by": "hand",
                "status": "ok",
                "connection": "open",
                "raw": answer(2),
                "text": "Jeux de données (e2e) : " + "cybersécurité " * 40,
                "tokens": 512,
                "truncated": {"tokens": 512, "total_tokens": 2048, "estimated": False},
                "duration_ms": 120,
            },
        ),
    ]
    envelopes = []
    for offset, (step, kind, payload) in enumerate(events, start=1):
        envelope = Envelope(
            seq=first + offset,
            ts=time.strftime("%Y-%m-%dT%H:%M:%S+00:00", time.gmtime()),
            session_epoch=0,
            context_id="mcp_lab",
            step_id=step,
            kind=kind,
            actor="harness",
            trigger="user",
            brick="mcp",
            component="mcp_lab.datagouv",
            payload=payload,
        )
        envelopes.append(json.loads(envelope.model_dump_json()))
    return envelopes


def _mcp_fake_failures(seq: int) -> list[dict[str, Any]]:
    """A `last_session` of the glossary (AD-27): its prompts/list left unanswered (the timeout
    in `list_errors`, the connection open), then an ask refused before any call, its context
    over the usable window (`model_started`, then `model_ended{overflow}`, no model call)."""
    rpc = lambda method, n: json.dumps({"jsonrpc": "2.0", "id": n, "method": method})  # noqa: E731
    answer = lambda n, result: json.dumps({"jsonrpc": "2.0", "id": n, "result": result})  # noqa: E731
    first = seq - 14
    message = lambda direction, method, text, kind, ms, reply=None: {  # noqa: E731
        "direction": direction,
        "method": method,
        "jsonrpc": text,
        "elapsed_ms": ms,
        "elapsed_kind": "round_trip" if kind == "response" else "since_start",
        "message_type": kind,
        "reply_to_seq": reply,
    }
    tool = {
        "name": "local__define_term",
        "tool": "define_term",
        "description": "Donne la définition d'une notion (e2e).",
        "schema": {"type": "object", "properties": {"term": {"type": "string"}}},
        "definition_text": json.dumps(
            {"type": "function", "function": {"name": "local__define_term"}}
        ),
        "doc_tokens": 98,
        "line_text": "- local__define_term : Donne la définition d'une notion",
        "line_tokens": 14,
    }
    caps = {"capabilities": {"tools": {}, "resources": {}, "prompts": {}}}
    too_long = "Non envoyé : le contexte compte 5 000 tokens pour 3 584 utilisables."
    events = [
        (
            "mcp95",
            "mcp_lab_exchange_started",
            {
                "exchange": "connect",
                "server": "local",
                "transport": "stdio",
                "launch_text": "lance le serveur : python -m wavestack.mcp.local_server fr",
            },
        ),
        (
            "mcp95",
            "mcp_lab_message",
            message("to_server", "initialize", rpc("initialize", 0), "request", 0),
        ),
        (
            "mcp95",
            "mcp_lab_message",
            message("from_server", "initialize", answer(0, caps), "response", 40, first + 2),
        ),
        (
            "mcp95",
            "mcp_lab_message",
            message(
                "to_server",
                "notifications/initialized",
                json.dumps({"jsonrpc": "2.0", "method": "notifications/initialized"}),
                "notification",
                41,
            ),
        ),
        (
            "mcp95",
            "mcp_lab_message",
            message("to_server", "tools/list", rpc("tools/list", 1), "request", 42),
        ),
        (
            "mcp95",
            "mcp_lab_message",
            message(
                "from_server", "tools/list", answer(1, {"tools": []}), "response", 3, first + 5
            ),
        ),
        (
            "mcp95",
            "mcp_lab_message",
            message("to_server", "resources/list", rpc("resources/list", 2), "request", 46),
        ),
        (
            "mcp95",
            "mcp_lab_message",
            message(
                "from_server",
                "resources/list",
                answer(2, {"resources": []}),
                "response",
                3,
                first + 7,
            ),
        ),
        (
            "mcp95",
            "mcp_lab_message",
            message("to_server", "prompts/list", rpc("prompts/list", 3), "request", 50),
        ),
        (
            "mcp95",
            "mcp_lab_connect_ended",
            {
                "server": "local",
                "status": "ok",
                "connection": "open",
                "primitives": {"tools": True, "resources": True, "prompts": True},
                "tools": [tool],
                "resources": [
                    {"uri": "glossary://terms", "name": "terms", "mime_type": "text/plain"}
                ],
                "prompts": None,
                "list_errors": [
                    {
                        "method": "prompts/list",
                        "error_kind": "timeout",
                        "error_text": "Le serveur n'a pas répondu dans le délai (10 s).",
                    }
                ],
                "full_tokens": 98,
                "duration_ms": 10_080,
            },
        ),
        (
            "mcp96",
            "mcp_lab_exchange_started",
            {
                "exchange": "ask",
                "server": "local",
                "transport": "stdio",
                "by": "model",
                "question": "Que veut dire MCP ?",
                "doc_mode_requested": "full",
            },
        ),
        (
            "mcp96.c1",
            "mcp_lab_model_started",
            {
                "index": 1,
                "sends": [
                    {"part": "question", "label_text": "question", "tokens": 6},
                    {"part": "tools", "label_text": "1 outil", "tokens": 98},
                ],
                "sends_total_tokens": 104,
                "prompt_tokens": 5000,
                "doc_mode": "full",
                "phase_label": "Envoi au modèle (5 000 tokens)",
            },
        ),
        (
            "mcp96.c1",
            "mcp_lab_model_ended",
            {
                "index": 1,
                "status": "error",
                "outcome": "overflow",
                "final": True,
                "error_text": too_long,
            },
        ),
        (
            "mcp96",
            "mcp_lab_ask_ended",
            {
                "server": "local",
                "status": "error",
                "outcome": "overflow",
                "error_text": too_long,
                "connection": "open",
                "duration_ms": 12,
            },
        ),
    ]
    envelopes = []
    for offset, (step, kind, payload) in enumerate(events, start=1):
        envelope = Envelope(
            seq=first + offset,
            ts=time.strftime("%Y-%m-%dT%H:%M:%S+00:00", time.gmtime()),
            session_epoch=0,
            context_id="mcp_lab",
            step_id=step,
            parent_step="mcp96" if "." in step else None,
            call_id=step if ".c" in step else None,
            kind=kind,
            actor="harness",
            trigger="user",
            brick="mcp",
            component="mcp_lab.local",
            payload=payload,
        )
        envelopes.append(json.loads(envelope.model_dump_json()))
    return envelopes


def s_compression(r: Run) -> None:
    """Story 20: a turn without then with the compression (Headroom, the real library), the
    step with the tokens before and after, the compressed segment and the total without
    compression in Contexte LLM, the compressor in the schema, « Comparer », a reload."""
    log = (REPO / "content" / "demo_files" / "journal_serveur.log").read_text(encoding="utf-8")
    error_line = next(line for line in log.splitlines() if " ERROR " in line)
    question, second = _prompts("compression")
    r.launch("compression")
    r.check(
        not r.bricks()["rag"]["wanted"]
        and "« Journal de sauvegarde (compression) »"
        in r.page.locator("#scenario-info-popover").text_content(),
        "compression : RAG non voulu, la consigne donne le préréglage de secours (story 27)",
    )
    brick = r.bricks()["compression"]
    reason = brick.get("reason_text") or ""
    if not brick["available"] and "uv sync --extra compression" in reason:
        # headroom-ai absent (the `compression` extra, or `--no-headroom`): a clean skip.
        text = r.card("Compression").inner_text()
        r.check(
            "uv sync --extra compression" in text,
            "headroom-ai absent : la carte donne la commande d'installation, scénario sauté",
            reason[:160],
        )
        seq = r.ev.mark()
        ended = r.send(question)
        r.check(
            ended["payload"]["status"] == "completed"
            and not r.ev.since(seq, "compression_started"),
            "headroom-ai absent : le tour aboutit, sans étape de compression",
        )
        print("  SKIP compression : headroom-ai n'est pas installé (uv sync --extra compression)")
        return
    seq = r.ev.mark()
    ready = r.bricks()["compression"]["available"] or r.ev.wait(
        "bricks_changed",
        seq,
        lambda p: next(b for b in p["bricks"] if b["id"] == "compression")["available"],
        30,
    )
    r.check(bool(ready), "brique Compression disponible (Headroom chargé)")
    card = r.card("Compression")
    r.check(
        "300 caractères" in card.inner_text(),
        "carte Compression : ce qui est compressé et le seuil",
        card.inner_text()[:200],
    )
    chip = r.page.locator('#schema .arch-chip[data-component="compression.compressor"]')
    r.check(
        "🗜️" in chip.inner_text() and "Headroom 0.38.0" in (chip.get_attribute("title") or ""),
        "schéma : la puce 🗜️ du compresseur, dans le processus du harnais",
        chip.get_attribute("title") or "",
    )

    # Compression off: the whole log goes to the model.
    r.set_brick("Compression", False)
    seq = r.ev.mark()
    ended = r.send(question)
    r.check(ended["payload"]["status"] == "completed", "tour sans compression terminé")
    r.check(not r.ev.since(seq, "compression_started"), "sans compression : aucune étape")
    started = [e["payload"] for e in r.ev.since(seq, "tool_started")]
    r.check(
        [(t["tool"], t["arguments"]) for t in started[:1]]
        == [("read_file", {"path": "journal_serveur.log"})],
        "le modèle lit journal_serveur.log, que le prompt nomme",
        str(started)[:200],
    )
    body = json.dumps(r.fake_calls()[-1]["messages"], ensure_ascii=False)
    r.check("lot 12 copié" in body, "sans compression : le journal entier part au modèle")
    r.check(
        not r.ev.since(seq, "rag_search_started")
        and "documentation interne d'Exemplia" not in body,
        "aucun extrait RAG n'entre dans le contexte (RAG non voulu)",
    )

    # On again, the prompt replayed: the log is compressed before the second call.
    seq = r.ev.mark()
    r.set_brick("Compression", True)
    r.ev.wait(
        "bricks_changed",
        seq,
        lambda p: next(b for b in p["bricks"] if b["id"] == "compression")["available"],
        30,
    )
    seq = r.ev.mark()
    ended = r.replay()
    r.check(ended["payload"]["status"] == "completed", "rejeu avec compression terminé")
    done = r.ev.since(seq, "compression_ended")
    tool_items = [i for e in done for i in e["payload"]["items"] if i["kind"] == "tool_result"]
    r.check(
        len(tool_items) == 1
        and tool_items[0]["changed"]
        and error_line in tool_items[0]["text_after"],
        "le résultat de read_file est compressé, l'erreur gardée",
        str([(i["source_text"], i["tokens_before"], i["tokens_after"]) for i in tool_items]),
    )
    rag_items = [i for e in done for i in e["payload"]["items"] if i["kind"] == "rag_excerpt"]
    r.check(not rag_items, "aucun extrait RAG parmi les candidats", f"{len(rag_items)} extraits")
    tool = next(m for m in r.fake_calls()[-1]["messages"] if m.get("role") == "tool")
    content = tool["content"] if isinstance(tool["content"], str) else json.dumps(tool["content"])
    r.check(
        "lot 12 copié" not in content and error_line in content,
        "le fournisseur reçoit la version courte (corps JSON)",
    )
    r.check(error_line in r.last_answer(), "la réponse cite l'erreur gardée", r.last_answer())
    # Story 33: the card's status line, the gap between two values of the last gauge.
    gauge = _last_gauge(r)
    gain = (gauge.get("uncompressed_used") or gauge.get("used", 0)) - gauge.get("used", 0)
    line = r.card("Compression").locator("p.brick-status").inner_text()
    found = re.search(r"Gain : (\d+)", line.replace("\u202f", "").replace("\xa0", ""))
    r.check(
        found is not None and gain > 0 and int(found.group(1)) == gain,
        "carte Compression : « Gain : n tokens » = uncompressed_used − used de la jauge",
        f"{line} / attendu {gain}",
    )

    # Orchestration: the step, its figure, its unfolded body.
    step = _compression_step(r)
    figure = step.locator(".turn-step-figure").inner_text()
    r.check(
        re.search(r"→ .*tokens \(−\d+ %\)", figure) is not None
        and "⚙ harnais" in step.locator(".turn-step-actor").inner_text(),
        "Orchestration : « 🗜️ Compression (Headroom) », acteur harnais, avant → après",
        figure,
    )
    step.locator(".turn-step-line").click()
    items = step.locator(".compression-items li")
    expect(items.first).to_be_visible(timeout=5000)
    text = step.inner_text()
    r.check(
        "Résultat de l'outil « read_file »" in text and "Décision du harnais" in text,
        "l'étape dépliée nomme la source et la décision du harnais",
    )
    step.locator(".compression-item-head").first.click()
    expect(chip).to_have_class(re.compile("is-selected"), timeout=5000)
    r.check(True, "un clic sur un texte compressé sélectionne le compresseur dans le schéma")

    # Contexte LLM: the compressed segment, its text before, the total without compression.
    ctx = r.page.locator("#ctx")
    total = ctx.locator(".ctx-compressed-total").inner_text()
    r.check("Sans compression" in total, "Contexte LLM : total sans compression affiché", total)
    badge = ctx.locator(".ctx-compressed-badge")
    r.check(
        badge.count() == 1, "Contexte LLM : un segment marqué « compressé »", str(badge.count())
    )
    r.check(
        ctx.get_by_text("Texte avant compression").count() == 1,
        "Contexte LLM : le texte d'avant compression se déplie",
    )
    r.shot("24-compression-avant-apres")

    # « Comparer » the replay with the turn without compression.
    r.page.locator("#chat .replay-badge").last.click()
    compare = r.page.locator("#ctx")
    r.check(
        "Comparaison de tours" in compare.inner_text() and "tokens (−" in compare.inner_text(),
        "« Comparer » : le contexte compressé pèse moins que l'original",
    )
    compare.get_by_role("button", name="Fermer").click()

    # AD-1: after a reload, the step is rebuilt from the journal.
    r.page.reload()
    r.wait_idle()
    step = _compression_step(r)
    expect(step).to_be_visible(timeout=10_000)
    r.check(True, "après rechargement, l'étape « Compression » est toujours là")

    # The second prompt: what Headroom cut is lost for the model (lot 12 is left out).
    seq = r.ev.mark()
    ended = r.send(second)
    done = r.ev.since(seq, "compression_ended")
    r.check(
        ended["payload"]["status"] == "completed" and len(done) >= 1,
        "second prompt : le journal relu est compressé de nouveau",
    )
    answer = r.last_answer()
    r.check(
        "ne mentionne pas le lot 12" in answer,
        "second prompt : la ligne du lot 12, coupée par Headroom, manque au modèle",
        answer,
    )
    kept = [i["text_after"] for e in done for i in e["payload"]["items"] if i["changed"]]
    r.check(
        bool(kept) and all("lot 12 " not in text for text in kept) and "lot 12 copié" in log,
        "second prompt : le lot 12 est dans le fichier, pas dans la version compressée",
    )

    # Story 27: the limit of the tool, shown by forcing a prose file (no RAG any more).
    r.show_forced(True)
    r.open_options("Outils")
    armed = r.arm(
        "Forcer l'appel : Lecture de fichier", preset="Guide du harnais (prose, compression)"
    )
    r.check(
        armed["payload"]["actions"][0]["args"].get("path") == "guide_harnais.md",
        "préréglage « Guide du harnais (prose, compression) »",
    )
    seq = r.ev.mark()
    ended = r.replay()
    prose = [
        i
        for e in r.ev.since(seq, "compression_ended")
        for i in e["payload"]["items"]
        if i["kind"] == "tool_result" and "# Guide du harnais d'agent" in i["text_before"]
    ]
    r.check(
        ended["payload"]["status"] == "completed" and bool(prose) and not prose[0]["changed"],
        "de la prose (le guide du harnais) passe inchangée : la limite de Headroom",
        str([(i["source_text"], i["tokens_before"], i["changed"]) for i in prose])[:200],
    )
    r.show_forced(False)


def s_busy_and_stop(r: Run) -> None:
    r.launch("bare_llm")
    seq = r.ev.mark()
    r.page.fill("#composer-input", "Explique le harnais [lent] [long]")
    r.page.press("#composer-input", "Enter")
    r.ev.wait("model_first_token", seq, timeout=20)
    # Story 32: the running call's answer grows in Contexte LLM before `model_call_ended`.
    answer = r.page.locator("#ctx .ctx-call").last.locator(".ctx-produced.is-answer pre")
    expect(answer).to_be_visible(timeout=5000)
    before = len(answer.inner_text())
    time.sleep(1.5)  # « [lent] »: a chunk every 0.4 s
    after = len(answer.inner_text())
    r.check(
        after > before and not r.ev.since(seq, "model_call_ended"),
        "Contexte LLM : la réponse de l'appel en cours grandit avant `model_call_ended`",
        f"{before} → {after} caractères",
    )
    r.check(r.page.locator("#scenario-picker").is_disabled(), "sélecteur désactivé pendant un tour")
    # A submit that reaches the form while the field is disabled is never dropped silently.
    r.page.evaluate("() => document.getElementById('composer').requestSubmit()")
    reason = r.page.locator("#composer-reason")
    ok, _ = r.poll(lambda: "Message non envoyé" in reason.inner_text(), 5)
    r.check(ok, "envoi pendant un tour : refus dit sous le champ", reason.inner_text())
    r.check(
        r.page.locator("#reset-button").is_disabled(), "« Réinitialiser » désactivé pendant un tour"
    )
    refused = r.api("POST", "/api/intentions/scenario", {"scenario_id": "hooks"})
    r.check(
        refused.status_code == 409, "lancer un scénario pendant un tour : 409", refused.text[:200]
    )
    refused = r.api("POST", "/api/intentions/reset")
    r.check(refused.status_code == 409, "réinitialiser pendant un tour : 409")
    r.page.click("#composer-stop")
    ended = r.ev.wait("turn_ended", seq)
    r.check(
        ended["payload"]["status"] == "cancelled",
        "« Arrêter » annule le tour",
        ended["payload"]["status"],
    )
    r.check("Arrêté à votre demande" in r.last_answer(), "annulation expliquée")
    r.wait_idle()
    r.page.fill("#composer-input", "   ")
    r.page.press("#composer-input", "Enter")
    ok, _ = r.poll(lambda: "Écrivez un message" in reason.inner_text(), 5)
    r.check(ok, "envoi d'un message vide : invitation à écrire", reason.inner_text())
    unknown = r.api("POST", "/api/intentions/scenario", {"scenario_id": "nope"})
    r.check(unknown.status_code == 404, "scénario inconnu : 404")
    # Story 32: an overflow; the last call says it was not sent, and produced nothing.
    seq = r.ev.mark()
    r.page.fill("#composer-input", "Résume : " + "mot " * 5000)
    r.page.press("#composer-input", "Enter")
    ended = r.ev.wait("turn_ended", seq)
    calls = _ctx_calls(r)
    none = r.page.locator("#ctx .ctx-call").last.locator(".ctx-produced-none")
    r.check(
        ended["payload"]["status"] == "overflow"
        and bool(calls)
        and "non envoyé : contexte dépassé" in calls[-1]["head"]
        and none.count() == 1
        and none.inner_text() == "Aucun appel : contexte dépassé.",
        "dépassement : le dernier appel « non envoyé : contexte dépassé », "
        "« Aucun appel : contexte dépassé. »",
        f"{ended['payload']['status']} · {calls[-1]['head'] if calls else '—'}",
    )
    # Story 31: the overflow's red pill: its text in on-vivid (formerly white, 3.7:1).
    figures = r.page.locator("#gauge.is-overflow #gauge-figures")
    expect(figures).to_be_visible(timeout=5000)
    wrong = _on_vivid_both_themes(r, figures)
    r.check(
        not wrong, "dépassement : chiffres de la jauge en --color-on-vivid sur le rouge", str(wrong)
    )


# Every change of the composer field's `disabled`, from the page's first byte on.
COMPOSER_FLIPS_JS = """
window.__composerFlips = [];
new MutationObserver((records) => {
  for (const m of records) {
    if (m.target.id === "composer-input") window.__composerFlips.push(m.target.disabled);
  }
}).observe(document, { subtree: true, attributes: true, attributeFilter: ["disabled"] });
"""


def _connect_local_mcp(r: Run) -> None:
    """E043: the local MCP server contacted before the turns, for the harness preparation the
    reset keeps (a connection made before the turns, not the last one)."""
    seq = r.ev.mark()
    r.api("POST", "/api/intentions/mcp_server", {"server": "local", "enabled": True})
    r.api("POST", "/api/intentions/brick", {"brick": "mcp", "wanted": True})
    r.ev.wait("mcp_connect_ended", seq, lambda p: p["server"] == "local", 45)
    for started in r.ev.since(seq, "mcp_connect_started"):  # data.gouv.fr too, if enabled
        server = started["payload"].get("server")
        r.ev.wait("mcp_connect_ended", seq, lambda p, s=server: p["server"] == s, 45)


def _reset_keeps_prep_and_folds(r: Run) -> None:
    """E043 and E047 (story 5 of the deferred leftovers), after « Réinitialiser »: the harness
    preparation keeps the MCP connection seen before the turns; no option list stays open."""
    prep = r.page.locator("#orch-scroll .harness-prep")
    ok, _ = r.poll(lambda: prep.count() == 1 and "Glossaire WaveStack" in prep.inner_text(), 5)
    r.check(
        ok,
        "E043 : après « Réinitialiser », la préparation du harnais garde la connexion MCP",
        prep.inner_text()[:200] if prep.count() else "aucune préparation",
    )
    opened = r.page.locator("#bricks details.brick-options[open]")
    folded, _ = r.poll(lambda: opened.count() == 0, 5)
    r.check(
        folded,
        "E047 : « Réinitialiser » referme les listes d'options ouvertes",
        f"{opened.count()} liste(s) ouverte(s)",
    )


def s_reload_and_reset(r: Run) -> None:
    r.launch("hooks")
    _connect_local_mcp(r)
    seq = r.ev.mark()
    for _ in range(3):  # past turns: `session_state` « turn » then « idle » in the journal
        r.send("Bonjour")
    past_ids = [e["turn_id"] for e in r.ev.since(seq, "turn_started")]
    r.page.add_init_script(COMPOSER_FLIPS_JS)
    r.reload_app()
    flips = r.page.evaluate("() => window.__composerFlips")
    r.check(
        True not in flips,
        "après rechargement : le rejeu ne désactive jamais le champ (états passés ignorés)",
        str(flips),
    )
    r.wait_idle()
    ok, took = r.poll(lambda: r.page.input_value("#scenario-picker") == "hooks")
    r.check(ok, "après rechargement : sélecteur sur « Hooks »", f"au bout de {took:.1f} s")
    ok, took = r.poll(lambda: r.page.locator("#suggested-prompts button").count() == 1)
    r.check(
        ok and r.page.locator("#scenario-info").is_visible(),
        "après rechargement : consigne et prompt suggéré",
        f"au bout de {took:.1f} s",
    )
    measure = (
        "() => ['#reset-button', '#pane-menu-toggle', '#gauge-bar'].map(q => {"
        " const b = document.querySelector(q).getBoundingClientRect();"
        " return [Math.round(b.width), Math.round(b.height)]; })"
    )
    before = r.page.evaluate(measure)
    r.open_options("Hooks")  # E047: an option list open before the reset
    r.check(
        r.card("Hooks").locator("details.brick-options").get_attribute("open") is not None,
        "E047 : liste d'options des Hooks ouverte avant « Réinitialiser »",
    )
    seq = r.ev.mark()
    r.page.click("#reset-button")
    r.ev.wait("harness_reset", seq, timeout=10)
    time.sleep(0.8)
    after = r.page.evaluate(measure)
    r.check(
        after == before,
        "le message de réinitialisation ne déforme pas la barre de l'atelier",
        f"[largeur, hauteur] de « Réinitialiser », « Volets », jauge : {before} puis {after}",
    )
    r.check(
        "WaveStack réinitialisé" in r.page.locator("#top-status").inner_text(),
        "message « WaveStack réinitialisé : LLM nu. »",
    )
    ok, took = r.poll(lambda: r.page.locator("#top-status").inner_text() == "", 10)
    r.check(ok, "le message de réinitialisation s'efface de lui-même (A4)", f"{took:.1f} s")
    b = r.bricks()
    r.check(
        not any(x["wanted"] for x in b.values()),
        "aucune brique après réinitialisation",
        str([k for k, x in b.items() if x["wanted"]]),
    )
    r.check(r.page.input_value("#scenario-picker") == "", "sélecteur revenu à « Choisir »")
    for pane in ("#chat", "#ctx", "#orch-scroll"):
        r.check(
            "Aucun tour" in r.page.locator(pane).inner_text(),
            f"{pane} : « Aucun tour »",
            r.page.locator(pane).inner_text()[:120],
        )
    _reset_keeps_prep_and_folds(r)
    title = r.page.locator("#event-log-title").inner_text()
    r.shot("17-reinitialisation")
    r.page.reload()
    r.wait_idle()
    ok, took = r.poll(lambda: "Aucun tour" in r.page.locator("#chat").inner_text())
    r.check(ok, "après rechargement : toujours « Aucun tour »", f"au bout de {took:.1f} s")
    ok, took = r.poll(lambda: r.page.locator("#event-log-title").inner_text() == title)
    r.check(
        ok,
        "après rechargement : journal affiché depuis la réinitialisation",
        f"{title}, au bout de {took:.1f} s",
    )
    replay = r.page.locator("#replay-last")
    r.check(replay.is_disabled(), "rien à rejouer après réinitialisation")

    # Story 22: « Tour 1 » again after the reset, then after « Vider la conversation »; the
    # journal's ids go on (t{n} unique for the session), said by the title's tooltip.
    r.check(len(past_ids) == 3, "trois tours avant la réinitialisation", str(past_ids))
    last = int(past_ids[-1][1:])
    _first_turn_after(r, "Réinitialiser", f"t{last + 1}")
    seq = r.ev.mark()
    r.page.click("#clear-conversation")
    r.ev.wait("conversation_cleared", seq, timeout=10)
    _first_turn_after(r, "Vider la conversation", f"t{last + 2}")


# ---------- languages (1/5): the language picker and the defaults sent to the model ----------

_PROMPT_EN = "You are WaveStack's demonstration assistant. Answer in English"
_PROMPT_FR = "Tu es l'assistant de démonstration de WaveStack. Réponds en français"


def _html_lang(r: Run) -> str:
    return r.page.evaluate("() => document.documentElement.lang")


def _pick_language(r: Run, language: str) -> None:
    """Choose `language` in the picker: the intention is accepted, then the page reloads."""
    seq = r.ev.mark()
    _open_display(r.page)  # languages (2/5): the picker is in « Affichage ▾ »
    with r.page.expect_navigation(timeout=15_000):
        r.page.select_option("#language-picker", language)
    r.ev.wait("language_changed", seq, lambda p: p["language"] == language, timeout=15)
    r.wait_idle()


def _clear_conversation(r: Run) -> None:
    seq = r.ev.mark()
    r.page.click("#clear-conversation")
    r.ev.wait("conversation_cleared", seq, timeout=10)


def _sent_system(r: Run) -> str:
    messages = r.fake_calls()[-1]["messages"]
    return messages[0]["content"] if messages and messages[0]["role"] == "system" else ""


def _sent_tool(r: Run, name: str) -> str:
    tools = r.fake_calls()[-1].get("tools") or []
    found = [t["function"] for t in tools if t["function"]["name"] == name]
    return found[0].get("description", "") if found else ""


def s_language(r: Run) -> None:
    """Languages (1/5): the picker locked by a turn, English once the conversation is
    cleared (reload, `<html lang>`, English defaults sent to the model and shown in
    « Contexte LLM »), then back to French. Always ends in French."""
    try:
        _language(r)
    finally:
        if r.state().get("language") != "fr":
            r.wait_idle()
            cleared = r.api("POST", "/api/intentions/clear_conversation", {})
            back = r.api("POST", "/api/intentions/language", {"language": "fr"})
            r.check(
                cleared.status_code == back.status_code == 200,
                "nettoyage : conversation vidée et retour au français",
                f"{cleared.status_code} {back.status_code} {back.text[:160]}",
            )
            r.goto_app()


def _language(r: Run) -> None:
    page = r.page
    picker = page.locator("#language-picker")
    r.launch("native_tools")  # system prompt and tools among its bricks
    r.check(
        picker.is_enabled() and picker.input_value() == "fr" and _html_lang(r) == "fr",
        "conversation vide : sélecteur de langue actif, sur « Français », <html lang=fr>",
    )
    labels = picker.locator("option").all_inner_texts()
    r.check(
        labels == ["Français", "English", "Deutsch"], "langues écrites en elles-mêmes", str(labels)
    )
    r.send("Bonjour")
    ok, took = r.poll(lambda: picker.is_disabled(), 10)
    title = picker.get_attribute("title") or ""
    r.check(
        ok and "Videz d'abord la conversation" in title,
        "après un tour : sélecteur désactivé, l'infobulle dit de vider la conversation",
        f"{title} ({took:.1f} s)",
    )
    refused = r.api("POST", "/api/intentions/language", {"language": "en"})
    r.check(
        refused.status_code == 409 and "conversation vide" in refused.json().get("detail", ""),
        "l'intention est refusée (409) tant que la conversation n'est pas vide",
        f"{refused.status_code} {refused.text[:160]}",
    )
    r.shot_element("language-01-verrouille", ".site-nav")

    seq = r.ev.mark()
    page.click("#reset-button")
    r.ev.wait("harness_reset", seq, timeout=10)
    ok, took = r.poll(lambda: picker.is_enabled(), 10)
    r.check(ok, "« Réinitialiser » : sélecteur de nouveau actif", f"{took:.1f} s")
    r.launch("native_tools")
    r.send("Bonjour")
    ok, _ = r.poll(lambda: picker.is_disabled(), 10)
    r.check(ok, "un nouveau tour verrouille de nouveau le sélecteur")
    _clear_conversation(r)
    ok, took = r.poll(lambda: picker.is_enabled(), 10)
    r.check(ok, "conversation vidée : sélecteur de nouveau actif", f"{took:.1f} s")
    _pick_language(r, "en")
    state = r.state()
    r.check(
        _html_lang(r) == "en"
        and page.locator("#language-picker").input_value() == "en"
        and page.locator("#language-picker").get_attribute("aria-label") == "Language"
        and state["language"] == "en"
        and not state["language_locked"],
        "« English » : page rechargée en <html lang=en>, sélecteur sur English, nommé Language",
        f"lang={_html_lang(r)}, état {state.get('language')}",
    )
    r.check(
        page.locator("#language-picker-code").inner_text() == "EN",
        "le sélecteur compact affiche « EN »",
    )
    r.check(r.bricks()["tools"]["wanted"], "les briques du scénario restent allumées")
    r.send("What time is it?")
    system = _sent_system(r)
    datetime_doc = _sent_tool(r, "get_datetime")
    r.check(
        system.startswith(_PROMPT_EN) and "Réponds en français" not in system,
        "corps envoyé au modèle : prompt système anglais",
        system[:120],
    )
    r.check(
        datetime_doc.startswith("Gives the workstation's local day")
        and _sent_tool(r, "calculator").startswith("Computes an arithmetic expression"),
        "corps envoyé au modèle : descriptions d'outils anglaises",
        datetime_doc[:120],
    )
    ok, took = r.poll(lambda: _PROMPT_EN in (page.locator("#ctx").text_content() or ""), 10)
    r.check(ok, "« Contexte LLM » montre le prompt système anglais", f"{took:.1f} s")
    r.shot("language-02-anglais")

    _clear_conversation(r)
    _pick_language(r, "fr")
    r.check(
        _html_lang(r) == "fr" and r.state()["language"] == "fr",
        "retour au français : page rechargée en <html lang=fr>",
    )
    r.send("Bonjour")
    system = _sent_system(r)
    r.check(
        system.startswith(_PROMPT_FR) and _sent_tool(r, "get_datetime").startswith("Donne le jour"),
        "retour au français : prompt système et descriptions d'outils français",
        system[:120],
    )
    _clear_conversation(r)


# ---------- languages (2/5): the main screen in English and in German ----------

_UI_VAR = re.compile(r"\{\w+\}")


def _ui_leaves(tree: dict[str, Any], prefix: str = "") -> dict[str, str]:
    found: dict[str, str] = {}
    for key, value in tree.items():
        if isinstance(value, dict):
            found |= _ui_leaves(value, f"{prefix}{key}.")
        else:
            found[prefix + key] = value
    return found


def _ui_catalogue(lang: str) -> dict[str, str]:
    import yaml

    rel = "content/ui.yaml" if lang == "fr" else f"content/i18n/{lang}/ui.yaml"
    return _ui_leaves(yaml.safe_load((REPO / rel).read_text(encoding="utf-8")))


def _message_catalogue(lang: str) -> dict[str, str]:
    """`content/messages.yaml` in `lang`, flattened, both forms of a plural kept apart."""
    import yaml

    rel = "content/messages.yaml" if lang == "fr" else f"content/i18n/{lang}/messages.yaml"
    tree = yaml.safe_load((REPO / rel).read_text(encoding="utf-8"))
    return {f"messages:{k}": " ".join(str(v).split()) for k, v in _ui_leaves(tree).items()}


def _value_patterns(
    french: dict[str, str], translated: dict[str, str]
) -> list[tuple[str, re.Pattern[str]]]:
    """A French value whose translation differs: as itself, or with each variable any text,
    kept only when its fixed words say something (six letters at least)."""
    patterns = []
    for key, value in french.items():
        if translated.get(key) == value:
            continue
        if len(re.findall(r"[^\W\d_]", _UI_VAR.sub("", value))) < 6:
            continue
        parts = [re.escape(part) for part in _UI_VAR.split(value)]
        patterns.append((key, re.compile(".+?".join(parts), re.S)))
    return patterns


def _literals(french: dict[str, str], translated: dict[str, str]) -> set[str]:
    """The values without variable of the catalogue in the page's language, whitespace folded:
    a text that is exactly one of them is in that language, even when a French pattern reads
    it too (« Augmented prompt », a label of `rag_lab.yaml` in `de`, against « {n} prompt »).
    Never a French value whose translation differs: one copied by mistake into the
    translated catalogue stays a French text left."""

    def fold(value: str) -> str:
        return " ".join(value.split())

    left = {fold(v) for k, v in french.items() if fold(translated.get(k, "")) != fold(v)}
    return {fold(v) for v in translated.values() if not _UI_VAR.search(v)} - left


def _french_patterns(lang: str) -> list[tuple[str, re.Pattern[str]]]:
    """The French values of `common` and `main` whose `lang` value differs: a text without
    variable as itself, a text with variables as a pattern (each variable any text), kept
    only when its fixed words say something (six letters at least). Languages 5/5 (story 7
    of 2026-09-30): the backend's messages too (`messages.yaml`)."""
    french, translated = _ui_catalogue("fr"), _ui_catalogue(lang)
    patterns = _value_patterns(_message_catalogue("fr"), _message_catalogue(lang))
    for key, value in french.items():
        if translated.get(key) == value:
            continue  # « Tokens », « RAG », « Skills »… : the same in both languages
        fixed = _UI_VAR.sub("", value)
        if len(re.findall(r"[^\W\d_]", fixed)) < 6:
            continue
        parts = [re.escape(part) for part in _UI_VAR.split(value)]
        patterns.append((key, re.compile(".+?".join(parts), re.S)))
    return patterns


_VISIBLE_TEXTS_JS = """() => {
  const texts = [];
  const walker = document.createTreeWalker(document.body, NodeFilter.SHOW_TEXT);
  for (let n = walker.nextNode(); n; n = walker.nextNode()) {
    const text = n.data.trim();
    if (text && n.parentElement.checkVisibility()) texts.push(['texte', text]);
  }
  for (const e of document.querySelectorAll('[title], [aria-label], [placeholder]')) {
    if (!e.checkVisibility() && !e.closest('.top-bar, .site-nav')) continue;
    for (const a of ['title', 'aria-label', 'placeholder']) {
      const v = e.getAttribute(a);
      if (v && v.trim()) texts.push([a, v.trim()]);
    }
  }
  return texts;
}"""


def _history_strings(r: Run, errors: bool = False) -> set[str]:
    """The texts of the history the pages replay from the journal, emitted before the last
    change of language: the last model load's steps and the startup diagnostic's checks, and
    with `errors` the errors (`harness_error`, that /diagnostic replays as lines of its checks:
    a provider's refusal, a failed download), kept as they were said. Every other text the
    session sends is in the current language (languages 5/5): a card's reason or a state is
    never set aside."""
    with r.ev._lock:
        items = list(r.ev.items)
    changes = [e["seq"] for e in items if e["kind"] == "language_changed"]
    if not changes:
        return set()
    found: set[str] = set()

    def walk(value: Any) -> None:
        if isinstance(value, str):
            found.add(" ".join(value.split()))
        elif isinstance(value, dict):
            for item in value.values():
                walk(item)
        elif isinstance(value, list):
            for item in value:
                walk(item)

    history = ("model_load_started", "model_load_step", "model_load_ended", "diagnostic_check")
    if errors:
        history += ("harness_error",)
    walk([e.get("payload") for e in items if e["seq"] < changes[-1] and e["kind"] in history])
    return found


def _french_left(r: Run, lang: str) -> list[str]:
    """The texts of the page that are a French value of the catalogue (whole texts), what
    the session sent included (languages 5/5: its messages are translated), the journal's
    history before the change of language and the literals of the `lang` catalogue
    (`_literals`) aside."""
    patterns = _french_patterns(lang)
    literals = _literals(
        _ui_catalogue("fr") | _message_catalogue("fr"),
        _ui_catalogue(lang) | _message_catalogue(lang),
    )
    history = _history_strings(r)
    found = []
    for where, text in r.page.evaluate(_VISIBLE_TEXTS_JS):
        folded = " ".join(text.split())
        if folded.removeprefix("— ") in history or folded in literals:
            continue
        for key, pattern in patterns:
            if pattern.fullmatch(text):
                found.append(f"{where} « {text[:80]} » ({key})")
                break
    return sorted(set(found))


def _switch_language(r: Run, lang: str) -> None:
    r.wait_idle()
    # The open page would reload itself on `language_changed`, racing `goto_app`: left first.
    r.page.goto("about:blank")
    cleared = r.api("POST", "/api/intentions/clear_conversation", {})
    changed = r.api("POST", "/api/intentions/language", {"language": lang})
    if cleared.status_code != 200 or changed.status_code != 200:
        raise RuntimeError(f"langue {lang} : {cleared.status_code} {changed.text[:160]}")
    r.goto_app()
    r.wait_idle()


def s_ui_language(r: Run) -> None:
    """Languages (2/5): the main screen in `fr`, `en` then `de`, after a turn. In `en` and
    `de`: no French text of the catalogue (texts and attributes), `<html lang>`, numbers in
    the language's format, `t()`'s plurals. In each language, at 1280 and 1600 px, normal and
    projection mode: the top bar whole on one line, its names readable (about six characters
    of the scenario, the model's hosting and name, the model picker); captures in German. In
    German, `/api/ui_texts` unreachable: the HTML's French, `t()` gives its keys. Always ends in
    French, at rest."""
    page = r.page
    try:
        _ui_language(r)
    finally:
        page.unroute("**/api/ui_texts")
        page.set_viewport_size({"width": 1600, "height": 1000})
        if page.evaluate("() => document.documentElement.classList.contains('projection')"):
            _toggle_projection(page)
        if r.state().get("language") != "fr":
            r.wait_idle()
            _switch_language(r, "fr")
        r.check(r.state()["language"] == "fr", "nettoyage : retour au français")


_THOUSANDS = {"en": r"\d,\d{3}", "de": r"\d\.\d{3}"}

# The names of the top bar: the part of each that shows, against its first six characters
# and « … » in its own font (its globe too, for the hosting chip), or its whole text when
# shorter. A native list loses its arrow's width (1.25 em) besides its padding.
_READABLE_NAMES_JS = """() => {
  const ctx = document.createElement('canvas').getContext('2d');
  const problems = [];
  const names = {
    'sélecteur de scénario': document.getElementById('scenario-picker'),
    'hébergement du modèle': document.querySelector('#model-indicator > :first-child'),
    'nom du modèle': document.querySelector('#model-indicator .model-indicator-name'),
    'sélecteur de modèle': document.getElementById('model-picker'),
  };
  for (const [name, e] of Object.entries(names)) {
    if (!e || !e.checkVisibility()) { problems.push(`${name} absent`); continue; }
    const cs = getComputedStyle(e);
    ctx.font = cs.font;
    const em = parseFloat(cs.fontSize);
    const padding = parseFloat(cs.paddingLeft) + parseFloat(cs.paddingRight);
    let shown = e.clientWidth - padding;
    let text, full;
    if (e.tagName === 'SELECT') {
      text = e.options[e.selectedIndex]?.text ?? '';
      full = ctx.measureText(text).width;
      shown -= 1.25 * em;
    } else {
      text = e.innerText;
      full = e.scrollWidth - padding;
    }
    const before = getComputedStyle(e, '::before').content;
    const prefix = before && before !== 'none' && before !== 'normal' ? JSON.parse(before) : '';
    const need = Math.min(full, ctx.measureText(prefix + text.trim().slice(0, 6) + '…').width);
    if (shown + 1 < need) {
      const say = `${Math.round(shown)} px visibles sur ${Math.round(need)}`;
      problems.push(`${name} « ${text.trim()} » : ${say}`);
    }
  }
  // The gauge's figures, whole (not six characters: a figure cut says nothing).
  const figures = document.getElementById('gauge-figures');
  if (figures.scrollWidth > figures.clientWidth + 1) {
    const missing = figures.scrollWidth - figures.clientWidth;
    problems.push(`chiffres de la jauge « ${figures.textContent} » coupés de ${missing} px`);
  }
  return problems;
}"""


def _readable_bar(r: Run, lang: str) -> None:
    """At 1280 and 1600 px, normal and projection mode: the bar whole, its names readable, the
    « Affichage ▾ » menu whole; captures in German."""
    page = r.page
    system = _ui_catalogue(lang)["common.theme.system"]
    for width, height in ((1280, 720), (1600, 1000)):
        page.set_viewport_size({"width": width, "height": height})
        for projection in (False, True):
            if projection:
                _toggle_projection(page)
            time.sleep(0.4)
            mode = "projection" if projection else "normal"
            fits, detail = _bar_fits(r)
            names = page.evaluate(_READABLE_NAMES_JS)
            menu = _display_menu_picker(r, system)
            panels = _bar_panels_problems(r)
            if not fits or names:  # what each control of the bar takes, to see who to trim
                detail += " ; " + page.evaluate(
                    "() => [...document.querySelectorAll('.top-bar > *')]"
                    ".filter(e => e.checkVisibility())"
                    ".map(e => `${e.id || e.className} ${Math.round(e.offsetWidth)}`).join(', ')"
                )
            r.check(
                fits and not names and not menu and not panels,
                f"{lang}, {width} × {height}, mode {mode} : barre commune et barre de l'atelier "
                "entières sur une ligne, la seconde sous les volets, « Fenêtre » et « Volets ▾ » "
                "entiers au-dessus d'elle, scénario, hébergement et nom du modèle, sélecteur de "
                "modèle lisibles (≈ 6 caractères), chiffres de la jauge entiers",
                f"{detail} ; {names} {menu} {panels}",
            )
            if lang == "de":
                r.shot(f"ui-language-de-{width}-{mode}")
            if projection:
                _toggle_projection(page)
    page.set_viewport_size({"width": 1600, "height": 1000})


def _ui_plurals(r: Run, lang: str) -> None:
    """Matrix « Pluriel »: `t()` of the page's `i18n.js`, `count` 1 then 2, on a `.one` /
    `.other` key: the two forms of the catalogue."""
    forms = r.page.evaluate(
        "async () => { const m = await import('/static/i18n.js'); await m.ready;"
        " return [1, 2].map((count) => m.t('common.count.token', { count })); }"
    )
    catalogue = _ui_catalogue(lang)
    expected = [
        catalogue["common.count.token.one"].replace("{count}", "1"),
        catalogue["common.count.token.other"].replace("{count}", "2"),
    ]
    r.check(
        forms == expected and forms[0] != forms[1],
        f"{lang} : t() choisit .one pour 1 et .other pour 2 (Intl.PluralRules)",
        f"{forms} / attendu {expected}",
    )


def _ui_route_down(r: Run) -> None:
    """Matrix « Route injoignable »: `/api/ui_texts` aborted, the page reloaded: the HTML keeps
    its French, `t()` gives the key and says so in the console. Then the route back."""
    page = r.page
    warnings: list[str] = []

    def listener(message: Any) -> None:
        if message.type == "warning":
            warnings.append(message.text)

    page.route("**/api/ui_texts", lambda route: route.abort())
    page.on("console", listener)
    try:
        r.reload_app()
        time.sleep(0.5)
        send = page.inner_text("#composer-send")
        french = _ui_catalogue("fr")["main.composer.send"]
        key = page.evaluate("async () => (await import('/static/i18n.js')).t('main.composer.send')")
        said = [w for w in warnings if w.startswith("i18n :")]
        r.check(
            send == french and key == "main.composer.send" and _html_lang(r) == "fr" and said,
            "route /api/ui_texts injoignable : le HTML garde son français, t() rend la clé, "
            "la console le signale",
            f"« {send} » · t() = {key} · lang={_html_lang(r)} · {said[:2]}",
        )
    finally:
        page.remove_listener("console", listener)
        page.unroute("**/api/ui_texts")
        r.reload_app()
    r.check(
        page.inner_text("#composer-send") == _ui_catalogue("de")["main.composer.send"],
        "route rétablie : la page revient en allemand",
    )


def _ui_language(r: Run) -> None:
    page = r.page
    for lang in ("fr", "en", "de"):
        page.set_viewport_size({"width": 1600, "height": 1000})
        _switch_language(r, lang)
        r.launch("native_tools")
        r.send({"fr": "Bonjour", "en": "Hello", "de": "Hallo"}[lang])
        r.wait_idle()
        time.sleep(0.5)
        if lang != "fr":
            _open_display(page)
            left = _french_left(r, lang)
            _close_display(page)
            figures = page.inner_text("#gauge-figures")
            r.check(
                not left,
                f"{lang} : aucun texte français du catalogue à l'écran (textes, title, "
                "aria-label, placeholder), après un tour",
                "; ".join(left[:12]),
            )
            r.check(
                _html_lang(r) == lang and re.search(_THOUSANDS[lang], figures) is not None,
                f"{lang} : <html lang={lang}>, nombres au format de la langue",
                f"lang={_html_lang(r)} · {figures}",
            )
            _ui_plurals(r, lang)
        _readable_bar(r, lang)
    r.shot_element("ui-language-de-barre", ".top-bar")
    r.shot_element("ui-language-de-barre-commune", ".site-nav")
    _ui_route_down(r)


def _content(lang: str, rel: str) -> Any:
    """`content/{rel}` in `lang` (its translation, else the French file)."""
    import yaml

    translated = REPO / "content" / "i18n" / lang / rel
    path = translated if lang != "fr" and translated.is_file() else REPO / "content" / rel
    return yaml.safe_load(path.read_text(encoding="utf-8"))


def _demo_text(lang: str, rel: str) -> str:
    translated = REPO / "content" / "i18n" / lang / "demo_files" / rel
    path = (
        translated
        if lang != "fr" and translated.is_file()
        else REPO / "content" / "demo_files" / rel
    )
    return path.read_text(encoding="utf-8")


def _flat(text: str) -> str:
    return " ".join(text.split())


def _paragraphs(brick: dict[str, Any]) -> list[str]:
    """A brick's explanation, each paragraph and each bullet, as the page shows them."""
    return [
        _flat(item)
        for block in brick["explanation_text"]
        for item in (block if isinstance(block, list) else [block])
    ]


def s_content_language(r: Run) -> None:
    """Languages (3/5): in `en` then `de`, `native_tools` launched: its title, instructions and
    prompts, the Tools brick's explanation, all of the language and no French value of the
    scope that differs; a forced `read_file` (preset) reads the translated demonstration file,
    shown in Orchestration; in German, H1 refuses `confidentiel/`. Captures in German at 1280
    and 1600 px, normal and projection mode. Always ends in French, at rest."""
    page = r.page
    try:
        for lang in ("en", "de"):
            _content_language(r, lang)
    finally:
        page.set_viewport_size({"width": 1600, "height": 1000})
        if page.evaluate("() => document.documentElement.classList.contains('projection')"):
            _toggle_projection(page)
        # What the slice turned on, turned off again; a failure here never masks its result.
        try:
            r.wait_idle()
            r.api("POST", "/api/intentions/brick", {"brick": "hooks", "wanted": False})
        except Exception as exc:  # noqa: BLE001 - cleaning up only
            print(f"  nettoyage : brique Hooks non éteinte ({exc})")
        try:
            r.show_forced(False)
        except Exception as exc:  # noqa: BLE001 - cleaning up only
            print(f"  nettoyage : actions forcées non masquées ({exc})")
        if r.state().get("language") != "fr":
            r.wait_idle()
            _switch_language(r, "fr")
        r.check(r.state()["language"] == "fr", "nettoyage : retour au français")


def _content_language(r: Run, lang: str) -> None:
    page = r.page
    page.set_viewport_size({"width": 1600, "height": 1000})
    _switch_language(r, lang)
    r.launch("native_tools")
    time.sleep(0.5)
    scenario = _content(lang, "scenarios.yaml")["scenarios"]["native_tools"]
    french = _content("fr", "scenarios.yaml")["scenarios"]["native_tools"]
    brick, french_brick = _content(lang, "bricks/tools.yaml"), _content("fr", "bricks/tools.yaml")

    # The scenario: its title in the picker, its instructions, its prompts.
    title = page.locator("#scenario-picker option:checked").inner_text()
    guide = _flat(page.locator("#scenario-info-popover .scenario-info-text").text_content() or "")
    prompts = page.locator("#suggested-prompts button").all_inner_texts()
    r.check(
        scenario["title_text"] in title
        and guide.endswith(_flat(scenario["description_text"]))
        and [_flat(p) for p in prompts] == [_flat(p) for p in scenario["prompts"]],
        f"{lang} : titre, consigne et prompts suggérés de native_tools dans la langue",
        f"« {title} » · « {guide[:80]} » · {prompts}",
    )

    # The Tools brick's explanation, opened from its « ? ».
    r.card(brick["label_text"]).locator(".brick-help").click()
    explain = page.locator("#explain-tools")
    expect(explain).to_be_visible(timeout=5000)
    shown = _flat(explain.inner_text())
    missing = [p[:60] for p in _paragraphs(brick) if p not in shown]
    r.check(
        not missing,
        f"{lang} : l'aide de la brique {brick['label_text']} est celle de la langue",
        f"absents : {missing}",
    )
    if lang == "de":
        for width, height in ((1280, 720), (1600, 1000)):
            page.set_viewport_size({"width": width, "height": height})
            for projection in (False, True):
                if projection:
                    _toggle_projection(page)
                    r.card(brick["label_text"]).locator(".brick-help").click()
                    expect(explain).to_be_visible(timeout=5000)
                time.sleep(0.4)
                mode = "projection" if projection else "normal"
                r.shot(f"content-language-de-{width}-{mode}")
                if projection:
                    page.keyboard.press("Escape")
                    _toggle_projection(page)
        page.set_viewport_size({"width": 1600, "height": 1000})
    page.keyboard.press("Escape")

    # No French value of the scope that differs from its translation.
    body = _flat(page.locator("body").inner_text())
    french_values = [french["title_text"], french["description_text"], *french["prompts"]]
    french_values += _paragraphs(french_brick) + [french_brick["label_text"]]
    translated = {
        _flat(v) for v in [*scenario.values(), *scenario["prompts"]] if isinstance(v, str)
    }
    translated |= set(_paragraphs(brick)) | {brick["label_text"]}
    left = [
        _flat(v)[:60]
        for v in french_values
        if _flat(v) not in translated
        and (_flat(v) in body if len(_flat(v)) > 12 else f" {_flat(v)} " in f" {body} ")
    ]
    r.check(not left, f"{lang} : aucune valeur française du périmètre à l'écran", f"{left}")

    # A forced `read_file` on a preset: the translated demonstration file, in Orchestration.
    tools = _content(lang, "tools.yaml")["tools"]["read_file"]
    notes = next(p for p in tools["presets"] if p["args"]["path"] == "notes_reunion.txt")
    ended = _forced_read(r, brick["label_text"], notes["label_text"], lang)
    expected = _demo_text(lang, "notes_reunion.txt")
    first = next(line for line in expected.splitlines() if line.strip())
    step = page.locator("#orch-scroll .turn-step").filter(
        has_text=re.compile(f"read_file|{re.escape(tools['label_text'])}")
    )
    if not step.last.locator(".turn-step-body").count():
        step.last.locator(".turn-step-line").click()
    time.sleep(0.3)
    orch = _flat(step.last.text_content() or "")
    r.check(
        bool(ended)
        and ended[-1]["status"] == "ok"
        and ended[-1]["result"].strip() == expected.strip()
        and expected != _demo_text("fr", "notes_reunion.txt"),
        f"{lang} : read_file forcé (préréglage « {notes['label_text']} ») lit le fichier traduit",
        str(ended[-1] if ended else None)[:200],
    )
    r.check(
        _flat(first) in orch,
        f"{lang} : Orchestration montre le contenu traduit",
        "" if _flat(first) in orch else f"« {first[:60]} » absent",
    )

    # German: H1 refuses `confidentiel/`, as in French.
    if lang == "de":
        seq = r.ev.mark()
        r.api("POST", "/api/intentions/brick", {"brick": "hooks", "wanted": True})
        r.ev.wait("bricks_changed", seq, timeout=10)
        secret = next(
            p for p in tools["presets"] if p["args"]["path"] == "confidentiel/budget_projet.txt"
        )
        seq = r.ev.mark()
        _forced_read(r, brick["label_text"], secret["label_text"], lang)
        decided = [e["payload"] for e in r.ev.since(seq, "hook_decided")]
        r.check(
            any(d["hook"] == "h1" and d["decision"] == "block" for d in decided)
            and not r.ev.since(seq, "tool_ended"),
            "de : H1 refuse confidentiel/budget_projet.txt (préréglage "
            f"« {secret['label_text']} »)",
            str([(d["hook"], d["decision"]) for d in decided]),
        )


def _forced_read(r: Run, tools_card: str, preset: str, lang: str) -> list[dict[str, Any]]:
    """Arms `read_file` with `preset` (its button and the form's « Armer » found by their
    role, whatever the language), sends a prompt; returns this turn's `tool_ended`."""
    page = r.page
    r.show_forced(True)
    r.open_options(tools_card)
    seq = r.ev.mark()
    button = page.locator('[data-focus-key="force:tools:read_file"]')
    if button.get_attribute("aria-expanded") != "true":
        button.click()
    form = page.locator(".force-form")
    expect(form).to_be_visible(timeout=5000)
    form.locator("select").first.select_option(label=preset)
    form.locator("button.force-arm").click()
    r.ev.wait("armed_actions_changed", seq, lambda p: bool(p["actions"]), timeout=10)
    seq = r.ev.mark()
    r.send({"en": "Read this file.", "de": "Lies diese Datei."}[lang])
    r.wait_idle()
    time.sleep(0.5)
    return [e["payload"] for e in r.ev.since(seq, "tool_ended")]


# ---------- languages (4/5): the workshops, the annex pages and the RAG in the language ----------

# Lot 3 of 2026-10-04: « Diagnostic et modèles » holds the models' table (`models` texts).
ANNEX_PAGES = ("llm", "rag", "diagnostic")
ANNEX_QUESTIONS = {
    "en": "How many characters must a password have at least at Exemplia?",
    "de": "Wie viele Zeichen muss ein Passwort bei Exemplia mindestens haben?",
}


def _yaml_leaves(tree: Any, prefix: str = "") -> dict[str, str]:
    """The texts of a YAML tree, by dotted key (numbers and lists aside)."""
    found: dict[str, str] = {}
    if isinstance(tree, dict):
        for key, value in tree.items():
            found |= _yaml_leaves(value, f"{prefix}{key}.")
    elif isinstance(tree, str):
        found[prefix.rstrip(".")] = " ".join(tree.split())
    return found


def _annex_patterns(
    lang: str,
) -> tuple[list[tuple[str, re.Pattern[str]]], set[str]]:
    """The French values of the story's scope whose `lang` value differs: the sections
    `common`, `llm`, `rag`, `diagnostic` and `models` of `ui.yaml`, and the workshops'
    `llm_lab.yaml` and `rag_lab.yaml`. As `_french_patterns`: a variable is any text, and
    only fixed words of six letters at least say something. With them, the literals of the
    `lang` catalogue (`_literals`)."""
    french, translated = {}, {}
    for key, value in _ui_catalogue("fr").items():
        if key.split(".")[0] in ("common", *ANNEX_PAGES, "models"):
            french[f"ui.{key}"] = " ".join(value.split())
    for key, value in _ui_catalogue(lang).items():
        translated[f"ui.{key}"] = " ".join(value.split())
    for rel in ("llm_lab.yaml", "rag_lab.yaml", "mcp_lab.yaml"):
        french |= {f"{rel}:{k}": v for k, v in _yaml_leaves(_content("fr", rel)).items()}
        translated |= {f"{rel}:{k}": v for k, v in _yaml_leaves(_content(lang, rel)).items()}
    # Languages 5/5 (story 7 of 2026-09-30): the backend's messages too.
    french |= _message_catalogue("fr")
    translated |= _message_catalogue(lang)
    return _value_patterns(french, translated), _literals(french, translated)


def _annex_french_left(r: Run, lang: str) -> list[str]:
    """As `_french_left`, on an annex page, with the annex catalogue (languages 5/5: what
    the session sent is no longer set aside, the journal's history excepted)."""
    patterns, literals = _annex_patterns(lang)
    history = _history_strings(r, errors=True)
    found = []
    for where, text in r.page.evaluate(_VISIBLE_TEXTS_JS):
        text = " ".join(text.split())
        if text.removeprefix("— ") in history:  # a check's line: « — {its text} »
            continue
        if text in literals:  # a value of the page's language, whatever pattern reads it
            continue
        for key, pattern in patterns:
            if pattern.fullmatch(text):
                found.append(f"{where} « {text[:80]} » ({key})")
                break
    return sorted(set(found))


def _goto_annex(r: Run, name: str) -> None:
    """An annex page, once it rendered in the session's language."""
    page = r.page
    if name == "llm":
        _goto_lab(r)
    elif name == "rag":
        _goto_rag_lab(r)
    else:
        _goto_diagnostic(r)
        # A card unfolded: its sections and states in the language too.
        _unfold(page.locator("#cloud-models .model-card").first)
    time.sleep(0.5)


def _annex_page(r: Run, lang: str, name: str) -> None:
    _goto_annex(r, name)
    left = _annex_french_left(r, lang)
    r.check(
        not left and _html_lang(r) == lang,
        f"{lang} : /{name} sans texte français du catalogue (ui.yaml, ateliers), "
        f"<html lang={lang}>",
        f"lang={_html_lang(r)} · " + "; ".join(left[:10]),
    )


def _titles(lang: str) -> set[str]:
    return {d["title_text"] for d in _content(lang, "rag.yaml")["documents"]}


def _annex_rag_turn(r: Run) -> None:
    """German: the index built from the card (the fake embedding model, the shipped index
    being Granite's), then a RAG turn whose excerpts are German, titles included."""
    lang = "de"
    rag_texts = _content(lang, "rag.yaml")
    brick = _content(lang, "bricks/rag.yaml")["label_text"]
    r.launch("rag")
    rag = r.bricks()["rag"]
    if rag.get("download") is not None:  # alone: the fake model's file, served first
        httpx.post(f"{r.stack.fake_url}/_e2e/model_ready", timeout=5, trust_env=False)
        seq = r.ev.mark()
        r.api("POST", "/api/intentions/download_model", {"target": rag["download"]["target"]})
        r.ev.wait(
            "bricks_changed",
            seq,
            lambda p: (
                next(b for b in p["bricks"] if b["id"] == "rag").get("build_index") is not None
            ),
            30,
        )
        r.wait_idle()
    card = r.card(brick)
    build = card.get_by_role("button", name=rag_texts["build_label_text"])
    expect(build).to_be_visible(timeout=10_000)
    target = r.stack.data_dir / "rag_index.de.sqlite"
    r.check(
        not target.exists() and "rag_index.de.sqlite" in card.inner_text(),
        "de : index allemand absent, « Construire l'index » proposé dans la langue",
        card.inner_text()[:200],
    )
    seq = r.ev.mark()
    build.click()
    r.ev.wait(
        "bricks_changed",
        seq,
        lambda p: next(b for b in p["bricks"] if b["id"] == "rag")["available"],
        60,
    )
    r.check(target.is_file(), "de : la carte construit data/rag_index.de.sqlite", str(target))
    r.wait_idle()
    seq = r.ev.mark()
    ended = r.send(ANNEX_QUESTIONS[lang])
    searched = r.ev.since(seq, "rag_search_ended")
    body = json.dumps(r.fake_calls()[-1]["messages"], ensure_ascii=False)
    first = re.search(r"Auszug 1 — ([^:\n]+):", body)
    french = sorted(t for t in _titles("fr") if t in body)
    r.check(
        ended["payload"]["status"] == "completed"
        and len(searched) == 1
        and first is not None
        and first.group(1) in _titles(lang)
        and not french,
        "de : tour RAG, « Auszug 1 — » et un titre allemand dans le corps envoyé, aucun titre "
        "français",
        f"{first.group(0) if first else None} · titres français : {french}",
    )


def _annex_rag_lab(r: Run) -> None:
    """German: a run of the RAG workshop, its excerpts and their titles German."""
    lang = "de"
    _goto_rag_lab(r)
    question = _content(lang, "rag_lab.yaml")["default_question_text"]
    ended, seq = _rag_lab_run(r, question)
    items = [
        item
        for e in r.ev.since(seq, "rag_lab_stage_ended")
        for item in e["payload"].get("items") or []
    ]
    titles = {item["title_text"] for item in items}
    r.check(
        ended["payload"]["status"] != "error"
        and bool(items)
        and titles <= _titles(lang)
        and not titles & _titles("fr"),
        "de : une chaîne de l'atelier RAG, ses extraits et leurs titres allemands",
        f"{ended['payload']['status']} · {sorted(titles)}",
    )
    time.sleep(0.5)


def _french_message_values(lang: str) -> list[str]:
    """The French values of `messages.yaml` whose `lang` value differs, `{…}` cut out, the
    pieces of twelve characters at least: none may reach the model in `lang`."""
    french, translated = _message_catalogue("fr"), _message_catalogue(lang)
    pieces = set()
    for key, value in french.items():
        if translated.get(key) != value:
            pieces |= {p.strip() for p in _UI_VAR.split(value) if len(p.strip()) >= 12}
    return sorted(pieces)


def _backend_tool_error(r: Run, lang: str) -> None:
    """A call to a tool that does not exist: the refusal the model reads (the tool message
    of the fake's last request) in `lang`, without a French value of the catalogue."""
    r.api("POST", "/api/intentions/brick", {"brick": "tools", "wanted": True})
    r.send("[outil-inconnu] test")
    r.wait_idle()
    tool_messages = [
        m.get("content") or ""
        for call in r.fake_calls()
        for m in call.get("messages") or []
        if m.get("role") == "tool"
    ]
    last = tool_messages[-1] if tool_messages else ""
    tail = _UI_VAR.split(_message_catalogue(lang)["messages:tools.reject"])[-1].strip()
    left = [v for v in _french_message_values(lang) if v in last]
    r.check(
        bool(last) and tail in last and not left,
        f"{lang} : le refus d'un outil inconnu lu par le modèle est dans la langue",
        f"{last[:160]!r} · {left[:3]}",
    )
    _clear_conversation(r)


def s_backend_language(r: Run) -> None:
    """Languages (5/5), story 7 of 2026-09-30: in `en` then `de`, the backend's messages.
    The refusal of an unknown tool as the model reads it; the main screen (cards, their
    reasons, the log) and « Diagnostic et modèles » without a French value of
    `messages.yaml` or `ui.yaml`; captures in German at 1280 and 1600 px, normal and
    projection mode, on the main screen. Always ends in French, at rest."""
    page = r.page
    try:
        for lang in ("en", "de"):
            page.set_viewport_size({"width": 1600, "height": 1000})
            r.goto_app()  # an annex page does not replay the journal
            _switch_language(r, lang)
            _backend_tool_error(r, lang)
            r.goto_app()
            r.wait_idle()
            left = _french_left(r, lang)
            r.check(
                not left,
                f"{lang} : écran principal sans message français du backend",
                "; ".join(left[:10]),
            )
            for name in ("diagnostic",):  # lot 3 of 2026-10-04: /models merged into it
                _annex_page(r, lang, name)
            if lang == "de":
                r.goto_app()
                r.wait_idle()
                for projection in (False, True):
                    if projection:
                        _toggle_projection(page)
                    for width, height in ((1280, 720), (1600, 1000)):
                        page.set_viewport_size({"width": width, "height": height})
                        time.sleep(0.4)
                        mode = "projection" if projection else "normal"
                        r.shot(f"backend-language-de-{mode}-{width}")
                    if projection:
                        _toggle_projection(page)
                page.set_viewport_size({"width": 1600, "height": 1000})
    finally:
        page.set_viewport_size({"width": 1600, "height": 1000})
        r.goto_app()
        if page.evaluate("() => document.documentElement.classList.contains('projection')"):
            _toggle_projection(page)
        if r.state().get("language") != "fr":
            r.wait_idle()
            _switch_language(r, "fr")
        r.check(r.state()["language"] == "fr", "nettoyage : retour au français")


def s_annex_language(r: Run) -> None:
    """Languages (4/5): in `en` then `de`, « LLM nu », the RAG workshop, the diagnostic and
    the models page: no French text of the story's catalogue (ui.yaml's sections, the
    workshops' files), `<html lang>`. In German: the index built from the RAG card, a RAG
    turn sending German excerpts and titles, a workshop run; captures at 1280 and 1600 px
    (no projection mode outside `/`). Always ends in French, at rest, the RAG brick off."""
    page = r.page
    try:
        for lang in ("en", "de"):
            page.set_viewport_size({"width": 1600, "height": 1000})
            r.goto_app()  # an annex page does not replay the journal
            _switch_language(r, lang)
            if lang == "de":
                _annex_rag_turn(r)
                _annex_rag_lab(r)
            for name in ANNEX_PAGES:
                _annex_page(r, lang, name)
                if lang == "de":
                    for width, height in ((1280, 720), (1600, 1000)):
                        page.set_viewport_size({"width": width, "height": height})
                        time.sleep(0.4)
                        nav = _site_nav_problems(r)
                        r.check(
                            not nav,
                            f"de, /{name}, {width} × {height} : barre commune entière, sur une "
                            "ligne",
                            "; ".join(nav),
                        )
                        r.shot(f"annex-language-de-{name}-{width}")
                        if name == "diagnostic" and width == 1280:
                            _models_window_then_network(r)  # story 3 of 2026-09-30
                    page.set_viewport_size({"width": 1600, "height": 1000})
    finally:
        page.set_viewport_size({"width": 1600, "height": 1000})
        try:
            r.goto_app()
            r.wait_idle()
            r.api("POST", "/api/intentions/brick", {"brick": "rag", "wanted": False})
        except Exception as exc:  # noqa: BLE001 - cleaning up only
            print(f"  nettoyage : brique RAG non éteinte ({exc})")
        if r.state().get("language") != "fr":
            _switch_language(r, "fr")
        r.check(
            r.state()["language"] == "fr" and not r.bricks()["rag"]["wanted"],
            "nettoyage : retour au français, brique RAG éteinte",
        )


def _first_turn_after(r: Run, gesture: str, turn_id: str) -> None:
    seq = r.ev.mark()
    r.send("Bonjour")
    started = [e["turn_id"] for e in r.ev.since(seq, "turn_started")]
    title = r.page.locator("#orch-scroll .turn-group-title", has_text="Tour ")
    shown = title.all_inner_texts()
    tooltip = title.last.get_attribute("title") if shown else None
    total = r.page.locator("#ctx .ctx-total").inner_text()
    r.check(
        started == [turn_id]
        and shown == ["Tour 1"]
        and tooltip == f"Identifiant du tour dans le journal : {turn_id}"
        and total.startswith("Tour 1 · "),
        f"après « {gesture} » : Orchestration et Contexte LLM « Tour 1 », infobulle et journal "
        f"en {turn_id}",
        f"journal {started} · titres {shown} · infobulle « {tooltip} » · contexte « {total[:40]} »",
    )


def s_stream_resync(r: Run) -> None:
    """A1, same process: `/api/state` and the stream name the same instance, the page does
    not reload; they differ (a relaunch between the two), it reloads once; no `/api/state`,
    the stream's instance is the reference. (A relaunch with the tab open: `s_relaunch`.)"""
    navigations: list[str] = []

    def on_nav(frame: Any) -> None:
        if frame == r.page.main_frame:
            navigations.append(frame.url)

    def other_instance(route: Any) -> None:
        # Every `/api/state` reader of the first load (site-nav.js and app.js) gets the other
        # instance; the reload's own read gets the real one.
        if len(navigations) > 1:
            route.fallback()
            return
        route.fulfill(json=route.fetch().json() | {"instance_id": "autre-instance"})

    r.page.on("framenavigated", on_nav)
    try:
        for label, handler, expected in [
            ("même instance dans l'état et le flux : aucun rechargement", None, 1),
            ("état et flux d'instances différentes : un seul rechargement", other_instance, 2),
            (
                "sans /api/state : l'instance du flux sert de référence, aucun rechargement",
                lambda route: route.abort(),
                1,
            ),
        ]:
            navigations.clear()
            if handler:
                r.page.route("**/api/state", handler)
            r.page.goto(f"{r.stack.app_url}/")
            # Not time.sleep: the sync API delivers `framenavigated` only while it runs.
            # The page is usable from `/api/state` on; the reload follows the stream's first event.
            r.page.wait_for_timeout(3000)
            r.wait_idle()
            r.page.wait_for_timeout(1000)
            r.check(len(navigations) == expected, label, f"{len(navigations)} navigation(s)")
            r.page.unroute("**/api/state")
        ended = r.send("Bonjour")
        r.check(ended["payload"]["status"] == "completed", "puis un tour aboutit")
    finally:
        r.page.remove_listener("framenavigated", on_nav)


def s_stream_lost(r: Run) -> None:
    """Story 2 of the deferred leftovers (E003): the live stream refused three times in a
    row, the top bar says « Connexion au serveur perdue, nouvel essai… »; the stream back, the
    first event clears it, without a reload (`Last-Event-ID` resumes)."""
    lost_text = _ui_catalogue("fr")["main.top_bar.connection_lost"]
    status = r.page.locator("#top-status")
    try:
        r.page.route("**/api/stream", lambda route: route.abort())
        r.page.goto(f"{r.stack.app_url}/")
        shown = r.page.wait_for_function(
            "() => document.body.dataset.connection === 'lost'", timeout=15000
        )
        r.check(
            bool(shown) and status.inner_text() == lost_text,
            "flux refusé trois fois : « Connexion au serveur perdue, nouvel essai… » dans la "
            "barre de l'atelier (#top-status)",
            f"« {status.inner_text()} »",
        )
        navigations: list[str] = []

        def on_nav(frame: Any) -> None:
            if frame == r.page.main_frame:
                navigations.append(frame.url)

        r.page.on("framenavigated", on_nav)
        r.page.unroute("**/api/stream")
        r.page.wait_for_function(
            "() => document.body.dataset.connection === undefined", timeout=15000
        )
        r.wait_idle()
        r.page.remove_listener("framenavigated", on_nav)
        r.check(
            status.inner_text() != lost_text and navigations == [],
            "flux revenu : l'indicateur s'efface au premier événement, sans rechargement",
            f"« {status.inner_text()} » · {len(navigations)} navigation(s)",
        )
        ended = r.send("Bonjour")
        r.check(ended["payload"]["status"] == "completed", "puis un tour aboutit")
    finally:
        r.page.unroute("**/api/stream")


def _picker_options(r: Run) -> dict[str, bool]:
    """The model picker's options: label → disabled."""
    return dict(
        r.page.eval_on_selector_all(
            "#model-picker option", "os => os.map(o => [o.textContent, o.disabled])"
        )
    )


def s_model_switch(r: Run) -> None:
    """Story 17: the hot switch from the top bar (warning, stopwatch, conversation kept, model
    line, replay, compare), then back from the diagnostic, with no « relancez »."""
    page = r.page
    a_label = "RÉSEAU · Faux fournisseur (e2e) · wavestack-fake"
    b_label = f"RÉSEAU · Faux fournisseur B (e2e) · {SECOND_MODEL}"
    r.launch("short_memory")
    r.send("Je m'appelle Pascal.")
    options = _picker_options(r)
    r.check(options.get(f"{a_label} (actif)") is True, "sélecteur : modèle actif marqué et grisé")
    r.check(
        options.get(b_label) is False, "sélecteur : le second modèle est choisissable", str(options)
    )
    r.check(
        list(options)[-1] == "Autre fichier ou clé API…",
        "sélecteur : dernière entrée « Autre fichier ou clé API… »",
    )
    # Story 11b's texts, gone with the hot switch. Other « relancez WaveStack » stay true (a
    # file read at launch only, e.g. the Compression card without the extra installed).
    body = page.inner_text("body")
    r.check(
        "Prochain lancement" not in body and "relancez WaveStack pour l'utiliser" not in body,
        "aucune mention « Prochain lancement » ni « relancez WaveStack pour l'utiliser »",
    )

    seq = r.ev.mark()
    page.select_option("#model-picker", label=b_label)
    apply = page.locator("#model-picker-apply")
    expect(apply).to_be_visible(timeout=5000)
    time.sleep(0.5)
    r.check(
        not r.ev.since(seq, "model_load_started") and page.locator("#cloud-warning").is_hidden(),
        "choisir une entrée ne fait que la noter (flèches du clavier sans effet)",
        apply.inner_text(),
    )
    apply.click()
    dialog = page.locator("#cloud-warning")
    expect(dialog).to_be_visible(timeout=5000)
    r.check(
        "Faux fournisseur B (e2e)" in dialog.inner_text(),
        "« Choisir… » : avertissement cloud dans la page, qui nomme le fournisseur",
    )
    page.click("#cloud-warning-cancel")
    time.sleep(0.5)
    r.check(
        not r.ev.since(seq, "model_load_started")
        and "wavestack-fake" in page.inner_text("#model-indicator"),
        "« Annuler » : aucun changement",
    )

    page.select_option("#model-picker", label=b_label)
    page.click("#model-picker-apply")
    expect(dialog).to_be_visible(timeout=5000)
    page.click("#cloud-warning-confirm")
    top = page.locator("#top-status")
    expect(top).to_contain_text(f"Chargement du modèle {SECOND_MODEL}…", timeout=5000)
    time.sleep(0.6)
    stopwatch = top.inner_text()
    r.check(
        re.search(r"… \d+(,\d)? s$", stopwatch) is not None,
        "barre de l'atelier : « Chargement du modèle … » avec chronomètre",
        stopwatch,
    )
    indicator = page.locator("#chat .model-load-indicator")
    r.check(
        indicator.count() == 1 and SECOND_MODEL in indicator.inner_text(),
        "Vue humain : indicateur de chargement en fin de fil",
    )
    reason = page.inner_text("#composer-reason")
    r.check(
        page.locator("#composer-input").is_disabled() and SECOND_MODEL in reason,
        "envoi désactivé pendant le chargement, avec la raison",
        reason,
    )
    r.check(page.locator("#model-picker").is_disabled(), "sélecteur désactivé au chargement")
    r.shot("22-changement-de-modele")
    ended = r.ev.wait("model_load_ended", seq, timeout=30)
    r.check(ended["payload"]["status"] == "ok", "chargement terminé", ended["payload"]["status"])
    expect(page.locator("#model-indicator")).to_contain_text(SECOND_MODEL, timeout=10_000)
    r.wait_idle()
    r.check("Je m'appelle Pascal." in page.inner_text("#chat"), "la conversation est conservée")

    r.send("Comment je m'appelle ?")
    r.check("Pascal" in r.last_answer(), "le nouveau modèle reçoit l'historique", r.last_answer())
    r.check(r.fake_calls()[-1].get("model") == SECOND_MODEL, "l'appel part avec le nouveau modèle")
    lines = page.locator("#chat .model-switch-line").all_inner_texts()
    r.check(
        lines == ["Modèle : wavestack-fake", f"Modèle : {SECOND_MODEL}"],
        "« Modèle : … » sur le premier tour, puis au changement",
        str(lines),
    )
    seq = r.ev.mark()
    r.replay()
    started = r.ev.since(seq, "turn_started")[0]["payload"]
    r.check(
        (started.get("active_model") or {}).get("ref") == SECOND_ENTRY_ID,
        "le rejeu est joué par le nouveau modèle",
    )
    page.click("#compare-turns")
    page.locator("#ctx .turn-compare-head select").first.select_option(index=0)  # A's turn
    time.sleep(0.3)
    models = page.locator(".turn-compare-model").all_inner_texts()
    r.check(
        models == ["Modèle : wavestack-fake", f"Modèle : {SECOND_MODEL}"],
        "« Comparer » affiche le modèle de chaque colonne",
        str(models),
    )
    page.locator("#ctx .turn-compare-head button").click()

    # Back to the first model from the diagnostic: « Choisir », no relaunch.
    _goto_diagnostic(r)
    row_b = _cloud_card(r, SECOND_MODEL)
    expect(row_b.locator(".model-card-head .state-pill")).to_have_text("Actif", timeout=10_000)
    r.check(True, "diagnostic : le modèle actif est lu dans la session applicative")
    row_a = _unfold(_cloud_card(r, "wavestack-fake"))
    row_a.get_by_role("button", name="Choisir ce modèle…").click()
    page.click("#cloud-warning-confirm")
    expect(row_a.locator(".card-status").last).to_have_text(
        "wavestack-fake est actif.", timeout=20_000
    )
    expect(row_a.locator(".model-card-head .state-pill")).to_have_text("Actif", timeout=10_000)
    expect(row_b.locator(".model-card-head .state-pill")).not_to_have_text("Actif")
    r.check(True, "diagnostic : « Choisir » change de modèle sans relance, issue affichée")
    body = page.inner_text("body")
    r.check("relancez WaveStack pour l'utiliser" not in body, "diagnostic : jamais « relancez »")
    page.goto(f"{r.stack.app_url}/")
    expect(page.locator("#model-indicator")).to_contain_text("wavestack-fake", timeout=10_000)
    r.wait_idle()

    # Lot E (E4): « Arrêter » during the slow load of B (`launch_app.py`): A comes back.
    stop = page.locator("#composer-stop")
    r.check(stop.is_hidden(), "« Arrêter » caché hors d'un tour ou d'un chargement")
    seq = r.ev.mark()
    page.select_option("#model-picker", label=b_label)
    page.click("#model-picker-apply")
    expect(dialog).to_be_visible(timeout=5000)
    page.click("#cloud-warning-confirm")
    r.ev.wait("model_load_started", seq, timeout=10)
    ok = True
    try:
        expect(stop).to_be_visible(timeout=5000)
    except AssertionError:
        ok = False
    r.check(ok, "« Arrêter » visible pendant le chargement du modèle")
    stop.click()
    ok, _ = r.poll(lambda: "Arrêt demandé" in top.inner_text(), 5)
    r.check(
        ok, "barre de l'atelier : « Arrêt demandé » pendant la fin de l'étape", top.inner_text()
    )
    ended = r.ev.wait("model_load_ended", seq, timeout=30)["payload"]
    r.check(
        ended["status"] == "cancelled"
        and ended["reason_text"] == "Chargement arrêté : wavestack-fake est de nouveau actif.",
        "« Arrêter » : chargement arrêté, le modèle précédent est de nouveau actif",
        f"{ended['status']} · {ended['reason_text']}",
    )
    ok = True
    try:
        expect(top).to_contain_text("Chargement arrêté", timeout=5000)
    except AssertionError:
        ok = False
    r.check(ok, "barre de l'atelier : issue « Chargement arrêté »", top.inner_text())
    expect(page.locator("#model-indicator")).to_contain_text("wavestack-fake", timeout=10_000)
    active = r.state()["active_model"] or {}
    r.check(active.get("ref") == MODEL_ENTRY_ID, "le modèle précédent est actif", str(active))
    r.wait_idle()
    r.check(stop.is_hidden(), "« Arrêter » de nouveau caché une fois le modèle rétabli")
    r.send("Encore là ?")
    r.check(
        r.fake_calls()[-1].get("model") != SECOND_MODEL,
        "le tour suivant part avec le modèle précédent",
    )
    _slow_probe_stopped(r)


SLOW_PROBE = "sonde-lente-e2e"  # `launch_app.py`: its probe is a child that only sleeps


def _probe_children(marker: str) -> list[int]:
    """The processes whose command line names `marker` (the slow probe's file)."""
    import psutil

    found = []
    for proc in psutil.process_iter(["cmdline"]):
        try:
            if any(marker in part for part in proc.info["cmdline"] or []):
                found.append(proc.pid)
        except psutil.Error:
            continue
    return found


def _slow_probe_stopped(r: Run) -> None:
    """Story 24: the memory budget and its calculation at the diagnostic, the session's own
    figure; then « Arrêter » during the probe of a file chosen hot: the child is killed at
    once, the previous model is back within 3 s, and the file is never marked incompatible."""
    import psutil

    page = r.page
    _goto_diagnostic(r)
    _open_checks(r)  # lot 3 of 2026-10-04: the checks fold once green
    memory = page.locator("#checks li", has_text="Budget mémoire")
    expect(memory).to_be_visible(timeout=10_000)
    text = memory.inner_text()
    budget = r.api("GET", "/api/diagnostic").json()["memory_budget_bytes"]
    budget_mo = f"{round(budget / 1024**2):,}".replace(",", "\u202f")
    r.check(
        "%" in text and "RAM" in text and f"Budget mémoire de WaveStack : {budget_mo} Mo" in text,
        "diagnostic : « Budget mémoire » avec son calcul, le budget des refus de la session",
        f"{budget_mo} Mo · " + text.replace("\n", " · "),
    )
    slow = r.stack.data_dir / f"{SLOW_PROBE}.gguf"  # outside the folders scanned at launch
    slow.write_bytes(b"octets quelconques, jamais charges")
    try:
        seq = r.ev.mark()
        page.fill("#model-path", str(slow))
        page.click("#submit-path")
        r.ev.wait("model_load_started", seq, timeout=10)
        ok, _ = r.poll(lambda: bool(_probe_children(SLOW_PROBE)), 10)
        r.check(ok, "sonde lente en cours (processus enfant)")
        r.goto_app()
        stop = page.locator("#composer-stop")
        ok = True
        try:
            expect(stop).to_be_visible(timeout=5000)
        except AssertionError:
            ok = False
        r.check(ok, "« Arrêter » visible pendant la sonde")
        top = page.locator("#top-status")
        clicked = time.monotonic()
        stop.click()  # the page renders « Arrêt demandé » before it even sends the intention
        after_click, tooltip = top.inner_text(), top.get_attribute("title") or ""
        ended = r.ev.wait("model_load_ended", seq, timeout=10)["payload"]
        elapsed = time.monotonic() - clicked
        r.check(
            after_click.startswith("Arrêt demandé · "),
            "barre de l'atelier : « Arrêt demandé · » après le clic",
            after_click,
        )
        r.check(
            "une sonde est interrompue tout de suite" in tooltip,
            "barre de l'atelier : l'infobulle explique le délai de l'arrêt",
            tooltip,
        )
        r.check(
            ended["status"] == "cancelled"
            and ended["reason_text"] == "Chargement arrêté : wavestack-fake est de nouveau actif."
            and elapsed < 3,
            "« Arrêter » pendant la sonde : arrêt en moins de 3 s, modèle précédent rétabli",
            f"{ended['status']} · {ended['reason_text']} · {elapsed:.1f} s",
        )
        active = r.state()["active_model"] or {}
        r.check(active.get("ref") == MODEL_ENTRY_ID, "le modèle précédent est actif", str(active))
        left = _probe_children(SLOW_PROBE)
        r.check(not left, "plus aucun processus de sonde", str(left))
        saved = json.loads((r.stack.data_dir / "settings.json").read_text(encoding="utf-8"))
        r.check(
            str(slow) not in saved.get("failed_probes", {}),
            "le fichier n'est pas marqué incompatible (failed_probes)",
            str(saved.get("failed_probes")),
        )
        errors = [
            e["payload"]
            for e in r.ev.since(seq, "harness_error")
            if "incompatible" in json.dumps(e["payload"], ensure_ascii=False)
        ]
        r.check(not errors, "aucune erreur « incompatible »", str(errors))
        r.wait_idle()
    finally:
        for pid in _probe_children(SLOW_PROBE):  # a failed check never leaves the sleeper
            try:
                psutil.Process(pid).kill()
            except psutil.Error:
                pass
        slow.unlink(missing_ok=True)


LLAMA_FILE = "faux-llama-server.gguf"
LLAMA_OPTION = f"Local · llama-server · {LLAMA_FILE}"
# Story 25: the fake Ollama's `details` give its size (and its publisher, Qwen).
OLLAMA_OPTION = "Local · Ollama · faux-ollama:latest · 0.6B"


def s_local_server(r: Run) -> None:
    """Story 18: models of already-running local servers. Detection at the diagnostic, choice
    by its « Choisir », the schema (a local process apart from the harness), a whole turn with
    a tool, a reload; back to the cloud fake model, then the served model again from the
    picker, and back."""
    page = r.page
    address = r.stack.llama_url.removeprefix("http://")
    _goto_diagnostic(r)
    llama_row = _card(r, f"server:llama_server/{LLAMA_FILE}")
    expect(llama_row).to_be_visible(timeout=20_000)
    _unfold(llama_row)
    text = llama_row.inner_text()
    r.check(
        f"llama-server · {address}" in text
        and r.stack.llama_url in text
        and "Mémoire du modèle servi" in text,
        "diagnostic : la carte du modèle servi par llama-server (origine, adresse, mémoire)",
        text.replace("\n", " · "),
    )
    r.check(
        llama_row.get_by_role("button", name="Choisir ce modèle").count() == 1
        and llama_row.locator(".model-card-head .state-pill").inner_text() == "Avertissement",
        "diagnostic : « Choisir ce modèle » sur la carte du modèle servi, « Avertissement »",
    )
    # Lot E (E1): the fake llama-server has a context of 8 192 tokens, twice the window.
    r.check(
        "relancez-le avec `-c 4096`" in text and "8\u202f192 tokens" in text,
        "diagnostic : llama-server à grand contexte, conseil « -c 4096 »",
        text.replace("\n", " · "),
    )
    ollama_row = _card(r, "server:ollama/faux-ollama:latest")
    if ollama_row.count():
        _unfold(ollama_row)
    r.check(
        ollama_row.count() == 1
        and "introuvable" in ollama_row.inner_text()
        and "is-unusable" in (ollama_row.get_attribute("class") or "")
        and ollama_row.locator(".model-card-head .state-pill").inner_text() == "Incompatible"
        and ollama_row.get_by_role("button", name="Choisir").count() == 0,
        "diagnostic : un modèle Ollama sans GGUF lisible est « Incompatible », sa raison dans la "
        "carte dépliée, sans « Choisir »",
        ollama_row.inner_text().replace("\n", " · ") if ollama_row.count() else "absent",
    )
    _unfold(llama_row)
    r.check("palier 2" not in page.inner_text("body"), "diagnostic : plus de « palier 2 »")

    # « Choisir » at the diagnostic: a hot switch from the cloud fake model, at the first
    # click (the page no longer rebuilds its rows while it replays the journal).
    seq = r.ev.mark()
    llama_row.get_by_role("button", name="Choisir ce modèle").click()
    r.ev.wait("model_load_started", seq, timeout=5)
    ended = r.ev.wait("model_load_ended", seq, timeout=30)
    r.check(ended["payload"]["status"] == "ok", "diagnostic : « Choisir » prépare le modèle servi")
    expect(page.locator("#select-model-status")).to_have_text(
        "faux-llama-server est actif.", timeout=10_000
    )
    expect(llama_row.locator(".model-card-head .state-pill")).to_have_text("Actif", timeout=10_000)
    r.check(
        llama_row.get_by_role("button", name="Choisir").count() == 0
        and "is-active" in (llama_row.get_attribute("class") or ""),
        "diagnostic : issue affichée, carte « Actif » à bordure épaisse, sans « Choisir »",
    )

    r.goto_app()
    r.launch("native_tools")
    options = _picker_options(r)
    r.check(
        options.get(f"{LLAMA_OPTION} (actif)") is True,
        "sélecteur : le modèle servi actif est marqué et grisé",
        str([o for o in options if "Local" in o]),
    )
    r.check(
        options.get(f"{OLLAMA_OPTION} (incompatible)") is True,
        "sélecteur : le modèle Ollama incompatible est grisé",
    )
    indicator = page.locator("#model-indicator")
    expect(indicator).to_contain_text("Local · llama-server", timeout=10_000)
    title = indicator.get_attribute("title") or ""
    r.check(
        "processus distinct de WaveStack" in title and address in title,
        "indicateur : « Local · llama-server », infobulle processus distinct",
        title,
    )
    r.wait_idle()
    box = page.locator("#schema .arch-zone-local .arch-server-model")
    expect(box).to_be_visible(timeout=10_000)
    r.check(
        f"llama-server · {address}" in box.inner_text()
        and box.locator(".robot").count() == 1
        and page.locator("#schema .arch-harness .robot").count() == 0
        and page.locator("#schema .arch-zone-network .robot").count() == 0,
        "schéma : robot hors du cadre Harnais, en zone Poste de travail, boîte llama-server",
        box.inner_text(),
    )

    seq = r.ev.mark()
    ended = r.send("Quelle heure est-il ?")
    r.check(ended["payload"]["status"] == "completed", "un tour complet avec le modèle servi")
    r.check(
        "D'après le résultat de l'outil" in r.last_answer(),
        "l'appel d'outil get_datetime est parsé puis exécuté",
        r.last_answer()[:120],
    )
    rendered = [e["payload"] for e in r.ev.since(seq, "context_rendered")]
    calls = [e["payload"] for e in r.ev.since(seq, "model_call_ended")]
    sent = [
        q["body"]["prompt"]
        for q in r.stack.local_requests(r.stack.llama_url)
        if q["path"] == "/completion"
    ][-2:]
    prompts = ["".join(s["text"] for s in ctx["segments"]) for ctx in rendered]
    r.check(
        len(sent) == 2 and all(p.startswith("<|im_start|>system") for p in prompts),
        "Contexte LLM : texte rendu par le harnais, gabarit compris",
    )
    r.check(
        [sum(s["tokens"] for s in ctx["segments"]) for ctx in rendered]
        == [c["prompt_tokens"] for c in calls]
        == [len(ids) for ids in sent],
        "somme des segments = prompt_tokens = ids reçus par llama-server",
        str([c["prompt_tokens"] for c in calls]),
    )
    _local_footprint(r, calls)
    # Story 32: the grouped reading of the Qwen3.5 template (the tools' JSON as trees), the
    # exact text equal to the prompt, the sections' sum equal to `prompt_tokens`.
    shown = _ctx_calls(r)
    r.check(
        [c["title"] for c in shown] == ["Appel 1 sur 2", "Appel 2 sur 2"],
        "Contexte LLM : les deux appels du tour, numérotés",
        str([c["title"] for c in shown]),
    )
    tools_row = (
        page.locator("#ctx .ctx-call")
        .first.locator(".ctx-section")
        .filter(has=page.locator(".ctx-section-label", has_text="Descriptions d'outils"))
    )
    r.check(
        tools_row.count() >= 1
        and tools_row.first.locator(".json-tree .json-key", has_text='"parameters"').count() >= 1
        and tools_row.first.locator(".ctx-section-label").count() > 1,
        "appel 1 : la ligne des descriptions d'outils montre un arbre JSON (« parameters »), "
        "sa marge empile les sources qu'il touche",
        " | ".join(tools_row.first.locator(".ctx-section-label").all_inner_texts())
        if tools_row.count()
        else "absente",
    )
    r.check(
        [sum(s["tokens"] for s in ctx["sections"]) for ctx in rendered]
        == [c["prompt_tokens"] for c in calls],
        "somme des sections = prompt_tokens, pour chaque appel",
        str([sum(s["tokens"] for s in ctx["sections"]) for ctx in rendered]),
    )
    _ctx_mode(r, "Texte exact")
    exact = [c["exact"][0] if len(c["exact"]) == 1 else None for c in _ctx_calls(r)]
    r.check(
        exact == prompts,
        "« Texte exact » : chaque texte est la jointure des segments de son appel (le prompt)",
    )
    _ctx_mode(r, "Lecture groupée")
    # Story 34: nothing left the workstation during that turn.
    summary = page.inner_text("#schema-outbound")
    r.check(
        "aucune donnée n'a quitté le poste" in summary,
        "bilan des sorties : aucune donnée n'a quitté le poste (modèle servi, outil local)",
        summary,
    )
    r.shot("23-serveur-local-llama-server")
    _braces_stay_text(r, "mode local")
    _cache_not_reused(r)

    # Story 32: a reasoning cut by the harness stays one call; the harness's note sits
    # between the reflection and the answer. The LLM nu, so that the reasoning's reserve
    # leaves room (the fake tokenizer counts one token per byte).
    r.launch("bare_llm")
    r.set_brick("Raisonnement", True)
    seq = r.ev.mark()
    ended = r.send("Bonjour [réfléchis longtemps]")
    cuts = r.ev.since(seq, "reasoning_cut")
    rendered = r.ev.since(seq, "context_rendered")
    order = (
        r.page.locator("#ctx .ctx-call")
        .last.locator(".ctx-produced.is-reasoning, .ctx-harness-note, .ctx-produced.is-answer")
        .evaluate_all(
            "ns => ns.map(n => n.classList.contains('ctx-harness-note') ? 'note'"
            " : n.classList.contains('is-reasoning') ? 'reasoning' : 'answer')"
        )
    )
    r.check(
        ended["payload"]["status"] == "completed"
        and len(cuts) == 1
        and len(rendered) == 1
        and len(_ctx_calls(r)) == 1
        and order == ["reasoning", "note", "answer"],
        "raisonnement coupé : un seul appel, la note du harnais entre la réflexion et la réponse",
        f"{ended['payload']['status']} · {len(cuts)} coupe(s), {len(rendered)} contexte(s), "
        f"ordre {order}",
    )
    r.set_brick("Raisonnement", False)

    r.reload_app()
    expect(page.locator("#model-indicator")).to_contain_text("Local · llama-server", timeout=10_000)
    expect(page.locator("#schema .arch-zone-local .arch-server-model .robot")).to_be_visible(
        timeout=10_000
    )
    r.check(True, "rechargement : indicateur et robot hors du Harnais reviennent (AD-1)")

    # Back to the cloud fake model: `relaunch` expects it saved.
    r.wait_idle()
    seq = r.ev.mark()
    page.select_option("#model-picker", label="RÉSEAU · Faux fournisseur (e2e) · wavestack-fake")
    page.click("#model-picker-apply")
    page.click("#cloud-warning-confirm")
    ended = r.ev.wait("model_load_ended", seq, timeout=30)
    r.check(ended["payload"]["status"] == "ok", "retour au modèle cloud depuis le modèle servi")
    expect(page.locator("#model-indicator")).to_contain_text("wavestack-fake", timeout=10_000)
    r.wait_idle()

    # The served model from the top bar's picker, then back again. The warning's dialog gave
    # the focus back to the picker, which is rebuilt only once it loses it (story 17).
    page.locator("#model-picker").blur()
    ok, _ = r.poll(lambda: _picker_options(r).get(LLAMA_OPTION) is False, 10)
    r.check(ok, "sélecteur : le modèle servi est choisissable", str(_picker_options(r)))
    seq = r.ev.mark()
    page.select_option("#model-picker", label=LLAMA_OPTION)
    page.click("#model-picker-apply")
    started = r.ev.wait("model_load_started", seq, timeout=10)
    r.check(
        started["payload"]["phase_label"] == "Préparation du modèle servi par llama-server…",
        "sélecteur : « Préparation du modèle servi par llama-server… »",
        started["payload"]["phase_label"],
    )
    ended = r.ev.wait("model_load_ended", seq, timeout=30)
    r.check(ended["payload"]["status"] == "ok", "sélecteur : modèle servi prêt")
    expect(page.locator("#model-indicator")).to_contain_text("Local · llama-server", timeout=10_000)
    r.wait_idle()
    seq = r.ev.mark()
    page.select_option("#model-picker", label="RÉSEAU · Faux fournisseur (e2e) · wavestack-fake")
    page.click("#model-picker-apply")
    page.click("#cloud-warning-confirm")
    r.ev.wait("model_load_ended", seq, timeout=30)
    expect(page.locator("#model-indicator")).to_contain_text("wavestack-fake", timeout=10_000)
    r.wait_idle()


PICK_MODELS_LABEL = "Tableau des modèles et de leurs capacités…"


def _picker_groups(r: Run) -> list[dict[str, Any]]:
    """The model picker's `optgroup`s: label, then each option's text and state."""
    return r.page.eval_on_selector_all(
        "#model-picker optgroup",
        "gs => gs.map(g => ({label: g.label, options: [...g.children].map("
        "o => ({text: o.textContent, disabled: o.disabled}))}))",
    )


def _models_row(r: Run, value: str) -> dict[str, str]:
    """Lot 3 of 2026-10-04: story 25's row, read on the card of `value`, unfolded: its
    publisher, size, state and each capability with its reason."""
    info = _card_info(r, value)
    facts = info["facts"]
    row = {
        "name": info["name"],
        "publisher": info["publisher"],
        "size": info["size"],
        "state": info["state"],
        "text": info["text"],
    }
    for key, label in (
        ("window", "Fenêtre"),
        ("tools", "Appel d'outils"),
        ("reasoning", "Raisonnement"),
        ("price", "Prix"),
    ):
        row[key], row[f"{key}_why"] = facts.get(label, ["", ""])
    return row


# ---------- story 3 of 2026-09-30, lot 3 of 2026-10-04: sort and filters of the cards ------

_CARDS_SHOWN_JS = """() => [...document.querySelectorAll('.publisher-group')].map((g) => ({
  group: g.dataset.key,
  cards: [...g.querySelectorAll('article.model-card')].map((c) => c.dataset.card),
}))"""


def _cards_shown(r: Run) -> list[dict[str, Any]]:
    """Each visible publisher group, its cards in order."""
    return r.page.evaluate(_CARDS_SHOWN_JS)


def _shown_ids(r: Run) -> list[str]:
    return sorted(c for g in _cards_shown(r) for c in g["cards"])


def _order_problems(r: Run, key) -> list[str]:  # noqa: ANN001 - card -> tuple, None unknown
    """The pairs of cards out of order within each visible group, unknown values last."""
    by_id = {c["id"]: c for c in _api_cards(r)}
    problems = []
    for group in _cards_shown(r):
        values = [key(by_id[c]) for c in group["cards"]]
        for i in range(1, len(values)):
            a, b = values[i - 1], values[i]
            for x, y in zip(a, b, strict=True):
                if x == y:
                    continue
                if x is None or (y is not None and x > y):
                    problems.append(f"{group['cards'][i - 1]} ({a}) > {group['cards'][i]} ({b})")
                break
    return problems


def _size_key(card: dict[str, Any]) -> tuple:
    return (card["size_bytes_min"], card["members"][0]["params_b"])


def _window_key(card: dict[str, Any]) -> tuple:
    return (max((m["window"] or 0) for m in card["members"]) or None,)


def _hosting(r: Run, value: str) -> None:
    r.page.locator(f'#filter-hosting button[data-value="{value}"]').click()


def _folded(text: str) -> str:
    import unicodedata

    decomposed = unicodedata.normalize("NFD", text or "")
    return "".join(c for c in decomposed if not unicodedata.combining(c)).lower()


def _card_words(card: dict[str, Any]) -> str:
    names = [f"{m['name']} {m['publisher_text']}" for m in card["members"]]
    return _folded(" ".join([card["name"], card["group"]["publisher_text"], *names]))


def _models_sort_and_filters(r: Run) -> None:
    """« Trier par » Taille, then Fenêtre, within each group, unknown values last; the network
    filter with a free text, its count; no result, then « Réinitialiser les filtres »; the
    tools, reasoning and publisher filters, a card kept when one of its sources matches."""
    page = r.page
    cards = _api_cards(r)
    total = len(cards)
    page.select_option("#filter-sort", "size")
    problems = _order_problems(r, _size_key)
    r.check(
        not problems and len(_shown_ids(r)) == total,
        "« Trier par : Taille » : croissant par taille dans chaque groupe, inconnues en dernier",
        "; ".join(problems[:4]),
    )
    page.locator("#filter-sort").focus()
    page.select_option("#filter-sort", "window")
    problems = _order_problems(r, _window_key)
    r.check(
        not problems, "« Trier par : Fenêtre » : croissant par fenêtre", "; ".join(problems[:4])
    )

    _hosting(r, "network")
    page.fill("#filter-text", "gem")
    expected = sorted(
        c["id"] for c in cards if c["hosting"] == "network" and "gem" in _card_words(c)
    )
    shown = _shown_ids(r)
    status = page.inner_text("#models-status")
    word = "modèle" if len(expected) <= 1 else "modèles"
    pressed = page.locator('#filter-hosting button[aria-pressed="true"]').inner_text()
    r.check(
        bool(expected)
        and shown == expected
        and status == f"{len(expected)} {word} sur {total}"
        and pressed == "Réseau"
        and "Aucun modèle local ne correspond à ces filtres." in page.inner_text("#candidates"),
        "filtres : « Réseau » (bouton segmenté) + « gem », les seules cartes cloud dont le nom ou "
        "l'éditeur contient « gem », compteur « n modèles sur N », groupes vides masqués",
        f"{shown} · attendu {expected} · « {status} » · {pressed}",
    )
    r.shot("44b-modeles-filtres", full_page=True)

    page.fill("#filter-text", "zzz")
    r.check(
        not _shown_ids(r)
        and "Aucun modèle cloud ne correspond à ces filtres." in page.inner_text("#cloud-models")
        and page.inner_text("#models-status") == f"0 modèle sur {total}",
        "filtres : « zzz », aucun résultat, message dans chaque zone",
        page.inner_text("#models-status"),
    )
    page.locator("#filters-reset").click()
    shown = _shown_ids(r)
    r.check(
        len(shown) == total
        and page.input_value("#filter-text") == ""
        and page.locator('#filter-hosting button[aria-pressed="true"]').inner_text() == "Tous"
        and page.input_value("#filter-sort") == ""
        and page.inner_text("#models-status").startswith(f"{total} modèle"),
        "« Réinitialiser les filtres » : toutes les cartes de nouveau, compteur entier",
        f"{len(shown)} / {total} · {page.inner_text('#models-status')}",
    )

    publisher = page.eval_on_selector_all(
        "#filter-publisher option", "os => os.map(o => o.value).filter(Boolean)"
    )
    picked = publisher[0] if publisher else None
    filters = [
        ("#filter-tools", "no", lambda m: m["tools"] is not True, "outils « Non ou inconnu »"),
        (
            "#filter-reasoning",
            "yes",
            lambda m: m["reasoning"] in ("always", "toggle"),
            "raisonnement « Oui » (toujours ou activable)",
        ),
        (
            "#filter-publisher",
            picked,
            lambda m: m["publisher_id"] == picked,
            f"éditeur « {picked} »",
        ),
    ]
    for selector, option, keep, label in filters:
        if option is not None:
            page.select_option(selector, option)
        expected = sorted(c["id"] for c in cards if any(keep(m) for m in c["members"]))
        shown = _shown_ids(r)
        r.check(
            option is not None and bool(expected) and shown == expected,
            f"filtres : {label}, ses seules cartes",
            f"{len(shown)} affichées · attendu {len(expected)} · "
            f"en trop {sorted(set(shown) - set(expected))[:4]} · "
            f"manquantes {sorted(set(expected) - set(shown))[:4]}",
        )
        page.locator("#filters-reset").click()
    # An unfolded card the filters hide folds.
    _unfold(page.locator("#cloud-models .model-card").first)
    _hosting(r, "local")
    r.check(
        page.locator('.model-card-head[aria-expanded="true"]').count() == 0,
        "filtres : une carte dépliée qui sort du filtre se replie",
    )
    page.locator("#filters-reset").click()


def _models_window_then_network(r: Run) -> None:
    """German, at the width of the moment: « Sortieren nach : Fenster », then « Netzwerk »;
    the cloud cards only, by window in their group, the count right (AC of story 3)."""
    page = r.page
    cards = _api_cards(r)
    network = sorted(c["id"] for c in cards if c["hosting"] == "network")
    page.select_option("#filter-sort", "window")
    _hosting(r, "network")
    option = page.locator('#filter-hosting button[aria-pressed="true"]').inner_text()
    shown = _shown_ids(r)
    problems = _order_problems(r, _window_key)
    status = page.inner_text("#models-status")
    word = "Modell" if len(network) == 1 else "Modelle"
    r.check(
        bool(network)
        and option == "Netzwerk"
        and shown == network
        and not problems
        and status == f"{len(network)} {word} von {len(cards)}",
        "de : « Fenster » puis « Netzwerk », les seules cartes cloud, par fenêtre dans leur "
        "groupe, compteur juste",
        f"{option} · {len(shown)} / {len(network)} · « {status} » · " + "; ".join(problems[:3]),
    )
    page.locator("#filters-reset").click()


def _diagnostic_search_shown(r: Run) -> None:
    """The diagnostic while the models are searched: `/api/diagnostic` and its stream
    simulated (the E2E stack is diagnosed once, at launch): the message without a count
    (`diagnostic_progress{0, 0}`), then « 3 modèles testés sur 30 » and the bar at 10 %
    from a live event, never « Aucun candidat trouvé. »; the real answer then lists them."""
    page = r.page
    real = r.api("GET", "/api/diagnostic").json()
    r.check(
        real.get("searching") is False and real.get("progress") is None,
        "/api/diagnostic : searching faux et progress nul une fois le contrôle « model » rendu",
        f"{real.get('searching')} · {real.get('progress')}",
    )
    fake = {**real, "searching": True, "progress": {"done": 0, "total": 0}, "candidates": []}
    # Lot 3 of 2026-10-04: no candidate yet, hence no local card (the session builds them).
    network = [g for g in real["models"]["groups"] if g["hosting"] == "network"]
    fake["models"] = {**real["models"], "groups": network}
    fake["ready"] = False
    envelope = {
        "seq": real["seq"] + 1000,
        "ts": "2026-10-01T00:00:00Z",
        "session_epoch": 0,
        "kind": "diagnostic_progress",
        "actor": "harness",
        "trigger": "harness",
        "payload": {"done": 3, "total": 30},
    }
    stream = f"id: {envelope['seq']}\nevent: diagnostic_progress\ndata: {json.dumps(envelope)}\n\n"
    search = page.locator("#candidates-search")
    count = page.locator("#candidates-progress-text")
    page.route("**/api/diagnostic", lambda route: route.fulfill(json=fake))
    page.route("**/api/diagnostic/stream", lambda route: route.abort())
    try:
        page.goto(f"{r.stack.app_url}/diagnostic")
        expect(search).to_be_visible(timeout=10_000)
        r.check(
            "Recherche et test des modèles en cours…" in search.inner_text()
            and count.is_hidden()
            and "Aucun candidat trouvé." not in page.inner_text("#candidates")
            and page.locator("#candidates .model-card").count() == 0,
            "diagnostic en recherche, rien à sonder : le message sans compteur, jamais "
            "« Aucun candidat trouvé. »",
            search.inner_text(),
        )
        page.unroute("**/api/diagnostic/stream")
        page.route(
            "**/api/diagnostic/stream",
            lambda route: route.fulfill(
                status=200, headers={"Content-Type": "text/event-stream"}, body=stream
            ),
        )
        page.reload()
        expect(count).to_have_text("3 modèles testés sur 30", timeout=10_000)
        bar = page.eval_on_selector("#candidates-progress", "p => [p.value, p.max, p.hidden]")
        r.check(
            bar == [3, 30, False]
            and "Aucun candidat trouvé." not in page.inner_text("#candidates"),
            "diagnostic en recherche : « 3 modèles testés sur 30 » en direct, barre à 10 %",
            str(bar),
        )
        r.shot("49b-diagnostic-recherche")
    finally:
        page.unroute("**/api/diagnostic")
        page.unroute("**/api/diagnostic/stream")
    page.goto(f"{r.stack.app_url}/diagnostic")
    expect(page.locator("#candidates .model-card").first).to_be_visible(timeout=20_000)
    r.check(
        search.is_hidden() and "Aucun candidat trouvé." not in page.inner_text("#candidates"),
        "diagnostic, recherche finie : la liste des candidats, sans message de recherche",
    )


def _diagnostic_card_states(r: Run) -> None:
    """Lot 3 of 2026-10-04, from a simulated `/api/diagnostic`: a card with an active source
    and an incompatible one says « Actif » (its sources keep their own state); a model whose
    last load failed says « Erreur », the cause and « Choisir ce modèle » in its detail; a
    check in warning opens the checks panel, all green folds it."""
    page = r.page
    real = r.api("GET", "/api/diagnostic").json()
    group = next(
        (g for g in real["models"]["groups"] if g["hosting"] == "local"),
        real["models"]["groups"][0],
    )
    base = {**group["models"][0], "hosting": "local", "usable": True, "disabled_text": None}
    active = {**base, "kind": "file", "ref": "C:/e2e/actif.gguf", "value": "file:C:/e2e/actif.gguf"}
    broken = {
        **base,
        "kind": "file",
        "ref": "D:/e2e/actif.gguf",
        "value": "file:D:/e2e/actif.gguf",
        "usable": False,
        "disabled_text": "Incompatible simulé.",
    }
    failed = {**base, "kind": "file", "ref": "C:/e2e/panne.gguf", "value": "file:C:/e2e/panne.gguf"}
    card = {
        "id": "card:e2e-actif",
        "name": "e2e-actif",
        "hosting": "local",
        "size_bytes_min": 1024**3,
        "size_text": "1,0 Go",
        "params_text": None,
        "origin_text": "2 sources · e2e",
        "quantization_text": None,
        "source_values": [active["value"], broken["value"]],
    }
    lone = {**card, "id": "card:e2e-panne", "name": "e2e-panne", "origin_text": "e2e"}
    lone["source_values"] = [failed["value"]]
    fake_group = {**group, "hosting": "local", "models": [active, broken, failed]}
    fake_group["cards"] = [card, lone]
    network = [g for g in real["models"]["groups"] if g["hosting"] == "network"]
    fake = {
        **real,
        "searching": False,
        "progress": None,
        "candidates": [],
        "models": {**real["models"], "groups": [fake_group, *network]},
        "loaded": {"kind": "file", "ref": active["ref"], "label": "e2e-actif"},
        "selected": {"kind": "file", "ref": active["ref"]},
        "load_errors": [{"kind": "file", "ref": failed["ref"], "reason_text": "Panne simulée."}],
    }

    def checks(network_status: str) -> str:
        frames = []
        for i, (check, status) in enumerate(
            (("memory", "ok"), ("model", "ok"), ("network", network_status), ("port", "ok"))
        ):
            envelope = {
                "seq": i + 1,
                "ts": "2026-10-04T00:00:00Z",
                "session_epoch": 0,
                "kind": "diagnostic_check",
                "actor": "harness",
                "trigger": "harness",
                "payload": {
                    "check": check,
                    "status": status,
                    "message_text": f"{check} simulé",
                    "action_text": None,
                    "blocking": False,
                },
            }
            frames.append(f"id: {i + 1}\nevent: diagnostic_check\ndata: {json.dumps(envelope)}\n\n")
        return "".join(frames)

    stream = {"body": checks("warn")}
    page.route("**/api/diagnostic", lambda route: route.fulfill(json=fake))
    page.route(
        "**/api/diagnostic/stream",
        lambda route: route.fulfill(
            status=200, headers={"Content-Type": "text/event-stream"}, body=stream["body"]
        ),
    )
    try:
        page.goto(f"{r.stack.app_url}/diagnostic")
        both = page.locator('.model-card[data-card="card:e2e-actif"]')
        expect(both).to_be_visible(timeout=10_000)
        pill = both.locator(".model-card-head .state-pill")
        r.check(
            pill.get_attribute("data-state") == "active"
            and pill.inner_text() == "Actif"
            and "is-active" in (both.get_attribute("class") or "")
            and both.locator(".sources-chip").inner_text() == "2 sources",
            "carte à deux sources, une active et une incompatible : pastille « Actif », "
            "puce « 2 sources »",
            f"{pill.get_attribute('data-state')} · {pill.inner_text()}",
        )
        both.locator(".model-card-head").click()
        sources = both.locator(".card-source")
        expect(sources).to_have_count(2, timeout=5_000)
        own = sources.locator(".state-pill").evaluate_all("ps => ps.map(p => p.dataset.state)")
        r.check(
            own == ["active", "incompatible"]
            and sources.nth(1).locator("button").count() == 0
            and "Incompatible simulé." in sources.nth(1).inner_text(),
            "carte dépliée : chaque source son état, pas de « Choisir » sur l'incompatible",
            str(own),
        )
        lone_card = page.locator('.model-card[data-card="card:e2e-panne"]')
        lone_pill = lone_card.locator(".model-card-head .state-pill")
        r.check(
            lone_pill.get_attribute("data-state") == "error"
            and lone_pill.inner_text() == "Erreur"
            and "is-unusable" in (lone_card.get_attribute("class") or ""),
            "dernier chargement en échec : carte « Erreur », fond inutilisable",
            lone_pill.inner_text(),
        )
        lone_card.locator(".model-card-head").click()
        expect(lone_card.locator(".model-card-detail")).to_be_visible(timeout=5_000)
        r.check(
            "Panne simulée." in lone_card.inner_text()
            and lone_card.get_by_role("button", name="Choisir ce modèle").count() == 1
            and both.locator(".model-card-detail").count() == 0,
            "carte « Erreur » dépliée : la cause et « Choisir ce modèle » pour réessayer ; "
            "une seule carte dépliée",
        )
        panel = page.locator("#checks-panel")
        r.check(
            panel.get_attribute("open") is not None
            and "1 avertissement : réseau" in page.inner_text("#checks-summary"),
            "un contrôle en avertissement : panneau des contrôles ouvert d'office",
            page.inner_text("#checks-summary"),
        )
        stream["body"] = checks("ok")
        page.reload()
        expect(page.locator("#checks-summary")).to_contain_text("4 contrôles OK", timeout=10_000)
        r.check(
            panel.get_attribute("open") is None,
            "tous les contrôles OK : panneau replié",
            page.inner_text("#checks-summary"),
        )
    finally:
        page.unroute("**/api/diagnostic")
        page.unroute("**/api/diagnostic/stream")


def _open_models_page(r: Run) -> None:
    """Lot 3 of 2026-10-04: the models' table is « Diagnostic et modèles »."""
    _goto_diagnostic(r)


def s_model_catalog(r: Run) -> None:
    """Story 25: the picker grouped by hosting then publisher, sorted by size, with its
    legend; the « Tableau des modèles » entry and the `/models` page (capabilities as the
    cards say them after the load); the tabs shared with the diagnostic."""
    page = r.page
    r.goto_app()
    r.wait_idle()
    page.locator("#model-picker").blur()
    ok, _ = r.poll(lambda: bool(_picker_groups(r)), 10)
    r.check(ok, "sélecteur : groupes reçus de la session")
    options = page.eval_on_selector_all(
        "#model-picker option", "os => os.map(o => [o.textContent, o.disabled])"
    )
    legend, legend_disabled = options[1]
    r.check(
        legend_disabled and "où tourne le modèle" in legend and "qui le sert" in legend,
        "sélecteur : la deuxième option est la légende désactivée",
        legend,
    )
    title = page.get_attribute("#model-picker", "title") or ""
    r.check("où tourne le modèle" in title, "sélecteur : l'infobulle reprend la légende", title)
    groups = _picker_groups(r)
    labels = [g["label"] for g in groups]
    # Three fake cloud models have no known publisher; the fourth is named as Gemini, with
    # the Gemini preset; the presets of wavestack.toml (Gemma, Gemini, Mistral, Groq's
    # gpt-oss, Claude since native providers 3/5, GPT since 4/5),
    # declared without a key, come in the table's order before.
    expected = [
        "Sur ce poste · Qwen (Alibaba)",
        "Réseau · Gemma (Google)",
        "Réseau · Gemini (Google)",
        "Réseau · Mistral (Mistral AI)",
        "Réseau · gpt-oss (OpenAI)",
        "Réseau · Claude (Anthropic)",
        "Réseau · GPT (OpenAI)",
        "Réseau · Autres éditeurs",
    ]
    if "Sur ce poste · Autres éditeurs" in labels:
        expected.insert(1, "Sur ce poste · Autres éditeurs")
    r.check(labels == expected, "sélecteur : groupes par hébergement puis éditeur", str(labels))
    qwen = [o["text"] for o in groups[0]["options"]] if groups else []
    ollama_at = next((i for i, t in enumerate(qwen) if t.startswith(OLLAMA_OPTION)), -1)
    llama_at = next((i for i, t in enumerate(qwen) if t.startswith(LLAMA_OPTION)), -1)
    r.check(
        f"{OLLAMA_OPTION} (incompatible)" in qwen and 0 <= ollama_at < llama_at,
        "sélecteur : faux Ollama (0.6B, incompatible) avant le faux llama-server (taille inconnue)",
        str(qwen),
    )
    texts = [o["text"] for g in groups for o in g["options"]]
    r.check(
        bool(texts) and all(t.startswith(("Local · ", "RÉSEAU · ")) for t in texts),
        "sélecteur : chaque modèle commence par « Local · » ou « RÉSEAU · »",
        str(texts),
    )
    r.check(
        [o[0] for o in options[-2:]] == [PICK_MODELS_LABEL, "Autre fichier ou clé API…"],
        "sélecteur : « Tableau des modèles… » puis « Autre fichier ou clé API… » en dernier",
        str([o[0] for o in options[-2:]]),
    )
    # The list as it opens: a native list cannot be captured open, shown as a list box.
    page.evaluate(
        """() => {
          const p = document.getElementById("model-picker");
          p.dataset.e2eStyle = p.getAttribute("style") ?? "";
          p.size = p.options.length + p.querySelectorAll("optgroup").length;
          p.style.cssText = "position: fixed; top: 64px; right: 16px; max-width: none; " +
            "width: 46rem; height: auto; z-index: 50";
        }"""
    )
    r.shot("43-modeles-selecteur")
    page.evaluate(
        """() => {
          const p = document.getElementById("model-picker");
          p.removeAttribute("size");
          p.setAttribute("style", p.dataset.e2eStyle);
          delete p.dataset.e2eStyle;
        }"""
    )

    # « Tableau des modèles… » noted, then « Ouvrir le tableau »: lot 3 of 2026-10-04, the
    # « Diagnostic et modèles » page, same tab; `/models` redirects there.
    page.select_option("#model-picker", label=PICK_MODELS_LABEL)
    apply = page.locator("#model-picker-apply")
    r.check(apply.inner_text() == "Ouvrir le tableau", "bouton « Ouvrir le tableau »")
    apply.click()
    page.wait_for_url(f"{r.stack.app_url}/diagnostic", timeout=10_000)
    expect(page.locator("#cloud-models .model-card").first).to_be_visible(timeout=20_000)
    current = page.locator('.site-nav a[aria-current="page"]')
    r.check(
        current.inner_text() == "🛠️ Diagnostic"
        and page.locator('.site-nav a[href="/models"]').count() == 0
        and page.title() == "WaveStack — Diagnostic et modèles"
        and page.locator("h1").inner_text() == "Diagnostic et modèles",
        "« Tableau des modèles… » : la page « Diagnostic et modèles », « 🛠️ Diagnostic » courant",
        current.inner_text(),
    )
    page.goto(f"{r.stack.app_url}/models")
    r.check(page.url.endswith("/diagnostic"), "/models redirige vers /diagnostic", page.url)
    expect(page.locator("#cloud-models .model-card").first).to_be_visible(timeout=20_000)
    llama = _models_row(r, f"server:llama_server/{LLAMA_FILE}")
    r.check(
        llama.get("publisher") == "Qwen (Alibaba)"
        and llama.get("tools", "").startswith("oui")
        and llama.get("reasoning") == "activable"
        and llama.get("window") == "4 096 tokens"
        and llama.get("price") == "—",
        "carte : faux llama-server Qwen, outils oui, raisonnement activable, 4 096 tokens, "
        "prix « — »",
        str({k: v for k, v in llama.items() if k != "text"}),
    )
    reasoning_r = _models_row(r, f"cloud:{REASONING_ENTRY_ID}")
    r.check(reasoning_r.get("reasoning") == "toujours", "carte : modèle R « toujours »")
    gemini = _models_row(r, "cloud:gemini")
    r.check(
        gemini.get("size") == "RÉSEAU · Google AI Studio"
        and gemini.get("name") == "gemini-3.5-flash-lite"
        and gemini.get("publisher") == "Gemini (Google)"
        and gemini.get("reasoning") == "activable"
        and gemini.get("state") == "key_missing"
        and "clé API" in gemini.get("text", "")
        and gemini.get("price") == "0,30 $ / 2,50 $"
        and "par million de tokens" in gemini.get("price_why", ""),
        "carte : préréglage Gemini, éditeur « Gemini (Google) », raisonnement « activable », "
        "« Clé manquante » avec la raison, prix « 0,30 $ / 2,50 $ » par million de tokens",
        str({k: v for k, v in gemini.items() if k != "text"}),
    )
    gemma = _models_row(r, "cloud:gemma")
    r.check(
        gemma.get("name") == "gemma-4-26b-a4b-it"
        and gemma.get("publisher") == "Gemma (Google)"
        and gemma.get("reasoning") == "activable"
        and gemma.get("state") == "key_missing"
        and gemma.get("price") == "—",
        "carte : préréglage Gemma, éditeur « Gemma (Google) », raisonnement « activable », "
        "« Clé manquante », prix « — » (gratuit, sans pricing)",
        str({k: v for k, v in gemma.items() if k != "text"}),
    )
    fake_a = _models_row(r, f"cloud:{MODEL_ENTRY_ID}")
    r.check(fake_a.get("reasoning") == "jamais", "carte : wavestack-fake « jamais »")
    r.check(fake_a.get("state") == "active", "carte : celle du modèle actif dit « Actif »")
    ollama = _models_row(r, "server:ollama/faux-ollama:latest")
    r.check(
        ollama.get("reasoning") == "inconnu" and "introuvable" in ollama["reasoning_why"],
        "carte : faux Ollama « inconnu », raison visible « introuvable »",
        str({k: v for k, v in ollama.items() if k != "text"}),
    )
    network = page.locator("#cloud-models .model-card")
    cloud_count = len(r.api("GET", "/api/diagnostic").json()["cloud"]["models"])
    tags = page.locator("#cloud-models .model-card-head .hosting-tag-network")
    r.check(
        network.count() == cloud_count >= 3
        and tags.count() == cloud_count
        and all("RÉSEAU" in t for t in tags.all_inner_texts()),
        "zone cloud : chaque carte montre « 🌐 RÉSEAU · {fournisseur} »",
        f"{network.count()} cartes, {cloud_count} modèles cloud",
    )
    r.check(
        r.css(tags.first, "background-color") == r.token_color("--color-hosting-network"),
        "carte cloud : étiquette réseau sur le jeton jaune",
    )
    headers = page.locator(".publisher-group-name").all_inner_texts()
    r.check(
        headers == [label.split(" · ", 1)[1] for label in labels],
        "un en-tête par groupe d'éditeur, ceux du sélecteur, dans son ordre",
        f"{headers} · {labels}",
    )
    r.check(
        "Capacités lues comme au chargement" in page.inner_text("body"),
        "page : « Capacités lues comme au chargement… »",
    )
    r.shot("44-modeles-cartes", full_page=True)
    _models_sort_and_filters(r)  # story 3 of 2026-09-30
    _diagnostic_search_shown(r)  # story 3 of 2026-09-30
    _diagnostic_card_states(r)  # lot 3 of 2026-10-04: aggregated state, « Erreur », checks

    # One truth: the reasoning card after the load and the table say the same.
    r.goto_app()
    r.launch("bare_llm")
    a_label = "RÉSEAU · Faux fournisseur (e2e) · wavestack-fake"
    try:
        _pick_model(r, f"RÉSEAU · Faux fournisseur R (e2e) · {REASONING_MODEL}")
        card = r.card("Raisonnement")
        locked = card.locator(".brick-lock").count() == 1
        _open_models_page(r)
        row = _models_row(r, f"cloud:{REASONING_ENTRY_ID}")
        r.check(
            locked and row.get("reasoning") == "toujours" and row.get("state") == "active",
            "modèle R actif : carte verrouillée et carte du modèle « toujours », « Actif »",
            str({k: v for k, v in row.items() if k != "text"}),
        )
    finally:
        r.goto_app()
        if (r.state().get("active_model") or {}).get("ref") != MODEL_ENTRY_ID:
            _pick_model(r, a_label)
    reason = r.card("Raisonnement").locator("p.brick-reason").all_inner_texts()
    _open_models_page(r)
    row = _models_row(r, f"cloud:{MODEL_ENTRY_ID}")
    r.check(
        row.get("reasoning") == "jamais"
        and any("ne déclare pas de raisonnement" in t for t in reason),
        "retour à l'entrée A : carte du modèle « jamais », carte indisponible « ne déclare "
        "pas de raisonnement »",
        f"{row.get('reasoning')} · {reason}",
    )
    _models_page_language(r)
    r.goto_app()


def _models_page_language(r: Run) -> None:
    """Story 2 (2026-09-30): on « Diagnostic et modèles » (lot 3 of 2026-10-04: the models'
    table), the conversation empty, « English » in « Affichage ▾ » of the shared bar: the page
    reloads in English. Back to French after."""
    page = r.page
    r.goto_app()
    r.launch("bare_llm")
    r.send("Bonjour")
    r.wait_idle()
    page.goto("about:blank")  # an open main screen would reload itself on `language_changed`
    page.goto(f"{r.stack.app_url}/diagnostic")
    expect(page.locator("#cloud-models .model-card").first).to_be_attached(timeout=20_000)
    try:
        picker = page.locator("#language-picker")
        panel = page.locator("#display-menu-panel")
        # A conversation under way: the picker locked, its tooltip says why.
        _open_display(page)
        ok, took = r.poll(lambda: picker.is_disabled(), 10)
        title = picker.get_attribute("title") or ""
        r.check(
            ok and "Videz d'abord la conversation" in title,
            "/diagnostic, un tour joué : sélecteur de langue désactivé, l'infobulle dit de vider "
            "la conversation",
            f"{title} ({took:.1f} s)",
        )
        cleared = r.api("POST", "/api/intentions/clear_conversation", {})
        _close_display(page)
        _open_display(page)  # the state read again at each opening
        ok, took = r.poll(lambda: picker.is_enabled(), 10)
        r.check(
            cleared.status_code == 200 and ok,
            "/diagnostic, conversation vidée, menu rouvert : sélecteur de langue actif",
            f"{cleared.status_code} · {took:.1f} s",
        )
        # A refusal (409): its reason in the menu, the picker offered again.
        refusal = "Refus simulé (e2e)"
        page.route(
            "**/api/intentions/language",
            lambda route: route.fulfill(
                status=409, content_type="application/json", json={"detail": refusal}
            ),
        )
        try:
            picker.select_option("en")
            alert = page.locator("#display-menu-alert")
            expect(alert).to_have_text(refusal, timeout=5000)
            ok, _ = r.poll(lambda: picker.is_enabled(), 10)
            r.check(
                ok and picker.input_value() == "fr" and _html_lang(r) == "fr",
                "/diagnostic, refus (409) : la raison dans « Affichage ▾ », le sélecteur de "
                "nouveau actif, sur « Français »",
                f"{alert.inner_text()} · {picker.input_value()}",
            )
        finally:
            page.unroute("**/api/intentions/language")
        # Escape closes the menu, the focus back on its face; a click outside closes it too.
        page.keyboard.press("Escape")
        focused = page.evaluate("() => document.activeElement?.id")
        r.check(
            panel.is_hidden()
            and focused == "display-menu-toggle"
            and page.locator("#display-menu-alert").is_hidden(),
            "/diagnostic : Échap ferme « Affichage ▾ », le focus revient sur sa face, le refus "
            "s'efface",
            f"focus sur {focused}",
        )
        _open_display(page)
        page.locator("h1").click()
        r.check(panel.is_hidden(), "/diagnostic : un clic hors du menu ferme « Affichage ▾ »")
        _open_display(page)
        ok, _ = r.poll(lambda: picker.is_enabled(), 10)
        seq = r.ev.mark()
        with page.expect_navigation(timeout=15_000):  # the page reloads, as on the main screen
            picker.select_option("en")
        r.ev.wait("language_changed", seq, lambda p: p["language"] == "en", timeout=15)
        expect(page.locator("#cloud-models .model-card").first).to_be_attached(timeout=20_000)
        home = page.locator(".site-nav > a:not(.site-nav-brand)").first.inner_text()
        current = page.locator('.site-nav a[aria-current="page"]').inner_text()
        r.check(
            page.url.endswith("/diagnostic")
            and _html_lang(r) == "en"
            and (home, current) == ("Harness", "🛠️ Diagnostics")
            and page.locator("#language-picker-code").inner_text() == "EN",
            "/diagnostic : « English » choisi, la page se recharge en anglais (barre commune "
            "« Harness », « 🛠️ Diagnostics » courant, « EN »)",
            f"{page.url} · lang={_html_lang(r)} · {home} · {current}",
        )
    finally:
        if r.state().get("language") != "fr":
            r.goto_app()  # `_switch_language` starts from the main screen, at rest
            _switch_language(r, "fr")
        r.check(r.state()["language"] == "fr", "nettoyage : retour au français")


A_LABEL = "RÉSEAU · Faux fournisseur (e2e) · wavestack-fake"


def _window_panel(r: Run) -> None:
    """Opens the « Fenêtre ▾ » panel (story 26) and waits for its three choices."""
    if r.page.locator("#window-panel").is_hidden():
        r.page.click("#window-toggle")
    expect(r.page.locator("#window-panel")).to_be_visible(timeout=5000)
    expect(r.page.locator("#window-choices .window-choice")).to_have_count(3, timeout=5000)


def _apply_window(r: Run, window: int) -> dict[str, Any]:
    """Notes `window` in the panel, « Appliquer », and waits for the session's new state."""
    seq = r.ev.mark()
    _window_panel(r)
    r.page.locator(f'#window-choices input[name="window-choice"][value="{window}"]').check()
    expect(r.page.locator("#window-apply")).to_be_enabled(timeout=5000)
    r.page.click("#window-apply")
    state = r.ev.wait("context_window_state", seq, lambda p: p["configured"] == window, 30)
    r.wait_idle()
    return state["payload"]


def s_context_window(r: Run) -> None:
    """Story 26: the « Fenêtre ▾ » panel of the top bar. On the fake cloud A: three choices,
    « chez le fournisseur », « (actuelle) » on 4 096; 8 192 applied without a reload (gauge,
    figures, conversation, `settings.json`); on the fake llama-server (`-c 8192`), 16 384
    noted shows its bound before « Appliquer »; back to A and to 4 096 (`relaunch` unchanged)."""
    page = r.page
    page.set_viewport_size({"width": 1600, "height": 1000})
    r.goto_app()
    r.wait_idle()
    if (r.state().get("active_model") or {}).get("ref") != MODEL_ENTRY_ID:
        _pick_model(r, A_LABEL)
    try:
        r.launch("short_memory")
        r.send("Bonjour")

        # (a) The panel on the fake cloud A.
        toggle = page.locator("#window-toggle")
        r.check(
            toggle.inner_text().replace(" ", " ").startswith("Fenêtre 4 096"),
            "bouton « Fenêtre 4 096 ▾ » dans la barre de l'atelier",
            toggle.inner_text(),
        )
        r.check(
            toggle.get_attribute("aria-haspopup") == "dialog"
            and toggle.get_attribute("aria-expanded") == "false",
            "bouton : aria-haspopup=dialog, aria-expanded=false",
        )
        _window_panel(r)
        r.check(toggle.get_attribute("aria-expanded") == "true", "panneau ouvert : aria-expanded")
        panel = page.locator("#window-panel")
        # Lot K (A8): at 1280 × 650, « Appliquer » and « Fermer » in view without scrolling
        # the panel (pinned at its foot), the panel inside the window.
        page.set_viewport_size({"width": 1280, "height": 650})
        time.sleep(0.3)
        placed = page.evaluate(
            "() => { const p = document.getElementById('window-panel').getBoundingClientRect();"
            " const out = {};"
            " for (const id of ['window-apply', 'window-close']) {"
            " const b = document.getElementById(id).getBoundingClientRect();"
            " out[id] = b.height > 0 && b.top >= p.top && b.bottom <= p.bottom + 1"
            " && b.bottom <= innerHeight; }"
            " out.inside = p.bottom <= innerHeight + 1;"
            " out.scrolled = document.querySelector('.window-scroll')?.scrollTop ?? -1;"
            " return out; }"
        )
        r.check(
            placed["window-apply"]
            and placed["window-close"]
            and placed["inside"]
            and placed["scrolled"] == 0,
            "1280 × 650 : « Appliquer » et « Fermer » visibles en pied du panneau, sans le "
            "faire défiler",
            str(placed),
        )
        page.set_viewport_size({"width": 1600, "height": 1000})
        time.sleep(0.3)
        r.check(panel.get_attribute("role") == "dialog", "panneau : role=dialog")
        text = panel.inner_text()
        rows = page.locator("#window-choices .window-choice").all_inner_texts()
        heads = [row.split("\n")[0] for row in rows]
        r.check(
            [h.replace(" ", " ").split(" tokens")[0] for h in heads]
            == ["4 096", "8 192", "16 384"],
            "trois choix : 4 096, 8 192 et 16 384 tokens",
            str(heads),
        )
        r.check(
            "(actuelle)" in rows[0] and not any("(actuelle)" in row for row in rows[1:]),
            "« (actuelle) » sur 4 096 seulement",
            " | ".join(row.split("\n")[1] if "\n" in row else row for row in rows),
        )
        r.check(
            all("chez le fournisseur" in row for row in rows)
            and all("Tient dans le budget" in row for row in rows),
            "modèle cloud : cache « chez le fournisseur », chaque choix tient dans le budget",
            " | ".join(row.replace("\n", " · ") for row in rows),
        )
        r.check(
            "Les scénarios sont conçus pour 4 096 tokens" in text and "Fenêtre de contexte" in text,
            "panneau : titre et aide « conçus pour 4 096 tokens »",
        )
        apply = page.locator("#window-apply")
        r.check(
            apply.is_disabled() and "déjà de 4 096" in (apply.get_attribute("title") or ""),
            "« Appliquer » désactivé sur la fenêtre actuelle, raison en infobulle",
            apply.get_attribute("title") or "",
        )
        page.keyboard.press("Escape")
        expect(panel).to_be_hidden(timeout=5000)
        r.check(True, "Échap ferme le panneau")

        # (b) 8 192 applied: no reload for a cloud model, the gauge follows.
        seq = r.ev.mark()
        state = _apply_window(r, 8192)
        r.check(
            state["window"] == 8192 and not r.ev.since(seq, "model_load_started"),
            "modèle cloud : 8 192 appliqué sans rechargement",
        )
        expect(panel).to_be_hidden(timeout=5000)
        expect(toggle).to_contain_text("Fenêtre 8 192", timeout=10_000)
        r.check(True, "bouton « Fenêtre 8 192 »")
        ok, _ = r.poll(
            lambda: "Fenêtre de 8 192 tokens" in (page.get_attribute("#gauge", "title") or ""),
            10,
        )
        r.check(
            ok,
            "infobulle de la jauge « Fenêtre de 8 192 tokens »",
            page.get_attribute("#gauge", "title") or "",
        )
        figures = page.inner_text("#gauge-figures")
        r.check("/ 7 680 tokens" in figures, "jauge : « / 7 680 tokens »", figures)
        r.check(
            page.locator("#chat .bubble-user", has_text="Bonjour").count() >= 1,
            "le message reste dans la Vue humain",
        )
        saved = json.loads((r.stack.data_dir / "settings.json").read_text(encoding="utf-8"))
        r.check(
            (saved.get("context") or {}).get("window") == 8192,
            "settings.json : context.window == 8192",
            str(saved.get("context")),
        )

        # (c) The fake llama-server (`-c 8192`): 16 384 noted shows its bound.
        page.locator("#model-picker").blur()
        ok, _ = r.poll(lambda: _picker_options(r).get(LLAMA_OPTION) is False, 10)
        r.check(ok, "sélecteur : le faux llama-server est choisissable")
        seq = r.ev.mark()
        page.select_option("#model-picker", label=LLAMA_OPTION)
        page.click("#model-picker-apply")
        ended = r.ev.wait("model_load_ended", seq, timeout=30)
        r.check(ended["payload"]["status"] == "ok", "faux llama-server chargé à 8 192")
        r.ev.wait("context_window_state", seq, lambda p: p["hosting"] == "server", 10)
        r.wait_idle()
        # The first call after a load warms it up and is never measured: the second is.
        r.send("Bonjour")
        seq = r.ev.mark()
        r.send("Bonjour encore")
        r.ev.wait("context_window_state", seq, lambda p: p["read_tps"] is not None, 10)
        _window_panel(r)
        page.locator('#window-choices input[name="window-choice"][value="16384"]').check()
        row = page.locator('#window-choices .window-choice[data-window="16384"]')
        r.check(
            row.locator(
                ".window-choice-bound", has_text="bornée à 8 192 par llama-server"
            ).first.is_visible(),
            "16 384 noté : « bornée à 8 192 par llama-server (-c) » visible avant d'appliquer",
            row.inner_text().replace("\n", " · "),
        )
        r.check(
            re.search(r"Temps de lecture : au moins ≈ \d", row.inner_text()) is not None
            and "réservé par llama-server" in row.inner_text(),
            "llama-server : temps de lecture mesuré (« au moins ≈ N s ») et cache réservé par "
            "son -c",
            row.inner_text().replace("\n", " · "),
        )
        r.shot("45-fenetre-contexte-reglage")
        page.click("#window-close")
        expect(page.locator("#window-panel")).to_be_hidden(timeout=5000)

        # Lot K (A3): 16 384 applied, bounded to 8 192 by the server: the button shows the
        # effective window, its tooltip the one chosen.
        state = _apply_window(r, 16384)
        toggle = page.locator("#window-toggle")
        title = toggle.get_attribute("title") or ""
        r.check(
            state["window"] == 8192
            and "8\u202f192" in page.inner_text("#window-toggle-value")
            and title.endswith(", 16\u202f384 choisi."),
            "16 384 appliqué, borné par llama-server : bouton « Fenêtre 8 192 ▾ », infobulle "
            "« …, 16 384 choisi »",
            f"{page.inner_text('#window-toggle-value')} · {title}",
        )
        if not page.locator("#window-panel").is_hidden():
            page.click("#window-close")

        # A reload of the served model: 4 096 shrinks its effective window (8 192).
        seq = r.ev.mark()
        _apply_window(r, 4096)
        started = r.ev.wait("model_load_started", seq, timeout=10)["payload"]
        ended = r.ev.wait("model_load_ended", seq, timeout=30)["payload"]
        r.check(
            started.get("window") == 4096
            and started["phase_label"]
            == "Rechargement de faux-llama-server avec une fenêtre de 4\u202f096 tokens…"
            and ended["status"] == "ok",
            "llama-server : « Rechargement de … avec une fenêtre de 4 096 tokens… », puis ok",
            f"{started['phase_label']} · {ended['status']}",
        )
        expect(page.locator("#top-status")).to_have_text(
            "Fenêtre de contexte : 4\u202f096 tokens (conversation gardée).", timeout=10_000
        )
        r.check(
            True,
            "barre de l'atelier : « Fenêtre de contexte : 4 096 tokens (conversation gardée). »",
        )
    finally:
        # (d) Back to the fake cloud A and to 4 096: `relaunch` expects them. A failure here
        # is its own check, never a mask over the one that led here.
        try:
            page.keyboard.press("Escape")
            r.goto_app()
            if (r.state().get("active_model") or {}).get("ref") != MODEL_ENTRY_ID:
                _pick_model(r, A_LABEL)
            if (r.state().get("context_window_state") or {}).get("configured") != 4096:
                _apply_window(r, 4096)
        except Exception as exc:  # noqa: BLE001 - reported, the scenario's own error kept
            r.check(False, "retour au faux cloud A et à 4 096", f"{type(exc).__name__}: {exc}")
    saved = json.loads((r.stack.data_dir / "settings.json").read_text(encoding="utf-8"))
    r.check(
        (saved.get("context") or {}).get("window") == 4096
        and saved.get("selected_model") == {"kind": "cloud", "ref": MODEL_ENTRY_ID},
        "retour au faux cloud A et à 4 096 (settings.json)",
        str({k: saved.get(k) for k in ("context", "selected_model")}),
    )
    expect(page.locator("#window-toggle")).to_contain_text("Fenêtre 4 096", timeout=10_000)


def s_relaunch(r: Run) -> None:
    """Story 11: the cloud model chosen is kept at the next launch, without a new warning."""
    saved = json.loads((r.stack.data_dir / "settings.json").read_text(encoding="utf-8"))
    r.check(
        saved.get("selected_model") == {"kind": "cloud", "ref": MODEL_ENTRY_ID},
        "settings.json retient le modèle cloud choisi",
        str(saved.get("selected_model")),
    )
    r.goto_app()
    r.wait_idle()
    for _ in range(10):  # a longer journal than the new process will have at first
        r.send("Bonjour")
    old_tip = r.ev.mark()
    r.page.evaluate("() => { window.__e2eBeforeRelaunch = true; }")
    r.stack.restart_app()
    r.earlier_events += r.ev.items  # kept for the run's summary
    r.ev = Events(r.stack.app_url)  # a new process: a new journal, from seq 1
    # The tab left open reconnects on its own (streamEvents, every second); the trainer
    # types in it, as he would after « relancez WaveStack pour l'utiliser ».
    time.sleep(4)
    reloaded = r.page.evaluate("() => window.__e2eBeforeRelaunch !== true")
    r.check(reloaded, "onglet resté ouvert : la page se recharge d'elle-même à la reconnexion (A1)")
    r.wait_idle()  # its barrier: the reloaded page replayed the new journal
    seq = r.ev.mark()
    r.page.fill("#composer-input", "Message après la relance")
    r.page.press("#composer-input", "Enter")
    try:
        r.ev.wait("turn_ended", seq, timeout=15)
        sent = "tour terminé côté serveur"
    except TimeoutError:
        sent = "aucun tour côté serveur"
    answer = "Réponse scriptée du faux modèle au message : « Message après la relance »"
    last = r.page.locator("#chat .bubble-model").last
    ok, took = r.poll(lambda: answer in last.inner_text(), 8)
    r.shot("18-onglet-ouvert-apres-relance")
    r.check(
        ok,
        "onglet resté ouvert pendant la relance : la réponse s'affiche",
        f"{sent} ; journal : seq {old_tip} avant relance, {r.ev.mark()} après ; Vue humain : "
        + r.page.locator("#chat .bubble-model").last.inner_text()[:80].replace("\n", " "),
    )
    r.goto_app()
    expect(r.page.locator("#model-indicator")).to_contain_text("wavestack-fake", timeout=30_000)
    r.wait_idle()
    r.check(True, "relance : le faux modèle est repris sans passer par le diagnostic")
    ended = r.send("Bonjour")
    r.check(ended["payload"]["status"] == "completed", "relance : un tour aboutit")
    r.page.goto(f"{r.stack.app_url}/diagnostic")
    checks = r.page.locator("#checks")
    expect(checks).to_contain_text("lors d'un lancement précédent", timeout=10_000)
    r.check(True, "diagnostic : « choisi lors d'un lancement précédent »")
    r.check(r.page.locator("#cloud-warning").is_hidden(), "aucun nouvel avertissement cloud")
    r.goto_app()


def _pick_model(r: Run, label: str) -> None:
    """The top bar's picker: note the entry, « Choisir… », confirm the cloud warning."""
    page = r.page
    r.wait_idle()
    seq = r.ev.mark()
    page.select_option("#model-picker", label=label)
    page.click("#model-picker-apply")
    expect(page.locator("#cloud-warning")).to_be_visible(timeout=5000)
    page.click("#cloud-warning-confirm")
    ended = r.ev.wait("model_load_ended", seq, timeout=30)
    r.check(ended["payload"]["status"] == "ok", f"chargement de « {label} »")
    r.wait_idle()
    time.sleep(0.5)


def s_reasoning_locked(r: Run) -> None:
    """Story 33: a model that always reasons locks the Reasoning card (🔒, « Imposé par ce
    modèle »); back on entry A, the lock goes."""
    r.launch("bare_llm")
    a_label = "RÉSEAU · Faux fournisseur (e2e) · wavestack-fake"
    try:
        _pick_model(r, f"RÉSEAU · Faux fournisseur R (e2e) · {REASONING_MODEL}")
        card = r.card("Raisonnement")
        toggle = card.locator(".brick-head input.brick-toggle")
        r.check(
            toggle.is_checked() and toggle.is_disabled(),
            "modèle qui raisonne toujours : interrupteur coché et désactivé",
        )
        r.check(card.locator(".brick-lock").is_visible(), "🔒 à côté de l'interrupteur")
        status = card.locator("p.brick-status").inner_text()
        r.check(status == "Imposé par ce modèle", "ligne d'état « Imposé par ce modèle »", status)
        r.shot_element("34-raisonnement-impose", '.pane[data-pane="bricks"]')
    finally:
        # Entry A back whatever happened: the scenarios after this one play on it.
        if (r.state().get("active_model") or {}).get("ref") != MODEL_ENTRY_ID:
            r.goto_app()  # a clean page, whatever dialog a failure left open
            _pick_model(r, a_label)
    card = r.card("Raisonnement")
    toggle = card.locator(".brick-head input.brick-toggle")
    status = card.locator("p.brick-status").inner_text()
    # Entry A does not reason: the card is no longer locked, it says it is off or unavailable.
    r.check(
        not toggle.is_checked()
        and card.locator(".brick-lock").count() == 0
        and status != "Imposé par ce modèle",
        "retour à l'entrée A : plus de verrou ni de « Imposé par ce modèle »",
        status,
    )


def s_reasoning_dropped(r: Run) -> None:
    """Finition V1 (#28, #35): the fake provider in Anthropic's shape throws away the
    reasoning of an earlier turn (`input_transformations`, « [jeté] »), in the turn and in
    the sub-agent's calls. Orchestration's row « Raisonnement jeté par le fournisseur » and
    its figure « historique réécrit », at both levels; the log's summary « {reason} · {path} »."""
    page = r.page
    r.launch("subagent")
    a_label = "RÉSEAU · Faux fournisseur (e2e) · wavestack-fake"
    try:
        _pick_model(r, f"RÉSEAU · {ANTHROPIC_PROVIDER} · {ANTHROPIC_MODEL}")
        seq = r.ev.mark()
        ended = r.send(_prompts("subagent")[0] + " [jeté]")
        r.check(
            ended["payload"]["status"] == "completed",
            "#28 : tour terminé sur le faux fournisseur au format Anthropic",
            ended["payload"]["status"],
        )
        dropped = r.ev.since(seq, "reasoning_dropped")
        main = [e for e in dropped if e["context_id"] == "main"]
        sub = [e for e in dropped if (e["context_id"] or "").startswith("sub")]
        r.check(
            main
            and sub
            and all(e["payload"]["reason"] == "prefix_binding_mismatch" for e in dropped),
            "#28 : reasoning_dropped émis au tour et au sous-agent",
            str([(e["context_id"], e["payload"]["reason"]) for e in dropped]),
        )
        rail = page.locator("#orch-scroll")
        title = "Raisonnement jeté par le fournisseur"
        top = rail.locator(".turn-step:not(.is-sub) .turn-step-line", has_text=title)
        child = rail.locator(".turn-step.is-sub", has_text=title)
        shown, _ = r.poll(lambda: top.count() >= 1 and child.count() >= 1, 10)
        figures = [x.first.inner_text() if x.count() else "" for x in (top, child)]
        r.check(
            shown and all("historique réécrit" in f for f in figures),
            "#35 : ligne « Raisonnement jeté par le fournisseur » et figure « historique "
            "réécrit », au tour et chez le sous-agent",
            " · ".join(f[:100] for f in figures),
        )
        top.first.click()
        body = top.first.locator("xpath=following-sibling::div[contains(@class,'turn-step-body')]")
        said = main[0]["payload"]["message_text"] if main else ""
        unfolded, _ = r.poll(lambda: bool(said) and said in (body.text_content() or ""), 5)
        r.check(
            unfolded,
            "#35 : l'étape dépliée donne la phrase du harnais",
            (body.text_content() or "")[:200] if body.count() else "aucun corps",
        )
        page.click("#event-log-head")
        try:
            expect(page.locator("#event-log-list")).to_be_visible(timeout=5000)
            rows = [x for x in page.evaluate(_LOG_ROWS_JS) if x["kind"] == "reasoning_dropped"]
            path = main[0]["payload"]["path"] if main else "?"
            r.check(
                rows
                and all(x["summary"] == f"historique réécrit · {path}" for x in rows)
                and rows[0]["name"] == "Raisonnement jeté",
                "#35 : le journal résume « historique réécrit · <chemin> »",
                str(rows[:2]),
            )
        finally:
            page.click("#event-log-head")
        r.shot_element("35-raisonnement-jete", '.pane[data-pane="orch"]')
    finally:
        # Entry A back whatever happened: the scenarios after this one play on it.
        if (r.state().get("active_model") or {}).get("ref") != MODEL_ENTRY_ID:
            r.goto_app()
            _pick_model(r, a_label)


# ---------- Gemini (Google AI Studio): the shape of its bodies ----------

GEMINI_LABEL = f"RÉSEAU · {GEMINI_PROVIDER} · {GEMINI_MODEL}"


def _gemini_turn(r: Run, prompt: str, tool: str) -> tuple[list[dict], list[dict], dict]:
    """One turn on the fake Gemini: the bodies it received, the `model_call_ended`
    payloads, and `turn_ended`."""
    before = len(r.fake_calls())
    seq = r.ev.mark()
    ended = r.send(prompt)
    bodies = r.fake_calls()[before:]
    calls = [e["payload"] for e in r.ev.since(seq, "model_call_ended")]
    tools = [e["payload"]["tool"] for e in r.ev.since(seq, "tool_started")]
    r.check(
        ended["payload"]["status"] == "completed" and tool in tools,
        f"tour « {prompt} » terminé, {tool} appelé",
        f"{ended['payload']['status']} · {tools}",
    )
    r.check(not r.ev.since(seq, "harness_error"), f"aucun harness_error ({tool})")
    return bodies, calls, ended


def _signature_replayed(r: Run, bodies: list[dict], calls: list[dict], what: str) -> None:
    signed = (calls[0].get("tool_calls") or [{}])[0].get("extra_content") if calls else None
    sent = None
    if len(bodies) >= 2:
        # The turn's own call: the last one (short memory sends the earlier turns' before).
        messages = bodies[1]["messages"]
        assistant = next((m for m in reversed(messages) if m.get("tool_calls")), {})
        sent = (assistant.get("tool_calls") or [{}])[0].get("extra_content")
    signature = ((signed or {}).get("google") or {}).get("thought_signature", "")
    r.check(
        signature.startswith("signature-fausse-") and sent == signed,
        f"{what} : signature tracée dans model_call_ended, rejouée telle quelle au 2e corps",
        f"{signed} · {sent}",
    )


def _gemini_costs(r: Run, calls: list[dict]) -> None:
    """FinOps: each call's cost (the fake gives `usage`), its line in the call's body, the
    turn's total in its head, the session's in the top bar, the same after a reload."""
    page = r.page
    r.check(
        len(calls) == 2
        and all(c.get("cost_in_usd") and c.get("cost_out_usd") for c in calls)
        and all(c.get("cost_source") == "api" for c in calls),
        "FinOps : coût d'entrée et de sortie sur chaque appel, tiré de usage",
        str([(c.get("cost_in_usd"), c.get("cost_out_usd"), c.get("cost_source")) for c in calls]),
    )
    _unfold_step(r, "Appelle le modèle")
    counters = (
        _step(r, "Appelle le modèle").locator(".turn-step-body .token-counter").all_inner_texts()
    )
    cost = next((t for t in counters if t.startswith("Coût estimé : ")), "")
    r.check(
        cost.startswith("Coût estimé : entrée ") and " $ · sortie " in cost and "≈" not in cost,
        "FinOps : « Coût estimé : entrée … $ · sortie … $ » dans le corps de l'appel",
        cost or str(counters),
    )
    head = page.locator("#orch-scroll .turn-group .turn-group-figures").last.inner_text()
    r.check(
        "coût estimé entrée " in head and " $ · sortie " in head,
        "FinOps : le total du tour dans son en-tête",
        head,
    )
    spend = r.state().get("consumption_updated") or {}
    top = page.locator("#consumption")
    expect(top).to_be_visible(timeout=5000)
    text = top.inner_text()
    # Lot 1 of 2026-10-04: three lines, « Dépense estimée », « 💰 … $ + … $ », « 🍃 … g CO₂e »
    # (two without a footprint measured).
    lines = text.split("\n")
    label, amounts = lines[0], lines[1] if len(lines) > 1 else ""
    green = spend.get("impact_calls", 0) > 0
    title = top.get_attribute("title") or ""
    r.check(
        label == "Dépense estimée"
        and amounts.startswith("💰 ")
        and amounts.count(" $") == 2
        and " + " in amounts
        and len(lines) == (3 if green else 2)
        and (not green or (lines[2].startswith("🍃 ") and lines[2].endswith(" g CO₂e")))
        and spend.get("calls", 0) >= 2
        and title.startswith("Dépense API estimée de la séance : entrée ")
        and ", sortie " in title
        and " € au taux de " in title
        and top.get_attribute("aria-label") == title,
        "FinOps : « Dépense estimée » dans la barre de l'atelier, « 💰 entrée + sortie » sur sa "
        "ligne (« 🍃 » sur la troisième), la phrase entière "
        "(euros compris) en infobulle et en nom accessible",
        f"{text!r} · {title} · {spend}",
    )
    cap = r.state().get("max_session_usd")
    cap_text = f"{cap:g}".replace(".", ",") if cap is not None else "?"
    # The reset sentence counts the totals shown (spend, footprint), never the cap's.
    reset = (
        "Seul un relancement de WaveStack remet ces totaux à zéro."
        if spend.get("impact_calls", 0) > 0
        else "Seul un relancement de WaveStack remet ce total à zéro."
    )
    r.check(
        cap is not None
        and "Plafond de dépense de la séance : " in title
        and f" $ sur {cap_text} $ ; une fois le plafond atteint, aucun appel payant ne part."
        in title
        and title.endswith(reset),
        "Finition V1 (#27) : le plafond de la séance dans l'infobulle de la dépense, "
        "et la phrase de remise à zéro au nombre des totaux affichés",
        f"{cap} · {title}",
    )
    ok, detail = _bar_fits(r)
    r.check(
        ok,
        "FinOps : barre de l'atelier entière, sur une ligne, avec la dépense (1600 × 1000)",
        detail,
    )
    r.reload_app()
    again = page.locator("#consumption")
    expect(again).to_be_visible(timeout=5000)
    r.check(
        again.inner_text() == text,
        "FinOps : après un rechargement, le même total dans la barre de l'atelier",
        again.inner_text(),
    )
    # Finition V1 (#27): the diagnostic says the cap and the spend so far, under the cloud
    # models (`#cloud-cap`, from `spend_cap`).
    page.goto(f"{r.stack.app_url}/diagnostic")
    line = page.locator("#cloud-cap")
    expect(line).to_be_visible(timeout=20_000)
    said = line.inner_text()
    r.check(
        said.startswith("Plafond de dépense de la séance : ")
        and f" $ dépensés sur {cap_text} $." in said
        and "max_session_usd" in said,
        "Finition V1 (#27) : le diagnostic dit le plafond et la dépense de la séance",
        said,
    )
    r.goto_app()


def _footprint_line(r: Run) -> tuple[str, str]:
    """GreenOps: the « Empreinte estimée » line of the last call's body, and its tooltip.

    E141 (restes différés, story 6): `Run.send` returns on the `turn_ended` the stream thread
    read, maybe before the page rendered it. The step « Appelle le modèle », still current
    there, was unfolded by the live view: `_unfold_step` did not click, then the live view
    folded it. So: the turn rendered ended first, then the step unfolded (clicked again if a
    render folds it) until its footprint is rendered; no fixed delay."""
    _turn_rendered_ended(r, timeout=5)
    step = _step(r, "Appelle le modèle")
    line = step.locator(".turn-step-body .footprint")

    def rendered() -> bool:
        if not step.locator(".turn-step-body").count():
            step.locator(".turn-step-line").click()
        return line.count() > 0

    ok, _ = r.poll(rendered, 5)  # the former `wait_for`'s bound, no longer
    if not ok:
        body = step.locator(".turn-step-body")
        return "", " | ".join(body.all_inner_texts())
    return line.first.inner_text(), line.first.get_attribute("title") or ""


def _session_footprint(r: Run, what: str) -> None:
    """GreenOps: the turn's footprint in its head, the session's in the top bar (lot 1 of
    2026-10-04: its own line, « 🍃 … g CO₂e », always shown; its sentence in the tooltip), the
    bar whole at 1600, 1440 and 1280 px, normal and projection mode."""
    page = r.page
    head = page.locator("#orch-scroll .turn-group .turn-group-figures").last.inner_text()
    r.check(
        "empreinte estimée " in head, f"GreenOps ({what}) : la somme du tour dans son en-tête", head
    )
    top = page.locator("#consumption")
    expect(top).to_be_visible(timeout=5000)
    title = top.get_attribute("title") or ""
    spend = r.state().get("consumption_updated") or {}
    shown = page.locator("#consumption-footprint")
    grams = shown.inner_text() if shown.is_visible() else ""
    lines = top.inner_text().split("\n")
    r.check(
        "Empreinte estimée de la séance : " in title
        and " g CO₂e" in title
        and top.get_attribute("aria-label") == title
        and spend.get("impact_calls", 0) >= 1
        and grams.startswith("🍃 ")
        and grams.endswith(" g CO₂e")
        and lines[-1] == grams
        and len(lines) == (3 if spend.get("calls") else 2),
        f"GreenOps ({what}) : l'empreinte de la séance dans la barre de l'atelier, « 🍃 » sur sa "
        "propre ligne (sa phrase en infobulle)",
        f"{top.inner_text()!r} · {title} · {spend.get('impact_calls')}",
    )
    # The bar whole with the session's block, at every width of the themes' check, in normal
    # and in projection mode, the footprint's line always shown.
    toggle = page.locator("#projection-toggle")
    visible: dict[str, bool] = {}
    try:
        for width, height in ((1600, 1000), (1440, 900), (1280, 720)):
            page.set_viewport_size({"width": width, "height": height})
            for projection in (False, True):
                if projection:
                    _toggle_projection(page)
                time.sleep(0.3)
                ok, detail = _bar_fits(r)
                mode = "mode projection" if projection else "mode normal"
                shown = page.locator("#consumption-footprint").is_visible()
                visible[f"{width} {mode}"] = shown
                r.check(
                    ok and shown,
                    f"GreenOps ({what}) : barre entière avec l'empreinte visible, "
                    f"{width} × {height}, {mode}",
                    detail if shown else "ligne d'empreinte masquée",
                )
                if projection:
                    _toggle_projection(page)
    finally:
        if toggle.get_attribute("aria-pressed") == "true":  # never left in projection mode
            _toggle_projection(page)
        page.set_viewport_size({"width": 1600, "height": 1000})
        time.sleep(0.3)
    r.check(
        all(visible.values()),
        f"GreenOps ({what}) : l'empreinte visible dans la barre à chaque largeur, dans chaque mode",
        str(visible),
    )


def _gemini_footprint(r: Run, calls: list[dict]) -> None:
    """GreenOps: EcoLogits' range on each call of the fake Gemini (the preset's `impacts`), its
    line in the call's body, its warnings in French in the tooltip."""
    r.check(
        len(calls) == 2
        and all(c.get("impact_method") == "ecologits" for c in calls)
        and all(0 < c["energy_wh_min"] < c["energy_wh_max"] for c in calls)
        and all(0 < c["gco2e_min"] < c["gco2e_max"] for c in calls),
        "GreenOps : fourchette EcoLogits (Wh, g CO₂e) sur chaque appel du faux Gemini",
        str([(c.get("energy_wh_min"), c.get("energy_wh_max")) for c in calls]),
    )
    text, title = _footprint_line(r)
    r.check(
        text.startswith("Empreinte estimée : ")
        and any(mark in text for mark in ("–", "≤", "<"))  # a range, or under 0,001
        and " Wh · " in text
        and text.endswith(" g CO₂e")
        and "architecture non publiée" in title,
        "GreenOps : « Empreinte estimée : a–b Wh · c–d g CO₂e » dans le corps de l'appel, "
        "avertissements d'EcoLogits en français dans l'infobulle",
        f"{text} · {title[:160]}",
    )
    _session_footprint(r, "faux Gemini")


def _local_footprint(r: Run, calls: list[dict]) -> None:
    """GreenOps: the fake llama-server runs in another process: CodeCarbon on the whole
    machine, « poste entier » in the tooltip; without the `greenops` extra, « indisponible »
    and the command that installs it."""
    # `--no-greenops`: WaveStack plays the extra absent (`wavestack_e2e.py`).
    installed = (
        os.environ.get("WAVESTACK_E2E_NO_GREENOPS") != "1"
        and importlib.util.find_spec("codecarbon") is not None
    )
    spend = r.state().get("consumption_updated") or {}
    if installed and not spend.get("calls"):
        # Before any priced cloud call: « Empreinte estimée » over the footprint alone.
        label = r.page.locator("#consumption-label").inner_text()
        amounts = r.page.locator("#consumption-footprint").inner_text()
        whole = r.page.locator("#consumption").inner_text()
        r.check(
            label == "Empreinte estimée"
            and amounts.startswith("🍃 ")
            and amounts.endswith(" g CO₂e")
            and "$" not in whole
            and "💰" not in whole
            and whole.split("\n") == [label, amounts],
            "GreenOps : sans dépense, deux lignes, « Empreinte estimée » sur « 🍃 … g CO₂e » (ni "
            "« $ », ni « · » en tête)",
            f"{label!r} · {amounts!r}",
        )
    notes = [c.get("impact_note_text") or "" for c in calls]
    text, title = _footprint_line(r)
    if installed:
        r.check(
            bool(calls)
            and all(c.get("impact_method") == "codecarbon" for c in calls)
            and all(c.get("energy_wh_min", -1) >= 0 for c in calls)
            and all("poste entier" in n for n in notes),
            "GreenOps : chaque appel au faux llama-server mesuré par CodeCarbon (poste entier)",
            str([(c.get("impact_method"), c.get("energy_wh_min")) for c in calls]),
        )
        r.check(
            text.startswith("Empreinte estimée : ")
            and " Wh · " in text
            and text.endswith(" g CO₂e")
            and "poste entier" in title
            and "estimation (TDP × charge, sans droits administrateur)" in title,
            "GreenOps : « Empreinte estimée » dans le corps de l'appel local, « poste entier » et "
            "« estimation (TDP × charge…) » dans l'infobulle",
            f"{text} · {title[:160]}",
        )
        _session_footprint(r, "faux llama-server")
    else:
        r.check(
            bool(calls)
            and all("energy_wh_min" not in c for c in calls)
            and all("uv sync --extra greenops" in n for n in notes)
            and text == "Empreinte estimée : indisponible"
            and "uv sync --extra greenops" in title,
            "GreenOps sans l'extra : empreinte locale « indisponible », la commande en infobulle",
            f"{text} · {title[:160]}",
        )


def s_gemini_shape(r: Run) -> None:
    """The fake Gemini (`fake_g`, the reasoning and `tool_call_extra` of the real preset): a
    tool turn with the reasoning off (`reasoning_effort: minimal`, 512), then on
    (`extra_body…include_thoughts`, 1 536, `<thought>` read as reasoning), the thought
    signature sent back each time; the Reasoning card « activable »."""
    r.goto_app()
    r.launch("native_tools")
    try:
        _pick_model(r, GEMINI_LABEL)
        active = r.state().get("active_model") or {}
        r.check(active.get("ref") == GEMINI_ENTRY_ID, "faux Gemini actif", str(active.get("ref")))
        r.set_brick("Raisonnement", False)
        card = r.card("Raisonnement")
        toggle = card.locator(".brick-head input.brick-toggle")
        r.check(
            not toggle.is_disabled() and card.locator(".brick-lock").count() == 0,
            "faux Gemini : carte Raisonnement réglable, sans verrou",
        )

        bodies, calls, _ = _gemini_turn(r, "Quelle heure est-il ?", "get_datetime")
        first = bodies[0] if bodies else {}
        r.check(
            len(bodies) == 2
            and first.get("reasoning_effort") == "minimal"
            and "extra_body" not in first
            and first.get("max_tokens") == 512,
            "raisonnement éteint : reasoning_effort « minimal », sans extra_body, 512 tokens",
            json.dumps({k: v for k, v in first.items() if k not in ("messages", "tools")}),
        )
        _signature_replayed(r, bodies, calls, "raisonnement éteint")
        r.check(
            all(not c.get("reasoning") for c in calls), "raisonnement éteint : aucune réflexion"
        )
        _gemini_footprint(r, calls)
        _gemini_costs(r, calls)

        r.set_brick("Raisonnement", True)
        r.check(toggle.is_checked(), "carte Raisonnement allumée sur le faux Gemini")
        seq = r.ev.mark()
        bodies, calls, _ = _gemini_turn(r, "Combien font 12 multiplié par 37 ?", "calculator")
        first = bodies[0] if bodies else {}
        thinking = ((first.get("extra_body") or {}).get("google") or {}).get("thinking_config")
        r.check(
            thinking == {"thinking_level": "high", "include_thoughts": True}
            and "reasoning_effort" not in first
            and first.get("max_tokens") == 1536,
            "raisonnement allumé : extra_body…include_thoughts, sans reasoning_effort, 1 536",
            json.dumps({k: v for k, v in first.items() if k not in ("messages", "tools")}),
        )
        _signature_replayed(r, bodies, calls, "raisonnement allumé")
        reasoning = calls[0].get("reasoning", "") if calls else ""
        r.check(
            reasoning.startswith("Je réfléchis")
            and all("<thought>" not in c.get("text", "") for c in calls)
            and "<thought>" in (calls[0].get("raw_output", "") if calls else ""),
            "<thought>…</thought> lu comme réflexion, hors du texte, gardé dans raw_output",
            reasoning[:120],
        )
        channels = {e["payload"]["channel"] for e in r.ev.since(seq, "model_delta")}
        r.check("reasoning" in channels, "deltas du canal reasoning", str(channels))
        answer = r.last_answer()
        r.check("<thought>" not in answer and "444" in answer, "bulle sans balise", answer[:160])
        r.shot("59-gemini-raisonnement")
        r.set_brick("Raisonnement", False)
    finally:
        # Entry A back whatever happened: the scenarios after this one play on it.
        if (r.state().get("active_model") or {}).get("ref") != MODEL_ENTRY_ID:
            r.goto_app()
            _pick_model(r, A_LABEL)
    r.check(
        (r.state().get("active_model") or {}).get("ref") == MODEL_ENTRY_ID,
        "retour à l'entrée A",
    )


PRICED_LABEL = f"RÉSEAU · {PRICED_PROVIDER} · {PRICED_MODEL}"


def s_priced_estimate(r: Run) -> None:
    """E135 (restes différés, story 6): `fake_m`, priced (the Mistral preset's prices) and
    never asking for `usage` (`stream_usage = false`): its cost is an estimate, said « ≈ » on
    the call's line, in the turn's head and in the top bar. Alone, it starts from the fake
    cloud A and goes back to it, even after a failure."""
    r.goto_app()
    r.launch("bare_llm")
    try:
        _pick_model(r, PRICED_LABEL)
        active = r.state().get("active_model") or {}
        r.check(active.get("ref") == PRICED_ENTRY_ID, "fake_m actif", str(active.get("ref")))
        before = len(r.fake_calls())
        seq = r.ev.mark()
        ended = r.send("Bonjour")
        bodies = r.fake_calls()[before:]
        calls = [e["payload"] for e in r.ev.since(seq, "model_call_ended")]
        r.check(
            ended["payload"]["status"] == "completed"
            and len(bodies) == 1
            and "stream_options" not in bodies[0]
            and len(calls) == 1
            and calls[0].get("cost_source") == "estimate"
            and calls[0].get("usage_source") == "estimate",
            "fake_m : aucun usage demandé (stream_usage = false), coût et tokens estimés",
            f"{sorted(k for k in (bodies or [{}])[0] if k != 'messages')} · "
            f"{[(c.get('cost_source'), c.get('usage_source')) for c in calls]}",
        )
        _turn_rendered_ended(r, ended["turn_id"])
        _unfold_step(r, "Appelle le modèle")
        counters = (
            _step(r, "Appelle le modèle")
            .locator(".turn-step-body .token-counter")
            .all_inner_texts()
        )
        cost = next((t for t in counters if t.startswith("Coût estimé : ")), "")
        r.check(
            cost.startswith("Coût estimé : entrée ≈ ") and " $ · sortie ≈ " in cost,
            "E135 : « ≈ » devant chaque montant sur la ligne de coût de l'appel",
            cost or str(counters),
        )
        head = _turn_group(r, ended["turn_id"]).locator(".turn-group-figures").inner_text()
        r.check(
            "coût estimé entrée ≈ " in head and " $ · sortie ≈ " in head,
            "E135 : « ≈ » dans le total du tour, en tête de son groupe",
            head,
        )
        spend = r.state().get("consumption_updated") or {}
        money = r.page.locator("#consumption-money").inner_text()
        r.check(
            spend.get("approx") is True and money.startswith("💰 ≈ "),
            "E135 : « ≈ » devant la dépense de la séance dans la barre de l'atelier",
            f"{money!r} · approx {spend.get('approx')}",
        )
    finally:
        # Entry A back whatever happened: the scenarios after this one play on it.
        if (r.state().get("active_model") or {}).get("ref") != MODEL_ENTRY_ID:
            r.goto_app()
            _pick_model(r, A_LABEL)
    r.check(
        (r.state().get("active_model") or {}).get("ref") == MODEL_ENTRY_ID,
        "retour à l'entrée A",
    )


# ---------- story 29: the « LLM nu » screen ----------

LLM_TEXT = "Bonjour <|im_end|> 🙂"


def _pick_served(r: Run, label: str) -> None:
    """The top bar's picker, a model an already-running server serves (no cloud warning)."""
    page = r.page
    r.wait_idle()
    page.locator("#model-picker").blur()
    r.poll(lambda: _picker_options(r).get(label) is False, 10)
    seq = r.ev.mark()
    page.select_option("#model-picker", label=label)
    page.click("#model-picker-apply")
    ended = r.ev.wait("model_load_ended", seq, timeout=30)
    r.check(ended["payload"]["status"] == "ok", f"chargement de « {label} »")
    r.wait_idle()


def _goto_lab(r: Run) -> None:
    """The « LLM nu » page, once it has read `/api/llm_lab`."""
    r.page.goto(f"{r.stack.app_url}/llm")
    expect(r.page.locator("body[data-lab-ready]")).to_be_attached(timeout=10_000)


def _lab_tokenize(r: Run, text: str) -> dict[str, Any]:
    page = r.page
    page.fill("#llm-prompt", text)
    expect(page.locator("#tokenize-button")).to_be_enabled(timeout=10_000)
    seq = r.ev.mark()
    page.click("#tokenize-button")
    event = r.ev.wait("llm_tokenized", seq, timeout=15)
    expect(page.locator("#token-counts")).to_be_visible(timeout=5000)
    return event


def _plain(text: str) -> str:
    return text.replace("\u202f", " ").replace("\u00a0", " ")


def s_llm_screen(r: Run) -> None:
    """Story 29: the « LLM nu » screen. The top bar's link (whole, the bar on one line at
    1600 × 1000), the workshop's theme on `/llm`; the tokenization on the fake cloud A (the
    tokenizer is at the provider: the estimate, no chip), then on the fake llama-server
    (chips with their id, `<|im_end|>` one special token, the diagram's real sizes). Back to
    the fake cloud A at the end."""
    page = r.page
    page.set_viewport_size({"width": 1600, "height": 1000})
    r.goto_app()
    r.wait_idle()
    if (r.state().get("active_model") or {}).get("ref") != MODEL_ENTRY_ID:
        _pick_model(r, A_LABEL)
    try:
        _llm_screen(r)
    finally:
        if page.url.rstrip("/").endswith("/llm") or not page.url.startswith(r.stack.app_url):
            r.goto_app()
        if page.locator("#theme-picker").count():
            _pick_theme(page, "system")
        if (r.state().get("active_model") or {}).get("ref") != MODEL_ENTRY_ID:
            _pick_model(r, A_LABEL)


def _llm_screen(r: Run) -> None:
    page = r.page
    # (1) The link, whole in the shared bar (story 2 of 2026-09-30), which stays on one line.
    link = page.locator('.site-nav a[href="/llm"]')
    r.check(
        link.is_visible() and link.inner_text() == "LLM",
        "barre commune : lien « LLM » visible et entier",
        link.inner_text(),
    )
    ok, detail = _bar_fits(r)
    r.check(
        ok, "barre commune et barre de l'atelier entières, sur une ligne, à 1600 × 1000", detail
    )

    # (2) The workshop's theme applies on /llm.
    _pick_theme(page, "dark")
    link.click()
    page.wait_for_url("**/llm")
    expect(page.locator("body[data-lab-ready]")).to_be_attached(timeout=10_000)
    r.check(
        _theme_attr(r) == "dark"
        and _body_bg(r) == _design_rgb("surface-dark")
        and page.locator("select[data-theme-picker]").count() == 1
        and page.locator("#theme-picker").input_value() == "dark",
        "/llm : sélecteur de thème, le thème sombre choisi dans l'atelier s'applique",
        f"{_theme_attr(r)} · {_body_bg(r)}",
    )
    r.check(
        page.locator("h1").inner_text() == "Atelier LLM : l'intérieur du modèle"
        and page.title() == "WaveStack — Atelier LLM"
        and page.locator("nav.site-nav a[aria-current=page]").inner_text() == "LLM"
        and not _site_nav_problems(r),
        "/llm : titre « Atelier LLM », barre commune entière, « LLM » courant",
    )

    # (3) The fake cloud A: the tokenizer is at the provider.
    expect(page.locator("#llm-model")).to_contain_text("RÉSEAU", timeout=5000)
    event = _lab_tokenize(r, "Bonjour tout le monde")
    info = page.inner_text("#token-info")
    counts = page.inner_text("#token-counts")
    r.check(
        event["payload"]["exact"] is False
        and "chez Faux fournisseur (e2e)" in info
        and "≈" in counts
        and page.locator("#token-chips li").count()
        == page.locator("#token-chips li.is-example").count()
        == 5,
        "cloud A : le tokenizer est chez le fournisseur, estimation, les colonnes de l'exemple"
        " seulement (correction C du 2026-10-05)",
        f"{info} · {counts}",
    )
    dark = _contrast_sweep(r, ["main"])
    _pick_theme(page, "system")

    # (3b) A workshop turn running: « Générer » disabled with the reason, a direct call 409.
    seq = r.ev.mark()
    r.api("POST", "/api/intentions/send", {"message": "Explique le harnais [lent] [long]"})
    r.ev.wait("model_first_token", seq, timeout=20)
    button = page.locator("#generate-button")
    expect(button).to_be_disabled(timeout=5000)
    refused = r.api(
        "POST",
        "/api/intentions/llm_generate",
        {"prompt": "Bonjour", "sampling": _LAB_SAMPLING},
    )
    r.check(
        "tour" in (button.get_attribute("title") or "")
        and "tour" in page.inner_text("#llm-busy")
        and refused.status_code == 409,
        "tour de l'atelier en cours : « Générer » désactivé avec la raison, appel direct 409",
        f"{button.get_attribute('title')} · {refused.status_code} {refused.text[:120]}",
    )
    r.api("POST", "/api/intentions/stop")
    r.ev.wait("turn_ended", seq, timeout=30)
    expect(button).to_be_enabled(timeout=10_000)

    # (3c) The fake cloud A takes temperature and top-p only; top-k says why. Correction C
    # of 2026-10-05: its slider stays active, it moves the OUTPUT's example only.
    _set_lab_sampling(r)
    top_k = page.locator("#sampling-top_k")
    reason = page.inner_text('.sampling-row[data-setting="top_k"] .sampling-row-reason')
    r.check(
        top_k.is_enabled()
        and "non réglable chez Faux fournisseur (e2e)" in reason
        and "ne bouge que l'exemple" in reason,
        "cloud A : top-k actif pour l'exemple, sa raison visible pour le vrai tirage",
        reason,
    )
    ended = _lab_generate(r, "Bonjour")
    body = r.fake_calls()[-1]
    r.check(
        ended["payload"]["status"] == "completed"
        and body.get("temperature") == 0.2
        and body.get("top_p") == 0.9
        and "top_k" not in body
        and "min_p" not in body
        and body.get("messages") == [{"role": "user", "content": "Bonjour"}],
        "cloud A : le corps envoyé porte temperature et top_p seulement, un seul message",
        str({k: v for k, v in body.items() if k != "messages"}),
    )
    r.check(
        page.locator("#generation-cloud").is_visible()
        and page.locator("#generation-tokens .token-chip").count() >= 1,
        "cloud A : fragments reçus du fournisseur, dits comme tels",
    )
    _candidates_unavailable(r, "Faux fournisseur (e2e)", "cloud A")
    _distribution_unavailable(r, "Faux fournisseur (e2e)", "cloud A")
    _lab_compare_stopped(r)

    # (4) The fake llama-server, chosen in the workshop's picker.
    r.goto_app()
    _pick_served(r, LLAMA_OPTION)
    bubbles = page.locator("#chat .bubble").count()
    seq = r.ev.mark()
    _goto_lab(r)
    expect(page.locator("#llm-model")).to_contain_text("Local · llama-server", timeout=5000)
    # Correction C of 2026-10-05: a served model (exact tokenizer, no candidates read): the
    # example until « Découper en tokens », nothing cut nor drawn by the page itself.
    expect(page.locator("#output-tag")).to_have_class(re.compile("is-example"), timeout=5000)
    page.wait_for_timeout(1000)
    r.check(
        page.locator("#token-chips .token-chip.is-example").count() == 5
        and not r.ev.since(seq, "llm_tokenized")
        and not r.ev.since(seq, "llm_generation_started"),
        "llama-server, 1er chargement : l'exemple étiqueté, rien de découpé ni tiré sans clic",
    )
    # Increment 3: the last load, its steps and its memory.
    steps = page.locator("#loading-steps .load-step").all_inner_texts()
    memory = page.inner_text("#loading-memory")
    r.check(
        any("Connexion à llama-server" in t for t in steps)
        and "dans son propre processus" in memory
        and page.locator("#loading-local").is_visible()
        and page.inner_text("#loading-total").startswith("faux-llama-server : chargé en"),
        "chargement : les étapes (« Connexion ») et leur durée, la mémoire du modèle servi",
        f"{[t.replace(chr(10), ' ') for t in steps]} · {memory}",
    )
    event = _lab_tokenize(r, LLM_TEXT)
    payload = event["payload"]
    chips = page.locator("#token-chips .token-chip")
    shown = chips.evaluate_all(
        "cs => cs.map(c => ({id: c.querySelector('.token-chip-id').textContent,"
        " special: c.classList.contains('is-special'),"
        " label: c.querySelector('.token-chip-special')?.textContent ?? null}))"
    )
    specials = [c for c in shown if c["special"]]
    r.check(
        payload["exact"]
        and len(shown) == payload["token_count"] == len(payload["tokens"])
        and [c["id"] for c in shown] == [str(t["id"]) for t in payload["tokens"]],
        "llama-server : une puce par token, son identifiant dessous, total = token_count",
        f"{len(shown)} puces · token_count {payload['token_count']}",
    )
    r.check(
        specials == [{"id": "1002", "special": True, "label": "spécial"}],
        "llama-server : <|im_end|> est un seul token, marqué spécial (id 1002)",
        str(specials),
    )
    counts = _plain(page.inner_text("#token-counts"))
    r.check(
        counts.startswith(f"{payload['token_count']} tokens"),
        "compte des tokens et des caractères (session)",
        counts,
    )
    diagram = _plain(page.inner_text("#embedding-diagram"))
    r.check(
        "2 048" in diagram and "1 004" in diagram,
        "schéma de vectorisation : 2 048 dimensions, 1 004 tokens de vocabulaire",
        diagram.replace("\n", " · ")[:300],
    )
    r.shot("52-llm-nu-tokenisation", full_page=True)

    # (5) The screen's sampling reaches llama-server; the tokens come one by one. A workshop
    # tab left open meanwhile follows the state: busy, then back to idle, without reload.
    workshop = page.context.browser.new_page(viewport={"width": 1600, "height": 1000})
    workshop.goto(f"{r.stack.app_url}/")
    expect(workshop.locator("body[data-journal-replayed]")).to_be_attached(timeout=30_000)
    expect(workshop.locator("#composer-send")).to_be_enabled(timeout=30_000)
    _set_lab_sampling(r)
    seq = r.ev.mark()
    ended = _lab_generate(r, "Explique " + "très longuement " * 14, watch=True)
    back = True
    try:
        expect(workshop.locator("#composer-send")).to_be_enabled(timeout=10_000)
    except AssertionError:
        back = False
    idle = [e for e in r.ev.since(seq, "session_state") if e["payload"]["state"] == "idle"]
    r.check(
        back and idle and idle[-1]["context_id"] is None,
        "atelier déjà ouvert pendant la génération : revenu en idle sans rechargement",
        f"envoi actif : {back} · dernier idle : {idle[-1]['context_id'] if idle else 'aucun'}",
    )
    workshop.close()
    body = [q for q in r.stack.local_requests(r.stack.llama_url) if q["path"] == "/completion"][-1]
    sent = {k: body["body"].get(k) for k in ("temperature", "top_k", "top_p", "min_p")}
    started = [
        e["payload"]
        for e in r.ev.since(seq, "model_call_started")
        if e["context_id"] == "llm" and e["turn_id"] is None
    ]
    traced = started[-1]["sampling"] if started else {}
    r.check(
        sent == _LAB_SAMPLING
        and {k: traced.get(k) for k in _LAB_SAMPLING} == _LAB_SAMPLING
        and traced.get("source") == "screen",
        "llama-server : le corps /completion et model_call_started (contexte llm) portent les "
        "réglages, source screen",
        f"{sent} · {traced}",
    )
    first = page.inner_text("#reading-first-token")
    rate = page.inner_text("#generation-rate")
    r.check(
        ended["payload"]["status"] == "completed"
        and first.startswith("Premier token après")
        and rate.startswith("Débit de sortie"),
        "temps jusqu'au premier token puis débit affichés",
        f"{first} · {rate}",
    )
    r.check(
        page.inner_text("#reading-rendered").startswith("<|im_start|>user")
        and r.state()["session_state"]["state"] == "idle",
        "prompt rendu par le gabarit, session revenue en idle",
    )
    _lab_questions_and_window(r)
    light = _contrast_sweep(r, ["main"])
    r.check(not dark and not light, "/llm : contrastes AA dans les deux thèmes", str(dark + light))
    r.shot("53-llm-nu-generation", full_page=True)

    _candidates_unavailable(r, "llama-server", "llama-server")
    _distribution_unavailable(r, "llama-server", "llama-server")
    _lab_compare(r)

    # Increment 3: the reasoning, on the fake llama-server (Qwen3.5's template).
    toggle = page.locator("#reasoning-toggle")
    r.check(toggle.is_enabled(), "raisonnement : interrupteur activable (gabarit Qwen3.5)")
    toggle.check()
    seq = r.ev.mark()
    ended = _lab_generate(r, "Bonjour")
    started = r.ev.since(seq, "llm_generation_started")
    thinking = page.inner_text("#lane-thinking")
    answer = page.inner_text("#lane-answer")
    r.check(
        ended["payload"]["status"] == "completed"
        and started
        and started[-1]["payload"]["reserve"] == 1536
        and "Je réfléchis." in thinking
        and "Réponse du faux llama-server" in answer,
        "raisonnement : le couloir « Réflexion » contient « Je réfléchis. », la réponse suit",
        f"{thinking[:60]!r} · {answer[:60]!r}",
    )
    r.shot("54-llm-nu-chargement-raisonnement", full_page=True)
    toggle.uncheck()

    # (6) The workshop got nothing from the screen.
    r.goto_app()
    r.check(
        page.locator("#chat .bubble").count() == bubbles,
        "atelier : la Vue humain n'a rien reçu de l'écran",
        f"{bubbles} → {page.locator('#chat .bubble').count()}",
    )

    # (7) Back to the fake cloud A: no memory on this workstation.
    _pick_model(r, A_LABEL)
    _goto_lab(r)
    memory = page.inner_text("#loading-memory")
    r.check(
        "aucune mémoire sur ce poste" in memory.lower()
        and not page.locator("#loading-local").is_visible(),
        "chargement du cloud A : « aucune mémoire sur ce poste »",
        memory,
    )
    r.goto_app()


_LAB_SAMPLING = {"temperature": 0.2, "top_k": 5, "top_p": 0.9, "min_p": 0.05}


def _candidates_unavailable(r: Run, name: str, where: str) -> None:
    """Increment 4: « Montrer les tokens candidats » greyed, its reason naming `name`; a
    direct call asking for them answers 409."""
    box = r.page.locator("#candidates-toggle")
    reason = r.page.inner_text("#candidates-reason")
    refused = r.api(
        "POST",
        "/api/intentions/llm_generate",
        {"prompt": "Bonjour", "sampling": _LAB_SAMPLING, "candidates": True},
    )
    r.check(
        box.is_disabled() and name in reason and refused.status_code == 409,
        f"{where} : « Montrer les tokens candidats » grisé avec sa raison, appel direct 409",
        f"{reason} · {refused.status_code}",
    )


def _distribution_unavailable(r: Run, name: str, where: str) -> None:
    """Story 5 (2026-09-30): no model in process, no live distribution in the OUTPUT: the
    candidates' reason (naming `name`); a direct read answers 404. Correction C of
    2026-10-05: the example's bars meanwhile, badge « Exemple »."""
    page = r.page
    expect(page.locator("#distribution-note")).to_contain_text(name, timeout=5000)
    expect(page.locator("#output-tag")).to_have_class(re.compile("is-example"), timeout=5000)
    read = r.api("POST", "/api/llm_lab/distribution", {"index": 0, "sampling": _LAB_SAMPLING})
    r.check(
        page.locator("#distribution-body").is_visible()
        and page.locator("#distribution-bars .dist-row:not(.is-tail)").count() == 6
        and page.inner_text("#distribution-note").startswith("Exemple d'illustration")
        and read.status_code == 404,
        f"{where} : distribution réelle indisponible, sa raison dite, l'exemple à la place,"
        " lecture 404",
        f"{page.inner_text('#distribution-note')} · {read.status_code}",
    )


def _lab_questions_and_window(r: Run) -> None:
    """Story 5 (2026-09-30): each section lists its questions; after a generation, section 4
    draws the window from `llm_generation_started` (its figures, as received)."""
    page = r.page
    counts = page.locator(".llm-questions-list").evaluate_all(
        "ls => ls.map(l => l.querySelectorAll('li').length)"
    )
    r.check(
        len(counts) == 6 and all(counts),
        "chaque section liste « Les questions que vous vous posez »",
        str(counts),
    )
    started = r.ev.since(0, "llm_generation_started")[-1]["payload"]
    usable = page.inner_text("#window-usable-label")
    caption = _plain(page.inner_text("#window-caption"))
    r.check(
        page.locator("#window-diagram").is_visible()
        and usable.startswith("Prompt")
        and _plain(started["figures_text"]["window"]) in caption
        and _plain(started["figures_text"]["reserve"]) in caption,
        "section 4 : schéma de la fenêtre (prompt, réserve) tiré de llm_generation_started",
        f"{usable} · {caption[:160]}",
    )


def _lab_compare(r: Run) -> None:
    """Story 5 (2026-09-30), on the fake llama-server: « Comparer » with two temperatures,
    `llm{n}.a` then `llm{n}.b`, one after the other; the workshop refused meanwhile; both
    columns filled, side by side."""
    page = r.page
    page.fill("#llm-prompt", "Explique " + "très longuement " * 14)
    field = page.locator("#compare-temperature")
    field.fill("1.2")
    field.dispatch_event("change")
    expect(page.locator("#compare-button")).to_be_enabled(timeout=10_000)
    seq = r.ev.mark()
    page.click("#compare-button")
    first = r.ev.wait("llm_generation_started", seq, lambda p: p["request_id"].endswith(".a"), 20)
    refused = r.api("POST", "/api/intentions/send", {"message": "Pendant la comparaison"})
    expect(page.locator("#generate-button")).to_be_disabled(timeout=5000)
    last = r.ev.wait("llm_generation_ended", seq, lambda p: p["request_id"].endswith(".b"), 60)
    expect(page.locator("#compare-button")).to_be_enabled(timeout=10_000)
    rid = first["payload"]["request_id"][: -len(".a")]
    started = [e for e in r.ev.since(seq, "llm_generation_started") if e["context_id"] == "llm"]
    ended = [e for e in r.ev.since(seq, "llm_generation_ended") if e["context_id"] == "llm"]
    ids = [e["payload"]["request_id"] for e in started]
    r.check(
        ids == [f"{rid}.a", f"{rid}.b"]
        and [e["payload"]["request_id"] for e in ended] == ids
        and ended[0]["seq"] < started[1]["seq"]
        and started[0]["payload"]["sampling"]["temperature"] == _LAB_SAMPLING["temperature"]
        and started[1]["payload"]["sampling"]["temperature"] == 1.2
        and last["payload"]["status"] == "completed",
        "comparaison : llm{n}.a puis llm{n}.b, l'un après l'autre, deux températures",
        f"{ids} · {[e['payload']['status'] for e in ended]}",
    )
    r.check(
        refused.status_code == 409,
        "comparaison en cours : l'atelier refuse un envoi (409)",
        f"{refused.status_code} {refused.text[:120]}",
    )
    lanes = page.locator("#compare-lanes")
    a_text = page.inner_text("#compare-a .compare-lane-text")
    b_text = page.inner_text("#compare-b .compare-lane-text")
    boxes = [page.locator(f"#compare-{x}").bounding_box() for x in ("a", "b")]
    side = all(boxes) and abs(boxes[0]["y"] - boxes[1]["y"]) < 4 and boxes[0]["x"] < boxes[1]["x"]
    r.check(
        lanes.is_visible()
        and a_text.strip()
        and b_text.strip()
        and side
        and "T 1,2" in page.inner_text("#compare-b .compare-lane-sampling"),
        "comparaison : deux colonnes côte à côte, remplies, réglages résumés en tête",
        f"{a_text[:40]!r} · {b_text[:40]!r} · {boxes}",
    )
    r.shot("64-llm-nu-comparaison", full_page=True)


def _lab_compare_stopped(r: Run) -> None:
    """Restes du 2026-10-01 (story 5, IA3): a comparison on the fake cloud A, slow
    (« [lent] »): two requests to the provider, temperature A then B; « Arrêter » of the page
    pressed while B runs: A completed, B cancelled and its column says so, the session back
    to idle, the buttons enabled again."""
    page = r.page
    page.fill("#llm-prompt", "Bonjour [lent]")
    field = page.locator("#compare-temperature")
    field.fill("1.2")
    field.dispatch_event("change")
    expect(page.locator("#compare-button")).to_be_enabled(timeout=10_000)
    calls = len(r.fake_calls())
    seq = r.ev.mark()
    page.click("#compare-button")
    first = r.ev.wait("llm_generation_started", seq, lambda p: p["request_id"].endswith(".a"), 20)
    rid = first["payload"]["request_id"][: -len(".a")]
    r.ev.wait("llm_token", seq, lambda p: p["request_id"] == f"{rid}.b", 30)
    stop = page.locator("#stop-button")
    expect(stop).to_be_enabled(timeout=5000)
    stop.click()
    last = r.ev.wait("llm_generation_ended", seq, lambda p: p["request_id"] == f"{rid}.b", 30)
    ended = {
        e["payload"]["request_id"]: e["payload"]["status"]
        for e in r.ev.since(seq, "llm_generation_ended")
        if e["context_id"] == "llm"
    }
    bodies = r.fake_calls()[calls:]
    r.check(
        ended == {f"{rid}.a": "completed", f"{rid}.b": "cancelled"}
        and [b.get("temperature") for b in bodies] == [_LAB_SAMPLING["temperature"], 1.2]
        and all(
            b.get("messages") == [{"role": "user", "content": "Bonjour [lent]"}] for b in bodies
        ),
        "comparaison cloud : deux requêtes au fournisseur, température A puis B ; « Arrêter » "
        "pressé pendant B : A terminée, B arrêtée",
        f"{ended} · {[b.get('temperature') for b in bodies]} · {last['payload']['status']}",
    )
    expect(page.locator("#compare-button")).to_be_enabled(timeout=10_000)
    b_status = page.inner_text("#compare-b .compare-lane-status")
    a_status = page.inner_text("#compare-a .compare-lane-status")
    r.check(
        "Génération arrêtée." in b_status
        and "Réponse terminée." in a_status
        and page.locator("#generate-button").is_enabled()
        and page.locator("#stop-button").is_disabled()
        and r.state()["session_state"]["state"] == "idle",
        "comparaison arrêtée : la colonne B le dit, « Générer » et « Comparer » de nouveau "
        "actifs, « Arrêter » grisé, session en idle",
        f"A « {a_status} » · B « {b_status} »",
    )


def _set_lab_sampling(r: Run) -> None:
    """The four settings of the screen, typed in their number fields (the disabled ones
    left as they are)."""
    for name, value in _LAB_SAMPLING.items():
        field = r.page.locator(f"#sampling-{name}")
        if field.is_enabled():
            field.fill(str(value))
            field.dispatch_event("change")


def _lab_generate(r: Run, prompt: str, watch: bool = False) -> dict[str, Any]:
    """« Générer » on the screen; `watch`: the chips counted while they come, and checked
    to grow."""
    page = r.page
    page.fill("#llm-prompt", prompt)
    expect(page.locator("#generate-button")).to_be_enabled(timeout=10_000)
    seq = r.ev.mark()
    page.click("#generate-button")
    counts: list[int] = []
    if watch:
        r.ev.wait("llm_token", seq, timeout=20)
        deadline = time.monotonic() + 20
        while time.monotonic() < deadline and not r.ev.since(seq, "llm_generation_ended"):
            counts.append(page.locator("#generation-tokens .token-chip").count())
            time.sleep(0.1)
    ended = r.ev.wait("llm_generation_ended", seq, timeout=30)
    expect(page.locator("#generate-button")).to_be_enabled(timeout=10_000)
    if watch:
        grows = len({c for c in counts if c}) >= 2 and counts == sorted(counts)
        r.check(grows, "les puces apparaissent une à une", str(counts[:12]) + "…")
    return ended


# ---------- restes du 2026-10-01: the live distribution and the window, page side ----------

# The tokens of a generation that never ran: their most probable candidates (text, p at
# temperature 1) and the rest of the vocabulary's mass, as the session keeps them.
_LIVE_TOKENS = [
    {
        "text": "Bon",
        "top": [("Bon", 0.50), ("Salut", 0.25), ("Hello", 0.12), ("Coucou", 0.06), ("Hé", 0.03)],
        "tail": 0.04,
    },
    {
        "text": "jour",
        "top": [("jour", 0.70), ("soir", 0.20), ("ne", 0.05), ("heur", 0.02)],
        "tail": 0.03,
    },
    {
        "text": " !",
        "top": [(" !", 0.40), (".", 0.35), (",", 0.15), (" à", 0.05)],
        "tail": 0.05,
    },
]
_LIVE_WINDOW = {"usable": 1000, "prompt_tokens": 250, "reserve": 500}
_LIVE_ID = "llm900"
_LIVE_SAMPLING = {"temperature": 1.0, "top_k": 0, "top_p": 1.0, "min_p": 0.0}


def _live_rows(index: int, sampling: dict[str, float]) -> list[dict[str, Any]]:
    """`candidates.distribution` of token `index`: what the session would answer."""
    token = _LIVE_TOKENS[index]
    values = [p for _, p in token["top"]]
    return live_distribution(values, token["tail"], Sampling(**sampling))


class _LiveLab:
    """`page.route` handlers that stand in for an engine in process: `/api/llm_lab` (the real
    answer, the candidates available, every setting adjustable), `/api/llm_lab/distribution`
    (computed by the session's own `candidates.distribution`, in the shape of
    `AppSession.llm_distribution`) and `/api/stream` (batches of envelopes, each served once
    the test released it, an empty stream otherwise: the page reads it again a second
    later). Every envelope is validated by the journal's `Envelope` before it is sent."""

    def __init__(self) -> None:
        self.next_seq = 0  # from the journal's real `seq` + 1000: the page takes them as new
        self.batches: list[str] = []
        self.released = 0
        self.served = 0
        self.kept = 0  # the tokens whose candidates « the session » keeps
        self.requests: list[dict[str, Any]] = []

    def lab(self, route) -> None:  # noqa: ANN001
        response = route.fetch()
        body = response.json()
        self.next_seq = self.next_seq or body["seq"] + 1000
        body["candidates"] = {**body["candidates"], "available": True, "reason_text": None}
        body["sampling"]["supported"] = dict.fromkeys(body["sampling"]["supported"])
        body["distribution"] = {"tokens": self.kept}
        route.fulfill(response=response, json=body)

    def distribution(self, route) -> None:  # noqa: ANN001
        asked = route.request.post_data_json
        self.requests.append(asked)
        index = asked.get("index", 0)
        if index >= self.kept:
            route.fulfill(status=404, json={"detail": "Générez d'abord un texte (e2e)."})
            return
        token = _LIVE_TOKENS[index]
        rows = _live_rows(index, asked["sampling"])
        route.fulfill(
            json={
                "index": index,
                "token_text": token["text"],
                "candidates": [
                    {"text": text} | row for (text, _), row in zip(token["top"], rows, strict=True)
                ],
                "tail": token["tail"],
                "sampling": asked["sampling"],
                "kept_count": sum(1 for row in rows if row["kept"]),
                "tokens": self.kept,
            }
        )

    def stream(self, route) -> None:  # noqa: ANN001
        body = ""
        if self.served < self.released:
            body = self.batches[self.served]
            self.served += 1
        route.fulfill(status=200, headers={"content-type": "text/event-stream"}, body=body)

    def add_batch(self, *events: tuple[str, dict[str, Any]]) -> None:
        lines = []
        for kind, payload in events:
            self.next_seq += 1
            envelope = Envelope(
                seq=self.next_seq,
                ts=time.strftime("%Y-%m-%dT%H:%M:%S+00:00", time.gmtime()),
                session_epoch=0,
                context_id="llm",
                step_id=_LIVE_ID,
                kind=kind,
                actor="model" if kind == "llm_token" else "harness",
                trigger="user",
                payload=payload,
            )
            data = envelope.model_dump_json()
            lines.append(f"id: {self.next_seq}\nevent: {kind}\ndata: {data}\n\n")
        self.batches.append("".join(lines))

    def release(self) -> None:
        self.released += 1


def _live_token(index: int) -> dict[str, Any]:
    token = _LIVE_TOKENS[index]
    rows = _live_rows(index, _LIVE_SAMPLING)
    return {
        "request_id": _LIVE_ID,
        "index": index,
        "token_id": 1000 + index,
        "text": token["text"],
        "channel": "text",
        "elapsed_ms": 10 * (index + 1),
        "candidates": [
            {"token_id": 2000 + i, "text": text, "chosen": i == 0} | row
            for i, ((text, _), row) in enumerate(zip(token["top"], rows, strict=True))
        ],
        "parts": [{"channel": "text", "text": token["text"]}],
    }


def s_llm_live(r: Run) -> None:
    """Restes du 2026-10-01 (story 5, IA1, IA5, VG5, BH11): the page's live distribution and
    window diagram, without an engine in process (`_LiveLab`): bars redrawn at each move of
    a slider (`p` fixed, the chance moving, the dropped greyed), a chip that picks the token,
    the prompt's share filled in proportion, the reserve's growing token after token. On the
    fake cloud A, whose `/api/llm_lab` is rewritten; back to `/` at the end."""
    page = r.page
    page.set_viewport_size({"width": 1600, "height": 1000})
    r.goto_app()
    r.wait_idle()
    if (r.state().get("active_model") or {}).get("ref") != MODEL_ENTRY_ID:
        _pick_model(r, A_LABEL)
    live = _LiveLab()
    routes = [
        ("**/api/llm_lab", live.lab),
        ("**/api/llm_lab/distribution", live.distribution),
        ("**/api/stream", live.stream),
    ]
    errors: list[str] = []
    listener = lambda e: errors.append(str(e))  # noqa: E731
    page.on("pageerror", listener)
    for pattern, handler in routes:
        page.route(pattern, handler)
    try:
        _llm_live(r, live, errors)
    finally:
        for pattern, _ in routes:
            page.unroute(pattern)
        page.remove_listener("pageerror", listener)
        r.goto_app()


_DIST_ROWS_JS = """rows => rows.map(row => {
  const value = (kind) => row.querySelector(`.dist-cell.${kind} .dist-value`).textContent;
  const width = (kind) =>
    parseFloat(row.querySelector(`.dist-cell.${kind} .dist-bar span`).style.width);
  return {
    text: row.querySelector('.dist-text').textContent,
    dropped: row.classList.contains('is-dropped'),
    model: value('is-model'),
    chance: value('is-chance'),
    modelWidth: width('is-model'),
    chanceWidth: width('is-chance'),
  };
})"""


def _dist_rows(r: Run) -> list[dict[str, Any]]:
    """The bars of section 2, as drawn: text, greyed, the two values and their widths."""
    rows = r.page.locator("#distribution-bars .dist-row:not(.is-tail)")
    return rows.evaluate_all(_DIST_ROWS_JS)


def _rows_match(r: Run, index: int, sampling: dict[str, float]) -> tuple[bool, str]:
    """Whether section 2 draws token `index` for `sampling` (polled: the page waits 80 ms
    before it asks, then draws the answer)."""
    want = [
        (not row["kept"], row["p"] * 100, row["p_sampled"] * 100)
        for row in _live_rows(index, sampling)
    ]

    def same() -> bool:
        got = _dist_rows(r)
        return len(got) == len(want) and all(
            g["dropped"] == dropped
            and abs(g["modelWidth"] - model) < 0.01
            and abs(g["chanceWidth"] - chance) < 0.01
            for g, (dropped, model, chance) in zip(got, want, strict=True)
        )

    ok, _ = r.poll(same, 10)
    got = _dist_rows(r)
    return ok, str([(g["text"], g["dropped"], g["model"], g["chance"]) for g in got])


def _set_live(r: Run, name: str, value: float, *, slider: bool = False) -> None:
    """A setting of section 2, by its number field or by its slider (`fill` on a range
    input sets its value and fires `input` then `change`, as a drag does)."""
    row = r.page.locator(f'#sampling-controls .sampling-row[data-setting="{name}"]')
    if slider:
        row.locator('input[type="range"]').fill(str(value))
    else:
        field = row.locator('input[type="number"]')
        field.fill(str(value))
        field.dispatch_event("change")


_WINDOW_SHARES_JS = """() => {
  const width = (node) => node.getBoundingClientRect().width;
  const figure = document.getElementById('window-diagram');
  const [usable, reserve] = figure.querySelectorAll('.window-part');
  return {
    prompt: width(figure.querySelector('.window-fill.is-prompt')) / width(usable),
    output: width(figure.querySelector('.window-fill.is-output')) / width(reserve),
  };
}"""


def _window_shares(r: Run) -> dict[str, float]:
    """The window diagram's fills, as a share of their part (layout boxes, sub-pixel)."""
    return r.page.evaluate(_WINDOW_SHARES_JS)


def _llm_live(r: Run, live: _LiveLab, errors: list[str]) -> None:
    page = r.page
    _goto_lab(r)
    expect(page.locator("#candidates-toggle")).to_be_enabled(timeout=5000)
    for name, value in _LIVE_SAMPLING.items():
        _set_live(r, name, value)
    # Correction C of 2026-10-05: nothing kept, the session's example meanwhile, labelled.
    ok_example, example = _example_rows(r, _LIVE_SAMPLING)
    r.check(
        ok_example
        and page.locator("#distribution-body").is_visible()
        and "Générez une réponse" in page.inner_text("#distribution-note")
        and not live.requests,
        "distribution vivante : rien de gardé, l'exemple étiqueté et quoi faire, aucune lecture"
        " réelle demandée",
        f"{page.inner_text('#distribution-note')} · {len(live.requests)} requêtes · {example}",
    )

    # (1) The generation starts, its first token comes with its candidates.
    started = {
        "request_id": _LIVE_ID,
        "prompt": "Bonjour",
        "rendered": "<|im_start|>user\nBonjour<|im_end|>\n<|im_start|>assistant\n",
        "prompt_tokens": _LIVE_WINDOW["prompt_tokens"],
        "exact": True,
        "sampling": _LIVE_SAMPLING | {"source": "screen"},
        "reserve": _LIVE_WINDOW["reserve"],
        "usable": _LIVE_WINDOW["usable"],
        "phase_label": "Génération (e2e)",
        "unit": "token",
        "figures_text": {
            "prompt_tokens": "250",
            "reserve": "500",
            "window": "1 500",
            "usable": "1 000",
        },
    }
    live.add_batch(("llm_generation_started", started), ("llm_token", _live_token(0)))
    live.kept = 1
    live.release()
    expect(page.locator("#generation-tokens .token-chip")).to_have_count(1, timeout=10_000)
    ok, drawn = _rows_match(r, 0, _LIVE_SAMPLING)
    r.check(
        ok and page.locator("#distribution-body").is_visible(),
        "distribution vivante : les barres du premier token, largeurs = p et chance reçues",
        drawn,
    )
    shares = _window_shares(r)
    r.check(
        abs(shares["prompt"] - 0.25) < 0.005 and abs(shares["output"] - 1 / 500) < 0.0005,
        "schéma de la fenêtre : prompt à 250/1 000 de sa part, réponse à 1/500 de la réserve",
        str(shares),
    )

    # (2) The top-k slider: the bars redrawn, the model's probability fixed.
    before = _dist_rows(r)
    _set_live(r, "top_k", 2, slider=True)
    ok, drawn = _rows_match(r, 0, _LIVE_SAMPLING | {"top_k": 2})
    after = _dist_rows(r)
    r.check(
        ok
        and sum(row["dropped"] for row in after) == 3
        and [row["model"] for row in after] == [row["model"] for row in before]
        and live.requests[-1]["sampling"]["top_k"] == 2,
        "curseur top-k à 2 : deux candidats gardés, trois grisés « écarté », probabilité du "
        "modèle inchangée",
        drawn,
    )
    # Three quick moves: the bars of the last one (the page waits, then draws the last answer).
    for value in (4, 1, 3):
        _set_live(r, "top_k", value, slider=True)
    ok, drawn = _rows_match(r, 0, _LIVE_SAMPLING | {"top_k": 3})
    r.check(
        ok and live.requests[-1]["sampling"]["top_k"] == 3,
        "trois mouvements rapides du curseur : les barres du dernier réglage (top-k 3)",
        f"{drawn} · {len(live.requests)} requêtes",
    )

    # (3) The temperature: the chance moves, the model's probability does not.
    before = _dist_rows(r)
    _set_live(r, "temperature", 0.3)
    hot = _LIVE_SAMPLING | {"top_k": 3, "temperature": 0.3}
    ok, drawn = _rows_match(r, 0, hot)
    after = _dist_rows(r)
    r.check(
        ok
        and [row["model"] for row in after] == [row["model"] for row in before]
        and after[0]["chanceWidth"] > before[0]["chanceWidth"],
        "température 1 → 0,3 : la chance du premier candidat monte, la probabilité du modèle "
        "ne bouge pas",
        drawn,
    )
    r.shot("65-llm-nu-distribution-vivante", full_page=True)

    # (4) Two more tokens: the reserve's share grows; the chip clicked is section 2's token.
    output_before = shares["output"]
    live.add_batch(("llm_token", _live_token(1)), ("llm_token", _live_token(2)))
    live.kept = 3
    live.release()
    expect(page.locator("#generation-tokens .token-chip")).to_have_count(3, timeout=10_000)
    shares = _window_shares(r)
    label = _plain(page.inner_text("#window-reserve-label"))
    r.check(
        abs(shares["output"] - 3 / 500) < 0.0005
        and shares["output"] > output_before
        and "Réponse : 3 tokens" in label,
        "schéma de la fenêtre : la part de la réponse croît, 3/500 de la réserve",
        f"{shares} · {label}",
    )
    chip = page.locator('#generation-tokens .token-chip[data-index="2"]')
    chip.click()
    ok, drawn = _rows_match(r, 2, hot)
    header = _plain(page.inner_text("#distribution-token"))
    r.check(
        ok
        and live.requests[-1]["index"] == 2
        and header.startswith("Token 3 de la dernière génération")
        and "is-dist-chosen" in (chip.get_attribute("class") or "")
        and page.locator("#generation-tokens .token-chip.is-dist-chosen").count() == 1,
        "clic sur la puce n° 3 : la section 2 montre ses candidats, la puce est marquée",
        f"{header} · {drawn}",
    )
    page.keyboard.press("Escape")  # the candidates' popover the click pinned
    r.check(not errors, "/llm, distribution simulée : aucune erreur JavaScript", str(errors)[:300])


# ---------- lot 6 (2026-10-04): the model's loop in three stages, page side ----------

# A tokenization of « Le chat dort sur le » by a hybrid model (Qwen3.5's header, simulated),
# then the tokens the engine « draws »: their most probable candidates and the rest's mass.
_LOOP_TEXT = "Le chat dort sur le"
_LOOP_TOKENS = [(2304, "Le"), (9558, " chat"), (87461, " dort"), (1847, " sur"), (512, " le")]
_LOOP_HEADER = {
    "general.architecture": "qwen35",
    "qwen35.block_count": 24,
    "qwen35.embedding_length": 2048,
    "qwen35.feed_forward_length": 6144,
    "qwen35.attention.head_count": 8,
    "qwen35.attention.head_count_kv": 2,
    "qwen35.full_attention_interval": 4,
    "qwen35.ssm.state_size": 128,
}
_LOOP_DIMS = {
    "vocab_size": 248320,
    "embedding_length": 2048,
    "layer_count": 24,
    "head_count": 8,
    "context_length": 262144,
}
_LOOP_DRAWS = [
    {
        "id": 107233,
        "text": " canapé",
        "top": [
            (" canapé", 0.38),
            (" lit", 0.22),
            (" tapis", 0.12),
            (" toit", 0.07),
            (" rebord", 0.05),
            (" sol", 0.04),
            (" fauteuil", 0.02),
        ],
        "tail": 0.10,
    },
    {
        "id": 13,
        "text": ".",
        "top": [(".", 0.41), (" du", 0.19), (" en", 0.14), (",", 0.09), (" rouge", 0.04)],
        "tail": 0.13,
    },
]
_LOOP_SAMPLING = {"temperature": 0.7, "top_k": 0, "top_p": 1.0, "min_p": 0.0}
_LOOP_VIEWPORTS = [(1600, 1000), (1366, 768)]


def _loop_tokenized(header: dict[str, Any] | None = None) -> dict[str, Any]:
    """`llm_tokenized` as the session would write it for the hybrid model (its own functions:
    the figures and the architecture's family are the session's, not the test's)."""
    architecture = llm_lab.architecture_from_header(header or _LOOP_HEADER)
    dimensions = llm_lab.dimensions_payload(
        _LOOP_DIMS, "Lues dans le moteur (e2e).", architecture=architecture
    )
    return {
        "request_id": _LIVE_ID,
        "text": _LOOP_TEXT,
        "char_count": len(_LOOP_TEXT),
        "model_label": "Qwen3.5-2B (e2e)",
        "hosting": "local",
        "exact": True,
        "tokenizer_text": "Découpage exact (e2e).",
        "tokens": [{"id": i, "text": t, "special": False} for i, t in _LOOP_TOKENS],
        "token_count": len(_LOOP_TOKENS),
        "more": 0,
        "dimensions": dimensions,
        "dimensions_text": llm_lab.dimensions_fr(dimensions),
        "figures_text": {"char_count": str(len(_LOOP_TEXT)), "token_count": "5", "more": "0"},
    }


class _LoopLab(_LiveLab):
    """`_LiveLab`, with an engine in process that draws one token per step: `llm_tokenize` and
    `llm_step` answered by the test (their events in the batches the test releases), and
    `/api/llm_lab/distribution` the candidates of the last token drawn (the session's own
    `candidates.distribution` and `dropped_by`)."""

    def __init__(self, exact: bool = False) -> None:
        super().__init__()
        self.steps: list[dict[str, Any]] = []
        self.tokenizes: list[dict[str, Any]] = []
        self.draw = _LOOP_DRAWS[0]
        # Correction C of 2026-10-05: the in-process engine's exact tokenizer too, which
        # makes the page cut its text and draw a step by itself on its first load; `busy`:
        # the session in a workshop turn; `refuse_step`: `llm_step` answers 409.
        self.exact = exact
        self.busy = False
        self.refuse_step = False

    def lab(self, route) -> None:  # noqa: ANN001
        if not self.exact:
            super().lab(route)
            return
        response = route.fetch()
        body = response.json()
        self.next_seq = self.next_seq or body["seq"] + 1000
        body["candidates"] = {**body["candidates"], "available": True, "reason_text": None}
        body["sampling"]["supported"] = dict.fromkeys(body["sampling"]["supported"])
        body["distribution"] = {"tokens": self.kept}
        body["tokenizer"] = {"exact": True, "reason_text": "Découpage exact (e2e)."}
        if self.busy:
            body["session_state"] = {"state": "turn", "reason_text": "Un tour est en cours (e2e)."}
        route.fulfill(response=response, json=body)

    def tokenize(self, route) -> None:  # noqa: ANN001
        self.tokenizes.append(route.request.post_data_json)
        route.fulfill(json={"request_id": _LIVE_ID})

    def step(self, route) -> None:  # noqa: ANN001
        self.steps.append(route.request.post_data_json)
        if self.refuse_step:
            route.fulfill(status=409, json={"detail": "Pas refusé (e2e)."})
            return
        route.fulfill(json={"request_id": self.step_id})

    @property
    def step_id(self) -> str:
        return f"llm{900 + len(self.steps)}.step"

    def distribution(self, route) -> None:  # noqa: ANN001
        asked = route.request.post_data_json
        self.requests.append(asked)
        if not self.kept or asked.get("index", 0) != 0:
            route.fulfill(status=404, json={"detail": "Rien de gardé (e2e)."})
            return
        values = [p for _, p in self.draw["top"]]
        sampling = Sampling(**asked["sampling"])
        rows = live_distribution(values, self.draw["tail"], sampling)
        route.fulfill(
            json={
                "index": 0,
                "token_text": self.draw["text"],
                "candidates": [
                    {"text": text} | row
                    for (text, _), row in zip(self.draw["top"], rows, strict=True)
                ],
                "tail": self.draw["tail"],
                "sampling": asked["sampling"],
                "kept_count": sum(1 for row in rows if row["kept"]),
                "tokens": 1,
                "dropped_by": live_dropped_by(values, self.draw["tail"], sampling),
            }
        )

    def drawn(self, draw: dict[str, Any]) -> None:
        """The step's three events: started, its one token (with its candidates), ended."""
        rid = self.step_id
        rows = live_distribution(
            [p for _, p in draw["top"]], draw["tail"], Sampling(**_LOOP_SAMPLING)
        )
        started = {
            "request_id": rid,
            "prompt": _LOOP_TEXT,
            "rendered": _LOOP_TEXT,  # the INPUT's text, no chat template
            "prompt_tokens": 5,
            "exact": True,
            "sampling": _LOOP_SAMPLING | {"source": "screen"},
            "reserve": 512,
            "usable": 3584,
            "phase_label": "Lecture (e2e)",
            "unit": "token",
            "figures_text": {"prompt_tokens": "5", "reserve": "512", "window": "4 096"},
        }
        token = {
            "request_id": rid,
            "index": 0,
            "token_id": draw["id"],
            "text": draw["text"],
            "channel": "text",
            "elapsed_ms": 12,
            "candidates": [
                {"token_id": 3000 + i, "text": text, "chosen": i == 0} | row
                for i, ((text, _), row) in enumerate(zip(draw["top"][:5], rows, strict=False))
            ],
            "parts": [{"channel": "text", "text": draw["text"]}],
        }
        ended = {
            "request_id": rid,
            "status": "limit",
            "duration_ms": 15,
            "answer_tokens": 1,
            "figures_text": {"reasoning_tokens": "0", "answer_tokens": "1"},
        }
        self.draw = draw
        self.kept = 1
        self.add_batch(
            ("llm_generation_started", started),
            ("llm_token", token),
            ("llm_generation_ended", ended),
        )
        self.release()


def s_llm_loop(r: Run) -> None:
    """Lot 6 of 2026-10-04: /llm's first three stages, without an engine in process
    (`_LoopLab`): the INPUT step by step (text, tokens, ids, in aligned columns), the
    TRANSFORMATION's 7 steps and its banner on a simulated hybrid header, the OUTPUT (a
    setting's help, a simulated step drawn, the chances following a setting, « Ajouter à la
    suite » then « Retirer le dernier »); each stage within the screen at 1600 × 1000 and
    1366 × 768; no JavaScript error. On the fake cloud A, whose `/api/llm_lab` is rewritten;
    back to `/` at the end."""
    page = r.page
    page.set_viewport_size({"width": 1600, "height": 1000})
    r.goto_app()
    r.wait_idle()
    if (r.state().get("active_model") or {}).get("ref") != MODEL_ENTRY_ID:
        _pick_model(r, A_LABEL)
    live = _LoopLab()
    routes = [
        ("**/api/llm_lab", live.lab),
        ("**/api/llm_lab/distribution", live.distribution),
        ("**/api/stream", live.stream),
        ("**/api/intentions/llm_tokenize", live.tokenize),
        ("**/api/intentions/llm_step", live.step),
    ]
    errors: list[str] = []
    listener = lambda e: errors.append(str(e))  # noqa: E731
    page.on("pageerror", listener)
    for pattern, handler in routes:
        page.route(pattern, handler)
    try:
        _llm_loop(r, live)
    finally:
        for pattern, _ in routes:
            page.unroute(pattern)
        page.remove_listener("pageerror", listener)
        page.set_viewport_size({"width": 1600, "height": 1000})
        r.goto_app()
    r.check(not errors, "/llm, boucle simulée : aucune erreur JavaScript", str(errors)[:300])
    _llm_loop_first_load(r)
    _llm_loop_cloud(r)


def _llm_loop_first_load(r: Run) -> None:
    """Correction C of 2026-10-05: an engine in process at rest (`_LoopLab(exact=True)`),
    the page opened: with no click, it asks the session to cut the field's text, then to
    draw one step; real columns and real bars, badges « Réel », the OUTPUT left on its first
    step; the INPUT's cut still shown step by step."""
    page = r.page
    page.evaluate("t => localStorage.setItem('wavestack.llm.prompt', t)", _LOOP_TEXT)
    live = _LoopLab(exact=True)
    routes = [
        ("**/api/llm_lab", live.lab),
        ("**/api/llm_lab/distribution", live.distribution),
        ("**/api/stream", live.stream),
        ("**/api/intentions/llm_tokenize", live.tokenize),
        ("**/api/intentions/llm_step", live.step),
    ]
    errors: list[str] = []
    listener = lambda e: errors.append(str(e))  # noqa: E731
    page.on("pageerror", listener)
    for pattern, handler in routes:
        page.route(pattern, handler)
    try:
        for name, value in _LOOP_SAMPLING.items():  # the step's settings, saved by the page
            page.evaluate(
                "([k, v]) => { const s = JSON.parse(localStorage.getItem("
                "'wavestack.llm.sampling') || '{}'); s[k] = v; "
                "localStorage.setItem('wavestack.llm.sampling', JSON.stringify(s)); }",
                [name, value],
            )
        _goto_lab(r)

        def pumped(condition: Callable[[], bool]) -> Callable[[], bool]:
            # The routes' handlers run only while Playwright works: wait in the page.
            return lambda: page.wait_for_timeout(50) is None and condition()

        asked, _ = r.poll(pumped(lambda: len(live.tokenizes) == 1), 10)
        live.add_batch(("llm_tokenized", _loop_tokenized()))
        live.release()
        stepped, _ = r.poll(pumped(lambda: len(live.steps) == 1), 10)
        if stepped:
            live.drawn(_LOOP_DRAWS[0])
        chip = page.locator("#llm-step-drawn .llm-output-chip")
        shown, _ = r.poll(lambda: chip.count() == 1 and chip.inner_text() == "␣canapé", 10)
        r.check(
            asked and stepped and shown,
            "1er chargement : la page demande le découpage, puis le pas, sans clic",
            f"{len(live.tokenizes)} découpage(s), {len(live.steps)} pas, puce {shown}"
            f" · statut {page.inner_text('#llm-step-status')!r}"
            f" · {page.inner_text('#tokenize-status')!r} · {page.inner_text('#llm-busy')!r}",
        )
        ok, drawn = _llm_loop_rows(r, _LOOP_SAMPLING)
        first = page.evaluate(_INPUT_JS)
        logits = page.locator("#logits-bars .dist-row:not(.is-tail) .dist-text").all_inner_texts()
        tags = [page.locator(t) for t in ("#input-tag", "#output-tag")]
        r.check(
            asked
            and stepped
            and live.tokenizes[0].get("text") == _LOOP_TEXT
            and live.steps[0]["prompt"] == _LOOP_TEXT
            and live.steps[0]["continuation"] == []
            and first["chips"] == ["Le", "␣chat", "␣dort", "␣sur", "␣le"]
            and page.locator("#token-chips .token-chip.is-example").count() == 0
            and page.locator("#token-example").is_hidden()
            and ok
            and logits == ["␣canapé", "␣lit", "␣tapis", "␣toit", "␣rebord", "␣sol"]
            and all(t.inner_text().startswith("RÉEL") for t in tags)
            and not any("is-example" in (t.get_attribute("class") or "") for t in tags),
            "1er chargement, moteur en processus : découpage et premier pas sans clic, colonnes"
            " et barres réelles, badges « Réel »",
            f"{len(live.tokenizes)} découpage(s), {len(live.steps)} pas · {logits} · {drawn}",
        )
        stepper = page.locator("#input-stepper")
        r.check(
            not first["cut"]
            and page.inner_text("#output-caption").startswith("Logits.")
            and page.locator("#output-stepper .diagram-step-position").inner_text()
            == "Étape 1 / 3",
            "1er chargement : l'INPUT s'ouvre sur le texte d'un bloc, l'OUTPUT sur les Logits",
            page.inner_text("#output-caption")[:80],
        )
        stepper.locator(".diagram-step-next").click()
        second = page.evaluate(_INPUT_JS)
        r.check(
            second["cut"] and second["tokens"] and not second["ids"],
            "1er chargement : ▶ découpe le texte réel en tokens, pas à pas",
        )
        r.shot_element("75-llm-boucle-premier-chargement", "#stage-output")

        # The page opened again while the session keeps a distribution (the step's): nothing
        # asked by itself, the real bars kept.
        cuts, steps = len(live.tokenizes), len(live.steps)
        _goto_lab(r)
        kept, _ = r.poll(pumped(lambda: page.inner_text("#output-tag").startswith("RÉEL")), 10)
        page.wait_for_timeout(1500)
        r.check(
            kept
            and len(live.tokenizes) == cuts
            and len(live.steps) == steps
            and page.locator("#token-chips .token-chip.is-example").count() == 5,
            "rechargement, distribution gardée : rien de demandé sans clic, barres réelles"
            " gardées, l'INPUT sur l'exemple",
            f"{len(live.tokenizes) - cuts} découpage(s), {len(live.steps) - steps} pas",
        )

        # The session busy (a workshop turn): nothing asked by itself, the example shown.
        live.kept, live.busy = 0, True
        cuts = len(live.tokenizes)
        _goto_lab(r)
        page.wait_for_timeout(1500)
        r.check(
            len(live.tokenizes) == cuts
            and page.locator("#token-chips .token-chip.is-example").count() == 5
            and page.inner_text("#output-tag").startswith("EXEMPLE"),
            "1er chargement, session occupée : rien de demandé sans clic, l'exemple montré",
            f"{len(live.tokenizes) - cuts} découpage(s)",
        )

        # The automatic step refused (409): the usual error, the example stays; the next step,
        # asked by a click, is a manual one (the OUTPUT moves to its token).
        live.busy, live.refuse_step = False, True
        cuts, steps = len(live.tokenizes), len(live.steps)
        _goto_lab(r)
        r.poll(pumped(lambda: len(live.tokenizes) == cuts + 1), 10)
        live.add_batch(("llm_tokenized", _loop_tokenized()))
        live.release()
        refused, _ = r.poll(pumped(lambda: len(live.steps) == steps + 1), 10)
        status = page.locator("#llm-step-status")
        expect(status).to_have_text("Pas refusé (e2e).", timeout=10_000)
        r.check(
            refused
            and "is-error" in (status.get_attribute("class") or "")
            and page.inner_text("#output-tag").startswith("EXEMPLE"),
            "1er chargement, pas automatique refusé : l'erreur habituelle, l'exemple reste",
            status.inner_text(),
        )
        live.refuse_step = False
        page.click("#llm-step-button")
        stepped, _ = r.poll(pumped(lambda: len(live.steps) == steps + 2), 10)
        if stepped:
            live.drawn(_LOOP_DRAWS[0])
        expect(chip).to_have_text("␣canapé", timeout=10_000)
        position = page.locator("#output-stepper .diagram-step-position")
        r.check(
            stepped and position.inner_text() == "Étape 3 / 3",
            "après le refus, un pas demandé au clic mène l'OUTPUT à son token tiré",
            position.inner_text(),
        )
    finally:
        for pattern, _ in routes:
            page.unroute(pattern)
        page.remove_listener("pageerror", listener)
        r.goto_app()
    r.check(
        not errors, "/llm, premier chargement simulé : aucune erreur JavaScript", str(errors)[:300]
    )


_EXAMPLE_INPUT_JS = """() => [...document.querySelectorAll('#token-chips .token-chip')].map(c => ({
  example: c.classList.contains('is-example'),
  chip: c.querySelector('.token-chip-text').textContent,
  id: c.querySelector('.token-chip-id').textContent,
}))"""


def _example_rows(r: Run, sampling: dict[str, float], lang: str = "fr") -> tuple[bool, str]:
    """Whether the Draw's chart shows the content's example for `sampling` (polled), the
    badge « Exemple » above it."""
    example = _content(lang, "llm_lab.yaml")["stages"]["output"]["example"]
    values = [c["p"] for c in example["candidates"]]
    want = live_distribution(values, example["tail"], Sampling(**sampling))
    why = live_dropped_by(values, example["tail"], Sampling(**sampling))
    texts = [c["text"].replace(" ", "␣") for c in example["candidates"]]

    def same() -> bool:
        got = _dist_rows(r)
        return (
            "is-example" in (r.page.locator("#output-tag").get_attribute("class") or "")
            and [g["text"] for g in got] == texts
            and all(
                g["dropped"] == (not w["kept"])
                and abs(g["chanceWidth"] - w["p_sampled"] * 100) < 0.01
                and (w["kept"] or g["chance"] == f"écarté ({reason})")
                for g, w, reason in zip(got, want, why, strict=True)
            )
        )

    ok, _ = r.poll(same, 10)
    got = _dist_rows(r)
    return ok, str([(g["text"], g["chance"]) for g in got])


def _llm_loop_example(r: Run) -> None:
    """Correction C of 2026-10-05, the fake cloud A as it is (no route), the page opened: the
    INPUT shows the example's 5 columns (badge « Exemple », its note), cut step by step by
    ◀ ▶; the OUTPUT the example's Logits and Draw with the provider's reason; top-k, which
    the provider does not take, active: it moves the example's bars. Nothing asked by itself.
    Each stage within the screen at 1366 × 768."""
    page = r.page
    seq = r.ev.mark()
    _goto_lab(r)
    expect(page.locator("#llm-model")).to_contain_text("RÉSEAU", timeout=5000)
    transfo = _content("fr", "llm_lab.yaml")["stages"]["transfo"]
    want = [
        {"example": True, "chip": t.replace(" ", "␣"), "id": str(i)}
        for t, i in zip(transfo["example_tokens"], transfo["example_ids"], strict=True)
    ]
    expect(page.locator("#token-chips .token-chip.is-example")).to_have_count(5, timeout=5000)
    columns = page.evaluate(_EXAMPLE_INPUT_JS)
    tag = page.inner_text("#input-tag")
    note = _plain(page.inner_text("#token-example"))
    r.check(
        columns == want
        and tag.startswith("EXEMPLE")
        and note.startswith("Exemple : un texte découpé")
        and page.locator("#token-empty").is_hidden(),
        "cloud A, 1er chargement : l'INPUT montre 5 colonnes d'exemple, badge « Exemple », sa note",
        f"{tag} · {columns}",
    )
    stepper = page.locator("#input-stepper")
    states = [page.evaluate(_INPUT_JS)]
    for _ in range(2):
        stepper.locator(".diagram-step-next").click()
        states.append(page.evaluate(_INPUT_JS))
    r.check(
        [(s["cut"], s["tokens"], s["ids"]) for s in states]
        == [(False, False, False), (True, True, False), (True, True, True)]
        and states[2]["idVisible"] == "visible",
        "cloud A, exemple : ◀ ▶ découpent le texte en tokens, puis en identifiants, pas à pas",
        str([(s["cut"], s["tokens"], s["ids"]) for s in states]),
    )
    harness = {"temperature": 0.7, "top_k": 20, "top_p": 0.8, "min_p": 0.0}
    for name, value in harness.items():
        _set_live(r, name, value)
    ok_start, start = _example_rows(r, harness)
    empty = page.inner_text("#distribution-note")
    r.check(
        ok_start
        and page.locator("#distribution-body").is_visible()
        and page.locator("#logits-body").is_visible()
        and page.inner_text("#output-tag").startswith("EXEMPLE")
        and empty.startswith("Exemple d'illustration")
        and "Faux fournisseur (e2e)" in empty
        and "après « Bonjour, comment allez-vous »" in page.inner_text("#logits-caption"),
        "cloud A, 1er chargement : l'OUTPUT montre Logits et Tirage d'exemple, badge « Exemple »,"
        " la raison du fournisseur",
        f"{start} · {empty[:160]}",
    )
    top_k = page.locator("#sampling-top_k")
    reason = page.inner_text('.sampling-row[data-setting="top_k"] .sampling-row-reason')
    _set_live(r, "top_k", 2, slider=True)
    ok_k, cut = _example_rows(r, harness | {"top_k": 2})
    r.check(
        top_k.is_enabled()
        and "non réglable chez Faux fournisseur (e2e)" in reason
        and "ne bouge que l'exemple" in reason
        and ok_k
        and "écarté (top-k)" in cut,
        "cloud A : top-k (non pris par le fournisseur) actif, sa raison dite, il bouge l'exemple",
        f"{reason} · {cut}",
    )
    _set_live(r, "top_k", 20)
    page.set_viewport_size({"width": 1366, "height": 768})
    time.sleep(0.6)
    heights = page.evaluate(_STAGE_HEIGHTS_JS)
    parts = page.evaluate(_OUTPUT_PARTS_JS)
    page.set_viewport_size({"width": 1600, "height": 1000})
    r.check(
        all(h <= 768 for _, h in heights),
        "cloud A, exemple : chaque étape tient dans l'écran à 1366 × 768",
        f"{heights} · {parts}",
    )
    r.check(
        not r.ev.since(seq, "llm_tokenized") and not r.ev.since(seq, "llm_generation_started"),
        "cloud A : la page ne demande ni découpage ni pas par elle-même",
    )
    r.shot("76-llm-boucle-exemple-cloud", full_page=True)


def _llm_loop_cloud(r: Run) -> None:
    """The spec's « Cloud » row, on the fake cloud A as it is (no route): the example first
    (correction C of 2026-10-05), then the INPUT's estimate beside the example's columns, the
    TRANSFORMATION's dimensions « inconnue » and « Architecture non lue », « Tirer le token
    suivant » greyed with the candidates' reason, a direct call refused (409)."""
    page = r.page
    _llm_loop_example(r)
    _lab_tokenize(r, "Bonjour tout le monde")
    facts = page.inner_text("#transfo-facts")
    unknown = page.inner_text("#transfo-unknown")
    r.check(
        "≈" in page.inner_text("#token-counts")
        and page.locator("#token-chips .token-chip.is-example").count() == 5
        and _plain(page.inner_text("#token-example")).startswith(
            "Exemple de découpage, pas celui de ce modèle"
        )
        and "inconnue" in facts
        and page.locator("#transfo-unknown").is_visible()
        and unknown.startswith("Architecture non lue"),
        "cloud A : INPUT estimé à côté des colonnes d'exemple (pas le découpage du modèle),"
        " TRANSFORMATION « inconnue », architecture non lue",
        f"{facts.replace(chr(10), ' ')[:160]} · {unknown}",
    )
    button = page.locator("#llm-step-button")
    # Correction C of 2026-10-05: the reason said once, with the example at the OUTPUT's top.
    status = page.inner_text("#distribution-note")
    refused = r.api(
        "POST",
        "/api/intentions/llm_step",
        {"prompt": "Bonjour", "continuation": [], "sampling": _LAB_SAMPLING},
    )
    r.check(
        button.is_disabled()
        and "Faux fournisseur (e2e)" in (button.get_attribute("title") or "")
        and "Faux fournisseur (e2e)" in status
        and page.inner_text("#llm-step-status") == ""
        and refused.status_code == 409
        and page.locator("#llm-step-raw").is_hidden(),
        "cloud A : « Tirer le token suivant » grisé avec la raison des candidats (dite une fois,"
        " avec l'exemple), appel direct 409, pas de phrase « sans gabarit »",
        f"{button.get_attribute('title')} · {status} · {refused.status_code}",
    )
    r.goto_app()


def _llm_loop(r: Run, live: _LoopLab) -> None:
    page = r.page
    _goto_lab(r)
    expect(page.locator("#llm-step-button")).to_be_visible(timeout=5000)
    _llm_loop_input(r, live)
    _llm_loop_transfo(r)
    _llm_loop_output(r, live)
    _llm_loop_heights(r)
    _llm_loop_families(r, live)
    _llm_loop_bos(r, live)
    _llm_loop_end(r, live)


_INPUT_JS = """() => {
  const box = document.getElementById('llm-input');
  const cols = [...document.querySelectorAll('#token-chips .token-chip')];
  return {
    cut: box.classList.contains('is-cut'),
    tokens: box.classList.contains('show-tokens'),
    ids: box.classList.contains('show-ids'),
    caption: document.getElementById('input-caption').textContent,
    pieces: cols.map(c => c.querySelector('.llm-input-seg').textContent),
    chips: cols.map(c => c.querySelector('.token-chip-text').textContent),
    ids_: cols.map(c => c.querySelector('.token-chip-id').textContent),
    produced: cols.map(c => c.classList.contains('is-produced')),
    labels: cols.map(c => c.getAttribute('aria-label')),
    idVisible: cols.length
      ? getComputedStyle(cols[0].querySelector('.llm-input-id')).visibility
      : '',
  };
}"""


def _llm_loop_input(r: Run, live: _LoopLab) -> None:
    """The INPUT, step by step: « Découper en tokens » opens step 1 (the text in one block),
    ▶ cuts it into tokens, ▶ shows their ids; the session's tokens and ids, as received."""
    page = r.page
    page.fill("#llm-prompt", _LOOP_TEXT)
    expect(page.locator("#tokenize-button")).to_be_enabled(timeout=10_000)
    live.add_batch(("llm_tokenized", _loop_tokenized()))
    page.click("#tokenize-button")
    live.release()
    # Correction C of 2026-10-05: the example's 5 columns until then, never the session's.
    expect(page.locator("#token-chips .token-chip.is-example")).to_have_count(0, timeout=10_000)
    expect(page.locator("#token-chips .token-chip")).to_have_count(5, timeout=10_000)
    stepper = page.locator("#input-stepper")
    first = page.evaluate(_INPUT_JS)
    r.check(
        page.inner_text("#input-tag").startswith("RÉEL")
        and page.locator("#token-example").is_hidden(),
        "INPUT découpé exactement : badge « Réel », plus de note d'exemple",
        page.inner_text("#input-tag"),
    )
    r.check(
        not first["cut"]
        and first["idVisible"] == "hidden"
        and first["caption"].startswith("Texte.")
        and "".join(first["pieces"]) == _LOOP_TEXT
        and stepper.locator(".diagram-step-live").inner_text() == "Tout montrer",
        "INPUT pas 1 : le texte d'un bloc, colonnes collées, ni token ni identifiant visibles",
        str(first)[:300],
    )
    stepper.locator(".diagram-step-next").click()
    second = page.evaluate(_INPUT_JS)
    stepper.locator(".diagram-step-next").click()
    third = page.evaluate(_INPUT_JS)
    r.check(
        second["cut"]
        and second["tokens"]
        and not second["ids"]
        and second["caption"].startswith("Tokens.")
        and second["chips"] == ["Le", "␣chat", "␣dort", "␣sur", "␣le"],
        "INPUT pas 2 : le texte se découpe, une puce par token, blancs visibles (␣)",
        str(second["chips"]),
    )
    counts = _plain(page.inner_text("#token-counts"))
    r.check(
        third["ids"]
        and third["idVisible"] == "visible"
        and third["caption"].startswith("Identifiants.")
        and third["ids_"] == [str(i) for i, _ in _LOOP_TOKENS]
        and third["labels"][1] == "« chat » → token ␣chat → identifiant 9558"
        and counts.startswith("5 tokens")
        and "5 nombres entre 0 et 248 319" in counts,
        "INPUT pas 3 : les identifiants reçus sous chaque token, compteurs de la session",
        f"{third['ids_']} · {counts!r} · {third['labels'][1]!r}",
    )
    r.check(
        page.locator("#token-bos").is_hidden(),
        "INPUT sans BOS (modèle qui n'en demande pas) : aucune phrase sur le token de début",
    )
    r.shot_element("70-llm-boucle-input", "#stage-input")


def _llm_loop_transfo(r: Run) -> None:
    """The TRANSFORMATION: the banner of a hybrid (D4), its 7 steps with the GGUF's real
    dimensions, the stack of layers (one in four in full attention), the note."""
    page = r.page
    banner = _plain(page.inner_text("#transfo-banner"))
    r.check(
        page.locator("#transfo-banner").is_visible()
        and banner.startswith("⚠ Schéma simplifié, inexact pour cette architecture.")
        and "est hybride : seule une couche sur 4 fait de l'attention complète" in banner,
        "TRANSFORMATION : bandeau D4 d'un modèle hybride, l'intervalle lu dans l'en-tête",
        banner[:200],
    )
    stepper = page.locator("#transfo-stepper")
    titles, drawn = [], []
    for step in range(7):
        if step:
            stepper.locator(".diagram-step-next").click()
        titles.append(page.inner_text("#transfo-step-title"))
        drawn.append(page.locator("#transfo-svg > *").count())
        if step == 1:
            legend = page.inner_text("#transfo-stack-legend")
            stack = page.locator("#transfo-stack i")
            rec = page.locator("#transfo-stack i.is-rec").count()
            now = page.locator("#transfo-stack i.is-now").count()
            attention = page.locator("#transfo-svg .llm-transfo-arc").count()
    r.check(
        len(set(titles)) == 7
        and titles[0].startswith("Embeddings")
        and titles[-1].startswith("Le vecteur du dernier token")
        and all(drawn)
        and stepper.locator(".diagram-step-next").get_attribute("aria-disabled") == "true",
        "TRANSFORMATION : 7 pas, un dessin et un titre chacun, ▶ grisé au dernier",
        str(titles),
    )
    r.check(
        stack.count() == 24
        and rec == 18
        and now == 1
        and attention == 5
        and "plein : attention complète, tirets : récurrente" in legend,
        "TRANSFORMATION : 24 couches, 1 sur 4 pleine (attention complète), la couche 1 en cours",
        f"{stack.count()} couches, {rec} récurrentes · {legend}",
    )
    panel = _plain(page.inner_text("#embedding-diagram"))
    note = page.inner_text("#transfo-note")
    r.check(
        "vecteurs de 2 048 nombres" in panel
        and "248 320 × 2 048" in panel
        and "24 couches" in panel
        and "8 têtes d'attention, 2 K/V" in panel
        and "2 048 → 6 144 → 2 048" in panel
        and "24 couches traversées" in panel
        and note.startswith(
            "Le moteur n'expose ni les poids d'attention ni les états cachés : 5 tokens"
        ),
        "TRANSFORMATION : les vraies dimensions du GGUF au panneau, la note « illustratif »",
        panel.replace("\n", " · ")[:300],
    )
    stepper.locator(".diagram-step-prev").click()
    stepper.locator(".diagram-step-prev").click()
    stepper.locator(".diagram-step-prev").click()
    stepper.locator(".diagram-step-prev").click()  # the MLP of layer 1: 8 → 16 → 8
    r.check(
        page.locator("#transfo-svg .llm-transfo-neuron").count() == 32
        and page.locator("#transfo-svg .llm-transfo-neuron.is-on").count() == 5,
        "TRANSFORMATION, MLP : 8 → 16 → 8 neurones, cinq allumés",
    )
    r.shot_element("71-llm-boucle-transformation", "#stage-transfo")


def _llm_loop_rows(r: Run, sampling: dict[str, float]) -> tuple[bool, str]:
    """Whether the Draw's chart shows the step's candidates for `sampling` (polled)."""
    draw = _LOOP_DRAWS[0]
    want = live_distribution([p for _, p in draw["top"]], draw["tail"], Sampling(**sampling))[:6]

    def same() -> bool:
        got = _dist_rows(r)
        return len(got) == len(want) and all(
            g["dropped"] == (not w["kept"]) and abs(g["chanceWidth"] - w["p_sampled"] * 100) < 0.01
            for g, w in zip(got, want, strict=True)
        )

    ok, _ = r.poll(same, 10)
    got = _dist_rows(r)
    return ok, str([(g["text"], g["chance"]) for g in got])


def _llm_loop_output(r: Run, live: _LoopLab) -> None:
    """The OUTPUT: a setting's help (title and popover), a step drawn by « the engine », its
    Logits and Draw, the chances following a setting, then « Ajouter à la suite » (the token
    in the INPUT, the continuation sent) and « Retirer le dernier »."""
    page = r.page
    for name, value in _LOOP_SAMPLING.items():
        _set_live(r, name, value)
    help_text = _content("fr", "llm_lab.yaml")["sampling"]["settings"]["temperature"]["help_text"]
    name = page.locator(
        '#sampling-controls .sampling-row[data-setting="temperature"] .sampling-row-name'
    )
    name.click()
    popover = page.locator("#sampling-temperature-help")
    opened = popover.evaluate("e => e.matches(':popover-open')")
    shown = popover.inner_text() if opened else ""
    page.keyboard.press("Escape")
    closed = not popover.evaluate("e => e.matches(':popover-open')")
    r.check(
        " ".join(help_text.split()) == (name.get_attribute("title") or "")
        and opened
        and shown.startswith("Aplatit ou creuse")
        and closed
        and name.get_attribute("aria-describedby") == "sampling-temperature-help",
        "OUTPUT : le nom d'un réglage porte son aide, au survol (title) et au clic, Échap la ferme",
        f"{opened} · {shown[:60]!r} · fermé {closed}",
    )
    # Correction C of 2026-10-05: before the first step, the example, labelled, never empty.
    ok_example, example = _example_rows(r, _LOOP_SAMPLING)
    r.check(
        ok_example
        and page.locator("#distribution-body").is_visible()
        and page.inner_text("#output-tag").startswith("EXEMPLE")
        and "Tirez le token suivant" in page.inner_text("#distribution-note")
        and not live.requests,
        "OUTPUT avant le premier pas : Logits et Tirage d'exemple, badge « Exemple », quoi faire",
        example,
    )

    # A step: « Tirer le token suivant », the engine draws « ␣canapé ».
    expect(page.locator("#llm-step-button")).to_be_enabled(timeout=5000)
    page.click("#llm-step-button")
    r.poll(lambda: len(live.steps) == 1, 5)
    live.drawn(_LOOP_DRAWS[0])
    expect(page.locator("#llm-step-drawn .llm-output-chip")).to_have_text("␣canapé", timeout=10_000)
    ok, drawn = _llm_loop_rows(r, _LOOP_SAMPLING)
    logits = page.locator("#logits-bars .dist-row:not(.is-tail) .dist-text").all_inner_texts()
    sent = live.steps[0]
    r.check(
        ok
        and sent["prompt"] == _LOOP_TEXT
        and sent["continuation"] == []
        and sent["sampling"]["temperature"] == 0.7
        and logits == ["␣canapé", "␣lit", "␣tapis", "␣toit", "␣rebord", "␣sol"]
        and page.locator("#logits-bars .dist-row.is-chosen").count() == 1
        and page.inner_text("#output-tag").startswith("RÉEL")
        and page.inner_text("#distribution-note") == ""
        and page.inner_text("#distribution-token").startswith(
            "Candidats du token tiré par le moteur"
        )
        and "après « dort sur le »" in page.inner_text("#logits-caption"),
        "OUTPUT : le moteur tire « ␣canapé », Logits et Tirage montrent ses 6 premiers candidats",
        f"{logits} · {drawn}",
    )
    raw = page.locator("#llm-step-raw")
    raw_text = _content("fr", "llm_lab.yaml")["stages"]["output"]["raw_text"]
    r.check(
        raw.is_visible() and _plain(raw.inner_text()) == _plain(raw_text),
        "OUTPUT : la carte du token tiré dit que le pas lit le texte sans gabarit, « Générer » non",
        raw.inner_text()[:160],
    )
    _set_live(r, "temperature", 1.5, slider=True)
    ok_hot, hot = _llm_loop_rows(r, _LOOP_SAMPLING | {"temperature": 1.5})
    _set_live(r, "top_p", 0.6)
    ok_p, cut = _llm_loop_rows(r, _LOOP_SAMPLING | {"temperature": 1.5, "top_p": 0.6})
    dropped = page.locator(
        "#distribution-bars .dist-row.is-dropped .dist-cell.is-chance .dist-value"
    )
    r.check(
        ok_hot
        and ok_p
        and dropped.count() >= 1
        and set(dropped.all_inner_texts()) == {"écarté (top-p)"},
        "OUTPUT : la chance suit la température puis top-p, les écartés disent « écarté (top-p) »",
        f"{hot} · {cut}",
    )
    r.check(
        page.locator("#llm-step-drawn .llm-output-chip").count() == 0
        and page.locator("#llm-step-append").is_disabled(),
        "un réglage bougé efface le token tiré (tiré avec les réglages d'avant), « Ajouter » grisé",
    )
    page.click("#llm-step-button")
    r.poll(lambda: len(live.steps) == 2, 5)
    live.drawn(_LOOP_DRAWS[0])
    expect(page.locator("#llm-step-drawn .llm-output-chip")).to_have_text("␣canapé", timeout=10_000)
    expect(page.locator("#distribution-body")).to_be_visible(timeout=10_000)
    r.shot_element("72-llm-boucle-output", "#stage-output")

    # « Ajouter à la suite »: the token in the INPUT (a produced column), sent with the next.
    page.click("#llm-step-append")
    expect(page.locator("#token-chips .token-chip")).to_have_count(6, timeout=5000)
    expect(page.locator("#output-tag")).to_have_class(re.compile("is-example"), timeout=5000)
    state = page.evaluate(_INPUT_JS)
    r.poll(lambda: abs((page.locator("#stage-input").bounding_box() or {"y": 999})["y"]) < 60, 5)
    top = page.locator("#stage-input").bounding_box()
    r.check(
        state["produced"] == [False] * 5 + [True]
        and state["ids_"][-1] == "107233"
        and state["ids"]
        and page.locator("#llm-step-drawn .llm-output-chip").count() == 0
        and page.inner_text("#output-tag").startswith("EXEMPLE")
        and top is not None
        and abs(top["y"]) < 60,
        "« Ajouter à la suite » : ␣canapé en puce « produit » au bout de l'INPUT, la page remonte,"
        " l'OUTPUT repasse à l'exemple",
        f"{state['produced']} · {state['ids_'][-1:]} · {top}",
    )
    page.click("#llm-step-button")
    r.poll(lambda: len(live.steps) == 3, 5)
    live.drawn(_LOOP_DRAWS[1])
    expect(page.locator("#llm-step-drawn .llm-output-chip")).to_have_text(".", timeout=10_000)
    r.check(
        live.steps[2]["continuation"] == [107233],
        "pas suivant : le token ajouté part avec le texte (continuation)",
        str(live.steps[2].get("continuation")),
    )
    page.click("#llm-step-undo")
    expect(page.locator("#token-chips .token-chip")).to_have_count(5, timeout=5000)
    r.check(
        page.locator("#token-chips .token-chip.is-produced").count() == 0
        and page.locator("#llm-step-undo").is_disabled(),
        "« Retirer le dernier » : l'ajout quitte l'INPUT",
    )
    # A changed text erases what was added.
    page.click("#llm-step-button")
    r.poll(lambda: len(live.steps) == 4, 5)
    live.drawn(_LOOP_DRAWS[0])
    expect(page.locator("#llm-step-append")).to_be_enabled(timeout=10_000)
    page.click("#llm-step-append")
    expect(page.locator("#token-chips .token-chip.is-produced")).to_have_count(1, timeout=5000)
    counts = _plain(page.inner_text("#token-counts"))
    r.check(
        counts.startswith("5 tokens") and "dont 1 ajouté par l'OUTPUT" in counts,
        "compteurs de l'INPUT : ceux de la session, plus le token ajouté par l'OUTPUT",
        counts,
    )
    page.fill("#llm-prompt", _LOOP_TEXT + " !")
    draw = page.locator("#llm-step-button")
    first = "Découpez d'abord ce texte en tokens (étape 1)."
    r.check(
        page.locator("#token-chips .token-chip.is-produced").count() == 0
        and draw.is_disabled()
        and draw.get_attribute("title") == first
        and page.inner_text("#llm-step-status") == first,
        "texte changé : les ajouts sont effacés, « Tirer » attend le découpage de ce texte",
        f"{draw.get_attribute('title')!r}",
    )
    page.fill("#llm-prompt", _LOOP_TEXT)
    expect(draw).to_be_enabled(timeout=5000)
    for name, value in _LOOP_SAMPLING.items():
        _set_live(r, name, value)
    # A model load forgets the tokens added (another vocabulary).
    page.click("#llm-step-button")
    r.poll(lambda: len(live.steps) == 5, 5)
    live.drawn(_LOOP_DRAWS[0])
    expect(page.locator("#llm-step-append")).to_be_enabled(timeout=10_000)
    page.click("#llm-step-append")
    expect(page.locator("#token-chips .token-chip.is-produced")).to_have_count(1, timeout=5000)
    model = {"id": "e2e", "label": "Autre modèle (e2e)", "hosting": "local", "kind": "file"}
    live.add_batch(("model_load_started", {"model": model, "phase_label": "Chargement (e2e)"}))
    live.release()
    expect(page.locator("#token-chips .token-chip.is-produced")).to_have_count(0, timeout=10_000)
    page.click("#llm-step-button")
    r.poll(lambda: len(live.steps) == 6, 5)
    r.check(
        live.steps[5]["continuation"] == [],
        "chargement d'un modèle : les ajouts sont effacés, le pas suivant n'en envoie aucun",
        str(live.steps[5].get("continuation")),
    )
    live.drawn(_LOOP_DRAWS[0])
    expect(page.locator("#distribution-body")).to_be_visible(timeout=10_000)


# The OUTPUT's parts, their heights: what makes the stage taller than the screen.
_OUTPUT_PARTS_JS = """() => ['#part-logits', '#part-draw', '#part-token', '#distribution-note',
  '#logits-body', '.llm-output-side', '.llm-output-knobs', '.llm-output-draw > :last-child',
  '#sampling-controls', '#output-caption'].map(s => {
  const node = document.querySelector(s);
  return [s, node ? Math.round(node.getBoundingClientRect().height) : null];
})"""


_STAGE_HEIGHTS_JS = """() => ['stage-input', 'stage-transfo', 'stage-output'].map(id => {
  const box = document.getElementById(id).getBoundingClientRect();
  return [id, Math.round(box.height)];
})"""


def _llm_loop_heights(r: Run) -> None:
    """Each stage whole on the screen (DESIGN.md of lot 6), the banner and the charts shown,
    at the two target sizes; no horizontal scroll."""
    page = r.page
    for width, height in _LOOP_VIEWPORTS:
        page.set_viewport_size({"width": width, "height": height})
        time.sleep(0.6)  # the layout, the canvas's size
        heights = page.evaluate(_STAGE_HEIGHTS_JS)
        wide = page.evaluate("() => document.documentElement.scrollWidth > innerWidth + 1")
        r.check(
            all(h <= height for _, h in heights) and not wide,
            f"chaque étape tient dans l'écran à {width} × {height}",
            f"{heights} · défilement horizontal {wide} · {page.evaluate(_OUTPUT_PARTS_JS)}",
        )
        for _, selector in (("input", "#stage-input"), ("output", "#stage-output")):
            page.locator(selector).scroll_into_view_if_needed()
        number = 73 if width == 1600 else 74
        r.shot(f"{number}-llm-boucle-{width}x{height}", full_page=True)


_LOOP_MOE_HEADER = {
    "general.architecture": "qwen3moe",
    "qwen3moe.block_count": 48,
    "qwen3moe.embedding_length": 2048,
    "qwen3moe.feed_forward_length": 6144,
    "qwen3moe.expert_feed_forward_length": 768,
    "qwen3moe.expert_count": 128,
    "qwen3moe.expert_used_count": 8,
    "qwen3moe.attention.head_count": 32,
    "qwen3moe.attention.head_count_kv": 4,
}
_LOOP_DENSE_HEADER = {
    "general.architecture": "qwen3",
    "qwen3.block_count": 28,
    "qwen3.embedding_length": 1024,
    "qwen3.feed_forward_length": 3072,
    "qwen3.attention.head_count": 16,
    "qwen3.attention.head_count_kv": 8,
}


def _llm_loop_retokenize(r: Run, live: _LoopLab, header: dict[str, Any]) -> str:
    """A tokenization by a model of `header`: the banner's text once drawn again ('' hidden)."""
    page = r.page
    before = page.inner_text("#embedding-source")
    payload = _loop_tokenized(header)
    payload["dimensions"]["source_text"] = f"{before} ·"  # a change to wait for
    live.add_batch(("llm_tokenized", payload))
    live.release()
    expect(page.locator("#embedding-source")).to_have_text(f"{before} ·", timeout=10_000)
    banner = page.locator("#transfo-banner")
    return _plain(banner.inner_text()) if banner.is_visible() else ""


def _llm_loop_families(r: Run, live: _LoopLab) -> None:
    """The TRANSFORMATION's banner (D4) for a mixture of experts (its router and experts at
    the MLP step, numbered below its 128 experts), a hybrid with experts (both reasons) and a
    dense model (no banner)."""
    page = r.page
    page.set_viewport_size({"width": 1600, "height": 1000})
    stepper = page.locator("#transfo-stepper")
    banner = _llm_loop_retokenize(r, live, _LOOP_MOE_HEADER)
    stepper.locator(".diagram-step-live").click()
    for _ in range(4):
        stepper.locator(".diagram-step-prev").click()  # the MLP of layer 1
    experts = page.locator("#transfo-svg .llm-transfo-expert")
    labels = page.locator("#transfo-svg text").all_text_contents()
    r.check(
        "un routeur choisit 8 experts sur 128" in banner
        and "une couche sur" not in banner
        and experts.count() == 6
        and page.locator("#transfo-svg .llm-transfo-expert.is-on").count() == 2
        and "expert 117" in labels
        and "expert 121" not in labels
        and page.locator("#transfo-svg .llm-transfo-neuron").count() == 0,
        "TRANSFORMATION, mélange d'experts : bandeau (8 sur 128), routeur et 6 experts au pas MLP",
        f"{banner[:160]} · {[t for t in labels if t.startswith('expert')]}",
    )
    both = _llm_loop_retokenize(
        r, live, _LOOP_HEADER | {"qwen35.expert_count": 256, "qwen35.expert_used_count": 8}
    )
    r.check(
        "seule une couche sur 4 fait de l'attention complète" in both
        and "un routeur choisit 8 experts sur 256" in both,
        "TRANSFORMATION, hybride à experts : les deux raisons dans le bandeau",
        both[:240],
    )
    dense = _llm_loop_retokenize(r, live, _LOOP_DENSE_HEADER)
    r.check(
        dense == "" and page.locator("#transfo-banner").is_hidden(),
        "TRANSFORMATION, modèle dense : pas de bandeau",
        dense[:160],
    )


def _llm_loop_bos(r: Run, live: _LoopLab) -> None:
    """A model that asks a begin-of-text token (`llm_tokenized.bos_token`): the INPUT names
    it in a sentence, its columns and counters unchanged; gone again without one."""
    page = r.page
    payload = _loop_tokenized(_LOOP_DENSE_HEADER)
    payload["bos_token"] = "<bos>"
    live.add_batch(("llm_tokenized", payload))
    live.release()
    bos = page.locator("#token-bos")
    expect(bos).to_be_visible(timeout=10_000)
    said = _plain(bos.inner_text())
    counts = _plain(page.inner_text("#token-counts"))
    bos_text = _content("fr", "llm_lab.yaml")["stages"]["input"]["bos_text"]
    r.check(
        said == _plain(bos_text.replace("{bos}", "<bos>"))
        and bos.locator("code").inner_text() == "<bos>"
        and page.locator("#token-chips .token-chip").count() == 5
        and counts.startswith("5 tokens"),
        "INPUT, modèle qui demande le BOS : une phrase le nomme, puces et compteurs inchangés",
        f"{said!r} · {counts!r}",
    )
    live.add_batch(("llm_tokenized", _loop_tokenized(_LOOP_DENSE_HEADER)))
    live.release()
    expect(bos).to_be_hidden(timeout=10_000)


def _llm_loop_end(r: Run, live: _LoopLab) -> None:
    """A step whose token is the model's end token: no `llm_token`, the step ends
    `completed`; the OUTPUT says the text stops there for the model. Correction C of
    2026-10-05: the session's `llm_lab` state, as it comes, leaves the bars shown during the
    step (no blink); the step over without a token, the OUTPUT goes back to the example."""
    page = r.page
    expect(page.locator("#llm-step-button")).to_be_enabled(timeout=5000)
    model = r.state().get("active_model")
    tag = page.locator("#output-tag")
    expect(tag).not_to_have_class(re.compile("is-example"), timeout=10_000)  # a real draw
    before = len(live.steps)
    page.click("#llm-step-button")
    r.poll(lambda: len(live.steps) == before + 1, 5)
    rid = live.step_id
    live.add_batch(
        (
            "session_state",
            {"state": "llm_lab", "reason_text": "Écran LLM (e2e).", "active_model": model},
        )
    )
    live.release()
    expect(page.locator("#llm-busy")).to_contain_text("Écran LLM (e2e).", timeout=10_000)
    page.wait_for_timeout(500)
    r.check(
        page.locator("#distribution-body").is_visible()
        and "is-example" not in (tag.get_attribute("class") or ""),
        "pas en cours (session en llm_lab) : les barres montrées restent, sans clignoter",
        tag.inner_text(),
    )
    live.add_batch(
        (
            "llm_generation_started",
            {
                "request_id": rid,
                "prompt": _LOOP_TEXT,
                "rendered": _LOOP_TEXT,
                "prompt_tokens": 5,
                "exact": True,
                "sampling": _LOOP_SAMPLING | {"source": "screen"},
                "reserve": 512,
                "usable": 3584,
                "phase_label": "Lecture (e2e)",
                "unit": "token",
                "figures_text": {"prompt_tokens": "5", "reserve": "512", "window": "4 096"},
            },
        ),
        (
            "llm_generation_ended",
            {
                "request_id": rid,
                "status": "completed",
                "duration_ms": 9,
                "answer_tokens": 0,
                "figures_text": {"reasoning_tokens": "0", "answer_tokens": "0"},
            },
        ),
        ("session_state", {"state": "idle", "reason_text": None, "active_model": model}),
    )
    live.release()
    end_text = _content("fr", "llm_lab.yaml")["stages"]["output"]["end_text"]
    status = page.locator("#llm-step-status")
    expect(status).to_have_text(end_text, timeout=10_000)
    expect(tag).to_have_class(re.compile("is-example"), timeout=10_000)
    r.check(
        status.inner_text() == end_text and page.locator("#distribution-body").is_visible(),
        "OUTPUT, token de fin tiré : le texte s'arrête là pour le modèle, rien à ajouter ;"
        " l'OUTPUT repasse à l'exemple (la session ne garde rien de ce pas)",
        status.inner_text(),
    )
    expect(page.locator("#llm-step-button")).to_be_enabled(timeout=10_000)


# ---------- story 30: the RAG workshop ----------

RAG_LAB_QUESTION = "Combien de jours de télétravail par semaine ?"
# Lot 5a: the chain's stages (their technical names, English in every language)...
RAG_LAB_STAGES = [
    "Chunking",
    "Embedding",
    "Vector store",
    "Dense retrieval",
    "Reranking",
    "Prompt augmentation",
    "Generation",
]
# ... and the sequence's lines, BUILD then RUN (vues-atelier-rag.md §2).
RAG_LAB_SEQUENCE = [
    "Documents",
    "Chunking",
    "Embedding",
    "Indexing",
    "Question",
    "Embedding",
    "Dense retrieval",
    "Reranking",
    "Prompt augmentation",
    "Generation",
]
RAG_LAB_TILES = [
    "Documents",
    "Chunks",
    "Vector store",
    "Embedding model",
    "Reranker",
    "LLM",
    "Question",
    "Augmented prompt",
    "Réponse",
]

# Every text a `.rag-stage-status` shows, recorded as it changes (the run is fast: a status
# may last one render only).
_WATCH_STATUSES_JS = """() => {
  window.__ragStatuses = [];
  const seen = () => { for (const s of document.querySelectorAll('.rag-stage-status'))
    window.__ragStatuses.push(s.textContent); };
  new MutationObserver(seen).observe(document.getElementById('rag-results'),
    { childList: true, subtree: true, characterData: true });
}"""

# The three views' boxes, and whether the page scrolls sideways.
_RAG_VIEWS_JS = """() => {
  const box = (id) => { const r = document.getElementById(id).getBoundingClientRect();
    return { l: r.left, r: r.right, t: r.top, b: r.bottom, h: r.height }; };
  return { seq: box('rag-seq'), arch: box('rag-arch'), focus: box('rag-focus'),
    views: box('rag-views'), scroll: document.documentElement.scrollWidth - innerWidth };
}"""


def _goto_rag_lab(r: Run) -> None:
    r.page.goto(f"{r.stack.app_url}/rag")
    expect(r.page.locator("body[data-rag-ready]")).to_be_attached(timeout=10_000)


def _rag_mode(r: Run, mode: str) -> None:
    """« ✎ Composer » (`compose`) or « ▶ Dérouler » (`play`), pressed."""
    button = r.page.locator(f'#rag-modes [data-mode="{mode}"]')
    if button.get_attribute("aria-pressed") != "true":
        button.click()
    expect(button).to_have_attribute("aria-pressed", "true")


def _open_details(r: Run) -> None:
    """« Toutes les étapes en détail », unfolded (its cards read as rendered)."""
    r.page.evaluate("() => { document.getElementById('rag-details').open = true; }")


def _rag_lab_run(
    r: Run, question: str = RAG_LAB_QUESTION, compose: bool = False
) -> tuple[dict[str, Any], int]:
    """« Lancer la chaîne »: the run's end, and the mark before it. « Lancer » passes into
    « Dérouler » (lot 5a-2); `compose`: back to « Composer » once the run ended."""
    page = r.page
    page.fill("#rag-question", question)
    expect(page.locator("#rag-run")).to_be_enabled(timeout=10_000)
    seq = r.ev.mark()
    page.click("#rag-run")
    expect(page.locator('#rag-modes [data-mode="play"]')).to_have_attribute("aria-pressed", "true")
    ended = r.ev.wait("rag_lab_run_ended", seq, timeout=60)
    expect(page.locator("#rag-run")).to_be_enabled(timeout=10_000)
    if compose:
        _rag_mode(r, "compose")
    return ended, seq


def _stage_ended(r: Run, seq: int, kind: str) -> dict[str, Any]:
    found = [
        e["payload"] for e in r.ev.since(seq, "rag_lab_stage_ended") if e["payload"]["kind"] == kind
    ]
    return found[-1] if found else {}


def _result_card(r: Run, kind: str):
    return r.page.locator(f'#rag-details .rag-lane .rag-stage-card[data-kind="{kind}"]')


def _seq_row(r: Run, kind: str):
    """The sequence's line of a chain's stage (Composer: it carries the stage's editor)."""
    return r.page.locator(f'#rag-seq li.rag-chain-card[data-kind="{kind}"]')


def _option_label(r: Run, kind: str) -> str:
    """The option a stage's line shows: its select's choice, else its single option."""
    return _seq_row(r, kind).evaluate(
        "row => { const s = row.querySelector('select.rag-option');"
        " return s ? s.selectedOptions[0].textContent"
        " : row.querySelector('.rag-chain-option').textContent; }"
    )


def _focus_of(r: Run, step: str) -> dict[str, Any]:
    """A line clicked: the focus's step and name, its components, the wires drawn."""
    page = r.page
    page.locator(f'#rag-seq .rag-seq-step[data-step="{step}"] .rag-seq-head').click()
    time.sleep(0.15)  # the wires, drawn at the next frame
    return page.evaluate(
        "() => { const f = document.getElementById('rag-focus');"
        " return { step: f.dataset.step,"
        " name: f.querySelector('.rag-focus-name')?.textContent ?? '',"
        " explain: f.querySelector('.rag-focus-explain')?.textContent ?? '',"
        " uses: [...f.querySelectorAll('.rag-focus-uses .rag-tag')].map(t => t.dataset.component),"
        " wires: [...document.querySelectorAll('#rag-views .diagram-path-core')]"
        ".map(p => p.dataset.component),"
        " rows: f.querySelectorAll('.rag-items tbody tr').length,"
        " text: f.innerText }; }"
    )


def s_rag_lab(r: Run) -> None:
    """Story 30, after `rag_rerank` (index built, both fake models on the workstation): the
    « Atelier RAG » link of the top bar; lot 5a: the three views side by side (the sequence
    BUILD then RUN, the architecture, the focus of a line clicked, its wires), the editor in
    the sequence (Composer); a run on a question (each stage's input, output, excerpts,
    duration and memory, in the details and in the focus), the same run after a reload, a 409
    while a workshop turn runs. Back to `/`."""
    page = r.page
    page.set_viewport_size({"width": 1600, "height": 1000})
    errors: list[str] = []
    listener = lambda e: errors.append(str(e))  # noqa: E731
    page.on("pageerror", listener)
    try:
        _rag_lab(r, errors)
    finally:
        page.remove_listener("pageerror", listener)
        if page.locator("#theme-picker").count():
            _pick_theme(page, "system")
        r.goto_app()


def _downloads_text(count: int) -> str:
    """« 1 modèle à télécharger », « 2 modèles à télécharger » (ui.yaml, `rag.arch_downloads`)."""
    return f"{count} modèle{'s' if count > 1 else ''} à télécharger"


def _rag_lab_arch_downloads(r: Run) -> None:
    """B1 (2026-10-05), in Composer with no line selected (the shipped chain): every
    « Télécharger » of the Embedding and Reranking lines visible; the tiles Embedding model and
    Reranker say « N modèles à télécharger », N the catalog's `download_count`. In Dérouler, the
    tile's mention opens Composer, the Embedding line selected, its first « Télécharger »
    focused."""
    page = r.page
    catalog = r.api("GET", "/api/rag_lab").json()["catalog"]
    counts = {s["kind"]: s.get("download_count") for s in catalog["stages"]}
    lines = {
        kind: _seq_row(r, kind).evaluate(
            "row => [...row.querySelectorAll('.rag-chain-download')]"
            ".filter(l => l.checkVisibility()).length"
        )
        for kind in ("embedding", "rerank")
    }
    mentions = page.eval_on_selector_all(
        "#rag-arch .rag-arch-download",
        "bs => Object.fromEntries(bs.map(b => [b.closest('.rag-arch-tile').dataset.component,"
        " { text: b.textContent, visible: b.checkVisibility() }]))",
    )
    r.check(
        not page.locator("#rag-seq .rag-seq-step.is-selected").count()
        and counts["embedding"] == 2
        and counts["rerank"] == 1
        and lines == {"embedding": 2, "rerank": 1}
        and mentions
        == {
            "embedding_model": {"text": _downloads_text(2), "visible": True},
            "reranker": {"text": _downloads_text(1), "visible": True},
        },
        "B1 : en Composer, sans ligne choisie, les « Télécharger » d'Embedding (2) et de "
        "Reranking (1) visibles ; tuiles « 2 modèles à télécharger », « 1 modèle à télécharger » "
        "(download_count du catalogue)",
        f"{counts} · {lines} · {mentions}",
    )
    # Dérouler: the tile revealed (▶ up to the Embedding of the chunks), its mention clicked.
    _rag_mode(r, "play")
    tile = page.locator('#rag-arch .rag-arch-tile[data-component="embedding_model"]')
    nxt = page.locator("#rag-stepper .diagram-step-next")
    for _ in range(12):
        if "is-hidden" not in (tile.get_attribute("class") or ""):
            break
        nxt.click()
    mention = tile.locator(".rag-arch-download")
    played = mention.is_visible() and mention.inner_text().endswith(_downloads_text(2))
    if not played:
        r.check(False, "B1 : la tuile Embedding model révélée en Dérouler, sa mention visible")
        _rag_mode(r, "compose")
        return
    mention.click()
    expect(page.locator('#rag-modes [data-mode="compose"]')).to_have_attribute(
        "aria-pressed", "true"
    )
    focus = page.evaluate(
        "() => { const a = document.activeElement; return { cls: a.className,"
        " target: a.dataset.target, step: a.closest('.rag-seq-step')?.dataset.step }; }"
    )
    selected = page.eval_on_selector_all(
        "#rag-seq .rag-seq-step.is-selected", "rs => rs.map(r => r.dataset.step)"
    )
    r.check(
        played
        and selected == ["embed_passages"]
        and "rag-download" in focus["cls"].split()
        and focus["step"] == "embed_passages"
        and focus["target"].startswith("rag_lab_embedding:"),
        "B1 : en Dérouler, la mention de la tuile Embedding model passe en Composer, choisit la "
        "ligne Embedding et met le focus sur son premier « Télécharger »",
        f"{played} · {selected} · {focus}",
    )
    # Back to no line selected, as the scenario goes on.
    _rag_mode(r, "play")
    _rag_mode(r, "compose")


def _rag_lab_download(r: Run) -> None:
    """Lot 5c-4: « Télécharger » in the Embedding's line (B1: no line selected) for a
    workshop's model missing; its click enters `download`, the stage's « Arrêter » stops it,
    or (the e2e stack being offline) it fails at once: the outcome, traced outside the brick,
    said in the stage, the button active again. No real download is completed."""
    page = r.page
    target = "rag_lab_embedding:qwen3-embedding-0.6b"
    row = _seq_row(r, "embedding")
    # B1 (2026-10-05): visible without selecting the line (no click on its head).
    button = row.locator(f'button.rag-download[data-target="{target}"]')
    expect(button).to_be_visible(timeout=5000)
    catalog = r.api("GET", "/api/rag_lab").json()["catalog"]
    stage = next(s for s in catalog["stages"] if s["kind"] == "embedding")
    option = next(o for o in stage["options"] if o["id"] == "qwen3-embedding-0.6b")
    label = button.inner_text()
    r.check(
        option["download"] == {"target": target, "label_text": label}
        and re.fullmatch(r"Télécharger \(≈ \d+ Mo\)", label) is not None
        and option["label_text"] in (button.get_attribute("aria-label") or "")
        and button.is_enabled()
        and "dans cette étape en mode Composer" in option["reason_text"],
        "lot 5c-4 : « Télécharger (≈ N Mo) » dans la ligne Embedding pour Qwen3-Embedding absent, "
        "nommé d'après l'option, la raison invitant à cliquer",
        f"{label} · {button.get_attribute('aria-label')} · {option.get('download')}",
    )
    seq = r.ev.mark()
    button.click()
    r.ev.wait("session_state", seq, lambda p: p["state"] == "download", 10)
    stop = row.locator(f'button.rag-download-stop[data-target="{target}"]')
    line = row.locator(f'.rag-chain-download[data-target="{target}"]')
    progress = line.locator(".rag-chain-download-progress")

    def outcome() -> dict[str, Any] | None:
        stopped = [
            e
            for e in r.ev.since(seq, "effect_applied")
            if e["payload"].get("effect") == "model_download_stopped"
        ]
        return (stopped or r.ev.since(seq, "harness_error") or [None])[0]

    # While it downloads (unless, offline, it already failed): the progress and the stage's
    # « Arrêter » in place of the button, the page's « Arrêter » active too.
    shown, _ = r.poll(lambda: outcome() is not None or stop.is_visible(), 5)
    clicked = False
    if outcome() is None:
        during = {
            "progress": progress.is_visible() and bool(progress.inner_text().strip()),
            "stop": stop.is_visible(),
            "page_stop": page.locator("#rag-stop").is_enabled(),
        }
        r.check(
            shown and all(during.values()),
            "lot 5c-4 : pendant le téléchargement, progression et « Arrêter » dans l'étape, "
            "« Arrêter » de la page actif",
            str(during),
        )
        with contextlib.suppress(PlaywrightTimeout):
            stop.click(timeout=2000)
            clicked = True

    ended, _ = r.poll(lambda: outcome() is not None, 30)
    r.ev.wait("session_state", seq, lambda p: p["state"] == "idle", 30)
    event = outcome() or {}
    notice = row.locator(".rag-chain-download-notice")
    expect(notice).to_contain_text("modèle d'embedding", timeout=5000)
    # B1: the outcome said on the line, no line selected.
    expect(notice).to_be_visible(timeout=5000)
    expect(page.locator("#rag-seq .rag-seq-step.is-selected")).to_have_count(0)
    expect(button).to_be_enabled(timeout=5000)
    part = list((r.stack.data_dir / "models").rglob("*.part"))
    r.check(
        ended
        and (not clicked or event.get("payload", {}).get("effect") == "model_download_stopped")
        and event.get("component") == "rag_lab.embedding"
        and event.get("brick") is None
        and event.get("context_id") == "rag_lab"
        and not [e for e in r.ev.since(seq) if e.get("brick") == "rag"]
        and not part,
        "lot 5c-4 : clic, état download, « Arrêter » de l'étape ; issue (arrêt ou échec hors "
        "ligne) tracée hors de la brique, dite dans l'étape, bouton de nouveau actif, aucun .part",
        f"{event.get('kind')} · {event.get('component')} · arrêt cliqué : {clicked} · "
        f"{notice.inner_text()[:160]} · {part}",
    )


def _rag_lab(r: Run, errors: list[str]) -> None:
    page = r.page
    r.goto_app()
    r.wait_idle()
    # (1) The link, whole in the shared bar (story 2 of 2026-09-30), which stays on one line.
    link = page.locator('.site-nav a[href="/rag"]')
    r.check(
        link.is_visible() and link.inner_text() == "RAG",
        "barre commune : lien « RAG » visible, entier, vers /rag",
        link.inner_text(),
    )
    ok, detail = _bar_fits(r)
    r.check(
        ok, "barre commune et barre de l'atelier entières, sur une ligne, à 1600 × 1000", detail
    )

    # (2) Lot 5a: the three views, the sequence BUILD then RUN, the architecture's tiles.
    link.click()
    page.wait_for_url("**/rag")
    expect(page.locator("body[data-rag-ready]")).to_be_attached(timeout=10_000)
    page.evaluate("() => localStorage.removeItem('wavestack.ragLab.mode')")
    page.reload()
    expect(page.locator("body[data-rag-ready]")).to_be_attached(timeout=10_000)
    r.check(
        page.locator('#rag-modes [data-mode="play"]').get_attribute("aria-pressed") == "true"
        and page.locator("#rag-reset-chain").is_hidden()
        and not page.locator("#rag-seq .rag-seq-controls").count(),
        "/rag s'ouvre en « Dérouler » : ni éditeur ni « Revenir à la chaîne livrée »",
    )
    boxes = page.evaluate(_RAG_VIEWS_JS)
    r.check(
        boxes["views"]["h"] <= 1000 and boxes["focus"]["l"] > boxes["arch"]["r"],
        "Dérouler : les trois vues tiennent dans 1 000 px de haut",
        str(boxes["views"]),
    )
    _rag_mode(r, "compose")
    names = page.locator("#rag-seq .rag-seq-name").all_inner_texts()
    build = page.locator("#rag-seq-build .rag-seq-step").count()
    run_rows = page.locator("#rag-seq-run .rag-seq-step").count()
    bands = [page.inner_text(f"#rag-phase-{p}") for p in ("build", "run")]
    r.check(
        names == RAG_LAB_SEQUENCE
        and (build, run_rows) == (4, 6)
        and bands[0].startswith("BUILD")
        and "Indexing" in bands[0]
        and bands[1].startswith("RUN")
        and "Retrieval" in bands[1],
        "séquence : 10 lignes, 4 sous « BUILD · Indexing », 6 sous « RUN · Retrieval »",
        f"{names} · {bands}",
    )
    kinds = _chain_kinds(r)
    tiles = page.locator("#rag-arch .rag-arch-name").all_inner_texts()
    groups = page.locator("#rag-arch .rag-arch-group").count()
    r.check(
        kinds == RAG_LAB_STAGES_KINDS and tiles == RAG_LAB_TILES and groups == 3,
        "Composer : une ligne-éditeur par étape de la chaîne ; architecture en trois groupes, "
        "neuf tuiles (Documents… Réponse)",
        f"{kinds} · {tiles}",
    )
    boxes = page.evaluate(_RAG_VIEWS_JS)
    seq, arch, focus = boxes["seq"], boxes["arch"], boxes["focus"]
    r.check(
        seq["r"] < arch["l"]
        and arch["r"] < focus["l"]
        and abs(seq["t"] - focus["t"]) < 40
        and boxes["scroll"] <= 0,
        "Composer : séquence, architecture et focus côte à côte, sans défilement horizontal",
        str(boxes),
    )
    options = {kind: _option_label(r, kind) for kind in ("embedding", "vector_store", "rerank")}
    subs = page.eval_on_selector_all(
        "#rag-arch .rag-arch-tile",
        "ts => Object.fromEntries(ts.map(t => [t.dataset.component,"
        " t.querySelector('.rag-arch-sub').textContent]))",
    )
    r.check(
        options
        == {
            "embedding": "Faux embedding (e2e)",
            "vector_store": "sqlite-vec",
            "rerank": "Faux reranker (e2e)",
        }
        and subs.get("embedding_model") == "Faux embedding (e2e)"
        and subs.get("reranker") == "Faux reranker (e2e)",
        "chaque ligne nomme son option livrée ; les tuiles Embedding model et Reranker aussi",
        f"{options} · {subs}",
    )
    # Lot 5c-1: the models of [[rag_lab.embeddings]] in the Embedding's select, after the
    # brick's model and fastembed; their files are not on the e2e workstation: unavailable,
    # the reason naming the file under the models folder.
    choices = _seq_row(r, "embedding").evaluate(
        "row => [...row.querySelectorAll('select.rag-option option')].map(o =>"
        " ({ value: o.value, disabled: o.disabled, title: o.title }))"
    )
    e5 = next((c for c in choices if c["value"] == "multilingual-e5-small"), {})
    notes = _seq_row(r, "embedding").locator(".rag-chain-unavailable").all_inner_texts()
    r.check(
        [c["value"] for c in choices][:2] == ["declared", "fastembed"]
        and "qwen3-embedding-0.6b" in [c["value"] for c in choices]
        and e5.get("disabled") is True
        and "embedding/multilingual-e5-small-q8_0.gguf" in e5.get("title", "")
        and any("embedding/multilingual-e5-small-q8_0.gguf" in n for n in notes),
        "Embedding : multilingual-e5-small et Qwen3-Embedding dans le choix, indisponibles "
        "sans leur fichier, la raison nommant embedding/…",
        f"{choices} · {notes}",
    )
    # Lot 5c-2: the models of [[rag_lab.rerankers]] in the Reranking's select, after the
    # brick's model; Qwen3-Reranker's file is not on the e2e workstation: unavailable, the
    # reason naming the file under the models folder.
    choices = _seq_row(r, "rerank").evaluate(
        "row => [...row.querySelectorAll('select.rag-option option')].map(o =>"
        " ({ value: o.value, disabled: o.disabled, title: o.title }))"
    )
    qwen = next((c for c in choices if c["value"] == "qwen3-reranker-0.6b"), {})
    notes = _seq_row(r, "rerank").locator(".rag-chain-unavailable").all_inner_texts()
    r.check(
        [c["value"] for c in choices] == ["declared", "qwen3-reranker-0.6b"]
        and qwen.get("disabled") is True
        and "reranker/qwen3-reranker-0.6b-q8_0.gguf" in qwen.get("title", "")
        and any("reranker/qwen3-reranker-0.6b-q8_0.gguf" in n for n in notes),
        "Reranking : Qwen3-Reranker dans le choix après le reranker de la brique, indisponible "
        "sans son fichier, la raison nommant reranker/…",
        f"{choices} · {notes}",
    )
    _rag_lab_arch_downloads(r)
    _rag_lab_download(r)
    r.check(
        "Même modèle" in page.inner_text('#rag-seq [data-step="embed_query"]'),
        "Embedding de la question : « même modèle que l'Embedding des chunks »",
    )
    r.check(
        page.locator("nav.site-nav a[aria-current=page]").inner_text() == "RAG"
        and page.title() == "WaveStack — Atelier RAG"
        and page.locator("h1").inner_text().startswith("Atelier RAG")
        and page.locator("select[data-theme-picker]").count() == 1
        and not page.locator("#rag-compare, #rag-chain-b, #rag-comparison").count()
        and not _site_nav_problems(r),
        "/rag : barre commune entière, « RAG » courant, titre « Atelier RAG », plus de "
        "comparaison A/B",
    )
    generation = page.locator('#rag-seq [data-step="generation"]')
    r.check(
        r.css(generation, "border-left-color") == r.token_color("--color-ink-fill"),
        "la ligne Generation repose sur l'encre (ink-fill)",
        r.css(generation, "border-left-color"),
    )
    # Each line opens its focus on a click, with its wires to the components it calls on.
    catalog = r.api("GET", "/api/rag_lab").json()["catalog"]
    uses = {s["key"]: [u["component"] for u in s["uses"]] for s in catalog["steps"]}
    keys = page.eval_on_selector_all("#rag-seq .rag-seq-step", "rs => rs.map(r => r.dataset.step)")
    wrong = []
    for key, name in zip(keys, RAG_LAB_SEQUENCE, strict=True):
        shown = _focus_of(r, key)
        if (
            shown["step"] != key
            or shown["name"] != name
            or len(shown["explain"]) < 40
            or shown["uses"] != uses[key]
            or sorted(shown["wires"]) != sorted(uses[key])
            or "Lancez la chaîne" not in shown["text"]
        ):
            wrong.append(f"{key}: {shown}")
    r.check(
        not wrong and len(keys) == 10,
        "Composer : chaque ligne ouvre son focus au clic (nom, explication, composants "
        "sollicités, une flèche par composant), sans chiffres de run",
        "; ".join(wrong)[:400],
    )
    shown = _focus_of(r, "rerank")
    selected = page.locator('#rag-seq [data-step="rerank"]')
    r.check(
        "is-selected" in (selected.get_attribute("class") or "")
        and shown["uses"] == ["question", "reranker"]
        and shown["wires"] == ["question", "reranker"]
        and "calibré à sa façon" in shown["explain"]
        and "seul l'ordre que chacun donne compte" in shown["explain"],
        "Reranking sélectionné : flèches vers Question (lu) et Reranker (appelé) ; "
        "l'explication dit que les scores de rerankers différents ne se comparent pas (lot 5c-2)",
        str(shown)[:300],
    )
    page.locator('#rag-seq [data-step="chunking"] .rag-seq-head').focus()
    page.keyboard.press("Enter")
    expect(page.locator("#rag-focus")).to_have_attribute("data-step", "chunking")
    light = _contrast_sweep(r, ["main", "nav.site-nav"])
    _pick_theme(page, "dark")
    dark = _contrast_sweep(r, ["main", "nav.site-nav"])
    _pick_theme(page, "system")
    r.check(not light and not dark, "/rag : contrastes AA en clair et en sombre", str(light + dark))
    r.shot("55-atelier-rag-chaine")
    _rag_lab_views(r)

    # (3) A run on the question: each stage, its excerpts, its duration and its memory.
    page.evaluate(_WATCH_STATUSES_JS)
    ended, seq = _rag_lab_run(r)
    failed = [
        (e["payload"].get("kind"), e["payload"].get("error_text"))
        for e in r.ev.since(seq, "rag_lab_stage_ended")
        if e["payload"].get("status") not in ("ok", None)
    ]
    r.check(
        ended["payload"]["status"] == "ok",
        "exécution de la chaîne livrée terminée",
        f"{ended['payload'].get('status')} {failed}",
    )
    started = {e["payload"]["kind"] for e in r.ev.since(seq, "rag_lab_stage_started")}
    r.check(
        started == set(RAG_LAB_STAGES_KINDS),
        "une paire started/ended par étape, la génération comprise (lot 5c-3)",
        str(sorted(started)),
    )
    _open_details(r)
    statuses = page.evaluate("() => window.__ragStatuses")
    figures = [
        _result_card(r, kind).locator(".rag-stage-figures").inner_text()
        for kind in RAG_LAB_STAGES_KINDS[:-1]
    ]
    r.check(
        any(s.startswith("en cours") for s in statuses)
        and all(re.search(r"\d+ ms", f) and re.search(r"\d+ Mo", f) for f in figures),
        "détail : chaque carte passe de « en cours » à une durée en ms et une mémoire en Mo",
        f"{sorted(set(statuses))[:6]} · {figures[0]!r}",
    )
    cfg_candidates = 8
    search = _stage_ended(r, seq, "vector_search")
    rows = _result_card(r, "vector_search").locator("tbody tr")
    r.check(
        len(search.get("items", [])) == cfg_candidates
        and rows.count() == cfg_candidates
        and [i["rank"] for i in search["items"]] == list(range(1, cfg_candidates + 1))
        and all(
            re.match(r"\d,\d{3}$", rows.nth(i).locator("td").nth(3).inner_text())
            for i in range(rows.count())
        ),
        "Dense retrieval : 8 extraits (rag_rerank_candidates) avec rang et score",
        str([(i["rank"], i["doc_id"], i["score"]) for i in search.get("items", [])]),
    )
    rerank = _stage_ended(r, seq, "rerank")
    rows = _result_card(r, "rerank").locator("tbody tr")
    befores = [rows.nth(i).locator("td").nth(1).inner_text() for i in range(rows.count())]
    r.check(
        rerank.get("status") == "ok"
        and len(rerank.get("items", [])) == cfg_candidates
        and all(b.strip("↑↓ ").isdigit() for b in befores)
        and sorted(i["before"] for i in rerank["items"]) == list(range(1, cfg_candidates + 1)),
        "Reranking : pour chaque extrait, le rang avant et le rang après",
        str([(i["rank"], i["before"], i["doc_id"]) for i in rerank.get("items", [])]),
    )
    facts = _result_card(r, "rerank").locator(".rag-stage-facts").inner_text()
    r.check(
        "lecture du score" in facts.casefold() and "sigmoïde du logit" in facts,  # dt uppercased
        "Reranking : le détail dit comment le score est lu (sigmoïde du logit, lot 5c-2)",
        facts[:300],
    )
    context = _stage_ended(r, seq, "context")
    output = _result_card(r, "context").locator(".rag-stage-output").inner_text()
    r.check(
        len(context.get("items", [])) == 3
        and output.count("Extrait ") == 3
        and "Extrait 1 — " in output
        and "Extrait 3 — " in output,
        "Prompt augmentation : les 3 extraits (top_k) au format de la brique",
        output[:200],
    )
    # Lot 5c-3: the workshop's active model answers; the card folds the prompt sent.
    generation = _stage_ended(r, seq, "generation")
    gen = _result_card(r, "generation")
    answer = generation.get("output_text") or ""
    deltas = [e for e in r.ev.since(seq, "model_delta") if e.get("context_id") == "rag_lab"]
    r.check(
        generation.get("status") == "ok"
        and answer.strip()
        and RAG_LAB_QUESTION in (generation.get("prompt_text") or "")
        and " ".join(answer.split())[:40]
        in " ".join(gen.locator(".rag-stage-output").inner_text().split())
        and gen.locator("details.rag-prompt").count() == 1
        and deltas
        and all(e.get("turn_id") is None for e in deltas),
        "Generation : le modèle actif répond (model_delta du contexte rag_lab, sans tour), "
        "le prompt envoyé replié dans la carte",
        f"{generation.get('status')} {answer[:120]!r} {generation.get('error_text')}",
    )
    # In « Dérouler », the focus shows what the step received and produced.
    _rag_mode(r, "play")
    shown = _focus_of(r, "vector_search")
    pills = page.eval_on_selector_all(
        "#rag-seq .rag-seq-status", "ps => ps.filter(p => !p.hidden).map(p => p.textContent)"
    )
    r.check(
        shown["rows"] == cfg_candidates
        and re.search(r"\d+ ms", shown["text"]) is not None
        and len(pills) == len(RAG_LAB_SEQUENCE),
        "Dérouler : le focus de Dense retrieval montre ses 8 candidats et sa durée ; une "
        "pastille d'état par ligne",
        f"{shown['rows']} lignes · {pills}",
    )
    r.check(not errors, "aucune pageerror", str(errors[:3]))
    r.shot("56-atelier-rag-resultats", full_page=True)

    # (4) Reloaded: the same run, from `last_run`.
    run_id = ended["payload"]["run_id"]
    page.reload()
    expect(page.locator("body[data-rag-ready]")).to_be_attached(timeout=10_000)
    _open_details(r)
    reloaded = page.locator("#rag-details .rag-stage-card").count()
    summary = page.inner_text("#rag-run-summary")
    state = r.api("GET", "/api/rag_lab").json()
    r.check(
        reloaded == len(RAG_LAB_STAGES)
        and RAG_LAB_QUESTION in summary
        and state["last_run"][0]["payload"]["run_id"] == run_id
        and page.locator('#rag-modes [data-mode="play"]').get_attribute("aria-pressed") == "true",
        "après rechargement, le même run se réaffiche (last_run), le mode est gardé",
        f"{reloaded} cartes · {summary}",
    )

    # (5) A workshop turn running: the run is refused, 409 with the reason.
    seq = r.ev.mark()
    r.api("POST", "/api/intentions/send", {"message": "Explique le harnais [lent] [long]"})
    r.ev.wait("model_first_token", seq, timeout=20)
    refused = r.api("POST", "/api/intentions/rag_lab_run", {"question": RAG_LAB_QUESTION})
    button = page.locator("#rag-run")
    expect(button).to_be_disabled(timeout=5000)
    r.check(
        refused.status_code == 409 and "tour" in refused.json().get("detail", ""),
        "tour de l'atelier en cours : rag_lab_run répond 409 avec la raison, « Lancer » grisé",
        f"{refused.status_code} {refused.text[:160]}",
    )
    r.api("POST", "/api/intentions/stop")
    r.ev.wait("turn_ended", seq, timeout=30)
    expect(button).to_be_enabled(timeout=10_000)
    _rag_mode(r, "compose")
    _rag_lab_compare(r)
    _rag_lab_alt(r)
    _rag_lab_hybrid(r)
    _rag_lab_presets(r)

    # (6) Lot 5c-1: the main page's journal reads the workshop's events (one chain per run,
    # no lane): a summary per stage ended, its name read in `rag_lab_run_started`'s stages.
    r.goto_app()
    r.wait_idle()
    page.click("#event-log-head")
    try:
        expect(page.locator("#event-log-list")).to_be_visible(timeout=5000)
        rows = [x for x in page.evaluate(_LOG_ROWS_JS) if x["kind"] == "rag_lab_stage_ended"]
        r.check(
            bool(rows)
            and all(x["summary"].strip() for x in rows)
            and any(x["summary"].startswith("Dense retrieval · ") for x in rows)
            and not errors,
            "page principale : le journal résume chaque rag_lab_stage_ended (« Dense retrieval "
            "· … »), sans pageerror",
            f"{rows[:3]} · {errors[:3]}",
        )
    finally:
        page.click("#event-log-head")


# Lot 5a-2: what « Dérouler » shows now: the steps, tiles and band visible, the tiles just
# arrived, the blocks lit, the wires, the stepper, the legend and the focus.
_RAG_PLAY_JS = """() => {
  const visible = (n) => getComputedStyle(n).visibility !== 'hidden';
  const tiles = [...document.querySelectorAll('#rag-arch .rag-arch-tile')];
  const focus = document.getElementById('rag-focus');
  const step = focus.dataset.step;
  const row = step ? document.querySelector(`#rag-seq .rag-seq-step[data-step="${step}"]`) : null;
  const bar = document.querySelector('#rag-stepper .diagram-stepper');
  const fresh = tiles.filter(t => t.classList.contains('is-new'));
  return {
    rows: [...document.querySelectorAll('#rag-seq .rag-seq-step')].filter(visible)
      .map(r => r.dataset.step),
    build: [...document.querySelectorAll('#rag-seq-build .rag-seq-step')].filter(visible).length,
    tiles: tiles.filter(visible).map(t => t.dataset.component),
    fresh: fresh.map(t => t.dataset.component),
    animation: fresh.map(t => getComputedStyle(t).animationName),
    lit: [...document.querySelectorAll('#rag-views .is-active')]
      .map(n => n.dataset.step || n.dataset.component).sort(),
    run_band: visible(document.getElementById('rag-phase-run')),
    focus: step,
    position: bar?.querySelector('.diagram-step-position').textContent ?? '',
    prev: bar?.querySelector('.diagram-step-prev').getAttribute('aria-disabled') === 'true',
    next: bar?.querySelector('.diagram-step-next').getAttribute('aria-disabled') === 'true',
    legend: document.getElementById('rag-legend').textContent,
    stepper: !document.getElementById('rag-stepper').hidden,
    live_button: !bar?.querySelector('.diagram-step-live').hidden,
    wires: [...document.querySelectorAll('#rag-views .diagram-path-core')]
      .map(p => p.dataset.component).sort(),
    flowing: document.querySelectorAll('#rag-views .diagram-path-core.is-flow').length,
    pill: row?.querySelector('.rag-seq-status')?.textContent ?? '',
    run: row?.dataset.run ?? '',
    error: focus.querySelector('.rag-stage-error')?.textContent ?? '',
    generation_top: document.querySelector('#rag-seq [data-step="generation"]')
      ?.getBoundingClientRect().top ?? 0,
    height: document.getElementById('rag-views').getBoundingClientRect().height,
  };
}"""

# Every state of « Dérouler » a run goes through, recorded as the views change (a frame may
# last one render only): the step shown, its pill, the blocks lit, the wires drawn.
_WATCH_PLAY_JS = """() => {
  window.__ragPlay = [];
  const note = () => {
    const step = document.getElementById('rag-focus').dataset.step;
    const row = step
      ? document.querySelector(`#rag-seq .rag-seq-step[data-step="${step}"]`) : null;
    window.__ragPlay.push({
      step,
      pill: row?.querySelector('.rag-seq-status')?.textContent ?? '',
      lit: [...document.querySelectorAll('#rag-views .is-active')]
        .map(n => n.dataset.step || n.dataset.component).sort(),
      wires: [...document.querySelectorAll('#rag-views .diagram-path-core')]
        .map(p => p.dataset.component).sort(),
      flowing: document.querySelectorAll('#rag-views .diagram-path-core.is-flow').length,
      // Lot 5c-3: the generation's answer in the focus, live (or its waiting text).
      answer: document.querySelector('#rag-focus .rag-answer-text')?.textContent ?? null,
      waiting: Boolean(document.querySelector('#rag-focus .rag-answer-text.is-waiting')),
    });
  };
  window.__ragPlayObserver?.disconnect();
  window.__ragPlayObserver = new MutationObserver(note);
  window.__ragPlayObserver.observe(document.getElementById('rag-views'),
    { childList: true, subtree: true, characterData: true, attributes: true,
      attributeFilter: ['class'] });
}"""


def _rag_play(r: Run) -> dict[str, Any]:
    time.sleep(0.15)  # the wires, drawn at the next frame
    return r.page.evaluate(_RAG_PLAY_JS)


def _rag_lab_views(r: Run) -> None:
    """Lot 5a-2, « Dérouler »: the guided tour without a run (image 1: Documents and its tile
    alone; each ▶ the next step and the tiles it calls on first, arriving, none moving with
    reduced motion; the steps after it keep their place); a run, from « Composer »: « Lancer »
    passes into « Dérouler », the steps arrive one by one, the step running lit with its
    components, its wires flowing; at the end, Generation « terminée » with the model's answer
    (lot 5c-3) and « rejouez avec ◀ ▶ »; ◀ ▶ replay; the same state after a reload; a step in
    error: its ✖ and its error in the focus."""
    page = r.page
    state = r.api("GET", "/api/rag_lab").json()
    uses = {s["key"]: [u["component"] for u in s["uses"]] for s in state["catalog"]["steps"]}
    texts = state["content"]
    keys = ["documents", "chunking", "embed_passages", "vector_store", "question", "embed_query"]
    keys += ["vector_search", "rerank", "context", "generation"]
    prev = page.locator("#rag-stepper .diagram-step-prev")
    nxt = page.locator("#rag-stepper .diagram-step-next")

    # (a) The guided tour: no run of this chain yet.
    _rag_mode(r, "play")
    first = _rag_play(r)
    r.check(
        first["stepper"]
        and first["rows"] == ["documents"]
        and first["tiles"] == ["documents"]
        and not first["run_band"]
        and first["prev"]
        and not first["next"]
        and first["position"] == "Étape 1 / 10"
        and first["legend"] == texts["legend_tour_text"]
        and first["focus"] == "documents"
        and first["lit"] == ["documents", "documents"]
        and not first["live_button"]
        and "Lancez la chaîne" in page.inner_text("#rag-focus"),
        "Dérouler sans run : image 1, Documents seule et sa tuile, allumées, ◀ grisé, "
        "« Visite guidée », pas de « Suivre le direct »",
        str({k: first[k] for k in ("rows", "tiles", "position", "legend", "lit")}),
    )
    nxt.click()
    second = _rag_play(r)
    r.check(
        second["rows"] == ["documents", "chunking"]
        and second["tiles"] == ["documents", "chunks"]
        and second["fresh"] == ["chunks"]
        and second["animation"] == ["rag-appear"]
        and second["lit"] == ["chunking", "chunks", "documents"]
        and second["wires"] == sorted(uses["chunking"])
        and not second["flowing"]
        and not second["prev"],
        "▶ : Chunking et la tuile Chunks arrivent (is-new), Chunking allumé avec Documents et "
        "Chunks, ses deux flèches",
        str({k: second[k] for k in ("rows", "tiles", "fresh", "lit", "wires")}),
    )
    nxt.click()
    third = _rag_play(r)
    page.emulate_media(reduced_motion="reduce")
    try:
        nxt.click()
        fourth = _rag_play(r)
    finally:
        page.emulate_media(reduced_motion="no-preference")
    r.check(
        fourth["build"] == 4
        and fourth["rows"] == keys[:4]
        and "vector_store" not in third["tiles"]
        and "vector_store" in fourth["tiles"]
        and fourth["fresh"] == ["vector_store"]
        and fourth["animation"] == ["none"]
        and not fourth["run_band"]
        and fourth["position"] == "Étape 4 / 10",
        "▶ trois fois : quatre étapes BUILD visibles, la tuile Vector store apparaît à la "
        "quatrième (sans mouvement avec prefers-reduced-motion), bandeau RUN encore masqué",
        str({k: fourth[k] for k in ("rows", "tiles", "fresh", "animation", "position")}),
    )
    for _ in range(len(keys) - 4):  # ▶ up to the last image
        nxt.click()
    last = _rag_play(r)
    page.locator('#rag-seq [data-step="chunking"] .rag-seq-head').click()
    clicked = _rag_play(r)
    r.check(
        last["rows"] == keys
        and last["run_band"]
        and abs(last["generation_top"] - first["generation_top"]) < 1
        and abs(last["height"] - first["height"]) < 1
        and clicked["position"] == "Étape 2 / 10"
        and clicked["focus"] == "chunking",
        "visite : à la dernière image tout est visible, aux mêmes places qu'à l'image 1 ; un "
        "clic sur une ligne montre son image",
        f"{last['generation_top']} / {first['generation_top']} · {clicked['position']}",
    )

    # (b) A run, launched from « Composer »: it passes into « Dérouler », live.
    _rag_mode(r, "compose")
    page.evaluate(_WATCH_PLAY_JS)
    ended, seq = _rag_lab_run(r)
    states = page.evaluate(
        "() => { window.__ragPlayObserver.disconnect(); return window.__ragPlay; }"
    )
    shown = [s["step"] for s in states if s["step"]]
    order = [k for i, k in enumerate(shown) if i == 0 or k != shown[i - 1]]
    indices = [keys.index(k) for k in order if k in keys]
    running = [s for s in states if s["pill"].startswith("en cours") and s["step"] in uses]
    unlit = [s for s in running if s["lit"] != sorted([s["step"], *uses[s["step"]]])]
    # The wires are drawn at the next frame: a state whose wires are its step's.
    drawn = [s for s in running if s["wires"] and s["wires"] == sorted(uses[s["step"]])]
    r.check(
        ended["payload"]["status"] == "ok"
        and len(set(order)) >= 3
        and indices == sorted(indices)
        and order[-1] == "generation"
        and running
        and not unlit
        and all(s["flowing"] == len(s["wires"]) for s in drawn),
        "Lancer passe en Dérouler : les étapes arrivent une à une ; l'étape en cours (« en "
        "cours ») est allumée avec ses composants, ses flèches animées",
        f"{order} · en cours : {sorted({s['step'] for s in running})} · "
        f"flèches vues en cours : {len(drawn)} · {unlit[:2]} · "
        f"{[s for s in drawn if s['flowing'] != len(s['wires'])][:2]}",
    )
    # Lot 5c-3: while the generation runs, its pill counts tokens (« n / N tokens ») and the
    # focus shows the answer as it comes (or that the model reasons).
    tokens_form = texts["progress_tokens_text"].replace("{done}", "").replace("{total}", "")
    unit = tokens_form.split("/")[-1].strip()
    live = [
        s
        for s in states
        if s["step"] == "generation"
        and s["pill"].startswith("en cours")
        and re.search(rf"\d+ / [\d\u202f\u00a0 ]+ {re.escape(unit)}$", s["pill"])
        and (
            (s["answer"] and s["answer"].strip() and not s["waiting"])
            or s["answer"] == texts["answer_reasoning_text"]
        )
    ]
    r.check(
        bool(live),
        "Generation en cours : pastille « n / N tokens » et réponse en direct dans le focus "
        "(lot 5c-3)",
        str(
            [
                (s["pill"], (s["answer"] or "")[:40], s["waiting"])
                for s in states
                if s["step"] == "generation"
            ][:6]
        ),
    )
    end = _rag_play(r)
    r.check(
        end["rows"] == keys
        and end["focus"] == "generation"
        and end["pill"].startswith(texts["status"]["ok_text"])
        and end["legend"] == texts["legend_done_text"]
        and "◀ ▶" in end["legend"]
        and end["position"] == "Étape 10 / 10"
        and end["next"]
        and end["live_button"]
        and not end["flowing"],
        "fin de run : dernière image Generation « terminée », légende « rejouez avec ◀ ▶ »",
        str({k: end[k] for k in ("focus", "pill", "legend", "position")}),
    )
    # Lot 5c-3: the focus shows the prompt sent (folded) and the answer; the Réponse tile, the
    # answer's first lines (the whole in its tooltip).
    focus_answer = page.locator("#rag-focus .rag-answer-text").inner_text()
    tile = page.locator('#rag-arch .rag-arch-tile[data-component="answer"] .rag-arch-sub')
    r.check(
        focus_answer.strip()
        and page.locator("#rag-focus details.rag-prompt").count() == 1
        and (tile.get_attribute("title") or "").strip() == focus_answer.strip(),
        "fin de run : le focus montre le prompt envoyé (replié) et la réponse ; la tuile Réponse "
        "porte la réponse",
        f"{focus_answer[:80]!r} · {(tile.get_attribute('title') or '')[:80]!r}",
    )
    prev.click()
    back = _rag_play(r)
    r.check(
        back["focus"] == "context"
        and back["rows"] == keys[:-1]
        and "llm" not in back["tiles"]
        and "answer" not in back["tiles"]
        and back["lit"] == sorted(["context", *uses["context"]])
        and back["legend"] == texts["legend_replay_text"]
        and re.search(r"\d+ ms", page.inner_text("#rag-focus")) is not None,
        "◀ : Prompt augmentation montrée avec ses chiffres, Generation masquée (et ses tuiles "
        "LLM, Réponse), « Relecture »",
        str({k: back[k] for k in ("focus", "rows", "tiles", "legend")}),
    )
    nxt.click()
    again = _rag_play(r)

    # (c) Reloaded: the same state, from `last_run`, straight to the last image.
    page.reload()
    expect(page.locator("body[data-rag-ready]")).to_be_attached(timeout=10_000)
    reloaded = _rag_play(r)
    same = ("rows", "tiles", "focus", "pill", "legend", "position", "lit", "wires")
    r.check(
        again["focus"] == "generation"
        and all(reloaded[k] == end[k] for k in same)
        and not reloaded["fresh"],
        "▶ revient à Generation ; après rechargement, le même état depuis last_run, sur la "
        "dernière image",
        str({k: (reloaded[k], end[k]) for k in same if reloaded[k] != end[k]})[:300],
    )
    # The steps that read a stage: the question for the question and its Embedding, no
    # excerpts for the latter, and none of them claims its stage's duration.
    # From the last one back: a line shown hides the lines after it.
    read = {key: _focus_of(r, key) for key in ("embed_query", "question", "documents")}
    r.check(
        all(RAG_LAB_QUESTION in read[k]["text"] for k in ("question", "embed_query"))
        and read["embed_query"]["rows"] == 0
        and read["documents"]["step"] == "documents"
        and not any(re.search(r"\d+ ms", f["text"]) for f in read.values()),
        "Dérouler : Documents, Question et l'Embedding de la question montrent ce qu'ils "
        "lisent (la question), sans extraits ni durée empruntée à leur étape",
        str({k: f["text"][-160:] for k, f in read.items()})[:400],
    )

    # (d) A step in error (the fake reranker breaks down): the run lands on it, ✖, its error
    # in the focus; the chain went on with the search's order (a soft failure).
    ended, seq = _rag_lab_run(r, f"{RAG_LAB_QUESTION} [reranker-en-panne]")
    failed = _rag_play(r)
    nxt.click()
    after = _rag_play(r)
    r.check(
        _stage_ended(r, seq, "rerank").get("status") == "error"
        and failed["focus"] == "rerank"
        and failed["run"] == "error"
        and failed["pill"].startswith(texts["status"]["error_text"])
        and bool(failed["error"])
        and failed["rows"] == keys[:8]
        and after["focus"] == "context",
        "étape en erreur : le run s'arrête sur Reranking, pastille ✖ et l'erreur dans le "
        "focus ; ▶ montre la suite",
        str({k: failed[k] for k in ("focus", "run", "pill", "error", "rows")})[:300],
    )
    page.fill("#rag-question", RAG_LAB_QUESTION)

    # (e) Composer: the last run is this chain's, its figures are in « Dérouler »; a setting
    # edited, « Dérouler » gives the edited chain's guided tour, without the run's figures.
    _rag_mode(r, "compose")
    hint = _focus_of(r, "chunking")["text"]
    _set_stage(r, "context", top_k=2)
    time.sleep(0.4)
    _rag_mode(r, "play")
    tour = _rag_play(r)
    pills = page.eval_on_selector_all(
        "#rag-seq .rag-seq-status", "ps => ps.filter(p => !p.hidden).length"
    )
    r.check(
        texts["focus_play_hint_text"] in hint
        and tour["legend"] == texts["legend_tour_text"]
        and tour["position"] == f"Étape 1 / {len(keys)}"
        and not pills
        and "Lancez la chaîne" in page.inner_text("#rag-focus"),
        "Composer après un run : le focus renvoie à Dérouler ; un réglage changé, Dérouler "
        "repart en visite guidée, sans pastille ni chiffres",
        f"{hint[-120:]!r} · {tour['legend']} · {tour['position']} · {pills} pastilles",
    )
    _rag_mode(r, "compose")
    page.locator("#rag-reset-chain").click()
    time.sleep(0.4)


def _chain_kinds(r: Run) -> list[str]:
    return r.page.eval_on_selector_all(
        "#rag-seq li.rag-chain-card", "rows => rows.map(c => c.dataset.kind)"
    )


def _add_stage(r: Run, label: str) -> None:
    r.page.locator("#rag-palette-a select").select_option(label=label)
    r.page.locator("#rag-palette-a .rag-palette-add").click()
    time.sleep(0.8)  # the session's verdict (`/api/rag_lab/validate`, after a 200 ms pause)


def _stage_button(r: Run, kind: str, label: str):
    return _seq_row(r, kind).get_by_role("button", name=label)


def _rag_lab_hybrid(r: Run) -> None:
    """Increment 4: the Reranking removed, BM25 added without a fusion (refused on its line,
    « Lancer » greyed), the Fusion added, the Reranking added back and moved after the Fusion
    by its buttons; a run: the Fusion gives each excerpt's rank in both searches and its RRF
    score. A Fusion moved before a search: refused, 409 if posted. Lot 5a: the sequence and
    the architecture follow (a Reranker tile only with the reranking)."""
    page = r.page
    page.locator("#rag-reset-chain").click()
    time.sleep(0.4)
    _stage_button(r, "rerank", "Retirer").click()
    tiles = page.locator("#rag-arch .rag-arch-tile").evaluate_all(
        "ts => ts.map(t => t.dataset.component)"
    )
    r.check(
        "reranker" not in tiles and "rerank" not in _chain_kinds(r),
        "sans reranking : plus de tuile Reranker",
        str(tiles),
    )
    _add_stage(r, "BM25")
    bm25 = _seq_row(r, "lexical_search")
    expect(bm25.locator(".rag-chain-refusal")).to_be_visible(timeout=5000)
    run = page.locator("#rag-run")
    r.check(
        "Deux recherches demandent une fusion après elles"
        in bm25.locator(".rag-chain-refusal").inner_text()
        and run.is_disabled()
        and "fusion" in (run.get_attribute("title") or ""),
        "BM25 sans fusion : la ligne BM25 dit « Deux recherches demandent une fusion après "
        "elles », « Lancer » désactivé",
        bm25.locator(".rag-chain-refusal").inner_text(),
    )
    _add_stage(r, "Reranking")
    _add_stage(r, "Fusion (RRF)")
    before = _chain_kinds(r)
    after_button = _stage_button(r, "rerank", "Déplacer après")
    after_button.focus()
    page.keyboard.press("Enter")  # by the keyboard, never by drag and drop
    time.sleep(0.8)
    kinds = _chain_kinds(r)
    names = page.locator("#rag-seq-run .rag-seq-name").all_inner_texts()
    r.check(
        before[3:7] == ["vector_search", "lexical_search", "rerank", "fusion"]
        and kinds[3:7] == ["vector_search", "lexical_search", "fusion", "rerank"]
        and names[2:6] == ["Dense retrieval", "BM25", "Fusion (RRF)", "Reranking"]
        and _stage_button(r, "rerank", "Déplacer après").is_disabled()
        and not page.locator("#rag-seq .rag-chain-refusal").count(),
        "Reranking déplacé après la Fusion au clavier (« Déplacer après ») : chaîne valide, la "
        "séquence suit l'ordre de la chaîne",
        f"{before} → {kinds} · {names}",
    )
    expect(run).to_be_enabled(timeout=5000)
    ended, seq = _rag_lab_run(r)
    _open_details(r)
    fusion = _stage_ended(r, seq, "fusion")
    items = fusion.get("items", [])
    ranks_ok = all(
        {s["kind"] for s in i["sources"]} == {"vector_search", "lexical_search"}
        and any(s["rank"] for s in i["sources"])
        for i in items
    )
    rows = _result_card(r, "fusion").locator("tbody tr")
    first_row = rows.first.inner_text() if rows.count() else ""
    r.check(
        ended["payload"]["status"] == "ok"
        and items
        and ranks_ok
        and "Dense retrieval :" in first_row
        and "BM25 :" in first_row
        and re.search(r"0,0\d{3}", first_row) is not None,
        "Fusion : le rang de chaque extrait dans les deux recherches et son score RRF",
        first_row.replace("\n", " | ")[:240],
    )
    r.shot("58-atelier-rag-hybride", full_page=True)
    _rag_mode(r, "compose")
    # The Fusion moved before a search: its line says why, and a POST anyway is refused.
    _stage_button(r, "fusion", "Déplacer avant").click()
    time.sleep(0.4)
    fusion_row = _seq_row(r, "fusion")
    expect(fusion_row.locator(".rag-chain-refusal")).to_be_visible(timeout=5000)
    chain = page.evaluate("() => JSON.parse(localStorage.getItem('wavestack.ragLab')).pipelines")
    refused = r.api(
        "POST", "/api/intentions/rag_lab_run", {"question": RAG_LAB_QUESTION, "pipelines": chain}
    )
    r.check(
        "Fusion" in fusion_row.locator(".rag-chain-refusal").inner_text()
        and run.is_disabled()
        and refused.status_code == 409
        and "« Fusion (RRF) »" in refused.json().get("detail", ""),
        "Fusion déplacée avant une recherche : la raison nomme la Fusion, 409 si l'on poste",
        f"{refused.status_code} {refused.text[:160]}",
    )
    page.locator("#rag-reset-chain").click()


def _rag_presets(r: Run) -> dict[str, dict[str, Any]]:
    """The ready-made architectures' row (Composer): each button's text, pressed, marked."""
    return r.page.eval_on_selector_all(
        "#rag-presets .rag-preset",
        "bs => Object.fromEntries(bs.map(b => [b.dataset.preset, { text: b.textContent,"
        " pressed: b.getAttribute('aria-pressed'), title: b.title,"
        " unavailable: b.classList.contains('is-unavailable') }]))",
    )


def _pressed_preset(r: Run) -> list[str]:
    return [k for k, v in _rag_presets(r).items() if v["pressed"] == "true"]


def _rag_lab_presets(r: Run) -> None:
    """Lot 5b: the ready-made architectures, in Composer only. The shipped chain is « RAG +
    reranking » (pressed); « RAG hybride » replaces the retrieval segment only (Dense
    retrieval, BM25, Fusion (RRF)), the chunk size and the `top_k` edited kept, the chain valid;
    reloaded, the chain kept and « RAG hybride » still pressed; a run: the Fusion shows both
    searches' ranks, `ok`. A segment composed by hand: none pressed. A preset that would not
    run (served unavailable by `page.route`): marked, still clickable."""
    page = r.page
    _rag_mode(r, "compose")
    page.locator("#rag-reset-chain").click()
    time.sleep(0.4)
    catalog = r.api("GET", "/api/rag_lab").json()["catalog"]
    served = {p["id"]: p for p in catalog.get("presets", [])}
    shown = _rag_presets(r)
    r.check(
        list(served) == ["dense", "hybrid", "rerank"]
        and all(p["available"] for p in served.values())
        and [s["kind"] for s in served["hybrid"]["segment"]]
        == ["vector_search", "lexical_search", "fusion"]
        and list(shown) == list(served)
        and all(shown[k]["text"] == served[k]["label_text"] for k in served)
        and all(served[k]["explain_text"] in shown[k]["title"] for k in served)
        and _pressed_preset(r) == ["rerank"]
        and page.locator("#rag-presets").is_visible(),
        "Composer : trois architectures toutes faites (catalog.presets), « RAG + reranking » "
        "pressé sur la chaîne livrée, l'explication en infobulle",
        f"{list(served)} · {shown}",
    )
    _set_stage(r, "chunking", chunk_max_chars=300)
    _set_stage(r, "context", top_k=2)
    _set_stage(r, "vector_search", candidates=5)  # back to its served value by the preset
    time.sleep(0.4)
    dense_id = _seq_row(r, "vector_search").get_attribute("data-stage-id")
    page.locator('#rag-presets .rag-preset[data-preset="hybrid"]').click()
    time.sleep(0.8)  # the session's verdict
    kinds = _chain_kinds(r)
    served_candidates = str(served["hybrid"]["segment"][0]["params"]["candidates"])
    candidates = (
        _seq_row(r, "vector_search").locator('input[data-param="candidates"]').input_value()
    )
    kept_id = _seq_row(r, "vector_search").get_attribute("data-stage-id")
    names = page.locator("#rag-seq-run .rag-seq-name").all_inner_texts()
    chunk = _seq_row(r, "chunking").locator('input[data-param="chunk_max_chars"]').input_value()
    top_k = _seq_row(r, "context").locator('input[data-param="top_k"]').input_value()
    r.check(
        kinds
        == [
            "chunking",
            "embedding",
            "vector_store",
            "vector_search",
            "lexical_search",
            "fusion",
            "context",
            "generation",
        ]
        and names[2:5] == ["Dense retrieval", "BM25", "Fusion (RRF)"]
        and (chunk, top_k) == ("300", "2")
        and candidates == served_candidates != "5"
        and kept_id == dense_id
        and _pressed_preset(r) == ["hybrid"]
        and not page.locator("#rag-seq .rag-chain-refusal").count()
        and page.locator("#rag-run").is_enabled(),
        "« RAG hybride » : le segment devient Dense retrieval, BM25, Fusion (RRF), le reste "
        "inchangé (300 caractères, top_k 2 gardés), les candidats du Dense retrieval à la "
        "valeur servie, son id gardé, le bouton pressé, la chaîne valide",
        f"{kinds} · {names} · {chunk}/{top_k} · {candidates}/{served_candidates} · "
        f"{dense_id}/{kept_id} · {_pressed_preset(r)}",
    )
    # B2 (2026-10-05): BM25's index, built at BUILD: its line after « Indexing », its tile
    # « Index lexical (BM25) » in Données, read by BM25.
    build_names = page.locator("#rag-seq-build .rag-seq-name").all_inner_texts()
    data_tiles = page.eval_on_selector_all(
        '#rag-arch .rag-arch-group[data-group="data"] .rag-arch-tile',
        "ts => ts.map(t => [t.dataset.component, t.querySelector('.rag-arch-name').textContent])",
    )
    bm25_uses = _focus_of(r, "lexical_search")["uses"]
    r.check(
        build_names == ["Documents", "Chunking", "Embedding", "Indexing", "Lexical indexing"]
        and ["lexical_index", "Index lexical (BM25)"] in data_tiles
        and bm25_uses == ["lexical_index", "question"],
        "B2 : « RAG hybride » : la ligne BUILD « Lexical indexing » après « Indexing », la tuile "
        "« Index lexical (BM25) » dans Données, BM25 lit l'index lexical et la question",
        f"{build_names} · {data_tiles} · {bm25_uses}",
    )
    page.reload()
    expect(page.locator("body[data-rag-ready]")).to_be_attached(timeout=10_000)
    time.sleep(0.4)
    r.check(
        _chain_kinds(r)[3:6] == ["vector_search", "lexical_search", "fusion"]
        and _pressed_preset(r) == ["hybrid"],
        "après rechargement, la chaîne hybride est gardée, « RAG hybride » reste pressé",
        f"{_chain_kinds(r)} · {_pressed_preset(r)}",
    )
    r.shot("59-atelier-rag-architectures")
    ended, seq = _rag_lab_run(r)
    # B2: in « Dérouler », the line « Lexical indexing »: its own pill (duration) and, in its
    # focus, the index's figures, « aucun modèle », its duration.
    indexed = _stage_ended(r, seq, "lexical_index")
    _focus_of(r, "lexical_index")
    focus = page.inner_text("#rag-focus")
    pill = page.inner_text('#rag-seq .rag-seq-step[data-step="lexical_index"] .rag-seq-status')
    r.check(
        indexed.get("status") == "ok"
        and indexed.get("part") == "index"
        and "Termes distincts" in focus
        and "Chunks indexés" in focus
        and "aucun (algorithme statistique)" in focus
        and "Durée" in focus
        and "ms" in pill,
        "B2 : en Dérouler après le run hybride, le focus de « Lexical indexing » montre les "
        "chiffres de l'index (chunks, termes distincts), « aucun modèle » et sa durée",
        f"{indexed.get('status')} · {pill} · {focus[:300]}",
    )
    _rag_mode(r, "compose")
    fusion = _stage_ended(r, seq, "fusion").get("items", [])
    r.check(
        ended["payload"]["status"] == "ok"
        and fusion
        and all(
            {s["kind"] for s in i["sources"]} == {"vector_search", "lexical_search"} for i in fusion
        )
        and len(_stage_ended(r, seq, "context").get("items", [])) == 2,
        "« RAG hybride » exécuté : la Fusion donne les rangs des deux recherches, run `ok`",
        f"{ended['payload'].get('status')} · {len(fusion)} extraits",
    )
    _add_stage(r, "Reranking")
    r.check(
        _chain_kinds(r)[3:7] == ["vector_search", "lexical_search", "fusion", "rerank"]
        and _pressed_preset(r) == [],
        "segment composé à la main (hybride + reranking) : aucun bouton pressé",
        f"{_chain_kinds(r)} · {_pressed_preset(r)}",
    )
    page.locator('#rag-presets .rag-preset[data-preset="dense"]').click()
    time.sleep(0.8)
    dense = (_chain_kinds(r), _pressed_preset(r))
    # B1 (2026-10-05): no Reranking, no Reranker tile: the Models group says to add the stage;
    # its click proposes Reranking in « Ajouter un composant ».
    hint = page.locator('#rag-arch .rag-arch-group[data-group="models"] .rag-arch-download-hint')
    said = hint.inner_text() if hint.count() == 1 else ""
    if hint.count() == 1:
        hint.click()
    picked = page.evaluate(
        "() => ({ value: document.querySelector('#rag-palette-a select')?.value,"
        " focused: document.activeElement?.classList.contains('rag-palette-add') })"
    )
    r.check(
        not page.locator('#rag-arch .rag-arch-tile[data-component="reranker"]').count()
        and said
        == "Reranker : 1 modèle à télécharger ; ajoutez l'étape Reranking pour le télécharger"
        and picked == {"value": "rerank", "focused": True},
        "B1 : « RAG dense » (sans Reranking) : le groupe Modèles dit d'ajouter l'étape Reranking "
        "pour télécharger son modèle ; le clic la propose dans « Ajouter un composant »",
        f"{said} · {picked}",
    )
    page.locator('#rag-presets .rag-preset[data-preset="rerank"]').click()
    time.sleep(0.8)
    r.check(
        dense[0][3:5] == ["vector_search", "context"]
        and dense[1] == ["dense"]
        and _chain_kinds(r)[3:6] == ["vector_search", "rerank", "context"]
        and _pressed_preset(r) == ["rerank"],
        "« RAG dense » puis « RAG + reranking » : chaque fois le segment remplacé, le bouton "
        "pressé",
        f"{dense} · {_chain_kinds(r)} · {_pressed_preset(r)}",
    )
    _rag_mode(r, "play")
    r.check(
        page.locator("#rag-presets").is_hidden(), "Dérouler : pas d'architectures toutes faites"
    )
    _rag_mode(r, "compose")

    # A preset the session says would not run (the reranker absent, served by `page.route`):
    # marked « indisponible », still clickable.
    def unavailable(route) -> None:  # noqa: ANN001
        response = route.fetch()
        body = response.json()
        for preset in (body.get("catalog") or {}).get("presets", []):
            if preset["id"] == "rerank":
                preset["available"], preset["reason_text"] = False, "Reranker absent (e2e)."
        route.fulfill(response=response, json=body)

    page.locator('#rag-presets .rag-preset[data-preset="dense"]').click()
    time.sleep(0.8)
    page.route("**/api/rag_lab", unavailable)
    try:
        page.reload()
        expect(page.locator("body[data-rag-ready]")).to_be_attached(timeout=10_000)
        marked = _rag_presets(r).get("rerank", {})
        sweep = _contrast_sweep(r, ["#rag-presets"])
        page.locator('#rag-presets .rag-preset[data-preset="rerank"]').click()
        time.sleep(0.8)
        r.check(
            marked.get("unavailable")
            and "indisponible" in marked.get("text", "")
            and "Reranker absent (e2e)." in marked.get("title", "")
            and _chain_kinds(r)[3:5] == ["vector_search", "rerank"]
            and not sweep,
            "préréglage indisponible : marqué « indisponible », la raison en infobulle, "
            "cliquable (il s'applique), contrastes AA",
            f"{marked} · {_chain_kinds(r)} · {sweep}",
        )
    finally:
        page.unroute("**/api/rag_lab", unavailable)
    page.reload()  # the real catalog again, not the faked one
    expect(page.locator("body[data-rag-ready]")).to_be_attached(timeout=10_000)
    page.locator("#rag-reset-chain").click()
    time.sleep(0.4)


def _rag_lab_alt(r: Run) -> None:
    """Increment 3: the scenario follows the catalog. Without the `rag-alt` extra, FAISS and
    LanceDB are greyed with the command that installs them; with it, the chain on FAISS gives
    the context of the shipped chain (sqlite-vec), its index built then read, its import's
    memory said. Lot 5a: one chain, FAISS on it."""
    page = r.page
    state = r.api("GET", "/api/rag_lab").json()
    stores = next(s for s in state["catalog"]["stages"] if s["kind"] == "vector_store")
    faiss = next(o for o in stores["options"] if o["id"] == "faiss")
    page.locator("#rag-reset-chain").click()
    select = _seq_row(r, "vector_store").locator("select.rag-option")
    expect(select).to_be_visible(timeout=5000)
    if not faiss["available"]:
        print("  (branche : sans l'extra rag-alt)")
        disabled = select.locator("option:disabled").all_inner_texts()
        reasons = _seq_row(r, "vector_store").locator(".rag-chain-unavailable")
        hidden = reasons.first.is_hidden()  # shown on the line selected only
        _focus_of(r, "vector_store")
        reasons = reasons.all_inner_texts()
        r.check(
            any(t.startswith("FAISS") for t in disabled)
            and any(t.startswith("LanceDB") for t in disabled)
            and hidden
            and len(reasons) == 2
            and all("uv sync --extra compression --extra rag-alt" in t for t in reasons),
            "sans l'extra : FAISS et LanceDB désactivés ; la ligne sélectionnée donne la raison "
            "et la commande",
            str(reasons)[:300],
        )
        page.locator("#rag-reset-chain").click()
        return
    print("  (branche : avec l'extra rag-alt)")
    _, seq = _rag_lab_run(r, compose=True)
    shipped = [(i["rank"], i["chunk_id"]) for i in _stage_ended(r, seq, "context")["items"]]
    _set_stage(r, "vector_store", "faiss")
    figures = []
    for _ in range(2):
        ended, seq = _rag_lab_run(r, compose=True)
        store = _stage_ended(r, seq, "vector_store")
        context = _stage_ended(r, seq, "context").get("items", [])
        figures.append((ended["payload"]["status"], store, context))
    (status, first, context), (_, second, _) = figures
    facts = {f["label_text"]: f["value_text"] for f in first.get("facts", [])}
    _open_details(r)
    card = _result_card(r, "vector_store").inner_text()
    r.check(
        status == "ok" and [(i["rank"], i["chunk_id"]) for i in context] == shipped,
        "avec l'extra : la chaîne sur FAISS garde les extraits et les rangs de sqlite-vec",
        str([(i["rank"], i["doc_id"]) for i in context]),
    )
    r.check(
        "construit (29 vecteurs)" in first.get("output_text", "")
        and "relu (29 vecteurs)" in second.get("output_text", "")
        and facts.get("Import", "").startswith(("premier import : +", "déjà fait"))
        and ("premier import" in card.lower() or "déjà fait" in card.lower()),
        "Vector store sur FAISS : « construit », puis « relu », et la mémoire ajoutée à l'import",
        f"{first.get('output_text', '')[:80]} · {second.get('output_text', '')[:60]} · {facts}",
    )
    page.locator("#rag-reset-chain").click()


def _git_status() -> str:
    import subprocess

    return subprocess.run(
        ["git", "status", "--porcelain", "--", ".", ":!tools/e2e/screenshots"],
        cwd=REPO,
        capture_output=True,
        text=True,
        check=False,
    ).stdout


def _set_stage(r: Run, kind: str, option: str | None = None, **params: int) -> None:
    if option is not None:
        _seq_row(r, kind).locator("select.rag-option").select_option(option)
    for name, value in params.items():
        field = _seq_row(r, kind).locator(f'input[data-param="{name}"]')
        field.fill(str(value))
        field.dispatch_event("change")


def _rag_lab_compare(r: Run) -> None:
    """Increment 2, one chain since lot 5a (the A/B comparison is gone from the page): the
    exhaustive search in memory, 300 characters, `top_k` 2; two runs (computed, then read from
    the cache); a chain saved by a page of before (A and B, labels `label_fr`) read again with
    A only; a chain with fewer candidates than excerpts refused with its reason."""
    page = r.page
    status_before = _git_status()
    lab_dir = r.stack.data_dir / "rag_lab"
    folders_before = set(lab_dir.iterdir()) if lab_dir.is_dir() else set()
    page.locator("#rag-reset-chain").click()
    expect(page.locator("#rag-seq li.rag-chain-card")).to_have_count(7, timeout=5000)
    store = _seq_row(r, "vector_store").locator("select.rag-option")
    labels = store.locator("option").all_inner_texts()
    r.check(
        "Recherche exhaustive en mémoire" in labels and "sqlite-vec" in labels,
        "Vector store : sqlite-vec et la recherche exhaustive en mémoire proposés",
        str(labels),
    )
    _set_stage(r, "vector_store", "memory")
    _set_stage(r, "chunking", chunk_max_chars=300)
    _set_stage(r, "context", top_k=2)
    ended, seq = _rag_lab_run(r, compose=True)
    _open_details(r)
    embedding = _result_card(r, "embedding").inner_text()
    context = _stage_ended(r, seq, "context")
    r.check(
        ended["payload"]["status"] == "ok"
        and page.locator("#rag-details .rag-lane").count() == 1
        and "calculés (77 passages)" in embedding
        and len(context.get("items", [])) == 2
        and _result_card(r, "context").locator("tbody tr").count() == 2,
        "une seule chaîne : l'Embedding calcule ses 77 passages, le prompt garde 2 extraits",
        embedding[:240],
    )
    folders = set(lab_dir.iterdir()) if lab_dir.is_dir() else set()
    r.check(
        len(folders - folders_before) == 1 and _git_status() == status_before,
        "un dossier nouveau sous rag_lab_dir(), aucun fichier créé dans le dépôt",
        f"{sorted(p.name for p in folders)} · git « {_git_status()[:120]} »",
    )
    r.shot("57-atelier-rag-composer", full_page=True)
    ended, seq = _rag_lab_run(r, compose=True)
    r.check(
        "relus du cache" in _result_card(r, "embedding").inner_text(),
        "second run : l'Embedding dit « relus du cache »",
    )
    # A page of before lot 5a saved two chains (A and B), each label named `label_fr`
    # (languages 2/5): A is read again, B is dropped.
    page.evaluate(
        "() => { const key = 'wavestack.ragLab';"
        " const saved = JSON.parse(localStorage.getItem(key));"
        " const [a] = saved.pipelines.map(({ label_text: _, ...rest }) => rest);"
        " const b = JSON.parse(JSON.stringify(a));"
        " b.stages.find(s => s.kind === 'chunking').params.chunk_max_chars = 900;"
        " saved.pipelines = [{ label_fr: 'Chaîne A', ...a }, { label_fr: 'Chaîne B', ...b }];"
        " localStorage.setItem(key, JSON.stringify(saved)); }"
    )
    page.reload()
    expect(page.locator("body[data-rag-ready]")).to_be_attached(timeout=10_000)
    pressed = page.locator('#rag-modes [data-mode="compose"]').get_attribute("aria-pressed")
    r.check(pressed == "true", "rechargé en Composer : Composer reste choisi", str(pressed))
    _rag_mode(r, "compose")
    kept = _seq_row(r, "chunking").locator('input[data-param="chunk_max_chars"]')
    r.check(
        kept.input_value() == "300"
        and page.locator("#rag-seq li.rag-chain-card").count() == 7
        and not page.locator("#rag-compare, #rag-chain-b").count(),
        "après rechargement, une chaîne enregistrée A + B (ancien format, label_fr) : seule A "
        "est gardée",
        kept.input_value(),
    )
    # Fewer candidates than excerpts kept: the session's reason on the line (increment 4
    # validates each change), « Lancer » greyed; posted anyway, the 409's reason.
    _set_stage(r, "vector_search", candidates=1)
    seq = r.ev.mark()
    row = _seq_row(r, "vector_search")
    expect(row.locator(".rag-chain-refusal")).to_be_visible(timeout=5000)
    said = row.locator(".rag-chain-refusal").inner_text()
    chain = page.evaluate("() => JSON.parse(localStorage.getItem('wavestack.ragLab')).pipelines")
    refused = r.api(
        "POST", "/api/intentions/rag_lab_run", {"question": RAG_LAB_QUESTION, "pipelines": chain}
    )
    time.sleep(0.3)
    r.check(
        len(chain) == 1
        and "Dense retrieval" in said
        and "candidat" in said
        and page.locator("#rag-run").is_disabled()
        and refused.status_code == 409
        and said in refused.json().get("detail", "")
        and not r.ev.since(seq, "rag_lab_run_started"),
        "candidats < top_k : la ligne affiche la raison du 409, « Lancer » grisé, rien ne "
        "s'exécute",
        f"{said} · {refused.status_code}",
    )
    page.locator("#rag-reset-chain").click()
    time.sleep(0.4)
    r.check(
        _chain_kinds(r) == RAG_LAB_STAGES_KINDS
        and not page.locator("#rag-seq .rag-chain-refusal").count(),
        "« Revenir à la chaîne livrée » : la chaîne livrée, valide",
    )


RAG_LAB_STAGES_KINDS = [
    "chunking",
    "embedding",
    "vector_store",
    "vector_search",
    "rerank",
    "context",
    "generation",
]


SCENARIOS: list[tuple[str, Callable[[Run], None]]] = [
    ("diagnostic", s_diagnostic),
    ("programme", s_programme),
    ("bare_llm", s_bare_llm),
    ("short_memory", s_short_memory),
    ("system_prompt", s_system_prompt),
    ("native_tools", s_native_tools),
    ("malformed", s_malformed),
    ("provider_errors", s_provider_errors),
    ("markdown", s_markdown),  # recette du 02/10
    ("diagnostic_wait", s_diagnostic_wait),  # recette du 02/10 (R1)
    ("network_tools", s_network_tools),
    ("disciplines", s_disciplines),
    ("themes", s_themes),
    ("linked_view", s_linked_view),
    ("panes", s_panes),  # restes différés, story 6 (E033)
    ("h5", s_h5),
    ("mcp_full", s_mcp_full),
    ("mcp_lazy", s_mcp_lazy),
    ("skills", s_skills),
    ("caveman", s_caveman),
    ("hooks", s_hooks),
    ("subagent", s_subagent),
    ("data_flows", s_data_flows),
    ("soc", s_soc),
    ("iam", s_iam),
    ("sovereignty", s_sovereignty),
    ("forced_native", s_forced_native),
    ("global_memory", s_global_memory),
    ("rag", s_rag),
    ("rag_rerank", s_rag_rerank),
    ("rag_lab", s_rag_lab),
    ("mcp_lab", s_mcp_lab),  # story 6 (2026-09-30): captures 61 and 62
    ("mcp_lab_page", s_mcp_lab_page),  # restes du 2026-10-01: /mcp on its own side
    ("compression", s_compression),
    ("busy_and_stop", s_busy_and_stop),
    ("reload_and_reset", s_reload_and_reset),
    ("language", s_language),
    ("ui_language", s_ui_language),
    ("content_language", s_content_language),
    ("annex_language", s_annex_language),
    ("backend_language", s_backend_language),  # story 7 of 2026-09-30 (languages 5/5)
    ("stream_resync", s_stream_resync),
    ("stream_lost", s_stream_lost),  # restes différés, story 2 (E003)
    ("model_switch", s_model_switch),
    ("reasoning_locked", s_reasoning_locked),
    ("reasoning_dropped", s_reasoning_dropped),  # finition V1 (#28, #35)
    # GreenOps: the served model before the first priced call (the footprint alone).
    ("local_server", s_local_server),
    ("gemini_shape", s_gemini_shape),
    ("priced_estimate", s_priced_estimate),  # restes différés, story 6 (E135)
    ("model_catalog", s_model_catalog),
    ("context_window", s_context_window),
    ("llm_screen", s_llm_screen),
    ("llm_live", s_llm_live),  # restes du 2026-10-01: distribution and window, page side
    ("llm_loop", s_llm_loop),  # lot 6 of 2026-10-04: the model's loop in three stages
    ("relaunch", s_relaunch),
]


def main() -> int:
    parser = argparse.ArgumentParser(description="Test de bout en bout de WaveStack (palier 1).")
    parser.add_argument("--only", nargs="*", help="scénarios à jouer (diagnostic toujours)")
    parser.add_argument("--keep", action="store_true", help="garder le dossier de données")
    parser.add_argument("--headed", action="store_true")
    parser.add_argument(
        "--channel",
        help="navigateur installé à piloter à la place du Chromium de Playwright (msedge, chrome)",
    )
    parser.add_argument(
        "--no-rag-alt",
        action="store_true",
        help="WaveStack comme sans l'extra rag-alt (FAISS et LanceDB indisponibles)",
    )
    parser.add_argument(
        "--no-greenops",
        action="store_true",
        help="WaveStack comme sans l'extra greenops (empreinte locale indisponible)",
    )
    parser.add_argument(
        "--no-headroom",
        action="store_true",
        help="WaveStack comme sans l'extra compression (le scénario compression est sauté)",
    )
    args = parser.parse_args()
    if args.no_headroom:  # read by `wavestack_e2e.py` through the stack's environment
        os.environ["WAVESTACK_E2E_NO_HEADROOM"] = "1"
    if args.no_greenops:  # GreenOps, likewise
        os.environ["WAVESTACK_E2E_NO_GREENOPS"] = "1"
    if args.no_rag_alt:  # story 30, likewise
        os.environ["WAVESTACK_E2E_NO_RAG_ALT"] = "1"
    chosen = [s for s in SCENARIOS if not args.only or s[0] in args.only or s[0] == "diagnostic"]

    console: list[str] = []
    with running_stack(keep=args.keep) as stack, sync_playwright() as p:
        print(f"WaveStack {stack.app_url} · faux modèle {stack.fake_url} · {stack.data_dir}")
        if args.channel:  # E125 (restes différés, story 6): e.g. Edge, as on the target PC
            try:
                browser = p.chromium.launch(headless=not args.headed, channel=args.channel)
            except Exception as exc:  # noqa: BLE001 - E125: said, then no run
                print(
                    f"Navigateur « {args.channel} » introuvable sur ce poste : {exc}".splitlines()[
                        0
                    ]
                )
                return 2
            print(f"Navigateur : {args.channel} {browser.version}")
        else:
            try:
                browser = p.chromium.launch(headless=not args.headed)
            except Exception:  # noqa: BLE001 - another Playwright revision: the preinstalled
                browser = p.chromium.launch(headless=not args.headed, executable_path=CHROMIUM)
        page = browser.new_page(viewport={"width": 1600, "height": 1000}, locale="fr-FR")
        page.on(
            "console",
            lambda m: (
                console.append(f"{m.type}: {m.text}") if m.type in ("error", "warning") else None
            ),
        )
        page.on("pageerror", lambda e: console.append(f"pageerror: {e}"))
        run = Run(page, stack, Events(stack.app_url))
        for name, scenario in chosen:
            run.current = name
            print(f"== {name}")
            try:
                scenario(run)
            except Exception as exc:  # noqa: BLE001 - reported, then the next scenario
                run.check(False, "exception", f"{type(exc).__name__}: {exc}".splitlines()[0])
                traceback.print_exc()
                try:
                    run.shot(f"echec-{name}")
                    run.page.goto(f"{stack.app_url}/")
                except Exception:  # noqa: BLE001
                    pass
        browser.close()
        errors = [e for e in run.earlier_events + run.ev.items if e["kind"] == "harness_error"]
        print(f"\nharness_error émis pendant la séance : {len(errors)}")
        for e in errors:
            print(f"  - {e['payload']['message_text'][:200]}")
    failed = [x for x in run.results if not x[2]]
    print(
        f"\n{len(run.results) - len(failed)} vérifications réussies, {len(failed)} en échec, "
        f"{len(run.known)} anomalies connues."
    )
    for scenario, what, known, detail in run.known:
        print(f"  KNOWN [{known}] [{scenario}] {what} — {detail}")
    for scenario, what, _, detail in failed:
        print(f"  FAIL [{scenario}] {what} — {detail}")
    if console:
        print("\nConsole du navigateur (erreurs et avertissements) :")
        for line in console[:40]:
            print(f"  {line[:300]}")
    return 1 if failed else 0


if __name__ == "__main__":
    raise SystemExit(main())
