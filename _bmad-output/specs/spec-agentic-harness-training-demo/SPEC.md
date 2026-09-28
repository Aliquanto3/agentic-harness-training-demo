---
id: SPEC-agentic-harness-training-demo
companions:
  - glossary.md
  - user-journeys.md
  - success-metrics.md
  - risks.md
  - ../../planning-artifacts/architecture/architecture-agentic-harness-training-demo-2026-09-23/ARCHITECTURE-SPINE.md
  - ../../planning-artifacts/ux-designs/ux-agentic-harness-training-demo-2026-09-22/DESIGN.md
  - ../../planning-artifacts/ux-designs/ux-agentic-harness-training-demo-2026-09-22/EXPERIENCE.md
  - ../../planning-artifacts/prds/prd-agentic-harness-training-demo-2026-09-22/addendum.md
sources:
  - ../../planning-artifacts/prds/prd-agentic-harness-training-demo-2026-09-22/prd.md
---

> **Canonical contract.** This SPEC and the files in `companions:` are the complete, preservation-validated contract for what to build, test, and validate. Source documents listed in frontmatter are for traceability — consult them only if you need narrative rationale or prose color this contract intentionally omits.

# WaveStack

## Why

WaveStack rend visible, brique par brique, ce qu'un harnais agentique ajoute à un LLM nu. C'est une **vision à réaliser** doublée d'un **mandat interne** : les consultants Wavestone utilisent des chatbots mais ne distinguent pas un LLM nu d'un LLM outillé, et confondent skill, plugin, outil et MCP — ils peinent donc à poser en clientèle la question clé de leurs missions de sécurité, souveraineté et conformité : où sont hébergés le harnais, les données et le modèle ? Anaël s'en sert pour former 50 à 100 personnes de sa BU ; si le résultat est probant, WaveStack devient un démonstrateur client et un support de vente de formations (V2). Tourne par défaut entièrement en local sur CPU avec des petits modèles (SLM), incarnant ce qu'il enseigne sur la souveraineté et le numérique responsable. En option, un modèle cloud appelé par API montre que le même harnais pilote des modèles plus gros, beaucoup plus vite, au prix de données qui quittent le poste.

## Capabilities

- **CAP-1** Vue humain (FR-1, palier 1)
  - **intent:** L'utilisateur peut converser avec le modèle comme dans un chatbot, en streaming, avec un indicateur pendant les phases sans token visible.
  - **success:** Les réponses s'affichent au fil de la génération ; un indicateur distinct signale le traitement du contexte ou l'exécution d'un outil.
- **CAP-2** Vue harnais : contexte LLM et orchestration (FR-2, palier 1)
  - **intent:** L'utilisateur peut inspecter le contexte exact de chaque appel (segments étiquetés par brique, sortie brute) et les étapes du tour.
  - **success:** Chaque segment du contexte LLM porte sa brique d'origine, sans troncature par défaut ; le volet orchestration liste les étapes dans l'ordre réel.
- **CAP-3** Schéma d'architecture en direct (FR-3, palier 1)
  - **intent:** L'utilisateur voit les composants actifs et leur lieu d'hébergement (processus local, fichier local, service réseau).
  - **success:** Seules les briques actives apparaissent ; le composant en cours d'action est mis en évidence pendant un tour ; un modèle cloud est dessiné comme service réseau, avec son fournisseur.
- **CAP-4** Synchronisation des volets (FR-4, palier 1)
  - **intent:** Sélectionner un élément dans un volet met en évidence ses correspondants ailleurs.
  - **success:** La sélection d'un segment de contexte surligne la brique et le composant correspondants dans le schéma.
- **CAP-5** Activation indépendante des briques (FR-5, palier 1)
  - **intent:** L'utilisateur active ou désactive chaque brique sans redémarrer WaveStack.
  - **success:** Le changement prend effet au tour suivant ; toutes briques désactivées = comportement LLM nu ; une dépendance manquante indique pourquoi la brique est indisponible.
- **CAP-6** Explication pédagogique de chaque brique (FR-6, palier 1)
  - **intent:** Chaque brique présente ce qu'elle ajoute au LLM nu, sa catégorie (prompt/context/harness engineering) et le lieu d'hébergement de ses composants.
  - **success:** Les trois informations sont visibles pour chaque brique, en français.
