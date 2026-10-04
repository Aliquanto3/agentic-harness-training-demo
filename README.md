# WaveStack

WaveStack rend visible, brique par brique, ce qu'un harnais agentique ajoute à un LLM nu :
raisonnement, mémoire, prompt système, outils, RAG, MCP, skills, hooks et sous-agent.
Démonstrateur pédagogique local, en français, qui tourne sur CPU, sans GPU.

![Démonstration de WaveStack : le LLM nu ne connaît pas l'heure ; avec la brique Outils, le modèle appelle get_datetime et chaque étape s'affiche](docs/assets/wavestack-demo.gif)

*Même question, deux harnais : le LLM nu avoue ne pas connaître l'heure ; avec les outils, le
modèle appelle `get_datetime`, et le contexte, l'orchestration et le schéma montrent chaque
étape. [Version vidéo (MP4)](docs/assets/wavestack-demo.mp4).*

## Ce que vous y voyez

- **Quatre volets synchronisés** : ce que voit l'utilisateur, ce que lit vraiment le modèle,
  ce que fait le harnais pas à pas, et où tourne chaque pièce (sur le poste ou sur le réseau).
- **Des briques à brancher une à une**, guidées par un programme de six modules (5 h 15).
- **Trois ateliers** pour regarder à l'intérieur : le LLM nu (tokens, échantillonnage), une
  chaîne RAG et le protocole MCP.
- **Un petit modèle local** (Qwen3.5-2B, 1,3 Go) sans droits administrateur, ou un modèle cloud
  si vous avez une clé.

## Installation sous Windows

Aucun droit administrateur n'est nécessaire.

1. **Installez `uv`**, le gestionnaire Python utilisé par le projet, dans un terminal PowerShell :

   ```powershell
   powershell -ExecutionPolicy ByPass -c "irm https://astral.sh/uv/install.ps1 | iex"
   ```

   Fermez puis rouvrez le terminal pour que la commande `uv` soit reconnue.

2. **Récupérez WaveStack**, avec Git (`git clone <adresse-du-dépôt>`) ou en décompressant
   l'archive zip remise par votre formateur, puis ouvrez un terminal dans ce dossier.

3. **Déposez le modèle** : téléchargez
   [`Qwen3.5-2B-Q4_K_M.gguf`](https://huggingface.co/unsloth/Qwen3.5-2B-GGUF/resolve/main/Qwen3.5-2B-Q4_K_M.gguf)
   (1,28 Go) et placez-le dans `%LOCALAPPDATA%\WaveStack\models`.

4. **Lancez** :

   ```powershell
   uv run wavestack
   ```

Le premier lancement télécharge Python 3.13 et les dépendances dans votre profil, puis ouvre
le navigateur sur le diagnostic (`http://127.0.0.1:8420/diagnostic`). Une fois les
vérifications passées, l'atelier s'ouvre : choisissez le scénario « LLM nu » en bas à gauche
et suivez sa consigne.

**Derrière un proxy d'entreprise**, posez `UV_SYSTEM_CERTS=1` avant `uv run` et faites
autoriser les domaines listés dans [l'installation détaillée](docs/installation.md#derrière-un-proxy-dentreprise).

## Aller plus loin

| Document | Contenu |
|---|---|
| [Installation détaillée](docs/installation.md) | Pas à pas Windows, macOS et Linux, premier lancement, proxy, mise à jour, extras optionnels |
| [Guide d'utilisation](docs/guide.md) | L'interface, le programme de formation, les ateliers, le RAG, la compression, FinOps et GreenOps |
| [Modèles](docs/modeles.md) | Changer de modèle, fenêtre de contexte, Ollama et llama-server, modèles cloud |
| [Contribuer](CONTRIBUTING.md) | Environnement de développement, conventions, tests, ajout de scénarios |
