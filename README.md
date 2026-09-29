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
`uv.lock`. Si vous utilisez la brique Compression, relancez aussi `uv sync --extra compression`
(voir « Compression du contexte »).

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

## Programme de formation

Le sélecteur de scénario de la barre haute liste six modules, dans l'ordre des briques, soit
5 h 15 au total, à répartir sur plusieurs séances :

| Module | Durée | Scénarios |
|---|---|---|
| 1. Du LLM nu au harnais | 60 min | LLM nu, raisonnement, mémoire courte, prompt système, mémoire globale |
| 2. Outils | 45 min | outils natifs, outils réseau |
| 3. RAG | 45 min | RAG, RAG avec reranking |
| 4. MCP | 45 min | documentation complète, lazy loading |
| 5. Skills et hooks | 60 min | skills, Caveman, hooks |
| 6. Sous-agent et compression | 60 min | sous-agent, compression du contexte |

Lancer le premier scénario d'un module active les briques des modules précédents et restaure la
mémoire globale de démonstration : on peut reprendre la formation à n'importe quel module, dans
un état reproductible. Deux exceptions, pour tenir dans la fenêtre de contexte : le raisonnement
reste éteint après le module 1, et le RAG est éteint pendant « MCP en documentation complète ».

Le groupe « Transverses et métier » suit les modules : « Où vont mes données ? », puis trois
scénarios métier, fictifs, pour que chaque practice imagine ses usages. Leur consigne, projetée,
se termine par le message à retenir ; la réponse attendue, ci-dessous, est pour le formateur.

| Scénario | Durée | Réponse attendue |
|---|---|---|
| SOC : journal d'audit et garde-fou | 20 min | Un seul incident, le compte adm.leroy : connexion depuis un pays inhabituel à 02:14 UTC (accès initial, comptes valides), auto-ajout aux « Admins du domaine » à 02:15 (élévation de privilèges, manipulation de compte), antivirus arrêté à 02:21 (contournement des défenses), 2,3 Go sortants à 02:40 (exfiltration), pendant une fenêtre de maintenance où des alertes étaient en sourdine. Les échecs de svc-sauvegarde sont à investiguer à part. Au second prompt, H1 bloque l'inventaire des comptes à privilèges : l'agent doit escalader vers un analyste habilité. |
| IAM : Entra ID avec Microsoft Learn | 15 min | MFA des administrateurs : une stratégie d'accès conditionnel qui cible les rôles d'administrateur et exige l'authentification multifacteur (modèle « Exiger l'authentification multifacteur pour les administrateurs »), ou les paramètres de sécurité par défaut pour un petit locataire. PIM : rôles attribués « éligibles », activés à la demande pour une durée limitée, avec justification, MFA et, au besoin, approbation. La réponse cite ses liens Microsoft Learn. |
| Souveraineté : où partent les requêtes ? | 15 min | Deux flux sortent du poste : la recherche vers data.gouv.fr (opérateur public français) et celle vers Microsoft Learn (éditeur américain, soumis au Cloud Act même en Europe). Chaque requête révèle le sujet de la mission. Hébergement et qualification (SecNumCloud) de chaque serveur restent à vérifier ; le modèle local ne sort pas du poste, un modèle cloud y ajouterait un troisième flux. |

IAM et Souveraineté demandent un accès à `learn.microsoft.com` et `mcp.data.gouv.fr` : sur le
réseau d'une entreprise, faites autoriser ces deux hôtes par le proxy avant la séance. Sans
réseau, chaque serveur est dessiné indisponible avec sa raison et le tour se poursuit sans lui.