- **CAP-7** Rejouer un prompt avec une autre configuration (FR-7, palier 1)
  - **intent:** L'utilisateur rejoue le dernier prompt après un changement de briques pour comparer deux tours.
  - **success:** Le contexte du rejeu est reconstruit depuis l'état antérieur au tour d'origine (sans la question/réponse d'origine) ; les deux tours restent consultables côte à côte ; un tour rejoué est lui-même rejouable.
- **CAP-8** Déclenchement par le modèle ou forcé (FR-42, palier 1)
  - **intent:** L'utilisateur peut forcer une action (appel d'outil, écriture mémoire, chargement doc MCP, skill, délégation) quand le modèle ne la déclenche pas.
  - **success:** Une action forcée suit tout le cycle du harnais (hooks compris) ; le volet orchestration indique qui l'a déclenchée.
- **CAP-9** LLM nu (FR-8, palier 1)
  - **intent:** Sans aucune brique active, chaque message est envoyé seul au modèle.
  - **success:** La vue harnais montre que le contexte ne contient que le message et le gabarit de conversation.
- **CAP-10** Raisonnement (FR-9, palier 2)
  - **intent:** L'utilisateur active le mode raisonnement et choisit de l'afficher ou non dans la vue humain.
  - **success:** Le raisonnement reste toujours visible en vue harnais ; la brique est indisponible avec explication si le modèle ne raisonne pas ; pour un modèle cloud qui raisonne toujours, elle s'affiche « toujours active pour ce modèle », avec sa raison.
- **CAP-11** Mémoire courte (FR-10, palier 1)
  - **intent:** Les messages précédents de la conversation sont réinjectés dans le contexte.
  - **success:** Le compteur de tokens montre le contexte qui grossit à chaque tour ; l'utilisateur peut vider la conversation.
- **CAP-12** Prompt système (FR-11, palier 1)
  - **intent:** Un prompt système par défaut en français est modifiable par l'utilisateur.
  - **success:** La modification est visible dans le contexte au tour suivant.
- **CAP-13** Mémoire globale (FR-12, palier 2)
  - **intent:** Des informations persistent d'une conversation à l'autre et sont réinjectées dans le contexte.
  - **success:** L'utilisateur peut consulter/modifier/effacer la mémoire ; la vue harnais montre quand et comment elle est injectée et écrite (modèle ou forcé) ; le schéma montre son stockage en fichier local.
- **CAP-14** Catalogue d'outils (FR-13, palier 1)
  - **intent:** WaveStack fournit un catalogue d'outils activables individuellement, hors ligne (heure/date, calculatrice, lecture de fichier confiné) et réseau (jours fériés, résumé Wikipedia, lecture de page web).
  - **success:** Au moins un outil hors ligne et un outil réseau fonctionnent ; chaque outil réseau est signalé comme tel dans le panneau et le schéma ; les cartes Outils et MCP disent ce qui sort du poste et où lire les données sortantes (story 23).
- **CAP-15** Cycle d'appel d'outil visible (FR-14, palier 1)
  - **intent:** La vue harnais montre le cycle complet d'un appel d'outil, de la description à la réponse finale.
  - **success:** Les 5 étapes (description, demande, exécution, réinjection, réponse) sont observables pour chaque appel.
- **CAP-16** Échecs d'appel visibles (FR-15, palier 1)
  - **intent:** Un appel d'outil mal formé ou inexistant est montré comme matériau pédagogique, jamais comme un plantage.
  - **success:** La vue harnais affiche l'échec du parsing et la réaction du harnais (nouvel essai, erreur réinjectée, arrêt) ; aucun crash.
- **CAP-17** Corpus de démonstration (FR-16, palier 2)
  - **intent:** WaveStack fournit un corpus RAG en français prêt à l'emploi.
  - **success:** L'index est stocké localement et affiché comme fichier local dans le schéma.
- **CAP-18** RAG simple visible (FR-17, palier 2)
  - **intent:** Pour chaque tour, la vue harnais montre la requête de recherche, les extraits retrouvés avec leur score et leur position dans le contexte.
  - **success:** Les trois informations sont visibles pour chaque recherche RAG.
- **CAP-19** Reranking (FR-18, palier 2)
  - **intent:** L'utilisateur active le reranking des extraits RAG.
  - **success:** Le volet orchestration montre l'ordre des extraits avant et après reranking.
- **CAP-20** Serveur MCP local (FR-19, palier 1)
  - **intent:** WaveStack fournit au moins un serveur MCP local, lancé automatiquement, hors ligne et sans droits admin.
  - **success:** Le schéma le montre comme un processus local distinct du harnais.
