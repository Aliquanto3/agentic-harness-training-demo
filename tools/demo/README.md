# GIF et vidéo de démonstration du README

[← Retour à Contribuer](../../CONTRIBUTING.md)

Les scripts de ce dossier régénèrent `docs/assets/wavestack-demo.gif` et
`docs/assets/wavestack-demo.mp4` à partir de la vraie interface : le scénario « LLM nu » puis
« Outils natifs » sur « Quelle heure est-il ? », puis les trois étapes de l'Atelier LLM (INPUT,
TRANSFORMATION, OUTPUT) sur « La capitale de la France est », jusqu'au token tiré, la visite
guidée de l'Atelier RAG (« Dérouler », sans exécution : aucun modèle du RAG n'est nécessaire) et
la poignée de main de l'Atelier MCP avec le glossaire local (sans réseau). À refaire quand
l'interface change.

## Prérequis

- Windows, pour les polices Segoe UI et Segoe UI Emoji des légendes.
- `ffmpeg` dans le `PATH` (par exemple `winget install Gyan.FFmpeg`, sans droits
  administrateur).
- Google Chrome installé (Playwright le pilote par le canal `chrome`).
- Le modèle local Qwen3.5-2B (voir [l'installation](../../docs/installation.md#le-modèle-local)).

## Régénérer

1. Préparez un dossier de données jetable, pour ne pas toucher à vos propres réglages ni à votre
   conversation. Copiez-y le `settings.json` de votre dossier de données habituel, puis mettez-y
   `"language": "fr"` et
   `"selected_model": {"kind": "file", "ref": "<chemin complet de Qwen3.5-2B-Q4_K_M.gguf>"}`.
   Sans cette copie, le diagnostic teste d'abord chaque GGUF du poste (jusqu'à une dizaine de
   minutes avec beaucoup de modèles Ollama) et ne trouve pas le modèle du dossier habituel :
   indiquez alors son chemin au diagnostic.

2. Lancez WaveStack sur ce dossier :

   ```powershell
   $env:WAVESTACK_DATA_DIR = "$env:TEMP\wavestack-demo"
   $env:BROWSER = "cmd /c rem %s"   # aucun navigateur ne s'ouvre
   uv run wavestack
   ```

3. Dans un autre terminal, capturez les écrans (1600 × 900), puis montez le GIF et la vidéo :

   ```powershell
   uv run --with playwright==1.56.0 python tools/demo/drive.py $env:TEMP\wavestack-frames
   uv run --with pillow python tools/demo/compose.py $env:TEMP\wavestack-frames
   ```

4. Regardez le résultat avant de le committer. Le modèle ne répond pas deux fois pareil : si une
   prise est ratée (réponse du LLM nu qui ne montre pas qu'il ignore l'heure, token tiré peu
   parlant), refaites-la seule, `main`, `llm`, `rag` ou `mcp`, en ajoutant son nom à la commande
   de `drive.py`, puis relancez `compose.py`. Les cadres de mise en évidence nommés (réponse du
   modèle, sélecteur de scénario, éléments des ateliers) sont mesurés sur chaque capture ;
   ceux de l'écran principal après le tour avec outils sont placés en pixels, et les nombres de
   leurs étiquettes (17 et 271 tokens de contexte) sont écrits dans `compose.py` (fonction
   `build`) : vérifiez-les si la mise en page, le modèle ou les descriptions d'outils ont changé.

Le GIF pèse environ 2,5 Mo et dure 59 s. La dernière capture de l'écran principal (dossier
`main`, phase `tools_final`) sert aussi d'illustration au guide : `docs/assets/atelier.jpg`,
en 1280 × 720.
