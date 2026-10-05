# Revue de vérification : lot 4 (AD-27, AD-28 et paragraphes « Lot 4 du 2026-10-04 »)

- **Date :** 2026-10-05
- **Objet :** `ARCHITECTURE-SPINE.md`, AD-27 (Atelier MCP en séquence), AD-28 (module commun de schéma), et les paragraphes « Lot 4 du 2026-10-04 » d'AD-2, AD-3, AD-18 et AD-19.
- **Angle :** chaque décision a-t-elle été confrontée au code et au SDK réels, ou affirmée de mémoire ?
- **Méthode :** lecture du code de la branche `feat/lot-4-atelier-mcp-design` (worktree `agentic-harness-training-demo-lot4`) et du SDK MCP installé. Aucune exécution, aucune installation.
- **Réserve sur la source du SDK :** le `.venv` du worktree est refusé par les permissions de la session. Le SDK a donc été lu dans le `.venv` du dépôt principal (`agentic-harness-training-demo/.venv`), qui contient `mcp-2.2.0` et `mcp_types-2.2.0` (dist-info). C'est la version qu'épingle `pyproject.toml:17,20` (`mcp>=2.2,<2.3`, `mcp-types>=2.2,<2.3`). Dans la suite, `SDK/…` désigne `…/.venv/Lib/site-packages/…`.
- **Recherche web :** pas nécessaire. Les noms de méthode et les noms sur le fil se lisent dans les `Literal` et les alias de `mcp_types`.

## Verdict

Le côté SDK a bien été vérifié : toutes les affirmations sur l'API `mcp.Client` 2.2, la poignée de main legacy, la pagination, `MCPServer` et les noms de méthode sont confirmées. Le côté session, lui, a été en partie affirmé sans vérification. Trois réutilisations ne marchent pas telles qu'elles sont écrites :

- `_call_model_chat` émet `context_reconciled`, ce qu'AD-27 interdit dans `mcp_lab` ;
- `_tool_definitions` et `_doc_catalog` sont liés au registre de la brique ;
- `ToolExecutor.check` est lié au registre de la brique.

Trois points sont aussi sous-spécifiés : `sends` dérivé des segments, la définition des « noms de premier niveau des capacités », et l'égalité « poids affiché = poids envoyé ». Les retouches d'AD-28 sont compatibles avec `diagram.js` et `pages.css`, à deux détails près (jeton de 3 px, bulle non focalisable).

| # | Sujet | Verdict | Gravité |
|---|---|---|---|
| V1 | Modèle cloud d'un `ask` par `_call_model_chat` | **faux** | haute |
| V2 | Définitions d'outils par `_tool_definitions`, « poids affiché = poids envoyé » | **faux** (en l'état) | moyenne |
| V3 | `ToolExecutor.check` sur les outils de l'atelier | **faux** (en l'état) | moyenne |
| V4 | API `mcp.Client` 2.2 (propriétés, listes, lecture, prompts, legacy) | confirmé | — |
| V5 | « Noms de premier niveau des capacités » | confirmé, ambigu | basse |
| V6 | `MCPServer` : ressource `glossary://terms`, prompt `explain_term(term)` | confirmé | — |
| V7 | Noms de méthode de la spec, `isError`, forme des prompts | confirmé, une contradiction interne | basse |
| V8 | `mcp/lab.step_number` et `mcp/lab.KINDS` | changement non signalé comme tel | basse |
| V9 | `_lab_restore` et `prefix_not_reused{cause: mcp_lab}` | faux dans le détail | basse |
| V10 | Portée des `model_call_*` et des `outbound_request` | confirmé, un ajustement | basse |
| V11 | `sends` « calculé à partir des segments du rendu » | non vérifiable (sous-spécifié) | moyenne |
| V12 | Autres noms cités (`tool_max_calls`, `ActiveModel`, rendus, `_bound_result`…) | confirmé | — |
| V13 | AD-28 : retouches de `diagram.js` et `pages.css` | confirmé, avec réserves | basse |
| V14 | AD-3 lot 4 : « Arrêter » pendant une génération | confirmé (changement à faire) | basse |

