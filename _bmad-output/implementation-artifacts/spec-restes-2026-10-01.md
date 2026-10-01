---
title: 'Restes du 2026-10-01 : constats différés des stories 5 et 6, BM25 par langue, libellé allemand, statut Langues 5'
type: 'chore'
created: '2026-10-01'
status: 'in-progress'
baseline_commit: '18c39782cb78d915dfebd38e2a4f63eb925f04e9'
baseline_revision: '18c39782cb78d915dfebd38e2a4f63eb925f04e9'
route: 'dispatch'
review_loop_iteration: 0
followup_review_recommended: false
context:
  - '{project-root}/_bmad-output/specs/spec-corrections-2026-09-30/stories/5-llm-nu-pedagogique-distribution-vivante-comparaison-a-b-schemas.md'
  - '{project-root}/_bmad-output/specs/spec-corrections-2026-09-30/stories/6-atelier-mcp-mcp-le-protocole-a-manipuler.md'
  - '{project-root}/_bmad-output/specs/spec-langues/i18n-conventions.md'
warnings: ['multiple-goals']
deferred: []
---

<intent-contract>

## Intent

**Problem:** Des constats différés qui ont déjà leur spec restent ouverts : la logique de page de la distribution vivante et du schéma de fenêtre (`/llm`) n'est pilotée par aucun test ; la comparaison A/B n'a jamais été arrêtée pendant B, ni jouée avec un modèle cloud, ni arrêtée par le bouton de la page ; la page `/mcp` n'est vérifiée que côté session (hors ligne, « Occupé », « Arrêter », préréglages, champs JSON, troncature, requêtes sortantes, rejeu, note « servi non traduit ») ; l'arrêt d'un appel au glossaire local (stdio) et le refus de l'écran principal pendant un échange de l'atelier MCP ne sont pas testés ; la recherche BM25 de l'atelier RAG n'ignore que des mots vides français ; le libellé allemand `session.compression.the_compressor` est au nominatif dans une phrase qui veut l'accusatif ; la story Langues 5 est encore `in-review`.

**Approach:** Un lot, un commit par point, sur `feat/restes-2026-10-01` : tests et E2E d'abord (les défauts qu'ils révèlent sont corrigés dans le même commit), puis BM25 par langue, libellé allemand, statut, et clôture des entrées `deferred` (specs) et `deferred-work.md` avec leur preuve. Accord d'Anaël pour lancer l'E2E et le serveur MCP local : donné.

## Boundaries & Constraints

**Always:**
- Code en anglais, textes en français avec surcouches `en` et `de` (parité des clés de `tests/test_i18n.py`) ; `uv`, `ruff check` et `ruff format` sur les fichiers touchés ; `pytest` sur les fichiers touchés pendant l'itération, puis en quatre quarts au premier plan les uns après les autres ; E2E en tranches `--only` de 4 à 6 scénarios (`PYTHONUTF8=1`).
- E2E sans moteur en processus : `page.route` simule `/api/llm_lab` (candidats disponibles, `distribution.tokens`), `/api/llm_lab/distribution` (réponse calculée par la vraie fonction `wavestack.models.candidates.distribution`, même forme que `AppSession.llm_distribution`) et `/api/stream` (des `llm_token` rejoués par lots, validés par `PAYLOAD_MODELS` avant envoi). AD-1 tenu : la page ne calcule rien, le test ne fait que lui servir des valeurs.
- Aucune API cloud payante : le cloud passe par `Provider` de `tests/test_cloud.py` et par `tools/e2e/fake_openai.py`.
- Chaque entrée fermée : retirée du bloc `deferred` de sa spec avec une ligne de clôture (preuve) dans ses Implementation Notes, ou marquée `closed:` ; `closed: 2026-10-01 — <preuve>` sur l'entrée de `deferred-work.md` (créée si elle n'existe pas, avec `source_spec`).

**Never:**
- Toucher au harnais, au moteur ou à la logique de la session pour faire passer un test ; ajouter au produit un crochet propre aux tests (ex. un terme « lent » dans le glossaire).
- Pousser, ouvrir une PR, fusionner.
- Lancer deux suites de tests en même temps.

