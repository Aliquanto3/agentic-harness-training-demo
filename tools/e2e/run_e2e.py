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

sys.path.insert(0, str(Path(__file__).resolve().parent))
from stack import (  # noqa: E402
    GEMINI_ENTRY_ID,
    GEMINI_MODEL,
    GEMINI_PROVIDER,
    MODEL_ENTRY_ID,
    REASONING_ENTRY_ID,
    REASONING_MODEL,
    SECOND_ENTRY_ID,
    SECOND_MODEL,
    Stack,
    running_stack,
)

from wavestack.rag import index as rag_index  # noqa: E402

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
        details = self.card(brick).locator("details.brick-options")
        if details.get_attribute("open") is None:
            details.locator("summary").click()

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


# ---------- scenarios ----------


def s_diagnostic(r: Run) -> None:
    page = r.page
    page.goto(f"{r.stack.app_url}/diagnostic")
    row = page.locator("#cloud-models li", has_text="wavestack-fake")
    expect(row).to_be_visible(timeout=20_000)
    r.check(
        "Clé fournie par la variable WAVESTACK_FAKE_API_KEY" in row.inner_text(),
        "la ligne du faux modèle indique la clé lue dans key_env",
    )
    r.check("e2e-fake-key" not in page.content(), "la valeur de la clé n'apparaît pas dans la page")
    row.get_by_role("button", name="Tester").click()
    expect(row.locator(".cloud-result.ok")).to_contain_text("Test réussi", timeout=20_000)
    r.check(True, "« Tester » réussit (appel d'outil get_datetime reçu)", row.inner_text()[-160:])
    row.get_by_role("button", name="Choisir").click()
    dialog = page.locator("#cloud-warning")
    expect(dialog).to_be_visible()
    r.check(
        "Faux fournisseur (e2e)" in dialog.inner_text(),
        "l'avertissement cloud nomme le fournisseur",
    )
    r.shot("01-diagnostic-avertissement-cloud")
    page.locator("#cloud-warning-confirm").click()
    expect(row).to_contain_text("actif", timeout=20_000)
    r.check(True, "« Utiliser ce modèle » : la ligne passe à « actif »")
    # Story 2 (2026-09-30): « Ouvrir WaveStack » gave way to « Atelier » of the shared bar.
    ok, took = r.poll(lambda: bool(r.api("GET", "/api/diagnostic").json().get("ready")), 20)
    r.check(ok, "diagnostic prêt", f"{took:.1f} s")
    page.locator('.site-nav > a[href="/"]:not(.site-nav-brand)').click()
    page.wait_for_url(f"{r.stack.app_url}/", timeout=10_000)
    expect(page.locator("#model-indicator")).to_contain_text("wavestack-fake", timeout=20_000)
    r.check(True, "l'indicateur de modèle de la barre de l'atelier montre le faux modèle")
    r.wait_idle()


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
    _braces_stay_text(r, "mode chat")


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
        "Je m'appelle Camille et je suis consultante en cybersécurité.",
        "Comment je m'appelle, et quel est mon métier ?",
    ]
    r.send(prompts[0])
    r.send(prompts[1])
    r.check("Camille" in r.last_answer(), "mémoire active : le prénom revient", r.last_answer())
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
    ended = r.send("Bonjour")
    r.check(ended["payload"]["status"] == "completed", "WaveStack reste utilisable ensuite")
    seq = r.ev.mark()
    ended = r.send("Explique [coupé]")
    r.check(
        ended["payload"]["status"] == "limit",
        "sortie coupée (finish_reason length)",
        ended["payload"]["status"],
    )


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
  if (order !== '/ / /llm /rag /mcp /diagnostic /models') problems.push(`liens ${order}`);
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
    for path, shot in (
        ("/diagnostic", "49-theme-sombre-diagnostic"),
        ("/models", "50-theme-sombre-modeles"),
    ):
        page.goto(f"{r.stack.app_url}{path}")
        if path == "/models":
            expect(page.locator("#models-table tbody tr").first).to_be_visible(timeout=10_000)
        else:
            expect(page.locator("#cloud-models li").first).to_be_visible(timeout=20_000)
        time.sleep(0.5)
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


