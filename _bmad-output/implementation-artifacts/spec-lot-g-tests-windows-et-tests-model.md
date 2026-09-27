---
title: 'Lot G : tests portables sous Windows et tests model du RAG'
type: 'bugfix'
created: '2026-09-27'
status: 'done'
baseline_revision: '515c858c59fd5040ed62a76780ae94a817432615'
review_loop_iteration: 0
followup_review_recommended: false
context:
  - '{project-root}/_bmad-output/implementation-artifacts/plan-corrections-palier-2.md'
  - '{project-root}/CLAUDE.md'
warnings: []
deferred:
  - summary: >-
      La suite par défaut n'a pas tourné sous Windows, ni les tests `model` du RAG avec les vrais modèles.
    evidence: |-
      Non vérifié ici : simulation des règles de fichiers de Windows (`WAVESTACK_TEST_WINDOWS_FILES=1`) sans échec, conteneur sans modèles. Se tranche sur le PC cible : `uv run pytest -q`, puis `-m model` avec `WAVESTACK_TEST_MODELS_DIR`.
    location: >-
      tests/
    severity: medium (unverified)
---

<intent-contract>

## Intent

**Problem:** (G1) Deux tests échouent sous Windows (`WinError 5`) : `test_an_index_replaced_during_the_session_is_read_again` et `test_an_index_replaced_with_the_reranker_loaded_closes_it` remplacent `rag_index.sqlite` par `os.replace` pendant qu'une session le tient ouvert, ce que Linux permet et Windows refuse. Le script `scripts/build_rag_index.py`, lancé pendant une session, échoue alors avec un message brut. (G2) Les tests `model` du RAG ne trouvent jamais les vrais modèles (`_isolated_data_dir` pointe le dossier de données vers un dossier temporaire), ils sont toujours sautés ; et `test_real_reranker_puts_the_password_document_first` planterait (`0 <= s` sur un `RerankScore`). (G3) Le guide de test annonce un nombre de tests périmé.

