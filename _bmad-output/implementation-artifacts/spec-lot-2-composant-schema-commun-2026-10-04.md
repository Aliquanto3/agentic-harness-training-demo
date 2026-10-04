---
title: 'Lot 2 du plan de corrections du 2026-10-04 : composant de schéma commun (static/diagram.js)'
type: 'refactor'
created: '2026-10-04'
status: 'done'
baseline_commit: '805c71c1f3cacbdebad352c2a4d5ac241e2c9199'
route: 'dispatch'
review_loop_iteration: 0
context:
  - '{project-root}/_bmad-output/implementation-artifacts/plan-corrections-2026-10-04.md'
---

<frozen-after-approval reason="human-owned intent — do not modify unless human renegotiates">

## Intent

**Problem:** Le schéma animé n'existe que dans l'Atelier Harnais, mêlé à sa logique dans `app.js` et `app.css`. Les lots 4 (MCP), 5 (RAG) et 6 (LLM) ont besoin du même vocabulaire : blocs qui s'allument, fils animés, pas à pas ◀ ▶, « suivre le direct », explication au clic.

**Approach:** Extraire les primitives génériques dans un module ES `static/diagram.js` et leurs règles dans `pages.css` (chargé par toutes les pages), y ajouter le pas à pas et l'explication au clic, puis rebrancher le harnais sur le module sans changement visible.

## Boundaries & Constraints

