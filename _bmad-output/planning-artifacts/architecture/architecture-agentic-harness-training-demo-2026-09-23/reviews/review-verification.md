# Revue « vérification » du spine WaveStack (2026-09-23)

Angle de lecture : chaque décision engagée a-t-elle été confirmée par le web, par le projet existant ou par un test, et pas seulement tirée de la mémoire d'entraînement ? Les entrées `(version)` du memlog sont tenues pour acquises. On a vérifié ici ce qu'elles ne couvrent pas.

**Méthode.** Recherche web, API PyPI, dépôts Hugging Face et **tests réels** dans un environnement jetable (scratchpad) sur le poste d'Anaël :

- CPython 3.13.13, géré par uv, Windows x64.
- Paquets installés aux versions du spine : `mcp==2.2.0`, `fastapi==0.141.1`, `httpx==0.28.1`, `truststore==0.10.4`, `psutil==7.2.2`, `sqlite-vec==0.1.9`, `huggingface-hub==1.32.0`, `jinja2==3.1.6`, `llama-cpp-python==0.3.35` (depuis l'index abetlen).
- Modèle `unsloth/Qwen3.5-0.8B-GGUF`, fichier Q4_K_M, téléchargé pour l'occasion.

Réserve : le uv local est en 0.11.7, pas en 0.12.18. La syntaxe `pyproject` a été testée en 0.11.7 et comparée à la documentation actuelle.

## Synthèse

| # | Sujet | Statut | Gravité |
| --- | --- | --- | --- |
| V1 | Le client Streamable HTTP de mcp 2.2.0 attend un client `httpx2`, pas `httpx` | **contredit** (AD-15) | haute |
| V2 | Jinja2 « nu » ne rend pas le gabarit comme HF ou llama.cpp (`tojson` échappe et trie) | **contredit** (AD-4, sans précision) | haute |
| V3 | `hf_hub_download` passe par hf-xet (Rust), qui contourne `net`, httpx et truststore | **contredit** (AD-15, AD-21) | moyenne à haute |
| V4 | sse-starlette est inutile : FastAPI fournit `fastapi.sse` depuis la 0.135 | contredit (Stack) | basse |
| V5 | Clés uv pour épingler l'index et `no-build-package` | confirmé | — |
| V6 | mcp 2.2.0 : `MCPServer`, serveur stdio, Python 3.13 | confirmé (chemin d'import à préciser) | basse |
| V7 | truststore 0.10.4 avec httpx 0.28.1 sur Python 3.13 | confirmé | — |
| V8 | `Llama(vocab_only=True)` pour n'avoir que le tokenizer | confirmé (détails d'API) | basse |
| V9 | `hf_hub_download(local_dir=...)` | confirmé | basse |
| V10 | psutil 7.2.2 et sqlite-vec 0.1.9 sur le CPython 3.13 de uv | confirmé | — |
| V11 | Qwen3.5 : licence du GGUF et rendu du gabarit en Jinja2 | confirmé (avec V2) | basse |
| V12 | Wheels llama-cpp-python hébergées sur github.com (releases) | constat nouveau | moyenne |

---

## V1 — mcp 2.2.0 : le client HTTP à fournir est un `httpx2.AsyncClient` — **contredit**

- **Constat.** Les métadonnées PyPI de mcp 2.2.0 déclarent `httpx2>=2.5.0`, et non `httpx`. `httpx2` est un paquet distinct : la version 2.13.1 a été installée, avec `httpcore2`. La signature réelle est :
  `mcp.client.streamable_http.streamable_http_client(url, *, http_client: httpx2.AsyncClient | None = None, terminate_on_close=True)`.
  Il existe aussi un utilitaire, `mcp.shared._httpx_utils.create_mcp_http_client(...)`, qui renvoie un `httpx2.AsyncClient`.
- **Conséquence pour AD-15.** Le client `httpx` partagé de `net` ne peut pas être transmis au client MCP public. Le projet embarque alors deux piles HTTP : `httpx` 0.28, tiré par huggingface-hub, et `httpx2`, tiré par mcp. La règle « Seul `net` ouvre des connexions HTTP » reste tenable, mais `net` doit fabriquer **deux** clients configurés à l'identique : proxy, certificats, délais.
- **Point favorable, testé.** `httpx2.AsyncClient` utilise par défaut `truststore.SSLContext` (voir `httpx2/_config.py`) et accepte `verify=ssl.SSLContext`, `proxy=` et `trust_env=`. Une requête HTTPS vers pypi.org répond 200. Le JSON-RPC exact peut être émis avant l'envoi grâce aux `event_hooks={"request": [...]}` de `httpx2`, qui ont la même API que ceux de httpx.
- **Sources.**
  - https://pypi.org/pypi/mcp/json
  - https://py.sdk.modelcontextprotocol.io/v2/migration/
  - test local : `inspect.signature(streamable_http_client)`
- **Modification suggérée du spine.**
  - AD-15 : remplacer « un client `httpx` partagé » par « une fabrique `net` qui produit un client `httpx` (huggingface-hub, API publiques) et un client `httpx2.AsyncClient` (transport Streamable HTTP de mcp), avec la même configuration (truststore, proxy de l'environnement, délais, hook de requête qui émet les données sortantes) ».
  - Stack : ajouter la ligne `httpx2 | 2.13.1 (tiré par mcp)`.

## V2 — Rendu du gabarit : Jinja2 « nu » ≠ rendu HF / llama.cpp — **contredit** (précision manquante dans AD-4)

- **Constat, testé.** Le gabarit embarqué dans le GGUF Qwen3.5-0.8B (`tokenizer.chat_template`, 7 816 caractères) sérialise les outils avec `{{ tool | tojson }}` et appelle `raise_exception(...)`. Dans un `ImmutableSandboxedEnvironment` standard :
  - `raise_exception` n'existe pas : il faut l'ajouter aux globales.
  - le filtre `tojson` **natif** de Jinja2 échappe pour le HTML et **trie les clés**. Pour une description d'outil « Donne l'année <n> », on obtient `"Donne l'année <n>"` avec les clés triées. Avec le `tojson` de transformers, on obtient `"Donne l'année <n>"` dans l'ordre d'origine.

  Conséquence : sans surcharge, le prompt envoyé diffère de celui pour lequel le modèle a été entraîné. Les apostrophes et accents français sont précisément le cas courant de WaveStack. Le nombre de tokens change aussi.
- **Référence, transformers.** `ImmutableSandboxedEnvironment(trim_blocks=True, lstrip_blocks=True, extensions=[AssistantTracker, jinja2.ext.loopcontrols])`, avec :
  - le filtre `tojson` = `json.dumps(x, ensure_ascii=False, indent, separators, sort_keys=False)` ;
  - les globales `raise_exception` (qui lève `TemplateError`) et `strftime_now(fmt)`.
- **Autres constats.**
  - Le gabarit unsloth diffère légèrement du gabarit officiel `Qwen/Qwen3.5-0.8B/chat_template.jinja` : itération des `tool_call.arguments` sans le filtre `|items`. Les deux se rendent en Jinja2 3.1.6.
  - Si `enable_thinking` est absent, le raisonnement est **désactivé** (`<think>\n\n</think>\n\n`). Il faut `enable_thinking=True` pour le montrer.
- **Sources.**
  - https://github.com/huggingface/transformers/blob/main/src/transformers/utils/chat_template_utils.py
  - https://huggingface.co/Qwen/Qwen3.5-0.8B/blob/main/chat_template.jinja
  - test local (script `t.py`)
- **Modification suggérée du spine.** Dans AD-4, remplacer « rendu en Jinja2 sandboxé » par « rendu dans un `ImmutableSandboxedEnvironment(trim_blocks=True, lstrip_blocks=True, extensions=[loopcontrols])` configuré comme transformers : filtre `tojson` = `json.dumps(ensure_ascii=False, sort_keys=False)`, globales `raise_exception` et `strftime_now` ; un test de non-régression compare le rendu à une chaîne de référence pour Qwen3.5 (avec outils, texte accentué et apostrophe) ».

## V3 — Téléchargement Hugging Face : hf-xet contourne `net` — **contredit**

- **Constat, testé.**
  - huggingface-hub 1.32.0 dépend de `hf-xet` (1.6.0 installé). Pour le fichier `Qwen3.5-0.8B-Q4_K_M.gguf`, `get_hf_file_metadata(...).xet_file_data` est non nul : le dépôt est stocké sur Xet, et le téléchargement passe par le client Rust `hf-xet`, pas par httpx.
  - Le client Rust échappe au client de `net`, à `truststore` et au hook « données sortantes ». Sur un poste avec inspection TLS d'entreprise, c'est aussi un point de panne probable.
  - La constante `HF_HUB_DISABLE_XET` existe bien dans `huggingface_hub.constants`. `huggingface_hub.set_client_factory(Callable[[], httpx.Client])` existe aussi, et permet d'injecter le client de `net`.
- **Sources.**
  - https://huggingface.co/docs/huggingface_hub/package_reference/environment_variables
  - https://huggingface.co/docs/hub/xet
  - test local
- **Modification suggérée du spine.** Dans AD-21 et AD-15 : « le téléchargement du modèle par défaut passe par `huggingface_hub` avec `HF_HUB_DISABLE_XET=1` et `set_client_factory` branché sur le client `httpx` de `net` ». Solution de rechange : retirer `hf-xet` avec `[tool.uv] override-dependencies` ou `exclude-dependencies`, **à tester**. Ajouter au Deferred : « vérifier le débit du téléchargement HTTP classique sans Xet ».

## V4 — sse-starlette n'est plus nécessaire — **contredit**

- **Constat.** FastAPI propose le SSE natif depuis la **0.135.0**, avec `from fastapi.sse import EventSourceResponse, ServerSentEvent`. Il couvre :
  - les champs `id`, `event` et `retry` ;
  - la reprise par l'en-tête `Last-Event-ID` ;
  - un ping de maintien toutes les 15 s ;
  - les en-têtes `Cache-Control: no-cache` et `X-Accel-Buffering: no`.

  Import vérifié dans fastapi 0.141.1. FastAPI ne dépend pas de sse-starlette. Ce dernier reste présent dans l'environnement de façon transitive, par `mcp`.
- **Sources.**
  - https://fastapi.tiangolo.com/tutorial/server-sent-events/
  - test local : `import fastapi.sse`
- **Modification suggérée du spine.**
  - Stack : supprimer la ligne `sse-starlette`.
  - AD-2 et AD-18 : « flux SSE via `fastapi.sse.EventSourceResponse` ; `ServerSentEvent.id = seq` ; la reprise lit `Last-Event-ID`, ou un paramètre `from_seq` ». Le mécanisme de reprise d'AD-2 devient ainsi natif.

## V5 — Clés uv pour épingler llama-cpp-python — **confirmé**

- **Test.** Le `pyproject.toml` suivant, avec `uv lock` puis `uv sync` sous uv 0.11.7, a résolu `llama-cpp-python 0.3.35` avec `source = { registry = "https://abetlen.github.io/llama-cpp-python/whl/cpu" }`, installé la wheel `py3-none-win_amd64` sans compilation, puis chargé le modèle :

  ```toml
  [tool.uv]
  no-build-package = ["llama-cpp-python"]
  [[tool.uv.index]]
  name = "llama-cpp-cpu"
  url = "https://abetlen.github.io/llama-cpp-python/whl/cpu"
  explicit = true
  [tool.uv.sources]
  llama-cpp-python = { index = "llama-cpp-cpu" }
  ```

- **Sources.**
  - https://docs.astral.sh/uv/concepts/indexes/ (exemple `explicit = true` avec `tool.uv.sources`)
  - https://docs.astral.sh/uv/reference/settings/#no-build-package
- **Modification suggérée du spine.** Recopier ce bloc dans AD-21 ou dans le Structural Seed, pour que la première story n'ait rien à redécouvrir. Non vérifié : le comportement propre à uv 0.12.18. La syntaxe est stable et documentée à l'identique.

## V6 — mcp 2.2.0 : `MCPServer`, stdio, Python 3.13 — **confirmé**

- **Test.** Serveur `MCPServer("demo")` avec un outil `@app.tool()` et `app.run()` (transport `stdio` par défaut, signature `run(transport: Literal['stdio','sse','streamable-http']='stdio')`). Client `mcp.Client(StdioServerParameters(command=sys.executable, args=[...]))`, puis `list_tools()` et `call_tool("add", {"a":2,"b":3})`, qui renvoie `5`. Classifiers PyPI : 3.10 à 3.14.
- **Précision.** Chemin canonique : `from mcp.server.mcpserver import MCPServer`, que `mcp.server` réexporte aussi. `mcp.server.fastmcp` n'existe plus.
- **Dépendances tirées, à connaître pour NFR-10 et AppLocker** : `httpx2`, `httpcore2`, `opentelemetry-api`, `pyjwt[crypto]` (d'où `cryptography`, DLL native), `pywin32`, `starlette 1.7`, `sse-starlette`.
- **Sources.**
  - https://pypi.org/pypi/mcp/json
  - https://py.sdk.modelcontextprotocol.io/v2/migration/#fastmcp-renamed-to-mcpserver
  - test local
- **Modification suggérée du spine.** AD-21 : `from mcp.server.mcpserver import MCPServer` ; `app.run()` (stdio). Dans le Deferred (AppLocker), ajouter `cryptography` et `pywin32` à la liste des binaires natifs non maîtrisés.

## V7 — truststore 0.10.4 avec httpx 0.28.1 sur Python 3.13 — **confirmé**

- **Test.** `httpx.Client(verify=truststore.SSLContext(ssl.PROTOCOL_TLS_CLIENT))`, puis `GET https://pypi.org/simple/mcp/`, qui répond 200.
- **Source.** https://truststore.readthedocs.io/ (usage `truststore.SSLContext`).
- **Modification suggérée du spine.** Aucune. À combiner avec V1 : `httpx2` utilise déjà truststore par défaut.

## V8 — `Llama(vocab_only=True)` — **confirmé**, avec deux détails d'API

- **Test.**
  - `Llama(model_path=..., vocab_only=True, verbose=False)` fonctionne. Coût mesuré : +79 Mo de RSS pour le 0.8B, à comparer à ~530 Mo pour le fichier.
  - `metadata["tokenizer.chat_template"]` est présent ; `general.architecture = qwen35`.
  - `tokenizer.ggml.add_bos_token` est **absent** : Qwen3.5 n'ajoute pas de BOS, mais la neutralisation d'AD-5 reste nécessaire pour les autres familles.
- **Détails d'API.**
  - `Llama.tokenize()` attend des **bytes** (`text.encode()`) : un `str` lève `ctypes.ArgumentError`. Le port `Engine.tokenize(str)` d'AD-5 doit donc encoder.
  - llama.cpp crée quand même un contexte (`n_ctx 512`) en mode vocab_only. C'est sans impact notable.
- **Source.** Test local ; https://github.com/abetlen/llama-cpp-python (paramètre `vocab_only` de `Llama.__init__`).
- **Modification suggérée du spine.** Dans AD-5, préciser : « `tokenize` de l'adaptateur llama_cpp encode en UTF-8 et appelle `tokenize(..., add_bos=False, special=True)` ; un tokenizer vocab_only coûte environ 80 Mo, à compter dans AD-8 ».

## V9 — `hf_hub_download(local_dir=...)` — **confirmé**

- **Test.** `hf_hub_download('unsloth/Qwen3.5-0.8B-GGUF', 'Qwen3.5-0.8B-Q4_K_M.gguf', local_dir=...)` dépose le fichier réel, pas un lien symbolique.
- **Effet de bord.** L'appel crée un sous-dossier `.cache/huggingface/` dans `local_dir`.
- **Source.** https://huggingface.co/docs/huggingface_hub/guides/download#download-files-to-a-local-folder
- **Modification suggérée du spine.** Dans AD-7, la découverte dans `models/` doit ignorer `.cache/`. Voir aussi V3.

## V10 — psutil et sqlite-vec sur le CPython 3.13 géré par uv — **confirmé**

- **Test.**
  - psutil 7.2.2 s'installe par wheel, sans compilation.
  - `sqlite3.connect(...).enable_load_extension(True)` puis `sqlite_vec.load(db)` fonctionnent sur le CPython 3.13.13 de python-build-standalone : `vec_version()` renvoie `v0.1.9`, avec SQLite 3.50.4.
- **Source.** Test local ; https://alexgarcia.xyz/sqlite-vec/python.html
- **Modification suggérée du spine.** Aucune. Ajouter au Deferred : « l'interpréteur Python du Microsoft Store ou de python.org peut différer ; WaveStack impose le Python géré par uv ».

## V11 — Qwen3.5 : licence et gabarit — **confirmé**

- **Constat.**
  - `Qwen/Qwen3.5-0.8B`, `unsloth/Qwen3.5-0.8B-GGUF`, `unsloth/Qwen3.5-2B-GGUF` et `bartowski/Qwen_Qwen3.5-2B-GGUF` sont tous sous licence `apache-2.0` sur le Hub. Le GGUF porte aussi `general.license = apache-2.0`.
  - Q4_K_M 0.8B : 532 517 120 octets.
  - Le gabarit se rend en Jinja2 3.1.6, sous la réserve de V2.
  - Les modèles sont étiquetés `image-text-to-text` : des fichiers `mmproj` sont fournis mais ne sont pas nécessaires en texte seul.
- **Sources.**
  - https://huggingface.co/Qwen/Qwen3.5-0.8B
  - https://huggingface.co/unsloth/Qwen3.5-2B-GGUF
  - https://huggingface.co/bartowski/Qwen_Qwen3.5-2B-GGUF
- **Modification suggérée du spine.** Stack : préciser le dépôt de référence, par exemple `unsloth/Qwen3.5-{0.8B,2B}-GGUF`, et noter que son gabarit diffère légèrement de l'officiel. Le harnais utilise celui du GGUF.

## V12 — Les wheels llama-cpp-python viennent de github.com — **constat nouveau**

- **Constat.** Le `uv.lock` généré pointe vers `https://github.com/abetlen/llama-cpp-python/releases/download/v0.3.35/llama_cpp_python-0.3.35-py3-none-win_amd64.whl`. L'index abetlen (GitHub Pages) ne fait que rediriger. Sur un poste d'entreprise, le proxy doit donc laisser passer `abetlen.github.io`, `github.com` et `release-assets.githubusercontent.com` (ou `objects.githubusercontent.com`).
- **Source.** Test local (`uv lock`).
- **Modification suggérée du spine.** Dans AD-21 et dans le README d'installation, lister les domaines à autoriser : PyPI, github.com (wheels), huggingface.co et les domaines Xet (modèle, sauf si V3 désactive Xet).

---

## Non vérifié ici

- Le comportement exact de uv **0.12.18**. Seul uv 0.11.7 a été testé ; la documentation actuelle a été lue.
- AppLocker et WDAC. C'est déjà dans le Deferred du spine.
