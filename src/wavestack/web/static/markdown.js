// Recette du 02/10: the model's final answer, rendered from its Markdown in the Vue humain
// only (every other view keeps the raw text). A small subset, built node by node with
// `createElement`, `textContent` and `createTextNode`: no HTML string is ever parsed, so the
// HTML a model writes shows as text. No third-party library, no network.
//
// Rendered: paragraphs (a single line break gives a line break), bold and italic (an
// underscore only at a word's edge, so `snake_case` stays whole), bullet and numbered lists
// nested by indentation, headings `#` to `######` (h3 to h6, under the panes' titles),
// inline code, fenced code blocks (one still open while streaming runs to the end), backslash
// escapes, and `[text](url)` links whose URL is absolute `http:` or `https:`. Anything else
// (tables, quotes, strikethrough, rules, images, autolinks, an unsafe link) stays text.

const FENCE = /^(\s*)(`{3,}|~{3,})\s*([^\s`]*)[^`]*$/;
const HEADING = /^ {0,3}(#{1,6})[ \t]+(.+?)(?:[ \t]+#+)?[ \t]*$/;
const ITEM = /^(\s*)(?:([-*+])|(\d{1,9})([.)]))[ \t]+(.*)$/;
const RULE = /^\s*([-*_])(?:\s*\1){2,}\s*$/; // a rule stays text, never a list item
const ESCAPABLE = "!\"#$%&'()*+,-./:;<=>?@[\\]^_`{|}~";
const WORD = /[\p{L}\p{N}]/u;
const SPACE = /\s/;

/** The rendering of `text`, as a `DocumentFragment`. */
export function renderMarkdown(text) {
  const root = document.createDocumentFragment();
  const lines = String(text ?? "").split(/\r?\n/);
  let paragraph = []; // the current paragraph's lines
  const lists = []; // the open lists, outermost first: { indent, ordered, node, item }
  let blank = false; // a blank line since the last list item

  const flushParagraph = () => {
    if (!paragraph.length) return;
    const p = document.createElement("p");
    inline(p, paragraph.join("\n"));
    root.appendChild(p);
    paragraph = [];
  };
  const flushItem = (entry) => {
    if (!entry.item || !entry.item.pending.length) return;
    inline(entry.item.node, entry.item.pending.join("\n"));
    entry.item.pending = [];
  };
  const closeLists = () => {
    while (lists.length) flushItem(lists.pop());
  };
  const closeAll = () => {
    flushParagraph();
    closeLists();
    blank = false;
  };

  for (let i = 0; i < lines.length; i++) {
    const line = lines[i];
    if (!line.trim()) {
      flushParagraph();
      if (lists.length) blank = true;
      continue;
    }

    const fence = FENCE.exec(line);
    if (fence) {
      const [, lead, marker, info] = fence;
      const body = [];
      let j = i + 1;
      for (; j < lines.length; j++) {
        const close = lines[j].trim();
        if (close[0] === marker[0] && close.length >= marker.length && [...close].every((c) => c === marker[0])) break;
        body.push(stripIndent(lines[j], lead.length));
      }
      i = j; // past the closing fence, or at the end: a block still open runs to the end
      const pre = document.createElement("pre");
      const code = document.createElement("code");
      if (/^[\w+#.-]+$/.test(info)) code.className = `language-${info}`;
      code.textContent = body.join("\n");
      pre.appendChild(code);
      flushParagraph();
      const owner = lists.length && lead.length > lists.at(-1).indent ? lists.at(-1) : null;
      if (owner) {
        flushItem(owner);
        owner.item.node.appendChild(pre);
      } else {
        closeAll();
        root.appendChild(pre);
      }
      blank = false;
      continue;
    }

    const heading = HEADING.exec(line);
    if (heading) {
      closeAll();
      const node = document.createElement(`h${Math.min(heading[1].length + 2, 6)}`);
      inline(node, heading[2]);
      root.appendChild(node);
      continue;
    }

    let item = RULE.test(line) ? null : ITEM.exec(line);
    // As in CommonMark, only a list starting at 1 interrupts a paragraph (« 2026. Une année »).
    if (item && paragraph.length && !lists.length && item[3] !== undefined && Number(item[3]) !== 1) item = null;
    if (item) {
      flushParagraph();
      const indent = indentOf(item[1]);
      const ordered = item[3] !== undefined;
      while (lists.length && lists.at(-1).indent > indent) flushItem(lists.pop());
      let top = lists.at(-1);
      if (top && top.indent === indent && top.ordered !== ordered) {
        flushItem(lists.pop()); // another kind of list at the same level: a new list
        top = lists.at(-1);
      }
      if (!top || top.indent < indent) {
        const node = document.createElement(ordered ? "ol" : "ul");
        if (ordered && Number(item[3]) !== 1) node.setAttribute("start", String(Number(item[3])));
        if (top) {
          flushItem(top);
          top.item.node.appendChild(node);
        } else {
          root.appendChild(node);
        }
        top = { indent, ordered, node, item: null };
        lists.push(top);
      } else {
        flushItem(top);
      }
      const li = document.createElement("li");
      top.node.appendChild(li);
      top.item = { node: li, pending: [item[5]] };
      blank = false;
      continue;
    }

    if (lists.length) {
      const top = lists.at(-1);
      const indent = indentOf(/^\s*/.exec(line)[0]);
      if (!blank || indent > top.indent) {
        // A continuation of the last item (lazy after a line, indented after a blank one).
        if (blank) top.item.pending.push("");
        top.item.pending.push(line.trim());
        blank = false;
        continue;
      }
      closeAll();
    }
    paragraph.push(line);
  }
  closeAll();
  return root;
}

function indentOf(lead) {
  return lead.replace(/\t/g, "    ").length;
}

function stripIndent(line, count) {
  let n = 0;
  while (n < count && n < line.length && line[n] === " ") n++;
  return line.slice(n);
}

// ---------- inline: escapes, code, links, bold and italic, line breaks ----------

function inline(parent, text) {
  // Finition V1 (#18): per opener (`*`, `**`, `_`, `__`), the position from which no closer
  // is left in `text`: a later opener of the same kind looks no further.
  const misses = {};
  let buffer = "";
  const flush = () => {
    if (buffer) parent.appendChild(document.createTextNode(buffer));
    buffer = "";
  };
  let i = 0;
  while (i < text.length) {
    const c = text[i];
    if (c === "\\" && i + 1 < text.length && ESCAPABLE.includes(text[i + 1])) {
      buffer += text[i + 1];
      i += 2;
      continue;
    }
    if (c === "\n") {
      flush();
      parent.appendChild(document.createElement("br"));
      i += 1;
      continue;
    }
    if (c === "`") {
      const span = codeSpan(text, i);
      if (span) {
        flush();
        const code = document.createElement("code");
        code.textContent = span.content;
        parent.appendChild(code);
        i = span.end;
        continue;
      }
      const run = runLength(text, i, "`");
      buffer += text.slice(i, i + run);
      i += run;
      continue;
    }
    if (c === "!" && text[i + 1] === "[") {
      const image = linkAt(text, i + 1); // an image stays its source, never a link
      if (image) {
        buffer += text.slice(i, image.end);
        i = image.end;
        continue;
      }
    }
    if (c === "[") {
      const link = linkAt(text, i);
      if (link) {
        flush();
        const url = safeUrl(link.url);
        if (url) {
          const a = document.createElement("a");
          a.href = url;
          a.target = "_blank";
          a.rel = "noopener noreferrer";
          inline(a, link.label);
          parent.appendChild(a);
        } else {
          parent.appendChild(document.createTextNode(text.slice(i, link.end))); // the exact source
        }
        i = link.end;
        continue;
      }
    }
    if (c === "*" || c === "_") {
      const emphasis = emphasisAt(text, i, misses);
      if (emphasis) {
        flush();
        const node = document.createElement(emphasis.strong ? "strong" : "em");
        inline(node, emphasis.content);
        parent.appendChild(node);
        i = emphasis.end;
        continue;
      }
      const run = runLength(text, i, c);
      buffer += text.slice(i, i + run);
      i += run;
      continue;
    }
    buffer += c;
    i += 1;
  }
  flush();
}

function runLength(text, i, c) {
  let n = 0;
  while (text[i + n] === c) n++;
  return n;
}

// A code span: a run of n backticks up to the next run of exactly n.
function codeSpan(text, i) {
  const n = runLength(text, i, "`");
  let j = i + n;
  while (j < text.length) {
    const close = text.indexOf("`", j);
    if (close < 0) return null;
    const m = runLength(text, close, "`");
    if (m === n) {
      let content = text.slice(i + n, close).replace(/\n/g, " ");
      if (content.length > 2 && content.startsWith(" ") && content.endsWith(" ") && content.trim()) {
        content = content.slice(1, -1);
      }
      return { content, end: close + n };
    }
    j = close + m;
  }
  return null;
}

// `[label](url)`, the brackets and parentheses balanced; `url` may carry a quoted title.
function linkAt(text, i) {
  let depth = 0;
  let j = i;
  for (; j < text.length; j++) {
    const c = text[j];
    if (c === "\\") {
      j++;
      continue;
    }
    if (c === "\n" && text[j + 1] === "\n") return null;
    if (c === "[") depth++;
    else if (c === "]" && --depth === 0) break;
  }
  if (j >= text.length || text[j + 1] !== "(") return null;
  const label = text.slice(i + 1, j);
  let k = j + 2;
  depth = 1;
  for (; k < text.length; k++) {
    const c = text[k];
    if (c === "\\") {
      k++;
      continue;
    }
    if (c === "\n") return null;
    if (c === "(") depth++;
    else if (c === ")" && --depth === 0) break;
  }
  if (k >= text.length) return null;
  const target = text.slice(j + 2, k).trim();
  const titled = /^(\S+)\s+(?:"[^"]*"|'[^']*')$/.exec(target);
  return { label, url: titled ? titled[1] : target, end: k + 1 };
}

/** The URL to link to, or null: an absolute `http:` or `https:` URL only. */
export function safeUrl(url) {
  if (!url || /\s/.test(url)) return null;
  try {
    const parsed = new URL(url);
    return parsed.protocol === "http:" || parsed.protocol === "https:" ? parsed.href : null;
  } catch {
    return null; // relative or invalid: no base, so never a link
  }
}

// `**x**`, `__x__` (strong), `*x*`, `_x_` (em): the opener followed by a non-space, the
// closer preceded by one; an underscore opens after and closes before a non-word character.
function emphasisAt(text, i, misses = {}) {
  const c = text[i];
  const run = runLength(text, i, c);
  const size = run >= 2 ? 2 : 1;
  const after = text[i + size];
  if (after === undefined || SPACE.test(after)) return null;
  if (c === "_" && i > 0 && WORD.test(text[i - 1])) return null;
  // #18: an earlier opener of this kind found no closer up to the end: nor will this one (its
  // closers are among those, under a stricter condition).
  const kind = c + size;
  if (misses[kind] !== undefined && i >= misses[kind]) return null;
  // #18: the blank line found once, not by slicing the paragraph at each candidate closer
  // (cubic on a paragraph of unclosed `*`: 550 ms for 5 000 characters).
  const blank = text.indexOf("\n\n", i + size);
  let j = i + size;
  while (j < text.length) {
    const close = text.indexOf(c, j);
    if (close < 0) break;
    const m = runLength(text, close, c);
    const before = text[close - 1];
    const escaped = before === "\\";
    const fits = size === 2 ? m >= 2 : m === 1;
    // A closer of size 2 may be the end of a longer run (`***`): its last two characters.
    const at = size === 2 ? close + m - 2 : close;
    const next = text[at + size];
    const edge = c !== "_" || next === undefined || !WORD.test(next);
    if (blank >= 0 && blank + 2 <= close) return null; // never past a blank line
    if (fits && !escaped && !SPACE.test(text[at - 1]) && edge && at > i + size) {
      return { strong: size === 2, content: text.slice(i + size, at), end: at + size };
    }
    j = close + m;
  }
  misses[kind] = i; // every closer up to the end tried
  return null;
}
