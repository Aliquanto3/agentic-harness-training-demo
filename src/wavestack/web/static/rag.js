// Story 30: the RAG workshop. Everything it shows comes from `GET /api/rag_lab` or from a
// `rag_lab_*` event of the journal (AD-1): the catalog, the options' availability, the
// excerpts, their ranks and scores, the durations and the memory are built in Python. The
// page lays them out and runs no computation of its own.

const $ = (id) => document.getElementById(id);

const store = {
  content: null,
  catalog: null,
  defaultPipeline: null,
  unavailable: null,
  session: { state: "diagnostic", reason_fr: null },
  serverInstance: null,
  lastSeq: 0,
  pending: false, // a POST sent, not answered yet
  run: null, // the projection of the last run: its lanes and their stages
  pipelines: [], // the chains being edited: A, and B when compared
};

// ---------- small helpers ----------

function el(tag, className, text) {
  const node = document.createElement(tag);
  if (className) node.className = className;
  if (text !== undefined && text !== null) node.textContent = text;
  return node;
}

// A text of content/rag_lab.yaml by its dotted path, `{name}` replaced by `values[name]`.
function text(path, values = {}) {
  let value = store.content;
  for (const key of path.split(".")) value = value?.[key];
  if (typeof value !== "string") return "";
  return value.replace(/\{(\w+)\}/g, (_, name) => String(values[name] ?? ""));
}

// « 1 536 » (narrow no-break space) and « 0,812 »: formatting only.
const fmtInt = (n) => (typeof n === "number" ? n.toLocaleString("fr-FR").replace(/\s/g, " ") : "—");
const fmtScore = (x) => (typeof x === "number" ? x.toFixed(3).replace(".", ",") : "—");

const QUESTION_KEY = "wavestack.ragLab.question";
const CHAINS_KEY = "wavestack.ragLab"; // the chains being edited (a browser setting only)

function loadQuestion() {
  try {
    return localStorage.getItem(QUESTION_KEY);
  } catch {
    return null;
  }
}

function saveQuestion(value) {
  try {
    localStorage.setItem(QUESTION_KEY, value);
  } catch {
    // no storage (private window, blocked data): the question lives with the page
  }
}

// Never rejects: a network failure is an answer too, with a French detail.
async function post(path, body) {
  let response;
  try {
    response = await fetch(path, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(body),
    });
  } catch {
    return { ok: false, status: 0, body: { detail: "WaveStack ne répond pas : rechargez la page." } };
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
  return answer.status ? `Refusé (HTTP ${answer.status}).` : "WaveStack ne répond pas : rechargez la page.";
}

// ---------- the chain ----------

function stageInfo(kind) {
  return store.catalog?.stages.find((s) => s.kind === kind) ?? null;
}

function optionInfo(kind, option) {
  return stageInfo(kind)?.options.find((o) => o.id === option) ?? null;
}

const clone = (value) => JSON.parse(JSON.stringify(value));

// The chains remembered by the browser, when they still have the shipped chain's stages.
function loadChains() {
  let saved = null;
  try {
    saved = JSON.parse(localStorage.getItem(CHAINS_KEY) || "null");
  } catch {
    saved = null;
  }
  const kinds = (p) => (Array.isArray(p?.stages) ? p.stages.map((s) => s?.kind).join(",") : null);
  const shipped = kinds(store.defaultPipeline);
  const pipelines = Array.isArray(saved?.pipelines) ? saved.pipelines.slice(0, 2) : [];
  if (!pipelines.length || pipelines.some((p) => kinds(p) !== shipped)) return [clone(store.defaultPipeline)];
  return pipelines;
}

function saveChains() {
  try {
    localStorage.setItem(CHAINS_KEY, JSON.stringify({ pipelines: store.pipelines }));
  } catch {
    // no storage: the chains live with the page
  }
}

function forgetChains() {
  try {
    localStorage.removeItem(CHAINS_KEY);
  } catch {
    // nothing stored
  }
}