---

## Constats

### V1 — Le modèle cloud d'un `ask` par `_call_model_chat` contredit « aucun `context_reconciled` dans `mcp_lab` »

- **Affirmation (AD-27, « Modèle cloud » et « Appels au modèle ») :** les `model_call_*` réels sont ceux qu'émet `_call_model` ; « `_call_model_chat` émet donc `outbound_request` sur `mcp{n}.c{k}` » ; et « Aucun `context_rendered`, `context_preview` ni `context_reconciled` dans `mcp_lab`, comme dans `llm`. La jauge de `/api/state` ignore ce contexte. »
- **Preuves :**
  - `src/wavestack/session/app_session.py:7711-7712` : `_call_model` passe la main à `_call_model_chat` dès que le rendu est un `RenderedChat`.
  - `app_session.py:8097-8102` : `_call_model_chat` émet `context_reconciled` dès que le fournisseur renvoie `usage`, puis met à jour `self._ratio`, le ratio d'estimation de la jauge principale.
  - `app_session.py:8086-8095` : il ajoute coût et impact à `self._turn_costs` et `self._turn_impacts`, alors qu'il n'y a pas de tour.
  - `app_session.py:8090-8091` : sur une erreur du fournisseur, le texte d'effet du `harness_error` est `session.turn.over` (« le tour s'arrête ») ou `delegation.error.effect`, ce qui est faux pour l'atelier.
  - Le précédent cité par AD-27, « LLM nu », évite justement ce chemin : `app_session.py:8676-8678` (« the cloud call through `run_call` directly (no `context_reconciled`, no `_ratio`) ») et `8878-8920` (`_lab_cloud_call` appelle `run_call` sans passer par `_call_model_chat`).
  - `src/wavestack/web/app.py:557-561` : le filtre de la jauge de `/api/state` écarte `sub*` et `llm`, mais pas `mcp_lab`. Un `context_reconciled` émis dans `mcp_lab` deviendrait donc la source de la jauge principale.
  - Ce qui tient : `_call_model_chat` pose bien `origin = model` lui-même (`app_session.py:8067`, `with scoped(origin="model")`). La phrase « la session pose `origin = model` » est donc vraie sans rien ajouter.
- **Verdict :** **faux**. La règle « aucun `context_reconciled` » et la règle « par `_call_model_chat` » ne peuvent pas tenir ensemble sans changer le code.
- **Correctif :** dans AD-27, remplacer « `_call_model_chat` émet donc… » par l'une des deux voies suivantes :
  - (a) un appel cloud propre à l'atelier, sur le modèle de `_lab_cloud_call` : `run_call` direct sous `origin = model`, qui rend aussi les appels d'outils analysés (`call.calls`, `call.malformed`, `stop_reason`, `channel`) ;
  - (b) une option de `_call_model_chat` (par exemple `lab_effect_text=…`) qui supprime `context_reconciled`, la mise à jour de `_ratio` et l'ajout aux coûts du tour, et qui prend le texte d'effet du `harness_error`.

  Dans les deux cas, ajouter `mcp_lab` (et `rag_lab`) au filtre de la jauge de `web/app.py:560`, par défense en profondeur. Écrire la règle sous la forme : « l'appel cloud de l'atelier suit `_lab_cloud_call` (story 29) ».

### V2 — Définitions d'outils « du `ToolRegistry` de l'atelier et de `_tool_definitions` » ; « le poids affiché est le poids envoyé »

