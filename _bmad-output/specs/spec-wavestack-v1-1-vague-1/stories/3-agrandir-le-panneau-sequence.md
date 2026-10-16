---
title: 'Story 3 : agrandir le panneau Séquence'
type: 'feature'
created: '2026-10-15'
status: 'review'
route: 'dispatch'
review_loop_iteration: 0
baseline_commit: '61c3e1a'
context:
  - '{project-root}/_bmad-output/specs/spec-wavestack-v1-1-vague-1/SPEC.md'
  - '{project-root}/_bmad-output/specs/spec-wavestack-v1-1-vague-1/brownfield.md'
---

<frozen-after-approval reason="human-owned intent — do not modify unless human renegotiates">

## Intent

**Problem:** CAP-6. Sur `/mcp` et `/rag`, le panneau Séquence est à taille fixe ; rien ne l'agrandit pour suivre un échange long.

**Approach:**
- `/mcp` a déjà le mécanisme générique « Mode focus » (⛶, `panes.js`) sur chaque `.pane`, dont la Séquence : en focus, `body.focus-mode` replie les autres panneaux à leur en-tête et laisse la Séquence prendre la quasi-totalité de la fenêtre. Il manquait Échap pour refermer, et `aria-pressed` sur le bouton ⛶ pour en dire l'état.
- `/rag` n'a pas de système de panneaux : la Séquence (`#rag-seq`) est une des trois vues côte à côte (`rag-views`). Un nouveau bouton ⛶ (même libellé, `common.panes.focus`) bascule une classe `is-expanded` qui la passe en recouvrement quasi plein écran (`position: fixed`, tokens de `pages.css`) ; même bouton ou Échap la referme.

**Décisions (prises par Claude, sans effet sur le contrat) :**
- Échap et `aria-pressed` du ⛶ sont ajoutés dans `panes.js` (partagé par `mcp.js` et `app.js`), jamais dans `app.js` : hors périmètre de cette story (lane B), mais `panes.js` n'est touché par aucune autre story de la vague.
- RAG réutilise la clé i18n existante `common.panes.focus` (fr/en/de déjà traduite) plutôt que d'en créer une nouvelle.

## Boundaries & Constraints

**Always:**
- Libellés (titre, aria-label) en fr, en, de.
- Bouton clavier-accessible : élément `<button>` natif, `aria-pressed` reflétant l'état agrandi/réduit.
- Échap referme le panneau agrandi, sauf si un autre gestionnaire a déjà consommé la touche (`event.defaultPrevented`).

**Never:** toucher `app.js`, `README.md`, `docs/`.

## Code Map

- `src/wavestack/web/static/panes.js` -- `renderVisibility()` : `aria-pressed` du bouton `[data-action="focus"]` de chaque pane ; `start()` : écouteur `keydown` document, Échap referme le panneau focalisé (`toggleFocus`), sauf `event.defaultPrevented`. Affecte `/mcp` (`mcp.js`) et `/` (`app.js`), tous deux déjà équipés du bouton ⛶.
- `src/wavestack/web/static/rag.html` -- `#rag-seq` : nouvel en-tête `.rag-seq-view-head` (label + `.pane-actions` avec le bouton `#rag-seq-expand`, `aria-pressed="false"`, libellés `data-i18n-title`/`data-i18n-aria-label="common.panes.focus"`).
- `src/wavestack/web/static/rag.css` -- `.rag-seq-view-head`, `.rag-seq.is-expanded` (recouvrement `position: fixed`, tokens `pages.css`/`tokens.css`).
- `src/wavestack/web/static/rag.js` -- `setSeqExpanded(on)` ; clic sur `#rag-seq-expand` et écouteur `keydown` Échap (même garde `defaultPrevented`), câblés dans `main()`.
- `tools/e2e/run_e2e.py` -- `_mcp_lab_page` : une vérification légère (clic ⛶, classe `is-focused` + `aria-pressed`, Échap referme).

## Tasks & Acceptance

