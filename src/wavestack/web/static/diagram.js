// Lot 2 of the 2026-10-04 corrections plan: the shared diagram, out of the Atelier Harnais so
// the MCP, RAG and LLM workshops (lots 4 to 6) speak the same visual language. HTML blocks
// laid out by the page, an SVG layer of wires drawn over them once they are laid out, a block
// lit by `is-active` (the halo), a stepper (◀ ▶ and « Suivre le direct ») fed by the real
// events, and a block's explanation on a click. Rules in pages.css (`diagram-*`), colours by
// the tokens of tokens.css only. Formatting only (AD-1): what is lit, drawn or shown is the
// page's to decide.
// - `explain()` relies on CSS anchor positioning: Chromium only, as the bricks' « ? », accepted
//   for the demo's target browser (Edge or Chrome on the PC).
// - `createStepper()` reads its labels when it is built: call it after i18n.js's `ready`.
// Lot 4 (2026-10-04, AD-28): the module's retouches, valid for every page that imports it: an
// ink ring under the halo, the path's core at `--spacing-stroke-path`, ◀ ▶ in `aria-disabled`,
// « Suivre le direct » pressed in solid with « ● », the stepper's own `status` node, `explain()`
// closed when the focus leaves, `reveal()` for the progressive discovery, and the stepper's
// options `describe` and `onLive`, its methods `load()` and `refresh()`.

import { t } from "./i18n.js";

export const SVG_NS = "http://www.w3.org/2000/svg";

export function svgEl(tag, attrs = {}) {
  const node = document.createElementNS(SVG_NS, tag);
  for (const [key, value] of Object.entries(attrs)) node.setAttribute(key, String(value));
  return node;
}

// ---------- blocks ----------

// A block of the diagram: a button (Tab reaches it, Enter clicks it), `diagram-block` after the
// page's own classes.
export function block(className = "", text) {
  const node = document.createElement("button");
  node.type = "button";
  node.className = className ? `${className} diagram-block` : "diagram-block";
  if (text !== undefined) node.textContent = text;
  return node;
}

// Lights `nodes` (a block, a list of blocks, or nothing) among the blocks of `root`: `is-active`
// on them (made blocks, so the next call puts them out), off on every other one.
export function light(root, nodes) {
  const lit = new Set(nodes ? (nodes instanceof Element ? [nodes] : nodes) : []);
  for (const node of root.querySelectorAll(".diagram-block.is-active")) {
    if (!lit.has(node)) node.classList.remove("is-active");
  }
  for (const node of lit) node.classList.add("diagram-block", "is-active");
}

// ---------- progressive discovery (lot 4, AD-28) ----------

// Shows `node` (an element of the diagram, HTML or SVG, or a list of them) or hides it:
// `diagram-unrevealed` (pages.css) keeps its place and takes it out of the accessibility tree.
// Appearing, it fades in briefly (`diagram-revealing`), but under `prefers-reduced-motion`.
// What is visible at a step is the page's to decide (AD-1: formatting only).
export function reveal(node, on) {
  if (!node) return;
  if (!(node instanceof Element)) {
    for (const one of node) reveal(one, on);
    return;
  }
  const hidden = node.classList.contains("diagram-unrevealed");
  node.classList.toggle("diagram-unrevealed", !on);
  if (!on) {
    node.classList.remove("diagram-revealing");
    return;
  }
  if (!hidden) return;
  node.classList.remove("diagram-revealing");
  void node.getBoundingClientRect(); // the animation starts again
  node.classList.add("diagram-revealing");
  node.addEventListener("animationend", () => node.classList.remove("diagram-revealing"), { once: true });
}

// ---------- wires ----------

// A wire: a path of the layer, its look by its classes (`diagram-wire`, `diagram-path`,
// `diagram-path-core`, `is-flow`, `diagram-path-block`, see pages.css).
export function wire(d, className) {
  return svgEl("path", { d, class: className });
}

// A round marker on a wire (`is-stop` ✋, `is-block` ✖).
export function marker(x, y, text, className = "") {
  const g = svgEl("g", { class: `diagram-marker ${className}`.trim() });
  const label = svgEl("text", { x, y: y + 4, "text-anchor": "middle" });
  label.textContent = text;
  g.append(svgEl("circle", { cx: x, cy: y, r: 12 }), label);
  return g;
}

