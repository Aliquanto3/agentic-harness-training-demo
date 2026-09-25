# Vérification technique : amendements cloud du spine WaveStack (FR-43)

- **Date :** 2026-09-24
- **Objet :** `ARCHITECTURE-SPINE.md`, amendements du 2026-09-24 (AD-4 mode chat, AD-5 `openai_chat`, AD-6, AD-9, AD-15, AD-16, AD-20, AD-21, Deferred).
- **Méthode :** lecture préalable de la recherche `technical-api-llm-cloud-gratuites-2026-09-24` (quotas, offres, données : non refait ici) ; documentation officielle des fournisseurs (Groq, Mistral, Microsoft Learn, Google Cloud) ; tickets GitHub datés quand la documentation se tait ; code source de httpx 0.28.1 installé dans le `.venv` du dépôt ; `pyproject.toml` et `src/wavestack/net/` du worktree. Aucun appel réel avec clé : **rien n'a été testé clé en main**. Le spine n'a pas été modifié.
- **Constat général :** les amendements ont été écrits sur le modèle de l'API OpenAI de référence. La recherche d'appui ne couvre pas le protocole de streaming (elle le signale elle-même comme lacune). Plusieurs affirmations d'AD-5 relèvent donc de la mémoire, et deux sont fausses pour Mistral.

## Synthèse

