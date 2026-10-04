# Formats natifs : traduction du pivot, flux et entrées

Relevé le 2026-10-03. Le pivot est l'historique que la session produit déjà au format Chat Completions (`system`, `user`, `assistant` avec `tool_calls`, `tool`). Revérifier chaque prix, chaque nom de modèle et chaque paramètre à l'écriture de l'entrée.

## Socle commun

| Élément | Règle |
|---|---|
| `CloudModel.api` | `openai_chat` (défaut), `openai_responses`, `anthropic_messages` |
| `CloudModel.extra_headers` | En-têtes fixes non secrets ; refusés s'ils figurent dans `PUBLIC_HEADERS` (même règle que `AuthHeader`) |
| `PUBLIC_RESPONSE_PREFIXES` | Ajouter `anthropic-ratelimit-` |
| `CloudReasoning.format` | Ajouter `thinking_blocks` (Anthropic) et `reasoning_items` (Responses) |
| `CloudPricing` | Ajouter `cache_read_usd_per_mtok` et `cache_write_usd_per_mtok`, facultatifs |
| Code commun | `ProviderError`, `mask_key`, `_refused`, `pace`, FinOps et `run_call` sortent de `openai_chat.py` vers un module de base ; chaque adaptateur garde son `_read` et son traducteur |
| Fabrique d'engine | `app_session.py` (création d'`OpenAIChatEngine`) choisit la classe par `entry.api` |
| Appels de `render_chat_body` | Tour (`app_session.py`), « LLM nu » (`app_session.py`), « Tester » (`session/diagnostic.py`) passent l'entrée pour choisir le traducteur |
| `chat_fields` (`cloud.py`) | Champs propres à l'API : nom de la limite de sortie, forme du raisonnement |

## Anthropic : API Messages

`POST https://api.anthropic.com/v1/messages`, `stream: true`.

En-têtes : `x-api-key` (`auth_header = { name = "x-api-key", scheme = "" }`), `anthropic-version: 2023-06-01`, `anthropic-beta: thinking-binding-controls-2026-08-01`.

### Traduction du pivot

| Pivot | Corps Anthropic |
|---|---|
| Messages `system` | Champ `system` de premier niveau, dans l'ordre, joints |
| `assistant.content` | Bloc `text` |
| Raisonnement reçu (`resend`) | Blocs `thinking` `{thinking, signature}` en tête du tour assistant, verbatim |
| `assistant.tool_calls[]` | Blocs `tool_use` `{id, name, input}` ; `input` est l'objet analysé de `arguments` |
| Messages `tool` consécutifs | Un seul message `user`, un bloc `tool_result` `{tool_use_id, content}` par réponse |
| Appel mal formé (AD-10) | Message `assistant` texte brut, puis `user` avec l'erreur, comme aujourd'hui |
| `tools[]` | `{name, description, input_schema}` |
| Limite de sortie | `max_tokens` |
| Réflexion | `thinking` selon l'entrée (tableau des entrées), plus `block_binding: {prefix_mismatch_behavior: "drop_block"}` |

### Lecture du flux SSE

| Événement | Effet |
|---|---|
| `message_start` | Usage d'entrée ; `input_transformations` lu s'il est présent |
| `content_block_start` type `tool_use` | Ouvre un appel `{provider_id: id, name}` |
| `content_block_delta` `text_delta` | Canal `text` |
| `content_block_delta` `thinking_delta` | Canal `reasoning` |
| `content_block_delta` `signature_delta` | Signature gardée verbatim pour le renvoi, masquée dans les événements |
| `content_block_delta` `input_json_delta` | Canal `tool_call`, accumulé dans `arguments` |
| `message_delta` | `stop_reason`, usage de sortie |
| `error` (dont `overloaded_error`) | `ProviderError` (AD-16) |
| `ping`, `message_stop`, `content_block_stop` | Rien |

Fins : `end_turn`, `tool_use` et `stop_sequence` donnent `stop` ; `max_tokens` donne `length` ; `refusal` donne une erreur expliquée, avec la catégorie de `stop_details`. HTTP 529 suit la règle des 5xx.

Usage : `prompt_tokens = input_tokens + cache_read_input_tokens + cache_creation_input_tokens` ; `output_tokens` inclut la réflexion.

