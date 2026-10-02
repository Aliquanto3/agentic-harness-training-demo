---
title: "E2E : schéma, rail, volets, comparaison, cas d'erreur et stabilité"
type: 'chore'
created: '2026-10-01'
status: 'in-progress'
route: 'dispatch'
baseline_commit: 'f36cc98848163cca19eccb66e4b3d6ba0db25cc5'
review_loop_iteration: 0
followup_review_recommended: false
context:
  - '{project-root}/_bmad-output/specs/spec-restes-differes-2026-10/SPEC.md'
  - '{project-root}/tools/e2e/README.md'
warnings: []
deferred:
  - 'Huit types du catalogue sans libellé dans main.log.kinds (fr, en, de) : consumption_updated, context_reconciled, context_window_state, rag_lab_* (deferred-work.md).'
  - 'Huit types sans résumé dans eventSummary : context_reconciled, context_window_state, language_changed, rag_lab_* (deferred-work.md).'
---

<frozen-after-approval reason="human-owned intent — do not modify unless human renegotiates">

## Intent

**Problem:** Le schéma (pose du robot, activité, bacs), le rail d'Orchestration, le redimensionnement des volets, la paire comparée par défaut et deux cas d'erreur (reranker, coût « ≈ ») n'ont aucun contrôle ; `gemini_shape` échoue une fois sur deux sur l'empreinte GreenOps, et le contrôle `aria-expanded` des actions forcées ne protège pas le correctif du lot K (CAP-5).

**Approach:** Contrôles E2E par le DOM, ou par `page.evaluate` sur les fonctions globales d'`app.js` (`robotPose`, `turnRows`, `syncLogGroups`, `moveBoundary`, `loadPaneLayout`) ; doublures d'erreur dans `tools/e2e` ; attente d'un état au lieu d'un délai pour `gemini_shape`.

## Boundaries & Constraints

