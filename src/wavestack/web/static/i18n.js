// Languages (2/5): the interface's texts in the session's language (`content/ui.yaml`, served
// by `GET /api/ui_texts`), and the number, date and list formats of that language. Loaded by
// every page, like theme.js; `app.js` imports it and awaits `ready` before its first render.
//
// - `t(key, vars)`: the text of `key` (`main.top_bar.reset`), `{name}` replaced by
//   `vars.name` (a number formatted in the language); a `{one, other}` pair is chosen by
//   `Intl.PluralRules` when `vars.count` is given. A missing key gives the key itself, said
//   in the console (the server already fills a translation's gaps with French).
// - The HTML keeps its French text: `data-i18n` (the text), `data-i18n-title`,
//   `data-i18n-aria-label` and `data-i18n-placeholder` name the key replacing it, so the page
//   stays readable when the route fails.

const LOCALES = { fr: "fr-FR", en: "en-GB", de: "de-DE" };
const ATTRIBUTES = [
  ["i18nTitle", "title"],
  ["i18nAriaLabel", "aria-label"],
  ["i18nPlaceholder", "placeholder"],
];

let lang = "fr";
let texts = {};
const warned = new Set();
// A page being left (a reload, a link) aborts its requests: nothing to say about it.
let leaving = false;
addEventListener("pagehide", () => (leaving = true));
const formats = new Map();

export const language = () => lang;
export const locale = () => LOCALES[lang];

function lookup(key) {
  let value = texts;
  for (const part of key.split(".")) {
    if (value === null || typeof value !== "object") return undefined;
    value = value[part];
  }
  return value;
}

function warn(key) {
  if (leaving || warned.has(key)) return;
  warned.add(key);
  console.warn(`i18n : clé absente du catalogue : ${key}`);
}

// A cached `Intl` formatter of the language, by its options.
function cached(kind, options, make) {
  const id = `${kind}|${lang}|${JSON.stringify(options)}`;
  if (!formats.has(id)) formats.set(id, make());
  return formats.get(id);
}

export const numberFormat = (options = {}) =>
  cached("number", options, () => new Intl.NumberFormat(locale(), options));
export const dateTimeFormat = (options = {}) =>
  cached("date", options, () => new Intl.DateTimeFormat(locale(), options));
const pluralRules = () => cached("plural", {}, () => new Intl.PluralRules(locale()));

// « a, b et c », « a, b and c », « a, b und c ».
export const joinList = (items) =>
  cached("list", {}, () => new Intl.ListFormat(locale(), { style: "long", type: "conjunction" })).format(items);

const shown = (value) =>
  typeof value === "number" ? numberFormat({ maximumFractionDigits: 1 }).format(value) : String(value);

export function has(key) {
  return lookup(key) !== undefined;
}

export function t(key, vars = {}) {
  let value = lookup(key);
  if (value !== null && typeof value === "object" && typeof vars.count === "number") {
    value = value[pluralRules().select(vars.count)] ?? value.other;
  }
  if (typeof value !== "string") {
    warn(key);
    return key;
  }
  return value.replace(/\{(\w+)\}/g, (whole, name) => (name in vars ? shown(vars[name]) : whole));
}

// A table of labels by id (`main.orch.hook_decisions`), read at each access: `table[id]` is
// the text of `{prefix}.{id}`, `undefined` for an id the section lacks (the caller's
// fallback applies); `Object.keys`, `Object.entries` and `in` see the section's keys.
export function section(prefix) {
  const node = () => {
    const value = lookup(prefix);
    if (value === null || typeof value !== "object") {
      warn(prefix);
      return {};
    }
    return value;
  };
  return new Proxy(
    {},
    {
      get: (_, id) => (typeof id === "string" && id in node() ? t(`${prefix}.${id}`) : undefined),
      has: (_, id) => typeof id === "string" && id in node(),
      ownKeys: () => Object.keys(node()),
      getOwnPropertyDescriptor: (_, id) =>
        typeof id === "string" && id in node()
          ? { value: t(`${prefix}.${id}`), enumerable: true, configurable: true }
          : undefined,
    }
  );
}

// Languages (4/5): the links of the pages' navigation (`nav[data-i18n-links]`), named by their
// address (`/llm` → `common.links.llm`) or their id (`open-link` → `common.links.open`): each
// page keeps its links' HTML as it is.
const LINK_NAMES = { "/diagnostic": "diagnostic", "/models": "models", "/llm": "llm", "/rag": "rag" };
const LINK_IDS = { "open-link": "open" };

// The `data-i18n*` attributes of `root` and below: each names the key of its text or attribute.
// A key the catalogue lacks leaves the French of the HTML.
export function applyTexts(root = document) {
  for (const node of root.querySelectorAll("[data-i18n]")) {
    if (has(node.dataset.i18n)) node.textContent = t(node.dataset.i18n);
  }
  for (const link of root.querySelectorAll("[data-i18n-links] a:not([data-i18n])")) {
    const name = LINK_IDS[link.id] ?? LINK_NAMES[link.getAttribute("href")];
    if (name && has(`common.links.${name}`)) link.textContent = t(`common.links.${name}`);
  }
  for (const [data, attribute] of ATTRIBUTES) {
    const selector = `[data-${data.replace(/[A-Z]/g, (c) => `-${c.toLowerCase()}`)}]`;
    for (const node of root.querySelectorAll(selector)) {
      if (has(node.dataset[data])) node.setAttribute(attribute, t(node.dataset[data]));
    }
  }
}

export const ready = (async () => {
  try {
    const response = await fetch("/api/ui_texts");
    if (!response.ok) throw new Error(`HTTP ${response.status}`);
    const body = await response.json();
    lang = body.language in LOCALES ? body.language : "fr";
    texts = body.texts && typeof body.texts === "object" ? body.texts : {};
  } catch (error) {
    if (!leaving) console.warn(`i18n : textes de l'interface indisponibles (${error.message}) : la page reste en français.`);
  }
  document.documentElement.lang = lang;
  if (document.readyState === "loading") {
    await new Promise((resolve) => document.addEventListener("DOMContentLoaded", resolve, { once: true }));
  }
  applyTexts();
})();
