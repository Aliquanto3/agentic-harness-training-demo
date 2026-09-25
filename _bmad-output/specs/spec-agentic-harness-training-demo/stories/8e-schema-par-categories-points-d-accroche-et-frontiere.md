---
title: 'Schéma par catégories, points d''accroche et frontière'
type: 'feature'
created: '2026-09-25'
status: 'done'
route: 'dispatch'
review_loop_iteration: 0
baseline_commit: '6f33055ef9512ce049f552ef6418260c5fadbc78'
context:
  - '{project-root}/_bmad-output/planning-artifacts/ux-designs/ux-agentic-harness-training-demo-2026-09-22/EXPERIENCE.md'
  - '{project-root}/_bmad-output/planning-artifacts/ux-designs/ux-agentic-harness-training-demo-2026-09-22/DESIGN.md'
---

<frozen-after-approval reason="human-owned intent — do not modify unless human renegotiates">

## Intent

**Problem:** Dans le schéma, tous les composants hors du cadre Harnais sont des rectangles identiques posés en grille dans l'ordre d'arrivée : on ne distingue pas un hook d'un outil, la frontière Poste de travail / Réseau n'existe pas, et les arêtes se croisent (sprint-change-proposal-2026-09-25, B1 à B5 ; deferred-work, élément 6c).

**Approach:** Réécrire `renderSchema` selon EXPERIENCE.md et DESIGN.md, maquette `.working/maquette-orchestration-schema-v3.html` en référence : deux zones séparées par la frontière, bacs par catégorie, bande « Points d'accroche » des hooks dans le cadre Harnais, tronc et rails, chemin parcouru, arrêt H5 (✋) et blocage (✖). Token `architecture-band-height` à 250 px.

## Boundaries & Constraints

**Always:**
- Bacs rangés par `node.kind` et `node.hosting` d'`architecture_changed` (AD-12) : Outils (`tool`, local), Serveurs MCP (`mcp_server`, local), Fichiers (`file`), Skills (`skill`) côté Poste de travail ; Outils réseau (`tool`, network), Serveurs MCP publics (`mcp_server`, network) côté Réseau. Un bac vide n'est pas dessiné. Titre du bac : icône, nom, nombre.
- Cadre Harnais : robot et puces des nœuds `kind: brick` (mémoire courte, prompt système) empilés ; « Aucune brique : LLM nu » sans brique voulue ; bande « Points d'accroche » quand la brique Hooks est voulue, un hook par ligne (nom, point d'accroche).
- Catégorie lisible par le bac, la forme et l'icône, jamais par une couleur (B2, B5) ; couleurs réservées à l'hébergement et à l'état.
- Composant en action retrouvé par `envelope.component` de `tool_started`, `hook_decided` et `approval_requested` (déjà émis) : aucun changement de backend.
- Nœuds et hooks sont des boutons atteignables au clavier ; clic = sélection synchronisée (`data-component`, `select`) ; `file.audit` ouvre toujours le journal d'audit.
- Serveurs publics indisponibles toujours dessinés (FR-20) ; mouvement réduit respecté ; textes d'interface en français.
- Décision (Anaël, 2026-09-25) : un hook désactivé (décoché dans le panneau, ou H5 après « Autoriser et ne plus demander ») reste dans la bande, en tirets gris, marqué « désactivé ». La bande liste les hooks des sous-options de `bricks_changed` ; seuls les hooks activés (présents dans `architecture_changed`) peuvent être en action.