function paramInput(lane, stage, param) {
  const label = el("label", "rag-param");
  label.append(el("span", "rag-param-name", param.label_fr));
  const input = el("input", "rag-param-input");
  input.type = "number";
  input.min = String(param.min);
  input.max = String(param.max);
  input.step = "1";
  input.value = String(stage.params?.[param.name] ?? param.default);
  input.dataset.lane = lane;
  input.dataset.stageId = stage.id;
  input.dataset.param = param.name;
  input.title = `De ${fmtInt(param.min)} à ${fmtInt(param.max)} ${param.unit_fr}`.trim();
  input.addEventListener("change", () => {
    const value = Number.parseInt(input.value, 10);
    stage.params = { ...(stage.params || {}) };
    if (Number.isFinite(value)) stage.params[param.name] = value;
    saveChains();
  });
  label.append(input, el("span", "rag-param-unit", param.unit_fr));
  return label;
}

function optionSelect(lane, stage, info) {
  const select = el("select", "rag-option");
  select.setAttribute("aria-label", `Option de l'étape ${info.label_fr}`);
  select.dataset.lane = lane;
  select.dataset.stageId = stage.id;
  for (const option of info.options) {
    const item = el("option", null, option.available ? option.label_fr : `${option.label_fr} (${text("unavailable_fr")})`);
    item.value = option.id;
    item.disabled = !option.available;
    if (option.reason_fr) item.title = option.reason_fr;
    select.append(item);
  }
  select.value = stage.option;
  select.addEventListener("change", () => {
    const option = info.options.find((o) => o.id === select.value);
    stage.option = select.value;
    // The option's own settings, at their shipped values.
    stage.params = Object.fromEntries((option?.params ?? []).map((p) => [p.name, p.default]));
    saveChains();
    renderChains();
    document.querySelector(`select.rag-option[data-lane="${lane}"][data-stage-id="${stage.id}"]`)?.focus();
  });
  return select;
}

function chainCard(lane, stage, index) {
  const info = stageInfo(stage.kind);
  const option = optionInfo(stage.kind, stage.option);
  const card = el("li", "rag-chain-card");
  card.dataset.kind = stage.kind;
  card.dataset.stageId = stage.id;
  if (stage.kind === "generation") card.classList.add("is-model");
  const head = el("p", "rag-chain-head");
  head.append(el("span", "rag-chain-number", String(index + 1)), el("span", "rag-chain-name", info?.label_fr ?? stage.kind));
  card.append(head);
  card.append(el("p", "rag-chain-option", option?.label_fr ?? stage.option));
  if (info && info.options.length > 1) card.append(optionSelect(lane, stage, info));
  for (const param of option?.params ?? []) card.append(paramInput(lane, stage, param));
  if (option?.note_fr) card.append(el("p", "rag-chain-note", option.note_fr));
  for (const other of info?.options ?? []) {
    if (!other.available && other.reason_fr) {
      card.append(el("p", "rag-chain-unavailable", `${other.label_fr} : ${other.reason_fr}`));
    }
  }
  card.append(el("p", "rag-chain-explain", info?.explain_fr ?? ""));
  return card;
}

function renderChains() {
  if (!store.catalog) return;
  const compared = store.pipelines.length > 1;
  $("rag-chain-title-a").hidden = !compared;
  $("rag-chain-title-b").hidden = !compared;
  $("rag-chain-title-a").textContent = text("chain_a_fr") || "Chaîne A";
  $("rag-chain-title-b").textContent = text("chain_b_fr") || "Chaîne B";
  $("rag-chain-b").hidden = !compared;
  $("rag-compare").checked = compared;
  store.pipelines.forEach((pipeline, i) => {
    const lane = i === 0 ? "a" : "b";
    const list = $(i === 0 ? "rag-chain" : "rag-chain-b");
    list.replaceChildren(...pipeline.stages.map((stage, index) => chainCard(lane, stage, index)));
  });
  if (!compared) $("rag-chain-b").replaceChildren();
}

function setCompare(on) {
  const [a] = store.pipelines;
  if (on) {
    const b = clone(a);
    b.label_fr = "B";
    store.pipelines = [a, b];
  } else {
    store.pipelines = [a];
  }
  saveChains();
  renderChains();
}

