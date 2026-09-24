---
title: 'MCP local et public : serveurs, échanges visibles, documentation complète'
type: 'feature'
created: '2026-09-24'
status: 'done'
route: 'dispatch'
review_loop_iteration: 0
context: []
baseline_commit: 'fa7d468b78522d2dce64fac3ba964d241165bd0a'
---

<frozen-after-approval reason="human-owned intent — do not modify unless human renegotiates">

## Intent

**Problem:** Les outils du harnais sont tous déclarés dans son propre code : rien ne montre qu'un serveur MCP est un processus séparé, éventuellement distant, qui expose ses outils, ni ce que pèse leur documentation dans le contexte (CAP-20, CAP-21, CAP-23).

**Approach:** Une brique `mcp` (harness engineering) dont chaque serveur est une sous-option : un serveur local en stdio (processus enfant, hors ligne, glossaire du démonstrateur) et deux serveurs publics en Streamable HTTP (data.gouv.fr, Microsoft Learn), connectés à l'activation par le SDK `mcp`. Leurs outils entrent, en documentation complète, dans le registre et l'exécuteur uniques de 5a sous le nom `{server_id}__{tool}` ; le transport HTTP passe par un client asynchrone de la fabrique `net`, tracé et filtré comme en 5b.

## Boundaries & Constraints

**Always:**
- AD-14 : `ToolRegistry` seul nomme ; outil MCP = `{server_id}__{tool}`, `source` `mcp_local`/`mcp_public`, `component` `mcp.{server_id}`, `network=True` pour un serveur public. Collision : outil indisponible, `harness_error`. Tout appel passe par l'exécuteur unique ; `is_error` du serveur → `tool_ended{error}` réinjecté.
- AD-15 : `net.create_async_client` (httpx2) partage la configuration de `create_client` : truststore, proxy, délais, refus hors `allowed_hosts` (`NetworkBlocked` avant envoi), `outbound_request{origin: brick}` avec le corps JSON-RPC exact avant chaque envoi, revérifié à chaque saut. Hôtes ajoutés : `mcp.data.gouv.fr`, `learn.microsoft.com`. Le serveur local installe la garde (boucle locale seule) avant tout import tiers.
- AD-15/AD-12 : un serveur n'est contacté (`initialize`, `tools/list`) qu'à l'activation de sa sous-option, brique voulue ; avant, rien ne sort. État `not_contacted` → `available` / `unavailable` + raison française ; décocher puis recocher retente. Un serveur indisponible n'empêche ni les autres serveurs ni les outils natifs.
- AD-21/AD-24 : le serveur local démarre (`sys.executable -m wavestack.mcp.local_server`) à l'activation et s'arrête à la désactivation ; tout s'arrête à la fermeture (attente bornée puis `terminate`). Les clients vivent sur la boucle asyncio de FastAPI ; le thread de travail les appelle par `run_coroutine_threadsafe(...).result(timeout)`.
- AD-4 : chaque outil MCP d'un serveur disponible est un segment `tool_catalog` de la variable `tools`, attribué à la brique `mcp` et au composant du serveur ; sa réponse est un `tool_result` du même composant.
- AD-16 : toute erreur MCP (démarrage, protocole, réseau, délai) devient un état ou un `harness_error` en français ; jamais de plantage.
- Aucun test ne sort du poste : serveurs MCP de test en processus ou `httpx2.MockTransport` ; un test vérifie le refus de la garde sous `ProactorEventLoop` avec le vrai client MCP.
- UX : sous-options serveurs (étiquette `Local` / « RÉSEAU ») ; nœud serveur séparé du harnais (zone Poste de travail ou Réseau), outils listés dans son infobulle ; étapes de découverte (connexion, outils trouvés) dans Orchestration ; badge « MCP » sur l'étape d'un outil MCP ; `outbound-payload` pour chaque requête d'un serveur public.

