---
id: SPEC-wavestack-v1-2-atelier-recherche-documentaire
companions:
  - brownfield.md
  - vues.md
  - architectures.md
  - corpus-et-questions.md
  - evaluation.md
  - attaques-et-conformite.md
  - litterature.md
  - ../spec-lot-5-atelier-rag-2026-10-04/vues-atelier-rag.md
  - ../spec-langues/i18n-conventions.md
  - ../spec-wavestack-v2/decision-model-candidates.md
sources:
  - ../spec-wavestack-v2/SPEC.md
---

> **Canonical contract.** This SPEC and the files in `companions:` are the complete, preservation-validated contract for what to build, test, and validate. Source documents listed in frontmatter are for traceability — consult them only if you need narrative rationale or prose color this contract intentionally omits.

# WaveStack V1.2 : Atelier recherche documentaire

## Why

Vision et opportunité. Anaël lance un projet de banc de comparaison des systèmes de recherche documentaire assistés par IA (brief du 2026-10-17). Ce projet a quatre livrables : une conviction mesurée, un outil de mission, une plateforme pédagogique et une publication éventuelle. Il a décidé que la plateforme pédagogique serait une extension de WaveStack, pas une nouvelle application. La V1.2 en est la première brique : l'Atelier RAG du lot 5 devient un atelier de recherche documentaire. En formation, un participant doit pouvoir, sans écrire de code :
- assembler et modifier une architecture, puis relancer la même question pour voir l'effet ;
- observer chaque étape ;
- comprendre le rôle, le coût et l'état de la littérature de chaque composant ;
- apprendre à évaluer, pièges des juges compris ;
- voir les risques de sécurité et de conformité propres à chaque architecture.

Le banc de mesure à grande échelle et l'optimiseur vivent dans un autre projet.

## Capabilities

**A. Corpus et questions**

- **CAP-1** Corpus Exemplia enrichi
  - **intent:** Le formateur dispose d'un corpus fictif sur lequel chaque type de question, d'attaque et de droit d'accès du lot a un cas concret.
  - **success:** Le corpus compte 25 à 30 documents, décrits dans `corpus-et-questions.md`, et contient au moins :
    - deux chaînes de renvois exploitables en multi-sauts ;
    - un document en deux versions datées ;
    - trois documents présents dans une seule langue ;
    - un document piégé et un document sentinelle, désactivés par défaut ;
    - un marquage de profil (tous, RH) sur chaque document.

    Il tient dans 16 384 tokens par langue avec une question et une réponse, et les tests de miroir i18n sont verts.
- **CAP-2** Jeu de questions (ex-CAP-1 de la V2)
  - **intent:** Le formateur choisit une question préparée dont la réponse et les passages attendus sont connus.
  - **success:** Au moins 3 questions par type (factuelle, multi-sauts, globale, sans réponse, temporelle, interlingue, suivi de conversation), en fr, en et de. Chacune a sa réponse et ses passages attendus. Un test vérifie que chaque passage attendu existe dans le corpus de chaque langue.

**B. Composants de l'atelier**

- **CAP-3** Compréhension de la requête
  - **intent:** Le participant ajoute une étape qui réécrit, décompose, reformule une question de suivi ou génère un document hypothétique (HyDE), et voit la ou les requêtes produites.
  - **success:** Chaque option s'ajoute depuis la palette, s'exécute avec le faux moteur en test, et la requête produite s'affiche dans le focus de l'étape. Sur une question multi-sauts du jeu, la décomposition produit au moins deux sous-requêtes (vérifié par E2E).
- **CAP-4** Découpage
  - **intent:** Le participant choisit un découpage sémantique, parent-enfant ou contextual retrieval (un contexte ajouté à chaque chunk), et voit les chunks produits.
  - **success:** Chaque option est disponible à l'étape de découpage et ses chunks s'affichent dans le focus. Les contextes du contextual retrieval sont livrés précalculés et marqués comme tels. Le late chunking est fait ou explicitement reporté dans `deferred-work.md`.
