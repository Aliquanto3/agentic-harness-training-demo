---
title: Rapprochement du PRD avec les demandes de modification UX (CR-1 à CR-9)
created: 2026-09-23
source: ../../ux-designs/ux-agentic-harness-training-demo-2026-09-22/prd-change-requests.md
cibles: prd.md, addendum.md
---

# Rapprochement du PRD avec les demandes de modification UX

Décisions de session appliquées en priorité sur le texte des CR :
- « vue harnais » désigne l'ensemble des volets contexte LLM et orchestration ;
- hooks retenus : H1 à H5 (H6 écarté) ;
- UJ-6 : le sous-agent lit une page web courte, par exemple le glossaire de la documentation d'Anthropic ;
- UJ-7 : la latence s'affiche, sans promesse qu'elle baisse ;
- UJ-5 : Sophie conservée ;
- détection des GGUF au palier 1, serveur local déjà lancé au palier 2.

Les « Notes sans modification du PRD » n'exigent rien.

**Bilan : 7 CR couvertes, 2 partielles (CR-6, CR-9), 0 manquante.**

## 1. Couverture CR par CR

| CR | Élément demandé | Statut | Citation PRD / addendum |
|---|---|---|---|
| **CR-1** | Cinq volets, chacun masquable | Couvert | §4.1 : « L'écran juxtapose cinq volets, que l'utilisateur peut chacun masquer et réafficher » |
| | §4.1 : renvoi aux specs UX | Couvert | §4.1 : « décrites dans les spécifications UX (`ux-designs/ux-agentic-harness-training-demo-2026-09-22/`) » |
| | §3 : scission de la vue harnais, nom de l'ensemble | Couvert (décision : nom conservé) | §3 : « **Vue harnais** : l'ensemble des deux volets contexte LLM et orchestration » + entrées **Contexte LLM**, **Orchestration** |
| | §10 : clore la question 1 | Couvert | §10 : « **Volets. Close le 2026-09-23 :** cinq volets, chacun masquable » |
| | *Report dans l'addendum* | **Écart** | addendum l. 119 : « **À trancher** : quatre ou cinq volets (§4.1 et §10 du PRD, question 1) » (voir écart M2) |
| **CR-2** | FR-42 : forcer un appel d'outil précis avec ses arguments | Couvert | FR-42 : « appeler un outil précis, avec ses arguments (FR-14), par exemple lire le fichier sensible du dossier de démonstration (FR-27) » |
| | Cycle complet, hooks compris | Couvert | FR-42 : « Une action forcée suit tout le cycle du harnais, hooks compris » |
| | Badge « forcé par l'utilisateur » en orchestration | Couvert | FR-42 : « Le volet orchestration indique qui a déclenché l'action : « déclenché par le modèle » ou « forcé par l'utilisateur » » |
| | Lien avec UJ-2 | Couvert | UJ-2 : « si le modèle ne s'y risque pas, Karim force l'appel (FR-42) » |
| **CR-3** | Segment « message et gabarit » dans FR-2 | Couvert | FR-2 : « message et gabarit, prompt système, historique, … » |
| | Idem dans FR-41 | Couvert | FR-41 : « La jauge est ventilée par brique : message et gabarit, … » |
| | FR-30 (titre de la CR) | Couvert implicitement | FR-30 : « au total et par segment, donc par brique » |
| | En LLM nu, seul segment présent | Couvert | FR-8 : « le contexte ne contient que le message et le gabarit de conversation » ; §3 LLM nu |
| **CR-4** | Dépassement : l'appel n'est pas envoyé | Couvert | NFR-8 : « Si le contexte dépasse la fenêtre, l'appel n'est pas envoyé au modèle » ; FR-41 idem avec renvoi NFR-8 |
| | Événement en orchestration expliquant les stratégies de production | Couvert | NFR-8 : « L'événement explique ce qu'un harnais en production pourrait faire (fenêtre glissante, compaction de l'historique, retrait des anciens résultats d'outils, lazy loading) » |
| | Propose comment poursuivre | Couvert | NFR-8 : « et propose comment poursuivre la démonstration » |
| | Aucune stratégie automatique, FR-31 distincte | Couvert | NFR-8 : « Aucune de ces stratégies n'est automatique en V1 ; la compression du contexte (FR-31) reste une brique distincte » |
| **CR-5** | Contexte reconstruit depuis l'état antérieur, sans question ni réponse d'origine | Couvert | FR-7 : « la question et la réponse d'origine n'y figurent pas, sinon le modèle verrait la question deux fois » ; §3 Rejeu. La justification « plus sa première réponse » est abrégée, sans perte de sens. |
| | Deux tours côte à côte | Couvert | FR-7 : « Les deux tours restent consultables côte à côte » |
| | Conversation continue depuis le tour rejoué | Couvert | FR-7 : « La conversation continue à partir du tour rejoué » |
| **CR-6** | GGUF existants proposés par le diagnostic et le choix du modèle (HF, LM Studio, Ollama), saisie d'un chemin | Couvert | FR-34 : « proposent les fichiers de modèle trouvés dans les emplacements usuels : cache Hugging Face, dossier de modèles de LM Studio, modèles d'Ollama. L'utilisateur peut aussi saisir un chemin » ; FR-37 : « ou des modèles déjà présents sur le poste (FR-34) » |
| | Précision « blobs Ollama, identifiables par le manifeste » | **Partiel** | Absente du PRD (niveau acceptable) mais aussi de l'addendum, qui est le bon support |
| | Serveur local déjà lancé (Ollama, llama-server) | Couvert | FR-34 : « un modèle servi sur le poste par Ollama ou llama.cpp (palier 2) » |
| | … via l'adaptateur compatible OpenAI de FR-32 | **Manquant** | FR-32 ne mentionne aucun adaptateur ; l'addendum l. 18 y renvoie quand même (voir écart M1) |
| | Schéma : modèle en processus local distinct | Couvert | FR-34 : « Le schéma d'architecture montre alors le modèle comme un processus local distinct de WaveStack » |
| | À arbitrer en architecture : détection Ollama, mémoire du serveur externe dans NFR-2 | **Manquant** | Ni §11, ni NFR-2, ni l'addendum. Trace seulement dans `.memlog.md` (voir écart M3) |
| | Paliers (décision de session) | Couvert | §7.1 palier 1 : « modèle depuis un fichier local ou déjà présent sur le poste » ; palier 2 : « modèle servi par un serveur local déjà lancé (FR-34) » |
| **CR-7** | Entre deux tours, sans redémarrer, indicateur de chargement | Couvert | FR-32 : « Le changement se fait entre deux tours, sans redémarrer WaveStack, avec un indicateur de chargement » |
| | Conversation conservée | Couvert | FR-32 : « La conversation est conservée : le harnais reconstruit le contexte à chaque tour » |
| | Registre des capacités, gabarit, plafond de fenêtre | Couvert | FR-33 : « appel d'outils, raisonnement, taille de contexte, gabarit de conversation » + « réévaluées à chaque changement de modèle (FR-32) » |
| | Palier 2 | Couvert | §7.1 palier 2 : « Changement de modèle en cours de session » |
| | Faisabilité à confirmer en architecture (5 à 20 s, libérer puis recharger) | Non reporté (mineur) | Absente de l'addendum (voir écart m9) |
| **CR-8** | FR-26 : cinq événements | Couvert | FR-26, liste 1 à 5, identique à la CR |
| | FR-27 : H1 à H5, sans H6 | Couvert | FR-27 : « cinq hooks de démonstration » H1 à H5 ; H6 absent |
| | FR-28 : décision « demander une validation humaine » | Couvert | FR-28 : « laisser passer, bloquer, modifier, demander une validation humaine » |
| | Contenu de chaque hook (événement, décision, message) | Couvert, nuances perdues | H4 : « et le schéma le montre » devient un renvoi à FR-22 ; H2 : « la traçabilité est du code déterministe » disparaît ; colonne Practices absente (voir écart m7) |
| **CR-9** | UJ-5 Sophie, RAG + reranking + temps fort | Couvert | UJ-5 conforme ; §4.5 « Réalise UJ-5 » |
| | UJ-6 sous-agent, page web courte (décision) | Couvert | UJ-6 : « une page courte de documentation publique, par exemple le glossaire de la documentation d'Anthropic » ; FR-13 : outil « lecture d'une page web publique » ; addendum : mesures du glossaire |
| | UJ-6 : bascule entre contextes, jauge | **Partiel** | La bascule est couverte par FR-29 (« inspectables séparément »). En revanche, FR-29 ne dit pas que le sous-agent peut appeler un outil, alors qu'UJ-6 en dépend (voir écart M5) |
| | UJ-7 compression + Caveman, latence affichée sans promesse | Couvert, une tension | UJ-7 : « La latence de chaque tour s'affiche ». Mais §4.10 : « En local, le gain se mesure en latence plutôt qu'en coût » (voir écart m5) |
| | Renvois FR ↔ UJ | Partiel | §4.9 → UJ-6 et §4.10 → UJ-7 sont présents. §4.7/FR-25 → UJ-7 et §4.1 → UJ-5 à UJ-7 manquent (mineur, voir m8) |