**Décisions (2026-09-24) :**
- Story scindée : le lazy loading (CAP-22) part en story 6b (voir `deferred-work.md`). Cette story livre la documentation complète seule.
- Serveur local : un glossaire des notions du démonstrateur, `list_terms` et `define_term(term)`, lu dans `content/mcp_local/glossary.yaml`, en français.
- Sous-options à l'activation de la brique : serveur local coché, serveurs publics décochés.
- Un serveur n'est dessiné qu'une fois sa sous-option cochée, d'abord « non contacté » pendant la connexion (comme les outils réseau de 5b ; UJ-1 : « un nœud apparaît »).
- La brique `mcp` n'exige pas la brique `tools` ; elle exige `tool_call_parser`.
- data.gouv.fr dépasse volontairement la fenêtre par défaut (AD-9) : la carte de dépassement nomme les descriptions d'outils et propose de désactiver un serveur.
- Nouvelle tentative par réactivation de la sous-option (AD-15, CAP-21), sans redémarrer WaveStack.

**Never:** pas de lazy loading ni de `load_tool_doc` (6b) ; pas de H5 ni d'aperçu `preview` MCP (story 8) ; pas d'action forcée ni de rejeu (story 9) ; pas d'instantanés `content/mcp_snapshots/` ni d'avertissement d'écart (story 10) ; pas de serveur Node/npx ; pas de seconde boucle asyncio ; le front ne calcule aucun état (AD-1).

## I/O & Edge-Case Matrix

| Scenario | Input / State | Expected Output / Behavior | Error Handling |
|----------|--------------|---------------------------|----------------|
| Local | Brique activée | Processus enfant lancé, `mcp_connect_started`/`ended{ok, tools}`, nœud local distinct, `local__define_term` et `local__list_terms` dans `tools` | Échec de lancement : `unavailable` + raison |
| Appel local | Modèle appelle `local__define_term(term="MCP")` | Étape badge MCP, définition réinjectée, aucun `outbound_request` | Terme inconnu : `is_error` → `tool_ended{error}` |
| Public | Microsoft Learn coché | `outbound_request` pour `initialize`, `notifications/initialized`, `tools/list`, hors tour ; nœud réseau `available` | N/A |
| Appel public | Modèle appelle `mslearn__microsoft_docs_search` | `outbound-payload` avec le corps `tools/call` sur l'étape, résultat texte réinjecté | Délai → `tool_ended{error}`, nœud `unavailable` |
| Hors ligne | Serveur public coché sans réseau | `unavailable` + raison, toujours dessiné ; local et natifs utilisables | Recocher retente |
| Refus | Hôte du serveur hors `allowed_hosts` | `NetworkBlocked` avant envoi, rien de tracé | `unavailable` + raison |
| Désactivation | Sous-option ou brique décochée | Connexion fermée, processus local arrêté, outils retirés au tour suivant | N/A |
| Dépassement | data.gouv.fr coché, fenêtre 4 096 | `context_overflow` dont la cause nomme les descriptions d'outils | Appel non envoyé |
| Collision | Deux outils de même nom exposé | Le second indisponible, `harness_error` | N/A |

</frozen-after-approval>

## Code Map

