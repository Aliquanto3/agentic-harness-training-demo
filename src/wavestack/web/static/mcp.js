// Story 6 (corrections of 2026-09-30): the MCP workshop. Everything it shows comes from
// `GET /api/mcp_lab` or from an event of the journal in the context `mcp_lab` (AD-1): the
// servers, the JSON-RPC messages as they passed the transport, the tools and their weight in
// the context, the call's raw answer and the text the harness would reinject are built in
// Python. The page lays them out; it only turns the form's fields into the call's arguments.
//
// Its own texts come from `content/ui.yaml` (section `mcp`) through `t()`; its pedagogical
// texts from `content/mcp_lab.yaml`, read in the session's language by `GET /api/mcp_lab`.
// The tools' descriptions are the servers' own, never translated.

import { numberFormat, ready as textsReady, t } from "./i18n.js";

const $ = (id) => document.getElementById(id);

const store = {
  content: null,
  servers: [],
  presets: {},
  openServer: null, // the server the workshop's connection is open to (`open_server`)
  session: { state: "diagnostic", reason_text: null },
  serverInstance: null,
  lastSeq: 0,
  pending: false, // a POST sent, not answered yet
  connectStep: 0, // the number of the last connection's exchange (`mcp{n}`)
  steps: new Map(), // step number -> {messages, outbound, ended}
};

// ---------- small helpers ----------

function el(tag, className, text) {
  const node = document.createElement(tag);
  if (className) node.className = className;
  if (text !== undefined && text !== null) node.textContent = text;
  return node;
}

function code(text, className = "mcp-code") {
  return el("code", className, text);
}

// A text of content/mcp_lab.yaml by its dotted path, `{name}` replaced by `values[name]`.
function text(path, values = {}) {
  let value = store.content;
  for (const key of path.split(".")) value = value?.[key];
  if (typeof value !== "string") return "";
  return value.replace(/\{(\w+)\}/g, (_, name) => String(values[name] ?? ""));
}

const fmtInt = (n) => (typeof n === "number" ? numberFormat().format(n) : "—");

// A JSON text, indented for reading; anything else as it is.
function pretty(value) {
  if (typeof value !== "string") return JSON.stringify(value, null, 2);
  try {
    return JSON.stringify(JSON.parse(value), null, 2);
  } catch {
    return value;
  }
}

function jsonBlock(value, label) {
  const pre = el("pre", "mcp-json");
  pre.tabIndex = 0; // scrollable by the keyboard
  if (label) pre.setAttribute("aria-label", label);
  pre.textContent = pretty(value);
  return pre;
}

function stepNumber(stepId) {
  const match = /^mcp(\d+)$/.exec(stepId || "");
  return match ? Number(match[1]) : null;
}

function serverInfo(id) {
  return store.servers.find((s) => s.id === id) ?? null;
}

const serverLabel = (id) => serverInfo(id)?.label_text ?? id;

