// AD-1: the single client-side store. It consumes every SSE event, visible
// panes or not, and only ever formats/derives (never recomputes business
// data such as tokens or availability).

const PANES = ["bricks", "human", "ctx", "orch", "schema"];
const PANE_LABELS = {
  bricks: "Panneau des briques",
  human: "Vue humain",
  ctx: "Contexte LLM",
  orch: "Orchestration",
  schema: "Schéma d'architecture",
};

const store = {
  sessionState: null,
  architecture: { nodes: [], edges: [] },
  journal: [],
  selection: null,
  hiddenPanes: new Set(),
  focusedPane: null,
  // Gauge source: the most recent of `context_preview` / `context_rendered` (AD-9).
  gauge: null, // { payload, preview }
  turns: [], // one projection per turn, filled only from its events
  composerError: null,
};

// Gauge group -> DESIGN.md segment colour token (formatting only).
const GROUP_COLORS = {
  system_prompt: "--color-segment-system-prompt",
  global_memory: "--color-segment-global-memory",
  tool_catalog: "--color-segment-tool-descriptions",
  skill_catalog: "--color-segment-tool-descriptions",
  skill_body: "--color-segment-tool-descriptions",
  history: "--color-segment-history",
  rag_excerpt: "--color-segment-rag",
  tool_result: "--color-segment-tool-results",
  subagent_result: "--color-segment-tool-results",
  message: "--color-segment-message",
};

const numberFormat = new Intl.NumberFormat("fr-FR", { maximumFractionDigits: 1 });
const fmt = (n) => numberFormat.format(n);
const seconds = (ms) => `${numberFormat.format(Math.max(ms, 0) / 1000)} s`;

// ---------- SSE: manual parsing, because the server names each event after
// its `kind` and EventSource cannot listen for an unknown kind generically. ----------

async function streamEvents(fromSeq, onEnvelope) {
  let lastSeq = fromSeq;
  for (;;) {
    try {
      const response = await fetch("/api/stream", {
        headers: lastSeq ? { "Last-Event-ID": String(lastSeq) } : {},
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
          const rawEvent = buffer.slice(0, sep);
          buffer = buffer.slice(sep + 2);
          const envelope = parseSseEvent(rawEvent);
          if (envelope) {
            lastSeq = envelope.seq;
            onEnvelope(envelope);
          }
        }
      }
    } catch {
      // Reconnection below picks up at lastSeq: no event lost or duplicated.
    }
    await new Promise((resolve) => setTimeout(resolve, 1000));
  }
}

function parseSseEvent(rawEvent) {
  let data = null;
  for (const line of rawEvent.split("\n")) {
    if (line.startsWith("data:")) {
      data = line.slice(5).trim();
    }
    // `id:`/`event:` are redundant with the envelope's own `seq`/`kind`.
  }
  if (!data) return null;
  try {
    return JSON.parse(data);
  } catch {
    return null;
  }
}

