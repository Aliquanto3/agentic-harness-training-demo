/* Story 31 (DESIGN.md > theme-picker, AD-18): the interface's theme, a browser setting only.
   A classic script loaded first in each page's <head>, so that `data-theme` is set before the
   first render (a module would be deferred, and the page would flash). « Système » removes
   the attribute: tokens.css then follows `prefers-color-scheme`. Every storage access is
   guarded: without storage the page shows « Système », and a choice holds for the open page.
   A page shown again (« Back », from the bfcache or not) or a choice made in another tab is
   read again. Lot K (A4): the browser restores a form's values on a « Back » outside the
   bfcache, after this script: the pickers say `autocomplete="off"`, and every `pageshow`
   (which follows that restoration) reads the stored choice again.
   Nothing goes to the server; no global variable. */
(() => {
  const KEY = "wavestack.theme";
  const CHOICES = ["system", "light", "dark"];
  const SYMBOLS = { system: "◐", light: "☀", dark: "☾" };

  const read = () => {
    try {
      const value = localStorage.getItem(KEY);
      return CHOICES.includes(value) ? value : "system";
    } catch {
      return "system";
    }
  };

  const apply = (choice) => {
    if (choice === "light" || choice === "dark") {
      document.documentElement.setAttribute("data-theme", choice);
    } else {
      document.documentElement.removeAttribute("data-theme");
    }
  };

  const save = (choice) => {
    try {
      localStorage.setItem(KEY, choice);
    } catch {
      // No storage (private window, blocked site data): the choice holds for this page only.
    }
  };

  // Each picker shows the choice, and the compact face (index.html) its symbol.
  const show = (choice) => {
    for (const picker of document.querySelectorAll("select[data-theme-picker]")) {
      picker.value = choice;
    }
    for (const symbol of document.querySelectorAll("[data-theme-symbol]")) {
      symbol.textContent = SYMBOLS[choice];
    }
  };

  // The stored choice, again: at a restore from the bfcache, or when another tab changed it.
  const reread = () => {
    const choice = read();
    apply(choice);
    show(choice);
  };

  apply(read());

  document.addEventListener("DOMContentLoaded", () => {
    show(read());
    for (const picker of document.querySelectorAll("select[data-theme-picker]")) {
      picker.addEventListener("change", () => {
        const choice = CHOICES.includes(picker.value) ? picker.value : "system";
        apply(choice);
        show(choice);
        save(choice);
      });
    }
  });

  window.addEventListener("pageshow", reread);

  window.addEventListener("storage", (event) => {
    if (event.key === KEY || event.key === null) reread();
  });
})();