**Never:** aucun changement de backend, d'événement ni de `/api/state` ; aucun calcul d'état côté front (lire les étapes du tour et les nœuds, c'est de la mise en forme) ; pas de nouvelle dépendance ; ne pas toucher à Orchestration (8d) ni au redimensionnement des volets (8f) ; pas de clic sur le flux qui ouvre les données sortantes (hors B1).

## I/O & Edge-Case Matrix

| Scénario | État | Comportement attendu |
|---|---|---|
| LLM nu | aucune brique voulue | Zone Poste : cadre Harnais, robot, « Aucune brique : LLM nu ». Zone Réseau : « Aucun composant réseau : rien ne sort du poste. » Frontière visible. |
| Toutes briques | outils, MCP local et publics, skills, hooks | Bacs Outils, Serveurs MCP + Fichiers, Skills (sur deux colonnes) ; côté Réseau, Outils réseau et Serveurs MCP publics ; tronc parti de la bande, rails par colonne, tirets après la frontière. |
| Outil local en cours | `tool_started` sans `tool_ended` | Halo vert sur le nœud ; chemin vert de la bande au nœud par le tronc et le rail ; robot en pose « outil ». |
| Outil réseau ou MCP public en cours | idem, nœud `network` | Même chemin, en tirets animés après la frontière. |
| Validation H5 en attente | `approval_requested` sans `approval_resolved` | Halo sur H5 ; chemin arrêté avant la frontière, marqueur ✋ violet. |
| Blocage H1 | `hook_decided` `block` | Chemin arrêté à la bande, marqueur ✖ rouge ; H1 sur filet rouge « ✖ a bloqué » jusqu'au tour suivant. |
| H2 après un outil | `hook_decided` de `hooks.h2` | Halo sur H2 ; chemin vers le Journal d'audit (arête `hooks.h2 → file.audit`). |
| Hook désactivé | H5 après « ne plus demander », ou hook décoché | Hook en tirets gris dans la bande, « désactivé » ; jamais de halo. |
| Serveur MCP | connecté · indisponible | Pastille « N outils » ou « indisponible », icône 🔌 ou ⊘, raison en infobulle. |
| Volet redimensionné, focus, réaffiché | taille qui change | Tronc, rails et chemin recalculés sur la nouvelle disposition. |

</frozen-after-approval>

## Code Map

- `src/wavestack/web/static/app.js` `renderSchema` (l.2031-2173) : à réécrire. Garder `renderedSchemaKey` (reconstruction seulement si la clé change), `robotPose` (l.1958), `openAudit`, `select`. `robot()` (l.1979) : garder le dessin, le sortir dans un `<svg>` propre avec « Modèle » et le nom du modèle en HTML. `BRICK_ICONS` (l.1947) pour les puces ; `HOOK_ICONS` (l.1176) pour la bande.
- `app.js` `applyEnvelope` : cases `tool_started` (l.205) et `hook_decided` (l.250) : ajouter `component: envelope.component` à l'étape (champ de projection, pas d'état calculé). `shownTurns()`, `activeTurn()` pour lire l'étape en action.
- Nœuds (`src/wavestack/session/app_session.py:389-475`, lecture seule) : ids `core.harness`, `core.model`, `short_memory.history` / `system_prompt.prompt` (`kind: brick`), `tools.<nom>`, `mcp.<serveur>` (`kind: mcp_server`, `contact`, `tools`), `skills.<id>` (`loaded`), `hooks.h1|h2|h3|h5`, `file.demo_dir`, `file.audit`. Arêtes `{from, to, crosses_boundary}`. Outils du harnais (`load_tool_doc`, skills) : `component` = `core.harness`.
- `src/wavestack/web/static/index.html` (l.140-142) : remplacer `<svg id="schema-svg">` par un conteneur HTML.
- `src/wavestack/web/static/app.css` (l.1157-1190, 1524-1575, 1603-1733) : remplacer les styles `.arch-node`, `.arch-edge`, `.arch-harness*`, `.arch-chip` ; adapter `.robot*`.
- `src/wavestack/web/static/tokens.css:98` et frontmatter de `DESIGN.md` (`spacing.architecture-band-height`) : 200px → 250px ; `tests/test_web_tokens.py` compare les deux, sans valeur en dur.

## Tasks & Acceptance

**Execution:**
- [x] `src/wavestack/web/static/app.js` -- stocker `component` sur les étapes `tool` et `hook` ; réécrire `renderSchema` en HTML (zones, frontière, cadre, bande, bacs, nœuds) plus un calque SVG pour tronc, rails, chemin et marqueurs, tracé après mise en page et à chaque redimensionnement (`ResizeObserver`) -- B1, B3.
- [x] `src/wavestack/web/static/index.html` -- conteneur du schéma -- B1.
- [x] `src/wavestack/web/static/app.css` -- styles `arch-zone-*`, `arch-boundary`, `arch-group`, formes par catégorie, `arch-hook-strip`, `arch-trunk`, chemin et marqueurs selon DESIGN.md (`{rounded.sm}` partout, traits ≥ `{spacing.stroke-min}`) -- B3, B5.
- [x] `tokens.css`, `DESIGN.md` (frontmatter et phrase `[ASSUMPTION]` de Layout & Spacing) -- 250 px -- B4.

**Acceptance Criteria:**
- Given toutes les briques voulues, when le schéma s'affiche, then un hook, un outil, un serveur MCP, un skill et un fichier se distinguent sans lire leur libellé, et la frontière est visible.
- Given un tour, when l'étape en action change, then le halo et le chemin suivent sans reconstruire le DOM à chaque `model_delta`.
- Given le clavier, when on tabule dans le schéma, then chaque nœud et chaque hook prend le focus et Entrée le sélectionne.