function tokensText(n, estimated) {
  if (typeof n !== "number") return "—";
  const tokens = t("mcp.tokens", { count: n });
  return estimated ? `${tokens} (${t("mcp.estimated")})` : tokens;
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

// ---------- the projection of the journal ----------

function step(n) {
  if (!store.steps.has(n)) store.steps.set(n, { messages: [], outbound: [], ended: null });
  return store.steps.get(n);
}

// A new connection: the exchanges of the former one are forgotten.
function startConnection(n) {
  if (n < store.connectStep) return false;
  if (n > store.connectStep) {
    store.connectStep = n;
    store.steps = new Map();
  }
  return true;
}

function connection() {
  return store.connectStep ? store.steps.get(store.connectStep) ?? null : null;
}

function connectEnded() {
  return connection()?.ended ?? null;
}

// The last call made on the connection, if any.
function lastCall() {
  const numbers = [...store.steps.keys()].filter((n) => n > store.connectStep);
  return numbers.length ? store.steps.get(Math.max(...numbers)) : null;
}

function applyEnvelope(envelope) {
  store.lastSeq = Math.max(store.lastSeq, envelope.seq);
  const p = envelope.payload;
  if (envelope.kind === "session_state") {
    const wasBusy = store.session.state === "mcp_lab";
    store.session = { state: p.state, reason_text: p.reason_text };
    if (wasBusy && p.state !== "mcp_lab") refreshOpenServer();
    renderBusy();
    return false;
  }
  if (envelope.context_id !== "mcp_lab") return false;
  const n = stepNumber(envelope.step_id);
  if (n === null) return false;
  switch (envelope.kind) {
    case "mcp_lab_message":
      // A handshake's first message opens a new connection (another tab's included).
      if (p.method === "initialize" && p.direction === "to_server") startConnection(n);
      if (n < store.connectStep) return false;
      step(n).messages.push({ ...p, seq: envelope.seq });
      return true;
    case "outbound_request":
      if (n < store.connectStep) return false;
      step(n).outbound.push({ ...p, seq: envelope.seq });
      return true;
    case "mcp_lab_connect_ended":
      // A connection that failed before any message has only its end.
      if (!startConnection(n)) return false;
      step(n).ended = p;
      return true;
    case "mcp_lab_call_ended":
      if (n <= store.connectStep) return false;
      step(n).ended = p;
      return true;
    default:
      return false;
  }
}

// ---------- section 1: the servers ----------

function renderServers() {
  const list = $("mcp-servers");
  list.replaceChildren();
  const busy = Boolean(busyReason()) || store.pending;
  for (const server of store.servers) {
    const item = el("li", "mcp-server");
    item.dataset.server = server.id;
    if (server.network) item.classList.add("is-network");
    const head = el("div", "mcp-server-head");
    head.append(el("h3", "mcp-server-name", server.label_text));
    if (store.openServer === server.id) head.append(el("span", "mcp-badge mcp-badge-open", t("mcp.connected")));
    item.append(head);
    const facts = el("dl", "mcp-facts");
    const transport = store.content?.transports?.[server.transport];
    const fact = (label, value) => {
      facts.append(el("dt", null, label));
      const dd = el("dd");
      dd.append(value);
      facts.append(dd);
    };
    fact(t("mcp.transport"), el("span", null, transport?.label_text ?? server.transport));
    if (server.url) fact(t("mcp.address"), code(server.url));
    if (server.command) fact(t("mcp.command"), code(server.command));
    fact(t("mcp.sends"), el("span", null, server.network ? server.sends_text || "—" : t("mcp.nothing_leaves")));
    item.append(facts);
    if (transport?.explain_text) item.append(el("p", "mcp-note", transport.explain_text));
    const connect = el("button", "mcp-button-primary", t("mcp.connect"));
    connect.type = "button";
    connect.dataset.connect = server.id;
    connect.disabled = busy || !store.content;
    connect.title = busyReason() || "";
    connect.addEventListener("click", () => connectTo(server.id));
    item.append(connect);
    list.append(item);
  }
}

// ---------- section 2: the handshake ----------

function messageItem(message) {
  const item = el("li", `mcp-message is-${message.direction}`);
  item.dataset.method = message.method || "";
  item.dataset.direction = message.direction;
  const head = el("div", "mcp-message-head");
  const arrow = el("span", "mcp-direction", t(message.direction === "to_server" ? "mcp.to_server" : "mcp.from_server"));
  head.append(arrow);
  if (message.method) head.append(code(message.method, "mcp-method"));
  const timing =
    message.direction === "from_server"
      ? t("mcp.round_trip", { ms: message.elapsed_ms })
      : t("mcp.since_start", { ms: message.elapsed_ms });
  head.append(el("span", "mcp-timing", timing));
  const origin = el("span", "mcp-tag", message.reconstructed ? t("mcp.reconstructed") : t("mcp.captured"));
  if (message.reconstructed) origin.classList.add("is-reconstructed");
  head.append(origin);
  item.append(head);
  const explain = message.direction === "to_server" ? text(`methods.${message.method}`) : "";
  if (explain) item.append(el("p", "mcp-note", explain));
  item.append(jsonBlock(message.jsonrpc));
  return item;
}

function outboundItem(request) {
  const item = el("li", "mcp-message mcp-outbound");
  item.dataset.direction = "outbound";
  const head = el("div", "mcp-message-head");
  head.append(el("span", "mcp-direction", t("mcp.outbound")), code(`${request.method} ${request.url}`, "mcp-method"));
  item.append(head);
  const headers = el("dl", "mcp-headers");
  for (const header of request.headers || []) {
    headers.append(el("dt", null, header.name), el("dd", header.masked ? "is-masked" : null, header.value));
  }
  const details = el("details", "mcp-details");
  details.append(el("summary", null, t("mcp.headers")), headers);
  item.append(details);
  if (request.body) {
    item.append(el("p", "mcp-label", t("mcp.body")), jsonBlock(request.body));
  }
  return item;
}

// The messages of an exchange and its outbound requests, in the journal's order (`seq`):
// each message as the session wrote or read it, each HTTP request (POST, the stream's GET,
// the closing DELETE) as it left.
function exchangeItems(exchange) {
  const entries = [
    ...exchange.messages.map((message) => [message.seq, () => messageItem(message)]),
    ...exchange.outbound.map((request) => [request.seq, () => outboundItem(request)]),
  ];
  return entries.sort((a, b) => a[0] - b[0]).map(([, item]) => item());
}

function renderHandshake() {
  const exchange = connection();
  const list = $("mcp-messages");
  list.replaceChildren(...(exchange ? exchangeItems(exchange) : []));
  $("mcp-handshake-empty").hidden = Boolean(exchange);
  const summary = $("mcp-connect-summary");
  const ended = exchange?.ended;
  summary.hidden = !ended && !exchange;
  summary.classList.toggle("is-error", ended?.status === "error");
  summary.dataset.status = ended?.status ?? "running";
  if (!exchange) {
    summary.textContent = "";
  } else if (!ended) {
    summary.textContent = t("mcp.connecting");
  } else {
    const server = serverLabel(ended.server);
    summary.textContent =
      ended.status === "ok"
        ? `${t("mcp.connect_ok", { server, ms: ended.duration_ms })} · ${t("mcp.tools_count", { count: ended.tools.length })}`
        : t("mcp.connect_error", { server, ms: ended.duration_ms, reason: ended.error_text || "" });
  }
}

// ---------- section 3: the tools' documentation and their weight ----------

function renderTools() {
  const ended = connectEnded();
  const ok = ended?.status === "ok";
  const tools = ok ? ended.tools : [];
  $("mcp-tools-empty").hidden = tools.length > 0;
  const box = $("mcp-tools");
  box.replaceChildren();
  const network = serverInfo(ended?.server)?.network;
  for (const tool of tools) {
    const card = el("article", "mcp-tool");
    card.dataset.tool = tool.name;
    const facts = el("dl", "mcp-facts");
    facts.append(el("dt", null, t("mcp.exposed_name")));
    const name = el("dd");
    name.append(code(tool.name));
    facts.append(name, el("dt", null, t("mcp.description")));
    const description = el("dd", "mcp-description", tool.description || "—");
    facts.append(description);
    card.append(facts);
    if (network) card.append(el("p", "mcp-note mcp-served", t("mcp.served_untranslated")));
    const details = el("details", "mcp-details");
    details.append(el("summary", null, t("mcp.schema")), jsonBlock(tool.schema, t("mcp.schema")));
    card.append(details);
    box.append(card);
  }
  const weights = $("mcp-weights");
  weights.hidden = !ok;
  const rows = $("mcp-weight-rows");
  rows.replaceChildren();
  if (!ok) return;
  const row = (label, full, lazy, className) => {
    const tr = el("tr", className);
    const th = el("th");
    th.scope = "row";
    th.append(label);
    tr.append(th, el("td", "mcp-number", full), el("td", "mcp-number", lazy));
    rows.append(tr);
    return tr;
  };
  for (const tool of tools) {
    row(code(tool.name), fmtInt(tool.doc_tokens), fmtInt(tool.line_tokens)).dataset.tool = tool.name;
  }
  if (typeof ended.load_tool_doc_tokens === "number") {
    row(el("span", null, t("mcp.weight_load_tool_doc")), "—", fmtInt(ended.load_tool_doc_tokens));
  }
  const total = row(
    el("span", null, t("mcp.weight_total")),
    tokensText(ended.full_tokens, false),
    tokensText(ended.lazy_tokens, false),
    "mcp-total"
  );
  total.dataset.full = String(ended.full_tokens ?? "");
  total.dataset.lazy = String(ended.lazy_tokens ?? "");
  $("mcp-weight-source").textContent = ended.estimated ? t("mcp.estimated") : t("mcp.counted");
}

// ---------- section 4: the call ----------

function callableTools() {
  const ended = connectEnded();
  if (ended?.status !== "ok" || store.openServer !== ended.server) return [];
  return ended.tools;
}

function selectedTool() {
  const name = $("mcp-call-tool").value;
  return callableTools().find((tool) => tool.name === name) ?? null;
}

// A field per parameter of the schema: text, number, boolean; anything else, a JSON value.
function fieldKind(prop) {
  const type = prop && typeof prop === "object" ? prop.type : undefined;
  if (type === "string") return "text";
  if (type === "number" || type === "integer") return "number";
  if (type === "boolean") return "boolean";
  return "json";
}

function renderCallForm() {
  const tools = callableTools();
  const form = $("mcp-call-form");
  form.hidden = tools.length === 0;
  $("mcp-call-empty").hidden = tools.length > 0;
  if (!tools.length) return;
  const picker = $("mcp-call-tool");
  const kept = picker.value;
  const names = tools.map((tool) => tool.name);
  if ([...picker.options].map((o) => o.value).join("|") !== names.join("|")) {
    picker.replaceChildren(...tools.map((tool) => {
      const option = el("option", null, tool.name);
      option.value = tool.name;
      return option;
    }));
    picker.value = names.includes(kept) ? kept : names[0];
    renderFields();
  }
  renderCallBusy();
}

function renderFields() {
  const tool = selectedTool();
  const presets = $("mcp-call-preset");
  const offered = tool ? store.presets[tool.name] ?? [] : [];
  const none = el("option", null, t("mcp.call_preset_none"));
  none.value = "";
  presets.replaceChildren(none, ...offered.map((preset, index) => {
    const option = el("option", null, preset.label_text);
    option.value = String(index);
    return option;
  }));
  presets.disabled = offered.length === 0;
  const box = $("mcp-call-fields");
  box.replaceChildren();
  if (!tool) return;
  const properties = tool.schema?.properties ?? {};
  const required = new Set(tool.schema?.required ?? []);
  const names = Object.keys(properties);
  if (!names.length) {
    box.append(el("p", "mcp-note", t("mcp.call_no_params")));
    return;
  }
  for (const name of names) {
    const prop = properties[name];
    const kind = fieldKind(prop);
    const label = el("label", `mcp-field is-${kind}`);
    const title = el("span", "mcp-field-name");
    title.append(code(name));
    if (required.has(name)) title.append(el("span", "mcp-required", ` ${t("mcp.call_required")}`));
    if (kind === "json") title.append(el("span", "mcp-field-kind", ` (${t("mcp.call_json")})`));
    let input;
    if (kind === "boolean") {
      input = el("input");
      input.type = "checkbox";
    } else if (kind === "json") {
      input = el("textarea");
      input.rows = 2;
    } else {
      input = el("input");
      input.type = kind === "number" ? "number" : "text";
      if (prop?.type === "integer") input.step = "1";
      else if (kind === "number") input.step = "any";
    }
    input.name = name;
    input.dataset.kind = kind;
    input.autocomplete = "off";
    label.append(title, input);
    if (prop && typeof prop.description === "string" && prop.description) {
      label.append(el("span", "mcp-field-hint", prop.description));
    }
    box.append(label);
  }
}

function applyPreset() {
  const tool = selectedTool();
  const index = $("mcp-call-preset").value;
  if (!tool || index === "") return;
  const preset = (store.presets[tool.name] ?? [])[Number(index)];
  if (!preset) return;
  for (const input of $("mcp-call-fields").querySelectorAll("[data-kind]")) {
    const value = preset.args?.[input.name];
    if (input.dataset.kind === "boolean") input.checked = Boolean(value);
    else if (value === undefined) input.value = "";
    else input.value = input.dataset.kind === "json" ? JSON.stringify(value) : String(value);
  }
}

// The arguments the fields hold, or why not (`{error}`).
function callArguments(tool) {
  const required = new Set(tool.schema?.required ?? []);
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
      if (required.has(name)) return { error: t("mcp.call_missing", { name }) };
      continue;
    }
    if (kind === "number") {
      const value = Number(raw);
      if (!Number.isFinite(value)) return { error: t("mcp.call_invalid_number", { name }) };
      args[name] = value;
    } else if (kind === "json") {
      try {
        args[name] = JSON.parse(raw);
      } catch {
        return { error: t("mcp.call_invalid_json", { name }) };
      }
    } else {
      args[name] = input.value;
    }
  }
  return { args };
}

