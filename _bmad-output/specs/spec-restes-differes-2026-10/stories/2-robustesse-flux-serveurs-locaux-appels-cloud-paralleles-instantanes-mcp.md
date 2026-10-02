---
title: 'Robustesse : flux, serveurs locaux, appels cloud parallèles, instantanés MCP'
type: 'bugfix'
created: '2026-10-01'
status: 'done'
baseline_commit: '2269793edb480b92807883613809b1b421ec92cf'
route: 'dispatch'
review_loop_iteration: 0
followup_review_recommended: false
context:
  - '{project-root}/_bmad-output/specs/spec-restes-differes-2026-10/SPEC.md'
  - '{project-root}/_bmad-output/specs/spec-langues/i18n-conventions.md'
warnings: []
deferred: []
---

<frozen-after-approval reason="human-owned intent — do not modify unless human renegotiates">

## Intent

**Problem:** Six défauts de robustesse restent ouverts (CAP-2 de `SPEC.md`) : un flux SSE coupé ne se voit pas, un Ollama trop ancien pour `qwen35` donne une erreur brute « HTTP 500 » au premier tour, deux appels d'outils parallèles au même `index` seraient fusionnés, l'avertissement d'écart à l'instantané MCP d'AD-9 n'existe pas, la composition du contexte du sous-agent est écrite en dur, et `back_text` survit sans usage.

**Approach:** Corriger chaque point au plus près de son module, avec ses tests pytest, ses textes en trois langues, et fermer les entrées.

## Boundaries & Constraints

**Always:**
- Entrées fermées (`closed: <date> (story 2 des restes différés) — <preuve>`) :
  - **E003** — après N échecs consécutifs de `streamEvents` (N petit, par exemple 3), la barre haute affiche « Connexion au serveur perdue, nouvel essai… » (texte `ui.yaml`, trois langues) ; il disparaît au premier événement reçu ; la reprise par `Last-Event-ID` est inchangée.
  - **E048** — `openai_chat` : un fragment d'appel qui arrive avec un `id` différent sur une clé (`index`) déjà prise ouvre un nouvel appel ; deux appels au même `index` (ou sans `index`) et d'`id` différents restent deux appels. Test avec `httpx.MockTransport`. La vérification réelle (Groq, Mistral) est faite par la story 7 : noter dans l'entrée « vérifié avec doublure, réel en story 7 ».
  - **E067** — le contexte `sub{n}` est composé en itérant sur les briques effectives qui déclarent `sub` dans `contributes_to` ; aucune brique nouvelle n'y entre : un test montre que le contexte du sous-agent est identique avant et après.
  - **E089** — seuil `[mcp] snapshot_drift_threshold` dans `wavestack.toml` (valeur à choisir au plan, documentée) ; à la connexion d'un serveur public qui a un instantané dans `content/mcp_snapshots/`, si `tools/list` s'en écarte au-delà du seuil (outils ajoutés ou retirés, ou poids de la documentation), un avertissement est émis et affiché sur la carte MCP ; sans instantané, rien.
  - **E119** — un modèle servi par Ollama dont `/api/generate` répond 500 parce que l'architecture n'est pas prise en charge : raison française (et `en`, `de`) qui nomme la cause et propose llama-server ou une mise à jour d'Ollama ; le modèle précédent est rétabli, ou le modèle refusé dès le chargement si une requête de vérification légère le permet (choix au plan, consigné).
  - **E142** — `back_text` retiré de `content/llm_lab.yaml`, `content/rag_lab.yaml`, de leurs surcouches `en`/`de` et de `LlmLabContent` / `RagLabContent` (et des tests qui le citent).
- Textes nouveaux par `t()` / `msg()`, en `fr`, `en`, `de` ; ARCHITECTURE-SPINE (AD-9) et README à jour pour E089.

**Never:**
- Retenter ou espacer automatiquement les appels après une erreur de serveur.
- Faire entrer une brique de plus dans le contexte du sous-agent (E067 est un refactor sans effet).
- Toucher aux blocs `deferred` des stories 5 et 6 de `spec-corrections-2026-09-30` (autre agent) : rebaser après sa fusion si `llm_lab.yaml` ou `rag_lab.yaml` ont bougé.

