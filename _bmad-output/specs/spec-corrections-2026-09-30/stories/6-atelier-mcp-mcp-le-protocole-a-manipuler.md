---
title: 'Atelier MCP (/mcp) : le protocole à manipuler'
type: 'feature'
created: '2026-10-01'
status: 'in-progress'
baseline_revision: '1bc25bfcc85f6761ca38f9356bc315c4aad1f2a0'
review_loop_iteration: 0
followup_review_recommended: false
context:
  - '{project-root}/_bmad-output/specs/spec-corrections-2026-09-30/SPEC.md'
  - '{project-root}/_bmad-output/specs/spec-corrections-2026-09-30/atelier-mcp.md'
  - '{project-root}/_bmad-output/specs/spec-langues/i18n-conventions.md'
warnings: []
deferred: []
---

<intent-contract>

## Intent

**Problem:** Le MCP n'a qu'une carte de brique et des nœuds du schéma : le protocole (processus séparé, poignée de main, `tools/list`, `tools/call`, JSON-RPC) n'est visible nulle part, alors que le LLM nu et le RAG ont leur page (CAP-6 de `SPEC.md`).

**Approach:** Une page `/mcp` sur le modèle de `/rag`, en cinq sections (détail dans `atelier-mcp.md`), avec ses propres connexions MCP en bac à sable, des intentions `mcp_lab_connect` et `mcp_lab_call` sous un état de session `mcp_lab`, et trois événements `mcp_lab_*`. Incrément minimal livrable : sections 1 à 3.

## Boundaries & Constraints