function resetChains() {
  store.pipelines = [clone(store.defaultPipeline)];
  forgetChains();
  renderChains();
}

// ---------- the run, projected from its events ----------

function stageOf(envelope) {
  const p = envelope.payload;
  if (!store.run || store.run.runId !== p.run_id) return null;
  const lane = store.run.lanes.find((l) => l.lane === p.lane);
  return lane?.stages.find((s) => s.stage_id === p.stage_id) ?? null;
}

function applyEnvelope(envelope) {
  store.lastSeq = Math.max(store.lastSeq, envelope.seq);
  const p = envelope.payload;
  switch (envelope.kind) {
    case "session_state":
      store.session = { state: p.state, reason_fr: p.reason_fr };
      renderBusy();
      return;
    case "rag_lab_run_started":
      store.run = {
        runId: p.run_id,
        question: p.question,
        startedAt: envelope.ts,
        ended: null,
        lanes: p.lanes.map((lane) => ({
          ...lane,
          stages: lane.stages.map((s) => ({ ...s, status: "waiting", progress: null, ended: null })),
        })),
      };
      break;
    case "rag_lab_stage_started": {
      const stage = stageOf(envelope);
      if (stage) stage.status = "running";
      break;
    }
    case "rag_lab_stage_progress": {
      const stage = stageOf(envelope);
      if (stage) stage.progress = { done: p.done, total: p.total };
      break;
    }
    case "rag_lab_stage_ended": {
      const stage = stageOf(envelope);
      if (stage) {
        stage.status = p.status;
        stage.ended = p;
      }
      break;
    }
    case "rag_lab_run_ended":
      if (store.run && store.run.runId === p.run_id) store.run.ended = p;
      break;
    default:
      return;
  }
  renderResults();
  renderBusy();
}

const STATUS_KEYS = {
  waiting: "status.waiting_fr",
  running: "status.running_fr",
  ok: "status.ok_fr",
  error: "status.error_fr",
  skipped: "status.skipped_fr",
  cancelled: "status.cancelled_fr",
  not_run: "status.not_run_fr",
};

function statusLine(stage) {
  const label = text(STATUS_KEYS[stage.status] ?? "") || stage.status;
  if (stage.status === "running" && stage.progress) {
    return `${label} · ${fmtInt(stage.progress.done)} / ${fmtInt(stage.progress.total)}`;
  }
  if (stage.ended && ["ok", "error", "cancelled"].includes(stage.status)) {
    return `${label} · ${fmtInt(stage.ended.duration_ms)} ms`;
  }
  return label;
}

function itemsTable(items) {
  const table = el("table", "rag-items");
  const head = el("tr");
  for (const key of ["rank_fr", "before_fr", "document_fr", "score_fr"]) {
    head.append(el("th", null, text(`columns.${key}`)));
  }
  const thead = el("thead");
  thead.append(head);
  const body = el("tbody");
  for (const item of items) {
    const row = el("tr");
    row.dataset.chunkId = String(item.chunk_id);
    row.append(el("td", "rag-num", fmtInt(item.rank)));
    const before = item.before === null || item.before === undefined ? "—" : fmtInt(item.before);
    const moved = typeof item.before === "number" && item.before !== item.rank;
    const beforeCell = el("td", "rag-num", before);
    if (moved) beforeCell.classList.add(item.before > item.rank ? "is-up" : "is-down");
    row.append(beforeCell);
    const doc = el("td", "rag-doc");
    doc.append(el("span", "rag-doc-title", item.title_fr));
    doc.append(el("span", "rag-doc-text", item.text));
    row.append(doc);
    row.append(el("td", "rag-num", fmtScore(item.score)));
    body.append(row);
  }
  table.append(thead, body);
  return table;
}

