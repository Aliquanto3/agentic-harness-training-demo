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
- Pour llama-server, facultatif (voir « Obtenir llama-server sans droits d'administrateur ») :
  `api.github.com`, et les hôtes de téléchargement des releases GitHub,
  `objects.githubusercontent.com` et `release-assets.githubusercontent.com`.

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
un état reproductible. Deux exceptions, que la consigne rappelle : le raisonnement reste éteint
après le module 1 (sa réserve de sortie prend de la place et allonge chaque tour), et le RAG
après le module 3 (ses extraits sur Exemplia sont hors sujet dans les démonstrations suivantes,
trompent un petit modèle et font relire tout le contexte à chaque tour). Rallumez-les à la main
pour les montrer.

Pour un petit modèle local, les prompts suggérés nomment l'outil ou le skill attendu (par
exemple `load_skill` et `meeting_minutes`, ou `mslearn__microsoft_docs_search`) : un modèle
plus gros fait seul le lien entre la demande et l'outil, ce qui se montre avec un modèle cloud.
Quand une action forcée existe, la consigne la donne en secours : « Déclencher le skill »
(Skills), « Forcer l'appel » sur « Lecture de fichier » avec un préréglage (Compression, SOC),
« Charger la documentation » en lazy loading (Lazy loading, Souveraineté), puis « Rejouer le
dernier prompt ». Un appel d'outil MCP ne se force pas : dans « MCP en documentation
complète », IAM, et pour la recherche elle-même en lazy loading, l'appel reste au modèle, et
la consigne dit quoi montrer s'il ne vient pas.

Le groupe « Transverses et métier » suit les modules : « Où vont mes données ? » (outils locaux,
serveur MCP local et data.gouv.fr actifs dès le lancement, en lazy loading ; décochez puis
recochez data.gouv.fr pour voir le flux sortant disparaître puis revenir), puis trois
scénarios métier, fictifs, pour que chaque practice imagine ses usages. Leur consigne, projetée,
se termine par le message à retenir ; la réponse attendue, ci-dessous, est pour le formateur.

| Scénario | Durée | Réponse attendue |
|---|---|---|
| SOC : journal d'audit et garde-fou | 20 min | Un seul incident, le compte adm.leroy : connexion depuis un pays inhabituel à 02:14 UTC (accès initial, comptes valides), auto-ajout aux « Admins du domaine » à 02:15 (élévation de privilèges, manipulation de compte), antivirus arrêté à 02:21 (contournement des défenses), 2,3 Go sortants à 02:40 (exfiltration), pendant une fenêtre de maintenance où des alertes étaient en sourdine. Les échecs de svc-sauvegarde sont à investiguer à part. Au second prompt, H1 bloque l'inventaire des comptes à privilèges : l'agent doit escalader vers un analyste habilité, comme le prompt le lui demande ; s'il ne le fait pas (fréquent avec un petit modèle), le formateur conclut : l'agent n'a pas ce privilège, la décision revient à un analyste habilité. |
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
  liste les fichiers GGUF du poste, les modèles d'un serveur local déjà lancé et les modèles
  cloud déclarés (grisés sans clé). Un modèle cloud affiche d'abord son avertissement. « Autre
  fichier ou clé API… » ouvre le diagnostic.
- **Diagnostic** : « Choisir » en face d'un fichier ou d'un modèle cloud, ou un chemin saisi.

**Lire le sélecteur.** Sa deuxième ligne est une légende : chaque option commence par où tourne
le modèle, puis qui le sert :
- « Local · fichier » : un fichier GGUF chargé par WaveStack lui-même (blob Ollama compris) ;
- « Local · Ollama », « Local · llama-server » : un serveur déjà lancé sur ce poste, processus
  distinct de WaveStack ;
- « RÉSEAU · {fournisseur} » : un modèle cloud, hors du poste.

Les modèles sont regroupés par hébergement puis par éditeur (« Sur ce poste · Qwen (Alibaba) »,
« Sur ce poste · Llama (Meta) », …, « Réseau · Autres éditeurs »), du plus petit au plus grand ;
la taille affichée est celle en paramètres (« 2B »), lue dans l'en-tête du fichier, dans les
détails d'Ollama ou dans le nom. L'éditeur est reconnu par `content/models/publishers.yaml`
(architecture, puis nom) ; un modèle inconnu va dans « Autres éditeurs ».

**Tableau des modèles.** L'avant-dernière entrée du sélecteur, « Tableau des modèles et de leurs
capacités… » (bouton « Ouvrir le tableau »), ouvre la page `/models`, aussi atteinte par
l'onglet « Modèles » du diagnostic. Pour chaque modèle : éditeur, taille (paramètres et octets),
hébergement, fenêtre de contexte que WaveStack utiliserait, appel d'outils (oui, non, inconnu) et
raisonnement (jamais, toujours, activable ou inconnu), avec la raison. Ces capacités sont lues
comme au chargement, par les mêmes règles que les cartes des briques, sans charger ni sonder le
modèle : l'en-tête du fichier GGUF (lu une fois, puis mémorisé), le gabarit de llama-server, la
déclaration d'un modèle cloud. « Inconnu » veut dire que rien ne permet de le dire avant le
chargement : un modèle Ollama dont le fichier est introuvable, un gabarit sans variable de
raisonnement qui contient `<think>` (le modèle raisonne peut-être de lui-même, WaveStack ne sait
ni l'allumer ni l'éteindre).

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

## Fenêtre de contexte