- **Affirmation (AD-27) :** « Les définitions d'outils viennent du `ToolRegistry` de l'atelier et de `_tool_definitions`, les mêmes qui donnent les poids de `mcp_lab_connect_ended` : le poids affiché est le poids envoyé. »
- **Preuves :**
  - `app_session.py:4116-4140` : `_tool_definitions(self, state: TurnState)` lit `state.tools` et `self._registry`, c'est-à-dire le registre de la brique. `app_session.py:4142-4155` : `_doc_catalog` lit aussi `self._registry`.
  - `app_session.py:9597-9600` : les outils de l'atelier ne sont jamais inscrits dans le registre de la brique (« Nothing is registered in the brick's registry: a registry of the workshop's own computes the definitions »). Appelé tel quel, `_tool_definitions` ne trouverait aucun outil de l'atelier.
  - `app_session.py:9612,9622,9632-9639` : les poids de `mcp_lab_connect_ended` comptent `json.dumps(registry.definition(name))`, la définition sérialisée en JSON. Ce n'est pas ce que reçoit le modèle. En local, le gabarit Jinja rend `tools` à sa façon (`render_context`, `context/render.py:369-376`). En cloud, le traducteur d'API écrit le corps (`render_chat_body`, `render.py:644-663`). Les `sends[].tokens` calculés depuis les segments du rendu (AD-27) ne seront donc pas égaux à `doc_tokens` et `full_tokens`.