## Design Notes

Composant « en action » (lu dans le dernier tour affiché, pendant qu'il tourne) : la dernière étape `tool` ou `hook`. Outil non terminé → nœud `step.component`, chemin plein. Hook `ask_human` non résolu → ✋. Hook `block` → ✖, tant qu'aucune autre étape outil ou hook ne suit. Autre décision de hook → halo sur le hook tant qu'il est la dernière étape du tour ; chemin vers un fichier seulement s'il existe une arête du hook vers un `file.*`. `component` = `core.harness` → pas de chemin. Fin du tour → plus rien en action ; le filet rouge du hook bloquant reste pour ce tour (comportement actuel).

Point d'accroche des hooks : table de libellés dans le front (comme `HOOK_ICONS`), libellés de la maquette : H3 « réception du message », H1 « avant un outil », H5 « avant un outil réseau », H2 « après un outil · fin du tour ». Serveur MCP sélectionné : la liste de ses outils se déplie sous le nœud, dans son bac.

Disposition (maquette `drawWires`) : colonnes du Poste = [Outils], [Serveurs MCP, Fichiers], [Skills en grille de 2] ; Réseau = [Outils réseau, Serveurs MCP publics]. Rail à 8 px à gauche de chaque colonne, amorce vers chaque bac ; tronc de la bande jusqu'au bas du schéma puis vers le rail le plus à droite, en tirets après la frontière.

## Verification

**Commands:**
- `node --check src/wavestack/web/static/app.js` -- expected: aucune erreur
- `uv run ruff check .` et `uv run pytest` -- expected: tout passe, `test_web_tokens.py` compris

**Manual checks:**
- Rejeu SSE scripté ou `uv run wavestack` : LLM nu ; toutes briques ; outil local, outil réseau, MCP public ; H5 en attente ; blocage H1 ; H2 ; serveur public indisponible ; mode focus et masquage d'un volet ; 1280×650.

## Implementation Notes

- Aucun changement de backend : `component` est lu dans l'enveloppe de `tool_started`, `hook_decided` et `approval_requested` et gardé sur l'étape.
- `renderSchema` a trois clés : la structure (architecture, briques voulues, hooks, hooks bloquants, sélection) reconstruit le DOM et restaure le focus par `data-focus-key` ; la pose du robot remplace seulement le robot ; l'activité (`schemaActivity`) ne déplace que la classe `is-active` et retrace le calque. Un `model_delta` ne reconstruit rien.
- Calque SVG retracé par `scheduleWires` après reconstruction, à chaque `ResizeObserver` de `#schema` et au chargement des polices.
- Ajouts hors spec : table `TOOL_ICONS` (tuile ronde des outils) ; skill chargé marqué d'une pastille « ✓ » (« Chargé » dans l'infobulle et le nom accessible) ; outil ou serveur réseau non contacté avec la pastille « non contacté ». Nœuds locaux sur fond blanc à bordure violette, comme la maquette : le token `arch-node-local` de DESIGN.md (fond violet) n'est pas appliqué, les formes de catégorie y seraient illisibles.
- Hauteur : toutes briques voulues, la bande de 250 px déborde de 50 à 70 px (cadre avec 4 hooks, colonne Réseau pleine) : le schéma défile ; mode focus et 8f pour ajuster.
- Vérifié par `node --check`, `ruff`, `pytest` (266 passés, `test_web_tokens.py` compris ; `uv run pytest` bute ici sur le lanceur du venv, `uv run python -m pytest` passe) et dans Chrome contre un rejeu SSE scripté (lignes de la matrice). Pas lancé sous `uv run wavestack` avec un vrai modèle, ni à 1280×650 exact.
- Audit de la matrice : pas de banc de test JavaScript dans le dépôt et aucune nouvelle dépendance permise ; les lignes de la matrice sont couvertes par le rejeu scripté dans Chrome, pas par un test automatisé (même écart que 5b, 6, 6b, 6c, 8c, 8d).

## Spec Change Log

## Review Triage Log

Passe 1 (2026-09-25) — relecteurs : blind-hunter (BH), edge-case-hunter (EC), verification-gap (VG).

