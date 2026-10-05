# WaveStack

WaveStack rend visible, brique par brique, ce qu'un harnais agentique ajoute à un LLM nu :
raisonnement, mémoire, prompt système, outils, RAG, MCP, skills, hooks, sous-agent et
compression du contexte. Démonstrateur pédagogique local, qui tourne sur CPU, sans GPU ;
interface en français, en anglais et en allemand.

![Démonstration de WaveStack : le LLM nu ne connaît pas l'heure ; avec la brique Outils, le modèle appelle get_datetime et chaque étape s'affiche](docs/assets/wavestack-demo.gif)

*Même question, sans puis avec outils : le LLM nu avoue ne pas connaître l'heure ; avec les
outils, le modèle appelle `get_datetime`, et les volets Contexte LLM, Orchestration et Schéma
montrent chaque étape. [Version vidéo (MP4)](docs/assets/wavestack-demo.mp4).*

## Ce que vous y voyez

- **Quatre volets synchronisés** : ce que voit l'utilisateur, ce que lit vraiment le modèle,
  ce que fait le harnais pas à pas, et où tourne chaque pièce (sur le poste ou sur le réseau).
- **Des briques à brancher une à une**, au fil d'un programme guidé de six modules (5 h 15).
- **Trois ateliers pour regarder à l'intérieur** : l'Atelier LLM (de l'entrée aux tokens puis à
  la sortie), l'Atelier RAG (indexation puis requête, architectures toutes faites, modèle au
  choix pour chaque composant) et l'Atelier MCP.
- **Un petit modèle local** (Qwen3.5-2B, 1,3 Go), installé sans droits administrateur, ou un
  modèle cloud si vous avez une clé API.

## Installation sous Windows

Pour Windows 10 ou 11 x64, sans droits administrateur ; prévoyez 3 Go de disque (5,9 Go avec
tous les modèles du RAG) et 4 Go de RAM libre. Sous macOS ou Linux, ou si une étape bloque
(politique du poste, proxy), suivez [l'installation détaillée](docs/installation.md).
**Sur un réseau d'entreprise**, tapez d'abord `$env:UV_SYSTEM_CERTS = "1"` dans le terminal et
faites autoriser les domaines de [Derrière un proxy d'entreprise](docs/installation.md#derrière-un-proxy-dentreprise).

1. **Installez `uv`** dans un terminal PowerShell, puis rouvrez le terminal (refusé ? voir [Windows](docs/installation.md#windows)) :

   ```powershell
   powershell -ExecutionPolicy ByPass -c "irm https://astral.sh/uv/install.ps1 | iex"
   ```

2. **Récupérez WaveStack** et entrez dans son dossier, d'où se lancent les commandes suivantes
   (avec l'archive zip : décompressez-la, puis `cd agentic-harness-training-demo-main`) :

   ```powershell
   git clone https://github.com/Aliquanto3/agentic-harness-training-demo.git
   cd agentic-harness-training-demo
   ```

3. **Déposez le modèle** (1,28 Go) dans `%LOCALAPPDATA%\WaveStack\models`, le dossier de
   données de votre profil, hors du dossier cloné (une mise à jour du code n'y touche pas) :

   ```powershell
   New-Item -ItemType Directory -Force "$env:LOCALAPPDATA\WaveStack\models" | Out-Null
   $ProgressPreference = "SilentlyContinue"
   Invoke-WebRequest -UseBasicParsing "https://huggingface.co/unsloth/Qwen3.5-2B-GGUF/resolve/main/Qwen3.5-2B-Q4_K_M.gguf" -OutFile "$env:LOCALAPPDATA\WaveStack\models\Qwen3.5-2B-Q4_K_M.gguf"
   ```

   En cas d'échec, prenez [le fichier](https://huggingface.co/unsloth/Qwen3.5-2B-GGUF/resolve/main/Qwen3.5-2B-Q4_K_M.gguf) avec le navigateur et copiez-le dans ce dossier.

4. **Facultatif : ajoutez les extras** (compression Headroom, FAISS et LanceDB, CodeCarbon), tous dans la même commande :

   ```powershell
   uv sync --extra compression --extra rag-alt --extra greenops
   ```

5. **Lancez** avec `uv run wavestack`. Le premier lancement télécharge Python 3.13 et les
   dépendances (quelques minutes), puis ouvre le diagnostic. Si plusieurs modèles sont trouvés,
   cliquez sur « Choisir » en face de Qwen3.5-2B, puis ouvrez l'Atelier par le lien « Harnais ».

**Modèles du RAG.** La brique RAG demande un modèle d'embedding (121 Mo) et, en option, un
modèle de reranking (438 Mo), à télécharger depuis la carte RAG de l'Atelier Harnais. Ceux de
l'Atelier RAG (132 à 639 Mo) : page « RAG », « N modèles à télécharger » sous la tuile Embedding
model ou Reranker, puis « Télécharger ». [Détails et copie à la main](docs/installation.md#modèles-du-rag).

**Pour commencer**, choisissez le scénario « LLM nu » en bas à gauche et suivez sa consigne ;
le [programme de formation](docs/guide.md#programme-de-formation) enchaîne les modules. Ctrl+C
arrête WaveStack. Mise à jour : `git pull` (ou un nouveau zip), `uv sync` avec vos extras.

## Utiliser un modèle cloud (clé API)

Facultatif : le modèle local suffit pour toute la formation. Préréglages fournis : Groq,
Mistral, Gemini, Gemma, Claude et GPT-6 Luna. Créez une clé dans la console du fournisseur
(chez Mistral, activez d'abord le plan gratuit « Experiment »), collez-la au diagnostic dans la
ligne du modèle (« Enregistrer la clé »), puis « Tester », « Choisir » et « Utiliser ce
modèle ». La clé reste sur ce poste (`%LOCALAPPDATA%\WaveStack\api_keys.json`), n'est jamais
affichée ni tracée, et ne part que vers l'hôte du fournisseur. Variables d'environnement,
domaines à autoriser et conditions de chaque fournisseur : [Modèles cloud](docs/modeles.md#modèles-cloud).

## Aller plus loin

| Document | Contenu |
|---|---|
| [Installation détaillée](docs/installation.md) | Pas à pas Windows, macOS et Linux, premier lancement, proxy, mise à jour, extras |
| [Guide d'utilisation](docs/guide.md) | L'interface, le programme de formation, les ateliers, le RAG, la compression, FinOps et GreenOps |
| [Modèles](docs/modeles.md) | Changer de modèle, fenêtre de contexte, Ollama et llama-server, modèles cloud |
| [Contribuer](CONTRIBUTING.md) | Environnement de développement, conventions, tests, ajout de scénarios |

## Licence

WaveStack est distribué sous [licence Apache 2.0](LICENSE) : vous pouvez le réutiliser, le
modifier et l'intégrer à vos propres formations, à condition de conserver le fichier
[NOTICE](NOTICE) et de citer « WaveStack, par Anaël Yahi » avec un lien vers ce dépôt.
