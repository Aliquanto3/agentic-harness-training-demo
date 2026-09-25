---
title: 'Orchestration lisible : rail par tour, préparation du harnais, journal replié'
type: 'feature'
created: '2026-09-25'
status: 'done'
route: 'dispatch'
review_loop_iteration: 0
baseline_commit: '15301a4ccc776d616e44de9c9e2c8698a9541288'
context:
  - '{project-root}/_bmad-output/planning-artifacts/ux-designs/ux-agentic-harness-training-demo-2026-09-22/EXPERIENCE.md'
  - '{project-root}/_bmad-output/planning-artifacts/ux-designs/ux-agentic-harness-training-demo-2026-09-22/DESIGN.md'
---

<frozen-after-approval reason="human-owned intent — do not modify unless human renegotiates">

## Intent

**Problem:** Dès le lancement, Orchestration affiche chaque événement en JSON déplié (`renderJournal`), sous des cartes d'étapes empilées à plat, tous tours confondus (`renderSteps`) : le déroulé d'un tour ne se suit pas (sprint-change-proposal-2026-09-25, A1 à A10).

**Approach:** Front seul. Réécrire le volet selon EXPERIENCE.md et DESIGN.md, maquette `.working/maquette-orchestration-schema-v3.html` en référence : « Préparation du harnais » en haut, rail d'étapes groupé par tour (une ligne par étape, étape courante dépliée, « Suivre le direct »), journal des événements replié en bas.

## Boundaries & Constraints

**Always:**
- Le contenu des cartes actuelles (appel, outil, hook, validation H5 en lecture seule, appel mal formé, borne, préfixe, dépassement, connexion MCP) devient le corps déplié de l'étape correspondante ; aucune information n'est perdue.
- Ligne d'étape : tuile d'icône, titre, acteur (`🤖 modèle`, `⚙ harnais`, `👤 vous`), chiffre clé, chevron ; `🌐 RÉSEAU → hôte` si l'étape a des données sortantes. Troncature : titre d'abord, puis l'hôte ; marqueur RÉSEAU, acteur et chiffre clé jamais tronqués.
- Restent dépliés quoi qu'il arrive : appel mal formé, hook qui bloque, borne `retries`, dépassement, validation H5 en attente.
- Un clic ou une touche sur une ligne n'est jamais perdu par le rafraîchissement de 250 ms, et le focus clavier reste sur la ligne.
- « Vider la conversation » : comportement de la 8c conservé (tours et connexions MCP d'avant masqués) ; le journal n'est pas vidé.
- Mouvement réduit respecté ; libellés d'interface en français.
- Décision (Anaël, 2026-09-25) : dans le journal, les `model_delta` consécutifs d'un même appel sont fusionnés en une ligne « Morceaux de réponse × N » ; le titre « Journal des événements (N) » compte chaque événement ; le JSON de chaque morceau reste accessible en dépliant la ligne fusionnée.

**Never:** aucun changement de backend, d'événement ni de `/api/state` (AD-1, AD-2) ; aucun calcul métier côté front (grouper, compter les appels, formater une durée, c'est de la mise en forme) ; pas de sélecteur de tour ; pas de nouvelle dépendance ; ne pas toucher au schéma (8e) ni au redimensionnement (8f).

## I/O & Edge-Case Matrix

| Scénario | État | Comportement attendu |
|---|---|---|
| Lancement | aucun tour, MCP actif | Préparation : une ligne repliée par serveur (`connecté · N outils` ou `indisponible · raison`) ; note « Aucun tour pour l'instant. Envoyez un message : les étapes du harnais apparaîtront ici. » ; « Journal des événements (N) » replié. Aucun texte brut visible. |
| Tour en cours, direct | `turn_started` puis étapes | Seul le dernier tour est déplié ; l'étape courante est dépliée, point vert, et suivie au défilement si l'utilisateur était en bas. |
| Clic sur une étape | direct | Vue figée : l'étape se déplie ou se replie ; « ● Suivre le direct » apparaît dans l'en-tête ; un clic dessus revient au direct. |
| Nouveau tour | tour précédent déplié | Le précédent se replie à son en-tête (`Tour N`, extrait du message, statut, durée, appels au modèle) ; un clic le rouvre. |
| Connexion MCP entre deux tours | `afterTurn > 0` | Même ligne que la préparation, à sa place dans le rail. |
| Rechargement | rejeu complet | Même affichage ; le journal compte tous les événements rejoués. |