La fenêtre de contexte vaut **4 096 tokens par défaut** : les scénarios sont conçus pour elle.
Elle se règle dans la barre haute, par le bouton « Fenêtre 4 096 ▾ » juste après la jauge, à
**4 096, 8 192 ou 16 384 tokens** (par exemple quand les trois serveurs MCP en lazy loading font
déborder 4 096 tokens après le chargement d'une documentation). Le panneau donne, pour chaque
choix et pour le modèle actif, ce que la fenêtre coûte :
- **le cache de contexte** en mémoire (la taille d'un token du cache, lue par la sonde ou dans
  l'en-tête du fichier, multipliée par la fenêtre, en f16 : une borne haute) ; « réservé par
  llama-server (-c N), inchangé » pour un modèle de llama-server, « chez le fournisseur, aucune
  mémoire sur ce poste » pour un modèle cloud ;
- **le temps de lecture** d'une fenêtre pleine, au débit mesuré sur le dernier appel local qui a
  lu au moins 64 tokens : une borne basse (le débit baisse quand le contexte s'allonge), signalée
  au-delà des 30 s visées au premier token ; « pas encore mesuré » avant le premier message ;
- **la borne**, quand le modèle ne peut pas prendre toute la fenêtre : son contexte natif, le
  `-c` de llama-server, le quota par minute d'un fournisseur (`tpm`), ou la fenêtre qu'une
  déclaration cloud fixe (`window` : le réglage est alors désactivé) ;
- **le verdict du budget mémoire** : « Tient dans le budget », ou le refus chiffré (ce que
  demanderait le modèle avec cette fenêtre, ce qu'occupe WaveStack sans lui, le budget et son
  calcul).

« Appliquer », entre deux tours seulement : un modèle local (fichier ou Ollama) est rechargé avec
la nouvelle fenêtre après le contrôle du budget, qui refuse avant de rien libérer ; un modèle de
llama-server est rechargé sans contrôle (sa mémoire est fixée par son `-c`) ; un modèle cloud
prend la fenêtre au tour suivant, sans rechargement. La conversation est gardée ; un échec du
rechargement ou « Arrêter » rend l'ancienne fenêtre. Un choix qui ne change pas la fenêtre
effective (llama-server lancé avec `-c 8192`, à 8 192 puis 16 384) est enregistré sans
rechargement ; une fenêtre plus petite n'est jamais refusée par le budget. Ollama est recompté comme s'il chargeait le
modèle (fichier plus cache à la nouvelle fenêtre, plus la marge), même s'il le tient déjà en
mémoire : il le recharge à son nouveau `num_ctx`. Le choix est mémorisé dans `settings.json`
(`"context": {"window": 8192}`) et repris au lancement suivant ; « Réinitialiser » ne le touche
pas. Sans modèle actif, il est enregistré pour le prochain chargement. Une autre valeur saisie à
la main dans `[context] window` reste lue, mais n'est pas proposée par le panneau.

## Langue

Le sélecteur de langue est dans le menu « Affichage ▾ » de la barre haute (juste avant
« Réinitialiser », avec le thème et le mode projection ; sa face montre le code de la langue,
« FR ») et propose **Français**, **English** et **Deutsch**. Il ne s'ouvre que sur une conversation vide : après un
échange, il est grisé et son infobulle demande de cliquer d'abord sur « Vider la conversation »
ou « Réinitialiser ». Le choix est enregistré dans `settings.json` (`"language": "en"`), repris
au lancement suivant, et la page se recharge dans la langue choisie.

Pour l'instant, la langue change :
- **ce qui part vers le modèle** : prompt système par défaut, prompt du sous-agent,
  descriptions des outils et de leurs paramètres (outils natifs, serveur MCP local,
  méta-outils `load_skill`, `load_tool_doc`, `remember`, `delegate`), skills, texte et date
  ajoutés par H3, introduction et entrées de la mémoire globale de démonstration, glossaire du
  serveur MCP local, introduction et format des extraits du RAG ;
- **les libellés tirés de ces mêmes fichiers** : noms et préréglages des outils (carte
  « Outils », schéma, actions forcées), noms et descriptions des hooks et points du tour
  (Orchestration), noms des skills, libellés des serveurs MCP et de leurs préréglages, bouton,
  phase et préréglages du sous-agent, textes du tiroir de la mémoire, boutons et phases de la
  carte RAG ;
- **l'écran principal** : boutons, volets, menus, infobulles, jauge, Orchestration, schéma et
  messages de l'interface elle-même, avec les nombres, montants et heures au format de la
  langue (« 1 234 », « 1,234 », « 1.234 »). Ses textes sont dans `content/ui.yaml`.

Restent en français : les noms et explications des briques, les scénarios et leurs
consignes, les messages produits par le harnais (erreurs, raisons d'indisponibilité, erreurs
d'outils, résultat de `get_datetime`), les écrans « LLM nu » et « Atelier RAG », le corpus
RAG et les titres de ses documents.
Une mémoire globale que vous avez modifiée est gardée telle quelle ; la mémoire de
démonstration, elle, passe dans la nouvelle langue.

Les traductions sont dans `content/i18n/en/` et `content/i18n/de/`, avec les mêmes noms de
fichiers que `content/` ; un fichier absent y est lu en français.

## Écran « LLM nu »

Le lien **« LLM nu »** de la barre haute ouvre la page `/llm` : ce qui se passe *dans* le modèle
actif, sans aucune brique (ni prompt système, ni historique, ni outil, ni mémoire) et sans
toucher à la conversation de l'atelier. Le modèle ne s'y change pas : le lien « Changer de modèle
dans l'atelier » ramène au sélecteur de la barre haute.

- **Tokenisation et vectorisation.** « Découper en tokens » découpe le texte saisi (2 000
  caractères au plus), sans gabarit, par le tokenizer du modèle actif : une puce par token avec
  son identifiant (512 au plus), les blancs rendus visibles (`␣`, `↵`), un marqueur du gabarit
  comme `<|im_end|>` en un seul token marqué « spécial ». Un schéma suit le chemin d'un token :
  texte → tokens → identifiants → ligne de la table d'embedding (vocabulaire × dimension) →
  vecteur → couches, avec les dimensions réelles du modèle (lues par llama.cpp, dans l'en-tête
  GGUF, ou données par llama-server), ou « inconnue » et pourquoi. Un modèle cloud n'a pas de
  tokenizer sur le poste : la page le dit et montre l'estimation du harnais.
- **Réglages d'échantillonnage.** L'échantillonnage est un paramètre de chaque appel au
  modèle : l'atelier envoie toujours les valeurs du harnais (température 0,7, top-k 20, top-p
  0,8, min-p 0), l'écran envoie les siennes, réglables par curseur (température 0 à 2, top-k 0 à
  100, 0 le désactivant, top-p 0,05 à 1, min-p 0 à 0,5), au moteur en processus, à llama-server et à Ollama. Un
  modèle cloud ne prend que ce que son entrée déclare (`sampling`, voir « Modèle cloud »), les
  autres réglages sont grisés avec leur raison. Chaque appel trace son échantillonnage dans
  `model_call_started` (journal des événements).
- **Lecture du prompt et génération.** « Générer » envoie le texte comme un seul message de
  l'utilisateur, rendu par le gabarit du modèle, sans prompt système ni historique. La page
  montre le prompt rendu, son nombre de tokens, le temps jusqu'au premier token et le débit de
  lecture, puis les tokens un par un (des fragments pour un modèle cloud) et le débit de
  sortie. « Arrêter » interrompt. Pendant la génération, l'atelier attend (état « écran LLM
  nu ») ; sa conversation n'en reçoit rien, et l'état du moteur est restauré pour le tour
  suivant.
- **Chargement du modèle.** L'écran montre le dernier chargement fait dans l'atelier, étape
  par étape (libération du modèle précédent, sonde, contrôle du budget, création du moteur,
  prêt), avec les durées et la mémoire : RAM du processeur pour un fichier (pas de carte
  graphique), processus du serveur pour un modèle d'Ollama ou de llama-server, aucune mémoire
  sur le poste pour un modèle cloud. Un chargement en cours se suit en direct.
- **Raisonnement.** « Raisonner avant de répondre » s'active quand le modèle sait raisonner
  (grisé avec la raison sinon, verrouillé pour un modèle qui raisonne toujours) ; la réflexion
  et la réponse s'affichent dans deux couloirs, avec la réserve de 1 536 tokens et, en local,
  la coupe du harnais au budget de réflexion.
- **Tokens candidats.** Avec un fichier GGUF chargé par WaveStack (moteur en processus),
  « Montrer les tokens candidats » garde, pour chaque token produit, les cinq tokens que le
  modèle jugeait les plus probables : survolez, donnez le focus ou cliquez une puce pour voir
  leur probabilité, ceux que top-k, top-p ou min-p écartent et leur chance réelle d'être tirés
  (la température appliquée), le token tiré marqué. La lecture coûte peu (le vocabulaire d'une
  seule position par token). Avec llama-server, Ollama ou un modèle cloud, la case est grisée :
  WaveStack ne lit pas leurs probabilités.

Les textes de la page sont dans `content/llm_lab.yaml`. Les événements de l'écran sont tracés
dans le contexte `llm` : le journal des événements de l'atelier les liste, aucun volet ne les
montre.

## Atelier RAG

Le lien **« Atelier RAG »** de la barre haute ouvre la page `/rag` : l'architecture d'une chaîne
RAG, dessinée pièce par pièce, puis exécutée sur une question, étape par étape. C'est un bac à
sable : la brique RAG de l'atelier (ses réglages, son index, ses modèles) ne change pas.

- **La chaîne.** Sept cartes : découpage du corpus, embedding, base vectorielle, recherche,
  reranking, construction du contexte, génération. Chaque carte nomme son option (le modèle
  déclaré dans `[rag.embedding]` et `[rag.reranker]`, sqlite-vec…), ses réglages, et explique
  ce qu'elle fait ; une note dit ce qu'une exécution rencontrerait (modèle absent, index de la
  brique à construire). La génération est dessinée mais ne s'exécute pas ici : générer, c'est un
  tour de l'atelier ; la carte montre ce que le modèle recevrait.
- **L'exécution.** « Lancer la chaîne » exécute chaque étape sur la question (500 caractères au
  plus) et montre ce qu'elle reçoit, ce qu'elle produit, ses chiffres, ses extraits (rang, rang
  d'avant, document, score), sa durée et la mémoire de WaveStack. La chaîne livrée lit l'index
  de la brique (sans jamais y écrire) ; l'embedder et le reranker sont empruntés à la brique RAG
  quand elle les a chargés, sinon chargés pour l'exécution (dans le budget mémoire) puis fermés.
  Sans modèle d'embedding, l'étape le dit : téléchargez-le depuis la carte RAG de l'atelier ;
  sans reranker, le reranking est sauté et le contexte garde l'ordre de la recherche.
  « Arrêter » interrompt entre deux étapes. Pendant l'exécution, l'atelier attend (état
  « Atelier RAG : exécution en cours »).
- **Options et réglages.** Chaque carte propose ses options (les indisponibles sont grisées, la
  raison sous la carte) et ses réglages : taille des extraits (200 à 1 500 caractères), candidats
  retenus et extraits du contexte (1 à 20, jamais moins de candidats que d'extraits). La base
  vectorielle peut être l'index sqlite-vec ou une **recherche exhaustive en mémoire** (Python pur,
  sans index) ; l'embedding peut être un modèle **fastembed** (ONNX), proposé seulement s'il est
  installé, déclaré dans `settings.json` (`"rag_lab": {"fastembed": {"model_name": …, "dims": …,
  "label_text": …}}`, `"folder"` en option) et copié à la main sous `models/fastembed/<son
  dossier>` du dossier de données (par défaut `models--<model_name>`, « / » devenant « -- ») :
  l'atelier ne
  télécharge jamais rien. Une chaîne refusée dit pourquoi, en nommant l'étape.
- **Comparer deux configurations.** « Comparer avec une autre configuration » ouvre une chaîne
  B ; les deux s'exécutent l'une après l'autre sur la même question, en deux colonnes, suivies
  d'une synthèse : extraits communs, propres à A ou à B, écarts de rang (par document quand les
  deux chaînes découpent le corpus autrement). Les chaînes en cours d'édition sont gardées par le
  navigateur ; « Revenir à la chaîne livrée » les oublie.
