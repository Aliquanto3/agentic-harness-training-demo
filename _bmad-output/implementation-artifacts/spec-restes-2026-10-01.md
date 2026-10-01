---
title: 'Restes du 2026-10-01 : constats différés des stories 5 et 6, BM25 par langue, libellé allemand, statut Langues 5'
type: 'chore'
created: '2026-10-01'
status: 'done'
baseline_commit: '18c39782cb78d915dfebd38e2a4f63eb925f04e9'
baseline_revision: '18c39782cb78d915dfebd38e2a4f63eb925f04e9'
route: 'dispatch'
review_loop_iteration: 0
followup_review_recommended: true
context:
  - '{project-root}/_bmad-output/specs/spec-corrections-2026-09-30/stories/5-llm-nu-pedagogique-distribution-vivante-comparaison-a-b-schemas.md'
  - '{project-root}/_bmad-output/specs/spec-corrections-2026-09-30/stories/6-atelier-mcp-mcp-le-protocole-a-manipuler.md'
  - '{project-root}/_bmad-output/specs/spec-langues/i18n-conventions.md'
warnings: ['multiple-goals']
deferred:
  - summary: >-
      La réponse simulée de `/api/llm_lab/distribution` dans l'E2E `llm_live` recopie à la main la forme de `AppSession.llm_distribution` (et renvoie `sampling` brut) : une dérive de la vraie route ne serait pas vue par l'E2E.
    evidence: |-
      Revue du 2026-10-01 du lot des restes (IA1, BH9) : `_LiveLab.distribution` (`tools/e2e/run_e2e.py`) construit son dict ; seule `candidates.distribution` est partagée. Piste : un constructeur de réponse partagé côté session, ou un test pytest qui compare clés et types des deux.
    location: >-
      tools/e2e/run_e2e.py (_LiveLab.distribution) ; src/wavestack/session/app_session.py (llm_distribution)
    severity: low
  - summary: >-
      La garde du ticket de `fetchDistribution` (une réponse ancienne arrivée après une plus récente est ignorée) n'est éprouvée par aucun test : la route simulée répond dans l'ordre.
    evidence: |-
      Revue du 2026-10-01 du lot des restes (VG2) : supprimer `if (ticket !== store.dist.ticket) return;` (`llm.js`) laisse `llm_live` vert. Piste : `_LiveLab` retient la première réponse jusqu'à ce que la seconde soit servie, mouvements espacés de plus de 80 ms.
    location: >-
      src/wavestack/web/static/llm.js (fetchDistribution) ; tools/e2e/run_e2e.py (_llm_live)
    severity: low
  - summary: >-
      Le refus de budget de l'atelier RAG insère « modèle d'embedding X » sans article dans `models.load_registry.component_refused` (« pour charger modèle d'embedding X », « um Embedding-Modell X zu laden »), en fr, en, de.
    evidence: |-
      Revue du 2026-10-01 du lot des restes (BH8) : `rag/lab.py:938` compose `f"{render(noun_text, lang)} {label_text}"`. Préexistant, hors du point du compresseur.
    location: >-
      src/wavestack/rag/lab.py:938 ; content/messages.yaml (session.rag.model_noun.*, models.load_registry.component_refused)
    severity: low
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
- [x] 1 · `spec-langues/stories/5-messages-produits-par-le-backend.md` -- `status: done`, tâches cochées, ligne de clôture (story 7, PR #14 et #16, tranche `backend_language` 16/16).
- [x] 2 · `content/messages.yaml` et surcouches, `app_session.py`, `tests/test_compression.py` -- clé `session.compression.the_compressor_to_load` (accusatif : « den Kompressor ») pour le refus de budget, `the_compressor` gardée au nominatif pour le schéma ; test : refus de budget en `de` sans libellé de fabrique → « um den Kompressor zu laden ».
- [x] 3 · `src/wavestack/rag/lab.py`, `content/rag_lab.yaml` et surcouches, `tests/test_rag_lab.py` -- `STOP_WORDS_BY_LANG` (fr, en, de, accents pliés ; « it » et « us » gardés : sigles), `bm25_terms(text, lang)`, `bm25(query, docs, lang)`, `_lexical_search` passe `self.deps.lang` ; explications réécrites dans les trois langues ; tests : mots vides par langue, sigles gardés, une course en `en` dont l'entrée ne cite pas « the ».
- [x] 4 · `tests/test_llm_lab.py` -- arrêt pendant B (moteur local) ; comparaison cloud (`Provider` à deux réponses).
- [x] 5 · `tests/test_mcp_lab.py` -- arrêt pendant un appel au glossaire (enfant suspendu par psutil) ; refus des intentions de classe (b) de l'écran principal en `mcp_lab` (routes web, 409, aucun événement).
- [x] 6 · `tools/e2e/run_e2e.py` -- `llm_screen` : comparaison sur le faux cloud A lent arrêtée par « Arrêter » pendant B ; nouveau scénario `llm_live` (distribution et fenêtre par `page.route`).
- [x] 7 · `tools/e2e/run_e2e.py` -- nouveau scénario `mcp_lab_page` (matrice `/mcp` ci-dessus) ; `tools/e2e/README.md` si la liste des scénarios y est décrite.
- [x] 8 · specs des stories 5 et 6 (`deferred`), `deferred-work.md` -- clôtures avec preuve ; Implementation Notes de ce lot.

**Acceptance Criteria:**
- Given la tête du lot, when on lance `ruff check`, `ruff format --check` sur les fichiers touchés et pytest en quatre quarts, then aucun échec qui ne soit expliqué et sans lien avec le lot.
- Given les tranches E2E `llm_screen llm_live bare_llm annex_language` et `mcp_lab mcp_lab_page mcp_full mcp_lazy`, when on les joue, then 0 échec.
- Given la langue `de`, when un refus de budget nomme le compresseur sans libellé de fabrique, then la phrase est « …, um den Kompressor zu laden: … ».
- Given l'atelier RAG en `en` ou `de`, when la recherche BM25 tourne, then les mots vides de la langue ne figurent pas dans les mots cherchés affichés et l'explication de l'étape le dit dans la langue.

## Implementation Notes

Commits sur `feat/restes-2026-10-01` (base `18c3978`) : `1fc4578` (spec), `c61770e` (1, statut Langues 5), `584163d` (2, compresseur à l'accusatif), `1ebc5bd` (3, BM25 par langue), `fe7ca10` (4, A/B), `8954576` (5, atelier MCP), `17f2748` (6, E2E `/llm`), `66971d8` (7, E2E `/mcp`), `e0e81fd` (8, clôtures), `87f6ac3` (correctifs de revue), puis le commit de clôture de cette spec.

### Décisions prises seul (à relire par Anaël)

- **Workflow BMAD.** `bmad-build-auto` exige des sous-agents synchrones ; ici ils tournent en arrière-plan : l'implémentation a été faite à la main, avec la même discipline (spec, code, tests, revue). La revue à quatre couches a été lancée en sous-agents (lecture seule) pendant que pytest tournait.
- **Point 2.** Un seul cas ne suffit pas : `the_compressor` sert de sujet (détail du schéma, « der Kompressor, Bibliothek… ») et d'objet (« um {label} zu laden »). Nouvelle clé `session.compression.the_compressor_to_load` (fr et en identiques à `the_compressor`, de « den Kompressor »), prise par `_compressor_label(to_load=True)` dans `_load_compressor`. Chemin rare : la fabrique Headroom donne toujours son `label_text`.
- **Point 3.** Listes courtes et prudentes ; en anglais « it » et « us » gardés (sigles « IT », « US »). Langue inconnue : le français. L'explication française n'a pas changé (elle était juste) ; en et de réécrites.
- **Point 4.** Le test cloud utilise un `Provider` qui répond selon la température (A et B distingués sans dépendre du nombre de requêtes faites au démarrage).
- **Point 5.** Arrêt stdio sans crochet : le processus du glossaire est suspendu par psutil (il ne lit plus rien), puis repris en `finally`. Les refus : 14 routes de classe (b) de l'écran principal et des ateliers, chacune 409 avec « Atelier MCP » dans la raison.
- **Point 6.** Nouveau scénario `llm_live` plutôt qu'un ajout à `llm_screen` (il se lance seul, sur le faux cloud A dont `/api/llm_lab` est réécrit). L'arrêt de la comparaison est joué sur le faux cloud A (« [lent] ») : il couvre aussi la comparaison cloud dans l'E2E. La première entrée `deferred` de la story 5 (redessin des barres avec un moteur factice) est close par la même voie (`page.route`), pas par un moteur factice.
- **Point 7.** Nouveau scénario `mcp_lab_page`. « Hors ligne » couvert de deux façons : `/api/mcp_lab` coupé par `page.route`, et data.gouv.fr hors réseau (pile E2E). « Arrêter » est pressé pendant la poignée de main du glossaire (seul échange assez long sans crochet), jusqu'à trois essais ; gagné au premier essai aux deux passages. Champs JSON, troncature et note « servi non traduit » sur un `last_session` simulé (aucun serveur public joignable ici).
- **Constat nouveau, consigné dans `deferred-work.md`** : « 1 tokens produits » et « Réponse : 1 tokens » (comptes de `llm_lab.yaml` sans pluriel), vu sur la capture 65. Préexistant, hors périmètre.

### Vérification

- Itération : `test_compression -k budget_refusal` 3 passés (le nouveau test échoue sur l'ancien code) ; `test_i18n`, `test_backend_messages` 3 257 passés ; `test_rag_lab`, `test_rag_lab_alt`, `test_annex_language` 90 passés, 1 échec (`test_nothing_is_written_under_the_repository`, écritures concurrentes d'autres agents dans le dépôt pendant le test), vert rejoué seul ; `test_llm_lab` 62 passés (1 désélectionné, marqueur `model`) ; `test_mcp_lab` 21 passés.
- E2E : `--only llm_screen llm_live bare_llm annex_language` 98/98 ; `--only mcp_lab mcp_lab_page mcp_full mcp_lazy` 51/52 au premier passage (attente fausse dans le test : la page formate « 2 048 »), corrigé, `--only mcp_lab_page` 19/19. Captures modifiées restaurées, nouvelles : 65 et 66.

## Spec Change Log

## Review Triage Log

### 2026-10-01 — Review pass
- verdicts: 37 findings — high 0, medium 4, low 29, false 4, maybe-false 0
- findings:
  - Intent Alignment
  - `[low]` `[defer]` IA1 : la réponse simulée de `/api/llm_lab/distribution` recopie à la main la forme de `AppSession.llm_distribution`, jamais comparée à elle — dérive possible sans que l'E2E la voie ; correctif = un constructeur partagé côté session (surface nouvelle), différé.
  - `[low]` `[reject]` IA2 : « Arrêter » de la page jamais pressé pendant B sur un moteur local — l'intention demande le bouton dans la tranche `llm_screen` : pressé sur le faux cloud ; l'arrêt pendant B en local est couvert par pytest.
  - `[low]` `[reject]` IA3 : champs JSON, troncature, note « servi non traduit » vérifiés sur un `last_session` fabriqué — voulu (aucun serveur public joignable dans la pile E2E) et validé par `Envelope`.
  - `[medium]` `[patch]` IA4 : la liste des intentions refusées omettait `set_api_key`, `test_cloud_model`, `reset` (et `download_model`, `build_rag_index`) — les trois premières ajoutées (409 avec la raison) ; les deux dernières répondent 404 avant l'état quand la brique RAG est éteinte, dit en commentaire.
  - `[false]` `[reject]` IA5 : passages français filtrés avec les mots vides anglais quand l'index de la brique sert — faux : l'index de la brique est par langue (`AppSession._rag_index_path` → `cfg.rag_index_path(self._language)`), seule la fixture des tests est française ; commentaire du code précisé.
  - `[low]` `[reject]` IA6 : le libellé à l'accusatif n'est pris que sans libellé de fabrique (jamais avec Headroom) — c'est le point 4 tel que demandé.
  - `[low]` `[patch]` IA7 : l'entrée Langues 5 de `deferred-work.md` disait encore « à jouer » pour `backend_language` — annotée (16/16, story close).
  - `[low]` `[patch]` IA8 : tâches de la spec non cochées, pas d'Implementation Notes dans le diff relu — notes écrites (non commitées au moment de la revue), tâches cochées à la finalisation.
  - `[false]` `[reject]` IA9 : chiffres de preuve non montrés par le diff — ce sont des comptes rendus d'exécution, consignés avec leurs commandes.
  - Verification Gap
  - `[medium]` `[patch]` VG1 : le score BM25 de `_lexical_search` n'était pas éprouvé dans la langue de la session (seuls les mots affichés l'étaient) — test paramétré `en`/`de` : chaque extrait trouvé partage un mot de contenu avec la question ; démontré : il échoue (2/2) quand le score reprend les mots vides français.
  - `[low]` `[defer]` VG2 : « le dernier mouvement gagne » ne prouve pas la garde du ticket de `fetchDistribution` (la route simulée répond dans l'ordre) — formulations des preuves corrigées (story 5, `deferred-work.md`) ; une réponse retardée dans `_LiveLab` est différée.
  - Blind Hunter
  - `[low]` `[patch]` BH1 : spec sans preuve propre — même correctif qu'IA8.
  - `[low]` `[patch]` BH2 : `STOP_WORDS` changeait de type sous le même nom (une ancienne utilisation filtrerait en silence sur les clés) et la spec annonçait `STOP_WORDS_BY_LANG` — renommé `STOP_WORDS_BY_LANG`.
  - `[low]` `[patch]` BH3 : refus de classe (b) incomplets — même correctif qu'IA4.
  - `[low]` `[patch]` BH4 : règle des sigles appliquée inégalement (« who »/WHO, « am »/9 am) — retirés de la liste anglaise ; « ce » (CE) français préexistant, laissé.
  - `[false]` `[reject]` BH5 : commentaire « le corpus et la question sont dans la langue de la session » faux — même réfutation qu'IA5.
  - `[medium]` `[patch]` BH6 : allemand moins couvert (pas de course `de`, « französische » non vérifié absent, français non vérifié) — course `de` ajoutée au test paramétré, test des trois explications.
  - `[low]` `[reject]` BH7 : preuves manquantes (tranche `rag rag_rerank rag_lab`, `backend_language` rejouée ?) — la tranche RAG est jouée en vérification finale ; Langues 5 close sur la vérification avec processus du 2026-10-01, dite telle.
  - `[low]` `[defer]` BH8a : la même phrase de refus reçoit « modèle d'embedding X » sans article (atelier RAG, `rag/lab.py:938`), fr, en, de — préexistant, hors de ce point.
  - `[low]` `[reject]` BH8b : l'étiquette `[reject]` de la story 7 reste malgré la reprise — journal append-only, la sous-ligne dit la reprise.
  - `[low]` `[defer]` BH9 : la route simulée renvoie `sampling` brut au lieu de `asdict` — même cause qu'IA1 (la page ne lit pas ce champ).
  - `[low]` `[patch]` BH10a : `sent_at[before] < sent_at[before + 1]` toujours vrai — supprimé (l'ordre est prouvé par les `seq`).
  - `[low]` `[reject]` BH10b : `engine.outputs` selon le nombre d'appels du démarrage, un token par caractère — motif des tests existants de `FakeEngine`, documenté par lui.
  - `[low]` `[patch]` BH11 : course d'« Arrêter » perdue trois fois → délai Playwright au lieu d'une vérification lisible — `_mcp_stop_during_handshake` rend un échec dit et arrête le scénario.
  - `[low]` `[patch]` BH12 : la réponse `tools/list` simulée était vide alors qu'un outil est listé — elle liste l'outil.
  - `[low]` `[patch]` BH13 : guillemets français dans un commentaire du fichier anglais — remplacés.
  - Edge Case Hunter
  - `[medium]` `[patch]` EC1 : un `assert` après `suspend()` laissait la liste du `finally` vide (processus suspendus) — la liste de l'appelant est remplie avant la suspension.
  - `[low]` `[patch]` EC2 : `assert session.state == "llm_lab"` après `llm_compare` cloud, course avec un faux fournisseur instantané — retiré (l'état synchrone est testé ailleurs).
  - `[low]` `[patch]` EC3 : `KeyError` opaque dans `_ByTemperature` — réponse 500 qui montre le corps inattendu.
  - `[low]` `[patch]` EC4 : un échec à l'étape « Occupé » laissait le tour lent tourner — `try/finally` qui l'arrête.
  - `[low]` `[patch]` EC5 : course d'« Arrêter » — même correctif que BH11.
  - `[low]` `[patch]` EC6 : tolérance égale à la valeur attendue (1/500 ± 0,002) — 0,0005.
  - `[false]` `[reject]` EC7 : `_DIST_ROWS_JS` pourrait lire une ligne à moitié redessinée — `renderDistribution` vide puis remplit la liste dans la même tâche ; `evaluate` ne s'intercale pas.
  - `[low]` `[reject]` EC8 : contractions anglaises (« don », « isn ») — rares dans un corpus formel, et « don », « won » sont aussi des mots.
  - `[low]` `[patch]` EC9 : le filtre « aucun événement » des refus ne regardait que des démarrages — il exige désormais zéro événement depuis la marque.
  - `[low]` `[patch]` EC10 : `STOP_WORDS_BY_LANG` annoncé, `STOP_WORDS` livré — même correctif que BH2.
  - `[low]` `[reject]` EC11 : « explications réécrites dans les trois langues » alors que le français n'a pas changé — corriger reviendrait à éditer la spec ; les notes le disent.

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

## Auto Run Result

Status: done

- **Changement** : les cinq points du périmètre. (1) Story Langues 5 passée à `done`. (2) Refus de budget allemand à l'accusatif par une seconde clé `session.compression.the_compressor_to_load`. (3) Mots vides de BM25 par langue (`STOP_WORDS_BY_LANG`, `LabDeps.lang`), explications en et de réécrites. (4) Tests de la comparaison A/B (arrêt pendant B, modèle cloud) et E2E `llm_live` (distribution vivante et fenêtre par `page.route`) plus l'arrêt d'une comparaison par le bouton dans `llm_screen`. (5) Tests de l'atelier MCP (arrêt d'un appel stdio, refus pendant un échange) et E2E `mcp_lab_page`. Entrées `deferred` des stories 5 et 6 et de `deferred-work.md` closes avec leur preuve.
- **Fichiers** : `content/messages.yaml` et surcouches (clé d'accusatif) ; `src/wavestack/session/app_session.py` (`_compressor_label(to_load=)`) ; `src/wavestack/rag/lab.py` (mots vides par langue) ; `content/i18n/{en,de}/rag_lab.yaml` (explications) ; `tests/test_compression.py`, `test_rag_lab.py`, `test_llm_lab.py`, `test_mcp_lab.py` (tests nouveaux) ; `tools/e2e/run_e2e.py` (`llm_live`, `mcp_lab_page`, `_lab_compare_stopped`), `tools/e2e/README.md`, captures 65 et 66 ; specs des stories 5, 6, 7 et Langues 5, `deferred-work.md`.
- **Revue** : 37 constats (0 high, 4 medium, 29 low, 4 false) ; 22 lignes corrigées (dont les 4 medium : IA4, VG1, BH6, EC1) ; 4 différées (IA1, BH9, VG2, BH8a) ; 11 rejetées avec leur raison (journal ci-dessus).
- **Revue de suivi recommandée** : oui (règle du premier passage : 4 entrées `medium` corrigées). Risque nommé : l'E2E `llm_live` ne compare pas la forme de sa réponse simulée à celle de la session, et la garde du ticket de `fetchDistribution` n'est pas éprouvée (entrées `deferred`).
- **Vérification finale (tête `87f6ac3`)** : `ruff check` et `ruff format --check` sur `src tests tools` propres. pytest en quatre quarts, un à la fois : Q1 3 567 passés (avant les correctifs de revue, fichiers non touchés par eux) ; Q2 599 passés, 1 désélectionné ; Q3 365 passés, 3 sautés, 3 désélectionnés ; Q4 336 passés, 3 désélectionnés. Aucun échec. Fichiers touchés par la revue rejoués : `test_llm_lab`, `test_mcp_lab`, `test_rag_lab`, `test_compression`, `test_i18n` 308 passés. E2E (`PYTHONUTF8=1`) : `mcp_lab mcp_lab_page mcp_full mcp_lazy` 52/52 ; `llm_screen llm_live bare_llm annex_language` 98/98 ; `rag rag_rerank rag_lab compression` 116/116 ; `backend_language ui_language content_language language` 64/64. Captures restaurées, sauf les nouvelles 65 et 66.
- **Risques résiduels** : la course d'« Arrêter » de `/mcp` (gagnée au premier essai sur ce poste, trois essais au plus) ; `test_nothing_is_written_under_the_repository` sensible aux écritures d'autres agents dans le dépôt pendant la suite.