</frozen-after-approval>

## Code Map

- `src/wavestack/web/static/app.js` -- `applyEnvelope` (l.108) : projection par tour déjà complète (`turn.steps` de types `call`, `tool`, `hook`, `tool_call_malformed`, `limit_reached`, `prefix_not_reused`, plus `turn.overflow`, `turn.status`) et `store.offTurn` (connexions MCP, `afterTurn`, `seq`, `outbound`). À réutiliser tel quel ; seuls des champs d'UI s'ajoutent au store.
- `app.js` `renderSteps` (l.1143) et cartes `modelCallCards` (l.869, qui découpe déjà un appel en description des outils, réinjection, appel, demande d'outil), `toolCard`, `connectCard`, `hookCard`, `approvalTrace`, `malformedCard`, `outboundPayload` : réutiliser comme corps d'étape. `approvalCard` et `renderChat` (Vue humain) ne changent pas.
- `app.js` `renderJournal` (l.1257) : à remplacer. `boot` (l.1547) : `setInterval` de 250 ms qui appelle `renderSteps`. `CLEARED_FR` (l.385) : texte à aligner sur A5 (« journal des événements (replié, en bas d'Orchestration) »).
- `turn_ended.payload` : `status` (`completed`, `cancelled`, `limit`, `overflow`, `error`, `blocked`) et `duration_ms` ; `turn_started.payload.message`. Hooks : `payload.hook` (`h1`, `h2`, `h3`, `h5`).
- `src/wavestack/web/static/index.html` (l.100-115) : en-tête et corps du volet `orch`.
- `src/wavestack/web/static/app.css` (l.467-640) : styles `.steps`, `.step`, `.journal` à remplacer ; garder `.harness-event`, `.overflow-card`, `.outbound-payload`, `.trigger-badge-model`.

## Tasks & Acceptance

**Execution:**
- [x] `src/wavestack/web/static/index.html` -- en-tête d'Orchestration : indicateur de travail et bouton « ● Suivre le direct » (masqué en direct) ; corps : zone défilante (préparation + rail) puis `event-log` en bas -- A9.
- [x] `src/wavestack/web/static/app.js` -- réécrire `renderSteps` en `harness-prep` + `turn-rail` / `turn-group` / `turn-step` ; état d'UI (`live`, étapes et tours ouverts par l'utilisateur, étape sélectionnée) dans le store ; nœuds de ligne gardés d'un rendu à l'autre par clé stable -- A2, A3, A4, A10.
- [x] `src/wavestack/web/static/app.js` -- réécrire `renderJournal` : en-tête repliable « Journal des événements (N) », lignes rendues seulement une fois déplié (heure, nom français par table `kind → libellé`, nom technique, résumé d'une ligne), JSON par ligne à la demande -- A3.
- [x] `src/wavestack/web/static/app.css` -- styles selon DESIGN.md (filet vertical 2 px `{colors.line}`, tuile `{rounded.sm}`, point vert, sélection violet doux, journal sans couleur d'état, JSON sur crème) -- A8.

**Acceptance Criteria:**
- Given le lancement, when Orchestration s'affiche, then aucun JSON ni texte brut n'est déplié et le journal ne s'ouvre jamais seul.
- Given un tour avec outil réseau, when l'étape d'exécution est repliée, then sa ligne montre `🌐 RÉSEAU → hôte` ; dépliée, les données sortantes sont ouvertes.
- Given une validation H5 en attente, when le tour suit son cours, then l'étape « Validation humaine » reste dépliée, acteur « vous ».
- Given le rafraîchissement de 250 ms pendant un tour, when l'utilisateur clique ou appuie sur Entrée sur une ligne, then l'action s'applique et le focus reste en place.

## Design Notes

Icônes (doublées du titre) : appel au modèle 🤖, demande d'outil 🗨, exécution 🔧, réinjection ↩, hook selon `payload.hook` (H1 🛡, H2 📝, H3 💉, H5 ✋), connexion MCP 🔌 (⊘ si indisponible), erreur ✖. Acteur : appel, demande d'outil et outil du harnais (`source: harness`, chargement de doc ou de skill) → modèle ; exécution, réinjection, hook, borne → harnais ; validation H5 → vous. Statut de tour : « en cours », « terminé », « arrêté », « contexte dépassé », « limite atteinte », « bloqué », « erreur ». La numérotation « 1. à 5. » des cartes actuelles disparaît, comme dans la maquette.

## Verification

**Commands:**
- `node --check src/wavestack/web/static/app.js` -- expected: aucune erreur
- `uv run ruff check .` et `uv run pytest` -- expected: tout passe (aucun fichier Python touché)

**Manual checks:**
- `uv run wavestack` : lancement avec MCP actif (serveur local et public) ; tour avec outil réseau et H5 ; tour bloqué par H1 ; deux tours puis clic sur le premier ; « Suivre le direct » ; « Vider la conversation » ; rechargement en cours de tour ; volet étroit (troncature).

## Implementation Notes

- `applyEnvelope` inchangé. État d'UI ajouté au store sous `store.orch` (live, userOpen, turnOpen, selected, prepOpen, logOpen, logRowsOpen). La durée d'un tour terminé est relue dans son `turn_ended` de `store.journal` (mise en cache par tour) : aucun champ ajouté à la projection.
- Lignes, groupes et lignes du journal sont gardés par clé stable (`turnId:indexÉtape[:partie]`, `mcp:<seq>`, premier seq d'une ligne du journal) ; un rendu ne met à jour que leur texte. Un corps n'est reconstruit que si ses données changent ; ses chronos sont rafraîchis sur place (`data-since`). Les enfants d'une ligne ignorent le pointeur : le bouton reste la cible du clic.
- La ligne est une grille : la colonne du titre (`minmax(2.5em, 1fr)`) prend ce qui reste, puis l'hôte (`minmax(0, auto)`) se réduit ; marqueur RÉSEAU, acteur et chiffre clé gardent leur largeur. Sous 460 px de rail (grille à 5 volets par défaut en 1280 px), tout ne tient pas sur une ligne : le chiffre clé passe sous le titre (container query) plutôt que d'être coupé.
- L'étape courante (dernière ligne du dernier tour affiché) garde son point vert tant que le tour tourne ; en direct, elle reste dépliée après la fin, pour que la réponse ne se replie pas sous les yeux.
- Icônes ajoutées hors Design Notes : description des outils 🧰, chargement de documentation 📖, chargement de skill 📘, borne non bloquante ⏹, préfixe non réutilisé ℹ.
- Vérifié par `node --check`, `ruff`, `pytest` (266 passés) et dans Chrome contre un rejeu SSE scripté (MCP local, public et indisponible ; tour calculatrice ; outil réseau avec H5 ; blocage H1, appel mal formé et borne `retries` ; connexion entre deux tours ; dépassement ; rechargement en cours de tour ; clic et Entrée sous le rafraîchissement de 250 ms ; vidage ; fusion du journal). Pas lancé contre `uv run wavestack` avec un vrai modèle.
- Audit de la matrice : le projet n'a pas de harnais de test JavaScript et la spec interdit toute nouvelle dépendance ; les six lignes de la matrice sont couvertes par le rejeu SSE scripté dans Chrome ci-dessus, pas par un test automatisé du dépôt. Reste à faire : le test manuel sous `uv run wavestack` (Verification).

## Spec Change Log

## Review Triage Log

Passe 1 (2026-09-25) — relecteurs : blind-hunter (BH), edge-case-hunter (EC), verification-gap (VG).

| # | Constat | Verdict | Preuve | Route |
|---|---|---|---|---|
| BH1 | Exécution d'outil en erreur et appel au modèle en erreur ne restent pas dépliés | low | `turnRows` : `tone: "error"` sans `sticky` ; EXPERIENCE « Restent dépliés : événements en échec ». Serveur MCP indisponible : la raison est déjà sur la ligne, et la préparation est « repliée par défaut » (EXPERIENCE) : pas de défaut sur ce point. | patch |
| BH2 / EC3 | Clic sur une ligne qui reste dépliée : aucun effet visible, mais fige le direct et fait apparaître « Suivre le direct » | low | `toggleStep` bascule `userOpen` alors que `unfolded = row.sticky || …` ; cas fréquent en démonstration (clic sur un blocage rouge). | patch |
| BH3 | Fusion des `model_delta` contraire à « une ligne par événement » ; canaux mêlés dans le résumé | false / low | Fusion : décision d'Anaël dans le bloc figé. Canaux mêlés : résumé d'une ligne tronqué, cosmétique, correctif qui ajoute des branches : rejeté. | rejeté |
| BH4 / EC7 | Travail quadratique du journal ouvert pendant le streaming | low | `eventSummary` rejoint N chaînes courtes par image (quelques centaines) : négligeable ; le JSON n'est resérialisé que si la ligne fusionnée est ouverte. Correctif = cache incrémental : rejeté. | rejeté |
| BH5 | `renderSteps` calcule les lignes des tours repliés ; signature d'outil qui sérialise tout le résultat | low | `const rows = isLast ? lastRows : turnRows(turn)` hors condition `open` ; `sig: [ended, …]` stringifié à chaque image pour une étape d'outil ouverte. Correctif direct. | patch |
| BH6 / EC1 | Le suivi du direct s'arrête un rendu trop tôt | low | `model_call_ended` et `turn_ended` peuvent arriver dans la même image : `running` est déjà faux, pas de défilement vers la fin. | patch |
| BH7 | « Réponse finale » réutilise l'icône 🤖 ; acteur « modèle » pour un outil du harnais | low / false | Icône : DESIGN.md demande une icône par type, réponse finale comprise. Acteur : conforme aux Design Notes (le modèle déclenche le chargement). | patch (icône) |
| BH8 | Nom accessible chargé d'emojis, glyphes `::before` lus, pas d'`aria-controls` | low | Réel mais rare en salle ; correctif hors correction directe (restructurer les spans). | rejeté |
| BH9 | Logique de l'indicateur de travail dupliquée entre Vue humain et Orchestration | low | Doublon réel, sans défaut visible aujourd'hui ; correctif = refactorisation. | rejeté |
| BH10 | Le corps déplié répète le titre de la ligne | false | Le titre de la carte apporte de l'information (« Bloqué par le hook garde-fou », titre imposé par EXPERIENCE ; titre de la carte de dépassement imposé aussi). | rejeté |
| BH11 | Géométrie du rail en pixels fixes ; `flex` inopérant dans une grille | low | Aucun défaut visible ; nuisance hypothétique si un token change. | rejeté |
| BH12 / VG1-VG4 | Aucun test automatisé du rail ni du journal (dépliage imposé, direct/figé, fusion et compte, correspondance avec le catalogue) | medium | Aucun banc de test JS dans le dépôt ; la spec interdit toute nouvelle dépendance ; même trou déjà consigné pour 5b, 6, 6b, 6c, 8c. | defer |
| VG autre | Une exception dans `renderJournal` empêcherait `renderSchema` | low | Aucune exception aujourd'hui (champs conformes au catalogue) ; hypothétique. Couvert par l'entrée différée ci-dessus. | rejeté |
| EC2 | En vue figée, un nouveau tour replie le tour que l'utilisateur lisait | false | Conforme à la ligne « Nouveau tour » de la matrice figée (« Le précédent se replie à son en-tête ; un clic le rouvre »). | rejeté |
| EC4 | Infobulle d'un serveur indisponible avec séparateur doublé « · · » | low | `note` commence déjà par « · », puis l'infobulle joint par `" · "`. Correctif direct. | patch |
| EC5 | Appel coupé (`length`) ou arrêté (`cancelled`) : rien sur la ligne repliée | low | Le badge n'est que dans le corps. Correctif direct (ajouter la raison au chiffre clé). | patch |
| EC6 | `tool_ended` `blocked` / `limit` / `overflow` affiché « erreur » | false | `tools/executor.py:138` n'émet que `ok` ou `error`. | rejeté |
| EC8 | Après rechargement, du texte brut s'affiche déplié | false | La ligne « Lancement » de la matrice vise l'état sans tour ; après des tours, l'étape courante et les lignes imposées dépliées le sont par la spec. | rejeté |

