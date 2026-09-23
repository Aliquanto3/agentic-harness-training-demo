---
title: Demandes de modification du PRD issues de l'UX
status: validated
created: 2026-09-23
source: bmad-ux (session du 2026-09-22 au 2026-09-23)
target: ../../prds/prd-agentic-harness-training-demo-2026-09-22/prd.md
---

# Demandes de modification du PRD issues de l'UX

À traiter avec `bmad-prd` en mode Update. Anaël a validé CR-1 à CR-8 le 2026-09-23. Les parcours de CR-9 et la rédaction exacte restent à relire dans `bmad-prd`.

## CR-1 : Réponse à la question ouverte n° 1 (§10) — cinq volets

Découpe retenue : cinq volets (panneau des briques, vue humain, contexte LLM, orchestration, schéma d'architecture). Chaque volet peut être masqué et réaffiché.

- §4.1 : remplacer la phrase « La découpe exacte relève de `bmad-ux`… » par un renvoi aux spécifications UX (`ux-designs/ux-agentic-harness-training-demo-2026-09-22/`).
- §3 (Glossaire) : la « vue harnais » se scinde en deux volets, **contexte LLM** (les tokens envoyés au modèle, segmentés) et **orchestration** (les étapes du tour). Soit on garde « vue harnais » comme nom de l'ensemble, soit on renomme dans FR-2. À trancher dans `bmad-prd`.
- §10 : clore la question 1.

## CR-2 : Forcer un appel d'outil (FR-42), pour UJ-2 et les hooks

**Problème.** Un SLM peut ne jamais tenter de lire le fichier sensible. Le hook de garde-fou n'a alors rien à bloquer, et la démonstration de Karim échoue.

**Proposition.** Ajouter à la liste de FR-42 : *déclencher un appel d'outil précis, avec ses arguments* (par exemple, la lecture du fichier sensible du dossier de démonstration).
- L'appel forcé passe par tout le cycle du harnais, hooks compris, comme un appel décidé par le modèle.
- La vue d'orchestration affiche le badge « forcé par l'utilisateur ».

## CR-3 : Segment « Message et gabarit » (FR-2, FR-30, FR-41)

Ajouter aux segments listés dans FR-2 et FR-41 un segment **message et gabarit** : le message courant et le gabarit de conversation du modèle. En LLM nu (FR-8), c'est le seul segment présent.

## CR-4 : Dépassement de la fenêtre de contexte (NFR-8, FR-41)

Préciser que, si le contexte dépasse la fenêtre :
- l'appel n'est **pas** envoyé au modèle ;
- la vue d'orchestration affiche un événement d'erreur qui explique ce qu'un harnais en production pourrait faire (fenêtre glissante, compaction de l'historique, retrait des anciens résultats d'outils, lazy loading) ;
- elle propose aussi comment poursuivre la démo.

Aucune stratégie automatique n'est implémentée en V1. La compression (FR-31) reste une brique distincte.

## CR-5 : Rejeu d'un prompt (FR-7)

Précision validée par Anaël :
- le rejeu reconstruit le contexte à partir de l'état qui précédait le tour d'origine. La question et la réponse d'origine n'y figurent pas, sinon le modèle verrait la question deux fois, plus sa première réponse, et la comparaison serait faussée ;
- les deux tours restent consultables côte à côte ;
- la conversation continue à partir du tour rejoué.

## CR-6 : Réutiliser un modèle déjà présent sur le poste (FR-34, FR-37)

**Constat d'Anaël.** Le modèle est souvent déjà sur le PC, servi par Ollama ou llama.cpp.

**Proposition :**
- **fichier GGUF existant** : le diagnostic de démarrage et le choix du modèle proposent les fichiers GGUF trouvés dans les emplacements usuels : cache Hugging Face, dossier de modèles LM Studio, blobs Ollama (ce sont des fichiers GGUF, identifiables grâce au manifeste Ollama). L'utilisateur peut aussi saisir un chemin ;
- **serveur local déjà lancé** : Ollama ou `llama-server` sur le poste, via l'adaptateur compatible OpenAI de FR-32. Le schéma d'architecture montre alors le modèle comme un processus local distinct de WaveStack.

À arbitrer en architecture : faisabilité de la détection dans le dossier Ollama, et place de la mémoire du serveur externe dans le budget de NFR-2.

## CR-7 : Changement de modèle en cours de session (FR-32)

**Faisabilité (à confirmer en architecture).** Avec llama-cpp-python, changer de modèle revient à libérer le modèle chargé puis à charger le nouveau fichier : environ 5 à 20 s sur CPU pour 1 à 2 Go, sans redémarrer WaveStack. Trois points demandent du soin :
- le registre des capacités (FR-33), qui peut rendre des briques indisponibles ;
- le gabarit de conversation, lu dans le fichier GGUF ;
- le plafond de la fenêtre, propre à chaque modèle.

La conversation peut être conservée, puisque le harnais reconstruit le contexte à chaque tour.

**Proposition.** Préciser dans FR-32 : « entre deux tours, sans redémarrer, avec un indicateur de chargement ». Le changement reste au palier 2.

## CR-8 : Hooks de démonstration et événements (FR-26, FR-27)

Les hooks proposés ci-dessous sont simples à réaliser et parlants en démonstration. La liste des événements en découle.

| # | Hook | Événement | Décision montrée | Ce que la salle comprend | Practices |
|---|---|---|---|---|---|
| H1 | **Garde-fou fichier sensible** : bloque la lecture d'un fichier de `demo/confidentiel/` | avant l'exécution d'un outil | bloquer | C'est le harnais qui dit non, pas le modèle. (FR-27, UJ-2) | cyber, DLP |
| H2 | **Journal d'audit** : consigne chaque appel au modèle et chaque outil, horodatés, dans un fichier local visible | après l'exécution d'un outil, fin de tour | laisser passer, avec effet de bord | La traçabilité est du code déterministe. (FR-27, scénario SOC de FR-40) | SOC, conformité |
| H3 | **Injection de contexte** : ajoute automatiquement la date et les règles de la mission au message | à la réception du message | modifier | Même effet que l'outil « heure », mais sans décision du modèle. (FR-27) | toutes |
| H4 | **Masquage avant sortie du poste** : remplace e-mails et noms propres par `[MASQUÉ]` dans les arguments envoyés à un outil réseau ou à un MCP public | avant l'exécution d'un outil (outils réseau uniquement) | modifier | Les données qui sortent du poste sont filtrées, et le schéma le montre. Relie hooks et souveraineté. | DLP, souveraineté, IAM |
| H5 | **Validation humaine** : suspend un appel d'outil réseau jusqu'à l'accord du formateur | avant l'exécution d'un outil | demander | Pattern « humain dans la boucle », comme les permissions de Claude Code. | cyber, gouvernance |
| H6 | **Troncature d'un gros résultat** : coupe un résultat d'outil au-delà de N tokens | après l'exécution d'un outil | modifier | Première forme de context engineering, qui prépare la compression (FR-31). | toutes |

**Décision d'Anaël (2026-09-23).** Les hooks retenus sont H1 à H5. H5, la validation humaine, est retenu parce que le human in the loop est un concept important du design d'architecture agentique. H6 est écarté pour la V1. À reporter dans FR-27.

**Événements qui en découlent** (à reporter dans FR-26, à la place de l'hypothèse actuelle) :
1. à la réception du message de l'utilisateur (H3) ;
2. avant l'appel au modèle ;
3. avant l'exécution d'un outil (H1, H4, H5) ;
4. après l'exécution d'un outil (H2) ;
5. en fin de tour (H2).

Les décisions d'un hook sont donc : laisser passer, bloquer, modifier, et demander une validation humaine (H5). Cette dernière est à ajouter à FR-28.

## CR-9 : Parcours utilisateurs manquants (§2.3)

Aucun parcours ne couvre aujourd'hui le RAG, le sous-agent, la compression du contexte ni Caveman, alors que ces briques ont des FR. Brouillons à valider ; les protagonistes sont à renommer au besoin.

- **UJ-5. Sophie, consultante conformité, voit d'où vient la réponse (RAG, FR-16 à FR-18).**
  - Le module 5 démarre avec le corpus de démonstration indexé.
  - Anaël pose une question dont la réponse est dans un seul document. La vue humain répond. Le volet contexte LLM montre trois extraits, avec leur score et leur place dans le contexte.
  - Il active le reranking : l'orchestration montre l'ordre des extraits avant et après.
  - *Temps fort.* Sophie remarque que l'index est un fichier local dans le schéma : « donc le RAG, ce n'est pas le modèle qui sait, c'est le harnais qui cherche ».
- **UJ-6. Anaël délègue une sous-tâche et montre l'économie de contexte (sous-agent, FR-29).**
  - Anaël demande de résumer une page Wikipedia puis d'en tirer trois questions. Le modèle, ou Anaël qui la force (FR-42), délègue la lecture de la page à un sous-agent.
  - Le volet contexte LLM permet de basculer entre le contexte principal et celui du sous-agent.
  - *Temps fort.* La jauge montre que seul le résumé, quelques centaines de tokens, entre dans le contexte principal. La page complète est restée dans celui du sous-agent.
- **UJ-7. Anaël compresse ce qui entre, puis ce qui sort (compression FR-31, Caveman FR-25).**
  - Anaël rejoue une question dont le résultat d'outil est volumineux, cette fois avec la compression (Headroom). Le volet contexte LLM montre le contexte avant et après, avec le nombre de tokens de chaque version, et la latence baisse.
  - Il déclenche ensuite Caveman et rejoue la même question (FR-7) : les tokens de sortie chutent, l'information reste.
  - *Temps fort.* La salle voit la symétrie : Headroom réduit ce qui entre, Caveman ce qui sort. Et en local, le gain se mesure en secondes, pas en euros.

## Notes sans modification du PRD

- **Serveur MCP public indisponible (FR-20).** Aucun nouvel essai sans redémarrer ; c'est accepté. Le serveur MCP local sert de repli (FR-19).
- **Masquage des volets, taille du texte, mode focus.** Ils relèvent de l'UX (NFR-9) et sont décrits dans `EXPERIENCE.md`.
