---
title: 'Démarrage sans scan du disque et bouton « Ajouter d''autres modèles » (story 4)'
type: 'feature'
created: '2026-10-15'
status: 'review'
route: 'dispatch'
review_loop_iteration: 0
context: []
baseline_commit: '61c3e1a'
---

## Intent

**Problem:** CAP-4 (SPEC.md de `spec-wavestack-v1-1-vague-1`) : au démarrage, `discover()`
parcourt `models_dir`, le cache Hugging Face (`~/.cache/huggingface/hub`), les dossiers de
LM Studio et Ollama. Sur le poste d'un testeur avec beaucoup de GGUF ailleurs sur le disque,
ce parcours peut figer la machine (douleur constatée, voir SPEC.md > Why). Ollama reste bon
marché (un appel HTTP local), mais le cache HF et LM Studio lisent le disque.

**Approach:** `discover()` prend un paramètre `extended` (par défaut `False`) : à `False`,
le cache HF et LM Studio ne sont pas lus ; `models_dir`, le chemin explicite, Ollama et les
serveurs déjà lancés restent lus comme avant. Le démarrage (`DiagnosticSession.check_model`,
via `run()`) appelle toujours `discover()` sans l'étendre. Un nouveau bouton du sélecteur de
modèles, « Ajouter d'autres modèles… », appelle une nouvelle intention
`POST /api/intentions/search_more` qui active `extended` pour le reste de la session et
rafraîchit la liste des candidats ; les appels suivants (changement de modèle compris)
gardent cette recherche étendue.

## Boundaries & Constraints

**Always:**
- L'ordre AD-7 des candidats est inchangé ; seule la présence des sources `hf_cache` et
  `lm_studio` dépend de `extended`.
- Les trois appelants existants de `discovery.discover()` dans `session/diagnostic.py`
  passent par `_discover()`, qui lit le drapeau de la session (`self._extended`) : aucun ne
  force `extended=True` au démarrage.
- Les textes de l'interface passent par `content/ui.yaml` et ses surcouches `en`/`de`
  (`main.model.picker_search_more`, `main.model.search_more_apply`).
- Les callers hors `discover()` (catalogue, cartes de modèles) ne changent pas.

**Never:** ne pas toucher `docs/` (story 2, lane A) ; ne pas changer `app.js` pour autre
chose que ce bouton (story 5, lane B, vient après) ; pas de nouvelle dépendance ; pas de
lancement d'E2E dans cette story (laissé à l'orchestrateur).

## I/O & Edge-Case Matrix

| Scenario | Input / State | Expected Output / Behavior | Error Handling |
|----------|--------------|---------------------------|----------------|
| Démarrage | `discover()` sans argument | `hf_cache` et `lm_studio` absents des candidats | N/A |
| Démarrage, fichiers ailleurs | GGUF présents dans le cache HF et chez LM Studio | Toujours absents des candidats tant que `extended` n'a pas été demandé | N/A |
| Bouton cliqué | `POST /api/intentions/search_more` | `discover(extended=True)` ; `/api/diagnostic` suivant liste les nouveaux candidats | N/A |
| Après le bouton | Un second changement de modèle (`select_model`) | La recherche reste étendue (gardée pour la session) | N/A |
| Hors `idle`/`diagnostic` | `search_more` pendant un tour | 409, comme les autres intentions de classe (b) | `_diagnostic_class_b` |

## Code Map

- `src/wavestack/models/discovery.py` -- `discover(explicit_path=None, *, extended=False)` :
  le bloc `hf_cache` + `lm_studio` n'est exécuté que si `extended`.
- `src/wavestack/session/diagnostic.py` -- `DiagnosticSession.__init__` : `self._extended =
  False` ; `_discover()` passe `extended=self._extended` à `discover()` ; nouvelle méthode
  `search_more()` (active `self._extended`, relance `_discover()`, met à jour
  `self.last_result.candidates`).