## I/O & Edge-Case Matrix

| Scenario | Input / State | Expected Output / Behavior | Error Handling |
|----------|--------------|---------------------------|----------------|
| Curseur déplacé | `/llm`, distribution simulée, top-k passé de 0 à 2 au curseur | barres redessinées : 2 lignes gardées, les autres grisées « écarté », `p` inchangé, dernière requête = dernier réglage | aucune erreur JS |
| Température changée | T 1 → 0,3 | `p` (modèle) fixe, chance de tirage qui bouge | — |
| Puce cliquée | clic sur la puce n° 3 | requête `index: 2`, en-tête « token 3 », puce marquée | — |
| Fenêtre | `usable` 1 000, `prompt_tokens` 250, `reserve` 500, puis 1 puis 3 tokens | remplissage du prompt à 25 % de sa part ; part de sortie à 1/500 puis 3/500 de la réserve, qui croît | — |
| A/B arrêtée pendant B | moteur local, A finie, B en cours | A `completed`, B `cancelled`, un seul retour à `idle` | — |
| A/B cloud | `Provider` à deux réponses | deux requêtes, températures A puis B, A puis B `completed`, distribution indisponible | — |
| « Arrêter » de `/llm` | comparaison sur le faux cloud lent, B en cours | B `cancelled`, colonne B le dit, boutons réactivés | — |
| `/mcp` injoignable | `/api/mcp_lab` coupé par `page.route` | alerte lisible, la page se rétablit seule quand la route revient | aucune erreur JS |
| `/mcp` occupé | tour lent de l'atelier principal | bandeau « Occupé » avec la raison, « Se connecter » désactivé, appel direct 409, « Arrêter » de l'atelier MCP désactivé | — |
| « Arrêter » de `/mcp` | pendant la poignée de main du glossaire | connexion `error` « arrêté », `open_server` nul, `idle` | course perdue : nouvel essai (3 au plus) |
| Serveur public coupé | data.gouv.fr, réseau coupé par la pile E2E | `connect_ended{error}`, requête sortante POST affichée | page lisible |
| Rejeu | rechargement après connexion et appel | mêmes messages et même résultat d'appel | — |
| Champs, troncature, note | `last_session` simulé (serveur public, outil à paramètres objet, entier, booléen ; appel tronqué) | champ JSON, nombre, case ; JSON invalide dit sans envoi ; arguments envoyés convertis ; note de troncature ; « servi non traduit » par outil | — |
| Arrêt stdio | appel au glossaire, processus enfant suspendu | `call_ended{error}` « arrêté », connexion fermée, aucun processus restant | reprise des processus en `finally` |
| Refus pendant l'atelier MCP | état `mcp_lab` | intentions de classe (b) de l'écran principal : 409 avec la raison, aucun événement | — |
| BM25 `en`/`de` | « What is the HR policy », « Wie viele Tage und Wochen » | « what », « is », « the » / « wie », « und » ignorés ; « hr », sigles et nombres gardés | — |

</intent-contract>

## Code Map