**Always:**
- Harnais : rendu identique (positions, couleurs, animations, focus, sélection, mouvement réduit, projection, thème sombre).
- Le pas à pas et l'explication au clic sont livrés et testés, mais pas montés sur le harnais (son clic garde `select()` et le volet d'explication).
- Classes génériques `diagram-*` ; état allumé = classe `is-active` (lue par l'E2E). Couleurs par les jetons de `tokens.css` uniquement.
- Libellés du pas à pas en fr/en/de (mêmes clés, section `common.diagram`).
- Branche `refactor/lot-2-schema-commun-2026-10-04` créée depuis `fix/lot-1-quick-wins-2026-10-04` (lot 1 non fusionné dans `main`).

**Never:**
- Déplacer la logique propre au harnais : robot, bande des hooks, bacs `ARCH_GROUPS`, `schemaActivity`, géométrie tronc/rails/chemin, résumé sortant.
- Migrer l'Atelier LLM, RAG ou MCP (lots 4 à 6). Aucune dépendance externe ni CDN.

## I/O & Edge-Case Matrix

| Scenario | Input / State | Expected Output / Behavior | Error Handling |
|----------|--------------|---------------------------|----------------|
| Direct | pas à pas en « suivre le direct », `push(frame)` | la dernière étape s'affiche, position « n / n » | N/A |
| Retour | ◀ pendant le direct | quitte le direct, étape n-1 ; les `push` suivants ne déplacent pas la vue | N/A |
| Bornes | ◀ à l'étape 1, ▶ à la dernière | bouton désactivé (`disabled`) | N/A |
| Reprise | clic « suivre le direct » | revient à la dernière étape et la suit | N/A |
| Vide | aucune étape | ◀ ▶ désactivés, position masquée | N/A |
| Explication | clic sur un bloc avec texte | popover ancré au bloc ; Échap ou clic hors le ferme | sans texte : pas de popover |
| Panneau masqué | conteneur de largeur nulle | aucun fil dessiné, pas d'erreur | retour silencieux |

</frozen-after-approval>

## Code Map

- `src/wavestack/web/static/app.js:6774-6780` -- `SVG_NS`, `svgEl` : à déplacer.
- `app.js:6889-6900` -- `schemaButton` : garde `setLinks`/`select`, crée sa base via le module (`diagram-block`).
- `app.js:6990-7054` -- `renderSchema` : halo `is-active` (l.7044-7050) via le helper d'allumage du module.
- `app.js:7186-7188` -- couche SVG `arch-wires` → couche du module.
- `app.js:7329-7427` -- `scheduleWires`, `wirePath`, `wireMarker`, mesure `box` : génériques → module ; `drawSchemaWires` garde sa géométrie et appelle le module.
- `app.js:7460,7583-7584` -- `ResizeObserver`, `fonts.ready`, projection → planification du module.
- `app.js:1292-1318` -- motif popover ancré (`anchor-name`, `[popover]`) à réutiliser pour l'explication.
- `app.css:3184-3191` (`.arch-wires`), `:3668-3670`, `:3477-3480`, `:4473-4475` (halos), `:3687-3760` (tronc, chemin, flux, marqueurs, `@keyframes arch-flow`, mouvement réduit) → `pages.css` en `diagram-*` ; l'antenne du robot reste dans `app.css`.
- `tools/e2e/run_e2e.py:986-1000,3759-3790` -- sélecteurs `.arch-wires`, `.arch-path`, `.arch-marker.is-*` à renommer.
- `content/ui.yaml` (`common`), `content/i18n/{en,de}/ui.yaml` -- clés `common.diagram.*`.
- `tests/test_web_tokens.py:528` -- couleurs par jetons (couvre `diagram.js` d'office).

## Tasks & Acceptance

**Execution:**
- [x] `src/wavestack/web/static/diagram.js` -- créer : `svgEl`, fil, marqueur, mesure relative, couche de fils (rAF + `ResizeObserver` + `fonts.ready`, `schedule()` public), allumage, bloc cliquable, `explain(block, text)`, `createStepper(host, { onShow })` avec `push`/`show`/`follow` -- primitives des lots 4 à 6.
- [x] `src/wavestack/web/static/pages.css` -- règles `diagram-*` (couche, fils, chemin, flux animé, blocage, marqueurs, halo, pas à pas, popover, mouvement réduit) -- partagées.
- [x] `src/wavestack/web/static/app.js` + `app.css` -- rebrancher le harnais, retirer les règles déplacées -- aucune double définition.
- [x] `content/ui.yaml`, `content/i18n/{en,de}/ui.yaml` -- `common.diagram.{prev,next,live,position}`.
- [x] `tools/e2e/run_e2e.py` -- renommer les sélecteurs ; ajouter dans un scénario existant une vérification du module dans la page (`import('/static/diagram.js')`, pas à pas et explication sur un conteneur de test) couvrant la matrice.

**Acceptance Criteria:**
- Given le harnais en tour avec outil, H5 en attente ou H1 bloquant, when le schéma se dessine, then halos, chemin, flux et marqueurs ✋/✖ sont ceux d'avant (E2E E032 et rail verts).
- Given les captures E2E du schéma avant et après, when on les compare, then aucune différence visible hors contenu horodaté.
- Given `app.css`, when on cherche `arch-trunk`, `arch-path`, `arch-marker`, `arch-flow`, then aucune règle ne subsiste.

## Implementation Notes

- `diagram.js` exporte `svgEl`, `block`, `light`, `wire`, `marker`, `measure`, `wireLayer` (`schedule`, `clear`, `svg`), `explain`, `createStepper` (`push`, `show`, `follow`, `clear`, `index`, `live`, `frames`). `clear()` appelle `onShow(null, -1)`.
- Harnais : `schemaButton` crée ses blocs par `block()`, sauf les robots (leur `is-active` est leur pose, pas un halo) ; `drawSchemaWires({ height, box })` garde sa géométrie et rend les pièces au calque. Fils renommés `arch-trunk` → `diagram-wire` (`is-network` → `is-dashed`), `arch-path*` → `diagram-path*`, `arch-marker` → `diagram-marker`.
- Hors Code Map : `tests/test_ui_texts.py` déclare `diagram.js` parmi les scripts d'`index.html` (vérifie ses clés `common.diagram.*`, `label` compris).
- Limites dites dans l'en-tête du module : `explain()` repose sur l'anchor positioning (Chromium, comme le « ? » des briques) ; `createStepper` lit ses libellés à la construction (après `ready` d'i18n). Pas de `destroy()` sur `wireLayer` : à décider au premier atelier qui reconstruit son hôte (lot 4).
- Vérification finale : `ruff check` et `ruff format --check` propres ; `node --check` (diagram.js, app.js) sans erreur ; pytest `test_web_tokens`, `test_ui_texts`, `test_i18n`, `test_web_app` : 220 passés. E2E (`--channel msedge`, 14 scénarios de la Verification) : base 387 PASS, 0 FAIL ; final 400 PASS, 0 FAIL (13 vérifications du lot 2). Console : les deux mêmes erreurs qu'à la base (ERR_FAILED, 409).
- Captures : passage de base rejoué dans un worktree au commit `805c71c` puis comparé au passage final (Pillow, seuil 40) : captures du schéma (15 à droite, 33, 38, 48) identiques ; écarts restants dus au défilement du volet Contexte, aux horodatages, au port du llama-server et à un décalage de 2 px du volet Briques. Captures du dépôt laissées à leur version commitée.

## Review Triage Log

Passe 1 (Blind Hunter BH, Edge Case Hunter EC, Verification Gap VG).

| # | Constat | Verdict | Preuve | Route |
| --- | --- | --- | --- | --- |
| VG1/BH3 | Halo du vrai `#schema` jamais lu en style calculé | medium | E2E ne lit que la classe `is-active` ; seul `_diagram_module` lit `boxShadow`, sur l'hôte de test | patch |
| VG2/BH2b | Fils `is-dashed` / `is-flow` du harnais jamais vérifiés | medium | aucune assertion sur `is-dashed`, `is-flow`, `diagram-path-core` | patch |
| VG3 | Redessin au redimensionnement non testé | medium | `draws.shown > 0` atteint par le `schedule()` explicite ; l'hôte nul ne reçoit jamais de largeur | patch |
| BH1/EC12 | Hôte de test fixe non retiré si une étape lève | medium | tous les scénarios partagent une page (`run_e2e.py:12243`) : la surcouche bloquerait les clics suivants | patch |
| BH2a | ▶ hors direct jamais cliqué | low | seul l'état `disabled` de ▶ est vérifié | patch |
| BH5/EC3 | `clear()` ne prévient pas la page | low | `go(-1)` saute `onShow` : la vue garde la dernière étape | patch |
| EC1 | `show(i)` sur pas à pas vide, puis `push` : « Étape 0 / N », flèches grisées | low | `go` laisse `index = -1`, `live = false` | patch |
| BH8/EC6 | `light()` laisse `is-active` sur un nœud sans `diagram-block` | low | le nettoyage ne cible que `.diagram-block.is-active` | patch |
| BH6 | Groupe sans nom ; `aria-live` annonce chaque `push` en direct | low | `role="group"` sans `aria-label` ; `aria-live="polite"` permanent | patch |
| BH9b/EC11 | Pas de repli sans anchor positioning, non dit dans le module | low | cible Chromium déjà acceptée (`app.js:1294`) ; manque le commentaire | patch (commentaire) |
| BH11c/EC5 | `createStepper` lit `t()` à la construction, sans le dire | low | appel avant `textsReady` = clés brutes | patch (commentaire) |
| BH4/EC7 | `wireLayer` sans `destroy()` | low | aucun hôte reconstruit à ce jour ; ajout d'API à décider au lot 4 | reject |
| BH7 | Pas de primitive « bloc qui apparaît » | low | apparition faisable par `hidden` dans `onShow` ; API spéculative | reject |
| BH9a | `explain()` ne garde pas l'état ouvert entre reconstructions | low | aucun consommateur ne reconstruit ; spéculatif | reject |
| BH9c | `explain()` écrase un `anchor-name` existant | low | aucun appelant n'en pose | reject |
| BH10 | DESIGN.md sans le pas à pas ni le popover | low | lots 4 à 6 passent par `bmad-ux`, qui le documentera | reject |
| BH11a | `draw` ne reçoit pas `host` | low | cosmétique, aucun défaut | reject |
| BH11b/EC8 | `wireLayer` au chargement lève si `#schema` absent | false | `#schema` est statique dans `index.html:215`, seule page qui charge `app.js` | reject |
| EC2 | `show(NaN)` | false | appel hors contrat, jamais produit par les boutons | reject |
| EC4 | Étapes sans plafond | low | sessions de démo courtes | reject |
| EC9 | `explain()` sur un non-bouton | false | contrat documenté (`block()`) | reject |
| EC10 | `explain('')` puis `explain(texte)` : écouteur doublé | low | doublon inoffensif (`after` idempotent) | reject |

## Design Notes

Le harnais emploie les classes `diagram-*` sur ses fils ; spécificité à surveiller : `.arch .arch-node.is-active` (0,3,0) devient une règle générique plus faible, chargée avant `app.css` ; comparer les styles calculés des blocs allumés, sélectionnés, bloqués et réseau avant et après.

## Verification

**Commands:**
- `uv run ruff check . ; uv run ruff format --check .` -- expected: propre
- `node --check src/wavestack/web/static/diagram.js src/wavestack/web/static/app.js` -- expected: sans erreur
- `uv run pytest -q tests/test_web_tokens.py tests/test_ui_texts.py tests/test_i18n.py tests/test_web_app.py` -- expected: tout passe
- `$env:PYTHONUTF8=1; uv run --with playwright==1.56.0 python tools/e2e/run_e2e.py --channel msedge --only native_tools h5 hooks disciplines linked_view panes network_tools subagent data_flows themes rag rag_rerank compression local_server` -- expected: 0 FAIL, avant et après
- Comparaison des captures (`uv run --with pillow`) entre le passage de base et le passage final -- expected: écarts limités au contenu horodaté
