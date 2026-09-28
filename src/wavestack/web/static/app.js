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
  // AD-12: the model indicator's only source (`session_state.active_model`, `/api/state`).
  activeModel: null,
  // Story 17: the load in progress, from `model_load_started` to `model_load_ended`
  // ({ model, startedAt }), and the model picker's list (`GET /api/diagnostic`).
  modelLoad: null,
  modelList: null,
  // The picker's choice waiting for « Charger » (a keyboard arrow already fires `change`
  // under Windows), and whether its list failed to load.
  pickerPending: "",
  modelListError: false,
  // The journal's tip when `/api/state` answered: an older `model_load_ended`, replayed by
  // the stream after a reload, does not come back in the top bar.
  liveFrom: 0,
  architecture: { nodes: [], edges: [] },
  journal: [],
  selection: null,
  hiddenPanes: new Set(),
  focusedPane: null,
  // Sizes the user dragged (story 8f), absent until then: `bricks` width and `schema` height
  // in px, `human` / `ctx` / `orch` as flex-grow weights. Saved with `hiddenPanes`.
  paneSizes: {},
  // Gauge source: the most recent of `context_preview` / `context_rendered` (AD-9).
  gauge: null, // { payload, preview }
  turns: [], // one projection per turn, filled only from its events
  // `conversation_cleared`: index of the first turn still shown (Vue humain, Contexte LLM,
  // Orchestration), and the seq of the clearing, to hide the MCP connections seen before it.
  chatFrom: 0,
  clearedSeq: null,
  // Story 10: the last `scenario_changed` ({ program, active }); the seq of the last
  // `harness_reset`, the first journal index the event log shows, and the top bar's message.
  scenarios: null,
  resetSeq: null,
  logFrom: 0,
  topStatus: null,
  serverInstance: null, // A1: the journal instance this page follows
  composerError: null,
  // Story 9b: the turn comparison open in Contexte LLM, UI state only: { left, right } turn ids.
  compare: null,
  bricks: null, // last `bricks_changed` payload: cards and system prompt, as the session computed them
  // Story 14: the last `memory_changed` ({ entries, path, error_fr }), as the session wrote it
  // (AD-1); the drawer's unsaved texts, by entry id (UI state only).
  memory: null,
  memoryDrafts: new Map(),
  downloadError: null, // story 15: the last refusal of « Télécharger » (UI state only)
  ragNotice: null, // story 15: the last failure of the RAG's download or build (`harness_error`)
  rerankNotice: null, // story 16: the last failure of the reranker's download or load
  openExplanations: new Set(), // `options:{brick.id}` keys whose option list is unfolded (UI state only)
  openBrickHelp: new Set(), // brick ids whose help popover is open (UI state only)
  closedPayloads: new Set(), // seq of outbound payloads folded by the user (open by default)
  openApprovalPayloads: new Set(), // approval ids whose payload is unfolded in the Vue humain card
  // Story 19, UI state only: the context Contexte LLM shows, `null` for the main one, else
  // `{ turn, sub }` (a turn id and a sub-agent's `context_id`); back to the main one if absent.
  ctxView: null,
  // Story 13, UI state only: « Afficher le raisonnement » (remembered by the browser, shown by
  // default), and the reasoning blocks the user unfolded (`chat:` or `ctx:` + turn id).
  showReasoning: true,
  openReasoning: new Set(),
  // Story 9: the armed actions as the session last sent them (AD-3), and every label seen, so
  // an `action_dropped` still names its action once the list moved on.
  armed: [],
  armedLabels: new Map(),
  // UI state only: « Afficher les actions forcées » (remembered by the browser), the forced
  // call form open under one option, and the last refusal of an arming.
  showForced: false,
  forceForm: null, // { brick, id, preset, values, error }
  forceFocus: null, // the focus key to restore once a form closes
  armError: null,
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

// Story 33: the disciplines, in the order of the legends. A segment, a gauge group and a brick
// card carry theirs from the session (`discipline`, `category`, AD-1); the colours are the
// `--color-discipline-*` tokens, read by `[data-discipline]` in app.css.
const DISCIPLINES = [
  ["prompt", "Prompt engineering"],
  ["context", "Context engineering"],
  ["harness", "Harness engineering"],
];
const DISCIPLINE_NAMES = Object.fromEntries(DISCIPLINES);
// Neutral: no brick (message, template), an assistant turn, or a brick the table lacks; one
// label in the legend and in the tooltips.
const NEUTRAL_FR = "Hors brique";
const NETWORK_FR = "Sort du poste de travail";
const disciplineName = (d) => DISCIPLINE_NAMES[d] || NEUTRAL_FR;

// A legend: one bordered swatch and a name per discipline. `network`: the yellow never alone,
// its swatch carries the globe (DESIGN.md > Colors).
function disciplineLegend(className, items) {
  const list = el("ul", className);
  for (const [discipline, label] of items) {
    const item = el("li", "discipline-legend-item");
    item.dataset.discipline = discipline;
    const swatch = el("span", "discipline-swatch", discipline === "network" ? "🌐" : "");
    swatch.setAttribute("aria-hidden", "true");
    item.append(swatch, el("span", "", label));
    list.appendChild(item);
  }
  return list;
}

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
          const { event, data } = parseSseEvent(rawEvent);
          if (event === "server_instance") {
            // A1: another process's journal, where lastSeq means nothing: resync by reloading.
            if (!sameServerInstance(data?.instance_id)) return;
          } else if (data) {
            lastSeq = data.seq;
            onEnvelope(data);
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
  let event = null;
  let data = null;
  for (const line of rawEvent.split("\n")) {
    if (line.startsWith("data:")) {
      data = line.slice(5).trim();
    } else if (line.startsWith("event:")) {
      // Only `server_instance` needs it: an envelope's own `kind` says the rest.
      event = line.slice(6).trim();
    }
    // `id:` is redundant with the envelope's own `seq`.
  }
  if (!data) return { event, data: null };
  try {
    return { event, data: JSON.parse(data) };
  } catch {
    return { event, data: null };
  }
}

// The journal this page was built from (`/api/state`, else the first stream). WaveStack
// relaunched while the tab stayed open: a new journal, from seq 1, with turn ids already
// used; the page reloads, which replays it whole (AD-1). False when reloading.
function sameServerInstance(instanceId) {
  if (!instanceId) return true;
  if (store.serverInstance === null) store.serverInstance = instanceId;
  if (instanceId === store.serverInstance) return true;
  location.reload();
  return false;
}

const RESET_STATUS_FR = "WaveStack réinitialisé : LLM nu.";
const RESET_STATUS_MS = 6000;
let resetStatusTimer = null;

// The "last known" states (`session_state`, the architecture, the bricks…): `/api/state`
// already gave the latest of each, up to `store.liveFrom`. An older one, replayed by the
// stream after a reload, would take the page back in time (a composer enabled then
// disabled by past turns): only a later one applies.
const isLive = (envelope) => envelope.seq > store.liveFrom;

