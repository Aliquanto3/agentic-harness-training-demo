# Atelier MCP : sections, architecture, tests (CAP-6, story 6)

Repris du lot 5 de `plan-corrections-2026-09-30.md`, avec les noms de champs de l'epic Langues (`*_text`).

## But

Une troisième page de focus, `/mcp`, sur le modèle de `/llm` et `/rag` : ce que fait le protocole entre le harnais et un serveur, sans l'atelier ni le modèle. Le stagiaire voit qu'un serveur MCP est un processus séparé, que le harnais lui parle en JSON-RPC, et ce que sa documentation pèse dans le contexte.

## Sections, dans l'ordre d'un échange réel

1. **Les serveurs** : les trois de `content/mcp.yaml` (glossaire local en stdio, data.gouv.fr et Microsoft Learn en Streamable HTTP), avec transport, adresse ou commande de lancement, et ce qui sort du poste (`sends_text`). Bouton « Se connecter » par serveur.
2. **La poignée de main** : `initialize` → réponse (nom, version, capacités) → `tools/list`. Chaque message JSON-RPC affiché tel quel, avec son sens (harnais → serveur, serveur → harnais) et sa durée. Un serveur public montre aussi l'`outbound_request` (adresse, en-têtes, corps), comme le volet Orchestration.
3. **La documentation des outils** : pour chaque outil, son nom `{serveur}__{outil}`, sa description et son schéma d'arguments ; à côté, son poids en tokens dans le contexte, serveur par serveur, en documentation complète et en lazy loading (`load_tool_doc`, une ligne par outil).
4. **L'appel** : un champ par paramètre du schéma, préréglages `call_presets` de `content/mcp.yaml` ; requête `tools/call` et résultat JSON-RPC bruts, puis le texte tel que le harnais le réinjecterait (`result_text`, bornage du lot B). Erreurs à montrer : argument invalide (`is_error`), serveur injoignable (`describe_error`), délai dépassé.
5. **Ce que le modèle voit** : le bloc « outils » du contexte tel qu'il partirait au modèle avec les serveurs cochés, sans génération.

## Architecture (calquée sur les stories 29 et 30, AD-19, AD-24)

- `GET /mcp` sert `static/mcp.html` (+ `mcp.css`, `mcp.js`, `theme.js` et `i18n.js` en tête, `tokens.css` seulement). `GET /api/mcp_lab` rend `{servers, content, content_error_text, last_session, session_state, seq}` ; la page lit `/api/stream` à partir de `seq` et ne garde que le contexte `mcp_lab` et `session_state`.
- Intentions de classe (b), acceptées en `idle` seulement, nouvel état de session `mcp_lab` (« Atelier MCP : échange en cours ; attendez sa fin ou arrêtez-le. », par `msg()`) : `mcp_lab_connect{server}`, `mcp_lab_call{server, tool, args}`. `stop` (classe c) ferme la connexion.
- Bac à sable : l'atelier ouvre ses propres `McpConnection`, jamais celles de la brique (`_mcp_conns`), fermées à la sortie de la page ou au `stop` ; il ne change ni `_mcp_enabled` ni `_mcp_lazy`. Le serveur local est relancé en processus enfant pour l'atelier. Les serveurs publics passent par `create_async_client` et la garde réseau (AD-15) ; hors ligne, la section 2 montre l'erreur.
- Événements, contexte `mcp_lab` (`turn_id` nul, `step_id` `mcp{n}`, `brick = mcp`, `component = mcp_lab.{server}`) :
  - `mcp_lab_message{direction: to_server|from_server, method, jsonrpc: str, elapsed_ms}` ;
  - `mcp_lab_connect_ended{server, status, tools: [{name, description, schema, doc_tokens}], full_tokens, lazy_tokens, error_text}` ;
  - `mcp_lab_call_ended{server, tool, status, raw, text, truncated, error_text, duration_ms}`.
- Point dur : le SDK `mcp` n'expose pas les messages JSON-RPC bruts. Hook de transport (flux lus et écrits par la session) si possible ; sinon reconstruction depuis les objets `mcp.types`, et la page le dit (« reconstitué »).
- Textes : `content/mcp_lab.yaml` (pydantic, `extra = "forbid"`), décliné dans `content/i18n/{en,de}/mcp_lab.yaml` ; libellés d'interface dans `ui.yaml` section `mcp`. Les descriptions des outils viennent du serveur (dans la langue de la session pour le serveur local).
- Navigation : « Atelier MCP » dans la barre commune, entre « Atelier RAG » et « Diagnostic » ; la carte de la brique MCP de l'atelier y renvoie.

## Tests

- `tests/test_mcp_lab.py` : doublure de serveur en stdio, comme `test_mcp.py`.
- E2E `s_mcp_lab`, captures `61-atelier-mcp-poignee-de-main`, `62-atelier-mcp-appel` (59 et 60 sont déjà pris).
- `test_web_tokens`, `test_i18n` (nouveau fichier de contenu dans les trois langues, clés `ui.yaml`).
- README : section « Atelier MCP » après « Atelier RAG ».

## Incrément livrable minimal si la story bloque

Sections 1 à 3 (serveurs, poignée de main, documentation et poids), sans le formulaire d'appel ; la page le dit.