**Always:**
- **Page** `GET /mcp` → `static/mcp.html` (+ `mcp.css`, `mcp.js`) ; tête identique aux autres pages (`theme.js`, `i18n.js`, `site-nav.js`, fonts, `tokens.css`, `pages.css`). La barre commune des **cinq pages existantes et de la nouvelle** gagne « Atelier MCP » (`/mcp`) entre « Atelier RAG » et « Diagnostic » (`common.links.mcp`, `common.links.mcp_title`, `LINK_NAMES` d'`i18n.js`). La carte de la brique MCP de l'atelier porte un lien vers `/mcp`.
- **Snapshot** `GET /api/mcp_lab` → `{servers, content, content_error_text, last_session, session_state, seq}` ; `servers` = les trois serveurs de `mcp_servers(cfg)` avec transport, adresse ou commande, `sends_text` ; `last_session` = les événements `mcp_lab_*` de la dernière connexion (rejouables par la page). La page lit `/api/stream` à partir de `seq` et ne garde que `mcp_lab_*` et `session_state` (même lecteur SSE que `rag.js`).
- **Intentions** (classe b, acceptées en `idle` seulement, sinon 409 avec la raison) : `mcp_lab_connect{server}` et `mcp_lab_call{server, tool, args}`. Nouvel état `mcp_lab` (`SessionState`, texte `session.state.mcp_lab` : « Atelier MCP : échange en cours ; attendez sa fin ou arrêtez-le. »), tenu pendant la connexion ou l'appel, retour à `idle` après. `stop` (classe c) accepte `mcp_lab` et **ferme** la connexion de l'atelier (le jeton d'annulation seul ne suffit pas sur la boucle asyncio).
- **Bac à sable** : l'atelier ouvre ses propres `McpConnection` (jamais `_mcp_conns` de la brique), ne change ni `_mcp_enabled` ni `_mcp_lazy`, et ferme sa connexion à la connexion suivante, au `stop`, au changement de langue et à la fermeture de la session (aucun processus enfant laissé, vérifié comme dans `test_mcp.py`). Serveurs publics : `create_async_client` et la garde réseau (AD-15), la portée de trace de l'atelier posée sur la connexion pour que `outbound_request` porte le contexte `mcp_lab`.
- **JSON-RPC brut** : d'abord tenter la capture réelle en enveloppant les flux lus et écrits entre le transport et la session du SDK `mcp` 2.2 (vérifier dans `.venv/Lib/site-packages/mcp` ce que `Client` accepte : transport personnalisé, gestionnaire de messages) ; sinon reconstruire chaque message depuis les objets `mcp_types` (`initialize`, réponse du serveur, `tools/list`, `tools/call`) et le marquer `reconstructed: true`, affiché « reconstitué » dans la page. Le choix est écrit dans ARCHITECTURE-SPINE.
- **Événements** (contexte `mcp_lab`, `turn_id` nul, `step_id` `mcp{n}`, `brick = mcp`, `component = mcp_lab.{server}`, validés par `PAYLOAD_MODELS`) :
  - `mcp_lab_message{direction: to_server|from_server, method, jsonrpc: str, elapsed_ms, reconstructed: bool}` ;
  - `mcp_lab_connect_ended{server, status: ok|error, tools: [{name, description, schema, doc_tokens}], full_tokens, lazy_tokens, error_text}` ;
  - `mcp_lab_call_ended{server, tool, status: ok|error, raw, text, truncated, error_text, duration_ms}`.
- **Poids** : `doc_tokens` d'un outil = tokens de sa définition telle que `_tool_definitions` la rend (nom exposé `{serveur}__{outil}`, description, schéma) ; `full_tokens` = somme ; `lazy_tokens` = tokens de la ligne de catalogue `_doc_catalog` par outil plus la définition de `load_tool_doc`. Compte par le moteur s'il est chargé, sinon estimation (`_count_tokens`), dite « estimé ».
- **Appel** : un champ par paramètre du schéma (texte, nombre, booléen ; autre type → champ JSON), préréglages `call_presets` de `content/mcp.yaml` ; résultat brut JSON-RPC puis texte réinjecté (`result_text` puis `_bound_result`, troncature indiquée). Erreurs montrées : argument invalide (`is_error`), serveur injoignable (`describe_error`), délai dépassé.
- **Ce que le modèle voit** (section 5) : le bloc « outils » du contexte avec les outils du serveur connecté, en documentation complète et en lazy loading, sans génération.
- **Textes** : `content/mcp_lab.yaml` (pydantic, `extra = "forbid"`, champs `*_text`) et `content/i18n/{en,de}/mcp_lab.yaml` ; libellés d'interface dans `ui.yaml` section `mcp` ; messages backend par `msg()` ; trois langues. Libellé de journal pour les trois `kind` (`main.log.kinds`) et résumé dans `eventSummary` d'`app.js`.
- DESIGN.md (`mcp-screen`), EXPERIENCE.md (surface, composants, état `mcp_lab`), ARCHITECTURE-SPINE (route, intentions, état, événements, bac à sable), README (section « Atelier MCP » après « Atelier RAG ») mis à jour.

**Never:**
- Toucher aux connexions ou aux réglages de la brique MCP de l'atelier.
- Lancer une génération ; appeler un serveur public sans la garde réseau.
- Traduire les descriptions d'outils des serveurs publics.

## I/O & Edge-Case Matrix

| Scenario | Input / State | Expected Output / Behavior | Error Handling |
|----------|--------------|---------------------------|----------------|
| Connexion locale | « Se connecter » au glossaire | `initialize`, réponse, `tools/list` affichés avec sens et durée ; `list_terms`, `define_term` avec leur poids | — |
| Appel valide | `define_term{term: "harnais"}` | requête `tools/call`, réponse brute, texte réinjecté | — |
| Argument invalide | terme inconnu | réponse `is_error` montrée, statut `error` | pas de 500 |
| Serveur public hors ligne | data.gouv.fr sans réseau | `mcp_lab_connect_ended{status: error}` avec `describe_error` | page lisible |
| Occupé | atelier en tour | 409 avec la raison, rien ne démarre | — |
| Arrêt | « Arrêter » pendant un appel | connexion fermée, `idle`, aucun processus enfant restant | — |
| Brique intacte | connexion de l'atelier | `_mcp_enabled`, `_mcp_lazy`, `_mcp_conns` inchangés | — |

</intent-contract>

## Code Map

- `src/wavestack/mcp/connection.py` -- `McpConnection(server, loop, *, connect_timeout, call_timeout, language)` l.78 (`idle_scope`/`scope` lus par le crochet HTTP l.93-94), `_transport` l.102-109 (stdio : `StdioServerParameters(sys.executable, -m wavestack.mcp.local_server, lang)` ; HTTP : `create_async_client(scope=…)` puis `streamable_http_client`), `_serve` l.111 (`mcp.Client(transport, mode="legacy")`, `list_tools`, file d'appels `call_tool` sous `anyio.fail_after`), `start` l.152, `aclose` l.162, `call` l.188, `close` l.211 ; `describe_error` l.44-64, `result_text` l.67.
- `src/wavestack/mcp/servers.py` -- `McpServer` l.16-31, `mcp_servers(cfg)` l.34, `ServerText` l.44, `CallPreset` l.58, `McpContent` l.66, `load_mcp_content(lang)` l.76 ; `src/wavestack/mcp/local_server.py` (glossaire, `list_terms`, `define_term`, terme inconnu → `is_error`).
- `src/wavestack/tools/registry.py:131-135,192-208` -- `exposed_name`, `definition(name)`.
- `src/wavestack/session/app_session.py` -- état MCP de la brique l.855-861, 953-954 ; `_mcp_connect` l.5000, `_mcp_apply` l.5058, `_mcp_spec` l.5097 (aperçu `tools/call` l.5109-5115), `aclose_mcp` l.5150, `close()` l.1568, changement de langue l.5272 ; `_tool_definitions` l.3846, `_doc_catalog` l.3872, `LOAD_TOOL_DOC` l.217, `_load_tool_doc_spec` l.4790 ; `_count_tokens` l.4576, `_bound_result` l.6507-6550 ; modèle de classe (b) : `run_rag_lab` l.8282-8316 (verrou, refus, `CancelToken`, état, `_executor.submit`, `finally` → `idle` l.8411-8413), `_RAG_LAB_FR` l.322, `rag_lab_state()` l.8254-8274, `_rag_lab_scope` l.8164-8179, `_rag_lab_emit` l.8415 ; `stop()` l.5508-5530.
- `src/wavestack/trace/catalog.py` -- `SessionState` l.64-75, payloads MCP l.634-644, `PAYLOAD_MODELS` ~l.1279 ; `trace/journal.py:38` `emit`, `trace/scope.py` `scoped`.
- `src/wavestack/web/app.py` -- routes des ateliers (modèle : `RagLabRunIntention` l.186, route l.402-411, 409 par `SendRefused`), `stop` l.661, pages l.~300.
- `src/wavestack/net/factory.py:50,144` -- crochet `_check_and_trace` (`outbound_request`), `create_async_client`.
- `src/wavestack/rag/lab.py:100-201` -- modèle de contenu strict et chargeur à cache (à copier pour `mcp_lab.yaml`) ; `config.clear_content_caches` l.1113.
- `src/wavestack/web/static/rag.html`, `rag.js` (lecteur SSE l.735-771, `refresh` l.788-820, `main` l.822), `rag.css` -- gabarit de page ; barre commune dans les cinq HTML (`nav.site-nav`).
- `src/wavestack/web/static/app.js` -- `renderBricks()` l.1106, corps de carte l.1216-1239 (lien vers `/mcp` près de `brick-outbound` l.1230), `eventSummary` ~l.6175.
- `content/mcp.yaml` et `content/i18n/{en,de}/mcp.yaml` ; `content/bricks/mcp.yaml` ; `content/ui.yaml` (`common.links` l.74-82, sections `llm` l.852, `rag` l.877) ; `content/messages.yaml:70` (`session.state.*`).
- `tests/test_mcp.py` -- fixtures `loop` l.63, `web` l.115 (`McpWeb` l.74-112 : serveur JSON-RPC en processus, `offline`, `delay`, `error`), `local_servers()`/`no_local_server_left()` l.186-202, helpers l.128-161 ; `tests/test_web_app.py:51` (`SITE_PAGES`), `tests/test_ui_texts.py:29-32,221` (`PAGES`), `tests/test_web_tokens.py:536,588`.
- `tools/e2e/run_e2e.py` -- `s_mcp_full` l.2744, `s_mcp_lazy` l.2783, `s_rag_lab` l.7696 (gabarit, `_site_nav_problems`) ; captures 61 et 62.
- ARCHITECTURE-SPINE : liste des `kind` l.104-121, AD-3 l.132-146, AD-15 l.411-456, AD-18 l.490-505, AD-19 l.509-536, AD-24 l.629 ; EXPERIENCE.md surfaces l.25-37, composants l.121-148 ; DESIGN.md `site-nav` l.239, composants l.957-1040 ; README « Atelier RAG » l.355.

## Tasks & Acceptance

**Execution (incrément 1 : sections 1 à 3 ; incrément 2 : sections 4 et 5) :**
- `src/wavestack/mcp/lab.py` (nouveau) -- capture ou reconstruction JSON-RPC, calcul des poids, contenu `McpLabContent`.
- `src/wavestack/session/app_session.py` -- `mcp_lab_state`, `mcp_lab_connect`, `mcp_lab_call`, état `mcp_lab`, `stop`, fermetures.
- `src/wavestack/trace/catalog.py`, `src/wavestack/web/app.py` -- état, payloads, routes.
- `src/wavestack/web/static/mcp.html`, `mcp.js`, `mcp.css` ; barre commune des cinq pages ; `i18n.js` ; `app.js` (lien de carte, `eventSummary`).
- `content/mcp_lab.yaml` et surcouches, `content/ui.yaml` et surcouches, `content/messages.yaml` et surcouches.
- `tests/test_mcp_lab.py` -- serveur local réel en stdio et `McpWeb` pour le public : matrice complète, brique intacte, aucun processus restant, refus 409, arrêt ; `test_web_app`, `test_ui_texts`, `test_web_tokens`, `test_i18n` étendus à la sixième page.
- `tools/e2e/run_e2e.py` -- `s_mcp_lab` : connexion au glossaire local, messages affichés, poids, appel valide puis terme inconnu, barre commune ; captures `61-atelier-mcp-poignee-de-main`, `62-atelier-mcp-appel` ; inscrit dans `SCENARIOS`.
- DESIGN.md, EXPERIENCE.md, ARCHITECTURE-SPINE, README.

**Acceptance Criteria:**
- Given `/mcp` en `de`, when le stagiaire se connecte au glossaire local, then il voit `initialize` et `tools/list` avec leur sens et leur durée, puis les deux outils avec leur poids complet et lazy, sans texte français hors noms propres et descriptions servies.
- Given une connexion de l'atelier ouverte, when l'atelier principal joue un tour avec la brique MCP, then la brique utilise ses propres connexions, inchangées.

## Verification

**Commands:**
- `uv run ruff check .` et `uv run ruff format --check .` -- expected: aucun écart.
- `node --check` sur `mcp.js`, `app.js`, `i18n.js` -- expected: aucune erreur.
- `uv run pytest -q tests/test_mcp_lab.py tests/test_mcp.py tests/test_mcp_lazy.py tests/test_web_app.py tests/test_ui_texts.py tests/test_web_tokens.py tests/test_i18n.py` -- expected: tout passe.
- E2E (orchestrateur) : `--only mcp_lab mcp_full mcp_lazy annex_language` -- expected: 0 échec.

## Implementation Notes (2026-10-01)

Implémentation livrée en entier (incréments 1 et 2, sections 1 à 5), **non vérifiée** : seuls `ruff check`, `ruff format --check` et `node --check` ont été passés ; ni `pytest` ni l'E2E n'ont été lancés (PC partagé avec une autre suite). Décisions prises sans question :

- **JSON-RPC brut : capture réelle**, pas de reconstruction. `mcp.Client` (SDK 2.2) accepte tout `Transport` (`_connect_transport` entre le gestionnaire de contexte et rend `(read_stream, write_stream)`) : `mcp/lab.LabConnection` enveloppe les flux du transport stdio ou Streamable HTTP (`_ReadTap`, `_WriteTap`) ; chaque `SessionMessage` est sérialisé comme le transport (`model_dump_json(by_alias=True, exclude_unset=True)`). `reconstructed` reste `false` ; le champ est gardé pour le contrat. Écrit dans ARCHITECTURE-SPINE.
- **Durée d'un message** (`elapsed_ms`) : aller-retour pour une réponse (depuis sa requête, apparié par `id`), temps depuis le début de l'échange pour une requête ou une notification.
- **Échanges numérotés** `mcp{n}`, une connexion ou un appel chacun ; `last_session` = les enveloppes `mcp_lab_*` et `outbound_request` du contexte `mcp_lab` dont le numéro est ≥ celui de la dernière connexion (`_mcp_lab_first`).
- **Snapshot** : en plus des clés imposées, `call_presets` (ceux de `content/mcp.yaml`, par nom exposé) et `open_server` (le serveur dont la connexion de l'atelier est vivante, `null` sinon). La page relit `open_server` quand la session quitte `mcp_lab`.
- **Payloads** : `mcp_lab_connect_ended.tools[]` porte aussi `tool` (le nom côté serveur, celui de `mcp_lab_call`), `definition_text`, `line_text`, `line_tokens` ; l'événement porte aussi `load_tool_doc_tokens`, `lazy_definition_text`, `estimated` et `duration_ms`.
- **Poids** : la définition d'un outil vient du `_mcp_spec` de la brique et d'un `ToolRegistry` propre à l'atelier (rien n'est inscrit dans le registre de la brique), comptée sur son JSON compact (`json.dumps(…, ensure_ascii=False)`) ; `lazy_tokens` = la définition de `load_tool_doc` dont la description est l'intro plus une ligne par outil (`catalog_line`, désormais partagé avec `_doc_catalog`). C'est une approximation du rendu par le gabarit du modèle, qui peut ajouter quelques tokens de structure.
- **Appel** : `is_error` → statut `error`, `text` = le texte du serveur, `error_text` = `session.mcp_lab.is_error` ; réponse d'erreur JSON-RPC → `mcp.error.call_refused` ; connexion perdue → `session.mcp_lab.closed` ; délai → `describe_error` ; « Arrêter » → `session.mcp_lab.stopped`, et la connexion est fermée.
- **Journal de l'atelier principal** : `app.js` range les événements du contexte `mcp_lab` au journal seulement (comme ceux de `llm`), pour qu'une `outbound_request` de l'atelier MCP ne s'accroche jamais à une étape de la brique.
- **Traductions** : en plus des clés nouvelles, `mcp.error.*` et `mcp.block_not_shown` sont traduits en `en` et `de` (montrés par la page) ; l'allemand vouvoie.
- **Tests écrits, non lancés** : `tests/test_mcp_lab.py` (capture, connexion locale réelle, poids exacts au faux moteur, appel valide et terme inconnu, refus, serveur public tracé, hors ligne, erreur JSON-RPC, délai, arrêt pendant un appel et pendant la poignée de main, brique intacte pendant un tour, routes et 409, aucun processus restant) ; `test_web_app`, `test_ui_texts`, `test_web_tokens`, `test_i18n`, `test_backend_messages` (périmètre : `mcp/lab.py`) étendus ; E2E `s_mcp_lab` (captures 61 et 62) inscrit dans `SCENARIOS`, et l'ordre des liens de `_SITE_NAV_PROBLEMS_JS` passe à six pages.
- **Risques connus** : la barre commune à six liens en `de` à 1 280 px en projection n'a pas été mesurée (`_bar_fits`) ; les durées des tests d'arrêt et de délai (`McpWeb.delay`) sont à confirmer sur le PC cible.