| # | Affirmation du spine | Verdict | Gravité |
| --- | --- | --- | --- |
| 1a | `stream_options.include_usage` accepté par Groq | Confirmé (accepté ; l'usage arrive dans `x_groq.usage` du dernier fragment) | Moyenne |
| 1b | `stream_options.include_usage` accepté par Mistral | **Infirmé** : champ absent de l'API, Mistral rejette les champs inconnus (422 `extra_forbidden`) | **Haute** |
| 2a | Deltas `reasoning` / `reasoning_content` chez Groq | Partiellement confirmé : `reasoning` seulement, et Qwen le met par défaut dans `content` entre `<think>` | Moyenne |
| 2b | Idem chez Mistral | **Infirmé** : `delta.content` devient une **liste** de blocs `thinking` / `text` | **Haute** |
| 2c | Activer ou couper le raisonnement | **Non couvert** : paramètres différents par fournisseur et par modèle | Moyenne |
| 3a | Deltas `tool_calls` fragmentés par `index`, `id` sur le premier fragment | Format compatible, mais Groq et Mistral envoient chaque appel **entier** en un fragment, parfois plusieurs par fragment | Basse |
| 3b | Ids d'appel d'outil libres (actions forcées fabriquées par le harnais) | **Infirmé pour Mistral** : `^[a-zA-Z0-9]{9}$` exigé, sinon 400/422 | **Haute** |
| 3c | Appel mal formé traité par AD-14 | Groq renvoie une **erreur** `tool_use_failed` (avec `failed_generation`) au lieu d'un `tool_calls` | Moyenne |
| 4a | Azure : `base_url` + en-tête `api-key` suffit | Confirmé **pour l'API v1** (`/openai/v1/`) seulement ; `Authorization: Bearer <clé>` y marche aussi | Basse |
| 4b | GCP Vertex exige un jeton OAuth de courte durée | Confirmé (jeton d'accès, 1 h par défaut) | — |
| 5 | Codes d'erreur : 429, 401, 403, 404, délai | **Incomplet** : 413 (Groq, requête plus grosse que le quota par minute), 400 (contexte dépassé, `tool_use_failed`), 422 (Mistral, validation), erreurs en plein flux après un 200 | **Haute** |
| 6a | Groq gpt-oss-120b : 8 000 tokens/min | Confirmé (page officielle relue) | — |
| 6b | `max_window` tenant compte du TPM suffit | **Insuffisant** : TPM compte `prompt + max_tokens` ; un tour de 6 appels dépasse probablement 8 000/min ; le plafond journalier (200 000) borne la séance | **Haute** |
| 7a | httpx : `follow_redirects` vaut `False` par défaut | Confirmé (0.28.1) | — |
| 7b | La clé n'accompagne jamais une redirection | Vrai par défaut seulement ; httpx ne retire que `Authorization`, **pas `api-key`** | Moyenne |
| 8 | Aucune nouvelle dépendance | Confirmé : `httpx>=0.28,<0.29` déjà déclaré | — |

---

## 1. `stream_options.include_usage` et emplacement de l'usage (AD-5)

### 1a. Groq : confirmé, avec un emplacement propre

- Point d'accès : `https://api.groq.com/openai/v1/chat/completions`. `stream_options` est documenté (« Only set this when you set `stream: true` »), sans détail sur `include_usage`.
  Source : [console.groq.com/docs/api-reference](https://console.groq.com/docs/api-reference).
- Groq attache l'usage à **`x_groq.usage` du dernier fragment**. La bibliothèque Go `maruel/genai` (v0.8.1, 18/09/2026) modélise à la fois `stream_options.include_usage` et `x_groq.usage` ; OpenLLMetry corrige la mesure Groq en lisant `chunk.x_groq.usage` (« Groq attaches x_groq.usage to a final chunk »).
  Sources : [pkg.go.dev/github.com/maruel/genai/providers/groq](https://pkg.go.dev/github.com/maruel/genai/providers/groq), [traceloop/openllmetry#4484](https://github.com/traceloop/openllmetry/pull/4484).
- Groq met les tokens en cache dans `usage.prompt_tokens_details.cached_tokens` (gpt-oss seulement).
  Source : [console.groq.com/docs/prompt-caching](https://console.groq.com/docs/prompt-caching).
- **Impact :** si l'adaptateur ne lit que `chunk.usage`, `usage_source` retombe sur `estimate` chez Groq alors que l'usage réel est disponible, et le segment `template` d'AD-4 devient faux.
- **Correctif :** « l'usage se lit dans le dernier fragment qui en porte un : `usage`, sinon `x_groq.usage` ; à défaut, `usage_source = estimate` ».

### 1b. Mistral : infirmé

- La référence de `POST /v1/chat/completions` liste tous les paramètres (`model`, `messages`, `stream`, `max_tokens`, `stop`, `tools`, `tool_choice`, `parallel_tool_calls`, `reasoning_effort`, `prompt_mode`, `response_format`, etc.) : **ni `stream_options` ni `include_usage`**.
  Source : [docs.mistral.ai/api/endpoint/chat](https://docs.mistral.ai/api/endpoint/chat).
- Mistral valide strictement le corps : `{'type': 'extra_forbidden', 'loc': ['body', 'stream_options', 'include_usage'], 'msg': 'Extra inputs are not permitted'}`, en 422, sur `api.mistral.ai/v1`. Toujours vrai fin août 2026 pour le champ `store`.
  Sources : [yetone/avante.nvim#2347](https://github.com/yetone/avante.nvim/issues/2347) (27/06/2025), [aliou/pi-ts-aperture#95](https://github.com/aliou/pi-ts-aperture/issues/95) (28/08/2026).
- Mistral renvoie de lui-même l'usage dans le dernier fragment du flux (source secondaire, confiance moyenne : [theneuralbase.com, streaming token usage](https://theneuralbase.com/mistral-api/learn/beginner/streaming-token-usage/)).
- **Impact :** avec le corps décrit par AD-5, **chaque appel au préréglage Mistral échoue en 422**, y compris le bouton « Tester ». L'une des deux cibles par défaut ne fonctionne pas.
- **Correctif :** retirer `stream_options.include_usage` de la règle générale. En faire un réglage du préréglage (`stream_usage_option: true|false`, vrai pour Groq et Azure, faux pour Mistral). Poser en règle : **le corps n'envoie que les champs acceptés par le préréglage** ; Mistral refuse tout champ inconnu, et Groq refuse `logprobs`, `logit_bias`, `top_logprobs`, `messages[].name` et `n ≠ 1` en 400 ([console.groq.com/docs/openai](https://console.groq.com/docs/openai)).

## 2. Deltas de raisonnement (AD-5, AD-6)

### 2a. Groq : `reasoning` seulement, et pas par défaut pour Qwen

- `reasoning_format` : `parsed` (champ `message.reasoning` dédié), `raw` (dans `content`, entre balises `<think>`), `hidden`. **Défaut : `raw`**, ou `parsed` quand des outils ou le mode JSON sont actifs ; `raw` avec outils renvoie 400.
- gpt-oss-20b et 120b **n'acceptent pas `reasoning_format`**. Ils utilisent `include_reasoning` (vrai par défaut) et `reasoning_effort` (`low|medium|high`), avec le raisonnement dans le champ `reasoning`. `include_reasoning` et `reasoning_format` sont mutuellement exclusifs. Qwen 3.8 27B accepte `reasoning_effort` `none|default|low|medium|high`.
  Source : [console.groq.com/docs/reasoning](https://console.groq.com/docs/reasoning).
- Le nom exact du champ de **delta** en streaming n'est pas écrit dans la documentation ; `reasoning` est la lecture cohérente avec `message.reasoning`. `reasoning_content` n'apparaît nulle part chez Groq (c'est le nom de DeepSeek, vLLM et llama-server).
- **Impact :** sur Qwen chez Groq, sans outils, le raisonnement arrive dans `content` avec ses balises `<think>` : il s'affiche dans le canal `text`. Sur gpt-oss, le raisonnement est toujours émis, même brique raisonnement désactivée.

### 2b. Mistral : infirmé

- Avec `reasoning_effort: "high"` (modèles `mistral-small-latest`, `mistral-medium-3-5` ; valeurs `high` ou `none`), `message.content` est **une liste de blocs** : `{type: "thinking", thinking: [TextChunk…]}` puis `{type: "text", text}`. En streaming, `delta.content` est d'abord une liste contenant un bloc `thinking`, puis une liste mêlant la fin du `thinking` et le premier `text`, puis une simple chaîne. **Aucun champ `reasoning_content`.** Les anciens Magistral passent par `prompt_mode: "reasoning"`.
- Pour une conversation à plusieurs tours, il faut renvoyer le message assistant complet, blocs `thinking` compris.
  Source : [docs.mistral.ai/capabilities/reasoning](https://docs.mistral.ai/capabilities/reasoning).
- La valeur `low` est refusée en 400 : « reasoning_effort='low' is not supported for this model. Must be one of (none, high) » ([aliou/pi-ts-aperture#95](https://github.com/aliou/pi-ts-aperture/issues/95), 28/08/2026).
- **Impact :** un adaptateur qui suppose `delta.content: str` lève une exception ou affiche du JSON dans le canal `text` dès que le raisonnement est actif chez Mistral. Le mapping du spine ne couvre pas le deuxième préréglage.

### 2c. Correctif proposé (2a à 2c)

- AD-5 : « `delta.content` est une chaîne **ou une liste de blocs** ; un bloc `thinking` va au canal `reasoning`, un bloc `text` au canal `text`. Les champs `reasoning` (Groq, OpenRouter) et `reasoning_content` (serveurs de type vLLM ou llama-server) vont au canal `reasoning`. »
- AD-6 : l'entrée `[[cloud.models]]` déclare les **paramètres d'activation** du raisonnement, en données : `reasoning_on = {…}` et `reasoning_off = {…}`. Exemples : gpt-oss chez Groq, `{reasoning_effort="medium"}` et `{include_reasoning=false}` ; Qwen chez Groq, `{reasoning_format="parsed"}` et `{reasoning_effort="none"}` ; Mistral, `{reasoning_effort="high"}` et `{reasoning_effort="none"}`.
- AD-4, mode chat : les messages assistant rejoués dans un tour gardent la forme reçue (blocs `thinking` compris chez Mistral).

## 3. Deltas `tool_calls` et ids d'appel (AD-5, AD-25)

### 3a. Format en streaming : compatible, mais pas fragmenté

- Groq envoie chaque appel d'outil **entier en un seul fragment**, et peut en mettre plusieurs dans le même delta (appels parallèles). Des analyseurs qui ne lisent que le premier élément ou qui concatènent par position perdent ou fusionnent des appels.
  Sources : [BerriAI/litellm#7621](https://github.com/BerriAI/litellm/issues/7621), [wiremuxhq/wiremux#149](https://github.com/wiremuxhq/wiremux/issues/149).
- Mistral envoie aussi chaque appel entier (`id`, `name`, `arguments` complets) ; des appels parallèles peuvent partager un delta. L'absence éventuelle d'`index` sur `api.mistral.ai` n'est pas établie (le SDK Mistral le met à 0 par défaut).
  Sources : [JulienRabault/LLMock#6](https://github.com/JulienRabault/LLMock/issues/6), [comet-ml/opik#8362](https://github.com/comet-ml/opik/issues/8362) (reachability non mesurée par l'auteur).
- La page Groq sur l'appel d'outils ne documente pas le streaming ([console.groq.com/docs/tool-use](https://console.groq.com/docs/tool-use)).
- **Correctif :** « les fragments `tool_calls` s'accumulent par `index`, et, si `index` manque ou se répète avec un nouvel `id`, par `id` ; tous les éléments d'un delta sont lus. » À couvrir par le test préalable (recommandation 6 de la recherche).

### 3b. Ids d'appel : infirmé pour Mistral

- Mistral valide `tool_call_id` : « Tool call id was b9dd800b-… but must be a-z, A-Z, 0-9, with a length of 9. » (`type: invalid_function_call`, `code: 3280`). Les exemples officiels utilisent des ids comme `D681PevKs`.
  Sources : [mistralai/mistral-vibe#1104](https://github.com/mistralai/mistral-vibe/issues/1104) (17/09/2026), [vercel/ai#11802](https://github.com/vercel/ai/issues/11802), [docs.mistral.ai/capabilities/function_calling](https://docs.mistral.ai/capabilities/function_calling).
- Mistral rejetterait aussi (422) un message assistant qui porte à la fois un `content` non vide et des `tool_calls` (source unique, récente, confiance moyenne : [github/copilot-cli#4884](https://github.com/github/copilot-cli/issues/4884), 16/09/2026).
- Le message `tool` de Mistral contient `name` ; Groq refuse `messages[].name` en 400 (§ 1b). À vérifier au test préalable pour les messages `tool`.
- **Impact :**
  - une **action forcée** (AD-25) fabrique un appel d'outil : un id du style `forced-<uuid>` ou `call_…` fait échouer l'appel suivant chez Mistral ;
  - un changement de modèle en cours de conversation (Groq vers Mistral) rejoue des ids Groq refusés par Mistral ;
  - un assistant « texte + appel d'outil » (fréquent avec gpt-oss) rejoué vers Mistral peut être refusé.
- **Correctif :** AD-4, mode chat : « les ids d'appel envoyés sont **normalisés** à la sérialisation : 9 caractères `[a-zA-Z0-9]`, correspondance stable par conversation. Les appels fabriqués reçoivent un id de ce format. » La trace garde l'id d'origine et l'id envoyé. Ajouter un cas au test du moteur factice.

### 3c. Appel mal formé : erreur au lieu d'un `tool_calls`

- Quand le modèle produit un appel invalide (ou du texte alors qu'un outil est forcé), Groq répond par une erreur `tool_use_failed` avec `failed_generation`, en 400, ou en événement d'erreur dans le flux déjà ouvert.
  Sources : [console.groq.com/docs/errors](https://console.groq.com/docs/errors), [pydantic/pydantic-ai#4350](https://github.com/pydantic/pydantic-ai/issues/4350), [langchain4j#2585](https://github.com/langchain4j/langchain4j/issues/2585).
- **Impact :** avec la règle d'AD-16 amendée, un appel mal formé devient un « refus du fournisseur » qui termine le tour. La réaction pédagogique d'AD-14 (nouvel essai, erreur réinjectée) disparaît en mode cloud.
- **Correctif :** « `tool_use_failed` : `failed_generation` devient la sortie brute de l'appel, traitée comme un appel mal formé par AD-14. »

## 4. Azure OpenAI et GCP Vertex (AD-5, Deferred)

### 4a. Azure : confirmé pour l'API v1 seulement

- API v1 (GA, opt-in depuis août 2025) : `base_url = https://<ressource>.openai.azure.com/openai/v1/` (ou `.services.ai.azure.com/openai/v1/`), `api-version` n'est plus exigé, `POST …/chat/completions` avec le **nom du déploiement** dans `model`. En REST, la clé passe par `api-key` ; le client `OpenAI()` standard l'envoie en `Authorization: Bearer <clé>` et fonctionne aussi. Entra ID : `Authorization: Bearer <jeton>`.
  Source : [learn.microsoft.com/…/foundry/openai/api-version-lifecycle](https://learn.microsoft.com/en-us/azure/foundry/openai/api-version-lifecycle) (mise à jour 05/06/2026).
- L'ancien chemin `…/openai/deployments/<d>/chat/completions?api-version=…` ne se construit pas avec `{base_url}/chat/completions` (paramètre de requête obligatoire).
- `stream_options` et `include_usage` existent chez Azure depuis `2024-09-01-preview` (même source).
- **Correctif :** préciser « Azure : API v1 uniquement ». L'en-tête `api-key` n'est pas nécessaire ; `Bearer` suffit et simplifie § 7b.

### 4b. Vertex : confirmé

- Le point d'accès `https://{location}-aiplatform.googleapis.com/v1/projects/{project}/locations/{location}/endpoints/openapi` s'authentifie par un jeton d'accès OAuth. Les exemples officiels le rafraîchissent (`credentials.refresh(...)`, puis `credentials.token` passé comme `api_key`). Le jeton dure 1 h par défaut.
  Sources : [docs.cloud.google.com/…/migrate/openai/auth-and-credentials](https://docs.cloud.google.com/vertex-ai/generative-ai/docs/migrate/openai/auth-and-credentials), [docs.cloud.google.com/docs/authentication/token-types](https://docs.cloud.google.com/docs/authentication/token-types).
- Nuance non tranchée : le mode Express de Vertex accepte des clés API, mais seulement sur `generateContent` d'après les sources trouvées (secondaires). L'affirmation du Deferred reste juste pour le point d'accès compatible OpenAI.

## 5. Codes d'erreur (AD-16)

- **Groq** documente 400, 401, 403, 404, **413**, 422, 424, 429, 498 (capacité Flex), 499 (annulé), 500, 502, 503 ([console.groq.com/docs/errors](https://console.groq.com/docs/errors)). Un 429 porte `retry-after`, et toutes les réponses portent les en-têtes `x-ratelimit-*` ([console.groq.com/docs/rate-limits](https://console.groq.com/docs/rate-limits)).
- **Groq, 413 :** « Request too large for model `openai/gpt-oss-20b` … on tokens per minute (TPM): Limit 8000, Requested 11240 », code `rate_limit_exceeded`. **Non réessayable** : la même requête échoue toujours, même après attente.
  Sources : [inferenceapis.com, groq-413](https://inferenceapis.com/reference/errors/groq-413-request-too-large) (vérifié le 16/09/2026), [dev.to, rate limit on max_tokens](https://dev.to/build996/a-rate-limit-that-counts-the-tokens-you-asked-for-not-the-ones-you-got-1oda).
- **Groq, contexte dépassé :** code d'erreur `context_length_exceeded` (type `invalid_request_error`), en 400 selon toute vraisemblance ([pkg.go.dev maruel/genai](https://pkg.go.dev/github.com/maruel/genai/providers/groq)).
- **Mistral :** contexte dépassé en 400 (sources secondaires : [krater.ai](https://krater.ai/troubleshoot/mistral/context-length-exceeded)) ; validation du corps en 422 (§ 1b, § 3b) ; **pas de `Retry-After` sur 429**, seulement `x-ratelimit-limit-req-minute` et `x-ratelimit-remaining-req-minute`, selon une réponse du support citée dans [mistralai/mistral-vibe#1133](https://github.com/mistralai/mistral-vibe/issues/1133). La formulation « `Retry-After` s'il est fourni » est donc correcte.
- **Erreurs en plein flux :** Groq envoie certaines erreurs comme un événement SSE après le 200 ; une passerelle compatible Mistral a renvoyé un JSON d'erreur sans cadrage SSE ([mistral-vibe#1104](https://github.com/mistralai/mistral-vibe/issues/1104)).
- **Impact :** AD-16 ne prévoit ni 413, ni 400, ni 422, ni l'erreur après un 200. Une erreur 400/422 due au harnais lui-même (champ refusé, id invalide) serait affichée en « clé refusée » ou en erreur générique ; un 413 serait présenté comme un quota qui se rétablira.
- **Correctif :** compléter la liste d'AD-16 :
  - 413 : « requête plus grosse que le quota par minute : réduisez la fenêtre » (aucun essai) ;
  - 400 : contexte dépassé (message du fournisseur, piste « réduire la fenêtre ») ou `tool_use_failed` (§ 3c) ;
  - 400 ou 422, autre cas : « requête refusée par le fournisseur », avec le message brut en cause (c'est un défaut du harnais ou du préréglage) ;
  - un objet `error` reçu dans le flux, ou une ligne non SSE, termine l'appel en `stop_reason: error` avec son contenu.
  - Le test préalable (`test_cloud_model`) doit envoyer le corps réel complet (outils, raisonnement, appel fabriqué), pas un appel minimal, pour attraper les 400/422 de préréglage.

## 6. Quota Groq et fenêtre (AD-9)

- **8 000 tokens/min pour gpt-oss-120b : confirmé** (30 req/min, 1 000 req/jour, 8 000 tokens/min, 200 000 tokens/jour ; mêmes valeurs pour gpt-oss-20b et `qwen/qwen3.8-27b`).
  Source : [console.groq.com/docs/rate-limits](https://console.groq.com/docs/rate-limits) (relue le 24/09/2026 ; le nom `qwen3.8-27b`, jugé douteux par la recherche, apparaît aussi sur la page Raisonnement).
- **Le TPM compte `prompt + max_tokens` demandés**, pas la sortie réelle : une requête de 20 tokens avec `max_tokens: 8192` reçoit un 413 (« Requested 8271 »).
  Sources : [inferenceapis.com](https://inferenceapis.com/reference/errors/groq-413-request-too-large), [dev.to](https://dev.to/build996/a-rate-limit-that-counts-the-tokens-you-asked-for-not-the-ones-you-got-1oda) (secondaires, concordantes).
- **Les tokens en cache ne comptent pas dans les limites** (gpt-oss seulement, cache automatique, non garanti).
  Source : [console.groq.com/docs/prompt-caching](https://console.groq.com/docs/prompt-caching).
- **Un appel isolé :** AD-9 envoie `max_tokens = réserve` et refuse un prompt au-delà de `usable = fenêtre − réserve`. Donc `prompt + max_tokens ≤ fenêtre`, et `max_window ≤ 8 000` suffit à éviter le 413. Ce point tient.
- **Un tour à plusieurs appels (jusqu'à 6) : oui, il dépasse probablement le TPM.** Chaque appel renvoie tout le contexte, plus sa réserve (512, ou 1 536 avec raisonnement). Exemple sans cache : 3 appels de 3 000 tokens de prompt plus 512 de réserve, soit 10 500 tokens en moins d'une minute : 429 au 3e appel. Même avec un cache parfait, 6 réserves de 1 536 tokens font 9 216 tokens. Le comptage exact des réserves dans la fenêtre glissante n'est pas documenté : **non vérifiable** sans clé, mais probable.
- **Plafond journalier :** 200 000 tokens/jour, contre environ 200 requêtes par demi-journée (cadre de la recherche) × 3 000 à 5 000 tokens, soit 600 000 à 1 000 000 tokens. Hors cache, **la séance s'arrête bien avant la fin** chez Groq sur ces modèles. La recherche ne l'a pas relevé ; c'est un risque produit, pas seulement d'architecture.
- **Impact :** la règle « sans nouvel essai automatique » (AD-16) transforme chaque dépassement de minute en fin de tour en erreur, au milieu d'une boucle d'outils, ce qui sera fréquent chez Groq.
- **Correctif :**
  - AD-9 : « `max_window` ≤ quota par minute du préréglage ; valeur par défaut conseillée pour Groq : environ 4 000 tokens, pour laisser passer un tour à deux ou trois appels ».
  - AD-16 : décider explicitement. Soit on garde « aucun essai » en l'assumant, et en affichant la jauge de quota tirée des en-têtes `x-ratelimit-remaining-tokens` ; soit on autorise **une** attente visible et annulable quand `retry-after` ≤ quelques secondes, tracée comme événement pédagogique.
  - Recherche ou préréglages : signaler le plafond de 200 000 tokens par jour dans l'infobulle Groq, et relever le quota journalier réel à la vérification avant séance.

## 7. httpx et redirections (AD-15)

- **`follow_redirects=False` par défaut : confirmé.** Le code de httpx 0.28.1 installé déclare `follow_redirects: bool = False` pour `Client.__init__`, `request` et `stream` (`httpx/_client.py`, lignes 197, 654, 1367). Documentation : « Unlike requests, HTTPX does not follow redirects by default » ([python-httpx.org/compatibility](https://www.python-httpx.org/compatibility/#redirects)).
- **httpx retire lui-même `Authorization`, et seulement lui.** `_redirect_headers` (lignes 546 à 556) supprime `Authorization` quand la redirection change d'origine, sauf pour une simple montée de http vers https sur le même hôte. **L'en-tête `api-key` d'Azure, lui, serait transmis** à l'hôte de destination.
  Source : `httpx/_client.py` 0.28.1, [github.com/encode/httpx/blob/0.28.1/httpx/_client.py](https://github.com/encode/httpx/blob/0.28.1/httpx/_client.py).
- Dans le dépôt, `tools/network.py` passe `follow_redirects=True` par requête sur le client partagé de `net` ; le client de `create_client` a un délai de 5 s par défaut (à relever pour un flux).
- **Impact :** l'affirmation « la clé n'accompagne jamais une redirection » repose sur un défaut implicite, pas sur une règle. Un futur appel avec `follow_redirects=True`, ou un client partagé reconfiguré, enverrait `api-key` à un autre hôte. La garde d'hôtes autorisés bloque les hôtes inconnus, mais pas un autre hôte de la liste (par exemple un serveur MCP public).
- **Correctif :** AD-15 : « l'appel au modèle cloud passe `follow_redirects=False` explicitement ; une réponse 3xx est une erreur (`harness_error`, cause "redirection refusée") ». Utiliser `Authorization: Bearer` pour Azure v1 (§ 4a) plutôt que `api-key`. Un test avec `httpx.MockTransport` qui renvoie un 302 vérifie qu'aucune seconde requête ne part.

## 8. Dépendances

- `pyproject.toml` du worktree : `httpx>=0.28,<0.29` est déjà une dépendance (et `httpx2>=2.13,<3` pour le client MCP asynchrone). `net/factory.py` fabrique déjà le `httpx.Client` synchrone. **Confirmé : aucune nouvelle dépendance n'est nécessaire.** Le SSE se lit avec `client.stream(...)` et `iter_lines()`, sans bibliothèque en plus.

## Hors liste, relevé en passant

- **Port `Engine` (AD-5, ligne 191).** La signature reste `complete(prompt_ids | prompt_text, stop, max_tokens, cancel)`, alors que `openai_chat` « reçoit messages et outils structurés ». Il faut soit élargir la signature (`prompt_ids | prompt_text | chat_body`), soit le dire explicitement. Ce n'est pas une affirmation vérifiable sur le web, mais c'est une incohérence interne.
- **Mistral `tool_choice`.** Les valeurs sont `auto`, `none`, `any`, `required` ou une fonction nommée ([docs.mistral.ai/api/endpoint/chat](https://docs.mistral.ai/api/endpoint/chat)). Si le harnais force un outil par l'API plutôt qu'en fabriquant l'appel, la valeur diffère d'un fournisseur à l'autre ; aujourd'hui AD-25 fabrique l'appel, donc sans effet.

## Correctifs à reporter dans le spine (par priorité)

1. AD-5 : `stream_options` devient un réglage du préréglage (faux pour Mistral) ; corps limité aux champs acceptés ; usage lu dans `usage` ou `x_groq.usage`.
2. AD-5 : `delta.content` peut être une liste de blocs `thinking`/`text` (Mistral) ; champs `reasoning` et `reasoning_content` ; paramètres d'activation et de coupure du raisonnement déclarés par modèle (AD-6).
3. AD-4 mode chat et AD-25 : ids d'appel normalisés en 9 caractères alphanumériques ; appels fabriqués conformes.
4. AD-16 : 413 (non réessayable), 400 (contexte, `tool_use_failed` renvoyé vers AD-14), 400/422 génériques, erreurs en plein flux ; test préalable avec le corps complet.
5. AD-9 et AD-16 : fenêtre Groq par défaut sous le TPM pour un tour à plusieurs appels ; décision explicite sur une attente unique ; plafond journalier dans l'infobulle.
6. AD-15 : `follow_redirects=False` explicite, 3xx en erreur ; `Bearer` pour Azure v1.
