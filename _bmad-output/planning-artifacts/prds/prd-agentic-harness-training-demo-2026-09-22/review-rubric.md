# Revue qualité du PRD : WaveStack

*Revue menée selon la grille `prd-validation-checklist.md`. Barème calibré pour un outil de formation interne (50 à 100 personnes, puis démo client éventuelle). La question des quatre ou cinq volets est reportée volontairement à la session de maquette : elle n'est pas traitée ici. Parmi les `[ASSUMPTION]`, seules celles qui bloquent l'UX, l'architecture ou les epics sont relevées.*

## Verdict global

Le PRD a une thèse nette : la compréhension compte, pas la qualité des réponses, et la question clé est « où sont hébergés le harnais, les données et le modèle ? ». Cette thèse se retrouve dans les FR, les contre-indicateurs et les non-objectifs, et le document peut passer à `bmad-ux` sans réécriture. Trois points risquent de coûter cher plus loin :
- le périmètre V1 n'est pas hiérarchisé, alors qu'une seule personne le construit ;
- les FR qui dépendent d'une décision du modèle (lazy loading, skill, sous-agent, mémoire globale) ne disent pas qui déclenche quoi ;
- la seule borne de latence porte sur le LLM nu, pas sur les configurations chargées que l'on montre réellement.

## Préparation à la décision : adéquate

Les décisions sont formulées comme telles, et chaque renoncement est justifié :
- modèle de 2B au plus (FR-32) ;
- aucun fournisseur cloud (§6) ;
- recherche web, email et graphiques reportés en V2 « ils demandent une clé, ont des effets de bord ou alourdissent l'interface » (FR-13) ;
- CrewAI écarté (§6).

Les questions ouvertes du §10 sont de vraies questions. Les contre-indicateurs (SM-C1 à SM-C3) disent ce que l'on refuse d'optimiser, ce qui est rare et utile.

La faiblesse principale : l'arbitrage le plus lourd est repoussé. Le §9 reconnaît un « Périmètre V1 large (11 briques, scénarios, sessions enregistrées) pour un porteur seul » et répond « Ordre de priorité à fixer dans les epics ». Or le §7.1 affirme l'inverse d'une hiérarchie : « MCP, skills et hooks traités avec la même profondeur que les briques de base ». Le PRD contient déjà la réponse (le « socle » du §9 : volets, LLM nu, outils, MCP, skills, hooks), mais la range dans un tableau de risques au lieu d'en faire une décision de périmètre.

### Constats
- **[high]** Aucune ligne de coupe dans le périmètre V1 (§7.1, §9 ligne « Périmètre V1 large ») : les 11 briques, le rejeu, les sessions enregistrées et le schéma animé ont tous le même statut. Les epics devront donc trancher sans cadre, et SM-C2 (« Ajouter des briques pour paraître complet dilue la progression ») reste sans effet sur le périmètre. *Correction :* sortir le socle du §9 et l'inscrire au §7.1 comme « V1 socle ». Ajouter un palier « V1 complément » (par exemple mémoire globale, reranking, compression Headroom, sous-agent) avec une règle explicite : ce palier glisse en V2 si le socle n'est pas prêt pour la session pilote.
- **[medium]** Publication open source sous-estimée (§10 Q2) : « à vérifier avant la première publication ». Pourtant NFR-10 (« Le dépôt GitHub est public »), FR-35 (« depuis GitHub ») et le nom « WaveStack » en dépendent directement. Un refus de Wavestone changerait le mode d'installation et la stratégie de licence. *Correction :* passer ce point en `[NOTE FOR PM]`, fixer une échéance avant les epics d'installation et nommer le plan B (dépôt interne, archive zip sur un partage).
- **[low]** Le seul `[NOTE FOR PM]` (§7.2) est posé sur un point sans tension (« C'est la trajectoire qui justifie l'investissement »). Les vraies tensions n'en ont pas : périmètre contre porteur seul, marque et publication, fiabilité du MCP public. *Correction :* déplacer les callouts vers ces trois tensions.

## Substance plutôt que décor : forte

