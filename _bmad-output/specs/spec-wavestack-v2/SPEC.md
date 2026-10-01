---
id: SPEC-wavestack-v2
status: draft
companions:
  - brownfield.md
  - decision-model-candidates.md
  - ../spec-agentic-harness-training-demo/SPEC.md
  - ../spec-agentic-harness-training-demo/success-metrics.md
  - ../../planning-artifacts/architecture/architecture-agentic-harness-training-demo-2026-09-23/ARCHITECTURE-SPINE.md
sources:
  - ../../forge/wavestack-v2-demo-client-vente-formations/forged-idea.md
---

> **Non déclenchée : conditions de la forged idea non remplies au 2026-10-01.**
> Aucune session pilote n'a eu lieu : SM-1, SM-3 et SM-6 ne sont pas mesurés. Aucune demande d'approfondissement n'a été constatée, et l'usage en clientèle n'est pas validé par Wavestone. Ce brouillon prépare la V2 ; il ne la lance pas. Aucune story de fonction ne part avant les conditions 1 et 2 de « Déclenchement » (contraintes).

> **Canonical contract.** This SPEC and the files in `companions:` are the complete, preservation-validated contract for what to build, test, and validate. Source documents listed in frontmatter are for traceability — consult them only if you need narrative rationale or prose color this contract intentionally omits.

# WaveStack V2 : modules de formation construits sur le démonstrateur

## Why

C'est une **opportunité** : vendre des modules de formation construits sur WaveStack, après la V1. Ce n'est pas la liste des fonctions reportées de la V1 : celles-ci ont été reportées parce qu'elles alourdissaient la V1, pas parce qu'elles servaient une cible.

La V2 approfondit la pédagogie pour une seconde audience :
- les **équipes techniques**, pour voir d'où viennent les erreurs (par exemple une perte de qualité en RAG) ;
- la **gouvernance technique**, pour des méthodes actionnables : FinOps, GreenOps, cyber, conformité.

Les consultants Wavestone passent d'abord, puis les équipes de gouvernance des clients. On vend des modules, pas le logiciel. Un module associe un scénario WaveStack et des slides récap à emporter. La démo client de type UJ-4 marche déjà en V1 : c'est un produit dérivé, pas la V2.

Le risque central : avec un SLM faible sur CPU, l'erreur du modèle masque l'erreur d'architecture. La V2 montre donc l'erreur **dans le contexte, avant la génération**, jamais par la qualité de la réponse.

## Capabilities

Repères : **[V1]** marque une base existante, **[neuf]** ce qui manque. Le détail de l'existant (fichiers, fonctions) est dans `brownfield.md`. CAP-1 à CAP-6 forment l'**incrément 1** (`stories.yaml`) ; CAP-7 à CAP-12 viennent après.

- **CAP-1** Jeu de questions de démonstration avec réponses attendues (incrément 1, [neuf])
  - **intent:** Le formateur choisit une question d'un petit jeu fourni. Chaque question porte sa réponse attendue et le passage du corpus qui la contient, dans chacune des trois langues.
  - **success:** Pour chaque question du jeu et chaque langue, le passage attendu est retrouvé dans le corpus de cette langue (test) ; dans l'interface, choisir une question la place dans la saisie et désigne son bon extrait pour le diagnostic.
- **CAP-2** Diagnostic du bon extrait dans la vue harnais (incrément 1, [neuf] sur CAP-18, CAP-19, CAP-31 [V1])
  - **intent:** Pour une question du jeu, la vue harnais dit, avant la génération, où est le bon extrait et quelle étape l'a perdu : retrouvé ou non, rang avant et après reranking, gardé dans le contexte ou coupé, position et tokens dans le contexte.
  - **success:** Sur chacun des cas d'échec du module (CAP-4), l'étape fautive est désignée par le harnais, sans lire la réponse du modèle ; une question hors du jeu ne déclenche aucun diagnostic.