## 2. Écarts classés par gravité

### Majeurs (à corriger avant l'architecture)

**M1. Adaptateur compatible OpenAI orphelin et liste de serveurs divergente.**
- La CR-6 fait passer le serveur local par « l'adaptateur compatible OpenAI de FR-32 ». Or FR-32 ne parle d'aucun adaptateur.
- L'addendum l. 18 renvoie pourtant à FR-32 : « Ollama et LM Studio viendraient en option, derrière un adaptateur compatible OpenAI (FR-32) ».
- FR-34 cite Ollama et llama.cpp, l'addendum cite Ollama et LM Studio. LM Studio est par ailleurs signalé comme propriétaire (NFR-10).
- *Correction.* Dans FR-34, puce « Serveur local déjà lancé », ajouter « via un adaptateur compatible OpenAI ». Dans l'addendum, écrire « Ollama ou `llama-server` (llama.cpp) viendraient en option, derrière un adaptateur compatible OpenAI (FR-34) » et retirer LM Studio comme moteur, en gardant son dossier de modèles pour la détection.

**M2. Question des volets toujours ouverte dans l'addendum.**
- Addendum l. 114-119 : « **À trancher** : quatre ou cinq volets (§4.1 et §10 du PRD, question 1) ». Le PRD, lui, a clos la question.
- *Correction.* Remplacer par « Tranché le 2026-09-23 : cinq volets masquables (§4.1), voir les spécifications UX ». Supprimer ou marquer comme historiques les trois pistes du brief (fusion des vues, extension de la vue humain, onglet RAG).

