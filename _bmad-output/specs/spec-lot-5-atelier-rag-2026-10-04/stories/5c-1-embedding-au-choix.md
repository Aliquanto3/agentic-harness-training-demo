---
title: 'Lot 5c-1 : embedding au choix (Granite, e5-small, Qwen3-Embedding, fastembed) et retrait de la voie B'
type: 'feature'
created: '2026-10-05'
status: 'done'
route: 'dispatch'
review_loop_iteration: 0
baseline_commit: 'f37aa72b904e176fd14fde5eee7417a33810177f'
context:
  - '{project-root}/_bmad-output/specs/spec-lot-5-atelier-rag-2026-10-04/SPEC.md'
  - '{project-root}/_bmad-output/specs/spec-lot-5-atelier-rag-2026-10-04/essai-modeles-5c.md'
---

<frozen-after-approval reason="human-owned intent — do not modify unless human renegotiates">

## Intent

**Problem:** L'étape Embedding de l'Atelier RAG ne propose que le modèle de la brique et fastembed ; un GGUF d'embedding d'architecture LLM (Qwen3-Embedding) posé hors de `models/embedding/` serait proposé comme modèle de conversation ; la troncature des chunks est silencieuse ; la voie B (comparaison A/B) survit dans le backend alors que la page l'a retirée.

