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
  chatFrom: 0, // index of the first turn shown as a bubble (`conversation_cleared`)
  composerError: null,
  bricks: null, // last `bricks_changed` payload: cards and system prompt, as the session computed them
  openExplanations: new Set(), // brick ids whose explanation is unfolded (UI state only)
  closedPayloads: new Set(), // seq of outbound payloads folded by the user (open by default)
  // Harness steps outside any turn (MCP discovery), each placed after the turns seen so far.
  offTurn: [],
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
    case "bricks_changed":
      store.bricks = p;
      break;
    case "conversation_cleared":
      // The trace keeps past turns (orchestration, context pane); only bubbles are hidden.
      store.chatFrom = store.turns.length;
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
        limit: null,
        // Orchestration, in the real order: model calls, tool executions, harness events.
        steps: [],
      });
      break;
    case "context_rendered":
      store.gauge = { payload: p, preview: false };
      if (turn) {
        turn.context = p;
        turn.steps.push({ type: "call", id: envelope.call_id, context: p, startedAt: null, ended: null });
      }
      break;
    case "context_overflow":
      if (turn) turn.overflow = p;
      break;
    case "model_call_started":
      if (turn) {
        // A new call of the same turn: the indicator comes back until its first token.
        Object.assign(turn, {
          phaseLabel: p.phase_label,
          callStartedAt: Date.parse(envelope.ts),
          firstToken: false,
          text: "",
          reasoning: "",
        });
        lastCall(turn).startedAt = Date.parse(envelope.ts);
      }
      break;
    case "model_first_token":
      if (turn) turn.firstToken = true;
      break;
    case "model_delta":
      // A tool call is shown in Orchestration, never as chat text.
      if (turn && p.channel !== "tool_call") turn[p.channel] += p.text;
      break;
    case "model_call_ended":
      // AD-2: the `*_ended` payload is authoritative and replaces the deltas.
      if (turn) {
        Object.assign(turn, { callEnded: p, text: p.text, reasoning: p.reasoning });
        lastCall(turn).ended = p;
      }
      break;
    case "tool_started":
      if (turn) {
        Object.assign(turn, {
          phaseLabel: p.phase_label,
          callStartedAt: Date.parse(envelope.ts),
          firstToken: false,
        });
        turn.steps.push({
          type: "tool",
          started: p,
          brick: envelope.brick,
          startedAt: Date.parse(envelope.ts),
          ended: null,
        });
      }
      break;
    case "tool_ended": {
      const tool = turn?.steps.filter((s) => s.type === "tool").at(-1);
      if (tool) tool.ended = p;
      break;
    }
    case "outbound_request": {
      // What a network tool sends out, shown in the step of the tool running it; out of a
      // turn, what an MCP server's discovery sends, shown in its connection step.
      const step = turn
        ? turn.steps.filter((s) => s.type === "tool").at(-1)
        : store.offTurn.filter((s) => `mcp.${s.started.server}` === envelope.component).at(-1);
      if (step && p.origin === "brick") (step.outbound ||= []).push({ ...p, seq: envelope.seq });
      break;
    }
    case "mcp_connect_started":
      store.offTurn.push({
        started: p,
        startedAt: Date.parse(envelope.ts),
        ended: null,
        afterTurn: store.turns.length,
      });
      break;
    case "mcp_connect_ended": {
      // The oldest pending card: connections of one server end in the order they started.
      const step = store.offTurn.find((s) => s.started.server === p.server && !s.ended);
      if (step) step.ended = p;
      break;
    }
    case "tool_call_malformed":
    case "prefix_not_reused":
      if (turn) turn.steps.push({ type: envelope.kind, payload: p });
      break;
    case "limit_reached":
      if (turn) {
        turn.limit = p;
        turn.steps.push({ type: envelope.kind, payload: p });
      }
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

