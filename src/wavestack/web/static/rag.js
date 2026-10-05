// Story 30: the RAG workshop. Everything it shows comes from `GET /api/rag_lab` or from a
// `rag_lab_*` event of the journal (AD-1): the catalog, the options' availability, the
// excerpts, their ranks and scores, the durations and the memory are built in Python. The
// page lays them out and runs no computation of its own.
//
// Lot 5a: one section, three views side by side (vues-atelier-rag.md): the sequence (BUILD
// then RUN, a line per step), the architecture (the components the chain calls on, by
// group) and the focus on one step, every step's detail folded under them. The table step →
// components is the session's (`catalog.steps`). In « Composer » the chain's editor lives in
// the sequence's lines; the A/B comparison is gone from the page.
//
// Lot 5a-2: in « Dérouler » the steps and the components arrive one by one, by a stepper
// (`diagram.createStepper`) whose frames are the sequence's steps: every step pushed for a
// guided tour without a run, else one frame per step the run reached (its `rag_lab_*` events,
// live). The frame shown lights its step and its components, its wires flow while it runs,
// the focus shows its figures; the steps and tiles after it keep their place, invisible.
//
// Languages (4/5): the page's own texts come from `content/ui.yaml` (section `rag`) through
// `t()`, its formats from the language (`i18n.js`); the workshop's texts stay those of
// `content/rag_lab.yaml`, read in the session's language by `GET /api/rag_lab`.

import { createStepper, light, svgEl, wire, wireLayer } from "./diagram.js";
import { numberFormat, ready as textsReady, t } from "./i18n.js";

const $ = (id) => document.getElementById(id);
const quote = (value) => t("common.format.quote", { text: value });

