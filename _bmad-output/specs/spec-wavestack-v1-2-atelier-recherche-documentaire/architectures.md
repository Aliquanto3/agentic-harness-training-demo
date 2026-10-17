# Architectures et composants de la V1.2

Chaque architecture est un préréglage de l'atelier (`PRESETS`), au même titre que dense, hybride et reranking. Elle est déclinée en version pédagogique et légère. On voit séparément ses coûts de **construction (B)**, de **mise à jour (U)** et de **requête (Q)**, à la manière de CAP-8.

## Nouveaux composants (options ou étapes de la chaîne)

| Groupe | Option | Phase | Ce qui s'affiche dans le focus | Modèle |
|---|---|---|---|---|
| Compréhension de la requête | rewrite | run | Requête réécrite | Génératif |
| | decompose | run | Sous-requêtes (au moins 2 en multi-sauts) | Génératif |
| | follow_up | run | Question autonome reformulée depuis l'historique | Génératif |
| | hyde | run | Document hypothétique, puis son embedding | Génératif, embedding |
| Découpage | semantic | build | Frontières décidées par la similarité de phrases | Embedding |
| | parent_child | build | Enfants indexés, parent renvoyé au contexte | — |
| | contextual | build | Contexte LLM ajouté à chaque chunk (précalculé) | Génératif (reconstruire) |
| | late (optionnel) | build | Embeddings de chunks pris dans le document entier | Embedding à contexte long |
| Construction du contexte | budget | run | Passages gardés et coupés, tokens | — |
| | order | run | Ordre « pertinence » ou « extrémités d'abord » | — |
| | compress | run | Tokens avant et après | Extra `compression` (existant) |
| System One | router | run | Stratégie choisie, probabilité, auteur | `deberta_xsmall`, puis SLM juge en repli |
| | passage_filter | run | Passages gardés ou rejetés, probabilité | Choisi par le banc, puis SLM juge en repli |
| | grounding_check | run | Phrases ancrées ou non, probabilité | Choisi par le banc, puis SLM juge en repli |

Pour chaque décision System One, l'affichage montre :
- l'auteur (classifieur ou juge) ;
- la probabilité ;
- le seuil réglable ;
- la cascade vers le juge sous le seuil.

**Candidats du banc préalable** (story 2), repris du cadrage et de `decision-model-candidates.md` :

