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
  // `conversation_cleared`: index of the first turn still shown (Vue humain, Contexte LLM,
  // Orchestration), and the seq of the clearing, to hide the MCP connections seen before it.
  chatFrom: 0,
  clearedSeq: null,
  composerError: null,
  bricks: null, // last `bricks_changed` payload: cards and system prompt, as the session computed them
  openExplanations: new Set(), // brick ids whose explanation is unfolded (UI state only)
  closedPayloads: new Set(), // seq of outbound payloads folded by the user (open by default)
  openApprovalPayloads: new Set(), // approval ids whose payload is unfolded in the Vue humain card
  // Harness steps outside any turn (MCP discovery), each placed after the turns seen so far.
  offTurn: [],
  // Orchestration, UI state only (story 8d): the rail follows the live turn until a click
  // freezes it; what the user unfolded; the event log, folded until asked.
  orch: {
    live: true,
    userOpen: new Set(), // step keys unfolded by the user (frozen view)
    turnOpen: new Map(), // turn id -> unfolded, when the user chose
    selected: null, // the step key last clicked
    current: null, // the live step's key, computed at each render
    currentSticky: false,
    prepGroupOpen: true,
    prepOpen: new Set(), // MCP connection lines unfolded
    logOpen: false,
    logRowsOpen: new Set(), // event log rows whose JSON is shown, by first seq
  },
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
  // ponytail: DESIGN.md has no hook colour yet; the harness violet keeps it apart from the message.
  hook_injection: "--color-primary",
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
      // Past turns leave the Vue humain, Contexte LLM and Orchestration; the event list keeps them.
      store.chatFrom = store.turns.length;
      store.clearedSeq = envelope.seq;
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
          component: envelope.component, // the schema node in action
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
        seq: envelope.seq, // `afterTurn` alone cannot tell a connection just before a clearing
      });
      break;
    case "mcp_connect_ended": {
      // The oldest pending card: connections of one server end in the order they started.
      const step = store.offTurn.find((s) => s.started.server === p.server && !s.ended);
      if (step) step.ended = p;
      break;
    }
    case "hook_decided":
      // A hook decision is a step of its own (AD-13): a blocked tool has no step at all.
      if (turn) turn.steps.push({ type: "hook", payload: p, component: envelope.component, lines: [] });
      break;
    case "effect_applied": {
      // The lines H2 appended to the audit log, shown in its own step.
      const step = turn?.steps.filter((s) => s.type === "hook").at(-1);
      if (step) step.lines.push(...p.lines);
      break;
    }
    case "approval_requested": {
      // H5: the validation asked, shown in its hook's step; the indicator waits for it.
      const step = turn?.steps.filter((s) => s.type === "hook").at(-1);
      if (step) {
        step.approval = p;
        step.component ||= envelope.component;
      }
      if (turn) {
        Object.assign(turn, {
          phaseLabel: "En attente de validation",
          callStartedAt: Date.parse(envelope.ts),
          firstToken: false,
        });
      }
      break;
    }
    case "approval_resolved": {
      const step = turn?.steps.find((s) => s.approval?.approval_id === p.approval_id);
      if (step) step.resolved = p;
      if (turn) turn.phaseLabel = null;
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
  "Conversation vidée : le prochain message repart sans historique. Les tours précédents restent dans le journal des événements (replié, en bas d'Orchestration).";

// The turns still shown after the last `conversation_cleared`, and whether one happened.
const shownTurns = () => store.turns.slice(store.chatFrom);
const cleared = () => store.clearedSeq !== null;

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
  const noun = { mcp: "Serveurs", skills: "Skills", hooks: "Hooks" }[brick.id] || "Outils";
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
  // A tool of the tools brick, a server of the MCP brick, the MCP documentation mode, a
  // skill of the skills brick, or a hook of the hooks brick.
  const [path, body] =
    brickId === "mcp_mode"
      ? ["/api/intentions/mcp_mode", { lazy: enabled }]
      : brickId === "mcp"
        ? ["/api/intentions/mcp_server", { server: id, enabled }]
        : brickId === "skills"
          ? ["/api/intentions/skill", { skill: id, enabled }]
          : brickId === "hooks"
            ? ["/api/intentions/hook", { hook: id, enabled }]
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

// H5 cards of the Vue humain, kept between renders while their state is unchanged: the
// 250 ms stopwatch would otherwise swap the buttons under the pointer and lose a click.
let approvalCards = new Map(); // approval id -> { key, node }

function renderChat() {
  const chat = document.getElementById("chat");
  const followTail = chat.scrollHeight - chat.scrollTop - chat.clientHeight < 40;
  // The rebuild could drop keyboard focus: note it, restore it on the new element.
  const focusKey = chat.contains(document.activeElement) ? document.activeElement.dataset.focusKey : null;
  const nodes = [];
  const cards = new Map();
  const turns = shownTurns();
  if (turns.length === 0) nodes.push(emptyNote(cleared() ? CLEARED_FR : NO_TURN_FR));
  for (const turn of turns) {
    nodes.push(el("div", "bubble bubble-user", turn.message));
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
    nodes.push(answer);
    // H5: the validation is the user's to give, in the thread of its turn, under the answer.
    for (const step of turn.steps) {
      if (step.type !== "hook" || !step.approval) continue;
      const id = step.approval.approval_id;
      const key = JSON.stringify([
        step.resolved,
        store.sessionState?.state === "awaiting_human",
        Boolean(step.answering),
        toolLabel(step.approval.tool),
      ]);
      const kept = approvalCards.get(id);
      const card = kept?.key === key ? kept : { key, node: approvalCard(step) };
      cards.set(id, card);
      nodes.push(card.node);
    }
  }
  approvalCards = cards;
  patchChildren(chat, nodes);
  if (focusKey && !chat.contains(document.activeElement)) {
    let target = chat.querySelector(`[data-focus-key="${cssEscape(focusKey)}"]`);
    // An answered approval disables, then removes, its buttons: focus goes to its card.
    if ((!target || target.disabled) && focusKey.startsWith("approval:")) {
      const cardKey = focusKey.slice(0, focusKey.lastIndexOf(":"));
      target = chat.querySelector(`[data-focus-key="${cssEscape(cardKey)}"]`);
    }
    target?.focus();
  }
  if (followTail) chat.scrollTop = chat.scrollHeight;
}

function patchChildren(parent, nodes) {
  // Replace the children with `nodes` without moving a node kept in place: moving it would
  // blur it and drop a click between mousedown and mouseup.
  const keep = new Set(nodes);
  for (const child of [...parent.childNodes]) if (!keep.has(child)) child.remove();
  nodes.forEach((node, i) => {
    if (parent.childNodes[i] !== node) parent.insertBefore(node, parent.childNodes[i] ?? null);
  });
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
  stop.hidden = state?.state !== "turn" && state?.state !== "awaiting_human";
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
  const turn = shownTurns().reverse().find((t) => t.context);
  if (!turn) {
    pane.appendChild(emptyNote(cleared() ? CLEARED_FR : NO_TURN_FR));
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

// ---------- orchestration: steps grouped by turn, in their real order (CAP-15, CAP-16, story 8d) ----------
// The bodies below are the content of the former step cards: each is now the unfolded part
// of one line of the rail.

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

// A stopwatch inside an unfolded body: its text is refreshed in place (`refreshTicks`), so
// the 250 ms tick never rebuilds the body under the pointer.
function tick(since) {
  const span = el("span", "tick", seconds(Date.now() - since));
  span.dataset.since = String(since);
  return span;
}

function refreshTicks(root) {
  for (const node of root.querySelectorAll("[data-since]")) {
    setText(node, seconds(Date.now() - Number(node.dataset.since)));
  }
}

function setText(node, text) {
  if (node.textContent !== text) node.textContent = text;
}

function hostOf(url) {
  try {
    return new URL(url).host;
  } catch {
    return url;
  }
}

function catalogBody(context, tokens) {
  const count = context.segments.filter((s) => s.kind === "tool_catalog").length;
  const plural = count > 1 ? "s" : "";
  return [el("p", "", `${count} outil${plural} décrit${plural} au modèle dans le contexte : ${fmt(tokens)} tokens.`)];
}

function callBody(turn, step) {
  const context = step.context;
  const ended = step.ended;
  const counter = el("div", "token-counter number");
  if (ended) {
    counter.textContent = `Entrée : ${fmt(ended.prompt_tokens)} tokens · Sortie : ${fmt(ended.output_tokens)} tokens · Temps : ${seconds(ended.duration_ms)}`;
  } else if (step.startedAt) {
    counter.append(`Entrée : ${fmt(context?.used ?? 0)} tokens · Sortie : … · Temps : `, tick(step.startedAt), " (en cours)");
  } else {
    counter.textContent = `Entrée : ${fmt(context?.used ?? 0)} tokens`;
  }
  const nodes = [el("p", "label", `Appel ${step.id ?? turn.id}`), counter];
  if (ended && ended.stop_reason !== "stop") {
    const reasons = { length: "sortie coupée", cancelled: "arrêté", error: "erreur" };
    nodes.push(el("span", "step-badge", reasons[ended.stop_reason]));
  }
  return nodes;
}

function toolBody(step) {
  const ended = step.ended;
  // A harness tool (`load_tool_doc`, `load_skill`) says the model triggered it (EXPERIENCE:
  // trigger badge).
  const harness = step.started.source === "harness";
  const nodes = [];
  if (step.started.source?.startsWith("mcp") || (harness && step.brick === "mcp")) {
    nodes.push(el("span", "step-badge is-mcp", "MCP"));
  }
  if (step.brick === "skills") nodes.push(el("span", "step-badge is-skill", "Skill"));
  if (harness) {
    const icon = el("span", "", "🤖 ");
    icon.setAttribute("aria-hidden", "true"); // the label alone is read aloud
    const badge = el("span", "trigger-badge-model");
    badge.append(icon, "Déclenché par le modèle");
    nodes.push(badge);
  }
  const asked = { name: step.started.tool, arguments: step.started.arguments };
  nodes.push(el("pre", "step-code", formatCall(asked)));
  for (const request of step.outbound || []) nodes.push(outboundPayload(request));
  if (!ended) {
    const running = el("div", "token-counter number", "En cours… ");
    running.appendChild(tick(step.startedAt));
    nodes.push(running);
    return nodes;
  }
  nodes.push(el("div", "token-counter number", `Temps : ${seconds(ended.duration_ms)}`));
  if (ended.status === "ok") {
    nodes.push(el("p", "label", "Résultat"), el("pre", "step-code", ended.result));
  } else {
    nodes.push(
      el("span", "step-badge", "erreur d'exécution"),
      el("p", "", `${ended.error_fr} L'erreur est réinjectée au modèle ; ce n'est pas un nouvel essai.`)
    );
  }
  return nodes;
}

function connectBody(step) {
  // MCP discovery, outside any turn: connection, then the tools the server lists.
  const ended = step.ended;
  const nodes = [el("span", "step-badge is-mcp", "MCP"), el("p", "", step.started.phase_label)];
  for (const request of step.outbound || []) nodes.push(outboundPayload(request));
  if (!ended) {
    nodes.push(el("div", "token-counter number", "Connexion en cours…"));
    return nodes;
  }
  nodes.push(el("div", "token-counter number", `Temps : ${seconds(ended.duration_ms)}`));
  if (ended.status === "ok") {
    const count = ended.tools.length;
    nodes.push(el("p", "label", `Outils trouvés : ${count}`));
    if (count) nodes.push(el("pre", "step-code", ended.tools.join("\n")));
  } else {
    nodes.push(el("span", "step-badge", "serveur indisponible"), el("p", "", ended.error_fr));
  }
  return nodes;
}

function overflowCard(overflow) {
  const card = el("div", "overflow-card");
  card.append(
    el("h3", "", "⚠ Contexte dépassé — l'appel au modèle n'a pas été envoyé"),
    el("p", "number", `${fmt(overflow.used)} / ${fmt(overflow.usable)} tokens`),
    el("p", "", overflow.message_fr),
    el("p", "label", "En production, un harnais pourrait")
  );
  const list = el("ul");
  for (const strategy of overflow.strategies_fr) list.appendChild(el("li", "", strategy));
  card.appendChild(list);
  return card;
}

function outboundPayload(request, openSet = null) {
  // DESIGN.md outbound-payload: exactly what leaves the workstation, open by default in the
  // trace; given `openSet` (the ids unfolded by the user), folded by default.
  const details = el("details", "outbound-payload");
  details.open = openSet ? openSet.has(request.seq) : !store.closedPayloads.has(request.seq);
  details.addEventListener("toggle", () => {
    if (openSet) {
      if (details.open) openSet.add(request.seq);
      else openSet.delete(request.seq);
    } else if (details.open) store.closedPayloads.delete(request.seq);
    else store.closedPayloads.add(request.seq);
  });
  const head = el("summary", "outbound-head");
  head.append(el("span", "outbound-tag", "🌐 RÉSEAU"), ` ${request.method} ${request.url}`);
  const body = request.body || "Aucun corps : seule l'adresse sort du poste.";
  details.append(head, el("pre", "step-code", body));
  return details;
}

const HOOK_DECISIONS = {
  allow: "laissé passer",
  modify: "modifié",
  block: "bloqué",
  ask_human: "validation humaine demandée",
};
const APPROVAL_DECISIONS = { approved: "Autorisé", refused: "Refusé", cancelled: "Annulé : tour arrêté" };

function toolLabel(name) {
  // Formatting only (AD-1): the label the bricks panel already shows for this tool.
  const option = (brickId, id) =>
    store.bricks?.bricks.find((b) => b.id === brickId)?.options?.find((o) => o.id === id);
  const native = option("tools", name);
  if (native) return native.label_fr;
  const at = name.indexOf("__"); // an MCP tool: `server__tool`
  const server = at > 0 ? option("mcp", name.slice(0, at)) : null;
  return server ? `${name.slice(at + 2)} (${server.label_fr})` : name;
}

function approvalDecision(resolved) {
  return `${APPROVAL_DECISIONS[resolved.decision]}${resolved.hook_disabled ? " · H5 désactivé" : ""}`;
}

function approvalCard(step) {
  // H5 in the Vue humain: tool, destination, what would leave the workstation, then the three
  // buttons while it waits, or the decision once answered (EXPERIENCE: human validation).
  const a = step.approval;
  const lines = [
    el("p", "", `Outil : ${toolLabel(a.tool)} · Destination : ${a.destination}`),
    outboundPayload({ ...a.preview, seq: a.approval_id }, store.openApprovalPayloads),
  ];
  if (step.resolved) {
    lines.push(el("p", "", `Décision : ${approvalDecision(step.resolved)}`));
  } else {
    const actions = el("div", "drawer-actions approval-actions");
    const answer = async (approved, disableHook) => {
      if (step.answering) return;
      step.answering = true; // one answer per click, even across re-renders
      render();
      try {
        const response = await postIntention("/api/intentions/approval", {
          approval_id: a.approval_id,
          approved,
          disable_hook: disableHook,
        });
        if (!response.ok) {
          const body = await response.json().catch(() => ({}));
          store.composerError = typeof body.detail === "string" ? body.detail : "Réponse refusée.";
          step.answering = false;
        }
      } catch {
        store.composerError = "WaveStack ne répond pas : la réponse n'a pas été transmise.";
        step.answering = false;
      }
      render();
    };
    const waiting = store.sessionState?.state === "awaiting_human";
    for (const [label, approved, disableHook, primary, key] of [
      ["Autoriser", true, false, true, "allow"],
      ["Refuser", false, false, false, "refuse"],
      ["Autoriser et ne plus demander", true, true, false, "allow-always"],
    ]) {
      const button = el("button", primary ? "primary" : "", label);
      button.type = "button";
      button.disabled = !waiting || Boolean(step.answering);
      button.dataset.focusKey = `approval:${a.approval_id}:${key}`;
      button.addEventListener("click", () => answer(approved, disableHook));
      actions.appendChild(button);
    }
    lines.push(actions);
  }
  const title = step.resolved ? "Validation humaine" : "En attente de votre validation";
  const card = harnessEvent(title, "info", lines);
  card.classList.add("approval-card");
  card.tabIndex = -1; // receives the focus of its buttons once they are disabled or gone
  card.dataset.focusKey = `approval:${a.approval_id}`;
  return card;
}

function approvalTrace(step) {
  // The same validation in Orchestration, read only: the answer is given in the Vue humain.
  const a = step.approval;
  const label = toolLabel(a.tool);
  const decision = step.resolved
    ? approvalDecision(step.resolved)
    : "En attente de votre réponse dans la Vue humain";
  return [
    el("p", "", `Outil : ${label}${label === a.tool ? "" : ` (${a.tool})`} · Destination : ${a.destination}`),
    outboundPayload({ ...a.preview, seq: a.approval_id }),
    el("p", "", `Décision : ${decision}`),
  ];
}

function hookCard(step) {
  // EXPERIENCE: violet when the hook lets through, modifies or asks, red when it blocks.
  const p = step.payload;
  const block = p.decision === "block";
  const title = step.approval
    ? step.resolved
      ? "Validation humaine"
      : "En attente de votre validation"
    : block
      ? `Bloqué par le hook ${p.hook_fr.toLowerCase()}`
      : `Hook : ${p.point_fr.toLowerCase()}`;
  const lines = [
    el("p", "", `Point d'accroche : ${p.point_fr} · Hook : ${p.hook_fr}`),
    el("p", "", `Décision : ${HOOK_DECISIONS[p.decision]}. ${p.detail_fr}`),
  ];
  if (block) {
    const effect =
      p.point === "before_tool"
        ? "Effet sur le tour : l'outil ne s'exécute pas ; le refus est réinjecté au modèle, qui reprend la main (ce n'est pas un nouvel essai)."
        : "Effet sur le tour : le tour s'arrête ici.";
    lines.push(el("p", "", effect));
  }
  if (step.approval) lines.push(...approvalTrace(step));
  if (step.lines.length) {
    lines.push(el("p", "label", "Lignes ajoutées au journal d'audit"), el("pre", "step-code", step.lines.join("\n")));
  }
  const origin = step.approval
    ? "Décision demandée par le harnais (code), pas par le modèle"
    : "Décision du harnais (code), pas du modèle";
  lines.push(el("p", "label", origin));
  return harnessEvent(title, block ? "error" : "info", lines);
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

// ---------- orchestration rail (EXPERIENCE: turn-rail, turn-group, turn-step, harness-prep) ----------

const ACTORS = {
  model: ["is-model", "🤖 modèle"],
  harness: ["is-harness", "⚙ harnais"],
  user: ["is-user", "👤 vous"],
};
const HOOK_ICONS = { h1: "🛡", h2: "📝", h3: "💉", h5: "✋" };
const TURN_STATUS = {
  completed: ["is-done", "terminé"],
  cancelled: ["is-done", "arrêté"],
  overflow: ["is-failed", "contexte dépassé"],
  limit: ["is-failed", "limite atteinte"],
  blocked: ["is-failed", "bloqué"],
  error: ["is-failed", "erreur"],
};
const LIMITS = { calls: "limite d'appels", retries: "limite d'essais", sub_calls: "limite de sous-appels" };
const APPROVAL_FIGURES = { approved: "autorisé", refused: "refusé", cancelled: "annulé" };

function plural(count, word) {
  return `${fmt(count)} ${word}${count > 1 ? "s" : ""}`;
}

// One line per step (DESIGN.md turn-step). A row: key (stable across renders), icon, title,
// actor, key figure, network host, tone, `sticky` (stays unfolded whatever happens), `sig`
// (the body is rebuilt only when it changes) and `body` (the former card's content).
function turnRows(turn) {
  const rows = [];
  const calls = turn.steps.filter((s) => s.type === "call");
  turn.steps.forEach((step, i) => {
    const key = `${turn.id}:${i}`;
    if (step.type === "call") {
      if (turn.overflow && step === calls.at(-1)) return; // the overflow row replaces it
      const index = calls.indexOf(step);
      const context = step.context;
      const catalog = groupTokens(context, "tool_catalog");
      const results = groupTokens(context, "tool_result");
      if (index === 0 && catalog) {
        rows.push({
          key: `${key}:catalog`,
          icon: "🧰",
          title: "Description des outils",
          actor: "harness",
          figure: `${fmt(catalog)} tokens`,
          sig: catalog,
          body: () => catalogBody(context, catalog),
        });
      }
      if (index > 0 && results) {
        rows.push({
          key: `${key}:reinject`,
          icon: "↩",
          title: "Réinjection",
          actor: "harness",
          figure: `+${fmt(results)} tokens`,
          sig: results,
          body: () => [el("p", "", `Résultats d'outils ajoutés au contexte de cet appel : ${fmt(results)} tokens.`)],
        });
      }
      const ended = step.ended;
      const last = index === calls.length - 1;
      const isFinal = catalog && ended && !ended.tool_calls.length && last && turn.status === "completed";
      let figure = `${fmt(context?.used ?? 0)} lus`;
      if (ended) {
        figure = `${fmt(ended.prompt_tokens)} lus · ${fmt(ended.output_tokens)} écrits · ${seconds(ended.duration_ms)}`;
        const stopped = { length: "sortie coupée", cancelled: "arrêté" }[ended.stop_reason];
        if (stopped) figure += ` · ${stopped}`;
      } else if (step.startedAt) {
        figure += ` · ${seconds(Date.now() - step.startedAt)}`;
      }
      rows.push({
        key: `${key}:call`,
        icon: isFinal ? "💬" : "🤖",
        title: isFinal ? "Réponse finale" : "Appel au modèle",
        actor: "model",
        figure,
        tone: ended && ended.stop_reason === "error" ? "error" : null,
        sticky: Boolean(ended && ended.stop_reason === "error"),
        sig: [Boolean(ended), step.startedAt],
        body: () => callBody(turn, step),
      });
      if (ended?.tool_calls.length) {
        const asked = ended.tool_calls;
        rows.push({
          key: `${key}:ask`,
          icon: "🗨",
          title: "Demande d'outil",
          actor: "model",
          figure: asked.length > 1 ? plural(asked.length, "outil") : asked[0].name,
          sig: asked.length,
          body: () => asked.map((call) => el("pre", "step-code", formatCall(call))),
        });
      }
    } else if (step.type === "tool") {
      const ended = step.ended;
      const harness = step.started.source === "harness";
      let figure = `en cours · ${seconds(Date.now() - step.startedAt)}`;
      if (ended) figure = `${ended.status === "ok" ? "OK" : "erreur"} · ${seconds(ended.duration_ms)}`;
      rows.push({
        key,
        icon: harness ? (step.brick === "skills" ? "📘" : "📖") : "🔧",
        title: harness ? step.started.phase_label : `Exécution · ${toolLabel(step.started.tool)}`,
        actor: harness ? "model" : "harness",
        figure,
        net: step.outbound?.length ? hostOf(step.outbound[0].url) : null,
        tone: ended && ended.status !== "ok" ? "error" : null,
        sticky: Boolean(ended && ended.status !== "ok"),
        sig: [Boolean(ended), ended?.status, step.outbound?.length ?? 0],
        body: () => toolBody(step),
      });
    } else if (step.type === "hook") {
      const p = step.payload;
      const block = p.decision === "block";
      const pending = Boolean(step.approval && !step.resolved);
      let figure = HOOK_DECISIONS[p.decision];
      if (step.approval) figure = step.resolved ? APPROVAL_FIGURES[step.resolved.decision] : "en attente";
      rows.push({
        key,
        icon: HOOK_ICONS[p.hook] || "🪝",
        title: step.approval ? "Validation humaine" : `Hook ${p.hook.toUpperCase()} · ${p.hook_fr}`,
        actor: step.approval ? "user" : "harness",
        figure,
        net: step.approval ? step.approval.destination : null,
        tone: block ? "error" : pending ? "pending" : "hook",
        sticky: block || pending,
        sig: [p, step.approval, step.resolved, step.lines.length, toolLabel(step.approval?.tool ?? "")],
        body: () => [hookCard(step)],
      });
    } else if (step.type === "tool_call_malformed") {
      rows.push({
        key,
        icon: "✖",
        title: "Appel d'outil mal formé",
        actor: "harness",
        figure: step.payload.reaction === "retry" ? "nouvel essai" : "tour arrêté",
        tone: "error",
        sticky: true,
        sig: 1,
        body: () => [malformedCard(step.payload)],
      });
    } else if (step.type === "limit_reached") {
      const retries = step.payload.limit === "retries";
      rows.push({
        key,
        icon: retries ? "✖" : "⏹",
        title: "Borne du tour atteinte",
        actor: "harness",
        figure: LIMITS[step.payload.limit] || step.payload.limit,
        tone: retries ? "error" : "hook",
        sticky: retries,
        sig: 1,
        body: () => [harnessEvent("Borne du tour atteinte", retries ? "error" : "info", [el("p", "", step.payload.message_fr)])],
      });
    } else if (step.type === "prefix_not_reused") {
      rows.push({
        key,
        icon: "ℹ",
        title: "Préfixe non réutilisé",
        actor: "harness",
        figure: `${fmt(step.payload.common_tokens)} tokens communs`,
        tone: "hook",
        sig: 1,
        body: () => [harnessEvent("Préfixe non réutilisé", "info", [el("p", "", step.payload.message_fr)])],
      });
    }
  });
  if (turn.overflow) {
    rows.push({
      key: `${turn.id}:overflow`,
      icon: "✖",
      title: "Contexte dépassé",
      actor: "harness",
      figure: `${fmt(turn.overflow.used)} / ${fmt(turn.overflow.usable)} tokens`,
      tone: "error",
      sticky: true,
      sig: 1,
      body: () => [overflowCard(turn.overflow)],
    });
  }
  return rows;
}

function mcpServerLabel(server) {
  const option = store.bricks?.bricks.find((b) => b.id === "mcp")?.options?.find((o) => o.id === server);
  return option?.label_fr ?? server;
}

function connectRow(step) {
  // The same line in the harness preparation and between two turns (EXPERIENCE: harness-prep).
  const ended = step.ended;
  const failed = ended?.status === "error";
  let figure = "connexion…";
  if (ended) figure = failed ? "indisponible" : `connecté · ${plural(ended.tools.length, "outil")}`;
  return {
    key: `mcp:${step.seq}`,
    icon: failed ? "⊘" : "🔌",
    title: mcpServerLabel(step.started.server),
    note: failed ? ended.error_fr : "",
    actor: "harness",
    figure,
    net: step.outbound?.length ? hostOf(step.outbound[0].url) : null,
    tone: failed ? "unavailable" : null,
    sig: [ended, step.outbound?.length ?? 0],
    body: () => connectBody(step),
  };
}

// DOM nodes kept from one render to the next, by stable key: the 250 ms tick only updates
// their text, so a click or a key press on a line is never lost and the focus stays on it.
const railNodes = new Map(); // row key -> line and body nodes
const groupNodes = new Map(); // turn id (or "prep", "off:N") -> group nodes
const turnDurations = new WeakMap(); // turn -> `turn_ended.payload.duration_ms`
let seenTurns = 0;
let wasRunning = false; // the last turn ran at the previous render

function stepNode(row, open, flags) {
  let node = railNodes.get(row.key);
  if (!node) {
    const root = el("div", "turn-step");
    const line = el("button", "turn-step-line");
    line.type = "button";
    const parts = {
      tile: el("span", "turn-step-tile"),
      title: el("span", "turn-step-title"),
      actor: el("span", "turn-step-actor"),
      netMark: el("span", "net-mark", "🌐 RÉSEAU →"),
      netHost: el("span", "net-host"),
      figure: el("span", "turn-step-figure"),
      chevron: el("span", "turn-step-chevron"),
    };
    parts.tile.setAttribute("aria-hidden", "true");
    parts.chevron.setAttribute("aria-hidden", "true");
    line.append(...Object.values(parts));
    // Name and note share one span: they truncate together, before the host (A10).
    parts.name = el("span", "turn-step-name");
    parts.note = el("span", "turn-step-note");
    parts.title.append(parts.name, parts.note);
    const key = row.key;
    line.addEventListener("click", () => toggleStep(key));
    root.appendChild(line);
    node = { root, line, ...parts, body: null, bodySig: null };
    railNodes.set(key, node);
  }
  node.seen = true;
  node.sticky = Boolean(row.sticky);
  setText(node.tile, row.icon);
  setText(node.name, row.title);
  setText(node.note, row.note ? ` · ${row.note}` : "");
  node.note.hidden = !row.note;
  const [actorClass, actorLabel] = ACTORS[row.actor];
  node.actor.className = `turn-step-actor ${actorClass}`;
  setText(node.actor, actorLabel);
  node.netMark.hidden = !row.net;
  node.netHost.hidden = !row.net;
  setText(node.netHost, row.net || "");
  setText(node.figure, row.figure);
  setText(node.chevron, open ? "▾" : "▸");
  // The whole title in the tooltip: the line truncates it first (A10).
  const tooltip = [row.title, row.note, row.net ? `RÉSEAU → ${row.net}` : "", row.figure].filter(Boolean).join(" · ");
  if (node.line.title !== tooltip) node.line.title = tooltip;
  node.line.setAttribute("aria-expanded", String(open));
  const classes = ["turn-step"];
  if (row.tone) classes.push(`tone-${row.tone}`);
  if (flags.current) classes.push("is-current");
  if (flags.selected) classes.push("is-selected");
  const className = classes.join(" ");
  if (node.root.className !== className) node.root.className = className;
  if (open) {
    const sig = JSON.stringify(row.sig);
    if (!node.body || node.bodySig !== sig) {
      const body = el("div", "turn-step-body");
      body.append(...row.body());
      if (node.body) node.body.replaceWith(body);
      else node.root.appendChild(body);
      node.body = body;
      node.bodySig = sig;
    }
    refreshTicks(node.body);
  } else if (node.body) {
    node.body.remove();
    node.body = null;
    node.bodySig = null;
  }
  return node.root;
}

function groupNode(id, className, onToggle) {
  let node = groupNodes.get(id);
  if (!node) {
    const root = el("section", className);
    const head = el("button", "turn-group-head");
    head.type = "button";
    const chevron = el("span", "turn-group-chevron");
    chevron.setAttribute("aria-hidden", "true");
    head.appendChild(chevron);
    head.addEventListener("click", onToggle);
    const list = el("div", "turn-steps");
    root.appendChild(head);
    node = { root, head, chevron, list };
    groupNodes.set(id, node);
  }
  node.seen = true;
  return node;
}

function fillGroup(node, open, rowNodes) {
  setText(node.chevron, open ? "▾" : "▸");
  node.head.setAttribute("aria-expanded", String(open));
  if (open) {
    patchChildren(node.list, rowNodes);
    if (!node.list.isConnected) node.root.appendChild(node.list);
  } else {
    node.list.remove();
  }
}

function headParts(node, parts) {
  // The head's spans, created once: [className, text] each, `null` text hides the span.
  node.parts ||= parts.map(([className]) => {
    const span = el("span", className);
    node.head.appendChild(span);
    return span;
  });
  parts.forEach(([className, text], i) => {
    const span = node.parts[i];
    if (span.className !== className) span.className = className;
    span.hidden = text === null;
    setText(span, text ?? "");
  });
}

function turnDuration(turn) {
  if (turn.status === null) return Date.now() - turn.startedAt;
  if (!turnDurations.has(turn)) {
    // Formatting only: the duration the session measured, read back from the journal.
    const ended = store.journal.findLast((e) => e.kind === "turn_ended" && e.turn_id === turn.id);
    turnDurations.set(turn, ended?.payload.duration_ms ?? null);
  }
  return turnDurations.get(turn);
}

function toggleSet(set, key) {
  if (set.has(key)) set.delete(key);
  else set.add(key);
}

function toggleStep(key) {
  const o = store.orch;
  if (key.startsWith("mcp:")) {
    toggleSet(o.prepOpen, key); // a connection line: no live to freeze
  } else if (railNodes.get(key)?.sticky) {
    o.selected = key; // stays unfolded whatever happens: no toggle, the live view goes on
  } else {
    // A click freezes the view (EXPERIENCE: direct par défaut); the live step stays open.
    if (o.live) {
      o.live = false;
      o.userOpen = new Set(o.current && !o.currentSticky ? [o.current] : []);
    }
    toggleSet(o.userOpen, key);
    o.selected = key;
  }
  renderSteps();
}

function toggleTurn(id, open) {
  store.orch.turnOpen.set(id, !open);
  renderSteps();
}

function followLive() {
  const o = store.orch;
  o.live = true;
  o.userOpen.clear();
  o.turnOpen.clear();
  o.selected = null;
  renderSteps();
  const scroll = document.getElementById("orch-scroll");
  scroll.scrollTop = scroll.scrollHeight;
}

function renderOrchWorking() {
  // EXPERIENCE: working-indicator, also in Orchestration's header, phase and stopwatch.
  const box = document.getElementById("orch-working");
  const turn = activeTurn();
  box.hidden = !turn;
  if (!turn) return;
  let label = turn.phaseLabel || "Préparation du contexte";
  if (turn.stopRequested) label = "Arrêt demandé";
  else if (turn.firstToken) label = "Génération de la réponse";
  const since = turn.callStartedAt ?? turn.startedAt;
  setText(document.getElementById("orch-working-label"), `${label}… ${seconds(Date.now() - since)}`);
}

let orchEmptyNote = null;

function renderSteps() {
  const o = store.orch;
  const scroll = document.getElementById("orch-scroll");
  const atBottom = scroll.scrollHeight - scroll.scrollTop - scroll.clientHeight < 40;
  const shown = shownTurns();
  // A new turn in live mode: the previous one folds back to its head.
  if (store.turns.length > seenTurns && o.live) o.turnOpen.clear();
  seenTurns = store.turns.length;
  for (const node of railNodes.values()) node.seen = false;
  for (const node of groupNodes.values()) node.seen = false;

  // Only what follows the last clearing (Q1: MCP connections before it are hidden too).
  const connections = (index) =>
    store.offTurn.filter((s) => s.afterTurn === index && (!cleared() || s.seq > store.clearedSeq));
  const connectNodes = (steps) => steps.map((s) => stepNode(connectRow(s), o.prepOpen.has(`mcp:${s.seq}`), {}));

  // The current step: the last line of the last turn shown, unfolded and followed in live.
  const lastTurn = shown.at(-1);
  const lastOpen = lastTurn && (o.turnOpen.has(lastTurn.id) ? o.turnOpen.get(lastTurn.id) : true);
  const lastRows = lastOpen ? turnRows(lastTurn) : [];
  const currentRow = lastRows.at(-1);
  o.current = currentRow?.key ?? null;
  o.currentSticky = Boolean(currentRow?.sticky);
  const running = Boolean(lastTurn && lastTurn.status === null);

  const top = [];
  const prep = connections(store.chatFrom);
  if (prep.length) {
    const node = groupNode("prep", "turn-group harness-prep", () => {
      o.prepGroupOpen = !o.prepGroupOpen;
      renderSteps();
    });
    const down = prep.filter((s) => s.ended?.status === "error").length;
    headParts(node, [
      ["turn-group-title", "Préparation du harnais"],
      ["turn-group-summary", `${plural(prep.length, "connexion")} MCP${down ? ` · ${down} indisponible${down > 1 ? "s" : ""}` : ""}`],
    ]);
    fillGroup(node, o.prepGroupOpen, connectNodes(prep));
    top.push(node.root);
  }
  if (!shown.length) {
    orchEmptyNote ||= emptyNote("");
    setText(
      orchEmptyNote,
      cleared() ? CLEARED_FR : "Aucun tour pour l'instant. Envoyez un message : les étapes du harnais apparaîtront ici."
    );
    top.push(orchEmptyNote);
  }
  shown.forEach((turn, i) => {
    const index = store.chatFrom + i;
    if (index > store.chatFrom) {
      const between = connections(index);
      if (between.length) {
        const node = groupNode(`off:${index}`, "turn-off", () => {});
        node.head.hidden = true; // a connection between two turns: the lines alone, in place
        fillGroup(node, true, connectNodes(between));
        top.push(node.root);
      }
    }
    const isLast = turn === lastTurn;
    const open = o.turnOpen.has(turn.id) ? o.turnOpen.get(turn.id) : isLast;
    const node = groupNode(turn.id, "turn-group", () => toggleTurn(turn.id, node.head.getAttribute("aria-expanded") === "true"));
    node.root.classList.toggle("is-live", turn.status === null);
    const [statusClass, statusLabel] = TURN_STATUS[turn.status] || ["is-running", "en cours"];
    const calls = turn.steps.filter((s) => s.type === "call" && s.startedAt).length;
    const duration = turnDuration(turn);
    const figures = [duration === null ? null : seconds(duration), `${plural(calls, "appel")} au modèle`];
    headParts(node, [
      ["turn-group-title", `Tour ${index + 1}`],
      [`turn-group-status ${statusClass}`, statusLabel],
      ["turn-group-figures", figures.filter(Boolean).join(" · ")],
      ["turn-group-message", `« ${turn.message} »`],
    ]);
    node.head.title = turn.message;
    const rowNodes = open
      ? (isLast ? lastRows : turnRows(turn)).map((row) => {
          const isCurrent = isLast && row.key === o.current;
          const unfolded = row.sticky || (o.live ? isCurrent : o.userOpen.has(row.key));
          return stepNode(row, unfolded, { current: isCurrent && running, selected: row.key === o.selected });
        })
      : [];
    fillGroup(node, open, rowNodes);
    top.push(node.root);
  });
  const trailing = shown.length ? connections(store.chatFrom + shown.length) : [];
  if (trailing.length) {
    const node = groupNode(`off:${store.chatFrom + shown.length}`, "turn-off", () => {});
    node.head.hidden = true;
    fillGroup(node, true, connectNodes(trailing));
    top.push(node.root);
  }
  patchChildren(scroll, top);
  for (const [key, node] of railNodes) if (!node.seen) railNodes.delete(key);
  for (const [key, node] of groupNodes) if (!node.seen) groupNodes.delete(key);

  // Followed while the user stays at the bottom; a manual scroll up is never taken back.
  // Also on the render where it just stopped: its last rows may land in the same frame.
  if (o.live && (running || wasRunning) && atBottom) scroll.scrollTop = scroll.scrollHeight;
  wasRunning = running;
  document.getElementById("follow-live").hidden = o.live;
  renderOrchWorking();
}

function renderChips() {
  const container = document.getElementById("pane-chips");
  container.innerHTML = "";
  for (const paneId of store.hiddenPanes) {
    const chip = document.createElement("button");
    chip.type = "button";
    chip.className = "pane-chip";
    // The Vue humain waits for the user's answer to an H5 validation.
    const awaiting = paneId === "human" && store.sessionState?.state === "awaiting_human";
    const linked = awaiting || (store.selection && paneOfComponent(store.selection) === paneId);
    if (linked) chip.classList.add("is-linked");
    chip.textContent = `+ ${PANE_LABELS[paneId]}`;
    chip.title = awaiting
      ? "Une validation humaine attend votre réponse : réafficher le volet Vue humain"
      : `Réafficher le volet ${PANE_LABELS[paneId]}`;
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

// ---------- event log: every event the harness emits, folded at the bottom of Orchestration ----------

const KIND_LABELS = {
  diagnostic_check: "Vérification du diagnostic",
  outbound_request: "Données sortantes",
  harness_error: "Erreur du harnais",
  session_state: "État de la session",
  architecture_changed: "Schéma mis à jour",
  turn_started: "Tour commencé",
  turn_ended: "Tour terminé",
  context_rendered: "Contexte rendu",
  context_preview: "Aperçu du contexte",
  context_overflow: "Contexte dépassé",
  output_truncated: "Sortie coupée",
  model_call_started: "Appel au modèle commencé",
  model_first_token: "Premier token",
  model_delta: "Morceau de réponse",
  model_call_ended: "Appel au modèle terminé",
  special_token_neutralized: "Token spécial neutralisé",
  bricks_changed: "Briques modifiées",
  conversation_cleared: "Conversation vidée",
  tool_started: "Outil lancé",
  tool_ended: "Outil terminé",
  tool_call_malformed: "Appel d'outil mal formé",
  limit_reached: "Borne du tour atteinte",
  prefix_not_reused: "Préfixe non réutilisé",
  mcp_connect_started: "Connexion MCP commencée",
  mcp_connect_ended: "Connexion MCP terminée",
  hook_decided: "Décision d'un hook",
  effect_applied: "Effet appliqué",
  approval_requested: "Validation demandée",
  approval_resolved: "Validation résolue",
};
const SESSION_STATES = {
  idle: "prête",
  turn: "tour en cours",
  awaiting_human: "attente de validation",
  model_load: "chargement du modèle",
  download: "téléchargement",
  reset: "réinitialisation",
  diagnostic: "diagnostic",
};

function eventSummary(group) {
  // One line per event, formatting only (AD-1).
  const e = group.events[0];
  const p = e.payload;
  switch (e.kind) {
    case "model_delta":
      return group.events.map((d) => d.payload.text).join("");
    case "session_state":
      return [SESSION_STATES[p.state] || p.state, p.reason_fr].filter(Boolean).join(" · ");
    case "architecture_changed":
      return `${plural(p.nodes.length, "nœud")}, ${plural(p.edges.length, "liaison")}`;
    case "bricks_changed":
      return `${p.bricks.filter((b) => b.wanted).length} sur ${p.bricks.length} briques voulues`;
    case "context_rendered":
    case "context_preview":
      return `${fmt(p.used)} / ${fmt(p.usable)} tokens · ${plural(p.segments.length, "segment")}`;
    case "context_overflow":
      return `${fmt(p.used)} / ${fmt(p.usable)} tokens`;
    case "turn_started":
      return `« ${p.message} »`;
    case "turn_ended":
      return [TURN_STATUS[p.status]?.[1] ?? p.status, p.duration_ms == null ? null : seconds(p.duration_ms)]
        .filter(Boolean)
        .join(" · ");
    case "model_call_started":
    case "mcp_connect_started":
      return p.phase_label;
    case "model_call_ended":
      return `${fmt(p.prompt_tokens)} lus · ${fmt(p.output_tokens)} écrits · ${seconds(p.duration_ms)} · ${p.stop_reason}`;
    case "tool_started":
      return formatCall({ name: p.tool, arguments: p.arguments });
    case "tool_ended":
      return `${p.status} · ${seconds(p.duration_ms)}`;
    case "outbound_request":
      return `${p.method} ${p.url}`;
    case "mcp_connect_ended":
      return p.status === "ok"
        ? `${mcpServerLabel(p.server)} : ${plural(p.tools.length, "outil")} · ${seconds(p.duration_ms)}`
        : `${mcpServerLabel(p.server)} : ${p.error_fr}`;
    case "hook_decided":
      return `${p.hook.toUpperCase()} · ${p.point_fr} · ${HOOK_DECISIONS[p.decision]}`;
    case "effect_applied":
      return `${plural(p.lines.length, "ligne")} au journal d'audit`;
    case "approval_requested":
      return `${p.tool} → ${p.destination}`;
    case "approval_resolved":
      return approvalDecision(p);
    case "tool_call_malformed":
      return p.detail_fr;
    case "output_truncated":
      return `${fmt(p.output_tokens)} / ${fmt(p.max_tokens)} tokens`;
    case "diagnostic_check":
      return `${p.check} : ${p.status} · ${p.message_fr}`;
    case "conversation_cleared":
      return "les tours précédents restent dans ce journal";
    default:
      return p.message_fr ?? "";
  }
}

// Rows are built only once the log is unfolded, then kept: consecutive `model_delta` of one
// call share a row (« Morceaux de réponse × N »), every other event has its own.
const eventLog = { groups: [], processed: 0, rows: [], list: null };

function syncLogGroups() {
  for (; eventLog.processed < store.journal.length; eventLog.processed++) {
    const e = store.journal[eventLog.processed];
    const last = eventLog.groups.at(-1);
    const first = last?.events[0];
    if (e.kind === "model_delta" && first?.kind === "model_delta" && first.call_id === e.call_id && first.turn_id === e.turn_id) {
      last.events.push(e);
    } else {
      eventLog.groups.push({ key: e.seq, kind: e.kind, events: [e] });
    }
  }
}

function logRow(i) {
  const group = eventLog.groups[i];
  let row = eventLog.rows[i];
  if (!row) {
    const li = el("li", "event-log-item");
    const line = el("button", "event-log-line");
    line.type = "button";
    const parts = {
      time: el("span", "event-log-time"),
      name: el("span", "event-log-name"),
      kind: el("code", "event-log-kind", group.kind),
      summary: el("span", "event-log-summary"),
      chevron: el("span", "event-log-chevron"),
    };
    parts.chevron.setAttribute("aria-hidden", "true");
    line.append(...Object.values(parts));
    line.addEventListener("click", () => {
      toggleSet(store.orch.logRowsOpen, group.key);
      logRow(i);
    });
    li.appendChild(line);
    setText(parts.time, new Date(group.events[0].ts).toLocaleTimeString("fr-FR"));
    row = { li, line, ...parts, json: null, count: 0 };
    eventLog.rows[i] = row;
  }
  const count = group.events.length;
  const open = store.orch.logRowsOpen.has(group.key);
  if (row.count !== count) {
    const merged = group.kind === "model_delta" && count > 1;
    setText(row.name, merged ? `Morceaux de réponse × ${fmt(count)}` : KIND_LABELS[group.kind] || group.kind);
    const summary = eventSummary(group);
    setText(row.summary, summary);
    row.line.title = summary;
  }
  setText(row.chevron, open ? "▾" : "▸");
  row.line.setAttribute("aria-expanded", String(open));
  if (open && (!row.json || row.count !== count)) {
    // The raw JSON, on demand: the whole envelope, or one line per chunk of a merged row.
    const text =
      count > 1
        ? group.events.map((e) => JSON.stringify(e)).join("\n")
        : JSON.stringify(group.events[0], null, 2);
    const json = el("pre", "event-log-json", text);
    if (row.json) row.json.replaceWith(json);
    else row.li.appendChild(json);
    row.json = json;
  } else if (!open && row.json) {
    row.json.remove();
    row.json = null;
  }
  row.count = count;
  return row.li;
}

function renderJournal() {
  const o = store.orch;
  const head = document.getElementById("event-log-head");
  setText(document.getElementById("event-log-chevron"), o.logOpen ? "▾" : "▸");
  setText(document.getElementById("event-log-title"), `Journal des événements (${fmt(store.journal.length)})`);
  head.setAttribute("aria-expanded", String(o.logOpen));
  if (!o.logOpen) {
    eventLog.list?.remove();
    return;
  }
  if (!eventLog.list) {
    eventLog.list = el("ol", "event-log-list");
    eventLog.list.id = "event-log-list";
    eventLog.empty = el("li", "empty-note", "Aucun événement pour l'instant.");
  }
  const list = eventLog.list;
  const atBottom = !list.isConnected || list.scrollHeight - list.scrollTop - list.clientHeight < 30;
  if (!list.isConnected) document.getElementById("event-log").appendChild(list);
  syncLogGroups();
  // Groups only grow at the end: the last known row is updated, new ones are appended.
  for (let i = Math.max(eventLog.rows.length - 1, 0); i < eventLog.groups.length; i++) {
    const li = logRow(i);
    if (!li.isConnected) list.appendChild(li);
  }
  if (eventLog.groups.length) eventLog.empty.remove();
  else list.appendChild(eventLog.empty);
  if (atBottom) list.scrollTop = list.scrollHeight;
}

function toggleJournal() {
  store.orch.logOpen = !store.orch.logOpen;
  renderJournal();
}

const SVG_NS = "http://www.w3.org/2000/svg";

function svgEl(tag, attrs) {
  const node = document.createElementNS(SVG_NS, tag);
  for (const [key, value] of Object.entries(attrs)) node.setAttribute(key, String(value));
  return node;
}

// Brick id -> chip icon in the harness frame (formatting only).
const BRICK_ICONS = {
  short_memory: "🧠",
  system_prompt: "📜",
  tools: "🔧",
  mcp: "🔌",
  skills: "📘",
  hooks: "🪝",
};
const POSE_LABELS = { idle: "au repos", thinking: "réfléchit", tool: "utilise un outil" };
// Hook id -> its point of attachment, in the order the strip lists them (formatting only, like
// HOOK_ICONS): the order of a turn, from the user's message to its end.
const HOOK_POINTS = {
  h3: "réception du message",
  h1: "avant un outil",
  h5: "avant un outil réseau",
  h2: "après un outil · fin du tour",
};
// Tool name -> icon of its round tile (formatting only); any other tool gets the wrench.
const TOOL_ICONS = {
  get_datetime: "🕐",
  calculator: "🧮",
  read_file: "📂",
  public_holidays: "📅",
  wikipedia_summary: "🔎",
  fetch_page: "🔗",
};
// The bins (EXPERIENCE: arch-group), by `node.kind` and `node.hosting` of `architecture_changed`
// (AD-12), each in a column of its zone: [Outils], [Serveurs MCP, Fichiers], [Skills] on the
// workstation, [Outils réseau, Serveurs MCP publics] on the network side.
const ARCH_GROUPS = [
  { zone: "local", col: 0, kind: "tool", hosting: "local", shape: "tool", icon: "🔧", title: "Outils" },
  { zone: "local", col: 1, kind: "mcp_server", hosting: "local", shape: "mcp", icon: "🔌", title: "Serveurs MCP" },
  { zone: "local", col: 1, kind: "file", shape: "file", icon: "📄", title: "Fichiers" },
  { zone: "local", col: 2, kind: "skill", shape: "skill", icon: "📘", title: "Skills" },
  { zone: "network", col: 0, kind: "tool", hosting: "network", shape: "tool", icon: "🔧", title: "Outils réseau" },
  { zone: "network", col: 0, kind: "mcp_server", hosting: "network", shape: "mcp", icon: "🔌", title: "Serveurs MCP publics" },
];
const SHAPE_LABELS = {
  tool: "outil",
  mcp: "serveur MCP (processus distinct du harnais)",
  skill: "skill (fichier local)",
  file: "fichier local",
};

// The robot's pose, derived from the turn's events only (AD-1).
function robotPose() {
  // Only calls and tools: e.g. a `prefix_not_reused` step lands between a call and its start.
  const step = activeTurn()?.steps.filter((s) => s.type === "call" || s.type === "tool").at(-1);
  if (!step || step.ended) return "idle";
  if (step.type === "tool") return "tool";
  return step.type === "call" && step.startedAt ? "thinking" : "idle";
}

// The robot mascot (DESIGN.md > arch-model): its own drawing, « Modèle » and the model's name
// in HTML under it.
function robot(pose, modelNode) {
  const name = modelNode?.model ?? null;
  const label = `Modèle${name ? ` ${name}` : ""} : ${POSE_LABELS[pose]}`;
  const button = schemaButton(`robot${pose === "idle" ? "" : " is-active"}`, "core.model");
  button.setAttribute("aria-label", label);
  button.title = label;
  const cx = 40;
  const svg = svgEl("svg", { class: "robot-drawing", viewBox: "4 14 74 70", width: 60, height: 57 });
  svg.setAttribute("aria-hidden", "true");
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
  svg.append(
    svgEl("rect", { class: "robot-stick", x: cx - 1.5, y: 24, width: 3, height: 11, rx: 1.5 }),
    svgEl("circle", { class: "robot-antenna", cx, cy: 22, r: 5 }),
    svgEl("rect", { class: "robot-ear", x: cx - 34, y: 44, width: 9, height: 20, rx: 4.5 }),
    svgEl("rect", { class: "robot-ear", x: cx + 25, y: 44, width: 9, height: 20, rx: 4.5 }),
    svgEl("rect", { class: "robot-body", x: cx - 26, y: 34, width: 52, height: 40, rx: 14 }),
    svgEl("rect", { class: "robot-visor", x: cx - 19, y: 41, width: 38, height: 24, rx: 10 }),
    ...face
  );
  if (pose === "tool") {
    const icon = svgEl("text", { x: cx + 26, y: 76, "text-anchor": "middle", class: "robot-badge-icon" });
    icon.textContent = "🔧";
    svg.append(svgEl("circle", { class: "robot-badge", cx: cx + 26, cy: 72, r: 9 }), icon);
  }
  button.append(svg, el("span", "robot-label", "Modèle"));
  // The frame is narrow: a long file name is cut by the style, the tooltip keeps it whole.
  if (name) button.appendChild(el("span", "robot-model", name));
  return button;
}

// Every piece of the schema is a button: Tab reaches it, Enter selects it (FR-4).
function schemaButton(className, componentId, text) {
  const button = el("button", className, text);
  button.type = "button";
  button.dataset.component = componentId;
  button.dataset.focusKey = componentId;
  button.classList.toggle("is-selected", store.selection === componentId);
  button.setAttribute("aria-pressed", String(store.selection === componentId));
  button.addEventListener("click", () => select(componentId));
  return button;
}

// What is in action in the last shown turn while it runs (story 8e, Design Notes): read from
// its steps and the nodes, formatting only (AD-1). `mode`: `on` (halo, path to `target`),
// `pending` (H5 waits: path stopped before the boundary), `blocked` (path stopped at the strip).
function schemaActivity(nodes) {
  const turn = shownTurns().at(-1);
  if (!turn || turn.status !== null) return null;
  const steps = turn.steps;
  let i = steps.length - 1;
  while (i >= 0 && steps[i].type !== "tool" && steps[i].type !== "hook") i--;
  if (i < 0) return null;
  const step = steps[i];
  const drawn = (id) => nodes.some((n) => n.id === id); // only enabled hooks can act
  if (step.type === "tool") {
    // A harness tool (documentation, skills) runs in the harness itself: no path.
    const id = step.component;
    if (step.ended || !id || id === "core.harness" || !drawn(id)) return null;
    return { component: id, mode: "on", target: id };
  }
  const p = step.payload;
  const hook = step.component || `hooks.${p.hook}`;
  if (!drawn(hook)) return null;
  if (p.decision === "ask_human" && !step.resolved) return { component: hook, mode: "pending" };
  if (p.decision === "block") return { component: hook, mode: "blocked" };
  if (i !== steps.length - 1) return null; // another step followed: the hook is done
  const edge = (store.architecture.edges || []).find((e) => e.from === hook && e.to.startsWith("file."));
  return edge ? { component: hook, mode: "on", target: edge.to } : { component: hook, mode: null };
}

let renderedSchemaKey = null;
let renderedRobotKey = null;
let renderedActivityKey = null;
let schemaActive = null; // the last `schemaActivity()`, read by `drawSchemaWires`

function renderSchema() {
  // Layout only: nodes, edges and availability come from `architecture_changed` (AD-12), the
  // hooks of the strip from `bricks_changed`. `render()` runs on every `model_delta`: the DOM is
  // rebuilt only when its key changes; the robot and the halo are patched on their own.
  const root = document.getElementById("schema");
  const nodes = store.architecture.nodes || [];
  const wanted = (store.bricks?.bricks || []).filter((b) => b.wanted);
  const hooks = wanted.find((b) => b.id === "hooks")?.options || null;
  // The hooks that blocked in the last shown turn: they stay on a red rule until the next one.
  const blocked = (shownTurns().at(-1)?.steps || [])
    .filter((s) => s.type === "hook" && s.payload.decision === "block")
    .map((s) => `hooks.${s.payload.hook}`);
  const model = nodes.find((n) => n.id === "core.model");
  const pose = robotPose();
  const key = JSON.stringify([store.architecture, wanted.length, hooks, blocked, store.selection]);
  if (key !== renderedSchemaKey) {
    renderedSchemaKey = key;
    renderedActivityKey = null;
    renderedRobotKey = JSON.stringify([pose, model?.model]);
    buildSchema(root, nodes, wanted.length > 0, hooks, blocked, robot(pose, model));
    scheduleWires();
  }
  const robotKey = JSON.stringify([pose, model?.model]);
  if (robotKey !== renderedRobotKey) {
    // A pose change swaps the robot only: the rest keeps its focus and its layout.
    renderedRobotKey = robotKey;
    const old = root.querySelector(".robot");
    const next = robot(pose, model);
    const focused = old === document.activeElement;
    old?.replaceWith(next);
    if (focused) next.focus();
  }
  const activity = schemaActivity(nodes);
  const activityKey = JSON.stringify(activity);
  if (activityKey !== renderedActivityKey) {
    renderedActivityKey = activityKey;
    schemaActive = activity;
    for (const node of root.querySelectorAll(".is-active:not(.robot)")) node.classList.remove("is-active");
    if (activity) {
      const id = cssEscape(activity.component);
      root.querySelector(`.arch-node[data-component="${id}"], .arch-hook[data-component="${id}"]`)?.classList.add("is-active");
    }
    scheduleWires();
  }
}

function buildSchema(root, nodes, anyBrick, hooks, blocked, robotNode) {
  // The rebuild would drop keyboard focus: note it, restore it on the new element.
  const focusKey = root.contains(document.activeElement) ? document.activeElement.dataset.focusKey : null;
  root.innerHTML = "";
  const byId = Object.fromEntries(nodes.map((n) => [n.id, n]));

  // The harness frame: the robot and the chips of the bricks with no outside component, stacked.
  const frame = el("div", "arch-harness");
  frame.dataset.component = "core.harness";
  frame.classList.toggle("is-selected", store.selection === "core.harness");
  frame.title = byId["core.harness"]?.label_fr || "Harnais";
  frame.addEventListener("click", (event) => {
    if (!event.target.closest("button:not(.arch-harness-tag)")) select("core.harness");
  });
  const tag = el("button", "arch-harness-tag", "Harnais"); // its click reaches the frame
  tag.type = "button";
  tag.dataset.focusKey = "core.harness";
  const core = el("div", "arch-core");
  const chips = el("div", "arch-chips");
  for (const node of nodes.filter((n) => n.kind === "brick")) {
    const icon = BRICK_ICONS[node.id.split(".")[0]] || "🧩";
    const chip = schemaButton("arch-chip", node.id, `${icon} ${node.label_fr}`);
    chip.classList.toggle("is-unavailable", !node.available);
    chip.title = node.available ? node.label_fr : `${node.label_fr} : ${node.reason_fr}`;
    chips.appendChild(chip);
  }
  if (!anyBrick) chips.appendChild(el("p", "arch-harness-empty", "Aucune brique : LLM nu"));
  core.append(robotNode, chips);
  frame.append(tag, core);
  if (hooks) frame.appendChild(hookStrip(hooks, byId, blocked));

  const local = el("div", "arch-zone arch-zone-local");
  const localRow = el("div", "arch-zone-row");
  localRow.append(frame, ...schemaColumns("local", nodes));
  local.append(el("span", "arch-zone-label", "🖥 Poste de travail"), localRow);

  const boundary = el("div", "arch-boundary");
  boundary.appendChild(el("span", "arch-boundary-label", "frontière du poste"));

  const network = el("div", "arch-zone arch-zone-network");
  const networkRow = el("div", "arch-zone-row");
  const networkCols = schemaColumns("network", nodes);
  if (networkCols.length) networkRow.append(...networkCols);
  else networkRow.appendChild(el("p", "arch-zone-empty", "Aucun composant réseau : rien ne sort du poste."));
  network.append(el("span", "arch-zone-label", "🌐 RÉSEAU · hors du poste"), networkRow);

  // The trunk, the rails and the path, drawn over the pieces once they are laid out.
  const wires = svgEl("svg", { class: "arch-wires" });
  wires.setAttribute("aria-hidden", "true");
  root.append(local, boundary, network, wires);
  if (focusKey) root.querySelector(`[data-focus-key="${cssEscape(focusKey)}"]`)?.focus();
}

// The « Points d'accroche » strip: every hook of the brick, one per line, name and point; a hook
// switched off (unchecked, or H5 after « Autoriser et ne plus demander ») stays, dashed grey.
function hookStrip(options, byId, blocked) {
  const strip = el("div", "arch-hook-strip");
  strip.appendChild(el("span", "arch-hook-strip-tag", "🪝 Points d'accroche"));
  const order = Object.keys(HOOK_POINTS);
  const rank = (id) => (order.includes(id) ? order.indexOf(id) : order.length);
  for (const option of [...options].sort((a, b) => rank(a.id) - rank(b.id))) {
    const id = `hooks.${option.id}`;
    const off = !byId[id]; // enabled hooks only are in `architecture_changed`
    const isBlocked = !off && blocked.includes(id);
    const point = HOOK_POINTS[option.id] || "";
    const state = isBlocked ? " · ✖ a bloqué" : off ? " · désactivé" : "";
    const hook = schemaButton("arch-hook", id);
    hook.classList.toggle("is-off", off);
    hook.classList.toggle("is-blocked", isBlocked);
    hook.append(
      el("span", "arch-hook-name", `${HOOK_ICONS[option.id] || "🪝"} ${option.label_fr}${state}`),
      el("span", "arch-hook-point", point)
    );
    hook.title = [
      `${option.label_fr} : code du harnais, point d'accroche « ${point} »`,
      byId[id]?.detail_fr,
      off ? "Désactivé : ce hook n'agit pas." : null,
    ]
      .filter(Boolean)
      .join("\n");
    strip.appendChild(hook);
  }
  return strip;
}

// The columns of a zone; a bin with no node is not drawn, nor a column with no bin.
function schemaColumns(zone, nodes) {
  const cols = [];
  for (const group of ARCH_GROUPS.filter((g) => g.zone === zone)) {
    const members = nodes.filter((n) => n.kind === group.kind && (!group.hosting || n.hosting === group.hosting));
    if (members.length) (cols[group.col] ||= []).push(schemaGroup(group, members));
  }
  return cols.filter(Boolean).map((bins) => {
    const col = el("div", "arch-col");
    col.append(...bins);
    return col;
  });
}

function schemaGroup(group, members) {
  const bin = el("div", `arch-group arch-group-${group.shape}`);
  bin.setAttribute("role", "group");
  bin.setAttribute("aria-label", `${group.title} : ${members.length}`);
  const list = el("div", "arch-group-nodes");
  for (const node of members) list.append(...schemaNode(node, group.shape));
  bin.append(el("span", "arch-group-title", `${group.icon} ${group.title} · ${members.length}`), list);
  return bin;
}

// A node: its category reads by its shape and icon, its hosting by its colours (DESIGN.md >
// arch-group). Returns the node, then the list of its tools for a selected MCP server.
function schemaNode(node, shape) {
  const network = node.hosting === "network";
  const unavailable = !node.available;
  const notContacted = node.contact === "not_contacted";
  const loaded = shape === "skill" && Boolean(node.loaded);
  const tools = node.tools || [];
  const button = schemaButton(`arch-node arch-node-${shape} ${network ? "is-network" : "is-local"}`, node.id);
  button.classList.toggle("is-unavailable", unavailable);
  button.classList.toggle("is-loaded", loaded);
  let icon = { tool: TOOL_ICONS[node.id.slice(6)] || "🔧", mcp: "🔌", file: "📄" }[shape] || null;
  if (unavailable) icon = "⊘"; // the crossed-out icon of DESIGN.md > arch-node-unavailable
  let pill = null;
  if (unavailable) pill = "indisponible";
  else if (shape === "mcp") pill = notContacted ? "non contacté" : plural(tools.length, "outil");
  else if (notContacted) pill = "non contacté";
  else if (loaded) pill = "✓"; // a skill's bin is narrow: « Chargé » is in its accessible name and tooltip
  if (icon) button.appendChild(el("span", "arch-node-icon", icon));
  // A network node carries its globe on the node itself, not only on its zone (FR-13).
  button.appendChild(el("span", "arch-node-name", network ? `🌐 ${node.label_fr}` : node.label_fr));
  if (pill) button.appendChild(el("span", "arch-node-pill", pill));

  const tooltip = [`${node.label_fr} · ${SHAPE_LABELS[shape]} · ${network ? "RÉSEAU" : "sur le poste"}`];
  if (unavailable) tooltip.push(`Indisponible : ${node.reason_fr}`);
  else if (notContacted) tooltip.push("Non contacté : aucune requête envoyée pour l'instant.");
  if (shape === "skill") tooltip.push(loaded ? "Chargé dans la conversation." : "Non chargé.");
  if (tools.length) tooltip.push(`Outils : ${tools.join(", ")}`);
  if (node.detail_fr) tooltip.push(node.detail_fr);
  button.title = tooltip.join("\n");
  button.setAttribute("aria-label", tooltip.join(". "));
  if (node.id === "file.audit") button.addEventListener("click", openAudit); // the whole log

  if (shape !== "mcp" || !tools.length) return [button];
  // A selected MCP server unfolds its tools under it, in its bin (FR-3).
  button.setAttribute("aria-expanded", String(store.selection === node.id));
  if (store.selection !== node.id) return [button];
  const list = el("ul", "arch-node-tools");
  for (const name of tools) {
    const at = name.indexOf("__"); // `server__tool`
    list.appendChild(el("li", "", at > 0 ? name.slice(at + 2) : name));
  }
  return [button, list];
}

// ---------- schema wires: trunk, rails, path and markers (DESIGN.md > arch-trunk) ----------

let wiresPending = false;
function scheduleWires() {
  if (wiresPending) return;
  wiresPending = true;
  requestAnimationFrame(() => {
    wiresPending = false;
    drawSchemaWires();
  });
}

function wirePath(d, className) {
  return svgEl("path", { d, class: className });
}

function wireMarker(x, y, text, className) {
  const g = svgEl("g", { class: `arch-marker ${className}` });
  const label = svgEl("text", { x, y: y + 4, "text-anchor": "middle" });
  label.textContent = text;
  g.append(svgEl("circle", { cx: x, cy: y, r: 12 }), label);
  return g;
}

// Drawn from the laid-out pieces, after each rebuild and each resize (ResizeObserver): the trunk
// leaves the strip (or the frame), runs under the bins, and crosses the boundary dashed; a rail
// runs 8 px left of each column, with a stub to each bin.
function drawSchemaWires() {
  const arch = document.getElementById("schema");
  const svg = arch.querySelector(".arch-wires");
  const frame = arch.querySelector(".arch-harness");
  if (!svg || !frame) return;
  const A = arch.getBoundingClientRect();
  if (!A.width || !A.height) return; // hidden pane
  svg.setAttribute("width", A.width);
  svg.setAttribute("height", A.height);
  svg.setAttribute("viewBox", `0 0 ${A.width} ${A.height}`);
  const box = (node) => {
    const r = node.getBoundingClientRect();
    return { l: r.left - A.left, t: r.top - A.top, r: r.right - A.left, b: r.bottom - A.top, cx: (r.left + r.right) / 2 - A.left, cy: (r.top + r.bottom) / 2 - A.top };
  };
  const F = box(frame);
  const strip = arch.querySelector(".arch-hook-strip");
  const sx = strip ? box(strip).cx : F.r - 40;
  const sy = strip ? box(strip).b : F.b;
  const by = A.height - 12;
  const fx = box(arch.querySelector(".arch-boundary")).cx;
  const parts = [];
  const rails = new Map();
  let maxRail = sx;
  for (const col of arch.querySelectorAll(".arch-col")) {
    const railX = box(col).l - 8;
    const cls = `arch-trunk${col.closest(".arch-zone-network") ? " is-network" : ""}`;
    const stubs = [...col.querySelectorAll(".arch-group")].map((g) => ({ x: box(g).l, y: box(g).t + 12 }));
    if (!stubs.length) continue;
    parts.push(wirePath(`M${railX},${by} V${Math.min(...stubs.map((s) => s.y))}`, cls));
    for (const s of stubs) parts.push(wirePath(`M${railX},${s.y} H${s.x}`, cls));
    rails.set(col, railX);
    maxRail = Math.max(maxRail, railX);
  }
  if (maxRail > sx) {
    parts.push(wirePath(`M${sx},${sy} V${by} H${Math.min(maxRail, fx)}`, "arch-trunk"));
    if (maxRail > fx) parts.push(wirePath(`M${fx},${by} H${maxRail}`, "arch-trunk is-network"));
  }

  const a = schemaActive;
  if (a?.mode === "blocked") {
    // Stopped at the strip: the tool is never reached.
    const y = F.b + 14;
    parts.push(wirePath(`M${sx},${sy} V${y - 12}`, "arch-path-block"), wireMarker(sx, y, "✖", "is-block"));
  } else if (a?.mode === "pending") {
    // H5 waits for the user: stopped before the boundary, nothing has left the workstation.
    const stopX = fx - 18;
    const d = `M${sx},${sy} V${by} H${stopX}`;
    parts.push(wirePath(d, "arch-path"), wirePath(d, "arch-path-core"), wireMarker(stopX, by, "✋", "is-stop"));
  } else if (a?.target) {
    const node = arch.querySelector(`.arch-node[data-component="${cssEscape(a.target)}"]`);
    const col = node?.closest(".arch-col");
    if (col && rails.has(col)) {
      const g = box(node.closest(".arch-group"));
      const n = box(node);
      const railX = rails.get(col);
      // Along the bin's left edge, then into the node when it stands on that edge.
      const end = n.l - g.l < 20 ? `V${n.cy} H${n.l}` : `V${n.cy}`;
      const tail = `H${railX} V${g.t + 12} H${g.l + 3} ${end}`;
      parts.push(wirePath(`M${sx},${sy} V${by} ${tail}`, "arch-path"));
      if (node.classList.contains("is-network")) {
        // Solid on the workstation, dashed and moving once it crosses the boundary.
        parts.push(
          wirePath(`M${sx},${sy} V${by} H${fx}`, "arch-path-core"),
          wirePath(`M${fx},${by} ${tail}`, "arch-path-core is-flow")
        );
      } else {
        parts.push(wirePath(`M${sx},${sy} V${by} ${tail}`, "arch-path-core"));
      }
    }
  }
  svg.replaceChildren(...parts);
}

// ---------- audit log: the whole file, read only (story 8) ----------

async function openAudit() {
  const dialog = document.getElementById("audit-dialog");
  const text = document.getElementById("audit-text");
  document.getElementById("audit-path").textContent = "";
  text.textContent = "Lecture du journal…";
  if (!dialog.open) dialog.showModal();
  try {
    const response = await fetch("/api/audit");
    const body = await response.json().catch(() => ({}));
    if (!response.ok) {
      text.textContent = `Lecture impossible : ${body.detail || response.status}.`;
      return;
    }
    document.getElementById("audit-path").textContent = `Fichier : ${body.path}`;
    text.textContent = body.text || "Journal vide";
  } catch {
    text.textContent = "Lecture impossible : WaveStack ne répond pas.";
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
  document.getElementById("follow-live").addEventListener("click", followLive);
  document.getElementById("event-log-head").addEventListener("click", toggleJournal);
  document.getElementById("drawer-save").addEventListener("click", () =>
    saveSystemPrompt(drawerText().value)
  );
  document.getElementById("drawer-reset").addEventListener("click", () => saveSystemPrompt(null));
  document.getElementById("drawer-close").addEventListener("click", () => closeDrawer());
  document.getElementById("drawer-dirty-save").addEventListener("click", async () => {
    if (await saveSystemPrompt(drawerText().value)) closeDrawer(true);
  });
  document.getElementById("drawer-dirty-discard").addEventListener("click", () => closeDrawer(true));
  document.getElementById("audit-close").addEventListener("click", () =>
    document.getElementById("audit-dialog").close()
  );
  // The schema's wires follow its pieces: pane resized, focused, hidden then shown, fonts loaded.
  new ResizeObserver(scheduleWires).observe(document.getElementById("schema"));
  document.fonts?.ready.then(scheduleWires);
  // Local stopwatch anchored on the `*_started` ts, replaced by `duration_ms` (AD-1).
  setInterval(() => {
    if (activeTurn()) {
      renderChat();
      renderSteps();
    }
  }, 250);

  document.addEventListener("keydown", (event) => {
    if (event.key !== "Escape") return;
    if (document.getElementById("audit-dialog").open) return; // the dialog closes itself
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
