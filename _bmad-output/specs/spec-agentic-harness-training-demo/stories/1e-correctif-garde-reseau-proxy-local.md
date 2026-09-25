---
title: 'Correctif 1e : un proxy en boucle locale ne doit pas ouvrir la garde réseau'
type: 'bugfix'
created: '2026-09-25'
status: 'draft'
route: ''
review_loop_iteration: 0
context: []
baseline_commit: ''
---

<frozen-after-approval reason="human-owned intent — do not modify unless human renegotiates">

## Intent

**Problem:** Sur un poste où le proxy d'entreprise tourne en boucle locale (`HTTPS_PROXY=http://127.0.0.1:9000`, PAC `localproxy-*.pac` : le cas du PC pro visé), la garde réseau AD-15 ne voit plus les destinations. Un client qui lit les variables de proxy (`trust_env`) ouvre un socket vers `127.0.0.1:9000`, toujours accepté comme boucle locale, puis envoie `CONNECT hôte:443` dans ce tunnel : aucun `getaddrinfo` ni `connect` vers l'hôte réel, donc rien à filtrer. Le proxy décide seul.

Constaté le 2026-09-25 : avec ce proxy, deux tests échouaient.
- `test_cli_diagnostic.py::test_network_unreachable_warns_without_blocking` : `check_network()` renvoie `ok` au lieu de `warn`. La requête sort par le proxy alors que la garde de test n'autorise que la boucle locale.
- `test_net_guard.py::test_guard_blocks_the_real_mcp_client_under_proactor_event_loop` : le client MCP du SDK, sans fabrique, atteint le proxy. Celui-ci coupe la connexion (`RemoteProtocolError`) au lieu d'un `NetworkBlocked`.

Les deux passent sans `HTTPS_PROXY`. `tests/conftest.py` neutralise désormais le proxy du poste, ce qui rend la suite déterministe mais masque le défaut.

**Portée réelle :** aujourd'hui, toutes les requêtes HTTP de l'application passent par `net/factory.py` (`create_client`, `create_async_client`, y compris `mcp/connection.py`). La fabrique vérifie l'hôte de l'URL avec `is_host_allowed` avant l'envoi, donc aucun chemin connu ne sort de la liste. Ce qui est perdu, c'est la seconde ligne de défense : tout code qui contournerait la fabrique (dépendance tierce, futur client, SDK MCP sans `http_client`, processus enfant) sortirait sans contrôle, alors qu'AD-15 promet un refus au niveau du processus.

**Approach:** à trancher à la spec. Pistes :
1. Ne plus accorder au proxy la confiance de la boucle locale au niveau socket, et imposer que tout client proxifié soit créé par la fabrique (contrôle de l'hôte cible par l'URL). Un client hors fabrique qui passe par le proxy est refusé au `connect` vers le proxy.
2. Désactiver `trust_env` hors fabrique, en retirant les variables de proxy de `os.environ` après que la fabrique les a lues, pour que seul un client de la fabrique sache joindre le proxy.
3. Documenter le plafond dans AD-15 (proxy local = garde socket aveugle, la fabrique fait foi) et ajouter un test qui échoue si un module de `src/` crée un client HTTP hors fabrique.

## Boundaries & Constraints

**Always:**
- Les requêtes de la fabrique vers un hôte autorisé continuent de passer par le proxy du poste (sinon plus de réseau sur le PC pro).
- Garde stdlib seule, installée avant tout import tiers, identique dans les processus enfants.
- Aucun test ne sort du poste ; le proxy est simulé.

**Never:** pas de liste d'IP en configuration ; pas d'analyse du flux `CONNECT` dans la garde ; pas de nouvelle dépendance.

## I/O & Edge-Case Matrix

| Scenario | Input / State | Expected Output / Behavior | Error Handling |
|----------|--------------|---------------------------|----------------|
| Fabrique, hôte autorisé, proxy local | `HTTPS_PROXY=http://127.0.0.1:9000`, `create_client().head("https://huggingface.co")` | Requête envoyée via le proxy | N/A |
| Fabrique, hôte refusé, proxy local | Même proxy, `https://example.com` | `NetworkBlocked` avant envoi | Appelant |
| Client hors fabrique, proxy local | Même proxy, `httpx.Client(trust_env=True).get("https://example.com")` | Refusé (piste 1 ou 2), ou détecté par test (piste 3) | Appelant |
| SDK MCP sans `http_client`, proxy local | Test Proactor actuel, proxy défini | `NetworkBlocked` trouvé par `find_blocked` | Appelant |
| Proxy distant | `HTTPS_PROXY=http://proxy.corp.test:8080` | Comportement actuel inchangé | N/A |

</frozen-after-approval>

## Code Map

- `src/wavestack/net/guard.py` -- `is_host_allowed` (boucle locale et `_proxy_hosts()` toujours acceptés), filtre `socket.connect`.
- `src/wavestack/net/factory.py` -- seul lieu de création des clients, `trust_env=True`, contrôle `_check_and_trace`.
- `src/wavestack/mcp/connection.py` -- client MCP déjà branché sur `create_async_client`.
- `tests/conftest.py` -- neutralise le proxy du poste depuis le 2026-09-25 ; les tests de cette story doivent simuler le proxy eux-mêmes, en sous-processus comme `test_net_guard.py`.

## Verification

- `uv run pytest` avec et sans `HTTPS_PROXY=http://127.0.0.1:9000` : mêmes résultats.
- Sur le PC pro, `uv run wavestack` : diagnostic « Accès réseau disponible », `public_holidays` répond.
