---
title: "Latence CPU : préremplissage du premier tour et documentation lazy en résultat d'outil"
type: 'feature'
created: '2026-10-01'
status: 'done'
route: 'dispatch'
baseline_revision: 'd7ff58b7f30061e7c16462096c36a69bab41488b'
baseline_commit: 'd7ff58b7f30061e7c16462096c36a69bab41488b'
review_loop_iteration: 0
followup_review_recommended: false
context:
  - '{project-root}/_bmad-output/specs/spec-restes-differes-2026-10/SPEC.md'
  - '{project-root}/_bmad-output/implementation-artifacts/spec-lot-a-cache-entre-les-tours.md'
warnings: []
deferred: []
---

<intent-contract>

## Intent

**Problem:** Sur le PC cible (Qwen3.5-2B, CPU, ≈ 30 tokens/s en lecture), le premier tour d'un scénario chargé attend 46 à 56 s avant le premier token (E122, NFR-1 vise 30 s), alors que l'animateur lit la consigne pendant ce temps. En lazy loading, charger une documentation réécrit la définition des outils : le tour suivant relit tout le contexte (≈ 40 s, `prefix_not_reused{cause: system}`, E121) (CAP-4).

**Approach:** (1) Au lancement d'un scénario en mode local, évaluer dans le moteur la partie du contexte du premier tour qui ne dépend pas du message (message système, outils, mémoire), pour que le premier appel la réutilise. (2) **Si Anaël valide D16**, placer la documentation chargée par `load_tool_doc` dans l'historique, comme résultat d'outil (append-only), au lieu de la définition de l'outil dans `tools`.

## Boundaries & Constraints

