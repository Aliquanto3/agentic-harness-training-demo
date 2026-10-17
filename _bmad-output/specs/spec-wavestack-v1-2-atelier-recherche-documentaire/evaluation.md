# Vue Évaluer (CAP-11) et diagnostic (CAP-10)

## Diagnostic du bon extrait (CAP-10, ex-CAP-2 à CAP-4 de la V2)

- **Rang du passage attendu à chaque étape** qui ordonne des passages : recherche dense, BM25, fusion, reranking, filtre et contexte final.
- **Étape fautive** : la première où le passage attendu sort du top-k ou chute de plus de N rangs (N réglable).
- **Hors de la vue Évaluer**, l'affichage reste par question : aucune moyenne.
- **Module « Où naît l'erreur »** : trois cas livrés, rejoués sans appel au modèle depuis une exécution enregistrée.
  - Le passage n'est pas dans l'index (découpage).
  - Le passage est mal classé par la recherche, puis repêché par le reranking.
  - Le passage est dans le contexte, mais perdu au milieu ou coupé par le budget.

## Critères et métriques (recalculés en interne)

| Mesure | Niveau | Définition retenue | Source de vérité |
|---|---|---|---|
| Rappel@k des passages | Recherche | Part des passages attendus présents dans les k premiers | Jeu de questions |
| MRR | Recherche | Moyenne de 1/rang du premier passage attendu | Jeu de questions |
| Précision du contexte | Contexte | Part des passages du contexte jugés pertinents | Juge LLM |
| Fidélité (ancrage) | Réponse | Part des affirmations de la réponse soutenues par le contexte | Juge LLM |
| Pertinence de la réponse | Réponse | La réponse traite-t-elle la question ? | Juge LLM |
| Exactitude | Réponse | Accord avec la réponse attendue | Juge LLM, annotation humaine |
| Refus correct | Réponse | « Je ne sais pas » sur une question sans réponse | Règle et juge |

**Ce que la vue affiche** :
- par question et par critère : le verdict de chaque juge, l'annotation humaine quand elle existe, l'accord ou le désaccord ;
- puis les agrégats, avec n (taille de l'échantillon) et le bandeau « démonstration, pas un banc ».

**Les juges** : un panel de deux juges de familles différentes, chacun critère par critère, sans score global par question.
- **Juge local** : un SLM GGUF, sortie contrainte par GBNF.
- **Juge cloud**, pris parmi les `[[cloud.models]]` déjà déclarés (Mistral Small, Gemini Flash-Lite, Claude Haiku…) :
  - requis pour le piège 4 ;
  - choisi par le formateur ;
  - activé seulement avec sa clé ;
  - dépense plafonnée par `[finops] max_session_usd`.
- **Règle du cadrage** : un juge ne note jamais un modèle de sa propre famille. Le modèle génératif par défaut est un Qwen, donc le juge local n'est pas un Qwen.
  - Le juge de même famille est écarté avec un message.
  - La fiche de la vue cite ce biais d'auto-préférence.
- **Sans clé cloud**, les pièges qui l'exigent s'affichent depuis un résultat enregistré, livré et marqué « enregistré le … avec … ».

## Pièges à démontrer (cas livrés)

| Piège | Démonstration |
|---|---|
| Deux juges, deux verdicts | Même question, même réponse : le juge A dit « fidèle », le juge B dit « non fidèle » ; on montre les deux justifications |
| Variance d'un même juge | Deux passages du même juge sur le même cas donnent deux verdicts (température, ordre des passages) |
| Deux outils, deux définitions | La « fidélité » de Ragas (affirmations soutenues par le contexte) et celle de DeepEval (contradictions avec le contexte) notent différemment la même réponse ; la vue affiche les deux définitions côte à côte, recalculées en interne |
| Le juge change le classement | Deux architectures classées A > B par le juge local et B > A par le juge cloud, sur le même jeu (H15 de `litterature.md`) |

**Adaptateurs Ragas et DeepEval** : ils sont facultatifs, dans l'extra `eval-adapters`, et servent à recouper les recalculs internes. Ils ne sont jamais requis pour afficher la vue.
