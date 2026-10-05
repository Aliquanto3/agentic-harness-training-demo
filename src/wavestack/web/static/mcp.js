// Lot 4 of the 2026-10-04 corrections plan: the MCP workshop in sequence (`/mcp`, EXPERIENCE.md
// « Atelier MCP en séquence », AD-27, AD-28). Four panes laid out by panes.js (Serveurs et
// commandes, 1 Séquence, 2 Ce que le modèle voit, 3 Architecture); the sequence, the context
// blocks and the architecture are drawn from the `mcp_lab` events only (AD-1): the page never
// reads `jsonrpc` but in the detail that shows it, never compares a `*_text`, computes nothing
// it did not receive. The live stream and the reload (`last_session`) go through the same pure
// function, `frames(envelopes)`, which turns the envelopes of the current series into phases,
// arrows (captured, deduced by AD-27's table, ghosts and notes) and context blocks; the stepper
// (diagram.js) gets the step arrows, and what each step shows is decided from `revealAt`.
//
// Texts: `content/ui.yaml` (section `mcp`) through `t()`, the pedagogical ones from
// `content/mcp_lab.yaml` (`GET /api/mcp_lab`, in the session's language). The servers'
// descriptions and the captured JSON are never translated.

import { numberFormat, ready as textsReady, t } from "./i18n.js";
import { createStepper, explain, light, marker, reveal, svgEl, wire, wireLayer } from "./diagram.js";
import { createPanes, initProjection } from "./panes.js";

const $ = (id) => document.getElementById(id);

// The six lifelines, in this order (EXPERIENCE.md: the model left of the host).
const COLS = ["user", "model", "host", "client", "server", "source"];
const [USER, MODEL, HOST, CLIENT, SERVER, SOURCE] = [0, 1, 2, 3, 4, 5];
// AD-27: the kinds the page draws, live and at a reload, besides the session's state.
const KINDS = new Set([
  "mcp_lab_exchange_started",
  "mcp_lab_message",
  "mcp_lab_connect_ended",
  "mcp_lab_call_ended",
  "mcp_lab_read_ended",
  "mcp_lab_prompt_ended",
  "mcp_lab_model_started",
  "mcp_lab_model_ended",
  "mcp_lab_ask_ended",
  "mcp_lab_closed",
  "model_call_started",
  "model_call_ended",
  "outbound_request",
  "outbound_response",
]);
// The methods whose answer the server took from its source (the deduced arrows Serveur ↔ Source).
const SOURCED = new Set(["tools/call", "resources/read", "prompts/get"]);
// AD-27: the error kinds where no answer came back (a `jsonrpc_error` is an answer).
const NO_REPLY_KINDS = new Set(["timeout", "lost", "unreachable", "guard_blocked", "stopped"]);
const PANES_KEY = "wavestack.mcp.panes";
const ARCH_KEY = "wavestack.mcp.arch_view";

const store = {
  content: null,
  servers: [],
  presets: {},
  ask: null,
  session: { state: "diagnostic", reason_text: null },
  openServer: null, // `open_server`, then each end's `connection`
  serverInstance: null,
  lastSeq: 0,
  first: 0, // the current series: the number of its connection's exchange (`mcp{first}`)
  envelopes: [], // the current series, in the order of their `seq`
  model: null, // `frames(envelopes)`, the last one drawn
  failures: new Map(), // server -> the reason of its last failed connection (the page's memory)
  pending: false, // an intention posted, not answered yet
  selected: "local",
  tab: "tools",
  mode: "hand", // « À la main » | « Par le modèle »
  docMode: "full", // « Documentation complète » | « Lazy loading »
  archView: "after",
  restoring: false,
  announced: new Set(), // the phases and failures already said (status, alert)
};

// ---------- small helpers ----------

function el(tag, className, text) {
  const node = document.createElement(tag);
  if (className) node.className = className;
  if (text !== undefined && text !== null) node.textContent = text;
  return node;
}

const fmt = (n) => (typeof n === "number" ? numberFormat().format(n) : "—");

// A text of content/mcp_lab.yaml by its dotted path, `{name}` replaced by `values[name]`.
function text(path, values = {}) {
  let value = store.content;
  for (const key of path.split(".")) value = value?.[key];
  if (typeof value !== "string") return "";
  return value.replace(/\{(\w+)\}/g, (_, name) => String(values[name] ?? ""));
}

function stepNumber(stepId) {
  const match = /^mcp(\d+)(\.[ct]\d+)?$/.exec(stepId || "");
  return match ? Number(match[1]) : null;
}

const serverInfo = (id) => store.servers.find((s) => s.id === id) ?? null;
const serverLabel = (id) => serverInfo(id)?.label_text ?? id ?? "";
const isNetwork = (id) => Boolean(serverInfo(id)?.network);

function duration(ms) {
  if (typeof ms !== "number") return "";
  return ms < 1000 ? t("mcp.time.ms", { n: ms }) : t("mcp.time.s", { n: Math.round(ms / 100) / 10 });
}

function tokens(n, estimated = false) {
  if (typeof n !== "number") return "";
  const said = t("mcp.tokens", { count: n, n });
  return estimated ? t("mcp.estimated_value", { value: said }) : said;
}

const quote = (value) => t("mcp.quote", { text: value });
const clip = (value, max = 60) => (value.length > max ? `${value.slice(0, max - 1).trimEnd()}…` : value);

function callText(name, args) {
  const parts = Object.entries(args || {}).map(([key, value]) =>
    t("mcp.arrow.argument", { name: key, value: typeof value === "string" ? value : JSON.stringify(value) })
  );
  return `${name}(${parts.join(", ")})`;
}

function pretty(value) {
  if (typeof value !== "string") return JSON.stringify(value, null, 2);
  try {
    return JSON.stringify(JSON.parse(value), null, 2);
  } catch {
    return value;
  }
}

function srOnly(value) {
  return el("span", "mcp-sr-only", value);
}

// Never rejects: a network failure is an answer too.
async function post(path, body) {
  let response;
  try {
    response = await fetch(path, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(body),
    });
  } catch {
    return { ok: false, status: 0, body: { detail: t("common.unreachable") } };
  }
  let answer = {};
  try {
    answer = await response.json();
  } catch {
    answer = {};
  }
  return { ok: response.ok, status: response.status, body: answer };
}

function refusalText(answer) {
  const detail = answer.body?.detail;
  if (typeof detail === "string") return detail;
  return answer.status ? t("common.refused_http", { status: String(answer.status) }) : t("common.unreachable");
}

// ---------- the series as phases, arrows and blocks: a pure function (AD-1, AD-27) ----------

