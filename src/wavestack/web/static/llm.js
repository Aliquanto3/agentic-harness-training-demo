// Story 29: the « LLM nu » screen. Everything it shows comes from `GET /api/llm_lab` or
// from an event of the journal (AD-1): the page counts no token and computes no rate, no
// probability, no size; it lays them out, shows blanks (␣, ↵) and runs a local stopwatch
// anchored on a `*_started` event, replaced by its `*_ended`.
//
// Languages (4/5): the page's own texts come from `content/ui.yaml` (section `llm`) through
// `t()`, its formats from the language (`i18n.js`); the screen's texts stay those of
// `content/llm_lab.yaml`, read in the session's language by `GET /api/llm_lab`.

import { locale, numberFormat, ready as textsReady, section, t } from "./i18n.js";

const $ = (id) => document.getElementById(id);
const quote = (value) => t("common.format.quote", { text: value });

const store = {
  content: null,
  session: { state: "diagnostic", reason_text: null },
  activeModel: null,
  tokenizer: null,
  serverInstance: null,
  lastSeq: 0,
  pending: { tokenize: null, generate: null, compare: null }, // compare: `llm{n}.b`, story 5
  sampling: null, // `lab_state().sampling`: defaults, bounds, what can be set
  values: null, // the sliders' values, sent with « Générer »
  gen: { callTs: null, timer: null, first: false, cloud: false },
  reasoning: null, // `lab_state().reasoning`: mode, reason, budget, reserve
  candidates: null, // `lab_state().candidates`: available, reason, n
  pinned: null, // the chip whose candidates a click keeps open
  lastLoad: [], // the envelopes of the last model load
  load: { timer: null },
  // The requests already answered by an event: the answer may come before the POST's own.
  answered: new Set(),
  // Story 5 (2026-09-30): the live distribution of section 2. `index`: the token chosen in
  // the last generation; `tokens`: how many the session keeps (`lab_state().distribution`,
  // then the `llm_token` events); `ticket`: the last request sent (the last answer wins).
  dist: { index: 0, tokens: 0, ticket: 0, timer: null },
  valuesB: null, // the comparison's settings B, as `values`
  win: { reserve: 0, reserveText: "" }, // the window diagram's output reserve (section 4)
};

// ---------- small helpers ----------

function el(tag, className, text) {
  const node = document.createElement(tag);
  if (className) node.className = className;
  if (text !== undefined && text !== null) node.textContent = text;
  return node;
}

// Correctif nuit du 2026-10-01 (restes différés) : the noun a `{one, other}` value picks,
// the same way `i18n.js`'s `t()` picks one for `content/ui.yaml` (« 1 tokens produits »).
let pluralRules = null;
let pluralLocale = null;
function pluralSelect(count) {
  if (pluralRules === null || pluralLocale !== locale()) {
    pluralLocale = locale();
    pluralRules = new Intl.PluralRules(pluralLocale);
  }
  return pluralRules.select(count);
}

