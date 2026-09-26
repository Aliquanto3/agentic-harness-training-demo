---
title: 'Reranking'
type: 'feature'
created: '2026-09-26'
status: 'done'
baseline_revision: '58b430683ac35bb7395edf98a833805586d4c429'
review_loop_iteration: 0
followup_review_recommended: false
context:
  - '{project-root}/_bmad-output/planning-artifacts/architecture/architecture-agentic-harness-training-demo-2026-09-23/ARCHITECTURE-SPINE.md'
  - '{project-root}/_bmad-output/specs/spec-agentic-harness-training-demo/stories/15-corpus-de-demonstration-et-rag-simple.md'
warnings: ['oversized']
deferred:
  - summary: >-
      Le vrai reranker (bge-reranker-v2-m3 Q4_K_M) n'a jamais tourné : latence de l'étape, mémoire ajoutée, pertinence et pooling déclaré dans le GGUF de gpustack restent à mesurer.
    evidence: |-
      Aucun modèle téléchargeable ici (huggingface.co bloqué). L'adaptateur est exercé dans la suite par défaut sur des GGUF BERT synthétiques (tests/fixtures/tiny-bert-rank.gguf et tiny-bert-cls.gguf : paire, score, troncature, progression, refus d'un GGUF d'embedding). À trancher sur le PC cible : `uv run python -m pytest -m model tests/test_rag_rerank.py`, puis le scénario « RAG avec reranking » (RSS ajouté ≤ 800 Mo, seuil de la story 12, NFR-2 ; durée de l'étape « Reranking », NFR-1 < 30 s au premier token). Reporté dans deferred-work.md.
    location: >-
      src/wavestack/models/reranker.py:LlamaCppReranker
    severity: medium (unverified)
  - summary: >-
      L'URL du reranker vise resolve/main et son sha256 n'est pas renseigné.
    evidence: |-
      Le connecteur Hugging Face donne la taille (438 376 864 octets) mais ni l'oid LFS ni le commit. Le premier téléchargement sur le PC cible trace le sha256 (effet model_download) : le recopier dans [rag.reranker] files[].sha256 et épingler l'URL sur le commit.
    location: >-
      wavestack.toml:[rag.reranker]
    severity: medium
  - summary: >-
      AD-21 amendé dans le spine, « à valider » : sans son modèle, seule la sous-option « Reranking » est indisponible, le RAG simple continue.
    evidence: |-
      Revue indépendante (intent). Décision attendue d'Anaël au test manuel ; défaut : garder la sous-option seule indisponible (hypothèse 1). Reporté dans deferred-work.md.
    location: >-
      ARCHITECTURE-SPINE.md:AD-21
    severity: medium
  - summary: >-
      Le parcours E2E ne joue ni l'échec d'un téléchargement du reranker ni une étape « Reranking » en erreur.
    evidence: |-
      Couverts par pytest ; l'affichage n'est vérifié qu'à la lecture du code. Reporté dans deferred-work.md.
    location: >-
      tools/e2e/run_e2e.py:s_rag_rerank
    severity: low
---

<intent-contract>

## Intent

