# Glossaire — WaveStack

Vocabulaire utilisé tel quel dans SPEC.md, l'architecture, l'UX et le code (identifiants) ou le contenu (libellés français).

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
- **Rejeu d'un prompt** : le renvoi du dernier message avec une autre configuration de briques, à partir de l'état qui précédait le tour d'origine, pour comparer deux tours.
- **Formateur** : la personne qui anime une session de formation avec WaveStack.
- **Participant** : une personne formée, qui regarde WaveStack projeté. Certains profils techniques l'installent aussi sur leur poste.
- **Utilisateur** : toute personne aux commandes de WaveStack, formateur ou participant qui l'a installé sur son poste.
- **Poste de référence** : le PC professionnel sur lequel les exigences de performance sont mesurées : HP EliteBook (édition Bang & Olufsen), Windows 11, Intel Core i5 vPro, sans GPU dédié, 16 Go de RAM.