- **CAP-5** Construction du contexte
  - **intent:** Le participant règle le budget de tokens, l'ordre des passages et une compression, et voit le prompt final changer.
  - **success:** Le budget tronque les passages en le signalant. L'ordre « extrémités d'abord » place les meilleurs passages en tête et en fin de contexte. La compression affiche les tokens avant et après. Le prompt final est visible dans le focus.
- **CAP-6** Couche de décision « System One »
  - **intent:** Le participant ajoute un routeur de stratégie, un filtre de passages ou un contrôle d'ancrage, voit la probabilité de chaque décision et la bascule vers un SLM juge quand la confiance est sous le seuil.
  - **success:**
    - Un banc préalable choisit les modèles du filtre et de l'ancrage ; son rapport est versionné.
    - Chaque décision affiche son auteur (classifieur ou juge), sa probabilité et le seuil.
    - Baisser le seuil change l'auteur d'au moins une décision du jeu de questions.
    - Jev (TypeSafe AI, API de décision) est proposé comme option cloud, active seulement avec une clé ; sans clé, l'option est grisée avec sa raison.
- **CAP-7** Architectures supplémentaires
  - **intent:** Le participant applique en un clic huit architectures de plus, comparables aux trois préréglages : contexte long, CAG, recherche agentique, PageIndex, RAPTOR, GraphRAG, LLM Wiki, Corrective RAG.
  - **success:** Chaque architecture de `architectures.md` s'applique, se valide et s'exécute sur le jeu de questions. Ses étapes apparaissent dans les vues séquence, architecture et focus du lot 5. GraphRAG, LLM Wiki et RAPTOR tournent sur leur contenu précalculé, et leur bouton « reconstruire » est disponible.
- **CAP-8** Coûts en trois temps
  - **intent:** Pour chaque architecture, le participant voit séparément le coût de construction, celui d'une mise à jour (ajout, modification, suppression d'un document) et celui d'une requête.
  - **success:**
    - Chaque exécution affiche les trois coûts en tokens, en durée, en dollars et en gCO₂e.
    - L'embedding, le reranking et l'indexation y sont comptés.
    - La limite de `docs/guide.md:750` est retirée.
    - L'avertissement sur les deux périmètres de mesure (local, cloud) reste affiché.
    - Pour un contenu précalculé, le coût affiché est celui mesuré lors de la construction, marqué comme tel.

**C. Comparer, diagnostiquer, évaluer**

- **CAP-9** Comparer deux exécutions
  - **intent:** Le participant épingle une exécution et la voit à côté de l'exécution courante sur la même question.
  - **success:** Deux colonnes montrent, étape par étape, les passages, les rangs, le prompt final, la réponse et les coûts. Les écarts sont mis en évidence. L'épingle survit à un rechargement (vérifié par E2E).
- **CAP-10** Diagnostic du bon extrait (ex-CAP-2 à CAP-4 de la V2)
  - **intent:** Sur une question préparée, le participant voit le rang du passage attendu à chaque étape et parcourt trois cas d'échec qui naissent chacun à une étape différente.
  - **success:** L'étape où le passage attendu disparaît ou chute est désignée sans lire la réponse. Les trois cas « Où naît l'erreur » s'ouvrent en un clic, sans appel au modèle.
- **CAP-11** Vue d'évaluation
  - **intent:** Le participant apprend à évaluer une architecture : verdicts de juges LLM par question et par critère face à une annotation humaine, métriques agrégées, et pièges des juges et des outils.
  - **success:**
    - Les métriques de `evaluation.md` sont calculées en interne et affichées avec la taille de l'échantillon et le bandeau « démonstration, pas un banc ».
    - Les quatre pièges de `evaluation.md` se démontrent sur des cas livrés.
    - Le panel compte un juge local et un juge cloud. Un juge n'est jamais de la même famille que le modèle jugé.
    - Le piège « le juge change le classement » oppose le juge local et le juge cloud. Sans clé cloud, il s'affiche depuis un résultat enregistré, marqué comme tel.
    - Les adaptateurs Ragas et DeepEval restent absents de l'installation par défaut.

**D. Observabilité**