**Problem:** La brique RAG de la story 15 place les `top_k` extraits les plus proches par embedding, sans deuxième passe : WaveStack ne peut pas montrer ce qu'un reranker change à l'ordre des extraits (CAP-19, FR-18, UJ-5 « l'ordre des extraits change, visible avant/après »).

**Approach:** Une sous-option « Reranking » de la brique RAG (case sur sa carte, comme « Lazy loading » pour MCP). Activée et disponible, la recherche retient `[rag] rerank_candidates` candidats, puis une étape « Reranking » du rail les fait noter par le reranker local (bge-reranker-v2-m3 Q4_K_M, verdict provisoire de la story 12, llama-cpp-python en pooling `RANK`) et montre l'ordre avant et après ; seuls les `top_k` premiers après reranking entrent dans le contexte. Le modèle passe par le registre de chargement (emplacement `reranker`), le téléchargement « Télécharger » et les contrôles d'identité de la story 15.

## Boundaries & Constraints

**Always:**
- **Point d'injection du verdict** : une section `[rag.reranker]` de `wavestack.toml`, seul endroit qui nomme le reranker (`id`, `backend = "llama_cpp"`, `label_fr`, `license`, `max_tokens`, `load_path`, `measured_rss_mb` facultatif, `files`), validée par un modèle strict comme `EmbeddingModel` ; `[rag] rerank_candidates` (8 par défaut, jamais moins que `top_k`, 20 au plus). Section absente ou invalide : sous-option indisponible avec la raison, jamais de plantage.
- **Adaptateur** (`models/reranker.py`) : port `Reranker{model_id, score(query, passages, cancelled) → list[float], close()}`, scores dans [0, 1] (sigmoïde de la sortie brute). `LlamaCppReranker` ouvre `Llama(embedding=True, pooling_type=RANK, n_ctx = n_batch = n_ubatch = max_tokens)`, forme la paire `[BOS] q [EOS] [SEP] d [EOS]` (drapeaux du vocabulaire, comme `format_rerank` de llama-server), tronque le passage pour tenir dans `max_tokens`, lit le score par `llama_get_embeddings_seq(ctx, 0)[0]` après un `decode` par paire (jamais `Llama.embed()`), et sonde une paire au chargement (score fini, sinon `ValueError` en français). `llama_cpp` importé paresseusement.
- **Sous-option** : état de session `_rag_rerank` (faux au lancement, remis à faux par la réinitialisation), intention de classe (a) `POST /api/intentions/rag_rerank {enabled}`, effet au tour suivant (« Prend effet au prochain tour » sur la carte RAG), champ `rag_rerank` des scénarios.
- **Disponibilité de la sous-option**, calculée par la session, dans cet ordre : section invalide ; fichiers absents (« modèle absent », offre `download_model{target: "rag_reranker"}`, chemin de copie manuelle) ; chargement en cours ; refus chiffré du registre ou échec du chargement. La brique RAG reste disponible quand seule la sous-option ne l'est pas : le tour cherche alors sans reranking, sans étape « Reranking ».
- **Chargement** (AD-8) : sur le fil de travail, quand la brique RAG est voulue, sans raison statique d'indisponibilité, son embedding chargé, et la sous-option activée avec ses fichiers présents ; libéré (`close()`, emplacement `reranker` rendu) sinon, et à `close()`. Coût : `measured_rss_mb`, sinon taille des fichiers plus `[memory] load_margin_mb`. sha256 déclaré vérifié au chargement.
- **Tour** : l'état figé porte `rag_rerank` (sous-option activée et reranker chargé au départ du tour). La recherche retient alors `rerank_candidates` candidats (son `top_k` d'événement vaut ce nombre ; son `placement_fr` dit qu'aucun n'entre directement). Puis une étape `{turn}.main.s{n+1}`, brique `rag`, composant `rag.reranker`, acteur et déclencheur `harness`, émet `rag_rerank_started{query, candidates, keep, phase_label}` et `rag_rerank_ended{status: ok|error, excerpts, keep, placement_fr, error_fr, duration_ms}`. `excerpts` liste tous les candidats dans l'ordre du reranker, chacun avec `position` (rang après), `before` (rang avant), `score` (reranker, 3 décimales) et `retrieval_score` (embedding). Tri stable : score décroissant, puis rang avant.
- **Contexte** : les `keep` = `top_k` premiers après reranking, renumérotés 1..k dans le nouvel ordre, au format de la story 15 (intro puis extraits, segments `rag_excerpt`, brique `rag`). Échec du reranker : `harness_error`, `rag_rerank_ended{status: error}`, et le tour continue avec les `top_k` premiers de l'ordre de l'embedding. « Arrêter » est testé entre deux paires.
- **Schéma** (AD-12) : composant `rag.reranker` (`local_process`, arête vers `core.harness`) dessiné tant que la sous-option est activée et la brique voulue ; puce « Reranking » avec l'infobulle « Modèle de reranking {id}, processus local », indisponible avec la raison de la sous-option ; allumé pendant l'étape.
- **Front** (AD-1, mise en forme seule) : sur la carte RAG, la case « Reranking », son étiquette « Local », sa raison et son bouton « Télécharger le modèle de reranking (≈ {taille} Mo) » ; au rail, la ligne « Reranking » (« {k} gardés sur {n} · {durée} », ou « erreur »), dépliée en deux listes « Avant (embedding) » et « Après (reranker) », rang, mouvement, document, scores, gardé ou écarté ; un clic sélectionne `rag.reranker` ; journal : un résumé d'une ligne par `kind`.
- **Scénario** : `rag_rerank` dans le module « RAG » (après `rag`), mêmes briques que `rag`, `rag_rerank: true`.
- **Discovery** : les fichiers de `[rag.reranker]` et le dossier `models/reranker/` ne sont jamais proposés comme modèle de conversation.
- Textes en français sous `content/` (sauf messages chiffrés composés en Python) ; code en anglais ; `uv`, `ruff`, `pytest` ; aucun test ne touche au réseau ; faux reranker déterministe pour les tests et l'E2E.

**Never:** nouvelle dépendance (fastembed reste un repli non adopté) ; nouveau `SegmentKind` ; reranking dans le contexte d'un sous-agent ; seuil de score ; compression (story 20) ; modification de `stories.yaml` ou d'une autre story ; identifiant du reranker ailleurs que dans `[rag.reranker]`.

