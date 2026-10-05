// AD-1: the single client-side store. It consumes every SSE event, visible
// panes or not, and only ever formats/derives (never recomputes business
// data such as tokens or availability).

// Languages (2/5): every text of the page comes from `content/ui.yaml` through `t()`, in the
// session's language; the formats of numbers, amounts and dates follow it.
import { dateTimeFormat, joinList, numberFormat as intlNumber, ready as textsReady, section, t } from "./i18n.js";
// Story 2 (2026-09-30): « Affichage ▾ » and the language picker, shared by the five pages.
import { languageChanging, renderLanguagePicker as drawLanguagePicker, setDisplayMenu, useSessionState } from "./site-nav.js";
// Recette du 02/10: the final answer's Markdown, rendered in the Vue humain only.
import { renderMarkdown } from "./markdown.js";
// Lot 2 (2026-10-04): the shared diagram's primitives (blocks, halo, wires, layer).
import { block as diagramBlock, light, marker, svgEl, wire, wireLayer } from "./diagram.js";
// Lot 4 (2026-10-04, AD-28): the panes' mechanics and the projection mode, shared with /mcp.
import { createPanes, initProjection } from "./panes.js";

const PANES = ["bricks", "human", "ctx", "orch", "schema"];
const PANE_LABELS = section("main.pane_titles");