## I/O & Edge-Case Matrix

| Scenario | Input / State | Expected Output / Behavior | Error Handling |
|----------|--------------|---------------------------|----------------|
| Deux appels même index | fragments `index: 0, id: a` puis `index: 0, id: b` | deux `tool_calls` | aucune |
| Fragments d'un même appel | `index: 0, id: a` puis `index: 0` sans `id` | un appel, arguments concaténés | aucune |
| Ollama sans `qwen35` | 500 « unknown model architecture » | raison expliquée, modèle précédent actif | `harness_error` avec la cause |
| Instantané absent | serveur public sans fichier d'instantané | aucun avertissement | aucune |
| Flux coupé | serveur arrêté | indicateur après N échecs, effacé au retour | aucune |

</frozen-after-approval>

## Code Map

- `src/wavestack/web/static/app.js:200-233` -- `streamEvents` : boucle `fetch("/api/stream")` + reprise `Last-Event-ID`. Le serveur envoie toujours `server_instance` en premier (`web/app.py:1037`) : c'est le « premier événement reçu ». `store.topStatus` et `setTopStatus` (l. 3192, 5897) rendent `#top-status` (`index.html:267`, `role="status"`). Les autres pages (`llm.js`, `rag.js`, `mcp.js`) ont leur propre `streamEvents` : hors périmètre (E003 nomme la barre haute de l'atelier).
- `src/wavestack/models/openai_chat.py:706-718` (`_channels`) et `:666-675` (ordre final) -- accumulation des `tool_calls` par `index`, sinon `id`. Test type : `tests/test_cloud.py::test_calls_without_index_keep_their_arrival_order` (doublure `Provider`, `sse`, `delta`).
- `src/wavestack/session/app_session.py:3939-3956` (`_sub_messages`), appelée par `_render` (l. 3982) et `_render_chat` (l. 4023) ; `_contributes` (l. 3529) ; outils du sous-agent déjà filtrés par `contributes_to` (l. 3600-3611). `bricks/registry.py` : seules `tools` et `subagent` déclarent `sub`.
- `src/wavestack/session/app_session.py:5099-5144` (`_mcp_connected`, `_mcp_apply`), `:1299-1319` (`_mcp_options`) ; `trace/catalog.py:469-484` (`BrickOption`), `:648-653` (`McpConnectEndedPayload`) ; `content/mcp_snapshots/{datagouv,mslearn}.json` (format de `scripts/snapshot_mcp.py` : `tools` = `model_dump(by_alias=True, exclude_none=True)`) ; `config.py:928-941` (lecture `[mcp]`, `_float` l. 633) ; `wavestack.toml:189-193`.
- `src/wavestack/models/servers.py:67-76` (`ServerError`), `:152-178` (`_stream`, HTTP ≥ 400 → `ServerError`), `:552-557` (`OllamaRawEngine.complete`, erreur dans le flux). Session : `_call_model_local` `except ServerError` (`app_session.py:7364-7372`), fin de tour (`_run_turn`, l. 5916-5947), chemin unique de chargement `_load` (l. 1815) avec retour au précédent ; `switch_model` (l. 1782). Tests : `tests/test_model_servers.py` (`FakeServer`, `_factory`, `test_vocab_only_failure_keeps_the_previous_model`).
- `content/llm_lab.yaml:11`, `content/rag_lab.yaml:12`, `content/i18n/{en,de}/{llm,rag}_lab.yaml` ; `session/llm_lab.py:223` (`LabContent.back_text`), `rag/lab.py:141` (`RagLabContent.back_text`) ; modèles `extra="forbid"` : retirer YAML et champ ensemble. Aucun `.js` ni test ne le lit.
- Textes : `content/ui.yaml` (`main.top_bar`), `content/messages.yaml` (`models.servers`, `session.mcp`, `session.load`) et surcouches `content/i18n/{en,de}/`. Parité vérifiée par `tests/test_i18n.py`.
- `tools/e2e/run_e2e.py` -- parcours E2E ; on y écrit le contrôle E003 (non lancé cette nuit).