function applyEnvelope(envelope) {
  store.journal.push(envelope);
  const p = envelope.payload;
  const turn = envelope.turn_id ? store.turns.find((t) => t.id === envelope.turn_id) : null;
  switch (envelope.kind) {
    case "session_state":
      store.sessionState = p;
      if (p.state === "idle") store.composerError = null;
      break;
    case "architecture_changed":
      store.architecture = p;
      break;
    case "context_preview":
      store.gauge = { payload: p, preview: true };
      break;
    case "turn_started":
      store.turns.push({
        id: envelope.turn_id,
        message: p.message,
        startedAt: Date.parse(envelope.ts),
        callStartedAt: null,
        phaseLabel: null,
        firstToken: false,
        stopRequested: false,
        context: null,
        text: "",
        reasoning: "",
        callEnded: null,
        overflow: null,
        truncated: null,
        notices: [],
        errors: [],
        status: null,
      });
      break;
    case "context_rendered":
      store.gauge = { payload: p, preview: false };
      if (turn) turn.context = p;
      break;
    case "context_overflow":
      if (turn) turn.overflow = p;
      break;
    case "model_call_started":
      if (turn) Object.assign(turn, { phaseLabel: p.phase_label, callStartedAt: Date.parse(envelope.ts) });
      break;
    case "model_first_token":
      if (turn) turn.firstToken = true;
      break;
    case "model_delta":
      if (turn) turn[p.channel === "reasoning" ? "reasoning" : "text"] += p.text;
      break;
    case "model_call_ended":
      // AD-2: the `*_ended` payload is authoritative and replaces the deltas.
      if (turn) Object.assign(turn, { callEnded: p, text: p.text, reasoning: p.reasoning });
      break;
    case "output_truncated":
      if (turn) turn.truncated = p;
      break;
    case "special_token_neutralized":
      if (turn) turn.notices.push(p.message_fr);
      break;
    case "harness_error":
      if (turn) turn.errors.push(p.message_fr);
      break;
    case "turn_ended":
      if (turn) {
        turn.status = p.status;
        announce(turn);
      }
      break;
  }
  scheduleRender();
}

// One render per frame at most: `model_delta` arrives every 50 ms.
let renderPending = false;
function scheduleRender() {
  if (renderPending) return;
  renderPending = true;
  requestAnimationFrame(() => {
    renderPending = false;
    render();
  });
}

function activeTurn() {
  const last = store.turns[store.turns.length - 1];
  return last && last.status === null ? last : null;
}

function announce(turn) {
  // Screen readers get the answer once, at the end of the turn, not token by token.
  document.getElementById("chat-live").textContent = turnNote(turn) || turn.text;
}

// ---------- pane visibility, focus, selection ----------

function hidePane(paneId) {
  if (store.hiddenPanes.size >= PANES.length - 1) return; // at least one stays visible
  store.hiddenPanes.add(paneId);
  render();
}

function showPane(paneId) {
  store.hiddenPanes.delete(paneId);
  render();
}

function togglePane(paneId) {
  if (store.hiddenPanes.has(paneId)) showPane(paneId);
  else hidePane(paneId);
}

function toggleFocus(paneId) {
  store.focusedPane = store.focusedPane === paneId ? null : paneId;
  render();
}

function paneOfComponent(componentId) {
  const el = document.querySelector(`[data-component="${cssEscape(componentId)}"]`);
  return el ? el.closest("[data-pane]")?.dataset.pane ?? null : null;
}

function cssEscape(value) {
  return window.CSS && CSS.escape ? CSS.escape(value) : value.replace(/[^a-zA-Z0-9_-]/g, "\\$&");
}

function select(componentId) {
  store.selection = store.selection === componentId ? null : componentId;
  render();
}

// ---------- rendering ----------

function render() {
  renderChips();
  renderMenu();
  renderPaneVisibility();
  renderGauge();
  renderChat();
  renderComposer();
  renderContext();
  renderSteps();
  renderJournal();
  renderSchema();
}

function el(tag, className, text) {
  const node = document.createElement(tag);
  if (className) node.className = className;
  if (text !== undefined) node.textContent = text;
  return node;
}

function emptyNote(text) {
  return el("p", "empty-note", text);
}

const NO_TURN_FR =
  "Aucun tour pour l'instant. Envoyez un message : le contexte envoyé au modèle apparaîtra ici.";

// ---------- context gauge (top bar) ----------