// The envelopes of the current series, in the order of their `seq`, give the phases (one per
// exchange `mcp{n}`), the arrows (each with its `revealAt`: the step from which it shows; a
// step arrow is its own step, a ghost or a note shows with the step before it) and the blocks
// of « Ce que le modèle voit » (each shown with the arrow that produces it). Same input, same
// output: the stream and the reload draw the same arrows.
export function frames(envelopes) {
  const phases = [];
  const phaseOf = new Map(); // `mcp{n}` -> its phase
  const arrows = [];
  const blocks = [];
  const bySeq = new Map(); // a message's `seq` -> its arrow
  const models = new Map(); // `mcp{n}.c{k}` -> the arrow Hôte → modèle
  let steps = 0;
  let model = null; // the model of the series' last call to the model
  let connect = null; // the series' `mcp_lab_connect_ended`
  let generating = null; // a call to the model started, not ended: its step
  let closed = null;

  const add = (arrow) => {
    arrow.revealAt = arrow.step ? steps++ : Math.max(steps - 1, 0);
    arrow.server ??= phaseOf.get(arrow.phase)?.server ?? connect?.server ?? null;
    arrows.push(arrow);
    return arrow;
  };
  const note = (phase, key, value, error = false) =>
    add({ key, phase, kind: "note", from: HOST, to: CLIENT, text: value, error, step: false });
  const ghost = (phase, key, from, to, chip, tag) =>
    add({ key, phase, kind: "ghost", from, to, chip, ghostTag: tag, step: false, produced: from === MODEL });
  const markFailed = (phase, end) => {
    const failed = end.failed_seq != null ? bySeq.get(end.failed_seq) : null;
    const reason = end.error_text || t(`mcp.error_kinds.${end.error_kind}`);
    if (failed) {
      failed.error = reason;
      failed.stopped = end.status === "cancelled";
      if (failed.from === CLIENT) failed.unanswered = true;
    } else if (end.status !== "ok") {
      note(phase, `${phase}:failure`, reason, true);
    }
  };

  for (const envelope of envelopes) {
    const p = envelope.payload || {};
    const step = envelope.step_id || "";
    const n = stepNumber(step);
    const base = `mcp${n}`;
    const sub = step.includes(".");
    switch (envelope.kind) {
      case "mcp_lab_exchange_started": {
        if (sub) {
          // `mcp{n}.t1`: the tool the model asked for, executed by the host through the client.
          add({ key: `${step}:exec`, phase: base, kind: "host", from: HOST, to: CLIENT, step: true,
            text: t("mcp.arrow.exec", { call: callText(p.tool, p.arguments) }) });
          break;
        }
        const phase = { key: step, n, exchange: p.exchange, by: p.by, server: p.server, start: p, end: null, ts: envelope.ts };
        phases.push(phase);
        phaseOf.set(step, phase);
        const user = (value, tag, extra = {}) =>
          add({ key: `${step}:user`, phase: step, kind: "user", from: USER, to: HOST, step: true, text: value, tag, ...extra });
        if (p.exchange === "connect") {
          add({ key: `${step}:launch`, phase: step, kind: "host", from: HOST, to: CLIENT, step: true, text: p.launch_text,
            explain: text(`transports.${isNetwork(p.server) ? "streamable_http" : "stdio"}.explain_text`) });
        } else if (p.exchange === "call") {
          const call = callText(p.tool, p.arguments);
          user(t("mcp.arrow.form", { call }), t("mcp.tags.instead_of_model"));
          ghost(step, `${step}:ghost-ask`, HOST, MODEL, t("mcp.chips.question_tools"), t("mcp.ghosts.skipped"));
          ghost(step, `${step}:ghost-call`, MODEL, HOST, t("mcp.chips.call", { tool: p.tool }), t("mcp.ghosts.you_did"));
          add({ key: `${step}:exec`, phase: step, kind: "host", from: HOST, to: CLIENT, step: true,
            text: t("mcp.arrow.exec", { call }) });
        } else if (p.exchange === "read") {
          user(t("mcp.arrow.choose_resource", { uri: p.uri }), t("mcp.tags.plays_app"));
          add({ key: `${step}:exec`, phase: step, kind: "host", from: HOST, to: CLIENT, step: true,
            text: t("mcp.arrow.read", { uri: p.uri }) });
        } else if (p.exchange === "prompt") {
          user(t("mcp.arrow.choose_prompt", { call: callText(p.prompt, p.arguments) }));
          add({ key: `${step}:exec`, phase: step, kind: "host", from: HOST, to: CLIENT, step: true,
            text: t("mcp.arrow.get", { name: p.prompt }) });
        } else if (p.exchange === "ask") {
          user(p.question ? quote(p.question) : t("mcp.arrow.send_prompt", { name: p.prompt }));
        }
        break;
      }
      case "mcp_lab_message": {
        const out = p.direction === "to_server";
        const reply = p.message_type === "response" || p.message_type === "error";
        if (reply && !p.unsolicited && SOURCED.has(p.method)) {
          // AD-27: inside the server, never captured, only when an answer came.
          const server = phaseOf.get(base)?.server;
          add({ key: `m${envelope.seq}:to-source`, phase: base, kind: "source", from: SERVER, to: SOURCE, step: true,
            text: serverInfo(server)?.source_action_text ?? "", tag: t("mcp.tags.not_captured"),
            explain: serverInfo(server)?.source_explain_text });
          add({ key: `m${envelope.seq}:from-source`, phase: base, kind: "source", from: SOURCE, to: SERVER, step: true,
            text: t("mcp.arrow.source_back"), tag: t("mcp.tags.not_captured") });
        }
        const arrow = add({
          key: `m${envelope.seq}`,
          seq: envelope.seq,
          phase: base,
          kind: "rpc",
          from: out ? CLIENT : SERVER,
          to: out ? SERVER : CLIENT,
          step: !p.unsolicited,
          method: p.method,
          messageType: p.message_type,
          text: p.summary_text,
          timing: { ms: p.elapsed_ms, kind: p.elapsed_kind },
          noReply: p.message_type === "notification",
          error: p.message_type === "error"
            ? t("mcp.arrow.rpc_error", { code: p.error?.code ?? "", message: p.error?.message ?? "" })
            : p.is_error
              ? t("mcp.arrow.is_error")
              : null,
          json: p.jsonrpc,
          unsolicited: p.unsolicited,
          net: isNetwork(phaseOf.get(base)?.server ?? connect?.server),
        });
        if (p.method === "tools/list" && reply) arrow.mv = "tools";
        bySeq.set(envelope.seq, arrow);
        break;
      }
      case "outbound_request": {
        if (p.message_seq != null && bySeq.has(p.message_seq)) bySeq.get(p.message_seq).outbound = p;
        else if (models.has(step) && p.origin === "model") models.get(step).outbound = p;
        break;
      }
      case "model_call_ended": {
        if (models.has(step)) models.get(step).call = p;
        break;
      }
      case "mcp_lab_connect_ended": {
        const phase = phaseOf.get(base);
        if (phase) phase.end = p;
        connect = p;
        if (p.status === "ok") {
          const missing = ["resources", "prompts"].filter((k) => !p.primitives?.[k]);
          if (missing.length) {
            note(base, `${base}:not-announced`, t(`mcp.notes.not_announced_${missing.join("_")}`));
          }
          for (const failed of p.list_errors || []) {
            const request = [...arrows].reverse().find((a) => a.phase === base && a.method === failed.method && a.from === CLIENT);
            if (request) {
              request.error = failed.error_text;
              // A JSON-RPC error answer came back: only a request with no reply is unanswered.
              request.unanswered = NO_REPLY_KINDS.has(failed.error_kind);
            }
          }
          add({ key: `${base}:lists`, phase: base, kind: "host", from: CLIENT, to: HOST, step: true, prims: true,
            text: primitivesText(p) });
        } else {
          markFailed(base, p);
        }
        break;
      }
      case "mcp_lab_call_ended": {
        const phase = sub ? null : phaseOf.get(base);
        if (phase) phase.end = p;
        if (p.status === "ok") {
          const result = add({ key: `${step}:result`, phase: base, kind: "host", from: CLIENT, to: HOST, step: true,
            text: t(p.is_error ? "mcp.arrow.result_error" : "mcp.arrow.result", { tokens: tokens(p.tokens, p.estimated) }),
            isError: p.is_error, mv: `${step}:result` });
          blocks.push({ kind: "result", key: `${step}:result`, arrow: result.key, payload: p, sent: sub });
          if (!sub) {
            ghost(base, `${base}:ghost-result`, HOST, MODEL, t("mcp.chips.tool_result"), t("mcp.ghosts.not_here"));
            ghost(base, `${base}:ghost-answer`, MODEL, HOST, t("mcp.chips.answer"), t("mcp.ghosts.not_here"));
            ghost(base, `${base}:ghost-user`, HOST, USER, t("mcp.chips.reply"), t("mcp.ghosts.see_harness"));
          }
        } else {
          markFailed(base, p);
        }
        break;
      }
      case "mcp_lab_read_ended": {
        const phase = phaseOf.get(base);
        if (phase) phase.end = p;
        if (p.status === "ok") {
          const content = add({ key: `${step}:content`, phase: base, kind: "host", from: CLIENT, to: HOST, step: true,
            text: t("mcp.arrow.content", { tokens: tokens(p.tokens, p.estimated) }) });
          blocks.push({ kind: "resource", key: step, arrow: content.key, payload: p });
          ghost(base, `${base}:ghost-context`, HOST, MODEL, t("mcp.chips.in_context"), t("mcp.ghosts.if_added"));
        } else {
          markFailed(base, p);
        }
        break;
      }
      case "mcp_lab_prompt_ended": {
        const phase = phaseOf.get(base);
        if (phase) phase.end = p;
        if (p.status === "ok") {
          const count = (p.messages || []).length;
          const content = add({ key: `${step}:content`, phase: base, kind: "host", from: CLIENT, to: HOST, step: true,
            text: t("mcp.arrow.messages", { count, n: count, tokens: tokens(p.tokens, p.estimated) }) });
          blocks.push({ kind: "prompt", key: step, arrow: content.key, payload: p });
          ghost(base, `${base}:ghost-message`, HOST, MODEL, t("mcp.chips.user_message"), t("mcp.ghosts.not_sent"));
        } else {
          markFailed(base, p);
        }
        break;
      }
      case "mcp_lab_model_started": {
        model = p.model || model;
        generating = step;
        const arrow = add({ key: step, phase: base, kind: "model", from: HOST, to: MODEL, step: true, read: true,
          chip: (p.sends || []).map((s) => s.label_text).join(" + "),
          text: tokens(p.prompt_tokens, p.estimated), cloud: p.model?.hosting === "network",
          startedAt: envelope.ts, mv: step });
        models.set(step, arrow);
        blocks.push({ kind: "sent", key: step, arrow: arrow.key, payload: p, ended: null });
        break;
      }
      case "mcp_lab_model_ended": {
        if (generating === step) generating = null;
        const started = models.get(step);
        const sent = blocks.find((b) => b.kind === "sent" && b.key === step);
        if (sent) sent.ended = p;
        if (started) started.ended = true;
        if (p.outcome === "overflow") {
          if (started) {
            started.error = p.error_text;
            started.text = t("mcp.arrow.not_sent");
          }
          break;
        }
        const cloud = started?.cloud ?? false;
        let chip;
        let error = null;
        if (p.status === "cancelled") {
          chip = t("mcp.chips.stopped");
          error = t("mcp.error_kinds.stopped");
        } else if (p.status === "error") {
          chip = t("mcp.chips.failed");
          error = p.error_text || t(`mcp.error_kinds.${p.error_kind || "interrupted"}`);
        } else if (p.outcome === "tool_call" || p.outcome === "meta_call") {
          chip = t("mcp.chips.call", { tool: p.tool_call?.name ?? "" });
        } else if (p.outcome === "refused") {
          chip = p.tool_call ? t("mcp.chips.call", { tool: p.tool_call.name }) : t("mcp.chips.malformed");
          error = t("mcp.arrow.refused", { reason: p.refusal_text || "" });
        } else if (p.outcome === "cut") {
          chip = t("mcp.chips.cut");
          error = t("mcp.arrow.cut");
        } else {
          chip = p.direct ? t("mcp.chips.direct") : t("mcp.chips.answer");
        }
        const answer = add({ key: `${step}:out`, phase: base, kind: "model", from: MODEL, to: HOST, step: true,
          produced: true, chip, cloud, error, text: duration(p.duration_ms),
          json: p.tool_call ? p.tool_call.arguments_text : null, mv: p.outcome === "refused" ? `${step}:refused` : null });
        if (p.outcome === "refused") blocks.push({ kind: "refused", key: `${step}:refused`, arrow: answer.key, payload: p });
        if (p.final && p.outcome === "answer") {
          add({ key: `${step}:reply`, phase: base, kind: "user", from: HOST, to: USER, step: true,
            text: quote(clip(p.answer_text || "")) });
          if (p.direct) note(base, `${step}:direct`, t("mcp.notes.direct"));
        }
        break;
      }
      case "mcp_lab_ask_ended": {
        const phase = phaseOf.get(base);
        if (phase) phase.end = p;
        if (p.outcome === "second_tool") note(base, `${base}:second`, t("mcp.notes.second_tool"), true);
        if (p.outcome === "max_calls") note(base, `${base}:max`, t("mcp.notes.max_calls", { n: p.calls }), true);
        if (p.status === "error" && p.outcome === null && p.error_text) note(base, `${base}:failure`, p.error_text, true);
        break;
      }
      case "mcp_lab_closed": {
        closed = p;
        const last = phases.at(-1);
        if (last) note(last.key, `closed${envelope.seq}`, t("mcp.notes.closed", { cause: t(`mcp.close_causes.${p.cause}`) }));
        break;
      }
      default:
        break;
    }
  }
  return { phases, arrows, blocks, connect, model, generating, closed, steps };
}

function primitivesText(end) {
  const part = (kind, icon) => {
    if (!end.primitives?.[kind]) return `${icon} ⊘`;
    const list = end[kind];
    return list ? `${icon} ${fmt(list.length)}` : `${icon} ⚠`;
  };
  return [part("tools", "🔧"), part("resources", "📄"), part("prompts", "💬")].join(" · ");
}

// ---------- the Séquence ----------

let stepper = null;
let panes = null;
let layer = null; // the architecture's wires
const rows = new Map(); // arrow key -> {li, sig}
const phaseNodes = new Map(); // phase key -> {section, list, toggle, meta, why, whyBox}
let current = null; // the arrow shown by the stepper
let shownIndex = -1;
let suspended = false; // the automatic scrolling, suspended by the user
let unseen = 0;
let programmatic = false;

function columnName(i) {
  return text(`columns.${COLS[i]}.name_text`) || COLS[i];
}

function modelInfo() {
  return store.model?.model || store.ask?.model || null;
}

function renderHeads() {
  const heads = $("mcp-heads");
  const lifelines = $("mcp-lifelines");
  if (heads.querySelectorAll(".mcp-head").length !== COLS.length) {
    heads.replaceChildren();
    lifelines.replaceChildren();
    COLS.forEach((id, i) => {
      const head = el("button", "mcp-head diagram-block");
      head.type = "button";
      head.dataset.col = id;
      head.append(el("span", "mcp-head-name"), el("small", "mcp-head-sub"));
      heads.append(head);
      lifelines.append(el("span", `mcp-lifeline mcp-lifeline-${id}`));
      reveal(head, false);
      reveal(lifelines.lastChild, false);
      void i;
    });
  }
  const server = store.model?.connect?.server ?? store.model?.phases?.[0]?.server ?? store.selected;
  const info = serverInfo(server);
  const model = modelInfo();
  const cloud = model?.hosting === "network";
  for (const head of heads.querySelectorAll(".mcp-head")) {
    const id = head.dataset.col;
    let name = columnName(COLS.indexOf(id));
    let sub = text(`columns.${id}.sub_text`);
    head.classList.toggle("is-net", id === "server" && Boolean(info?.network));
    head.classList.toggle("is-model", id === "model");
    head.classList.toggle("is-cloud", id === "model" && cloud);
    if (id === "server") {
      sub = info?.label_text ?? "";
      if (info?.network) name = `🌐 ${name}`;
    }
    if (id === "source") sub = info?.source_label_text ?? "";
    if (id === "model") {
      if (cloud) name = t("mcp.columns.cloud", { provider: model.provider ?? "" });
      sub = model?.label ?? sub;
    }
    head.querySelector(".mcp-head-name").textContent = name;
    head.querySelector(".mcp-head-sub").textContent = sub;
    explain(head, columnExplain(id, info));
  }
}

function analogy(piece) {
  const place = text(`restaurant.${piece}.place_text`);
  return place ? t("mcp.arch.analogy", { place, meaning: text(`restaurant.${piece}.meaning_text`) }) : "";
}

function columnExplain(id, info) {
  const base = text(`columns.${id}.explain_text`);
  const piece = { user: null, model: "model", host: "host", client: "client", source: "source",
    server: info?.network ? "server_http" : "server_stdio" }[id];
  const extra = id === "source" ? info?.source_explain_text : null;
  return [base, extra, piece ? analogy(piece) : ""].filter(Boolean).join("\n");
}

// Where a line starts and how long it is, on a grid of six equal columns and their gaps.
function geometry(from, to) {
  const lo = Math.min(from, to);
  const hi = Math.max(from, to);
  const col = "((100% - 5 * var(--mcp-col-gap)) / 6)";
  return {
    left: `calc(${col} * ${lo + 0.5} + var(--mcp-col-gap) * ${lo})`,
    width: `calc(${col} * ${hi - lo} + var(--mcp-col-gap) * ${hi - lo})`,
    right: to > from,
    span: `${lo + 1} / ${hi + 2}`,
  };
}

function originTag(arrow) {
  if (arrow.kind === "ghost") return arrow.ghostTag;
  return t(`mcp.origins.${arrow.kind === "user" ? "host" : arrow.kind}`);
}

// The arrow's name for a screen reader, after its visible text (EXPERIENCE.md, Accessibilité).
function arrowFragments(arrow) {
  const parts = [];
  if (arrow.net && arrow.kind === "rpc") parts.push(t("mcp.a11y.network"));
  if (arrow.cloud) parts.push(t("mcp.a11y.network"));
  if (arrow.kind === "rpc") parts.push(t(`mcp.a11y.${arrow.noReply ? "notification" : arrow.messageType === "request" ? "request" : "response"}`));
  parts.push(originTag(arrow));
  if (arrow.error) parts.push(t("mcp.a11y.error", { reason: arrow.error }));
  if (arrow.timing) parts.push(timingText(arrow.timing));
  return `, ${parts.filter(Boolean).join(", ")}`;
}

function timingText(timing) {
  return t(timing.kind === "round_trip" ? "mcp.time.round_trip" : "mcp.time.at", { time: duration(timing.ms) });
}

function arrowLabel(arrow) {
  return [arrow.method, arrow.chip, arrow.text].filter(Boolean).join(" ");
}

