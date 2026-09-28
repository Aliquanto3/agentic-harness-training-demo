---
title: 'Atelier RAG : l''architecture RAG à manipuler'
type: 'feature'
created: '2026-09-28'
status: 'ready-for-dev'
review_loop_iteration: 0
followup_review_recommended: false
context:
  - '{project-root}/CLAUDE.md'
  - '{project-root}/_bmad-output/planning-artifacts/architecture/architecture-agentic-harness-training-demo-2026-09-23/ARCHITECTURE-SPINE.md'
  - '{project-root}/_bmad-output/planning-artifacts/ux-designs/ux-agentic-harness-training-demo-2026-09-22/EXPERIENCE.md'
  - '{project-root}/_bmad-output/planning-artifacts/ux-designs/ux-agentic-harness-training-demo-2026-09-22/DESIGN.md'
  - '{project-root}/_bmad-output/specs/spec-agentic-harness-training-demo/stories/31-mode-sombre.md'
  - '{project-root}/_bmad-output/specs/spec-agentic-harness-training-demo/stories/25-selecteur-de-modeles-regroupe-et-tableau-des-capacites.md'
  - '{project-root}/_bmad-output/specs/spec-agentic-harness-training-demo/stories/16-reranking.md'
  - '{project-root}/tools/e2e/README.md'
warnings:
  - oversized
deferred: []
---

<intent-contract>

## Intent

**Problem:** Aujourd'hui, le RAG n'existe que comme une brique de l'atelier. Sa chaîne est figée : sqlite-vec, embedding et reranker déclarés dans `wavestack.toml`, `top_k` fixe. Le formateur ne peut donc ni montrer de quoi est faite une architecture RAG, ni faire varier un composant pour en voir l'effet. Anaël a demandé le 2026-09-28 un écran à part pour cela, avec FAISS et LanceDB parmi les bases vectorielles.

**Approach:** Ajouter un nouvel écran, `/rag`, atteint depuis la barre haute. Il dessine la chaîne (découpage, embedding, base vectorielle, recherche, reranking, construction du contexte, génération) et l'exécute sur une question, étape par étape, sur le fil de travail de la session. Chaque étape est tracée par des événements `rag_lab_*` (AD-1, AD-2), avec ce qui entre, ce qui sort, les scores, les rangs, la durée et la mémoire. Le livrable se découpe en quatre incréments, chacun utilisable seul :
1. la chaîne livrée, exécutée telle quelle ;
2. le choix des options et des réglages, puis la comparaison de deux configurations ;
3. FAISS et LanceDB, dans l'extra `rag-alt` ;
4. l'ajout, le retrait et le déplacement de composants, dont BM25 et la fusion hybride.

## Boundaries & Constraints

**Always:**
- `uv`, `ruff` et `pytest` (CLAUDE.md). Code et identifiants en anglais ; textes d'interface et explications en français, dans `content/rag_lab.yaml` (AD-19).
- Un incrément livré est commité avec `ruff` et `pytest -q` verts et, si l'interface a changé, un E2E sans FAIL. Un incrément non livré est noté comme tel dans la spec (Spec Change Log) et dans le rapport. Il ne casse jamais le précédent : pas de code mort branché, pas d'option affichée sans implémentation.
- L'atelier RAG est un bac à sable : il ne change ni la configuration ni l'état de la brique RAG de l'atelier des briques.
- AD-1 : tout ce que la page affiche vient des événements `rag_lab_*` ou de `GET /api/rag_lab`, construit côté Python à partir de la configuration et du journal. Cela vaut pour la disponibilité des options, les scores, les rangs et les écarts de la comparaison. Le front met en forme, rien de plus.
- AD-3 et AD-24 : une exécution est une intention de classe (b), acceptée en `idle` seulement. La session passe alors dans le nouvel état `rag_lab`, et le travail se fait sur `self._executor`, le fil unique. « Arrêter » (`stop`) arme un `CancelToken`, vérifié entre deux étapes et entre deux passages d'un embedding ou d'un reranking.
- AD-8 : tout chargement de modèle passe par `LoadRegistry` avec les mêmes appels que `_load_embedder` et `_load_reranker`, relus au moment de l'implémentation, car la story 24 change `grant`. Si la brique RAG a déjà chargé l'embedder ou le reranker, le laboratoire l'emprunte sans le fermer. Sinon, il le charge dans le créneau `EMBEDDING` ou `RERANKER` et le ferme en fin d'exécution. Les bibliothèques FAISS et LanceDB sont comptées à leur premier import (incrément 3).
- AD-15 : tout marche hors ligne. Aucune connexion n'est ouverte, et la garde réseau reste active dans les tests.
- AD-20 : les index propres au laboratoire se construisent à la demande sous `config.rag_lab_dir()`, soit `data_dir()/rag_lab`, jamais dans le dépôt. L'index de la brique n'est que lu.
- Jetons de design seulement. La page applique les règles de la story 31 : `theme.js` en tête de `<head>`, `tokens.css`, sélecteur `[data-theme-picker]`, aucune couleur en dur. `tests/test_web_tokens.py` doit passer.
- Aucune dépendance nouvelle hors de l'extra `rag-alt`, qui contient exactement `faiss-cpu==1.15.1` et `lancedb==0.39.0`. `uv.lock` est mis à jour. BM25, la fusion et la recherche exhaustive sont en Python pur.
- Aucun vrai modèle dans le conteneur. On utilise les doublures : `tests/fake_embedder.py`, `tests/fake_reranker.py`, les faux serveurs de `tools/e2e`, les GGUF synthétiques.
- `uv run pytest -q` reste entièrement vert, et aucune story livrée ne casse. Mettre à jour EXPERIENCE.md, DESIGN.md (composants), SPEC.md, README, la spine (AD-2, AD-20, AD-22, Stack) et `tools/e2e/README.md`.