**M3. Arbitrages d'architecture de la CR-6 perdus.**
- La faisabilité de la détection dans le dossier Ollama (blobs et manifeste) n'est reportée nulle part.
- La place de la mémoire du serveur externe dans le budget NFR-2 non plus. Le `[ASSUMPTION]` de NFR-2 compte « le modèle » dans le périmètre mesuré, ce qui devient ambigu quand le modèle tourne dans Ollama.
- *Correction.* Ajouter dans l'addendum, sous « Budget mémoire », un point « à arbitrer : un modèle servi par un serveur externe compte-t-il dans les 4 Go ? ». Ajouter sous « Moteur d'inférence » : « détection des GGUF d'Ollama via le manifeste (les blobs sont des GGUF) : faisabilité à confirmer ». Ajouter une ligne dans le tableau du §11 pour NFR-2 (serveur externe, architecture).

### Moyens

**M4. Listes de segments divergentes et incomplètes (FR-2, FR-41, §3, FR-30).**
- FR-2 sépare « descriptions d'outils » et « descriptions de skills ». FR-41 les fusionne en « descriptions d'outils et de skills ».
- Aucune des deux listes n'attribue de segment :
  - au contenu d'un skill déclenché (FR-24) ;
  - à l'injection du hook H3 (FR-27), alors que le §3 exige que chaque segment soit « attribué à la brique qui l'a produit » ;
  - au résultat du sous-agent (FR-29), qu'UJ-6 montre dans la jauge.