function applyEnvelope(envelope) {
  store.journal.push(envelope);
  const p = envelope.payload;
  const turn = envelope.turn_id ? store.turns.find((t) => t.id === envelope.turn_id) : null;
  // Story 19 (AD-11): a sub-agent's events fill its own projection, never the turn's gauge,
  // context or text; the Vue humain only gets the phase and H5's validations.
  if (turn && envelope.context_id?.startsWith("sub") && SUB_KINDS.has(envelope.kind)) {
    applySubEnvelope(turn, subProjection(turn, envelope), envelope);
    scheduleRender();
    return;
  }
  switch (envelope.kind) {
    case "session_state":
      // A new attempt clears the earlier failures, replayed or not (they come from the stream only).
      if (p.state === "download" || p.state === "index_build") store.ragNotice = store.rerankNotice = null;
      if (!isLive(envelope)) break;
      store.sessionState = p;
      // The diagnostic session's own states carry no model: the last known one stays.
      if (p.active_model !== undefined) store.activeModel = p.active_model;
      if (p.state === "idle") store.composerError = null;
      break;
    case "architecture_changed":
      if (isLive(envelope)) store.architecture = p;
      break;
    case "context_preview":
      if (isLive(envelope)) store.gauge = { payload: p, preview: true };
      break;
    case "bricks_changed":
      if (isLive(envelope)) {
        store.bricks = p;
        syncDrawerSave(); // story 22: the prompt the session holds may have changed
      }
      break;
    case "memory_changed":
      if (!isLive(envelope)) break;
      store.memory = p;
      renderMemoryDrawer();
      break;
    case "armed_actions_changed":
      // Every label seen stays known, so that a replayed `action_dropped` still names it.
      for (const action of p.actions) store.armedLabels.set(action.armed_id, action.label_fr);
      // AD-1: the chips are this list, never a local computation.
      if (isLive(envelope)) store.armed = p.actions;
      break;
    case "action_dropped":
      if (turn) turn.steps.push({ type: envelope.kind, payload: p, label: store.armedLabels.get(p.armed_id) });
      break;
    case "conversation_cleared":
      // Past turns leave the Vue humain, Contexte LLM and Orchestration; the event list keeps them.
      store.chatFrom = store.turns.length;
      store.clearedSeq = envelope.seq;
      store.compare = null;
      break;
    case "scenario_changed":
      if (!isLive(envelope)) break;
      store.scenarios = p;
      // Lot E (E5): a refresh after a model load is no launch: the load's outcome stays.
      if (p.active && !p.refresh) store.topStatus = null;
      break;
    case "harness_reset":
      // Like `conversation_cleared`, but the panes go back to « Aucun tour », the MCP
      // connections seen so far stay in the harness preparation, and the event log restarts.
      store.chatFrom = store.turns.length;
      store.resetSeq = envelope.seq;
      store.compare = null;
      store.logFrom = store.journal.length;
      eventLog.list?.remove();
      Object.assign(eventLog, { groups: [], processed: store.logFrom, rows: [], list: null });
      store.memoryDrafts.clear();
      if (!isLive(envelope)) break; // an earlier reset: no confirmation in the top bar
      store.topStatus = RESET_STATUS_FR;
      // A4: a discreet confirmation, over the panes: it leaves on its own.
      clearTimeout(resetStatusTimer);
      resetStatusTimer = setTimeout(() => {
        if (store.topStatus !== RESET_STATUS_FR) return;
        store.topStatus = null;
        render();
      }, RESET_STATUS_MS);
      break;
    case "model_load_started":
      store.modelLoad = { model: p.model, startedAt: Date.parse(envelope.ts) };
      store.topStatus = null;
      break;
    case "model_load_ended":
      store.modelLoad = null;
      // A load that fell back, or a choice not saved, says so in the top bar (live only).
      if (isLive(envelope)) store.topStatus = p.reason_fr ?? null;
      scheduleModelList();
      break;
    case "turn_started":
      store.topStatus = null;
      store.compare = null; // the new turn's live context shows in Contexte LLM
      store.ctxView = null; // story 22: each new turn opens on « Agent principal »
      store.turns.push({
        id: envelope.turn_id,
        message: p.message,
        model: p.active_model ?? null, // story 17: « Modèle : … » and « Comparer »
        replayOf: p.replay_of, // story 9b: the turn this one replays, or null
        startedAt: Date.parse(envelope.ts),
        callStartedAt: null,
        phaseLabel: null,
        firstToken: false,
        stopRequested: false,
        context: null,
        text: "",
        reasoning: "",
        // Story 13: the reasoning of the turn's earlier calls, in order (the current one is
        // `reasoning`), so a multi-call turn keeps them all in the Vue humain.
        pastReasoning: [],
        callEnded: null,
        overflow: null,
        truncated: null,
        notices: [],
        errors: [],
        status: null,
        limit: null,
        // Orchestration, in the real order: model calls, tool executions, harness events.
        steps: [],
        subs: new Map(), // story 19: `context_id` -> the projection of a sub-agent
      });
      break;
    case "context_rendered":
      if (isLive(envelope)) store.gauge = { payload: p, preview: false };
      if (turn) {
        turn.context = p;
        turn.steps.push({ type: "call", id: envelope.call_id, context: p, startedAt: null, ended: null });
      }
      break;
    case "context_reconciled":
      // AD-4, chat mode: `usage` came back; its figures replace the estimate of that call.
      if (isLive(envelope)) store.gauge = { payload: p, preview: false };
      if (turn) {
        const call = turn.steps.find((s) => s.type === "call" && s.id === envelope.call_id);
        if (call) call.context = p;
        if (lastCall(turn) === call) turn.context = p;
      }
      break;
    case "context_overflow":
      if (turn) turn.overflow = p;
      break;
    case "model_call_started":
      if (turn) {
        // A new call of the same turn: the indicator comes back until its first token.
        if (turn.reasoning) turn.pastReasoning.push(turn.reasoning);
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
          stepId: envelope.step_id, // a sub-agent hangs on it by `parent_step` (story 19)
          started: p,
          brick: envelope.brick,
          component: envelope.component, // the schema node in action
          trigger: envelope.trigger, // AD-2: `model`, or `user` for a forced action
          startedAt: Date.parse(envelope.ts),
          ended: null,
        });
      }
      break;
    case "rag_search_started":
      // Story 15: the harness searches the corpus before the first call (its own step).
      if (turn) {
        Object.assign(turn, { phaseLabel: p.phase_label, callStartedAt: Date.parse(envelope.ts), firstToken: false });
        turn.steps.push({ type: "rag", started: p, component: envelope.component, startedAt: Date.parse(envelope.ts), ended: null });
      }
      break;
    case "rag_search_ended": {
      const search = turn?.steps.filter((s) => s.type === "rag").at(-1);
      if (search) search.ended = p;
      break;
    }
    case "rag_rerank_started":
      // Story 16: the reranker scores the candidates, its own step after the search.
      if (turn) {
        Object.assign(turn, { phaseLabel: p.phase_label, callStartedAt: Date.parse(envelope.ts), firstToken: false });
        // The texts are the search's (by `chunk_id`): the step keeps the search it reranks.
        const search = turn.steps.filter((s) => s.type === "rag").at(-1) ?? null;
        turn.steps.push({ type: "rerank", started: p, search, component: envelope.component, startedAt: Date.parse(envelope.ts), ended: null, progress: null });
      }
      break;
    case "rag_rerank_progress": {
      const rerank = turn?.steps.filter((s) => s.type === "rerank").at(-1);
      if (rerank) rerank.progress = p;
      break;
    }
    case "rag_rerank_ended": {
      const rerank = turn?.steps.filter((s) => s.type === "rerank").at(-1);
      if (rerank) rerank.ended = p;
      break;
    }
    case "compression_started":
      // Story 20: the harness compresses tool results and RAG excerpts before a call.
      if (turn) {
        Object.assign(turn, { phaseLabel: p.phase_label, callStartedAt: Date.parse(envelope.ts), firstToken: false });
        // `stepId`: a compressed segment finds its text before here (`compressed_from.step_id`).
        turn.steps.push({ type: "compression", stepId: envelope.step_id, started: p, component: envelope.component, startedAt: Date.parse(envelope.ts), ended: null });
      }
      break;
    case "compression_ended": {
      const step = turn?.steps.filter((s) => s.type === "compression").at(-1);
      if (step) step.ended = p;
      break;
    }
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
      if (step && p.origin === "brick") {
        (step.outbound ||= []).push({ ...p, seq: envelope.seq, component: envelope.component });
      }
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
      if (turn) {
        turn.steps.push({ type: "hook", payload: p, component: envelope.component, trigger: envelope.trigger, lines: [] });
      }
      break;
    case "effect_applied": {
      if (p.effect === "memory_write") {
        // Story 14: the entry `remember` wrote, shown in its own step (model's or forced).
        const step = turn?.steps.filter((s) => s.type === "tool" && s.started.tool === "remember").at(-1);
        if (step) (step.memoryWrites ||= []).push(p);
        break;
      }
      // The lines H2 appended to the audit log, shown in its own step.
      const step = turn?.steps.filter((s) => s.type === "hook").at(-1);
      if (step) step.lines.push(...(p.lines ?? []));
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
    case "reasoning_cut": // lot C: the harness closed a reasoning at its budget
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
      // A cloud provider's refusal carries what to try (AD-16).
      if (turn) turn.errors.push([p.message_fr, ...(p.hints_fr ?? [])].join(" "));
      // Story 15: a failed download (or load) of the RAG's model, said on its card.
      else if (envelope.brick === "rag") {
        const notice = [p.message_fr, p.cause ? `Cause : ${p.cause}.` : null, p.effect_fr].filter(Boolean).join(" ");
        // Story 16: the reranker's, said under its switch.
        if (envelope.component === "rag.reranker") store.rerankNotice = notice;
        else store.ragNotice = notice;
      }
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

// Story 19: the kinds a sub-agent's projection takes; any other event emitted while it runs
// (`session_state` of H5's wait, `architecture_changed`, `bricks_changed`…) is the session's.
const SUB_KINDS = new Set([
  "subagent_started",
  "subagent_ended",
  "context_rendered",
  "context_reconciled",
  "context_overflow",
  "model_call_started",
  "model_first_token",
  "model_delta",
  "model_call_ended",
  "tool_started",
  "tool_ended",
  "outbound_request",
  "hook_decided",
  "effect_applied",
  "approval_requested",
  "approval_resolved",
  "tool_call_malformed",
  "prefix_not_reused",
  "reasoning_cut",
  "limit_reached",
  "output_truncated",
  "special_token_neutralized",
  "harness_error",
]);

// Story 19 (AD-11): the projection of the sub-agent `context_id`, created at its first event
// and hung on the `delegate` step whose `step_id` is its `parent_step`, never by position.
function subProjection(turn, envelope) {
  let sub = turn.subs.get(envelope.context_id);
  if (!sub) {
    sub = {
      id: `${turn.id}:${envelope.context_id}`, // unique rail keys for its lines
      contextId: envelope.context_id,
      parentStep: envelope.parent_step,
      started: null,
      ended: null,
      steps: [],
      context: null,
      callEnded: null,
      text: "",
      reasoning: "",
      overflow: null,
      limit: null,
      truncated: null,
      errors: [],
      notices: [],
      firstToken: false,
      status: null,
    };
    turn.subs.set(envelope.context_id, sub);
    const tool = turn.steps.find((s) => s.type === "tool" && s.stepId === envelope.parent_step);
    if (tool) tool.sub = sub;
  }
  return sub;
}

function applySubEnvelope(turn, sub, envelope) {
  const p = envelope.payload;
  const phase = (label) =>
    Object.assign(turn, { phaseLabel: `Sous-agent · ${label}`, callStartedAt: Date.parse(envelope.ts), firstToken: false });
  const last = (type) => sub.steps.filter((s) => s.type === type).at(-1);
  switch (envelope.kind) {
    case "subagent_started":
      sub.started = p;
      phase(p.phase_label);
      break;
    case "subagent_ended":
      Object.assign(sub, { ended: p, status: p.status });
      break;
    case "context_rendered":
      sub.context = p;
      sub.steps.push({ type: "call", id: envelope.call_id, context: p, startedAt: null, ended: null });
      break;
    case "context_reconciled": {
      const call = sub.steps.find((s) => s.type === "call" && s.id === envelope.call_id);
      if (call) call.context = p;
      if (lastCall(sub) === call) sub.context = p;
      break;
    }
    case "context_overflow":
      sub.overflow = p;
      break;
    case "model_call_started":
      Object.assign(sub, { text: "", reasoning: "", firstToken: false });
      lastCall(sub).startedAt = Date.parse(envelope.ts);
      phase(p.phase_label);
      break;
    case "model_first_token":
      sub.firstToken = true; // the Vue humain keeps its « Sous-agent · … » indicator
      break;
    case "model_delta":
      if (p.channel !== "tool_call") sub[p.channel] += p.text;
      break;
    case "special_token_neutralized":
      sub.notices.push(p.message_fr);
      break;
    case "model_call_ended":
      Object.assign(sub, { callEnded: p, text: p.text, reasoning: p.reasoning });
      lastCall(sub).ended = p;
      break;
    case "tool_started":
      phase(p.phase_label);
      sub.steps.push({
        type: "tool",
        stepId: envelope.step_id,
        started: p,
        brick: envelope.brick,
        component: envelope.component,
        trigger: envelope.trigger,
        startedAt: Date.parse(envelope.ts),
        ended: null,
      });
      break;
    case "tool_ended": {
      const tool = last("tool");
      if (tool) tool.ended = p;
      break;
    }
    case "outbound_request": {
      const tool = last("tool");
      if (tool && p.origin === "brick") {
        (tool.outbound ||= []).push({ ...p, seq: envelope.seq, component: envelope.component });
      }
      break;
    }
    case "hook_decided":
      sub.steps.push({ type: "hook", payload: p, component: envelope.component, trigger: envelope.trigger, lines: [] });
      break;
    case "effect_applied": {
      const hook = last("hook");
      if (hook) hook.lines.push(...(p.lines ?? []));
      break;
    }
    case "approval_requested": {
      const hook = last("hook");
      if (hook) {
        hook.approval = p;
        hook.component ||= envelope.component;
      }
      Object.assign(turn, { phaseLabel: "En attente de validation", callStartedAt: Date.parse(envelope.ts), firstToken: false });
      break;
    }
    case "approval_resolved": {
      const hook = sub.steps.find((s) => s.approval?.approval_id === p.approval_id);
      if (hook) hook.resolved = p;
      turn.phaseLabel = null;
      break;
    }
    case "tool_call_malformed":
    case "prefix_not_reused":
    case "reasoning_cut":
      sub.steps.push({ type: envelope.kind, payload: p });
      break;
    case "limit_reached":
      sub.limit = p;
      sub.steps.push({ type: envelope.kind, payload: p });
      break;
    case "output_truncated":
      sub.truncated = p;
      break;
    case "harness_error":
      sub.errors.push([p.message_fr, ...(p.hints_fr ?? [])].join(" "));
      break;
  }
}

// A turn's steps, each `delegate` step followed by its sub-agent's (story 19).
function allSteps(turn) {
  return turn.steps.flatMap((step) => (step.sub ? [step, ...step.sub.steps] : [step]));
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
  savePaneLayout();
  render();
}

function showPane(paneId) {
  store.hiddenPanes.delete(paneId);
  savePaneLayout();
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
  updateBrickStatuses();
  renderChips();
  renderMenu();
  renderPaneVisibility();
  renderGauge();
  renderModelIndicator();
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
const cleared = () => store.clearedSeq !== null && store.clearedSeq > (store.resetSeq ?? -1);

// ---------- bricks panel: cards, toggles, system prompt drawer ----------

let renderedBricks = null;
let renderedArmed = null;
let renderedForceUi = null;
let renderedMemory = null;
let renderedSessionKey = null; // story 15: the download's state and progress, on the RAG card

// Story 9: the forced actions' UI changed (toggle, form): the panel is rebuilt at next render.
// Story 22: a sentinel no `store.forceForm` can equal; `null` let a closed form (back to
// `null`) pass the guard of `renderBricks`, so « Annuler » left the form open.
const STALE = Symbol("stale");
function forceUiChanged() {
  renderedForceUi = STALE;
  scheduleRender();
}

function renderBricks() {
  // Rebuilt only when the session sends new cards or armed actions, or the forced actions' UI
  // changes, so an unfolded explanation stays open.
  if (
    renderedBricks === store.bricks &&
    renderedArmed === store.armed &&
    renderedForceUi === store.forceForm &&
    renderedMemory === store.memory &&
    renderedSessionKey === sessionKey()
  ) {
    return;
  }
  renderedSessionKey = sessionKey();
  renderedBricks = store.bricks;
  renderedArmed = store.armed;
  renderedForceUi = store.forceForm;
  renderedMemory = store.memory;
  const pane = document.getElementById("bricks");
  // The rebuild would drop keyboard focus: note it, restore it on the new element. A closed
  // forced-call form gives it back to its Forcer button.
  let focusKey = pane.contains(document.activeElement) ? document.activeElement.dataset.focusKey : null;
  // A card chip disarmed leaves: the focus goes to the next chip of that card, else its toggle.
  const nextChipKey = focusKey?.startsWith("card:")
    ? document.activeElement.nextElementSibling?.dataset.focusKey ?? null
    : null;
  if (store.forceFocus) {
    const lost = !document.activeElement || document.activeElement === document.body;
    if (focusKey?.startsWith("forceform:") || lost) focusKey = store.forceFocus;
    store.forceFocus = null;
  }
  pane.innerHTML = "";
  if (!store.bricks) {
    pane.appendChild(emptyNote("En attente du harnais…"));
    return;
  }
  // Story 33: the four disciplines first, then the cards in their two groups.
  pane.appendChild(
    disciplineLegend("discipline-legend brick-legend", [...DISCIPLINES, ["network", NETWORK_FR]])
  );
  pane.appendChild(forcedToggle());
  if (store.armError) {
    const error = el("p", "force-error", store.armError);
    error.setAttribute("role", "alert");
    pane.appendChild(error);
  }
  const reopenPopovers = []; // help popovers that were open before this rebuild
  let group = null;
  for (const brick of store.bricks.bricks) {
    // Story 33: the group comes with the card (AD-1); the list's order is the display order.
    const brickGroup = brick.group === "reads" ? "reads" : "acts";
    if (brickGroup !== group) {
      group = brickGroup;
      pane.appendChild(el("h3", "brick-group-title", BRICK_GROUPS[group]));
    }
    const card = el("article", "brick-card");
    card.dataset.discipline = brick.category;
    card.dataset.brick = brick.id;
    // Story 13: a model that always reasons keeps the reasoning brick on, whatever `wanted`.
    const always = Boolean(brick.always_fr);
    // Story 22: the brick is off (or unavailable): its sub-options apply nothing, and say so.
    const parentOff = !(always || (brick.wanted && brick.available));
    const offReason = parentOff ? parentOffReason(brick) : null;
    card.classList.toggle("is-active", !parentOff);
    card.classList.toggle("is-unavailable", !brick.available);

    const head = el("label", "brick-head");
    const toggle = el("input", "brick-toggle");
    toggle.type = "checkbox";
    toggle.setAttribute("role", "switch");
    toggle.checked = always || brick.wanted;
    // A wanted brick can always be turned off, except one the model keeps on.
    toggle.disabled = always || (!brick.available && !brick.wanted);
    toggle.dataset.focusKey = `toggle:${brick.id}`;
    toggle.addEventListener("change", () => setBrick(brick.id, toggle.checked));
    head.append(toggle);
    if (always) {
      // Story 33: the switch the model locks, said by the padlock beside it.
      const lock = el("span", "brick-lock", "🔒");
      lock.title = "Verrouillé : imposé par ce modèle";
      lock.setAttribute("aria-hidden", "true");
      head.appendChild(lock);
    }
    head.appendChild(el("span", "brick-name", brick.label_fr));

    const tags = el("div", "brick-tags");
    tags.appendChild(el("span", "category-chip", brick.category_fr));
    if (brick.hosting_fr) tags.appendChild(el("span", "hosting-tag-local", brick.hosting_fr));
    // Story 33: an enabled option leaves the workstation: « 🌐 RÉSEAU » on the card itself.
    if (!parentOff && (brick.options || []).some((o) => o.enabled && o.network)) {
      tags.appendChild(el("span", "hosting-tag-network brick-network", "RÉSEAU"));
    }
    // Story 33: what the brick weighs or does now, refreshed in place (`updateBrickStatuses`).
    const status = el("p", "brick-status", brickStatus(brick));
    status.dataset.brick = brick.id;
    card.append(head, tags, status);

    if (!brick.available && brick.reason_fr) card.appendChild(el("p", "brick-reason", brick.reason_fr));
    if (brick.id === "rag") card.append(...downloadParts(brick), ...rerankParts(brick, offReason));
    if (always) {
      const why = el("p", "brick-reason brick-always", brick.always_fr);
      why.id = `always-${brick.id}`;
      toggle.setAttribute("aria-describedby", why.id);
      card.appendChild(why);
    }
    if (brick.note_fr) card.appendChild(el("p", "brick-note", brick.note_fr));
    // Story 23: what leaves the workstation and where to read it, outside the folded options.
    if (brick.outbound_fr) card.appendChild(el("p", "brick-outbound", brick.outbound_fr));
    if (brick.pending) card.appendChild(el("p", "brick-pending", "Prend effet au prochain tour"));
    // Story 9: its armed actions, always visible (the Forcer buttons may be hidden).
    const armed = store.armed.filter((a) => a.brick === brick.id);
    if (armed.length) card.appendChild(armedChips(armed, `card:${brick.id}`));

    if (brick.options?.length) card.appendChild(brickOptions(brick, offReason));
    if (brick.limits_fr) card.appendChild(el("p", "brick-limits", brick.limits_fr));
    // Story 19: a brick without sub-option forces its action from the card itself.
    if (brick.force && store.showForced) card.append(...cardForce(brick));

    if (brick.explanation_fr?.length) {
      // ponytail: CSS anchor positioning (Chromium) has no fallback for other engines;
      // acceptable here since the demo targets a Chromium-based browser on the PC.
      const anchorName = `--brick-anchor-${brick.id}`;
      card.style.setProperty("anchor-name", anchorName);
      const help = el("button", "brick-help", "?");
      help.type = "button";
      help.setAttribute("popovertarget", `explain-${brick.id}`);
      help.setAttribute("aria-label", `Ce que la brique ${brick.label_fr} ajoute`);
      const popover = el("div", "brick-explanation");
      popover.id = `explain-${brick.id}`;
      popover.setAttribute("popover", "");
      popover.style.setProperty("position-anchor", anchorName);
      popover.addEventListener("toggle", (event) => {
        if (event.newState === "open") store.openBrickHelp.add(brick.id);
        else store.openBrickHelp.delete(brick.id);
      });
      for (const block of brick.explanation_fr) {
        if (Array.isArray(block)) {
          const list = el("ul", "brick-explanation-list");
          for (const item of block) list.appendChild(el("li", "", item));
          popover.appendChild(list);
        } else {
          popover.appendChild(el("p", "", block));
        }
      }
      card.append(help, popover);
      if (store.openBrickHelp.has(brick.id)) reopenPopovers.push(popover);
    }
    if (brick.id === "global_memory") card.append(...memoryCardParts(brick));
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
  for (const popover of reopenPopovers) popover.showPopover();
  if (focusKey) {
    const find = (key) => (key ? pane.querySelector(`[data-focus-key="${cssEscape(key)}"]`) : null);
    let target = find(focusKey);
    if (!target && focusKey.startsWith("card:")) {
      const brickId = focusKey.split(":")[1];
      target = find(nextChipKey) || find(`toggle:${brickId}`);
    }
    target?.focus();
  }
}

const BRICK_GROUPS = { reads: "Ce que le modèle lit", acts: "Ce que le harnais fait" };

// Story 33: the card's status line, from received values only (AD-1): the gauge's `by_brick`,
// `reserve` and `uncompressed_used`, the memory's entries, the schema's network nodes.
// Counting a received list and the gap between two received values stay formatting.
function brickStatus(brick) {
  const always = Boolean(brick.always_fr);
  if (always) return "Imposé par ce modèle";
  if (!brick.available) return "Indisponible"; // wanted or not: it cannot be switched on
  if (!brick.wanted) return "Éteinte";
  const p = store.gauge?.payload;
  if (!p) return "En attente du modèle";
  if (brick.id === "reasoning") return `Réserve de sortie : ${plural(p.reserve, "token")}`;
  const row = (p.by_brick || []).find((b) => b.brick === brick.id);
  // Only « n tokens dans le contexte » says « ≈ » (EXPERIENCE.md > brick-card); the others count.
  const count = plural(row?.tokens ?? 0, "token");
  if (brick.id === "global_memory") return `${plural(store.memory?.entries?.length ?? 0, "entrée")} · ${count}`;
  if (brick.id === "tools" || brick.id === "mcp") {
    const on = (brick.options || []).filter((o) => o.enabled);
    const declared = `${fmt(on.length)} déclaré${on.length > 1 ? "s" : ""}`;
    if (!on.some((o) => o.network)) return `${declared} · ${count}`;
    const contacted = (store.architecture.nodes || []).filter(
      (n) =>
        n.id.startsWith(`${brick.id}.`) && n.hosting === "network" && n.contact && n.contact !== "not_contacted"
    ).length;
    return `${declared} · ${fmt(contacted)} contacté${contacted > 1 ? "s" : ""}`;
  }
  if (brick.id === "compression") {
    const gain = p.uncompressed_used == null ? 0 : p.uncompressed_used - p.used;
    return gain > 0 ? `Gain : ${plural(gain, "token")}` : "Aucun gain pour l'instant";
  }
  return `${approx(Boolean(row?.estimated))}${count} dans le contexte`;
}

// Story 33: the status lines follow the gauge, the memory and the schema without rebuilding
// the cards, so an open explanation and the keyboard focus stay put.
function updateBrickStatuses() {
  for (const brick of store.bricks?.bricks || []) {
    const line = document.querySelector(`#bricks p.brick-status[data-brick="${cssEscape(brick.id)}"]`);
    if (line) setText(line, brickStatus(brick));
  }
}

// Story 22: why a sub-option cannot be set while its brick is off: the brick's own reason when
// it is unavailable, else how to turn it on. Said on hover (`title`) and to screen readers.
function parentOffReason(brick) {
  if (!brick.available) return brick.reason_fr || `La brique ${brick.label_fr} est indisponible.`;
  return `Activez la brique ${brick.label_fr} pour régler cette option.`;
}

// Story 22: a sub-option's row whose brick is off: its switch keeps its state but is greyed
// and disabled; the session would still accept it (the API is unchanged), the UI does not.
function markParentOff(row, toggle, offReason) {
  if (!offReason) return;
  toggle.disabled = true;
  toggle.setAttribute("aria-description", offReason);
  row.classList.add("is-parent-off");
  row.title = offReason;
}

function sessionKey() {
  return `${store.sessionState?.state ?? ""}|${store.sessionState?.reason_fr ?? ""}|${store.ragNotice ?? ""}|${store.rerankNotice ?? ""}`;
}

// Story 15 (AD-21): « Télécharger » while the model is missing, the progress and « Arrêter »
// while it downloads; the figures come from the session (`session_state.reason_fr`).
function downloadParts(brick) {
  // Story 15 (AD-21): « Télécharger » while the model is missing, « Construire l'index » once
  // it is there; the progress and « Arrêter » while either runs. Figures from the session.
  const state = store.sessionState?.state;
  const jobs = { download: "Arrêter le téléchargement", index_build: "Arrêter la construction" };
  if (jobs[state]) {
    const progress = el("p", "brick-download-progress", store.sessionState.reason_fr || "En cours…");
    progress.setAttribute("role", "status");
    const stop = el("button", "brick-edit brick-download-stop", jobs[state]);
    stop.type = "button";
    stop.dataset.focusKey = `download-stop:${brick.id}`;
    stop.addEventListener("click", () => postIntention("/api/intentions/stop", {}).catch(() => {}));
    return [progress, stop];
  }
  let offer = null;
  if (brick.download) {
    const body = { target: brick.download.target };
    offer = { label: brick.download.label_fr, key: "download", run: () => ragAction("/api/intentions/download_model", body) };
  } else if (brick.build_index) {
    offer = { label: brick.build_index.label_fr, key: "build", run: () => ragAction("/api/intentions/build_rag_index", {}) };
  }
  // The last failure stays said while the card still offers an action (AD-1: from the event).
  const notice = store.ragNotice && !brick.available && offer ? [el("p", "force-error", store.ragNotice)] : [];
  if (!offer) return notice;
  const button = el("button", `brick-edit brick-${offer.key}`, offer.label);
  button.type = "button";
  button.dataset.focusKey = `${offer.key}:${brick.id}`;
  const idle = state === "idle";
  button.disabled = !idle;
  const parts = [...notice, button];
  if (!idle) {
    const why = el("p", "brick-download-why", store.sessionState?.reason_fr || "WaveStack est occupé.");
    why.id = `download-why-${brick.id}`;
    button.setAttribute("aria-describedby", why.id);
    parts.push(why);
  }
  if (store.downloadError) parts.push(el("p", "force-error", store.downloadError));
  button.addEventListener("click", offer.run);
  return parts;
}

// Story 16: the « Reranking » sub-option of the RAG card: its switch and hosting tag, its
// reason when unavailable, and « Télécharger » while its model is missing (AD-21).
function rerankParts(brick, offReason = null) {
  const option = brick.rerank;
  if (!option) return [];
  const box = el("div", "brick-suboption");
  const row = el("label", "brick-option");
  const toggle = el("input", "brick-toggle");
  toggle.type = "checkbox";
  toggle.setAttribute("role", "switch");
  toggle.checked = option.enabled;
  // Always switchable off; switchable on only when available (like a brick).
  toggle.disabled = !option.available && !option.enabled;
  toggle.dataset.focusKey = "option:rag:rerank";
  toggle.addEventListener("change", () => setOption("rag_rerank", null, toggle.checked));
  markParentOff(row, toggle, offReason);
  row.append(toggle, el("span", "brick-option-name", option.label_fr), el("span", "hosting-tag-local", option.hosting_fr));
  box.appendChild(row);
  if (!option.available && option.reason_fr) {
    const why = el("p", "brick-reason", option.reason_fr);
    why.id = "rerank-why";
    toggle.setAttribute("aria-describedby", why.id);
    box.appendChild(why);
  }
  // The last failure of its download or load (`harness_error`), while still unavailable.
  if (store.rerankNotice && !option.available) box.appendChild(el("p", "force-error", store.rerankNotice));
  if (option.download) {
    const state = store.sessionState?.state;
    const button = el("button", "brick-edit brick-download-rerank", option.download.label_fr);
    button.type = "button";
    button.dataset.focusKey = "download:rag:rerank";
    button.disabled = state !== "idle";
    if (button.disabled) button.title = store.sessionState?.reason_fr || "WaveStack est occupé.";
    button.addEventListener("click", () => ragAction("/api/intentions/download_model", { target: option.download.target }));
    box.appendChild(button);
    // A refusal (409) is said here when the card's own offer does not already say it.
    if (store.downloadError && !brick.download && !brick.build_index) box.appendChild(el("p", "force-error", store.downloadError));
  }
  return [box];
}

async function ragAction(path, body) {
  store.downloadError = null;
  try {
    const response = await postIntention(path, body);
    if (!response.ok) {
      const answer = await response.json().catch(() => ({}));
      store.downloadError = typeof answer.detail === "string" ? answer.detail : "Action refusée.";
    }
  } catch {
    store.downloadError = "WaveStack ne répond pas : rien n'a commencé.";
  }
  renderedBricks = null;
  scheduleRender();
}

function brickOptions(brick, offReason = null) {
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
  // The closed card still shows the MCP documentation mode; the brick off, that it is off
  // (story 22: a lazy loading shown while MCP is off seemed to act).
  const mode = offReason ? " · brique éteinte" : brick.mode === "lazy" ? ` · ${brick.lazy_label_fr}` : "";
  details.classList.toggle("is-parent-off", Boolean(offReason));
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
    markParentOff(row, toggle, offReason);
    row.append(
      toggle,
      el("span", "brick-option-name", option.label_fr),
      el("span", option.network ? "hosting-tag-network" : "hosting-tag-local", option.hosting_fr)
    );
    const li = el("li", "brick-option-item");
    li.appendChild(row);
    const force = store.showForced ? forceButton(brick, option) : null;
    if (force) {
      li.appendChild(force);
      const open = store.forceForm?.brick === brick.id && store.forceForm?.id === option.id;
      if (open) li.appendChild(forceForm(brick, option));
    }
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
    markParentOff(row, toggle, offReason);
    row.append(toggle, el("span", "brick-option-name", brick.lazy_label_fr));
    details.appendChild(row);
  }
  return details;
}

// ---------- forced actions (story 9, FR-42): toggle, Forcer, form with presets, chips ----------

const FORCED_STORAGE_KEY = "wavestack.forcedActions";
// EXPERIENCE: force-button labels, by brick; a native tool has none there: « Forcer l'appel ».
const FORCE_LABELS = {
  tools: "Forcer l'appel",
  skills: "Déclencher le skill",
  mcp: "Charger la documentation",
  global_memory: "Écrire en mémoire",
  subagent: "Déléguer au sous-agent",
};
// Story 14: the memory write is forced from the card itself, a form with one field whose
// help comes with the card (AD-19).
function memoryForceOption(brick) {
  return {
    id: "remember",
    label_fr: "Mémoire globale",
    parameters: { text: brick.text_help_fr || "" },
    fieldLabels: { text: "Texte" },
    presets: [],
  };
}

// Hidden by default: the SLMs are meant to act on their own. Remembered like the panes'
// layout; unreadable storage leaves the default, silently.
function loadShowForced() {
  try {
    store.showForced = localStorage.getItem(FORCED_STORAGE_KEY) === "1";
  } catch {
    store.showForced = false;
  }
}

function saveShowForced() {
  try {
    localStorage.setItem(FORCED_STORAGE_KEY, store.showForced ? "1" : "0");
  } catch {
    // No storage: the choice lasts until the page is reloaded.
  }
}

function forcedToggle() {
  const row = el("label", "force-toggle");
  const toggle = el("input", "brick-toggle");
  toggle.type = "checkbox";
  toggle.setAttribute("role", "switch");
  toggle.checked = store.showForced;
  toggle.dataset.focusKey = "force-toggle";
  toggle.addEventListener("change", () => {
    store.showForced = toggle.checked;
    if (!store.showForced) {
      store.forceForm = null;
      store.armError = null;
    }
    saveShowForced();
    renderedBricks = null; // the Forcer buttons appear or leave
    scheduleRender();
  });
  row.append(toggle, el("span", "", "Afficher les actions forcées"));
  return row;
}

function handIcon() {
  const icon = el("span", "", "👆 ");
  icon.setAttribute("aria-hidden", "true"); // the label alone is read aloud
  return icon;
}

function isFormOpen(brickId, optionId) {
  return store.forceForm?.brick === brickId && store.forceForm?.id === optionId;
}

function forceButton(brick, option) {
  // Tools, skills, and in lazy loading only, the documentation of an MCP server's tool.
  const label = FORCE_LABELS[brick.id];
  if (!label) return null;
  if (brick.id === "mcp" && (brick.mode !== "lazy" || !option.tools?.length)) return null;
  const button = el("button", "force-button");
  button.type = "button";
  button.append(handIcon(), label);
  button.setAttribute("aria-label", `${label} : ${option.label_fr}`);
  button.dataset.focusKey = `force:${brick.id}:${option.id}`;
  // A tool without parameter and a skill are armed at once; the others open their form.
  const needsForm =
    brick.id === "mcp" ||
    brick.id === "global_memory" ||
    (brick.id === "tools" && Object.keys(option.parameters || {}).length > 0);
  if (needsForm) button.setAttribute("aria-expanded", String(isFormOpen(brick.id, option.id)));
  button.addEventListener("click", () => {
    if (!needsForm) {
      armAction(brick.id === "skills" ? "skill" : "tool", option.id, {});
      return;
    }
    store.forceForm = isFormOpen(brick.id, option.id) ? null : newForceForm(brick, option);
    forceUiChanged();
  });
  return button;
}

// Story 19: the card's Forcer button and, once open, its form; `brick.force` gives the
// action's target, its parameters and presets (AD-1: from `bricks_changed`).
function cardForce(brick) {
  const force = brick.force;
  const option = { id: force.target, label_fr: brick.label_fr, parameters: force.parameters, presets: force.presets };
  const label = FORCE_LABELS[brick.id] || force.label_fr;
  const button = el("button", "force-button force-button-card");
  button.type = "button";
  button.append(handIcon(), label);
  button.dataset.focusKey = `force:${brick.id}:${option.id}`;
  const open = isFormOpen(brick.id, option.id);
  button.setAttribute("aria-expanded", String(open));
  button.addEventListener("click", () => {
    store.forceForm = isFormOpen(brick.id, option.id) ? null : newForceForm(brick, option);
    forceUiChanged();
  });
  return open ? [button, forceForm(brick, option)] : [button];
}

function presetValues(option, index) {
  // The form's fields are text; the session converts them per the tool's schema.
  const args = option.presets?.[index]?.args || {};
  return Object.fromEntries(
    Object.keys(option.parameters || {}).map((name) => {
      const value = args[name];
      return [name, value === undefined ? "" : typeof value === "string" ? value : JSON.stringify(value)];
    })
  );
}

function newForceForm(brick, option) {
  if (brick.id === "mcp") return { brick: brick.id, id: option.id, values: { tool: option.tools[0] }, error: null };
  const preset = option.presets?.length ? 0 : -1; // prefilled by the first preset
  return { brick: brick.id, id: option.id, preset, values: presetValues(option, preset), error: null };
}

function forceField(name, control, help = null) {
  const field = el("label", "force-field");
  field.append(el("span", "force-field-name", name), control);
  if (help) field.appendChild(help);
  return field;
}

function forceForm(brick, option) {
  // One field per parameter, its description as help, prefilled by a chosen preset.
  const form = store.forceForm;
  const base = `forceform:${brick.id}:${option.id}`;
  const box = el("div", "force-form");
  box.setAttribute("role", "group");
  const arm = () =>
    brick.id === "mcp"
      ? armAction("tool_doc", form.values.tool, {}, form)
      : brick.id === "global_memory"
        ? armAction("memory", option.id, { text: form.values.text ?? "" }, form)
      : brick.force
        ? armAction(brick.force.kind, brick.force.target, { ...form.values }, form)
        : armAction("tool", option.id, { ...form.values }, form);
  if (brick.id === "mcp") {
    box.setAttribute("aria-label", `Charger la documentation d'un outil de ${option.label_fr}`);
    const select = el("select");
    select.dataset.focusKey = `${base}:tool`;
    for (const name of option.tools) {
      const choice = el("option", "", name);
      choice.value = name;
      select.appendChild(choice);
    }
    select.value = form.values.tool;
    select.addEventListener("change", () => {
      form.values.tool = select.value;
    });
    box.appendChild(forceField("Outil", select));
  } else {
    box.setAttribute(
      "aria-label",
      brick.force ? `${brick.force.label_fr} : tâche et préréglages` : `Arguments de l'appel forcé : ${option.label_fr}`
    );
    if (option.presets?.length) {
      const select = el("select");
      select.dataset.focusKey = `${base}:preset`;
      option.presets.forEach((preset, i) => {
        const choice = el("option", "", preset.label_fr);
        choice.value = String(i);
        select.appendChild(choice);
      });
      const free = el("option", "", "Saisie libre");
      free.value = "-1";
      select.appendChild(free);
      select.value = String(form.preset);
      select.addEventListener("change", () => {
        const preset = Number(select.value);
        const values = preset >= 0 ? presetValues(option, preset) : form.values;
        store.forceForm = { ...form, preset, values, error: null };
        forceUiChanged();
      });
      box.appendChild(forceField("Préréglage", select));
    }
    for (const [name, description] of Object.entries(option.parameters)) {
      const input = el("input");
      input.type = "text";
      input.value = form.values[name] ?? "";
      if (brick.id === "global_memory" && store.memory?.max_chars) input.maxLength = store.memory.max_chars;
      input.dataset.focusKey = `${base}:arg:${name}`;
      const help = el("span", "force-help", description);
      help.id = `force-help-${brick.id}-${option.id}-${name}`;
      input.setAttribute("aria-describedby", help.id);
      input.addEventListener("input", () => {
        form.values[name] = input.value; // kept in place: typing never rebuilds the panel
      });
      input.addEventListener("keydown", (event) => {
        if (event.key === "Enter") {
          event.preventDefault();
          arm();
        }
      });
      box.appendChild(forceField(option.fieldLabels?.[name] ?? name, input, help));
    }
  }
  if (form.error) {
    const error = el("p", "force-error", form.error);
    error.setAttribute("role", "alert");
    box.appendChild(error);
  }
  const actions = el("div", "force-actions");
  const armButton = el("button", "force-arm", "Armer");
  armButton.type = "button";
  armButton.dataset.focusKey = `${base}:arm`;
  armButton.addEventListener("click", arm);
  const cancel = el("button", "force-cancel", "Annuler");
  cancel.type = "button";
  cancel.dataset.focusKey = `${base}:cancel`;
  cancel.addEventListener("click", () => {
    store.forceForm = null;
    store.forceFocus = `force:${brick.id}:${option.id}`;
    forceUiChanged();
  });
  actions.append(armButton, cancel);
  box.appendChild(actions);
  return box;
}

// Arm requests in flight, by form or button: a double click or a repeated Enter arms once.
const armsPending = new Set();

async function armAction(kind, target, args, form = null) {
  // Class (a): accepted at any time; the chip comes from `armed_actions_changed` (AD-1).
  const pendingKey = form ? `form:${form.brick}:${form.id}` : `${kind}:${target}`;
  if (armsPending.has(pendingKey)) return;
  armsPending.add(pendingKey);
  let error = null;
  try {
    const response = await postIntention("/api/intentions/arm", { kind, target, args });
    if (!response.ok) {
      const body = await response.json().catch(() => ({}));
      error = typeof body.detail === "string" ? body.detail : "Armement refusé : vérifiez les arguments.";
    }
  } catch {
    error = "WaveStack ne répond pas : l'action n'a pas été armée.";
  } finally {
    armsPending.delete(pendingKey);
  }
  if (!error && store.armError) {
    store.armError = null; // any successful arming clears the panel's last refusal
    renderedBricks = null;
  }
  if (form) {
    if (store.forceForm !== form) return; // closed or replaced meanwhile
    if (error) {
      store.forceForm = { ...form, error };
    } else {
      store.forceForm = null;
      store.forceFocus = `force:${form.brick}:${form.id}`;
    }
  } else {
    store.armError = error;
    renderedBricks = null;
  }
  forceUiChanged();
}

async function disarmAction(armedId) {
  try {
    await postIntention("/api/intentions/disarm", { armed_id: armedId });
  } catch {
    // The chip stays until the session says otherwise.
  }
}

function armedChips(actions, keyPrefix) {
  // EXPERIENCE: « Armé : … », a click disarms; named « Désarmer … » for screen readers.
  const row = el("div", "armed-chips");
  for (const action of actions) {
    const chip = el("button", "armed-chip");
    chip.type = "button";
    const close = el("span", "armed-chip-close", "✕");
    close.setAttribute("aria-hidden", "true");
    chip.append(handIcon(), `Armé : ${action.label_fr}`, close);
    chip.setAttribute("aria-label", `Désarmer ${action.label_fr}`);
    chip.dataset.focusKey = `${keyPrefix}:${action.armed_id}`;
    chip.addEventListener("click", () => disarmAction(action.armed_id));
    row.appendChild(chip);
  }
  return row;
}

function triggerBadge(trigger) {
  // DESIGN.md trigger-badge-*: who caused the action, told by the icon and the label.
  if (trigger !== "user" && trigger !== "model") return null;
  const user = trigger === "user";
  const badge = el("span", user ? "trigger-badge-user" : "trigger-badge-model");
  const icon = el("span", "", user ? "👆 " : "🤖 ");
  icon.setAttribute("aria-hidden", "true");
  badge.append(icon, user ? "Forcé par l'utilisateur" : "Déclenché par le modèle");
  return badge;
}

function hookTrigger(step) {
  // A hook deciding on a tool call (H1 blocking it, H5 asking): who caused that call.
  return ["before_tool", "after_tool"].includes(step.payload.point) ? step.trigger : null;
}

async function setOption(brickId, id, enabled) {
  // A tool of the tools brick, a server of the MCP brick, the MCP documentation mode, a
  // skill of the skills brick, or a hook of the hooks brick.
  const [path, body] =
    brickId === "rag_rerank"
      ? ["/api/intentions/rag_rerank", { enabled }]
      : brickId === "mcp_mode"
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

// Story 22 (M1): « Enregistrer » only when the text differs from the one the session holds;
// checked on opening, typing, saving and at each `bricks_changed`.
function syncDrawerSave() {
  const save = document.getElementById("drawer-save");
  save.disabled = drawerText().value === (store.bricks?.system_prompt.text ?? "");
  // A disabled button drops the keyboard focus to the page: it goes to the text instead.
  if (save.disabled && document.activeElement === save) drawerText().focus();
}

// Story 22 (M1): the confirmation of a save, read by screen readers (`role=status`, a live
// region always in the page, empty when silent); cleared by the next keystroke or the closing.
function drawerStatus(text) {
  document.getElementById("drawer-status").textContent = text || "";
}

function openDrawer() {
  drawerText().value = store.bricks?.system_prompt.text ?? "";
  drawerAlert(null);
  drawerStatus(null);
  syncDrawerSave();
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
  drawerStatus(null);
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
    drawerStatus(text === null ? "Prompt par défaut rétabli." : "Prompt système enregistré.");
    syncDrawerSave();
    return true;
  } catch {
    drawerStatus(null);
    drawerAlert("Enregistrement refusé : WaveStack ne répond pas. Réessayez.");
    return false;
  }
}

// ---------- global memory: card and edit drawer (story 14, FR-12, AD-23) ----------

const MEMORY_SOURCES = { model: "écrite par le modèle", user: "écrite par l'utilisateur", demo: "démonstration" };
const memoryDrawer = () => document.getElementById("memory-drawer");

function memoryCardParts(brick) {
  // The count the last `memory_changed` gives, the forced write, then the drawer's button.
  const parts = [];
  const memory = store.memory;
  if (memory && !memory.error_fr) {
    const n = memory.entries.length;
    parts.push(el("p", "brick-limits", n ? `${plural(n, "entrée")} en mémoire globale.` : "Mémoire globale vide."));
  }
  if (store.showForced) {
    const option = memoryForceOption(brick);
    const force = forceButton(brick, option);
    if (brick.note_fr) {
      // H4: no tool parser, the forced write would be dropped: said on the button itself.
      force.disabled = true;
      force.title = brick.note_fr;
      force.setAttribute("aria-description", brick.note_fr);
    }
    parts.push(force);
    if (!brick.note_fr && isFormOpen(brick.id, option.id)) parts.push(forceForm(brick, option));
  }
  const edit = el("button", "brick-edit", "Modifier la mémoire");
  edit.type = "button";
  edit.disabled = !memory || Boolean(memory.error_fr);
  edit.id = "edit-memory";
  edit.dataset.focusKey = "edit-memory";
  edit.addEventListener("click", openMemoryDrawer);
  parts.push(edit);
  return parts;
}

// `choice`: the buttons under the message, « dirty » (Enregistrer / Abandonner) or « clear »
// (Tout effacer / Annuler), the same inline pattern as the unsaved change (EXPERIENCE.md).
function memoryAlert(text, choice = null) {
  const alert = document.getElementById("memory-alert");
  alert.hidden = !text;
  alert.textContent = text || "";
  document.getElementById("memory-dirty").hidden = choice !== "dirty";
  document.getElementById("memory-confirm").hidden = choice !== "clear";
  // Story 22: while « Oui, tout effacer » waits, « Tout effacer » is not offered twice.
  document.getElementById("memory-clear").disabled = choice === "clear" || !store.memory?.entries.length;
  if (choice) document.getElementById(choice === "dirty" ? "memory-dirty-save" : "memory-confirm-clear").focus();
}

function askClearMemory() {
  const n = store.memory?.entries.length ?? 0;
  if (!n) return;
  memoryAlert(`Effacer ${n > 1 ? `les ${n} entrées` : "l'entrée"} de la mémoire globale ? Le fichier est réécrit aussitôt.`, "clear");
}

async function confirmClearMemory() {
  if (await editMemory({ op: "clear" })) document.getElementById("memory-close").focus();
}

function memoryCard() {
  return store.bricks?.bricks.find((b) => b.id === "global_memory") ?? null;
}

// The entries whose text differs from the one the session wrote: what « Enregistrer » sends.
function memoryDirty() {
  const entries = store.memory?.entries ?? [];
  return entries.filter((e) => store.memoryDrafts.has(e.id) && store.memoryDrafts.get(e.id) !== e.text);
}

function openMemoryDrawer() {
  if (!store.memory || store.memory.error_fr) return;
  if (!memoryDrawer().hidden) {
    // Already open (a click on the schema's node): its drafts stay, the focus comes back.
    (document.querySelector("#memory-list textarea") || document.getElementById("memory-close")).focus();
    return;
  }
  // The drawer lives in the bricks pane: shown first when hidden, or behind another focus.
  if (store.hiddenPanes.has("bricks")) showPane("bricks");
  if (store.focusedPane && store.focusedPane !== "bricks") {
    store.focusedPane = null;
    render();
  }
  if (!drawer().hidden) {
    closeDrawer(); // an unsaved system prompt asks first, and the memory waits
    if (!drawer().hidden) return;
  }
  store.memoryDrafts.clear();
  memoryAlert(null);
  memoryDrawer().hidden = false;
  document.getElementById("bricks").inert = true; // cards under the drawer leave the Tab order
  renderMemoryDrawer();
  const first = document.querySelector("#memory-list textarea") || document.getElementById("memory-close");
  first.focus();
}

function closeMemoryDrawer(force = false) {
  if (!force && memoryDirty().length) {
    memoryAlert("Modification non enregistrée. Enregistrer ou abandonner ?", "dirty");
    return;
  }
  store.memoryDrafts.clear();
  memoryAlert(null);
  memoryDrawer().hidden = true;
  document.getElementById("bricks").inert = false;
  document.getElementById("edit-memory")?.focus();
}

function renderMemoryDrawer() {
  // Rebuilt from the last `memory_changed`, the texts being typed kept (AD-1).
  if (memoryDrawer().hidden) return;
  const memory = store.memory;
  const list = document.getElementById("memory-list");
  const focusKey = list.contains(document.activeElement) ? document.activeElement.dataset.focusKey : null;
  const entries = memory?.entries ?? [];
  for (const id of [...store.memoryDrafts.keys()]) {
    if (!entries.some((e) => e.id === id)) store.memoryDrafts.delete(id); // deleted meanwhile
  }
  document.getElementById("memory-path").textContent = memory ? `Fichier : ${memory.path}` : "";
  const empty = document.getElementById("memory-empty");
  empty.textContent = memoryCard()?.empty_fr ?? "";
  empty.hidden = entries.length > 0;
  document.getElementById("memory-clear").disabled =
    entries.length === 0 || !document.getElementById("memory-confirm").hidden;
  list.innerHTML = "";
  entries.forEach((entry, i) => {
    const item = el("li", "memory-entry");
    const label = `Entrée ${i + 1}`;
    const head = el("div", "memory-entry-head");
    head.append(el("span", "memory-entry-name", label), el("span", "memory-entry-source", MEMORY_SOURCES[entry.source] ?? entry.source));
    const text = el("textarea", "memory-entry-text");
    text.rows = 3;
    if (memory?.max_chars) text.maxLength = memory.max_chars;
    text.spellcheck = false;
    text.value = store.memoryDrafts.get(entry.id) ?? entry.text;
    text.setAttribute("aria-label", `Texte de l'entrée ${i + 1}`);
    text.dataset.focusKey = `memory:${entry.id}:text`;
    const save = el("button", "memory-entry-save", "Enregistrer");
    save.type = "button";
    save.disabled = text.value === entry.text;
    save.setAttribute("aria-label", `Enregistrer l'entrée ${i + 1}`);
    save.dataset.focusKey = `memory:${entry.id}:save`;
    text.addEventListener("input", () => {
      store.memoryDrafts.set(entry.id, text.value); // kept in place: typing never rebuilds
      save.disabled = text.value === entry.text;
    });
    save.addEventListener("click", () => saveMemoryEntries([entry.id]));
    const remove = el("button", "memory-entry-delete", "Supprimer");
    remove.type = "button";
    remove.setAttribute("aria-label", `Supprimer l'entrée ${i + 1}`);
    remove.dataset.focusKey = `memory:${entry.id}:delete`;
    remove.addEventListener("click", () => editMemory({ op: "delete", entry_id: entry.id }));
    // Story 22: compact and flat, told apart from the footer's « Tout effacer » and « Fermer ».
    const actions = el("div", "memory-entry-actions");
    actions.append(save, remove);
    item.append(head, text, actions);
    list.appendChild(item);
  });
  if (focusKey) {
    const target = list.querySelector(`[data-focus-key="${cssEscape(focusKey)}"]`);
    (target || document.getElementById("memory-close")).focus();
  }
}

async function editMemory(body) {
  // Class (b): the session writes `memory.json`; `memory_changed` redraws the list (AD-23).
  try {
    const response = await postIntention("/api/intentions/memory", body);
    if (!response.ok) {
      const answer = await response.json().catch(() => ({}));
      memoryAlert(typeof answer.detail === "string" ? answer.detail : "Modification refusée.");
      return false;
    }
  } catch {
    memoryAlert("WaveStack ne répond pas : la mémoire n'a pas été modifiée.");
    return false;
  }
  if (body.entry_id) store.memoryDrafts.delete(body.entry_id);
  memoryAlert(null);
  return true;
}

async function saveMemoryEntries(ids) {
  for (const id of ids) {
    const text = store.memoryDrafts.get(id);
    if (text === undefined) continue;
    if (!(await editMemory({ op: "replace", entry_id: id, text }))) return false;
  }
  return true;
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

async function replayLast() {
  store.composerError = null;
  try {
    const response = await postIntention("/api/intentions/replay", {});
    if (!response.ok) {
      const body = await response.json().catch(() => ({}));
      store.composerError = typeof body.detail === "string" ? body.detail : "Rejeu refusé.";
    }
  } catch {
    store.composerError = "WaveStack ne répond pas : le rejeu n'a pas eu lieu.";
  }
  render();
}

// ---------- context gauge (top bar) ----------

function renderGauge() {
  const bar = document.getElementById("gauge-bar");
  const figures = document.getElementById("gauge-figures");
  const threshold = document.getElementById("gauge-threshold");
  const root = document.getElementById("gauge");
  bar.querySelectorAll(".gauge-seg, .gauge-free").forEach((node) => node.remove());
  const gauge = store.gauge;
  root.classList.toggle("is-overflow", Boolean(gauge?.payload.overflow));
  root.classList.toggle("is-near-limit", Boolean(gauge?.payload.near_limit));
  if (!gauge) {
    threshold.hidden = true;
    renderGaugeLegend([]);
    figures.textContent = "Contexte : en attente du modèle";
    figures.title = figures.textContent;
    return;
  }
  const p = gauge.payload;
  // flex-grow = received token counts: the bar is laid out, never recomputed (AD-1). Story 33:
  // each group in its discipline's colour (from the session), its type named in the tooltip.
  for (const item of p.breakdown) {
    const seg = el("span", "gauge-seg");
    seg.style.flexGrow = String(item.tokens);
    seg.dataset.discipline = item.discipline || "neutral";
    seg.title = `${item.label_fr} : ${fmt(item.tokens)} tokens · ${disciplineName(seg.dataset.discipline)}`;
    bar.appendChild(seg);
  }
  renderGaugeLegend(p.breakdown);
  const free = el("span", "gauge-free");
  free.style.flexGrow = String(Math.max(p.usable - p.used, 0));
  free.title = `Espace libre : ${fmt(Math.max(p.usable - p.used, 0))} tokens`;
  bar.appendChild(free);
  threshold.hidden = p.overflow; // past 100 % the bar no longer maps to `usable`
  threshold.style.left = `${p.near_limit_ratio * 100}%`;
  threshold.title = `Seuil d'alerte : ${fmt(p.near_limit_ratio * 100)} %`;

  let text = `${approxTotal(p)}${fmt(p.used)} / ${fmt(p.usable)} tokens · ${fmt(p.percent)} %`;
  if (p.overflow) text = `⚠ ${text} · contexte dépassé`;
  else if (p.near_limit) text = `⚠ ${text} · Contexte plein à ${fmt(p.percent)} %`;
  if (p.uncertain_fr) text += ` · ${p.uncertain_fr}`;
  if (gauge.preview) text += " · prochain tour";
  figures.textContent = text;
  figures.title = text; // story 33: cut on a narrow window, whole in the tooltip
  root.title =
    `Fenêtre de ${fmt(p.window)} tokens, dont ${fmt(p.reserve)} réservés à la réponse : ` +
    `${fmt(p.usable)} utilisables.`;
}

// Story 33: the disciplines present in the gauge, prompt, context, harness, then the neutral
// one; names only, no tokens per discipline (the total stays in the figures).
let renderedGaugeLegend = null;
function renderGaugeLegend(breakdown) {
  const present = new Set(breakdown.map((item) => item.discipline || "neutral"));
  const items = DISCIPLINES.filter(([d]) => present.has(d));
  if (present.has("neutral")) items.push(["neutral", NEUTRAL_FR]);
  const key = items.map(([d]) => d).join(",");
  if (key === renderedGaugeLegend) return;
  renderedGaugeLegend = key;
  const legend = document.getElementById("gauge-legend");
  legend.replaceChildren(...disciplineLegend("", items).children);
}

// AD-4: « ≈ » on an estimate; the total loses it once it comes from the API.
const approx = (estimated) => (estimated ? "≈ " : "");
const approxTotal = (p) =>
  approx(p.usage_source !== "api" && (p.segments ?? []).some((s) => s.estimated));

// The model indicator (EXPERIENCE.md model-indicator): tag, name; tooltip = the cloud warning.
function renderModelIndicator() {
  renderModelPicker();
  const button = document.getElementById("model-indicator");
  const model = store.activeModel;
  button.hidden = !model;
  if (!model) return;
  const network = model.hosting === "network";
  const served = model.kind === "server"; // story 18: a local server's model
  const key = JSON.stringify(model);
  if (button.dataset.key === key) return;
  button.dataset.key = key;
  const tag = el(
    "span",
    network ? "hosting-tag-network" : "hosting-tag-local",
    network ? `RÉSEAU · ${model.provider}` : served ? `Local · ${model.provider}` : "Local"
  );
  button.replaceChildren(tag, el("span", "model-indicator-name", model.label));
  button.title = served
    ? `Modèle servi par ${model.provider} sur ce poste (${model.server_url}) : processus distinct ` +
      "de WaveStack ; le texte envoyé est construit par le harnais."
    : model.warning_fr ??
      `Modèle local ${model.label}, sur ce poste. Cliquez pour ouvrir le diagnostic.`;
  button.setAttribute("aria-label", `Modèle actif : ${model.label}. ${button.title}`);
}

// ---------- story 17: model picker (EXPERIENCE.md model-picker), hot switch ----------

const PICK_OTHER = "other";
const modelKey = (model) => (model ? `${model.kind ?? ""}:${model.ref ?? model.id}` : "");

let modelListTimer = null;
function scheduleModelList() {
  clearTimeout(modelListTimer);
  modelListTimer = setTimeout(loadModelList, 150);
}

// The last diagnostic's list: no new discovery nor probe at the picker's opening. A failed
// fetch keeps the last list and tries again a few seconds later.
let modelListRetry = null;
async function loadModelList() {
  clearTimeout(modelListRetry);
  try {
    const response = await fetch("/api/diagnostic");
    if (!response.ok) throw new Error(`HTTP ${response.status}`);
    store.modelList = await response.json();
    store.modelListError = false;
  } catch {
    store.modelListError = true;
    modelListRetry = setTimeout(loadModelList, 5000);
  }
  renderModelPicker();
}

function pickerOption(value, text, { disabled = false, title = "" } = {}) {
  const option = el("option", "", text);
  option.value = value;
  option.disabled = disabled;
  if (title) option.title = title;
  return option;
}

let renderedPickerKey = null;

function renderModelPicker() {
  const picker = document.getElementById("model-picker");
  const apply = document.getElementById("model-picker-apply");
  const state = store.sessionState;
  const idle = state?.state === "idle"; // class (b): between two turns only
  picker.disabled = !idle || !store.modelList;
  picker.title = !idle
    ? state?.reason_fr || "Disponible hors d'un tour."
    : !store.modelList
      ? "Liste des modèles indisponible : nouvel essai dans quelques secondes."
      : "Changer de modèle : la conversation est conservée.";
  if (!idle) store.pickerPending = "";
  const active = store.activeModel;
  const key = JSON.stringify([store.modelList, modelKey(active)]);
  // A native list open under the pointer must not lose its options: rebuilt once it closes.
  if (key !== renderedPickerKey && document.activeElement !== picker) {
    renderedPickerKey = key;
    rebuildModelPicker(picker, active);
  }
  if (picker.value !== store.pickerPending) picker.value = store.pickerPending;
  if (picker.value !== store.pickerPending) store.pickerPending = ""; // its option left
  const pending = store.pickerPending;
  apply.hidden = !pending;
  apply.disabled = !idle;
  setText(
    apply,
    pending === PICK_OTHER ? "Ouvrir le diagnostic" : pending.startsWith("cloud:") ? "Choisir…" : "Charger"
  );
}

function rebuildModelPicker(picker, active) {
  const list = store.modelList ?? { candidates: [], cloud: { models: [] } };
  const local = el("optgroup");
  local.label = "Sur ce poste";
  const seen = new Set();
  for (const c of list.candidates ?? []) {
    if (c.source === "server") {
      // Story 18: a model an already-running local server serves, chosen like a file.
      const isActive = active?.kind === "server" && active.ref === c.ref;
      const unusable = c.status !== "server";
      const suffix = isActive ? " (actif)" : unusable ? " (incompatible)" : "";
      local.append(
        pickerOption(`server:${c.ref}`, `Local · ${c.provider} · ${c.name}${suffix}`, {
          disabled: isActive || unusable,
          title: unusable ? c.reason ?? "" : `${c.provider} sur ${c.server_url}`,
        })
      );
      continue;
    }
    if (c.status !== "found" || !c.path || seen.has(c.path)) continue;
    seen.add(c.path);
    const isActive = active?.kind === "file" && active.ref === c.path;
    const size = c.size_label ? ` · ${c.size_label}` : "";
    local.append(
      pickerOption(`file:${c.path}`, `${c.name}${size}${isActive ? " (actif)" : ""}`, {
        disabled: isActive,
        title: c.path,
      })
    );
  }
  const network = el("optgroup");
  network.label = "Réseau";
  for (const m of list.cloud?.models ?? []) {
    const isActive = active?.kind === "cloud" && active.ref === m.id;
    const suffix = isActive ? " (actif)" : m.disabled_fr ? " (indisponible)" : "";
    network.append(
      pickerOption(`cloud:${m.id}`, `RÉSEAU · ${m.provider} · ${m.model}${suffix}`, {
        disabled: isActive || Boolean(m.disabled_fr),
        title: m.disabled_fr ?? "",
      })
    );
  }
  const head = pickerOption("", "Changer de modèle…");
  const groups = [local, network].filter((g) => g.children.length);
  picker.replaceChildren(head, ...groups, pickerOption(PICK_OTHER, "Autre fichier ou clé API…"));
}

// `change` only notes the choice: « Charger » (or « Choisir… », « Ouvrir le diagnostic »)
// acts on it.
function notePick(event) {
  store.pickerPending = event.target.value;
  renderModelPicker();
}

async function applyPick() {
  const value = store.pickerPending;
  store.pickerPending = "";
  renderModelPicker();
  if (!value) return;
  if (value === PICK_OTHER) {
    window.location.href = "/diagnostic"; // the key and a free path stay there
    return;
  }
  const at = value.indexOf(":");
  const kind = value.slice(0, at);
  const ref = value.slice(at + 1);
  if (kind === "cloud") {
    openCloudWarning(store.modelList?.cloud?.models?.find((m) => m.id === ref));
    return;
  }
  await selectModel({ kind, ref }); // a file, or a served model (story 18)
}

async function selectModel(body) {
  store.topStatus = null;
  try {
    const response = await postIntention("/api/intentions/select_model", body);
    const answer = await response.json().catch(() => ({}));
    if (!response.ok) store.topStatus = answer.detail || "Changement de modèle refusé.";
    else if (!answer.switching) store.topStatus = answer.message_fr ?? null; // « … est déjà actif. »
  } catch (error) {
    store.topStatus = `La demande n'a pas abouti : ${error.message}. Réessayez.`;
  }
  render();
}

// EXPERIENCE.md cloud-warning: in the page, texts from `/api/diagnostic`; nothing changes
// before « Utiliser ce modèle ».
let warningModel = null;

function openCloudWarning(model) {
  if (!model?.warning) {
    // Without its warning text, a cloud model cannot be confirmed, hence not chosen (AD-21).
    store.topStatus = model
      ? "L'avertissement de ce modèle cloud est indisponible (fichier content/cloud.yaml " +
        "absent ou invalide) : il ne peut pas être choisi tant que le fichier n'est pas corrigé."
      : "Ce modèle n'est plus dans la liste : rouvrez le sélecteur.";
    render();
    return;
  }
  warningModel = model;
  const w = model.warning;
  setText(document.getElementById("cloud-warning-title"), w.title_fr);
  document
    .getElementById("cloud-warning-points")
    .replaceChildren(...["sent_fr", "provider_fr", "unseen_fr"].map((k) => el("li", "", w[k])));
  setText(document.getElementById("cloud-warning-confirm"), w.confirm_fr);
  setText(document.getElementById("cloud-warning-cancel"), w.cancel_fr);
  document.getElementById("cloud-warning").showModal();
  document.getElementById("cloud-warning-confirm").focus();
}

function bindCloudWarning() {
  const dialog = document.getElementById("cloud-warning");
  dialog.addEventListener("close", () => {
    warningModel = null;
    document.getElementById("model-picker").focus();
  });
  document.getElementById("cloud-warning-cancel").addEventListener("click", () => dialog.close());
  document.getElementById("cloud-warning-confirm").addEventListener("click", () => {
    const model = warningModel;
    dialog.close();
    if (model) selectModel({ kind: "cloud", ref: model.id, acknowledged: true });
  });
}

// The top bar and the Vue humain's stopwatch, anchored on `model_load_started.ts` (AD-1).
function modelLoadText() {
  const load = store.modelLoad;
  if (!load) return null;
  // Lot E (E4): llama.cpp cannot interrupt a load; the stop acts at the end of the step.
  const stopping = load.stopRequested ? "Arrêt demandé, effectif à la fin de l'étape en cours · " : "";
  return `${stopping}Chargement du modèle ${load.model.label}… ${seconds(Date.now() - load.startedAt)}`;
}

// ---------- human view: bubbles, working indicator, composer ----------

function turnNote(turn) {
  switch (turn.status) {
    case "overflow":
      return "Contexte dépassé : le modèle n'a pas été appelé.";
    case "limit":
      if (turn.limit) return turn.limit.message_fr;
      if (turn.truncated?.channel === "reasoning") {
        return `Sortie coupée pendant le raisonnement : la limite de ${fmt(turn.truncated.max_tokens)} tokens a été atteinte avant toute réponse. Le raisonnement reçu reste visible dans Contexte LLM.`;
      }
      return `Sortie coupée : la réponse a atteint la limite de ${fmt(turn.truncated?.max_tokens ?? 0)} tokens. Le texte reçu est conservé.`;
    case "cancelled":
      return "Arrêté à votre demande : le texte déjà reçu est conservé.";
    case "error":
      return `Erreur : ${turn.errors.join(" ") || "le tour s'est interrompu."} WaveStack reste utilisable.`;
    default:
      return null;
  }
}

// EXPERIENCE.md reasoning-block: folded by default; the user's unfolding survives the
// 250 ms rebuilds of the panes.
function reasoningBlock(text, key, title) {
  const details = el("details", "reasoning-block");
  details.open = store.openReasoning.has(key);
  const summary = el("summary", "", title);
  summary.dataset.focusKey = `reasoning:${key}`;
  details.append(summary, el("div", "reasoning-text", text));
  details.addEventListener("toggle", () => {
    if (details.open) store.openReasoning.add(key);
    else store.openReasoning.delete(key);
  });
  return details;
}

const REASONING_STORAGE_KEY = "wavestack.showReasoning";

function loadShowReasoning() {
  try {
    store.showReasoning = localStorage.getItem(REASONING_STORAGE_KEY) !== "0";
  } catch {
    store.showReasoning = true;
  }
  document.getElementById("show-reasoning").checked = store.showReasoning;
}

function toggleShowReasoning(event) {
  store.showReasoning = event.target.checked;
  try {
    localStorage.setItem(REASONING_STORAGE_KEY, store.showReasoning ? "1" : "0");
  } catch {
    // No storage: the choice lasts until the page is reloaded.
  }
  renderChat();
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
  let shownBefore = null;
  for (const turn of turns) {
    // Story 17: « Modèle : … » above the first turn shown, then above each turn played by
    // another model than the turn shown before it.
    if (turn.model && modelKey(shownBefore?.model) !== modelKey(turn.model)) {
      nodes.push(el("div", "model-switch-line", `Modèle : ${turn.model.label}`));
    }
    shownBefore = turn;
    const user = el("div", "bubble bubble-user", turn.message);
    const origin = turn.replayOf && store.turns.find((t) => t.id === turn.replayOf);
    if (origin) {
      // Story 9b: the replayed turn opens the comparison with its origin.
      const badge = el("button", "replay-badge", "Rejeu");
      badge.type = "button";
      badge.setAttribute("aria-label", `Rejeu du ${turnName(origin).toLowerCase()} : comparer`);
      badge.dataset.focusKey = `replay:${turn.id}`;
      badge.addEventListener("click", () => openCompare(origin.id, turn.id));
      user.prepend(badge);
    }
    nodes.push(user);
    const answer = el("div", "bubble bubble-model");
    // FR-9: shown here only if « Afficher le raisonnement » is ticked; Contexte LLM always.
    const reasonings = [...turn.pastReasoning, ...(turn.reasoning ? [turn.reasoning] : [])];
    if (store.showReasoning) {
      reasonings.forEach((text, i) => {
        const title = reasonings.length > 1 ? `Raisonnement (appel ${i + 1})` : "Raisonnement";
        answer.appendChild(reasoningBlock(text, `chat:${turn.id}:${i}`, title));
      });
    } else if (turn.status === null && turn.firstToken && turn.reasoning && !turn.text) {
      // The reasoning is hidden: the bubble still says the model is working.
      const since = turn.callStartedAt ?? turn.startedAt;
      answer.appendChild(el("div", "working-indicator", `Le modèle raisonne… ${seconds(Date.now() - since)}`));
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
    // H5: the validation is the user's to give, in the thread of its turn, under the answer;
    // a sub-agent's too (story 19), though its text never shows here.
    for (const step of allSteps(turn)) {
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
  const loading = modelLoadText();
  if (loading) nodes.push(el("div", "working-indicator model-load-indicator", loading));
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

let renderedComposerArmed = null;

function renderComposer() {
  const state = store.sessionState;
  const ready = state?.state === "idle" && !state.reason_fr;
  document.getElementById("composer-input").disabled = !ready;
  document.getElementById("composer-send").disabled = !ready;
  const clear = document.getElementById("clear-conversation");
  clear.disabled = state?.state !== "idle"; // class (b)
  clear.title = clear.disabled ? state?.reason_fr || "Disponible hors d'un tour." : "";
  const replay = document.getElementById("replay-last");
  replay.disabled = clear.disabled || shownTurns().length === 0; // class (b), story 9b
  replay.title = clear.disabled
    ? clear.title
    : replay.disabled
      ? "Aucun prompt à rejouer : envoyez d'abord un message."
      : "";
  const compare = document.getElementById("compare-turns");
  compare.disabled = shownTurns().length < 2;
  compare.title = compare.disabled ? "Il faut au moins deux tours pour comparer." : "";
  const stop = document.getElementById("composer-stop");
  // Lot E (E4): « Arrêter » also stops a model load (the previous model comes back).
  const loading = state?.state === "model_load" && Boolean(store.modelLoad);
  stop.hidden = state?.state !== "turn" && state?.state !== "awaiting_human" && !loading;
  stop.disabled = loading ? Boolean(store.modelLoad.stopRequested) : Boolean(activeTurn()?.stopRequested);
  const reason = document.getElementById("composer-reason");
  const text = store.composerError || (ready ? null : state?.reason_fr || "En attente du modèle…");
  reason.hidden = !text;
  reason.textContent = text || "";
  renderScenarioControls(state);
  // Story 9: the armed actions above the composer, rebuilt only when the list changes.
  if (renderedComposerArmed !== store.armed) {
    renderedComposerArmed = store.armed;
    const row = document.getElementById("armed-chips");
    const focusKey = row.contains(document.activeElement) ? document.activeElement.dataset.focusKey : null;
    row.replaceChildren(...(store.armed.length ? [armedChips(store.armed, "composer")] : []));
    row.hidden = !store.armed.length;
    if (focusKey) {
      // A disarmed chip leaves: the focus goes to the next one, else to the message field
      // when enabled (the states above are current), else to « Arrêter ».
      const target = row.querySelector(`[data-focus-key="${cssEscape(focusKey)}"]`) || row.querySelector("button");
      const input = document.getElementById("composer-input");
      (target || (input.disabled ? document.getElementById("composer-stop") : input)).focus();
    }
  }
}

// ---------- scenarios and reset (story 10, FR-38, FR-39) ----------

function findScenario(id) {
  const program = store.scenarios?.program;
  if (!program || !id) return null;
  return [...program.modules.flatMap((m) => m.scenarios), ...program.transverse].find((s) => s.id === id) ?? null;
}

let renderedProgram = null;
let renderedGuide = null;

// Story 22 (C1): the scenario's instructions fold to 3 lines so they never hide the
// conversation; « Afficher plus » only when the text overflows them, measured after each
// rendering and whenever the text's box changes size (pane resized, text size). UI state
// only, not remembered.
let guideExpanded = false;
const GUIDE_LINES = 3;

function setGuideExpanded(expanded) {
  guideExpanded = expanded;
  const more = document.getElementById("scenario-guide-more");
  document.getElementById("scenario-guide").classList.toggle("is-expanded", expanded);
  more.setAttribute("aria-expanded", String(expanded));
  more.textContent = expanded ? "Réduire" : "Afficher plus";
  measureGuide();
}

function measureGuide() {
  const guide = document.getElementById("scenario-guide");
  const text = document.getElementById("scenario-guide-text");
  const more = document.getElementById("scenario-guide-more");
  if (guide.hidden || !text.clientHeight) {
    more.hidden = true;
    return;
  }
  const line = parseFloat(getComputedStyle(text).lineHeight) || 0;
  // Folded: the clamp cuts the text; unfolded: it is taller than the three lines.
  const overflows = guideExpanded
    ? text.scrollHeight > GUIDE_LINES * line + 1
    : text.scrollHeight > text.clientHeight + 1;
  more.hidden = !overflows;
}

function renderScenarioControls(state) {
  const idle = state?.state === "idle"; // class (b)
  const reason = idle ? "" : state?.reason_fr || "Disponible hors d'un tour.";
  const picker = document.getElementById("scenario-picker");
  const program = store.scenarios?.program ?? null;
  if (renderedProgram !== program) {
    renderedProgram = program;
    const empty = el("option", "", "Choisir un scénario");
    empty.value = "";
    const groups = [];
    const group = (label, scenarios) => {
      const node = el("optgroup");
      node.label = label;
      for (const s of scenarios) {
        const option = el("option", "", s.title_fr);
        option.value = s.id;
        node.appendChild(option);
      }
      groups.push(node);
    };
    program?.modules.forEach((m, i) => group(`Module ${i + 1} · ${m.title_fr} · ${m.duration_min} min`, m.scenarios));
    // Story 21: the business scenarios (FR-40) follow the hosting one, in `transverse`.
    if (program?.transverse.length) group("Transverses et métier", program.transverse);
    picker.replaceChildren(empty, ...groups);
  }
  const active = store.scenarios?.active ?? "";
  if (picker.value !== active) picker.value = active;
  picker.disabled = !idle;
  picker.title = reason;
  const reset = document.getElementById("reset-button");
  reset.disabled = !idle;
  reset.title = reason || "Retour au LLM nu, conversation vide.";
  setTopStatus(modelLoadText() ?? store.topStatus ?? "");

  // Vue humain: the active scenario's instructions, then one chip per suggested prompt.
  const scenario = findScenario(store.scenarios?.active);
  renderScenarioUnavailable(scenario ? store.scenarios?.unavailable ?? [] : []);
  if (renderedGuide === scenario) return;
  // A refresh of the same scenario keeps the guide as the user left it (unfolded or not).
  const sameScenario = Boolean(scenario) && renderedGuide?.id === scenario.id;
  renderedGuide = scenario;
  const guide = document.getElementById("scenario-guide");
  const guideText = document.getElementById("scenario-guide-text");
  const chips = document.getElementById("suggested-prompts");
  guide.hidden = chips.hidden = !scenario;
  if (!scenario) {
    guideText.replaceChildren();
    chips.replaceChildren();
    setGuideExpanded(false);
    return;
  }
  guideText.replaceChildren(el("strong", "", scenario.title_fr), ` · ${scenario.description_fr}`);
  // Story 22: folded again at each new scenario, then measured.
  if (sameScenario) measureGuide();
  else setGuideExpanded(false);
  chips.replaceChildren(
    ...scenario.prompts.map((prompt) => {
      const chip = el("button", "suggested-prompt", prompt);
      chip.type = "button";
      chip.setAttribute("aria-label", `Remplir le champ : ${prompt}`);
      chip.addEventListener("click", () => {
        // Fills the field without sending: the trainer can comment or edit first (UJ-2).
        const input = document.getElementById("composer-input");
        input.value = prompt;
        input.focus();
      });
      return chip;
    })
  );
}

// Lot E (E5): the bricks the scenario wants and the active model cannot offer, each with its
// reason, under the scenario's instructions (the session computed them, AD-1).
let renderedUnavailable = null;

function renderScenarioUnavailable(unavailable) {
  const key = JSON.stringify(unavailable);
  if (renderedUnavailable === key) return;
  renderedUnavailable = key;
  const box = document.getElementById("scenario-unavailable");
  box.hidden = unavailable.length === 0;
  if (!unavailable.length) {
    box.replaceChildren();
    return;
  }
  const title = unavailable.length > 1
    ? "Briques du scénario indisponibles avec ce modèle :"
    : "Brique du scénario indisponible avec ce modèle :";
  const list = el("ul", "scenario-unavailable-list");
  for (const brick of unavailable) {
    const item = el("li");
    item.append(el("strong", "", brick.label_fr), ` : ${brick.reason_fr}`);
    list.appendChild(item);
  }
  box.replaceChildren(el("strong", "", title), list);
}

async function scenarioIntention(path, body, failure) {
  store.composerError = null;
  try {
    const response = await postIntention(path, body);
    if (!response.ok) {
      const detail = await response.json().catch(() => ({}));
      store.composerError = typeof detail.detail === "string" ? detail.detail : "Action refusée.";
    }
  } catch {
    store.composerError = failure;
  }
  render();
}

function launchScenario(event) {
  const id = event.target.value;
  event.target.value = store.scenarios?.active ?? ""; // the option shown follows `active`
  if (!id) return;
  scenarioIntention("/api/intentions/scenario", { scenario_id: id }, "WaveStack ne répond pas : le scénario n'a pas été lancé.");
}

function resetHarness() {
  store.openExplanations.clear();
  store.openBrickHelp.clear();
  for (const popover of document.querySelectorAll(".brick-explanation:popover-open")) popover.hidePopover();
  scenarioIntention("/api/intentions/reset", {}, "WaveStack ne répond pas : rien n'a été réinitialisé.");
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
  // Never ignored without a word: the reason stays under the field.
  if (input.disabled) {
    const reason = store.sessionState?.reason_fr;
    store.composerError = `Message non envoyé : ${reason || "WaveStack n'est pas prêt à recevoir un message."}`;
    render();
    return;
  }
  if (!message) {
    store.composerError = "Écrivez un message avant d'envoyer.";
    render();
    return;
  }
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
  if (store.sessionState?.state === "model_load" && store.modelLoad) {
    store.modelLoad.stopRequested = true; // lot E (E4)
  } else {
    const turn = activeTurn();
    if (turn) turn.stopRequested = true;
  }
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
  if (store.compare) {
    renderCompare(pane);
    return;
  }
  // The rebuild would drop keyboard focus (e.g. on the context switch): restore it.
  const focusKey = pane.contains(document.activeElement) ? document.activeElement.dataset.focusKey : null;
  renderContextBody(pane);
  if (focusKey) pane.querySelector(`[data-focus-key="${cssEscape(focusKey)}"]`)?.focus();
}

function renderContextBody(pane) {
  pane.innerHTML = "";
  const chosen = store.ctxView && shownTurns().find((t) => t.id === store.ctxView.turn);
  const turn = chosen?.subs.get(store.ctxView.sub)?.context
    ? chosen
    : shownTurns().reverse().find((t) => t.context);
  if (!turn) {
    pane.appendChild(emptyNote(cleared() ? CLEARED_FR : NO_TURN_FR));
    return;
  }
  // Story 19: « Agent principal » / « Sous-agent sub1 », one tab per sub-agent (story 22);
  // what follows is the selected tab's panel.
  const subs = [...turn.subs.values()].filter((s) => s.context);
  const view = store.ctxView?.turn === turn.id ? turn.subs.get(store.ctxView.sub) : null;
  if (subs.length) {
    const tabs = ctxViewSwitch(turn, subs, view?.context ? view : null);
    const panel = el("div", "ctx-view-panel");
    panel.id = "ctx-view-panel";
    panel.setAttribute("role", "tabpanel");
    panel.setAttribute("aria-labelledby", tabs.querySelector("[aria-selected='true']").id);
    pane.append(tabs, panel);
    pane = panel;
  }
  if (view?.context) {
    renderSubContext(pane, view);
    return;
  }
  const p = turn.context;
  if (p.body !== undefined && p.body !== null) {
    // Chat mode: the context is the JSON body sent to the provider (FR-43).
    const banner = store.activeModel?.banner_fr ?? "Modèle cloud : ce contexte est le corps JSON envoyé au fournisseur.";
    pane.appendChild(el("p", "ctx-banner", banner));
  }
  // AD-4: the provider's total replaces the sum of the segments, it is not added to it.
  const source = p.usage_source === "api" ? "total renvoyé par le fournisseur" : "somme des segments";
  pane.appendChild(
    el(
      "p",
      "ctx-total",
      `${turnName(turn)} · ${approxTotal(p)}${fmt(p.used)} tokens envoyés (${source}) · ` +
        `fenêtre ${fmt(p.window)}, réserve ${fmt(p.reserve)}`
    )
  );
  if (p.uncertain_fr) pane.appendChild(el("p", "bubble-note", p.uncertain_fr));
  if (p.uncompressed_used != null) {
    // Story 20: the session's total without compression, next to the one sent (FR-31).
    pane.appendChild(
      el(
        "p",
        "ctx-compressed-total",
        `🗜️ Sans compression : ≈ ${fmt(p.uncompressed_used)} tokens ; envoyés : ${approxTotal(p)}${fmt(p.used)}.`
      )
    );
  }
  appendSegments(pane, p, turn);
  for (const error of turn.errors) pane.appendChild(el("p", "bubble-note is-error", error));
  // FR-9: the reasoning of the last call, always here, whatever the Vue humain option says:
  // its `model_call_ended` once there, the live deltas while it streams.
  const ended = lastCall(turn).ended;
  const reasoning = ended ? ended.reasoning : turn.reasoning;
  if (reasoning) {
    pane.appendChild(el("h3", "ctx-heading", "Raisonnement du modèle"));
    pane.appendChild(reasoningBlock(reasoning, `ctx:${turn.id}`, "Afficher le raisonnement de cet appel"));
  }
  pane.appendChild(el("h3", "ctx-heading", "Sortie brute du modèle"));
  const raw = turn.callEnded ? turn.callEnded.raw_output : turn.reasoning + turn.text;
  pane.appendChild(
    el("pre", "ctx-raw", raw || (turn.overflow ? "Aucun appel : contexte dépassé." : "…"))
  );
}

// Story 20: the text a compressed segment had before, kept once by its compression step.
function textBefore(turn, was) {
  const step = turn?.steps.find((s) => s.type === "compression" && s.stepId === was.step_id);
  return step?.ended?.items[was.item]?.text_before ?? null;
}

function appendSegments(pane, p, turn = null) {
  for (const segment of p.segments) {
    const group = p.breakdown.find((item) => item.kinds.includes(segment.kind));
    const box = el("div", "ctx-segment");
    // Story 33: the rule and the background say the discipline (from the session); the swatch
    // keeps the segment type's colour, so the type stays readable.
    box.dataset.discipline = segment.discipline || "neutral";
    box.style.setProperty(
      "--segment-color",
      `var(${GROUP_COLORS[group?.group] || "--color-muted"})`
    );
    const label = el("div", "ctx-segment-label");
    label.append(
      el("span", "swatch"),
      `${segment.label_fr}${segment.brick ? ` (${segment.brick})` : ""} · ` +
        `${approx(segment.estimated)}${fmt(segment.tokens)} ${segment.tokens > 1 ? "tokens" : "token"}`
    );
    box.append(label, el("pre", "", segment.text));
    if (segment.compressed_from) {
      // Story 20: a compressed segment, and what it was before (AD-22).
      const was = segment.compressed_from;
      const tokens = `${approx(was.estimated)}${fmt(was.tokens_before)} tokens`;
      box.classList.add("ctx-compressed");
      label.append(el("span", "ctx-compressed-badge", `🗜️ compressé, ${tokens} avant`));
      const text = textBefore(turn, was);
      if (text !== null) {
        const before = el("details");
        before.append(el("summary", "", `Texte avant compression (${tokens})`), el("pre", "", text));
        box.appendChild(before);
      }
    }
    pane.appendChild(box);
  }
}

// Story 19 (EXPERIENCE: Sous-agent au travail), story 22 (M6): tabs, `aria-selected` on the
// one shown. No arrow-key navigation: every tab stays in the Tab order.
function ctxViewSwitch(turn, subs, view) {
  const bar = el("div", "ctx-view-switch");
  bar.setAttribute("role", "tablist");
  bar.setAttribute("aria-label", "Contexte affiché");
  const button = (label, target, pressed) => {
    const b = el("button", "ctx-view-button", label);
    b.type = "button";
    b.id = `ctx-tab-${target ?? "main"}`;
    b.setAttribute("role", "tab");
    b.setAttribute("aria-selected", String(pressed));
    b.setAttribute("aria-controls", "ctx-view-panel");
    b.dataset.focusKey = `ctxview:${target ?? "main"}`;
    b.addEventListener("click", () => {
      store.ctxView = target ? { turn: turn.id, sub: target } : null;
      renderContext(); // the focus stays on the button clicked, rebuilt
    });
    return b;
  };
  bar.appendChild(button("Agent principal", null, !view));
  for (const sub of subs) bar.appendChild(button(`Sous-agent ${sub.contextId}`, sub.contextId, view === sub));
  return bar;
}

function renderSubContext(pane, sub) {
  const p = sub.context;
  pane.appendChild(
    el(
      "p",
      "ctx-total",
      `Sous-agent ${sub.contextId} · ${approxTotal(p)}${fmt(p.used)} tokens envoyés (somme des segments) · ` +
        `fenêtre ${fmt(p.window)}, réserve ${fmt(p.reserve)}`
    )
  );
  if (sub.ended) {
    pane.appendChild(
      el(
        "p",
        "subagent-saving",
        `Ce contexte reste dans le sous-agent. ${subSaving(sub.ended)}`
      )
    );
  }
  appendSegments(pane, p);
  for (const notice of sub.notices) pane.appendChild(el("p", "bubble-note", notice));
  for (const error of sub.errors) pane.appendChild(el("p", "bubble-note is-error", error));
  pane.appendChild(el("h3", "ctx-heading", "Sortie brute du sous-agent"));
  const raw = sub.callEnded ? sub.callEnded.raw_output : sub.reasoning + sub.text;
  pane.appendChild(el("pre", "ctx-raw", raw || (sub.overflow ? "Aucun appel : contexte du sous-agent dépassé." : "…")));
}

// ---------- turn comparison (story 9b, EXPERIENCE.md turn-compare) ----------

// Story 22: the rail's name of a turn, its rank in the conversation shown (back to 1 after
// « Vider la conversation » or « Réinitialiser »); its id `t{n}` stays unique in the journal.
const turnNumber = (turn) => {
  const i = shownTurns().indexOf(turn);
  return i < 0 ? null : i + 1;
};
const turnName = (turn) => (turnNumber(turn) ? `Tour ${turnNumber(turn)}` : turn.id);
const turnIdTitle = (turn) => `Identifiant du tour dans le journal : ${turn.id}`;

function openCompare(left, right) {
  const turns = shownTurns();
  if (turns.length < 2) return;
  if (!left) {
    // Default: the last replayed turn and its origin, else the two last turns.
    const replayed = turns.findLast((t) => t.replayOf && turns.some((o) => o.id === t.replayOf));
    [left, right] = replayed ? [replayed.replayOf, replayed.id] : turns.slice(-2).map((t) => t.id);
  }
  store.compare = { left, right };
  if (store.hiddenPanes.delete("ctx")) savePaneLayout(); // the badge shows it in Contexte LLM
  if (store.focusedPane !== null && store.focusedPane !== "ctx") store.focusedPane = null;
  render();
  document.querySelector("#ctx .turn-compare-head select")?.focus();
}

function closeCompare() {
  store.compare = null;
  render();
  document.getElementById("compare-turns").focus();
}

// Formatting only (AD-1): sums of what each `model_call_ended` of the turn reported.
function turnFigures(turn) {
  const ended = turn.steps.filter((s) => s.type === "call" && s.ended).map((s) => s.ended);
  const sum = (key) => ended.reduce((total, e) => total + (e[key] ?? 0), 0);
  return { input: sum("prompt_tokens"), output: sum("output_tokens"), duration: turnDuration(turn) };
}

// The last rendered context's segments grouped by brick, in order of first appearance.
function brickGroups(turn) {
  const groups = new Map();
  for (const segment of turn.context?.segments ?? []) {
    const key = segment.brick ?? "";
    if (!groups.has(key)) groups.set(key, { segments: [], tokens: 0 });
    const group = groups.get(key);
    group.segments.push(segment);
    group.tokens += segment.tokens;
  }
  return groups;
}

function brickName(brick) {
  if (!brick) return "Hors brique (message et gabarit)";
  return store.bricks?.bricks?.find((b) => b.id === brick)?.label_fr ?? brick;
}

const signed = (n, unit) => `${n > 0 ? "+" : n < 0 ? "−" : "±"}${unit(Math.abs(n))}`;

function compareCell(turn, group, other) {
  const cell = el("div", "turn-compare-cell");
  if (!group) {
    const delta = other ? ` (${signed(-other.tokens, fmt)} tokens)` : "";
    cell.append(el("p", "empty-note", `${turnName(turn)} : absent de ce contexte${delta}.`));
    return cell;
  }
  const first = group.segments[0];
  const colorGroup = turn.context.breakdown.find((item) => item.kinds.includes(first.kind))?.group;
  cell.style.setProperty("--segment-color", `var(${GROUP_COLORS[colorGroup] || "--color-muted"})`);
  cell.dataset.discipline = first.discipline || "neutral"; // story 33
  cell.classList.add("ctx-segment");
  const label = el("div", "ctx-segment-label");
  const delta = other === undefined ? "" : ` (${signed(group.tokens - (other?.tokens ?? 0), fmt)} tokens)`;
  label.append(el("span", "swatch"), `${turnName(turn)} · ${fmt(group.tokens)} tokens${delta}`);
  const details = el("details");
  details.append(el("summary", "", `Texte intégral (${group.segments.length} segments)`));
  for (const segment of group.segments) {
    details.append(el("div", "ctx-segment-label", `${segment.label_fr} · ${fmt(segment.tokens)} tokens`));
    details.append(el("pre", "", segment.text));
  }
  cell.append(label, details);
  return cell;
}

function renderCompare(pane) {
  const turns = shownTurns();
  const left = turns.find((t) => t.id === store.compare.left);
  const right = turns.find((t) => t.id === store.compare.right);
  if (!left || !right) {
    store.compare = null;
    renderContext();
    return;
  }
  // Rebuilt at each render: the keyboard focus is restored on the same control.
  const focusKey = pane.contains(document.activeElement) ? document.activeElement.dataset.focusKey : null;
  pane.innerHTML = "";
  const head = el("div", "turn-compare-head");
  head.append(el("h3", "ctx-heading", "Comparaison de tours"));
  for (const [side, label] of [["left", "Tour de gauche"], ["right", "Tour de droite"]]) {
    const select = el("select");
    select.setAttribute("aria-label", label);
    select.dataset.focusKey = `compare:${side}`;
    for (const turn of turns) {
      const option = el("option", "", `${turnName(turn)}${turn.replayOf ? " (rejeu)" : ""} · « ${turn.message} »`);
      option.value = turn.id;
      option.selected = turn.id === store.compare[side];
      select.append(option);
    }
    select.addEventListener("change", () => {
      store.compare = { ...store.compare, [side]: select.value };
      render();
    });
    head.append(select);
  }
  const close = el("button", "pane-text-action", "Fermer");
  close.type = "button";
  close.dataset.focusKey = "compare:close";
  close.addEventListener("click", closeCompare);
  head.append(close);
  pane.append(head);

  const grid = el("div", "turn-compare");
  const [a, b] = [turnFigures(left), turnFigures(right)];
  // A running turn has no measured time yet: « en cours », and no time difference.
  if (left.status === null) a.duration = null;
  if (right.status === null) b.duration = null;
  const time = (ms) => (ms === null ? "en cours" : seconds(ms));
  for (const [turn, figures, other] of [[left, a, null], [right, b, a]]) {
    const card = el("div", "turn-compare-figures");
    card.append(el("div", "turn-group-title", `${turnName(turn)}${turn.replayOf ? " · Rejeu" : ""}`));
    card.append(el("div", "turn-compare-model", `Modèle : ${turn.model?.label ?? "inconnu"}`));
    const diff = (key, unit) =>
      other && figures[key] !== null && other[key] !== null ? ` (${signed(figures[key] - other[key], unit)})` : "";
    card.append(
      el("div", "number", `Entrée : ${fmt(figures.input)} tokens${diff("input", fmt)}`),
      el("div", "number", `Sortie : ${fmt(figures.output)} tokens${diff("output", fmt)}`),
      el("div", "number", `Temps : ${time(figures.duration)}${diff("duration", seconds)}`)
    );
    grid.append(card);
  }
  const [ga, gb] = [brickGroups(left), brickGroups(right)];
  for (const brick of new Set([...ga.keys(), ...gb.keys()])) {
    grid.append(el("h4", "turn-compare-brick", brickName(brick)));
    grid.append(compareCell(left, ga.get(brick)), compareCell(right, gb.get(brick), ga.get(brick) ?? null));
  }
  if (!ga.size && !gb.size) grid.append(el("p", "empty-note", "Aucun contexte rendu pour ces tours."));
  pane.append(grid);
  if (focusKey) pane.querySelector(`[data-focus-key="${cssEscape(focusKey)}"]`)?.focus();
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
    // FR-30, FR-43: the rate (tokens/s) from the session; « ≈ » on what was estimated.
    const guess = approx(ended.usage_source === "estimate");
    const rate = ended.output_tps != null ? ` · Débit : ${fmt(ended.output_tps)} tokens/s` : "";
    counter.textContent = `Entrée : ${guess}${fmt(ended.prompt_tokens)} tokens · Sortie : ${guess}${fmt(ended.output_tokens)} tokens · Temps : ${seconds(ended.duration_ms)}${rate}`;
  } else if (step.startedAt) {
    counter.append(`Entrée : ${context ? approxTotal(context) : ""}${fmt(context?.used ?? 0)} tokens · Sortie : … · Temps : `, tick(step.startedAt), " (en cours)");
  } else {
    counter.textContent = `Entrée : ${context ? approxTotal(context) : ""}${fmt(context?.used ?? 0)} tokens`;
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
  const harness = step.started.source === "harness";
  const nodes = [];
  if (step.started.source?.startsWith("mcp") || (harness && step.brick === "mcp")) {
    nodes.push(el("span", "step-badge is-mcp", "MCP"));
  }
  if (step.brick === "skills") nodes.push(el("span", "step-badge is-skill", "Skill"));
  if (step.brick === "global_memory") nodes.push(el("span", "step-badge is-memory", "Mémoire globale"));
  // EXPERIENCE: trigger badge, read from the envelope's `trigger` (story 9).
  const badge = triggerBadge(step.trigger);
  if (badge) nodes.push(badge);
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
    const cut = ended.truncated;
    if (cut) {
      // Lot B (N3): the harness cut a network or MCP result before the model read it.
      const approx = cut.estimated ? "≈ " : "";
      nodes.push(el("p", "", `Résultat tronqué par le harnais : ${approx}${fmt(cut.tokens)} tokens sur ${approx}${fmt(cut.total_tokens)} (borne [tools] result_max_tokens)`));
    }
    nodes.push(el("p", "label", "Résultat"), el("pre", "step-code", ended.result));
    for (const write of step.memoryWrites || []) {
      // Story 14: what the harness wrote in memory.json, the model having only asked.
      nodes.push(el("p", "label", "Entrée écrite dans memory.json par le harnais"), el("pre", "step-code", write.text));
    }
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

const OUTBOUND_MASKED_FR = "Valeur masquée par le harnais : jamais écrite dans le journal";
const OUTBOUND_MASKED_NOTE_FR =
  "[masqué] : valeur secrète ou propre à la session (clé, cookie, identifiant de session…), remplacée par le harnais avant le journal. Le nom de l'en-tête reste visible.";
const OUTBOUND_HEADERS_AT_SEND_FR =
  "Posés par le client HTTP à l'envoi (User-Agent, Accept…) : si l'appel est accepté, ils seront visibles dans les données sortantes de l'étape de l'outil.";

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
  // Story 23: « Données sortantes », the name the user looks for and the event log's.
  const head = el("summary", "outbound-head");
  head.append(
    el("span", "outbound-tag", "🌐 RÉSEAU"),
    " · ",
    el("span", "outbound-label", "Données sortantes"),
    " ",
    el("span", "outbound-address", `${request.method} ${request.url}`)
  );
  const body = el("div", "outbound-body");
  body.append(
    el("p", "outbound-section", "Requête"),
    el("pre", "step-code", `${request.method} ${request.url}`),
    el("p", "outbound-section", "En-têtes")
  );
  if (Array.isArray(request.headers)) {
    // As the session traced them (AD-2): a value outside its allow-list arrives masked.
    const lines = el("pre", "step-code outbound-headers");
    request.headers.forEach((header, index) => {
      if (index) lines.append("\n");
      lines.append(`${header.name}: `);
      if (header.masked) {
        const masked = el("span", "outbound-masked", header.value);
        masked.title = OUTBOUND_MASKED_FR;
        lines.append(masked);
      } else {
        lines.append(header.value);
      }
    });
    // An event traced before story 23 carries none: nothing says what was sent.
    if (!request.headers.length) lines.textContent = "En-têtes non tracés pour cet événement.";
    body.append(lines);
    if (request.headers.some((header) => header.masked)) body.append(el("p", "outbound-note", OUTBOUND_MASKED_NOTE_FR));
  } else {
    // The H5 preview: headers are set by the HTTP client when sending, after the decision.
    body.append(el("p", "outbound-note", OUTBOUND_HEADERS_AT_SEND_FR));
  }
  body.append(
    el("p", "outbound-section", "Corps"),
    el("pre", "step-code", request.body || "Aucun corps : seule l'adresse sort du poste.")
  );
  details.append(head, body);
  return details;
}

// Story 15: a score with two decimals, French style (« 0,82 »).
const scoreFormat = new Intl.NumberFormat("fr-FR", { minimumFractionDigits: 2, maximumFractionDigits: 2 });

function ragBody(step) {
  // The query, where the excerpts go, then rank, document, score and foldable text; a click on
  // an excerpt selects the retriever in the schema (CAP-4).
  const ended = step.ended;
  const nodes = [el("p", "label", "Requête"), el("pre", "step-code", step.started.query)];
  if (!ended) {
    const running = el("div", "token-counter number", `${step.started.phase_label} `);
    running.appendChild(tick(step.startedAt));
    nodes.push(running);
    return nodes;
  }
  nodes.push(el("p", "", `Placement : ${ended.placement_fr}`));
  // Story 16: the reranking enabled, but not applied to this turn, and why.
  if (ended.rerank_skipped_fr) nodes.push(el("p", "bubble-note", ended.rerank_skipped_fr));
  nodes.push(el("div", "token-counter number", `Temps : ${seconds(ended.duration_ms)}`));
  if (ended.status === "error") {
    nodes.push(el("span", "step-badge", "erreur"), el("p", "", ended.error_fr));
    return nodes;
  }
  const list = el("ol", "rag-excerpts");
  for (const excerpt of ended.excerpts) {
    const item = el("li", "rag-excerpt");
    const details = el("details");
    const head = el("summary", "rag-excerpt-head");
    head.append(
      el("span", "rag-rank", `#${excerpt.position}`),
      el("span", "rag-doc", excerpt.title_fr),
      el("span", "rag-score number", scoreFormat.format(excerpt.score))
    );
    head.title = "Sélectionne le composant RAG dans le schéma ; déplie le texte de l'extrait";
    head.addEventListener("click", () => {
      store.selection = step.component || "rag.retriever";
      scheduleRender();
    });
    details.append(head, el("pre", "step-code", excerpt.text));
    item.appendChild(details);
    list.appendChild(item);
  }
  nodes.push(el("p", "label", "Extraits (rang · document · score)"), list);
  return nodes;
}

// Story 16: the order before and after reranking, side by side; the kept ones first.
function rerankKept(keep) {
  return keep > 1 ? `Seuls les ${keep} premiers après reranking entrent` : "Seul le premier après reranking entre";
}

function rerankBody(step) {
  const ended = step.ended;
  const nodes = [el("p", "label", "Requête"), el("pre", "step-code", step.started.query)];
  if (!ended) {
    const done = step.progress ? ` ${step.progress.done} / ${step.progress.total} ` : " ";
    const running = el("div", "token-counter number", `${step.started.phase_label}${done}`);
    running.appendChild(tick(step.startedAt));
    nodes.push(running);
    return nodes;
  }
  nodes.push(el("p", "", `Placement : ${ended.placement_fr}`));
  nodes.push(el("div", "token-counter number", `Temps : ${seconds(ended.duration_ms)}`));
  if (ended.status === "cancelled") {
    nodes.push(el("span", "step-badge", "arrêté"), el("p", "", ended.error_fr));
    return nodes;
  }
  if (ended.status === "error") {
    nodes.push(el("span", "step-badge", "erreur"), el("p", "", ended.error_fr));
    return nodes;
  }
  const texts = new Map((step.search?.ended?.excerpts ?? []).map((e) => [e.chunk_id, e.text]));
  const select = () => {
    store.selection = step.component || "rag.reranker";
    scheduleRender();
  };
  const kept = (excerpt) => excerpt.position <= ended.keep;
  const keepTag = (excerpt) => el("span", "rerank-keep", kept(excerpt) ? "gardé" : "écarté");
  const before = [...ended.excerpts].sort((a, b) => a.before - b.before);
  const columns = el("div", "rerank-columns");
  const beforeList = el("ol", "rerank-list rerank-before");
  for (const excerpt of before) {
    const item = el("li", `rerank-item${kept(excerpt) ? " is-kept" : " is-dropped"}`);
    item.append(
      el("span", "rag-rank", `#${excerpt.before}`),
      el("span", "rag-doc", excerpt.title_fr),
      el("span", "rag-score number", scoreFormat.format(excerpt.retrieval_score)),
      el("span", "rerank-move", `→ #${excerpt.position}`),
      keepTag(excerpt)
    );
    beforeList.appendChild(item);
  }
  const afterList = el("ol", "rerank-list rerank-after");
  for (const excerpt of ended.excerpts) {
    const item = el("li", `rerank-item${kept(excerpt) ? " is-kept" : " is-dropped"}`);
    const details = el("details");
    const head = el("summary", "rag-excerpt-head");
    const moved = excerpt.before - excerpt.position;
    const move = moved > 0 ? `↑ ${moved}` : moved < 0 ? `↓ ${-moved}` : "=";
    head.append(
      el("span", "rag-rank", `#${excerpt.position}`),
      el("span", "rerank-move", move),
      el("span", "rag-doc", excerpt.title_fr),
      el("span", "rag-score number", scoreFormat.format(excerpt.score)),
      keepTag(excerpt)
    );
    if (excerpt.truncated) head.append(el("span", "rerank-cut", "coupé"));
    head.title = `Rang ${excerpt.before} avant le reranking. Sélectionne le reranker dans le schéma ; déplie le texte`;
    head.addEventListener("click", select);
    details.append(head, el("pre", "step-code", texts.get(excerpt.chunk_id) ?? ""));
    item.appendChild(details);
    afterList.appendChild(item);
  }
  const col = (title, list) => {
    const box = el("div", "rerank-column");
    box.append(el("p", "label", title), list);
    return box;
  };
  columns.append(
    col("Avant (embedding) · rang · document · score · rang après", beforeList),
    col("Après (reranker) · rang · écart · document · score", afterList)
  );
  const cut = ended.excerpts.filter((e) => e.truncated).length;
  const notes = [`${rerankKept(ended.keep)} dans le contexte ; les deux scores ne se comparent pas.`];
  if (cut) {
    notes.push(
      `${plural(cut, "extrait")} coupé${cut > 1 ? "s" : ""} pour tenir dans la paire question + extrait du reranker ([rag.reranker] max_tokens) : noté${cut > 1 ? "s" : ""} sur son début.`
    );
  }
  nodes.push(columns, ...notes.map((note) => el("p", "rerank-note", note)));
  return nodes;
}

// Story 20: « 1 240 → 310 tokens (−75 %) », the session's own sums (AD-1).
function compressionFigure(p) {
  const percent = p.tokens_before ? Math.round((100 * p.saved_tokens) / p.tokens_before) : 0;
  const mark = approx(p.estimated);
  return `${mark}${fmt(p.tokens_before)} → ${mark}${fmt(p.tokens_after)} tokens (−${percent} %)`;
}

function compressionBody(step) {
  // What each candidate was and became, with the tokens of both versions (FR-31); a click on
  // a candidate selects the compressor in the schema (CAP-4).
  const ended = step.ended;
  if (!ended) {
    const running = el("div", "token-counter number", `${step.started.phase_label} `);
    running.appendChild(tick(step.startedAt));
    return [running];
  }
  const many = ended.items.length > 1;
  const lines = [
    el(
      "p",
      "",
      `Décision du harnais (code) : avant l'appel au modèle, ${plural(ended.items.length, "texte")} ` +
        `passé${many ? "s" : ""} à ${ended.compressor_fr}. Un texte déjà lu par le modèle n'est jamais réécrit.`
    ),
    el("div", "token-counter number", `Contexte réduit : ${compressionFigure(ended)} · ${seconds(ended.duration_ms)}`),
  ];
  const list = el("ol", "compression-items"); // each error once, under its own text
  for (const item of ended.items) {
    const entry = el("li", "compression-item");
    const head = el("button", "compression-item-head");
    head.type = "button";
    head.title = "Sélectionne le compresseur dans le schéma";
    const mark = approx(ended.estimated);
    head.append(
      el("span", "compression-source", item.source_fr),
      el(
        "span",
        "compression-tokens number",
        item.changed
          ? `${mark}${fmt(item.tokens_before)} → ${mark}${fmt(item.tokens_after)} tokens`
          : `${mark}${fmt(item.tokens_before)} tokens · inchangé`
      )
    );
    head.addEventListener("click", () => {
      store.selection = step.component || "compression.compressor";
      scheduleRender();
    });
    entry.appendChild(head);
    if (item.error_fr) entry.appendChild(el("p", "bubble-note is-error", item.error_fr));
    else if (!item.changed) entry.appendChild(el("p", "label", ended.unchanged_fr));
    const before = el("details");
    before.append(el("summary", "", `Avant (${mark}${fmt(item.tokens_before)} tokens)`), el("pre", "step-code", item.text_before));
    entry.appendChild(before);
    if (item.changed) {
      const after = el("details");
      after.append(el("summary", "", `Après (${mark}${fmt(item.tokens_after)} tokens)`), el("pre", "step-code", item.text_after));
      entry.appendChild(after);
    }
    list.appendChild(entry);
  }
  lines.push(list);
  const tone = ended.status === "error" ? "error" : "info";
  return [harnessEvent(`Compression du contexte (${ended.compressor_fr})`, tone, lines)];
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
  const badge = triggerBadge(hookTrigger(step)); // on a tool call: forced or the model's
  if (badge) lines.unshift(badge);
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
// The trigger badge of a line (story 9): class, icon, label.
const TRIGGERS = {
  user: ["trigger-badge-user", "👆 ", "Forcé par l'utilisateur"],
  model: ["trigger-badge-model", "🤖 ", "Déclenché par le modèle"],
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
const LIMITS = {
  calls: "limite d'appels",
  retries: "limite d'essais",
  sub_calls: "limite de sous-appels",
  sub_retries: "limite d'essais du sous-agent",
};
const APPROVAL_FIGURES = { approved: "autorisé", refused: "refusé", cancelled: "annulé" };
// Lot A: why the engine reads the context again (`prefix_not_reused.cause`); the full
// French explanation is its `message_fr`.
const PREFIX_CAUSES = {
  in_turn: "dans le tour",
  system: "message système modifié",
  history: "historique réécrit",
  template: "gabarit",
  reset: "conversation vidée",
  replay: "rejeu",
  abandoned: "tour précédent abandonné",
  subagent: "sous-agent",
};

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
    const from = rows.length;
    stepRows(turn, step, i, calls, rows);
    // Story 33: each new row's tile in its discipline (a sub-agent's rows already have theirs).
    for (const row of rows.slice(from)) row.discipline ??= rowDiscipline(row, step);
  });
  if (turn.overflow) {
    rows.push({
      key: `${turn.id}:overflow`,
      icon: "✖",
      title: turn.contextId ? "Contexte du sous-agent dépassé" : "Contexte dépassé",
      actor: "harness",
      discipline: "harness",
      figure: `${fmt(turn.overflow.used)} / ${fmt(turn.overflow.usable)} tokens`,
      tone: "error",
      sticky: true,
      sig: 1,
      body: () => [overflowCard(turn.overflow)],
    });
  }
  return rows;
}

// Story 33: `model` for what the model does (calls, tool requests, final answers), `network`
// for what leaves the workstation, else the category of the step's brick, `harness` by default.
function rowDiscipline(row, step) {
  if (row.net) return "network";
  return brickCategory(step.brick ?? step.component?.split(".")[0]) ?? "harness";
}

// Story 33: a brick's category, as its card received it (AD-1).
const brickCategory = (id) => store.bricks?.bricks?.find((b) => b.id === id)?.category ?? null;

// The rows of one step, pushed onto `rows`.
function stepRows(turn, step, i, calls, rows) {
  {
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
        const guess = approx(ended.usage_source === "estimate");
        figure = `${guess}${fmt(ended.prompt_tokens)} lus · ${guess}${fmt(ended.output_tokens)} écrits · ${seconds(ended.duration_ms)}`;
        // Lot A: what the engine really evaluated, the tokens reused from its cache excluded.
        if (ended.evaluated_tokens != null) figure += ` · ${fmt(ended.evaluated_tokens)} tokens évalués`;
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
        discipline: "model",
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
          discipline: "model",
          figure: asked.length > 1 ? plural(asked.length, "outil") : asked[0].name,
          sig: asked.length,
          body: () => asked.map((call) => el("pre", "step-code", formatCall(call))),
        });
      }
    } else if (step.type === "tool" && step.started.tool === "delegate") {
      rows.push(delegateRow(turn, step, key));
      // Story 19: the sub-agent's own steps, as indented child lines of the delegation.
      if (step.sub) for (const row of turnRows(step.sub)) rows.push({ ...row, sub: true });
    } else if (step.type === "tool") {
      const ended = step.ended;
      const harness = step.started.source === "harness";
      let figure = `en cours · ${seconds(Date.now() - step.startedAt)}`;
      if (ended) figure = `${ended.status === "ok" ? (ended.truncated ? "OK · tronqué" : "OK") : "erreur"} · ${seconds(ended.duration_ms)}`;
      const forced = step.trigger === "user";
      rows.push({
        key,
        icon: harness ? { skills: "📘", global_memory: "💾" }[step.brick] || "📖" : "🔧",
        title: harness ? step.started.phase_label : `Exécution · ${toolLabel(step.started.tool)}`,
        actor: forced ? "user" : harness ? "model" : "harness",
        trigger: step.trigger,
        figure,
        net: step.outbound?.length ? hostOf(step.outbound[0].url) : null,
        outbound: step.outbound || [], // story 23: what `revealOutbound` looks for
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
        trigger: hookTrigger(step),
        figure,
        net: step.approval ? step.approval.destination : null,
        tone: block ? "error" : pending ? "pending" : "hook",
        sticky: block || pending,
        sig: [p, step.approval, step.resolved, step.lines.length, toolLabel(step.approval?.tool ?? "")],
        body: () => [hookCard(step)],
      });
    } else if (step.type === "rag") {
      const ended = step.ended;
      const failed = ended?.status === "error";
      let figure = `en cours · ${seconds(Date.now() - step.startedAt)}`;
      if (ended) figure = failed ? "erreur" : `${plural(ended.excerpts.length, "extrait")} · ${seconds(ended.duration_ms)}`;
      rows.push({
        key,
        icon: "📚",
        title: "Recherche RAG",
        actor: "harness",
        figure,
        tone: failed ? "error" : null,
        sticky: failed,
        sig: [Boolean(ended), ended?.status],
        body: () => ragBody(step),
      });
    } else if (step.type === "rerank") {
      // Story 16: the reranking of the search's candidates.
      const ended = step.ended;
      const failed = ended?.status === "error";
      const stopped = ended?.status === "cancelled";
      const done = step.progress ? `${step.progress.done} / ${step.progress.total} · ` : "";
      let figure = `en cours · ${done}${seconds(Date.now() - step.startedAt)}`;
      if (ended) {
        figure = stopped
          ? "arrêté"
          : failed
            ? "erreur"
            : `${plural(ended.keep, "gardé")} sur ${ended.excerpts.length} · ${seconds(ended.duration_ms)}`;
      }
      rows.push({
        key,
        icon: "↕️",
        title: "Reranking",
        actor: "harness",
        figure,
        tone: failed ? "error" : null,
        sticky: failed,
        sig: [Boolean(ended), ended?.status, step.progress?.done],
        body: () => rerankBody(step),
      });
    } else if (step.type === "compression") {
      const ended = step.ended;
      const failed = ended?.status === "error";
      let figure = `en cours · ${seconds(Date.now() - step.startedAt)}`;
      if (ended) figure = compressionFigure(ended);
      rows.push({
        key,
        icon: "🗜️",
        title: step.started.title_fr,
        actor: "harness",
        figure,
        tone: failed ? "error" : null,
        sticky: failed,
        sig: [Boolean(ended), ended?.status],
        body: () => compressionBody(step),
      });
    } else if (step.type === "action_dropped") {
      const label = step.label || "action forcée";
      rows.push({
        key,
        icon: "⊘",
        title: `Action forcée abandonnée · ${label}`,
        actor: "harness",
        trigger: "user",
        figure: "abandonnée",
        tone: "unavailable",
        sig: 1,
        body: () => [
          harnessEvent("Action forcée abandonnée", "info", [
            triggerBadge("user"),
            el("p", "", step.payload.reason_fr),
            el("p", "label", "Décision du harnais (code) : la cible n'est plus disponible au moment du tour."),
          ]),
        ],
      });
    } else if (step.type === "tool_call_malformed") {
      rows.push({
        key,
        icon: "✖",
        title: "Appel d'outil mal formé",
        actor: "harness",
        figure: step.payload.reaction === "retry" ? "nouvel essai" : turn.contextId ? "délégation arrêtée" : "tour arrêté",
        tone: "error",
        sticky: true,
        sig: 1,
        body: () => [malformedCard(step.payload)],
      });
    } else if (step.type === "limit_reached") {
      const retries = step.payload.limit.endsWith("retries");
      const title = turn.contextId ? "Borne du sous-agent atteinte" : "Borne du tour atteinte";
      rows.push({
        key,
        icon: retries ? "✖" : "⏹",
        title,
        actor: "harness",
        figure: LIMITS[step.payload.limit] || step.payload.limit,
        tone: retries ? "error" : "hook",
        sticky: retries,
        sig: 1,
        body: () => [harnessEvent(title, retries ? "error" : "info", [el("p", "", step.payload.message_fr)])],
      });
    } else if (step.type === "prefix_not_reused") {
      const cause = PREFIX_CAUSES[step.payload.cause];
      rows.push({
        key,
        icon: "ℹ",
        title: "Préfixe non réutilisé",
        actor: "harness",
        figure: `${cause ? `${cause} · ` : ""}${fmt(step.payload.common_tokens)} tokens communs`,
        tone: "hook",
        sig: 1,
        body: () => [harnessEvent("Préfixe non réutilisé", "info", [el("p", "", step.payload.message_fr)])],
      });
    } else if (step.type === "reasoning_cut") {
      // Lot C (N4): the reasoning reached its budget; the harness closed it and relaunched.
      rows.push({
        key,
        icon: "✂",
        title: "Raisonnement coupé",
        actor: "harness",
        figure: `${fmt(step.payload.reasoning_tokens)} tokens · ${fmt(step.payload.answer_reserve)} pour la réponse`,
        tone: "hook",
        sig: 1,
        body: () => [harnessEvent("Raisonnement coupé", "info", [el("p", "", step.payload.message_fr)])],
      });
    }
  }
}

// Story 19 (EXPERIENCE: Sous-agent au travail): the delegation, its trigger, and the tokens
// the main context got against those that stayed in the sub-agent's.
function delegateRow(turn, step, key) {
  const ended = step.ended;
  const done = step.sub?.ended;
  let figure = `en cours · ${seconds(Date.now() - step.startedAt)}`;
  if (done?.status === "completed") {
    figure = subFigure(done);
  } else if (done?.status === "cancelled") {
    figure = "Délégation arrêtée";
  } else if (done) {
    figure = `${SUB_STATUS[done.status] ?? done.status} · ${seconds(done.duration_ms)}`;
  } else if (ended) {
    figure = `${ended.status === "cancelled" ? "arrêtée" : "refusée"} · ${seconds(ended.duration_ms)}`;
  }
  if (done && subState(done)) figure += ` · ${subState(done)}`;
  const failed = Boolean(ended && !["ok", "cancelled"].includes(ended.status));
  return {
    key,
    icon: "👥",
    title: "Délégation au sous-agent",
    actor: step.trigger === "user" ? "user" : "model",
    trigger: step.trigger,
    figure,
    tone: failed ? "error" : null,
    sticky: failed,
    sig: [Boolean(ended), ended?.status, Boolean(done), step.sub?.steps.length ?? 0],
    body: () => delegateBody(turn, step),
  };
}

const SUB_STATUS = {
  completed: "Terminé",
  limit: "Borne atteinte",
  overflow: "Contexte du sous-agent dépassé",
  error: "Échec",
  cancelled: "Arrêté",
};

// The saving of a finished delegation, in words (AD-1: the figures are the session's).
// `kept_tokens` counts every tool reply that stayed in the sub-agent: results, errors, refusals.
function subSaving(done) {
  if (done.status === "cancelled") return "Délégation arrêtée : rien n'entre dans le contexte principal.";
  const guess = approx(done.estimated);
  const result = `${guess}${fmt(done.result_tokens)} tokens`;
  if (done.status !== "completed") {
    return `Délégation sans résultat : l'erreur (${result}) entre dans le contexte principal à sa place, aucune économie.`;
  }
  const kept = `${approx(done.context_estimated)}${fmt(done.kept_tokens ?? 0)} tokens`;
  const figures =
    `Réponses d'outils restées dans le contexte du sous-agent (ce que l'agent principal aurait lu sans délégation) : ${kept}. ` +
    `Résultat réinjecté dans le contexte principal : ${result}.`;
  if ((done.kept_tokens ?? 0) <= done.result_tokens) {
    return `${figures} Aucune économie : le résultat pèse autant ou plus que ce qu'il remplace (déléguer n'est pas gratuit).`;
  }
  return `${figures} Économie pour le contexte principal : ${guess}${fmt(done.saved_tokens)} tokens.`;
}

// Lot A (AD-11): the main context's state saved around the delegation, when it was.
function subState(done) {
  if (done.state_saved_bytes == null) return "";
  const size = (done.state_saved_bytes / 1e6).toLocaleString("fr-FR", { maximumFractionDigits: 1 });
  const restored = done.state_restore_ms != null ? `, restauré en ${seconds(done.state_restore_ms)}` : ", non restauré";
  return `état sauvegardé : ${size} Mo${restored}`;
}

// The delegation line's key figure once the sub-agent is done.
function subFigure(done) {
  const guess = approx(done.estimated);
  const saving = done.saved_tokens > 0 ? `${guess}${fmt(done.saved_tokens)} économisés` : "aucune économie";
  return `${guess}${fmt(done.result_tokens)} tokens réinjectés · ${saving}`;
}

function delegateBody(turn, step) {
  const sub = step.sub;
  const done = sub?.ended;
  const nodes = [];
  const badge = triggerBadge(step.trigger);
  if (badge) nodes.push(badge);
  nodes.push(el("p", "label", "Tâche confiée au sous-agent"), el("pre", "step-code", step.started.arguments.task ?? ""));
  if (sub?.started) {
    const tools = sub.started.tools.length ? sub.started.tools.map(toolLabel).join(", ") : "aucun";
    nodes.push(el("p", "", `Outils du sous-agent : ${tools}. Contexte propre : son prompt système, la tâche et ces outils, rien du contexte principal.`));
  }
  if (!done) {
    const running = el("div", "token-counter number", "En cours… ");
    running.appendChild(tick(step.startedAt));
    nodes.push(running);
    return nodes;
  }
  const context = `${approx(done.context_estimated)}${fmt(done.context_tokens)}`;
  const cancelled = done.status === "cancelled";
  nodes.push(
    el(
      "div",
      "token-counter number",
      `${plural(done.calls, "appel")} au modèle · Temps : ${seconds(done.duration_ms)} · ${SUB_STATUS[done.status] ?? done.status}`
    ),
    el("p", "subagent-saving", `${subSaving(done)} Contexte complet du sous-agent : ${context} tokens.`)
  );
  if (!cancelled) {
    nodes.push(
      el("p", "label", done.status === "completed" ? "Résultat (seul à revenir dans le contexte principal)" : "Erreur réinjectée à la place du résultat"),
      el("pre", "step-code", step.ended?.status === "ok" ? step.ended.result : done.result)
    );
  }
  if (sub.context) {  // no call rendered (e.g. blocked first): nothing to show
    const show = el("button", "subagent-show", "Voir le contexte du sous-agent");
    show.type = "button";
    show.addEventListener("click", () => showSubContext(turn.id, sub.contextId));
    nodes.push(show);
  }
  return nodes;
}

function showSubContext(turnId, contextId) {
  store.ctxView = { turn: turnId, sub: contextId };
  store.compare = null;
  if (store.hiddenPanes.delete("ctx")) savePaneLayout();
  if (store.focusedPane !== null && store.focusedPane !== "ctx") store.focusedPane = null;
  render();
  document.querySelector("#ctx .ctx-view-switch [aria-selected='true']")?.focus();
}

function mcpServerLabel(server) {
  const option = store.bricks?.bricks.find((b) => b.id === "mcp")?.options?.find((o) => o.id === server);
  return option?.label_fr ?? server;
}

// The MCP connections Orchestration shows (`renderSteps`): after the last clearing, from the
// conversation shown on, and after a reset those of the preparation too.
function shownConnections() {
  const visible = (s) => store.clearedSeq === null || s.seq > store.clearedSeq;
  return store.offTurn.filter(
    (s) => visible(s) && (store.resetSeq !== null || s.afterTurn >= store.chatFrom)
  );
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
    outbound: step.outbound || [], // story 23: what `revealOutbound` looks for
    // Story 33: a public server's connection leaves the workstation; a local one is MCP's.
    discipline: step.outbound?.length ? "network" : "harness",
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
      trigger: el("span", "turn-step-trigger"),
      actor: el("span", "turn-step-actor"),
      netMark: el("span", "net-mark", "🌐 RÉSEAU →"),
      netHost: el("span", "net-host"),
      figure: el("span", "turn-step-figure"),
      chevron: el("span", "turn-step-chevron"),
    };
    parts.tile.setAttribute("aria-hidden", "true");
    parts.chevron.setAttribute("aria-hidden", "true");
    line.append(...Object.values(parts));
    // Story 9: « Forcé par l'utilisateur » / « Déclenché par le modèle », icon then label.
    parts.triggerIcon = el("span");
    parts.triggerIcon.setAttribute("aria-hidden", "true");
    parts.triggerLabel = el("span");
    parts.trigger.append(parts.triggerIcon, parts.triggerLabel);
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
  if (node.tile.dataset.discipline !== row.discipline) node.tile.dataset.discipline = row.discipline;
  setText(node.name, row.title);
  setText(node.note, row.note ? ` · ${row.note}` : "");
  node.note.hidden = !row.note;
  const trigger = TRIGGERS[row.trigger] || null;
  node.trigger.hidden = !trigger;
  const triggerClass = `turn-step-trigger ${trigger ? trigger[0] : ""}`;
  if (node.trigger.className !== triggerClass) node.trigger.className = triggerClass;
  setText(node.triggerIcon, trigger ? trigger[1] : "");
  setText(node.triggerLabel, trigger ? trigger[2] : "");
  const [actorClass, actorLabel] = ACTORS[row.actor];
  node.actor.className = `turn-step-actor ${actorClass}`;
  setText(node.actor, actorLabel);
  node.netMark.hidden = !row.net;
  node.netHost.hidden = !row.net;
  setText(node.netHost, row.net || "");
  setText(node.figure, row.figure);
  setText(node.chevron, open ? "▾" : "▸");
  // The whole title in the tooltip: the line truncates it first (A10).
  const tooltip = [row.title, row.note, trigger?.[2], row.net ? `RÉSEAU → ${row.net}` : "", row.figure]
    .filter(Boolean)
    .join(" · ");
  if (node.line.title !== tooltip) node.line.title = tooltip;
  node.line.setAttribute("aria-expanded", String(open));
  const classes = ["turn-step"];
  if (row.tone) classes.push(`tone-${row.tone}`);
  if (flags.current) classes.push("is-current");
  if (flags.selected) classes.push("is-selected");
  if (row.sub) classes.push("is-sub");
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

// Story 23: the components some shown step or connection sent outbound data to, i.e. the
// network nodes a click leads from (`revealOutbound` finds something for them).
function outboundComponents() {
  const found = new Set();
  const add = (step) => {
    for (const request of step.outbound || []) found.add(request.component);
  };
  for (const turn of shownTurns()) {
    for (const step of turn.steps) {
      add(step);
      for (const sub of step.sub?.steps || []) add(sub);
    }
  }
  for (const step of shownConnections()) add(step);
  return found;
}

// Story 23: a click on a network node of the schema leads to what was sent to it. The last
// step of the turns shown (sub-agent included) whose outbound data went to that component,
// else the last connection shown: Orchestration shown again, turn and step unfolded, the view
// frozen as by a click on the step, its block open and brought on screen. Nothing sent to it
// in view: nothing to do, the node stays merely selected.
function revealOutbound(componentId) {
  const o = store.orch;
  const sentTo = (row) => row.outbound?.some((request) => request.component === componentId);
  let target = null;
  for (const turn of shownTurns()) {
    for (const row of turnRows(turn)) if (sentTo(row)) target = { row, turn };
  }
  if (!target) {
    const row = shownConnections().map(connectRow).findLast(sentTo);
    if (row) target = { row, turn: null };
  }
  if (!target) return;
  const { row, turn } = target;
  if (store.hiddenPanes.has("orch")) showPane("orch");
  if (store.focusedPane !== null && store.focusedPane !== "orch") {
    store.focusedPane = null;
    render();
  }
  if (turn) {
    // A turn step: unfolded and the view frozen, as by a click on it (`toggleStep`).
    o.turnOpen.set(turn.id, true);
    if (o.live) {
      o.live = false;
      o.userOpen = new Set(o.current && !o.currentSticky ? [o.current] : []);
    }
    o.userOpen.add(row.key);
    o.selected = row.key;
  } else {
    // A connection line: unfolded in place, no live view to freeze (`toggleStep`).
    o.prepGroupOpen = true;
    o.prepOpen.add(row.key);
  }
  for (const request of row.outbound) store.closedPayloads.delete(request.seq);
  renderSteps();
  // A body kept from the last render keeps a block the user folded: open it in place.
  const blocks = [...(railNodes.get(row.key)?.root.querySelectorAll(".outbound-payload") ?? [])];
  for (const block of blocks) block.open = true;
  blocks[0]?.scrollIntoView({ block: "nearest" });
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
  const visible = (s) => store.clearedSeq === null || s.seq > store.clearedSeq;
  const connections = (index) => store.offTurn.filter((s) => s.afterTurn === index && visible(s));
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
  // After a reset, the preparation keeps every connection seen before it (2026-09-25).
  const prep =
    store.resetSeq === null
      ? connections(store.chatFrom)
      : store.offTurn.filter((s) => s.afterTurn <= store.chatFrom && visible(s));
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
      ["turn-group-title", `Tour ${i + 1}`],
      [`turn-group-status ${statusClass}`, statusLabel],
      ["turn-group-replay", turn.replayOf ? "Rejeu" : null],
      ["turn-group-figures", figures.filter(Boolean).join(" · ")],
      ["turn-group-message", `« ${turn.message} »`],
    ]);
    node.head.title = turn.message;
    node.parts[0].title = turnIdTitle(turn); // story 22: links « Tour N » to the journal
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

// Story 33: the top bar's message may be cut on a narrow window: its whole text in the tooltip.
function setTopStatus(text) {
  const status = document.getElementById("top-status");
  setText(status, text);
  if (status.title !== text) status.title = text;
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
  // Story 11b: the diagnostic, besides the model indicator, after a separator.
  const separator = document.createElement("li");
  separator.className = "pane-menu-separator";
  separator.setAttribute("role", "separator");
  list.appendChild(separator);
  const item = document.createElement("li");
  const link = document.createElement("a");
  link.href = "/diagnostic";
  link.className = "pane-menu-link";
  link.textContent = "Diagnostic";
  item.appendChild(link);
  list.appendChild(item);
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
  // A handle only stands between two visible neighbours, never in focus mode.
  for (const handle of document.querySelectorAll(".pane-resize-handle")) {
    const pair = store.focusedPane === null ? handleNeighbours(handle.dataset.handle) : null;
    handle.hidden = !pair;
    if (pair) handle.setAttribute("aria-label", pair.label);
  }
  scheduleHandleValues();
}

// ---------- pane resizing (story 8f): gutter handles, mouse and keyboard ----------

const PANES_STORAGE_KEY = "wavestack.panes";
const TOP_ROW = ["human", "ctx", "orch"];
const PANE_SIZE_VARS = {
  bricks: "--pane-bricks-width",
  schema: "--pane-schema-height",
  human: "--pane-human-grow",
  ctx: "--pane-ctx-grow",
  orch: "--pane-orch-grow",
};
const PANE_MIN_WIDTH = 240; // same minimums as app.css (--pane-min-width / --pane-min-height)
const PANE_MIN_HEIGHT = 160;
const RESIZE_STEP = 16;
// One handle after each of these; "schema" sits between the top row and the schema.
const RESIZE_HANDLES = ["bricks", "human", "ctx", "schema"];

function paneSection(paneId) {
  return document.querySelector(`.pane[data-pane="${paneId}"]`);
}

function isPaneVisible(paneId) {
  return !store.hiddenPanes.has(paneId);
}

// The two neighbours a handle moves the boundary between, or null when it has no place (one
// side hidden). `before` / `after` are the elements measured; `label` names both panes.
function handleNeighbours(handleId) {
  if (handleId === "bricks") {
    if (!isPaneVisible("bricks") || ![...TOP_ROW, "schema"].some(isPaneVisible)) return null;
    return {
      before: paneSection("bricks"),
      after: document.querySelector(".right"),
      label: `Redimensionner entre ${PANE_LABELS.bricks} et les autres volets`,
    };
  }
  if (handleId === "schema") {
    const top = TOP_ROW.filter(isPaneVisible);
    if (!top.length || !isPaneVisible("schema")) return null;
    const names = top.map((p) => PANE_LABELS[p]).join(", ");
    return {
      before: document.querySelector(".top-row"),
      after: paneSection("schema"),
      label: `Redimensionner entre la rangée du haut (${names}) et ${PANE_LABELS.schema}`,
    };
  }
  const next = TOP_ROW.slice(TOP_ROW.indexOf(handleId) + 1).find(isPaneVisible);
  if (!isPaneVisible(handleId) || !next) return null;
  return {
    before: paneSection(handleId),
    after: paneSection(next),
    beforeId: handleId,
    afterId: next,
    label: `Redimensionner entre ${PANE_LABELS[handleId]} et ${PANE_LABELS[next]}`,
  };
}

// Current sizes along the handle's axis. For a top-row handle, also the width and the weight
// shared by the visible columns, to turn pixels back into weights.
function measureHandle(handleId) {
  const pair = handleNeighbours(handleId);
  if (!pair) return null;
  const vertical = handleId === "schema";
  const size = (el) => {
    const rect = el.getBoundingClientRect();
    return vertical ? rect.height : rect.width;
  };
  const m = { handleId, pair, a: size(pair.before), b: size(pair.after) };
  m.min = vertical ? PANE_MIN_HEIGHT : PANE_MIN_WIDTH;
  m.minAfter = m.min;
  if (handleId === "bricks") {
    // Every visible top-row column keeps its minimum, not just the right side as a whole: the
    // narrowest share (smallest weight) sets the width the columns need together.
    const weights = TOP_ROW.filter(isPaneVisible).map((p) => store.paneSizes[p] ?? 1);
    if (weights.length > 1) {
      const gutter = parseFloat(getComputedStyle(document.querySelector(".top-row")).columnGap) || 0;
      const sum = weights.reduce((total, w) => total + w, 0);
      m.minAfter = (PANE_MIN_WIDTH * sum) / Math.min(...weights) + (weights.length - 1) * gutter;
    }
  }
  if (TOP_ROW.includes(handleId)) {
    const visible = TOP_ROW.filter(isPaneVisible);
    m.total = visible.reduce((sum, p) => sum + size(paneSection(p)), 0);
    m.weight = visible.reduce((sum, p) => sum + (store.paneSizes[p] ?? 1), 0);
  }
  return m;
}

// Moves the boundary `delta` px from the measured position, within the minimums. A side already
// under its minimum (shrunk window) is never pushed further down, nor snapped up.
function moveBoundary(m, delta) {
  const lo = Math.min(m.min, m.a);
  const hi = Math.max(m.a + m.b - m.minAfter, m.a);
  const a = Math.min(hi, Math.max(lo, m.a + delta));
  const round = (value) => Math.round(value * 10000) / 10000;
  if (m.handleId === "bricks") {
    store.paneSizes.bricks = Math.round(a);
  } else if (m.handleId === "schema") {
    store.paneSizes.schema = Math.round(m.a + m.b - a);
  } else if (m.total > 0) {
    // Weights of the two neighbours only, their sum unchanged: the other columns do not move.
    store.paneSizes[m.pair.beforeId] = round((a / m.total) * m.weight);
    store.paneSizes[m.pair.afterId] = round(((m.a + m.b - a) / m.total) * m.weight);
  }
  applyPaneSizes();
  updateHandleValues();
}

// Double-click: default proportions for what this handle moves.
function resetBoundary(handleId) {
  if (handleId === "bricks" || handleId === "schema") delete store.paneSizes[handleId];
  else for (const p of TOP_ROW) delete store.paneSizes[p];
  applyPaneSizes();
  savePaneLayout();
  updateHandleValues();
}

function applyPaneSizes() {
  const layout = document.getElementById("layout");
  for (const [key, name] of Object.entries(PANE_SIZE_VARS)) {
    const value = store.paneSizes[key];
    if (value === undefined) layout.style.removeProperty(name);
    else layout.style.setProperty(name, key === "bricks" || key === "schema" ? `${value}px` : String(value));
  }
}

// aria-valuenow: share (%) of what precedes the handle, out of both neighbours.
function updateHandleValues() {
  for (const handle of document.querySelectorAll(".pane-resize-handle")) {
    if (handle.hidden) continue;
    const m = measureHandle(handle.dataset.handle);
    const total = m ? m.a + m.b : 0;
    if (!total) continue;
    const pct = (value) => String(Math.round((value / total) * 100));
    handle.setAttribute("aria-valuenow", pct(m.a));
    handle.setAttribute("aria-valuemin", pct(Math.min(m.min, m.a)));
    handle.setAttribute("aria-valuemax", pct(Math.max(total - m.minAfter, m.a)));
  }
}

let handleValuesFrame = 0;

function scheduleHandleValues() {
  if (handleValuesFrame) return;
  handleValuesFrame = requestAnimationFrame(() => {
    handleValuesFrame = 0;
    updateHandleValues();
  });
}

// Sizes and hidden panes survive a reload (not the focus mode). Missing, unreadable or corrupt
// storage leaves the defaults, silently.
function loadPaneLayout() {
  let saved = null;
  try {
    saved = JSON.parse(localStorage.getItem(PANES_STORAGE_KEY));
  } catch {
    return;
  }
  if (!saved || typeof saved !== "object") return;
  const sizes = saved.sizes && typeof saved.sizes === "object" ? saved.sizes : {};
  for (const key of Object.keys(PANE_SIZE_VARS)) {
    const value = sizes[key];
    const max = key === "bricks" || key === "schema" ? 100000 : 100;
    if (typeof value === "number" && Number.isFinite(value) && value > 0 && value <= max) {
      store.paneSizes[key] = value;
    }
  }
  if (Array.isArray(saved.hidden)) {
    const hidden = new Set(saved.hidden.filter((p) => PANES.includes(p)));
    if (hidden.size < PANES.length) store.hiddenPanes = hidden; // at least one stays visible
  }
}

function savePaneLayout() {
  try {
    localStorage.setItem(
      PANES_STORAGE_KEY,
      JSON.stringify({ hidden: [...store.hiddenPanes], sizes: store.paneSizes })
    );
  } catch {
    // No storage (private window, blocked site data): the layout just won't be remembered.
  }
}

function createResizeHandles() {
  for (const handleId of RESIZE_HANDLES) {
    const horizontal = handleId === "schema";
    const handle = document.createElement("div");
    handle.className = "pane-resize-handle";
    handle.dataset.handle = handleId;
    handle.setAttribute("role", "separator");
    handle.setAttribute("aria-orientation", horizontal ? "horizontal" : "vertical");
    handle.tabIndex = 0;
    handle.hidden = true;
    (horizontal ? document.querySelector(".top-row") : paneSection(handleId)).after(handle);

    let drag = null;
    const endDrag = () => {
      if (!drag) return;
      if (drag.moved) savePaneLayout();
      drag = null;
      handle.classList.remove("is-dragging");
      document.body.classList.remove("is-resizing-x", "is-resizing-y");
    };
    handle.addEventListener("pointerdown", (event) => {
      if (event.button !== 0) return;
      const m = measureHandle(handleId);
      if (!m) return;
      event.preventDefault(); // no text selection; focus is given explicitly
      handle.focus({ preventScroll: true });
      handle.setPointerCapture(event.pointerId);
      drag = { m, x: event.clientX, y: event.clientY, moved: false };
      handle.classList.add("is-dragging");
      document.body.classList.add(horizontal ? "is-resizing-y" : "is-resizing-x");
    });
    handle.addEventListener("pointermove", (event) => {
      if (!drag) return;
      const delta = horizontal ? event.clientY - drag.y : event.clientX - drag.x;
      if (!delta && !drag.moved) return;
      drag.moved = true;
      moveBoundary(drag.m, delta);
    });
    handle.addEventListener("pointerup", endDrag);
    handle.addEventListener("pointercancel", endDrag);
    handle.addEventListener("lostpointercapture", endDrag);
    handle.addEventListener("dblclick", () => resetBoundary(handleId));
    handle.addEventListener("keydown", (event) => {
      if (event.altKey || event.ctrlKey || event.metaKey) return; // browser shortcuts (Alt+←)
      const keys = horizontal ? ["ArrowUp", "ArrowDown"] : ["ArrowLeft", "ArrowRight"];
      const direction = keys.indexOf(event.key);
      if (direction < 0) return;
      event.preventDefault();
      const m = measureHandle(handleId);
      if (!m) return;
      moveBoundary(m, direction ? RESIZE_STEP : -RESIZE_STEP);
      savePaneLayout();
    });
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
  reasoning_cut: "Raisonnement coupé",
  model_call_started: "Appel au modèle commencé",
  model_first_token: "Premier token",
  model_delta: "Morceau de réponse",
  model_call_ended: "Appel au modèle terminé",
  special_token_neutralized: "Token spécial neutralisé",
  bricks_changed: "Briques modifiées",
  conversation_cleared: "Conversation vidée",
  scenario_changed: "Scénario",
  harness_reset: "Réinitialisation",
  tool_started: "Outil lancé",
  tool_ended: "Outil terminé",
  tool_call_malformed: "Appel d'outil mal formé",
  limit_reached: "Borne du tour atteinte",
  prefix_not_reused: "Préfixe non réutilisé",
  server_cache_used: "Cache du serveur local",
  mcp_connect_started: "Connexion MCP commencée",
  mcp_connect_ended: "Connexion MCP terminée",
  hook_decided: "Décision d'un hook",
  effect_applied: "Effet appliqué",
  approval_requested: "Validation demandée",
  approval_resolved: "Validation résolue",
  armed_actions_changed: "Actions armées",
  action_dropped: "Action forcée abandonnée",
  memory_changed: "Mémoire globale modifiée",
  model_load_started: "Chargement du modèle commencé",
  model_load_ended: "Chargement du modèle terminé",
  subagent_started: "Sous-agent lancé",
  subagent_ended: "Sous-agent terminé",
  rag_search_started: "Recherche RAG commencée",
  rag_search_ended: "Recherche RAG terminée",
  rag_rerank_started: "Reranking commencé",
  rag_rerank_progress: "Reranking en cours",
  rag_rerank_ended: "Reranking terminé",
  compression_started: "Compression commencée",
  compression_ended: "Compression terminée",
};
const MODEL_LOAD_STATUS = {
  ok: "chargé",
  restored: "retour au modèle précédent",
  cancelled: "chargement arrêté",
  error: "échec",
};
const MEMORY_OPS = { add: "Ajout en mémoire", replace: "Modification en mémoire", delete: "Suppression en mémoire" };
const SESSION_STATES = {
  idle: "prête",
  turn: "tour en cours",
  awaiting_human: "attente de validation",
  model_load: "chargement du modèle",
  download: "téléchargement",
  index_build: "construction de l'index RAG",
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
    case "model_load_started":
      return p.phase_label;
    case "model_load_ended":
      return [`${p.model.label} : ${MODEL_LOAD_STATUS[p.status] ?? p.status}`, seconds(p.duration_ms), p.reason_fr]
        .filter(Boolean)
        .join(" · ");
    case "model_call_ended": {
      const evaluated = p.evaluated_tokens != null ? ` · ${fmt(p.evaluated_tokens)} évalués` : "";
      return `${fmt(p.prompt_tokens)} lus${evaluated} · ${fmt(p.output_tokens)} écrits · ${seconds(p.duration_ms)} · ${p.stop_reason}`;
    }
    case "tool_started":
      return formatCall({ name: p.tool, arguments: p.arguments });
    case "tool_ended":
      return `${p.status}${p.truncated ? " · tronqué" : ""} · ${seconds(p.duration_ms)}`;
    case "outbound_request":
      return `${p.method} ${p.url}`;
    case "mcp_connect_ended":
      return p.status === "ok"
        ? `${mcpServerLabel(p.server)} : ${plural(p.tools.length, "outil")} · ${seconds(p.duration_ms)}`
        : `${mcpServerLabel(p.server)} : ${p.error_fr}`;
    case "hook_decided":
      return `${p.hook.toUpperCase()} · ${p.point_fr} · ${HOOK_DECISIONS[p.decision]}`;
    case "effect_applied":
      if (p.effect === "memory_write") return `${MEMORY_OPS[p.op] ?? p.op} · « ${p.text} »`;
      if (p.effect === "model_download" || p.effect === "rag_index_write") return p.lines.join(" · ");
      if (p.effect === "audit_append") return `${plural(p.lines.length, "ligne")} au journal d'audit`;
      return p.key ?? p.id ?? p.effect;
    case "memory_changed":
      return p.error_fr ?? `${plural(p.entries.length, "entrée")} · ${p.path}`;
    case "approval_requested":
      return `${p.tool} → ${p.destination}`;
    case "approval_resolved":
      return approvalDecision(p);
    case "armed_actions_changed":
      return p.actions.length ? p.actions.map((a) => a.label_fr).join(" · ") : "aucune action armée";
    case "action_dropped":
      return p.reason_fr;
    case "subagent_started":
      return p.task;
    case "subagent_ended":
      return [p.status === "completed" ? subFigure(p) : SUB_STATUS[p.status] ?? p.status, subState(p)]
        .filter(Boolean)
        .join(" · ");
    case "rag_search_started":
      return `« ${p.query} » · ${fmt(p.top_k)} au plus`;
    case "rag_rerank_started":
      return `« ${p.query} » · ${plural(p.candidates, "candidat")}, ${plural(p.keep, "gardé")}`;
    case "rag_rerank_progress":
      return `${fmt(p.done)} / ${fmt(p.total)} extraits notés`;
    case "rag_rerank_ended":
      return p.status === "ok"
        ? `${plural(p.keep, "gardé")} sur ${p.excerpts.length} · ${seconds(p.duration_ms)}` +
            (p.excerpts.length ? ` · premier : ${p.excerpts[0].title_fr} (avant : #${p.excerpts[0].before})` : "")
        : p.error_fr;
    case "compression_started":
      return `${plural(p.items, "texte")} · ${p.compressor_fr}`;
    case "compression_ended":
      return p.status === "ok" ? compressionFigure(p) : p.error_fr;
    case "rag_search_ended":
      return p.status === "ok"
        ? `${plural(p.excerpts.length, "extrait")} · ${seconds(p.duration_ms)}` +
            (p.excerpts.length ? ` · meilleur : ${p.excerpts[0].title_fr} (${scoreFormat.format(p.excerpts[0].score)})` : "")
        : p.error_fr;
    case "tool_call_malformed":
      return p.detail_fr;
    case "output_truncated":
      return `${fmt(p.output_tokens)} / ${fmt(p.max_tokens)} tokens`;
    case "reasoning_cut":
      return `coupé à ${fmt(p.reasoning_tokens)} tokens (budget ${fmt(p.budget)}) · ${fmt(p.answer_reserve)} pour la réponse`;
    case "diagnostic_check":
      return `${p.check} : ${p.status} · ${p.message_fr}`;
    case "conversation_cleared":
      return "les tours précédents restent dans ce journal";
    case "harness_reset":
      return "retour au LLM nu ; les événements précédents restent sur le serveur";
    case "scenario_changed":
      return p.active ? (findScenario(p.active)?.title_fr ?? p.active) : "aucun scénario actif";
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
    if (e.kind === "scenario_changed" && e.payload?.refresh) continue; // lot E: not a launch
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
  setText(
    document.getElementById("event-log-title"),
    `Journal des événements (${fmt(store.journal.length - store.logFrom)})`
  );
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
  global_memory: "💾",
  reasoning: "💭",
  tools: "🔧",
  mcp: "🔌",
  skills: "📘",
  hooks: "🪝",
  subagent: "👥",
  rag: "📚",
  compression: "🗜️",
};
// A component with its own icon in the harness frame (story 16: the reranker).
const COMPONENT_ICONS = { "rag.reranker": "↕️" };
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

// The robot's pose, derived from the turn's events only (AD-1); `sub`: the sub-agent's robot,
// from the running sub-agent of the active turn (story 19).
function robotPose(sub = false) {
  const turn = activeTurn();
  const steps = sub ? [...(turn?.subs.values() ?? [])].findLast((s) => !s.ended)?.steps : turn?.steps;
  // Only calls and tools: e.g. a `prefix_not_reused` step lands between a call and its start.
  const step = steps?.filter((s) => s.type === "call" || s.type === "tool").at(-1);
  if (!step || step.ended) return "idle";
  if (step.type === "tool") return "tool";
  return step.type === "call" && step.startedAt ? "thinking" : "idle";
}

// The robot mascot (DESIGN.md > arch-model): its own drawing, « Modèle » and the model's name
// in HTML under it.
function robot(pose, modelNode, sub = false) {
  const name = modelNode?.model ?? null;
  const who = sub ? "Sous-agent : même modèle, second contexte" : `Modèle${name ? ` ${name}` : ""}`;
  const label = `${who} : ${POSE_LABELS[pose]}`;
  const classes = `robot${sub ? " robot-sub" : ""}${pose === "idle" ? "" : " is-active"}`;
  const button = schemaButton(classes, sub ? "core.model_sub" : "core.model");
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
  button.append(svg, el("span", "robot-label", sub ? "Sous-agent" : "Modèle"));
  // The frame is narrow: a long file name is cut by the style, the tooltip keeps it whole.
  if (name && !sub) button.appendChild(el("span", "robot-model", name));
  if (modelNode && !modelNode.available) button.classList.add("is-unavailable");
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
  const steps = allSteps(turn); // a sub-agent's tools and hooks light up too (story 19)
  let i = steps.length - 1;
  while (i >= 0 && !["tool", "hook", "rag", "rerank", "compression"].includes(steps[i].type)) i--;
  if (i < 0) return null;
  const step = steps[i];
  const drawn = (id) => nodes.some((n) => n.id === id); // only enabled hooks can act
  if (step.type === "rag") {
    // Story 15: the retriever reads the index while it searches.
    const id = step.component || "rag.retriever";
    if (step.ended || !drawn(id)) return null;
    return { component: id, mode: "on", target: drawn("file.rag_index") ? "file.rag_index" : null };
  }
  if (step.type === "rerank") {
    // Story 16: the reranker scores in the harness itself: no path.
    const id = step.component || "rag.reranker";
    return step.ended || !drawn(id) ? null : { component: id, mode: "on", target: null };
  }
  if (step.type === "compression") {
    // Story 20: the compressor works inside the harness, no path.
    const id = step.component || "compression.compressor";
    if (step.ended || !drawn(id)) return null;
    return { component: id, mode: "on", target: null };
  }
  if (step.type === "tool") {
    // A harness tool (documentation, skills, delegation) runs in the harness itself: no path.
    const id = step.component;
    if (step.ended || !id || id === "core.harness" || !drawn(id) || step.started.source === "harness") return null;
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

let outboundShown = null; // story 23: `outboundComponents()` at the last `renderSchema`

function renderSchema() {
  // Layout only: nodes, edges and availability come from `architecture_changed` (AD-12), the
  // hooks of the strip from `bricks_changed`. `render()` runs on every `model_delta`: the DOM is
  // rebuilt only when its key changes; the robot and the halo are patched on their own.
  const root = document.getElementById("schema");
  const nodes = store.architecture.nodes || [];
  const wanted = (store.bricks?.bricks || []).filter((b) => b.wanted);
  const hooks = wanted.find((b) => b.id === "hooks")?.options || null;
  // The hooks that blocked in the last shown turn: they stay on a red rule until the next one.
  const last = shownTurns().at(-1);
  const blocked = (last ? allSteps(last) : [])
    .filter((s) => s.type === "hook" && s.payload.decision === "block")
    .map((s) => `hooks.${s.payload.hook}`);
  const model = nodes.find((n) => n.id === "core.model");
  const subModel = nodes.find((n) => n.id === "core.model_sub"); // story 19
  const pose = robotPose();
  const subPose = subModel ? robotPose(true) : null;
  const robots = () => [robot(pose, model), ...(subModel ? [robot(subPose, subModel, true)] : [])];
  outboundShown = outboundComponents(); // story 23: the network nodes a click leads from
  const key = JSON.stringify([store.architecture, wanted.length, hooks, blocked, store.selection, [...outboundShown].sort()]);
  const robotKey = JSON.stringify([pose, subPose, model?.model]);
  if (key !== renderedSchemaKey) {
    renderedSchemaKey = key;
    renderedActivityKey = null;
    renderedRobotKey = robotKey;
    buildSchema(root, nodes, wanted.length > 0, hooks, blocked, robots());
    scheduleWires();
  }
  if (robotKey !== renderedRobotKey) {
    // A pose change swaps the robots only: the rest keeps its focus and its layout.
    renderedRobotKey = robotKey;
    for (const next of robots()) {
      const old = root.querySelector(`.robot[data-component="${next.dataset.component}"]`);
      const focused = old === document.activeElement;
      old?.replaceWith(next);
      if (focused) next.focus();
    }
  }
  const activity = schemaActivity(nodes);
  const activityKey = JSON.stringify(activity);
  if (activityKey !== renderedActivityKey) {
    renderedActivityKey = activityKey;
    schemaActive = activity;
    for (const node of root.querySelectorAll(".is-active:not(.robot)")) node.classList.remove("is-active");
    if (activity) {
      const id = cssEscape(activity.component);
      root
        .querySelector(`.arch-node[data-component="${id}"], .arch-hook[data-component="${id}"], .arch-chip[data-component="${id}"]`)
        ?.classList.add("is-active");
    }
    scheduleWires();
  }
}

function buildSchema(root, nodes, anyBrick, hooks, blocked, robotNodes) {
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
    const icon = COMPONENT_ICONS[node.id] || BRICK_ICONS[node.id.split(".")[0]] || "🧩";
    const chip = schemaButton("arch-chip", node.id, `${icon} ${node.label_fr}`);
    chip.dataset.discipline = nodeDiscipline(node); // story 33
    chip.classList.toggle("is-unavailable", !node.available);
    chip.title = [node.available ? node.label_fr : `${node.label_fr} : ${node.reason_fr}`, node.detail_fr]
      .filter(Boolean)
      .join("\n");
    chips.appendChild(chip);
  }
  if (!anyBrick) chips.appendChild(el("p", "arch-harness-empty", "Aucune brique : LLM nu"));
  // AD-12: a cloud model is drawn in the network zone, with its provider; a served model
  // (story 18) out of the harness frame, on the workstation, as the process it is.
  const model = byId["core.model"];
  const cloud = model?.hosting === "network";
  const served = model?.process === "external";
  // Story 19: the sub-agent's robot beside the model's, the same model in a second context.
  const robotRow = el("div", "arch-robots");
  robotRow.append(...robotNodes);
  core.append(...(cloud || served ? [chips] : [robotRow, chips]));
  frame.append(tag, core);
  if (hooks) frame.appendChild(hookStrip(hooks, byId, blocked));

  const local = el("div", "arch-zone arch-zone-local");
  const localRow = el("div", "arch-zone-row");
  localRow.append(frame);
  if (served) {
    const address = (model.server_url || "").replace(/^https?:\/\//, "");
    const box = el("div", "arch-server-model");
    box.title =
      `${model.provider} · processus local distinct du harnais, sur ce poste (${address}) : ` +
      "l'appel reste sur la boucle locale, le texte envoyé est construit par le harnais.";
    box.append(robotRow, el("span", "arch-node-name", `🖥 ${model.provider} · ${address}`));
    localRow.appendChild(box);
  }
  localRow.append(...schemaColumns("local", nodes));
  local.append(el("span", "arch-zone-label", "🖥 Poste de travail"), localRow);

  const boundary = el("div", "arch-boundary");
  boundary.appendChild(el("span", "arch-boundary-label", "frontière du poste"));

  const network = el("div", "arch-zone arch-zone-network");
  const networkRow = el("div", "arch-zone-row");
  const networkCols = schemaColumns("network", nodes);
  if (cloud) {
    const box = el("div", "arch-cloud-model");
    box.title = `${model.provider} · service réseau : chaque appel franchit la frontière du poste.`;
    box.append(robotRow, el("span", "arch-node-name", `🌐 ${model.provider}`));
    networkCols.unshift(box);
  }
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
    hook.dataset.discipline = brickCategory("hooks") ?? "harness"; // story 33
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

// Story 33: a node's discipline: `network` when it leaves the workstation, `neutral` for a file
// of the harness (`file.*`), else the category of its brick (`{brick}.*`).
function nodeDiscipline(node) {
  if (node.hosting === "network") return "network";
  const prefix = node.id.split(".")[0];
  return prefix === "file" ? "neutral" : brickCategory(prefix) ?? "neutral";
}

// A node: its category reads by its shape and icon, its hosting by its zone and its globe, its
// colour is its discipline's (story 33; DESIGN.md > arch-group). Returns the node, then the
// list of its tools for a selected MCP server.
function schemaNode(node, shape) {
  const network = node.hosting === "network";
  const unavailable = !node.available;
  const notContacted = node.contact === "not_contacted";
  const loaded = shape === "skill" && Boolean(node.loaded);
  const tools = node.tools || [];
  const button = schemaButton(`arch-node arch-node-${shape} ${network ? "is-network" : "is-local"}`, node.id);
  button.dataset.discipline = nodeDiscipline(node); // story 33
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
  // Story 23: a network tool or server leads to its outbound data, while a step shown has some
  // (a clearing or a reset leaves the node contacted, with nothing left to show).
  const leadsOut =
    network && (shape === "tool" || shape === "mcp") && Boolean(outboundShown?.has(node.id));
  if (leadsOut) tooltip.push("Clic : ses données sortantes dans Orchestration");
  button.title = tooltip.join("\n");
  button.setAttribute("aria-label", tooltip.join(". "));
  if (node.id === "file.audit") button.addEventListener("click", openAudit); // the whole log
  if (node.id === "file.memory") button.addEventListener("click", openMemoryDrawer); // story 14
  if (leadsOut) {
    // After `select`, which toggles: the node stays selected and always leads to its data.
    button.addEventListener("click", () => {
      if (store.selection !== node.id) select(node.id);
      revealOutbound(node.id);
    });
  }

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
  // Remembered pane layout first, so the page does not open on the defaults then jump.
  loadPaneLayout();
  loadShowForced();
  loadShowReasoning();
  document.getElementById("show-reasoning").addEventListener("change", toggleShowReasoning);
  createResizeHandles();
  applyPaneSizes();
  renderChips();
  renderMenu();
  renderPaneVisibility();
  // aria-valuenow follows the window too (bricks and schema are in px).
  new ResizeObserver(scheduleHandleValues).observe(document.getElementById("layout"));

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
  document.getElementById("replay-last").addEventListener("click", replayLast);
  document.getElementById("scenario-picker").addEventListener("change", launchScenario);
  document.getElementById("scenario-guide-more").addEventListener("click", () => setGuideExpanded(!guideExpanded));
  new ResizeObserver(measureGuide).observe(document.getElementById("scenario-guide-text"));
  const modelPicker = document.getElementById("model-picker");
  modelPicker.addEventListener("change", notePick);
  modelPicker.addEventListener("focus", loadModelList);
  modelPicker.addEventListener("blur", renderModelPicker); // a rebuild waiting for the close
  document.getElementById("model-picker-apply").addEventListener("click", applyPick);
  bindCloudWarning();
  document.getElementById("reset-button").addEventListener("click", resetHarness);
  document.getElementById("compare-turns").addEventListener("click", () => openCompare());
  document.getElementById("follow-live").addEventListener("click", followLive);
  document.getElementById("event-log-head").addEventListener("click", toggleJournal);
  document.getElementById("drawer-save").addEventListener("click", () =>
    saveSystemPrompt(drawerText().value)
  );
  document.getElementById("drawer-reset").addEventListener("click", () => saveSystemPrompt(null));
  drawerText().addEventListener("input", () => {
    drawerStatus(null);
    syncDrawerSave();
  });
  document.getElementById("drawer-close").addEventListener("click", () => closeDrawer());
  document.getElementById("drawer-dirty-save").addEventListener("click", async () => {
    if (await saveSystemPrompt(drawerText().value)) closeDrawer(true);
  });
  document.getElementById("drawer-dirty-discard").addEventListener("click", () => closeDrawer(true));
  document.getElementById("memory-close").addEventListener("click", () => closeMemoryDrawer());
  // Story 22: the cross of the drawer's head, the same path as « Fermer ».
  document.getElementById("memory-x").addEventListener("click", () => closeMemoryDrawer());
  document.getElementById("memory-clear").addEventListener("click", askClearMemory);
  document.getElementById("memory-confirm-clear").addEventListener("click", confirmClearMemory);
  document.getElementById("memory-confirm-cancel").addEventListener("click", () => {
    memoryAlert(null);
    document.getElementById("memory-clear").focus();
  });
  document.getElementById("memory-dirty-save").addEventListener("click", async () => {
    if (await saveMemoryEntries(memoryDirty().map((e) => e.id))) closeMemoryDrawer(true);
  });
  document.getElementById("memory-dirty-discard").addEventListener("click", () => closeMemoryDrawer(true));
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
    if (store.modelLoad) {
      renderChat();
      setTopStatus(modelLoadText());
    }
  }, 250);

  document.addEventListener("keydown", (event) => {
    if (event.key !== "Escape") return;
    if (document.getElementById("audit-dialog").open) return; // the dialog closes itself
    if (document.getElementById("cloud-warning").open) return;
    if (!drawer().hidden) {
      closeDrawer();
    } else if (!memoryDrawer().hidden) {
      closeMemoryDrawer();
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
    store.serverInstance = body.instance_id ?? null;
    store.liveFrom = body.seq ?? 0;
    store.sessionState = body.session_state;
    store.activeModel = body.active_model ?? null;
    store.architecture = body.architecture_changed || { nodes: [], edges: [] };
    store.bricks = body.bricks_changed;
    store.armed = body.armed_actions_changed?.actions ?? [];
    store.scenarios = body.scenario_changed;
    store.memory = body.memory_changed ?? null;
    const preview = body.context_preview;
    const rendered = body.context_rendered;
    const reconciled = body.context_reconciled;
    const latest = [preview, rendered, reconciled].filter(Boolean).sort((a, b) => b.seq - a.seq)[0];
    if (latest) store.gauge = { payload: latest.payload, preview: latest === preview };
  } catch {
    // AD-16: a failed boot fetch still lets the live stream take over.
  }
  render();
  loadModelList();

  // Replay the whole journal: a reload rebuilds past and in-progress turns (AD-1). Once it
  // reaches the snapshot's tip, the page says so (`data-journal-replayed`, read by the E2E run).
  const replayed = () => (document.body.dataset.journalReplayed = "true");
  if (store.liveFrom === 0) replayed();
  streamEvents(0, (envelope) => {
    applyEnvelope(envelope);
    if (envelope.seq >= store.liveFrom) replayed();
  });
}

boot();