function renderArrow(arrow, li) {
  li.className = `mcp-row k-${arrow.kind}`;
  li.classList.toggle("is-net", Boolean(arrow.net || arrow.cloud));
  li.classList.toggle("is-error", Boolean(arrow.error || arrow.isError));
  li.classList.toggle("no-reply", Boolean(arrow.noReply || arrow.kind === "ghost"));
  // A request left without an answer (AD-27: timeout, lost, unreachable, guard, stopped).
  li.classList.toggle("is-unanswered", Boolean(arrow.unanswered));
  li.dataset.key = arrow.key;
  li.dataset.kind = arrow.kind;
  li.dataset.from = COLS[arrow.from];
  li.dataset.to = COLS[arrow.to];
  if (arrow.method) li.dataset.method = arrow.method;
  else delete li.dataset.method;
  li.replaceChildren();
  const g = geometry(arrow.from, arrow.to);
  const interactive = arrow.kind !== "note" && arrow.kind !== "ghost";
  const body = el(interactive ? "button" : "div", "mcp-arrow");
  if (interactive) {
    body.type = "button";
    body.tabIndex = -1;
    body.setAttribute("aria-expanded", "false");
  }
  const cap = el("span", "mcp-cap");
  cap.style.gridColumn = arrow.kind === "note" ? "3 / 7" : g.span;
  if (arrow.kind === "note") {
    cap.append(el("span", `mcp-tag ${arrow.error ? "is-error" : "is-ghost"}`, `${arrow.error ? "✖" : "ⓘ"} ${arrow.text}`));
    body.append(cap);
    li.append(body);
    return;
  }
  body.append(srOnly(t("mcp.a11y.from_to", { from: columnName(arrow.from), to: columnName(arrow.to) })));
  if (arrow.kind === "rpc") {
    const chip = el("span", "mcp-method-chip diagram-block", `${arrow.net ? "🌐 " : ""}${arrow.method || "—"}`);
    chip.lang = "en";
    cap.append(chip);
  } else if (arrow.kind === "model" || (arrow.kind === "ghost" && arrow.chip)) {
    const chip = el("span", `mcp-model-chip diagram-block ${arrow.produced ? "is-produced" : "is-read"}`, `${arrow.cloud ? "🌐 " : ""}${arrow.chip}`);
    cap.append(chip);
  }
  if (arrow.text) {
    const caption = el("span", "mcp-caption", arrow.text);
    if (!cap.querySelector(".diagram-block")) caption.classList.add("diagram-block");
    cap.append(caption);
  }
  if (arrow.kind === "model" && arrow.read && !arrow.ended && arrow.startedAt) {
    const chrono = el("span", "mcp-chrono");
    chrono.dataset.since = arrow.startedAt;
    chrono.setAttribute("aria-hidden", "true");
    cap.append(chrono);
  }
  if (arrow.timing) cap.append(el("span", "mcp-timing", timingText(arrow.timing)));
  if ((arrow.noReply || arrow.unanswered) && arrow.kind === "rpc") cap.append(el("span", "mcp-tag", t("mcp.tags.no_reply")));
  if (arrow.tag) cap.append(el("span", `mcp-tag ${arrow.kind === "source" ? "is-ghost" : "is-who"}`, arrow.tag));
  if (arrow.isError) cap.append(el("span", "mcp-tag is-error", "isError"));
  if (arrow.kind === "ghost") cap.append(el("span", "mcp-tag is-ghost", arrow.ghostTag));
  if (arrow.error && arrow.kind !== "note") cap.append(el("span", "mcp-reason", arrow.stopped ? t("mcp.arrow.stopped") : arrow.error));
  const line = el("span", `mcp-line ${g.right ? "to-right" : "to-left"}`);
  line.style.left = g.left;
  line.style.width = g.width;
  line.setAttribute("aria-hidden", "true");
  body.append(cap, line);
  if (arrow.error) {
    const x = el("span", "mcp-x", "✖");
    x.setAttribute("aria-hidden", "true");
    x.style.left = `calc(${g.left} + ${g.right ? g.width : "0px"})`;
    body.append(x);
  }
  if (arrow.kind === "ghost") body.append(srOnly(t("mcp.a11y.ghost", { tag: arrow.ghostTag })));
  else body.append(srOnly(arrowFragments(arrow)));
  li.append(body);
  if (interactive) {
    const detail = renderDetail(arrow);
    detail.id = `mcp-detail-${arrow.key.replace(/[^\w-]/g, "_")}`;
    detail.hidden = true;
    body.setAttribute("aria-controls", detail.id);
    body.addEventListener("click", () => {
      detail.hidden = !detail.hidden;
      body.setAttribute("aria-expanded", String(!detail.hidden));
      openDetails[detail.hidden ? "delete" : "add"](arrow.key);
    });
    if (openDetails.has(arrow.key)) {
      detail.hidden = false;
      body.setAttribute("aria-expanded", "true");
    }
    li.append(detail);
  }
}

const openDetails = new Set();

function renderDetail(arrow) {
  const box = el("div", "mcp-message-detail");
  box.classList.toggle("is-net", Boolean(arrow.net || arrow.cloud));
  box.classList.toggle("is-model", arrow.kind === "model");
  box.classList.toggle("is-error", Boolean(arrow.error || arrow.isError));
  const head = el("div", "mcp-detail-head");
  head.append(
    el("span", "mcp-detail-way", t("mcp.detail.way", { from: columnName(arrow.from), to: columnName(arrow.to) })),
    el("span", "mcp-tag", originTag(arrow))
  );
  box.append(head, el("p", "mcp-detail-caption", arrowLabel(arrow)));
  const why = arrow.kind === "rpc" ? text(`methods.${arrow.method}`) : arrow.explain;
  if (why) box.append(el("p", "mcp-detail-text", why));
  if (arrow.error) box.append(el("p", "mcp-detail-error", t("mcp.a11y.error", { reason: arrow.error })));
  if (arrow.call) {
    const call = arrow.call;
    box.append(el("p", "mcp-detail-text", t("mcp.detail.model_call", {
      prompt: tokens(call.prompt_tokens, call.usage_source === "estimate"),
      output: tokens(call.output_tokens, call.usage_source === "estimate"),
      time: duration(call.duration_ms),
    })));
  }
  if (arrow.outbound) box.append(outboundPayload(arrow.outbound));
  if (arrow.json) {
    const pre = el("pre", "mcp-json", pretty(arrow.json));
    pre.lang = "en";
    pre.tabIndex = 0;
    pre.setAttribute("role", "region");
    pre.setAttribute("aria-label", t("mcp.detail.json", { method: arrow.method || arrow.chip || "" }));
    box.append(pre);
  }
  return box;
}

// The request that left the workstation (`outbound-payload`, as the atelier's Orchestration).
function outboundPayload(request) {
  const box = el("div", "mcp-outbound");
  box.append(el("div", "mcp-outbound-head", t("mcp.detail.outbound")));
  box.append(el("p", "mcp-outbound-line", `${request.method} ${request.url}`));
  if ((request.headers || []).length) {
    const details = el("details", "mcp-outbound-headers");
    details.append(el("summary", null, t("mcp.detail.headers")));
    details.append(el("pre", "mcp-json", request.headers.map((h) => `${h.name}: ${h.value}`).join("\n")));
    box.append(details);
  }
  if (request.body) {
    const pre = el("pre", "mcp-json", pretty(request.body));
    pre.lang = "en";
    pre.tabIndex = 0;
    pre.setAttribute("role", "region");
    pre.setAttribute("aria-label", t("mcp.detail.body"));
    box.append(pre);
  }
  return box;
}

function phaseTitle(phase) {
  const server = serverLabel(phase.server);
  switch (phase.exchange) {
    case "connect":
      return t("mcp.phase.connect", { server });
    case "call":
      return t(phase.by === "model" ? "mcp.phase.call_model" : "mcp.phase.call_hand");
    case "read":
      return t("mcp.phase.read", { uri: phase.start.uri });
    case "prompt":
      return t("mcp.phase.prompt", { name: phase.start.prompt });
    default:
      if (phase.by === "model") return t("mcp.phase.call_model");
      return t("mcp.phase.ask", { name: phase.start.uri || phase.start.prompt || "" });
  }
}

function phaseSummary(phase) {
  const end = phase.end;
  if (!end) return t("mcp.phase.running");
  if (end.status === "cancelled") return t("mcp.phase.stopped");
  // A failure first, whatever the exchange (an `ask`'s `outcome` says its own end).
  if (end.status !== "ok" && !end.outcome) {
    const reason = end.error_text || (end.error_kind ? t(`mcp.error_kinds.${end.error_kind}`) : "");
    return t("mcp.phase.failed", { reason });
  }
  const time = duration(end.duration_ms);
  if (phase.exchange === "connect") {
    return t("mcp.phase.opened", { time, lists: primitivesText(end) });
  }
  if (phase.exchange === "call") {
    const said = t("mcp.phase.call_summary", { tool: end.tool, time });
    return end.is_error ? `${said} · isError` : said;
  }
  if (phase.exchange === "ask") {
    const parts = [time, end.share_text, end.outcome ? t(`mcp.outcomes.${end.outcome}`) : null];
    return parts.filter(Boolean).join(" · ");
  }
  if (end.status !== "ok") return t("mcp.phase.failed", { reason: end.error_text || "" });
  return time;
}

function phaseNode(phase) {
  let node = phaseNodes.get(phase.key);
  if (node) return node;
  const section = el("section", "mcp-phase");
  section.dataset.phase = phase.key;
  const heading = el("h3", "mcp-phase-header");
  const toggle = el("button", "mcp-phase-toggle");
  toggle.type = "button";
  const list = el("ol", "mcp-arrows");
  list.id = `mcp-phase-${phase.key}`;
  toggle.setAttribute("aria-controls", list.id);
  toggle.setAttribute("aria-expanded", "true");
  const chevron = el("span", "mcp-chevron", "▾");
  chevron.setAttribute("aria-hidden", "true");
  const title = el("span", "mcp-phase-title");
  const meta = el("span", "mcp-phase-meta");
  toggle.append(chevron, title, meta);
  heading.append(toggle);
  // « Par le modèle » is an `ask` without `of`: the phase of a tool call, its « Pourquoi ».
  const kind = phase.exchange === "ask" && phase.by === "model" ? "call" : phase.exchange;
  const why = el("button", "mcp-phase-why", text(`phases.${kind}.why_label_text`));
  why.type = "button";
  const whyBox = el("p", "mcp-phase-explain", text(`phases.${kind}.why_text`));
  whyBox.id = `mcp-why-${phase.key}`;
  whyBox.hidden = true;
  why.setAttribute("aria-expanded", "false");
  why.setAttribute("aria-controls", whyBox.id);
  why.addEventListener("click", () => {
    whyBox.hidden = !whyBox.hidden;
    why.setAttribute("aria-expanded", String(!whyBox.hidden));
  });
  toggle.addEventListener("click", () => setFolded(phase.key, toggle.getAttribute("aria-expanded") === "true"));
  section.append(heading, why, whyBox, list);
  $("mcp-seq").append(section);
  node = { section, heading, list, toggle, title, meta, why, whyBox };
  phaseNodes.set(phase.key, node);
  reveal(section, false);
  return node;
}

function setFolded(key, folded) {
  const node = phaseNodes.get(key);
  if (!node) return;
  node.toggle.setAttribute("aria-expanded", String(!folded));
  node.list.hidden = folded;
  node.section.classList.toggle("is-folded", folded);
  updateRoving();
  layer?.schedule();
}

function clearSequence() {
  $("mcp-seq").replaceChildren();
  rows.clear();
  phaseNodes.clear();
  openDetails.clear();
  current = null;
  shownIndex = -1;
  unseen = 0;
  renderNewChip();
}

// Draws what `frames` gave, row by row: a row is created once, rebuilt only when its data
// changed, never the whole list (EXPERIENCE.md: the list is never rebuilt during a session).
function renderSequence(model, { restoring = false } = {}) {
  const startedPhases = [];
  for (const phase of model.phases) {
    const fresh = !phaseNodes.has(phase.key);
    const node = phaseNode(phase);
    node.title.textContent = phaseTitle(phase);
    node.meta.textContent = ` · ${phaseSummary(phase)}`;
    if (fresh) startedPhases.push(phase.key);
  }
  for (const arrow of model.arrows) {
    const node = phaseNodes.get(arrow.phase) ?? phaseNodes.get(model.phases.at(-1)?.key);
    if (!node) continue;
    const sig = JSON.stringify(arrow);
    let entry = rows.get(arrow.key);
    if (!entry) {
      const li = el("li");
      node.list.append(li);
      entry = { li, sig: null };
      rows.set(arrow.key, entry);
      reveal(li, false);
      li.classList.add("mcp-ahead");
    }
    if (entry.sig !== sig) {
      const wasAhead = entry.li.classList.contains("mcp-ahead");
      const unrevealed = entry.li.classList.contains("diagram-unrevealed");
      renderArrow(arrow, entry.li);
      entry.li.classList.toggle("mcp-ahead", wasAhead);
      entry.li.classList.toggle("diagram-unrevealed", unrevealed);
      entry.sig = sig;
    }
  }
  // A new phase folds the former ones, but the one holding the focus (EXPERIENCE.md); a reload
  // folds every phase but the last.
  if (restoring) {
    const last = model.phases.at(-1)?.key;
    for (const key of phaseNodes.keys()) setFolded(key, key !== last);
  } else if (startedPhases.length) {
    for (const key of phaseNodes.keys()) {
      if (startedPhases.includes(key)) continue;
      const node = phaseNodes.get(key);
      if (!node.section.contains(document.activeElement)) setFolded(key, true);
    }
  }
  $("mcp-seq-empty").hidden = model.phases.length > 0;
}