- `src/wavestack/web/static/llm.js` -- `renderDistributionIdle` l.506, `scheduleDistribution` l.514 (anti-rebond 80 ms), `fetchDistribution` l.519 (ticket : la dernière réponse gagne), `renderDistribution` l.553 (`.dist-row`, `.is-dropped`, `.dist-cell.is-model`/`.is-chance .dist-value`, largeur `fill.style.width = p×100 %`), `chooseDistributionToken` l.614, `renderWindow` l.735 (`.window-fill.is-prompt` largeur `calc(100% * prompt/usable)`), `windowToken` l.768 (`.window-fill.is-output`, `index+1 / reserve`), `renderToken` l.844, `bindCandidates` l.1063 (clic → `chooseDistributionToken`), `applyEnvelope` l.1135 (contexte `llm`, `compareLane`), `streamEvents` l.1237 (relit `/api/stream` après 1 s quand le corps se termine), `refresh` l.1286 (`candidates`, `distribution.tokens`, `sampling.supported`), `renderBusy` l.137 (`#stop-button` actif en `llm_lab`).
- `src/wavestack/models/candidates.py:137` -- `distribution(top_p_values, tail, sampling)` ; `session/app_session.py:8036` -- `llm_distribution` (forme de la réponse) ; `_run_compare` l.7976.
- `src/wavestack/trace/catalog.py` -- `LlmGenerationStartedPayload` l.1066, `LlmTokenPayload` l.1097, `McpLab*Payload` l.1264-1312, `PAYLOAD_MODELS` l.1316.
- `tools/e2e/run_e2e.py` -- `s_llm_screen` l.7881 (cloud A, puis llama-server), `_lab_compare` l.8217, `_LAB_SAMPLING`, `_lab_generate` ; `s_mcp_lab` l.4460 ; `SCENARIOS` l.8834 ; `Run` (`check`, `api`, `ev.wait`, `fake_calls`, `shot`).
- `tools/e2e/fake_openai.py:418` -- « [lent] » : 0,4 s par fragment (le faux cloud A).
- `src/wavestack/web/static/mcp.js` -- `refresh` l.~770 (alerte `#mcp-content-error`, nouvel essai toutes les 2 s), `renderServers` (boutons `data-connect`), `renderBusy` (`#mcp-busy`, `#mcp-stop`), `renderTools` (`.mcp-served` si serveur réseau), `renderFields`/`applyPreset`/`callArguments` (types `text`/`number`/`boolean`/`json`), `renderCallResult` (troncature `mcp.call_truncated`), `outboundItem` (`.mcp-outbound`).
- `tests/test_llm_lab.py:1017-1100` -- tests de comparaison ; `tests/test_cloud.py:64,86` -- `Provider`, `_cloud_session` ; `tests/fake_engine.py` -- `outputs` par appel, `delay`.
- `tests/test_mcp_lab.py` -- `connect`, `lab_call`, `lab_events`, `wait_idle`, `_client`, `test_stop_during_a_call_closes_the_connection` l.416 (modèle, sur `McpWeb`) ; `tests/test_mcp.py:186-202` -- `local_servers()` (psutil), `no_local_server_left()`.
- `src/wavestack/rag/lab.py:1854-1900` -- `STOP_WORDS`, `bm25_terms`, `bm25` ; appel l.1714 et l.1730 dans `_lexical_search` (`self.deps.lang`, `LabDeps.lang` l.~998) ; `content/rag_lab.yaml:96-101` et surcouches (`stages.lexical_search.explain_text`) ; `tests/test_rag_lab.py:444,803`.
- `content/i18n/de/messages.yaml:358` -- `session.compression.the_compressor` ; insérée par `_compressor_label()` (`app_session.py:3270`) dans `session.architecture.compressor` (sujet, nominatif) et, par `_load_compressor` l.3344, dans `models.load_registry.component_refused` (« um {label} zu laden » : accusatif).
- `_bmad-output/specs/spec-langues/stories/5-messages-produits-par-le-backend.md` -- `status: in-review`, tâches cochées absentes.

## Tasks & Acceptance

