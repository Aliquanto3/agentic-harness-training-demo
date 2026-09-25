# Vérification factuelle : passe « Update » cloud du spine (FR-43)

- **Date :** 2026-09-24
- **Objet :** `ARCHITECTURE-SPINE.md` après intégration des retours cloud (AD-4 mode chat, AD-5 `openai_chat`, AD-6, AD-9, AD-10, AD-15, AD-16, AD-20, AD-21, Deferred).
- **Point de départ :** `review-cloud-verification.md`. Ce qui y est sourcé n'est pas refait ; on contrôle (1) que le spine en a tiré les bonnes conséquences, (2) les affirmations nouvelles.
- **Méthode :** documentation officielle (Groq, Mistral, Microsoft Learn, pydantic), code source de httpx 0.28.1 sur GitHub, code du worktree (`src/wavestack/net/factory.py`, `models/engine.py`, `web/app.py`). Aucun appel avec clé : **rien n'a été testé en réel**. L'exécution Python locale n'a pas été possible (refusée par le classifieur de permissions) : les comportements pydantic et httpx sont tirés de la documentation et du code source publiés.
- **Incident à signaler :** une commande `uv run --no-sync` lancée dans le worktree cloud y a créé un dossier `.venv` **vide** (20:43, 4 fichiers dans `site-packages`, aucun paquet). La suppression a été refusée par le classifieur. Il faut le supprimer à la main (`Remove-Item -Recurse .venv` dans `agentic-harness-training-demo-cloud`) ou lancer `uv sync`. Le spine n'a pas été modifié.

## Verdict global

Le spine a bien repris les six correctifs prioritaires de la vérification précédente : `stream_usage`, `x_groq.usage`, blocs `thinking`, ids à 9 caractères, 413/400/422, erreurs dans le flux, `follow_redirects=False`, Bearer pour Azure v1, `tool_use_failed` vers AD-10, signature `Engine` élargie. La formule `tpm // 2` est juste dans son périmètre. Il reste **trois défauts qui peuvent faire échouer un appel réel** : `max_tokens` codé en dur (refusé par les modèles de raisonnement Azure), pas de `Content-Type` sur un corps envoyé en octets, délai de lecture de 5 s hérité de la fabrique. S'y ajoutent **deux fuites ou pertes de clé** possibles, liées à `SecretStr` et aux 422 de FastAPI, et **un choix contraire à la consigne explicite de Mistral** : ne pas renvoyer le raisonnement.

## Synthèse