function lastCall(turn) {
  return turn.steps.filter((s) => s.type === "call").at(-1) || {};
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
  renderBricks();
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
const CLEARED_FR =
  "Conversation vidée : le prochain message repart sans historique. Les tours précédents restent dans la trace.";

// ---------- bricks panel: cards, toggles, system prompt drawer ----------

let renderedBricks = null;

function renderBricks() {
  // Rebuilt only when the session sends new cards, so an unfolded explanation stays open.
  if (renderedBricks === store.bricks) return;
  renderedBricks = store.bricks;
  const pane = document.getElementById("bricks");
  // The rebuild would drop keyboard focus: note it, restore it on the new element.
  const focusKey = pane.contains(document.activeElement) ? document.activeElement.dataset.focusKey : null;
  pane.innerHTML = "";
  if (!store.bricks) {
    pane.appendChild(emptyNote("En attente du harnais…"));
    return;
  }
  for (const brick of store.bricks.bricks) {
    const card = el("article", "brick-card");
    card.classList.toggle("is-active", brick.wanted && brick.available);
    card.classList.toggle("is-unavailable", !brick.available);

    const head = el("label", "brick-head");
    const toggle = el("input", "brick-toggle");
    toggle.type = "checkbox";
    toggle.setAttribute("role", "switch");
    toggle.checked = brick.wanted;
    toggle.disabled = !brick.available && !brick.wanted; // a wanted brick can always be turned off
    toggle.dataset.focusKey = `toggle:${brick.id}`;
    toggle.addEventListener("change", () => setBrick(brick.id, toggle.checked));
    head.append(toggle, el("span", "brick-name", brick.label_fr));

    const tags = el("div", "brick-tags");
    tags.appendChild(el("span", "category-chip", brick.category_fr));
    // ponytail: every brick so far is local; the network tag comes with the first network brick.
    if (brick.hosting_fr) tags.appendChild(el("span", "hosting-tag-local", brick.hosting_fr));
    card.append(head, tags);

    if (!brick.available && brick.reason_fr) card.appendChild(el("p", "brick-reason", brick.reason_fr));
    if (brick.pending) card.appendChild(el("p", "brick-pending", "Prend effet au prochain tour"));

    if (brick.options?.length) card.appendChild(brickOptions(brick));
    if (brick.limits_fr) card.appendChild(el("p", "brick-limits", brick.limits_fr));

    if (brick.explanation_fr) {
      const details = el("details", "brick-explanation");
      details.open = store.openExplanations.has(brick.id);
      details.addEventListener("toggle", () => {
        if (details.open) store.openExplanations.add(brick.id);
        else store.openExplanations.delete(brick.id);
      });
      details.append(el("summary", "", "Ce que la brique ajoute"), el("p", "", brick.explanation_fr));
      card.appendChild(details);
    }
    if (brick.id === "system_prompt") {
      const edit = el("button", "brick-edit", "Modifier le prompt");
      edit.type = "button";
      edit.disabled = !brick.available;
      edit.id = "edit-system-prompt";
      edit.dataset.focusKey = "edit";
      edit.addEventListener("click", openDrawer);
      card.appendChild(edit);
    }
    pane.appendChild(card);
  }
  if (focusKey) pane.querySelector(`[data-focus-key="${focusKey}"]`)?.focus();
}

function brickOptions(brick) {
  // Sub-options (EXPERIENCE: brick-card): one switch per tool, with its hosting tag.
  const key = `options:${brick.id}`;
  const details = el("details", "brick-options");
  details.open = store.openExplanations.has(key);
  details.addEventListener("toggle", () => {
    if (details.open) store.openExplanations.add(key);
    else store.openExplanations.delete(key);
  });
  const on = brick.options.filter((o) => o.enabled).length;
  const noun = brick.id === "mcp" ? "Serveurs" : "Outils";
  // The closed card still shows the MCP documentation mode.
  const mode = brick.mode === "lazy" ? ` · ${brick.lazy_label_fr}` : "";
  details.appendChild(
    el("summary", "", `${noun} : ${on} activé${on > 1 ? "s" : ""} sur ${brick.options.length}${mode}`)
  );
  const list = el("ul", "brick-option-list");
  for (const option of brick.options) {
    const row = el("label", "brick-option");
    const toggle = el("input", "brick-toggle");
    toggle.type = "checkbox";
    toggle.setAttribute("role", "switch");
    toggle.checked = option.enabled;
    toggle.dataset.focusKey = `option:${brick.id}:${option.id}`;
    toggle.addEventListener("change", () => setOption(brick.id, option.id, toggle.checked));
    row.append(
      toggle,
      el("span", "brick-option-name", option.label_fr),
      el("span", option.network ? "hosting-tag-network" : "hosting-tag-local", option.hosting_fr)
    );
    const li = el("li");
    li.appendChild(row);
    list.appendChild(li);
  }
  details.appendChild(list);
  if (brick.id === "mcp") {
    // Story 6b: the documentation mode of every server, under the list of servers.
    const row = el("label", "brick-option");
    const toggle = el("input", "brick-toggle");
    toggle.type = "checkbox";
    toggle.setAttribute("role", "switch");
    toggle.checked = brick.mode === "lazy";
    toggle.dataset.focusKey = "option:mcp:lazy";
    toggle.addEventListener("change", () => setOption("mcp_mode", null, toggle.checked));
    row.append(toggle, el("span", "brick-option-name", brick.lazy_label_fr));
    details.appendChild(row);
  }
  return details;
}

async function setOption(brickId, id, enabled) {
  // A tool of the tools brick, a server of the MCP brick, or the MCP documentation mode.
  const [path, body] =
    brickId === "mcp_mode"
      ? ["/api/intentions/mcp_mode", { lazy: enabled }]
      : brickId === "mcp"
        ? ["/api/intentions/mcp_server", { server: id, enabled }]
        : ["/api/intentions/tool", { tool: id, enabled }];
  try {
    const response = await postIntention(path, body);
    if (response.ok) return; // `bricks_changed` redraws the card
  } catch {
    // Fall through: redraw from the last state the session sent.
  }
  renderedBricks = null;
  scheduleRender();
}

async function setBrick(brick, wanted) {
  try {
    const response = await postIntention("/api/intentions/brick", { brick, wanted });
    if (response.ok) return; // `bricks_changed` redraws the card
  } catch {
    // Fall through: redraw from the last state the session sent.
  }
  renderedBricks = null;
  scheduleRender();
}

const drawer = () => document.getElementById("edit-drawer");
const drawerText = () => document.getElementById("drawer-text");

function drawerAlert(text, dirtyChoice = false) {
  const alert = document.getElementById("drawer-alert");
  alert.hidden = !text;
  alert.textContent = text || "";
  document.getElementById("drawer-dirty").hidden = !dirtyChoice;
}

function openDrawer() {
  drawerText().value = store.bricks?.system_prompt.text ?? "";
  drawerAlert(null);
  drawer().hidden = false;
  document.getElementById("bricks").inert = true; // cards under the drawer leave the Tab order
  drawerText().focus();
}

function closeDrawer(force = false) {
  if (!force && drawerText().value !== store.bricks?.system_prompt.text) {
    drawerAlert("Modification non enregistrée. Enregistrer ou abandonner ?", true);
    return;
  }
  drawerAlert(null);
  drawer().hidden = true;
  document.getElementById("bricks").inert = false;
  document.getElementById("edit-system-prompt")?.focus();
}

async function saveSystemPrompt(text) {
  try {
    const response = await postIntention("/api/intentions/system_prompt", { text });
    if (!response.ok) throw new Error();
    const saved = await response.json();
    // The session's answer, so closing right away is not flagged as unsaved.
    if (store.bricks) store.bricks.system_prompt = saved;
    drawerText().value = saved.text;
    drawerAlert(null);
    return true;
  } catch {
    drawerAlert("Enregistrement refusé : WaveStack ne répond pas. Réessayez.");
    return false;
  }
}

async function clearConversation() {
  store.composerError = null;
  try {
    const response = await postIntention("/api/intentions/clear_conversation", {});
    if (!response.ok) {
      const body = await response.json().catch(() => ({}));
      store.composerError = typeof body.detail === "string" ? body.detail : "Action refusée.";
    }
  } catch {
    store.composerError = "WaveStack ne répond pas : la conversation n'a pas été vidée.";
  }
  render();
}

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
      if (turn.limit) return turn.limit.message_fr;
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
  const turns = store.turns.slice(store.chatFrom);
  if (turns.length === 0) {
    chat.appendChild(emptyNote(store.chatFrom ? CLEARED_FR : NO_TURN_FR));
    return;
  }
  for (const turn of turns) {
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
  const clear = document.getElementById("clear-conversation");
  clear.disabled = state?.state !== "idle"; // class (b)
  clear.title = clear.disabled ? state?.reason_fr || "Disponible hors d'un tour." : "";
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

// ---------- orchestration: the turn's steps in their real order (CAP-15, CAP-16) ----------

function stepCard(title, className = "step") {
  const card = el("div", className);
  card.appendChild(el("div", "step-title", title));
  return card;
}

function groupTokens(context, group) {
  return context?.breakdown.find((item) => item.group === group)?.tokens ?? 0;
}

function formatCall(call) {
  const args = Object.entries(call.arguments)
    .map(([name, value]) => `${name}=${JSON.stringify(value)}`)
    .join(", ");
  return `${call.name}(${args})`;
}

function harnessEvent(title, tone, lines) {
  // DESIGN.md harness-event: red for a failure, violet for information.
  const card = el("div", `harness-event is-${tone}`);
  card.appendChild(el("div", "step-title", `${tone === "error" ? "✖" : "ℹ"} ${title}`));
  card.append(...lines);
  return card;
}

function modelCallCards(turn, step, index, calls) {
  const cards = [];
  const context = step.context;
  const catalog = groupTokens(context, "tool_catalog");
  const results = groupTokens(context, "tool_result");
  if (index === 0 && catalog) {
    const count = context.segments.filter((s) => s.kind === "tool_catalog").length;
    const card = stepCard("1. Description des outils");
    const plural = count > 1 ? "s" : "";
    card.appendChild(
      el("p", "", `${count} outil${plural} décrit${plural} au modèle dans le contexte : ${fmt(catalog)} tokens.`)
    );
    cards.push(card);
  }
  if (index > 0 && results) {
    const card = stepCard("4. Réinjection");
    card.appendChild(
      el("p", "", `Résultats d'outils ajoutés au contexte de cet appel : ${fmt(results)} tokens.`)
    );
    cards.push(card);
  }
  const ended = step.ended;
  const last = index === calls.length - 1;
  const isFinal = catalog && ended && !ended.tool_calls.length && last && turn.status === "completed";
  const title = isFinal ? "5. Réponse finale · appel au modèle" : "Appel au modèle";
  const card = stepCard(`${title} · ${step.id ?? turn.id}`);
  let counter = `Entrée : ${fmt(context?.used ?? 0)} tokens`;
  if (ended) {
    counter = `Entrée : ${fmt(ended.prompt_tokens)} tokens · Sortie : ${fmt(ended.output_tokens)} tokens · Temps : ${seconds(ended.duration_ms)}`;
  } else if (step.startedAt) {
    counter += ` · Sortie : … · Temps : ${seconds(Date.now() - step.startedAt)} (en cours)`;
  }
  card.appendChild(el("div", "token-counter number", counter));
  if (ended && ended.stop_reason !== "stop") {
    const reasons = { length: "sortie coupée", cancelled: "arrêté", error: "erreur" };
    card.appendChild(el("span", "step-badge", reasons[ended.stop_reason]));
  }
  cards.push(card);
  if (ended?.tool_calls.length) {
    const ask = stepCard("2. Demande d'outil (décidée par le modèle)");
    for (const call of ended.tool_calls) ask.appendChild(el("pre", "step-code", formatCall(call)));
    cards.push(ask);
  }
  return cards;
}

function toolCard(step) {
  const ended = step.ended;
  // A harness tool (`load_tool_doc`) shows its own step, e.g. « Chargement de la documentation ».
  const harness = step.started.source === "harness";
  const title = harness ? step.started.phase_label : "Exécution par le harnais";
  const card = stepCard(`3. ${title} · ${step.started.tool}`);
  if (step.started.source?.startsWith("mcp") || (harness && step.brick === "mcp")) {
    card.appendChild(el("span", "step-badge is-mcp", "MCP"));
  }
  const asked = { name: step.started.tool, arguments: step.started.arguments };
  card.appendChild(el("pre", "step-code", formatCall(asked)));
  for (const request of step.outbound || []) card.appendChild(outboundPayload(request));
  if (!ended) {
    const running = `En cours… ${seconds(Date.now() - step.startedAt)}`;
    card.appendChild(el("div", "token-counter number", running));
    return card;
  }
  card.appendChild(el("div", "token-counter number", `Temps : ${seconds(ended.duration_ms)}`));
  if (ended.status === "ok") {
    card.append(el("p", "label", "Résultat"), el("pre", "step-code", ended.result));
  } else {
    card.classList.add("is-error");
    card.append(
      el("span", "step-badge", "erreur d'exécution"),
      el("p", "", `${ended.error_fr} L'erreur est réinjectée au modèle ; ce n'est pas un nouvel essai.`)
    );
  }
  return card;
}

function connectCard(step) {
  // MCP discovery, outside any turn: connection, then the tools the server lists.
  const ended = step.ended;
  const card = stepCard(step.started.phase_label);
  card.appendChild(el("span", "step-badge is-mcp", "MCP"));
  for (const request of step.outbound || []) card.appendChild(outboundPayload(request));
  if (!ended) {
    card.appendChild(el("div", "token-counter number", "Connexion en cours…"));
    return card;
  }
  card.appendChild(el("div", "token-counter number", `Temps : ${seconds(ended.duration_ms)}`));
  if (ended.status === "ok") {
    const count = ended.tools.length;
    card.appendChild(el("p", "label", `Outils trouvés : ${count}`));
    if (count) card.appendChild(el("pre", "step-code", ended.tools.join("\n")));
  } else {
    card.classList.add("is-error");
    card.append(el("span", "step-badge", "serveur indisponible"), el("p", "", ended.error_fr));
  }
  return card;
}

function outboundPayload(request) {
  // DESIGN.md outbound-payload: exactly what leaves the workstation, open by default.
  const details = el("details", "outbound-payload");
  details.open = !store.closedPayloads.has(request.seq);
  details.addEventListener("toggle", () => {
    if (details.open) store.closedPayloads.delete(request.seq);
    else store.closedPayloads.add(request.seq);
  });
  const head = el("summary", "outbound-head");
  head.append(el("span", "outbound-tag", "🌐 RÉSEAU"), ` ${request.method} ${request.url}`);
  const body = request.body || "Aucun corps : seule l'adresse sort du poste.";
  details.append(head, el("pre", "step-code", body));
  return details;
}

function malformedCard(p) {
  // The raw output with the faulty part marked (EXPERIENCE: malformed tool call).
  const raw = el("pre", "step-code");
  const at = p.raw.indexOf(p.fragment);
  if (at >= 0) {
    raw.append(p.raw.slice(0, at), el("mark", "", p.fragment), p.raw.slice(at + p.fragment.length));
  } else {
    raw.append(p.raw, "\n", el("mark", "", p.fragment));
  }
  const reaction =
    p.reaction === "retry"
      ? "Réaction du harnais : erreur réinjectée au modèle, nouvel essai."
      : "Réaction du harnais : arrêt du tour, le modèle n'est plus rappelé (plus d'essai possible).";
  return harnessEvent("Appel d'outil mal formé", "error", [
    el("p", "", `Partie fautive : ${p.detail_fr}`),
    el("p", "label", "Sortie brute du modèle"),
    raw,
    el("p", "", reaction),
    el("p", "label", "Décision du harnais (code), pas du modèle"),
  ]);
}

function renderSteps() {
  const steps = document.getElementById("steps");
  steps.innerHTML = "";
  const offTurn = (index) => {
    for (const step of store.offTurn) if (step.afterTurn === index) steps.appendChild(connectCard(step));
  };
  store.turns.forEach((turn, index) => {
    offTurn(index);
    const calls = turn.steps.filter((s) => s.type === "call");
    for (const step of turn.steps) {
      if (step.type === "call") {
        if (turn.overflow && step === calls.at(-1)) continue; // the overflow card replaces it
        steps.append(...modelCallCards(turn, step, calls.indexOf(step), calls));
      } else if (step.type === "tool") {
        steps.appendChild(toolCard(step));
      } else if (step.type === "tool_call_malformed") {
        steps.appendChild(malformedCard(step.payload));
      } else if (step.type === "limit_reached") {
        const text = el("p", "", step.payload.message_fr);
        const tone = step.payload.limit === "retries" ? "error" : "info";
        steps.appendChild(harnessEvent("Borne du tour atteinte", tone, [text]));
      } else if (step.type === "prefix_not_reused") {
        const text = el("p", "", step.payload.message_fr);
        steps.appendChild(harnessEvent("Préfixe non réutilisé", "info", [text]));
      }
    }
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
    }
  });
  offTurn(store.turns.length);
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

const SVG_NS = "http://www.w3.org/2000/svg";

function svgEl(tag, attrs) {
  const node = document.createElementNS(SVG_NS, tag);
  for (const [key, value] of Object.entries(attrs)) node.setAttribute(key, String(value));
  return node;
}

// Brick id -> chip icon in the harness frame (formatting only).
const BRICK_ICONS = { short_memory: "🧠", system_prompt: "📜", tools: "🔧", mcp: "🔌" };
const POSE_LABELS = { idle: "au repos", thinking: "réfléchit", tool: "utilise un outil" };

// The robot's pose, derived from the turn's events only (AD-1).
function robotPose() {
  // Only calls and tools: e.g. a `prefix_not_reused` step lands between a call and its start.
  const step = activeTurn()?.steps.filter((s) => s.type === "call" || s.type === "tool").at(-1);
  if (!step || step.ended) return "idle";
  if (step.type === "tool") return "tool";
  return step.type === "call" && step.startedAt ? "thinking" : "idle";
}

function svgText(text, attrs) {
  const node = svgEl("text", attrs);
  node.textContent = text;
  return node;
}

function svgTitle(text) {
  const title = svgEl("title", {});
  title.textContent = text;
  return title;
}

// The robot mascot (DESIGN.md > arch-model), centred on `cx`.
function robot(cx, pose, modelNode) {
  const g = svgEl("g", { class: `robot${pose === "idle" ? "" : " is-active"}`, role: "img" });
  g.dataset.component = "core.model";
  const name = modelNode?.model ?? null;
  const label = `Modèle${name ? ` ${name}` : ""} : ${POSE_LABELS[pose]}`;
  g.setAttribute("aria-label", label);
  if (store.selection === "core.model") g.classList.add("is-selected");
  g.addEventListener("click", () => select("core.model"));
  const stroke = { class: "robot-face", fill: "none" };
  const face =
    pose === "idle"
      ? [
          svgEl("path", { ...stroke, d: `M${cx - 12} 52 q4 3 8 0` }),
          svgEl("path", { ...stroke, d: `M${cx + 4} 52 q4 3 8 0` }),
        ]
      : [
          svgEl("circle", { class: "robot-eye", cx: cx - 7, cy: 50, r: 2.5 }),
          svgEl("circle", { class: "robot-eye", cx: cx + 7, cy: 50, r: 2.5 }),
        ];
  if (pose === "thinking") {
    for (const dx of [-5, 0, 5]) {
      face.push(svgEl("circle", { class: "robot-eye", cx: cx + dx, cy: 58, r: 1.3 }));
    }
  }
  if (pose === "tool") face.push(svgEl("path", { ...stroke, d: `M${cx - 6} 56 q6 5 12 0` }));
  g.append(
    svgTitle(label),
    svgEl("rect", { class: "robot-stick", x: cx - 1.5, y: 24, width: 3, height: 11, rx: 1.5 }),
    svgEl("circle", { class: "robot-antenna", cx, cy: 22, r: 5 }),
    svgEl("rect", { class: "robot-ear", x: cx - 34, y: 44, width: 9, height: 20, rx: 4.5 }),
    svgEl("rect", { class: "robot-ear", x: cx + 25, y: 44, width: 9, height: 20, rx: 4.5 }),
    svgEl("rect", { class: "robot-body", x: cx - 26, y: 34, width: 52, height: 40, rx: 14 }),
    svgEl("rect", { class: "robot-visor", x: cx - 19, y: 41, width: 38, height: 24, rx: 10 }),
    ...face
  );
  if (pose === "tool") {
    g.append(
      svgEl("circle", { class: "robot-badge", cx: cx + 26, cy: 72, r: 9 }),
      svgText("🔧", { x: cx + 26, y: 76, "text-anchor": "middle", class: "robot-badge-icon" })
    );
  }
  g.appendChild(svgText("Modèle", { x: cx, y: 91, "text-anchor": "middle", class: "robot-label" }));
  if (name) {
    // The frame is narrow: a long file name is cut, the tooltip keeps it whole.
    const short = name.length > 20 ? `${name.slice(0, 19)}…` : name;
    g.appendChild(svgText(short, { x: cx, y: 105, "text-anchor": "middle", class: "robot-model" }));
  }
  return g;
}

let renderedSchemaKey = null;

function renderSchema() {
  // Layout only: nodes, edges and availability come from `architecture_changed` (AD-12),
  // the frame's chips from `bricks_changed`.
  const wanted = (store.bricks?.bricks || []).filter((b) => b.wanted);
  const pose = robotPose();
  // `render()` runs on every `model_delta`: rebuilding would restart the antenna blink.
  const key = JSON.stringify([
    store.architecture,
    wanted.map((b) => [b.id, b.label_fr, b.available, b.reason_fr]),
    pose,
    store.selection,
  ]);
  if (key === renderedSchemaKey) return;
  renderedSchemaKey = key;

  const svg = document.getElementById("schema-svg");
  svg.innerHTML = "";
  const nodes = store.architecture.nodes || [];
  const byId = Object.fromEntries(nodes.map((n) => [n.id, n]));
  // Brick components are the frame's chips; the harness and the model, the frame and the robot.
  const outside = nodes.filter((n) => !["harness", "model", "brick"].includes(n.kind));
  outside.sort((a, b) => (a.kind === "file") - (b.kind === "file"));

  const FX = 4; // harness frame
  const FY = 12;
  const FW = 360;
  const FH = 120;
  const RELIEF = 4;
  const W = 170; // outside nodes: a grid of 3 rows right of the frame, files last
  const H = 38;
  const GAP = 4;
  const COL_GAP = 12;
  const x0 = FX + FW + 40;
  const pos = {};
  outside.forEach((node, i) => {
    pos[node.id] = { x: x0 + Math.floor(i / 3) * (W + COL_GAP), y: FY + (i % 3) * (H + GAP) };
  });
  const cols = Math.ceil(outside.length / 3);
  const width = cols ? x0 + cols * (W + COL_GAP) : FX + FW + RELIEF;
  svg.setAttribute("viewBox", `0 0 ${width} 140`);

  // Edges first: the nodes drawn after mask them.
  for (const edge of store.architecture.edges || []) {
    const a = pos[edge.from];
    if (!a) continue;
    const cls = `arch-edge${edge.crosses_boundary ? " is-network" : ""}`;
    if (edge.to === "core.harness") {
      const y = a.y + H / 2;
      svg.appendChild(svgEl("line", { class: cls, x1: FX + FW, y1: y, x2: a.x, y2: y }));
      continue;
    }
    const b = pos[edge.to];
    if (!b) continue;
    svg.appendChild(
      svgEl("line", { class: cls, x1: a.x + W / 2, y1: a.y + H / 2, x2: b.x + W / 2, y2: b.y + H / 2 })
    );
  }

  const frame = svgEl("g", { class: "arch-harness" });
  frame.dataset.component = "core.harness";
  if (store.selection === "core.harness") frame.classList.add("is-selected");
  frame.addEventListener("click", () => select("core.harness"));
  frame.append(
    svgTitle(byId["core.harness"]?.label_fr || "Harnais"),
    svgEl("rect", { class: "arch-harness-relief", x: FX, y: FY + RELIEF, width: FW, height: FH }),
    svgEl("rect", { class: "arch-harness-frame", x: FX, y: FY, width: FW, height: FH }),
    svgEl("rect", { class: "arch-harness-tag", x: FX + 18, y: FY - 10, width: 72, height: 20 }),
    svgText("Harnais", { x: FX + 54, y: FY + 4, "text-anchor": "middle", class: "arch-harness-tag-text" })
  );
  // Chips alternate left and right of the robot, 3 per column.
  // ponytail: 6 chips at most (3 rows x 2), 124 units wide, labels not truncated; grow FH
  // and the viewBox when a later story adds bricks.
  const CW = 124;
  const CH = 26;
  wanted.forEach((brick, i) => {
    const x = i % 2 ? FX + FW - 12 - CW : FX + 12;
    const y = FY + 16 + Math.floor(i / 2) * (CH + 8);
    const chip = svgEl("g", { class: `arch-chip${brick.available ? "" : " is-unavailable"}` });
    const icon = BRICK_ICONS[brick.id] || "🧩";
    chip.append(
      svgTitle(brick.available ? brick.label_fr : `${brick.label_fr} : ${brick.reason_fr}`),
      svgEl("rect", { x, y, width: CW, height: CH }),
      svgText(`${icon} ${brick.label_fr}`, { x: x + CW / 2, y: y + 17, "text-anchor": "middle" })
    );
    frame.appendChild(chip);
  });
  if (!wanted.length) {
    frame.appendChild(
      svgText("Aucune brique : LLM nu", {
        x: FX + FW / 2,
        y: FY + FH - 7,
        "text-anchor": "middle",
        class: "arch-harness-empty",
      })
    );
  }
  svg.append(frame, robot(FX + FW / 2, pose, byId["core.model"]));

  for (const node of outside) {
    const { x, y } = pos[node.id];
    const g = svgEl("g", { class: "arch-node" });
    g.dataset.component = node.id;
    g.classList.toggle("is-network", node.hosting === "network");
    g.classList.toggle("is-unavailable", !node.available);
    const notContacted = node.contact === "not_contacted";
    g.classList.toggle("is-not-contacted", notContacted);
    if (store.selection === node.id) g.classList.add("is-selected");
    g.addEventListener("click", () => select(node.id));
    let tooltip = node.available ? node.label_fr : `${node.label_fr} : ${node.reason_fr}`;
    if (notContacted) tooltip += " : non contacté";
    // An MCP server lists its tools in its tooltip (AD-12).
    if (node.tools?.length) tooltip += `\nOutils : ${node.tools.join(", ")}`;
    const network = node.hosting === "network";
    // A network node shows its globe; its contact state stays visible under the label.
    const state = notContacted ? "non contacté" : node.contact === "unavailable" ? "indisponible" : "";
    const text = svgText(network ? `🌐 ${node.label_fr}` : node.label_fr, {
      x: x + W / 2,
      y: y + (state ? 16 : H / 2 + 4),
      "text-anchor": "middle",
    });
    g.append(svgTitle(tooltip), svgEl("rect", { x, y, width: W, height: H }), text);
    if (state) {
      g.appendChild(
        svgText(state, { x: x + W / 2, y: y + H - 7, "text-anchor": "middle", class: "arch-node-state" })
      );
    }
    svg.appendChild(g);
  }
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
  document.getElementById("clear-conversation").addEventListener("click", clearConversation);
  document.getElementById("drawer-save").addEventListener("click", () =>
    saveSystemPrompt(drawerText().value)
  );
  document.getElementById("drawer-reset").addEventListener("click", () => saveSystemPrompt(null));
  document.getElementById("drawer-close").addEventListener("click", () => closeDrawer());
  document.getElementById("drawer-dirty-save").addEventListener("click", async () => {
    if (await saveSystemPrompt(drawerText().value)) closeDrawer(true);
  });
  document.getElementById("drawer-dirty-discard").addEventListener("click", () => closeDrawer(true));
  // Local stopwatch anchored on the `*_started` ts, replaced by `duration_ms` (AD-1).
  setInterval(() => {
    if (activeTurn()) {
      renderChat();
      renderSteps();
    }
  }, 250);

  document.addEventListener("keydown", (event) => {
    if (event.key !== "Escape") return;
    if (!drawer().hidden) {
      closeDrawer();
    } else if (!document.getElementById("pane-menu-list").hidden) {
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
    store.bricks = body.bricks_changed;
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