**Execution:**
- [ ] 1 · `spec-langues/stories/5-messages-produits-par-le-backend.md` -- `status: done`, tâches cochées, ligne de clôture (story 7, PR #14 et #16, tranche `backend_language` 16/16).
- [ ] 2 · `content/messages.yaml` et surcouches, `app_session.py`, `tests/test_compression.py` -- clé `session.compression.the_compressor_to_load` (accusatif : « den Kompressor ») pour le refus de budget, `the_compressor` gardée au nominatif pour le schéma ; test : refus de budget en `de` sans libellé de fabrique → « um den Kompressor zu laden ».
- [ ] 3 · `src/wavestack/rag/lab.py`, `content/rag_lab.yaml` et surcouches, `tests/test_rag_lab.py` -- `STOP_WORDS_BY_LANG` (fr, en, de, accents pliés ; « it » et « us » gardés : sigles), `bm25_terms(text, lang)`, `bm25(query, docs, lang)`, `_lexical_search` passe `self.deps.lang` ; explications réécrites dans les trois langues ; tests : mots vides par langue, sigles gardés, une course en `en` dont l'entrée ne cite pas « the ».
- [ ] 4 · `tests/test_llm_lab.py` -- arrêt pendant B (moteur local) ; comparaison cloud (`Provider` à deux réponses).
- [ ] 5 · `tests/test_mcp_lab.py` -- arrêt pendant un appel au glossaire (enfant suspendu par psutil) ; refus des intentions de classe (b) de l'écran principal en `mcp_lab` (routes web, 409, aucun événement).
- [ ] 6 · `tools/e2e/run_e2e.py` -- `llm_screen` : comparaison sur le faux cloud A lent arrêtée par « Arrêter » pendant B ; nouveau scénario `llm_live` (distribution et fenêtre par `page.route`).
- [ ] 7 · `tools/e2e/run_e2e.py` -- nouveau scénario `mcp_lab_page` (matrice `/mcp` ci-dessus) ; `tools/e2e/README.md` si la liste des scénarios y est décrite.
- [ ] 8 · specs des stories 5 et 6 (`deferred`), `deferred-work.md` -- clôtures avec preuve ; Implementation Notes de ce lot.

**Acceptance Criteria:**
- Given la tête du lot, when on lance `ruff check`, `ruff format --check` sur les fichiers touchés et pytest en quatre quarts, then aucun échec qui ne soit expliqué et sans lien avec le lot.
- Given les tranches E2E `llm_screen llm_live bare_llm annex_language` et `mcp_lab mcp_lab_page mcp_full mcp_lazy`, when on les joue, then 0 échec.
- Given la langue `de`, when un refus de budget nomme le compresseur sans libellé de fabrique, then la phrase est « …, um den Kompressor zu laden: … ».
- Given l'atelier RAG en `en` ou `de`, when la recherche BM25 tourne, then les mots vides de la langue ne figurent pas dans les mots cherchés affichés et l'explication de l'étape le dit dans la langue.

## Spec Change Log

## Review Triage Log

## Design Notes

- **Flux simulé par lots.** `streamEvents` relit `/api/stream` une seconde après la fin d'un corps. La route rend le lot suivant seulement quand le test l'a « libéré », sinon un corps vide : le test vérifie l'état entre deux lots (réserve qui croît) sans bloquer le fil de Playwright. Les `seq` simulés partent du `seq` réel de `/api/llm_lab` (+ 1 000).
- **Arrêt stdio sans crochet.** Le glossaire répond en quelques ms : le test suspend le processus enfant (psutil) une fois l'atelier connecté, lance l'appel, attend le `mcp_lab_message` `tools/call` sortant, puis `stop()`. Les processus sont repris en `finally` (un processus déjà tué est ignoré).
- **« Arrêter » de `/mcp`.** Sans crochet, seule la poignée de main du glossaire (lancement d'un processus Python, ~1 s) laisse le temps de presser le bouton : le test le presse dès qu'il s'active, et rejoue au plus trois fois si la poignée de main a gagné la course.

## Verification

**Commands:**
- `uv run ruff check src tests tools ; uv run ruff format --check src tests tools` -- expected: aucun écart
- `node --check src/wavestack/web/static/llm.js src/wavestack/web/static/mcp.js` -- expected: aucune erreur (si touchés)
- `uv run pytest -q tests/test_llm_lab.py tests/test_mcp_lab.py tests/test_rag_lab.py tests/test_compression.py tests/test_i18n.py` -- expected: tout passe
- pytest en quatre quarts des `tests/test_*.py` triés, un à la fois -- expected: tout passe
- `$env:PYTHONUTF8=1; uv run --with playwright==1.56.0 python tools/e2e/run_e2e.py --only llm_screen llm_live bare_llm annex_language` puis `--only mcp_lab mcp_lab_page mcp_full mcp_lazy`, puis `--only rag rag_rerank rag_lab` -- expected: 0 FAIL