function stageCard(stage, index) {
  const card = el("article", "rag-stage-card");
  card.dataset.kind = stage.kind;
  card.dataset.status = stage.status;
  card.dataset.stageId = stage.stage_id;
  if (stage.kind === "generation") card.classList.add("is-model");
  const head = el("header", "rag-stage-head");
  const title = el("h3", "rag-stage-title");
  title.append(el("span", "rag-chain-number", String(index + 1)), el("span", null, stage.label_fr));
  head.append(title);
  head.append(el("span", "rag-stage-status", statusLine(stage)));
  card.append(head);
  card.append(el("p", "rag-stage-option", stage.option_label_fr));
  const ended = stage.ended;
  if (!ended) return card;
  if (ended.error_fr) card.append(el("p", "rag-stage-error", ended.error_fr));
  if (ended.borrowed) card.append(el("p", "rag-stage-borrowed", text("borrowed_fr")));
  const dl = el("dl", "rag-stage-io");
  if (ended.input_fr) dl.append(el("dt", null, text("input_fr")), el("dd", "rag-stage-input", ended.input_fr));
  if (ended.output_fr) dl.append(el("dt", null, text("output_fr")), el("dd", "rag-stage-output", ended.output_fr));
  if (dl.childElementCount) card.append(dl);
  if (ended.facts.length) {
    const facts = el("dl", "rag-stage-facts");
    for (const fact of ended.facts) facts.append(el("dt", null, fact.label_fr), el("dd", null, fact.value_fr));
    card.append(facts);
  }
  if (ended.items.length) card.append(itemsTable(ended.items));
  if (ended.memory_fr || ["ok", "error", "cancelled"].includes(stage.status)) {
    const foot = el("p", "rag-stage-figures");
    foot.append(el("span", "rag-stage-duration", `${text("duration_fr")} : ${fmtInt(ended.duration_ms)} ms`));
    if (ended.memory_fr) foot.append(el("span", "rag-stage-memory", `${text("memory_fr")} : ${ended.memory_fr}`));
    card.append(foot);
  }
  return card;
}

function renderResults() {
  const box = $("rag-results");
  box.replaceChildren();
  const run = store.run;
  $("rag-results-empty").hidden = Boolean(run);
  const summary = $("rag-run-summary");
  summary.hidden = !run;
  if (!run) {
    renderComparison(null);
    return;
  }
  const status = run.ended ? text(STATUS_KEYS[run.ended.status === "ok" ? "ok" : run.ended.status]) : text("status.running_fr");
  summary.textContent = `« ${run.question} » · ${status}${run.ended ? ` · ${fmtInt(run.ended.duration_ms)} ms` : ""}`;
  box.dataset.lanes = String(run.lanes.length);
  renderComparison(run.ended?.comparison ?? null);
  for (const lane of run.lanes) {
    const column = el("section", "rag-lane");
    column.dataset.lane = lane.lane;
    if (run.lanes.length > 1) column.append(el("h3", "rag-lane-title", `Chaîne ${lane.label_fr}`));
    lane.stages.forEach((stage, index) => column.append(stageCard(stage, index)));
    box.append(column);
  }
}

function renderComparison(comparison) {
  const section = $("rag-comparison");
  section.hidden = !comparison;
  if (!comparison) return;
  $("rag-comparison-summary").textContent = comparison.summary_fr;
  const lists = $("rag-comparison-lists");
  lists.replaceChildren();
  const rank = (n) => (n === null || n === undefined ? "—" : `${n}${n === 1 ? "er" : "ᵉ"}`);
  const groups = [
    ["common_fr", comparison.common, (e) => `${e.title_fr} (A : ${rank(e.rank_a)}, B : ${rank(e.rank_b)})`],
    ["only_a_fr", comparison.only_a, (e) => `${e.title_fr} (${rank(e.rank_a)})`],
    ["only_b_fr", comparison.only_b, (e) => `${e.title_fr} (${rank(e.rank_b)})`],
    ["rank_changes_fr", comparison.rank_changes, (e) => `${e.title_fr} : ${rank(e.rank_a)} → ${rank(e.rank_b)}`],
  ];
  for (const [key, entries, line] of groups) {
    const dd = el("dd");
    if (entries.length) {
      const list = el("ul");
      for (const entry of entries) list.append(el("li", null, line(entry)));
      dd.append(list);
    } else {
      dd.textContent = "—";
    }
    lists.append(el("dt", null, text(key)), dd);
  }
}