function renderCallBusy() {
  const blocked = busyReason();
  const run = $("mcp-call-run");
  run.disabled = Boolean(blocked) || store.pending;
  run.title = blocked || "";
}

function renderCallResult() {
  const call = lastCall();
  const summary = $("mcp-call-summary");
  const box = $("mcp-call-result");
  box.replaceChildren();
  summary.hidden = !call;
  if (!call) return;
  const ended = call.ended;
  summary.dataset.status = ended?.status ?? "running";
  summary.classList.toggle("is-error", ended?.status === "error");
  if (!ended) {
    summary.textContent = t("mcp.calling");
  } else if (ended.status === "ok") {
    summary.textContent = t("mcp.call_ok", { tool: ended.tool, ms: ended.duration_ms });
  } else {
    summary.textContent = t("mcp.call_error", { tool: ended.tool, ms: ended.duration_ms, reason: ended.error_text || "" });
  }
  const request = call.messages.find((m) => m.direction === "to_server" && m.method === "tools/call");
  const block = (title, node, className) => {
    const part = el("div", `mcp-call-part ${className}`);
    part.append(el("h3", "mcp-subtitle", title), node);
    box.append(part);
  };
  for (const outbound of call.outbound) {
    const list = el("ol", "mcp-messages");
    list.append(outboundItem(outbound));
    block(t("mcp.outbound"), list, "mcp-call-outbound");
  }
  if (request) block(t("mcp.call_request"), jsonBlock(request.jsonrpc), "mcp-call-request");
  if (ended) {
    block(
      t("mcp.call_response"),
      ended.raw ? jsonBlock(ended.raw) : el("p", "mcp-note", t("mcp.call_no_raw")),
      "mcp-call-raw"
    );
    if (typeof ended.text === "string") {
      const reinjected = el("div");
      const help = text("reinjected_help_text");
      if (help) reinjected.append(el("p", "mcp-note", help));
      const pre = el("pre", "mcp-text");
      pre.tabIndex = 0;
      pre.textContent = ended.text;
      reinjected.append(pre);
      if (ended.truncated) {
        reinjected.append(
          el("p", "mcp-note", t("mcp.call_truncated", { kept: ended.truncated.tokens, total: ended.truncated.total_tokens }))
        );
      }
      block(t("mcp.call_reinjected"), reinjected, "mcp-call-text");
    }
  }
}

