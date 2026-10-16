// Story 9 (CAP-7, CAP-9): the barre commune's two buttons and their flyouts, the same static
// HTML in each of the five pages, one implementation (`bar.js`, loaded after site-nav.js,
// like it): « Dépense » (the session's spend and its economies, "Bilan de la séance") and
// « Journal » (the session's refusals and blocks, a 5-event preview).
//
// - Non modal, one open at a time (ux/EXPERIENCE.md bar-flyout): a click toggles its own
//   panel and closes the other; Escape closes the open one and returns the focus to its
//   button; a click outside both closes them too (a page change closes them for free, a
//   full navigation).
// - Its state: `GET /api/state` at load, and again each time a panel opens. Every page's own
//   `/api/stream` reader (app.js, llm.js, rag.js, mcp.js, the diagnostic's) hands each
//   envelope to `feedBar`, which keeps only `consumption_updated` and `security_event`, in
//   O(1), never a walk of the journal (a structure that only grows during a session). `seq`
//   orders the two sources: a snapshot older than the last event fed is ignored.
// - It replaces the main screen's former « Dépense estimée » gauge (ux/EXPERIENCE.md): the
//   panel carries what the gauge said (the euros, the cap, the footprint, the reset).

import { dateTimeFormat, has, numberFormat, rangeText, ready, t } from "./i18n.js";

const $ = (id) => document.getElementById(id);

let consumption = null; // the `consumption_updated` shape, or null before any paid/impactful call
let preview = { denied_count: 0, entries: [] }; // newest first, 5 at most
let maxSessionUsd = null; // finition V1 (#27): `[finops] max_session_usd`, from `/api/state`
let seq = 0; // the newest journal `seq` the figures above reflect