## Tasks & Acceptance

**Execution:**
- [x] `src/wavestack/models/openai_chat.py` -- clés d'accumulation `(clé, n)` : un fragment portant un `id` différent de celui de l'appel ouvert sur la même clé ouvre `(clé, n+1)` ; tri par `index` puis `n` quand tout est indexé, sinon ordre d'arrivée -- E048.
- [x] `tests/test_cloud.py` -- deux tests `MockTransport` : même `index` et `id` différents → deux appels ; fragments `index: 0, id: a` puis `index: 0` sans `id` → un appel, arguments concaténés -- E048.
- [x] `src/wavestack/session/app_session.py` (`_sub_messages`) -- composer les messages de tête en itérant les briques effectives (registre, ordre déclaré) qui déclarent `sub`, chacune via sa contribution (`subagent` : prompt puis tâche ; `tools` : rien en messages, ses outils passent déjà par `sub.tools`) ; signature reçoit `effective` -- E067.
- [x] `tests/test_subagent.py` -- (1) contexte `sub1` identique octet pour octet avec `tools, subagent` et avec toutes les briques disponibles allumées ; (2) `_sub_messages` égal à la composition écrite en dur d'avant (prompt, tâche, étapes) ; (3) sans `sub` dans `subagent.contributes_to` (monkeypatch), ni prompt ni tâche -- E067.
- [x] `src/wavestack/mcp/snapshot.py` (nouveau) -- `load_snapshot(server_id)`, `documentation_weight(tools)`, `drift(snapshot, live)` → outils ajoutés, retirés, poids avant/après, ratio ; aucun accès réseau -- E089.
- [x] `src/wavestack/config.py`, `wavestack.toml` -- `[mcp] snapshot_drift_threshold = 0.2` (fraction, bornée 0 à 10, illisible → 0,2), commenté -- E089.
- [x] `src/wavestack/session/app_session.py` (`_mcp_apply`, `_mcp_options`, déconnexion), `trace/catalog.py` -- à la connexion réussie d'un serveur public avec instantané, si l'écart dépasse le seuil : `_log.warning`, `drift_text` dans `mcp_connect_ended` et dans l'option du serveur ; effacé à la déconnexion -- E089.
- [x] `src/wavestack/web/static/app.js`, `app.css` -- sous la ligne du serveur dans la carte MCP, `drift_text` en note d'avertissement -- E089.
- [x] `tests/test_mcp.py` (ou `test_mcp_snapshot.py`) -- seuil dépassé (outil ajouté, documentation alourdie) → avertissement ; sous le seuil → rien ; sans instantané → rien ; serveur local → rien ; calcul pur de `drift` -- E089.
- [x] `src/wavestack/models/servers.py` -- `UnsupportedArchitecture(ServerError)` : levée quand une réponse HTTP ≥ 400 ou une erreur dans le flux nomme `unknown|unsupported model architecture` ; message clé `models.servers.unsupported_architecture` (architecture, cause, llama-server ou mise à jour) -- E119.
- [x] `src/wavestack/session/app_session.py` -- mémoriser le modèle précédent à chaque chargement réussi ; sur `UnsupportedArchitecture` dans un tour : `harness_error` expliqué, puis, une fois le tour terminé et sur le même fil, retour au modèle précédent par `_load` (sauvegardé) ; sans précédent, l'erreur dit de choisir un autre modèle -- E119.
- [x] `tests/test_model_servers.py` -- Ollama qui répond 500 « unknown model architecture: 'qwen35' » : raison française, modèle précédent actif, choix sauvegardé = précédent ; sans précédent : raison et tour en erreur, WaveStack utilisable -- E119.
- [x] `content/*.yaml`, `content/i18n/{en,de}/*.yaml`, `session/llm_lab.py`, `rag/lab.py` -- retirer `back_text` -- E142.
- [x] `src/wavestack/web/static/app.js` -- compteur d'essais consécutifs sans événement dans `streamEvents` ; à 3, `store.connectionLost = true` et rendu ; au premier événement, effacé ; texte `main.top_bar.connection_lost` (fr, en, de) prioritaire dans `#top-status` ; `body[data-connection="lost"]` pour l'E2E -- E003.
- [x] `tools/e2e/run_e2e.py` -- contrôle : `page.route("**/api/stream", abort)` + fermeture du flux courant → texte affiché ; `unroute` → effacé (écrit, non lancé) -- E003.
- [x] `content/ui.yaml`, `content/messages.yaml` (+ `en`, `de`) -- clés nouvelles dans les trois langues.
- [x] `ARCHITECTURE-SPINE.md` (AD-9), `README.md` -- seuil, mesure et affichage de l'écart à l'instantané -- E089.
- [x] `_bmad-output/implementation-artifacts/deferred-work.md` -- fermer E003, E048 (« vérifié avec doublure, réel en story 7 »), E067, E089, E119, E142 avec leur preuve.

