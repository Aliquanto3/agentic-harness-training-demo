---
title: 'Correctif 1e : un proxy en boucle locale ne doit pas ouvrir la garde réseau'
type: 'bugfix'
created: '2026-09-25'
status: 'done'
route: ''
review_loop_iteration: 0
context: []
baseline_commit: '2269793edb480b92807883613809b1b421ec92cf'
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

## Déjà en place (relevé du 2026-10-01, `main` à `18c3978`)

- **Client de boucle locale sans proxy.** `create_loopback_client` (`net/factory.py` L126-141, story 18, `fc4c038`) passe `trust_env=False` : un `HTTP_PROXY` du poste ne reçoit plus les requêtes vers Ollama ou llama-server. Tous les adaptateurs de `models/servers.py` l'utilisent.
- **Suite de tests déterministe.** `tests/conftest.py` retire les variables `*_proxy` et neutralise `urllib.request.getproxies_registry` avant `install(allowed_hosts=[])`. `test_net_guard.py` (`_CHILD_PREAMBLE`, `_run_guarded`) et `test_compression.py` font de même dans leurs sous-processus.
- **Toutes les sorties légitimes passent par la fabrique.** `create_client` ou `create_async_client` dans `models/download.py`, `models/openai_chat.py` (Gemini, Groq, Mistral), `session/diagnostic.py`, `tools/network.py` (Wikipédia, calendrier) et `mcp/connection.py` (data.gouv.fr, Microsoft Learn). Seules exceptions dans `src/` : les deux `urllib.request.urlopen` de `cli.py` (L109, L152) vers `127.0.0.1`. Les bibliothèques tierces sont tenues hors ligne par leurs variables (`compression/env.py`, `HF_HUB_*` dans `cli.py`).
- **AD-15 dit déjà une partie du plafond.** « Derrière un proxy, la garde ne voit que le proxy, et le contrôle par destination reste à `net`. » AD-15 ne nomme ni le proxy en boucle locale, ni le client hors fabrique qui hérite du proxy. Le plafond « IP littérale ouverte par asyncio sous Proactor » y est déjà écrit.
- **Le lanceur E2E repose sur le proxy de l'environnement.** `tools/e2e/stack.py` (`_env`) coupe le réseau de WaveStack en lui donnant un proxy en boucle locale sur un port fermé. `tests/test_e2e_stack.py` applique ces variables **dans le processus de pytest**, après l'installation de la garde, et attend que `create_client()` les lise.
- **llama-server n'est pas un processus enfant.** WaveStack ne lance ni n'arrête Ollama ou llama-server (story 18) : leur environnement est celui de l'utilisateur. Les seuls enfants Python sont la sonde (`models/probe.py`, garde avec `allowed_hosts`) et le serveur MCP local en stdio (`mcp/local_server.py`, garde `install([])`). Aucun des deux n'a besoin du réseau.

## Approche recommandée : la garde confisque le proxy, la fabrique seule le reçoit (pistes 2 + 3)

**Principe.** Au moment où `install` pose la garde, avant tout import tiers, elle lit une fois le proxy du poste (`urllib.request.getproxies()` : variables d'environnement, ou registre Windows à défaut), le garde en mémoire, puis le retire du processus. Elle supprime de `os.environ` toutes les variables dont le nom se termine par `_proxy` (casse ignorée, comme `getproxies_environment`) et neutralise la lecture du système (`getproxies_registry` sous Windows, `getproxies_macosx_sysconf` sous macOS). La fabrique construit ses clients avec `trust_env=False` et des montages de proxy explicites, tirés de cette copie. Tout autre client (dépendance tierce, SDK MCP sans `http_client`, `urllib`, futur code) ne trouve plus de proxy. Il se connecte donc en direct, par un nom d'hôte, et passe par `getaddrinfo`, que la garde voit sur toutes les boucles, Proactor compris : un hôte hors liste est refusé. Un test statique (piste 3) empêche le code de `src/` de créer un client HTTP hors de la fabrique, et AD-15 est amendé.

**Pourquoi pas la piste 1 seule** (refuser le proxy au `connect` hors fabrique) :
- **Elle ne tient pas sous Proactor.** Un proxy donné par une IP littérale (`127.0.0.1:9000`) n'émet ni `getaddrinfo` ni `socket.connect` quand asyncio l'ouvre sous Proactor (plafond déjà écrit dans AD-15). Le cas du test `test_guard_blocks_the_real_mcp_client_under_proactor_event_loop` resterait donc ouvert.
- **Elle demande un jeton de fabrique fragile.** Il faudrait savoir, au `connect`, que la connexion vient de la fabrique : une variable de contexte devrait traverser le pool de connexions de httpcore et la tâche d'écriture du transport MCP, qui ne voit pas le contexte de l'appelant (`mcp/connection.py`).
- **Elle laisse les enfants ouverts.** Ils héritent des variables du parent et devraient porter la même logique.

**Pourquoi pas la piste 3 seule** (documenter, test statique) : elle couvre le code du dépôt, pas les dépendances ni le SDK MCP, alors qu'AD-15 promet un refus au niveau du processus. Elle reste utile en complément, pour le seul cas que la confiscation ne couvre pas : du code qui connaîtrait l'adresse du proxy.

**Grille d'évaluation (PC pro : proxy `127.0.0.1:9000`, PAC `localproxy-*.pac`, sans droits d'administrateur)**