export function feedBar(envelope) {
  const kind = envelope.kind;
  if ((kind !== "consumption_updated" && kind !== "security_event") || envelope.seq <= seq) return;
  seq = envelope.seq;
  const payload = envelope.payload;
  if (kind === "consumption_updated") {
    consumption = payload;
    renderSpend();
    return;
  }
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
    maxSessionUsd = body.max_session_usd ?? null;
    // An answer older than an event already fed would put stale figures back.
    if ((body.seq ?? 0) >= seq) {
      seq = body.seq ?? 0;
      consumption = body.consumption_updated ?? null;
      preview = body.security_journal_preview ?? { denied_count: 0, entries: [] };
    }
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
const usd = (n) => t("common.format.usd", { amount: numberFormat({ maximumSignificantDigits: 4 }).format(n) });
const eur = (n) => t("common.format.eur", { amount: numberFormat({ maximumSignificantDigits: 4 }).format(n) });
// AD-4: « ≈ » on every amount of a session whose spend is (partly) estimated.
const guess = () => (consumption?.approx ? "≈ " : "");
const money = (n) => `${guess()}${shortUsd(n)}`;
const kvSeconds = (s) => numberFormat({ maximumFractionDigits: 1 }).format(s);

// ---------- « Dépense » ----------

// The session's net economy, signed (a cache write may cost more than its reads saved), or
// null when nothing priced was measured (never a fabricated « économisé 0 $ »).
function economy(c) {
  if (!c.saved_calls) return null;
  return (c.cache_saved_usd ?? 0) + (c.compression_saved_usd ?? 0);
}

function renderSpend() {
  const toggle = $("bar-spend-toggle");
  if (!toggle) return;
  toggle.hidden = !consumption;
  if (!consumption) return;
  const c = consumption;
  const amount = $("bar-spend-amount");
  amount.textContent = c.calls > 0 ? money(c.total_usd) : shortUsd(0);
  const saved = $("bar-spend-saved");
  const net = economy(c);
  if (c.calls > 0 && net !== null) {
    saved.textContent =
      net >= 0 ? t("common.bar.spend.saved", { amount: money(net) }) : t("common.bar.spend.overcost", { amount: money(-net) });
  } else if (c.kv_time_saved_s > 0) {
    // A local session costs nothing: the time the KV-cache saved is its one economy.
    saved.textContent = t("common.bar.spend.time_saved", { seconds: kvSeconds(c.kv_time_saved_s) });
  } else {
    saved.textContent = "";
  }
  saved.hidden = !saved.textContent;
  toggle.setAttribute(
    "aria-label",
    [`${t("common.bar.spend.label")} ${amount.textContent}`, saved.textContent].filter(Boolean).join(" · "),
  );
  toggle.title = detailSentence(c);
  renderSpendPanel();
}

// The former gauge's sentence: the spend in dollars and euros, the cap, the footprint, and
// what resets them.
function detailSentence(c) {
  const paid = c.calls > 0;
  const green = (c.impact_calls ?? 0) > 0;
  const sentences = [];
  if (paid) {
    sentences.push(
      t("main.consumption.spend_sentence", {
        input: `${guess()}${usd(c.total_in_usd)}`,
        output: `${guess()}${usd(c.total_out_usd)}`,
        total: `${guess()}${eur(c.total_eur)}`,
        rate: numberFormat({ maximumSignificantDigits: 4 }).format(c.eur_per_usd),
        calls: t("main.consumption.paid_calls", { count: c.calls }),
      }),
    );
    if (maxSessionUsd != null) {
      sentences.push(t("main.consumption.cap_sentence", { total: `${guess()}${usd(c.total_usd)}`, cap: usd(maxSessionUsd) }));
    }
  }
  if (green) {
    sentences.push(
      t("main.consumption.footprint_sentence", {
        energy: rangeText(c.energy_wh_min, c.energy_wh_max, "Wh"),
        grams: rangeText(c.gco2e_min, c.gco2e_max, "g CO₂e"),
        calls: t("common.count.call", { count: c.impact_calls }),
      }),
    );
  }
  sentences.push(paid && green ? t("main.consumption.reset_totals") : t("main.consumption.reset_total"));
  return sentences.join(" ");
}

function renderSpendPanel() {
  const bars = $("bar-savings-bars");
  const summary = $("bar-spend-summary");
  if (!bars || !summary || !consumption) return;
  const c = consumption;
  const paid = c.calls > 0;
  const real = c.total_usd;
  const net = economy(c);
  // Exact arithmetic: what the session would have cost with no cache nor compression; above
  // the real cost when they saved, below it when the cache's writes cost more.
  const without = real + (net ?? 0);
  const scale = Math.max(without, real) || 1;
  bars.replaceChildren(
    savingsBar(t("common.bar.spend.without_optimization"), without, scale),
    savingsBar(t("common.bar.spend.real_cost"), real, scale),
  );
  bars.hidden = !paid;
  const legend = document.querySelector(".bar-savings-legend");
  if (legend) legend.hidden = !paid;
  const lines = [];
  if (paid && net !== null && net < 0) {
    lines.push(t("common.bar.spend.summary_overcost", { amount: money(-net) }));
  } else if (paid && net !== null && without > 0) {
    lines.push(
      t("common.bar.spend.summary", {
        percent: String(Math.round((100 * net) / without)),
        cache: money(c.cache_saved_usd ?? 0),
        compression: money(c.compression_saved_usd ?? 0),
      }),
    );
  } else if (!(c.kv_time_saved_s > 0)) {
    lines.push(t("common.bar.spend.summary_none"));
  }
  if (c.kv_time_saved_s > 0) lines.push(t("common.bar.spend.summary_kv", { seconds: kvSeconds(c.kv_time_saved_s) }));
  summary.textContent = lines.join(" ");
  const footprint = $("bar-spend-footprint");
  const green = (c.impact_calls ?? 0) > 0;
  if (footprint) {
    footprint.textContent = green ? `🍃 ${rangeText(c.energy_wh_min, c.energy_wh_max, "Wh")} · ${rangeText(c.gco2e_min, c.gco2e_max, "g CO₂e")}` : "";
    footprint.hidden = !green;
  }
  const detail = $("bar-spend-detail");
  if (detail) detail.textContent = detailSentence(c);
}

function savingsBar(label, amount, scale) {
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
  const length = Math.max(0, amount) / scale;
  input.style.width = `${(100 * length * (consumption.total_in_usd ?? 0)) / total}%`;
  output.style.width = `${(100 * length * (consumption.total_out_usd ?? 0)) / total}%`;
  track.append(input, output);
  const value = document.createElement("span");
  value.textContent = money(amount);
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

const LEVEL_OF = {
  allow: "low",
  allow_once: "low",
  passed: "low",
  partial: "low",
  deny: "high",
  blocked: "high",
  timeout: "high",
  masked: "mid",
  cancelled: "mid",
  flagged: "mid",
  error: "mid",
};

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
  const key = `common.bar.log.decisions.${entry.decision}`;
  chip.textContent = has(key) ? t(key) : entry.decision; // `t` would show the key itself
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