- **CAP-3** Diagnostic du bon extrait dans l'Atelier RAG (incrément 1, [neuf] sur CAP-45 [V1])
  - **intent:** Dans l'Atelier RAG, pour une question du jeu, chaque étape montre le rang du bon extrait, et l'étape contexte compte des tokens ; la comparaison A/B dit quelle chaîne place le bon extrait le plus haut.
  - **success:** Deux chaînes qui diffèrent par une seule étape (par exemple avec ou sans reranking) donnent deux rangs du bon extrait lisibles côte à côte, et la synthèse A/B les nomme.
- **CAP-4** Module « Où naît l'erreur d'un RAG » (incrément 1, [neuf] sur les scénarios et modules [V1])
  - **intent:** Un module V2 joue au moins trois cas d'échec du RAG à partir du jeu de questions, chacun localisé à une étape différente.
  - **success:** Chaque cas se lance en un clic ; le diagnostic de CAP-2 y désigne une étape fautive différente ; aucune réponse du modèle n'est nécessaire à la démonstration.
- **CAP-5** Coût contrefactuel d'un tour local (incrément 1, [neuf] sur le FinOps cloud [V1])
  - **intent:** Pour un tour mené avec un modèle local, WaveStack donne l'ordre de grandeur de ce qu'aurait coûté le même tour chez chaque modèle cloud déclaré avec un prix. Les prix sont datés et sourcés, et présentés comme une hypothèse.
  - **success:** Un tour local affiche ces estimations, marquées « ≈ », avec la date et la source du prix, sans aucun appel réseau ; un modèle cloud sans prix déclaré n'apparaît pas.
- **CAP-6** Test préalable des modèles de décision (incrément 1, [neuf])
  - **intent:** Un banc hors produit mesure chaque candidat de `decision-model-candidates.md` selon les critères du test préalable, et rend un verdict par échelon du routage.
  - **success:** Un verdict écrit (retenu, écarté ou à surveiller, avec ses mesures) existe pour chaque candidat, relevé sur le PC cible. Aucune story de routage (CAP-7, CAP-8) ne part sans ce verdict.