- **CAP-12** Arbre des étapes et export OpenTelemetry
  - **intent:** Le participant voit l'exécution comme un arbre d'étapes, que le formateur peut exporter vers son Langfuse ou son Phoenix.
  - **success:**
    - L'arbre (étape, sous-étape, appel de modèle) s'affiche à partir de `trace/`, avec durées et tokens.
    - Une fois l'extra `otel` installé et l'URL OTLP réglée, une exécution produit des spans aux conventions GenAI, vérifiées par un test avec un faux collecteur.
    - Sans réglage, rien ne sort du poste.

**E. Sécurité et conformité**

- **CAP-13** Document piégé
  - **intent:** Le formateur active un document piégé et montre l'injection indirecte et l'empoisonnement, dans le RAG et dans le graphe, avec et sans garde-fous.
  - **success:** Les trois scénarios de `attaques-et-conformite.md` produisent chacun l'effet attendu sans garde-fou et un verdict visible avec garde-fou. Le document piégé est inactif par défaut.
- **CAP-14** Droit à l'effacement
  - **intent:** Le formateur supprime le document sentinelle et vérifie s'il remonte encore par les chunks, le graphe, le wiki ou les caches.
  - **success:** Pour chaque architecture, une vérification liste chaque copie ou dérivé de la sentinelle : présent, effacé ou « à reconstruire ». Une requête sur la sentinelle après effacement montre ce qui fuit encore.
- **CAP-15** Deux profils de droits
  - **intent:** Le formateur bascule entre deux profils et montre la fuite quand le filtrage se fait après la recherche, et son absence quand le contrôle d'accès est déterministe et passe avant le LLM.
  - **success:** Une question du jeu fait apparaître un passage RH au profil « tous » en mode filtrage après recherche, et jamais en mode contrôle avant recherche (vérifié par pytest et E2E).
- **CAP-16** Fiche conformité par architecture
  - **intent:** Le participant lit, pour chaque architecture, ses risques sur sept axes : localisation des données, copies et contenu dérivé, effacement, droits d'accès, injection et outils, traçabilité, cadre réglementaire.
  - **success:** Chaque architecture a sa fiche en fr, en et de, alimentée par les mêmes données que la matrice des risques de la page Sécurité et reliée aux démonstrations de CAP-13 à CAP-15.

**F. Fiches pédagogiques**

- **CAP-17** Fiche par composant et par architecture
  - **intent:** Le participant lit à quoi sert chaque composant ou architecture, quand l'utiliser ou l'éviter, ce qu'il coûte et ce qu'en dit la littérature, avec les liens.
  - **success:**
    - Chaque option de `OPTIONS` et chaque préréglage a sa fiche déclarée dans `content/`, en fr, en et de.
    - La littérature reprend les hypothèses de `litterature.md` avec leurs liens, ou à défaut une source primaire ouverte et citée.
    - Un bloc « ce qu'a mesuré le banc » reste vide tant que le projet de banc ne publie rien.
    - Un test vérifie que les clés sont exhaustives et qu'il y a au moins une source par fiche.

**G. Optionnel, en fin de lot**

- **CAP-18** Architecture exposée en MCP
  - **intent:** Le formateur expose l'architecture composée comme serveur MCP, branchable dans Copilot Studio ou Claude.
  - **success:** Un client MCP de test liste l'outil de recherche et reçoit des passages cités.
- **CAP-19** Recherche visuelle sans OCR
  - **intent:** Le lot dit si ColPali ou ColQwen tient dans le budget du CPU.
  - **success:** Une note mesurée (mémoire, latence, dépendances) conclut, et l'éventuel écart est consigné dans `deferred-work.md`.

## Constraints

- **Matériel cible.**
  - CPU seul, 4 Go de budget mémoire, un seul modèle génératif chargé à la fois (`LoadRegistry`), fonctionnement hors ligne, installation sans droits administrateur.
  - Un modèle cloud est toujours une option, jamais un prérequis.
  - Un modèle cloud (génération, juge, décision) ne reçoit que le corpus fictif Exemplia. Sa dépense est plafonnée par `[finops] max_session_usd`.
