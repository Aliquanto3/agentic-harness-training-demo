# Existant V1 utile à la V2

Relevé du 2026-10-01 sur `main` (18c3978), lecture seule. « Manque » désigne ce que la V2 doit ajouter.

| Capacité V2 | Existe en V1 | Manque |
|---|---|---|
| CAP-1 Jeu de questions | Corpus `content/corpus/*.md` (8 documents Exemplia), traduit sous `content/i18n/{en,de}/corpus/`, déclaré dans `content/rag.yaml`. Banc hors interface `tools/bench/story12_bench.py` : 10 requêtes françaises avec un document attendu chacune (rappel@1, @3, MRR), qui a servi à choisir les modèles. | Aucun jeu dans l'application : pas de réponse attendue, pas de passage attendu, pas de sélection dans l'interface, pas de traduction. |
| CAP-2 Diagnostic, vue harnais | `RagSearchEndedPayload` et `RagRerankEndedPayload` (`trace/catalog.py`) : position, `chunk_id`, `doc_id`, score, rang d'avant, `keep`, `placement_text`. Segments typés avec leurs tokens (`context/segments.py`, `SegmentKind.rag_excerpt`), jauge et `ContextWindowPayload` (`by_brick`, sections). Recherche `SqliteVecRetriever` (`rag/retriever.py`) : cosinus, `top_k = 3` ; reranking `bge-reranker-v2-m3` avec `rerank_candidates = 8`. | Aucune notion de « bon extrait ». Le rang d'un passage au-delà des candidats renvoyés n'est pas calculé. Aucun verdict sur l'étape fautive. |
| CAP-3 Diagnostic, Atelier RAG | `/rag`, `rag/lab.py` (`LabRun`, `Pipeline`, `Stage`) : découpage, embedding, base vectorielle, recherche vectorielle, BM25, fusion RRF, reranking, contexte ; A/B avec synthèse (extraits communs, propres, écarts de rang). | Pas de bon extrait suivi d'étape en étape. L'étape contexte compte des caractères, pas des tokens. |
| CAP-4 Module | `content/scenarios.yaml` et `scenarios.py` : `program` (modules de 30 à 60 min), `transverse`, scénario avec `bricks`, `rag_rerank`, `prompts`… Un scénario s'ajoute sans code, avec ses traductions. | Le module et ses scénarios de cas d'échec. Un champ qui rattache un prompt suggéré à une question du jeu. |
| CAP-5 Coût contrefactuel | FinOps des appels cloud : `pricing = {input_usd_per_mtok, output_usd_per_mtok, checked}` par `[[cloud.models]]` dans `wavestack.toml`, source en commentaire ; `CloudPricing` (`config.py`), `CallCost` (`models/openai_chat.py`), totaux du tour et de la séance, `[finops] eur_per_usd`. GreenOps local (CodeCarbon) et cloud (EcoLogits) dans `greenops.py`. | Aucun coût pour un tour local (choix explicite de `app.js` et de la spec FinOps). La source du prix n'est qu'un commentaire TOML, pas une donnée affichable. |
| CAP-6 Test préalable | Modèle de banc : `tools/bench/story12_bench.py` (Headroom, embedding, reranking), avec processus enfant propre, garde réseau, dépendances par `uv run --with`, verdict consigné dans le « Deferred » de `ARCHITECTURE-SPINE.md`. | Aucun routeur, classifieur, NLI ni encodeur zero-shot dans le code. La seule exécution ONNX est fastembed, en option de l'Atelier RAG. |
| CAP-7, CAP-8 Routage | — | Tout. |
| CAP-9 Bascule annoncée | `LoadRegistry` (`models/load_registry.py`) : un seul créneau génératif, créneaux `EMBEDDING`, `RERANKER`, `COMPRESSOR`… ; `AppSession.switch_model` libère, charge, restaure en cas d'échec ; messages `session.load.*`. | Aucun message n'annonce la durée d'une bascule avant qu'elle commence. |
| CAP-10 Multi-agent | Un sous-agent (`subagent.py`, méta-outil `delegate`, même modèle, contexte séparé, `max_calls = 4`). | Plusieurs agents qui échangent. |
| CAP-11 Documents propres | Construction d'index (`scripts/build_rag_index.py`, bouton « Construire l'index »), un index par langue. | Import de documents du participant, index séparé de celui du dépôt, questions de contrôle écrites par lui. |
| CAP-12 Format chat local | Adaptateur `openai_chat` (Groq, Mistral, Gemini, Gemma) ; le pointer vers un serveur local est possible, non visé (ARCHITECTURE-SPINE, Deferred). | Prise en charge visée et testée d'un serveur local au format chat. |

## Contrat V1 déjà aligné sur la forge

- NFR-2 dit « jamais deux modèles génératifs » ; les non génératifs coexistent dans le budget.
- NFR-10, NFR-11 et CAP-37 disent « dépôt privé ».
- Correct course du 2026-09-25 (`sprint-change-proposal-2026-09-25-depot-prive.md`), appliqué. La section « À corriger dans la V1 » de la forge est close.
