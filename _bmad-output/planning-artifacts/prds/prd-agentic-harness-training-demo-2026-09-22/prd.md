---
title: PRD — WaveStack
status: final
created: 2026-09-22
updated: 2026-09-24
---

# PRD : WaveStack

*Démonstrateur pédagogique de harnais agentique. Les hypothèses restantes sont marquées `[ASSUMPTION]` et reprises au §11, avec la personne chargée de les trancher et le moment prévu.*

## 0. Objet du document

Ce PRD s'adresse à Anaël, porteur du produit, et aux étapes BMAD qui suivent : UX (`bmad-ux`), architecture (`bmad-architecture`), puis epics et stories. Il s'appuie sur le brief validé (`briefs/brief-agentic-harness-training-demo-2026-09-22/brief.md`) et sur son addendum, sans les reproduire.

Organisation :
- le vocabulaire est fixé au §3 (Glossaire) ;
- les fonctionnalités sont regroupées au §4, avec des exigences fonctionnelles (FR) numérotées globalement ;
- les exigences non fonctionnelles transverses sont au §5.

Le détail technique (pistes de moteur d'inférence, bibliothèques, veille) est dans `addendum.md` et `research-landscape.md`.

## 1. Vision

WaveStack rend visible, brique par brique, ce qu'un harnais agentique fait à un modèle de langage :
- le formateur part d'un LLM nu ;
- il active les briques une à une : raisonnement, mémoire courte, prompt système, mémoire globale, outils, RAG, MCP, skills, hooks, sous-agent, compression du contexte ;
- sur le même écran, les participants voient à la fois ce que voit un utilisateur de chatbot et ce que le harnais envoie réellement au modèle, décide et exécute.

L'enjeu n'est pas la qualité des réponses mais la compréhension. Les collègues de Wavestone utilisent des chatbots, mais ne distinguent pas un LLM nu d'un LLM outillé et confondent skill, plugin, outil et MCP. Ils peinent donc à se poser la question clé de leurs missions de sécurité, de souveraineté et de conformité : **où sont hébergés le harnais, les données et le modèle ?** WaveStack leur donne le vocabulaire et les repères pour raisonner sur l'agentique. Il les aide aussi à imaginer des cas d'usage dans leur métier.

WaveStack tourne entièrement en local, sur CPU, avec de petits modèles (SLM). Il incarne ainsi ce qu'il enseigne sur la souveraineté et le numérique responsable.

Aucun outil existant ne réunit ces éléments dans une même interface locale en français :
- l'activation progressive des briques ;
- la double vue sur le contexte réel ;
- la couverture des skills, hooks et sous-agents.

Trajectoire :
1. Former 50 à 100 personnes de la BU d'Anaël.
2. Si le résultat est probant, en faire un démonstrateur client et un support de vente de formations.

## 2. Utilisateurs cibles

### 2.1 Jobs To Be Done

**Formateur (Anaël, puis d'autres formateurs)**
- Faire comprendre en une session ce qu'apporte chaque brique d'un harnais, sans slides abstraites, en montrant l'effet en direct.
- Enchaîner une démonstration fiable malgré un modèle faible, sans se retrouver bloqué devant la salle.
- Réutiliser le même outil en clientèle pour vendre une formation ou illustrer une recommandation.

**Participant (consultant d'une practice : cloud, cyber, IAM, DLP, SOC, souveraineté, agile, PO, BA, numérique responsable…)**
- Pouvoir expliquer à un client ce qu'est un harnais, un skill, un MCP ou un hook, et ce que chacun ajoute à un LLM nu.
- Distinguer prompt engineering, context engineering et harness engineering.
- Savoir interroger une solution tierce sur l'hébergement du harnais, des données et du modèle.
- Repartir avec au moins une idée d'application agentique pour son métier.
- *(Nouvel arrivant)* Comprendre d'abord ce qu'est un LLM nu, avant l'agentique.

### 2.2 Non-utilisateurs (V1)

- Les clients en autonomie : la démo client, menée par un formateur, est une cible V2.
- Les développeurs qui cherchent un framework agentique réutilisable : WaveStack est un outil pédagogique, pas une bibliothèque.
- Les personnes qui évaluent la qualité d'un modèle : ce n'est pas un banc d'essai.

### 2.3 Parcours utilisateurs clés

*Déroulé par défaut d'une session : le formateur est seul aux commandes, WaveStack est projeté. Une session dure de 30 min à 1 h ; le programme complet se découpe en modules, répartis sur plusieurs sessions pour découvrir les briques progressivement. Quelques profils techniques installeront WaveStack sur leur poste, en amont ou après, en suivant le README.*

- **UJ-1. Anaël anime une session et fait émerger le « déclic MCP ».**
  - *Contexte.* Anaël forme douze consultants de la BU en salle, pour un premier module d'une heure. WaveStack tourne sur son portable, projeté.
  - *Lancement.* Il lance WaveStack d'une commande et part du LLM nu. Il demande l'heure : le modèle invente, et la vue harnais montre que seul le message a été envoyé, dans le gabarit de conversation.
  - *Premières briques.* Il active la mémoire courte, puis le prompt système. Il rejoue le même prompt : le contexte grossit sous les yeux de la salle, compteur de tokens à l'appui.
  - *Outils.* Il active les outils. Le schéma d'architecture s'anime : le modèle demande l'outil « heure » et le harnais l'exécute puis réinjecte le résultat.
  - *Déclic.* Il active un serveur MCP public. Le schéma montre qu'un composant sort du poste. Un participant demande « donc là, mes données partent où ? ». La salle a compris la question de l'hébergement.
  - *Fin.* Il réinitialise WaveStack pour la session suivante.
  - *Cas limite.* Le modèle produit un appel d'outil mal formé. La vue harnais montre l'échec du parsing et ce que le harnais en fait. Anaël s'en sert comme illustration plutôt que de le subir.
- **UJ-2. Karim, consultant SOC, reprend WaveStack seul après la session.**
  - *Contexte.* Karim veut vérifier ce qu'un hook peut bloquer.
  - *Installation.* Il installe WaveStack sur son poste professionnel sans droits admin, en suivant la procédure en français. Il lance le scénario « Hooks ».
  - *Test.* Il modifie le prompt pour que le modèle tente de lire un fichier sensible ; si le modèle ne s'y risque pas, Karim force l'appel (FR-42). Le hook de garde-fou bloque l'appel d'outil, et la vue harnais indique que c'est du code du harnais, pas le modèle, qui a décidé.
  - *Résultat.* Karim note une idée de cas d'usage pour la détection d'incidents.
- **UJ-3. Léa, consultante cloud, installe WaveStack sur un poste verrouillé avant la session.**
  - *Installation.* Elle suit le README. Le proxy bloque le téléchargement du modèle depuis Hugging Face. Le diagnostic de démarrage le signale en français et propose la voie hors ligne : copier le fichier du modèle depuis un partage fourni par le formateur.
  - *Résultat.* Léa relance, WaveStack démarre, et le diagnostic est vert.
- **UJ-4 (usage client en V2, scénario livré en V1). Anaël montre WaveStack à un client RSSI.**
  - Anaël ouvre directement le scénario « Où vont mes données ? ». Dès le lancement (story 27), sont actifs :
    - un outil local ;
    - un MCP local ;
    - un MCP public.
  - Le schéma d'architecture distingue ce qui reste sur le poste de ce qui en sort ; décocher puis recocher le MCP public fait disparaître puis revenir le seul flux sortant. La démo se fait sans adaptation du produit.
- **UJ-5. Sophie, consultante conformité, voit d'où vient la réponse.**
  - *Contexte.* Module RAG, en salle. Le corpus de démonstration est déjà indexé.
  - *Recherche.* Anaël pose une question dont la réponse se trouve dans un seul document. La réponse s'affiche dans la vue humain. Le volet contexte LLM montre trois extraits, avec leur score et leur place dans le contexte.
  - *Reranking.* Anaël active le reranking : le volet orchestration montre l'ordre des extraits avant et après.
  - *Temps fort.* Sophie remarque dans le schéma d'architecture que l'index est un fichier local : « donc le RAG, ce n'est pas le modèle qui sait, c'est le harnais qui cherche ».
- **UJ-6. Anaël délègue une lecture à un sous-agent et montre l'économie de contexte.**
  - *Délégation.* Anaël demande au modèle de lire une page courte de documentation publique, par exemple le glossaire de la documentation d'Anthropic, puis d'en tirer trois questions de quiz. Le modèle délègue la lecture de la page à un sous-agent, ou Anaël force la délégation (FR-42).
  - *Deux contextes.* Le volet contexte LLM permet de basculer entre le contexte principal et celui du sous-agent.
  - *Temps fort.* La jauge montre que seul le résumé, quelques centaines de tokens, entre dans le contexte principal. La page complète, environ 2 000 tokens, est restée dans le contexte du sous-agent.
- **UJ-7. Anaël compresse ce qui entre, puis ce qui sort.**
  - *Compression.* Anaël rejoue une question dont le résultat d'outil est volumineux, par exemple la lecture d'une page web, cette fois avec la compression du contexte (FR-31). Le volet contexte LLM montre le contexte avant et après, avec le nombre de tokens de chaque version. La latence de chaque tour s'affiche.
  - *Caveman.* Il déclenche ensuite Caveman et rejoue la même question (FR-7) : les tokens de sortie chutent, l'information reste.
  - *Temps fort.* La salle voit la symétrie : Headroom réduit ce qui entre, Caveman ce qui sort. En local, l'enjeu se compte en secondes, pas en euros.

## 3. Glossaire

*Ces termes sont utilisés tels quels dans le reste du document et en aval.*

- **Modèle** : le modèle de langage local (SLM) qui génère les réponses. Un seul modèle est actif à la fois.
- **LLM nu** : le modèle sollicité sans aucune brique. Chaque message est envoyé seul, avec le seul gabarit de conversation du modèle.
- **Harnais** : tout le code autour du modèle, qui assemble le contexte, appelle le modèle, interprète sa sortie, exécute des actions et décide de continuer ou de s'arrêter.
- **Brique** : une capacité du harnais que l'on peut activer ou désactiver indépendamment. Liste V1 : raisonnement, mémoire courte, prompt système, mémoire globale, outils, RAG, MCP, skills, hooks, sous-agent, compression du contexte.
- **Tour** : un cycle complet, du message de l'utilisateur jusqu'à la réponse finale. Un tour peut contenir plusieurs appels au modèle.
- **Contexte** : l'ensemble exact des tokens envoyés au modèle lors d'un appel. Il est composé de segments, chacun attribué à la brique qui l'a produit.
- **Fenêtre de contexte** : le nombre maximal de tokens que le contexte peut atteindre. WaveStack la plafonne en dessous de la limite du modèle.
- **Vue humain** : le volet qui montre la conversation telle qu'un utilisateur de chatbot la voit.
- **Vue harnais** : l'ensemble des deux volets contexte LLM et orchestration, qui montrent ce que le harnais a réellement fait à chaque tour.
- **Contexte LLM** : le volet qui montre le contexte exact de chaque appel au modèle, segmenté par brique, et la sortie brute du modèle.
- **Orchestration** : le volet qui montre les étapes d'un tour dans l'ordre, les événements du harnais (hooks, échecs, dépassements) et les échanges avec les serveurs MCP.
- **Schéma d'architecture** : le volet qui représente les composants actifs (modèle, harnais, briques, serveurs MCP, données) et leur lieu d'hébergement. Il s'anime pendant un tour.
- **Panneau des briques** : le volet où l'on active ou désactive les briques.
- **Lieu d'hébergement** : où un composant s'exécute ou réside. Trois lieux : processus local, fichier local, service réseau.
- **Outil** : une fonction exécutée par le harnais à la demande du modèle.
- **Serveur MCP** : un processus séparé qui expose des outils via le protocole MCP. Il est local (sur le poste) ou public (accessible par le réseau).
- **Skill** : un ensemble d'instructions et de ressources que le harnais charge dans le contexte à la demande. Seuls le nom et la description sont présents tant que le skill n'est pas déclenché.
- **Hook** : du code du harnais, déterministe, exécuté automatiquement à un événement du tour. Le modèle ne le décide pas.
- **Sous-agent** : un second agent, qui réutilise le modèle déjà chargé avec son propre contexte, auquel le harnais délègue une sous-tâche. Seul son résultat revient dans le contexte principal.
- **Mémoire courte** : la réinjection des messages précédents de la conversation en cours.
- **Mémoire globale** : les informations conservées d'une conversation à l'autre et réinjectées dans le contexte.
- **Compression du contexte** : la réduction du contexte avant l'appel au modèle, démontrée avec Headroom si le test préalable le valide, sinon avec un compresseur minimal du harnais.
- **Caveman** : un skill de démonstration, déclenchable par le modèle ou directement par l'utilisateur, qui fait répondre le modèle en style télégraphique pour réduire les tokens de sortie.
- **Scénario** : une séquence préparée de configuration des briques et de prompts, qui illustre une brique ou un message pédagogique.
- **Programme** : la suite ordonnée des scénarios, du LLM nu au harnais complet. Il se découpe en modules, chacun tenant dans une session de formation de 30 min à 1 h.
- **Rejeu d'un prompt** : le renvoi du dernier message avec une autre configuration de briques, à partir de l'état qui précédait le tour d'origine, pour comparer deux tours (FR-7).
- **Formateur** : la personne qui anime une session de formation avec WaveStack.
- **Participant** : une personne formée, qui regarde WaveStack projeté. Certains profils techniques l'installent aussi sur leur poste.
- **Utilisateur** : toute personne aux commandes de WaveStack, formateur ou participant qui l'a installé sur son poste.
- **Poste de référence** : le PC professionnel sur lequel les exigences de performance sont mesurées : HP EliteBook (édition Bang & Olufsen), Windows 11, Intel Core i5 vPro, sans GPU dédié, 16 Go de RAM.

## 4. Fonctionnalités

### 4.1 Interface à volets synchronisés

**Description.** WaveStack est une application web locale, ouverte dans le navigateur du poste. L'écran juxtapose cinq volets ; l'utilisateur peut masquer et réafficher chacun d'eux :
- panneau des briques ;
- vue humain ;
- contexte LLM (vue harnais) ;
- orchestration (vue harnais) ;
- schéma d'architecture.

Les volets restent synchronisés : sélectionner un segment du contexte met en évidence la brique et le composant correspondants. La disposition et les interactions sont décrites dans les spécifications UX (`ux-designs/ux-agentic-harness-training-demo-2026-09-22/`). Réalise UJ-1 et UJ-4.

#### FR-1 : Vue humain
L'utilisateur peut converser avec le modèle comme dans un chatbot.
- Les réponses s'affichent au fil de la génération (streaming).
- Un indicateur montre que le modèle travaille pendant les phases sans token visible, comme le traitement du contexte ou l'exécution d'un outil.

#### FR-2 : Vue harnais
Pour chaque tour, l'utilisateur peut inspecter ce que le harnais a réellement fait, dans deux volets visibles en même temps.
- **Contexte LLM :**
  - le volet affiche l'intégralité du contexte de chaque appel au modèle, sans troncature par défaut ;
  - chaque segment du contexte est étiqueté avec la brique qui l'a produit : message et gabarit, prompt système, historique, descriptions d'outils, skills (descriptions, puis contenu une fois déclenchés), extraits RAG, résultats d'outils et du sous-agent, injections de hook, mémoire globale ;
  - la sortie brute du modèle est affichée : raisonnement, texte, appels d'outils.
- **Orchestration :** le volet liste les étapes du tour dans l'ordre : appel au modèle, interprétation de la sortie, exécution, réinjection, décision de continuer ou de s'arrêter, plus les étapes des briques actives. Il affiche aussi les événements du harnais (FR-15, FR-28, NFR-8) et les échanges MCP (FR-22).

#### FR-3 : Schéma d'architecture en direct
L'utilisateur voit les composants actifs et leur lieu d'hébergement. Réalise UJ-1 et UJ-4.
- Seules les briques actives apparaissent dans le schéma.
- Chaque composant indique son lieu d'hébergement : processus local, fichier local ou service réseau. Les composants réseau sont visuellement distincts.
- Pendant un tour, le composant en cours d'action est mis en évidence.
- Les zones qui le permettent se déplient : détail d'un skill, outils exposés par un serveur MCP.

#### FR-4 : Synchronisation des volets
Sélectionner un élément dans un volet met en évidence ses correspondants dans les autres volets.

### 4.2 Panneau des briques et progression

**Description.** Le formateur construit le harnais devant la salle, brique après brique. Chaque brique s'accompagne d'une courte explication en français. Réalise UJ-1.

#### FR-5 : Activation indépendante des briques
L'utilisateur peut activer ou désactiver chaque brique sans redémarrer WaveStack.
- Le changement prend effet au tour suivant.
- Quand toutes les briques sont désactivées, WaveStack se comporte exactement comme le LLM nu.
- Une brique qui dépend d'une autre indique pourquoi elle est indisponible. Par exemple, le lazy loading MCP exige la brique MCP.

#### FR-6 : Explication pédagogique de chaque brique
Chaque brique présente :
- ce qu'elle ajoute au LLM nu, en deux ou trois phrases ;
- sa catégorie : prompt engineering, context engineering ou harness engineering ;
- le lieu d'hébergement des composants qu'elle introduit.

La boucle agent (raisonner, agir, observer, décider de continuer) est présentée comme le cœur du harness engineering, et non comme une quatrième catégorie. Les termes émergents, comme loop engineering et agentic engineering, sont cités et datés dans les contenus pédagogiques, sans devenir des catégories.

#### FR-7 : Rejouer un prompt avec une autre configuration
L'utilisateur peut rejouer le dernier prompt après avoir changé les briques, puis comparer les deux tours.
- Le rejeu renvoie le même message de l'utilisateur avec la nouvelle configuration.
- Le contexte est reconstruit à partir de l'état qui précédait le tour d'origine : la question et la réponse d'origine n'y figurent pas, sinon le modèle verrait la question deux fois et la comparaison serait faussée.
- L'historique est restauré dans cet état ; la mémoire globale, elle, reste dans son état courant.
- Les deux tours restent consultables côte à côte, pour comparer leurs contextes et leurs nombres de tokens.
- La conversation continue à partir du tour rejoué.
- Un tour rejoué peut lui-même être rejoué ; l'utilisateur compare alors deux tours de son choix.
- Une action forcée avant le rejeu (FR-42), comme le déclenchement de Caveman, s'applique au tour rejoué.

#### FR-42 : Déclenchement par le modèle, ou forcé
Certaines actions sont décidées par le modèle :
- appeler un outil précis, avec ses arguments (FR-14), par exemple lire le fichier sensible du dossier de démonstration (FR-27) ;
- écrire en mémoire globale (FR-12) ;
- charger la documentation d'un outil MCP en lazy loading (FR-21) ;
- déclencher un skill (FR-24) ;
- déléguer à un sous-agent (FR-29).

Quand le modèle ne les déclenche pas, l'utilisateur peut les forcer depuis l'interface, pour que la démonstration aboutisse malgré un SLM faible.
- Une action forcée suit tout le cycle du harnais, hooks compris, comme une action décidée par le modèle.
- Le volet orchestration indique qui a déclenché l'action : « déclenché par le modèle » ou « forcé par l'utilisateur ».

### 4.3 Briques de base

**Description.** Ces briques posent les fondations. Elles servent surtout aux nouveaux arrivants et aux clients. Réalise UJ-1.

#### FR-8 : LLM nu
Sans aucune brique, chaque message est envoyé seul au modèle.
- La vue harnais montre que le contexte ne contient que le message et le gabarit de conversation.
- Une question qui suppose une mémoire ou un outil (« quelle heure est-il ? », « qu'ai-je dit avant ? ») met la limite en évidence.

#### FR-9 : Raisonnement
L'utilisateur peut activer le mode raisonnement du modèle, et afficher ou masquer ce raisonnement dans la vue humain.
- Dans la vue harnais, le raisonnement est toujours visible.
- Si le modèle actif ne sait pas raisonner, la brique est indisponible et l'interface explique pourquoi.

#### FR-10 : Mémoire courte
Les messages précédents de la conversation sont réinjectés dans le contexte.
- Le compteur de tokens montre le contexte qui grossit à chaque tour.
- L'utilisateur peut vider la conversation.

#### FR-11 : Prompt système
Un prompt système par défaut, en français, est fourni.
- L'utilisateur peut le modifier depuis l'interface.
- La modification est visible dans le contexte au tour suivant.

#### FR-12 : Mémoire globale
Des informations sont conservées d'une conversation à l'autre et réinjectées dans le contexte.
- L'utilisateur peut consulter, modifier et effacer la mémoire globale.
- La vue harnais montre quand et comment la mémoire est injectée, et comment elle est écrite. L'écriture est décidée par le modèle, ou forcée (FR-42).
- Le schéma d'architecture indique où la mémoire est stockée (fichier local).

### 4.4 Outils

**Description.** Le modèle demande un outil ; le harnais l'exécute et réinjecte le résultat. C'est le premier moment où le LLM « agit ». Réalise UJ-1.

#### FR-13 : Catalogue d'outils
WaveStack fournit un catalogue d'outils activables individuellement. Liste V1, choisie pour être simple à réaliser et parlante en démonstration :
- **hors ligne** :
  - heure et date : le LLM nu ne peut pas les connaître ;
  - calculatrice : un SLM calcule mal de tête ;
  - lecture de fichier dans un dossier de démonstration : c'est la cible du hook de garde-fou (FR-27) ;
- **réseau**, via des API publiques gratuites et sans clé :
  - jours fériés français, à combiner avec l'outil heure dans un même tour ;
  - résumé d'une page Wikipedia ;
  - lecture d'une page web publique, convertie en texte : fournit le résultat volumineux du sous-agent (UJ-6) et de la compression (UJ-7).
    - L'outil n'accepte que les adresses autorisées dans la configuration, et coupe la page au-delà d'une taille maximale.
    - L'adresse demandée sort du poste, et une adresse peut transporter des données : le volet orchestration l'affiche comme toute donnée sortante (FR-22).
    - Sans réseau, un long fichier du dossier de démonstration remplace la page.
- Le catalogue contient au moins un outil qui fonctionne hors ligne et au moins un outil réseau.
- Chaque outil réseau est signalé comme tel dans le panneau des briques et dans le schéma d'architecture.

Recherche web, envoi d'email et génération de graphiques sont reportés en V2 : ils demandent une clé, ont des effets de bord ou alourdissent l'interface.

#### FR-14 : Cycle d'appel d'outil visible
La vue harnais montre le cycle complet d'un appel d'outil :
1. la description de l'outil dans le contexte ;
2. la demande d'appel émise par le modèle ;
3. l'exécution par le harnais ;
4. la réinjection du résultat ;
5. la réponse finale.

#### FR-15 : Échecs d'appel visibles
Quand le modèle émet un appel d'outil mal formé ou inexistant, la vue harnais montre l'échec du parsing et la réaction du harnais : nouvel essai, message d'erreur réinjecté ou arrêt. Réalise le cas limite d'UJ-1.
- Un appel mal formé ne fait jamais planter WaveStack.

### 4.5 RAG

**Description.** Le harnais retrouve des extraits de documents et les injecte dans le contexte, avec d'abord un RAG simple, puis un reranking. Réalise UJ-5.

#### FR-16 : Corpus de démonstration
WaveStack fournit un corpus de démonstration en français, prêt à l'emploi. L'indexation de documents propres à l'utilisateur est reportée en V2.
- L'index est stocké localement, et le schéma d'architecture l'indique comme fichier local.

#### FR-17 : RAG simple visible
Pour chaque tour, la vue harnais affiche :
- la requête de recherche ;
- les extraits retrouvés, avec leur score ;
- leur position dans le contexte.

#### FR-18 : Reranking
L'utilisateur peut activer le reranking. Le volet orchestration montre alors l'ordre des extraits avant et après le reranking.

### 4.6 MCP

**Description.** La brique MCP est au cœur pédagogique de WaveStack, avec les skills et les hooks. Elle montre qu'un serveur MCP est un processus séparé, éventuellement distant, qui expose des outils. Elle montre aussi comment le chargement de leur documentation pèse sur le contexte. Réalise UJ-1 et UJ-4.

#### FR-19 : Serveur MCP local
WaveStack fournit au moins un serveur MCP local, lancé automatiquement.
- Il fonctionne hors ligne et sans droits admin.
- Le schéma d'architecture le montre comme un processus local distinct du harnais.

#### FR-20 : Serveur MCP public
WaveStack peut se connecter à au moins un serveur MCP public, gratuit et sans clé d'API :
- serveur principal : le serveur MCP de **data.gouv.fr**, qui donne accès aux données publiques françaises et intéresse le secteur public et la souveraineté ;
- serveur secondaire : **Microsoft Learn**, qui donne accès à la documentation Azure et Entra ID et parle aux practices cloud et IAM.

Leurs descriptions d'outils pèsent respectivement environ 2 900 et 1 250 tokens : l'écart avec le lazy loading (FR-21) se voit nettement.
- Le schéma d'architecture montre le serveur public comme un service réseau.
- Chaque serveur public est traité séparément : s'il ne répond pas au démarrage, ou sans réseau, il est indisponible jusqu'à une nouvelle tentative, et l'interface explique pourquoi. Les autres serveurs, dont le serveur MCP local, restent utilisables.
- Même indisponible, le serveur public reste dessiné dans le schéma d'architecture, marqué comme tel, pour que le message sur l'hébergement demeure visible.

#### FR-21 : Documentation complète contre lazy loading
L'utilisateur peut basculer entre deux modes :
- **documentation complète** : toutes les descriptions d'outils MCP sont chargées dans le contexte ;
- **lazy loading** : le harnais ne charge la documentation d'un outil qu'à la demande du modèle, ou quand l'utilisateur la force (FR-42).

Le compteur de tokens montre l'écart entre les deux modes pour un même prompt.

#### FR-22 : Échanges MCP visibles
La vue harnais montre les échanges avec les serveurs MCP : découverte des outils, appel, résultat.
- Elle distingue un outil MCP d'un outil natif du harnais.
- Pour un serveur MCP public, comme pour un outil réseau (FR-13), elle affiche l'adresse de destination et les données exactement envoyées hors du poste.

### 4.7 Skills

**Description.** Un skill est un paquet d'instructions et de ressources que le harnais ne charge qu'au besoin. La brique montre en quoi un skill diffère d'un outil, d'un serveur MCP et d'un prompt système.

#### FR-23 : Catalogue de skills
WaveStack fournit au moins deux skills de démonstration activables, dont Caveman.

#### FR-24 : Chargement progressif visible
Tant qu'un skill n'est pas déclenché, seuls son nom et sa description figurent dans le contexte. Une fois déclenché, par le modèle ou par l'utilisateur (FR-42), son contenu est chargé.
- La vue harnais montre les deux états.
- Le compteur de tokens montre l'écart.

#### FR-25 : Caveman
L'utilisateur peut déclencher le skill Caveman comme n'importe quel skill, puis comparer le nombre de tokens de sortie à la même question sans Caveman (voir FR-7).
- Une version simplifiée du skill est acceptable si elle illustre le concept : moins de tokens de sortie, même information utile.

### 4.8 Hooks

**Description.** Un hook est du code déterministe du harnais. Il s'exécute à un événement du tour, sans décision du modèle. La brique parle directement aux practices cyber, DLP et IAM : garde-fous, journalisation, contrôle. Réalise UJ-2.

#### FR-26 : Événements de hook
Des hooks peuvent s'exécuter aux événements suivants :
1. à la réception du message de l'utilisateur ;
2. avant l'appel au modèle ;
3. avant l'exécution d'un outil ;
4. après l'exécution d'un outil ;
5. en fin de tour.

#### FR-27 : Hooks de démonstration
WaveStack fournit quatre hooks de démonstration, simples à réaliser et parlants pour les practices. Chacun s'active et se désactive séparément dans la brique hooks : on compose les contrôles selon les besoins. Chaque scénario fixe la liste de ses hooks actifs.
- **H1, garde-fou fichier sensible** (avant l'exécution d'un outil) : bloque la lecture d'un fichier du dossier confidentiel de démonstration. C'est le harnais qui dit non, pas le modèle. Réalise UJ-2.
- **H2, journal d'audit** (après l'exécution d'un outil, en fin de tour) : consigne chaque appel au modèle et chaque appel d'outil, horodatés, dans un fichier local visible. Le schéma d'architecture montre ce fichier. Sert le scénario SOC (FR-40).
- **H3, injection de contexte** (à la réception du message) : ajoute automatiquement la date et les règles de la mission au message. Même effet que l'outil « heure », mais sans décision du modèle : deux architectures possibles pour un même besoin.
- **H5, validation humaine** (avant l'exécution d'un outil réseau) : suspend l'appel jusqu'à l'accord de l'utilisateur, qui voit l'outil, la destination et les données qui sortiraient du poste. Un refus est réinjecté dans le contexte et le tour continue. Illustre le principe « humain dans la boucle » (human in the loop), comme les permissions de Claude Code. Ce hook se désactive d'un geste, pour n'en faire la démonstration qu'une fois.

#### FR-28 : Déclenchement visible
Le volet orchestration montre chaque déclenchement de hook : événement, décision et effet sur le tour. Les décisions possibles sont : laisser passer, bloquer, modifier, demander une validation humaine.
- L'interface indique explicitement que la décision vient du harnais et non du modèle.

### 4.9 Sous-agent

**Description.** La V1 contient un **sous-agent simple** : une délégation unique, sans dialogue entre agents. Il montre l'isolation du contexte. Le multi-agent collaboratif reste en V2. Réalise UJ-6.

#### FR-29 : Délégation à un sous-agent
Le harnais peut déléguer une sous-tâche à un sous-agent qui a son propre contexte. La délégation est demandée par le modèle, ou forcée (FR-42).
- Le contexte du sous-agent et le contexte principal sont inspectables séparément.
- Seul le résultat du sous-agent entre dans le contexte principal. Le compteur de tokens montre l'économie réalisée.
- Le sous-agent peut appeler des outils ; ses appels suivent le même cycle, hooks compris.

### 4.10 Tokens et compression du contexte

**Description.** Le compteur de tokens est le fil rouge du context engineering. La compression du contexte démontre qu'on peut réduire ce qui *entre* dans le modèle, en miroir de Caveman qui réduit ce qui *sort*. En local, le gain se mesure en latence plutôt qu'en coût. Réalise UJ-7.

#### FR-30 : Compteur de tokens
Pour chaque appel au modèle, WaveStack affiche :
- le nombre de tokens du contexte, au total et par segment, donc par brique ;
- le nombre de tokens de sortie ;
- le temps écoulé.

#### FR-31 : Compression du contexte
L'utilisateur peut activer la compression du contexte, démontrée avec Headroom si le test préalable le valide (fonctionnement hors ligne, dans le budget mémoire), sinon avec un compresseur minimal du harnais. La vue harnais montre alors le contexte avant et après compression, avec le nombre de tokens de chaque version.
- La compression porte au moins sur les résultats d'outils et les extraits RAG.

#### FR-41 : Jauge de remplissage du contexte
WaveStack affiche en permanence le taux de remplissage de la fenêtre de contexte, à l'image de la commande `/context` de Claude Code.
- La jauge est ventilée selon les segments de FR-2, plus l'espace libre.
- Elle se met à jour à chaque appel au modèle, y compris pendant les étapes d'un même tour.
- Quand la fenêtre approche de sa limite, la jauge le signale.
- Si le contexte dépasse la fenêtre, l'appel n'est pas envoyé au modèle (NFR-8).

### 4.11 Choix du modèle

**Description.** Le modèle doit pouvoir changer facilement, pour suivre l'évolution des SLM et s'adapter au poste.

#### FR-32 : Changer de modèle
L'utilisateur peut changer de modèle depuis l'interface ou la configuration, sans modifier le code.
- Le changement se fait entre deux tours, sans redémarrer WaveStack, avec un indicateur de chargement.
- La conversation est conservée : le harnais reconstruit le contexte à chaque tour.
- WaveStack fournit un modèle par défaut de 2B paramètres au plus.

#### FR-33 : Capacités du modèle
WaveStack connaît les capacités du modèle actif : appel d'outils, raisonnement, taille de contexte, gabarit de conversation. Les briques qui exigent une capacité absente sont indisponibles, et l'interface explique pourquoi.
- Les capacités sont réévaluées à chaque changement de modèle (FR-32).
- Pour un modèle inconnu, les capacités sont lues dans son fichier. Si le fichier ne les indique pas, les briques qui les exigent sont indisponibles, avec une explication.
- L'appel d'outils n'est disponible que pour les familles de modèle dont le format d'appel est connu de WaveStack.

#### FR-34 : Modèle déjà présent sur le poste
L'utilisateur peut utiliser un modèle sans le télécharger. Réalise UJ-3.
- **Fichier local** : il installe un modèle à partir d'un fichier, par exemple depuis un partage ou une clé USB, sans accès à Internet.
- **Fichier déjà présent** : le diagnostic de démarrage et le choix du modèle proposent les fichiers de modèle trouvés dans les emplacements usuels : cache Hugging Face, dossier de modèles de LM Studio, modèles d'Ollama. L'utilisateur peut aussi saisir un chemin.
- **Serveur local déjà lancé** : WaveStack peut utiliser un modèle servi sur le poste par Ollama ou llama.cpp, via son point d'entrée natif en texte brut (Ollama `/api/generate` en mode `raw`, llama-server `/completion`, palier 2). WaveStack construit lui-même le texte envoyé au modèle, gabarit compris, pour que le contexte affiché reste le contexte réel (FR-2). Le schéma d'architecture montre le modèle comme un processus local distinct de WaveStack.

#### FR-43 : Modèle cloud via API
En option, l'utilisateur choisit au diagnostic un modèle cloud déclaré en configuration, pour montrer que le même harnais pilote des modèles plus gros, beaucoup plus vite qu'un SLM sur CPU (palier 1).
- Préréglages Groq et Mistral ; Google, NVIDIA et OpenRouter en exemples de configuration, avec leur avertissement. Un point d'accès interne (Wavestone sur Azure ou GCP) s'ajoute par simple configuration, hors du dépôt.
- Chaque modèle cloud affiche un pictogramme réseau et une infobulle : hébergement, usage des données pour l'entraînement, offre d'essai, quotas renvoyés vers la console du fournisseur.
- Le choisir affiche un avertissement sur ses conséquences (données qui partent, gabarit et appels d'outils traités chez le fournisseur, tokens estimés), à confirmer avant tout appel qui porte des données de l'utilisateur. La barre haute signale ensuite un modèle réseau.
- La clé API est saisie dans l'interface et stockée hors du dépôt. Un bouton « Tester » prouve streaming et appel d'outils avant la séance, avec une invite fixe, sans donnée de l'utilisateur.
- Chaque appel est tracé comme donnée sortante, clé jamais tracée. Un refus du fournisseur (quota dépassé, clé refusée) est un événement expliqué, jamais un plantage.
- Un modèle cloud n'est jamais choisi d'office : un choix explicite mémorisé est repris au lancement, sans réafficher l'avertissement. Les scénarios fournis restent jouables sans clé.

### 4.12 Installation et exploitation sur poste professionnel

**Description.** WaveStack s'installe depuis GitHub sur un poste professionnel verrouillé. Le cas principal est le poste du formateur ; l'installation par les participants est un confort, visé pour les profils techniques. Si l'installation échoue, le repli assumé est la démo pilotée par le formateur, ou la vidéo d'une session précédente. Réalise UJ-2 et UJ-3.

#### FR-35 : Installation sans droits admin
Un utilisateur peut installer WaveStack depuis GitHub, par clone ou par archive zip, sans droits administrateur.
- La procédure est documentée en français.
- Prérequis : Git, ou à défaut une archive zip, et `uv`, qui s'installe sans droits admin et fournit Python.
- Une fois les prérequis en place, l'installation tient en une commande.
- Aucune étape ne demande d'élévation de droits, d'installation de service ni de règle de pare-feu.

#### FR-36 : Lancement en une commande
Une seule commande démarre WaveStack et ouvre l'interface dans le navigateur local.

#### FR-37 : Diagnostic de démarrage
Au démarrage, WaveStack vérifie :
- la mémoire disponible ;
- la présence du modèle, ou des modèles déjà présents sur le poste (FR-34) ;
- l'accès au réseau ;
- la disponibilité du port.

Chaque problème est signalé en français, avec l'action corrective, par exemple la voie hors ligne pour le modèle. Réalise UJ-3.

### 4.13 Scénarios et conduite de session

**Description.** Les scénarios rendent la démonstration reproductible. Le formateur n'improvise pas ses prompts devant la salle et sait qu'ils mettent en valeur la brique malgré un modèle faible. En dernier recours, quand le modèle est trop lent, le formateur projette la vidéo d'une session précédente, enregistrée en réunion Teams. Ce repli ne demande aucune fonctionnalité dans WaveStack.

#### FR-38 : Scénarios par brique et programme
WaveStack fournit au moins un scénario par brique : une configuration de briques et des prompts suggérés.
- L'utilisateur lance un scénario en un clic.
- Au moins un scénario transverse porte sur l'hébergement : « Où vont mes données ? » (UJ-4).
- Les scénarios sont ordonnés en un programme découpé en modules de 30 min à 1 h. L'utilisateur peut démarrer un module directement, avec les briques des modules précédents déjà actives.
- Ordre du programme : LLM nu, raisonnement, mémoire courte, prompt système, mémoire globale, outils, RAG (simple, puis reranking), MCP (documentation complète, puis lazy loading), skills, hooks, sous-agent, compression du contexte.

#### FR-39 : Réinitialisation rapide
L'utilisateur peut revenir en un geste à l'état initial : LLM nu, conversation vide, mémoire globale de démonstration restaurée.

#### FR-40 : Scénarios métier
WaveStack fournit au moins trois scénarios ancrés dans le métier d'une practice, pour aider les participants à imaginer des usages. Contribue à SM-4.
- SOC : un hook journalise les actions de l'agent et bloque une action interdite.
- IAM : une question sur Entra ID, traitée via le serveur MCP Microsoft Learn.
- Souveraineté : une recherche dans les données publiques françaises, via le serveur MCP data.gouv.fr, avec le schéma qui montre ce qui sort du poste.

D'autres métiers s'ajouteront au fil des sessions, sans modifier le code.

## 5. Exigences non fonctionnelles transverses

- **NFR-1 Latence.** Sur le poste de référence, avec le modèle par défaut :
  - un tour LLM nu produit son premier token en moins de 10 s ;
  - avec la configuration la plus chargée d'un scénario fourni, par exemple le MCP en documentation complète, le premier token arrive en moins de 30 s ;
  - dans un tour à plusieurs appels au modèle (outils, sous-agent), ces bornes s'appliquent au premier token de chaque appel. La durée totale du tour n'est pas bornée, mais elle est affichée ;
  - la fenêtre de contexte est plafonnée pour tenir ces bornes et NFR-2 ; le plafond est fixé en architecture ;
  - `[ASSUMPTION]` la génération dépasse 10 tokens/s.

  La latence est toujours rendue visible (voir FR-1 et FR-30), jamais masquée.
  Ces bornes visent les modèles locaux. Pour un modèle cloud (FR-43), aucune borne : premier token, durée et débit sont mesurés et affichés.
- **NFR-2 Empreinte mémoire.** WaveStack tient sur un poste de 16 Go de RAM partagé avec le système d'exploitation et les applications de travail du formateur (visio, navigateur, outils bureautiques).
  - Plafond : 4 Go de RAM pour WaveStack, modèle compris, toutes briques actives. Cible : 2 à 3 Go.
  - `[ASSUMPTION]` Le périmètre mesuré couvre les processus de WaveStack (harnais, modèle, serveurs MCP locaux, index RAG), hors navigateur.
  - Un modèle servi par un serveur local déjà lancé (FR-34) est compté dans ce budget tant que le serveur répond ; jamais deux modèles chargés à la fois.
  - Un modèle cloud (FR-43) ne coûte rien en mémoire ; quand il est actif, le modèle local est libéré.
- **NFR-3 Local et hors ligne.** Toutes les briques fonctionnent sans réseau, sauf celles explicitement marquées réseau (outils réseau, serveur MCP public).
  - Sans réseau, ces briques sont indisponibles avec une explication. Le reste fonctionne normalement.
  - Aucune télémétrie.
- **NFR-4 Confidentialité.** Aucune donnée ne quitte le poste, hormis par une brique réseau activée explicitement, ou par trois sorties limitées hors brique, toutes tracées dans le volet orchestration comme données sortantes :
  - la sonde de connectivité du diagnostic de démarrage (FR-37), vers une adresse fixe, pour vérifier l'accès au réseau ;
  - le téléchargement d'un modèle (FR-34), uniquement sur demande explicite de l'utilisateur.
  - l'appel à un modèle cloud (FR-43) choisi explicitement, test compris ; la clé n'est envoyée qu'à l'hôte déclaré de ce modèle et n'apparaît jamais dans la trace.
  - L'interface n'écoute que sur l'adresse locale, `127.0.0.1`.
  - Aucune clé d'API n'est requise pour les scénarios fournis.
- **NFR-5 Sans droits admin.** Aucune étape d'installation ni d'exécution ne requiert de droits administrateur, ni ne déclenche d'invite du pare-feu.
- **NFR-6 Plateforme.** Cible principale : Windows 11 sur poste professionnel. `[ASSUMPTION]` macOS et Linux sont pris en charge au mieux, sans garantie en V1.
- **NFR-7 Langue.**
  - Interface, explications, scénarios et documentation utilisateur en français.
  - Code et identifiants en anglais.
- **NFR-8 Robustesse en démonstration.** Aucune défaillance du modèle ne fait planter l'application : sortie mal formée, boucle d'appels d'outils ou dépassement de contexte. Chacune est affichée comme un événement lisible dans le volet orchestration.
  - Le harnais borne le nombre d'appels au modèle par tour : 6 au plus, dont 2 nouveaux essais au plus et 4 pour le sous-agent ; une action forcée n'est pas comptée ; la borne est réglable.
  - Si le contexte dépasse la fenêtre, l'appel n'est pas envoyé au modèle. L'événement :
    - explique ce qu'un harnais en production pourrait faire : fenêtre glissante, compaction de l'historique, retrait des anciens résultats d'outils, lazy loading ;
    - propose comment poursuivre la démonstration.
  - Aucune de ces stratégies n'est automatique en V1 ; la compression du contexte (FR-31) reste une brique distincte.
- **NFR-9 Lisibilité en projection.** L'interface reste lisible projetée, dans une salle ou en visio. Une taille de texte agrandie est disponible.
- **NFR-10 Licences.** Le dépôt GitHub est public. Toutes les dépendances et tous les modèles embarqués ont des licences compatibles avec une redistribution publique et une démonstration en clientèle.
  - Les licences restrictives sont signalées avant adoption : Caveman proxy en BSL-1.1, LM Studio propriétaire.
- **NFR-11 Contenu publiable.** Le dépôt étant public, rien de ce qu'il contient n'est confidentiel : corpus RAG, scénarios, mémoire globale de démonstration et exemples de hooks.
  - Aucune donnée client ni document interne à Wavestone.
  - Aucun secret ni clé d'API dans le dépôt.
  - Les clés API sont stockées hors du dépôt, dans le dossier de données ; un point d'accès interne se déclare dans la configuration locale, jamais dans le dépôt.

## 6. Non-objectifs

- WaveStack n'est **pas** un framework agentique réutilisable ni une bibliothèque.
- WaveStack ne cherche **pas** la qualité des réponses : la faiblesse du SLM est assumée et devient un matériau pédagogique.
- WaveStack n'exige **aucun** fournisseur de modèle cloud et n'en utilise aucun par défaut : le cloud reste une option explicite (FR-43).
- WaveStack n'est **pas** un banc d'essai ni un comparateur de modèles.
- WaveStack ne propose **pas** de gestion d'utilisateurs, de comptes ni de mode serveur partagé : une instance par poste.
- WaveStack évite CrewAI et, plus largement, tout framework multi-agents lourd.

## 7. Périmètre MVP

### 7.1 Dans le périmètre (V1)

Toute la liste ci-dessous fait partie de la V1 : Anaël ne présente WaveStack qu'une fois la V1 complète, pour marquer les esprits dès la première session. La livraison suit deux paliers, pour tester tôt et obtenir des victoires rapides. En cas d'arbitrage, MCP, skills et hooks, cœur pédagogique du brief, passent avant le sous-agent et la compression du contexte.

**Palier 1 : socle**
- Interface à cinq volets synchronisés : panneau des briques, vue humain, contexte LLM, orchestration, schéma d'architecture.
- LLM nu, puis les briques mémoire courte, prompt système, outils, MCP (serveur local, serveur public, documentation complète et lazy loading), skills (dont Caveman) et hooks.
- Compteur de tokens, jauge de remplissage du contexte, déclenchement forcé, rejeu d'un prompt.
- Scénarios par brique, programme en modules, réinitialisation.
- Installation sans droits admin, modèle depuis un fichier local ou déjà présent sur le poste, lancement en une commande, diagnostic de démarrage.
- Modèle cloud optionnel via API, choisi au diagnostic (FR-43).

**Palier 2 : complément**
- Briques raisonnement, mémoire globale, RAG simple et reranking, sous-agent simple, compression du contexte.
- Scénarios métier.
- Changement de modèle en cours de session, et modèle servi par un serveur local déjà lancé (FR-34).

### 7.2 Hors périmètre V1

- **Multi-agent collaboratif** (agents qui dialoguent) : V2.
- **Routage vers des modèles spécialisés** (modèle de décision, image) : V2.
- **Serveur local au format chat** (compatible OpenAI) comme voie visée : V2. En V1, le format chat sert aux modèles cloud (FR-43) ; en local, le texte brut natif montre le gabarit.
- **RAG avancé** (HyDE, self-RAG) : V2. Les stratégies RAG restent interchangeables pour le préparer.
- **Indexation de documents propres à l'utilisateur** : V2.
- **Enregistrement et relecture de sessions dans WaveStack** : non prévu. Le repli est une vidéo de réunion Teams.
- **Démonstration client** : conditionnée au succès des sessions internes. C'est la trajectoire qui justifie l'investissement ; NFR-10 et FR-38 la préparent dès la V1.

### 7.3 Trajectoire

1. **Session pilote** avec un petit groupe, pour valider le déroulé et le poste de référence.
2. **Déploiement** sur 50 à 100 personnes de la BU.
3. **Si le résultat est probant** : démonstrateur client et support de vente de formations (V2).

## 8. Indicateurs de succès

*Mesure : questionnaire court en fin de session, plus une question ouverte sur les idées d'usage. Anaël le construit avant la session pilote. `[ASSUMPTION]` Les cibles autres que SM-1 sont à confirmer après la session pilote.*

**Principaux**
- **SM-1 : Compréhension des briques.** Part des participants qui savent expliquer ce qu'ajoutent un skill, un MCP, un hook et un harnais à un LLM nu. Cible : 80 % ou plus. Valide FR-5 à FR-29.
- **SM-2 : Trois ingénieries.** Part des participants qui distinguent prompt, context et harness engineering. Cible : 70 % ou plus. Valide FR-6, FR-30, FR-31 et FR-41.
- **SM-3 : Réflexe hébergement.** Part des participants qui, face à une solution tierce décrite en exercice, posent la question de l'hébergement du harnais, des données et du modèle. Cible : 80 % ou plus. Valide FR-3, FR-22 et FR-38.
- **SM-4 : Idées d'usage.** Part des participants qui formulent au moins une idée d'application agentique pour leur métier. Cible : 70 % ou plus. Valide FR-40.

**Secondaires**
- **SM-5 : Installation.** Part des participants qui tentent l'installation (profils techniques, en amont ou après la session) et réussissent sur leur poste professionnel sans droits admin, en moins de 20 minutes. Cible : 80 % ou plus. Valide FR-35 à FR-37.
- **SM-6 : Fiabilité en session.** Part des sessions menées sans repli forcé (plantage, blocage du modèle). Cible : 90 % ou plus. Valide NFR-8 et FR-38.
- **SM-7 : Présentable en clientèle.** WaveStack est montré au moins une fois à un client sans adaptation majeure. Cible V2, sans chiffre en V1. Valide NFR-10, NFR-11 et FR-38.

**Contre-indicateurs (à ne pas optimiser)**
- **SM-C1 : Qualité des réponses du modèle.** Améliorer les réponses au prix d'un modèle plus gros ou d'un contexte masqué trahirait l'objectif. Contrebalance SM-6.
- **SM-C2 : Nombre de briques et de fonctionnalités.** Ajouter des briques pour paraître complet dilue la progression. Contrebalance SM-1.
- **SM-C3 : Vitesse perçue.** Cacher des étapes pour aller plus vite retire de la transparence. Contrebalance NFR-1.

## 9. Risques et parades

| Risque | Parade |
|---|---|
| Le SLM rate ses appels d'outils ou de skills en pleine démonstration. | Scénarios éprouvés (FR-38). Déclenchement forcé (FR-42). Échecs montrés comme matériau pédagogique (FR-15, NFR-8). Changement de modèle (FR-32). |
| L'installation échoue sur les postes verrouillés (proxy, AppLocker, antivirus). | Voie hors ligne pour le modèle (FR-34). Diagnostic (FR-37). Roues précompilées, sans compilation ni exécutable à installer ; DLL non signées acceptées, vérifiées lors de la session pilote. Repli en démo pilotée. |
| Le contexte trop long (RAG et MCP en documentation complète) rend la latence insupportable. | Modèle par défaut de 2B au plus, fenêtre de contexte plafonnée, lazy loading MCP, compression du contexte, latence et jauge affichées (FR-30, FR-41). En dernier recours, vidéo d'une session précédente. |
| Pas de réseau en salle. | Toutes les briques non réseau fonctionnent hors ligne (NFR-3). |
| Une offre gratuite de modèle cloud change, ferme ou épuise son quota en séance (429). | Aucun fournisseur en dur (FR-43), refus expliqué, test avant chaque séance, repli sur le modèle local. |
| Les prompts envoyés à un modèle cloud servent à entraîner le modèle du fournisseur. | Avertissement et infobulle par fournisseur ; scénarios sans donnée sensible (NFR-11) ; désactivation en console quand elle existe (Mistral). |
| Une clé API fuit (trace, dépôt, capture d'écran). | Clé hors dépôt, jamais tracée ni renvoyée au navigateur, champ masqué. |
| Périmètre V1 large (11 briques, scénarios) pour un porteur seul. | Pas d'échéance imposée. Livraison en deux paliers (§7.1), le socle d'abord, pour tester tôt. |
| Le plafond de 4 Go ne laisse pas de place au modèle, aux embeddings, au reranker et aux serveurs MCP locaux réunis. | Mesure sur le poste de référence avant de figer le modèle par défaut. Modèles d'embedding et de reranking légers. Chargement des composants à l'activation de leur brique. |

## 10. Questions ouvertes

1. **Volets.** Question close le 2026-09-23 : cinq volets, chacun masquable (§4.1).
2. **Questionnaire de mesure.** Construit par Anaël avant la session pilote (§8).
3. **Validation par Wavestone de l'usage en clientèle.** Non requise pour l'usage interne ni pour la publication du dépôt public. À obtenir avant toute présentation client (V2).

## 11. Hypothèses différées

Aucune de ces hypothèses ne bloque l'UX, l'architecture ni les epics.

| Hypothèse | Qui tranche | Quand |
|---|---|---|
| NFR-1 : génération de plus de 10 tokens/s | Mesure `llama-bench` sur le poste de référence | Avant de figer le modèle par défaut |
| NFR-2 : périmètre de mesure de la mémoire, hors navigateur | Mesure sur le poste de référence | Avant de figer le modèle par défaut |
| NFR-6 : Windows 11 en cible principale, macOS et Linux au mieux | Anaël | Après la session pilote |
| §8 : cibles des indicateurs autres que SM-1 | Anaël | Après la session pilote |