## I/O & Edge-Case Matrix

| Scénario | Entrée / état | Comportement attendu | Erreur |
|---|---|---|---|
| Reranking actif | RAG effective, sous-option activée, reranker chargé | étape « Recherche RAG » (8 candidats), étape « Reranking » (8 extraits, `before`), contexte : intro + 3 extraits dans l'ordre du reranker | — |
| Sous-option éteinte | RAG effective | comportement de la story 15, aucune étape « Reranking », reranker libéré | — |
| Modèle absent | fichiers du reranker manquants | sous-option indisponible « modèle absent », `download` proposé ; le tour cherche sans reranking | — |
| Budget dépassé | mesure + coût > budget | sous-option indisponible, raison chiffrée ; RAG disponible | — |
| Reranker en échec | `score` lève | `harness_error`, `rag_rerank_ended{error}`, contexte : 3 premiers de l'embedding | AD-16 |
| Téléchargement | `download_model{rag_reranker}` | progression « modèle de reranking », fichier vérifié, reranker chargé si voulu | échec : `.part` supprimé, `harness_error` |
| Réinitialisation | après un scénario `rag_rerank` | sous-option éteinte, reranker fermé, registre libéré | — |

</intent-contract>

## Code Map

- `wavestack.toml` : `[rag]` (ajouter `rerank_candidates`) et nouvelle section `[rag.reranker]` après `[rag.embedding]`. Verdict (story 12, L212) : `gpustack/bge-reranker-v2-m3-GGUF`, `bge-reranker-v2-m3-Q4_K_M.gguf`, 438 376 864 octets (taille reconfirmée par le connecteur HF), Apache-2.0, pooling RANK.
- `src/wavestack/config.py` : `EmbeddingFile`, `_relative_path`, `EmbeddingModel` (L162-229) comme modèle de `RerankerModel` ; accesseurs `rag_embedding` (L346-365), `rag_top_k` (L367) → `rag_reranker`, `rag_rerank_candidates`.
- `src/wavestack/models/embedding.py` : style de l'adaptateur et de la sonde. `tools/bench/story12_bench.py:1007-1073` : `_decode_sequence`, `_llama_scores_rerank` (paire, drapeaux, lecture du score) à reprendre.
- `src/wavestack/models/load_registry.py` : `EMBEDDING`, `embedding_cost`, `check_component`, `grant`, `release` → emplacement `RERANKER`.
- `src/wavestack/models/download.py` : `missing_files`, `download_files` réutilisés tels quels.
- `src/wavestack/models/discovery.py:50-60,195-200` : exclure aussi `[rag.reranker]` et `models/reranker/`.
- `src/wavestack/rag/retriever.py` : `SqliteVecRetriever.search(query)` → paramètre `k` facultatif ; `Excerpt`.
- `src/wavestack/rag/corpus.py` : `RagContent` (strict) → textes du reranking.
- `src/wavestack/bricks/registry.py:193-206` : composant `rag.reranker` de la brique `rag`.
- `src/wavestack/trace/catalog.py` : `DownloadOffer.target` (L279), `BrickState` (L292) → champ `rerank` ; paires `rag_search_*` (L583-606) comme modèle ; `PAYLOAD_MODELS`.
- `src/wavestack/session/app_session.py` :
  - `TurnState` (L298) : `rag_rerank: bool = False` ;
  - `__init__` (L418-570) : `reranker_factory`, état du reranker ; `_apply_launch_config` (L571) : `_rag_rerank = False` ;
  - `_drawn_components` (L637), `_emit_architecture` (L694-826 : libellé, `detail_fr`, disponibilité du nœud) ;
  - `_pending_ids` (L828) : un `_sent_rerank` à part, sans toucher au tuple `_sent` (story 20 en parallèle) ;
  - `_emit_bricks` (L953) → `rerank` sur la carte RAG ;
  - `_load_rag` (L1545), `_rag_refresh` (L1574), `_request_rag_sync` (L1733), `_sync_rag` (L1758), `_load_embedder`/`_close_embedder` (L1787-1853) : fichiers, chargement et libération du reranker ;
  - `build_turn_state` (L2008), `_start` (L2483 : `_sent_rerank`), `set_mcp_mode` (L2715) comme modèle de `set_rag_rerank` ;
  - `launch_scenario`/`_reconfigure` (L3530-3585), `close` (L1023) ;
  - `download_model`, `_download_fr`, `_run_download` (L3614-3737) : cible `rag_reranker` ;
  - `_turn` (L3968-3973), `_rag_search` (L4110) : candidats, puis `_rag_rerank`.
