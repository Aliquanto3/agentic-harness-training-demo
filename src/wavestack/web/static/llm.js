// Story 29: the « LLM nu » screen. Everything it shows comes from `GET /api/llm_lab` or
// from an event of the journal (AD-1): the page counts no token and computes no rate, no
// probability, no size; it lays them out, shows blanks (␣, ↵) and runs a local stopwatch
// anchored on a `*_started` event, replaced by its `*_ended`.

const $ = (id) => document.getElementById(id);

const store = {
  content: null,
  session: { state: "diagnostic", reason_fr: null },
  activeModel: null,
  tokenizer: null,
  serverInstance: null,
  lastSeq: 0,
  pending: { tokenize: null, generate: null },
  sampling: null, // `lab_state().sampling`: defaults, bounds, what can be set
  values: null, // the sliders' values, sent with « Générer »
  gen: { callTs: null, timer: null, first: false, cloud: false },
  reasoning: null, // `lab_state().reasoning`: mode, reason, budget, reserve
  lastLoad: [], // the envelopes of the last model load
  load: { timer: null },
  // The requests already answered by an event: the answer may come before the POST's own.
  answered: new Set(),
};

// ---------- small helpers ----------

function el(tag, className, text) {
  const node = document.createElement(tag);
  if (className) node.className = className;
  if (text !== undefined && text !== null) node.textContent = text;
  return node;
}

// A text of content/llm_lab.yaml by its dotted path, `{name}` replaced by `values[name]`.
function text(path, values = {}) {
  let value = store.content;
  for (const key of path.split(".")) value = value?.[key];
  if (typeof value !== "string") return "";
  return value.replace(/\{(\w+)\}/g, (_, name) => String(values[name] ?? ""));
}

// Blanks made visible: a space ␣, a line break ↵, a tab ⇥ (the chip keeps its width).
const BLANKS = { " ": "␣", "\n": "↵", "\r": "␍", "\t": "⇥" };
const visibleBlanks = (value) => value.replace(/[ \n\r\t]/g, (c) => BLANKS[c]);

const PROMPT_KEY = "wavestack.llm.prompt";

function loadDraft() {
  try {
    return localStorage.getItem(PROMPT_KEY);
  } catch {
    return null;
  }
}

function saveDraft(value) {
  try {
    localStorage.setItem(PROMPT_KEY, value);
  } catch {
    // no storage (private window, blocked data): the draft lives with the page
  }
}

async function post(path, body) {
  const response = await fetch(path, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(body),
  });
  let answer = {};
  try {
    answer = await response.json();
  } catch {
    answer = {};
  }
  return { ok: response.ok, status: response.status, body: answer };
}

// ---------- state of the session: what may be asked now ----------

function busyReason() {
  if (!store.activeModel) return text("no_model_fr") || "Aucun modèle actif.";
  const { state, reason_fr: reason } = store.session;
  if (state !== "idle") return text("busy_fr", { raison: reason || state }) || reason || state;
  return null;
}

function renderModel() {
  const model = store.activeModel;
  const tag = $("llm-model-tag");
  const name = $("llm-model-name");
  tag.replaceChildren();
  if (!model) {
    name.textContent = text("no_model_fr") || "Aucun modèle actif.";
    return;
  }
  const network = model.hosting === "network";
  const label = network
    ? `🌐 RÉSEAU · ${model.provider || ""}`
    : model.kind === "server"
      ? `Local · ${model.provider || "serveur"}`
      : "Local · fichier";
  tag.append(el("span", network ? "hosting-tag-network" : "hosting-tag-local", label));
  name.textContent = model.label;
}

function renderBusy() {
  const reason = busyReason();
  const busy = $("llm-busy");
  busy.hidden = !reason;
  busy.textContent = reason || "";
  const pending = store.pending.tokenize !== null || store.pending.generate !== null;
  for (const id of ["tokenize-button", "generate-button"]) {
    const button = $(id);
    button.disabled = Boolean(reason) || pending;
    button.title = reason || "";
  }
  // « Arrêter »: while the screen generates (class c, `/api/intentions/stop`).
  $("stop-button").disabled = store.session.state !== "llm_lab";
}

