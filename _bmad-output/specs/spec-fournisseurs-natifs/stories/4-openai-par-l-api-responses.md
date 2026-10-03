---
title: 'Fournisseurs natifs (4/5) : OpenAI par l''API Responses'
type: 'feature'
created: '2026-10-03'
status: 'done'
baseline_commit: '4dc5f232e99f297adcaec2618b793b520dee6ea5'
route: 'dispatch'
review_loop_iteration: 0
context:
  - '{project-root}/_bmad-output/specs/spec-fournisseurs-natifs/SPEC.md'
  - '{project-root}/_bmad-output/specs/spec-fournisseurs-natifs/formats-natifs.md'
  - '{project-root}/_bmad-output/specs/spec-fournisseurs-natifs/stories/3-anthropic-par-l-api-messages.md'
---

<frozen-after-approval reason="human-owned intent — do not modify unless human renegotiates">

## Intent

**Problem:** GPT-6 Luna n'appelle d'outils par Chat Completions que raisonnement éteint (doc OpenAI relue le 2026-10-03), et ne renvoie jamais son raisonnement par cette API : les briques Outils, MCP, Sous-agent et Raisonnement exigent l'API Responses.

**Approach:** Un adaptateur `openai_responses` (engine + traducteur du pivot, sur les registres des stories 1 et 3) écrit le corps Responses sans état (`store: false`), lit le flux SSE, renvoie verbatim les items `reasoning` chiffrés reçus, et une entrée `openai_luna` (`gpt-6-luna`) rejoint `wavestack.toml`, `gpt-6.1-sol` en commentaire. Les questions ouvertes (Luna accepte-t-il `temperature`/`top_p` ; quel effort montre un résumé sans gonfler le coût) sont tranchées par quelques appels réels, plafond 5 $ (CAP-3).

## Boundaries & Constraints