def s_h5(r: Run) -> None:
    r.launch("network_tools")
    r.set_brick("Hooks", True)
    r.set_option("Hooks", "Validation humaine", True)
    asked = r.send("Quels sont les jours fériés en France cette année ?", expect_approval=True)
    r.check(
        asked["payload"]["tool"] == "public_holidays", "H5 suspend le tour avant l'outil réseau"
    )
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
    r.shot("09-h5-validation-humaine")
    seq = r.ev.mark()
    card.get_by_role("button", name="Refuser", exact=True).click()
    resolved = r.ev.wait("approval_resolved", seq, timeout=10)
    ended = r.ev.wait("turn_ended", seq)
    r.check(resolved["payload"]["decision"] == "refused", "« Refuser » : décision refused")
    r.check(not r.ev.since(seq, "outbound_request"), "refusé : rien ne sort du poste")
    r.check(
        ended["payload"]["status"] == "completed",
        "le tour se termine après le refus",
        ended["payload"]["status"],
    )
    asked = r.send("Quels sont les jours fériés en France cette année ?", expect_approval=True)
    seq = r.ev.mark()
    r.page.locator("#chat .approval-card").last.get_by_role(
        "button", name="Autoriser", exact=True
    ).click()
    r.ev.wait("approval_resolved", seq, timeout=10)
    r.ev.wait("turn_ended", seq)
    r.check(bool(r.ev.since(seq, "outbound_request")), "« Autoriser » : la requête part")
    results = [e["payload"] for e in r.ev.since(seq, "tool_ended")]
    r.check(
        bool(results) and results[-1]["status"] == "error",
        "autorisé : l'échec réseau est expliqué",
        (results[-1].get("error_text") or "")[:200] if results else "",
    )
    # A reload while the turn waits: the card comes back (AD-1); « Arrêter » cancels it.
    asked = r.send("Quels sont les jours fériés en France cette année ?", expect_approval=True)
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
    # the fragments of JSON the sentinels cut.
    tools_row = (
        r.page.locator("#ctx .ctx-call")
        .first.locator(".ctx-section")
        .filter(has=r.page.locator(".ctx-section-label", has_text="Descriptions d'outils"))
    )
    names = (
        tools_row.first.locator(".json-tree .json-string").all_inner_texts()
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


def s_mcp_lazy(r: Run) -> None:
    first, second = _prompts("mcp_lazy")
    r.launch("mcp_lazy")
    guide = r.page.locator("#scenario-info-popover").text_content()
    r.check(
        not r.bricks()["rag"]["wanted"] and "le RAG, laissé éteint" in guide,
        "lazy loading : RAG non voulu (story 27), la consigne le dit",
        guide[:200],
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
    ended = r.send(second)
    r.check(
        ended["payload"]["status"] == "completed",
        "qualité de l'air sans data.gouv.fr : réponse sans outil",
        r.last_answer()[:160],
    )
    # Story 9: force an MCP documentation.
    r.show_forced(True)
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
    seq = r.ev.mark()
    ended = r.send(_prompts("skills")[0])
    tools = [e["payload"]["tool"] for e in r.ev.since(seq, "tool_started")]
    r.check("load_skill" in tools, "le modèle charge le skill", str(tools))
    r.check(ended["payload"]["status"] == "completed", "tour terminé")
    sent = json.dumps(r.fake_calls()[-1]["messages"], ensure_ascii=False)
    r.check("compte rendu de réunion structuré" in sent, "le contenu du skill rejoint le contexte")


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
    seq = r.ev.mark()
    ended = r.send("Lis le fichier confidentiel/budget_projet.txt et résume-le.")
    decided = [e["payload"] for e in r.ev.since(seq, "hook_decided")]
    blocks = [d for d in decided if d["hook"] == "h1" and d["decision"] == "block"]
    r.check(
        bool(blocks),
        "H1 bloque la lecture du dossier confidentiel",
        str([(d["hook"], d["decision"]) for d in decided]),
    )
    r.check(any(d["hook"] == "h2" for d in decided), "H2 journalise")
    r.check(ended["payload"]["status"] == "completed", "le tour se termine")
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
    delegate.click()
    expect(form).to_be_visible(timeout=5000)
    # Lot K (A8): the button says the form is open.
    r.check(
        delegate.get_attribute("aria-expanded") == "true",
        "1280 × 650 : formulaire « Déléguer au sous-agent » ouvert, aria-expanded=true",
        str(delegate.get_attribute("aria-expanded")),
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


def s_forced_native(r: Run) -> None:
    r.launch("native_tools")
    r.show_forced(True)
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
        "Camille" in r.last_answer(),
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
    form.locator("input").fill("Camille anime la formation à Nantes.")
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
    r.shot("20-memoire-tiroir")

    seq = r.ev.mark()
    entries.first.locator("textarea").fill("L'utilisateur s'appelle Camille Martin.")
    entries.first.get_by_role("button", name="Enregistrer l'entrée 1").click()
    r.ev.wait("memory_changed", seq, timeout=10)
    saved = _memory_file(r)
    r.check(
        saved[0]["text"] == "L'utilisateur s'appelle Camille Martin."
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

    # The file is served now: the download succeeds; the card offers the index's build.
    httpx.post(f"{r.stack.fake_url}/_e2e/model_ready", timeout=5, trust_env=False)
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
    """Story 6 of 2026-09-30: the MCP workshop (`/mcp`). The link of the shared bar and of the
    MCP card, the three servers, a connection to the local glossary (its JSON-RPC messages with
    direction and duration, its two tools and their weight), a valid call then an unknown term
    (`is_error`), the brick left as it was. Captures 61 and 62. Back to `/`."""
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


def _mcp_lab(r: Run, errors: list[str]) -> None:
    page = r.page
    r.goto_app()
    r.wait_idle()
    brick_before = r.bricks()["mcp"]
    # (1) The links: the shared bar's, whole, and the MCP card's.
    link = page.locator('.site-nav a[href="/mcp"]')
    r.check(
        link.is_visible() and link.inner_text() == "Atelier MCP",
        "barre commune : lien « Atelier MCP » visible, entier, vers /mcp",
        link.inner_text() if link.count() else "absent",
    )
    ok, detail = _bar_fits(r)
    r.check(ok, "barre commune entière avec six pages, sur une ligne, à 1600 × 1000", detail)
    r.check(
        page.locator('a.brick-workshop-link[href="/mcp"]').count() == 1,
        "la carte de la brique MCP renvoie à l'atelier MCP",
    )

    # (2) The page: the shared bar, the three servers.
    link.click()
    page.wait_for_url("**/mcp")
    expect(page.locator("body[data-mcp-ready]")).to_be_attached(timeout=10_000)
    r.check(
        page.locator("nav.site-nav a[aria-current=page]").inner_text() == "Atelier MCP"
        and not _site_nav_problems(r),
        "/mcp : barre commune entière, « Atelier MCP » courant",
        str(_site_nav_problems(r)),
    )
    servers = page.locator("#mcp-servers .mcp-server")
    ids = [servers.nth(i).get_attribute("data-server") for i in range(servers.count())]
    r.check(ids == ["local", "datagouv", "mslearn"], "/mcp : les trois serveurs", str(ids))
    command = servers.nth(0).inner_text()
    r.check(
        "stdio" in command and "wavestack.mcp.local_server" in command,
        "le glossaire : transport stdio et commande de lancement",
        command[:200],
    )

    # (3) The handshake with the local glossary: its messages, its tools, their weight.
    seq = r.ev.mark()
    page.locator('button[data-connect="local"]').click()
    ended = r.ev.wait("mcp_lab_connect_ended", seq, timeout=60)["payload"]
    r.check(ended["status"] == "ok", "connexion de l'atelier au glossaire local", str(ended)[:300])
    expect(page.locator('#mcp-connect-summary[data-status="ok"]')).to_be_visible(timeout=10_000)
    messages = page.locator("#mcp-messages .mcp-message")
    shape = [
        (
            messages.nth(i).get_attribute("data-direction"),
            messages.nth(i).get_attribute("data-method"),
        )
        for i in range(messages.count())
    ]
    r.check(
        shape[:2] == [("to_server", "initialize"), ("from_server", "initialize")]
        and ("to_server", "tools/list") in shape
        and ("from_server", "tools/list") in shape,
        "poignée de main : initialize, sa réponse, tools/list et sa réponse, avec leur sens",
        str(shape),
    )
    timings = [messages.nth(i).locator(".mcp-timing").inner_text() for i in range(messages.count())]
    r.check(
        timings and all(re.search(r"\d+ ms", t) for t in timings),
        "chaque message porte sa durée en ms",
        str(timings),
    )
    tools = page.locator("#mcp-tools .mcp-tool")
    names = [tools.nth(i).get_attribute("data-tool") for i in range(tools.count())]
    total = page.locator("#mcp-weight-rows .mcp-total")
    full = int(total.get_attribute("data-full") or 0)
    lazy = int(total.get_attribute("data-lazy") or 0)
    r.check(
        names == ["local__list_terms", "local__define_term"] and full > 0 and lazy > 0,
        "deux outils, leur poids en documentation complète et en lazy loading",
        f"{names} · {full} · {lazy}",
    )
    r.check(
        page.locator('#mcp-context [data-mode="full"]').count() == 1
        and page.locator('#mcp-context [data-mode="lazy"]').count() == 1,
        "ce que le modèle voit : le bloc « outils » dans les deux modes",
    )
    light = _contrast_sweep(r, ["main", "nav.site-nav"])
    _pick_theme(page, "dark")
    dark = _contrast_sweep(r, ["main", "nav.site-nav"])
    _pick_theme(page, "system")
    r.check(not light and not dark, "/mcp : contrastes AA en clair et en sombre", str(light + dark))
    r.shot("61-atelier-mcp-poignee-de-main", full_page=True)

    # (4) A valid call, then an unknown term: `is_error`, said, never a 500.
    page.locator("#mcp-call-tool").select_option("local__define_term")
    page.locator('#mcp-call-fields input[name="term"]').fill("harnais")
    seq = r.ev.mark()
    page.locator("#mcp-call-run").click()
    call = r.ev.wait("mcp_lab_call_ended", seq, timeout=30)["payload"]
    expect(page.locator('#mcp-call-summary[data-status="ok"]')).to_be_visible(timeout=10_000)
    reinjected = page.locator(".mcp-call-text pre").inner_text()
    r.check(
        call["status"] == "ok"
        and "harnais" in reinjected.lower()
        and page.locator(".mcp-call-request pre").count() == 1
        and page.locator(".mcp-call-raw pre").count() == 1,
        "appel valide : requête tools/call, réponse brute, texte réinjecté",
        reinjected[:200],
    )
    r.shot("62-atelier-mcp-appel", full_page=True)
    page.locator('#mcp-call-fields input[name="term"]').fill("zzz")
    seq = r.ev.mark()
    page.locator("#mcp-call-run").click()
    unknown = r.ev.wait("mcp_lab_call_ended", seq, timeout=30)["payload"]
    expect(page.locator('#mcp-call-summary[data-status="error"]')).to_be_visible(timeout=10_000)
    r.check(
        unknown["status"] == "error" and "is_error" in (unknown.get("error_text") or ""),
        "terme inconnu : réponse is_error montrée, statut erreur",
        str(unknown)[:300],
    )
    r.check(not errors, "/mcp : aucune erreur JavaScript", str(errors)[:300])

    # (5) The brick, untouched by the workshop.
    r.goto_app()
    after = r.bricks()["mcp"]
    r.check(
        (after.get("wanted"), after.get("options"))
        == (brick_before.get("wanted"), brick_before.get("options")),
        "la brique MCP de l'atelier est inchangée",
    )


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


def s_reload_and_reset(r: Run) -> None:
    r.launch("hooks")
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


def _history_strings(r: Run) -> set[str]:
    """The texts of the events emitted before the last change of language: the journal keeps
    them as they were said (the last model load's steps, in the language of the time). Every
    other text the session sends is in the current language (languages 5/5)."""
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

    walk([e.get("payload") for e in items if e["seq"] < changes[-1]])
    return found


def _french_left(r: Run, lang: str) -> list[str]:
    """The texts of the page that are a French value of the catalogue (whole texts), what
    the session sent included (languages 5/5: its messages are translated), the journal's
    history before the change of language aside."""
    patterns = _french_patterns(lang)
    history = _history_strings(r)
    found = []
    for where, text in r.page.evaluate(_VISIBLE_TEXTS_JS):
        if " ".join(text.split()).removeprefix("— ") in history:
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

ANNEX_PAGES = ("llm", "rag", "diagnostic", "models")
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


def _annex_patterns(lang: str) -> list[tuple[str, re.Pattern[str]]]:
    """The French values of the story's scope whose `lang` value differs: the sections
    `common`, `llm`, `rag`, `diagnostic` and `models` of `ui.yaml`, and the workshops'
    `llm_lab.yaml` and `rag_lab.yaml`. As `_french_patterns`: a variable is any text, and
    only fixed words of six letters at least say something."""
    french, translated = {}, {}
    for key, value in _ui_catalogue("fr").items():
        if key.split(".")[0] in ("common", *ANNEX_PAGES):
            french[f"ui.{key}"] = " ".join(value.split())
    for key, value in _ui_catalogue(lang).items():
        translated[f"ui.{key}"] = " ".join(value.split())
    for rel in ("llm_lab.yaml", "rag_lab.yaml", "mcp_lab.yaml"):
        french |= {f"{rel}:{k}": v for k, v in _yaml_leaves(_content("fr", rel)).items()}
        translated |= {f"{rel}:{k}": v for k, v in _yaml_leaves(_content(lang, rel)).items()}
    # Languages 5/5 (story 7 of 2026-09-30): the backend's messages too.
    french |= _message_catalogue("fr")
    translated |= _message_catalogue(lang)
    return _value_patterns(french, translated)


def _annex_french_left(r: Run, lang: str) -> list[str]:
    """As `_french_left`, on an annex page, with the annex catalogue (languages 5/5: what
    the session sent is no longer set aside, the journal's history excepted)."""
    patterns = _annex_patterns(lang)
    history = _history_strings(r)
    found = []
    for where, text in r.page.evaluate(_VISIBLE_TEXTS_JS):
        text = " ".join(text.split())
        if text.removeprefix("— ") in history:  # a check's line: « — {its text} »
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
    elif name == "diagnostic":
        page.goto(f"{r.stack.app_url}/diagnostic")
        expect(page.locator("#cloud-models li").first).to_be_visible(timeout=20_000)
    else:
        page.goto(f"{r.stack.app_url}/models")
        expect(page.locator("#models-table tbody").first).to_be_attached(timeout=20_000)
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
    reasons, the log) and the diagnostic and models pages without a French value of
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
            for name in ("diagnostic", "models"):
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
                        if name == "models" and width == 1280:
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
                r.page.route("**/api/state", handler, times=1)
            r.page.goto(f"{r.stack.app_url}/")
            # Not time.sleep: the sync API delivers `framenavigated` only while it runs.
            # The page is usable from `/api/state` on; the reload follows the stream's first event.
            r.page.wait_for_timeout(3000)
            r.wait_idle()
            r.page.wait_for_timeout(1000)
            r.check(len(navigations) == expected, label, f"{len(navigations)} navigation(s)")
        ended = r.send("Bonjour")
        r.check(ended["payload"]["status"] == "completed", "puis un tour aboutit")
    finally:
        r.page.remove_listener("framenavigated", on_nav)


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
    r.send("Je m'appelle Camille.")
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
    r.check("Je m'appelle Camille." in page.inner_text("#chat"), "la conversation est conservée")

    r.send("Comment je m'appelle ?")
    r.check("Camille" in r.last_answer(), "le nouveau modèle reçoit l'historique", r.last_answer())
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
    page.goto(f"{r.stack.app_url}/diagnostic")
    row_b = page.locator("#cloud-models li", has_text=SECOND_MODEL)
    expect(row_b).to_contain_text("actif", timeout=10_000)
    r.check(True, "diagnostic : le modèle actif est lu dans la session applicative")
    row_a = page.locator("#cloud-models li", has_text="wavestack-fake")
    row_a.get_by_role("button", name="Choisir").click()
    page.click("#cloud-warning-confirm")
    expect(row_a.locator(".cloud-result").last).to_have_text(
        "wavestack-fake est actif.", timeout=20_000
    )
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
    page.goto(f"{r.stack.app_url}/diagnostic")
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
    page.goto(f"{r.stack.app_url}/diagnostic")
    llama_row = page.locator("#candidates li", has_text=f"llama-server · {LLAMA_FILE}")
    expect(llama_row).to_be_visible(timeout=20_000)
    text = llama_row.inner_text()
    r.check(
        "Local" in text and r.stack.llama_url in text and "Mémoire du modèle servi" in text,
        "diagnostic : le modèle servi par llama-server est listé (Local, adresse, mémoire)",
        text.replace("\n", " · "),
    )
    r.check(
        llama_row.get_by_role("button", name="Choisir").count() == 1,
        "diagnostic : « Choisir » en face du modèle servi",
    )
    # Lot E (E1): the fake llama-server has a context of 8 192 tokens, twice the window.
    r.check(
        "relancez-le avec `-c 4096`" in text and "8\u202f192 tokens" in text,
        "diagnostic : llama-server à grand contexte, conseil « -c 4096 »",
        text.replace("\n", " · "),
    )
    ollama_row = page.locator("#candidates li", has_text="Ollama · faux-ollama:latest")
    r.check(
        ollama_row.count() == 1
        and "introuvable" in ollama_row.inner_text()
        and ollama_row.get_by_role("button", name="Choisir").count() == 0,
        "diagnostic : un modèle Ollama sans GGUF lisible est incompatible, sans « Choisir »",
        ollama_row.inner_text().replace("\n", " · ") if ollama_row.count() else "absent",
    )
    r.check("palier 2" not in page.inner_text("body"), "diagnostic : plus de « palier 2 »")

    # « Choisir » at the diagnostic: a hot switch from the cloud fake model, at the first
    # click (the page no longer rebuilds its rows while it replays the journal).
    seq = r.ev.mark()
    llama_row.get_by_role("button", name="Choisir").click()
    r.ev.wait("model_load_started", seq, timeout=5)
    ended = r.ev.wait("model_load_ended", seq, timeout=30)
    r.check(ended["payload"]["status"] == "ok", "diagnostic : « Choisir » prépare le modèle servi")
    expect(page.locator("#select-model-status")).to_have_text(
        "faux-llama-server est actif.", timeout=10_000
    )
    expect(llama_row).to_contain_text("chargé", timeout=10_000)
    r.check(
        llama_row.get_by_role("button", name="Choisir").count() == 0,
        "diagnostic : issue affichée, ligne marquée « chargé », sans « Choisir »",
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
    """A row of the `/models` table by its value (`cloud:fake`…): each column's text."""
    row = r.page.locator(f'#models-table tr[data-value="{value}"]')
    expect(row).to_have_count(1, timeout=10_000)
    cells = row.locator("td").all_inner_texts()
    keys = (
        "model",
        "publisher",
        "size",
        "hosting",
        "window",
        "tools",
        "reasoning",
        "price",
        "state",
    )
    row_texts: dict[str, str] = {}
    for key, cell in zip(keys, cells, strict=False):
        word, _, why = cell.replace("\u202f", " ").replace("\xa0", " ").partition("\n")
        row_texts[key], row_texts[f"{key}_why"] = word, why  # the word, its reason under it
    return row_texts


# ---------- story 3 of 2026-09-30: sort and filters of /models, the diagnostic's search ------

# Each visible group of the table, its visible rows in order: the pairs out of order for the
# column `key` (`size`: bytes, then parameters), unknown values always last; `ranks`: the
# rank of each text value (`reasoning`), the others unknown.
_MODELS_ORDER_JS = """({key, descending, ranks}) => {
  const problems = [];
  const value = (v) =>
    ranks ? (ranks[v] ?? null) : v === "" || v === undefined ? null : Number(v);
  const read = (tr) => (key === "size" ? [tr.dataset.size, tr.dataset.params] : [tr.dataset[key]])
    .map(value);
  for (const body of document.querySelectorAll("#models-table tbody")) {
    if (body.hidden) continue;
    const rows = [...body.querySelectorAll("tr[data-value]")].filter((tr) => !tr.hidden);
    for (let i = 1; i < rows.length; i++) {
      const a = read(rows[i - 1]);
      const b = read(rows[i]);
      for (let j = 0; j < a.length; j++) {
        if (a[j] === b[j]) continue;
        const wrong = a[j] === null || (b[j] !== null && (descending ? a[j] < b[j] : a[j] > b[j]));
        const [x, y] = [rows[i - 1].dataset.value, rows[i].dataset.value];
        if (wrong) problems.push(`${x} (${a}) > ${y} (${b})`);
        break;
      }
    }
  }
  return problems;
}"""


def _models_order_problems(
    r: Run, key: str, descending: bool, ranks: dict[str, int] | None = None
) -> list[str]:
    return r.page.evaluate(_MODELS_ORDER_JS, {"key": key, "descending": descending, "ranks": ranks})


def _models_sort_marks(r: Run) -> dict[str, str | None]:
    """`aria-sort` of each header of the table, by its `data-sort` (the price: « price »)."""
    return r.page.eval_on_selector_all(
        "#models-table thead th",
        "ths => Object.fromEntries(ths.map(th => [th.dataset.sort ?? 'price',"
        " th.getAttribute('aria-sort')]))",
    )


def _models_visible_values(r: Run) -> list[str]:
    return r.page.eval_on_selector_all(
        "#models-table tbody:not([hidden]) tr[data-value]:not([hidden])",
        "trs => trs.map(tr => tr.dataset.value)",
    )


def _folded(text: str) -> str:
    import unicodedata

    decomposed = unicodedata.normalize("NFD", text or "")
    return "".join(c for c in decomposed if not unicodedata.combining(c)).lower()


def _models_sort_and_filters(r: Run) -> None:
    """Sort by size (twice: descending, `aria-sort`), by the window from the keyboard; the
    network filter with a free text, its count; no result, then « Réinitialiser les filtres »."""
    page = r.page
    models = r.api("GET", "/api/diagnostic").json()["models"]
    rows = [m for g in models["groups"] for m in g["models"]]
    total = len(rows)
    size = page.locator('#models-table th[data-sort="size"] .sort-button')
    size.click()
    size.click()
    marks = _models_sort_marks(r)
    problems = _models_order_problems(r, "size", descending=True)
    r.check(
        marks["size"] == "descending"
        and all(v is None for k, v in marks.items() if k != "size")
        and not problems,
        "tableau : « Taille » deux fois, décroissant par taille dans chaque groupe, inconnues "
        "en dernier, aria-sort=descending sur cet en-tête seul",
        f"{marks} · " + "; ".join(problems[:4]),
    )
    window = page.locator('#models-table th[data-sort="window"] .sort-button')
    window.focus()
    page.keyboard.press("Enter")
    marks = _models_sort_marks(r)
    problems = _models_order_problems(r, "window", descending=False)
    r.check(
        marks["window"] == "ascending" and marks["size"] is None and not problems,
        "tableau : Entrée sur « Fenêtre », croissant par fenêtre, aria-sort passé à cet en-tête",
        f"{marks} · " + "; ".join(problems[:4]),
    )
    r.check(
        page.locator("#models-table thead th", has_text="Prix").locator("button").count() == 0,
        "tableau : le prix ne se trie pas",
    )

    page.select_option("#filter-hosting", "network")
    page.fill("#filter-text", "gem")
    expected = sorted(
        m["value"]
        for m in rows
        if m["hosting"] == "network" and "gem" in _folded(f"{m['name']} {m['publisher_text']}")
    )
    shown = sorted(_models_visible_values(r))
    status = page.inner_text("#models-status")
    word = "modèle" if len(expected) <= 1 else "modèles"
    local_hidden = page.eval_on_selector_all(
        "#models-table tbody",
        "bs => bs.every(b => b.hidden || [...b.querySelectorAll('tr[data-value]')]"
        ".some(tr => !tr.hidden))",
    )
    r.check(
        bool(expected)
        and shown == expected
        and status == f"{len(expected)} {word} sur {total}"
        and local_hidden,
        "filtres : réseau + « gem », les seules lignes réseau dont le nom ou l'éditeur contient "
        "« gem », compteur « n modèles sur N », groupes vides masqués",
        f"{shown} · attendu {expected} · « {status} »",
    )
    r.shot("44b-modeles-filtres", full_page=True)

    page.fill("#filter-text", "zzz")
    empty = page.locator("#models-empty")
    expect(empty).to_be_visible(timeout=5000)
    r.check(
        page.locator("#models-table").is_hidden()
        and "Aucun modèle ne correspond à ces filtres." in empty.inner_text()
        and page.inner_text("#models-status") == f"0 modèle sur {total}",
        "filtres : « zzz », aucun résultat, message dédié, tableau masqué",
        page.inner_text("#models-status"),
    )
    page.locator("#models-empty-reset").click()
    shown = _models_visible_values(r)
    r.check(
        empty.is_hidden()
        and len(shown) == total
        and page.input_value("#filter-text") == ""
        and page.input_value("#filter-hosting") == ""
        and page.inner_text("#models-status").startswith(f"{total} modèles"),
        "« Réinitialiser les filtres » : toutes les lignes de nouveau, compteur entier",
        f"{len(shown)} / {total} · {page.inner_text('#models-status')}",
    )

    reasoning = page.locator('#models-table th[data-sort="reasoning"] .sort-button')
    reasoning.click()
    ranks = {"always": 0, "toggle": 1, "never": 2}
    problems = _models_order_problems(r, "reasoning", descending=False, ranks=ranks)
    r.check(
        _models_sort_marks(r)["reasoning"] == "ascending" and not problems,
        "tableau : « Raisonnement », toujours < activable < jamais dans chaque groupe, "
        "inconnus en dernier",
        "; ".join(problems[:4]),
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
        expected = sorted(m["value"] for m in rows if keep(m))
        shown = sorted(_models_visible_values(r))
        r.check(
            option is not None and bool(expected) and shown == expected,
            f"filtres : {label}, ses seules lignes",
            f"{len(shown)} affichées · attendu {len(expected)} · "
            f"en trop {sorted(set(shown) - set(expected))[:4]} · "
            f"manquantes {sorted(set(expected) - set(shown))[:4]}",
        )
        page.locator("#filters-reset").click()


def _models_window_then_network(r: Run) -> None:
    """German, at the width of the moment: sort by « Fenster », then the « Netzwerk » filter;
    the network rows only, by window in their group, the count right (AC of story 3)."""
    page = r.page
    rows = [
        m for g in r.api("GET", "/api/diagnostic").json()["models"]["groups"] for m in g["models"]
    ]
    network = sorted(m["value"] for m in rows if m["hosting"] == "network")
    page.locator('#models-table th[data-sort="window"] .sort-button').click()
    page.select_option("#filter-hosting", "network")
    option = page.eval_on_selector("#filter-hosting", "s => s.selectedOptions[0].textContent")
    shown = sorted(_models_visible_values(r))
    problems = _models_order_problems(r, "window", descending=False)
    status = page.inner_text("#models-status")
    word = "Modell" if len(network) == 1 else "Modelle"
    r.check(
        bool(network)
        and option == "Netzwerk"
        and shown == network
        and not problems
        and status == f"{len(network)} {word} von {len(rows)}",
        "de : « Fenster » puis « Netzwerk », les seules lignes réseau, par fenêtre dans leur "
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
            and page.locator("#candidates li").count() == 0,
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
    expect(page.locator("#candidates li").first).to_be_visible(timeout=20_000)
    r.check(
        search.is_hidden() and "Aucun candidat trouvé." not in page.inner_text("#candidates"),
        "diagnostic, recherche finie : la liste des candidats, sans message de recherche",
    )


def _open_models_page(r: Run) -> None:
    r.page.goto(f"{r.stack.app_url}/models")
    expect(r.page.locator("#models-table tbody tr").first).to_be_visible(timeout=10_000)


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
    # gpt-oss),
    # declared without a key, come in the table's order before.
    expected = [
        "Sur ce poste · Qwen (Alibaba)",
        "Réseau · Gemma (Google)",
        "Réseau · Gemini (Google)",
        "Réseau · Mistral (Mistral AI)",
        "Réseau · gpt-oss (OpenAI)",
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

    # « Tableau des modèles… » noted, then « Ouvrir le tableau »: `/models`, same tab.
    page.select_option("#model-picker", label=PICK_MODELS_LABEL)
    apply = page.locator("#model-picker-apply")
    r.check(apply.inner_text() == "Ouvrir le tableau", "bouton « Ouvrir le tableau »")
    apply.click()
    page.wait_for_url(f"{r.stack.app_url}/models", timeout=10_000)
    expect(page.locator("#models-table tbody tr").first).to_be_visible(timeout=10_000)
    current = page.locator('.site-nav a[aria-current="page"]')
    r.check(current.inner_text() == "Modèles", "page /models : lien « Modèles » courant")
    r.check(
        page.locator(".site-nav a", has_text="Diagnostic").get_attribute("href") == "/diagnostic",
        "page /models : le lien « Diagnostic » de la barre commune mène à /diagnostic",
    )
    llama = _models_row(r, f"server:llama_server/{LLAMA_FILE}")
    r.check(
        llama.get("publisher") == "Qwen (Alibaba)"
        and llama.get("tools", "").startswith("oui")
        and llama.get("reasoning") == "activable"
        and llama.get("window") == "4 096 tokens"
        and llama.get("price") == "—",
        "tableau : faux llama-server Qwen, outils oui, raisonnement activable, 4 096 tokens, "
        "prix « — »",
        str(llama),
    )
    reasoning_r = _models_row(r, f"cloud:{REASONING_ENTRY_ID}")
    r.check(reasoning_r.get("reasoning") == "toujours", "tableau : modèle R « toujours »")
    gemini = _models_row(r, "cloud:gemini")
    r.check(
        gemini.get("model") == "RÉSEAU · Google AI Studio"
        and gemini.get("model_why") == "gemini-3.5-flash-lite"
        and gemini.get("publisher") == "Gemini (Google)"
        and gemini.get("reasoning") == "activable"
        and gemini.get("state") == "indisponible"
        and "clé API" in gemini.get("state_why", "")
        and gemini.get("price") == "0,30 $ / 2,50 $"
        and "par million de tokens" in gemini.get("price_why", ""),
        "tableau : préréglage Gemini, éditeur « Gemini (Google) », raisonnement « activable », "
        "indisponible sans clé, avec la raison, prix « 0,30 $ / 2,50 $ » par million de tokens",
        str(gemini),
    )
    gemma = _models_row(r, "cloud:gemma")
    r.check(
        gemma.get("model") == "RÉSEAU · Google AI Studio"
        and gemma.get("model_why") == "gemma-4-26b-a4b-it"
        and gemma.get("publisher") == "Gemma (Google)"
        and gemma.get("reasoning") == "activable"
        and gemma.get("size") == "26 B"
        and gemma.get("state") == "indisponible"
        and gemma.get("price") == "—",
        "tableau : préréglage Gemma, éditeur « Gemma (Google) », raisonnement « activable », "
        "« 26 B » lu dans le nom, indisponible sans clé, prix « — » (gratuit, sans pricing)",
        str(gemma),
    )
    fake_a = _models_row(r, f"cloud:{MODEL_ENTRY_ID}")
    r.check(fake_a.get("reasoning") == "jamais", "tableau : wavestack-fake « jamais »")
    r.check(fake_a.get("state") == "actif", "tableau : la ligne du modèle actif dit « actif »")
    ollama = _models_row(r, "server:ollama/faux-ollama:latest")
    r.check(
        ollama.get("reasoning") == "inconnu" and "introuvable" in ollama["reasoning_why"],
        "tableau : faux Ollama « inconnu », raison visible « introuvable »",
        str(ollama),
    )
    network = page.locator("#models-table tr[data-value^='cloud:']")
    rows = network.all_inner_texts()
    cloud_count = len(r.api("GET", "/api/diagnostic").json()["cloud"]["models"])
    r.check(
        len(rows) == cloud_count >= 3 and all("RÉSEAU" in t for t in rows),
        "tableau : chaque ligne réseau montre « RÉSEAU »",
        f"{len(rows)} lignes, {cloud_count} modèles cloud",
    )
    tag = network.first.locator(".hosting-tag-network")
    r.check(
        r.css(tag, "background-color") == r.token_color("--color-hosting-network"),
        "tableau : étiquette réseau sur le jeton jaune",
    )
    r.check(
        page.locator("#models-table th[scope='rowgroup']").all_inner_texts() == labels
        and page.locator("#models-table caption").count() == 1,
        "tableau : une légende, et un en-tête par groupe, ceux du sélecteur",
        str(page.locator("#models-table th[scope='rowgroup']").all_inner_texts()),
    )
    r.check(
        "Capacités lues comme au chargement" in page.inner_text("body"),
        "tableau : « Capacités lues comme au chargement… »",
    )
    r.shot("44-modeles-tableau", full_page=True)
    _models_sort_and_filters(r)  # story 3 of 2026-09-30
    page.locator(".site-nav a", has_text="Diagnostic").click()
    page.wait_for_url(f"{r.stack.app_url}/diagnostic", timeout=10_000)
    r.check(
        page.locator('.site-nav a[aria-current="page"]').inner_text() == "Diagnostic"
        and page.locator(".site-nav a", has_text="Modèles").get_attribute("href") == "/models",
        "diagnostic : même barre commune, « Diagnostic » courant",
    )
    _diagnostic_search_shown(r)  # story 3 of 2026-09-30

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
            locked and row.get("reasoning") == "toujours" and row.get("state") == "actif",
            "modèle R actif : carte verrouillée et ligne « toujours », « actif »",
            str(row),
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
        "retour à l'entrée A : ligne « jamais », carte indisponible « ne déclare pas de "
        "raisonnement »",
        f"{row.get('reasoning')} · {reason}",
    )
    _models_page_language(r)
    r.goto_app()


def _models_page_language(r: Run) -> None:
    """Story 2 (2026-09-30): on `/models`, the conversation empty, « English » in « Affichage ▾ »
    of the shared bar: the page reloads in English. Back to French after."""
    page = r.page
    r.goto_app()
    r.launch("bare_llm")
    r.send("Bonjour")
    r.wait_idle()
    page.goto("about:blank")  # an open main screen would reload itself on `language_changed`
    page.goto(f"{r.stack.app_url}/models")
    expect(page.locator("#models-table tbody").first).to_be_attached(timeout=20_000)
    try:
        picker = page.locator("#language-picker")
        panel = page.locator("#display-menu-panel")
        # A conversation under way: the picker locked, its tooltip says why.
        _open_display(page)
        ok, took = r.poll(lambda: picker.is_disabled(), 10)
        title = picker.get_attribute("title") or ""
        r.check(
            ok and "Videz d'abord la conversation" in title,
            "/models, un tour joué : sélecteur de langue désactivé, l'infobulle dit de vider "
            "la conversation",
            f"{title} ({took:.1f} s)",
        )
        cleared = r.api("POST", "/api/intentions/clear_conversation", {})
        _close_display(page)
        _open_display(page)  # the state read again at each opening
        ok, took = r.poll(lambda: picker.is_enabled(), 10)
        r.check(
            cleared.status_code == 200 and ok,
            "/models, conversation vidée, menu rouvert : sélecteur de langue actif",
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
                "/models, refus (409) : la raison dans « Affichage ▾ », le sélecteur de nouveau "
                "actif, sur « Français »",
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
            "/models : Échap ferme « Affichage ▾ », le focus revient sur sa face, le refus "
            "s'efface",
            f"focus sur {focused}",
        )
        _open_display(page)
        page.locator("h1").click()
        r.check(panel.is_hidden(), "/models : un clic hors du menu ferme « Affichage ▾ »")
        _open_display(page)
        ok, _ = r.poll(lambda: picker.is_enabled(), 10)
        seq = r.ev.mark()
        with page.expect_navigation(timeout=15_000):  # the page reloads, as on the main screen
            picker.select_option("en")
        r.ev.wait("language_changed", seq, lambda p: p["language"] == "en", timeout=15)
        expect(page.locator("#models-table tbody").first).to_be_attached(timeout=20_000)
        home = page.locator(".site-nav > a:not(.site-nav-brand)").first.inner_text()
        current = page.locator('.site-nav a[aria-current="page"]').inner_text()
        r.check(
            page.url.endswith("/models")
            and _html_lang(r) == "en"
            and (home, current) == ("Workshop", "Models")
            and page.locator("#language-picker-code").inner_text() == "EN",
            "/models : « English » choisi, la page se recharge en anglais (barre commune "
            "« Workshop », « Models » courant, « EN »)",
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
    label, _, amounts = text.partition("\n")
    title = top.get_attribute("title") or ""
    r.check(
        label == "Dépense estimée"
        and amounts.count(" $") == 2
        and " + " in amounts
        and spend.get("calls", 0) >= 2
        and title.startswith("Dépense API estimée de la séance : entrée ")
        and ", sortie " in title
        and " € au taux de " in title
        and top.get_attribute("aria-label") == title,
        "FinOps : « Dépense estimée » dans la barre de l'atelier, entrée + sortie, la phrase "
        "entière "
        "(euros compris) en infobulle et en nom accessible",
        f"{text!r} · {title} · {spend}",
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


def _footprint_line(r: Run) -> tuple[str, str]:
    """GreenOps: the « Empreinte estimée » line of the last call's body, and its tooltip."""
    _unfold_step(r, "Appelle le modèle")
    line = _step(r, "Appelle le modèle").locator(".turn-step-body .footprint")
    try:
        line.first.wait_for(timeout=5000)
    except Exception:  # noqa: BLE001 - said in the check's detail
        body = _step(r, "Appelle le modèle").locator(".turn-step-body")
        return "", " | ".join(body.all_inner_texts())
    return line.first.inner_text(), line.first.get_attribute("title") or ""


def _session_footprint(r: Run, what: str) -> None:
    """GreenOps: the turn's footprint in its head, the session's in the top bar (its line when
    it fits, always its sentence), the bar whole. Alone (no spend yet), the footprint is the
    block's whole second line: it must show at 1600 px in normal mode."""
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
    r.check(
        "Empreinte estimée de la séance : " in title
        and " g CO₂e" in title
        and top.get_attribute("aria-label") == title
        and spend.get("impact_calls", 0) >= 1
        and (not grams or grams.endswith(" g CO₂e")),
        f"GreenOps ({what}) : l'empreinte de la séance dans la barre de l'atelier (sa phrase en "
        "infobulle, sa ligne quand elle tient)",
        f"{top.inner_text()!r} · {title} · {spend.get('impact_calls')}",
    )
    # The bar whole with the session's block, at every width of the themes' check, in normal
    # and in projection mode (the footprint's line then hides when it does not fit).
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
                    ok,
                    f"GreenOps ({what}) : barre entière avec l'empreinte, {width} × {height}, "
                    f"{mode} (ligne d'empreinte {'visible' if shown else 'en infobulle'})",
                    detail,
                )
                if projection:
                    _toggle_projection(page)
    finally:
        if toggle.get_attribute("aria-pressed") == "true":  # never left in projection mode
            _toggle_projection(page)
        page.set_viewport_size({"width": 1600, "height": 1000})
        time.sleep(0.3)
    if not spend.get("calls"):  # the footprint alone: it fits the widest bar
        r.check(
            visible.get("1600 mode normal") is True,
            f"GreenOps ({what}) : l'empreinte seule visible dans la barre à 1600 px (mode normal)",
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
        amounts = r.page.locator("#consumption-amounts").inner_text()
        r.check(
            label == "Empreinte estimée"
            and amounts.endswith(" g CO₂e")
            and "$" not in r.page.locator("#consumption").inner_text()
            and not amounts.lstrip().startswith("·"),
            "GreenOps : sans dépense, « Empreinte estimée » sur l'empreinte seule (ni « $ », ni "
            "« · » en tête)",
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
            thinking == {"thinking_level": "medium", "include_thoughts": True}
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
        link.is_visible() and link.inner_text() == "LLM nu",
        "barre commune : lien « LLM nu » visible et entier",
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
        page.locator("h1").inner_text() == "LLM nu : l'intérieur du modèle"
        and page.locator("nav.site-nav a[aria-current=page]").inner_text() == "LLM nu"
        and not _site_nav_problems(r),
        "/llm : titre, barre commune entière, « LLM nu » courant",
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
        and page.locator("#token-chips li").count() == 0,
        "cloud A : le tokenizer est chez le fournisseur, estimation, aucune puce",
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

    # (3c) The fake cloud A takes temperature and top-p only; top-k is disabled, with why.
    _set_lab_sampling(r)
    top_k = page.locator("#sampling-top_k")
    reason = page.inner_text('.sampling-row[data-setting="top_k"] .sampling-row-reason')
    r.check(
        top_k.is_disabled() and "non réglable chez Faux fournisseur (e2e)" in reason,
        "cloud A : top-k désactivé, sa raison visible",
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

    # (4) The fake llama-server, chosen in the workshop's picker.
    r.goto_app()
    _pick_served(r, LLAMA_OPTION)
    bubbles = page.locator("#chat .bubble").count()
    _goto_lab(r)
    expect(page.locator("#llm-model")).to_contain_text("Local · llama-server", timeout=5000)
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
    """Story 5 (2026-09-30): no model in process, no live distribution in section 2: the
    candidates' reason (naming `name`) instead of the bars; a direct read answers 404."""
    page = r.page
    expect(page.locator("#distribution-empty")).to_contain_text(name, timeout=5000)
    read = r.api("POST", "/api/llm_lab/distribution", {"index": 0, "sampling": _LAB_SAMPLING})
    r.check(
        page.locator("#distribution-body").is_hidden() and read.status_code == 404,
        f"{where} : distribution vivante indisponible, sa raison en section 2, lecture 404",
        f"{page.inner_text('#distribution-empty')} · {read.status_code}",
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


# ---------- story 30: the RAG workshop ----------

RAG_LAB_QUESTION = "Combien de jours de télétravail par semaine ?"
RAG_LAB_STAGES = [
    "Découpage",
    "Embedding",
    "Base vectorielle",
    "Recherche",
    "Reranking",
    "Construction du contexte",
    "Génération",
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


def _goto_rag_lab(r: Run) -> None:
    r.page.goto(f"{r.stack.app_url}/rag")
    expect(r.page.locator("body[data-rag-ready]")).to_be_attached(timeout=10_000)


def _rag_lab_run(r: Run, question: str = RAG_LAB_QUESTION) -> tuple[dict[str, Any], int]:
    """« Lancer la chaîne »: the run's end, and the mark before it."""
    page = r.page
    page.fill("#rag-question", question)
    expect(page.locator("#rag-run")).to_be_enabled(timeout=10_000)
    seq = r.ev.mark()
    page.click("#rag-run")
    ended = r.ev.wait("rag_lab_run_ended", seq, timeout=60)
    expect(page.locator("#rag-run")).to_be_enabled(timeout=10_000)
    return ended, seq


def _stage_ended(r: Run, seq: int, kind: str, lane: str = "a") -> dict[str, Any]:
    found = [
        e["payload"]
        for e in r.ev.since(seq, "rag_lab_stage_ended")
        if e["payload"]["kind"] == kind and e["payload"]["lane"] == lane
    ]
    return found[-1] if found else {}


def _result_card(r: Run, kind: str, lane: str = "a"):
    return r.page.locator(f'.rag-lane[data-lane="{lane}"] .rag-stage-card[data-kind="{kind}"]')


def s_rag_lab(r: Run) -> None:
    """Story 30, after `rag_rerank` (index built, both fake models on the workstation): the
    « Atelier RAG » link of the top bar, the chain drawn (seven cards, the shipped options,
    their explanations), a run on a question (each stage's input, output, excerpts, duration
    and memory), the same run after a reload, a 409 while a workshop turn runs. Back to `/`."""
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


def _rag_lab(r: Run, errors: list[str]) -> None:
    page = r.page
    r.goto_app()
    r.wait_idle()
    # (1) The link, whole in the shared bar (story 2 of 2026-09-30), which stays on one line.
    link = page.locator('.site-nav a[href="/rag"]')
    r.check(
        link.is_visible() and link.inner_text() == "Atelier RAG",
        "barre commune : lien « Atelier RAG » visible, entier, vers /rag",
        link.inner_text(),
    )
    ok, detail = _bar_fits(r)
    r.check(
        ok, "barre commune et barre de l'atelier entières, sur une ligne, à 1600 × 1000", detail
    )

    # (2) The chain: seven cards in order, their shipped options, their explanations.
    link.click()
    page.wait_for_url("**/rag")
    expect(page.locator("body[data-rag-ready]")).to_be_attached(timeout=10_000)
    cards = page.locator("#rag-chain .rag-chain-card")
    names = [cards.nth(i).locator(".rag-chain-name").inner_text() for i in range(cards.count())]
    r.check(names == RAG_LAB_STAGES, "/rag : sept cartes dans l'ordre de la chaîne", str(names))
    options = {
        page.locator(f'#rag-chain [data-kind="{kind}"] .rag-chain-option').inner_text()
        for kind in ("embedding", "vector_store", "rerank")
    }
    explained = all(
        len(cards.nth(i).locator(".rag-chain-explain").inner_text()) > 40
        for i in range(cards.count())
    )
    r.check(
        options == {"Faux embedding (e2e)", "sqlite-vec", "Faux reranker (e2e)"} and explained,
        "chaque carte nomme son option livrée et l'explique",
        str(options),
    )
    r.check(
        page.locator("nav.site-nav a[aria-current=page]").inner_text() == "Atelier RAG"
        and page.locator("select[data-theme-picker]").count() == 1
        and not _site_nav_problems(r),
        "/rag : barre commune entière, « Atelier RAG » courant, sélecteur de thème",
    )
    generation = page.locator('#rag-chain [data-kind="generation"]')
    r.check(
        r.css(generation, "background-color") == r.token_color("--color-ink-fill"),
        "la carte Génération repose sur l'encre (ink-fill), les autres en discipline context",
        r.css(generation, "background-color"),
    )
    light = _contrast_sweep(r, ["main", "nav.site-nav"])
    _pick_theme(page, "dark")
    dark = _contrast_sweep(r, ["main", "nav.site-nav"])
    _pick_theme(page, "system")
    r.check(not light and not dark, "/rag : contrastes AA en clair et en sombre", str(light + dark))
    r.shot("55-atelier-rag-chaine", full_page=True)

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
        started == set(RAG_LAB_STAGES_KINDS[:-1]),
        "une paire started/ended par étape exécutée, la génération non exécutée",
        str(sorted(started)),
    )
    statuses = page.evaluate("() => window.__ragStatuses")
    figures = [
        _result_card(r, kind).locator(".rag-stage-figures").inner_text()
        for kind in RAG_LAB_STAGES_KINDS[:-1]
    ]
    r.check(
        any(s.startswith("en cours") for s in statuses)
        and all(re.search(r"\d+ ms", f) and re.search(r"\d+ Mo", f) for f in figures),
        "chaque carte passe de « en cours » à une durée en ms et une mémoire en Mo",
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
        "Recherche : 8 extraits (rag_rerank_candidates) avec rang et score",
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
    context = _stage_ended(r, seq, "context")
    output = _result_card(r, "context").locator(".rag-stage-output").inner_text()
    r.check(
        len(context.get("items", [])) == 3
        and output.count("Extrait ") == 3
        and "Extrait 1 — " in output
        and "Extrait 3 — " in output,
        "Contexte : les 3 extraits (top_k) au format de la brique",
        output[:200],
    )
    gen = _result_card(r, "generation").inner_text()
    r.check(
        "non exécutée dans l'atelier rag" in gen.lower(),
        "Génération : « non exécutée dans l'atelier RAG »",
        gen[:200],
    )
    r.check(not errors, "aucune pageerror", str(errors[:3]))
    r.shot("56-atelier-rag-resultats", full_page=True)

    # (4) Reloaded: the same run, from `last_run`.
    run_id = ended["payload"]["run_id"]
    page.reload()
    expect(page.locator("body[data-rag-ready]")).to_be_attached(timeout=10_000)
    reloaded = page.locator(".rag-stage-card").count()
    summary = page.inner_text("#rag-run-summary")
    state = r.api("GET", "/api/rag_lab").json()
    r.check(
        reloaded == len(RAG_LAB_STAGES)
        and RAG_LAB_QUESTION in summary
        and state["last_run"][0]["payload"]["run_id"] == run_id,
        "après rechargement, le même run se réaffiche (last_run)",
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
    _rag_lab_compare(r)
    _rag_lab_alt(r)
    _rag_lab_hybrid(r)


def _chain_kinds(r: Run) -> list[str]:
    return r.page.eval_on_selector_all(
        "#rag-chain .rag-chain-card", "cards => cards.map(c => c.dataset.kind)"
    )


def _add_stage(r: Run, label: str) -> None:
    r.page.locator("#rag-palette-a select").select_option(label=label)
    r.page.locator("#rag-palette-a .rag-palette-add").click()
    time.sleep(0.8)  # the session's verdict (`/api/rag_lab/validate`, after a 200 ms pause)


def _stage_button(r: Run, kind: str, label: str):
    card = r.page.locator(f'#rag-chain .rag-chain-card[data-kind="{kind}"]')
    return card.get_by_role("button", name=label)


def _rag_lab_hybrid(r: Run) -> None:
    """Increment 4: the Reranking removed, « Recherche lexicale BM25 » added without a fusion
    (refused on its card, « Lancer » greyed), the Fusion added, the Reranking added back and
    moved after the Fusion by its buttons; a run: the Fusion gives each excerpt's rank in both
    searches and its RRF score. A Fusion moved before a search: refused, 409 if posted."""
    page = r.page
    page.locator("#rag-reset-chain").click()
    time.sleep(0.4)
    _stage_button(r, "rerank", "Retirer").click()
    _add_stage(r, "Recherche lexicale BM25")
    bm25 = page.locator('#rag-chain .rag-chain-card[data-kind="lexical_search"]')
    expect(bm25.locator(".rag-chain-refusal")).to_be_visible(timeout=5000)
    run = page.locator("#rag-run")
    r.check(
        "Deux recherches demandent une fusion après elles"
        in bm25.locator(".rag-chain-refusal").inner_text()
        and run.is_disabled()
        and "fusion" in (run.get_attribute("title") or ""),
        "BM25 sans fusion : la carte BM25 dit « Deux recherches demandent une fusion après "
        "elles », « Lancer » désactivé",
        bm25.locator(".rag-chain-refusal").inner_text(),
    )
    _add_stage(r, "Reranking")
    _add_stage(r, "Fusion")
    before = _chain_kinds(r)
    after_button = _stage_button(r, "rerank", "Déplacer après")
    after_button.focus()
    page.keyboard.press("Enter")  # by the keyboard, never by drag and drop
    time.sleep(0.8)
    kinds = _chain_kinds(r)
    r.check(
        before[3:7] == ["vector_search", "lexical_search", "rerank", "fusion"]
        and kinds[3:7] == ["vector_search", "lexical_search", "fusion", "rerank"]
        and _stage_button(r, "rerank", "Déplacer après").is_disabled()
        and not page.locator("#rag-chain .rag-chain-refusal").count(),
        "Reranking déplacé après la Fusion au clavier (« Déplacer après ») : chaîne valide",
        f"{before} → {kinds}",
    )
    expect(run).to_be_enabled(timeout=5000)
    ended, seq = _rag_lab_run(r)
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
        and "Recherche :" in first_row
        and "Recherche lexicale BM25 :" in first_row
        and re.search(r"0,0\d{3}", first_row) is not None,
        "Fusion : le rang de chaque extrait dans les deux recherches et son score RRF",
        first_row.replace("\n", " | ")[:240],
    )
    r.shot("58-atelier-rag-hybride", full_page=True)
    # The Fusion moved before a search: its card says why, and a POST anyway is refused.
    _stage_button(r, "fusion", "Déplacer avant").click()
    time.sleep(0.4)
    fusion_card = page.locator('#rag-chain .rag-chain-card[data-kind="fusion"]')
    expect(fusion_card.locator(".rag-chain-refusal")).to_be_visible(timeout=5000)
    chain = page.evaluate("() => JSON.parse(localStorage.getItem('wavestack.ragLab')).pipelines")
    refused = r.api(
        "POST", "/api/intentions/rag_lab_run", {"question": RAG_LAB_QUESTION, "pipelines": chain}
    )
    r.check(
        "Fusion" in fusion_card.locator(".rag-chain-refusal").inner_text()
        and run.is_disabled()
        and refused.status_code == 409
        and "« Fusion »" in refused.json().get("detail", ""),
        "Fusion déplacée avant une recherche : la raison nomme la Fusion, 409 si l'on poste",
        f"{refused.status_code} {refused.text[:160]}",
    )
    page.locator("#rag-reset-chain").click()


def _rag_lab_alt(r: Run) -> None:
    """Increment 3: the scenario follows the catalog. Without the `rag-alt` extra, FAISS and
    LanceDB are greyed with the command that installs them; with it, A = sqlite-vec and B =
    FAISS give the same context, B's index built then read, its import's memory said."""
    page = r.page
    state = r.api("GET", "/api/rag_lab").json()
    stores = next(s for s in state["catalog"]["stages"] if s["kind"] == "vector_store")
    faiss = next(o for o in stores["options"] if o["id"] == "faiss")
    page.locator("#rag-reset-chain").click()
    page.locator("#rag-compare").check()
    select = page.locator('#rag-chain-b [data-kind="vector_store"] select.rag-option')
    expect(select).to_be_visible(timeout=5000)
    if not faiss["available"]:
        print("  (branche : sans l'extra rag-alt)")
        disabled = select.locator("option:disabled").all_inner_texts()
        reasons = page.locator(
            '#rag-chain-b [data-kind="vector_store"] .rag-chain-unavailable'
        ).all_inner_texts()
        r.check(
            any(t.startswith("FAISS") for t in disabled)
            and any(t.startswith("LanceDB") for t in disabled)
            and len(reasons) == 2
            and all("uv sync --extra compression --extra rag-alt" in t for t in reasons),
            "sans l'extra : FAISS et LanceDB désactivés, la raison donne la commande",
            str(reasons)[:300],
        )
        page.locator("#rag-reset-chain").click()
        return
    print("  (branche : avec l'extra rag-alt)")
    _set_stage(r, "b", "vector_store", "faiss")
    figures = []
    for _ in range(2):
        ended, seq = _rag_lab_run(r)
        store = _stage_ended(r, seq, "vector_store", "b")
        contexts = [_stage_ended(r, seq, "context", lane).get("items", []) for lane in "ab"]
        figures.append((ended["payload"]["status"], store, contexts))
    (status, first, contexts), (_, second, _) = figures
    same = [(i["rank"], i["chunk_id"]) for i in contexts[0]] == [
        (i["rank"], i["chunk_id"]) for i in contexts[1]
    ]
    facts = {f["label_text"]: f["value_text"] for f in first.get("facts", [])}
    card = _result_card(r, "vector_store", "b").inner_text()
    r.check(
        status == "ok" and same and len(contexts[0]) == 3,
        "avec l'extra : A = sqlite-vec et B = FAISS, mêmes extraits et mêmes rangs au Contexte",
        str([(i["rank"], i["doc_id"]) for i in contexts[1]]),
    )
    r.check(
        "construit (29 vecteurs)" in first.get("output_text", "")
        and "relu (29 vecteurs)" in second.get("output_text", "")
        and facts.get("Import", "").startswith(("premier import : +", "déjà fait"))
        and "premier import" in card.lower(),
        "Base vectorielle de B : « construit », puis « relu », et la mémoire ajoutée à l'import",
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


def _set_stage(r: Run, lane: str, kind: str, option: str | None = None, **params: int) -> None:
    card = r.page.locator(f'.rag-chain[data-lane="{lane}"] .rag-chain-card[data-kind="{kind}"]')
    if option is not None:
        card.locator("select.rag-option").select_option(option)
        card = r.page.locator(f'.rag-chain[data-lane="{lane}"] .rag-chain-card[data-kind="{kind}"]')
    for name, value in params.items():
        field = card.locator(f'input[data-param="{name}"]')
        field.fill(str(value))
        field.dispatch_event("change")


def _rag_lab_compare(r: Run) -> None:
    """Increment 2: A = the shipped chain (sqlite-vec, 700 characters), B = the exhaustive
    search in memory, 300 characters, `top_k` 2; two runs (computed, then read from the
    cache); a chain with fewer candidates than excerpts is refused with its reason."""
    page = r.page
    status_before = _git_status()
    lab_dir = r.stack.data_dir / "rag_lab"
    folders_before = set(lab_dir.iterdir()) if lab_dir.is_dir() else set()
    page.locator("#rag-reset-chain").click()
    page.locator("#rag-compare").check()
    expect(page.locator("#rag-chain-b .rag-chain-card")).to_have_count(7, timeout=5000)
    store = page.locator('#rag-chain-b [data-kind="vector_store"] select.rag-option')
    labels = store.locator("option").all_inner_texts()
    r.check(
        "Recherche exhaustive en mémoire" in labels and "sqlite-vec" in labels,
        "chaîne B : la base vectorielle propose sqlite-vec et la recherche en mémoire",
        str(labels),
    )
    _set_stage(r, "b", "vector_store", "memory")
    _set_stage(r, "b", "chunking", chunk_max_chars=300)
    _set_stage(r, "b", "context", top_k=2)
    ended, seq = _rag_lab_run(r)
    lanes = page.locator(".rag-lane")
    embedding_b = _result_card(r, "embedding", "b").inner_text()
    context_b = _stage_ended(r, seq, "context", "b")
    r.check(
        ended["payload"]["status"] == "ok"
        and lanes.count() == 2
        and "calculés (77 passages)" in embedding_b
        and len(context_b.get("items", [])) == 2
        and _result_card(r, "context", "b").locator("tbody tr").count() == 2,
        "comparaison : deux colonnes, B calcule ses 77 passages et garde 2 extraits",
        embedding_b[:240],
    )
    summary = page.inner_text("#rag-comparison")
    comparison = ended["payload"]["comparison"] or {}
    r.check(
        "En commun" in summary
        and ("Écarts de rang" in summary or "Aucun écart de rang" in summary)
        and comparison.get("summary_text", "")[:40] in summary,
        "la synthèse nomme les extraits communs et les écarts de rang",
        summary[:300],
    )
    folders = set(lab_dir.iterdir()) if lab_dir.is_dir() else set()
    r.check(
        len(folders - folders_before) == 1 and _git_status() == status_before,
        "un dossier nouveau sous rag_lab_dir(), aucun fichier créé dans le dépôt",
        f"{sorted(p.name for p in folders)} · git « {_git_status()[:120]} »",
    )
    r.shot("57-atelier-rag-comparaison", full_page=True)
    ended, seq = _rag_lab_run(r)
    r.check(
        "relus du cache" in _result_card(r, "embedding", "b").inner_text(),
        "second run : l'Embedding de B dit « relus du cache »",
    )
    # The chains are remembered by the browser, the comparison too. Languages (2/5): saved in
    # the former format, each chain's label named `label_fr`, they are read again.
    page.evaluate(
        "() => { const key = 'wavestack.ragLab';"
        " const saved = JSON.parse(localStorage.getItem(key));"
        " saved.pipelines = saved.pipelines.map((p, i) => {"
        " const { label_text: _, ...rest } = p;"
        " return { label_fr: `Chaîne ${'AB'[i]}`, ...rest }; });"
        " localStorage.setItem(key, JSON.stringify(saved)); }"
    )
    page.reload()
    expect(page.locator("body[data-rag-ready]")).to_be_attached(timeout=10_000)
    kept = page.locator('#rag-chain-b [data-kind="chunking"] input[data-param="chunk_max_chars"]')
    lanes = [page.locator(f"{q} .rag-chain-card").count() for q in ("#rag-chain", "#rag-chain-b")]
    r.check(
        page.locator("#rag-compare").is_checked() and kept.input_value() == "300" and all(lanes),
        "après rechargement, les chaînes A et B sont gardées (localStorage), relues depuis "
        "l'ancien format (label_fr)",
        f"cartes {lanes}",
    )
    # Fewer candidates than excerpts kept: the session's reason on the card (increment 4
    # validates each change), « Lancer » greyed; posted anyway, the 409's reason.
    _set_stage(r, "b", "vector_search", candidates=1)
    seq = r.ev.mark()
    card = page.locator('#rag-chain-b .rag-chain-card[data-kind="vector_search"]')
    expect(card.locator(".rag-chain-refusal")).to_be_visible(timeout=5000)
    said = card.locator(".rag-chain-refusal").inner_text()
    chain = page.evaluate("() => JSON.parse(localStorage.getItem('wavestack.ragLab')).pipelines")
    refused = r.api(
        "POST", "/api/intentions/rag_lab_run", {"question": RAG_LAB_QUESTION, "pipelines": chain}
    )
    time.sleep(0.3)
    r.check(
        "Recherche" in said
        and "candidat" in said
        and page.locator("#rag-run").is_disabled()
        and refused.status_code == 409
        and said in refused.json().get("detail", "")
        and not r.ev.since(seq, "rag_lab_run_started"),
        "candidats < top_k : la page affiche la raison du 409, « Lancer » grisé, rien ne s'exécute",
        f"{said} · {refused.status_code}",
    )
    page.locator("#rag-reset-chain").click()
    r.check(
        not page.locator("#rag-compare").is_checked()
        and page.locator("#rag-chain-b .rag-chain-card").count() == 0,
        "« Revenir à la chaîne livrée » : une seule chaîne, la livrée",
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
    ("network_tools", s_network_tools),
    ("disciplines", s_disciplines),
    ("themes", s_themes),
    ("linked_view", s_linked_view),
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
    ("compression", s_compression),
    ("busy_and_stop", s_busy_and_stop),
    ("reload_and_reset", s_reload_and_reset),
    ("language", s_language),
    ("ui_language", s_ui_language),
    ("content_language", s_content_language),
    ("annex_language", s_annex_language),
    ("backend_language", s_backend_language),  # story 7 of 2026-09-30 (languages 5/5)
    ("stream_resync", s_stream_resync),
    ("model_switch", s_model_switch),
    ("reasoning_locked", s_reasoning_locked),
    # GreenOps: the served model before the first priced call (the footprint alone).
    ("local_server", s_local_server),
    ("gemini_shape", s_gemini_shape),
    ("model_catalog", s_model_catalog),
    ("context_window", s_context_window),
    ("llm_screen", s_llm_screen),
    ("relaunch", s_relaunch),
]


def main() -> int:
    parser = argparse.ArgumentParser(description="Test de bout en bout de WaveStack (palier 1).")
    parser.add_argument("--only", nargs="*", help="scénarios à jouer (diagnostic toujours)")
    parser.add_argument("--keep", action="store_true", help="garder le dossier de données")
    parser.add_argument("--headed", action="store_true")
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
        try:
            browser = p.chromium.launch(headless=not args.headed)
        except Exception:  # noqa: BLE001 - another Playwright revision: the preinstalled one
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