// `node`'s box relative to `origin` (a DOMRect): its edges and its centre.
export function measure(node, origin) {
  const r = node.getBoundingClientRect();
  return {
    l: r.left - origin.left,
    t: r.top - origin.top,
    r: r.right - origin.left,
    b: r.bottom - origin.top,
    cx: (r.left + r.right) / 2 - origin.left,
    cy: (r.top + r.bottom) / 2 - origin.top,
  };
}

// The SVG layer over `host` (positioned by the page): `draw({ width, height, box })` returns the
// wires and markers (`null`: the layer is left as it is), `box(node)` measuring a piece of the
// host. Drawn once per frame at most (`schedule()`), and again when the host is resized (a pane
// resized, focused, hidden then shown) or the fonts are loaded. A host of no size (a hidden
// pane) draws nothing. `clear()` empties the layer (the host rebuilt).
export function wireLayer(host, draw) {
  const svg = svgEl("svg", { class: "diagram-wires", "aria-hidden": "true" });
  host.appendChild(svg);
  let pending = false;
  const render = () => {
    pending = false;
    if (svg.parentNode !== host) host.appendChild(svg); // the host was emptied
    const origin = host.getBoundingClientRect();
    if (!origin.width || !origin.height) return;
    svg.setAttribute("width", origin.width);
    svg.setAttribute("height", origin.height);
    svg.setAttribute("viewBox", `0 0 ${origin.width} ${origin.height}`);
    const parts = draw({ width: origin.width, height: origin.height, box: (node) => measure(node, origin) });
    if (parts) svg.replaceChildren(...parts);
  };
  const schedule = () => {
    if (pending) return;
    pending = true;
    requestAnimationFrame(render);
  };
  new ResizeObserver(schedule).observe(host);
  document.fonts?.ready.then(schedule);
  return { svg, schedule, clear: () => svg.replaceChildren() };
}

// ---------- a block's explanation, on a click ----------

const explanations = new WeakMap(); // block -> its popover
let anchors = 0;

// The block's click opens `text` in a popover anchored to it (CSS anchor positioning, Chromium,
// as the bricks' « ? »); Escape or a click elsewhere closes it (native `popover`), and so does
// the focus leaving the block for anything but the popover (lot 4: the popover is focusable,
// `tabindex="-1"`, and a click in it keeps it open). Without a text, no popover. `node` is a
// button (`block()`): it is the popover's invoker.
export function explain(node, text) {
  let popover = explanations.get(node);
  if (!text) {
    if (popover) {
      popover.remove();
      explanations.delete(node);
      node.popoverTargetElement = null;
    }
    return null;
  }
  if (!popover) {
    anchors += 1;
    const anchor = `--diagram-anchor-${anchors}`;
    node.style.setProperty("anchor-name", anchor);
    popover = document.createElement("div");
    popover.className = "diagram-explain";
    popover.setAttribute("popover", "");
    popover.tabIndex = -1;
    popover.style.setProperty("position-anchor", anchor);
    explanations.set(node, popover);
    node.popoverTargetElement = popover;
    // Beside its block, which the page may have placed after this call: the click's listeners
    // run before the invoker opens the popover.
    node.addEventListener("click", () => {
      const current = explanations.get(node);
      if (current && !current.isConnected) node.after(current);
    });
    // Lot 4 (AD-28): the focus gone elsewhere than the block or its popover closes it.
    const leave = (event) => {
      const current = explanations.get(node);
      if (!current || !current.matches(":popover-open")) return;
      const to = event.relatedTarget;
      if (to && (node.contains(to) || current.contains(to))) return;
      current.hidePopover();
    };
    node.addEventListener("focusout", leave);
    popover.addEventListener("focusout", leave);
  }
  popover.textContent = text;
  if (node.parentNode && !popover.isConnected) node.after(popover);
  return popover;
}

// ---------- the stepper: ◀ ▶ and « Suivre le direct » ----------

