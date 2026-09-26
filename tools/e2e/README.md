# Tests de bout en bout (faux modèle)

Rejoue l'interface de WaveStack dans un Chromium sans affichage, sans GGUF ni accès à un
fournisseur : un faux serveur compatible OpenAI, déclaré comme modèle cloud, répond de façon
scriptée et déterministe.

## Relancer

```bash
uv run --with playwright==1.56.0 python tools/e2e/run_e2e.py
```

- `--only h5 caveman` : seulement ces scénarios (le diagnostic est toujours joué).
- `--keep` : garde le dossier de données temporaire (journaux `wavestack.log`,
  `fake_openai.log`, `settings.json`, `audit.log`) ; son chemin s'affiche au début.
- `--headed` : navigateur visible.

Playwright n'est pas une dépendance du projet : `--with` l'ajoute le temps de la commande.
Il faut un Chromium de la révision attendue par Playwright 1.56 (`PLAYWRIGHT_BROWSERS_PATH`),
sinon le script essaie `/opt/pw-browsers/chromium`. Code de sortie 1 si une vérification
échoue ; `KNOWN [Ax]` signale une anomalie déjà décrite dans
`_bmad-output/implementation-artifacts/test-e2e-palier-1-cloud.md`, sans faire échouer.

Les captures (JPEG) sont réécrites dans `tools/e2e/screenshots/`.

Pour explorer à la main : `uv run python tools/e2e/stack.py` lance le faux modèle et WaveStack
(adresse affichée), puis choisissez « Faux fournisseur (e2e) » au diagnostic.

## Fichiers

- `fake_openai.py` : le faux serveur (`/v1/chat/completions` en SSE avec `usage`,
  `/v1/models`, `/_e2e/requests` pour relire les corps reçus). Clé attendue : `e2e-fake-key`.
- `stack.py` : dossier de données temporaire, `settings.json` qui déclare le modèle `fake`
  (clé par `key_env = WAVESTACK_FAKE_API_KEY`), lancement des deux serveurs sur `127.0.0.1`.
  `wavestack.toml` n'est jamais modifié.
- `run_e2e.py` : les scénarios Playwright ; le journal est lu en parallèle sur `/api/stream`.
- `tests/test_e2e_fake_openai.py` : tests pytest du faux serveur, sans navigateur.

## Déclencheurs du faux modèle

La réponse dépend du dernier message de l'utilisateur (sans le texte ajouté par H3), des
outils proposés et des résultats déjà reçus dans le tour :

| Message contient | Réponse |
|---|---|
| « heure », « Combien font », « recette_crepes », « confidentiel », « férié », « Wikipédia », « compte rendu », « MCP … veut dire » | appel de l'outil correspondant s'il est proposé (`get_datetime`, `calculator`, `read_file`, `public_holidays`, `wikipedia_summary`, `load_skill`, `load_tool_doc` puis `local__define_term`), puis « D'après le résultat de l'outil : … » |
| « Délègue … sous-agent » (story 19) | appel de `delegate`, tâche « Lis le fichier guide_harnais.md et résume-le… » (` [lent]` recopié ; avec « page web » : tâche de lecture de page, le sous-agent appelle `fetch_page`) ; le sous-agent (tâche avec « guide_harnais ») appelle `read_file`, puis répond « D'après le résultat de l'outil : … » |
| « Je m'appelle X » / « Comment je m'appelle » | retient X s'il est dans l'historique |
| « Retiens que … » / « Rappelle-moi mon prénom » | appel de `remember` (mémoire globale) / prénom lu dans le message système |
| prompt système « … toujours en une phrase, comme un pirate » | « Arrr ! … » |
| « harnais » | réponse longue, courte si le skill Caveman est chargé |
| `[mal-formé]` / `[mal-formé-toujours]` / `[outil-inconnu]` | arguments JSON invalides puis correction / à chaque essai / outil inexistant |
| `[tool_use_failed]` | 400 `tool_use_failed` (façon Groq) |
| `[erreur429]`, `[erreur500]`, `[erreur401]`, `[flux-erreur]` | refus du fournisseur, erreur au milieu du flux |
| `[coupé]`, `[long]`, `[lent]`, `[raisonne]` | `finish_reason: length`, texte long, flux lent (pour « Arrêter »), champ `reasoning` |
| `[sans-usage]` | réponse sans `usage` en fin de flux (tokens estimés par WaveStack) |
