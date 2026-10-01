---
title: 'Constats différés : rag_rerank sous charge, table cl100k_base hors ligne'
type: 'bugfix'
created: '2026-10-01'
status: 'done'
baseline_revision: 'f06e34b77a7d1c595f35d935bf2ff56e2aa1a9fe'
review_loop_iteration: 0
followup_review_recommended: true
context:
  - '{project-root}/_bmad-output/specs/spec-corrections-2026-09-30/SPEC.md'
warnings: []
deferred:
  - summary: >-
      Headroom ne trouve plus hors ligne la table o200k_base du tokenizer gpt-4o et se rabat sur une estimation pour ce comptage.
    evidence: |-
      stderr du test hors ligne : « Failed to create tokenizer for gpt-4o: Hôte réseau non autorisé : openaipublic.blob.core.windows.net. Falling back to estimation. » Avant la story, TIKTOKEN_CACHE_DIR pointait sur le dossier de litellm, qui livre aussi fb374d… (o200k_base) ; il pointe désormais sur la seule table livrée (cl100k_base). La compression fonctionne (texte compressé, aucune tentative publique). Correctif possible : livrer aussi o200k_base (LF, sha256 vérifié) ou copier les tables de litellm dans le cache du dossier de données au lancement.
    location: >-
      src/wavestack/compression/env.py
    severity: medium
  - summary: >-
      CUSTOM_TIKTOKEN_CACHE_DIR et TIKTOKEN_CACHE_DIR pointent sur un dossier suivi du dépôt (src/wavestack/compression/tiktoken/) : une écriture de cache de tiktoken ou de litellm y atterrirait.
    evidence: |-
      Non observé : la table est vérifiée avant l'import (une table fausse rend la brique indisponible avant que tiktoken ne la supprime) et la garde réseau bloque les téléchargements. À trancher : copier la table dans le cache du dossier de données au lancement garderait src/ en lecture seule.
    location: >-
      src/wavestack/compression/env.py:55-60
    severity: medium (unverified)
  - summary: >-
      Le banc de la story 12 (tools/bench/story12_bench.py) garde l'ancienne logique (TIKTOKEN_CACHE_DIR vers litellm, CUSTOM_TIKTOKEN_CACHE_DIR retiré) et son README le décrit encore ainsi.
    evidence: |-
      Outil de mesure de développement, hors du chemin de l'application ; sa variante « configurée » ne mesure plus ce que fait WaveStack sur un .venv neuf.
    location: >-
      tools/bench/story12_bench.py:857-891, tools/bench/README.md:40-42
    severity: low
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

## Review Triage Log