function renderContent() {
  for (const node of document.querySelectorAll("[data-text]")) {
    const value = text(node.dataset.text);
    if (value) node.textContent = value;
  }
  const title = text("title_fr");
  if (title) {
    $("llm-title").textContent = title;
    document.title = `WaveStack — ${title}`;
  }
  $("llm-intro").textContent = text("intro_fr");
  const back = text("back_fr");
  if (back) $("back-link").textContent = back;
  const change = text("change_model_fr");
  if (change) $("llm-change-model").textContent = change;
  const active = text("active_model_fr");
  if (active) $("llm-model-label").textContent = active;
  const prompt = $("llm-prompt");
  prompt.placeholder = text("tokenization.placeholder_fr");
}

function renderTokenizerInfo() {
  const info = $("token-info");
  info.textContent = store.tokenizer?.reason_fr || "";
}

// ---------- section 1: tokenization and vectorization ----------

function renderTokenized(p) {
  const status = $("tokenize-status");
  status.classList.remove("is-error");
  status.textContent = "";
  const counts = $("token-counts");
  const chips = $("token-chips");
  const more = $("token-more");
  const blanks = $("token-blanks");
  chips.replaceChildren();
  if (!p.exact) {
    // A cloud model: its tokenizer is at its provider, no chip; the harness's estimate.
    $("token-info").textContent = p.unavailable_fr || p.tokenizer_fr;
    counts.hidden = false;
    counts.textContent = text("tokenization.estimate_fr", {
      estimation: p.figures_fr.estimate,
      caracteres: p.figures_fr.char_count,
      ratio: p.figures_fr.chars_per_token,
    });
    more.hidden = true;
    blanks.hidden = true;
  } else {
    $("token-info").textContent = p.tokenizer_fr;
    counts.hidden = false;
    counts.textContent = text("tokenization.counts_fr", {
      tokens: p.figures_fr.token_count,
      caracteres: p.figures_fr.char_count,
    });
    p.tokens.forEach((token, index) => chips.append(tokenChip(token, index)));
    more.hidden = !p.more;
    more.textContent = p.more ? text("tokenization.more_fr", { reste: p.figures_fr.more }) : "";
    blanks.hidden = !p.tokens.length;
  }
  renderDiagram(p);
}

function tokenChip(token, index) {
  const chip = el("li", "token-chip");
  chip.dataset.parity = index % 2 ? "odd" : "even";
  chip.append(el("span", "token-chip-text", visibleBlanks(token.text)));
  chip.append(el("span", "token-chip-id", String(token.id)));
  if (token.special) {
    chip.classList.add("is-special");
    chip.append(el("span", "token-chip-special", text("tokenization.special_fr") || "spécial"));
    chip.title = text("tokenization.special_help_fr");
  }
  chip.setAttribute("aria-label", `« ${token.text} », identifiant ${token.id}`);
  return chip;
}

function diagramStep(name, value, caption, { unknown = false, isText = false, extra } = {}) {
  const step = el("li", "embedding-step");
  if (unknown) step.classList.add("is-unknown");
  step.append(el("span", "embedding-step-name", name));
  const shown = el("span", "embedding-step-value", value);
  if (isText) shown.classList.add("is-text");
  step.append(shown);
  if (extra) step.append(extra);
  if (caption) step.append(el("span", "embedding-step-caption", caption));
  return step;
}

