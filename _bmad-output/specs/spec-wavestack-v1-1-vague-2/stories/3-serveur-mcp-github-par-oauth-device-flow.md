---
title: 'Story 3 : serveur MCP GitHub par OAuth device flow'
type: 'feature'
created: '2026-10-16'
status: 'review'
route: 'dispatch'
review_loop_iteration: 1
baseline_commit: '1a7b015'
context:
  - '{project-root}/_bmad-output/specs/spec-wavestack-v1-1-vague-2/SPEC.md'
  - '{project-root}/_bmad-output/specs/spec-wavestack-v1-1-vague-2/mcp-tools.md'
  - '{project-root}/_bmad-output/specs/spec-wavestack-v1-1-vague-2/ux/DESIGN.md'
  - '{project-root}/_bmad-output/specs/spec-wavestack-v1-1-vague-2/ux/EXPERIENCE.md'
  - '{project-root}/_bmad-output/specs/spec-wavestack-v1-1-vague-2/stories/1-politique-dautorisation-par-outil-mcp-et-journal-de-securite.md'
  - '{project-root}/_bmad-output/specs/spec-wavestack-v1-1-vague-2/stories/2-outils-concrets-du-mcp-local.md'
---

<frozen-after-approval reason="human-owned intent — do not modify unless human renegotiates">

## Intent

**Problem:** CAP-4. L'atelier MCP n'a que trois serveurs (local, data.gouv.fr, Microsoft
Learn), tous sans authentification. Aucun moyen de montrer à un RSSI ce qu'un serveur MCP
distant avec de vrais droits (GitHub) expose, ni les trois niveaux de refus d'une écriture.

