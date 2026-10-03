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

### Review Findings

Revue de la PR #20 du 2026-10-03, groupe 1 (`src/wavestack/models/`, `context/render.py`), quatre couches (Blind Hunter, Edge Case Hunter, Verification Gap, Acceptance Auditor).

- [x] [Review][Patch] Test : un message assistant qui ne porte que des `thinking_blocks` (texte vide, sans appel) est omis du corps Anthropic. Aujourd'hui, remplacer `len(blocks) > thought` par `blocks` ne fait échouer aucun test. [`tests/test_anthropic_messages.py:651`]
- [x] [Review][Patch] Tests : un « Arrêter » pendant le flux donne `stop_reason == "cancelled"` et aucun `harness_error`, pour Anthropic et pour Responses (variante avec un événement `error` avant l'arrêt). Aucun test ne lève le jeton pendant un flux. [`src/wavestack/models/anthropic_messages.py:96`, `src/wavestack/models/openai_responses.py:127`]
- [x] [Review][Patch] Test : `reasoning_dropped` est émis quand l'appel échoue après `input_transformations` (refus, ou événement `error`). Seul le chemin réussi est testé. [`src/wavestack/models/cloud_base.py:758`]
- [x] [Review][Patch] Masquer `path` dans `reasoning_dropped` (AD-15 : toute chaîne venue du fournisseur passe par le masque avant d'entrer dans un événement). [`src/wavestack/models/cloud_base.py:758`]
- [x] [Review][Patch] Règle « une réponse finie reste finie » à l'arrêt. Anthropic écrase un `stop` déjà lu dans `message_delta` par `cancelled`, ce qui fait perdre les appels d'une réponse complète et facturée ; corriger en `stop = stop or "cancelled"`. Responses porte ce `or`, mais il y est mort, car chaque fin fait `break` : simplifier et corriger le commentaire. [`src/wavestack/models/anthropic_messages.py:96`, `src/wavestack/models/openai_responses.py:128`]
- [x] [Review][Defer] Réflexion entrelacée : `_anthropic_messages` place tous les `thinking_blocks` en tête du message, avant le texte et les `tool_use`. Si un appel reçoit thinking → texte → thinking → tool_use, l'ordre renvoyé diffère de l'ordre reçu. [`src/wavestack/context/render.py:502`] — deferred: non vérifié, serait moyen ; à trancher par un appel Sonnet 5 qui produit un texte avant un `tool_use`, en relevant l'ordre des blocs bruts et la réponse au renvoi (accepté, `reasoning_dropped` ou 400).

**Rejetées (Anthropic) :**
- `false` (décision d'Anaël : mesurer d'abord) : un corps qui porte des `tool_use`/`tool_result` sans `tools` serait refusé quand la brique Outils est éteinte après un tour avec appels. Haiku l'accepte (200, `mesures-anthropic-2026-10.md`, « Mesure de la revue de la PR #20 »).
- `low` : un `index` absent dans les événements `content_block_*` : l'API en donne toujours un, entier.
- `false` : un refus traité autrement que par Responses. Les sémantiques diffèrent : `stop_reason: refusal` est un arrêt de l'API, alors que le `refusal` d'OpenAI est un contenu d'une réponse complète.
- `false` : un `raw_output` sans `message_start`/`message_delta`. Il suit la convention d'`openai_chat` (deltas de contenu seuls, `openai_chat.py:154`) ; la fin et l'usage sont dans `model_call_ended`.
- `low` : un `ReadTimeout` après `message_start` et avant tout delta perd l'usage et les abandons. C'est rare, et le correctif devrait porter l'usage à travers `complete()`.
- `low` : des `NaN` dans les arguments d'un appel. Peu plausible, et le correctif ajouterait une garde.

Revue de la PR #20 du 2026-10-03, groupe 2 (`src/` hors `models/` et `context/render.py`, `wavestack.toml`, `content/`), quatre couches. Acceptance Auditor bloqué au premier essai (600 s sans progrès), relancé une fois avec succès.

- [x] [Review][Patch] (décision d'Anaël : `temperature` seule) Haiku 4.5 refuse `temperature` et `top_p` ensemble : « LLM nu » échoue (400) à chaque appel réflexion éteinte — `claude_haiku` déclare `sampling = ["temperature", "top_p"]`, et l'écran envoie toujours ses quatre réglages (`SamplingIntention` requis, `web/app.py:425`), donc `chat_fields` pose les deux. Doc d'Anthropic (guide de migration Haiku 4.5) : « Use only `temperature` OR `top_p`, not both. Setting both returns a 400 error on Claude Haiku 4.5. » Aucune mesure du 2026-10-03 ne l'a essayé (M3b et suivantes sans échantillonnage). Choix : ne déclarer que `temperature` (recommandé), ne déclarer que `top_p`, ou une règle de code « un seul des deux » pour `anthropic_messages`. [`wavestack.toml:484`]
- [x] [Review][Patch] (décision d'Anaël : corriger les commentaires, retirer les `off` morts) Le bloc `off` des exemples Opus 5.5 et GPT-6.1 Sol n'est jamais envoyé — les deux portent `always = true`, et `reasoning_params` prend `on` dès que `always` est vrai (`config.py:330`). Les commentaires (« low pour l'éteindre au mieux », « « low » éteinte ») et le tableau de `formats-natifs.md` disent le contraire ; le memlog note la même intention. Choix : corriger les commentaires et retirer les `off` morts (recommandé, AD-6 inchangé), ou faire lire `off` à une entrée `always` qui le déclare (change AD-6, à garder vide pour Groq). [`wavestack.toml:528`, `wavestack.toml:596`]
- [x] [Review][Patch] Entrée `always` + brique Raisonnement éteinte : les blocs `thinking` ne repartent pas, alors que le modèle a réfléchi (`on` envoyé). `TurnState.resend` n'est posé que si `"reasoning" in effective`. Pour l'exemple Opus 5.5 activé, un tour Outils sans la brique Raisonnement renverrait un `tool_use` sans son bloc signé (400). Poser `resend` aussi quand l'entrée raisonne toujours (`always_reasons`) ; aucune entrée `openai_chat` actuelle n'a `always` et `resend` ensemble, les corps restent identiques. [`src/wavestack/session/app_session.py:3750`]
- [x] [Review][Patch] « Tester » rejoue l'appel d'outil sans les blocs de réflexion reçus : seul `extra_content` est repris. Sans effet pour Haiku et Sonnet (« Tester » envoie `off`), mais une entrée `always` (Opus 5.5) reçoit `on` et son second appel part sans le bloc signé. Reprendre `out.thinking_blocks` sous la clé de `entry.reasoning.format` quand `resend` est vrai. [`src/wavestack/session/diagnostic.py:1127`]
- [x] [Review][Patch] Test au niveau session : une réflexion (ou un résumé Responses) qui contient un marqueur de gabarit (`<|im_end|>`) repart à l'octet près, dans le tour (appel suivant), dans l'historique (tour suivant) et, si possible, au sous-agent. Aujourd'hui seuls des appels directs à `_assistant_message(..., markers=...)` le testent : retirer `markers=` d'un site d'appel (l. 4012, 4054, 4164) ne fait échouer aucun test. Jumeau dans `tests/test_openai_responses.py`. [`tests/test_anthropic_messages.py:934`]
- [x] [Review][Patch] Test : `claude-haiku-4-5` et `claude-sonnet-5` classés sous l'éditeur `claude` dans `test_publisher_for` (seul `gpt` y a des cas ; supprimer l'entrée `claude` ne fait échouer aucun test). [`tests/test_model_catalog.py:479`]
- [x] [Review][Patch] Motif d'éditeur `claude` non ancré : un modèle local sans architecture reconnue dont le nom contient « claude » (les « …-Claude-…-Distill ») est classé « Claude (Anthropic) ». Ancrer en `^claude` (fr, en, de), comme `^gpt-\d`. [`content/models/publishers.yaml:78`]
- [x] [Review][Patch] `Exchange(..., *self._final_thinking)` : dépaquetage positionnel dans les deux derniers champs ; passer `thinking=`, `thinking_for=` nommés. [`src/wavestack/session/app_session.py:6381`]
- [x] [Review][Patch] Commentaires restés « Anthropic seul » : `chat_fields` (« none to Anthropic while it thinks ») et la docstring de `_sampling_trace`, alors que `sampling_sent` vaut aussi pour `openai_responses` et pour une entrée `always`. [`src/wavestack/cloud.py:100`, `src/wavestack/session/app_session.py:8262`]
- [x] [Review][Patch] Commentaire de `wavestack.toml` : « propre à Opus 5.5, Fable 5.1 et Sonnet 5.5 » ; la SPEC (Assumptions) dit « Opus 5.5 et Fable 5.1 », Sonnet 5.5 n'est sourcé nulle part. Aligner sur la SPEC. [`wavestack.toml:459`]
- [x] [Review][Defer] Front de `reasoning_dropped` non vérifié : aucun test JS, et le faux fournisseur E2E ne parle que Chat Completions, donc ne peut émettre `input_transformations`. Retirer le `case "reasoning_dropped"` d'`applyEnvelope` ne fait échouer aucun contrôle. [`src/wavestack/web/static/app.js:639`] — deferred: demande un point d'API Messages dans le faux fournisseur E2E, hors de ce groupe.
- [x] [Review][Defer] Crédit Anthropic épuisé non reconnu : `no_credit` ne lit que les codes d'OpenAI (`insufficient_quota`, `credit_balance_exhausted`). [`src/wavestack/models/cloud_base.py:214`] — deferred: non vérifié, serait moyen (code du groupe 1) ; à trancher par la forme réelle de l'erreur d'un compte Anthropic à solde nul (attendu : 400 `invalid_request_error`, « credit balance is too low ») et le message affiché aujourd'hui.

**Rejetées (groupe 2) :**
- `false` : `block_binding` envoyé à Haiku et Sonnet sans preuve qu'ils l'acceptent. Mesuré accepté avec la réflexion allumée (M1+A1, 200, `mesures-anthropic-2026-10.md:22`, `:24`).
- `false` : l'indication `free_models` nommerait à tort Gemma. Gemma n'a pas de `pricing` (`wavestack.toml:433`).
- `false` : plafond invisible dans l'interface. Hors intention de la story 2 (« Pas d'interface ») et déjà différé à sa revue.
- `low` : la note `with_reasoning` conseille d'éteindre « Raisonner avant de répondre » à une entrée `always`. Aucune entrée `always` native ne déclare `sampling` ; le correctif ajouterait une variante de message.
- `low` : aucun contrôle croisé `api` / `max_tokens_field` / `anthropic-version` / `reasoning.format` au chargement. Une entrée mal recopiée échoue bruyamment au premier appel (400) ; les entrées livrées et les exemples sont justes ; le correctif ajouterait un validateur.
- `low` : raisons d'`extra_headers` en français seulement. Prolonge l'exception de la story 23 (`auth_header`), visible seulement sur une erreur de configuration ; le correctif demanderait des messages à clé.
- `low` : noms ou valeurs d'en-têtes invalides (CR/LF, non-ASCII) acceptés au chargement. Erreur d'opérateur, rattrapée au premier appel par l'`except` du tour.
- `low` : raisons d'abandon définies à trois endroits (tuple, `Literal`, YAML). Le correctif ajouterait une dérivation ou un test de cohérence.
- `low` : clé de pas `thinking_blocks` réutilisée pour les items `reasoning` d'OpenAI. Le renommage toucherait tout le canal pour un nom.
- `low` : `^gpt-\d` ne couvre ni `chatgpt-4o-latest` ni la série o. Aucune entrée de ce type n'est configurée.
- rejetée par règle : signatures et `encrypted_content` en clair dans `context_rendered` / `outbound_request`, alors que la SPEC dit « masqués que dans les événements ». L'implémentation suit CAP-1 (corps égal aux octets envoyés) et la story 3 (masqués dans `raw_output`) ; le correctif modifierait la spec relue.

Revue de la PR #20 du 2026-10-03, groupe 4a (`tests/`, `tools/e2e/`, hors `test_v2s6_decision_bench.py`), quatre couches. Le code testé n'a été relu que pour juger les tests. Empreintes `openai_chat_bodies.json` recalculées sur le code d'avant la refactorisation (`7f40fc1^`, `e09cfa6`) par deux couches : identiques. Aucun test ne touche le réseau ni ne dépend de l'ordre.

- [x] [Review][Patch] `reasoning_dropped` : `organization_binding_mismatch` n'est dans aucun test (le retirer du tuple ne fait rien échouer), et les textes en, de ne sont vérifiés que pour `prefix_binding_mismatch` (`dropped[0]`). Ajouter la troisième raison à `DROPPED` et vérifier chaque raison dans les trois langues. [`tests/test_anthropic_messages.py:566`]
- [x] [Review][Patch] `test_reasoning_dropped_speaks_the_sessions_language` appelle `run_call(..., lang=lang)` sur un engine nu : retirer `lang=self._language` des trois appelants (`app_session.py:7996`, `:8823`, `diagnostic.py:1112`) ne fait échouer aucun test. Ajouter un tour par séance passée en `en` (ou `de`) dont le flux porte `input_transformations`, et vérifier la langue du `message_text`. [`tests/test_anthropic_messages.py:617`]
- [x] [Review][Patch] Corps Anthropic sans liste exacte des clés : les tests ne nomment que des clés absentes (`temperature`, `stream_options`), alors que Responses épingle `list(sent)`. Une clé `store`, `include` ou `reasoning` venue d'un chemin commun passerait (400 en réel). Reprise incomplète du #10 de la story 4 (« empreinte de chaque entrée livrée, Luna et Claude ») : épingler `list(body)` de `claude_haiku` allumé et éteint, et de `claude_sonnet` allumé. [`tests/test_anthropic_messages.py:210`]
- [x] [Review][Patch] Branches d'erreur des deux adaptateurs jamais atteintes : une ligne `data:` illisible au milieu du flux (`unreadable_stream`, Anthropic et Responses ; `test_nothing_after_a_terminal_event_is_read` la place après la fin, où elle n'est pas lue), `data: [DONE]` de Responses, une erreur de transport (`httpx.ReadError`) en plein flux, un refus Anthropic sans `stop_details` (message et cause sans catégorie), et l'usage facturé quand un événement `error` Anthropic suit `message_start` (seul le refus le vérifie). [`tests/test_anthropic_messages.py:491`, `tests/test_openai_responses.py:756`]
- [x] [Review][Patch] Masquage de `redacted_thinking.data` dans les événements non prouvé : le test utilise `data: "b3BhcXVl"`, sans fragment de clé. Y mettre `SENTINEL[-4:]` et vérifier qu'il est masqué dans `raw_output` et verbatim dans le corps suivant. [`tests/test_anthropic_messages.py:892`]
- [x] [Review][Patch] Aucun test natif du sous-agent (CAP-2, CAP-3 : « tours, outils, sous-agent… » ; demandé « si possible » en groupe 2) : blocs `thinking` et items `reasoning` remis au sous-agent, isolement par `thinking_for`. Un tour par `claude_haiku`, puis le même par `openai_luna`, avec la brique Sous-agent. [`tests/test_anthropic_messages.py`, `tests/test_openai_responses.py`]
- [x] [Review][Patch] Second tour des deux tests d'acceptation : le canal Raisonnement n'est vérifié qu'au premier (`channels` sur `first`), alors que le critère porte sur « un tour Outils puis un tour Raisonnement ». Vérifier `reasoning` dans les `model_delta` de `second`. [`tests/test_anthropic_messages.py:210`, `tests/test_openai_responses.py:251`]
- [x] [Review][Patch] `test_a_null_in_the_last_usage_keeps_the_first_value` omet `message_stop` et teste donc aussi, sans le dire, un flux sans `message_stop` : ajouter l'événement. `cost_in_usd > 0` répète l'`approx` qui précède dans `test_a_refusal_is_explained_with_its_category` : le retirer. [`tests/test_anthropic_messages.py:452`, `:398`]
- [x] [Review][Patch] U+200B littéral (invisible à la relecture) dans deux assertions, alors que les autres écrivent `"​"`. [`tests/test_anthropic_messages.py:1002`, `tests/test_openai_responses.py:926`]

**Rejetées (groupe 4a) :**
- rejetée par règle : une raison inconnue de `thinking_dropped` ignorée sans événement. La story le prescrit (« Raisons et types inconnus ignorés »).
- rejetée par règle : `anthropic-version` et `anthropic-beta` masqués dans la trace. Déjà rejeté en story 1 (#16), imposé par SPEC.md.
- `false` : refus traités autrement par Anthropic (erreur) et OpenAI (texte). Déjà rejeté en groupe 1 : les sémantiques diffèrent.
- `false` : plafond à 0 non testé. La story 2 dit qu'aucune valeur ne désactive le plafond, et 0 est documenté (triage #5).
- `false` : un « Arrêter » après `response.completed` non testé pour Responses. La lecture s'arrête à chaque fin (groupe 1), le jeton n'y est plus lu.
- `false` : jetons de raisonnement d'OpenAI comptés deux fois. Le test d'acceptation donne `output_tokens == 40` avec `reasoning_tokens = 20`.
- `false` : modèle local « Claude-…-Gemma3 » classé Claude. `publisher_for` lit les architectures avant les noms : il est classé Gemma.
- `false` : `anthropic-beta` absent quand la réflexion est éteinte. `extra_headers` est fixe par entrée et posé à chaque requête (`test_extra_headers_are_sent_on_each_request_and_masked_in_the_trace`).
- `low` : aides de test recopiées entre les deux fichiers natifs (`Provider`, `sse`, `_session`…). Refactorisation sans défaut.
- `low` : fixtures `_spend` redondantes avec `conftest.py`. Sans effet.
- `low` : aucun test de données après `message_stop`. Anthropic ferme le flux après cet événement.
- `low` : entrée `always` testée pour Anthropic seulement. Même chemin de session pour Responses.
- `low` : changement d'entrée par `session._cloud`. Déjà rejeté (story 3, triage #15).
- `low` : empreintes illisibles en cas d'échec. Déjà rejeté (story 1, #13) ; empreintes vérifiées justes.
- `low` : `test_a_provider_error_is_a_provider_error` recoupe le test du flux coupé. Il vérifie le type levé par l'engine seul ; doublon inoffensif.
- `low` : `cloud_model` remplacé pour tous les ids. Déjà rejeté (story 1, #15).
- `low` : noms préfixés par un routeur (`anthropic/claude-…`) en « Autres éditeurs ». Aucune entrée de ce type n'est configurée.
- `low` : `cfg.cloud_model(...)` sans `assert` avant usage. Échoue bruyamment (`AttributeError`).
- `low` : « rien d'autre » vérifié par `engine._headers()` et non sur le fil. httpx ajoute ses propres en-têtes sur le fil ; l'ordre est vérifié sur le fil par un autre test.

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

- 2026-10-03, revue de la PR #20 (groupe 2), décision d'Anaël : `claude_haiku` déclare `sampling = ["temperature"]` au lieu de `["temperature", "top_p"]` (Always, entrée `claude_haiku`). Haiku 4.5 refuse les deux ensemble (400, guide de migration d'Anthropic relu le 2026-10-03), et « LLM nu » envoie toujours les réglages déclarés. Le top-p est laissé à Anthropic.

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