function renderDiagram(p) {
  const figure = $("embedding-diagram");
  const steps = $("embedding-steps");
  steps.replaceChildren();
  figure.hidden = false;
  const unknown = text("vectorization.unknown_fr") || "inconnue";
  const dims = p.dimensions;
  const figures = dims?.figures_fr || {};
  const s = (key, values) => text(`vectorization.steps.${key}`, values);
  const sample = p.text.length > 24 ? `${p.text.slice(0, 24)}…` : p.text;
  steps.append(diagramStep(s("text_fr"), `« ${sample} »`, null, { isText: true }));
  if (p.exact) {
    const shown = p.tokens.slice(0, 4);
    steps.append(
      diagramStep(
        s("tokens_fr"),
        p.figures_fr.token_count,
        shown.map((t) => visibleBlanks(t.text)).join(" · ") + (p.token_count > 4 ? " …" : "")
      )
    );
    steps.append(
      diagramStep(
        s("ids_fr"),
        shown.map((t) => t.id).join(", ") + (p.token_count > 4 ? ", …" : ""),
        null,
        { isText: true }
      )
    );
  } else {
    steps.append(diagramStep(s("tokens_fr"), `≈ ${p.figures_fr.estimate}`, null));
    steps.append(diagramStep(s("ids_fr"), unknown, null, { unknown: true }));
  }
  const vocab = figures.vocab_size || unknown;
  const width = figures.embedding_length || unknown;
  const row = el("span", "embedding-row");
  row.setAttribute("aria-hidden", "true");
  for (let i = 0; i < 12; i += 1) {
    const cell = el("span");
    if (i === 4) cell.classList.add("is-picked");
    row.append(cell);
  }
  const params = figures.embedding_params
    ? s("params_fr", { parametres: figures.embedding_params })
    : null;
  steps.append(
    diagramStep(
      s("table_fr"),
      `${vocab} × ${width}`,
      [s("table_caption_fr", { vocabulaire: vocab, dimension: width }), params]
        .filter(Boolean)
        .join(" · "),
      { unknown: !dims?.vocab_size && !dims?.embedding_length, extra: row }
    )
  );
  steps.append(
    diagramStep(s("vector_fr"), width, s("vector_caption_fr", { dimension: width }), {
      unknown: !dims?.embedding_length,
    })
  );
  const layers = figures.layer_count;
  const heads = figures.head_count;
  const layersCaption = !layers
    ? null
    : heads
      ? s("layers_caption_fr", { couches: layers, tetes: heads })
      : s("layers_only_caption_fr", { couches: layers });
  steps.append(
    diagramStep(s("layers_fr"), layers || unknown, layersCaption, { unknown: !layers })
  );
  $("embedding-sentence").textContent = p.dimensions_fr || "";
  $("embedding-source").textContent = dims?.source_fr || text("vectorization.help_fr");
}

async function tokenize() {
  const value = $("llm-prompt").value;
  const status = $("tokenize-status");
  status.classList.remove("is-error");
  status.textContent = text("tokenization.running_fr") || "…";
  $("tokenize-button").disabled = true;
  const answer = await post("/api/intentions/llm_tokenize", { text: value });
  if (!answer.ok) {
    status.classList.add("is-error");
    status.textContent = answer.body.detail || `Refusé (HTTP ${answer.status}).`;
    store.pending.tokenize = null;
    renderBusy();
    return;
  }
  const id = answer.body.request_id;
  store.pending.tokenize = store.answered.has(id) ? null : id;
  renderBusy();
}

// ---------- section 2: sampling settings ----------

const SAMPLING_KEY = "wavestack.llm.sampling";
const SAMPLING_ORDER = ["temperature", "top_k", "top_p", "min_p"];
const SAMPLING_STEP = { temperature: 0.05, top_k: 1, top_p: 0.05, min_p: 0.01 };
const numberFr = new Intl.NumberFormat("fr-FR", { maximumFractionDigits: 2 });

function loadSampling() {
  try {
    const saved = JSON.parse(localStorage.getItem(SAMPLING_KEY) || "null");
    return saved && typeof saved === "object" ? saved : null;
  } catch {
    return null;
  }
}

function saveSampling() {
  try {
    localStorage.setItem(SAMPLING_KEY, JSON.stringify(store.values));
  } catch {
    // no storage: the settings live with the page
  }
}

// Within the session's bounds, else the harness's value.
function clampSetting(name, value) {
  const [low, high] = store.sampling.bounds[name];
  const number = Number(value);
  if (!Number.isFinite(number)) return store.sampling.defaults[name];
  const clamped = Math.min(high, Math.max(low, number));
  return name === "top_k" ? Math.round(clamped) : clamped;
}