| Critère | 1. Refus du proxy au `connect` | 2. Confiscation du proxy | 3. Doc + test statique | **2 + 3 (retenue)** |
|---|---|---|---|---|
| Seconde ligne de défense réelle | Partielle : trouée sous Proactor (IP littérale) | Oui pour tout client qui lit l'environnement, Proactor compris (refus à `getaddrinfo`) | Non à l'exécution ; code du dépôt seulement | Oui, plus le code du dépôt verrouillé |
| Risque pour les sorties légitimes (Gemini, Groq, Mistral, data.gouv.fr, Wikipédia, calendrier, Hugging Face) | Moyen : un faux refus coupe tout le réseau | Faible : toutes passent par la fabrique, qui reçoit le proxy explicitement ; reste à bien reproduire `NO_PROXY` | Nul | Faible |
| Sous-processus (sonde, serveur MCP stdio) | Héritent du proxy, à garder aussi | Héritent d'un environnement sans proxy, ce qui leur convient (aucun besoin réseau) | Inchangés | Sans proxy |
| Coût | Élevé (jeton de contexte, cas asynchrones) | Moyen : environ 30 lignes dans la garde, 35 dans la fabrique, tests E2E en processus à adapter | Faible | Moyen |
| Testabilité | Difficile (Proactor, pool) | Bonne : sous-processus avec un faux proxy en boucle locale qui note la ligne `CONNECT` | Bonne (AST) | Bonne |

**Plafond qui reste, à écrire dans AD-15 et en `ponytail:` dans la garde.** Du code qui vise explicitement l'adresse du proxy (en dur, ou en lisant la copie de la garde) passe toujours, car la boucle locale reste acceptée. Il en va de même du code natif qui lit lui-même les réglages système de Windows (WinHTTP, PAC). Le test statique couvre le premier cas pour `src/` ; le second figure déjà dans le plafond d'AD-15.

## Boundaries & Constraints (compléments, hors bloc gelé)

**Always:**
- La copie du proxy est prise **une seule fois**, à la première installation de la garde dans le processus. Un second appel à `install` ne l'écrase pas par un dictionnaire vide.
- La fabrique reproduit la règle de httpx 0.28 (`httpx._utils.get_environment_proxies`, sans l'importer, car l'API est privée) : schémas `http`, `https`, `all` ; URL sans schéma préfixée par `http://` ; `NO_PROXY` (`*` = aucun proxy, IPv4, IPv6, `localhost`, domaine et sous-domaines). En plus, la boucle locale (`127.0.0.1`, `localhost`, `[::1]`) ne passe jamais par le proxy.
- Aucun montage de proxy quand un `transport` est injecté (tests, `MockTransport`), comme httpx (`allow_env_proxies = trust_env and transport is None`).
- `_proxy_hosts()` lit la copie, pas l'environnement : derrière un proxy distant, l'hôte du proxy reste accepté pour la fabrique.
- L'URL du proxy, identifiants compris, n'entre ni dans le journal, ni dans les logs, ni dans `/api/*`, ni dans le diagnostic (AD-15 : ce que le transport ajoute sous le hook n'est pas tracé).

**Never:** pas d'analyse de fichier PAC (Python ne le fait pas aujourd'hui, et un PAC seul, sans variable ni `ProxyServer`, reste sans proxy comme avant) ; pas de changement de `create_loopback_client` ; pas de changement de `tools/e2e/stack.py`, qui continue de couper le réseau par les variables du processus lancé.