// ---------- state of the session: what may be asked now ----------

function busyReason() {
  if (!store.content) return null;
  if (store.unavailable) return store.unavailable;
  const { state, reason_fr: reason } = store.session;
  if (state !== "idle") return text("busy_fr", { raison: reason || state }) || reason || state;
  return null;
}

function renderBusy() {
  const reason = busyReason();
  const busy = $("rag-busy");
  busy.hidden = !reason;
  busy.textContent = reason || "";
  const run = $("rag-run");
  run.disabled = Boolean(reason) || store.pending || !store.content;
  run.title = reason || "";
  $("rag-stop").disabled = store.session.state !== "rag_lab";
}

function renderContent() {
  for (const node of document.querySelectorAll("[data-text]")) {
    const value = text(node.dataset.text);
    if (value) node.textContent = value;
  }
  if (store.content) {
    $("rag-title").textContent = store.content.title_fr;
    $("rag-intro").textContent = store.content.intro_fr;
    $("back-link").textContent = store.content.back_fr;
    $("rag-question").placeholder = store.content.question_placeholder_fr;
  }
}

// ---------- gestures ----------

async function runChain() {
  const question = $("rag-question").value.trim();
  const status = $("rag-status");
  status.classList.remove("is-error");
  if (!question) {
    status.classList.add("is-error");
    status.textContent = "Écrivez d'abord une question (500 caractères au plus).";
    return;
  }
  store.pending = true;
  renderBusy();
  status.textContent = text("running_fr");
  // The number fields' last values, even one typed without leaving its field.
  for (const input of document.querySelectorAll(".rag-param-input")) input.dispatchEvent(new Event("change"));
  const answer = await post("/api/intentions/rag_lab_run", { question, pipelines: store.pipelines });
  store.pending = false;
  if (!answer.ok) {
    status.classList.add("is-error");
    status.textContent = refusalText(answer);
  } else {
    status.textContent = "";
  }
  renderBusy();
}

async function stopRun() {
  await post("/api/intentions/stop", {});
}

// ---------- the stream ----------

// SSE read by hand, as app.js: the server names each event after its `kind`.
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
            applyEnvelope(data);
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

async function refresh() {
  let body;
  try {
    const response = await fetch("/api/rag_lab");
    if (!response.ok) throw new Error(`HTTP ${response.status}`);
    body = await response.json();
  } catch (error) {
    const alert = $("rag-content-error");
    alert.hidden = false;
    alert.textContent = `Atelier RAG indisponible (${error.message}) : rechargez la page.`;
    return null;
  }
  store.content = body.content;
  store.catalog = body.catalog;
  store.defaultPipeline = body.default_pipeline;
  store.unavailable = body.unavailable_fr;
  store.session = body.session_state;
  const alert = $("rag-content-error");
  alert.hidden = !body.content_error_fr;
  alert.textContent = body.content_error_fr || "";
  renderContent();
  if (!store.pipelines.length && store.defaultPipeline) store.pipelines = loadChains();
  renderChains();
  // The last run, rebuilt from its envelopes (AD-1): the same projection as the stream's.
  store.run = null;
  for (const envelope of body.last_run) applyEnvelope(envelope);
  store.lastSeq = body.seq;
  renderResults();
  renderBusy();
  return body;
}

async function main() {
  let body = await refresh();
  while (!body) {
    await new Promise((resolve) => setTimeout(resolve, 2000));
    body = await refresh();
  }
  const question = $("rag-question");
  question.value = loadQuestion() ?? (text("default_question_fr") || "");
  question.addEventListener("input", () => saveQuestion(question.value));
  question.addEventListener("keydown", (event) => {
    if (event.key === "Enter" && !$("rag-run").disabled) runChain();
  });
  $("rag-run").addEventListener("click", runChain);
  $("rag-stop").addEventListener("click", stopRun);
  $("rag-compare").addEventListener("change", () => setCompare($("rag-compare").checked));
  $("rag-reset-chain").addEventListener("click", resetChains);
  document.body.dataset.ragReady = "true";
  streamEvents();
}

main();