- **Ajouter, retirer, déplacer.** Entre la base vectorielle et le contexte, les recherches, la
  fusion et le reranking se déplacent par leurs boutons « ◀ » et « ▶ » (au clavier aussi) et se
  retirent ; « Ajouter un composant » propose ceux qui manquent, placés avant le contexte : la
  **recherche lexicale BM25** (par mots, sans embedding, k1 = 1,5 et b = 0,75 ; accents et petits
  mots ignorés, sigles et nombres gardés, comme « RH » ou « 35 ») et la **fusion**
  des rangs réciproques (k = 60), qui combine deux recherches en une recherche hybride. Les
  autres étapes sont fixes. WaveStack vérifie la chaîne à chaque modification : une chaîne
  invalide (deux recherches sans fusion après elles, une fusion sans deux recherches avant elle,
  un reranking avant toute recherche…) affiche sa raison sur la carte fautive, et « Lancer » est
  désactivé.
- **Le dossier `rag_lab`.** Hors de la chaîne livrée, les vecteurs du corpus sont calculés une
  fois par modèle et par taille d'extrait, puis relus (« relus du cache »), et les index sqlite-vec
  de l'atelier sont construits à côté, dans `rag_lab/` du dossier de données (moins de 1 Mo par
  configuration pour le corpus livré). Rien n'est écrit dans le dépôt ni dans l'index de la
  brique. Ce dossier se supprime sans risque, WaveStack arrêté.