// ---------- what a step shows (progressive discovery, AD-28) ----------

function archNode(col, server) {
  const id = COLS[col];
  if (id === "client" || id === "server" || id === "source") return `${id}-${server}`;
  return id;
}

function wireOf(arrow) {
  const pair = [arrow.from, arrow.to].sort((a, b) => a - b).join("");
  return { "02": "user", "12": "model", "34": `t-${arrow.server}`, "45": `s-${arrow.server}` }[pair] ?? null;
}

function revealedAt(index) {
  const model = store.model;
  const cols = new Set();
  const nodes = new Set();
  const wires = new Set();
  const keys = new Set();
  let prims = false;
  if (!model) return { cols, nodes, wires, keys, prims };
  for (const arrow of model.arrows) {
    if (index < 0 || arrow.revealAt > index) continue;
    keys.add(arrow.key);
    if (arrow.kind === "note") continue;
    cols.add(arrow.from);
    cols.add(arrow.to);
    if (arrow.kind === "ghost") continue;
    nodes.add(archNode(arrow.from, arrow.server));
    nodes.add(archNode(arrow.to, arrow.server));
    const w = wireOf(arrow);
    if (w) wires.add(w);
    if (arrow.prims) prims = true;
  }
  return { cols, nodes, wires, keys, prims };
}

function onShow(arrow, index) {
  shownIndex = index;
  current = arrow ? store.model?.arrows.find((a) => a.key === arrow.key) ?? arrow : null;
  const seen = revealedAt(index);
  for (const a of store.model?.arrows ?? []) {
    const entry = rows.get(a.key);
    if (!entry) continue;
    const on = seen.keys.has(a.key);
    reveal(entry.li, on);
    entry.li.classList.toggle("mcp-ahead", !on);
  }
  for (const phase of store.model?.phases ?? []) {
    const node = phaseNodes.get(phase.key);
    const on = (store.model.arrows || []).some((a) => a.phase === phase.key && seen.keys.has(a.key));
    reveal(node.section, on);
    node.section.classList.toggle("mcp-ahead", !on);
  }
  const heads = [...$("mcp-heads").querySelectorAll(".mcp-head")];
  heads.forEach((head, i) => reveal(head, seen.cols.has(i)));
  [...$("mcp-lifelines").children].forEach((line, i) => reveal(line, seen.cols.has(i)));
  // The current arrow: ▶, its chip lit, its two heads, its phase open, kept in view.
  for (const entry of rows.values()) {
    entry.li.classList.remove("is-current");
    entry.li.querySelector(".mcp-arrow")?.removeAttribute("aria-current");
  }
  const entry = current ? rows.get(current.key) : null;
  light($("mcp-seq"), entry ? entry.li.querySelector(".mcp-cap .diagram-block") : null);
  light($("mcp-heads"), current ? [heads[current.from], heads[current.to]] : null);
  if (entry) {
    entry.li.classList.add("is-current");
    entry.li.querySelector(".mcp-arrow")?.setAttribute("aria-current", "step");
    const node = phaseNodes.get(current.phase);
    if (node && node.list.hidden) setFolded(current.phase, false);
    if (!suspended && !$("mcp-seq").contains(document.activeElement)) {
      programmatic = true;
      entry.li.scrollIntoView({ block: "nearest" });
      requestAnimationFrame(() => (programmatic = false));
    } else if (stepper?.live) {
      unseen += 1;
      renderNewChip();
    }
  }
  updateRoving();
  renderArchReveal(seen);
  renderModelReveal(seen);
}

function renderNewChip() {
  const chip = $("mcp-new-messages");
  chip.hidden = !(suspended && unseen > 0);
  chip.textContent = t("mcp.seq.new_messages", { count: unseen, n: unseen });
}

// One tab stop for the arrows (roving tabindex): the current arrow, else the first one shown.
function visibleArrows() {
  return [...$("mcp-seq").querySelectorAll("li:not(.mcp-ahead) > button.mcp-arrow")].filter(
    (b) => !b.closest("ol").hidden
  );
}

function updateRoving() {
  const buttons = visibleArrows();
  const currentButton = current ? rows.get(current.key)?.li.querySelector("button.mcp-arrow") : null;
  const holder = buttons.includes(currentButton) ? currentButton : buttons[0];
  for (const button of $("mcp-seq").querySelectorAll("button.mcp-arrow")) button.tabIndex = button === holder ? 0 : -1;
}

function onSequenceKey(event) {
  const target = event.target.closest?.("button.mcp-arrow");
  if (!target) return;
  const buttons = visibleArrows();
  const at = buttons.indexOf(target);
  let next = null;
  if (event.key === "ArrowDown") next = buttons[Math.min(at + 1, buttons.length - 1)];
  else if (event.key === "ArrowUp") next = buttons[Math.max(at - 1, 0)];
  else if (event.key === "Home") next = buttons[0];
  else if (event.key === "End") next = buttons.at(-1);
  if (!next) return;
  event.preventDefault();
  for (const button of buttons) button.tabIndex = button === next ? 0 : -1;
  next.focus();
}

function describeStep(arrow) {
  const known = store.model?.arrows.find((a) => a.key === arrow.key) ?? arrow;
  return t("mcp.a11y.step", { from: columnName(known.from), to: columnName(known.to), label: arrowLabel(known) });
}

// ---------- Ce que le modèle voit ----------

const blockNodes = new Map(); // block key -> {node, sig}
let toolsKey = null;

function sentence(className, value) {
  return el("p", className, value);
}

function chooserBadge(kind) {
  const label = t(`mcp.choosers.${kind}`);
  return el("span", `mcp-badge is-${kind}`, label);
}

function renderModelPane(model) {
  const body = $("mcp-model-body");
  const connect = model?.connect;
  const phases = model?.phases ?? [];
  const connectPhase = phases[0];
  let state = "empty";
  if (connectPhase && !connect) state = "pending";
  else if (connect && connect.status !== "ok") state = "failed";
  else if (connect) state = "ready";
  if (body.dataset.state !== state || toolsKey !== (connectPhase?.key ?? null)) {
    body.replaceChildren();
    blockNodes.clear();
    body.dataset.state = state;
    toolsKey = connectPhase?.key ?? null;
    if (state === "empty") body.append(sentence("mcp-note", text("tools_empty_text")));
    if (state === "pending") body.append(sentence("mcp-note", t("mcp.model.listing")));
    if (state === "failed") body.append(sentence("mcp-note", t("mcp.model.failed", { server: serverLabel(connect.server) })));
    if (state === "ready") {
      const pending = sentence("mcp-note mcp-tools-pending", t("mcp.model.listing"));
      pending.id = "mcp-tools-pending";
      body.append(pending, toolsBlock(connect));
      const outside = sentence("mcp-note", text("outside_text"));
      outside.dataset.mv = "tools";
      body.append(outside);
    }
  }
  if (state !== "ready") return;
  for (const block of model.blocks) {
    const sig = JSON.stringify(block);
    const entry = blockNodes.get(block.key);
    if (entry && entry.sig === sig) continue;
    const node = contextBlock(block, model);
    node.dataset.mv = block.arrow;
    if (entry) entry.node.replaceWith(node);
    else body.append(node);
    reveal(node, false);
    blockNodes.set(block.key, { node, sig, block });
  }
}

function toolsBlock(connect) {
  const wrap = el("div", "mcp-tools-wrap");
  wrap.dataset.mv = "tools";
  if (!connect.tools) {
    const failed = (connect.list_errors || []).find((e) => e.method === "tools/list");
    wrap.append(sentence("mcp-note", failed ? t("mcp.lists.failed_tools", { reason: failed.error_text }) : t("mcp.lists.no_tools_announced")));
    return wrap;
  }
  const switcher = segmented("mcp-doc-mode", t("mcp.model.doc_mode"), [
    ["full", t("mcp.model.full")],
    ["lazy", t("mcp.model.lazy")],
  ], () => store.docMode, (value) => {
    store.docMode = value;
    fillTools(block, connect);
    say(t("mcp.model.total_said", { mode: t(`mcp.model.${value}`), total: tokens(totalOf(connect), connect.estimated) }));
  });
  wrap.append(switcher);
  const block = el("div", "mcp-context-block is-tools");
  wrap.append(block);
  fillTools(block, connect);
  return wrap;
}

const totalOf = (connect) => (store.docMode === "lazy" ? connect.lazy_tokens : connect.full_tokens);

function fillTools(block, connect) {
  block.replaceChildren();
  const head = el("h3", "mcp-block-title", t("mcp.model.tools_block"));
  head.append(chooserBadge("model"));
  const help = el("button", "mcp-info", "ⓘ");
  help.type = "button";
  help.setAttribute("aria-label", t("mcp.model.tools_help"));
  head.append(help);
  explain(help, text("tools_help_text"));
  block.append(head);
  const total = el("p", "mcp-total");
  total.append(el("span", "mcp-total-number", fmt(totalOf(connect))), el("span", "mcp-note", ` ${t("mcp.tokens_word")} · ${t(connect.estimated ? "mcp.model.estimated" : "mcp.model.counted")}`));
  block.append(total);
  const table = el("table", "mcp-weights");
  const headRow = el("tr");
  headRow.append(el("th", null, t(store.docMode === "lazy" ? "mcp.model.catalog_line" : "mcp.model.tool")), el("th", null, t("mcp.tokens_word")));
  const thead = el("thead");
  thead.append(headRow);
  const tbody = el("tbody");
  for (const tool of connect.tools) {
    const row = el("tr");
    const name = el("td", "mcp-code", store.docMode === "lazy" ? tool.line_text : tool.name);
    name.lang = "en";
    row.append(name, el("td", "mcp-number", fmt(store.docMode === "lazy" ? tool.line_tokens : tool.doc_tokens)));
    tbody.append(row);
  }
  if (store.docMode === "lazy" && connect.load_tool_doc_tokens != null) {
    const row = el("tr");
    row.append(el("td", "mcp-code", t("mcp.model.load_tool_doc")), el("td", "mcp-number", fmt(connect.load_tool_doc_tokens)));
    tbody.append(row);
  }
  table.append(thead, tbody);
  block.append(table);
  const toggle = el("button", "mcp-link", t("mcp.model.show_json"));
  toggle.type = "button";
  const pre = el("pre", "mcp-json", store.docMode === "lazy"
    ? pretty(connect.lazy_definition_text || "")
    : JSON.stringify(connect.tools.map((tool) => JSON.parse(tool.definition_text)), null, 2));
  pre.lang = "en";
  pre.id = "mcp-tools-json";
  pre.hidden = true;
  pre.tabIndex = 0;
  pre.setAttribute("role", "region");
  pre.setAttribute("aria-label", t("mcp.model.json_label"));
  toggle.setAttribute("aria-expanded", "false");
  toggle.setAttribute("aria-controls", pre.id);
  toggle.title = text("context_help_text");
  toggle.addEventListener("click", () => {
    pre.hidden = !pre.hidden;
    toggle.setAttribute("aria-expanded", String(!pre.hidden));
  });
  block.append(toggle, pre);
}

function contextBlock(block, model) {
  const p = block.payload;
  const node = el("div", `mcp-context-block is-${block.kind}`);
  const head = el("h3", "mcp-block-title");
  node.append(head);
  if (block.kind === "sent") {
    const index = p.index;
    head.append(t("mcp.model.sent"), el("span", "mcp-tag", t("mcp.model.call_index", { n: index })));
    const parts = el("ul", "mcp-sends");
    for (const send of p.sends || []) {
      const item = el("li");
      item.append(el("span", null, send.label_text), el("span", "mcp-number", tokens(send.tokens)));
      parts.append(item);
    }
    node.append(parts);
    node.append(sentence("mcp-block-line", t("mcp.model.sent_total", { tokens: tokens(p.prompt_tokens, p.estimated) })));
    if (p.doc_mode === "none") node.append(sentence("mcp-block-line", t("mcp.model.no_tools_sent")));
    if (p.model?.hosting === "network") node.append(sentence("mcp-block-line", t("mcp.model.left_for", { provider: p.model.provider ?? "" })));
    if (block.ended) {
      node.append(sentence("mcp-block-line", t("mcp.model.generated", { time: duration(block.ended.duration_ms) })));
      if (block.ended.reasoning_cut) node.append(sentence("mcp-block-line", t("mcp.model.reasoning_cut")));
      if (block.ended.outcome === "overflow") {
        head.append(el("span", "mcp-tag is-error", t("mcp.model.not_sent")));
        node.append(sentence("mcp-block-line", block.ended.error_text || ""));
      }
    }
    node.append(sentence("mcp-note", t("mcp.model.no_system_prompt")));
  } else if (block.kind === "result") {
    head.append(t("mcp.model.result"), el("span", "mcp-number", tokens(p.tokens, p.estimated)));
    if (p.is_error) head.append(el("span", "mcp-tag is-error", "isError"));
    node.append(sentence("mcp-note", block.sent ? t("mcp.model.result_sent") : t("mcp.model.result_hand")));
    if (!block.sent) node.append(sentence("mcp-note", text("reinjected_help_text")));
    node.append(el("pre", "mcp-text", p.text || ""));
    if (p.truncated) node.append(sentence("mcp-note", t("mcp.model.truncated", { kept: p.truncated.tokens, total: p.truncated.total_tokens })));
  } else if (block.kind === "resource") {
    head.append(t("mcp.model.resource"), el("span", "mcp-number", tokens(p.tokens, p.estimated)), chooserBadge("app"));
    const sent = sentAfter(model, block.key);
    node.append(sentence("mcp-note", t(sent ? "mcp.model.resource_sent" : "mcp.model.resource_waits")));
    node.append(el("pre", "mcp-text", p.text || ""));
  } else if (block.kind === "prompt") {
    head.append(t("mcp.model.prompt"), el("span", "mcp-number", tokens(p.tokens, p.estimated)), chooserBadge("user"));
    const sent = sentAfter(model, block.key);
    node.append(sentence("mcp-note", t(sent ? "mcp.model.prompt_sent" : "mcp.model.prompt_waits")));
    node.append(el("pre", "mcp-text", (p.messages || []).map((m) => `${m.role} : ${m.text}`).join("\n\n")));
  } else if (block.kind === "refused") {
    head.append(t("mcp.model.refused"), el("span", "mcp-tag is-error", t("mcp.outcomes.refused")));
    node.append(sentence("mcp-block-line", p.refusal_text || ""));
  }
  return node;
}

