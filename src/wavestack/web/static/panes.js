// Lot 4 of the 2026-10-04 corrections plan (AD-28): the panes' mechanics, out of the Atelier
// Harnais so the workshops (the MCP one first) lay out their panes the same way: hide (« — »),
// focus (⛶), gutter handles (mouse, arrow keys, double click back to the defaults), the chips
// « + Nom du volet » of the hidden panes, the layout remembered by the browser, and the
// projection mode. Rules in pages.css (`pane-*`, `:root.projection`), texts in ui.yaml
// (`common.panes`). Call after i18n.js's `ready`.
//
// The layout this module drives (classes and attributes the page writes):
//
//   <div class="layout" id="layout">              ← `layout`, the size variables set on it
//     <section class="pane" data-pane="{left}">   ← width `--pane-{left}-width` (px)
//     <div class="right">
//       <div class="top-row">                     ← the `row` panes, weights `--pane-{id}-grow`
//         <section class="pane" data-pane="{id}">…
//       </div>
//       <section class="pane" data-pane="{bottom}"> ← height `--pane-{bottom}-height` (px)
//     </div>
//   </div>
//
// Each `.pane` holds `[data-action="focus"]` (⛶) and, unless it is `pinned`, `[data-action=
// "hide"]` (« — »). The page's CSS gives the panes their flex sizes from these variables (see
// app.css, `.layout`); `left`, `bottom` or `row` may be left out. The module toggles
// `.pane.is-hidden`, `.pane.is-focused`, `body.focus-mode`, inserts `.pane-resize-handle`
// separators (`data-handle` = the pane before it, the bottom one after `.top-row`) and fills the
// chips container with `button.pane-chip`.
//
// export createPanes(options) → controller
//   options: { panes: [ids], labels: {id: name}, storageKey, layout: Element,
//              left?, row?: [ids], bottom?, pinned?: [ids], chips?: Element,
//              chipState?(id) → { linked?, awaiting?, title? }, onChange?() }
//   controller: { hidden: Set, focused (get/set), sizes, isVisible(id), canHide(id),
//                 hide(id), show(id), toggle(id), toggleFocus(id), load(), save(), start(),
//                 render(), renderChips(), scheduleHandleValues() }
//   `load()` reads the stored layout (call it first, before the first render); `start()`
//   inserts the handles, applies the sizes and binds the buttons; `render()` lays out what is
//   hidden and focused and redraws the chips. `hide`, `show`, `toggle` and `toggleFocus` save
//   and call `onChange`, which re-renders the page (and so `render()`).
// export initProjection({ toggle?: Element, onChange?(on) }) → { on, set(on), toggle() }
//   The projection mode (`:root.projection`), remembered under `wavestack.projection`, shared by
//   every page that offers it.

import { t } from "./i18n.js";

const MIN_WIDTH = 240; // as pages.css (--pane-min-width / --pane-min-height)
const MIN_HEIGHT = 160;
const STEP = 16;

// WCAG 2.5.3: the accessible name starts with the visible text (« {label} : {value} »).
const labelValue = (label, value) => t("common.format.label_value", { label, value });

