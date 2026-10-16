# Existant touché par la vague 2 (relevé du 16/10/2026, lecture seule)

| Zone | Où | État |
|---|---|---|
| Serveurs MCP | `content/mcp.yaml:5-13`, `src/wavestack/mcp/servers.py:39-43` | `local` (stdio), `datagouv`, `mslearn` (distants, couple id/url). Aucune authentification. |
| MCP local | `src/wavestack/mcp/local_server.py:55-86` | Outils `list_terms`, `define_term` ; ressource `terms` ; prompt `explain_term`. Textes dans `content/mcp_local/`. |
| Journal MCP | `src/wavestack/mcp/lab.py:412-536` (`record`) | Journal des messages JSON-RPC de l'atelier. Pas de liste blanche d'outils, pas de décision d'autorisation. |
| Hooks | `src/wavestack/hooks.py:167-318`, `content/hooks.yaml` | H1 `guard` bloque `confidentiel/`, H2 `audit` journalise, H3 `inject` ajoute la date, H5 `ask` confirme avant un envoi réseau. Aucun filtrage de contenu en entrée ou en sortie. |
| Réseau | `src/wavestack/net/guard.py` (`allowed_hosts`), `src/wavestack/tools/network.py:5` | Liste blanche d'hôtes. |
| FinOps | `web/static/app.js:2425-2487`, plafond `maxSessionUsd` `:92`, compression `:3761`, sous-agent `:3781` ; `session/app_session.py:1031-1036` | Coût et tokens par appel, tour et séance. Sous-agent sommé dans le total sans ligne dédiée. Cache cloud lu et tarifé (`models/cloud_base.py:317,333`) mais non affiché. `timings.prompt_n` lu (`models/servers.py:520-522`), `cache_n` ignoré. |
| Affichage | `web/static/index.html:48`, `panes.js:426-430` | Seul mode : « Mode projection » (clé `wavestack.projection`). Aucune notion de public. |
| Pages | `web/static/` | index, llm, mcp, rag, diagnostic. Textes des ateliers : `content/llm_lab.yaml`, `rag_lab.yaml`, `mcp_lab.yaml`. |
| Hébergement | `cli.py:302`, `web/app.py:396-401` | Écoute sur `127.0.0.1`, contrôle d'origine des POST. Ni multi-utilisateur ni authentification. |
