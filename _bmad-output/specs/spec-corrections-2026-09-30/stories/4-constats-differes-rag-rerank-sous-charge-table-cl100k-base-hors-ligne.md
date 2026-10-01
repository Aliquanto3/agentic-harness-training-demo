---
title: 'Constats différés : rag_rerank sous charge, table cl100k_base hors ligne'
type: 'bugfix'
created: '2026-10-01'
status: 'in-progress'
baseline_revision: 'f06e34b77a7d1c595f35d935bf2ff56e2aa1a9fe'
review_loop_iteration: 0
followup_review_recommended: false
context:
  - '{project-root}/_bmad-output/specs/spec-corrections-2026-09-30/SPEC.md'
warnings: []
deferred: []
---

<intent-contract>

## Intent

**Problem:** (A) Le scénario E2E `rag_rerank` échoue dans une tranche chargée : l'attente de `bricks_changed` avec `rerank.available` vrai (30 s) expire ; rejoué seul, il passe. (B) Dans un `.venv` neuf, Headroom ne peut pas compter hors ligne : le paquet litellm 1.102.1 livre la table `cl100k_base` (`9b5ad71b…`) avec des fins de ligne CRLF ; tiktoken en vérifie le sha256 au premier usage, la trouve fausse, la **supprime** et veut la retélécharger. Hors ligne, la compression perd sa table, et les deux tests Headroom hors ligne échouent (CAP-4 de `SPEC.md`).

**Approach:** (A) Rendre la cause visible et retirer la dépendance à la RAM libre de l'hôte : budget mémoire fixe dans la pile E2E, et un échec qui dit la raison de la carte et les `harness_error` survenus. (B) Livrer la table `cl100k_base` correcte (LF, sha256 vérifié) dans le dépôt et y pointer tiktoken par `CUSTOM_TIKTOKEN_CACHE_DIR`, la seule variable que litellm ne réécrit pas.

## Boundaries & Constraints