- `src/wavestack/web/app.py` : `McpModeIntention`/`mcp_mode` (L70, L424) comme modèle de la route `rag_rerank`.
- `src/wavestack/web/static/app.js` : `applyEnvelope` (L370-381), `renderBricks`/`downloadParts` (L837, L914-967), `setOption` (L1345), `turnRows` (L3047-3062), `ragBody` (L2711), `EVENT_LABELS`/`eventSummary` (L3952, L4033), `BRICK_ICONS` (L4184, puces L4408), `schemaActivity` (L4305-4314) ; `app.css` (L2969-3000).
- `content/rag.yaml`, `content/bricks/rag.yaml`, `content/scenarios.yaml` (module « RAG » L32-34, scénario `rag` L222-240), `src/wavestack/scenarios.py:17-29`.
- Tests : `tests/fake_embedder.py`, `tests/test_rag.py` (`rag_values`, `rag_session`, `Embedders`, `card`, `turn_events`), `tests/test_rag_download.py` (MockTransport), `tests/test_scenarios.py`, `tests/test_bricks.py`.
- E2E : `tools/e2e/wavestack_e2e.py` (faux embedder), `stack.py:63-83` (`rag_settings`), `fake_openai.py:420-437` (fichier servi), `run_e2e.py:1218-1420` (`s_rag`), `SCENARIOS` L1870, `README.md`.
- GGUF synthétique de reranker (story 12, aléatoire) dans le scratchpad : sert à exercer l'adaptateur, pas à le qualifier.

## Tasks & Acceptance

**Execution:**
- [x] `wavestack.toml`, `src/wavestack/config.py` -- `[rag] rerank_candidates`, `[rag.reranker]`, `RerankerModel`, accesseurs -- point d'injection unique du verdict.
- [x] `src/wavestack/models/reranker.py` (nouveau) -- port, `LlamaCppReranker`, `open_reranker`, `sigmoid`, `pair_tokens` -- adaptateur du verdict.
- [x] `src/wavestack/models/load_registry.py`, `models/discovery.py` -- emplacement `reranker` ; exclusion des fichiers du reranker.
- [x] `src/wavestack/rag/retriever.py`, `rag/corpus.py`, `content/rag.yaml`, `content/bricks/rag.yaml` -- `k` de recherche ; textes du reranking.
- [x] `src/wavestack/bricks/registry.py`, `trace/catalog.py`, `session/app_session.py`, `web/app.py`, `scenarios.py` -- composant, événements, carte, disponibilité, chargement, tour, téléchargement, route, scénario.
- [x] `src/wavestack/web/static/app.js`, `app.css` -- case et bouton sur la carte, étape du rail avant/après, schéma, journal.
- [x] `content/scenarios.yaml` -- scénario `rag_rerank` dans le module « RAG ».
- [x] `tests/fake_reranker.py`, `tests/test_rag_rerank.py` (nouveaux) -- une ligne de la matrice par test, plus pairage, sigmoïde, config, route, discovery, test `model` sur le vrai GGUF (sauté s'il est absent).
- [x] `tools/e2e/` et `README.md` -- faux reranker au lanceur, fichier servi, scénario E2E `rag_rerank` (modèle absent, téléchargement, étape avant/après, contexte, schéma, désactivation), capture, documentation.

**Acceptance Criteria:**
- Given un tour avec reranking effectif, when la page est rechargée, then le rail montre toujours « Recherche RAG » puis « Reranking », avec l'ordre avant et après (projection du journal, AD-1).
- Given la sous-option activée puis désactivée, when le fil de travail a traité les deux intentions, then le reranker a été chargé une fois puis fermé, et le registre ne compte plus l'emplacement `reranker`.
- Given la sous-option changée depuis le dernier tour, when on lit `/api/state`, then la carte RAG porte `pending: true`.
- Given le scénario `rag_rerank` lancé, when on lit `/api/state`, then les briques sont celles du scénario `rag` et `rerank.enabled` est vrai.
- Given `uv lock --check --offline`, `ruff check`, `ruff format --check`, `pytest`, `node --check` et l'E2E complet, when ils s'exécutent sans réseau externe, then tout passe.

## Spec Change Log

## Review Triage Log

### 2026-09-26 — Review pass
Revue faite par l'agent d'implémentation lui-même, sans sous-agent (aucun outil de sous-agent dans cette exécution, sur instruction de l'appelant), sous les quatre angles du workflow (lecture à froid du diff, cas limites, trous de vérification, alignement sur l'intention) ; une revue indépendante suivra.
- verdicts: 7 findings — high 0, medium 1, low 5, false 0, maybe-false 1
- findings:
  - `[low]` `[patch]` Un index remplacé pendant la séance libérait l'embedder mais laissait le reranker chargé (mémoire gardée jusqu'à la reconfiguration suivante). — Corrigé : `_rag_current_retriever` libère aussi le reranker.
  - `[low]` `[patch]` Un refus (409) de « Télécharger le modèle de reranking » n'était affiché nulle part quand la carte RAG n'offrait pas d'autre action. — Corrigé : `rerankParts` affiche `store.downloadError` dans ce cas.
  - `[maybe-false]` `[defer]` Le vrai GGUF (pooling déclaré, scores, latence, mémoire) n'a pas tourné. — À trancher par le test `model` et le scénario sur le PC cible (frontmatter `deferred`).
  - `[medium]` `[defer]` URL sur resolve/main, sha256 vide. — Même limite que la story 15 : le connecteur HF ne donne ni oid ni commit ; relevé au premier téléchargement.
  - `[low]` `[defer]` Refus d'un GGUF non RANK non testé automatiquement. — Nécessiterait la dépendance gguf ; vérifié à la main.
  - `[low]` `[reject]` Le tri se fait sur le score arrondi à 3 décimales, puis sur le rang avant : deux scores très proches gardent l'ordre de l'embedding. — Voulu : l'ordre affiché correspond aux scores affichés.
  - `[low]` `[reject]` Pendant un chargement, deux synchronisations successives pouvaient émettre deux fois le refus de budget du reranker. — Corrigé pendant l'implémentation (un refus attend une nouvelle demande, test `test_a_budget_refusal_*`) ; la même course existe pour l'embedding (story 15), non touchée ici.

