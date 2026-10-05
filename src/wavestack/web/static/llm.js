// Story 29: the « LLM nu » screen. Everything it shows comes from `GET /api/llm_lab` or
// from an event of the journal (AD-1): the page counts no token and computes no rate, no
// probability, no size; it lays them out, shows blanks (␣, ↵) and runs a local stopwatch
// anchored on a `*_started` event, replaced by its `*_ended`.
//
// Languages (4/5): the page's own texts come from `content/ui.yaml` (section `llm`) through
// `t()`, its formats from the language (`i18n.js`); the screen's texts stay those of
// `content/llm_lab.yaml`, read in the session's language by `GET /api/llm_lab`.

import { createStepper, explain, light, svgEl } from "./diagram.js";
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
  // compare: `llm{n}.b`, story 5; step: `llm{n}.step`, lot 6 (the OUTPUT's draw)
  pending: { tokenize: null, generate: null, compare: null, step: null },
  sampling: null, // `lab_state().sampling`: defaults, bounds, what can be set
  values: null, // the sliders' values, sent with « Générer »
  gen: { callTs: null, timer: null, first: false, cloud: false, texts: [] },
  reasoning: null, // `lab_state().reasoning`: mode, reason, budget, reserve
  candidates: null, // `lab_state().candidates`: available, reason, n
  pinned: null, // the chip whose candidates a click keeps open
  lastLoad: [], // the envelopes of the last model load
  load: { timer: null },
  // The requests already answered by an event: the answer may come before the POST's own.
  answered: new Set(),
  // Story 5 (2026-09-30): the live distribution (lot 6: in the OUTPUT). `index`: the token chosen in
  // the last generation; `tokens`: how many the session keeps (`lab_state().distribution`,
  // then the `llm_token` events); `ticket`: the last request sent (the last answer wins).
  // Lot 6: `source`, whose token it is, a generation's (section 6) or the OUTPUT's step.
  // `stepped`: a step ran since the last generation (its chips no longer pick a token).
  dist: { index: 0, tokens: 0, ticket: 0, timer: null, source: "generation", stepped: false },
  valuesB: null, // the comparison's settings B, as `values`
  win: { reserve: 0, reserveText: "" }, // the window diagram's output reserve (section 5)
  // Lot 6 (2026-10-04): the three stages. `tokenized`: the last `llm_tokenized`; `step`: the
  // OUTPUT's draws (`added`: the tokens kept in the INPUT, for the text `forText`; `drawn`:
  // the last token the engine drew); `steppers`: one per stage; `transfo.last`: the step
  // drawn last (its vectors move to the next one's).
  tokenized: null,
  step: { added: [], forText: null, prompt: null, drawn: null, history: [], status: "", error: false },
  steppers: { input: null, transfo: null, output: null },
  transfo: { last: -1 },
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
  const pending = anyPending();
  for (const id of ["tokenize-button", "generate-button", "compare-button"]) {
    const button = $(id);
    button.disabled = Boolean(reason) || pending;
    button.title = reason || "";
  }
  // « Arrêter »: while the screen generates (class c, `/api/intentions/stop`).
  $("stop-button").disabled = store.session.state !== "llm_lab";
  renderStep(); // lot 6: « Tirer le token suivant » and its reason
}