**Always:**
- Même architecture que la story 3 : traducteur dans `TRANSLATORS`, engine dans `ENGINES`, `Literal` de `CloudModel.api` élargi à `openai_responses` (test de phase de la story 1) ; corps envoyé = `context_rendered.body` = `outbound_request.body` (faux serveur).
- Point d'accès `POST {base_url}/responses`, `base_url = "https://api.openai.com/v1"`, `Authorization: Bearer` (défaut), aucun `extra_headers`.
- Corps (section « OpenAI » de `formats-natifs.md`) : messages système → `instructions` (joints par « \n\n ») ; `user` et texte d'assistant → items `{type: "message", role, content}` (contenu chaîne, sauf si les mesures exigent des parties typées) ; appels → items `{type: "function_call", call_id, name, arguments}` (`arguments` chaîne, telle qu'émise) ; réponses d'outil → `{type: "function_call_output", call_id, output}` ; outils → `{type: "function", name, description, parameters}` ; limite → `max_output_tokens` (`max_tokens_field` l'accepte) ; toujours `store: false` et `include: ["reasoning.encrypted_content"]`.
- Raisonnement renvoyé verbatim : `CloudReasoning.format` accepte `reasoning_items`, `resend = true`. Les items `reasoning` complets (`response.output_item.done`, dont `encrypted_content` et `summary`) passent par le même canal que les blocs de la story 3 (`ChatEnd.thinking_blocks`, `thinking_for`, seule l'entrée qui les a produits les reçoit), et repartent juste avant les items de leur tour assistant, dans l'ordre reçu. `encrypted_content` masqué dans les événements seulement (AD-15). Le texte du résumé est attribué comme le raisonnement quand la forme le permet (`verbatim`), sinon au gabarit.
- Flux : `response.output_text.delta` → `text` ; `response.reasoning_summary_text.delta` → `reasoning` ; `response.output_item.added` `function_call` ouvre un appel `{provider_id: call_id, name}` ; `response.function_call_arguments.delta` → `tool_call` ; `response.completed` → `stop` et usage ; `response.incomplete` → `length` si `max_output_tokens`, sinon `ProviderError` expliqué (raison citée) ; `response.failed` et `error` → `ProviderError` (AD-16), avec l'usage déjà lu attaché comme en story 3. Usage pivot : `prompt_tokens = input_tokens`, `prompt_tokens_details.cached_tokens = input_tokens_details.cached_tokens`, `completion_tokens = output_tokens` (raisonnement compris). Dépassement de contexte (`context_length_exceeded`) reconnu.
- Échantillonnage de « LLM nu » : même règle que la story 3 (`sampling_sent`), étendue à `openai_responses` : rien pendant que le modèle raisonne. `sampling` de Luna reste vide si la mesure montre un refus, même raisonnement éteint.
- Entrée `openai_luna` : `provider = "OpenAI"`, `model = "gpt-6-luna"`, contexte 1 050 000, prix 0,10 / 0,50, cache lu 0,01 (fiche du modèle relue le 2026-10-03, à revérifier), `on = {reasoning: {effort: "low", summary: "auto"}}`, `off = {reasoning: {effort: "none"}}` (Luna n'a pas `minimal`), `tools = true`, `key_env = "OPENAI_API_KEY"`, `impacts = {provider = "openai", model = "gpt-6-luna"}` (connu d'EcoLogits 0.11.2). `hosting_text`, `training`, `notes_text` relus sur les conditions d'OpenAI (relevé du 2026-10-03 : pas d'entraînement sur les données d'API par défaut, journaux d'abus jusqu'à 30 jours même avec `store: false`, résidence UE seulement par un projet dédié et `eu.api.openai.com`). `gpt-6.1-sol` en commentaire : 2 / 10, cache 0,10, `always = true`, effort `medium` / `low`.
- Éditeur « OpenAI » dans `content/models/publishers.yaml` (fr, en, de) s'il manque, comme Claude en story 3.
- Mesures réelles (clé `OPENAI_API_KEY` lue dans l'environnement utilisateur Windows, jamais affichée ; une dizaine d'appels au plus) : (1) `temperature` et `top_p` raisonnement éteint ; (2) effort `low` puis `medium` : résumé visible ou non, tokens de raisonnement et coût ; (3) items `reasoning` renvoyés avec leur `id` sous `store: false` acceptés (sinon les renvoyer sans `id`) ; (4) contenu d'assistant en chaîne accepté ; (5) résumé absent faute de vérification d'organisation : le consigner, c'est une action d'Anaël. Résultats dans `_bmad-output/implementation-artifacts/mesures-openai-2026-10.md` et dans les notes d'implémentation ; réponses reportées dans les questions ouvertes de SPEC.md.

**Never:**
- Pas de SDK, pas de `previous_response_id` ni de `store: true`, pas d'outils intégrés (recherche web, fichiers), pas de Sol actif, pas de relance automatique.
- Ne pas changer les corps `openai_chat` ni `anthropic_messages`.

## I/O & Edge-Case Matrix

| Scenario | Input / State | Expected Output / Behavior | Error Handling |
|----------|--------------|---------------------------|----------------|
| Texte | `response.output_text.delta` puis `response.completed` | Canal `text`, fin `stop`, usage pivot | N/A |
| Raisonnement | `reasoning_summary_text.delta`, item `reasoning` chiffré, puis appel | Canal `reasoning` ; item renvoyé verbatim avant le `function_call` au tour suivant, masqué dans `model_call_ended` | N/A |
| Outils parallèles | Deux `function_call` | Deux appels dans l'ordre ; deux `function_call_output` | N/A |
| Coupure | `response.incomplete`, `max_output_tokens` | Fin `length` | N/A |
| Échec | `response.failed` après un 200 | `harness_error`, usage déjà lu compté | `ProviderError` |
| Quota | HTTP 429 `retry-after` | Indication d'attente | `ProviderError` |
| Cache | `input_tokens 1000`, `cached_tokens 800` | Coût selon la story 2 (0,01 pour 800) | N/A |
| Autre entrée | Items reçus de `openai_luna`, modèle changé pour `claude_haiku` | Jamais renvoyés à Claude | N/A |

</frozen-after-approval>

## Code Map

- `src/wavestack/models/anthropic_messages.py` -- modèle direct de l'adaptateur (lecture SSE, usage pivot, erreurs avec usage attaché, `_merge`) ; nouveau `src/wavestack/models/openai_responses.py`.
- `src/wavestack/context/render.py` -- `_anthropic_messages`, `_tool_input`, `verbatim`, `TRANSLATORS` ; ajouter `_openai_responses`.
- `src/wavestack/models/cloud_base.py` -- `ChatEnd.thinking_blocks`, `ProviderError.usage`/`dropped`, `run_call` (masquage des blocs dans `traced`).
- `src/wavestack/session/app_session.py` -- `_assistant_message` (l. ~3873-3900, forme `thinking_blocks`), `_assistant_step` (l. ~5118), `out.thinking` (l. ~8013) : réutiliser pour `reasoning_items`.
- `src/wavestack/config.py` -- `CloudModel.api`, `CloudReasoning.format`, `max_tokens_field`, `sampling_sent` (l. ~308).
- `wavestack.toml` (entrées Claude de la story 3 comme modèle), `README.md` (section Claude comme modèle), `content/models/publishers.yaml` (+ en, de).
- `tests/test_anthropic_messages.py` -- modèle des tests sur faux serveur SSE.

## Tasks & Acceptance

**Execution:**
- [x] `src/wavestack/config.py` -- `openai_responses`, `reasoning_items`, `max_output_tokens`, `sampling_sent` étendu.
- [x] `src/wavestack/models/openai_responses.py` -- engine ; enregistrement dans `ENGINES`.
- [x] `src/wavestack/context/render.py` -- traducteur `openai_responses`.
- [x] `src/wavestack/session/app_session.py` (si besoin) -- items `reasoning` au format `reasoning_items`.
- [x] `wavestack.toml`, `README.md`, `content/models/publishers.yaml` (+ en, de) -- entrée `openai_luna`, Sol en commentaire, clé et conditions.
- [x] `tests/test_openai_responses.py` -- chaque ligne de la matrice, corps envoyé = tracé, corps de `openai_luna` raisonnement allumé et éteint.
- [ ] Mesures réelles -- `mesures-openai-2026-10.md`, SPEC.md. **Partielles** : le compte OpenAI n'a plus de crédit (`credit_balance_exhausted`) ; mesures 1 et 4 tranchées à la validation, 2, 3, 5 et la recette « clé réelle » restent à faire, crédit ajouté.

**Acceptance Criteria:**
- Given le faux serveur, when un tour Outils avec raisonnement allumé passe par `openai_luna`, then il aboutit, le résumé s'affiche au canal Raisonnement et les items `reasoning` du premier appel repartent dans le second.
- Given la clé réelle, when on joue un tour Outils raisonnement allumé et un tour Raisonnement, then ils aboutissent, et les mesures coûtent moins de 0,50 $.
- Given `pytest` en quarts, when on le joue, then tout est vert.

## Implementation Notes

- Clé réelle : `OPENAI_API_KEY` est dans l'environnement UTILISATEUR de Windows (registre), pas dans celui des shells ouverts. La lire par `powershell -NoProfile -Command "[Environment]::GetEnvironmentVariable('OPENAI_API_KEY','User')"` et la passer au seul processus de mesure, sans jamais l'afficher, la journaliser, l'écrire dans un fichier ni la commiter. `tests/conftest.py` doit retirer `OPENAI_API_KEY` de l'environnement des tests, comme `ANTHROPIC_API_KEY`.
- PC partagé de 16 Go : `pytest` en quarts (un à la fois, `run_in_background` puis attendre), E2E par tranches `--only` ; jamais deux suites à la fois, aucun modèle local en parallèle. Vider le dossier `pytest-of-anael.yahi` du Temp local à la fin. Avant tout E2E, vérifier que le port 8420 est libre ; remettre ensuite `tools/e2e/screenshots` (`git checkout` puis `git clean`).
- La documentation d'OpenAI n'a pas pu être lue en entier (403) : la forme exacte des événements et des items se confirme par les appels réels, à consigner.
- Fait (2026-10-03) : adaptateur `models/openai_responses.py` (`OpenAIResponsesEngine`, `pivot_usage`) et traducteur `_openai_responses` de `context/render.py`, inscrits dans `ENGINES` et `TRANSLATORS` ; `CloudModel.api` accepte `openai_responses`, `CloudReasoning.format` `reasoning_items`, `max_tokens_field` `max_output_tokens` ; `sampling_sent` étendu à `openai_responses`. Corps : `model`, `instructions` (systèmes joints par « \n\n »), `input`, `tools`, puis les champs de `chat_fields` (`stream`, `max_output_tokens`, `reasoning`), enfin `store: false` et `include` (toujours, ajoutés par le traducteur). Un message assistant sans texte ni appel est omis avec ses items `reasoning` (un item seul serait refusé).
- Items `reasoning` : gardés verbatim depuis `response.output_item.done` (ordre de `output_index`) dans `ChatEnd.thinking_blocks`, le canal de la story 3 (`_ModelOutput.thinking`, `thinking_blocks`/`thinking_for` du pas, `Exchange.thinking`) ; `_assistant_message` les pose sous la clé pivot `reasoning_items` si `resend == "reasoning_items"` et l'entrée est la leur ; chaque `summary_text` est attribué par `render.verbatim` (`AppSession._reasoning_item`), le reste (`id`, `encrypted_content`) au gabarit. Masqués (`mask_key`) seulement dans `raw_output`, fait des `output_item.done` reçus. Chaque item garde la clé privée `_follows` (`render.FOLLOWS` : `message` ou `call:<n>`, l'item qui le suivait), retirée par le traducteur, qui le replace juste avant cet item (avant le premier item du tour si son suivant a disparu) ; seuls les items finis (`encrypted_content`) sont gardés. Plusieurs parties de résumé (ou items) sont séparées par « \n\n » au canal Raisonnement.
- Erreurs : `response.incomplete` → `length` (`max_output_tokens`) ou `stopped` (raison citée) ; `error` (forme imbriquée `{type, error: {type, code, message}}` relevée en réel, et forme à plat) est différé jusqu'à `response.failed` ou la fin du flux, pour attacher l'usage qui suit ; `insufficient_quota`/`credit_balance_exhausted` → « le crédit du compte est épuisé » (`no_credit`, helper partagé `cloud_base.no_credit`), aussi pour un 429 `insufficient_quota` (`cloud_base._refused`) ; `context_length_exceeded` (code d'un 400 ou d'un échec) → contexte dépassé ; `server_error` et voisins → indisponible.
- Hors Code Map : éditeur « GPT (OpenAI) » (`^gpt-\d`, ancré : ni GPT4All ni Cerebras-GPT, après Claude) dans `content/models/publishers.yaml` (+ en, de) ; attentes mises à jour dans `tests/test_cloud.py`, `tests/test_cloud_api.py`, `tests/test_model_catalog.py`, `tests/test_backend_messages.py` (périmètre) et le scénario E2E `model_catalog` (`tools/e2e/run_e2e.py`, non rejoué) ; `tests/conftest.py` retire `OPENAI_API_KEY`.
- Mesures réelles (7 requêtes, 0 $) : `_bmad-output/implementation-artifacts/mesures-openai-2026-10.md`. Le compte OpenAI n'a plus de crédit : 200 puis `error` `credit_balance_exhausted` et `response.failed` sans usage. La validation passe avant le crédit : `temperature`/`top_p` acceptés avec l'effort « none », refusés (400) avec « low » → `sampling = ["temperature", "top_p"]` ; corps complet du traducteur (assistant en chaîne, `function_call` à `call_id` du harnais, `function_call_output`) accepté ; deux tours réels par `AppSession` aboutissent au `harness_error` attendu. Restent, crédit ajouté (action d'Anaël) : effort low/medium, items renvoyés avec `id` sous `store: false`, résumé visible (vérification d'organisation), recette Outils + Raisonnement.

