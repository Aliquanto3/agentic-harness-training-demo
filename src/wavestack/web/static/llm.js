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
  pending: { tokenize: null },
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
  const button = $("tokenize-button");
  button.disabled = Boolean(reason) || store.pending.tokenize !== null;
  button.title = reason || "";
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
  if (envelope.kind === "model_load_ended") {
    refresh(); // the active model and its tokenizer changed: read them again
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
  const alert = $("llm-content-error");
  alert.hidden = !body.content_error_fr;
  alert.textContent = body.content_error_fr || "";
  renderContent();
  renderModel();
  renderTokenizerInfo();
  renderBusy();
  return body;
}

async function main() {
  const prompt = $("llm-prompt");
  const body = await refresh();
  prompt.value = loadDraft() ?? (text("tokenization.default_text_fr") || "");
  prompt.addEventListener("input", () => saveDraft(prompt.value));
  $("tokenize-button").addEventListener("click", tokenize);
  if (body) store.lastSeq = body.seq;
  document.body.dataset.labReady = "true";
  streamEvents();
}

main();
