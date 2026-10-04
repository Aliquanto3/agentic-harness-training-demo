# Installation détaillée

[← Retour au README](../README.md)

WaveStack s'installe sans droits administrateur, depuis le dépôt Git ou une archive zip. La
cible est un PC Windows professionnel ; macOS et Linux suivent la même procédure, à deux
commandes près.

- [Prérequis](#prérequis)
- [Windows](#windows)
- [macOS et Linux](#macos-et-linux)
- [Le modèle local](#le-modèle-local)
- [Premier lancement et diagnostic](#premier-lancement-et-diagnostic)
- [Derrière un proxy d'entreprise](#derrière-un-proxy-dentreprise)
- [Mise à jour](#mise-à-jour)
- [Extras optionnels](#extras-optionnels)

## Prérequis

- Un accès au dépôt privé WaveStack et Git, ou une archive zip de WaveStack (téléchargée depuis
  le dépôt, ou remise par votre formateur sur un partage interne).
- [`uv`](https://docs.astral.sh/uv/) installé pour l'utilisateur courant (aucun droit
  administrateur requis). `uv run` télécharge lui-même Python 3.13 (dans le profil utilisateur,
  sans élévation) et synchronise les dépendances depuis `uv.lock`.
- Moins de 3 Go de disque (Python, dépendances et modèle). Aucune carte graphique : le modèle
  recommandé occupe environ 2 Go de RAM (mesure de la sonde sur le PC cible).

## Windows

Dans un terminal PowerShell :

```powershell
# 1. uv, dans le profil utilisateur (fermez puis rouvrez le terminal ensuite)
powershell -ExecutionPolicy ByPass -c "irm https://astral.sh/uv/install.ps1 | iex"

# 2. WaveStack
git clone <adresse-du-dépôt>
cd <dossier-cloné>

# 3. Le modèle (1,28 Go)
New-Item -ItemType Directory -Force "$env:LOCALAPPDATA\WaveStack\models" | Out-Null
$ProgressPreference = "SilentlyContinue"   # sinon PowerShell 5.1 télécharge très lentement
Invoke-WebRequest -UseBasicParsing "https://huggingface.co/unsloth/Qwen3.5-2B-GGUF/resolve/main/Qwen3.5-2B-Q4_K_M.gguf" -OutFile "$env:LOCALAPPDATA\WaveStack\models\Qwen3.5-2B-Q4_K_M.gguf"

# 4. Lancement
uv run wavestack
```

Au premier clone, Git vous demande de vous authentifier auprès de l'hébergeur du dépôt. Avec
l'archive zip, décompressez-la, ouvrez un terminal dans le dossier obtenu, puis lancez
`uv run wavestack`.

Si la politique du poste refuse le script d'installation de `uv`, prenez l'une des autres
méthodes de la [documentation de uv](https://docs.astral.sh/uv/getting-started/installation/)
(archive autonome à décompresser dans le profil, par exemple).

## macOS et Linux

La procédure est la même ; seules l'installation de `uv` et le dossier de données changent :

```bash
curl -LsSf https://astral.sh/uv/install.sh | sh
git clone <adresse-du-dépôt> && cd <dossier-cloné>
mkdir -p ~/.local/share/wavestack/models
curl -L -o ~/.local/share/wavestack/models/Qwen3.5-2B-Q4_K_M.gguf \
  https://huggingface.co/unsloth/Qwen3.5-2B-GGUF/resolve/main/Qwen3.5-2B-Q4_K_M.gguf
uv run wavestack
```

- **Dossier de données** : `~/.local/share/wavestack` (sous macOS aussi), au lieu de
  `%LOCALAPPDATA%\WaveStack`.
- **Linux** : x86_64 et ARM64. Les tests de bout en bout du projet tournent sous Linux.
- **macOS** : puces Apple seulement (le moteur `llama-cpp-python` n'est publié que pour
  `arm64`), et non vérifié sur un vrai poste à ce jour.
- **Le reste de la documentation** donne les commandes en PowerShell : remplacez
  `%LOCALAPPDATA%\WaveStack` par `~/.local/share/wavestack` et `setx NOM valeur` par un
  `export NOM=valeur` dans votre profil de shell.

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

## Premier lancement et diagnostic

Au lancement, WaveStack vérifie la mémoire disponible, la présence d'un modèle GGUF déjà sur le
poste, l'accès réseau et la disponibilité du port — chaque résultat s'affiche en français dans le
terminal et sur la page de diagnostic. Si aucun modèle n'est trouvé, la page propose de saisir le
chemin d'un fichier `.gguf` (partage, clé USB, cache Hugging Face, LM Studio, Ollama).

### Page ouverte au lancement

- Au premier lancement sur le poste, le navigateur s'ouvre sur le diagnostic
  (`http://127.0.0.1:8420/diagnostic`) au bout d'une seconde, pour voir défiler les vérifications.
- Aux lancements suivants, il s'ouvre une fois le diagnostic terminé : sur l'interface principale
  (`/`) si tout est prêt, sinon sur le diagnostic. Si le diagnostic dure plus de 30 s, le
  diagnostic s'ouvre.
- Si WaveStack tourne déjà, la commande ouvre l'interface principale quand l'instance est prête,
  sinon le diagnostic.
- Le diagnostic reste accessible par l'indicateur de modèle de la barre haute et par le lien
  « Diagnostic » de la barre de navigation, en haut de chaque page.

### Premier lancement long sur un poste qui a beaucoup de modèles

Avant de proposer un choix, le diagnostic teste chaque fichier GGUF trouvé (dossier des modèles,
cache Hugging Face, LM Studio, Ollama), chacun dans un processus à part. Sur un poste qui a
beaucoup de modèles Ollama, comptez une dizaine de minutes (18 modèles le 2026-10-02) ; la page
dit « n modèles testés sur N ». Les résultats sont gardés dans `settings.json` : les lancements
suivants ne refont pas ces tests (sauf pour un fichier modifié).

Pour la suite (l'interface, les scénarios, les ateliers), voir le
[guide d'utilisation](guide.md).

## Derrière un proxy d'entreprise

- `UV_SYSTEM_CERTS=1` pour utiliser les certificats du système.
- `UV_PYTHON_INSTALL_MIRROR=<miroir>` si `github.com` est bloqué pour le téléchargement de Python.
- Domaines à autoriser : PyPI (`pypi.org`, `files.pythonhosted.org`), `abetlen.github.io`
  (roue CPU de `llama-cpp-python`), `github.com` et ses domaines de téléchargement,
  `huggingface.co` et `*.hf.co`, et `astral.sh` pour le script d'installation de `uv`.
- Pour llama-server, facultatif (voir [Obtenir llama-server sans droits d'administrateur](modeles.md#obtenir-llama-server-sans-droits-dadministrateur-windows)) :
  `api.github.com`, et les hôtes de téléchargement des releases GitHub,
  `objects.githubusercontent.com` et `release-assets.githubusercontent.com`.

Dans PowerShell, `$env:UV_SYSTEM_CERTS = "1"` vaut pour le terminal en cours ; `setx
UV_SYSTEM_CERTS 1` le garde pour les terminaux suivants.

Ces réglages de proxy concernent l'installation (via `uv`), pas WaveStack lui-même : une fois
lancée, l'application ne peut sortir que vers les hôtes de sa propre liste blanche (AD-15,
`wavestack.toml`, section `[net] allowed_hosts`). Pour autoriser un hôte supplémentaire (par
exemple un miroir interne de modèles), ajoutez-le dans `settings.json`, dans le dossier de
données (AD-20 : `%LOCALAPPDATA%\WaveStack` sous Windows, `~/.local/share/wavestack` ailleurs) :

```json
{ "net": { "allowed_hosts": ["mon-miroir-interne.exemple.com"] } }
```

Ce fichier surcharge `wavestack.toml` sans le modifier ; les hôtes en boucle locale
(`127.0.0.1`, `localhost`) et les hôtes de proxy détectés sont toujours autorisés.

## Mise à jour

`git pull` (ou un nouveau zip), puis `uv run wavestack`, qui resynchronise sur `uv.lock`. Si
vous utilisez un extra (ci-dessous), relancez aussi `uv sync` avec tous vos extras, par exemple
`uv sync --extra compression` : un `uv sync` sans un extra le retire.

## Extras optionnels

`uv run wavestack` seul n'installe pas ces dépendances ; ajoutez-les une fois, depuis le
dossier de WaveStack, en gardant tous les extras voulus dans la même commande :

```bash
uv sync --extra compression --extra rag-alt --extra greenops
```

| Extra | Ce qu'il active | Taille | Détails |
|---|---|---|---|
| `compression` | La brique Compression (Headroom) | ≈ 285 Mo | [Compression du contexte](guide.md#compression-du-contexte-headroom) |
| `rag-alt` | FAISS et LanceDB dans l'Atelier RAG | ≈ 390 Mo | [FAISS et LanceDB](guide.md#faiss-et-lancedb-extra-rag-alt) |
| `greenops` | L'empreinte des modèles locaux (CodeCarbon) | ≈ 150 Mo | [GreenOps](guide.md#greenops-empreinte-estimée-des-appels-au-modèle) |