**Never:**
- Exécuter la génération dans le laboratoire. L'étape est dessinée, avec l'entrée qu'elle recevrait (le contexte construit), et elle dit pourquoi elle ne s'exécute pas ici.
- Glisser-déposer obligatoire : les déplacements se font par boutons, au clavier.
- Indexer des documents de l'utilisateur (non-goal V1), faire du RAG avancé (HyDE, self-RAG) ou comparer des modèles génératifs.
- Télécharger un modèle depuis le laboratoire. Un fichier manquant renvoie à la carte RAG de l'atelier.
- Écrire dans `data/rag_index.sqlite` ou sous la racine du dépôt.

## I/O & Edge-Case Matrix

| Scenario | Input / State | Expected Output / Behavior | Error Handling |
|----------|--------------|---------------------------|----------------|
| Chaîne livrée | `idle`, index de la brique à jour, fichiers présents | `rag_lab_run_started`, puis une paire `stage_started` / `stage_ended{status: ok}` par étape exécutée. La génération est `not_run`. Le contexte liste `top_k` extraits au format `RagContent.excerpt` | — |
| Occupé | Un tour, un téléchargement ou une construction en cours | 409 avec `_refusal_reason()` | Rien n'est émis |
| Question vide ou trop longue | `""`, ou plus de 500 caractères | 422, message français (`loc`, `type`) | — |
| Index de la brique absent ou périmé | Option sqlite-vec avec la taille livrée | L'étape base vectorielle passe en `error` avec la raison de la brique (`_rag_index_error`) ; les suivantes en `skipped` ; le run se termine en `error` | Aucun plantage, retour en `idle` |
| Modèle d'embedding absent | Fichiers manquants | Étape embedding en `error` : « Téléchargez-le depuis la carte RAG de l'atelier » | idem |
| Reranker indisponible | Sans fichier, refusé par le budget ou en échec | Étape reranking en `skipped` ou `error` avec sa raison ; le contexte prend les `top_k` premiers de la recherche | Le run continue |
| Refus du budget | `check_component` refuse | L'étape concernée passe en `error` avec le message chiffré ; rien n'est chargé | — |
| Arrêt | « Arrêter » pendant une étape | L'étape en cours passe en `cancelled`, les suivantes en `skipped`, le run en `cancelled` ; retour en `idle` | — |
| Option sans l'extra (incr. 3) | `faiss` ou `lancedb` absents | Catalogue : `available: false`, avec une raison qui donne la commande d'installation. Un run qui la demande : 409 avec la même raison | — |
| Import refusé (incr. 3) | DLL bloquée (AppLocker) | Étape en `error` (`ImportError`, en français) ; l'option est ensuite marquée indisponible | — |
| Chaîne invalide (incr. 4) | Deux recherches sans fusion, reranking sans recherche… | 409 : raison française qui nomme l'étape fautive ; rien n'est émis | — |
| Emprunt de l'embedder | Brique RAG active, embedder chargé | Réutilisé, non fermé ; aucun nouveau `grant` | — |

</intent-contract>

## Code Map

Les stories 33, 23, 34, 32, 24, 25, 26, 27, 31 et 29 modifient l'arbre avant celle-ci. On se repère aux symboles, jamais aux numéros de ligne.