function renderGauge() {
  const bar = document.getElementById("gauge-bar");
  const figures = document.getElementById("gauge-figures");
  const threshold = document.getElementById("gauge-threshold");
  const root = document.getElementById("gauge");
  bar.querySelectorAll(".gauge-seg").forEach((node) => node.remove());
  const gauge = store.gauge;
  root.classList.toggle("is-overflow", Boolean(gauge?.payload.overflow));
  root.classList.toggle("is-near-limit", Boolean(gauge?.payload.near_limit));
  if (!gauge) {
    threshold.hidden = true;
    figures.textContent = "Contexte : en attente du modèle";
    return;
  }
  const p = gauge.payload;
  // flex-grow = received token counts: the bar is laid out, never recomputed (AD-1).
  for (const item of p.breakdown) {
    const seg = el("span", "gauge-seg");
    seg.style.flexGrow = String(item.tokens);
    seg.style.background = `var(${GROUP_COLORS[item.group] || "--color-muted"})`;
    seg.title = `${item.label_fr} : ${fmt(item.tokens)} tokens`;
    bar.appendChild(seg);
  }
  const free = el("span", "gauge-seg gauge-free");
  free.style.flexGrow = String(Math.max(p.usable - p.used, 0));
  free.title = `Espace libre : ${fmt(Math.max(p.usable - p.used, 0))} tokens`;
  bar.appendChild(free);
  threshold.hidden = p.overflow; // past 100 % the bar no longer maps to `usable`
  threshold.style.left = `${p.near_limit_ratio * 100}%`;
  threshold.title = `Seuil d'alerte : ${fmt(p.near_limit_ratio * 100)} %`;

  let text = `${fmt(p.used)} / ${fmt(p.usable)} tokens · ${fmt(p.percent)} %`;
  if (p.overflow) text = `⚠ ${text} · contexte dépassé`;
  else if (p.near_limit) text = `⚠ ${text} · Contexte plein à ${fmt(p.percent)} %`;
  if (gauge.preview) text += " · prochain tour";
  figures.textContent = text;
  root.title =
    `Fenêtre de ${fmt(p.window)} tokens, dont ${fmt(p.reserve)} réservés à la réponse : ` +
    `${fmt(p.usable)} utilisables.`;
}

// ---------- human view: bubbles, working indicator, composer ----------

function turnNote(turn) {
  switch (turn.status) {
    case "overflow":
      return "Contexte dépassé : le modèle n'a pas été appelé.";
    case "limit":
      return `Sortie coupée : la réponse a atteint la limite de ${fmt(turn.truncated?.max_tokens ?? 0)} tokens. Le texte reçu est conservé.`;
    case "cancelled":
      return "Arrêté à votre demande : le texte déjà reçu est conservé.";
    case "error":
      return `Erreur : ${turn.errors.join(" ") || "le tour s'est interrompu."} WaveStack reste utilisable.`;
    default:
      return null;
  }
}

function renderChat() {
  const chat = document.getElementById("chat");
  const followTail = chat.scrollHeight - chat.scrollTop - chat.clientHeight < 40;
  chat.innerHTML = "";
  if (store.turns.length === 0) {
    chat.appendChild(emptyNote(NO_TURN_FR));
    return;
  }
  for (const turn of store.turns) {
    chat.appendChild(el("div", "bubble bubble-user", turn.message));
    const answer = el("div", "bubble bubble-model");
    if (turn.reasoning) {
      const details = el("details", "bubble-reasoning");
      details.append(el("summary", "", "Raisonnement"), el("div", "", turn.reasoning));
      answer.appendChild(details);
    }
    if (turn.text) answer.appendChild(el("div", "bubble-text", turn.text));
    if (turn.status === null && !turn.firstToken) {
      const since = turn.callStartedAt ?? turn.startedAt;
      const label = turn.stopRequested
        ? "Arrêt demandé : il prend effet dès le premier token"
        : turn.phaseLabel || "Préparation du contexte";
      answer.appendChild(el("div", "working-indicator", `${label}… ${seconds(Date.now() - since)}`));
    }
    for (const notice of turn.notices) answer.appendChild(el("div", "bubble-note", notice));
    if (turn.status !== "error") {
      // e.g. attribution checks 4/6: the turn completed, but the harness reports it.
      for (const error of turn.errors) answer.appendChild(el("div", "bubble-note is-error", error));
    }
    const note = turnNote(turn);
    if (note) answer.appendChild(el("div", `bubble-note is-${turn.status}`, note));
    if (turn.status === "completed" && !turn.text) {
      answer.appendChild(el("div", "bubble-note", "(réponse vide)"));
    }
    chat.appendChild(answer);
  }
  if (followTail) chat.scrollTop = chat.scrollHeight;
}

