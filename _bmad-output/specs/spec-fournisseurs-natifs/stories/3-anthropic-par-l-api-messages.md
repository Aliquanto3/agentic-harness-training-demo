---
title: 'Fournisseurs natifs (3/5) : Anthropic par l''API Messages'
type: 'feature'
created: '2026-10-03'
status: 'done'
baseline_commit: '9357d502fae2c4b03080b1dce5082f148266edc8'
route: 'dispatch'
review_loop_iteration: 0
context:
  - '{project-root}/_bmad-output/specs/spec-fournisseurs-natifs/SPEC.md'
  - '{project-root}/_bmad-output/specs/spec-fournisseurs-natifs/formats-natifs.md'
  - '{project-root}/_bmad-output/specs/spec-fournisseurs-natifs/stories/1-champ-api-socle-commun-et-traducteurs.md'
---

<frozen-after-approval reason="human-owned intent — do not modify unless human renegotiates">

## Intent

**Problem:** Claude n'est pas joignable dans WaveStack : sa couche compatible OpenAI ne renvoie pas la réflexion, et les briques Outils, MCP, Sous-agent et Raisonnement exigent l'API Messages native, avec ses blocs `thinking` signés à renvoyer tels quels.

**Approach:** Un adaptateur `anthropic_messages` (engine + traducteur du pivot, branchés sur les registres de la story 1) écrit le corps Messages, lit le flux SSE, renvoie verbatim les blocs de réflexion reçus et trace comme événement de journal chaque bloc qu'Anthropic jette (`input_transformations`, CAP-5). Deux entrées `claude_haiku` (`claude-haiku-4-5`) et `claude_sonnet` (`claude-sonnet-5`) rejoignent `wavestack.toml`. Les deux questions ouvertes de SPEC.md (appel d'outil fabriqué avec réflexion active ; Sonnet 5 sans réflexion) sont tranchées par quelques appels réels, plafond 5 $, et leurs résultats consignés (CAP-2).

## Boundaries & Constraints