**Always:**
- Entrées fermées (`closed: <date> (story 6 des restes différés) — <scénario, contrôle>`) :
  - **E020** — `robotPose()` change selon l'état du tour ; la clé de mémorisation de `renderSchema()` inclut la pose (le robot bouge entre deux rendus).
  - **E031** — rail d'Orchestration : lignes dépliées qui le restent, direct et vue figée, « Suivre le direct », repli du tour précédent, fusion des `model_delta` et compte du journal ; chaque `kind` du catalogue (`trace/catalog.py`) a son libellé dans `KIND_LABELS` et un résumé `eventSummary`.
  - **E032** — `schemaActivity` (halo, chemin, ✋ H5, ✖ blocage), `component` gardé sur les étapes `tool` et `hook`, bacs par `kind` et `hosting`, états « désactivé » et « ✖ a bloqué » de la bande des hooks ; et l'assertion pytest `tool_started.component == "tools.<nom>"` dans `tests/test_tools.py`.
  - **E033** — `moveBoundary` (bornes minimales, seuls les voisins changent, sens de la hauteur du schéma), `resetBoundary`, `loadPaneLayout` sur un stockage corrompu et cinq volets masqués, `savePaneLayout` à chaque masquage.
  - **E042** — paire comparée par défaut de « Comparer » (tour rejoué contre son origine).
  - **E094** — échec simulé du téléchargement du reranker (notice sous l'interrupteur) et étape « Reranking » en erreur dans le rail.
  - **E125** — `aria-expanded` lu juste après le clic, avant toute reconstruction du panneau ; la tranche passe aussi sous Edge (`channel="msedge"`) si Edge est installé, sinon le noter.
  - **E135** — faux fournisseur tarifé sans `usage` (sans `stream_usage`) : « ≈ » devant le coût sur la ligne de l'appel, l'en-tête du tour et la barre haute.
  - **E141** — `_footprint_line` attend que l'empreinte soit rendue dans le corps de l'étape « Appelle le modèle » (événement ou état du DOM), sans délai fixe ; `gemini_shape` passe cinq fois de suite dans sa tranche.
- Doublures d'erreur dans `tools/e2e/` (faux fournisseur, faux échec de téléchargement), jamais dans `src/`.
- Chaque contrôle échoue si l'on retire la ligne qu'il protège (constaté une fois à la main).

**Never:**
- Banc de test JS ou dépendance nouvelle.
- Allonger un délai pour faire passer `gemini_shape`.
- Changer le comportement de l'interface ; un défaut trouvé est noté dans `deferred` et `deferred-work.md`.

</frozen-after-approval>

## Code Map

- `tools/e2e/run_e2e.py` -- fichier principal. Helpers à réutiliser : `Run.check` (paramètre `known=` : anomalie déjà décrite, signalée `KNOWN` sans faire échouer), `Run.poll`, `Run.send`/`replay`, `Run.set_option`, `Run.open_options` (story 5 : reclique si la liste se replie), `Run.show_forced`, `Run.api`, `_step`, `_unfold_step`, `_pick_model`, `_ui_catalogue(lang)`, `A_LABEL`. Scénarios touchés : `native_tools` (rail, journal, robot, halo), `system_prompt` (rejeu, « Comparer »), `h5` (✋, bacs, H5 « désactivé »), `hooks` (✖), `data_flows` (bacs MCP), `subagent` (`aria-expanded`), `rag_rerank` (joué après `rag`), `gemini_shape` (`_footprint_line`) ; scénarios nouveaux `panes` et `priced_estimate` (après `gemini_shape`) dans `SCENARIOS`. `main()` : option `--channel` (Edge).
- `src/wavestack/web/static/app.js` (module ES : aucune fonction globale, donc lecture par le DOM, `localStorage`, le clavier et `page.evaluate` sur les nœuds) -- lignes protégées :
  - E020 : `robotPose` (6723), `robotKey` = `[pose, subPose, model]` dans `renderSchema` (6916).
  - E031 : `toggleStep` (`o.live = false`, 5809-5814), `renderSteps` (`o.turnOpen.clear()` d'un nouveau tour en direct 5918, `unfolded` 6000), `followLive` (5886), `syncLogGroups` (fusion des `model_delta`, 6562), `logRow` (`KIND_LABELS[group.kind]`, 6606), `eventSummary` (6387), `renderJournal` (titre « Journal des événements ({count}) », 6638).
  - E032 : `schemaActivity` (6800), `drawSchemaWires` (marqueurs ✖ `is-block`, ✋ `is-stop`, `.arch-path`, 7289-7320), `component: envelope.component` des étapes `tool` (505) et `hook` (592), `stepLinks` (5179), `schemaColumns` (filtre `hosting`, 7124), `hookStrip` (`is-off`, `is-blocked`, « · désactivé », « · ✖ a bloqué », 7096-7103).
  - E033 : `hidePane` (`savePaneLayout`, 884), `moveBoundary` (6219), `resetBoundary` (6238), `loadPaneLayout` (6281), poignées `.pane-resize-handle[data-handle]` (flèches ±16 px, double clic).
  - E042 : `openCompare` (paire par défaut, 4427-4428).
  - E094 : `rerankParts` (`store.rerankNotice` en `.force-error`, 1475), ligne `rerank` de `stepRows` (`tone: "error"`, `sticky`, 5342-5360).
  - E125 : `forceButton`/`cardForce` (`button.setAttribute("aria-expanded", …)` du lot K, 1704, 1725).
  - E135 : `costText` (`approx(cost.cost_source === "estimate")`, 2351), `renderConsumption` (`approx(c.approx)`, 2394).
  - E141 : `callBody` (`footprintNode`, 4638-4640).
- `tools/e2e/fake_openai.py` -- `POST /_e2e/reranker_fail` (`{"fail": bool}`) : `/_e2e/reranker.gguf` répond 503 tant que l'échec est armé.
- `tools/e2e/wavestack_e2e.py` -- faux reranker qui lève quand la question contient `[reranker-en-panne]` (sur `tests/fake_reranker.py`).
- `tools/e2e/launch_app.py` -- `read_file` de `confidentiel/outil-lent-e2e` attend 1,5 s avant de lire (outil lent pour voir halo, chemin et pose « utilise un outil »).
- `tools/e2e/stack.py` -- cinquième faux modèle `fake_m` (« Faux fournisseur M (e2e) », `faux-modele-tarife`), `stream_usage: false`, `pricing` du préréglage Mistral.
- `tests/test_tools.py` -- enveloppe `tool_started` : `component == "tools.<nom>"`, `brick == "tools"`.
- `tests/test_e2e_fake_openai.py` -- l'échec armé du fichier du reranker.
- `_bmad-output/implementation-artifacts/deferred-work.md` -- `closed:` sous E020 (l. 97), E031 (150), E032 (154), E033 (158), E042 (201), E094 (451), E125 (605), E135 (647), E141 (671) ; entrées nouvelles pour les défauts trouvés.
- `tools/e2e/README.md` -- section « Restes différés, story 6 » ; `fake_m`, `--channel`, doublures.

## Tasks & Acceptance

**Execution:**
- [x] `tools/e2e/fake_openai.py`, `tools/e2e/wavestack_e2e.py`, `tools/e2e/launch_app.py`, `tools/e2e/stack.py` -- doublures (échec du fichier du reranker, reranker en panne, outil lent, `fake_m`) -- E094, E032, E020, E135.
- [x] `tools/e2e/run_e2e.py` -- `native_tools` : quatrième tour « Lis le fichier confidentiel/outil-lent-e2e [lent] » ; un `MutationObserver` note les poses du robot (« réfléchit », « utilise un outil », « au repos »), le halo `is-active` de `tools.read_file` et `.arch-path` ; le tour 3 ouvert à la main se replie au tour 4 ; ligne courante dépliée en direct ; clic sur une ligne : vue figée, la ligne reste dépliée, les suivantes non ; « Suivre le direct » ; journal : `× N` = nombre de `model_delta` de l'appel, compte du titre = événements reçus, libellé et résumé de chaque ligne, catalogue complet en `fr`/`en`/`de` -- E020, E031, E032.
- [x] `tools/e2e/run_e2e.py` -- `h5` : ✋ et halo de `hooks.h5` pendant l'attente, bacs « Outils » et « Outils réseau » ; H5 « désactivé » après « ne plus demander » ; `hooks` : ✖ pendant le tour lent, « ✖ a bloqué » après, lien `hooks.h1` ; `data_flows` : serveur local et data.gouv.fr dans leurs zones -- E032.
- [x] `tools/e2e/run_e2e.py` -- scénario `panes` : flèches sur les poignées, bornes, voisins seuls, hauteur du schéma, double clic, masquage mémorisé, stockage corrompu et cinq volets masqués -- E033.
- [x] `tools/e2e/run_e2e.py` -- `system_prompt` : tour après le rejeu, « Comparer » sur l'origine et le rejeu -- E042 ; `rag_rerank` : échec du téléchargement puis réussite, tour `[reranker-en-panne]` -- E094 ; `subagent` : `aria-expanded` lu dans le même `evaluate` que le clic -- E125 ; `priced_estimate` -- E135 ; `_footprint_line` -- E141.
- [x] `tests/test_tools.py`, `tests/test_e2e_fake_openai.py` -- assertions pytest.
- [x] `deferred-work.md`, `tools/e2e/README.md` -- fermetures, défauts, documentation.

**Acceptance Criteria:**
- Given la pile E2E sur le faux modèle, when les tranches couvrant `native_tools`, `system_prompt`, `h5`, `hooks`, `data_flows`, `panes`, `rag rag_rerank`, `subagent`, `gemini_shape priced_estimate` sont jouées, then aucun contrôle n'échoue (les défauts notés passent en `KNOWN`).
- Given `gemini_shape` seul, when il est joué cinq fois de suite, then cinq passages sans échec.
- Given une ligne d'`app.js` du Code Map retirée à la main, when le scénario qui la protège est rejoué, then au moins un contrôle ajouté échoue ; la ligne remise, il passe.
- Given la tranche `subagent` avec `--channel msedge`, then 0 échec (ou l'absence d'Edge notée).

## Design Notes

- `app.js` est chargé en module : `robotPose`, `turnRows`, `moveBoundary`, `loadPaneLayout` ne sont pas joignables par `page.evaluate`. Les contrôles passent par ce que ces fonctions produisent : `aria-label` du robot, classes et `aria-expanded` du rail, lignes du journal, tailles des volets après les flèches, `localStorage["wavestack.panes"]`.
- Pose et halo ne durent qu'un instant avec le faux modèle : l'outil lent (doublure) et `[lent]` les rendent observables ; un `MutationObserver` posé avant l'envoi note chaque état, sans délai fixe.
- `_footprint_line` : l'échec intermittent vient du dépliage. `Run.send` rend la main au `turn_ended` du flux Python ; la page peut ne pas l'avoir rendu. L'étape « Appelle le modèle » encore courante est dépliée par le direct, `_unfold_step` ne clique pas, puis le direct la replie. Correctif : attendre que l'en-tête du tour soit rendu terminé, déplier, puis attendre `.footprint`, en recliquant si la ligne se replie.
- E125 : `b.click(); return b.getAttribute("aria-expanded")` dans un seul `evaluate` lit le bouton cliqué avant le rendu de la frame suivante ; sans la ligne du lot K, il vaut encore `false`.
- Défauts connus à l'écriture : libellés absents de `main.log.kinds` (`context_reconciled`, `context_window_state`, `consumption_updated`, `rag_lab_*`), cas absents d'`eventSummary` (`context_reconciled`, `context_window_state`, `language_changed`, `rag_lab_*`) : contrôles `known=`, entrées nouvelles dans `deferred-work.md`.

## Verification

**Commands:**
- `uv run ruff check tools/e2e tests/test_tools.py tests/test_e2e_fake_openai.py` -- expected: aucun écart.
- `uv run ruff format --check tools/e2e tests/test_tools.py tests/test_e2e_fake_openai.py` -- expected: aucun écart.
- `uv run pytest -q tests/test_tools.py tests/test_e2e_fake_openai.py` -- expected: tout passe.
- `MSYS_NO_PATHCONV=1 uv run --with playwright==1.56.0 python tools/e2e/run_e2e.py --only native_tools system_prompt h5 hooks` -- expected: 0 échec.
- `… --only data_flows panes subagent` ; `… --only rag rag_rerank` ; `… --only gemini_shape priced_estimate` ; `… --only gemini_shape` (cinq fois) ; `… --only subagent --channel msedge` -- expected: 0 échec.

## Implementation Notes

- Implémenté directement par l'agent de la story (mode nuit) plutôt que par un sous-agent : l'investigation était faite et l'E2E ne se joue qu'une tranche à la fois.
- Fichiers : `tools/e2e/run_e2e.py` (`_turn_group`, `_turn_rendered_ended`, `_slow_tool_turn`, `_event_log`, `_log_catalog`, `_schema_bins`, `_schema_h5_pending`, `_schema_blocked_while_running`, `_hook_strip_state`, `s_panes`, `_default_compare_pair`, `_rerank_download_fails`, `_rerank_step_failed`, `s_priced_estimate`, `_footprint_line` réécrit, option `--channel`), `tools/e2e/fake_openai.py` (`/_e2e/reranker_fail`), `tools/e2e/wavestack_e2e.py` (`_E2EReranker`), `tools/e2e/launch_app.py` (`read_file` lent), `tools/e2e/stack.py` (`fake_m`, `preset()`), `tools/e2e/README.md`, `tests/test_tools.py`, `tests/test_e2e_fake_openai.py`, `deferred-work.md` (neuf `closed:`, deux entrées nouvelles). `app.js` inchangé.
- Défauts trouvés, notés sans correctif (la story ne change pas l'interface) : huit types du catalogue sans libellé dans `main.log.kinds` (fr, en, de) et huit sans résumé dans `eventSummary` ; contrôles `KNOWN [deferred-work : libellés du journal]` et `KNOWN [deferred-work : résumés du journal]`.
- Surprise : `s_hooks` vérifiait la ligne H1 par `[data-links~="hooks.h1"]` ; une seconde étape du tour porte aussi ce lien, et la mutation du `component` des étapes `hook` passait. Le contrôle lit désormais l'étape « Hook H1 » seule.
- Surprise : sans bornes dans `moveBoundary`, le CSS (`--pane-min-width`) tient encore la Vue humain à 240 px ; le contrôle ajoute un → qui doit la rendre aussitôt à 256 px.
- `_log_catalog` lit l'`app.js` servi, en CRLF sur une copie Windows : normalisé avant de chercher la fin d'`eventSummary`.
- Le premier tour de `hooks` porte « [lent] » : la suite du tour après le blocage dure assez pour lire le ✖ ; la capture 14 change de message (restaurée, non commitée).

### Auto Run Result

Mutations faites à la main dans `app.js` (script local `mutate.py`, ancres uniques), rejouées, puis défaites par `git checkout` ; chaque contrôle visé a échoué :

| Entrée | Ligne retirée ou neutralisée | Contrôle en échec |
|---|---|---|
| E020 | `pose` hors de `robotKey` | poses « au repos → réfléchit », jamais « utilise un outil » |
| E032 | `component: envelope.component` de l'étape `tool` | halo (`allumés []`, `chemins 0`) et lien `tools.read_file` de l'étape |
| E032 | `component` de l'étape `hook` | « l'étape « Hook H1 » … hooks.h1 » (`core.harness`) |
| E032 | branche `pending` de `schemaActivity` | « H5 attend … ✋ » (marqueur vide) |
| E032 | branche `block` de `schemaActivity` | « H1 a bloqué … ✖ » |
| E032 | filtre `hosting` de `schemaColumns` | bacs `h5` et `data_flows` (nœuds réseau dans la zone du poste) |
| E032 | `classList.toggle("is-off")`, `isBlocked` | bande : H5 « désactivé », H1 « ✖ a bloqué » |
| E031 | `o.turnOpen.clear()` d'un nouveau tour | « le nouveau tour replie le précédent » (`true`) |
| E031 | `o.live = false` de `toggleStep` | « un clic fige la vue », puis exception sur « Suivre le direct » absent |
| E031 | `o.live = true` de `followLive` | « Suivre le direct » (dernière ligne repliée) |
| E031 | fusion de `syncLogGroups` | « Morceaux de réponse × N » (aucune fusion) |
| E031 | `KIND_LABELS[group.kind] \|\|` | « chaque ligne dit son type par son libellé » |
| E031 | `case "tool_started"` d'`eventSummary` | « chaque ligne résume », « chaque type a un résumé » |
| E031 | compte du titre → nombre de groupes | « le titre compte les événements reçus » (0) |
| E033 | bornes de `moveBoundary` | minimum 240 px (0 puis 15,9) |
| E033 | sens de `paneSizes.schema` | « ↓ … le schéma perd 16 px » (250 → 628) |
| E033 | `savePaneLayout` de `resetBoundary`, de `hidePane` | double clic (tailles gardées), masquage (non inscrit) |
| E033 | garde des cinq volets, `return` du `catch` | « cinq volets masqués … refusés », « stockage illisible » |
| E042 | paire par défaut d'`openCompare` | paire `('t2', 't3')` au lieu de `('t1', 't2')` |
| E094 | notice de `rerankParts`, ton `error` de la ligne `rerank` | notice vide ; étape sans `tone-error` |
| E125 | `setAttribute("aria-expanded")` de `cardForce` | « au clic : false · après : true » |
| E135 | `approx` de `costText`, de `renderConsumption` | trois contrôles « ≈ » |
| E141 | `if (footprint) nodes.push(footprint)` | empreinte absente du corps de l'appel |
| E032 (pytest) | `component=spec.component` de `_run_tool` | `test_tool_started_names_the_tool_component_for_the_schema` |

Tranches propres (faux modèle, réseau coupé, une à la fois, `diagnostic` compris) : `native_tools system_prompt h5 hooks` 94 réussies, 1 échec (`substring not found` sur l'`app.js` servi en CRLF, corrigé) ; `native_tools data_flows panes subagent` 114 réussies, 0 échec, 2 `KNOWN` ; `rag rag_rerank gemini_shape priced_estimate` 103 réussies, 0 échec ; `gemini_shape` seul cinq fois de suite : 41 réussies, 0 échec à chaque passage ; `model_switch reasoning_locked local_server model_catalog context_window` (non-régression de `fake_m`) 165 réussies, 0 échec ; `annex_language llm_screen relaunch hooks panes` 95 réussies, 0 échec ; `subagent --channel msedge` (Edge 154.0.4258.37) 47 réussies, 0 échec. Pytest : `tests/test_tools.py tests/test_e2e_fake_openai.py tests/test_e2e_stack.py` 77 réussis.

## Spec Change Log

- 2026-10-01 -- validé en mode nuit (Anaël absent, autorisation du 01/10 au soir) : point d'arrêt 1 de bmad-build, « Approve and continue » ; la spec respecte CAP-5, la contrainte « pas de banc JS » et le triage (E020, E031, E032, E033, E042, E094, E125, E135, E141). Bloc d'intention repris tel quel du brouillon ; l'approche « `page.evaluate` sur les fonctions globales » est inapplicable (module ES) et remplacée par la lecture de ce qu'elles produisent (Design Notes). Spec d'environ 3 600 tokens, sous le seuil de 4 000 du projet : pas de découpage.

## Review Triage Log