### 2026-09-26 — Revue indépendante (4 relecteurs séparés), triage du coordinateur

Tous les points ont été vérifiés dans le code puis appliqués ; aucun n'a été jugé faux. Le troisième report de la première passe (refus d'un GGUF non RANK sans test) est levé : il est testé sur un GGUF synthétique.
- `[medium]` `[patch]` Intent : AD-21 contredit par la sous-option seule indisponible. — Garde de C1 ; AD-21 amendé dans le spine, marqué « à valider » ; report dans deferred-work.md.
- `[medium]` `[patch]` Tour lancé pendant le chargement du reranker : reranking ignoré sans le dire. — `TurnState.rag_rerank_skipped_fr`, porté par `rag_search_ended.rerank_skipped_fr` et affiché dans l'étape « Recherche RAG » ; `_sent_rerank` vaut ce qui a tourné (la case reste « Prend effet au prochain tour » pendant le chargement). Tests `test_the_reason_is_said_*`, `test_a_missing_reranker_*`.
- `[medium]` `[patch]` E2E : aucun prompt du scénario joué. — La question sur l'hôtel à Paris devient le premier prompt de `rag_rerank` ; le parcours vérifie qu'il la joue et que la consigne est chiffrée.
- `[medium]` `[defer]` Coût mémoire et latence du vrai reranker. — deferred-work.md (seuil 800 Mo, NFR-1, NFR-2).
- `[low]` `[patch]` Tests manquants (verification-gap) : index remplacé avec reranker chargé, refus de budget puis changement de modèle, nœud du schéma indisponible avec sa raison, `load_path` hors de `reranker/`, adaptateur sur GGUF synthétique. — Tests `test_an_index_replaced_with_the_reranker_*`, `test_a_reranker_refused_by_the_budget_loads_*`, `test_the_schema_node_says_*`, `test_the_reranker_file_outside_its_folder_*`, `test_the_adapter_scores_pairs_*`, `test_the_adapter_refuses_an_embedding_gguf` ; fixtures `tests/fixtures/tiny-bert-rank.gguf` et `tiny-bert-cls.gguf` (`make_tiny_rerank_gguf.py`).
- `[low]` `[defer]` E2E : notice d'échec de téléchargement et étape en erreur. — Couverts par pytest ; deferred-work.md.
- `[medium]` `[patch]` Adaptateur : `LLAMA_TOKEN_NULL` pris pour un vrai jeton, binding absent pris pour « ajouté ». — `special_tokens` : `None` dans les deux cas.
- `[low]` `[patch]` Tests : fabrique qui lève, sha256 déclaré faux, route 404 sans brique RAG, sous-agent jamais reranké, règle de la moitié. — Tests `test_a_factory_that_raises_*`, `test_a_declared_sha256_*`, `test_the_rag_rerank_route_is_404_*`, `test_the_sub_agent_context_is_never_reranked`, `test_the_query_keeps_at_least_half_*`.
- `[low]` `[patch]` `pair_tokens` : la question ne récupérait pas la place laissée par un extrait court ; troncature muette. — La question garde au moins la moitié et prend le reste laissé par l'extrait ; `RerankScore.truncated`, `rag_rerank_ended.excerpts[].truncated`, « coupé » dans l'étape.
- `[low]` `[patch]` Progression du reranking invisible. — `progress` du port, événement `rag_rerank_progress{done, total}`, « 3 / 8 » dans l'étape en cours et au journal.
- `[low]` `[patch]` Pluriels en dur. — `plural()` et « Seul le premier… ».
- `[low]` `[patch]` « 8 » et « 3 » en dur dans la carte et le scénario. — `{candidates}` et `{keep}`, remplis par la session (`_fill`) depuis `[rag]`.
- `[low]` `[patch]` Colonne « Avant » : gardé/écarté seulement en infobulle ; CSS `.rerank-column`, `.rerank-note` absentes. — Libellés visibles, CSS ajoutées.
- `[low]` `[patch]` `store.rerankNotice` montré seulement avec « Télécharger ». — Montré tant que la sous-option est indisponible (échec de chargement, sha256).
- `[low]` `[patch]` Doublons `EmbeddingModel`/`RerankerModel`, noms propres à l'embedding. — `LocalModelSpec` et `ModelFile` dans `config.py`, `component_cost`, `_rag_model_files`, `_missing_model_fr` pour les deux modèles.
- `[low]` `[patch]` Accès disque à chaque émission (raison « modèle absent »). — Raisons calculées à la relecture des fichiers (`_rag_refresh`, `_rerank_refresh`) et mémorisées.
- `[low]` `[patch]` Journal : `rag_rerank_ended` répétait les textes. — Référence par `chunk_id` ; le front reprend le texte de l'étape de recherche.
- `[low]` `[patch]` Fichier de story : triage et front matter à mettre en cohérence. — Ce passage.
- `[low]` `[patch]` README : bornes, réglage de lenteur, coût mémoire, verdict provisoire. — Section « Reranking » réécrite.
- `[low]` `[patch]` Edge : score non numérique hors du `try`. — Conversion et contrôle dans le `try` : repli sur l'ordre d'embedding, `rag_rerank_ended{error}` toujours émis. Test `test_scores_that_are_not_figures_*`.
- `[low]` `[patch]` Edge : `_request_rag_sync` demandait le reranker sans l'embedder. — Même condition que `_sync_reranker` (embedder chargé ou en cours).
- `[low]` `[patch]` Edge : embedder non chargé, sous-option dite disponible. — Raison « Indisponible tant que la brique RAG l'est… ». Test `test_the_reranker_waits_for_the_embedding_model`.
- `[low]` `[patch]` Edge : `top_k` > 20. — `rag_top_k` borné à 20, candidats jamais au-delà.
- `[low]` `[patch]` Edge : `_rerank_missing` non calculé si `[rag.embedding]` est invalide. — `_rerank_refresh` avant tout retour anticipé de `_load_rag`.
- `[low]` `[patch]` Edge : lectures du vocabulaire hors du `try`. — Dans le `try`, `close()` en cas d'échec.
- `[low]` `[patch]` Edge : dossiers `embedding/`, `reranker/` comparés à la casse près (Windows). — `casefold` et `os.path.normcase`.
- `[low]` `[patch]` Edge : « Arrêter » affiché en erreur rouge. — Statut `cancelled`, étape « arrêté », ton neutre.