function renderSampling() {
  const box = $("sampling-controls");
  const sampling = store.sampling;
  if (!sampling) return;
  if (!store.values) {
    const saved = loadSampling() || {};
    store.values = {};
    for (const name of SAMPLING_ORDER) {
      store.values[name] = clampSetting(name, saved[name] ?? sampling.defaults[name]);
    }
  }
  box.replaceChildren();
  for (const name of SAMPLING_ORDER) {
    const reason = sampling.supported[name];
    const row = el("div", "sampling-row");
    row.dataset.setting = name;
    const head = el("div", "sampling-row-head");
    const label = el("label", "", text(`sampling.settings.${name}.label_fr`) || name);
    const number = el("input");
    number.type = "number";
    number.id = `sampling-${name}`;
    label.htmlFor = number.id;
    const range = el("input");
    range.type = "range";
    range.setAttribute("aria-label", `${label.textContent} (curseur)`);
    const [low, high] = sampling.bounds[name];
    for (const input of [number, range]) {
      input.min = String(low);
      input.max = String(high);
      input.step = String(SAMPLING_STEP[name]);
      input.value = String(store.values[name]);
      input.disabled = Boolean(reason);
    }
    const sync = (source, other) => {
      source.addEventListener("input", () => {
        if (source === number && source.value === "") return;
        store.values[name] = clampSetting(name, source.value);
        other.value = String(store.values[name]);
        saveSampling();
      });
      source.addEventListener("change", () => {
        store.values[name] = clampSetting(name, source.value);
        source.value = other.value = String(store.values[name]);
        saveSampling();
      });
    };
    sync(number, range);
    sync(range, number);
    head.append(label, number);
    row.append(head, range, el("span", "sampling-row-help", text(`sampling.settings.${name}.help_fr`)));
    if (reason) {
      row.classList.add("is-unsupported");
      const why = el("span", "sampling-row-reason", reason);
      why.id = `sampling-${name}-reason`;
      number.setAttribute("aria-describedby", why.id);
      range.setAttribute("aria-describedby", why.id);
      row.append(why);
    }
    box.append(row);
  }
  $("sampling-source").textContent = sampling.source_fr || "";
  $("sampling-defaults").textContent = sampling.defaults_fr || "";
}

function resetSampling() {
  store.values = { ...store.sampling.defaults };
  saveSampling();
  renderSampling();
}

// What « Générer » sends: the settings the model takes; the others keep the harness's value.
function samplingToSend() {
  const values = {};
  for (const name of SAMPLING_ORDER) {
    values[name] = store.sampling.supported[name]
      ? store.sampling.defaults[name]
      : clampSetting(name, store.values[name]);
  }
  return values;
}

// « T 0,2 · top-k 5 · top-p 0,9 · min-p 0,05 » from a `sampling` trace; `—` for what is not sent.
function samplingFr(trace) {
  const part = (label, value) => `${label} ${value === null || value === undefined ? "—" : numberFr.format(value)}`;
  const line = [
    part("T", trace.temperature),
    part("top-k", trace.top_k),
    part("top-p", trace.top_p),
    part("min-p", trace.min_p),
  ].join(" · ");
  return trace.note_fr ? `${line} (${trace.note_fr})` : line;
}

// ---------- sections 4 and 5: the prompt's reading, the generation token by token ----------

const duration = (ms) =>
  ms < 1000 ? `${Math.round(ms)} ms` : `${numberFr.format(Math.round(ms / 100) / 10)} s`;

function stopStopwatch() {
  if (store.gen.timer) clearInterval(store.gen.timer);
  store.gen.timer = null;
}

// The local stopwatch, anchored on `model_call_started.ts`, until the first token.
function startStopwatch(ts) {
  stopStopwatch();
  store.gen.callTs = Date.parse(ts);
  const tick = () => {
    if (store.gen.first) return stopStopwatch();
    const elapsed = Math.max(Date.now() - store.gen.callTs, 0);
    $("reading-first-token").textContent = text("reading.waiting_fr", { duree: duration(elapsed) });
  };
  tick();
  store.gen.timer = setInterval(tick, 100);
}

