// Story 9 (CAP-7, CAP-9): the barre commune's two buttons and their flyouts, the same static
// HTML in each of the five pages, one implementation (`bar.js`, loaded after site-nav.js,
// like it): « Dépense » (the session's spend and its economies, "Bilan de la séance") and
// « Journal » (the session's refusals and blocks, a 5-event preview).
//
// - Non modal, one open at a time (ux/EXPERIENCE.md bar-flyout): a click toggles its own
//   panel and closes the other; Escape closes the open one and returns the focus to its
//   button; a click outside both closes them too (a page change closes them for free, a
//   full navigation).
// - Its state: `GET /api/state` at load, and again each time a panel opens (as site-nav.js's
//   own picker does on the four pages that do not feed it live). The main screen's own
//   `/api/stream` reader already parses every envelope for its own render; it forwards
//   `consumption_updated` whole and `security_event` through `feedSecurityEvent`, in O(1),
//   never a walk of the journal (a structure that only grows during a session).

import { dateTimeFormat, numberFormat, ready, t } from "./i18n.js";

const $ = (id) => document.getElementById(id);

let consumption = null; // the `consumption_updated` shape, or null before any paid/impactful call
let preview = { denied_count: 0, entries: [] }; // newest first, 5 at most

export function feedConsumption(payload) {
  consumption = payload;
  renderSpend();
}

export function feedSecurityEvent(payload) {
  preview = {
    denied_count: payload.denied_count,
    entries: [
      {
        ts: payload.ts,
        source: payload.source,
        name: payload.name,
        decision: payload.decision,
        reason_text: payload.reason_text,
      },
      ...preview.entries,
    ].slice(0, 5),
  };
  renderLog();
}

async function refresh() {
  try {
    const body = await (await fetch("/api/state")).json();
    consumption = body.consumption_updated ?? null;
    preview = body.security_journal_preview ?? { denied_count: 0, entries: [] };
  } catch {
    // Kept as it was: a page briefly unreachable shows the last known state, not a blank one.
  }
  renderSpend();
  renderLog();
}

// ---------- formatting (figures are the session's; this only shapes them) ----------

const shortUsd = (n) =>
  n > 0 && n < 0.00005
    ? t("common.format.usd_below", { amount: numberFormat({ maximumFractionDigits: 4 }).format(0.0001) })
    : t("common.format.usd", { amount: numberFormat({ maximumFractionDigits: 4 }).format(n) });

// ---------- « Dépense » ----------

function economySaved(c) {
  return Math.max(0, (c.cache_saved_usd ?? 0) + (c.compression_saved_usd ?? 0));
}

function renderSpend() {
  const toggle = $("bar-spend-toggle");
  if (!toggle) return;
  toggle.hidden = !consumption;
  if (!consumption) return;
  const amount = $("bar-spend-amount");
  amount.textContent = shortUsd(consumption.total_usd);
  const saved = $("bar-spend-saved");
  const economy = economySaved(consumption);
  saved.textContent = t("common.bar.spend.saved", { amount: shortUsd(economy) });
  saved.hidden = false;
  toggle.setAttribute(
    "aria-label",
    `${t("common.bar.spend.label")} ${amount.textContent} · ${saved.textContent}`,
  );
  renderSpendPanel();
}

function renderSpendPanel() {
  const bars = $("bar-savings-bars");
  const summary = $("bar-spend-summary");
  if (!bars || !summary || !consumption) return;
  const real = consumption.total_usd;
  const economy = economySaved(consumption);
  const without = real + economy;
  bars.replaceChildren(savingsBar(t("common.bar.spend.without_optimization"), without), savingsBar(t("common.bar.spend.real_cost"), real));
  if (without <= 0) {
    summary.textContent = t("common.bar.spend.summary_none");
    return;
  }
  const percent = Math.round((100 * economy) / without);
  let text = t("common.bar.spend.summary", {
    percent: String(percent),
    cache: shortUsd(Math.max(0, consumption.cache_saved_usd ?? 0)),
    compression: shortUsd(Math.max(0, consumption.compression_saved_usd ?? 0)),
  });
  const kvSeconds = consumption.kv_time_saved_s;
  if (kvSeconds > 0) {
    text += ` ${t("common.bar.spend.summary_kv", { seconds: numberFormat({ maximumFractionDigits: 1 }).format(kvSeconds) })}`;
  }
  summary.textContent = text;
}

function savingsBar(label, amount) {
  const row = document.createElement("div");
  row.className = "bar-savings-row";
  const name = document.createElement("span");
  name.textContent = label;
  const track = document.createElement("span");
  track.className = "bar-savings-track";
  const input = document.createElement("i");
  input.className = "bar-savings-in";
  const output = document.createElement("i");
  output.className = "bar-savings-out";
  const total = (consumption.total_in_usd ?? 0) + (consumption.total_out_usd ?? 0) || 1;
  // The bar's own shares, from this session's cloud totals only (sub-agent calls already in
  // them, never added again): entrée/sortie, the only split cheap enough to show honestly.
  input.style.width = `${(100 * (consumption.total_in_usd ?? 0)) / total}%`;
  output.style.width = `${(100 * (consumption.total_out_usd ?? 0)) / total}%`;
  track.append(input, output);
  const value = document.createElement("span");
  value.textContent = shortUsd(amount);
  row.append(name, track, value);
  return row;
}