Constat hors story pendant le parcours E2E complet : `local_server` puis `relaunch` échouaient une fois sur deux, aussi sur le commit d'intégration d'avant la revue (2 échecs sur 3). Cause : `/api/stream` et `/api/diagnostic/stream` s'abonnaient au journal après avoir envoyé tout l'historique ; un événement émis pendant ce rejeu (5,7 Mo à ce stade du parcours) était perdu, ici le `model_load_ended` d'un « Choisir » cliqué dès l'ouverture du diagnostic. Corrigé dans `web/app.py:_sse_stream` (abonnement avant la lecture de l'historique, doublons écartés par `seq`) ; test `test_an_event_emitted_during_the_replay_is_never_lost_nor_repeated` (il échoue sur l'ancien code). Deux parcours complets verts ensuite.

## Design Notes

**Pourquoi une étape distincte.** EXPERIENCE.md range « recherche RAG, reranking » comme deux étapes dépliables d'Orchestration : la première montre ce que l'embedding trouve (8 candidats), la seconde ce que le reranker en fait. Le lecteur voit ainsi qu'un extrait classé 5ᵉ par l'embedding peut entrer dans le contexte et qu'un 2ᵉ peut en sortir.

**Scores.** bge-reranker renvoie un logit (souvent entre −10 et +10). La sigmoïde (comme `normalize=True` de FlagEmbedding) le ramène dans [0, 1], lisible à côté du score de l'embedding ; les deux ne sont pas comparables entre eux, ce que dit l'explication de la brique.

