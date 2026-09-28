---
title: 'Vue liée au survol et lecture guidée des volets'
type: 'feature'
created: '2026-09-28'
status: 'ready-for-dev'
review_loop_iteration: 0
followup_review_recommended: false
context:
  - '{project-root}/CLAUDE.md'
  - '{project-root}/_bmad-output/planning-artifacts/ux-designs/maquette-refonte-2026-09-28.html'
  - '{project-root}/_bmad-output/planning-artifacts/ux-designs/ux-agentic-harness-training-demo-2026-09-22/EXPERIENCE.md'
  - '{project-root}/_bmad-output/planning-artifacts/ux-designs/ux-agentic-harness-training-demo-2026-09-22/DESIGN.md'
  - '{project-root}/_bmad-output/planning-artifacts/architecture/architecture-agentic-harness-training-demo-2026-09-23/ARCHITECTURE-SPINE.md'
  - '{project-root}/_bmad-output/specs/spec-agentic-harness-training-demo/stories/33-contrastes-et-code-couleur-par-discipline.md'
  - '{project-root}/_bmad-output/specs/spec-agentic-harness-training-demo/stories/23-donnees-sortantes-visibles-en-tetes-compris.md'
  - '{project-root}/tools/e2e/README.md'
warnings:
  - oversized
deferred: []
---

<intent-contract>

## Intent

**Problem:** Les cinq volets montrent le même tour sans le relier. La sélection synchronisée (FR-4) ne vit que dans le schéma : elle passe par `data-component`, que seuls les nœuds portent. Un segment de contexte, une étape ou une carte n'éclairent rien ailleurs, et Échap n'efface pas la sélection. Rien ne dit dans quel ordre lire les volets. Le rail d'Orchestration nomme les étapes par des noms (« Appel au modèle ») sans montrer qui agit. Rien ne résume ce qui a quitté le poste pendant le tour. Aucun réglage n'agrandit les textes pour la salle : le contrôle « Aa » de DESIGN.md n'a jamais été construit.

**Approach:** On reprend les principes d'interaction de la maquette du 2026-09-28 :
- Chaque élément liable porte ses clés de liaison, tirées du journal : brique, composant, appel. Un survol, un focus ou un clic éclaire, dans tous les volets, les éléments qui partagent une de ces clés.
- Les volets sont numérotés, avec un sous-titre.
- Le rail devient une frise : une pastille par acteur, un verbe d'action, les chiffres à droite.
- Un bilan des sorties du poste s'affiche sous le schéma. Il se fonde sur les données sortantes de la story 23 et sur l'hébergement du modèle du tour.
- Un bouton « Mode projection » agrandit tous les textes. Le navigateur le mémorise.

## Boundaries & Constraints