Un nouveau scénario s'ajoute dans `content/scenarios.yaml`, sans modifier le code : un scénario
métier va dans `transverse`, avec un titre « Métier … », sa durée et son message « À retenir »
dans la consigne. Les tests du programme (`tests/test_program.py`) vérifient ces règles, le
cumul des modules et l'adéquation de chaque scénario à la fenêtre, sans liste de scénarios à
mettre à jour. Pour qu'ils comptent la documentation réelle des serveurs MCP publics, lancez une
fois sur un poste relié au réseau `uv run python scripts/snapshot_mcp.py` : il enregistre leurs
outils dans `content/mcp_snapshots/`.

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
raison, et redeviennent disponibles au retour à un modèle qui l'offre. Un scénario qui en veut
une le signale sous sa consigne, avec la raison : par exemple, la famille Llama (Llama 3.2 via
Ollama) n'a pas de format d'appel d'outils connu de WaveStack, donc pas d'outils, de MCP, de
skills ni de sous-agent.

Le choix est mémorisé pour les lancements suivants une fois le chargement réussi. Si le nouveau
modèle ne se charge pas (fichier incompatible, erreur), WaveStack recharge le modèle précédent et
l'explique.

**Budget mémoire.** Un seul modèle est en mémoire à la fois : l'ancien est libéré avant le
chargement du nouveau (et avant la sonde d'un fichier jamais chargé). Avant de libérer quoi que
ce soit, WaveStack estime le coût du nouveau modèle (mémoire mesurée par la sonde, sinon taille
du fichier, plus son cache de contexte et une marge) et refuse le changement, chiffres à
l'appui, s'il dépasse le budget ; le modèle actif reste alors chargé. La sonde charge le
fichier une fois, dans un processus à part, avec un contexte de la taille de la fenêtre, et lui
fait lire un premier lot de 512 tokens : la mémoire qu'elle mesure comprend ses poids, le cache
de contexte de toute la fenêtre (llama.cpp le réserve et l'initialise en créant le contexte) et
les tampons de calcul d'un lot. Cela prend quelques dizaines de secondes de plus, une seule fois
par fichier ; un fichier sondé par une version précédente de WaveStack est mesuré de nouveau au
lancement s'il est le modèle enregistré, sinon quand on le choisit. Une sonde à court de
mémoire ou de temps n'est pas retenue contre le fichier. Avec le budget de 4 Go, Qwen3.5-4B
devrait être refusé : 4,27 Go mesurés après 3 000 tokens lors du test du 2026-09-27 (à vérifier
sur PC avec la nouvelle sonde). Pour l'utiliser malgré tout : fermez des applications,
relevez `budget_mb` (le plafond) et au besoin `budget_ram_ratio`, ou passez en
`budget_mode = "fixed"` avec un `budget_mb` suffisant, puis relancez WaveStack (le budget est
calculé au lancement).

Le refus dit aussi ce qu'occupe WaveStack sans le modèle actif : la mémoire mesurée juste avant
la création de son moteur (après la libération du précédent), ou davantage si d'autres
composants se sont chargés depuis (embedding, reranker). Les poids d'un modèle sont projetés en
mémoire depuis le fichier et peuvent être bien moins présents que ce que la sonde a mesuré :
retrancher la mesure de la sonde pouvait donner « 0 Mo », ce que la mesure d'avant le moteur
évite.

**Budget calculé au lancement.** Par défaut (`budget_mode = "dynamic"`), le budget vaut le plus
petit de deux nombres : le plafond `budget_mb` (4 096 Mo, NFR-2) et 60 % de la RAM disponible
au lancement (`budget_ram_ratio`). Il est calculé une seule fois, au lancement, puis ne bouge
plus pendant la séance. La ligne « memory » du diagnostic donne la RAM du poste, la RAM
disponible, la part retenue, le plafond et le budget ; chaque refus donne le même budget et son
calcul en bref, par exemple « budget de 4,0 Go (= plafond [memory] budget_mb) » ou « budget de
2,9 Go (= 60 % des 4,9 Go de RAM disponibles au lancement) » ; le diagnostic donne le calcul
complet (« plafond [memory] budget_mb de 4 096 Mo, plus petit que 60 % des 9 600 Mo de RAM
disponibles au lancement (5 760 Mo), sur 16 071 Mo »). Le budget ne descend jamais sous
512 Mo. Quand la RAM
disponible fait descendre le budget sous le plafond, le diagnostic l'avertit (sans bloquer) :
fermez des applications (navigateur, messagerie, visioconférence) puis relancez WaveStack. Si
la RAM ne peut pas être lue, le budget est le plafond. `budget_mode = "fixed"` garde un budget
fixe de `budget_mb`, quelle que soit la RAM (« valeur fixe » dans le calcul) ; le diagnostic
avertit s'il dépasse la RAM disponible.

« Arrêter » (à droite du champ de message) interrompt un chargement en cours. Pendant la sonde
d'un fichier jamais chargé, il arrête le processus de la sonde aussitôt : rien n'est retenu
contre le fichier, et le modèle précédent revient. Pendant un chargement dans WaveStack, il
prend effet à la fin de l'étape (libération ou chargement, que llama.cpp ne sait pas
interrompre), puis WaveStack recharge le modèle précédent. La sonde du diagnostic de lancement,
elle, n'a pas de bouton « Arrêter ». Le budget se règle dans `wavestack.toml` (ou
`settings.json`) :