// In `host`: ◀, the position (« n / total »), ▶ and « Suivre le direct ». `push(frame)` adds a
// step (a real event); while live, the last one is shown and followed. ◀, ▶ or `show(i)` leave
// the live mode (`show` does nothing with no step): the next pushes no longer move the view;
// `follow()` (its button) goes back to the last step and follows it. `onShow(frame, index)` draws
// the step shown. A bound greys its button (`aria-disabled`, never `disabled`: it keeps the
// focus; a click on it does nothing); with no step, both are grey and the position hidden.
// `clear()`: no step, live, and `onShow(null, -1)` so the page erases the step it drew.
// Lot 4 (AD-28):
// - `describe(frame, index)` names a step: out of live mode, the stepper's own `status` node
//   (polite, visually hidden) says « Étape n sur N : {name} », else the position only; it says
//   nothing while live, and the visible position is no longer a live region;
// - `onLive(live)` is called at each change of the live mode (the page suspends its scrolling);
// - `load(frames)` puts back a whole series at once (a reload), live, with a single `onShow` on
//   the last frame (`onShow(null, -1)` for none); `refresh()` draws the current step again
//   without touching the live mode.
// The frames stay opaque to the module: the page decides what a step is (AD-27).
// Lot 6 (2026-10-04): `liveText`, the right button's text for a stepper over fixed steps
// (« Tout montrer », the last one), `common.diagram.live` by default; such a stepper has no
// live stream, so its button shows no ● dot.
export function createStepper(host, { onShow, describe, onLive, liveText } = {}) {
  const frames = [];
  let index = -1;
  let live = true;
  const bar = document.createElement("div");
  bar.className = "diagram-stepper";
  bar.setAttribute("role", "group");
  bar.setAttribute("aria-label", t("common.diagram.label"));
  const button = (className, text, label) => {
    const node = document.createElement("button");
    node.type = "button";
    node.className = className;
    node.textContent = text;
    if (label) {
      node.setAttribute("aria-label", label);
      node.title = label;
    }
    return node;
  };
  const prev = button("diagram-step-prev", "◀", t("common.diagram.prev"));
  const next = button("diagram-step-next", "▶", t("common.diagram.next"));
  const follow = button("diagram-step-live", "");
  const dot = document.createElement("span");
  dot.className = "diagram-step-live-dot";
  dot.setAttribute("aria-hidden", "true");
  dot.textContent = "● ";
  follow.append(dot, liveText || t("common.diagram.live"));
  const position = document.createElement("span");
  position.className = "diagram-step-position";
  // Reserved to the stepper (AD-28): the page's own `status` region says its summaries only.
  const status = document.createElement("span");
  status.className = "diagram-step-status";
  status.setAttribute("role", "status");
  status.setAttribute("aria-live", "polite");
  bar.append(prev, position, next, follow, status);
  host.appendChild(bar);

  const announce = () => {
    if (live || index < 0) {
      status.textContent = "";
      return;
    }
    const total = frames.length;
    const name = describe ? describe(frames[index], index) : "";
    status.textContent = name
      ? t("common.diagram.announce", { n: index + 1, total, name })
      : t("common.diagram.position", { n: index + 1, total });
  };
  const update = () => {
    const total = frames.length;
    prev.setAttribute("aria-disabled", String(index <= 0));
    next.setAttribute("aria-disabled", String(index < 0 || index >= total - 1));
    position.hidden = total === 0;
    position.textContent = total ? t("common.diagram.position", { n: index + 1, total }) : "";
    follow.setAttribute("aria-pressed", String(live));
    dot.hidden = !live || Boolean(liveText);
    bar.classList.toggle("is-live", live);
  };
  const setLive = (value) => {
    if (live === value) return;
    live = value;
    onLive?.(live);
  };
  const go = (i) => {
    index = frames.length ? Math.max(0, Math.min(i, frames.length - 1)) : -1;
    update();
    announce();
    if (index >= 0) onShow?.(frames[index], index);
  };

  const stepper = {
    element: bar,
    status,
    get frames() {
      return [...frames];
    },
    get index() {
      return index;
    },
    get live() {
      return live;
    },
    push(frame) {
      frames.push(frame);
      if (live) go(frames.length - 1);
      else update();
    },
    show(i) {
      if (!frames.length) return;
      setLive(false);
      go(i);
    },
    follow() {
      setLive(true);
      go(frames.length - 1);
    },
    clear() {
      frames.length = 0;
      setLive(true);
      go(-1);
      onShow?.(null, -1);
    },
    load(list) {
      frames.length = 0;
      frames.push(...list);
      setLive(true);
      go(frames.length - 1);
      if (!frames.length) onShow?.(null, -1);
    },
    refresh() {
      update();
      announce();
      if (index >= 0) onShow?.(frames[index], index);
    },
  };
  // A bound's button stays focusable and does nothing.
  prev.addEventListener("click", () => {
    if (index > 0) stepper.show(index - 1);
  });
  next.addEventListener("click", () => {
    if (index >= 0 && index < frames.length - 1) stepper.show(index + 1);
  });
  follow.addEventListener("click", () => stepper.follow());
  update();
  return stepper;
}