Rien ne relève du décor :
- **Vision (§1).** Elle ne pourrait pas servir à un autre produit : elle nomme la confusion « skill, plugin, outil et MCP » et la question de l'hébergement propre aux missions sécurité et souveraineté.
- **Protagonistes.** Les deux rôles et les trois protagonistes nommés (Anaël, Karim, Léa) déclenchent chacun des FR précis : UJ-2 pour les hooks et l'installation, UJ-3 pour FR-34 et FR-37, UJ-4 pour le scénario transverse de FR-38.
- **NFR.** Ils sont chiffrés là où c'est possible : 4 Go avec une cible de 2 à 3 Go, `127.0.0.1`, 10 s. Ils s'appuient sur un poste de référence nommé.
- **Différenciation (§1, trois points).** Elle est mince, mais elle repose sur la veille (`research-landscape.md`) et ne prétend pas plus qu'elle ne montre.

Seule exception : NFR-9 est formulé en adjectifs. Le constat est rangé sous « Clarté du "fini" ».

## Cohérence stratégique : forte

Le fil est tenu du début à la fin. UJ-1 déroule exactement la progression du parcours, du LLM nu qui invente l'heure jusqu'au « déclic MCP ». Le schéma d'architecture et le lieu d'hébergement (FR-3, FR-6) portent la thèse souveraineté. SM-3 mesure ce réflexe plutôt qu'une activité, et les contre-indicateurs protègent la thèse contre la tentation d'un modèle plus gros.

Le type de MVP est clair : un MVP d'expérience, qui vise le moment de compréhension. Deux points affaiblissent pourtant la réalisation du moment central.

### Constats
- **[medium]** Le repli du MCP public casse le déclic (FR-20, addendum « Vigilance »). data.gouv.fr est proposé comme serveur principal alors que sa gestion de session « a renvoyé une erreur ». De plus, le repli prévu est « le serveur MCP local ». Or le déclic d'UJ-1 repose précisément sur « un composant [qui] sort du poste ». Un repli local fait donc disparaître le message pédagogique. *Correction :* dans FR-20, ordonner le repli ainsi : second serveur public, puis session enregistrée (FR-40) du scénario « Où vont mes données ? », et seulement ensuite le MCP local. Reconsidérer aussi le choix du serveur principal au vu du test de fumée.
- **[medium]** FR-22 ne montre pas ce qui part sur le réseau. La thèse est « mes données partent où ? », mais FR-22 se limite à « découverte des outils, appel, résultat », et FR-13 ne dit rien sur les outils réseau. *Correction :* ajouter à FR-22 et à FR-14, pour tout composant réseau, l'affichage de la destination (URL ou hôte) et de la charge envoyée (arguments de l'appel). C'est la preuve visuelle dont SM-3 a besoin.
- **[low]** Les indicateurs n'ont pas de point de départ. SM-1 à SM-4 sont mesurés en fin de session seulement : sans question posée en début de session, on ne sait pas quelle part des 80 % visés vient de WaveStack. De plus, SM-6 (90 % des sessions sans repli) porte sur 5 à 8 sessions : une seule défaillance suffit à manquer la cible. *Correction :* ajouter deux ou trois questions en ouverture de session, et exprimer SM-6 en nombre de sessions.

## Clarté du « fini » : adéquate

La plupart des FR ont une conséquence testable. En voici de bons exemples :
- « Toutes les briques désactivées correspondent exactement au LLM nu » (FR-5) ;
- « Un appel mal formé ne fait jamais planter WaveStack » (FR-15) ;
- les checklists de FR-2 et FR-14 ;
- les quatre contrôles de FR-37.

La difficulté se concentre sur les FR où le modèle, un SLM de 2B, doit prendre une initiative. Ce sont précisément les briques au « cœur pédagogique » (§4.6).

