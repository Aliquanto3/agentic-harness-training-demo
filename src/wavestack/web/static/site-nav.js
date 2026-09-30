// Corrections of 2026-09-30, story 2: the navigation bar shared by the five pages
// (`nav.site-nav`, the same static HTML in each), and its « Affichage ▾ » menu: the theme
// (theme.js), the language and, on the main screen only, the projection mode (app.js's).
// One implementation for the five pages, loaded after i18n.js; app.js imports it.
//
// - The menu: opened and closed by its face, closed by a click outside it and by Escape (the
//   focus back on its face); `setDisplayMenu(open, returnFocus)` for the page's own chain.
// - The language picker: locked while the conversation is not empty (`language_locked`) or
//   outside `idle`, with the reason in its tooltip; a choice is an intention
//   (`POST /api/intentions/language`), the page reloads in the new language on success, and a
//   refusal is said under the picker.
// - Its state: from `/api/state` (read at load and at each opening of the menu), unless the
//   page gives it itself (`useSessionState()` then `renderLanguagePicker(info)`, app.js: the
//   main screen follows the session's events).

import { language, ready, t } from "./i18n.js";

let changing = false; // the intention is on its way: the page reloads on success
let external = false; // the page gives the picker's state (app.js)
let info = null; // {language, language_locked, idle, busy_text}, null while unknown
let onOpen = null;
let offered = false; // unlocked and idle at the last render: a refusal said is then cleared

const $ = (id) => document.getElementById(id);

export const languageChanging = () => changing;

// The page gives the state (`renderLanguagePicker`); `opened` runs at each opening of the menu
// (the main screen closes its « Volets ▾ » list).
export function useSessionState({ opened = null } = {}) {
  external = true;
  onOpen = opened;
}

export function setDisplayMenu(open, returnFocus = false) {
  const panel = $("display-menu-panel");
  const toggle = $("display-menu-toggle");
  if (!panel || panel.hidden === !open) return;
  panel.hidden = !open;
  toggle.setAttribute("aria-expanded", String(open));
  if (open) {
    onOpen?.();
    if (!external) refreshState();
    (panel.querySelector("select:not(:disabled), button") ?? toggle).focus();
  } else {
    sayRefusal(null); // said once, in the open menu
    if (returnFocus) toggle.focus();
  }
}

export const displayMenuOpen = () => $("display-menu-panel")?.hidden === false;

function sayRefusal(text) {
  const alert = $("display-menu-alert");
  if (!alert) return;
  alert.textContent = text ?? "";
  alert.hidden = !text;
}

// `next`: `{language, language_locked, idle, busy_text}`, or null when the lock is unknown
// (nothing to offer then).
export function renderLanguagePicker(next = info) {
  info = next;
  const picker = $("language-picker");
  if (!picker) return;
  const code = $("language-picker-code");
  const current = info?.language ?? language();
  if (code && code.textContent !== current.toUpperCase()) code.textContent = current.toUpperCase();
  if (!info) {
    picker.disabled = true;
    return;
  }
  const locked = Boolean(info.language_locked);
  // A refusal stays until the picker is offered again (the lock lifted, the turn over).
  const available = !locked && info.idle;
  if (available && !offered) sayRefusal(null);
  offered = available;
  if (picker.value !== info.language) picker.value = info.language;
  picker.disabled = locked || !info.idle || changing;
  const busy = info.busy_text || t("common.unavailable_outside_turn");
  const title = locked ? t("common.language.locked") : info.idle ? t("common.language.help") : busy;
  picker.title = title;
  const box = $("language-picker-box");
  if (box) box.title = title;
  picker.setAttribute("aria-label", t("common.language.name"));
}

// A page that does not follow the session's events reads its state again.
async function refreshState() {
  try {
    const body = await (await fetch("/api/state")).json();
    if (external) return;
    renderLanguagePicker(
      body.language
        ? {
            language: body.language,
            language_locked: Boolean(body.language_locked),
            // No `session_state` yet (the diagnostic's pages): idle, the server refusing if not.
            idle: !body.session_state || body.session_state.state === "idle",
            busy_text: body.session_state?.reason_text ?? null,
          }
        : null
    );
  } catch {
    if (!external) renderLanguagePicker(null); // no answer: the lock is unknown
  }
}

async function changeLanguage(event) {
  const wanted = event.target.value;
  const current = info?.language ?? language();
  event.target.value = current; // the option shown follows the session until the reload
  if (wanted === current) return;
  changing = true;
  sayRefusal(null);
  renderLanguagePicker();
  try {
    const response = await fetch("/api/intentions/language", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ language: wanted }),
    });
    if (response.ok) {
      location.reload(); // the page comes back in the new language
      return;
    }
    const detail = await response.json().catch(() => ({}));
    sayRefusal(typeof detail.detail === "string" ? detail.detail : t("common.language.refused"));
  } catch {
    sayRefusal(t("common.language.failed"));
  }
  changing = false;
  renderLanguagePicker();
  if (!external) refreshState(); // the lock or the turn that refused it, read again
}

// Bound at once (a module runs once the page is parsed), before the page's own listeners:
// Escape closes the menu first, and says so (`defaultPrevented`) to the page's chain.
function bind() {
  const toggle = $("display-menu-toggle");
  if (!toggle) return;
  toggle.addEventListener("click", () => setDisplayMenu($("display-menu-panel").hidden));
  document.addEventListener("click", (event) => {
    if (!event.target.closest(".display-menu")) setDisplayMenu(false);
  });
  document.addEventListener("keydown", (event) => {
    if (event.key !== "Escape" || !displayMenuOpen()) return;
    event.preventDefault();
    setDisplayMenu(false, true);
  });
  $("language-picker")?.addEventListener("change", changeLanguage);
  renderLanguagePicker(null); // its code at once, the picker locked until its state is known
  ready.then(() => {
    renderLanguagePicker();
    if (!external) refreshState();
  });
}

bind();