**Approach:** (G1) les tests ferment d'abord la connexion de la session à l'index, comme le fait la carte RAG avant de reconstruire, et vérifient ensuite la même chose, sans dépendre de la sémantique de `os.replace` de Linux ; un index verrouillé par une session produit une erreur claire en français (« WaveStack utilise l'index : construisez-le depuis la carte RAG, ou arrêtez WaveStack »), testée en simulant le refus du remplacement. (G2) variable `WAVESTACK_TEST_MODELS_DIR` qui pointe les tests `model` vers le vrai dossier des modèles ; comparaison sur `s.score`. (G3) le nombre de tests du guide est mis à jour au lot I, avec le compte final.

## Boundaries & Constraints

**Always:** code en anglais, textes en français ; `uv`, `ruff`, `pytest` ; la suite par défaut passe sous Linux et sous Windows : aucun test ne remplace, ne renomme ni ne supprime un fichier qu'une connexion ou un descripteur ouvert du même processus tient encore ; les tests `model` restent sautés sans GGUF ni variable ; ce que chaque test G1 vérifie aujourd'hui (index remplacé détecté, brique indisponible avec la raison, modèles libérés) reste vérifié.

**Never:** changer le comportement de la carte RAG (elle libère déjà l'index avant de reconstruire) ; retirer un test ; exiger un vrai modèle pour la suite par défaut.

## I/O & Edge-Case Matrix

| Scenario | Input / State | Expected Output / Behavior | Error Handling |
|----------|--------------|---------------------------|----------------|
| Index remplacé pendant la session | Session RAG ouverte, connexion fermée, index reconstruit avec un autre modèle | Au tour suivant : recherche en erreur « remplacé », carte indisponible avec la raison, modèles libérés (embedding, reranker) | — |
| Index verrouillé | Remplacement refusé par le système (`PermissionError`, simulé) | `build_index` lève une erreur au message français ; le fichier temporaire est supprimé ; le script sort en 1 avec ce message | — |
| Tests `model` avec modèles | `WAVESTACK_TEST_MODELS_DIR` pointe le dossier des modèles, `-m model` | Les tests du RAG trouvent les fichiers et tournent | Variable absente ou fichier manquant : test sauté avec la raison |
| Reranker réel | Scores `RerankScore` | Bornes vérifiées sur `s.score` | — |

</intent-contract>

## Code Map

- `src/wavestack/rag/index.py:138-152` -- `build_index` : écrit `path.tmp`, puis `os.replace(tmp, path)` ; en cas d'exception, supprime le temporaire.
- `scripts/build_rag_index.py:100-110` -- attrape `OSError` et affiche « Index non construit : {exc}. » (sortie 1).
- `src/wavestack/session/app_session.py` -- `_run_build` (carte RAG, l.~4292), `_release_embedder` / `_close_embedder` → `retriever.close()` (idempotent, `rag/retriever.py:81-85`) ; `_stamp` (mtime_ns, taille) et la détection du remplacement (l.~4780-4792).
- `tests/test_rag_review.py:336-349`, `tests/test_rag_rerank.py:570-580` -- les deux tests G1 ; `tests/test_rag.py:73-76` -- helper `build(index, model_id=…)` → `rag_index.build_index`.
- `tests/conftest.py:27-30` -- `_isolated_data_dir` (`WAVESTACK_DATA_DIR` = dossier temporaire ; `config.models_dir()` = `data_dir()/models`, `config.py:~613`).
- Tests `model` du RAG : `tests/test_rag.py:529` (`test_real_embedding_model_finds_the_password_document`), `tests/test_rag_rerank.py:779-794` (`test_real_reranker_puts_the_password_document_first` : `0 <= s <= 1` sur des `RerankScore`) ; `src/wavestack/models/reranker.py:22-26` -- `RerankScore(score, truncated)`.
- `pyproject.toml` -- marqueur `model`, `addopts = "-m 'not model'"`.
- `_bmad-output/implementation-artifacts/deferred-work.md` -- deux entrées du 2026-09-27 du lot G (tests Windows, tests `model` du RAG), à fermer.

## Tasks & Acceptance

**Execution:**
- `src/wavestack/rag/index.py` -- `build_index` : un `PermissionError` au remplacement devient une erreur (sous-classe d'`OSError`) au message « WaveStack utilise l'index : construisez-le depuis la carte RAG, ou arrêtez WaveStack, puis relancez ce script. » ; le temporaire est supprimé.
- `scripts/build_rag_index.py` -- affiche ce message tel quel (sans la représentation brute de l'exception).
- `tests/test_rag_review.py`, `tests/test_rag_rerank.py` -- avant `build(...)`, fermer la connexion de la session à l'index (le retriever, comme la carte RAG) ; mêmes vérifications qu'aujourd'hui.
- `tests/test_rag.py` (ou fichier voisin) -- test : `os.replace` simulé en `PermissionError` → erreur au message français, temporaire supprimé ; test du script : sortie 1 et message.
- `tests/conftest.py` ou fixture des tests `model` -- `WAVESTACK_TEST_MODELS_DIR` : les tests `model` du RAG lisent les modèles dans ce dossier (le dossier de données reste isolé) ; saut avec la raison si la variable ou le fichier manque.
- `tests/test_rag_rerank.py` -- `0 <= s.score <= 1`.
- Recherche dans `tests/` d'autres remplacements, renommages ou suppressions de fichiers encore ouverts dans le processus (index, `memory.json`, `settings.json`, journaux) : les rendre portables de la même façon.
- `_bmad-output/implementation-artifacts/deferred-work.md` -- fermer les deux entrées du lot G (G3 renvoyé au guide, lot I).

**Acceptance Criteria:**
- Given la suite par défaut sous Windows, when elle tourne, then les deux tests G1 passent.
- Given `WAVESTACK_TEST_MODELS_DIR` et `-m model`, when les tests du RAG tournent sur le PC, then ils trouvent les modèles et passent.

## Spec Change Log

## Review Triage Log

### 2026-09-27 — Review pass
- verdicts: 12 findings (constats des quatre couches, doublons regroupés avec leurs sources) — high 0, medium 3, low 6, false 0, maybe-false 3
- findings:
  - `[medium]` `[patch]` Tout `PermissionError` (fichier en lecture seule, dossier protégé, antivirus) annoncé comme « WaveStack utilise l'index » (blind, edge) — correspondance restreinte (cible modifiable, `winerror` 5 ou 32), sinon l'erreur d'origine ; test du cas lecture seule.
  - `[medium]` `[patch]` Message du script affiché aussi par la carte RAG (« relancez ce script ») (blind, edge, verification-gap, intent) — message neutre dans la bibliothèque, conseil propre au script et à la carte, test de la carte.
  - `[medium]` `[patch]` Chemin Linux (index remplacé encore ouvert) plus couvert, et état hybride décrit à tort comme celui de la carte (blind, edge, intent) — variante Linux/macOS gardée, commentaires exacts.
  - `[low]` `[patch]` Tests `model` : `AttributeError` si la configuration du modèle est invalide (edge) — saut avec la raison.
  - `[low]` `[patch]` Test du script sans vérifier l'index intact (blind) — ajouté.
  - `[low]` `[patch]` `IndexInUse` non sérialisable (blind) — `*args`.
  - `[low]` `[patch]` Deux syntaxes de chemin Windows (blind) — forme PowerShell.
  - `[low]` `[patch]` Simulation Windows non versionnée, aucun garde-fou (blind, intent) — garde facultative `WAVESTACK_TEST_WINDOWS_FILES=1`, testée.
  - `[low]` `[reject]` Entrées fermées avant le passage sous Windows (blind) — consigne de l'utilisateur ; « à vérifier sur PC » noté et repris dans le guide.
  - `[maybe-false]` `[reject]` Sous Windows, le script ne peut plus remplacer l'index d'une session ouverte : ouvrir une connexion par recherche (blind) — comportement voulu par le plan (message clair), la carte libère l'index ; si vrai : low.
  - `[maybe-false]` `[reject]` Les tests `model` contournent `config.models_dir()` (intent) — la variable du plan pointe un dossier de modèles sans toucher au dossier de données isolé ; si vrai : low.
  - `[maybe-false]` `[defer]` Suite par défaut sous Windows et tests `model` avec les vrais modèles non exécutés (intent) — si vrai : medium ; se tranche en lançant la suite sur le PC cible.

## Verification

**Commands:**
- `uv run ruff check .` -- expected: aucun problème
- `uv run ruff format --check .` -- expected: aucun fichier à reformater
- `uv run pytest -q` -- expected: tout vert
- `uv run pytest -q -m model tests/test_rag.py tests/test_rag_rerank.py` -- expected: tests sautés avec la raison (pas de modèle ici)

## Auto Run Result

Status: done

**Résumé.** (G1) Les deux tests qui échouaient sous Windows ferment la connexion de la session avant de reconstruire l'index (variante portable, détection du remplacement par l'empreinte du fichier) ; la variante « remplacé encore ouvert » est gardée sous Linux et macOS. Un remplacement refusé parce qu'un programme tient l'index (Windows, `winerror` 5 ou 32, cible modifiable) devient `IndexInUse`, au message neutre ; le script ajoute son conseil (carte RAG ou arrêt de WaveStack), la carte RAG le sien ; les autres refus gardent leur erreur d'origine. Garde facultative `WAVESTACK_TEST_WINDOWS_FILES=1` qui applique à toute la suite, sous Linux, la règle de Windows (pas de remplacement, renommage ni suppression d'un fichier ouvert). (G2) `WAVESTACK_TEST_MODELS_DIR` pointe les tests `model` du RAG vers le vrai dossier des modèles (saut expliqué sinon) ; comparaison sur `s.score`. (G3) renvoyé au guide (lot I).

**Fichiers.** `src/wavestack/rag/index.py`, `scripts/build_rag_index.py`, `src/wavestack/session/app_session.py` (`_run_build`), `tests/conftest.py`, `tests/test_rag.py`, `tests/test_rag_review.py`, `tests/test_rag_rerank.py`, `deferred-work.md` (deux entrées fermées).

**Revue.** 8 patchs (3 medium, 5 low), 1 différé (passage sous Windows et tests `model` réels), 3 rejetés. `followup_review_recommended: false`.

**Vérification.** `ruff check`, `ruff format --check` : OK ; `pytest -q` : 930 réussis, 7 sautés ; avec `WAVESTACK_TEST_WINDOWS_FILES=1` : 928 réussis, 9 sautés (les deux variantes « remplacé encore ouvert » sautées) ; `-m model` du RAG : sautés avec la raison.

**Risques résiduels (à vérifier sur PC).** Suite par défaut sous Windows (0 échec attendu) ; `-m model` avec `$env:WAVESTACK_TEST_MODELS_DIR = "$env:LOCALAPPDATA\WaveStack\models"`.