**Always:**
- Entrées fermées : **E122** ; **E121** seulement si D16 = oui (sinon, l'entrée reste ouverte avec la décision).
- Préremplissage : mode local et moteur en processus seulement ; démarre après `scenario_changed`, s'abandonne dès qu'un tour, un chargement de modèle, un réglage de brique ou un autre scénario arrive (le moteur est exclusif) ; ne change ni la jauge, ni le contexte envoyé, ni les événements du tour. Un événement le trace (début, fin ou abandon, tokens évalués, durée), visible dans le journal, pas dans le rail du tour.
- Le premier appel du premier tour réutilise les ids préremplis (contrôle de `spec-lot-a` : aucun `prefix_not_reused`) ; `evaluated_tokens` le montre.
- Si D16 = oui : AD-25 et AD-4 amendés dans ARCHITECTURE-SPINE ; le résultat de `load_tool_doc` porte la documentation complète de l'outil (segment `tool_catalog` attribué au serveur MCP) ; l'outil est appelable dans le même tour et les suivants ; « Vider la conversation » et le rejeu suivent la branche (AD-17) ; Contexte LLM et la jauge le montrent comme résultat d'outil ; EXPERIENCE.md et la carte de la brique MCP disent où va la documentation.
- Tests avec le faux moteur (ids, cache) ; mesure réelle renvoyée à la story 7 (`prompt_ms` du premier tour de `mcp_lazy` et `subagent`, et du tour qui suit un `load_tool_doc`, avant et après).

**Never:**
- Préremplir en mode cloud ou serveur local, ou bloquer une action de l'utilisateur en attendant le préremplissage.
- Changer ce que le modèle reçoit au premier tour (même texte, mêmes ids).
- Implémenter E121 sans la validation de D16.

## I/O & Edge-Case Matrix

| Scenario | Input / State | Expected Output / Behavior | Error Handling |
|----------|--------------|---------------------------|----------------|
| Préremplissage fini | scénario lancé, attente, premier message | premier appel réutilise le préfixe, `evaluated_tokens` réduit | aucune |
| Message pendant le préremplissage | message envoyé à mi-chemin | préremplissage abandonné, tour normal sans attente notable | abandon tracé |
| Mode cloud | modèle cloud actif | aucun préremplissage | aucune |
| D16, documentation chargée | `load_tool_doc(local__define_term)` puis tour suivant | pas de `prefix_not_reused{cause: system}` | aucune |

## Décisions (D16 = oui, tranché par Anaël le 2026-10-01 ; détails validés en mode nuit)

- **D16-a.** En mode local et lazy loading, la variable `tools` ne dépend plus des documentations chargées : `load_tool_doc` garde la ligne d'un outil déjà chargé dans son catalogue (sinon le message système changerait), et reste dans `tools` tant qu'un outil MCP existe. En mode chat, rien ne change (AD-25 : le fournisseur refuse un appel à un outil absent de `tools`).
- **D16-b.** Dans le tour, la réponse de `load_tool_doc` est un résultat d'outil `tool_catalog` attribué au serveur (déjà le cas) ; aux tours suivants, l'historique la rend **en entier**, typée `history` comme tout résultat d'outil passé (règle d'AD-4 inchangée) ; le talon ne sert plus qu'au mode chat. Avec la mémoire courte éteinte, la documentation n'est pas relue : l'outil n'est alors pas tenu pour documenté, et `load_tool_doc` rend la documentation de nouveau au lieu de « déjà chargée ».
- **D16-c.** Un appel MCP forcé en lazy loading (lot K) n'ajoute sa définition à `tools` et ne marque la documentation chargée qu'en mode chat ; en mode local, l'appel forcé est rendu avec son résultat, l'outil reste à charger (le modèle peut le demander par `load_tool_doc`).
- **E122-a.** Un préremplissage périmé (réglage changé entre le lancement et le premier message) n'émet aucun `prefix_not_reused` nouveau : le contrôle du premier tour reste celui du lot A ; seul `evaluated_tokens` montre ce que le moteur a relu. Sans conversation antérieure, `_main_cache` reste `None` ; après une conversation antérieure (où le lot A émettait déjà `reset`), `_main_cache` suit le cache réel du moteur à la fin du préremplissage, pour que le premier appel qui le prolonge n'émette pas un `reset` faux (amendement de revue, 2026-10-02).
- **E122-b.** Le port moteur gagne `prefill(ids, cancel) -> int | None` : évalue les ids dans le cache par lots (`PREFILL_BATCH = 128`), en réutilisant le préfixe déjà en cache, s'arrête entre deux lots dès que `cancel` l'exige (la partie évaluée reste utile) ; `None` pour un moteur qui ne sait pas (serveurs, cloud). Le jeton d'annulation voit tout départ d'`idle` (tour, chargement, ateliers) et tout changement de réglage (le rafraîchissement de l'aperçu).
- **E122-c.** Le préremplissage attend la fin des connexions MCP que le scénario ouvre (sinon la variable `tools` serait incomplète), et ne vide pas la conversation ; « Vider la conversation » ne préremplit pas (hors périmètre, listé dans le rapport).

</intent-contract>

## Code Map

- `src/wavestack/session/app_session.py` :
  - `TurnState` (l.492 ; `tools`, `loadable`), `_with_loaded` (l.546, mode chat), `build_turn_state` (l.3622 ; lazy l.3636-3642), `_step_messages` (l.3696 ; talon l.3730), `_messages` (l.3886), `_tool_definitions` (l.3959), `_doc_catalog` (l.3985), `_render` (l.4044 ; `_render(state, "", None)` sans événement, comme `_emit_preview` l.4163).
  - `_start` (l.4229 : `state = "turn"` sous le verrou puis `_emit_state`), `_run_turn` (l.6023), `_turn` (l.6106 : `check` l.6231, `_call_model(..., state.tools + tuple(loaded_in_turn), ...)` l.6176, `_with_loaded(state, defined)` l.6129), `_consume_armed` (l.6776 ; lot K l.6818-6822), `_armed_unavailable` (l.6873 ; l.6921), `_apply_doc_loaded` (l.7076, `stub`), `_load_tool_doc` (l.4946, « déjà chargée » l.4951), `_turn_ctx` (l.6058, l'état du tour en cours).
  - Cache (lot A) : `_main_cache` (l.944), `_keep_cache` (l.7151), `_check_reuse` (l.7167 ; `cached is None → return`), `_engine_cached_ids` (l.630), `_evaluated` (l.640), `_call_model_local` (l.7328, `evaluated_tokens`).
  - Scénarios : `launch_scenario` (l.5641), `_reconfigure` (l.5667 ; `_cache_cause = "reset"` l.5683, `_emit_scenario` l.5694, connexions MCP l.5695-5698, aperçu l.5703), `_mcp_connect` (l.5136, `_mcp_state = ("not_contacted", None)` l.5142), `_mcp_apply` (l.5194, fin l.5237-5239), `_mcp_state` : `not_contacted | available | unavailable`.
  - Réglages de classe (a) : onze `self._executor.submit(self._emit_preview)` (l.4313, 4329, 4345, 4360, 4491, 5087, 5134, 5366, 5383, 5489, 5795) ; `_set_state` (l.1016), départs d'`idle` par affectation directe (l.1790, 1815, 2170, 2440, 4247, 8113, 8673, 9068).
  - `_SYSTEM_KINDS` / `_CONVERSATION_KINDS` (l.341-353), `_t` (l.1571), `_n` (l.1567), `_executor` (un seul thread, AD-24).
- `src/wavestack/models/engine.py` -- port `Engine` (l.103 ; `cached_ids`, `snapshot`, `restore`, `last_evaluated`), `LlamaCppEngine` (l.260 ; `cached_ids` l.275 sur `input_ids[:n_tokens]`). llama-cpp-python 0.3.35 : `Llama.eval(tokens)` retire le KV au-delà de `n_tokens` puis décode par `n_batch` et met `_requires_eval = False` ; `generate` réutilise le plus long préfixe commun (`reuse_prefix`, `kv_cache_seq_rm`) et n'évalue que la suite.
- `src/wavestack/models/servers.py`, `src/wavestack/models/openai_chat.py` -- `cached_ids`/`snapshot` rendent `None` : y ajouter `prefill` → `None`.
- `src/wavestack/trace/catalog.py` -- `PAYLOAD_MODELS` (l.1321) ; modèles voisins `PrefixNotReusedPayload` (l.637), `ScenarioChangedPayload` (l.778).
- `src/wavestack/web/static/app.js` -- journal : `KIND_LABELS = section("main.log.kinds")` (l.6372), résumé par défaut `p.message_text` (l.6540) ; le rail ne prend que les genres listés (l.676-700 et `case`) : rien à faire pour que les nouveaux événements restent au journal.
- `content/ui.yaml` (`main.log.kinds`, l.656), `content/messages.yaml` (`session.prefix.causes.history` l.108 cite le talon ; `session.stubs` l.423 ; `session.mcp.*`), `content/bricks/mcp.yaml` (puce lazy loading, l.15-20) ; surcouches `content/i18n/{en,de}/...` mêmes clés (parité, `i18n-conventions.md`).
- `tests/fake_engine.py` -- `FakeEngine` (cache simulé l.57-62, `gate`, `complete` l.113) ; `booted_session`. `tests/test_turn_cache.py` (aides `run`, `of`, `exact`, `qwen_session`, `reused` ; `test_a_scenario_change_is_a_reset` l.335). `tests/test_mcp_lazy.py` (`lazy_session`, `load`, `definition_names`, `DEFINE`, `LOCAL` ; tests l.81, 184, 201, 218 encodent l'ancien comportement). `tests/test_forced.py:406` (lot K). `tests/test_mcp.py` (`mcp_session`, `enable`, `since`, `wait_for`, `web`/`McpWeb`). `tests/test_engine_cache.py` (tiny-llama synthétique de 42 Ko, sans marqueur `model`). `tests/test_scenarios.py` (`booted_session(FakeEngine())` sans boucle : aucun serveur contacté).
- `tools/e2e/run_e2e.py:2801` `s_mcp_lazy` -- deux prompts puis action forcée ; aucun contrôle n'affirme l'entrée de la documentation dans `tools` au tour suivant.
- `ARCHITECTURE-SPINE.md` -- AD-4 (historique l.170, emplacements l.177, ajout seul d'un tour à l'autre l.211), AD-25 (l.666-667). `EXPERIENCE.md` -- l.172 (journal), l.213 (lazy loading : documentation chargée). `deferred-work.md` -- E121 l.575-577, E122 l.579-581.

## Tasks & Acceptance

**Execution:**
- [x] `src/wavestack/models/engine.py` -- port : `prefill(ids, cancel) -> int | None` ; `LlamaCppEngine.prefill` : préfixe commun avec `input_ids[:n_tokens]`, `n_tokens` ramené à ce préfixe (`reset()` si nul), puis `eval` par lots de `PREFILL_BATCH`, `cancel.cancelled` testé entre deux lots ; rend le nombre d'ids évalués -- E122-b.
- [x] `src/wavestack/models/servers.py`, `src/wavestack/models/openai_chat.py` -- `prefill` rend `None` -- port complet.
- [x] `src/wavestack/trace/catalog.py` -- `ContextPrefillStartedPayload{tokens, message_text}` et `ContextPrefillEndedPayload{status: completed|abandoned|error, tokens, evaluated_tokens, duration_ms, message_text}` ; enregistrés `context_prefill_started` / `context_prefill_ended` -- journal.
- [x] `src/wavestack/session/app_session.py` -- E122 : `_prefill_cancel`, `_prefill_pending` ; `_reconfigure` abandonne le préremplissage en cours, puis, pour un scénario, note la demande et appelle `_maybe_prefill()` ; `_mcp_apply` l'appelle aussi ; `_maybe_prefill` attend qu'aucun serveur ne soit `not_contacted`, puis soumet `_run_prefill(scenario_id, token)` au worker ; `_run_prefill` : conditions (local, `_active.kind == "file"`, moteur avec `prefill`, `idle`, scénario toujours actif, jeton vif), `build_turn_state()` rendu avec un message de remplacement non vide, ids dont les octets finissent avant le premier octet du dernier segment `user_message`, moins le dernier (frontière de tokenisation), événements début et fin, aucune exception sortante (statut `error`) ; `_PrefillToken(CancelToken)` dont `cancelled` est vrai aussi hors `idle` ; `_refresh_preview()` = abandon + aperçu, à la place des onze `submit(self._emit_preview)` ; `_main_cache` et `_cache_cause` inchangés (E122-a).
- [x] `src/wavestack/session/app_session.py` -- D16 : `TurnState.documented` ; `build_turn_state` en lazy et mode local : `loadable` = tous les outils MCP, `tools += [LOAD_TOOL_DOC]`, `documented` = chargés si `short_memory` effective ; mode chat inchangé ; `_callable(state, loaded_in_turn)` = `tools + documented + loaded_in_turn` pour `check` et `_call_model` ; `_armed_unavailable` : `doc_loaded` aussi pour `documented` ; `_consume_armed` : lot K en mode chat seulement (D16-c) ; `_step_messages` : en local, un pas `tool_catalog` passé garde son contenu (D16-b) ; `_load_tool_doc` : « déjà chargée » seulement si la documentation est lue (chat, ou local avec `short_memory` effective, via `_turn_ctx`), sinon la documentation de nouveau.
- [x] `tests/fake_engine.py` -- `prefill(ids, cancel)` par lots (`prefill_batch`, `prefill_gate` : attend après le premier lot), `prefills` (ids demandés) et `prefilled` (évalués) ; aucune entrée dans `evaluated` (indices des tests inchangés).
- [x] `content/messages.yaml` + `i18n/{en,de}` -- `session.prefill.{started, completed, abandoned, error}` ; `session.prefix.causes.history` sans « documentation remplacée par son talon ». `content/ui.yaml` + `i18n/{en,de}` -- `main.log.kinds.context_prefill_started/ended`. `content/bricks/mcp.yaml` + `i18n/{en,de}` -- la puce lazy loading dit où va la documentation (historique en local, `tools` au tour suivant en cloud).
- [x] `tests/test_turn_cache.py` -- section préremplissage : scénario lancé → `context_prefill_started/ended{completed}`, premier appel qui prolonge le préfixe (`engine.calls[0][:n] == prefix`), `evaluated_tokens` = nouveaux ids, aucun `prefix_not_reused`, prompt et `used` du premier appel identiques à ceux d'un moteur sans `prefill` ; message pendant le préremplissage (`prefill_gate`) → `abandoned`, partie évaluée réutilisée ; réglage de brique pendant → `abandoned` ; moteur sans `prefill` → aucun événement ; scénario `hooks` (injection H3 avant le message) → le préfixe tient ; `mcp_lazy` avec serveur local et faux data.gouv.fr → le préremplissage commence après les `mcp_connect_ended` et son préfixe porte les lignes du catalogue.
- [x] `tests/test_cloud.py` -- un lancement de scénario en cloud n'émet aucun `context_prefill_*`.
- [x] `tests/test_engine_cache.py` -- tiny-llama : `prefill` puis `complete` qui le prolonge → `last_evaluated` = nouveaux ids ; `prefill` annulé après le premier lot → partie évaluée, puis `complete` n'évalue que la suite.
- [x] `tests/test_mcp_lazy.py` -- adapter l.81 (tour suivant : `definition_names == ["load_tool_doc"]`, documentation dans `history`, lignes du catalogue intactes, aucun `prefix_not_reused`, appel de l'outil accepté), l.201 (tout chargé : le méta-outil reste ; vidage → `documented == ()`), l.218 (`documented` suit le serveur) ; nouveaux : mémoire courte éteinte → `documented == ()` et la documentation rendue de nouveau ; mode chat inchangé (tests existants l.351, 398).
- [x] `tests/test_forced.py:406` -- en local : `definition_names == ["load_tool_doc"]`, ligne de `DEFINE` toujours offerte, résultat en `tool_result`, `DEFINE not in _loaded_docs`.
- [x] `tools/e2e/run_e2e.py` `s_mcp_lazy` -- après le second prompt : aucun `prefix_not_reused` de cause `system` (écrit, non lancé).
- [x] `ARCHITECTURE-SPINE.md` -- AD-4 : historique (la documentation chargée reste en entier en local, talon en chat), emplacements, paragraphe « Préremplissage du premier tour » ; AD-25 : lazy loading et tours suivants réécrits (D16-a, b, c). `EXPERIENCE.md` -- l.213 et ligne du journal. `deferred-work.md` -- E121 et E122 fermées (`closed:`), mesure PC vers la story 7.

**Acceptance Criteria:**
- Given un scénario lancé en mode local avec le faux moteur, when le premier message part après le préremplissage, then `model_call_ended.evaluated_tokens` du premier appel vaut le nombre d'ids qui suivent le préfixe prérempli, aucun `prefix_not_reused` n'est émis, et le prompt envoyé est identique à celui d'une session sans préremplissage.
- Given un préremplissage en cours, when un message, un réglage ou un autre scénario arrive, then `context_prefill_ended{status: abandoned}` est émis et le tour (ou l'aperçu) suit sans attendre la fin du préremplissage.
- Given la brique MCP en lazy loading et le mode local, when `load_tool_doc` charge une documentation puis un tour suit, then le premier appel de ce tour n'émet aucun `prefix_not_reused`, `tools` est identique, la documentation est lue dans l'historique et l'outil est appelable.
- Given la jauge de chaque appel, when un tour s'exécute, then la somme des segments vaut le total et aucun `harness_error` n'est émis.

## Implementation Notes

- 2026-10-02 -- implémentation par sous-agent (dispatch), vérifiée sur le diff complet depuis `d7ff58b`. Écarts et constats :
  - `LlamaCppEngine.prefill` ramène le cache au préfixe commun par `kv_cache_seq_rm` quand llama.cpp l'accepte (comme `generate`), sinon `reset()` (modèle hybride) ; et appelle `llama_synchronize` en `finally` : sans cela, llama.cpp comptait les tokens du préremplissage dans le `n_p_eval` du `complete` suivant (`last_evaluated` 46 au lieu de 20 sur tiny-llama).
  - Le statut `completed` / `abandoned` est décidé par la session en comparant `cached_ids()` aux ids demandés ; un moteur sans `cached_ids` (serveur) n'est pas prérempli.
  - Le test « injection H3 dans le préfixe » utilise le scénario `subagent` (le scénario `hooks` n'active que H1 et H2).
  - Fichiers concernés hors de la liste de vérification joués en plus : `test_global_memory`, `test_program`, `test_content_language`, `test_reasoning`, `test_rag_review`, `test_rag_rerank`, `test_trace_architecture`, `test_replay` (dont `test_a_documentation_loaded_in_the_origin_turn_is_unloaded_an_earlier_one_stays`, adapté à D16 : le rejeu suit la branche par `documented` et l'historique, pas par `tools`), `test_render_reference`, `test_e2e_fake_openai`.
- 2026-10-02 -- revue (trois relecteurs) : 20 constats, 15 patchs appliqués par le sous-agent d'implémentation (journal de triage ci-dessous), 5 rejetés ; E122-a amendée (`_main_cache` suit le cache du moteur après une conversation antérieure). Vérification finale : `ruff check` et `ruff format --check` sans écart ; pytest en trois lots : 114 (`test_turn_cache`, `test_engine_cache`, `test_scenarios`, `test_mcp`, `test_mcp_lazy`, `test_mcp_lab`), 225 (`test_mcp_snapshot`, `test_forced`, `test_cloud`, `test_replay`, `test_global_memory`, `test_program`, `test_reasoning`), 3 495 + 3 sautés (`test_i18n`, `test_ui_texts`, `test_backend_messages`, `test_content_language`, `test_rag_review`, `test_rag_rerank`, `test_render_reference`, `test_e2e_fake_openai`, `test_trace_architecture`). Suite complète et E2E (`--only mcp_full mcp_lazy subagent sovereignty`) non lancées cette nuit ; mesure PC (`prompt_ms` avant et après) : story 7.

## Spec Change Log

- 2026-10-01 -- validé en mode nuit (Anaël absent, autorisation du 01/10 au soir) : spec conforme au SPEC (CAP-4, Assumptions), à D16 = oui et à AD-4 / AD-25 ; décisions D16-a à D16-c et E122-a à E122-c prises comme options les plus prudentes et réversibles (voir l'intention) ; approuvée et poursuivie dans la même session.
- 2026-10-02 -- validé en mode nuit (Anaël absent, autorisation du 01/10 au soir) : constat de revue « préremplissage terminé après une conversation antérieure → `prefix_not_reused{reset}` faux », en contradiction avec l'Always « aucun `prefix_not_reused` » ; E122-a (décision du mode nuit, pas d'Anaël) amendée : `_main_cache` suit le cache du moteur après le préremplissage quand une conversation a précédé, reste `None` sinon. État évité : un texte « le cache contient encore l'ancienne » alors que le moteur tient le préfixe prérempli. KEEP : le chemin `reset` sans préremplissage reste épinglé (`test_a_scenario_change_is_a_reset` sur un moteur sans `prefill`).
- 2026-10-02 -- confirmé par Anaël : détails D16-a à D16-c (ligne d'un outil chargé gardée au catalogue de `load_tool_doc`, appel MCP forcé en lazy défini dans `tools` seulement en mode chat) gardés tels quels.

## Review Triage Log

### 2026-10-02 — Review pass (blind-hunter 14, edge-case-hunter 8, verification-gap 3 ; doublons regroupés)
- verdicts: 20 constats distincts — high 0, medium 7, low 8, false 3, maybe-false 2
- findings:
  - `[medium]` `[patch]` Préremplissage terminé après une conversation antérieure : `_main_cache` garde l'ancienne conversation, le premier tour émet `prefix_not_reused{reset}` « le cache contient encore l'ancienne », faux (blind) — vérifié : `_reconfigure` ne vide pas `_main_cache`, `test_a_scenario_change_is_a_reset` suit ce chemin ; contredit l'Always « aucun prefix_not_reused » — après le préremplissage, `_main_cache` suit le cache du moteur quand il n'était pas `None` (E122-a amendée, mode nuit).
  - `[medium]` `[patch]` Préfixe vide : `prefill([])` remet le cache à zéro et trace un préremplissage de 0 token ; contexte en débordement : `eval` échouerait (blind, edge) — vérifié dans `_run_prefill` et `LlamaCppEngine.prefill` — sortie silencieuse quand `ids` est vide ou que la jauge dit `overflow`.
  - `[medium]` `[patch]` `context_prefill_ended{error}` orphelin si le rendu échoue avant `started` (blind, edge) — vérifié : le rendu est dans le `try` — préparation hors du `try`, retour silencieux en cas d'échec.
  - `[medium]` `[patch]` Message envoyé avant la fin d'une connexion MCP lente : `_mcp_apply` lance le préremplissage en pleine conversation, qui coupe ou vide le cache vivant (edge) — vérifié : `live` ne regarde pas l'historique — `_start` abandonne la demande ; `live` exige un historique vide.
  - `[medium]` `[patch]` Talon du mode chat plus épinglé par aucun test (verification-gap, pré-vérifié) — second tour ajouté au test chat de `test_mcp_lazy`.
  - `[medium]` `[patch]` Branche chat du lot K (`_consume_armed`) sans test (verification-gap, edge) — test chat ajouté dans `test_forced`.
  - `[medium]` `[patch]` `_load_tool_doc`, mémoire courte éteinte : un second chargement dans le même tour renvoie la documentation entière (blind, edge, verification-gap) — vérifié : `read` ignore ce que le tour a chargé — « déjà chargée » si chargé depuis le début du tour (`_last[4]`), test étendu.
  - `[low]` `[patch]` `assert isinstance` effacé sous `-O`, `str(exc)` vide dans le texte d'erreur (blind) — `if` explicite, repli sur le nom du type.
  - `[low]` `[patch]` `evaluated_tokens` à 0 en `error` alors que des lots sont en cache (edge) — préfixe commun avec le cache.
  - `[low]` `[patch]` `ContextPrefillStartedPayload` sans `phase_label` (AD-2) (blind) — ajouté, texte en trois langues.
  - `[low]` `[patch]` Cache déjà au-delà des ids demandés coupé pour rien (edge, déduit de BH1) — `prefill` rend 0 sans toucher le cache quand il commence par les ids.
  - `[low]` `[patch]` Lacunes de tests : statut `error`, sortie d'`idle` par un chargement, conversation antérieure (blind) — tests ajoutés ; RAG non testé : `[low]` `[reject]`, la frontière est éprouvée par l'injection H3 (même mécanisme : texte entre le gabarit et le message) et le lancement de `rag` charge un embedder.
  - `[low]` `[patch]` Textes : `abandoned` n'énumère pas chargement ni atelier ; en « read again » ; carte MCP « au tour suivant » pour le mode chat alors qu'AD-25 dit « dès l'appel suivant » (blind) — trois langues corrigées.
  - `[low]` `[patch]` AD-4 : parenthèse sur le talon en mode chat trompeuse (le contrôle est local) ; cas non préremplis sous-listés (réinitialisation, changement de modèle, premier tour sans scénario) (blind) — spine et `deferred-work.md` complétés.
  - `[low]` `[reject]` Aucune preuve E2E du préremplissage (blind) — la pile E2E tourne sur un faux fournisseur OpenAI (mode chat) sans moteur en processus : impossible là ; la preuve réelle est la mesure PC de la story 7 ; le contrôle D16 écrit le dit dans son commentaire.
  - `[false]` `[reject]` `_prefix_ids` pourrait se déduire de `sum(s.tokens)` (blind) — non équivalent : les tokens d'un segment sont ceux dont le premier octet y tombe, un token à cheval serait compté ; la marge « moins un » tient avec l'algorithme actuel ; coût : ~1 600 appels ctypes par lancement, négligeable devant 50 s d'évaluation.
  - `[false]` `[reject]` `_reconfigure` abandonne le préremplissage avant le contrôle `idle` : un lancement refusé perd la demande (edge) — un refus n'arrive qu'hors `idle`, où le jeton est déjà annulé par l'état et où un tour en cours rend la demande caduque.
  - `[false]` `[reject]` La portée du contrôle `prefix_not_reused` est locale : la remarque de la spec « tests existants l.351 » visait un test local (verification-gap, note) — corrigé par le test chat ajouté.
  - `[maybe-false]` `[reject]` Connexion MCP qui ne rend jamais compte : demande en attente jusqu'au scénario suivant (blind) — `_mcp_apply` est toujours soumis par le rappel de la future ; désactiver le serveur passe par `_refresh_preview`, qui vide la demande ; si vrai : low (aucun préremplissage, pas de dégât).
  - `[maybe-false]` `[reject]` Lecture de `session.state` hors verrou dans `_PrefillToken.cancelled` (rapport d'implémentation) — lecture d'une chaîne, à la manière des autres lectures non verrouillées ; si vrai : low (un lot de plus avant l'abandon).

## Design Notes

- Frontière du préfixe : les ids sont ceux du rendu réel (tokenisation du prompt entier) coupés au premier octet du message, moins le dernier token : un token qui chevaucherait la frontière (« \n » + début du message) n'est jamais prérempli. Le premier appel prolonge donc toujours le préfixe tant que la configuration n'a pas changé.
- Le préremplissage tourne sur le thread de travail (AD-24) : un tour envoyé pendant ce temps attend au plus un lot (128 tokens, ≈ 4 s sur le PC cible) puis réutilise ce qui est déjà évalué ; rien n'est perdu, et l'aperçu du scénario est émis avant lui.
- D16 : la documentation chargée pèse désormais dans « Mémoire courte » aux tours suivants, comme tout résultat d'outil passé ; la carte MCP garde son poids de catalogue (lignes et définition de `load_tool_doc`).

## Verification

**Commands:**
- `uv run ruff check .` et `uv run ruff format --check .` -- expected: aucun écart.
- `uv run pytest -q tests/test_turn_cache.py tests/test_engine_cache.py tests/test_scenarios.py tests/test_mcp.py tests/test_mcp_lazy.py tests/test_mcp_lab.py tests/test_mcp_snapshot.py tests/test_forced.py tests/test_cloud.py tests/test_i18n.py tests/test_ui_texts.py tests/test_backend_messages.py`, en quarts -- expected: tout passe.
- E2E (avec l'accord d'Anaël) : `--only mcp_full mcp_lazy subagent sovereignty` -- expected: 0 échec.
