# Modèles

[← Retour au README](../README.md)

WaveStack utilise au choix un petit modèle local (un fichier GGUF), le modèle d'un serveur que
vous avez lancé (Ollama, llama-server) ou un modèle cloud. Pour obtenir le modèle recommandé, voir
[l'installation](installation.md#le-modèle-local).

- [Changer de modèle](#changer-de-modèle), et le [budget mémoire](#budget-mémoire)
- [Fenêtre de contexte](#fenêtre-de-contexte)
- [Utiliser un serveur déjà lancé (Ollama, llama-server)](#utiliser-un-serveur-déjà-lancé-ollama-llama-server)
- [Modèles cloud](#modèles-cloud) : [clé, test et choix](#clé-test-et-choix),
  [particularités des fournisseurs](#particularités-des-fournisseurs),
  [ajouter ou modifier un modèle](#ajouter-ou-modifier-un-modèle)

## Changer de modèle

Le modèle se change sans relancer WaveStack, entre deux tours (pas pendant un tour ni une
validation) :
- **Barre du bas** : le sélecteur « Changer de modèle… », à droite de l'indicateur de modèle,
  liste les fichiers GGUF du poste, les modèles d'un serveur local déjà lancé et les modèles
  cloud déclarés (grisés sans clé). Un modèle cloud affiche d'abord son avertissement. « Autre
  fichier ou clé API… » ouvre le diagnostic.
- **Diagnostic** : « Choisir ce modèle » dans la carte d'un fichier ou d'un modèle servi,
  « Choisir ce modèle… » dans celle d'un modèle cloud (qui ouvre d'abord l'avertissement), ou
  « Choisir ce fichier » après un chemin saisi.

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
capacités… » (bouton « Ouvrir le tableau »), ouvre la page « Diagnostic et modèles »
(`/diagnostic` ; l'ancienne adresse `/models` y redirige). Une carte par modèle, groupée par
éditeur : un même modèle trouvé sous plusieurs sources (le fichier d'Ollama et le modèle
qu'Ollama sert, une copie dans le cache Hugging Face et dans LM Studio…) n'a qu'une carte,
« 2 sources », et chaque source garde son « Choisir cette source » dans la carte dépliée ; le
sélecteur, lui, garde une option par source. Un clic déplie la carte. Pour chaque modèle : éditeur, taille
(paramètres et octets), hébergement, fenêtre de contexte que WaveStack utiliserait, appel d'outils (oui, non, inconnu) et
raisonnement (jamais, toujours, activable ou inconnu), avec la raison. Ces capacités sont lues
comme au chargement, par les mêmes règles que les cartes des briques, sans charger ni sonder le
modèle : l'en-tête du fichier GGUF (lu une fois, puis mémorisé), le gabarit de llama-server, la
déclaration d'un modèle cloud. « Inconnu » veut dire que rien ne permet de le dire avant le
chargement : un modèle Ollama dont le fichier est introuvable, un gabarit sans variable de
raisonnement qui contient `<think>` (le modèle raisonne peut-être de lui-même, WaveStack ne sait
ni l'allumer ni l'éteindre).

Pendant le chargement, la barre du bas et la Vue humain affichent « Chargement du modèle… » avec
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

### Budget mémoire

Un seul modèle est en mémoire à la fois : l'ancien est libéré avant le
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
Elle se règle dans la barre du bas, par le bouton « Fenêtre 4 096 ▾ » juste après la jauge, à
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
16 384 si vous l'avez choisie dans « Fenêtre ▾ », voir [Fenêtre de contexte](#fenêtre-de-contexte)) : WaveStack ne relance
jamais llama-server, et une fenêtre plus grande que son `-c` est bornée à celui-ci. Sans `-c`,
il prend tout le contexte natif du modèle (262 144 tokens pour Qwen3.5) et réserve dès son
lancement la mémoire de ce contexte entier, quelle que soit la longueur des conversations
(5 137 Mo mesurés pour le 2B lors du test du 2026-09-27, pour un fichier de 1,28 Go). Avec
plusieurs emplacements (`-np N`), `-c` est partagé entre eux : gardez `-np 1`. Le diagnostic
signale un contexte trop grand et conseille la commande à relancer. Au diagnostic, chaque
modèle servi apparaît avec l'étiquette « Local », son serveur, son adresse et sa mémoire ;
« Choisir ce modèle » le charge, comme un fichier. Il est aussi dans le sélecteur de la barre du bas
(« Local · Ollama · … », « Local · llama-server · … »). Un modèle servi n'est jamais choisi
d'office ; un choix mémorisé est repris au lancement si le serveur le sert encore. Les modèles
« cloud » d'Ollama (`…-cloud`), qui tournent chez ollama.com, ne sont pas listés.

### Obtenir llama-server sans droits d'administrateur (Windows)

WaveStack n'installe pas
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

### Ce que reçoit le serveur

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
  `qwen35`, le modèle est accepté (seul son tokenizer est lu au choix), puis le premier tour
  échoue : l'erreur dit qu'Ollama ne connaît pas cette architecture et propose de mettre Ollama
  à jour ou de servir ce modèle avec llama-server, et WaveStack revient aussitôt au modèle
  précédent (enregistré comme choix). Aucune requête légère ne permet de le savoir plus tôt :
  seul un vrai chargement par Ollama révèle le refus. Si Ollama lit plus
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

## Modèles cloud

Un modèle cloud compatible OpenAI peut remplacer le SLM local : plus rapide, meilleur avec les
outils, et il montre un vrai appel hors du poste. Les préréglages Groq (`openai/gpt-oss-120b`),
Mistral (`mistral-small-latest`), Gemini (`gemini-3.5-flash-lite`) et Gemma
(`gemma-4-26b-a4b-it`, tous deux sur Google AI Studio) sont déclarés dans `wavestack.toml` ;
NVIDIA et OpenRouter y figurent en exemples commentés, avec leur avertissement.

### Clé, test et choix

1. **Clé.** Créez une clé API dans la console du fournisseur, puis collez-la sur la page de
   diagnostic, dans la ligne du modèle (« Enregistrer la clé »). Elle est stockée sur ce poste
   seulement (`api_keys.json` dans le dossier de données), jamais affichée ni tracée, et envoyée au
   seul hôte déclaré. Si l'adresse du fournisseur change, la clé est à ressaisir. Une clé
   enregistrée ou changée ici s'applique tout de suite, y compris au modèle cloud déjà actif dans
   le harnais : inutile de relancer WaveStack (une variable d'environnement, elle, demande une
   relance, voir ci-dessous).

   **Mistral : un plan d'abord.** Avant le premier appel, activez un plan dans la console
   Mistral, « Experiment » (gratuit) ou payant : sans plan, le compte n'a aucun quota et chaque
   appel répond 429 (« Aucun quota actif sur ce compte »).

   **Ou par variable d'environnement.** Chaque préréglage nomme une variable (`key_env`) :
   `GROQ_API_KEY` pour Groq, `MISTRAL_API_KEY` pour Mistral, `GEMINI_API_KEY` pour Gemini et
   Gemma (même clé), `ANTHROPIC_API_KEY` pour Claude (Haiku et Sonnet, même clé) et
   `OPENAI_API_KEY` pour GPT-6 Luna. Sous Windows, sans droits administrateur :

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
3. **Choisir.** « Choisir ce modèle… » affiche l'avertissement « Ce modèle tourne hors de votre
   poste » (ce qui part, ce qu'en fait le fournisseur, ce
   que le harnais ne voit plus) ; « Utiliser ce modèle » le confirme. Le choix est repris aux
   lancements suivants, sans nouvel avertissement. Choisi après le chargement d'un modèle, il le
   remplace sans relance (voir [Changer de modèle](#changer-de-modèle)).

### Particularités des fournisseurs

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
brique : allumé, `thinking_level` « high » et le texte de la réflexion (entre `<thought>` et
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

**Claude (Anthropic, API Messages).** `claude_haiku` (`claude-haiku-4-5`, 200 000 tokens,
1 $ / 5 $ par million de tokens) et `claude_sonnet` (`claude-sonnet-5`, 1 000 000 tokens,
2 $ / 10 $) passent par l'API native d'Anthropic (`api = "anthropic_messages"`), pas par une
couche compatible OpenAI : elle seule renvoie le raisonnement et accepte les outils avec lui.
Clé : `ANTHROPIC_API_KEY` ou saisie au diagnostic (envoyée dans l'en-tête `x-api-key`).
Conditions relevées le 2026-10-03 : les données de l'API ne servent pas à l'entraînement sans
permission expresse et sont supprimées sous 30 jours ; inférence « global » par défaut (ou
« us »), stockage aux États-Unis, pas de résidence dans l'UE. Brique Raisonnement allumée :
Haiku raisonne avec un budget de 1 024 tokens, Sonnet en mode adaptatif (il décide s'il
raisonne), raisonnement résumé ; le résumé s'affiche au canal Raisonnement. Les blocs de
raisonnement reçus repartent tels quels, signature comprise, au seul modèle qui les a produits.
WaveStack réécrivant l'historique par conception (fenêtre, troncature, compression, mémoire,
briques changées), chaque requête demande à Anthropic de jeter un raisonnement devenu invalide
plutôt que de refuser l'appel ; quand il le fait, le journal le dit (« Raisonnement jeté », avec
la cause). Seuls les modèles qui font ce contrôle d'historique (Opus 5.5, Fable 5.1) peuvent
produire cette ligne : avec les préréglages actifs, Haiku 4.5 et Sonnet 5, elle n'apparaît pas.
La température (Atelier LLM, Haiku seulement) ne part que raisonnement éteint : Anthropic la
refuse avec le raisonnement. Pas de top-p : Haiku 4.5 refuse la température et le top-p
ensemble. Le cache de prompt d'Anthropic
n'est jamais activé. Opus 5.5 figure en commentaire dans `wavestack.toml` (son raisonnement ne
s'éteint pas). Un compte sans crédit est refusé avec « le crédit du compte est épuisé » :
ajoutez du crédit dans la console Anthropic (forme de l'erreur lue dans la documentation
d'Anthropic, non mesurée).

**GPT-6 Luna (OpenAI, API Responses).** `openai_luna` (`gpt-6-luna`, 1 050 000 tokens,
0,10 $ / 0,50 $ par million de tokens, cache lu 0,01 $) passe par l'API Responses d'OpenAI
(`api = "openai_responses"`) : par Chat Completions, GPT-6 n'appelle d'outils que raisonnement
éteint et ne renvoie jamais son raisonnement. WaveStack l'utilise sans état (`store: false`,
jamais `previous_response_id`) : tout l'historique part à chaque appel, comme pour les autres
fournisseurs. Clé : `OPENAI_API_KEY` ou saisie au diagnostic (en-tête `Authorization: Bearer`).
Conditions relevées le 2026-10-03 : les données de l'API ne servent pas à l'entraînement par
défaut ; OpenAI garde des journaux de lutte contre les abus jusqu'à 30 jours, même sans
stockage des réponses, et le cache de prompt 24 heures par défaut (`prompt_cache_retention`
relevé sur l'API) ; la résidence dans l'UE demande un projet dédié et l'hôte
`eu.api.openai.com` (non préréglé). Brique Raisonnement allumée : effort « low » et résumé
automatique, affiché au canal Raisonnement ; éteinte : effort « none » (Luna n'a pas
« minimal »). Le raisonnement reçu (items `reasoning` chiffrés) repart tel quel au seul modèle
qui l'a produit. OpenAI peut exiger la vérification de l'organisation (console OpenAI) avant
d'envoyer les résumés de raisonnement : sans elle, le canal Raisonnement reste vide. Température
et top-p (Atelier LLM) ne partent que raisonnement éteint : OpenAI les refuse avec le
raisonnement. Un compte sans crédit est refusé avec « le crédit du compte est épuisé » :
ajoutez du crédit dans la console OpenAI.
GPT-6.1 Sol figure en commentaire dans `wavestack.toml` (il raisonne toujours).

### Revenir au modèle local

Choisissez un fichier GGUF dans le sélecteur de la barre du bas, ou
cliquez sur « Choisir ce modèle » dans la carte d'un fichier, page Diagnostic : le modèle local est
rechargé sans relance, conversation gardée.

### Hôtes à autoriser

Sur le réseau de l'entreprise : `api.groq.com`, `api.mistral.ai`,
`generativelanguage.googleapis.com`, `api.anthropic.com` et `api.openai.com` (plus l'hôte de tout modèle ajouté dans `settings.json`).

### Ajouter ou modifier un modèle

Les exemples NVIDIA et OpenRouter de `wavestack.toml` sont en TOML :
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

`hosting_text` et `notes_text` sont saisis par l'opérateur, dans `wavestack.toml` ou
`settings.json`, et affichés tels quels dans l'avertissement et le bandeau du modèle cloud,
dans toutes les langues de l'interface, y compris après un changement de langue en cours de
séance : ils n'ont pas de traduction. Ceux des préréglages sont
en français ; pour une séance en anglais ou en allemand, redéclarez-les dans `settings.json`
dans la langue de la séance (par exemple `{"id": "groq", "hosting_text": "United States (Groq)"}`).

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
- `sampling` (Atelier LLM) : les réglages d'échantillonnage que le modèle accepte, parmi
  `"temperature"` et `"top_p"` (les deux champs de l'API compatible OpenAI) ; vide par défaut :
  le fournisseur garde les siens. Les préréglages Groq et Mistral déclarent les deux. Seul l'Atelier
  LLM les envoie ; les tours de l'atelier n'envoient aucun réglage, et top-k et min-p ne
  partent jamais chez un fournisseur.
- `pricing` (voir [FinOps](guide.md#finops-coût-estimé-des-appels-cloud)) : les prix du modèle, par exemple
  `"pricing": {"input_usd_per_mtok": 0.15, "output_usd_per_mtok": 0.6, "checked": "2026-09-29"}`.
- `impacts` (voir [GreenOps](guide.md#greenops-empreinte-estimée-des-appels-au-modèle)) : le modèle tel qu'EcoLogits le connaît, par exemple
  `"impacts": {"provider": "mistralai", "model": "mistral-small-latest", "zone": "FRA"}`.
