# Vérification technique : mise à jour R01 à R04 du spine WaveStack

- **Date :** 2026-09-23
- **Objet :** `ARCHITECTURE-SPINE.md` (AD-2, AD-4, AD-5, AD-9, AD-15, AD-21, table Stack)
- **Méthode :** lecture du code source des versions épinglées, installées dans un environnement jetable (Python 3.13.13 géré par uv, Windows 11) ; tests exécutés localement ; code source amont sur GitHub ; documentation officielle. Le spine n'a pas été modifié.

Versions installées et confirmées : huggingface_hub 1.32.0, fastapi 0.141.1, uvicorn 0.53.0, Jinja2 3.1.6, httpx 0.28.1, llama-cpp-python 0.3.35 (roue CPU de l'index abetlen, installée sans compilation).

## Synthèse

| # | Affirmation | Verdict | Gravité |
| --- | --- | --- | --- |
| 1a | L'événement d'audit `socket.connect(self, address)` existe en 3.13 | Confirmé | — |
| 1b | Un hook `sys.addaudithook` qui lève une exception bloque la connexion | Confirmé (connexions synchrones et boucle Selector) | — |
| 1c | Le hook voit aussi les connexions asyncio, anyio et httpx async | **Infirmé sous Windows** avec la boucle par défaut (Proactor), qui est celle d'uvicorn | **Haute** |
| 2a | `HF_HUB_OFFLINE` est lu à l'import et bloque ensuite les téléchargements | Confirmé | — |
| 2b | `HF_HUB_DISABLE_TELEMETRY` et `HF_HUB_DISABLE_XET` existent | Confirmé | — |
| 2c | `set_client_factory` existe (client httpx injectable) | Confirmé | — |
| 2d | (constat annexe) Les domaines de téléchargement se limitent à `huggingface.co` | **Infirmé** : redirection vers `*.cdn.hf.co` | Moyenne |
| 3a | Signatures `detokenize(tokens, prev_tokens=None, special=False)` et `tokenize(text: bytes, add_bos=True, special=False)` | Confirmé | — |
| 3b | La concaténation des `detokenize([id], special=True)` redonne les octets exacts | **Infirmé en pratique** : vrai pour le BPE byte-level, mais `Llama.detokenize` perd les tokens de plus de 32 octets | **Haute** |
| 4a | Jinja2 3.1.6 : `ImmutableSandboxedEnvironment` et `loopcontrols` | Confirmé | — |
| 4b | transformers applique toujours `trim_blocks`, `lstrip_blocks`, `tojson(ensure_ascii=False)` | Confirmé, avec deux écarts mineurs (extension `generation`, paramètres de `tojson`) | Basse |
| 5 | litellm récupère la table des prix depuis GitHub à l'import, sauf avec `LITELLM_LOCAL_MODEL_COST_MAP` | Confirmé | Moyenne pour le test préalable de Headroom |
| 6 | `fastapi.sse.EventSourceResponse` existe en 0.141.1 | Confirmé | — |

---

## 1. Python 3.13 : garde réseau par `sys.addaudithook` (AD-15)

### 1a. L'événement existe : confirmé

La table officielle des événements d'audit liste `socket.connect` avec les arguments `self, address`, levé par `socket.connect` et `socket.connect_ex`. `socket.getaddrinfo(host, port, family, type, protocol)` et `socket.bind(self, address)` y figurent aussi.
Source : [docs.python.org/3.13/library/audit_events.html](https://docs.python.org/3.13/library/audit_events.html).

### 1b. Un hook qui lève bloque la connexion : confirmé

Test local (`audit_test.py`, Python 3.13.13) : `socket.create_connection` lève `PermissionError("blocked by guard")` et aucune connexion n'est ouverte. Avec httpx synchrone, l'appelant reçoit `httpx.ConnectError` ; le message de la garde est conservé et l'exception d'origine reste dans la chaîne `__context__`.

### 1c. Connexions asyncio, anyio et httpx async : infirmé sous Windows

Résultats du test local (serveur sur 127.0.0.1, hook qui refuse le port cible) :

| Boucle | Appel | Événements vus | Connexion bloquée ? |
| --- | --- | --- | --- |
| `ProactorEventLoop` (défaut Windows) | `asyncio.open_connection("127.0.0.1")` | aucun `socket.connect` vers la cible | **Non** |
| `ProactorEventLoop` | `httpx.AsyncClient().get("http://127.0.0.1:…")` | aucun | **Non** (réponse 200) |
| `ProactorEventLoop` | `httpx.AsyncClient().get("http://localhost:…")` | `socket.getaddrinfo` seulement | **Non** |
| `SelectorEventLoop` | les trois appels ci-dessus | `socket.connect` | Oui |

**Cause.** Sous Windows, `IocpProactor.connect` passe par `_overlapped.Overlapped.ConnectEx`, implémenté en C sans aucun `PySys_Audit`. Le fichier ne contient d'ailleurs aucun appel d'audit ([cpython 3.13, Modules/overlapped.c](https://raw.githubusercontent.com/python/cpython/3.13/Modules/overlapped.c)). Seuls `sock_connect` en mode Selector et `socket.connect` en synchrone passent par l'événement.

**Pourquoi c'est grave pour WaveStack.** uvicorn 0.53.0 choisit `asyncio.ProactorEventLoop` sous Windows quand il n'y a ni rechargement ni workers (`uvicorn/loops/asyncio.py` : `if sys.platform == "win32" and not use_subprocess: return asyncio.ProactorEventLoop`). Or AD-24 place les clients MCP (`httpx2.AsyncClient`, transport Streamable HTTP) sur cette boucle. Les sorties vers data.gouv.fr et Microsoft Learn **échappent donc à la garde** sur la plateforme cible. Les tests pytest asynchrones sous Windows sont dans le même cas, ce qui fragilise la convention « aucun test ne dépend du réseau ».

**Conséquences pour le spine (AD-15, AD-24) :**
1. Faire tourner uvicorn sur une boucle Selector sous Windows, par exemple `uvicorn.Config(..., loop="asyncio:SelectorEventLoop")` (uvicorn accepte une chaîne d'import de fabrique de boucle, `config.py`, `get_loop_factory`). Le transport stdio du SDK `mcp` le permet : sur une boucle sans sous-processus asynchrones, il se replie sur `subprocess.Popen` ([mcp/os/win32/utilities.py](https://github.com/modelcontextprotocol/python-sdk/blob/main/src/mcp/os/win32/utilities.py), `create_windows_process` → `_create_windows_fallback_process`).
2. Étendre la garde à `socket.getaddrinfo`, avec la même liste d'adresses autorisées (par nom d'hôte). C'est une défense en profondeur : elle couvre toutes les boucles pour les noms d'hôte, mais pas les adresses IP littérales sous Proactor.
3. Ajouter un test qui vérifie que la garde bloque une connexion asynchrone **sur la boucle réellement utilisée** par l'application et par pytest.
4. Préciser que l'exception arrive enveloppée (`httpx.ConnectError`, « All connection attempts failed » avec anyio). L'appelant doit reconnaître le refus par une sous-classe dédiée (par exemple `GuardRefused(PermissionError)`) retrouvée dans la chaîne, ou par un signal posé dans la `TraceScope`, et non par le type de l'exception reçue.

Note : à la création de chaque boucle sous Windows, `socket.socketpair` fait un `socket.connect` vers la boucle locale. La garde doit donc toujours laisser passer la boucle locale, ce que prévoit le spine.

## 2. huggingface_hub 1.32.0 (AD-15, AD-21)

### 2a. `HF_HUB_OFFLINE` est lu à l'import : confirmé

`constants.py`, ligne 194 : `HF_HUB_OFFLINE = _is_true(os.environ.get("HF_HUB_OFFLINE") or os.environ.get("TRANSFORMERS_OFFLINE"))`. `is_offline_mode()` renvoie cette constante et ne relit pas l'environnement.

Test local : avec `HF_HUB_OFFLINE=1` à l'import, puis la variable supprimée de `os.environ`, on obtient `is_offline_mode() == True`, `get_session().get(...)` lève `OfflineModeIsEnabled`, et `hf_hub_download` lève `LocalEntryNotFoundError`. La règle « ne jamais fixer `HF_HUB_OFFLINE` » est donc justifiée.

Nuance : le blocage est appliqué par `hf_request_event_hook` (`utils/_http.py`, ligne 283), un hook du client **par défaut**. Un client injecté par `set_client_factory` sans ce hook ne bloque plus (vérifié : réponse 200 sur un transport simulé). Sans conséquence ici, puisque le spine ne fixe jamais la variable.

### 2b. Variables de désactivation : confirmé

- `HF_HUB_DISABLE_TELEMETRY` (`constants.py`, ligne 243, avec les alias `DISABLE_TELEMETRY` et `DO_NOT_TRACK`). Utile en plus : quand il est actif, `build_hf_headers` n'appelle pas `detect_agent()` (`utils/_headers.py`, ligne 183). Cela évite la récupération de `{ENDPOINT}/api/agent-harnesses` dans `utils/_detect_agent.py`.
- `HF_HUB_DISABLE_XET` (`constants.py`, ligne 342) : `is_xet_available()` renvoie `False` (`utils/_runtime.py`, ligne 157), et `file_download.py` n'emprunte plus la voie Xet.

### 2c. `set_client_factory` : confirmé

Défini dans `huggingface_hub/utils/_http.py` (ligne 362) et exporté au niveau du paquet. Il attend `Callable[[], httpx.Client]` ; le client créé est partagé par tous les appels. Il existe aussi `set_async_client_factory`, inutile ici.

À noter pour la fabrique `net` :
- La fabrique par défaut crée le client avec `follow_redirects=True`. Les appels HEAD de résolution forcent `follow_redirects=False` et suivent eux-mêmes les redirections (`_httpx_follow_relative_redirects`), mais le GET de téléchargement (`http_get` → `http_stream_backoff`) s'appuie sur le réglage du client. Il vise l'URL déjà résolue, donc en principe sans nouvelle redirection. Si `net` désactive le suivi automatique, il faut le vérifier au test du téléchargement.
- Il est conseillé d'ajouter `hf_request_event_hook` aux hooks de requête du client injecté, pour garder l'identifiant de requête et le compteur de téléchargement.

### 2d. Constat annexe : domaines de téléchargement (AD-21, liste d'adresses autorisées)

`HEAD https://huggingface.co/Qwen/Qwen3-0.6B-GGUF/resolve/main/Qwen3-0.6B-Q8_0.gguf` répond `302`, avec `Location: https://us.aws.cdn.hf.co/xet-bridge-us/…`. Le sous-domaine dépend de la région. Sans Xet, le fichier est servi par ce pont CDN.

**Correction :** le README d'installation et la liste d'adresses autorisées doivent inclure `*.hf.co` (au moins `*.cdn.hf.co`), en plus de `huggingface.co`. Sinon, le téléchargement est refusé par la garde, ou par le proxy d'entreprise.

## 3. llama-cpp-python 0.3.35 (AD-4, étape 6 ; AD-5)

### 3a. Signatures : confirmé

Vérifié par `inspect.signature` sur la roue installée :
- `Llama.detokenize(self, tokens: List[int], prev_tokens: Optional[List[int]] = None, special: bool = False) -> bytes` ;
- `Llama.tokenize(self, text: bytes, add_bos: bool = True, special: bool = False) -> List[int]`.

AD-5 (`add_bos=False, special=True`) est conforme. `special=True` est indispensable au décodage : sans lui, `llama_token_to_piece` rend une chaîne vide pour les tokens de contrôle.

### 3b. Concaténation des `detokenize([id])` : principe exact, implémentation défaillante

**Principe.** Pour un BPE byte-level, chaque token correspond à une suite d'octets fixe, et `llama_token_to_piece` rend des octets, pas du texte. La concaténation des pièces redonne donc exactement le prompt, y compris pour un caractère UTF-8 coupé entre deux tokens. D'ailleurs, `LlamaModel.detokenize` n'est lui-même qu'une boucle de `llama_token_to_piece` sur chaque token (`_internals.py`, lignes 191 à 207).

**Défaut.** Cette boucle utilise un tampon fixe de 32 octets. Quand une pièce est plus longue, `llama_token_to_piece` renvoie `-taille_requise` ; `assert n <= size` passe, puis `bytes(buffer[:n])` avec `n` négatif rend `b""`. Le token disparaît sans erreur.

**Test local** avec le vocabulaire Qwen2 de llama.cpp (`models/ggml-vocab-qwen2.gguf`, ouvert en `vocab_only`) :
- **240 tokens** ont une pièce de plus de 32 octets (longues suites d'espaces, de tirets, etc.) ; par exemple, `detokenize([1920])` rend 0 octet au lieu de 35 ;
- sur un prompt ChatML en français (accents, `’`, `«»`, emoji, `<think>`), la concaténation est exacte ;
- après ajout de 40 espaces et de 80 tirets (code, tableaux Markdown, JSON indenté), elle est **fausse**, alors que `llama_cpp.llama_token_to_piece` appelé directement avec un tampon agrandi sur retour négatif redonne le prompt exact.

Défaut connu : [abetlen/llama-cpp-python#2362](https://github.com/abetlen/llama-cpp-python/issues/2362), « Long whitespace tokens detokenize to empty bytes, breaking tokenize/detokenize round-trip » (même cause signalée dans [dottxt-ai/outlines#2041](https://github.com/dottxt-ai/outlines/issues/2041)).

**Conséquence pour AD-4, étape 6.** Les décalages cumulés dérivent, et des tokens sont attribués au mauvais segment. C'est typiquement le cas avec du JSON indenté (résultats d'outils, documentation MCP), précisément les contenus que la jauge doit montrer. Le contrôle 4 ne le détecte pas, car il porte sur le rendu, pas sur la tokenisation.

**Correction :**
1. Le port `Engine` expose une fonction `token_bytes(id) -> bytes`. L'adaptateur `llama_cpp` l'implémente avec `llama_cpp.llama_token_to_piece(vocab, id, buf, size, 0, True)` et agrandit le tampon quand le retour est négatif. L'appel reste dans `models`, seul module autorisé à importer la bibliothèque.
2. Ajouter à l'étape 6 un contrôle : `b"".join(pièces) == prompt.encode("utf-8")`, sinon `harness_error` « attribution approximative ».
3. Ajouter au test de non-régression Qwen3.5 un segment avec une longue suite d'espaces.

## 4. Jinja2 3.1.6 et réglages de transformers (AD-4, Rendu)

### 4a. Jinja2 3.1.6 : confirmé

`jinja2.sandbox.ImmutableSandboxedEnvironment(trim_blocks=True, lstrip_blocks=True, extensions=[jinja2.ext.loopcontrols])` se construit, et `{% break %}` fonctionne (test local).

### 4b. Réglages de transformers : confirmé, avec deux écarts mineurs

Dans `transformers/utils/chat_template_utils.py` (`_cached_compile_jinja_template`, branche main, consultée le 2026-09-23) :

```python
jinja_env = ImmutableSandboxedEnvironment(
    trim_blocks=True, lstrip_blocks=True, extensions=[AssistantTracker, jinja2.ext.loopcontrols]
)
jinja_env.filters["tojson"] = tojson   # json.dumps(x, ensure_ascii=False, indent=None, separators=None, sort_keys=False)
jinja_env.globals["raise_exception"] = raise_exception
jinja_env.globals["strftime_now"] = strftime_now
```

Source : [chat_template_utils.py](https://github.com/huggingface/transformers/blob/main/src/transformers/utils/chat_template_utils.py). transformers exige jinja2 3.1.0 ou plus, ce que remplit la 3.1.6.

**Écarts à reprendre dans le spine :**
1. **Extension `AssistantTracker`** : elle définit la balise `{% generation %}…{% endgeneration %}`. Sans elle, un gabarit qui l'utilise ne compile pas (`TemplateSyntaxError`, vérifié). Pour les familles inconnues lues dans le GGUF (AD-6), ajouter une extension `generation` qui ne fait rien.
2. **Filtre `tojson`** : transformers accepte `indent`, `separators` et `sort_keys` en arguments (`tojson(indent=2)` apparaît dans certains gabarits). Il faut écrire « signature identique à transformers : `tojson(x, ensure_ascii=False, indent=None, separators=None, sort_keys=False)` », et non un `json.dumps` à paramètres figés.

Point connexe : transformers passe aussi au gabarit `messages`, `add_generation_prompt` et les jetons spéciaux (`bos_token`, `eos_token`…). La liste des « variables du modèle » d'AD-4 gagnerait à les nommer.

## 5. litellm : table des prix récupérée à l'import (test préalable de Headroom)

**Confirmé.** Dans `litellm/__init__.py` (main) :
- le module exécute `model_cost = get_model_cost_map(url=model_cost_map_url)` dès l'import ;
- l'adresse par défaut est `https://raw.githubusercontent.com/BerriAI/litellm/main/model_prices_and_context_window.json` (surchargeable par `LITELLM_MODEL_COST_MAP_URL`).

Dans `litellm_core_utils/get_model_cost_map.py`, si `LITELLM_LOCAL_MODEL_COST_MAP` vaut `true` (comparaison insensible à la casse), la table embarquée est utilisée sans requête. Sinon, la fonction fait un GET httpx synchrone avec un délai de 5 s. En cas d'erreur réessayable, elle **relance des essais dans un thread d'arrière-plan**, puis se replie sur la copie locale.
Source : [get_model_cost_map.py](https://github.com/BerriAI/litellm/blob/main/litellm/litellm_core_utils/get_model_cost_map.py). Dernière version PyPI : 1.102.1.

**Pertinence.** headroom-ai 0.38.0 dépend de `litellm>=1.96.2,<2.0` et de `tiktoken>=0.5.0` sans extra, donc dans l'installation de base (métadonnées PyPI).

**Conséquences pour le spine :**
- Si Headroom est adopté, `cli` fixe `LITELLM_LOCAL_MODEL_COST_MAP=True` avant tout import, avec les variables HF. Sinon, l'import déclenche une sortie non tracée : elle est bloquée par la garde (en synchrone, donc bien vue), mais suivie d'essais en arrière-plan qui produiront du bruit de refus.
- Ajouter aux critères du test préalable : **tiktoken télécharge ses fichiers BPE** (`openaipublic.blob.core.windows.net`) au premier `get_encoding`, sauf si `TIKTOKEN_CACHE_DIR` les contient déjà. Le test doit le couvrir.
- Le critère « respecte la règle d'adoption d'AD-15 » doit nommer explicitement ces deux sorties.

## 6. fastapi 0.141.1 : `fastapi.sse.EventSourceResponse` (AD-2)

**Confirmé.** `fastapi/sse.py` définit `class EventSourceResponse(StreamingResponse)` (`media_type = "text/event-stream"`) et `class ServerSentEvent(BaseModel)`, avec les champs `data`, `event`, `id` et `retry`.

L'usage prévu est `response_class=EventSourceResponse` sur un endpoint générateur qui fait `yield ServerSentEvent(...)`. `routing.py` gère l'encodage et un ping périodique (`_PING_INTERVAL`).

Détail d'implémentation : `data` est toujours sérialisé en JSON, y compris les chaînes. Pour `id = seq`, il faut passer `id=str(seq)`. L'en-tête `Last-Event-ID` se lit par un paramètre `Header`.

---

## Corrections proposées au spine (récapitulatif)

1. **AD-15 et AD-24, garde réseau.** Sous Windows, la boucle Proactor contourne `socket.connect`. Il faut :
   - imposer une boucle Selector à uvicorn (`loop="asyncio:SelectorEventLoop"`) ;
   - ajouter un contrôle sur `socket.getaddrinfo` ;
   - tester le blocage sur la boucle réelle, en application comme sous pytest ;
   - identifier le refus par une exception dédiée retrouvée dans la chaîne.
2. **AD-4, étape 6, et AD-5.** Remplacer `detokenize([id], special=True)` par un `token_bytes(id)` du port `Engine`, fondé sur `llama_token_to_piece` avec agrandissement du tampon. Ajouter le contrôle « concaténation = octets du prompt ».
3. **AD-21 et liste d'adresses autorisées.** Ajouter `*.hf.co` (CDN `xet-bridge`) aux domaines requis pour le téléchargement.
4. **AD-4, Rendu.** Ajouter une extension `generation` qui ne fait rien, et aligner la signature de `tojson` sur celle de transformers.
5. **Deferred, test préalable de Headroom.** Fixer `LITELLM_LOCAL_MODEL_COST_MAP=True` au démarrage si Headroom est adopté, et vérifier le téléchargement BPE de tiktoken.