function sentAfter(model, step) {
  return model.phases.some((phase) => phase.exchange === "ask" && phase.start.of === step);
}

function renderModelReveal(seen) {
  const body = $("mcp-model-body");
  const toolsShown = [...seen.keys].some((key) => store.model?.arrows.find((a) => a.key === key)?.mv === "tools");
  for (const node of body.querySelectorAll("[data-mv]")) {
    const key = node.dataset.mv;
    const on = key === "tools" ? toolsShown : seen.keys.has(key);
    reveal(node, on);
    node.classList.toggle("mcp-ahead", !on);
  }
  const pending = $("mcp-tools-pending");
  if (pending) pending.hidden = toolsShown;
}

// ---------- Architecture ----------

function archBlock(className, node, label) {
  const button = el("button", `${className} diagram-block`);
  button.type = "button";
  button.dataset.node = node;
  if (label !== undefined) button.append(label);
  return button;
}

function robot(model) {
  const button = archBlock("mcp-robot", "model");
  const svg = document.createElementNS("http://www.w3.org/2000/svg", "svg");
  svg.setAttribute("viewBox", "0 0 30 26");
  svg.setAttribute("aria-hidden", "true");
  svg.innerHTML =
    '<rect class="mcp-antenna" x="14" y="0" width="2" height="5" rx="1"/>' +
    '<rect class="mcp-robot-body" x="4" y="5" width="22" height="18" rx="6"/>' +
    '<rect class="mcp-robot-visor" x="8" y="10" width="14" height="8" rx="4"/>' +
    '<circle class="mcp-robot-eye" cx="12" cy="14" r="1.6"/><circle class="mcp-robot-eye" cx="18" cy="14" r="1.6"/>';
  const cloud = model?.hosting === "network";
  button.append(svg, el("span", "mcp-robot-name", cloud ? t("mcp.columns.cloud", { provider: model.provider ?? "" }) : columnName(MODEL)), el("small", null, model?.label ?? ""));
  explain(button, columnExplain("model"));
  return button;
}

function buildArch() {
  const arch = $("mcp-arch");
  arch.replaceChildren();
  const model = modelInfo();
  const cloud = model?.hosting === "network";
  const local = el("div", "mcp-zone is-local");
  local.setAttribute("role", "group");
  local.setAttribute("aria-label", t("mcp.arch.local_zone"));
  const lanes = el("div", "mcp-lanes-local");
  lanes.append(el("span", "mcp-zone-label", t("mcp.arch.local_label")));
  const user = archBlock("mcp-node is-user", "user", t("mcp.arch.user"));
  explain(user, columnExplain("user"));
  lanes.append(user);
  if (!cloud) lanes.append(robot(model));
  const host = el("div", "mcp-host diagram-block");
  host.dataset.node = "host";
  host.setAttribute("role", "group");
  host.setAttribute("aria-label", t("mcp.arch.host"));
  const hostLabel = el("button", "mcp-host-label", t("mcp.arch.host"));
  hostLabel.type = "button";
  explain(hostLabel, columnExplain("host"));
  host.append(hostLabel);
  for (const server of store.servers) {
    const client = archBlock("mcp-node is-client", `client-${server.id}`, t("mcp.arch.client", { server: server.label_text }));
    client.append(srOnly(t("mcp.arch.state_idle")));
    explain(client, columnExplain("client"));
    host.append(client);
  }
  lanes.append(host);
  const network = el("div", "mcp-zone is-network");
  network.setAttribute("role", "group");
  network.setAttribute("aria-label", t("mcp.arch.network_zone"));
  network.append(el("span", "mcp-zone-label", t("mcp.arch.network_label")));
  const netLanes = el("div", "mcp-lanes-network");
  if (cloud) netLanes.append(robot(model));
  store.servers.forEach((server, i) => {
    const node = archBlock(`mcp-node is-server ${server.network ? "is-net" : ""}`, `server-${server.id}`);
    node.append(el("span", "mcp-node-name", server.label_text), el("span", "mcp-prims"));
    node.append(srOnly(""));
    explain(node, columnExplain("server", server));
    const source = archBlock(`mcp-node is-source ${server.network ? "is-hidden-side" : ""}`, `source-${server.id}`, server.source_label_text ?? "");
    explain(source, columnExplain("source", server));
    node.style.gridRow = String(i + 1);
    source.style.gridRow = String(i + 1);
    (server.network ? netLanes : lanes).append(node, source);
  });
  local.append(lanes);
  network.append(netLanes);
  const boundary = el("div", "mcp-boundary");
  boundary.setAttribute("aria-hidden", "true");
  boundary.append(el("span", null, t("mcp.arch.boundary")));
  const empty = el("p", "mcp-arch-empty", text("arch_empty_text"));
  empty.id = "mcp-arch-empty";
  arch.append(local, boundary, network, empty);
  for (const node of arch.querySelectorAll("[data-node]")) reveal(node, false);
  reveal(network, false);
  reveal(boundary, false);
  layer = wireLayer(arch, drawWires);
}

let shownWires = new Set();
let litWire = null;

function drawWires({ box }) {
  const arch = $("mcp-arch");
  const q = (id) => arch.querySelector(`[data-node="${id}"]`);
  const parts = [];
  const add = (id, from, to, className, label) => {
    if (!shownWires.has(id) || !from || !to || from.classList.contains("diagram-unrevealed")) return;
    const a = box(from);
    const b = box(to);
    const y = a.cy;
    const [x1, x2] = a.cx < b.cx ? [a.r, b.l] : [a.l, b.r];
    const d = `M${x1},${y} L${x2},${b.cy}`;
    parts.push(wire(d, `diagram-wire ${className}`));
    if (litWire === id) {
      parts.push(wire(d, "diagram-path"), wire(d, `diagram-path-core ${className.includes("is-dashed") && stepper?.live ? "is-flow" : ""}`));
    }
    const failed = id.startsWith("t-") && store.failures.has(id.slice(2));
    if (failed) {
      parts.push(wire(d, "diagram-path-block"));
      parts.push(marker((x1 + x2) / 2, (y + b.cy) / 2, "✖", "is-block"));
    }
    if (id.startsWith("t-")) {
      // « Avec MCP »: every client→server wire ends in the same plug, one protocol for all.
      const plug = svgEl("text", { x: x2 + (x1 < x2 ? -9 : 9), y: b.cy + 5, "text-anchor": "middle", class: "mcp-plug" });
      plug.textContent = "🔌";
      parts.push(plug);
    }
    if (label) {
      const textNode = document.createElementNS("http://www.w3.org/2000/svg", "text");
      textNode.setAttribute("x", String((x1 + x2) / 2));
      textNode.setAttribute("y", String(Math.min(y, b.cy) - 6));
      textNode.setAttribute("text-anchor", "middle");
      textNode.setAttribute("class", "mcp-wire-label");
      textNode.textContent = label;
      parts.push(textNode);
    }
  };
  add("user", q("user"), q("host"), "", null);
  add("model", q("model"), q("host"), modelInfo()?.hosting === "network" ? "is-dashed" : "", null);
  for (const server of store.servers) {
    add(`t-${server.id}`, q(`client-${server.id}`), q(`server-${server.id}`), server.network ? "is-dashed" : "",
      text(`transports.${server.network ? "streamable_http" : "stdio"}.label_text`).split(" ")[0]);
    add(`s-${server.id}`, q(`server-${server.id}`), q(`source-${server.id}`), "mcp-wire-source", null);
  }
  return parts;
}

function renderArchReveal(seen) {
  const arch = $("mcp-arch");
  const nodes = new Set(seen.nodes);
  for (const server of store.failures.keys()) {
    nodes.add(`client-${server}`);
    nodes.add(`server-${server}`);
    seen.wires.add(`t-${server}`);
  }
  if ([...nodes].some((n) => n.startsWith("client-"))) nodes.add("host");
  for (const node of arch.querySelectorAll("[data-node]")) reveal(node, nodes.has(node.dataset.node));
  const network = [...nodes].some((n) => {
    const server = n.split("-").slice(1).join("-");
    return (n.startsWith("server-") || n.startsWith("source-")) && isNetwork(server);
  }) || (nodes.has("model") && modelInfo()?.hosting === "network");
  reveal(arch.querySelector(".mcp-zone.is-network"), network);
  reveal(arch.querySelector(".mcp-boundary"), network);
  const empty = $("mcp-arch-empty");
  if (empty) empty.hidden = nodes.size > 0;
  // The connection's state and lists, on the client and its server.
  const connect = store.model?.connect;
  for (const server of store.servers) {
    const open = store.openServer === server.id;
    const client = arch.querySelector(`[data-node="client-${server.id}"]`);
    const node = arch.querySelector(`[data-node="server-${server.id}"]`);
    client?.classList.toggle("is-idle", !open);
    node?.classList.toggle("is-idle", !open && !store.failures.has(server.id));
    node?.classList.toggle("is-failed", store.failures.has(server.id));
    if (client) client.querySelector(".mcp-sr-only").textContent = `, ${t(open ? "mcp.arch.state_open" : "mcp.arch.state_idle")}`;
    const prims = node?.querySelector(".mcp-prims");
    const shown = connect && connect.server === server.id && connect.status === "ok" && seen.prims;
    if (prims) prims.textContent = shown ? primitivesText(connect) : "";
    if (node) {
      node.querySelector(".mcp-sr-only").textContent = `, ${t(server.network ? "mcp.arch.where_network" : "mcp.arch.where_local")}, ${text(`transports.${server.network ? "streamable_http" : "stdio"}.label_text`)}, ${t(open ? "mcp.arch.state_open" : store.failures.has(server.id) ? "mcp.arch.state_failed" : "mcp.arch.state_idle")}${shown ? `, ${primitivesText(connect)}` : ""}`;
    }
  }
  // Lit: the current arrow's two blocks and its wire; the robot's antenna during a generation.
  const lit = current && current.kind !== "note" && current.kind !== "ghost"
    ? [archNode(current.from, current.server), archNode(current.to, current.server)]
    : [];
  light(arch, lit.map((id) => arch.querySelector(`[data-node="${id}"]`)).filter(Boolean));
  litWire = current && current.kind !== "ghost" ? wireOf(current) : null;
  const generating = Boolean(store.model?.generating) && stepper?.live;
  arch.querySelector('[data-node="model"]')?.classList.toggle("is-generating", generating);
  shownWires = seen.wires;
  layer?.schedule();
}

// « Avant MCP » (EXPERIENCE.md, DESIGN.md > mcp-arch-before): a schema of principle, nothing
// captured, nothing lit. The same zones and host frame; in the host, one integration written
// by hand per source, each wired straight to its source by a connector of its own shape
// (● circle, ◆ diamond, ▲ triangle). The schema is drawn for the eyes (`aria-hidden`); its text
// equivalent, the integrations and the captions, is a list read by assistive technologies.
const BEFORE_SHAPES = { local: "circle", datagouv: "diamond", mslearn: "triangle" };
const BEFORE_MARKS = { circle: "●", diamond: "◆", triangle: "▲" };
let beforeLayer = null;