**Approach:** Déclarer des modèles d'embedding supplémentaires pour l'atelier dans `wavestack.toml` (multilingual-e5-small TwinSunsLLC, Qwen3-Embedding-0.6B, valeurs d'`essai-modeles-5c.md`), chacun option de l'étape Embedding (id = id déclaré) avec disponibilité et raison, son emplacement mémoire et son cache de vecteurs ; signaler et écarter des modèles de conversation tout GGUF portant `{arch}.pooling_type` ; avertir de la troncature ; retirer la voie B du backend et les clés `ui.yaml` orphelines.

## Boundaries & Constraints

**Always:**
- Granite (`[rag.embedding]`, option `declared`) et fastembed inchangés ; la brique RAG garde son seul modèle et son index.
- Modèles supplémentaires déclarés en liste `[[rag_lab.embeddings]]`, même schéma qu'`EmbeddingModel` (fichiers sous `embedding/`, sha256 vérifié au chargement) ; id unique, ni `declared` ni `fastembed`, ni l'id de la brique, au plus 32 caractères ; entrée invalide écartée avec message, les autres gardées.
- Un emplacement `LoadRegistry` par modèle (`rag_lab.embedding.<id>`) : budget compté, brique jamais déchargée par l'atelier.
- Identité du cache de vecteurs : id, dims, taille, sha256, préfixes, `max_tokens`.
- Chaque incompatibilité a son message dédié en fr, en et de (`content/messages.yaml` et copies) : fichier absent, GGUF d'embedding/reranking pris pour un modèle de conversation, troncature.
- GGUF portant `{arch}.pooling_type`, où qu'il soit (dossier des modèles, cache HF, LM Studio) : statut `incompatible` à la découverte, jamais sélectionné automatiquement, carte rouge sur Diagnostic et modèles avec le message dédié.
- Troncature : nombre de chunks dépassant `max_tokens` du modèle, affiché dans le focus de l'étape (avertissement, pas une erreur).
- Voie B : une seule chaîne par run et par validation (`LANES_MAX`, `compare()`, `lane`, `comparison`, `RagLabCompared`/`RagLabComparison`, `session.rag_lab.two_chains`/`lane`, `rag_lab.compare.*` retirés) ; clés `rag.comparison.*`, `rag.chain_a`, `rag.chain_b`, `rag.chain_b_steps` (et `rag.chain_steps`, orpheline) retirées des trois `ui.yaml` ; `rag.chain` gardée.

**Never:** téléchargement depuis l'atelier (5c-4) ; rerankers (5c-2) ; changer le modèle ou les réglages du dossier de données partagé ; nouvel endpoint ; modèles déclarés via settings.json.

## I/O & Edge-Case Matrix

| Scenario | Input / State | Expected Output / Behavior | Error Handling |
|----------|--------------|---------------------------|----------------|
| Choix e5 | fichier présent, chaîne livrée, Embedding = multilingual-e5-small | run `ok`, passages préfixés `passage: `, question `query: `, cache sous sa clé | N/A |
| Fichier absent | Qwen3-Embedding non téléchargé | option listée, indisponible, raison nommant le fichier `embedding/…` | refus `unavailable` sur la ligne |
| Budget | modèle trop lourd pour la RAM restante | rien chargé | refus nommant le modèle |
| Troncature | chunks de 1 500 caractères, Granite (512 tokens) | focus : « N chunks sur M dépassent 512 tokens, tronqués » | avertissement |
| Qwen3-Embedding dans le cache HF | GGUF avec `qwen3.pooling_type` | absent du choix du modèle de conversation, carte incompatible avec le message dédié | jamais auto-sélectionné |
| Deux chaînes postées | `pipelines` de longueur 2 | 422 | N/A |

</frozen-after-approval>

## Code Map

- `wavestack.toml` -- `[rag.embedding]` l. 86-105 (modèle de forme) ; ajouter `[[rag_lab.embeddings]]` après `[rag_lab]` (l. 126). URL `resolve/<commit complet>/…` (commit complet via le Hub), size et sha256 d'`essai-modeles-5c.md` ; e5 : dims 384, max_tokens 512, préfixes `query: ` / `passage: `, MIT, RSS 440 ; Qwen3 : dims 1024, max_tokens 2048, query_prefix `Instruct: Given a web search query, retrieve relevant passages that answer the query\nQuery:`, Apache-2.0, RSS 1055.
- `src/wavestack/config.py` -- `EmbeddingModel` l. 402, `Config.rag_embedding` l. 831 ; ajouter `Config.rag_lab_embeddings` (liste validée entrée par entrée, sur le modèle de `cloud_models` l. 664-690 et `cloud_rejected`).
- `src/wavestack/models/discovery.py` -- `_rag_model_files` l. 86-94 : inclure les fichiers déclarés de l'atelier.
- `src/wavestack/session/diagnostic.py` -- `_discover` l. 420-477 : pour un GGUF `found`, `catalog.header_metadata(path)` (cache, préchauffé) ; `{arch}.pooling_type` présent → `status="incompatible"`, `reason` dédiée (auto-sélection `_usable` l. 1228 et fichier unique l. 546 lisent `status`).
- `src/wavestack/models/catalog.py` + `models/capabilities.py` -- `_engine_metadata` l. 369 lit déjà `raw` ; porter `pooling_type` dans `EngineMetadata`, `capabilities_for` l. 45-58 pose `incompatible_reason` dédié (précédent `no_template`) → `disabled_text` de la carte. `diagnostic.html` inchangé (pastille rouge existante).
- `src/wavestack/models/embedding.py` -- `_embed(truncate=True)` l. 60-82 : compter les textes tronqués du dernier `embed_passages` (attribut lu par l'atelier).
- `src/wavestack/rag/lab.py` -- `OPTIONS` l. 65 et `_every_kind_option_and_setting` l. 313-340 : options statiques exigées dans le YAML, options de modèles déclarés ajoutées par le catalogue (libellé = `label_text` du toml) ; `Catalog.payload()` l. 436-482 parcourt aussi ces options ; `Stage.option` max 32 ; `_embedding` l. 1647-1718 (troncature après l. 1683) ; `Loans` l. 1152-1221 (retirer `_by_key`) ; voie B : `LANES_MAX` l. 90, `run()` l. 1362-1427, `_Lane.lane`, `_compared`/`compare` l. 2189-2261.
- `src/wavestack/trace/catalog.py` -- l. 1224-1343 : retirer `RagLabLaneId`, `lane`, `lanes`, `RagLabCompared`, `RagLabComparison`, `comparison` ; ajouter `warning_text: str | None = None` à `RagLabStageEndedPayload`.
- `src/wavestack/session/app_session.py` -- `_rag_lab_catalog` l. 9166-9203 (options déclarées : disponible si fichiers présents, sinon raison) ; `_rag_lab_embedder` l. 9389-9427 (slot par modèle, sha256, `_embedder_factory`) ; `_rag_lab_identity` l. 9527 ; `run_rag_lab` l. 9248-9282 et `validate_rag_lab` l. 9296-9313 (voie B).
- `src/wavestack/web/app.py` -- `LANES_MAX` l. 39, 239, 252 : `pipelines` de longueur 1.
- `src/wavestack/web/static/rag.js` -- restes de voie B (l. 10, 38, 143-176, 200, 223, 278, 373, 621, 1008, 1027-1029, 1070, 1184) ; afficher `warning_text` dans le focus et `#rag-details`.
- `content/messages.yaml`, `content/ui.yaml`, `content/rag_lab.yaml` et copies `content/i18n/{en,de}/` -- clés ajoutées ou retirées dans les trois langues (`test_i18n.py` l. 240-266, `test_backend_messages.py`, `test_ui_texts.py`).
- Tests -- `tests/test_rag_lab.py` (voie B : l. 313-318, 340, 381, 467, 513, 529, 625, 716, 746, 1284), `tests/test_rag_lab_alt.py` (l. 58-319), `tests/test_rag.py` / `test_rag_rerank.py` (toml), `tools/e2e/run_e2e.py` (zone RAG).

## Tasks & Acceptance

**Execution:**
- [x] `wavestack.toml`, `config.py` -- déclarer et valider `[[rag_lab.embeddings]]` -- source unique des modèles proposés.
- [x] `trace/catalog.py`, `rag/lab.py`, `app_session.py`, `web/app.py`, `rag.js`, messages, `ui.yaml` -- retirer la voie B -- une seule chaîne, clés orphelines supprimées.
- [x] `rag/lab.py`, `app_session.py`, `rag_lab.yaml` ×3 -- options d'embedding déclarées, disponibilité, emplacement et cache par modèle.
- [x] `models/embedding.py`, `rag/lab.py`, `trace/catalog.py`, `rag.js` -- avertissement de troncature.
- [x] `discovery.py`, `diagnostic.py`, `catalog.py`, `capabilities.py`, messages ×3 -- GGUF d'embedding/reranking jamais modèle de conversation, signalé.
- [x] tests pytest (matrice, validation toml, slot par modèle, discovery) et E2E RAG (choix e5 visible dans le select, indisponible sans fichier) ; `docs/guide.md` (puce Embedding).

**Acceptance Criteria:**
- Given e5-small et Granite utilisés l'un après l'autre, when on relance la chaîne avec Granite, then son cache est relu (pas de recalcul) et e5 a le sien.
- Given un run avec e5 pendant que la brique tient Granite, when le run se termine, then le slot `embedding` de la brique est intact et `rag_lab.embedding.multilingual-e5-small` est libéré.
- Given la langue en ou de, when on lit les raisons et l'avertissement, then ils sont traduits.
- Given `uv run pytest` et `ruff check`, when on les lance, then tout est vert.

## Implementation Notes

- `[[rag_lab.embeddings]]` : commits complets relevés via l'API du Hub (`b6cac9615d4e…`, `370f27d7550e…`, mêmes préfixes que l'essai). `load_config` remet la liste de `wavestack.toml` après la fusion avec `settings.json` (jamais déclarés par settings.json) ; une entrée écartée est tracée une fois en `harness_error` (contexte `rag_lab`), les autres restent.
- Voie B : `LabRun(run_id, question, pipeline, deps)`, `run_rag_lab(question, pipeline=None)`, `validate_rag_lab(pipeline)` ; l'API garde la forme `{"pipelines": [...]}` avec `max_length=1` (deux : 422). `step_id` devient `lab{n}.s{i}`. `rag_lab_run_started` porte `stages` à la place de `lanes`. Le journal est en mémoire (perdu au redémarrage, `instance_id` force la resynchronisation) : aucun `last_run` d'avant ce lot ne peut être relu, pas de tolérance de l'ancien format ajoutée. Clés `session.rag_lab.two_chains`, `session.rag_lab.lane`, `rag_lab.compare.*` retirées des trois `messages.yaml`. L'entrée correspondante de `deferred-work.md` est soldée.
- Identité du cache : prefixes et `max_tokens` ajoutés aussi pour le modèle de la brique : les caches Granite existants hors index de la brique sont recalculés une fois.
- Troncature : `LlamaCppEmbedder.last_truncated` (tokenisation comme `embed`, BOS compris) et `max_tokens` ; le compte est écrit dans `chunks.json` du cache et redit à la relecture. fastembed et l'index de la brique relu tel quel : pas d'avertissement.
- `{arch}.pooling_type` : porté dans `EngineMetadata.pooling_type` (en-tête Python et moteur en processus) ; `capabilities_for` pose `models.capabilities.pooling` ; `_discover` marque `incompatible` avant toute sonde. Clé ajoutée à `reason_message`.

## Spec Change Log

## Review Triage Log

Passe 1, 2026-10-05.

| # | Source | Constat | Verdict | Preuve | Suite |
| --- | --- | --- | --- | --- | --- |
| 1 | verif, edge, blind | le journal d'`app.js` lit `lanes`, `p.lane`, `p.comparison` retirés : `TypeError` sur tout événement de l'atelier | high | `app.js` l. 6162-6166, 6228-6229, 6243-6252 ; `logRow` sans garde | patch (+ E2E du journal, clé `main.log.rag_lab_compared` retirée) |
| 2 | edge | `_discover` lit l'en-tête complet de chaque GGUF en synchrone, sous `_READ_LOCK` : la recherche de lancement repaie ce que R1 avait mis en arrière-plan (21 s / 39 fichiers sur le PC pro) | medium | `diagnostic.py:449`, `catalog.header_metadata` ; `{arch}.*` précède `tokenizer.*` dans les GGUF (vérifié sur Qwen3.5 et `tiny-bert-rank.gguf`) | patch (lecture arrêtée au premier `tokenizer.*`) |
| 3 | blind | sha256 de 639 Mo recalculé à chaque run (modèle chargé puis fermé par run) | medium | `_rag_lab_declared_lent.open_model` appelle `file_sha256` ; `rag_lab.file_digest` garde le résultat par (taille, mtime) | patch |
| 4 | verif | `pooling_type` lu par `VocabTokenizer` (moteur en processus, Ollama) non testé, seul refus au chargement d'un modèle servi | medium | `engine.py:261` ; `test_model_servers.py:1344-1366` n'en dit rien | patch (deux assertions) |
| 5 | verif | avertissement de troncature dans la page (focus, carte) vérifié par aucun E2E | medium | `rag.js:731, 1138` ; aucune occurrence dans `run_e2e.py` | defer (la pile E2E branche un faux embedder qui ne tronque jamais : contrôle à vide) |
| 6 | blind, edge | `pooling_type = 0` (NONE, génératif) pris pour un modèle d'embedding | low | `capabilities_for`, `_embedding_or_reranking` testent `is not None` | patch (> 0) |
| 7 | blind | deux `_pooling` (catalog, engine) qui divergent sur `bool` | low | `catalog.py:381`, `engine.py:186` | patch (un seul helper) |
| 8 | blind | accord « 1 chunk sur 16 dépassent … tronqués » | low | `rag_lab.embedding.truncated` sans formes one/other | patch |
| 9 | edge | chemin « . » : `parts[0]` lève `IndexError` dans la `cached_property` | low | `_relative_path` accepte « . » ; `PureWindowsPath(".").parts == ()` | patch |
| 10 | blind | `RAG_LAB_RESERVED_IDS` recopie `OPTIONS["embedding"]` | low | `config.py` ne peut importer `rag.lab` | patch (test d'égalité) |
| 11 | blind | annotations `list[str]` pour des `Message` | low | `Config.rag_lab_embeddings`, `_rag_lab_trace_rejected` | patch |
| 12 | blind | `docs/installation.md` (« Modèles du RAG ») ignore les deux modèles de l'atelier | low | tableau à Granite et BGE seulement | patch |
| 13 | blind | spec : dernière tâche non cochée, note sur l'ancien journal contredite | low | correction de la spec | rejeté (tâche cochée à la vérification) |
| 14 | blind | caractères de l'id non validés | low | toml livré, écrit par les développeurs ; DOM et slot tolèrent | rejeté |
| 15 | blind, edge | `[rag_lab.embeddings]` en table simple ignoré sans message | low | cas d'écriture du toml livré, ajout de branche | rejeté |
| 16 | blind | entrées de settings.json ignorées sans message | low | voulu (Never) | rejeté |
| 17 | blind | entrée rejetée tracée seulement à la construction du catalogue | low | toml livré valide ; ajout de surface | rejeté |
| 18 | blind | anciens caches de vecteurs jamais nettoyés | low | dossier de données, recalcul unique | rejeté |
| 19 | blind | raison « fichier absent » sans l'URL | low | le téléchargement arrive en 5c-4 | rejeté |
| 20 | blind | tests : LM Studio, préfixes au niveau du run, fixture inutilisée | low | même chemin que le cache HF ; adaptateur testé | rejeté |
| 21 | blind | avertissement distingué de l'erreur par la couleur seule | low | même motif que les erreurs, texte explicite | rejeté |
| 22 | blind | restes de la forme à deux chaînes (`pipelines` liste, `rag-lane`) | low | forme d'API gardée, décision notée | rejeté |
| 23 | verif, edge | GGUF d'embedding servi par llama-server non signalé | low | hors des emplacements de l'intention ; choix explicite de l'utilisateur | rejeté |
| 24 | edge | deux constructions concurrentes du catalogue tracent deux fois | low | course rare, effet : une ligne de trace en double | rejeté |

## Design Notes

- Option id = id déclaré (`multilingual-e5-small`, `qwen3-embedding-0.6b`) : `PRESETS` et `default_pipeline` restent sur `declared`.
- Fichier absent : option indisponible (contrairement à `declared`, que la brique gère) ; la raison nomme le chemin sous le dossier des modèles, le téléchargement viendra en 5c-4.
- Signe d'un modèle d'embedding/reranking : `{arch}.pooling_type` dans l'en-tête GGUF, absent des modèles de conversation (essai §3).
- Les relectures de `last_run` d'avant ce lot (champ `lane`) ne doivent pas casser l'état : vérifier si le journal persiste et tolérer l'ancien format le cas échéant.

## Verification

**Commands:**
- `uv run ruff check . && uv run ruff format --check .` -- expected: aucun écart
- `uv run pytest -q` -- expected: vert (hors `test_readme_is_a_short_onboarding_page` si encore rouge sur main)
- `uv run --with playwright==1.56.0 python tools/e2e/run_e2e.py --channel msedge --only rag rag_rerank rag_lab` -- expected: aucun FAIL