Les textes de la page sont dans `content/rag_lab.yaml`. Les événements `rag_lab_*` sont tracés
dans le contexte `rag_lab` : le journal des événements de l'atelier les liste, aucun volet ne
les montre. Après un rechargement, la page réaffiche la dernière exécution.

## Atelier RAG : FAISS et LanceDB (extra optionnel)

La base vectorielle de l'Atelier RAG peut aussi être [FAISS](https://pypi.org/project/faiss-cpu/)
(`faiss-cpu` 1.15.1, MIT) ou [LanceDB](https://pypi.org/project/lancedb/) (`lancedb` 0.39.0,
Apache-2.0, avec `pyarrow` 25.0.1). Ce sont des dépendances optionnelles, l'extra `rag-alt`,
non installées par `uv run wavestack` seul. Depuis le dossier de WaveStack :

```bash
uv sync --extra compression --extra rag-alt
uv run wavestack
```

- **Headroom.** Gardez `--extra compression` dans la commande : un `uv sync` sans lui retire
  Headroom (la brique Compression).
- **Taille.** Environ 390 Mo sur disque sous Linux, dont pyarrow 150 Mo et lancedb 170 Mo ;
  six paquets, des roues seulement (rien n'est compilé sur le poste).
- **Hors ligne.** Une fois installés, FAISS et LanceDB ne se connectent à rien : leurs index
  sont des fichiers du dossier de données.
- **Mémoire.** Leur premier import est compté par le budget, à vie (un module Python ne se
  décharge pas) : `[rag_lab] faiss_cost_mb = 60` et `lancedb_cost_mb = 180` ; l'étape « Base
  vectorielle » dit la mémoire réellement ajoutée.
- **Le dossier `rag_lab`.** Chaque index est construit à la première exécution (« construit
  (N vecteurs) »), puis relu (« relu ») ; `rag_lab/` du dossier de données se supprime sans
  risque, WaveStack arrêté.
- **Poste verrouillé.** Leurs bibliothèques natives (DLL) ne sont pas signées : AppLocker ou
  WDAC peuvent les bloquer. L'étape « Base vectorielle » dit alors « Import refusé », l'option
  devient indisponible, et les autres bases (sqlite-vec, recherche en mémoire) restent
  utilisables.
- **Sans l'extra,** FAISS et LanceDB sont grisés dans l'Atelier RAG, avec la commande
  d'installation.
- **fastembed n'est pas livré** (décision de la story 30) : ni dépendance ni extra de WaveStack,
  car il ajoute onnxruntime et un client de téléchargement que le parcours n'a pas vérifiés hors
  ligne sous la garde réseau, ni sous Windows. Un formateur qui veut le montrer l'ajoute sur son
  poste seulement, depuis le dossier de WaveStack : `uv add --optional fastembed
  "fastembed==0.8.1"`, puis `uv sync --extra compression --extra rag-alt --extra fastembed` ;
  `git checkout pyproject.toml uv.lock` le retire avant une mise à jour. Son import est compté
  à vie par le budget (`[rag_lab] fastembed_cost_mb = 150`), son modèle à part, le temps d'une
  exécution.

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
toujours à llama-server un `-c` égal à la fenêtre choisie** (4 096 par défaut ; 8 192 ou
16 384 si vous l'avez choisie dans « Fenêtre ▾ », section précédente) : WaveStack ne relance
jamais llama-server, et une fenêtre plus grande que son `-c` est bornée à celui-ci. Sans `-c`,
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

**Obtenir llama-server sans droits d'administrateur (Windows).** WaveStack n'installe pas
llama-server. Sur un poste sans droits d'administrateur, prenez l'archive CPU officielle de
llama.cpp, `llama-bNNNNN-bin-win-cpu-x64.zip`, publiée sur `github.com/ggml-org/llama.cpp`,
décompressez-la dans votre profil (`%LOCALAPPDATA%\llama.cpp\<version>`, un dossier par
version) et lancez l'exécutable par son chemin complet : rien ne s'installe, rien ne demande
d'élévation. Dans PowerShell (Windows PowerShell 5.1 ou PowerShell 7), ligne par ligne :

```powershell
[Net.ServicePointManager]::SecurityProtocol = [Net.SecurityProtocolType]::Tls12   # PowerShell 5.1
$px = @{}   # erreur 407 : lancez la ligne « Proxy », puis reprenez ici à Invoke-RestMethod
$rels = Invoke-RestMethod -UseBasicParsing @px "https://api.github.com/repos/ggml-org/llama.cpp/releases?per_page=10"
$rel = $rels | Where-Object { $_.assets.name -match '^llama-b\d+-bin-win-cpu-x64\.zip$' } | Select-Object -First 1
$asset = $rel.assets | Where-Object name -match '^llama-b\d+-bin-win-cpu-x64\.zip$'
if (-not $asset) { throw "Aucune archive llama-bNNNNN-bin-win-cpu-x64.zip dans les dix dernières releases : prenez le repli b11239." }
$zip = "$env:TEMP\$($asset.name)"; $dest = "$env:LOCALAPPDATA\llama.cpp\$($rel.tag_name)"
Invoke-WebRequest -UseBasicParsing @px $asset.browser_download_url -OutFile $zip
if ($asset.digest) { if (("sha256:" + (Get-FileHash $zip -Algorithm SHA256).Hash.ToLower()) -ne $asset.digest) { throw "Empreinte SHA-256 différente de celle publiée par GitHub : archive refusée." } else { "Empreinte SHA-256 vérifiée." } }
Expand-Archive $zip -DestinationPath $dest -Force; Get-ChildItem $dest -Recurse | Unblock-File
$llama = "$dest\llama-server.exe"; & $llama --version
& $llama -m "$env:LOCALAPPDATA\WaveStack\models\Qwen3.5-2B-Q4_K_M.gguf" --port 8080 -np 1 -c 4096
```

La première ligne ne sert qu'à Windows PowerShell 5.1 ; `$asset.name` donne le nom de
l'archive, `& $llama --version` la version. Si le téléchargement se traîne sous PowerShell 5.1,
tapez d'abord `$ProgressPreference = "SilentlyContinue"`. Dans un nouveau terminal, sans rien
retélécharger, retrouvez l'exécutable, puis lancez-le par la dernière ligne du bloc :

```powershell
$llama = Get-ChildItem "$env:LOCALAPPDATA\llama.cpp" -Recurse -Filter llama-server.exe | Sort-Object LastWriteTime | Select-Object -Last 1 -ExpandProperty FullName
```

Ligne « Proxy » (erreur 407 seulement) :

```powershell
$px = @{ Proxy = [System.Net.WebRequest]::GetSystemWebProxy().GetProxy("https://api.github.com"); ProxyUseDefaultCredentials = $true }
```

- **Erreur 407** (le proxy demande vos identifiants) : lancez la ligne « Proxy » ci-dessous. Elle
  calcule le proxy du système (`GetSystemWebProxy().GetProxy(…)`) et fait passer `-Proxy` et
  `-ProxyUseDefaultCredentials` à `Invoke-RestMethod` et à `Invoke-WebRequest` (par `@px`, repli
  compris) ; reprenez ensuite le bloc à `Invoke-RestMethod`.
- **Aucune archive trouvée** : le bloc s'arrête (« Aucune archive … : prenez le repli b11239. »).
- **Intégrité** : quand l'API donne l'empreinte de l'archive (champ `digest`, SHA-256), le bloc
  la compare à `Get-FileHash` et refuse une archive différente. Le repli, sans l'API, ne vérifie
  rien : comparez `(Get-FileHash $zip).Hash` à l'empreinte de la page de la release si elle
  s'ouvre.
- **`Unblock-File`** retire la marque « téléchargé depuis Internet » (Mark of the Web) que
  Windows pose sur les fichiers de l'archive. Si la politique du poste l'interdit, ou si
  SmartScreen ou AppLocker bloque l'exécutable, arrêtez-vous : « non fait (poste) », sans
  contourner.
- Sous macOS ou Linux, prenez l'archive de la même release qui correspond au système.

Si ça bloque encore :
- **API GitHub refusée** (403, ou 407 qui persiste) : si `github.com` reste joignable, prenez la
  version fixe `b11239` (la dernière le 2026-09-28) par son adresse directe :

  ```powershell
  $tag = "b11239"; if (-not $px) { $px = @{} }
  $zip = "$env:TEMP\llama-$tag-bin-win-cpu-x64.zip"; $dest = "$env:LOCALAPPDATA\llama.cpp\$tag"
  Invoke-WebRequest -UseBasicParsing @px "https://github.com/ggml-org/llama.cpp/releases/download/$tag/llama-$tag-bin-win-cpu-x64.zip" -OutFile $zip
  Expand-Archive $zip -DestinationPath $dest -Force; Get-ChildItem $dest -Recurse | Unblock-File
  $llama = "$dest\llama-server.exe"; & $llama --version
  ```

- **GitHub entièrement bloqué** : récupérez la même archive sur un autre réseau ou un autre
  poste, ou auprès de votre formateur, et copiez-la dans `%TEMP%` (partage interne, OneDrive,
  clé USB). Lancez alors les deux premières lignes du bloc de repli, avec `$tag` égal à la
  version de l'archive copiée, sautez `Invoke-WebRequest` et reprenez à `Expand-Archive`.
  Aucune autre source : ni winget, ni Chocolatey, ni installeur.
- **Exécutable bloqué** (AppLocker, SmartScreen, ou « VCRUNTIME140.dll » ou « MSVCP140.dll »
  introuvable) : relevez le message exact et transmettez-le au support, sans contourner le
  blocage. WaveStack reste utilisable avec son moteur intégré ou avec Ollama.
- Gardez `llama-server.exe` avec ses DLL : ne le copiez pas seul, et ne le décompressez pas dans
  `Program Files`.

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

**Un corpus et un index par langue.** Le corpus anglais et le corpus allemand sont dans
`content/i18n/{en,de}/corpus/`, sous les mêmes noms de fichiers, et les titres des documents
dans `content/i18n/{en,de}/rag.yaml`. Chaque langue a son index, à côté du français :
`data/rag_index.en.sqlite` et `data/rag_index.de.sqlite` (le chemin de `[rag] index_path`,
`.{langue}` inséré avant l'extension). Les trois index sont livrés avec le dépôt : la brique
RAG et l'atelier RAG ouvrent celui de la langue de la session, titres des extraits compris.
Après un changement de langue, un index absent se construit depuis la carte, comme ci-dessus.

Le script fait la même chose, pour une langue à la fois (`fr` par défaut, jamais lue dans
`settings.json`), et peut committer l'index avec le dépôt :

```bash
uv run python scripts/build_rag_index.py                  # modèle de [rag.embedding], français
uv run python scripts/build_rag_index.py --lang de        # corpus allemand, rag_index.de.sqlite
uv run python scripts/build_rag_index.py --download       # télécharge d'abord le modèle
uv run python scripts/build_rag_index.py --model C:\chemin\modele.gguf
```

`--model` n'accepte que le fichier déclaré (même taille, même sha256 s'il est renseigné).
L'index garde l'identifiant, les dimensions et le fichier de son modèle, et une empreinte du
corpus de sa langue : un autre modèle, un corpus modifié (ou celui d'une autre langue) ou un
autre `[rag] chunk_max_chars` rendent la brique indisponible, avec la raison, et la carte
propose « Construire l'index ». Le dossier
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

## Modèle cloud (Groq, Mistral, Gemini, Gemma)

Un modèle cloud compatible OpenAI peut remplacer le SLM local : plus rapide, meilleur avec les
outils, et il montre un vrai appel hors du poste. Les préréglages Groq (`openai/gpt-oss-120b`),
Mistral (`mistral-small-latest`), Gemini (`gemini-3.5-flash-lite`) et Gemma
(`gemma-4-26b-a4b-it`, tous deux sur Google AI Studio) sont déclarés dans `wavestack.toml` ;
NVIDIA et OpenRouter y figurent en exemples commentés, avec leur avertissement.

1. **Clé.** Créez une clé API dans la console du fournisseur, puis collez-la sur la page de
   diagnostic, dans la ligne du modèle (« Enregistrer la clé »). Elle est stockée sur ce poste
   seulement (`api_keys.json` dans le dossier de données), jamais affichée ni tracée, et envoyée au
   seul hôte déclaré. Si l'adresse du fournisseur change, la clé est à ressaisir.

   **Ou par variable d'environnement.** Chaque préréglage nomme une variable (`key_env`) :
   `GROQ_API_KEY` pour Groq, `MISTRAL_API_KEY` pour Mistral, `GEMINI_API_KEY` pour Gemini et
   Gemma (même clé). Sous Windows, sans droits administrateur :

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

**Gemini (Google AI Studio).** L'offre payante est obligatoire : les conditions de Google
(relues le 2026-09-30) réservent l'offre payante à tout client d'API (site, application ou
service) mis à disposition d'utilisateurs de l'EEE, de Suisse ou du Royaume-Uni, et sur l'offre
payante les contenus ne servent pas à l'entraînement. Ces règles de données s'appliquent aussi
aux utilisateurs de l'EEE sur le quota gratuit. Les prix se vérifient dans la
console (relevé le 2026-09-29 : 0,30 $ / 2,50 $ par million de tokens pour
`gemini-3.5-flash-lite`, sans hausse annoncée ; hausse au 2027-01-01 pour les 3.6 à 3.8 Flash). Le raisonnement s'allume et s'éteint avec la
brique : allumé, `thinking_level` « medium » et le texte de la réflexion (entre `<thought>` et
`</thought>`) ; éteint, `reasoning_effort` « minimal ». Gemini 3.x signe une réponse qui appelle
des outils (sur le premier appel seulement quand il y en a plusieurs en parallèle) et refuse un
appel rejoué sans cette signature : WaveStack la lui renvoie telle quelle, et à lui seul. Si la forme réelle diffère (balises, `minimal` ou `extra_body` refusés), corrigez
l'entrée `gemini` dans `settings.json`, sans toucher au code : les secours sont décrits en
commentaire dans `wavestack.toml`. `null` n'y retire qu'une clé de premier niveau de
`reasoning.on` ou `reasoning.off` (par exemple `"extra_body": null`) : un `null` plus profond
est envoyé tel quel, et `tool_call_extra` ou `tags` à `null` rendent l'entrée invalide.

**Gemma 4 (Google AI Studio).** `gemma-4-26b-a4b-it` est un modèle ouvert de Google : un MoE de
26 milliards de paramètres au total, 4 milliards actifs par token (le sélecteur et le tableau
lisent « 26B » dans le nom). Il est servi avec la même clé et sur le même hôte que Gemini, mais
seulement sur l'offre gratuite : aucun prix, aucun quota publié, donc aucun coût estimé et
« offre d'essai » dans l'avertissement. Conditions : Google réserve l'offre payante aux clients
d'API mis à disposition d'utilisateurs de l'EEE, et Gemma n'en a pas ; l'entrée vaut pour un
usage personnel de votre clé sur votre poste, pas pour une mise à disposition. Données : la page
tarifaire dit que l'offre gratuite sert à améliorer les produits Google, mais les utilisateurs
de l'EEE ont les règles de l'offre payante, quota gratuit compris, d'où `training = "no"` avec la
nuance dans la note. Relevé sur l'API réelle le 2026-09-30 : 262 144 tokens en entrée, 32 768 en
sortie ; le modèle réfléchit et montre sa pensée par défaut (entre `<thought>` et `</thought>`).
Brique Raisonnement allumée, WaveStack envoie `include_thoughts` seul (explicite, et distinct du
corps éteint) ; éteinte, `reasoning_effort` « minimal » supprime la réflexion ; `thinking_level`
et `thinking_budget` sont refusés. Les appels d'outils portent la même signature de pensée que
Gemini, rejouée de la même façon. Un 429 vient du quota gratuit, non publié : s'il survient
« par seconde », posez `min_interval_s` dans `settings.json` ; au premier appel de « Tester »,
c'est le quota du compte. Une clé saisie au diagnostic est propre à sa ligne : saisissez-la aussi
sur la ligne Gemma, ou posez `GEMINI_API_KEY`, qui sert aux deux préréglages. Secours :
`gemma-4-31b-it` (dense, plus lent), avec son empreinte, dans `settings.json` :
`{"id": "gemma", "model": "gemma-4-31b-it", "impacts": {"provider": "google_genai", "model":
"gemma-4-31b-it"}}`.

**Revenir au modèle local.** Choisissez un fichier GGUF dans le sélecteur de la barre haute, ou
cliquez sur « Choisir » en face d'un fichier sur la page de diagnostic : le modèle local est
rechargé sans relance, conversation gardée.

**Hôtes à autoriser** sur le réseau de l'entreprise : `api.groq.com`, `api.mistral.ai` et
`generativelanguage.googleapis.com` (plus l'hôte de tout modèle ajouté dans `settings.json`).

**Ajouter un modèle.** Les exemples NVIDIA et OpenRouter de `wavestack.toml` sont en TOML :
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
        "hosting_text": "Selon le fournisseur routé par OpenRouter",
        "training": "yes",
        "notes_text": "Catalogue gratuit instable : vérifiez le nom du modèle avant la séance."
      }
    ]
  }
}
```

Une entrée de même `id` qu'un préréglage le modifie champ par champ (par exemple
`{"id": "groq", "tpm": 6000}`), et `"enabled": false` le masque. Un `settings.json` écrit
avant la version multilingue reste lu : les anciennes clés `hosting_fr`, `notes_fr`, `note_fr`
(de `impacts`) et `label_fr` (de `[rag.embedding]`, `[rag.reranker]` ou `[rag_lab.fastembed]`)
valent `hosting_text`, `notes_text`, `note_text` et `label_text`.

Quatre champs facultatifs :
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
- `sampling` (écran « LLM nu ») : les réglages d'échantillonnage que le modèle accepte, parmi
  `"temperature"` et `"top_p"` (les deux champs de l'API compatible OpenAI) ; vide par défaut :
  le fournisseur garde les siens. Les préréglages Groq et Mistral déclarent les deux. Seul l'écran
  « LLM nu » les envoie ; les tours de l'atelier n'envoient aucun réglage, et top-k et min-p ne
  partent jamais chez un fournisseur.
- `pricing` (FinOps, voir ci-dessous) : les prix du modèle, par exemple
  `"pricing": {"input_usd_per_mtok": 0.15, "output_usd_per_mtok": 0.6, "checked": "2026-09-29"}`.
- `impacts` (GreenOps, voir plus bas) : le modèle tel qu'EcoLogits le connaît, par exemple
  `"impacts": {"provider": "mistralai", "model": "mistral-small-latest", "zone": "FRA"}`.

## FinOps : coût estimé des appels cloud

Chaque entrée `[[cloud.models]]` peut déclarer ses prix dans `pricing` : prix d'entrée et prix de
sortie, en dollars par million de tokens, et la date du relevé (`checked`, au format
AAAA-MM-JJ). Relevés le 2026-09-29 sur les pages officielles : Groq `openai/gpt-oss-120b` et
Mistral Small 4 à 0,15 $ / 0,60 $, Gemini `gemini-3.5-flash-lite` à 0,30 $ / 2,50 $. Sur le
plan gratuit de Mistral, le coût réel est nul : le prix affiché est le prix catalogue. Gemma n'a
pas de `pricing` : le modèle est gratuit, aucun coût n'est estimé ni affiché (« — »).

**Estimation.** Pour chaque appel cloud, WaveStack calcule le coût d'entrée (tokens du prompt ×
prix d'entrée / 10⁶) et le coût de sortie (tokens produits × prix de sortie / 10⁶, les tokens de
raisonnement compris, même ceux que Gemini ne compte pas dans `completion_tokens`). Les tokens
viennent de `usage` quand le fournisseur le renvoie ; sinon ils sont estimés, et le coût aussi
(« ≈ »). Ce sont toujours des estimations : ni les en-têtes de facturation ni la console du
fournisseur ne sont lus. Un appel arrêté (« Arrêter ») compte son entrée telle qu'envoyée, et la
sortie reçue avant l'arrêt ; un appel refusé avant toute réponse ne compte rien. L'estimation
suit le prix catalogue : les remises sur l'entrée en cache, les prix par palier ou pour les longs
contextes, les prix du traitement par lots (batch) et les offres gratuites ne sont pas pris en
compte.

**Affichage.** « Coût estimé : entrée … $ · sortie … $ » dans le détail de chaque appel
(Orchestration), le total du tour dans son en-tête (« coût estimé … $ »), et « Dépense
estimée » dans la barre haute dès le premier appel payant : le total de la séance, entrée + sortie
(arrondies au centième de cent), la phrase entière (4 chiffres significatifs, conversion en
euros) dans l'infobulle. Ce total compte tous les appels payants : les tours, le sous-agent,
« Tester » au diagnostic et l'écran « LLM nu ». Ni « Vider la conversation » ni « Réinitialiser »
ne le remettent à zéro ; seul un relancement de WaveStack le fait (il n'est jamais écrit sur le
disque). Les prix déclarés sont aussi dans la colonne « Prix » de la page `/models` et sur la
ligne « Prix » du diagnostic. Un modèle local n'a pas de coût, et une entrée sans `pricing` non
plus.

**Mettre les prix à jour.** Relevez les prix sur la page du fournisseur, puis surchargez l'entrée
dans `settings.json`, par exemple `{"id": "gemini", "pricing": {"input_usd_per_mtok": 0.3,
"output_usd_per_mtok": 2.5, "checked": "2027-01-02"}}`, et relancez WaveStack. Le taux de
conversion se règle dans `[finops] eur_per_usd` (euros pour un dollar, 0,86 par défaut, borné de
0,5 à 2 ; une valeur illisible, `nan` ou `inf`, vaut 0,86). Ce taux par défaut a été relevé le
2026-09-30 : mettez-le à jour. Un prix négatif rend l'entrée invalide : elle est écartée au lancement, avec la raison.

## GreenOps : empreinte estimée des appels au modèle

WaveStack estime, pour chaque appel au modèle, l'énergie consommée (Wh) et les émissions (g CO₂e),
puis les additionne par tour et par séance, sans aucun appel réseau.

**Modèle cloud : méthode EcoLogits.** La bibliothèque `ecologits` (dépendance normale, son cœur
seul : aucun SDK n'est instrumenté) estime l'impact d'un appel à partir de ses tokens de sortie
(raisonnement compris) et de sa durée, pour le modèle que nomme le champ `impacts` de l'entrée
`[[cloud.models]]` : `provider` et `model` tels qu'EcoLogits les connaît, et `zone`, facultative,
le mix électrique (code ISO à trois lettres ; par défaut celui du fournisseur dans EcoLogits).
Préréglages : Groq → `huggingface_hub` / `openai/gpt-oss-120b` (EcoLogits ne connaît pas Groq ;
gpt-oss y figure chez Hugging Face, sur GPU), Mistral → `mistralai` / `mistral-small-latest`,
Gemini → `google_genai` / `gemini-3.5-flash-lite`, Gemma → `google_genai` /
`gemma-4-26b-a4b-it`. Le champ facultatif `note_text` de `impacts`
s'ajoute à l'infobulle de chaque appel : celui de Groq dit que l'estimation passe par un autre
hébergeur. Quand EcoLogits donne une fourchette (architecture non
publiée, comme Gemini), elle est gardée : « 0,066–0,45 Wh ». Ses avertissements (architecture non
publiée, modèle multimodal) sont repris en français dans l'infobulle. Sans `impacts`, ou pour un
modèle qu'EcoLogits ne connaît pas, l'appel n'a pas d'empreinte, et l'infobulle dit pourquoi.

**Modèle local : CodeCarbon.** Avec l'extra `greenops`, un traceur CodeCarbon hors ligne entoure
chaque génération : le processus de WaveStack seul pour le moteur intégré, le poste entier pour
Ollama et llama-server (processus à part). Seule son énergie est gardée ; les émissions en
découlent à `[greenops] local_gco2e_per_kwh` (41,4 g CO₂e par kWh par défaut, le facteur du mix
France d'EcoLogits ; RTE donne pour 2025 19,6 g en émissions directes, environ 29 g en cycle de
vie). Sous Windows, sans RAPL ni droits administrateur, CodeCarbon estime la puissance du
processeur à partir de son TDP et de sa charge : c'est une estimation, pas une mesure. Ni le
GPU, ni un fichier `emissions.csv`.

**Deux périmètres différents.** Le chiffre local ne compte que l'électricité consommée pendant
l'appel (kWh × 41,4 g/kWh), sans la fabrication du poste. Le chiffre cloud d'EcoLogits est un
cycle de vie : l'électricité des serveurs et une part de leur fabrication. Les deux s'additionnent
dans la séance, mais ne se comparent pas terme à terme.

```bash
uv sync --extra compression --extra greenops   # gardez vos autres extras dans la commande
```

Environ 150 Mo installés : l'installation de l'extra demande le réseau (PyPI) ou un cache local
de paquets. Dès qu'un modèle local est prêt, CodeCarbon s'importe en arrière-plan (environ 70 Mo
en mémoire, `[greenops] codecarbon_cost_mb = 80` comptés une fois, à vie, par le budget mémoire)
et détecte le processeur (quelques secondes, une seule fois ; un appel qui commence avant la fin
de cette préparation l'attend). Sans l'extra, ou si le budget le
refuse, tout le reste fonctionne : l'empreinte locale est « indisponible », et l'infobulle en
donne la raison (la commande d'installation, ou le refus du budget). Une estimation qui échoue
n'arrête jamais un tour : l'appel n'a pas d'empreinte, avec la raison.

**Affichage.** « Empreinte estimée : 0,11 Wh · 0,046 g CO₂e » dans le détail de chaque appel
(la méthode et ses limites dans l'infobulle), la somme du tour dans son en-tête, et l'empreinte
de la séance dans la barre haute : en fin de deuxième ligne de « Dépense estimée »
(« · 0,12 g CO₂e ») quand elle tient, sinon dans l'infobulle ; « Empreinte estimée » seule tant
qu'aucun appel payant n'a eu lieu. Comme la dépense, ce total compte les tours, le sous-agent,
« Tester » et l'écran « LLM nu », et seul un relancement le remet à zéro. L'embedding et le
reranker du RAG ne sont pas comptés.

## Développement

```bash
uv sync --extra compression --extra rag-alt --extra greenops   # leurs tests
uv run ruff check .
uv run ruff format .
uv run pytest
```

Les tests marqués `model` nécessitent un vrai fichier GGUF sur le poste ; ils sont sautés par
défaut.
