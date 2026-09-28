---
title: 'Mode sombre'
type: 'feature'
created: '2026-09-28'
status: 'ready-for-dev'
review_loop_iteration: 0
followup_review_recommended: false
context:
  - '{project-root}/CLAUDE.md'
  - '{project-root}/_bmad-output/planning-artifacts/ux-designs/ux-agentic-harness-training-demo-2026-09-22/DESIGN.md'
  - '{project-root}/_bmad-output/planning-artifacts/ux-designs/ux-agentic-harness-training-demo-2026-09-22/EXPERIENCE.md'
  - '{project-root}/_bmad-output/specs/spec-agentic-harness-training-demo/stories/33-contrastes-et-code-couleur-par-discipline.md'
  - '{project-root}/_bmad-output/specs/spec-agentic-harness-training-demo/stories/25-selecteur-de-modeles-regroupe-et-tableau-des-capacites.md'
  - '{project-root}/_bmad-output/planning-artifacts/architecture/architecture-agentic-harness-training-demo-2026-09-23/ARCHITECTURE-SPINE.md'
  - '{project-root}/tools/e2e/README.md'
warnings:
  - oversized
deferred: []
---

<intent-contract>

## Intent

**Problem:** WaveStack n'a qu'un thème clair. Sur un poste réglé en sombre, en visio le soir ou dans une salle sans lumière, l'interface éblouit. Anaël a demandé le 2026-09-28 un sélecteur « Système », « Clair », « Sombre » pour l'atelier, le diagnostic et les nouveaux écrans. Depuis la story 33, toutes les couleurs de `app.css` et `app.js` passent par des jetons, mais `diagnostic.html` écrit encore ses couleurs en dur. Et certains jetons jouent deux rôles qui divergent en sombre : l'encre sert de texte et de fond, et `on-ink` sert de texte sur l'encre et sur les couleurs de discipline.

**Approach:** Dessiner une palette sombre dans DESIGN.md, avec un jumeau `{clé}-dark` pour chaque couleur du frontmatter, et la recopier dans `tokens.css` sous `:root[data-theme="dark"]` et sous `@media (prefers-color-scheme: dark) { :root:not([data-theme]) }`. Séparer les rôles qui divergent grâce à cinq jetons de rôle. Un petit script classique, `static/theme.js`, chargé en tête de chaque page, pose `data-theme` avant le premier rendu, lit et écrit le choix dans `localStorage` (lecture protégée), et branche chaque sélecteur `[data-theme-picker]`.

## Boundaries & Constraints

**Always:**
- `uv`, `ruff` et `pytest` (CLAUDE.md). Code et identifiants en anglais, textes d'interface en français.
- Chaque couleur passe par un jeton de `tokens.css`, dans toutes les pages statiques : `app.css`, `app.js`, `theme.js`, `diagnostic.html`, `models.html` (story 25) et toute page ajoutée plus tard (stories 29 et 30). Chaque clé `colors.X` de DESIGN.md a son jumeau `colors.X-dark`, et inversement. Le test l'exige, si bien qu'un jeton ajouté par une story précédente (22 à 27, 32 à 34) sans jumeau fait échouer `pytest`. **Relire `tokens.css` et le frontmatter au moment de l'implémentation** et couvrir tous les jetons présents, pas seulement ceux listés ici.
- WCAG AA dans les deux thèmes : 4,5:1 pour le texte, 3:1 pour les traits porteurs de sens. Le jaune reste doublé de « RÉSEAU » ou du globe. Jamais la couleur seule.
- Le thème relève de l'état du navigateur, limité à l'interface (AD-18). Rien ne part au serveur, aucun événement n'est émis, et l'API ne change pas.
- `localStorage` : chaque lecture et chaque écriture passent par `try/catch`. Sans stockage, la page s'affiche en « Système » sans erreur en console, et le choix vaut pour la page ouverte.
- Aucune dépendance nouvelle et aucun CDN. Aucun vrai modèle dans le conteneur : on utilise les doublures du dépôt (faux moteur, faux serveurs `tools/e2e`, GGUF synthétiques, faux fournisseurs).
- `uv run pytest -q` reste entièrement vert : aucune story livrée ne casse. Les scénarios E2E existants gardent le thème clair par défaut.
- Mettre à jour DESIGN.md, EXPERIENCE.md, la spine (AD-18) et `tools/e2e/README.md`. Ajouter les vérifications au parcours E2E.

