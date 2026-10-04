# Contribuer à WaveStack

[← Retour au README](README.md)

WaveStack est un démonstrateur pédagogique : la clarté de ce qu'il montre passe avant la qualité
des réponses du modèle. Il doit tourner sur un PC professionnel sans GPU ni droits
administrateur.

## Environnement de développement

Installez WaveStack comme indiqué dans [l'installation détaillée](docs/installation.md), puis,
depuis le dossier du dépôt :

```bash
uv sync --extra compression --extra rag-alt --extra greenops   # leurs tests
uv run ruff check .
uv run ruff format .
uv run pytest
```

Les tests marqués `model` nécessitent un vrai fichier GGUF sur le poste ; ils sont sautés par
défaut. Pour les jouer : `uv run pytest -m model`, avec `WAVESTACK_TEST_GGUF` (chemin d'un
fichier GGUF) et, pour ceux du RAG, `WAVESTACK_TEST_MODELS_DIR` (le dossier `models` de
WaveStack, par exemple `%LOCALAPPDATA%\WaveStack\models`). Les tests ne touchent jamais au
vrai dossier de données : chacun a le sien, temporaire.

Les tests de bout en bout rejouent l'interface dans un navigateur, avec un faux modèle : voir
[tools/e2e/README.md](tools/e2e/README.md).

## Conventions

- **`uv` pour tout** (`uv add`, `uv run`, `uv sync`), jamais `pip`.
- **`ruff`** pour le lint et le formatage, **`pytest`** pour les tests.
- **Langues** : code et identifiants en anglais. Textes d'interface et contenus pédagogiques en
  français par défaut, sous `content/` ; l'anglais et l'allemand en surcouche sous
  `content/i18n/{en,de}/`, avec la même arborescence et les mêmes noms de fichiers (résolus par
  `config.content_file`). Un fichier absent d'une langue y est lu en français.
- **Méthode** : le développement suit la méthode BMAD, configurée dans `_bmad/` ; les
  spécifications, stories et rapports sont dans `_bmad-output/`.
- **Documentation** : le [README](README.md) reste court (présentation et première
  installation). Le détail va dans `docs/` : [installation](docs/installation.md),
  [guide d'utilisation](docs/guide.md) et [modèles](docs/modeles.md). Les liens relatifs entre
  ces fichiers sont vérifiés par `tests/test_docs_links.py`.

## Ajouter un scénario

Un nouveau scénario s'ajoute dans `content/scenarios.yaml`, sans modifier le code : un scénario
métier va dans `transverse`, avec un titre « Métier … », sa durée et son message « À retenir »
dans la consigne. Les tests du programme (`tests/test_program.py`) vérifient ces règles, le
cumul des modules et l'adéquation de chaque scénario à la fenêtre, sans liste de scénarios à
mettre à jour. Pour qu'ils comptent la documentation réelle des serveurs MCP publics, lancez une
fois sur un poste relié au réseau `uv run python scripts/snapshot_mcp.py` : il enregistre leurs
outils dans `content/mcp_snapshots/`. En séance, à la connexion d'un serveur public qui a un
instantané, WaveStack compare sa liste d'outils à l'instantané : si elle s'en écarte de plus de
`[mcp] snapshot_drift_threshold` (`wavestack.toml`, 0.2 soit 20 % : outils ajoutés ou retirés,
ou poids de leur documentation), la carte MCP l'affiche en le nommant ; la jauge prévue pour
ses scénarios peut alors ne plus tenir, relancez le script pour mettre l'instantané à jour.

## Reconstruire les index du RAG

Après un changement de `[rag.embedding]` ou de `[rag] chunk_max_chars`, ou du corpus,
reconstruisez les trois index livrés avec le dépôt : voir
[Brique RAG, corpus et index](docs/guide.md#brique-rag-corpus-et-index).

## Régénérer le GIF de démonstration

Le GIF et la vidéo du README (`docs/assets/wavestack-demo.gif` et `.mp4`) se régénèrent quand
l'interface change : voir [tools/demo/README.md](tools/demo/README.md).