**Acceptance Criteria:**
- Given le parcours des tests touchés, when `uv run pytest` les exécute, then tous passent et chaque test nouveau échoue si l'on retire le correctif qu'il protège.
- Given un texte nouveau, when la session ou la page tourne en `en` ou `de`, then il est traduit (parité `test_i18n.py`).
- Given aucun instantané pour un serveur, when il se connecte, then aucun `drift_text` n'apparaît.
- Given un flux SSE coupé puis rétabli sur la même instance, when la page reçoit `server_instance`, then l'indicateur disparaît et aucun événement n'est rejoué deux fois.

## Design Notes

- **E089, mesure.** Poids de la documentation d'un outil = longueur de `description` + longueur du JSON (`sort_keys`, `ensure_ascii=False`) de `inputSchema` ; poids du serveur = somme. Écart = max(`(ajoutés + retirés) / nb outils de l'instantané`, `|poids après − poids avant| / poids avant`). Avertissement si écart > seuil. 0,2 : un outil de plus ou de moins sur Microsoft Learn (2 outils) ou 20 % de documentation en plus suffit à fausser la prévision de jauge du scénario (`mcp_full` était à 3 018 / 3 584).
- **E119, choix consigné.** Pas de refus au chargement : aucune requête légère ne le permet (`/api/show` répond pour une architecture que le moteur d'Ollama ne sait pas charger ; seul un vrai chargement, aussi coûteux que le premier tour, la révèle). On garde donc l'échec au premier tour, expliqué, et on revient au modèle précédent juste après, sur le fil de la session (pas de fenêtre où un autre tour partirait sur le modèle refusé).
- **E048.** `calls` reste un `dict` ; clés `(clé_fournisseur, n)`. Sans `index` ni `id`, clé `(None, n)`, comportement inchangé.

## Verification

**Commands:**
- `uv run ruff check <fichiers touchés>` et `uv run ruff format --check <fichiers touchés>` -- expected: aucun écart.
- `uv run pytest -q tests/test_cloud.py tests/test_subagent.py`, puis `tests/test_mcp.py tests/test_mcp_lazy.py tests/test_program.py`, puis `tests/test_model_servers.py`, puis `tests/test_llm_lab.py tests/test_rag_lab.py tests/test_rag_lab_alt.py tests/test_i18n.py tests/test_content_language.py` (l'un après l'autre) -- expected: tout passe.
- `node --check src/wavestack/web/static/app.js` -- expected: aucune erreur.
- E2E (batterie finale, avec l'accord d'Anaël, pas cette nuit) : `--only themes mcp_full mcp_lazy llm_screen rag_lab` plus le contrôle de connexion perdue -- expected: 0 échec.

## Implementation Notes

- Implémenté directement par l'agent principal (mode nuit) : un sous-agent neuf aurait pu démarrer hors du worktree isolé et toucher le dépôt principal ; le contexte était déjà chargé.
- E048 : `calls` garde ses clés en tuples `(clé, n)` ; mutation vérifiée à la main (condition ramenée à `if n is None` : `test_two_parallel_calls_under_one_index_stay_two_calls` échoue).
- E067 : `_sub_messages` reçoit `state.effective` ; `_sub_contributions` porte la contribution de `subagent`. Le test « écrit en dur » reproduit la composition d'avant ligne pour ligne.
- E089 : `mcp/snapshot.py` (nouveau) ; `drift_text` ajouté à `BrickOption` et `McpConnectEndedPayload` ; avertissement rendu hors des sous-options repliées (`.brick-drift`), pour être vu sans déplier.
- E119 : `OllamaRawEngine.complete` enveloppe `_complete` et convertit l'erreur ; la session mémorise le modèle d'avant chaque chargement réussi (`_before_active`), passe du tour à `model_load` sans repasser par `idle` (`_start_way_back`) puis recharge hors du contexte du tour (`_run_way_back`, `_load(..., ok_reason=...)`), et n'offre plus de retour ensuite (pas d'aller-retour). Le chemin de l'écran LLM nu garde la raison nouvelle mais ne revient pas au modèle précédent.
- E003 : contrôle E2E `stream_lost` écrit dans `tools/e2e/run_e2e.py`, non lancé (règle de la nuit) : la ligne « Flux coupé » de la matrice n'est couverte que par lui, à jouer dans la batterie finale.
- Tests lancés (l'un après l'autre) : `test_cloud.py test_subagent.py` 141 passés ; `test_mcp.py test_mcp_snapshot.py test_mcp_lazy.py test_program.py` 57 passés ; `test_model_servers.py` 79 passés ; `test_llm_lab.py test_rag_lab.py test_rag_lab_alt.py test_i18n.py test_content_language.py test_annex_language.py` 343 passés ; `test_config_paths.py test_trace_architecture.py` 10 passés ; `node --check app.js` OK ; ruff check et format OK sur les fichiers touchés.
- Après la revue (passe 1) : garde `_turn_ctx` sur le drapeau E119 (l'écran LLM nu ne promet ni ne laisse de retour), nouvel appel E048 seulement avec `function.name`, arrondi supérieur de l'écart, `documentation_weight`, message « sans doute trop ancienne », six tests ajoutés. Relancés : `test_cloud.py test_subagent.py` 142 passés ; `test_model_servers.py test_mcp.py test_mcp_snapshot.py` 112 passés ; `test_i18n.py test_content_language.py` 188 passés ; ruff et `node --check` OK.

## Spec Change Log

- 2026-10-01 -- validé en mode nuit (Anaël absent, autorisation du 01/10 au soir) : point d'arrêt 1 (spec) approuvé, « Approve and continue » ; spec conforme au SPEC (CAP-2) et au triage (E003, E048, E067, E089, E119, E142). Choix du plan : seuil 0,2, retour au modèle précédent après le tour pour E119 (pas de refus au chargement), N = 3 pour E003.
- 2026-10-02 -- confirmé par Anaël : choix du mode nuit (retour au modèle précédent après le tour pour E119, N = 3 essais pour E003, seuil d'écart MCP de 0,2) gardés tels quels.

## Review Triage Log

Passe 1 (2026-10-01, trois relecteurs : blind, edge-case, verification-gap).

| # | Constat | Verdict | Preuve | Suite |
|---|---|---|---|---|
| 1 | Refus d'architecture vu par l'écran LLM nu : `_unsupported` posé, retour promis mais jamais fait, drapeau resté qui recharge le modèle refusé après un tour réussi plus tard (3 relecteurs) | high | `_run_lab` appelle `_call_model` ; seul `_run_turn` consomme le drapeau | patch : drapeau et promesse seulement dans un tour (`_turn_ctx`), test `test_a_refusal_on_the_llm_screen_promises_nothing_and_leaves_no_way_back` (échoue sans la garde) |
| 2 | Retour au précédent qui échoue : réinstalle le modèle refusé | medium | `_run_way_back` passe `previous=active` à `_load` | defer (entrée ajoutée) |
| 3 | Sauvegarde du choix en échec : la raison du retour est perdue | low | `reason_text` remplacé par la notice de sauvegarde | rejeté : rare (settings.json non inscriptible), la notice reste dite |
| 4 | Serveur désactivé entre la lecture de la connexion et l'écriture de l'écart | low | même fenêtre que `_mcp_state` existant | rejeté : préexistant, rare |
| 5 | « 20 % (seuil : 20 %) » pour un écart de 0,204 | low | `round` | patch : arrondi supérieur, test `test_a_gap_just_over_the_threshold_never_reads_as_equal_to_it` |
| 6 | Noms en double ou absents dans un instantané | low | `str(None)` | rejeté : instantanés écrits par le script, noms uniques |
| 7 | Premier fragment sans `id` puis second appel avec `id` : fusion | maybe-false | comportement d'avant, inchangé ; Groq et Mistral envoient l'`id` au premier fragment | rejeté ; vérification réelle en story 7 |
| 8 | Fragment sans `index` ni `id` : appel `(None, n)` séparé | low | préexistant | rejeté : non causé par le changement |
| 9 | Fragments entrelacés sans `id` | maybe-false | aucun fournisseur cible ne le fait | rejeté |
| 10 | Un `id` neuf à chaque fragment d'un même appel couperait l'appel | medium | règle « `id` différent ⇒ nouvel appel » | patch : un nouvel appel exige aussi `function.name` ; cas ajouté à `test_fragments_of_one_call_stay_one_call` |
| 11 | Texte d'Ollama tronqué à 200 caractères avant la recherche de l'architecture | low | message réel ≈ 140 caractères | rejeté |
| 12 | Flux qui reste ouvert sans événement : pas d'indicateur | low | un serveur vivant envoie un keep-alive ; l'indicateur dit une connexion perdue | rejeté |
| 13 | Serveur local jamais comparé : non testé | medium | aucun test | patch : `test_the_local_server_is_never_compared` |
| 14 | Spec : `documentation_weight(tools)` absente | low | seul `tool_weight` existait | patch : fonction ajoutée et utilisée |
| 15 | Tests nouveaux qui passent sans le correctif (fragments, briques, autre 500) | false | ils gardent des lignes de la matrice (non-régression), pas un correctif ; le correctif E048 est gardé par le test des appels parallèles | rejeté |
| 16 | Instantanés versionnés jamais lus sans doublure | medium | fixture qui remplace `snapshot_path` partout | patch : `test_the_versioned_snapshots_are_read` |
| 17 | Avertissement effacé après échec du serveur : non testé | low | aucun test | patch : `test_a_server_that_fails_loses_its_warning` |
| 18 | `stream_lost` jamais lancé ; `.brick-drift` sans E2E ; priorité sur le texte de chargement non couverte | medium | règle de la nuit | defer (entrée ajoutée) |
| 19 | Variante « erreur dans le flux » non testée | low | seul le 500 était joué | patch : `test_an_error_inside_ollamas_stream_is_read_too` |
| 20 | Message « trop ancienne » affirmé alors que la regex couvre d'autres cas | medium | GGUF non conversationnel possible | patch : « sans doute trop ancienne » (fr, en, de) |
| 21 | Moitié « sans index » du test des appels parallèles passe sans le correctif | low | clé = `id` | rejeté : garde la ligne « ou sans index » de la matrice |
| 22 | `_sub_contributions` perd en silence une brique qui déclarerait `sub` | low | aucune vérification | patch : `test_every_brick_declaring_sub_says_what_it_brings` |
| 23 | Indicateur absent des pages LLM nu, RAG, MCP ; saisie active pendant la coupure | low | E003 ne nomme que l'atelier | defer (entrée ajoutée) |
| 24 | E048 et E003 fermés avant leur vérification réelle | false | le contrat d'intention demande « vérifié avec doublure, réel en story 7 » ; la fermeture d'E003 nomme le contrôle à jouer | rejeté |
| 25 | Listes d'outils ajoutés non tronquées ; poids toujours affiché | low | cas improbable ; le poids est l'information principale d'AD-9 | rejeté |
| 26 | README et `wavestack.toml` disent « sous le serveur » | low | rendu au niveau de la carte | patch : « en le nommant », « qui nomme le serveur » |