- `src/wavestack/web/app.py` -- nouvelle route `POST /api/intentions/search_more`
  (`_diagnostic_class_b()`, puis `session.search_more()`).
- `src/wavestack/web/static/app.js` -- `rebuildModelPicker` et `rebuildModelPickerByKind` :
  nouvelle option `PICK_SEARCH_MORE` avant « Autre fichier ou clé API… » ; `applyPick`
  dispatche vers la nouvelle fonction `searchMore()` (POST puis `loadModelList()`).
- `content/ui.yaml`, `content/i18n/{en,de}/ui.yaml` -- `main.model.picker_search_more`,
  `main.model.search_more_apply`.
- `tools/e2e/run_e2e.py` -- `s_model_catalog` : la liste des trois dernières options du
  sélecteur inclut maintenant « Ajouter d'autres modèles… ».
- `tests/test_discovery.py` -- nouveaux tests du drapeau `extended`.

## Tasks & Acceptance

**Execution:**
- [x] `src/wavestack/models/discovery.py` -- `extended` par défaut à `False`
- [x] `src/wavestack/session/diagnostic.py` -- drapeau de session, `_discover`, `search_more`
- [x] `src/wavestack/web/app.py` -- `POST /api/intentions/search_more`
- [x] `src/wavestack/web/static/app.js` -- option et bouton « Ajouter d'autres modèles… »
- [x] `content/ui.yaml` + surcouches `en`/`de`
- [x] `tools/e2e/run_e2e.py` -- `s_model_catalog` adapté à la nouvelle option
- [x] `tests/test_discovery.py` -- comportement par défaut et étendu

**Acceptance Criteria:**
- Given un dossier `models_dir` vide mais des GGUF dans le cache HF et chez LM Studio, when
  `discover()` est appelé sans argument, then aucun candidat `hf_cache` ni `lm_studio`.
- Given le même état, when `discover(extended=True)` est appelé, then les deux sont listés.
- Given le sélecteur de modèles ouvert, when « Ajouter d'autres modèles… » est choisi, then
  la session recherche en étendu et le sélecteur se recharge avec les modèles trouvés.

## Implementation Notes

- `_server_candidates` (serveurs déjà lancés) et `_ollama_candidates` restent lus dans tous
  les cas : un appel HTTP local et une lecture du dossier d'Ollama, jamais le disque entier
  (hypothèse de SPEC.md).
- Le drapeau `extended` est gardé pour le reste de la session une fois activé (pas de
  re-restriction après un clic), pour que le modèle trouvé reste sélectionnable ensuite.
- `ruff` et `pytest -q tests/test_discovery.py` verts (11 passed). Suite complète non
  relancée dans cette story (contrainte 16 Go) ; les modules qui isolent déjà le cache HF et
  LM Studio par un environnement vide (`test_web_app.py`, `test_cli_diagnostic.py`,
  `test_model_switch.py`, `test_model_servers.py`, `test_cloud.py`,
  `test_context_window_setting.py`, `test_memory_budget.py`) ne sont pas affectés par le
  nouveau défaut (ils fixaient déjà `extended=False` de fait).
- E2E non lancé (consigne de l'orchestrateur) : `s_model_catalog` adapté par relecture du
  code, à vérifier à l'intégration.

## Spec Change Log

## Review Triage Log

## Verification

**Commands:**
- `python .claude/cost-kit/controle_rapide.py` -- expected: aucune erreur
- `uv run pytest -q --tb=short tests/test_discovery.py` -- expected: tous les tests passent
- `uv run --with playwright==1.56.0 python tools/e2e/run_e2e.py --channel msedge --only model_catalog` -- expected: scénario vert (laissé à l'orchestrateur)

**Manual checks (if no CLI):**
- Lancer WaveStack, ouvrir le sélecteur de modèles, choisir « Ajouter d'autres modèles… » :
  le sélecteur propose « Rechercher », puis liste les modèles trouvés dans le cache HF ou
  chez LM Studio s'il y en a.