- **CAP-7** Routage par coût (après l'incrément 1, dépend de CAP-6)
  - **intent:** Le harnais choisit le modèle d'un tour selon le coût. Il montre la décision, les tokens réels et le coût estimé de l'alternative (CAP-5).
  - **success:** La vue harnais montre pour chaque tour routé la décision, qui l'a prise (classifieur, règle, SLM juge) et le coût contrefactuel de l'option écartée.
- **CAP-8** Routage par spécialité en trois échelons (après l'incrément 1, dépend de CAP-6)
  - **intent:** La même question passe par trois routeurs : classifieur à étiquettes fixes, encodeur programmable, SLM utilisé comme juge. Le message porte sur l'endroit où vit la règle, qui la modifie et qui l'audite.
  - **success:** Pour une même question, chaque échelon affiche sa décision et l'endroit où sa règle est écrite : dans les poids, dans le texte des critères, dans le prompt.
- **CAP-9** Bascule annoncée entre modèles génératifs (après l'incrément 1, [neuf] sur le `LoadRegistry` [V1])
  - **intent:** Quand une démonstration change de modèle génératif, WaveStack décharge puis recharge, et prévient de l'attente avant de commencer.
  - **success:** Toute bascule affiche la durée attendue avant de démarrer ; jamais deux modèles génératifs ne sont chargés.
- **CAP-10** Module multi-agent collaboratif (après l'incrément 1, [neuf] sur le sous-agent [V1])
  - **intent:** Un module montre ce que coûte la collaboration entre agents : la multiplication des tokens et la perte d'information d'un agent à l'autre.
  - **success:** Un tour multi-agent affiche les tokens par agent et ce que chaque agent a reçu des autres.
- **CAP-11** Indexation de documents propres, avec questions de contrôle (après l'incrément 1, [neuf])
  - **intent:** Le participant indexe ses propres documents et écrit ses questions de contrôle avec leurs réponses attendues, diagnostiquées comme celles du jeu fourni.
  - **success:** Une question écrite par le participant passe par le même diagnostic que CAP-2.
- **CAP-12** Format chat compatible OpenAI comme fonction d'appui (après l'incrément 1, [neuf] sur l'adaptateur `openai_chat` [V1])
  - **intent:** Un serveur local au format chat devient une voie prise en charge. C'est une fonction d'appui, pas un module.
  - **success:** Les scénarios fournis tournent sur un serveur local au format chat sans modification.

## Constraints

- **Déclenchement.** Trois conditions, définies le 2026-09-25 :
  1. La V1 tient au pilote : SM-1 et SM-3 à leur cible, SM-6 sans repli forcé.
  2. Il y a une demande : *N* profils techniques ou gouvernance demandent un approfondissement, ou une practice ou un client demande un module.
  3. Avant toute présentation client : validation Wavestone de l'usage en clientèle.
  Aucune story de fonction ne part avant (1) et (2). Le banc de CAP-6 n'est pas une fonction : il peut partir avant, sur décision d'Anaël (donnée le 2026-10-01).
- **Diagnostiquer dans le contexte, pas dans la réponse.** Mesures d'avant génération. La qualité de la réponse reste secondaire (SM-C1). On garde le SLM sur CPU et le budget de 4 Go (NFR-2).
- **Jamais deux modèles génératifs chargés.** Classifieurs et encodeurs passent par le `LoadRegistry`, dans le budget, comme l'embedding et le reranker de la V1. Un modèle gardien génératif (Llama-Guard, Qwen3Guard) tombe sous la règle d'un seul modèle génératif.
- **Le jeu de questions reste une démonstration.** Chaque question sert un scénario. L'interface n'affiche aucune métrique agrégée (rappel, MRR, score de réponse) : ce n'est pas un banc d'essai.
- **Modèle de décision : même règle que Headroom.** La spec nomme la catégorie, « modèle de décision programmable » ; Decision 1.0 (vLLM Semantic Router) est le candidat. Le test préalable est obligatoire, avec ses critères dans `decision-model-candidates.md`. Au 2026-09-25, il échoue : ni GGUF ni ONNX, pas de chemin CPU. Le repli est le SLM utilisé comme juge (critères dans le prompt, sortie contrainte), et la leçon « où vit la règle » reste intacte.
- **Prix et énergie sont des hypothèses.** Les prix sont datés, sourcés et donnés en ordre de grandeur ; la grille vieillit vite. L'énergie consommée dans le cloud n'est pas publiée : toute comparaison d'énergie est une hypothèse, affichée comme telle.
- **Un module vendu = un scénario WaveStack + des slides récap à emporter.** Les slides portent la méthode actionnable ; le démonstrateur ne la porte pas seul.
- **Dépôt et diffusion.** Dépôt privé : GitHub, puis GitLab interne. Licences compatibles avec une remise du code à des clients, contenu non confidentiel (NFR-10, NFR-11). Chez le client, la démo se fait par défaut sur le poste du consultant ; la remise du code se négocie au cas par cas.
- **Langues.** Tout nouveau contenu (questions, réponses attendues, passages, scénarios) existe en français, avec ses surcouches `en` et `de` sous `content/i18n/`, mêmes identifiants (convention du dépôt).
- Les invariants de la V1 (`ARCHITECTURE-SPINE.md` : événements, ports, budget, garde réseau, contenus en données) s'appliquent à toute story V2.

## Non-goals

Rejeté par la forge du 2026-09-25 :
- Reprendre telle quelle la liste V2 du SPEC V1.
- Grossir le modèle ou passer par un fournisseur externe pour rendre visible la dégradation de la réponse : cela casse les 4 Go et l'argument de souveraineté.
- Un modèle d'image : trop lourd, et il ne sert aucune audience visée.
- Arch-Router-1.5B : sa licence exige une licence commerciale DigitalOcean.
- Un dépôt public servant de vitrine.

Hors périmètre :
- Noter automatiquement la réponse du modèle face à la réponse attendue.
- Vendre ou distribuer le logiciel comme un produit.
- Produire les slides récap dans le démonstrateur.
- Dans l'incrément 1 : toute fonction de routage (CAP-7, CAP-8), et la comparaison d'énergie cloud d'un tour local.

## Success signal

Dans une session d'essai avec des profils techniques, le formateur joue les cas d'échec du module de CAP-4. Pour chacun, la vue harnais désigne l'étape qui a perdu le bon extrait avant toute génération, et les participants nomment cette étape sans s'appuyer sur la réponse du modèle. En fin de module, le même tour local affiche son coût contrefactuel cloud, daté et sourcé. La mesure d'appropriation (questionnaire, exercice de restitution éventuel) reste à définir au pilote.

## Assumptions

- La réponse attendue est montrée au formateur et sert à désigner le bon extrait ; elle n'est jamais comparée automatiquement à la réponse du modèle.
- Le bon extrait se repère par son document et une ancre textuelle (une phrase du passage), pas par `chunk_id`, pour survivre à un autre découpage dans l'Atelier RAG.
- Le jeu compte de 6 à 12 questions, chacune rattachée à un cas d'échec visé.
- Le corpus V1 (8 documents Exemplia) permet au moins trois cas d'échec distincts ; sinon, un document de démonstration s'ajoute, non confidentiel et traduit.
- CAP-5 compare aux seuls modèles cloud déclarés avec `pricing`, qui restent la seule source de prix, déjà datée et sourcée.

## Préalables hors code

- Ajouter au questionnaire du pilote une question « envie d'approfondir » (profils techniques et gouvernance) : sans elle, la condition 2 ne se mesure pas.
- Ouvert jusqu'au pilote : la valeur de *N* et les seuils de la condition 2, les cibles de SM-2 à SM-7, la remise d'un zip au client (selon SM-5), l'exercice de restitution « votre message à la direction en 3 phrases », l'ordre des modules V2, macOS et Linux (NFR-6).

## Questions ouvertes pour Anaël

**Tranchées le 2026-10-01 : Anaël suit les cinq recommandations.** Avant le pilote, seuls la story 6 et la question du questionnaire partent ; 9 questions écrites par l'agent de la story 1 et relues par Anaël ; réponse attendue affichée sans score ; coût contrefactuel contre les seuls modèles cloud déclarés avec un prix ; slides récap hors du dépôt. La spec reste non déclenchée pour les stories 1 à 5.

1. **Que préparer avant le pilote ?** Recommandation : seulement le test préalable (story 6, un banc hors produit qu'il faut de toute façon refaire, Decision 1.0 évoluant vite) et la question du questionnaire. Les stories 1 à 5 attendent les conditions 1 et 2.
2. **Qui écrit le jeu de questions, et combien ?** Recommandation : 9 questions françaises (trois par cas d'échec), rédigées par l'agent de la story 1 à partir des 10 requêtes de `tools/bench/story12_bench.py`, relues par toi, puis traduites.
3. **La réponse attendue sert-elle à noter la réponse du modèle ?** Recommandation : non. Elle s'affiche pour le formateur, sans score (SM-C1, « pas un banc d'essai »).
4. **Contre quels modèles chiffrer le coût contrefactuel ?** Recommandation : les seuls modèles cloud déclarés avec un prix (Groq, Mistral, Gemini). Ajouter une grille de grands modèles payants ferait une deuxième source de prix qui vieillit.
5. **Où vivent les slides récap des modules ?** Recommandation : hors du dépôt, dans l'espace documentaire Wavestone de la practice. Le dépôt reste remettable à un client, et les slides vendues n'y circulent pas.