**Never:**
- Inverser les couleurs par filtre (`filter: invert`) ou calculer une palette en JS : la palette sombre est dessinée, jeton par jeton.
- Garder `ink` en fond : un fond d'encre passe par `ink-fill`.
- Changer l'aspect du thème clair, sauf pour les jetons de rôle, qui valent l'ancienne valeur. Seule exception : le texte sur rouge passe à `on-vivid`, d'après la règle de DESIGN.md « rouge : texte encre », à 5,3:1 au lieu de 3,7:1.
- Hors périmètre : le mode contrasté de Windows (`forced-colors`), une synchronisation en direct entre onglets, le mode projection (story 34) et le contenu des écrans 29 et 30. Ces écrans reprennent seulement la règle et le script.

## I/O & Edge-Case Matrix

| Scenario | Input / State | Expected Output / Behavior | Error Handling |
|----------|--------------|---------------------------|----------------|
| Défaut, poste clair | Aucun `wavestack.theme`, `prefers-color-scheme: light` | Pas d'attribut `data-theme`, palette claire, sélecteur sur « Système » | — |
| Défaut, poste sombre | Aucun choix, `prefers-color-scheme: dark` | Pas d'attribut, palette sombre (bloc `@media`) | — |
| Le poste change de mode | « Système », puis le mode du poste bascule | La palette suit sans rechargement (CSS seul) | — |
| Choix explicite | « Sombre » sur un poste clair, ou « Clair » sur un poste sombre | `data-theme="dark"` ou `"light"`, le choix l'emporte, `wavestack.theme` mémorisé | — |
| Rechargement | `wavestack.theme = "dark"` | `data-theme="dark"` posé avant le premier rendu, même sans `app.js` | — |
| Valeur corrompue | `wavestack.theme = "violet"` | Traitée comme « Système » | Ignorée sans message |
| Stockage indisponible | `localStorage` lève une exception | « Système » au chargement ; un choix s'applique à la page sans être mémorisé | Aucune `pageerror`, aucune erreur en console |
| Autres pages | Choix « Sombre », puis `/diagnostic` et `/models` | Même thème et même sélecteur (même origine) | — |

</intent-contract>

## Code Map

Les stories 33 (en cours), 23, 34, 32, 24, 25, 26 et 27 modifient ces fichiers avant celle-ci. Se repérer aux symboles, aux sélecteurs et aux noms de jetons, jamais aux numéros de ligne.