- `src/wavestack/rag/index.py`
  - Fonctions à réutiliser : `connect`, `load_vec`, `vec_unavailable`, `read_meta`, `read_chunks`, `IndexMeta`, `corpus_digest`, `passage_text` (le titre puis le texte : c'est ce qui est embeddé), `write_index`, `build_index` (paramètres `on_progress` et `cancelled`), `BuildCancelled`, `IndexInUse` et `file_sha256`.
  - Le motif d'écriture est à reproduire pour les index du laboratoire : un fichier temporaire, puis `os.replace`.
- `src/wavestack/rag/retriever.py`
  - `Excerpt` (`position`, `chunk_id`, `doc_id`, `title_fr`, `text`, `score`) ;
  - `Retriever`, le port que les stratégies V2 doivent implémenter ;
  - `score_of`, qui calcule `1 − distance` borné à [0, 1] ;
  - `SqliteVecRetriever`, qui prend `search(query, k)`.
- `src/wavestack/rag/corpus.py`
  - `RagContent` : `excerpt()` et `placement_fr` ;
  - `Chunk` ;
  - `split_text` et `chunk_corpus(content, max_chars)`. Le corpus donne 77 extraits à 300 caractères, 29 à 700 et 16 à 1 200 ;
  - `load_rag_content`.
- `src/wavestack/models/embedding.py`
  - `Embedder`, qui prend `embed_queries` et `embed_passages` et rend des vecteurs normalisés ;
  - `normalize`, `open_embedder` et `model_path`.
- `src/wavestack/models/reranker.py` -- `Reranker.score(query, passages, cancelled, progress)`, `RerankScore`, `RerankCancelled` et `open_reranker`.
- `src/wavestack/models/load_registry.py`
  - Constantes de créneau `EMBEDDING`, `RERANKER` et `COMPRESSOR`, à imiter.
  - `component_cost`, `check_component`, `grant`, `release` et `holder`.
  - `process_rss`, qui mesure le processus et ses enfants.
- `src/wavestack/config.py`
  - Chemins : `data_dir`, `repo_root` et `models_dir`. Seul `config` résout les chemins (AD-20).
  - `Config.rag_embedding`, `rag_reranker`, `rag_top_k` (bornes 1 à 20), `rag_rerank_candidates`, `rag_chunk_max_chars` (≥ 50) et `rag_index_path()`.
  - Motifs à reprendre : `compression_cost_bytes` pour un `cost_mb`, et `_int`.
- `src/wavestack/session/app_session.py`
  - `__init__` : `_embedder_factory` et `_reranker_factory` (les faux s'y branchent), `_executor` (un seul worker) et `_load_registry`.
  - État RAG : `_rag_model`, `_rerank_model`, `_rag_content`, `_embedder`, `_rag_retriever`, `_reranker`, `_rag_index_error` et `_rag_missing_fr`.
  - `_rag_static_reason`, `_rag_unavailable`, `_rerank_static_reason` et `_rerank_availability` donnent les raisons à réutiliser.
  - Chargement et fermeture : `_load_embedder`, `_build_embedder`, `_load_reranker`, `_close_embedder` et `_close_reranker`. Ces fonctions émettent `_error` ; le laboratoire, lui, rapporte l'erreur dans son étape.
  - État de la session : `_enter_rag_job`, `_set_state`, `_refusal_reason`, `stop` (ajouter `rag_lab`) et `hold`.
  - `_rag_rerank_step` : son tri stable (score, puis rang d'origine) est à reprendre.
  - Le fichier fait plus de 6 000 lignes. La logique du laboratoire va dans un module à part, et la session ne garde que des méthodes minces.
- `src/wavestack/trace/catalog.py`
  - `SessionState`, auquel ajouter `rag_lab` ;
  - `PAYLOAD_MODELS`, qui enregistre chaque `kind` ;
  - `RagSearchEndedPayload` et `RerankedExcerpt`, les modèles de forme.
- `src/wavestack/trace/scope.py` -- `scoped(...)`, qui pose `step_id`, `brick`, `component`, `actor` et `trigger`.
- `src/wavestack/web/app.py`
  - `create_app`, et les routes de page `index_page`, `diagnostic_page` et `/models` (story 25).
  - Le motif d'intention de classe (b) de `build_rag_index`, où `SendRefused` donne un 409.
  - Le gestionnaire de `RequestValidationError`, `_revalidate_pages` et `_latest`.
- `src/wavestack/web/static/`
  - `index.html` : `header.top-bar`, où la story 29 a peut-être ajouté son lien d'écran.
  - `models.html` : `nav.page-tabs`, story 25.
  - `theme.js` et `[data-theme-picker]`, story 31.
  - `tokens.css`.
  - `app.js` : `streamEvents` et `parseSseEvent`, le protocole SSE à recopier ; `app.js` lui-même ne change pas.
- `tests/fake_embedder.py` -- `FakeEmbedder` : 64 dimensions, sac de mots haché, `fail`.
- `tests/fake_reranker.py` -- `FakeReranker` : `fail`, `before_each` (pour arrêter en cours de route), `calls`.
- `tests/test_rag_rerank.py` -- `index`, `rerank_config`, `place_reranker`, `session_for` et `wait_idle`, à réutiliser.
- `tests/test_web_app.py` et `tests/test_web_tokens.py` -- les pages servies et les règles des jetons et du thème (story 31).
- `tools/e2e/stack.py` -- `rag_settings` : faux embedding `fake-embedding`, index dans le dossier de données, fichiers servis par le faux serveur.
- `tools/e2e/wavestack_e2e.py` -- remplace `embedding.open_embedder` et le reranker par les faux.
- `tools/e2e/run_e2e.py` -- `s_rag` (télécharge et construit), `s_rag_rerank`, `SCENARIOS`, `Run.shot`, `Run.shot_element`, `_fully_visible`, et `_contrast_sweep` (story 31).
- `pyproject.toml`
  - `[project.optional-dependencies]`, où se trouve déjà `compression` ;
  - `[tool.uv] no-build-package` ;
  - l'index explicite `abetlen-cpu`.
- `wavestack.toml` -- `[rag]` ; y ajouter `[rag_lab]`.
- `README.md` -- `## Compression du contexte (Headroom)` sert de modèle pour une section d'extra.

## Tasks & Acceptance

**Execution:**
- `_bmad-output/specs/spec-agentic-harness-training-demo/stories/30-atelier-rag-l-architecture-rag-a-manipuler.md` -- Livrer les incréments de la section « Incréments » dans l'ordre 1 → 4. Chacun se clôt par la Verification et un commit. Si le temps manque, s'arrêter après le dernier incrément livré et noter les suivants « non livré » dans le Spec Change Log. -- Raison : ce sont des livraisons utilisables même partielles.

**Acceptance Criteria:**
- Given un incrément livré, when on lance la Verification, then `ruff`, `pytest -q` et l'E2E passent, et les critères des incréments précédents restent vrais.
- Given un ou plusieurs runs du laboratoire, when on lance `git status`, then aucun fichier nouveau ou modifié n'apparaît sous la racine du dépôt (index et caches sous `data_dir()` seulement).

## Incréments

### Incrément 1 — La chaîne livrée, dessinée et exécutée

**Execution:**
1. `content/rag_lab.yaml` (nouveau), et `RagLabContent` (pydantic, `extra="forbid"`) dans `src/wavestack/rag/lab.py`. Pour chaque type d'étape : `label_fr` et `explain_fr` (2 à 3 phrases). Pour chaque option : `label_fr`. À quoi s'ajoutent les textes de page : titre, aide, « génération non exécutée ici » et « emprunté à la brique RAG ». Un fichier invalide donne `content_error_fr` dans `GET /api/rag_lab`, et la page l'affiche. Raison : AD-19.
2. `src/wavestack/rag/lab.py` (nouveau, sans dépendance à la session) :
   - `Stage{id, kind, option, params}` et `Pipeline{label_fr, stages}` ;
   - `default_pipeline(cfg)` : `chunking/paragraphs{chunk_max_chars}`, `embedding/declared`, `vector_store/sqlite_vec`, `vector_search/cosine{candidates}`, `rerank/declared`, `context/excerpts{top_k}`, `generation/not_run` ;
   - `validate_pipeline(p, catalog) → reason_fr | None` : à cet incrément, seule la chaîne livrée est acceptée ;
   - `LabRun`, qui exécute les étapes d'une voie avec des fonctions injectées (embedder, reranker, index, annulation, émission) et rend, pour chaque étape, `input_fr`, `output_fr`, `facts`, `items`, `duration_ms` et `rss_bytes`.

   Le découpage lit les extraits de l'index (`read_chunks`). La recherche passe par `SqliteVecRetriever`. Le reranking reprend le tri stable de `_rag_rerank_step`. Le contexte suit le format `RagContent.excerpt`. Raison : un moteur testable seul, sans alourdir `app_session.py`.
3. `src/wavestack/trace/catalog.py` -- Ajouter `rag_lab` à `SessionState`, puis cinq `kind` et leurs payloads (note de conception) : `rag_lab_run_started`, `rag_lab_stage_started`, `rag_lab_stage_progress`, `rag_lab_stage_ended` et `rag_lab_run_ended`. Raison : AD-2.
4. `src/wavestack/session/app_session.py` -- Ajouter les méthodes minces qui s'appuient sur `rag/lab.py` :
   - `rag_lab_state()`, qui donne le catalogue, la chaîne par défaut, le contenu et sa raison d'erreur, ainsi que les disponibilités, calculées par `_rag_unavailable` et `_rerank_availability` ;
   - `run_rag_lab(question, pipelines)`, de classe (b), qui passe en `rag_lab` puis `executor.submit`. L'embedder et le reranker sont empruntés ou chargés, puis fermés (AD-8), et la session revient en `idle` avec la raison qu'elle avait.

   Il faut aussi étendre `stop` à `rag_lab`. Pour la portée, poser `step_id=lab{n}.{lane}.s{i}`, `brick="rag"`, `component="rag_lab.{kind}"`, `actor="harness"` et `trigger="user"`. Raison : AD-3, AD-8 et AD-24.
5. `src/wavestack/web/app.py`
   - Ajouter les routes :
     - `GET /rag`, qui sert `rag.html` ;
     - `GET /api/rag_lab`, qui renvoie `{catalog, default_pipeline, content, content_error_fr, last_run, session_state, seq}`, où `last_run` est formé des enveloppes `rag_lab_*` du dernier run lues dans le journal ;
     - `POST /api/intentions/rag_lab_run`, de corps `RagLabRunIntention{question: str (1 à 500), pipelines: list[Pipeline] | None (max 1 ici)}`, qui répond `{run_id}` et renvoie 409 sur `SendRefused` ou sur une chaîne refusée.
   - Raison : AD-18.
6. Fichiers statiques :
   - `src/wavestack/web/static/rag.html` (nouveau) :
     - en tête de `<head>`, `theme.js`, puis `fonts.css`, `tokens.css` et `rag.css` ;
     - `nav.page-tabs` : Atelier (`/`), les écrans de la story 29 s'ils existent, « Atelier RAG » (courant), Diagnostic et Modèles ;
     - le sélecteur de thème ;
     - `#rag-chain`, la chaîne en cartes reliées par des flèches, la génération en `ink-fill` et les autres en discipline `context` ;
     - `#rag-question`, avec « Lancer la chaîne » et « Arrêter » ;
     - `#rag-results`, une carte par étape : entrée, sortie, table des extraits (rang, avant, document, score), durée et mémoire.
   - `rag.js` (nouveau, module) : `GET /api/rag_lab`, puis le flux SSE à partir de `seq`. Il projette les `rag_lab_*` et `session_state` et désactive « Lancer » hors `idle`.
   - `rag.css` (nouveau) : jetons seulement.
   - Raison : AD-18 et story 31.
7. `index.html` (et `app.css` si besoin) -- Le lien `Atelier RAG` (`href="/rag"`) va dans `header.top-bar`, dans le même groupe que le lien d'écran de la story 29 s'il existe, et avec son style. Sinon, il prend la classe `screen-link` et se place avant `#reset-button`. Raison : l'écran est atteint depuis la barre haute.
8. Tests (`tests/test_rag_lab.py`, nouveau ; `tests/test_web_app.py`) :
   - chaque étape avec `FakeEmbedder` et `FakeReranker` : contenu des `items`, rangs, `before`, format du contexte ;
   - l'emprunt, qui ne ferme rien, et le chargement, qui ferme et libère le créneau ;
   - chaque ligne de la matrice : occupé, index absent, reranker indisponible, budget, arrêt ;
   - `/rag`, `/static/rag.js` et `/static/rag.css` servis en 200 ;
   - intentions 422 et 409 ;
   - rien d'écrit sous `repo_root()`.
9. `tools/e2e/run_e2e.py` et `tools/e2e/README.md` -- Scénario `s_rag_lab`, après `rag_rerank`, qui couvre les critères ci-dessous. Captures `NN-atelier-rag-chaine` et `NN-atelier-rag-resultats`, avec NN le prochain numéro libre. En fin de scénario, retour à `/`.
10. Documentation :
    - EXPERIENCE : surface « Atelier RAG », ligne Barre haute, composants `rag-chain` et `rag-stage-card` ;
    - DESIGN : composants, faits de jetons existants ;
    - SPEC : prochaine CAP libre, « Atelier RAG » ;
    - spine : AD-2 pour les `kind`, AD-22 pour « l'atelier RAG exécute des chaînes à part ; le port `Retriever` les porte » ;
    - README : section « Atelier RAG ».

**Acceptance Criteria:**
- Given l'atelier à 1600 × 1000 après `rag_rerank`, when on lit la barre haute, then le lien « Atelier RAG » est entièrement visible (`_fully_visible`) sur une ligne, avec les autres commandes, et il mène à `/rag`.
- Given `/rag`, when la page est chargée, then :
  - `#rag-chain` montre sept cartes dans l'ordre (Découpage, Embedding, Base vectorielle, Recherche, Reranking, Construction du contexte, Génération) ;
  - chaque carte nomme son option livrée (sqlite-vec, « Faux embedding (e2e) », « Faux reranker (e2e) ») et son explication ;
  - l'onglet « Atelier RAG » porte `aria-current="page"` ;
  - `_contrast_sweep` ne renvoie aucun échec, en clair comme en sombre.
- Given la question « Combien de jours de télétravail par semaine ? », when on clique « Lancer la chaîne », then :
  - chaque carte de résultat passe de « en cours » à une durée en ms et une mémoire en Mo ;
  - l'étape Recherche liste `rag_rerank_candidates` extraits avec rang et score ;
  - l'étape Reranking montre, pour chacun, le rang avant et le rang après ;
  - l'étape Contexte affiche les `top_k` extraits au format de la brique ;
  - Génération dit « non exécutée dans l'atelier RAG » ;
  - aucune `pageerror` n'est levée.
- Given ces résultats, when on recharge `/rag`, then le même run se réaffiche (depuis `last_run`).
- Given un tour en cours dans l'atelier, when on poste `rag_lab_run`, then la réponse est 409 avec la raison.

### Incrément 2 — Options, réglages et comparaison

**Execution:**
1. `src/wavestack/config.py` et `wavestack.toml` -- Ajouter `rag_lab_dir()` (`data_dir()/"rag_lab"`) et la section `[rag_lab]` : `fastembed` (optionnelle : `model_name`, `dims`, `label_fr`), puis `faiss_cost_mb` et `lancedb_cost_mb` (incrément 3). Raison : AD-20.
2. `src/wavestack/rag/lab.py`
   - Réglages bornés dans le catalogue : `chunk_max_chars` de 200 à 1 500, `candidates` et `top_k` de 1 à 20, avec `candidates ≥ top_k`.
   - Option `vector_store/memory` : recherche exhaustive en Python pur (produit scalaire sur vecteurs normalisés).
   - Option `embedding/fastembed` : disponible seulement si `importlib.util.find_spec("fastembed")`, si `[rag_lab.fastembed]` est déclarée et si ses fichiers sont sous `models_dir()/fastembed`. Elle s'ouvre avec `local_files_only=True`. Sinon, elle est indisponible avec sa raison.
   - Cache de vecteurs, par clé : l'identité de l'embedder (id, dimensions, taille et sha256 du fichier), `chunk_max_chars` et `corpus_digest`. Il est écrit dans `rag_lab_dir()/<clé>/` (`chunks.json`, `vectors.f32` via `array('f')`) de façon atomique. L'étape Embedding dit « relus du cache » ou « calculés (N passages) », avec sa progression.
   - Pour sqlite-vec, l'index de la brique sert quand son `meta` correspond à la clé. Sinon, l'index est construit dans le dossier de la clé avec `write_index`.
   - `validate_pipeline` accepte toute option disponible.
3. `run_rag_lab` et l'intention -- `pipelines` accepte deux configurations au plus, A puis B, exécutées l'une après l'autre sur la même question. `rag_lab_run_ended.comparison` donne les extraits communs, ceux propres à A et à B, et les écarts de rang, calculés en Python.
4. `rag.html`, `rag.js` et `rag.css`
   - Chaque carte reçoit une liste d'options (les indisponibles sont désactivées, raison en infobulle et en texte) et ses réglages en `input type=number` bornés.
   - Une case « Comparer avec une autre configuration » ouvre la chaîne B.
   - Les résultats s'affichent en deux colonnes, suivies de la synthèse de comparaison.
   - Les chaînes en cours d'édition sont mémorisées dans `localStorage` (`wavestack.ragLab`, lecture protégée par `try/catch`), avec un bouton « Revenir à la chaîne livrée ».
5. Tests et E2E
   - Tests :
     - bornes et refus, en 422 ou 409 ;
     - la recherche en mémoire rend les mêmes rangs que sqlite-vec sur le faux embedder ;
     - cache relu, et reconstruit quand la taille change ;
     - fastembed indisponible sans le paquet, puis disponible avec un faux module injecté dans `sys.modules` ;
     - comparaison.
   - E2E : A = sqlite-vec avec 700 caractères, B = mémoire avec 300 caractères et `top_k` 2. La capture est `NN-atelier-rag-comparaison`.

**Acceptance Criteria:**
- Given A = livrée et B = « Recherche exhaustive en mémoire », avec extraits de 300 caractères et `top_k` = 2, when on lance la comparaison, then :
  - deux colonnes s'affichent ;
  - l'Embedding de B dit « calculés (77 passages) » au premier run et « relus du cache » au second ;
  - le Contexte de B a 2 extraits ;
  - la synthèse nomme les extraits communs et les écarts de rang ;
  - un nouveau dossier apparaît sous `rag_lab_dir()` et aucun fichier n'est créé dans le dépôt (`git status` inchangé).
- Given `candidates` < `top_k` saisi, when on lance, then la page affiche la raison du 409 et rien ne s'exécute.

### Incrément 3 — FAISS et LanceDB (extra `rag-alt`)

**Execution:**
1. `pyproject.toml`, `uv.lock`
   - Déclarer l'extra `rag-alt = ["faiss-cpu==1.15.1", "lancedb==0.39.0"]`.
   - Ajouter `faiss-cpu`, `lancedb` et `pyarrow` à `no-build-package` : roues seulement.
   - Mettre à jour `uv.lock`. Le conteneur ne joint pas l'index `abetlen` : voir la note de conception.
2. `src/wavestack/rag/lab.py`
   - Options `vector_store/faiss` (`IndexFlatIP`, `write_index`) et `vector_store/lancedb` (`lancedb.connect(dossier)`, table `chunks`, métrique `cosine`). Chacune est construite à la demande depuis le cache de vecteurs, dans `rag_lab_dir()/<clé>/faiss/` ou `lancedb/`, puis relue ensuite.
   - Catalogue : `find_spec` sans import. En cas d'absence : « Indisponible : FAISS (ou LanceDB) n'est pas installé. Depuis le dossier de WaveStack : `uv sync --extra compression --extra rag-alt`, puis relancez WaveStack. » Et, pour Headroom, « sans `--extra compression`, Headroom serait retiré ».
   - Premier import : `check_component` puis `grant` dans les créneaux `rag_lab.faiss` et `rag_lab.lancedb` (constantes dans `load_registry.py`), avec pour coût `[rag_lab] faiss_cost_mb = 60` et `lancedb_cost_mb = 180`. Ces créneaux ne sont jamais libérés, car un import ne se défait pas. L'étape le dit.
3. Tests
   - `tests/test_rag_lab_alt.py` : les options indisponibles sans l'extra (`find_spec` → `None`), la commande dans la raison, le refus du budget à l'import, l'`ImportError` convertie en raison.
   - Avec `pytest.importorskip("faiss")` et `("lancedb")`, FAISS et LanceDB rendent les mêmes rangs que la recherche en mémoire, sous la garde réseau. Ces tests sont lancés une fois avec `uv run --extra compression --extra rag-alt pytest tests/test_rag_lab_alt.py`, et le résultat va dans le rapport.
4. E2E : le scénario suit le catalogue. Indisponible : la raison contient `uv sync --extra`. Disponible : A = sqlite-vec et B = FAISS rendent les mêmes extraits. Le rapport dit quelle branche a tourné.
5. Documentation :
   - README : section « Atelier RAG : FAISS et LanceDB (extra optionnel) », avec la commande, l'avertissement Headroom, la taille (environ 390 Mo sur disque sous Linux, dont pyarrow 150 Mo et lancedb 170 Mo), le fonctionnement hors ligne, le dossier `rag_lab` que l'on peut supprimer, et les DLL non signées exposées à AppLocker.
   - Spine, tableau Stack : ajouter faiss-cpu 1.15.1 (MIT) et lancedb 0.39.0 (Apache-2.0, pyarrow 25.0.1), en optionnel.

**Acceptance Criteria:**
- Given l'environnement sans extra, when on ouvre la liste de la base vectorielle, then FAISS et LanceDB sont désactivés, et leur raison, affichée, contient `uv sync --extra compression --extra rag-alt`.
- Given l'extra installé, when on lance A = sqlite-vec et B = FAISS, then les extraits et les rangs du Contexte sont identiques. La Base vectorielle de B dit « construit (N vecteurs) » au premier run, « relu » au second, et donne la mémoire ajoutée à l'import.

### Incrément 4 — Ajouter, retirer et déplacer

**Execution:**
1. `src/wavestack/rag/lab.py`
   - Étapes `lexical_search/bm25` (Python pur, k1 = 1,5 et b = 0,75, tokenisation par `\w+` en minuscules, mots de 3 lettres et plus ; réglage `candidates`) et `fusion/rrf` (fusion par rangs réciproques, k = 60).
   - `validate_pipeline` applique les règles :
     - le découpage, l'embedding, la base vectorielle, le contexte et la génération sont fixes et dans cet ordre ;
     - entre la base et le contexte, l'ordre est libre parmi `vector_search`, `lexical_search`, `fusion` et `rerank` ;
     - il faut au moins une recherche ;
     - deux recherches exigent une fusion placée après elles, et une fusion exige deux recherches avant elle ;
     - le reranking vient après une recherche ;
     - une même étape n'apparaît qu'une fois.
   - Chaque refus nomme l'étape.
2. `rag.html`, `rag.js` et `rag.css`
   - Sur chaque carte mobile : les boutons « ◀ » et « ▶ » (`aria-label` « Déplacer avant » et « Déplacer après ») et « Retirer ».
   - Une palette « Ajouter un composant » propose les étapes absentes, insérées avant le Contexte.
   - Une chaîne invalide affiche la raison sur la carte fautive, et « Lancer » est désactivé : le serveur valide à chaque modification, via `POST /api/rag_lab/validate`, en lecture seule.
3. Tests et E2E
   - Tests : chaque règle ; le rang BM25 sur un petit corpus écrit à la main ; la RRF ; l'intention 409.
   - E2E : retirer le Reranking, ajouter BM25 et la Fusion, déplacer le Reranking après la Fusion, puis lancer. Capture `NN-atelier-rag-hybride`.

**Acceptance Criteria:**
- Given la chaîne livrée, when on retire Reranking et qu'on ajoute « Recherche lexicale BM25 » sans fusion, then la carte BM25 affiche « Deux recherches demandent une fusion après elles » et « Lancer » est désactivé. Une fois la Fusion ajoutée, le run montre, pour la Fusion, le rang de chaque extrait dans les deux recherches et son score RRF.
- Given une Fusion déplacée avant une recherche, when la chaîne est validée, then la raison nomme la Fusion et le 409 est renvoyé si l'on poste quand même.

## Spec Change Log

## Review Triage Log

## Design Notes

**Payloads.** Tous portent `run_id`. L'étape porte `lane` (`a` ou `b`) et `stage_id` :
- `rag_lab_run_started{question, lanes: [{lane, label_fr, stages: [{stage_id, kind, option, label_fr}]}], phase_label}` ;
- `rag_lab_stage_started{kind, option, phase_label}` ;
- `rag_lab_stage_progress{done, total}` ;
- `rag_lab_stage_ended{status: ok|error|skipped|cancelled|not_run, input_fr, output_fr, facts: [{label_fr, value_fr}], items: [{rank, before, chunk_id, doc_id, title_fr, text, score, sources}], borrowed: bool, error_fr, duration_ms, rss_bytes}` ;
- `rag_lab_run_ended{status: ok|error|cancelled, duration_ms, comparison: {common, only_a, only_b, rank_changes} | null}`.

**Chaîne en JSON** (intention et `localStorage`) :

```json
{"label_fr": "B", "stages": [
  {"id": "s1", "kind": "chunking", "option": "paragraphs", "params": {"chunk_max_chars": 300}},
  {"id": "s3", "kind": "vector_store", "option": "memory", "params": {}},
  {"id": "s6", "kind": "context", "option": "excerpts", "params": {"top_k": 2}}]}
```

**Versions vérifiées le 2026-09-28** (PyPI JSON et `uv pip compile --python-version 3.13 --python-platform x86_64-pc-windows-msvc --only-binary :all:`) :
- `faiss-cpu==1.15.1`, publié le 2026-09-16, MIT : roue `cp313-cp313-win_amd64` de 16,3 Mo, `cp310-abi3-manylinux_2_28` pour le conteneur. Il dépend de `numpy` (déjà verrouillé en 2.5.3, via llama-cpp-python) et de `packaging`.
- `lancedb==0.39.0`, publié le 2026-09-17, Apache-2.0 : roue `cp310-abi3-win_amd64` de 103 Mo. Il tire `pyarrow==25.0.1` (`cp313-win_amd64`), `lance-namespace` et `lance-namespace-urllib3-client` 0.13.0 (Apache-2.0), et `deprecation` 2.1.0.
- En tout, six paquets nouveaux dans le verrou. Essai dans le conteneur (Linux) : import de faiss en 0,15 s pour +16 Mo, import de lancedb en 2,0 s pour +104 Mo. Aucun `connect` réseau n'est apparu (`strace`), sous une garde d'audit.

**`uv lock` dans le conteneur.** Le proxy refuse `abetlen.github.io` et `github.com` (403), si bien que `uv lock` échoue sur llama-cpp-python. La recette suivante a été vérifiée le 2026-09-28 :
1. Dans le scratchpad, copier `pyproject.toml` (avec l'extra), `uv.lock` et `README.md`.
2. Remplacer la source de llama-cpp-python par un paquet factice local (`[tool.uv.sources] llama-cpp-python = { path = "stub" }`, version 0.3.35, mêmes dépendances : `typing-extensions`, `numpy`, `diskcache`, `jinja2`), puis retirer `no-build-package`, et lancer `uv lock`.
3. Recoller le bloc `[[package]] llama-cpp-python` et sa ligne `specifier` d'origine dans le verrou obtenu.
4. Copier le résultat dans le dépôt, puis lancer `uv lock --check --offline`, qui doit répondre « Resolved 97 packages ». Ensuite, `uv sync --extra compression --extra rag-alt` passe par PyPI.

**Emprunt et état.** Le laboratoire s'exécute sur le worker, donc en série avec `_sync_rag` et les tours : un embedder emprunté ne peut pas être fermé pendant un run. `rag_lab` n'est pas `idle`, si bien que les tours, la réinitialisation et les constructions sont refusés pendant ce temps, avec la raison « Atelier RAG : exécution en cours ».

## Verification

**Commands:**
- `uv run ruff check .` -- expected: aucune erreur
- `uv run ruff format --check .` -- expected: aucun fichier à reformater
- `uv run pytest -q` -- expected: tout vert, y compris `tests/test_rag_lab*.py`, `test_web_app.py` et `test_web_tokens.py`
- `uv lock --check --offline` -- expected: verrou cohérent (incrément 3)
- `uv run --extra compression --extra rag-alt pytest -q tests/test_rag_lab_alt.py` -- expected: tests FAISS et LanceDB passés, non sautés (incrément 3)
- `uv run --with playwright==1.56.0 python tools/e2e/run_e2e.py` -- expected: aucun FAIL ; scénario `rag_lab` passé ; captures `NN-atelier-rag-*` écrites dans `tools/e2e/screenshots/`

**Manual checks (if no CLI):**
- Relire les captures dans les deux thèmes : chaîne lisible d'un coup d'œil, sept cartes sur une ligne à 1 600 px, comparaison en deux colonnes sans texte coupé.

## Décisions prises par défaut

- **Génération non exécutée** dans le laboratoire. L'étape est dessinée, avec le contexte construit comme entrée. L'exécuter reviendrait à dupliquer un tour, sa jauge et ses bornes, et l'atelier des briques comme l'écran « LLM nu » le montrent déjà.
- **Bac à sable** : le laboratoire ne change pas la brique RAG. Deux sources de vérité pour la même brique seraient source de confusion en séance.
- **Classe (b), nouvel état `rag_lab`, exécution sur le worker** plutôt que sur un fil à part. Cela met en série l'emprunt des modèles et les tours sans verrou supplémentaire (AD-24).
- **Emprunter ou charger, puis fermer** l'embedder et le reranker à chaque run : aucun créneau AD-8 n'est tenu deux fois. Recharger coûte de l'ordre de la seconde, ce qui est acceptable.
- **Imports de FAISS et LanceDB comptés à vie** dans des créneaux propres, au coût déclaré (`[rag_lab]`) : un module Python ne se décharge pas.
- **Cache de vecteurs du corpus** partagé par toutes les bases : il montre la séparation indexation / requête et évite de réembedder pour chaque option. Il est au format `array('f')`, en bibliothèque standard, sans dépendre directement de numpy.
- **Index de la brique réutilisé** quand il correspond à la clé : aucune reconstruction inutile, et l'écriture ne vise que `rag_lab_dir()`.
- **Pas de purge automatique** de `rag_lab/`, car les index sont petits (moins de 1 Mo par clé pour le corpus livré). Le README dit qu'on peut supprimer le dossier.
- **fastembed** n'est proposé que s'il est installé, déclaré et présent hors ligne (`local_files_only`). Le laboratoire ne le télécharge jamais, conformément à AD-15.
- **BM25 et fusion à l'incrément 4**, dans l'ordre donné par le contexte. Ils sont en Python pur, avec RRF (k = 60) comme fusion standard.
- **Déplacement par boutons**, pas par glisser-déposer : c'est accessible au clavier, testable en E2E, et un seul geste à expliquer.
- **Règles de chaîne** : le socle est fixe, et seul le segment de récupération (recherches, fusion, reranking) se réordonne. Tout autre ordre n'aurait pas de sens exécutable.
- **Comparaison de deux configurations au plus**, exécutées l'une après l'autre : c'est ce que demande la story, et l'écran reste lisible à 1 600 px. Il ne s'agit pas d'un comparateur de modèles (non-goal).
- **Accès** : lien dans la barre haute, groupé avec celui de la story 29, puis `nav.page-tabs` sur `/rag`, sur le modèle de `/models`.
- **Extra `rag-alt`** : versions exactes, roues seulement (`no-build-package`), et commande d'installation avec `--extra compression`, pour ne pas retirer Headroom.
- **SSE recopié dans `rag.js`** plutôt que de refactoriser `app.js`, qui est gros et modifié par huit stories cette nuit : aucun risque de régression sur l'atelier.

## À vérifier sur PC

- **Installation de l'extra sans droits d'administrateur**
  - **Geste** : dans PowerShell, depuis le dossier de WaveStack, lancer `uv sync --extra compression --extra rag-alt`, puis `uv run wavestack`.
  - **Attendu** : installation sans invite UAC ni pare-feu, et FAISS et LanceDB disponibles dans `/rag`.
  - **Critère** : code de sortie 0 ; durée et taille de `.venv` notées ; aucune boîte de dialogue.
  - **Moyen** : à la main, ou script PowerShell.
- **DLL non signées (AppLocker ou WDAC)**
  - **Geste** : `/rag`, base vectorielle FAISS puis LanceDB, « Lancer la chaîne ».
  - **Attendu** : le run passe ; si un import est bloqué, l'étape en `error` dit pourquoi et le reste fonctionne.
  - **Critère** : aucune `pageerror` ; WaveStack reste utilisable.
  - **Moyen** : Claude in Chrome ou Playwright.
- **Chaîne livrée avec les vrais modèles**
  - **Geste** : `/rag`, question « Combien de jours de télétravail par semaine ? », « Lancer », avec granite-embedding et bge-reranker (Qwen3.5-2B actif).
  - **Attendu** : les sept étapes sont renseignées, et le reranking réordonne.
  - **Critère** : run complet en moins de 15 s ; RSS de WaveStack sous le budget (4 Go) ; mémoire affichée par étape relevée.
  - **Moyen** : script AppSession, puis Playwright pour la capture.
- **Coût mémoire réel des imports**
  - **Geste** : RSS avant et après la première exécution FAISS, puis LanceDB (Gestionnaire des tâches ou script `psutil`).
  - **Attendu** : les ajouts réels sont relevés.
  - **Critère** : chaque ajout mesuré est au plus égal à `[rag_lab] faiss_cost_mb` (60) et `lancedb_cost_mb` (180). Sinon, ajuster les valeurs.
  - **Moyen** : script AppSession.
- **Taille des extraits et reconstruction**
  - **Geste** : chaîne B avec des extraits de 300 caractères, deux runs de suite.
  - **Attendu** : premier run « calculés (77 passages) », second « relus du cache ».
  - **Critère** : durée de l'embedding du premier run notée (cible : moins de 10 s) ; second run au moins 5 fois plus court sur cette étape.
  - **Moyen** : Playwright.
- **Hors ligne**
  - **Geste** : mode avion, puis `/rag` avec la comparaison sqlite-vec / LanceDB.
  - **Attendu** : tout fonctionne.
  - **Critère** : aucune erreur réseau ; aucune invite du pare-feu.
  - **Moyen** : à la main.
- **Rien dans le dépôt**
  - **Geste** : après les runs, lancer `git status` et regarder `%LOCALAPPDATA%\WaveStack\rag_lab`.
  - **Attendu** : les index sont dans le dossier de données seulement.
  - **Critère** : `git status` propre.
  - **Moyen** : PowerShell.
- **Lisibilité en séance**
  - **Geste** : dans Chrome puis Edge, zoom à 125 %, comparaison A/B et chaîne hybride, dans les thèmes clair et sombre, projetées.
  - **Attendu** : chaîne et colonnes lisibles depuis le fond de la salle.
  - **Critère** : Anaël lit les rangs et les scores à 3 m ; aucune colonne coupée à 1 600 × 1 000.
  - **Moyen** : à la main (œil humain).
- **Arrêt pendant un calcul réel**
  - **Geste** : extraits de 300 caractères, cache supprimé, « Lancer » puis « Arrêter » pendant l'embedding.
  - **Attendu** : l'étape passe en « arrêtée », le retour en `idle` suit, et aucun fichier partiel ne reste.
  - **Critère** : arrêt en moins de 2 s ; aucun dossier `.tmp` restant sous `rag_lab`.
  - **Moyen** : Playwright.