function renderComposer() {
  const state = store.sessionState;
  const ready = state?.state === "idle" && !state.reason_fr;
  document.getElementById("composer-input").disabled = !ready;
  document.getElementById("composer-send").disabled = !ready;
  const stop = document.getElementById("composer-stop");
  stop.hidden = state?.state !== "turn";
  stop.disabled = Boolean(activeTurn()?.stopRequested);
  const reason = document.getElementById("composer-reason");
  const text = store.composerError || (ready ? null : state?.reason_fr || "En attente du modèle…");
  reason.hidden = !text;
  reason.textContent = text || "";
}

async function postIntention(path, body) {
  return fetch(path, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(body),
  });
}

async function sendMessage(event) {
  event.preventDefault();
  const input = document.getElementById("composer-input");
  const message = input.value.trim();
  if (!message || input.disabled) return;
  store.composerError = null;
  try {
    const response = await postIntention("/api/intentions/send", { message });
    if (response.ok) {
      input.value = "";
    } else {
      const body = await response.json().catch(() => ({}));
      store.composerError = typeof body.detail === "string" ? body.detail : "Envoi refusé.";
    }
  } catch {
    store.composerError = "WaveStack ne répond pas : l'envoi n'a pas eu lieu.";
  }
  render();
}

async function stopTurn() {
  const turn = activeTurn();
  if (turn) turn.stopRequested = true;
  render();
  try {
    await postIntention("/api/intentions/stop", {});
  } catch {
    // The turn ends on its own; the next state event re-enables the composer.
  }
}

// ---------- LLM context pane: labelled segments and raw output ----------

function renderContext() {
  const pane = document.getElementById("ctx");
  pane.innerHTML = "";
  const turn = [...store.turns].reverse().find((t) => t.context);
  if (!turn) {
    pane.appendChild(emptyNote(NO_TURN_FR));
    return;
  }
  const p = turn.context;
  pane.appendChild(
    el(
      "p",
      "ctx-total",
      `Tour ${turn.id} · ${fmt(p.used)} tokens envoyés (somme des segments) · ` +
        `fenêtre ${fmt(p.window)}, réserve ${fmt(p.reserve)}`
    )
  );
  for (const segment of p.segments) {
    const group = p.breakdown.find((item) => item.kinds.includes(segment.kind));
    const box = el("div", "ctx-segment");
    box.style.setProperty(
      "--segment-color",
      `var(${GROUP_COLORS[group?.group] || "--color-muted"})`
    );
    const label = el("div", "ctx-segment-label");
    label.append(
      el("span", "swatch"),
      `${segment.label_fr}${segment.brick ? ` (${segment.brick})` : ""} · ` +
        `${fmt(segment.tokens)} ${segment.tokens > 1 ? "tokens" : "token"}`
    );
    box.append(label, el("pre", "", segment.text));
    pane.appendChild(box);
  }
  for (const error of turn.errors) pane.appendChild(el("p", "bubble-note is-error", error));
  pane.appendChild(el("h3", "ctx-heading", "Sortie brute du modèle"));
  const raw = turn.callEnded ? turn.callEnded.raw_output : turn.reasoning + turn.text;
  pane.appendChild(
    el("pre", "ctx-raw", raw || (turn.overflow ? "Aucun appel : contexte dépassé." : "…"))
  );
}

// ---------- orchestration: model-call step with its counter, overflow card ----------