- **CAP-21** Serveur MCP public (FR-20, palier 1)
  - **intent:** WaveStack se connecte à au moins deux serveurs MCP publics gratuits (data.gouv.fr, Microsoft Learn).
  - **success:** Le schéma montre chaque serveur comme un service réseau, distinct, indisponible avec raison s'il ne répond pas (nouvelle tentative possible), toujours dessiné même indisponible.
- **CAP-22** Documentation complète contre lazy loading (FR-21, palier 1)
  - **intent:** L'utilisateur bascule entre charger toutes les descriptions d'outils MCP ou seulement à la demande.
  - **success:** Le compteur de tokens montre l'écart entre les deux modes pour un même prompt.
- **CAP-23** Échanges MCP visibles (FR-22, palier 1)
  - **intent:** La vue harnais montre la découverte, l'appel et le résultat des échanges MCP, en distinguant outil MCP et outil natif.
  - **success:** Pour un serveur public, l'adresse de destination, les en-têtes (secrets masqués par le harnais) et les données exactement envoyées sont affichés, comme pour un outil réseau.
- **CAP-24** Catalogue de skills (FR-23, palier 1)
  - **intent:** WaveStack fournit au moins deux skills de démonstration activables, dont Caveman.
  - **success:** Les skills apparaissent dans le panneau des briques, activables individuellement.