Raisonnement abandonné : chaque entrée de `input_transformations` (`thinking_dropped`, raison `prefix_binding_mismatch` ou `model_binding_mismatch`) produit un événement de journal, avec la cause en français. Les raisons inconnues sont ignorées.

## OpenAI : API Responses

`POST https://api.openai.com/v1/responses`, `stream: true`, `store: false`, `include: ["reasoning.encrypted_content"]`. Authentification par `Authorization: Bearer` (le défaut).

### Traduction du pivot

| Pivot | Corps Responses |
|---|---|
| Messages `system` | `instructions` |
| `user` et `assistant.content` | Items `{type: "message", role, content}` de `input` |
| Raisonnement reçu (`resend`) | Items `reasoning` reçus, verbatim (dont `encrypted_content`), avant les appels qu'ils précèdent |
| `assistant.tool_calls[]` | Items `{type: "function_call", call_id, name, arguments}` (`arguments` en chaîne) |
| Messages `tool` | Items `{type: "function_call_output", call_id, output}` |
| `tools[]` | `{type: "function", name, description, parameters}` |
| Limite de sortie | `max_output_tokens` |
| Réflexion | `reasoning: {effort, summary: "auto"}` |

### Lecture du flux SSE

| Événement | Effet |
|---|---|
| `response.output_text.delta` | Canal `text` |
| `response.reasoning_summary_text.delta` | Canal `reasoning` |
| `response.output_item.added` type `function_call` | Ouvre un appel `{provider_id: call_id, name}` |
| `response.function_call_arguments.delta` | Canal `tool_call`, accumulé dans `arguments` |
| `response.output_item.done` type `reasoning` | Item gardé verbatim pour le renvoi |
| `response.completed` | Fin `stop` ; usage `input_tokens`, `output_tokens` (dont `output_tokens_details.reasoning_tokens`) |
| `response.incomplete` | Fin `length` si la raison est `max_output_tokens`, sinon erreur expliquée |
| `response.failed`, `error` | `ProviderError` (AD-16) |

Usage en cache : `input_tokens_details.cached_tokens`.

## Entrées de `wavestack.toml`

| id | Modèle | API | Contexte | Prix (entrée / sortie / lecture du cache, $ par million) | Raisonnement on | Raisonnement off | `sampling` |
|---|---|---|---|---|---|---|---|
| `claude_haiku` | `claude-haiku-4-5` | `anthropic_messages` | 200 000 | 1 / 5 / 0,10 | `{type: "enabled", budget_tokens: 1024}` | `{type: "disabled"}` | `temperature` (Haiku 4.5 refuse `temperature` et `top_p` ensemble, revue G2 du 2026-10-03) |
| `claude_sonnet` | `claude-sonnet-5` | `anthropic_messages` | 1 000 000 | 2 / 10 / 0,20 | `{type: "adaptive", display: "summarized"}` | `{type: "disabled"}` | aucun |
| `openai_luna` | `gpt-6-luna` | `openai_responses` | 1 050 000 | 0,10 / 0,50 / 0,01 | `effort: "low"`, `summary: "auto"` | `effort: "none"` | `temperature`, `top_p`, raisonnement éteint seulement (mesuré le 2026-10-03 : refusés avec l'effort `low`) |
| commentaire | `claude-opus-5-5` | `anthropic_messages` | 1 000 000 | 4 / 20 / 0,20 | `always = true`, `{type: "adaptive", display: "summarized"}`, effort `medium` | aucun : `always = true` n'envoie que `on` (« off = low » retiré le 2026-10-03) | aucun |
| commentaire | `gpt-6.1-sol` | `openai_responses` | 1 050 000 | 2 / 10 / 0,10 | `always = true`, effort `medium` | aucun : `always = true` n'envoie que `on` (« off = low » retiré le 2026-10-03) | aucun |

Les prix de lecture du cache d'Anthropic sont à relever (le tableau donne la règle habituelle, 0,1 fois l'entrée) ; l'écriture en cache vaut 1,25 fois l'entrée. `resend = true` pour les deux formats natifs : sans les blocs ou les items renvoyés, une boucle d'outils avec raisonnement est refusée ou se dégrade.

Le budget de Haiku (1 024) doit rester inférieur à `max_tokens` : avec la réserve de 1 536 tokens (AD-9), il reste 512 tokens à la réponse.