function renderGenerationStarted(p) {
  store.gen.first = false;
  store.gen.cloud = !p.exact;
  $("reading-empty").hidden = true;
  $("reading-body").hidden = false;
  $("reading-label").textContent = text(p.exact ? "reading.rendered_label_fr" : "reading.body_label_fr");
  $("reading-rendered").textContent = p.rendered;
  $("reading-tokens").textContent = text("reading.tokens_fr", {
    tokens: p.figures_fr.prompt_tokens,
    reserve: p.figures_fr.reserve,
  });
  $("reading-sampling").textContent = text("reading.sampling_fr", { reglages: samplingFr(p.sampling) });
  $("reading-first-token").textContent = "";
  $("reading-rate").textContent = "";
  $("generation-tokens").replaceChildren();
  $("generation-count").textContent = "";
  $("generation-rate").textContent = "";
  $("generation-empty").hidden = true;
  $("generation-cloud").hidden = p.exact;
  clearLanes();
  const status = $("generate-status");
  status.classList.remove("is-error");
  status.textContent = text("generation.running_fr");
}

function renderToken(p) {
  store.gen.first = true;
  const chip = el("li", "token-chip");
  chip.dataset.parity = p.index % 2 ? "odd" : "even";
  chip.dataset.channel = p.channel;
  if (store.gen.cloud) chip.classList.add("is-fragment");
  chip.append(el("span", "token-chip-text", visibleBlanks(p.text)));
  chip.append(el("span", "token-chip-id", p.token_id === null ? "" : String(p.token_id)));
  $("generation-tokens").append(chip);
  $("generation-count").textContent = text(store.gen.cloud ? "generation.fragments_fr" : "generation.count_fr", {
    tokens: numberFr.format(p.index + 1),
  });
}

function renderCallEnded(p) {
  stopStopwatch();
  store.gen.first = true;
  $("reading-first-token").textContent = text("reading.first_token_fr", { duree: duration(p.prompt_ms) });
  if (p.output_tps !== null && p.output_tps !== undefined) {
    $("generation-rate").textContent = text("generation.rate_fr", { debit: numberFr.format(p.output_tps) });
  }
}

function renderGenerationEnded(p) {
  stopStopwatch();
  const status = $("generate-status");
  status.classList.toggle("is-error", p.status === "error");
  status.textContent = [text(`generation.status.${p.status}`), p.message_fr].filter(Boolean).join(" ");
  $("reading-rate").textContent = p.figures_fr?.read_tps
    ? text("reading.read_rate_fr", { debit: p.figures_fr.read_tps })
    : store.gen.cloud
      ? ""
      : text("reading.read_rate_unknown_fr");
  if (!$("generation-tokens").children.length) $("generation-empty").hidden = false;
  const figures = p.figures_fr || {};
  $("lane-thinking-count").textContent = text("reasoning.count_fr", { tokens: figures.reasoning_tokens ?? "0" });
  $("lane-answer-count").textContent = text("reasoning.count_fr", { tokens: figures.answer_tokens ?? "0" });
  for (const id of ["lane-thinking", "lane-answer"]) {
    if (!$(id).textContent) $(id).textContent = text("reasoning.empty_fr");
  }
}

async function generate() {
  const status = $("generate-status");
  status.classList.remove("is-error");
  status.textContent = text("generation.running_fr");
  store.pending.generate = "…";
  renderBusy();
  const answer = await post("/api/intentions/llm_generate", {
    prompt: $("llm-prompt").value,
    sampling: samplingToSend(),
    reasoning: store.reasoning?.mode === "toggle" && $("reasoning-toggle").checked,
  });
  if (!answer.ok) {
    status.classList.add("is-error");
    status.textContent = answer.body.detail || `Refusé (HTTP ${answer.status}).`;
    store.pending.generate = null;
    renderBusy();
    return;
  }
  const id = answer.body.request_id;
  store.pending.generate = store.answered.has(id) ? null : id;
  renderBusy();
}

async function stopGeneration() {
  await post("/api/intentions/stop", {});
}

// ---------- section 3: the model's load ----------

