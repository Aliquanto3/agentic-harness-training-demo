// Story 10 (CAP-3, CAP-8, CAP-9): the page Sécurité. A single read of `/api/security` (the
// question cards, the risk matrix, the active controls) and of `/api/security_journal` (the
// full journal) at load; after that, each `security_event` of the shared stream is applied
// in O(1) (a new row prepended, the two decision-based question cards' counts bumped), never
// a re-fetch nor a walk of the growing journal.

import { dateTimeFormat, has, ready, t } from "./i18n.js";
import { feedBar } from "./bar.js";

const $ = (id) => document.getElementById(id);

// The two counters a live `security_event` can move (CAP-9's question cards); the other two
// (« peut écrire », « non couvert ») come from the policy and the content, never from events.
let toolDenied = 0;
let guardrailBlocked = 0;
let allowOnce = 0;

function chipClass(level) {
  return level === "low" ? "" : ` status-chip-${level}`;
}

function chip(text, level) {
  const el = document.createElement("span");
  el.className = `status-chip${chipClass(level)}`;
  el.textContent = text;
  return el;
}

// ---------- the 4 question cards ----------

function questionCard(ask, count, detailText, alert) {
  const el = document.createElement("div");
  el.className = "sec-question-card";
  const askEl = document.createElement("span");
  askEl.className = "sec-question-ask";
  askEl.textContent = ask;
  const figure = document.createElement("span");
  figure.className = `sec-question-figure${alert ? " alert" : ""}`;
  figure.textContent = String(count);
  const detail = document.createElement("span");
  detail.className = "sec-question-detail";
  detail.textContent = detailText;
  el.append(askEl, figure, detail);
  return el;
}

function renderQuestions(q) {
  const box = $("sec-questions");
  if (!box) return;
  box.replaceChildren(
    questionCard(t("security.questions.can_write"), q.can_write.count, q.can_write.detail_text, false),
    questionCard(t("security.questions.authorized_by_you"), q.authorized_by_you.count, q.authorized_by_you.detail_text, false),
    questionCard(t("security.questions.blocked"), q.blocked.count, q.blocked.detail_text, q.blocked.count > 0),
    questionCard(t("security.questions.not_covered"), q.not_covered.count, q.not_covered.detail_text, false),
  );
}

// Rebuilds only the « qui a autorisé » and « bloqué » cards from the counters a live event
// just moved (O(1): the other two cards, from the policy and the content, never change
// from an event).
function renderMovableQuestions() {
  const box = $("sec-questions");
  if (!box || box.children.length < 4) return;
  box.children[1].replaceWith(
    questionCard(
      t("security.questions.authorized_by_you"),
      allowOnce,
      t("security.questions.authorized_detail", { count: allowOnce }),
      false,
    ),
  );
  const blocked = toolDenied + guardrailBlocked;
  box.children[2].replaceWith(questionCard(t("security.questions.blocked"), blocked, blockedDetailText(), blocked > 0));
}

function blockedDetailText() {
  const parts = [];
  if (toolDenied) parts.push(t("security.questions.tool_denied", { count: toolDenied }));
  if (guardrailBlocked) parts.push(t("security.questions.guardrail_blocked", { count: guardrailBlocked }));
  return parts.length ? parts.join(", ") : t("security.questions.nothing_blocked");
}

// ---------- the risk matrix ----------

function renderMatrix(rows) {
  const body = $("sec-matrix-body");
  if (!body) return;
  body.replaceChildren(
    ...rows.map((row) => {
      const tr = document.createElement("tr");
      const tool = document.createElement("td");
      tool.textContent = row.label_text;
      const nature = document.createElement("td");
      nature.textContent = row.nature_text;
      const risk = document.createElement("td");
      risk.append(chip(t(`mcp.policy.risk.${row.risk}`), row.risk));
      const rule = document.createElement("td");
      rule.textContent = t(`mcp.policy.rule.${row.rule}`);
      tr.append(tool, nature, risk, rule);
      return tr;
    }),
  );
}

// ---------- disclosure rows (the single pattern for technical detail, DESIGN.md) ----------

function discRow(label, badge, bodyNodes) {
  const li = document.createElement("li");
  li.className = "sec-row disclosure-row";
  const button = document.createElement("button");
  button.type = "button";
  button.className = "sec-row-head disclosure-row-head";
  const chevron = document.createElement("span");
  chevron.className = "disclosure-row-chevron";
  chevron.setAttribute("aria-hidden", "true");
  chevron.textContent = "▸";
  const name = document.createElement("span");
  name.className = "disclosure-row-label";
  name.textContent = label;
  button.append(chevron, name);
  if (badge) button.append(badge);
  const body = document.createElement("div");
  body.className = "disclosure-row-body";
  body.hidden = true;
  body.append(...bodyNodes);
  button.addEventListener("click", () => {
    body.hidden = !body.hidden;
    button.setAttribute("aria-expanded", String(!body.hidden));
    chevron.classList.toggle("is-open", !body.hidden);
  });
  button.setAttribute("aria-expanded", "false");
  li.append(button, body);
  return li;
}

function kv(pairs) {
  const dl = document.createElement("dl");
  for (const [key, value] of pairs) {
    const dt = document.createElement("dt");
    dt.textContent = key;
    const dd = document.createElement("dd");
    dd.textContent = value;
    dl.append(dt, dd);
  }
  return [dl];
}

function sub(text) {
  const span = document.createElement("span");
  span.className = "sec-row-sub";
  span.textContent = text;
  return span;
}

// ---------- the active controls ----------

