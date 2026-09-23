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
};

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
  if (envelope.kind === "session_state") {
    store.sessionState = envelope.payload;
  } else if (envelope.kind === "architecture_changed") {
    store.architecture = envelope.payload;
  }
  render();
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
  renderJournal();
  renderSchema();
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

  document.addEventListener("keydown", (event) => {
    if (event.key !== "Escape") return;
    if (!document.getElementById("pane-menu-list").hidden) {
      closePaneMenu();
    } else if (store.focusedPane !== null) {
      store.focusedPane = null;
      render();
    }
  });

  let bootSeq = 0;
  try {
    const response = await fetch("/api/state");
    const body = await response.json();
    store.sessionState = body.session_state;
    store.architecture = body.architecture_changed || { nodes: [], edges: [] };
    bootSeq = body.seq || 0;
  } catch {
    // AD-16: a failed boot fetch still lets the live stream take over.
  }
  render();

  streamEvents(bootSeq, applyEnvelope);
}

boot();