**Always:**
- Corps conforme à la section « Anthropic » de `formats-natifs.md`, écrit par `context` seul (traducteur dans `TRANSLATORS`) ; corps envoyé = `context_rendered.body` = `outbound_request.body` (test sur le faux serveur). `CloudModel.api` accepte `anthropic_messages` ; `ENGINES`, `TRANSLATORS` et le `Literal` restent en phase (test de la story 1).
- En-têtes : `x-api-key` (`auth_header = { name = "x-api-key", scheme = "" }`), `anthropic-version: 2023-06-01` et `anthropic-beta: thinking-binding-controls-2026-08-01` en `extra_headers`. `block_binding = { prefix_mismatch_behavior = "drop_block" }` se déclare dans l'objet `thinking` de `reasoning.on` (documentation relue le 2026-10-03 : le champ vit sous `thinking`) ; s'il est refusé avec `{type: "disabled"}`, il ne figure que dans `on`.
- Renvoi verbatim (`resend = true`, `CloudReasoning.format = "thinking_blocks"`) : les blocs `thinking` (texte reçu + `signature`) et `redacted_thinking` (`data`) d'une réponse repartent en tête de son message assistant, dans l'ordre reçu, au seul modèle qui les a produits (même règle que `extra_content`, `extra_for`). Signatures et `data` masqués dans les événements seulement (AD-15).
- Usage au format pivot (contrat de la story 2) : `prompt_tokens = input_tokens + cache_read_input_tokens + cache_creation_input_tokens` ; `prompt_tokens_details = {cached_tokens: cache_read, cache_write_tokens: cache_creation}` ; `completion_tokens` = dernier `output_tokens` de `message_delta` (cumulatif, réflexion comprise).
- `input_transformations` (lu dans `message.input_transformations` de `message_start`) : chaque entrée `thinking_dropped` émet un événement de journal `reasoning_dropped` `{path, reason, message_text}` ; `message_text` dit, dans la langue de la séance, que la réflexion d'un tour précédent a été jetée par le fournisseur et pourquoi (`prefix_binding_mismatch` : historique réécrit par le harnais — fenêtre, troncature, compression, mémoire, brique changée ; `model_binding_mismatch` : produite par un autre modèle ; `organization_binding_mismatch` : autre organisation). Raisons et types inconnus ignorés. Affichage dans le journal sur le modèle de `reasoning_cut` (catalogue, `app.js`, libellés `content/ui.yaml` fr/en/de).
- Fins : `end_turn`, `tool_use`, `stop_sequence` → `stop` ; `max_tokens` → `length` ; `refusal` → `ProviderError` expliqué, avec la catégorie de `stop_details` si présente ; `pause_turn`, `model_context_window_exceeded` et toute autre valeur → `ProviderError` « arrêté » (AD-16). Événement `error` (dont `overloaded_error`) → `ProviderError`. HTTP 529 suit les 5xx ; 429 avec `retry-after` suit la règle commune. `PUBLIC_RESPONSE_PREFIXES` gagne `anthropic-ratelimit-`. Le 400 « prompt is too long » est reconnu comme dépassement de contexte.
- Traduction : `system` = messages système joints par « \n\n » ; blocs `text` vides omis ; `tool_use.input` = objet analysé de `arguments` ; messages `tool` consécutifs → un seul `user` à blocs `tool_result` (contenu chaîne) ; outils `{name, description, input_schema}`. Échantillonnage de « LLM nu » : envoyé seulement si l'entrée le déclare ET que la réflexion est éteinte (Anthropic refuse `temperature`/`top_p` avec la réflexion) ; sinon la trace d'échantillonnage le note (`note_text`).
- Entrées (prix relevés le 2026-10-03, à revérifier à l'écriture, `checked` à la date relue) :
  - `claude_haiku` : `claude-haiku-4-5`, contexte 200 000, prix 1 / 5, cache lu 0,10, écrit 1,25 ; `on = {thinking: {type: "enabled", budget_tokens: 1024, block_binding…}}`, `off = {thinking: {type: "disabled"}}` ; `sampling = ["temperature", "top_p"]`.
  - `claude_sonnet` : `claude-sonnet-5`, contexte 1 000 000, prix 2 / 10, cache lu 0,20, écrit 2,50 ; `on = {thinking: {type: "adaptive", display: "summarized", block_binding…}}`, `off = {thinking: {type: "disabled"}}` ; `sampling = []`.
  - Communs : `provider = "Anthropic"`, `base_url = "https://api.anthropic.com/v1"`, `tools = true`, `key_env = "ANTHROPIC_API_KEY"`, `impacts = {provider = "anthropic", model = <id>}` (EcoLogits 0.11.2 connaît les deux, vérifié), `hosting_text`, `training`, `notes_text` relus sur les conditions commerciales et la page de résidence des données d'Anthropic (relevé du 2026-10-03 : pas d'entraînement sur les données d'API, suppression sous 30 jours, inférence « global » par défaut ou « us », pas de résidence UE).
- Mesures réelles (clé `ANTHROPIC_API_KEY` fournie par Anaël, jamais affichée ni journalisée ; plafond de séance 5 $ ; une dizaine d'appels Haiku et Sonnet au plus) : (1) appel d'outil fabriqué par le harnais (action forcée) avec réflexion active, sur Haiku (réflexion manuelle) et Sonnet (adaptative) ; (2) Sonnet 5 réflexion éteinte : appels d'outils natifs ou écrits en texte ; (3) `block_binding` accepté avec `{type: "disabled"}` et par les deux modèles ; (4) `display: "summarized"` accepté par Sonnet 5. Résultats dans `_bmad-output/implementation-artifacts/mesures-anthropic-2026-10.md` (requête sans clé, statut, extrait de réponse, coût) et dans les notes d'implémentation.
- Parades si les mesures l'exigent : (1) refusé → pour l'appel qui suit une action forcée, réflexion éteinte (paramètres `off`) et note au journal ; (2) appels en texte → `off` de Sonnet devient une réflexion adaptative à faible effort, consignée ; (3) refusé → `block_binding` seulement dans `on`.

**Never:**
- Pas de SDK, pas de `cache_control`, pas de `count_tokens`, pas d'outils serveur, pas d'Opus 5.5 actif (commentaire seulement), pas de relance automatique.
- Ne pas changer les corps `openai_chat` (empreintes de la story 1).

## I/O & Edge-Case Matrix

| Scenario | Input / State | Expected Output / Behavior | Error Handling |
|----------|--------------|---------------------------|----------------|
| Texte | Flux `text_delta` | Canal `text`, fin `stop`, usage converti | N/A |
| Réflexion | `thinking_delta` puis `signature_delta`, puis texte | Canal `reasoning` ; bloc gardé (signature verbatim dans le corps suivant, masquée dans `model_call_ended`) | N/A |
| Outils parallèles | Deux blocs `tool_use` + `input_json_delta` | Deux appels dans l'ordre ; réponses en un seul `user` à deux `tool_result` | N/A |
| Refus | `stop_reason: refusal`, `stop_details` | `harness_error` expliqué, catégorie citée | `ProviderError` |
| Surcharge | `event: error` `overloaded_error` après un 200 ; ou HTTP 529 | `harness_error` (fournisseur indisponible) | `ProviderError` |
| Quota | HTTP 429 `retry-after: 7` | Indication « attendre 7 s » | `ProviderError` |
| Réflexion jetée | `message_start` avec `input_transformations` `thinking_dropped` / `prefix_binding_mismatch` | Événement `reasoning_dropped`, message en fr, en, de | N/A |
| Cache | Usage `input 100`, `cache_read 800`, `cache_creation 100` | `prompt_tokens = 1000`, coût selon la story 2 | N/A |

</frozen-after-approval>

## Code Map

- `src/wavestack/models/cloud_base.py` -- `CloudEngine` (en-têtes, URL `base_url + endpoint`, `_refused`, `_error`, `_text`), `ChatEnd` (ajouter les blocs de réflexion natifs, verbatim), `run_call` (masquage par `traced` : y masquer aussi les blocs), `_CONTEXT_WORDS`.
- `src/wavestack/models/openai_chat.py` -- modèle d'un `_read` SSE ; nouveau `src/wavestack/models/anthropic_messages.py` à côté.
- `src/wavestack/models/cloud_api.py` `ENGINES` ; `src/wavestack/context/render.py` `TRANSLATORS` (signature `(model, messages, tools, tail)`, chaque texte du pivot gardé en chaîne JSON ; `tool_use.input` : analyser `arguments` sans les sentinelles).
- `src/wavestack/config.py` -- `CloudModel.api` (`Literal`), `CloudReasoning.format`, `PUBLIC_RESPONSE_PREFIXES`.
- `src/wavestack/session/app_session.py` -- `_ModelOutput.extras`/`extra_for` (l. ~449) et `_assistant_step` (l. ~5078) : modèle pour garder les blocs par sortie et ne les rendre qu'à leur entrée ; `_assistant_message` (l. ~3845) : forme du raisonnement selon `resend` (ajouter `thinking_blocks`) ; `_cloud_call` (l. ~7905-7965) : lecture de `call.calls`/`extras` ; actions forcées (l. ~7076, `tool_call_extra`) pour la parade (1).
- `src/wavestack/trace/catalog.py` (`ReasoningCutPayload`, l. ~365 ; table des événements l. ~1358), `src/wavestack/web/static/app.js` (`reasoning_cut` l. ~631, ~700, ~831, ~5461), `content/ui.yaml` (+ `content/i18n/{en,de}/ui.yaml`) -- événement `reasoning_dropped`.
- `content/messages.yaml` (+ en, de) -- textes `models.openai_chat.*` (refus, arrêt) et de `reasoning_dropped`.
- `wavestack.toml` -- entrées sur le modèle de `gemini` (l. ~365), commentaire Opus 5.5.
- `tests/test_e2e_fake_openai.py`, `tests/test_cloud_api.py` -- modèles de faux serveur SSE et du test « corps envoyé = tracé ».

## Tasks & Acceptance

**Execution:**
- [x] `src/wavestack/config.py` -- `api` accepte `anthropic_messages` ; `format` accepte `thinking_blocks` ; préfixe `anthropic-ratelimit-`.
- [x] `src/wavestack/models/anthropic_messages.py` -- engine (`_read` du flux, usage pivot, fins, `input_transformations` remontés à la session) ; enregistrement dans `ENGINES`.
- [x] `src/wavestack/context/render.py` -- traducteur `anthropic_messages` ; `src/wavestack/cloud.py` `chat_fields` si besoin (échantillonnage seulement réflexion éteinte).
- [x] `src/wavestack/models/cloud_base.py`, `src/wavestack/session/app_session.py` -- blocs de réflexion portés de `ChatEnd` à l'historique et renvoyés à leur seule entrée ; émission de `reasoning_dropped`.
- [x] `src/wavestack/trace/catalog.py`, `src/wavestack/web/static/app.js`, `content/ui.yaml`, `content/messages.yaml` et leurs traductions en, de -- événement et textes.
- [x] `wavestack.toml`, `README.md` -- entrées `claude_haiku` et `claude_sonnet`, Opus 5.5 en commentaire ; clé `ANTHROPIC_API_KEY` et conditions dans le README.
- [x] `tests/test_anthropic_messages.py` -- faux serveur SSE : chaque ligne de la matrice, corps envoyé = tracé, renvoi verbatim au tour suivant et jamais à une autre entrée, `reasoning_dropped` en trois langues.
- [x] Mesures réelles (après accord d'Anaël et clé fournie) -- `mesures-anthropic-2026-10.md` ; parades appliquées si besoin.

**Acceptance Criteria:**
- Given le faux serveur, when un tour Outils puis un tour Raisonnement passent par `claude_haiku`, then ils aboutissent, la réflexion s'affiche au canal Raisonnement et les blocs `thinking` du premier appel repartent signés dans le second.
- Given la clé réelle, when on joue un tour Outils et un tour Raisonnement avec chaque modèle, then ils aboutissent et le coût total des mesures reste sous 1 $.
- Given `pytest` en quarts et les tranches E2E touchées par le journal, when on les joue, then tout est vert.

## Implementation Notes

- Clé réelle : `ANTHROPIC_API_KEY` est définie dans l'environnement UTILISATEUR de Windows (registre), pas dans celui des shells déjà ouverts. La lire par `powershell -NoProfile -Command "[Environment]::GetEnvironmentVariable('ANTHROPIC_API_KEY','User')"` (ou `winreg`) et la passer au seul processus de mesure, sans jamais l'afficher, la journaliser, l'écrire dans un fichier ni la commiter.
- Fait (2026-10-03) : adaptateur `models/anthropic_messages.py` (`AnthropicMessagesEngine`, `pivot_usage`) et traducteur `_anthropic_messages` de `context/render.py`, inscrits dans `ENGINES` et `TRANSLATORS`. Le traducteur garde chaque texte du pivot en chaîne JSON : `tool_use.input` est l'objet analysé de `arguments` sans les sentinelles, chaque valeur chaîne y étant réenveloppée des sentinelles de la partie `arguments` (le reste au gabarit) ; `_attribute` déduplique les parties d'un segment (une partie coupée en morceaux ne compte qu'une fois). Un message assistant sans texte ni appel (blocs de réflexion seuls compris) est omis.
- Blocs de réflexion : `ChatEnd.thinking_blocks` (verbatim, ordre reçu, `thinking` + `signature`, `redacted_thinking` + `data`) → `ChatCall.thinking_blocks` → `_ModelOutput.thinking` ; gardés dans le pas assistant (`thinking_blocks`, `thinking_for`) et, pour la réponse finale, dans `Exchange.thinking`/`thinking_for` (via `self._final_thinking`). `_assistant_message` les pose sous la clé pivot `thinking_blocks` seulement si `resend == "thinking_blocks"` et l'entrée est la leur ; le texte d'un bloc est attribué comme le raisonnement par `render.verbatim` quand l'étape 2 le laisse intact (blancs extérieurs au gabarit), sinon au gabarit. Signatures masquées seulement dans `raw_output` (mask_key, AD-15).
- `reasoning_dropped` est émis par `run_call` (`cloud_base.reasoning_dropped`), au même endroit pour le tour, le sous-agent, « LLM nu » et « Tester », dans la langue de la séance ; textes sous `models.openai_chat.reasoning_dropped.*` (règle de la story 1 : clés `models.openai_chat.*`), libellés `main.orch.rows.reasoning_dropped`, `main.log.kinds.reasoning_dropped`, `main.log.reasoning_dropped`, `main.log.drop_reasons.*`.
- Échantillonnage : `CloudModel.sampling_sent(reasoning)` (vide pour `anthropic_messages` qui réfléchit), lu par `chat_fields` et `_sampling_trace` (note `session.llm_lab.sampling.with_reasoning`).
- Prix revérifiés sur platform.claude.com le 2026-10-03 (Haiku 4.5 : 1 / 5, cache 0,10 / 1,25 ; Sonnet 5 : 2 / 10, cache 0,20 / 2,50, prix standard confirmé) ; résidence : inférence `global` par défaut ou `us`, géo de l'espace de travail `us` seule.
- Mesures réelles (12 requêtes, 10 facturées, 0,0258 $) : `_bmad-output/implementation-artifacts/mesures-anthropic-2026-10.md`. (1) appel fabriqué avec réflexion active accepté par les deux modèles (Haiku saute alors sa réflexion sur ce tour, sans erreur) : parade (1) inutile ; (2) Sonnet 5 éteint appelle ses outils nativement : parade (2) inutile ; (3) `block_binding` refusé avec `{type: "disabled"}` (400 « Extra inputs are not permitted ») : **parade (3) appliquée**, `block_binding` seulement dans `on` ; (4) `display: "summarized"` accepté. Tour Outils et tour Raisonnement réels aboutis avec chaque modèle, blocs signés renvoyés et acceptés.
- Hors Code Map, rendu nécessaire par les nouvelles entrées : éditeur « Claude (Anthropic) » dans `content/models/publishers.yaml` (+ en, de), sinon les deux modèles tombaient dans « Autres éditeurs » ; attentes mises à jour dans `tests/test_model_catalog.py`, `tests/test_cloud.py`, `tests/test_net_factory.py` (préfixe `anthropic-ratelimit-`) et le scénario E2E `model_catalog` (`tools/e2e/run_e2e.py`).
- Vérification : ruff vert ; pytest en quatre quarts vert (fichiers en échec corrigés puis rejoués, et une passe des 15 fichiers touchés : 3 845 verts) ; E2E `--only native_tools malformed provider_errors forced_native reasoning_locked subagent` (136/136) et `--only model_switch model_catalog llm_screen sovereignty backend_language` (149/150, l'échec était l'attente des groupes, `model_catalog` rejoué seul : 54/54).
- `tests/conftest.py` retire aussi `ANTHROPIC_API_KEY` de l'environnement des tests (la clé est posée dans l'environnement utilisateur).
- PC partagé de 16 Go : `pytest` en quarts (un à la fois, `run_in_background` puis attendre), E2E par tranches `--only` de 4 à 6 scénarios ; jamais deux suites à la fois, aucun modèle local en parallèle. Vider `%LOCALAPPDATA%\Temp\pytest-of-anael.yahi` à la fin. Avant tout E2E, vérifier qu'aucun serveur n'écoute sur le port 8420 (Anaël peut tester à la main).

## Spec Change Log

## Review Triage Log

Passe 1 (2026-10-03) : blind-hunter (BH), edge-case-hunter (EC), verification-gap (VG).

| # | Source | Constat | Verdict | Preuve | Route |
|---|---|---|---|---|---|
| 1 | BH, EC | Usage perdu quand le flux finit en erreur ou en refus après `message_start` : entrée facturée non comptée, plafond contourné | medium | `_read` lève avant `ChatEnd` ; `run_call` ne compte un coût que si une sortie est arrivée | patch |
| 2 | EC | `reasoning_dropped` non émis quand l'appel échoue après `message_start` | low | Émis seulement après `ChatEnd` ; même mécanisme que #1 | patch |
| 3 | EC | Un `usage` de `message_delta` à valeurs `null` écrase celles de `message_start` | low | `usage.update(...)` sans filtre (l. ~100) ; correction directe | patch |
| 4 | VG | Tests manquants : `redacted_thinking` dans le flux, `api_error` et autre type d'erreur, corps de `claude_sonnet` (on/off, sans échantillonnage), `verbatim` avec marqueur ou caractère privé, estimation d'un appel à deux chaînes (dédoublonnage de `_attribute`) | medium | Recherches de VG : aucun test ne les atteint | patch |
| 5 | BH | `model_context_window_exceeded` donne l'erreur générique, pas « contexte dépassé » | low | Correction directe | patch |
| 6 | BH | Libellés français « Réflexion jetée » alors que la brique et `reasoning_cut` disent « Raisonnement » | low | Correction de texte | patch |
| 7 | BH | README promet « Réflexion jetée » alors qu'aucun préréglage actif ne fait le contrôle ; exemple Opus 5.5 sans `enabled`, `impacts`, `notes_text` | low | `wavestack.toml`, README | patch |
| 8 | BH | Note de mesures : total 0,0258 $ contre 0,0259 $ par ligne ; questions ouvertes de SPEC.md non mises à jour | low | `mesures-anthropic-2026-10.md`, SPEC.md | patch (SPEC.md par l'orchestrateur) |
| 9 | VG, BH | Rendu de `reasoning_dropped` dans `app.js` non couvert par l'E2E | low | Le faux fournisseur E2E ne parle que Chat Completions | defer |
| 10 | EC | `verbatim` avec sentinelles U+E000-E002 casse l'étape 4 | false | `verbatim` rend une chaîne simple pour tout caractère privé : rendus marqué et simple identiques | rejeté |
| 11 | BH, EC | `_tool_input` rend `{}` en silence pour des arguments invalides | false | Un appel aux arguments invalides suit la voie mal formée (AD-10) et n'entre pas dans l'historique comme `tool_calls` | rejeté |
| 12 | EC | Combinaisons incohérentes dans `settings.json` (`anthropic_messages` + `content_blocks`…) non refusées | low | Édition manuelle rare ; garde nouvelle | rejeté |
| 13 | BH | Chemin brut `messages.1.content.0` affiché ; catégories de refus non traduites ; `is_error` absent des `tool_result` | low | Cosmétique ou surface nouvelle | rejeté |
| 14 | BH | Bloc `thinking` sans signature écarté sans trace | low | Anthropic signe toujours ses blocs | rejeté |
| 15 | BH | Test du changement de modèle par `session._cloud` ; état `_final_thinking` porté par l'instance ; contenu `user` vide | low | Fonctionne ; l'interface n'envoie pas de message vide | rejeté |

## Design Notes

Les blocs de réflexion sont opaques comme `extra_content` de Gemini : la session les garde par sortie (`extra_for` = id de l'entrée) et le pivot les porte dans une clé que seul le traducteur `anthropic_messages` lit. Le texte d'un bloc `thinking` est le raisonnement reçu : quand la forme le permet, il est attribué comme le raisonnement (segment de l'assistant), sinon au gabarit ; la réconciliation par `usage` reste exacte. Même chose pour `tool_use.input` (objet analysé, octets au gabarit si les sentinelles ne peuvent pas y tenir).

## Verification

**Commands:**
- `uv run ruff check . ; uv run ruff format --check .` -- expected: aucun écart
- `uv run pytest tests/test_anthropic_messages.py tests/test_cloud_api.py tests/test_cloud.py tests/test_cloud_cap.py tests/test_backend_messages.py -q` -- expected: vert
- `pytest` complet en quatre quarts, un à la fois ; E2E par tranches `--only` pour le journal (`app.js`) -- expected: vert