// ---------- section 5: what the model sees ----------

function renderContext() {
  const ended = connectEnded();
  const ok = ended?.status === "ok";
  $("mcp-context-empty").hidden = ok;
  const box = $("mcp-context");
  box.replaceChildren();
  if (!ok) return;
  const full = el("div", "mcp-context-mode");
  full.dataset.mode = "full";
  full.append(el("h3", "mcp-subtitle", t("mcp.context_full", { tokens: tokensText(ended.full_tokens, ended.estimated) })));
  const definitions = ended.tools.map((tool) => {
    try {
      return JSON.parse(tool.definition_text);
    } catch {
      return tool.definition_text;
    }
  });
  full.append(jsonBlock(definitions));
  box.append(full);
  if (ended.lazy_definition_text) {
    const lazy = el("div", "mcp-context-mode");
    lazy.dataset.mode = "lazy";
    lazy.append(el("h3", "mcp-subtitle", t("mcp.context_lazy", { tokens: tokensText(ended.lazy_tokens, ended.estimated) })));
    let definition = ended.lazy_definition_text;
    try {
      definition = JSON.parse(definition);
    } catch {
      // shown as it is
    }
    lazy.append(jsonBlock([definition]));
    // The description as the model reads it, its lines one under the other.
    const description = definition?.function?.description;
    if (typeof description === "string") {
      const pre = el("pre", "mcp-text");
      pre.tabIndex = 0;
      pre.textContent = description;
      lazy.append(pre);
    }
    box.append(lazy);
  }
}