| Candidat | Où il tourne | Rôle visé | Remarque |
|---|---|---|---|
| `deberta_xsmall` | Local, ONNX, 87 Mo, MIT | Routeur | Déjà retenu par le banc CAP-6 de la V2 |
| Strands Decider 2B | Local | Routeur, filtre, ancrage | Cité par le cadrage, à mesurer (format, licence, RAM) |
| [AnyJev (Nokia)](https://github.com/nokia-applied-research/AnyJev) | Local | Filtre, ancrage | Cité par le cadrage, à mesurer |
| Reranker déjà livré | Local | Filtre de passages | Seuil sur son score |
| Petit NLI en ONNX | Local | Contrôle d'ancrage | À choisir dans le banc |
| Jev (TypeSafe AI) | Cloud, API de décision | Routeur, filtre, ancrage | Voir ci-dessous |
| Microsoft-Decision-1 | Cloud, Azure AI Foundry | Routeur, filtre, ancrage | Cité par le cadrage ; budget Azure à confirmer |
| Qwen3.5-2B + GBNF | Local | Juge de repli de la cascade | Déjà mesuré (CAP-6 de la V2) |

**Jev**, d'après la recherche du 2026-10-17 :
- **Éditeur** : TypeSafe AI ; modèle propriétaire, sans poids publiés ni hébergement local.
- **Accès** :
  - accès anticipé sur liste d'attente depuis le 2026-09-15 ;
  - aussi servi par Eden AI à `POST /v3/alpha/decisions` (modèle `typesafe/jev-latest`), un endpoint alpha dont la forme peut changer.
- **Questions** :
  - `Choice` : renvoie une étiquette, `confidence` et `probabilities` ;
  - `Score` : grille de 2 à 10 niveaux ;
  - `Noul` : renvoie la probabilité du oui.
- **Prix et performances** : 0,042 $ par million de tokens d'entrée, sortie gratuite ; 70 à 500 ms par appel ; environ 32 000 tokens par requête.
- **Intégration** :
  - un adaptateur dédié à l'API de décision, qui n'est pas un modèle de chat ;
  - clé dans une variable d'environnement, sur le modèle de `key_env` des `[[cloud.models]]` ;
  - désactivé sans clé.
- **Sources** : [Eden AI](https://www.edenai.co/post/jev-a-new-kind-of-ai-model-built-for-decisions-not-conversation), [eesel.ai](https://www.eesel.ai/blog/typesafe-jev-pricing), [Layer3Labs](https://www.layer3labs.io/guides/jev-pricing). Aucune page de prix officielle trouvée.
- **Limite connue** (H7) : il accepte 23 % d'affirmations non étayées, contre 13 % pour un LLM. C'est la raison de la cascade vers un juge sous le seuil.

## Architectures

| Id | Architecture | Construction (B) | Mise à jour (U) | Requête (Q) | Précalculé livré | Réutilise |
|---|---|---|---|---|---|---|
| `long_context` | Contexte long, sans recherche | Aucune | Aucune | Tout le corpus dans le prompt (~12 k tokens) | — | Fenêtre de 16 384 |
| `cag` | CAG | Corpus préchargé dans le cache du modèle (préfixe) | Recharger tout le cache | Question seule après le préfixe en cache | Non (préfixe calculé au premier usage) | `engine.snapshot/restore`, `cache_prompt` |
| `agentic` | Recherche agentique | Aucune | Aucune | Boucle d'outils `list_files`, `grep`, `read_file` sur le corpus | — | Brique outils et MCP |
| `pageindex` | PageIndex | Arbre des sections (titres, résumés courts) | Recalcul de l'arbre du document modifié | Descente dans l'arbre par le modèle | Arbre | Génératif |
| `raptor` | RAPTOR | Regroupement des chunks et résumés récursifs | Résumés des branches touchées à refaire | Recherche sur tous les niveaux | Arbre de résumés | Embedding, génératif |
| `graphrag` | GraphRAG simplifié | Extraction d'entités et de relations, communautés, résumés de communautés | Ré-extraction du document, fusion, communautés à recalculer | Locale (entités voisines) ou globale (résumés de communautés) | Graphe et résumés | Maison, inspiré de LightRAG |
| `llm_wiki` | LLM Wiki (pattern de Karpathy) | Compilation d'un wiki Markdown depuis les sources | Recompilation des pages touchées, puis passe de lint | Recherche sur les pages du wiki | Wiki | Génératif |
| `crag` | Corrective RAG | Celle du RAG hybride | Celle du RAG hybride | Filtre des passages, puis repli (réécriture et nouvelle recherche, ou « je ne sais pas ») | — | System One `passage_filter` |

## Règles communes

- **Contenu précalculé.**
  - Il est livré sous `content/` dans les trois langues, avec la mesure de sa construction : tokens, durée, modèle et date.
  - Ce coût est affiché « mesuré à la construction ».
  - Le bouton « reconstruire » refait la construction avec le modèle actif, local ou cloud, et en affiche le coût réel.
- **Mise à jour.** Elle se démontre sur trois opérations :
  - ajout d'un document ;
  - modification (la nouvelle version du document versionné de CAP-1) ;
  - suppression (la sentinelle, CAP-14).
- **Message pédagogique.** Il doit se lire dans les chiffres, sans commentaire : GraphRAG et le LLM Wiki coûtent plus à toutes les étapes, le CAG ne coûte rien à la requête mais tout à la mise à jour, et le contexte long ne coûte rien à construire mais tout à chaque requête.
- **Disponibilité.** Une architecture est refusée, avec sa raison affichée, si :
  - son modèle manque ;
  - la fenêtre de contexte n'est pas réglée sur 16 384 tokens alors qu'elle l'exige ;
  - son extra n'est pas installé.

  Le refus suit la même règle que FAISS et LanceDB aujourd'hui.
