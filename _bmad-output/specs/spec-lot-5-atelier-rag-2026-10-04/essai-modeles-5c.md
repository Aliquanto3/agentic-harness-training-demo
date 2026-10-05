# Essai des modèles candidats de 5c (2026-10-05)

Préalable à 5c-1 et 5c-2. Essai sur le PC de développement (CPU, llama-cpp-python 0.3.35),
avec les chargeurs du projet (`models/embedding.py`, `models/reranker.py`), fichiers GGUF dans le
dossier temporaire de la session (le dossier de données partagé n'est pas touché). Question
« Quelle est la capitale de la France ? » contre trois passages : Paris (pertinent), le Rhin à
Strasbourg, Berlin (en allemand). Mêmes phrases en anglais pour les rerankers.

## Résultats

| Modèle | Fichier (dépôt @ commit) | Taille | sha256 (= oid LFS HF) | Résultat |
| --- | --- | --- | --- | --- |
| Granite Embedding 107M (référence) | bartowski/granite-embedding-107m-multilingual-GGUF @ 52fed1c | 121 020 096 | (déjà dans `wavestack.toml`) | OK, 384 dims, pooling CLS, cos 0,89 / 0,52 / 0,77, RSS +443 Mo |
| multilingual-e5-small Q8_0 | TwinSunsLLC/multilingual-e5-small-gguf @ b6cac96, `multilingual-e5-small-q8_0.gguf` | 132 439 008 | e011debc1208e31bf7b6aebee2d9fc8bd2ca11694a77ed66ac9d0c9d0a877c93 | OK, 384 dims, pooling MEAN, licence MIT ; avec `query: ` / `passage: ` cos 0,87 / 0,78 / 0,79 (échelle tassée, propre à e5), RSS +440 Mo |
| multilingual-e5-small (cstr) | cstr/multilingual-e5-small-GGUF @ 178420d | 131 624 960 | — | **Refusé par llama.cpp** : « bert model needs to define token type count » (conversion ancienne) |
| multilingual-e5-small (keisuke-miyako) | keisuke-miyako/multilingual-e5-small-gguf-q8_0 @ e1da944 | 131 953 504 | — | Se charge, mais ne discrimine pas (cos 0,95 / 0,94 / 0,93) : écarté |
| Qwen3-Embedding-0.6B Q8_0 | Qwen/Qwen3-Embedding-0.6B-GGUF @ 370f27d, `Qwen3-Embedding-0.6B-Q8_0.gguf` | 639 150 592 | 06507c7b42688469c4e7298b0a1e16deff06caf291cf0a5b278c308249c3e439 | OK, 1 024 dims, pooling LAST lu dans le GGUF, Apache-2.0 ; avec l'instruction de requête cos 0,77 / 0,37 / 0,41 ; RSS +1 055 Mo à `max_tokens = 2048` |
| BGE Reranker v2 M3 (référence) | gpustack/bge-reranker-v2-m3-GGUF @ 3093af0 | 438 376 864 | (déjà dans `wavestack.toml`) | OK, scores 0,998 / 0,014 / 0,005, RSS +729 Mo |
| Qwen3-Reranker-0.6B Q8_0 | ggml-org/Qwen3-Reranker-0.6B-Q8_0-GGUF @ a02f48b, `qwen3-reranker-0.6b-q8_0.gguf` | 639 153 184 | 22c9979ce4fbcdc5acdc310c6641c32797eff1aa980b8f7a2db8a8ea23429a48 | OK **à deux conditions** (voir ci-dessous) ; RSS +937 Mo |
| ms-marco-MiniLM-L6-v2 Q8_0 | toolittlecakes/ms-marco-MiniLM-L6-v2-Q8_0-GGUF @ 72e3ad8 | 25 281 216 | — | Se charge, **scores plats** même en anglais (0,50 / 0,48 / 0,49) : écarté |
| ms-marco-MiniLM-L12-v2 Q8_0 | mradermacher/ms-marco-MiniLM-L12-v2-GGUF @ 2691566 | — | — | Idem (0,48 / 0,43 / 0,45 en anglais) : écarté |

## Ce que l'essai établit

1. **Qwen3-Reranker** (`general.architecture = qwen3`, `qwen3.pooling_type = 4`, tête `cls.output`
   à partir des logits « yes » / « no ») :
   - la paire doit passer par le gabarit `tokenizer.chat_template.rerank` du GGUF (`{query}`,
     `{document}`), tokenisé avec `special=True`, en une seule séquence ; le format générique
     `[BOS] q [EOS] [SEP] d [EOS]` donne des scores sans signification (0,73 / 0,68 / 0,68) ;
   - la sortie de llama.cpp est **déjà une probabilité** (1,0 / 0,0 / 0,06 avec le gabarit) : lui
     appliquer la sigmoïde, comme pour BGE, l'écrase entre 0,5 et 0,73.
   - Les scores de deux rerankers ne se comparent donc pas : seul l'ordre compte.
2. **Cross-encoders BERT** (ms-marco MiniLM) : llama.cpp ne transmet pas les identifiants de
   segment (question / passage), dont ces modèles dépendent ; les modèles XLM-R (BGE) n'en ont
   pas besoin. Un reranker d'architecture `bert` doit être refusé avec un message dédié.
3. **Modèles d'embedding ou de reranking d'architecture LLM** (Qwen3-Embedding, Qwen3-Reranker) :
   ils ont un gabarit de conversation, donc la découverte des modèles de conversation
   (`discovery.py`, exclusion par dossier `embedding/` et `reranker/` seulement) les proposerait
   comme modèles de conversation s'ils sont ailleurs (cache HF, LM Studio, autre sous-dossier).
   Signe distinctif : la clé `{arch}.pooling_type` du GGUF, absente des modèles de conversation.
4. **Troncature silencieuse** : les chunks de l'atelier vont jusqu'à 1 500 caractères, l'embedding
   tronque à `max_tokens` (512 pour Granite et e5) sans le dire.
5. **Mémoire** : instances `Llama` indépendantes, pas de conflit entre modèles de même
   architecture ; Qwen3-Embedding et Qwen3-Reranker pèsent chacun environ 1 Go de RSS. Les prêts
   de l'atelier (`Loans`) n'ont qu'un emplacement par sorte (`embedding`, `reranker`) : un second
   modèle déclaré doit avoir le sien, sinon le budget est sous-compté.
6. Pas de GPU en jeu : les roues llama-cpp-python sont celles du CPU.

## Retenus pour 5c-1 et 5c-2

- Embeddings : Granite Embedding 107M (brique, inchangé), multilingual-e5-small (TwinSunsLLC),
  Qwen3-Embedding-0.6B (`max_tokens = 2048`, instruction de requête
  `Instruct: Given a web search query, retrieve relevant passages that answer the query\nQuery:`).
- Rerankers : BGE Reranker v2 M3 (brique, inchangé), Qwen3-Reranker-0.6B (gabarit du GGUF,
  score en probabilité).
- Écartés : MiniLM L6 et L12 (cross-encoders BERT), les deux autres GGUF d'e5-small.
  `measured_rss_mb` à remesurer sur le PC cible (valeurs ci-dessus : PC de développement).