// ---------- the state of the session ----------

function busyReason() {
  if (!store.content) return null;
  const { state, reason_text: reason } = store.session;
  if (state !== "idle") return text("busy_text", { reason: reason || state }) || reason || state;
  return null;
}

function renderBusy() {
  const reason = busyReason();
  const busy = $("mcp-busy");
  busy.hidden = !reason;
  busy.textContent = reason || "";
  $("mcp-stop").disabled = store.session.state !== "mcp_lab";
  renderServers();
  renderCallBusy();
}

function renderContent() {
  for (const node of document.querySelectorAll("[data-text]")) {
    const value = text(node.dataset.text);
    if (value) node.textContent = value;
  }
}

function renderAll() {
  renderBusy();
  renderHandshake();
  renderTools();
  renderCallForm();
  renderCallResult();
  renderContext();
}

// ---------- gestures ----------

async function connectTo(server) {
  const status = $("mcp-status");
  status.classList.remove("is-error");
  store.pending = true;
  renderBusy();
  status.textContent = t("mcp.connecting");
  const answer = await post("/api/intentions/mcp_lab_connect", { server });
  store.pending = false;
  if (!answer.ok) {
    status.classList.add("is-error");
    status.textContent = refusalText(answer);
  } else {
    status.textContent = "";
    const n = stepNumber(answer.body.step_id);
    if (n !== null && startConnection(n)) step(n);
    store.openServer = null;
  }
  renderAll();
}