const STEP_NAMES = {
  release: "Libération",
  probe: "Sonde",
  check: "Contrôle du budget",
  engine: "Moteur",
  ready: "Prêt",
};

function stopLoadTimer() {
  if (store.load.timer) clearInterval(store.load.timer);
  store.load.timer = null;
}

function appendLoadStep(p) {
  const item = el("li", "load-step");
  item.dataset.step = p.step;
  item.append(el("span", "load-step-name", STEP_NAMES[p.step] || p.step));
  item.append(el("span", "", p.label_fr));
  item.append(el("span", "load-step-time", `${duration(p.duration_ms)} · à ${duration(p.elapsed_ms)}`));
  $("loading-steps").append(item);
}

function renderLoadEnded(p) {
  stopLoadTimer();
  const status = text(`loading.status.${p.status}`) || p.status;
  $("loading-total").textContent = [
    text("loading.total_fr", { modele: p.model.label, statut: status, duree: duration(p.duration_ms) }),
    p.reason_fr,
  ]
    .filter(Boolean)
    .join(" ");
  const memory = $("loading-memory");
  memory.hidden = !p.memory;
  memory.textContent = p.memory?.where_fr || "";
  $("loading-local").hidden = !(p.status === "ok" && p.model.hosting === "local");
}

function renderLoadStarted(envelope) {
  stopLoadTimer();
  $("loading-steps").replaceChildren();
  $("loading-empty").hidden = true;
  $("loading-memory").hidden = true;
  $("loading-local").hidden = true;
  const since = Date.parse(envelope.ts);
  const tick = () => {
    const elapsed = Math.max(Date.now() - since, 0);
    $("loading-total").textContent = `${envelope.payload.phase_label} ${text("loading.running_fr", {
      duree: duration(elapsed),
    })}`;
  };
  tick();
  store.load.timer = setInterval(tick, 200);
}

function renderLastLoad() {
  const events = store.lastLoad || [];
  $("loading-steps").replaceChildren();
  $("loading-empty").hidden = events.length > 0;
  if (!events.length) {
    $("loading-total").textContent = "";
    return;
  }
  for (const envelope of events) {
    if (envelope.kind === "model_load_started") renderLoadStarted(envelope);
    else if (envelope.kind === "model_load_step") appendLoadStep(envelope.payload);
    else if (envelope.kind === "model_load_ended") renderLoadEnded(envelope.payload);
  }
}

// ---------- section 6: reasoning ----------

function renderReasoning() {
  const r = store.reasoning;
  const box = $("reasoning-toggle-box");
  const toggle = $("reasoning-toggle");
  if (!r) return;
  const always = r.mode === "always";
  const can = r.mode === "toggle";
  toggle.disabled = !can;
  if (always) toggle.checked = true;
  if (!can && !always) toggle.checked = false;
  box.classList.toggle("is-disabled", !can);
  $("reasoning-reason").textContent = always
    ? text("reasoning.always_fr")
    : can
      ? ""
      : r.reason_fr || "";
  toggle.title = can ? "" : r.reason_fr || "";
  $("reasoning-budget").textContent = [
    r.budget_fr,
    text("reasoning.reserve_fr", { reserve: numberFr.format(r.reserve) }),
  ]
    .filter(Boolean)
    .join(" ");
}

function clearLanes() {
  for (const id of ["lane-thinking", "lane-answer", "lane-thinking-count", "lane-answer-count"]) {
    $(id).textContent = "";
  }
  $("lane-cut").hidden = true;
}

function laneToken(p) {
  const lane = p.channel === "reasoning" ? $("lane-thinking") : $("lane-answer");
  lane.textContent += p.text;
}

// ---------- the journal ----------