- `pyproject.toml`, `uv.lock` -- `uv add "mcp>=2.2,<2.3"` (MIT ; tire `httpx2`, `anyio`, `pywin32`) ; vérifier les licences tirées (NFR-10).
- `src/wavestack/net/factory.py` -- extraire contrôle et trace de `_trace_request` dans une fonction commune prenant la portée ; ajouter `create_async_client(scope: Callable[[], TraceScope], transport=None) -> httpx2.AsyncClient` (hook `async`, `journal.emit(..., scope=scope())`). Réutiliser `USER_AGENT`, `is_host_allowed`, `NetworkBlocked`.
- `src/wavestack/net/guard.py` -- inchangé (`check_host` décode déjà les octets IDNA d'anyio, 1c) sauf `find_blocked(exc) -> NetworkBlocked | None`, qui parcourt `__cause__`, `__context__` et `ExceptionGroup.exceptions`.
- `src/wavestack/mcp/` (nouveau) -- `connection.py` : `McpConnection` ; une tâche longue entre `mcp.Client(transport, mode="legacy")` (poignée de main `initialize` d'AD-15, pas de sonde `server/discover`), liste les outils, puis sert une file d'appels jusqu'à la fermeture (les portées anyio se ferment dans la tâche qui les ouvre). `start()`, `call(name, args, timeout) -> str` (texte des blocs `text`, autres blocs nommés ; `is_error` → `ToolError`, transport ou délai → `Unreachable`), `aclose()`/`close()`. Transports : `StdioServerParameters(command=sys.executable, args=["-m", "wavestack.mcp.local_server"])` ; `streamable_http_client(url, http_client=create_async_client(...))`. `servers.py` : les trois serveurs (id `local`/`datagouv`/`mslearn`, URL depuis `[mcp]`). `local_server.py` : `install([])` puis `MCPServer` (`mcp.server.mcpserver`) en stdio, deux outils sur le glossaire.
- `src/wavestack/tools/registry.py` -- `ToolSpec` + `description: str | None`, `schema: dict | None` (inputSchema tel quel), `required: tuple[str, ...] | None` (None = tous) ; `definition()` les utilise quand présents (nom d'abord, description en dernier) ; filtre de contenu (L87) limité aux specs sans `description` ; `add(specs)`/`remove(prefix)` réutilisant le contrôle de collision (L77).
- `src/wavestack/tools/executor.py` -- `check` : requis selon `spec.required` ; un type de schéma inconnu est déjà accepté (L64). `tool_started` porte `source`.
- `src/wavestack/tools/parser.py` -- `_convert` garde le texte sur un type inconnu : rien à changer, couvrir par un test.
- `src/wavestack/session/app_session.py` -- `attach_loop(loop)` ; `_mcp_enabled` (défaut `{"local"}`), connexions et états ; `set_mcp_server` (classe a) ; connexion/fermeture dans `set_brick` et `set_mcp_server` ; fin de connexion appliquée sur le thread de travail (`_executor.submit`) : registre, `architecture_changed`, `bricks_changed`, `context_preview`. `build_turn_state` (L502) ajoute les outils MCP des serveurs disponibles quand la brique `mcp` est effective. Brique et composant tirés de `spec.component` au lieu de `"tools"` codé en dur (L537, L615, L856, L868). `_emit_architecture` (L231) : nœuds `mcp.{id}`, kind `mcp_server`, `contact`, `tools`. `_OVERFLOW_CAUSES_FR` (L80) + `TOOL_CATALOG`. `close()` ferme les connexions.
- `src/wavestack/bricks/registry.py`, `content/bricks/mcp.yaml`, `content/mcp.yaml`, `content/mcp_local/glossary.yaml` -- brique `mcp` (`harness`, `capabilities=["tool_call_parser"]`, `network=True`), composants `mcp.local` (`local_process`), `mcp.datagouv`, `mcp.mslearn` (`network_service`) ; libellés des serveurs ; glossaire (harnais, LLM nu, contexte, token, outil, MCP, skill, hook, RAG, sous-agent, lazy loading…).
- `src/wavestack/trace/catalog.py` -- `ArchitectureNode.kind` + `mcp_server` et `tools: list[str] = []` ; `ToolStartedPayload` + `source` ; kinds `mcp_connect_started{server, phase_label}` et `mcp_connect_ended{server, status, tools, error_fr, duration_ms}` dans `PAYLOAD_MODELS` (L260).
- `src/wavestack/web/app.py` -- lifespan : `attach_loop(asyncio.get_running_loop())` à l'entrée, `await` fermeture MCP avant `close()` ; `POST /api/intentions/mcp_server {server, enabled}`.
- `src/wavestack/web/static/app.js` -- `brickOptions` (L393) : endpoint selon la brique (`setTool` L428 figé sur `/tool`) ; `applyEnvelope` (L104, pas de `default`) : `mcp_connect_*` en étapes hors tour ; `toolCard` (L782) : badge MCP selon `source` ; `renderSchema` (L970) : `mcp_server` en deuxième rangée, outils dans le `title` ; la ligne L359 (étiquette de brique toujours locale) reste telle quelle, la brique mêlant local et réseau. `app.css` : badge MCP.
- `tests/test_mcp.py` (nouveau), `tests/test_net_factory.py`, `tests/test_net_guard.py` -- fixture qui fait tourner une boucle dans un thread (`attach_loop`) ; serveur MCP de test en processus (`Client(MCPServer)`) ou `httpx2.MockTransport` ; motifs `booted_session`/`FakeEngine` de `tests/test_tools.py`.

## Tasks & Acceptance

**Execution:**
- [x] `pyproject.toml`, `wavestack.toml`, `src/wavestack/config.py` -- dépendance `mcp`, hôtes autorisés, `[mcp]` (URL publiques, `connect_timeout_s`, `call_timeout_s`) -- AD-15, NFR-10
- [x] `src/wavestack/net/factory.py`, `net/guard.py`, `tests/test_net_factory.py`, `tests/test_net_guard.py` -- client async tracé, `find_blocked`, refus sous Proactor avec le vrai client MCP -- AD-15
- [x] `src/wavestack/mcp/*`, `content/mcp_local/glossary.yaml` -- connexion, serveurs, serveur local -- AD-21, AD-24
- [x] `src/wavestack/tools/registry.py`, `executor.py` -- specs MCP, ajout/retrait, collisions, `source` -- AD-14
- [x] `src/wavestack/session/app_session.py`, `bricks/registry.py`, `trace/catalog.py`, `content/bricks/mcp.yaml`, `content/mcp.yaml` -- brique, états, tour, schéma, cause de dépassement -- AD-4, AD-12
- [x] `src/wavestack/web/app.py`, `static/app.js`, `static/app.css` -- boucle, intention, sous-options, étapes, badge, nœuds -- AD-1, AD-18
- [x] `tests/test_mcp.py` -- les 9 lignes de la matrice ; fermeture des connexions à `close()`

**Acceptance Criteria:**
- Given la brique MCP activée, when on coche Microsoft Learn, then la jauge « prochain tour » augmente du poids de ses trois descriptions, attribué au serveur.
- Given un serveur public disponible, when on ouvre son étape d'outil, then l'adresse et le corps `tools/call` exacts partis du poste s'affichent avant le résultat.
- Given WaveStack fermé (Ctrl+C), when on liste les processus, then aucun serveur MCP local ne survit.

## Implementation Notes

- Implémenté par un sous-agent (dispatch), diff relu dans cette session. `ruff check`, `ruff format --check` : propres. `pytest` : 187 passed, 2 deselected (tests `model`).
- Audit de la matrice : les 9 lignes sont couvertes par `tests/test_mcp.py` (serveur local réel en processus enfant ; serveurs publics par `httpx2.MockTransport`), tous exécutés. L'échec de lancement du serveur local (colonne « Error Handling » de la ligne 1) a été ajouté dans cette session (`test_local_server_that_cannot_start_is_unavailable_with_its_reason`). Refus de la garde sous Proactor avec le vrai client MCP : `tests/test_net_guard.py`.
- Choix : `mcp==2.2.0` (licences des dépendances tirées : MIT, BSD, Apache-2.0, PSF) ; `Client(..., mode="legacy", cache=None)` ; délai de lecture du client async à 300 s (flux d'événements du serveur), chaque appel borné par `call_timeout_s` ; configuration `[mcp] connect_timeout_s`, `call_timeout_s`, `[mcp.urls]` ; `ToolSpec.is_mcp` ; résultat de la connexion appliqué sur le thread de travail ; nœuds `mcp_server` en deuxième rangée du schéma (pas de zone dessinée à part, comme les nœuds réseau de 5b).
- Appel réel hors pytest par le sous-agent vers Microsoft Learn : 3 outils, `tools/call` rendu, toutes les requêtes tracées.
- Risques signalés : « Arrêter » n'interrompt pas un appel MCP en cours (borné par `call_timeout_s`, comme les outils réseau de 5b) ; `httpx2` importé directement sans être déclaré (arrive par `mcp`) ; erreurs propres au SDK en anglais ; tests du serveur local dépendants de `psutil` et du lanceur de venv Windows. Passe manuelle dans l'interface avec un vrai modèle non faite.
- Correctifs de revue P1 à P10 appliqués par le même sous-agent, vérifiés dans cette session : `ruff` propre, `node --check` propre, `pytest` : 194 passed, 2 deselected. Ajouts hors consigne, jugés corrects : drapeau `_calling` pour qu'une fermeture annule aussitôt un appel en cours ; `_mcp_failed` sans effet sur un serveur déjà décoché. `httpx2`, `anyio`, `mcp-types` déclarés sans changer le verrou.

## Spec Change Log

## Review Triage Log

Passe 1 (blind-hunter, edge-case-hunter, verification-gap ; 3 couches, 38 constats) :

- [BH2/EC1] `McpConnection.call` classe toute `MCPError` de `tools/call` en `Unreachable` : une erreur JSON-RPC (paramètres invalides) rend le serveur indisponible, le ferme et retire ses outils — `medium`, confirmé (`except Exception` dans `call`, puis `_after_mcp_call` → `_mcp_failed`). → P1 `patch` (`CONNECTION_CLOSED` reste `Unreachable`).
- [BH1/EC12] Un appel en cours n'est pas résolu quand la tâche de connexion est annulée (décocher pendant l'appel, arrêt) : le thread de travail attend `call_timeout + 1` et la fermeture bloque la boucle derrière lui — `medium`, confirmé (`except Exception` ne prend pas `CancelledError` ; `_run` ne vide que la file). → P2 `patch`.
- [BH3/BH4/EC6] Décocher puis recocher avant la fin d'une connexion : la fin de l'ancienne tentative se rattache à la nouvelle carte (`app.js` : dernière carte non terminée du serveur) et porte « décochez puis recochez » au lieu de « abandonnée » — `low`, confirmé (`error_fr or …` ; appariement `.at(-1)`) ; correction directe. → P3 `patch`.
- [BH5] Le résultat d'une connexion attend la fin du tour sur le thread de travail et `duration_ms` compte cette attente — `low`, confirmé (unique thread, AD-24) ; durée mesurée dans le rappel de fin, correction directe. → P4 `patch`.
- [EC2] Tour arrêté avant l'exécution : `_after_mcp_call` lit un `contact` périmé et peut fermer un serveur reconnecté sain — `low`, confirmé (`run` rend `None`, `contact` non effacé) ; garde d'une condition. → P5 `patch`.
- [EC5] Propriété de schéma booléenne (`true`) : `AttributeError` sur le thread de travail, serveur figé « non contacté » — `low`, confirmé (`(prop or {}).get`) ; correction directe. → P6 `patch`.
- [EC10] `httpx2.ConnectTimeout` est une `RequestError` : décrit « injoignable » au lieu de « délai » — `low`, confirmé (hiérarchie httpx2) ; correction directe. → P7 `patch`.
- [BH15] Message de dépassement `TOOL_CATALOG` : deux deux-points dans une phrase — `low`, confirmé ; reformulation. → P8 `patch`.
- [BH12] `httpx2`, `anyio`, `mcp_types` importés directement sans être déclarés — `low`, confirmé ; déclaration directe. → P9 `patch`.
- [VG1] Branchement `attach_loop`/`aclose_mcp` du lifespan jamais exercé — pré-vérifié. → P10 `patch` (test `with TestClient(app)`).
- [VG2] « Prend effet au prochain tour » de la brique MCP après un envoi non testé — pré-vérifié. → P10 `patch`.
- [VG3] Attribution à `mcp` d'un appel mal formé quand seule la brique MCP est effective non testée — pré-vérifié. → P10 `patch`.
- [VG4] Délai de connexion (serveur muet à `initialize`/`tools/list`) non testé — pré-vérifié. → P10 `patch`.
- [VG5] Isolement de la brique outils (options, `set_tool` sur un nom MCP) non testé — pré-vérifié. → P10 `patch`.
- [VG-o2] Rendu front de la story 6 (cartes de connexion, `setOption`, badge) non testé : aucun banc JS — `medium`, préexistant (même écart qu'en 5b). → `defer`.
- [BH7] La jauge sous-compterait le poids d'un serveur (schéma laissé au gabarit) — `false` : la définition garde le nom en tête et la description en fin, `_merge_groups` rattache tout le schéma enclavé au segment `tool_catalog` de l'outil ; seules les accolades de clôture vont au gabarit, comme pour les outils natifs.
- [BH6] Serveurs contactés quand la brique est voulue mais indisponible (modèle sans `tool_call_parser`) — `low`, rejeté : cas rare (les modèles par défaut ont un format d'appel), l'utilisateur a coché la sous-option ; il faudrait reconnecter au changement de modèle.
- [BH8] Carte de la brique sans état par serveur — `low`, rejeté : la spec place l'état dans le schéma et Orchestration.
- [BH9] Glossaire incomplet, entrée « lazy loading » — `low`, rejeté : choix de contenu ; la notion existe dans le démonstrateur (6b).
- [BH10] `define_term` exige le terme exact — `low`, rejeté : l'erreur liste les termes et n'est pas comptée comme essai (5a) ; appariement approché = logique supplémentaire.
- [BH11/EC16] Identifiants de serveurs répétés ; `[mcp.urls]` non table fait échouer le démarrage — `low`, rejeté : même motif que `fetch_page_hosts` en 5b (erreur de saisie de configuration).
- [BH13/EC14] `send` recalcule les outils MCP après `build_turn_state` : course de quelques microsecondes sur le badge « prochain tour » — `low`, rejeté : fenêtre infime, et dériver de `state.tools` casse le cas brique voulue mais indisponible.
- [BH14] Brique `tools` et `mcp` actives : un appel refusé visant un outil MCP est attribué à `tools` — `low`, rejeté : l'étape de refus appartient au harnais ; nommer la brique de l'outil visé ajoute une branche.
- [EC3] Serveur décoché puis recoché en plein tour, puis appel de l'ancien outil : la nouvelle connexion est fermée — `low`, rejeté : bascule en plein tour et appel du même outil, rare ; il faudrait porter l'identité de la connexion dans la spec d'outil.
- [EC4] Toute exception de `_mcp_apply` fige le serveur « non contacté » — `low`, rejeté après P6 : plus d'entrée connue qui lève.
- [EC7] Pagination de `tools/list` ignorée — `low`, rejeté : 10 et 3 outils sans curseur observés le 2026-09-24.
- [EC8] Résultat sans bloc texte mais avec `structuredContent` rendu vide — `low`, rejeté : les deux serveurs et le serveur local renvoient du texte.
- [EC9] Groupe d'exceptions dont la première feuille est secondaire — `maybe-false`, rejeté : au plus `low` (message moins précis) ; à vérifier sur une erreur réelle de transport.
- [EC11] `RequestError` sans requête attachée — `low`, rejeté : les transports httpx2 attachent toujours la requête.
- [EC13] Processus local mort entre deux appels : nœud encore disponible — `low`, rejeté : le prochain appel échoue et rend le serveur indisponible (`_mcp_failed`).
- [EC15] `required` nommant un argument absent de `properties` — `low`, rejeté : schéma invalide côté serveur, non observé.
- [VG-o1] `_mcp_failed` écrit `unavailable` pour un serveur déjà décoché — `low`, rejeté : sans effet visible, l'état est remis à zéro à la réactivation.

Groupes routés en `patch` : P1 à P10 ; `defer` : VG-o2 ; aucun `intent_gap` ni `bad_spec`, pas de loopback.

## Design Notes

Les requêtes HTTP partent de la tâche `post_writer` du transport, créée à la connexion : elle ne voit pas la `TraceScope` posée par l'appelant. La connexion tient donc la portée de l'appel en cours (ses appels sont en série dans sa file ; hors tour pendant la découverte), et le hook de la fabrique la lit :

```python
http = create_async_client(scope=lambda: conn.scope)
```

Essai réel du 2026-09-24 avec `mcp` 2.2.0 en mode `legacy` : data.gouv.fr (10 outils) et Microsoft Learn (3 outils) répondent en anonyme en ~1 s ; le hook voit `initialize`, `notifications/initialized`, `tools/list` (plus un `GET` de flux et un `DELETE` de fin de session pour Microsoft Learn).

## Verification

**Commands:**
- `uv run ruff check .` et `uv run ruff format --check .` -- expected: aucune erreur
- `uv run pytest` -- expected: tous les tests passent (tests `model` exclus)

**Manual checks (if no CLI):**
- `uv run wavestack` : activer MCP et demander « Que veut dire MCP ? » (serveur local) ; cocher Microsoft Learn, demander « Comment déployer une stratégie d'accès conditionnel Entra ID ? » et vérifier les données sortantes ; cocher data.gouv.fr (dépassement expliqué) ; couper le réseau et recocher.
