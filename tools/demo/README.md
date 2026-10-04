# GIF et vidéo de démonstration du README

Régénère `docs/assets/wavestack-demo.gif` et `docs/assets/wavestack-demo.mp4` à partir de la vraie
interface : le scénario « LLM nu » puis « Outils natifs » sur « Quelle heure est-il ? », puis le
découpage en tokens de l'écran « LLM nu ». À refaire quand l'interface change.

## Prérequis

- Windows : les polices Segoe UI et Segoe UI Emoji servent aux légendes.
- `ffmpeg` dans le `PATH` (par exemple `winget install Gyan.FFmpeg`, sans droits
  administrateur).
- Google Chrome installé (Playwright le pilote par le canal `chrome`).
- Le modèle local Qwen3.5-2B (voir [l'installation](../../docs/installation.md#le-modèle-local)).

## Régénérer

1. Lancez WaveStack dans un dossier de données jetable, en français, avec le modèle local
   choisi, pour ne pas toucher à vos propres réglages ni à votre conversation :

   ```powershell
   $env:WAVESTACK_DATA_DIR = "$env:TEMP\wavestack-demo"
   $env:BROWSER = "cmd /c rem"   # aucun navigateur ne s'ouvre
   uv run wavestack
   ```

   Au diagnostic (`http://127.0.0.1:8420/diagnostic`), choisissez Qwen3.5-2B, puis laissez
   la langue en français. Un dossier de données neuf teste d'abord chaque GGUF du poste
   (jusqu'à une dizaine de minutes avec beaucoup de modèles Ollama) ; pour l'éviter, copiez-y
   le `settings.json` de votre dossier de données, puis mettez `"language": "fr"`.

2. Dans un autre terminal, capturez les écrans (1600 × 900), puis montez le GIF et la vidéo :

   ```powershell
   uv run --with playwright==1.56.0 python tools/demo/drive.py $env:TEMP\wavestack-frames
   uv run --with pillow python tools/demo/compose.py $env:TEMP\wavestack-frames
   ```

3. Regardez le résultat avant de le committer. Le modèle ne répond pas deux fois pareil : si la
   réponse du LLM nu ne montre pas bien qu'il ignore l'heure, relancez l'étape 2. Le cadre de
   la réponse suit la bulle du modèle ; les autres cadres sont placés en pixels dans
   `compose.py` (fonction `build`) et sont à vérifier si la mise en page a changé.

Le GIF pèse environ 1,6 Mo et dure 35 s.