## I/O & Edge-Case Matrix (compléments)

Les lignes du bloc gelé valent toujours. Pour la ligne « Client hors fabrique », l'issue retenue est la piste 2 (refusé). Pour la ligne « Proxy distant », « comportement actuel inchangé » est lu comme « la fabrique sort toujours par ce proxy » (voir la question 2).

| Scenario | Input / State | Expected Output / Behavior | Error Handling |
|----------|--------------|---------------------------|----------------|
| Confiscation | `HTTPS_PROXY=http://127.0.0.1:9000` et `https_proxy` posés, puis `install([...])` | `os.environ` sans aucune variable `*_proxy` ; `getproxies()` rend `{}` ; la copie de la garde vaut `{"https": "http://127.0.0.1:9000"}` | N/A |
| Fabrique, hôte autorisé, faux proxy en boucle locale | Faux proxy sur `127.0.0.1:<port>`, `create_client().get("https://fr.wikipedia.org/…")` | `outbound_request` émis, puis le faux proxy reçoit `CONNECT fr.wikipedia.org:443 HTTP/1.1` | `httpx.ProxyError` (le faux proxy répond 502) |
| Fabrique asynchrone, même proxy | `create_async_client(...)` vers un hôte autorisé | Même ligne `CONNECT` reçue | Idem |
| Fabrique, hôte refusé | Même proxy, `https://example.com` | `NetworkBlocked` ; le faux proxy ne reçoit rien ; rien n'est tracé | Appelant |
| `httpx.Client()` hors fabrique, hôte refusé | Même proxy, `https://example.com` | `NetworkBlocked` à `getaddrinfo` ; le faux proxy ne reçoit rien | Appelant |
| `httpx.Client()` hors fabrique, hôte autorisé | Même proxy, `https://huggingface.co` | Connexion directe vers l'IP résolue, pas vers le proxy ; non tracée (plafond, couvert par le test statique pour `src/`) | Échec réseau ordinaire sur le PC pro |
| `urllib.request.urlopen` hors fabrique | Même proxy, `https://example.com` | `NetworkBlocked` ; le faux proxy ne reçoit rien | Appelant |
| SDK MCP sans `http_client`, Proactor, proxy posé avant `install` | Sous-processus, `Client("https://blocked.example.test/mcp")` | `find_blocked` trouve `NetworkBlocked` ; le faux proxy ne reçoit rien | Appelant |
| Processus enfant | Parent installé avec proxy, puis `subprocess.run([sys.executable, …])` | L'enfant ne voit aucune variable `*_proxy` ; sa copie est vide | N/A |
| Proxy distant | `HTTPS_PROXY=http://proxy.corp.test:8080` (résolveur simulé) | La fabrique passe par lui, et `getaddrinfo("proxy.corp.test")` est accepté (copie) ; un client hors fabrique sort en direct, donc refusé hors liste | Appelant |
| `NO_PROXY` | `NO_PROXY=intranet.example` ; puis `NO_PROXY=*` | Hôte listé : montage sans proxy ; `*` : aucun proxy | N/A |
| Boucle locale par la fabrique | Proxy posé, sans `NO_PROXY`, `create_client().get("http://127.0.0.1:<port>/")` | Atteinte en direct, non tracée | N/A |
| Proxy sans schéma | `HTTPS_PROXY=127.0.0.1:9000` | Traité comme `http://127.0.0.1:9000` | N/A |
| Proxy du registre Windows | Aucune variable, `getproxies_registry` simulé rendant `{"https": "127.0.0.1:9000"}` | Copié dans la garde, puis la lecture du registre rend `{}` | N/A |
| PAC seul | `AutoConfigURL` sans `ProxyServer` ni variable | Aucun proxy, comme aujourd'hui | Échec réseau ordinaire |
| Identifiants dans l'URL | `HTTPS_PROXY=http://user:secret@127.0.0.1:9000` | Transmis au transport ; `secret` absent du journal et des logs | N/A |
| Transport injecté | `create_client(transport=MockTransport(...))` avec une copie non vide | Aucun montage de proxy, le `MockTransport` répond | N/A |
| Second `install` | `install` appelé deux fois dans un processus | La première copie est conservée | N/A |
| Proxy SOCKS | `ALL_PROXY=socks5://127.0.0.1:1080` | Comportement actuel de httpx (erreur sans `socksio`), hors périmètre | Appelant |
| Test statique | Un module de `src/` hors `net/factory.py` appelle `httpx.Client(`, `httpx.AsyncClient(`, `httpx2.AsyncClient(`, `httpx2.Client(`, `urllib.request.urlopen(`, `urllib.request.build_opener(`, `http.client.HTTPConnection(` ou `HTTPSConnection(`, ou `streamable_http_client(` sans `http_client=` | Le test échoue en nommant `fichier:ligne` ; seules les exemptions listées, avec leur raison, passent | N/A |

