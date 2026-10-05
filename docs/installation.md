# Installation détaillée

[← Retour au README](../README.md)

WaveStack s'installe sans droits administrateur, depuis le dépôt Git ou une archive zip. La
cible est un PC Windows professionnel ; macOS et Linux suivent la même procédure, à quelques
commandes près.

- [Prérequis](#prérequis)
- [Derrière un proxy d'entreprise](#derrière-un-proxy-dentreprise)
- [Windows](#windows)
- [macOS et Linux](#macos-et-linux)
- [Le modèle local](#le-modèle-local)
- [Modèles du RAG](#modèles-du-rag)
- [Premier lancement et diagnostic](#premier-lancement-et-diagnostic)
- [Mise à jour](#mise-à-jour)
- [Extras optionnels](#extras-optionnels)

## Prérequis

- Un accès au dépôt privé WaveStack et Git, ou une archive zip de WaveStack (téléchargée depuis
  le dépôt, ou remise par votre formateur sur un partage interne).
- [`uv`](https://docs.astral.sh/uv/) installé pour l'utilisateur courant (aucun droit
  administrateur requis). `uv run` télécharge lui-même Python 3.13 (dans le profil utilisateur,
  sans élévation) et synchronise les dépendances depuis `uv.lock`.
- Windows 10 ou 11 **x64** (pas Windows sur ARM : le moteur `llama-cpp-python` n'y est pas
  publié), Linux ou macOS sur puce Apple (voir [macOS et Linux](#macos-et-linux)).
- Environ 3 Go d'espace disque libre (Python, dépendances et modèle), 4,5 Go avec les modèles
  du RAG et tous les extras, 5,9 Go avec en plus les modèles de l'Atelier RAG (deux d'embedding,
  un de reranking).
- Pas de carte graphique nécessaire. Le modèle recommandé occupe environ 2 Go de RAM (mesuré sur
  le PC cible) ; comme le [budget mémoire](modeles.md#budget-mémoire) en retient 60 % de la RAM
  disponible au lancement, comptez environ 4 Go de RAM libre (fermez Teams ou le navigateur au
  besoin). Les modèles de l'Atelier RAG se chargent le temps d'une exécution, en plus : environ
  1 Go chacun pour Qwen3-Reranker 0.6B (937 Mo) et Qwen3-Embedding 0.6B (1 055 Mo), mesurés sur
  le PC de développement ; le budget refuse, chiffres à l'appui, ce qui ne tient pas.
- Sur un réseau d'entreprise, les réglages de
  [Derrière un proxy d'entreprise](#derrière-un-proxy-dentreprise), avant toute commande.

## Derrière un proxy d'entreprise

- `UV_SYSTEM_CERTS=1` pour utiliser les certificats du système.
- `UV_PYTHON_INSTALL_MIRROR=<miroir>` si `releases.astral.sh` est bloqué pour le téléchargement
  de Python.
- Domaines à autoriser : `astral.sh` et `releases.astral.sh` (script d'installation de `uv`,
  `uv` lui-même et Python), PyPI (`pypi.org`, `files.pythonhosted.org`), `abetlen.github.io`
  (roue CPU de `llama-cpp-python`), `github.com` et ses domaines de téléchargement,
  `huggingface.co` et `*.hf.co`.
- Pour llama-server, facultatif (voir [Obtenir llama-server sans droits d'administrateur](modeles.md#obtenir-llama-server-sans-droits-dadministrateur-windows)) :
  `api.github.com`, et les hôtes de téléchargement des releases GitHub,
  `objects.githubusercontent.com` et `release-assets.githubusercontent.com`.
- Pendant les séances, selon les briques utilisées : les modèles cloud (voir
  [Hôtes à autoriser](modeles.md#hôtes-à-autoriser)) et les serveurs MCP publics,
  `learn.microsoft.com` et `mcp.data.gouv.fr` (voir le
  [programme de formation](guide.md#programme-de-formation)).

Si le proxy n'est pas détecté, indiquez-le aussi : `$env:HTTPS_PROXY = "http://proxy:port"`.
Dans PowerShell, `$env:UV_SYSTEM_CERTS = "1"` ne vaut que pour le terminal en cours ;
`setx UV_SYSTEM_CERTS 1` enregistre la variable pour les terminaux ouverts ensuite (pas pour
celui-ci). Il en va de même pour `UV_PYTHON_INSTALL_MIRROR`.

Ces réglages de proxy concernent l'installation (via `uv`), pas WaveStack lui-même : une fois
lancée, l'application ne peut sortir que vers les hôtes de sa propre liste blanche
(`wavestack.toml`, section `[net] allowed_hosts`). Pour autoriser un hôte supplémentaire (par
exemple un miroir interne de modèles), ajoutez-le dans `settings.json`, dans le dossier de
données (`%LOCALAPPDATA%\WaveStack` sous Windows, `~/.local/share/wavestack` ailleurs) :

```json
{ "net": { "allowed_hosts": ["mon-miroir-interne.exemple.com"] } }
```

Ce fichier surcharge `wavestack.toml` sans le modifier ; les hôtes en boucle locale
(`127.0.0.1`, `localhost`) et les hôtes de proxy détectés sont toujours autorisés.

## Windows

Dans un terminal PowerShell, installez d'abord `uv` dans votre profil, puis fermez et rouvrez
le terminal pour que la commande `uv` soit reconnue :

```powershell
powershell -ExecutionPolicy ByPass -c "irm https://astral.sh/uv/install.ps1 | iex"
```

Dans le nouveau terminal, récupérez WaveStack, déposez le modèle (1,28 Go), puis lancez :

```powershell
git clone <adresse-du-dépôt>
cd <dossier-cloné>

New-Item -ItemType Directory -Force "$env:LOCALAPPDATA\WaveStack\models" | Out-Null
$ProgressPreference = "SilentlyContinue"   # sinon PowerShell 5.1 télécharge très lentement
Invoke-WebRequest -UseBasicParsing "https://huggingface.co/unsloth/Qwen3.5-2B-GGUF/resolve/main/Qwen3.5-2B-Q4_K_M.gguf" -OutFile "$env:LOCALAPPDATA\WaveStack\models\Qwen3.5-2B-Q4_K_M.gguf"

uv run wavestack
```

Si le téléchargement du modèle échoue derrière le proxy (erreur 407 notamment), prenez
[le fichier](https://huggingface.co/unsloth/Qwen3.5-2B-GGUF/resolve/main/Qwen3.5-2B-Q4_K_M.gguf)
avec le navigateur et copiez-le dans `%LOCALAPPDATA%\WaveStack\models`.

Au premier clone, Git vous demande de vous authentifier auprès de l'hébergeur du dépôt. Avec
l'archive zip, décompressez-la, ouvrez un terminal dans le dossier obtenu, puis lancez
`uv run wavestack`.

Placez WaveStack hors de OneDrive et des lecteurs réseau, par exemple dans
`%USERPROFILE%\wavestack` : son environnement Python compte des milliers de fichiers. Lancez
les commandes depuis le dossier qui contient `pyproject.toml` (une archive zip décompressée
par l'Explorateur ajoute souvent un niveau de dossier).

Le premier `uv run wavestack` télécharge plusieurs centaines de Mo et prend quelques minutes.
Pour arrêter WaveStack, faites Ctrl+C dans le terminal (ou fermez-le) ; pour le relancer,
retapez `uv run wavestack` dans le même dossier. Si le port 8420 est pris, choisissez-en un
autre : `uv run wavestack --port 8421`.

Si la politique du poste refuse le script d'installation de `uv`, utilisez l'une des autres
méthodes de la [documentation d'uv](https://docs.astral.sh/uv/getting-started/installation/)
(archive autonome à décompresser dans le profil, par exemple). Si le poste bloque l'exécution
de programmes depuis le profil utilisateur (AppLocker, WDAC), `uv`, Python et WaveStack ne
peuvent pas tourner : demandez une exception pour eux à votre service informatique, sans
contourner le blocage.

## macOS et Linux

La procédure est la même ; seules l'installation de `uv` et le dossier de données changent :

```bash
curl -LsSf https://astral.sh/uv/install.sh | sh
source "$HOME/.local/bin/env"   # uv dans ce terminal, sans le rouvrir
git clone <adresse-du-dépôt> && cd <dossier-cloné>
mkdir -p ~/.local/share/wavestack/models
curl -fL -o ~/.local/share/wavestack/models/Qwen3.5-2B-Q4_K_M.gguf \
  https://huggingface.co/unsloth/Qwen3.5-2B-GGUF/resolve/main/Qwen3.5-2B-Q4_K_M.gguf
uv run wavestack
```

- **Dossier de données** : `~/.local/share/wavestack` (sous macOS aussi), au lieu de
  `%LOCALAPPDATA%\WaveStack`.
- **Linux** : x86_64 et ARM64 ; c'est la plateforme des tests de bout en bout du projet.
- **macOS** : puces Apple seulement (le moteur `llama-cpp-python` n'est publié que pour
  `arm64`), et non vérifié sur un vrai poste à ce jour.
- **Le reste de la documentation** donne les commandes en PowerShell : remplacez
  `%LOCALAPPDATA%\WaveStack` par `~/.local/share/wavestack`, `$env:NOM = "valeur"` par
  `export NOM=valeur` dans le terminal, et `setx NOM valeur` par cette même ligne dans votre
  profil de shell.

## Le modèle local

Le modèle recommandé est **Qwen3.5-2B en Q4_K_M** (GGUF amont publié par unsloth, licence
Apache-2.0), validé sur le PC cible. WaveStack ne le télécharge pas : copiez le fichier `.gguf`
dans le dossier `models/` du dossier de données (`%LOCALAPPDATA%\WaveStack\models` sous
Windows, `~/.local/share/wavestack/models` ailleurs), ou indiquez son chemin au diagnostic.
Un blob GGUF d'Ollama choisi comme un fichier peut être refusé par llama-cpp-python 0.3.35
(fichier incompatible, raison expliquée, modèle précédent gardé) : préférez le fichier amont.
Servi par Ollama lui-même, le même modèle fonctionne avec un Ollama récent (`qwen3.5:2b` au test
du 2026-09-27), ou par llama-server (voir [Utiliser un serveur déjà lancé](modeles.md#utiliser-un-serveur-déjà-lancé-ollama-llama-server)).

Sans modèle local, WaveStack fonctionne aussi avec un modèle cloud : collez une clé API au
diagnostic (voir [Modèles cloud](modeles.md#modèles-cloud)).

## Modèles du RAG

La brique RAG (et l'Atelier RAG) utilise deux petits modèles GGUF, distincts du modèle de
conversation et jamais proposés comme tel ; l'Atelier RAG en propose deux de plus pour son
étape Embedding et un pour son étape Reranking. Chacun est nommé dans une seule section de
`wavestack.toml`, qui donne aussi son adresse de téléchargement et son sha256 :

| Rôle | Fichier | Taille | Section | Dossier |
|---|---|---|---|---|
| Embedding (obligatoire pour le RAG) | `granite-embedding-107m-multilingual-Q8_0.gguf` (IBM, Apache-2.0) | 121 Mo | `[rag.embedding]` | `models/embedding/` |
| Reranking (facultatif, case « Reranking ») | `bge-reranker-v2-m3-Q4_K_M.gguf` (BAAI, Apache-2.0) | 438 Mo | `[rag.reranker]` | `models/reranker/` |
| Embedding de l'Atelier RAG (facultatif) | `multilingual-e5-small-q8_0.gguf` (intfloat, MIT) | 132 Mo | `[[rag_lab.embeddings]]` | `models/embedding/` |
| Embedding de l'Atelier RAG (facultatif) | `Qwen3-Embedding-0.6B-Q8_0.gguf` (Qwen, Apache-2.0) | 639 Mo | `[[rag_lab.embeddings]]` | `models/embedding/` |
| Reranking de l'Atelier RAG (facultatif) | `qwen3-reranker-0.6b-q8_0.gguf` (Qwen, Apache-2.0) | 639 Mo | `[[rag_lab.rerankers]]` | `models/reranker/` |

Les dossiers sont relatifs au dossier `models/` du dossier de données
(`%LOCALAPPDATA%\WaveStack\models\embedding\` sous Windows,
`~/.local/share/wavestack/models/embedding/` ailleurs ; de même pour `reranker\`).

**Les télécharger.** Depuis la carte RAG de l'Atelier Harnais, sans ligne de commande :
« Télécharger le modèle d'embedding », puis, dans la sous-option « Reranking », « Télécharger
le modèle de reranking ». WaveStack vérifie la taille et le sha256 de chaque fichier.

**Les modèles d'embedding de l'Atelier RAG** (multilingual-e5-small, Qwen3-Embedding 0.6B) sont
des options de son étape Embedding, à côté de celui de la brique. Pour les télécharger, ouvrez
l'Atelier RAG (lien « RAG » de la barre de navigation) : dans la colonne ARCHITECTURE, la tuile
Embedding model affiche, dans les deux modes, « N modèles à télécharger » (les modèles absents de
l'étape, celui de la brique compris : 2 sur une installation neuve où il est déjà là) ; son clic
passe en mode Composer et choisit la ligne Embedding de la séquence, où chaque modèle absent a
son bouton « Télécharger (≈ taille) » (taille et sha256 vérifiés). En mode Composer, ces boutons
sont visibles sans rien choisir. Sinon, téléchargez-les à la main (adresses `url` des entrées
`[[rag_lab.embeddings]]` de `wavestack.toml`) et copiez-les sous ces noms exacts dans
`models/embedding/`. Sans son fichier, l'option est grisée, la raison nomme le fichier attendu ;
WaveStack vérifie son sha256 au chargement. **Le modèle de reranking de l'Atelier RAG**
(Qwen3-Reranker 0.6B) se télécharge de même : « N modèles à télécharger » sous la tuile
Reranker (celui de la brique compris s'il manque), puis le bouton de la ligne Reranking. Une chaîne sans étape Reranking (préréglages « RAG dense », « RAG hybride ») n'a ni
tuile ni ligne Reranking : au pied du groupe MODÈLES, une phrase dit d'ajouter l'étape, et son
clic la propose dans « Ajouter un composant ». Le fichier peut aussi se placer à la main, sous
son nom exact, dans `models/reranker/` (adresse `url` de l'entrée `[[rag_lab.rerankers]]`).

**Hors ligne, ou derrière un proxy qui bloque Hugging Face.** Téléchargez les fichiers sur un
autre poste (adresses `url` des sections `[rag.embedding]` et `[rag.reranker]` de
`wavestack.toml`, et, pour l'Atelier RAG, des entrées `[[rag_lab.embeddings]]` et
`[[rag_lab.rerankers]]`), copiez-les sous ces noms exacts dans `models/embedding/` et
`models/reranker/`, puis cliquez de nouveau sur la carte RAG ou rechargez l'Atelier RAG (ou
relancez WaveStack).

**Les index.** Les index du corpus sont livrés avec le dépôt, un par langue :
`data/rag_index.sqlite` (français), `data/rag_index.en.sqlite` et `data/rag_index.de.sqlite`.
Il n'y a rien à construire sur une installation neuve : seul le modèle d'embedding manque. Pour
reconstruire un index (après un changement de `[rag.embedding]`, de `[rag] chunk_max_chars` ou
du corpus), utilisez « Construire l'index » sur la carte RAG, ou le script, une langue à la fois :

```bash
uv run python scripts/build_rag_index.py --download --lang fr   # télécharge d'abord l'embedding
uv run python scripts/build_rag_index.py --lang en
uv run python scripts/build_rag_index.py --lang de
```

`--download` ne prend que le modèle d'embedding (le reranker n'entre pas dans l'index) ;
`--model C:\chemin\modele.gguf` désigne un fichier copié ailleurs (le même que celui de
`[rag.embedding]`). Détails : [Brique RAG, corpus et index](guide.md#brique-rag-corpus-et-index).

**Pour l'Atelier RAG seulement :**

- FAISS et LanceDB, deux bases vectorielles de plus : `uv sync --extra rag-alt` (≈ 390 Mo,
  voir [Extras optionnels](#extras-optionnels)) ;
- fastembed, un second modèle d'embedding, est **facultatif** et n'est pas livré : voir
  [FAISS et LanceDB](guide.md#faiss-et-lancedb-extra-rag-alt) pour l'ajouter sur un poste.

## Premier lancement et diagnostic

Au lancement, WaveStack vérifie la mémoire disponible, la présence d'un modèle GGUF déjà sur le
poste, l'accès réseau et la disponibilité du port — chaque résultat s'affiche en français dans le
terminal et sur la page de diagnostic. Si aucun modèle n'est trouvé, la page propose de saisir le
chemin d'un fichier `.gguf` (partage, clé USB, cache Hugging Face, LM Studio, Ollama). Avec
plusieurs modèles utilisables, cliquez sur « Choisir » en face de celui que vous voulez, puis
ouvrez l'Atelier Harnais par le lien « Harnais » de la barre de navigation. Pour la suite (l'interface,
les scénarios, les ateliers), voir le [guide d'utilisation](guide.md).

### Page ouverte au lancement

- Au premier lancement sur le poste, le navigateur s'ouvre sur le diagnostic
  (`http://127.0.0.1:8420/diagnostic`) au bout d'une seconde, pour voir défiler les vérifications.
- Aux lancements suivants, il s'ouvre une fois le diagnostic terminé : sur l'interface principale
  (`/`) si tout est prêt, sinon sur le diagnostic. Si le diagnostic dure plus de 30 s, le
  diagnostic s'ouvre.
- Si WaveStack tourne déjà, la commande ouvre l'interface principale quand l'instance est prête,
  sinon le diagnostic.
- Le diagnostic reste accessible par l'indicateur de modèle de la barre du bas et par le lien
  « 🛠️ Diagnostic » de la barre de navigation, en haut de chaque page.

### Premier lancement long sur un poste qui a beaucoup de modèles

Avant de proposer un choix, le diagnostic teste chaque fichier GGUF trouvé (dossier des modèles,
cache Hugging Face, LM Studio, Ollama), chacun dans un processus à part. Sur un poste qui a
beaucoup de modèles Ollama, comptez une dizaine de minutes (18 modèles le 2026-10-02) ; la page
dit « n modèles testés sur N ». Les résultats sont gardés dans `settings.json` : les lancements
suivants ne refont pas ces tests (sauf pour un fichier modifié).

## Mise à jour

`git pull` (ou un nouveau zip), puis `uv run wavestack`, qui resynchronise sur `uv.lock`. Si
vous utilisez un extra (ci-dessous), relancez aussi `uv sync` avec tous vos extras, par exemple
`uv sync --extra compression` : un `uv sync` qui omet un extra le désinstalle.

## Extras optionnels

Trois briques ou ateliers demandent des dépendances supplémentaires, que `uv run wavestack`
seul n'installe pas. Ajoutez-les depuis le dossier de WaveStack, puis après chaque mise à jour,
en gardant tous les extras voulus dans la même commande :

```bash
uv sync --extra compression --extra rag-alt --extra greenops
```

| Extra | Ce qu'il active | Taille | Détails |
|---|---|---|---|
| `compression` | La brique Compression (Headroom) | ≈ 285 Mo | [Compression du contexte](guide.md#compression-du-contexte-headroom) |
| `rag-alt` | FAISS et LanceDB dans l'Atelier RAG | ≈ 390 Mo | [FAISS et LanceDB](guide.md#faiss-et-lancedb-extra-rag-alt) |
| `greenops` | L'empreinte des modèles locaux (CodeCarbon) | ≈ 150 Mo | [GreenOps](guide.md#greenops-empreinte-estimée-des-appels-au-modèle) |