**Paire** (verdict de la story 12) :

```python
tokens = [bos]*add_bos + q + [eos]*add_eos + [sep]*add_sep + d + [eos]*add_eos
# d tronqué pour que len(tokens) <= max_tokens
```

## Hypothèses à valider

1. **Sous-option indisponible, brique disponible.** AD-21 dit « une brique RAG activée sans ses modèles d'embedding ou de reranking est indisponible ». Le reranking étant une sous-option (EXPERIENCE.md, `brick-card`), seule la sous-option devient indisponible quand le reranker manque ; le RAG simple continue. C'est la lecture qui ne prive pas le module de son RAG pour un modèle facultatif.
2. **Pooling forcé.** Suivant le verdict de la story 12, l'adaptateur force `pooling_type=RANK` (l'embedding lit le sien dans le GGUF). Le fichier est identifié par sa taille (et son sha256 s'il est déclaré) avant tout chargement.
3. **Candidats.** `rerank_candidates = 8` : assez pour que l'ordre change, borné pour NFR-1 (une passe du reranker par candidat, ~0,3 à 1 s chacune sur CPU, à mesurer sur le PC cible).
4. **sha256 et révision.** Le connecteur HF donne la taille (438 376 864) mais ni sha256 ni commit : URL sur `resolve/main`, sha256 vide, tracé au premier téléchargement (comme la story 15).
5. **Module « RAG ».** Le scénario `rag_rerank` suit `rag` dans le même module (PRD : « RAG (simple, puis reranking) »), dont la durée passe de 30 à 45 min.

Ajoutées pendant l'implémentation (exécution sans humain, 2026-09-26) :

6. **Pooling vérifié dans les métadonnées.** Charger un GGUF d'embedding en pooling RANK réussit et note n'importe quoi (vu sur le GGUF synthétique de la story 12). L'adaptateur force RANK comme le verdict, mais refuse, en français, un fichier dont les métadonnées déclarent un autre pooling ; un GGUF sans pooling déclaré est accepté.
7. **Passage noté.** Le reranker lit « titre du document + texte », comme l'index embarque les passages (story 15).
8. **Troncature de la paire.** La question garde au plus la moitié des `max_tokens` (1 024) ; l'extrait est coupé au-delà.
9. **Arrêt.** « Arrêter » pendant le reranking termine l'étape en « Reranking arrêté. », sans `harness_error`, et le tour est annulé.
10. **Second prompt du scénario.** « Que faut-il faire en premier quand on perd son ordinateur portable chez Exemplia ? » (document « Incidents de sécurité »). Le parcours E2E utilise la question de l'hôtel à Paris, que le faux reranker réordonne nettement.
11. **Pas de trace réseau en boucle locale.** Le téléchargement du faux reranker (E2E, 127.0.0.1) n'émet pas `outbound_request`, comme celui de l'embedding ; le test pytest vérifie la trace vers huggingface.co.

Ajoutées après la revue indépendante (2026-09-26) :

12. **Reranking non appliqué.** Sous-option cochée mais reranker absent, refusé ou en cours de chargement au départ du tour : l'étape « Recherche RAG » le dit, avec la raison. Pendant un chargement, la carte garde « Prend effet au prochain tour » ; sinon, la raison de la sous-option suffit.
13. **Paire.** La question garde au moins la moitié des `max_tokens`, et prend la place qu'un extrait court laisse ; un extrait coupé est marqué « coupé » dans l'étape.
14. **Jetons spéciaux.** BOS, EOS et SEP ne sont ajoutés que si le vocabulaire le dit et que le jeton existe ; sans binding pour le savoir, ils sont omis (jamais supposés).
15. **Bornes.** `[rag] top_k` va de 1 à 20, `[rag] rerank_candidates` de `top_k` à 20.
16. **Textes chiffrés.** La carte et le scénario disent `{candidates}` et `{keep}`, remplis depuis `[rag]` à l'émission.

## Verification

**Commands:**
- `uv lock --check --offline` -- expected: à jour.
- `uv run ruff check .` et `uv run ruff format --check .` -- expected: aucune erreur.
- `uv run python -m pytest -q` -- expected: tout passe, sans réseau.
- `node --check src/wavestack/web/static/app.js` -- expected: aucune erreur.
- `uv run --with playwright==1.56.0 python tools/e2e/run_e2e.py` -- expected: 0 échec.

**Manual checks (if no CLI):**
- Sur le PC cible, scénario « RAG avec reranking » : « Télécharger le modèle de reranking », puis une question ; l'étape « Reranking » montre un ordre qui change, la latence reste sous 30 s (NFR-1), la mémoire sous le budget.

## Auto Run Result

Status: done
Blocking condition: aucune.

**Résumé.** Sous-option « Reranking » de la brique RAG : case sur la carte RAG (intention `rag_rerank`, classe a, « Prend effet au prochain tour »), modèle nommé dans la seule section `[rag.reranker]` (bge-reranker-v2-m3 Q4_K_M, verdict provisoire de la story 12), adaptateur llama.cpp en pooling RANK (paire `[BOS] q [EOS] [SEP] d [EOS]`, score lu par `llama_get_embeddings_seq`, sigmoïde), emplacement `reranker` du registre (refus chiffré), « Télécharger le modèle de reranking » (même code que l'embedding, cible `rag_reranker`). Activée et disponible : la recherche retient 8 candidats, l'étape « Reranking » (paire `rag_rerank_started/ended`) les note et trace l'ordre avant et après, et seuls les 3 premiers entrent dans le message. Modèle absent, budget refusé ou reranker en échec : la sous-option seule est indisponible, le RAG continue. Scénario `rag_rerank` dans le module « RAG » (45 min).

**Fichiers.**
- `wavestack.toml`, `src/wavestack/config.py` : `[rag] rerank_candidates`, `[rag.reranker]`, `RerankerModel`, `rag_reranker`, `rag_rerank_candidates`.
- `src/wavestack/models/reranker.py` (nouveau) : port `Reranker`, `LlamaCppReranker`, `pair_tokens`, `sigmoid`, `open_reranker`.
- `src/wavestack/models/load_registry.py`, `models/discovery.py` : emplacement `reranker` ; `models/reranker/` jamais proposé comme modèle de conversation.
- `src/wavestack/rag/retriever.py`, `rag/corpus.py`, `content/rag.yaml`, `content/bricks/rag.yaml` : `k` de recherche, textes de la sous-option, explication de la brique.
- `src/wavestack/bricks/registry.py`, `trace/catalog.py`, `session/app_session.py`, `web/app.py`, `scenarios.py` : composant `rag.reranker`, `RerankOption`, événements, disponibilité, chargement, tour, téléchargement, route, champ de scénario.
- `src/wavestack/web/static/app.js`, `app.css` : case et bouton sur la carte, ligne « ↕️ Reranking » du rail (avant/après, gardés/écartés), puce du schéma, journal.
- `content/scenarios.yaml` : scénario `rag_rerank`.
- `tests/fake_reranker.py`, `tests/test_rag_rerank.py` (nouveaux), `tests/test_scenarios.py` (16 scénarios).
- `tools/e2e/` : faux reranker au lanceur, fichier servi, `rag_settings`, scénario `rag_rerank`, README, capture `25-reranking-avant-apres.jpg` ; `README.md` : section « Reranking ».

**Revue.** 2 corrections (low), 3 reports (dont 1 medium non vérifiable ici), 2 rejets motivés (Review Triage Log). Relecture de suivi recommandée : non selon la règle (aucune correction medium ou high) ; une revue indépendante est prévue par l'appelant.

**Vérifications.**
- `uv lock --check --offline` : OK ; `uv run ruff check .`, `uv run ruff format --check .` : OK ; `node --check src/wavestack/web/static/app.js` : OK.
- `uv run python -m pytest -q` : 673 réussis, 4 sautés, 4 désélectionnés (`model`).
- `uv run --with playwright==1.56.0 python tools/e2e/run_e2e.py` : 286 vérifications réussies, 0 échec (dont 19 pour `rag_rerank`).
- Adaptateur exercé sur les GGUF synthétiques de la story 12 : chargement en RANK, drapeaux du vocabulaire, trois paires notées, texte long tronqué, GGUF d'embedding refusé en français.

**Risques résiduels.** Voir `deferred` : le vrai reranker sur le PC cible (latence de 8 passes sur CPU, mémoire, pertinence), sha256 et révision à épingler.

**Revue indépendante (2026-09-26).** Tous les points appliqués (voir « Review Triage Log »), aucun jugé faux ; reports dans deferred-work.md (mémoire et latence du vrai reranker, sha256, AD-21 à valider, deux cas E2E, prompt réordonné avec le vrai modèle). AD-21 amendé dans le spine, marqué « à valider ». Vérifications après correctifs : `uv lock --check --offline`, `ruff check`, `ruff format --check`, `node --check` : OK ; `pytest -q` complet : 751 réussis, 4 sautés ; E2E complet : 312 vérifications réussies, 0 échec (deux parcours de suite), après le correctif du flux SSE ci-dessus.