| # | Affirmation du spine | Verdict | Gravité | Source |
| --- | --- | --- | --- | --- |
| 1 | AD-5 : `stream_options.include_usage` seulement si `stream_usage` ; usage lu dans `usage`, sinon `x_groq.usage` | Confirmé (correctif repris) | — | Vérif. précédente § 1 ; [docs.mistral.ai/api/endpoint/chat](https://docs.mistral.ai/api/endpoint/chat) (aucun `stream_options`, relu) |
| 2 | AD-5 : `delta.content` chaîne ou liste de blocs `thinking`/`text` | Confirmé | — | [docs.mistral.ai/capabilities/reasoning](https://docs.mistral.ai/capabilities/reasoning) |
| 3 | AD-4 : le raisonnement n'est jamais renvoyé au fournisseur | **Contraire à la doc Mistral** (« IMPORTANT… Do not strip ThinkChunk »). Assumé en Deferred, mais la doc Mistral en fait une obligation | **Moyenne** | [docs.mistral.ai/capabilities/reasoning](https://docs.mistral.ai/capabilities/reasoning) |
| 4 | AD-4 : `tool_call_id` à 9 caractères `[A-Za-z0-9]`, id du fournisseur remplacé | Confirmé, conforme à `^[a-zA-Z0-9]{9}$` de Mistral ; Groq et Azure acceptent toute chaîne | — | Vérif. précédente § 3b |
| 5 | AD-4 : corps sérialisé par `json.dumps(ensure_ascii=False, separators=(",", ":"))` | Juste, et identique à l'encodage `json=` de httpx 0.28.1, **sauf `allow_nan=False`** que httpx ajoute | Basse | [httpx/_content.py 0.28.1](https://github.com/encode/httpx/blob/0.28.1/httpx/_content.py) |
| 6 | AD-5 : l'adaptateur envoie le `ChatBody` octet pour octet et « n'y ajoute que l'en-tête d'authentification » | **Incomplet** : avec `content=bytes`, httpx ne pose que `Content-Length`, **pas de `Content-Type: application/json`** ; la fabrique ajoute aussi `User-Agent` | **Moyenne** | [httpx/_content.py 0.28.1](https://github.com/encode/httpx/blob/0.28.1/httpx/_content.py) ; `net/factory.py` l. 67 |
| 7 | AD-4 : corps = `model, messages, tools, stream, max_tokens` + champs déclarés | **Faux pour les modèles de raisonnement Azure** (GPT-5, série o, GPT-6 Astra) : `max_tokens` n'est pas pris en charge, seul `max_completion_tokens` l'est. Chez Groq, `max_tokens` est déprécié mais accepté ; Mistral n'accepte que `max_tokens` | **Haute** (Azure) | [learn.microsoft.com/…/how-to/reasoning](https://learn.microsoft.com/en-us/azure/foundry/openai/how-to/reasoning) (maj. 22/09/2026) ; [console.groq.com/docs/api-reference](https://console.groq.com/docs/api-reference) |
| 8 | AD-5 : `finish_reason` : `stop`/`tool_calls` → stop, `length` → length, tout autre → error | Incomplet : Mistral a aussi `model_length` (limite de contexte du modèle), qui devient `error` au lieu de `length` | Basse | [saarnilauri/ai-provider-for-mistral#8](https://github.com/saarnilauri/ai-provider-for-mistral/pull/8), [pi-go.sh, Mistral pitfalls](http://pi-go.sh/blog/mistral-provider-pitfalls/) |
| 9 | AD-2 : `raw_output` = suite des `choices[0].delta` | Imprécis : Azure envoie un premier fragment à `choices: []` (`prompt_filter_results`), et le fragment d'usage OpenAI/Azure a aussi `choices: []` | Moyenne | [learn.microsoft.com, content streaming](https://learn.microsoft.com/en-us/azure/foundry/openai/concepts/content-streaming), [langfuse#2833](https://github.com/langfuse/langfuse/issues/2833), [semantic-kernel#3650](https://github.com/microsoft/semantic-kernel/issues/3650) |
| 10 | AD-5/AD-16 : une « ligne non SSE » après un 200 termine l'appel en erreur | À préciser : selon la norme SSE, une ligne `:` (commentaire), une ligne vide, `event:`, `id:` ou `retry:` sont valides | Basse | Norme WHATWG SSE (connaissance, non refetchée) |
| 11 | AD-5 vs AD-10/AD-16 : `tool_use_failed` suit AD-10, mais tout objet `error` dans le flux → `stop_reason: error` | **Incohérence interne** : chez Groq, `tool_use_failed` arrive aussi comme erreur **dans le flux** ; il faut dire lequel l'emporte | Moyenne | Vérif. précédente § 3c |
| 12 | AD-5 : Azure « par son API v1 seulement », Bearer par défaut | Confirmé : exemple officiel `OpenAI(api_key=AZURE_OPENAI_API_KEY, base_url=…/openai/v1/)`, donc clé en `Authorization: Bearer` | — | [learn.microsoft.com/…/api-version-lifecycle](https://learn.microsoft.com/en-us/azure/foundry/openai/api-version-lifecycle) |
| 13 | AD-6/AD-20 : `reasoning.on`/`off` déclarés par modèle | Juste dans son principe ; valeurs à vérifier : la doc Groq se contredit sur Qwen 3.8 27B (`none|default|low|medium|high` sur la page Raisonnement, `low|medium|high` dans la référence API) | Basse | [console.groq.com/docs/reasoning](https://console.groq.com/docs/reasoning), [console.groq.com/docs/api-reference](https://console.groq.com/docs/api-reference) |
| 14 | AD-9 : fenêtre ≤ `tpm // 2` ; deux appels tiennent dans la minute (4 000 pour gpt-oss-120b) | Arithmétique juste si le TPM compte `prompt + max_tokens` (sources secondaires concordantes). Plafond : repose sur des tokens **estimés** (ratio), sans marge ; 3e appel, sous-agent ou tour suivant dans la minute → 429, ce que le spine assume | Basse | Vérif. précédente § 6 |
| 15 | AD-9 + AD-6 : réserve de 1 536 quand `reasoning.always` (gpt-oss) | Conséquence non dite : `usable` = 4 000 − 1 536 = **2 464 tokens** chez Groq gpt-oss, catalogue d'outils compris ; `length` probable en effort `medium` | Moyenne (produit) | Calcul ; non vérifiable sans clé |
| 16 | AD-15 : `follow_redirects=False` explicite, 3xx → `harness_error` | Confirmé ; rend inopérant le fait que httpx ne retire que `Authorization` | — | `httpx/_client.py` 0.28.1 (vérif. précédente § 7) |
| 17 | AD-15 : « des délais bornés » ; AD-16 « délai dépassé » | **Correctif précédent non repris** : `create_client` a `timeout=5.0` (lecture comprise). Un modèle de raisonnement ou un long prompt peut dépasser 5 s avant le premier octet | **Moyenne** | `net/factory.py` l. 56 et 64 |
| 18 | AD-15 : la clé est un `SecretStr` de bout en bout (intention, effet, adaptateur) | Juste pour le masquage, mais **piège à l'écriture** : `model_dump_json()` écrit `"**********"`, `json.dumps(model_dump())` lève `TypeError`. `api_keys.json` peut donc recevoir des astérisques, suivis d'un 401 affiché « clé refusée » | **Moyenne** | [pydantic, SecretStr](https://pydantic.dev/docs/validation/latest/api/pydantic/types/) |
| 19 | AD-15 : « une réponse d'intention ne renvoie jamais ce qu'elle a reçu » | **Pas garanti par la pile** : les intentions sont des corps pydantic parsés par FastAPI (`web/app.py`), sans gestionnaire `RequestValidationError`. Le 422 par défaut renvoie `detail[].input`, qui peut contenir la clé | **Moyenne** | `web/app.py` (aucun `exception_handler`) ; comportement FastAPI par défaut (connaissance, non ré-exécuté) |
| 20 | AD-16 : liste **fermée** des issues cloud | Pas de cas « autre code » : Groq documente 424, 498 et 499. 404 = « modèle retiré », alors qu'une erreur de `base_url` ou de nom de déploiement Azure donne aussi 404 | Basse | [console.groq.com/docs/errors](https://console.groq.com/docs/errors) (vérif. précédente § 5) |
| 21 | AD-5 : signature `complete(request: RenderedPrompt \| ChatBody, cancel)` | Incohérence précédente corrigée dans le spine ; le code (`models/engine.py` l. 57-59) a encore l'ancienne signature (normal, à faire par la story) | — | `models/engine.py` |
| 22 | AD-20 : `CloudModel` avec `extra = "forbid"`, sans champ de clé ; `api_keys.json {id: {host, key}}` | Juste (`ConfigDict(extra="forbid")`) ; bonne règle de liaison clé-hôte | — | pydantic |
| 23 | Plafond Groq de 200 000 tokens par jour | **Non repris** dans le spine (ni infobulle, ni `notes_fr`) | Basse | Vérif. précédente § 6 |
| 24 | Message `tool` : `name` refusé par Groq (`messages[].name`), présent dans les exemples Mistral | Non tranché dans le spine (la forme du message `tool` n'est pas fixée) | Basse | Vérif. précédente § 3b |

---

## Détails et correctifs

### 1. `max_tokens` en dur dans le corps (AD-4, AD-5, AD-9) : haute pour Azure

- Microsoft Learn, page des modèles de raisonnement (mise à jour du 22/09/2026) : « Reasoning models will only work with the `max_completion_tokens` parameter when using the Chat Completions API ». `max_tokens` figure dans la liste des paramètres non pris en charge, avec `temperature`, `top_p`, `logprobs`, etc.
- Groq : `max_tokens` est « Deprecated in favor of `max_completion_tokens` », encore accepté.
- Mistral : seul `max_tokens` existe, et un champ inconnu est refusé en 422 (`extra_forbidden`). On ne peut donc pas passer à `max_completion_tokens` pour tout le monde.
- **Impact :** un point d'accès Azure v1 qui sert un GPT-5 (cas probable pour un point d'accès interne) échoue à chaque appel, test compris, en « requête refusée par le fournisseur ». Le Prevents d'AD-5 (« un préréglage qui échoue dès le premier appel ») n'est pas tenu.
- **Correctif :** champ `max_tokens_field: max_tokens | max_completion_tokens` dans `CloudModel`. Défaut `max_tokens` ; `max_completion_tokens` pour Azure (modèles de raisonnement) et pour Groq, où il est conseillé. AD-4 construit le corps avec ce nom. AD-9 parle de « limite de sortie » plutôt que de `max_tokens`.

### 2. En-têtes réellement envoyés (AD-5) : moyenne

- httpx 0.28.1, `encode_content` : pour `content=bytes`, seul `Content-Length` est posé. Pour `json=`, httpx pose `Content-Type: application/json` et sérialise avec `ensure_ascii=False, separators=(",", ":"), allow_nan=False`.
- Le spine envoie des octets (à juste titre, pour garantir « corps tracé = corps envoyé »). Sans `Content-Type`, certains frontaux (APIM Azure, passerelle interne) peuvent répondre 400 ou 415. Ce n'est pas vérifiable sans clé, mais c'est gratuit à éviter.
- La fabrique `net` ajoute déjà `User-Agent: WaveStack/0.1 …` (`net/factory.py` l. 67). La phrase « n'y ajoute que l'en-tête d'authentification » est donc littéralement fausse.
- **Correctif :** « l'adaptateur n'ajoute rien au **corps** ; il pose `Content-Type: application/json`, `Accept: text/event-stream` et l'en-tête d'authentification ; le `User-Agent` vient de `net` ». Ajouter `allow_nan=False` au `json.dumps` d'AD-4, pour s'aligner sur httpx et refuser un `NaN` qui produirait du JSON invalide.
- Au passage : `.encode("utf-8")` lève une exception sur un substitut isolé (`\ud800`), qu'un résultat d'outil MCP décodé depuis du JSON peut contenir. La normalisation de l'étape 2 peut les retirer, comme la zone privée Unicode.

### 3. Délai de lecture du flux (AD-15, AD-16) : moyenne, correctif précédent non repris

- `create_client(timeout=5.0)` applique 5 s à la connexion **et à la lecture**. En streaming, httpx compte le délai de lecture entre deux blocs reçus, y compris l'attente des en-têtes de réponse.
- Mistral en `reasoning_effort: high`, Azure GPT-5, ou un prompt de 4 000 tokens chez un fournisseur chargé peuvent dépasser 5 s avant le premier octet : on aurait des « délai dépassé » intermittents.
- **Correctif :** AD-15 : « pour `origin = model`, délai de connexion 10 s, de lecture 60 s (réglables dans `wavestack.toml`) ; l'annulation reste le recours de l'utilisateur ».

### 4. Raisonnement non renvoyé (AD-4, Deferred) : moyenne

- Doc Mistral : « IMPORTANT: append the full assistant message to history. This preserves ThinkChunk… Do not strip `ThinkChunk` from assistant messages before replaying them. »
- Pour gpt-oss, le format harmony d'OpenAI demande aussi de garder le raisonnement qui précède un appel d'outil pendant le même tour (connaissance, non refetchée ; Groq ne documente pas le renvoi).
- Le spine a choisi l'inverse (« jamais renvoyé, ni du tour ni de l'historique ») et l'a mis en Deferred avec un déclencheur. Le choix se défend (pas de segment de raisonnement, jauge plus simple), mais le Deferred le présente comme une optimisation à revoir, alors que la doc Mistral en fait une obligation.
- **Correctif minimal :** dans le Deferred, écrire que c'est un **écart assumé à la consigne Mistral**, et ajouter au test du modèle (AD-21) un tour à deux appels avec raisonnement actif chez Mistral. Correctif complet : renvoyer le raisonnement **du tour en cours** seulement (blocs `thinking` chez Mistral), en segment `assistant_turn`. C'est une vraie décision d'architecture, à trancher.

### 5. Fragments sans `choices` et « ligne non SSE » (AD-2, AD-5) : moyenne à basse

- Azure (filtrage de contenu actif par défaut) envoie un premier fragment `{"choices": [], "prompt_filter_results": […]}`. Avec `include_usage`, le dernier fragment d'usage a aussi `choices: []`. Un adaptateur qui lit `choices[0]` lève `IndexError` (cas documentés : langfuse, semantic-kernel).
- **Correctif :** AD-5 : « un fragment sans `choices` est lu pour `usage` et ignoré pour les canaux ». AD-2 : « `raw_output` est la suite des fragments reçus » (ou des `delta`, s'il y en a). Ajouter ce cas au test `MockTransport`.
- « Ligne non SSE » : préciser qu'une ligne vide, une ligne commentaire (`:`) ou un champ `event:`, `id:` ou `retry:` sont valides. Seule une ligne qui n'est pas de la forme `champ: valeur`, ou un `data:` qui n'est pas du JSON (hors `[DONE]`), est une erreur.

### 6. `tool_use_failed` dans le flux (AD-5, AD-10, AD-16) : moyenne

- AD-5 : « un objet `error` […] reçu après un 200 termine l'appel par `stop_reason: error` (AD-16) ». AD-16 et AD-10 : `tool_use_failed` n'est pas une issue d'erreur, il suit le nouvel essai.
- Chez Groq, `tool_use_failed` arrive **en 400 ou dans le flux déjà ouvert**. Tel qu'écrit, le second cas tombe dans la règle d'AD-5 et termine le tour.
- **Correctif :** AD-5 : « un objet `error` de code `tool_use_failed`, en réponse HTTP ou dans le flux, termine l'appel en appel mal formé (AD-10), avec `failed_generation` pour sortie brute ; tout autre objet `error` → `stop_reason: error` ».

### 7. `SecretStr` : écriture de `api_keys.json` et réponses 422 (AD-15, AD-20) : moyenne

- pydantic : `SecretStr` est sérialisé en `"**********"` par `model_dump_json()` ; `model_dump()` renvoie l'objet `SecretStr`, que `json.dumps` refuse. Pour écrire la vraie valeur, il faut `get_secret_value()` ou un `field_serializer(when_used="json")`.
- **Risque 1, perte silencieuse :** l'effet qui écrit `api_keys.json` via pydantic enregistre des astérisques ; `key_set` passe à vrai, puis le fournisseur répond 401, affiché « clé refusée ». Le formateur croit à une mauvaise clé.
- **Risque 2, écho de la clé :** `web/app.py` déclare les intentions en corps pydantic, sans gestionnaire `RequestValidationError`. Le 422 par défaut de FastAPI renvoie `detail[].input`, soit la valeur fautive, soit le corps entier (un `id` invalide avec une clé valide renvoie la clé en clair). Le risque est local (même navigateur), mais contredit la règle d'AD-15.
- **Correctif :** AD-15 : « seule l'écriture de `api_keys.json` et la pose de l'en-tête appellent `get_secret_value()` ; un test relit `api_keys.json` et vérifie la clé ». « Un gestionnaire `RequestValidationError` renvoie les erreurs sans `input` (au moins pour `set_api_key`) ». Le test à clé sentinelle doit inclure une intention `set_api_key` **invalide**.

### 8. AD-9 et la réserve de raisonnement (AD-6) : moyenne, côté produit

- La formule `min(…, tpm // 2)` est correcte. La phrase « deux appels tiennent dans la minute » est juste si le TPM compte `prompt + max_tokens` à l'admission (sources secondaires concordantes, non testé) et si l'estimation du prompt n'est pas trop basse (aucune marge au-delà du facteur 2).
- Conséquence non écrite : avec `reasoning.always` (gpt-oss chez Groq), la réserve est de 1 536 tokens sur une fenêtre de 4 000, soit `usable = 2 464` tokens pour le prompt système, le catalogue d'outils, les documentations MCP et l'historique. Le scénario MCP en « documentation complète » débordera, et gpt-oss en effort `medium` risque la coupure `length` avant l'appel d'outil.
- **Correctif :** dire en AD-9 que la fenêtre cloud est affichée avec son `usable` réel. Dans l'entrée Groq gpt-oss, poser `reasoning.on = {reasoning_effort = "low"}` par défaut. Le test du modèle doit aussi vérifier qu'un appel d'outil tient dans la réserve.

### 9. Points mineurs

- **Mistral `model_length`** : le rattacher à `length` (même traitement qu'AD-9), et `error` à `error`.
- **Qwen 3.8 27B chez Groq** : les deux pages de Groq se contredisent sur `reasoning_effort: none`. Mieux vaut poser `on = {reasoning_format = "parsed"}` (le raisonnement arrive alors dans `reasoning`, avec ou sans outils) et vérifier `off` au test.
- **AD-16, liste fermée** : ajouter « autre code : erreur du fournisseur, code et message cités » ; libeller le 404 « modèle ou adresse introuvable ».
- **Message `tool`** : fixer sa forme à `{role, tool_call_id, content}`, sans `name` (Groq refuse `messages[].name`), à confirmer au test chez Mistral.
- **Plafond journalier Groq** (200 000 tokens) : le mettre dans `notes_fr` du préréglage (AD-19/AD-20).
- **`auth_header` = « Authorization: Bearer »** : une seule chaîne mélange le nom d'en-tête et le schéma. Deux champs (`auth_header = "Authorization"`, `auth_scheme = "Bearer" | ""`) évitent un analyseur ad hoc. Détail de conception, sans effet factuel.

## Correctifs à reporter (par priorité)

1. AD-4/AD-20 : nom du champ de limite de sortie déclaré par entrée (`max_tokens` ou `max_completion_tokens`).
2. AD-15 : délai de lecture propre à `origin = model` (lecture ≥ 60 s).
3. AD-5 : `Content-Type: application/json` (et `Accept`) posé par l'adaptateur ; corps inchangé.
4. AD-15 : `get_secret_value()` à l'écriture de `api_keys.json`, avec un test de relecture ; 422 FastAPI sans `input`.
5. AD-5 : `tool_use_failed` dans le flux → AD-10 ; fragments sans `choices` ; définition de la ligne non SSE.
6. AD-4/Deferred : renvoi du raisonnement présenté comme un écart à la consigne Mistral, avec un cas au test.
7. Mineurs du § 9.
