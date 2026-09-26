# WaveStack

WaveStack rend visible, brique par brique, ce qu'un harnais agentique ajoute à un LLM nu.
Démonstrateur pédagogique local, en français, sans GPU.

## Installation

**Prérequis :**
- Un accès au dépôt privé WaveStack et Git, ou une archive zip de WaveStack (téléchargée depuis le
  dépôt, ou remise par votre formateur sur un partage interne).
- [`uv`](https://docs.astral.sh/uv/) installé pour l'utilisateur courant (aucun droit administrateur requis).

**Procédure :**

```bash
git clone <adresse-du-dépôt>
cd <dossier-cloné>
uv run wavestack
```

Au premier clone, Git vous demande de vous authentifier auprès de l'hébergeur du dépôt. Avec
l'archive zip, décompressez-la, ouvrez un terminal dans le dossier obtenu, puis lancez
`uv run wavestack`.

`uv run` télécharge automatiquement Python 3.13 (dans le profil utilisateur, sans élévation) et
synchronise les dépendances depuis `uv.lock`. La commande ouvre ensuite un navigateur (voir
« Page ouverte au lancement »).

**Derrière un proxy d'entreprise :**
- `UV_SYSTEM_CERTS=1` pour utiliser les certificats du système.
- `UV_PYTHON_INSTALL_MIRROR=<miroir>` si `github.com` est bloqué pour le téléchargement de Python.
- Domaines à autoriser : PyPI (`pypi.org`, `files.pythonhosted.org`), `abetlen.github.io`
  (roue CPU de `llama-cpp-python`), `github.com` et ses domaines de téléchargement,
  `huggingface.co` et `*.hf.co`.

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

**Mise à jour :** `git pull` (ou un nouveau zip), puis `uv run wavestack`, qui resynchronise sur
`uv.lock`.

## Diagnostic de démarrage

Au lancement, WaveStack vérifie la mémoire disponible, la présence d'un modèle GGUF déjà sur le
poste, l'accès réseau et la disponibilité du port — chaque résultat s'affiche en français dans le
terminal et sur la page de diagnostic. Si aucun modèle n'est trouvé, la page propose de saisir le
chemin d'un fichier `.gguf` (partage, clé USB, cache Hugging Face, LM Studio, Ollama).

**Page ouverte au lancement.**
- Au premier lancement sur le poste, le navigateur s'ouvre sur le diagnostic
  (`http://127.0.0.1:8420/diagnostic`) au bout d'une seconde, pour voir défiler les vérifications.
- Aux lancements suivants, il s'ouvre une fois le diagnostic terminé : sur l'interface principale
  (`/`) si tout est prêt, sinon sur le diagnostic. Si le diagnostic dure plus de 30 s, le
  diagnostic s'ouvre.
- Si WaveStack tourne déjà, la commande ouvre l'interface principale quand l'instance est prête,
  sinon le diagnostic.
- Le diagnostic reste accessible par l'indicateur de modèle de la barre haute et par l'entrée
  « Diagnostic » du menu « Volets ▾ ».

## Changer de modèle

Le modèle se change sans relancer WaveStack, entre deux tours (pas pendant un tour ni une
validation) :
- **Barre haute** : le sélecteur « Changer de modèle… », à droite de l'indicateur de modèle,
  liste les fichiers GGUF du poste (« Sur ce poste », avec leur taille, par exemple « 2B », une
  fois le fichier sondé), les modèles d'un serveur local déjà lancé et les modèles cloud déclarés
  (« Réseau », grisés sans clé). Un modèle
  cloud affiche d'abord son avertissement. « Autre fichier ou clé API… » ouvre le diagnostic.
- **Diagnostic** : « Choisir » en face d'un fichier ou d'un modèle cloud, ou un chemin saisi.

Pendant le chargement, la barre haute et la Vue humain affichent « Chargement du modèle… » avec
un chronomètre ; l'envoi est désactivé. La conversation est conservée : l'historique est
reconstruit à chaque tour avec le gabarit du nouveau modèle, et « Rejouer le dernier prompt »
le fait jouer par le nouveau modèle. Une ligne « Modèle : … » marque dans la Vue humain le
premier tour d'un autre modèle, et « Comparer » affiche le modèle de chaque tour. Les briques
qui exigent une capacité absente (appel d'outils, raisonnement) passent indisponibles avec leur
raison, et redeviennent disponibles au retour à un modèle qui l'offre.

Le choix est mémorisé pour les lancements suivants une fois le chargement réussi. Si le nouveau
modèle ne se charge pas (fichier incompatible, erreur), WaveStack recharge le modèle précédent et
l'explique.

**Budget mémoire.** Un seul modèle est en mémoire à la fois : l'ancien est libéré avant le
chargement du nouveau (et avant la sonde d'un fichier jamais chargé). Avant de libérer quoi que
ce soit, WaveStack estime le coût du nouveau modèle (mémoire mesurée par la sonde, sinon taille
du fichier, plus son cache de contexte et une marge) et refuse le changement, chiffres à
l'appui, s'il dépasse le budget ; le modèle actif reste alors chargé. Le budget se règle dans
`wavestack.toml` (ou `settings.json`) :

```toml
[memory]
budget_mb = 4096      # mémoire de WaveStack et de ses processus enfants, modèle compris
load_margin_mb = 256  # marge ajoutée au coût estimé de chaque modèle local
```

## Modèle par défaut

Le modèle recommandé est **Qwen3.5-2B en Q4_K_M** (GGUF amont publié par unsloth, licence
Apache-2.0), validé sur le PC cible. WaveStack ne le télécharge pas : copiez le fichier `.gguf`
dans le dossier `models/` du dossier de données (`%LOCALAPPDATA%\WaveStack\models` sous
Windows, `~/.local/share/wavestack/models` ailleurs), ou indiquez son chemin au diagnostic.
Les GGUF `qwen35` d'Ollama ne se chargent pas avec llama-cpp-python 0.3.35 : préférez le fichier
amont, ou un serveur déjà lancé (section suivante).

## Utiliser un serveur déjà lancé (Ollama, llama-server)

WaveStack peut faire tourner le modèle d'un serveur local que **vous** avez lancé : Ollama ou
llama-server (llama.cpp). WaveStack ne lance, n'installe ni n'arrête jamais ces serveurs ; il
les interroge sur la boucle locale (`127.0.0.1`, sans proxy), aux ports de `wavestack.toml` :

```toml
[net.loopback_ports]
ollama = 11434
llama_server = 8080

[model_servers]
connect_timeout_s = 2   # connexion au serveur
read_timeout_s = 300    # lecture de la réponse (le premier appel d'Ollama charge le modèle)
```

Lancez le serveur avant WaveStack, par exemple `ollama serve`, ou
`llama-server -m C:\modeles\Qwen3.5-2B-Q4_K_M.gguf --port 8080`. Au diagnostic, chaque modèle
servi apparaît avec l'étiquette « Local », son serveur, son adresse et sa mémoire ; « Choisir »
le charge, comme un fichier. Il est aussi dans le sélecteur de la barre haute
(« Local · Ollama · … », « Local · llama-server · … »). Un modèle servi n'est jamais choisi
d'office ; un choix mémorisé est repris au lancement si le serveur le sert encore.

**Le harnais construit toujours le texte.** Le gabarit de conversation du modèle est appliqué
par WaveStack, comme pour un fichier : le serveur reçoit le texte déjà rendu, jamais des
messages au format chat.
- **llama-server** reçoit les tokens du prompt (`/completion`) et tokenise lui-même
  (`/tokenize`) : la jauge compte exactement ce que lit le modèle. La fenêtre est la plus petite
  de la fenêtre configurée, du contexte natif et du contexte du serveur (`-c`).
- **Ollama** reçoit le texte en mode `raw` (`/api/generate`), avec `num_ctx` égal à la fenêtre
  effective. WaveStack compte les tokens avec le tokenizer lu dans le fichier GGUF du modèle,
  dans le dossier d'Ollama (`OLLAMA_MODELS`). Un modèle sans GGUF lisible y est « incompatible ».
  Si Ollama annonce un autre nombre de tokens que le harnais, ou renvoie un raisonnement séparé
  (`thinking`), une erreur « transparence réduite » l'explique dans le journal ; le tour
  continue.

**Mémoire.** En mode serveur, aucun modèle ne reste chargé dans WaveStack ; la mémoire du modèle
servi compte dans le budget `[memory]` (celle qu'annonce Ollama une fois le modèle chargé, sinon
la taille du fichier). En quittant un modèle Ollama (changement de modèle ou fermeture de
WaveStack), WaveStack demande à Ollama de le décharger (`keep_alive: 0`). Le schéma
d'architecture dessine ce modèle hors du cadre Harnais, sur le poste de travail : c'est un
processus distinct.

## RAG : corpus de démonstration et index

La brique RAG cherche dans huit textes fictifs (`content/corpus/`, l'organisation imaginaire
« Exemplia ») avec un petit modèle d'embedding local, nommé dans la seule section
`[rag.embedding]` de `wavestack.toml` (Granite Embedding 107M multilingue, GGUF Q8_0, 121 Mo,
verdict provisoire de la story 12). Les tailles sont en Mo décimaux (1 Mo = 1 000 000 octets),
sur la carte comme ici.

Sur une installation neuve, tout se fait depuis la carte RAG, sans ligne de commande :

1. « Télécharger le modèle d'embedding » : le fichier va dans `models/embedding/` du dossier de
   données (sans réseau, copiez-le à la main à cet endroit, puis cliquez de nouveau) ;
2. « Construire l'index » : le corpus est découpé et indexé sur le poste, dans
   `data/rag_index.sqlite` (sqlite-vec), avec une progression et « Arrêter ».

Le script fait la même chose, et peut committer l'index avec le dépôt :

```bash
uv run python scripts/build_rag_index.py                  # modèle de [rag.embedding]
uv run python scripts/build_rag_index.py --download       # télécharge d'abord le modèle
uv run python scripts/build_rag_index.py --model C:\chemin\modele.gguf
```

`--model` n'accepte que le fichier déclaré (même taille, même sha256 s'il est renseigné).
L'index garde l'identifiant, les dimensions et le fichier de son modèle, et une empreinte du
corpus : un autre modèle, un corpus modifié ou un autre `[rag] chunk_max_chars` rendent la
brique indisponible, avec la raison, et la carte propose « Construire l'index ». Le dossier
`models/embedding/` n'est jamais proposé comme modèle de conversation.

## Modèle cloud (Groq, Mistral)

Un modèle cloud compatible OpenAI peut remplacer le SLM local : plus rapide, meilleur avec les
outils, et il montre un vrai appel hors du poste. Les préréglages Groq (`openai/gpt-oss-120b`) et
Mistral (`mistral-small-latest`) sont déclarés dans `wavestack.toml` ; Google, NVIDIA et
OpenRouter y figurent en exemples commentés, avec leur avertissement.

1. **Clé.** Créez une clé API dans la console du fournisseur, puis collez-la sur la page de
   diagnostic, dans la ligne du modèle (« Enregistrer la clé »). Elle est stockée sur ce poste
   seulement (`api_keys.json` dans le dossier de données), jamais affichée ni tracée, et envoyée au
   seul hôte déclaré. Si l'adresse du fournisseur change, la clé est à ressaisir.

   **Ou par variable d'environnement.** Chaque préréglage nomme une variable (`key_env`) :
   `GROQ_API_KEY` pour Groq, `MISTRAL_API_KEY` pour Mistral. Sous Windows, sans droits
   administrateur :

   ```bat
   setx GROQ_API_KEY votre-clé
   ```

   `setx` n'agit que sur les **nouveaux** terminaux : fermez celui-ci, ouvrez-en un autre, puis
   `uv run wavestack`. La ligne du modèle indique alors « Clé fournie par la variable
   GROQ_API_KEY » (le nom seul, jamais la valeur). Une clé saisie au diagnostic passe avant la
   variable ; une variable vide compte comme absente.

   `setx` enregistre la clé **en clair** dans l'environnement de l'utilisateur
   (`HKCU\Environment`) : tout programme lancé sous votre session peut la lire. Un terminal
   intégré à un éditeur (VS Code, par exemple) ne la voit qu'après le redémarrage complet de
   l'éditeur, pas seulement du terminal.
2. **Tester avant chaque séance.** « Tester » envoie une invite et un outil fixes, sans vos données
   (deux appels au plus), et affiche la réponse, l'appel d'outil reçu et le débit. Les offres
   gratuites et leurs quotas changent souvent : seul ce test prouve que la clé et le préréglage
   fonctionnent le jour J.
3. **Choisir.** « Choisir » affiche l'avertissement (ce qui part, ce qu'en fait le fournisseur, ce
   que le harnais ne voit plus) ; « Utiliser ce modèle » le confirme. Le choix est repris aux
   lancements suivants, sans nouvel avertissement. Choisi après le chargement d'un modèle, il le
   remplace sans relance (voir « Changer de modèle »).

**Fenêtre de Groq.** Son quota gratuit (8 000 tokens par minute) limite la fenêtre à 4 000 tokens,
dont 1 536 réservés à la réponse : il reste **2 464 tokens utilisables**. Les scénarios lourds
(MCP en documentation complète, longue conversation) dépassent : passez en lazy loading, videz la
conversation, ou préférez Mistral.

**Revenir au modèle local.** Choisissez un fichier GGUF dans le sélecteur de la barre haute, ou
cliquez sur « Choisir » en face d'un fichier sur la page de diagnostic : le modèle local est
rechargé sans relance, conversation gardée.

**Hôtes à autoriser** sur le réseau de l'entreprise : `api.groq.com` et `api.mistral.ai` (plus
l'hôte de tout modèle ajouté dans `settings.json`).

**Ajouter un modèle.** Les exemples Google, NVIDIA et OpenRouter de `wavestack.toml` sont en TOML :
recopiez-en les champs, en JSON, dans `settings.json` (dossier de données, WaveStack arrêté). Une
entrée nouvelle doit être complète :

```json
{
  "cloud": {
    "models": [
      {
        "id": "openrouter",
        "provider": "OpenRouter",
        "base_url": "https://openrouter.ai/api/v1",
        "model": "meta-llama/llama-3.3-70b-instruct:free",
        "tools": true,
        "context": 131072,
        "hosting_fr": "Selon le fournisseur routé par OpenRouter",
        "training": "yes",
        "notes_fr": "Catalogue gratuit instable : vérifiez le nom du modèle avant la séance."
      }
    ]
  }
}
```

Une entrée de même `id` qu'un préréglage le modifie champ par champ (par exemple
`{"id": "groq", "tpm": 6000}`), et `"enabled": false` le masque.

Deux champs facultatifs :
- `key_env` : nom de la variable d'environnement qui fournit la clé (lettres majuscules,
  chiffres et `_`), jamais la clé elle-même.
- `min_interval_s` : délai minimal, en secondes (au plus 60), entre deux envois au même modèle,
  tour ou « Tester ». Mistral gratuit refuse (429) deux requêtes à moins d'une seconde : son
  préréglage vaut `1`. Si des 429 « par seconde » persistent, augmentez-le, par exemple
  `{"id": "mistral", "min_interval_s": 1.5}`. L'attente n'entre pas dans les durées affichées, et
  un appel refusé n'est jamais réessayé.

## Développement

```bash
uv sync
uv run ruff check .
uv run ruff format .
uv run pytest
```

Les tests marqués `model` nécessitent un vrai fichier GGUF sur le poste ; ils sont sautés par
défaut.