```toml
[memory]
budget_mode = "dynamic"  # ou "fixed"
budget_mb = 4096         # plafond (dynamic) ou valeur (fixed), en Mo, modèle compris
budget_ram_ratio = 0.6   # part de la RAM disponible au lancement (de 0,1 à 0,9)
load_margin_mb = 256     # marge ajoutée au coût estimé de chaque modèle local
```

## Modèle par défaut

Le modèle recommandé est **Qwen3.5-2B en Q4_K_M** (GGUF amont publié par unsloth, licence
Apache-2.0), validé sur le PC cible. WaveStack ne le télécharge pas : copiez le fichier `.gguf`
dans le dossier `models/` du dossier de données (`%LOCALAPPDATA%\WaveStack\models` sous
Windows, `~/.local/share/wavestack/models` ailleurs), ou indiquez son chemin au diagnostic.
Un blob GGUF d'Ollama choisi comme un fichier peut être refusé par llama-cpp-python 0.3.35
(fichier incompatible, raison expliquée, modèle précédent gardé) : préférez le fichier amont.
Servi par Ollama lui-même, le même modèle fonctionne avec un Ollama récent (`qwen3.5:2b` au test
du 2026-09-27), ou par llama-server (section suivante).

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
`llama-server -m C:\modeles\Qwen3.5-2B-Q4_K_M.gguf --port 8080 -np 1 -c 4096`. **Donnez
toujours `-c 4096` à llama-server** (la fenêtre de WaveStack, `[context] window`) : sans `-c`,
il prend tout le contexte natif du modèle (262 144 tokens pour Qwen3.5) et réserve dès son
lancement la mémoire de ce contexte entier, quelle que soit la longueur des conversations
(5 137 Mo mesurés pour le 2B lors du test du 2026-09-27, pour un fichier de 1,28 Go). Avec
plusieurs emplacements (`-np N`), `-c` est partagé entre eux : gardez `-np 1`. Le diagnostic
signale un contexte trop grand et conseille la commande à relancer. Au diagnostic, chaque
modèle servi apparaît avec l'étiquette « Local », son serveur, son adresse et sa mémoire ;
« Choisir » le charge, comme un fichier. Il est aussi dans le sélecteur de la barre haute
(« Local · Ollama · … », « Local · llama-server · … »). Un modèle servi n'est jamais choisi
d'office ; un choix mémorisé est repris au lancement si le serveur le sert encore. Les modèles
« cloud » d'Ollama (`…-cloud`), qui tournent chez ollama.com, ne sont pas listés.

**Le harnais construit toujours le texte.** Le gabarit de conversation du modèle est appliqué
par WaveStack, comme pour un fichier : le serveur reçoit le texte déjà rendu, jamais des
messages au format chat. L'échantillonnage est celui du modèle en processus (température 0,7,
`top_p` 0,8, `top_k` 20, sans pénalité de répétition, graine aléatoire), envoyé à chaque appel.
- **llama-server** reçoit les tokens du prompt (`/completion`) et tokenise lui-même
  (`/tokenize`) : la jauge compte exactement ce que lit le modèle. C'est la voie la plus sûre.
  La fenêtre est la plus petite de la fenêtre configurée, du contexte natif et du contexte d'un
  emplacement du serveur : avec plusieurs emplacements (`-np`), llama-server partage `-c`
  entre eux, d'où une fenêtre « serveur » plus petite que `-c`. Lancez-le avec `-np 1`.