- **Verdict :** **faux en l'état**. La *définition* peut être la même ; le *poids* ne l'est pas.
- **Correctif :**
  - Écrire : « `_tool_definitions` et `_doc_catalog` prennent un registre (celui de la brique par défaut, celui de l'atelier pour un `ask`) et la liste des outils exposés au lieu d'un `TurnState` ».
  - Remplacer « le poids affiché est le poids envoyé » par « la définition affichée est la définition envoyée ; le poids envoyé est celui de `sends` ». Ou bien décider que `mcp_lab_connect_ended` compte les segments `tool_catalog` d'un rendu à blanc. Il faut trancher l'un ou l'autre et le dire, faute de quoi la page affichera deux chiffres différents pour « la même » documentation.

### V3 — `ToolExecutor.check` sur les appels demandés par le modèle

- **Affirmation (AD-27, « Déroulé et bornes d'un `ask` ») :** « Chaque appel demandé est contrôlé par `ToolExecutor.check` (AD-14). Un refus donne `outcome: refused`. »
- **Preuves :** `src/wavestack/tools/executor.py:41-66`. L'exécuteur est construit sur un `registry`. `check(call, enabled, loadable=())` refuse tout nom absent de `self.registry` ou de `enabled` (`tools.check.unknown_tool`). L'exécuteur de la session est construit sur le registre de la brique, qui ne contient pas les outils de l'atelier (voir V2). Ailleurs, `check` ne valide que les noms, les arguments connus, les arguments requis et les types JSON (`executor.py:67-87`), sans hook : c'est cohérent avec « rien n'est envoyé au serveur ».
- **Verdict :** **faux en l'état**. Avec l'exécuteur de la brique, tout appel du modèle serait refusé comme outil inconnu.
- **Correctif :** préciser « un `ToolExecutor` construit sur le `ToolRegistry` de l'atelier (même langue de session) ». Préciser aussi `enabled` et `loadable` selon `doc_mode` :
  - `full` : tous les noms exposés `{server}__{tool}`, plus rien d'autre ;
  - `lazy` : `load_tool_doc` et les outils dont la doc a été chargée dans l'échange, les autres dans `loadable` (ce qui donne `tools.check.doc_not_loaded`, `executor.py:62-63`).

### V4 — L'API `mcp.Client` 2.2 en mode legacy

- **Affirmation (AD-27, AD-18) :** la session lit `client.server_capabilities`, `server_info` et `protocol_version`. `LabConnection` appelle `list_resources`, `list_prompts`, `read_resource` et `get_prompt`. Après `initialize` vient `notifications/initialized`. On ne lit qu'une page par liste.
- **Preuves :**
  - `SDK/mcp/client/client.py:496-514` : propriétés `protocol_version` (str), `server_info` (`Implementation | None`, toujours présent en legacy selon la docstring l.502-508) et `server_capabilities` (`ServerCapabilities`).
  - `client.py:592-606` (`list_resources`), `624-686` (`read_resource(uri)`), `826-840` (`list_prompts`), `842-881` (`get_prompt(name, arguments: dict[str, str] | None)`).
  - `client.py:457-458` : `mode == "legacy"` appelle `session.initialize()`. `SDK/mcp/client/session.py:651-673` : `initialize` envoie `InitializeRequest`, vérifie la version, puis `send_notification(InitializedNotification())` (l.671).
  - `SDK/mcp_types/_types.py:190-195` : `PaginatedResult.next_cursor` (sur le fil `nextCursor`, alias camelCase l.48), hérité par `ListResourcesResult` (849-855) et `ListPromptsResult` (1128-1133).
  - `session.py:890,1185` : `list_resources` et `list_prompts` ne vérifient pas la capacité côté client. Le filtre « seulement si la capacité est annoncée » revient donc bien à la session.
  - **Point à ne pas perdre :** `Client.cache` vaut par défaut `CacheConfig()` (`client.py:358-366`), et les quatre verbes de liste ainsi que `read_resource` passent par `_cached_fetch` et le cache (`client.py:553-590, 664-686`). En legacy, le TTL vaut 0 (`SDK/mcp/client/caching.py:113,338-349`), donc rien n'est servi depuis le cache. Mais `McpConnection._serve` passe déjà `cache=None` (`src/wavestack/mcp/connection.py:114`), et c'est ce qui garantit que chaque lecture passe sur le fil, donc dans la capture.
- **Verdict :** **confirmé**.
- **Correctif (précision) :** ajouter à AD-27, « Poignée de main » : « `LabConnection` garde `Client(…, mode="legacy", cache=None)` : aucune réponse servie sans passer par le transport ». Préciser aussi si `tools/list` est conditionné à la capacité `tools`. La phrase actuelle se lit des deux façons, et le code d'aujourd'hui l'appelle toujours (`connection.py:115`).

### V5 — « Noms de premier niveau des capacités »

- **Affirmation (AD-27) :** `capabilities` liste les noms de premier niveau des capacités du résultat d'`initialize`, lus dans `client.server_capabilities`.
- **Preuves :**
  - `SDK/mcp_types/_types.py:485-512` : les champs de `ServerCapabilities` sont `experimental`, `logging`, `prompts`, `resources`, `tools`, `completions`, `extensions` et `tasks`, tous `… | None`. Ce sont des mots simples, donc identiques en Python et sur le fil.
  - `_types.py:45-48` : `MCPModel` n'a pas `extra="allow"`. Une capacité non standard de premier niveau est donc perdue par le SDK, alors qu'elle reste visible dans le JSON capturé.
  - `SDK/mcp/server/lowlevel/server.py:594-607`, avec `SDK/mcp/server/mcpserver/server.py:218-224` : `MCPServer` enregistre toujours les gestionnaires `tools/list`, `resources/list` et `prompts/list`, et annonce donc toujours `tools`, `resources` et `prompts`, même sans ressource ni prompt. Le Glossaire annonce déjà les trois aujourd'hui. Avant l'ajout de `glossary://terms`, il rendrait `resources: []` et `prompts: []`, ce qui est cohérent avec la règle `null` / `[]` d'AD-27.
- **Verdict :** **confirmé, mais ambigu**.
- **Correctif :** définir la liste de façon exécutable, par exemple « les clés de `server_capabilities.model_dump(by_alias=True, exclude_none=True)`, dans l'ordre du modèle ». Ajouter : « une capacité non standard n'apparaît que dans le JSON brut ». Signaler dans EXPERIENCE.md que, pour un serveur `MCPServer`, « capacité annoncée » ne veut pas dire « contenu présent ».

### V6 — `MCPServer` sert `glossary://terms` et `explain_term(term)`

- **Affirmation (AD-19, lot 4) :** le serveur local sert la ressource `glossary://terms` et le prompt `explain_term(term)`.
- **Preuves :**
  - `src/wavestack/mcp/local_server.py:15,40` utilise `mcp.server.mcpserver.MCPServer`.
  - `SDK/mcp/server/mcpserver/server.py:779-938` : décorateur `resource(uri, *, name, title, description, mime_type, …)`. Une URI sans variable donne une ressource statique ; une fonction à paramètres est alors refusée (l.909-914), ce qui convient à `glossary://terms`.
  - `server.py:959-1020` : décorateur `prompt(name, title, description, icons)`. Les arguments viennent de la signature (`Prompt.from_function`), donc `term: str` donne un argument requis.
  - `server.py:454-466` : une URI inconnue lève `MCPError(INVALID_PARAMS)`. Le 409 d'AD-27 (« une entrée listée ») l'évite avant tout envoi.
  - `server.py:469-489` : un contenu `str` devient `TextResourceContents` avec `mime_type` `text/plain` par défaut.
- **Verdict :** **confirmé**.
- **Correctif :** aucun. Note pour la story : `LocalToolsText` (`src/wavestack/mcp/servers.py:82-86`) ne porte que deux descriptions. Les textes de la ressource et du prompt demandent d'étendre ce modèle (ou d'en ajouter un) dans les trois langues.

### V7 — Noms de méthode, `isError`, forme des prompts

- **Affirmation (AD-19, AD-27) :** il y a quatre nouvelles méthodes, `resources/list`, `resources/read`, `prompts/list` et `prompts/get`. `isError` est le nom sur le fil. `mcp_lab_prompt_ended.messages: [{role, text}]`. « Un prompt envoie ses messages tels quels. »
- **Preuves :**
  - `SDK/mcp_types/_types.py:776` (`"resources/list"`), `896` (`"resources/read"`), `1100` (`"prompts/list"`), `1146` (`"prompts/get"`), `565` (`"notifications/initialized"`), `1459` (`"tools/call"`).
  - `_types.py:1480` : `CallToolResult.is_error`, avec l'alias `to_camel` (l.48), donc `isError` sur le fil.
  - `SDK/mcp_types/version.py:33-38` : ces méthodes existent dans toutes les versions de la poignée de main (2024-11-05 à 2025-11-25).
  - `_types.py:1323-1330` : `PromptMessage{role, content: ContentBlock}`, un seul bloc, qui peut être `TextContent`, `ImageContent`, `AudioContent`, `ResourceLink` ou `EmbeddedResource` (l.1319).
- **Verdict :** **confirmé**, avec une contradiction interne. « Tels quels » s'oppose à « un contenu binaire ou non textuel n'est jamais inliné ».
- **Correctif :** écrire « un prompt envoie, dans l'ordre et avec leur rôle, le texte de ses messages ; un bloc non textuel devient sa mention tirée de `content/` ». Ajouter que `mcp_lab_prompt.args` n'accepte que des chaînes, puisque `get_prompt(arguments: dict[str, str])` (`client.py:845`), avec un refus 422/409 lisible sinon.

### V8 — `mcp/lab.step_number` et `mcp/lab.KINDS`

- **Affirmation (AD-27) :** « `mcp/lab.step_number` lit `n` dans `mcp{n}` comme dans `mcp{n}.c{k}` » ; « `mcp/lab.KINDS` est cette liste » (neuf `mcp_lab_*`, `model_call_started`, `model_call_ended` et `outbound_request`).
- **Preuves :**
  - `src/wavestack/mcp/lab.py:323-327` : aujourd'hui, `step_number("mcp3.c1")` rend `None`, parce que `step_id[3:].isdigit()` échoue.
  - `lab.py:320` : `KINDS` contient trois genres. `outbound_request` est traité à part (l.340).
  - `last_session` (l.330-345) écarterait donc les `model_call_*` sur `mcp{n}.c{k}`.
- **Verdict :** il s'agit d'un **changement à faire**, écrit comme un état existant. Ce n'est pas faux comme décision, mais c'est trompeur pour le développeur.
- **Correctif :** écrire « `step_number` *est étendu* à `mcp{n}.c{k}` » et « `KINDS` *devient* cette liste, `outbound_request` compris (la branche à part de `last_session` disparaît) ». Ajouter un test pour `mcp12.c3 → 12`.

### V9 — `_lab_restore` et `prefix_not_reused{cause: mcp_lab}`

- **Affirmation (AD-27, « Cache du moteur » ; AD-2, lot 4) :** un appel local copie puis restaure l'état du moteur par `_lab_restore`, « comme LLM nu ». À défaut, `prefix_not_reused{cause: mcp_lab}`.
- **Preuves :**
  - `app_session.py:8922-8932` : `_lab_restore(saved)` écrit en dur `self._cache_cause = self._cache_cause or "llm"`.
  - `src/wavestack/trace/catalog.py:649-659` : `PrefixCause` ne contient pas `mcp_lab`.
  - `content/messages.yaml:105-114` : la clé du texte (`…prefix…llm`) devra exister pour `mcp_lab` dans les trois langues, sous contrôle de parité (`tests/test_i18n.py`).
- **Verdict :** **faux dans le détail**. Réutiliser `_lab_restore` tel quel tracerait `cause: llm`.
- **Correctif :** « `_lab_restore(saved, cause)` ; `PrefixCause` gagne `mcp_lab`, avec son texte dans `messages.yaml` et ses deux surcouches ».

### V10 — Portée des `model_call_*`, des messages et des `outbound_request`

- **Affirmation (AD-27) :** chaque appel au modèle a `step_id = call_id = mcp{n}.c{k}` et `parent_step = mcp{n}`. `_call_model` émet ses `model_call_*` sous la portée courante. Restent sur `mcp{n}` : les messages JSON-RPC, le `mcp_lab_call_ended{by: model}` et les `outbound_request` d'un serveur public (`origin = brick`).
- **Preuves :**
  - `app_session.py:7739-7750` : `_call_model_local` lit `current().step_id` et émet `model_call_started` sous la portée courante. `src/wavestack/trace/journal.py:51-67` : `emit` prend `call_id`, `step_id` et les autres champs dans `current()`. `TraceScope` a bien `parent_step` (`trace/scope.py:24`). Le chemin local est déjà réutilisé hors tour par « LLM nu » (`app_session.py:8808`).
  - `src/wavestack/mcp/lab.py:304-315` : `LabConnection.call_result` soumet l'appel avec `self.idle_scope` (`origin = brick`, `step_id = mcp{n}` posé par `begin`, l.289-292), et non avec `current()`. Le `tools/call` demandé par le modèle garde donc `mcp{n}` et `origin = brick`, même s'il part depuis la portée `mcp{n}.c{k}`. C'est confirmé.
  - `app_session.py:9390-9404, 9729-9737` : `_mcp_lab_emit` force `call_id = None` et `parent_step = None`. Tel quel, il ne peut pas poser `mcp_lab_model_started` et `mcp_lab_model_ended` sur `mcp{n}.c{k}` avec `parent_step`.
  - `src/wavestack/tools/parser.py:27-35` : `tool_call_id(step_id, index)` accepte tout `step_id`.
- **Verdict :** **confirmé**, avec un ajustement.
- **Correctif :** écrire « `_mcp_lab_scope` prend `call_id` et `parent_step` » (ou une variante pour les appels au modèle).

### V11 — `sends` « calculé par la session à partir des segments du rendu »

- **Affirmation (AD-27) :** `sends: [{part: question|resource|prompt|tools|tool_doc|tool_call|tool_result, …}]` est calculé à partir des segments du rendu.
- **Preuves :** `src/wavestack/context/segments.py:15-30`. Il n'existe aucun `SegmentKind` pour une ressource MCP, un prompt MCP ou une doc chargée. Une ressource et sa question forment « un seul message utilisateur » (AD-27), donc deux textes qui seraient tous deux `USER_MESSAGE`. Le `Part` porte `brick`, `component` et `name` (`app_session.py:4128, 4151`), ce qui permettrait de les distinguer, mais AD-27 ne le dit pas. Un nouveau `SegmentKind` demanderait ses libellés dans `content/labels/segment_kinds.yaml` et ses deux surcouches (AD-19).
- **Verdict :** **non vérifiable**. La correspondance entre `part` et les segments n'est pas définie.
- **Correctif :** ajouter une table `part → (SegmentKind, component/name)`, par exemple :
  - `question` → `USER_MESSAGE`, `name = question` ;
  - `resource` → `USER_MESSAGE`, `name = resource:{uri}` ;
  - `prompt` → `USER_MESSAGE` ou `ASSISTANT_TURN` selon le rôle ;
  - `tools` → `TOOL_CATALOG` ;
  - `tool_doc` → `TOOL_RESULT` de `load_tool_doc` ;
  - `tool_call` → `ASSISTANT_TURN` ;
  - `tool_result` → `TOOL_RESULT`.

  Dire explicitement « aucun nouveau `SegmentKind` », ou lister ceux qui sont ajoutés.

### V12 — Autres noms cités

- **Affirmation :** `tools.max_calls`, `ActiveModel`, `render_context`, `render_chat_body(api=…)`, `_bound_result`, `_count_tokens`, les routes `POST /api/intentions/mcp_lab_*` qui rendent `{step_id}`.
- **Preuves :**
  - `src/wavestack/config.py:944-947` : `tool_max_calls`, lu dans `[tools] max_calls`, 6 par défaut, au moins 1.
  - `src/wavestack/trace/catalog.py:99` : `class ActiveModel`.
  - `context/render.py:369-376` (`render_context(…, tools=…)`) et `644-654` (`render_chat_body(…, tools, …, api="openai_chat")`).
  - `app_session.py:7101-7125` : `_bound_result`, qui compte avec `_count_tokens(uncapped=True)`. `app_session.py:5019-5032` : `_count_tokens`, une estimation en mode chat.
  - `src/wavestack/web/app.py:512-531` : les routes existantes rendent `{"step_id": …}`.
  - `src/wavestack/models/capabilities.py:29-42` : `tool_call_parser` et `reasoning_always`, dont `ask.tools` peut être dérivé.
- **Verdict :** **confirmé**.
- **Correctif :** aucun. Note : avec le déroulé d'AD-27 (au plus un `meta_call`, un outil MCP, une réponse), la borne `tools.max_calls` ne joue que contre des `load_tool_doc` répétés. Ce n'est pas un défaut, mais la phrase pourrait le dire.

### V13 — AD-28 : retouches de `static/diagram.js` et `pages.css`

- **Affirmation (AD-28) :** les signatures ne changent pas, et `createStepper` gagne une option facultative `onLive(live)`. La position passe d'un `aria-live` sur l'élément visible à un nœud `role="status"` masqué. « Suivre le direct » pressé prend un fond plein et un « ● » `aria-hidden`. `explain()` se ferme au `focusout`. `.diagram-block.is-active` reçoit un anneau d'encre sous le halo. `.diagram-path-core` passe à 3 px. Une retouche vaut pour toutes les pages qui importent le module, et les E2E suivent.
- **Preuves :**
  - `src/wavestack/web/static/diagram.js:153` : `createStepper(host, { onShow } = {})`. Une option déstructurée de plus ne casse rien. Le mode direct change dans `show`, `follow` et `clear` (l.212-226) : c'est là qu'il faut appeler `onLive`, et seulement quand la valeur change.
  - `diagram.js:175-186` : aujourd'hui, la position visible bascule `aria-live` entre `off` et `polite`. La retouche la remplace, ce qui est cohérent.
  - `diagram.js:174` : le bouton direct prend son nom par `textContent`. Le « ● » doit être un `span aria-hidden` à côté du texte, pour garder le nom accessible. `pages.css:536-539` : l'état pressé est aujourd'hui `--color-primary-soft`, à remplacer par un fond plein.
  - `diagram.js:122-141` : la bulle est un `div popover` (popover automatique, fermé par Échap ou un clic ailleurs), non focalisable. « Le focus va à la bulle » n'arrive donc jamais sans `tabindex`. Un `focusout` dont le `relatedTarget` est `null` (clic dans le texte de la bulle, clic dans une zone non focalisable) fermerait la bulle sur un clic à l'intérieur.
  - `pages.css:429-431` : le halo est `box-shadow: 0 0 0 4px var(--color-state-active)`. L'anneau d'encre s'écrit en double `box-shadow`. `src/wavestack/web/static/app.css:3470-3473` : `.arch .arch-hook.is-active` ajoute déjà une bordure d'encre, et les hooks du Harnais auraient bordure plus anneau.
  - `pages.css:454-459` : `.diagram-path-core` vaut `var(--spacing-stroke-min)`. `src/wavestack/web/static/tokens.css:127` : `--spacing-stroke-min: 2px`, et aucun jeton à 3 px. AD-28 écrit « 3 px », mais aussi « valeurs exactes : DESIGN.md et `tokens.css` seulement ». `pages.css` contient déjà des largeurs littérales (7px l.449, 6px l.470).
  - `src/wavestack/web/static/app.js:13` : le Harnais n'importe que `block`, `light`, `marker`, `svgEl`, `wire` et `wireLayer`, ni `createStepper` ni `explain`. `mcp.js` n'importe pas encore `diagram.js`. L'Atelier MCP est donc le premier consommateur du stepper et de `explain`. Seuls l'anneau et le fil de 3 px touchent le Harnais.
  - `tests/test_ui_texts.py:30` : la table page → scripts ne liste `diagram.js` que pour `index.html`. Il faut l'ajouter pour `mcp.html`. Aucun test E2E ne vise aujourd'hui les règles `diagram-*` : il n'y a pas d'E2E à « suivre », il faut en écrire.
- **Verdict :** **confirmé**, avec réserves (jeton de 3 px, bulle non focalisable, doublon d'encre sur les hooks).
- **Correctif :**
  - (1) Ajouter un jeton (par exemple `spacing-stroke-path: 3px`) dans DESIGN.md et `tokens.css`, contrôlé par le test des jetons, ou retirer « 3 px » de l'AD et renvoyer à DESIGN.md.
  - (2) Écrire : « `explain()` ferme sa bulle au `focusout` quand `relatedTarget` n'est ni le bloc ni dans la bulle, et n'est pas `null` », ou rendre la bulle focalisable (`tabindex="-1"`).
  - (3) Vérifier visuellement `arch-hook.is-active`.
  - (4) Remplacer « les E2E du harnais suivent » par « les E2E du harnais *ajoutent* la couverture » et ajouter `diagram.js` pour `mcp.html` dans `test_ui_texts.py`.

### V14 — AD-3, lot 4 : « Arrêter » pendant une génération garde la connexion

- **Affirmation (AD-3, AD-27) :** pendant une génération, « Arrêter » n'arme que le `CancelToken`. Pendant une requête MCP, il ferme aussi la connexion.
- **Preuves :** `app_session.py:9752-9764`. Aujourd'hui, `_mcp_lab_stop` arme le jeton puis ferme toujours la connexion (`conn.close(wait=False)`). Le jeton est bien testé par `_call_model` et `run_call` (paramètre `cancel`, `app_session.py:7695, 8071`).
- **Verdict :** **confirmé** comme décision, mais c'est un changement à faire.
- **Correctif :** préciser que la session tient la phase de l'échange en cours (par exemple `_mcp_lab_phase: model|mcp`, sous le verrou) et que `_mcp_lab_stop` ne ferme la connexion qu'en phase `mcp`.

---

## Hors portée, remarqué en passant

- AD-26, lot 4 (« un quatrième appel du corps ») dépend de V1 : si l'appel cloud de l'atelier ne passe pas par `_call_model_chat`, la règle « le corps envoyé = `outbound_request.body` » doit être assurée par la nouvelle voie, comme elle l'est par `_lab_cloud_call`.