**Always:**
- `uv`, `ruff` et `pytest` (CLAUDE.md). Code et identifiants en anglais ; textes d'interface en français.
- AD-1 : les liens viennent des champs reçus (`brick`, `component`, `call_id` de l'enveloppe, `id` des nœuds, `kinds` des groupes de jauge). Le JS ne contient aucune table brique → composant écrite à la main. Compter les éléments d'une liste reçue reste permis (appels, requêtes).
- Story 33 : aucune couleur écrite en dur dans `app.css` ou `app.js`, seulement des variables de `tokens.css`. Un contour ou un estompage n'est jamais le seul signal : un élément sélectionné garde son contour encre.
- `prefers-reduced-motion: reduce` : aucune transition sur l'estompage ni sur les contours.
- On garde la sélection existante : `store.selection` reste l'id de la source cliquée. Le schéma (`schemaNode` : déplier un serveur MCP) et la story 23 (`revealOutbound`, quand `store.selection === node.id`) le lisent.
- Aucune information n'est réservée au survol : le clic donne le même éclairage, en sélection persistante.
- Pour le front, le Code Map s'appuie sur les noms de symboles, pas sur les lignes. Les stories 33 puis 23 modifient les mêmes fichiers juste avant celle-ci.
- Aucune dépendance nouvelle. Aucun vrai modèle dans le conteneur : on utilise les doublures du dépôt (faux moteur, faux serveurs `tools/e2e`, GGUF synthétiques, faux fournisseurs). Le réseau sortant est coupé par le lanceur E2E.
- Aucune story livrée ne casse : `pytest` complet vert, E2E sans FAIL. Mettre à jour EXPERIENCE.md, DESIGN.md, SPEC.md et ARCHITECTURE-SPINE.md là où un comportement décrit change. Ajouter les vérifications au parcours E2E et mettre les captures à jour.

**Never:**
- Ne changer ni les événements existants, ni `step_id` / `call_id`, ni l'API HTTP. On ajoute un seul champ optionnel : `ArchitectureNode.sends_fr`.
- Pas de clic dans le vide pour effacer, pas de lien message → tour, pas de sélection d'appel qui change Contexte LLM : hors périmètre (voir Décisions).
- Pas de palette sombre (story 31), pas de lecture groupée du contexte (story 32), pas de refonte de la grille des volets ni de `diagnostic.html`.
- Aucune perte du détail dépliable des étapes, de « Suivre le direct », des tons d'erreur ni des étapes toujours dépliées (8d).

## I/O & Edge-Case Matrix

| Scenario | Input / State | Expected Output / Behavior | Error Handling |
|----------|--------------|---------------------------|----------------|
| Survol d'une carte | Pointeur sur la carte Outils après un tour Wikipédia | `body.linking` ; les nœuds `tools.*`, les segments `brick: tools` et les étapes d'outil ont `.is-linked` ; la carte Mémoire globale est estompée | — |
| Focus clavier | Tab jusqu'à un segment de Contexte LLM | Même éclairage qu'au survol ; le perdre efface | — |
| Nœud du modèle | Survol de la plaque du modèle | Les segments affichés dans Contexte LLM et toutes les étapes d'appel des tours affichés sont éclairés | — |
| Clic | Clic sur le nœud Calculatrice | `store.selection = "tools.calculator"` ; les éléments liés ont `.is-selection-linked` (contour encre) dans chaque volet ; puce d'un volet masqué lié : « lié » | Re-clic : sélection effacée |
| Échap | Sélection active, aucun tiroir ni menu ouvert | Sélection effacée ; aucun `.is-selection-linked` | Tiroir ouvert : Échap le ferme d'abord (inchangé) |
| Rendu pendant un tour | Survol maintenu pendant le streaming | L'éclairage survit aux rendus (`applyLinks` après chaque rendu) | Élément sous le pointeur retiré : le survol suivant recalcule |
| Bilan, cloud et réseau | Tour Wikipédia, faux cloud, réseau coupé | « Au tour N, les données ont quitté le poste K fois : vers le modèle chez {fournisseur} (contexte complet, a appels) et vers Résumé Wikipédia (le titre de l'article, 1 requête en échec). » | Requête sans `component` (story 23 absente) : destination = hôte de l'URL |
| Bilan, local | Tour avec le faux llama-server ou Ollama | « Au tour N, aucune donnée n'a quitté le poste : le modèle tourne sur ce poste et aucun service réseau n'a été contacté. » | — |
| Aucun tour | Lancement, ou après Vider la conversation | « Aucun tour affiché : rien n'a quitté le poste pendant un tour. » | — |
| Mode projection | Clic sur « Mode projection », rechargement | `html.projection`, corps à 18 px, `aria-pressed="true"`, conservé après rechargement et Réinitialiser | Stockage refusé : le mode marche, sans mémoire |

</intent-contract>

## Code Map

- `src/wavestack/web/static/app.js`, par symbole :
  - État et sélection : `store` (`selection`), `select`, `paneOfComponent`, `render`, `renderChips` (puce « lié »), `renderPaneVisibility` (`.pane.is-selected`). Les écritures directes de `store.selection` dans `ragBody`, `rerankBody` et `compressionBody` passent désormais par `setSelection`.
  - Clavier : l'écouteur `keydown` sur Escape dans `boot` (ordre : dialogues, tiroirs, menu, focus). La boucle de 250 ms dans `boot` rafraîchit `renderChat` et `renderSteps` sans passer par `render`.
  - Cartes : `renderBricks`. `label.brick-head` contient l'interrupteur et `.brick-name` : un clic sur le nom bascule la brique. On y trouve aussi `disciplineLegend` (story 33).
  - Jauge : `renderGauge` (`.gauge-seg`, `title`). `store.gauge` est affecté dans `applyEnvelope` (`context_preview`, `context_rendered`, `context_reconciled`) et au démarrage.
  - Contexte : `renderContextBody` (tour montré : le dernier tour affiché avec `context`), `appendSegments` (`.ctx-segment`), `renderSubContext`, `reasoningBlock`, `renderChat` (bloc de raisonnement de la Vue humain).
  - Orchestration : `turnRows`, `stepRows` (lignes `:catalog`, `:reinject`, `:call`, `:ask`, outil, hook, rag…), `rowDiscipline` et `brickCategory` (story 33), `delegateRow`, `connectRow`, `stepNode` (`.turn-step-tile`, `.turn-step-title` = `.turn-step-name` + `.turn-step-note`, `.turn-step-actor`, `net-mark`, `net-host`, `.turn-step-figure`), `ACTORS`, `toggleStep` (`o.selected`), `renderSteps`, `turnNumber`, `turnName`, `allSteps`, `hostOf`.
  - Schéma : `schemaButton` (`data-component`, `select`), `renderSchema` (clé de reconstruction, remplacement des robots), `buildSchema` (cadre `core.harness`, `.arch-cloud-model`, `.arch-server-model`), `robot`, `schemaNode` (pastille « non contacté » tirée de `node.contact`), `hookStrip`.
  - Données sortantes (story 23) : `case "outbound_request"` (entrées `step.outbound`, avec `component` depuis la 23).
- `src/wavestack/web/static/index.html` -- en-têtes `.pane-heading` (titres et sous-titres actuels), `#gauge-bar` (`role="img"`), `.top-bar` (où placer le bouton), `.pane-body-schema` (où placer le bilan).
- `src/wavestack/web/static/app.css` -- `.pane-chip.is-linked`, `.pane.is-selected`, `.turn-step-line` (grille `tile title trigger actor mark host figure chevron`, enfants en `pointer-events: none`), `.turn-step-tile`, `.arch .is-selected`, les deux blocs `prefers-reduced-motion`, et les `font-size` en px bruts (`9px`, `10px`, `11px`, `13px`, `14px`) hors jetons.
- `src/wavestack/web/static/tokens.css` -- rampe `--typography-*-font-size` (corps 14 px) et `--spacing-top-bar-height`. `tests/test_web_tokens.py` exige que ce fichier soit le miroir exact du frontmatter de DESIGN.md : aucun second bloc ici.
- `src/wavestack/trace/catalog.py` -- `ArchitectureNode` (ajouter `sends_fr`). `ActiveModel` (`hosting`, `provider`, `kind`), lu dans `turn.model`.
- `src/wavestack/tools/registry.py` -- `ToolText` ; `src/wavestack/mcp/servers.py` -- `ServerText`.
- `content/tools.yaml` (`public_holidays`, `wikipedia_summary`, `fetch_page`) et `content/mcp.yaml` (`datagouv`, `mslearn`).
- `src/wavestack/session/app_session.py` -- `_emit_architecture` (branche `is_tool and hosting == "network"`) et `_mcp_node`.
- `src/wavestack/net/factory.py` -- `_check_and_trace` ne trace jamais la boucle locale. Le faux cloud des E2E (`127.0.0.1`) n'émet donc pas d'`outbound_request{origin: model}`.
- `tests/test_tools.py`, `tests/test_mcp.py` -- nœuds réseau de `architecture_changed`.
- `tools/e2e/run_e2e.py` -- `Run` (`shot`, `shot_element`, `css`, `token_color`, `card`), `s_native_tools`, `s_network_tools`, `s_disciplines` (tuiles repérées par `.turn-step-name`, « Appel au modèle », « Description des outils », « Résumé Wikipédia »), `s_local_server`, `SCENARIOS`. Lignes d'actions repérées par titre : `s_subagent`, `_memory_step`, `_rag_step`, `_rerank_step`, `_compression_step`. `tools/e2e/stack.py` (faux cloud en boucle locale).

## Tasks & Acceptance

**Execution:**
1. `src/wavestack/trace/catalog.py`, `tools/registry.py`, `mcp/servers.py`, `content/tools.yaml`, `content/mcp.yaml`, `session/app_session.py` -- Ajouter `sends_fr: str | None = None` à `ToolText`, `ServerText` et `ArchitectureNode`. Textes :
   - `public_holidays` : « l'année demandée » ;
   - `wikipedia_summary` : « le titre de l'article » ;
   - `fetch_page` : « l'adresse de la page » ;
   - `datagouv` : « la recherche et ses arguments » ;
   - `mslearn` : « la question posée ».
   `_emit_architecture` et `_mcp_node` recopient ce texte sur les nœuds réseau. Raison : le bilan dit ce qui part (AD-19, AD-1).
2. `tests/test_tools.py`, `tests/test_mcp.py` -- Le nœud `tools.wikipedia_summary` porte « le titre de l'article », `tools.calculator` n'a pas de `sends_fr`, et le nœud `mcp.datagouv` a le sien. Raison : verrouiller le contenu émis.
3. `app.js` (liaison) -- Ajouter `setLinks(node, keys)`, qui écrit `data-links` (clés séparées par des espaces, sans doublon ni vide), et `linkKeysOfComponent(id)`, qui renvoie `[id]`. L'état d'interface gagne `store.linkHover` (clés) et `store.selectionKeys`.
   - `select(id, keys)` bascule la sélection. `setSelection(id, keys)` la pose sans bascule, pour les extraits RAG, le reranking et la compression. `clearSelection()` efface aussi `store.orch.selected`.
   - Des écouteurs délégués sur `document` (`pointerover` et `focusin` pour poser, `pointerout` et `focusout` pour retirer) prennent l'élément `[data-links]` le plus proche. S'il n'y en a pas, l'éclairage s'efface.
   - `applyLinks()` pose `body.linking`, `.is-linked` (survol ou focus) et `.is-selection-linked` (sélection) sur chaque élément `[data-links]` qui partage une clé. Elle tourne à la fin de `render()` et après la boucle de 250 ms.
   - `renderChips` marque une puce quand le volet masqué contient un élément `.is-selection-linked`. La puce devient alors « + Nom · lié », avec un `aria-label` qui le dit. `renderPaneVisibility` ne pose plus `.pane.is-selected`.
   - Échap efface la sélection après les tiroirs et le menu, et avant la sortie du mode focus.
   Raison : les points (1) et FR-4.
4. `app.js` (clés par élément, voir la table des Design Notes) :
   - Cartes : un clic hors des contrôles sélectionne (`id` = `brick:{id}`).
   - Segments de Contexte LLM et de la jauge : `tabindex="0"`, sélection par clic, Entrée ou Espace. `#gauge-bar` passe en `role="group"`, et chaque segment a un `aria-label` égal à son infobulle.
   - `store.gauge` garde `callId` depuis l'enveloppe.
   - Chaque ligne de `stepRows` reçoit `links`. `stepNode` les écrit sur `.turn-step`. Un clic sur la ligne déplie l'étape (comme avant) et sélectionne `step:{key}`.
   - Schéma : les nœuds, puces, hooks, le cadre `core.harness` et la plaque du modèle portent leurs clés. Celles du modèle sont patchées sans reconstruire le schéma.
   - Vue humain : le bloc de raisonnement porte `reasoning`.
   Raison : les cinq sources demandées.
5. `app.css` -- Styles de liaison, en variables seulement :
   - Survol : estompage à 0,35 (`body.linking [data-links]:not(.is-linked)`) et anneau de 2 px de la discipline de l'élément (`--discipline`), en encre pour `network` et `neutral`.
   - Sélection : `outline` de 2 px `--color-ink`, décalé de 2 px, sans estompage.
   - Transitions de 150 ms, supprimées sous `prefers-reduced-motion`.
   Raison : la maquette (`.hl`) et l'accessibilité.
6. `index.html`, `app.css` (volets numérotés) -- Ajouter `span.pane-step` (`aria-hidden`, pastille `ink` / `on-ink`) devant le titre de quatre volets :
   - 1 Vue humain, « Ce que voit l'utilisateur » ;
   - 2 Contexte LLM, « Ce que le modèle lit, dans l'ordre » ;
   - 3 Orchestration, « Ce que fait le harnais, pas à pas » ;
   - 4 Schéma d'architecture, « Où tourne chaque pièce ».
   Le panneau des briques reste sans numéro. Sous sa légende, il affiche l'aide « Survolez une brique : elle s'éclaire dans le contexte, l'orchestration et le schéma. » Raison : le point (2).
7. `app.js`, `app.css` (frise) -- Dans `stepNode`, la tuile affiche la pastille de l'acteur : `R` si la ligne a `net` et vient d'un outil ou d'une connexion, sinon `M`, `H` ou `U` selon `row.actor`. Elle garde `data-discipline` (story 33).
   - La ligne passe sur deux rangées. En haut, l'icône du type puis `.turn-step-title`. En dessous, `trigger`, `.turn-step-actor` (texte inchangé), « · via le réseau » pour un appel à un modèle `hosting: network`, puis `net-mark` et `net-host`. Le chiffre et le chevron restent à droite, et les règles de troncature de la 8d restent en vigueur.
   - Nouveaux titres : `:catalog` « Décrit les outils » ; `:call` « Appelle le modèle » (« Répond » pour la réponse finale) ; `:ask` « Demande un outil » ; exécution réseau « Exécute l'outil hors du poste », sinon « Exécute l'outil », avec le libellé de l'outil en `row.note` ; `:reinject` « Réinjecte le résultat ». Les autres titres ne changent pas.
   Raison : le point (3).
8. `index.html`, `app.js`, `app.css` (bilan) -- Ajouter `p#schema-outbound.schema-outbound` après `#schema`. `renderOutboundSummary()`, appelée par `render`, porte sur le dernier tour de `shownTurns()` (voir la note).
   - `schemaNode` remplace la pastille des nœuds réseau par « contacté » ou « non contacté », pour ce tour, avec l'infobulle « Au tour N : contacté. ». Sans tour affiché, il retombe sur `node.contact`. « indisponible » l'emporte toujours.
   Raison : le point (4).
9. `index.html`, `app.js`, `app.css` (projection) -- Ajouter `button#projection-toggle` (« Mode projection », `aria-pressed`) avant « Réinitialiser ». Il bascule `document.documentElement.classList` `projection`, mémorisé sous `wavestack.projection` (lecture et écriture dans un try/catch).
   - Dans `app.css`, `:root.projection` redéfinit les `--typography-*-font-size` par 9/7, arrondis : 19→24, 13→17, 18→23, 16→21, 14→18, 12→15, 20→26. Il agrandit aussi `--spacing-top-bar-height` pour que la barre tienne sur une ligne.
   - Les tailles en px bruts passent en `em` ou en jeton.
   - `scheduleWires()` est appelé après la bascule.
   Raison : le point (5) et NFR-9.
10. `EXPERIENCE.md` -- Réécrire ces entrées :
    - Interaction Primitives : vue liée au survol et au focus, sélection visible partout, Échap. Retirer « clic dans le vide ».
    - `pane-chip` (« · lié »), `pane` (numéro et sous-titre), `turn-rail` (frise sur deux rangées, pastilles, verbes).
    - `text-size-control` devient le Mode projection.
    - Nouveau composant `schema-outbound`, et les pastilles contacté ou non contacté du schéma.
    - Accessibility Floor : mouvement réduit, taille de texte.
11. `DESIGN.md` -- Ajouter les composants `pane-step`, `link-state` (valeurs d'estompage, d'anneau et de contour), `schema-outbound` et `projection-toggle` (en remplacement de `text-size-control`), avec la table de la rampe en mode projection dans Typography. Mettre `turn-step` à jour (pastille à lettre, deux rangées).
12. `ARCHITECTURE-SPINE.md`, `SPEC.md` -- Dans AD-12, ajouter `sends_fr` sur le nœud réseau. Dans CAP-4, le succès devient : survol, focus ou clic éclairent l'élément lié dans chaque volet, Échap efface. Dans NFR-9, ajouter : Mode projection mémorisé.
13. `tools/e2e/run_e2e.py`, `tools/e2e/README.md` -- Ajuster les repères des titres renommés dans `s_native_tools` et `s_disciplines` : lire `.turn-step-title` plutôt que `.turn-step-name` quand c'est le libellé de l'outil qu'on cherche. Même ajustement pour les vérifications de la story 23 sur « Exécution · … ».
    - Nouveau scénario `s_linked_view`, placé après `disciplines`, qui couvre les critères ci-dessous.
    - Vérification du bilan local dans `s_local_server`.
    - Captures : `35-vue-liee-survol`, `36-selection-liee`, `37-frise-orchestration`, `38-bilan-des-sorties`, `39-mode-projection`. Réécrire les captures touchées et mettre le README à jour.

**Acceptance Criteria:**
- Given le scénario `network_tools` à 1600 × 1000 et le tour « Résume l'article Wikipédia sur le Mont-Saint-Michel. », when le pointeur survole la carte Outils, then `body` a `linking`. Les nœuds « Résumé Wikipédia » et « Calculatrice », au moins un `.ctx-segment` et l'étape « Exécute l'outil hors du poste » ont `.is-linked`. La carte Mémoire globale a une opacité calculée < 0,5. Pointeur sur le titre de la barre haute : plus de `linking`.
- Given le même état, when on survole tour à tour un `.gauge-seg[data-discipline="harness"]`, la plaque du modèle et la dernière étape « Appelle le modèle », then la carte Outils, puis chaque `.ctx-segment` affiché, puis la plaque du modèle et les segments ont `.is-linked`. Given un `.ctx-segment` puis une `.turn-step-line` focalisés au clavier (`focus()` puis Tab), when on lit les classes, then l'éclairage est le même qu'au survol.
- Given le même état, when on clique le nœud « Calculatrice » puis on masque Contexte LLM, then la carte Outils a `.is-selection-linked` et un `outline-color` égal à `--color-ink`, et la puce « + Contexte LLM » contient « lié ». When on appuie sur Échap, then aucun `.is-selection-linked` ne reste et la puce ne contient plus « lié ».
- Given l'émulation `reduced_motion: "reduce"`, when on lit le `transition-duration` calculé d'une carte, then il vaut `0s`.
- Given le même tour, when on lit les en-têtes, then `.pane-step` vaut 1, 2, 3 et 4 pour Vue humain, Contexte LLM, Orchestration et Schéma d'architecture, avec les quatre sous-titres de la tâche 6. Le panneau des briques n'a pas de `.pane-step`.
- Given le même tour, when on lit ses lignes dans Orchestration, then les titres se suivent dans cet ordre : « Décrit les outils », « Appelle le modèle », « Demande un outil », « Exécute l'outil hors du poste », « Réinjecte le résultat », « Répond ». Leurs pastilles valent H, M, M, R, H, M. La ligne réseau montre « Résumé Wikipédia » et « 🌐 RÉSEAU → fr.wikipedia.org ». « Répond » a une figure qui correspond à `/écrits · [\d,]+ s/`. Un clic sur une ligne déplie toujours son détail.
- Given le même tour (faux cloud, réseau coupé par le lanceur), when on lit `#schema-outbound`, then il commence par « Au tour » et contient « quitté le poste {K} fois ». K est le nombre de `model_call_started` du tour plus le nombre d'`outbound_request{origin: brick}` du tour. Le texte contient aussi « vers le modèle chez » et « contexte complet », puis « vers Résumé Wikipédia (le titre de l'article, 1 requête en échec) ». Le nœud Wikipédia porte « contacté » et le nœud « Jours fériés » « non contacté ».
- Given `s_local_server` après un tour avec le faux llama-server, when on lit `#schema-outbound`, then il contient « aucune donnée n'a quitté le poste ».
- Given l'atelier, when on clique « Mode projection », then `html` a `projection`, le `font-size` calculé de `body` vaut `18px`, `aria-pressed="true"`, et « Réinitialiser » reste entièrement visible dans la barre à 1600 × 1000. Après rechargement puis Réinitialiser, le mode est toujours actif. Un second clic ramène `14px`.

## Spec Change Log

## Review Triage Log

## Design Notes

Clés de liaison (`data-links`). Deux éléments sont liés s'ils partagent une clé.

| Élément | Clés |
|---|---|
| Carte de brique | `{id}` et les `id` des nœuds `{id}.*` de `store.architecture` |
| Nœud, puce ou hook du schéma | `node.id` ; cadre du harnais : `core.harness` |
| Plaque du modèle (principal ou sous-agent) | `core.model` (ou `core.model_sub`), plus `call:{id}` de chaque appel de ce contexte dans les tours affichés |
| Segment de Contexte LLM | `brick`, `component`, `call:{id}` de l'appel montré |
| Segment de jauge | `brick` et `component` des `payload.segments` dont le `kind` figure dans `item.kinds`, plus `call:{store.gauge.callId}` |
| Étapes `:call` et `:ask` | `call:{step.id}` |
| Étapes `:catalog` et `:reinject` | `brick` et `component` des segments `tool_catalog` ou `tool_result` de cet appel |
| Autres étapes | `step.brick`, `step.component` ; sans l'un ni l'autre, `core.harness` |
| Bloc de raisonnement (Vue humain, Contexte LLM) | `reasoning` |

Bilan (`renderOutboundSummary`, sur le tour T) :

- **Appels au modèle.** Ce sont les étapes `call` de `allSteps(T)` qui ont `startedAt`, quand `T.model.hosting === "network"`. Le faux cloud des E2E tourne en boucle locale et n'est pas tracé ; en réel, ce nombre égale celui des `outbound_request{origin: model}`.
- **Requêtes.** Ce sont les entrées `step.outbound` des étapes d'outil de `allSteps(T)`, regroupées par `component`, dans l'ordre du premier contact. Le libellé et `sends_fr` viennent du nœud du schéma. Sans `component` ni nœud, la destination est l'hôte de l'URL.
- **Échec.** Une requête est « en échec » si l'étape qui la porte a `ended.status !== "ok"`.
- **Tour en cours.** « Au tour N (en cours), … ».
- **Modèle servi.** « le modèle est servi sur ce poste ({provider}) ».

Exemple : « Au tour 2, les données ont quitté le poste 3 fois : vers le modèle chez Groq (contexte complet, 2 appels) et vers Résumé Wikipédia (le titre de l'article, 1 requête). »

## Verification

**Commands:**
- `uv run ruff check .` -- expected: aucune erreur
- `uv run ruff format --check .` -- expected: aucun fichier à reformater
- `uv run pytest -q` -- expected: tout vert, y compris les tests `sends_fr` de `test_tools` et `test_mcp`, et `test_web_tokens` inchangé
- `uv run --with playwright==1.56.0 python tools/e2e/run_e2e.py` -- expected: aucun FAIL ; captures 35 à 39 écrites, captures existantes réécrites dans `tools/e2e/screenshots/`

**Manual checks (if no CLI):**
- Relire les captures 35 à 39 : éléments non liés estompés, contour encre de la sélection, frise H/M/R, bilan sous le schéma, textes agrandis sans chevauchement.

## Décisions prises par défaut

- **Clés partagées plutôt qu'une table de relations.** L'intersection symétrique de la maquette (`data-k`) garde AD-1 : chaque clé est un champ reçu. On lie par la brique, par le composant et par l'appel.
- **Modèle ↔ appels.** La plaque du modèle porte les clés de tous ses appels affichés. Une étape d'appel ne porte que la sienne : survoler un appel n'éclaire pas les autres.
- **Contexte LLM montre toujours le dernier appel** (comportement actuel). Survoler une étape d'appel plus ancienne n'éclaire que la plaque du modèle et l'étape elle-même.
- **Jauge.** Ses clés sont déduites des `segments` reçus avec la charge, via `kinds`. On ne touche pas à `gauge()`, que la story 33 vient de modifier.
- **Survol et sélection distincts.** Le survol estompe le reste et pose un anneau de discipline (encre pour réseau et neutre, le jaune n'atteignant pas 3:1). La sélection pose un contour encre sans estomper. La maquette ne montre que le survol.
- **Carte de brique.** Son nom est dans le `label` de l'interrupteur : un clic sur le nom bascule toujours la brique. La sélection se fait par un clic hors des contrôles. Au clavier, le focus de l'interrupteur éclaire les liens.
- **Échap.** Ordre : dialogues, tiroirs, menu Volets, sélection, mode focus. Le « clic dans le vide » d'EXPERIENCE.md n'est pas construit : on le retire du document.
- **`.pane.is-selected` est retiré.** Les contours des éléments le remplacent. Les puces des volets masqués disent « lié » en texte.
- **Frise.** La pastille `U` (utilisateur) s'ajoute à H, M et R pour les actions forcées et la validation H5. L'icône du type passe devant le titre. Le libellé d'acteur actuel est gardé : les E2E de la 8d le lisent. Seuls les titres cités par la story sont renommés, et le libellé de l'outil passe en `note`.
- **Deux rangées par étape**, comme la maquette, malgré l'« une ligne » de la 8d. Les règles de troncature de la 8d restent.
- **Bilan.** Il porte sur le dernier tour affiché, le même que l'activité du schéma. Les connexions MCP hors tour restent dans « Préparation du harnais ». K compte les requêtes et non les destinations (une indication précise, contrairement aux « 2 fois » de la maquette).
- **`sends_fr` en contenu** (AD-19) sur les nœuds réseau. Le JS ne connaît pas ce qu'envoie chaque outil.
- **Pastille contacté par tour**, pour rester cohérente avec le bilan. La ligne d'état de la story 33 garde le compte de la session.
- **Mode projection** : un bouton à deux états, à l'échelle 9/7 (14 → 18 px). Il remplace le « Aa 100/125/150 % » jamais construit. Les autres paliers passent par le zoom du navigateur. Il est redéfini dans `app.css`, car `tokens.css` doit rester le miroir exact de DESIGN.md. Réinitialiser ne le touche pas, comme la disposition des volets.
- **Numéros des volets** en `aria-hidden` : le nom accessible des volets ne change pas.
- **Story 23 absente** : le bilan retombe sur l'hôte de `url` (plan de la nuit).

## À vérifier sur PC

- **Vue liée pendant la génération**
  - **Geste** : dans Edge puis Chrome, lancer `uv run wavestack` (PowerShell) avec Qwen3.5-4B (GGUF), choisir le scénario « Outils natifs », envoyer « Combien font 12*37 ? », et pendant la génération survoler la carte Outils, puis le nœud Calculatrice.
  - **Attendu** : éclairage immédiat, sans clignotement, pendant que le texte arrive.
  - **Critère** : l'éclairage suit le pointeur en moins de 100 ms, et le CPU ne dépasse pas celui d'un tour sans survol de plus de 5 points (Gestionnaire des tâches).
  - **Moyen** : Claude in Chrome, et à la main pour le CPU.
- **Bilan réel**
  - **Geste** : avec Groq gpt-oss-120b (clé déclarée) et Internet, scénario « Outils réseau », envoyer « Résume l'article Wikipédia sur le Mont-Saint-Michel. », puis lire la phrase sous le schéma.
  - **Attendu** : « … vers le modèle chez Groq (contexte complet, n appels) et vers Résumé Wikipédia (le titre de l'article, 1 requête). »
  - **Critère** : K égale le nombre d'`outbound_request` du tour dans le journal, sans « en échec ».
  - **Moyen** : script AppSession (`get_journal().all_events()`) et Claude in Chrome.
- **Bilan avec Ollama**
  - **Geste** : choisir un modèle Ollama au diagnostic, envoyer un message sans brique réseau.
  - **Attendu** : « aucune donnée n'a quitté le poste : le modèle est servi sur ce poste (Ollama) ».
  - **Critère** : la phrase exacte, et zéro `outbound_request` dans le tour.
  - **Moyen** : Playwright (Chromium de `%LOCALAPPDATA%\ms-playwright`) ou à la main.
- **Mode projection en salle**
  - **Geste** : sur le vidéoprojecteur puis en partage Teams, cliquer « Mode projection », parcourir les quatre volets numérotés à 1280 × 720.
  - **Attendu** : les textes sont agrandis, la barre haute tient sur une ligne, rien ne se chevauche.
  - **Critère** : Anaël lit les sous-titres et la frise à 3 m ; aucun texte coupé dans la barre haute.
  - **Moyen** : à la main (œil humain).
- **Mouvement réduit Windows**
  - **Geste** : Paramètres, Accessibilité, Effets visuels, désactiver « Effets d'animation », recharger WaveStack, survoler une carte.
  - **Attendu** : l'estompage est instantané, sans fondu.
  - **Critère** : aucune transition visible, et l'éclairage reste identique.
  - **Moyen** : à la main.
- **Clavier et Narrateur**
  - **Geste** : Narrateur actif, Tab depuis la barre haute jusqu'à un segment de Contexte LLM, Entrée, masquer Contexte LLM, puis Échap.
  - **Attendu** : les éléments liés sont éclairés au focus ; la puce annonce « lié » ; Échap efface.
  - **Critère** : Narrateur lit « lié » sur la puce, et le focus reste visible à chaque étape.
  - **Moyen** : à la main.