function buildBefore() {
  const box = $("mcp-arch-before");
  box.replaceChildren();
  const schema = el("div", "mcp-before-schema");
  schema.setAttribute("aria-hidden", "true");
  const local = el("div", "mcp-zone is-local");
  const lanes = el("div", "mcp-lanes-before");
  lanes.append(el("span", "mcp-zone-label", t("mcp.arch.local_label")));
  lanes.append(el("div", "mcp-before-node is-user", t("mcp.arch.user")));
  lanes.append(el("div", "mcp-before-node is-model", columnName(MODEL)));
  const host = el("div", "mcp-before-host");
  host.append(el("span", "mcp-before-host-label", t("mcp.arch.host")));
  const network = el("div", "mcp-zone is-network");
  network.append(el("span", "mcp-zone-label", t("mcp.arch.network_label")));
  const netLanes = el("div", "mcp-lanes-before-network");
  const sr = el("ul", "mcp-sr-only");
  store.servers.forEach((server, i) => {
    const shape = BEFORE_SHAPES[server.id] ?? "circle";
    const integration = el("div", "mcp-before-node is-integration", `${BEFORE_MARKS[shape]} ${text(`before.integrations.${server.id}`)}`);
    integration.dataset.before = server.id;
    integration.style.gridRow = String(i + 1);
    host.append(integration);
    const source = el("div", `mcp-before-node is-source ${server.network ? "is-hidden-side" : ""}`, server.source_label_text ?? "");
    source.dataset.beforeSource = server.id;
    source.dataset.shape = shape;
    source.style.gridRow = String(i + 1);
    (server.network ? netLanes : lanes).append(source);
    sr.append(el("li", null, `${text(`before.integrations.${server.id}`)} → ${server.source_label_text ?? ""}`));
  });
  lanes.append(host);
  local.append(lanes);
  network.append(netLanes);
  const boundary = el("div", "mcp-boundary");
  boundary.append(el("span", null, t("mcp.arch.boundary")));
  schema.append(local, boundary, network);
  const captions = el("div", "mcp-before-captions");
  captions.setAttribute("aria-hidden", "true");
  captions.append(el("span", "mcp-before-banner", text("before.banner_text")));
  for (const caption of store.content?.before?.captions ?? []) captions.append(el("span", null, caption));
  const said = el("div", "mcp-sr-only");
  const captionList = el("ul");
  for (const caption of store.content?.before?.captions ?? []) captionList.append(el("li", null, caption));
  said.append(el("p", null, text("before.banner_text")), sr, captionList);
  box.append(schema, captions, said);
  beforeLayer = wireLayer(schema, drawBefore);
}

// A connector's end, 12 px, ink: the shape that says « this code for this API only ».
function connectorEnd(shape, x, y) {
  const size = 6;
  if (shape === "circle") return svgEl("circle", { cx: x, cy: y, r: size, class: "mcp-connector-end" });
  const points = shape === "diamond"
    ? [[x, y - size], [x + size, y], [x, y + size], [x - size, y]]
    : [[x - size, y + size], [x, y - size], [x + size, y + size]];
  return svgEl("polygon", { points: points.map((p) => p.join(",")).join(" "), class: "mcp-connector-end" });
}

function drawBefore({ box }) {
  const schema = $("mcp-arch-before").querySelector(".mcp-before-schema");
  if (!schema || store.archView !== "before") return null;
  const parts = [];
  for (const server of store.servers) {
    const from = schema.querySelector(`[data-before="${server.id}"]`);
    const to = schema.querySelector(`[data-before-source="${server.id}"]`);
    if (!from || !to) continue;
    const a = box(from);
    const b = box(to);
    const end = b.l - 8;
    parts.push(wire(`M${a.r},${a.cy} L${end},${b.cy}`, "diagram-wire mcp-before-wire"));
    parts.push(connectorEnd(to.dataset.shape, end, b.cy));
  }
  return parts;
}

function setArchView(view, save = true) {
  store.archView = view === "before" ? "before" : "after";
  for (const button of $("mcp-arch-switch").querySelectorAll("[role=radio]")) {
    button.setAttribute("aria-checked", String(button.dataset.view === store.archView));
    button.tabIndex = button.dataset.view === store.archView ? 0 : -1;
  }
  $("mcp-arch").hidden = store.archView === "before";
  $("mcp-arch-before").hidden = store.archView !== "before";
  beforeLayer?.schedule();
  if (save) {
    try {
      localStorage.setItem(ARCH_KEY, store.archView);
    } catch {
      // No storage: the view lasts until the page is reloaded.
    }
  }
  layer?.schedule();
}

// ---------- Serveurs et commandes ----------

// A segmented choice (`mcp-mode-switch`): a named radiogroup, arrows to move.
function segmented(id, label, options, get, set, disabled = () => null) {
  const group = el("div", "mcp-switch");
  group.id = id;
  group.setAttribute("role", "radiogroup");
  group.setAttribute("aria-label", label);
  const buttons = options.map(([value, name]) => {
    const button = el("button", null, name);
    button.type = "button";
    button.setAttribute("role", "radio");
    button.dataset.value = value;
    button.addEventListener("click", () => {
      if (button.getAttribute("aria-disabled") === "true") return;
      set(value);
      update();
    });
    return button;
  });
  const update = () => {
    for (const button of buttons) {
      const on = get() === button.dataset.value;
      button.setAttribute("aria-checked", String(on));
      button.tabIndex = on ? 0 : -1;
      const reason = disabled(button.dataset.value);
      button.setAttribute("aria-disabled", String(Boolean(reason)));
      button.title = reason || "";
    }
  };
  group.addEventListener("keydown", (event) => {
    const keys = ["ArrowLeft", "ArrowUp", "ArrowRight", "ArrowDown"];
    if (!keys.includes(event.key)) return;
    event.preventDefault();
    const at = buttons.indexOf(document.activeElement);
    const step = keys.indexOf(event.key) < 2 ? -1 : 1;
    const next = buttons[(at + step + buttons.length) % buttons.length];
    next.focus();
    next.click();
  });
  group.append(...buttons);
  group.update = update;
  update();
  return group;
}

function renderServers() {
  const list = $("mcp-servers");
  if (!list.childElementCount) {
    for (const server of store.servers) {
      const item = el("li", `mcp-server ${server.network ? "is-net" : "is-local"}`);
      item.dataset.server = server.id;
      const label = el("label", "mcp-server-choice");
      const radio = el("input");
      radio.type = "radio";
      radio.name = "mcp-server";
      radio.value = server.id;
      radio.addEventListener("change", () => {
        store.selected = server.id;
        renderControls();
        renderHeads();
      });
      const name = el("span", "mcp-server-name", server.label_text);
      const hosting = el("span", `mcp-hosting ${server.network ? "is-network" : "is-local"}`);
      if (server.network) {
        const globe = el("span", null, "🌐");
        globe.setAttribute("aria-hidden", "true");
        hosting.append(globe, srOnly(t("mcp.a11y.network")), ` ${t("mcp.servers.network")}`);
      } else {
        hosting.textContent = t("mcp.servers.local");
      }
      label.append(radio, name, hosting, el("span", "mcp-server-transport", text(`transports.${server.transport}.label_text`)));
      const info = el("button", "mcp-info", "ⓘ");
      info.type = "button";
      info.setAttribute("aria-label", t("mcp.servers.details", { server: server.label_text }));
      const details = el("div", "mcp-server-details");
      details.id = `mcp-server-details-${server.id}`;
      details.hidden = true;
      details.append(sentence("mcp-note", server.network ? t("mcp.servers.address", { value: server.url }) : t("mcp.servers.command", { value: server.command })));
      details.append(sentence("mcp-note", server.sends_text ? t("mcp.servers.sends", { value: server.sends_text }) : t("mcp.servers.nothing_leaves")));
      details.append(sentence("mcp-note", text("servers_help_text")));
      info.setAttribute("aria-expanded", "false");
      info.setAttribute("aria-controls", details.id);
      info.addEventListener("click", () => {
        details.hidden = !details.hidden;
        info.setAttribute("aria-expanded", String(!details.hidden));
      });
      const badges = el("span", "mcp-server-badges");
      item.append(label, info, badges, details);
      list.append(item);
    }
  }
  for (const item of list.children) {
    const id = item.dataset.server;
    item.querySelector("input").checked = id === store.selected;
    item.classList.toggle("is-open", store.openServer === id);
    const badges = item.querySelector(".mcp-server-badges");
    badges.replaceChildren();
    if (store.openServer === id) badges.append(el("span", "mcp-badge-state is-open", t("mcp.servers.connected")));
    if (store.failures.has(id)) badges.append(el("span", "mcp-badge-state is-failed", t("mcp.servers.unreachable")));
  }
  const note = $("mcp-server-note");
  const failed = store.failures.get(store.selected);
  const closed = store.model?.closed;
  if (failed) note.textContent = t("mcp.servers.failed_note", { reason: failed });
  else if (closed && !store.openServer) note.textContent = t("mcp.notes.closed", { cause: t(`mcp.close_causes.${closed.cause}`) });
  else if (!store.openServer) note.textContent = t("mcp.servers.hint");
  note.hidden = Boolean(store.openServer) && !failed;
}

function idle() {
  return store.session.state === "idle" && !store.pending;
}

function busyReason() {
  if (store.pending) return t("mcp.servers.sending");
  const { state, reason_text: reason } = store.session;
  if (state !== "idle") return text("busy_text", { reason: reason || state }) || reason || state;
  return null;
}

function setAvailable(button, reason) {
  if (!button) return;
  button.setAttribute("aria-disabled", String(Boolean(reason)));
  if (reason) button.title = reason;
  else button.removeAttribute("title");
}

const connection = () => (store.model?.connect?.status === "ok" && store.openServer === store.model.connect.server ? store.model.connect : null);

function lastOk(kind) {
  const model = store.model;
  if (!model) return null;
  const phase = [...model.phases].reverse().find((p) => p.exchange === kind && p.end?.status === "ok");
  return phase ?? null;
}

function renderControls() {
  const busy = busyReason();
  const banner = $("mcp-busy");
  banner.hidden = !busy || store.pending;
  banner.textContent = busy || "";
  const connect = $("mcp-connect");
  connect.textContent = t(store.openServer === store.selected ? "mcp.servers.reconnect" : "mcp.servers.connect");
  setAvailable(connect, idle() ? null : busy);
  setAvailable($("mcp-stop"), store.session.state === "mcp_lab" ? null : t("mcp.servers.nothing_to_stop"));
  renderServers();
  renderCommands();
}

let commandsKey = null;

function renderCommands() {
  const box = $("mcp-commands");
  const open = connection();
  const key = open ? `${store.model.phases[0]?.key}:${store.selected}` : null;
  if (key !== commandsKey) {
    commandsKey = key;
    box.replaceChildren();
    if (open && open.server === store.selected) buildCommands(box, open);
  }
  updateCommands();
}

function tabReason(kind, end) {
  if (!end.primitives?.[kind]) return t(`mcp.lists.not_announced.${kind}`);
  return null;
}