// ---------- « Journal » ----------

function renderLog() {
  const toggle = $("bar-log-toggle");
  if (!toggle) return;
  const count = $("bar-log-count");
  const n = preview.denied_count;
  count.textContent = t("common.bar.log.count", { count: n });
  count.hidden = n === 0;
  toggle.setAttribute(
    "aria-label",
    n === 0 ? t("common.bar.log.aria_label_zero") : t("common.bar.log.aria_label", { count: n }),
  );
  renderLogPanel();
}

function renderLogPanel() {
  const list = $("bar-log-list");
  if (!list) return;
  list.replaceChildren();
  if (preview.entries.length === 0) {
    const empty = document.createElement("p");
    empty.className = "bar-flyout-empty";
    empty.textContent = t("common.bar.log.empty");
    list.append(empty);
    return;
  }
  for (const entry of preview.entries) list.append(logRow(entry));
}

const LEVEL_OF = { allow: "low", allow_once: "low", deny: "high", blocked: "high", masked: "mid", cancelled: "mid", timeout: "high" };

function logRow(entry) {
  const row = document.createElement("li");
  row.className = "bar-log-row disclosure-row";
  const button = document.createElement("button");
  button.type = "button";
  button.className = "bar-log-row-head disclosure-row-head";
  const chevron = document.createElement("span");
  chevron.className = "disclosure-row-chevron";
  chevron.setAttribute("aria-hidden", "true");
  chevron.textContent = "▸";
  const name = document.createElement("span");
  name.className = "disclosure-row-label";
  name.textContent = entry.name;
  const chip = document.createElement("span");
  chip.className = `status-chip status-chip-${LEVEL_OF[entry.decision] ?? "mid"}`;
  chip.textContent = t(`common.bar.log.decisions.${entry.decision}`) || entry.decision;
  button.append(chevron, name, chip);
  const body = document.createElement("div");
  body.className = "disclosure-row-body";
  body.hidden = true;
  let when = entry.ts;
  try {
    when = dateTimeFormat({ timeStyle: "medium" }).format(new Date(entry.ts));
  } catch {
    // The raw ISO text stays rather than nothing.
  }
  const reason = document.createElement("p");
  reason.textContent = `${when} — ${entry.reason_text}`;
  body.append(reason);
  button.addEventListener("click", () => {
    body.hidden = !body.hidden;
    button.setAttribute("aria-expanded", String(!body.hidden));
    chevron.classList.toggle("is-open", !body.hidden);
  });
  button.setAttribute("aria-expanded", "false");
  row.append(button, body);
  return row;
}

// ---------- the two flyouts: non modal, one at a time ----------

const PANELS = [
  { toggle: "bar-spend-toggle", panel: "bar-spend-panel" },
  { toggle: "bar-log-toggle", panel: "bar-log-panel" },
];

function closeAll(returnFocus = null) {
  for (const { toggle, panel } of PANELS) {
    const btn = $(toggle);
    const flyout = $(panel);
    if (!btn || !flyout || flyout.hidden) continue;
    flyout.hidden = true;
    btn.setAttribute("aria-expanded", "false");
  }
  returnFocus?.focus();
}

function openPanel(toggleId, panelId) {
  const toggle = $(toggleId);
  const panel = $(panelId);
  if (!toggle || !panel) return;
  const opening = panel.hidden;
  closeAll();
  if (!opening) return; // it was the open one: the toggle above just closed it
  panel.hidden = false;
  toggle.setAttribute("aria-expanded", "true");
  refresh(); // fresh figures each time a panel opens (the four pages with no live feed)
}

function bind() {
  const spendToggle = $("bar-spend-toggle");
  const logToggle = $("bar-log-toggle");
  if (!spendToggle || !logToggle) return;
  spendToggle.addEventListener("click", (event) => {
    event.stopPropagation();
    openPanel("bar-spend-toggle", "bar-spend-panel");
  });
  logToggle.addEventListener("click", (event) => {
    event.stopPropagation();
    openPanel("bar-log-toggle", "bar-log-panel");
  });
  for (const link of document.querySelectorAll(".bar-flyout-link[data-href]")) {
    link.addEventListener("click", () => {
      location.href = link.dataset.href;
    });
  }
  document.addEventListener("click", (event) => {
    if (!event.target.closest(".bar-flyout") && !event.target.closest(".bar-button")) closeAll();
  });
  document.addEventListener("keydown", (event) => {
    if (event.key !== "Escape") return;
    const open = PANELS.find(({ panel }) => $(panel) && !$(panel).hidden);
    if (!open) return;
    event.preventDefault();
    closeAll($(open.toggle));
  });
  ready.then(refresh);
}

bind();