- **CAP-25** Chargement progressif visible (FR-24, palier 1)
  - **intent:** Un skill n'entre en contexte qu'une fois déclenché (par le modèle ou l'utilisateur).
  - **success:** La vue harnais montre les deux états (nom/description seuls, puis contenu chargé) ; le compteur de tokens montre l'écart.
- **CAP-26** Caveman (FR-25, palier 1)
  - **intent:** L'utilisateur déclenche le skill Caveman pour réduire les tokens de sortie sans perdre l'information utile.
  - **success:** Comparaison du nombre de tokens de sortie avec/sans Caveman sur la même question (via CAP-7).
- **CAP-27** Événements de hook (FR-26, palier 1)
  - **intent:** Des hooks s'exécutent à des points fixes du tour (réception message, avant/après appel modèle et outil, fin de tour).
  - **success:** Les 5 points d'accroche sont disponibles pour tout hook.
- **CAP-28** Hooks de démonstration H1/H2/H3/H5 (FR-27, palier 1)
  - **intent:** WaveStack fournit 4 hooks démonstratifs activables séparément — garde-fou fichier sensible (H1), journal d'audit (H2), injection de contexte (H3), validation humaine avant outil réseau (H5).
  - **success:** Chaque hook s'active/désactive indépendamment ; chaque scénario fixe sa liste de hooks actifs ; H5 se désactive d'un geste.
- **CAP-29** Déclenchement visible des hooks (FR-28, palier 1)
  - **intent:** Le volet orchestration montre chaque déclenchement de hook (événement, décision, effet).
  - **success:** La décision (laisser passer, bloquer, modifier, demander validation humaine) est explicitement attribuée au harnais, jamais au modèle.
- **CAP-30** Délégation à un sous-agent (FR-29, palier 2)
  - **intent:** Le harnais délègue une sous-tâche à un sous-agent avec son propre contexte, sur demande du modèle ou forcée.
  - **success:** Les deux contextes sont inspectables séparément ; seul le résultat entre dans le contexte principal, avec l'économie de tokens visible ; le sous-agent peut appeler des outils sous le même cycle (hooks compris).
- **CAP-31** Compteur de tokens (FR-30, palier 1)
  - **intent:** Pour chaque appel au modèle, WaveStack affiche le nombre de tokens (total et par segment/brique), les tokens de sortie, le temps écoulé et le débit de sortie (tokens/s).
  - **success:** Ces mesures sont affichées à chaque appel, sans recalcul côté front ; pour un modèle cloud, la ventilation par segment est une estimation marquée « ≈ », le total vient de l'API quand elle le renvoie (sinon il est lui aussi estimé), l'écart va au segment « Gabarit appliqué chez le fournisseur (estimé) » et la somme des segments égale le total.
- **CAP-32** Compression du contexte (FR-31, palier 2)
  - **intent:** L'utilisateur active la compression du contexte (Headroom si le test préalable le valide, sinon un compresseur minimal du harnais), portant au moins sur les résultats d'outils et extraits RAG.
  - **success:** La vue harnais montre le contexte avant/après avec le nombre de tokens de chaque version.
- **CAP-33** Jauge de remplissage du contexte (FR-41, palier 1)
  - **intent:** WaveStack affiche en permanence le taux de remplissage de la fenêtre, ventilé par segment, à l'image de `/context` de Claude Code.
  - **success:** La jauge se met à jour à chaque appel (y compris intra-tour), signale l'approche de la limite, et un dépassement certain empêche l'envoi de l'appel (NFR-8).
- **CAP-34** Changer de modèle (FR-32, palier 2)
  - **intent:** L'utilisateur change de modèle depuis l'interface ou la configuration, sans modifier le code.
  - **success:** Le changement se fait entre deux tours, sans redémarrage, avec indicateur de chargement ; la conversation est conservée (contexte reconstruit à chaque tour) ; un modèle par défaut de 2B paramètres au plus est fourni.
- **CAP-35** Capacités du modèle (FR-33, palier 1)
  - **intent:** WaveStack connaît les capacités du modèle actif (appel d'outils, raisonnement, taille de contexte, gabarit) et rend indisponibles, avec explication, les briques qui en dépendent.
  - **success:** Les capacités sont réévaluées à chaque changement de modèle ; un modèle inconnu est lu depuis son fichier ; les capacités d'un modèle cloud sont déclarées dans la configuration ; l'appel d'outils n'est disponible que pour les familles au format connu.
- **CAP-36** Modèle déjà présent sur le poste (FR-34, palier 1 pour fichier local/déjà présent, palier 2 pour serveur local déjà lancé)
  - **intent:** L'utilisateur utilise un modèle sans le télécharger, depuis un fichier (partage, clé USB) ou déjà présent (cache HF, LM Studio, Ollama), ou servi par un serveur local déjà lancé (Ollama/llama.cpp, texte brut natif).
  - **success:** Le diagnostic et le choix du modèle proposent les fichiers trouvés ; pour un serveur déjà lancé, WaveStack construit lui-même le texte envoyé, gabarit compris, et le schéma montre le modèle comme processus local distinct.
- **CAP-37** Installation sans droits admin (FR-35, palier 1)
  - **intent:** Un utilisateur installe WaveStack sans droits administrateur, par un clone authentifié du dépôt privé (GitHub privé, puis GitLab interne Wavestone) ou depuis une archive zip (téléchargée depuis le dépôt, ou remise par le formateur sur un partage interne).
  - **success:** Aucune étape ne demande d'élévation, de service ni de règle de pare-feu ; procédure documentée en français, indépendante de l'hébergeur du dépôt, une commande une fois les prérequis (accès au dépôt et Git, ou archive zip ; `uv`) en place.
- **CAP-38** Lancement en une commande (FR-36, palier 1)
  - **intent:** Une seule commande démarre WaveStack et ouvre l'interface dans le navigateur local.
  - **success:** La commande ouvre effectivement le navigateur sur l'interface.
- **CAP-39** Diagnostic de démarrage (FR-37, palier 1)
  - **intent:** Au démarrage, WaveStack vérifie mémoire, présence du modèle, accès réseau et disponibilité du port.
  - **success:** Chaque problème est signalé en français avec l'action corrective (ex. voie hors ligne pour le modèle).
- **CAP-40** Scénarios par brique et programme (FR-38, palier 1)
  - **intent:** WaveStack fournit au moins un scénario par brique, lançable en un clic, organisés en un programme par modules de 30 min à 1 h.
  - **success:** Au moins un scénario transverse porte sur l'hébergement ; l'utilisateur peut démarrer un module directement, avec les briques des modules précédents déjà actives.
- **CAP-41** Réinitialisation rapide (FR-39, palier 1)
  - **intent:** L'utilisateur revient en un geste à l'état initial (LLM nu, conversation vide, mémoire globale de démonstration restaurée).
  - **success:** Un seul geste suffit et l'état obtenu est reproductible.
- **CAP-42** Scénarios métier (FR-40, palier 2)
  - **intent:** WaveStack fournit au moins trois scénarios ancrés métier (SOC via H2, IAM via MCP Microsoft Learn, Souveraineté via MCP data.gouv.fr).
  - **success:** Chaque scénario métier illustre une brique en situation professionnelle reconnaissable par la practice visée.
- **CAP-43** Modèle cloud via API (FR-43, palier 1)
  - **intent:** L'utilisateur choisit au diagnostic un modèle cloud déclaré en configuration (préréglages Groq et Mistral ; Google, NVIDIA et OpenRouter en exemples de configuration avec leur avertissement ; ou point d'accès ajouté hors du dépôt, comme un endpoint interne), saisit sa clé API, le teste, puis mène les mêmes tours qu'en local.
  - **success:** Chaque modèle cloud affiche un pictogramme réseau et une infobulle (hébergement, usage des données pour l'entraînement, offre d'essai, quotas renvoyés vers la console du fournisseur) ; le choisir affiche un avertissement sur ses conséquences (données qui partent, gabarit et appels d'outils traités chez le fournisseur, tokens estimés), à confirmer avant tout appel qui porte des données de l'utilisateur, et la barre haute signale ensuite un modèle réseau ; « Tester » prouve streaming et appel d'outils avec une invite fixe, sans donnée de l'utilisateur ; chaque appel est tracé comme donnée sortante, clé jamais tracée ; un refus du fournisseur (quota, clé refusée, requête trop grosse) est un événement expliqué, sans nouvel essai automatique, jamais un plantage ; un modèle cloud n'est jamais choisi d'office : un choix explicite mémorisé est repris au lancement, sans réafficher l'avertissement ; après le démarrage, un choix change le modèle à chaud (CAP-34).

## Constraints

- Livraison en deux paliers : le palier 1 (socle) livre l'interface 5 volets, LLM nu, mémoire courte, prompt système, outils, MCP, skills, hooks, compteur/jauge, déclenchement forcé, rejeu, scénarios par brique, réinitialisation, installation, modèle cloud optionnel (CAP-43) ; le palier 2 (complément) livre raisonnement, mémoire globale, RAG, sous-agent, compression, scénarios métier, changement de modèle à chaud. En cas d'arbitrage, MCP/skills/hooks priment sur sous-agent/compression. La V1 complète (palier 1 + 2) est requise avant toute présentation en session.
- **NFR-1 Latence.** Sur le poste de référence (HP EliteBook, i5 vPro, 16 Go, sans GPU) : premier token < 10 s en LLM nu, < 30 s avec la configuration la plus chargée d'un scénario fourni ; ces bornes s'appliquent au premier token de chaque appel dans un tour multi-appels. La fenêtre de contexte est plafonnée pour tenir ces bornes. Ces bornes visent les modèles locaux ; pour un modèle cloud, aucune borne : premier token, durée et débit sont mesurés et affichés.
- **NFR-2 Empreinte mémoire.** 4 Go de RAM au plus pour WaveStack (modèle compris, toutes briques actives), cible 2-3 Go, sur un poste de 16 Go partagé avec le système et les outils de travail. Un modèle servi en externe est compté tant qu'il répond ; jamais deux modèles génératifs chargés à la fois. Les modèles non génératifs (tokenizer, embedding, reranker) coexistent avec le modèle génératif dans le même budget. Un modèle cloud ne coûte rien en mémoire ; quand il est actif, le modèle local n'est pas chargé ou est libéré.
- **NFR-3 Local et hors ligne.** Toutes les briques fonctionnent sans réseau sauf celles explicitement marquées réseau, qui deviennent indisponibles avec explication ; aucune télémétrie.
- **NFR-4 Confidentialité.** Aucune donnée ne quitte le poste hors d'une brique réseau explicitement activée, ou de trois sorties limitées et tracées comme données sortantes (sonde de connectivité du diagnostic, téléchargement de modèle sur demande explicite, appel à un modèle cloud choisi explicitement, test compris). La clé d'un modèle cloud n'est envoyée qu'à l'hôte enregistré avec elle (ressaisie si l'hôte déclaré change) et n'apparaît jamais dans la trace, les journaux ni les réponses de l'API locale. Écoute uniquement sur `127.0.0.1`. Aucune clé d'API requise pour les scénarios fournis.
- **NFR-5 Sans droits admin.** Aucune étape d'installation ni d'exécution ne requiert de droits administrateur ni ne déclenche d'invite du pare-feu.
- **NFR-6 Plateforme.** Cible principale Windows 11 professionnel ; macOS et Linux pris en charge au mieux, sans garantie V1.
- **NFR-7 Langue.** Interface, explications, scénarios et documentation utilisateur en français ; code et identifiants en anglais.
- **NFR-8 Robustesse en démonstration.** Aucune défaillance du modèle (sortie mal formée, boucle d'appels, dépassement de contexte) ne fait planter l'application ; borne de 6 appels au modèle par tour (2 nouveaux essais max, 4 pour le sous-agent, action forcée non comptée, borne réglable) ; un dépassement de contexte empêche l'envoi de l'appel et explique les stratégies possibles en production sans les automatiser en V1. Pour un modèle cloud, dont les tokens sont estimés avant l'envoi, seul un dépassement certain bloque l'appel : sinon il part avec l'avertissement « estimation incertaine », et le refus du fournisseur fait foi.
- **NFR-9 Lisibilité en projection.** L'interface reste lisible en salle ou en visio ; une taille de texte agrandie est disponible.
- **NFR-10 Licences.** Dépôt privé (GitHub privé, puis GitLab interne Wavestone), dont le code peut être remis à un client au cas par cas : toutes dépendances et modèles embarqués sous licence compatible avec une redistribution à des clients et une démonstration client ; licences restrictives signalées avant adoption (Caveman proxy BSL-1.1 écarté, LM Studio propriétaire).
- **NFR-11 Contenu non confidentiel.** Rien de confidentiel dans le dépôt (corpus RAG, scénarios, mémoire globale de démo, hooks), car il est montré et peut être remis à des clients ; aucune donnée client, document interne Wavestone, secret ni clé d'API. Le caractère privé du dépôt n'autorise aucune exception. Les clés API sont stockées hors du dépôt, dans le dossier de données ; un point d'accès interne se déclare dans `settings.json`, jamais dans le dépôt.

Les invariants d'implémentation (paradigme événementiel, ports/adaptateurs, contrats de brique, garde réseau, etc.) sont fixés dans le companion `ARCHITECTURE-SPINE.md` et s'appliquent à toute story.

## Non-goals

- Pas un framework agentique réutilisable ni une bibliothèque.
- Ne vise pas la qualité des réponses : la faiblesse du SLM est assumée et devient un matériau pédagogique.
- Aucun fournisseur de modèle cloud par défaut ni requis : le cloud reste une option explicite (CAP-43).
- Pas un banc d'essai ni un comparateur de modèles.
- Pas de gestion d'utilisateurs, de comptes ni de mode serveur partagé : une instance par poste.
- Évite CrewAI et, plus largement, tout framework multi-agents lourd.
- Pas de multi-agent collaboratif (agents qui dialoguent) — V2.
- Pas de routage vers des modèles spécialisés (modèle de décision, image) — V2.
- Le format chat compatible OpenAI sert aux modèles cloud et aux points d'accès déclarés. Pour un serveur local, WaveStack garde le texte brut natif, qui montre le gabarit : pointer l'adaptateur chat vers un serveur local reste possible par configuration, sans être visé.
- Pas de nouvel essai automatique ni d'espacement des appels face aux quotas d'un fournisseur cloud : le refus est expliqué.
- Pas de RAG avancé (HyDE, self-RAG) — V2.
- Pas d'indexation de documents propres à l'utilisateur — V2.
- Pas d'enregistrement ni de relecture de sessions dans WaveStack — le repli est une vidéo Teams, non prévu dans le produit.
- Pas de démonstration client autonome — conditionnée au succès des sessions internes (V2).

## Success signal

Une session de formation WaveStack fait émerger, en direct et sans slide abstraite, le réflexe de poser la question de l'hébergement (harnais / données / modèle) face à une solution agentique tierce — mesuré en fin de session par le taux de participants qui savent expliquer ce qu'ajoutent skill, MCP, hook et harnais à un LLM nu (SM-1, cible 80 % ou plus) et qui posent spontanément la question de l'hébergement en exercice (SM-3, cible 80 % ou plus). Détail des indicateurs secondaires et contre-indicateurs dans le companion `success-metrics.md`.

## Assumptions

- NFR-1 suppose une génération de plus de 10 tokens/s sur le poste de référence, à confirmer par `llama-bench` avant de figer le modèle par défaut.
- NFR-2 suppose que le périmètre mesuré de l'empreinte mémoire couvre les processus WaveStack (harnais, modèle, serveurs MCP locaux, index RAG) hors navigateur, à confirmer par mesure sur le poste de référence.
- NFR-6 : macOS et Linux restent une cible « au mieux » en V1 ; l'arbitrage définitif revient à Anaël après la session pilote.
- Les cibles chiffrées des indicateurs de succès autres que SM-1 (SM-2 à SM-7) sont à confirmer par Anaël après la session pilote.
- Les mentions des préréglages cloud (hébergement, entraînement, quotas, formats) viennent de la documentation des fournisseurs, non testée clé en main (recherche du 2026-09-24 : 18 affirmations sur 19 à source unique) ; « Tester » avant chaque séance les vérifie en partie.