function buildCommands(box, end) {
  const tablist = el("div", "mcp-primitive-tabs");
  tablist.setAttribute("role", "tablist");
  tablist.setAttribute("aria-label", t("mcp.tabs.label"));
  const reasons = el("div", "mcp-tab-reasons");
  const tabs = [];
  const panels = [];
  for (const [kind, icon] of [["tools", "🔧"], ["resources", "📄"], ["prompts", "💬"]]) {
    const tab = el("button", "mcp-tab");
    tab.type = "button";
    tab.id = `mcp-tab-${kind}`;
    tab.setAttribute("role", "tab");
    tab.dataset.tab = kind;
    const list = end[kind];
    const count = list ? ` ${fmt(list.length)}` : end.primitives?.[kind] ? " ⚠" : "";
    const reason = tabReason(kind, end);
    const iconNode = el("span", null, icon);
    iconNode.setAttribute("aria-hidden", "true");
    tab.append(reason ? "⊘ " : "", iconNode, ` ${t(`mcp.tabs.${kind}`)}${count}`);
    if (reason) {
      tab.setAttribute("aria-disabled", "true");
      tab.classList.add("is-unavailable");
      const said = sentence("mcp-note", reason);
      said.id = `mcp-tab-reason-${kind}`;
      tab.setAttribute("aria-describedby", said.id);
      reasons.append(said);
    }
    const panel = el("div", "mcp-tab-panel");
    panel.id = `mcp-panel-${kind}`;
    panel.setAttribute("role", "tabpanel");
    panel.setAttribute("aria-labelledby", tab.id);
    tab.setAttribute("aria-controls", panel.id);
    tab.addEventListener("click", () => {
      if (tab.getAttribute("aria-disabled") === "true") return;
      store.tab = kind;
      selectTab();
    });
    tabs.push(tab);
    panels.push(panel);
    tablist.append(tab);
  }
  tablist.addEventListener("keydown", (event) => {
    const at = tabs.indexOf(document.activeElement);
    if (at < 0) return;
    let next = null;
    if (event.key === "ArrowRight") next = tabs[(at + 1) % tabs.length];
    else if (event.key === "ArrowLeft") next = tabs[(at - 1 + tabs.length) % tabs.length];
    else if (event.key === "Home") next = tabs[0];
    else if (event.key === "End") next = tabs.at(-1);
    if (!next) return;
    event.preventDefault();
    next.focus();
    next.click();
  });
  box.append(tablist, reasons, ...panels);
  fillToolsPanel(panels[0], end);
  fillResources(panels[1], end);
  fillPrompts(panels[2], end);
  if (tabReason(store.tab, end)) store.tab = "tools";
  function selectTab() {
    for (const [i, tab] of tabs.entries()) {
      const on = tab.dataset.tab === store.tab;
      tab.setAttribute("aria-selected", String(on));
      tab.tabIndex = on ? 0 : -1;
      panels[i].hidden = !on;
    }
  }
  selectTab();
  function fillToolsPanel(panel, connect) {
    panel.append(whoChooses("model", t("mcp.choosers.tool_note")));
    if (!connect.tools?.length) { // not listed, failed, or an empty list: no form
      const failed = (connect.list_errors || []).find((e) => e.method === "tools/list");
      panel.append(sentence("mcp-note", failed ? t("mcp.lists.failed_tools", { reason: failed.error_text }) : t("mcp.lists.none_tools")));
      return;
    }
    const mode = segmented("mcp-call-mode", t("mcp.call.who"), [["hand", t("mcp.call.hand")], ["model", t("mcp.call.model")]],
      () => store.mode, (value) => {
        store.mode = value;
        updateCommands();
      }, (value) => (value === "model" ? byModelReason() : null));
    mode.dataset.role = "mode";
    const reason = sentence("mcp-note mcp-reason-line", "");
    reason.id = "mcp-by-model-reason";
    const hand = el("form", "mcp-form");
    hand.id = "mcp-call-form";
    hand.append(sentence("mcp-note", text("by_hand_text")), sentence("mcp-note", text("call_help_text")));
    const toolField = field(t("mcp.call.tool"), select("mcp-call-tool", connect.tools.map((tool) => [tool.tool, tool.name])));
    const presetField = field(t("mcp.call.preset"), select("mcp-call-preset", []));
    const fields = el("div", "mcp-fields");
    fields.id = "mcp-call-fields";
    const run = el("button", "mcp-button-primary", t("mcp.call.run"));
    run.type = "submit";
    run.id = "mcp-call-run";
    hand.append(toolField, presetField, fields, run);
    const byModel = el("form", "mcp-form");
    byModel.id = "mcp-ask-form";
    const question = el("textarea", "mcp-input");
    question.id = "mcp-ask-question";
    question.rows = 2;
    question.maxLength = 4000;
    question.value = t("mcp.call.default_question");
    const send = el("button", "mcp-button-primary", t("mcp.ask.send"));
    send.type = "submit";
    send.id = "mcp-ask-send";
    const modelLine = sentence("mcp-note mcp-model-line", "");
    modelLine.id = "mcp-ask-model";
    byModel.append(sentence("mcp-note", text("by_model_text")), field(t("mcp.ask.question"), question), send, modelLine);
    panel.append(mode, reason, hand, byModel);
    $("mcp-call-tool")?.addEventListener("change", () => renderCallFields(connect));
    $("mcp-call-preset")?.addEventListener("change", () => applyPreset(connect));
    hand.addEventListener("submit", (event) => {
      event.preventDefault();
      callTool(connect);
    });
    byModel.addEventListener("submit", (event) => {
      event.preventDefault();
      ask({ question: question.value });
    });
    renderCallFields(connect);
  }
  function fillResources(panel, connect) {
    panel.append(whoChooses("app", text("primitives.resources.note_text")));
    if (!connect.primitives?.resources) return;
    if (!connect.resources) {
      const failed = (connect.list_errors || []).find((e) => e.method === "resources/list");
      panel.append(sentence("mcp-note", t("mcp.lists.failed_resources", { reason: failed?.error_text ?? "" })));
      return;
    }
    if (!connect.resources.length) {
      panel.append(sentence("mcp-note", t("mcp.lists.none_resources")));
      return;
    }
    const group = el("fieldset", "mcp-resource-set");
    group.append(el("legend", "mcp-legend", t("mcp.read.legend")));
    connect.resources.forEach((resource, i) => {
      const label = el("label", "mcp-resource");
      const radio = el("input");
      radio.type = "radio";
      radio.name = "mcp-resource";
      radio.value = resource.uri;
      radio.checked = i === 0;
      const uri = el("code", "mcp-code", resource.uri);
      uri.lang = "en";
      label.append(radio, uri, el("span", "mcp-note", [resource.title || resource.name, resource.mime_type].filter(Boolean).join(" · ")));
      group.append(label);
    });
    const read = el("button", "mcp-button-secondary", t("mcp.read.run"));
    read.type = "button";
    read.id = "mcp-read";
    read.addEventListener("click", () => {
      if (read.getAttribute("aria-disabled") === "true") return;
      const uri = panel.querySelector('input[name="mcp-resource"]:checked')?.value;
      if (uri) exchange("/api/intentions/mcp_lab_read", { server: connect.server, uri });
    });
    const question = el("input", "mcp-input");
    question.id = "mcp-read-question";
    question.value = t("mcp.read.default_question");
    const send = el("button", "mcp-button-primary", t("mcp.ask.send"));
    send.type = "button";
    send.id = "mcp-read-send";
    send.addEventListener("click", () => {
      if (send.getAttribute("aria-disabled") === "true") return;
      ask({ question: question.value, of: lastOk("read")?.key });
    });
    const line = sentence("mcp-note mcp-model-line", "");
    line.id = "mcp-read-model";
    panel.append(group, read, field(t("mcp.read.question"), question), send, line);
  }
  function fillPrompts(panel, connect) {
    panel.append(whoChooses("user", text("primitives.prompts.note_text")));
    if (!connect.primitives?.prompts) return;
    if (!connect.prompts) {
      const failed = (connect.list_errors || []).find((e) => e.method === "prompts/list");
      panel.append(sentence("mcp-note", t("mcp.lists.failed_prompts", { reason: failed?.error_text ?? "" })));
      return;
    }
    if (!connect.prompts.length) {
      panel.append(sentence("mcp-note", t("mcp.lists.none_prompts")));
      return;
    }
    const chooser = select("mcp-prompt", connect.prompts.map((p) => [p.name, p.title ? `${p.name} · ${p.title}` : p.name]));
    const fields = el("div", "mcp-fields");
    fields.id = "mcp-prompt-fields";
    const renderArgs = () => {
      fields.replaceChildren();
      const prompt = connect.prompts.find((p) => p.name === chooser.value);
      for (const argument of prompt?.arguments ?? []) {
        const input = el("input", "mcp-input");
        input.name = argument.name;
        input.required = Boolean(argument.required);
        if (argument.name === "term") input.value = t("mcp.prompt.default_term");
        const label = argument.required ? t("mcp.prompt.required", { name: argument.name }) : argument.name;
        const wrap = field(label, input);
        if (argument.description) wrap.append(sentence("mcp-note", argument.description));
        fields.append(wrap);
      }
    };
    chooser.addEventListener("change", renderArgs);
    renderArgs();
    const get = el("button", "mcp-button-secondary", t("mcp.prompt.run"));
    get.type = "button";
    get.id = "mcp-prompt-get";
    get.addEventListener("click", () => {
      if (get.getAttribute("aria-disabled") === "true") return;
      const args = {};
      for (const input of fields.querySelectorAll("input")) if (input.value.trim()) args[input.name] = input.value.trim();
      exchange("/api/intentions/mcp_lab_prompt", { server: connect.server, prompt: chooser.value, arguments: args });
    });
    const send = el("button", "mcp-button-primary", t("mcp.ask.send"));
    send.type = "button";
    send.id = "mcp-prompt-send";
    send.addEventListener("click", () => {
      if (send.getAttribute("aria-disabled") === "true") return;
      ask({ of: lastOk("prompt")?.key });
    });
    const line = sentence("mcp-note mcp-model-line", "");
    line.id = "mcp-prompt-model";
    panel.append(field(t("mcp.prompt.name"), chooser), fields, get, send, line);
  }
}

function whoChooses(kind, note) {
  const box = el("div", "mcp-who");
  box.append(chooserBadge(kind), el("span", "mcp-note", note));
  return box;
}

function field(label, control) {
  const wrap = el("label", "mcp-field");
  wrap.append(el("span", "mcp-field-label", label), control);
  return wrap;
}

function select(id, options) {
  const node = el("select", "mcp-input");
  node.id = id;
  for (const [value, label] of options) node.append(new Option(label, value));
  return node;
}

function byModelReason() {
  const ask = store.ask;
  if (!ask?.model_ready) return ask?.model_reason_text || t("mcp.ask.no_model");
  if (!ask.tools) return ask.tools_reason_text || t("mcp.ask.no_tools");
  return null;
}

function modelLine() {
  const model = store.ask?.model;
  if (!model) return "";
  if (model.hosting === "network") return t("mcp.ask.cloud_line", { model: model.label, provider: model.provider ?? "" });
  return t("mcp.ask.local_line", { model: model.label });
}

function updateCommands() {
  const busy = idle() ? null : busyReason();
  const open = connection();
  const mode = $("mcp-call-mode");
  mode?.update();
  const byModel = store.mode === "model";
  const reasonLine = $("mcp-by-model-reason");
  if (reasonLine) {
    const reason = byModelReason();
    reasonLine.textContent = reason ? t("mcp.ask.unavailable", { reason }) : "";
    reasonLine.hidden = !reason;
    mode?.querySelector('[data-value="model"]')?.setAttribute("aria-describedby", reasonLine.id);
  }
  if ($("mcp-call-form")) $("mcp-call-form").hidden = byModel;
  if ($("mcp-ask-form")) $("mcp-ask-form").hidden = !byModel;
  setAvailable($("mcp-call-run"), busy || (open ? null : t("mcp.servers.not_connected")));
  setAvailable($("mcp-ask-send"), busy || byModelReason() || (open ? null : t("mcp.servers.not_connected")));
  setAvailable($("mcp-read"), busy || (open ? null : t("mcp.servers.not_connected")));
  setAvailable($("mcp-prompt-get"), busy || (open ? null : t("mcp.servers.not_connected")));
  const ready = store.ask?.model_ready ? null : store.ask?.model_reason_text || t("mcp.ask.no_model");
  setAvailable($("mcp-read-send"), busy || ready || (lastOk("read") ? null : t("mcp.read.first")));
  setAvailable($("mcp-prompt-send"), busy || ready || (lastOk("prompt") ? null : t("mcp.prompt.first")));
  for (const id of ["mcp-ask-model", "mcp-read-model", "mcp-prompt-model"]) {
    const line = $(id);
    if (line) line.textContent = modelLine();
  }
}

function selectedTool(connect) {
  const name = $("mcp-call-tool")?.value;
  return connect.tools?.find((tool) => tool.tool === name) ?? null;
}

function renderCallFields(connect) {
  const tool = selectedTool(connect);
  const fields = $("mcp-call-fields");
  if (!fields) return;
  fields.replaceChildren();
  const preset = $("mcp-call-preset");
  preset.replaceChildren(new Option(t("mcp.call.preset_none"), ""));
  (store.presets[tool?.name] || []).forEach((entry, i) => preset.append(new Option(entry.label_text, String(i))));
  const properties = tool?.schema?.properties || {};
  const required = new Set(tool?.schema?.required || []);
  if (!Object.keys(properties).length) {
    fields.append(sentence("mcp-note", t("mcp.call.no_params")));
    return;
  }
  for (const [name, schema] of Object.entries(properties)) {
    const type = schema?.type;
    let input;
    let kind;
    if (type === "boolean") {
      input = el("input");
      input.type = "checkbox";
      kind = "boolean";
    } else if (type === "integer" || type === "number") {
      input = el("input", "mcp-input");
      input.type = "number";
      kind = "number";
    } else if (type === "string") {
      input = el("input", "mcp-input");
      input.type = "text";
      kind = "text";
    } else {
      input = el("textarea", "mcp-input");
      input.rows = 2;
      kind = "json";
    }
    input.name = name;
    input.dataset.kind = kind;
    const label = [name, required.has(name) ? t("mcp.call.required") : null, kind === "json" ? t("mcp.call.json") : null].filter(Boolean).join(" · ");
    const wrap = field(label, input);
    if (schema?.description) wrap.append(sentence("mcp-note", schema.description));
    fields.append(wrap);
  }
}

function applyPreset(connect) {
  const tool = selectedTool(connect);
  const index = $("mcp-call-preset").value;
  const preset = index === "" ? null : (store.presets[tool?.name] || [])[Number(index)];
  if (!preset) return;
  for (const input of $("mcp-call-fields").querySelectorAll("[data-kind]")) {
    const value = preset.args[input.name];
    if (value === undefined) continue;
    if (input.dataset.kind === "boolean") input.checked = Boolean(value);
    else input.value = typeof value === "string" ? value : JSON.stringify(value);
  }
}

function callArguments(connect) {
  const tool = selectedTool(connect);
  const required = new Set(tool?.schema?.required || []);
  const args = {};
  for (const input of $("mcp-call-fields").querySelectorAll("[data-kind]")) {
    const name = input.name;
    const kind = input.dataset.kind;
    if (kind === "boolean") {
      args[name] = input.checked;
      continue;
    }
    const raw = input.value.trim();
    if (!raw) {
      if (required.has(name)) return { error: t("mcp.call.missing", { name }) };
      continue;
    }
    if (kind === "number") {
      const value = Number(raw);
      if (!Number.isFinite(value)) return { error: t("mcp.call.invalid_number", { name }) };
      args[name] = value;
    } else if (kind === "json") {
      try {
        args[name] = JSON.parse(raw);
      } catch {
        return { error: t("mcp.call.invalid_json", { name }) };
      }
    } else {
      args[name] = raw;
    }
  }
  return { args };
}