- `_bmad-output/planning-artifacts/ux-designs/ux-agentic-harness-training-demo-2026-09-22/DESIGN.md`
  - Frontmatter : `description` (« Thème clair en V1… »), `colors`, groupés par commentaires (Charte, Relief, Lieu d'hébergement, États, Segments, Discipline, Sur encre), et `components` : `top-bar.background`, `discipline-code.model`, `chat-message-user.background`, `arch-model.plate`, `model-picker`, `scenario-picker`.
  - Prose : `## Brand & Style`, dernier paragraphe (« Thème clair en V1 `[ASSUMPTION]`… un thème sombre n'aura qu'à redéfinir les jetons »). `## Colors`, avec les tables des disciplines et de leurs contrastes. `## Do's and Don'ts`, dernière ligne.
  - Format DESIGN.md (`.claude/skills/bmad-ux/references/design-md-spec.md`) : clair et sombre se notent par des jetons jumeaux au suffixe `-dark`.
- `src/wavestack/web/static/tokens.css` -- un seul bloc `:root`, miroir du frontmatter (AD-18). À y ajouter : `color-scheme` et les deux blocs sombres.
- `tests/test_web_tokens.py`
  - `_expected_tokens` et `_css_custom_properties` : l'expression régulière lit tout le fichier ; une fois les blocs sombres ajoutés, les dernières définitions écraseraient les premières. Il faut lire bloc par bloc.
  - `test_tokens_css_declares_no_orphan_token`.
  - `_luminance`, `_contrast`, `_PAIRS` et `test_discipline_tokens_meet_wcag_aa`, les contrastes clairs de la story 33, à garder.
  - `_COMMENTS`, `_HARD_COLOR` et `test_app_css_and_js_write_no_color_outside_the_tokens`, qui ne visent aujourd'hui que `app.css` et `app.js`.
- `src/wavestack/web/static/app.css` -- endroits où un jeton joue un rôle qui diverge en sombre :
  - blocs `[data-discipline="prompt|context|harness|network|neutral|model"]` (`--on-discipline`, et `--discipline: var(--color-ink)` pour `model`) ;
  - fonds d'encre : `.top-bar`, `.bubble-user`, `.turn-step-tile[data-discipline="model"]`, `.arch-robots`, `.arch-cloud-model`, `.arch-server-model` ;
  - fonds vifs sous un texte, explicite ou hérité : `.net-mark`, `.net-host`, `.hosting-tag-network`, `.outbound-head`, `.arch-zone-network .arch-zone-label`, `.gauge.is-overflow .gauge-figures`, `.drawer-actions button.danger.is-confirm`, `.turn-group-status.is-running`, `.turn-group-status.is-failed`, `.turn-step.tone-error .turn-step-tile`, `.step-code mark` ;
  - sélecteurs de la barre haute : `.top-bar > .scenario-picker`, `.scenario-picker`, `.model-picker`, qui servent de modèle au sélecteur de thème.
- `src/wavestack/web/static/app.js`
  - `GROUP_COLORS` et `DISCIPLINES` ne portent que des noms de variables, ce qui les rend compatibles tels quels.
  - `loadShowForced` et `saveShowForced`, avec les clés `wavestack.*`, donnent le modèle de lecture protégée.
  - Le schéma pose ses couleurs par classes CSS, `svgEl` et les marqueurs `arch-marker` compris.
  - Aucune modification attendue.
- `src/wavestack/web/static/index.html` -- `<head>` (`fonts.css`, `tokens.css`, `app.css`). Dans `header.top-bar`, le sélecteur se place juste avant `#reset-button`.
- `src/wavestack/web/static/diagnostic.html` -- page autonome : `<style>` en ligne sans `tokens.css`, avec des couleurs en dur (`li.ok`, `li.warn`, `li.fail`, `li.incompatible`, `li.found`, `li.server`, `li.cloud`, `.served`, `.served-warning`, `.action`, `.hosting-tag-*`, `.cloud-result.*`, `dialog#cloud-warning`) et un `<script type="module">`. La story 25 y ajoute `nav.page-tabs`, et la story 24 y retouche des lignes.
- `src/wavestack/web/static/models.html` -- page `/models` de la story 25, avec `nav.page-tabs`, `tokens.css` et des jetons seulement.
- `src/wavestack/web/app.py` -- `app.mount("/static", …)` et l'intergiciel `Cache-Control: no-cache`. `theme.js` est servi sans nouvelle route.
- `tests/test_web_app.py` -- boucle sur `("/", "/diagnostic", "/static/app.js")`.
- `tools/e2e/run_e2e.py`
  - `Run.token_color` et `_CSS_COLOR_JS` résolvent un jeton dans le thème courant.
  - `Run.css`, `Run.shot`, `Run.shot_element` et `_fully_visible`.
  - `s_disciplines`, qui laisse un tour « Outils réseau » à l'écran.
  - `SCENARIOS`.
  - `main` : une seule page Playwright pour tous les scénarios, donc le thème doit revenir à « Système » en fin de scénario.
- `ARCHITECTURE-SPINE.md` AD-18 -- la puce `static/tokens.css`, et « État du navigateur » (sélection, volets masqués, mode focus, taille de texte, direct ou figé).
- `EXPERIENCE.md`
  - Tables `### Surfaces`, lignes « Diagnostic de démarrage » et « Barre haute ».
  - `## Component Patterns`, ligne `top-bar`.
  - `## Accessibility Floor`.
  - `## Code couleur par discipline`, puce « Encre = élément clé ».

## Tasks & Acceptance

**Execution:**
1. `DESIGN.md` -- Ajouter au frontmatter les jetons de rôle `ink-fill`, `on-discipline`, `on-vivid`, `warning-soft` et `danger-soft`. Ajouter ensuite un bloc « # Thème sombre (story 31) » avec un `X-dark` pour **chaque** clé de `colors` présente à ce moment-là, valeurs de la note de conception. Faire pointer `top-bar.background`, `chat-message-user.background`, `arch-model.plate` et `discipline-code.model` vers `{colors.ink-fill}`, et ajouter le composant `theme-picker`. Dans la prose :
   - réécrire le paragraphe « Thème clair en V1 » : deux thèmes, « Système » par défaut ;
   - ajouter à Colors une sous-section « Thème sombre » avec les rôles, la table clair / sombre et les contrastes ;
   - ajouter à Do's and Don'ts « fond d'encre = `ink-fill` », « texte sur fond vif = `on-vivid` » et « pas de `filter: invert` ».
   Raison : DESIGN.md est la source des jetons (AD-18).
2. `src/wavestack/web/static/tokens.css` -- Dans `:root`, ajouter `color-scheme: light` et les jetons de rôle. Ajouter `:root[data-theme="dark"] { color-scheme: dark; --color-X: <X-dark>; … }` pour chaque couleur, puis `@media (prefers-color-scheme: dark) { :root:not([data-theme]) { … } }` avec des déclarations identiques. Aucun `--color-X-dark` n'est déclaré. Raison : le thème choisi l'emporte, « Système » suit le poste, et `color-scheme` fait suivre les contrôles natifs (listes, barres de défilement, `dialog`).
3. `tests/test_web_tokens.py` -- Découper `tokens.css` en trois blocs (`:root`, `[data-theme="dark"]`, `@media` puis `:root:not([data-theme])`). Les tests :
   - la correspondance et l'absence d'orphelins portent sur le bloc `:root`, hors clés `-dark` ;
   - tout `X` a son `X-dark`, et inversement ;
   - le bloc `[data-theme="dark"]` vaut exactement `{--color-X: X-dark}` pour toutes les couleurs ;
   - le bloc `@media` est identique ;
   - `color-scheme` vaut `light` puis `dark` ;
   - `_THEME_PAIRS`, contrôlé dans les deux palettes (liste de la note de conception), s'ajoute à `_PAIRS`, qui est gardé ;
   - l'interdiction des couleurs en dur s'étend à tous les `.css`, `.js` et `.html` de `static/` sauf `tokens.css`. Les commentaires `<!-- -->`, `/* */` et `//` sont exclus, ainsi que les entités `&#…;` ;
   - chaque `static/*.html` charge `/static/tokens.css`, et `<script src="/static/theme.js">` est dans `<head>`, avant la première feuille de style, sans `type="module"`, `defer` ni `async`.
   Raison : c'est ce qui force la couverture complète maintenant et pour les stories 29 et 30.
4. `src/wavestack/web/static/theme.js` (nouveau, script classique) -- Une IIFE qui :
   - lit `wavestack.theme` sous `try/catch`, avec pour valeurs `system`, `light` et `dark`, toute autre valeur valant `system` ;
   - pose ou retire `data-theme` sur `document.documentElement` ;
   - au `DOMContentLoaded`, règle chaque `select[data-theme-picker]` et l'écoute : au changement, elle applique le thème puis l'écrit sous `try/catch`.
   Aucune variable globale. Raison : un seul code pour toutes les pages, exécuté avant le rendu (un module serait différé).
5. `index.html`, `diagnostic.html`, `models.html` -- En tête de `<head>`, `<script src="/static/theme.js"></script>`. Dans la barre haute de `index.html`, avant `#reset-button` : `<select id="theme-picker" class="theme-picker" data-theme-picker aria-label="Thème de l'interface" title="Thème de l'interface">` avec « ◐ Système » (`system`), « ☀ Clair » (`light`) et « ☾ Sombre » (`dark`). Même sélecteur à droite de `nav.page-tabs` dans `diagnostic.html` et `models.html`, ou en haut de page si la nav est absente. Raison : le choix se fait partout et reste le même d'une page à l'autre.
6. `src/wavestack/web/static/app.css` -- Migrer les rôles :
   - les fonds d'encre du Code Map passent à `var(--color-ink-fill)` ;
   - `[data-discipline="model"]` prend `--discipline` et `--discipline-soft` à `ink-fill` ;
   - les blocs prompt, context et harness prennent `--on-discipline: var(--color-on-discipline)`, les blocs network et neutral `var(--color-on-vivid)` ;
   - chaque fond vif (jaune, vert, rouge, gris neutre) portant du texte reçoit un `color: var(--color-on-vivid)` explicite, car un texte hérité deviendrait clair en sombre.
   Ajouter `.theme-picker` sur le modèle de `.model-picker`, lisible sur `ink-fill`, avec un anneau de focus `on-ink`. Raison : les jetons seuls ne suffisent pas là où un rôle diverge.
7. `diagnostic.html` (`<style>`) -- Charger `tokens.css`. `body` prend le fond `surface` et le texte `ink`, et chaque couleur en dur est remplacée par un jeton :
   - `li.ok`, `li.found` et `li.server` : `accent-soft` ;
   - `li.warn` et `li.server.warn` : `warning-soft` ;
   - `li.fail` et `li.incompatible` : `danger-soft` ;
   - `li.cloud` : `discipline-network-soft`, en tirets `hosting-boundary` ;
   - `.served` et `.action` : `ink-soft` ;
   - `.served-warning` et `.cloud-result.*` : `ink`, avec un filet gauche de 4 px en `state-ok`, `warning` ou `state-error` ;
   - `.hosting-tag-network` : `hosting-network`, texte `on-vivid` ;
   - `.hosting-tag-local` : comme dans `app.css` ;
   - `dialog` : fond `surface-raised`, bordure `ink`.
   Le JS de la page ne change pas. Raison : la story couvre le diagnostic.
8. `tests/test_web_app.py` -- Ajouter `/static/theme.js` aux chemins servis en 200.
9. `EXPERIENCE.md`, `ARCHITECTURE-SPINE.md` -- EXPERIENCE :
   - ajouter le thème aux lignes Barre haute et Diagnostic ;
   - nouvelle ligne `theme-picker` : trois choix, « Système » par défaut, effet immédiat, mémorisé dans le navigateur, repris sur toutes les pages ;
   - Accessibility Floor : AA dans les deux thèmes ;
   - « Encre = élément clé » devient « fond d'encre (`ink-fill`, violet profond en sombre) ».
   AD-18 : ajouter « thème » à l'état du navigateur, et « palette sombre sous `[data-theme="dark"]` et `prefers-color-scheme` sans attribut, mêmes noms ».
10. `tools/e2e/run_e2e.py`, `tools/e2e/README.md` -- Nouveau scénario `s_themes`, placé juste après `disciplines`, qui couvre les critères ci-dessous. Il ajoute `_contrast_sweep(r)`, un JS qui, pour chaque élément visible portant du texte, remonte au premier fond opaque, calcule le ratio WCAG et renvoie la liste des échecs. Sont ignorés un ancêtre en `opacity < 1` ou désactivé (exemption WCAG) et un fond en image. Le seuil est de 4,5, ou 3 à partir de 24 px, ou de 18,66 px en gras. En fin de scénario : « Système », `emulate_media(color_scheme="light")` et `unroute`. Captures, numérotées au prochain numéro libre de `tools/e2e/screenshots/` : `NN-theme-sombre-atelier` (page entière), `-vue-humain`, `-schema`, `-diagnostic`, `-modeles` (`shot_element` pour les volets), et `NN-theme-clair-atelier`. Ajouter au README une section « Mode sombre (story 31) ».

**Acceptance Criteria:**
- Given un tour « Outils réseau » à l'écran (fin de `disciplines`) et aucun choix mémorisé, when on lit la barre haute à 1600 × 1000, then `#theme-picker` montre « Système », propose Système, Clair et Sombre, et toutes les commandes de la barre sont entièrement visibles sur une ligne (`_fully_visible`). Sans attribut `data-theme`, avec `emulate_media(color_scheme="dark")`, le fond calculé de `body` vaut `surface-dark` (valeur lue dans DESIGN.md) sans rechargement ; avec `"light"`, il revient à `surface`.
- Given le poste émulé en clair, when on choisit « Sombre », then `<html data-theme="dark">`, `localStorage["wavestack.theme"] == "dark"`, et :
  - le fond de `.top-bar`, de la dernière `.bubble-user` et de la tuile de l'appel au modèle vaut `ink-fill-dark` ;
  - le filet du segment du prompt système vaut `discipline-prompt-dark` ;
  - chaque `.gauge-seg` a le fond de son jeton sombre ;
  - la plaque du modèle du schéma vaut `ink-fill-dark` ;
  - `_contrast_sweep` ne renvoie aucun échec dans les cinq volets ni dans la barre haute.
- Given « Sombre » mémorisé, when on recharge la page avec `**/static/app.js` interrompu (`route.abort`), then `data-theme="dark"` et le fond de `body` en `surface-dark` sont déjà en place. Après `unroute` et un rechargement, le sélecteur montre « Sombre » et aucune `pageerror` n'est apparue.
- Given « Sombre », when on ouvre `/diagnostic` puis `/models`, then chaque page est sombre, son sélecteur montre « Sombre » et `_contrast_sweep` ne renvoie aucun échec. Choisir « Clair » sur `/diagnostic`, puis revenir à `/` avec le poste émulé en sombre, donne `data-theme="light"` et un fond `surface` clair.
- Given `wavestack.theme = "violet"`, when on recharge, then il n'y a pas d'attribut `data-theme` et le sélecteur montre « Système ».
- Given une nouvelle page dont le script d'initialisation fait lever `Storage.prototype.getItem` et `setItem`, when on charge `/` puis on choisit « Sombre », then la page s'affiche sans `pageerror`, et `data-theme="dark"` s'applique sans être mémorisé.
- Given `uv run pytest -q`, when `tests/test_web_tokens.py` s'exécute, then la couverture des jumeaux, l'identité des deux blocs sombres, les contrastes des deux palettes, l'interdiction des couleurs en dur sur toutes les pages et la présence de `theme.js` en tête de chaque page passent. Retirer un seul `X-dark` fait échouer le test.

## Spec Change Log

## Review Triage Log

## Design Notes

**Rôles qui divergent en sombre**. Leur valeur claire est celle d'aujourd'hui, ce qui ne change rien au thème clair :

| Jeton | Rôle | Clair | Sombre |
|---|---|---|---|
| `ink-fill` | fond des éléments clés (barre haute, bulle de l'utilisateur, étapes et plaque du modèle) | `#0A0A14` | `#33257A` |
| `on-discipline` | texte sur prompt, context ou harness | `#FFFFFF` | `#0E0B1E` |
| `on-vivid` | texte sur jaune, vert, rouge ou gris neutre | `#0A0A14` | `#0A0A14` |
| `warning-soft`, `danger-soft` | fonds d'état du diagnostic | `#FFF4D6`, `#FDE8EB` | `#3A3010`, `#3A1820` |

**Palette sombre** (`X-dark`) :
- charte : `primary #9C86FF`, `primary-deep #C9BDFF`, `primary-soft #2A2350`, `accent #04F06A`, `accent-soft #0F3A24`, `ink #ECEBF5`, `ink-soft #B4B3C7`, `muted #8A8A9E`, `line #3A394F`, `surface #12121C`, `surface-raised #1E1D2C`, `warning #FFCA4A`, `danger #FF6B7F`, `on-primary #0E0B1E` ;
- relief : `relief #2A2156`, `relief-active #3A2E78`, `dot #262538` ;
- hébergement : `hosting-network #FFCA4A`, `hosting-boundary #ECEBF5` ;
- états : `state-active` et `state-ok` `#04F06A`, `state-blocked` et `state-error` `#FF6B7F`, `state-unavailable #8A8A9E` ;
- segments : `system-prompt #8C74FF`, `global-memory #3CC878`, `tool-descriptions #4F95EA`, `history #A48EF0`, `rag #1FB3A2`, `tool-results #F08A42`, `message #C07FDA`, `free #2A2938` ;
- disciplines : `prompt #9C86FF` / `#262047`, `context #2FB8A3` / `#12302B`, `harness #E8639F` / `#3A1A2B`, `network #E8B516` / `#3A3010`, `neutral #8A8A9E` / `#26252F` ;
- `on-ink #FFFFFF`, `on-ink-soft #CFCDE4`.

Un jeton ajouté entre-temps (stories 32 et 34, par exemple) reçoit une valeur sombre dessinée sur le même principe et entre dans `_THEME_PAIRS` s'il porte du texte.

**Contrastes vérifiés** (calcul WCAG) pour `_THEME_PAIRS`. Ils valent dans les deux palettes ; en sombre :
- `ink` et `ink-soft` sur `surface`, `surface-raised`, `primary-soft`, `accent-soft`, `warning-soft`, `danger-soft` et chaque `-soft` de discipline : au moins 6,2 ;
- `primary` sur `surface-raised` : 5,9 ;
- `primary-deep` sur `primary-soft` : 8,4 ;
- `on-primary` sur `primary` : 6,7 ;
- `on-ink` et `on-ink-soft` sur `ink-fill` : 12,5 et 8,0 ;
- `on-discipline` sur prompt, context et harness : 6,7, 7,8 et 6,2 ;
- `on-vivid` sur `hosting-network`, `warning`, `discipline-network`, `discipline-neutral`, `state-active`, `accent`, `danger` et `state-error` : au moins 5,8 ;
- disciplines prompt, context, harness et neutral sur `surface` et `surface-raised` : au moins 3.

À contrôler en sombre seulement, car le clair échoue déjà et c'est documenté : `danger` sur `surface-raised` en texte (6,2), et chaque segment sur `segment-free` (au moins 4,1).

**Squelette de `theme.js`** :

```js
(() => {
  const KEY = "wavestack.theme", CHOICES = ["system", "light", "dark"];
  const read = () => { try { const v = localStorage.getItem(KEY); return CHOICES.includes(v) ? v : "system"; } catch { return "system"; } };
  const apply = (c) => (c === "system" ? document.documentElement.removeAttribute("data-theme") : document.documentElement.setAttribute("data-theme", c));
  apply(read());
  document.addEventListener("DOMContentLoaded", () => document.querySelectorAll("select[data-theme-picker]").forEach((s) => {
    s.value = read(); s.addEventListener("change", () => { apply(s.value); try { localStorage.setItem(KEY, s.value); } catch {} });
  }));
})();
```

Sans stockage, `read()` renvoie toujours « system ». Le sélecteur garde pourtant la valeur choisie, parce qu'il n'est relu qu'au chargement.

## Verification

**Commands:**
- `uv run ruff check .` -- expected: aucune erreur
- `uv run ruff format --check .` -- expected: aucun fichier à reformater
- `uv run pytest -q` -- expected: tout vert, y compris les nouveaux tests de `test_web_tokens.py` et `test_web_app.py`
- `uv run --with playwright==1.56.0 python tools/e2e/run_e2e.py` -- expected: aucun FAIL ; scénario `themes` passé ; captures `NN-theme-*` écrites ; captures existantes réécrites et inchangées en apparence (thème clair)

**Manual checks (if no CLI):**
- Relire les captures sombres : barre haute et bulle sur violet profond, cartes teintées lisibles, jaune toujours doublé de « RÉSEAU », schéma (frontière, zones, robot) lisible, diagnostic et `/models` sans fond blanc résiduel.

## Décisions prises par défaut

- **Jumeaux `-dark` dans `colors`** : c'est la forme prévue par le format DESIGN.md (`design-md-spec.md`), qui garde un seul fichier et un seul test. Chaque couleur a son jumeau, même quand la valeur est identique, pour qu'une couverture incomplète se voie.
- **Cinq jetons de rôle** plutôt qu'une redéfinition des jetons existants : `ink`, `on-ink` et `on-primary` jouent deux rôles qui divergent en sombre (texte et fond, texte sur l'encre et sur la discipline). Leur valeur claire est identique à l'ancienne, ce qui ne change rien au thème clair.
- **Bloc `@media` sur `:root:not([data-theme])`** : c'est le « sans attribut » demandé. « Clair » pose `data-theme="light"`, qui l'emporte donc sur un poste sombre.
- **Script classique partagé, `static/theme.js`**, chargé en tête plutôt que copié en ligne dans chaque page. Un module serait différé et laisserait passer un flash. Le coût, une requête locale en `no-cache`, est négligeable.
- **Clé `wavestack.theme`** (`system`, `light`, `dark`), sur le modèle des autres clés `wavestack.*`. Rien côté serveur : c'est un réglage d'affichage (AD-18).
- **Sélecteur natif `<select>`**, statique dans le HTML, placé avant « Réinitialiser » ; libellés « ◐ Système », « ☀ Clair », « ☾ Sombre ». Il est aussi sur le diagnostic et sur `/models` : la story couvre ces pages, et y changer de thème évite un aller-retour.
- **Pas de synchronisation en direct entre onglets** : chaque page lit le choix à son chargement. Cela suffit pour un seul formateur.
- **Texte sur rouge en `on-vivid` dans les deux thèmes** : DESIGN.md prescrit déjà « texte encre sur rouge ». C'est la seule retouche visible du thème clair, et elle améliore le contraste (3,7 → 5,3).
- **`primary-deep` sombre clair (`#C9BDFF`)** : son rôle de texte sur `primary-soft` l'emporte. L'ombre pleine du bouton primaire devient un relief clair, comme le reste des reliefs sombres.
- **Robot** : visière `surface-raised` et visage `ink`, inversés en sombre (écran sombre, yeux clairs), sur une plaque `ink-fill`. Aucun jeton propre au robot.
- **Balayage des contrastes E2E** : il est bloquant en sombre. En clair, il signale en `known` (« clair-préexistant ») les échecs antérieurs à la story, comme le texte `danger` sur blanc.
- **`/models`** : il est couvert parce que la story 25 précède celle-ci. Si la story 25 n'est pas livrée, sa part du scénario et du test est sautée, et le fait est consigné dans le rapport.
- **SPEC.md et README** : inchangés, car ni l'un ni l'autre ne décrit les réglages d'affichage. EXPERIENCE, DESIGN et la spine portent le comportement.
- **« Captures de la Vue humain »** : lu comme les captures E2E de la Vue humain et du schéma en thème sombre.

## À vérifier sur PC

- **Suivi du mode Windows**
  - **Geste** : Paramètres, Personnalisation, Couleurs, « Choisir votre mode » = Sombre, puis lancer `uv run wavestack` dans PowerShell et ouvrir l'atelier dans Chrome puis dans Edge, sélecteur sur « Système ». Repasser Windows en Clair sans recharger.
  - **Attendu** : l'atelier passe en sombre, puis revient en clair de lui-même.
  - **Critère** : bascule en moins de 2 s, sans rechargement, dans les deux navigateurs.
  - **Moyen** : à la main.
- **Pas de flash sur un poste chargé**
  - **Geste** : « Sombre » choisi, lancer un changement de modèle vers Qwen3.5-4B (GGUF), puis appuyer sur F5 pendant le chargement, dans Edge.
  - **Attendu** : aucun éclair blanc au rechargement.
  - **Critère** : aucune image claire visible à l'œil sur 5 rechargements. Au besoin, Performance de DevTools, où la première image est déjà sombre.
  - **Moyen** : à la main (DevTools).
- **Lisibilité en projection et en visio**
  - **Geste** : scénario « Outils réseau », envoyer « Résume l'article Wikipédia sur le Mont-Saint-Michel. » en thème sombre, projeter, puis partager l'écran dans Teams à 125 %.
  - **Attendu** : barre haute, légendes, segments, jaune « RÉSEAU » et schéma lisibles.
  - **Critère** : Anaël lit la jauge, les lignes d'état des briques et les nœuds du schéma à 3 m et dans la visio. Il tranche entre clair et sombre pour la salle.
  - **Moyen** : à la main (œil humain).
- **Contrastes réels**
  - **Geste** : dans Edge, thème « Sombre », DevTools, Lighthouse, Accessibility, Analyze, sur l'atelier après le tour ci-dessus, puis sur `/diagnostic` et `/models`.
  - **Attendu** : aucun défaut « Contrast ».
  - **Critère** : 0 élément signalé sur les trois pages.
  - **Moyen** : Lighthouse à la main, ou Claude in Chrome.
- **Mémorisation sans droits d'administrateur**
  - **Geste** : choisir « Sombre », fermer Chrome, relancer `uv run wavestack`, puis refaire la même chose dans une fenêtre InPrivate d'Edge.
  - **Attendu** : sombre repris dans Chrome ; dans InPrivate, choix possible sans erreur, puis oublié à la fermeture.
  - **Critère** : thème repris au lancement suivant, aucune erreur dans la console.
  - **Moyen** : Playwright (Chromium de `%LOCALAPPDATA%\ms-playwright`) ou à la main.