**Execution:**
- [x] `panes.js` -- `aria-pressed`, Échap.
- [x] `rag.html`, `rag.css`, `rag.js` -- bouton ⛶, bascule, Échap.
- [x] `tools/e2e/run_e2e.py` -- vérification dans `s_mcp_lab_page` (non lancée par le développeur ; à lancer par l'orchestrateur).
- [ ] Un scénario E2E RAG (reporté : pas ajouté dans ce lot, sur consigne de l'orchestrateur).

**Acceptance Criteria:**
- Given `/mcp`, when on clique le ⛶ de la Séquence, then elle prend la quasi-totalité de la fenêtre, le bouton porte `aria-pressed="true"`, et Échap (ou un second clic) referme et remet `aria-pressed="false"`.
- Given `/rag`, when on clique le ⛶ de la Séquence, then elle recouvre la quasi-totalité de la fenêtre par-dessus Architecture/Focus, et Échap (ou un second clic) referme.
- Given les langues en et de, when on lit le titre/aria-label du bouton, then ils sont traduits (`common.panes.focus`).

## Implementation Notes

- `/mcp` possédait déjà le mécanisme générique de `panes.js` (le bouton ⛶ existait dans `mcp.html` et aboutissait à `body.focus-mode`, qui réduit tous les panneaux sauf celui en focus à leur en-tête) : il ne manquait qu'Échap et `aria-pressed`, ajoutés une fois dans `panes.js` pour que `/mcp` (et `/`, qui partage le fichier) en bénéficient.
- `/rag` n'a pas de panneaux : la bascule est locale à `rag.js`/`rag.css`, un recouvrement `position: fixed; inset: var(--spacing-4)` au-dessus du reste de la page (z-index 45, sous aucun autre élément de la page sauf le menu « Affichage » à 40... en fait au-dessus, volontairement, car c'est la seule bascule d'affichage présente).
- Testé : `tests/test_ui_texts.py` (39), `tests/test_web_app.py` (27), `tests/test_web_tokens.py` (21) -- tous verts. Pas de nouveau test pytest dédié : la story est de l'UI pure, déjà couverte par ces suites (texte, structure des pages) ; la vérification comportementale (ouvre/referme, aria-pressed) est dans l'E2E ajouté.

## Spec Change Log

## Review Triage Log

(pas encore de relecture)

## Verification

**Commands:**
- `uv run pytest -q --tb=short tests/test_ui_texts.py tests/test_web_app.py tests/test_web_tokens.py` -- obtenu : 87 passés.
- `python .claude/cost-kit/controle_rapide.py` -- obtenu : aucun écart (lint/format).
- E2E (non lancé par le développeur) : `uv run --with playwright==1.56.0 python tools/e2e/run_e2e.py --channel msedge --only mcp_lab_page` -- à lancer par l'orchestrateur.

## Revue

- medium | second avis 1 | corrigé | sur `/`, l'écouteur Échap de `panes.js` (posé par `panes.start()`, avant celui d'app.js) passait avant tiroirs, menu des volets, panneau Fenêtre et sélection (story 34), qu'app.js gère déjà dans l'ordre, focus compris. Échap de `panes.js` devient opt-in (`escape: true`), activé par `mcp.js` seul ; `/` revient au comportement d'avant la story.
- medium | second avis 2 | corrigé | Échap avec un volet focalisé annulait la fermeture native d'un `<dialog>` modal (audit, avertissement cloud sur `/`). Réglé par l'opt-in, plus une garde `dialog[open]` dans `panes.js`.
- low | second avis 3 | rejeté | Échap dans un champ d'un volet focalisé sur `/mcp` : aucune action native perdue (le menu d'un `select` ouvert ne remonte pas au document), et sortir du focus est l'effet attendu.
- low | second avis 4 | rejeté | le recouvrement RAG n'est pas modal (comme le « Mode focus » des volets) ; le ⛶ reste dans le recouvrement, donc le focus n'est jamais perdu à la fermeture.
- low | second avis 5 | rejeté | le setter `focused` est toujours suivi d'un `render()` chez ses appelants (app.js passe par `store.focusedPane` puis `render`), comme le dit le contrat du module.
- low | second avis 6 | corrigé | vérification légère ajoutée dans `_rag_lab` (scénario `rag_lab`) : ⛶, recouvrement à plus de 90 % de la fenêtre, `aria-pressed`, Échap. Reporté : lancer `--only mcp_lab_page,rag_lab` (non lancé en revue).