async function callTool(event) {
  event.preventDefault();
  const status = $("mcp-call-status");
  status.classList.remove("is-error");
  const tool = selectedTool();
  const ended = connectEnded();
  if (!tool || !ended) return;
  const { args, error } = callArguments(tool);
  if (error) {
    status.classList.add("is-error");
    status.textContent = error;
    return;
  }
  store.pending = true;
  renderBusy();
  status.textContent = t("mcp.calling");
  const answer = await post("/api/intentions/mcp_lab_call", { server: ended.server, tool: tool.tool, args });
  store.pending = false;
  if (!answer.ok) {
    status.classList.add("is-error");
    status.textContent = refusalText(answer);
  } else {
    status.textContent = "";
    const n = stepNumber(answer.body.step_id);
    if (n !== null && n > store.connectStep) step(n);
  }
  renderAll();
}

async function stopExchange() {
  await post("/api/intentions/stop", {});
}

// ---------- the stream ----------

let rendering = false;
function scheduleRender() {
  if (rendering) return;
  rendering = true;
  requestAnimationFrame(() => {
    rendering = false;
    renderAll();
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
            // Another process's journal: the page reloads, as the workshop does.
            if (store.serverInstance === null) store.serverInstance = data.instance_id;
            else if (data.instance_id !== store.serverInstance) {
              location.reload();
              return;
            }
          } else if (data.seq > store.lastSeq) {
            if (applyEnvelope(data)) scheduleRender();
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

// After an exchange: whether the workshop's connection is still open (it is closed by
// « Arrêter », by a server gone, by another connection).
async function refreshOpenServer() {
  try {
    const body = await fetchState();
    store.openServer = body.open_server;
  } catch {
    store.openServer = null;
  }
  renderAll();
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
  const alert = $("mcp-content-error");
  alert.hidden = !body.content_error_text;
  alert.textContent = body.content_error_text || "";
  renderContent();
  // The last connection, rebuilt from its envelopes (AD-1): the same projection as the stream's.
  store.connectStep = 0;
  store.steps = new Map();
  const first = stepNumber(body.last_session[0]?.step_id);
  if (first !== null) startConnection(first);
  for (const envelope of body.last_session) applyEnvelope(envelope);
  store.lastSeq = body.seq;
  renderAll();
  return body;
}

async function main() {
  await textsReady; // the page's texts and formats in the session's language
  let body = await refresh();
  while (!body) {
    await new Promise((resolve) => setTimeout(resolve, 2000));
    body = await refresh();
  }
  $("mcp-stop").addEventListener("click", stopExchange);
  $("mcp-call-form").addEventListener("submit", callTool);
  $("mcp-call-tool").addEventListener("change", renderFields);
  $("mcp-call-preset").addEventListener("change", applyPreset);
  document.body.dataset.mcpReady = "true";
  streamEvents();
}

main();