## Code Map

- `src/wavestack/net/guard.py` -- `install` (L89) : copier `getproxies()` dans `_proxies` au premier appel, puis supprimer de `os.environ` toute variable dont le nom se termine par `_proxy` et remplacer `urllib.request.getproxies_registry` (et `getproxies_macosx_sysconf` s'il existe) par `lambda: {}`. L'ordre compte : la copie d'abord, sinon le registre serait relu. `httpx` et `httpx2` importent `getproxies` par nom (`from urllib.request import getproxies`), mais cette fonction relit `getproxies_environment` et `getproxies_registry` à chaque appel : il suffit de vider l'environnement et de remplacer ces deux attributs. Nouvelle fonction publique `office_proxies() -> dict[str, str]` (copie). `_proxy_hosts()` (L56) lit `_proxies`. Mettre à jour la docstring du module et ajouter un commentaire `ponytail:` sur le plafond.
- `src/wavestack/net/factory.py` -- `create_client` (L100) et `create_async_client` (L144) : `trust_env=False` et `mounts=_proxy_mounts(...)` quand `transport is None`. `_proxy_mounts` construit `httpx.HTTPTransport(proxy=url, verify=ctx)` ou `httpx2.AsyncHTTPTransport(proxy=url, verify=ctx)` par schéma (`"http://"`, `"https://"`, `"all://"`), `None` pour les motifs de `NO_PROXY` et pour la boucle locale. Les deux API exposent `proxy=` et `mounts=` (httpx 0.28.1, httpx2 2.13.1). Docstring : « proxy du poste, confisqué par la garde ».
- `src/wavestack/cli.py` -- aucun changement attendu : `_install_guard` (L27) précède déjà tout import tiers et toute lecture du proxy. Les deux `urlopen` vers `127.0.0.1` (L109, L152) ne trouveront plus de proxy, ce qui corrige au passage un défaut latent : avec `HTTP_PROXY` sans `NO_PROXY`, ces sondes partaient vers le proxy.
- `src/wavestack/models/probe.py` (L404-407), `src/wavestack/mcp/local_server.py` (L10-12) -- aucun changement : la garde y fait la même confiscation, sur un environnement déjà vide.
- `tests/conftest.py` -- garder le retrait des variables et du registre **avant** `install` : la copie de la session de test doit être vide, quel que soit le proxy du poste de développement. Mettre à jour la docstring : la story 1e est couverte par des tests dédiés.
- `tests/test_net_guard.py` -- lignes « Confiscation », « hors fabrique » (`httpx`, `urllib`), « SDK MCP sous Proactor », « Processus enfant », « Proxy distant », « Proxy du registre », « Second `install` », en sous-processus (`_run_guarded` avec `HTTPS_PROXY` dans `extra_env`). Le faux proxy est un `socketserver.ThreadingTCPServer` sur `127.0.0.1:0`, démarré dans l'enfant, qui note la première ligne et répond 502, comme `_RecordingProxy` dans `tests/test_e2e_stack.py`.
- `tests/test_net_factory.py` -- lignes « Fabrique » (synchrone et asynchrone), `NO_PROXY`, boucle locale, proxy sans schéma, identifiants absents du journal, transport injecté : en processus, en posant la copie par `monkeypatch.setattr(guard, "_proxies", {...})` et un faux proxy en boucle locale.
- `tests/test_e2e_stack.py` -- `_apply_proxies` pose aussi la copie de la garde, tirée des variables appliquées (`urllib.request.getproxies_environment()` après les `setenv`). Sans cela, `test_public_host_is_traced_then_fails_through_the_closed_proxy`, `test_public_host_goes_through_the_launcher_proxy` et `test_loopback_is_reached_directly_and_not_traced` ne voient plus le proxy, car la fabrique ne lit plus l'environnement.
- `tests/test_net_single_factory.py` (nouveau) -- test statique par `ast` sur `src/wavestack/**/*.py` hors `net/factory.py`. Exemptions nommées avec leur raison : `cli.py` `_existing_instance_health` et `_existing_instance_ready` (boucle locale, `urllib` avant tout client ; voir la question 3).
- `_bmad-output/planning-artifacts/architecture/architecture-agentic-harness-training-demo-2026-09-23/ARCHITECTURE-SPINE.md` -- AD-15, puce « Garde réseau » : ajouter la confiscation du proxy (copie, retrait de l'environnement et du registre, fabrique seule détentrice). Remplacer « le proxy de l'environnement » par « le proxy du poste, confisqué par la garde » dans la configuration commune de la fabrique. Ajouter au plafond le code qui vise explicitement l'adresse du proxy. Ajouter à « Garde en test » le test statique de la fabrique unique.

## Tasks & Acceptance

**Execution:**
- [x] `src/wavestack/net/guard.py` -- copie unique du proxy, confiscation (environnement, registre, macOS), `office_proxies()`, `_proxy_hosts()` sur la copie, `ponytail:` -- AD-15
- [x] `src/wavestack/net/factory.py` -- `_proxy_mounts` (règle httpx, plus la boucle locale en direct), `trust_env=False` sur les deux clients publics, aucun montage avec un transport injecté -- AD-15
- [x] `tests/test_net_guard.py` -- lignes de la matrice côté garde, en sous-processus, faux proxy en boucle locale, aucun accès réseau
- [x] `tests/test_net_factory.py` -- lignes de la matrice côté fabrique
- [x] `tests/test_e2e_stack.py` -- `_apply_proxies` pose la copie de la garde
- [x] `tests/test_net_single_factory.py` -- test statique, exemptions nommées
- [x] `tests/conftest.py` -- docstring
- [x] `ARCHITECTURE-SPINE.md` -- AD-15 amendé (confiscation, plafond, test statique)

**Acceptance Criteria:**
- Given `HTTPS_PROXY=http://127.0.0.1:9000` posé avant le lancement, when la garde est installée, then aucune variable `*_proxy` ne reste dans `os.environ`, `urllib.request.getproxies()` rend `{}`, et la fabrique connaît le proxy.
- Given ce proxy, when la fabrique envoie une requête vers un hôte autorisé, then elle passe par le proxy (ligne `CONNECT hôte:443` reçue par le faux proxy) après avoir émis `outbound_request`.
- Given ce proxy, when un client créé hors de la fabrique (`httpx.Client()`, `urllib`, SDK MCP sans `http_client`, Proactor compris) vise un hôte hors liste, then `NetworkBlocked` est levée et le proxy ne reçoit rien.
- Given les tests du dépôt, when `uv run pytest` tourne avec puis sans `HTTPS_PROXY=http://127.0.0.1:9000`, then les résultats sont identiques. Avec l'ancien `guard.py` et l'ancien `factory.py`, les nouveaux tests « hors fabrique » et « SDK MCP sous Proactor » échouent.
- Given un module de `src/` qui crée un client HTTP hors de la fabrique, when `pytest` tourne, then le test statique échoue en nommant le fichier et la ligne.
- Given le PC pro, when `uv run wavestack` démarre, then le diagnostic affiche « Accès réseau disponible », et les sorties légitimes répondent (vérification manuelle).

## Décisions à prendre par Anaël

**Tranchées le 2026-10-01 : Anaël suit les quatre recommandations.** 1 = pistes 2 + 3 ; 2 = oui, le proxy distant est confisqué aussi ; 3 = A, exemption nommée ; 4 = non, pas de ligne au diagnostic dans cette story.

1. **Approche : confiscation du proxy et test statique (pistes 2 + 3), avec AD-15 amendé, plutôt que la documentation seule (piste 3) ?** Recommandation : **oui**. C'est la seule option qui rend une seconde ligne de défense réelle, y compris sous Proactor et pour le SDK MCP, pour un coût moyen.
2. **Confisquer aussi un proxy distant (`proxy.corp.test:8080`), et lire la ligne gelée « Proxy distant : comportement actuel inchangé » comme « la fabrique sort toujours par lui » ?** Recommandation : **oui**. La faille est la même : un client hors fabrique ouvre un tunnel `CONNECT` vers un hôte de proxy accepté. Une règle unique est aussi plus simple à expliquer en formation. Si la réponse est non, la confiscation se limite aux proxys en boucle locale, et la ligne gelée garde son sens littéral.
3. **Les deux `urlopen` de `cli.py` vers `127.0.0.1` : (A) exemption nommée dans le test statique, ou (B) passage à `create_loopback_client` ?** Recommandation : **A**. Ils ne visent que la boucle locale et ne trouveront plus de proxy après la confiscation. B touche le démarrage pour un gain nul en sécurité.
4. **Montrer la confiscation dans l'interface (une ligne du diagnostic : « Proxy du poste : réservé aux requêtes tracées ») dans cette story ?** Recommandation : **non**. C'est un correctif de sécurité. La ligne pédagogique ferait une petite story à part (textes en, de, fr, journal), sans jamais afficher l'URL ni les identifiants.

## Review Triage Log

Revue du 2026-10-01 (couches Blind Hunter, Edge Case Hunter, Verification Gap).

| # | Source | Constat | Verdict | Preuve | Route |
|---|---|---|---|---|---|
| 1 | Edge | `NO_PROXY` avec un CIDR IPv6 (`fe80::/10`) : `all://[fe80::/10]` lève `InvalidURL`, toute requête de la fabrique échoue | medium | Vérifié : httpx et httpx2 refusent `all://[fe80::/10]`, acceptent `all://[fe80::]/10` | patch |
| 2 | Blind, Edge | Le test statique laisse passer `streamable_http_client(..., http_client=None)`, et le test du chercheur l'entérine | medium | `visit_Call` ne regarde que la présence du mot-clé ; `None` fait créer son client au SDK | patch |
| 3 | Blind, Edge, VG | Le test statique ignore `mcp.Client(url)`, `urlretrieve`, `sse_client`, `requests`, `urllib3`, `aiohttp` | medium | Critère d'acceptation : un client hors fabrique dans `src/` doit faire échouer le test ; `mcp.Client` avec une URL ouvre son propre client (`test_net_guard.py`) | patch |
| 4 | Blind | Exemptions indexées par (fichier, fonction) : tout nouvel appel interdit dans ces fonctions passe | low | Correction directe : ajouter le nom qualifié à la clé | patch |
| 5 | Blind | Rien n'empêche un module de `src/` de lire `office_proxies()` ou `guard._proxies` hors de `net/` ; AD-15 dit le contraire | low | Grep : seule la fabrique les lit aujourd'hui ; règle statique simple | patch |
| 6 | Blind, Edge | `conftest.py`, les préambules de `test_net_guard.py` et `test_compression.py` n'aveuglent pas `getproxies_macosx_sysconf` ; `test_compression.py:911` filtre encore par la liste fixe de quatre noms | low | Correction directe, une ligne chacune | patch |
| 7 | Blind, Edge | Sous Windows, un enfant (sonde, serveur MCP local) relit le proxy du registre à son `install` ; docstring et AD-15 disent « aucun proxy hérité » | low | Les enfants n'ont pas besoin du réseau et leurs clients hors fabrique restent aveuglés : seule la formulation est fausse | patch (formulation) |
| 8 | Blind | `ProxyOverride` du registre jamais copié en `no` | false | Avant la story, `getproxies_registry()` ne rendait pas non plus de `no`, et httpx l'ignorait : comportement inchangé | rejet |
| 9 | Blind, Edge | Motifs de boucle locale plus étroits que `is_loopback` (`127.0.0.2` part au proxy) | low | Réel, mais aucune configuration ne vise autre chose que `127.0.0.1` ; le correctif demande un transport enveloppant | rejet |
| 10 | Blind | Le banc rouvre le trou de 1e et son commentaire dit à tort que la garde vérifie l'hôte du proxy | low | Avec un proxy en boucle locale, la garde ne voit que `127.0.0.1` ; correction du commentaire et une phrase dans AD-15 | patch |
| 11 | Blind | `_apply_proxies` laisse les variables de proxy dans le processus de pytest ; docstring fausse | low | Correction directe : copie tirée des variables, puis retrait | patch |
| 12 | Blind | Tests absents : client asynchrone vers la boucle locale, identifiants absents du journal quand le proxy est injoignable | low | Deux tests courts | patch |
| 13 | Blind | Autres tests absents (`[::1]`, `http://` en clair par le proxy, `/api/*`, trace du proxy distant) | low | Aucun chemin ne met l'URL du proxy dans `/api/*` ; correctif = tests supplémentaires sans défaut démontré | rejet |
| 14 | Blind | Le fichier de story manque au diff | false | Exclu volontairement : la spec va à la seule couche Edge | rejet |
| 15 | Edge | Sans `install`, la fabrique ne trouve plus le proxy | false | Tout processus qui utilise la fabrique installe la garde (`cli`, sonde, serveur MCP local) ; `tools/` n'utilise pas la fabrique | rejet |
| 16 | VG | Le saut de `no` dans `_proxy_hosts()` n'est pas testé | gap | Supprimer le `continue` ne fait échouer aucun test | patch |
| 17 | VG | La remise du proxy dans l'environnement du banc n'est pas testée | gap | `_record_and_guard` est toujours remplacé par un bouchon dans `test_story12_bench.py` | patch |
| 18 | VG | `test_the_test_session_holds_no_proxy` passe trivialement sur un poste sans proxy | gap | Il faudrait un pytest imbriqué ; la garantie tient sur le PC pro | defer |

## Spec Change Log

- 2026-10-01 -- Spec complétée hors du bloc gelé : relevé de l'existant, approche recommandée (pistes 2 + 3), compléments de contraintes et de matrice, Code Map, tâches, vérification et quatre décisions à prendre. Statut laissé à `draft` en attendant les réponses d'Anaël.
- 2026-10-01 -- Décisions 1 à 4 tranchées par Anaël (recommandations suivies). Statut passé à `ready-for-dev`.
- 2026-10-01 -- Implémentation : en plus de la Code Map, `tools/bench/story12_bench.py` remet la copie du proxy dans l'environnement du banc quand `strip_proxy` est faux (le banc télécharge par `huggingface_hub` et `fastembed`, hors fabrique). `tests/conftest.py` retire le proxy dès son chargement, car l'import de `wavestack.cli` à la collecte installe la garde avant la fixture de session.
- 2026-10-01 -- Revue triée (18 constats : 12 corrigés, 5 rejetés, 1 reporté dans `deferred-work.md`). Vérification : `ruff` propre ; pytest en quarts avec `HTTPS_PROXY=http://127.0.0.1:9000` : 3569 + 682 + 314 + 327 passés, un échec étranger (`test_rag_lab::test_nothing_is_written_under_the_repository`, écritures d'un autre agent dans `.claude/worktrees/`). Statut `done` ; les vérifications manuelles sur le PC pro restent à faire par Anaël.
- 2026-10-02 -- confirmé par Anaël : `tools/bench/story12_bench.py` remet le proxy du poste dans l'environnement du banc, qui télécharge hors fabrique.

## Verification

**Commands:**
- `uv run ruff check .` et `uv run ruff format --check .` -- expected: aucune erreur
- `uv run pytest` -- expected: tous les tests passent (tests `model` exclus)
- PowerShell : `$env:HTTPS_PROXY = "http://127.0.0.1:9000"; uv run pytest; Remove-Item Env:HTTPS_PROXY` -- expected: mêmes résultats que sans la variable
- Preuve de non-régression : les nouveaux tests « hors fabrique » et « SDK MCP sous Proactor » échouent sur `guard.py` et `factory.py` de `18c3978`

**Manual checks (PC pro, proxy en boucle locale, sans droits d'administrateur):**
- `uv run wavestack` : le diagnostic affiche « Accès réseau disponible ».
- Outils réseau : `public_holidays` (calendrier) et un article de Wikipédia répondent ; le bloc des données sortantes apparaît.
- MCP public : data.gouv.fr se connecte et liste ses outils.
- Modèles cloud : le test de clé de Gemini, Groq et Mistral répond (au moins un, selon les clés disponibles).
- Téléchargement d'un modèle depuis Hugging Face : la progression démarre.
- Démarrer une seconde fois `uv run wavestack` pendant que la première tourne : le message « déjà lancée » s'affiche (sondes `urlopen` vers `127.0.0.1`).