function applyEnvelope(envelope) {
  store.lastSeq = envelope.seq;
  const p = envelope.payload;
  if (envelope.kind === "session_state") {
    store.session = { state: p.state, reason_fr: p.reason_fr };
    if (p.active_model !== undefined) store.activeModel = p.active_model;
    renderModel();
    renderBusy();
    return;
  }
  if (envelope.kind === "model_load_started") {
    renderLoadStarted(envelope);
    return;
  }
  if (envelope.kind === "model_load_step") {
    appendLoadStep(p);
    return;
  }
  if (envelope.kind === "model_load_ended") {
    renderLoadEnded(p);
    refresh(); // the active model, its tokenizer and its last load: read them again
    return;
  }
  if (envelope.context_id !== "llm") return;
  switch (envelope.kind) {
    case "llm_tokenized":
      store.answered.add(p.request_id);
      if (store.pending.tokenize === p.request_id) store.pending.tokenize = null;
      renderTokenized(p);
      renderBusy();
      break;
    case "llm_generation_started":
      renderGenerationStarted(p);
      break;
    case "model_call_started":
      startStopwatch(envelope.ts);
      break;
    case "llm_token":
      renderToken(p);
      laneToken(p);
      break;
    case "reasoning_cut": {
      const cut = $("lane-cut");
      cut.hidden = false;
      cut.textContent = p.message_fr;
      break;
    }
    case "model_call_ended":
      renderCallEnded(p);
      break;
    case "llm_generation_ended":
      store.answered.add(p.request_id);
      if (store.pending.generate === p.request_id) store.pending.generate = null;
      renderGenerationEnded(p);
      renderBusy();
      break;
    case "harness_error":
      if (envelope.step_id) store.answered.add(envelope.step_id);
      if (envelope.step_id && envelope.step_id === store.pending.tokenize) {
        store.pending.tokenize = null;
        const status = $("tokenize-status");
        status.classList.add("is-error");
        status.textContent = [p.message_fr, p.cause].filter(Boolean).join(" ");
        renderBusy();
      }
      break;
    default:
      break;
  }
}

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
          let event = null;
          let data = null;
          for (const line of raw.split("\n")) {
            if (line.startsWith("event:")) event = line.slice(6).trim();
            else if (line.startsWith("data:")) data = line.slice(5).trim();
          }
          if (!data) continue;
          let parsed;
          try {
            parsed = JSON.parse(data);
          } catch {
            continue;
          }
          if (event === "server_instance") {
            // Another process's journal: the page reloads, as the workshop does.
            if (store.serverInstance === null) store.serverInstance = parsed.instance_id;
            else if (parsed.instance_id !== store.serverInstance) {
              location.reload();
              return;
            }
          } else if (parsed.seq > store.lastSeq) {
            applyEnvelope(parsed);
          }
        }
      }
    } catch {
      // reconnection below resumes at lastSeq
    }
    await new Promise((resolve) => setTimeout(resolve, 1000));
  }
}

async function refresh() {
  let body;
  try {
    const response = await fetch("/api/llm_lab");
    if (!response.ok) throw new Error(`HTTP ${response.status}`);
    body = await response.json();
  } catch (error) {
    const alert = $("llm-content-error");
    alert.hidden = false;
    alert.textContent = `Écran indisponible (${error.message}) : rechargez la page.`;
    return null;
  }
  store.content = body.content;
  store.activeModel = body.active_model;
  store.session = body.session_state;
  store.tokenizer = body.tokenizer;
  store.sampling = body.sampling;
  store.reasoning = body.reasoning;
  store.lastLoad = body.last_load;
  const alert = $("llm-content-error");
  alert.hidden = !body.content_error_fr;
  alert.textContent = body.content_error_fr || "";
  renderContent();
  renderModel();
  renderTokenizerInfo();
  renderSampling();
  renderReasoning();
  if (!store.load.timer) renderLastLoad();
  renderBusy();
  return body;
}

async function main() {
  const prompt = $("llm-prompt");
  const body = await refresh();
  prompt.value = loadDraft() ?? (text("tokenization.default_text_fr") || "");
  prompt.addEventListener("input", () => saveDraft(prompt.value));
  $("tokenize-button").addEventListener("click", tokenize);
  $("generate-button").addEventListener("click", generate);
  $("stop-button").addEventListener("click", stopGeneration);
  $("sampling-reset").addEventListener("click", resetSampling);
  if (body) store.lastSeq = body.seq;
  document.body.dataset.labReady = "true";
  streamEvents();
}

main();