const store = {
  sessionState: null,
  // Languages (1/5): `{language, languages, language_locked}` from `/api/state`; the lock
  // follows `session_state` and is lifted by `conversation_cleared` or `harness_reset`.
  language: null,
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
  // Story 26: the last `context_window_state` (the window and its choices, as the session
  // computed them, AD-1); the panel's choice waiting for « Appliquer » and its last refusal
  // (UI state only).
  windowState: null,
  windowPick: null,
  windowError: null,
  // The journal's tip when `/api/state` answered: an older `model_load_ended`, replayed by
  // the stream after a reload, does not come back in the top bar.
  liveFrom: 0,
  architecture: { nodes: [], edges: [] },
  journal: [],
  // FR-4: the id of the source the user clicked (a schema node's `node.id`, `brick:{id}`,
  // `step:{key}`…), and the link keys it carried (story 34); `null` when nothing is selected.
  selection: null,
  selectionKeys: null,
  // Story 34, UI state only: the link keys of the element under the pointer or the keyboard
  // focus (`data-links`); every pane lights what shares one of them.
  linkHover: null,
  // Lot 4 (AD-28): the hidden panes, the focused one and the sizes the user dragged (story 8f:
  // `bricks` width and `schema` height in px, `human` / `ctx` / `orch` as flex-grow weights)
  // are panes.js's, read here through `panes`.
  get hiddenPanes() {
    return panes.hidden;
  },
  get focusedPane() {
    return panes.focused;
  },
  set focusedPane(paneId) {
    panes.focused = paneId;
  },
  // Gauge source: the most recent of `context_preview` / `context_rendered` (AD-9), and the
  // call it measures (the envelope's `call_id`, `null` for a preview; story 34).
  gauge: null, // { payload, preview, callId }
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
  connectionLost: false, // E003: the live stream failed several times in a row
  serverInstance: null, // A1: the journal instance this page follows
  composerError: null,
  // Story 9b: the turn comparison open in Contexte LLM, UI state only: { left, right } turn ids.
  compare: null,
  bricks: null, // last `bricks_changed` payload: cards and system prompt, as the session computed them
  // Story 14: the last `memory_changed` ({ entries, path, error_text }), as the session wrote it
  // (AD-1); the drawer's unsaved texts, by entry id (UI state only).
  memory: null,
  memoryDrafts: new Map(),
  // FinOps: the session's API spend, the last `consumption_updated` (or `/api/state`), as the
  // session computed it (AD-1); `null` before the first paid call.
  consumption: null,
  maxSessionUsd: null, // finition V1 (#27): `[finops] max_session_usd`, from `/api/state`
  downloadError: null, // story 15: the last refusal of « Télécharger » (UI state only)
  // Story 15: the last failure of the RAG's download or build (`harness_error`), or a stopped
  // download (finition V1, #20): `{ text, error }`, `error` false for a stop (neutral).
  ragNotice: null,
  rerankNotice: null, // story 16: the same, for the reranker's download or load
  openExplanations: new Set(), // `options:{brick.id}` keys whose option list is unfolded (UI state only)
  openBrickHelp: new Set(), // brick ids (and "force-section") whose help popover is open (UI state only)
  closedPayloads: new Set(), // seq of outbound payloads folded by the user (open by default)
  openApprovalPayloads: new Set(), // approval ids whose payload is unfolded in the Vue humain card
  // Story 19, UI state only: the context Contexte LLM shows, `null` for the main one, else
  // `{ turn, sub }` (a turn id and a sub-agent's `context_id`); back to the main one if absent.
  ctxView: null,
  // Story 13, UI state only: « Afficher le raisonnement » (remembered by the browser, shown by
  // default), and the reasoning blocks the user unfolded (`chat:` or `ctx:` + turn id).
  showReasoning: true,
  openReasoning: new Set(),
  // Story 32, UI state only: Contexte LLM's view (« Lecture groupée », « Texte exact »,
  // « Corps JSON »; remembered by the browser), the « déjà lu » blocks unfolded (by call), the
  // JSON nodes the user toggled (lot 1 of 2026-10-04: a tree opens on its root's keys, every
  // node under it folded) and the exact texts shown, by key.
  ctxMode: "grouped",
  openSeen: new Set(),
  jsonToggled: new Set(),
  openExact: new Set(),
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
    // The live step is not unfolded as the live one: sticky (always open) or quiet (lot 1 of
    // 2026-10-04: on a click only); a frozen view then keeps it as it was.
    currentApart: false,
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
const DISCIPLINE_IDS = ["prompt", "context", "harness"];
const DISCIPLINE_NAMES = section("main.disciplines");
const disciplines = () => DISCIPLINE_IDS.map((d) => [d, DISCIPLINE_NAMES[d]]);
// Neutral: no brick (message, template), an assistant turn, or a brick the table lacks; one
// label in the legend and in the tooltips.
const disciplineName = (d) => (DISCIPLINE_IDS.includes(d) ? DISCIPLINE_NAMES[d] : DISCIPLINE_NAMES.neutral);

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

// The formats of the session's language (`i18n.js`), read at each call: never before the
// texts are there.
const numberFormat = () => intlNumber({ maximumFractionDigits: 1 });
const fmt = (n) => numberFormat().format(n);
const seconds = (ms) => `${numberFormat().format(Math.max(ms, 0) / 1000)} s`;
// FinOps: amounts in dollars (or euros), 4 significant digits, in the language's pattern
// (« 0,02 $ », « $0.02 »); formatting only.
const moneyFormat = () => intlNumber({ maximumSignificantDigits: 4 });
const usd = (n) => t("common.format.usd", { amount: moneyFormat().format(n) });
const eur = (n) => t("common.format.eur", { amount: moneyFormat().format(n) });
// What the user (or the model) wrote, quoted as the language quotes: « … », “…”, „…“.
const quote = (text) => t("common.format.quote", { text });
// « Outil : 3 », « Tool: 3 »: a label and its value, with the language's colon.
const labelValue = (label, value) => t("common.format.label_value", { label, value });
// GreenOps: energy and emissions, 2 significant digits, French comma; a range « 0,035–0,23 Wh »
// when its bounds differ once formatted. Under the display's precision (a thousandth), a
// positive value is « < 0,001 » and a range from under it « ≤ 0,0016 »; 0 is a true 0 (its
// note says why). Formatting only (the figures are the session's).
const footprintFormat = () => intlNumber({ maximumSignificantDigits: 2 });
const FOOTPRINT_FLOOR = 0.001;
const tiny = (n) => n > 0 && n < FOOTPRINT_FLOOR;
function rangeText(low, high, unit) {
  if (tiny(high) || (tiny(low) && high === low)) return `< ${footprintFormat().format(FOOTPRINT_FLOOR)} ${unit}`;
  const b = footprintFormat().format(high);
  if (tiny(low)) return `≤ ${b} ${unit}`;
  const a = footprintFormat().format(low);
  return a === b ? `${a} ${unit}` : `${a}–${b} ${unit}`;
}

// ---------- SSE: manual parsing, because the server names each event after
// its `kind` and EventSource cannot listen for an unknown kind generically. ----------

// Story 2 of the deferred leftovers (E003): after this many attempts in a row without a
// single event, the top bar says the connection is lost; the first event received clears it.
const STREAM_FAILURES_SHOWN = 3;

async function streamEvents(fromSeq, onEnvelope, onConnection = () => {}) {
  let lastSeq = fromSeq;
  let failures = 0;
  for (;;) {
    let received = false;
    try {
      const response = await fetch("/api/stream", {
        headers: lastSeq ? { "Last-Event-ID": String(lastSeq) } : {},
      });
      if (!response.ok) throw new Error(`HTTP ${response.status}`);
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
          if ((event || data) && !received) {
            // The server always sends `server_instance` first: the connection is back.
            received = true;
            failures = 0;
            onConnection(true);
          }
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
    // The retry keeps its pace (1 s); after a few in a row, the top bar says why nothing moves.
    if (!received && ++failures >= STREAM_FAILURES_SHOWN) onConnection(false);
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

const resetStatusText = () => t("main.top_bar.reset_done");
const RESET_STATUS_MS = 6000;
let resetStatusTimer = null;

// The "last known" states (`session_state`, the architecture, the bricks…): `/api/state`
// already gave the latest of each, up to `store.liveFrom`. An older one, replayed by the
// stream after a reload, would take the page back in time (a composer enabled then
// disabled by past turns): only a later one applies.
const isLive = (envelope) => envelope.seq > store.liveFrom;

function applyEnvelope(envelope) {
  store.journal.push(envelope);
  // FinOps: every paid call counts, the « LLM nu » screen's and the diagnostic's included.
  if (envelope.kind === "consumption_updated" && isLive(envelope)) store.consumption = envelope.payload;
  // Story 29: the « LLM nu » screen's events (context `llm`, no turn) go to the event log
  // only; no pane of the workshop shows them. Story 6 (2026-09-30): so do the MCP
  // workshop's (context `mcp_lab`), its outbound requests included: never the brick's.
  if ((envelope.context_id === "llm" || envelope.context_id === "mcp_lab") && envelope.kind !== "session_state") {
    scheduleRender();
    return;
  }
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
      if (typeof p.language_locked === "boolean" && store.language) {
        store.language.language_locked = p.language_locked;
      }
      break;
    case "language_changed":
      // Another tab changed the language: this page reloads in it too. Only against a language
      // `/api/state` gave (without it, a replayed change would reload the page).
      if (isLive(envelope) && !languageChanging() && store.language && p.language !== store.language.language) {
        location.reload();
      }
      break;
    case "architecture_changed":
      if (isLive(envelope)) store.architecture = p;
      break;
    case "context_preview":
      if (isLive(envelope)) store.gauge = { payload: p, preview: true, callId: null };
      break;
    case "context_window_state":
      if (isLive(envelope)) store.windowState = p; // story 26: the « Fenêtre » panel
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
      for (const action of p.actions) store.armedLabels.set(action.armed_id, action.label_text);
      // AD-1: the chips are this list, never a local computation.
      if (isLive(envelope)) store.armed = p.actions;
      break;
    case "action_dropped":
      if (turn) turn.steps.push({ type: envelope.kind, payload: p, label: store.armedLabels.get(p.armed_id) });
      break;
    case "conversation_cleared":
      // Past turns leave the Vue humain, Contexte LLM and Orchestration; the event list keeps them.
      if (isLive(envelope) && store.language) store.language.language_locked = false;
      dropSelection(); // story 34: its keys named what is gone
      clearCtxFolds(); // story 32: the folds of calls that are gone
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
      if (isLive(envelope) && store.language) store.language.language_locked = false;
      dropSelection();
      clearCtxFolds();
      store.chatFrom = store.turns.length;
      store.resetSeq = envelope.seq;
      store.compare = null;
      store.logFrom = store.journal.length;
      eventLog.list?.remove();
      Object.assign(eventLog, { groups: [], processed: store.logFrom, rows: [], list: null });
      store.memoryDrafts.clear();
      if (!isLive(envelope)) break; // an earlier reset: no confirmation in the top bar
      store.topStatus = resetStatusText();
      // A4: a discreet confirmation, over the panes: it leaves on its own.
      clearTimeout(resetStatusTimer);
      resetStatusTimer = setTimeout(() => {
        if (store.topStatus !== resetStatusText()) return;
        store.topStatus = null;
        render();
      }, RESET_STATUS_MS);
      break;
    case "model_load_started":
      // Story 26: a reload with another window is named by its phase label.
      store.modelLoad = {
        model: p.model,
        startedAt: Date.parse(envelope.ts),
        phaseLabel: p.window ? p.phase_label : null,
      };
      store.topStatus = null;
      break;
    case "model_load_ended":
      store.modelLoad = null;
      // A load that fell back, or a choice not saved, says so in the top bar (live only).
      if (isLive(envelope)) store.topStatus = p.reason_text ?? null;
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
      if (isLive(envelope)) store.gauge = { payload: p, preview: false, callId: envelope.call_id };
      if (turn) {
        turn.context = p;
        turn.steps.push({ type: "call", id: envelope.call_id, context: p, startedAt: null, ended: null });
      }
      break;
    case "context_reconciled":
      // AD-4, chat mode: `usage` came back; its figures replace the estimate of that call.
      if (isLive(envelope)) store.gauge = { payload: p, preview: false, callId: envelope.call_id };
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
        brick: envelope.brick, // story 34: its link keys (AD-1)
        component: envelope.component,
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
      // Correction A (2026-10-05): a key saved at the diagnostic changes the picker's rows.
      if (p.effect === "api_key_set") {
        scheduleModelList();
        break;
      }
      // Finition V1 (#20): a download stopped by « Arrêter », said on its card, neutral.
      if (!turn && envelope.brick === "rag" && p.effect === "model_download_stopped") {
        const notice = { text: p.lines.join(" "), error: false };
        if (envelope.component === "rag.reranker") store.rerankNotice = notice;
        else store.ragNotice = notice;
        break;
      }
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
          phaseLabel: t("main.chat.awaiting_approval"),
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
    case "reasoning_cut": // lot C: the harness closed a reasoning at its budget
      if (turn) {
        turn.steps.push({ type: envelope.kind, payload: p });
        lastCall(turn).cut = p; // story 32: a note between the call's reasoning and its answer
      }
      break;
    case "tool_call_malformed":
    case "prefix_not_reused":
    case "reasoning_dropped": // native providers 3/5 (CAP-5): the provider threw a reasoning away
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
      if (turn) turn.notices.push(p.message_text);
      break;
    case "harness_error":
      // A cloud provider's refusal carries what to try (AD-16).
      if (turn) turn.errors.push([p.message_text, ...(p.hints_text ?? [])].join(" "));
      // Story 15: a failed download (or load) of the RAG's model, said on its card.
      else if (envelope.brick === "rag") {
        const text = [p.message_text, p.cause ? t("main.bricks.notice_cause", { cause: p.cause }) : null, p.effect_text].filter(Boolean).join(" ");
        const notice = { text, error: true };
        // Story 16: the reranker's, said under its switch.
        if (envelope.component === "rag.reranker") store.rerankNotice = notice;
        else store.ragNotice = notice;
      }
      break;
    case "turn_ended":
      if (turn) {
        turn.status = p.status;
        // FinOps: the turn's cost as the session summed it, when it cost something.
        turn.cost = p.cost_in_usd != null ? p : null;
        // GreenOps: its footprint likewise, when one of its calls had one.
        turn.footprint = p.energy_wh_min != null ? p : null;
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
  "outbound_response",
  "hook_decided",
  "effect_applied",
  "approval_requested",
  "approval_resolved",
  "tool_call_malformed",
  "prefix_not_reused",
  "reasoning_cut",
  "reasoning_dropped",
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
      model: turn.model, // story 34: « via le réseau » on its calls too
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
    Object.assign(turn, { phaseLabel: t("main.chat.subagent_phase", { label }), callStartedAt: Date.parse(envelope.ts), firstToken: false });
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
      sub.notices.push(p.message_text);
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
      Object.assign(turn, { phaseLabel: t("main.chat.awaiting_approval"), callStartedAt: Date.parse(envelope.ts), firstToken: false });
      break;
    }
    case "approval_resolved": {
      const hook = sub.steps.find((s) => s.approval?.approval_id === p.approval_id);
      if (hook) hook.resolved = p;
      turn.phaseLabel = null;
      break;
    }
    case "reasoning_cut":
      sub.steps.push({ type: envelope.kind, payload: p });
      lastCall(sub).cut = p; // story 32
      break;
    case "tool_call_malformed":
    case "prefix_not_reused":
    case "reasoning_dropped":
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
      sub.errors.push([p.message_text, ...(p.hints_text ?? [])].join(" "));
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

// Lot 4 (AD-28): panes.js lays them out, hides, focuses, resizes and remembers them
// (`wavestack.panes`); the page re-renders on each change. At least one stays visible.
const panes = createPanes({
  panes: PANES,
  labels: PANE_LABELS,
  storageKey: "wavestack.panes",
  layout: document.getElementById("layout"),
  left: "bricks",
  row: ["human", "ctx", "orch"],
  bottom: "schema",
  chips: document.getElementById("pane-chips"),
  // The Vue humain waits for the user's answer to an H5 validation; story 34: a hidden pane
  // holds an element linked to the selection (FR-4), said in words on its chip.
  chipState: (paneId) => {
    const awaiting = paneId === "human" && store.sessionState?.state === "awaiting_human";
    return {
      awaiting,
      linked: Boolean(document.querySelector(`.pane[data-pane="${paneId}"] .is-selection-linked`)),
      ...(awaiting ? { title: t("main.panes.awaiting") } : {}),
    };
  },
  onChange: () => render(),
});

function showPane(paneId) {
  panes.show(paneId);
}

function togglePane(paneId) {
  panes.toggle(paneId);
}

function savePaneLayout() {
  panes.save();
}

function cssEscape(value) {
  return window.CSS && CSS.escape ? CSS.escape(value) : value.replace(/[^a-zA-Z0-9_-]/g, "\\$&");
}

// ---------- story 34: the linked view (FR-4) ----------
// Every linkable element carries its link keys in `data-links`, each a field received (AD-1):
// a brick id, a component id (`node.id`, `segment.component`, the envelope's `component`) or
// `call:{call_id}`. Two elements are linked when they share a key. Hovering or focusing one
// lights, in every pane, those that share a key (`.is-linked`, the rest dimmed); a click
// selects it, and the same elements keep an ink outline (`.is-selection-linked`).

// Writes the keys, space-separated, without duplicates nor empty ones; none: not linkable.
function setLinks(node, keys) {
  const value = [...new Set((keys || []).filter(Boolean))].join(" ");
  if (!value) node.removeAttribute("data-links");
  else if (node.dataset.links !== value) node.dataset.links = value;
  return node;
}

const readLinks = (node) => (node?.dataset.links ? node.dataset.links.split(" ") : []);

// A schema component is linked by its own id (brick cards and segments carry it too).
const linkKeysOfComponent = (id) => [id];

// Toggles the selection: a second click on the same source clears it.
function select(id, keys = linkKeysOfComponent(id)) {
  if (store.selection === id) clearSelection();
  else setSelection(id, keys);
}

// Sets the selection without toggling (RAG excerpts, reranking, compression items).
function setSelection(id, keys = linkKeysOfComponent(id)) {
  store.selection = id;
  store.selectionKeys = [...keys];
  if (!id.startsWith("step:")) store.orch.selected = null; // no old step stays highlighted
  render();
}

// Without rendering: the envelope's own render follows.
function dropSelection() {
  Object.assign(store, { selection: null, selectionKeys: null });
  store.orch.selected = null;
}

function clearSelection() {
  store.selection = null;
  store.selectionKeys = null;
  store.orch.selected = null;
  render();
}

// The hover (pointer or keyboard focus): the closest `[data-links]`, else nothing lit.
const linkSource = (target) => (target instanceof Element ? target.closest("[data-links]") : null);

function setLinkHover(source) {
  const keys = source ? readLinks(source) : [];
  const next = keys.length ? keys : null;
  if ((next || []).join(" ") === (store.linkHover || []).join(" ")) return;
  store.linkHover = next;
  applyLinks();
}

// A focus given back by a render (the node was rebuilt) is no user's gesture: its `focusin`
// must not take the hover from the pointer.
let quietFocusing = false;
function quietFocus(node) {
  if (!node) return;
  quietFocusing = true;
  try {
    node.focus();
  } finally {
    quietFocusing = false;
  }
}

// Lights what shares a key with the hover and outlines what shares one with the selection,
// in every pane (hidden ones included); runs after each render, which rebuilds some nodes.
function applyLinks() {
  // The hovered or focused node went away (a render, a reset) without the pointer moving:
  // nothing is under it any more, the page must not stay dimmed.
  if (store.linkHover && !document.querySelector("[data-links]:hover, [data-links]:focus-within")) {
    store.linkHover = null;
  }
  const chosen = new Set(store.selectionKeys || []);
  // Hovering the source of the selection (the pointer stays where it clicked): no dimming,
  // the ink outline of the selection reads alone.
  const onSelection =
    store.linkHover !== null && store.selectionKeys !== null && store.linkHover.join(" ") === store.selectionKeys.join(" ");
  const hover = new Set(onSelection ? [] : store.linkHover || []);
  document.body.classList.toggle("linking", hover.size > 0);
  for (const node of document.querySelectorAll("[data-links]")) {
    const keys = readLinks(node);
    node.classList.toggle("is-linked", hover.size > 0 && keys.some((k) => hover.has(k)));
    node.classList.toggle("is-selection-linked", chosen.size > 0 && keys.some((k) => chosen.has(k)));
  }
  // A focusable source that is no button says whether it is the selection.
  for (const node of document.querySelectorAll("[data-select-id]")) {
    node.setAttribute("aria-pressed", String(store.selection === node.dataset.selectId));
  }
  renderChips(); // a hidden pane holding a linked element says so on its chip
}

function bindLinkedView() {
  document.addEventListener("pointerover", (event) => setLinkHover(linkSource(event.target)));
  document.addEventListener("pointerout", (event) => {
    if (!event.relatedTarget) setLinkHover(null); // the pointer left the page
  });
  // A tap is no hover: it ends with the finger lifted.
  document.addEventListener("pointerup", (event) => {
    if (event.pointerType !== "mouse") setLinkHover(null);
  });
  document.addEventListener("focusin", (event) => {
    if (!quietFocusing) setLinkHover(linkSource(event.target));
  });
  document.addEventListener("focusout", (event) => {
    if (!quietFocusing && !linkSource(event.relatedTarget)) setLinkHover(null);
  });
}

// A segment (context, gauge): a button for assistive technologies, named short; selected on
// the mouse's press (these nodes are rebuilt while a turn streams: a click, press and release
// on two different nodes, would never fire), by a tap, or by Enter or Space.
function selectOnActivate(node, id, name) {
  node.tabIndex = 0;
  node.setAttribute("role", "button");
  node.setAttribute("aria-label", name);
  node.dataset.selectId = id;
  node.setAttribute("aria-pressed", String(store.selection === id));
  // Its own controls (a fold), the node itself excepted when it is a button (story 32: a
  // section's margin), whose keys are those of the row that holds it.
  const own = (event) => {
    const control = event.target.closest("summary, button, a");
    return Boolean(control) && control !== node;
  };
  const keys = () => readLinks(node.closest("[data-links]"));
  node.addEventListener("pointerdown", (event) => {
    if (event.pointerType !== "mouse" || event.button !== 0 || own(event)) return;
    select(id, keys());
  });
  node.addEventListener("click", (event) => {
    if (event.pointerType === "mouse" || own(event)) return;
    select(id, keys());
  });
  node.addEventListener("keydown", (event) => {
    // A native button clicks on Enter and Space by itself: the `click` above selects it.
    if (node.tagName === "BUTTON" || event.target !== node || (event.key !== "Enter" && event.key !== " ")) return;
    event.preventDefault(); // Space would scroll the pane
    select(id, keys());
  });
}

// Story 34: Escape clears a selection still shown somewhere (an element, or a chip saying
// « lié »); an invisible one is dropped silently and Escape does its next job.
function selectionShown() {
  return [...document.querySelectorAll(".is-selection-linked")].some(
    (node) => node.getClientRects().length > 0 || node.closest(".pane.is-hidden")
  );
}

// ---------- rendering ----------

function render() {
  renderLanguagePicker();
  renderBricks();
  updateBrickStatuses();
  renderChips();
  renderMenu();
  renderPaneVisibility();
  renderGauge();
  renderConsumption();
  renderWindowPicker();
  renderModelIndicator();
  renderChat();
  renderComposer();
  renderContext();
  renderSteps();
  renderJournal();
  renderSchema();
  renderOutboundSummary();
  updateBrickLinks();
  applyLinks();
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

const noTurnText = () => t("main.chat.no_turn");
const clearedText = () => t("main.chat.cleared");

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
    pane.appendChild(emptyNote(t("main.bricks.waiting_harness")));
    return;
  }
  // Story 33: the four disciplines first, then the cards in their two groups.
  pane.appendChild(
    disciplineLegend("discipline-legend brick-legend", [...disciplines(), ["network", DISCIPLINE_NAMES.network]])
  );
  // Story 34: how to read the panes together.
  pane.appendChild(el("p", "brick-link-hint", t("main.bricks.link_hint")));
  const reopenPopovers = []; // help popovers that were open before this rebuild
  pane.appendChild(forcedToggle(reopenPopovers));
  if (store.armError) {
    const error = el("p", "force-error", store.armError);
    error.setAttribute("role", "alert");
    pane.appendChild(error);
  }
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
    // Story 34: its keys (`updateBrickLinks`); a click out of its controls selects it (the
    // name is in the switch's label: a click on it still toggles the brick).
    setLinks(card, brickLinkKeys(brick));
    card.addEventListener("click", (event) => {
      if (event.target.closest(BRICK_CONTROLS)) return;
      select(`brick:${brick.id}`, readLinks(card));
    });
    // From the keyboard: the card itself takes the focus, Enter or Space selects it.
    card.tabIndex = 0;
    card.dataset.focusKey = `brickcard:${brick.id}`;
    card.setAttribute("aria-label", t("main.bricks.card_name", { brick: brick.label_text }));
    card.addEventListener("keydown", (event) => {
      if (event.target !== card || (event.key !== "Enter" && event.key !== " ")) return;
      event.preventDefault();
      select(`brick:${brick.id}`, readLinks(card));
    });
    // Story 13: a model that always reasons keeps the reasoning brick on, whatever `wanted`.
    const always = Boolean(brick.always_text);
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
      lock.title = t("main.bricks.locked_by_model");
      lock.setAttribute("aria-hidden", "true");
      head.appendChild(lock);
    }
    head.appendChild(el("span", "brick-name", brick.label_text));

    const tags = el("div", "brick-tags");
    tags.appendChild(el("span", "category-chip", brick.category_text));
    if (brick.hosting_text) tags.appendChild(el("span", "hosting-tag-local", brick.hosting_text));
    // Story 33: an enabled option leaves the workstation: « 🌐 RÉSEAU » on the card itself.
    if (!parentOff && (brick.options || []).some((o) => o.enabled && o.network)) {
      tags.appendChild(el("span", "hosting-tag-network brick-network", t("main.hosting.network")));
    }
    // Story 33: what the brick weighs or does now, refreshed in place (`updateBrickStatuses`).
    const status = el("p", "brick-status", brickStatus(brick));
    status.dataset.brick = brick.id;
    card.append(head, tags, status);

    if (!brick.available && brick.reason_text) card.appendChild(el("p", "brick-reason", brick.reason_text));
    if (brick.id === "rag") card.append(...downloadParts(brick), ...rerankParts(brick, offReason));
    if (always) {
      const why = el("p", "brick-reason brick-always", brick.always_text);
      why.id = `always-${brick.id}`;
      toggle.setAttribute("aria-describedby", why.id);
      card.appendChild(why);
    }
    if (brick.note_text) card.appendChild(el("p", "brick-note", brick.note_text));
    // AD-9 (E089): a public MCP server whose live tools drift from its snapshot, outside the
    // folded options so that it is seen.
    for (const option of brick.id === "mcp" ? brick.options || [] : []) {
      if (!option.drift_text) continue;
      const warning = el("p", "brick-drift", option.drift_text);
      warning.setAttribute("role", "note");
      warning.dataset.server = option.id;
      card.appendChild(warning);
    }
    // Story 23: what leaves the workstation and where to read it, outside the folded options.
    if (brick.outbound_text) card.appendChild(el("p", "brick-outbound", brick.outbound_text));
    // Story 6 (2026-09-30): the MCP card leads to the MCP workshop, the protocol laid bare.
    if (brick.id === "mcp") {
      const workshop = el("a", "brick-workshop-link", t("main.bricks.mcp_workshop"));
      workshop.href = "/mcp";
      workshop.title = t("common.links.mcp_title");
      card.appendChild(workshop);
    }
    if (brick.pending) card.appendChild(el("p", "brick-pending", t("main.bricks.pending")));
    // Story 9: its armed actions, always visible (the Forcer buttons may be hidden).
    const armed = store.armed.filter((a) => a.brick === brick.id);
    if (armed.length) card.appendChild(armedChips(armed, `card:${brick.id}`));

    if (brick.options?.length) card.appendChild(brickOptions(brick, offReason));
    if (brick.limits_text) card.appendChild(el("p", "brick-limits", brick.limits_text));
    // Story 19: a brick without sub-option forces its action from the card itself.
    if (brick.force && store.showForced) card.append(...cardForce(brick));

    if (brick.explanation_text?.length) {
      // ponytail: CSS anchor positioning (Chromium) has no fallback for other engines;
      // acceptable here since the demo targets a Chromium-based browser on the PC.
      const anchorName = `--brick-anchor-${brick.id}`;
      card.style.setProperty("anchor-name", anchorName);
      const help = el("button", "brick-help", "?");
      help.type = "button";
      help.setAttribute("popovertarget", `explain-${brick.id}`);
      help.setAttribute("aria-label", t("main.bricks.help_label", { brick: brick.label_text }));
      const popover = el("div", "brick-explanation");
      popover.id = `explain-${brick.id}`;
      popover.setAttribute("popover", "");
      popover.style.setProperty("position-anchor", anchorName);
      popover.addEventListener("toggle", (event) => {
        if (event.newState === "open") store.openBrickHelp.add(brick.id);
        else store.openBrickHelp.delete(brick.id);
      });
      for (const block of brick.explanation_text) {
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
      const edit = el("button", "brick-edit", t("main.bricks.edit_prompt"));
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
    quietFocus(target);
  }
}

const BRICK_GROUPS = section("main.bricks.groups");
// What a click on a card leaves to its controls (switch and its label, options, forms, help).
const BRICK_CONTROLS = "input, button, a, select, textarea, label, summary, details, [popover], .force-form";

// Story 34: a card's link keys: its id and the ids of its nodes (`{id}.*`) in the schema.
function brickLinkKeys(brick) {
  const nodes = (store.architecture.nodes || []).filter((n) => n.id.startsWith(`${brick.id}.`));
  return [brick.id, ...nodes.map((n) => n.id)];
}

// The schema changes without the cards being rebuilt: their keys follow it in place.
function updateBrickLinks() {
  for (const brick of store.bricks?.bricks || []) {
    const card = document.querySelector(`#bricks article.brick-card[data-brick="${cssEscape(brick.id)}"]`);
    if (card) setLinks(card, brickLinkKeys(brick));
  }
}

// Story 33: the card's status line, from received values only (AD-1): the gauge's `by_brick`,
// `reserve` and `uncompressed_used`, the memory's entries, the schema's network nodes.
// Counting a received list and the gap between two received values stay formatting.
function brickStatus(brick) {
  const always = Boolean(brick.always_text);
  if (always) return t("main.bricks.status.imposed");
  if (!brick.available) return t("main.bricks.status.unavailable"); // wanted or not: it cannot be switched on
  if (!brick.wanted) return t("main.bricks.status.switched_off");
  const p = store.gauge?.payload;
  if (!p) return t("main.bricks.status.waiting_model");
  if (brick.id === "reasoning") return t("main.bricks.status.reserve", { tokens: t("common.count.token", { count: p.reserve }) });
  const row = (p.by_brick || []).find((b) => b.brick === brick.id);
  // Only « n tokens dans le contexte » says « ≈ » (EXPERIENCE.md > brick-card); the others count.
  const count = t("common.count.token", { count: row?.tokens ?? 0 });
  if (brick.id === "global_memory") return `${t("common.count.entry", { count: store.memory?.entries?.length ?? 0 })} · ${count}`;
  if (brick.id === "tools" || brick.id === "mcp") {
    const on = (brick.options || []).filter((o) => o.enabled);
    const declared = t("main.bricks.status.declared", { count: on.length });
    if (!on.some((o) => o.network)) return `${declared} · ${count}`;
    const contacted = (store.architecture.nodes || []).filter(
      (n) =>
        n.id.startsWith(`${brick.id}.`) && n.hosting === "network" && n.contact && n.contact !== "not_contacted"
    ).length;
    return `${declared} · ${t("main.bricks.status.contacted", { count: contacted })}`;
  }
  if (brick.id === "compression") {
    const gain = p.uncompressed_used == null ? 0 : p.uncompressed_used - p.used;
    return gain > 0 ? t("main.bricks.status.gain", { tokens: t("common.count.token", { count: gain }) }) : t("main.bricks.status.no_gain");
  }
  return t("main.bricks.status.in_context", { tokens: `${approx(Boolean(row?.estimated))}${count}` });
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
  if (!brick.available) return brick.reason_text || t("main.bricks.parent_unavailable", { brick: brick.label_text });
  return t("main.bricks.parent_off", { brick: brick.label_text });
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
  return `${store.sessionState?.state ?? ""}|${store.sessionState?.reason_text ?? ""}|${store.ragNotice?.text ?? ""}|${store.rerankNotice?.text ?? ""}`;
}

// A notice of the RAG's card: red for a failure, neutral for a download stopped (#20).
const noticeLine = (notice) => el("p", notice.error ? "force-error" : "brick-note", notice.text);

// Story 15 (AD-21): « Télécharger » while the model is missing, the progress and « Arrêter »
// while it downloads; the figures come from the session (`session_state.reason_text`).
function downloadParts(brick) {
  // Story 15 (AD-21): « Télécharger » while the model is missing, « Construire l'index » once
  // it is there; the progress and « Arrêter » while either runs. Figures from the session.
  const state = store.sessionState?.state;
  const jobs = { download: t("main.bricks.stop_download"), index_build: t("main.bricks.stop_build") };
  if (jobs[state]) {
    const progress = el("p", "brick-download-progress", store.sessionState.reason_text || t("common.in_progress"));
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
    offer = { label: brick.download.label_text, key: "download", run: () => ragAction("/api/intentions/download_model", body) };
  } else if (brick.build_index) {
    offer = { label: brick.build_index.label_text, key: "build", run: () => ragAction("/api/intentions/build_rag_index", {}) };
  }
  // The last failure stays said while the card still offers an action (AD-1: from the event).
  const notice = store.ragNotice && !brick.available && offer ? [noticeLine(store.ragNotice)] : [];
  if (!offer) return notice;
  const button = el("button", `brick-edit brick-${offer.key}`, offer.label);
  button.type = "button";
  button.dataset.focusKey = `${offer.key}:${brick.id}`;
  const idle = state === "idle";
  button.disabled = !idle;
  const parts = [...notice, button];
  if (!idle) {
    const why = el("p", "brick-download-why", store.sessionState?.reason_text || t("common.busy"));
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
  row.append(toggle, el("span", "brick-option-name", option.label_text), el("span", "hosting-tag-local", option.hosting_text));
  box.appendChild(row);
  if (!option.available && option.reason_text) {
    const why = el("p", "brick-reason", option.reason_text);
    why.id = "rerank-why";
    toggle.setAttribute("aria-describedby", why.id);
    box.appendChild(why);
  }
  // The last failure of its download or load (`harness_error`), while still unavailable.
  if (store.rerankNotice && !option.available) box.appendChild(noticeLine(store.rerankNotice));
  if (option.download) {
    const state = store.sessionState?.state;
    const button = el("button", "brick-edit brick-download-rerank", option.download.label_text);
    button.type = "button";
    button.dataset.focusKey = "download:rag:rerank";
    button.disabled = state !== "idle";
    if (button.disabled) button.title = store.sessionState?.reason_text || t("common.busy");
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
      store.downloadError = typeof answer.detail === "string" ? answer.detail : t("common.action_refused");
    }
  } catch {
    store.downloadError = t("main.bricks.no_answer_nothing_started");
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
  const noun = section("main.bricks.option_nouns")[brick.id] || t("main.bricks.option_nouns.tools");
  // The closed card still shows the MCP documentation mode; the brick off, that it is off
  // (story 22: a lazy loading shown while MCP is off seemed to act).
  const mode = offReason ? ` · ${t("main.bricks.brick_off")}` : brick.mode === "lazy" ? ` · ${brick.lazy_label_text}` : "";
  details.classList.toggle("is-parent-off", Boolean(offReason));
  details.appendChild(
    el("summary", "", t("main.bricks.options_summary", { noun, count: on, total: brick.options.length, mode }))
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
      el("span", "brick-option-name", option.label_text),
      el("span", option.network ? "hosting-tag-network" : "hosting-tag-local", option.hosting_text)
    );
    const li = el("li", "brick-option-item");
    li.appendChild(row);
    const force = store.showForced ? forceButton(brick, option) : null;
    if (force) {
      li.appendChild(force);
      const open = store.forceForm?.brick === brick.id && store.forceForm?.id === option.id;
      if (open) li.appendChild(forceForm(brick, option));
    }
    // Lot K: « Forcer l'appel » of each tool of a connected MCP server, both modes.
    for (const call of store.showForced && brick.id === "mcp" ? option.calls || [] : []) {
      const callOption = mcpCallOption(call);
      li.appendChild(forceButton(brick, callOption));
      if (isFormOpen(brick.id, callOption.id)) li.appendChild(forceForm(brick, callOption));
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
    row.append(toggle, el("span", "brick-option-name", brick.lazy_label_text));
    details.appendChild(row);
  }
  return details;
}

// ---------- forced actions (story 9, FR-42): toggle, Forcer, form with presets, chips ----------

const FORCED_STORAGE_KEY = "wavestack.forcedActions";
// EXPERIENCE: force-button labels, by brick; a native tool has none there: « Forcer l'appel ».
const FORCE_LABELS = section("main.force.labels");
// Story 14: the memory write is forced from the card itself, a form with one field whose
// help comes with the card (AD-19).
function memoryForceOption(brick) {
  return {
    id: "remember",
    label_text: t("main.memory.title"),
    parameters: { text: brick.text_help_text || "" },
    fieldLabels: { text: t("main.force.text_field") },
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

// D3 of 2026-10-01: a titled section with the ✋, told apart from the bricks' switches. Lot 1 of
// 2026-10-04: a « ? » by its title, the bricks' help (`.brick-help` and its popover, anchored
// to the button), open again after a rebuild (`reopen`, the pane's list).
const FORCE_HELP = "force-section"; // its key in `store.openBrickHelp` (no brick has this id)
function forcedToggle(reopen) {
  const box = el("section", "force-section");
  // Its own class: the E2E reads the two groups' titles by `.brick-group-title`.
  const title = el("h3", "force-section-title", t("main.force.section_title"));
  title.id = "force-section-title";
  box.setAttribute("aria-labelledby", title.id);
  const head = el("div", "force-section-head");
  const help = el("button", "brick-help brick-help-inline", "?");
  help.type = "button";
  help.id = "force-help";
  help.dataset.focusKey = "force-help";
  help.setAttribute("popovertarget", "explain-force-section");
  help.setAttribute("aria-label", t("main.force.help_label"));
  help.style.setProperty("anchor-name", "--force-help-anchor");
  const popover = el("div", "brick-explanation force-explanation");
  popover.id = "explain-force-section";
  popover.setAttribute("popover", "");
  popover.style.setProperty("position-anchor", "--force-help-anchor");
  popover.appendChild(el("p", "", t("main.force.help_text")));
  popover.addEventListener("toggle", (event) => {
    if (event.newState === "open") store.openBrickHelp.add(FORCE_HELP);
    else store.openBrickHelp.delete(FORCE_HELP);
  });
  if (store.openBrickHelp.has(FORCE_HELP)) reopen.push(popover);
  head.append(title, help, popover);
  const row = el("label", "force-toggle");
  const toggle = el("input", "brick-toggle");
  toggle.type = "checkbox";
  toggle.setAttribute("role", "switch");
  toggle.checked = store.showForced;
  toggle.dataset.focusKey = "force-toggle";
  toggle.addEventListener("change", () => {
    store.showForced = toggle.checked;
    if (store.showForced) {
      // The Forcer buttons are in the bricks' folded option lists: unfold those lists.
      for (const brick of store.bricks?.bricks || []) {
        if (hasOptionForce(brick)) store.openExplanations.add(`options:${brick.id}`);
      }
    } else {
      store.forceForm = null;
      store.armError = null;
    }
    saveShowForced();
    renderedBricks = null; // the Forcer buttons appear or leave
    scheduleRender();
  });
  const hand = el("span", "force-toggle-icon", "✋");
  hand.setAttribute("aria-hidden", "true"); // the label alone is read aloud
  row.append(toggle, hand, el("span", "", t("main.force.show")));
  box.append(head, row);
  return box;
}

// D3: whether the brick's option list holds a Forcer button (`forceButton`'s rule, an MCP
// tool's forced call included).
function hasOptionForce(brick) {
  return (brick.options || []).some(
    (option) => optionForceLabel(brick, option) !== null || (brick.id === "mcp" && (option.calls || []).length > 0)
  );
}

function handIcon() {
  const icon = el("span", "", "👆 ");
  icon.setAttribute("aria-hidden", "true"); // the label alone is read aloud
  return icon;
}

function isFormOpen(brickId, optionId) {
  return store.forceForm?.brick === brickId && store.forceForm?.id === optionId;
}

// Lot K: the forced call of one MCP tool, as an option of its server's row (`call`: from
// `bricks_changed`, its parameters described by the server and its presets).
function mcpCallOption(call) {
  return {
    id: `call:${call.tool}`,
    label_text: call.tool,
    target: call.tool,
    call: true,
    parameters: call.parameters,
    presets: call.presets,
  };
}

// The label of the option's Forcer button, `null` when it has none. Tools, skills, and in lazy
// loading only, the documentation of an MCP server's tool; lot K: the call of an MCP tool
// (`option.call`), in both modes.
function optionForceLabel(brick, option) {
  const label = option.call ? FORCE_LABELS.tools : FORCE_LABELS[brick.id];
  if (!label) return null;
  if (brick.id === "mcp" && !option.call && (brick.mode !== "lazy" || !option.tools?.length)) return null;
  return label;
}

function forceButton(brick, option) {
  const label = optionForceLabel(brick, option);
  if (!label) return null;
  const button = el("button", "force-button");
  button.type = "button";
  button.append(handIcon(), option.call ? `${label} · ${option.label_text}` : label);
  button.setAttribute("aria-label", labelValue(label, option.label_text));
  button.dataset.focusKey = `force:${brick.id}:${option.id}`;
  // A tool without parameter and a skill are armed at once; the others open their form.
  const hasParameters = Object.keys(option.parameters || {}).length > 0;
  const needsForm =
    (brick.id === "mcp" && (!option.call || hasParameters)) ||
    brick.id === "global_memory" ||
    (brick.id === "tools" && hasParameters);
  if (needsForm) button.setAttribute("aria-expanded", String(isFormOpen(brick.id, option.id)));
  button.addEventListener("click", () => {
    if (!needsForm) {
      armAction(brick.id === "skills" ? "skill" : "tool", option.target ?? option.id, {});
      return;
    }
    store.forceForm = isFormOpen(brick.id, option.id) ? null : newForceForm(brick, option);
    button.setAttribute("aria-expanded", String(Boolean(store.forceForm))); // lot K (A8)
    forceUiChanged();
  });
  return button;
}

// Story 19: the card's Forcer button and, once open, its form; `brick.force` gives the
// action's target, its parameters and presets (AD-1: from `bricks_changed`).
function cardForce(brick) {
  const force = brick.force;
  const option = { id: force.target, label_text: brick.label_text, parameters: force.parameters, presets: force.presets };
  const label = FORCE_LABELS[brick.id] || force.label_text;
  const button = el("button", "force-button force-button-card");
  button.type = "button";
  button.append(handIcon(), label);
  button.dataset.focusKey = `force:${brick.id}:${option.id}`;
  const open = isFormOpen(brick.id, option.id);
  button.setAttribute("aria-expanded", String(open));
  button.addEventListener("click", () => {
    store.forceForm = isFormOpen(brick.id, option.id) ? null : newForceForm(brick, option);
    // Lot K (A8): the button says the form's state at once, the rebuild keeps it.
    button.setAttribute("aria-expanded", String(Boolean(store.forceForm)));
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
  if (brick.id === "mcp" && !option.call) {
    return { brick: brick.id, id: option.id, values: { tool: option.tools[0] }, error: null };
  }
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
    option.call
      ? armAction("tool", option.target, { ...form.values }, form)
      : brick.id === "mcp"
      ? armAction("tool_doc", form.values.tool, {}, form)
      : brick.id === "global_memory"
        ? armAction("memory", option.id, { text: form.values.text ?? "" }, form)
      : brick.force
        ? armAction(brick.force.kind, brick.force.target, { ...form.values }, form)
        : armAction("tool", option.id, { ...form.values }, form);
  if (brick.id === "mcp" && !option.call) {
    box.setAttribute("aria-label", t("main.force.doc_form_label", { server: option.label_text }));
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
    box.appendChild(forceField(t("main.force.tool_field"), select));
  } else {
    box.setAttribute(
      "aria-label",
      brick.force ? t("main.force.task_form_label", { action: brick.force.label_text }) : t("main.force.args_form_label", { option: option.label_text })
    );
    if (option.presets?.length) {
      const select = el("select");
      select.dataset.focusKey = `${base}:preset`;
      option.presets.forEach((preset, i) => {
        const choice = el("option", "", preset.label_text);
        choice.value = String(i);
        select.appendChild(choice);
      });
      const free = el("option", "", t("main.force.free_input"));
      free.value = "-1";
      select.appendChild(free);
      select.value = String(form.preset);
      select.addEventListener("change", () => {
        const preset = Number(select.value);
        const values = preset >= 0 ? presetValues(option, preset) : form.values;
        store.forceForm = { ...form, preset, values, error: null };
        forceUiChanged();
      });
      box.appendChild(forceField(t("main.force.preset_field"), select));
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
  const armButton = el("button", "force-arm", t("main.force.arm"));
  armButton.type = "button";
  armButton.dataset.focusKey = `${base}:arm`;
  armButton.addEventListener("click", arm);
  const cancel = el("button", "force-cancel", t("common.cancel"));
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
      error = typeof body.detail === "string" ? body.detail : t("main.force.arm_refused");
    }
  } catch {
    error = t("main.force.arm_no_answer");
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
    chip.append(handIcon(), t("main.force.armed_chip", { action: action.label_text }), close);
    chip.setAttribute("aria-label", t("main.force.disarm", { action: action.label_text }));
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
  badge.append(icon, user ? t("main.trigger.user") : t("main.trigger.model"));
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
    drawerAlert(t("main.drawer.unsaved"), true);
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
    drawerStatus(text === null ? t("main.drawer.default_restored") : t("main.drawer.saved"));
    syncDrawerSave();
    return true;
  } catch {
    drawerStatus(null);
    drawerAlert(t("main.drawer.save_no_answer"));
    return false;
  }
}

// ---------- global memory: card and edit drawer (story 14, FR-12, AD-23) ----------

const MEMORY_SOURCES = section("main.memory.sources");
const memoryDrawer = () => document.getElementById("memory-drawer");

function memoryCardParts(brick) {
  // The count the last `memory_changed` gives, the forced write, then the drawer's button.
  const parts = [];
  const memory = store.memory;
  if (memory && !memory.error_text) {
    const n = memory.entries.length;
    parts.push(el("p", "brick-limits", n ? t("main.memory.card_count", { entries: t("common.count.entry", { count: n }) }) : t("main.memory.card_empty")));
  }
  if (store.showForced) {
    const option = memoryForceOption(brick);
    const force = forceButton(brick, option);
    if (brick.note_text) {
      // H4: no tool parser, the forced write would be dropped: said on the button itself.
      force.disabled = true;
      force.title = brick.note_text;
      force.setAttribute("aria-description", brick.note_text);
    }
    parts.push(force);
    if (!brick.note_text && isFormOpen(brick.id, option.id)) parts.push(forceForm(brick, option));
  }
  const edit = el("button", "brick-edit", t("main.memory.edit"));
  edit.type = "button";
  edit.disabled = !memory || Boolean(memory.error_text);
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
  memoryAlert(t("main.memory.clear_question", { count: n }), "clear");
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
  if (!store.memory || store.memory.error_text) return;
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
    memoryAlert(t("main.drawer.unsaved"), "dirty");
    return;
  }
  store.memoryDrafts.clear();
  memoryAlert(null);
  memoryDrawer().hidden = true;
  document.getElementById("bricks").inert = false;
  document.getElementById("edit-memory")?.focus();
}

// D7: `created_at` (ISO 8601 with its offset, `memory.py`) as a `<time>`, its date and hour
// short in the session's language; `null` for a missing or unreadable date.
function memoryDate(createdAt) {
  const date = createdAt ? new Date(createdAt) : null;
  if (!date || Number.isNaN(date.getTime())) return null;
  const node = el("time", "memory-entry-date", dateTimeFormat({ dateStyle: "short", timeStyle: "short" }).format(date));
  node.dateTime = createdAt;
  node.title = t("main.memory.written_at");
  return node;
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
  document.getElementById("memory-path").textContent = memory ? t("main.memory.file", { path: memory.path }) : "";
  const empty = document.getElementById("memory-empty");
  empty.textContent = memoryCard()?.empty_text ?? "";
  empty.hidden = entries.length > 0;
  document.getElementById("memory-clear").disabled =
    entries.length === 0 || !document.getElementById("memory-confirm").hidden;
  list.innerHTML = "";
  entries.forEach((entry, i) => {
    const item = el("li", "memory-entry");
    const label = t("main.memory.entry", { n: String(i + 1) });
    const head = el("div", "memory-entry-head");
    const source = el("span", "memory-entry-source", MEMORY_SOURCES[entry.source] ?? entry.source);
    // D7 of 2026-10-01: when it was written, short, in the workstation's time zone.
    const written = memoryDate(entry.created_at);
    if (written) source.append(" · ", written);
    head.append(el("span", "memory-entry-name", label), source);
    const text = el("textarea", "memory-entry-text");
    text.rows = 3;
    if (memory?.max_chars) text.maxLength = memory.max_chars;
    text.spellcheck = false;
    text.value = store.memoryDrafts.get(entry.id) ?? entry.text;
    text.setAttribute("aria-label", t("main.memory.entry_text", { n: String(i + 1) }));
    text.dataset.focusKey = `memory:${entry.id}:text`;
    const save = el("button", "memory-entry-save", t("common.save"));
    save.type = "button";
    save.disabled = text.value === entry.text;
    save.setAttribute("aria-label", t("main.memory.entry_save", { n: String(i + 1) }));
    save.dataset.focusKey = `memory:${entry.id}:save`;
    text.addEventListener("input", () => {
      store.memoryDrafts.set(entry.id, text.value); // kept in place: typing never rebuilds
      save.disabled = text.value === entry.text;
    });
    save.addEventListener("click", () => saveMemoryEntries([entry.id]));
    const remove = el("button", "memory-entry-delete", t("main.memory.delete"));
    remove.type = "button";
    remove.setAttribute("aria-label", t("main.memory.entry_delete", { n: String(i + 1) }));
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
      memoryAlert(typeof answer.detail === "string" ? answer.detail : t("main.memory.edit_refused"));
      return false;
    }
  } catch {
    memoryAlert(t("main.memory.edit_no_answer"));
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
      store.composerError = typeof body.detail === "string" ? body.detail : t("common.action_refused");
    }
  } catch {
    store.composerError = t("main.chat.clear_no_answer");
  }
  render();
}

async function replayLast() {
  store.composerError = null;
  try {
    const response = await postIntention("/api/intentions/replay", {});
    if (!response.ok) {
      const body = await response.json().catch(() => ({}));
      store.composerError = typeof body.detail === "string" ? body.detail : t("main.chat.replay_refused");
    }
  } catch {
    store.composerError = t("main.chat.replay_no_answer");
  }
  render();
}

// ---------- context gauge (top bar) ----------

function renderGauge() {
  const bar = document.getElementById("gauge-bar");
  const figures = document.getElementById("gauge-figures");
  const threshold = document.getElementById("gauge-threshold");
  const root = document.getElementById("gauge");
  // Story 34: a segment has the keyboard focus: given back to the rebuilt one.
  const focusedGroup = bar.contains(document.activeElement) ? document.activeElement.dataset.group : null;
  bar.querySelectorAll(".gauge-seg, .gauge-free").forEach((node) => node.remove());
  const gauge = store.gauge;
  root.classList.toggle("is-overflow", Boolean(gauge?.payload.overflow));
  root.classList.toggle("is-near-limit", Boolean(gauge?.payload.near_limit));
  if (!gauge) {
    threshold.hidden = true;
    renderGaugeLegend([]);
    figures.textContent = t("main.gauge.waiting");
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
    seg.dataset.group = item.group;
    seg.title = t("main.gauge.segment", { label: item.label_text, tokens: item.tokens, discipline: disciplineName(seg.dataset.discipline) });
    seg.setAttribute("aria-label", seg.title);
    // Story 34: the bricks and components of its segments (by `kinds`), and the call measured.
    const segments = (p.segments || []).filter((s) => item.kinds.includes(s.kind));
    setLinks(seg, [
      ...segments.flatMap((s) => [s.brick, s.component]),
      gauge.callId ? `call:${gauge.callId}` : null,
    ]);
    selectOnActivate(seg, `gauge:${item.group}`, seg.title);
    bar.appendChild(seg);
    if (item.group === focusedGroup) quietFocus(seg);
  }
  renderGaugeLegend(p.breakdown);
  const free = el("span", "gauge-free");
  free.style.flexGrow = String(Math.max(p.usable - p.used, 0));
  free.title = t("main.gauge.free", { tokens: Math.max(p.usable - p.used, 0) });
  bar.appendChild(free);
  threshold.hidden = p.overflow; // past 100 % the bar no longer maps to `usable`
  threshold.style.left = `${p.near_limit_ratio * 100}%`;
  threshold.title = t("main.gauge.threshold", { percent: p.near_limit_ratio * 100 });

  let text = t("main.gauge.figures", { approx: approxTotal(p), used: p.used, usable: p.usable, percent: p.percent });
  if (p.overflow) text = `⚠ ${text} · ${t("main.gauge.overflow")}`;
  else if (p.near_limit) text = `⚠ ${text} · ${t("main.gauge.near_limit", { percent: p.percent })}`;
  if (p.uncertain_text) text += ` · ${p.uncertain_text}`;
  if (gauge.preview) text += ` · ${t("main.gauge.next_turn")}`;
  figures.textContent = text;
  figures.title = text; // story 33: cut on a narrow window, whole in the tooltip
  root.title = t("main.gauge.title", { window: p.window, reserve: p.reserve, usable: p.usable });
}

// Story 33: the disciplines present in the gauge, prompt, context, harness, then the neutral
// one; names only, no tokens per discipline (the total stays in the figures).
let renderedGaugeLegend = null;
function renderGaugeLegend(breakdown) {
  const present = new Set(breakdown.map((item) => item.discipline || "neutral"));
  const items = disciplines().filter(([d]) => present.has(d));
  if (present.has("neutral")) items.push(["neutral", DISCIPLINE_NAMES.neutral]);
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

// FinOps: « Coût estimé : entrée … $ · sortie … $ » (a call), « coût estimé entrée … $ ·
// sortie … $ » (a turn's head), from the cost fields; always said to be an estimate.
function costText(cost, label = t("main.cost.call_label")) {
  const guess = approx(cost.cost_source === "estimate");
  return t("main.cost.text", { label, input: `${guess}${usd(cost.cost_in_usd)}`, output: `${guess}${usd(cost.cost_out_usd)}` });
}

// GreenOps: « Empreinte estimée : 0,11 Wh · 0,046 g CO₂e » (a call), « empreinte estimée … » (a
// turn's head), a range when EcoLogits gives one; from the footprint fields.
function footprintText(p, label = t("main.footprint.call_label")) {
  return `${label}${rangeText(p.energy_wh_min, p.energy_wh_max, "Wh")} · ${rangeText(p.gco2e_min, p.gco2e_max, "g CO₂e")}`;
}

// GreenOps: a call's footprint line, the method and its limits (or why there is none, the
// command to install CodeCarbon included) in its tooltip; `null` for a call that says
// nothing of it.
function footprintNode(ended) {
  if (ended?.energy_wh_min == null && !ended?.impact_note_text) return null;
  const known = ended.energy_wh_min != null;
  const node = el("div", `token-counter footprint${known ? " number" : " is-unavailable"}`, known ? footprintText(ended) : t("main.footprint.unavailable"));
  if (ended.impact_note_text) node.title = ended.impact_note_text;
  return node;
}

// FinOps, the top bar's compact amounts: 4 decimals at most (a hundredth of a cent), « < 0,0001 $ »
// under it; the 4 significant digits stay in the tooltip. Formatting only.
const shortMoneyFormat = () => intlNumber({ minimumFractionDigits: 0, maximumFractionDigits: 4 });
const shortUsd = (n) =>
  n > 0 && n < 0.00005
    ? t("common.format.usd_below", { amount: shortMoneyFormat().format(0.0001) })
    : t("common.format.usd", { amount: shortMoneyFormat().format(n) });

// FinOps: the session's API spend in the top bar, from the first paid call, on three lines
// (lot 1 of 2026-10-04): « Dépense estimée », « 💰 entrée $ + sortie $ », « 🍃 a–b g CO₂e »;
// the whole sentence (4 significant digits, the euros) in the tooltip and the accessible name
// (every figure from the session, AD-1). Before any paid call (local calls only), two lines:
// « Empreinte estimée » over the footprint.
function renderConsumption() {
  const node = document.getElementById("consumption");
  const c = store.consumption;
  node.hidden = !c;
  if (!c) return;
  const paid = c.calls > 0;
  const green = (c.impact_calls ?? 0) > 0;
  const guess = approx(c.approx);
  const grams = green ? rangeText(c.gco2e_min, c.gco2e_max, "g CO₂e") : "";
  setText(document.getElementById("consumption-label"), paid ? t("main.consumption.spend_label") : t("main.consumption.footprint_label"));
  const money = document.getElementById("consumption-money");
  setText(money, paid ? `💰 ${guess}${shortUsd(c.total_in_usd)} + ${shortUsd(c.total_out_usd)}` : "");
  money.hidden = !paid;
  const footprint = document.getElementById("consumption-footprint");
  setText(footprint, green ? `🍃 ${grams}` : "");
  footprint.hidden = !green;
  const sentences = [];
  if (paid) {
    sentences.push(
      t("main.consumption.spend_sentence", {
        input: `${guess}${usd(c.total_in_usd)}`,
        output: `${guess}${usd(c.total_out_usd)}`,
        total: `${guess}${eur(c.total_eur)}`,
        rate: moneyFormat().format(c.eur_per_usd),
        calls: t("main.consumption.paid_calls", { count: c.calls }),
      }),
    );
    // Finition V1 (#27): the session's cap, shown before it bites (no warning as it nears).
    if (store.maxSessionUsd != null) {
      sentences.push(t("main.consumption.cap_sentence", { total: `${guess}${usd(c.total_usd)}`, cap: usd(store.maxSessionUsd) }));
    }
  }
  if (green) {
    sentences.push(
      t("main.consumption.footprint_sentence", {
        energy: rangeText(c.energy_wh_min, c.energy_wh_max, "Wh"),
        grams,
        calls: t("common.count.call", { count: c.impact_calls }),
      }),
    );
  }
  // The totals shown (spend, footprint), never the cap's sentence (finition V1, #27).
  sentences.push(paid && green ? t("main.consumption.reset_totals") : t("main.consumption.reset_total"));
  const sentence = sentences.join(" ");
  if (node.title !== sentence) {
    node.title = sentence;
    node.setAttribute("aria-label", sentence);
  }
}

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
  // Languages (2/5): the provider in a span of its own, which a narrow bar drops (app.css);
  // it stays in the tooltip and the accessible name.
  const tag = el("span", network ? "hosting-tag-network" : "hosting-tag-local");
  tag.append(t(network ? "main.hosting.network" : "main.hosting.local"));
  if (network || served) tag.append(el("span", "model-indicator-provider", ` · ${model.provider}`));
  button.replaceChildren(tag, el("span", "model-indicator-name", model.label));
  button.title = served
    ? t("main.model.served_title", { provider: model.provider, url: model.server_url })
    : model.warning_text ?? t("main.model.local_title", { model: model.label });
  button.setAttribute("aria-label", t("main.model.active_label", { model: model.label, title: button.title }));
}

// ---------- story 17: model picker (EXPERIENCE.md model-picker), hot switch ----------

const PICK_OTHER = "other";
// Story 25: the table of the models and their capabilities, just before PICK_OTHER; lot 3 of
// 2026-10-04: merged into « Diagnostic et modèles » (`/diagnostic`).
const PICK_MODELS = "models";
const PICK_LEGEND = "legend"; // a disabled option, never chosen
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
  const legend = store.modelList?.models?.legend_text;
  picker.title = !idle
    ? state?.reason_text || t("common.unavailable_outside_turn")
    : !store.modelList
      ? t("main.model.list_unavailable")
      : `${t("main.model.picker_title")}${legend ? ` ${legend}` : ""}`;
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
    pending === PICK_OTHER
      ? t("main.model.open_diagnostic")
      : pending === PICK_MODELS
        ? t("main.model.open_table")
        : pending.startsWith("cloud:")
          ? t("main.model.choose")
          : t("main.model.load")
  );
}

// ---------- story 26: the context window (DESIGN.md > window-picker, AD-9) ----------

// Every figure and text of the panel comes from `context_window_state` (AD-1): the browser
// only lays them out, marks the choice noted and says why « Appliquer » is disabled.
const windowPanel = () => document.getElementById("window-panel");
let renderedWindowKey = null;
let windowApplying = false; // a POST in flight: a second click sends nothing

function bindWindowPicker() {
  document.getElementById("window-toggle").addEventListener("click", () => {
    if (windowPanel().hidden) openWindowPanel();
    else closeWindowPanel(true);
  });
  document.getElementById("window-close").addEventListener("click", () => closeWindowPanel(true));
  document.getElementById("window-apply").addEventListener("click", applyWindow);
  document.getElementById("window-choices").addEventListener("change", (event) => {
    if (event.target.name !== "window-choice") return;
    store.windowPick = Number(event.target.value);
    store.windowError = null;
    renderWindowPicker();
  });
  window.addEventListener("resize", () => {
    if (!windowPanel().hidden) placeWindowPanel();
  });
}

// Lot K (K8): the panel drops under its button, left-aligned; when that would take it past
// the window's right edge (853 px at a 150 % zoom, no pane hidden), it moves left by the
// overflow, never past the window's left edge. Its width already fits the window (CSS).
function placeWindowPanel() {
  const panel = windowPanel();
  panel.style.left = "";
  const margin = 16; // --spacing-4, the gutter the CSS width keeps on each side
  const rect = panel.getBoundingClientRect();
  const overflow = rect.right - (document.documentElement.clientWidth - margin);
  if (overflow > 0) panel.style.left = `${-Math.min(overflow, Math.max(0, rect.left - margin))}px`;
}

function openWindowPanel() {
  store.windowPick = store.windowState?.configured ?? null;
  store.windowError = null;
  windowPanel().hidden = false;
  document.getElementById("window-toggle").setAttribute("aria-expanded", "true");
  placeWindowPanel();
  renderWindowPicker();
  const checked = windowPanel().querySelector('input[name="window-choice"]:checked');
  (checked ?? windowPanel().querySelector('input[name="window-choice"]'))?.focus();
}

function closeWindowPanel(returnFocus = false) {
  if (windowPanel().hidden) return;
  windowPanel().hidden = true;
  store.windowError = null;
  const toggle = document.getElementById("window-toggle");
  toggle.setAttribute("aria-expanded", "false");
  if (returnFocus) toggle.focus();
}

// Why « Appliquer » cannot act on the choice noted, else `null`.
function windowApplyReason(ws, pick) {
  const state = store.sessionState;
  if (state?.state !== "idle") return state?.reason_text || t("main.window.between_turns");
  if (ws.locked_text) return ws.locked_text;
  if (pick === ws.configured) return t("main.window.already", { window: pick });
  const choice = ws.choices.find((c) => c.window === pick);
  if (!choice) return t("main.window.choose");
  return choice.fits ? null : choice.refusal_text;
}

function renderWindowPicker() {
  const ws = store.windowState;
  const toggle = document.getElementById("window-toggle");
  setText(document.getElementById("window-toggle-value"), ws ? fmt(ws.window) : "…");
  toggle.disabled = !ws;
  // Lot K (A3): the button shows the effective window; the one chosen, when it differs
  // (llama-server's `-c`, the native context…), is in its tooltip.
  const chosen = ws && ws.configured !== ws.window ? t("main.window.chosen", { window: ws.configured }) : "";
  const title = !ws
    ? t("main.window.waiting")
    : t("main.window.toggle_title", { window: ws.window, bound: ws.bound_text ? `, ${ws.bound_text}` : "", chosen });
  if (toggle.title !== title) toggle.title = title;
  toggle.setAttribute("aria-label", ws ? t("main.window.toggle_label", { window: ws.window }) : t("main.window.panel_title"));
  if (!ws || windowPanel().hidden) return;
  const pick = store.windowPick ?? ws.configured;
  const list = document.getElementById("window-choices");
  setText(
    document.getElementById("window-help"),
    t("main.window.help", { window: ws.default })
  );
  // A value set by hand outside the choices: said, no choice marked « (actuelle) ».
  const offList = !ws.choices.some((c) => c.current);
  const currentLine = document.getElementById("window-current");
  currentLine.hidden = !offList;
  setText(currentLine, offList ? t("main.window.current_off_list", { window: ws.configured }) : "");
  // Rebuilt only when the session's figures change: an arrow key moving the choice keeps
  // its focus (the choice noted is set in place below); a rebuild gives it back.
  const key = JSON.stringify(ws);
  if (key !== renderedWindowKey) {
    renderedWindowKey = key;
    const focused = list.contains(document.activeElement) ? document.activeElement.value : null;
    list.replaceChildren(...ws.choices.map(windowChoiceNode));
    if (focused !== null) list.querySelector(`input[name="window-choice"][value="${focused}"]`)?.focus();
  }
  for (const input of list.querySelectorAll('input[name="window-choice"]')) {
    const checked = Number(input.value) === pick;
    if (input.checked !== checked) input.checked = checked;
    input.closest(".window-choice").classList.toggle("is-picked", checked);
  }
  setText(document.getElementById("window-note"), ws.read_note_text);
  const apply = document.getElementById("window-apply");
  const reason = windowApplying ? t("main.window.request_pending") : windowApplyReason(ws, pick);
  apply.disabled = Boolean(reason);
  const applyTitle = reason ?? t("main.window.apply_title", { window: pick });
  if (apply.title !== applyTitle) apply.title = applyTitle;
  const alert = document.getElementById("window-alert");
  alert.hidden = !store.windowError;
  setText(alert, store.windowError ?? "");
}

function windowChoiceNode(choice) {
  const row = el("div", "window-choice");
  row.dataset.window = String(choice.window);
  row.classList.toggle("is-refused", !choice.fits);
  const label = el("label", "window-choice-label");
  const input = el("input");
  input.type = "radio";
  input.name = "window-choice";
  input.value = String(choice.window);
  input.disabled = !choice.fits; // AD-9: a refused choice is only disabled, its reason shown
  const details = el("div", "window-choice-details");
  const figures = el("span", "window-choice-figures");
  figures.id = `window-choice-${choice.window}`;
  label.append(input, el("strong", "", t("main.window.choice", { window: choice.window })));
  if (choice.current) label.append(el("span", "window-choice-current", ` ${t("main.window.current")}`));
  figures.append(el("span", "window-choice-line", choice.kv_text), el("span", "window-choice-line", choice.read_text));
  if (choice.bound_text) figures.append(el("span", "window-choice-line window-choice-bound", choice.bound_text));
  const verdict = choice.fits
    ? el("span", "window-choice-verdict is-fits", `✓ ${t("main.window.fits")}`)
    : el("span", "window-choice-verdict is-refused", `⚠ ${choice.refusal_text}`);
  verdict.id = `window-choice-${choice.window}-verdict`;
  details.append(figures, verdict);
  // The figures and the verdict (a refused choice's reason) describe the radio.
  input.setAttribute("aria-describedby", `${figures.id} ${verdict.id}`);
  row.append(label, details);
  return row;
}

async function applyWindow() {
  const ws = store.windowState;
  if (!ws || windowApplying) return;
  const pick = store.windowPick ?? ws.configured;
  store.windowError = null;
  windowApplying = true;
  renderWindowPicker(); // « Appliquer » disabled during the request
  try {
    const response = await postIntention("/api/intentions/context_window", { window: pick });
    const answer = await response.json().catch(() => ({}));
    if (!response.ok) {
      const detail = typeof answer.detail === "string" ? answer.detail : t("main.window.refused");
      store.windowError = detail; // in the panel and in the top bar
      store.topStatus = detail;
    } else {
      closeWindowPanel(true);
      // A reload is followed as a model load (`model_load_*`); otherwise the answer says it.
      store.topStatus = answer.switching ? null : answer.message_text ?? null;
    }
  } catch (error) {
    store.windowError = t("main.request_failed", { error: error.message });
  } finally {
    windowApplying = false;
  }
  render();
}

// Story 25: the groups the session built (`/api/diagnostic.models`: hosting, then publisher,
// sorted by size, AD-1); the browser only marks the active model. Before the story's API,
// or when the table could not be built, the former lists.
function rebuildModelPicker(picker, active) {
  const models = store.modelList?.models;
  if (!Array.isArray(models?.groups)) {
    rebuildModelPickerByKind(picker, active);
    return;
  }
  const activeKey = modelKey(active);
  const groups = models.groups.map((group) => {
    const optgroup = el("optgroup");
    optgroup.label = group.label_text;
    for (const m of group.models) {
      const isActive = activeKey === `${m.kind}:${m.ref}`;
      const unusable = !m.usable;
      const suffix = isActive
        ? ` ${t("main.model.suffix_active")}`
        : unusable
          ? m.hosting === "network"
            ? ` ${t("main.model.suffix_unavailable")}`
            : ` ${t("main.model.suffix_incompatible")}`
          : "";
      optgroup.append(
        pickerOption(m.value, `${m.label_text}${suffix}`, {
          disabled: isActive || unusable,
          title: unusable ? m.disabled_text ?? "" : m.title_text,
        })
      );
    }
    return optgroup;
  });
  const head = pickerOption("", t("main.model.picker_head"));
  const legend = pickerOption(PICK_LEGEND, models.legend_text, { disabled: true, title: models.legend_text });
  picker.replaceChildren(
    head,
    legend,
    ...groups.filter((g) => g.children.length),
    pickerOption(PICK_MODELS, t("main.model.picker_table")),
    pickerOption(PICK_OTHER, t("main.model.picker_other"))
  );
}

function rebuildModelPickerByKind(picker, active) {
  const list = store.modelList ?? { candidates: [], cloud: { models: [] } };
  const local = el("optgroup");
  local.label = t("main.model.group_local");
  const seen = new Set();
  for (const c of list.candidates ?? []) {
    if (c.source === "server") {
      // Story 18: a model an already-running local server serves, chosen like a file.
      const isActive = active?.kind === "server" && active.ref === c.ref;
      const unusable = c.status !== "server";
      const suffix = isActive ? ` ${t("main.model.suffix_active")}` : unusable ? ` ${t("main.model.suffix_incompatible")}` : "";
      local.append(
        pickerOption(`server:${c.ref}`, `${t("main.hosting.local")} · ${c.provider} · ${c.name}${suffix}`, {
          disabled: isActive || unusable,
          title: unusable ? c.reason ?? "" : t("main.model.served_at", { provider: c.provider, url: c.server_url }),
        })
      );
      continue;
    }
    if (c.status !== "found" || !c.path || seen.has(c.path)) continue;
    seen.add(c.path);
    const isActive = active?.kind === "file" && active.ref === c.path;
    const size = c.size_label ? ` · ${c.size_label}` : "";
    local.append(
      pickerOption(`file:${c.path}`, `${c.name}${size}${isActive ? ` ${t("main.model.suffix_active")}` : ""}`, {
        disabled: isActive,
        title: c.path,
      })
    );
  }
  const network = el("optgroup");
  network.label = t("main.model.group_network");
  for (const m of list.cloud?.models ?? []) {
    const isActive = active?.kind === "cloud" && active.ref === m.id;
    const suffix = isActive ? ` ${t("main.model.suffix_active")}` : m.disabled_text ? ` ${t("main.model.suffix_unavailable")}` : "";
    network.append(
      pickerOption(`cloud:${m.id}`, `${t("main.hosting.network")} · ${m.provider} · ${m.model}${suffix}`, {
        disabled: isActive || Boolean(m.disabled_text),
        title: m.disabled_text ?? "",
      })
    );
  }
  const head = pickerOption("", t("main.model.picker_head"));
  const groups = [local, network].filter((g) => g.children.length);
  picker.replaceChildren(head, ...groups, pickerOption(PICK_OTHER, t("main.model.picker_other")));
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
  if (value === PICK_MODELS) {
    // Lot 3 of 2026-10-04: the table is the « Diagnostic et modèles » page now; same tab.
    window.location.href = "/diagnostic";
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
    if (!response.ok) store.topStatus = answer.detail || t("main.model.switch_refused");
    else if (!answer.switching) store.topStatus = answer.message_text ?? null; // « … est déjà actif. »
  } catch (error) {
    store.topStatus = t("main.request_failed", { error: error.message });
  }
  render();
}

// EXPERIENCE.md cloud-warning: in the page, texts from `/api/diagnostic`; nothing changes
// before « Utiliser ce modèle ».
let warningModel = null;

function openCloudWarning(model) {
  if (!model?.warning) {
    // Without its warning text, a cloud model cannot be confirmed, hence not chosen (AD-21).
    store.topStatus = model ? t("main.model.warning_unavailable") : t("main.model.gone");
    render();
    return;
  }
  warningModel = model;
  const w = model.warning;
  setText(document.getElementById("cloud-warning-title"), w.title_text);
  document
    .getElementById("cloud-warning-points")
    .replaceChildren(...["sent_text", "provider_text", "unseen_text"].map((k) => el("li", "", w[k])));
  setText(document.getElementById("cloud-warning-confirm"), w.confirm_text);
  setText(document.getElementById("cloud-warning-cancel"), w.cancel_text);
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
  // Lot E (E4), story 24: the probe stops at once, an in-process load at the end of its step;
  // the front cannot tell which, so it only says the stop was asked.
  const stopping = load.stopRequested ? `${t("main.model.stop_requested")} · ` : "";
  const what = load.phaseLabel ?? t("main.model.loading", { model: load.model.label });
  return `${stopping}${what} ${seconds(Date.now() - load.startedAt)}`;
}

// Story 24: why « Arrêt demandé » may last, in the top bar's tooltip; `undefined` otherwise.
function modelLoadTitle() {
  return store.modelLoad?.stopRequested ? t("main.model.stop_explained") : undefined;
}

// ---------- human view: bubbles, working indicator, composer ----------

function turnNote(turn) {
  switch (turn.status) {
    case "overflow":
      return t("main.chat.note.overflow");
    case "limit":
      if (turn.limit) return turn.limit.message_text;
      if (turn.truncated?.channel === "reasoning") {
        return t("main.chat.note.cut_reasoning", { tokens: turn.truncated.max_tokens });
      }
      return t("main.chat.note.cut", { tokens: turn.truncated?.max_tokens ?? 0 });
    case "cancelled":
      return t("main.chat.note.cancelled");
    case "error":
      return t("main.chat.note.error", { errors: turn.errors.join(" ") || t("main.chat.note.interrupted") });
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
  // Story 34: linked to the Raisonnement card and to the other reasoning blocks; unfolding it
  // by hand selects it too (nothing is left to the hover alone), folding it clears that.
  setLinks(details, ["reasoning"]);
  let byUser = false; // a rebuilt block opened by the code must not select
  summary.addEventListener("click", () => (byUser = true));
  details.append(summary, el("div", "reasoning-text", text));
  details.addEventListener("toggle", () => {
    if (details.open) store.openReasoning.add(key);
    else store.openReasoning.delete(key);
    if (!byUser) return;
    byUser = false;
    const id = `reasoning:${key}`;
    if (details.open) setSelection(id, ["reasoning"]);
    else if (store.selection === id) clearSelection();
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

// Recette du 02/10: each turn's rendered answer, kept while its text is unchanged (no re-parse
// while streaming); a changed text is rendered again.
let answerNodes = new Map(); // turn id -> { text, nodes }

// The answer's Markdown as DOM nodes (never an HTML string), in a new `.bubble-text`.
function answerText(turn, kept) {
  const old = answerNodes.get(turn.id);
  const entry = old?.text === turn.text ? old : { text: turn.text, nodes: [...renderMarkdown(turn.text).childNodes] };
  kept.set(turn.id, entry);
  const div = el("div", "bubble-text is-markdown");
  div.append(...entry.nodes);
  return div;
}

function renderChat() {
  const chat = document.getElementById("chat");
  const followTail = chat.scrollHeight - chat.scrollTop - chat.clientHeight < 40;
  // The rebuild could drop keyboard focus: note it, restore it on the new element.
  const focusKey = chat.contains(document.activeElement) ? document.activeElement.dataset.focusKey : null;
  const nodes = [];
  const cards = new Map();
  const answers = new Map();
  const turns = shownTurns();
  if (turns.length === 0) nodes.push(emptyNote(cleared() ? clearedText() : noTurnText()));
  let shownBefore = null;
  for (const turn of turns) {
    // Story 17: « Modèle : … » above the first turn shown, then above each turn played by
    // another model than the turn shown before it.
    if (turn.model && modelKey(shownBefore?.model) !== modelKey(turn.model)) {
      nodes.push(el("div", "model-switch-line", t("main.chat.model_line", { model: turn.model.label })));
    }
    shownBefore = turn;
    const user = el("div", "bubble bubble-user", turn.message);
    const origin = turn.replayOf && store.turns.find((t) => t.id === turn.replayOf);
    if (origin) {
      // Story 9b: the replayed turn opens the comparison with its origin.
      const badge = el("button", "replay-badge", t("main.chat.replay_badge"));
      badge.type = "button";
      badge.setAttribute("aria-label", t("main.chat.replay_label", { turn: turnNameLower(origin) }));
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
        const title = reasonings.length > 1 ? t("main.chat.reasoning_call", { n: String(i + 1) }) : t("main.chat.reasoning");
        answer.appendChild(reasoningBlock(text, `chat:${turn.id}:${i}`, title));
      });
    } else if (turn.status === null && turn.firstToken && turn.reasoning && !turn.text) {
      // The reasoning is hidden: the bubble still says the model is working.
      const since = turn.callStartedAt ?? turn.startedAt;
      answer.appendChild(el("div", "working-indicator", `${t("main.chat.reasoning_now")} ${seconds(Date.now() - since)}`));
    }
    if (turn.text) answer.appendChild(answerText(turn, answers));
    if (turn.status === null && !turn.firstToken) {
      const since = turn.callStartedAt ?? turn.startedAt;
      const label = turn.stopRequested ? t("main.chat.stop_requested") : turn.phaseLabel || t("main.chat.preparing");
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
      answer.appendChild(el("div", "bubble-note", t("main.chat.empty_answer")));
    }
    const consulted = consultedTools(turn);
    if (consulted.length) answer.appendChild(consultedLine(turn, consulted));
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
  answerNodes = answers;
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
    quietFocus(target);
  }
  if (followTail) chat.scrollTop = chat.scrollHeight;
}

// D5 of 2026-10-01: the tools whose result the answer could draw on, each with its step's
// index in `turn.steps` (the key of its Orchestration line is `{turn.id}:{index}`): ended
// `ok` only (a failed, refused or still running call brought nothing). The harness's own
// tools (`load_skill`, `load_tool_doc`, `remember`) bring no information to cite; a
// delegation brings the sub-agent's answer, so it counts.
function consultedTools(turn) {
  const found = [];
  turn.steps.forEach((step, index) => {
    if (step.type !== "tool" || !step.started || step.ended?.status !== "ok") return;
    if (step.started.source === "harness" && step.started.tool !== "delegate") return;
    found.push({ step, index });
  });
  return found;
}

// « Outils consultés pendant ce tour : A, B », each name a button that opens its step.
function consultedLine(turn, consulted) {
  const line = el("p", "answer-tools");
  line.appendChild(el("span", "answer-tools-label", t("main.chat.tools_used")));
  consulted.forEach(({ step, index }, n) => {
    const name = step.started.tool === "delegate" ? t("main.orch.sub.title") : toolLabel(step.started.tool);
    const button = el("button", "answer-tool", name);
    button.type = "button";
    button.title = t("main.chat.tools_used_title", { tool: name });
    button.dataset.focusKey = `tools:${turn.id}:${index}`;
    setLinks(button, stepLinks(step));
    const reveal = () => revealStep(turn, `${turn.id}:${index}`, stepLinks(step));
    // The bubble is rebuilt at every render (a turn streaming): a mouse acts on its press, as
    // `selectOnActivate` does, before a rebuild can split the press from the release.
    button.addEventListener("pointerdown", (event) => {
      if (event.pointerType === "mouse" && event.button === 0) reveal();
    });
    button.addEventListener("click", (event) => {
      if (event.pointerType !== "mouse") reveal(); // keyboard, touch, pen
    });
    line.append(n === 0 ? " " : ", ", button);
  });
  return line;
}

// D5: the step of a turn opened in Orchestration, as a click on it does (`toggleStep`, which
// freezes the live view) and as `revealOutbound` brings it into view, then selected.
function revealStep(turn, key, links) {
  const o = store.orch;
  if (store.hiddenPanes.has("orch")) showPane("orch");
  if (store.focusedPane !== null && store.focusedPane !== "orch") store.focusedPane = null;
  o.turnOpen.set(turn.id, true);
  if (o.live) {
    o.live = false;
    o.userOpen = new Set(o.current && !o.currentApart ? [o.current] : []);
  }
  o.userOpen.add(key);
  o.selected = key;
  setSelection(`step:${key}`, links); // renders: the step open, its linked elements outlined
  railNodes.get(key)?.line.scrollIntoView({ block: "nearest" });
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
  const ready = state?.state === "idle" && !state.reason_text;
  document.getElementById("composer-input").disabled = !ready;
  document.getElementById("composer-send").disabled = !ready;
  const clear = document.getElementById("clear-conversation");
  clear.disabled = state?.state !== "idle"; // class (b)
  clear.title = clear.disabled ? state?.reason_text || t("common.unavailable_outside_turn") : "";
  const replay = document.getElementById("replay-last");
  replay.disabled = clear.disabled || shownTurns().length === 0; // class (b), story 9b
  replay.title = clear.disabled ? clear.title : replay.disabled ? t("main.chat.nothing_to_replay") : "";
  const compare = document.getElementById("compare-turns");
  compare.disabled = shownTurns().length < 2;
  compare.title = compare.disabled ? t("main.chat.compare_needs_two") : "";
  const stop = document.getElementById("composer-stop");
  // Lot E (E4): « Arrêter » also stops a model load (the previous model comes back).
  const loading = state?.state === "model_load" && Boolean(store.modelLoad);
  stop.hidden = state?.state !== "turn" && state?.state !== "awaiting_human" && !loading;
  stop.disabled = loading ? Boolean(store.modelLoad.stopRequested) : Boolean(activeTurn()?.stopRequested);
  const reason = document.getElementById("composer-reason");
  const text = store.composerError || (ready ? null : state?.reason_text || t("main.chat.waiting_model"));
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

// The scenario's instructions sit behind the « i » next to the Vue humain title, so they
// never take room from the conversation. A toggletip: the native popover opens on click
// (Escape or a click outside closes it), and a mouse resting on the « i » previews it as a
// tooltip, which a click then keeps open. UI state only, not remembered.
const INFO_HOVER_OPEN_MS = 300;
const INFO_HOVER_CLOSE_MS = 200;
let infoHoverTimer = null;
let infoOpenedByHover = false;

function setupScenarioInfo() {
  const button = document.getElementById("scenario-info");
  const popover = document.getElementById("scenario-info-popover");
  const isOpen = () => popover.matches(":popover-open");
  const later = (delay, action) => {
    clearTimeout(infoHoverTimer);
    infoHoverTimer = setTimeout(action, delay);
  };
  const leave = (event) => {
    if (event.pointerType !== "mouse") return;
    later(INFO_HOVER_CLOSE_MS, () => {
      if (infoOpenedByHover && isOpen()) popover.hidePopover();
    });
  };
  button.addEventListener("pointerenter", (event) => {
    if (event.pointerType !== "mouse" || button.hidden) return;
    later(INFO_HOVER_OPEN_MS, () => {
      if (isOpen() || button.hidden) return;
      infoOpenedByHover = true;
      popover.showPopover();
    });
  });
  button.addEventListener("pointerleave", leave);
  popover.addEventListener("pointerenter", () => clearTimeout(infoHoverTimer));
  popover.addEventListener("pointerleave", leave);
  button.addEventListener("click", (event) => {
    clearTimeout(infoHoverTimer);
    // Open as a preview: the click keeps it open instead of toggling it shut.
    if (infoOpenedByHover && isOpen()) {
      event.preventDefault();
      infoOpenedByHover = false;
    }
  });
  popover.addEventListener("toggle", (event) => {
    if (event.newState === "closed") infoOpenedByHover = false;
  });
}

function renderScenarioInfo(scenario) {
  const button = document.getElementById("scenario-info");
  const popover = document.getElementById("scenario-info-popover");
  button.hidden = !scenario;
  if (!scenario) {
    if (popover.matches(":popover-open")) popover.hidePopover();
    popover.replaceChildren();
    return;
  }
  // No `title`: a native tooltip would pile up on the popover the hover already shows.
  const label = t("main.scenario.info_label", { scenario: scenario.title_text });
  button.setAttribute("aria-label", label);
  popover.replaceChildren(
    el("p", "scenario-info-title", scenario.title_text),
    el("p", "scenario-info-text", scenario.description_text)
  );
  // A new scenario: the « i » glows once so the eye finds where its instructions went.
  button.classList.remove("is-new");
  void button.offsetWidth;
  button.classList.add("is-new");
}

function renderScenarioControls(state) {
  const idle = state?.state === "idle"; // class (b)
  const reason = idle ? "" : state?.reason_text || t("common.unavailable_outside_turn");
  const picker = document.getElementById("scenario-picker");
  const program = store.scenarios?.program ?? null;
  if (renderedProgram !== program) {
    renderedProgram = program;
    const empty = el("option", "", t("main.scenario.choose"));
    empty.value = "";
    const groups = [];
    const group = (label, scenarios) => {
      const node = el("optgroup");
      node.label = label;
      for (const s of scenarios) {
        const option = el("option", "", s.title_text);
        option.value = s.id;
        node.appendChild(option);
      }
      groups.push(node);
    };
    program?.modules.forEach((m, i) =>
      group(t("main.scenario.module", { n: String(i + 1), title: m.title_text, minutes: m.duration_min }), m.scenarios)
    );
    // Story 21: the business scenarios (FR-40) follow the hosting one, in `transverse`.
    if (program?.transverse.length) group(t("main.scenario.transverse"), program.transverse);
    picker.replaceChildren(empty, ...groups);
  }
  const active = store.scenarios?.active ?? "";
  if (picker.value !== active) picker.value = active;
  picker.disabled = !idle;
  picker.title = reason;
  const reset = document.getElementById("reset-button");
  reset.disabled = !idle;
  reset.title = reason || t("main.top_bar.reset_title");
  // E003: a lost connection first, whatever the page last heard (a load, a reset…).
  const lost = store.connectionLost ? t("main.top_bar.connection_lost") : null;
  const topText = lost ?? modelLoadText() ?? store.topStatus ?? "";
  setTopStatus(topText, lost ?? modelLoadTitle() ?? topText);

  // Vue humain: the active scenario's instructions behind the « i » of the header, then one
  // chip per suggested prompt.
  const scenario = findScenario(store.scenarios?.active);
  renderScenarioUnavailable(scenario ? store.scenarios?.unavailable ?? [] : []);
  if (renderedGuide === scenario) return;
  // A refresh of the same scenario (same id, new object) updates the text without the glow.
  const sameScenario = Boolean(scenario) && renderedGuide?.id === scenario.id;
  renderedGuide = scenario;
  renderScenarioInfo(scenario);
  if (sameScenario) document.getElementById("scenario-info").classList.remove("is-new");
  const chips = document.getElementById("suggested-prompts");
  chips.hidden = !scenario;
  if (!scenario) {
    chips.replaceChildren();
    return;
  }
  chips.replaceChildren(
    ...scenario.prompts.map((prompt) => {
      const chip = el("button", "suggested-prompt", prompt);
      chip.type = "button";
      chip.setAttribute("aria-label", t("main.scenario.fill", { prompt }));
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
  const title = t("main.scenario.unavailable", { count: unavailable.length });
  const list = el("ul", "scenario-unavailable-list");
  for (const brick of unavailable) {
    const item = el("li");
    item.append(el("strong", "", brick.label_text), labelValue("", brick.reason_text));
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
      store.composerError = typeof detail.detail === "string" ? detail.detail : t("common.action_refused");
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
  scenarioIntention("/api/intentions/scenario", { scenario_id: id }, t("main.scenario.no_answer"));
}

function resetHarness() {
  store.openExplanations.clear();
  store.openBrickHelp.clear();
  for (const popover of document.querySelectorAll(".brick-explanation:popover-open")) popover.hidePopover();
  scenarioIntention("/api/intentions/reset", {}, t("main.top_bar.reset_no_answer"));
}

// ---------- languages (1/5): the language picker, in « Affichage ▾ » of the shared bar ----------

// Story 2 (2026-09-30): the picker, its lock and its intention are site-nav.js's, shared by the
// five pages; the main screen gives it the session's state, which its events keep current.
useSessionState({ opened: () => closePaneMenu() });

function renderLanguagePicker() {
  const info = store.language;
  drawLanguagePicker(
    info && {
      language: info.language,
      language_locked: info.language_locked,
      idle: store.sessionState?.state === "idle",
      busy_text: store.sessionState?.reason_text ?? null,
    }
  );
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
    const reason = store.sessionState?.reason_text;
    store.composerError = t("main.composer.not_sent", { reason: reason || t("main.composer.not_ready") });
    render();
    return;
  }
  if (!message) {
    store.composerError = t("main.composer.empty");
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
      store.composerError = typeof body.detail === "string" ? body.detail : t("main.composer.refused");
    }
  } catch {
    store.composerError = t("main.composer.no_answer");
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

// ---------- LLM context pane: each call of the turn, what it read then what it produced (story 32) ----------
// The session cuts each context into sections (consecutive segments of one source) and says
// which prefix the previous call of the same context read already (AD-1, AD-9): the pane only
// lays them out. Three views: the grouped reading (default), the exact text sent (the join of
// the segments, or the chat body, byte for byte), and, in chat mode, the JSON body as a tree.

const CTX_MODE_STORAGE_KEY = "wavestack.ctxMode";
const CTX_MODES = [
  ["grouped", () => t("main.ctx.modes.grouped")],
  ["exact", () => t("main.ctx.modes.exact")],
  ["body", () => t("main.ctx.modes.body")], // chat mode only
];

function loadCtxMode() {
  try {
    const saved = localStorage.getItem(CTX_MODE_STORAGE_KEY);
    if (CTX_MODES.some(([id]) => id === saved)) store.ctxMode = saved;
  } catch {
    // No storage: the grouped reading, until the user picks another view.
  }
}

function setCtxMode(mode) {
  store.ctxMode = mode;
  try {
    localStorage.setItem(CTX_MODE_STORAGE_KEY, mode);
  } catch {
    // No storage: the choice lasts until the page is reloaded.
  }
  renderContext();
}

const isChat = (p) => p?.body !== undefined && p?.body !== null;
// « Corps JSON » falls back on the grouped reading outside chat mode.
const ctxMode = (chat) => (store.ctxMode === "body" && !chat ? "grouped" : store.ctxMode);

// A stable number per object, for the pane's rebuild key (a reconciled context, a call ended).
const objectIds = new WeakMap();
let nextObjectId = 1;
function objectId(o) {
  if (!o || typeof o !== "object") return 0;
  if (!objectIds.has(o)) objectIds.set(o, nextObjectId++);
  return objectIds.get(o);
}

// The turn and the context shown: the tab chosen (story 22), else the last turn with a context.
function ctxShown() {
  const turns = shownTurns();
  const chosen = store.ctxView && turns.find((t) => t.id === store.ctxView.turn);
  const turn = chosen?.subs.get(store.ctxView.sub)?.context ? chosen : turns.findLast((t) => t.context);
  if (!turn) return null;
  const subs = [...turn.subs.values()].filter((s) => s.context);
  const view = store.ctxView?.turn === turn.id ? turn.subs.get(store.ctxView.sub) : null;
  const owner = view?.context ? view : turn;
  return { turn, subs, owner, chat: isChat(owner.context) };
}

const ctxCalls = (owner) => owner.steps.filter((s) => s.type === "call");

// The steps between a call and the next call of the same context (tools, hooks, errors).
function stepsAfter(owner, call) {
  const from = owner.steps.indexOf(call) + 1;
  const next = owner.steps.findIndex((s, i) => i >= from && s.type === "call");
  return owner.steps.slice(from, next < 0 ? undefined : next);
}

// « Vider la conversation » and « Réinitialiser »: the folds of calls that are gone.
function clearCtxFolds() {
  for (const set of [store.openSeen, store.jsonToggled, store.openExact]) set.clear();
}

// A call step clicked in Orchestration (story 34 selection): its call in Contexte LLM is
// brought into view, as its sections may sit far above (not on hover).
function revealCall(keys) {
  const id = keys.find((k) => k.startsWith("call:"))?.slice(5);
  if (!id) return;
  document.querySelector(`#ctx .ctx-call[data-call-id="${cssEscape(id)}"]`)?.scrollIntoView({ block: "nearest" });
}

// What the pane shows, as a key: it is rebuilt only when this changes (story 32), so an
// unfolded block, the keyboard focus and the scroll stay; the running call's text is patched.
function ctxKey(shown) {
  if (!shown) return JSON.stringify(["none", cleared()]);
  const { turn, owner, subs, chat } = shown;
  const calls = ctxCalls(owner);
  const last = calls.at(-1);
  return JSON.stringify([
    ctxMode(chat),
    turn.id,
    turnNumber(turn),
    owner === turn ? "main" : owner.contextId,
    subs.map((s) => s.contextId),
    objectId(store.bricks),
    store.activeModel?.banner_text ?? null,
    calls.map((c) => [c.id, c.startedAt ?? null, objectId(c.context), objectId(c.ended), objectId(c.cut)]),
    owner.steps.length,
    last && !last.ended ? [Boolean(owner.reasoning), Boolean(owner.text)] : null,
    turn.status,
    turn.errors.length,
    owner.errors?.length ?? 0,
    owner.notices?.length ?? 0,
    Boolean(owner.overflow),
    objectId(owner.ended),
  ]);
}

let renderedCtxKey = null;
// The running call's nodes, patched in place at each delta: `{ owner, answer, reasoning, raw }`.
let ctxLive = null;

function renderContext() {
  const pane = document.getElementById("ctx");
  if (store.compare) {
    renderedCtxKey = null;
    ctxLive = null;
    renderCompare(pane);
    return;
  }
  const shown = ctxShown();
  const key = ctxKey(shown);
  // Streaming (EXPERIENCE.md): the scroll follows the end of the text, unless the user went up.
  const atEnd = pane.scrollHeight - pane.scrollTop - pane.clientHeight < 40;
  if (key !== renderedCtxKey) {
    renderedCtxKey = key;
    // The rebuild would drop keyboard focus (e.g. on the view switch) and the scroll: restore them.
    const focusKey = pane.contains(document.activeElement) ? document.activeElement.dataset.focusKey : null;
    const scroll = pane.scrollTop;
    ctxLive = null;
    renderContextBody(pane, shown);
    pane.scrollTop = scroll;
    if (focusKey) quietFocus(pane.querySelector(`[data-focus-key="${cssEscape(focusKey)}"]`));
  }
  if (ctxLive) {
    const { owner } = ctxLive;
    if (ctxLive.answer) setText(ctxLive.answer, owner.text);
    if (ctxLive.reasoning) setText(ctxLive.reasoning, owner.reasoning);
    if (ctxLive.raw) setText(ctxLive.raw, owner.reasoning + owner.text || "…");
    if (atEnd) pane.scrollTop = pane.scrollHeight;
  }
}

function renderContextBody(pane, shown) {
  pane.innerHTML = "";
  if (!shown) {
    pane.appendChild(emptyNote(cleared() ? clearedText() : noTurnText()));
    return;
  }
  const { turn, subs, owner, chat } = shown;
  // Story 19: « Agent principal » / « Sous-agent sub1 », one tab per sub-agent (story 22);
  // what follows is the selected tab's panel.
  if (subs.length) {
    const tabs = ctxViewSwitch(turn, subs, owner === turn ? null : owner);
    const panel = el("div", "ctx-view-panel");
    panel.id = "ctx-view-panel";
    panel.setAttribute("role", "tabpanel");
    panel.setAttribute("aria-labelledby", tabs.querySelector("[aria-selected='true']").id);
    pane.append(tabs, panel);
    pane = panel;
  }
  pane.appendChild(ctxModeSwitch(chat));
  const p = owner.context;
  if (owner === turn) {
    if (chat) {
      // Chat mode: the context is the JSON body sent to the provider (FR-43).
      const banner = store.activeModel?.banner_text ?? t("main.ctx.cloud_banner");
      pane.appendChild(el("p", "ctx-banner", banner));
    }
    // AD-4: the provider's total replaces the sum of the segments, it is not added to it.
    const source = p.usage_source === "api" ? t("main.ctx.source_api") : t("main.ctx.source_sum");
    pane.appendChild(
      el(
        "p",
        "ctx-total",
        t("main.ctx.total", {
          owner: turnName(turn),
          approx: approxTotal(p),
          used: p.used,
          source,
          window: p.window,
          reserve: p.reserve,
        })
      )
    );
    if (p.uncertain_text) pane.appendChild(el("p", "bubble-note", p.uncertain_text));
    if (p.uncompressed_used != null) {
      // Story 20: the session's total without compression, next to the one sent (FR-31).
      pane.appendChild(
        el(
          "p",
          "ctx-compressed-total",
          `🗜️ ${t("main.ctx.without_compression", { uncompressed: p.uncompressed_used, sent: `${approxTotal(p)}${fmt(p.used)}` })}`
        )
      );
    }
  } else {
    pane.appendChild(
      el(
        "p",
        "ctx-total",
        t("main.ctx.total", {
          owner: t("main.ctx.subagent", { id: owner.contextId }),
          approx: approxTotal(p),
          used: p.used,
          source: t("main.ctx.source_sum"),
          window: p.window,
          reserve: p.reserve,
        })
      )
    );
    if (owner.ended) {
      pane.appendChild(el("p", "subagent-saving", `${t("main.ctx.stays_in_subagent")} ${subSaving(owner.ended)}`));
    }
  }
  pane.appendChild(renderCalls(owner, turn, chat));
  for (const notice of owner === turn ? [] : owner.notices) pane.appendChild(el("p", "bubble-note", notice));
  for (const error of owner.errors) pane.appendChild(el("p", "bubble-note is-error", error));
}

// « Lecture groupée », « Texte exact », and « Corps JSON » in chat mode: remembered by the
// browser, a reading comfort, not a state of the harness.
function ctxModeSwitch(chat) {
  const group = el("div", "ctx-view-mode");
  group.setAttribute("role", "group");
  group.setAttribute("aria-label", t("main.ctx.mode_label"));
  const current = ctxMode(chat);
  for (const [id, label] of CTX_MODES) {
    if (id === "body" && !chat) continue;
    const button = el("button", "ctx-mode-button", label());
    button.type = "button";
    button.setAttribute("aria-pressed", String(current === id));
    button.dataset.focusKey = `ctxmode:${id}`;
    button.addEventListener("click", () => setCtxMode(id));
    group.appendChild(button);
  }
  return group;
}

// The calls of the context shown, numbered, each what it read then what it produced; between
// two calls, what the harness did (EXPERIENCE.md > context-call).
function renderCalls(owner, turn, chat) {
  const list = el("div", "ctx-calls");
  const calls = ctxCalls(owner);
  const mode = ctxMode(chat);
  calls.forEach((call, i) => {
    const last = i === calls.length - 1;
    const section = el("section", "ctx-call");
    section.dataset.callId = call.id;
    section.setAttribute("aria-label", t("main.ctx.call_of", { n: String(i + 1), total: String(calls.length) }));
    section.appendChild(callHead(call, i, calls.length, owner, turn, last));
    if (mode === "exact") {
      section.append(...exactParts(call, owner, last, turn));
    } else {
      section.appendChild(mode === "body" ? bodyPart(call) : readPart(call, turn, chat));
      section.appendChild(producedPart(call, owner, turn, last));
    }
    list.appendChild(section);
    if (!last) list.appendChild(betweenLine(owner, turn, call, calls[i + 1], i + 2));
  });
  return list;
}

// « Appel i sur n », then the call's figures, from its `model_call_ended` (AD-1): read,
// evaluated by the engine (« non communiqué » when it cannot say), produced.
function callHead(call, i, n, owner, turn, last) {
  const head = el("header", "ctx-call-head");
  head.appendChild(el("h3", "ctx-call-title", t("main.ctx.call_of", { n: String(i + 1), total: String(n) })));
  const ended = call.ended;
  const p = call.context;
  let figures;
  if (ended) {
    const guess = approx(ended.usage_source === "estimate");
    const evaluated = ended.evaluated_tokens == null ? t("main.ctx.not_reported") : fmt(ended.evaluated_tokens);
    figures = t("main.ctx.call_figures", {
      read: `${guess}${fmt(ended.prompt_tokens)}`,
      evaluated,
      produced: `${guess}${fmt(ended.output_tokens)}`,
    });
  } else {
    const running = last && turn.status === null && !owner.ended && !owner.overflow;
    const state =
      last && owner.overflow
        ? t("main.ctx.call_state.not_sent")
        : running
          ? t("main.ctx.call_state.running")
          : t("main.ctx.call_state.no_answer");
    figures = t("main.ctx.call_read", { read: `${approxTotal(p)}${fmt(p.used)}`, state });
  }
  head.appendChild(el("p", "ctx-call-figures", figures));
  return head;
}

// ---- « Lu » : the grouped reading ----

// Sections from an older journal (no `sections`): one per segment, nothing summed (AD-1).
function fallbackSections(p) {
  return p.segments.map((s, i) => ({
    start: i,
    end: i + 1,
    kind: s.kind,
    label_text: s.label_text,
    brick: s.kind === "template" ? null : s.brick,
    discipline: s.discipline || "neutral",
    tokens: s.tokens,
    template_tokens: 0,
    estimated: s.estimated,
    seen: false,
  }));
}

// The JSON of the exact text, for the display only: balanced, aware of strings, accepted by
// `JSON.parse` and worth a tree (`treeWorthy`); the first one wins, never nested. A JSON cut
// or invalid stays text. `[start, end, value]`, in characters of `text`. Linear in practice:
// a bracket that cannot close is skipped, and a bracket closed during an earlier scan reuses
// its closing position (the scan from it is the suffix of that scan).
function jsonSpans(text) {
  const spans = [];
  const closeAt = new Map(); // opening position -> position after its closing bracket
  const failed = new Set(); // opening positions that can never close
  let i = 0;
  while (i < text.length) {
    const c = text[i];
    if ((c !== "{" && c !== "[") || failed.has(i)) {
      i += 1;
      continue;
    }
    if (!closeAt.has(i)) {
      const stack = []; // [position, closing bracket]
      let inString = false;
      let j = i;
      for (; j < text.length; j++) {
        const d = text[j];
        if (inString) {
          if (d === "\\") j += 1;
          else if (d === '"') inString = false;
        } else if (d === '"') {
          inString = true;
        } else if (d === "{" || d === "[") {
          stack.push([j, d === "{" ? "}" : "]"]);
        } else if (d === "}" || d === "]") {
          const top = stack.at(-1);
          if (!top || top[1] !== d) break; // a mismatch: nothing still open here can close
          stack.pop();
          closeAt.set(top[0], j + 1);
          if (!stack.length) break;
        }
      }
      for (const [position] of stack) failed.add(position);
    }
    const end = closeAt.get(i);
    const value = end ? parseJson(text.slice(i, end)) : undefined;
    if (value !== undefined && treeWorthy(value, end - i)) {
      spans.push([i, end, value]);
      i = end;
    } else {
      i += 1;
    }
  }
  return spans;
}

// Worth a tree: an object of at least 2 keys or 40 characters, or an array holding at least
// one object, of 40 characters or more; a `[1, 2]` in prose stays text.
function treeWorthy(value, length) {
  if (Array.isArray(value)) {
    return length >= 40 && value.some((v) => v !== null && typeof v === "object" && !Array.isArray(v));
  }
  return Object.keys(value).length >= 2 || length >= 40;
}

// A non-empty object or array, else `undefined`.
function parseJson(text) {
  try {
    const value = JSON.parse(text);
    if (value !== null && typeof value === "object" && Object.keys(value).length) return value;
  } catch {
    // Not JSON: shown as text.
  }
  return undefined;
}

// Chat mode: the body is one JSON, cut into fragments that are not JSON on their own (a tool
// definition: `name","parameters":{…},"description":"…`). Only the definitions of its
// top-level `tools` array get a tree, as `jsonSpans` gives them; the messages keep theirs.
function toolSpans(text) {
  const range = topLevelValue(text, "tools");
  if (!range) return [];
  const [a, b] = range;
  return jsonSpans(text.slice(a + 1, b - 1)).map(([x, y, value]) => [a + 1 + x, a + 1 + y, value]);
}

// `[start, end]` of the object or array under `key` in the top-level object of `text`
// (a JSON written without blanks, as the body is), aware of strings; `null` when absent.
function topLevelValue(text, key) {
  const quoted = JSON.stringify(key);
  let depth = 0;
  let inString = false;
  let from = -1; // where the current string opened
  let isKey = false; // the last string closed at depth 1 is `key`, followed by `:`
  let start = -1;
  for (let i = 0; i < text.length; i++) {
    const c = text[i];
    if (inString) {
      if (c === "\\") i += 1;
      else if (c === '"') {
        inString = false;
        isKey = depth === 1 && text[i + 1] === ":" && text.slice(from, i + 1) === quoted;
      }
    } else if (c === '"') {
      inString = true;
      from = i;
    } else if (c === "{" || c === "[") {
      if (depth === 1 && isKey) start = i;
      depth += 1;
    } else if (c === "}" || c === "]") {
      depth -= 1;
      if (depth === 1 && start >= 0) return [start, i + 1];
    } else if (c === ",") {
      isKey = false;
    }
  }
  return null;
}

// Chat mode: a fragment of the body is inside a JSON string (sentinels, AD-4); decoded for the
// display, raw text when it is not a whole string (a fragment spanning JSON syntax).
function decodeFragment(text) {
  try {
    const value = JSON.parse(`"${text}"`);
    return typeof value === "string" ? value : text;
  } catch {
    return text;
  }
}

// The rows of a context's grouped reading, computed once per payload: one per section, except
// sections touched by one JSON of the exact text (locally; a tool definition in chat mode),
// merged into one row whose margin
// stacks their labels (Qwen3.5's `<tools>`: the JSON syntax falls in the template). Never a
// merge across the « déjà lu » boundary, where the JSON stays text.
const readingCache = new WeakMap();
function readingRows(p, chat) {
  const cached = readingCache.get(p);
  if (cached) return cached;
  const offsets = [0];
  for (const segment of p.segments) offsets.push(offsets.at(-1) + segment.text.length);
  const sections = (p.sections ?? []).length ? p.sections : fallbackSections(p);
  const text = p.segments.map((s) => s.text).join("");
  const seenAt = offsets[p.seen_segments ?? 0];
  const spans = (chat ? toolSpans(text) : jsonSpans(text)).filter(([a, b]) => !(a < seenAt && seenAt < b));
  const from = (s) => offsets[s.start];
  const to = (s) => offsets[s.end];
  const joined = new Array(sections.length).fill(false); // section k shares a row with k + 1
  for (const [a, b] of spans) {
    let k = sections.findIndex((s) => to(s) > a);
    if (k < 0) continue;
    while (k + 1 < sections.length && from(sections[k + 1]) < b) joined[k++] = true;
  }
  const rows = [];
  let group = [];
  sections.forEach((section, k) => {
    group.push(section);
    if (joined[k]) return;
    const start = group[0].start;
    const end = group.at(-1).end;
    const [a, b] = [offsets[start], offsets[end]];
    rows.push({ sections: group, start, end, from: a, to: b, seen: group[0].seen, json: spans.filter(([x, y]) => x >= a && y <= b) });
    group = [];
  });
  const reading = { rows, offsets, text };
  readingCache.set(p, reading);
  return reading;
}

function readPart(call, turn, chat) {
  const p = call.context;
  const part = el("div", "ctx-read");
  part.appendChild(el("h4", "ctx-part-title", t("main.ctx.read_title")));
  const reading = readingRows(p, chat);
  const seen = p.seen_segments ?? 0;
  if (seen > 0) {
    // What the previous call of this context read already, folded (its key remembered).
    const key = `seen:${call.id}`;
    const details = el("details", "ctx-seen");
    details.open = store.openSeen.has(key);
    const seenRows = reading.rows.filter((r) => r.seen);
    const k = seenRows.length; // the rows shown inside the fold, JSON merges included
    const summary = el("summary", "", t("main.ctx.seen", { count: k, tokens: p.seen_tokens }));
    summary.dataset.focusKey = key;
    details.appendChild(summary);
    details.addEventListener("toggle", () => {
      if (details.open) store.openSeen.add(key);
      else store.openSeen.delete(key);
    });
    for (const row of seenRows) details.appendChild(sectionRow(p, reading, row, call, turn, chat, false));
    part.appendChild(details);
  }
  for (const row of reading.rows.filter((r) => !r.seen)) {
    part.appendChild(sectionRow(p, reading, row, call, turn, chat, seen > 0));
  }
  return part;
}

// The DESIGN.md colour token of a segment type (its gauge group), for the swatch.
function kindColor(p, kind) {
  const group = p.breakdown.find((item) => item.kinds.includes(kind))?.group ?? kind;
  return GROUP_COLORS[group] || "--color-muted";
}

const tokensFr = (n, estimated) => `${approx(estimated)}${t("common.count.token", { count: n })}`;

function sectionLabel(s) {
  const count = s.end - s.start;
  const brick = s.brick ? brickName(s.brick) : t("main.ctx.no_brick");
  // « Prompt système · Prompt système », « Extraits RAG · RAG »: the brick said once.
  const source = s.brick && s.label_text.toLowerCase().includes(brick.toLowerCase()) ? "" : ` · ${brick}`;
  return (
    `${s.label_text}${source} · ${tokensFr(s.tokens, s.estimated)}` +
    (s.template_tokens ? ` ${t("main.ctx.of_template", { tokens: s.template_tokens })}` : "") +
    (count > 1 ? ` · ${t("common.count.segment", { count })}` : "")
  );
}

// One row: the margin (discipline rule, type swatch, label and tokens of each section), then
// the continuous text, one span per segment (its label and tokens in the tooltip). The margin
// is the row's one control (a button, `aria-pressed`, named short): the text stays plain
// readable content, and the row's own controls (JSON, compression) are never nested in it.
function sectionRow(p, reading, row, call, turn, chat, marked) {
  const node = el("div", "ctx-section");
  const segments = p.segments.slice(row.start, row.end);
  node.dataset.discipline = row.sections.find((s) => s.discipline && s.discipline !== "neutral")?.discipline ?? "neutral";
  node.style.setProperty("--segment-color", `var(${kindColor(p, row.sections[0].kind)})`);
  // Story 34: its segments' bricks and components, and its own call; its margin selects it.
  setLinks(node, [...segments.flatMap((s) => [s.brick, s.component]), `call:${call.id}`]);
  const id = `section:${call.id}:${row.start}`;
  const margin = el("div", "ctx-section-margin");
  if (marked) {
    node.classList.add("is-new");
    margin.appendChild(el("span", "ctx-new-badge", t("main.ctx.new")));
  }
  const control = el("button", "ctx-section-select");
  control.type = "button";
  control.dataset.focusKey = id;
  for (const section of row.sections) {
    const label = el("span", "ctx-section-label");
    label.style.setProperty("--segment-color", `var(${kindColor(p, section.kind)})`);
    const swatch = el("span", "swatch");
    swatch.setAttribute("aria-hidden", "true");
    label.append(swatch, el("span", "", sectionLabel(section)));
    control.appendChild(label);
    // A section over several components (the tools of one brick) names them.
    const components = [
      ...new Set(p.segments.slice(section.start, section.end).map((s) => s.component).filter(Boolean)),
    ];
    if (components.length > 1) control.appendChild(el("span", "ctx-section-components", components.join(", ")));
  }
  const first = row.sections[0];
  selectOnActivate(control, id, `${first.label_text} · ${tokensFr(first.tokens, first.estimated)}${row.sections.length > 1 ? ` ${t("main.ctx.and_more", { more: row.sections.length - 1 })}` : ""}`);
  margin.appendChild(control);
  const main = el("div", "ctx-section-main");
  const pre = el("pre", "ctx-section-text");
  if (chat) appendChatText(pre, p, reading, row, call);
  else appendLocalText(pre, p, reading, row, call);
  main.appendChild(pre);
  for (const segment of segments) {
    if (!segment.compressed_from) continue;
    // Story 20: a compressed segment, and what it was before (AD-22).
    const was = segment.compressed_from;
    const tokens = `${approx(was.estimated)}${t("main.ctx.tokens", { tokens: was.tokens_before })}`;
    node.classList.add("ctx-compressed");
    margin.appendChild(el("span", "ctx-compressed-badge", `🗜️ ${t("main.ctx.compressed_badge", { tokens })}`));
    const text = textBefore(turn, was);
    if (text !== null) {
      const key = `before:${call.id}:${segment.id}`; // its unfolding kept like the other folds
      const before = el("details");
      before.open = store.openExact.has(key);
      before.addEventListener("toggle", () => {
        if (before.open) store.openExact.add(key);
        else store.openExact.delete(key);
      });
      const summary = el("summary", "", t("main.ctx.before_compression", { tokens }));
      summary.dataset.focusKey = key;
      before.append(summary, el("pre", "", text));
      main.appendChild(before);
    }
  }
  node.append(margin, main);
  return node;
}

function segmentSpan(segment, text) {
  const span = el("span", segment.kind === "template" ? "ctx-seg is-template" : "ctx-seg", text);
  span.dataset.segmentId = segment.id;
  span.title = `${segment.label_text} · ${tokensFr(segment.tokens, segment.estimated)}`;
  return span;
}

// Locally: the exact text of the row, each JSON found replaced by its tree (its exact text a
// click away), the rest one span per segment piece.
function appendLocalText(pre, p, reading, row, call) {
  const { offsets, text } = reading;
  const plain = (a, b) => {
    for (let k = row.start; k < row.end; k++) {
      const x = Math.max(a, offsets[k]);
      const y = Math.min(b, offsets[k + 1]);
      if (x < y) pre.appendChild(segmentSpan(p.segments[k], text.slice(x, y)));
    }
  };
  let at = row.from;
  for (const [a, b, value] of row.json) {
    plain(at, a);
    pre.appendChild(jsonBlock(value, text.slice(a, b), `${call.id}:${a}`));
    at = b;
  }
  plain(at, row.to);
}

// Chat mode: the JSON syntax (template) in ink-soft, each fragment decoded (a template piece
// inside a string too, the `\n\n` between two parts; JSON syntax stays as sent), and a tree
// when the fragment is itself JSON (a tool result, arguments). A tool definition found by
// `toolSpans` is replaced by its tree, as locally.
function appendChatText(pre, p, reading, row, call) {
  const { text } = reading;
  let at = row.from;
  for (const [a, b, value] of row.json) {
    appendChatPieces(pre, p, reading, row, call, at, a);
    pre.appendChild(jsonBlock(value, text.slice(a, b), `${call.id}:${a}`));
    at = b;
  }
  appendChatPieces(pre, p, reading, row, call, at, row.to);
}

// The row's segments between `from` and `to`, each decoded; a segment cut by a tree keeps
// only its decoded piece.
function appendChatPieces(pre, p, reading, row, call, from, to) {
  const { offsets } = reading;
  for (let k = row.start; k < row.end; k++) {
    const segment = p.segments[k];
    const x = Math.max(from, offsets[k]);
    const y = Math.min(to, offsets[k + 1]);
    if (x >= y) continue;
    if (segment.kind === "template" || y - x < segment.text.length) {
      pre.appendChild(segmentSpan(segment, decodeFragment(segment.text.slice(x - offsets[k], y - offsets[k]))));
      continue;
    }
    const decoded = decodeFragment(segment.text);
    const trimmed = decoded.trim();
    const value = /^[[{]/.test(trimmed) ? parseJson(trimmed) : undefined;
    if (value !== undefined && treeWorthy(value, trimmed.length)) {
      const block = jsonBlock(value, segment.text, `${call.id}:${reading.offsets[k]}`);
      block.dataset.segmentId = segment.id;
      pre.appendChild(block);
    } else {
      pre.appendChild(segmentSpan(segment, decoded));
    }
  }
}

// A JSON of the context: its tree, and « Texte exact », the substring sent.
function jsonBlock(value, exact, key) {
  const block = el("span", "ctx-json");
  const exactKey = `jsonexact:${key}`;
  const shown = store.openExact.has(exactKey);
  const toggle = el("button", "ctx-json-exact-toggle", t("main.ctx.modes.exact"));
  toggle.type = "button";
  toggle.dataset.focusKey = exactKey;
  toggle.setAttribute("aria-pressed", String(shown));
  const raw = el("span", "ctx-json-exact", exact);
  raw.hidden = !shown;
  toggle.addEventListener("click", () => {
    const on = !store.openExact.has(exactKey);
    if (on) store.openExact.add(exactKey);
    else store.openExact.delete(exactKey);
    toggle.setAttribute("aria-pressed", String(on));
    raw.hidden = !on;
  });
  block.append(toggle, jsonTree(value, key), raw);
  return block;
}

// A JSON tree in native JS (no library, AD-18): a `details` per object or array, the root
// open and the others folded by default (lot 1 of 2026-10-04), its folding kept by key; keys, strings and literals in their classes.
function jsonTree(value, key) {
  const tree = el("span", "json-tree");
  tree.appendChild(jsonNode(value, undefined, `json:${key}`, true, true));
  return tree;
}

function jsonNode(value, name, path, last, root = false) {
  const head = [];
  if (typeof name === "string") head.push(el("span", "json-key", JSON.stringify(name)), el("span", "json-punct", ": "));
  const comma = () => (last ? [] : [el("span", "json-punct", ",")]);
  if (value !== null && typeof value === "object") {
    const isArray = Array.isArray(value);
    const entries = isArray ? value.map((v, i) => [i, v]) : Object.entries(value);
    const [open, close] = isArray ? ["[", "]"] : ["{", "}"];
    if (!entries.length) {
      const leaf = el("span", "json-leaf");
      leaf.append(...head, el("span", "json-punct", `${open}${close}`), ...comma());
      return leaf;
    }
    const node = el("details", "json-node");
    // Open by default: the root only; `jsonToggled`, the paths whose state the user inverted.
    node.open = root !== store.jsonToggled.has(path);
    node.addEventListener("toggle", () => {
      if (node.open !== root) store.jsonToggled.add(path);
      else store.jsonToggled.delete(path);
    });
    const summary = el("summary", "json-summary");
    summary.dataset.focusKey = path;
    const count = entries.length;
    const noun = isArray ? t("main.ctx.json_items", { count }) : t("main.ctx.json_keys", { count });
    summary.append(...head, el("span", "json-punct", open), el("span", "json-folded", ` … ${close} ${noun}`));
    const children = el("span", "json-children");
    entries.forEach(([k, v], i) => {
      children.appendChild(jsonNode(v, isArray ? undefined : k, `${path}/${encodeURIComponent(k)}`, i === count - 1));
    });
    const end = el("span", "json-close");
    end.append(el("span", "json-punct", close), ...comma());
    node.append(summary, children, end);
    return node;
  }
  const leaf = el("span", "json-leaf");
  const literal = typeof value === "string" ? el("span", "json-string", jsonString(value)) : el("span", "json-literal", JSON.stringify(value));
  leaf.append(...head, literal, ...comma());
  return leaf;
}

// A string of the tree, quoted and escaped, except its line breaks, shown as such (an MCP
// tool's documentation spans lines); « Texte exact » keeps the `\n`.
function jsonString(value) {
  return `"${value
    .split("\n")
    .map((line) => JSON.stringify(line).slice(1, -1))
    .join("\n")}"`;
}

// « Corps JSON » (chat mode): the body sent, as a tree.
function bodyPart(call) {
  const part = el("div", "ctx-read ctx-body");
  part.appendChild(el("h4", "ctx-part-title", t("main.ctx.body_sent")));
  const value = parseJson(call.context.body ?? "");
  part.appendChild(value === undefined ? el("pre", "ctx-exact", call.context.body ?? "") : jsonTree(value, `body:${call.id}`));
  return part;
}

// « Texte exact »: the join of the segments (the prompt sent, AD-4; the body in chat mode),
// then the raw output, without colour nor margin. An earlier call's text is folded.
function exactParts(call, owner, last, turn) {
  const p = call.context;
  const exact = el("pre", "ctx-exact", isChat(p) ? p.body : p.segments.map((s) => s.text).join(""));
  const nodes = [];
  if (last) {
    nodes.push(el("h4", "ctx-part-title", t("main.ctx.exact_read")), exact);
  } else {
    const key = `exact:${call.id}`;
    const details = el("details", "ctx-exact-fold");
    details.open = store.openExact.has(key);
    const summary = el("summary", "", t("main.ctx.exact_read_fold", { tokens: `${approxTotal(p)}${fmt(p.used)}` }));
    summary.dataset.focusKey = key;
    details.addEventListener("toggle", () => {
      if (details.open) store.openExact.add(key);
      else store.openExact.delete(key);
    });
    details.append(summary, exact);
    nodes.push(details);
  }
  nodes.push(el("h4", "ctx-part-title", t("main.ctx.raw_title")));
  let raw;
  if (call.ended) raw = el("pre", "ctx-raw", call.ended.raw_output);
  else if (last && owner.overflow) raw = el("pre", "ctx-raw", t("main.ctx.no_call_overflow"));
  else if (last && call.startedAt != null) {
    // Only once its `model_call_started` came: before, the deltas are the previous call's.
    raw = el("pre", "ctx-raw", owner.reasoning + owner.text || "…");
    ctxLive = { ...(ctxLive ?? { owner }), raw };
  } else raw = el("pre", "ctx-raw", ctxRunning(owner, turn) ? "…" : "");
  nodes.push(raw);
  return nodes;
}

// ---- « Produit » : what the call itself produced, on its own background ----

function producedBlock(className, kind, links) {
  const block = el("div", `ctx-produced ${className}`);
  block.dataset.discipline = "model";
  setLinks(block, links);
  const head = el("div", "ctx-produced-head");
  head.append(el("span", "ctx-produced-tag", t("main.ctx.produced.tag")), el("span", "ctx-produced-kind", kind));
  block.appendChild(head);
  return block;
}

// Chat mode's `arguments` is the JSON string the provider emitted: decoded for the tree.
function decodeArguments(args) {
  if (typeof args !== "string") return args;
  try {
    return JSON.parse(args);
  } catch {
    return args;
  }
}

// The turn (or the sub-agent) still running, its last call not answered yet.
const ctxRunning = (owner, turn) => turn.status === null && !owner.ended && !owner.overflow;

function producedPart(call, owner, turn, last) {
  const part = el("div", "ctx-produced-list");
  const ended = call.ended;
  if (!ended && last && owner.overflow) {
    part.appendChild(el("p", "ctx-produced-none", t("main.ctx.no_call_overflow")));
    return part;
  }
  // The running call: the live deltas, patched in place by `renderContext`; only once its
  // `model_call_started` came (a chat call may wait for its provider's pacing, and the
  // deltas held until then are the previous call's).
  const live = !ended && last && call.startedAt != null;
  if (!ended && !live) {
    // Not sent yet: a note while it waits, nothing once the turn stopped.
    if (last && ctxRunning(owner, turn)) {
      part.appendChild(el("p", "ctx-produced-none", t("main.ctx.produced.waiting_send")));
    }
    return part;
  }
  if (live) ctxLive = { ...(ctxLive ?? {}), owner };
  const reasoning = ended ? ended.reasoning : owner.reasoning;
  const text = ended ? ended.text : owner.text;
  const links = [`call:${call.id}`];
  if (reasoning) {
    // FR-9: always here, whatever the Vue humain option says; folded by default.
    const block = producedBlock("is-reasoning", t("main.ctx.produced.reflection"), [...links, "reasoning"]);
    const details = reasoningBlock(reasoning, `ctx:${call.id}`, t("main.ctx.produced.show_reasoning"));
    block.appendChild(details);
    part.appendChild(block);
    if (live) ctxLive.reasoning = details.querySelector(".reasoning-text");
  }
  // Lot C: the harness closed the reasoning at its budget and relaunched the same call.
  if (call.cut) part.appendChild(el("p", "ctx-harness-note", `⚙ ${t("main.ctx.produced.harness_note", { message: call.cut.message_text })}`));
  if (text) {
    const block = producedBlock("is-answer", t("main.ctx.produced.answer"), links);
    const pre = el("pre", "ctx-produced-text", text);
    block.appendChild(pre);
    part.appendChild(block);
    if (live) ctxLive.answer = pre;
  }
  (ended?.tool_calls ?? []).forEach((toolCall, i) => {
    const block = producedBlock("is-tool-call", t("main.ctx.produced.tool_call"), links);
    block.appendChild(jsonTree({ name: toolCall.name, arguments: decodeArguments(toolCall.arguments) }, `tool:${call.id}:${i}`));
    part.appendChild(block);
  });
  // A malformed tool call reaches no `tool_calls`: its raw output is what the model produced.
  const malformed = stepsAfter(owner, call).some((s) => s.type === "tool_call_malformed");
  if (ended?.raw_output && (malformed || !part.childElementCount)) {
    const block = producedBlock("is-answer is-raw", malformed ? t("main.ctx.produced.raw_malformed") : t("main.ctx.produced.raw"), links);
    block.appendChild(el("pre", "ctx-produced-text", ended.raw_output));
    part.appendChild(block);
  }
  if (!part.childElementCount) {
    part.appendChild(el("p", "ctx-produced-none", live && ctxRunning(owner, turn) ? t("main.ctx.produced.waiting_output") : t("main.ctx.produced.none")));
  }
  return part;
}

// Between two calls: what the harness ran (only the tools that started), what it refused
// (a malformed call, a call blocked by a hook), and that the next call reads it; for a
// delegation, the sub-agent's tab.
function betweenLine(owner, turn, call, next, nextNumber) {
  const steps = stepsAfter(owner, call);
  const tools = steps.filter((s) => s.type === "tool");
  const names = [
    ...new Set(tools.map((s) => (s.started.tool === "delegate" ? t("main.ctx.between.delegation") : toolLabel(s.started.tool)))),
  ];
  const blocked = steps.filter((s) => s.type === "hook" && s.payload.decision === "block");
  const malformed = steps.some((s) => s.type === "tool_call_malformed");
  const parts = [];
  if (names.length) parts.push(t("main.ctx.between.runs", { tools: joinList(names) }));
  if (blocked.length) {
    parts.push(t("main.ctx.between.refuses", { count: blocked.length, hooks: joinList(blocked.map((s) => s.payload.hook_text)) }));
  }
  if (malformed) parts.push(t("main.ctx.between.refuses_malformed"));
  const nextCall = String(nextNumber);
  let text;
  if (!parts.length) text = t("main.ctx.between.relaunch", { call: nextCall });
  else if (names.length && parts.length === 1) text = t("main.ctx.between.result_read", { action: parts[0], call: nextCall });
  else if (names.length) text = t("main.ctx.between.results_read", { actions: joinList(parts), call: nextCall });
  else text = t("main.ctx.between.refusal_read", { actions: joinList(parts), call: nextCall });
  const line = el("div", "ctx-between");
  line.appendChild(el("p", "", `⚙ ${text}`));
  if (owner === turn) {
    for (const step of tools.filter((s) => s.sub?.context)) {
      const show = el("button", "subagent-show", t("main.ctx.between.show_subagent", { id: step.sub.contextId }));
      show.type = "button";
      show.dataset.focusKey = `ctxsub:${step.sub.contextId}`;
      show.addEventListener("click", () => showSubContext(turn.id, step.sub.contextId));
      line.appendChild(show);
    }
  }
  return line;
}

// Story 20: the text a compressed segment had before, kept once by its compression step.
function textBefore(turn, was) {
  const step = turn?.steps.find((s) => s.type === "compression" && s.stepId === was.step_id);
  return step?.ended?.items[was.item]?.text_before ?? null;
}

// Story 19 (EXPERIENCE: Sous-agent au travail), story 22 (M6): tabs, `aria-selected` on the
// one shown. No arrow-key navigation: every tab stays in the Tab order.
function ctxViewSwitch(turn, subs, view) {
  const bar = el("div", "ctx-view-switch");
  bar.setAttribute("role", "tablist");
  bar.setAttribute("aria-label", t("main.ctx.view_label"));
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
  bar.appendChild(button(t("main.ctx.main_agent"), null, !view));
  for (const sub of subs) bar.appendChild(button(t("main.ctx.subagent", { id: sub.contextId }), sub.contextId, view === sub));
  return bar;
}

// ---------- turn comparison (story 9b, EXPERIENCE.md turn-compare) ----------

// Story 22: the rail's name of a turn, its rank in the conversation shown (back to 1 after
// « Vider la conversation » or « Réinitialiser »); its id `t{n}` stays unique in the journal.
const turnNumber = (turn) => {
  const i = shownTurns().indexOf(turn);
  return i < 0 ? null : i + 1;
};
const turnName = (turn) => (turnNumber(turn) ? t("main.turn.name", { n: String(turnNumber(turn)) }) : turn.id);
// Inside a sentence (« Rejeu du tour 2 »).
const turnNameLower = (turn) => (turnNumber(turn) ? t("main.turn.name_inline", { n: String(turnNumber(turn)) }) : turn.id);
const turnIdTitle = (turn) => t("main.turn.id_title", { id: turn.id });

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
  if (!brick) return t("main.compare.no_brick");
  return store.bricks?.bricks?.find((b) => b.id === brick)?.label_text ?? brick;
}

const signed = (n, unit) => `${n > 0 ? "+" : n < 0 ? "−" : "±"}${unit(Math.abs(n))}`;

function compareCell(turn, group, other) {
  const cell = el("div", "turn-compare-cell");
  if (!group) {
    const delta = other ? ` (${t("main.ctx.tokens", { tokens: signed(-other.tokens, fmt) })})` : "";
    cell.append(el("p", "empty-note", t("main.compare.absent", { turn: turnName(turn), delta })));
    return cell;
  }
  const first = group.segments[0];
  const colorGroup = turn.context.breakdown.find((item) => item.kinds.includes(first.kind))?.group;
  cell.style.setProperty("--segment-color", `var(${GROUP_COLORS[colorGroup] || "--color-muted"})`);
  cell.dataset.discipline = first.discipline || "neutral"; // story 33
  cell.classList.add("ctx-segment");
  const label = el("div", "ctx-segment-label");
  const delta = other === undefined ? "" : ` (${t("main.ctx.tokens", { tokens: signed(group.tokens - (other?.tokens ?? 0), fmt) })})`;
  label.append(el("span", "swatch"), `${turnName(turn)} · ${t("main.ctx.tokens", { tokens: group.tokens })}${delta}`);
  const details = el("details");
  details.append(el("summary", "", t("main.compare.full_text", { segments: String(group.segments.length) })));
  for (const segment of group.segments) {
    details.append(el("div", "ctx-segment-label", `${segment.label_text} · ${t("main.ctx.tokens", { tokens: segment.tokens })}`));
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
  head.append(el("h3", "ctx-heading", t("main.compare.title")));
  for (const [side, label] of [["left", t("main.compare.left")], ["right", t("main.compare.right")]]) {
    const select = el("select");
    select.setAttribute("aria-label", label);
    select.dataset.focusKey = `compare:${side}`;
    for (const turn of turns) {
      const option = el("option", "", `${turnName(turn)}${turn.replayOf ? ` ${t("main.compare.replay_suffix")}` : ""} · ${quote(turn.message)}`);
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
  const close = el("button", "pane-text-action", t("common.close"));
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
  const time = (ms) => (ms === null ? t("main.ctx.call_state.running") : seconds(ms));
  for (const [turn, figures, other] of [[left, a, null], [right, b, a]]) {
    const card = el("div", "turn-compare-figures");
    card.append(el("div", "turn-group-title", `${turnName(turn)}${turn.replayOf ? ` · ${t("main.chat.replay_badge")}` : ""}`));
    card.append(el("div", "turn-compare-model", t("main.chat.model_line", { model: turn.model?.label ?? t("main.compare.unknown_model") })));
    const diff = (key, unit) =>
      other && figures[key] !== null && other[key] !== null ? ` (${signed(figures[key] - other[key], unit)})` : "";
    card.append(
      el("div", "number", t("main.compare.input", { tokens: figures.input, diff: diff("input", fmt) })),
      el("div", "number", t("main.compare.output", { tokens: figures.output, diff: diff("output", fmt) })),
      el("div", "number", t("main.compare.time", { time: time(figures.duration), diff: diff("duration", seconds) }))
    );
    grid.append(card);
  }
  const [ga, gb] = [brickGroups(left), brickGroups(right)];
  for (const brick of new Set([...ga.keys(), ...gb.keys()])) {
    grid.append(el("h4", "turn-compare-brick", brickName(brick)));
    grid.append(compareCell(left, ga.get(brick)), compareCell(right, gb.get(brick), ga.get(brick) ?? null));
  }
  if (!ga.size && !gb.size) grid.append(el("p", "empty-note", t("main.compare.no_context")));
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
  return [el("p", "", t("main.orch.catalog", { count, tokens }))];
}

function callBody(turn, step) {
  const context = step.context;
  const ended = step.ended;
  const counter = el("div", "token-counter number");
  if (ended) {
    // FR-30, FR-43: the rate (tokens/s) from the session; « ≈ » on what was estimated.
    const guess = approx(ended.usage_source === "estimate");
    const rate = ended.output_tps != null ? ` · ${t("main.orch.call.rate", { tps: ended.output_tps })}` : "";
    counter.textContent = t("main.orch.call.ended", {
      input: `${guess}${fmt(ended.prompt_tokens)}`,
      output: `${guess}${fmt(ended.output_tokens)}`,
      time: seconds(ended.duration_ms),
      rate,
    });
  } else if (step.startedAt) {
    const input = `${context ? approxTotal(context) : ""}${fmt(context?.used ?? 0)}`;
    counter.append(`${t("main.orch.call.running", { input })} `, tick(step.startedAt), ` ${t("main.orch.call.running_suffix")}`);
  } else {
    counter.textContent = t("main.orch.call.input", { input: `${context ? approxTotal(context) : ""}${fmt(context?.used ?? 0)}` });
  }
  const nodes = [el("p", "label", t("main.orch.call.label", { id: step.id ?? turn.id })), counter];
  // FinOps: a cloud call with declared prices; never for a local model.
  if (ended?.cost_in_usd != null) nodes.push(el("div", "token-counter number", costText(ended)));
  // GreenOps: its footprint (cloud: EcoLogits, local: CodeCarbon), or « indisponible ».
  const footprint = footprintNode(ended);
  if (footprint) nodes.push(footprint);
  if (ended && ended.stop_reason !== "stop") {
    nodes.push(el("span", "step-badge", section("main.orch.call.stop_reasons")[ended.stop_reason]));
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
  if (step.brick === "skills") nodes.push(el("span", "step-badge is-skill", t("main.orch.skill_badge")));
  if (step.brick === "global_memory") nodes.push(el("span", "step-badge is-memory", t("main.memory.title")));
  // EXPERIENCE: trigger badge, read from the envelope's `trigger` (story 9).
  const badge = triggerBadge(step.trigger);
  if (badge) nodes.push(badge);
  const asked = { name: step.started.tool, arguments: step.started.arguments };
  nodes.push(el("pre", "step-code", formatCall(asked)));
  for (const request of step.outbound || []) nodes.push(outboundPayload(request));
  if (!ended) {
    const running = el("div", "token-counter number", `${t("common.in_progress")} `);
    running.appendChild(tick(step.startedAt));
    nodes.push(running);
    return nodes;
  }
  nodes.push(el("div", "token-counter number", t("main.orch.time", { time: seconds(ended.duration_ms) })));
  if (ended.status === "ok") {
    const cut = ended.truncated;
    if (cut) {
      // Lot B (N3): the harness cut a network or MCP result before the model read it.
      const approx = cut.estimated ? "≈ " : "";
      nodes.push(el("p", "", t("main.orch.tool.truncated", { tokens: `${approx}${fmt(cut.tokens)}`, total: `${approx}${fmt(cut.total_tokens)}` })));
    }
    nodes.push(el("p", "label", t("main.orch.tool.result")), el("pre", "step-code", ended.result));
    for (const write of step.memoryWrites || []) {
      // Story 14: what the harness wrote in memory.json, the model having only asked.
      nodes.push(el("p", "label", t("main.orch.tool.memory_written")), el("pre", "step-code", write.text));
    }
  } else {
    nodes.push(
      el("span", "step-badge", t("main.orch.tool.error_badge")),
      el("p", "", t("main.orch.tool.error", { error: ended.error_text }))
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
    nodes.push(el("div", "token-counter number", t("main.orch.connect.running")));
    return nodes;
  }
  nodes.push(el("div", "token-counter number", t("main.orch.time", { time: seconds(ended.duration_ms) })));
  if (ended.status === "ok") {
    const count = ended.tools.length;
    nodes.push(el("p", "label", t("main.orch.connect.found", { count: String(count) })));
    if (count) nodes.push(el("pre", "step-code", ended.tools.join("\n")));
  } else {
    nodes.push(el("span", "step-badge", t("main.orch.connect.unavailable")), el("p", "", ended.error_text));
  }
  return nodes;
}

function overflowCard(overflow) {
  const card = el("div", "overflow-card");
  card.append(
    el("h3", "", `⚠ ${t("main.orch.overflow.title")}`),
    el("p", "number", t("main.orch.overflow.figures", { used: overflow.used, usable: overflow.usable })),
    el("p", "", overflow.message_text),
    el("p", "label", t("main.orch.overflow.strategies"))
  );
  const list = el("ul");
  for (const strategy of overflow.strategies_text) list.appendChild(el("li", "", strategy));
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
  // Story 23: « Données sortantes », the name the user looks for and the event log's.
  const head = el("summary", "outbound-head");
  head.append(
    el("span", "outbound-tag", `🌐 ${t("main.hosting.network")}`),
    " · ",
    el("span", "outbound-label", t("main.outbound.label")),
    " ",
    el("span", "outbound-address", `${request.method} ${request.url}`)
  );
  const body = el("div", "outbound-body");
  body.append(
    el("p", "outbound-section", t("main.outbound.request")),
    el("pre", "step-code", `${request.method} ${request.url}`),
    el("p", "outbound-section", t("main.outbound.headers"))
  );
  if (Array.isArray(request.headers)) {
    // As the session traced them (AD-2): a value outside its allow-list arrives masked.
    const lines = el("pre", "step-code outbound-headers");
    request.headers.forEach((header, index) => {
      if (index) lines.append("\n");
      lines.append(`${header.name}: `);
      if (header.masked) {
        const masked = el("span", "outbound-masked", header.value);
        masked.title = t("main.outbound.masked");
        lines.append(masked);
      } else {
        lines.append(header.value);
      }
    });
    // An event traced before story 23 carries none: nothing says what was sent.
    if (!request.headers.length) lines.textContent = t("main.outbound.headers_not_traced");
    body.append(lines);
    if (request.headers.some((header) => header.masked)) body.append(el("p", "outbound-note", t("main.outbound.masked_note")));
  } else {
    // The H5 preview: headers are set by the HTTP client when sending, after the decision.
    body.append(el("p", "outbound-note", t("main.outbound.headers_at_send")));
  }
  body.append(
    el("p", "outbound-section", t("main.outbound.body")),
    el("pre", "step-code", request.body || t("main.outbound.no_body"))
  );
  details.append(head, body);
  return details;
}

// Story 15: a score with two decimals, in the language's style (« 0,82 », « 0.82 »).
const scoreFormat = () => intlNumber({ minimumFractionDigits: 2, maximumFractionDigits: 2 });

function ragBody(step) {
  // The query, where the excerpts go, then rank, document, score and foldable text; a click on
  // an excerpt selects the retriever in the schema (CAP-4).
  const ended = step.ended;
  const nodes = [el("p", "label", t("main.orch.rag.query")), el("pre", "step-code", step.started.query)];
  if (!ended) {
    const running = el("div", "token-counter number", `${step.started.phase_label} `);
    running.appendChild(tick(step.startedAt));
    nodes.push(running);
    return nodes;
  }
  nodes.push(el("p", "", t("main.orch.rag.placement", { placement: ended.placement_text })));
  // Story 16: the reranking enabled, but not applied to this turn, and why.
  if (ended.rerank_skipped_text) nodes.push(el("p", "bubble-note", ended.rerank_skipped_text));
  nodes.push(el("div", "token-counter number", t("main.orch.time", { time: seconds(ended.duration_ms) })));
  if (ended.status === "error") {
    nodes.push(el("span", "step-badge", t("main.orch.error")), el("p", "", ended.error_text));
    return nodes;
  }
  const list = el("ol", "rag-excerpts");
  for (const excerpt of ended.excerpts) {
    const item = el("li", "rag-excerpt");
    const details = el("details");
    const head = el("summary", "rag-excerpt-head");
    head.append(
      el("span", "rag-rank", `#${excerpt.position}`),
      el("span", "rag-doc", excerpt.title_text),
      el("span", "rag-score number", scoreFormat().format(excerpt.score))
    );
    head.title = t("main.orch.rag.excerpt_title");
    head.addEventListener("click", () => setSelection(step.component || "rag.retriever"));
    details.append(head, el("pre", "step-code", excerpt.text));
    item.appendChild(details);
    list.appendChild(item);
  }
  nodes.push(el("p", "label", t("main.orch.rag.excerpts")), list);
  return nodes;
}

// Story 16: the order before and after reranking, side by side; the kept ones first.
function rerankKept(keep) {
  return t("main.orch.rerank.kept", { count: keep });
}

function rerankBody(step) {
  const ended = step.ended;
  const nodes = [el("p", "label", t("main.orch.rag.query")), el("pre", "step-code", step.started.query)];
  if (!ended) {
    const done = step.progress ? ` ${step.progress.done} / ${step.progress.total} ` : " ";
    const running = el("div", "token-counter number", `${step.started.phase_label}${done}`);
    running.appendChild(tick(step.startedAt));
    nodes.push(running);
    return nodes;
  }
  nodes.push(el("p", "", t("main.orch.rag.placement", { placement: ended.placement_text })));
  nodes.push(el("div", "token-counter number", t("main.orch.time", { time: seconds(ended.duration_ms) })));
  if (ended.status === "cancelled") {
    nodes.push(el("span", "step-badge", t("main.orch.stopped")), el("p", "", ended.error_text));
    return nodes;
  }
  if (ended.status === "error") {
    nodes.push(el("span", "step-badge", t("main.orch.error")), el("p", "", ended.error_text));
    return nodes;
  }
  const texts = new Map((step.search?.ended?.excerpts ?? []).map((e) => [e.chunk_id, e.text]));
  const select = () => setSelection(step.component || "rag.reranker");
  const kept = (excerpt) => excerpt.position <= ended.keep;
  const keepTag = (excerpt) => el("span", "rerank-keep", kept(excerpt) ? t("main.orch.rerank.kept_tag") : t("main.orch.rerank.dropped_tag"));
  const before = [...ended.excerpts].sort((a, b) => a.before - b.before);
  const columns = el("div", "rerank-columns");
  const beforeList = el("ol", "rerank-list rerank-before");
  for (const excerpt of before) {
    const item = el("li", `rerank-item${kept(excerpt) ? " is-kept" : " is-dropped"}`);
    item.append(
      el("span", "rag-rank", `#${excerpt.before}`),
      el("span", "rag-doc", excerpt.title_text),
      el("span", "rag-score number", scoreFormat().format(excerpt.retrieval_score)),
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
      el("span", "rag-doc", excerpt.title_text),
      el("span", "rag-score number", scoreFormat().format(excerpt.score)),
      keepTag(excerpt)
    );
    if (excerpt.truncated) head.append(el("span", "rerank-cut", t("main.orch.rerank.cut_tag")));
    head.title = t("main.orch.rerank.item_title", { rank: String(excerpt.before) });
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
    col(t("main.orch.rerank.before_column"), beforeList),
    col(t("main.orch.rerank.after_column"), afterList)
  );
  const cut = ended.excerpts.filter((e) => e.truncated).length;
  const notes = [t("main.orch.rerank.kept_note", { kept: rerankKept(ended.keep) })];
  if (cut) notes.push(t("main.orch.rerank.cut_note", { count: cut }));
  nodes.push(columns, ...notes.map((note) => el("p", "rerank-note", note)));
  return nodes;
}

// Story 20: « 1 240 → 310 tokens (−75 %) », the session's own sums (AD-1).
function compressionFigure(p) {
  const percent = p.tokens_before ? Math.round((100 * p.saved_tokens) / p.tokens_before) : 0;
  const mark = approx(p.estimated);
  return t("main.orch.compression.figure", { before: `${mark}${fmt(p.tokens_before)}`, after: `${mark}${fmt(p.tokens_after)}`, percent: String(percent) });
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
  const lines = [
    el("p", "", t("main.orch.compression.decision", { count: ended.items.length, compressor: ended.compressor_text })),
    el("div", "token-counter number", t("main.orch.compression.reduced", { figure: compressionFigure(ended), time: seconds(ended.duration_ms) })),
  ];
  const list = el("ol", "compression-items"); // each error once, under its own text
  for (const item of ended.items) {
    const entry = el("li", "compression-item");
    const head = el("button", "compression-item-head");
    head.type = "button";
    head.title = t("main.orch.compression.item_title");
    const mark = approx(ended.estimated);
    head.append(
      el("span", "compression-source", item.source_text),
      el(
        "span",
        "compression-tokens number",
        item.changed
          ? t("main.orch.compression.item_changed", { before: `${mark}${fmt(item.tokens_before)}`, after: `${mark}${fmt(item.tokens_after)}` })
          : t("main.orch.compression.item_unchanged", { before: `${mark}${fmt(item.tokens_before)}` })
      )
    );
    head.addEventListener("click", () => setSelection(step.component || "compression.compressor"));
    entry.appendChild(head);
    if (item.error_text) entry.appendChild(el("p", "bubble-note is-error", item.error_text));
    else if (!item.changed) entry.appendChild(el("p", "label", ended.unchanged_text));
    const before = el("details");
    before.append(el("summary", "", t("main.orch.compression.before", { tokens: `${mark}${fmt(item.tokens_before)}` })), el("pre", "step-code", item.text_before));
    entry.appendChild(before);
    if (item.changed) {
      const after = el("details");
      after.append(el("summary", "", t("main.orch.compression.after", { tokens: `${mark}${fmt(item.tokens_after)}` })), el("pre", "step-code", item.text_after));
      entry.appendChild(after);
    }
    list.appendChild(entry);
  }
  lines.push(list);
  const tone = ended.status === "error" ? "error" : "info";
  return [harnessEvent(t("main.orch.compression.title", { compressor: ended.compressor_text }), tone, lines)];
}

const HOOK_DECISIONS = section("main.orch.hook_decisions");
const APPROVAL_DECISIONS = section("main.orch.approval_decisions");

function toolLabel(name) {
  // Formatting only (AD-1): the label the bricks panel already shows for this tool.
  const option = (brickId, id) =>
    store.bricks?.bricks.find((b) => b.id === brickId)?.options?.find((o) => o.id === id);
  const native = option("tools", name);
  if (native) return native.label_text;
  const at = name.indexOf("__"); // an MCP tool: `server__tool`
  const server = at > 0 ? option("mcp", name.slice(0, at)) : null;
  return server ? `${name.slice(at + 2)} (${server.label_text})` : name;
}

function approvalDecision(resolved) {
  return `${APPROVAL_DECISIONS[resolved.decision]}${resolved.hook_disabled ? ` · ${t("main.orch.approval.h5_disabled")}` : ""}`;
}

function approvalCard(step) {
  // H5 in the Vue humain: tool, destination, what would leave the workstation, then the three
  // buttons while it waits, or the decision once answered (EXPERIENCE: human validation).
  const a = step.approval;
  const lines = [
    el("p", "", t("main.orch.approval.tool_destination", { tool: toolLabel(a.tool), destination: a.destination })),
    outboundPayload({ ...a.preview, seq: a.approval_id }, store.openApprovalPayloads),
  ];
  if (step.resolved) {
    lines.push(el("p", "", t("main.orch.approval.decision", { decision: approvalDecision(step.resolved) })));
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
          store.composerError = typeof body.detail === "string" ? body.detail : t("main.orch.approval.answer_refused");
          step.answering = false;
        }
      } catch {
        store.composerError = t("main.orch.approval.answer_no_answer");
        step.answering = false;
      }
      render();
    };
    const waiting = store.sessionState?.state === "awaiting_human";
    for (const [label, approved, disableHook, primary, key] of [
      [t("main.orch.approval.allow"), true, false, true, "allow"],
      [t("main.orch.approval.refuse"), false, false, false, "refuse"],
      [t("main.orch.approval.allow_always"), true, true, false, "allow-always"],
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
  const title = step.resolved ? t("main.orch.approval.title") : t("main.orch.approval.waiting");
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
    : t("main.orch.approval.waiting_answer");
  return [
    el("p", "", t("main.orch.approval.tool_destination", { tool: `${label}${label === a.tool ? "" : ` (${a.tool})`}`, destination: a.destination })),
    outboundPayload({ ...a.preview, seq: a.approval_id }),
    el("p", "", t("main.orch.approval.decision", { decision })),
  ];
}

function hookCard(step) {
  // EXPERIENCE: violet when the hook lets through, modifies or asks, red when it blocks.
  const p = step.payload;
  const block = p.decision === "block";
  const title = step.approval
    ? step.resolved
      ? t("main.orch.approval.title")
      : t("main.orch.approval.waiting")
    : block
      ? t("main.orch.hook.blocked_by", { hook: p.hook_text.toLowerCase() })
      : t("main.orch.hook.title", { point: p.point_text.toLowerCase() });
  const lines = [
    el("p", "", t("main.orch.hook.point", { point: p.point_text, hook: p.hook_text })),
    el("p", "", t("main.orch.hook.decision", { decision: HOOK_DECISIONS[p.decision], detail: p.detail_text })),
  ];
  const badge = triggerBadge(hookTrigger(step)); // on a tool call: forced or the model's
  if (badge) lines.unshift(badge);
  if (block) {
    const effect =
      p.point === "before_tool"
        ? t("main.orch.hook.effect_tool")
        : t("main.orch.hook.effect_turn");
    lines.push(el("p", "", effect));
  }
  if (step.approval) lines.push(...approvalTrace(step));
  if (step.lines.length) {
    lines.push(el("p", "label", t("main.orch.hook.audit_lines")), el("pre", "step-code", step.lines.join("\n")));
  }
  const origin = step.approval ? t("main.orch.decision_asked_by_harness") : t("main.orch.decision_by_harness");
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
      ? t("main.orch.malformed.retry")
      : t("main.orch.malformed.stop");
  return harnessEvent(t("main.orch.malformed.title"), "error", [
    el("p", "", t("main.orch.malformed.fault", { detail: p.detail_text })),
    el("p", "label", t("main.ctx.raw_title")),
    raw,
    el("p", "", reaction),
    el("p", "label", t("main.orch.decision_by_harness")),
  ]);
}

// ---------- orchestration rail (EXPERIENCE: turn-rail, turn-group, turn-step, harness-prep) ----------

// Each actor's class and icon; its name in `main.orch.actors`.
const ACTOR_STYLES = { model: ["is-model", "🤖"], harness: ["is-harness", "⚙"], user: ["is-user", "👤"] };
const ACTOR_NAMES = section("main.orch.actors");
const actorOf = (id) => [ACTOR_STYLES[id][0], `${ACTOR_STYLES[id][1]} ${ACTOR_NAMES[id]}`];
// The trigger badge of a line (story 9): class, icon, label (`main.trigger`).
const TRIGGER_STYLES = { user: ["trigger-badge-user", "👆 "], model: ["trigger-badge-model", "🤖 "] };
const TRIGGER_NAMES = section("main.trigger");
const triggerOf = (id) => (TRIGGER_STYLES[id] ? [...TRIGGER_STYLES[id], TRIGGER_NAMES[id]] : null);
const HOOK_ICONS = { h1: "🛡", h2: "📝", h3: "💉", h5: "✋" };
// A turn's status: its class, and its name in `main.orch.turn_status`.
const TURN_STATUS_CLASSES = {
  completed: "is-done",
  cancelled: "is-done",
  overflow: "is-failed",
  limit: "is-failed",
  blocked: "is-failed",
  error: "is-failed",
};
const TURN_STATUS_NAMES = section("main.orch.turn_status");
const turnStatusOf = (status) => (TURN_STATUS_CLASSES[status] ? [TURN_STATUS_CLASSES[status], TURN_STATUS_NAMES[status]] : undefined);
const LIMITS = section("main.orch.limits");
const APPROVAL_FIGURES = section("main.orch.approval_figures");
// Lot A: why the engine reads the context again (`prefix_not_reused.cause`); the full
// explanation is its `message_text`.
const PREFIX_CAUSES = section("main.orch.prefix_causes");
// Native providers 3/5 (CAP-5): why the provider threw a reasoning away.
const DROP_REASONS = section("main.log.drop_reasons");

// « 3 appels », « 1 appel »: `noun` names a pair of `common.count` (`call`, `tool`…).
function plural(count, noun) {
  return t(`common.count.${noun}`, { count });
}

// One line per step (DESIGN.md turn-step). A row: key (stable across renders), icon, title,
// actor, key figure, network host, tone, `sticky` (stays unfolded whatever happens), `quiet`
// (never unfolded as the live step), `sig` (the body is rebuilt only when it changes) and
// `body` (the former card's content).
function turnRows(turn) {
  const rows = [];
  const calls = turn.steps.filter((s) => s.type === "call");
  turn.steps.forEach((step, i) => {
    const from = rows.length;
    stepRows(turn, step, i, calls, rows);
    // Story 33: each new row's tile in its discipline (a sub-agent's rows already have theirs).
    // Story 34: its link keys, its step's brick and component, else the harness.
    for (const row of rows.slice(from)) {
      row.discipline ??= rowDiscipline(row, step);
      row.links ??= stepLinks(step);
    }
  });
  if (turn.overflow) {
    rows.push({
      key: `${turn.id}:overflow`,
      icon: "✖",
      title: turn.contextId ? t("main.orch.rows.sub_overflow") : t("main.orch.rows.overflow"),
      actor: "harness",
      discipline: "harness",
      links: ["core.harness"],
      figure: t("main.orch.overflow.figures", { used: turn.overflow.used, usable: turn.overflow.usable }),
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

// Story 34: a step's link keys, from its envelope (AD-1): its brick and its component; a step
// with neither is the harness's own.
function stepLinks(step) {
  const keys = [step.brick, step.component].filter(Boolean);
  return keys.length ? keys : ["core.harness"];
}

// Story 34: the bricks and components of the segments of one kind in a call's context.
const segmentLinks = (context, kind) =>
  (context?.segments || []).filter((s) => s.kind === kind).flatMap((s) => [s.brick, s.component]);

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
          title: t("main.orch.rows.catalog"),
          actor: "harness",
          links: segmentLinks(context, "tool_catalog"),
          figure: t("main.ctx.tokens", { tokens: catalog }),
          sig: catalog,
          body: () => catalogBody(context, catalog),
        });
      }
      if (index > 0 && results) {
        rows.push({
          key: `${key}:reinject`,
          icon: "↩",
          title: t("main.orch.rows.reinject"),
          actor: "harness",
          links: segmentLinks(context, "tool_result"),
          figure: `+${t("main.ctx.tokens", { tokens: results })}`,
          sig: results,
          body: () => [el("p", "", t("main.orch.rows.reinject_body", { tokens: results }))],
        });
      }
      const ended = step.ended;
      const last = index === calls.length - 1;
      const isFinal = catalog && ended && !ended.tool_calls.length && last && turn.status === "completed";
      let figure = t("main.orch.rows.read", { tokens: fmt(context?.used ?? 0) });
      if (ended) {
        const guess = approx(ended.usage_source === "estimate");
        figure = t("main.orch.rows.call_figure", {
          read: `${guess}${fmt(ended.prompt_tokens)}`,
          written: `${guess}${fmt(ended.output_tokens)}`,
          time: seconds(ended.duration_ms),
        });
        // Lot A: what the engine really evaluated, the tokens reused from its cache excluded.
        if (ended.evaluated_tokens != null) figure += ` · ${t("main.orch.rows.evaluated", { tokens: ended.evaluated_tokens })}`;
        const stopped = ["length", "cancelled"].includes(ended.stop_reason)
          ? section("main.orch.call.stop_reasons")[ended.stop_reason]
          : null;
        if (stopped) figure += ` · ${stopped}`;
      } else if (step.startedAt) {
        figure += ` · ${seconds(Date.now() - step.startedAt)}`;
      }
      rows.push({
        key: `${key}:call`,
        icon: isFinal ? "💬" : "🤖",
        title: isFinal ? t("main.orch.rows.answers") : t("main.orch.rows.calls_model"),
        actor: "model",
        // Story 34: a model out of the workstation: the call crosses the boundary.
        via: turn.model?.hosting === "network",
        discipline: "model",
        links: [`call:${step.id}`],
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
          title: t("main.orch.rows.asks_tool"),
          actor: "model",
          discipline: "model",
          links: [`call:${step.id}`],
          figure: asked.length > 1 ? plural(asked.length, "tool") : asked[0].name,
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
      let figure = `${t("main.orch.running")} · ${seconds(Date.now() - step.startedAt)}`;
      if (ended) {
        const outcome = ended.status === "ok" ? (ended.truncated ? `OK · ${t("main.orch.rows.truncated")}` : "OK") : t("main.orch.error");
        figure = `${outcome} · ${seconds(ended.duration_ms)}`;
      }
      const forced = step.trigger === "user";
      const net = step.outbound?.length ? hostOf(step.outbound[0].url) : null;
      rows.push({
        key,
        icon: harness ? { skills: "📘", global_memory: "💾" }[step.brick] || "📖" : "🔧",
        // Story 34: a verb; the tool's label follows, as a note.
        title: harness ? step.started.phase_label : net ? t("main.orch.rows.runs_tool_out") : t("main.orch.rows.runs_tool"),
        note: harness ? "" : toolLabel(step.started.tool),
        actor: forced ? "user" : harness ? "model" : "harness",
        trigger: step.trigger,
        figure,
        net,
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
      if (step.approval) figure = step.resolved ? APPROVAL_FIGURES[step.resolved.decision] : t("main.orch.rows.pending");
      rows.push({
        key,
        icon: HOOK_ICONS[p.hook] || "🪝",
        title: step.approval ? t("main.orch.approval.title") : `Hook ${p.hook.toUpperCase()} · ${p.hook_text}`,
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
      let figure = `${t("main.orch.running")} · ${seconds(Date.now() - step.startedAt)}`;
      if (ended) figure = failed ? t("main.orch.error") : `${plural(ended.excerpts.length, "excerpt")} · ${seconds(ended.duration_ms)}`;
      rows.push({
        key,
        icon: "📚",
        title: t("main.orch.rows.rag_search"),
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
      let figure = `${t("main.orch.running")} · ${done}${seconds(Date.now() - step.startedAt)}`;
      if (ended) {
        figure = stopped
          ? t("main.orch.stopped")
          : failed
            ? t("main.orch.error")
            : `${t("main.orch.rows.kept_of", { kept: plural(ended.keep, "kept"), total: String(ended.excerpts.length) })} · ${seconds(ended.duration_ms)}`;
      }
      rows.push({
        key,
        icon: "↕️",
        title: t("main.orch.rows.rerank"),
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
      let figure = `${t("main.orch.running")} · ${seconds(Date.now() - step.startedAt)}`;
      if (ended) figure = compressionFigure(ended);
      rows.push({
        key,
        icon: "🗜️",
        title: step.started.title_text,
        actor: "harness",
        figure,
        tone: failed ? "error" : null,
        sticky: failed,
        sig: [Boolean(ended), ended?.status],
        body: () => compressionBody(step),
      });
    } else if (step.type === "action_dropped") {
      const label = step.label || t("main.orch.rows.forced_action");
      rows.push({
        key,
        icon: "⊘",
        title: `${t("main.orch.rows.dropped_title")} · ${label}`,
        actor: "harness",
        trigger: "user",
        figure: t("main.orch.rows.dropped"),
        tone: "unavailable",
        sig: 1,
        body: () => [
          harnessEvent(t("main.orch.rows.dropped_title"), "info", [
            triggerBadge("user"),
            el("p", "", step.payload.reason_text),
            el("p", "label", t("main.orch.rows.dropped_decision")),
          ]),
        ],
      });
    } else if (step.type === "tool_call_malformed") {
      rows.push({
        key,
        icon: "✖",
        title: t("main.orch.malformed.title"),
        actor: "harness",
        figure:
          step.payload.reaction === "retry"
            ? t("main.orch.rows.retry")
            : turn.contextId
              ? t("main.orch.rows.delegation_stopped")
              : t("main.orch.rows.turn_stopped"),
        tone: "error",
        sticky: true,
        sig: 1,
        body: () => [malformedCard(step.payload)],
      });
    } else if (step.type === "limit_reached") {
      const retries = step.payload.limit.endsWith("retries");
      const title = turn.contextId ? t("main.orch.rows.sub_limit") : t("main.orch.rows.turn_limit");
      rows.push({
        key,
        icon: retries ? "✖" : "⏹",
        title,
        actor: "harness",
        figure: LIMITS[step.payload.limit] || step.payload.limit,
        tone: retries ? "error" : "hook",
        sticky: retries,
        sig: 1,
        body: () => [harnessEvent(title, retries ? "error" : "info", [el("p", "", step.payload.message_text)])],
      });
    } else if (step.type === "prefix_not_reused") {
      // Lot 1 of 2026-10-04: « Cache non réutilisé », the cause and the tokens read again;
      // quiet: folded even as the live step (its message on a click).
      const cause = PREFIX_CAUSES[step.payload.cause];
      const again = step.payload.again_tokens;
      const reread = again > 0 ? t("main.orch.rows.again_tokens", { count: again }) : null;
      rows.push({
        key,
        icon: "ℹ",
        title: t("main.orch.rows.prefix"),
        actor: "harness",
        figure: [cause, reread].filter(Boolean).join(" · "),
        tone: "hook",
        quiet: true,
        sig: 1,
        body: () => [harnessEvent(t("main.orch.rows.prefix"), "info", [el("p", "", step.payload.message_text)])],
      });
    } else if (step.type === "reasoning_cut") {
      // Lot C (N4): the reasoning reached its budget; the harness closed it and relaunched.
      rows.push({
        key,
        icon: "✂",
        title: t("main.orch.rows.reasoning_cut"),
        actor: "harness",
        figure: t("main.orch.rows.reasoning_cut_figure", { tokens: step.payload.reasoning_tokens, reserve: step.payload.answer_reserve }),
        tone: "hook",
        sig: 1,
        body: () => [harnessEvent(t("main.orch.rows.reasoning_cut"), "info", [el("p", "", step.payload.message_text)])],
      });
    } else if (step.type === "reasoning_dropped") {
      // Native providers 3/5 (CAP-5): a reasoning of an earlier turn thrown away by the provider.
      rows.push({
        key,
        icon: "ℹ",
        title: t("main.orch.rows.reasoning_dropped"),
        actor: "harness",
        figure: DROP_REASONS[step.payload.reason] || step.payload.reason,
        tone: "hook",
        sig: 1,
        body: () => [harnessEvent(t("main.orch.rows.reasoning_dropped"), "info", [el("p", "", step.payload.message_text)])],
      });
    }
  }
}

// Story 19 (EXPERIENCE: Sous-agent au travail): the delegation, its trigger, and the tokens
// the main context got against those that stayed in the sub-agent's.
function delegateRow(turn, step, key) {
  const ended = step.ended;
  const done = step.sub?.ended;
  let figure = `${t("main.orch.running")} · ${seconds(Date.now() - step.startedAt)}`;
  if (done?.status === "completed") {
    figure = subFigure(done);
  } else if (done?.status === "cancelled") {
    figure = t("main.orch.sub.stopped_title");
  } else if (done) {
    figure = `${SUB_STATUS[done.status] ?? done.status} · ${seconds(done.duration_ms)}`;
  } else if (ended) {
    figure = `${ended.status === "cancelled" ? t("main.orch.sub.stopped") : t("main.orch.sub.refused")} · ${seconds(ended.duration_ms)}`;
  }
  if (done && subState(done)) figure += ` · ${subState(done)}`;
  const failed = Boolean(ended && !["ok", "cancelled"].includes(ended.status));
  return {
    key,
    icon: "👥",
    title: t("main.orch.sub.title"),
    actor: step.trigger === "user" ? "user" : "model",
    trigger: step.trigger,
    figure,
    tone: failed ? "error" : null,
    sticky: failed,
    sig: [Boolean(ended), ended?.status, Boolean(done), step.sub?.steps.length ?? 0],
    body: () => delegateBody(turn, step),
  };
}

const SUB_STATUS = section("main.orch.sub.status");

// The saving of a finished delegation, in words (AD-1: the figures are the session's).
// `kept_tokens` counts every tool reply that stayed in the sub-agent: results, errors, refusals.
function subSaving(done) {
  if (done.status === "cancelled") return t("main.orch.sub.saving_cancelled");
  const guess = approx(done.estimated);
  const result = `${guess}${fmt(done.result_tokens)}`;
  if (done.status !== "completed") return t("main.orch.sub.saving_failed", { result });
  const kept = `${approx(done.context_estimated)}${fmt(done.kept_tokens ?? 0)}`;
  const figures = t("main.orch.sub.saving_figures", { kept, result });
  if ((done.kept_tokens ?? 0) <= done.result_tokens) return `${figures} ${t("main.orch.sub.saving_none")}`;
  return `${figures} ${t("main.orch.sub.saving", { saved: `${guess}${fmt(done.saved_tokens)}` })}`;
}

// Lot A (AD-11): the main context's state saved around the delegation, when it was.
function subState(done) {
  if (done.state_saved_bytes == null) return "";
  const size = intlNumber({ maximumFractionDigits: 1 }).format(done.state_saved_bytes / 1e6);
  const restored =
    done.state_restore_ms != null
      ? t("main.orch.sub.restored", { time: seconds(done.state_restore_ms) })
      : t("main.orch.sub.not_restored");
  return t("main.orch.sub.state_saved", { size, restored });
}

// The delegation line's key figure once the sub-agent is done.
function subFigure(done) {
  const guess = approx(done.estimated);
  const saving =
    done.saved_tokens > 0 ? t("main.orch.sub.saved", { tokens: `${guess}${fmt(done.saved_tokens)}` }) : t("main.orch.sub.no_saving");
  return `${t("main.orch.sub.reinjected", { tokens: `${guess}${fmt(done.result_tokens)}` })} · ${saving}`;
}

function delegateBody(turn, step) {
  const sub = step.sub;
  const done = sub?.ended;
  const nodes = [];
  const badge = triggerBadge(step.trigger);
  if (badge) nodes.push(badge);
  nodes.push(el("p", "label", t("main.orch.sub.task")), el("pre", "step-code", step.started.arguments.task ?? ""));
  if (sub?.started) {
    const tools = sub.started.tools.length ? sub.started.tools.map(toolLabel).join(", ") : t("main.orch.sub.no_tool");
    nodes.push(el("p", "", t("main.orch.sub.tools", { tools })));
  }
  if (!done) {
    const running = el("div", "token-counter number", `${t("common.in_progress")} `);
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
      `${t("main.orch.sub.calls", { calls: plural(done.calls, "call") })} · ${t("main.orch.time", { time: seconds(done.duration_ms) })} · ${SUB_STATUS[done.status] ?? done.status}`
    ),
    el("p", "subagent-saving", `${subSaving(done)} ${t("main.orch.sub.full_context", { tokens: context })}`)
  );
  if (!cancelled) {
    nodes.push(
      el("p", "label", done.status === "completed" ? t("main.orch.sub.result") : t("main.orch.sub.error_instead")),
      el("pre", "step-code", step.ended?.status === "ok" ? step.ended.result : done.result)
    );
  }
  if (sub.context) {  // no call rendered (e.g. blocked first): nothing to show
    const show = el("button", "subagent-show", t("main.orch.sub.show_context"));
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
  return option?.label_text ?? server;
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
  let figure = t("main.orch.connect.connecting");
  if (ended) figure = failed ? t("main.orch.connect.down") : `${t("main.orch.connect.connected")} · ${plural(ended.tools.length, "tool")}`;
  return {
    key: `mcp:${step.seq}`,
    icon: failed ? "⊘" : "🔌",
    title: mcpServerLabel(step.started.server),
    note: failed ? ended.error_text : "",
    actor: "harness",
    figure,
    net: step.outbound?.length ? hostOf(step.outbound[0].url) : null,
    links: stepLinks(step),
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

// Story 34: the tile's letter, who acts: « R » the network (a tool or a connection that sent
// data out), else the model, the harness or the user.
const ACTOR_LETTERS = { model: "M", harness: "H", user: "U" };
const rowLetter = (row) => (row.net && row.outbound?.length ? "R" : ACTOR_LETTERS[row.actor] || "H");

function stepNode(row, open, flags) {
  let node = railNodes.get(row.key);
  if (!node) {
    const root = el("div", "turn-step");
    const line = el("button", "turn-step-line");
    line.type = "button";
    // Story 34, two rows: the tile (who acts) on both; the type's icon and the title on top,
    // who decides and where it goes under them; the key figure and the chevron on the right.
    const parts = {
      tile: el("span", "turn-step-tile"),
      icon: el("span", "turn-step-icon"),
      title: el("span", "turn-step-title"),
      meta: el("span", "turn-step-meta"),
      figure: el("span", "turn-step-figure"),
      chevron: el("span", "turn-step-chevron"),
    };
    parts.tile.setAttribute("aria-hidden", "true");
    parts.icon.setAttribute("aria-hidden", "true");
    parts.chevron.setAttribute("aria-hidden", "true");
    line.append(...Object.values(parts));
    Object.assign(parts, {
      trigger: el("span", "turn-step-trigger"),
      actor: el("span", "turn-step-actor"),
      via: el("span", "turn-step-via", ` · ${t("main.orch.via_network")}`),
      netMark: el("span", "net-mark", `🌐 ${t("main.hosting.network")} →`),
      netHost: el("span", "net-host"),
    });
    // « 🌐 RÉSEAU → host » wraps as one piece; only its host shrinks (story 8d).
    const net = el("span", "turn-step-net");
    net.append(parts.netMark, parts.netHost);
    parts.meta.append(parts.trigger, parts.actor, parts.via, net);
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
    // Unfolds the step (story 8d) and selects it (story 34): its keys light the other panes.
    line.addEventListener("click", () => {
      toggleStep(key);
      select(`step:${key}`, readLinks(root));
      if (store.selection === `step:${key}`) revealCall(readLinks(root)); // story 32
    });
    root.appendChild(line);
    node = { root, line, ...parts, body: null, bodySig: null };
    railNodes.set(key, node);
  }
  node.seen = true;
  node.sticky = Boolean(row.sticky);
  setText(node.tile, rowLetter(row));
  setText(node.icon, row.icon);
  if (node.tile.dataset.discipline !== row.discipline) node.tile.dataset.discipline = row.discipline;
  if (node.root.dataset.discipline !== row.discipline) node.root.dataset.discipline = row.discipline;
  setLinks(node.root, row.links);
  setText(node.name, row.title);
  setText(node.note, row.note ? ` · ${row.note}` : "");
  node.note.hidden = !row.note;
  const trigger = triggerOf(row.trigger);
  node.trigger.hidden = !trigger;
  const triggerClass = `turn-step-trigger ${trigger ? trigger[0] : ""}`;
  if (node.trigger.className !== triggerClass) node.trigger.className = triggerClass;
  setText(node.triggerIcon, trigger ? trigger[1] : "");
  setText(node.triggerLabel, trigger ? trigger[2] : "");
  const [actorClass, actorLabel] = actorOf(row.actor);
  node.actor.className = `turn-step-actor ${actorClass}`;
  setText(node.actor, actorLabel);
  node.via.hidden = !row.via;
  node.netMark.hidden = !row.net;
  node.netHost.hidden = !row.net;
  setText(node.netHost, row.net || "");
  setText(node.figure, row.figure);
  setText(node.chevron, open ? "▾" : "▸");
  // The whole title in the tooltip: the line truncates it first (A10).
  const tooltip = [
    row.title,
    row.note,
    trigger?.[2],
    actorLabel,
    row.via ? t("main.orch.via_network") : "",
    row.net ? `${t("main.hosting.network")} → ${row.net}` : "",
    row.figure,
  ]
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
      o.userOpen = new Set(o.current && !o.currentApart ? [o.current] : []);
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
      o.userOpen = new Set(o.current && !o.currentApart ? [o.current] : []);
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
  let label = turn.phaseLabel || t("main.chat.preparing");
  if (turn.stopRequested) label = t("main.model.stop_requested");
  else if (turn.firstToken) label = t("main.orch.generating");
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
  o.currentApart = Boolean(currentRow?.sticky || currentRow?.quiet);
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
      ["turn-group-title", t("main.orch.prep")],
      ["turn-group-summary", `${t("main.orch.prep_connections", { count: prep.length })}${down ? ` · ${t("main.orch.prep_down", { count: down })}` : ""}`],
    ]);
    fillGroup(node, o.prepGroupOpen, connectNodes(prep));
    top.push(node.root);
  }
  if (!shown.length) {
    orchEmptyNote ||= emptyNote("");
    setText(
      orchEmptyNote,
      cleared() ? clearedText() : t("main.orch.no_turn")
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
    const [statusClass, statusLabel] = turnStatusOf(turn.status) || ["is-running", t("main.orch.running")];
    const calls = turn.steps.filter((s) => s.type === "call" && s.startedAt).length;
    const duration = turnDuration(turn);
    const figures = [
      duration === null ? null : seconds(duration),
      t("main.orch.sub.calls", { calls: plural(calls, "call") }),
      turn.cost ? costText(turn.cost, t("main.cost.turn_label")) : null,
      turn.footprint ? footprintText(turn.footprint, t("main.footprint.turn_label")) : null,
    ];
    headParts(node, [
      ["turn-group-title", t("main.turn.name", { n: String(i + 1) })],
      [`turn-group-status ${statusClass}`, statusLabel],
      ["turn-group-replay", turn.replayOf ? t("main.chat.replay_badge") : null],
      ["turn-group-figures", figures.filter(Boolean).join(" · ")],
      ["turn-group-message", quote(turn.message)],
    ]);
    node.head.title = turn.message;
    node.parts[0].title = turnIdTitle(turn); // story 22: links « Tour N » to the journal
    const rowNodes = open
      ? (isLast ? lastRows : turnRows(turn)).map((row) => {
          const isCurrent = isLast && row.key === o.current;
          // Lot 1 of 2026-10-04: a quiet row (`prefix_not_reused`) is never unfolded as the live one.
          const unfolded = row.sticky || (o.live ? isCurrent && !row.quiet : o.userOpen.has(row.key));
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
function setTopStatus(text, title = text) {
  const status = document.getElementById("top-status");
  setText(status, text);
  if (status.title !== title) status.title = title;
}

function renderChips() {
  panes.renderChips();
}

function renderMenu() {
  const list = document.getElementById("pane-menu-list");
  list.innerHTML = "";
  for (const paneId of PANES) {
    const visible = !store.hiddenPanes.has(paneId);
    const li = document.createElement("li");
    const label = document.createElement("label");
    const checkbox = document.createElement("input");
    checkbox.type = "checkbox";
    checkbox.checked = visible;
    checkbox.disabled = !panes.canHide(paneId);
    if (checkbox.disabled) checkbox.title = t("common.panes.one_visible");
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
  link.textContent = t("main.panes.diagnostic");
  item.appendChild(link);
  list.appendChild(item);
}

function renderPaneVisibility() {
  panes.render();
}

// ---------- event log: every event the harness emits, folded at the bottom of Orchestration ----------

const KIND_LABELS = section("main.log.kinds");
const MODEL_LOAD_STATUS = section("main.log.model_load_status");
const MEMORY_OPS = section("main.log.memory_ops");
const SESSION_STATES = section("main.log.session_states");

// Story 29: how a generation of the « LLM nu » screen ended.
const LAB_STATUS = section("main.log.lab_status");
// Correctif du 2026-10-02: how a RAG workshop's stage or run ended, and the language names.
const RAG_LAB_STATUS = section("main.log.rag_lab_status");
const LANGUAGE_NAMES = section("main.log.languages");

// A RAG workshop stage, « Dense retrieval »: its label is in the run's
// `rag_lab_run_started` (lot 5c-1: one chain per run, its `stages`), its kind when that event
// is not on the page. B2 (2026-10-05): BM25's index, built at BUILD (`part` « index »), keeps
// the BM25 stage's id but has its own name.
function ragLabStage(p) {
  if (p.part === "index") return t("main.log.rag_lab_lexical_index");
  const run = store.journal.findLast((e) => e.kind === "rag_lab_run_started" && e.payload.run_id === p.run_id);
  const stage = run?.payload.stages?.find((s) => s.stage_id === p.stage_id);
  return stage?.label_text ?? p.kind;
}

// Story 29: « T 0,7 · top-k 20 · top-p 0,8 · min-p 0 », a value not sent as « — ».
function samplingSummary(s) {
  if (s.source === "provider") return s.note_text || t("main.log.sampling_provider");
  const part = (label, value) => `${label} ${value === null || value === undefined ? "—" : fmt(value)}`;
  return [part("T", s.temperature), part("top-k", s.top_k), part("top-p", s.top_p), part("min-p", s.min_p)].join(" · ");
}

function eventSummary(group) {
  // One line per event, formatting only (AD-1).
  const e = group.events[0];
  const p = e.payload;
  switch (e.kind) {
    case "model_delta":
      return group.events.map((d) => d.payload.text).join("");
    case "session_state":
      return [SESSION_STATES[p.state] || p.state, p.reason_text].filter(Boolean).join(" · ");
    case "architecture_changed":
      return `${plural(p.nodes.length, "node")}, ${plural(p.edges.length, "edge")}`;
    case "bricks_changed":
      return t("main.log.bricks_wanted", { wanted: String(p.bricks.filter((b) => b.wanted).length), total: String(p.bricks.length) });
    case "context_rendered":
    case "context_preview":
    case "context_reconciled":
      return `${t("main.orch.overflow.figures", { used: p.used, usable: p.usable })} · ${plural(p.segments.length, "segment")}`;
    case "context_overflow":
      return t("main.orch.overflow.figures", { used: p.used, usable: p.usable });
    case "context_window_state": {
      const chosen = p.configured !== p.window ? t("main.window.chosen", { window: p.configured }) : "";
      return [p.model_label, `${t("main.window.choice", { window: p.window })}${chosen}`].filter(Boolean).join(" · ");
    }
    case "language_changed":
      return LANGUAGE_NAMES[p.language] ?? p.language;
    case "turn_started":
      return quote(p.message);
    case "turn_ended":
      return [
        turnStatusOf(p.status)?.[1] ?? p.status,
        p.duration_ms == null ? null : seconds(p.duration_ms),
        p.cost_in_usd != null ? costText(p, "") : null,
        p.energy_wh_min != null ? footprintText(p, "") : null,
      ]
        .filter(Boolean)
        .join(" · ");
    case "consumption_updated":
      return [
        p.calls
          ? `${t("main.cost.text", { label: "", input: `${approx(p.approx)}${usd(p.total_in_usd)}`, output: `${approx(p.approx)}${usd(p.total_out_usd)}` })} · ${plural(p.calls, "call")}`
          : null,
        p.impact_calls ? t("main.log.footprint", { footprint: footprintText(p, ""), calls: plural(p.impact_calls, "call") }) : null,
      ]
        .filter(Boolean)
        .join(" · ");
    case "model_call_started":
      return p.sampling ? `${p.phase_label} · ${samplingSummary(p.sampling)}` : p.phase_label;
    case "mcp_connect_started":
    case "model_load_started":
    case "llm_generation_started":
    case "rag_lab_run_started":
      return p.phase_label;
    // Correctif du 2026-10-02: the RAG workshop's run, in the log only.
    case "rag_lab_stage_started":
      return p.phase_label;
    case "rag_lab_stage_progress":
      return `${ragLabStage(p)} · ${t("main.log.rag_lab_progress", { done: p.done, total: p.total })}`;
    case "rag_lab_stage_ended":
      return [
        ragLabStage(p),
        RAG_LAB_STATUS[p.status] ?? p.status,
        p.status === "ok" && p.items.length ? plural(p.items.length, "excerpt") : null,
        ["ok", "error", "cancelled"].includes(p.status) ? seconds(p.duration_ms) : null,
      ]
        .filter(Boolean)
        .join(" · ");
    case "rag_lab_run_ended":
      return [RAG_LAB_STATUS[p.status] ?? p.status, seconds(p.duration_ms)].filter(Boolean).join(" · ");
    case "llm_token":
      return group.events
        .filter((x) => x.kind === "llm_token")
        .map((x) => x.payload.text)
        .join("")
        .slice(0, 200);
    case "model_load_step":
      return `${p.label_text} · ${seconds(p.duration_ms)}`;
    case "llm_generation_ended":
      return [LAB_STATUS[p.status] ?? p.status, seconds(p.duration_ms), p.message_text]
        .filter(Boolean)
        .join(" · ");
    case "model_load_ended":
      return [labelValue(p.model.label, MODEL_LOAD_STATUS[p.status] ?? p.status), seconds(p.duration_ms), p.reason_text]
        .filter(Boolean)
        .join(" · ");
    case "model_call_ended": {
      const evaluated = p.evaluated_tokens != null ? ` · ${t("main.log.evaluated", { tokens: p.evaluated_tokens })}` : "";
      const footprint = p.energy_wh_min != null ? ` · ${footprintText(p, "")}` : "";
      return `${t("main.orch.rows.read", { tokens: fmt(p.prompt_tokens) })}${evaluated} · ${t("main.log.written", { tokens: p.output_tokens })} · ${seconds(p.duration_ms)} · ${p.stop_reason}${footprint}`;
    }
    case "tool_started":
      return formatCall({ name: p.tool, arguments: p.arguments });
    case "tool_ended":
      return `${p.status}${p.truncated ? ` · ${t("main.orch.rows.truncated")}` : ""} · ${seconds(p.duration_ms)}`;
    case "outbound_request":
      return `${p.method} ${p.url}`;
    // Recette du 02/10 (R2): a refusal's status, then the quota headers left in clear.
    case "outbound_response": {
      const quota = (p.headers ?? [])
        .filter((h) => !h.masked && /^(x-)?ratelimit-|^retry-after$/i.test(h.name))
        .map((h) => `${h.name}: ${h.value}`)
        .join(", ");
      return [String(p.status), `${p.method} ${p.url}`, quota].filter(Boolean).join(" · ");
    }
    case "mcp_connect_ended":
      return p.status === "ok"
        ? `${labelValue(mcpServerLabel(p.server), plural(p.tools.length, "tool"))} · ${seconds(p.duration_ms)}`
        : labelValue(mcpServerLabel(p.server), p.error_text);
    // Story 6 (2026-09-30): the MCP workshop's exchanges, in the log only.
    case "mcp_lab_message":
      return `${t(p.direction === "to_server" ? "mcp.to_server" : "mcp.from_server")} · ${p.method || "—"} · ${seconds(p.elapsed_ms)}`;
    case "mcp_lab_connect_ended":
      return p.status === "ok"
        ? `${labelValue(mcpServerLabel(p.server), plural((p.tools ?? []).length, "tool"))} · ${seconds(p.duration_ms)}`
        : labelValue(mcpServerLabel(p.server), p.error_text);
    case "mcp_lab_call_ended":
      return [labelValue(mcpServerLabel(p.server), p.tool), seconds(p.duration_ms), p.error_text]
        .filter(Boolean)
        .join(" · ");
    // Lot 4 of 2026-10-04 (AD-27): the workshop's other exchanges, in the log only.
    case "mcp_lab_exchange_started":
      return [labelValue(mcpServerLabel(p.server), p.exchange), p.tool ?? p.uri ?? p.prompt ?? p.question]
        .filter(Boolean)
        .join(" · ");
    case "mcp_lab_read_ended":
      return [labelValue(mcpServerLabel(p.server), p.uri), seconds(p.duration_ms), p.error_text]
        .filter(Boolean)
        .join(" · ");
    case "mcp_lab_prompt_ended":
      return [labelValue(mcpServerLabel(p.server), p.name), seconds(p.duration_ms), p.error_text]
        .filter(Boolean)
        .join(" · ");
    case "mcp_lab_model_started":
      return p.phase_label;
    case "mcp_lab_model_ended":
      return [p.outcome ?? p.status, seconds(p.duration_ms), p.refusal_text ?? p.error_text]
        .filter(Boolean)
        .join(" · ");
    case "mcp_lab_ask_ended":
      return [labelValue(mcpServerLabel(p.server), p.outcome ?? p.status), seconds(p.duration_ms), p.error_text]
        .filter(Boolean)
        .join(" · ");
    case "mcp_lab_closed":
      return labelValue(mcpServerLabel(p.server), p.cause);
    case "hook_decided":
      return `${p.hook.toUpperCase()} · ${p.point_text} · ${HOOK_DECISIONS[p.decision]}`;
    case "effect_applied":
      if (p.effect === "memory_write") return `${MEMORY_OPS[p.op] ?? p.op} · ${quote(p.text)}`;
      if (["model_download", "model_download_stopped", "rag_index_write"].includes(p.effect)) return p.lines.join(" · ");
      if (p.effect === "audit_append") return t("main.log.audit_lines", { lines: plural(p.lines.length, "line") });
      return p.key ?? p.id ?? p.effect;
    case "memory_changed":
      return p.error_text ?? `${plural(p.entries.length, "entry")} · ${p.path}`;
    case "approval_requested":
      return `${p.tool} → ${p.destination}`;
    case "approval_resolved":
      return approvalDecision(p);
    case "armed_actions_changed":
      return p.actions.length ? p.actions.map((a) => a.label_text).join(" · ") : t("main.log.no_armed");
    case "action_dropped":
      return p.reason_text;
    case "subagent_started":
      return p.task;
    case "subagent_ended":
      return [p.status === "completed" ? subFigure(p) : SUB_STATUS[p.status] ?? p.status, subState(p)]
        .filter(Boolean)
        .join(" · ");
    case "rag_search_started":
      return `${quote(p.query)} · ${t("main.log.at_most", { count: p.top_k })}`;
    case "rag_rerank_started":
      return `${quote(p.query)} · ${plural(p.candidates, "candidate")}, ${plural(p.keep, "kept")}`;
    case "rag_rerank_progress":
      return t("main.log.rerank_progress", { done: p.done, total: p.total });
    case "rag_rerank_ended":
      return p.status === "ok"
        ? `${t("main.orch.rows.kept_of", { kept: plural(p.keep, "kept"), total: String(p.excerpts.length) })} · ${seconds(p.duration_ms)}` +
            (p.excerpts.length ? ` · ${t("main.log.rerank_first", { title: p.excerpts[0].title_text, before: String(p.excerpts[0].before) })}` : "")
        : p.error_text;
    case "compression_started":
      return `${plural(p.items, "text")} · ${p.compressor_text}`;
    case "compression_ended":
      return p.status === "ok" ? compressionFigure(p) : p.error_text;
    case "rag_search_ended":
      return p.status === "ok"
        ? `${plural(p.excerpts.length, "excerpt")} · ${seconds(p.duration_ms)}` +
            (p.excerpts.length ? ` · ${t("main.log.search_best", { title: p.excerpts[0].title_text, score: scoreFormat().format(p.excerpts[0].score) })}` : "")
        : p.error_text;
    case "tool_call_malformed":
      return p.detail_text;
    case "output_truncated":
      return t("main.orch.overflow.figures", { used: p.output_tokens, usable: p.max_tokens });
    case "reasoning_cut":
      return t("main.log.reasoning_cut", { tokens: p.reasoning_tokens, budget: p.budget, reserve: p.answer_reserve });
    case "reasoning_dropped":
      return t("main.log.reasoning_dropped", { reason: DROP_REASONS[p.reason] || p.reason, path: p.path });
    case "diagnostic_check":
      return `${labelValue(p.check, p.status)} · ${p.message_text}`;
    case "diagnostic_progress":
      return p.total ? t("main.log.diagnostic_progress", { count: p.done, total: String(p.total) }) : t("main.log.diagnostic_nothing_to_probe");
    case "llm_tokenized":
      return p.exact
        ? `${t("main.ctx.tokens", { tokens: String(p.figures_text?.token_count ?? p.token_count) })} · ${p.model_label}`
        : `≈ ${t("main.log.estimate", { tokens: String(p.figures_text?.estimate ?? p.estimate) })} · ${p.model_label}`;
    case "conversation_cleared":
      return t("main.log.cleared");
    case "harness_reset":
      return t("main.log.reset");
    case "scenario_changed":
      return p.active ? (findScenario(p.active)?.title_text ?? p.active) : t("main.log.no_scenario");
    default:
      return p.message_text ?? "";
  }
}

// Rows are built only once the log is unfolded, then kept: consecutive `model_delta` of one
// call share a row (« Morceaux de réponse × N »), every other event has its own.
const eventLog = { groups: [], processed: 0, rows: [], list: null, labStreams: new Map() };

function syncLogGroups() {
  for (; eventLog.processed < store.journal.length; eventLog.processed++) {
    const e = store.journal[eventLog.processed];
    if (e.kind === "scenario_changed" && e.payload?.refresh) continue; // lot E: not a launch
    const last = eventLog.groups.at(-1);
    const first = last?.events[0];
    // Story 29: one line per generation of the « LLM nu » screen, its tokens and deltas.
    if (e.context_id === "llm" && (e.kind === "llm_token" || e.kind === "model_delta")) {
      const stream = eventLog.labStreams.get(e.step_id);
      if (stream) stream.events.push(e);
      else {
        const group = { key: e.seq, kind: "llm_token", events: [e] };
        eventLog.labStreams.set(e.step_id, group);
        eventLog.groups.push(group);
      }
      continue;
    }
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
    setText(parts.time, dateTimeFormat({ hour: "2-digit", minute: "2-digit", second: "2-digit" }).format(new Date(group.events[0].ts)));
    row = { li, line, ...parts, json: null, count: 0 };
    eventLog.rows[i] = row;
  }
  const count = group.events.length;
  const open = store.orch.logRowsOpen.has(group.key);
  if (row.count !== count) {
    const merged = group.kind === "model_delta" && count > 1;
    const tokens = group.kind === "llm_token" ? group.events.filter((x) => x.kind === "llm_token").length : 0;
    setText(
      row.name,
      merged
        ? t("main.log.deltas", { count: fmt(count) })
        : tokens
          ? t("main.log.lab_tokens", { count: fmt(tokens) })
          : KIND_LABELS[group.kind] || group.kind
    );
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
    t("main.log.title", { count: fmt(store.journal.length - store.logFrom) })
  );
  head.setAttribute("aria-expanded", String(o.logOpen));
  if (!o.logOpen) {
    eventLog.list?.remove();
    return;
  }
  if (!eventLog.list) {
    eventLog.list = el("ol", "event-log-list");
    eventLog.list.id = "event-log-list";
    eventLog.empty = el("li", "empty-note", t("main.log.empty"));
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
const POSE_LABELS = section("main.schema.poses");
// Hook id -> its point of attachment, in the order the strip lists them (formatting only, like
// HOOK_ICONS): the order of a turn, from the user's message to its end.
const HOOK_POINT_ORDER = ["h3", "h1", "h5", "h2"];
const HOOK_POINTS = section("main.schema.hook_points");
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
  { zone: "local", col: 0, kind: "tool", hosting: "local", shape: "tool", icon: "🔧", title: "tools" },
  { zone: "local", col: 1, kind: "mcp_server", hosting: "local", shape: "mcp", icon: "🔌", title: "mcp_servers" },
  { zone: "local", col: 1, kind: "file", shape: "file", icon: "📄", title: "files" },
  { zone: "local", col: 2, kind: "skill", shape: "skill", icon: "📘", title: "skills" },
  { zone: "network", col: 0, kind: "tool", hosting: "network", shape: "tool", icon: "🔧", title: "network_tools" },
  { zone: "network", col: 0, kind: "mcp_server", hosting: "network", shape: "mcp", icon: "🔌", title: "public_mcp_servers" },
];
const GROUP_TITLES = section("main.schema.groups");
const SHAPE_LABELS = section("main.schema.shapes");

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
  const who = sub ? t("main.schema.sub_robot") : name ? t("main.schema.model_named", { model: name }) : t("main.schema.model");
  const label = labelValue(who, POSE_LABELS[pose]);
  const classes = `robot${sub ? " robot-sub" : ""}${pose === "idle" ? "" : " is-active"}`;
  // Its `is-active` is its pose (the antenna), not a halo: not a block of the diagram.
  const button = schemaButton(classes, sub ? "core.model_sub" : "core.model", undefined, false);
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
  button.append(svg, el("span", "robot-label", sub ? t("main.schema.subagent") : t("main.schema.model")));
  // The frame is narrow: a long file name is cut by the style, the tooltip keeps it whole.
  if (name && !sub) button.appendChild(el("span", "robot-model", name));
  if (modelNode && !modelNode.available) button.classList.add("is-unavailable");
  return button;
}

// Every piece of the schema is a button: Tab reaches it, Enter selects it (FR-4); a block of
// the shared diagram (`halo`), lit by `is-active`, but the robots.
function schemaButton(className, componentId, text, halo = true) {
  const button = halo ? diagramBlock(className, text) : el("button", className, text);
  button.type = "button";
  button.dataset.component = componentId;
  button.dataset.focusKey = componentId;
  setLinks(button, linkKeysOfComponent(componentId)); // story 34 (the model's are patched)
  button.classList.toggle("is-selected", store.selection === componentId);
  button.setAttribute("aria-pressed", String(store.selection === componentId));
  button.addEventListener("click", () => select(componentId, readLinks(button)));
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
// Story 34: the last turn shown, its number and the components it sent data to (the network
// nodes' « contacté » / « non contacté »), at the last `renderSchema`; `null` without a turn.
let schemaTurn = null;

// Story 34: a step whose outcome is known and is no success: its requests did not get through.
const stepFailed = (step) => Boolean(step.ended && step.ended.status !== "ok");

// Story 34: the requests a turn sent out (sub-agent included), each with the step that sent
// it, in the order they left (AD-1: the `outbound_request` events of its tool steps).
function turnRequests(turn) {
  return allSteps(turn)
    .filter((step) => step.type === "tool")
    .flatMap((step) => (step.outbound || []).map((request) => ({ request, step })));
}

// Story 34: the model plate's keys: the model, then every call of its context in the turns
// shown (the sub-agent's plate: its calls).
function modelLinkKeys(sub) {
  const calls = shownTurns().flatMap((turn) =>
    (sub ? [...turn.subs.values()] : [turn]).flatMap((context) =>
      context.steps.filter((step) => step.type === "call" && step.id).map((step) => `call:${step.id}`)
    )
  );
  return [sub ? "core.model_sub" : "core.model", ...calls];
}

// Patched at each render, the schema not rebuilt: the calls come during a turn.
function patchModelLinks(root) {
  const main = modelLinkKeys(false);
  const plates = root.querySelectorAll(
    '.robot[data-component="core.model"], .arch-cloud-model, .arch-server-model'
  );
  for (const plate of plates) setLinks(plate, main);
  const sub = root.querySelector('.robot[data-component="core.model_sub"]');
  if (sub) setLinks(sub, modelLinkKeys(true));
}

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
  // « contacté »: a request of a step that succeeded; « en échec »: only failed attempts.
  const requests = last ? turnRequests(last) : [];
  const reachedIds = new Set(requests.filter((r) => r.step.ended?.status === "ok").map((r) => r.request.component));
  schemaTurn = last
    ? {
        number: turnNumber(last),
        contacted: reachedIds,
        failed: new Set(requests.filter((r) => stepFailed(r.step) && !reachedIds.has(r.request.component)).map((r) => r.request.component)),
      }
    : null;
  const turnKey = schemaTurn ? [schemaTurn.number, [...schemaTurn.contacted].sort(), [...schemaTurn.failed].sort()] : null;
  const key = JSON.stringify([store.architecture, wanted.length, hooks, blocked, store.selection, [...outboundShown].sort(), turnKey]);
  const robotKey = JSON.stringify([pose, subPose, model?.model]);
  if (key !== renderedSchemaKey) {
    renderedSchemaKey = key;
    renderedActivityKey = null;
    renderedRobotKey = robotKey;
    buildSchema(root, nodes, wanted.length > 0, hooks, blocked, robots());
    schemaWires.schedule();
  }
  if (robotKey !== renderedRobotKey) {
    // A pose change swaps the robots only: the rest keeps its focus and its layout.
    renderedRobotKey = robotKey;
    for (const next of robots()) {
      const old = root.querySelector(`.robot[data-component="${next.dataset.component}"]`);
      const focused = old === document.activeElement;
      old?.replaceWith(next);
      if (focused) quietFocus(next);
    }
  }
  const activity = schemaActivity(nodes);
  const activityKey = JSON.stringify(activity);
  if (activityKey !== renderedActivityKey) {
    renderedActivityKey = activityKey;
    schemaActive = activity;
    const id = activity ? cssEscape(activity.component) : null;
    light(root, id && root.querySelector(`.arch-node[data-component="${id}"], .arch-hook[data-component="${id}"], .arch-chip[data-component="${id}"]`));
    schemaWires.schedule();
  }
  patchModelLinks(root);
}

// ---------- story 34: what left the workstation during the last turn shown ----------


// The sentence under the schema (AD-1: counted from the turn's events only). The model's
// calls when it runs out of the workstation (the E2E fake cloud, on the loopback, is not
// traced: its calls are counted from `model_call_started`), then the requests of its tool
// steps, by destination in the order of first contact, with what the node says it sends.
function outboundSummary(turn) {
  if (!turn) return t("main.outbound_summary.no_turn");
  const at = t(turn.status === null ? "main.outbound_summary.at_turn_running" : "main.outbound_summary.at_turn", { n: String(turnNumber(turn)) });
  const model = turn.model;
  const cloud = model?.hosting === "network";
  const provider = model?.provider ?? (cloud ? t("main.outbound_summary.the_provider") : null);
  const calls = cloud ? allSteps(turn).filter((s) => s.type === "call" && s.startedAt).length : 0;
  const nodes = new Map((store.architecture.nodes || []).map((n) => [n.id, n]));
  // Destination -> { label, sends, count (requests that left), failed (failed steps) }: a
  // failed step's requests did not reach it (network cut, refused), a single failed attempt
  // whatever its redirect hops.
  const groups = new Map();
  const failedSteps = new Set();
  for (const { request, step } of turnRequests(turn)) {
    const node = request.component ? nodes.get(request.component) : null;
    const key = node ? node.id : hostOf(request.url); // story 23 absent: the URL's host
    const group = groups.get(key) ?? { label: node?.label_text ?? key, sends: node?.sends_text, count: 0, failed: 0 };
    if (!stepFailed(step)) group.count += 1;
    else if (!failedSteps.has(`${key} ${step.stepId}`)) {
      failedSteps.add(`${key} ${step.stepId}`);
      group.failed += 1;
    }
    groups.set(key, group);
  }
  const what = (g) => (g.sends ? ` (${g.sends})` : "");
  const left = [...groups.values()].filter((g) => g.count);
  const failed = [...groups.values()]
    .filter((g) => g.failed)
    .map((g) => t("main.outbound_summary.failed", { count: g.failed, target: `${g.label}${what(g)}` }));
  const times = calls + left.reduce((sum, g) => sum + g.count, 0);
  if (!times) {
    const where =
      model?.kind === "server"
        ? t("main.outbound_summary.served", { provider: provider ? ` (${provider})` : "" })
        : cloud
          ? t("main.outbound_summary.no_call", { provider })
          : t("main.outbound_summary.local");
    if (failed.length) return t("main.outbound_summary.nothing_failed", { at, where, failed: joinList(failed) });
    return t("main.outbound_summary.nothing", { at, where });
  }
  const parts = [];
  if (calls) parts.push(t("main.outbound_summary.to_model", { provider, calls: plural(calls, "call") }));
  for (const g of left) parts.push(t("main.outbound_summary.to_node", { label: g.label, sends: g.sends ? `${g.sends}, ` : "", requests: plural(g.count, "request") }));
  return t("main.outbound_summary.left", { at, count: times, parts: joinList([...parts, ...failed]) });
}

function renderOutboundSummary() {
  setText(document.getElementById("schema-outbound"), outboundSummary(shownTurns().at(-1)));
}

function buildSchema(root, nodes, anyBrick, hooks, blocked, robotNodes) {
  // The rebuild would drop keyboard focus: note it, restore it on the new element.
  const focusKey = root.contains(document.activeElement) ? document.activeElement.dataset.focusKey : null;
  root.innerHTML = "";
  const byId = Object.fromEntries(nodes.map((n) => [n.id, n]));

  // The harness frame: the robot and the chips of the bricks with no outside component, stacked.
  const frame = el("div", "arch-harness");
  frame.dataset.component = "core.harness";
  setLinks(frame, ["core.harness"]); // story 34
  frame.classList.toggle("is-selected", store.selection === "core.harness");
  frame.title = byId["core.harness"]?.label_text || t("main.schema.harness");
  frame.addEventListener("click", (event) => {
    if (!event.target.closest("button:not(.arch-harness-tag)")) select("core.harness");
  });
  const tag = el("button", "arch-harness-tag", t("main.schema.harness")); // its click reaches the frame
  tag.type = "button";
  tag.dataset.focusKey = "core.harness";
  const core = el("div", "arch-core");
  const chips = el("div", "arch-chips");
  for (const node of nodes.filter((n) => n.kind === "brick")) {
    const icon = COMPONENT_ICONS[node.id] || BRICK_ICONS[node.id.split(".")[0]] || "🧩";
    const chip = schemaButton("arch-chip", node.id, `${icon} ${node.label_text}`);
    chip.dataset.discipline = nodeDiscipline(node); // story 33
    chip.classList.toggle("is-unavailable", !node.available);
    chip.title = [node.available ? node.label_text : labelValue(node.label_text, node.reason_text), node.detail_text]
      .filter(Boolean)
      .join("\n");
    chips.appendChild(chip);
  }
  if (!anyBrick) chips.appendChild(el("p", "arch-harness-empty", t("main.schema.no_brick")));
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
    box.title = t("main.schema.served_title", { provider: model.provider, address });
    box.append(robotRow, el("span", "arch-node-name", `🖥 ${model.provider} · ${address}`));
    localRow.appendChild(box);
  }
  localRow.append(...schemaColumns("local", nodes));
  local.append(el("span", "arch-zone-label", `🖥 ${t("main.schema.workstation")}`), localRow);

  const boundary = el("div", "arch-boundary");
  boundary.appendChild(el("span", "arch-boundary-label", t("main.schema.boundary")));

  const network = el("div", "arch-zone arch-zone-network");
  const networkRow = el("div", "arch-zone-row");
  const networkCols = schemaColumns("network", nodes);
  if (cloud) {
    const box = el("div", "arch-cloud-model");
    box.title = t("main.schema.cloud_title", { provider: model.provider });
    box.append(robotRow, el("span", "arch-node-name", `🌐 ${model.provider}`));
    networkCols.unshift(box);
  }
  if (networkCols.length) networkRow.append(...networkCols);
  else networkRow.appendChild(el("p", "arch-zone-empty", t("main.schema.no_network")));
  network.append(el("span", "arch-zone-label", `🌐 ${t("main.hosting.network")} · ${t("main.schema.off_workstation")}`), networkRow);

  // The trunk, the rails and the path, drawn over the pieces once they are laid out.
  schemaWires.clear();
  root.append(local, boundary, network, schemaWires.svg);
  if (focusKey) quietFocus(root.querySelector(`[data-focus-key="${cssEscape(focusKey)}"]`));
}

// The « Points d'accroche » strip: every hook of the brick, one per line, name and point; a hook
// switched off (unchecked, or H5 after « Autoriser et ne plus demander ») stays, dashed grey.
function hookStrip(options, byId, blocked) {
  const strip = el("div", "arch-hook-strip");
  strip.appendChild(el("span", "arch-hook-strip-tag", `🪝 ${t("main.schema.hook_strip")}`));
  const order = HOOK_POINT_ORDER;
  const rank = (id) => (order.includes(id) ? order.indexOf(id) : order.length);
  for (const option of [...options].sort((a, b) => rank(a.id) - rank(b.id))) {
    const id = `hooks.${option.id}`;
    const off = !byId[id]; // enabled hooks only are in `architecture_changed`
    const isBlocked = !off && blocked.includes(id);
    const point = HOOK_POINTS[option.id] || "";
    const state = isBlocked ? ` · ✖ ${t("main.schema.hook_blocked")}` : off ? ` · ${t("main.schema.hook_off")}` : "";
    const hook = schemaButton("arch-hook", id);
    hook.dataset.discipline = brickCategory("hooks") ?? "harness"; // story 33
    hook.classList.toggle("is-off", off);
    hook.classList.toggle("is-blocked", isBlocked);
    hook.append(
      el("span", "arch-hook-name", `${HOOK_ICONS[option.id] || "🪝"} ${option.label_text}${state}`),
      el("span", "arch-hook-point", point)
    );
    hook.title = [
      t("main.schema.hook_title", { hook: option.label_text, point }),
      byId[id]?.detail_text,
      off ? t("main.schema.hook_off_title") : null,
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
  const title = GROUP_TITLES[group.title];
  bin.setAttribute("aria-label", labelValue(title, String(members.length)));
  const list = el("div", "arch-group-nodes");
  for (const node of members) list.append(...schemaNode(node, group.shape));
  bin.append(el("span", "arch-group-title", `${group.icon} ${title} · ${members.length}`), list);
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
  // Story 34: a network tool or server says whether the last turn shown reached it, as the
  // outbound summary under the schema does; without a turn shown, the session's state.
  const perTurn = network && (shape === "tool" || shape === "mcp") && schemaTurn !== null;
  const reached = perTurn && schemaTurn.contacted.has(node.id);
  const attempted = perTurn && schemaTurn.failed.has(node.id);
  const turnState = reached ? t("main.schema.contacted") : attempted ? t("main.schema.failed") : t("main.schema.not_contacted");
  let pill = null;
  if (unavailable) pill = t("main.schema.unavailable");
  else if (perTurn) pill = turnState;
  else if (shape === "mcp") pill = notContacted ? t("main.schema.not_contacted") : plural(tools.length, "tool");
  else if (notContacted) pill = t("main.schema.not_contacted");
  else if (loaded) pill = "✓"; // a skill's bin is narrow: « Chargé » is in its accessible name and tooltip
  if (icon) button.appendChild(el("span", "arch-node-icon", icon));
  // A network node carries its globe on the node itself, not only on its zone (FR-13).
  button.appendChild(el("span", "arch-node-name", network ? `🌐 ${node.label_text}` : node.label_text));
  if (pill) button.appendChild(el("span", "arch-node-pill", pill));

  const tooltip = [`${node.label_text} · ${SHAPE_LABELS[shape]} · ${network ? t("main.hosting.network") : t("main.schema.on_workstation")}`];
  if (unavailable) tooltip.push(t("main.schema.unavailable_reason", { reason: node.reason_text }));
  else if (notContacted) tooltip.push(t("main.schema.not_contacted_title"));
  if (perTurn) {
    const state = attempted && !reached ? t("main.schema.attempt_failed") : turnState;
    tooltip.push(t("main.schema.at_turn", { n: String(schemaTurn.number), state }));
  }
  if (shape === "skill") tooltip.push(loaded ? t("main.schema.loaded") : t("main.schema.not_loaded"));
  if (tools.length) tooltip.push(t("main.schema.tools", { tools: tools.join(", ") }));
  if (node.detail_text) tooltip.push(node.detail_text);
  // Story 23: a network tool or server leads to its outbound data, while a step shown has some
  // (a clearing or a reset leaves the node contacted, with nothing left to show).
  const leadsOut =
    network && (shape === "tool" || shape === "mcp") && Boolean(outboundShown?.has(node.id));
  if (leadsOut) tooltip.push(t("main.schema.leads_out"));
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

// Lot 2 (2026-10-04): the shared diagram's layer (diagram.js) draws them, on the schema's
// rebuilds, its resizes (pane resized, focused, hidden then shown), the fonts and projection.
const schemaWires = wireLayer(document.getElementById("schema"), drawSchemaWires);

// Drawn from the laid-out pieces, after each rebuild and each resize (ResizeObserver): the trunk
// leaves the strip (or the frame), runs under the bins, and crosses the boundary dashed; a rail
// runs 8 px left of each column, with a stub to each bin.
function drawSchemaWires({ height, box }) {
  const arch = document.getElementById("schema");
  const frame = arch.querySelector(".arch-harness");
  if (!frame) return null;
  const F = box(frame);
  const strip = arch.querySelector(".arch-hook-strip");
  const sx = strip ? box(strip).cx : F.r - 40;
  const sy = strip ? box(strip).b : F.b;
  const by = height - 12;
  const fx = box(arch.querySelector(".arch-boundary")).cx;
  const parts = [];
  const rails = new Map();
  let maxRail = sx;
  for (const col of arch.querySelectorAll(".arch-col")) {
    const railX = box(col).l - 8;
    const cls = `diagram-wire${col.closest(".arch-zone-network") ? " is-dashed" : ""}`;
    const stubs = [...col.querySelectorAll(".arch-group")].map((g) => ({ x: box(g).l, y: box(g).t + 12 }));
    if (!stubs.length) continue;
    parts.push(wire(`M${railX},${by} V${Math.min(...stubs.map((s) => s.y))}`, cls));
    for (const s of stubs) parts.push(wire(`M${railX},${s.y} H${s.x}`, cls));
    rails.set(col, railX);
    maxRail = Math.max(maxRail, railX);
  }
  if (maxRail > sx) {
    parts.push(wire(`M${sx},${sy} V${by} H${Math.min(maxRail, fx)}`, "diagram-wire"));
    if (maxRail > fx) parts.push(wire(`M${fx},${by} H${maxRail}`, "diagram-wire is-dashed"));
  }

  const a = schemaActive;
  if (a?.mode === "blocked") {
    // Stopped at the strip: the tool is never reached.
    const y = F.b + 14;
    parts.push(wire(`M${sx},${sy} V${y - 12}`, "diagram-path-block"), marker(sx, y, "✖", "is-block"));
  } else if (a?.mode === "pending") {
    // H5 waits for the user: stopped before the boundary, nothing has left the workstation.
    const stopX = fx - 18;
    const d = `M${sx},${sy} V${by} H${stopX}`;
    parts.push(wire(d, "diagram-path"), wire(d, "diagram-path-core"), marker(stopX, by, "✋", "is-stop"));
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
      parts.push(wire(`M${sx},${sy} V${by} ${tail}`, "diagram-path"));
      if (node.classList.contains("is-network")) {
        // Solid on the workstation, dashed and moving once it crosses the boundary.
        parts.push(
          wire(`M${sx},${sy} V${by} H${fx}`, "diagram-path-core"),
          wire(`M${fx},${by} ${tail}`, "diagram-path-core is-flow")
        );
      } else {
        parts.push(wire(`M${sx},${sy} V${by} ${tail}`, "diagram-path-core"));
      }
    }
  }
  return parts;
}

// ---------- audit log: the whole file, read only (story 8) ----------

async function openAudit() {
  const dialog = document.getElementById("audit-dialog");
  const text = document.getElementById("audit-text");
  document.getElementById("audit-path").textContent = "";
  text.textContent = t("main.audit.reading");
  if (!dialog.open) dialog.showModal();
  try {
    const response = await fetch("/api/audit");
    const body = await response.json().catch(() => ({}));
    if (!response.ok) {
      text.textContent = t("main.audit.failed", { cause: String(body.detail || response.status) });
      return;
    }
    document.getElementById("audit-path").textContent = t("main.memory.file", { path: body.path });
    text.textContent = body.text || t("main.audit.empty");
  } catch {
    text.textContent = t("main.audit.no_answer");
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
  // Languages (2/5): the interface's texts first (`i18n.js` has set `<html lang>` and the
  // `data-i18n*` of the page); every render reads them.
  await textsReady;
  // Remembered pane layout first, so the page does not open on the defaults then jump.
  panes.load();
  // Story 34: the projection mode (NFR-9), panes.js's; the schema's pieces move with it.
  initProjection({
    toggle: document.getElementById("projection-toggle"),
    onChange: () => schemaWires.schedule(),
  });
  bindLinkedView();
  loadShowForced();
  loadShowReasoning();
  loadCtxMode(); // story 32: Contexte LLM's view, remembered by the browser
  document.getElementById("show-reasoning").addEventListener("change", toggleShowReasoning);
  panes.start(); // the gutter handles, the sizes, « — » and ⛶, then the first layout
  renderMenu();

  document.getElementById("pane-menu-toggle").addEventListener("click", () => {
    const list = document.getElementById("pane-menu-list");
    const expanded = !list.hidden;
    list.hidden = expanded;
    document.getElementById("pane-menu-toggle").setAttribute("aria-expanded", String(!expanded));
    if (!expanded) setDisplayMenu(false);
  });

  document.addEventListener("click", (event) => {
    if (!event.target.closest(".pane-menu")) closePaneMenu();
    if (!event.target.closest(".window-picker")) closeWindowPanel();
  });
  bindWindowPicker();

  document.getElementById("composer").addEventListener("submit", sendMessage);
  document.getElementById("composer-stop").addEventListener("click", stopTurn);
  document.getElementById("clear-conversation").addEventListener("click", clearConversation);
  document.getElementById("replay-last").addEventListener("click", replayLast);
  document.getElementById("scenario-picker").addEventListener("change", launchScenario);
  setupScenarioInfo();
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
  // Local stopwatch anchored on the `*_started` ts, replaced by `duration_ms` (AD-1).
  setInterval(() => {
    if (activeTurn()) {
      renderChat();
      renderSteps();
      applyLinks(); // story 34: the rebuilt nodes get their light back
    }
    if (store.modelLoad) {
      renderChat();
      const loadText = modelLoadText();
      if (!store.connectionLost) setTopStatus(loadText, modelLoadTitle() ?? loadText);
    }
  }, 250);

  document.addEventListener("keydown", (event) => {
    // Story 2: an open « Affichage ▾ » menu is closed by site-nav.js first (`defaultPrevented`).
    if (event.key !== "Escape" || event.defaultPrevented) return;
    if (document.getElementById("audit-dialog").open) return; // the dialog closes itself
    if (document.getElementById("cloud-warning").open) return;
    if (!drawer().hidden) {
      closeDrawer();
    } else if (!memoryDrawer().hidden) {
      closeMemoryDrawer();
    } else if (!document.getElementById("pane-menu-list").hidden) {
      closePaneMenu();
    } else if (!windowPanel().hidden) {
      closeWindowPanel(true); // story 26: the focus back on « Fenêtre ▾ »
    } else if (store.selection !== null && selectionShown()) {
      clearSelection(); // story 34: before leaving focus mode
    } else {
      // Story 34: a selection no element shows any more is dropped silently, then Escape
      // does its next job.
      const stale = store.selection !== null;
      if (stale) Object.assign(store, { selection: null, selectionKeys: null });
      if (store.focusedPane !== null) store.focusedPane = null;
      else if (!stale) return;
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
    store.windowState = body.context_window_state ?? null;
    store.consumption = body.consumption_updated ?? null; // FinOps: kept across a reload
    store.maxSessionUsd = body.max_session_usd ?? null;
    if (body.language) {
      store.language = {
        language: body.language,
        languages: body.languages ?? [],
        language_locked: Boolean(body.language_locked),
      };
      // `<html lang>` is i18n.js's: the language of the texts shown (French when they fail).
    }
    const preview = body.context_preview;
    const rendered = body.context_rendered;
    const reconciled = body.context_reconciled;
    const latest = [preview, rendered, reconciled].filter(Boolean).sort((a, b) => b.seq - a.seq)[0];
    if (latest) store.gauge = { payload: latest.payload, preview: latest === preview, callId: latest.call_id ?? null };
  } catch {
    // AD-16: a failed boot fetch still lets the live stream take over.
  }
  render();
  loadModelList();

  // Replay the whole journal: a reload rebuilds past and in-progress turns (AD-1). Once it
  // reaches the snapshot's tip, the page says so (`data-journal-replayed`, read by the E2E run).
  const replayed = () => (document.body.dataset.journalReplayed = "true");
  if (store.liveFrom === 0) replayed();
  streamEvents(
    0,
    (envelope) => {
      applyEnvelope(envelope);
      if (envelope.seq >= store.liveFrom) replayed();
    },
    (connected) => {
      // E003: « Connexion au serveur perdue… » in the top bar, gone with the first event.
      if (store.connectionLost === !connected) return;
      store.connectionLost = !connected;
      if (connected) delete document.body.dataset.connection;
      else document.body.dataset.connection = "lost";
      render();
    }
  );
}

boot();