function renderSteps() {
  const steps = document.getElementById("steps");
  steps.innerHTML = "";
  for (const turn of store.turns) {
    if (turn.overflow) {
      const card = el("div", "overflow-card");
      card.append(
        el("h3", "", "⚠ Contexte dépassé — l'appel au modèle n'a pas été envoyé"),
        el("p", "number", `${fmt(turn.overflow.used)} / ${fmt(turn.overflow.usable)} tokens`),
        el("p", "", turn.overflow.message_fr),
        el("p", "label", "En production, un harnais pourrait")
      );
      const list = el("ul");
      for (const strategy of turn.overflow.strategies_fr) list.appendChild(el("li", "", strategy));
      card.appendChild(list);
      steps.appendChild(card);
      continue;
    }
    if (turn.callStartedAt === null) continue;
    const step = el("div", "step");
    step.appendChild(el("div", "step-title", `Appel au modèle · ${turn.id}`));
    const ended = turn.callEnded;
    const counter = ended
      ? `Entrée : ${fmt(ended.prompt_tokens)} tokens · Sortie : ${fmt(ended.output_tokens)} tokens · Temps : ${seconds(ended.duration_ms)}`
      : `Entrée : ${fmt(turn.context?.used ?? 0)} tokens · Sortie : … · Temps : ${seconds(Date.now() - turn.callStartedAt)} (en cours)`;
    step.appendChild(el("div", "token-counter number", counter));
    if (ended && ended.stop_reason !== "stop") {
      const reasons = { length: "sortie coupée", cancelled: "arrêté", error: "erreur" };
      step.appendChild(el("span", "step-badge", reasons[ended.stop_reason]));
    }
    steps.appendChild(step);
  }
}

function renderChips() {
  const container = document.getElementById("pane-chips");
  container.innerHTML = "";
  for (const paneId of store.hiddenPanes) {
    const chip = document.createElement("button");
    chip.type = "button";
    chip.className = "pane-chip";
    const linked = store.selection && paneOfComponent(store.selection) === paneId;
    if (linked) chip.classList.add("is-linked");
    chip.textContent = `+ ${PANE_LABELS[paneId]}`;
    chip.title = `Réafficher le volet ${PANE_LABELS[paneId]}`;
    chip.addEventListener("click", () => showPane(paneId));
    container.appendChild(chip);
  }
}

function renderMenu() {
  const list = document.getElementById("pane-menu-list");
  list.innerHTML = "";
  const lastVisible = store.hiddenPanes.size >= PANES.length - 1;
  for (const paneId of PANES) {
    const visible = !store.hiddenPanes.has(paneId);
    const li = document.createElement("li");
    const label = document.createElement("label");
    const checkbox = document.createElement("input");
    checkbox.type = "checkbox";
    checkbox.checked = visible;
    checkbox.disabled = visible && lastVisible;
    if (checkbox.disabled) checkbox.title = "Au moins un volet reste visible.";
    checkbox.addEventListener("change", () => togglePane(paneId));
    label.appendChild(checkbox);
    label.append(PANE_LABELS[paneId]);
    li.appendChild(label);
    list.appendChild(li);
  }
}

function renderPaneVisibility() {
  const lastVisible = store.hiddenPanes.size >= PANES.length - 1;
  document.body.classList.toggle("focus-mode", store.focusedPane !== null);
  for (const paneId of PANES) {
    const section = document.querySelector(`.pane[data-pane="${paneId}"]`);
    const hidden = store.hiddenPanes.has(paneId);
    section.classList.toggle("is-hidden", hidden);
    section.classList.toggle("is-focused", store.focusedPane === paneId);
    section.classList.toggle(
      "is-selected",
      store.selection !== null && paneOfComponent(store.selection) === paneId
    );
    const hideButton = section.querySelector('[data-action="hide"]');
    const disable = !hidden && lastVisible;
    hideButton.disabled = disable;
    hideButton.title = disable
      ? "Au moins un volet reste visible."
      : `Masquer le volet ${PANE_LABELS[paneId]}`;
    hideButton.setAttribute("aria-label", hideButton.title);
  }
}