**Approach:**
- `wavestack.mcp.github_auth.GithubAuth` (nouveau) : device flow de l'OAuth App WaveStack
  (Client ID public `Ov23li3Ovj8ZnyXMFUPQ`, portée `read:user`, validée par le test réel du
  16/10) — `start()` (device/code), `poll()` (sondage borné par l'intervalle de GitHub),
  `access_token()` (renouvellement par `refresh_token` sans client secret), `headers()`
  (`Authorization: Bearer …` + `X-MCP-Toolsets: secret_protection,dependabot,code_security`,
  sans `X-MCP-Readonly` — la politique WaveStack est le premier niveau de refus démontré),
  `state()` (jamais le jeton). Jeton en mémoire, persistant dans
  `config.data_dir()/github_token.json` (hors dépôt) pour survivre à un redémarrage (flux 4).
- `wavestack.mcp.servers.McpServer` gagne un champ `headers` ; `mcp_servers()` ajoute
  `"github"` (4ᵉ serveur de l'atelier MCP), jamais une sous-option de la brique Harnais
  (`AppSession._mcp_options` l'exclut explicitement : son propre bloc OAuth vit sur la page
  MCP, pas dans le panneau des briques, qui reste un fichier statique — `bricks/registry.py`
  n'est pas touché).
- `AppSession` : `github_connect()`/`github_disconnect()`/`_github_state()` (exposé dans
  `mcp_lab_state()["github"]`) ; `_mcp_connect` et `_run_mcp_lab_connect` résolvent un jeton
  frais juste avant de tenter la connexion (`_github.headers()`) — sans jeton, l'appel
  n'est même pas tenté (état d'erreur propre, jamais un 401 réel).
- `wavestack.mcp.policy` : entrées par défaut de `mcp-tools.md` pour les 6 outils GitHub
  nommés (lecture : moyen/autoriser ; écriture : élevé/refuser) ; un outil GitHub non nommé
  (parmi les 46 exposés) prend par défaut élevé/refusé (écriture présumée), au lieu du repli
  faible/autoriser des autres serveurs.
- `wavestack.net.factory` : un paramètre `headers` sur `create_async_client` (le jeton
  GitHub comme en-tête par défaut de la connexion) ; masquage des champs de corps sensibles
  (`refresh_token`, `access_token`, `client_secret`, `device_code`) avant qu'ils n'atteignent
  le journal réseau (`outbound_request`), pour les requêtes du device flow (en-têtes
  form-urlencoded, jamais un en-tête HTTP ordinaire).
- `wavestack.toml` : `github.com` et `api.githubcopilot.com` ajoutés à `[net] allowed_hosts`.
- Front (`mcp.html`/`mcp.js`/`mcp.css`) : bloc GitHub (état, code à saisir, connexion,
  déconnexion), visible seulement quand « GitHub » est le serveur choisi ; le bouton « Se
  connecter » générique de l'atelier reste désactivé tant qu'aucun jeton n'existe. Le
  risque/règle par outil réutilise le sélecteur déjà posé par la story 1 (`renderToolPolicy`) :
  aucun code neuf, les outils GitHub y apparaissent comme n'importe quel outil listé.

**Décisions (prises par Claude, sans effet sur le contrat) :**
- Portée OAuth : `read:user` seule, confirmée par le test réel du 16/10 (46 outils listés,
  alertes comprises, sur ce Client ID). Aucune portée plus large demandée.
- Renouvellement sans client secret : GitHub accepte `grant_type=refresh_token` avec le seul
  `client_id` pour une OAuth App publique en device flow ; testé ici avec un faux serveur.
- Outil GitHub inconnu de la table : refusé par défaut (écriture présumée), à la différence
  du repli habituel de `ToolPolicy` (faible/autoriser) — un serveur distant peut ajouter des
  outils sans que WaveStack les ait vus.
- GitHub n'est jamais une sous-option de la brique Harnais : seule l'Atelier MCP le propose,
  avec son propre bloc OAuth ; `_mcp_options()` l'exclut par son id, un seul endroit touché.
- Jeton stocké en clair dans un fichier JSON du dossier de données (pas de chiffrement) :
  cohérent avec le reste du poste (pas de secret-store sur ce profil), documenté comme limite
  dans le code ; la story ne demande pas de chiffrement.

## Boundaries & Constraints

**Always:**
- Le jeton (accès, renouvellement) n'apparaît jamais dans le journal de sécurité, la
  Séquence ou les traces réseau ; seul le fichier local hors dépôt le porte.
- Une tentative de connexion GitHub sans jeton n'émet aucune requête réseau.
- Libellés en fr, en, de.
- Tests sans aucun appel réseau réel (faux serveur MCP, faux GitHub).

**Never:** toucher `src/wavestack/guardrails/` (lane B), le panneau des briques
(`bricks/registry.py`), ni `web/static/app.js` (lane C). GitHub n'apparaît jamais comme
sous-option de la brique Harnais.

## Code Map

- `src/wavestack/mcp/github_auth.py` (nouveau) -- `GithubAuth`, `GithubToken` : device flow,
  renouvellement, stockage, `headers()`, `state()`.
- `src/wavestack/mcp/servers.py` -- `McpServer.headers` ; `mcp_servers()` + `"github"`.
- `src/wavestack/mcp/policy.py` -- 6 entrées GitHub, repli dédié `github__*` (élevé/refuser).
- `src/wavestack/mcp/connection.py`, `src/wavestack/mcp/lab.py` -- `_transport` passe
  `headers=self.server.headers` à `create_async_client`.
- `src/wavestack/net/factory.py` -- `create_async_client(..., headers=...)` ; masquage des
  champs de corps sensibles (`_masked_body`).
- `src/wavestack/session/app_session.py` -- `self._github` ; `github_connect`,
  `github_disconnect`, `_github_state` ; `_resolve`-like branche dans `_mcp_connect` et
  `_run_mcp_lab_connect` (jeton requis avant toute tentative) ; `_mcp_options` exclut
  `"github"` ; `mcp_lab_state()["github"]`.
- `src/wavestack/web/app.py` -- `POST /api/intentions/github_connect`,
  `POST /api/intentions/github_disconnect`.
- `wavestack.toml` -- `github.com`, `api.githubcopilot.com` dans `[net] allowed_hosts`.
- `content/messages.yaml`, `content/mcp.yaml`, `content/ui.yaml` (+ i18n en/de) -- textes du
  bloc GitHub et des messages de refus.
- `src/wavestack/web/static/mcp.html`/`mcp.js`/`mcp.css` -- bloc GitHub (état, code,
  connexion/déconnexion), visible pour le serveur « github » choisi.
- `tests/test_mcp_github_auth.py` (nouveau) -- device flow, renouvellement, stockage, aucun
  secret tracé.
- `tests/test_mcp_github.py` (nouveau) -- connexion avec jeton (faux serveur), en-tête
  Authorization jamais en clair dans le journal, outil de lecture autorisé, outil d'écriture
  refusé par la politique (jamais envoyé), outil inconnu refusé par défaut, aucune tentative
  sans jeton.
- `tests/test_mcp_policy.py`, `tests/test_mcp_policy_http.py` -- défauts GitHub, routes HTTP
  du device flow.

## Tasks & Acceptance

**Execution:**
- [x] `github_auth.py` et son test unitaire (device flow, sondage, renouvellement, stockage).
- [x] `servers.py`, `policy.py` : 4ᵉ serveur, défauts GitHub, repli dédié.
- [x] `connection.py`, `lab.py`, `net/factory.py` : en-têtes par connexion, masquage du corps.
- [x] `app_session.py` : état GitHub, résolution du jeton avant connexion, exclusion de la
      brique Harnais.
- [x] `app.py` : deux routes.
- [x] `wavestack.toml` : liste blanche réseau.
- [x] Textes fr/en/de.
- [x] `mcp.html`/`mcp.js`/`mcp.css` : bloc GitHub.
- [ ] Essai réel avec Anaël (device flow GitHub, réseau réel, derrière le proxy).
- [ ] E2E `mcp_lab_page`, `mcp_lab` (non lancés par le développeur, consigne de
      l'orchestrateur).

**Acceptance Criteria:**
- Given aucun jeton GitHub, when on choisit le serveur GitHub dans l'atelier MCP et qu'on
  clique « Se connecter », then le bouton générique de connexion reste désactivé, le bloc
  GitHub propose « Se connecter à GitHub », et aucune requête réseau ne part.
- Given le bloc GitHub, when on clique « Se connecter à GitHub », then un code et une adresse
  s'affichent (`github.com/login/device`), sans jeton journalisé.
- Given un jeton obtenu (faux serveur dans les tests), when on se connecte au serveur
  GitHub, then la connexion porte `Authorization: Bearer …` et `X-MCP-Toolsets`, jamais en
  clair dans le journal réseau.
- Given la règle par défaut d'un outil de lecture (`list_secret_scanning_alerts`…), when on
  l'appelle, then il est exécuté et journalisé `allow`.
- Given la règle par défaut d'un outil d'écriture (`merge_pull_request`, `create_pull_request`)
  ou d'un outil GitHub non nommé par `mcp-tools.md`, when on l'appelle, then il est refusé par
  la politique WaveStack avant tout envoi à GitHub, et journalisé `deny`.
- Given un jeton expiré avec son renouvellement encore valable, when une connexion est
  tentée, then `access_token()` le renouvelle sans client secret, sans jamais écrire le
  jeton (ancien ou nouveau) dans le journal.

## Implementation Notes

- GitHub n'est jamais une sous-option de la brique Harnais : `bricks/registry.py` déclare la
  liste des serveurs MCP de la brique de façon statique (`local`, `datagouv`, `mslearn`), donc
  l'ajout de `"github"` à `mcp_servers()` ne crée pas de bascule dans le panneau des briques ;
  seul `AppSession._mcp_options()` (qui, lui, parcourt `self._mcp_servers`) a dû exclure
  `"github"` explicitement par son id.
- L'atelier MCP (lab.py) tient son propre registre d'outils, jamais celui de la conversation
  (`_mcp_lab_registry`, « nothing ever enters the brick's registry ») : les outils GitHub
  appelés « par le modèle » dans l'atelier ne polluent jamais le catalogue d'outils de la
  brique Harnais.
- Un secret dans le corps d'une requête (le `refresh_token` du renouvellement) est aussi
  sensible qu'un en-tête : `net/factory.py` masque maintenant les champs de corps nommés
  `refresh_token`, `access_token`, `client_secret`, `device_code` d'un corps
  form-urlencodé, avant `emit`, comme les en-têtes hors `PUBLIC_HEADERS`.
- Les trois niveaux de refus de `mcp-tools.md` sont couverts par construction : la politique
  WaveStack (démontrée ici, sans `X-MCP-Readonly`), lecture seule côté GitHub (un jeton réel
  en lecture seule ferait disparaître l'outil) et 403 GitHub (un compte réel sans droit) — les
  deux derniers s'observent seulement avec un vrai compte, à l'essai réel.
- shortcut: le jeton est stocké en clair (JSON) dans `config.data_dir()`, jamais chiffré ;
  à revoir si WaveStack doit un jour protéger ce fichier (permissions NTFS, DPAPI) au-delà de
  « hors dépôt, hors journal ».
- Testé : `uv run pytest -q --tb=short tests/test_mcp_github_auth.py tests/test_mcp_github.py`
  (15 tests, neufs) ; `tests/test_mcp_policy.py tests/test_mcp_policy_http.py` (14 tests,
  étendus) ; suite existante `tests/test_mcp.py tests/test_mcp_lab.py tests/test_mcp_lab_policy.py
  tests/test_mcp_lazy.py tests/test_mcp_policy_http.py tests/test_mcp_snapshot.py
  tests/test_net_factory.py` pour vérifier l'absence de régression — tous verts.

## Spec Change Log

## Review Triage Log

(pas encore de relecture)

## Verification

**Commands:**
- `uv run pytest -q --tb=short tests/test_mcp_github_auth.py tests/test_mcp_github.py` -- 15
  passés.
- `uv run pytest -q --tb=short tests/test_mcp_policy.py tests/test_mcp_policy_http.py` -- 14
  passés.
- `uv run pytest -q --tb=short tests/test_mcp.py tests/test_mcp_lab.py tests/test_mcp_lab_policy.py tests/test_mcp_lazy.py tests/test_mcp_snapshot.py tests/test_net_factory.py` --
  verts (pas de régression).
- `python .claude/cost-kit/controle_rapide.py` -- vert.
- E2E (non lancé par le développeur, consigne de l'orchestrateur) :
  `uv run --with playwright==1.56.0 python tools/e2e/run_e2e.py --channel msedge --only mcp_lab_page,mcp_lab`.

## Revue

Relecture du 16/10 (Opus), après rebase sur `origin/main` (277567b, sans conflit).

- MEDIUM · second avis 1 · corrigé · `poll`/`_refresh` : une page 200 non JSON (proxy Zscaler, portail captif) levait `JSONDecodeError` et cassait `GET /api/mcp_lab` en 500 ; `GithubAuth._post` lève `ValueError`, attrapée (sondage : on attend le suivant ; renouvellement : erreur réseau). Tests `test_a_proxy_page_*`.
- MEDIUM · second avis 2 · corrigé · `start` : même cas, et champ manquant (`KeyError`) ; `github_connect` rend un 409 « réseau » au lieu d'un 500.
- MEDIUM · second avis 3 · corrigé · flux 4 : renouvellement refusé ou expiré → état `expired` (« Se reconnecter »), plus `disconnected` ; « Se déconnecter » revient à « non connecté ». Une panne réseau garde le jeton (6 mois) et réessaie toutes les 30 s (état « erreur réseau »).
- MEDIUM · second avis 4 · corrigé · `GET /api/mcp_lab` renouvelle un jeton d'accès expiré avant de lire l'état (plus de « expire dans 0 s »).
- MEDIUM · second avis 5 · corrigé · le bearer était figé à la création du client httpx : `McpServer.auth` (un `httpx2.Auth`, `GithubAuth.bearer`) le pose à chaque requête, renouvelé hors de la boucle (`asyncio.to_thread`). Test de bout en bout : connexion ouverte, 8 h plus tard, l'appel part avec le jeton renouvelé.
- MEDIUM · relecture · corrigé · flux 4 : un appel d'outil GitHub sur une connexion restée ouverte sans jeton valable partait avec l'ancien jeton (401 obscur) ; il est refusé avant l'envoi avec « Envoyé à GitHub : non » (`session.mcp_lab.github_expired_call`), la connexion se ferme.
- MEDIUM · relecture · corrigé · `renderGithub` réactivait le bouton générique « Se connecter » à chaque rendu hors GitHub, effaçant l'état occupé posé par `renderControls` ; la condition GitHub vit maintenant dans `renderControls`.
- MEDIUM · relecture · corrigé · E2E `mcp_lab_page` attendait trois serveurs ; `run_e2e.py` attend maintenant les quatre (GitHub compris).
- LOW · second avis · corrigé · clés `mcp.github.error.{access_denied,expired_token,network}` ajoutées (fr, en, de) ; un code inconnu garde le texte générique (`has()`). Un échec de « Se connecter à GitHub » affiche le détail du 409.
- LOW · second avis · corrigé · `_masked_body` ré-encode le corps masqué : docstring du module corrigée (« corps, champs sensibles masqués »), test du masquage rendu strict.
- LOW · second avis · corrigé · écriture atomique de `github_token.json` (`os.replace`) ; `OSError` toujours avalé (le jeton reste en mémoire, choix conservé) ; limite « jeton stocké en clair » ajoutée à `limites-harnais.md` (11 limites, à reporter dans l'affichage de la story 9).
- LOW · relecture · corrigé · `POST /api/intentions/mcp_server` acceptait `github` (sous-option cachée de la brique Harnais) ; refusé en 404.
- Reporté · essai réel avec Anaël : device flow derrière le proxy, renouvellement sans client secret accepté par GitHub (non vérifiable sans compte), 401/403 réels, page MCP rejouée (E2E `mcp_lab_page`, `mcp_lab`).

## Correctif après fusion

Correctif du 16/10 (branche `fix/v1-1-v2-test-program`, base 998729f) : GitHub reste un
serveur authentifié de l'Atelier MCP, sans instantané public possible (`scripts/snapshot_mcp.py`
échouait par `KeyError: 'api.githubcopilot.com'`, le filtre `s.network` de `mcp_servers()`
incluant GitHub comme les deux vrais serveurs publics). Deux endroits manquaient encore
l'exclusion explicite déjà faite ailleurs (`AppSession._mcp_options`, `server.id != "github"`) :
`scripts/snapshot_mcp.py` (liste des serveurs « publics » à instantanéifier) et
`AppSession._outbound_fr` (la ligne « Peuvent sortir du poste », qui énumérait GitHub comme
un serveur MCP public de la brique Harnais). Les deux excluent maintenant `github` par id,
comme `_mcp_options`. Testé : `tests/test_program.py::test_snapshot_script_writes_each_public_servers_tools`,
`tests/test_bricks.py::test_outbound_line_without_network_tool_or_public_server`, et les
suites `tests/test_mcp*.py`, `tests/test_bricks.py` complètes, verts.