### Constats
- **[high]** Le déclencheur n'est pas défini pour les mécanismes pilotés par le modèle :
  - FR-21 : « le harnais ne charge que ce qui est nécessaire, à la demande » (nécessaire selon qui ? par quel mécanisme ?) ;
  - FR-24 : « Tant qu'un skill n'est pas déclenché » (par le modèle ou par l'utilisateur ? FR-25 ne tranche que pour Caveman) ;
  - FR-29 : « Le harnais peut déléguer » (sur décision du modèle, du scénario ou du formateur ?) ;
  - FR-12 : « comment elle est écrite » (par un outil appelé par le modèle, par un hook ou par l'utilisateur ?).

  Sans cette précision, l'architecture ne sait pas quoi construire, et la story n'a pas de critère d'acceptation. Avec un SLM faible, c'est aussi le premier point de défaillance en salle. *Correction :* pour chacun de ces FR, écrire le déclencheur nominal (modèle, formateur ou scénario) et un déclenchement forcé par le formateur, qui garantisse la démonstration quand le modèle ne suit pas.
- **[high]** NFR-1 ne borne que le LLM nu. « Un tour LLM nu produit son premier token en moins de 10 s », mais les configurations réellement montrées chargent déjà environ 2 900 tokens de descriptions MCP (FR-20), plus le RAG et les descriptions de skills. Sur CPU, c'est le traitement du contexte qui domine la latence. Le risque est cité au §9, mais aucune borne n'en découle, et l'`[ASSUMPTION]` « plus de 10 tokens/s » conditionne le choix du modèle par défaut. *Correction :* ajouter une borne pour une configuration de référence, par exemple le scénario MCP en documentation complète, et un plafond de taille de contexte. Fixer les valeurs après le `llama-bench` prévu dans l'addendum.
- **[medium]** NFR-9 est formulé en adjectifs : « reste lisible projetée », « Une taille de texte agrandie est disponible ». Pourtant, quatre ou cinq volets et un contexte affiché « sans troncature par défaut » (FR-2) sur un vidéoprojecteur forment la tension UX centrale du produit. *Correction :* fixer une résolution cible de projection (par exemple 1280×720 et 1920×1080) et une taille de texte minimale en mode projection. `bmad-ux` en a besoin pour la maquette.
- **[medium]** Les prérequis d'installation ne sont pas nommés. FR-35 dit : « Une fois les prérequis en place, l'installation tient en une commande ». Or les prérequis (uv, Python, Git ou non) sont justement le point dur d'un poste sans droits admin. On ne sait pas non plus si le téléchargement du modèle (environ 1,5 Go) fait partie de la commande ni des « moins de 20 minutes » de SM-5. *Correction :* lister les prérequis et leur mode d'installation sans admin, puis préciser le périmètre de la commande et de la mesure SM-5.
- **[low]** Les politiques de repli ne sont pas fixées. FR-15 propose « nouvel essai, message d'erreur réinjecté ou arrêt », et NFR-8 « borne le nombre d'appels au modèle par tour » sans valeur. *Correction :* indiquer le comportement par défaut et un ordre de grandeur de la borne. L'architecture pourra les affiner.
- **[low]** Plusieurs critères sont satisfaits a minima :
  - FR-32 dit « depuis l'interface ou la configuration », donc un fichier de configuration suffit ;
  - FR-23 exige « au moins deux skills » sans nommer le second.

  *Correction :* trancher l'interface pour FR-32 et nommer le second skill, ou assumer que la configuration suffit.

## Honnêteté du périmètre : adéquate

Le §6 (non-objectifs) et le §2.2 (non-utilisateurs) font un vrai travail, par exemple « pas un banc d'essai », « une instance par poste » ou « CrewAI est à éviter ». Les onze `[ASSUMPTION]` en ligne sont toutes indexées au §11. Au total, on compte onze hypothèses, un callout et trois questions ouvertes. Cette densité est raisonnable pour un outil interne.

Deux hypothèses, en revanche, bloquent l'aval.

### Constats
- **[medium]** L'`[ASSUMPTION]` de FR-16 (« Le formateur peut aussi indexer ses propres documents ») bloque l'UX et l'architecture. Elle ajoute une interface d'import, une chaîne d'indexation en cours d'exécution (qui pèse sur le budget NFR-2) et un risque de confidentialité : ce sont des documents qui ne relèvent plus de NFR-11. *Correction :* trancher avant `bmad-ux`. Soit en faire un `[NON-GOAL for MVP]`, soit contraindre la fonction (dossier local désigné, formats limités, aucun document dans le dépôt).
- **[medium]** L'`[ASSUMPTION]` de FR-40 (« une session enregistrée pour chaque scénario ») dimensionne les epics. Avec au moins un scénario par brique (FR-38), cela fait au moins 11 enregistrements à produire, puis à refaire à chaque évolution du format d'événements. *Correction :* trancher avant les epics, par exemple avec une session enregistrée par module du parcours plutôt que par scénario.
- **[low]** Il y a une contradiction entre NFR-3 et FR-13. NFR-3 cite « outil de recherche web » parmi les briques réseau, alors que FR-13 reporte la recherche web en V2. *Correction :* remplacer par « outils réseau (jours fériés, Wikipedia) ».

## Utilisabilité en aval : adéquate

Le glossaire est riche et utilisé de façon globalement cohérente. Les identifiants sont contigus (FR-1 à FR-40, NFR-1 à NFR-11, SM-1 à SM-7, SM-C1 à SM-C3, UJ-1 à UJ-4). Chaque section de fonctionnalités indique quels UJ elle réalise. Les UJ ont tous un protagoniste nommé et contextualisé. Le terme le plus structurant du produit, « brique », dérive pourtant.

### Constats
- **[medium]** « Brique » n'a pas un périmètre stable :
  - le §3 liste 11 briques ;
  - le §1 en liste 9 (la mémoire n'y est pas scindée et la compression est absente) ;
  - le §7.1 range « LLM nu » parmi les briques, alors que le glossaire le définit comme l'absence de brique ;
  - FR-5 traite le lazy loading comme une brique dépendante (« le lazy loading MCP exige la brique MCP ») ;
  - le reranking (FR-18) et l'affichage du raisonnement (FR-9) sont activables sans statut défini.

  Or le panneau des briques, FR-5 et « au moins un scénario par brique » (FR-38) dépendent de cette liste. *Correction :* ajouter au glossaire une entrée « option de brique » (lazy loading, reranking, affichage du raisonnement), puis aligner le §1 et le §7.1 sur la liste du §3.
- **[low]** « Utilisateur » n'est pas défini. Le mot apparaît dans FR-2, FR-3, FR-12 et FR-25, alors que le glossaire ne connaît que Formateur et Participant. Pour FR-12 (qui peut effacer la mémoire globale ?) et FR-25, la différence compte. *Correction :* remplacer par Formateur ou Participant, ou définir « utilisateur » comme l'un ou l'autre.

## Adéquation de la forme : adéquate

La forme convient au produit : un outil interne piloté par un seul opérateur, devant un public, en tête d'une chaîne UX, puis architecture, puis stories. Les UJ se justifient parce que l'expérience en salle est le produit. Le glossaire long se justifie par la chaîne aval. Seul le volume dépasse la cible.

### Constats
- **[low]** Le PRD fait environ 5 900 mots, soit une dizaine de pages, pour une cible de 5 à 8. Quelques FR n'apportent pas de critère propre :
  - FR-4 répète la description du §4.1 ;
  - FR-36 pourrait fusionner avec FR-35 ;
  - FR-8 reformule la définition du glossaire.

  *Correction :* fusionner ces FR si un allègement est souhaité. Ce n'est pas bloquant.

## Notes mécaniques

- **Renvoi cassé dans l'addendum.** La section « Pistes pour l'UX » renvoie à « (Q2) » pour les volets, alors que c'est la Q1 du §10 du PRD (la Q2 porte sur la publication open source).
- **Aller-retour des hypothèses.** Correct : 11 `[ASSUMPTION]` en ligne et 11 entrées au §11, qui correspondent une à une.
- **Continuité des identifiants.** Aucun trou ni doublon. Les renvois internes sont résolus (glossaire vers FR-7 et FR-40, FR-13 vers FR-27, §7.2 vers NFR-10 et FR-38).
- **Polysémie de « session ».** Le mot désigne une session de formation (non définie au glossaire), une session enregistrée (définie) et, dans l'addendum, une session MCP (`Mcp-Session-Id`). Ajouter « Session » au glossaire suffit.
- **Collision sur « Parcours ».** Le glossaire le définit comme une suite de scénarios, alors que le titre du §2.3 est « Parcours utilisateurs clés ». Renommer le §2.3 « Scénarios d'usage » ou « Récits utilisateurs ».
- **Licences des modèles dans l'addendum.** NFR-10 exige de signaler les licences restrictives avant adoption, mais l'addendum cite Llama 3.2 (licence communautaire Meta, avec conditions) et Gemma 4 sans mention de licence. Ajouter la licence de chaque modèle candidat.
- **Affirmation conditionnelle dans l'addendum.** « environ 10 000 tokens dépasse le contexte d'un SLM de 2B » n'est vrai qu'avec le plafond de contexte évoqué plus bas dans l'addendum. Rattacher cette phrase à ce plafond.
- **Sections requises.** Toutes présentes pour ce type de produit.