function renderControls(controls) {
  const list = $("sec-controls");
  if (!list) return;
  const rows = [];

  const tr = controls.tool_rules;
  const trBits = [`${tr.count}`];
  if (tr.ask_count) trBits.push(t("security.controls.ask_count", { count: tr.ask_count }));
  if (tr.deny_count) trBits.push(t("security.controls.deny_count", { count: tr.deny_count }));
  rows.push(discRow(t("security.controls.tool_rules"), sub(trBits.join(" · ")), kv([])));

  for (const g of controls.guardrails) {
    const level = g.status === "active" ? (g.mode === "block" ? "high" : "mid") : "off";
    const text =
      g.status === "active"
        ? t(`guardrails.modes.${g.mode === "flag" && g.id === "pii" ? "flag_pii" : g.mode}`)
        : has(`main.bricks.status.${g.status}`)
          ? t(`main.bricks.status.${g.status}`)
          : g.status;
    rows.push(discRow(g.label_text, chip(text, level), g.install_text ? kv([[t("security.limits.reason_label"), g.install_text]]) : []));
  }

  const enabledHooks = controls.hooks.filter((h) => h.enabled);
  rows.push(
    discRow(
      t("security.controls.hooks"),
      sub(String(enabledHooks.length)),
      kv(enabledHooks.map((h) => [h.id.toUpperCase(), h.label_text])),
    ),
  );

  rows.push(
    discRow(
      t("security.controls.network_whitelist"),
      sub(t("security.controls.domain_count", { count: controls.network_whitelist.length })),
      kv([[t("security.matrix.column_tool"), controls.network_whitelist.join(" · ")]]),
    ),
  );

  const gh = controls.github;
  const ghLevel = gh.status === "connected" ? "low" : gh.status === "expired" || gh.status === "error" ? "high" : "off";
  const ghDetail = [[t("security.controls.github_scope_label"), gh.scope], [t("security.controls.github_server_label"), gh.server]];
  if (gh.expires_in_s != null) {
    const hours = Math.floor(gh.expires_in_s / 3600);
    ghDetail.unshift([t("security.controls.github"), t("security.controls.github_expires", { time: `${hours} h` })]);
  }
  rows.push(discRow(t("security.controls.github"), chip(t(`security.controls.github_states.${gh.status}`), ghLevel), kv(ghDetail)));

  list.replaceChildren(...rows);
}

// ---------- the full journal (growing; a live event only prepends, never a re-walk) ----------

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

function journalRow(entry) {
  let when = entry.ts;
  try {
    when = dateTimeFormat({ timeStyle: "medium" }).format(new Date(entry.ts));
  } catch {
    // The raw ISO text stays rather than nothing.
  }
  const key = `common.bar.log.decisions.${entry.decision}`;
  const badge = chip(has(key) ? t(key) : entry.decision, LEVEL_OF[entry.decision] ?? "mid");
  const p = document.createElement("p");
  p.textContent = entry.reason_text;
  return discRow(`${when} — ${entry.label_text}`, badge, [p]);
}

function renderJournal(entries) {
  const list = $("sec-journal");
  if (!list) return;
  if (entries.length === 0) {
    const empty = document.createElement("li");
    empty.className = "sec-empty";
    empty.textContent = t("security.journal.empty");
    list.replaceChildren(empty);
    return;
  }
  list.replaceChildren(...entries.map(journalRow));
}

function prependJournalRow(entry) {
  const list = $("sec-journal");
  if (!list) return;
  if (list.firstElementChild?.classList.contains("sec-empty")) list.replaceChildren();
  list.prepend(journalRow(entry));
}

// ---------- the limits ----------

function renderLimits(limits) {
  const list = $("sec-limits");
  if (!list) return;
  list.replaceChildren(
    ...limits.map((limit) =>
      discRow(limit.statement_text, null, kv([
        [t("security.limits.reason_label"), limit.reason_text],
        [t("security.limits.production_label"), limit.production_text],
      ])),
    ),
  );
}

// ---------- load, then live ----------

async function load() {
  const [security, journal] = await Promise.all([
    fetch("/api/security").then((r) => r.json()),
    fetch("/api/security_journal").then((r) => r.json()),
  ]);
  renderQuestions(security.questions);
  renderMatrix(security.risk_matrix);
  renderControls(security.controls);
  renderLimits(security.limits);
  renderJournal(journal.entries.slice().reverse()); // newest first
  // The two counters a live event may move, read back from the entries already in hand
  // (O(n) once, at load only; never repeated per event).
  toolDenied = journal.entries.filter((e) => e.source === "mcp_tool" && e.decision === "deny").length;
  guardrailBlocked = journal.entries.filter((e) => e.source === "guardrail" && e.decision === "blocked").length;
  allowOnce = journal.entries.filter((e) => e.decision === "allow_once").length;
}

function openStream() {
  const source = new EventSource("/api/diagnostic/stream");
  source.addEventListener("consumption_updated", (event) => feedBar(JSON.parse(event.data)));
  source.addEventListener("security_event", (event) => {
    const envelope = JSON.parse(event.data);
    feedBar(envelope);
    const entry = envelope.payload;
    prependJournalRow(entry);
    if (entry.source === "mcp_tool" && entry.decision === "deny") toolDenied += 1;
    if (entry.source === "guardrail" && entry.decision === "blocked") guardrailBlocked += 1;
    if (entry.decision === "allow_once") allowOnce += 1;
    renderMovableQuestions();
  });
}

async function main() {
  await ready; // the page's texts and formats in the session's language (languages 4/5)
  await load();
  openStream();
}

main();