export function createPanes({
  panes,
  labels,
  storageKey,
  layout,
  left = null,
  row = [],
  bottom = null,
  pinned = [],
  chips = null,
  chipState = () => ({}),
  onChange = () => {},
}) {
  const hidden = new Set();
  const sizes = {};
  let focused = null;
  let chipsKey = null;
  let valuesFrame = 0;
  const hideable = panes.filter((p) => !pinned.includes(p));
  const pxVar = (id) => (id === bottom ? `--pane-${id}-height` : `--pane-${id}-width`);
  const sizeVars = Object.fromEntries([
    ...(left ? [[left, pxVar(left)]] : []),
    ...(bottom ? [[bottom, pxVar(bottom)]] : []),
    ...row.map((id) => [id, `--pane-${id}-grow`]),
  ]);
  const inPx = (id) => id === left || id === bottom;
  const section = (id) => layout.querySelector(`.pane[data-pane="${id}"]`);
  const topRow = () => layout.querySelector(".top-row");
  const isVisible = (id) => !hidden.has(id);
  const visibleCount = () => panes.filter(isVisible).length;
  const canHide = (id) => !pinned.includes(id) && (hidden.has(id) || visibleCount() > 1);

  // ---------- the stored layout ----------

  // Sizes and hidden panes survive a reload (not the focus mode). Missing, unreadable or corrupt
  // storage leaves the defaults, silently.
  function load() {
    let saved = null;
    try {
      saved = JSON.parse(localStorage.getItem(storageKey));
    } catch {
      return;
    }
    if (!saved || typeof saved !== "object") return;
    const stored = saved.sizes && typeof saved.sizes === "object" ? saved.sizes : {};
    for (const key of Object.keys(sizeVars)) {
      const value = stored[key];
      const max = inPx(key) ? 100000 : 100;
      if (typeof value === "number" && Number.isFinite(value) && value > 0 && value <= max) {
        sizes[key] = value;
      }
    }
    if (Array.isArray(saved.hidden)) {
      const wanted = new Set(saved.hidden.filter((p) => hideable.includes(p)));
      if (wanted.size < panes.length) {
        // at least one stays visible
        hidden.clear();
        for (const p of wanted) hidden.add(p);
      }
    }
  }

  function save() {
    try {
      localStorage.setItem(storageKey, JSON.stringify({ hidden: [...hidden], sizes }));
    } catch {
      // No storage (private window, blocked site data): the layout just won't be remembered.
    }
  }

  // ---------- hide, show, focus ----------

  function hide(id) {
    if (!canHide(id) || hidden.has(id)) return;
    hidden.add(id);
    save();
    onChange();
  }

  function show(id) {
    if (!hidden.delete(id)) return;
    save();
    onChange();
  }

  function toggle(id) {
    if (hidden.has(id)) show(id);
    else hide(id);
  }

  function toggleFocus(id) {
    focused = focused === id ? null : id;
    onChange();
  }

  function renderChips() {
    if (!chips) return;
    const shown = [...hidden].map((id) => ({ id, ...chipState(id) }));
    // Rebuilt only when it changes: a page may call it on each hover, under the pointer.
    const key = JSON.stringify(shown);
    if (key === chipsKey) return;
    chipsKey = key;
    chips.innerHTML = "";
    for (const { id, awaiting, linked, title } of shown) {
      const chip = document.createElement("button");
      chip.type = "button";
      chip.className = "pane-chip";
      const name = labels[id];
      chip.textContent = `+ ${name}${linked ? ` · ${t("common.panes.linked")}` : ""}`;
      if (awaiting || linked) {
        chip.classList.add("is-linked");
        const dot = document.createElement("span");
        dot.className = "pane-chip-dot";
        dot.textContent = "● ";
        dot.setAttribute("aria-hidden", "true");
        chip.prepend(dot);
      }
      chip.title =
        title ??
        (linked ? t("common.panes.show_linked", { pane: name }) : t("common.panes.show", { pane: name }));
      chip.setAttribute("aria-label", labelValue(chip.textContent.replace(/^● /, ""), chip.title));
      chip.addEventListener("click", () => show(id));
      chips.appendChild(chip);
    }
  }

  function renderVisibility() {
    document.body.classList.toggle("focus-mode", focused !== null);
    for (const id of panes) {
      const pane = section(id);
      if (!pane) continue;
      pane.classList.toggle("is-hidden", hidden.has(id));
      pane.classList.toggle("is-focused", focused === id);
      const button = pane.querySelector('[data-action="hide"]');
      if (!button) continue;
      // aria-disabled, never `disabled`: the button keeps the focus (AD-28).
      const unavailable = !canHide(id);
      button.setAttribute("aria-disabled", String(unavailable));
      button.title = unavailable ? t("common.panes.one_visible") : t("common.panes.hide", { pane: labels[id] });
      button.setAttribute("aria-label", button.title);
    }
    // A handle only stands between two visible neighbours, never in focus mode.
    for (const handle of layout.querySelectorAll(".pane-resize-handle")) {
      const pair = focused === null ? neighbours(handle.dataset.handle) : null;
      handle.hidden = !pair;
      if (pair) handle.setAttribute("aria-label", pair.label);
    }
    scheduleHandleValues();
  }

  function render() {
    renderVisibility();
    renderChips();
  }

  // ---------- resizing: gutter handles, mouse and keyboard ----------

  // The two neighbours a handle moves the boundary between, or null when it has no place (one
  // side hidden). `before` / `after` are the elements measured; `label` names both panes.
  function neighbours(handleId) {
    if (handleId === left) {
      if (!isVisible(left) || ![...row, ...(bottom ? [bottom] : [])].some(isVisible)) return null;
      return {
        before: section(left),
        after: layout.querySelector(".right"),
        label: t("common.panes.resize_left", { pane: labels[left] }),
      };
    }
    if (handleId === bottom) {
      const top = row.filter(isVisible);
      if (!top.length || !isVisible(bottom)) return null;
      return {
        before: topRow(),
        after: section(bottom),
        label: t("common.panes.resize_bottom", { names: top.map((p) => labels[p]).join(", "), pane: labels[bottom] }),
      };
    }
    const next = row.slice(row.indexOf(handleId) + 1).find(isVisible);
    if (!isVisible(handleId) || !next) return null;
    return {
      before: section(handleId),
      after: section(next),
      beforeId: handleId,
      afterId: next,
      label: t("common.panes.resize_between", { a: labels[handleId], b: labels[next] }),
    };
  }

  // Current sizes along the handle's axis. For a row handle, also the width and the weight
  // shared by the visible columns, to turn pixels back into weights.
  function measure(handleId) {
    const pair = neighbours(handleId);
    if (!pair) return null;
    const vertical = handleId === bottom;
    const size = (node) => {
      const rect = node.getBoundingClientRect();
      return vertical ? rect.height : rect.width;
    };
    const m = { handleId, pair, a: size(pair.before), b: size(pair.after) };
    m.min = vertical ? MIN_HEIGHT : MIN_WIDTH;
    m.minAfter = m.min;
    if (handleId === left) {
      // Every visible row column keeps its minimum, not just the right side as a whole: the
      // narrowest share (smallest weight) sets the width the columns need together.
      const weights = row.filter(isVisible).map((p) => sizes[p] ?? 1);
      if (weights.length > 1) {
        const gutter = parseFloat(getComputedStyle(topRow()).columnGap) || 0;
        const sum = weights.reduce((total, w) => total + w, 0);
        m.minAfter = (MIN_WIDTH * sum) / Math.min(...weights) + (weights.length - 1) * gutter;
      }
    }
    if (row.includes(handleId)) {
      const visible = row.filter(isVisible);
      m.total = visible.reduce((sum, p) => sum + size(section(p)), 0);
      m.weight = visible.reduce((sum, p) => sum + (sizes[p] ?? 1), 0);
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
    if (m.handleId === left) {
      sizes[left] = Math.round(a);
    } else if (m.handleId === bottom) {
      sizes[bottom] = Math.round(m.a + m.b - a);
    } else if (m.total > 0) {
      // Weights of the two neighbours only, their sum unchanged: the other columns do not move.
      sizes[m.pair.beforeId] = round((a / m.total) * m.weight);
      sizes[m.pair.afterId] = round(((m.a + m.b - a) / m.total) * m.weight);
    }
    applySizes();
    updateHandleValues();
  }

  // Double-click: default proportions for what this handle moves.
  function resetBoundary(handleId) {
    if (handleId === left || handleId === bottom) delete sizes[handleId];
    else for (const p of row) delete sizes[p];
    applySizes();
    save();
    updateHandleValues();
  }

  function applySizes() {
    for (const [key, name] of Object.entries(sizeVars)) {
      const value = sizes[key];
      if (value === undefined) layout.style.removeProperty(name);
      else layout.style.setProperty(name, inPx(key) ? `${value}px` : String(value));
    }
  }

  // aria-valuenow: share (%) of what precedes the handle, out of both neighbours.
  function updateHandleValues() {
    for (const handle of layout.querySelectorAll(".pane-resize-handle")) {
      if (handle.hidden) continue;
      const m = measure(handle.dataset.handle);
      const total = m ? m.a + m.b : 0;
      if (!total) continue;
      const pct = (value) => String(Math.round((value / total) * 100));
      handle.setAttribute("aria-valuenow", pct(m.a));
      handle.setAttribute("aria-valuemin", pct(Math.min(m.min, m.a)));
      handle.setAttribute("aria-valuemax", pct(Math.max(total - m.minAfter, m.a)));
    }
  }

  function scheduleHandleValues() {
    if (valuesFrame) return;
    valuesFrame = requestAnimationFrame(() => {
      valuesFrame = 0;
      updateHandleValues();
    });
  }

  function createHandles() {
    // One handle after the left pane and after each row pane but the last; the bottom one
    // between the top row and the bottom pane.
    const ids = [...(left ? [left] : []), ...row.slice(0, -1), ...(bottom && row.length ? [bottom] : [])];
    for (const handleId of ids) {
      const horizontal = handleId === bottom;
      const handle = document.createElement("div");
      handle.className = "pane-resize-handle";
      handle.dataset.handle = handleId;
      handle.setAttribute("role", "separator");
      handle.setAttribute("aria-orientation", horizontal ? "horizontal" : "vertical");
      handle.tabIndex = 0;
      handle.hidden = true;
      (horizontal ? topRow() : section(handleId)).after(handle);

      let drag = null;
      const endDrag = () => {
        if (!drag) return;
        if (drag.moved) save();
        drag = null;
        handle.classList.remove("is-dragging");
        document.body.classList.remove("is-resizing-x", "is-resizing-y");
      };
      handle.addEventListener("pointerdown", (event) => {
        if (event.button !== 0) return;
        const m = measure(handleId);
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
        const m = measure(handleId);
        if (!m) return;
        moveBoundary(m, direction ? STEP : -STEP);
        save();
      });
    }
  }

  // The handles, the sizes, the pane buttons, then the first layout.
  function start() {
    createHandles();
    applySizes();
    for (const id of panes) {
      const pane = section(id);
      pane?.querySelector('[data-action="hide"]')?.addEventListener("click", () => hide(id));
      pane?.querySelector('[data-action="focus"]')?.addEventListener("click", () => toggleFocus(id));
    }
    render();
    // aria-valuenow follows the window too (the left and bottom panes are in px).
    new ResizeObserver(scheduleHandleValues).observe(layout);
  }

  return {
    hidden,
    sizes,
    get focused() {
      return focused;
    },
    set focused(id) {
      focused = id;
    },
    isVisible,
    canHide,
    hide,
    show,
    toggle,
    toggleFocus,
    load,
    save,
    start,
    render,
    renderChips,
    scheduleHandleValues,
  };
}

// ---------- the projection mode (story 34, NFR-9) ----------
// Every text a notch larger (the ramp × 9/7, in pages.css), remembered by the browser; the
// reset leaves it, like the panes' layout. Without storage, it works until the next reload.

const PROJECTION_STORAGE_KEY = "wavestack.projection";

export function initProjection({ toggle = null, onChange = () => {} } = {}) {
  const set = (on) => {
    document.documentElement.classList.toggle("projection", on);
    toggle?.setAttribute("aria-pressed", String(on));
    onChange(on);
  };
  let on = false;
  try {
    on = localStorage.getItem(PROJECTION_STORAGE_KEY) === "1";
  } catch {
    // No storage: the default size.
  }
  set(on);
  const projection = {
    get on() {
      return document.documentElement.classList.contains("projection");
    },
    set,
    toggle() {
      const next = !projection.on;
      set(next);
      try {
        localStorage.setItem(PROJECTION_STORAGE_KEY, next ? "1" : "0");
      } catch {
        // No storage: the mode lasts until the page is reloaded.
      }
    },
  };
  toggle?.addEventListener("click", () => projection.toggle());
  return projection;
}
