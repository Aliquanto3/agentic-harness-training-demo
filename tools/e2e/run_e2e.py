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
    MODEL_ENTRY_ID,
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
    expect(page.locator("#open-link")).to_be_visible(timeout=20_000)
    page.goto(f"{r.stack.app_url}/")
    expect(page.locator("#model-indicator")).to_contain_text("wavestack-fake", timeout=20_000)
    r.check(True, "l'indicateur de modèle de la barre haute montre le faux modèle")
    r.wait_idle()


def s_bare_llm(r: Run) -> None:
    r.launch("bare_llm")
    guide = r.page.locator("#scenario-guide")
    r.check(guide.is_visible() and "LLM nu" in guide.inner_text(), "consigne affichée")
    overflow, more = r.page.evaluate(
        "() => { const t = document.getElementById('scenario-guide-text');"
        " return [t.scrollHeight > t.clientHeight + 1,"
        " !document.getElementById('scenario-guide-more').hidden]; }"
    )
    r.check(
        overflow == more,
        "« Afficher plus » seulement si la consigne dépasse 3 lignes",
        f"déborde : {overflow} · bouton : {more}",
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
        label = card["label_fr"]
        expected = (
            card["reason_fr"] or f"La brique {label} est indisponible."
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
                lazy.is_disabled() and card["lazy_label_fr"] not in seen["summary"],
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
        bad[0]["payload"]["detail_fr"] if bad else "",
    )
    seq = r.ev.mark()
    ended = r.send("Bonjour [tool_use_failed]")
    bad = r.ev.since(seq, "tool_call_malformed")
    r.check(
        bool(bad),
        "tool_use_failed (400 du fournisseur) suit le chemin mal formé",
        bad[0]["payload"]["detail_fr"][:200] if bad else ended["payload"]["status"],
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
        errors = [e["payload"]["message_fr"] for e in r.ev.since(seq, "harness_error")]
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
            res.get("status") == "error" and "Service injoignable" in (res.get("error_fr") or ""),
            f"{tool} : échec réseau expliqué (réseau sortant coupé par le lanceur)",
            (res.get("error_fr") or str(res))[:300],
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
    """'' when `selector` is inside the viewport and its box, not cut by its own width."""
    return r.page.evaluate(
        "(q) => { const e = document.querySelector(q); if (!e) return 'absent';"
        " const b = e.getBoundingClientRect(); const bar = e.closest('.top-bar')"
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

    # The top bar: ink, the legend of the disciplines, the figures.
    ink = r.token_color("--color-ink")
    r.check(
        r.css(page.locator(".top-bar"), "background-color") == ink,
        "barre haute : fond --color-ink",
    )
    r.check(
        r.css(page.locator(".top-bar-title"), "color") == r.token_color("--color-on-ink"),
        "barre haute : titre en --color-on-ink",
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
        r.check(not over, f"{width} × {height} : la barre haute tient dans sa largeur", str(over))
        for selector in ("#gauge-legend", "#gauge-figures"):
            cut = _fully_visible(r, selector)
            r.check(not cut, f"{width} × {height} : {selector} entièrement visible", cut)
        if width == 1280:
            status = page.evaluate(
                "() => { const s = document.getElementById('top-status').getBoundingClientRect();"
                " return s.left >= 0 && s.right <= innerWidth + 1; }"
            )
            r.check(status, "1280 × 720 : le message de la barre haute tient dans la fenêtre")
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
        "dernière bulle de l'utilisateur : fond --color-ink, texte --color-on-ink",
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

    # Contexte LLM: every segment its discipline; the system prompt's rule and swatch.
    ctx = page.locator("#ctx .ctx-segment")
    disciplines = ctx.evaluate_all("ss => ss.map(s => s.dataset.discipline || '')")
    r.check(
        bool(disciplines) and all(disciplines),
        "Contexte LLM : chaque segment porte sa discipline",
        str(disciplines),
    )
    prompt = page.locator("#ctx .ctx-segment", has_text="(system_prompt)").first
    r.check(
        r.css(prompt, "border-left-color") == r.token_color("--color-discipline-prompt")
        and r.css(prompt.locator(".swatch"), "background-color")
        == r.token_color("--color-segment-system-prompt"),
        "segment du prompt système : filet de sa discipline, pastille de son type",
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
        "Orchestration : la tuile de l'appel au modèle a le fond --color-ink",
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
        "schéma : la plaque du modèle a le fond --color-ink",
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
    lit_segments = page.locator("#ctx .ctx-segment.is-linked").count()
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
    page.locator(".top-bar-title").hover()
    time.sleep(0.2)
    r.check(not _linking(r), "pointeur sur le titre de la barre haute : plus d'éclairage")

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
    flags = page.locator("#ctx .ctx-segment").evaluate_all(
        "ss => ss.map(s => s.classList.contains('is-linked'))"
    )
    r.check(
        bool(flags) and all(flags),
        "survol de la plaque du modèle : chaque segment de Contexte LLM s'éclaire",
        f"{sum(flags)} / {len(flags)}",
    )
    # The last call (« Répond ») is the one Contexte LLM shows: plate and segments; an older
    # call (« Appelle le modèle ») lights the plate and itself only (Design Notes).
    for name, segments in (("Répond", True), ("Appelle le modèle", False)):
        _step(r, name).locator(".turn-step-line").hover()
        time.sleep(0.2)
        flags = page.locator("#ctx .ctx-segment").evaluate_all(
            "ss => ss.map(s => s.classList.contains('is-linked'))"
        )
        lit = bool(flags) and (all(flags) if segments else not any(flags))
        r.check(
            _is_linked(plate.first) and lit,
            f"survol de « {name} » : plaque du modèle éclairée, segments "
            f"{'éclairés' if segments else 'non éclairés (appel plus ancien)'}",
            f"plaque {_is_linked(plate.first)}, segments {sum(flags)} / {len(flags)}",
        )

    # Keyboard: a focused segment, then a step line reached by Tab, light as the hover does.
    segment = page.locator("#ctx .ctx-segment").first
    segment.hover()
    time.sleep(0.2)
    hovered = page.evaluate(_LINKED_JS)
    r.rest_pointer()
    segment.focus()
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
        "() => ['#ctx .ctx-segment', '#orch-scroll .turn-step'].map((q) =>"
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
    toggle.click()
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
        "Mode projection : textes à 18 px, bouton pressé, barre haute sur une ligne à 1600 × 1000",
        f"{on} {size} {pressed} ; Réinitialiser : {cut or 'visible'} ; débordent : {over}",
    )
    r.shot("39-mode-projection")
    # At 1280 × 720, in projection mode, a selection shown on a hidden pane's chip.
    page.set_viewport_size({"width": 1280, "height": 720})
    node("Calculatrice").click()
    page.locator('.pane[data-pane="ctx"] .pane-hide').click()
    time.sleep(0.5)
    cut = _fully_visible(r, "#reset-button")
    over = page.evaluate(
        "() => { const bar = document.querySelector('.top-bar').getBoundingClientRect();"
        " return [...document.querySelectorAll('.top-bar > *')]"
        ".filter(e => e.offsetParent && getComputedStyle(e).position !== 'absolute')"
        ".filter(e => { const b = e.getBoundingClientRect();"
        " return b.right > bar.right + 1 || b.bottom > bar.bottom + 1 || b.top < bar.top - 1; })"
        ".map(e => e.id || e.className); }"
    )
    chip = page.locator("#pane-chips .pane-chip", has_text="Contexte LLM")
    readable = chip.evaluate("c => c.scrollWidth <= c.clientWidth + 1")
    r.check(
        not cut and not over and readable and "· lié" in chip.inner_text(),
        "1280 × 720 en mode projection : barre sur une ligne, « Réinitialiser » entier, "
        "« · lié » lisible sur la puce",
        f"Réinitialiser : {cut or 'visible'} ; débordent : {over} ; puce « {chip.inner_text()} », "
        f"entière : {readable}",
    )
    page.keyboard.press("Escape")
    chip.click()
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
    toggle.click()
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
        (results[-1].get("error_fr") or "")[:200] if results else "",
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
        dg.get("status") == "error" and bool(dg.get("error_fr")),
        "data.gouv.fr injoignable : échec expliqué",
        (dg.get("error_fr") or str(dg))[:300],
    )
    gauge = r.page.locator("#gauge-figures").inner_text()
    seq = r.ev.mark()
    ended = r.send("Que veut dire MCP ?")
    tools = [e["payload"]["tool"] for e in r.ev.since(seq, "tool_started")]
    r.check("local__define_term" in tools, "outil MCP local appelé", str(tools))
    r.check(
        "MCP" in r.last_answer() and ended["payload"]["status"] == "completed",
        "réponse issue du glossaire MCP",
        r.last_answer()[:200],
    )
    r.shot("10-mcp-documentation-complete")
    r.results.append((r.current, f"jauge avant envoi : {gauge}", True, ""))


def s_mcp_lazy(r: Run) -> None:
    r.launch("mcp_lazy")
    body_tools = None
    seq = r.ev.mark()
    ended = r.send("Que veut dire MCP ?")
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
    ended = r.send("Quels jeux de données publics existent sur la qualité de l'air ?")
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
    r.show_forced(False)


def s_skills(r: Run) -> None:
    r.launch("skills")
    seq = r.ev.mark()
    ended = r.send(
        "Rédige le compte rendu de cette réunion : Paul présente le budget, Julie valide le "
        "planning, prochaine réunion lundi à 10 h."
    )
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
    prompt = (
        "Délègue à ton sous-agent la lecture du fichier guide_harnais.md : il doit le lire et "
        "te rendre un résumé en cinq points. Puis présente-moi ce résumé. [lent]"
    )
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
    main_tab.click()
    text = ctx.inner_text()
    r.check(
        main_tab.get_attribute("aria-selected") == "true"
        and "Résultat du sous-agent" in text
        and guide not in text,
        "onglet « Agent principal » : le seul résultat, en « Résultat du sous-agent »",
    )
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
    delegate.click()
    expect(form).to_be_visible(timeout=5000)
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
    r.launch("data_flows")
    r.set_brick("MCP", True)
    time.sleep(1)
    seq = r.ev.mark()
    r.set_option("MCP", "data.gouv.fr", True)
    ended = r.ev.wait("mcp_connect_ended", seq, lambda p: p["server"] == "datagouv", 45)
    r.check(
        ended["payload"]["status"] == "error",
        "data.gouv.fr échoue, sans réseau",
        (ended["payload"].get("error_fr") or "")[:200],
    )
    time.sleep(0.5)
    arch = r.state()["architecture_changed"]
    crossing = [e for e in arch["edges"] if e.get("crosses_boundary")]
    r.check(
        any("datagouv" in e["from"] + e["to"] for e in crossing),
        "le flux vers data.gouv.fr franchit la frontière du poste",
        str(crossing)[:300],
    )
    local = [e for e in arch["edges"] if "mcp.local" in e["from"] + e["to"]]
    r.check(
        all(not e.get("crosses_boundary") for e in local),
        "le serveur MCP local reste sur le poste",
        str(local)[:200],
    )
    _datagouv_node_reveals_its_connection(r)
    _datagouv_connection_outbound(r, seq)
    r.shot("15-ou-vont-mes-donnees-schema")
    schema_fits(r, "data.gouv.fr")


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
        [f"Module {i} · {m['title_fr']} · {m['duration_min']} min", m["scenarios"]]
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
    } - {"reasoning"}
    r.launch(first)  # module 5, launched directly
    wanted = {k for k, b in r.bricks().items() if b["wanted"]}
    r.check(
        earlier <= wanted and "reasoning" not in wanted,
        "module 5 lancé directement : les briques des modules 1 à 4, sans le raisonnement",
        str(sorted(wanted)),
    )
    guide = r.page.locator("#scenario-guide")
    r.check(
        "sans le raisonnement" in guide.inner_text(),
        "la consigne dit que le raisonnement reste éteint",
    )
    r.launch("mcp_full")
    r.check(
        not r.bricks()["rag"]["wanted"] and "sauf le raisonnement et le RAG" in guide.inner_text(),
        "« MCP en documentation complète » : RAG éteint, la consigne le dit",
    )


def s_soc(r: Run) -> None:
    """FR-40, SOC: H2 logs the reads; the model looks for the privileged accounts' inventory
    itself and H1 blocks it; the audit log opens from the schema."""
    first, second = _prompts("soc")
    r.launch("soc")
    guide = r.page.locator("#scenario-guide")
    r.check("Métier SOC" in guide.inner_text(), "consigne du scénario SOC affichée")
    seq = r.ev.mark()
    ended = r.send(first)
    _folded_guide(r)
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

    # Story 22: left unfolded, the guide folds again when another scenario is launched.
    more = r.page.locator("#scenario-guide-more")
    more.click()
    expect(more).to_have_attribute("aria-expanded", "true", timeout=5000)
    r.launch("reasoning")
    folded = r.page.evaluate(
        "() => [document.getElementById('scenario-guide-more').getAttribute('aria-expanded'),"
        " document.getElementById('scenario-guide').classList.contains('is-expanded')]"
    )
    r.check(
        folded == ["false", False],
        "nouveau scénario : la consigne dépliée se replie",
        str(folded),
    )


def _folded_guide(r: Run) -> None:
    """Story 22 (C1): a long scenario guide holds 3 lines, « Afficher plus » unfolds it; the
    field and the last bubble stay in view."""
    text = r.page.locator("#scenario-guide-text")
    more = r.page.locator("#scenario-guide-more")
    measure = (
        "e => { const s = getComputedStyle(e);"
        " return [e.getBoundingClientRect().height, parseFloat(s.lineHeight)]; }"
    )
    height, line = text.evaluate(measure)
    r.check(
        height <= 3 * line + 1
        and more.is_visible()
        and more.get_attribute("aria-expanded") == "false",
        "consigne longue : 3 lignes au plus, « Afficher plus » visible",
        f"{height:.1f} px pour des lignes de {line:.1f} px",
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
    r.check(
        not missing, "consigne repliée : le champ et la dernière bulle restent visibles", missing
    )
    more.click()
    unfolded = text.evaluate(measure)[0]
    r.check(
        more.get_attribute("aria-expanded") == "true"
        and more.inner_text() == "Réduire"
        and unfolded > height,
        "« Afficher plus » : le texte entier, « Réduire »",
        f"{height:.1f} puis {unfolded:.1f} px",
    )
    missing = in_view()
    r.check(
        not missing, "consigne dépliée : le champ et la dernière bulle restent visibles", missing
    )
    more.click()
    r.check(
        more.get_attribute("aria-expanded") == "false" and more.inner_text() == "Afficher plus",
        "« Réduire » replie la consigne",
    )


def _public_server_offline(r: Run, server: str, label: str) -> None:
    # A server already enabled by the previous scenario is not contacted again (AD-15):
    # its last answer, from before `seq`, still stands.
    ends = {e["payload"]["server"]: e["payload"] for e in r.ev.since(0, "mcp_connect_ended")}
    ended = ends.get(server, {})
    r.check(
        ended.get("status") == "error" and bool(ended.get("error_fr")),
        f"{label} injoignable sans réseau : échec expliqué",
        (ended.get("error_fr") or str(ended))[:200],
    )
    arch = r.state()["architecture_changed"]
    drawn = next((n for n in arch["nodes"] if n["id"] == f"mcp.{server}"), {})
    r.check(
        drawn.get("hosting") == "network" and drawn.get("available") is False,
        f"schéma : {label} dessiné dans la zone Réseau, indisponible",
        str({k: drawn.get(k) for k in ("hosting", "available", "reason_fr")})[:200],
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
    _public_server_offline(r, "mslearn", "Microsoft Learn")
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
        and row.get_attribute("title") == rag["reason_fr"]
        and rerank.get_attribute("aria-description") == rag["reason_fr"],
        "RAG voulue mais indisponible : « Reranking » désactivé, raison de la brique au survol",
        f"« {row.get_attribute('title')} » · raison « {rag['reason_fr']} »",
    )

    # The file is not served yet: the download fails, explained on the card.
    seq = r.ev.mark()
    download.click()
    r.ev.wait("session_state", seq, lambda p: p["state"] == "download", 10)
    error = r.ev.wait("harness_error", seq, timeout=20)
    r.ev.wait("session_state", seq, lambda p: p["state"] == "idle", 20)
    effect = error["payload"].get("effect_fr") or ""
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
        index.get("kind") == "file" and f"{chunks} extraits" in (index.get("detail_fr") or ""),
        "schéma : le fichier d'index, local, avec son nombre d'extraits",
        str(index.get("detail_fr"))[:200],
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

    # Contexte LLM: the intro and three excerpts, labelled, before the message.
    labels = r.page.locator("#ctx .ctx-segment-label").all_inner_texts()
    rag_labels = [x for x in labels if x.startswith("Extraits RAG (rag)")]
    r.check(len(rag_labels) == 4, "Contexte LLM : 4 segments « Extraits RAG (rag) »", str(labels))
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
        scenario["prompts"][0] == RERANK_QUESTION and "{" not in scenario["description_fr"],
        "le premier prompt du scénario est celui que le parcours joue ; consigne chiffrée",
        scenario["description_fr"][:160],
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
    r.ev.wait(
        "bricks_changed",
        seq,
        lambda p: (
            (next(b for b in p["bricks"] if b["id"] == "rag").get("rerank") or {}).get("available")
            is True
        ),
        30,
    )
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


COMPRESSION_QUESTION = (
    "Lis le fichier journal_serveur.log et dis-moi quelle erreur grave la sauvegarde de cette "
    "nuit a rencontrée."
)


COMPRESSION_SECOND = "Dans le journal_serveur.log, à quelle heure le lot 12 a-t-il été copié ?"


def _compression_step(r: Run):
    """The last « Compression (…) » step of Orchestration."""
    name = r.page.locator(".turn-step-name", has_text="Compression (")
    return r.page.locator("#orch-scroll .turn-step", has=name).last


def s_compression(r: Run) -> None:
    """Story 20: a turn without then with the compression (Headroom, the real library), the
    step with the tokens before and after, the compressed segment and the total without
    compression in Contexte LLM, the compressor in the schema, « Comparer », a reload."""
    log = (REPO / "content" / "demo_files" / "journal_serveur.log").read_text(encoding="utf-8")
    error_line = next(line for line in log.splitlines() if " ERROR " in line)
    r.launch("compression")
    brick = r.bricks()["compression"]
    reason = brick.get("reason_fr") or ""
    if not brick["available"] and "uv sync --extra compression" in reason:
        # headroom-ai absent (the `compression` extra, or `--no-headroom`): a clean skip.
        text = r.card("Compression").inner_text()
        r.check(
            "uv sync --extra compression" in text,
            "headroom-ai absent : la carte donne la commande d'installation, scénario sauté",
            reason[:160],
        )
        seq = r.ev.mark()
        ended = r.send(COMPRESSION_QUESTION)
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
    ended = r.send(COMPRESSION_QUESTION)
    r.check(ended["payload"]["status"] == "completed", "tour sans compression terminé")
    r.check(not r.ev.since(seq, "compression_started"), "sans compression : aucune étape")
    body = json.dumps(r.fake_calls()[-1]["messages"], ensure_ascii=False)
    r.check("lot 12 copié" in body, "sans compression : le journal entier part au modèle")

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
        str([(i["source_fr"], i["tokens_before"], i["tokens_after"]) for i in tool_items]),
    )
    rag_items = [i for e in done for i in e["payload"]["items"] if i["kind"] == "rag_excerpt"]
    r.check(
        all(not i["changed"] for i in rag_items),
        "extraits RAG candidats, prose inchangée",
        f"{len(rag_items)} extraits",
    )
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
    ended = r.send(COMPRESSION_SECOND)
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


def s_busy_and_stop(r: Run) -> None:
    r.launch("bare_llm")
    seq = r.ev.mark()
    r.page.fill("#composer-input", "Explique le harnais [lent] [long]")
    r.page.press("#composer-input", "Enter")
    r.ev.wait("model_first_token", seq, timeout=20)
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
        ok and r.page.locator("#scenario-guide").is_visible(),
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
        "le message de réinitialisation ne déforme pas la barre haute",
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
        "barre haute : « Chargement du modèle … » avec chronomètre",
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
    r.check(ok, "barre haute : « Arrêt demandé » pendant la fin de l'étape", top.inner_text())
    ended = r.ev.wait("model_load_ended", seq, timeout=30)["payload"]
    r.check(
        ended["status"] == "cancelled"
        and ended["reason_fr"] == "Chargement arrêté : wavestack-fake est de nouveau actif.",
        "« Arrêter » : chargement arrêté, le modèle précédent est de nouveau actif",
        f"{ended['status']} · {ended['reason_fr']}",
    )
    ok = True
    try:
        expect(top).to_contain_text("Chargement arrêté", timeout=5000)
    except AssertionError:
        ok = False
    r.check(ok, "barre haute : issue « Chargement arrêté »", top.inner_text())
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


LLAMA_FILE = "faux-llama-server.gguf"
LLAMA_OPTION = f"Local · llama-server · {LLAMA_FILE}"


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
        options.get("Local · Ollama · faux-ollama:latest (incompatible)") is True,
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
    # Story 34: nothing left the workstation during that turn.
    summary = page.inner_text("#schema-outbound")
    r.check(
        "aucune donnée n'a quitté le poste" in summary,
        "bilan des sorties : aucune donnée n'a quitté le poste (modèle servi, outil local)",
        summary,
    )
    r.shot("23-serveur-local-llama-server")

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
    ("compression", s_compression),
    ("busy_and_stop", s_busy_and_stop),
    ("reload_and_reset", s_reload_and_reset),
    ("stream_resync", s_stream_resync),
    ("model_switch", s_model_switch),
    ("reasoning_locked", s_reasoning_locked),
    ("local_server", s_local_server),
    ("relaunch", s_relaunch),
]


def main() -> int:
    parser = argparse.ArgumentParser(description="Test de bout en bout de WaveStack (palier 1).")
    parser.add_argument("--only", nargs="*", help="scénarios à jouer (diagnostic toujours)")
    parser.add_argument("--keep", action="store_true", help="garder le dossier de données")
    parser.add_argument("--headed", action="store_true")
    parser.add_argument(
        "--no-headroom",
        action="store_true",
        help="WaveStack comme sans l'extra compression (le scénario compression est sauté)",
    )
    args = parser.parse_args()
    if args.no_headroom:  # read by `wavestack_e2e.py` through the stack's environment
        os.environ["WAVESTACK_E2E_NO_HEADROOM"] = "1"
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
            print(f"  - {e['payload']['message_fr'][:200]}")
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