| # | Constat | Verdict | Preuve | Route |
|---|---|---|---|---|
| BH1 | Un nœud réseau ne porte plus son « RÉSEAU » / 🌐 | medium | `schemaNode` n'affiche que l'icône de catégorie ; EXPERIENCE (FR-13) : un outil réseau porte toujours l'étiquette « RÉSEAU » ; l'ancien code préfixait 🌐. | patch |
| BH2 | Le flux qui franchit la frontière n'est pas cliquable | false | Exclu par le bloc figé (Never : « pas de clic sur le flux qui ouvre les données sortantes »). | rejeté |
| BH3 | Tokens de DESIGN.md en retard (`arch-node-local` violet plein, `arch-flow`, pas d'entrée `arch-group`…) | low | `arch-node-local` contredit la prose B3 et le code : correction directe. Nommage `arch-flow` et entrées manquantes : aucun consommateur (le test ne lit que couleurs, typo, rayons, espacements), pas de dommage nommé. | patch (token) / rejeté (reste) |
| BH4 / EC7 / EC9 | Nœud indisponible : la bordure en tirets efface le filet du skill et le double trait du MCP | medium | `.arch .arch-node.is-unavailable { border: … }` l'emporte sur `.arch-node-skill` et `.arch-node-mcp` ; hors réseau, cas courant en salle, catégories confondues (critère d'acceptation). | patch |
| BH5 | Sélectionner un serveur MCP public efface son double tiret | low | `.arch .arch-node.is-selected` remplace l'`outline` en tirets du réseau ; serveur typiquement cliqué en démonstration. | patch |
| BH6 | Un `kind` non prévu par `ARCH_GROUPS` disparaît | low | Tous les `kind` du catalogue actuel (catalog.py:57) sont rangés ; cas hypothétique, correctif = branche de repli. | rejeté |
| BH7 | Les arêtes d'`architecture_changed` ne sont plus dessinées une à une | false | Choix de la spec (tronc et rails, B1) ; arêtes lues pour le chemin hook → fichier. | rejeté |
| BH8 | Hook désactivé sélectionnable avec un id absent de l'architecture | false | `select` accepte tout id ; `paneOfComponent` retrouve le bouton de la bande par `data-component` ; aucun effet de bord. | rejeté |
| BH9 / EC5 | Tronc et rails périmés après le remplacement du robot | false | Le nom du modèle est dans `store.architecture` (clé de structure : reconstruction et `scheduleWires`) ; la pose ne change pas la taille du robot (svg 60×57). | rejeté |
| BH10 / EC6 | Sélection et dépliage non exposés aux lecteurs d'écran | low | Pas d'`aria-pressed` ; `aria-expanded` absent quand le serveur est replié. Correctif direct. | patch |
| BH11 | Chaque bac est un repère `region` | low | `<section aria-label>` : jusqu'à six repères. Correctif direct (`div role="group"`). | patch |
| BH12 | Hook inconnu : guillemets vides | low | Les quatre hooks déclarés ont un libellé ; hypothétique. | rejeté |
| BH13 | Valeurs en dur fragiles aux paliers 125 / 150 % ; marqueur ✖ qui peut déborder | maybe-false | À vérifier au palier 150 % dans Chrome ; si réel, low (le volet défile) ; correctif = refonte des décalages. | rejeté |
| BH14 / VG1 / VG2 | Aucun test automatique de `schemaActivity`, du rangement en bacs ni des états de la bande | medium | Aucun banc de test JS (même écart que 5b à 8d) ; la spec interdit toute nouvelle dépendance. | defer |
| EC1 / EC8 | Brique voulue sans sous-option cochée : rien dans le schéma | low | Cas rare (Outils voulus, aucun outil coché) ; le schéma montre les composants, il n'y en a pas ; correctif = branche de repli. | rejeté |
| EC2 | Hooks de la brique indisponible rendus comme actifs | false | La brique Hooks n'exige aucune capacité (registry.py:133) : jamais indisponible. | rejeté |
| EC3 | Brique Hooks sans `options` : bande absente | false | `_hook_options` renvoie toujours la liste des hooks déclarés. | rejeté |
| EC4 | Halo et ✖ restent pendant que le modèle réfléchit à nouveau | false | Choix des Design Notes (« tant qu'aucune autre étape outil ou hook ne suit »). | rejeté |
| EC10 | Pastille d'un nœud indisponible bordée de 1 px | low | Sous `{spacing.stroke-min}` exigé pour les traits du schéma. Correctif direct. | patch |
| EC11 | « `{rounded.sm}` partout » surévalué | false | La tâche vise les nœuds ; bacs `{rounded.md}` et cadre `{rounded.lg}` suivent DESIGN.md. | rejeté |