// A text of content/llm_lab.yaml by its dotted path, `{name}` replaced by `values[name]`.
// A `{one, other}` value is chosen by `values.count` (a number), as `i18n.js`'s `t()` does.
function text(path, values = {}) {
  let value = store.content;
  for (const key of path.split(".")) value = value?.[key];
  if (value !== null && typeof value === "object" && typeof values.count === "number") {
    value = value[pluralSelect(values.count)] ?? value.other;
  }
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

// A refusal's text: the session's French detail, never « [object Object] ».
function refusalText(answer) {
  const detail = answer.body?.detail;
  if (typeof detail === "string") return detail;
  if (Array.isArray(detail) && detail[0]?.msg) return t("llm.invalid_intention", { detail: detail[0].msg });
  return answer.status ? t("common.refused_http", { status: String(answer.status) }) : t("common.unreachable");
}

// ---------- state of the session: what may be asked now ----------

function busyReason() {
  if (!store.activeModel) return text("no_model_text") || t("llm.no_model");
  const { state, reason_text: reason } = store.session;
  if (state !== "idle") return text("busy_text", { raison: reason || state }) || reason || state;
  return null;
}

function renderModel() {
  const model = store.activeModel;
  const tag = $("llm-model-tag");
  const name = $("llm-model-name");
  tag.replaceChildren();
  if (!model) {
    name.textContent = text("no_model_text") || t("llm.no_model");
    return;
  }
  const network = model.hosting === "network";
  const label = network
    ? t("llm.hosting.network", { provider: model.provider || "" })
    : model.kind === "server"
      ? t("llm.hosting.server", { provider: model.provider || t("llm.hosting.server_default") })
      : t("llm.hosting.file");
  tag.append(el("span", network ? "hosting-tag-network" : "hosting-tag-local", label));
  name.textContent = model.label;
}

function renderBusy() {
  const reason = busyReason();
  const busy = $("llm-busy");
  busy.hidden = !reason;
  busy.textContent = reason || "";
  const pending =
    store.pending.tokenize !== null || store.pending.generate !== null || store.pending.compare !== null;
  for (const id of ["tokenize-button", "generate-button", "compare-button"]) {
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
  // Lot 1 of 2026-10-04 (D2): the h1 only; <title> keeps the full title (`llm.page_title`).
  const title = text("title_text");
  if (title) $("llm-title").textContent = title;
  $("llm-intro").textContent = text("intro_text");
  const change = text("change_model_text");
  if (change) $("llm-change-model").textContent = change;
  const active = text("active_model_text");
  if (active) $("llm-model-label").textContent = active;
  const prompt = $("llm-prompt");
  prompt.placeholder = text("tokenization.placeholder_text");
  renderQuestions();
}

// Story 5 (2026-09-30): « Les questions que vous vous posez », one list per section
// (`sections.{id}.questions_text`); a section without any hides its box.
function renderQuestions() {
  for (const list of document.querySelectorAll("[data-questions]")) {
    const items = store.content?.sections?.[list.dataset.questions]?.questions_text || [];
    list.replaceChildren(...items.map((question) => el("li", "", question)));
    const box = list.closest(".llm-questions");
    if (box) box.hidden = !items.length;
  }
}

function renderTokenizerInfo() {
  const info = $("token-info");
  info.textContent = store.tokenizer?.reason_text || "";
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
    $("token-info").textContent = p.unavailable_text || p.tokenizer_text;
    counts.hidden = false;
    counts.textContent = text("tokenization.estimate_text", {
      estimation_phrase: text("tokenization.token_noun", {
        n: p.figures_text.estimate,
        count: p.estimate,
      }),
      caracteres_phrase: text("tokenization.character_noun", {
        n: p.figures_text.char_count,
        count: p.char_count,
      }),
      ratio: p.figures_text.chars_per_token,
    });
    more.hidden = true;
    blanks.hidden = true;
  } else {
    $("token-info").textContent = p.tokenizer_text;
    counts.hidden = false;
    counts.textContent = text("tokenization.counts_text", {
      tokens_phrase: text("tokenization.token_noun", {
        n: p.figures_text.token_count,
        count: p.token_count,
      }),
      caracteres_phrase: text("tokenization.character_noun", {
        n: p.figures_text.char_count,
        count: p.char_count,
      }),
    });
    p.tokens.forEach((token, index) => chips.append(tokenChip(token, index)));
    more.hidden = !p.more;
    more.textContent = p.more
      ? text("tokenization.more_text", { reste: p.figures_text.more, count: p.more })
      : "";
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
    chip.append(el("span", "token-chip-special", text("tokenization.special_text") || t("llm.special")));
    chip.title = text("tokenization.special_help_text");
  }
  chip.setAttribute("aria-label", t("llm.token_label", { text: quote(token.text), id: String(token.id) }));
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
  const unknown = text("vectorization.unknown_text") || t("llm.unknown");
  const dims = p.dimensions;
  const figures = dims?.figures_text || {};
  const s = (key, values) => text(`vectorization.steps.${key}`, values);
  const sample = p.text.length > 24 ? `${p.text.slice(0, 24)}…` : p.text;
  steps.append(diagramStep(s("text_text"), quote(sample), null, { isText: true }));
  if (p.exact) {
    const shown = p.tokens.slice(0, 4);
    steps.append(
      diagramStep(
        s("tokens_text"),
        p.figures_text.token_count,
        shown.map((t) => visibleBlanks(t.text)).join(" · ") + (p.token_count > 4 ? " …" : "")
      )
    );
    steps.append(
      diagramStep(
        s("ids_text"),
        shown.map((t) => t.id).join(", ") + (p.token_count > 4 ? ", …" : ""),
        null,
        { isText: true }
      )
    );
  } else {
    steps.append(diagramStep(s("tokens_text"), `≈ ${p.figures_text.estimate}`, null));
    steps.append(diagramStep(s("ids_text"), unknown, null, { unknown: true }));
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
    ? s("params_text", { parametres: figures.embedding_params })
    : null;
  steps.append(
    diagramStep(
      s("table_text"),
      `${vocab} × ${width}`,
      [s("table_caption_text", { vocabulaire: vocab, dimension: width }), params]
        .filter(Boolean)
        .join(" · "),
      { unknown: !dims?.vocab_size && !dims?.embedding_length, extra: row }
    )
  );
  steps.append(
    diagramStep(s("vector_text"), width, s("vector_caption_text", { dimension: width }), {
      unknown: !dims?.embedding_length,
    })
  );
  const layers = figures.layer_count;
  const heads = figures.head_count;
  const layersCaption = !layers
    ? null
    : heads
      ? s("layers_caption_text", { couches: layers, tetes: heads })
      : s("layers_only_caption_text", { couches: layers });
  steps.append(
    diagramStep(s("layers_text"), layers || unknown, layersCaption, { unknown: !layers })
  );
  $("embedding-sentence").textContent = p.dimensions_text || "";
  $("embedding-source").textContent = dims?.source_text || text("vectorization.help_text");
}

async function tokenize() {
  const value = $("llm-prompt").value;
  const status = $("tokenize-status");
  if (!value.trim()) {
    status.classList.add("is-error");
    status.textContent = t("llm.empty_prompt");
    return;
  }
  status.classList.remove("is-error");
  status.textContent = text("tokenization.running_text") || "…";
  $("tokenize-button").disabled = true;
  const answer = await post("/api/intentions/llm_tokenize", { text: value });
  if (!answer.ok) {
    status.classList.add("is-error");
    status.textContent = refusalText(answer);
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
// Read at each use: the language is known once `textsReady` resolved.
const decimals = () => numberFormat({ maximumFractionDigits: 2 });

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

// One setting's card: its label, number field and slider kept in step with `values[name]`,
// `changed()` called at each move (`prefix`: the fields' ids, `sampling` for section 2,
// `compare` for the comparison's settings B; `help`: the setting's explanation under it).
function samplingRow(name, values, prefix, changed, help) {
  const sampling = store.sampling;
  const reason = sampling.supported[name];
  const row = el("div", "sampling-row");
  row.dataset.setting = name;
  const head = el("div", "sampling-row-head");
  const label = el("label", "", text(`sampling.settings.${name}.label_text`) || name);
  const number = el("input");
  number.type = "number";
  number.id = `${prefix}-${name}`;
  label.htmlFor = number.id;
  const range = el("input");
  range.type = "range";
  range.setAttribute("aria-label", t("llm.slider", { label: label.textContent }));
  const [low, high] = sampling.bounds[name];
  for (const input of [number, range]) {
    input.min = String(low);
    input.max = String(high);
    input.step = String(SAMPLING_STEP[name]);
    input.value = String(values[name]);
    input.disabled = Boolean(reason);
  }
  const sync = (source, other) => {
    source.addEventListener("input", () => {
      if (source === number && source.value === "") return;
      values[name] = clampSetting(name, source.value);
      other.value = String(values[name]);
      changed();
    });
    source.addEventListener("change", () => {
      // An emptied field takes back the value it had, not 0.
      if (source.value.trim() !== "") values[name] = clampSetting(name, source.value);
      source.value = other.value = String(values[name]);
      changed();
    });
  };
  sync(number, range);
  sync(range, number);
  head.append(label, number);
  row.append(head, range);
  if (help) row.append(el("span", "sampling-row-help", text(`sampling.settings.${name}.help_text`)));
  if (reason) {
    row.classList.add("is-unsupported");
    const why = el("span", "sampling-row-reason", reason);
    why.id = `${prefix}-${name}-reason`;
    number.setAttribute("aria-describedby", why.id);
    range.setAttribute("aria-describedby", why.id);
    row.append(why);
  }
  return row;
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
    // Story 5 (2026-09-30): each move asks the session for the distribution again.
    const changed = () => {
      saveSampling();
      scheduleDistribution();
    };
    box.append(samplingRow(name, store.values, "sampling", changed, true));
  }
  $("sampling-source").textContent = sampling.source_text || "";
  $("sampling-defaults").textContent = sampling.defaults_text || "";
  renderCompareSettings();
}

function resetSampling() {
  store.values = { ...store.sampling.defaults };
  saveSampling();
  renderSampling();
  scheduleDistribution();
}

// What « Générer » sends: the settings the model takes; the others keep the harness's value.
// Story 5 (2026-09-30): `values` the comparison's settings B, or section 2's by default.
function samplingToSend(values = store.values) {
  const sent = {};
  for (const name of SAMPLING_ORDER) {
    sent[name] = store.sampling.supported[name]
      ? store.sampling.defaults[name]
      : clampSetting(name, values[name]);
  }
  return sent;
}

// « T 0,2 · top-k 5 · top-p 0,9 · min-p 0,05 » from a `sampling` trace; `—` for what is not sent.
function samplingFr(trace) {
  const part = (label, value) => `${label} ${value === null || value === undefined ? "—" : decimals().format(value)}`;
  const line = [
    part("T", trace.temperature),
    part("top-k", trace.top_k),
    part("top-p", trace.top_p),
    part("min-p", trace.min_p),
  ].join(" · ");
  return trace.note_text ? `${line} (${trace.note_text})` : line;
}

// ---------- story 5 (2026-09-30): the live distribution of section 2 ----------
//
// The session keeps, for the last generation with the candidates, the most probable tokens of
// each token; at each move of a slider the page asks it (`POST /api/llm_lab/distribution`)
// which ones stay in the draw and their chance, for the settings shown (AD-1: the session
// computes, the page draws bars from the values received).

const DIST_ROWS = 10; // the bars shown; the others read are counted under them
const DIST_DEBOUNCE_MS = 80;

// Nothing to show: the reason the candidates are unavailable (a server, a cloud model), the
// session's answer (`detail`), or what to do.
function renderDistributionIdle(detail) {
  store.dist.ticket += 1; // an answer still in flight is stale: it draws nothing
  $("distribution-body").hidden = true;
  const offer = store.candidates;
  const why = offer && !offer.available ? offer.reason_text : detail || text("distribution.empty_text");
  $("distribution-empty").textContent = why || "";
}

function scheduleDistribution(delay = DIST_DEBOUNCE_MS) {
  if (store.dist.timer) clearTimeout(store.dist.timer);
  store.dist.timer = setTimeout(fetchDistribution, delay);
}

async function fetchDistribution() {
  store.dist.timer = null;
  // Asked only when the session keeps something: a 404 would be an error in the console.
  if (!store.candidates?.available || !store.dist.tokens || !store.sampling || !store.values) {
    renderDistributionIdle();
    return;
  }
  store.dist.ticket += 1;
  const ticket = store.dist.ticket;
  const answer = await post("/api/llm_lab/distribution", {
    index: store.dist.index,
    sampling: samplingToSend(),
  });
  if (ticket !== store.dist.ticket) return; // a later request was sent: its answer wins
  if (!answer.ok) {
    renderDistributionIdle(refusalText(answer));
    return;
  }
  renderDistribution(answer.body);
}

// A bar of one value in [0, 1] and its value in %, as the candidates' popover draws them.
function distributionBar(kind, value, label, name) {
  const cell = el("span", `dist-cell ${kind}`);
  if (name) cell.append(el("span", "llm-sr-only", `${name} `));
  const bar = el("span", "dist-bar");
  bar.setAttribute("aria-hidden", "true");
  const fill = el("span");
  fill.style.width = `${Math.max(0, Math.min(1, value)) * 100}%`;
  bar.append(fill);
  cell.append(bar, el("span", "dist-value", label));
  return cell;
}

function renderDistribution(body) {
  const rows = body.candidates || [];
  if (!rows.length) {
    renderDistributionIdle();
    return;
  }
  $("distribution-empty").textContent = "";
  $("distribution-body").hidden = false;
  $("distribution-token").textContent = text("distribution.token_text", {
    index: decimals().format(body.index + 1),
    texte: quote(visibleBlanks(body.token_text)),
  });
  const list = $("distribution-bars");
  list.replaceChildren();
  for (const c of rows.slice(0, DIST_ROWS)) {
    const row = el("li", "dist-row");
    if (!c.kept) row.classList.add("is-dropped");
    row.append(el("span", "dist-text", quote(visibleBlanks(c.text))));
    row.append(distributionBar("is-model", c.p, percent().format(c.p), text("distribution.probability_text")));
    row.append(
      distributionBar(
        "is-chance",
        c.p_sampled,
        c.kept ? percent().format(c.p_sampled) : text("distribution.dropped_text"),
        text("distribution.chance_text")
      )
    );
    list.append(row);
  }
  // The rest of the vocabulary: its mass at temperature 1, never drawn here (approximate).
  const tail = el("li", "dist-row is-tail");
  tail.append(el("span", "dist-text", text("distribution.tail_text")));
  tail.append(distributionBar("is-model", body.tail, percent().format(body.tail), text("distribution.probability_text")));
  tail.append(el("span", "dist-cell is-chance"));
  list.append(tail);
  const more = rows.length > DIST_ROWS ? text("distribution.more_text", { reste: decimals().format(rows.length - DIST_ROWS) }) : "";
  $("distribution-kept").textContent = [
    text("distribution.kept_text", {
      gardes: decimals().format(body.kept_count),
      lus: decimals().format(rows.length),
    }),
    more,
  ]
    .filter(Boolean)
    .join(" ");
  $("distribution-tail").textContent = text("distribution.tail_help_text", {
    reste: percent().format(body.tail),
    lus: decimals().format(rows.length),
  });
  markDistributionChip();
}

// The chip of section 5 whose candidates section 2 shows.
function markDistributionChip() {
  for (const chip of document.querySelectorAll("#generation-tokens .token-chip.is-dist-chosen")) {
    chip.classList.remove("is-dist-chosen");
  }
  const chip = document.querySelector(`#generation-tokens .token-chip[data-index="${store.dist.index}"]`);
  if (chip?.classList.contains("has-candidates")) chip.classList.add("is-dist-chosen");
}

function chooseDistributionToken(index) {
  store.dist.index = index;
  markDistributionChip();
  scheduleDistribution(0);
}

// ---------- story 5 (2026-09-30): the comparison A/B of section 5 ----------

const SAMPLING_B_KEY = "wavestack.llm.sampling_b";
const B_TEMPERATURE = 1.2; // settings B's first value: the harness's, hotter

function saveSamplingB() {
  try {
    localStorage.setItem(SAMPLING_B_KEY, JSON.stringify(store.valuesB));
  } catch {
    // no storage: the settings live with the page
  }
}

function renderCompareSettings() {
  const box = $("compare-settings");
  const sampling = store.sampling;
  if (!sampling) return;
  if (!store.valuesB) {
    let saved = null;
    try {
      saved = JSON.parse(localStorage.getItem(SAMPLING_B_KEY) || "null");
    } catch {
      saved = null;
    }
    const first = { ...sampling.defaults, temperature: B_TEMPERATURE };
    store.valuesB = {};
    for (const name of SAMPLING_ORDER) {
      store.valuesB[name] = clampSetting(name, (saved && saved[name]) ?? first[name]);
    }
  }
  for (const row of box.querySelectorAll(".sampling-row")) row.remove();
  for (const name of SAMPLING_ORDER) {
    box.append(samplingRow(name, store.valuesB, "compare", saveSamplingB, false));
  }
}

// `llm{n}.a` → "a", `llm{n}.b` → "b", anything else (« Générer ») → null.
function compareLane(requestId) {
  const match = /\.(a|b)$/.exec(requestId || "");
  return match ? match[1] : null;
}

function laneBox(lane) {
  const box = $(`compare-${lane}`);
  return {
    sampling: box.querySelector(".compare-lane-sampling"),
    thinking: box.querySelector(".compare-lane-thinking"),
    text: box.querySelector(".compare-lane-text"),
    status: box.querySelector(".compare-lane-status"),
  };
}

function clearCompareLane(lane, sampling, status) {
  const box = laneBox(lane);
  box.sampling.textContent = sampling ? samplingFr(sampling) : "";
  box.thinking.textContent = "";
  box.text.textContent = "";
  box.status.textContent = status;
  box.status.classList.remove("is-error");
}

function compareEvent(lane, kind, p) {
  const box = laneBox(lane);
  if (kind === "llm_generation_started") {
    $("compare-lanes").hidden = false;
    clearCompareLane(lane, p.sampling, text("generation.running_text"));
    if (lane === "a") clearCompareLane("b", null, text("compare.waiting_text"));
  } else if (kind === "llm_token") {
    for (const part of p.parts || []) {
      (part.channel === "reasoning" ? box.thinking : box.text).textContent += part.text;
    }
  } else if (kind === "llm_generation_ended") {
    box.status.classList.toggle("is-error", p.status === "error");
    box.status.textContent = [text(`generation.status.${p.status}`), p.message_text].filter(Boolean).join(" ");
    if (!box.text.textContent && !box.thinking.textContent) box.text.textContent = text("compare.empty_text");
  }
}

async function compareRun() {
  const status = $("compare-status");
  if (!$("llm-prompt").value.trim()) {
    status.classList.add("is-error");
    status.textContent = t("llm.empty_prompt");
    return;
  }
  status.classList.remove("is-error");
  status.textContent = text("compare.running_text");
  store.pending.compare = "…";
  renderBusy();
  const answer = await post("/api/intentions/llm_compare", {
    prompt: $("llm-prompt").value,
    sampling_a: samplingToSend(),
    sampling_b: samplingToSend(store.valuesB),
    reasoning: store.reasoning?.mode === "toggle" && $("reasoning-toggle").checked,
    candidates: Boolean(store.candidates?.available) && $("candidates-toggle").checked,
  });
  if (!answer.ok) {
    status.classList.add("is-error");
    status.textContent = refusalText(answer);
    store.pending.compare = null;
    renderBusy();
    return;
  }
  const last = `${answer.body.request_id}.b`;
  store.pending.compare = store.answered.has(last) ? null : last;
  if (!store.pending.compare) status.textContent = "";
  renderBusy();
}

// ---------- story 5 (2026-09-30): the window diagram of section 4 ----------
//
// From `llm_generation_started` (`usable`, `reserve`, `prompt_tokens` and their figures): the
// window drawn as its two shares, the prompt filling the first, each token produced the
// second. CSS lays the widths out from the values received; the page counts nothing.

function renderWindow(p) {
  const figure = $("window-diagram");
  if (p.usable === null || p.usable === undefined) {
    figure.hidden = true;
    return;
  }
  figure.hidden = false;
  const figures = p.figures_text || {};
  const [usable, reserve] = figure.querySelectorAll(".window-part");
  const [usableLabel, reserveLabel] = [$("window-usable-label"), $("window-reserve-label")];
  for (const [part, label, grow] of [
    [usable, usableLabel, p.usable],
    [reserve, reserveLabel, p.reserve],
  ]) {
    part.style.flexGrow = String(Math.max(grow, 1));
    label.style.flexGrow = String(Math.max(grow, 1));
  }
  usable.title = text("window.free_text");
  const promptFill = figure.querySelector(".window-fill.is-prompt");
  promptFill.title = text("window.prompt_text", { tokens: figures.prompt_tokens });
  promptFill.style.width = `min(100%, calc(100% * ${p.prompt_tokens} / ${Math.max(p.usable, 1)}))`;
  figure.querySelector(".window-fill.is-output").style.width = "0";
  store.win.reserve = Math.max(p.reserve, 1);
  store.win.reserveText = text("window.reserve_text", { reserve: figures.reserve });
  usableLabel.textContent = text("window.prompt_text", { tokens: figures.prompt_tokens });
  reserveLabel.textContent = store.win.reserveText;
  $("window-caption").textContent = text("window.caption_text", {
    fenetre: figures.window,
    utilisables: figures.usable,
    reserve: figures.reserve,
  });
}

function windowToken(p) {
  const fill = document.querySelector("#window-diagram .window-fill.is-output");
  if (!fill || $("window-diagram").hidden) return;
  // A server or a cloud model sends fragments of several tokens: no share of the reserve
  // drawn from their count, only the count said.
  fill.style.width = store.gen.fragments
    ? "0"
    : `min(100%, calc(100% * ${p.index + 1} / ${store.win.reserve}))`;
  const output = store.gen.fragments ? "window.output_fragments_text" : "window.output_text";
  $("window-reserve-label").textContent = `${store.win.reserveText} · ${text(output, {
    tokens: decimals().format(p.index + 1),
    count: p.index + 1,
  })}`;
}

// ---------- sections 4 and 5: the prompt's reading, the generation token by token ----------

const duration = (ms) =>
  ms < 1000 ? `${Math.round(ms)} ms` : `${decimals().format(Math.round(ms / 100) / 10)} s`;

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
    $("reading-first-token").textContent = text("reading.waiting_text", { duree: duration(elapsed) });
  };
  tick();
  store.gen.timer = setInterval(tick, 100);
}

const CHIP_LIMIT = 512; // as the tokenization: the page stays fluid on a projector

function renderGenerationStarted(p) {
  store.gen.first = false;
  store.gen.cloud = !p.exact;
  store.gen.fragments = p.unit === "fragment";
  $("reading-empty").hidden = true;
  $("reading-body").hidden = false;
  $("reading-label").textContent = text(p.exact ? "reading.rendered_label_text" : "reading.body_label_text");
  $("reading-rendered").textContent = p.rendered;
  $("reading-tokens").textContent = text("reading.tokens_text", {
    tokens_phrase: text("reading.token_noun", { n: p.figures_text.prompt_tokens, count: p.prompt_tokens }),
    reserve_phrase: text("reading.token_noun", { n: p.figures_text.reserve, count: p.reserve }),
  });
  $("reading-sampling").textContent = text("reading.sampling_text", { reglages: samplingFr(p.sampling) });
  $("reading-first-token").textContent = "";
  $("reading-rate").textContent = "";
  $("generation-tokens").replaceChildren();
  store.pinned = null;
  hideCandidates();
  $("generation-count").textContent = "";
  $("generation-rate").textContent = "";
  $("generation-empty").hidden = true;
  const unitNote = $("generation-cloud");
  unitNote.hidden = !store.gen.fragments;
  unitNote.textContent = text(p.exact ? "generation.server_text" : "generation.cloud_text");
  $("generation-more").textContent = "";
  clearLanes();
  const status = $("generate-status");
  status.classList.remove("is-error");
  status.textContent = text("generation.running_text");
  // Story 5 (2026-09-30): the window's diagram; a new generation erases the session's
  // memory of the last one: the distribution waits for its first token.
  renderWindow(p);
  store.dist.index = 0;
  store.dist.tokens = 0;
  renderDistributionIdle();
}

function renderToken(p) {
  store.gen.first = true;
  windowToken(p);
  if (p.candidates?.length && store.candidates?.available) {
    // Story 5 (2026-09-30): kept by the session before the event; the chosen token's
    // distribution is asked as soon as it exists.
    store.dist.tokens = p.index + 1;
    if (p.index === store.dist.index) scheduleDistribution(0);
  }
  $("generation-count").textContent = text(store.gen.fragments ? "generation.fragments_text" : "generation.count_text", {
    tokens: decimals().format(p.index + 1),
    count: p.index + 1,
  });
  if (p.index >= CHIP_LIMIT) {
    $("generation-more").textContent = text("generation.more_text", {
      reste: decimals().format(p.index + 1 - CHIP_LIMIT),
    });
    return;
  }
  const chip = el("li", "token-chip");
  chip.dataset.parity = p.index % 2 ? "odd" : "even";
  chip.dataset.channel = p.channel;
  chip.dataset.index = String(p.index);
  if (store.gen.fragments) chip.classList.add("is-fragment");
  chip.setAttribute(
    "aria-label",
    p.token_id === null ? quote(p.text) : t("llm.token_label", { text: quote(p.text), id: String(p.token_id) })
  );
  chip.append(el("span", "token-chip-text", visibleBlanks(p.text)));
  chip.append(el("span", "token-chip-id", p.token_id === null ? "" : String(p.token_id)));
  if (p.candidates?.length) bindCandidates(chip, p);
  $("generation-tokens").append(chip);
}

function renderCallEnded(p) {
  stopStopwatch();
  store.gen.first = true;
  $("reading-first-token").textContent = text("reading.first_token_text", { duree: duration(p.prompt_ms) });
  if (p.output_tps !== null && p.output_tps !== undefined) {
    $("generation-rate").textContent = text("generation.rate_text", { debit: decimals().format(p.output_tps) });
  }
}

function renderGenerationEnded(p) {
  stopStopwatch();
  const status = $("generate-status");
  status.classList.toggle("is-error", p.status === "error");
  status.textContent = [text(`generation.status.${p.status}`), p.message_text].filter(Boolean).join(" ");
  $("reading-rate").textContent = p.figures_text?.read_tps
    ? text("reading.read_rate_text", { debit: p.figures_text.read_tps })
    : store.gen.cloud
      ? ""
      : text("reading.read_rate_unknown_text");
  if (!$("generation-tokens").children.length) $("generation-empty").hidden = false;
  const figures = p.figures_text || {};
  const key = store.gen.fragments ? "reasoning.fragments_count_text" : "reasoning.count_text";
  $("lane-thinking-count").textContent = text(key, {
    tokens: figures.reasoning_tokens ?? "0",
    count: p.reasoning_tokens ?? 0,
  });
  $("lane-answer-count").textContent = text(key, {
    tokens: figures.answer_tokens ?? "0",
    count: p.answer_tokens ?? 0,
  });
  for (const id of ["lane-thinking", "lane-answer"]) {
    if (!$(id).textContent) $(id).textContent = text("reasoning.empty_text");
  }
}

async function generate() {
  const status = $("generate-status");
  if (!$("llm-prompt").value.trim()) {
    status.classList.add("is-error");
    status.textContent = t("llm.empty_prompt");
    return;
  }
  status.classList.remove("is-error");
  status.textContent = text("generation.running_text");
  store.pending.generate = "…";
  renderBusy();
  const answer = await post("/api/intentions/llm_generate", {
    prompt: $("llm-prompt").value,
    sampling: samplingToSend(),
    reasoning: store.reasoning?.mode === "toggle" && $("reasoning-toggle").checked,
    candidates: Boolean(store.candidates?.available) && $("candidates-toggle").checked,
  });
  if (!answer.ok) {
    status.classList.add("is-error");
    status.textContent = refusalText(answer);
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

const STEP_NAMES = section("llm.load_steps");

function stopLoadTimer() {
  if (store.load.timer) clearInterval(store.load.timer);
  store.load.timer = null;
}

function appendLoadStep(p) {
  const item = el("li", "load-step");
  item.dataset.step = p.step;
  item.append(el("span", "load-step-name", STEP_NAMES[p.step] || p.step));
  item.append(el("span", "", p.label_text));
  item.append(
    el("span", "load-step-time", t("llm.step_time", { duration: duration(p.duration_ms), elapsed: duration(p.elapsed_ms) }))
  );
  $("loading-steps").append(item);
}

function renderLoadEnded(p) {
  stopLoadTimer();
  const status = text(`loading.status.${p.status}`) || p.status;
  $("loading-total").textContent = [
    text("loading.total_text", { modele: p.model.label, statut: status, duree: duration(p.duration_ms) }),
    p.reason_text,
  ]
    .filter(Boolean)
    .join(" ");
  const memory = $("loading-memory");
  memory.hidden = !p.memory;
  memory.textContent = p.memory?.where_text || "";
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
    $("loading-total").textContent = `${envelope.payload.phase_label} ${text("loading.running_text", {
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
    ? text("reasoning.always_text")
    : can
      ? ""
      : r.reason_text || "";
  toggle.title = can ? "" : r.reason_text || "";
  $("reasoning-budget").textContent = [
    r.budget_text,
    text("reasoning.reserve_text", { reserve: decimals().format(r.reserve), count: r.reserve }),
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

// The lanes read the token's decoded text by channel (tags dropped), never its bytes.
function laneToken(p) {
  for (const part of p.parts || []) {
    const lane = part.channel === "reasoning" ? $("lane-thinking") : $("lane-answer");
    lane.textContent += part.text;
  }
}

// ---------- increment 4: the candidates of each token ----------

const percent = () => numberFormat({ style: "percent", maximumFractionDigits: 1 });

function renderCandidatesOffer() {
  const offer = store.candidates;
  if (!offer) return;
  const toggle = $("candidates-toggle");
  toggle.disabled = !offer.available;
  if (!offer.available) toggle.checked = false;
  $("candidates-toggle-box").classList.toggle("is-disabled", !offer.available);
  toggle.title = offer.reason_text || "";
  $("candidates-reason").textContent = offer.available ? text("candidates.help_text") : offer.reason_text;
}

function bindCandidates(chip, p) {
  chip.classList.add("has-candidates");
  chip.tabIndex = 0;
  chip.setAttribute("role", "button");
  chip.setAttribute("aria-haspopup", "dialog");
  const show = () => showCandidates(chip, p);
  chip.addEventListener("mouseenter", show);
  chip.addEventListener("focus", show);
  chip.addEventListener("mouseleave", () => store.pinned !== chip && hideCandidates());
  chip.addEventListener("blur", () => store.pinned !== chip && hideCandidates());
  const toggle = () => {
    store.pinned = store.pinned === chip ? null : chip;
    if (store.pinned) show();
    else hideCandidates();
    // Story 5 (2026-09-30): the token clicked is the one section 2 redraws.
    chooseDistributionToken(p.index);
  };
  chip.addEventListener("click", toggle);
  chip.addEventListener("keydown", (event) => {
    if (event.key === "Enter" || event.key === " ") {
      event.preventDefault();
      toggle();
    }
  });
}

function showCandidates(chip, p) {
  const box = $("candidates-popover");
  for (const other of document.querySelectorAll("[aria-describedby='candidates-popover']")) {
    other.removeAttribute("aria-describedby");
  }
  chip.setAttribute("aria-describedby", "candidates-popover");
  chip.setAttribute("aria-expanded", "true");
  $("candidates-title").textContent = text("candidates.title_text", { index: p.index + 1 });
  const list = $("candidates-list");
  list.replaceChildren();
  for (const c of p.candidates) {
    const row = el("li", "candidate");
    if (c.chosen) row.classList.add("is-chosen");
    if (!c.kept) row.classList.add("is-dropped");
    row.append(el("span", "candidate-text", quote(visibleBlanks(c.text))));
    const bar = el("span", "candidate-bar");
    const fill = el("span");
    fill.style.width = `${Math.max(0, Math.min(1, c.p)) * 100}%`;
    bar.append(fill);
    bar.setAttribute("aria-hidden", "true");
    row.append(bar, el("span", "candidate-p", percent().format(c.p)));
    const notes = [
      text("candidates.chance_text", { chance: percent().format(c.p_sampled) }),
      c.kept ? null : text("candidates.dropped_text"),
      c.chosen ? text("candidates.chosen_text") : null,
    ].filter(Boolean);
    row.append(el("span", "candidate-note", notes.join(" · ")));
    list.append(row);
  }
  box.hidden = false;
  const rect = chip.getBoundingClientRect();
  const width = box.offsetWidth;
  const left = Math.min(rect.left + window.scrollX, window.scrollX + document.documentElement.clientWidth - width - 16);
  box.style.left = `${Math.max(left, 16)}px`;
  box.style.top = `${rect.bottom + window.scrollY + 6}px`;
}

function hideCandidates() {
  $("candidates-popover").hidden = true;
  for (const chip of document.querySelectorAll(".token-chip[aria-expanded='true']")) {
    chip.setAttribute("aria-expanded", "false");
  }
}

// ---------- the journal ----------

function applyEnvelope(envelope) {
  store.lastSeq = envelope.seq;
  const p = envelope.payload;
  if (envelope.kind === "session_state") {
    store.session = { state: p.state, reason_text: p.reason_text };
    if (p.active_model !== undefined) store.activeModel = p.active_model;
    if (p.state === "llm_lab" || p.state === "model_load") {
      // Story 5 (2026-09-30): the session has just let go of the last generation's
      // candidates (a new one, or the engine released): nothing to ask until it says.
      store.dist.tokens = 0;
      renderDistributionIdle();
    }
    renderModel();
    renderBusy();
    return;
  }
  if (envelope.kind === "model_load_started") {
    renderLoadStarted(envelope);
    store.dist.tokens = 0; // the engine that read the candidates is being released
    renderDistributionIdle();
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
  // Story 5 (2026-09-30): a comparison's events, routed by `request_id` (`llm{n}.a`,
  // `llm{n}.b`; `step_id` for the model call's own). B fills its column only; A fills its
  // column and the sections as « Générer » does (its tokens are the live distribution's).
  const lane = compareLane(p.request_id || envelope.step_id);
  if (!lane && envelope.kind === "llm_generation_started") $("compare-lanes").hidden = true;
  if (lane) {
    compareEvent(lane, envelope.kind, p);
    if (lane === "b") {
      if (envelope.kind === "llm_generation_ended") {
        store.answered.add(p.request_id);
        if (store.pending.compare === p.request_id) {
          store.pending.compare = null;
          $("compare-status").textContent = "";
        }
        renderBusy();
      }
      return;
    }
  }
  switch (envelope.kind) {
    case "llm_tokenized":
      store.answered.add(p.request_id);
      if (store.pending.tokenize === p.request_id) store.pending.tokenize = null;
      renderTokenized(p);
      renderBusy();
      break;
    case "llm_generation_started":
      renderGenerationStarted(p);
      if (lane === "a") $("generate-status").textContent = ""; // the comparison says it runs
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
      cut.textContent = p.message_text;
      break;
    }
    case "model_call_ended":
      renderCallEnded(p);
      break;
    case "llm_generation_ended":
      store.answered.add(p.request_id);
      if (store.pending.generate === p.request_id) store.pending.generate = null;
      renderGenerationEnded(p);
      // A comparison's A: its end is written in its column, B is still to come.
      if (lane === "a") $("generate-status").textContent = "";
      renderBusy();
      break;
    case "harness_error":
      if (envelope.step_id) store.answered.add(envelope.step_id);
      if (envelope.step_id && envelope.step_id === store.pending.tokenize) {
        store.pending.tokenize = null;
        const status = $("tokenize-status");
        status.classList.add("is-error");
        status.textContent = [p.message_text, p.cause].filter(Boolean).join(" ");
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
    alert.textContent = t("llm.unavailable", { cause: error.message });
    return null;
  }
  store.content = body.content;
  // A late answer never takes the page back in time: the stream may already be further.
  if (body.seq >= store.lastSeq) {
    store.activeModel = body.active_model;
    store.session = body.session_state;
  }
  store.tokenizer = body.tokenizer;
  store.sampling = body.sampling;
  store.reasoning = body.reasoning;
  store.candidates = body.candidates;
  store.lastLoad = body.last_load;
  // Story 5 (2026-09-30): what the session keeps of the last generation (0 after a switch).
  store.dist.tokens = body.distribution?.tokens || 0;
  if (store.dist.index >= store.dist.tokens) store.dist.index = 0;
  const alert = $("llm-content-error");
  alert.hidden = !body.content_error_text;
  alert.textContent = body.content_error_text || "";
  renderContent();
  renderModel();
  renderTokenizerInfo();
  renderSampling();
  renderReasoning();
  renderCandidatesOffer();
  if (!store.load.timer) renderLastLoad();
  renderBusy();
  scheduleDistribution(0);
  return body;
}

async function main() {
  await textsReady; // the page's texts and formats in the session's language (languages 4/5)
  const prompt = $("llm-prompt");
  // The stream starts from the answer's `seq`: without it, retried, never the whole journal.
  let body = await refresh();
  while (!body) {
    await new Promise((resolve) => setTimeout(resolve, 2000));
    body = await refresh();
  }
  $("llm-content-error").hidden = !body.content_error_text;
  prompt.value = loadDraft() ?? (text("tokenization.default_text_text") || "");
  prompt.addEventListener("input", () => saveDraft(prompt.value));
  $("tokenize-button").addEventListener("click", tokenize);
  $("generate-button").addEventListener("click", generate);
  $("stop-button").addEventListener("click", stopGeneration);
  $("sampling-reset").addEventListener("click", resetSampling);
  $("compare-button").addEventListener("click", compareRun);
  document.addEventListener("keydown", (event) => {
    // Story 2 (2026-09-30): an Escape that closed « Affichage ▾ » (site-nav.js) stops there.
    if (event.key === "Escape" && !event.defaultPrevented) {
      store.pinned = null;
      hideCandidates();
    }
  });
  store.lastSeq = body.seq;
  document.body.dataset.labReady = "true";
  streamEvents();
}

main();