**Always:**
- **(A) Pile E2E** (`tools/e2e/stack.py`, réglages de la pile) : un budget mémoire fixe et large (par le réglage `[memory]` existant de `config.py`, sinon par la variable ou le réglage que `config.memory_budget` lit déjà) pour que `check_component` ne refuse jamais le reranker factice selon la RAM libre du PC. Le budget réel de l'application ne change pas.
- **(A) Scénario** `s_rag_rerank` : en cas d'expiration de l'attente, le message d'échec donne `reason_text` de `rag.rerank` (via l'état des briques) et les `harness_error` émis depuis la marque, pour distinguer un refus de budget d'une file du fil de travail encombrée. Délai d'attente inchangé sauf si la cause observée est la file : alors il suit la règle des autres attentes derrière le fil de travail (`TURN_TIMEOUT_S`), justifié dans un commentaire.
- **(A) Preuve** : la tranche `rag rag_rerank rag_lab` passe trois fois de suite, et une tranche de 8 à 10 scénarios qui contient `rag_rerank` passe une fois.
- **(B) Table livrée** : `src/wavestack/compression/tiktoken/9b5ad71b2ce5302211f9c61530b329a4922fc6a4` (nom = sha1 de l'URL, comme le cache de tiktoken), octets LF identiques à la table officielle, sha256 `223921b7…` (valeur complète relevée dans `tiktoken_ext/openai_public.py`) ; `.gitattributes` la marque `-text` pour que `core.autocrlf=true` ne la corrompe pas. Licence MIT de tiktoken citée dans un `NOTICE` ou `LICENSE-tiktoken` à côté.
- **(B) Environnement** : `apply_offline_env()` pose `CUSTOM_TIKTOKEN_CACHE_DIR` (et `TIKTOKEN_CACHE_DIR`) sur ce dossier, avant tout import de litellm ; `tiktoken_cache_dir()` rend ce dossier. Si le fichier manque ou que son sha256 ne correspond pas, la brique compression dit pourquoi elle est indisponible (message par `msg()`, trois langues) au lieu d'appeler le réseau.
- **(B) Tests** : les deux tests hors ligne copient leur table depuis le dossier livré (plus depuis le cache de litellm) ; un test vérifie le sha256 de la table livrée et l'absence de `\r` ; un test vérifie que `CUSTOM_TIKTOKEN_CACHE_DIR` est posé par `apply_offline_env()`.
- Les deux entrées de `_bmad-output/implementation-artifacts/deferred-work.md` (« rag_rerank instable sous charge », « table cl100k_base absente d'un .venv neuf ») fermées avec la cause et la preuve.

**Never:**
- Allonger une attente sans avoir établi la cause.
- Télécharger la table à l'installation ou au lancement ; ajouter une dépendance.
- Modifier les fichiers du paquet litellm installé.

## I/O & Edge-Case Matrix

| Scenario | Input / State | Expected Output / Behavior | Error Handling |
|----------|--------------|---------------------------|----------------|
| `.venv` neuf hors ligne | litellm livre `9b5ad71b…` en CRLF | la compression compte avec la table livrée par WaveStack, aucune connexion | — |
| Table livrée absente | fichier supprimé | carte compression indisponible avec la raison | pas d'appel réseau |
| Table livrée altérée | sha256 différent | même comportement que « absente » | pas d'appel réseau |
| Expiration E2E | carte `rerank` refusée | message d'échec avec la raison et les `harness_error` | — |

</intent-contract>

## Code Map

- `tools/e2e/run_e2e.py:55-98` -- `class Events` (`mark`, `since`, `wait(kind, after, pred, timeout=TURN_TIMEOUT_S=60)`) ; `s_rag_rerank` l.4105, clic « Télécharger le modèle de reranking » ≈l.4150, attente `session_state` (10 s) puis `bricks_changed` avec `rag.rerank.available` (30 s) l.4158-4166 ; `r.bricks()` pour l'état des cartes.
- `tools/e2e/stack.py:126-138` -- déclaration du reranker factice (2 048 octets, sans sha256, sans `[memory]`) ; réglages de la pile. `tools/e2e/wavestack_e2e.py:30` -- `FakeReranker` (chargement instantané).
- `src/wavestack/session/app_session.py` -- `download_model` l.5534, `_run_download` l.5619, `_rag_caught_up` l.5579, `_request_rag_sync` l.2921 (`_rerank_loading`, `executor.submit(_sync_rag)` l.2949), `_sync_rag` l.2954 (`_emit_bricks` après chargement l.2987), `_sync_reranker` l.3136, `_load_reranker` l.3170 (`check_component`) ; fil unique `ThreadPoolExecutor(max_workers=1)` l.726.
- `src/wavestack/models/load_registry.py:87,266,273` -- `process_rss` (processus et enfants), `component_cost` (+ `load_margin_mb` 256 Mo), `check_component`.
- `src/wavestack/config.py:525-557,714,750` -- calcul du budget (`min(4096, max(512, 0,6 × RAM libre))`), `memory_budget`, `load_margin_mb`.
- `src/wavestack/compression/env.py:15-43` -- `OFFLINE_ENV`, `tiktoken_cache_dir()` (cherche le dossier de litellm), `apply_offline_env()` ; appelé par `cli.py:29` et `headroom_adapter.py:111-120` (`COUNTING_MODEL = "gpt-4"` l.39).
- litellm `litellm_core_utils/default_encoding.py:18-55` -- réécrit `TIKTOKEN_CACHE_DIR` sauf si `CUSTOM_TIKTOKEN_CACHE_DIR` est posé, puis `tiktoken.get_encoding("cl100k_base")` à l'import. tiktoken `load.py:54-64` -- `read_file_cached` supprime un fichier au mauvais sha256.
- `tests/test_compression.py:688-700` (env), `:779` (`_OFFLINE_CHILD` remplace `tiktoken_cache_dir`), `:819-857` (`_tiktoken_file`, `_run_offline_child` : copie depuis le cache de litellm l.832-835), `:866`, `:878`, `:887-897`.
- `pyproject.toml` -- hatchling, `packages = ["src/wavestack"]` : tout fichier non ignoré sous le paquet est livré. `.gitattributes` -- seulement `tests/fixtures/** -text`.
- Table officielle LF (1 681 126 octets, sha256 conforme) présente dans `C:\Users\anael.yahi\Documents\GitHub\agentic-harness-training-demo\.venv\Lib\site-packages\litellm\litellm_core_utils\tokenizers\9b5ad71b2ce5302211f9c61530b329a4922fc6a4` : la copier en vérifiant son sha256 (aucun téléchargement).

## Tasks & Acceptance

**Execution:**
- `src/wavestack/compression/tiktoken/9b5ad71b2ce5302211f9c61530b329a4922fc6a4`, `src/wavestack/compression/tiktoken/LICENSE-tiktoken`, `.gitattributes` -- table livrée, licence, `-text`.
- `src/wavestack/compression/env.py` -- dossier livré, `CUSTOM_TIKTOKEN_CACHE_DIR`, vérification sha256 (constante).
- `src/wavestack/compression/headroom_adapter.py` -- raison d'indisponibilité si la table manque ou est altérée ; `content/messages.yaml` et surcouches `en`, `de`.
- `tests/test_compression.py` -- tests ci-dessus ; copie depuis le dossier livré.
- `tools/e2e/stack.py`, `tools/e2e/run_e2e.py` -- budget fixe, message d'échec explicite.
- `_bmad-output/implementation-artifacts/deferred-work.md` -- deux entrées fermées.

**Acceptance Criteria:**
- Given un `.venv` neuf sans réseau, when la brique compression s'active, then elle compte avec la table livrée et `test_headroom_makes_no_network_attempt_at_import_nor_compression` passe.
- Given la tranche E2E `rag rag_rerank rag_lab`, when elle est jouée trois fois de suite, then elle passe trois fois.

## Verification

**Commands:**
- `uv run ruff check .` et `uv run ruff format --check .` -- expected: aucun écart.
- `uv run pytest -q tests/test_compression.py tests/test_backend_messages.py tests/test_i18n.py` -- expected: tout passe (tests Headroom non sautés).
- E2E (orchestrateur) : `--only rag rag_rerank rag_lab` trois fois, puis `--only rag rag_rerank rag_lab compression busy_and_stop reload_and_reset global_memory mcp_full` -- expected: 0 échec.