// A request of the screen not answered yet (lot 6: the OUTPUT's step included).
function anyPending() {
  return Object.values(store.pending).some((id) => id !== null);
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
  if (store.steppers.input) {
    renderInput();
    renderTransfo();
    showOutputStep(store.steppers.output.index);
  }
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

// ---------- lot 6 (2026-10-04): stage 1, INPUT (real) ----------
//
// The text cut by the model's tokenizer (`llm_tokenized`), one column per token read down:
// its piece of text, its token, its id. The tokens the OUTPUT drew and the trainer added
// follow, as « produit » columns. A stepper of three steps: the text in one block, then cut
// into tokens, then their ids.

const INPUT_STEPS = ["text", "tokens", "ids"];

// A template of llm_lab.yaml whose `{name}` may be a node (a big figure): text and nodes.
function richText(path, values = {}) {
  let value = store.content;
  for (const key of path.split(".")) value = value?.[key];
  if (value !== null && typeof value === "object" && typeof values.count === "number") {
    value = value[pluralSelect(values.count)] ?? value.other;
  }
  if (typeof value !== "string") return [];
  return value.split(/(\{\w+\})/).map((part) => {
    const name = /^\{(\w+)\}$/.exec(part)?.[1];
    if (!name) return part;
    const shown = values[name];
    return shown instanceof Node ? shown : String(shown ?? "");
  });
}

// The tokens the INPUT shows: the text's (exact tokenization only), then the ones added.
function inputTokens() {
  const p = store.tokenized;
  const own = p?.exact ? p.tokens : [];
  return [...own, ...store.step.added.map((token) => ({ ...token, produced: true }))];
}

function inputColumn(token, index) {
  const column = el("li", "token-chip");
  column.dataset.parity = index % 2 ? "odd" : "even";
  if (token.produced) column.classList.add("is-produced");
  // The piece of text as typed: only the line breaks and tabs made visible (one line).
  const piece = el("span", "llm-input-seg", token.text.replace(/[\n\r\t]/g, (c) => BLANKS[c]));
  const arrow = () => {
    const node = el("span", "llm-input-arrow");
    node.setAttribute("aria-hidden", "true");
    return node;
  };
  const chip = el("span", "token-chip-text", visibleBlanks(token.text));
  const id = el("span", "llm-input-id");
  id.append(el("span", "token-chip-id", String(token.id)));
  if (token.special) {
    column.classList.add("is-special");
    id.append(el("span", "token-chip-special", text("tokenization.special_text") || t("llm.special")));
    column.title = text("tokenization.special_help_text");
  }
  for (const part of [piece, chip, id]) part.setAttribute("aria-hidden", "true");
  column.append(piece, arrow(), chip, arrow(), id);
  const label = token.produced ? "stages.input.produced_label_text" : "stages.input.column_label_text";
  column.setAttribute(
    "aria-label",
    text(label, { texte: shownToken(token), token: visibleBlanks(token.text), id: String(token.id) })
  );
  return column;
}

// One counter on the right: its figure big, its words after it (« 5 tokens »).
function inputCount(path, values, figure, key) {
  const line = el("p", "llm-input-count");
  line.dataset.count = key;
  line.append(...richText(path, { ...values, n: el("b", "", figure) }));
  return line;
}

function renderInput() {
  const p = store.tokenized;
  const list = $("token-chips");
  const counts = $("token-counts");
  const more = $("token-more");
  const tokens = inputTokens();
  list.replaceChildren(...tokens.map(inputColumn));
  counts.replaceChildren();
  $("token-empty").hidden = Boolean(tokens.length) || Boolean(p && !p.exact);
  if (!p) {
    counts.hidden = true;
    more.hidden = true;
    $("token-blanks").hidden = true;
  } else if (!p.exact) {
    // A cloud model: its tokenizer is at its provider, no column; the harness's estimate.
    counts.hidden = false;
    counts.append(
      el(
        "p",
        "llm-input-estimate",
        text("tokenization.estimate_text", {
          estimation_phrase: text("tokenization.token_noun", { n: p.figures_text.estimate, count: p.estimate }),
          caracteres_phrase: text("tokenization.character_noun", {
            n: p.figures_text.char_count,
            count: p.char_count,
          }),
          ratio: p.figures_text.chars_per_token,
        })
      )
    );
    more.hidden = true;
    $("token-blanks").hidden = true;
  } else {
    // The session's figures (AD-1): the tokens and characters of the text, the ids' range.
    const figures = p.figures_text;
    const maxId = p.dimensions?.figures_text?.max_id;
    counts.hidden = false;
    counts.append(
      inputCount("tokenization.token_noun", { count: p.token_count }, figures.token_count, "tokens"),
      inputCount("tokenization.character_noun", { count: p.char_count }, figures.char_count, "chars"),
      maxId
        ? inputCount("stages.input.ids_count_text", { count: p.token_count, max: maxId }, figures.token_count, "ids")
        : inputCount("stages.input.ids_unknown_text", { count: p.token_count }, figures.token_count, "ids")
    );
    // The tokens the OUTPUT added: counted apart, the session's figures unchanged.
    const added = store.step.added.length;
    if (added) counts.append(inputCount("stages.input.added_text", { count: added }, decimals().format(added), "tokens"));
    more.hidden = !p.more;
    more.textContent = p.more ? text("tokenization.more_text", { reste: figures.more, count: p.more }) : "";
    $("token-blanks").hidden = !p.tokens.length;
  }
  // The begin-of-text token the OUTPUT's step reads before these tokens, when the model
  // asks one (Gemma, Llama): named by the session, never one of the columns.
  const bos = $("token-bos");
  const bosToken = p?.exact ? p.bos_token : null;
  bos.hidden = !bosToken;
  bos.replaceChildren(
    ...(bosToken ? richText("stages.input.bos_text", { bos: el("code", "token-bos-text", visibleBlanks(bosToken)) }) : [])
  );
  showInputStep(store.steppers.input?.index ?? 0);
}

function renderTokenized(p) {
  const status = $("tokenize-status");
  status.classList.remove("is-error");
  status.textContent = "";
  store.tokenized = p;
  $("token-info").textContent = p.exact ? p.tokenizer_text : p.unavailable_text || p.tokenizer_text;
  renderInput();
  store.steppers.input?.show(0); // « Découper en tokens » opens the first step: the text
  renderTransfo();
  renderStep();
}

// The INPUT's step `index`: the columns cut apart from step 2, the ids shown at step 3.
function showInputStep(index) {
  const box = $("llm-input");
  box.classList.toggle("is-cut", index >= 1);
  box.classList.toggle("show-tokens", index >= 1);
  box.classList.toggle("show-ids", index >= 2);
  const labels = box.querySelectorAll(".llm-input-rows span");
  labels.forEach((label, k) => label.classList.toggle("is-dim", (k >= 1 && index < 1) || (k >= 3 && index < 2)));
  for (const count of $("token-counts").querySelectorAll(".llm-input-count")) {
    const dim = (count.dataset.count === "tokens" && index < 1) || (count.dataset.count === "ids" && index < 2);
    count.classList.toggle("is-dim", dim);
  }
  $("token-bos").classList.toggle("is-dim", index < 1); // read with the tokens, from step 2
  const step = INPUT_STEPS[Math.max(0, index)];
  caption($("input-caption"), `stages.input.steps.${step}`);
}

// A stage's caption: the step's title in bold, then its text.
function caption(node, path, values = {}) {
  node.replaceChildren();
  const title = text(`${path}.title_text`, values);
  if (title) node.append(el("strong", "", title), " ");
  node.append(text(`${path}.text_text`, values));
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

// ---------- lot 6 (2026-10-04): stage 2, TRANSFORMATION (illustrative) ----------
//
// Drawn in SVG on a handful of tokens (the last 5 of the INPUT) and 8 numbers per vector,
// seeded pseudo-random states (the same text, the same drawing): the engine exposes neither
// the attention weights nor the hidden states, which the note under the canvas says. Only
// the panel's dimensions are read (`llm_tokenized.dimensions`, AD-1), and the banner of a
// hybrid or a mixture of experts (`dimensions.architecture`, D4).

const TRANSFO_STEPS = [
  { key: "embed", state: 0, layer: -1 },
  { key: "attention", state: 1, layer: 0 },
  { key: "mlp", state: 2, layer: 0 },
  { key: "attention_2", state: 3, layer: 1 },
  { key: "mlp_2", state: 4, layer: 1 },
  { key: "skip", state: 5, layer: "last" },
  { key: "final", state: 5, layer: "end" },
];
const DRAWN_TOKENS = 5; // the last tokens drawn
const DRAWN_NUMBERS = 8; // the numbers drawn per vector
// The last token's attention over five tokens, layer 1 then layer 2 (other weights), and the
// hidden neurons lit by each layer's MLP: illustrative, as the note says.
const ATTENTION_FIVE = [
  [0.06, 0.44, 0.14, 0.24, 0.12],
  [0.3, 0.08, 0.36, 0.1, 0.16],
];
const LIT_NEURONS = [
  [2, 5, 6, 11, 13],
  [0, 4, 8, 9, 14],
];
const CELL = 15; // a vector's cell, in the viewBox's units
const VECTOR_Y = 262; // the vectors' top
const integerPercent = () => numberFormat({ style: "percent", maximumFractionDigits: 0 });

function seeded(seed) {
  let state = seed >>> 0 || 7;
  return () => {
    state = (Math.imul(state, 1664525) + 1013904223) >>> 0;
    return state / 4294967296;
  };
}

// What the TRANSFORMATION draws: its tokens (the INPUT's last ones, or the example's), the
// figures read, the architecture, and the illustrative states and weights.
function transfoModel() {
  const p = store.tokenized;
  const real = inputTokens();
  const example = !real.length;
  const all = example
    ? (store.content?.stages?.transfo?.example_tokens || []).map((piece) => ({ text: piece, id: null }))
    : real;
  const tokens = all.slice(-DRAWN_TOKENS);
  const seed = tokens.reduce((s, token) => (Math.imul(s, 31) + (token.id ?? token.text.length) + 1) >>> 0, 7);
  const random = seeded(seed);
  const n = tokens.length;
  const states = [
    tokens.map(() => Array.from({ length: DRAWN_NUMBERS }, () => random() * 2 - 1)),
  ];
  for (let s = 1; s <= 5; s += 1) {
    states.push(states[s - 1].map((v) => v.map((x) => Math.max(-1, Math.min(1, 0.55 * x + 0.45 * (random() * 2 - 1))))));
  }
  const layerWeights = (layer) => {
    if (n === ATTENTION_FIVE[layer].length) return ATTENTION_FIVE[layer];
    const raw = tokens.map((_, i) => (i === n - 1 ? 0.6 : 0.2 + random()));
    const total = raw.reduce((a, b) => a + b, 0) || 1;
    return raw.map((w) => w / total);
  };
  const weights = layerWeights(0);
  const weights2 = layerWeights(1);
  const dims = p?.exact ? p.dimensions : null;
  return {
    tokens,
    example,
    dims,
    figures: dims?.figures_text || {},
    arch: dims?.architecture || null,
    label: p?.model_label || store.activeModel?.label || "",
    states,
    weights,
    weights2,
  };
}

const shownToken = (token) => quote(token.text.trim() || visibleBlanks(token.text));

// The step's text, its figures and tokens placed.
function transfoText(step, model) {
  const s = (path, values) => text(`stages.transfo.${path}`, values);
  const n = model.tokens.length;
  const last = model.tokens[n - 1];
  let body;
  if (step.key === "attention" && n < 2) {
    body = s("attention_alone_text", { dernier: last ? shownToken(last) : "" });
  } else if (step.key === "attention") {
    const target = model.weights.slice(0, n - 1).reduce((best, w, i, all) => (w > all[best] ? i : best), 0);
    body = s("steps.attention.text_text", { dernier: shownToken(last), cible: shownToken(model.tokens[target]) });
  } else if (step.key === "skip" && !model.figures.layer_count) {
    body = s("skip_unknown_text");
  } else {
    body = s(`steps.${step.key}.text_text`, { couches: model.figures.layer_count || "" });
  }
  if ((step.key === "mlp" || step.key === "mlp_2") && isMoe(model.arch)) body += ` ${s("moe_mlp_text")}`;
  return body;
}

// Six expert numbers spread evenly below the model's count (a fixed list when unknown).
function expertNumbers(count) {
  if (!count) return [3, 17, 42, 66, 90, 121];
  return Array.from({ length: 6 }, (_, e) => Math.floor(((e + 0.5) * count) / 6));
}

const isMoe = (arch) => Boolean(arch && (arch.family === "moe" || (arch.expert_count || 0) > 1));

function svgText(x, y, value, className = "", anchor) {
  const node = svgEl("text", { x, y, class: className });
  if (anchor) node.setAttribute("text-anchor", anchor);
  node.textContent = value;
  return node;
}

// The canvas of step `step`: the tokens and ids at the top, the vectors at the bottom
// (`from`: the states to start from, moved to the step's by a CSS transition).
function drawTransfo(step, model, from) {
  const svg = $("transfo-svg");
  const unknown = text("vectorization.unknown_text") || t("llm.unknown");
  const label = (path, values) => text(`stages.transfo.labels.${path}`, values);
  const { tokens, figures } = model;
  const n = tokens.length;
  const width = figures.embedding_length || unknown;
  const vocab = figures.vocab_size || unknown;
  const parts = [];
  const defs = svgEl("defs");
  const marker = svgEl("marker", {
    id: "transfo-arrowhead",
    viewBox: "0 0 10 10",
    refX: 8,
    refY: 5,
    markerWidth: 7,
    markerHeight: 7,
    orient: "auto",
  });
  marker.append(svgEl("path", { class: "llm-transfo-arrowhead", d: "M0,0 L10,5 L0,10 z" }));
  defs.append(marker);
  parts.push(defs);
  const left = 160;
  const span = Math.min(100, 400 / Math.max(n - 1, 1));
  const X = (i) => left + i * span;
  const focus = step.key === "final";
  // Each text alone in its group, or over the shape it sits on: the contrast sweep reads it
  // against that shape only.
  const texts = svgEl("g");
  tokens.forEach((token, i) => {
    const shown = visibleBlanks(token.text);
    const w = Math.max(34, shown.length * 8.2 + 12);
    const chip = svgEl("g", focus && i < n - 1 ? { class: "is-faded" } : {});
    chip.append(
      svgEl("rect", {
        class: `llm-transfo-chip${i % 2 ? " is-odd" : ""}`,
        x: X(i) + CELL / 2 - w / 2,
        y: 6,
        width: w,
        height: 24,
        rx: 8,
      }),
      svgText(X(i) + CELL / 2, 23, shown, "t-code", "middle")
    );
    parts.push(chip);
    const id = svgEl("g", focus && i < n - 1 ? { class: "is-faded" } : {});
    id.append(svgText(X(i) + CELL / 2, 46, token.id === null ? "…" : String(token.id), "t-num t-soft", "middle"));
    parts.push(id);
  });
  texts.append(
    svgText(8, 23, label("tokens_text"), "t-label"),
    svgText(8, 46, label("ids_text"), "t-label"),
    svgText(8, VECTOR_Y + 10, label("vectors_text"), "t-label"),
    svgText(8, VECTOR_Y + 28, label("drawn_text", { n: decimals().format(DRAWN_NUMBERS) }), "t-soft"),
    svgText(8, VECTOR_Y + 44, label("of_text", { dimension: width }), "t-soft")
  );
  const last = n - 1;
  const lastX = X(last) + CELL / 2;
  if (step.key === "embed") {
    const table = svgEl("g");
    table.append(svgEl("rect", { class: "llm-transfo-table", x: 8, y: 66, width: 124, height: 140, rx: 6 }));
    for (let r = 0; r < 13; r += 1) {
      table.append(svgEl("line", { class: "llm-transfo-wire is-faint", x1: 8, x2: 132, y1: 76 + r * 10, y2: 76 + r * 10 }));
    }
    tokens.forEach((token, i) => {
      const row = 78 + (((token.id ?? token.text.length * 5) * 7) % 12) * 10;
      table.append(svgEl("rect", { class: "llm-transfo-row", x: 10, y: row - 3, width: 120, height: 6, rx: 2 }));
      table.append(
        svgEl("path", {
          class: "llm-transfo-wire is-dashed",
          d: `M132,${row} C${X(i) - 20},${row} ${X(i) + CELL / 2},${(row + VECTOR_Y) / 2} ${X(i) + CELL / 2},${VECTOR_Y - 10}`,
          "marker-end": "url(#transfo-arrowhead)",
        })
      );
    });
    parts.push(table);
    texts.append(
      svgText(10, 222, label("table_text"), "t-label"),
      svgText(10, 238, label("table_rows_text", { vocabulaire: vocab, dimension: width }), "t-soft")
    );
  } else if (step.key === "attention" || step.key === "attention_2") {
    const arcs = svgEl("g");
    const w = step.layer === 1 ? model.weights2 : model.weights; // layer 2: other weights
    tokens.forEach((_, i) => {
      if (i === last) return;
      const x1 = X(i) + CELL / 2;
      const h = 60 + (last - i) * 28;
      arcs.append(
        svgEl("path", {
          class: "llm-transfo-arc",
          d: `M${x1},${VECTOR_Y - 26} C${x1},${VECTOR_Y - 26 - h} ${lastX},${VECTOR_Y - 26 - h} ${lastX - 6},${VECTOR_Y - 8}`,
          "stroke-width": 1 + w[i] * 18,
        })
      );
      texts.append(svgText(x1, VECTOR_Y - 14, integerPercent().format(w[i]), "t-num", "middle"));
    });
    arcs.append(
      svgEl("path", {
        class: "llm-transfo-arc",
        d: `M${lastX - 4},${VECTOR_Y - 8} C${lastX - 22},${VECTOR_Y - 46} ${lastX + 22},${VECTOR_Y - 46} ${lastX + 4},${VECTOR_Y - 8}`,
        "stroke-width": 1 + w[last] * 18,
      })
    );
    parts.push(arcs);
    texts.append(svgText(lastX + 22, VECTOR_Y - 30, label("self_text", { p: integerPercent().format(w[last]) }), "t-num"));
    const heads = figures.head_count
      ? text("stages.transfo.panel.heads_text", { tetes: figures.head_count })
      : unknown;
    texts.append(svgText(8, 74, label("attention_text", { dernier: shownToken(tokens[last]), tetes: heads }), "t-soft"));
  } else if (step.key === "mlp" || step.key === "mlp_2") {
    const x0 = X(last) + CELL + 40;
    const xs = [x0, x0 + 95, x0 + 190];
    const hidden = 16;
    const ys = (k) => VECTOR_Y + 4 + (k + 0.5) * ((DRAWN_NUMBERS * 17 - 8) / DRAWN_NUMBERS);
    const yh = (k) => 112 + (k + 0.5) * (290 / hidden); // the hidden layer: wider than the vector
    const net = svgEl("g");
    if (isMoe(model.arch)) {
      const arch = model.arch.figures_text || {};
      texts.append(svgText(x0 - 10, 96, label("moe_title_text"), "t-label"));
      texts.append(
        svgText(
          x0 - 10,
          110,
          arch.expert_used_count
            ? label("moe_drawn_text", { actifs: arch.expert_used_count, experts: arch.expert_count })
            : label("moe_drawn_any_text", { experts: arch.expert_count || unknown }),
          "t-soft"
        )
      );
      expertNumbers(model.arch.expert_count).forEach((number, e) => {
        const on = e === 1 || e === 4;
        const y = 126 + e * 46;
        net.append(
          svgEl("path", {
            class: `llm-transfo-wire${on ? "" : " is-dashed is-faint"}`,
            d: `M${X(last) + CELL + 4},${VECTOR_Y + 68} L${x0 + 60},${y + 9}`,
          })
        );
        const expert = svgEl("g");
        expert.append(
          svgEl("rect", { class: `llm-transfo-expert${on ? " is-on" : ""}`, x: x0 + 60, y, width: 140, height: 18, rx: 5 }),
          svgText(x0 + 70, y + 13, label(on ? "expert_active_text" : "expert_text", { n: String(number) }), "t-soft")
        );
        parts.push(expert);
      });
      texts.append(svgText(8, 74, label("moe_note_text"), "t-soft"));
    } else {
      const lit = new Set(LIT_NEURONS[step.layer === 1 ? 1 : 0]); // layer 2: another network
      for (let i = 0; i < DRAWN_NUMBERS; i += 1) {
        for (let h = 0; h < hidden; h += 1) {
          net.append(svgEl("line", { class: "llm-transfo-synapse", x1: xs[0], y1: ys(i), x2: xs[1], y2: yh(h) }));
          net.append(svgEl("line", { class: "llm-transfo-synapse", x1: xs[1], y1: yh(h), x2: xs[2], y2: ys(i) }));
        }
      }
      for (let i = 0; i < DRAWN_NUMBERS; i += 1) {
        net.append(svgEl("circle", { class: "llm-transfo-neuron", cx: xs[0], cy: ys(i), r: 5 }));
        net.append(svgEl("circle", { class: "llm-transfo-neuron", cx: xs[2], cy: ys(i), r: 5 }));
      }
      for (let h = 0; h < hidden; h += 1) {
        net.append(svgEl("circle", { class: `llm-transfo-neuron${lit.has(h) ? " is-on" : ""}`, cx: xs[1], cy: yh(h), r: 4.5 }));
      }
      net.append(
        svgEl("path", {
          class: "llm-transfo-wire",
          d: `M${X(last) + CELL + 4},${VECTOR_Y + 68} H${xs[0] - 9}`,
          "marker-end": "url(#transfo-arrowhead)",
        })
      );
      const mlp = mlpFigure(model, unknown);
      texts.append(
        svgText(xs[0] - 6, 84, label("mlp_title_text", { entree: decimals().format(DRAWN_NUMBERS), cachee: decimals().format(hidden) }), "t-label"),
        svgText(xs[0] - 6, 100, label("mlp_real_text", { mlp }), "t-soft"),
        svgText(xs[0], VECTOR_Y - 12, label("input_text"), "t-soft", "middle"),
        svgText(xs[2], VECTOR_Y - 12, label("output_text"), "t-soft", "middle"),
        svgText(8, 74, label("mlp_note_text"), "t-soft")
      );
    }
    parts.push(net);
  } else if (step.key === "skip") {
    const stack = svgEl("g");
    for (let k = 5; k >= 0; k -= 1) {
      stack.append(
        svgEl("rect", {
          class: "llm-transfo-layer",
          x: X(0) - 14 + k * 10,
          y: 96 + k * 18,
          width: X(last) - X(0) + CELL + 28,
          height: 34,
          rx: 8,
          opacity: (1 - k * 0.12).toFixed(2),
        })
      );
    }
    parts.push(stack);
    const layersLabel = svgEl("g");
    layersLabel.append(
      svgText(
        X(0),
        84,
        figures.layer_count ? label("layers_text", { couches: figures.layer_count }) : label("layers_unknown_text"),
        "t-num"
      )
    );
    parts.push(layersLabel);
  } else if (step.key === "final") {
    const out = svgEl("g");
    out.append(
      svgEl("path", {
        class: "llm-transfo-wire",
        d: `M${lastX},${VECTOR_Y + DRAWN_NUMBERS * 17 + 4} V414`,
        "marker-end": "url(#transfo-arrowhead)",
      })
    );
    parts.push(out);
    texts.append(svgText(lastX - 14, 412, label("final_text", { vocabulaire: vocab }), "t-num", "end"));
  }
  parts.push(texts);
  // The vectors: drawn with the states to start from, then moved to the step's.
  const cells = [];
  const now = model.states[step.state];
  tokens.forEach((_, i) => {
    const group = svgEl("g", focus && i < last ? { class: "is-faded" } : {});
    group.append(
      svgEl("rect", {
        class: `llm-transfo-frame${focus && i === last ? " is-focus" : ""}`,
        x: X(i) - 3,
        y: VECTOR_Y - 3,
        width: CELL + 6,
        height: DRAWN_NUMBERS * 17 + 3,
        rx: 4,
      })
    );
    for (let d = 0; d < DRAWN_NUMBERS; d += 1) {
      const v = (from || now)[i][d];
      const cell = svgEl("rect", {
        class: `llm-transfo-cell ${v >= 0 ? "is-positive" : "is-negative"}`,
        x: X(i),
        y: VECTOR_Y + d * 17,
        width: CELL,
        height: CELL,
        rx: 2,
        "fill-opacity": (0.15 + Math.abs(v) * 0.85).toFixed(2),
      });
      cells.push([cell, i, d]);
      group.append(cell);
    }
    parts.push(group);
  });
  svg.replaceChildren(...parts);
  if (from) {
    requestAnimationFrame(() =>
      requestAnimationFrame(() => {
        for (const [cell, i, d] of cells) {
          const v = now[i][d];
          cell.setAttribute("class", `llm-transfo-cell ${v >= 0 ? "is-positive" : "is-negative"}`);
          cell.setAttribute("fill-opacity", (0.15 + Math.abs(v) * 0.85).toFixed(2));
        }
      })
    );
  }
}

// « 2 048 → 6 144 → 2 048 », or a mixture of experts' « 128 experts de 2 048 → 768 → 2 048,
// 8 actifs par token » (figures received; « inconnue » for what is not read).
function mlpFigure(model, unknown) {
  const s = (path, values) => text(`stages.transfo.panel.${path}`, values);
  const arch = model.arch?.figures_text || {};
  const dimension = model.figures.embedding_length || unknown;
  const largeur = arch.feed_forward_length || unknown;
  if (isMoe(model.arch)) {
    return arch.expert_used_count
      ? s("moe_text", { experts: arch.expert_count, dimension, largeur, actifs: arch.expert_used_count })
      : s("moe_any_text", { experts: arch.expert_count || unknown, dimension, largeur });
  }
  return s("mlp_text", { dimension, largeur });
}

// The panel: « En vrai, pour {modèle} », the stack of layers, the banner, the note.
function renderTransfoPanel(step, model) {
  const s = (path, values) => text(`stages.transfo.panel.${path}`, values);
  const unknown = text("vectorization.unknown_text") || t("llm.unknown");
  const { figures, arch } = model;
  const archFigures = arch?.figures_text || {};
  const width = figures.embedding_length || unknown;
  const vocab = figures.vocab_size || unknown;
  const heads = !figures.head_count
    ? unknown
    : archFigures.kv_head_count
      ? s("heads_kv_text", { tetes: figures.head_count, kv: archFigures.kv_head_count })
      : s("heads_text", { tetes: figures.head_count });
  const mlp = mlpFigure(model, unknown);
  const facts = $("transfo-facts");
  const title = el("p", "llm-transfo-facts-title", s("facts_title_text", { modele: model.label || unknown }));
  // No dimension read (a cloud model): one line says so, not « inconnue » in every fact.
  if (!figures.embedding_length && !figures.vocab_size && !figures.layer_count) {
    facts.replaceChildren(title, el("p", "", s("unknown_text")));
  } else facts.replaceChildren(
    title,
    el("p", "", s("width_text", { dimension: width })),
    el(
      "p",
      "",
      figures.embedding_params
        ? s("table_text", { vocabulaire: vocab, dimension: width, parametres: figures.embedding_params })
        : s("table_only_text", { vocabulaire: vocab, dimension: width })
    ),
    el(
      "p",
      "",
      figures.layer_count
        ? s("layers_text", { couches: figures.layer_count, tetes: heads, mlp })
        : s("layers_unknown_text", { tetes: heads, mlp })
    )
  );
  // The stack: one bar per layer; a hybrid's full-attention layers solid, the others dashed.
  const layers = model.dims?.layer_count || 0;
  const interval = arch?.family === "hybrid" ? arch.attention_interval : null;
  const at = step.layer === -1 ? -1 : step.layer === "last" || step.layer === "end" ? layers - 1 : step.layer;
  const stack = $("transfo-stack");
  stack.replaceChildren(
    ...Array.from({ length: layers }, (_, k) => {
      const bar = el("i");
      if (interval && (k + 1) % interval !== 0) bar.classList.add("is-rec");
      if (k < at || (k === at && step.layer === "end")) bar.classList.add("is-done");
      if (k === at && step.layer !== "end") bar.classList.add("is-now");
      return bar;
    })
  );
  const total = figures.layer_count;
  $("transfo-stack-legend").textContent = !layers
    ? s("stack_unknown_text")
    : at < 0
      ? s("stack_none_text")
      : step.layer === "end"
        ? s("stack_done_text", { couches: total })
        : s(interval ? "stack_hybrid_text" : "stack_now_text", { n: decimals().format(at + 1), couches: total });
  // D4: the banner of a hybrid or a mixture of experts, the reasons added up; never closed.
  const banner = $("transfo-banner");
  const b = (path, values) => text(`stages.transfo.${path}`, values);
  const reasons = [];
  if (arch?.family === "hybrid") {
    reasons.push(
      archFigures.attention_interval
        ? b("banner_hybrid_text", { modele: model.label, intervalle: archFigures.attention_interval })
        : b("banner_hybrid_any_text", { modele: model.label })
    );
  }
  if (isMoe(arch)) {
    reasons.push(
      archFigures.expert_used_count
        ? b("banner_moe_text", { modele: model.label, actifs: archFigures.expert_used_count, experts: archFigures.expert_count })
        : b("banner_moe_any_text", { modele: model.label, experts: archFigures.expert_count || unknown })
    );
  }
  banner.hidden = !reasons.length;
  banner.replaceChildren();
  if (reasons.length) banner.append(el("strong", "", b("banner_title_text")), ` ${reasons.join(" ")}`);
  const p = store.tokenized;
  const unread = Boolean(p) && (!arch || arch.family === "unknown");
  $("transfo-unknown").hidden = !unread;
  $("transfo-unknown").textContent = unread ? b("unknown_architecture_text") : "";
  $("embedding-source").textContent = p ? (p.exact ? p.dimensions?.source_text : p.dimensions_text) || "" : "";
  const example = $("transfo-example");
  example.hidden = !model.example;
  example.textContent = model.example ? b("example_text") : "";
  $("transfo-note").textContent = b("note_text", { n: decimals().format(model.tokens.length), count: model.tokens.length });
}

function showTransfoStep(index) {
  const step = TRANSFO_STEPS[Math.max(0, index)];
  const model = transfoModel();
  const previous = TRANSFO_STEPS[store.transfo.last];
  const moving = previous && index === store.transfo.last + 1 && previous.state !== step.state;
  drawTransfo(step, model, moving && !reducedMotion() ? model.states[previous.state] : null);
  store.transfo.last = index;
  $("transfo-step-title").textContent = text(`stages.transfo.steps.${step.key}.title_text`);
  $("transfo-step-text").textContent = transfoText(step, model);
  renderTransfoPanel(step, model);
}

function renderTransfo() {
  store.transfo.last = -1; // a new drawing: nothing to move from
  showTransfoStep(store.steppers.transfo?.index ?? 0);
}

const reducedMotion = () => matchMedia("(prefers-reduced-motion: reduce)").matches;

// ---------- the sampling settings (lot 6: in the OUTPUT's Draw) ----------

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
// `changed()` called at each move (`prefix`: the fields' ids, `sampling` for the OUTPUT,
// `compare` for the comparison's settings B). Lot 6: `compact`, the OUTPUT's row on one line
// (name, slider, value), the name a button whose explanation shows on hover (`title`) and on
// a click, Enter or Space (diagram.js's `explain`, Escape closes it).
function samplingRow(name, values, prefix, changed, compact) {
  const sampling = store.sampling;
  const reason = sampling.supported[name];
  const row = el("div", "sampling-row");
  row.dataset.setting = name;
  const head = el("div", "sampling-row-head");
  const labelText = text(`sampling.settings.${name}.label_text`) || name;
  const label = el("label", "", labelText);
  const number = el("input");
  number.type = "number";
  number.id = `${prefix}-${name}`;
  label.htmlFor = number.id;
  const range = el("input");
  range.type = "range";
  range.setAttribute("aria-label", t("llm.slider", { label: labelText }));
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
  if (compact) {
    row.classList.add("is-compact");
    const help = text(`sampling.settings.${name}.help_text`);
    const button = el("button", "sampling-row-name");
    button.type = "button";
    button.title = help;
    const mark = el("span", "sampling-row-mark", "?");
    mark.setAttribute("aria-hidden", "true");
    button.append(labelText, " ", mark);
    number.setAttribute("aria-label", labelText);
    row.append(button);
    const popover = explain(button, help);
    if (popover) {
      popover.id = `${prefix}-${name}-help`;
      button.setAttribute("aria-describedby", popover.id);
      row.append(popover);
    }
    row.append(range, number);
  } else {
    head.append(label, number);
    row.append(head, range);
  }
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
      clearDrawn(); // lot 6: drawn with the previous settings
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
// Story 5 (2026-09-30): `values` the comparison's settings B, or the OUTPUT's by default.
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

// ---------- story 5 (2026-09-30): the live distribution, lot 6: the OUTPUT's Logits and Draw ----------
//
// The session keeps, for the last generation with the candidates (or the OUTPUT's last step),
// the most probable tokens of each token; at each move of a slider the page asks it
// (`POST /api/llm_lab/distribution`) which ones stay in the draw and their chance, for the
// settings shown (AD-1: the session computes, the page draws bars from the values received).
// Lot 6: the Logits draw their probabilities, the Draw their chances (the probability kept
// as a ghost bar), six words at most.

const DIST_ROWS = 6; // the bars shown; the others read are counted under them
const DIST_DEBOUNCE_MS = 80;

// Nothing to show: the reason the candidates are unavailable (a server, a cloud model), the
// session's answer (`detail`), or what to do.
function renderDistributionIdle(detail) {
  store.dist.ticket += 1; // an answer still in flight is stale: it draws nothing
  $("distribution-body").hidden = true;
  $("logits-body").hidden = true;
  const offer = store.candidates;
  const why = offer && !offer.available ? offer.reason_text : detail || text("distribution.empty_text");
  $("distribution-empty").textContent = why || "";
  $("logits-caption").textContent = text("stages.output.logits_start_text");
  $("distribution-token").textContent = "";
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

// The Logits' caption: what the model had read before the token (its last three tokens).
function logitsCaption() {
  let tail = "";
  if (store.dist.source === "step") {
    const tokens = inputTokens();
    tail = tokens.length
      ? tokens
          .slice(-3)
          .map((token) => token.text)
          .join("")
      : (store.step.prompt || "").slice(-24);
  } else {
    tail = store.gen.texts.slice(Math.max(0, store.dist.index - 3), store.dist.index).join("");
  }
  tail = tail.replace(/\s+/g, " ").trim();
  return tail ? text("stages.output.logits_text", { fin: tail }) : text("stages.output.logits_start_text");
}

function distText(value, className = "dist-text") {
  return el("span", className, visibleBlanks(value));
}

function renderDistribution(body) {
  const rows = body.candidates || [];
  if (!rows.length) {
    renderDistributionIdle();
    return;
  }
  $("distribution-empty").textContent = "";
  $("distribution-body").hidden = false;
  $("logits-body").hidden = false;
  $("logits-caption").textContent = logitsCaption();
  $("distribution-token").textContent =
    store.dist.source === "step"
      ? text("stages.output.step_token_text", { texte: quote(visibleBlanks(body.token_text)) })
      : text("distribution.token_text", {
          index: decimals().format(body.index + 1),
          texte: quote(visibleBlanks(body.token_text)),
        });
  const shown = rows.slice(0, DIST_ROWS);
  const probability = text("distribution.probability_text");
  const chance = text("distribution.chance_text");
  // The Logits: the model's probability of each word, then the rest of the vocabulary.
  const logits = $("logits-bars");
  logits.replaceChildren();
  for (const c of shown) {
    const row = el("li", "dist-row");
    if (c.text === body.token_text) row.classList.add("is-chosen");
    row.append(distText(c.text), distributionBar("is-model", c.p, percent().format(c.p), probability));
    logits.append(row);
  }
  const rest = el("li", "dist-row is-tail");
  rest.append(el("span", "dist-text", text("distribution.tail_text")));
  rest.append(distributionBar("is-model", body.tail, percent().format(body.tail), probability));
  rest.title = text("distribution.tail_help_text", {
    reste: percent().format(body.tail),
    lus: decimals().format(rows.length),
  });
  logits.append(rest);
  // The Draw: the same words in the same order, their chance of being drawn.
  const list = $("distribution-bars");
  list.replaceChildren();
  shown.forEach((c, i) => {
    const row = el("li", "dist-row");
    if (!c.kept) row.classList.add("is-dropped");
    if (c.text === body.token_text) row.classList.add("is-chosen");
    const why = body.dropped_by?.[i];
    const dropped = why ? text("stages.output.dropped_text", { reglage: why }) : text("distribution.dropped_text");
    row.append(distText(c.text));
    row.append(distributionBar("is-model", c.p, percent().format(c.p), probability));
    row.append(distributionBar("is-chance", c.p_sampled, c.kept ? percent().format(c.p_sampled) : dropped, chance));
    list.append(row);
  });
  // The rest of the vocabulary: its mass at temperature 1, never drawn here (approximate).
  const tail = el("li", "dist-row is-tail");
  tail.append(el("span", "dist-text", text("distribution.tail_text")));
  tail.append(distributionBar("is-model", body.tail, percent().format(body.tail), probability));
  tail.append(el("span", "dist-cell is-chance"));
  list.append(tail);
  const more = rows.length > DIST_ROWS ? text("distribution.more_text", { reste: decimals().format(rows.length - DIST_ROWS) }) : "";
  $("distribution-kept").textContent = [
    text("stages.output.kept_text", {
      gardes: decimals().format(body.kept_count),
      lus: decimals().format(rows.length),
      reste: percent().format(body.tail),
      count: body.kept_count,
    }),
    more,
  ]
    .filter(Boolean)
    .join(" ");
  markDistributionChip();
}

// The chip of section 6 whose candidates the OUTPUT shows (none for a step).
function markDistributionChip() {
  for (const chip of document.querySelectorAll("#generation-tokens .token-chip.is-dist-chosen")) {
    chip.classList.remove("is-dist-chosen");
  }
  if (store.dist.source !== "generation") return;
  const chip = document.querySelector(`#generation-tokens .token-chip[data-index="${store.dist.index}"]`);
  if (chip?.classList.contains("has-candidates")) chip.classList.add("is-dist-chosen");
}

function chooseDistributionToken(index) {
  // A step since that generation emptied the session's memory of its candidates: the chip's
  // popover (from its event) stays, the live distribution is no longer asked for it.
  if (store.dist.stepped) return;
  store.dist.source = "generation";
  store.dist.index = index;
  markDistributionChip();
  scheduleDistribution(0);
}

// ---------- lot 6 (2026-10-04): stage 3, OUTPUT: the token the engine draws ----------
//
// « Tirer le token suivant » asks the engine for one token (`POST /api/intentions/llm_step`):
// it reads the INPUT's text and the tokens already added, draws one with the OUTPUT's
// settings and reads its candidates. The page draws nothing: the token and its candidates
// come with `llm_token` (`llm{n}.step`). « Ajouter à la suite » keeps it in the INPUT,
// « Retirer le dernier » takes the last one back; a changed text erases them.

const OUTPUT_STEPS = ["logits", "draw", "token"];
const OUTPUT_PARTS = { logits: "part-logits", draw: "part-draw", token: "part-token" };
const STEP_LIMIT = 64; // as the session's `llm_lab.STEP_LIMIT`
const HISTORY = 8; // the last draws said

function showOutputStep(index) {
  const step = OUTPUT_STEPS[Math.max(0, index)];
  light($("stage-output"), $(OUTPUT_PARTS[step]));
  caption($("output-caption"), `stages.output.steps.${step}`);
}

// Why « Tirer » cannot be pressed now, else `null`.
function stepReason() {
  const busy = busyReason();
  if (busy) return busy;
  const offer = store.candidates;
  if (offer && !offer.available) return offer.reason_text;
  if (store.step.added.length >= STEP_LIMIT) return text("stages.output.limit_text");
  // The INPUT, the TRANSFORMATION and the Logits show the last text cut: the same one only.
  if (!store.tokenized || store.tokenized.text !== $("llm-prompt").value) {
    return text("stages.output.tokenize_first_text");
  }
  return null;
}

// A setting moved: the token drawn was drawn with the previous ones (the mockup's rule).
function clearDrawn() {
  if (!store.step.drawn) return;
  store.step.drawn = null;
  renderStep();
}

function renderStep() {
  const step = store.step;
  const reason = stepReason();
  const pending = anyPending();
  const draw = $("llm-step-button");
  draw.disabled = Boolean(reason) || pending;
  draw.title = reason || "";
  const drawn = $("llm-step-drawn");
  drawn.replaceChildren();
  if (step.drawn) {
    const chip = el("span", "llm-output-chip", visibleBlanks(step.drawn.text));
    chip.setAttribute("aria-label", t("llm.token_label", { text: quote(step.drawn.text), id: String(step.drawn.id) }));
    drawn.append(chip);
  } else {
    drawn.append(el("span", "llm-output-history", text("stages.output.none_text")));
  }
  $("llm-step-append").disabled = !step.drawn || step.drawn.id === null || pending || step.added.length >= STEP_LIMIT;
  $("llm-step-undo").disabled = !step.added.length || pending;
  // « sans gabarit »: said only where a step can be drawn (not a server, not a cloud model).
  $("llm-step-raw").hidden = Boolean(store.candidates && !store.candidates.available);
  $("llm-step-history").textContent = step.history.length
    ? text("stages.output.history_text", { tirages: step.history.map(visibleBlanks).join(" · ") })
    : "";
  const status = $("llm-step-status");
  status.classList.toggle("is-error", step.error);
  // The reason « Tirer » is greyed (a server, a cloud model), unless a status says more.
  status.textContent = step.status || (pending ? "" : reason || "");
}

function setStepStatus(message, error = false) {
  store.step.status = message || "";
  store.step.error = Boolean(message) && error;
  renderStep();
}

async function drawStep() {
  const prompt = $("llm-prompt").value;
  if (!prompt.trim()) {
    setStepStatus(t("llm.empty_prompt"), true);
    return;
  }
  store.pending.step = "…";
  setStepStatus(text("stages.output.running_text"));
  renderBusy();
  const answer = await post("/api/intentions/llm_step", {
    prompt,
    continuation: store.step.added.map((token) => token.id),
    sampling: samplingToSend(),
  });
  if (!answer.ok) {
    store.pending.step = null;
    setStepStatus(refusalText(answer), true);
    renderBusy();
    return;
  }
  const id = answer.body.request_id;
  store.step.forText = prompt;
  store.step.prompt = prompt;
  store.pending.step = store.answered.has(id) ? null : id;
  renderBusy();
}

// The OUTPUT's distribution no longer matches the INPUT (a token added or taken back, the
// text changed): nothing shown until the next draw (the session's memory is left as is).
function forgetStepDistribution() {
  if (store.dist.source !== "step") return;
  store.dist.tokens = 0;
  renderDistributionIdle();
}

function inputChanged() {
  renderInput();
  renderTransfo();
  forgetStepDistribution();
  renderStep();
}

function appendStep() {
  const drawn = store.step.drawn;
  if (!drawn || drawn.id === null || store.step.added.length >= STEP_LIMIT) return;
  if (store.step.prompt !== $("llm-prompt").value) return; // drawn for another text
  store.step.added.push({ id: drawn.id, text: drawn.text });
  store.step.forText = $("llm-prompt").value;
  store.step.drawn = null;
  store.step.history = [];
  store.step.status = "";
  inputChanged();
  store.steppers.input?.follow(); // the ids shown: « le modèle ne voit que ça »
  store.steppers.output?.show(0);
  $("stage-input").scrollIntoView({ behavior: reducedMotion() ? "auto" : "smooth", block: "start" });
}

function undoStep() {
  if (!store.step.added.length) return;
  store.step.added.pop();
  store.step.drawn = null;
  store.step.history = [];
  store.step.status = "";
  inputChanged();
}

// A text changed in the INPUT: what was added and drawn belonged to the old one.
function clearSteps() {
  if (!store.step.added.length && !store.step.drawn && !store.step.history.length) return;
  store.step.added = [];
  store.step.drawn = null;
  store.step.history = [];
  store.step.status = "";
  store.step.forText = null;
  inputChanged();
}

// The events of a step (`llm{n}.step`): its token and candidates in the OUTPUT only, as the
// comparison's B fills its column only.
function stepEvent(kind, p) {
  if (kind === "llm_generation_started") {
    store.step.drawn = null;
    store.step.prompt = p.prompt;
    store.dist.stepped = true; // the session forgot the last generation's candidates
  } else if (kind === "llm_token") {
    // Drawn for a text edited since: never shown, never added to the new one.
    if (store.step.prompt !== $("llm-prompt").value) return;
    store.step.drawn = { id: p.token_id, text: p.text };
    store.step.history = [p.text, ...store.step.history].slice(0, HISTORY);
    store.step.status = "";
    if (p.candidates?.length && store.candidates?.available) {
      store.dist.source = "step";
      store.dist.index = p.index;
      store.dist.tokens = p.index + 1;
      scheduleDistribution(0);
    }
    store.steppers.output?.show(OUTPUT_STEPS.length - 1);
    renderStep();
  } else if (kind === "llm_generation_ended") {
    store.answered.add(p.request_id);
    if (store.pending.step === p.request_id) store.pending.step = null;
    if (p.status === "error") setStepStatus([text("generation.status.error"), p.message_text].filter(Boolean).join(" "), true);
    else if (p.status === "cancelled" && !store.step.drawn) setStepStatus(text("generation.status.cancelled"));
    else if (!store.step.drawn) setStepStatus(p.message_text || text("stages.output.end_text"));
    else setStepStatus("");
    renderBusy();
  }
}

// ---------- story 5 (2026-09-30): the comparison A/B of section 6 ----------

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

// ---------- story 5 (2026-09-30): the window diagram of section 5 ----------
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

// ---------- sections 5 and 6: the prompt's reading, the generation token by token ----------

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
  store.dist.source = "generation";
  store.dist.stepped = false;
  store.dist.index = 0;
  store.dist.tokens = 0;
  store.gen.texts = [];
  renderDistributionIdle();
}

function renderToken(p) {
  store.gen.first = true;
  store.gen.texts[p.index] = p.text; // lot 6: the Logits' caption (« après … »)
  windowToken(p);
  if (p.candidates?.length && store.candidates?.available && store.dist.source === "generation") {
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

// ---------- section 4: the model's load ----------

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

// ---------- section 7: reasoning ----------

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
    // Story 5 (2026-09-30): the token clicked is the one the OUTPUT redraws.
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
    clearSteps(); // lot 6: the ids added are another vocabulary's
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
  // Lot 6 (2026-10-04): the OUTPUT's step (`llm{n}.step`), in the OUTPUT only.
  if (/\.step$/.test(p.request_id || envelope.step_id || "")) {
    stepEvent(envelope.kind, p);
    return;
  }
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

// Lot 6: one stepper per stage, in its head, over fixed steps (built once the texts are read:
// `createStepper` reads its labels when it is built). INPUT and TRANSFORMATION end on « Tout
// montrer », the OUTPUT on « Suivre le direct ».
function buildSteppers() {
  const make = (id, steps, onShow, liveText) => {
    const stepper = createStepper($(id), { onShow: (_, index) => onShow(index), liveText });
    for (const step of steps) stepper.push(step);
    stepper.show(0);
    return stepper;
  };
  const all = text("stages.show_all_text") || undefined;
  store.steppers.input = make("input-stepper", INPUT_STEPS, showInputStep, all);
  store.steppers.transfo = make("transfo-stepper", TRANSFO_STEPS, showTransfoStep, all);
  store.steppers.output = make("output-stepper", OUTPUT_STEPS, showOutputStep);
  renderInput();
  renderTransfo();
  renderStep();
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
  prompt.addEventListener("input", () => {
    saveDraft(prompt.value);
    // Lot 6: the tokens added and drawn belonged to the text they were drawn for.
    if (store.step.forText !== null && prompt.value !== store.step.forText) clearSteps();
    renderStep(); // « Tirer » waits for this text's tokens
  });
  buildSteppers();
  $("tokenize-button").addEventListener("click", tokenize);
  $("llm-step-button").addEventListener("click", drawStep);
  $("llm-step-append").addEventListener("click", appendStep);
  $("llm-step-undo").addEventListener("click", undoStep);
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