## Spec Change Log

## Review Triage Log

Passe 1 (2026-10-03) : blind-hunter (BH), edge-case-hunter (EC), verification-gap (VG).

| # | Source | Constat | Verdict | Preuve | Route |
|---|---|---|---|---|---|
| 1 | BH, EC | Le traducteur met tous les items `reasoning` d'un tour en tête, alors qu'OpenAI peut les entrelacer (rs, fc, rs, fc) ; un item `reasoning` sans l'item qui le suivait est refusé (400) | medium | `render.py` `_openai_responses` : trois groupes (raisonnement, texte, appels) | patch (garder l'ordre de sortie) |
| 2 | EC | Outils Responses envoyés sans `strict` : les fonctions y sont strictes par défaut, et les schémas MCP ou de skills (champs facultatifs, sans `additionalProperties: false`) sont refusés ou forcés | medium | `render.py` l. ~585 | patch (`strict: false` explicite) |
| 3 | BH | Message « Aucun quota actif… vérifiez le plan » pour un compte OpenAI sans crédit (prépayé : il faut ajouter du crédit) | medium | Réutilise `no_quota` ; vu en réel le 2026-10-03 | patch (message « crédit épuisé » fr, en, de) |
| 4 | BH, EC | Détection « sans crédit » écrite deux fois et différente (429 : `insufficient_quota` seul) | low | `cloud_base.py` l. ~594, `openai_responses.py` `_NO_CREDIT` | patch |
| 5 | EC | Appel sans aucun delta et `arguments` vide stocké `""` | low | `openai_responses.py` l. ~187 ; correction directe (`"{}"`) | patch |
| 6 | EC | Item `reasoning` vu seulement à `added` (sans `encrypted_content`) renvoyé quand même | low | l. ~193 ; filtre direct | patch |
| 7 | EC | Annulation reçue après `response.completed` : réponse facturée marquée annulée | low | l. ~93-127 ; garde directe | patch |
| 8 | EC | Motif d'éditeur `gpt[-_ ]?\d` non ancré : GPT4All, Cerebras-GPT, KoGPT2 classés « GPT (OpenAI) » | low | `publishers.yaml` l. 82 | patch (`^gpt-\d`) |
| 9 | BH | Rétention du cache de prompt de 24 h (relevée en mesure) absente de `notes_text` et du README ; numérotation des mesures incohérente avec la story ; nom de test devenu faux ; coupure de ligne du README | low | `mesures-openai-2026-10.md`, `test_cloud_api.py` | patch |
| 10 | VG, BH | Tests manquants : `response.refusal.delta`, repli sur les `arguments` de l'item fini, empreinte de chaque entrée livrée (Luna et Claude), isolement entre deux entrées Responses (Luna puis Sol) | medium | Recherches de VG | patch |
| 11 | BH | Renvoi des items `msg_`/`fc_` sans `id` à côté d'un `rs_` avec `id` : à mesurer avec crédit | maybe-false | Aucune réponse réelle obtenue (crédit épuisé) | defer (mesure à rejouer) |
| 12 | EC | Story acceptée sans les appels réels (mesures 2, 3, 5 et critère de clé réelle) | low | Bloqué par le crédit du compte, consigné | rejeté (consigné dans le rapport et la mémoire) |
| 13 | BH, EC | Cohérence `api` / `max_tokens_field` / `format` non validée ; `include` de l'entrée écrasé ; `sampling_sent` sans section `reasoning` | low | Édition manuelle rare ; gardes nouvelles | rejeté |
| 14 | EC | Objets non-dict ou `error: null` dans le flux ; clés `output_index` contre `id` | low | Spéculatif | rejeté |
| 15 | BH | Fichier de la story absent du diff | false | Fichier non suivi, exclu du diff par l'orchestrateur ; il existe | rejeté |

## Verification

**Commands:**
- `uv run ruff check . ; uv run ruff format --check .` -- expected: aucun écart
- `uv run pytest tests/test_openai_responses.py tests/test_anthropic_messages.py tests/test_cloud_api.py tests/test_cloud.py tests/test_cloud_cap.py tests/test_backend_messages.py -q` -- expected: vert
- `pytest` complet en quatre quarts, un à la fois -- expected: vert