// ---------- gestures ----------

function commandStatus(value, error = false) {
  const status = $("mcp-command-status");
  status.textContent = value || "";
  status.classList.toggle("is-error", error);
}

async function exchange(path, body) {
  if (store.pending) return;
  commandStatus("");
  store.pending = true;
  renderControls();
  const answer = await post(path, body);
  store.pending = false;
  if (!answer.ok) commandStatus(refusalText(answer), true);
  else if (stepper && !stepper.live) stepper.follow(); // a new exchange goes back to live
  renderControls();
}

function callTool(connect) {
  if ($("mcp-call-run").getAttribute("aria-disabled") === "true") return;
  const tool = selectedTool(connect);
  if (!tool) return; // no tool listed, or none chosen: nothing to call
  const { args, error } = callArguments(connect);
  if (error) {
    commandStatus(error, true);
    return;
  }
  exchange("/api/intentions/mcp_lab_call", { server: connect.server, tool: tool.tool, arguments: args });
}

function ask({ question = null, of = null }) {
  const open = connection();
  if (!open) return;
  const body = { server: open.server, doc_mode: store.docMode };
  if (question !== null && question.trim()) body.question = question.trim();
  if (of) body.of = of;
  exchange("/api/intentions/mcp_lab_ask", body);
}

function connect() {
  if ($("mcp-connect").getAttribute("aria-disabled") === "true") return;
  store.failures.delete(store.selected);
  exchange("/api/intentions/mcp_lab_connect", { server: store.selected });
}

async function stop() {
  if ($("mcp-stop").getAttribute("aria-disabled") === "true") return;
  await post("/api/intentions/stop", {});
}

// ---------- the projection of the stream ----------

function say(value) {
  $("mcp-status").textContent = value;
}

function alertOnce(key, value) {
  if (store.announced.has(key) || !value) return;
  store.announced.add(key);
  $("mcp-alert").textContent = value;
}

// The phases ended and the failures since the last draw, said once each (live only).
function announce(model) {
  for (const phase of model.phases) {
    if (!phase.end || store.announced.has(phase.key)) continue;
    store.announced.add(phase.key);
    if (!store.restoring) say(t("mcp.a11y.phase_done", { title: phaseTitle(phase), summary: phaseSummary(phase) }));
  }
  for (const arrow of model.arrows) {
    if (!(arrow.error || arrow.isError)) continue;
    // At a reload, a past failure is marked said: the first live envelope never repeats it.
    if (store.restoring) {
      store.announced.add(`alert:${arrow.key}`);
      continue;
    }
    alertOnce(`alert:${arrow.key}`, t("mcp.a11y.failure", { label: arrowLabel(arrow), reason: arrow.error || "isError" }));
  }
}

function rememberFailures(model) {
  const end = model.connect;
  if (end && end.status === "error" && end.error_kind !== "stopped") {
    store.failures.set(end.server, end.error_text || t(`mcp.error_kinds.${end.error_kind}`));
  }
}

// Draws the series again from its envelopes: the same code live and at a reload.
function redraw({ restoring = false } = {}) {
  const before = store.model?.arrows.filter((a) => a.step).length ?? 0;
  const model = frames(store.envelopes);
  store.model = model;
  store.restoring = restoring;
  rememberFailures(model);
  // Each end says the connection's state (AD-27): the page follows it.
  for (const envelope of store.envelopes) {
    const p = envelope.payload || {};
    if (envelope.kind.endsWith("_ended") && envelope.kind.startsWith("mcp_lab_") && p.connection && !envelope.step_id.includes(".")) {
      store.openServer = p.connection === "open" ? p.server : null;
    }
    if (envelope.kind === "mcp_lab_closed") store.openServer = null;
  }
  renderHeads();
  renderSequence(model, { restoring });
  renderModelPane(model);
  const stepArrows = model.arrows.filter((a) => a.step);
  if (restoring) {
    stepper.load(stepArrows);
  } else if (stepArrows.length > before) {
    for (const arrow of stepArrows.slice(before)) stepper.push(arrow);
    if (!stepper.live) onShow(current, shownIndex);
  } else {
    stepper.refresh();
    if (stepper.frames.length === 0) onShow(null, -1);
  }
  announce(model);
  store.restoring = false;
  renderControls();
}

function newSeries(first) {
  store.first = first;
  store.envelopes = [];
  store.model = null;
  clearSequence();
  stepper.clear();
}

function applyEnvelope(envelope) {
  if (envelope.kind === "session_state") {
    store.session = envelope.payload;
    return "controls";
  }
  if (envelope.kind === "model_load_ended") return "state";
  // The reset (AD-27): the session closed the workshop's connection and forgot its series
  // (`first` back to zero), as a reload would show it. The session emits `harness_reset`.
  if (envelope.kind === "harness_reset") {
    newSeries(0);
    store.openServer = null;
    return "redraw";
  }
  if (envelope.context_id !== "mcp_lab" || !KINDS.has(envelope.kind)) return null;
  const n = stepNumber(envelope.step_id);
  if (n === null) return null;
  const opens = envelope.kind === "mcp_lab_exchange_started" && envelope.payload.exchange === "connect" && !envelope.step_id.includes(".");
  if (opens && n >= store.first) newSeries(n);
  if (n < store.first || !store.first) return null;
  store.envelopes.push(envelope);
  return "redraw";
}

let scheduled = null;
function schedule(what) {
  if (!what) return;
  const rank = { controls: 1, redraw: 2, state: 3 };
  if (scheduled && rank[scheduled] >= rank[what]) return;
  const first = !scheduled;
  scheduled = what;
  if (!first) return;
  requestAnimationFrame(async () => {
    const todo = scheduled;
    scheduled = null;
    if (todo === "state") await refreshAsk();
    if (todo === "redraw" || todo === "state") redraw();
    else renderControls();
  });
}

// SSE read by hand, as rag.js: the server names each event after its `kind`.
async function streamEvents() {
  for (;;) {
    try {
      const response = await fetch("/api/stream", {
        headers: store.lastSeq ? { "Last-Event-ID": String(store.lastSeq) } : {},
      });
      const reader = response.body.getReader();
      const decoder = new TextDecoder();
      let buffer = "";
      for (;;) {
        const { value, done } = await reader.read();
        if (done) break;
        buffer += decoder.decode(value, { stream: true });
        let sep;
        while ((sep = buffer.indexOf("\n\n")) !== -1) {
          const raw = buffer.slice(0, sep);
          buffer = buffer.slice(sep + 2);
          const { event, data } = parseSseEvent(raw);
          if (!data) continue;
          if (event === "server_instance") {
            if (store.serverInstance === null) store.serverInstance = data.instance_id;
            else if (data.instance_id !== store.serverInstance) {
              location.reload();
              return;
            }
          } else if (data.seq > store.lastSeq) {
            store.lastSeq = data.seq;
            schedule(applyEnvelope(data));
          }
        }
      }
    } catch {
      // reconnection below resumes at lastSeq
    }
    await new Promise((resolve) => setTimeout(resolve, 1000));
  }
}

function parseSseEvent(raw) {
  let event = null;
  let data = null;
  for (const line of raw.split("\n")) {
    if (line.startsWith("event:")) event = line.slice(6).trim();
    else if (line.startsWith("data:")) data = line.slice(5).trim();
  }
  if (!data) return { event, data: null };
  try {
    return { event, data: JSON.parse(data) };
  } catch {
    return { event, data: null };
  }
}

async function fetchState() {
  const response = await fetch("/api/mcp_lab");
  if (!response.ok) throw new Error(`HTTP ${response.status}`);
  return response.json();
}

// AD-27: the availability of the model, read again after each `model_load_ended`.
async function refreshAsk() {
  try {
    const body = await fetchState();
    store.ask = body.ask;
    store.session = body.session_state;
    buildArch();
  } catch {
    // the next event tries again
  }
}

function renderContent() {
  for (const node of document.querySelectorAll("[data-text]")) {
    const value = text(node.dataset.text);
    if (value) node.textContent = value;
  }
}

async function refresh() {
  let body;
  try {
    body = await fetchState();
  } catch (error) {
    const alert = $("mcp-content-error");
    alert.hidden = false;
    alert.textContent = t("mcp.unavailable", { cause: error.message });
    return null;
  }
  store.content = body.content;
  store.servers = body.servers;
  store.presets = body.call_presets || {};
  store.openServer = body.open_server;
  store.session = body.session_state;
  store.ask = body.ask;
  if (body.open_server) store.selected = body.open_server;
  const alert = $("mcp-content-error");
  alert.hidden = !body.content_error_text;
  alert.textContent = body.content_error_text || "";
  renderContent();
  buildArch();
  buildBefore();
  // The last connection, rebuilt from its envelopes (AD-27): the same code as the stream's.
  const first = stepNumber(body.last_session[0]?.step_id) ?? 0;
  newSeries(first);
  for (const envelope of body.last_session) {
    const n = stepNumber(envelope.step_id);
    if (n !== null && n >= first) store.envelopes.push(envelope);
  }
  if (!store.envelopes.length && first) store.first = first;
  if (store.model === null && store.envelopes[0]) {
    const server = store.envelopes[0].payload?.server;
    if (server && !body.open_server) store.selected = server;
  }
  store.lastSeq = body.seq;
  for (const phase of frames(store.envelopes).phases) store.announced.add(phase.key);
  redraw({ restoring: true });
  store.openServer = body.open_server; // the session's word on the connection, after the replay
  renderControls();
  return body;
}

function startPanes() {
  const labels = {
    servers: t("mcp.panes.servers"),
    seq: t("mcp.panes.seq"),
    model: t("mcp.panes.model"),
    arch: t("mcp.panes.arch"),
  };
  panes = createPanes({
    panes: ["servers", "seq", "model", "arch"],
    labels,
    storageKey: PANES_KEY,
    layout: $("layout"),
    left: "servers",
    row: ["seq", "model"],
    bottom: "arch",
    pinned: ["seq"],
    chips: $("mcp-pane-chips"),
    onChange: () => {
      panes.render();
      layer?.schedule();
    },
  });
  panes.load();
  panes.start();
}

function startSequence() {
  stepper = createStepper($("mcp-stepper"), {
    onShow,
    describe: describeStep,
    onLive: (live) => {
      if (live) {
        suspended = false;
        unseen = 0;
        renderNewChip();
      }
      layer?.schedule();
    },
  });
  const body = $("mcp-seq-body");
  const leave = () => {
    if (programmatic) return;
    suspended = true;
  };
  body.addEventListener("wheel", leave, { passive: true });
  body.addEventListener("touchmove", leave, { passive: true });
  body.addEventListener("scroll", () => {
    if (!programmatic && document.activeElement?.closest?.("#mcp-seq-body")) suspended = true;
  });
  $("mcp-seq").addEventListener("keydown", onSequenceKey);
  $("mcp-new-messages").addEventListener("click", () => {
    suspended = false;
    unseen = 0;
    renderNewChip();
    const entry = current ? rows.get(current.key) : null;
    entry?.li.scrollIntoView({ block: "nearest" });
  });
  // The chronometer of a call to the model waiting for its answer (AD-1: anchored on its `ts`).
  setInterval(() => {
    for (const chrono of document.querySelectorAll(".mcp-chrono")) {
      const since = Date.parse(chrono.dataset.since);
      if (Number.isFinite(since)) chrono.textContent = duration(Math.max(0, Date.now() - since));
    }
  }, 500);
}

async function main() {
  await textsReady; // the page's texts and formats in the session's language
  initProjection({ toggle: $("projection-toggle"), onChange: () => layer?.schedule() });
  startPanes();
  startSequence();
  let view = "after";
  try {
    view = localStorage.getItem(ARCH_KEY) || "after";
  } catch {
    // No storage: « Avec MCP ».
  }
  let body = await refresh();
  while (!body) {
    await new Promise((resolve) => setTimeout(resolve, 2000));
    body = await refresh();
  }
  setArchView(view, false);
  for (const button of $("mcp-arch-switch").querySelectorAll("[role=radio]")) {
    button.addEventListener("click", () => setArchView(button.dataset.view));
  }
  $("mcp-arch-switch").addEventListener("keydown", (event) => {
    if (!["ArrowLeft", "ArrowRight", "ArrowUp", "ArrowDown"].includes(event.key)) return;
    event.preventDefault();
    setArchView(store.archView === "before" ? "after" : "before");
    $("mcp-arch-switch").querySelector('[aria-checked="true"]').focus();
  });
  $("mcp-connect").addEventListener("click", connect);
  $("mcp-stop").addEventListener("click", stop);
  document.body.dataset.mcpReady = "true";
  streamEvents();
}

main();
