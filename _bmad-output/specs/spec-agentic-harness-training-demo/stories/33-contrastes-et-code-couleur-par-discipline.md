---
title: 'Contrastes et code couleur par discipline'
type: 'feature'
created: '2026-09-28'
status: 'done'
baseline_revision: 'c1f171ecc7299336b8e087cb5d09fbb548f77f9e'
review_loop_iteration: 0
followup_review_recommended: false
context:
  - '{project-root}/CLAUDE.md'
  - '{project-root}/_bmad-output/planning-artifacts/ux-designs/maquette-refonte-2026-09-28.html'
  - '{project-root}/_bmad-output/planning-artifacts/ux-designs/ux-agentic-harness-training-demo-2026-09-22/DESIGN.md'
  - '{project-root}/_bmad-output/planning-artifacts/ux-designs/ux-agentic-harness-training-demo-2026-09-22/EXPERIENCE.md'
  - '{project-root}/_bmad-output/specs/spec-agentic-harness-training-demo/stories/22-retours-de-recette-briques-volets-et-tiroirs.md'
  - '{project-root}/tools/e2e/README.md'
warnings:
  - oversized
deferred:
  - summary: >-
      Contrastes testés sur des paires de la note de design, pas sur toutes les paires dessinées (pastille de débordement blanc sur danger 3,7:1, trait de carte éteinte 2,95:1).
    evidence: |-
      test_web_tokens vérifie des couples abstraits ; --on-discipline défini mais non lu.
    severity: low
  - summary: >-
      Le violet porte à la fois la marque, le prompt engineering, le cadre du harnais et les sélections.
    evidence: |-
      .arch-harness, soulignement d'onglet et fond d'étape sélectionnée restent en primary ; primary-soft et discipline-prompt-soft quasi identiques.
    severity: low
  - summary: >-
      Disciplines et by_brick non testés en pytest sur context_preview et context_reconciled.
    evidence: |-
      Seul context_rendered local est couvert en pytest ; le chemin chat l'est par l'E2E.
    severity: low
  - summary: >-
      La garde « aucune couleur en dur » ne voit pas les couleurs nommées, color-mix(, oklch( ni les attributs SVG en JS.
    evidence: |-
      Regex _HARD_COLOR limitée à #hex, rgb(, hsl(.
    severity: low
---

<intent-contract>

## Intent

**Problem:** L'interface est claire partout, avec le même violet pour la marque, le « local » et la brique active. Rien ne ressort, et rien ne dit si un élément relève du prompt, du contexte, du harnais ou du réseau. La maquette de refonte validée le 2026-09-28 fixe des fonds foncés pour les éléments clés et un code couleur par discipline. Elle regroupe aussi les briques selon ce que le modèle lit et ce que le harnais fait.

**Approach:** Ajouter des jetons de discipline (prompt, context, harness, réseau, neutre) et des jetons « sur encre » à DESIGN.md et `tokens.css`. La session porte ce que l'interface ne doit pas calculer (AD-1) : le groupe de chaque brique, la discipline de chaque segment et de chaque groupe de la jauge, et les tokens par brique. L'interface applique ces couleurs dans les cinq volets et dans la barre haute. Elle n'en change pas la structure : volets masquables et redimensionnables (8f), journal.

## Boundaries & Constraints

**Always:**
- `uv`, `ruff` et `pytest` (CLAUDE.md). Code et identifiants en anglais, textes d'interface en français.
- Chaque couleur passe par une variable de `tokens.css`. Chaque jeton figure dans le frontmatter de DESIGN.md, avec la même valeur (`tests/test_web_tokens.py`). Aucune couleur écrite en dur dans `app.css` ni dans `app.js`, pour que la story 31 n'ait qu'à redéfinir les jetons.
- Contrastes WCAG AA : 4,5:1 pour le texte et 3:1 pour les traits porteurs de sens. Le jaune réseau n'est jamais seul : il est toujours doublé du libellé « RÉSEAU » ou du globe.
- AD-1 : aucune somme de tokens, discipline ou disponibilité calculée dans le navigateur. Compter les éléments d'une liste reçue (entrées, options, nœuds) et faire l'écart entre deux valeurs reçues restent permis.
- Le premier groupe du panneau s'ouvre sur Raisonnement (story 22). Les identifiants `t{n}`, les événements existants et l'API HTTP ne changent pas. Seuls s'ajoutent des champs optionnels.
- Mettre à jour DESIGN.md (frontmatter et prose), EXPERIENCE.md et la spine (AD-9, AD-12). Ajouter les vérifications au parcours E2E et mettre à jour les captures.

**Never:**
- Aucune dépendance nouvelle et aucun appel à Google Fonts. La police reste Atkinson Hyperlegible, déjà servie depuis `static/fonts`.
- Aucun vrai modèle dans le conteneur. On utilise les doublures du dépôt : faux moteur, faux serveurs `tools/e2e`, GGUF synthétiques, faux fournisseurs.
- Hors périmètre :
  - vue liée au survol, volets numérotés, frise H/M/R, bilan des sorties et mode projection (story 34) ;
  - palette sombre (story 31) ;
  - lecture groupée du contexte (story 32) ;
  - `diagnostic.html`.
- Ne reprendre de la maquette ni sa grille ni sa structure : seulement ses choix visuels.

## I/O & Edge-Case Matrix

| Scenario | Input / State | Expected Output / Behavior | Error Handling |
|----------|--------------|---------------------------|----------------|
| Segment d'une brique | Segment `brick: "system_prompt"` | `discipline: "prompt"` dans le segment et dans son groupe de `breakdown` | — |
| Segment sans brique | Gabarit, message de l'utilisateur | `discipline: "neutral"` | — |
| Brique inconnue du registre | `brick` absent de la table des catégories | `"neutral"` | Pas d'exception |
| Tokens par brique | Trois segments `system_prompt` (10, 5) et `tools` (40), plus un gabarit | `by_brick = [{system_prompt, 15}, {tools, 40}]` dans l'ordre d'apparition, sans le gabarit | — |
| Mode chat | Segments estimés | `by_brick[i].estimated = true` : la carte affiche « ≈ » | Après `context_reconciled`, valeurs réconciliées |
| Brique éteinte | `wanted:false` | Carte grisée (`discipline-neutral-soft`, trait neutre), ligne d'état « Éteinte » | — |
| Modèle qui raisonne toujours | `always_fr` non vide | Carte Raisonnement active, interrupteur verrouillé avec 🔒, ligne « Imposé par ce modèle » | — |
| Aucun tour encore | Seul le `context_preview` existe | Les lignes d'état lisent l'aperçu ; sans aperçu, « En attente du modèle » | — |

</intent-contract>

## Code Map

- `src/wavestack/bricks/contract.py:12-30` -- `Category` et `BrickDeclaration` : y ajouter `group: Literal["reads", "acts"]`.
- `src/wavestack/bricks/registry.py:33-228` -- `BRICKS`, dont l'ordre sert d'ordre d'affichage (story 22). L'ordre actuel est reasoning, short_memory, system_prompt, global_memory, tools, mcp, skills, hooks, subagent, rag, compression. Catégories : reasoning et system_prompt en prompt ; short_memory, global_memory, skills, rag et compression en context ; tools, mcp, hooks et subagent en harness.
- `src/wavestack/session/app_session.py:1227-1290` -- `_emit_bricks` : ajouter `"group"`. Lignes 3123-3130 et 3176-3190 : les deux appels de `gauge()` (local et chat), qui doivent passer la table brique → catégorie tirée de `self._bricks`.
- `src/wavestack/context/window.py:18-75` -- `gauge()`, fonction unique des charges de jauge (AD-9). Elle y ajoute `discipline` par segment et par groupe, et `by_brick`.
- `src/wavestack/trace/catalog.py:157-196, 332-340` -- `SegmentPayload`, `BreakdownItem`, `ContextWindowPayload` et `BrickState`, où ajouter les champs.
- `src/wavestack/web/static/tokens.css` et le frontmatter de DESIGN.md (`colors`, `spacing.top-bar-height`) -- les jetons.
- `src/wavestack/web/static/app.js:101-115` -- `GROUP_COLORS`, couleur par type de segment, conservée pour la pastille de type.
- `app.js:828-940` -- `renderBricks`. Il n'est reconstruit que sur `bricks` / `armed` / `forceForm` / `memory` / `sessionKey`. La ligne d'état dépend de `store.gauge` et `store.architecture` : il faut la mettre à jour sur place, sans reconstruire la carte, pour garder les popovers et le focus. `app.js:1110-1125` : les lignes d'option ont déjà `hosting-tag-network`.
- `app.js:1575-1600` -- `memoryCardParts`, qui porte déjà le nombre d'entrées.
- `app.js:1789-1830` -- `renderGauge` : segments, figures et infobulle. `index.html:15-20` pour la jauge.
- `app.js:2143` -- bulle `bubble-user`. `app.js:2590-2620` -- `appendSegments` (filet `--segment-color` et `.swatch`). `app.js:2733-2745` -- `compareCell`.
- `app.js:3389-3640` -- `turnRows` : chaque ligne porte `actor` et `net`, et l'étape `step.brick` quand elle l'a. `app.js:3808-3880` -- `stepNode`, où `.turn-step-tile` est la pastille.
- `app.js:4791-4830` -- `robot()`. `app.js:4955-5040` -- `buildSchema` : puces `arch-chip`, `arch-cloud-model`, `arch-server-model`. `app.js:5091-5125` -- `schemaNode`, qui connaît `node.hosting`, avec la brique en `node.id.split(".")[0]`. `hookStrip` pour les hooks.
- `src/wavestack/web/static/app.css` -- `.top-bar` (98), `.pane-header` (377), `.gauge*` (444-500), `.bubble-user` (528), `.ctx-segment` (636), `.turn-step-tile` (1129), `.brick-card` (1508, 1578-1591), `.brick-toggle:checked` (1630), `.robot` (2375), `.arch-node*` (2583-2700), `.arch-cloud-model` et `.arch-server-model` (2954-2970).
- `tools/e2e/run_e2e.py` -- `Run.shot` (120), `_CSS_COLOR_JS` (1555), `s_network_tools` (670), `s_model_switch` (2599), `SCENARIOS` (2986). `tools/e2e/stack.py:57-120` -- `_entry` et `settings()`, qui déclarent deux faux modèles cloud.
- `tests/test_bricks.py:444-470` (ordre, story 22), `tests/test_turn.py:234-246` (`gauge()`), `tests/test_web_tokens.py`.

## Tasks & Acceptance

**Execution:**
- `src/wavestack/bricks/contract.py`, `registry.py` -- Ajouter `group` et réordonner `BRICKS` : reasoning, system_prompt, short_memory, global_memory, rag (`reads`), puis tools, mcp, skills, hooks, subagent, compression (`acts`). Les catégories ne changent pas. La story demande ces deux groupes, et l'ordre de la liste reste l'ordre d'affichage.
- `src/wavestack/trace/catalog.py`, `context/window.py`, `session/app_session.py` -- Ajouter `BrickState.group`. Ajouter `discipline` (`prompt|context|harness|neutral`, `"neutral"` par défaut) à `SegmentPayload` et `BreakdownItem`, et `by_brick: [{brick, tokens, estimated}]` à `ContextWindowPayload`. `gauge()` reçoit `categories: Mapping[str, str] = {}` ; la discipline d'un groupe est celle de son premier segment. `_emit_bricks` émet `group`. AD-1 : ces valeurs viennent de la session.
- `tests/test_bricks.py`, `tests/test_turn.py` -- Couvrir l'ordre exact et les groupes des cartes, ainsi que les cas de la matrice : discipline par segment et par groupe, brique inconnue, `by_brick` et son ordre, `estimated`.
- `DESIGN.md` (frontmatter et prose) puis `src/wavestack/web/static/tokens.css` -- Ajouter les jetons de la note de conception et passer `top-bar-height` à 56px. Réécrire Colors (« violet = marque et prompt engineering », le lieu d'hébergement porté par les zones du schéma et le libellé RÉSEAU, jaune = sort du poste), le tableau des disciplines avec leurs contrastes, et les composants `top-bar`, `pane`, `brick-card`, `context-gauge`, `context-segment`, `turn-step`, `arch-node-*`, la bulle utilisateur et le nœud du modèle. Retirer la phrase « Thème clair uniquement… Pas de tokens sombres » au profit de « jetons prêts pour un second thème (story 31) ».
- `tests/test_web_tokens.py` -- Ajouter un test des contrastes, avec un calcul WCAG en Python pur, sur les paires de la note de conception. Ajouter un test qui interdit `#hex`, `rgb(` et `hsl(` dans `app.css` et `app.js`, commentaires exclus. Ces deux tests verrouillent l'AA et la préparation de la story 31.
- `src/wavestack/web/static/index.html`, `app.css`, `app.js` (barre haute et volets) -- Donner à la barre haute le fond `ink`, avec titre, figures et statut en `on-ink` et un anneau de focus `on-ink`. La jauge garde une piste claire (`surface-raised`) : segments colorés par `item.discipline`, séparés d'un filet de 1 px, avec en infobulle « {label_fr} : n tokens · {discipline} ». Sous la barre, une légende `#gauge-legend` : une pastille bordée `on-ink-soft` et le nom par discipline présente, dans l'ordre prompt, context, harness, puis « Message et gabarit » ; le total reste dans `#gauge-figures`. `.pane-header` prend le fond `surface` (bandeau), et `.bubble-user` le fond `ink` avec le texte `on-ink`.
- `app.js`, `app.css` (panneau des briques) -- En tête du panneau, la légende des quatre disciplines (« Prompt engineering », « Context engineering », « Harness engineering », « Sort du poste de travail »). Deux sections selon `brick.group` : « Ce que le modèle lit » et « Ce que le harnais fait ». Chaque carte porte `data-discipline=category`. Carte active : trait gauche de 5 px et fond teinté de sa discipline, interrupteur coché de cette couleur. Carte éteinte : grisée, fond et trait neutres, texte `ink-soft`. Une puce « 🌐 RÉSEAU » s'affiche si une option activée a `network: true`. La ligne d'état `p.brick-status[data-brick]` est mise à jour sur place à chaque rendu (voir la note). Un modèle qui raisonne toujours affiche 🔒 à côté de l'interrupteur verrouillé.
- `app.js`, `app.css` (Contexte LLM, Orchestration, schéma) --
  - `appendSegments` et `compareCell` : le filet et le fond du segment prennent sa discipline (`data-discipline`), la `.swatch` garde `GROUP_COLORS` pour que le type de segment reste lisible.
  - Chaque ligne de `turnRows` reçoit `discipline` : `model` (tuile `ink`, icône `on-ink`) pour les appels, demandes d'outil et réponses finales ; `network` si `row.net` est présent ; sinon la catégorie de la brique de l'étape (lue dans `store.bricks`) ; `harness` par défaut. La tuile porte `data-discipline`.
  - Schéma : un nœud `network` porte la discipline réseau, un nœud `{brick}.*` la catégorie de sa brique, et `file.*` le neutre. Les puces `arch-chip` et les hooks prennent la couleur de leur brique. Le robot, ou la boîte du modèle cloud ou servi, repose sur une plaque `ink` avec son libellé en `on-ink`.
- `EXPERIENCE.md` -- Mettre à jour la barre haute (l. 119), la jauge (124 : couleur par discipline, légende), la carte de brique (130 : groupes, nouvel ordre, ligne d'état, carte éteinte grisée, 🔒), le rail d'étapes (141 : couleur de la tuile), le segment de contexte (144) et le schéma (151). Ajouter une section « Code couleur par discipline ».
- `ARCHITECTURE-SPINE.md` -- AD-12 : ajouter « groupe du panneau (`reads`, `acts`) » à la déclaration. AD-9 : ajouter `discipline` par segment et par groupe, et `by_brick`, calculés par la session.
- `tools/e2e/stack.py`, `tools/e2e/run_e2e.py`, `tools/e2e/README.md` --
  - Ajouter une troisième entrée cloud factice, `reasoning: {format: "field", always: true}`.
  - Nouveau scénario `s_disciplines`, placé après `network_tools`, qui fait les vérifications ci-dessous.
  - Nouveau scénario `s_reasoning_locked`, placé après `model_switch` : il bascule sur l'entrée qui raisonne, vérifie la carte, puis revient à l'entrée A.
  - Ajouter `Run.shot_element(name, selector)`. Captures `28-disciplines-barre-haute`, `29-disciplines-briques`, `30-disciplines-vue-humain`, `31-disciplines-contexte`, `32-disciplines-orchestration`, `33-disciplines-schema`, `34-raisonnement-impose`. Réécrire les captures existantes et mettre la liste du README à jour.

**Acceptance Criteria:**
- Given le scénario `network_tools` et un tour « Résume l'article Wikipédia… », when on lit la barre haute, then son fond calculé vaut `--color-ink`, `#gauge-legend` contient « Prompt engineering », « Context engineering » et « Harness engineering », chaque `.gauge-seg` a un `data-discipline` et le fond du jeton correspondant, et `#gauge-figures` correspond à `/\d[\d  ]* \/ \d[\d  ]* tokens · [\d,]+ %/`. Légende et figures sont entièrement visibles à 1600 × 1000.
- Given le même état, when on lit le panneau des briques, then la légende montre les quatre disciplines. Les titres « Ce que le modèle lit » puis « Ce que le harnais fait » apparaissent dans cet ordre. Le premier groupe contient exactement Raisonnement, Prompt système, Mémoire courte, Mémoire globale et RAG, Raisonnement en premier. La carte Prompt système a un `border-left-color` égal à `--color-discipline-prompt`, et la carte RAG, éteinte, un fond égal à `--color-discipline-neutral-soft`.
- Given le même état, when on lit les lignes d'état, then celle de Prompt système correspond à `/\d+ tokens? dans le contexte/`, celle de Mémoire globale à `/\d+ entrées? · \d+ tokens?/`, et celle d'Outils à `/\d+ déclarés · 1 contacté/`, avec la puce « RÉSEAU » sur la carte. Après l'extinction de Prompt système, sa ligne dit « Éteinte » sans que la carte ait perdu une explication ouverte.
- Given le même tour, when on lit la Vue humain, then la dernière `.bubble-user` a le fond `--color-ink` et le texte `--color-on-ink`. Chaque `.pane-header` des cinq volets a le fond `--color-surface`.
- Given le même tour, when on lit Contexte LLM, then chaque `.ctx-segment` a un `data-discipline`. Le segment du prompt système a le filet `--color-discipline-prompt` et sa `.swatch` garde `--color-segment-system-prompt`.
- Given le même tour, when on lit Orchestration, then la tuile de l'appel au modèle a le fond `--color-ink`, celle de l'exécution de `wikipedia_summary` a `data-discipline="network"`, et celle de « Description des outils » `data-discipline="harness"`.
- Given le même tour, when on lit le schéma, then la plaque du modèle a le fond `--color-ink`, le nœud Wikipédia `data-discipline="network"` et le nœud Calculatrice `data-discipline="harness"`.
- Given l'entrée factice qui raisonne toujours, activée depuis le sélecteur, when on lit la carte Raisonnement, then son interrupteur est coché et désactivé, 🔒 est visible et la ligne d'état dit « Imposé par ce modèle ». Revenu à l'entrée A, la carte redevient réglable.

## Spec Change Log

## Review Triage Log

### 2026-09-28 — Review pass
- verdicts: 26 findings — high 0, medium 5, low 17, false 4, maybe-false 0 (l'auditeur d'intention n'a relevé que des écarts d'interprétation consignés dans les décisions par défaut)
- findings:
  - `[low]` `[patch]` (vérif.) lignes d'état passent avec « 0 token » et sans « ≈ » — égalité avec `by_brick` et « ≈ » vérifiés dans `s_disciplines`.
  - `[low]` `[patch]` (vérif.) « Gain : n tokens » de la Compression jamais vérifié — assertion ajoutée au scénario de compression.
  - `[low]` `[patch]` (vérif.) tuile d'Orchestration vérifiée seulement par le repli harness — tuile d'une étape de brique context vérifiée.
  - `[medium]` `[patch]` (blind + edge) groupe de jauge mixte coloré par une discipline arbitraire (ordre des types) — discipline majoritaire en tokens, calculée à la création du groupe, test ajouté.
  - `[low]` `[patch]` (blind) boucle de `gauge()` refait le dictionnaire à chaque passage — regroupé avec le point précédent.
  - `[low]` `[defer]` (blind) test de contraste sur des paires non dessinées ; paires dessinées non testées (pastille de débordement 3,7:1, trait de carte éteinte 2,95:1) — à reprendre avec la story 31 qui refait la matrice des contrastes.
  - `[low]` `[defer]` (blind) le violet sert aussi au cadre du harnais et aux sélections — choix de charte, à trancher en recette.
  - `[low]` `[patch]` (blind + edge) légende neutre nommée de trois façons — un seul libellé.
  - `[low]` `[patch]` (blind + edge) textes périmés (commentaires, DESIGN.md « fond crème », swatch en prose) — alignés sur le code.
  - `[low]` `[patch]` (blind + edge) contiguïté des groupes non garantie — contrôle au registre et test.
  - `[medium]` `[patch]` (blind + edge) barre haute rigide qui déborde avec un message d'état ou des puces à 1280 px — éléments rétrécissables avec ellipse, contrôle E2E étendu.
  - `[low]` `[patch]` (blind) regex `(\d+) déclarés` échoue au singulier — `déclarés?`.
  - `[false]` `[reject]` (blind) appels à un modèle cloud non jaunes — la maquette validée garde la pastille du modèle en encre même via le réseau ; le bilan des sorties relève de la story 34.
  - `[low]` `[patch]` (blind) `s_reasoning_locked` sans `try/finally` — retour à l'entrée A garanti.
  - `[low]` `[defer]` (blind) disciplines non testées sur `context_preview` / `context_reconciled` en pytest — le chemin chat est couvert par l'E2E.
  - `[low]` `[defer]` (blind) garde anti-couleurs en dur ne voit pas les couleurs nommées ni `color-mix(` — à étendre avec la story 31.
  - `[medium]` `[patch]` (edge) contour de sélection du robot invisible sur la plaque d'encre, focus à 2,1:1 — contour et focus en `on-ink`.
  - `[low]` `[patch]` (edge) tige du robot à 1,27:1 — trait `on-ink`.
  - `[low]` `[patch]` (edge) brique indisponible et non voulue affichée « Éteinte » — « Indisponible » testé d'abord.
  - `[false]` `[reject]` (edge) critère « 1 contacté » faux en parcours complet — compte de session assumé et documenté (README E2E), l'E2E compare au compte réel.
  - `[false]` `[reject]` (edge) « la carte redevient réglable » faux sur l'entrée A — l'entrée A ne déclare pas le raisonnement : la carte n'est plus verrouillée (pas de 🔒), ce que vérifie l'E2E ; le reste est le comportement voulu des capacités.
  - `[false]` `[reject]` (edge) suppression de la règle `.arch-node-file` — voulue (plus de couleur d'hébergement) ; seule la prose de DESIGN.md était à corriger (point patché ci-dessus).
  - `[medium]` → regroupé (groupe mixte, edge).
  - `[medium]` → regroupé (barre haute, edge).
  - `[low]` → regroupé (contiguïté, edge).
  - `[low]` → regroupé (légende neutre, edge).

## Design Notes

Jetons à ajouter (clair) : `discipline-prompt #451DC7` / `-soft #EEE9FC`, `discipline-context #0F7B6C` / `#E2F3EF`, `discipline-harness #B8327A` / `#FBE7F1`, `discipline-network #D9A400` / `#FFF5D1`, `discipline-neutral #8A8A9E` / `#EFEFF4`, `on-ink #FFFFFF`, `on-ink-soft #CFCDE4`. Ce sont les valeurs de la maquette, sauf `ink` : l'encre de la charte (`#0A0A14`) reste en place.

Contrastes calculés, à verrouiller dans le test :

| Paire | Ratio | Seuil |
|---|---|---|
| `on-ink` sur `ink` | 19,7 | 4,5 |
| `on-ink-soft` sur `ink` | 12,7 | 4,5 |
| `on-ink` sur prompt | 9,3 | 4,5 |
| `on-ink` sur context | 5,2 | 4,5 |
| `on-ink` sur harness | 5,6 | 4,5 |
| `ink` sur network | 8,7 | 4,5 |
| `ink-soft` sur chaque `-soft` | ≥ 7,2 | 4,5 |
| prompt, context, harness et neutral sur `surface-raised` | ≥ 3,4 | 3 |

`discipline-network` fait 2,3:1 sur blanc : il sert toujours de fond sous un texte encre, ou de trait accompagné du libellé RÉSEAU.

Le violet sur `ink` fait 2,1:1. La jauge garde donc une piste claire dans la barre foncée, et les pastilles de la légende sont bordées.

Ligne d'état (`brick-status`), calculée seulement à partir de valeurs reçues :

| Brique allumée | Texte |
|---|---|
| reasoning | « Imposé par ce modèle » si `always_fr`, sinon « Réserve de sortie : {gauge.reserve} tokens » |
| global_memory | « {n} entrées · {tokens} tokens » |
| tools, mcp | « {options activées} déclarés · {c} contacté(s) », où c compte les nœuds `{brick}.*` réseau dont `contact` n'est ni `null` ni `not_contacted`. Sans option réseau activée : « {d} déclarés · {tokens} tokens » |
| compression | « Gain : {uncompressed_used − used} tokens », sinon « Aucun gain pour l'instant » |
| autres | « {tokens} tokens dans le contexte » (`by_brick`, « ≈ » si `estimated`, 0 si absente) |

Brique éteinte : « Éteinte ». Brique voulue mais indisponible : « Indisponible ».

## Verification

**Commands:**
- `uv run ruff check .` -- expected: aucune erreur
- `uv run ruff format --check .` -- expected: aucun fichier à reformater
- `uv run pytest -q` -- expected: tout vert, y compris les nouveaux tests de `test_bricks`, `test_turn` et `test_web_tokens`
- `uv run --with playwright==1.56.0 python tools/e2e/run_e2e.py` -- expected: aucun FAIL ; captures 28 à 34 écrites et captures existantes réécrites dans `tools/e2e/screenshots/`

**Manual checks (if no CLI):**
- Relire les captures 28 à 34 : barre haute foncée et lisible, deux groupes de briques, cartes teintées, bulle utilisateur foncée, tuiles colorées, plaque du modèle foncée.

## Décisions prises par défaut

- **Groupe du panneau** : c'est un champ de la déclaration de brique (`group`), distinct de la catégorie. Skills et compression sont en context engineering, mais la story les range dans « Ce que le harnais fait ». Une table écrite dans le JS irait contre AD-1.
- **Ordre du premier groupe** : Raisonnement, prompt système, mémoire courte, mémoire globale, RAG. C'est l'ordre du texte de la story, et Raisonnement reste en tête (story 22).
- **Discipline réseau** : elle ne s'applique qu'à ce qui sort du poste, c'est-à-dire les nœuds `hosting: network`, les étapes avec `net`, les puces RÉSEAU et la légende. Les segments et la jauge n'ont que prompt, context, harness et neutre : un résultat d'outil réseau est entré dans le contexte, il n'en sort pas.
- **Tokens par brique et discipline** : ils sont calculés par la session dans `gauge()`, qui produit toutes les charges de jauge (AD-9), plutôt que dans le navigateur (AD-1).
- **Légende de la jauge** : des noms de discipline, sans tokens par discipline, pour ne pas ajouter une somme de plus. Le total en tokens et en pourcentage reste dans les figures existantes.
- **Type de segment toujours lisible** : dans Contexte LLM, le filet porte la discipline et la pastille garde la couleur de type ; dans la jauge, un filet de 1 px sépare les groupes et l'infobulle nomme le type.
- **Valeurs de la maquette** : ses couleurs de discipline sont reprises, mais pas son encre ni ses neutres lilas. La règle de DESIGN.md sur les jetons de la charte s'applique.
- **Bandeau de volet** : il reprend `surface`, sans nouveau jeton.
- **Hauteur de la barre haute** : elle passe de 48 à 56 px pour loger la légende sous la barre.
- **Bloc de raisonnement de la Vue humain** : il n'est pas teinté, car la story ne le liste pas.
- **Couleur des nœuds** : les nœuds locaux ne sont plus violets par hébergement. Le lieu d'hébergement est porté par les zones, la frontière, le globe et le libellé RÉSEAU. DESIGN.md est corrigé en conséquence.
- **Ligne d'état** : elle n'est pas annoncée en direct (pas d'`aria-live`), pour éviter une annonce à chaque tour. Elle reste lisible au clavier dans la carte.
- **Raisonnement imposé** : on ajoute un troisième faux modèle cloud au banc E2E plutôt que de modifier les deux existants, qu'utilisent déjà `model_switch` et les scénarios suivants.

## À vérifier sur PC

- **Barre haute projetée**
  - **Geste** : dans Chrome puis Edge, lancer `uv run wavestack`, choisir « Outils réseau » dans le sélecteur de scénario, envoyer « Résume l'article Wikipédia sur le Mont-Saint-Michel. », puis projeter ou se placer à 3 m de l'écran.
  - **Attendu** : barre haute foncée, légende de la jauge lisible, total en tokens et en pourcentage.
  - **Critère** : Anaël lit la légende et le total à 3 m, à 100 % puis à 150 % de taille de texte (« Aa »), sans texte coupé.
  - **Moyen** : à la main.
- **Code couleur partout**
  - **Geste** : même tour, regarder les cinq volets.
  - **Attendu** : même couleur pour une discipline dans la carte, le segment, la tuile et le nœud ; jaune seulement pour ce qui sort du poste.
  - **Critère** : Anaël associe chaque couleur à sa discipline sans lire la légende, pour 4 éléments tirés au hasard.
  - **Moyen** : à la main (œil humain).
- **Raisonnement imposé**
  - **Geste** : avec Groq gpt-oss-120b (clé déclarée), choisir le modèle dans le sélecteur, cliquer « Charger », confirmer, puis regarder la carte Raisonnement.
  - **Attendu** : interrupteur verrouillé avec 🔒, « Imposé par ce modèle ».
  - **Critère** : l'interrupteur ne bouge pas au clic.
  - **Moyen** : Claude in Chrome ou à la main.
- **Lignes d'état avec Qwen3.5-4B (GGUF, local)**
  - **Geste** : scénario « Mémoire globale », envoyer deux prompts suggérés, puis éteindre et rallumer « Prompt système ».
  - **Attendu** : tokens exacts (sans « ≈ ») sur les cartes ; « Éteinte » puis de nouveau des tokens.
  - **Critère** : pour chaque carte, les tokens affichés égalent ceux des segments de sa brique dans Contexte LLM.
  - **Moyen** : script AppSession (lecture de `by_brick` dans `context_rendered`) et Playwright (Chromium de `%LOCALAPPDATA%\ms-playwright`) pour les cartes.
- **Contrastes réels**
  - **Geste** : dans Edge, ouvrir DevTools, aller dans Lighthouse, puis Accessibility, puis Analyze, sur l'atelier après un tour du scénario « Outils réseau ».
  - **Attendu** : aucun défaut « Contrast ».
  - **Critère** : 0 élément signalé pour le contraste.
  - **Moyen** : à la main (Lighthouse), ou Claude in Chrome.
- **Mode contrasté de Windows**
  - **Geste** : Paramètres, puis Accessibilité, puis Thèmes de contraste, choisir « Désert », puis recharger WaveStack.
  - **Attendu** : barre haute, bulles et tuiles restent lisibles ; les focus sont visibles.
  - **Critère** : tous les textes restent lisibles, et le focus clavier reste visible sur les interrupteurs et la barre haute.
  - **Moyen** : à la main.

## Auto Run Result

Statut : done (2026-09-28, orchestrateur de nuit ; étapes 1 à 4 menées par l'orchestrateur, les sous-agents ne pouvant pas en lancer d'autres).

**Changement :** reprise des choix de couleur et de contraste de la maquette dans les cinq volets existants : barre haute en encre, jauge colorée par discipline avec légende, bandeau des volets, bulle utilisateur foncée ; code couleur unique par discipline (prompt, context, harness, réseau, neutre) sur les cartes, segments, tuiles d'Orchestration et nœuds du schéma ; briques en deux groupes (« Ce que le modèle lit » / « Ce que le harnais fait ») avec ligne d'état vivante et interrupteur verrouillé quand le modèle raisonne toujours. Discipline et tokens par brique calculés par la session (AD-1).

**Fichiers :** `bricks/contract.py`, `bricks/registry.py` (groupe, ordre, contrôle de contiguïté), `context/window.py` (discipline par segment et par groupe, `by_brick`), `trace/catalog.py`, `session/app_session.py`, `web/static/{app.js,app.css,index.html,tokens.css}`, `tests/test_{bricks,turn,web_tokens}.py`, `tools/e2e/{stack.py,run_e2e.py,README.md}`, DESIGN.md, EXPERIENCE.md, ARCHITECTURE-SPINE.md, captures 28 à 34 et captures existantes réécrites.

**Revue :** 26 constats — 17 corrigés (4 medium, 13 low), 4 différés, 4 rejetés (false) ; voir le triage. Revue de suivi recommandée : false (aucun high).

**Vérification :** ruff check et format verts ; pytest : 947 passés, 3 ignorés ; E2E complet : 437 PASS, 0 FAIL.

**Risques résiduels :** tailles de texte 125/150 % non testées automatiquement (légende de la jauge dans une barre de 56 px) ; contrastes réels à confirmer par Lighthouse sur le PC ; libellé neutre raccourci en « Hors brique » pour tenir dans la barre.