- **Ollama** reçoit le texte en mode `raw` (`/api/generate`), avec `num_ctx` égal à la fenêtre
  effective. WaveStack compte les tokens avec le tokenizer lu dans le fichier GGUF du modèle,
  dans le dossier d'Ollama (`OLLAMA_MODELS`), par llama-cpp-python : un modèle sans GGUF
  lisible y est « incompatible », et un tokenizer que llama-cpp-python ne sait pas lire est
  refusé avec la raison, le modèle précédent restant actif. Qwen3.5 (`qwen3.5:2b`) passe avec un
  Ollama récent (test du 2026-09-27). Avec un Ollama trop ancien pour servir l'architecture
  `qwen35`, le modèle est accepté, puis le premier tour échoue sur une erreur brute « HTTP 500 »
  d'Ollama : mettez Ollama à jour, ou servez ce modèle avec llama-server. Si Ollama lit plus
  de tokens que le harnais n'en a comptés, ou renvoie un raisonnement séparé (`thinking`), une
  erreur « transparence réduite » l'explique dans le journal ; s'il en lit moins, c'est son
  cache (début du prompt identique à l'appel précédent), noté pour information. Le tour
  continue dans les deux cas.

**Mémoire.** En mode serveur, aucun modèle ne reste chargé dans WaveStack (seul le tokenizer
d'un modèle Ollama y est ouvert, sans les poids). Le budget `[memory]` compte le modèle servi :
- déjà en mémoire (le modèle de llama-server, un modèle qu'Ollama a déjà chargé) : compté pour
  ce qu'il occupe, jamais refusé, puisque le choisir n'ajoute rien. Pour llama-server, c'est la
  taille de son fichier plus son cache de contexte pour tout son contexte (`n_ctx`, lu dans
  `/props`), la taille d'un token du cache étant lue dans l'en-tête du fichier GGUF (sans les
  poids, sans llama.cpp) ; si WaveStack ne peut pas lire ce fichier, le chiffre affiché le dit
  et ne compte que la taille du fichier. Pour Ollama, la mémoire qu'il annonce (`/api/ps`) ;
- pas encore chargé par Ollama : compté pour la taille de son fichier plus son cache de
  contexte (f16) à la fenêtre, lu dans l'en-tête du fichier (la ligne du diagnostic), plus la
  marge `load_margin_mb` au moment du choix (elle couvre aussi le tokenizer), et refusé,
  chiffres à l'appui, s'il dépasse le budget. Jamais la mémoire mesurée par la sonde de son
  fichier : elle mesure llama-cpp-python dans un processus de WaveStack (tampons de calcul
  compris), pas Ollama. Par exemple `llama3.2:3b` (2,0 Go) : ≈ 2,3 Go au diagnostic, ≈ 2,6 Go
  avec la marge, sous un budget de 4 096 Mo. Un cache quantifié ou `OLLAMA_NUM_PARALLEL` > 1
  dans Ollama changent sa mémoire réelle (à vérifier sur PC).

En quittant un modèle Ollama (changement de modèle ou fermeture de WaveStack), WaveStack demande
à Ollama de le décharger (`keep_alive: 0`), seulement s'il l'a fait charger : un modèle
qu'Ollama avait déjà en mémoire (utilisé par un autre programme) n'est jamais déchargé. Le
schéma d'architecture dessine le modèle servi hors du cadre Harnais, sur le poste de travail :
c'est un processus distinct.

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

### Reranking (sous-option de la brique RAG)

La case « Reranking » de la carte RAG ajoute une seconde passe : la recherche retient
`[rag] rerank_candidates` candidats (8 par défaut, de `top_k` à 20), un reranker local les note
un par un avec la question, et seuls les `[rag] top_k` premiers (3 par défaut, 20 au plus)
entrent dans le message. L'étape « Reranking » d'Orchestration montre l'ordre avant et après.

- **Modèle.** Il est nommé dans la seule section `[rag.reranker]` de `wavestack.toml` : BGE
  Reranker v2 M3, GGUF Q4_K_M, 438 Mo, Apache-2.0. C'est le verdict **provisoire** de la
  story 12 : sa latence et sa mémoire restent à mesurer sur le PC cible.
- **Mémoire.** Il est compté dans le budget mémoire (`[memory]`, calculé au lancement) pour la
  taille de son fichier plus `[memory] load_margin_mb` (environ 690 Mo), ou pour
  `measured_rss_mb` une fois mesuré.
  Refusé, seule la case est indisponible, avec la raison chiffrée.
- **Lenteur.** Un passage du reranker par candidat, avant le premier appel au modèle : si
  l'étape « Reranking » est trop lente sur le poste, baissez `[rag] rerank_candidates` dans
  `settings.json`.
- **Sans le modèle,** la case propose « Télécharger le modèle de reranking » (fichier dans
  `models/reranker/`, ou copie à la main au même endroit) et le RAG fonctionne sans reranking.
  Le dossier `models/reranker/` n'est jamais proposé comme modèle de conversation.

## Compression du contexte (Headroom)

La brique Compression passe les gros résultats d'outils et les extraits RAG à
[Headroom](https://pypi.org/project/headroom-ai/) (`headroom-ai` 0.38.0, Apache-2.0), avant
l'appel au modèle. C'est une dépendance optionnelle, non installée par `uv run wavestack` seul :
installez-la une fois, depuis le dossier de WaveStack, avant une séance qui l'utilise.

```bash
uv sync --extra compression
uv run wavestack
```

- **Installation et mise à jour.** Relancez `uv sync --extra compression` après chaque mise à
  jour. Attention : un `uv sync` sans `--extra compression` retire Headroom et ses dépendances
  (`uv run wavestack`, lui, les garde).
- **Réseau à l'installation.** L'extra se télécharge depuis PyPI (`pypi.org`,
  `files.pythonhosted.org`) : environ 40 paquets, 285 Mo sur disque. Ensuite, Headroom tourne
  hors ligne, sans télémétrie ni modèle d'apprentissage automatique (variables posées par
  WaveStack au lancement).
- **Poste verrouillé.** headroom-ai apporte deux binaires natifs non signés (`_core.pyd` et
  l'exécutable `ast-grep`) : AppLocker ou WDAC peuvent les bloquer. La carte de la brique dit
  alors pourquoi elle est indisponible ; le reste de WaveStack fonctionne.
- **Sans l'extra,** la carte de la brique est indisponible et donne la commande d'installation.
- **Réglages.** Headroom ajoute 84 Mo de mémoire au pic sur le PC cible (107 Mo sous Linux),
  avec le comptage `gpt-4` ; `[compression] cost_mb` en compte 110, contrôlés par le budget.
  Un texte plus court que
  `[compression] min_chars` (300 caractères) n'est pas compressé. La brique n'a d'effet
  qu'avec Outils, MCP ou RAG : sans eux, rien à compresser.

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
  un appel refusé n'est jamais réessayé. Un 429 au premier appel de « Tester », premier envoi
  de la séance, ne vient pas de l'espacement : le quota du compte est épuisé, et
  `min_interval_s` n'y peut rien. Lisez d'abord le message du fournisseur dans le journal
  (capacité saturée ou quota), puis vérifiez le quota dans la console Mistral.

## Développement

```bash
uv sync --extra compression   # l'extra couvre le test de l'adaptateur Headroom
uv run ruff check .
uv run ruff format .
uv run pytest
```

Les tests marqués `model` nécessitent un vrai fichier GGUF sur le poste ; ils sont sautés par
défaut.