const store = {
  content: null,
  catalog: null,
  defaultPipeline: null,
  unavailable: null,
  session: { state: "diagnostic", reason_text: null },
  serverInstance: null,
  lastSeq: 0,
  pending: false, // a POST sent, not answered yet
  run: null, // the projection of the last run: its lanes and their stages
  pipelines: [], // the chain being edited (one: the A/B comparison is gone from the page)
  refusals: [], // why the session would refuse it (`POST /api/rag_lab/validate`)
  validating: 0, // the last validation asked, so that a late answer is dropped
  mode: "play", // « compose » or « play » (vues-atelier-rag.md §1)
  current: null, // the step shown in the focus (its key), or none
  replaying: false, // `last_run` being read again: one render at its end, not one per event
  land: false, // a run just ended: its stepper lands on its last frame, or its failed step
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

// « 1 536 » (narrow no-break space in French) and « 0,812 »: formatting only, in the
// session's language (read at each use: the language is known once `textsReady` resolved).
const fmtInt = (n) => (typeof n === "number" ? numberFormat().format(n) : "—");
// A fusion's score (1 / (60 + rank)) needs a fourth decimal to tell two apart.
const fmtScore = (x) => {
  if (typeof x !== "number") return "—";
  const digits = x > 0 && x < 0.1 ? 4 : 3;
  return numberFormat({ minimumFractionDigits: digits, maximumFractionDigits: digits, useGrouping: false }).format(x);
};
// « 1er », « 2ᵉ » (« No. 2 », « Nr. 2 »): a plural pair of the catalogue, by the rank.
const fmtRank = (n) => (typeof n === "number" ? t("rag.rank", { count: n }) : t("rag.rank_absent"));
const labelled = (label, value) => t("common.format.label_value", { label, value });

const QUESTION_KEY = "wavestack.ragLab.question";
const CHAINS_KEY = "wavestack.ragLab"; // the chain being edited (a browser setting only)
const MODE_KEY = "wavestack.ragLab.mode";
const MODES = ["compose", "play"];

function stored(key) {
  try {
    return localStorage.getItem(key);
  } catch {
    return null;
  }
}

function keep(key, value) {
  try {
    localStorage.setItem(key, value);
  } catch {
    // no storage (private window, blocked data): the value lives with the page
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

function refusalText(answer) {
  const detail = answer.body?.detail;
  if (typeof detail === "string") return detail;
  return answer.status ? t("common.refused_http", { status: String(answer.status) }) : t("common.unreachable");
}

// ---------- the chain ----------

function stageInfo(kind) {
  return store.catalog?.stages.find((s) => s.kind === kind) ?? null;
}

function optionInfo(kind, option) {
  return stageInfo(kind)?.options.find((o) => o.id === option) ?? null;
}

const clone = (value) => JSON.parse(JSON.stringify(value));

function chain() {
  return store.pipelines[0] ?? null;
}

// The chain remembered by the browser, when it still has the shipped chain's shape. A page
// of before lot 5a may have saved two (A and B): only A is kept.
function loadChains() {
  let saved = null;
  try {
    saved = JSON.parse(stored(CHAINS_KEY) || "null");
  } catch {
    saved = null;
  }
  // Only the shape the session accepts is checked here (a saved chain of an older page, or
  // edited by hand, falls back to the shipped one); the session says whether a chain runs.
  const only = (value, keys) =>
    value !== null && typeof value === "object" && !Array.isArray(value) && Object.keys(value).every((k) => keys.includes(k));
  const stageShaped = (s) =>
    only(s, ["id", "kind", "option", "params"]) &&
    typeof s.id === "string" &&
    /^[a-z0-9_]{1,16}$/.test(s.id) &&
    typeof s.kind === "string" &&
    typeof s.option === "string" &&
    (s.params === undefined || (only(s.params, Object.keys(s.params)) && Object.values(s.params).every(Number.isInteger)));
  const shaped = (p) =>
    only(p, ["label_text", "stages"]) &&
    (p.label_text === undefined || (typeof p.label_text === "string" && p.label_text.length >= 1 && p.label_text.length <= 40)) &&
    Array.isArray(p.stages) &&
    p.stages.length >= 1 &&
    p.stages.length <= 12 &&
    p.stages.every(stageShaped);
  // Languages (2/5): a chain saved before names its label `label_fr`; read as `label_text`.
  const renamed = (p) => {
    if (p === null || typeof p !== "object" || !("label_fr" in p) || "label_text" in p) return p;
    const { label_fr: label, ...rest } = p;
    return { label_text: label, ...rest };
  };
  const pipelines = Array.isArray(saved?.pipelines) ? saved.pipelines.slice(0, 1).map(renamed) : [];
  if (!pipelines.length || !pipelines.every(shaped)) return [clone(store.defaultPipeline)];
  return pipelines;
}

function saveChains() {
  keep(CHAINS_KEY, JSON.stringify({ pipelines: store.pipelines }));
}

function forgetChains() {
  try {
    localStorage.removeItem(CHAINS_KEY);
  } catch {
    // nothing stored
  }
}

function paramInput(stage, param) {
  const label = el("label", "rag-param");
  label.append(el("span", "rag-param-name", param.label_text));
  const input = el("input", "rag-param-input");
  input.type = "number";
  input.min = String(param.min);
  input.max = String(param.max);
  input.step = "1";
  input.value = String(stage.params?.[param.name] ?? param.default);
  input.dataset.lane = "a";
  input.dataset.stageId = stage.id;
  input.dataset.param = param.name;
  input.title = t("rag.param_range", { min: fmtInt(param.min), max: fmtInt(param.max), unit: param.unit_text }).trim();
  input.addEventListener("change", () => {
    const value = Number(input.value);
    stage.params = { ...(stage.params || {}) };
    if (input.value.trim() !== "" && Number.isInteger(value)) {
      stage.params[param.name] = value;
    } else {
      // A field cleared or not a whole number: the value the chain keeps, shown again.
      input.value = String(stage.params[param.name] ?? param.default);
    }
    saveChains();
    validateChains();
  });
  label.append(input, el("span", "rag-param-unit", param.unit_text));
  return label;
}

function optionSelect(stage, info) {
  const select = el("select", "rag-option");
  select.setAttribute("aria-label", t("rag.option_label", { stage: info.label_text }));
  select.dataset.lane = "a";
  select.dataset.stageId = stage.id;
  for (const option of info.options) {
    const item = el("option", null, option.available ? option.label_text : `${option.label_text} (${text("unavailable_text")})`);
    item.value = option.id;
    item.disabled = !option.available;
    if (option.reason_text) item.title = option.reason_text;
    select.append(item);
  }
  select.value = stage.option;
  select.addEventListener("change", () => {
    const option = info.options.find((o) => o.id === select.value);
    stage.option = select.value;
    // The option's own settings, at their shipped values.
    stage.params = Object.fromEntries((option?.params ?? []).map((p) => [p.name, p.default]));
    changed();
    document.querySelector(`select.rag-option[data-stage-id="${stage.id}"]`)?.focus();
  });
  return select;
}

// A chain stage's editor, in its line of the sequence (Composer): its option, its settings,
// what a run would meet, and ▲ ▼ Retirer for the retrieval segment.
function stageControls(stage, index) {
  const info = stageInfo(stage.kind);
  const option = optionInfo(stage.kind, stage.option);
  const box = el("div", "rag-seq-controls");
  if (info && info.options.length > 1) box.append(optionSelect(stage, info));
  else box.append(el("span", "rag-chain-option", option?.label_text ?? stage.option));
  for (const param of option?.params ?? []) box.append(paramInput(stage, param));
  if (info?.movable) box.append(moveButtons(index));
  if (option?.note_text) box.append(el("p", "rag-chain-note", option.note_text));
  for (const other of info?.options ?? []) {
    if (!other.available && other.reason_text) {
      box.append(el("p", "rag-chain-unavailable", labelled(other.label_text, other.reason_text)));
    }
  }
  return box;
}

// Increment 4: a stage of the retrieval segment moves by buttons (keyboard included), never
// by drag and drop, and can be removed; the session says whether the chain still runs.
function isMovable(stage) {
  return Boolean(stage && stageInfo(stage.kind)?.movable);
}

function moveButtons(index) {
  const stages = chain().stages;
  const box = el("div", "rag-chain-moves");
  const button = (label, symbol, action, disabled, onClick) => {
    const b = el("button", "rag-move-button", symbol);
    b.type = "button";
    b.setAttribute("aria-label", label);
    b.title = label;
    b.disabled = disabled;
    b.dataset.lane = "a";
    b.dataset.stageId = stages[index].id;
    b.dataset.action = action;
    b.addEventListener("click", onClick);
    return b;
  };
  const move = (delta) => () => {
    const [stage] = stages.splice(index, 1);
    stages.splice(index + delta, 0, stage);
    changed();
    const action = delta < 0 ? "before" : "after";
    const again = document.querySelector(`.rag-move-button[data-stage-id="${stage.id}"][data-action="${action}"]`);
    (again && !again.disabled ? again : document.querySelector(`#rag-seq [data-stage-id="${stage.id}"] .rag-move-button:not(:disabled)`))?.focus();
  };
  const remove = text("remove_text") || t("rag.remove");
  box.append(
    button(text("move_before_text") || t("rag.move_before"), "▲", "before", !isMovable(stages[index - 1]), move(-1)),
    button(text("move_after_text") || t("rag.move_after"), "▼", "after", !isMovable(stages[index + 1]), move(1)),
    button(remove, remove, "remove", false, () => {
      stages.splice(index, 1);
      changed();
      document.querySelector("#rag-palette-a select")?.focus();
    }),
  );
  return box;
}

function renderPalette() {
  const box = $("rag-palette-a");
  box.replaceChildren();
  const pipeline = chain();
  if (!pipeline || !store.catalog || store.mode !== "compose") return;
  const present = new Set(pipeline.stages.map((s) => s.kind));
  const absent = store.catalog.stages.filter((s) => s.movable && !present.has(s.kind));
  if (!absent.length) return;
  const label = el("label", "rag-palette-label");
  label.append(el("span", null, text("add_text") || t("rag.add")));
  const select = el("select", "rag-palette-select");
  for (const info of absent) {
    const option = el("option", null, info.label_text);
    option.value = info.kind;
    select.append(option);
  }
  label.append(select);
  const add = el("button", "rag-button-secondary rag-palette-add", text("add_button_text") || t("rag.add_button"));
  add.type = "button";
  add.addEventListener("click", () => {
    const info = store.catalog.stages.find((s) => s.kind === select.value);
    const choice = info?.options.find((o) => o.available) ?? info?.options[0];
    if (!info || !choice) return;
    const used = new Set(pipeline.stages.map((s) => s.id));
    let n = pipeline.stages.length + 1;
    while (used.has(`s${n}`)) n += 1;
    const stage = {
      id: `s${n}`,
      kind: info.kind,
      option: choice.id,
      params: Object.fromEntries(choice.params.map((p) => [p.name, p.default])),
    };
    const before = pipeline.stages.findIndex((s) => s.kind === store.catalog.insert_before);
    pipeline.stages.splice(before < 0 ? pipeline.stages.length : before, 0, stage);
    changed();
    document.querySelector("#rag-palette-a select")?.focus();
  });
  box.append(label, add);
}

function changed() {
  saveChains();
  redraw();
  validateChains();
}

// The session's verdict on the chain being edited, shown on the line at fault.
// Asked once the edits pause (a run's fields send several at once): one request, the last.
let validationTimer = null;
function validateChains() {
  clearTimeout(validationTimer);
  validationTimer = setTimeout(askValidation, 200);
}

async function askValidation() {
  const asked = ++store.validating;
  const answer = await post("/api/rag_lab/validate", { pipelines: store.pipelines });
  if (asked !== store.validating) return;
  if (answer.ok) {
    store.refusals = answer.body.refusals ?? [];
  } else if (answer.status === 422) {
    // A chain the session cannot even read: back to the shipped one.
    store.pipelines = [clone(store.defaultPipeline)];
    forgetChains();
    redraw();
    validateChains();
    return;
  } else {
    store.refusals = [{ lane: null, stage_id: null, reason_text: refusalText(answer) }];
  }
  renderRefusals();
  renderBusy();
}

// The reasons said once to a screen reader, when they change (never at each render).
let announced = "";
function announceRefusals() {
  const said = store.refusals.map((r) => r.reason_text).join(" ");
  if (said === announced) return;
  announced = said;
  $("rag-refusal-live").textContent = said;
}

function renderRefusals() {
  for (const node of document.querySelectorAll(".rag-chain-refusal")) node.remove();
  for (const row of document.querySelectorAll(".rag-chain-card.is-invalid")) row.classList.remove("is-invalid");
  const general = $("rag-chain-refusal-a");
  general.hidden = true;
  general.textContent = "";
  for (const refusal of store.refusals) {
    const row = refusal.stage_id ? document.querySelector(`#rag-seq .rag-chain-card[data-stage-id="${refusal.stage_id}"]`) : null;
    // A line not shown yet (« Dérouler », after the frame shown): said in the general line.
    if (row && !row.classList.contains("is-hidden")) {
      row.classList.add("is-invalid");
      row.querySelector(".rag-seq-head").after(el("p", "rag-chain-refusal", refusal.reason_text));
    } else {
      general.hidden = false;
      general.textContent = [general.textContent, refusal.reason_text].filter(Boolean).join(" ");
    }
  }
  announceRefusals();
  wires?.schedule();
}

// ---------- lot 5b: the ready-made architectures (vues-atelier-rag.md §8) ----------

// The preset whose segment (kind, option, in order) is the chain's retrieval segment, if any.
function currentPreset() {
  const segment = (chain()?.stages ?? []).filter(isMovable);
  return (
    (store.catalog?.presets ?? []).find(
      (preset) =>
        preset.segment.length === segment.length &&
        preset.segment.every((s, i) => s.kind === segment[i].kind && s.option === segment[i].option),
    ) ?? null
  );
}

// Applying a preset replaces the retrieval segment only, its stages at the settings the
// session gives (the shipped ones); the session then says whether the chain runs. A stage of a
// kind already there keeps its id.
function applyPreset(preset) {
  const pipeline = chain();
  if (!pipeline) return;
  const old = pipeline.stages.filter(isMovable);
  const kept = pipeline.stages.filter((s) => !isMovable(s));
  const used = new Set(kept.map((s) => s.id));
  const idOf = (kind) => {
    const same = old.find((s) => s.kind === kind && !used.has(s.id));
    if (same) return same.id;
    let n = 1;
    while (used.has(`s${n}`) || old.some((s) => s.id === `s${n}`)) n += 1;
    return `s${n}`;
  };
  const segment = preset.segment.map((s) => {
    const stage = { id: idOf(s.kind), kind: s.kind, option: s.option, params: clone(s.params ?? {}) };
    used.add(stage.id);
    return stage;
  });
  const before = kept.findIndex((s) => s.kind === store.catalog.insert_before);
  kept.splice(before < 0 ? kept.length : before, 0, ...segment);
  pipeline.stages = kept;
  changed();
  document.querySelector(`#rag-presets .rag-preset[data-preset="${preset.id}"]`)?.focus();
}

function renderPresets() {
  const box = $("rag-presets");
  box.replaceChildren();
  const presets = store.catalog?.presets ?? [];
  box.hidden = store.mode !== "compose" || !presets.length || !chain();
  if (box.hidden) return;
  const title = text("presets_title_text");
  box.setAttribute("aria-label", title);
  box.append(el("span", "rag-presets-label", title));
  const current = currentPreset();
  for (const preset of presets) {
    const label = preset.available ? preset.label_text : `${preset.label_text} (${text("unavailable_text")})`;
    const button = el("button", "rag-preset", label);
    button.type = "button";
    button.dataset.preset = preset.id;
    button.classList.toggle("is-unavailable", !preset.available);
    // The explanation, why it would not run, what a run would meet: the tooltip, and the
    // same text described to the keyboard and screen readers (`title` reaches neither).
    const help = [preset.explain_text, preset.reason_text, preset.note_text].filter(Boolean).join("\n");
    button.title = help;
    const described = el("span", "rag-visually-hidden", help);
    described.id = `rag-preset-help-${preset.id}`;
    button.setAttribute("aria-describedby", described.id);
    button.setAttribute("aria-pressed", String(preset.id === current?.id));
    button.addEventListener("click", () => applyPreset(preset));
    box.append(button, described);
  }
}

function resetChains() {
  store.pipelines = [clone(store.defaultPipeline)];
  forgetChains();
  redraw();
  validateChains();
}

// ---------- the three views (lot 5a, vues-atelier-rag.md §3 to §5, §7) ----------

// The sequence of the chain being edited: BUILD's steps, then RUN's own steps (the question,
// its embedding), then the chain's RUN stages in its order. Each entry: its step (from the
// catalog), the chain's stage it shows (or none), that stage's index in the chain.
function sequence() {
  const catalog = store.catalog;
  const stages = chain()?.stages ?? [];
  if (!catalog) return [];
  const of = (kind) => stages.find((s) => s.kind === kind) ?? null;
  const entries = [];
  const push = (step, stage) => entries.push({ step, stage, index: stage ? stages.indexOf(stage) : -1 });
  for (const step of catalog.steps) {
    if (step.phase !== "build" || (step.stage && !of(step.stage))) continue;
    push(step, step.stage ? of(step.stage) : null);
  }
  for (const step of catalog.steps) {
    if (step.phase !== "run" || step.own || (step.stage && !of(step.stage))) continue;
    push(step, step.stage ? of(step.stage) : null);
  }
  for (const stage of stages) {
    const step = catalog.steps.find((s) => s.own && s.stage === stage.kind);
    if (step && step.phase === "run") push(step, stage);
  }
  return entries;
}

function seqRow(entry, n) {
  const { step, stage, index } = entry;
  const row = el("li", `rag-seq-step is-${step.phase}`);
  row.dataset.step = step.key;
  if (step.stage === "generation") row.classList.add("is-model");
  if (step.own && stage) {
    // The editor's selectors (SPEC.md): the line is the chain's stage card.
    row.classList.add("rag-chain-card");
    row.dataset.kind = stage.kind;
    row.dataset.stageId = stage.id;
  }
  const head = el("button", "rag-seq-head");
  head.type = "button";
  head.append(el("span", "rag-chain-number", String(n)), el("span", "rag-seq-name", step.label_text));
  const pill = el("span", "rag-seq-status");
  pill.hidden = true;
  head.append(pill);
  head.addEventListener("click", () => {
    const focused = document.activeElement === head;
    select(step.key);
    // « Dérouler » draws the lines again: the keyboard's focus back on this line's head.
    if (focused && !head.isConnected) {
      document.querySelector(`#rag-seq .rag-seq-step[data-step="${step.key}"] .rag-seq-head`)?.focus();
    }
  });
  row.append(head, el("p", "rag-seq-line", step.action_text));
  if (store.mode === "compose") {
    if (step.own && stage) row.append(stageControls(stage, index));
    else if (step.key === "embed_query") row.append(el("p", "rag-seq-same", text("same_model_text")));
  }
  return row;
}

function renderPhase(id) {
  const phase = store.catalog.phases.find((p) => p.id === id);
  const band = $(`rag-phase-${id}`);
  band.replaceChildren();
  if (!phase) return;
  band.append(el("span", "rag-phase-tag", phase.tag_text), el("span", null, phase.label_text), el("small", null, phase.help_text));
}

// `shown`: the last step visible (« Dérouler »: the frame shown; the steps after it keep their
// place, invisible, and so does the RUN band before its first step).
function renderSequence(entries, shown) {
  renderPhase("build");
  renderPhase("run");
  const lists = { build: $("rag-seq-build"), run: $("rag-seq-run") };
  lists.build.replaceChildren();
  lists.run.replaceChildren();
  entries.forEach((entry, i) => {
    const row = seqRow(entry, i + 1);
    row.classList.toggle("is-hidden", i > shown);
    lists[entry.step.phase]?.append(row);
  });
  const firstRun = entries.findIndex((e) => e.step.phase === "run");
  $("rag-phase-run").classList.toggle("is-hidden", firstRun >= 0 && shown < firstRun);
  renderPalette();
}

// The tiles visible at the last render: a tile revealed since then arrives (`is-new`).
// `null`: none arrives at the next render (the stepper rebuilt, straight to its frame).
let seen = null;

// A tile's subtitle: the chosen option of its stage (the embedding model, the reranker, the
// store), else its own note.
function subtitle(component) {
  const stage = component.stage ? chain()?.stages.find((s) => s.kind === component.stage) : null;
  return (stage && optionInfo(stage.kind, stage.option)?.label_text) || component.note_text;
}

function renderArchitecture(entries, shown) {
  const box = $("rag-arch-groups");
  box.replaceChildren();
  const componentsOf = (list) => new Set(list.flatMap((e) => e.step.uses.map((u) => u.component)));
  // A tile exists only when a step of the chain calls on it (no Reranker without reranking);
  // in « Dérouler », it shows once a step up to the frame shown has called on it.
  const used = componentsOf(entries);
  const revealed = componentsOf(entries.slice(0, shown + 1));
  const playing = store.mode === "play";
  for (const group of store.catalog.groups) {
    const tiles = store.catalog.components.filter((c) => c.group === group.id && used.has(c.id));
    if (!tiles.length) continue;
    const section = el("section", "rag-arch-group");
    section.dataset.group = group.id;
    section.classList.toggle("is-hidden", !tiles.some((c) => revealed.has(c.id)));
    section.append(el("h4", null, group.label_text));
    const list = el("ul");
    for (const component of tiles) {
      const tile = el("li", "rag-arch-tile");
      tile.dataset.component = component.id;
      if (!revealed.has(component.id)) tile.classList.add("is-hidden");
      else if (playing && seen && !seen.has(component.id)) tile.classList.add("is-new");
      const icon = el("span", "rag-arch-icon", component.icon);
      icon.setAttribute("aria-hidden", "true");
      tile.append(icon, el("span", "rag-arch-name", component.label_text), el("span", "rag-arch-sub", subtitle(component)));
      list.append(tile);
    }
    section.append(list);
    box.append(section);
  }
  seen = revealed;
}

// ---------- the run, as the sequence reads it ----------

function runLane() {
  const run = store.run;
  return run ? (run.lanes.find((l) => l.lane === "a") ?? run.lanes[0] ?? null) : null;
}

// A stage's settings, those left out at their shipped value: a run and the chain compared.
function settingsOf(kind, option, params) {
  const values = Object.fromEntries((optionInfo(kind, option)?.params ?? []).map((p) => [p.name, p.default]));
  Object.assign(values, params ?? {});
  return JSON.stringify(Object.keys(values).sort().map((name) => [name, values[name]]));
}

// The run « Dérouler » shows: the last one, when it ran the chain being edited (its stages,
// options and settings, in order). A chain edited since then gets its guided tour instead.
function shownRun() {
  return store.mode === "play" ? chainRun() : null;
}

// The last run, when it ran the chain being edited; else none.
function chainRun() {
  if (!store.run) return null;
  const lane = runLane();
  const stages = chain()?.stages ?? [];
  if (!lane || lane.stages.length !== stages.length) return null;
  const same = lane.stages.every((s, i) => {
    const mine = stages[i];
    return (
      s.stage_id === mine.id &&
      s.kind === mine.kind &&
      s.option === mine.option &&
      settingsOf(s.kind, s.option, s.params) === settingsOf(mine.kind, mine.option, mine.params)
    );
  });
  return same ? store.run : null;
}

function runStage(step) {
  if (!step.stage || !shownRun()) return null;
  return runLane()?.stages.find((s) => s.kind === step.stage) ?? null;
}

// The pill of a line in « Dérouler », once a run is known: a stage's own status and duration;
// Documents and the question's Embedding take their stage's status without a duration.
function pillOf(step) {
  if (!shownRun()) return null;
  if (step.key === "question") return { status: "ok", said: text("question_received_text") };
  const stage = runStage(step);
  if (!stage) return null;
  return { status: stage.status, said: stepStatus(step, stage) };
}

// A step's status: its stage's own line (progress, duration), or only its status for a step
// that reads a stage (its duration is the stage's, not its own).
function stepStatus(step, stage) {
  return step.own ? statusLine(stage) : text(STATUS_KEYS[stage.status] ?? "") || stage.status;
}

function renderPills() {
  for (const row of document.querySelectorAll("#rag-seq .rag-seq-step")) {
    const step = store.catalog?.steps.find((s) => s.key === row.dataset.step);
    const pill = row.querySelector(".rag-seq-status");
    const shown = step ? pillOf(step) : null;
    pill.hidden = !shown;
    pill.textContent = shown?.said ?? "";
    if (shown) row.dataset.run = shown.status;
    else delete row.dataset.run;
  }
}

// ---------- the focus ----------

function uses(step) {
  const box = el("div", "rag-focus-uses");
  box.append(el("span", "rag-view-label", text("uses_title_text")));
  const how = { reads: text("reads_text"), writes: text("writes_text"), calls: text("calls_text") };
  for (const use of step.uses) {
    const component = store.catalog.components.find((c) => c.id === use.component);
    if (!component) continue;
    const tag = el("span", "rag-tag");
    const icon = el("span", "rag-tag-icon", component.icon);
    icon.setAttribute("aria-hidden", "true");
    tag.append(icon, ` ${component.label_text} · ${how[use.how] ?? use.how}`);
    tag.dataset.component = component.id;
    tag.dataset.how = use.how;
    box.append(tag);
  }
  return box;
}

function focusIo(rows) {
  const dl = el("dl", "rag-focus-io");
  for (const [label, value, className] of rows) {
    if (value) dl.append(el("dt", null, label), el("dd", className ?? null, value));
  }
  return dl;
}

// What the step received, produced and cost in the last run (« Dérouler » only, §5, §7).
function focusRun(box, step) {
  const run = shownRun();
  if (!run) {
    // Composer, the last run being this chain's: its figures are one click away.
    const hint = store.mode === "compose" && chainRun() ? "focus_play_hint_text" : "focus_no_run_text";
    box.append(el("p", "rag-note rag-focus-hint", text(hint)));
    return;
  }
  if (step.key === "question") {
    box.append(focusIo([[text("question_label_text"), quote(run.question)]]));
    return;
  }
  const stage = runStage(step);
  if (!stage) {
    box.append(el("p", "rag-note rag-focus-hint", text("focus_no_run_text")));
    return;
  }
  box.append(el("p", "rag-focus-status", stepStatus(step, stage)));
  const ended = stage.ended;
  if (!ended) return;
  if (ended.error_text) box.append(el("p", "rag-stage-error", ended.error_text));
  if (step.key === "documents") {
    box.append(focusIo([[text("input_text"), ended.input_text]]));
    return;
  }
  if (step.key === "embed_query") {
    box.append(focusIo([[text("input_text"), quote(run.question)]]));
  } else if (["context", "generation"].includes(step.stage)) {
    box.append(focusIo([[text("input_text"), ended.input_text]]));
    if (ended.output_text) box.append(el("pre", "rag-focus-pre", ended.output_text));
  } else {
    box.append(
      focusIo([
        [text("input_text"), ended.input_text],
        [text("output_text"), ended.output_text],
      ]),
    );
  }
  if (ended.facts?.length) {
    const facts = el("ul", "rag-focus-facts");
    for (const fact of ended.facts) facts.append(el("li", null, labelled(fact.label_text, fact.value_text)));
    box.append(facts);
  }
  if (step.key !== "embed_query" && ended.items?.length) box.append(itemsTable(ended.items));
  if (step.own && ["ok", "error", "cancelled"].includes(stage.status)) {
    const foot = el("p", "rag-stage-figures");
    foot.append(el("span", "rag-stage-duration", labelled(text("duration_text"), `${fmtInt(ended.duration_ms)} ms`)));
    if (ended.memory_text) foot.append(el("span", "rag-stage-memory", labelled(text("memory_text"), ended.memory_text)));
    box.append(foot);
  }
}

function renderFocus(entries) {
  const box = $("rag-focus");
  box.replaceChildren();
  const i = entries.findIndex((e) => e.step.key === store.current);
  const step = i >= 0 ? entries[i].step : null;
  box.classList.toggle("is-run", step?.phase === "run");
  box.dataset.step = step?.key ?? "";
  if (!step) {
    box.append(el("p", "rag-focus-phase", text("focus_title_text")), el("p", "rag-focus-explain", text("focus_empty_text")));
    return;
  }
  const phase = store.catalog.phases.find((p) => p.id === step.phase);
  box.append(
    el(
      "p",
      "rag-focus-phase",
      text("focus_position_text", { phase: phase ? `${phase.tag_text} · ${phase.label_text}` : step.phase, n: i + 1, total: entries.length }),
    ),
  );
  const title = el("h3");
  title.append(el("span", "rag-chain-number", String(i + 1)), el("span", "rag-focus-name", step.label_text));
  box.append(title, el("p", "rag-focus-action", step.action_text));
  if (step.note_text) box.append(el("p", "rag-focus-note", step.note_text));
  if (step.explain_text) box.append(el("p", "rag-focus-explain", step.explain_text));
  if (step.uses.length) box.append(uses(step));
  focusRun(box, step);
}

// ---------- the wires: from the step shown to the components it calls on ----------

let wires = null;

function drawWires({ box }) {
  const defs = svgEl("defs");
  const head = svgEl("marker", {
    id: "rag-arrow",
    viewBox: "0 0 10 10",
    refX: 9,
    refY: 5,
    markerWidth: 6,
    markerHeight: 6,
    orient: "auto-start-reverse",
  });
  head.append(svgEl("path", { d: "M0 0 L10 5 L0 10 z", class: "rag-arrow-head" }));
  defs.append(head);
  const parts = [defs];
  const step = store.catalog?.steps.find((s) => s.key === store.current);
  const row = step && document.querySelector(`#rag-seq .rag-seq-step[data-step="${step.key}"] .rag-seq-head`);
  if (!row) return parts;
  const from = box(row);
  const flowing = store.mode === "play" && runStage(step)?.status === "running";
  step.uses.forEach((use, i) => {
    const tile = document.querySelector(`#rag-arch .rag-arch-tile[data-component="${use.component}"]`);
    if (!tile) return;
    const to = box(tile);
    const x1 = from.r + 2;
    const y1 = from.cy + (i - (step.uses.length - 1) / 2) * 8;
    const x2 = to.l - 2;
    const y2 = to.cy;
    const dx = Math.max(30, (x2 - x1) / 2);
    // Read: from the component to the step; written or called: from the step to it.
    const d =
      use.how === "reads"
        ? `M${x2} ${y2} C${x2 - dx} ${y2}, ${x1 + dx} ${y1}, ${x1 + 6} ${y1}`
        : `M${x1} ${y1} C${x1 + dx} ${y1}, ${x2 - dx} ${y2}, ${x2 - 4} ${y2}`;
    parts.push(wire(d, "diagram-path"));
    const core = wire(d, `diagram-path-core${flowing ? " is-flow" : ""}`);
    core.setAttribute("marker-end", "url(#rag-arrow)");
    core.dataset.component = use.component;
    parts.push(core);
  });
  return parts;
}

// The step shown: its line selected (Composer) or lit with its components (Dérouler), its
// focus, its wires.
function renderCurrent(entries = sequence()) {
  if (store.current && !entries.some((e) => e.step.key === store.current)) store.current = null;
  const views = $("rag-views");
  let lit = null;
  for (const row of views.querySelectorAll(".rag-seq-step")) {
    const on = row.dataset.step === store.current;
    row.classList.toggle("is-selected", on && store.mode === "compose");
    row.querySelector(".rag-seq-head").setAttribute("aria-pressed", String(on));
    if (on) lit = row;
  }
  const step = store.catalog?.steps.find((s) => s.key === store.current);
  const nodes = [];
  if (store.mode === "play" && lit && step) {
    nodes.push(lit);
    for (const use of step.uses) {
      const tile = views.querySelector(`.rag-arch-tile[data-component="${use.component}"]`);
      if (tile) nodes.push(tile);
    }
  }
  light(views, nodes);
  renderFocus(entries);
  wires?.schedule();
}

function select(key) {
  if (store.mode === "play" && stepper) {
    // « Dérouler »: the line's frame (vues-atelier-rag.md §3).
    const i = stepper.frames.indexOf(key);
    if (i >= 0) stepper.show(i);
    return;
  }
  store.current = key;
  renderCurrent();
}

function renderModes() {
  $("rag-views").dataset.mode = store.mode;
  for (const button of document.querySelectorAll("#rag-modes [data-mode]")) {
    button.setAttribute("aria-pressed", String(button.dataset.mode === store.mode));
  }
  $("rag-reset-chain").hidden = store.mode !== "compose";
  $("rag-stepper").hidden = store.mode !== "play";
}

function setMode(mode) {
  if (!MODES.includes(mode) || mode === store.mode) return;
  store.mode = mode;
  keep(MODE_KEY, mode);
  if (mode === "compose") store.current = null; // no step selected (§7)
  redraw({ restart: true });
}

// ---------- « Dérouler »: the stepper (lot 5a-2, vues-atelier-rag.md §6) ----------

let stepper = null;
let quiet = false; // the stepper being rebuilt: one render at the end, not one per frame

// The frames the stepper should hold, a step's key each: every step of the sequence for the
// guided tour; with a run, the steps up to the last one the run reached (a stage with an
// event). The steps that read a stage (Documents, the question and its Embedding) come with
// the next step of their own: the question is embedded during `embedding`, but the sequence
// shows it just before the retrieval.
function playFrames(entries) {
  const run = shownRun();
  if (!run) return entries.map((e) => e.step.key);
  const reached = new Set((runLane()?.stages ?? []).filter((s) => s.status !== "waiting").map((s) => s.stage_id));
  let last = -1;
  entries.forEach((e, i) => {
    if (e.step.own && e.stage && reached.has(e.stage.id)) last = i;
  });
  return entries.slice(0, last + 1).map((e) => e.step.key);
}

// Where an ended run lands: the first step in error (or stopped), else the last frame.
function landing(keys = stepper?.frames ?? []) {
  const steps = store.catalog?.steps ?? [];
  const failed = keys.findIndex((key) => {
    const step = steps.find((s) => s.key === key);
    return Boolean(step?.own) && ["error", "cancelled"].includes(runStage(step)?.status);
  });
  return failed >= 0 ? failed : keys.length - 1;
}

// The stepper brought to the frames the page should show: the missing ones pushed (live, the
// last one shown), else rebuilt (`restart`, or a sequence that changed): `clear()`, every frame
// pushed, then image 1 for the tour, the landing frame for an ended run, the live one for a
// run going on. True when it rendered the views.
function syncFrames({ restart = false } = {}) {
  if (store.mode !== "play" || !stepper || !store.catalog || !chain()) return false;
  const keys = playFrames(sequence());
  const have = stepper.frames;
  const prefix = have.length <= keys.length && have.every((key, i) => key === keys[i]);
  if (!restart && prefix) {
    if (have.length === keys.length) return false;
    const live = stepper.live;
    for (const key of keys.slice(have.length)) stepper.push(key);
    return live;
  }
  quiet = true;
  stepper.clear();
  for (const key of keys) stepper.push(key);
  quiet = false;
  const run = shownRun();
  store.current = null;
  seen = null;
  if (!keys.length) {
    renderViews();
    return true;
  }
  if (!run) stepper.show(0);
  else if (run.ended) stepper.show(landing(keys));
  else stepper.follow();
  return true;
}

// A frame shown (◀, ▶, a line clicked, a frame pushed live): its step lit, the views drawn.
function showFrame(key) {
  if (quiet) return;
  store.current = key ?? null;
  renderViews();
}

function renderLegend() {
  const legend = $("rag-legend");
  if (store.mode !== "play" || !stepper) {
    legend.textContent = "";
    return;
  }
  const run = shownRun();
  // « Suivre le direct » means nothing in the guided tour: shown with a run only.
  stepper.element.querySelector(".diagram-step-live").hidden = !run;
  let key = "legend_tour_text";
  if (run && !run.ended) key = stepper.live ? "legend_live_text" : "legend_replay_text";
  else if (run) key = stepper.index === landing() ? "legend_done_text" : "legend_replay_text";
  legend.textContent = text(key);
}

// The views drawn again, the stepper first brought up to date in « Dérouler ».
function redraw(options) {
  if (store.mode === "play" && syncFrames(options)) return;
  renderViews();
}

function renderViews() {
  if (!store.catalog || !chain()) return;
  const entries = sequence();
  // « Composer »: everything visible; « Dérouler »: up to the frame shown.
  const shown = store.mode === "play" ? (stepper?.index ?? -1) : entries.length - 1;
  renderModes();
  renderPresets();
  renderSequence(entries, shown);
  renderArchitecture(entries, shown);
  renderPills();
  renderCurrent(entries);
  renderRefusals();
  renderLegend();
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
      store.session = { state: p.state, reason_text: p.reason_text };
      if (p.state === "idle" && closeStaleRun()) renderRun();
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
      if (store.run && store.run.runId === p.run_id) {
        store.run.ended = p;
        store.land = true;
      }
      break;
    default:
      return;
  }
  if (store.replaying) return; // `last_run` read again: drawn once, at its end
  renderRun();
  renderBusy();
}

// A run whose end never came (WaveStack failed between two events) while the session is
// back in `idle`: said ended in error, never left « en cours ».
function closeStaleRun() {
  const run = store.run;
  if (!run || run.ended) return false;
  run.ended = { status: "error", duration_ms: null, comparison: null };
  for (const lane of run.lanes) {
    for (const stage of lane.stages) if (!stage.ended) stage.status = "skipped";
  }
  return true;
}

const STATUS_KEYS = {
  waiting: "status.waiting_text",
  running: "status.running_text",
  ok: "status.ok_text",
  error: "status.error_text",
  skipped: "status.skipped_text",
  cancelled: "status.cancelled_text",
  not_run: "status.not_run_text",
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
  for (const key of ["rank_text", "before_text", "document_text", "score_text"]) {
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
    doc.append(el("span", "rag-doc-title", item.title_text));
    if (item.sources?.length) {
      // Where the excerpt stood in each list before (the fusion: both searches).
      const said = item.sources.map((src) =>
        labelled(src.label_text, `${fmtRank(src.rank)}${typeof src.score === "number" ? ` (${fmtScore(src.score)})` : ""}`),
      );
      doc.append(el("span", "rag-doc-sources", said.join(" · ")));
    }
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
  title.append(el("span", "rag-chain-number", String(index + 1)), el("span", null, stage.label_text));
  head.append(title);
  head.append(el("span", "rag-stage-status", statusLine(stage)));
  card.append(head);
  card.append(el("p", "rag-stage-option", stage.option_label_text));
  const ended = stage.ended;
  if (!ended) return card;
  if (ended.error_text) card.append(el("p", "rag-stage-error", ended.error_text));
  if (ended.borrowed) card.append(el("p", "rag-stage-borrowed", text("borrowed_text")));
  const dl = el("dl", "rag-stage-io");
  if (ended.input_text) dl.append(el("dt", null, text("input_text")), el("dd", "rag-stage-input", ended.input_text));
  if (ended.output_text) dl.append(el("dt", null, text("output_text")), el("dd", "rag-stage-output", ended.output_text));
  if (dl.childElementCount) card.append(dl);
  if (ended.facts.length) {
    const facts = el("dl", "rag-stage-facts");
    for (const fact of ended.facts) facts.append(el("dt", null, fact.label_text), el("dd", null, fact.value_text));
    card.append(facts);
  }
  if (ended.items.length) card.append(itemsTable(ended.items));
  if (ended.memory_text || ["ok", "error", "cancelled"].includes(stage.status)) {
    const foot = el("p", "rag-stage-figures");
    foot.append(el("span", "rag-stage-duration", labelled(text("duration_text"), `${fmtInt(ended.duration_ms)} ms`)));
    if (ended.memory_text) foot.append(el("span", "rag-stage-memory", labelled(text("memory_text"), ended.memory_text)));
    card.append(foot);
  }
  return card;
}

// Every step's detail (the former section 3), folded under the views: the chain's lane only
// (a run of two lanes, from a page of before lot 5a, shows its A).
function renderResults() {
  const box = $("rag-results");
  box.replaceChildren();
  const run = store.run;
  $("rag-results-empty").hidden = Boolean(run);
  const summary = $("rag-run-summary");
  summary.hidden = !run;
  if (!run) return;
  const status = run.ended ? text(STATUS_KEYS[run.ended.status === "ok" ? "ok" : run.ended.status]) : text("status.running_text");
  summary.textContent = `${quote(run.question)} · ${status}${typeof run.ended?.duration_ms === "number" ? ` · ${fmtInt(run.ended.duration_ms)} ms` : ""}`;
  const lane = runLane();
  if (!lane) return;
  const column = el("section", "rag-lane");
  column.dataset.lane = lane.lane;
  lane.stages.forEach((stage, index) => column.append(stageCard(stage, index)));
  box.append(column);
}

// An event of the run: the details, then « Dérouler »: a frame per step reached (live), the
// landing frame once it ended, the pills, the focus and the wires of the step shown.
function renderRun() {
  renderResults();
  syncFrames();
  if (store.land && store.mode === "play" && stepper && shownRun()?.ended) {
    const i = landing();
    if (stepper.live && i >= 0 && i !== stepper.index) stepper.show(i);
  }
  store.land = false;
  renderPills();
  renderCurrent();
  renderLegend();
}

// ---------- state of the session: what may be asked now ----------

function busyReason() {
  if (!store.content) return null;
  if (store.unavailable) return store.unavailable;
  const { state, reason_text: reason } = store.session;
  if (state !== "idle") return text("busy_text", { raison: reason || state }) || reason || state;
  return null;
}

// Why « Lancer » waits: the session busy, else a chain it would refuse.
function runBlocked() {
  return busyReason() || store.refusals[0]?.reason_text || null;
}

function renderBusy() {
  const reason = busyReason();
  const busy = $("rag-busy");
  busy.hidden = !reason;
  busy.textContent = reason || "";
  const run = $("rag-run");
  const blocked = runBlocked();
  run.disabled = Boolean(blocked) || store.pending || !store.content;
  run.title = blocked || "";
  $("rag-stop").disabled = store.session.state !== "rag_lab";
}

function renderContent() {
  for (const node of document.querySelectorAll("[data-text]")) {
    const value = text(node.dataset.text);
    if (value) node.textContent = value;
  }
  if (store.content) {
    $("rag-title").textContent = store.content.title_text;
    $("rag-intro").textContent = store.content.intro_text;
    $("rag-question").placeholder = store.content.question_placeholder_text;
    $("rag-modes").setAttribute("aria-label", store.content.modes_label_text);
  }
}

// ---------- gestures ----------

async function runChain() {
  const question = $("rag-question").value.trim();
  const status = $("rag-status");
  status.classList.remove("is-error");
  if (!question) {
    status.classList.add("is-error");
    status.textContent = t("rag.empty_question");
    return;
  }
  // The number fields' last values, even one typed without leaving its field (before
  // « Dérouler » takes the editor away).
  for (const input of document.querySelectorAll(".rag-param-input")) input.dispatchEvent(new Event("change"));
  const before = store.mode;
  setMode("play"); // « Lancer » shows the run as it goes (lot 5a-2)
  store.pending = true;
  renderBusy();
  status.textContent = text("running_text");
  const answer = await post("/api/intentions/rag_lab_run", { question, pipelines: store.pipelines });
  store.pending = false;
  if (!answer.ok) {
    setMode(before); // refused: nothing runs, back where the trainer was
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
    alert.textContent = t("rag.unavailable", { cause: error.message });
    return null;
  }
  store.content = body.content;
  store.catalog = body.catalog;
  store.defaultPipeline = body.default_pipeline;
  store.unavailable = body.unavailable_text;
  store.session = body.session_state;
  const alert = $("rag-content-error");
  alert.hidden = !body.content_error_text;
  alert.textContent = body.content_error_text || "";
  renderContent();
  if (!store.pipelines.length && store.defaultPipeline) store.pipelines = loadChains();
  // The last run, rebuilt from its envelopes (AD-1): the same projection as the stream's.
  store.run = null;
  store.replaying = true;
  try {
    for (const envelope of body.last_run) applyEnvelope(envelope);
  } finally {
    store.replaying = false;
  }
  store.land = false;
  store.lastSeq = body.seq;
  if (store.session.state === "idle") closeStaleRun();
  // « Dérouler »: the run's frames pushed again, straight to its landing frame (§6).
  redraw({ restart: true });
  renderResults();
  if (store.catalog) validateChains();
  renderBusy();
  return body;
}

async function main() {
  await textsReady; // the page's texts and formats in the session's language (languages 4/5)
  const mode = stored(MODE_KEY);
  if (MODES.includes(mode)) store.mode = mode;
  wires = wireLayer($("rag-views"), drawWires);
  // The stepper before the legend, in « Dérouler »'s bar (its labels read now: after `ready`).
  stepper = createStepper($("rag-stepper"), { onShow: showFrame });
  $("rag-stepper").prepend(stepper.element);
  let body = await refresh();
  while (!body) {
    await new Promise((resolve) => setTimeout(resolve, 2000));
    body = await refresh();
  }
  const question = $("rag-question");
  question.value = stored(QUESTION_KEY) ?? (text("default_question_text") || "");
  question.addEventListener("input", () => keep(QUESTION_KEY, question.value));
  question.addEventListener("keydown", (event) => {
    if (event.key === "Enter" && !$("rag-run").disabled) runChain();
  });
  $("rag-run").addEventListener("click", runChain);
  $("rag-stop").addEventListener("click", stopRun);
  $("rag-reset-chain").addEventListener("click", resetChains);
  for (const button of document.querySelectorAll("#rag-modes [data-mode]")) {
    button.addEventListener("click", () => setMode(button.dataset.mode));
  }
  document.body.dataset.ragReady = "true";
  streamEvents();
}

main();