### 2026-10-01 — Review pass
- verdicts: 27 findings — high 1, medium 7, low 15, false 2, maybe-false 2
- findings:
  - Intent Alignment
    - `[medium]` `[patch]` La preuve exigée (trois passages E2E, tranche de 8 à 10) manquait au changement — jouée : trois passages `rag rag_rerank rag_lab` à 88/88 après correctif, tranche de 9 scénarios à 220/220.
    - `[high]` `[patch]` Cause supposée, pas établie (refus de budget « retenu ») — fausse : sur un échec réel (passage 2 sur 3), le nouveau message a dit « Chargement… », aucun `harness_error`. Cause établie : course de notification du journal (`seq` attribué sous verrou, abonnés notifiés hors verrou, le flux SSE jette l'événement doublé) et carte « Chargement » construite avant le chargement mais émise après. Corrigé dans l'application (`trace/journal.py`, `_emit_bricks`/`_emit_architecture` sous `_emit_lock`), deux tests déterministes qui échouent sur l'ancien code.
    - `[low]` `[reject]` Message d'échec E2E non testé — il a servi sur un échec réel et a donné la cause.
    - `[medium]` `[patch]` Budget fixe : toute la pile E2E en mode fixe, contrôle « Budget mémoire » réécrit — retiré (`stack.py`, test associé), contrôle dynamique rétabli.
    - `[medium]` `[patch]` Les tests hors ligne ne distinguent pas la table livrée de celle de litellm — dans ce `.venv`, la copie de litellm est absente (supprimée par tiktoken), donc les tests passent bien grâce à la table livrée ; assertion ajoutée : `TIKTOKEN_CACHE_DIR` pointe encore sur la copie après l'import et la table y est toujours.
    - `[low]` `[reject]` « Pas d'appel réseau » déduit de « Headroom non chargé » — sans Headroom ni tiktoken importés, aucun code réseau ne tourne.
    - `[low]` `[patch]` Preuves « à reporter » dans `deferred-work.md` — reportées, cause du `rag_rerank` réécrite.
  - Edge Case Hunter
    - `[low]` `[reject]` Table illisible (`OSError`) dite « absente » — cas rare ; une clé de message de plus dans trois langues pour un gain faible.
    - `[low]` `[patch]` La cause des `harness_error` manque au message d'échec — ajoutée.
    - `[medium]` `[patch]` Budget fixe de 8 192 Mo au-dessus de la RAM libre → `fixed_over` — budget fixe retiré.
    - `[maybe-false]` `[defer]` Les autres tables de litellm (`o200k_base`) ne sont plus atteignables — confirmé ensuite par le stderr du test hors ligne (repli sur estimation pour `gpt-4o`) ; différé, sévérité medium.
    - `[low]` `[patch]` Cause des `harness_error` omise (doublon) — même correctif.
  - Verification Gap
    - `[medium]` `[patch]` Test hors ligne aveugle à la table réellement lue (doublon) — même assertion.
    - `[low]` `[defer]` Banc de la story 12 resté sur l'ancienne logique — outil de développement ; différé.
    - `[medium]` `[patch]` Avertissement `fixed_over` dans les captures (doublon) — budget fixe retiré.
  - Blind Hunter
    - `[low]` `[patch]` Entrées fermées avant la preuve (doublon) — reportées.
    - `[false]` `[reject]` Suivi produit du budget dynamique trop petit — la cause n'était pas le budget.
    - `[medium]` `[patch]` Budget fixe et avertissement (doublon) — retiré.
    - `[low]` `[patch]` Contrôle E2E du budget dynamique perdu — rétabli.
    - `[low]` `[patch]` sha256 comparé à une copie du même littéral — comparé à celui que tiktoken lit dans `tiktoken_ext/openai_public.py` (`inspect`).
    - `[maybe-false]` `[defer]` Cache de tiktoken dans un dossier suivi de `src/` — non observé ; différé avec ce qui le trancherait.
    - `[low]` `[defer]` Clés `compression.*` sœurs (`install`, `missing`…) sans en/de — préexistant ; story 7 (traductions restantes).
    - `[low]` `[patch]` README et ARCHITECTURE-SPINE non mis à jour — README (table de comptage, restauration) et SPINE (variables) mis à jour.
    - `[low]` `[patch]` Provenance de la licence incohérente — `LICENSE-tiktoken` dit la copie depuis litellm, sans téléchargement ; vérification de licence à faire avant le GitLab interne (rapport).
    - `[low]` `[patch]` Conseil de réparation vague, anglais peu idiomatique — « restaurez… (`git checkout -- src/wavestack/compression/tiktoken`) » en fr, en, de.
    - `[low]` `[reject]` `env` importé deux fois, retour en chaînes — style, sans défaut nommé.
    - `[false]` `[reject]` Le message ne nomme pas l'état de chargement — il le nomme (« raison : Chargement du modèle de reranking… »), vu sur l'échec réel.

## Auto Run Result

- **Résumé** : (A) instabilité de `rag_rerank` : cause réelle établie et corrigée dans l'application (ordre de notification du journal, carte construite et émise sous un même verrou) ; message d'échec explicite dans l'E2E. (B) table `cl100k_base` livrée (LF, sha256 de tiktoken, MIT), `CUSTOM_TIKTOKEN_CACHE_DIR` posé, brique compression indisponible avec sa raison si la table manque ou est altérée.
- **Fichiers** : `trace/journal.py`, `session/app_session.py`, `compression/env.py`, `compression/headroom_adapter.py`, `compression/tiktoken/` (table, licence), `.gitattributes`, `content/messages.yaml` et surcouches, `tests/test_compression.py`, `tests/test_web_app.py`, `tests/test_rag_rerank.py`, `tools/e2e/run_e2e.py`, README, ARCHITECTURE-SPINE, `deferred-work.md`.
- **Revue** : 27 constats ; 1 `high` et 4 `medium` corrigés (vraie cause, preuve, budget fixe retiré, test de la table lue), 3 différés, rejets motivés.
- **Revue de suivi recommandée** : `true` (un `high` corrigé). Risque nommé : le verrou de notification du journal sert tous les émetteurs ; un abonné qui bloquerait ou prendrait un verrou tenu par un émetteur gèlerait les événements (abonnés actuels vérifiés : aucun).
- **Vérification** : `ruff` propre ; tests de la spec 3 249 passés (aucun ignoré) ; E2E `rag rag_rerank rag_lab` 3 × 88/88 ; point de contrôle de la version de démo : pytest en quarts 3 513 (2 échecs de mon test, corrigés : `test_compression` 38/38) + 603 + 310 (3 ignorés) + 332, E2E `rag rag_rerank rag_lab compression busy_and_stop reload_and_reset global_memory mcp_full model_switch` 220/220.
- **Risques résiduels** : comptage `gpt-4o` de Headroom estimé hors ligne (différé) ; licence de la table à confirmer avant diffusion interne.