- **Contenu précalculé.** Les étapes trop lourdes pour le CPU sont livrées précalculées comme contenu, avec un bouton « reconstruire » : graphe, wiki, arbre RAPTOR, contextes de chunks.
- **Contexte long et CAG.** Ils exigent la fenêtre de 16 384 tokens (`config.WINDOW_CHOICES`). Le corpus enrichi doit y tenir.
- **Outillage.**
  - Uniquement `uv`, `ruff` et `pytest`.
  - Toute nouvelle dépendance va dans un extra épinglé et est justifiée dans `brownfield.md`.
  - Ni torch ni service à démarrer, sauf accord explicite d'Anaël.
- **Réutilisation de l'Atelier RAG du lot 5, sans duplication.** On réutilise ses registres (`lab.py`), `Pipeline`, `LabRun`, ses vues et ses préréglages. Une architecture est un préréglage ou une variante de chaîne, pas une page à part.
- **Interdiction des agrégats.** L'interdiction des métriques agrégées de la V2 est levée dans la seule vue Évaluer (CAP-11). Les autres vues l'appliquent toujours.
- **Mesures d'évaluation recalculées en interne.** Les adaptateurs Ragas et DeepEval sont optionnels, dans un extra épinglé.
- **Observabilité.** Aucun service n'est embarqué dans WaveStack, et rien ne sort du poste sans URL OTLP réglée par le formateur.
- **GreenOps.** L'avertissement sur les deux périmètres de mesure (local : électricité ; cloud : cycle de vie) est conservé.
- **Fichiers carrefour** (`ui.yaml`, `messages.yaml`, `app.py`, `app.js`, `run_e2e.py`) : ajouts seulement, groupés par section.
- **Langues.**
  - Code, identifiants et commentaires en anglais.
  - Textes d'interface en fr, avec des copies en et de sous `content/i18n/`.
  - Les contrôles `tests/test_i18n.py` et `RagLabContent` restent verts.
- **Tests.**
  - Faux moteurs existants, aucun modèle réel dans la suite par défaut.
  - Un E2E Playwright pour chaque nouvelle vue.
- **Méthode.**
  - Une story à la fois, avec un point d'étape à la fin de chacune : ce qui est fait, tests, captures, écarts à la spec.
  - Rien n'est codé avant la validation de cette spec par Anaël.

## Non-goals

- Le banc de mesure à grande échelle et l'optimiseur de configuration (optimisation bayésienne) : autre projet.
- Le benchmark des bases vectorielles au million de chunks ; GenBI, l'audio et la vidéo.
- Les corpus personnels d'Anaël : jamais dans le dépôt.
- Les réimplémentations industrielles : les architectures sont pédagogiques et légères.
- Le routage par coût et par spécialité (CAP-7 et CAP-8 de la V2) : il reste dans la V2.
- La chaîne B composée en parallèle et sa synthèse de comparaison : elles ne reviennent pas.
- La notation automatique de la réponse hors de la vue Évaluer.

## Success signal

En formation, sur un PC sans GPU et hors ligne, un participant :
1. applique GraphRAG puis le RAG hybride à la même question multi-sauts ;
2. épingle la première exécution ;
3. constate côte à côte que GraphRAG coûte plus à la construction, à la mise à jour et à la requête ;
4. ouvre la vue Évaluer et voit deux juges se contredire sur une question ;
5. efface le document sentinelle et voit où il survit encore.

Tout cela sans écrire de code. L'E2E complet de l'atelier est vert.

## Assumptions

- Les nouvelles vues sont des onglets de la page `/rag`, renommée « Atelier recherche documentaire » : Construire (les vues du lot 5), Comparer, Évaluer, Attaquer et Fiches (`vues.md`). La barre commune ne gagne pas d'onglet.
- Le corpus enrichi fait environ 12 000 tokens par langue.
- Qwen3.5-2B avec une fenêtre de 16 384 tokens tient dans 4 Go ; c'est mesuré dans la story de banc.
- L'export OpenTelemetry passe par `opentelemetry-sdk` et l'exporteur OTLP HTTP (pur Python), dans un extra `otel`.
- L'accès à Jev (accès anticipé de TypeSafe, ou Eden AI en alpha) sera obtenu d'ici la story 2. Sinon, le banc le mesure sur les seuls chiffres publiés, et le reporte dans `deferred-work.md`.