function renderJournal() {
  const list = document.getElementById("journal");
  list.innerHTML = "";
  if (store.journal.length === 0) {
    const li = document.createElement("li");
    li.className = "empty-note";
    li.textContent = "Aucun événement pour l'instant.";
    list.appendChild(li);
    return;
  }
  for (const envelope of store.journal) {
    const li = document.createElement("li");
    const kind = document.createElement("span");
    kind.className = "kind";
    kind.textContent = envelope.kind;
    const pre = document.createElement("pre");
    pre.textContent = JSON.stringify(envelope.payload, null, 2);
    li.append(kind, pre);
    list.appendChild(li);
  }
}

function renderSchema() {
  const svg = document.getElementById("schema-svg");
  svg.innerHTML = "";
  const nodes = store.architecture.nodes || [];
  const width = 200;
  const gap = 40;
  nodes.forEach((node, index) => {
    const x = 20 + index * (width + gap);
    const g = document.createElementNS("http://www.w3.org/2000/svg", "g");
    g.setAttribute("class", "arch-node");
    g.dataset.component = node.id;
    if (store.selection === node.id) g.classList.add("is-selected");
    g.addEventListener("click", () => select(node.id));

    const rect = document.createElementNS("http://www.w3.org/2000/svg", "rect");
    rect.setAttribute("x", String(x));
    rect.setAttribute("y", "40");
    rect.setAttribute("width", String(width));
    rect.setAttribute("height", "60");

    const text = document.createElementNS("http://www.w3.org/2000/svg", "text");
    text.setAttribute("x", String(x + width / 2));
    text.setAttribute("y", "75");
    text.setAttribute("text-anchor", "middle");
    text.textContent = node.label_fr;

    g.append(rect, text);
    svg.appendChild(g);
  });
}

// ---------- boot ----------

function closePaneMenu() {
  const list = document.getElementById("pane-menu-list");
  if (list.hidden) return;
  list.hidden = true;
  document.getElementById("pane-menu-toggle").setAttribute("aria-expanded", "false");
}

async function boot() {
  document.getElementById("pane-menu-toggle").addEventListener("click", () => {
    const list = document.getElementById("pane-menu-list");
    const expanded = !list.hidden;
    list.hidden = expanded;
    document.getElementById("pane-menu-toggle").setAttribute("aria-expanded", String(!expanded));
  });

  document.addEventListener("click", (event) => {
    if (!event.target.closest(".pane-menu")) closePaneMenu();
  });

  for (const paneId of PANES) {
    const section = document.querySelector(`.pane[data-pane="${paneId}"]`);
    section
      .querySelector('[data-action="hide"]')
      .addEventListener("click", () => hidePane(paneId));
    section
      .querySelector('[data-action="focus"]')
      .addEventListener("click", () => toggleFocus(paneId));
  }

  document.getElementById("composer").addEventListener("submit", sendMessage);
  document.getElementById("composer-stop").addEventListener("click", stopTurn);
  // Local stopwatch anchored on the `*_started` ts, replaced by `duration_ms` (AD-1).
  setInterval(() => {
    if (activeTurn()) {
      renderChat();
      renderSteps();
    }
  }, 250);

  document.addEventListener("keydown", (event) => {
    if (event.key !== "Escape") return;
    if (!document.getElementById("pane-menu-list").hidden) {
      closePaneMenu();
    } else if (store.focusedPane !== null) {
      store.focusedPane = null;
      render();
    }
  });

  try {
    const response = await fetch("/api/state");
    const body = await response.json();
    store.sessionState = body.session_state;
    store.architecture = body.architecture_changed || { nodes: [], edges: [] };
    const preview = body.context_preview;
    const rendered = body.context_rendered;
    const latest = [preview, rendered].filter(Boolean).sort((a, b) => b.seq - a.seq)[0];
    if (latest) store.gauge = { payload: latest.payload, preview: latest === preview };
  } catch {
    // AD-16: a failed boot fetch still lets the live stream take over.
  }
  render();

  // Replay the whole journal: a reload rebuilds past and in-progress turns (AD-1).
  streamEvents(0, applyEnvelope);
}

boot();