- « Message et gabarit » n'est produit par aucune brique, ce qui contredit « donc par brique » (FR-30) et la définition du Contexte (§3).
- *Correction.* Définir une liste unique dans FR-2 : message et gabarit, prompt système, historique, descriptions d'outils, descriptions de skills, contenu des skills chargés, extraits RAG, résultats d'outils (dont résultat du sous-agent), mémoire globale, injections des hooks. FR-41 y renvoie (« les segments de FR-2, plus l'espace libre »). Au §3, préciser que le segment « message et gabarit » n'appartient à aucune brique.

**M5. FR-29 ne dit pas que le sous-agent peut utiliser un outil.**
- Dans UJ-6, le sous-agent « lit la page », donc il appelle l'outil réseau « lecture d'une page web ». FR-29 ne dit ni que le sous-agent dispose d'outils, ni que les hooks H4 et H5 s'appliquent dans son contexte. L'addendum affirme pourtant « c'est un outil réseau : les hooks H4 et H5 s'y appliquent ».
- UJ-6 parle de « la jauge », FR-29 du « compteur de tokens ».
- *Correction.* Ajouter à FR-29 : « Le sous-agent peut appeler les outils actifs ; ses appels suivent le même cycle, hooks compris, et apparaissent dans son contexte. » Remplacer « Le compteur de tokens » par « Le compteur de tokens et la jauge (FR-41) montrent l'économie réalisée ».

**M6. Rejeu (FR-7) combiné au déclenchement forcé (FR-42) non spécifié.**
- Dans UJ-7, Anaël « déclenche ensuite Caveman et rejoue la même question (FR-7) ». FR-7 ne parle que de rejouer « après avoir changé les briques ». Rien ne dit si un skill forcé, ou un autre forçage, s'applique au tour rejoué, dont le contexte est reconstruit depuis l'état antérieur.
- Dans UJ-7, trois tours se succèdent (original, compressé, compressé avec Caveman). FR-7 n'en garde que « deux » côte à côte.
- *Correction.* Dans FR-7, écrire : « Le rejeu peut s'accompagner d'une action forcée (FR-42), par exemple le déclenchement de Caveman. » Remplacer « Les deux tours » par « Le tour rejoué et le tour d'origine », ou préciser que chaque rejeu se compare au tour précédent.

### Mineurs

- **m1. Ordre et périmètre de H4 et H5.** Les deux hooks s'exécutent « avant l'exécution d'un outil », dans un ordre non fixé. Or H5 montre « les données qui sortiraient du poste », ce qui n'a de sens qu'après le masquage de H4. De plus, H4 couvre « outil réseau ou serveur MCP public », mais H5 seulement « outil réseau ». *Correction :* « H4 s'exécute avant H5 » ; aligner le périmètre de H5 sur celui de H4, ou justifier l'exclusion du MCP public. Dans FR-26, préciser que l'événement 3 couvre aussi les outils MCP.
- **m2. FR-2 : « deux volets visibles en même temps »** alors que chaque volet est masquable (§4.1). *Correction :* « deux volets, qui peuvent s'afficher en même temps ».
- **m3. FR-2, puce Orchestration, plus étroite que le glossaire.** Le §3 y inclut « les événements du harnais (hooks, échecs, dépassements) et les échanges avec les serveurs MCP ». *Correction :* compléter la puce de FR-2 avec ces éléments et le badge de FR-42.
- **m4. FR-14, étape 2 : « la demande d'appel émise par le modèle »**, alors qu'avec FR-42 l'appel peut être forcé. *Correction :* « la demande d'appel, émise par le modèle ou forcée (FR-42) ».
- **m5. §4.10 : « En local, le gain se mesure en latence plutôt qu'en coût. »** Cela promet une baisse de latence, contrairement à la décision prise pour UJ-7. *Correction :* « En local, l'enjeu se compte en latence plutôt qu'en coût », comme dans UJ-7.
- **m6. UJ-1 et la sémantique du rejeu.** « Il active la mémoire courte, puis le prompt système. Il rejoue le même prompt : le contexte grossit. » Avec FR-7, le rejeu repart de l'état antérieur : si la question sur l'heure est le premier tour, la mémoire courte n'ajoute rien, et seul le prompt système fait grossir le contexte. *Correction :* préciser qu'Anaël a déjà échangé quelques messages, ou que la croissance due à la mémoire courte se voit aux tours suivants.
- **m7. Nuances du tableau des hooks perdues.** Pour H4, « le schéma le montre » n'a pas d'équivalent dans FR-3 ou FR-27. Pour H2, le message « la traçabilité est du code déterministe » disparaît. La colonne Practices (SOC, conformité, DLP, souveraineté, IAM, gouvernance) n'est pas reprise. *Correction :* dans H4, ajouter « le schéma d'architecture signale le masquage sur le flux sortant » ; éventuellement, reprendre les practices entre parenthèses.
- **m8. Renvois « Réalise UJ-x » incomplets.** Ajouter UJ-7 à §4.7 ou FR-25, UJ-5 à UJ-7 à §4.1 (volets contexte LLM et orchestration), UJ-5 à FR-3 (index en fichier local), et UJ-2, UJ-6 et UJ-7 à §4.2 (FR-7, FR-42).
- **m9. Informations d'architecture de la CR-7 non reportées.** Dans l'addendum, sous « Moteur d'inférence », ajouter : « changement de modèle : libérer puis recharger avec llama-cpp-python, environ 5 à 20 s sur CPU pour 1 à 2 Go, à confirmer ». Il faut aussi prévoir le cas où la conversation dépasse la fenêtre du nouveau modèle : NFR-8 s'applique.
- **m10. Choix du modèle au palier 1.** FR-34 évoque « le choix du modèle » parmi les GGUF détectés, au palier 1, alors que le changement en cours de session (FR-32) est au palier 2. *Correction :* au §7.1, palier 1, préciser « choix du modèle au démarrage (configuration ou diagnostic) ».

## 3. Contrôles sans écart

- **Renvois FR, UJ, NFR et SM du PRD.** Tous pointent vers des éléments existants (FR-1 à FR-42, UJ-1 à UJ-7, NFR-1 à NFR-11). Aucun renvoi cassé dans `prd.md`. Le seul renvoi faux est celui de l'addendum vers FR-32 (M1).
- **Mentions de « quatre volets ».** Aucune dans `prd.md`. Il en reste une dans l'addendum (M2) ; celle de `review-rubric.md` est historique.
- **Emplois de « vue harnais ».** Dans FR-8, FR-9, FR-12, FR-14, FR-15, FR-17, FR-18, FR-22, FR-24 et FR-31, ainsi que dans UJ-1 et UJ-2, le terme renvoie à l'ensemble des deux volets. C'est compatible avec le §3, et aucun cas n'est contradictoire. UJ-5 et UJ-7 désignent précisément le volet visé, ce qui reste cohérent avec FR-17, FR-18 et FR-31.
- **Paliers du §7.1.**
  - Rien ne manque au palier 1 : hooks H1 à H5 (outils réseau inclus), jauge, déclenchement forcé, rejeu, détection des GGUF.
  - Au palier 2 : sous-agent, compression, changement de modèle, serveur local.
  - UJ-6 et UJ-7 s'appuient sur des briques du palier 2, ce qui est cohérent.
- **Nombre de briques.** Onze partout (§1, §3, §9).
